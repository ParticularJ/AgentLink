#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
赛道配置
V5.0 - 政策+资金+产业三层漏斗
"""

from typing import Dict, List, Tuple

# 政策驱动赛道 - 十五五规划未来产业方向
POLICY_DRIVEN_SECTORS = {
    '未来制造': ['量子科技', '具身智能', '脑机接口', '人形机器人'],
    '未来信息': ['6G', '卫星互联网', '光通信'],
    '未来能源': ['氢能', '可控核聚变', '新型储能', '固态电池'],
    '未来材料': ['第三代半导体材料', '第四代半导体材料', '碳纳米管'],
    '未来空间': ['商业航天', '低空经济'],
    '未来健康': ['生物制造', '细胞治疗', '基因治疗', '创新药'],
}

# 资金驱动赛道阈值
FUND_DRIVEN_THRESHOLDS = {
    'sector_rps20': 85,                    # 板块RPS20 > 85 (V5.0从90下调)
    'volume_share_days': 5,                # 连续5日
    'volume_share_threshold': 0.04,        # 成交额占比 > 4%
    'margin_increase_days': 5,             # 近5日
    'margin_increase_threshold': 0.10,     # 融资余额增幅 > 10%
    'limit_up_count_days': 5,              # 近5日
    'limit_up_count_threshold': 3,         # 涨停家数 > 3家 (V5.0从5家下调)
    'north_bound_inflow_days': 30,         # 近1个月
    'north_bound_inflow_threshold': 3e9,   # 北向净流入 > 30亿 (V5.0从50亿下调)
}

# 产业驱动赛道阈值
INDUSTRY_DRIVEN_THRESHOLDS = {
    'penetration_lower': 0.03,             # 渗透率下限 3% (V5.0从5%下调)
    'penetration_upper': 0.15,             # 渗透率上限 15%
    'capex_growth_threshold': 0.30,        # 龙头CAPEX增速 > 30% (V5.0从50%下调)
    'research_report_threshold': 3,        # 近1个月深度报告 > 3篇 (V5.0从5篇下调)
    'financing_threshold': 5e9,            # 近3个月融资额 > 50亿 (V5.0从100亿下调)
    'price_increase_threshold': 0.20,      # 核心产品价格上涨 > 20%
}

# 赛道四维评估权重
SECTOR_EVALUATION_WEIGHTS = {
    'policy_strength': 0.25,      # 政策强度 25% (V5.0从30%下调)
    'industry_stage': 0.30,       # 产业阶段 30%
    'fund_consensus': 0.30,       # 资金共识 30% (V5.0从25%上调)
    'catalyst_density': 0.15,     # 催化密度 15%
}

# 政策强度评分
POLICY_STRENGTH_SCORING = {
    'national_strategy': (20, 25),    # 国家战略级
    'ministry_level': (12, 19),       # 部委级
    'local_level': (5, 11),           # 地方级
}

# 产业阶段评分
INDUSTRY_STAGE_SCORING = {
    'explosive': (25, 30),        # 爆发期
    'growth': (15, 24),           # 成长期
    'differentiation': (5, 14),   # 分化期
    'decline': (0, 4),            # 衰退期
}

# 资金共识评分
FUND_CONSENSUS_SCORING = {
    'strong': (25, 30),       # 强
    'medium': (13, 24),       # 中
    'weak': (0, 12),          # 弱
}

# 催化密度评分
CATALYST_DENSITY_SCORING = {
    'high': (12, 15),     # 高
    'medium': (6, 11),    # 中
    'low': (0, 5),        # 低
}

# 赛道定级标准
SECTOR_GRADING = {
    'S': {'min_score': 85, 'max_count': 4, 'depth': 'full_four_layer'},      # S级 2-4个
    'A': {'min_score': 70, 'max_count': 6, 'depth': 'full_four_layer'},      # A级 4-6个
    'B': {'min_score': 60, 'max_count': 3, 'depth': 'core_only'},            # B级 2-3个
}

# 赛道筛选总分阈值
SECTOR_SCORE_THRESHOLDS = {
    'pass': 70,       # 总分 >=70分 进入第三层
    'watch': 50,      # 总分 50-69分 观察池
    'eliminate': 0,   # 总分 <50分 剔除
}

# 交叉验证规则 (V5.0新增)
CROSS_VALIDATION_RULE = {
    'S_grade_requires': 2,  # S级赛道需要至少2个来源同时识别
    'sources': ['policy', 'fund', 'industry'],
}

# 产业链四层结构定义
INDUSTRY_CHAIN_LAYERS = {
    'upstream': {
        'name': '上游',
        'definition': '原材料、芯片设计、IP、EDA',
        'characteristics': '弹性最大，波动剧烈，启动最早',
        'timing': 'T0-T1',  # 景气传导时序
    },
    'midstream': {
        'name': '中游',
        'definition': '制造、封装、测试、模组集成',
        'characteristics': '业绩确定性高，市值偏大，启动次之',
        'timing': 'T1-T2',
    },
    'downstream': {
        'name': '下游',
        'definition': '应用、品牌、渠道、运营',
        'characteristics': '受终端需求影响大，启动最晚',
        'timing': 'T2-T3',
    },
    'support': {
        'name': '支撑层',
        'definition': '设备、材料、耗材、技术服务',
        'characteristics': '弹性与确定性兼得，常被忽视，全周期受益',
        'timing': 'T0-T3',  # 全周期
    },
}

# 支撑层量化识别标准 (V5.0)
SUPPORT_LAYER_CRITERIA = {
    'customer_coverage': {
        'description': '客户覆盖广',
        'threshold': {'top5_customers': 3, 'sectors': 2},  # 前5大客户来自>=3个细分行业或覆盖>=2个赛道
    },
    'consumable_attribute': {
        'description': '耗材属性',
        'threshold': {'repurchase_cycle': 1},  # 复购周期<1年
        'examples': ['电子特气', '光刻胶', '靶材'],
    },
    'equipment_attribute': {
        'description': '设备属性',
        'threshold': {'capex_growth': 0.20},  # 客户CAPEX增速>20%时订单加速
        'examples': ['激光设备', '刻蚀机', '检测设备'],
    },
    'service_attribute': {
        'description': '服务属性',
        'threshold': {'renewal_rate': 0.70},  # 客户续约率>70%
        'examples': ['CRO/CDMO', 'EDA软件'],
    },
    'import_substitution': {
        'description': '国产替代空间',
        'threshold': {'localization_rate': 0.30},  # 国产化率<30%且正在加速替代
        'examples': ['半导体设备', '高端材料'],
    },
}

# 龙头识别标准权重
LEADER_IDENTIFICATION_WEIGHTS = {
    'market_share': 0.25,         # 市占率 25% (V5.0从前3放宽到前5)
    'tech_barrier': 0.25,         # 技术壁垒 25%
    'earnings_elasticity': 0.25,  # 业绩弹性 25%
    'institution_coverage': 0.15, # 机构覆盖 15% (V5.0从2家下调到1家)
    'historical_performance': 0.10,  # 历史股性 10%
}

# 板块轮动四阶段
ROTATION_STAGES = {
    'startup': {
        'name': '启动期',
        'rps_range': (50, 70),
        'volume_characteristics': '温和放大',
        'band_suitability': '最佳入场时机',
        'strategy': '重点筛选，积极配置',
    },
    'acceleration': {
        'name': '加速期',
        'rps_range': (70, 90),
        'volume_characteristics': '显著放大',
        'band_suitability': '仍可参与，但需控制仓位',
        'strategy': '正常筛选，严格止损',
    },
    'climax': {
        'name': '高潮期',
        'rps_range': (90, 100),
        'volume_characteristics': '天量',
        'band_suitability': '仅适合短线，波段风险高',
        'strategy': '谨慎筛选，降低仓位上限',
    },
    'decline': {
        'name': '衰退期',
        'rps_range': (0, 50),
        'volume_characteristics': '萎缩',
        'band_suitability': '不适合波段',
        'strategy': '不筛选，已有持仓考虑止盈',
    },
}
