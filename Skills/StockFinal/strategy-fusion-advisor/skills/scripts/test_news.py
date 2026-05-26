import akshare as ak
import pandas as pd
from bs4 import BeautifulSoup
import requests, time
from datetime import datetime, timedelta
from typing import List, Dict
from llm_client import generate_text


def _analyze_news_sentiment(news_content: str, stock_name: str = "百济神州") -> dict:
    prompt = f"""
    你是专业A股个股舆情分析师，只聚焦当前指定个股做研判，严禁扩散分析其他股票、其他行业无关信息。
    本次仅分析标的：{stock_name}

    新闻内容：{news_content}
    研判硬性规则：
    1. 仅评判本条新闻对该股单独影响，其余个股、大盘、跨板块行情全部忽略
    2. 股东大额减持、高折价大宗、业绩暴雷、监管问询统一认定实质性利空，不做任何对冲抵消
    3. 仅围绕该股自身业绩、产能落地、定点供货、订单确认、核心技术突破、主力长期资金流向判定多空
    4. 日常调研、人事变动、普通公告、纯股价走势描述、市场统计榜单归类中性或轻微级别，严禁拔高

    【强制打分层级（必须严格执行）】
    1. 极端重大利好(85-95)：行业巨头量产落地、公司定点核心供应商、批量订单派送、业绩即将大幅兑现、核心技术独家突破
    2. 中等实质利好(70-84)：行业景气上行、机构一致看好、主力大额持续净流入、业务订单稳步增长
    3. 轻微盘面利好(55-69)：单纯股价新高、均线突破、短期涨幅走高，无实质经营与订单支撑
    4. 中性(45-55)：无实质影响公告、市场汇总提及、无关行业资讯
    5. 轻微利空(30-44)：小幅股权变动、低比例折价交易
    6. 中等利空(50-69)：常规股东减持、小幅经营扰动
    7. 极端重大利空(70-90)：大额减持、超高折价出逃、业绩预亏、监管处罚

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
        return {"sentiment": "neutral", "score": 50, "reason": "三次调用AI均无结果，默认中性研判"}

    # JSON容错补全
    try:
        import json
        # 自动补全缺失右大括号
        if response.count("{") > response.count("}"):
            response += "}"
        return json.loads(response)
    except:
        return {"sentiment": "neutral", "score": 50, "reason": "JSON解析失败"}

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
        now = datetime.now()
        cutoff = now - timedelta(days=days)
        
        news_list = []
        for _, row in df.iterrows():
            news_time = pd.to_datetime(row["发布时间"])
            if news_time >= cutoff:
                news_url = row["新闻链接"]
                # 抓取完整原文，替换残缺content
                full_content = _get_news_full_content(news_url)
                #print("full_content: ", full_content)


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
    news = _get_stock_latest_news(stock_code, days=3)
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
            reason.append(result['reason'])  # 记录利空原因
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
           # reason.append(result['reason'])  # 记录利空原因

            if score >= 80:
                penalty += 6
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
    penalty,reason = recommendations_penalty("688017", "绿的谐波")
    print("新闻分数: ", penalty)
   # if penalty < 0:
    print("存在利空新闻，建议回避")
    print("新闻原因: ", reason)
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

