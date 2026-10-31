# UI chrome: no glass plate

**Статус:** обязательный guard для header/footer на cream.

## Правило

- `header.top` и `footer.site-footer` сидят на фоне страницы **без** плашки `surface-glass` / rgba cream plate.
- В `SiteChrome.tsx`: `className="top"` и `className="site-footer reference-footer"` — **без** `surface-glass`.
- В `scene01-continuity.css` **запрещено** возвращать `.top` / `.site-footer` в селектор вида  
  `html[data-booker-theme="cream"] :is(.top, .bottom-nav, .workspace-sidebar, .site-footer) { background: rgba(...) }`.
- Kill-switch **вне** `@layer` + unit `apps/web/lib/chromeNoPlate.test.ts`.

## Чеклист перед UI-коммитом на login/register

1. Header без фона/blur/border-plate.
2. Footer без той же плашки.
3. `p.role-picked` на register с выбранной ролью не дублирует карточку роли.
4. `nav.nav-public` без белого контура-контейнера.
5. Локально: `node --test apps/web/lib/chromeNoPlate.test.ts`.

## Превью на bukergo.ru

Пока web не задеплоен, прод отдаёт старый CSS: после refresh CDP-правки пропадают. Это **не** значит, что репо откатило фикс — сверяй SHA ветки `sync/live-canonical-20261031`, не только живой домен.
