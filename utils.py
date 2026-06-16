"""
公共工具模块
提供跨模块共享的辅助函数：HTTP 请求、日期处理、结果格式化等。
"""

import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
import requests


# ================================================================
# 路径与配置
# ================================================================
def get_data_dir() -> str:
    """获取 data/ 目录的绝对路径，若不存在则自动创建。"""
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def get_output_dir() -> str:
    """获取 output/ 目录的绝对路径，若不存在则自动创建。"""
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


# ================================================================
# HTTP 请求（带重试）
# ================================================================
DEFAULT_HEADERS: Dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://fundf10.eastmoney.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def http_get_with_retry(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    max_retries: int = 3,
    retry_delay: float = 1.0,
    timeout: int = 15,
    verbose: bool = True,
) -> requests.Response:
    """
    带指数退避重试机制的 HTTP GET 请求。

    参数
    ----
    url : str
        请求 URL
    headers : dict or None
        请求头，默认使用基金数据爬取通用头
    max_retries : int
        最大重试次数
    retry_delay : float
        基础重试延迟（秒），实际延迟 = delay × (attempt + 1)
    timeout : int
        请求超时（秒）
    verbose : bool
        是否打印重试信息

    返回
    ----
    requests.Response

    异常
    ----
    requests.RequestException : 所有重试均失败时抛出
    """
    if headers is None:
        headers = DEFAULT_HEADERS

    last_exception: Optional[requests.RequestException] = None
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            last_exception = e
            if attempt < max_retries - 1:
                delay = retry_delay * (attempt + 1)
                if verbose:
                    print(
                        f"  [Retry {attempt + 1}/{max_retries}] {url[:80]}... (wait {delay:.0f}s)"
                    )
                time.sleep(delay)
    assert last_exception is not None
    raise last_exception


# ================================================================
# 日期工具
# ================================================================
def parse_date_range(
    start_date: Union[str, datetime],
    end_date: Optional[Union[str, datetime]] = None,
) -> Tuple[pd.Timestamp, pd.Timestamp]:
    """
    标准化日期范围为 pd.Timestamp。

    参数
    ----
    start_date : str or datetime
        开始日期
    end_date : str, datetime or None
        结束日期，None 表示今天

    返回
    ----
    (pd.Timestamp, pd.Timestamp)
    """
    start_ts = pd.Timestamp(start_date)
    if end_date is None:
        end_ts = pd.Timestamp.now()
    else:
        end_ts = pd.Timestamp(end_date)
    return start_ts, end_ts


def format_date_ymd(ts: pd.Timestamp) -> str:
    """Timestamp → 'YYYY-MM-DD' 字符串。"""
    return ts.strftime("%Y-%m-%d")


# ================================================================
# 回测结果打印
# ================================================================
def print_backtest_result(result, name: str) -> None:
    """
    格式化打印单个回测策略结果到控制台。

    参数
    ----
    result : BacktestResult
        回测结果对象（需有 total_invest, total_asset, sharpe_ratio 等属性）
    name : str
        策略显示名称
    """
    print(f"\n{'─' * 50}")
    print(f"  [{name}]")
    print(f"{'─' * 50}")
    print(f"  Total Invested:  {result.total_invest:>12,.2f} yuan")
    print(f"  Final Asset:     {result.total_asset:>12,.2f} yuan")
    print(f"  Total Profit:    {result.total_profit:>12,.2f} yuan")
    print(f"  Total Return:    {result.total_return:>+12.2%}")
    print(f"  Annual Return:   {result.annual_return:>+12.2%}")
    print(f"  Max Drawdown:    {result.max_drawdown:>12.2%}")
    print(f"  Sharpe Ratio:    {result.sharpe_ratio:>12.4f}")
    print(f"  Volatility:      {result.volatility:>12.2%}")
    print(f"  Win Rate:        {result.win_rate:>12.1%}")
    print(f"  Max Loss Months: {result.max_loss_months:>12}")
    print(f"  Total Trades:    {len(result.trades):>12}")


# ================================================================
# 指标排序映射
# ================================================================
SORT_COLUMN_MAP: Dict[str, str] = {
    "sharpe_ratio": "夏普比率",
    "annual_return": "年化收益率",
    "total_return": "总收益率",
    "max_drawdown": "最大回撤",
    "volatility": "波动率",
    "win_rate": "胜率",
    "total_profit": "总收益(元)",
}
"""sort_by 参数 → DataFrame 列名的映射表。"""

