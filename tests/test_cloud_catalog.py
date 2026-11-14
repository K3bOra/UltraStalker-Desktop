import unittest
from unittest.mock import patch

from ultrastalker_desktop.core import cloud_catalog


class CloudCatalogTests(unittest.TestCase):
    first = "1" * 32
    second = "2" * 32

    @patch.object(cloud_catalog, "_request")
    def test_page_keeps_only_display_fields_and_validates_cursor(self, request):
        request.return_value = {
            "items": [{"id": self.second, "label": "Account", "password": "test", "expires_on": "2027-01-02"}],
            "next": self.second,
        }
        page = cloud_catalog.page("portal", self.first, self.first)
        request.assert_called_once_with(f"portal/servers/{self.first}/accounts", after=self.first)
        self.assertEqual(page, {"items": [{"id": self.second, "label": "Account", "expiry": "2027-01-02"}], "next": self.second})
        with self.assertRaises(cloud_catalog.CatalogError):
            cloud_catalog.page("portal", self.first, self.second)

    @patch.object(cloud_catalog, "_request")
    def test_selected_account_builds_a_desktop_profile(self, request):
        request.return_value = {"connection": {"url": "https://provider.example/", "username": "demo", "password": "example"}}
        profile = cloud_catalog.profile("xtream", self.first, self.second, "Account")
        request.assert_called_once_with(f"xtream/servers/{self.first}/accounts/{self.second}", select=True)
        self.assertEqual((profile.source_type, profile.portal_url), ("xtream", "https://provider.example/"))

    @patch.object(cloud_catalog, "_request")
    def test_invalid_route_never_requests_an_endpoint(self, request):
        with self.assertRaises(cloud_catalog.CatalogError):
            cloud_catalog.page("portal", "../xtream")
        request.assert_not_called()
