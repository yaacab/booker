"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { api, getActiveOrg, getToken, setActiveOrg } from "@/lib/api";
import { cabinetPathForKind } from "@/lib/cabinetRoutes";
import { loginHref } from "@/lib/next";
import Link from "next/link";

/** Legacy `/cabinet` — redirect to role-specific cabinet by active workspace. */
export default function CabinetRedirectPage() {
  const router = useRouter();

  useEffect(() => {
    if (!getToken()) {
      router.replace(loginHref("/cabinet"));
      return;
    }
    void api<{
      organizations?: { id: string; kind: string }[];
      active_organization_id?: string;
    }>("/me")
      .then((me) => {
        const activeOrgId = getActiveOrg() || me.active_organization_id || me.organizations?.[0]?.id;
        const org = me.organizations?.find((o) => o.id === activeOrgId) || me.organizations?.[0];
        if (org) setActiveOrg(org.id);
        router.replace(cabinetPathForKind(org?.kind || "customer"));
      })
      .catch(() => router.replace("/cabinet/customer"));
  }, [router]);

  return (
    <main>
      <p className="timeline">Открываем кабинет…</p>
      <p>
        <Link href={loginHref("/cabinet")}>Войти</Link>
      </p>
    </main>
  );
}
