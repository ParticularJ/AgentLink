#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""common/feishu_config.py：凭据加载优先级与容错。"""
from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path

from tests import support  # noqa: F401

import feishu_config


class TestFeishuConfig(unittest.TestCase):

    def test_loads_from_secrets_yaml(self):
        self.assertEqual(feishu_config.missing(), [], "common/secrets.yaml 应包含全部必填项")
        self.assertTrue(feishu_config.FEISHU_APP_ID.startswith("cli_"))
        self.assertEqual(len(feishu_config.FEISHU_APP_SECRET), 32)
        self.assertTrue(feishu_config.FEISHU_GROUP_ID.startswith("oc_"))

    def test_alt_group_falls_back_to_main(self):
        self.assertTrue(feishu_config.FEISHU_GROUP_ID_ALT)

    def test_env_var_wins_over_file(self):
        original = os.environ.get("FEISHU_APP_ID")
        try:
            os.environ["FEISHU_APP_ID"] = "cli_from_env"
            reloaded = importlib.reload(feishu_config)
            self.assertEqual(reloaded.FEISHU_APP_ID, "cli_from_env")
        finally:
            if original is None:
                os.environ.pop("FEISHU_APP_ID", None)
            else:
                os.environ["FEISHU_APP_ID"] = original
            importlib.reload(feishu_config)

    def test_flat_yaml_fallback_parser(self):
        """没有 pyyaml 时也要能解析 secrets.yaml 这种扁平格式。"""
        text = (support.COMMON_DIR / "secrets.yaml").read_text(encoding="utf-8")
        parsed = feishu_config._parse_flat_yaml(text)
        self.assertIn("app_id", parsed)
        self.assertIn("group_id", parsed)
        self.assertFalse(parsed["app_id"].startswith('"'), "引号应被剥离")

    def test_custom_secrets_file_via_env(self):
        with tempfile.TemporaryDirectory() as d:
            custom = Path(d) / "custom.yaml"
            custom.write_text(
                "app_id: cli_custom\n"
                "app_secret: secret_value\n"
                "group_id: oc_custom\n",
                encoding="utf-8",
            )
            os.environ["FEISHU_SECRETS_FILE"] = str(custom)
            for key in ("FEISHU_APP_ID", "FEISHU_APP_SECRET", "FEISHU_GROUP_ID"):
                os.environ.pop(key, None)
            try:
                reloaded = importlib.reload(feishu_config)
                self.assertEqual(reloaded.FEISHU_APP_ID, "cli_custom")
                self.assertEqual(reloaded.FEISHU_GROUP_ID, "oc_custom")
            finally:
                os.environ.pop("FEISHU_SECRETS_FILE", None)
                importlib.reload(feishu_config)

    def test_require_feishu_raises_when_empty(self):
        import feishu_config as fc

        saved = (fc.FEISHU_APP_ID, fc.FEISHU_APP_SECRET, fc.FEISHU_GROUP_ID)
        try:
            fc.FEISHU_APP_ID = ""
            fc.FEISHU_APP_SECRET = ""
            fc.FEISHU_GROUP_ID = ""
            with self.assertRaises(RuntimeError) as ctx:
                fc.require_feishu()
            self.assertIn("secrets.yaml", str(ctx.exception))
        finally:
            fc.FEISHU_APP_ID, fc.FEISHU_APP_SECRET, fc.FEISHU_GROUP_ID = saved


if __name__ == "__main__":
    unittest.main()
