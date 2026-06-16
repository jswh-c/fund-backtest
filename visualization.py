"""
可视化模块
使用Plotly生成交互式图表，包括：
- 累计收益对比曲线
- 回撤曲线
- 月度收益热力图
- 风险指标雷达图
- 策略对比表格
"""

import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
import os
from typing import List, Dict
from backtest import BacktestResult


# 配色方案
COLORS = {
    "普通定投": "#5470C6",
    "止盈定投": "#91CC75",
    "价值平均": "#FAC858",
    "动态定投": "#EE6666",
    "MA动态": "#73C0DE",
}


def _get_color(name: str) -> str:
    """根据策略名获取颜色"""
    for key, color in COLORS.items():
        if key in name:
            return color
    return "#999999"


def _hex_to_rgb(hex_color: str) -> tuple:
    """将十六进制颜色转为RGB"""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def plot_cumulative_returns(
    results: List[BacktestResult],
    names: List[str],
    title: str = "Cumulative Return Comparison",
) -> go.Figure:
    """
    累计收益对比曲线
    显示每种策略的总资产随时间变化
    """
    fig = go.Figure()

    for result, name in zip(results, names):
        if result is None or result.daily_values is None or len(result.daily_values) == 0:
            continue

        dv = result.daily_values
        color = _get_color(name)

        # 累计收益率曲线
        fig.add_trace(
            go.Scatter(
                x=dv["日期"],
                y=dv["收益率"] * 100,  # 转为百分比
                mode="lines",
                name=f"{name} ({result.annual_return:.2%} annual)",
                line=dict(color=color, width=2),
                hovertemplate=(
                    f"<b>{name}</b><br>"
                    "Date: %{x|%Y-%m-%d}<br>"
                    "Return: %{y:.2f}%<br>"
                    "<extra></extra>"
                ),
            )
        )

    # 添加零线
    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)

    fig.update_layout(
        title=dict(text=title, font=dict(size=20)),
        xaxis_title="Date",
        yaxis_title="Cumulative Return (%)",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
        ),
        hovermode="x unified",
        template="plotly_white",
        height=500,
    )

    return fig


def plot_asset_growth(
    results: List[BacktestResult],
    names: List[str],
    title: str = "Total Asset Growth",
) -> go.Figure:
    """
    总资产增长曲线
    """
    fig = go.Figure()

    for result, name in zip(results, names):
        if result is None or result.daily_values is None or len(result.daily_values) == 0:
            continue

        dv = result.daily_values
        color = _get_color(name)

        # 总资产曲线
        fig.add_trace(
            go.Scatter(
                x=dv["日期"],
                y=dv["总资产"],
                mode="lines",
                name=name,
                line=dict(color=color, width=2),
                hovertemplate=(
                    f"<b>{name}</b><br>"
                    "Date: %{x|%Y-%m-%d}<br>"
                    "Asset: %{y:,.0f}<br>"
                    "<extra></extra>"
                ),
            )
        )

        # 累计投入线（虚线）
        if result.total_invest > 0:
            fig.add_trace(
                go.Scatter(
                    x=dv["日期"],
                    y=dv["累计投入"],
                    mode="lines",
                    name=f"{name} (Invested)",
                    line=dict(color=color, width=1, dash="dot"),
                    showlegend=False,
                    hovertemplate="Invested: %{y:,.0f}<extra></extra>",
                )
            )

    fig.update_layout(
        title=dict(text=title, font=dict(size=20)),
        xaxis_title="Date",
        yaxis_title="Asset / Invested (yuan)",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
        ),
        hovermode="x unified",
        template="plotly_white",
        height=500,
    )

    return fig


