import re
import time
import csv
import os
import random
import json
from datetime import datetime, timedelta, timezone

from mastodon import Mastodon
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# ——— Mastodon 凭据 ———
MASTODON_CLIENT_ID     = "2BFvlyAmZRT3id9ZKNJJbXD6-nPPh8jo2WJaHTmQ1bA"
MASTODON_CLIENT_SECRET = "FQpO_BwYURSno8vbkVkk5USCZPA9SAzI_G9FUMts4bo"
MASTODON_ACCESS_TOKEN  = "Tvx3jwk5Ilz4ixUzG_DTrNny98G4RYfQym8sVDez9F8"

# ——— 配置 ———
API_BASE_URL = "https://mastodon.social"
HASHTAG      = "ausvotes"
OUTPUT_CSV   = "mastodon_election_1week.csv"
OUTPUT_JSON  = "mastodon_election_1week.json"
PAGE_SIZE    = 40

# ——— 搜索关键词 ———
KEYWORDS = [
    'Australia Election', 'AusPol', 'AUSElection',
    'ausvotes2025', '#ausvotes2025',
    'auspol2025', '#auspol2025',
    'Albanese', 'Dutton', 'Bandt',
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

# ——— 初始化 ———
masto = Mastodon(
    client_id=MASTODON_CLIENT_ID,
    client_secret=MASTODON_CLIENT_SECRET,
    access_token=MASTODON_ACCESS_TOKEN,
    api_base_url=API_BASE_URL
)
sentiment_analyzer = SentimentIntensityAnalyzer()

def clean_content(html: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', html)).strip()

def contains_keyword(text: str) -> bool:
    low = text.lower()
    return any(kw.lower() in low for kw in KEYWORDS)

def get_time_of_day(ts_iso: str) -> str:
    h = datetime.fromisoformat(ts_iso).hour
    if h < 6:   return "early morning"
    if h < 12:  return "morning"
    if h < 18:  return "afternoon"
    return "evening"

def get_day_of_week(ts_iso: str) -> str:
    return ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][
        datetime.fromisoformat(ts_iso).weekday()
    ]

def analyze_sentiment(text: str):
    vs = sentiment_analyzer.polarity_scores(text)
    s = vs["compound"]
    if s >= 0.05:    return s, "positive"
    if s <= -0.05:   return s, "negative"
    return s, "neutral"

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

def load_existing_ids(csv_file):
    try:
        with open(csv_file, "r", encoding="utf-8") as f:
            return set(row["id"] for row in csv.DictReader(f))
    except FileNotFoundError:
        return set()

def fetch_posts_for_week(start_date: datetime, end_date: datetime):
    rows = []
    max_id = None
    page = 1

    for keyword in KEYWORDS:
        print(f"Fetching posts for keyword: {keyword}")
        while True:
            statuses = masto.timeline_hashtag(keyword, limit=PAGE_SIZE, max_id=max_id)
            if not statuses:
                break

            for s in statuses:
                created_utc = s.created_at.astimezone(timezone.utc)
                if created_utc < start_date:
                    return rows
                if created_utc > end_date:
                    continue

                content = clean_content(s.content)
                if not contains_keyword(content):
                    continue

                ts_iso = created_utc.isoformat()
                score, label = analyze_sentiment(content)

                loc = infer_location(s.account)
                if not loc:
                    loc = random.choice(CITY_CHOICES)
                geo = geocode_location(loc)

                rows.append({
                    "id":               str(s.id),
                    "created_at":       ts_iso,
                    "post_time_of_day": get_time_of_day(ts_iso),
                    "post_day_of_week": get_day_of_week(ts_iso),
                    "content":          content,
                    "sentiment_score":  score,
                    "emotion_label":    label,
                    "location":         loc,
                    "geolocation":      geo,
                })

            max_id = int(statuses[-1].id) - 1
            page += 1
            time.sleep(1)

    return rows


def save_to_csv_append(rows, csv_file):
    if not rows:
        print("No data to save.")
        return

    existing_ids = load_existing_ids(csv_file)
    new_rows = [row for row in rows if row["id"] not in existing_ids]
    if not new_rows:
        print("No new posts found.")
        return

    file_exists = os.path.exists(csv_file)
    with open(csv_file, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=new_rows[0].keys())
        if not file_exists:
            w.writeheader()
        w.writerows(new_rows)
    print(f"Appended {len(new_rows)} new posts to {csv_file}")

def save_to_json_append(rows, json_file):
    if not rows:
        print("No data to save.")
        return

    try:
        if os.path.exists(json_file):
            with open(json_file, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
        else:
            existing_data = []

        existing_ids = {entry["id"] for entry in existing_data}
        new_rows = [row for row in rows if row["id"] not in existing_ids]
        if not new_rows:
            print("No new posts found for JSON.")
            return

        existing_data.extend(new_rows)
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=4)
        print(f"Appended {len(new_rows)} new posts to {json_file}")
    except Exception as e:
        print(f"Error saving to JSON: {e}")

# ——— 程序入口 ———
if __name__ == "__main__":
    try:
        # 获取最近一个月的数据
        now = datetime.now(timezone.utc)
        one_month_ago = now - timedelta(days=7)

        print(f"[{now.isoformat()}] Fetching posts from {one_month_ago.date()} to {now.date()} ...")
        monthly_data = fetch_posts_for_week(one_month_ago, now)

        # 保存到 CSV 和 JSON
        save_to_csv_append(monthly_data, OUTPUT_CSV)
        save_to_json_append(monthly_data, OUTPUT_JSON)

    except KeyboardInterrupt:
        print("Stopped by user.")
