"""
Streamlit Web 界面 — 基金定投策略回测系统
运行方式: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import sys
import os
from datetime import datetime, timedelta
import plotly.graph_objects as go

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(__file__))

from data_fetcher import get_fund_data, get_available_funds
from backtest import FundBacktest
from strategies import run_ml_rf_dca
from visualization import (
    plot_cumulative_returns,
    plot_asset_growth,
    plot_drawdowns,
    plot_monthly_heatmap,
    plot_risk_radar,
    plot_comparison_table,
    plot_optimization_analysis,
)
from pdf_report import generate_pdf_report


# ---- 统一初始化所有 session_state key ----
def _init_session_state() -> None:
    """集中初始化所有 session_state 变量，避免 KeyError 和分散维护。"""
    defaults: dict = {
        # 回测参数 widget keys
        "widget_fund_code": "161725",
        "widget_start_date": datetime(2021, 1, 1),
        "widget_end_date": datetime.now(),
        "widget_invest_amount": 1000,
        "widget_invest_day": 1,
        "widget_fee_rate": 0.0015,
        # UI 状态
        "dark_mode": False,
        "dark_mode_toggle": False,
        "quick_select": "",
        # 回测运行时数据
        "backtest_df": None,
        "backtest_results": None,
        "backtest_names": None,
        "has_backtest_run": False,  # 控制结果显示的持久化标志
        # 快照系统
        "snapshots": [],
        "_restore_snapshot": None,
        "_pdf_bytes": None,
        "_pdf_name": "fund_dca_report.pdf",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


_init_session_state()


# ---- 回调函数（组件联动） ----
def _on_dark_mode_toggle() -> None:
    """黑暗模式 toggle 回调：同步 toggle 值到 dark_mode 状态。"""
    st.session_state.dark_mode = st.session_state.dark_mode_toggle


def _on_quick_select() -> None:
    """快速选择下拉框回调：将选中的基金代码写入 widget_fund_code。"""
    selected: str = st.session_state.quick_select
    if selected:
        quick_funds: dict = {
            "161725 - 招商中证白酒": "161725",
            "110011 - 易方达中小盘": "110011",
            "002610 - 博时黄金ETF联接A": "002610",
            "000001 - 华夏成长混合": "000001",
            "001632 - 天弘中证食品饮料ETF联接A": "001632",
        }
        st.session_state.widget_fund_code = quick_funds[selected]


# ---- 快照恢复处理 ----
if st.session_state.get("_restore_snapshot"):
    snap = st.session_state.pop("_restore_snapshot")
    st.session_state.widget_fund_code = snap["fund_code"]
    st.session_state.widget_start_date = datetime.strptime(snap["start_date"], "%Y-%m-%d")
    st.session_state.widget_end_date = datetime.strptime(snap["end_date"], "%Y-%m-%d")
    st.session_state.widget_invest_amount = snap["invest_amount"]
    st.session_state.widget_invest_day = snap["invest_day"]
    st.session_state.widget_fee_rate = snap["fee_rate"]
    st.rerun()

# ---- 页面配置 ----
st.set_page_config(
    page_title="Fund DCA Backtest System",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📈 智能基金定投策略回测与AI优化系统")
st.markdown("*Fund DCA Backtest & AI Optimization System*")

# ---- 黑暗模式 CSS ----
if st.session_state.dark_mode:
    st.markdown(
        """
    <style>
    .stApp {
        background-color: #0e1117;
    }
    .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
    .stApp p, .stApp span, .stApp div, .stApp label, .stApp li,
    .stApp .stMarkdown, .stApp .stText, .stApp .stCaption {
        color: #f0f0f0 !important;
    }
    .stDataFrame, .stTable, [data-testid="stTable"] {
        background-color: #1e2130 !important;
    }
    .stDataFrame th, .stTable th {
        background-color: #2c3040 !important;
        color: #f0f0f0 !important;
    }
    .stDataFrame td, .stTable td {
        background-color: #1e2130 !important;
        color: #e0e0e0 !important;
    }
    [data-testid="stSidebar"] {
        background-color: #161a24;
    }
    [data-testid="stSidebar"] * {
        color: #e0e0e0 !important;
    }
    [data-testid="stSidebar"] .stSelectbox label,
    [data-testid="stSidebar"] .stSlider label,
    [data-testid="stSidebar"] .stNumberInput label,
    [data-testid="stSidebar"] .stTextInput label,
    [data-testid="stSidebar"] .stCheckbox label,
    [data-testid="stSidebar"] .stDateInput label {
        color: #c0c0d0 !important;
    }
    .stButton>button {
        background-color: #2e3b5c !important;
        color: #f0f0f0 !important;
        border-color: #4a5580 !important;
    }
    .stButton>button:hover {
        background-color: #3d4f7c !important;
        border-color: #5a65a0 !important;
    }
    .stProgress>div>div>div {
        background-color: #4da6ff !important;
    }
    .stProgress>div {
        background-color: #2c3040 !important;
    }
    [data-testid="stMetricValue"] {
        color: #f0f0f0 !important;
    }
    [data-testid="stMetricDelta"] {
        color: #a0a0c0 !important;
    }
    .stAlert, [data-testid="stInfo"], [data-testid="stSuccess"],
    [data-testid="stWarning"], [data-testid="stError"] {
        background-color: #1e2130 !important;
        color: #f0f0f0 !important;
    }
    .stExpander {
        background-color: #1a1d28 !important;
    }
    .stExpander [data-testid="stExpanderDetails"] {
        background-color: #1e2130 !important;
    }
    [data-testid="stTabs"] [data-baseweb="tab-list"] {
        background-color: #161a24 !important;
    }
    [data-testid="stTabs"] button[data-baseweb="tab"] {
        color: #a0a0c0 !important;
    }
    [data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] {
        color: #4da6ff !important;
    }
    hr, .stDivider {
        border-color: #2c3040 !important;
    }
    input, textarea, select, .stTextInput input, .stDateInput input {
        background-color: #1a1d28 !important;
        color: #f0f0f0 !important;
        border-color: #3a3f50 !important;
    }
    .stDownloadButton>button {
        background-color: #1e5c3a !important;
        color: #f0f0f0 !important;
    }
    </style>
    """,
        unsafe_allow_html=True,
    )

# ---- 侧边栏 ----
with st.sidebar:
    # ---- 黑暗模式切换（on_change 回调，无需手动 rerun） ----
    st.toggle(
        "🌙 黑暗模式",
        key="dark_mode_toggle",
        on_change=_on_dark_mode_toggle,
    )

    st.divider()

    st.header("⚙️ 参数设置")

    # 基金选择
    st.subheader("📊 基金选择")
    fund_code = st.text_input(
        "基金代码",
        max_chars=6,
        help="输入6位基金代码，如 161725（招商中证白酒）",
        key="widget_fund_code",
    )

    # 快速选择（on_change 回调，自动同步基金代码，无需手动 rerun）
    quick_funds: dict = {
        "161725 - 招商中证白酒": "161725",
        "110011 - 易方达中小盘": "110011",
        "002610 - 博时黄金ETF联接A": "002610",
        "000001 - 华夏成长混合": "000001",
        "001632 - 天弘中证食品饮料ETF联接A": "001632",
    }
    st.selectbox(
        "快速选择",
        options=[""] + list(quick_funds.keys()),
        key="quick_select",
        on_change=_on_quick_select,
    )

    st.divider()

    # 回测参数
    st.subheader("⏱️ 回测参数")

    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input(
            "开始日期",
            min_value=datetime(2000, 1, 1),
            max_value=datetime.now(),
            key="widget_start_date",
        )
    with col2:
        end_date = st.date_input(
            "结束日期",
            min_value=datetime(2000, 1, 1),
            max_value=datetime.now(),
            key="widget_end_date",
        )

    invest_amount = st.number_input(
        "每期定投金额（元）",
        min_value=100,
        max_value=100000,
        step=100,
        help="每月定投的固定金额",
        key="widget_invest_amount",
    )

    invest_day = st.slider(
        "每月定投日",
        min_value=1,
        max_value=28,
        help="每月第几天定投（1-28日）",
        key="widget_invest_day",
    )

    fee_rate = st.number_input(
        "申购费率",
        min_value=0.0,
        max_value=0.05,
        step=0.0005,
        format="%.4f",
        help="基金申购费率，默认0.15%",
        key="widget_fee_rate",
    )

    st.divider()

    # 策略选择
    st.subheader("🎯 策略选择")
    run_normal = st.checkbox("普通定投", value=True)
    run_stop_profit = st.checkbox("止盈定投", value=True)
    if run_stop_profit:
        stop_profit = st.slider(
            "止盈线",
            min_value=0.05,
            max_value=1.0,
            value=0.20,
            step=0.05,
            format="%.0f%%",
            help="收益率达到此线则全部赎回",
        )
    run_value_avg = st.checkbox("价值平均策略", value=True)
    if run_value_avg:
        value_growth = st.number_input(
            "每月目标市值增长（元）",
            min_value=100,
            max_value=100000,
            value=1000,
            step=500,
        )
    run_ma_dynamic = st.checkbox("AI均线动态定投", value=True)
    if run_ma_dynamic:
        ma_period = st.selectbox(
            "均线周期",
            options=[60, 120, 250],
            index=2,
            help="交易日均线周期",
        )
        low_mult = st.slider(
            "低位加倍系数",
            min_value=1.0,
            max_value=5.0,
            value=2.0,
            step=0.5,
        )
        high_mult = st.slider(
            "高位减仓系数",
            min_value=0.0,
            max_value=1.0,
            value=0.5,
            step=0.25,
        )

    run_ma60 = st.checkbox("60日均线策略", value=True)
    if run_ma60:
        ma60_period = st.selectbox(
            "MA60周期",
            options=[60, 120, 250],
            index=0,
            help="60日均线周期（可改为120/250）",
            key="ma60_period",
        )

    run_macd = st.checkbox("MACD策略", value=True)
    if run_macd:
        col_macd1, col_macd2, col_macd3 = st.columns(3)
        with col_macd1:
            macd_fast = st.number_input(
                "快线周期", min_value=2, max_value=50, value=12, step=1, key="macd_fast"
            )
        with col_macd2:
            macd_slow = st.number_input(
                "慢线周期", min_value=5, max_value=100, value=26, step=1, key="macd_slow"
            )
        with col_macd3:
            macd_signal = st.number_input(
                "信号线周期", min_value=2, max_value=50, value=9, step=1, key="macd_signal"
            )

    run_rsi = st.checkbox("RSI策略", value=True)
    if run_rsi:
        col_rsi1, col_rsi2, col_rsi3 = st.columns(3)
        with col_rsi1:
            rsi_period = st.slider(
                "RSI周期", min_value=5, max_value=30, value=14, step=1, key="rsi_period"
            )
        with col_rsi2:
            rsi_oversold = st.slider(
                "超卖阈值", min_value=15, max_value=40, value=30, step=1, key="rsi_oversold"
            )
        with col_rsi3:
            rsi_overbought = st.slider(
                "超买阈值", min_value=60, max_value=85, value=70, step=1, key="rsi_overbought"
            )

    run_volatility = st.checkbox("波动率策略", value=True)
    if run_volatility:
        vol_period = st.slider(
            "波动率计算周期",
            min_value=5,
            max_value=60,
            value=20,
            step=5,
            key="vol_period",
            help="历史波动率的滚动窗口（交易日）",
        )

    run_ml_rf = st.checkbox("ML随机森林策略", value=True)
    if run_ml_rf:
        col_ml1, col_ml2, col_ml3 = st.columns(3)
        with col_ml1:
            ml_n_estimators = st.slider(
                "树的数量", min_value=50, max_value=500, value=100, step=50, key="ml_n"
            )
        with col_ml2:
            ml_max_depth = st.slider(
                "最大深度", min_value=3, max_value=15, value=6, step=1, key="ml_depth"
            )
        with col_ml3:
            ml_train_ratio = st.slider(
                "训练集占比", min_value=0.60, max_value=0.90, value=0.80, step=0.05,
                key="ml_train_ratio",
                help="前 N% 的数据用于训练，剩余用于测试",
            )

    st.divider()

    # ---- 实用工具 ----
    st.subheader("🔧 实用工具")

    # 1. 实时数据更新
    with st.expander("🔄 实时数据更新", expanded=False):
        st.markdown("更新当前基金的最新净值数据（清空缓存重拉）。")
        if st.button("🔄 更新最新数据", use_container_width=True, key="refresh_data_btn"):
            with st.spinner("正在更新数据..."):
                try:
                    # 清空该基金的缓存文件强制重拉
                    cache_file = os.path.join(os.path.dirname(__file__), "data", f"{fund_code}.csv")
                    if os.path.exists(cache_file):
                        os.remove(cache_file)
                    df_fresh = get_fund_data(
                        fund_code,
                        start_date="2015-01-01",
                        end_date=datetime.now().strftime("%Y-%m-%d"),
                    )
                    st.success(
                        f"✅ 数据已更新！最新日期: {df_fresh['日期'].max().strftime('%Y-%m-%d')}"
                    )
                except Exception as e:
                    st.error(f"更新失败: {e}")

    # 2. 定投计算器
    with st.expander("🧮 定投计算器", expanded=False):
        st.markdown("计算达成目标所需的每月定投金额。")
        calc_target = st.number_input(
            "目标总金额（元）",
            min_value=10000,
            max_value=50000000,
            value=1000000,
            step=10000,
            key="calc_target",
        )
        calc_years = st.slider("定投年限", min_value=1, max_value=40, value=20, key="calc_years")
        calc_annual = st.slider(
            "预期年化收益率",
            min_value=1.0,
            max_value=30.0,
            value=8.0,
            step=0.5,
            format="%.1f%%",
            key="calc_annual",
        )
        if calc_annual > 0 and calc_years > 0:
            r = calc_annual / 100 / 12  # 月利率
            n = calc_years * 12
            # PMT 公式: PMT = FV * r / ((1+r)^n - 1)
            monthly_pmt = calc_target * r / ((1 + r) ** n - 1)
            total_invest = monthly_pmt * n
            st.metric("每月需定投", f"CNY {monthly_pmt:,.0f}")
            st.caption(
                f"总投入: CNY {total_invest:,.0f}  |  总收益: CNY {calc_target - total_invest:+,.0f}"
            )

    # 3. 风险预警（仅在回测完成后显示）
    if "backtest_df" in st.session_state and st.session_state.backtest_df is not None:
        with st.expander("⚠️ 风险预警", expanded=True):
            df_warn = st.session_state.backtest_df
            if len(df_warn) >= 250:
                ma250 = df_warn["单位净值"].rolling(250).mean().iloc[-1]
                latest_price = df_warn["单位净值"].iloc[-1]
                ratio = latest_price / ma250 if ma250 > 0 else 1
                latest_date = df_warn["日期"].iloc[-1].strftime("%Y-%m-%d")
                st.caption(
                    f"📅 最新日期: {latest_date}  |  最新净值: {latest_price:.4f}  |  MA250: {ma250:.4f}  |  比值: {ratio:.2%}"
                )
                if ratio > 1.20:
                    st.error(
                        f"🔴 **高位风险！** 当前价格是250日均线的 {ratio:.0%}，远超120%阈值。建议**减少定投金额**或暂停定投，等待回归均线。"
                    )
                elif ratio < 0.80:
                    st.success(
                        f"🟢 **低位机会！** 当前价格仅为250日均线的 {ratio:.0%}，低于80%阈值。建议**加大定投金额**，积极低位吸筹。"
                    )
                elif ratio > 1.10:
                    st.warning(
                        f"🟡 **偏高区间** — 价格/MA250 = {ratio:.0%}，处于均线上方，建议保持正常定投或适当减量。"
                    )
                elif ratio < 0.90:
                    st.info(
                        f"🔵 **偏低区间** — 价格/MA250 = {ratio:.0%}，处于均线下方，可适当加大投入。"
                    )
                else:
                    st.info(f"⚪ **正常区间** — 价格/MA250 = {ratio:.0%}，价格在均线附近运行。")
            else:
                st.caption("数据不足（需至少250个交易日），无法计算250日均线。")

    # 4. 历史回测快照
    with st.expander("📸 历史回测快照", expanded=False):
        st.caption("保存当前回测参数和结果，支持一键恢复。")

        col_s1, col_s2 = st.columns(2)
        with col_s1:
            snap_name = st.text_input(
                "快照名称",
                value="",
                placeholder="如: 白酒2021-2026",
                key="snap_name",
                label_visibility="collapsed",
            )
        with col_s2:
            if st.button("💾 保存当前回测", use_container_width=True, key="save_snapshot_btn"):
                if "backtest_results" in st.session_state and st.session_state.backtest_results:
                    name = snap_name.strip() or datetime.now().strftime("%m/%d %H:%M")
                    snapshot = {
                        "name": name,
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "fund_code": fund_code,
                        "start_date": start_date.strftime("%Y-%m-%d"),
                        "end_date": end_date.strftime("%Y-%m-%d"),
                        "invest_amount": invest_amount,
                        "invest_day": invest_day,
                        "fee_rate": fee_rate,
                        "strategies": [
                            {"name": n, "sharpe": r.sharpe_ratio, "annual": r.annual_return}
                            for r, n in zip(
                                st.session_state.backtest_results, st.session_state.backtest_names
                            )
                        ],
                    }
                    st.session_state.snapshots.insert(0, snapshot)
                    st.success(f"✅ 快照「{name}」已保存！")
                    st.rerun()
                else:
                    st.warning("请先运行回测后再保存快照。")

        # 显示已保存的快照
        if st.session_state.snapshots:
            for i, snap in enumerate(st.session_state.snapshots):
                with st.container():
                    cols = st.columns([4, 2, 2])
                    with cols[0]:
                        st.markdown(f"**{snap['name']}**  ")
                        st.caption(
                            f"{snap['time']} | {snap['fund_code']} | {snap['start_date']}~{snap['end_date']}"
                        )
                    with cols[1]:
                        best = max(snap["strategies"], key=lambda s: s["sharpe"])
                        st.caption(f"最佳: {best['name']} ({best['sharpe']:.2f})")
                    with cols[2]:
                        if st.button("🗑️", key=f"del_snap_{i}", help="删除此快照"):
                            st.session_state.snapshots.pop(i)
                            st.rerun()
                        if st.button("📂", key=f"restore_snap_{i}", help="恢复此回测参数"):
                            st.session_state["_restore_snapshot"] = snap
                            st.rerun()
        else:
            st.caption("暂无保存的快照。回测完成后点击「保存当前回测」。")

    st.divider()

    # 运行按钮
    run_btn = st.button("🚀 运行回测", type="primary", use_container_width=True)

    st.divider()
    st.caption("💡 提示：支持A股公募基金代码，数据来源于天天基金网")

# ---- 主区域 ----
# 使用持久化标志确保点击PDF/下载/Tab切换后结果不丢失
# has_backtest_run 在回测完成后设为 True，仅 st.stop() 或手动刷新页面才重置
if not run_btn and not st.session_state.has_backtest_run:
    # 显示欢迎页面（首次加载 或 无回测结果时）
    st.info("👈 请在左侧设置参数后点击 **运行回测** 按钮")

    # 展示使用说明
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            """
        ### 📋 系统功能
        - **数据获取**：自动从天天基金网获取历史净值
        - **多策略回测**：普通定投、止盈定投、价值平均、AI动态
        - **风险分析**：夏普比率、最大回撤、波动率、胜率
        - **参数优化**：网格搜索最优策略参数
        - **可视化**：收益曲线、回撤图、热力图、雷达图
        """
        )
    with col2:
        st.markdown(
            """
        ### 🔧 策略说明
        | 策略 | 特点 |
        |------|------|
        | 普通定投 | 定期定额，最简单 |
        | 止盈定投 | 达到目标收益全部赎回 |
        | 价值平均 | 动态调整使市值匀速增长 |
        | AI均线动态 | 根据250日均线智能调整金额 |
        | 60日均线 | 基于60日均线中期趋势调整 |
        | MACD | 基于MACD柱强度判断买卖区间 |
        | RSI | 基于RSI超买超卖信号决策 |
        | 波动率 | 恐慌时加仓，平静时减仓 |
        | ML随机森林 | 机器学习预测涨跌概率智能调仓 |
        """
        )

else:
    # ---- 数据加载 ----
    with st.spinner(f"正在获取基金 {fund_code} 的历史净值数据..."):
        try:
            df = get_fund_data(
                fund_code,
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
            )
        except Exception as e:
            st.error(f"数据获取失败: {e}")
            st.stop()

    st.success(f"✅ 数据加载成功！共 {len(df):,} 条净值记录")
    st.session_state.backtest_df = df  # 存储供风险预警等工具使用

    # 数据预览
    with st.expander("📋 数据预览", expanded=False):
        st.dataframe(df.head(20), use_container_width=True)
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(
                "日期范围",
                f"{df['日期'].min().strftime('%Y-%m-%d')} ~ {df['日期'].max().strftime('%Y-%m-%d')}",
            )
        with col2:
            st.metric("数据条数", len(df))
        with col3:
            if "累计净值" in df.columns and len(df) > 1:
                change = df["累计净值"].iloc[-1] / df["累计净值"].iloc[0] - 1
                st.metric("区间涨跌", f"{change:+.2%}")

    # ---- 创建回测引擎 ----
    bt = FundBacktest(
        df,
        invest_amount=invest_amount,
        invest_day=invest_day,
        fee_rate=fee_rate,
    )

    # ---- 运行策略 ----
    # 关键：仅当用户显式点击「运行回测」时重新计算策略
    # 点击 PDF/下载/Tab 等交互触发 rerun 时，直接从 session_state 读缓存，跳过计算
    _should_recompute = run_btn or not st.session_state.has_backtest_run

    if not _should_recompute:
        results = st.session_state.backtest_results or []
        names = st.session_state.backtest_names or []

    if _should_recompute:
        results = []
        names = []

        total_steps = sum(
        [
            run_normal,
            run_stop_profit,
            run_value_avg,
            run_ma_dynamic,
            run_ma60,
            run_macd,
            run_rsi,
            run_volatility,
            run_ml_rf,
        ]
    )
    if _should_recompute:
        step_state = {"current": 0}
        st.markdown("#### ⏳ 回测进度")
        main_progress = st.progress(0, text=f"准备运行 {total_steps} 个策略...")
        status_text = st.empty()  # 文本占位符：替代 st.status，兼容所有 Streamlit 版本
    else:
        step_state = {"current": 0}
        total_steps = 1
        main_progress = st.empty()
        status_text = st.empty()

    def _run_one(method, *args, **kwargs):
        """执行一个策略并更新进度；异常时自动兜底，确保进度条不卡死。"""
        if not _should_recompute:
            return None  # 非计算帧：跳过所有策略执行
        try:
            r = method(*args, **kwargs)
            return r
        except Exception as e:
            status_text.markdown(f"✗ {method.__name__} 失败: {e}")
            return None
        finally:
            step_state['current'] += 1
            if main_progress is not None:
                main_progress.progress(
                    step_state['current'] / max(total_steps, 1),
                    text=f"已完成 {step_state['current']}/{total_steps} 个策略",
                )

    if run_normal:
        status_text.markdown(f"🔄 运行普通定投... ({step_state['current'] + 1}/{total_steps})"
        )
        r = _run_one(bt.run_normal_dca)
        if r is not None:
            results.append(r)
            names.append("普通定投")
            status_text.markdown(f"✓ 普通定投完成 — 年化: {r.annual_return:+.2%}")

    if run_stop_profit:
        status_text.markdown(f"🔄 运行止盈定投... ({step_state['current'] + 1}/{total_steps})"
        )
        r = _run_one(bt.run_stop_profit_dca, stop_profit=stop_profit)
        if r is not None:
            results.append(r)
            names.append(f"止盈定投({stop_profit:.0%})")
            status_text.markdown(
                f"✓ 止盈定投完成 — 年化: {r.annual_return:+.2%} | "
                f"止盈 {len(r.stop_profit_events)} 次"
            )

    if run_value_avg:
        status_text.markdown(f"🔄 运行价值平均策略... ({step_state['current'] + 1}/{total_steps})"
        )
        r = _run_one(bt.run_value_average, target_growth=value_growth)
        if r is not None:
            results.append(r)
            names.append(f"价值平均(+{value_growth:.0f}/月)")
            status_text.markdown(f"✓ 价值平均完成 — 年化: {r.annual_return:+.2%}")

    if run_ma_dynamic:
        status_text.markdown(f"🔄 运行AI均线动态定投... ({step_state['current'] + 1}/{total_steps})"
        )
        r = _run_one(
            bt.run_ma_dynamic_dca,
            ma_period=ma_period, low_multiplier=low_mult, high_multiplier=high_mult,
        )
        if r is not None:
            results.append(r)
            names.append(f"MA{ma_period}动态定投")
            status_text.markdown(f"✓ AI均线动态完成 — 年化: {r.annual_return:+.2%}")

    if run_ma60:
        status_text.markdown(f"🔄 运行60日均线策略... ({step_state['current'] + 1}/{total_steps})"
        )
        r = _run_one(bt.run_ma60_dca, ma_period=ma60_period)
        if r is not None:
            results.append(r)
            names.append(f"MA{ma60_period}均线定投")
            status_text.markdown(f"✓ 60日均线完成 — 年化: {r.annual_return:+.2%}")

    if run_macd:
        status_text.markdown(f"🔄 运行MACD策略... ({step_state['current'] + 1}/{total_steps})"
        )
        r = _run_one(bt.run_macd_dca, fast=macd_fast, slow=macd_slow, signal=macd_signal)
        if r is not None:
            results.append(r)
            names.append("MACD定投")
            status_text.markdown(f"✓ MACD完成 — 年化: {r.annual_return:+.2%}")

    if run_rsi:
        status_text.markdown(f"🔄 运行RSI策略... ({step_state['current'] + 1}/{total_steps})")
        r = _run_one(
            bt.run_rsi_dca, period=rsi_period, oversold=rsi_oversold, overbought=rsi_overbought,
        )
        if r is not None:
            results.append(r)
            names.append("RSI定投")
            status_text.markdown(f"✓ RSI完成 — 年化: {r.annual_return:+.2%}")

    if run_volatility:
        status_text.markdown(f"🔄 运行波动率策略... ({step_state['current'] + 1}/{total_steps})"
        )
        r = _run_one(bt.run_volatility_dca, vol_period=vol_period)
        if r is not None:
            results.append(r)
            names.append("波动率定投")
            status_text.markdown(f"✓ 波动率完成 — 年化: {r.annual_return:+.2%}")

    if run_ml_rf:
        status_text.markdown(f"🔄 运行ML随机森林策略... ({step_state['current'] + 1}/{total_steps})"
        )
        r = _run_one(
            run_ml_rf_dca, bt=bt, n_estimators=ml_n_estimators,
            max_depth=ml_max_depth, train_ratio=ml_train_ratio,
        )
        if r is not None:
            results.append(r)
            names.append(f"ML随机森林(RF{ml_n_estimators})")
            status_text.markdown(
                f"✓ ML随机森林完成 — 年化: {r.annual_return:+.2%} | "
                f"Train Acc: {r.ml_meta['train_accuracy']:.2%}"
            )

    if _should_recompute:
        main_progress.progress(1.0, text=f"✅ 回测全部完成！共运行 {len(results)} 个策略")
        status_text.markdown(f"✅ 回测全部完成！共运行 {len(results)} 个策略")

        # 存储到 session_state 供风险预警、快照等工具使用
        st.session_state.backtest_results = results
        st.session_state.backtest_names = names
        st.session_state.has_backtest_run = True  # 持久化标志：点击PDF/下载/切换Tab不会丢失结果

    if not results:
        st.error("未选择任何策略！")
        st.stop()

    # ---- 结果展示 ----
    st.markdown("---")
    st.header("📊 回测结果")

    # 核心指标卡片
    cols = st.columns(len(results))
    for i, (result, name) in enumerate(zip(results, names)):
        with cols[i]:
            st.metric(
                label=f"**{name}**",
                value=f"{result.annual_return:+.2%}",
                delta=f"年化收益率",
                delta_color="normal",
            )
            st.caption(f"总收益: {result.total_profit:+,.0f}元 | 夏普: {result.sharpe_ratio:.2f}")

    # ---- 图表展示 ----
    st.markdown("---")
    st.header("📈 可视化分析")

    tab_comparison, tab_returns, tab_drawdown, tab_monthly, tab_radar, tab_trades = st.tabs(
        ["📋 策略对比", "📈 收益曲线", "📉 回撤分析", "🔥 月度收益", "🎯 风险雷达", "📑 交易记录"]
    )

    # ====== Tab 1: 策略对比 ======
    with tab_comparison:
        # 对比表格
        st.subheader("📋 策略对比表")
        table_data = []
        for result, name in zip(results, names):
            table_data.append(
                {
                    "策略": name,
                    "总投入(元)": f"{result.total_invest:,.0f}",
                    "最终资产(元)": f"{result.total_asset:,.0f}",
                    "总收益(元)": f"{result.total_profit:+,.0f}",
                    "总收益率": f"{result.total_return:+.2%}",
                    "年化收益率": f"{result.annual_return:+.2%}",
                    "夏普比率": f"{result.sharpe_ratio:.4f}",
                    "最大回撤": f"{result.max_drawdown:.2%}",
                    "波动率": f"{result.volatility:.2%}",
                    "胜率": f"{result.win_rate:.1%}",
                    "最大连亏月": f"{result.max_loss_months}",
                    "交易次数": len(result.trades),
                }
            )
        st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)

        # 导出按钮
        st.markdown("#### 📥 导出结果")
        summary_data = []
        for result, name in zip(results, names):
            summary_data.append(
                {
                    "策略": name,
                    "总投入": result.total_invest,
                    "总资产": result.total_asset,
                    "总收益": result.total_profit,
                    "总收益率": result.total_return,
                    "年化收益率": result.annual_return,
                    "夏普比率": result.sharpe_ratio,
                    "最大回撤": result.max_drawdown,
                    "波动率": result.volatility,
                    "胜率": result.win_rate,
                    "最大连亏月": result.max_loss_months,
                }
            )
        summary_df = pd.DataFrame(summary_data)
        csv_summary = summary_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="📥 下载策略对比汇总 (CSV)",
            data=csv_summary,
            file_name=f"backtest_summary_{fund_code}_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )

    # ====== Tab 2: 收益曲线 ======
    with tab_returns:
        st.subheader("累计收益率对比")
        fig = plot_cumulative_returns(results, names)
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("总资产增长")
        fig2 = plot_asset_growth(results, names)
        st.plotly_chart(fig2, use_container_width=True)

    # ====== Tab 3: 回撤分析 ======
    with tab_drawdown:
        st.subheader("回撤曲线")
        fig = plot_drawdowns(results, names)
        st.plotly_chart(fig, use_container_width=True)

    # ====== Tab 4: 月度收益 ======
    with tab_monthly:
        st.subheader("月度收益热力图")
        selected_heatmap = st.selectbox(
            "选择策略",
            options=names,
            key="heatmap_select",
        )
        idx = names.index(selected_heatmap)
        fig = plot_monthly_heatmap(results[idx], selected_heatmap)
        st.plotly_chart(fig, use_container_width=True)

    # ====== Tab 5: 风险雷达 ======
    with tab_radar:
        if len(results) >= 2:
            st.subheader("风险收益雷达图")
            fig = plot_risk_radar(results, names)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("需要至少2个策略才能生成雷达图")

    # ====== Tab 6: 交易记录 ======
    with tab_trades:
        st.subheader("交易记录")
        selected_trades = st.selectbox(
            "选择策略查看详细交易记录",
            options=names,
            key="trades_select",
        )
        idx = names.index(selected_trades)
        result = results[idx]

        if result.trades is not None and len(result.trades) > 0:
            st.dataframe(result.trades, use_container_width=True, hide_index=True)

            # 下载按钮
            csv = result.trades.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                label=f"📥 下载 {selected_trades} 交易记录 (CSV)",
                data=csv,
                file_name=f"trades_{selected_trades}_{fund_code}.csv",
                mime="text/csv",
            )
        else:
            st.info("无交易记录")

        # 止盈事件
        stop_events_found = False
        for result_i, name_i in zip(results, names):
            if result_i.stop_profit_events and len(result_i.stop_profit_events) > 0:
                stop_events_found = True
                with st.expander(
                    f"🎉 {name_i} - 止盈事件 ({len(result_i.stop_profit_events)}次)", expanded=False
                ):
                    events_df = pd.DataFrame(result_i.stop_profit_events)
                    if "日期" in events_df.columns:
                        events_df["日期"] = events_df["日期"].apply(
                            lambda x: x.strftime("%Y-%m-%d") if hasattr(x, "strftime") else str(x)
                        )
                    st.dataframe(events_df, use_container_width=True, hide_index=True)
        if not stop_events_found:
            st.info("止盈事件：无（本轮回测未触发止盈条件）")

    # ---- 一键生成 PDF 报告 ----
    st.markdown("---")
    st.subheader("📄 一键生成 PDF 报告")

    # 空结果校验：使用持久化的 session_state 数据（不会在 rerun 时丢失）
    saved_results = st.session_state.get("backtest_results")
    saved_names = st.session_state.get("backtest_names")
    if not saved_results:
        st.info("请先运行回测，再生成 PDF 报告。")
    else:
        st.markdown(
            "自动生成包含回测基本信息、策略对比表、收益曲线、回撤图、"
            "月度热力图和风险指标汇总的完整 PDF 报告。"
        )

        # === 按钮 1：生成 PDF（写入 session_state） ===
        if st.button(
            "📥 生成 PDF 报告",
            type="secondary",
            use_container_width=True,
            key="pdf_generate_btn",
        ):
            with st.spinner("正在生成 PDF 报告（含图表）..."):
                import traceback

                try:
                    pdf_bytes = generate_pdf_report(
                        fund_code=fund_code,
                        fund_name="",
                        start_date=start_date.strftime("%Y-%m-%d"),
                        end_date=end_date.strftime("%Y-%m-%d"),
                        invest_amount=invest_amount,
                        invest_day=invest_day,
                        fee_rate=fee_rate,
                        results=saved_results,
                        names=saved_names,
                    )
                    st.session_state._pdf_bytes = pdf_bytes
                    st.session_state._pdf_name = (
                        f"fund_dca_report_{fund_code}_"
                        f"{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
                    )
                    st.success(
                        f"✅ PDF 报告生成成功！({len(pdf_bytes) / 1024:.0f} KB) — "
                        f"请点击下方下载按钮"
                    )
                except Exception as e:
                    traceback.print_exc()
                    st.session_state._pdf_bytes = None
                    st.error(f"PDF 生成失败: {e}")

        # === 按钮 2：下载 PDF（从 session_state 读取，与生成按钮平级，不受 st.button 条件块影响） ===
        if st.session_state.get("_pdf_bytes"):
            st.download_button(
                label="📥 下载 PDF 报告",
                data=st.session_state._pdf_bytes,
                file_name=st.session_state.get("_pdf_name", "fund_dca_report.pdf"),
                mime="application/pdf",
                key="pdf_download_btn",
                use_container_width=True,
            )

    # ---- 参数优化建议（Optuna贝叶斯优化） ----
    if run_ma_dynamic and len(results) >= 2:
        st.markdown("---")
        st.header("🤖 Optuna贝叶斯参数优化")

        # 优化参数设置
        col_opt1, col_opt2, col_opt3 = st.columns(3)
        with col_opt1:
            n_trials = st.slider(
                "优化轮数 (n_trials)",
                20,
                300,
                80,
                step=10,
                help="贝叶斯优化迭代次数，越多越精确但越慢",
            )
        with col_opt2:
            train_start = st.text_input("训练集开始", value="2018-01-01", key="train_start")
        with col_opt3:
            train_end = st.text_input("训练集结束", value="2020-12-31", key="train_end")

        col_test1, col_test2 = st.columns(2)
        with col_test1:
            test_start = st.text_input("测试集开始", value="2021-01-01", key="test_start")
        with col_test2:
            test_end = st.text_input("测试集结束", value="2023-12-31", key="test_end")

        if st.button("🚀 启动贝叶斯优化", type="primary", key="optuna_btn"):
            with st.spinner(f"正在使用 Optuna TPE 贝叶斯优化（{n_trials} 轮）..."):
                try:
                    opt_result = bt.optimize_ma_bayesian(
                        n_trials=n_trials,
                        train_start=train_start,
                        train_end=train_end,
                        test_start=test_start,
                        test_end=test_end,
                    )

                    st.success(
                        f"✅ 优化完成！最佳夏普比率 = {opt_result['train_sharpe']:.4f} | "
                        f"耗时 {n_trials} 轮贝叶斯搜索"
                    )

                    # ---- 最优参数 + Train/Test 对比 ----
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("#### 🎯 最优参数")
                        params_df = pd.DataFrame([opt_result["best_params"]])
                        st.dataframe(params_df, use_container_width=True, hide_index=True)

                    with col2:
                        st.markdown("#### 📊 训练集 vs 测试集")
                        train_r = opt_result["train_result"]
                        test_r = opt_result["test_result"]
                        compare_df = pd.DataFrame(
                            [
                                {
                                    "指标": "夏普比率",
                                    "训练集": f"{train_r.sharpe_ratio:.4f}",
                                    "测试集": f"{test_r.sharpe_ratio:.4f}",
                                },
                                {
                                    "指标": "年化收益率",
                                    "训练集": f"{train_r.annual_return:+.2%}",
                                    "测试集": f"{test_r.annual_return:+.2%}",
                                },
                                {
                                    "指标": "总收益率",
                                    "训练集": f"{train_r.total_return:+.2%}",
                                    "测试集": f"{test_r.total_return:+.2%}",
                                },
                                {
                                    "指标": "最大回撤",
                                    "训练集": f"{train_r.max_drawdown:.2%}",
                                    "测试集": f"{test_r.max_drawdown:.2%}",
                                },
                                {
                                    "指标": "波动率",
                                    "训练集": f"{train_r.volatility:.2%}",
                                    "测试集": f"{test_r.volatility:.2%}",
                                },
                            ]
                        )
                        st.dataframe(compare_df, use_container_width=True, hide_index=True)

                        # 过拟合检测
                        train_sharpe = opt_result["train_sharpe"]
                        test_sharpe = opt_result["test_sharpe"]
                        gap = train_sharpe - test_sharpe
                        if gap > 0.3:
                            st.warning(f"⚠️ 过拟合风险较高 (Train-Test Sharpe gap: {gap:.4f})")
                        elif gap > 0.1:
                            st.info(f"📝 轻微性能差异 (Train-Test Sharpe gap: {gap:.4f})")
                        else:
                            st.success(f"✅ 泛化良好 (Train-Test Sharpe gap: {gap:.4f})")

                    # ---- 敏感性分析图 ----
                    st.markdown("#### 🔬 参数敏感性分析")
                    fig = plot_optimization_analysis(
                        opt_result["study"],
                        title=f"MA Dynamic Optimization — {train_start}~{train_end} (train) "
                        f"→ {test_start}~{test_end} (test)",
                    )
                    st.plotly_chart(fig, use_container_width=True)

                    # ---- Trials 详情 ----
                    with st.expander("📋 查看全部 Trial 详情", expanded=False):
                        st.dataframe(
                            opt_result["trials_df"].sort_values("sharpe_ratio", ascending=False),
                            use_container_width=True,
                            hide_index=True,
                        )

                except Exception as e:
                    st.error(f"优化失败: {e}")
                    st.info(
                        "提示：请确保数据范围包含训练集和测试集的日期。可尝试使用 基金代码 000001 或扩大日期范围。"
                    )

    # ---- ML 模型信息展示 ----
    for result, name in zip(results, names):
        if hasattr(result, "ml_meta") and result.ml_meta:
            with st.expander(f"🤖 {name} — 模型详情", expanded=False):
                meta = result.ml_meta
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    st.metric("训练集准确率", f"{meta['train_accuracy']:.2%}")
                with col_b:
                    st.metric("测试集准确率", f"{meta['test_accuracy']:.2%}")
                with col_c:
                    st.metric("特征数量", meta["feature_count"])
                st.caption(
                    f"模型: {meta['model_type']} | 树数: {meta['n_estimators']} | "
                    f"深度: {meta['max_depth']} | 训练集占比: {meta['train_ratio']:.0%} | "
                    f"预测周期: {meta['lookback_horizon']} 交易日"
                )
                st.markdown("**Top 5 重要特征:**")
                top_feat_df = pd.DataFrame(
                    [(k, f"{v:.4f}") for k, v in meta["top_features"].items()],
                    columns=["特征", "重要性"],
                )
                st.dataframe(top_feat_df, use_container_width=True, hide_index=True)

    st.success("✅ 回测完成！可切换Tab查看不同分析维度。")

# ---- 页脚 ----
st.markdown("---")
st.caption(
    "📈 Fund DCA Backtest System | " "数据来源: 天天基金网 | " "仅供学习研究使用，不构成投资建议"
)
