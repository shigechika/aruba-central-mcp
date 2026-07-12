"""Tests for MCP server tools."""

import os
import re
from unittest.mock import patch

import pytest

from aruba_central_mcp.client import ArubaAuthError, ArubaClientError
from aruba_central_mcp.server import (
    _build_odata_filter,
    _format_ap,
    _format_client,
    _format_switch,
    _odata_literal,
    _reset_client,
    _safe_mac,
    _safe_serial,
    daily_brief,
    find_client_by_mac,
    get_ap_status,
    get_ap_throughput,
    get_site_summary,
    health_check,
    list_aps,
    list_clients,
    list_switches,
)

SAMPLE_APS = [
    {
        "deviceName": "AP-01",
        "status": "ONLINE",
        "model": "AP-515",
        "siteName": "Main Campus",
        "ipv4": "10.0.1.1",
        "firmwareVersion": "10.6.0.0",
        "macAddress": "aa:bb:cc:dd:ee:01",
        "serialNumber": "SN001",
        "publicIpv4": "203.0.113.1",
        "deviceGroupName": "Group1",
        "deployment": "campus",
    },
    {
        "deviceName": "AP-02",
        "status": "OFFLINE",
        "model": "AP-515",
        "siteName": "Sub Campus",
        "ipv4": "10.0.1.2",
        "firmwareVersion": "10.6.0.0",
        "macAddress": "aa:bb:cc:dd:ee:02",
    },
]

SAMPLE_SWITCHES = [
    {
        "deviceName": "SW-01",
        "status": "ONLINE",
        "model": "CX 6200",
        "switchType": "AOS-CX",
        "ipv4": "10.0.2.1",
        "firmwareVersion": "10.12.0001",
        "macAddress": "11:22:33:44:55:01",
    },
]

SAMPLE_CLIENTS = [
    {
        "clientName": "iPhone",
        "macAddress": "ff:ee:dd:cc:bb:aa",
        "ipv4": "172.16.1.10",
        "wlanName": "eduroam",
        "wirelessBand": "5 GHz",
        "snr": "45",
        "connectedTo": "AP-01",
        "authenticationType": "DOT1X",
        "siteName": "Main Campus",
    },
    {
        "clientName": "Laptop",
        "macAddress": "aa:bb:cc:dd:ee:ff",
        "ipv4": "172.16.1.11",
        "wlanName": "nichidai-wifi",
        "wirelessBand": "2.4 GHz",
        "snr": "28",
        "connectedTo": "AP-01",
        "authenticationType": "MAC",
        "siteName": "Main Campus",
    },
]


def _parse_odata_filter(filter_str):
    """Parse OData filter string into a dict of field -> value.

    Handles: "field eq 'value'" and "field1 eq 'v1' and field2 eq 'v2'"
    """
    if not filter_str:
        return {}
    result = {}
    for clause in re.split(r"\s+and\s+", filter_str):
        m = re.match(r"(\w+)\s+eq\s+'([^']*)'", clause.strip())
        if m:
            result[m.group(1)] = m.group(2)
    return result


def _apply_odata_filter(items, filter_str):
    """Filter items using parsed OData eq clauses."""
    filters = _parse_odata_filter(filter_str)
    if not filters:
        return items
    return [
        item for item in items
        if all(item.get(k) == v for k, v in filters.items())
    ]


@pytest.fixture(autouse=True)
def reset():
    """Reset shared client before each test."""
    _reset_client()
    yield
    _reset_client()


@pytest.fixture
def mock_client():
    """Patch _get_client to return a FakeClient with OData filter support."""

    class FakeClient:
        def __init__(self):
            self.ap_items = SAMPLE_APS
            self.switch_items = SAMPLE_SWITCHES
            self.client_items = SAMPLE_CLIENTS

        def fetch_all(self, path, limit=1000, params=None):
            from aruba_central_mcp.client import PATH_APS, PATH_CLIENTS, PATH_SWITCHES

            if path == PATH_APS:
                items = self.ap_items
            elif path == PATH_SWITCHES:
                items = self.switch_items
            elif path == PATH_CLIENTS:
                items = self.client_items
            else:
                items = []

            # Apply OData filter if present
            if params and "filter" in params:
                items = _apply_odata_filter(items, params["filter"])
            return items

        def get(self, path, params=None):
            from aruba_central_mcp.client import PATH_CLIENTS, ArubaAPIError

            # Direct client lookup: /clients/{mac}
            if path.startswith(PATH_CLIENTS + "/"):
                mac = path[len(PATH_CLIENTS) + 1:]
                for cl in self.client_items:
                    if cl.get("macAddress", "").lower() == mac.lower():
                        return cl
                raise ArubaAPIError(f"404 Not Found: {path}", status_code=404)
            return {}

        def close(self):
            pass

    fake = FakeClient()
    with patch("aruba_central_mcp.server._get_client", return_value=fake):
        yield fake


