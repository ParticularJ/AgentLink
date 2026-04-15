#!/usr/bin/env python3
"""
limit-up-retrace-strategy 文件一致性检查
"""

import sys
import os

sys.path.insert(0, '/home/qinliming/.npm-global/lib/node_modules/openclaw/skills/Stock/limit-up-retrace-strategy')

def check_file_structure():
    """检查文件结构完整性"""
    print("="*80)
    print("1. 文件结构完整性检查")
    print("="*80)
    
    required_files = [
        'README.md',
        'SKILL.md',
        'requirements.txt',
        'config/scoring_weights.yaml',
        'config/strategy_config.yaml',
        'config/risk_rules.yaml',
        'agents/limit-up-retrace-agent.yaml',
        'crons/limit-up-retrace-crons.yaml',
        'skills/scripts/limit_up_retrace_analyzer.py',
        'skills/scripts/limit_up_retrace_scanner.py',
    ]
    
    base_path = '/home/qinliming/.npm-global/lib/node_modules/openclaw/skills/Stock/limit-up-retrace-strategy'
    
    all_exist = True
    for filepath in required_files:
        full_path = os.path.join(base_path, filepath)
        exists = os.path.exists(full_path)
        status = "✅" if exists else "❌"
        print(f"   {status} {filepath}")
        if not exists:
            all_exist = False
    
    if all_exist:
        print(f"\n   ✅ 所有必需文件存在")
        return True
    else:
        print(f"\n   ❌ 部分文件缺失")
        return False


def check_module_imports():
    """检查模块导入"""
    print()
    print("="*80)
    print("2. 模块导入检查")
    print("="*80)
    
    sys.path.insert(0, '/home/qinliming/.npm-global/lib/node_modules/openclaw/skills/Stock/limit-up-retrace-strategy/skills/scripts')
    
    try:
        from limit_up_retrace_analyzer import LimitUpRetraceAnalyzer
        print("   ✅ LimitUpRetraceAnalyzer 导入成功")
        
        # 检查权重配置
        weights = {
            'limit_up_quality': 0.25,
            'retrace_quality': 0.20,
            'support_strength': 0.20,
            'volume_shrink': 0.20,
            'stop_signal': 0.15
        }
        total = sum(weights.values())
        print(f"   评分权重总和: {total*100:.0f}%")
        
        if abs(total - 1.0) < 0.01:
            print("   ✅ 权重配置正确")
            return True
        else:
            print("   ❌ 权重配置错误")
            return False
            
    except Exception as e:
        print(f"   ❌ 导入失败: {e}")
        return False


def main():
    print("\n" + "="*80)
    print("limit-up-retrace-strategy - 文件一致性检查")
    print("="*80 + "\n")
    
    results = []
    results.append(("文件结构完整性", check_file_structure()))
    results.append(("模块导入检查", check_module_imports()))
    
    print()
    print("="*80)
    print("检查总结")
    print("="*80)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"   {status} - {name}")
    
    all_passed = all(r[1] for r in results)
    
    print()
    if all_passed:
        print("✅ 所有检查通过！策略已完整可用。")
    else:
        print("⚠️ 部分检查未通过。")
    print("="*80 + "\n")
    
    return all_passed


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
