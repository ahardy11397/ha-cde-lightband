# Graph Report - ha-cde-lightband  (2026-11-14)

## Corpus Check
- 25 files · ~17,720 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 2 file(s) not represented in the graph (top: (none) 2)

## Summary
- 406 nodes · 819 edges · 16 communities (11 shown, 5 thin omitted)
- Extraction: 87% EXTRACTED · 13% INFERRED · 0% AMBIGUOUS · INFERRED: 110 edges (avg confidence: 0.91)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `4c5dfee4`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- CdeApiClient & API Tests
- Coordinator & Sensor Entities
- Integration Lifecycle & Constants
- GWT-RPC Protocol & Date Parsing
- Billing, Usage & Coordinator Tests
- Exceptions & Config Flow Tests
- Validate Workflow (CI)
- Config & Options Flow
- Integration Manifest
- Sensor & Cost Tests
- Repository Root
- Rate Scraping & Parsing
- Release Workflow (CD)

## God Nodes (most connected - your core abstractions)
1. `CdeDataUpdateCoordinator` - 49 edges
2. `CdeApiClient` - 39 edges
3. `CdeAuthError` - 17 edges
4. `CdeBillingData` - 16 edges
5. `CdeRateData` - 16 edges
6. `CdeConnectionError` - 16 edges
7. `CdeUsageRecord` - 15 edges
8. `async_setup_entry()` - 13 edges
9. `_setup_integration()` - 13 edges
10. `parse_rates_html()` - 12 edges

## Surprising Connections (you probably didn't know these)
- `test_fetch_billing_data_parses_fields()` --uses--> `CdeBillingData`  [INFERRED]
  tests/test_cde_api.py → custom_components/cde_lightband/cde_api.py
- `test_sensors_created_and_updated()` --uses--> `CdeBillingData`  [INFERRED]
  tests/test_sensor.py → custom_components/cde_lightband/cde_api.py
- `test_sensors_created_and_updated()` --uses--> `CdeUsageRecord`  [INFERRED]
  tests/test_sensor.py → custom_components/cde_lightband/cde_api.py
- `test_coordinator_stores_rates_and_internet_price()` --uses--> `CdeRateData`  [INFERRED]
  tests/test_coordinator.py → custom_components/cde_lightband/cde_api.py
- `test_rates_scrape_failure_keeps_last_known_rates()` --uses--> `CdeRateData`  [INFERRED]
  tests/test_coordinator.py → custom_components/cde_lightband/cde_api.py

## Import Cycles
- None detected.

## Communities (16 total, 5 thin omitted)

### Community 0 - "CdeApiClient & API Tests"
Cohesion: 0.07
Nodes (21): CdeApiClient, _do_post(), CdeConnectionError, _FakeResponse, _FakeSession, _mock_session(), test_auth_failure_raises_cde_auth_error(), test_auth_success() (+13 more)

### Community 1 - "Coordinator & Sensor Entities"
Cohesion: 0.06
Nodes (10): CdeDataUpdateCoordinator, async_setup_entry(), CdeBalanceDueSensor, CdeBaseSensor, CdeDailyEnergyCostSensor, CdeDailyEnergySensor, CdeEstimatedBillSensor, CdeLastBillSensor (+2 more)

### Community 2 - "Integration Lifecycle & Constants"
Cohesion: 0.08
Nodes (6): CdeAuthError, CdeDataError, CdeError, async_setup_entry(), async_unload_entry(), update_listener()

### Community 3 - "GWT-RPC Protocol & Date Parsing"
Cohesion: 0.09
Nodes (13): _parse_date(), _parse_timestamp(), build_gwt_json_data_payload(), build_gwt_payload(), escape_gwt_string(), parse_gwt_response(), test_build_gwt_payload_structure(), test_build_gwt_payload_zero_params() (+5 more)

