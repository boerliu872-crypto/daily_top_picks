"""
utils/serverchan_push.py - Server酱推送
"""
import logging
import os
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


def get_sendkey():
    # 优先环境变量(云端),再读 .env(本地)
    key = os.getenv("SERVERCHAN3_SENDKEY", "")
    if key:
        return key
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("SERVERCHAN3_SENDKEY="):
                return line.split("=", 1)[1].strip()
    return ""


def push(title: str, content: str, tags: str = "daily_top_picks") -> bool:
    sendkey = get_sendkey()
    if not sendkey:
        logger.error("未配置 SERVERCHAN3_SENDKEY")
        return False
    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    payload = {"title": title[:32], "desp": content[:32000], "tags": tags}
    for attempt in range(3):
        try:
            resp = requests.post(url, data=payload, timeout=10)
            resp.raise_for_status()
            result = resp.json()
            if result.get("code") == 0:
                logger.info(f"推送成功: {title}")
                return True
            logger.error(f"推送失败: {result.get('message')}")
        except Exception as e:
            logger.warning(f"推送第{attempt+1}次失败: {e}")
            if attempt < 2:
                time.sleep(2 ** attempt)
    return False


def quick_push(title: str, content: str, **kwargs) -> bool:
    return push(title, content, **kwargs)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ok = push("📊 测试推送", "# daily_top_picks 系统测试\n\n推送链路正常 ✅\n\n时间: 2026-05-30")
    print(f"结果: {ok}")
