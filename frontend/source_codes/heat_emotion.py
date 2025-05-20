"""
COMP90024 Cluster and Cloud Computing - Assignment 2
Big Data Analytics on the Cloud

Team Information:
Team Name: COMP90024_team_43
Team Members:
- Linyao ZHOU     (Student ID: 1619649)
- Yihao SANG      (Student ID: 1562582)
- Xiwen CHEN      (Student ID: 1542252)
- Yuan GAO        (Student ID: 1602894)
- Yao ZHAO        (Student ID: 1695969)

This file is part of the team's solution for Assignment 2,
demonstrating the use of cloud technologies (Kubernetes, Fission,
ElasticSearch) for social media data analytics related to Australia.
"""
import os
import json
import requests
import pandas as pd
import numpy as np
import folium
from elasticsearch8 import Elasticsearch
from dateutil import parser
import datetime
import ipywidgets as widgets
from IPython.display import display, clear_output

# 1. Connect to Elasticsearch
es = Elasticsearch(
    ["https://elasticsearch-master.elastic.svc.cluster.local:9200"],
    basic_auth=("elastic", "elastic"),
    verify_certs=False,
    headers={
        "Accept": "application/vnd.elasticsearch+json;compatible-with=8",
        "Content-Type": "application/vnd.elasticsearch+json;compatible-with=8"
    }
)
assert es.ping(), "❌ Failed to connect to Elasticsearch"
print("✅ Successfully connected to Elasticsearch")

# 2. Retrieve data from Elasticsearch
response = es.search(
    index="election_analysis",
    size=5000,
    _source=["created_at", "geolocation", "sentiment_score", "location"],
    query={"bool": {"must": [
        {"exists": {"field": "created_at"}},
        {"exists": {"field": "geolocation"}},
        {"exists": {"field": "sentiment_score"}},
        {"exists": {"field": "location"}}
    ]}}
)
records = [hit["_source"] for hit in response["hits"]["hits"]]
df = pd.DataFrame(records)
df["created_at"] = df["created_at"].apply(parser.isoparse)

def parse_geolocation(geo):
    """Extract latitude and longitude from geolocation field."""
    if isinstance(geo, dict) and "lat" in geo and "lon" in geo:
        return geo["lat"], geo["lon"]
    if isinstance(geo, str) and "," in geo:
        a, b = geo.split(",", 1)
        return float(a), float(b)
    return None, None

df[["lat", "lon"]] = df["geolocation"].apply(lambda g: pd.Series(parse_geolocation(g)))
df = df.dropna(subset=["created_at", "lat", "lon", "sentiment_score", "location"])

city_to_state = {
    'Sydney': 'New South Wales', 'Melbourne': 'Victoria',
    'Brisbane': 'Queensland', 'Perth': 'Western Australia',
    'Adelaide': 'South Australia', 'Hobart': 'Tasmania',
    'Darwin': 'Northern Territory', 'Canberra': 'Australian Capital Territory'
}
df["state"] = df["location"].map(city_to_state)

def prepare_state_counts(subdf):
    """Aggregate state post counts for choropleth."""
    state_counts = (
        subdf["state"]
            .dropna()
            .value_counts()
            .rename_axis("state")
            .reset_index(name="count")
    )
    return state_counts

all_state_counts = prepare_state_counts(df)
global_max = all_state_counts["count"].max()
color_bins = list(np.linspace(0, global_max, 8))

# 3. Load Australia state GeoJSON for map visualization (download if not found locally)
geojson_filename = "australian-states.geojson"
geo_url = "https://raw.githubusercontent.com/ferocia/australia-geojsons/master/outputs/australian-states.geojson"

if not os.path.exists(geojson_filename):
    print("GeoJSON file not found locally. Downloading from GitHub...")
    r = requests.get(geo_url)
    r.raise_for_status()
    with open(geojson_filename, "wb") as f:
        f.write(r.content)
else:
    print("GeoJSON file found locally. Using the local file.")

with open(geojson_filename, "r", encoding="utf-8") as f:
    australia_geojson = json.load(f)

# 4. Interactive controls and mapping logic
facebook_blue = "#3b5998"
border_style = f'2px solid {facebook_blue}'

before_button = widgets.Button(
    description="Before Election",
    layout=widgets.Layout(width="150px", border=border_style),
    style={'button_color': 'white'}
)
after_button = widgets.Button(
    description="After Election",
    layout=widgets.Layout(width="150px", border=border_style),
    style={'button_color': 'white'}
)

