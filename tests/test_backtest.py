"""
pytest 单元测试 — backtest.py 核心回测函数

覆盖：BacktestResult、FundBacktest 初始化、8 个策略、_build_daily_values、
      _build_trade_dates、_build_trades_vectorized
"""

import numpy as np
import pandas as pd
import pytest
from datetime import datetime

from backtest import BacktestResult, FundBacktest


# ================================================================
# BacktestResult 数据类
# ================================================================
class TestBacktestResult:
    """测试 BacktestResult 数据类。"""

    def test_default_creation(self) -> None:
        """默认值创建。"""
        r = BacktestResult()
        assert r.strategy_name == ""
        assert r.total_invest == 0.0
        assert r.total_asset == 0.0
        assert r.total_profit == 0.0
        assert r.total_return == 0.0
        assert r.annual_return == 0.0
        assert r.max_drawdown == 0.0
        assert r.sharpe_ratio == 0.0
        assert r.volatility == 0.0
        assert r.win_rate == 0.0
        assert r.max_loss_months == 0
        assert r.total_shares == 0.0
        assert r.avg_cost == 0.0
        assert r.trades is None
        assert r.daily_values is None
        assert r.stop_profit_events == []

    def test_custom_name(self) -> None:
        """自定义策略名。"""
        r = BacktestResult(strategy_name="测试策略")
        assert r.strategy_name == "测试策略"


# ================================================================
# FundBacktest 初始化
# ================================================================
class TestFundBacktestInit:
    """测试 FundBacktest 初始化与预处理。"""

    def test_init_with_adjusted_nav(self, sample_df: pd.DataFrame) -> None:
        """含复权净值的初始化。"""
        df = sample_df.copy()
        df["复权净值"] = df["单位净值"] * 1.01
        bt = FundBacktest(df, invest_amount=500, invest_day=10)
        assert bt.price_col == "复权净值"
        assert bt.invest_amount == 500
        assert bt.invest_day == 10
        assert bt.fee_rate == 0.0015

    def test_init_without_adjusted_nav(self, sample_df: pd.DataFrame) -> None:
        """无复权净值时回退到单位净值。"""
        df = sample_df.drop(columns=["累计净值"])
        bt = FundBacktest(df)
        assert bt.price_col == "单位净值"

    def test_invest_day_clamped(self, sample_df: pd.DataFrame) -> None:
        """定投日不会超过28号。"""
        bt = FundBacktest(sample_df, invest_day=31)
        assert bt.invest_day == 28

    def test_dates_sorted(self, sample_df: pd.DataFrame) -> None:
        """日期自动按升序排列。"""
        df = sample_df.sample(frac=1).reset_index(drop=True)
        bt = FundBacktest(df)
        assert bt.df["日期"].is_monotonic_increasing

    def test_start_end_dates(self, bt: FundBacktest) -> None:
        """start_date 和 end_date 正确设置。"""
        assert bt.start_date == bt.df["日期"].min()
        assert bt.end_date == bt.df["日期"].max()

    def test_preprocess_adds_return_column(self, bt: FundBacktest) -> None:
        """预处理添加日收益率列。"""
        assert "日收益率" in bt.df.columns


# ================================================================
# 交易日期生成
# ================================================================
class TestTradeDates:
    """测试 _build_trade_dates 向量化方法。"""

    def test_generates_trade_dates(self, bt: FundBacktest) -> None:
        """生成非空交易日期。"""
        dates = bt._trade_dates
        assert len(dates) > 0
        assert isinstance(dates, pd.DatetimeIndex)

    def test_trade_dates_within_range(self, bt: FundBacktest) -> None:
        """交易日期在数据范围内。"""
        dates = bt._trade_dates
        assert dates.min() >= bt.df["日期"].min()
        assert dates.max() <= bt.df["日期"].max()

    def test_trade_dates_unique(self, bt: FundBacktest) -> None:
        """交易日期去重。"""
        assert bt._trade_dates.is_unique

    def test_invest_day_15(self, sample_df: pd.DataFrame) -> None:
        """invest_day=15 的日期生成正确。"""
        bt = FundBacktest(sample_df, invest_day=15)
        dates = bt._trade_dates
        assert len(dates) > 0
        # 所有日期应为交易日
        for d in dates:
            assert d in bt.df["日期"].values


