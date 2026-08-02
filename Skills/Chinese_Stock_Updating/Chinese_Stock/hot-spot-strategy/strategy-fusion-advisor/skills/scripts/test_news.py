import akshare as ak
import pandas as pd
from bs4 import BeautifulSoup
import requests, time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from llm_client import generate_text

def _analyze_news_sentiment(news_content: str, stock_name: str = "百济神州") -> dict:

    prompt = f"""
    你是一名专业的A股个股新闻分析师，任务是对给定的个股新闻进行独立、客观的多空影响研判。你仅依据本提示词设定的规则进行判断，不受任何外部观点干扰。
    本次仅分析标的：{stock_name}

    新闻内容：{news_content}

    二、研判硬性规则
    2.1 分析范围限制
    仅评判本条新闻对该股单独影响，其余个股联动、大盘走势、跨板块轮动全部忽略，不纳入分析。
    该股的历史走势仅作为背景参考，不作为多空判定的核心依据。
    2.2 实质性利空的硬性认定
    以下情形统一认定为实质性利空，不做任何对冲抵消：
    股东大额减持（判定标准见2.5）
    高折价大宗交易（折价≥7%）
    业绩暴雷（预亏、大幅下修业绩预告）
    监管问询/立案/公开谴责
    2.3 多空判定的核心维度
    仅围绕以下维度判定多空：
    该股自身业绩变化（季报/年报/业绩预告）
    产能落地情况（投产、达产、扩产进度）
    定点供货/合同中标（收到定点通知、签署供货协议）
    订单确认（在手订单、新增订单的公告或可靠信源）
    核心技术突破（专利获批、技术鉴定、产品验证通过）
    主力长期资金流向（需满足2.4条件）
    2.4 资金流向引用的特别约束
    若引用主力资金流向作为判定依据，须同步确认同期大盘（上证指数/深证成指）无异常波动。
    若无法确认大盘因素，须注明“无法排除系统性因素，资金流向信号降级处理”，并将该条降一级使用。
    2.5 大额减持与常规减持的量化判定标准
    类型	量化标准
    大额减持	拟减持比例 ≥ 总股本 2%，或公告当日折价 ≥ 7%（大宗交易）
    常规减持	拟减持比例 ＜ 总股本 1%，且减持方非控股股东/非实控人
    不满足以上任一量化标准的减持，按“中等利空”下限评分，并在判定依据中注明“未达大额减持量化红线”。
    2.6 中性或轻微级别的硬性归类
    以下情形严禁拔高为中等及以上级别：
    日常调研接待
    常规人事变动（非核心高管离职除外）
    无实质影响的例行公告
    纯股价走势描述（如涨停、新高、放量，无经营公告支撑）
    市场统计榜单提及（如“入选XX指数成分股”“上榜龙虎榜”）
    无关行业资讯（行业政策变动但不直接涉及该股经营）
    三、强制打分层级（单向制，50为绝对中性）
    3.1 利好区间（分值越高利好越强）
    级别名称	分值区间	判定标准
    极端重大利好	+85～+95	行业巨头量产落地且公司确认为核心供应商；批量订单正式派送并有公告/合同佐证；业绩即将大幅兑现（如产能释放+锁价长单）；核心技术独家突破并通过权威验证
    中等实质利好	+70～+84	行业景气上行有明确行业数据支撑；多家权威机构一致上调评级/目标价；主力大额持续净流入（已排除大盘因素）；业务订单稳步增长并有合同/公告佐证
    轻微盘面利好	+55～+69	单纯股价创阶段新高；均线系统突破；短期涨幅靠前/涨停；但无实质经营与订单公告支撑
    3.2 中性区间
    级别名称	分值区间	判定标准
    中性	45～55	日常调研接待；常规人事变动；无实质影响的例行公告；市场统计类榜单提及；无关行业资讯；超过30天的旧闻重提（即使内容本身曾为利好/利空）
    3.3 利空区间（分值越低利空越强）
    级别名称	分值区间	判定标准
    轻微利空	30～44	小幅股权变动（非控股股东、变动比例＜总股本0.5%）；低比例折价大宗交易（折价＜5%，且金额不显著）
    中等利空	15～29	常规股东减持（符合2.5“常规减持”标准）；小幅经营扰动（单一产线常规检修、非核心客户流失、非重大诉讼）
    极端重大利空	5～14	大额减持（符合2.5“大额减持”标准）；超高折价大宗出逃（折价≥10%）；业绩预亏/业绩预告大幅下修；监管立案调查/公开谴责/行政处罚

    严格输出纯JSON，无多余文字、无换行注释：
    {{
        "sentiment": "positive/neutral/negative",
        "score": 0-100整数分数,
        "reason": "简洁精准说明影响逻辑"
    }}
    """
    system_prompt = "严格单一个股舆情研判，只针对传入标的分析，无视市场整体、其他个股、跨行业信息，减持行为直接认定个股利空，不进行对冲抹平。"
    temperature = 0.1
    max_tokens = 1024
    retry_times=3
    response = ""
    # 循环重试最多3次
    for attempt in range(1, retry_times + 1):
        try:
            response = generate_text(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens
            )
            response = response.strip()
            print("response: ", response)
            # 拿到非空结果直接跳出重试
            if response:
                break
            print(f"第{attempt}次调用无返回，即将重试...")
        except Exception as e:
            print(f"第{attempt}次调用异常：{str(e)}，即将重试...")
        # 短暂休眠防接口拥堵
        import time
        time.sleep(0.5)

  

    # 三次都失败，直接返回默认中性
    if not response:
        result = {"sentiment": "neutral", "score": 50, "reason": "三次调用AI均无结果，默认中性研判"}
        return result

    # JSON容错补全
    try:
        import json
        # 自动补全缺失右大括号
        if response.count("{") > response.count("}"):
            response += "}"
        result = json.loads(response)
        
        return result
    except:
        result = {"sentiment": "neutral", "score": 50, "reason": "JSON解析失败"}
    
        return result

