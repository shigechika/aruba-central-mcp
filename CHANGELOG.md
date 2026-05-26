# Changelog

## [0.3.0](https://github.com/shigechika/aruba-central-mcp/releases/tag/v0.3.0) - 2026-05-26

### Features

* add `daily_brief` tool for AP health check by site ([#3](https://github.com/shigechika/aruba-central-mcp/pull/3))
* add `get_clients_trend` tool for client count trend over time
* add `get_client_mobility_trail` tool for roaming history
* add `get_top_clients_by_usage` tool

### Bug Fixes

* `get_ap_throughput`: handle both `tx`/`txBytes` field variants

## [0.2.0] - Initial public release

* 13 tools covering APs, switches, clients, radios, BSSIDs, WLANs, swarms, site summary, top APs
