# Changelog

## [0.7.1](https://github.com/shigechika/aruba-central-mcp/compare/v0.7.0...v0.7.1) (2026-08-11)


### Bug Fixes

* add explicit workflow permissions to test.yml and release.yml ([#55](https://github.com/shigechika/aruba-central-mcp/issues/55)) ([df62c74](https://github.com/shigechika/aruba-central-mcp/commit/df62c74de7d6498ee0d690207fd9ad7348b0c6e3))

## [0.7.0](https://github.com/shigechika/aruba-central-mcp/compare/v0.6.4...v0.7.0) (2026-08-08)


### Features

* add pr-gate.yml admission control caller ([#53](https://github.com/shigechika/aruba-central-mcp/issues/53)) ([1d12349](https://github.com/shigechika/aruba-central-mcp/commit/1d12349e438a38506ff13026bf9144036f48f499))

## [0.6.4](https://github.com/shigechika/aruba-central-mcp/compare/v0.6.3...v0.6.4) (2026-08-06)


### Bug Fixes

* **deps:** ignore mcp major version updates in Dependabot ([#49](https://github.com/shigechika/aruba-central-mcp/issues/49)) ([5fb1b27](https://github.com/shigechika/aruba-central-mcp/commit/5fb1b271a09242093c943bed787f3f34fb1204f0))

## [0.6.3](https://github.com/shigechika/aruba-central-mcp/compare/v0.6.2...v0.6.3) (2026-07-31)


### Bug Fixes

* **deps:** cap the MCP SDK below v2 ([#44](https://github.com/shigechika/aruba-central-mcp/issues/44)) ([8548072](https://github.com/shigechika/aruba-central-mcp/commit/85480725b248c4d599bfb9564ad63e7a8e581626))

## [0.6.2](https://github.com/shigechika/aruba-central-mcp/compare/v0.6.1...v0.6.2) (2026-07-27)


### Bug Fixes

* **ci:** read AI-review guidance from the base revision, drop the checkout ([#41](https://github.com/shigechika/aruba-central-mcp/issues/41)) ([3ee7c26](https://github.com/shigechika/aruba-central-mcp/commit/3ee7c26c8dcb7d7bf775fc0aafb147456f1eab4d))
* sync the smoke-test engine ([#39](https://github.com/shigechika/aruba-central-mcp/issues/39)) ([81b5e62](https://github.com/shigechika/aruba-central-mcp/commit/81b5e62764264c908b6fa799bf22558772780a6d))

## [0.6.1](https://github.com/shigechika/aruba-central-mcp/compare/v0.6.0...v0.6.1) (2026-07-26)


### Bug Fixes

* refuse the answer daily_brief gives when the backend is dead ([#34](https://github.com/shigechika/aruba-central-mcp/issues/34)) ([afb8214](https://github.com/shigechika/aruba-central-mcp/commit/afb8214e161c5d0c8910154e14e3653152c3460b))

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