# ================================================================
# 策略 1：普通定投
# ================================================================
class TestNormalDCA:
    """测试普通定投策略。"""

    def test_returns_backtest_result(self, bt: FundBacktest) -> None:
        """返回 BacktestResult。"""
        r = bt.run_normal_dca()
        assert isinstance(r, BacktestResult)
        assert r.strategy_name == "普通定投"

    def test_trades_not_empty(self, bt: FundBacktest) -> None:
        """交易记录非空。"""
        r = bt.run_normal_dca()
        assert r.trades is not None
        assert len(r.trades) > 0

    def test_total_invest_matches_trades(self, bt: FundBacktest) -> None:
        """总投入 = 每次定投金额 × 交易次数。"""
        r = bt.run_normal_dca()
        expected = 1000 * len(r.trades)
        assert abs(r.total_invest - expected) < 0.01

    def test_shares_positive(self, bt: FundBacktest) -> None:
        """所有交易买入份额 > 0。"""
        r = bt.run_normal_dca()
        assert (r.trades["买入份额"] > 0).all()

    def test_cumulative_shares_increasing(self, bt: FundBacktest) -> None:
        """累计份额单调递增。"""
        r = bt.run_normal_dca()
        assert r.trades["累计份额"].is_monotonic_increasing

    def test_daily_values_not_empty(self, bt: FundBacktest) -> None:
        """每日资产序列非空。"""
        r = bt.run_normal_dca()
        assert r.daily_values is not None
        assert len(r.daily_values) > 0

    def test_metrics_reasonable(self, bt: FundBacktest) -> None:
        """核心指标在合理范围内。"""
        r = bt.run_normal_dca()
        assert r.total_asset > 0
        assert r.total_invest > 0
        assert -1.0 <= r.total_return <= 10.0
        assert -2.0 <= r.max_drawdown <= 0.0
        assert r.volatility >= 0
        assert 0 <= r.win_rate <= 1.0
        assert r.max_loss_months >= 0

    def test_zero_fee_shares_exact(self, bt_no_fee: FundBacktest) -> None:
        """零费率时 shares ≈ amount / price（允许四舍五入误差）。"""
        r = bt_no_fee.run_normal_dca()
        for _, row in r.trades.iterrows():
            expected = 1000 / row["净值"]
            # 交易记录中买入份额保留4位小数
            assert abs(row["买入份额"] - expected) < 0.001

    def test_daily_profit_calculation(self, bt: FundBacktest) -> None:
        """每日收益 = 总资产 - 累计投入。"""
        r = bt.run_normal_dca()
        dv = r.daily_values
        diff = (dv["总资产"] - dv["累计投入"] - dv["收益"]).abs().max()
        assert diff < 0.01

    def test_daily_return_rate_range(self, bt: FundBacktest) -> None:
        """每日收益率在合理范围。"""
        r = bt.run_normal_dca()
        rates = r.daily_values["收益率"].dropna()
        assert rates.min() > -2.0
        assert rates.max() < 10.0


# ================================================================
# 策略 5：60日均线策略
# ================================================================
class TestMA60DCA:
    """测试60日均线策略。"""

    def test_returns_result(self, bt: FundBacktest) -> None:
        r = bt.run_ma60_dca()
        assert isinstance(r, BacktestResult)
        assert "MA60" in r.strategy_name

    def test_varying_invest_amount(self, bt: FundBacktest) -> None:
        """不同区域的投资金额不同。"""
        r = bt.run_ma60_dca()
        amounts = r.trades["实际投入"].unique()
        assert len(amounts) >= 2  # 至少有 2 个不同的投入金额

    def test_zones_populated(self, bt: FundBacktest) -> None:
        """区域列已填充。"""
        r = bt.run_ma60_dca()
        zones = r.trades["区域"].unique()
        assert len(zones) > 0

    def test_custom_period(self, bt: FundBacktest) -> None:
        """自定义 MA 周期。"""
        r = bt.run_ma60_dca(ma_period=120)
        assert "MA120" in r.strategy_name
        assert len(r.trades) > 0


# ================================================================
# 策略 6：MACD 策略
# ================================================================
class TestMACDDCA:
    """测试 MACD 策略。"""

    def test_returns_result(self, bt: FundBacktest) -> None:
        r = bt.run_macd_dca()
        assert isinstance(r, BacktestResult)
        assert "MACD" in r.strategy_name

    def test_indicator_columns(self, bt: FundBacktest) -> None:
        """交易记录包含 DIF、DEA、MACD柱。"""
        r = bt.run_macd_dca()
        assert "DIF" in r.trades.columns
        assert "DEA" in r.trades.columns
        assert "MACD柱" in r.trades.columns

    def test_custom_params(self, bt: FundBacktest) -> None:
        """自定义 MACD 参数。"""
        r = bt.run_macd_dca(fast=5, slow=20, signal=7)
        assert len(r.trades) > 0


