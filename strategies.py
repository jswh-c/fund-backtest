"""
机器学习增强策略模块

使用随机森林（Random Forest）等技术指标训练分类器，
预测未来市场方向，动态调整定投金额。
"""

from __future__ import annotations

import warnings
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

from backtest import BacktestResult, FundBacktest

warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")


# ================================================================
# 特征工程
# ================================================================
def _build_features(df: pd.DataFrame, price_col: str) -> pd.DataFrame:
    """
    从净值数据构建机器学习特征矩阵。

    计算以下技术指标作为特征：
    - MA 比值：price / MA(20), price / MA(60), price / MA(120), price / MA(250)
    - MA 斜率：MA(20) 的 5 日变化率
    - MACD：DIF, DEA, MACD 柱
    - RSI：14 日 RSI
    - 波动率：20 日年化波动率、波动率相对水平
    - 动量：5 日、10 日、20 日收益率
    - 价格位置：当前价格在 20/60 日高/低之间的位置

    返回
    ----
    pd.DataFrame : 特征矩阵（含 NaN 的原始值，调用方负责处理）
    """
    price = df[price_col]

    features = pd.DataFrame(index=df.index)

    # --- MA 比值 ---
    for w in [20, 60, 120, 250]:
        ma = price.rolling(window=w, min_periods=1).mean()
        features[f"MA{w}_ratio"] = price / ma - 1.0

    # --- MA 斜率 ---
    ma20 = price.rolling(window=20, min_periods=1).mean()
    features["MA20_slope"] = ma20.pct_change(periods=5)

    # --- MACD ---
    ema12 = price.ewm(span=12, adjust=False).mean()
    ema26 = price.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    features["MACD_dif"] = dif / price
    features["MACD_dea"] = dea / price
    features["MACD_hist"] = (dif - dea) / price

    # --- RSI (14) ---
    delta = price.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / 14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    features["RSI"] = 100.0 - (100.0 / (1.0 + rs))

    # --- 波动率 ---
    daily_ret = price.pct_change()
    vol20 = daily_ret.rolling(window=20, min_periods=5).std() * np.sqrt(252)
    vol60 = vol20.rolling(window=60, min_periods=10).mean()
    features["Volatility"] = vol20
    features["Vol_ratio"] = vol20 / vol60.replace(0, np.nan)

    # --- 动量 ---
    for p in [5, 10, 20]:
        features[f"Momentum_{p}d"] = price.pct_change(periods=p)

    # --- 价格位置 ---
    for w in [20, 60]:
        high = price.rolling(window=w, min_periods=1).max()
        low = price.rolling(window=w, min_periods=1).min()
        features[f"Position_{w}d"] = (price - low) / (high - low).replace(0, np.nan)

    return features


def _build_labels(df: pd.DataFrame, price_col: str, horizon: int = 21) -> pd.Series:
    """
    构建二分类标签：未来 horizon 个交易日是否上涨。

    返回
    ----
    pd.Series : 1 = 上涨, 0 = 下跌或持平
    """
    price = df[price_col]
    future_price = price.shift(-horizon)
    labels = (future_price > price).astype(int)
    return labels


