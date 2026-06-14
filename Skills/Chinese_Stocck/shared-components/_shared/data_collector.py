#!/usr/bin/env python3
"""
统一数据采集器 - 各策略分析结果持久化
"""
import json
import os
from datetime import datetime
from typing import Dict, List


class DataCollector:
    """统一数据采集器"""
    
    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = os.path.expanduser("~/.openclaw/stock/data")
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)
    
    def save(self, strategy_name: str, results: List[Dict], date: str = None) -> str:
        """
        保存策略分析结果
        
        Args:
            strategy_name: 策略名称（对应目录名）
            results: 分析结果列表
            date: 日期，默认为今天
        
        Returns:
            保存的文件路径
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        # 标准化结果数据
        normalized = self._normalize_results(strategy_name, results, date)
        
        strategy_dir = os.path.join(self.base_dir, strategy_name)
        os.makedirs(strategy_dir, exist_ok=True)
        
        filename = os.path.join(strategy_dir, f"{date}.json")
        
        # 合并已有数据（不重复覆盖同一天追加）
        existing = []
        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            except:
                pass
        
        # 追加新结果，按code去重
        existing_codes = {r.get('stock_code') or r.get('code') for r in existing}
        for r in normalized:
            code = r.get('stock_code') or r.get('code')
            if code and code not in existing_codes:
                existing.append(r)
                existing_codes.add(code)
        
        # 写入
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        
        return filename
    
    def load(self, strategy_name: str, date: str) -> List[Dict]:
        """加载指定日期的分析结果"""
        filename = os.path.join(self.base_dir, strategy_name, f"{date}.json")
        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return []
    
    def _normalize_results(self, strategy_name: str, results: List[Dict], date: str) -> List[Dict]:
        """标准化各策略的输出格式"""
        normalized = []
        for r in results:
            nr = {
                'date': date,
                'strategy': strategy_name,
                'stock_code': r.get('code') or r.get('stock_code'),
                'stock_name': r.get('name') or r.get('stock_name'),
                'signal': r.get('signal', 'WATCH'),
                'score': r.get('score', 0),
                'current_price': r.get('current_price') or r.get('latest_price'),
            }
            # 策略特有字段透传
            for k, v in r.items():
                if k not in ('date', 'strategy', 'stock_code', 'stock_name', 'signal', 'score', 'current_price'):
                    nr[k] = self._to_json_serializable(v)
            normalized.append(nr)
        return normalized
    
    def _to_json_serializable(self, obj):
        """递归转换对象为JSON可序列化的格式"""
        if isinstance(obj, bool):
            return obj  # JSON支持true/false
        elif isinstance(obj, (int, float, str, type(None))):
            return obj
        elif isinstance(obj, dict):
            return {k: self._to_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._to_json_serializable(item) for item in obj]
        else:
            # 其他类型转换为字符串
            return str(obj)


# 便捷函数
_collector = None

def collect(strategy_name: str, results: List[Dict], date: str = None) -> str:
    """一行代码保存分析结果"""
    global _collector
    if _collector is None:
        _collector = DataCollector()
    return _collector.save(strategy_name, results, date)


if __name__ == '__main__':
    print("DataCollector ready - import and use collect('strategy', results_list)")
