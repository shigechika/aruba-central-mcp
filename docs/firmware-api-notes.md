# Firmware API notes (New Central and Classic Central)

Working notes behind `firmware_status` / `firmware_versions` and the planned
upgrade tool. Each fact says where it came from. "Not confirmed" means the
published reference does not say, and nothing here was guessed to fill the gap.
Sources were read on 2026-10-24.

## Which API sees what

| Need | New Central (GreenLake SSO, the token this server already uses) | Classic Central (API gateway OAuth) |
|---|---|---|
| Running version per AP | yes, `/network-services/v1/firmware-details` and `/network-monitoring/v1/aps` | yes, per swarm, `/firmware/v1/swarms` |
| Recommended version | yes, `recommendedVersion` per device | yes, `recommended` per swarm |
| Upgrade status | a per-device string `upgradeStatus` (values not enumerated) | per swarm `status.state` + `status.reason` + `firmware_scheduled_at` |
| Why an upgrade failed | not documented | `status.reason` ("Description of specific state") |
| Group of a device | `deviceGroupName` on `/network-monitoring/v1/aps` (not filterable server-side) | `group` query filter on `/firmware/v1/swarms` |
| Site of a device | `siteName` (filterable server-side, `eq`/`in`) | not in the firmware responses |
| Swarm (cluster) of an AP | `clusterId` / `clusterName` on `/network-monitoring/v1/aps` (filterable) | `swarm_id` / `swarm_name` |
| Group compliance version | not documented | `/firmware/v1/upgrade/compliance_version` |
| Versions offered | not documented | `/firmware/v1/versions` |
| Start an upgrade of AOS-8 Instant APs | no documented endpoint (the "Live Upgrade" read endpoints carry AOS-10 examples) | `POST /firmware/v1/upgrade` |

Choice: `firmware_status` reads New Central first, with the token the server
already has, so it works with no extra setup and filters by group, site and
swarm. Classic is optional and adds what only it reports (state with reason,
compliance, offered versions); the upgrade tool (phase 2) needs Classic,
because New Central documents no upgrade call for AOS-8 Instant APs.

## New Central

Base: the GreenLake API gateway (`ARUBA_CENTRAL_BASE_URL`); token from
`https://sso.common.cloud.hpe.com/as/token.oauth2` (client credentials), as the
rest of this server. Specs: developer.arubanetworks.com/new-central reference
(`getfirmwaredetailslistv1`, `getaccesspointsv1`, `getswarmsv1`,
`listdeviceliveupgradesv1`, `listapliveupgradesv1`), fetched as OpenAPI.

### `GET /network-services/v1/firmware-details`

"Retrieves list of device's firmware details such as firmware version, upgrade
status, recommended version, firmware classification and last upgraded timestamp."

- Query: `filter` (OData, `and` only; fields `siteId`, `siteName`,
  `serialNumber`, `deviceName`, `deviceType`, `upgradeStatus`,
  `firmwareClassification`, `firmwareVersion`; operators `eq` and `in`),
  `sort`, `limit` (max 1000), `next` (page cursor).
- Item fields (all marked required): `serialNumber`, `deviceName`,
  `recommendedVersion`, `upgradeStatus`, `firmwareClassification`,
  `lastUpgradedTimeAt`, `deviceType` (`ACCESS_POINT` / `SWITCH` / `GATEWAY`),
  `siteId`, `siteName`, `id`, `type`, `firmwareVersion`.
- The spec's example item is an AP on `8.5.2.0_59123` with
  `recommendedVersion` `8.6.0.6_77023` and `upgradeStatus` "Up To Date", so
  AOS-8 devices appear in it. The full set of `upgradeStatus` values is not
  enumerated. No group, no swarm, no failure reason.

### `GET /network-monitoring/v1/aps` and `/network-monitoring/v1/swarms`

- `aps` filter fields: `siteId`, `siteName`, `serialNumber`, `deviceName`,
  `status`, `model`, `firmwareVersion`, `deployment`, `clusterId`,
  `clusterName`, `hibernate`. The item also carries `deviceGroupName` (read by
  `get_ap_status`), which is not a filter field.
- `swarms` filter fields: `siteId`, `siteName`, `clusterId`, `clusterName`,
  `conductorSerialNumber`, `conductorDeviceName`, `firmwareVersion`.
