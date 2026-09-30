"""Durable event command receipts. Call only after authorization and a scope row lock."""
import hashlib
import json

from fastapi import HTTPException

from booker_api.models import EventCommandReceipt


def command_hash(body: dict) -> str:
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def replay_command(db, scope: str, key: str | None, body: dict) -> dict | None:
    if not key:
        return None
    row = db.get(EventCommandReceipt, (scope, hashlib.sha256(key.encode()).hexdigest()))
    if not row:
        return None
    if row.body_hash != command_hash(body):
        raise HTTPException(409, "Этот ключ отправки уже использован с другими данными")
    return {**json.loads(row.result_json), "reused": True}


def remember_command(db, scope: str, key: str | None, body: dict, result: dict) -> None:
    if key:
        db.add(EventCommandReceipt(scope=scope, key_hash=hashlib.sha256(key.encode()).hexdigest(),
                                   body_hash=command_hash(body), result_json=json.dumps(result, ensure_ascii=False)))