### Community 4 - "Billing, Usage & Coordinator Tests"
Cohesion: 0.09
Nodes (12): CdeBillingData, CdeUsageRecord, auto_enable_custom_integrations(), _rates_entry(), test_coordinator_auth_error_raises_config_entry_auth_failed(), test_coordinator_stores_rates_and_internet_price(), test_coordinator_update_failure_raises_update_failed(), test_coordinator_update_success() (+4 more)

### Community 5 - "Exceptions & Config Flow Tests"
Cohesion: 0.14
Nodes (9): test_cannot_connect_error(), test_form_displayed(), test_invalid_auth_error(), test_options_flow(), test_options_flow_includes_internet_plan(), test_reauth_cannot_connect(), test_reauth_invalid_auth(), test_reauth_successful() (+1 more)

### Community 6 - "Validate Workflow (CI)"
Cohesion: 0.08
Nodes (26): GH_TOKEN, outputs, runs-on, steps, jobs, gate, validate, name (+18 more)

### Community 8 - "Integration Manifest"
Cohesion: 0.15
Nodes (12): after_dependencies, categories, codeowners, config_flow, documentation, domain, integration_type, iot_class (+4 more)

### Community 9 - "Sensor & Cost Tests"
Cohesion: 0.15
Nodes (12): _setup_integration(), test_daily_energy_cost_sensor_computes_cost(), test_daily_energy_cost_unknown_without_rates(), test_daily_energy_cost_unknown_without_usage(), test_daily_energy_cost_uses_most_recent_record(), test_estimated_bill_sensor_computes_estimate(), test_estimated_bill_sensor_without_internet(), test_estimated_bill_unknown_at_month_start() (+4 more)

### Community 13 - "Rate Scraping & Parsing"
Cohesion: 0.11
Nodes (12): CdeRateData, parse_internet_prices_html(), parse_rates_html(), _rates_section_with_preceding_note_row(), test_grid_access_charge_tiers(), test_parse_internet_prices_html(), test_parse_internet_prices_html_garbage_returns_none(), test_parse_rates_html_extracts_residential_table() (+4 more)

### Community 14 - "Release Workflow (CD)"
Cohesion: 0.10
Nodes (20): GH_TOKEN, TAG, jobs, release, name, on, push, permissions (+12 more)

## Knowledge Gaps
- **1 isolated node(s):** `ha-cde-lightband`
  These have ≤1 connection - possible missing edges. (Counts symbols only; 187 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `CdeDataUpdateCoordinator` connect `Coordinator & Sensor Entities` to `CdeApiClient & API Tests`, `Integration Lifecycle & Constants`, `Billing, Usage & Coordinator Tests`, `Sensor & Cost Tests`, `Rate Scraping & Parsing`, `Coordinator Initialization`?**
  _High betweenness centrality (0.237) - this node is a cross-community bridge._
- **Are the 24 inferred relationships involving `CdeDataUpdateCoordinator` (e.g. with `CdeApiClient` and `CdeBillingData`) actually correct?**
  _`CdeDataUpdateCoordinator` has 24 INFERRED edges - model-reasoned connections that need verification._
- **What connects `ha-cde-lightband` to the rest of the system?**
  _1 weakly-connected nodes found - possible missing edges._
- **Should `CdeApiClient & API Tests` be split into smaller, more focused modules?**
  _Cohesion score 0.07297726070861978 - nodes in this community are weakly interconnected._
- **Why does `CdeApiClient` connect `CdeApiClient & API Tests` to `Coordinator & Sensor Entities`, `Integration Lifecycle & Constants`, `GWT-RPC Protocol & Date Parsing`, `Billing, Usage & Coordinator Tests`, `Config & Options Flow`, `Coordinator Initialization`?**
  _High betweenness centrality (0.154) - this node is a cross-community bridge._
- **Are the 17 inferred relationships involving `CdeApiClient` (e.g. with `CdeAuthError` and `CdeConnectionError`) actually correct?**
  _`CdeApiClient` has 17 INFERRED edges - model-reasoned connections that need verification._
- **Should `Coordinator & Sensor Entities` be split into smaller, more focused modules?**
  _Cohesion score 0.06291591046581972 - nodes in this community are weakly interconnected._