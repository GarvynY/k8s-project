import time
from datetime import datetime, timedelta
from atproto import Client, exceptions
import pandas as pd
import matplotlib.pyplot as plt
import os
import re
from snownlp import SnowNLP
import sys
from dateutil import parser
# ================= 配置区域 =================
CONFIG = {
    "USERNAME": "linyaozhou.bsky.social",  # 用户名
    "APP_PASSWORD": "btpz-wrf6-7usi-spjj",  # 应用密码
    "SEARCH_KEYWORD": ['Australia Election', 'AusPol', 'AUSElection', 'ausvotes2025',
                    '#ausvotes2025', 'auspol2025', '#auspol2025', 'Albanese',
                    'Dutton', 'Bandt', 'Labor', 'Liberal', 'Greens'],  # 搜索关键词
    "DATA_FILE": os.path.join(os.path.dirname(__file__), "bluesky_data.csv"),  # 数据文件路径
    "IMG_DIR": os.path.join(os.path.dirname(__file__), "charts"),  # 图表目录
    "FETCH_INTERVAL": 60,  # 抓取间隔(秒)
    "MAX_PAGES": 5,  # 最大页数
    "PAGE_SIZE": 100,  # 每页大小
    "MAX_RETRIES": 3,  # 新增重试次数
    "DEBUG": True  # 调试模式
}


# ===========================================

