import assert from "node:assert/strict";
import test from "node:test";
import DevCabinetsPage from "../app/dev/cabinets/page.tsx";

test("dev cabinets returns 404 when the demo gateway is disabled", () => {
  const previous = process.env.BOOKER_DEMO_GATEWAY;
  delete process.env.BOOKER_DEMO_GATEWAY;

  try {
    assert.throws(
      () => DevCabinetsPage(),
      (error: unknown) =>
        error instanceof Error &&
        "digest" in error &&
        error.digest === "NEXT_HTTP_ERROR_FALLBACK;404",
    );
  } finally {
    if (previous === undefined) delete process.env.BOOKER_DEMO_GATEWAY;
    else process.env.BOOKER_DEMO_GATEWAY = previous;
  }
});