# ================================================================
# 随机森林定投策略
# ================================================================
def run_ml_rf_dca(
    bt: FundBacktest,
    n_estimators: int = 100,
    max_depth: int = 6,
    train_ratio: float = 0.80,
    lookback_horizon: int = 21,
    up_threshold: float = 0.70,
    down_threshold: float = 0.70,
    random_state: int = 42,
) -> BacktestResult:
    """
    基于随机森林的机器学习定投策略。

    流程：
    1. 从历史净值数据计算技术指标特征
    2. 用前 train_ratio 的数据训练随机森林分类器（预测未来1个月涨跌）
    3. 用训练好的模型对所有交易日做预测
    4. 根据预测概率动态调整每月定投金额：
       - 预测上涨概率 > up_threshold → 定投金额 × 2
       - 预测下跌概率 > down_threshold → 定投金额 × 0.5
       - 否则 → 正常定投

    参数
    ----
    bt : FundBacktest
        回测引擎实例
    n_estimators : int
        随机森林树的数量
    max_depth : int
        树的最大深度
    train_ratio : float
        训练集占比（时间序列前 train_ratio 的数据）
    lookback_horizon : int
        预测目标：未来多少个交易日（默认 21 ≈ 1 个月）
    up_threshold : float
        上涨概率阈值（高于此值加倍）
    down_threshold : float
        下跌概率阈值（高于此值减半）
    random_state : int
        随机种子

    返回
    ----
    BacktestResult
    """
    df = bt.df.copy()
    price_col = bt.price_col

    # ---- 特征工程 ----
    feature_df = _build_features(df, price_col)
    labels = _build_labels(df, price_col, horizon=lookback_horizon)

    # 去除 NaN（指标未形成的早期数据）
    valid_mask = feature_df.notna().all(axis=1) & labels.notna()
    X: np.ndarray = feature_df[valid_mask].values.astype(np.float64)
    y: np.ndarray = labels[valid_mask].values.astype(int)

    if len(X) < 200:
        raise ValueError(
            f"Insufficient valid data for ML training ({len(X)} rows). "
            f"Need at least 200 trading days with complete indicators."
        )

    # ---- 训练/测试切分（时序） ----
    split_idx = int(len(X) * train_ratio)
    if split_idx < 50:
        raise ValueError(
            f"Training set too small ({split_idx} rows). "
            f"Try increasing train_ratio (current: {train_ratio:.0%}) or using a longer date range."
        )
    X_train, y_train = X[:split_idx], y[:split_idx]

    # 标准化 + 训练（sklearn 异常统一转换友好提示）
    try:
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_all_scaled = scaler.transform(X)

        model = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_leaf=5,
            random_state=random_state,
            n_jobs=-1,
        )
        model.fit(X_train_scaled, y_train)

        prob_up_all = model.predict_proba(X_all_scaled)[:, 1]
    except ValueError as e:
        raise ValueError(
            f"ML training failed: {e}. "
            f"This may happen if all labels are the same (e.g., market only went up or down). "
            f"Try a different date range or fund code."
        ) from e

    # ---- 将预测概率映射回交易日 ----
    # 构建 trade_df（复用引擎的向量化方法）
    trade_df = bt._get_trade_data_vectorized(df)
    if len(trade_df) == 0:
        raise ValueError("No trade dates generated.")

    # 为每个交易日查找对应的预测概率
    valid_dates = df.loc[valid_mask, "日期"].values
    prob_series = pd.Series(prob_up_all, index=valid_dates)

    trade_dates_list = trade_df["日期"].values
    prob_values = np.full(len(trade_dates_list), 0.5)  # 默认 0.5

    for i, td in enumerate(trade_dates_list):
        mask_dates = (valid_dates == td)
        if mask_dates.any():
            prob_values[i] = prob_series.loc[td]

    # ---- 根据概率计算投资倍数 ----
    mults = np.where(
        prob_values > up_threshold, 2.0,
        np.where((1.0 - prob_values) > down_threshold, 0.5, 1.0),
    )
    zones = np.where(
        prob_values > up_threshold, "ML看涨加倍",
        np.where((1.0 - prob_values) > down_threshold, "ML看跌减半", "ML中性"),
    )

    trade_df["_mult"] = mults
    trade_df["_zone"] = zones

    # 将预测概率存入指标列
    trade_df["_prob_up"] = np.round(prob_values, 4)

    result = bt._build_trades_vectorized(
        trade_df,
        invest_mult_col="_mult",
        zone_col="_zone",
        indicator_cols={"_prob_up": "ML上涨概率"},
        strategy_name=f"ML随机森林(RF{n_estimators})",
    )

    # ---- 附加模型元信息 ----
    train_acc = float(model.score(X_train_scaled, y_train))
    test_acc = float(model.score(X_all_scaled[split_idx:], y[split_idx:])) if split_idx < len(y) else train_acc

    # 特征重要性
    feat_names = feature_df.columns.tolist()
    importances = model.feature_importances_
    top_idx = np.argsort(importances)[-5:][::-1]
    top_features = {feat_names[i]: float(importances[i]) for i in top_idx}

    # 将元信息附加到 result（非侵入式）
    result.ml_meta = {
        "model_type": "RandomForestClassifier",
        "n_estimators": n_estimators,
        "max_depth": max_depth,
        "train_samples": int(split_idx),
        "test_samples": int(len(X) - split_idx),
        "train_accuracy": round(train_acc, 4),
        "test_accuracy": round(test_acc, 4),
        "train_ratio": train_ratio,
        "lookback_horizon": lookback_horizon,
        "top_features": top_features,
        "feature_count": len(feat_names),
    }

    return result
