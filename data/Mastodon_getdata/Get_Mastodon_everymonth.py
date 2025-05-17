#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import csv
import random
import os
import re
from datetime import datetime, timedelta, timezone
from dateutil.relativedelta import relativedelta
from mastodon import Mastodon
from textblob import TextBlob
from bs4 import BeautifulSoup

# ------------------------
# 1) 登录
# ------------------------
mastodon = Mastodon(
    client_id='pytooter_clientcred.secret',
    access_token='pytooter_usercred.secret',
    api_base_url='https://mastodon.au'
)

# ------------------------
# 2) 抓取参数
# ------------------------
KEYWORDS = [
    'Australia Election', 'AusPol', 'AUSElection',
    'ausvotes2025', '#ausvotes2025',
    'auspol2025', '#auspol2025', 'ausvotes',
    'Albanese', 'Dutton', 'Bandt',
    'Labor', 'Liberal', 'Greens'
]

CITY_COORDS = {
    "Sydney": "-33.868820,151.209296",
    "Melbourne": "-37.813629,144.963058",
    "Brisbane": "-27.469770,153.025131",
    "Perth": "-31.950527,115.860458",
    "Adelaide": "-34.928497,138.600739",
    "Canberra": "-35.280937,149.130009",
    "Hobart": "-42.882137,147.327195",
    "Darwin": "-12.463440,130.845642",
    "Gold Coast": "-28.016667,153.400000"
}
CITY_CHOICES = list(CITY_COORDS.keys())
PAGE_LIMIT = 40

# ------------------------
# 3) 工具函数
# ------------------------

def clean_html_content(raw_html):
    soup = BeautifulSoup(raw_html, 'html.parser')
    return soup.get_text(separator=' ', strip=True)

def get_post_time_of_day(created_at):
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
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    return created_at.strftime('%A')

def get_sentiment_score(content):
    analysis = TextBlob(content)
    return analysis.sentiment.polarity

def get_emotion_label(sentiment_score):
    if sentiment_score > 0:
        return 'positive'
    elif sentiment_score < 0:
        return 'negative'
    else:
        return 'neutral'

def infer_location(account) -> str:
    for f in getattr(account, "fields", []):
        if "location" in f.get("name", "").lower():
            val = f.get("value", "") or ""
            val = re.sub(r'\s*,?\s*Australia$', '', val, flags=re.IGNORECASE).strip()
            spans = re.findall(r'<span>([^<]+)</span>', val)
            for city in spans:
                for c in CITY_CHOICES:
                    if city.strip().lower() == c.lower():
                        return c
            text = re.sub(r'<[^>]+>', '', val)
            for c in CITY_CHOICES:
                if re.search(rf"\b{re.escape(c)}\b", text, re.IGNORECASE):
                    return c
    return ""

def geocode_location(loc: str) -> str:
    return CITY_COORDS.get(loc, "")

def convert_datetime_to_str(statuses):
    for st in statuses:
        if isinstance(st['created_at'], datetime):
            st['created_at'] = st['created_at'].isoformat()
    return statuses

def save_to_csv(statuses, output_csv):
    if not statuses:
        return
    keys = statuses[0].keys()
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(statuses)

# ------------------------
# 4) 抓取函数（含时间窗口）
# ------------------------

def fetch_keyword(keyword, start_time, end_time, PAGE_LIMIT=40):
    all_statuses = []
    max_id = None

    while True:
        statuses = mastodon.timeline_hashtag(
            hashtag=keyword.replace('#', ''),
            limit=PAGE_LIMIT,
            max_id=max_id
        )

        if not statuses:
            break

        for st in statuses:
            dt = st['created_at']
            if dt < start_time:
                return all_statuses
            if dt >= end_time:
                continue  # 超出抓取窗口

            sentiment_score = get_sentiment_score(st['content'])
            emotion_label = get_emotion_label(sentiment_score)

            location = infer_location(st['account'])
            if not location:
                location = random.choice(CITY_CHOICES)
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

        max_id = int(statuses[-1]['id']) - 1

    return all_statuses

# ------------------------
# 5) 批量抓取每月3天数据
# ------------------------

base_output_dir = "monthly_outputs"
os.makedirs(base_output_dir, exist_ok=True)

today = datetime.now(timezone.utc)

for i in range(6):
    month_date = today - relativedelta(months=i)
    month_str = month_date.strftime("%Y-%m")
    print(f"\n### 正在处理月份：{month_str}")

    selected_days = [5, 15, 25]
    monthly_data = {}

    for day in selected_days:
        try:
            start_time = datetime(month_date.year, month_date.month, day, tzinfo=timezone.utc)
        except ValueError:
            continue
        end_time = start_time + timedelta(days=1)
        print(f"  >>> 抓取日期：{start_time.date()}")

        for kw in KEYWORDS:
            print(f"     - 关键词：{kw}")
            sts = fetch_keyword(kw, start_time, end_time, PAGE_LIMIT=40)
            for s in sts:
                monthly_data[s['id']] = s

    if not monthly_data:
        print(f"  ✘ 跳过：{month_str}（无数据）")
        continue

    filename_csv = os.path.join(base_output_dir, f"aus_election_{month_date.strftime('%Y_%m')}.csv")
    all_statuses = convert_datetime_to_str(list(monthly_data.values()))
    save_to_csv(all_statuses, filename_csv)
    print(f"  ✔ 已保存：{filename_csv}")