class TestBuildOdataFilter:
    def test_single_field(self):
        """Single field generates correct OData string."""
        result = _build_odata_filter(siteName="Main Campus")
        assert result == "siteName eq 'Main Campus'"

    def test_multiple_fields(self):
        """Multiple fields joined with 'and'."""
        result = _build_odata_filter(siteName="Main", status="ONLINE")
        assert "siteName eq 'Main'" in result
        assert "status eq 'ONLINE'" in result
        assert " and " in result

    def test_empty_values_skipped(self):
        """Empty values are excluded from filter."""
        result = _build_odata_filter(siteName="", status="ONLINE")
        assert result == "status eq 'ONLINE'"

    def test_all_empty_returns_none(self):
        """All empty values returns None."""
        result = _build_odata_filter(siteName="", status="")
        assert result is None

    def test_single_quote_is_escaped(self):
        """A value with a single quote is escaped (doubled), not injected."""
        result = _build_odata_filter(siteName="O'Hare")
        assert result == "siteName eq 'O''Hare'"

    def test_injection_attempt_stays_inside_literal(self):
        """An OData-injection attempt is neutralised by quote-doubling."""
        result = _build_odata_filter(siteName="x' or '1'='1")
        assert result == "siteName eq 'x'' or ''1''=''1'"


class TestInputValidation:
    def test_odata_literal_doubles_quotes(self):
        assert _odata_literal("a'b'c") == "a''b''c"
        assert _odata_literal("plain") == "plain"

    def test_safe_mac_normalises_and_accepts(self):
        assert _safe_mac("AA-BB-CC-DD-EE-FF") == "aa:bb:cc:dd:ee:ff"
        assert _safe_mac("aabbccddeeff") == "aabbccddeeff"

    def test_safe_mac_rejects_path_injection(self):
        for bad in ["aa:bb/../secret", "aa:bb:cc?x=1", "aa'bb", "aa bb"]:
            with pytest.raises(ArubaClientError):
                _safe_mac(bad)

    def test_safe_mac_rejects_malformed(self):
        # Structurally invalid even though every char is in the hex/colon set.
        for bad in [":", "::::", "aabb", "aa:bb:cc:dd:ee", "aabbccddeeffgg"]:
            with pytest.raises(ArubaClientError):
                _safe_mac(bad)

    def test_safe_serial_accepts_and_rejects(self):
        assert _safe_serial("CN12345ABC") == "CN12345ABC"
        assert _safe_serial("SN-01_A.2") == "SN-01_A.2"
        for bad in ["SN/../x", "SN 1", "SN'x", "SN?y=1"]:
            with pytest.raises(ArubaClientError):
                _safe_serial(bad)

    def test_safe_serial_rejects_traversal_tokens(self):
        # A bare "." / ".." would inject a path-traversal segment into the URL.
        for bad in [".", "..", "...", "-", "_", ".hidden"]:
            with pytest.raises(ArubaClientError):
                _safe_serial(bad)


class TestFormatFunctions:
    def test_format_ap(self):
        """AP formatting includes key fields."""
        result = _format_ap(SAMPLE_APS[0])
        assert "AP-01" in result
        assert "ONLINE" in result
        assert "AP-515" in result

    def test_format_switch(self):
        """Switch formatting includes key fields."""
        result = _format_switch(SAMPLE_SWITCHES[0])
        assert "SW-01" in result
        assert "CX 6200" in result

    def test_format_client(self):
        """Client formatting includes key fields."""
        result = _format_client(SAMPLE_CLIENTS[0])
        assert "iPhone" in result
        assert "eduroam" in result
        assert "5 GHz" in result