def plot_drawdowns(
    results: List[BacktestResult],
    names: List[str],
    title: str = "Drawdown Analysis",
) -> go.Figure:
    """
    回撤曲线
    """
    fig = go.Figure()

    for result, name in zip(results, names):
        if result is None or result.daily_values is None or len(result.daily_values) == 0:
            continue

        dv = result.daily_values
        color = _get_color(name)

        # 计算回撤
        cumulative_max = dv["总资产"].cummax()
        drawdowns = (dv["总资产"] - cumulative_max) / cumulative_max.replace(0, np.nan) * 100

        r, g, b = _hex_to_rgb(color)
        fig.add_trace(
            go.Scatter(
                x=dv["日期"],
                y=drawdowns,
                mode="lines",
                name=f"{name} (Max: {result.max_drawdown:.2%})",
                line=dict(color=color, width=2),
                fill="tozeroy",
                fillcolor=f"rgba({r},{g},{b},0.1)",
                hovertemplate=(
                    f"<b>{name}</b><br>"
                    "Date: %{x|%Y-%m-%d}<br>"
                    "Drawdown: %{y:.2f}%<br>"
                    "<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        title=dict(text=title, font=dict(size=20)),
        xaxis_title="Date",
        yaxis_title="Drawdown (%)",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
        ),
        hovermode="x unified",
        template="plotly_white",
        height=400,
    )

    fig.update_yaxes(autorange="reversed")

    return fig


def plot_monthly_heatmap(
    result: BacktestResult,
    name: str,
    title: str = None,
) -> go.Figure:
    """
    月度收益热力图
    """
    if result is None or result.daily_values is None:
        return go.Figure()

    dv = result.daily_values.copy()
    dv["年份"] = dv["日期"].dt.year
    dv["月份"] = dv["日期"].dt.month

    # 计算月度收益率
    monthly = (
        dv.groupby(["年份", "月份"])
        .agg(
            {
                "总资产": "last",
                "累计投入": "last",
            }
        )
        .reset_index()
    )
    monthly["月度收益率"] = monthly.groupby("年份")["总资产"].pct_change()

    # 构建热力图数据
    pivot = monthly.pivot_table(
        values="月度收益率",
        index="年份",
        columns="月份",
        aggfunc="first",
    )

    for m in range(1, 13):
        if m not in pivot.columns:
            pivot[m] = np.nan
    pivot = pivot[sorted(pivot.columns)]

    text_arr = []
    for col in pivot.columns:
        col_text = []
        for val in pivot[col]:
            if pd.notna(val):
                col_text.append(f"{val:.2%}")
            else:
                col_text.append("")
        text_arr.append(col_text)
    text_matrix = list(zip(*text_arr)) if text_arr else []

    if title is None:
        title = f"Monthly Return Heatmap - {name}"

    fig = go.Figure(
        data=go.Heatmap(
            z=pivot.values * 100,
            x=[f"M{m}" for m in pivot.columns],
            y=[str(y) for y in pivot.index],
            text=text_matrix,
            texttemplate="%{text}",
            textfont={"size": 10},
            colorscale=[
                [0, "#DC143C"],
                [0.35, "#FFB6C1"],
                [0.5, "#F5F5F5"],
                [0.65, "#90EE90"],
                [1, "#006400"],
            ],
            zmid=0,
            colorbar=dict(
                title="Return (%)",
                tickformat=".1f",
            ),
            hovertemplate=(
                "Year: %{y}<br>" "Month: %{x}<br>" "Return: %{z:.2f}%<br>" "<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        title=dict(text=title, font=dict(size=18)),
        xaxis_title="Month",
        yaxis_title="Year",
        template="plotly_white",
        height=400,
        yaxis=dict(dtick=1),
    )

    return fig


def plot_risk_radar(
    results: List[BacktestResult],
    names: List[str],
    title: str = "Risk & Return Radar",
) -> go.Figure:
    """
    风险指标雷达图
    """
    metrics = [
        "annual_return",
        "sharpe_ratio",
        "win_rate",
        "max_drawdown",
        "volatility",
        "max_loss_months",
    ]
    metric_labels = [
        "Annual Return",
        "Sharpe Ratio",
        "Win Rate",
        "Max Drawdown",
        "Volatility",
        "Max Loss Months",
    ]

    all_values = {m: [] for m in metrics}
    for result in results:
        if result is None:
            continue
        for m in metrics:
            val = getattr(result, m, 0)
            all_values[m].append(val)

    fig = go.Figure()

    for result, name in zip(results, names):
        if result is None:
            continue

        values = []
        for m in metrics:
            val = getattr(result, m, 0)
            vals = all_values[m]
            if len(vals) == 0 or max(vals) == min(vals):
                values.append(50)
                continue

            min_v, max_v = min(vals), max(vals)
            if m in ["max_drawdown", "volatility", "max_loss_months"]:
                values.append((max_v - val) / (max_v - min_v) * 100)
            else:
                values.append((val - min_v) / (max_v - min_v) * 100)

        color = _get_color(name)
        r, g, b = _hex_to_rgb(color)

        fig.add_trace(
            go.Scatterpolar(
                r=values,
                theta=metric_labels,
                name=name,
                fill="toself",
                line=dict(color=color, width=2),
                fillcolor=f"rgba({r},{g},{b},0.2)",
            )
        )

    fig.update_layout(
        title=dict(text=title, font=dict(size=20)),
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100],
                showticklabels=False,
            ),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.05,
            xanchor="center",
            x=0.5,
        ),
        template="plotly_white",
        height=500,
    )

    return fig


