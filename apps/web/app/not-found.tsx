import Link from "next/link";

export const metadata = { title: "Нет такой страницы" };

export default function NotFound() {
  return (
    <main>
      <p className="kicker">404. Даже слот свободнее.</p>
      <h1>Этой страницы нет. И не было.</h1>
      <p className="timeline">Либо опечатка, либо кто-то слишком творчески набрал адрес.</p>
      <p>
        <Link className="btn" href="/">
          Унести ноги на главную
        </Link>
        {" "}
        <Link className="btn secondary" href="/search">
          Кто ещё не занят
        </Link>
        {" "}
        <Link className="btn secondary" href="/events/new">
          Создать заявку
        </Link>
      </p>
    </main>
  );
}
