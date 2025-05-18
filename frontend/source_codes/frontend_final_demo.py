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

# — NLTK stopwords (assume data is in ./nltk_data next to the geojson) —
BASE_DIR = os.path.dirname(GEOJSON_PATH)
NLTK_DATA_PATH = os.path.join(BASE_DIR, "nltk_data")
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

def fetch_filtered_data(start_date, end_date, max_docs=30000, batch_size=1000):
    """Fetch up to max_docs posts between start_date and end_date via Scroll API."""
    query = {
        "size": batch_size,
        "query": {
            "range": {
                "created_at": {
                    "gte": start_date.strftime('%Y-%m-%d'),
                    "lte": end_date.strftime('%Y-%m-%d')
                }
            }
        }
    }
    page = es.search(index="election_v2", body=query, scroll="2m")
    scroll_id = page["_scroll_id"]
    hits = page["hits"]["hits"]
    records = []
    while hits and len(records) < max_docs:
        for hit in hits:
            if len(records) >= max_docs:
                break
            src = hit["_source"]
            loc = src.get("location")
            if not loc:
                continue
            records.append({
                "created_at": pd.to_datetime(src["created_at"]),
                "emotion_label": src.get("emotion_label"),
                "post_time_of_day": src.get("post_time_of_day"),
                "location": loc,
                "content": src.get("content", "")
            })
        page = es.scroll(scroll_id=scroll_id, scroll="2m")
        scroll_id = page["_scroll_id"]
        hits = page["hits"]["hits"]
    es.clear_scroll(scroll_id=scroll_id)

    if not records:
        return pd.DataFrame(columns=[
            "created_at","emotion_label","post_time_of_day",
            "location","latitude","longitude","content"
        ])
    df = pd.DataFrame(records)
    df[["latitude","longitude"]] = df["location"].apply(
        lambda loc: pd.Series(city_coords.get(loc,(None,None)))
    )
    return df

def prepare_map_data(df):
    """Filter invalid coords, map city to state, return state counts & heat points."""
    df2 = df.dropna(subset=["location","latitude","longitude"]).copy()
    state_map = {
        'Sydney':'New South Wales','Melbourne':'Victoria',
        'Brisbane':'Queensland','Perth':'Western Australia',
        'Adelaide':'South Australia','Hobart':'Tasmania',
        'Darwin':'Northern Territory','Canberra':'Australian Capital Territory'
    }
    df2["state"] = df2["location"].map(state_map)
    state_counts = df2.groupby("state").size().reset_index(name="count")
    heat_points = df2[["latitude","longitude"]].values.tolist()
    return state_counts, heat_points

def draw_map(df, start_date, end_date, show_choro=True, show_heat=True):
    """Draw choropleth and/or heatmap of posts."""
    sc, hp = prepare_map_data(df)
    print(f"Date range: {start_date} to {end_date} | Total posts: {len(df)}")
    if sc.empty:
        print("No data to display")
        return
    cnt = sc["count"]
    bins = list(np.linspace(cnt.min(), cnt.max(), 6))
    m = folium.Map(location=[-25.27,133.77], tiles="CartoDB positron",
                   zoom_start=4, min_zoom=4, max_zoom=6)
    bounds = [[-44,112],[-10,154]]
    m.fit_bounds(bounds)
    m.options["maxBounds"] = bounds
    m.options["maxBoundsViscosity"] = 1.0

    if show_choro:
        folium.Choropleth(
            geo_data=australia,
            data=sc,
            columns=["state","count"],
            key_on="feature.properties.name",
            fill_color="Blues",
            threshold_scale=bins,
            fill_opacity=0.6,
            line_opacity=0.3,
            legend_name="Post Count"
        ).add_to(m)
        folium.GeoJson(australia, style_function=lambda feat: {
            "color":"#333","weight":0.5,"fillOpacity":0
        }).add_to(m)

    if show_heat:
        HeatMap(data=hp, radius=12, blur=6, max_zoom=6,
                gradient={0.0:'#deebf7',0.25:'#9ecae1',
                          0.5:'#6baed6',0.75:'#3182bd',1.0:'#08519c'}
        ).add_to(m)
    display(m)

