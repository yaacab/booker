import { readFile } from "node:fs/promises";
import path from "node:path";

export const LEGAL_PACK_VERSION = "2026-08-18-draft";

export const LEGAL_DOCS = [
  { href: "/legal/offer", file: "OFFER_DRAFT.md", title: "Оферта цифровых услуг" },
  { href: "/legal/privacy", file: "PRIVACY_DRAFT.md", title: "Персональные данные" },
  { href: "/legal/cookies", file: "COOKIES_DRAFT.md", title: "Cookie-файлы" },
  { href: "/legal/disputes", file: "DISPUTES_REFUNDS_DRAFT.md", title: "Споры и возвраты" },
  { href: "/legal/suppliers", file: "SUPPLIER_TERMS_DRAFT.md", title: "Исполнители и площадки" },
] as const;

export async function readLegalFile(file: string): Promise<string> {
  const roots = [path.join(process.cwd(), "../../docs/legal"), path.join(process.cwd(), "docs/legal")];
  let last = "";
  for (const root of roots) {
    const full = path.join(root, file);
    try {
      return await readFile(full, "utf8");
    } catch (err) {
      last = err instanceof Error ? err.message : String(err);
    }
  }
  throw new Error(`Не найден ${file}: ${last}`);
}

export function splitInline(text: string): (string | { b: string })[] {
  const out: (string | { b: string })[] = [];
  const re = /\*\*(.+?)\*\*/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    out.push({ b: m[1] });
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export type Block =
  | { t: "h"; level: number; text: string }
  | { t: "p"; text: string }
  | { t: "ul"; items: string[] }
  | { t: "table"; head: string[]; rows: string[][] };

export function parseLegalMarkdown(src: string): Block[] {
  const lines = src.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i += 1;
      continue;
    }
    const heading = /^(#{1,3})\s+(.*)$/.exec(line);
    if (heading) {
      blocks.push({ t: "h", level: heading[1].length, text: heading[2] });
      i += 1;
      continue;
    }
    if (line.trim().startsWith("|")) {
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        const cells = lines[i]
          .split("|")
          .slice(1, -1)
          .map((c) => c.trim());
        if (!cells.every((c) => /^[-:]+$/.test(c))) rows.push(cells);
        i += 1;
      }
      if (rows.length) blocks.push({ t: "table", head: rows[0], rows: rows.slice(1) });
      continue;
    }
    if (line.trim().startsWith("- ")) {
      const items: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith("- ")) {
        items.push(lines[i].trim().slice(2));
        i += 1;
      }
      blocks.push({ t: "ul", items });
      continue;
    }
    const para: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() &&
      !lines[i].startsWith("#") &&
      !lines[i].trim().startsWith("|") &&
      !lines[i].trim().startsWith("- ")
    ) {
      para.push(lines[i]);
      i += 1;
    }
    blocks.push({ t: "p", text: para.join(" ") });
  }
  return blocks;
}
