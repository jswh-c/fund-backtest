"""
PDF 报告生成模块
使用 reportlab 生成包含回测结果、图表和风险指标的完整 PDF 报告。
图表使用 matplotlib 渲染（无需 kaleido/chrome 依赖）。
"""
import os
import io
from datetime import datetime
from typing import List

import pandas as pd
import numpy as np

# ---- Matplotlib: 非交互后端，中文支持 ----
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.font_manager import FontProperties

# 注册中文字体（跨平台：Linux → macOS → Windows）
_CN_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",   # Linux (apt fonts-wqy-microhei)
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",  # Linux (Noto)
    "/System/Library/Fonts/PingFang.ttc",                # macOS
    "C:/Windows/Fonts/msyh.ttc",                         # Windows
    "C:/Windows/Fonts/simhei.ttf",                       # Windows (fallback)
    "C:/Windows/Fonts/simsun.ttc",                       # Windows (system default)
]
_CN_FP = FontProperties()  # default
for _path in _CN_FONT_CANDIDATES:
    if os.path.exists(_path):
        _CN_FP = FontProperties(fname=_path)
        break

# ---- ReportLab ----
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
    PageBreak,
    HRFlowable,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from backtest import BacktestResult

# ================================================================
# 中文字体注册 (reportlab)
# ================================================================
# 注册 reportlab 中文字体（跨平台自动检测）
_FONT_REGULAR_CANDIDATES = [
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",   # Linux
    "/System/Library/Fonts/PingFang.ttc",                # macOS
    "C:/Windows/Fonts/msyh.ttc",                         # Windows
    "C:/Windows/Fonts/simsun.ttc",                       # Windows (system default)
]
_FONT_BOLD_CANDIDATES = [
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",   # Linux (same font for bold)
    "/System/Library/Fonts/PingFang.ttc",                # macOS
    "C:/Windows/Fonts/msyhbd.ttc",                       # Windows
]

CN_FONT = "Helvetica"
CN_FONT_BOLD = "Helvetica"

for _path in _FONT_REGULAR_CANDIDATES:
    if os.path.exists(_path):
        pdfmetrics.registerFont(TTFont("YaHei", _path))
        CN_FONT = "YaHei"
        break

for _path in _FONT_BOLD_CANDIDATES:
    if os.path.exists(_path):
        pdfmetrics.registerFont(TTFont("YaHeiBold", _path))
        CN_FONT_BOLD = "YaHeiBold"
        break

if CN_FONT_BOLD == "Helvetica":
    CN_FONT_BOLD = CN_FONT  # fallback to regular if no bold found

# ================================================================
# 颜色方案
# ================================================================
PRIMARY = HexColor("#1a5276")
SECONDARY = HexColor("#2e86c1")
LIGHT_BG = HexColor("#f2f4f4")
TABLE_HEADER = HexColor("#2c3e50")
TABLE_ROW_ALT = HexColor("#eaf2f8")
BORDER = HexColor("#bdc3c7")

PAGE_W, PAGE_H = A4

# Matplotlib 配色
MPL_COLORS = [
    "#5470C6",
    "#91CC75",
    "#FAC858",
    "#EE6666",
    "#73C0DE",
    "#3BA272",
    "#FC8452",
    "#9A60B4",
    "#EA7CCC",
]

# ================================================================
# ReportLab 样式
# ================================================================
style_h1 = ParagraphStyle(
    "CN_H1",
    fontName=CN_FONT_BOLD,
    fontSize=16,
    leading=22,
    textColor=PRIMARY,
    spaceBefore=18,
    spaceAfter=10,
)
style_h2 = ParagraphStyle(
    "CN_H2",
    fontName=CN_FONT_BOLD,
    fontSize=13,
    leading=18,
    textColor=SECONDARY,
    spaceBefore=12,
    spaceAfter=6,
)
style_body = ParagraphStyle(
    "CN_Body",
    fontName=CN_FONT,
    fontSize=10,
    leading=16,
    textColor=HexColor("#2c3e50"),
    spaceAfter=6,
)
style_small = ParagraphStyle(
    "CN_Small", fontName=CN_FONT, fontSize=8, leading=12, textColor=HexColor("#95a5a6")
)
style_subtitle = ParagraphStyle(
    "CN_Subtitle",
    fontName=CN_FONT,
    fontSize=12,
    leading=16,
    alignment=TA_CENTER,
    textColor=HexColor("#7f8c8d"),
    spaceAfter=20,
)


