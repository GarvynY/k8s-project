#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import csv
from datetime import datetime, timedelta, timezone
from mastodon import Mastodon
from textblob import TextBlob
from bs4 import BeautifulSoup

# 1) 登录
mastodon = Mastodon(
    client_id   = 'pytooter_clientcred.secret',
    access_token= 'pytooter_usercred.secret',
    api_base_url= 'https://mastodon.au'
)

# 2) 定义抓取参数
KEYWORDS = [
    # 中文关键词
    '澳大利亚大选',
    '澳洲大选',

    # 英文关键词
    'Australia Election',
    'AusPol',
    'AUSElection',

    # 热门标签（大小写变体）
    'ausvotes2025', '#ausvotes2025',
    'auspol2025', '#auspol2025',

    # 核心政党领导人
    'Albanese', 'Dutton', 'Bandt',

    # 基本政党
    'Labor', 'Liberal', 'Greens'
]

DAYS_BACK     = 5 * 30      # 粗略 5 个月
SINCE_DT = datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)
PAGE_LIMIT    = 40          # 每页最多 40 条
OUTPUT_JSON   = 'aus_election_statuses.json'
OUTPUT_CSV    = 'aus_election_statuses.csv'

def clean_html_content(raw_html):
    """从 Mastodon HTML 内容中提取纯文本"""
    soup = BeautifulSoup(raw_html, 'html.parser')
    return soup.get_text(separator=' ', strip=True)

def get_post_time_of_day(created_at):
    # 如果 created_at 是字符串，先将其转换为 datetime 对象
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))  # 处理 ISO 8601 格式中的 'Z'

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
    # 如果 created_at 是字符串，先将其转换为 datetime 对象
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))  # 处理 ISO 8601 格式中的 'Z'

    # 如果 created_at 是 datetime 对象，直接使用 strftime 获取星期几
    return created_at.strftime('%A')  # 返回星期几，如 Monday, Tuesday 等


# 获取情感分析分数
def get_sentiment_score(content):
    analysis = TextBlob(content)
    return analysis.sentiment.polarity  # 评分范围为[-1, 1]

# 根据情感分数返回情感标签
def get_emotion_label(sentiment_score):
    if sentiment_score > 0:
        return 'positive'
    elif sentiment_score < 0:
        return 'negative'
    else:
        return 'neutral'

# 增加地理信息
def get_location_info(account):
    # 提取位置和地理坐标
    location = account.get('location', None)
    geolocation = account.get('geolocation', None)
    return location, geolocation

# 3) 抓取函数（分页 + 时间过滤）
def fetch_keyword(keyword, SINCE_DT, PAGE_LIMIT=20):
    """抓取关键词相关的动态，直到达到五个月前的动态为止"""
    all_statuses = []
    max_id = None
    total_fetched = 0  # 计数器，限制抓取 300 条数据

    while total_fetched < 300:  # 只抓取 300 条数据
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

            # 情感分析与情感标签
            sentiment_score = get_sentiment_score(st['content'])
            emotion_label = get_emotion_label(sentiment_score)

            # 获取用户的位置信息和地理坐标
            location, geolocation = get_location_info(st['account'])

            # 使用 clean_html_content 来清理 HTML 标签，只保留文本内容
            clean_content = clean_html_content(st['content'])

            # 构建当前动态的字典，添加到 all_statuses 列表中
            all_statuses.append({
                'id': st['id'],
                'created_at': st['created_at'],
                'content': clean_content,  # 清理后的内容
                'post_time_of_day': get_post_time_of_day(st['created_at']),  # 发布时间段
                'post_day_of_week': get_post_day_of_week(st['created_at']),  # 周几
                'sentiment_score': sentiment_score,  # 情感分数
                'emotion_label': emotion_label,  # 情感标签
                'location': location,  # 用户位置
                'geolocation': geolocation,  # 用户地理坐标
                'account': st['account']['acct'],
                'reblogs_count': st['reblogs_count'],
                'favourites_count': st['favourites_count'],
                'url': st['url'],
            })

            total_fetched += 1  # 每抓取一条动态，计数器加一

            if total_fetched >= 300:  # 如果已抓取 300 条，停止
                break

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
    keys = statuses[0].keys()  # 获取字典的键名作为 CSV 的列头
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(statuses)

# 4) 逐关键词抓取，合并去重
all_data = {}
for kw in KEYWORDS:
    print(f'>>> 正在抓取关键词：{kw}')
    sts = fetch_keyword(kw, SINCE_DT)  # 传递 SINCE_DT 参数
    for s in sts:
        all_data[s['id']] = s

print(f'抓取完成，共 {len(all_data)} 条动态（去重后）')

# 5) 转换 datetime 为字符串后写入文件
with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
    # 转换所有日期为字符串
    all_statuses = convert_datetime_to_str(list(all_data.values()))
    json.dump(all_statuses, f, ensure_ascii=False, indent=2)

# 6) 保存为 CSV 格式
save_to_csv(all_statuses, OUTPUT_CSV)

print(f'已保存到 {OUTPUT_JSON} 和 {OUTPUT_CSV}')