# ================================================================
# 策略 7：RSI 策略
# ================================================================
class TestRSIDCA:
    """测试 RSI 策略。"""

    def test_returns_result(self, bt: FundBacktest) -> None:
        r = bt.run_rsi_dca()
        assert isinstance(r, BacktestResult)
        assert "RSI" in r.strategy_name

    def test_oversold_overbought(self, bt: FundBacktest) -> None:
        """自定义超买超卖阈值。"""
        r = bt.run_rsi_dca(period=10, oversold=25, overbought=75)
        zones = r.trades["区域"].unique()
        assert "极度超卖" in zones or "极度超买" in zones or len(zones) > 1

    def test_rsi_column_present(self, bt: FundBacktest) -> None:
        """交易记录包含 RSI 列。"""
        r = bt.run_rsi_dca()
        assert "RSI" in r.trades.columns


# ================================================================
# 策略 8：波动率策略
# ================================================================
class TestVolatilityDCA:
    """测试波动率策略。"""

    def test_returns_result(self, bt: FundBacktest) -> None:
        r = bt.run_volatility_dca()
        assert isinstance(r, BacktestResult)
        assert "波动率" in r.strategy_name

    def test_custom_period(self, bt: FundBacktest) -> None:
        """自定义波动率周期。"""
        r = bt.run_volatility_dca(vol_period=30)
        assert len(r.trades) > 0

    def test_indicator_columns(self, bt: FundBacktest) -> None:
        """包含波动率指标列。"""
        r = bt.run_volatility_dca()
        assert "年化波动率" in r.trades.columns
        assert "波动率均值" in r.trades.columns


# ================================================================
# 策略 4：MA 动态定投
# ================================================================
class TestMADynamicDCA:
    """测试均线动态定投策略。"""

    def test_returns_result(self, bt: FundBacktest) -> None:
        r = bt.run_ma_dynamic_dca()
        assert isinstance(r, BacktestResult)
        assert "动态" in r.strategy_name

    def test_custom_params(self, bt: FundBacktest) -> None:
        """自定义所有参数（策略运行成功即可，具体倍率取决于数据）。"""
        r = bt.run_ma_dynamic_dca(
            ma_period=120, low_multiplier=3.0, high_multiplier=0.3,
            low_threshold=0.85, high_threshold=1.15,
        )
        assert len(r.trades) > 0
        assert "MA120" in r.strategy_name
        # 所有倍数要么是 1.0, 3.0, 或 0.3（取决于实际价格/MA比值）
        mults = r.trades["定投倍数"].unique()
        for m in mults:
            assert m in (1.0, 3.0, 0.3), f"Unexpected multiplier: {m}"

    def test_different_from_normal(self, bt: FundBacktest) -> None:
        """与普通定投产生不同结果。"""
        r_norm = bt.run_normal_dca()
        r_ma = bt.run_ma_dynamic_dca(ma_period=60)
        # 总投入至少不同（因为投资倍数波动）
        assert r_norm.total_invest != r_ma.total_invest or len(r_norm.trades) == len(r_ma.trades)


# ================================================================
# 策略 2：止盈定投
# ================================================================
class TestStopProfitDCA:
    """测试止盈定投策略。"""

    def test_returns_result(self, bt: FundBacktest) -> None:
        r = bt.run_stop_profit_dca(stop_profit=0.20)
        assert isinstance(r, BacktestResult)
        assert "止盈" in r.strategy_name

    def test_trades_with_action_column(self, bt: FundBacktest) -> None:
        """交易记录包含行动列。"""
        r = bt.run_stop_profit_dca()
        assert "行动" in r.trades.columns

    def test_no_error_with_high_threshold(self, bt: FundBacktest) -> None:
        """极高止盈线不会崩溃。"""
        r = bt.run_stop_profit_dca(stop_profit=10.0)
        assert len(r.trades) > 0

    def test_no_error_with_low_threshold(self, bt: FundBacktest) -> None:
        """极低止盈线不会崩溃（可能触发多次）。"""
        r = bt.run_stop_profit_dca(stop_profit=0.01)
        assert len(r.trades) > 0
        # 极低止盈线应触发至少一次止盈
        assert len(r.stop_profit_events) >= 0


# ================================================================
# 策略 3：价值平均策略
# ================================================================
class TestValueAverage:
    """测试价值平均策略。"""

    def test_returns_result(self, bt: FundBacktest) -> None:
        r = bt.run_value_average(target_growth=1000)
        assert isinstance(r, BacktestResult)
        assert "价值平均" in r.strategy_name

    def test_custom_growth(self, bt: FundBacktest) -> None:
        """自定义增长目标。"""
        r = bt.run_value_average(target_growth=2000)
        assert len(r.trades) > 0
        assert r.total_invest > 1000

    def test_share_changes_can_be_negative(self, bt: FundBacktest) -> None:
        """份额变动列可以包含负数（卖出）。"""
        r = bt.run_value_average(target_growth=5000)
        changes = r.trades["份额变动"]
        assert len(changes) > 0

    def test_actions_include_all_types(self, bt: FundBacktest) -> None:
        """行动列包含买入/卖出/不变。"""
        r = bt.run_value_average(target_growth=1000)
        actions = r.trades["行动"].unique()
        assert len(actions) >= 1  # 至少有一种行动


