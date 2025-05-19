import os
import time
import random
from datetime import datetime, timezone

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import praw
import prawcore
from elasticsearch import Elasticsearch, helpers

REDDIT_CLIENT_ID     = "52joX-SatVEUkn4_C_2SCw"
REDDIT_CLIENT_SECRET = "SFd7h3i3Adk_8uh3VhgxHonz6iJXag"
REDDIT_USER_AGENT    = "aus_election_scraper/0.1 by linyaozhou"

KEYWORDS = [
    'Australia Election', 'AusPol', 'AUSElection',
    'ausvotes2025', '#ausvotes2025',
    'auspol2025', '#auspol2025', 'ausvotes',
    'Albanese', 'Dutton', 'Bandt',
    'Labor', 'Liberal', 'Greens'
]

now = datetime.now(timezone.utc)
SINCE_MONTH_START = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

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

ES_HOST  = "https://elasticsearch-master.elastic.svc.cluster.local"
ES_USER  = "elastic"
ES_PASS  = "elastic"
ES_INDEX = "reddit_zy"

GRAB_TIME_LIMIT = float(os.environ.get('GRAB_TIME_LIMIT', '40.0'))

def get_time_of_day(dt):
    h = dt.hour
    if   h < 6:   return "Night"
    elif h < 12:  return "Morning"
    elif h < 18:  return "Afternoon"
    else:         return "Evening"

sid = SentimentIntensityAnalyzer()
def analyze_sentiment(text: str):
    vs = sid.polarity_scores(text)
    c  = vs["compound"]
    if   c >=  0.05: label = "positive"
    elif c <= -0.05: label = "negative"
    else:            label = "neutral"
    return c, label

def get_last_run_time(es_client, index_name):
    try:
        resp = es_client.search(
            index=index_name, size=1,
            sort=[{"created_at": "desc"}],
            _source=["created_at"]
        )
        hits = resp.get("hits", {}).get("hits", [])
        if hits:
            return datetime.fromisoformat(hits[0]["_source"]["created_at"])
    except Exception as e:
        print("error", e)
    return None

# ------------------------
# 3) Fission Handler
# ------------------------
def main(context=None, data=None):
    """
    Fission 。
    """
    start_ts = time.time()

    reddit = praw.Reddit(
        client_id=     REDDIT_CLIENT_ID,
        client_secret= REDDIT_CLIENT_SECRET,
        user_agent=    REDDIT_USER_AGENT,
        requestor_kwargs={'timeout': 10}
    )
    es = Elasticsearch(
        [ES_HOST],
        http_auth=(ES_USER, ES_PASS),
        use_ssl=True,
        verify_certs=False,
        ssl_show_warn=False,
    )
    if not es.indices.exists(index=ES_INDEX):
        es.indices.create(index=ES_INDEX)

    last_time = get_last_run_time(es, ES_INDEX) or SINCE_MONTH_START

    records = []
    seen_ids = set()
    stop_flag = False

    for kw in KEYWORDS:
        if stop_flag:
            break
        try:
            results = reddit.subreddit('all').search(
                query=kw, sort='new', time_filter='all', limit=None
            )
        except prawcore.exceptions.Redirect:
            print(f"pass。")
            continue

        for post in results:
            if time.time() - start_ts > GRAB_TIME_LIMIT:
                stop_flag = True
                break

            dt = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)
            if dt <= last_time:
                break
            if post.id in seen_ids:
                continue

            title, body = post.title or "", post.selftext or ""
            if not (title.strip() or body.strip()): continue
            if body.strip() in ('[deleted]','[removed]'): continue

            score,label = analyze_sentiment(f"{title}\n{body}".strip())
            loc = random.choice(CITY_CHOICES)
            records.append({
                "_index": ES_INDEX, "_id": post.id,
                "_source": {
                    "type":"post","id":post.id,"parent_id":None,
                    "created_at":dt.isoformat(),
                    "time_of_day":get_time_of_day(dt),
                    "day_of_week":dt.strftime("%A"),
                    "keyword":kw,"subreddit":post.subreddit.display_name,
                    "title":title,"content":body,
                    "sentiment_score":score,"sentiment_label":label,
                    "author":getattr(post.author,"name",None),
                    "location":loc,"geolocation":CITY_COORDS[loc],
                    "url":post.url
                }
            })
            seen_ids.add(post.id)

            try:
                post.comments.replace_more(limit=None)
            except Exception as e:
                print(f"展开评论失败({post.id}): {e}")

            for comment in post.comments.list():
                if time.time() - start_ts > GRAB_TIME_LIMIT:
                    print("达到抓取时间上限，停止拉取评论")
                    stop_flag = True
                    break

                dtc = datetime.fromtimestamp(comment.created_utc, tz=timezone.utc)
                if dtc <= last_time: continue
                if comment.id in seen_ids: continue

                bc = comment.body or ""
                if not bc.strip() or bc.strip() in ('[deleted]','[removed]'):
                    continue

                sc,lc = analyze_sentiment(bc)
                loc_c = random.choice(CITY_CHOICES)
                records.append({
                    "_index": ES_INDEX, "_id": comment.id,
                    "_source": {
                        "type":"comment","id":comment.id,
                        "parent_id":post.id,
                        "created_at":dtc.isoformat(),
                        "time_of_day":get_time_of_day(dtc),
                        "day_of_week":dtc.strftime("%A"),
                        "keyword":kw,"subreddit":post.subreddit.display_name,
                        "title":None,"content":bc,
                        "sentiment_score":sc,"sentiment_label":lc,
                        "author":getattr(comment.author,"name",None),
                        "location":loc_c,"geolocation":CITY_COORDS[loc_c],
                        "url":f"https://reddit.com{comment.permalink}"
                    }
                })
                seen_ids.add(comment.id)
            # end comments loop
        # end posts loop

    if not records:
        print("本次运行没有增量数据。")
        return {"status": "no_increment"}

    try:
        success, _ = helpers.bulk(es, records, raise_on_error=False)
        print(f"已写入 {success} 条新文档到 Elasticsearch")
        return {"status": "ok", "written": success}
    except Exception as e:
        print("写入 ES 失败:", e)
        return {"status": "error", "message": str(e)}
