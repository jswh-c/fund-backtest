# 智能基金定投策略回测与AI优化系统

**Fund DCA Backtest & AI Optimization System**

基于 Python 的基金定投多策略回测框架。支持 9 种定投策略（含机器学习）、贝叶斯参数优化、交互式可视化、PDF 报告导出。已部署至 Streamlit Community Cloud。

---

## 功能清单

### 策略引擎（9 种）
| 类别 | 策略 | 核心逻辑 |
|------|------|----------|
| 基准 | 普通定投 | 每月固定金额 |
| 基准 | 止盈定投 | 收益率达标全额赎回，重新开始 |
| 动态 | 价值平均 | 维持市值匀速增长，低买高卖 |
| 均线 | MA250动态 | 价格/MA 比值分三档调整金额 |
| 均线 | 60日均线 | MA60 ±5% 偏离度判断 |
| 技术指标 | MACD | 柱状图强度决定投资倍数 |
| 技术指标 | RSI | 超买超卖 5 档信号 |
| 技术指标 | 波动率 | 恐慌时加仓、平静时减仓 |
| 机器学习 | ML随机森林 | 16 维特征预测涨跌概率动态调仓 |

### 核心指标
年化收益率、夏普比率、最大回撤、年化波动率、胜率、最大连续亏损月数、平均成本等共 14 项。

### 参数优化
Optuna TPE 贝叶斯优化 + 训练/测试集分离 + 过拟合检测 + 四合一敏感性分析图。

### Web 界面
- 黑暗模式切换、实时进度条、6 标签页图表
- 实用工具：数据更新、定投计算器、风险预警、快照保存/恢复
- 一键生成 PDF 报告（含图表）

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 语言 | Python 3.10+ |
| 数据处理 | Pandas, NumPy（全向量化，63x 加速） |
| 可视化 | Plotly（交互式）, Matplotlib（静态导出） |
| Web 框架 | Streamlit 1.45 |
| 机器学习 | scikit-learn（RandomForest） |
| 优化 | Optuna（TPE 贝叶斯优化） |
| PDF 生成 | ReportLab + Matplotlib |
| 异步 | aiohttp（批量数据下载） |
| 测试 | pytest（57 个用例） |
| CI/CD | GitHub Actions（自动 lint + test + health check） |
| 部署 | Streamlit Community Cloud |

---

## 本地运行

### 环境要求
- Python 3.10 或更高版本
- Windows / macOS / Linux

### 安装

```bash
git clone https://github.com/YOUR_USERNAME/fund-backtest.git
cd fund_backtest
pip install -r requirements.txt
```

### 启动 Web 界面（推荐）

```bash
streamlit run app.py
```

浏览器自动打开 `http://localhost:8501`。在左侧选择基金代码、日期范围、勾选策略，点击 **"运行回测"**。

### 命令行模式

```bash
# 单基金全策略回测
python main.py --code 161725 --start 2021-01-01 --all --output

# 批量回测（5 只基金 × 8 策略）
python backtest.py batch 161725 110011 000001 002610 001632
```

### 运行测试

```bash
pytest tests/ -v
# 57 passed in 0.86s
```

---

## 在线部署

已部署至 Streamlit Community Cloud：**https://YOUR_APP_NAME.streamlit.app**

详细部署步骤见 [DEPLOY_FINAL.md](DEPLOY_FINAL.md)。

---

## 文件结构

```
fund_backtest/
├── app.py                 Streamlit Web 主界面
├── backtest.py            回测引擎（8 策略 + Optuna 优化）
├── strategies.py          机器学习策略（随机森林）
├── data_fetcher.py        数据获取 + 智能缓存 + 异步下载
├── visualization.py       Plotly 交互式图表 + 敏感性分析
├── pdf_report.py          PDF 报告生成
├── utils.py               公共工具模块
├── main.py                CLI 命令行入口
├── tests/                 pytest 单元测试（57 用例）
├── .streamlit/config.toml Streamlit Cloud 部署配置
├── packages.txt           Linux apt 系统依赖
├── .github/workflows/     GitHub Actions CI/CD
├── requirements.txt       13 个 Python 依赖（精确版本）
├── README.md              本文件
├── PROJECT_REPORT.md      项目详细报告
├── DEPLOY_FINAL.md        部署操作步骤
├── TEST_REPORT.md         测试验证报告
├── CHANGELOG.md           版本变更记录
├── data/                  净值缓存（.gitkeep）
└── output/                图表输出（.gitkeep）
```

---

## 免责声明

本系统基金净值数据来源于天天基金网公开 API，仅供学习研究使用，不构成投资建议。历史回测结果不代表未来表现。
