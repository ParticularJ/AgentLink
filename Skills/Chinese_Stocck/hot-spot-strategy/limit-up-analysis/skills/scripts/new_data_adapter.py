import requests
import pandas as pd
import time
import os

# 强制不走代理
os.environ["HTTP_PROXY"] = ""
os.environ["HTTPS_PROXY"] = ""

def get_zt_pool_full():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36",
        "Referer": "https://quote.eastmoney.com/ztb/",
        "Origin": "https://quote.eastmoney.com",
        "Host": "push2ex.eastmoney.com"
    }

    url = "https://push2ex.eastmoney.com/getTopicZTPool"
    today = time.strftime("%Y%m%d")
    timestamp = int(time.time() * 1000)

    # 最新有效参数（2026-04-29亲测）
    params = {
        "ut": "7eea3edcaed734bea9cbfc24409ed989",  # 最新ut
        "dpt": "wz.ztzt",
        "Pageindex": 0,
        "pagesize": 200,
        "sort": "fbt:asc",
        "date": today,
        "_": timestamp  # 必须带时间戳
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        result = resp.json()

        # 关键：数据在 data["pool"] 里
        pool = result.get("data", {}).get("pool", [])
        if not pool:
            print("⚠️ pool 为空，接口无数据")
            return pd.DataFrame()

        df = pd.DataFrame(pool)
        # 字段映射（完全对齐你要的16列）
        map_dict = {
            "c": "代码",
            "n": "名称",
            "zdp": "涨跌幅",
            "p": "最新价",
            "amount": "成交额",
            "ltsz": "流通市值",
            "tshare": "总市值",
            "hs": "换手率",
            "fund": "封板资金",
            "fbt": "首次封板时间",
            "lbt": "最后封板时间",
            "zbc": "炸板次数",
            "zttj": "涨停统计",
            "lbc": "连板数",
            "hybk": "所属行业"
        }

        df = df.rename(columns=map_dict)
        df["序号"] = range(1, len(df) + 1)

        cols = [
            "序号", "代码", "名称", "涨跌幅", "最新价", "成交额",
            "流通市值", "总市值", "换手率", "封板资金",
            "首次封板时间", "最后封板时间", "炸板次数",
            "涨停统计", "连板数", "所属行业"
        ]
        df = df[cols]
        return df

    except Exception as e:
        print(f"❌ 异常: {e}")
        return pd.DataFrame()

if __name__ == "__main__":
    df = get_zt_pool_full()
    if not df.empty:
        print(f"✅ 获取成功，共 {len(df)} 只涨停股")
        print(df.head(10))
    else:
        print("❌ 仍未获取到数据")