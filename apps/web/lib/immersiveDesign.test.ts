import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");
const theme = read("../app/immersive.css");
const studio = read("../components/event-studio/event-studio-map.css");
const home = read("../app/page.tsx");
const hero = read("../components/ReferencePuzzleHero.tsx");
const puzzles = read("../app/reference-puzzles.css");
const token = (css: string, name: string) => {
  const value = css.match(new RegExp(`${name}:\\s*(#[a-fA-F0-9]{6})\\s*;`))?.[1];
  assert.ok(value, `Missing token ${name}`);
  return value;
};
const luminance = (hex: string) => {
  const channels = [1, 3, 5].map((start) => {
    const c = parseInt(hex.slice(start, start + 2), 16) / 255;
    return c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4;
  });
  return channels[0] * .2126 + channels[1] * .7152 + channels[2] * .0722;
};
const contrast = (a: string, b: string) => {
  const x = luminance(a), y = luminance(b);
  return (Math.max(x, y) + .05) / (Math.min(x, y) + .05);
};

test("light reference theme text and hover tokens have readable contrast", () => {
  for (const foreground of ["--ink", "--muted", "--brand-dark"]) {
    for (const background of ["--canvas", "--surface", "--surface-2"]) {
      assert.ok(contrast(token(theme, foreground), token(theme, background)) >= 4.5, `${foreground} / ${background}`);
    }
  }
  assert.ok(contrast("#ffffff", token(theme, "--brand-hover")) >= 4.5);
});

test("studio text and form fields remain readable", () => {
  assert.ok(contrast(token(studio, "--es-ink"), token(studio, "--es-paper")) >= 4.5);
  assert.ok(contrast(token(studio, "--es-muted"), token(studio, "--es-paper")) >= 4.5);
  assert.match(studio, /\.event-studio-shell :is\(input, select\)[^}]*background: #ffffff[^}]*color: var\(--es-ink\)/);
  assert.match(studio, /\.stage-rail button[^}]*min-height: 52px/);
});

test("home offers direct search and assembly while keeping the classic wizard", () => {
  const home = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");
  assert.ok(home.includes('/search?kind=artist'));
  assert.ok(home.includes('/assemble'));
  const assembly = readFileSync(new URL("../app/assemble/page.tsx", import.meta.url), "utf8");
  assert.ok(assembly.includes('/events/new?event_studio_map_v1=1'));
});

test("studio never assigns reference portraits or venue photos to real suppliers", () => {
  const component = read("../components/event-studio/EventStudioMap.tsx");
  assert.doesNotMatch(component, /reference-portrait|portrait-\$|className="venue-visual"/);
  assert.match(component, /talent-initials/);
  assert.match(component, /item.initials/);
  assert.doesNotMatch(component, /<img|<Image/);
});

test("motion styles include a reduced-motion alternative", () => {
  assert.match(theme, /prefers-reduced-motion: reduce/);
  assert.match(studio, /prefers-reduced-motion: reduce/);
  assert.match(puzzles, /prefers-reduced-motion: reduce/);
});

test("reference puzzles are accessible local toggles, not booking actions", () => {
  assert.match(hero, /aria-pressed=\{selected === piece.id\}/);
  assert.match(hero, /current === id \? null : id/);
  assert.match(hero, /event.key === "Escape"/);
  assert.match(hero, /Образы категорий, не реальные предложения/);
  assert.doesNotMatch(hero, /\bfetch\(|\bapi\(|localStorage/);
  assert.match(puzzles, /translateY\(-20px\)/);
});

test("internal pages share the workspace skin without restyling the home", () => {
  const layout = read("../app/layout.tsx");
  const chrome = read("../components/SiteChrome.tsx");
  const workspace = read("../app/workspace-design.css");
  assert.match(layout, /import "\.\/workspace-design.css"/);
  assert.match(chrome, /className="site-content" data-section=/);
  assert.match(workspace, /:not\(\[data-section="home"\]\)/);
  assert.match(workspace, /prefers-reduced-motion:reduce/);
  assert.match(workspace, /\.deal-head :is\(h1,a\).*color: #243b2e/);
});
test("supplier profiles retain booking, favorite and sharing actions", () => {
  for (const file of ["ArtistProfileClient.tsx", "VenueProfileClient.tsx"]) {
    const source = read("../components/" + file);
    assert.match(source, /id="profile-booking"/);
    assert.match(source, /<FavoriteToggle/);
    assert.match(source, /Поделиться/);
  }
});
