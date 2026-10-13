"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import {
  DATA_SUBJECT_HOLD_REASONS, DATA_SUBJECT_REASONS, DATA_SUBJECT_TYPES,
  availableDataSubjectTransitions, dataSubjectError, dataSubjectHeaders, dataSubjectListPath, dataSubjectPath,
  dataSubjectReasonForStatus,
  dataSubjectStatusLabel, dataSubjectTypeLabel,
  type DataSubjectList, type DataSubjectRequest, type DataSubjectRequestDetail,
  type DataSubjectDeletionPlan, type DataSubjectHold,
} from "@/lib/dataSubject";

type Mode = "user" | "admin";
type RequestKey = { signature: string; key: string };

function errorText(error: unknown): string {
  return dataSubjectError(error instanceof ApiError ? error.status : 0);
}

function RequestSummary({ row, onOpen }: { row: DataSubjectRequest; onOpen: () => void }) {
  return <li>
    <button type="button" onClick={onOpen}>{dataSubjectTypeLabel(row.request_type)} · {row.request_type === "delete" && row.status === "approved"
      ? "Объём рассмотрен, удаление не выполнено" : dataSubjectStatusLabel(row.status)}</button>
    {row.created_at ? <small> · {new Date(row.created_at).toLocaleDateString("ru-RU")}</small> : null}
  </li>;
}

