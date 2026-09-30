"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { BrandLockup } from "@/components/BrandLockup";
import { api, createOrgWithConfirm, setActiveOrg, setToken } from "@/lib/api";
import { cabinetPathForKind } from "@/lib/cabinetRoutes";
import { safeNext } from "@/lib/next";

type AuthPageProps = {
  artistWelcome?: boolean;
  publicRegistrationEnabled: boolean;
};

export default function AuthPage({
  artistWelcome = false,
  publicRegistrationEnabled,
}: AuthPageProps) {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register" | "recover" | "reset">(
    artistWelcome && publicRegistrationEnabled ? "register" : "login",
  );
  const [resetToken, setResetToken] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState("");
  const [selectedRole, setSelectedRole] = useState(artistWelcome ? "artist" : "customer");

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    if (query.get("mode") === "register" && publicRegistrationEnabled) setMode("register");
    if (query.get("role") === "artist") setSelectedRole("artist");
    const token = new URLSearchParams(window.location.search).get("reset");
    if (token) {
      setResetToken(token);
      setMode("reset");
    }
  }, [publicRegistrationEnabled]);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setNotice("");
    setPending(true);
    const form = new FormData(e.currentTarget);
    try {
      if (mode === "register" && !publicRegistrationEnabled) {
        setError("Саморегистрация временно закрыта. Войдите по приглашению.");
        return;
      }
      if (mode === "reset") {
        await api("/auth/recover/confirm", {
          method: "POST",
          body: JSON.stringify({
            token: resetToken,
            password: String(form.get("password") || ""),
          }),
        });
        setNotice("Пароль обновлён. Войдите с новым паролем.");
        setMode("login");
        return;
      }
      if (mode === "recover") {
        await api("/auth/recover", {
          method: "POST",
          body: JSON.stringify({ email: String(form.get("email") || "") }),
        });
        setNotice("Если аккаунт существует, инструкция для восстановления будет отправлена на указанную почту.");
        return;
      }
      const path = mode === "login" ? "/auth/login" : "/auth/register";
      const payload: Record<string, unknown> = {
        email: String(form.get("email") || ""),
        password: String(form.get("password") || ""),
      };
      if (mode === "register") {
        payload.full_name = String(form.get("full_name") || "Пользователь");
        payload.accept_offer = form.get("accept_offer") === "on";
        payload.accept_privacy = form.get("accept_privacy") === "on";
        payload.marketing_opt_in = form.get("marketing_opt_in") === "on";
      }
      const res = await api<{ token: string; is_platform_admin?: boolean }>(path, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setToken(res.token);
      if (res.is_platform_admin) localStorage.setItem("booker.admin", "1");
      else localStorage.removeItem("booker.admin");
      if (mode === "register") {
        const kind = String(form.get("kind") || "customer");
        const org = await createOrgWithConfirm({
          name: String(payload.full_name || "Пользователь"),
          kind,
          city: "Москва",
        });
        setActiveOrg(org.id);
        const rawNext = new URLSearchParams(window.location.search).get("next");
        const roleCabinet = cabinetPathForKind(kind);
        const next = safeNext(rawNext, roleCabinet);
        router.push(!rawNext || next === "/cabinet" ? roleCabinet : next);
        return;
      }
      const me = await api<{
        organizations?: { id: string; kind: string }[];
        active_organization_id?: string;
      }>("/me");
      const activeOrgId = me.active_organization_id || me.organizations?.[0]?.id;
      if (activeOrgId) setActiveOrg(activeOrgId);
      const org = me.organizations?.find((o) => o.id === activeOrgId) || me.organizations?.[0];
      const rawNext = new URLSearchParams(window.location.search).get("next");
      const next = safeNext(rawNext);
      if (!rawNext || next === "/cabinet") {
        router.push(cabinetPathForKind(org?.kind || "customer"));
      } else {
        router.push(next);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка входа");
    } finally {
      setPending(false);
    }
  }

  const heading =
    mode === "reset"
      ? "Задайте новый пароль"
      : mode === "recover"
        ? "Вернём доступ к кабинету"
        : mode === "login"
          ? "Войти в Букер"
          : "Создать кабинет";

  const kicker =
    mode === "reset"
      ? "Подтверждение восстановления"
      : mode === "recover"
        ? "Восстановление доступа"
        : mode === "login"
          ? "Ваше пространство событий"
          : "Новый аккаунт";

  return (
    <main className={`login-layout ${artistWelcome ? "artist-welcome" : ""}`}>
      {artistWelcome ? <aside className="artist-benefits" aria-label="Букер для артистов">
        <p className="kicker">Твоя следующая сцена</p>
        <h1>Ты создаёшь атмосферу.<br /><em>Мы помогаем встретиться.</em></h1>
        <p className="artist-benefits-lead">{publicRegistrationEnabled
          ? "С заказчиками, которым нужен именно твой талант. Создай кабинет и собери всё для будущих выступлений в одном месте."
          : "Сейчас Букер работает как закрытый пилот. Если тебе уже выдали доступ, войди в существующий кабинет."}</p>
        <ol>
          <li><span>01</span><div><h2>Покажи, что умеешь</h2><p>Профиль с видео, программой и условиями поможет заказчику познакомиться с тобой.</p></div></li>
          <li><span>02</span><div><h2>Выбирай свои выступления</h2><p>Смотри открытые заказы, откликайся на подходящие события и получай личные заявки.</p></div></li>
          <li><span>03</span><div><h2>Договорись без путаницы</h2><p>Даты, предложения и переписка с заказчиком — в общем пространстве сделки.</p></div></li>
        </ol>
        <p className="artist-benefits-foot">{publicRegistrationEnabled
          ? "Сначала кабинет. Фото, программу и свободные даты добавишь следующим шагом."
          : "Новые участники подключаются по приглашению команды пилота."}</p>
      </aside> : <aside className="login-story" aria-label="О Букере"><p className="kicker">Артисты. События. Букер.</p><h2>Хорошие события<br />начинаются с людей.</h2><img src="/design/puzzle-dj.png" alt="Декоративный пазл — музыка для события" width="1280" height="1280" /><p>Находите артистов и заказы, обсуждайте детали и сохраняйте договорённости в одном месте.</p></aside>}
      <section className="login-fields">
      {!artistWelcome && <p className="brand-lockup-wrap">
        <BrandLockup />
      </p>}
      <p className="kicker">{kicker}</p>
      {artistWelcome ? <h2>{mode === "register" ? "Начни с простого" : heading}</h2> : <h1>{heading}</h1>}
      {!publicRegistrationEnabled && mode === "login" ? (
        <div className="registration-closed-note" role="status">
          <strong>Саморегистрация временно закрыта</strong>
          <p>
            Букер работает как закрытый пилот. Если у вас уже есть аккаунт или приглашение,
            войдите ниже. По вопросам доступа напишите на{" "}
            <a href="mailto:hello@bukergo.ru">hello@bukergo.ru</a>.
          </p>
        </div>
      ) : null}
      {mode === "register" ? (
        <p className="timeline">{artistWelcome ? "Три поля — и у тебя будет кабинет артиста." : "Выберите роль — мы настроим кабинет и первый сценарий под ваши задачи."}</p>
      ) : mode === "reset" ? (
        <p className="timeline">Введите новый пароль для аккаунта.</p>
      ) : mode === "recover" ? (
        <p className="timeline">Укажите email — отправим инструкцию, если аккаунт существует.</p>
      ) : null}
      <form className="card surface-glass" style={{ display: "grid", gap: 16 }} onSubmit={onSubmit}>
        {mode === "register" ? (
          <>
            <label>
              Имя
              <input name="full_name" autoComplete="name" placeholder={artistWelcome ? "Как тебя зовут?" : undefined} required />
            </label>
            {artistWelcome ? <input type="hidden" name="kind" value="artist" /> : <fieldset className="role-picker" data-testid="role-picker">
              <legend>Роль</legend>
              <input type="hidden" name="kind" value={selectedRole} />
              {[
                ["customer", "Заказчик", "Ищу артистов для своего события"],
                ["artist", "Артист / менеджер", "Ищу заказы и управляю выступлениями"],
                ["venue", "Площадка", "Размещаю пространство и слоты"],
              ].map(([value, title, description]) => (
                <button
                  key={value}
                  type="button"
                  className={`role-option ${selectedRole === value ? "on" : ""}`}
                  aria-pressed={selectedRole === value}
                  data-testid={`role-option-${value}`}
                  onClick={() => setSelectedRole(value)}
                >
                  <span><strong>{title}</strong><small>{description}</small></span>
                  <span aria-hidden>{selectedRole === value ? "✓" : ""}</span>
                </button>
              ))}
            </fieldset>}
          </>
        ) : null}
        {mode !== "reset" ? (
          <label>
            Email
            <input name="email" type="email" autoComplete="username" required />
          </label>
        ) : null}
        {mode !== "recover" ? (
          <label>
            {mode === "reset" ? "Новый пароль" : "Пароль"}
            <input
              name="password"
              type="password"
              autoComplete={mode === "register" || mode === "reset" ? "new-password" : "current-password"}
              required
              minLength={8}
              placeholder={artistWelcome ? "Не меньше 8 символов" : undefined}
            />
          </label>
        ) : null}
        {mode === "register" ? (
          <>
            <div className="unknown">
              <input id="accept_offer" name="accept_offer" type="checkbox" required />
              <span>
                <label htmlFor="accept_offer" className="inline-label">
                  Принимаю
                </label>{" "}
                <a href="/legal/offer">оферту</a> и правила использования сервиса.
              </span>
            </div>
            <div className="unknown">
              <input id="accept_privacy" name="accept_privacy" type="checkbox" required />
              <span>
                <label htmlFor="accept_privacy" className="inline-label">
                  Согласен
                </label>{" "}
                с <a href="/legal/privacy">политикой обработки персональных данных</a>.
              </span>
            </div>
            {!artistWelcome && <label className="unknown">
              <input name="marketing_opt_in" type="checkbox" />
              Получать новости продукта и специальные предложения. Необязательно.
            </label>}
          </>
        ) : null}
        {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
        {notice ? <p className="timeline">{notice}</p> : null}
        <button type="submit" disabled={pending}>
          {pending
            ? "Обрабатываем…"
            : mode === "reset"
              ? "Сохранить пароль"
              : mode === "recover"
                ? "Отправить инструкцию"
                : mode === "login"
                  ? "Войти"
                  : artistWelcome ? "Создать кабинет артиста →" : "Создать аккаунт"}
        </button>
      </form>
      <p className="login-secondary-actions" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {mode === "reset" ? (
          <button type="button" className="secondary" onClick={() => setMode("login")}>
            Вернуться ко входу
          </button>
        ) : (
          <>
            {publicRegistrationEnabled ? (
              <button type="button" className="secondary" onClick={() => setMode(mode === "login" ? "register" : "login")}>
                {mode === "login" ? "Создать аккаунт" : "Вернуться ко входу"}
              </button>
            ) : mode !== "login" ? (
              <button type="button" className="secondary" onClick={() => setMode("login")}>
                Вернуться ко входу
              </button>
            ) : null}
            {mode === "login" ? (
              <button type="button" className="secondary" onClick={() => setMode("recover")}>
                Забыли пароль?
              </button>
            ) : null}
          </>
        )}
      </p>
      {!artistWelcome && <p className="login-demo-note"><a href="/dev/cabinets">Тестовые кабинеты и данные для проверки ↗</a></p>}
      </section>
    </main>
  );
}
