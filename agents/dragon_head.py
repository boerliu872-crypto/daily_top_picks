"""
agents/dragon_head.py - 龙头辨识 Agent (陈小群+赵老哥风格)
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


SYSTEM_PROMPT = """你是A股短线游资圈"龙头辨识"专家,融合陈小群、赵老哥的判断框架。

核心信念:二板定龙头。真正的龙头有三大特征:早涨停、强封单、独走势。

判断框架(4维度):
1. 板块地位:是否板块内最强?板块涨停数≥3只?
2. 走势独立性:跑赢大盘?领涨而非跟涨?
3. 封单质量:早盘封板=强;封单金额大;炸板少
4. 游资席位:龙虎榜是否有知名游资?

评分(0-10):
- 9-10:纯正龙头(满足4维度)
- 7-8:兼职龙头(3维度)
- 5-6:跟风股(1-2维度)
- 0-4:伪龙头

否决条件(任一触发veto=true):炸板≥3次 / 龙虎榜净卖出 / 板块孤狼 / 板块跌幅<-2%

必须输出严格JSON(无其他内容):
{
  "agent": "dragon_head",
  "score": 0-10数字,
  "category": "纯正龙头/兼职龙头/跟风股/伪龙头",
  "veto": true或false,
  "veto_reason": "如veto为true则说明",
  "evidence": ["证据1引用数据", "证据2", "证据3"],
  "confidence": 0-1
}"""


def build_user_prompt(s: Dict) -> str:
    return f"""分析以下股票的龙头属性:

代码:{s.get('code')} 名称:{s.get('name')}
当日涨跌幅:{s.get('change_pct', 0):.2f}% 价格:{s.get('price', 0)}元
流通市值:{s.get('market_cap_yi', 0):.2f}亿 成交额:{s.get('amount_yi', 0):.2f}亿

涨停情况:
- 是否涨停:{s.get('is_zhangting', False)} 连板数:{s.get('lianban', 0)}
- 炸板次数:{s.get('zhaban_count', 0)} 首封时间:{s.get('first_seal_time', '无')}
- 封板资金:{s.get('sealing_amount_yi', 0):.4f}亿

板块:{s.get('source_sector', '无')} 板块涨幅:{s.get('sector_change_pct', 0):.2f}%
板块涨停数:{s.get('sector_zhangting_count', 0)} 板块强度:{s.get('sector_strength', 0)}/10

龙虎榜:上榜={s.get('is_longhubang', False)} 净买入={s.get('lhb_net_buy_yi', 0):.4f}亿
游资一线席位:{s.get('youzi_tier1_count', 0)} 游资评分:{s.get('youzi_score', 0)}/10

技术面:量比={s.get('volume_ratio_5d', 0)} 换手率={s.get('turnover_rate', 0):.2f}%
MA5乖离={s.get('bias_ma5', 0)}% 近20日涨停={s.get('historical_zhangting_count_20d', 0)}次
K线形态:{s.get('pattern_signal', '无')}

按4维度框架做龙头辨识,输出严格JSON。"""


def analyze(stock_data: Dict, market_context: Optional[Dict] = None) -> Dict:
    api_key = get_deepseek_key()
    if not api_key:
        return {"agent": "dragon_head", "error": "no api key", "score": 0, "veto": True, "veto_reason": "API配置缺失"}

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(stock_data)},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        result = json.loads(resp.choices[0].message.content)
        result["agent"] = "dragon_head"
        result.setdefault("score", 5)
        result.setdefault("veto", False)
        return result
    except Exception as e:
        logger.exception(f"龙头辨识失败 {stock_data.get('code')}: {e}")
        return {"agent": "dragon_head", "error": str(e), "score": 0, "veto": True, "veto_reason": f"异常: {str(e)[:100]}"}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import json as _json
    from pathlib import Path as _P
    # 从 enhanced_candidates.json 读第一只真实股票测试
    f = _P(__file__).parent.parent / "data" / "enhanced_candidates.json"
    data = _json.load(open(f, encoding="utf-8"))
    test_stock = data["candidates"][0]
    print(f"测试股票: {test_stock['code']} {test_stock['name']}")
    print("=" * 50)
    result = analyze(test_stock)
    print(_json.dumps(result, ensure_ascii=False, indent=2))