def _section_header(text):
    return [
        Paragraph(text, style_h1),
        HRFlowable(width="100%", thickness=1, color=BORDER, spaceAfter=10),
    ]


# ================================================================
# Matplotlib 图表 → PNG bytes
# ================================================================
MPL_DPI = 150
IMG_W_INCH = 8.0  # 适合 A4 宽度
IMG_H_INCH = 4.0


def _fig2bytes(fig, dpi=MPL_DPI):
    """matplotlib Figure → PNG bytes"""
    buf = io.BytesIO()
    fig.savefig(
        buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white", edgecolor="none"
    )
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def _fig2image(fig, dpi=MPL_DPI):
    """matplotlib Figure → reportlab Image"""
    img_bytes = _fig2bytes(fig, dpi)
    buf = io.BytesIO(img_bytes)
    img_width = PAGE_W - 40 * mm
    img_height = img_width * (IMG_H_INCH / IMG_W_INCH)
    return Image(buf, width=img_width, height=img_height)


def _plot_returns_png(results, names):
    """累计收益率曲线 → PNG bytes"""
    fig, ax = plt.subplots(figsize=(IMG_W_INCH, IMG_H_INCH))
    ax.axhline(y=0, color="gray", linewidth=0.8, linestyle="--", alpha=0.6)

    for i, (r, n) in enumerate(zip(results, names)):
        if r.daily_values is None or len(r.daily_values) == 0:
            continue
        dv = r.daily_values
        color = MPL_COLORS[i % len(MPL_COLORS)]
        ax.plot(
            dv["日期"],
            dv["收益率"] * 100,
            linewidth=1.5,
            color=color,
            label=f"{n} ({r.annual_return:+.2%})",
        )

    ax.set_title(
        "Cumulative Return Comparison", fontproperties=_CN_FP, fontsize=14, fontweight="bold"
    )
    ax.set_xlabel("Date", fontproperties=_CN_FP, fontsize=10)
    ax.set_ylabel("Cumulative Return (%)", fontproperties=_CN_FP, fontsize=10)
    ax.legend(loc="upper left", prop=_CN_FP, fontsize=8, framealpha=0.8)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f%%"))
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return _fig2bytes(fig)


def _plot_drawdown_png(results, names):
    """回撤曲线 → PNG bytes"""
    fig, ax = plt.subplots(figsize=(IMG_W_INCH, IMG_H_INCH))

    for i, (r, n) in enumerate(zip(results, names)):
        if r.daily_values is None or len(r.daily_values) == 0:
            continue
        dv = r.daily_values
        cummax = dv["总资产"].cummax()
        dd = (dv["总资产"] - cummax) / cummax.replace(0, np.nan) * 100
        color = MPL_COLORS[i % len(MPL_COLORS)]
        ax.fill_between(dv["日期"], dd, 0, alpha=0.08, color=color)
        ax.plot(
            dv["日期"], dd, linewidth=1.5, color=color, label=f"{n} (Max: {r.max_drawdown:.2%})"
        )

    ax.set_title("Drawdown Analysis", fontproperties=_CN_FP, fontsize=14, fontweight="bold")
    ax.set_xlabel("Date", fontproperties=_CN_FP, fontsize=10)
    ax.set_ylabel("Drawdown (%)", fontproperties=_CN_FP, fontsize=10)
    ax.legend(loc="lower left", prop=_CN_FP, fontsize=8, framealpha=0.8)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f%%"))
    ax.grid(True, alpha=0.3)
    ax.invert_yaxis()
    fig.tight_layout()
    return _fig2bytes(fig)


