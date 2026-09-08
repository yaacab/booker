import Link from "next/link";
import { ReferencePuzzleStrip } from "@/components/ReferencePuzzleStrip";
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

function BlockView({ block, id }: { block: Block; id?: string }) {
  if (block.t === "h") {
    if (block.level === 1) return <h1 id={id}>{block.text}</h1>;
    if (block.level === 2) return <h2 id={id}>{block.text}</h2>;
    return <h3 id={id}>{block.text}</h3>;
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
  const titleIndex = blocks.findIndex(block => block.t === "h" && block.level === 1);
  const title = blocks[titleIndex];
  return (
    <main className="page-enter legal-doc">
      <p className="timeline">
        <Link href="/legal">Правовые документы</Link>
      </p>
      <header className="legal-document-heading">
        {title && <BlockView block={title} id={`section-${titleIndex}`} />}
        <p>Правила и договорённости, к которым можно вернуться в любой момент.</p>
      </header>
      <div className="legal-document-art"><ReferencePuzzleStrip /></div>
      <div className="legal-banner">
        Редакция {LEGAL_PACK_VERSION}. До завершения юридической проверки документ считается черновиком и не является действующей офертой или консультацией.
        Платежи в пилотной версии отключены. Реквизиты оператора будут заполнены после юридической проверки.
        Все документы: <Link href="/legal">в общем разделе</Link>.
      </div>
      <div className="document-layout">
        <nav className="document-toc" aria-label="Содержание документа"><strong>В этом документе</strong>
          {blocks.map((block,i) => block.t === "h" && block.level === 2 ? <a key={i} href={`#section-${i}`}>{block.text}</a> : null)}
        </nav>
        <article className="document-body">{blocks.map((block, i) => (
          i === titleIndex ? null : <BlockView key={i} block={block} id={`section-${i}`} />
        ))}</article>
      </div>
    </main>
  );
}
