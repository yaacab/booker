"use client";

import { useState } from "react";
import { isWriteRole } from "@/lib/api";
import { CabinetPageShell } from "../CabinetPageShell";
import { SupplyCabinetSection } from "../SupplyCabinetSection";
import { ArtistOpportunities } from "../PlanningPriorities";
import { usePerformerCabinetData } from "./usePerformerCabinetData";
import { AwaitingResponseWidget } from "./widgets/AwaitingResponseWidget";
import { CalendarConflictsWidget } from "./widgets/CalendarConflictsWidget";
import { CalendarOverviewWidget } from "./widgets/CalendarOverviewWidget";
import { ExpiringOffersWidget } from "./widgets/ExpiringOffersWidget";
import { HoldsWidget } from "./widgets/HoldsWidget";
import { NewRequestsWidget } from "./widgets/NewRequestsWidget";
import { OpenSlotsWidget } from "./widgets/OpenSlotsWidget";
import { PerformerOnboardingWidget } from "./widgets/PerformerOnboardingWidget";
import { PortfolioRiderWidget } from "./widgets/PortfolioRiderWidget";
import { ProfileCompletenessWidget } from "./widgets/ProfileCompletenessWidget";
import { RequestsInboxWidget } from "./widgets/RequestsInboxWidget";
import { ServicesWidget } from "./widgets/ServicesWidget";
import { UpcomingPerformancesWidget } from "./widgets/UpcomingPerformancesWidget";

export type PerformerCabinetSection = "home" | "calendar" | "requests" | "services";

const SECTION_COPY = {
  home: ["Кабинет артиста", "Новые возможности. Больше событий. Твоя аудитория."],
  calendar: ["Календарь артиста", "Управляйте доступностью, чтобы получать больше подходящих заявок."],
  requests: ["Заявки артисту", "Новые запросы от клиентов. Отвечайте, создавайте предложения, получайте события."],
  services: ["Услуги артиста", "Создавайте услуги. Покажите, что входит в выступление, — и упростите бронирование."],
} as const;

