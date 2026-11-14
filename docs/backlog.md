# Backlog

Deferred items noted for future updates. Nothing here blocks anything.

## Hardening (from earlier review passes)

- [ ] **Usage-date skip logs at DEBUG** (from PR #2 review): `fetch_usage_data` skips
  unparseable daily rows silently at DEBUG level. If CDE ever changes their date format
  upstream, every daily row would be dropped and the estimated bill would quietly understate
  with no user-visible signal. Consider a rate-limited WARNING, like the rates-page parse
  failure path.