def plot_optimization_analysis(
    study,
    title: str = "Optuna Bayesian Optimization Analysis",
) -> go.Figure:
    """
    Optuna 贝叶斯优化敏感性分析图（4合1）

    子图：
    - 左上：优化历史（目标值 vs 试验次数）
    - 右上：参数重要性（水平条形图）
    - 左下：前两个最重要参数与目标的散点关系
    - 右下：平行坐标图（高亮最优 trial）
    """
    import optuna
    from optuna.importance import get_param_importances

    # 收集完成的 trials
    completed = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    if not completed:
        fig = go.Figure()
        fig.update_layout(title="No completed trials to analyze")
        return fig

    param_names = list(completed[0].params.keys())
    n_params = len(param_names)

    fig = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=(
            "Optimization History",
            "Parameter Importance",
            "Parameter Relationship (top 2 params)",
            "Parallel Coordinate",
        ),
        specs=[
            [{"type": "scatter"}, {"type": "bar"}],
            [{"type": "scatter"}, {"type": "parcoords"}],
        ],
        vertical_spacing=0.10,
        horizontal_spacing=0.08,
    )

    # ---- 1. 优化历史 ----
    trial_nums = list(range(1, len(completed) + 1))
    values = [t.value for t in completed]
    best_so_far = []
    cur_best = float("-inf")
    for v in values:
        if v is not None and v > cur_best:
            cur_best = v
        best_so_far.append(cur_best)

    fig.add_trace(
        go.Scatter(
            x=trial_nums,
            y=values,
            mode="markers",
            name="Trial Value",
            marker=dict(color="lightblue", size=5, opacity=0.6),
            hovertemplate="Trial %{x}<br>Sharpe: %{y:.4f}<extra></extra>",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=trial_nums,
            y=best_so_far,
            mode="lines",
            name="Best So Far",
            line=dict(color="red", width=2),
            hovertemplate="Best: %{y:.4f}<extra></extra>",
        ),
        row=1,
        col=1,
    )

    # ---- 2. 参数重要性 ----
    try:
        importances = get_param_importances(study)
        imp_names = list(importances.keys())
        imp_values = [importances[n] * 100 for n in imp_names]
    except Exception:
        imp_names, imp_values = param_names, [0] * n_params

    sorted_idx = sorted(range(len(imp_values)), key=lambda i: imp_values[i])
    sorted_names = [imp_names[i] for i in sorted_idx]
    sorted_vals = [imp_values[i] for i in sorted_idx]

    fig.add_trace(
        go.Bar(
            y=sorted_names,
            x=sorted_vals,
            orientation="h",
            name="Importance",
            marker=dict(color=sorted_vals, colorscale="Viridis", showscale=False),
            text=[f"{v:.1f}%" for v in sorted_vals],
            textposition="outside",
            hovertemplate="%{y}: %{x:.1f}%<extra></extra>",
        ),
        row=1,
        col=2,
    )

    # ---- 3. 前两个最重要参数的散点关系 ----
    if n_params >= 2:
        top2_names = list(reversed(sorted_names))[:2]
        x_vals = [t.params[top2_names[0]] for t in completed]
        y_vals = [t.params[top2_names[1]] for t in completed]
        z_vals = [t.value if t.value is not None else 0 for t in completed]

        fig.add_trace(
            go.Scatter(
                x=x_vals,
                y=y_vals,
                mode="markers",
                name="Trials",
                marker=dict(
                    size=8,
                    color=z_vals,
                    colorscale="RdYlGn",
                    colorbar=dict(title="Sharpe", x=0.46, len=0.45),
                    showscale=True,
                    line=dict(width=1, color="black"),
                ),
                hovertemplate=(
                    f"{top2_names[0]}: %{{x}}<br>"
                    f"{top2_names[1]}: %{{y}}<br>"
                    "Sharpe: %{marker.color:.4f}<extra></extra>"
                ),
            ),
            row=2,
            col=1,
        )

        # 高亮最优参数
        best_t = study.best_trial
        fig.add_trace(
            go.Scatter(
                x=[best_t.params[top2_names[0]]],
                y=[best_t.params[top2_names[1]]],
                mode="markers",
                name="Best",
                marker=dict(
                    size=16, color="red", symbol="star", line=dict(width=2, color="darkred")
                ),
                hovertemplate=f"★ BEST<br>{top2_names[0]}: %{{x}}<br>{top2_names[1]}: %{{y}}<extra></extra>",
            ),
            row=2,
            col=1,
        )

        fig.update_xaxes(title_text=top2_names[0], row=2, col=1)
        fig.update_yaxes(title_text=top2_names[1], row=2, col=1)

    # ---- 4. 平行坐标图 ----
    # 分位数标记（高 Sharpe / 低 Sharpe）
    valid_vals = [v for v in values if v is not None]
    threshold = np.median(valid_vals) if valid_vals else 0

    dims = []
    for pname in param_names:
        if isinstance(completed[0].params[pname], float):
            dims.append(
                dict(
                    label=pname,
                    values=[t.params[pname] for t in completed],
                )
            )
        else:
            dims.append(
                dict(
                    label=pname,
                    values=[float(t.params[pname]) for t in completed],
                )
            )

    # Add Sharpe dimension with coloring
    dims.append(
        dict(
            label="Sharpe",
            values=values,
            range=[min(values), max(values)] if values else [0, 1],
        )
    )

    line_colors = []
    for v in values:
        if v is not None and v >= threshold:
            line_colors.append("red")
        else:
            line_colors.append("lightgray")

    # Build a separate parcoords trace for better interactivity
    parcoords_trace = go.Parcoords(
        line=dict(
            color=values,
            colorscale="RdYlGn",
            showscale=True,
            colorbar=dict(title="Sharpe"),
        ),
        dimensions=dims,
        name="Trials",
    )

    fig.add_trace(parcoords_trace, row=2, col=2)

    # ---- 布局 ----
    fig.update_layout(
        title=dict(text=title, font=dict(size=22), x=0.5),
        template="plotly_white",
        height=850,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.08,
            xanchor="center",
            x=0.5,
        ),
    )

    fig.update_xaxes(title_text="Trial", row=1, col=1)
    fig.update_yaxes(title_text="Sharpe Ratio", row=1, col=1)
    fig.update_xaxes(title_text="Importance (%)", row=1, col=2)

    return fig