class TestListAps:
    def test_list_all(self, mock_client):
        """List all APs."""
        result = list_aps()
        assert "2 total" in result
        assert "AP-01" in result
        assert "AP-02" in result

    def test_filter_by_site(self, mock_client):
        """Filter APs by site name (server-side OData)."""
        result = list_aps(site="Main Campus")
        assert "AP-01" in result
        assert "AP-02" not in result

    def test_filter_by_status(self, mock_client):
        """Filter APs by status (server-side OData)."""
        result = list_aps(status="OFFLINE")
        assert "AP-02" in result
        assert "1 total" in result

    def test_empty_result(self, mock_client):
        """No APs match filter."""
        result = list_aps(site="Nonexistent")
        assert "No access points found" in result


class TestListSwitches:
    def test_list_all(self, mock_client):
        """List all switches."""
        result = list_switches()
        assert "1 total" in result
        assert "SW-01" in result

    def test_empty(self, mock_client):
        """No switches."""
        mock_client.switch_items = []
        result = list_switches()
        assert "No switches found" in result


class TestListClients:
    def test_list_all(self, mock_client):
        """List all clients."""
        result = list_clients()
        assert "2 total" in result

    def test_filter_by_ssid(self, mock_client):
        """Filter clients by SSID (server-side OData)."""
        result = list_clients(ssid="eduroam")
        assert "iPhone" in result
        assert "Laptop" not in result

    def test_filter_by_band(self, mock_client):
        """Filter clients by band (server-side OData)."""
        result = list_clients(band="2.4 GHz")
        assert "Laptop" in result
        assert "iPhone" not in result

    def test_empty_result(self, mock_client):
        """No clients match filter."""
        result = list_clients(ssid="nonexistent")
        assert "No clients found" in result


class TestFindClientByMac:
    def test_found(self, mock_client):
        """Find client by MAC via direct API lookup."""
        result = find_client_by_mac("ff:ee:dd:cc:bb:aa")
        assert "iPhone" in result

    def test_not_found(self, mock_client):
        """MAC not found returns appropriate message."""
        result = find_client_by_mac("00:00:00:00:00:00")
        assert "No client found" in result

    def test_case_insensitive(self, mock_client):
        """MAC lookup is case-insensitive."""
        result = find_client_by_mac("FF:EE:DD:CC:BB:AA")
        assert "iPhone" in result

    def test_dash_format(self, mock_client):
        """MAC with dashes is converted to colons."""
        result = find_client_by_mac("ff-ee-dd-cc-bb-aa")
        assert "iPhone" in result

    def test_rejects_invalid_mac(self, mock_client):
        """The tool validates the MAC before building the request path."""
        with pytest.raises(ArubaClientError):
            find_client_by_mac("aa:bb/../secret")


class TestGetApThroughput:
    def test_rejects_invalid_serial(self, mock_client):
        """The tool validates the AP serial before building the request path."""
        with pytest.raises(ArubaClientError):
            get_ap_throughput("SN/../secret")


class TestGetApStatus:
    def test_found(self, mock_client):
        """Get detailed AP status."""
        result = get_ap_status("AP-01")
        assert "AP-01" in result
        assert "Status" in result
        assert "ONLINE" in result
        assert "Serial" in result

    def test_not_found(self, mock_client):
        """AP name not found."""
        result = get_ap_status("AP-99")
        assert "No access point found" in result

    def test_case_insensitive(self, mock_client):
        """AP name search is case-insensitive."""
        result = get_ap_status("ap-01")
        assert "AP-01" in result


class TestGetSiteSummary:
    def test_summary(self, mock_client):
        """Site summary aggregates correctly."""
        result = get_site_summary()
        assert "2 sites" in result
        assert "Main Campus" in result
        assert "Sub Campus" in result

    def test_empty(self, mock_client):
        """No data."""
        mock_client.ap_items = []
        mock_client.client_items = []
        result = get_site_summary()
        assert "No site data" in result


