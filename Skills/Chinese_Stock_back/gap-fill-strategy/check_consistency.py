# skills/scripts/check_consistency.py

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
策略一致性检查脚本
"""

import os
import sys


def check_imports():
    """检查依赖导入"""
    print("\n【依赖检查】")
    
    packages = ['akshare', 'pandas', 'numpy']
    
    for pkg in packages:
        try:
            module = __import__(pkg)
            version = getattr(module, '__version__', 'unknown')
            print(f"✅ {pkg} - {version}")
        except ImportError:
            print(f"❌ {pkg} - 未安装")


def check_strategy():
    """检查策略模块"""
    print("\n【策略模块检查】")
    
    try:
        from gap_fill_analyzer import GapFillAnalyzer
        analyzer = GapFillAnalyzer()
        print(f"✅ 策略名称: {analyzer.name}")
        print(f"✅ 预期胜率: {analyzer.win_rate}")
        print(f"✅ 最小跳空幅度: {analyzer.min_gap_pct}%")
        print(f"✅ 强势跳空幅度: {analyzer.strong_gap_pct}%")
        print(f"✅ 最小放量倍数: {analyzer.min_volume_ratio}")
    except Exception as e:
        print(f"❌ 策略加载失败: {e}")


def check_config():
    """检查配置文件"""
    print("\n【配置文件检查】")
    
    config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'config')
    
    config_files = ['strategy_config.yaml', 'scoring_weights.yaml', 'risk_rules.yaml']
    
    for f in config_files:
        path = os.path.join(config_dir, f)
        if os.path.exists(path):
            print(f"✅ {f}")
        else:
            print(f"❌ {f} - 不存在")


if __name__ == '__main__':
    print("=" * 50)
    print("缺口回补策略一致性检查")
    print("=" * 50)
    
    check_imports()
    check_strategy()
    check_config()
    
    print("\n✅ 检查完成")