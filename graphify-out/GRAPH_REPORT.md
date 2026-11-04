# Graph Report - ha-cde-lightband  (2026-11-03)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 262 nodes · 493 edges · 13 communities (8 shown, 5 thin omitted)
- Extraction: 87% EXTRACTED · 13% INFERRED · 0% AMBIGUOUS · INFERRED: 63 edges (avg confidence: 0.91)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `2c861479`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- CdeApiClient
- CdeDataUpdateCoordinator
- cde_api.py
- gwt_rpc.py
- CdeUsageRecord
- test_config_flow.py
- steps
- CdeConfigFlow
- manifest.json
- async_setup_entry
- ha-cde-lightband

## God Nodes (most connected - your core abstractions)
1. `CdeDataUpdateCoordinator` - 33 edges
2. `CdeApiClient` - 29 edges
3. `CdeConnectionError` - 15 edges
4. `CdeUsageRecord` - 13 edges
5. `CdeBillingData` - 12 edges
6. `CdeAuthError` - 12 edges
7. `async_setup_entry()` - 11 edges
8. `CdeBaseSensor` - 10 edges
9. `parse_gwt_response()` - 10 edges
10. `build_gwt_payload()` - 9 edges

## Surprising Connections (you probably didn't know these)
- `test_coordinator_update_success()` --uses--> `CdeBillingData`  [INFERRED]
  tests/test_coordinator.py → custom_components/cde_lightband/cde_api.py
- `test_sensors_created_and_updated()` --uses--> `CdeBillingData`  [INFERRED]
  tests/test_sensor.py → custom_components/cde_lightband/cde_api.py
- `test_invalid_auth_error()` --uses--> `CdeAuthError`  [INFERRED]
  tests/test_config_flow.py → custom_components/cde_lightband/exceptions.py
- `test_cannot_connect_error()` --uses--> `CdeConnectionError`  [INFERRED]
  tests/test_config_flow.py → custom_components/cde_lightband/exceptions.py
- `test_coordinator_update_failure_raises_update_failed()` --uses--> `CdeConnectionError`  [INFERRED]
  tests/test_coordinator.py → custom_components/cde_lightband/exceptions.py

## Import Cycles
- None detected.

## Communities (13 total, 5 thin omitted)

### Community 0 - "CdeApiClient"
Cohesion: 0.08
Nodes (14): CdeApiClient, _do_post(), CdeBillingData, _parse_date(), CdeAuthError, CdeConnectionError, CdeDataError, CdeError (+6 more)

### Community 1 - "CdeDataUpdateCoordinator"
Cohesion: 0.07
Nodes (8): CdeDataUpdateCoordinator, async_setup_entry(), CdeBalanceDueSensor, CdeBaseSensor, CdeDailyEnergySensor, CdeLastBillSensor, CdeLastPaymentSensor, CdePaymentDueDateSensor

### Community 3 - "gwt_rpc.py"
Cohesion: 0.11
Nodes (11): build_gwt_json_data_payload(), build_gwt_payload(), escape_gwt_string(), parse_gwt_response(), test_build_gwt_payload_structure(), test_build_gwt_payload_zero_params(), test_parse_gwt_ex_response(), test_parse_gwt_invalid_response() (+3 more)

### Community 4 - "CdeUsageRecord"
Cohesion: 0.12
Nodes (5): CdeUsageRecord, test_coordinator_update_failure_raises_update_failed(), test_coordinator_update_success(), test_sync_statistics_incremental_ingestion(), test_sensors_created_and_updated()

### Community 5 - "test_config_flow.py"
Cohesion: 0.15
Nodes (6): auto_enable_custom_integrations(), test_cannot_connect_error(), test_form_displayed(), test_invalid_auth_error(), test_options_flow(), test_successful_config_entry()

### Community 6 - "steps"
Cohesion: 0.12
Nodes (16): jobs, validate, name, on, pull_request, push, branches, branches (+8 more)

### Community 8 - "manifest.json"
Cohesion: 0.15
Nodes (12): after_dependencies, categories, codeowners, config_flow, documentation, domain, integration_type, iot_class (+4 more)

### Community 9 - "async_setup_entry"
Cohesion: 0.36
Nodes (3): async_setup_entry(), async_unload_entry(), update_listener()

## Knowledge Gaps
- **1 isolated node(s):** `ha-cde-lightband`
  These have ≤1 connection - possible missing edges. (Counts symbols only; 127 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `CdeDataUpdateCoordinator` connect `CdeDataUpdateCoordinator` to `CdeApiClient`, `async_setup_entry`, `cde_api.py`, `CdeUsageRecord`?**
  _High betweenness centrality (0.238) - this node is a cross-community bridge._
- **Are the 14 inferred relationships involving `CdeDataUpdateCoordinator` (e.g. with `CdeApiClient` and `CdeBillingData`) actually correct?**
  _`CdeDataUpdateCoordinator` has 14 INFERRED edges - model-reasoned connections that need verification._
- **What connects `ha-cde-lightband` to the rest of the system?**
  _1 weakly-connected nodes found - possible missing edges._
- **Should `CdeApiClient` be split into smaller, more focused modules?**
  _Cohesion score 0.08418367346938775 - nodes in this community are weakly interconnected._
- **Why does `CdeApiClient` connect `CdeApiClient` to `CdeDataUpdateCoordinator`, `cde_api.py`, `CdeConfigFlow`?**
  _High betweenness centrality (0.185) - this node is a cross-community bridge._
- **Are the 10 inferred relationships involving `CdeApiClient` (e.g. with `CdeAuthError` and `CdeConnectionError`) actually correct?**
  _`CdeApiClient` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Should `CdeDataUpdateCoordinator` be split into smaller, more focused modules?**
  _Cohesion score 0.06567992599444958 - nodes in this community are weakly interconnected._