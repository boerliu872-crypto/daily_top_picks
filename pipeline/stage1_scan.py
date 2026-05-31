# ============================================
# 网络配置:绕过所有系统代理
# ============================================
import os
# 清除所有可能的代理环境变量
for var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy', 'FTP_PROXY', 'ftp_proxy']:
    os.environ.pop(var, None)
# 强制设置 NO_PROXY,告诉 requests 库所有域名都不走代理
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'
"""
============================================
stage1_scan.py - 全市场扫描器
============================================

功能:每日盘后扫描全市场,筛出30只候选股
输入:无(自动获取当日数据)
输出:data/candidate_pool.json
"""

import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
# 清除系统代理环境变量
import os
for proxy_var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
    os.environ.pop(proxy_var, None)

import akshare as ak
import pandas as pd

# ============================================
# 配置
# ============================================

# 确保 logs 目录存在
Path('logs').mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler('logs/stage1_scan.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent / 'data'
OUTPUT_DIR.mkdir(exist_ok=True)
CANDIDATE_FILE = OUTPUT_DIR / 'candidate_pool.json'

SCAN_CONFIG = {
    'max_candidates': 30,
    'min_market_cap_yi': 20,
    'max_market_cap_yi': 500,
    'min_turnover_rate': 5.0,
    'max_turnover_rate': 20.0,
    'min_zhangting_for_normal': 10,
}


# ============================================
# 工具函数
# ============================================

def is_friday() -> bool:
    """判断今天是否周五"""
    return datetime.now().weekday() == 4


def filter_st_stocks(df: pd.DataFrame, name_col: str = '名称') -> pd.DataFrame:
    """过滤ST股"""
    if df.empty or name_col not in df.columns:
        return df
    return df[~df[name_col].str.contains('ST|退', na=False, regex=True)]


def filter_beijing_stocks(df: pd.DataFrame, code_col: str = '代码') -> pd.DataFrame:
    """过滤北交所股票"""
    if df.empty or code_col not in df.columns:
        return df
    return df[~df[code_col].astype(str).str.startswith(('8', '9'))]


def safe_to_yi(amount) -> float:
    """转换为亿元"""
    try:
        if pd.isna(amount):
            return 0.0
        return float(amount) / 1e8
    except (TypeError, ValueError):
        return 0.0


# ============================================
# 数据获取层
# ============================================

def fetch_zhangting_pool() -> pd.DataFrame:
    """获取今日涨停股池"""
    try:
        logger.info("📡 获取涨停股池...")
        df = ak.stock_zt_pool_em()
        logger.info(f"   ✅ 涨停股 {len(df)} 只")
        return df
    except Exception as e:
        logger.error(f"   ❌ 涨停股池获取失败: {e}")
        return pd.DataFrame()


def fetch_longhubang() -> pd.DataFrame:
    """获取今日龙虎榜"""
    try:
        today = datetime.now().strftime('%Y%m%d')
        logger.info(f"📡 获取龙虎榜({today})...")
        df = ak.stock_lhb_detail_em(start_date=today, end_date=today)
        logger.info(f"   ✅ 龙虎榜 {len(df)} 条")
        return df
    except Exception as e:
        logger.error(f"   ❌ 龙虎榜获取失败: {e}")
        return pd.DataFrame()


def fetch_top_sectors_stocks(top_n: int = 5) -> pd.DataFrame:
    """获取领涨板块成分股"""
    try:
        logger.info("📡 获取领涨板块...")
        sectors = ak.stock_board_concept_name_em()
        if sectors.empty:
            return pd.DataFrame()
        
        top_sectors = sectors.sort_values('涨跌幅', ascending=False).head(top_n)
        logger.info(f"   ✅ 领涨板块TOP{top_n}: " + 
                    ", ".join(top_sectors['板块名称'].tolist()))
        
        all_members = []
        for sector_name in top_sectors['板块名称']:
            try:
                members = ak.stock_board_concept_cons_em(symbol=sector_name)
                members['source_sector'] = sector_name
                all_members.append(members)
            except Exception as e:
                logger.warning(f"   ⚠️ 板块[{sector_name}]获取失败: {e}")
                continue
        
        if not all_members:
            return pd.DataFrame()
        
        combined = pd.concat(all_members, ignore_index=True)
        combined = combined.sort_values('涨跌幅', ascending=False)
        combined = combined.head(int(len(combined) * 0.3))
        
        logger.info(f"   ✅ 领涨板块成分股 {len(combined)} 只")
        return combined
        
    except Exception as e:
        logger.error(f"   ❌ 领涨板块获取失败: {e}")
        return pd.DataFrame()


# ============================================
# 数据融合与打分层
# ============================================

def merge_candidates(zt_pool, lhb, sectors) -> pd.DataFrame:
    """融合三个来源的候选股"""
    logger.info("🔄 融合多源数据...")
    candidates = {}
    
    # 处理涨停股池
    for _, row in zt_pool.iterrows():
        code = str(row.get('代码', ''))
        if not code:
            continue
        
        candidates[code] = {
            'code': code,
            'name': row.get('名称', ''),
            'change_pct': row.get('涨跌幅', 0),
            'price': row.get('最新价', 0),
            'turnover_rate': row.get('换手率', 0),
            'market_cap_yi': safe_to_yi(row.get('流通市值', 0)),
            'amount_yi': safe_to_yi(row.get('成交额', 0)),
            'lianban': int(row.get('连板数', 1)),
            'zhaban_count': int(row.get('炸板次数', 0)),
            'sealing_amount_yi': safe_to_yi(row.get('封板资金', 0)),
            'first_seal_time': str(row.get('首次封板时间', '')),
            'is_zhangting': True,
            'is_longhubang': False,
            'is_top_sector': False,
            'source_sector': '',
            'lhb_net_buy_yi': 0,
        }
    
    # 处理龙虎榜
    for _, row in lhb.iterrows():
        code = str(row.get('代码', ''))
        if not code:
            continue
        
        lhb_net_buy = safe_to_yi(row.get('龙虎榜净买额', 0))
        
        if code in candidates:
            candidates[code]['is_longhubang'] = True
            candidates[code]['lhb_net_buy_yi'] = lhb_net_buy
        else:
            candidates[code] = {
                'code': code,
                'name': row.get('名称', ''),
                'change_pct': row.get('涨跌幅', 0),
                'price': row.get('收盘价', 0),
                'turnover_rate': 0,
                'market_cap_yi': safe_to_yi(row.get('流通市值', 0)),
                'amount_yi': 0,
                'lianban': 0,
                'zhaban_count': 0,
                'sealing_amount_yi': 0,
                'first_seal_time': '',
                'is_zhangting': False,
                'is_longhubang': True,
                'is_top_sector': False,
                'source_sector': '',
                'lhb_net_buy_yi': lhb_net_buy,
            }
    
    # 处理板块成分股
    if not sectors.empty:
        sector_codes = set(sectors['代码'].astype(str).tolist())
        sector_map = dict(zip(sectors['代码'].astype(str), sectors['source_sector']))
        
        for code in candidates:
            if code in sector_codes:
                candidates[code]['is_top_sector'] = True
                candidates[code]['source_sector'] = sector_map.get(code, '')
    
    df = pd.DataFrame(list(candidates.values()))
    logger.info(f"   ✅ 融合后总候选 {len(df)} 只")
    return df


def apply_hard_filters(df: pd.DataFrame) -> pd.DataFrame:
    """硬过滤"""
    if df.empty:
        return df
    
    original_count = len(df)
    df = filter_st_stocks(df, name_col='name')
    df = filter_beijing_stocks(df, code_col='code')
    
    df = df[
        (df['market_cap_yi'] >= SCAN_CONFIG['min_market_cap_yi']) &
        (df['market_cap_yi'] <= SCAN_CONFIG['max_market_cap_yi'])
    ]
    
    logger.info(f"   🔧 硬过滤后 {len(df)} 只 (剔除 {original_count - len(df)} 只)")
    return df


def calculate_screen_score(row) -> float:
    """计算综合筛选评分"""
    score = 0
    score += row['lianban'] * 30
    
    if row['lhb_net_buy_yi'] > 0:
        score += row['lhb_net_buy_yi'] * 10
    
    if row['is_top_sector']:
        score += 15
    
    if row['is_zhangting']:
        score += 20
    
    tr = row['turnover_rate']
    if SCAN_CONFIG['min_turnover_rate'] <= tr <= SCAN_CONFIG['max_turnover_rate']:
        score += tr / 2
    elif tr > SCAN_CONFIG['max_turnover_rate']:
        score -= 5
    
    score += row['sealing_amount_yi'] * 5
    score -= row['zhaban_count'] * 5
    
    return round(score, 2)


def rank_and_select_top(df: pd.DataFrame) -> pd.DataFrame:
    """打分排序"""
    if df.empty:
        return df
    
    df['screen_score'] = df.apply(calculate_screen_score, axis=1)
    df = df.sort_values('screen_score', ascending=False)
    df = df.head(SCAN_CONFIG['max_candidates'])
    
    logger.info(f"   📊 打分排序后TOP{SCAN_CONFIG['max_candidates']}:")
    for _, row in df.head(10).iterrows():
        logger.info(
            f"      {row['code']} {row['name']:8s} "
            f"score={row['screen_score']:.1f} "
            f"连板={row['lianban']} "
            f"龙虎榜净买={row['lhb_net_buy_yi']:.2f}亿"
        )
    
    return df


# ============================================
# 主流程
# ============================================

def run_scan() -> Optional[List[Dict]]:
    """主扫描函数"""
    logger.info("=" * 60)
    logger.info(f"🚀 启动全市场扫描 - {datetime.now()}")
    logger.info("=" * 60)
    
    if is_friday():
        logger.warning("⚠️ 今天周五,不输出推荐(持仓过周末风险)")
        return None
    
    zt_pool = fetch_zhangting_pool()
    lhb = fetch_longhubang()
    sectors = fetch_top_sectors_stocks(top_n=5)
    
    if zt_pool.empty and lhb.empty:
        logger.error("❌ 涨停股池和龙虎榜都为空,扫描失败")
        return None
    
    if len(zt_pool) < SCAN_CONFIG['min_zhangting_for_normal']:
        logger.warning(
            f"⚠️ 今日涨停股仅 {len(zt_pool)} 只,市场偏冷"
        )
    
    candidates = merge_candidates(zt_pool, lhb, sectors)
    if candidates.empty:
        logger.error("❌ 融合后候选池为空")
        return None
    
    candidates = apply_hard_filters(candidates)
    if candidates.empty:
        logger.warning("⚠️ 硬过滤后无候选")
        return []
    
    final_candidates = rank_and_select_top(candidates)
    result = final_candidates.to_dict(orient='records')
    
    logger.info(f"✅ 扫描完成,最终候选 {len(result)} 只")
    return result


def save_candidates(candidates: List[Dict]):
    """保存候选股"""
    output = {
        'generated_at': datetime.now().isoformat(),
        'count': len(candidates),
        'candidates': candidates,
    }
    
    with open(CANDIDATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    
    logger.info(f"💾 候选股已保存到 {CANDIDATE_FILE}")


def main():
    """入口"""
    try:
        candidates = run_scan()
        
        if candidates is None:
            logger.info("ℹ️ 今日不输出候选")
            sys.exit(0)
        
        if not candidates:
            save_candidates([])
            sys.exit(0)
        
        save_candidates(candidates)
        sys.exit(0)
        
    except KeyboardInterrupt:
        logger.info("\n用户中断")
        sys.exit(130)
    except Exception as e:
        logger.exception(f"❌ 严重错误: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()