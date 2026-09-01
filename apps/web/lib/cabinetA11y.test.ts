import assert from "node:assert/strict";
import test from "node:test";
import { cabinetWidgetHeadingId } from "./cabinetA11y";

test("cabinetWidgetHeadingId slugifies Cyrillic titles", () => {
  assert.equal(cabinetWidgetHeadingId("Новые заявки"), "cabinet-widget-новые-заявки");
  assert.equal(cabinetWidgetHeadingId("Hold"), "cabinet-widget-hold");
  assert.equal(cabinetWidgetHeadingId("  Истекающие hold  "), "cabinet-widget-истекающие-hold");
});

test("cabinetWidgetHeadingId falls back for empty titles", () => {
  assert.equal(cabinetWidgetHeadingId("---"), "cabinet-widget-section");
});
