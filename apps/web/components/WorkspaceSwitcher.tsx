"use client";

import { useEffect, useState } from "react";
import { api, getActiveOrg, getToken, setActiveOrg } from "@/lib/api";
import { KIND_LABEL } from "@/lib/copy";

type Org = { id: string; name: string; kind: string };

export function WorkspaceSwitcher() {
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [current, setCurrent] = useState<string>("");

  useEffect(() => {
    if (!getToken()) return;
    void api<{ flags?: { workspace_switcher?: boolean } }>("/health").then((health) => {
      if (health.flags && health.flags.workspace_switcher === false) {
        setOrgs([]);
      }
    });
    void api<{ organizations: Org[]; active_organization_id?: string }>("/me").then((me) => {
      setOrgs(me.organizations || []);
      const next = getActiveOrg() || me.active_organization_id || me.organizations[0]?.id || "";
      setCurrent(next);
      if (next) setActiveOrg(next);
    });
  }, []);

  if (orgs.length < 2) return null;

  return (
    <label className="workspace-switch">
      <select
        aria-label="Рабочее пространство"
        value={current}
        onChange={(e) => {
          const id = e.target.value;
          setCurrent(id);
          setActiveOrg(id);
          void api("/me/active-org", {
            method: "POST",
            body: JSON.stringify({ organization_id: id }),
          }).finally(() => {
            window.location.reload();
          });
        }}
      >
        {orgs.map((org) => (
          <option key={org.id} value={org.id}>
            {(KIND_LABEL[org.kind] || org.kind) + " · " + org.name}
          </option>
        ))}
      </select>
    </label>
  );
}
