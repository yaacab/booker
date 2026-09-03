"use client";

import { CabinetPageShell } from "../CabinetPageShell";
import { SupplyCabinetSection } from "../SupplyCabinetSection";
import { usePerformerCabinetData } from "./usePerformerCabinetData";
import { AwaitingResponseWidget } from "./widgets/AwaitingResponseWidget";
import { CalendarConflictsWidget } from "./widgets/CalendarConflictsWidget";
import { ExpiringOffersWidget } from "./widgets/ExpiringOffersWidget";
import { HoldsWidget } from "./widgets/HoldsWidget";
import { NewRequestsWidget } from "./widgets/NewRequestsWidget";
import { OpenSlotsWidget } from "./widgets/OpenSlotsWidget";
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
    offerBusy,
    sendOffer,
  } = usePerformerCabinetData();

  const completenessScore = profileIncomplete?.score;

  return (
    <CabinetPageShell
      mode="performer"
      kindKey="artist"
      ready={ready}
      error={error}
      email={email}
      orgName={orgName}
      empty={false}
      emptyState={null}
      subtitle="Календарь, гонорар и ответы на запросы. Вы не собираете события — вас бронируют."
      metrics={[
        { label: "Новые запросы", value: newRequests.length, tone: newRequests.length ? "wait" : "default" },
        { label: "Ждут заказчика", value: awaitingResponse.length, tone: awaitingResponse.length ? "live" : "default" },
        { label: "Ближайшие даты", value: upcomingPerformances.length, tone: "ok" },
        {
          label: "Профиль",
          value: completenessScore != null ? `${completenessScore}%` : "—",
          tone: completenessScore != null && completenessScore >= 80 ? "ok" : "wait",
        },
      ]}
      actions={[{ href: "#cabinet-widgets", label: "К заявкам", primary: true }]}
      lead={orgId ? <OpenSlotsWidget orgId={orgId} role={role} orgName={orgName} supplyKind="artist" /> : null}
      footer={orgId ? <SupplyCabinetSection orgId={orgId} role={role} /> : null}
    >
      <section className="cabinet-zone" aria-label="Входящие">
        <h2 className="cabinet-zone-title">Входящие</h2>
        <div className="cabinet-zone-grid">
          <NewRequestsWidget
            requests={newRequests}
            role={role}
            offerBusy={offerBusy}
            onSendOffer={(item) => void sendOffer(item)}
          />
          <AwaitingResponseWidget deals={awaitingResponse} />
          <ExpiringOffersWidget deals={expiringOffers} />
          <HoldsWidget holds={activeHolds} />
        </div>
      </section>

      <section className="cabinet-zone" aria-label="Расписание">
        <h2 className="cabinet-zone-title">Расписание</h2>
        <div className="cabinet-zone-grid">
          <UpcomingPerformancesWidget bookings={upcomingPerformances} />
          <CalendarConflictsWidget conflicts={calendarConflicts} />
          {profileIncomplete ? <ProfileCompletenessWidget completeness={profileIncomplete} /> : null}
        </div>
      </section>
    </CabinetPageShell>
  );
}
