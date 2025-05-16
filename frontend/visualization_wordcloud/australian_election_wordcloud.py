import os
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

# === 设置 NLTK 本地路径和依赖下载 ===
local_nltk_data = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nltk_data")
os.makedirs(local_nltk_data, exist_ok=True)
nltk.data.path.append(local_nltk_data)

# 下载依赖
nltk.download('stopwords', download_dir=local_nltk_data, force=True)
nltk.download('averaged_perceptron_tagger', download_dir=local_nltk_data, force=True)
nltk.download('averaged_perceptron_tagger_eng', download_dir=local_nltk_data, force=True)

# === 加载文本数据 ===
df = pd.read_csv("aus_election_statuses30days.csv")
texts = df["content"].dropna().astype(str)

# === 文本清洗与预处理 ===
all_text = " ".join(texts).lower()
all_text = all_text.translate(str.maketrans("", "", string.punctuation))
tokens = all_text.split()

# === 词性标注 + 名词提取 ===
tagged = pos_tag(tokens, tagset=None, lang='eng')
nltk_stopwords = set(stopwords.words('english'))

# === 自定义停用词（结合政治语境）===
custom_stopwords = {
    # 功能性高频词
    "election", "elections", "federal", "government", "campaign", "seat", "minister",
    "votes","vote","voters","voting", "elect", "electorate", "political", "candidate", "candidates",

    # 噪音型结构词
    "https", "http", "www", "com", "co", "amp", "rt", "via","httpswww",

    # 模糊地名和通用词（不带情感）
    "australia", "australian", "canberra", "sydney", "melbourne", "nsw", "vic", "qld",

    # 无意义词
    "said", "says", "get", "like", "think", "know", "also", "make", "still",
    "one", "new", "day", "today", "year", "years", "people"
}
combined_stopwords = nltk_stopwords.union(STOPWORDS).union(custom_stopwords)

# === 提取有意义的名词（排除停用词、非字母）===
nouns = [
    word for word, tag in tagged
    if tag.startswith('NN') and word not in combined_stopwords and word.isalpha()
]

# === 词频统计 ===
word_freq = Counter(nouns)

# === 加载形状蒙版（可选）===
mask_image = np.array(Image.open("australia_mask1.png"))  # 如果你已有澳洲轮廓图，可启用

# === 生成词云 ===
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
    font_path="C:/Windows/Fonts/arial.ttf",  # 改为 SimHei.ttf 若为中文
    mask=mask_image  # 启用形状图像词云
)

wc.generate_from_frequencies(word_freq)

# === 显示图像 ===
plt.figure(figsize=(12, 10))
plt.imshow(wc, interpolation='bilinear')
plt.axis("off")
plt.title("Australian Federal Election – Word Cloud", fontsize=20, weight='bold', color='midnightblue')
plt.tight_layout(pad=0)
plt.show()