class BlueskyAnalyzer:
    def __init__(self, config):
        self.config = config
        self.client = None
        self.setup_directories()

    def setup_directories(self):
        """创建必要的目录结构"""
        os.makedirs(self.config["IMG_DIR"], exist_ok=True)
        if not os.path.exists(self.config["DATA_FILE"]):
            with open(self.config["DATA_FILE"], 'w', encoding='utf-8') as f:
                f.write("author,content,time,likes,sentiment,url,post_time_of_day,post_day_of_week,sentiment_score,emotion_label,location,geolocation\n")


    def log(self, message):
        """带时间戳的日志记录"""
        if self.config["DEBUG"]:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{timestamp}] {message}")

    def connect_bluesky(self):
        """建立Bluesky连接"""
        try:
            self.client = Client()
            profile = self.client.login(
                self.config["USERNAME"],
                self.config["APP_PASSWORD"]
            )
            self.log(f"✅ 登录成功 @{profile.handle}")
            return True
        except exceptions.UnauthorizedError:
            self.log("❌ 认证失败：请检查用户名和APP密码")
        except exceptions.NetworkError:
            self.log("❌ 网络错误：请检查网络连接")
        except Exception as e:
            self.log(f"❌ 连接异常: {str(e)}")
        return False

    def analyze_sentiment(self, text):
        """返回情感分数和标签"""
        if not isinstance(text, str) or len(text.strip()) < 5:
            return 0.0, 'neutral'

        text = re.sub(r'http\S+|@\w+|#\w+|[【】\n]', ' ', text.strip())

        try:
            s = SnowNLP(text)
            score = s.sentiments

            # 关键词加权（保持现有逻辑）
            positive_words = ['支持', '好', '满意', '胜利', '赞成', '喜欢']
            negative_words = ['反对', '差', '抗议', '失败', '谴责', '讨厌']

            score += 0.15 * any(w in text for w in positive_words)
            score -= 0.15 * any(w in text for w in negative_words)

            score = max(0, min(score, 1))  # 限制范围在[0,1]
            label = 'positive' if score > 0.7 else 'negative' if score < 0.3 else 'neutral'

            self.log(f"分析: {text[:50]}... → 得分: {score:.2f} → 标签: {label}")
            return score * 2 - 1, label  # 转为 [-1, 1] 范围
        except Exception as e:
            self.log(f"分析异常: {str(e)}")
            return 0.0, 'neutral'

    def fetch_posts_with_retry(self):
        """带重试机制的获取帖子数据"""
        for attempt in range(1, self.config["MAX_RETRIES"] + 1):
            try:
                self.log(f"尝试第 {attempt} 次获取数据...")
                posts = self.fetch_posts()
                if posts:
                    return posts
                time.sleep(2)  # 等待2秒后重试
            except Exception as e:
                self.log(f"❌ 第 {attempt} 次尝试失败: {str(e)}")
                if attempt == self.config["MAX_RETRIES"]:
                    return None
                time.sleep(5)  # 等待更长时间后重试
        return None

    def fetch_posts(self):
        """获取帖子数据（多关键词支持）"""
        if not self.client and not self.connect_bluesky():
            return None

        try:
            self.log(f"🔍 搜索关键词列表: {self.config['SEARCH_KEYWORD']}")
            all_posts = []

            for keyword in self.config["SEARCH_KEYWORD"]:
                self.log(f"🔎 正在搜索关键词: '{keyword}'")
                cursor = None

                for page in range(1, self.config["MAX_PAGES"] + 1):
                    params = {
                        'q': keyword,
                        'limit': self.config["PAGE_SIZE"],
                        'cursor': cursor
                    }

                    response = self.client.app.bsky.feed.search_posts(params=params)

                    post_count = len(response.posts) if response.posts else 0
                    self.log(f"📄 第 {page} 页获取 {post_count} 条结果")

                    if not response.posts:
                        break

                    all_posts.extend(response.posts)
                    cursor = response.cursor
                    time.sleep(1)

            self.log(f"📊 共获取原始帖子数: {len(all_posts)}")
            return self.process_posts(all_posts)

        except Exception as e:
            self.log(f"❌ 搜索失败: {str(e)}")
            return None



    def process_posts(self, posts):
        """处理原始帖子数据"""
        processed = []
        for post in posts[:200]:
            try:
                content = post.record.text
                if not content or len(content) < 10:
                    continue

                timestamp = parser.parse(post.indexed_at)
                hour = timestamp.hour
                post_time_of_day = (
                    "Night" if hour < 6 else
                    "Morning" if hour < 12 else
                    "Afternoon" if hour < 18 else
                    "Evening"
                )
                post_day_of_week = timestamp.strftime('%A')

                sentiment_score, emotion_label = self.analyze_sentiment(content)

                location = getattr(post.author, "description", "")
                geolocation = ""  # Bluesky目前不提供明确的经纬度字段

                processed.append({
                    'author': post.author.handle,
                    'content': content,
                    'time': post.indexed_at,
                    'likes': getattr(post, 'like_count', 0),
                    'sentiment': emotion_label,
                    'url': f"https://bsky.app/profile/{post.author.handle}/post/{post.uri.split('/')[-1]}",
                    'post_time_of_day': post_time_of_day,
                    'post_day_of_week': post_day_of_week,
                    'sentiment_score': sentiment_score,
                    'emotion_label': emotion_label,
                    'location': location,
                    'geolocation': geolocation
                })

            except Exception as e:
                self.log(f"⏭️ 跳过异常数据: {str(e)}")

        return processed

    def save_and_analyze(self, new_data):
        """保存数据并生成统计"""
        if not new_data:
            self.log("⚠️ 无新数据需要保存")
            return None, 0

        try:
            # 读取现有数据
            if os.path.exists(self.config["DATA_FILE"]) and os.path.getsize(self.config["DATA_FILE"]) > 10:
                existing_df = pd.read_csv(self.config["DATA_FILE"])
            else:
                existing_df = pd.DataFrame()

            # 合并数据
            new_df = pd.DataFrame(new_data)
            combined_df = pd.concat([existing_df, new_df]).drop_duplicates(subset=['content'])
            new_count = len(combined_df) - len(existing_df)

            # 保存数据
            combined_df.to_csv(self.config["DATA_FILE"], index=False, encoding='utf-8-sig')
            self.log(f"💾 保存成功: 新增 {new_count} 条，总计 {len(combined_df)} 条")

            return combined_df, new_count

        except Exception as e:
            self.log(f"❌ 保存失败: {str(e)}")
            return None, 0

    def generate_visualization(self, df):
        """生成可视化图表（修复版）"""
        if df is None or len(df) == 0:
            self.log("⚠️ 无数据可可视化")
            return False

        try:
            # 数据预处理
            df['date'] = pd.to_datetime(df['time']).dt.date
            df_counts = df.groupby(['date', 'sentiment']).size().unstack(fill_value=0)

            # 创建图表
            plt.figure(figsize=(12, 6))

            # 颜色映射
            colors = {'positive': '#4CAF50', 'neutral': '#FFC107', 'negative': '#F44336'}

            # 绘制每种情感的趋势线
            for sentiment in df_counts.columns:
                if sentiment in colors:
                    df_counts[sentiment].plot(
                        kind='line',
                        marker='o',
                        label=sentiment,
                        color=colors[sentiment],
                        linewidth=2
                    )

            # 图表装饰
            plt.title(f"关键词: {self.config['SEARCH_KEYWORD']}\n总数据量: {len(df)}条", pad=20)
            plt.xlabel("日期", labelpad=10)
            plt.ylabel("帖子数量", labelpad=10)
            plt.legend(title="情感倾向")
            plt.grid(True, linestyle='--', alpha=0.6)
            plt.tight_layout()

            # 保存图表
            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            img_path = os.path.join(self.config["IMG_DIR"], f"sentiment_{timestamp}.png")
            plt.savefig(img_path, bbox_inches='tight', dpi=120)
            plt.close()

            self.log(f"📊 图表已保存: {img_path}")
            return True

        except Exception as e:
            self.log(f"❌ 可视化失败: {str(e)}")
            return False

    @staticmethod
    def show_summary(df, new_count):
        """显示统计摘要"""
        print("\n" + "=" * 50)
        print(f"📅 分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("-" * 50)

        stats = df['sentiment'].value_counts()
        print(f"📌 新增数据: {new_count} 条")
        print(f"📦 总计数据: {len(df)} 条")
        print("\n💖 情感分布:")
        print(f"  👍 积极: {stats.get('positive', 0)} 条")
        print(f"  😐 中性: {stats.get('neutral', 0)} 条")
        print(f"  👎 消极: {stats.get('negative', 0)} 条")

        if not df.empty:
            latest = pd.to_datetime(df['time']).max()
            oldest = pd.to_datetime(df['time']).min()
            print(f"\n⏳ 时间范围: {oldest.strftime('%Y-%m-%d')} 至 {latest.strftime('%Y-%m-%d')}")

        print("=" * 50 + "\n")

    def run_analysis(self):
        """执行单次分析"""
        posts = self.fetch_posts_with_retry()
        if not posts:
            self.log("⚠️ 无法获取任何数据")
            return False

        df, new_count = self.save_and_analyze(posts)
        if df is not None:
            self.generate_visualization(df)
            self.show_summary(df, new_count)
            return True
        return False

    def continuous_monitoring(self):
        """持续监控模式"""
        try:
            while True:
                if not self.run_analysis():
                    self.log("⚠️ 本次分析未获取数据")

                next_run = datetime.now() + timedelta(seconds=self.config["FETCH_INTERVAL"])
                self.log(f"⏰ 下次运行: {next_run.strftime('%H:%M:%S')}")

                for _ in range(self.config["FETCH_INTERVAL"]):
                    time.sleep(1)

        except KeyboardInterrupt:
            self.log("\n🛑 用户中断，程序安全退出")
        finally:
            if self.client:
                self.log("🔒 已断开Bluesky连接")


if __name__ == "__main__":
    analyzer = BlueskyAnalyzer(CONFIG)

    print(f"""
🌟 Bluesky 舆情分析系统 v2.3 🌟
{"-" * 40}
🔎 关键词: {CONFIG['SEARCH_KEYWORD']}
📁 数据文件: {os.path.abspath(CONFIG['DATA_FILE'])}
📊 图表目录: {os.path.abspath(CONFIG['IMG_DIR'])}
🔄 更新间隔: {CONFIG['FETCH_INTERVAL']}秒
{"-" * 40}
    """)

    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        analyzer.run_analysis()
    else:
        print("进入持续监控模式 (Ctrl+C 退出)\n")
        analyzer.continuous_monitoring()
