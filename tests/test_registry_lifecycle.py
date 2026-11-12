import unittest
from unittest.mock import Mock, patch

import requests

from registry_lifecycle import RegistryLifecycle, service_metadata
from s5_app import create_app


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.metadata = {"service_id": "S5", "name": "Moving Averages", "description": "SMA", "url": "http://s5/comparison"}
        self.http = Mock()
        self.http.post.return_value = Mock(status_code=200)
        self.manager = RegistryLifecycle(self.metadata, ["http://primary", "http://backup"], session=self.http)

    def test_registers_both_registries_and_preserves_description(self):
        self.manager.renew_once()
        self.assertEqual([c.args[0] for c in self.http.post.call_args_list], ["http://primary/register", "http://backup/register"])
        self.assertTrue(all(self.manager.registered.values()))
        self.assertEqual(self.http.post.call_args.kwargs["json"], self.metadata)

    def test_heartbeat_then_unknown_node_reregisters(self):
        self.manager.registered = {url: True for url in self.manager.urls}
        self.http.post.side_effect = [Mock(status_code=404), Mock(status_code=200), Mock(status_code=200)]
        self.manager.renew_once()
        self.assertEqual([c.args[0] for c in self.http.post.call_args_list], ["http://primary/heartbeat", "http://primary/register", "http://backup/heartbeat"])

    def test_http_failure_does_not_prevent_backup_registration(self):
        self.http.post.side_effect = [Mock(status_code=500), Mock(status_code=200)]
        self.manager.renew_once()
        self.assertFalse(self.manager.registered["http://primary"])
        self.assertTrue(self.manager.registered["http://backup"])

    def test_transport_failure_and_later_recovery(self):
        self.http.post.side_effect = [requests.ConnectionError(), Mock(status_code=200)]
        self.manager.renew_once()
        self.http.post.side_effect = None
        self.manager.renew_once()
        self.assertTrue(all(self.manager.registered.values()))

    def test_failed_heartbeat_is_registered_again_next_cycle(self):
        self.manager.registered = {url: True for url in self.manager.urls}
        self.http.post.side_effect = [Mock(status_code=503), Mock(status_code=200)]
        self.manager.renew_once()
        self.http.post.side_effect = None
        self.http.post.reset_mock()
        self.manager.renew_once()
        self.assertEqual(self.http.post.call_args_list[0].args[0], "http://primary/register")

    def test_stop_ceases_renewals_without_inventing_delete_endpoint(self):
        self.manager.stop()
        self.manager.renew_once()
        self.http.post.assert_not_called()
        self.http.delete.assert_not_called()

    def test_explicit_delete_contract_can_be_configured(self):
        manager = RegistryLifecycle(self.metadata, ["http://primary"], session=self.http, remove_path="/services/{service_id}")
        manager.stop()
        self.http.delete.assert_called_once_with("http://primary/services/S5", timeout=2, allow_redirects=False)
        manager.stop()
        self.assertEqual(self.http.delete.call_count, 1)

    def test_environment_disabled_by_default_and_enabled_explicitly(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(RegistryLifecycle.from_environment(self.metadata))
        with patch.dict("os.environ", {"REGISTRY_URLS": "http://primary, http://backup"}, clear=True):
            manager = RegistryLifecycle.from_environment(self.metadata)
            self.assertEqual(manager.urls, ["http://primary", "http://backup"])

    def test_invalid_configuration(self):
        for urls in ([], ["relative"], ["file:///tmp/registry"]):
            with self.assertRaises(ValueError):
                RegistryLifecycle(self.metadata, urls)

    def test_app_registers_metadata_and_exposes_info(self):
        manager = Mock()
        app = create_app(registry=manager)
        manager.start.assert_called_once()
        info = app.test_client().get("/service-info")
        self.assertEqual(info.status_code, 200)
        self.assertEqual(info.get_json()["service_id"], "S5")
        self.assertIn("description", info.get_json())

    def test_public_url_is_explicit(self):
        with patch.dict("os.environ", {"SERVICE_PUBLIC_URL": "https://example.org/s5"}):
            info = service_metadata("S5", "SMA", "Description", "/comparison", 5005)
        self.assertEqual(info["url"], "https://example.org/s5/comparison")


if __name__ == "__main__":
    unittest.main()
