#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
编码规范护栏测试 —— 把「已经修好、不许再退化」的约定固化成可执行的检查。

这些用例看起来琐碎，但它们正是本轮重构解决的问题：
硬编码绝对路径、明文凭据、静默吞异常、重复实现、cwd 相对路径。
"""
from __future__ import annotations

import re
import unittest

from tests import support

ROOT = support.REPO_ROOT

# 说明性文字里允许出现历史路径（例如「旧代码把 /home/jarvis/... 写死」）
PATH_DOC_ALLOWLIST = {
    "common/paths.py",
    "scripts/_common.sh",
}


def py_files():
    for p in ROOT.rglob("*.py"):
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith(("_archive/", "tests/")):
            continue
        yield p, rel


def code_files(*suffixes):
    for p in ROOT.rglob("*"):
        if not p.is_file() or p.suffix not in suffixes:
            continue
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith(("_archive/", "tests/")):
            continue
        yield p, rel


class TestNoHardcodedPaths(unittest.TestCase):

    def test_no_absolute_home_paths_in_code(self):
        offenders = []
        for p, rel in code_files(".py", ".sh", ".yaml", ".yml", ".md"):
            if rel in PATH_DOC_ALLOWLIST:
                continue
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if "/home/jarvis" in line:
                    offenders.append(f"{rel}:{i}")
        self.assertEqual(offenders, [], f"发现硬编码绝对路径: {offenders}")

    def test_no_cwd_relative_data_paths(self):
        """历史写法 ./my_stock_pool/... 或 ../../../my_stock_pool/... 依赖 cwd，必须走 common/paths。"""
        offenders = []
        for p, rel in py_files():
            text = p.read_text(encoding="utf-8")
            if re.search(r"['\"]\.\.?/(?:\.\./)*my_stock_pool", text):
                offenders.append(rel)
        self.assertEqual(offenders, [], f"发现 cwd 相对数据路径: {offenders}")


class TestNoSecretsInSource(unittest.TestCase):

    def test_no_plaintext_feishu_credentials(self):
        import feishu_config

        secret = feishu_config.FEISHU_APP_SECRET
        if not secret:
            self.skipTest("本地未配置凭据")
        offenders = []
        for p, rel in code_files(".py", ".sh", ".yaml", ".yml"):
            if rel.startswith("common/secrets"):
                continue  # 真实凭据只允许出现在这里，且已被 .gitignore 忽略
            if secret in p.read_text(encoding="utf-8", errors="ignore"):
                offenders.append(rel)
        self.assertEqual(offenders, [], f"源码中出现明文 App Secret: {offenders}")

    def test_secrets_file_is_gitignored(self):
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("common/secrets.yaml", gitignore)

    def test_example_secrets_contains_no_real_secret(self):
        example = (support.COMMON_DIR / "secrets.example.yaml").read_text(encoding="utf-8")
        import feishu_config

        if feishu_config.FEISHU_APP_SECRET:
            self.assertNotIn(feishu_config.FEISHU_APP_SECRET, example)


class TestExceptionHandling(unittest.TestCase):

    def test_no_bare_except(self):
        offenders = []
        for p, rel in py_files():
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if re.match(r"^\s*except\s*:\s*$", line):
                    offenders.append(f"{rel}:{i}")
        self.assertEqual(offenders, [], f"裸 except 会吞掉 KeyboardInterrupt: {offenders}")

    # 已知历史包袱：这些位置用 except: pass 忽略异常（多为数据源逐票探测循环）。
    # 本轮重构未逐一改造（会改变告警噪音与既有行为），故设为「棘轮基线」：
    #   - 新增任何一处 → 测试失败
    #   - 改造掉任何一处 → 需要同步下调基线，保证只减不增
    SILENT_EXCEPT_BASELINE = 39

    def test_no_silent_except_pass(self):
        """静默吞异常的处数不得超过基线（只减不增）。"""
        offenders = []
        for p, rel in py_files():
            lines = p.read_text(encoding="utf-8").splitlines()
            for i in range(len(lines) - 1):
                if re.match(r"^\s*except\b.*:\s*$", lines[i]) and lines[i + 1].strip() == "pass":
                    offenders.append(f"{rel}:{i + 1}")
        self.assertLessEqual(
            len(offenders), self.SILENT_EXCEPT_BASELINE,
            f"静默吞异常新增了：{offenders[self.SILENT_EXCEPT_BASELINE:]}",
        )


class TestEntryPointBootstrap(unittest.TestCase):

    FIND_MARKER = '"common", "paths.py"'
    INSERT_MARKER = 'sys.path.insert(0, os.path.join(_root, "common"))'

    def test_every_paths_consumer_uses_the_same_bootstrap(self):
        """凡是从 common 导入的脚本，必须用同一套「向上找 common/paths.py」引导。

        不要求字面完全一致（有的文件已有 _BASE_DIR，写法略有差别），
        但必须同时具备「探测」与「插入 sys.path」两步，否则就是各写一套。
        """
        offenders = []
        for p, rel in py_files():
            text = p.read_text(encoding="utf-8")
            if self.FIND_MARKER not in text:
                continue
            if rel.startswith("common/"):
                continue
            if self.INSERT_MARKER not in text:
                offenders.append(rel)
        self.assertEqual(offenders, [], f"引导代码不完整: {offenders}")

    def test_shell_wrappers_have_no_absolute_paths(self):
        offenders = []
        for p, rel in code_files(".sh"):
            text = p.read_text(encoding="utf-8")
            if re.search(r"^\s*(cd|PYTHONPATH=|/)[^\n]*/home/", text, re.M):
                offenders.append(rel)
        self.assertEqual(offenders, [], f"shell 脚本含绝对路径: {offenders}")

    def test_shell_wrappers_source_common_env(self):
        wrappers = sorted(ROOT.glob("run_*.sh"))
        self.assertGreaterEqual(len(wrappers), 13)
        for w in wrappers:
            self.assertIn("scripts/_common.sh", w.read_text(encoding="utf-8"), w.name)

    def test_shell_wrappers_are_valid_bash(self):
        """有 bash 时做一次语法检查（Windows 上用 WSL，缺失则跳过）。"""
        import shutil
        import subprocess

        bash = shutil.which("bash")
        if not bash:
            self.skipTest("环境没有 bash")
        for w in sorted(ROOT.glob("run_*.sh")) + [ROOT / "scripts" / "_common.sh"]:
            result = subprocess.run([bash, "-n", str(w)], capture_output=True, text=True)
            if result.returncode in (126, 127) or "No such file" in (result.stderr or ""):
                self.skipTest("bash 无法访问该路径（WSL 与 Windows 路径差异）")
            self.assertEqual(result.returncode, 0, f"{w.name}: {result.stderr}")


class TestNoDuplicatedImplementations(unittest.TestCase):

    def test_watchlist_loader_is_not_reimplemented(self):
        """_load_watchlist 只允许作为薄包装出现，不能再出现解析逻辑。"""
        offenders = []
        for p, rel in py_files():
            text = p.read_text(encoding="utf-8")
            if "def _load_watchlist" in text and "yaml.safe_load" in text:
                offenders.append(rel)
        self.assertEqual(offenders, [], f"仍在自行解析股票池: {offenders}")

    def test_holdings_loader_is_not_reimplemented(self):
        offenders = []
        for p, rel in py_files():
            text = p.read_text(encoding="utf-8")
            if "def _load_holdings" in text and "json.load" in text:
                offenders.append(rel)
        self.assertEqual(offenders, [], f"仍在自行读取持仓: {offenders}")

    def test_feishu_token_helper_is_centralised(self):
        offenders = []
        for p, rel in py_files():
            if rel.startswith("common/") or rel.startswith("tests/"):
                continue
            text = p.read_text(encoding="utf-8")
            if "def get_tenant_token" in text:
                offenders.append(rel)
        self.assertEqual(offenders, [], f"飞书 token 获取应统一到 common/feishu.py: {offenders}")

    def test_code_normalisation_is_centralised(self):
        """lstrip(\"sh\") 是按字符集剥离，属于历史写法，应统一用 holdings.to_pure_code。"""
        offenders = []
        for p, rel in py_files():
            if rel.startswith("common/") or rel.startswith("tests/"):
                continue
            text = p.read_text(encoding="utf-8")
            if re.search(r"lstrip\(['\"]s['\"]?\)|lstrip\(['\"]sh['\"]\)", text):
                offenders.append(rel)
        self.assertEqual(offenders, [], f"代码规范化应统一到 common/holdings.py: {offenders}")


class TestModuleHygiene(unittest.TestCase):

    def test_every_module_compiles(self):
        import py_compile

        for p, rel in py_files():
            try:
                py_compile.compile(str(p), doraise=True, cfile=None)
            except py_compile.PyCompileError as e:  # pragma: no cover
                self.fail(f"{rel} 编译失败: {e}")

    def test_pyflakes_is_clean_when_available(self):
        try:
            from pyflakes.api import checkPath
            from pyflakes.reporter import Reporter
        except ImportError:
            self.skipTest("未安装 pyflakes")
        import io

        out = io.StringIO()
        reporter = Reporter(out, out)
        warnings = 0
        for p, rel in py_files():
            warnings += checkPath(str(p), reporter)
        self.assertEqual(warnings, 0, f"pyflakes 报告:\n{out.getvalue()}")

    def test_shared_modules_do_not_import_strategy_code(self):
        """分层约束：common 只能向下依赖，不能反向 import 策略目录。"""
        banned = ("market_phase_detector", "fusion_runner", "stock_analyzer", "data_source")
        offenders = []
        for p in sorted((ROOT / "common").glob("*.py")):
            text = p.read_text(encoding="utf-8")
            for name in banned:
                if re.search(rf"^\s*(from|import)\s+{name}\b", text, re.M):
                    offenders.append(f"{p.name} -> {name}")
        self.assertEqual(offenders, [], f"common 层出现反向依赖: {offenders}")


if __name__ == "__main__":
    unittest.main()
