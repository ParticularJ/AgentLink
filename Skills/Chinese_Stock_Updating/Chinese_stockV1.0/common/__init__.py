"""
common —— 全工程共享的基础设施层。

模块划分（依赖方向单向：scripts -> common -> paths）：

    paths.py         仓库内所有路径的唯一来源（可被环境变量覆盖）
    feishu_config.py 飞书凭据加载（环境变量 > secrets.yaml > 模板）
    holdings.py      持仓/现金读写、备份、原子写入、代码规范化
    watchlist.py     股票池读取（容错 level:/空列表等历史写法）
    logutil.py       统一日志（保持 [时间] 消息 的原有输出格式）
    feishu.py        飞书 token / 卡片 / 文本推送（带重试）
    indicators.py    纯计算技术指标
    grade.py         个股分级相关的纯函数（分级表由调用方注入）

模块名刻意不叫 secrets，避免遮蔽 Python 标准库的同名模块。
"""
