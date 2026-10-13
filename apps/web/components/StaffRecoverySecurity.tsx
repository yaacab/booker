"use client";

import { FormEvent, useState } from "react";
import { api, setToken } from "@/lib/api";

export default function StaffRecoverySecurity({ email }: { email: string }) {
  const [totp, setTotp] = useState("");
  const [password, setPassword] = useState("");
  const [remaining, setRemaining] = useState<number | null>(null);
  const [codes, setCodes] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function showCount() {
    setError("");
    setBusy(true);
    try {
      const result = await api<{ remaining: number }>("/auth/admin-totp/recovery-codes/count", {
        headers: { "X-Booker-TOTP": totp.trim() },
      });
      setRemaining(result.remaining);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось проверить количество кодов");
    } finally {
      setBusy(false);
    }
  }

  async function regenerate(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const result = await api<{ recovery_codes: string[] }>("/auth/admin-totp/recovery-codes/regenerate", {
        method: "POST",
        body: JSON.stringify({ email, password, totp: totp.trim() }),
      });
      setCodes(result.recovery_codes);
      setRemaining(result.recovery_codes.length);
      setSaved(false);
      setPassword("");
      setTotp("");
      setToken(null);
      localStorage.removeItem("booker.admin");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось создать новые коды");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card surface-glass" style={{ display: "grid", gap: 12, maxWidth: 480, marginTop: 16 }}>
      <h2>Безопасность · резервные коды</h2>
      {codes.length ? (
        <>
          <p role="status">Сохраните новые коды вне Букера. Старый комплект и служебные сессии отозваны; каждый код работает один раз.</p>
          <label htmlFor="profile-recovery-codes">Новый комплект</label>
          <textarea id="profile-recovery-codes" readOnly rows={10} value={codes.join("\n")} autoComplete="off" spellCheck={false} />
          <label><input type="checkbox" checked={saved} onChange={(event) => setSaved(event.target.checked)} /> Я сохранил коды</label>
          <button type="button" disabled={!saved} onClick={() => { setCodes([]); window.location.href = "/login"; }}>Войти заново</button>
        </>
      ) : (
        <form onSubmit={regenerate} style={{ display: "grid", gap: 12 }}>
          <p className="timeline">Для проверки и обновления кодов нужен текущий код Authenticator. Обновление аннулирует прежний комплект и все служебные сессии.</p>
          <label>Текущий код Authenticator<input value={totp} onChange={(event) => setTotp(event.target.value)} inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" minLength={6} maxLength={6} required /></label>
          {remaining !== null ? <p role="status">Осталось кодов: {remaining}</p> : null}
          <button type="button" className="secondary" disabled={busy || !/^[0-9]{6}$/.test(totp.trim())} onClick={() => void showCount()}>Проверить количество</button>
          <label>Пароль для выпуска нового комплекта<input value={password} onChange={(event) => setPassword(event.target.value)} type="password" autoComplete="current-password" minLength={8} required /></label>
          {error ? <p role="alert" style={{ color: "var(--danger)" }}>{error}</p> : null}
          <button type="submit" disabled={busy}>{busy ? "Проверяем…" : "Создать новые резервные коды"}</button>
        </form>
      )}
    </section>
  );
}
