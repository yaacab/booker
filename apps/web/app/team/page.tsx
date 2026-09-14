"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, getActiveOrg, getToken } from "@/lib/api";
import { commerceError } from "@/lib/commerce";
import { TeamPanel } from "@/components/team/TeamPanel";
export default function TeamPage() {
  const [orgId, setOrgId] = useState(""); const [error, setError] = useState("");
  useEffect(() => { if (!getToken()) { setError("Войдите в аккаунт, чтобы открыть команду"); return; } api<{ active_organization_id?: string; organizations: { id: string }[] }>("/me").then(me => { const requested = new URLSearchParams(location.search).get("organization"); const active = requested || getActiveOrg() || me.active_organization_id; const org = me.organizations.find(o => o.id === active) || (!requested ? me.organizations[0] : undefined); if (org) setOrgId(org.id); else setError("Создайте рабочее пространство в профиле"); }).catch(e => setError(commerceError(e))); }, []);
  return <main><h1>Команда</h1>{error && <p role="alert">{error}</p>}{orgId ? <TeamPanel key={orgId} orgId={orgId} /> : !error && <p role="status">Загружаем пространство…</p>}<p><Link href="/profile">Профиль и рабочие пространства</Link></p></main>;
}
