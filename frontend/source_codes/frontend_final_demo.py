import os
import json
import string
import datetime
from collections import Counter
import warnings

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import requests
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from wordcloud import WordCloud, STOPWORDS
from PIL import Image

import nltk
from nltk.corpus import stopwords
from nltk import pos_tag

import ipywidgets as widgets
from IPython.display import display, clear_output

import folium
from folium.plugins import HeatMap

from elasticsearch8 import Elasticsearch

# suppress insecure TLS warning from Elasticsearch
warnings.filterwarnings("ignore", message=".*verify_certs=False is insecure.*")

# — ensure GeoJSON exists, otherwise download it —
GEOJSON_PATH = "/home/jovyan/work/repo/frontend/source_codes/australia_states.geojson"
GEOJSON_URL = (
    "https://raw.githubusercontent.com/"
    "codeforgermany/click_that_hood/"
    "main/public/data/australia.geojson"
)
if not os.path.exists(GEOJSON_PATH):
    print(f"GeoJSON not found at {GEOJSON_PATH}, downloading...")
    resp = requests.get(GEOJSON_URL)
    resp.raise_for_status()
    with open(GEOJSON_PATH, "wb") as f:
        f.write(resp.content)
    print("GeoJSON download complete.")
with open(GEOJSON_PATH, "r", encoding="utf-8") as f:
    australia = json.load(f)

# — NLTK stopwords (fixed absolute path) —
NLTK_DATA_PATH = "/home/jovyan/work/repo/frontend/source_codes/nltk_data"
nltk.data.path.append(NLTK_DATA_PATH)

custom_stopwords = {
    "election", "government", "campaign", "vote", "voting",
    "https", "http", "www", "com", "co", "amp", "rt", "via",
    "australia", "australian", "sydney", "melbourne", "nsw", "vic", "qld",
    "said", "says", "like", "think", "know", "also", "one", "new", "today",
    "people"
}
nltk_sw = set(stopwords.words('english'))
combined_stopwords = nltk_sw.union(STOPWORDS).union(custom_stopwords)

# — load mask image for word cloud —
MASK_PATH = "/home/jovyan/work/repo/frontend/source_codes/australia_mask1.png"
if not os.path.exists(MASK_PATH):
    raise FileNotFoundError(f"Mask image not found: {MASK_PATH}")
mask_image = np.array(Image.open(MASK_PATH))

# — initialize Elasticsearch client —
es = Elasticsearch(
    ["https://elasticsearch-master.elastic.svc.cluster.local:9200"],
    basic_auth=("elastic", "elastic"),
    verify_certs=False
)
assert es.ping(), "Failed to connect to Elasticsearch"
print("Elasticsearch connection successful")

# — city → (lat, lon) mapping —
city_coords = {
    'Sydney': (-33.8688, 151.2093),
    'Melbourne': (-37.8136, 144.9631),
    'Brisbane': (-27.4698, 153.0251),
    'Perth': (-31.9505, 115.8605),
    'Adelaide': (-34.9285, 138.6007),
    'Hobart': (-42.8821, 147.3272),
    'Darwin': (-12.4634, 130.8456),
    'Canberra': (-35.2809, 149.1300)
}

# ...（后续函数保持不变）...

