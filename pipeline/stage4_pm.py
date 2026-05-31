# ====== 网络配置:绕过系统代理 ======
import os
for var in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"]:
    os.environ.pop(var, None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

"""
stage4_pm.py - PM 裁决调度器
"""
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from agents import pm_decision

Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.FileHandler("logs/stage4_pm.log", encoding="utf-8"), logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

AGENT_FILE = Path(__file__).parent.parent / "data" / "agent_results.json"
ENHANCED_FILE = Path(__file__).parent.parent / "data" / "enhanced_candidates.json"
OUTPUT_FILE = Path(__file__).parent.parent / "data" / "final_picks.json"


def run():
    logger.info("=" * 60)
    logger.info(f"启动PM裁决 - {datetime.now()}")
    logger.info("=" * 60)
    if not AGENT_FILE.exists() or not ENHANCED_FILE.exists():
        logger.error("输入文件缺失")
        return None
    agent_data = json.load(open(AGENT_FILE, encoding="utf-8"))
    enhanced = json.load(open(ENHANCED_FILE, encoding="utf-8"))
    enhanced_by_code = {c["code"]: c for c in enhanced.get("candidates", [])}
    market_ctx = agent_data.get("market_context", {})
    stocks = agent_data.get("stocks", [])
    logger.info(f"待裁决 {len(stocks)} 只")

    decisions = []
    for sr in stocks:
        code = sr["stock_code"]
        stock = enhanced_by_code.get(code, {})
        d = pm_decision.decide(stock, sr, market_ctx)
        decisions.append(d)
        logger.info(f"   {d['level_emoji']} {code} 分={d['final_score']:.1f} {d['level']}")

    priority = {"主推": 1, "备选": 2, "观察": 3, "不参与": 4}
    decisions.sort(key=lambda x: (priority.get(x["level"], 5), -x["final_score"]))

    main_picks = [d for d in decisions if d["level"] == "主推"][:1]
    backup_picks = [d for d in decisions if d["level"] == "备选"][:1]

    result = {
        "generated_at": datetime.now().isoformat(),
        "market_context": market_ctx,
        "main_picks": main_picks,
        "backup_picks": backup_picks,
        "all_decisions": decisions,
        "summary": {
            "total": len(decisions),
            "main": len(main_picks),
            "backup": len(backup_picks),
            "observe": sum(1 for d in decisions if d["level"] == "观察"),
            "pass": sum(1 for d in decisions if d["level"] == "不参与"),
        },
    }
    logger.info(f"主推{len(main_picks)} 备选{len(backup_picks)} 观察{result['summary']['observe']} 不参与{result['summary']['pass']}")
    return result


def main():
    try:
        r = run()
        if r is None:
            sys.exit(1)
        json.dump(r, open(OUTPUT_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=str)
        logger.info(f"已保存到 {OUTPUT_FILE}")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"严重错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