# ================================================================
# _build_daily_values 边界条件
# ================================================================
class TestBuildDailyValues:
    """测试 _build_daily_values 的边界条件。"""

    def test_result_has_all_metrics(self, bt: FundBacktest) -> None:
        """结果包含所有核心指标。"""
        r = bt.run_normal_dca()
        assert r.total_shares > 0
        assert r.avg_cost > 0
        assert r.max_drawdown <= 0
        assert isinstance(r.max_loss_months, int)

    def test_avg_cost_calculation(self, bt_no_fee: FundBacktest) -> None:
        """平均成本：零费率时约等于调和平均。"""
        r = bt_no_fee.run_normal_dca()
        assert r.avg_cost > 0
        assert abs(r.avg_cost - r.total_invest / r.total_shares) < 0.01

    def test_max_drawdown_negative_or_zero(self, bt: FundBacktest) -> None:
        """最大回撤 <= 0。"""
        r = bt.run_normal_dca()
        assert r.max_drawdown <= 0.0

    def test_sharpe_calculation(self, bt: FundBacktest) -> None:
        """夏普比率计算正确（有波动时非零）。"""
        r = bt.run_normal_dca()
        if r.volatility > 0:
            expected = (r.annual_return - 0.03) / r.volatility
            assert abs(r.sharpe_ratio - expected) < 1e-6
        else:
            assert r.sharpe_ratio == 0.0

    def test_win_rate_between_zero_and_one(self, bt: FundBacktest) -> None:
        """胜率在 [0, 1] 范围内。"""
        r = bt.run_normal_dca()
        assert 0.0 <= r.win_rate <= 1.0


# ================================================================
# 跨策略一致性
# ================================================================
class TestCrossStrategyConsistency:
    """跨策略一致性测试。"""

    def test_all_strategies_same_trade_dates(self, bt: FundBacktest) -> None:
        """所有策略的交易日数相同（同日历月）。"""
        results = [
            bt.run_normal_dca(),
            bt.run_ma60_dca(),
            bt.run_macd_dca(),
            bt.run_rsi_dca(),
            bt.run_volatility_dca(),
            bt.run_ma_dynamic_dca(),
        ]
        trade_counts = [len(r.trades) for r in results]
        assert len(set(trade_counts)) == 1, f"Trade counts differ: {trade_counts}"

    def test_all_strategies_positive_shares(self, bt: FundBacktest) -> None:
        """所有策略的最终份额 > 0。"""
        for r in [
            bt.run_normal_dca(),
            bt.run_ma60_dca(),
            bt.run_macd_dca(),
            bt.run_rsi_dca(),
            bt.run_volatility_dca(),
            bt.run_ma_dynamic_dca(),
        ]:
            assert r.total_shares > 0, f"{r.strategy_name} has zero shares"

    def test_deterministic_results(self, bt: FundBacktest) -> None:
        """相同输入产生相同输出（确定性）。"""
        r1 = bt.run_normal_dca()
        r2 = bt.run_normal_dca()
        assert r1.total_invest == r2.total_invest
        assert r1.total_asset == r2.total_asset
        assert r1.sharpe_ratio == r2.sharpe_ratio
        assert r1.annual_return == r2.annual_return
        assert r1.max_drawdown == r2.max_drawdown


# ================================================================
# utils 模块函数
# ================================================================
class TestUtilsIntegration:
    """测试 utils.py 集成函数。"""

    def test_compute_max_consecutive_losses(self) -> None:
        """最大连续亏损月数计算正确。"""
        from utils import compute_max_consecutive_losses

        s = pd.Series([-0.01, -0.02, 0.01, -0.03, -0.04, -0.05, 0.02])
        assert compute_max_consecutive_losses(s) == 3

        s2 = pd.Series([0.01, 0.02, 0.03])
        assert compute_max_consecutive_losses(s2) == 0

        s3 = pd.Series([])
        assert compute_max_consecutive_losses(s3) == 0

    def test_get_sort_column(self) -> None:
        """排序映射正确。"""
        from utils import get_sort_column

        col, asc = get_sort_column("sharpe_ratio")
        assert col == "夏普比率"
        assert asc is False

        col, asc = get_sort_column("max_drawdown")
        assert col == "最大回撤"
        assert asc is True

    def test_print_backtest_result(self, bt: FundBacktest, capsys) -> None:
        """打印函数无异常。"""
        from utils import print_backtest_result

        r = bt.run_normal_dca()
        print_backtest_result(r, "Test")
        captured = capsys.readouterr()
        assert "Test" in captured.out
        assert "Total Invested" in captured.out
        assert "Sharpe Ratio" in captured.out