- OData `eq` is an exact, case-sensitive match. `firmware_status` therefore
  reads all APs and filters client-side, case-insensitively, by
  `deviceGroupName`, `siteName` and `clusterName`.

### Live upgrade (read-only)

`GET /network-services/v1/device-live-upgrades` (needs `serial-numbers` or
`scope-id`; optional `start-at`, `end-at`, `history`) returns per-device
upgrades with `status` in `NOT_STARTED`, `IMAGE_DOWNLOAD_REQUESTED`,
`IMAGE_DOWNLOAD_IN_PROGRESS`, `IMAGE_DOWNLOAD_COMPLETED`,
`IMAGE_DOWNLOAD_FAILED`, `IMAGE_DOWNLOAD_FAILED_PERMANENTLY`,
`UPDATING_BOOT_PARTITION`, `BOOT_PARTITION_UPDATED`,
`BOOT_PARTITION_UPDATE_FAILED`, `REBOOT_REQUESTED`, `REBOOTING`,
`REBOOT_COMPLETED`, `FAILED`, `ABORTED`. The examples are AOS-10
(`10.5.0.1_81234`) and the description ties them to "the config scope at
which they were triggered", i.e. upgrades started from New Central. Not
confirmed whether an upgrade started from Classic Central for an AOS-8 swarm
appears here. Not used yet.

### Is a group "New Central-enabled"?

Not confirmed. The Classic upgrade dialog warns that devices in New
Central-enabled groups must be upgraded from New Central and that the Classic
upgrade fails for them, but no reference page found here exposes that flag:
neither the New Central AP/swarm/firmware items nor the Classic firmware
responses carry it. Classic group properties (`AllowedDevTypes`,
`Architecture` Instant/AOS10, `ApNetworkRole`, seen in Classic group-creation
examples) are documented; a New Central compatibility property is mentioned
only by a third-party CLI (`cnx`), not in the Classic reference. Practical
check until then: start an upgrade from Classic and read the swarm's
`status.state` / `status.reason` with `firmware_status` (Classic configured),
or compare a group's devices against New Central's firmware management page.

## Classic Central

Base: the Classic API gateway, `https://apigw-<region>.central.arubanetworks.com`
(per account). Specs: developer.arubanetworks.com/central reference pages
`apifirmware*`, fetched as OpenAPI, plus aruba/pycentral `firmware_management.py`
and `url_utils.FirmwareManagementUrl`.

### OAuth (access-token-management, api-oauth-access-token docs)

- Refresh: `POST <gateway>/oauth2/token` with query parameters `client_id`,
  `client_secret`, `grant_type=refresh_token`, `refresh_token`.
- Response: `access_token`, `refresh_token` (use the new one next time; the
  old one is replaced), `token_type` (`bearer`), `expires_in` (7200 in the example).
- The refresh token's own lifetime is not documented. Generating a token by
  login / authorization code is limited to one per client id every 30 minutes;
  the docs recommend refreshing instead. One Central On-Prem help page says a
  token can be refreshed only every 15 minutes (single source, not confirmed
  for the cloud).
- The client id/secret come from an application created in Classic Central's
  API Gateway, which also issues the first access/refresh token pair. The API
  docs do not give the menu path; look for "API Gateway" / "REST API" in
  Classic Central's account or organization settings.

### Endpoints (all `Authorization: Bearer <access_token>`)

| Method, path | Query / body | Response fields |
|---|---|---|
| `GET /firmware/v1/swarms` | `group`, `limit` (default 20, max 1000), `offset` | `swarms[]`: `swarm_id`, `swarm_name`, `firmware_version`, `recommended`, `upgrade_required`, `device_status` (Up/Down), `aps_count`, `aps[]` (`serial`, `name`, `model`, `mac_address`), `status` {`state`, `reason`, `firmware_scheduled_at`}; `swarm_count` |
| `GET /firmware/v1/swarms/{swarm_id}` | – | one swarm (pycentral `get_firmware_swarm`; shape not re-checked) |
| `GET /firmware/v1/status` | `swarm_id` (IAP) or `serial`, not both | `state`, `reason`, `firmware_scheduled_at` |
| `GET /firmware/v1/versions` | `device_type` (IAP/MAS/HP/CX/CONTROLLER) or `swarm_id` or `serial` | `data[]`: `firmware_version`, `release_status` (`release`/`beta`), `create_date` |
| `GET /firmware/v1/upgrade/compliance_version` | `device_type` (required), `group` (omit for customer level) | `firmware_compliance_version`, `compliance_scheduled_at` |
| `POST /firmware/v1/upgrade` | body: `swarm_id`, `serial`, `group` + `device_type`, `firmware_version` (omitted = recommended), `firmware_scheduled_at` (epoch s, default now), `reboot` (ignored for IAP: "IAP reboots automatically"), `model` (switches only), `forced` (gateway cluster) | `success_list[]`, `failed_list[]` ({`hostname`, `reason`}), `message` (bulk upgrades run in the background with both lists empty) |
| `POST /firmware/v1/upgrade/cancel` | body: `swarm_id` or `serial`, or `group` + `device_type` | `status` |

