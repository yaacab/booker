"""Fail-closed, offline schema release inventory and approval check.

This module never runs migrations against a live database. A passing check is
only an input to a separately reviewed migration phase and release rehearsal.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import sqlite3
from pathlib import Path

REVISION = re.compile(r"^[a-z0-9]{12}$")
SAFE_CALLS = {"create_table", "create_index", "add_column", "create_foreign_key"}
MANUAL_CALLS = {"execute", "alter_column", "drop_column", "drop_table", "rename_table",
                "drop_constraint", "drop_index", "create_check_constraint"}


class SchemaReleaseError(RuntimeError):
    pass


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _literal_assignment(tree: ast.Module, name: str):
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == name for target in targets):
                return ast.literal_eval(node.value)
    raise SchemaReleaseError(f"missing {name}")


def classify_upgrade(tree: ast.Module) -> dict:
    upgrade = next((node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "upgrade"), None)
    if upgrade is None:
        raise SchemaReleaseError("migration has no upgrade")
    calls = set()
    for node in ast.walk(upgrade):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            calls.add(node.func.attr)
            if node.func.attr == "add_column":
                for child in ast.walk(node):
                    if (isinstance(child, ast.keyword) and child.arg == "nullable"
                            and isinstance(child.value, ast.Constant)
                            and child.value.value is False):
                        has_default = any(isinstance(part, ast.keyword)
                                          and part.arg == "server_default"
                                          for part in ast.walk(node))
                        if not has_default:
                            calls.add("nonnullable_without_default")
    reasons = sorted(calls & MANUAL_CALLS | (calls - SAFE_CALLS - MANUAL_CALLS - {
        "Column", "String", "Integer", "Boolean", "DateTime", "ForeignKey", "Text",
        "UniqueConstraint", "CheckConstraint", "text", "get_bind", "now", "utcnow",
        "uuid4", "batch_alter_table", "mappings", "all", "one", "scalar_one",
        "values", "items", "append", "str", "len", "int", "setdefault", "get",
        "isinstance", "has_table", "get_table_names", "get_columns", "connect",
        "begin", "fetchall", "fetchone", "scalar", "first", "execute",
    }))
    # SQL execution, conditional DDL, data rewrites and unknown helpers are manual.
    if "execute" in calls:
        reasons = sorted(set(reasons) | {"execute"})
    if "nonnullable_without_default" in calls:
        reasons = sorted(set(reasons) | {"nonnullable_without_default"})
    return {"classification": "manual_block" if reasons else "expand_review",
            "reasons": reasons, "reversible": False}


def inventory(versions: Path) -> list[dict]:
    entries = {}
    for path in sorted(versions.glob("*.py")):
        if path.is_symlink():
            raise SchemaReleaseError("symlinked migration")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        revision = _literal_assignment(tree, "revision")
        parent = _literal_assignment(tree, "down_revision")
        if not isinstance(revision, str) or not REVISION.fullmatch(revision):
            raise SchemaReleaseError("invalid revision")
        if parent is not None and (not isinstance(parent, str) or not REVISION.fullmatch(parent)):
            raise SchemaReleaseError("branch or invalid down_revision")
        if revision in entries:
            raise SchemaReleaseError("duplicate revision")
        entries[revision] = {"revision": revision, "down_revision": parent,
                             "file": path.name, "sha256": digest(path),
                             **classify_upgrade(tree)}
    if not entries:
        raise SchemaReleaseError("no migrations")
    roots = [entry for entry in entries.values() if entry["down_revision"] is None]
    parents = [entry["down_revision"] for entry in entries.values() if entry["down_revision"]]
    heads = set(entries) - set(parents)
    if len(roots) != 1 or len(heads) != 1 or any(parent not in entries for parent in parents):
        raise SchemaReleaseError("chain is not single-root single-head with no gaps")
    ordered = []
    current = next(iter(heads))
    while current is not None:
        if current in ordered:
            raise SchemaReleaseError("cycle in migration chain")
        ordered.append(current)
        current = entries[current]["down_revision"]
    if len(ordered) != len(entries):
        raise SchemaReleaseError("disconnected migration chain")
    return [entries[revision] for revision in reversed(ordered)]


def sqlite_state(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        return "unknown"
    uri = f"file:{path}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "alembic_version" not in tables:
            return "unversioned" if tables else "empty"
        rows = connection.execute("SELECT version_num FROM alembic_version").fetchall()
        if len(rows) != 1 or not isinstance(rows[0][0], str):
            return "unknown"
        return rows[0][0]


def draft_manifest(versions: Path, *, baseline: str) -> dict:
    ordered = inventory(versions)
    if baseline not in [entry["revision"] for entry in ordered]:
        raise SchemaReleaseError("baseline not in chain")
    return {"version": 1, "baseline_source_commit": "834fb22d71ad2d83b212a5ad5ef1e7ef9b485907",
            "expected_before_states": [baseline], "target_head": ordered[-1]["revision"],
            "revisions": ordered, "review": {"status": "draft", "owner": "",
                                        "rehearsal_evidence_sha256": "",
                                        "data_backup_sha256": ""}}


def verify_manifest(manifest: dict, versions: Path, *, exact_manifest_sha256: str,
                    source_state: str, actual_state: str, rehearsal_sha256: str,
                    backup_sha256: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", exact_manifest_sha256):
        raise SchemaReleaseError("exact manifest hash required")
    # The manifest hash comes from an independently protected release approval.
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    if hashlib.sha256(raw).hexdigest() != exact_manifest_sha256:
        raise SchemaReleaseError("manifest hash mismatch")
    if manifest.get("version") != 1 or manifest.get("revisions") != inventory(versions):
        raise SchemaReleaseError("migration inventory/hash mismatch")
    revisions = [entry["revision"] for entry in manifest["revisions"]]
    if manifest.get("target_head") != revisions[-1]:
        raise SchemaReleaseError("target head mismatch")
    if (source_state not in manifest.get("expected_before_states", [])
            or source_state not in revisions or source_state != actual_state):
        raise SchemaReleaseError("unknown or mismatched source revision")
    if any(entry["classification"] != "expand_review" for entry in manifest["revisions"]
           if revisions.index(entry["revision"]) > revisions.index(source_state)):
        raise SchemaReleaseError("manual/destructive migration requires separate phase")
    review = manifest.get("review", {})
    if review.get("status") != "approved" or not review.get("owner"):
        raise SchemaReleaseError("owner review missing")
    for value, expected in ((review.get("rehearsal_evidence_sha256"), rehearsal_sha256),
                            (review.get("data_backup_sha256"), backup_sha256)):
        if not re.fullmatch(r"[0-9a-f]{64}", expected or "") or value != expected:
            raise SchemaReleaseError("rehearsal or data backup evidence mismatch")
