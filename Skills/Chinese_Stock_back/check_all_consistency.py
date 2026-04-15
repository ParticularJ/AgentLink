#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Stock目录所有策略一致性检查脚本
"""

import os
import yaml
import re
from pathlib import Path

BASE_DIR = "/home/qinliming/.npm-global/lib/node_modules/openclaw/skills/Stock"

strategies = [
    "ma-bullish-strategy",
    "limit-up-analysis",
    "earnings-surprise-strategy",
    "volume-retrace-ma-strategy",
    "limit-up-retrace-strategy",
    "macd-divergence-strategy",
    "morning-star-strategy",
    "breakout-high-strategy",
    "rsi-oversold-strategy",
    "volume-extreme-strategy",
    "gap-fill-strategy"
]

def check_strategy_consistency(strategy_name):
    """检查单个策略的一致性"""
    issues = []
    strategy_dir = os.path.join(BASE_DIR, strategy_name)
    
    if not os.path.exists(strategy_dir):
        return [f"目录不存在: {strategy_dir}"]
    
    # 检查必需文件
    required_files = [
        "README.md",
        "SKILL.md",
        "requirements.txt",
        "config/scoring_weights.yaml",
        "config/strategy_config.yaml",
        "config/risk_rules.yaml"
    ]
    
    for file in required_files:
        file_path = os.path.join(strategy_dir, file)
        if not os.path.exists(file_path):
            issues.append(f"缺少文件: {file}")
    
    # 读取SKILL.md
    skill_md_path = os.path.join(strategy_dir, "SKILL.md")
    if os.path.exists(skill_md_path):
        with open(skill_md_path, 'r', encoding='utf-8') as f:
            skill_content = f.read()
        
        # 提取SKILL.md中的信息
        skill_name_match = re.search(r'name:\s*"([^"]+)"', skill_content)
        skill_version_match = re.search(r'version:\s*"([^"]+)"', skill_content)
        skill_desc_match = re.search(r'description:\s*"([^"]+)"', skill_content)
        
        skill_name = skill_name_match.group(1) if skill_name_match else None
        skill_version = skill_version_match.group(1) if skill_version_match else None
        skill_desc = skill_desc_match.group(1) if skill_desc_match else None
    else:
        skill_name = skill_version = skill_desc = None
        issues.append("SKILL.md不存在")
    
    # 读取README.md
    readme_path = os.path.join(strategy_dir, "README.md")
    if os.path.exists(readme_path):
        with open(readme_path, 'r', encoding='utf-8') as f:
            readme_content = f.read()
        
        # 检查README中的名称一致性
        if skill_name and skill_name not in readme_content:
            issues.append(f"README.md中缺少策略名称: {skill_name}")
        
        if skill_version and skill_version not in readme_content:
            issues.append(f"README.md中版本不一致: {skill_version}")
    else:
        issues.append("README.md不存在")
    
    # 检查scoring_weights.yaml
    weights_path = os.path.join(strategy_dir, "config/scoring_weights.yaml")
    if os.path.exists(weights_path):
        try:
            with open(weights_path, 'r', encoding='utf-8') as f:
                weights = yaml.safe_load(f)
            
            if weights and 'weights' in weights:
                total = sum(weights['weights'].values())
                if abs(total - 1.0) > 0.01:
                    issues.append(f"权重和不等于100%: {total*100:.1f}%")
        except Exception as e:
            issues.append(f"scoring_weights.yaml解析错误: {e}")
    
    # 检查requirements.txt
    req_path = os.path.join(strategy_dir, "requirements.txt")
    if os.path.exists(req_path):
        with open(req_path, 'r', encoding='utf-8') as f:
            req_content = f.read()
        
        # 检查是否包含数据源依赖
        has_datasource = any(x in req_content for x in ['akshare', 'tushare', 'baostock', 'yfinance'])
        if not has_datasource:
            issues.append("requirements.txt缺少数据源依赖")
    
    return issues

def main():
    print("="*80)
    print("Stock目录策略一致性检查报告")
    print("="*80)
    print()
    
    all_ok = True
    for strategy in strategies:
        issues = check_strategy_consistency(strategy)
        
        if issues:
            all_ok = False
            print(f"❌ {strategy}")
            for issue in issues:
                print(f"   - {issue}")
            print()
        else:
            print(f"✅ {strategy} - 检查通过")
    
    print("="*80)
    if all_ok:
        print("所有策略一致性检查通过！")
    else:
        print("发现一致性问题，请修复上述问题")
    print("="*80)

if __name__ == '__main__':
    main()