function UserRequests() {
  const [items, setItems] = useState<DataSubjectRequest[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [listLoaded, setListLoaded] = useState(false);
  const [selected, setSelected] = useState<DataSubjectRequestDetail | null>(null);
  const [kind, setKind] = useState<(typeof DATA_SUBJECT_TYPES)[number]>("access");
  const [correctionField, setCorrectionField] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const keyRef = useRef<RequestKey | null>(null);
  const sessionToken = useRef<string | null>(null);
  const sessionEpoch = useRef(0);

  async function loadList(nextOffset = offset) {
    const token = localStorage.getItem("booker.token");
    const epoch = sessionEpoch.current;
    const result = await api<DataSubjectList>(dataSubjectListPath(nextOffset), { cache: "no-store" });
    if (epoch !== sessionEpoch.current || token !== localStorage.getItem("booker.token")) return;
    setItems(result.items);
    setTotal(result.total ?? result.items.length);
    setOffset(nextOffset);
    setListLoaded(true);
  }

  async function loadDetail(id: string) {
    const token = localStorage.getItem("booker.token");
    const epoch = sessionEpoch.current;
    const detail = await api<DataSubjectRequestDetail>(dataSubjectPath(id), { cache: "no-store" });
    if (epoch !== sessionEpoch.current || token !== localStorage.getItem("booker.token")) return;
    setSelected(detail);
  }

  useEffect(() => {
    sessionToken.current = localStorage.getItem("booker.token");
    const checkSession = () => {
      const next = localStorage.getItem("booker.token");
      if (next === sessionToken.current) return;
      sessionToken.current = next;
      sessionEpoch.current += 1;
      setItems([]);
      setTotal(0);
      setOffset(0);
      setListLoaded(false);
      setSelected(null);
      keyRef.current = null;
      setError("");
      setNotice("");
      if (next) void loadList(0).catch((failure) => setError(errorText(failure)));
    };
    window.addEventListener("storage", checkSession);
    window.addEventListener("focus", checkSession);
    void loadList().catch((failure) => setError(errorText(failure)));
    return () => {
      window.removeEventListener("storage", checkSession);
      window.removeEventListener("focus", checkSession);
    };
  }, []);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const body = { request_type: kind, ...(kind === "correct" ? { correction_field: correctionField.trim() } : {}) };
    const signature = JSON.stringify(body);
    if (keyRef.current?.signature !== signature) keyRef.current = { signature, key: crypto.randomUUID() };
    setBusy(true);
    setError("");
    setNotice("");
    let postSucceeded = false;
    try {
      const created = await api<DataSubjectRequest>("/data-subject/requests", {
        method: "POST", headers: dataSubjectHeaders("", undefined, keyRef.current.key),
        body: JSON.stringify(body),
      });
      postSucceeded = true;
      await loadList(0);
      await loadDetail(created.id);
      keyRef.current = null;
      setCorrectionField("");
      setNotice("Запрос получен. Его статус можно проверить здесь.");
    } catch (failure) {
      setError(postSucceeded
        ? "Запрос мог быть сохранён, но история не обновилась. Повторите отправку с теми же данными: ключ запроса сохранён."
        : errorText(failure));
      if (failure instanceof ApiError && failure.status === 409) {
        try { await loadList(); } catch { /* keep the original conflict message */ }
      }
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    if (!selected || busy) return;
    const id = selected.id;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api(dataSubjectPath(id, false, "/cancel"), {
        method: "POST", headers: dataSubjectHeaders("", selected.state_version),
      });
      await Promise.all([loadList(), loadDetail(id)]);
      setNotice("Запрос отменён.");
    } catch (failure) {
      setError(errorText(failure));
      if (failure instanceof ApiError && failure.status === 409) {
        try { await Promise.all([loadList(), loadDetail(id)]); } catch { /* preserve conflict */ }
      }
    } finally {
      setBusy(false);
    }
  }

  return <section className="card surface-glass" aria-labelledby="data-subject-title" style={{ marginTop: 16, minWidth: 0 }}>
    <h2 id="data-subject-title">Запросы по персональным данным</h2>
    <p>Здесь можно отправить запрос и следить за его статусом. Срок и результат зависят от проверки; отправка запроса сама по себе не удаляет данные.</p>
    <form onSubmit={create} style={{ display: "grid", gap: 12, maxWidth: 520 }}>
      <label>Тип запроса
        <select value={kind} onChange={(event) => setKind(event.target.value as typeof kind)}>
          {DATA_SUBJECT_TYPES.map((value) => <option key={value} value={value}>{dataSubjectTypeLabel(value)}</option>)}
        </select>
      </label>
      {kind === "correct" ? <label>Поле для исправления
        <select value={correctionField} onChange={(event) => setCorrectionField(event.target.value)} required>
          <option value="">Выберите поле</option>
          <option value="email">Электронная почта</option>
          <option value="phone">Телефон</option>
          <option value="full_name">Имя</option>
        </select>
      </label> : null}
      <p>Не указывайте здесь пароли, коды и платёжные реквизиты. Подробности при необходимости уточнит оператор.</p>
      <button type="submit" disabled={busy}>{busy ? "Сохраняем…" : "Отправить запрос"}</button>
    </form>
    {error ? <p role="alert">{error}</p> : null}
    {notice ? <p role="status">{notice}</p> : null}
    <h3>История запросов</h3>
    {listLoaded ? <p>Всего: {total}</p> : null}
    {items.length ? <ul>{items.map((row) => <RequestSummary key={row.id} row={row}
      onOpen={() => { void loadDetail(row.id).catch((failure) => setError(errorText(failure))); }} />)}</ul> :
      listLoaded ? <p>Запросов на этой странице нет.</p> : <p>Загружаем историю…</p>}
    {listLoaded ? <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
      <button type="button" disabled={busy || offset === 0} onClick={() => void loadList(Math.max(0, offset - 20)).catch((failure) => setError(errorText(failure)))}>Назад</button>
      <button type="button" disabled={busy || offset + 20 >= total} onClick={() => void loadList(offset + 20).catch((failure) => setError(errorText(failure)))}>Далее</button>
    </div> : null}
    {selected ? <section aria-label="Детали запроса">
      <h4>{dataSubjectTypeLabel(selected.request_type)}</h4>
      <p>Статус: {dataSubjectStatusLabel(selected.status)}</p>
      {selected.request_type === "delete" && selected.status === "approved" ?
        <p>Объём запроса рассмотрен. Удаление данных не выполнено; оно требует отдельного решения и сейчас отключено.</p> : null}
      {selected.correction_field ? <p>Поле для исправления: {selected.correction_field}</p> : null}
      {selected.events?.length ? <ol>{selected.events.map((item) => <li key={item.state_version}>
        {dataSubjectStatusLabel(item.to_status)}
      </li>)}</ol> : null}
      {(["access", "export"].includes(selected.request_type)) ?
        <p>Автоматическая выгрузка файла пока не доступна; статус запроса виден выше.</p> : null}
      {(["pending", "needs_info"].includes(selected.status)) ?
        <button type="button" disabled={busy} onClick={() => void cancel()}>Отменить запрос</button> : null}
    </section> : null}
  </section>;
}

