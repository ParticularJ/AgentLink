#!/bin/bash
# 盘中交易询问-早盘 (10:00)
# 询问用户是否需要买入或卖出
unset ALL_PROXY all_proxy http_proxy https_proxy HTTP_PROXY HTTPS_PROXY

echo "发送盘中交易询问（早盘）..."

# 发送到飞书群
/home/jarvis/miniconda3/envs/vllm/bin/python -c "
import requests
import json
from datetime import datetime

FEISHU_APP_ID = 'cli_a93eb458ceb81cc0'
FEISHU_APP_SECRET = '1i18JUKuFhQEejUOkNividRbMdJBMpV8'
FEISHU_GROUP_ID = 'oc_0ac1e4e8d09f939d887f4992bba2886b'

# 获取 token
resp = requests.post(
    'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
    json={'app_id': FEISHU_APP_ID, 'app_secret': FEISHU_APP_SECRET},
    timeout=10
)
token = resp.json()['tenant_access_token']

# 读取持仓和现金信息
holdings = json.load(open('/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/my_holdings/holdings.json'))
cash_info = json.load(open('/home/jarvis/.openclaw/workspace/skills/Chinese_Stock_back/my_holdings/cash_balance.json'))

available_cash = cash_info.get('available_cash', 0)
holdings_text = '\n'.join([f\"- {h['name']}({h['code']}): 持仓{h['shares']}股，成本{h['cost']:.2f}\" for h in holdings]) if holdings else '（暂无持仓）'

card = {
    'header': {
        'title': {'tag': 'plain_text', 'content': '📊 盘中交易询问 | 10:00'},
        'subtitle': {'tag': 'plain_text', 'content': f'{datetime.now().strftime(\"%Y-%m-%d %H:%M\")} 开盘时段'},
        'template': 'orange'
    },
    'elements': [
        {'tag': 'div', 'text': {'tag': 'lark_md', 'content': '**盘中交易询问**\n\n当前是否有交易需求？'}},
        {'tag': 'hr'},
        {'tag': 'div', 'text': {'tag': 'lark_md', 'content': f'**💰 可用资金：{available_cash:,.2f} 元**'}},
        {'tag': 'hr'},
        {'tag': 'div', 'text': {'tag': 'lark_md', 'content': '**📋 当前持仓参考**\n' + holdings_text}},
        {'tag': 'hr'},
        {'tag': 'div', 'text': {'tag': 'lark_md', 'content': '**💬 操作方式**\n如需买入/卖出，请直接回复指令，例如：\n- 买入 600105 100股 # 50.0\n- 卖出 600105 50股 # 55.0'}},
        {'tag': 'note', 'elements': [{'tag': 'plain_text', 'content': '⚠️ 交易时段，请谨慎操作'}]}
    ]
}

resp = requests.post(
    'https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id',
    headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
    json={'receive_id': FEISHU_GROUP_ID, 'msg_type': 'interactive', 'content': json.dumps(card)},
    timeout=15
)
print('发送成功' if resp.status_code == 200 else f'发送失败: {resp.text}')
" 2>&1

exit 0