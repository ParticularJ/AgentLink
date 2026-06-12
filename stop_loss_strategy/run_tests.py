#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
运行测试入口
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tests.test_decision import run_all_tests

if __name__ == '__main__':
    run_all_tests()
