# ====== 网络配置:绕过系统代理 ======
import os
for var in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"]:
    os.environ.pop(var, None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

"""
stage5_push.py - 格式化并推送最终结果
"""
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.serverchan_push import quick_push

Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.FileHandler("logs/stage5_push.log", encoding="utf-8"), logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

INPUT_FILE = Path(__file__).parent.parent / "data" / "final_picks.json"


def fmt_market(mc, summary):
    return f"""## 🌡️ 大盘情绪
- 阶段: {mc.get('emotion_stage', '未知')}
- 涨停: {mc.get('limit_up_count', 0)}家 | 最高{mc.get('max_lianban', 0)}板
- 炸板率: {mc.get('blast_rate_pct', 0)}%

## 📊 扫描汇总
共{summary['total']}只 → 🎯主推{summary['main']} 🟡备选{summary['backup']} ⚠️观察{summary['observe']} ⛔不参与{summary['pass']}"""


def fmt_pick(p):
    md = f"""## {p['level_emoji']} {p['level']}: {p['stock_name']} ({p['stock_code']})
**综合评分: {p['final_score']}/100**

**核心逻辑**: {p.get('core_logic', 'N/A')}
"""
    summ = p.get("agent_summary", {})
    md += f"""
### 🤖 Agent 共识
- 龙头辨识: {summ.get('dragon_head')}/10
- 情绪阶段: {summ.get('emotion_cycle')}
- 二板概率: {summ.get('second_board')}%
- 量化博弈: {summ.get('quant_reverse')}
- 风控: {summ.get('risk_control')}
"""
    tp = p.get("trade_plan")
    if tp:
        md += f"""
### 💰 交易计划
- 买入: {tp.get('ideal_buy_price')}元
- 止损: {tp.get('stop_loss_price')}元 ({tp.get('stop_loss_pct')}%)
- 止盈: {tp.get('take_profit_price')}元 (+{tp.get('take_profit_pct')}%)
- 仓位: {tp.get('suggested_position_pct')}% | 持有≤{tp.get('max_holding_days')}天
"""
    es = p.get("entry_strategy")
    if es:
        md += f"""
### 🎯 入场策略
- 理想: {es.get('best_case', '')}
- 次优: {es.get('fallback_case', '')}
- 放弃: {es.get('abort_case', '')}
"""
    risks = p.get("key_risks")
    if risks:
        md += "\n### ⚠️ 风险\n" + "\n".join(f"- {r}" for r in risks) + "\n"
    ref = p.get("reflection")
    if ref:
        md += f"\n### 🤔 系统反思\n- 若跌5%: {ref.get('if_drop_5pct', '')}\n- 若涨停: {ref.get('if_zhangting', '')}\n"
    return md


def build_content(data):
    today = datetime.now().strftime("%Y-%m-%d")
    main = data.get("main_picks", [])
    backup = data.get("backup_picks", [])
    mc = data.get("market_context", {})
    summary = data.get("summary", {})

    if main:
        title = f"🎯 {today} 主推: {main[0]['stock_name']}({main[0]['stock_code']})"
    elif backup:
        title = f"🟡 {today} 备选: {backup[0]['stock_name']}"
    else:
        title = f"⛔ {today} 今日不出推荐"

    parts = [f"# 📊 {today} A股短线决策\n"]
    if main:
        parts.append("# 🎯 主推标的\n")
        for p in main:
            parts.append(fmt_pick(p))
            parts.append("\n---\n")
    if backup:
        parts.append("# 🟡 备选标的\n")
        for p in backup:
            parts.append(fmt_pick(p))
            parts.append("\n---\n")
    if not main and not backup:
        parts.append("# ⛔ 今日不出推荐\n\n经完整Agent辩论,无股票达到主推门槛(综合分≥78)。\n\n**宁缺毋滥 > 凑数推荐。**\n")
        # 附 TOP3 观察
        tops = data.get("all_decisions", [])[:3]
        if tops:
            parts.append("\n### 📋 TOP3 候选(仅观察)\n")
            for d in tops:
                parts.append(f"- {d['stock_name']}({d['stock_code']}) 分{d['final_score']:.1f}\n")
    parts.append("\n" + fmt_market(mc, summary))
    parts.append("\n\n---\n⚠️ 仅供参考,不构成投资建议。明日09:15前请再次确认。")
    return title, "\n".join(parts)


def main():
    if not INPUT_FILE.exists():
        logger.error(f"找不到 {INPUT_FILE}")
        sys.exit(1)
    data = json.load(open(INPUT_FILE, encoding="utf-8"))
    title, content = build_content(data)
    logger.info(f"推送标题: {title}")
    logger.info(f"推送长度: {len(content)} 字符")
    ok = quick_push(title, content, tags="daily_top_picks|短线决策")
    logger.info("推送成功" if ok else "推送失败")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
