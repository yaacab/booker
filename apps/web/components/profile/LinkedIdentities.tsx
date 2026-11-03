"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatWhen } from "@/lib/format";

type IdentityRow = {
  provider: string;
  linked_at?: string | null;
  last_login_at?: string | null;
};

type IdentitiesPayload = {
  has_password_login: boolean;
  identities: IdentityRow[];
};

const PROVIDER_LABEL: Record<string, string> = {
  telegram: "Telegram",
  yandex: "Яндекс ID",
  vk: "VK ID",
};

const PLANNED = ["telegram", "yandex", "vk"] as const;

export function LinkedIdentities() {
  const [data, setData] = useState<IdentitiesPayload | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    api<IdentitiesPayload>("/me/identities")
      .then((payload) => {
        if (cancelled) return;
        setData(payload);
        setError("");
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message || "Не удалось загрузить привязки");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const linked = new Map((data?.identities || []).map((row) => [row.provider, row]));

  return (
    <section className="card" data-testid="linked-identities">
      <h2>Способы входа</h2>
      <p className="timeline">
        Один аккаунт Букера. Внешние провайдеры появляются здесь после явной привязки.
      </p>
      {error ? <p className="timeline">{error}</p> : null}
      {!data && !error ? <p className="timeline">Загружаем…</p> : null}
      {data ? (
        <ul className="timeline">
          <li>
            Email и пароль: {data.has_password_login ? "доступны" : "не настроены"}
          </li>
          {PLANNED.map((provider) => {
            const row = linked.get(provider);
            const label = PROVIDER_LABEL[provider] || provider;
            if (row) {
              return (
                <li key={provider}>
                  {label}: привязан
                  {row.linked_at ? ` · с ${formatWhen(row.linked_at)}` : ""}
                  {row.last_login_at ? ` · вход ${formatWhen(row.last_login_at)}` : ""}
                </li>
              );
            }
            return (
              <li key={provider}>
                {label}: не привязан
                {provider === "telegram"
                  ? " · вход через Mini App, когда бот настроен"
                  : " · OAuth пока выключен (fail-closed)"}
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}