Errors: `{service_name, error_code, description}` with codes 0001 general,
0002 out of range, 0003 unsupported combination, 0004 invalid value, 0005
missing parameter; HTTP 400/401/403/413/429/500.

Not confirmed:

- The value strings of `status.state` and `status.reason` (only "State of
  firmware upgrade" / "Description of specific state").
- Any "live" / upgrade-type field in `POST /firmware/v1/upgrade`. The UI's
  Live vs Standard choice has no documented counterpart in the API body.
- Whether Classic `swarm_id` equals New Central `clusterId`. `firmware_status`
  joins on the id and falls back to the swarm name.
- A site filter on any Classic firmware endpoint (none documented).

## Selectors (group / site / swarm)

`firmware_status(group, site, swarm_name)`: any combination, each exact and
case-insensitive, all must match; group from the AP's `deviceGroupName`, site
from `siteName`, swarm from `clusterName`. APs with no cluster are listed per
(group, site), not merged into one line.

How it reads:

- New Central AP inventory in full (one page per 1000 APs), filtered locally.
- `firmware-details`: with a filter, narrowed to `siteName in (...)` of the
  matched APs when that fits the 256-character filter limit; otherwise, and
  with no filter, every AP. Not narrowed by `serialNumber in (...)`: about 15
  serials fit in 256 characters, so a swarm of 140 APs would take 10 requests
  where the unfiltered read takes one.
- Classic: `/firmware/v1/swarms?group=<name>` and the compliance version, once
  per distinct group of the matched APs (up to 20), with the group's exact
  name as New Central reports it, so a filter typed in another case still
  reaches Classic. The first Classic failure (authentication or any other)
  is noted once and the remaining Classic calls are skipped; the New Central
  part of the answer is kept.
- Join: Classic `swarm_id` = New Central `clusterId` when they match; otherwise
  by (group, swarm name). Several Classic swarms with that name are reported
  as ambiguous, never picked. `firmware_versions` refuses an ambiguous
  `swarm_name` and takes `group` or `swarm_id` instead.

Token file handling (Classic):

- A refresh first checks that the token file's directory is writable; if
  not, it does not refresh (the old refresh token would be spent and the new
  one could not be saved).
- The new pair is written to a temp file, flushed and fsynced, renamed over
  the file, and the directory fsynced. If that still fails, the process keeps
  the pair in memory, reports it in `health_check` (`classic: error`) and
  `firmware_status` notes with the remedy, and retries the write on the next
  refresh.
- A bootstrapped file without `expires_at` is used as is until the first
  HTTP 401, then refreshed once.
- httpx/httpcore are set to WARNING when the Classic client is built, and a
  filter masks `client_id`, `client_secret`, `refresh_token`, `access_token`
  query values in anything they log.

Planned upgrade tool (phase 2, not implemented): the same three selectors,
refusing a call with none of them (no "upgrade everything"). Classic upgrades
by `swarm_id` or by `group` + `device_type`, not by site, so a site selector is
resolved to the swarms whose APs sit in that site (from New Central) and sent
as one `swarm_id` request per swarm; a group selector maps to `group` +
`device_type=IAP` only when no site/swarm narrows it. Before sending, the tool
should check that the version is in `/firmware/v1/versions` for that swarm,
report the branch change (e.g. 8.10 to 8.13), and read `/firmware/v1/status`
afterwards. It is state-changing, so it stays opt-in and out of the smoke test.
