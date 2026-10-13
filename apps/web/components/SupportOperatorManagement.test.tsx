import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import SupportOperatorManagement, { listSupportOperators, setSupportOperator } from "./SupportOperatorManagement";

test("admin without TOTP sees enrollment guidance instead of role controls", () => {
  const html = renderToStaticMarkup(createElement(SupportOperatorManagement, { totpEnabled: false }));
  assert.match(html, /Для управления ролями настройте TOTP администратора/);
  assert.match(html, /enroll=1/);
  assert.doesNotMatch(html, /Выдать роль оператора/);
});

test("list and role changes use admin endpoint, TOTP header, and exact role payload", async () => {
  const requests: { url: string; init: RequestInit }[] = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input, init) => {
    requests.push({ url: String(input), init: init ?? {} });
    return new Response(JSON.stringify(requests.length === 1
      ? { items: [{ id: "op-1", email: "operator@example.test", totp_enabled: false, email_verified: true }] }
      : { id: "op-1", is_support_operator: requests.length === 2, totp_enabled: false, idempotent: false }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  try {
    const items = await listSupportOperators(" 123456 ");
    assert.equal(items[0].totp_enabled, false);
    const changed = await setSupportOperator(" Operator@Example.Test ", true, " 654321 ");
    assert.equal(changed.is_support_operator, true);
    const revoked = await setSupportOperator("operator@example.test", false, "111222");
    assert.equal(revoked.is_support_operator, false);
    assert.equal(requests.length, 3);
    for (const request of requests) {
      assert.equal(new URL(request.url).pathname, "/admin/support/operators");
      assert.doesNotMatch(request.url, /123456|654321|111222/);
    }
    assert.equal(requests[0].init.method, undefined);
    assert.equal(new Headers(requests[0].init.headers).get("X-Booker-TOTP"), "123456");
    assert.equal(requests[1].init.method, "POST");
    assert.equal(new Headers(requests[1].init.headers).get("X-Booker-TOTP"), "654321");
    assert.deepEqual(JSON.parse(String(requests[1].init.body)), {
      email: "operator@example.test", enabled: true,
    });
    assert.deepEqual(JSON.parse(String(requests[2].init.body)), {
      email: "operator@example.test", enabled: false,
    });
    assert.equal(new Headers(requests[2].init.headers).get("X-Booker-TOTP"), "111222");
  } finally {
    globalThis.fetch = originalFetch;
  }
});