class TestDailyBrief:
    def test_header_format(self, mock_client):
        """Output starts with daily_brief header and site count line."""
        result = daily_brief()
        assert "## daily_brief —" in result
        assert "sites:" in result

    def test_offline_site_is_warning(self, mock_client):
        """Site with all APs offline appears in WARNINGS."""
        # SAMPLE_APS: Sub Campus has 1 AP (OFFLINE) → 100% > 10%
        result = daily_brief()
        assert "### WARNINGS" in result
        assert "Sub Campus" in result
        assert "AP-OFFLINE" in result

    def test_online_site_is_ok(self, mock_client):
        """Site with all APs online appears in OK sites."""
        # SAMPLE_APS: Main Campus has 1 AP (ONLINE) → 0% ≤ 10%
        result = daily_brief()
        assert "### OK sites" in result
        assert "Main Campus" in result

    def test_site_counts_in_header(self, mock_client):
        """Header reports correct OK/WARNING counts."""
        result = daily_brief()
        # Main Campus: OK, Sub Campus: WARNING (1/1 = 100% > 10%)
        assert "2 sites:" in result
        assert "1 OK" in result
        assert "1 WARNING" in result

    def test_all_online_no_warnings(self, mock_client):
        """When all APs are online, no WARNINGS section appears."""
        mock_client.ap_items = [
            {**SAMPLE_APS[0], "siteName": "Site-A"},
            {**SAMPLE_APS[0], "deviceName": "AP-03", "siteName": "Site-B"},
        ]
        result = daily_brief()
        assert "### WARNINGS" not in result
        assert "Site-A" in result
        assert "Site-B" in result

    def test_api_error_returns_critical(self, mock_client):
        """fetch_all failure returns a CRITICAL message."""
        def raise_error(*args, **kwargs):
            raise RuntimeError("Connection failed")
        mock_client.fetch_all = raise_error
        result = daily_brief()
        assert "CRITICAL" in result
        assert "Connection failed" in result

    def test_no_aps_returns_no_data(self, mock_client):
        """Empty AP list returns no-data message."""
        mock_client.ap_items = []
        result = daily_brief()
        assert "No AP data available" in result

    def test_high_threshold_suppresses_warning(self, mock_client):
        """Setting threshold=100 means no site triggers WARNING."""
        result = daily_brief(offline_threshold=100.0)
        assert "### WARNINGS" not in result
        assert "### OK sites" in result

    def test_offline_ratio_shown_in_warning(self, mock_client):
        """WARNING entry shows offline count and percentage."""
        result = daily_brief()
        # Sub Campus: 1/1 = 100%
        assert "1/1 APs offline" in result
        assert "100%" in result


class TestMissingEnvVars:
    def test_missing_env_raises(self):
        """Missing env vars raises ValueError."""
        with pytest.raises(ValueError, match="Missing environment variables"):
            list_aps()


class TestHealthCheck:
    EXPECTED_KEYS = {"status", "service", "version", "base_url", "auth"}

    def test_healthy_when_token_obtained(self):
        """A successful token request reports healthy / auth ok."""

        class TokenClient:
            def __init__(self):
                self.token_calls = 0

            def _get_token(self):
                self.token_calls += 1
                return "fake-token"

            def close(self):
                pass

        fake = TokenClient()
        with patch("aruba_central_mcp.server._get_client", return_value=fake):
            result = health_check()
        assert result["status"] == "healthy"
        assert result["auth"] == "ok"
        assert result["service"] == "aruba-central-mcp"
        assert result["version"]  # __version__ is present
        assert "detail" not in result
        # Probe obtained a token but did NOT touch any data endpoint.
        assert fake.token_calls == 1

    def test_always_returns_fixed_keys(self):
        """Every outcome returns the same fixed-shape key set."""

        class TokenClient:
            def _get_token(self):
                return "fake-token"

            def close(self):
                pass

        with patch("aruba_central_mcp.server._get_client", return_value=TokenClient()):
            result = health_check()
        assert self.EXPECTED_KEYS <= set(result)

    def test_missing_env(self):
        """Missing env vars → status error, auth missing-env, with detail."""
        # Clear the credentials so _get_client raises ValueError (missing-env),
        # independent of whatever is set in the runner's environment.
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith("ARUBA_CENTRAL_")
        }
        with patch.dict(os.environ, env, clear=True):
            result = health_check()
        assert result["status"] == "error"
        assert result["auth"] == "missing-env"
        assert "detail" in result
        assert self.EXPECTED_KEYS <= set(result)

    def test_backend_error(self):
        """A token failure → status degraded, auth error, with detail."""

        class FailingClient:
            def _get_token(self):
                raise ArubaAuthError("OAuth2 authentication failed: 401")

            def close(self):
                pass

        with patch("aruba_central_mcp.server._get_client", return_value=FailingClient()):
            result = health_check()
        assert result["status"] == "degraded"
        assert result["auth"] == "error"
        assert "detail" in result
        assert self.EXPECTED_KEYS <= set(result)
