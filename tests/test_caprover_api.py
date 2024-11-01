#!/usr/bin/env python

"""Tests for `caprover_api` package."""

import json
import unittest
from unittest.mock import MagicMock, patch

from caprover_api.caprover_api import CaproverAPI


class TestCaprover_api(unittest.TestCase):
    """Tests for `caprover_api` package."""

    def setUp(self):
        """Set up test fixtures, if any."""

    def tearDown(self):
        """Tear down test fixtures, if any."""

    def test_000_something(self):
        """Test something."""


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
