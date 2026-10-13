import Link from "next/link";
import { LEGAL_DOCS } from "@/lib/legal";
import { getPublicLegalPack } from "@/lib/legalPack";

export const metadata = { title: "Правовые документы", alternates: { canonical: "/legal" } };
export const dynamic = "force-dynamic";

export default async function LegalIndexPage() {
  const pack = await getPublicLegalPack();
  return (
    <main className="page-enter">
      <p className="kicker">Правила сервиса</p>
      <h1>Правовые документы</h1>
      <div className="legal-banner" role="status">
        <strong>{pack?.status === "published" ? "Серверный пакет опубликован." : "Черновик."}</strong>{" "}
        {pack?.pack_version ? `Редакция ${pack.pack_version}. ` : "Серверная редакция не подтверждена. "}
        {pack?.status === "draft"
          ? "Документы проходят юридическую проверку; тестовое ознакомление не является юридическим акцептом."
          : pack?.status === "published"
            ? "Статус каждого показанного текста проверяйте на его странице."
            : "Доступность регистрации пока не подтверждена."}
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
      <p className="timeline">Доступность регистрации определяется серверным статусом пакета. Согласие на рассылки всегда отдельно и необязательно.</p>
    </main>
  );
}
