"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { api, createOrgWithConfirm, getActiveOrg, getToken, setActiveOrg, setToken } from "@/lib/api";
import { KIND_LABEL } from "@/lib/copy";
import { loginHref } from "@/lib/next";

type Org = { id: string; name: string; kind: string; role: string };

type Me = {
  email: string;
  full_name: string;
  is_platform_admin?: boolean;
  organizations: Org[];
  active_organization_id?: string;
};

const ROLE: Record<string, string> = {
  owner: "владелец",
  admin: "админ",
  manager: "менеджер",
  viewer: "просмотр",
  member: "в команде",
};

export default function ProfilePage() {
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState("");
  const [active, setActive] = useState("");
  const [switching, setSwitching] = useState(false);
  const [newOrgName, setNewOrgName] = useState("");
  const [newOrgKind, setNewOrgKind] = useState("customer");
  const [orgBusy, setOrgBusy] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      setError("Нужен вход");
      return;
    }
    api<Me>("/me")
      .then((data) => {
        setMe(data);
        const orgs = data.organizations || [];
        setActive(getActiveOrg() || data.active_organization_id || orgs[0]?.id || "");
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  if (!getToken() && error) {
    return (
      <main>
        <h1>Профиль</h1>
        <p>
          {error}. <Link href={loginHref("/profile")}>Войти</Link>
        </p>
      </main>
    );
  }

  if (!me) {
    return (
      <main>
        <p className="kicker">Это вы</p>
        <h1>Профиль</h1>
        {error ? (
          <p>
            {error}. <Link href={loginHref("/profile")}>Войти</Link>
          </p>
        ) : (
          <div className="skeleton" />
        )}
      </main>
    );
  }

  const orgs = me.organizations || [];

  async function addOrg(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const name = newOrgName.trim();
    if (!name) return;
    setOrgBusy(true);
    setError("");
    try {
      const org = await createOrgWithConfirm({ name, kind: newOrgKind, city: "Москва" });
      setActiveOrg(org.id);
      window.location.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось создать пространство");
    } finally {
      setOrgBusy(false);
    }
  }

  return (
    <main className="account-reference">
      <header className="account-heading"><p className="kicker">Ваш аккаунт</p><h1>Мой профиль</h1><p>Личные данные и рабочие пространства.</p></header>
      <section className="card account-identity"><span className="account-monogram" aria-hidden="true">{me.full_name.trim().slice(0,1).toLocaleUpperCase("ru") || "Б"}</span><div><h2>{me.full_name}</h2><p>{me.email}</p></div><Link href="/support">Помощь с аккаунтом →</Link></section>
      <div className="account-columns"><section className="account-organizations"><h2>Мои пространства</h2><p className="timeline">Переключайтесь между своими организациями и ролями.</p>
      {orgs.length > 1 ? (
        <label>
          Активное пространство
          <select
            value={active}
            disabled={switching}
            onChange={(e) => {
              const id = e.target.value;
              setActive(id);
              setSwitching(true);
              setActiveOrg(id);
              void api("/me/active-org", {
                method: "POST",
                body: JSON.stringify({ organization_id: id }),
              })
                .then(() => {
                  window.location.reload();
                })
                .catch((err: unknown) => {
                  setSwitching(false);
                  setError(err instanceof Error ? err.message : "Не удалось переключить");
                });
            }}
          >
            {orgs.map((o) => (
              <option key={o.id} value={o.id}>
                {(KIND_LABEL[o.kind] || o.kind) + " · " + o.name}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      {error ? <p className="timeline">{error}</p> : null}
      {orgs.map((o) => (
        <article className={`card surface-glass account-organization${active === o.id ? " is-active" : ""}`} key={o.id}>
          <strong>{o.name}</strong>
          <div>
            {KIND_LABEL[o.kind] || o.kind} · {ROLE[o.role] || o.role}
            {active === o.id ? " · сейчас" : ""}
          </div>
        </article>
      ))}
      </section>
      <form className="card surface-glass account-create" onSubmit={addOrg}>
        <h2>Добавить пространство</h2>
        <p className="timeline">Для новой команды, артиста или площадки.</p>
        <label>
          Название
          <input value={newOrgName} onChange={(e) => setNewOrgName(e.target.value)} required />
        </label>
        <label>
          Тип
          <select value={newOrgKind} onChange={(e) => setNewOrgKind(e.target.value)}>
            <option value="customer">Заказчик</option>
            <option value="artist">Исполнитель</option>
            <option value="venue">Площадка</option>
          </select>
        </label>
        <button type="submit" disabled={orgBusy}>
          {orgBusy ? "Создаём…" : "Создать"}
        </button>
      </form>
      </div>
      {me.is_platform_admin ? (
        <p>
          <Link href="/admin">Панель оператора →</Link>
        </p>
      ) : null}
      <p style={{ display: "flex", gap: 8 }}>
        <Link className="btn" href="/cabinet">
          Сделки
        </Link>
        <button
          type="button"
          className="secondary"
          onClick={() => {
            setToken(null);
            localStorage.removeItem("booker.admin");
            window.location.href = "/";
          }}
        >
          Выйти
        </button>
      </p>
    </main>
  );
}
