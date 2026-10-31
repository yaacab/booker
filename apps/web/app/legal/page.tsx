import Link from "next/link";
import { LEGAL_DOCS, LEGAL_PACK_VERSION } from "@/lib/legal";
import { ReferencePuzzleStrip } from "@/components/ReferencePuzzleStrip";

export const metadata = { title: "Правовые документы", alternates: { canonical: "/legal" } };

export default function LegalIndexPage() {
  const descriptions: Record<string, string> = {
    "/legal/offer": "Условия использования цифровых услуг Букера.",
    "/legal/privacy": "Какие данные мы обрабатываем и как с ними работаем.",
    "/legal/cookies": "Использование cookie-файлов на сайте.",
    "/legal/disputes": "Порядок работы с обращениями, спорами и возвратами.",
    "/legal/suppliers": "Условия сотрудничества для артистов и площадок.",
  };
  return (
    <main className="page-enter reference-information legal-reference">
      <header className="information-heading"><p className="kicker">Правила сервиса</p>
      <h1>Документы</h1><h2>Понятные правила<br />для совместной работы.</h2><p>Здесь собраны условия сервиса и документы о том, как Букер работает с договорённостями и данными.</p></header>
      <ReferencePuzzleStrip />
      <div className="legal-banner">
        Редакция {LEGAL_PACK_VERSION}. Документы проходят юридическую проверку. Платежи в пилотной версии отключены.
      </div>
      <ul className="legal-index">
        {LEGAL_DOCS.map((doc) => (
          <li key={doc.href}>
            <Link href={doc.href}><span className="document-icon" aria-hidden="true">≡</span><span><strong>{doc.title}</strong><small>{descriptions[doc.href]}</small></span><span aria-hidden="true">↗</span></Link>
          </li>
        ))}
        <li>
          <Link href="/legal/cancellation"><span className="document-icon" aria-hidden="true">≡</span><span><strong>Отмены и переносы</strong><small>Шаблон условий отмены события.</small></span><span aria-hidden="true">↗</span></Link>
        </li>
      </ul>
      <p className="timeline">
        При регистрации необходимо принять условия сервиса и обработки персональных данных. Согласие на рассылки — отдельно и по желанию.
      </p>
      <aside className="information-help"><p>Есть вопрос по документам?<br />Напишите нам — поможем разобраться.</p><Link className="btn" href="/support">Написать в поддержку →</Link></aside>
    </main>
  );
}