def plot_comparison_table(
    results: List[BacktestResult],
    names: List[str],
    title: str = "Strategy Comparison",
) -> go.Figure:
    """
    策略对比表格
    """
    if not results:
        return go.Figure()

    data = []
    for result, name in zip(results, names):
        if result is None:
            continue
        trades_count = len(result.trades) if result.trades is not None else 0
        data.append(
            {
                "Strategy": name,
                "Invested": f"{result.total_invest:,.0f}",
                "Asset": f"{result.total_asset:,.0f}",
                "Profit": f"{result.total_profit:+,.0f}",
                "Return": f"{result.total_return:+.2%}",
                "Annual": f"{result.annual_return:+.2%}",
                "Sharpe": f"{result.sharpe_ratio:.2f}",
                "MaxDD": f"{result.max_drawdown:.2%}",
                "Vol": f"{result.volatility:.2%}",
                "WinRate": f"{result.win_rate:.1%}",
                "MaxLoss": f"{result.max_loss_months}",
                "Trades": f"{trades_count}",
            }
        )

    if not data:
        return go.Figure()

    df_table = pd.DataFrame(data)

    fig = go.Figure(
        data=[
            go.Table(
                header=dict(
                    values=list(df_table.columns),
                    fill_color="#2C3E50",
                    font=dict(color="white", size=11),
                    align="center",
                ),
                cells=dict(
                    values=[df_table[col] for col in df_table.columns],
                    fill_color=[["#f8f9fa", "#e9ecef"] * len(df_table)],
                    font=dict(size=11),
                    align="center",
                    height=28,
                ),
            )
        ]
    )

    fig.update_layout(
        title=dict(text=title, font=dict(size=20)),
        template="plotly_white",
        height=250 + len(data) * 35,
    )

    return fig


