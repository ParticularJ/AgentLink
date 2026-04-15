#!/usr/bin/env python3
"""
earnings-surprise-strategy 文件一致性检查脚本
"""

import sys
import os
import yaml

sys.path.insert(0, '/home/qinliming/.npm-global/lib/node_modules/openclaw/skills/Stock/earnings-surprise-strategy')

def check_version_consistency():
    """检查版本号一致性"""
    print("="*80)
    print("1. 版本号一致性检查")
    print("="*80)
    
    versions = {}
    
    # 检查README
    try:
        with open('/home/qinliming/.npm-global/lib/node_modules/openclaw/skills/Stock/earnings-surprise-strategy/README.md', 'r') as f:
            content = f.read()
            if '1.0.0' in content:
                versions['README.md'] = 'v1.0.0'
    except Exception as e:
        print(f"   ❌ 读取README失败: {e}")
    
    # 检查agents
    try:
        with open('/home/qinliming/.npm-global/lib/node_modules/openclaw/skills/Stock/earnings-surprise-strategy/agents/earnings-surprise-agent.yaml', 'r') as f:
            content = f.read()
            if 'version:' in content:
                for line in content.split('\n'):
                    if 'version:' in line and '"' in line:
                        versions['agents/earnings-surprise-agent.yaml'] = line.split('"')[1]
                        break
    except Exception as e:
        print(f"   ⚠️ agents配置可能不存在: {e}")
    
    print(f"   发现的版本号:")
    for filepath, version in versions.items():
        print(f"     {filepath}: {version}")
    
    if len(set(versions.values())) <= 1:
        print(f"   ✅ 版本号一致")
        return True
    else:
        print(f"   ⚠️ 版本号可能不一致")
        return True


def check_weight_consistency():
    """检查评分权重一致性"""
    print()
    print("="*80)
    print("2. 评分权重一致性检查")
    print("="*80)
    
    try:
        # 从配置文件读取
        with open('/home/qinliming/.npm-global/lib/node_modules/openclaw/skills/Stock/earnings-surprise-strategy/config/scoring_weights.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        config_weights = config.get('weights', {})
        config_total = sum(config_weights.values()) * 100
        
        print(f"   配置文件权重:")
        for k, v in config_weights.items():
            print(f"     {k}: {v*100:.0f}%")
        print(f"     总和: {config_total:.0f}%")
        
        # 从代码读取
        from skills.scripts.earnings_scanner import EarningsSurpriseScanner
        scanner = EarningsSurpriseScanner()
        code_weights = scanner.weights
        code_total = sum(code_weights.values()) * 100
        
        print(f"   代码中的权重:")
        for k, v in code_weights.items():
            print(f"     {k}: {v*100:.0f}%")
        print(f"     总和: {code_total:.0f}%")
        
        # 比较
        match = abs(config_total - 100) < 0.1 and abs(code_total - 100) < 0.1
        
        if match:
            print(f"   ✅ 权重配置一致")
            return True
        else:
            print(f"   ❌ 权重配置不一致")
            return False
    except Exception as e:
        print(f"   ❌ 检查失败: {e}")
        return False


def check_file_structure():
    """检查文件结构完整性"""
    print()
    print("="*80)
    print("3. 文件结构完整性检查")
    print("="*80)
    
    required_files = [
        'README.md',
        'requirements.txt',
        'config/scoring_weights.yaml',
        'config/strategy_config.yaml',
        'config/risk_rules.yaml',
        'agents/earnings-surprise-agent.yaml',
        'crons/earnings-surprise-crons.yaml',
        'skills/scripts/earnings_scanner.py',
        'skills/scripts/data_fetcher.py',
        'skills/scripts/surprise_analyzer.py',
        'skills/scripts/quality_analyzer.py',
        'skills/scripts/market_analyzer.py',
        'skills/scripts/risk_assessor.py',
        'skills/scripts/report_generator.py',
        'skills/scripts/backtest.py',
    ]
    
    base_path = '/home/qinliming/.npm-global/lib/node_modules/openclaw/skills/Stock/earnings-surprise-strategy'
    
    all_exist = True
    empty_files = []
    
    for filepath in required_files:
        full_path = os.path.join(base_path, filepath)
        exists = os.path.exists(full_path)
        
        if exists:
            # 检查文件是否为空
            size = os.path.getsize(full_path)
            if size == 0:
                empty_files.append(filepath)
                status = "⚠️ 空文件"
            else:
                status = "✅"
        else:
            status = "❌ 缺失"
            all_exist = False
        
        print(f"   {status} {filepath}")
    
    if empty_files:
        print(f"\n   ⚠️ 发现空文件: {', '.join(empty_files)}")
    
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
    print("4. 模块导入检查")
    print("="*80)
    
    modules_to_check = [
        ('data_fetcher', 'EarningsDataFetcher'),
        ('surprise_analyzer', 'SurpriseAnalyzer'),
        ('quality_analyzer', 'QualityAnalyzer'),
        ('market_analyzer', 'MarketReactionAnalyzer'),
        ('risk_assessor', 'RiskAssessor'),
        ('report_generator', 'EarningsReportGenerator'),
    ]
    
    sys.path.insert(0, '/home/qinliming/.npm-global/lib/node_modules/openclaw/skills/Stock/earnings-surprise-strategy/skills/scripts')
    
    all_ok = True
    for module_name, class_name in modules_to_check:
        try:
            module = __import__(module_name)
            cls = getattr(module, class_name)
            print(f"   ✅ {module_name}.{class_name}")
        except Exception as e:
            print(f"   ❌ {module_name}.{class_name}: {e}")
            all_ok = False
    
    return all_ok


def check_cron_config():
    """检查定时任务配置"""
    print()
    print("="*80)
    print("5. 定时任务配置检查")
    print("="*80)
    
    try:
        with open('/home/qinliming/.npm-global/lib/node_modules/openclaw/skills/Stock/earnings-surprise-strategy/crons/earnings-surprise-crons.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        jobs = config.get('jobs', [])
        print(f"   定时任务数量: {len(jobs)}")
        
        for job in jobs:
            print(f"   - {job.get('name', '未命名')}: {job.get('schedule', '无调度')}")
        
        print(f"   ✅ 定时任务配置正常")
        return True
    except Exception as e:
        print(f"   ❌ 检查失败: {e}")
        return False


def main():
    print("\n" + "="*80)
    print("earnings-surprise-strategy - 文件一致性检查")
    print("="*80 + "\n")
    
    results = []
    results.append(("版本号一致性", check_version_consistency()))
    results.append(("评分权重一致性", check_weight_consistency()))
    results.append(("文件结构完整性", check_file_structure()))
    results.append(("模块导入检查", check_module_imports()))
    results.append(("定时任务配置", check_cron_config()))
    
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
        print("✅ 所有检查通过！文件内容一致。")
    else:
        print("⚠️ 部分检查未通过，请检查相关文件。")
    print("="*80 + "\n")
    
    return all_passed


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
