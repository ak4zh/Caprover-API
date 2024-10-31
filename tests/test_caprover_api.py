#!/usr/bin/env python

"""Tests for `caprover_api` package."""

import unittest
from unittest.mock import patch

import yaml

from caprover_api.caprover_api import CaproverAPI


class TestCaprover_api(unittest.TestCase):
    """Tests for `caprover_api` package."""

    def setUp(self):
        """Set up test fixtures, if any."""

    def tearDown(self):
        """Tear down test fixtures, if any."""

    def test_000_something(self):
        """Test something."""


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
            parsed["services"]["testapp"]["environment"]["VRD"],
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
