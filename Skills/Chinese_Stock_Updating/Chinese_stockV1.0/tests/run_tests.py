#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
零依赖测试入口（只用标准库 unittest），保证在没装 pytest 的部署机上也能跑。

    python tests/run_tests.py            # 全部用例
    python tests/run_tests.py -v         # 详细输出
    python tests/run_tests.py -k holdings  # 只跑名字含 holdings 的用例

装了 pytest 的环境也可以直接用：pytest tests
"""
from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tests import support  # noqa: E402,F401

REPO_ROOT = support.REPO_ROOT  # 触发路径引导与依赖打桩


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="运行测试套件")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")
    parser.add_argument("-k", "--pattern", default="test_*.py", help="测试文件名匹配")
    args = parser.parse_args(argv)

    suite = unittest.defaultTestLoader.discover(
        start_dir=str(REPO_ROOT / "tests"),
        pattern=args.pattern,
        top_level_dir=str(REPO_ROOT),
    )
    result = unittest.TextTestRunner(verbosity=2 if args.verbose else 1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
