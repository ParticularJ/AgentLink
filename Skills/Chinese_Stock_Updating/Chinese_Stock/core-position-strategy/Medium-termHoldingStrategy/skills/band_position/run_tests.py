#!/usr/bin/env python3
"""
波段交易系统 - 测试运行脚本
"""
import unittest
import sys
import os

# 添加src到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# 导入测试模块
from tests.test_phase1 import (
    TestMarketEnvironment,
    TestTrackDiscovery,
    TestPhase1Filter,
    TestPhase1Scorer,
)
from tests.test_phase2 import (
    TestMoatEvaluator,
    TestVetoChecker,
    TestFinancialScorer,
    TestValuationEvaluator,
    TestPositionCalculator,
)
from tests.test_integration import TestIntegration


def run_tests():
    """运行所有测试"""
    # 创建测试套件
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # 添加第一阶段测试
    print("=" * 60)
    print("加载第一阶段测试...")
    suite.addTests(loader.loadTestsFromTestCase(TestMarketEnvironment))
    suite.addTests(loader.loadTestsFromTestCase(TestTrackDiscovery))
    suite.addTests(loader.loadTestsFromTestCase(TestPhase1Filter))
    suite.addTests(loader.loadTestsFromTestCase(TestPhase1Scorer))

    # 添加第二阶段测试
    print("加载第二阶段测试...")
    suite.addTests(loader.loadTestsFromTestCase(TestMoatEvaluator))
    suite.addTests(loader.loadTestsFromTestCase(TestVetoChecker))
    suite.addTests(loader.loadTestsFromTestCase(TestFinancialScorer))
    suite.addTests(loader.loadTestsFromTestCase(TestValuationEvaluator))
    suite.addTests(loader.loadTestsFromTestCase(TestPositionCalculator))

    # 添加集成测试
    print("加载集成测试...")
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))

    # 运行测试
    print("=" * 60)
    print("开始运行测试...")
    print("=" * 60)

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 输出结果
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    print(f"总测试数: {result.testsRun}")
    print(f"通过: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"失败: {len(result.failures)}")
    print(f"错误: {len(result.errors)}")

    if result.wasSuccessful():
        print("\n✅ 所有测试通过！")
        return 0
    else:
        print("\n❌ 测试未通过")
        return 1


if __name__ == "__main__":
    sys.exit(run_tests())