function AdminRequests() {
  const [totp, setTotp] = useState("");
  const [verified, setVerified] = useState(false);
  const verifiedRef = useRef(false);
  const sessionToken = useRef<string | null>(null);
  const sessionEpoch = useRef(0);
  const [items, setItems] = useState<DataSubjectRequest[]>([]);
  const [total, setTotal] = useState(0);
  const [queueStatus, setQueueStatus] = useState("");
  const [queueOffset, setQueueOffset] = useState(0);
  const [selected, setSelected] = useState<DataSubjectRequestDetail | null>(null);
  const [plan, setPlan] = useState<DataSubjectDeletionPlan | null>(null);
  const [holds, setHolds] = useState<DataSubjectHold[]>([]);
  const [status, setStatus] = useState("");
  const [reasonCode, setReasonCode] = useState<(typeof DATA_SUBJECT_REASONS)[number]>("review_started");
  const [holdReason, setHoldReason] = useState<(typeof DATA_SUBJECT_HOLD_REASONS)[number]>("dispute");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  function adminHeaders(version?: number) {
    return dataSubjectHeaders(verifiedRef.current ? "" : totp, version);
  }

  function clearSensitive() {
    verifiedRef.current = false;
    setVerified(false);
    setTotp("");
    setItems([]);
    setTotal(0);
    setQueueOffset(0);
    setSelected(null);
    setPlan(null);
    setHolds([]);
  }

  useEffect(() => {
    sessionToken.current = localStorage.getItem("booker.token");
    const checkSession = () => {
      const next = localStorage.getItem("booker.token");
      if (next === sessionToken.current) return;
      sessionToken.current = next;
      sessionEpoch.current += 1;
      clearSensitive();
      setError("");
      setNotice("");
    };
    window.addEventListener("storage", checkSession);
    window.addEventListener("focus", checkSession);
    return () => {
      window.removeEventListener("storage", checkSession);
      window.removeEventListener("focus", checkSession);
    };
  }, []);

  async function loadList(nextStatus = queueStatus, nextOffset = queueOffset) {
    const token = localStorage.getItem("booker.token");
    const epoch = sessionEpoch.current;
    const result = await api<DataSubjectList>(dataSubjectListPath(nextOffset, true, nextStatus), {
      headers: adminHeaders(), cache: "no-store",
    });
    if (epoch !== sessionEpoch.current || token !== localStorage.getItem("booker.token")) return;
    setItems(result.items);
    setTotal(result.total ?? result.items.length);
    setQueueStatus(nextStatus);
    setQueueOffset(nextOffset);
    if (!verifiedRef.current) {
      verifiedRef.current = true;
      setVerified(true);
      setTotp("");
    }
  }

  async function loadDetail(id: string) {
    const token = localStorage.getItem("booker.token");
    const epoch = sessionEpoch.current;
    setSelected(null);
    setHolds([]);
    setPlan(null);
    const detail = await api<DataSubjectRequestDetail>(dataSubjectPath(id, true), {
      headers: adminHeaders(), cache: "no-store",
    });
    if (epoch !== sessionEpoch.current || token !== localStorage.getItem("booker.token")) return;
    const list = await api<{ items: DataSubjectHold[] }>(
      `/admin/legal-holds?subject_user_id=${encodeURIComponent(detail.subject_user_id || "")}`,
      { headers: adminHeaders(), cache: "no-store" },
    );
    if (epoch !== sessionEpoch.current || token !== localStorage.getItem("booker.token")) return;
    setSelected(detail);
    setHolds(list.items);
    const nextStatus = availableDataSubjectTransitions(detail)[0] || "";
    setStatus(nextStatus);
    setReasonCode(dataSubjectReasonForStatus(nextStatus));
  }

  async function execute(task: () => Promise<void>, refreshId?: string) {
    if (busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await task();
    } catch (failure) {
      setError(errorText(failure));
      if (failure instanceof ApiError && (failure.status === 401 || failure.status === 403)) {
        clearSensitive();
        return;
      }
      if (failure instanceof ApiError && failure.status === 409) {
        try {
          await loadList();
          if (refreshId) await loadDetail(refreshId);
        } catch (refreshFailure) {
          if (refreshFailure instanceof ApiError && (refreshFailure.status === 401 || refreshFailure.status === 403)) {
            clearSensitive();
            setError(errorText(refreshFailure));
          }
        }
      }
    } finally {
      setBusy(false);
    }
  }

  function transition(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const current = selected;
    void execute(async () => {
      await api(dataSubjectPath(current.id, true, "/transition"), {
        method: "POST", headers: adminHeaders(current.state_version),
        body: JSON.stringify({ status, decision_reason_code: reasonCode }),
      });
      await Promise.all([loadList(), loadDetail(current.id)]);
      setNotice("Статус обновлён.");
    }, current.id);
  }

  function createHold(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected?.subject_user_id) return;
    const current = selected;
    void execute(async () => {
      await api("/admin/legal-holds", {
        method: "POST", headers: adminHeaders(),
        body: JSON.stringify({ subject_user_id: current.subject_user_id, scope: "user", reason_code: holdReason }),
      });
      await loadDetail(current.id);
      setNotice("Удержание зарегистрировано.");
    }, current.id);
  }

  function releaseHold(id: string) {
    void execute(async () => {
      await api(`/admin/legal-holds/${encodeURIComponent(id)}/release`, {
        method: "POST", headers: adminHeaders(),
      });
      if (selected) await loadDetail(selected.id);
      setNotice("Удержание снято.");
    }, selected?.id);
  }

  return <section aria-labelledby="admin-data-subject-title" style={{ minWidth: 0 }}>
    <h2 id="admin-data-subject-title">Запросы по данным</h2>
    <p>Операторская очередь. Просмотр плана удаления не запускает удаление.</p>
    {!verified ? <label>Код 2FA, если сессия ещё не подтверждена
      <input type="password" inputMode="numeric" autoComplete="one-time-code" value={totp}
        onChange={(event) => setTotp(event.target.value)} minLength={6} maxLength={8} />
    </label> : <p>2FA подтверждена для текущей сессии.</p>}
    <label>Статус
      <select value={queueStatus} onChange={(event) => setQueueStatus(event.target.value)}>
        <option value="">Все</option>
        {["pending", "in_review", "needs_info", "approved", "rejected", "completed", "cancelled"].map((value) =>
          <option key={value} value={value}>{dataSubjectStatusLabel(value)}</option>)}
      </select>
    </label>
    <button type="button" disabled={busy || (totp.length > 0 && totp.trim().length < 6)}
      onClick={() => void execute(() => loadList(queueStatus, 0))}>Обновить очередь</button>
    {error ? <p role="alert">{error}</p> : null}
    {notice ? <p role="status">{notice}</p> : null}
    {busy ? <p role="status">Загрузка…</p> : null}
    <p>Всего по фильтру: {total}</p>
    <ul>{items.map((row) => <RequestSummary key={row.id} row={row}
      onOpen={() => void execute(() => loadDetail(row.id))} />)}</ul>
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
      <button type="button" disabled={busy || queueOffset === 0} onClick={() => void execute(() => loadList(queueStatus, Math.max(0, queueOffset - 20)))}>Назад</button>
      <button type="button" disabled={busy || queueOffset + 20 >= total} onClick={() => void execute(() => loadList(queueStatus, queueOffset + 20))}>Далее</button>
    </div>
    {selected ? <section aria-label="Операторская карточка запроса" style={{ overflowWrap: "anywhere" }}>
      <h3>{dataSubjectTypeLabel(selected.request_type)}</h3>
      <p>Статус: {dataSubjectStatusLabel(selected.status)}</p>
      {selected.correction_field ? <p>Поле для исправления: {selected.correction_field}</p> : null}
      {selected.active_hold ? <p>Действует юридическое удержание.</p> : null}
      {status ? <form onSubmit={transition} style={{ display: "grid", gap: 8, maxWidth: 480 }}>
        <label>Новый статус
          <select value={status} onChange={(event) => {
            setStatus(event.target.value);
            setReasonCode(dataSubjectReasonForStatus(event.target.value));
          }}>
            {availableDataSubjectTransitions(selected).map((value) =>
              <option key={value} value={value}>{dataSubjectStatusLabel(value)}</option>) }
          </select>
        </label>
        <label>Код основания решения
          <select value={reasonCode} onChange={(event) => setReasonCode(event.target.value as typeof reasonCode)}>
            {DATA_SUBJECT_REASONS.filter((value) => value === dataSubjectReasonForStatus(status)
              || (status === "rejected" && value === "policy_pending"))
              .map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
        <button type="submit" disabled={busy}>Изменить статус</button>
      </form> : null}
      {selected.request_type === "delete" ? <button type="button" disabled={busy} onClick={() => void execute(async () => {
        setPlan(await api<DataSubjectDeletionPlan>(dataSubjectPath(selected.id, true, "/deletion-plan"), {
          headers: adminHeaders(), cache: "no-store",
        }));
      })}>Показать план удаления</button> : null}
      {plan ? <section aria-label="План удаления">
        <p>{plan.blocked ? "План заблокирован удержанием или другой причиной." : "План доступен только для просмотра."}</p>
        <p>Исполнение удаления через эту страницу недоступно.</p>
        {plan.categories?.length ? <ul>{plan.categories.map((item) =>
          <li key={item.code}>{item.code}: {item.action}
            {typeof item.count === "number" ? ` · записей: ${item.count}` : ""}
          </li>)}</ul> : null}
        {plan.block_reasons?.length ? <p>Причины блокировки: {plan.block_reasons.join(", ")}</p> : null}
      </section> : null}
      <details>
        <summary>Юридическое удержание</summary>
        <p>Действие доступно только оператору с подтверждённым доступом.</p>
        <form onSubmit={createHold} style={{ display: "grid", gap: 8, maxWidth: 480 }}>
          <label>Код основания
            <select value={holdReason} onChange={(event) => setHoldReason(event.target.value as typeof holdReason)}>
              {DATA_SUBJECT_HOLD_REASONS.map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
          <button type="submit" disabled={busy || !selected.subject_user_id || selected.active_hold}>Зарегистрировать удержание</button>
        </form>
        <ul>{holds.map((hold) => <li key={hold.id}>
          {hold.scope} · {hold.reason_code} · {hold.released_at ? "снято" : "действует"}
          {!hold.released_at ? <button type="button" disabled={busy} onClick={() => {
            if (window.confirm("Снять это юридическое удержание?")) releaseHold(hold.id);
          }}>Снять удержание</button> : null}
        </li>)}</ul>
      </details>
    </section> : null}
  </section>;
}

export default function DataSubjectRequests({ mode = "user" }: { mode?: Mode }) {
  return mode === "admin" ? <AdminRequests /> : <UserRequests />;
}
