"""Tests for MCP server tools."""

from unittest.mock import patch

import pytest

from aruba_central_mcp.server import (
    _format_ap,
    _format_client,
    _format_switch,
    _reset_client,
    find_client_by_mac,
    get_ap_status,
    get_site_summary,
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
        "name": "iPhone",
        "macAddress": "ff:ee:dd:cc:bb:aa",
        "ip": "172.16.1.10",
        "network": "eduroam",
        "band": "5.0",
        "signal_db": "-55",
        "associatedDeviceName": "AP-01",
        "authentication_type": "DOT1X",
    },
    {
        "name": "Laptop",
        "macAddress": "aa:bb:cc:dd:ee:ff",
        "ip": "172.16.1.11",
        "network": "nichidai-wifi",
        "band": "2.4",
        "signal_db": "-72",
        "associatedDeviceName": "AP-01",
        "authentication_type": "MAC",
    },
]


@pytest.fixture(autouse=True)
def reset():
    """Reset shared client before each test."""
    _reset_client()
    yield
    _reset_client()


@pytest.fixture
def mock_client():
    """Patch _get_client to return a mock with fetch_all."""

    class FakeClient:
        def __init__(self):
            self.ap_items = SAMPLE_APS
            self.switch_items = SAMPLE_SWITCHES
            self.client_items = SAMPLE_CLIENTS

        def fetch_all(self, path, limit=1000):
            from aruba_central_mcp.client import PATH_APS, PATH_CLIENTS, PATH_SWITCHES

            if path == PATH_APS:
                return self.ap_items
            elif path == PATH_SWITCHES:
                return self.switch_items
            elif path == PATH_CLIENTS:
                return self.client_items
            return []

        def close(self):
            pass

    fake = FakeClient()
    with patch("aruba_central_mcp.server._get_client", return_value=fake):
        yield fake


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
        assert "5.0" in result


class TestListAps:
    def test_list_all(self, mock_client):
        """List all APs."""
        result = list_aps()
        assert "2 total" in result
        assert "AP-01" in result
        assert "AP-02" in result

    def test_filter_by_site(self, mock_client):
        """Filter APs by site name."""
        result = list_aps(site="Main")
        assert "AP-01" in result
        assert "AP-02" not in result

    def test_filter_by_status(self, mock_client):
        """Filter APs by status."""
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
        """Filter clients by SSID."""
        result = list_clients(ssid="eduroam")
        assert "iPhone" in result
        assert "Laptop" not in result

    def test_filter_by_band(self, mock_client):
        """Filter clients by band."""
        result = list_clients(band="2.4")
        assert "Laptop" in result
        assert "iPhone" not in result

    def test_empty_result(self, mock_client):
        """No clients match filter."""
        result = list_clients(ssid="nonexistent")
        assert "No clients found" in result


class TestFindClientByMac:
    def test_found(self, mock_client):
        """Find client by MAC."""
        result = find_client_by_mac("ff:ee:dd:cc:bb:aa")
        assert "iPhone" in result

    def test_not_found(self, mock_client):
        """MAC not found."""
        result = find_client_by_mac("00:00:00:00:00:00")
        assert "No client found" in result

    def test_case_insensitive(self, mock_client):
        """MAC search is case-insensitive."""
        result = find_client_by_mac("FF:EE:DD:CC:BB:AA")
        assert "iPhone" in result

    def test_dash_format(self, mock_client):
        """MAC with dashes is converted to colons."""
        result = find_client_by_mac("ff-ee-dd-cc-bb-aa")
        assert "iPhone" in result


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


class TestMissingEnvVars:
    def test_missing_env_raises(self):
        """Missing env vars raises ValueError."""
        with pytest.raises(ValueError, match="Missing environment variables"):
            list_aps()
