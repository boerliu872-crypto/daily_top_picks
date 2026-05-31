# ====== 网络配置:绕过所有系统代理 ======
import os
for var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy', 'FTP_PROXY', 'ftp_proxy']:
    os.environ.pop(var, None)
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'

"""
stage2_factor.py - 因子增强 (Tushare 版,K线走 Tushare 不被反爬)
"""

import json
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import akshare as ak
import numpy as np
import pandas as pd
import tushare as ts

Path('logs').mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler('logs/stage2_factor.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

INPUT_FILE = Path(__file__).parent.parent / 'data' / 'candidate_pool.json'
OUTPUT_FILE = Path(__file__).parent.parent / 'data' / 'enhanced_candidates.json'

# ====== 初始化 Tushare ======
def load_tushare_token():
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        for line in env_path.read_text(encoding='utf-8').splitlines():
            if line.startswith('TUSHARE_TOKEN='):
                return line.split('=', 1)[1].strip()
    return os.getenv('TUSHARE_TOKEN', '')

TS_TOKEN = load_tushare_token()
if TS_TOKEN:
    ts.set_token(TS_TOKEN)
    pro = ts.pro_api()
    logger.info('Tushare 初始化成功')
else:
    pro = None
    logger.warning('未找到 TUSHARE_TOKEN')


def to_ts_code(code: str) -> str:
    """002432 -> 002432.SZ, 600590 -> 600590.SH"""
    code = str(code).zfill(6)
    if code.startswith('6'):
        return f'{code}.SH'
    elif code.startswith(('0', '3')):
        return f'{code}.SZ'
    elif code.startswith(('8', '4')):
        return f'{code}.BJ'
    return f'{code}.SZ'


def fetch_daily_history_ts(stock_code: str, days: int = 60) -> pd.DataFrame:
    """用 Tushare 拉日K线,字段重命名为中文兼容原代码"""
    if pro is None:
        return pd.DataFrame()
    try:
        ts_code = to_ts_code(stock_code)
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days * 2)).strftime('%Y%m%d')
        time.sleep(0.15)
        df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        if df is None or df.empty:
            return pd.DataFrame()
        # Tushare 返回是倒序(最新在前),需要正序
        df = df.sort_values('trade_date').reset_index(drop=True)
        # 字段映射: Tushare -> 原中文字段
        df = df.rename(columns={
            'trade_date': '日期', 'open': '开盘', 'high': '最高',
            'low': '最低', 'close': '收盘', 'vol': '成交量', 'amount': '成交额',
        })
        df['日期'] = pd.to_datetime(df['日期'])
        return df.tail(days).reset_index(drop=True)
    except Exception as e:
        logger.warning(f'   Tushare K线失败 {stock_code}: {str(e)[:80]}')
        return pd.DataFrame()


def calculate_technical_factors(hist: pd.DataFrame) -> Dict:
    if hist.empty or len(hist) < 20:
        return {'ma5': None, 'ma10': None, 'ma20': None, 'bias_ma5': None,
                'volume_ratio_5d': None, 'recent_volatility_10d': None,
                'price_position_60d': None, 'historical_zhangting_count_20d': 0}
    latest = hist.iloc[-1]
    close_price = latest['收盘']
    ma5 = hist['收盘'].tail(5).mean()
    ma10 = hist['收盘'].tail(10).mean()
    ma20 = hist['收盘'].tail(20).mean()
    bias_ma5 = (close_price - ma5) / ma5 * 100
    vol_5d_avg = hist['成交量'].tail(5).mean()
    volume_ratio_5d = latest['成交量'] / vol_5d_avg if vol_5d_avg > 0 else 1.0
    recent_10 = hist.tail(10)
    recent_volatility_10d = recent_10['收盘'].std() / recent_10['收盘'].mean() * 100
    recent_60 = hist.tail(min(60, len(hist)))
    price_min = recent_60['最低'].min()
    price_max = recent_60['最高'].max()
    price_position_60d = (close_price - price_min) / (price_max - price_min) * 100 if price_max > price_min else 50
    recent_20 = hist.tail(20).copy()
    recent_20['daily_return'] = recent_20['收盘'].pct_change() * 100
    zhangting_count_20d = (recent_20['daily_return'] >= 9.8).sum()
    return {'ma5': round(float(ma5), 2), 'ma10': round(float(ma10), 2),
            'ma20': round(float(ma20), 2), 'bias_ma5': round(float(bias_ma5), 2),
            'volume_ratio_5d': round(float(volume_ratio_5d), 2),
            'recent_volatility_10d': round(float(recent_volatility_10d), 2),
            'price_position_60d': round(float(price_position_60d), 1),
            'historical_zhangting_count_20d': int(zhangting_count_20d)}


