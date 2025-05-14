# hello.py

import logging

# 配置日志：INFO 级别会被捕捉到
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")

def main():
    logging.info("👋 hello from Fission!")
    # 也可以用 print("hello")，但 logging 更好跟踪
    return {"body":"hello"}    # 返回值会被 HTTP 层忽略，但至少示例完整

