import Link from "next/link";

export const metadata = { title: "Нет такой страницы" };

export default function NotFound() {
  return (
    <main className="reference-empty">
      <p className="kicker">Ошибка 404</p>
      <h1>Страница не найдена</h1>
      <p className="timeline">Проверьте адрес или продолжите подбор команды в каталоге.</p>
      <p>
        <Link className="btn" href="/">
          На главную
        </Link>
        {" "}
        <Link className="btn secondary" href="/search">
          Открыть каталог
        </Link>
        {" "}
        <Link className="btn secondary" href="/events/new">
          Создать заявку
        </Link>
      </p>
    </main>
  );
}
