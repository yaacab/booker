import test from "node:test";
import assert from "node:assert/strict";
import { SESSION_CHANGED_EVENT, setActiveOrg, setToken } from "./api";

test("session setters notify this tab once per actual token or organization change", () => {
  const oldWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
  const oldStorage = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  const values = new Map<string, string>();
  const local = {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value); },
    removeItem: (key: string) => { values.delete(key); },
  };
  const browser = new EventTarget();
  let notifications = 0;
  browser.addEventListener(SESSION_CHANGED_EVENT, () => { notifications += 1; });
  Object.defineProperty(globalThis, "window", { configurable: true, value: browser });
  Object.defineProperty(globalThis, "localStorage", { configurable: true, value: local });

  try {
    setToken("account-a");
    setToken("account-a");
    setActiveOrg("org-a");
    setActiveOrg("org-a");
    assert.equal(notifications, 2);

    setActiveOrg("org-b");
    setToken("account-b");
    assert.equal(notifications, 4);

    setToken(null);
    assert.equal(notifications, 5);
    assert.equal(local.getItem("booker.org"), null);
    setToken(null);
    assert.equal(notifications, 5);
  } finally {
    if (oldWindow) Object.defineProperty(globalThis, "window", oldWindow);
    else Reflect.deleteProperty(globalThis, "window");
    if (oldStorage) Object.defineProperty(globalThis, "localStorage", oldStorage);
    else Reflect.deleteProperty(globalThis, "localStorage");
  }
});
