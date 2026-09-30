"use client";

import { useState } from "react";
import { CabinetPageShell } from "../CabinetPageShell";
import { SupplyCabinetSection } from "../SupplyCabinetSection";
import { AwaitingResponseWidget } from "../performer/widgets/AwaitingResponseWidget";
import { CalendarConflictsWidget } from "../performer/widgets/CalendarConflictsWidget";
import { ExpiringOffersWidget } from "../performer/widgets/ExpiringOffersWidget";
import { HoldsWidget } from "../performer/widgets/HoldsWidget";
import { NewRequestsWidget } from "../performer/widgets/NewRequestsWidget";
import { OpenSlotsWidget } from "../performer/widgets/OpenSlotsWidget";
import { ProfileCompletenessWidget } from "../performer/widgets/ProfileCompletenessWidget";
import { UpcomingPerformancesWidget } from "../performer/widgets/UpcomingPerformancesWidget";
import { useVenueCabinetData } from "./useVenueCabinetData";
import { VenueHallsPanel } from "./widgets/VenueHallsPanel";
import { VenueHallsWidget } from "./widgets/VenueHallsWidget";
import { VenueOnboardingWidget } from "./widgets/VenueOnboardingWidget";
import { VenueStatsWidget } from "./widgets/VenueStatsWidget";
import { VenueMonthCalendar } from "./widgets/VenueMonthCalendar";
import { RequestsInboxWidget } from "../performer/widgets/RequestsInboxWidget";

export type VenueCabinetSection = "home" | "calendar" | "requests" | "halls" | "stats";
const SECTION_COPY = {
  home: ["Кабинет площадки", "Управляйте залами, заявками и событиями. Больше людей на ваших местах."],
  calendar: ["Календарь площадки", "Планируйте загрузку залов, управляйте бронированиями и доступностью."],
  requests: ["Заявки площадке", "Входящие запросы на ваши залы. Обсуждайте детали и подтверждайте события."],
  halls: ["Залы площадки", "У каждого пространства — свой календарь, вместимость и условия."],
  stats: ["Статистика площадки", "Заявки, подтверждённые бронирования и ближайшие события."],
} as const;

export function VenueCabinetDashboard({ section = "home" }: { section?: VenueCabinetSection }) {
  const { ready, error, email, orgName, orgId, role, newRequests, awaitingResponse, expiringOffers, activeHolds, upcomingEvents, calendarConflicts, profileIncomplete, profileCompleteness, halls, venueId, bookingStats, requestCount, requests, offerBusy, sendOffer, reload } = useVenueCabinetData();
  const [calendarRevision, setCalendarRevision] = useState(0);
  const realHalls = halls.filter(hall => hall.resource_type === "hall");
  const [title, subtitle] = SECTION_COPY[section];
  const calendarSetup = orgId ? <details className="workspace-disclosure" id="calendar-manage"><summary>Открыть свободные даты <span aria-hidden="true">＋</span></summary><OpenSlotsWidget orgId={orgId} role={role} orgName={orgName} supplyKind="venue" onChanged={() => { setCalendarRevision(value => value + 1); void reload(); }} /></details> : null;

  return <CabinetPageShell mode="venue" section={section} title={title} subtitle={subtitle} ready={ready} error={error} email={email} orgName={orgName} empty={false} emptyState={null}
    actions={section === "calendar" ? [{ href: "#calendar-manage", label: "Открыть свободные даты", primary: true }] : section === "requests" ? [{ href: "/cabinet/venue/calendar", label: "Открыть календарь" }] : [{ href: "/cabinet/venue/halls", label: "Управлять залами", primary: true }, { href: "/cabinet/venue/calendar", label: "Открыть календарь" }]}
    metrics={section === "home" ? [
      { label: "Новые заявки", value: newRequests.length, hint: "требуют ответа" },
      { label: "Активные удержания", value: activeHolds.length, hint: "даты закреплены за заказчиком" },
      { label: "Предстоящие события", value: upcomingEvents.length, hint: "подтверждённые и активные" },
      { label: "Залы", value: realHalls.length, hint: "ваши пространства" },
    ] : section === "stats" ? [
      { label: "Бронирования", value: bookingStats.total }, { label: "Подтверждено", value: bookingStats.confirmed }, { label: "Ближайшие события", value: bookingStats.upcoming }, { label: "Заявки", value: requestCount },
    ] : undefined}
    lead={section === "calendar" ? <>{venueId ? <VenueMonthCalendar key={calendarRevision} venueId={venueId} hallNames={realHalls.map(hall => hall.label)} /> : <div className="workspace-soft-empty"><h2>Ваш календарь начинается с площадки</h2><p>Создайте площадку и добавьте залы, чтобы открыть свободные даты.</p></div>}{calendarSetup}</>
      : section === "requests" ? <RequestsInboxWidget requests={requests} role={role} offerBusy={offerBusy} onSendOffer={item => void sendOffer(item)} />
        : section === "halls" ? venueId ? <VenueHallsPanel venueId={venueId} venueName={orgName} role={role} /> : <div className="workspace-soft-empty"><h2>Сначала создайте площадку</h2><p>После этого вы сможете добавить залы и открыть свободные даты.</p>{calendarSetup}</div>
          : section === "stats" ? <VenueStatsWidget stats={bookingStats} requestCount={requestCount} />
            : <div className="workspace-overview-grid"><UpcomingPerformancesWidget bookings={upcomingEvents} title="Ближайшие события" />{profileCompleteness ? <ProfileCompletenessWidget completeness={profileCompleteness} /> : <VenueOnboardingWidget hasHalls={realHalls.length > 0} profileComplete={!profileIncomplete} hasRequests={newRequests.length + awaitingResponse.length > 0} />}</div>}
    footer={orgId ? <details className="workspace-disclosure workspace-settings" id="supply-settings"><summary>Настройки площадки, календаря и услуг <span aria-hidden="true">＋</span></summary><SupplyCabinetSection orgId={orgId} role={role} /></details> : null}
  >
    {section === "home" ? <div className="cabinet-zone-grid workspace-secondary-grid"><NewRequestsWidget requests={newRequests} role={role} offerBusy={offerBusy} onSendOffer={item => void sendOffer(item)} /><VenueHallsWidget halls={halls} role={role} onChanged={() => void reload()} /></div> : null}
    {(section === "home" || section === "requests") && (awaitingResponse.length > 0 || activeHolds.length > 0 || expiringOffers.length > 0) ? <div className="cabinet-zone-grid workspace-secondary-grid">
      {awaitingResponse.length > 0 ? <AwaitingResponseWidget deals={awaitingResponse} /> : null}{activeHolds.length > 0 ? <HoldsWidget holds={activeHolds} /> : null}{expiringOffers.length > 0 ? <ExpiringOffersWidget deals={expiringOffers} /> : null}
    </div> : null}
    {(section === "home" || section === "calendar") && calendarConflicts.length > 0 ? <CalendarConflictsWidget conflicts={calendarConflicts} /> : null}
    {section === "home" ? calendarSetup : null}
  </CabinetPageShell>;
}
