# Backlog

Deferred items noted for future updates. Nothing here blocks anything.

## Documentation

- [ ] **README entity-id shorthand** (noted 2026-11-11, from PR #4 review): the README
  documents entities with abbreviated IDs (e.g. `sensor.cde_daily_energy_cost`), but real
  entity IDs follow `sensor.cde_lightband_<account>_*`. Anyone pasting a documented ID into
  an automation template gets a nonexistent entity. Fix: add a one-line note near the top of
  the Features section ("all entity IDs follow `sensor.cde_lightband_<account>_*`"), or spell
  the IDs out in every section.

## Hardening (from earlier review passes)

- [ ] **Usage-date skip logs at DEBUG** (from PR #2 review): `fetch_usage_data` skips
  unparseable daily rows silently at DEBUG level. If CDE ever changes their date format
  upstream, every daily row would be dropped and the estimated bill would quietly understate
  with no user-visible signal. Consider a rate-limited WARNING, like the rates-page parse
  failure path.
