import datetime
import gzip
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import geoip_ops


def _fake_response(payload):
    response = MagicMock()
    response.read.return_value = json.dumps(payload).encode()
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


def _fake_gz_response(rows):
    response = MagicMock()
    response.read.return_value = gzip.compress("\n".join(rows).encode())
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


class FetchCountryRangesTest(unittest.TestCase):
    @patch("geoip_ops.urllib.request.urlopen")
    def test_converts_start_end_rows_into_cidrs(self, mock_urlopen):
        mock_urlopen.return_value = _fake_gz_response(["18.228.0.0,18.231.255.255,BR"])
        self.assertEqual(geoip_ops.fetch_country_ranges(["BR"]), {"BR": ["18.228.0.0/14"]})

    @patch("geoip_ops.urllib.request.urlopen")
    def test_returns_only_requested_countries_and_ignores_ipv6(self, mock_urlopen):
        mock_urlopen.return_value = _fake_gz_response([
            "1.2.3.0,1.2.3.255,BR",
            "5.6.7.0,5.6.7.255,US",
            "2001:db8::,2001:db8::ffff,BR",
        ])
        self.assertEqual(geoip_ops.fetch_country_ranges(["br"]), {"BR": ["1.2.3.0/24"]})

    @patch("geoip_ops.urllib.request.urlopen")
    def test_falls_back_to_previous_month_when_current_is_missing(self, mock_urlopen):
        not_found = urllib.error.HTTPError("url", 404, "Not Found", None, None)
        mock_urlopen.side_effect = [not_found, _fake_gz_response(["1.2.3.0,1.2.3.255,BR"])]
        result = geoip_ops.fetch_country_ranges(["BR"])
        self.assertEqual(result, {"BR": ["1.2.3.0/24"]})
        first_url = mock_urlopen.call_args_list[0].args[0].full_url
        second_url = mock_urlopen.call_args_list[1].args[0].full_url
        self.assertNotEqual(first_url, second_url)
        self.assertIn("dbip-country-lite", second_url)

    @patch("geoip_ops.urllib.request.urlopen")
    def test_sends_a_custom_user_agent(self, mock_urlopen):
        mock_urlopen.return_value = _fake_gz_response(["1.2.3.0,1.2.3.255,BR"])
        geoip_ops.fetch_country_ranges(["BR"])
        request = mock_urlopen.call_args.args[0]
        self.assertFalse(request.get_header("User-agent", "Python-urllib").startswith("Python-urllib"))

    @patch("geoip_ops.urllib.request.urlopen", side_effect=urllib.error.URLError("sem rede"))
    def test_network_failure_raises_geoip_error(self, mock_urlopen):
        with self.assertRaises(geoip_ops.GeoIPError):
            geoip_ops.fetch_country_ranges(["BR"])

    @patch("geoip_ops.urllib.request.urlopen")
    def test_malformed_row_raises_geoip_error(self, mock_urlopen):
        mock_urlopen.return_value = _fake_gz_response(["isso nao e csv"])
        with self.assertRaises(geoip_ops.GeoIPError):
            geoip_ops.fetch_country_ranges(["BR"])


class LookupIpCountryTest(unittest.TestCase):
    @patch("geoip_ops.urllib.request.urlopen")
    def test_returns_the_country_and_matching_resource(self, mock_urlopen):
        mock_urlopen.return_value = _fake_response({
            "data": {"located_resources": [
                {"resource": "189.124.0.0/16", "locations": [{"country": "BR", "covered_percentage": 100.0}]},
            ]},
        })
        result = geoip_ops.lookup_ip_country("189.124.85.75")
        self.assertEqual(result, {"country": "BR", "resource": "189.124.0.0/16"})

    @patch("geoip_ops.urllib.request.urlopen")
    def test_none_when_no_located_resources(self, mock_urlopen):
        mock_urlopen.return_value = _fake_response({"data": {"located_resources": []}})
        self.assertIsNone(geoip_ops.lookup_ip_country("8.8.8.8"))

    @patch("geoip_ops.urllib.request.urlopen")
    def test_none_when_resource_has_no_locations(self, mock_urlopen):
        mock_urlopen.return_value = _fake_response({
            "data": {"located_resources": [{"resource": "8.8.8.0/24", "locations": []}]},
        })
        self.assertIsNone(geoip_ops.lookup_ip_country("8.8.8.8"))

    @patch("geoip_ops.urllib.request.urlopen", side_effect=urllib.error.URLError("sem rede"))
    def test_network_failure_raises_geoip_error(self, mock_urlopen):
        with self.assertRaises(geoip_ops.GeoIPError):
            geoip_ops.lookup_ip_country("8.8.8.8")

    @patch("geoip_ops.urllib.request.urlopen")
    def test_unexpected_shape_raises_geoip_error(self, mock_urlopen):
        mock_urlopen.return_value = _fake_response({"data": {}})
        with self.assertRaises(geoip_ops.GeoIPError):
            geoip_ops.lookup_ip_country("8.8.8.8")


