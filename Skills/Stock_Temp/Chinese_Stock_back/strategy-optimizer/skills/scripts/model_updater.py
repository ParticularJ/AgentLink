# skills/scripts/model_updater.py

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
模型更新器 - 更新策略配置文件和参数
"""

import os
import yaml
import shutil
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path


class ModelUpdater:
    """策略模型更新器"""
    
    def __init__(self, config: Dict):
        self.config = config
        
    def update_strategy_params(self, strategy_name: str,
                               optimized_params: Dict) -> bool:
        """更新策略参数配置"""
        print(f"\n更新{strategy_name}策略参数...")
        
        # 获取策略配置路径
        strategy_config_path = self._get_strategy_config_path(strategy_name)
        
        if not strategy_config_path:
            print(f"  未找到{strategy_name}的配置路径")
            return False
        
        # 备份原配置
        self._backup_config(strategy_config_path)
        
        # 更新参数
        try:
            with open(strategy_config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # 更新参数
            if 'strategy' in config and 'parameters' in config['strategy']:
                for param, value in optimized_params.items():
                    if param in config['strategy']['parameters']:
                        config['strategy']['parameters'][param] = value
                        print(f"  更新参数: {param} = {value}")
            
            # 保存更新后的配置
            with open(strategy_config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
            
            print(f"  ✅ 参数更新完成")
            return True
            
        except Exception as e:
            print(f"  ❌ 更新失败: {e}")
            return False
    
    def update_scoring_weights(self, strategy_name: str,
                               optimized_weights: Dict) -> bool:
        """更新评分权重配置"""
        print(f"\n更新{strategy_name}评分权重...")
        
        # 获取权重配置路径
        weights_path = self._get_weights_path(strategy_name)
        
        if not weights_path:
            print(f"  未找到{strategy_name}的权重配置")
            return False
        
        # 备份原配置
        self._backup_config(weights_path)
        
        # 更新权重
        try:
            with open(weights_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            if 'weights' in config:
                for weight_name, weight_value in optimized_weights.items():
                    if weight_name in config['weights']:
                        config['weights'][weight_name] = weight_value
                        print(f"  更新权重: {weight_name} = {weight_value}")
            
            with open(weights_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
            
            print(f"  ✅ 权重更新完成")
            return True
            
        except Exception as e:
            print(f"  ❌ 更新失败: {e}")
            return False
    
    def update_thresholds(self, strategy_name: str,
                          optimized_thresholds: Dict) -> bool:
        """更新阈值配置"""
        print(f"\n更新{strategy_name}阈值配置...")
        
        # 获取策略配置路径
        strategy_config_path = self._get_strategy_config_path(strategy_name)
        
        if not strategy_config_path:
            return False
        
        # 备份并更新
        try:
            with open(strategy_config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            if 'scoring' in config and 'thresholds' in config['scoring']:
                for threshold, value in optimized_thresholds.items():
                    if threshold in config['scoring']['thresholds']:
                        config['scoring']['thresholds'][threshold] = value
                        print(f"  更新阈值: {threshold} = {value}")
            
            with open(strategy_config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
            
            print(f"  ✅ 阈值更新完成")
            return True
            
        except Exception as e:
            print(f"  ❌ 更新失败: {e}")
            return False
    
    def rollback_update(self, strategy_name: str, version: str = None) -> bool:
        """回滚到之前的版本"""
        print(f"\n回滚{strategy_name}配置...")
        
        # 获取备份目录
        backup_dir = self._get_backup_dir(strategy_name)
        
        if not os.path.exists(backup_dir):
            print(f"  未找到备份文件")
            return False
        
        # 获取备份文件列表
        backups = sorted(os.listdir(backup_dir))
        
        if not backups:
            print(f"  无可用备份")
            return False
        
        # 选择要回滚的版本
        if version:
            target_backup = version
        else:
            target_backup = backups[-1]  # 最新的备份
        
        backup_path = os.path.join(backup_dir, target_backup)
        
        if not os.path.exists(backup_path):
            print(f"  未找到备份: {target_backup}")
            return False
        
        # 恢复配置
        strategy_config_path = self._get_strategy_config_path(strategy_name)
        
        try:
            shutil.copy(backup_path, strategy_config_path)
            print(f"  ✅ 已回滚到: {target_backup}")
            return True
            
        except Exception as e:
            print(f"  ❌ 回滚失败: {e}")
            return False
    
    def _get_strategy_config_path(self, strategy_name: str) -> Optional[str]:
        """获取策略配置路径"""
        strategies = self.config['optimizer']['strategies']
        
        for strategy in strategies:
            if strategy['name'] == strategy_name:
                config_path = os.path.join(
                    strategy['path'],
                    'config', 'strategy_config.yaml'
                )
                if os.path.exists(config_path):
                    return config_path
        
        return None
    
    def _get_weights_path(self, strategy_name: str) -> Optional[str]:
        """获取权重配置路径"""
        strategies = self.config['optimizer']['strategies']
        
        for strategy in strategies:
            if strategy['name'] == strategy_name:
                weights_path = os.path.join(
                    strategy['path'],
                    'config', 'scoring_weights.yaml'
                )
                if os.path.exists(weights_path):
                    return weights_path
        
        return None
    
    def _get_backup_dir(self, strategy_name: str) -> str:
        """获取备份目录"""
        return os.path.join(
            self.config['data_storage']['optimized_params'],
            f"{strategy_name}_backups"
        )
    
    def _backup_config(self, config_path: str):
        """备份配置文件"""
        backup_dir = os.path.join(
            os.path.dirname(config_path),
            'backups'
        )
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"{os.path.basename(config_path)}.{timestamp}.bak"
        backup_path = os.path.join(backup_dir, backup_name)
        
        shutil.copy(config_path, backup_path)
        print(f"  已备份: {backup_name}")