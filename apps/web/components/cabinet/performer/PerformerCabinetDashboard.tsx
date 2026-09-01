"use client";

import Link from "next/link";
import { CabinetPageShell } from "../CabinetPageShell";
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
    <CabinetPageShell
      mode="performer"
      kindKey="artist"
      ready={ready}
      error={error}
      email={email}
      orgName={orgName}
      empty={empty}
      emptyState={
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
      }
      footer={orgId ? <SupplyCabinetSection orgId={orgId} role={role} /> : null}
    >
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
    </CabinetPageShell>
  );
}