class ValidateRangesTest(unittest.TestCase):
    def test_rejects_empty_response(self):
        ok, reason = geoip_ops.validate_ranges("BR", [], previous_count=100)
        self.assertFalse(ok)
        self.assertIsNotNone(reason)

    def test_rejects_a_drop_of_more_than_half(self):
        ok, reason = geoip_ops.validate_ranges("BR", ["1.2.3.0/24"] * 10, previous_count=100)
        self.assertFalse(ok)
        self.assertIsNotNone(reason)

    def test_accepts_normal_variation(self):
        ok, reason = geoip_ops.validate_ranges("BR", ["1.2.3.0/24"] * 95, previous_count=100)
        self.assertTrue(ok)
        self.assertIsNone(reason)

    def test_accepts_first_fetch_with_no_previous_count(self):
        ok, reason = geoip_ops.validate_ranges("BR", ["1.2.3.0/24"], previous_count=0)
        self.assertTrue(ok)


class RefreshTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.state_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    @patch("geoip_ops.fetch_country_ranges", return_value={"BR": ["1.2.3.0/24", "5.6.7.0/24"]})
    def test_accepted_fetch_writes_the_cache(self, mock_fetch):
        results = geoip_ops.refresh(["BR"], self.state_dir)
        self.assertTrue(results["BR"]["accepted"])
        self.assertEqual(results["BR"]["count"], 2)
        self.assertEqual(geoip_ops.read_cached_ranges(self.state_dir, "BR"), ["1.2.3.0/24", "5.6.7.0/24"])

    @patch("geoip_ops.fetch_country_ranges", side_effect=geoip_ops.GeoIPError("timeout"))
    def test_fetch_error_keeps_the_previous_cache(self, mock_fetch):
        geoip_ops._write_ranges(self.state_dir, "BR", ["9.9.9.0/24"])
        results = geoip_ops.refresh(["BR"], self.state_dir)
        self.assertFalse(results["BR"]["accepted"])
        self.assertEqual(geoip_ops.read_cached_ranges(self.state_dir, "BR"), ["9.9.9.0/24"])

    @patch("geoip_ops.fetch_country_ranges", return_value={"BR": []})
    def test_rejected_validation_keeps_the_previous_cache(self, mock_fetch):
        geoip_ops._write_ranges(self.state_dir, "BR", ["9.9.9.0/24"])
        results = geoip_ops.refresh(["BR"], self.state_dir)
        self.assertFalse(results["BR"]["accepted"])
        self.assertEqual(geoip_ops.read_cached_ranges(self.state_dir, "BR"), ["9.9.9.0/24"])

    @patch("geoip_ops.fetch_country_ranges", return_value={"BR": ["1.2.3.0/24"], "CA": ["5.6.7.0/24"]})
    def test_downloads_once_for_multiple_countries(self, mock_fetch):
        results = geoip_ops.refresh(["BR", "CA"], self.state_dir)
        mock_fetch.assert_called_once()
        self.assertTrue(results["BR"]["accepted"])
        self.assertTrue(results["CA"]["accepted"])

    def test_cache_updated_at_is_none_without_cache_and_a_datetime_after_write(self):
        self.assertIsNone(geoip_ops.cache_updated_at(self.state_dir, "BR"))
        geoip_ops._write_ranges(self.state_dir, "BR", ["1.2.3.0/24"])
        self.assertIsInstance(geoip_ops.cache_updated_at(self.state_dir, "BR"), datetime.datetime)

    def test_read_cached_ranges_is_empty_before_any_refresh(self):
        self.assertEqual(geoip_ops.read_cached_ranges(self.state_dir, "BR"), [])


if __name__ == "__main__":
    unittest.main()
