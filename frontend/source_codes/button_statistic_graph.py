import ipywidgets as widgets
from IPython.display import display, clear_output
import datetime
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from elasticsearch8 import Elasticsearch
from elasticsearch.helpers import scan

# ==================== 1. Initialise Elasticsearch ====================
es = Elasticsearch(
    ["https://elasticsearch-master.elastic.svc.cluster.local:9200"],
    basic_auth=("elastic", "elastic"),
    verify_certs=False
)
assert es.ping(), "can't ping by ES"
print("Elasticsearch connection success")
# ==================== 2. control set ====================
facebook_blue = "#3b5998"
border_style = f'2px solid {facebook_blue}'

before_button = widgets.Button(
    description="Before election",
    layout=widgets.Layout(width="150px", border=border_style),
    style={'button_color': 'white', 'font_weight': 'bold', 'font_color': facebook_blue}
)

after_button = widgets.Button(
    description="After election",
    layout=widgets.Layout(width="150px", border=border_style),
    style={'button_color': 'white', 'font_weight': 'bold', 'font_color': facebook_blue}
)

start_date_picker = widgets.DatePicker(description='Start Date', value=datetime.date(2022, 4, 1))
end_date_picker = widgets.DatePicker(description='End Date', value=datetime.date(2022, 5, 31))

top_controls = widgets.HBox([before_button, after_button])
date_controls = widgets.HBox([start_date_picker, end_date_picker])
output_area = widgets.Output()
display(widgets.VBox([top_controls, date_controls, output_area]))

# ==================== 3. colour relation function ====================
def select_button(selected, unselected):
    selected.style.button_color = facebook_blue
    selected.style.font_color = 'white'
    unselected.style.button_color = 'white'
    unselected.style.font_color = facebook_blue

# ==================== 4. access ES datas ====================
def fetch_filtered_data(start_date, end_date):
    query = {
        "size": 10000,
        "query": {
            "range": {
                "created_at": {
                    "gte": start_date.strftime('%Y-%m-%d'),
                    "lte": end_date.strftime('%Y-%m-%d')
                }
            }
        }
    }

    index_name = "election_analysis"
    res = es.search(index=index_name, body=query)
    records = []
    for hit in res["hits"]["hits"]:
        src = hit["_source"]
        records.append({
            "emotion_label": src.get("emotion_label"),
            "post_time_of_day": src.get("post_time_of_day"),
            "location": src.get("location")
        })
    return pd.DataFrame(records)

# ==================== 5. draw graph ====================
def plot_sentiment_by_state(df):
    output_area.clear_output()
    with output_area:
        city_to_state = {
            'Sydney': 'New South Wales',
            'Melbourne': 'Victoria',
            'Brisbane': 'Queensland',
            'Perth': 'Western Australia',
            'Adelaide': 'South Australia',
            'Hobart': 'Tasmania',
            'Darwin': 'Northern Territory',
            'Canberra': 'Australian Capital Territory'
        }
        df['state'] = df['location'].map(city_to_state)
        df_state = df.dropna(subset=['state'])
        if df_state.empty:
            print("there is no valid data during this time")
            return
        state_sentiment_data = df_state.groupby(['state', 'emotion_label']).size().reset_index(name='count')
        emotion_labels = state_sentiment_data['emotion_label'].unique()
        colors = sns.color_palette("Blues", n_colors=len(emotion_labels))
        sentiment_palette = dict(zip(emotion_labels, colors))

        plt.figure(figsize=(12, 6))
        sns.barplot(
            data=state_sentiment_data,
            x='state',
            y='count',
            hue='emotion_label',
            palette=sentiment_palette
        )
        plt.xticks(rotation=45, ha='right')
        plt.title('Number of Posts by State and Sentiment', fontsize=14)
        plt.xlabel('State')
        plt.ylabel('Number of Posts')
        plt.legend(title='Sentiment')
        plt.tight_layout()
        plt.grid(axis='y')
        plt.show()

# ==================== 6. callback binding ====================
def update_chart(start_date, end_date):
    df = fetch_filtered_data(start_date, end_date)
    plot_sentiment_by_state(df)

def on_before_click(b):
    select_button(before_button, after_button)
    start_date_picker.value = datetime.date(2022, 3, 1)
    end_date_picker.value = datetime.date(2022, 5, 20)
    update_chart(start_date_picker.value, end_date_picker.value)

def on_after_click(b):
    select_button(after_button, before_button)
    start_date_picker.value = datetime.date(2022, 5, 21)
    end_date_picker.value = datetime.date(2022, 7, 15)
    update_chart(start_date_picker.value, end_date_picker.value)

def on_date_change(change):
    if start_date_picker.value and end_date_picker.value:
        update_chart(start_date_picker.value, end_date_picker.value)

before_button.on_click(on_before_click)
after_button.on_click(on_after_click)
start_date_picker.observe(on_date_change, names='value')
end_date_picker.observe(on_date_change, names='value')