def highlight_button(selected, unselected):
    selected.style.button_color = facebook_blue
    selected.style.font_color = 'white'
    unselected.style.button_color = 'white'
    unselected.style.font_color = facebook_blue

chk_choropleth = widgets.Checkbox(value=True, description="Show Choropleth")

all_dates = df["created_at"].dt.date.sort_values()
min_date = all_dates.min()
max_date = all_dates.max()

start_date_picker = widgets.DatePicker(
    description='Start Date',
    value=min_date,
    disabled=False,
    min=min_date,
    max=max_date
)
end_date_picker = widgets.DatePicker(
    description='End Date',
    value=max_date,
    disabled=False,
    min=min_date,
    max=max_date
)

output = widgets.Output()
top_controls = widgets.HBox([before_button, after_button])
option_controls = widgets.HBox([chk_choropleth])
date_controls = widgets.HBox([start_date_picker, end_date_picker])
ui = widgets.VBox([top_controls, date_controls, option_controls, output])
display(ui)

def plot_map(start_date, end_date, show_choropleth=True):
    """Render folium map for the selected date range and options."""
    df_range = df[
        (df["created_at"].dt.date >= start_date) &
        (df["created_at"].dt.date <= end_date)
    ]
    state_counts = prepare_state_counts(df_range)
    print(f"Selected Range: {start_date} ~ {end_date}")
    print("Number of posts in range:", len(df_range))
    if len(df_range) == 0 or len(state_counts) == 0:
        print("⚠️ No data available for the selected range. Please choose another range.")
        return
    bounds = [[-44, 112], [-10, 154]]
    m = folium.Map(
        location=[-25.27, 133.77], tiles="CartoDB positron",
        zoom_start=4, min_zoom=4, max_zoom=6, max_bounds=True
    )
    m.fit_bounds(bounds)
    m.options['maxBounds'] = bounds; m.options['maxBoundsViscosity'] = 1.0
    if show_choropleth:
        folium.Choropleth(
            geo_data=australia_geojson,
            data=state_counts,
            columns=["state", "count"],
            key_on="feature.properties.STATE_NAME",
            fill_color="Blues",
            threshold_scale=color_bins,
            fill_opacity=0.6,
            line_opacity=0.3,
            legend_name="Number of Posts"
        ).add_to(m)
        folium.GeoJson(
            australia_geojson,
            style_function=lambda f: {"color": "#333", "weight": 0.5, "fillOpacity": 0}
        ).add_to(m)
    legend = """
    <div style="
      position:fixed;top:100px;right:20px;
      width:20px;height:250px;
      background:linear-gradient(to top,
        #deebf7 0%,#9ecae1 25%,#6baed6 50%,#3182bd 75%,#08519c 100%);
      border:1px solid #888;z-index:9999;
    "></div>
    <div style="position:fixed;top:80px;right:45px;font-size:12px;z-index:9999;">High</div>
    <div style="position:fixed;top:360px;right:45px;font-size:12px;z-index:9999;">Low</div>
    """
    m.get_root().html.add_child(folium.Element(legend))
    display(m)

def on_before_click(b):
    """Switch to the default 'before election' period and update the map."""
    highlight_button(before_button, after_button)
    # Change these dates according to your actual election cut-off!
    start_date_picker.value = min_date
    end_date_picker.value = datetime.date(2025, 5, 2)
    refresh_map()
def on_after_click(b):
    """Switch to the default 'after election' period and update the map."""
    highlight_button(after_button, before_button)
    start_date_picker.value = datetime.date(2025, 5, 3)
    end_date_picker.value = max_date
    refresh_map()

def refresh_map(*args):
    """Update the map whenever date range or options change."""
    with output:
        clear_output(wait=True)
        s, e = start_date_picker.value, end_date_picker.value
        if s is None or e is None or s > e:
            print("Please select a valid date range!")
            return
        plot_map(s, e, show_choropleth=chk_choropleth.value)

# Bind events to controls
start_date_picker.observe(refresh_map, names='value')
end_date_picker.observe(refresh_map, names='value')
chk_choropleth.observe(refresh_map, names='value')
before_button.on_click(on_before_click)
after_button.on_click(on_after_click)

# Default highlight and initial map display
highlight_button(before_button, after_button)
refresh_map()

