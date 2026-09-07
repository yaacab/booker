import Link from "next/link";
import { LEGAL_DOCS, LEGAL_PACK_VERSION } from "@/lib/legal";

export const metadata = { title: "Правовые документы", alternates: { canonical: "/legal" } };

export default function LegalIndexPage() {
  return (
    <main className="page-enter">
      <p className="kicker">Правила сервиса</p>
      <h1>Правовые документы</h1>
      <div className="legal-banner">
        Редакция {LEGAL_PACK_VERSION}. Документы проходят юридическую проверку. Платежи в пилотной версии отключены.
      </div>
      <ul className="legal-index">
        {LEGAL_DOCS.map((doc) => (
          <li key={doc.href}>
            <Link href={doc.href}>{doc.title}</Link>
          </li>
        ))}
        <li>
          <Link href="/legal/cancellation">Шаблон отмен</Link>
        </li>
      </ul>
      <p className="timeline">
        При регистрации необходимо принять условия сервиса и обработки персональных данных. Согласие на рассылки — отдельно и по желанию.
      </p>
    </main>
  );
}
