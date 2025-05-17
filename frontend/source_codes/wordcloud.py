import os
from elasticsearch8 import Elasticsearch
import pandas as pd
import string
from collections import Counter
import matplotlib.pyplot as plt
from wordcloud import WordCloud, STOPWORDS
from nltk.corpus import stopwords
from nltk import pos_tag
import nltk
import numpy as np
from PIL import Image
import ipywidgets as widgets
from IPython.display import display, clear_output
import datetime

# 连接 ES
es = Elasticsearch(
    ["https://elasticsearch-master.elastic.svc.cluster.local:9200"],
    basic_auth=("elastic", "elastic"),
    verify_certs=False
)
assert es.ping(), "❌ 无法 ping 通 ES"
print("✅ ES 连接成功")

# 设置 NLTK 本地数据路径和下载资源
local_nltk_data = os.path.expanduser("nltk_data")
os.makedirs(local_nltk_data, exist_ok=True)
nltk.data.path.append(local_nltk_data)
nltk.download('stopwords', download_dir=local_nltk_data)
nltk.download('averaged_perceptron_tagger', download_dir=local_nltk_data)
nltk.download('averaged_perceptron_tagger_eng', download_dir=local_nltk_data)


# 自定义停用词（跟你之前定义一致）
custom_stopwords = {
    "election", "elections", "federal", "government", "campaign", "seat", "minister",
    "votes","vote","voters","voting", "elect", "electorate", "political", "candidate", "candidates",
    "https", "http", "www", "com", "co", "amp", "rt", "via", "httpswww",
    "australia", "australian", "canberra", "sydney", "melbourne", "nsw", "vic", "qld",
    "said", "says", "get", "like", "think", "know", "also", "make", "still",
    "one", "new", "day", "today", "year", "years", "people"
}
nltk_stopwords = set(stopwords.words('english'))
combined_stopwords = nltk_stopwords.union(STOPWORDS).union(custom_stopwords)

# 加载蒙版图片路径（请确认路径正确）
mask_image = np.array(Image.open("work/repo/frontend/visualization_wordcloud/australia_mask1.png"))


# === ES 查询函数，根据时间范围拉取 content 字段 ===
def fetch_content_by_date(start_date, end_date, index_name="election_v2"):
    query = {
        "size": 10000,
        "query": {
            "range": {
                "created_at": {
                    "gte": start_date.strftime('%Y-%m-%d'),
                    "lte": end_date.strftime('%Y-%m-%d')
                }
            }
        },
        "_source": ["content"]
    }
    res = es.search(index=index_name, body=query)
    contents = []
    for hit in res["hits"]["hits"]:
        if 'content' in hit["_source"]:
            contents.append(hit["_source"]["content"])
    return contents


# === 生成词云函数 ===
def generate_wordcloud(texts):
    all_text = " ".join(texts).lower()
    all_text = all_text.translate(str.maketrans("", "", string.punctuation))
    tokens = all_text.split()
    tagged = pos_tag(tokens)
    
    nouns = [
        word for word, tag in tagged
        if tag.startswith('NN') and word not in combined_stopwords and word.isalpha()
    ]
    word_freq = Counter(nouns)
    
    wc = WordCloud(
        width=800,
        height=400,
        background_color='white',
        max_words=300,
        stopwords=combined_stopwords,
        contour_width=3,
        contour_color='skyblue',
        colormap='plasma',
        prefer_horizontal=0.9,
        mask=mask_image
    )
    wc.generate_from_frequencies(word_freq)
    
    return wc


# === UI 控件定义 ===
facebook_blue = "#3b5998"
border_style = f'2px solid {facebook_blue}'

before_button = widgets.Button(
    description="Before election",
    layout=widgets.Layout(width="150px", border=border_style),
    style={'button_color': 'white', 'font_weight': 'bold'}
)

after_button = widgets.Button(
    description="After election",
    layout=widgets.Layout(width="150px", border=border_style),
    style={'button_color': 'white', 'font_weight': 'bold'}
)

# 高亮选中按钮
def select_button(selected, unselected):
    selected.style.button_color = facebook_blue
    selected.style.font_weight = 'bold'
    selected.layout.border = f'2px solid {facebook_blue}'
    unselected.style.button_color = 'white'
    unselected.style.font_weight = 'normal'
    unselected.layout.border = '2px solid white'

start_date_picker = widgets.DatePicker(description='Start Date', value=datetime.date(2022, 4, 1))
end_date_picker = widgets.DatePicker(description='End Date', value=datetime.date(2022, 5, 31))

top_controls = widgets.HBox([before_button, after_button])
date_controls = widgets.HBox([start_date_picker, end_date_picker])

# 图表输出区域
output = widgets.Output()

# === 更新词云显示函数 ===
def update_wordcloud(start_date, end_date):
    with output:
        clear_output(wait=True)
        contents = fetch_content_by_date(start_date, end_date)
        if not contents:
            print(f"⚠️ No content found for range {start_date} to {end_date}")
            return
        wc = generate_wordcloud(contents)
        plt.figure(figsize=(12, 10))
        plt.imshow(wc, interpolation='bilinear')
        plt.axis("off")
        plt.title(f"Word Cloud from {start_date} to {end_date}", fontsize=20, weight='bold', color='midnightblue')
        plt.tight_layout(pad=0)
        plt.show()


# === 事件绑定函数 ===
def on_before_click(b):
    select_button(before_button, after_button)
    # 设置日期控件范围匹配“Before election”
    start_date_picker.value = datetime.date(2022, 3, 1)
    end_date_picker.value = datetime.date(2022, 5, 20)
    update_wordcloud(start_date_picker.value, end_date_picker.value)

def on_after_click(b):
    select_button(after_button, before_button)
    start_date_picker.value = datetime.date(2022, 5, 21)
    end_date_picker.value = datetime.date(2022, 7, 15)
    update_wordcloud(start_date_picker.value, end_date_picker.value)


def on_date_change(change):
    # 当用户手动更改日期时，取消按钮高亮（因为不一定对应“Before”或“After”）
    before_button.style.button_color = 'white'
    before_button.style.font_weight = 'normal'
    before_button.layout.border = '2px solid white'
    after_button.style.button_color = 'white'
    after_button.style.font_weight = 'normal'
    after_button.layout.border = '2px solid white'
    
    # 只在日期选择器值有效时更新词云
    if start_date_picker.value and end_date_picker.value and start_date_picker.value <= end_date_picker.value:
        update_wordcloud(start_date_picker.value, end_date_picker.value)


# 绑定事件
before_button.on_click(on_before_click)
after_button.on_click(on_after_click)
start_date_picker.observe(on_date_change, names='value')
end_date_picker.observe(on_date_change, names='value')


# 初始默认显示（Before election）
select_button(before_button, after_button)
update_wordcloud(datetime.date(2022, 3, 1), datetime.date(2022, 5, 20))

# 显示界面
display(widgets.VBox([top_controls, date_controls, output]))