export function PerformerCabinetDashboard({ section = "home" }: { section?: PerformerCabinetSection }) {
  const {
    ready, error, email, orgName, orgId, role, artistId, requests, bookings,
    newRequests, awaitingResponse, negotiations, expiringOffers, activeHolds, upcomingPerformances,
    calendarConflicts, profileIncomplete, profileCompleteness, offerBusy, sendOffer, reload,
  } = usePerformerCabinetData();
  const [calendarRevision, setCalendarRevision] = useState(0);
  const completenessScore = profileCompleteness?.score;
  const [title, subtitle] = SECTION_COPY[section];
  const actions = section === "calendar"
    ? [{ href: "#calendar-manage", label: "Открыть свободные даты", primary: true }]
    : section === "requests"
      ? [{ href: "/cabinet/performer/calendar", label: "Открыть календарь" }]
      : section === "services"
        ? isWriteRole(role) ? [{ href: "#performer-service-form", label: "Добавить услугу", primary: true }] : []
        : [{ href: "/briefs", label: "Найти работу", primary: true }, { href: artistId ? `/artists/${artistId}` : "/cabinet/performer/services", label: "Смотреть профиль" }];

  return <CabinetPageShell
    mode="performer" kindKey="artist" section={section} title={title} subtitle={subtitle}
    ready={ready} error={error} email={email} orgName={orgName} empty={false} emptyState={null}
    actions={actions}
    metrics={section === "home" ? [
      { label: "Новые заявки", value: newRequests.length, hint: "требуют ответа", tone: newRequests.length ? "wait" : "default" },
      { label: "Предстоящие выступления", value: upcomingPerformances.length, hint: "подтверждённые и активные", tone: "ok" },
      { label: "Ждут заказчика", value: awaitingResponse.length, hint: "предложения отправлены" },
      { label: "Профиль", value: completenessScore != null ? `${completenessScore}%` : "—", hint: "готовность к бронированию" },
    ] : undefined}
    lead={section === "calendar" && orgId ? <>
      <CalendarOverviewWidget key={calendarRevision} orgId={orgId} artistId={artistId} bookings={bookings} />
      <details className="workspace-disclosure" id="calendar-manage">
        <summary>Открыть свободные даты <span aria-hidden="true">＋</span></summary>
        <OpenSlotsWidget orgId={orgId} role={role} orgName={orgName} supplyKind="artist" onChanged={() => { setCalendarRevision(value => value + 1); void reload(); }} />
      </details>
    </> : section === "requests" ? <RequestsInboxWidget requests={requests} role={role} offerBusy={offerBusy} onSendOffer={item => void sendOffer(item)} />
      : section === "services" && orgId ? <ServicesWidget orgId={orgId} role={role} />
      : section === "home" ? <div className="workspace-overview-grid">
        <NewRequestsWidget requests={newRequests} role={role} offerBusy={offerBusy} onSendOffer={item => void sendOffer(item)} />
        {activeHolds.length ? <HoldsWidget holds={activeHolds} /> : negotiations.length ? <AwaitingResponseWidget deals={negotiations} /> : <UpcomingPerformancesWidget bookings={upcomingPerformances} />}
      </div> : null}
    footer={orgId ? <details className="workspace-disclosure workspace-settings" id="supply-settings">
      <summary>Настройки профиля, календаря и услуг <span aria-hidden="true">＋</span></summary>
      <SupplyCabinetSection orgId={orgId} role={role} />
    </details> : null}
  >
    {section === "home" ? <>
      <ArtistOpportunities artistId={artistId}/>
      <section className="cabinet-zone-grid workspace-secondary-grid" aria-label="Заявки и профиль">
        {activeHolds.length>0||negotiations.length>0?<UpcomingPerformancesWidget bookings={upcomingPerformances} />:null}
        {orgId ? <CalendarOverviewWidget orgId={orgId} artistId={artistId} bookings={bookings} compact /> : null}
        {profileCompleteness ? <ProfileCompletenessWidget completeness={profileCompleteness} /> : <PerformerOnboardingWidget profileComplete={!profileIncomplete} hasOpenSlots={upcomingPerformances.length > 0 || activeHolds.length > 0} hasRequests={newRequests.length + awaitingResponse.length > 0} />}
      </section>
      {orgId ? <details className="workspace-disclosure">
        <summary>Витрина, услуги и свободные даты <span aria-hidden="true">＋</span></summary>
        <div className="cabinet-zone-grid"><PortfolioRiderWidget orgId={orgId} role={role} /><ServicesWidget orgId={orgId} role={role} compact /><OpenSlotsWidget orgId={orgId} role={role} orgName={orgName} supplyKind="artist" /></div>
      </details> : null}
    </> : null}
    {section === "services" && orgId ? <PortfolioRiderWidget orgId={orgId} role={role} /> : null}
    {section === "calendar" && calendarConflicts.length > 0 ? <CalendarConflictsWidget conflicts={calendarConflicts} /> : null}
    {(section === "home" && negotiations.length>0 && activeHolds.length>0 || section === "requests" && (negotiations.length > 0 || expiringOffers.length > 0 || activeHolds.length > 0)) ? <section className="cabinet-zone-grid workspace-secondary-grid" aria-label="Предложения и удержания">
      {negotiations.length > 0 && (section!=="home"||activeHolds.length>0) ? <AwaitingResponseWidget deals={negotiations} /> : null}
      {expiringOffers.length > 0 && section!=="home" ? <ExpiringOffersWidget deals={expiringOffers} /> : null}
      {activeHolds.length > 0 && section!=="home" ? <HoldsWidget holds={activeHolds} /> : null}
    </section> : null}
    {section === "home" && calendarConflicts.length > 0 ? <CalendarConflictsWidget conflicts={calendarConflicts} /> : null}
  </CabinetPageShell>;
}
