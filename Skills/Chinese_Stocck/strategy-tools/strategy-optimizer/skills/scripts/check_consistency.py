# skills/scripts/check_consistency.py

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
策略优化器一致性检查脚本
"""

import os
import sys
import yaml


def check_imports():
    """检查依赖导入"""
    print("\n【依赖检查】")
    
    packages = ['pandas', 'numpy', 'yaml']
    
    for pkg in packages:
        try:
            module = __import__(pkg)
            version = getattr(module, '__version__', 'unknown')
            print(f"✅ {pkg} - {version}")
        except ImportError:
            print(f"❌ {pkg} - 未安装")


def check_config():
    """检查配置文件"""
    print("\n【配置文件检查】")
    
    config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'config')
    
    config_files = ['optimizer_config.yaml', 'optimization_params.yaml', 'evaluation_config.yaml']
    
    for f in config_files:
        path = os.path.join(config_dir, f)
        if os.path.exists(path):
            print(f"✅ {f}")
            with open(path, 'r', encoding='utf-8') as file:
                try:
                    yaml.safe_load(file)
                    print(f"   └─ YAML格式正确")
                except Exception as e:
                    print(f"   └─ YAML格式错误: {e}")
        else:
            print(f"❌ {f} - 不存在")


def check_strategy_paths():
    """检查策略路径"""
    print("\n【策略路径检查】")
    
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        'config', 'optimizer_config.yaml'
    )
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    strategies = config.get('optimizer', {}).get('strategies', [])
    
    for strategy in strategies:
        name = strategy.get('name')
        path = strategy.get('path')
        
        if path and os.path.exists(path):
            print(f"✅ {name}: {path}")
        else:
            print(f"❌ {name}: {path} - 路径不存在")


def check_data_dirs():
    """检查数据目录"""
    print("\n【数据目录检查】")
    
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        'config', 'optimizer_config.yaml'
    )
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    data_dirs = config.get('data_storage', {})
    
    for name, path in data_dirs.items():
        if name != 'logs':
            full_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), path)
            if os.path.exists(full_path):
                print(f"✅ {name}: {path}")
            else:
                print(f"⚠️ {name}: {path} - 目录不存在，将自动创建")


if __name__ == '__main__':
    print("=" * 50)
    print("策略优化器一致性检查")
    print("=" * 50)
    
    check_imports()
    check_config()
    check_strategy_paths()
    check_data_dirs()
    
    print("\n✅ 检查完成")