def plot_all_results(
    results: List[BacktestResult],
    names: List[str],
    save_html: bool = True,
    output_dir: str = "output",
):
    """一键生成所有图表"""
    if save_html:
        os.makedirs(output_dir, exist_ok=True)

    valid_results = []
    valid_names = []
    for r, n in zip(results, names):
        if r is not None:
            valid_results.append(r)
            valid_names.append(n)

    if not valid_results:
        print("No valid results to plot.")
        return {}

    figs = {}

    print("Generating cumulative return chart...")
    figs["cumulative_returns"] = plot_cumulative_returns(valid_results, valid_names)

    print("Generating asset growth chart...")
    figs["asset_growth"] = plot_asset_growth(valid_results, valid_names)

    print("Generating drawdown chart...")
    figs["drawdowns"] = plot_drawdowns(valid_results, valid_names)

    for result, name in zip(valid_results, valid_names):
        print(f"Generating heatmap for {name}...")
        safe_name = name.replace("/", "_").replace("\\", "_").replace(" ", "_")
        figs[f"heatmap_{safe_name}"] = plot_monthly_heatmap(result, name)

    if len(valid_results) >= 2:
        print("Generating risk radar chart...")
        figs["radar"] = plot_risk_radar(valid_results, valid_names)

    print("Generating comparison table...")
    figs["table"] = plot_comparison_table(valid_results, valid_names)

    if save_html:
        for key, fig in figs.items():
            filepath = os.path.join(output_dir, f"{key}.html")
            fig.write_html(filepath)
            print(f"  Saved: {filepath}")

    return figs


if __name__ == "__main__":
    from data_fetcher import get_fund_data
    from backtest import FundBacktest

    print("=" * 60)
    print("Visualization Module Test")
    print("=" * 60)

    df = get_fund_data("161725", "2021-01-01", "2026-06-09")
    bt = FundBacktest(df, invest_amount=1000, invest_day=1)

    print("\nRunning all strategies...")
    r1 = bt.run_normal_dca()
    r2 = bt.run_stop_profit_dca(stop_profit=0.20)
    r3 = bt.run_value_average(target_growth=1000)
    r4 = bt.run_ma_dynamic_dca(ma_period=250, low_multiplier=2.0, high_multiplier=0.5)

    results = [r1, r2, r3, r4]
    names = ["Normal DCA", "Stop-Profit 20%", "Value Avg +1000", "MA250 Dynamic"]

    print("\n--- Strategy Comparison ---")
    for name, r in zip(names, results):
        print(
            f"{name}: Annual={r.annual_return:+.2%}, Sharpe={r.sharpe_ratio:.2f}, "
            f"MaxDD={r.max_drawdown:.2%}, WinRate={r.win_rate:.1%}"
        )

    figs = plot_all_results(results, names, save_html=True)
    print("\nDone! Check the 'output' folder for HTML charts.")
