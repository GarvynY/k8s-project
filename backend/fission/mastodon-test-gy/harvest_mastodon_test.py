import os
import requests
import json

def main():
    # token = os.environ['ACCESS_TOKEN']
    token = "cDWlSYHFFEPxIFpkrTf2ss5kAB7hOekUQ7DY3dglm4E"
    url = "https://mastodon.social/api/v1/timelines/public?limit=5"
    headers = {"Authorization": f"Bearer {token}"}

    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    # 返回一个 JSON 字符串，Flask 会把它当 HTTP Body
    return json.dumps(data)

