import test from "node:test";
import assert from "node:assert/strict";
import { ApiError } from "./api";
import { eventCommandError, eventCommandKey } from "./eventCommands";

test("a retry keeps its key; changed selection creates a different command", async () => {
  const payload = { title: "Корпоратив", artistIds: ["one"] };
  const first = await eventCommandKey("browser-seed", payload);
  assert.equal(first, await eventCommandKey("browser-seed", payload));
  assert.match(first, /^[a-f0-9]{64}$/);
  assert.notEqual(first, await eventCommandKey("browser-seed", { ...payload, artistIds: ["two"] }));
});

test("validation responses never print backend input bodies in the event UI", () => {
  const error = new ApiError('{"detail":[{"input":"private-input","type":"int_type"}]}', 422);
  assert.match(eventCommandError(error), /Проверьте дату/);
  assert.doesNotMatch(eventCommandError(error), /private-input|int_type/);
  assert.match(eventCommandError(new Error("Failed to fetch")), /Повторите попытку/);
  assert.equal(eventCommandError(new ApiError("Нет доступа", 403)), "Нет доступа");
});
