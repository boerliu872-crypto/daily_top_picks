"""
agents/risk_control.py - 风控 Agent (纯规则,不调用LLM,快速)
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

BLACKLIST = ["ST", "退", "*ST"]

POSITION_RULES = {
    "冰点期": {"total": 0.10, "single": 0.05},
    "启动期": {"total": 0.30, "single": 0.10},
    "发酵期": {"total": 0.70, "single": 0.15},
    "高潮期": {"total": 0.90, "single": 0.20},
    "退潮期": {"total": 0.20, "single": 0.05},
    "混沌期": {"total": 0.30, "single": 0.10},
}


def analyze(stock_data: Dict, market_context: Optional[Dict] = None) -> Dict:
    try:
        veto_reasons = []
        name = stock_data.get("name", "")
        for kw in BLACKLIST:
            if kw in name:
                veto_reasons.append(f"黑名单({kw})")
                break
        code = str(stock_data.get("code", ""))
        if code.startswith(("8", "9")):
            veto_reasons.append("北交所(流动性风险)")
        mc = stock_data.get("market_cap_yi", 0)
        if mc < 20:
            veto_reasons.append(f"市值过小({mc:.1f}亿)")
        elif mc > 1000:
            veto_reasons.append(f"市值过大({mc:.1f}亿)")
        tr = stock_data.get("turnover_rate", 0)
        if tr > 25:
            veto_reasons.append(f"换手过高({tr:.1f}%)")
        bias = stock_data.get("bias_ma5") or 0
        if bias > 15:
            veto_reasons.append(f"乖离过高({bias:.1f}%)")

        # 周五风险
        if datetime.now().weekday() == 4:
            veto_reasons.append("周五(持仓过周末)")

        emotion = market_context.get("emotion_stage", "混沌期") if market_context else "混沌期"
        rules = POSITION_RULES.get(emotion, POSITION_RULES["混沌期"])

        is_veto = len(veto_reasons) > 0
        quality = 0 if is_veto else 10
        if not is_veto:
            if bias > 10:
                quality -= 2
            elif bias > 7:
                quality -= 1
            if tr > 20:
                quality -= 1

        return {
            "agent": "risk_control",
            "veto": is_veto,
            "veto_reasons": veto_reasons,
            "quality_score": max(0, quality),
            "recommended_position_pct": min(rules["single"] * 100, 15),
            "stop_loss_pct": -3,
            "max_holding_days": 3,
            "confidence": 1.0,
        }
    except Exception as e:
        logger.exception(f"风控失败: {e}")
        return {"agent": "risk_control", "veto": True, "veto_reasons": [f"异常:{str(e)[:80]}"], "quality_score": 0, "confidence": 0}
