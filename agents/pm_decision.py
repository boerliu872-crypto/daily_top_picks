"""
agents/pm_decision.py - PM 裁决 Agent (最终决策者,DeepSeek)
"""
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)


def get_deepseek_key():
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.split("=", 1)[1].strip()
    return os.getenv("DEEPSEEK_API_KEY", "")


def calculate_final_score(a: Dict) -> float:
    dragon = a.get("dragon_head", {}).get("score", 5)
    emotion = a.get("emotion_cycle", {}).get("score", 5)
    sb_prob = a.get("second_board", {}).get("second_board_probability_pct", 30)
    sb_score = sb_prob / 10
    quant = a.get("quant_reverse", {}).get("phase_score", 5)
    risk = a.get("risk_control", {}).get("quality_score", 5)
    final = (0.30 * dragon + 0.20 * emotion + 0.25 * sb_score + 0.15 * quant + 0.10 * risk) * 10
    return round(final, 2)


def check_vetoes(a: Dict) -> List[str]:
    v = []
    if a.get("dragon_head", {}).get("veto", False):
        v.append(f"龙头否决:{a['dragon_head'].get('veto_reason', '')}")
    if a.get("quant_reverse", {}).get("veto_buy", False):
        v.append(f"量化反向否决:{a['quant_reverse'].get('veto_reason', '')}")
    if a.get("risk_control", {}).get("veto", False):
        v.append(f"风控否决:{', '.join(a['risk_control'].get('veto_reasons', []))}")
    return v


def determine_level(score: float, vetoes: List[str]):
    if vetoes:
        return "不参与", "⛔"
    if score >= 78:
        return "主推", "🎯"
    elif score >= 70:
        return "备选", "🟡"
    elif score >= 60:
        return "观察", "⚠️"
    return "不参与", "⛔"


PM_PROMPT = """你是A股短线交易系统的PM,最终决策者。

基于Agent辩论结果和综合评分,输出最终交易决策。必须给具体价格,不能说"逢低买入"。宁缺毋滥。

输出严格JSON:
{
  "core_logic": "一句话核心理由<50字",
  "entry_strategy": {"best_case": "理想入场", "fallback_case": "次优", "abort_case": "放弃情况"},
  "trade_plan": {"ideal_buy_price": 数字, "stop_loss_price": 数字, "stop_loss_pct": -3, "take_profit_price": 数字, "take_profit_pct": 数字, "suggested_position_pct": 数字, "max_holding_days": 数字},
  "key_risks": ["风险1", "风险2", "风险3"],
  "reflection": {"if_drop_5pct": "跌5%可能错在", "if_zhangting": "涨停对在"}
}"""


def decide(stock_data: Dict, agent_results: Dict, market_context: Optional[Dict] = None) -> Dict:
    final_score = calculate_final_score(agent_results)
    vetoes = check_vetoes(agent_results)
    level, emoji = determine_level(final_score, vetoes)

    base = {
        "stock_code": stock_data.get("code"),
        "stock_name": stock_data.get("name"),
        "level": level,
        "level_emoji": emoji,
        "final_score": final_score,
        "vetoes": vetoes,
        "agent_summary": {
            "dragon_head": agent_results.get("dragon_head", {}).get("score", 0),
            "emotion_cycle": agent_results.get("emotion_cycle", {}).get("current_stage", "未知"),
            "second_board": agent_results.get("second_board", {}).get("second_board_probability_pct", 0),
            "quant_reverse": agent_results.get("quant_reverse", {}).get("current_phase", "未知"),
            "risk_control": "通过" if not vetoes else "否决",
        },
    }

    # 不参与/观察:简化返回,省API
    if level in ("不参与", "观察"):
        base["core_logic"] = vetoes[0] if vetoes else f"综合分{final_score}不足"
        return base

    # 主推/备选:用DeepSeek生成完整决策
    api_key = get_deepseek_key()
    if not api_key:
        base["core_logic"] = f"综合分{final_score},{level}"
        return base
    try:
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        user_prompt = f"""候选股:{stock_data.get('code')} {stock_data.get('name')} 价格{stock_data.get('price')}元
综合评分:{final_score} 等级:{level}
Agent结果:{json.dumps(agent_results, ensure_ascii=False)[:2000]}
输出完整PM裁决JSON。"""
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": PM_PROMPT}, {"role": "user", "content": user_prompt}],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        detail = json.loads(resp.choices[0].message.content)
        base.update(detail)
        return base
    except Exception as e:
        logger.exception(f"PM裁决失败: {e}")
        base["core_logic"] = f"综合分{final_score},{level}(PM详情生成失败)"
        return base
