"""
pytest 共享 fixtures — 提供测试用的合成行情数据和回测引擎。
"""

import sys
import os

import numpy as np
import pandas as pd
import pytest

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest import BacktestResult, FundBacktest


@pytest.fixture
def sample_df() -> pd.DataFrame:
    """
    生成 1000 个交易日的合成净值数据（含上涨和下跌周期）。
    列：日期、单位净值、累计净值
    """
    np.random.seed(42)
    n = 1000
    dates = pd.date_range(start="2020-01-01", periods=n, freq="B")

    # 构造一个有趋势 + 波动的价格序列：前 500 天上涨，后 500 天下跌
    trend_up = np.linspace(1.0, 2.0, 500)
    trend_down = np.linspace(2.0, 1.2, 500)
    trend = np.concatenate([trend_up, trend_down])
    noise = np.random.normal(0, 0.02, n).cumsum() * 0.1
    unit_nav = trend + noise
    unit_nav = np.maximum(unit_nav, 0.5)

    # 累计净值：在单位净值基础上加累计分红
    acc_nav = unit_nav * (1 + np.arange(n) * 0.0001)

    df = pd.DataFrame(
        {
            "日期": dates,
            "单位净值": unit_nav,
            "累计净值": acc_nav,
        }
    )
    return df


@pytest.fixture
def bt(sample_df: pd.DataFrame) -> FundBacktest:
    """使用合成数据创建 FundBacktest 实例。"""
    return FundBacktest(sample_df, invest_amount=1000, invest_day=1, fee_rate=0.0015)


@pytest.fixture
def bt_no_fee(sample_df: pd.DataFrame) -> FundBacktest:
    """零费率的 FundBacktest（用于份额精确验证）。"""
    return FundBacktest(sample_df, invest_amount=1000, invest_day=1, fee_rate=0.0)


@pytest.fixture
def bt_risky(sample_df: pd.DataFrame) -> FundBacktest:
    """高无风险利率的 FundBacktest。"""
    return FundBacktest(sample_df, invest_amount=1000, invest_day=15, risk_free_rate=0.05)
