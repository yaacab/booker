"use client";

import Link from "next/link";
import { setToken } from "@/lib/api";
import { cabinetTitle, cabinetHeadline } from "@/lib/cabinetRoutes";
import { KIND_LABEL } from "@/lib/copy";
import { loginHref } from "@/lib/next";
import { useCustomerCabinetData } from "./useCustomerCabinetData";
import { DraftsWidget } from "./widgets/DraftsWidget";
import { ExpiringHoldsWidget } from "./widgets/ExpiringHoldsWidget";
import { NewOffersWidget } from "./widgets/NewOffersWidget";
import { UpcomingEventsWidget } from "./widgets/UpcomingEventsWidget";

export function CustomerCabinetDashboard() {
  const {
    ready,
    error,
    email,
    orgName,
    upcomingEvents,
    drafts,
    newOffers,
    expiringHolds,
    empty,
  } = useCustomerCabinetData();

  return (
    <main className="customer-cabinet">
      <p className="kicker">{cabinetTitle("customer")} · {KIND_LABEL.customer || "Букер"}</p>
      <h1>{cabinetHeadline("customer")}</h1>
      {email ? <p className="timeline">{email}{orgName ? ` · ${orgName}` : ""}</p> : null}
      {!ready ? <div className="skeleton" /> : null}
      {error ? (
        <p>
          {error}. <Link href={loginHref("/cabinet/customer")}>Войти</Link>
        </p>
      ) : null}
      {empty ? (
        <article className="card empty">
          <h2>У вас пока нет заявок</h2>
          <p>Создайте первую заявку или найдите свободный слот в каталоге. Черновик можно заполнить за несколько минут.</p>
          <p className="timeline">Условия и итоговая сумма появятся в Deal Room после серверного предложения.</p>
          <p style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Link className="btn" href="/events/new">
              Создать заявку
            </Link>
            <Link className="btn secondary" href="/search">
              Открыть каталог
            </Link>
          </p>
        </article>
      ) : (
        <div className="dashboard-grid">
          <UpcomingEventsWidget events={upcomingEvents} />
          <DraftsWidget drafts={drafts} />
          <NewOffersWidget offers={newOffers} />
          <ExpiringHoldsWidget holds={expiringHolds} />
        </div>
      )}
      <p style={{ marginTop: 24 }}>
        <button
          type="button"
          className="secondary"
          onClick={() => {
            setToken(null);
            localStorage.removeItem("booker.admin");
            window.location.href = "/login";
          }}
        >
          Выйти
        </button>
      </p>
    </main>
  );
}