SORT_ASCENDING_KEYS: frozenset = frozenset({"max_drawdown", "max_loss_months", "volatility"})
"""需要升序排列的指标（越小越好）。"""


def get_sort_column(sort_by: str) -> Tuple[str, bool]:
    """
    将 sort_by 参数映射为 (DataFrame列名, 是否升序)。

    参数
    ----
    sort_by : str
        排序指标键名

    返回
    ----
    (列名, ascending)
    """
    col = SORT_COLUMN_MAP.get(sort_by, "夏普比率")
    ascending = sort_by in SORT_ASCENDING_KEYS
    return col, ascending


# ================================================================
# 数值安全处理
# ================================================================
def safe_float_series(series: pd.Series, default: float = 0.0) -> pd.Series:
    """将 Series 安全转换为 float，NaN 填充为 default。"""
    return pd.to_numeric(series, errors="coerce").fillna(default)


def safe_divide(a: float, b: float, default: float = 0.0) -> float:
    """安全除法：b 为 0 时返回 default。"""
    return a / b if b != 0 else default


# ================================================================
# 最大连续亏损月数（向量化）
# ================================================================
def compute_max_consecutive_losses(monthly_returns: pd.Series) -> int:
    """
    向量化计算最大连续亏损月数。

    参数
    ----
    monthly_returns : pd.Series
        月度收益率序列（可含 NaN）

    返回
    ----
    int : 最大连续亏损月数
    """
    valid = monthly_returns.dropna()
    if len(valid) == 0:
        return 0
    loss_streak: pd.Series = (valid < 0).astype(int)
    streak_groups = (loss_streak.diff() != 0).cumsum()
    loss_lengths = loss_streak.groupby(streak_groups).cumsum()
    max_len: int = int(loss_lengths.max()) if len(loss_lengths) > 0 else 0
    return max_len


# ================================================================
# 年化收益率计算
# ================================================================
def compute_annual_return(
    total_asset: float,
    total_invest: float,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> float:
    """
    计算年化收益率：CAGR = (final / initial)^{1/years} - 1。

    参数
    ----
    total_asset : float
        最终资产
    total_invest : float
        总投入
    start_date : pd.Timestamp
        回测起始日期
    end_date : pd.Timestamp
        回测结束日期

    返回
    ----
    float : 年化收益率（小数形式）
    """
    years = (end_date - start_date).days / 365.25
    if years <= 0 or total_invest <= 0:
        return 0.0
    return float((total_asset / total_invest) ** (1.0 / years) - 1.0)


# ================================================================
# 最大回撤（向量化）
# ================================================================
def compute_max_drawdown(asset_series: pd.Series) -> float:
    """
    向量化计算最大回撤。

    参数
    ----
    asset_series : pd.Series
        资产序列（非负）

    返回
    ----
    float : 最大回撤（负小数，如 -0.15 表示 -15%）
    """
    valid = asset_series.dropna()
    if len(valid) == 0 or valid.max() <= 0:
        return 0.0
    cummax = valid.cummax()
    drawdowns = (valid - cummax) / cummax
    return float(drawdowns.min())


# ================================================================
# 年化波动率
# ================================================================
def compute_annual_volatility(daily_returns: pd.Series, trading_days: int = 252) -> float:
    """
    计算年化波动率。

    参数
    ----
    daily_returns : pd.Series
        日收益率序列
    trading_days : int
        年交易日数

    返回
    ----
    float : 年化波动率
    """
    valid = daily_returns.dropna()
    if len(valid) < 2:
        return 0.0
    return float(valid.std() * np.sqrt(trading_days))


# ================================================================
# 夏普比率
# ================================================================
def compute_sharpe_ratio(
    annual_return: float,
    annual_volatility: float,
    risk_free_rate: float = 0.03,
) -> float:
    """
    计算夏普比率。

    参数
    ----
    annual_return : float
        年化收益率
    annual_volatility : float
        年化波动率
    risk_free_rate : float
        无风险利率

    返回
    ----
    float : 夏普比率
    """
    if annual_volatility <= 0:
        return 0.0
    return (annual_return - risk_free_rate) / annual_volatility
