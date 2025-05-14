#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import csv
import random
from datetime import datetime, timedelta, timezone
from mastodon import Mastodon
from textblob import TextBlob
from bs4 import BeautifulSoup
import re

# 1) 登录
mastodon = Mastodon(
    client_id   = 'pytooter_clientcred.secret',
    access_token= 'pytooter_usercred.secret',
    api_base_url= 'https://mastodon.au'
)

# 2) 定义抓取参数
KEYWORDS = [
    # 英文关键词
    'Australia Election',
    'AusPol',
    'AUSElection',

    # 热门标签（大小写变体）
    'ausvotes2025', '#ausvotes2025',
    'auspol2025', '#auspol2025','ausvotes',

    # 核心政党领导人
    'Albanese', 'Dutton', 'Bandt',

    # 基本政党
    'Labor', 'Liberal', 'Greens'
]

CITY_COORDS = {
    "Sydney":      "-33.868820,151.209296",
    "Melbourne":   "-37.813629,144.963058",
    "Brisbane":    "-27.469770,153.025131",
    "Perth":       "-31.950527,115.860458",
    "Adelaide":    "-34.928497,138.600739",
    "Canberra":    "-35.280937,149.130009",
    "Hobart":      "-42.882137,147.327195",
    "Darwin":      "-12.463440,130.845642",
    "Gold Coast":  "-28.016667,153.400000"
}

CITY_CHOICES = list(CITY_COORDS.keys())

# 修改为灵活设置抓取的天数
def get_since_date(days_back):
    """根据用户选择的天数返回起始日期"""
    return datetime.now(timezone.utc) - timedelta(days=days_back)

# 用户可以选择爬取过去的天数（7, 30, 60 天）
days_back = 30  # 可以设置为 7, 30 或 60
SINCE_DT = get_since_date(days_back)

PAGE_LIMIT    = 100          # 每页最多 40 条
OUTPUT_JSON   = 'aus_election_statuses30days.json'
OUTPUT_CSV    = 'aus_election_statuses30days.csv'

def clean_html_content(raw_html):
    """从 Mastodon HTML 内容中提取纯文本"""
    soup = BeautifulSoup(raw_html, 'html.parser')
    return soup.get_text(separator=' ', strip=True)

def get_post_time_of_day(created_at):
    """根据创建时间获取帖子发布时间段"""
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    hour = created_at.hour
    if 0 <= hour < 6:
        return 'Night'
    elif 6 <= hour < 12:
        return 'Morning'
    elif 12 <= hour < 18:
        return 'Afternoon'
    else:
        return 'Evening'

def get_post_day_of_week(created_at):
    """根据创建时间获取帖子发布的星期几"""
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    return created_at.strftime('%A')

def get_sentiment_score(content):
    """获取情感分析分数"""
    analysis = TextBlob(content)
    return analysis.sentiment.polarity  # 评分范围为[-1, 1]

def get_emotion_label(sentiment_score):
    """根据情感分数返回情感标签"""
    if sentiment_score > 0:
        return 'positive'
    elif sentiment_score < 0:
        return 'negative'
    else:
        return 'neutral'

def infer_location(account) -> str:
    """从 Mastodon 账户字段中推断城市名"""
    for f in getattr(account, "fields", []):
        if "location" in f.get("name", "").lower():
            val = f.get("value", "") or ""
            val = re.sub(r'\s*,?\s*Australia$', '', val, flags=re.IGNORECASE).strip()

            # 尝试从 span 中提取
            spans = re.findall(r'<span>([^<]+)</span>', val)
            for city in spans:
                for c in CITY_CHOICES:
                    if city.strip().lower() == c.lower():
                        return c

            # 去除 HTML 标签再匹配
            text = re.sub(r'<[^>]+>', '', val)
            for c in CITY_CHOICES:
                if re.search(rf"\b{re.escape(c)}\b", text, re.IGNORECASE):
                    return c
    return ""

def geocode_location(loc: str) -> str:
    """根据城市名称获取经纬度字符串"""
    return CITY_COORDS.get(loc, "")

# 3) 抓取函数（分页 + 时间过滤）
def fetch_keyword(keyword, SINCE_DT, PAGE_LIMIT=20):
    """抓取关键词相关的动态，直到达到时间限制"""
    all_statuses = []
    max_id = None

    while True:
        statuses = mastodon.timeline_hashtag(
            hashtag=keyword.replace('#', ''),  # 去掉可能的 #
            limit=PAGE_LIMIT,
            max_id=max_id
        )

        if not statuses:
            break

        for st in statuses:
            dt = st['created_at']
            if dt < SINCE_DT:
                return all_statuses

            sentiment_score = get_sentiment_score(st['content'])
            emotion_label = get_emotion_label(sentiment_score)

            location_inferred = bool(infer_location(st['account']))
            if not location_inferred:
                location = random.choice(list(CITY_COORDS.keys()))
            geolocation = geocode_location(location)

            clean_content = clean_html_content(st['content'])

            all_statuses.append({
                'id': st['id'],
                'created_at': st['created_at'],
                'content': clean_content,
                'post_time_of_day': get_post_time_of_day(st['created_at']),
                'post_day_of_week': get_post_day_of_week(st['created_at']),
                'sentiment_score': sentiment_score,
                'emotion_label': emotion_label,
                'location': location,
                'geolocation': geolocation,
                'account': st['account']['acct'],
                'reblogs_count': st['reblogs_count'],
                'favourites_count': st['favourites_count'],
                'url': st['url'],
            })

        # 更新 max_id，以便抓取下一页数据
        max_id = int(statuses[-1]['id']) - 1

    return all_statuses

def convert_datetime_to_str(statuses):
    """将 datetime 对象转换为字符串"""
    for st in statuses:
        st['created_at'] = st['created_at'].isoformat()  # 转换为 ISO 格式字符串
    return statuses

def save_to_csv(statuses, output_csv):
    """将抓取到的数据保存为 CSV 格式"""
    keys = statuses[0].keys()
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(statuses)

# 4) 逐关键词抓取，合并去重
all_data = {}
for kw in KEYWORDS:
    print(f'>>> 正在抓取关键词：{kw}')
    sts = fetch_keyword(kw, SINCE_DT)
    for s in sts:
        all_data[s['id']] = s

print(f'抓取完成，共 {len(all_data)} 条动态（去重后）')

# 5) 转换 datetime 为字符串后写入文件
with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
    all_statuses = convert_datetime_to_str(list(all_data.values()))
    json.dump(all_statuses, f, ensure_ascii=False, indent=2)

# 6) 保存为 CSV 格式
save_to_csv(all_statuses, OUTPUT_CSV)

print(f'已保存到 {OUTPUT_JSON} 和 {OUTPUT_CSV}')
