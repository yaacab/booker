import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");
const chrome = read("../components/SiteChrome.tsx");
const continuity = read("../app/scene01-continuity.css");
const globals = read("../app/globals.css");

test("SiteChrome header/footer omit surface-glass", () => {
  assert.match(chrome, /<header className="top">/);
  assert.match(chrome, /<footer className="site-footer reference-footer">/);
  assert.doesNotMatch(chrome, /<header className="[^"]*surface-glass/);
  assert.doesNotMatch(chrome, /<footer className="[^"]*surface-glass/);
});

test("cream continuity never paints .top/.site-footer as a plate", () => {
  assert.doesNotMatch(
    continuity,
    /data-booker-theme="cream"[^{]*:is\(\.top,\s*\.bottom-nav/,
  );
  assert.doesNotMatch(
    continuity,
    /data-booker-theme="cream"[^{]*:is\([^)]*\.top[^)]*\.site-footer[^)]*\)[^{]*\{[^}]*background:\s*rgba\(251/,
  );
  assert.match(
    continuity,
    /REGRESSION GUARD[\s\S]*header\.top[\s\S]*background:\s*transparent\s*!important/,
  );
});

test("globals force transparent sticky chrome", () => {
  assert.match(globals, /header\.top[\s\S]*background:\s*transparent\s*!important/);
  assert.match(globals, /footer\.site-footer[\s\S]*background:\s*transparent\s*!important/);
});

test("cream nav never regains a white glass contour", () => {
  assert.match(
    continuity,
    /REGRESSION GUARD: public nav[\s\S]*\.nav-public[\s\S]*border:\s*0\s*!important/,
  );
  assert.match(
    continuity,
    /html\[data-booker-theme="cream"\] \.reference-login a[\s\S]*border:\s*1px solid #d8cbb9\s*!important/,
  );
  assert.doesNotMatch(
    continuity,
    /html\[data-booker-theme="cream"\] \.reference-login a[\s\S]*rgba\(255,\s*255,\s*255/,
  );
});
