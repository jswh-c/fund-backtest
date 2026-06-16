"""
基金定投回测框架
支持多种定投策略的回测，计算收益、风险指标
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from utils import compute_max_consecutive_losses, get_sort_column


@dataclass
class BacktestResult:
    """回测结果数据类"""

    strategy_name: str = ""
    trades: pd.DataFrame = None  # 交易记录
    daily_values: pd.DataFrame = None  # 每日资产变动
    total_invest: float = 0.0  # 总投入
    total_asset: float = 0.0  # 最终总资产
    total_profit: float = 0.0  # 总收益
    total_return: float = 0.0  # 总收益率
    annual_return: float = 0.0  # 年化收益率
    max_drawdown: float = 0.0  # 最大回撤
    sharpe_ratio: float = 0.0  # 夏普比率
    volatility: float = 0.0  # 波动率
    win_rate: float = 0.0  # 胜率（盈利月数/总月数）
    max_loss_months: int = 0  # 最大连续亏损月数
    total_shares: float = 0.0  # 最终持有份额
    avg_cost: float = 0.0  # 平均成本
    stop_profit_events: List[Dict] = field(default_factory=list)  # 止盈事件


class FundBacktest:
    """
    基金定投回测引擎

    参数
    ----
    df : pd.DataFrame
        基金净值数据，必须包含：日期、单位净值、复权净值（可选）
    invest_amount : float
        每期定投金额（元）
    invest_day : int
        每月定投日（1-28），默认每月1日
    fee_rate : float
        申购费率，默认 0.15%
    risk_free_rate : float
        无风险利率（用于夏普比率），默认 3%
    """

    def __init__(
        self,
        df: pd.DataFrame,
        invest_amount: float = 1000,
        invest_day: int = 1,
        fee_rate: float = 0.0015,
        risk_free_rate: float = 0.03,
    ):
        self.df = df.copy()
        self.df["日期"] = pd.to_datetime(self.df["日期"])
        self.df = self.df.sort_values("日期").reset_index(drop=True)

        # 使用复权净值（如果存在），否则用单位净值
        if "复权净值" in self.df.columns:
            self.price_col = "复权净值"
        else:
            self.price_col = "单位净值"
            print("[WARN] No adjusted NAV found, using unit NAV (may not account for dividends)")

        self.invest_amount = invest_amount
        self.invest_day = min(invest_day, 28)  # 确保定投日在1-28之间
        self.fee_rate = fee_rate
        self.risk_free_rate = risk_free_rate

        # 预计算
        self._preprocess()

    def _preprocess(self):
        """预处理：计算收益率、构建交易日期索引"""
        df = self.df

        # 日收益率（用于风险计算）
        df["日收益率"] = df[self.price_col].pct_change()

        # 获取所有定投日期
        self.start_date = df["日期"].min()
        self.end_date = df["日期"].max()

        # ---- 预生成所有定投日期（向量化） ----
        self._trade_dates = self._build_trade_dates()

    def _build_trade_dates(self) -> pd.DatetimeIndex:
        """
        向量化生成所有定投日（每月 invest_day 或之后第一个交易日）。

        返回
        ----
        pd.DatetimeIndex : 所有定投日期
        """
        target_day = min(self.invest_day, 28)
        # 生成每月目标日期
        months = pd.date_range(
            start=self.start_date.replace(day=1),
            end=self.end_date + pd.DateOffset(months=1),
            freq="MS",
        )
        targets = pd.Index(
            [
                max(pd.Timestamp(year=d.year, month=d.month, day=min(target_day, 28)), d)
                for d in months
            ]
        )
        targets = targets[targets <= self.end_date]

        if len(targets) == 0:
            return pd.DatetimeIndex([])

        # 使用 searchsorted 向量化查找 >= target 的最近交易日
        all_dates = self.df["日期"].values
        trade_indices = np.searchsorted(all_dates, targets, side="left")
        # 确保不越界
        trade_indices = np.clip(trade_indices, 0, len(all_dates) - 1)
        trade_dates = all_dates[trade_indices]
        # 去重（同月可能落入同一交易日）
        trade_dates = pd.DatetimeIndex(np.unique(trade_dates))
        return trade_dates

    def _get_trade_data_vectorized(self, df: pd.DataFrame, extra_cols: list = None) -> pd.DataFrame:
        """
        向量化获取每个定投日的净值、指标等数据。

        参数
        ----
        df : pd.DataFrame
            包含价格列和指标列的 DataFrame（需已对齐日期）
        extra_cols : list
            需要额外提取的列名列表

        返回
        ----
        pd.DataFrame : trade_dates × columns
        """
        trade_dates = self._trade_dates
        if len(trade_dates) == 0:
            return pd.DataFrame()

        # 使用 merge 提取交易日数据（df 已包含指标列）
        base_cols = ["日期", self.price_col]
        if extra_cols:
            base_cols.extend(extra_cols)

        trade_df = df[df["日期"].isin(trade_dates)][base_cols].copy()
        trade_df = trade_df.reset_index(drop=True)
        return trade_df

    def _build_trades_vectorized(
        self,
        trade_df: pd.DataFrame,
        invest_mult_col: str = None,
        zone_col: str = None,
        indicator_cols: dict = None,
        strategy_name: str = "",
    ) -> BacktestResult:
        """
        向量化构建 trades DataFrame 并生成回测结果。

        参数
        ----
        trade_df : pd.DataFrame
            包含 日期、价格列、投资倍数列、区域列的交易日数据
        invest_mult_col : str
            投资倍数列名（None 表示固定 1x）
        zone_col : str
            区域列名（None 表示无区域划分）
        indicator_cols : dict
            {列名: 列名} 映射，需保留到 trades 的指标列
        strategy_name : str
            策略名称

        返回
        ----
        BacktestResult
        """
        if len(trade_df) == 0:
            raise ValueError("No trade dates found.")

        price_col = self.price_col
        prices = trade_df[price_col].values
        n = len(prices)

        # 投资倍数
        if invest_mult_col and invest_mult_col in trade_df.columns:
            mults = trade_df[invest_mult_col].values.astype(float)
        else:
            mults = np.ones(n)

        # 实际投资金额
        actual_invest = self.invest_amount * mults
        fee = actual_invest * self.fee_rate
        net_amount = actual_invest - fee
        shares = net_amount / prices

        # 累计
        cum_shares = np.cumsum(shares)
        cum_invest = np.cumsum(actual_invest)

        # 构建 trades
        trades_data = {
            "日期": trade_df["日期"],
            "净值": prices,
            "定投倍数": mults,
            "实际投入": np.round(actual_invest, 2),
            "申购费": np.round(fee, 2),
            "净投入": np.round(net_amount, 2),
            "买入份额": np.round(shares, 4),
            "累计份额": np.round(cum_shares, 4),
            "累计投入": np.round(cum_invest, 2),
        }

        if zone_col and zone_col in trade_df.columns:
            trades_data["区域"] = trade_df[zone_col].values

        if indicator_cols:
            for src_col, dst_col in indicator_cols.items():
                if src_col in trade_df.columns:
                    vals = trade_df[src_col].values
                    trades_data[dst_col] = np.round(vals, 4) if vals.dtype.kind == "f" else vals

        trades_df = pd.DataFrame(trades_data)
        trades_df["日期"] = pd.to_datetime(trades_df["日期"])
        cumulative_invest_list = cum_invest.tolist()
        total_shares = cum_shares[-1]

        result = self._build_daily_values(trades_df, total_shares, cumulative_invest_list)
        result.strategy_name = strategy_name
        result.trades = trades_df
        return result

    def _find_trade_date(self, year: int, month: int) -> pd.Timestamp:
        """（保留兼容）找到最近的交易日"""
        target_day = min(self.invest_day, 28)
        target_date = pd.Timestamp(year=year, month=month, day=target_day)
        if target_date > self.end_date:
            return None
        idx = np.searchsorted(self.df["日期"].values, target_date, side="left")
        if idx >= len(self.df):
            return None
        return self.df["日期"].iloc[idx]

    def _get_price_on_date(self, date: pd.Timestamp) -> float:
        """（保留兼容）获取指定日期的净值"""
        rows = self.df[self.df["日期"] == date]
        if len(rows) == 0:
            return None
        return rows[self.price_col].iloc[0]

    # ================================================================
    # 策略1：普通定投（定期定额）— 向量化
    # ================================================================
    def run_normal_dca(self) -> BacktestResult:
        """
        普通定投策略：每月固定日期买入固定金额（向量化实现）。
        """
        trade_df = self._get_trade_data_vectorized(self.df)
        if len(trade_df) == 0:
            raise ValueError("No trades generated. Check date range and data.")

        trade_df["_mult"] = 1.0
        trade_df["_zone"] = "正常定投"
        return self._build_trades_vectorized(
            trade_df,
            invest_mult_col="_mult",
            zone_col="_zone",
            strategy_name="普通定投",
        )

    # ================================================================
    # 策略2：止盈定投（半向量化优化）
    # ================================================================
    def run_stop_profit_dca(self, stop_profit: float = 0.20) -> BacktestResult:
        """
        止盈定投策略（使用预计算交易日期优化）。
        """
        trade_dates = self._trade_dates
        if len(trade_dates) == 0:
            raise ValueError("No trades generated.")

        # 向量化获取所有交易日的价格
        df_set = self.df.set_index("日期")
        valid_dates = [d for d in trade_dates if d in df_set.index]
        prices = df_set.loc[valid_dates, self.price_col].values

        trades = []
        stop_events = []
        total_shares = 0.0
        total_invest = 0.0
        total_redeemed = 0.0
        current_cash = 0.0
        cumulative_invest_list = []
        cycle_total_invest = 0.0

        fee_per = self.invest_amount * self.fee_rate
        net_per = self.invest_amount - fee_per

        for i, (d, price) in enumerate(zip(valid_dates, prices)):
            if price <= 0:
                continue

            shares = net_per / price
            total_shares += shares
            total_invest += self.invest_amount
            cycle_total_invest += self.invest_amount

            current_asset = total_shares * price
            current_return = (
                (current_asset - cycle_total_invest) / cycle_total_invest
                if cycle_total_invest > 0
                else 0
            )

            action = "买入"
            if current_return >= stop_profit:
                action = "止盈赎回"
                stop_events.append(
                    {
                        "日期": d,
                        "净值": price,
                        "累计投入": round(cycle_total_invest, 2),
                        "赎回资产": round(current_asset, 2),
                        "收益": round(current_asset - cycle_total_invest, 2),
                        "收益率": round(current_return, 4),
                    }
                )
                total_redeemed += current_asset
                current_cash += current_asset
                total_shares = 0.0
                cycle_total_invest = 0.0

            trades.append(
                {
                    "日期": d,
                    "净值": price,
                    "投入金额": self.invest_amount,
                    "申购费": round(fee_per, 2),
                    "净投入": round(net_per, 2),
                    "买入份额": round(shares, 4),
                    "累计份额": round(total_shares, 4),
                    "累计投入": round(total_invest, 2),
                    "当前资产": round(current_asset, 2),
                    "当前收益率": round(current_return, 4),
                    "行动": action,
                }
            )
            if action == "止盈赎回":
                trades[-1]["赎回金额"] = round(current_asset, 2)

            cumulative_invest_list.append(total_invest)

        if not trades:
            raise ValueError("No trades generated. Check date range and data.")

        trades_df = pd.DataFrame(trades)

        # 最终资产 = 持有份额市值 + 现金
        final_price = self.df[self.price_col].iloc[-1]
        final_asset = total_shares * final_price + current_cash

        result = self._build_daily_values(trades_df, total_shares, cumulative_invest_list)
        result.strategy_name = f"止盈定投({stop_profit:.0%})"
        result.trades = trades_df
        result.stop_profit_events = stop_events
        result.total_asset = final_asset
        result.total_profit = result.total_asset - result.total_invest
        result.total_return = (
            result.total_profit / result.total_invest if result.total_invest > 0 else 0
        )
        return result

    # ================================================================
    # 策略3：价值平均策略（半向量化优化）
    # ================================================================
    def run_value_average(self, target_growth: float = 1000) -> BacktestResult:
        """
        价值平均策略：
        - 设定每月市值增长目标
        - 第1月目标市值 = target_growth
        - 第2月目标市值 = 2 * target_growth
        - 第N月目标市值 = N * target_growth
        - 如果当前市值 < 目标市值 → 买入差额
        - 如果当前市值 > 目标市值 → 卖出超额部分

        参数
        ----
        target_growth : float
            每月市值增长目标（元）
        """
        trade_dates = self._trade_dates
        if len(trade_dates) == 0:
            raise ValueError("No trades generated.")

        df_set = self.df.set_index("日期")
        valid_dates = [d for d in trade_dates if d in df_set.index]
        prices = df_set.loc[valid_dates, self.price_col].values

        trades = []
        total_shares = 0.0
        total_invest = 0.0
        total_redeemed = 0.0

        for month_count, (d, price) in enumerate(zip(valid_dates, prices), start=1):
            if price <= 0:
                continue

            target_value = month_count * target_growth
            current_value = total_shares * price
            gap = target_value - current_value

            if gap > 0:
                fee = gap * self.fee_rate
                shares_change = (gap - fee) / price
                action = "买入"
                total_invest += gap
            elif gap < 0:
                sell_amount = abs(gap)
                shares_change = -sell_amount / price
                action = "卖出"
                total_redeemed += sell_amount
            else:
                shares_change = 0
                action = "不变"

            total_shares += shares_change

            trades.append(
                {
                    "日期": d,
                    "净值": price,
                    "目标市值": round(target_value, 2),
                    "当前市值": round(current_value, 2),
                    "差额": round(gap, 2),
                    "操作金额": round(abs(gap) if gap != 0 else 0, 2),
                    "份额变动": round(shares_change, 4),
                    "累计份额": round(total_shares, 4),
                    "累计投入": round(total_invest, 2),
                    "累计赎回": round(total_redeemed, 2),
                    "当前资产": round(total_shares * price, 2),
                    "行动": action,
                }
            )

        if not trades:
            raise ValueError("No trades generated. Check date range and data.")

        trades_df = pd.DataFrame(trades)

        # 累计投入列表
        cumulative_invest_list = [total_invest] * len(trades_df)

        result = self._build_daily_values(trades_df, total_shares, cumulative_invest_list)
        result.strategy_name = f"价值平均(+{target_growth:.0f} p.m.)"
        result.trades = trades_df
        # 价值平均策略可以卖出，净投入 = total_invest - total_redeemed
        result.total_invest = max(total_invest, total_redeemed)
        result.total_profit = result.total_asset - (total_invest - total_redeemed)
        result.total_return = (
            result.total_profit / (total_invest - total_redeemed)
            if (total_invest - total_redeemed) > 0
            else 0
        )
        return result

    # ================================================================
    # 策略4：均线动态定投（AI优化）— 向量化
    # ================================================================
    def run_ma_dynamic_dca(
        self,
        ma_period: int = 250,
        low_multiplier: float = 2.0,
        high_multiplier: float = 0.5,
        low_threshold: float = 0.9,
        high_threshold: float = 1.1,
    ) -> BacktestResult:
        """
        基于均线的动态定投策略（向量化实现）。
        """
        df = self.df.copy()
        ma_col = f"MA{ma_period}"
        df[ma_col] = df[self.price_col].rolling(window=ma_period).mean()
        df["_ratio"] = df[self.price_col] / df[ma_col]

        extra = [ma_col, "_ratio"]
        trade_df = self._get_trade_data_vectorized(df, extra_cols=extra)
        if len(trade_df) == 0:
            raise ValueError("No trades generated. Check date range and data.")

        ratio = trade_df["_ratio"].values
        ma_vals = trade_df[ma_col].values

        # 向量化信号
        mults = np.where(
            np.isnan(ratio),
            1.0,
            np.where(
                ratio < low_threshold,
                low_multiplier,
                np.where(ratio >= high_threshold, high_multiplier, 1.0),
            ),
        )
        zones = np.where(
            np.isnan(ratio),
            "均线未形成",
            np.where(
                ratio < low_threshold,
                "低位加仓",
                np.where(ratio >= high_threshold, "高位减仓", "正常定投"),
            ),
        )

        trade_df["_mult"] = mults
        trade_df["_zone"] = zones

        return self._build_trades_vectorized(
            trade_df,
            invest_mult_col="_mult",
            zone_col="_zone",
            indicator_cols={ma_col: ma_col, "_ratio": "均线比值"},
            strategy_name=f"MA{ma_period}动态定投",
        )

    # ================================================================
    # 策略5：60日均线策略 — 向量化
    # ================================================================
    def run_ma60_dca(self, ma_period: int = 60) -> BacktestResult:
        """
        60日均线定投策略（向量化实现）。
        """
        df = self.df.copy()
        ma_col = f"MA{ma_period}"
        df[ma_col] = df[self.price_col].rolling(window=ma_period).mean()
        df["_ratio"] = df[self.price_col] / df[ma_col]

        extra = [ma_col, "_ratio"]
        trade_df = self._get_trade_data_vectorized(df, extra_cols=extra)
        if len(trade_df) == 0:
            raise ValueError("No trades generated. Check date range and data.")

        ratio = trade_df["_ratio"].values

        mults = np.where(
            np.isnan(ratio), 1.0, np.where(ratio < 0.95, 2.0, np.where(ratio > 1.05, 0.5, 1.0))
        )
        zones = np.where(
            np.isnan(ratio),
            "均线未形成",
            np.where(ratio < 0.95, "低位加仓", np.where(ratio > 1.05, "高位减仓", "正常定投")),
        )

        trade_df["_mult"] = mults
        trade_df["_zone"] = zones

        return self._build_trades_vectorized(
            trade_df,
            invest_mult_col="_mult",
            zone_col="_zone",
            indicator_cols={ma_col: ma_col, "_ratio": "均线比值"},
            strategy_name=f"MA{ma_period}均线定投",
        )

    # ================================================================
    # 策略6：MACD策略 — 向量化
    # ================================================================
    def run_macd_dca(
        self,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ) -> BacktestResult:
        """
        MACD指标定投策略（向量化实现）。
        """
        df = self.df.copy()
        df["EMA_fast"] = df[self.price_col].ewm(span=fast, adjust=False).mean()
        df["EMA_slow"] = df[self.price_col].ewm(span=slow, adjust=False).mean()
        df["DIF"] = df["EMA_fast"] - df["EMA_slow"]
        df["DEA"] = df["DIF"].ewm(span=signal, adjust=False).mean()
        df["MACD_hist"] = 2 * (df["DIF"] - df["DEA"])

        extra = ["DIF", "DEA", "MACD_hist"]
        trade_df = self._get_trade_data_vectorized(df, extra_cols=extra)
        if len(trade_df) == 0:
            raise ValueError("No trades generated. Check date range and data.")

        hist = trade_df["MACD_hist"].values

        mults = np.where(
            np.isnan(hist),
            1.0,
            np.where(hist <= -0.05, 2.0, np.where(hist < 0, 1.5, np.where(hist <= 0.05, 1.0, 0.5))),
        )
        zones = np.where(
            np.isnan(hist),
            "指标未形成",
            np.where(
                hist <= -0.05,
                "深度超卖",
                np.where(hist < 0, "弱势区间", np.where(hist <= 0.05, "正常偏多", "强势上涨")),
            ),
        )

        trade_df["_mult"] = mults
        trade_df["_zone"] = zones

        return self._build_trades_vectorized(
            trade_df,
            invest_mult_col="_mult",
            zone_col="_zone",
            indicator_cols={"DIF": "DIF", "DEA": "DEA", "MACD_hist": "MACD柱"},
            strategy_name="MACD定投",
        )

    # ================================================================
    # 策略7：RSI策略 — 向量化
    # ================================================================
    def run_rsi_dca(
        self,
        period: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
    ) -> BacktestResult:
        """
        RSI指标定投策略（向量化实现）。
        """
        df = self.df.copy()
        delta = df[self.price_col].diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
        rs = avg_gain / avg_loss
        df["RSI"] = 100 - (100 / (1 + rs))

        extra = ["RSI"]
        trade_df = self._get_trade_data_vectorized(df, extra_cols=extra)
        if len(trade_df) == 0:
            raise ValueError("No trades generated. Check date range and data.")

        rsi = trade_df["RSI"].values

        mults = np.where(
            np.isnan(rsi),
            1.0,
            np.where(
                rsi < oversold,
                2.0,
                np.where(
                    rsi < 45, 1.5, np.where(rsi <= 55, 1.0, np.where(rsi <= overbought, 0.75, 0.5))
                ),
            ),
        )
        zones = np.where(
            np.isnan(rsi),
            "指标未形成",
            np.where(
                rsi < oversold,
                "极度超卖",
                np.where(
                    rsi < 45,
                    "偏弱区间",
                    np.where(
                        rsi <= 55, "中性区间", np.where(rsi <= overbought, "偏强区间", "极度超买")
                    ),
                ),
            ),
        )

        trade_df["_mult"] = mults
        trade_df["_zone"] = zones

        return self._build_trades_vectorized(
            trade_df,
            invest_mult_col="_mult",
            zone_col="_zone",
            indicator_cols={"RSI": "RSI"},
            strategy_name="RSI定投",
        )

    # ================================================================
    # 策略8：波动率策略 — 向量化
    # ================================================================
    def run_volatility_dca(self, vol_period: int = 20) -> BacktestResult:
        """
        波动率定投策略（向量化实现）。
        """
        df = self.df.copy()
        df["daily_ret"] = df[self.price_col].pct_change()
        df["_vol"] = df["daily_ret"].rolling(window=vol_period).std() * np.sqrt(252)
        df["_vol_ma"] = df["_vol"].rolling(window=60).mean()

        extra = ["_vol", "_vol_ma"]
        trade_df = self._get_trade_data_vectorized(df, extra_cols=extra)
        if len(trade_df) == 0:
            raise ValueError("No trades generated. Check date range and data.")

        vol = trade_df["_vol"].values
        vol_ma = trade_df["_vol_ma"].values
        vol_ratio = np.where(
            (vol_ma > 0) & ~np.isnan(vol) & ~np.isnan(vol_ma), vol / vol_ma, np.nan
        )

        mults = np.where(
            np.isnan(vol_ratio),
            1.0,
            np.where(
                vol_ratio > 1.5,
                2.0,
                np.where(vol_ratio > 1.2, 1.5, np.where(vol_ratio < 0.7, 0.75, 1.0)),
            ),
        )
        zones = np.where(
            np.isnan(vol_ratio),
            "指标未形成",
            np.where(
                vol_ratio > 1.5,
                "极度恐慌",
                np.where(
                    vol_ratio > 1.2, "偏恐慌", np.where(vol_ratio < 0.7, "极度平静", "正常波动")
                ),
            ),
        )

        trade_df["_mult"] = mults
        trade_df["_zone"] = zones

        return self._build_trades_vectorized(
            trade_df,
            invest_mult_col="_mult",
            zone_col="_zone",
            indicator_cols={"_vol": "年化波动率", "_vol_ma": "波动率均值"},
            strategy_name="波动率定投",
        )

    # ================================================================
    # 构建每日资产序列 + 计算所有指标
    # ================================================================
    def _build_daily_values(
        self,
        trades_df: pd.DataFrame,
        total_shares: float,
        cumulative_invest_list: List[float],
    ) -> BacktestResult:
        """
        构建每日资产序列，计算所有收益和风险指标
        """
        df = self.df.copy()
        result = BacktestResult()

        # ---- 向量化构建每日资产序列 ----
        # 确定份额变动列名
        if "买入份额" in trades_df.columns:
            share_col = "买入份额"
        elif "份额变动" in trades_df.columns:
            share_col = "份额变动"
        else:
            share_col = None

        # 构建份额变动 Series（对齐到所有日期）
        df_daily = df[["日期", self.price_col]].copy()
        df_daily["_share_change"] = 0.0
        df_daily["_cum_invest"] = 0.0

        if share_col:
            trades_share = trades_df[["日期", share_col]].copy()
            trades_share = trades_share.rename(columns={share_col: "_share_change"})
            trades_share["日期"] = pd.to_datetime(trades_share["日期"])

            # Merge onto daily df
            df_daily = df_daily.merge(trades_share, on="日期", how="left", suffixes=("", "_trade"))
            df_daily["_share_change"] = df_daily["_share_change_trade"].fillna(0)
            df_daily.drop(columns=["_share_change_trade"], inplace=True, errors="ignore")

        # 累计投入映射
        if len(trades_df) > 0:
            trades_invest = pd.DataFrame(
                {
                    "日期": pd.to_datetime(trades_df["日期"]),
                    "_cum_invest_raw": cumulative_invest_list,
                }
            )
            df_daily = df_daily.merge(trades_invest, on="日期", how="left")
            # 前向填充累计投入
            df_daily["_cum_invest"] = df_daily["_cum_invest_raw"].ffill().fillna(0)
            df_daily.drop(columns=["_cum_invest_raw"], inplace=True, errors="ignore")

        # 向量化累计
        df_daily["_cur_shares"] = df_daily["_share_change"].cumsum()
        df_daily["_asset_value"] = df_daily["_cur_shares"] * df_daily[self.price_col]
        df_daily["_profit"] = df_daily["_asset_value"] - df_daily["_cum_invest"]
        df_daily["_return_rate"] = np.where(
            df_daily["_cum_invest"] > 0,
            df_daily["_profit"] / df_daily["_cum_invest"],
            0.0,
        )

        daily_df = pd.DataFrame(
            {
                "日期": df_daily["日期"],
                "净值": df_daily[self.price_col],
                "持有份额": df_daily["_cur_shares"].round(4),
                "累计投入": df_daily["_cum_invest"].round(2),
                "总资产": df_daily["_asset_value"].round(2),
                "收益": df_daily["_profit"].round(2),
                "收益率": df_daily["_return_rate"],
            }
        )

        # ---- 计算核心指标 ----
        result.total_shares = total_shares
        result.total_invest = float(daily_df["累计投入"].iloc[-1]) if len(daily_df) > 0 else 0.0

        final_price = df[self.price_col].iloc[-1]
        result.total_asset = total_shares * final_price
        result.total_profit = result.total_asset - result.total_invest
        result.total_return = (
            result.total_profit / result.total_invest if result.total_invest > 0 else 0
        )

        # 年化收益率
        years = (self.end_date - self.start_date).days / 365.25
        if years > 0 and result.total_invest > 0:
            result.annual_return = (result.total_asset / result.total_invest) ** (1 / years) - 1
        else:
            result.annual_return = 0

        # 平均成本
        if total_shares > 0:
            result.avg_cost = result.total_invest / total_shares
        else:
            result.avg_cost = 0

        # 最大回撤
        if len(daily_df) > 0 and daily_df["总资产"].max() > 0:
            cumulative_max = daily_df["总资产"].cummax()
            drawdowns = (daily_df["总资产"] - cumulative_max) / cumulative_max
            result.max_drawdown = drawdowns.min()
        else:
            result.max_drawdown = 0

        # 年化波动率
        if len(daily_df) > 1:
            daily_returns = daily_df["总资产"].pct_change().dropna()
            if len(daily_returns) > 0:
                result.volatility = daily_returns.std() * np.sqrt(252)  # 年化
            else:
                result.volatility = 0
        else:
            result.volatility = 0

        # 夏普比率
        if result.volatility > 0:
            result.sharpe_ratio = (result.annual_return - self.risk_free_rate) / result.volatility
        else:
            result.sharpe_ratio = 0

        # 月度统计：胜率 & 最大连续亏损月数
        if len(daily_df) > 0:
            daily_df["月份"] = daily_df["日期"].dt.to_period("M")
            monthly = (
                daily_df.groupby("月份")
                .agg(
                    {
                        "总资产": "last",
                        "累计投入": "last",
                        "日期": "first",
                    }
                )
                .reset_index(drop=True)
            )
            monthly["收益率"] = monthly["总资产"].pct_change()

            # 排除第一个月（没有前值）
            valid_monthly = monthly["收益率"].dropna()
            if len(valid_monthly) > 0:
                result.win_rate = (valid_monthly > 0).sum() / len(valid_monthly)
            else:
                result.win_rate = 0

            # 最大连续亏损月数（向量化，使用 utils 公共函数）
            result.max_loss_months = compute_max_consecutive_losses(valid_monthly)
        else:
            result.win_rate = 0
            result.max_loss_months = 0

        result.daily_values = daily_df
        return result

    # ================================================================
    # 贝叶斯参数优化（Optuna）
    # ================================================================
    def optimize_ma_bayesian(
        self,
        n_trials: int = 100,
        train_start: str = "2018-01-01",
        train_end: str = "2020-12-31",
        test_start: str = "2021-01-01",
        test_end: str = "2023-12-31",
        random_state: int = 42,
    ) -> dict:
        """
        使用 Optuna 贝叶斯优化搜索 MA 动态定投的最优参数。

        优化目标：最大化训练集上的夏普比率。
        最终在测试集上评估最优参数，输出过拟合检测。

        参数
        ----
        n_trials : int
            Optuna 优化轮数（默认100）
        train_start / train_end : str
            训练集日期范围
        test_start / test_end : str
            测试集日期范围
        random_state : int
            随机种子

        返回
        ----
        dict with keys:
            best_params, train_result, test_result, study, trials_df,
            train_sharpe, test_sharpe
        """
        import optuna
        from optuna.samplers import TPESampler

        # 切分训练/测试数据
        all_df = self.df.copy()
        train_mask = (all_df["日期"] >= pd.Timestamp(train_start)) & (
            all_df["日期"] <= pd.Timestamp(train_end)
        )
        test_mask = (all_df["日期"] >= pd.Timestamp(test_start)) & (
            all_df["日期"] <= pd.Timestamp(test_end)
        )
        train_df = all_df[train_mask].reset_index(drop=True)
        test_df = all_df[test_mask].reset_index(drop=True)

        if len(train_df) < 250:
            raise ValueError(
                f"Training data too small ({len(train_df)} rows). Need at least 250 trading days."
            )

        # 保存实例参数用于每个 trial 创建引擎
        invest_amount = self.invest_amount
        invest_day = self.invest_day
        fee_rate = self.fee_rate
        risk_free_rate = self.risk_free_rate
        price_col = self.price_col

        def objective(trial):
            """Optuna 目标函数：最大化训练集夏普比率"""
            ma_period = trial.suggest_int("ma_period", 20, 300)
            low_multiplier = trial.suggest_float("low_multiplier", 1.0, 5.0, step=0.1)
            high_multiplier = trial.suggest_float("high_multiplier", 0.1, 1.0, step=0.05)
            low_threshold = trial.suggest_float("low_threshold", 0.70, 0.98, step=0.01)
            high_threshold = trial.suggest_float("high_threshold", 1.02, 1.30, step=0.01)

            # 确保高位阈值 > 低位阈值
            if high_threshold <= low_threshold:
                return float("-inf")

            try:
                bt_inner = FundBacktest(
                    train_df.copy(),
                    invest_amount=invest_amount,
                    invest_day=invest_day,
                    fee_rate=fee_rate,
                    risk_free_rate=risk_free_rate,
                )
                bt_inner.price_col = price_col
                r = bt_inner.run_ma_dynamic_dca(
                    ma_period=ma_period,
                    low_multiplier=low_multiplier,
                    high_multiplier=high_multiplier,
                    low_threshold=low_threshold,
                    high_threshold=high_threshold,
                )
                trial.set_user_attr("annual_return", float(r.annual_return))
                trial.set_user_attr("total_return", float(r.total_return))
                trial.set_user_attr("max_drawdown", float(r.max_drawdown))
                trial.set_user_attr("volatility", float(r.volatility))

                return float(r.sharpe_ratio)
            except Exception as exc:
                # 打印异常信息辅助调试，但不中断优化
                print(f"[Optuna Trial {trial.number}] Failed: {exc}")
                return float("-inf")

        # 创建 Optuna study，最大化夏普比率
        sampler = TPESampler(seed=random_state)
        study = optuna.create_study(
            direction="maximize",
            sampler=sampler,
            study_name="ma_dynamic_optimization",
        )

        # 运行优化（静默模式）
        optuna.logging.set_verbosity(optuna.logging.WARNING)
        study.optimize(objective, n_trials=n_trials, show_progress_bar=True)

        # 确保至少有 1 个有效 trial
        if study.best_trial is None:
            raise ValueError(
                "Optuna optimization failed: all trials returned invalid results. "
                "This may happen if the training data is too small or the date range "
                "contains only price data outside the valid threshold range. "
                "Try a longer training period or a fund with more price variation."
            )

        # ---- 训练集结果 ----
        best_params = study.best_params
        bt_train = FundBacktest(
            train_df.copy(),
            invest_amount=invest_amount,
            invest_day=invest_day,
            fee_rate=fee_rate,
            risk_free_rate=risk_free_rate,
        )
        bt_train.price_col = price_col
        train_result = bt_train.run_ma_dynamic_dca(
            ma_period=best_params["ma_period"],
            low_multiplier=best_params["low_multiplier"],
            high_multiplier=best_params["high_multiplier"],
            low_threshold=best_params["low_threshold"],
            high_threshold=best_params["high_threshold"],
        )

        # ---- 测试集结果 ----
        bt_test = FundBacktest(
            test_df.copy(),
            invest_amount=invest_amount,
            invest_day=invest_day,
            fee_rate=fee_rate,
            risk_free_rate=risk_free_rate,
        )
        bt_test.price_col = price_col
        test_result = bt_test.run_ma_dynamic_dca(
            ma_period=best_params["ma_period"],
            low_multiplier=best_params["low_multiplier"],
            high_multiplier=best_params["high_multiplier"],
            low_threshold=best_params["low_threshold"],
            high_threshold=best_params["high_threshold"],
        )

        # ---- 构建 trials 汇总表 ----
        trials_data = []
        for t in study.trials:
            if t.state == optuna.trial.TrialState.COMPLETE:
                trials_data.append(
                    {
                        "trial": t.number,
                        "ma_period": t.params.get("ma_period"),
                        "low_multiplier": t.params.get("low_multiplier"),
                        "high_multiplier": t.params.get("high_multiplier"),
                        "low_threshold": t.params.get("low_threshold"),
                        "high_threshold": t.params.get("high_threshold"),
                        "sharpe_ratio": round(t.value, 4) if t.value else None,
                        "annual_return": round(t.user_attrs.get("annual_return", 0), 4),
                        "total_return": round(t.user_attrs.get("total_return", 0), 4),
                        "max_drawdown": round(t.user_attrs.get("max_drawdown", 0), 4),
                        "volatility": round(t.user_attrs.get("volatility", 0), 4),
                    }
                )
        trials_df = pd.DataFrame(trials_data)

        return {
            "best_params": best_params,
            "train_result": train_result,
            "test_result": test_result,
            "study": study,
            "trials_df": trials_df,
            "train_sharpe": study.best_value,
            "test_sharpe": test_result.sharpe_ratio,
            "train_start": train_start,
            "train_end": train_end,
            "test_start": test_start,
            "test_end": test_end,
        }


def run_batch_backtest(
    fund_codes: List[str],
    start_date: str = "2021-01-01",
    end_date: str = "2026-06-09",
    invest_amount: float = 1000,
    invest_day: int = 1,
    fee_rate: float = 0.0015,
    risk_free_rate: float = 0.03,
    output_file: str = None,
    sort_by: str = "sharpe_ratio",
    verbose: bool = True,
) -> pd.DataFrame:
    """
    批量回测：对多个基金代码运行全部8个策略，生成对比表格。

    参数
    ----
    fund_codes : List[str]
        基金代码列表，如 ["161725", "110011", "000001"]
    start_date / end_date : str
        回测日期范围
    invest_amount : float
        每期定投金额
    invest_day : int
        每月定投日 (1-28)
    fee_rate : float
        申购费率
    risk_free_rate : float
        无风险利率
    output_file : str or None
        输出 Excel 文件路径，None 则不保存
    sort_by : str
        排序指标，可选: "sharpe_ratio", "annual_return", "total_return", "max_drawdown"
    verbose : bool
        是否打印进度

    返回
    ----
    pd.DataFrame
        包含所有基金×策略组合的对比表，按 sort_by 降序排列
    """
    from data_fetcher import get_fund_data

    # 定义所有策略 (name, method, kwargs)
    strategies = [
        ("普通定投", "run_normal_dca", {}),
        ("60日均线定投", "run_ma60_dca", {}),
        ("MACD定投", "run_macd_dca", {}),
        ("RSI定投", "run_rsi_dca", {}),
        ("波动率定投", "run_volatility_dca", {}),
        ("AI均线动态", "run_ma_dynamic_dca", {}),
        ("止盈定投(20%)", "run_stop_profit_dca", {"stop_profit": 0.20}),
        ("价值平均(+1k)", "run_value_average", {"target_growth": 1000}),
    ]

    all_rows = []
    fund_names = {}  # cache fund names

    for fi, code in enumerate(fund_codes):
        if verbose:
            print(f"\n{'=' * 50}")
            print(f"[{fi + 1}/{len(fund_codes)}] Fund {code}")
            print(f"{'=' * 50}")

        # 获取数据
        try:
            df = get_fund_data(code, start_date, end_date)
        except Exception as e:
            print(f"  [SKIP] Failed to fetch data for {code}: {e}")
            continue

        if len(df) < 60:
            print(f"  [SKIP] Too few records ({len(df)}) for fund {code}")
            continue

        # 获取基金名称（从 data_fetcher 缓存或 df 推断）
        fund_name = code
        try:
            from data_fetcher import FUND_NAME_CACHE

            if code in FUND_NAME_CACHE:
                fund_name = FUND_NAME_CACHE[code]
        except Exception:
            pass

        bt = FundBacktest(
            df,
            invest_amount=invest_amount,
            invest_day=invest_day,
            fee_rate=fee_rate,
            risk_free_rate=risk_free_rate,
        )

        for sname, method_name, kwargs in strategies:
            try:
                method = getattr(bt, method_name)
                r = method(**kwargs)
                all_rows.append(
                    {
                        "基金代码": code,
                        "基金名称": fund_name,
                        "策略": sname,
                        "总投入(元)": round(r.total_invest, 2),
                        "最终资产(元)": round(r.total_asset, 2),
                        "总收益(元)": round(r.total_profit, 2),
                        "总收益率": round(r.total_return, 6),
                        "年化收益率": round(r.annual_return, 6),
                        "夏普比率": round(r.sharpe_ratio, 4),
                        "最大回撤": round(r.max_drawdown, 6),
                        "波动率": round(r.volatility, 6),
                        "胜率": round(r.win_rate, 6),
                        "最大连亏月": r.max_loss_months,
                        "交易次数": len(r.trades),
                    }
                )
                if verbose:
                    print(
                        f"  {sname:12s} | Sharpe={r.sharpe_ratio:+.4f}  "
                        f"Annual={r.annual_return:+.2%}  MaxDD={r.max_drawdown:.2%}"
                    )
            except Exception as e:
                if verbose:
                    print(f"  {sname:12s} | [ERROR] {e}")
                continue

    if not all_rows:
        print("\n[WARN] No results generated.")
        return pd.DataFrame()

    # 构建 DataFrame，按指定指标排序
    result_df = pd.DataFrame(all_rows)
    # 确保基金代码始终为字符串（避免 000001 → 1）
    result_df["基金代码"] = result_df["基金代码"].astype(str).str.zfill(6)
    # 将 sort_by 映射到实际列名
    sort_col, sort_ascending = get_sort_column(sort_by)
    result_df = result_df.sort_values(sort_col, ascending=sort_ascending).reset_index(drop=True)

    # 格式化百分比列
    pct_cols = ["总收益率", "年化收益率", "最大回撤", "波动率", "胜率"]
    for col in pct_cols:
        if col in result_df.columns:
            result_df[col] = result_df[col].apply(lambda x: f"{x:+.2%}" if pd.notna(x) else "")

    # 保存 Excel
    if output_file:
        # 准备写入数据（数值格式，非字符串百分比）
        numeric_df = pd.DataFrame(all_rows)
        numeric_df["基金代码"] = numeric_df["基金代码"].astype(str).str.zfill(6)
        numeric_df = numeric_df.sort_values(sort_col, ascending=sort_ascending).reset_index(
            drop=True
        )

        with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
            # Sheet 1: 原始数值
            numeric_df.to_excel(writer, sheet_name="对比数据", index=False)

            # Sheet 2: 按基金汇总
            summary_rows = []
            for code in numeric_df["基金代码"].unique():
                fund_rows = numeric_df[numeric_df["基金代码"] == code]
                if len(fund_rows) == 0:
                    continue
                best_row = fund_rows.loc[fund_rows["夏普比率"].idxmax()]
                summary_rows.append(
                    {
                        "基金代码": code,
                        "基金名称": fund_rows["基金名称"].iloc[0],
                        "最优策略": best_row["策略"],
                        "最优夏普比率": best_row["夏普比率"],
                        "最优年化收益率": best_row["年化收益率"],
                        "最低年化收益率": fund_rows["年化收益率"].min(),
                        "平均总收益率": fund_rows["总收益率"].mean(),
                        "测试策略数": len(fund_rows),
                    }
                )
            summary_df = pd.DataFrame(summary_rows)
            summary_df = summary_df.sort_values("最优夏普比率", ascending=False)
            summary_df.to_excel(writer, sheet_name="基金汇总", index=False)

            # 格式化 Sheet 1
            ws = writer.sheets["对比数据"]
            # 百分比列格式化
            col_map = {col: i + 1 for i, col in enumerate(numeric_df.columns)}
            for col_name, col_idx in col_map.items():
                # 基金代码列强制文本格式（避免 000001 → 1）
                if col_name == "基金代码":
                    for row in range(2, len(numeric_df) + 2):
                        ws.cell(row=row, column=col_idx).number_format = "@"
                elif col_name in ["总收益率", "年化收益率", "最大回撤", "波动率", "胜率"]:
                    for row in range(2, len(numeric_df) + 2):
                        cell = ws.cell(row=row, column=col_idx)
                        if cell.value is not None:
                            cell.number_format = "0.00%"
                elif col_name in ["夏普比率"]:
                    for row in range(2, len(numeric_df) + 2):
                        cell = ws.cell(row=row, column=col_idx)
                        if cell.value is not None:
                            cell.number_format = "0.0000"

            # 冻结首行
            ws.freeze_panes = "A2"
            # 自动列宽
            for col_cells in ws.columns:
                max_len = max(len(str(c.value or "")) for c in col_cells)
                ws.column_dimensions[col_cells[0].column_letter].width = min(max_len + 4, 30)

            # 格式化 Sheet 2：基金代码文本格式
            ws2 = writer.sheets["基金汇总"]
            ws2.freeze_panes = "A2"
            fund_code_col = list(summary_df.columns).index("基金代码") + 1
            for row in range(2, len(summary_df) + 2):
                ws2.cell(row=row, column=fund_code_col).number_format = "@"

        if verbose:
            print(f"\n[OK] Excel saved to: {output_file}")

    return result_df


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "batch":
        # 批量模式: python backtest.py batch
        codes = (
            sys.argv[2:]
            if len(sys.argv) > 2
            else [
                "161725",
                "110011",
                "000001",
                "002610",
                "001632",
            ]
        )
        print("=" * 60)
        print("Batch Backtest — Multi-Fund × Multi-Strategy")
        print("=" * 60)
        print(f"Funds: {codes}")
        print(f"Date: 2021-01-01 ~ 2026-06-09")
        print(f"Invest: CNY 1000/month\n")

        result_df = run_batch_backtest(
            fund_codes=codes,
            start_date="2021-01-01",
            end_date="2026-06-09",
            output_file="batch_backtest_result.xlsx",
            sort_by="sharpe_ratio",
        )

        print(f"\n{'=' * 60}")
        print("Top 10 (by Sharpe ratio):")
        print(f"{'=' * 60}")
        print(result_df.head(10).to_string(index=False))
        print(f"\nTotal: {len(result_df)} fund×strategy combinations")
        print(f"Output: batch_backtest_result.xlsx")

    else:
        # 单基金测试模式（原逻辑）
        from data_fetcher import get_fund_data

        print("=" * 60)
        print("Fund Backtest Framework Test")
        print("=" * 60)

        # 加载数据
        df = get_fund_data("161725", "2021-01-01", "2026-06-09")

        # 创建回测引擎
        bt = FundBacktest(df, invest_amount=1000, invest_day=1)

        # 辅助打印函数
        def print_result(r, name):
            print(f"\n--- {name} ---")
            print(f"总投入:     {r.total_invest:>10.2f} 元")
            print(f"总资产:     {r.total_asset:>10.2f} 元")
            print(f"总收益:     {r.total_profit:>10.2f} 元")
            print(f"总收益率:   {r.total_return:>10.2%}")
            print(f"年化收益率: {r.annual_return:>10.2%}")
            print(f"最大回撤:   {r.max_drawdown:>10.2%}")
            print(f"夏普比率:   {r.sharpe_ratio:>10.4f}")
            print(f"波动率:     {r.volatility:>10.2%}")
            print(f"胜率:       {r.win_rate:>10.2%}")
            print(f"最大连亏月: {r.max_loss_months:>10}")
            print(f"交易次数:   {len(r.trades):>10}")

        # 测试全部8个策略
        print_result(bt.run_normal_dca(), "普通定投")
        print_result(bt.run_ma60_dca(), "60日均线定投")
        print_result(bt.run_macd_dca(), "MACD定投")
        print_result(bt.run_rsi_dca(), "RSI定投")
        print_result(bt.run_volatility_dca(), "波动率定投")
        print_result(bt.run_ma_dynamic_dca(), "AI均线动态定投")
        print_result(bt.run_stop_profit_dca(), "止盈定投")
        print_result(bt.run_value_average(), "价值平均策略")
