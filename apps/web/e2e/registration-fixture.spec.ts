import { test, expect, type APIRequestContext } from "@playwright/test";
import { register } from "./helpers";

test("registration fixture honors Retry-After once without hiding failures", async () => {
  for (const scenario of ["retry", "persistent", "invalid", "too-long", "error"]) {
    let calls = 0;
    const request = {
      get: async () => ({ ok: () => true, json: async () => ({ documents: [] }) }),
      post: async () => {
        calls++;
        const status = scenario === "error" ? 500 : scenario === "retry" && calls === 2 ? 200 : 429;
        return {
          status: () => status, ok: () => status === 200,
          headers: () => ({ "retry-after": scenario === "invalid" ? "bad" : scenario === "too-long" ? "301" : scenario === "retry" ? "61" : "1" }),
          text: async () => "fixture failure",
          json: async () => ({ token: "fixture", user_id: "fixture" }),
        };
      },
    } as unknown as APIRequestContext;
    if (scenario === "retry") {
      expect((await register(request, "fixture@booker.test", "Fixture")).user_id).toBe("fixture");
    } else {
      await expect(register(request, "fixture@booker.test", "Fixture")).rejects.toThrow("register failed");
    }
    expect(calls).toBe(["retry", "persistent"].includes(scenario) ? 2 : 1);
  }
});
