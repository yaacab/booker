"use client";

import Link from "next/link";
import { CabinetPageShell } from "../CabinetPageShell";
import { SupplyCabinetSection } from "../SupplyCabinetSection";
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

export function PerformerCabinetDashboard({ section = "home" }: { section?: PerformerCabinetSection }) {
  const {
    ready,
    error,
    email,
    orgName,
    orgId,
    role,
    artistId,
    requests,
    bookings,
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

  const completenessScore = profileIncomplete?.score;
  const showRequests = section === "home" || section === "requests";
  const showCalendar = section === "home" || section === "calendar";
  const showVitrine = section === "home" || section === "services";
  const subtitle =
    section === "calendar"
      ? "Свободные слоты, ближайшие даты и конфликты календаря."
      : section === "requests"
        ? "Входящие заявки, предложения и удержания."
        : section === "services"
          ? "Услуги, тарифы и публичная витрина."
          : "Календарь, гонорар и ответы на запросы. Вы не собираете события — вас бронируют.";

  const actions =
    section === "calendar"
      ? [{ href: "#cabinet-widgets", label: "К слотам", primary: true }]
      : section === "requests"
        ? [{ href: "/cabinet/performer/calendar", label: "К календарю", primary: true }]
        : section === "services"
          ? [
              { href: "/cabinet/performer/requests", label: "К заявкам", primary: true },
              { href: "/cabinet/performer", label: "На главную" },
            ]
          : [
              { href: "/cabinet/performer/requests", label: "К заявкам", primary: true },
              { href: "/cabinet/performer/services", label: "Услуги и витрина" },
            ];

  return (
    <CabinetPageShell
      mode="performer"
      kindKey="artist"
      ready={ready}
      error={error}
      email={email}
      orgName={orgName}
      empty={empty && section === "home"}
      emptyState={
        <article className="card empty">
          <h2>Пока тихо</h2>
          <p>
            Новые запросы, удержания и ближайшие даты появятся здесь. Держите календарь открытым — так вас чаще
            бронируют.
          </p>
          <div className="cabinet-hero-actions">
            <Link className="btn" href="/cabinet/performer/calendar">
              Открыть календарь
            </Link>
            <Link className="btn secondary" href="/cabinet/performer/services">
              Настроить витрину
            </Link>
          </div>
        </article>
      }
      subtitle={subtitle}
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
      actions={actions}
      lead={
        showCalendar && orgId ? (
          <OpenSlotsWidget orgId={orgId} role={role} orgName={orgName} supplyKind="artist" />
        ) : null
      }
      footer={
        orgId ? (
          <div id="supply">
            <SupplyCabinetSection orgId={orgId} role={role} />
          </div>
        ) : null
      }
    >
      {showVitrine && orgId ? (
        <section className="cabinet-zone" aria-label="Витрина и услуги">
          <h2 className="cabinet-zone-title">Витрина и услуги</h2>
          <div className="cabinet-zone-grid">
            <PortfolioRiderWidget orgId={orgId} role={role} />
            <ServicesWidget orgId={orgId} role={role} compact={section === "home"} />
          </div>
        </section>
      ) : null}

      {showRequests ? (
        <section className="cabinet-zone" aria-label="Входящие">
          <h2 className="cabinet-zone-title">Входящие</h2>
          <div className="cabinet-zone-grid">
            {section === "home" ? (
              <PerformerOnboardingWidget
                profileComplete={!profileIncomplete}
                hasOpenSlots={upcomingPerformances.length > 0 || activeHolds.length > 0}
                hasRequests={newRequests.length + awaitingResponse.length > 0}
              />
            ) : null}
            {section === "requests" ? (
              <RequestsInboxWidget
                requests={requests}
                role={role}
                offerBusy={offerBusy}
                onSendOffer={(item) => void sendOffer(item)}
              />
            ) : (
              <NewRequestsWidget
                requests={newRequests}
                role={role}
                offerBusy={offerBusy}
                onSendOffer={(item) => void sendOffer(item)}
              />
            )}
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
            {orgId ? (
              <CalendarOverviewWidget orgId={orgId} artistId={artistId} bookings={bookings} />
            ) : null}
            <UpcomingPerformancesWidget bookings={upcomingPerformances} />
            <CalendarConflictsWidget conflicts={calendarConflicts} />
            {profileIncomplete ? <ProfileCompletenessWidget completeness={profileIncomplete} /> : null}
          </div>
        </section>
      ) : null}
    </CabinetPageShell>
  );
}
