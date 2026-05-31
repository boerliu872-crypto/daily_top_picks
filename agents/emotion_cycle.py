"""
agents/emotion_cycle.py - 情绪周期 Agent (涅槃重生+养家)
分析大盘情绪,不针对单只股票
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


SYSTEM_PROMPT = """你是A股情绪周期判官,融合涅槃重生"六维情绪体系"和炒股养家"情绪哲学"。

五大情绪阶段:
- 冰点期❄️:连板≤3+涨停<30家+炸板率>40% → 空仓,仓位上限10%
- 启动期🌱:连板3-4+涨停30-50家+炸板率30-40% → 试探,仓位上限30%
- 发酵期🔥:连板5+涨停50-80家+炸板率25-30% → 主升,仓位上限70%
- 高潮期🌋:连板≥7+涨停>80家+炸板率<25% → 满仓但警惕,仓位上限90%
- 退潮期🌊:龙头断板/晋级率<20%+炸板率回升>40% → 离场,仓位上限20%

必须输出严格JSON:
{
  "agent": "emotion_cycle",
  "current_stage": "冰点期/启动期/发酵期/高潮期/退潮期",
  "stage_emoji": "对应emoji",
  "score": 0-10,
  "max_position_pct": 数字,
  "transition_signals": ["切换信号1", "切换信号2"],
  "operation_advice": "仓位与方向建议<100字",
  "evidence": ["证据1", "证据2"],
  "confidence": 0-1
}"""


def build_user_prompt(m: Dict) -> str:
    return f"""分析当前A股情绪周期:

涨停股总数:{m.get('limit_up_count', 0)} 跌停股:{m.get('limit_down_count', 0)}
炸板数:{m.get('blast_count', 0)} 炸板率:{m.get('blast_rate_pct', 0):.1f}%
最高连板:{m.get('max_lianban', 0)}板
连板梯队:5板+={m.get('lianban_5plus', 0)} 4板={m.get('lianban_4', 0)} 3板={m.get('lianban_3', 0)} 2板={m.get('lianban_2', 0)} 首板={m.get('lianban_1', 0)}
昨日情绪:{m.get('yesterday_stage', '未知')} 已持续:{m.get('stage_duration_days', 1)}天

按6维情绪体系判断阶段,输出严格JSON。"""


def analyze(market_data: Dict, _unused: Optional[Dict] = None) -> Dict:
    api_key = get_deepseek_key()
    if not api_key:
        return {"agent": "emotion_cycle", "error": "no key", "score": 5, "current_stage": "混沌期", "max_position_pct": 30}
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": build_user_prompt(market_data)}],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        result = json.loads(resp.choices[0].message.content)
        result["agent"] = "emotion_cycle"
        return result
    except Exception as e:
        logger.exception(f"情绪周期失败: {e}")
        return {"agent": "emotion_cycle", "error": str(e), "score": 5, "current_stage": "混沌期", "max_position_pct": 30}