def _plot_heatmap_png(result, name):
    """月度收益热力图 → PNG bytes"""
    if result is None or result.daily_values is None or len(result.daily_values) == 0:
        return None

    dv = result.daily_values.copy()
    dv["年份"] = dv["日期"].dt.year
    dv["月份"] = dv["日期"].dt.month

    monthly = (
        dv.groupby(["年份", "月份"])
        .agg(
            总资产=("总资产", "last"),
            累计投入=("累计投入", "last"),
        )
        .reset_index()
    )
    monthly["月度收益率"] = monthly.groupby("年份")["总资产"].pct_change()

    pivot = monthly.pivot_table(values="月度收益率", index="年份", columns="月份", aggfunc="first")
    # 补齐缺失月份
    for m in range(1, 13):
        if m not in pivot.columns:
            pivot[m] = np.nan
    pivot = pivot[sorted(pivot.columns)]

    years = pivot.index.tolist()
    months = list(range(1, 13))
    data = pivot.values * 100  # 转为百分比

    fig, ax = plt.subplots(figsize=(IMG_W_INCH, IMG_H_INCH * 0.7))
    cmap = plt.cm.RdYlGn
    im = ax.imshow(data, aspect="auto", cmap=cmap, vmin=-15, vmax=15)

    ax.set_xticks(range(12))
    ax.set_xticklabels([f"M{m}" for m in months], fontsize=9)
    ax.set_yticks(range(len(years)))
    ax.set_yticklabels([str(y) for y in years], fontsize=9)

    # 在每个单元格中标注数值
    for yi in range(len(years)):
        for mi in range(12):
            val = data[yi, mi]
            if not np.isnan(val):
                text_color = "white" if abs(val) > 8 else "black"
                ax.text(
                    mi, yi, f"{val:.1f}%", ha="center", va="center", fontsize=7, color=text_color
                )

    ax.set_title(
        f"Monthly Return Heatmap — {name}", fontproperties=_CN_FP, fontsize=14, fontweight="bold"
    )
    ax.set_xlabel("Month", fontproperties=_CN_FP, fontsize=10)
    ax.set_ylabel("Year", fontproperties=_CN_FP, fontsize=10)

    cbar = fig.colorbar(im, ax=ax, shrink=0.85, pad=0.02)
    cbar.set_label("Return (%)", fontsize=9)
    fig.tight_layout()
    return _fig2bytes(fig)


