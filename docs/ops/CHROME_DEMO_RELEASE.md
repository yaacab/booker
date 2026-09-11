# Chrome editions and development cabinets

Two editions are stored in `booker.edition`. `/assemble` creates a saved brief and passes it to the existing studio. Location filters are applied to venues, never inferred for artists. The map uses locally hosted Leaflet 1.9.4 and attributed OSM tiles; geocoding is explicit, cached and throttled.

## Isolated demo

`booker-demo-api.service` uses its own Unix user, SQLite database and uploads under `/var/lib/booker-demo`, binds only to 127.0.0.1:8031, and has no access to production data or configuration. All external notifications are disabled; payments use the stub provider. Seed only this database with `BOOKER_ALLOW_DEMO_SEED=1`. Never run a demo seed against production.

Web gateway routes return 404 unless `BOOKER_DEMO_GATEWAY=1` is set on the private development web service. Never enable this flag on the public booker-web service. `/dev/cabinets` opens customer, performer, venue and operator roles using existing seeded test accounts. Tokens are kept in sessionStorage, isolated from real tokens and organization selection. Demo drafts use sessionStorage as well. Test data is shared and must not contain personal information.

The private web service binds to 127.0.0.1:3032 and is accessed through an SSH tunnel. To disable development access, stop booker-demo-web and booker-demo-api. No rebuild is needed. Existing production authentication is unchanged.

## Checks

Frontend unit tests and production build; catalog district/metro and authorization tests; all four demo tokens must return 401 from production `/me`.
