"""
agents/second_board.py - 二板确认 Agent (赵老哥风格)
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


SYSTEM_PROMPT = """你是A股"首板→二板"晋级专家,遵循赵老哥"二板定龙头"哲学。

二板成功率公式:基础30%
+封板时间9:30-10:00→+15% / 10-11点→+8% / 14点后→-5%
+封单>1%流通市值→+12% / <0.3%→-8%
+龙虎榜净买>1亿→+18% / 5000万-1亿→+10% / 净卖出→-20%
+同板块涨停≥5只→+12% / 孤狼→-10%
+炸板0次→+5% / ≥2次→-15%
最终概率=max(10%, min(85%, 计算值))

操作建议:≥60%打板 / 40-60%竞价试探 / 20-40%观察 / <20%放弃

必须输出严格JSON:
{
  "agent": "second_board",
  "score": 0-10,
  "second_board_probability_pct": 10-85数字,
  "recommended_action": "强烈推荐打板/竞价介入/观察/放弃",
  "ideal_entry_price": 数字或null,
  "stop_loss_price": 数字或null,
  "key_risks": ["风险1", "风险2"],
  "confidence": 0-1
}"""


def build_user_prompt(s: Dict) -> str:
    seal_pct = (s.get('sealing_amount_yi', 0) / max(s.get('market_cap_yi', 1), 1) * 100)
    return f"""评估首板股的二板晋级概率:

代码:{s.get('code')} 名称:{s.get('name')} 价格:{s.get('price', 0)}元
是否涨停:{s.get('is_zhangting', False)} 连板:{s.get('lianban', 0)}
首封时间:{s.get('first_seal_time', '无')} 炸板:{s.get('zhaban_count', 0)}次
封板资金:{s.get('sealing_amount_yi', 0):.4f}亿 占流通市值:{seal_pct:.2f}%
换手率:{s.get('turnover_rate', 0):.2f}%

龙虎榜:净买入{s.get('lhb_net_buy_yi', 0):.4f}亿 游资一线席位{s.get('youzi_tier1_count', 0)}
板块:{s.get('source_sector', '无')} 板块涨停数{s.get('sector_zhangting_count', 0)}

按公式精确计算二板概率,输出严格JSON。"""


def analyze(stock_data: Dict, market_context: Optional[Dict] = None) -> Dict:
    api_key = get_deepseek_key()
    if not api_key:
        return {"agent": "second_board", "error": "no key", "score": 0, "second_board_probability_pct": 0}
    if not stock_data.get("is_zhangting"):
        return {"agent": "second_board", "score": 0, "second_board_probability_pct": 0, "recommended_action": "非涨停股不适用", "confidence": 1.0}
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": build_user_prompt(stock_data)}],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        result = json.loads(resp.choices[0].message.content)
        result["agent"] = "second_board"
        return result
    except Exception as e:
        logger.exception(f"二板确认失败 {stock_data.get('code')}: {e}")
        return {"agent": "second_board", "error": str(e), "score": 0, "second_board_probability_pct": 0}