# ================================================================
# PDF 构建主函数
# ================================================================
def generate_pdf_report(
    fund_code: str,
    fund_name: str,
    start_date: str,
    end_date: str,
    invest_amount: float,
    invest_day: int,
    fee_rate: float,
    results: List[BacktestResult],
    names: List[str],
    figs: dict = None,
) -> bytes:
    """
    生成 PDF 报告，返回 bytes 供下载。

    figs 参数已弃用（保留兼容性），图表始终使用 matplotlib 生成。
    """
    buf = io.BytesIO()
    margin = 20 * mm

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Fund DCA Backtest Report — {fund_code}",
        author="Fund DCA Backtest System",
    )

    story = []

    # ========== 封面 ==========
    story.append(Spacer(1, 12 * mm))
    story.append(
        Paragraph(
            "Fund DCA Backtest Report",
            ParagraphStyle(
                "EnTitle",
                fontName=CN_FONT_BOLD,
                fontSize=26,
                leading=34,
                alignment=TA_CENTER,
                textColor=PRIMARY,
            ),
        )
    )
    story.append(
        Paragraph(
            "Intelligent Fund DCA Backtest & AI Optimization",
            ParagraphStyle(
                "EnSub",
                fontName=CN_FONT,
                fontSize=11,
                leading=16,
                alignment=TA_CENTER,
                textColor=HexColor("#95a5a6"),
            ),
        )
    )
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(f"Report · {datetime.now().strftime('%Y-%m-%d %H:%M')}", style_subtitle))
    story.append(HRFlowable(width="60%", thickness=2, color=PRIMARY, spaceAfter=10))
    story.append(Spacer(1, 4 * mm))

    # ========== Section 1: 回测基本信息 ==========
    story.extend(_section_header("1. Backtest Basic Info"))

    info_data = [
        ["Fund Code", fund_code, "Fund Name", fund_name or f"Fund {fund_code}"],
        ["Start Date", start_date, "End Date", end_date],
        ["Invest Amount", f"CNY {invest_amount:,.0f} / month", "Invest Day", f"Day {invest_day}"],
        ["Fee Rate", f"{fee_rate:.2%}", "Risk-Free Rate", "3.00%"],
        ["Total Strategies", str(len(results)), "Generated", datetime.now().strftime("%Y-%m-%d")],
    ]

    info_table = Table(info_data, colWidths=[22 * mm, 46 * mm, 22 * mm, 46 * mm])
    info_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), CN_FONT),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("BACKGROUND", (0, 0), (0, -1), LIGHT_BG),
                ("BACKGROUND", (2, 0), (2, -1), LIGHT_BG),
                ("TEXTCOLOR", (0, 0), (0, -1), HexColor("#7f8c8d")),
                ("TEXTCOLOR", (2, 0), (2, -1), HexColor("#7f8c8d")),
                ("TEXTCOLOR", (1, 0), (1, -1), HexColor("#2c3e50")),
                ("TEXTCOLOR", (3, 0), (3, -1), HexColor("#2c3e50")),
                ("ALIGN", (0, 0), (0, -1), "RIGHT"),
                ("ALIGN", (2, 0), (2, -1), "RIGHT"),
                ("ALIGN", (1, 0), (1, -1), "LEFT"),
                ("ALIGN", (3, 0), (3, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(info_table)
    story.append(Spacer(1, 10 * mm))

    # ========== Section 2: 策略对比表格 ==========
    story.extend(_section_header("2. Strategy Comparison"))

    tbl_header = [
        "Strategy",
        "Invested",
        "Asset",
        "Profit",
        "Total Rtn",
        "Annual Rtn",
        "Sharpe",
        "Max DD",
        "Vol",
        "Win Rate",
        "Trades",
    ]
    tbl_data = [tbl_header]
    for r, n in zip(results, names):
        tbl_data.append(
            [
                n,
                f"{r.total_invest:,.0f}",
                f"{r.total_asset:,.0f}",
                f"{r.total_profit:+,.0f}",
                f"{r.total_return:+.2%}",
                f"{r.annual_return:+.2%}",
                f"{r.sharpe_ratio:.4f}",
                f"{r.max_drawdown:.2%}",
                f"{r.volatility:.2%}",
                f"{r.win_rate:.1%}",
                str(len(r.trades)),
            ]
        )

    n_cols = len(tbl_header)
    avail_w = PAGE_W - 2 * margin
    col_w = avail_w / n_cols

    comp_table = Table(tbl_data, colWidths=[col_w] * n_cols, repeatRows=1)
    table_cmds = [
        ("FONTNAME", (0, 0), (-1, -1), CN_FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("FONTNAME", (0, 0), (-1, 0), CN_FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("BACKGROUND", (0, 0), (-1, 0), TABLE_HEADER),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    for i in range(1, len(tbl_data)):
        if i % 2 == 0:
            table_cmds.append(("BACKGROUND", (0, i), (-1, i), TABLE_ROW_ALT))
    comp_table.setStyle(TableStyle(table_cmds))
    story.append(comp_table)
    story.append(Spacer(1, 8 * mm))

    # ========== Section 3: 图表 (matplotlib) ==========
    story.append(PageBreak())
    story.extend(_section_header("3. Chart Analysis"))

    # 3.1 累计收益曲线
    story.append(Paragraph("3.1 Cumulative Return Comparison", style_h2))
    try:
        png_bytes = _plot_returns_png(results, names)
        img_buf = io.BytesIO(png_bytes)
        img_w = PAGE_W - 40 * mm
        img_h = img_w * (IMG_H_INCH / IMG_W_INCH)
        story.append(Image(img_buf, width=img_w, height=img_h))
    except Exception as e:
        story.append(Paragraph(f"[Chart generation failed: {e}]", style_body))
    story.append(Spacer(1, 6 * mm))

    # 3.2 回撤曲线
    story.append(Paragraph("3.2 Drawdown Analysis", style_h2))
    try:
        png_bytes = _plot_drawdown_png(results, names)
        img_buf = io.BytesIO(png_bytes)
        img_w = PAGE_W - 40 * mm
        img_h = img_w * (IMG_H_INCH / IMG_W_INCH)
        story.append(Image(img_buf, width=img_w, height=img_h))
    except Exception as e:
        story.append(Paragraph(f"[Chart generation failed: {e}]", style_body))
    story.append(Spacer(1, 6 * mm))

    # 3.3 月度热力图 (第一个策略)
    if results and names:
        name0 = names[0]
        story.append(Paragraph(f"3.3 Monthly Return Heatmap — {name0}", style_h2))
        try:
            png_bytes = _plot_heatmap_png(results[0], name0)
            if png_bytes:
                img_buf = io.BytesIO(png_bytes)
                img_w = PAGE_W - 40 * mm
                img_h = img_w * (IMG_H_INCH * 0.7 / IMG_W_INCH)
                story.append(Image(img_buf, width=img_w, height=img_h))
        except Exception as e:
            story.append(Paragraph(f"[Chart generation failed: {e}]", style_body))

    # ========== Section 4: 风险指标汇总 ==========
    story.append(PageBreak())
    story.extend(_section_header("4. Risk Metrics Summary"))

    if len(results) > 0:
        best_idx = max(range(len(results)), key=lambda i: results[i].sharpe_ratio)
        best_r = results[best_idx]
        best_n = names[best_idx]
        story.append(
            Paragraph(
                f"Best Strategy (by Sharpe): <font color='#1a5276'><b>{best_n}</b></font>  |  "
                f"Sharpe: {best_r.sharpe_ratio:.4f}  |  Annual Return: {best_r.annual_return:+.2%}  |  "
                f"Max Drawdown: {best_r.max_drawdown:.2%}",
                style_body,
            )
        )
        story.append(Spacer(1, 5 * mm))

    risk_header = [
        "Strategy",
        "Annual Rtn",
        "Sharpe",
        "Max DD",
        "Volatility",
        "Win Rate",
        "Max Loss Mo.",
        "Trades",
    ]
    risk_data = [risk_header]
    for r, n in zip(results, names):
        risk_data.append(
            [
                n,
                f"{r.annual_return:+.2%}",
                f"{r.sharpe_ratio:.4f}",
                f"{r.max_drawdown:.2%}",
                f"{r.volatility:.2%}",
                f"{r.win_rate:.1%}",
                str(r.max_loss_months),
                str(len(r.trades)),
            ]
        )

    n_rcols = len(risk_header)
    rcol_w = avail_w / n_rcols
    risk_table = Table(risk_data, colWidths=[rcol_w] * n_rcols, repeatRows=1)
    risk_cmds = [
        ("FONTNAME", (0, 0), (-1, -1), CN_FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 0), (-1, 0), CN_FONT_BOLD),
        ("BACKGROUND", (0, 0), (-1, 0), TABLE_HEADER),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    for i in range(1, len(risk_data)):
        if i % 2 == 0:
            risk_cmds.append(("BACKGROUND", (0, i), (-1, i), TABLE_ROW_ALT))
    risk_table.setStyle(TableStyle(risk_cmds))
    story.append(risk_table)

    # ========== 页脚 ==========
    story.append(Spacer(1, 15 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceAfter=6))
    story.append(
        Paragraph(
            f"Generated by Fund DCA Backtest System  |  "
            f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  "
            f"Data source: EastMoney  |  "
            f"For educational purposes only — not financial advice.",
            style_small,
        )
    )

    # ========== 构建 ==========
    doc.build(story)
    buf.seek(0)
    return buf.getvalue()


# ================================================================
# Streamlit 集成辅助（兼容旧接口，已不再需要预生成 figs）
# ================================================================
def build_report_figs(results, names):
    """兼容旧接口，返回空 dict。图表由 generate_pdf_report 内部用 matplotlib 生成。"""
    return {}
