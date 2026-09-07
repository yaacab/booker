"use client";

import Link from "next/link";
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
import { VenueCabinetSubNav } from "./VenueCabinetSubNav";
import { useVenueCabinetData } from "./useVenueCabinetData";
import { VenueHallsPanel } from "./widgets/VenueHallsPanel";
import { VenueHallsWidget } from "./widgets/VenueHallsWidget";
import { VenueOnboardingWidget } from "./widgets/VenueOnboardingWidget";
import { VenueStatsWidget } from "./widgets/VenueStatsWidget";
import { VenueMonthCalendar } from "./widgets/VenueMonthCalendar";
import { RequestsInboxWidget } from "../performer/widgets/RequestsInboxWidget";

export type VenueCabinetSection = "home" | "calendar" | "requests" | "halls" | "stats";

export function VenueCabinetDashboard({ section = "home" }: { section?: VenueCabinetSection }) {
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
    upcomingEvents,
    calendarConflicts,
    profileIncomplete,
    halls,
    venueId,
    bookingStats,
    requestCount,
    requests,
    empty,
    offerBusy,
    sendOffer,
    reload,
  } = useVenueCabinetData();

  const hallCount = halls.filter((h) => h.resource_type === "hall").length;
  const completenessScore = profileIncomplete?.score;
  const hallsActive = hallCount > 0;
  const slotsActive =
    newRequests.length > 0 || activeHolds.length > 0 || upcomingEvents.length > 0;
  const showRequests = section === "home" || section === "requests";
  const showCalendar = section === "home" || section === "calendar";
  const showSpace = section === "home" || section === "calendar";
  const showHalls = section === "halls";
  const showStats = section === "stats";
  const subtitle =
    section === "calendar"
      ? "Залы, свободные слоты, даты и конфликты календаря."
      : section === "requests"
        ? "Входящие бронирования, предложения и удержания."
        : section === "halls"
          ? "Создание и просмотр залов — каждый зал со своим календарём."
          : section === "stats"
            ? "Сводка по бронированиям площадки — просмотры и воронка позже."
            : "Залы, календарь и ответы на бронирования — рабочий стол площадки.";

  const primaryAction =
    section === "requests"
      ? { href: "/cabinet/venue/calendar", label: "К календарю" }
      : section === "halls"
        ? { href: "/cabinet/venue/calendar", label: "К календарю" }
        : section === "stats"
          ? { href: "/cabinet/venue/requests", label: "К заявкам" }
          : { href: "#cabinet-widgets", label: "К виджетам" };

  const sectionEmpty =
    section === "halls"
      ? ready && !error && !venueId
      : section === "stats"
        ? ready && !error && bookingStats.total === 0 && requestCount === 0
        : empty;

  return (
    <CabinetPageShell
      mode="venue"
      ready={ready}
      error={error}
      email={email}
      orgName={orgName}
      empty={sectionEmpty}
      emptyState={
        section === "halls" ? (
          <article className="card empty">
            <h2>Нет площадки</h2>
            <p>
              Сначала создайте площадку в блоке «Свободные слоты» на{" "}
              <Link href="/cabinet/venue/calendar">календаре</Link>, затем добавьте залы.
            </p>
          </article>
        ) : section === "stats" ? (
          <article className="card empty">
            <h2>Статистика появится позже</h2>
            <p>После первых заявок и бронирований здесь будет сводка по /bookings.</p>
          </article>
        ) : (
          <article className="card empty">
            <h2>Пока тихо</h2>
            <p>Добавьте зал и держите календарь открытым — новые заявки и удержания появятся здесь.</p>
          </article>
        )
      }
      subtitle={subtitle}
      metrics={
        section === "stats"
          ? [
              {
                label: "Бронирования",
                value: bookingStats.total,
                tone: bookingStats.total ? "live" : "default",
                glow: bookingStats.total > 0,
              },
              {
                label: "Подтверждено",
                value: bookingStats.confirmed,
                tone: bookingStats.confirmed ? "ok" : "default",
              },
              {
                label: "Ближайшие",
                value: bookingStats.upcoming,
                tone: bookingStats.upcoming ? "live" : "default",
                glow: bookingStats.upcoming > 0,
              },
              {
                label: "Заявки",
                value: requestCount,
                tone: requestCount ? "wait" : "default",
              },
            ]
          : section === "halls"
            ? [
                {
                  label: "Залы",
                  value: hallCount,
                  tone: hallCount ? "live" : "wait",
                  hint: "ресурсы календаря",
                  glow: hallsActive,
                },
                {
                  label: "Новые заявки",
                  value: newRequests.length,
                  tone: newRequests.length ? "wait" : "default",
                },
                {
                  label: "Удержания",
                  value: activeHolds.length,
                  tone: activeHolds.length ? "wait" : "default",
                },
                {
                  label: "Профиль",
                  value: completenessScore != null ? `${completenessScore}%` : "—",
                  tone: completenessScore != null && completenessScore >= 80 ? "ok" : "wait",
                  hint: "готовность к выдаче",
                },
              ]
            : [
                {
                  label: "Залы",
                  value: hallCount,
                  tone: hallCount ? "live" : "wait",
                  hint: "ресурсы календаря",
                  glow: hallsActive,
                },
                {
                  label: "Новые заявки",
                  value: newRequests.length,
                  tone: newRequests.length ? "wait" : "default",
                  glow: slotsActive && newRequests.length > 0,
                },
                {
                  label: "Удержания",
                  value: activeHolds.length,
                  tone: activeHolds.length ? "wait" : "default",
                  glow: slotsActive && activeHolds.length > 0,
                },
                {
                  label: "Профиль",
                  value: completenessScore != null ? `${completenessScore}%` : "—",
                  tone: completenessScore != null && completenessScore >= 80 ? "ok" : "wait",
                  hint: "готовность к выдаче",
                  glow: hallsActive || slotsActive,
                },
              ]
      }
      actions={[
        { href: primaryAction.href, label: primaryAction.label, primary: true },
        { href: "/cabinet/venue/messages", label: "Сообщения" },
        ...(section !== "halls" ? [{ href: "/cabinet/venue/halls", label: "Залы" }] : []),
        ...(section !== "stats" ? [{ href: "/cabinet/venue/stats", label: "Статистика" }] : []),
      ]}
      lead={
        <>
          <VenueCabinetSubNav />
          {showCalendar && orgId ? (
            <>
            {section === "calendar" && venueId ? <VenueMonthCalendar venueId={venueId} /> : null}
            <OpenSlotsWidget orgId={orgId} role={role} orgName={orgName} supplyKind="venue" />
            </>
          ) : null}
        </>
      }
      footer={orgId ? <SupplyCabinetSection orgId={orgId} role={role} /> : null}
    >
      {showHalls ? (
        <section className="cabinet-zone" aria-label="Управление залами">
          <h2 className="cabinet-zone-title">Залы</h2>
          <div className="cabinet-zone-grid">
            <VenueHallsPanel venueId={venueId} venueName={orgName} role={role} />
          </div>
        </section>
      ) : null}

      {showStats ? (
        <section className="cabinet-zone" aria-label="Статистика">
          <h2 className="cabinet-zone-title">Статистика</h2>
          <div className="cabinet-zone-grid">
            <VenueStatsWidget stats={bookingStats} requestCount={requestCount} />
          </div>
        </section>
      ) : null}

      {showSpace ? (
        <section className="cabinet-zone" aria-label="Пространство">
          <h2 className="cabinet-zone-title">Пространство</h2>
          <div className="cabinet-zone-grid">
            <VenueOnboardingWidget
              hasHalls={hallCount > 0}
              profileComplete={!profileIncomplete}
              hasRequests={newRequests.length + awaitingResponse.length > 0}
            />
            <VenueHallsWidget halls={halls} role={role} onChanged={() => void reload()} />
            {profileIncomplete ? <ProfileCompletenessWidget completeness={profileIncomplete} /> : null}
          </div>
        </section>
      ) : null}

      {showRequests ? (
        <section className="cabinet-zone" aria-label="Заявки и сделки">
          <h2 className="cabinet-zone-title">Заявки и сделки</h2>
          <div className="cabinet-zone-grid">
            {section === "requests" ? <RequestsInboxWidget requests={requests} role={role} offerBusy={offerBusy} onSendOffer={item => void sendOffer(item)} /> : null}
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
      ) : null}

      {showCalendar ? (
        <section className="cabinet-zone" aria-label="Расписание">
          <h2 className="cabinet-zone-title">Расписание</h2>
          <div className="cabinet-zone-grid">
            <UpcomingPerformancesWidget bookings={upcomingEvents} />
            <CalendarConflictsWidget conflicts={calendarConflicts} />
          </div>
        </section>
      ) : null}
    </CabinetPageShell>
  );
}
