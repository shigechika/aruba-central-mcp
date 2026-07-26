# Changelog

## [0.6.0](https://github.com/shigechika/aruba-central-mcp/compare/v0.5.3...v0.6.0) (2026-07-26)


### Features

* live smoke test that exercises every registered tool ([#33](https://github.com/shigechika/aruba-central-mcp/issues/33)) ([67cea71](https://github.com/shigechika/aruba-central-mcp/commit/67cea71a993affb27e4501588903703cc590da62))


### Bug Fixes

* request a page size the mobility-trail endpoint accepts ([#31](https://github.com/shigechika/aruba-central-mcp/issues/31)) ([7260e56](https://github.com/shigechika/aruba-central-mcp/commit/7260e5681103ccf870c796d6a23280065a1041c1))

## [0.5.3](https://github.com/shigechika/aruba-central-mcp/compare/v0.5.2...v0.5.3) (2026-07-12)


### Bug Fixes

* escape OData literals and validate MAC/serial path segments ([#21](https://github.com/shigechika/aruba-central-mcp/issues/21)) ([911e202](https://github.com/shigechika/aruba-central-mcp/commit/911e20282c782adc34769a7ad94611a26ae0d442))

## [0.5.2](https://github.com/shigechika/aruba-central-mcp/compare/v0.5.1...v0.5.2) (2026-07-12)


### Documentation

* correct tool count and document __main__.py + interpolation surface ([#16](https://github.com/shigechika/aruba-central-mcp/issues/16)) ([4a90bb7](https://github.com/shigechika/aruba-central-mcp/commit/4a90bb7f1484d98c9581431ee5c0f037d49fb72c))

## [0.5.1](https://github.com/shigechika/aruba-central-mcp/compare/v0.5.0...v0.5.1) (2026-07-06)


### Documentation

* add repository custom instructions for Copilot code review ([#11](https://github.com/shigechika/aruba-central-mcp/issues/11)) ([64a88df](https://github.com/shigechika/aruba-central-mcp/commit/64a88df7e597b57f403be9f55426e655c69fea2c))

## [0.5.0](https://github.com/shigechika/aruba-central-mcp/compare/v0.4.1...v0.5.0) (2026-06-18)


### Features

* add health_check MCP tool ([#8](https://github.com/shigechika/aruba-central-mcp/issues/8)) ([ecabc58](https://github.com/shigechika/aruba-central-mcp/commit/ecabc5838388604eb7169ff42cb705f8750743bb))

## [0.4.1](https://github.com/shigechika/aruba-central-mcp/compare/v0.4.0...v0.4.1) (2026-05-26)


### Bug Fixes

* add GH_REPO env to gh release upload ([#6](https://github.com/shigechika/aruba-central-mcp/issues/6)) ([97e507f](https://github.com/shigechika/aruba-central-mcp/commit/97e507f801f04b99a1c05f7a92e5d5968093b673))

## [0.4.0](https://github.com/shigechika/aruba-central-mcp/compare/v0.3.0...v0.4.0) (2026-05-26)


### Features

* add daily_brief tool for AP health check by site ([#3](https://github.com/shigechika/aruba-central-mcp/issues/3)) ([b91ed09](https://github.com/shigechika/aruba-central-mcp/commit/b91ed09987e727524a1c312734512f45128ca879))

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
