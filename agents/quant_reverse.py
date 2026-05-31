"""
agents/quant_reverse.py - 量化反向 Agent (灵魂Agent,基于梁文锋判断)
"""
import json
import logging
import os
from pathlib import Path
from typing import Dict, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)


def get_deepseek_key():
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.split("=", 1)[1].strip()
    return os.getenv("DEEPSEEK_API_KEY", "")


SYSTEM_PROMPT = """你是系统的"反向思考者",站在A股量化机构视角看问题。

核心问题:这只股票上,量化机构在收割散户,还是被游资反收割?

核心信念(梁文锋):A股量化的alpha来源是散户非理性。但游资能识别量化模式反向操作。真正赚钱的散户跟随游资,避开量化收割期。

四种博弈状态:
- 量化收割期🔴:散户情绪化+量化机械收割+游资未出手 → 一票否决,phase_score 0-2
- 量化被反收割期🟢:游资逆量化+龙虎榜游资席位+突破量化预期 → 最高优先级,phase_score 8-10
- 共识期🟢:量化游资散户同向+趋势明确 → 跟进,phase_score 6-7
- 混沌期🟡:信号不清+多空胶着 → 观察,phase_score 3-5

否决权使用边界(重要!):只在【明确量化收割期】才 veto_buy=true。信号不清时标"混沌期"(veto=false)。过度否决=系统永不出推荐=失去价值。

必须输出严格JSON:
{
  "agent": "quant_reverse",
  "current_phase": "量化收割期/量化被反收割期/共识期/混沌期",
  "phase_score": 0-10,
  "retail_behavior": "追涨/杀跌/扛单/分歧",
  "quant_intervention": "high/medium/low",
  "youzi_resistance": "明显/中等/无",
  "veto_buy": true或false,
  "veto_reason": "如否决则说明",
  "evidence": ["证据1引用数据", "证据2", "证据3"],
  "key_insight": "核心洞察<50字",
  "confidence": 0-1
}"""


def build_user_prompt(s: Dict, m: Optional[Dict] = None) -> str:
    market = ""
    if m:
        market = f"\n大盘:涨停{m.get('limit_up_count', 0)}家 情绪{m.get('emotion_stage', '未知')}\n"
    return f"""对以下股票做量化反向分析:
{market}
代码:{s.get('code')} 名称:{s.get('name')} 涨跌幅:{s.get('change_pct', 0):.2f}%
价格:{s.get('price', 0)}元 换手率:{s.get('turnover_rate', 0):.2f}% 量比:{s.get('volume_ratio_5d', 0)}
连板:{s.get('lianban', 0)} 炸板:{s.get('zhaban_count', 0)}次

龙虎榜:净买入{s.get('lhb_net_buy_yi', 0):.4f}亿 游资一线席位{s.get('youzi_tier1_count', 0)} 游资评分{s.get('youzi_score', 0)}/10

技术面:MA5乖离{s.get('bias_ma5', 0)}% 60日位置{s.get('price_position_60d', 0)}%
近20日涨停{s.get('historical_zhangting_count_20d', 0)}次 形态{s.get('pattern_signal', '无')}
波动率{s.get('recent_volatility_10d', 0)}%

从量化机构视角判定博弈阶段。审慎用否决权。输出严格JSON。"""


def analyze(stock_data: Dict, market_context: Optional[Dict] = None) -> Dict:
    api_key = get_deepseek_key()
    if not api_key:
        return {"agent": "quant_reverse", "error": "no key", "phase_score": 5, "veto_buy": False, "current_phase": "混沌期"}
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": build_user_prompt(stock_data, market_context)}],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        result = json.loads(resp.choices[0].message.content)
        result["agent"] = "quant_reverse"
        result.setdefault("phase_score", 5)
        result.setdefault("veto_buy", False)
        result.setdefault("current_phase", "混沌期")
        return result
    except Exception as e:
        logger.exception(f"量化反向失败 {stock_data.get('code')}: {e}")
        return {"agent": "quant_reverse", "error": str(e), "phase_score": 5, "veto_buy": False, "current_phase": "混沌期"}
