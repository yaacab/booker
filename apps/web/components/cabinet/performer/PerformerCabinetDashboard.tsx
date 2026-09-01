"use client";

import Link from "next/link";
import { setToken } from "@/lib/api";
import { cabinetHeadline, cabinetTitle } from "@/lib/cabinetRoutes";
import { KIND_LABEL } from "@/lib/copy";
import { loginHref } from "@/lib/next";
import { SupplyCabinetSection } from "../SupplyCabinetSection";
import { usePerformerCabinetData } from "./usePerformerCabinetData";
import { AwaitingResponseWidget } from "./widgets/AwaitingResponseWidget";
import { CalendarConflictsWidget } from "./widgets/CalendarConflictsWidget";
import { ExpiringOffersWidget } from "./widgets/ExpiringOffersWidget";
import { HoldsWidget } from "./widgets/HoldsWidget";
import { NewRequestsWidget } from "./widgets/NewRequestsWidget";
import { ProfileCompletenessWidget } from "./widgets/ProfileCompletenessWidget";
import { UpcomingPerformancesWidget } from "./widgets/UpcomingPerformancesWidget";

export function PerformerCabinetDashboard() {
  const {
    ready,
    error,
    email,
    orgName,
    orgId,
    role,
    newRequests,
    awaitingResponse,
    expiringOffers,
    activeHolds,
    upcomingPerformances,
    calendarConflicts,
    profileIncomplete,
    empty,
    offerBusy,
    sendOffer,
  } = usePerformerCabinetData();

  return (
    <main className="performer-cabinet">
      <p className="kicker">{cabinetTitle("performer")} · {KIND_LABEL.artist || "Букер"}</p>
      <h1>{cabinetHeadline("performer")}</h1>
      {email ? <p className="timeline">{email}{orgName ? ` · ${orgName}` : ""}</p> : null}
      {!ready ? <div className="skeleton" /> : null}
      {error ? (
        <p>
          {error}. <Link href={loginHref("/cabinet/performer")}>Войти</Link>
        </p>
      ) : null}
      {empty ? (
        <article className="card empty">
          <h2>Пока нет входящих заявок</h2>
          <p>Когда заказчик отправит запрос на ваш слот, он появится здесь.</p>
          <p className="timeline">Условия и итоговая сумма появятся в Deal Room после серверного предложения.</p>
          <p style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Link className="btn secondary" href="/search">
              Открыть каталог
            </Link>
          </p>
        </article>
      ) : (
        <div className="dashboard-grid">
          <NewRequestsWidget
            requests={newRequests}
            role={role}
            offerBusy={offerBusy}
            onSendOffer={(item) => void sendOffer(item)}
          />
          <AwaitingResponseWidget deals={awaitingResponse} />
          <ExpiringOffersWidget deals={expiringOffers} />
          <HoldsWidget holds={activeHolds} />
          <UpcomingPerformancesWidget bookings={upcomingPerformances} />
          <CalendarConflictsWidget conflicts={calendarConflicts} />
          {profileIncomplete ? <ProfileCompletenessWidget completeness={profileIncomplete} /> : null}
        </div>
      )}
      {orgId ? <SupplyCabinetSection orgId={orgId} role={role} /> : null}
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