def _get_news_full_content(url: str, retry_times=3, sleep_sec=0.6) -> str:
    """东方财富财经链接抓取全文"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    for attempt in range(1, retry_times + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            # 东财多正文节点兼容
            article = (
                soup.find("div", class_="article-body")
                or soup.find("div", id="ContentBody")
                or soup.find("div", class_="news-body")
            )
            if article:
                text = article.get_text(strip=True, separator="\n")
                if len(text) > 30:  # 有效内容阈值
                    return text
        except Exception as e:
            print(f"正文抓取第{attempt}次失败：{str(e)[:50]}")
        time.sleep(sleep_sec)
        # 三次全部失败返回空
    return ""


def get_after_close_cutoff() -> datetime:
    now = datetime.now()
    today_open = datetime(now.year, now.month, now.day, 9, 30, 0)
    # 已将大于开盘，就用开盘之后的信息
    if now > today_open:
        return today_open
    
    offset = 1
    # 循环找到上一个工作日（周一~周五）
    while True:
        target_day = now - timedelta(days=offset)
        # weekday 0=周一，4=周五，5/6周六日
        if target_day.weekday() < 5:
            break
        offset += 1
    # 返回该交易日15:00
    return datetime(target_day.year, target_day.month, target_day.day, 15, 0, 0)


def _get_stock_latest_news(stock_code: str, days: int = 7) -> List[Dict]:
    """
    获取个股最新新闻（公告+市场资讯）
    :param stock_code: 股票代码，如 688235（不需要 sh/sz 前缀）
    :param days: 获取最近 N 天的新闻
    :return:     
    "关键词",
            "新闻标题",
            "新闻内容",
            "发布时间",
            "文章来源",
            "新闻链接",
    """
    try:
        # 东方财富：个股最新新闻（最稳定、最全、速度最快）

        df = ak.stock_news_em(symbol=stock_code)
        # print(df)
        # 时间过滤：只保留最近 N 天
        #now = datetime.now()
        cutoff = get_after_close_cutoff()
        # cutoff = now - timedelta(days=days)
    

        news_list = []
        for _, row in df.iterrows():
            news_time = pd.to_datetime(row["发布时间"])
            print("晚于此时间: ", cutoff, " 新闻时间",news_time)

            if news_time >= cutoff:
                news_url = row["新闻链接"]
                # 抓取完整原文，替换残缺content
                full_content = _get_news_full_content(news_url)
                print("full_content: ", news_time, news_url)


                news_list.append({
                    "date": news_time.strftime("%Y-%m-%d %H:%M"),
                    "title": row["新闻标题"],
                    "content": full_content,  # 用全文替换摘要
                    "type": row["文章来源"],  # 公告/新闻/研报
                    "url": row["新闻链接"]
                })

        return news_list

    except Exception as e:
        print(f"获取新闻失败: {e}")
        return []


def recommendations_penalty(stock_code: str, stock_name: str) -> tuple[int,List[str]]:
    news = _get_stock_latest_news(stock_code, days=7)
    print(len(news))

    if not news:
        return 0, []
    penalty = 0
    reason = []
    for n in news:

        result = _analyze_news_sentiment(n['content'], stock_name)
        sentiment = result['sentiment']
        score = float(result['score'])
        # print(result['reason'])
        # -----------------------
        # 利空 → 强惩罚（风控第一）
        # -----------------------
        if sentiment == 'negative':
            reason.append(result['reason'] + '  URL: ' + n['url'])  # 记录利空原因
           
            if score >= 80:
                penalty -= 25   # 重大利空：减持/暴雷/监管
            elif score >= 60:
                penalty -= 15   # 一般利空
            else:
                penalty -= 8    # 轻微利空

        # -----------------------
        # 利好 → 弱奖励（不追高）
        # -----------------------
        elif sentiment == 'positive':
            reason.append(result['reason']  + '  URL: ' + n['url'])  # 记录利好原因
        

            if score >= 80:
                penalty += 6
               # reason.append(result['reason'])  # 记录利好原因

            elif score >= 60:
                penalty += 4
            else:
                penalty += 2

        # print(f"AI分析结果: {result}", "url: ", n['url'])

    # -----------------------
    # ✅ 【正确】循环结束后再封顶
    # -----------------------
    penalty = max(-35, min(10, penalty))  # 利空最多-35，利好最多+10
    return penalty,reason



if __name__ == "__main__":
     #('长电科技','600584')
    penalty,reason = recommendations_penalty("601872", "招商轮船")
    print("新闻分数: ", penalty, reason)
   # if penalty < 0:
    # print("存在利空新闻，建议回避")
    # print("新闻原因: ", reason)
    # news = _get_stock_latest_news("688017", days=7)
    # analyzed_news = []

    # for n in news:

        
    #     print(f"链接: {n['url']}\n {'-'*80}   ")
    #     ai_result = _analyze_news_sentiment(n['title'], n['content'], stock_name="绿的谐波")
    #     analyzed_news.append(ai_result)
    # print(analyzed_news)


    # generate_text()
    # print(len(news))
    # is_positive = has_positive_news(news)
    # is_negative = has_negative_news(news)
    # print("is_positive: ", is_positive, "is_negative: ", is_negative)

