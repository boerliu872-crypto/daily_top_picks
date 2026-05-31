# ====== 网络配置:绕过系统代理 ======
import os
for var in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"]:
    os.environ.pop(var, None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

"""
stage3_agents.py - Agent 调度器
"""
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent))
from agents import dragon_head, emotion_cycle, second_board, quant_reverse, risk_control

Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.FileHandler("logs/stage3_agents.log", encoding="utf-8"), logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

INPUT_FILE = Path(__file__).parent.parent / "data" / "enhanced_candidates.json"
OUTPUT_FILE = Path(__file__).parent.parent / "data" / "agent_results.json"


def build_market_context(candidates: List[Dict]) -> Dict:
    """从候选股反推大盘情绪指标"""
    limit_up = sum(1 for c in candidates if c.get("is_zhangting"))
    max_lb = max((c.get("lianban", 0) for c in candidates), default=0)
    blast = sum(c.get("zhaban_count", 0) for c in candidates)
    lb_count = {}
    for c in candidates:
        lb = c.get("lianban", 0)
        lb_count[lb] = lb_count.get(lb, 0) + 1
    return {
        "limit_up_count": limit_up,
        "limit_down_count": 0,
        "blast_count": blast,
        "blast_rate_pct": round(blast / max(limit_up, 1) * 100, 1),
        "max_lianban": max_lb,
        "lianban_5plus": sum(v for k, v in lb_count.items() if k >= 5),
        "lianban_4": lb_count.get(4, 0),
        "lianban_3": lb_count.get(3, 0),
        "lianban_2": lb_count.get(2, 0),
        "lianban_1": lb_count.get(1, 0),
        "yesterday_stage": "未知",
        "stage_duration_days": 1,
    }


def analyze_one_stock(stock: Dict, market_ctx: Dict) -> Dict:
    """对单只股票并行跑4个个股Agent"""
    code = stock["code"]
    results = {"stock_code": code, "stock_name": stock.get("name", "")}
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {
            "dragon_head": ex.submit(dragon_head.analyze, stock, market_ctx),
            "second_board": ex.submit(second_board.analyze, stock, market_ctx),
            "quant_reverse": ex.submit(quant_reverse.analyze, stock, market_ctx),
            "risk_control": ex.submit(risk_control.analyze, stock, market_ctx),
        }
        for name, fut in futures.items():
            try:
                results[name] = fut.result(timeout=120)
            except Exception as e:
                logger.error(f"   {code} {name} 失败: {e}")
                results[name] = {"error": str(e)}
    return results


def run():
    logger.info("=" * 60)
    logger.info(f"启动Agent辩论 - {datetime.now()}")
    logger.info("=" * 60)
    if not INPUT_FILE.exists():
        logger.error(f"找不到 {INPUT_FILE}")
        return None
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    candidates = data.get("candidates", [])
    if not candidates:
        logger.info("候选池为空,生成空Agent结果")
        return {"market_context": {"emotion_stage": "无数据"}, "emotion_cycle": {}, "stocks": []}
    logger.info(f"待分析 {len(candidates)} 只")

    # 1. 大盘情绪(跑1次)
    market_ctx = build_market_context(candidates)
    logger.info("跑情绪周期Agent(大盘级)...")
    emotion_result = emotion_cycle.analyze(market_ctx)
    market_ctx["emotion_stage"] = emotion_result.get("current_stage", "混沌期")
    logger.info(f"当前情绪阶段: {market_ctx['emotion_stage']}")

    # 2. 逐只分析
    all_results = {"market_context": market_ctx, "emotion_cycle": emotion_result, "stocks": []}
    for i, c in enumerate(candidates, 1):
        logger.info(f"[{i}/{len(candidates)}] 分析 {c['code']} {c.get('name', '')}")
        r = analyze_one_stock(c, market_ctx)
        r["emotion_cycle"] = emotion_result
        all_results["stocks"].append(r)
        dh = r.get("dragon_head", {}).get("score", "?")
        qr = r.get("quant_reverse", {}).get("current_phase", "?")
        logger.info(f"   龙头={dh} 量化博弈={qr}")

    return all_results


def save(results):
    out = {"generated_at": datetime.now().isoformat(), **results}
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    logger.info(f"已保存到 {OUTPUT_FILE}")


def main():
    try:
        results = run()
        if results is None:
            sys.exit(1)
        save(results)
        sys.exit(0)
    except Exception as e:
        logger.exception(f"严重错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
