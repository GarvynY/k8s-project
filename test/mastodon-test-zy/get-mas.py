"""
COMP90024 Cluster and Cloud Computing - Assignment 2
Big Data Analytics on the Cloud

Team Information:
Team Name: COMP90024_team_43
Team Members:
- Linyao ZHOU     (Student ID: 1619649)
- Yihao SANG      (Student ID: 1562582)
- Xiwen CHEN      (Student ID: 1542252)
- Yuan GAO        (Student ID: 1602894)
- Yao ZHAO        (Student ID: 1695969)

This file is part of the team's solution for Assignment 2,
demonstrating the use of cloud technologies (Kubernetes, Fission,
ElasticSearch) for social media data analytics related to Australia.
"""
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import json
from bs4 import BeautifulSoup
import re

# 配置
MASTODON_INSTANCE   = "mastodon.au"
MASTODON_ACCESS_TOKEN = "OAe_XIfSurn6S8Cp5RjVlhacOmFLSqI1Pb6w6Zdaog0"
HASHTAGS            = ["AusVotes2025", "auspol", "AusVotes", "Election2025"]
LIMIT               = 10   # 每个标签请求条数

def html_to_text(html_content):
    """将 HTML 转纯文本"""
    soup = BeautifulSoup(html_content or "", 'html.parser')
    for tag in soup(["script", "style"]):
        tag.extract()
    text = soup.get_text(separator=" ")
    return re.sub(r'\s+', ' ', text).strip()

def fetch_tag_timeline(tag, token, limit=10):
    """
    调用 Mastodon API 获取指定标签的 timeline，
    返回不超过 limit 条状态（帖子）的 JSON 列表。
    """
    url = f"https://{MASTODON_INSTANCE}/api/v1/timelines/tag/{tag}"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    params = {"limit": limit}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[错误] 获取 #{tag} 时出错: {e}")
        return []

def main():
    for tag in HASHTAGS:
        print(f"\n===== #{tag} 的最新 {LIMIT} 条帖子 =====\n")
        posts = fetch_tag_timeline(tag, MASTODON_ACCESS_TOKEN, LIMIT)
        if not posts:
            print("（未获取到任何帖子）")
            continue

        for i, post in enumerate(posts, 1):
            created = post.get("created_at", "")
            acct    = post.get("account", {}).get("acct", "")
            content = html_to_text(post.get("content", ""))
            print(f"帖子 {i}:")
            print(f"  ID       : {post.get('id')}")
            print(f"  用户     : {acct}")
            print(f"  创建时间 : {created}")
            print(f"  内容     : {content}\n")
    # 结束
    print("Done.")

if __name__ == "__main__":
    main()
