#!/usr/bin/env python

"""Tests for `caprover_api` package."""

import json
import unittest
from unittest.mock import MagicMock, patch

import yaml

from caprover_api.caprover_api import CaproverAPI


class TestAppVariables(unittest.TestCase):
    """Tests for app variable resolution in one-click-app definitions"""

    def setUp(self):
        """Set up test fixtures"""
        with patch.object(CaproverAPI, "get_system_info"), patch.object(
            CaproverAPI, "_login"
        ):
            self.api = CaproverAPI(
                dashboard_url="http://dummy", password="dummy"
            )
            self.api.root_domain = (
                "example.com"  # This is used by _resolve_app_variables
            )
        self.raw_yaml = """
captainVersion: 4
services:
  $$cap_appname:
    image: $$cap_docker_image
    environment:
      SECRET: $$cap_gen_random_hex(10)
      VRD: $$cap_var_with_random_default
      VSD: $$cap_var_with_static_default

caproverOneClickApp:
  variables:
    - id: '$$cap_docker_image'
      label: Docker Image
    - id: '$$cap_var_with_random_default'
      label: Var with random default
      defaultValue: '$$cap_gen_random_hex(6)'
    - id: '$$cap_var_with_static_default'
      label: Var with static default
      defaultValue: 'Abcde'
"""

    def test_appname_replacement(self):
        """Test that $$cap_appname is replaced correctly"""
        result = self.api._resolve_app_variables(
            self.raw_yaml, "testapp", {}, automated=True
        )
        parsed = yaml.safe_load(result)
        self.assertIn("testapp", parsed["services"])

    def test_override_default(self):
        """A defaultValue can be overridden by app_variables"""
        result = self.api._resolve_app_variables(
            self.raw_yaml,
            "testapp",
            {"$$cap_var_with_static_default": "CustomValue"},
            automated=True,
        )
        parsed = yaml.safe_load(result)
        self.assertEqual(
            parsed["services"]["testapp"]["environment"]["VSD"], "CustomValue"
        )

    def test_static_default_variable(self):
        """Variable with (static) defaultValue gets that value when not set"""
        result = self.api._resolve_app_variables(
            self.raw_yaml, "testapp", {}, automated=True
        )
        parsed = yaml.safe_load(result)
        self.assertEqual(
            parsed["services"]["testapp"]["environment"]["VSD"], "Abcde"
        )

    def test_gen_random_hex_default_variable(self):
        """Variable with random default gets a random value when not set"""
        result = self.api._resolve_app_variables(
            self.raw_yaml, "testapp", {}, automated=True
        )
        parsed = yaml.safe_load(result)
        self.assertRegex(
            str(parsed["services"]["testapp"]["environment"]["VRD"]),
            r"^[0-9a-f]{6}$",
        )

    def test_gen_random_hex_in_service(self):
        """gen_random_hex is applied in service definitions (not just variables)"""
        result = self.api._resolve_app_variables(
            self.raw_yaml, "testapp", {}, automated=True
        )
        parsed = yaml.safe_load(result)
        self.assertRegex(
            parsed["services"]["testapp"]["environment"]["SECRET"],
            r"^[0-9a-f]{10}$",
        )


class TestUpdateApp(unittest.TestCase):
    def setUp(self):
        with patch.object(CaproverAPI, "get_system_info"), patch.object(
            CaproverAPI, "_login"
        ):
            self.api = CaproverAPI(
                dashboard_url="http://dummy", password="dummy"
            )
        self.api.headers = {"Authorization": "Bearer mock_token"}

        # Mock session.post so we can sniff how update calls it
        self.api.session = MagicMock()
        self.api.session.post = MagicMock(
            return_value=MagicMock(
                json=lambda: {"description": "Saved", "status": 100}
            )
        )

        # Mock get_app response to simulate the current app information
        self.api.get_app = MagicMock(
            return_value={
                "appName": "test_app",
                "redirectDomain": "",
                "envVars": [{"key": "EXISTING_ENV_VAR", "value": "old_value"}],
                "volumes": [
                    {
                        "hostPath": "/old_path",
                        "containerPath": "/container_path",
                    }
                ],
                "appPushWebhook": {},
            }
        )

    def test_add_environment_variables(self):
        self.api.update_app(
            "test_app",
            environment_variables={"ANOTHER": "foobar"},
        )
        post_data = json.loads(self.api.session.post.call_args[1]["data"])

        expected = [
            {"key": "EXISTING_ENV_VAR", "value": "old_value"},
            {"key": "ANOTHER", "value": "foobar"},
        ]
        self.assertEqual(post_data["envVars"], expected)

    def test_update_no_change(self):
        """
        update_app, without passing persistent_directories arg, should
        keep existing volumes from get_app.
        """
        self.api.update_app("test_app")

        # Capture post data
        post_data = json.loads(self.api.session.post.call_args[1]["data"])

        # Assert 'volumes' is unchanged from get_app()
        expected_volumes = [
            {"hostPath": "/old_path", "containerPath": "/container_path"}
        ]
        self.assertEqual(post_data["volumes"], expected_volumes)

    def test_add_http_auth(self):
        self.api.update_app(
            "test_app", http_auth={"user": "admin", "password": "example"}
        )
        post_data = json.loads(self.api.session.post.call_args[1]["data"])

        self.assertEqual(
            post_data["httpAuth"], {"user": "admin", "password": "example"}
        )

    def test_update_with_persistent_directories_host_path(self):
        """
        Test update_app with persistent_directories using hostPath format.
        """
        self.api.update_app(
            "test_app",
            persistent_directories=["/new_host_path:/new_container_path"],
        )
        post_data = json.loads(self.api.session.post.call_args[1]["data"])

        # Assert 'volumes' is replaced
        expected_volumes = [
            {
                "hostPath": "/new_host_path",
                "containerPath": "/new_container_path",
            }
        ]
        self.assertEqual(post_data["volumes"], expected_volumes)

    def test_update_with_persistent_directories_volume_name(self):
        """
        Test update_app with persistent_directories using volumeName format.
        """
        self.api.update_app(
            "test_app",
            persistent_directories=["new_volume:/new_container_path"],
        )
        post_data = json.loads(self.api.session.post.call_args[1]["data"])

        # Assert 'volumes' is replaced with the new volumeName entry
        expected_volumes = [
            {"volumeName": "new_volume", "containerPath": "/new_container_path"}
        ]
        self.assertEqual(post_data["volumes"], expected_volumes)

    def test_update_port_mapping(self):
        self.api.update_app("test_app", port_mapping=["8080:80", "443:443"])
        post_data = json.loads(self.api.session.post.call_args[1]["data"])

        expected = [
            {"containerPort": "80", "hostPort": "8080"},
            {"containerPort": "443", "hostPort": "443"},
        ]
        self.assertEqual(post_data["ports"], expected)

    def test_update_via_unspecified_kwarg(self):
        """You can use kwargs to override any other not explicitly listed as a method arg."""
        new_redirect_domain = "test_app.example.com"
        self.api.update_app("test_app", redirectDomain=new_redirect_domain)
        post_data = json.loads(self.api.session.post.call_args[1]["data"])

        self.assertEqual(post_data["redirectDomain"], new_redirect_domain)