def identify_pattern_signals(hist: pd.DataFrame) -> Dict:
    if hist.empty or len(hist) < 5:
        return {'pattern_signal': '数据不足', 'pattern_score': 0}
    recent = hist.tail(5)
    signals = []
    score = 5
    if len(hist) >= 20:
        ma5 = hist['收盘'].tail(5).mean()
        ma10 = hist['收盘'].tail(10).mean()
        ma20 = hist['收盘'].tail(20).mean()
        if ma5 > ma10 > ma20:
            signals.append('多头排列'); score += 2
        elif ma5 < ma10 < ma20:
            signals.append('空头排列'); score -= 2
    if len(recent) >= 2:
        prev = recent.iloc[-2]; curr = recent.iloc[-1]
        if curr['收盘'] > prev['开盘'] and curr['开盘'] < prev['收盘'] and curr['收盘'] > curr['开盘']:
            signals.append('阳包阴'); score += 1.5
    if len(hist) >= 10:
        vol_avg = hist['成交量'].tail(10).mean()
        if recent.iloc[-1]['成交量'] > vol_avg * 1.5 and recent.iloc[-1]['收盘'] > recent.iloc[-1]['开盘']:
            signals.append('放量阳线'); score += 1
    pattern = '、'.join(signals) if signals else '中性'
    return {'pattern_signal': pattern, 'pattern_score': min(10, max(0, round(score, 1)))}


def enhance_one(candidate: Dict) -> Dict:
    code = candidate['code']
    logger.info(f'   增强 {code} {candidate.get("name", "")}')
    hist = fetch_daily_history_ts(code, days=60)
    tech = calculate_technical_factors(hist)
    pattern = identify_pattern_signals(hist)
    return {**candidate, **tech, **pattern,
            'youzi_seats': [], 'youzi_tier1_count': 0, 'youzi_tier2_count': 0,
            'youzi_score': 0, 'youzi_net_buy_yi': 0,
            'sector_strength': 5, 'sector_zhangting_count': 0, 'sector_change_pct': 0}


def run():
    logger.info('=' * 60)
    logger.info(f'启动因子增强(Tushare) - {datetime.now()}')
    logger.info('=' * 60)
    if not INPUT_FILE.exists():
        logger.error(f'找不到 {INPUT_FILE}')
        return None
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    candidates = data.get('candidates', [])
    if not candidates:
        return []
    logger.info(f'待增强 {len(candidates)} 只')
    enhanced_list = []
    for i, c in enumerate(candidates, 1):
        try:
            e = enhance_one(c)
            enhanced_list.append(e)
            logger.info(f'   [{i}/{len(candidates)}] {c["code"]} MA5={e["ma5"]} 形态={e["pattern_signal"]}')
        except Exception as ex:
            logger.error(f'   {c["code"]} 失败: {ex}')
            enhanced_list.append(c)
    logger.info(f'完成,共 {len(enhanced_list)} 只')
    return enhanced_list


def save(items):
    output = {'generated_at': datetime.now().isoformat(), 'count': len(items), 'candidates': items}
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    logger.info(f'已保存到 {OUTPUT_FILE}')


def main():
    try:
        items = run()
        if items is None:
            sys.exit(1)
        save(items)
        sys.exit(0)
    except Exception as e:
        logger.exception(f'严重错误: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
