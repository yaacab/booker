import Link from "next/link";
import { LEGAL_PACK_VERSION, parseLegalMarkdown, splitInline, type Block } from "@/lib/legal";

function Inline({ text }: { text: string }) {
  return (
    <>
      {splitInline(text).map((part, idx) =>
        typeof part === "string" ? <span key={idx}>{part}</span> : <strong key={idx}>{part.b}</strong>
      )}
    </>
  );
}

function BlockView({ block }: { block: Block }) {
  if (block.t === "h") {
    if (block.level === 1) return <h1>{block.text}</h1>;
    if (block.level === 2) return <h2>{block.text}</h2>;
    return <h3>{block.text}</h3>;
  }
  if (block.t === "ul") {
    return (
      <ul>
        {block.items.map((item) => (
          <li key={item}>
            <Inline text={item} />
          </li>
        ))}
      </ul>
    );
  }
  if (block.t === "table") {
    return (
      <div className="legal-table-wrap">
        <table className="legal-table">
          <thead>
            <tr>
              {block.head.map((c) => (
                <th key={c}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {block.rows.map((row, ri) => (
              <tr key={ri}>
                {row.map((c, ci) => (
                  <td key={ci}>
                    <Inline text={c} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  return (
    <p>
      <Inline text={block.text} />
    </p>
  );
}

export function LegalDoc({ source }: { source: string }) {
  const blocks = parseLegalMarkdown(source);
  return (
    <main className="page-enter legal-doc">
      <p className="timeline">
        <Link href="/legal">Бумажки</Link>
      </p>
      <div className="legal-banner">
        Редакция {LEGAL_PACK_VERSION}. Пока юрист не кивнул — это черновик, не действующая оферта и не консультация.
        Живые платежи спим. Реквизиты оператора ещё пустые.
        Весь пакет: <Link href="/legal">сюда</Link>.
      </div>
      {blocks.map((block, i) => (
        <BlockView key={i} block={block} />
      ))}
    </main>
  );
}
