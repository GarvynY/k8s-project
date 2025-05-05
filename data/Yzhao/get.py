#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
from datetime import datetime, timedelta
from dateutil import parser as date_parser
from mastodon import Mastodon

# 1) 登录
mastodon = Mastodon(
    client_id   = 'clientcred.secret',
    access_token= 'usercred.secret',
    api_base_url= 'https://mastodon.au'
)

# 2) 定义抓取参数
KEYWORDS = [
    '澳大利亚大选',     # 中文关键词
    '澳洲大选',
    'Australia Election', # 英文关键词
    'AusPol',             # 常见标签
    'AUSElection'
]
DAYS_BACK     = 5 * 30      # 粗略 5 个月
SINCE_DT      = datetime.utcnow() - timedelta(days=DAYS_BACK)
PAGE_LIMIT    = 40          # 每页最多 40 条
OUTPUT_JSON   = 'aus_election_statuses.json'

# 3) 抓取函数（分页 + 时间过滤）
def fetch_keyword(keyword):
    """抓取单个关键词的所有分页动态，直到遇到五个月前的为止。"""
    all_statuses = []
    max_id = None

    while True:
        resp = mastodon.search(
            q           = keyword,
            result_type = 'statuses',
            limit       = PAGE_LIMIT,
            max_id      = max_id
        )

        # search() 返回的 dict 带 'statuses' 键
        statuses = resp['statuses']
        if not statuses:
            break

        for st in statuses:
            dt = date_parser.isoparse(st['created_at'])
            if dt < SINCE_DT:
                # 已经超出我们想要的时间范围，结束本关键词抓取
                return all_statuses
            all_statuses.append({
                'id'         : st['id'],
                'created_at' : st['created_at'],
                'content'    : st['content'],
                'account'    : st['account']['acct'],
                'reblogs_count': st['reblogs_count'],
                'favourites_count': st['favourites_count'],
                'url'        : st['url']
            })

        # 翻页：取最末条 id 减 1
        max_id = statuses[-1]['id'] - 1

    return all_statuses

# 4) 逐关键词抓取，合并去重
all_data = {}
for kw in KEYWORDS:
    print(f'>>> 正在抓取关键词：{kw}')
    sts = fetch_keyword(kw)
    for s in sts:
        all_data[s['id']] = s

print(f'抓取完成，共 {len(all_data)} 条动态（去重后）')

# 5) 写入文件
with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
    json.dump(list(all_data.values()), f, ensure_ascii=False, indent=2)

print(f'已保存到 {OUTPUT_JSON}')