def draw_sentiment_chart(df):
    """Plot bar chart of post counts by state & sentiment."""
    if df.empty or "emotion_label" not in df:
        print("No sentiment data")
        return
    df2 = df.dropna(subset=["location","emotion_label"]).copy()
    smap = {
        'Sydney':'New South Wales','Melbourne':'Victoria',
        'Brisbane':'Queensland','Perth':'Western Australia',
        'Adelaide':'South Australia','Hobart':'Tasmania',
        'Darwin':'Northern Territory','Canberra':'Australian Capital Territory'
    }
    df2["state"] = df2["location"].map(smap)
    agg = df2.groupby(["state","emotion_label"]).size().reset_index(name="count")
    plt.figure(figsize=(12,6))
    palette = dict(zip(
        agg["emotion_label"].unique(),
        sns.color_palette("Blues", n_colors=agg["emotion_label"].nunique())
    ))
    sns.barplot(data=agg, x="state", y="count", hue="emotion_label", palette=palette)
    plt.xticks(rotation=45, ha="right")
    plt.title("Posts by State & Sentiment")
    plt.tight_layout(); plt.grid(axis="y"); plt.show()

def draw_wordcloud(df, start_date, end_date):
    """Generate noun word cloud from post content."""
    if df.empty or "content" not in df:
        print("No text data")
        return
    text = " ".join(df["content"].dropna().astype(str)).lower()
    text = text.translate(str.maketrans("","",string.punctuation))
    tagged = pos_tag(text.split())
    nouns = [w for w,t in tagged if t.startswith("NN") and w.isalpha() and w not in combined_stopwords]
    if not nouns:
        print("No valid words")
        return
    freqs = Counter(nouns)
    wc = WordCloud(width=800, height=400, background_color="white",
                   max_words=300, stopwords=combined_stopwords,
                   mask=mask_image, contour_width=3, contour_color="skyblue",
                   colormap="plasma", prefer_horizontal=0.9)
    wc.generate_from_frequencies(freqs)
    plt.figure(figsize=(12,6)); plt.imshow(wc, interpolation="bilinear")
    plt.axis("off"); plt.title(f"Word Cloud {start_date} to {end_date}", fontsize=18)
    plt.tight_layout(pad=0); plt.show()

def update_outputs(*_):
    """Refresh map, sentiment chart, and word cloud when inputs change."""
    start, end = start_picker.value, end_picker.value
    if not start or not end or start > end:
        for out in (map_out, chart_out, wc_out):
            with out:
                clear_output(); print("Invalid date range")
        return
    df = fetch_filtered_data(start, end)
    with map_out:
        clear_output(wait=True); draw_map(df, start, end,
                                          choropleth_cb.value, heatmap_cb.value)
    with chart_out:
        clear_output(wait=True); draw_sentiment_chart(df)
    with wc_out:
        clear_output(wait=True); draw_wordcloud(df, start, end)

# create widgets and layout
fb_blue = "#3b5998"
before_btn = widgets.Button(description="Before Election", layout=widgets.Layout(width="150px"))
after_btn  = widgets.Button(description="After Election",  layout=widgets.Layout(width="150px"))
choropleth_cb = widgets.Checkbox(value=True, description="Show Choropleth")
heatmap_cb    = widgets.Checkbox(value=True, description="Show HeatMap")
start_picker  = widgets.DatePicker(description="Start Date", value=datetime.date(2025,4,15))
end_picker    = widgets.DatePicker(description="End Date",   value=datetime.date(2025,4,20))

map_out   = widgets.Output()
chart_out = widgets.Output()
wc_out    = widgets.Output()

def select_btn(sel, unsel):
    sel.style.button_color   = fb_blue; sel.style.font_color = "white"
    unsel.style.button_color = "white";    unsel.style.font_color = fb_blue

def on_before(b):
    select_btn(before_btn, after_btn)
    start_picker.value = datetime.date(2025,3,1)
    end_picker.value   = datetime.date(2025,5,3)

def on_after(b):
    select_btn(after_btn, before_btn)
    start_picker.value = datetime.date(2025,5,4)
    end_picker.value   = datetime.date(2025,5,14)

before_btn.on_click(on_before)
after_btn.on_click(on_after)
for w in (start_picker, end_picker, choropleth_cb, heatmap_cb):
    w.observe(update_outputs, names="value")

ui = widgets.VBox([
    widgets.HBox([before_btn, after_btn]),
    widgets.HBox([start_picker, end_picker]),
    widgets.HBox([choropleth_cb, heatmap_cb]),
    widgets.Label("Map Display"),    map_out,
    widgets.Label("Sentiment Chart"), chart_out,
    widgets.Label("Word Cloud"),      wc_out
])
display(ui)

select_btn(before_btn, after_btn)
update_outputs()

