/** Spec §5 — role onboarding: missing steps list, no fake success %. */

export type OnboardingItem = {
  id: string;
  label: string;
  done: boolean;
  href: string;
};

export function customerOnboardingItems(input: {
  hasName: boolean;
  hasContact: boolean;
  hasEventWithCity: boolean;
  hasOffers: boolean;
}): OnboardingItem[] {
  return [
    {
      id: "name",
      label: "Указать имя в профиле",
      done: input.hasName,
      href: "/profile",
    },
    {
      id: "contact",
      label: "Подтвердить канал связи (email)",
      done: input.hasContact,
      href: "/profile",
    },
    {
      id: "event",
      label: "Создать событие: город, дата и тип",
      done: input.hasEventWithCity,
      href: "/events/new",
    },
    {
      id: "search",
      label: "Посмотреть каталог по слотам",
      done: input.hasEventWithCity,
      href: "/search",
    },
    {
      id: "offer",
      label: "Дождаться предложения в Deal Room",
      done: input.hasOffers,
      href: "/cabinet/customer",
    },
  ];
}

export function performerOnboardingItems(input: {
  profileComplete: boolean;
  hasOpenSlots: boolean;
  hasRequests: boolean;
}): OnboardingItem[] {
  return [
    {
      id: "profile",
      label: "Заполнить профиль и портфолио",
      done: input.profileComplete,
      href: "/cabinet/performer#supply",
    },
    {
      id: "slots",
      label: "Открыть слоты в календаре",
      done: input.hasOpenSlots || input.hasRequests,
      href: "/cabinet/performer/calendar",
    },
    {
      id: "requests",
      label: "Ответить на входящую заявку предложением",
      done: input.hasRequests,
      href: "/cabinet/performer/requests",
    },
  ];
}

export function venueOnboardingItems(input: {
  hasHalls: boolean;
  profileComplete: boolean;
  hasRequests: boolean;
}): OnboardingItem[] {
  return [
    {
      id: "halls",
      label: "Добавить зал с вместимостью",
      done: input.hasHalls,
      href: "/cabinet/venue/halls",
    },
    {
      id: "profile",
      label: "Заполнить профиль площадки",
      done: input.profileComplete,
      href: "/cabinet/venue#supply",
    },
    {
      id: "requests",
      label: "Ответить на заявку бронирования",
      done: input.hasRequests,
      href: "/cabinet/venue/requests",
    },
  ];
}

export function openOnboardingItems(items: OnboardingItem[]): OnboardingItem[] {
  return items.filter((i) => !i.done);
}
