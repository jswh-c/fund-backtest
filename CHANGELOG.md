# Changelog — 智能基金定投策略回测与AI优化系统

所有值得注意的变更记录。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

---

## [1.0.0] — 2026-06-10（最终提交）

### Added — 新增功能
#### 策略扩展（4→9种）
- **60日均线策略** (`run_ma60_dca`)：基于 MA60 中期趋势的3区判断（低位加仓/正常/高位减仓）
- **MACD 定投策略** (`run_macd_dca`)：基于 MACD 柱强度（深度超卖→2x，强势上涨→0.5x）
- **RSI 定投策略** (`run_rsi_dca`)：基于 Wilder's RSI 超买超卖信号（5区判断）
- **波动率定投策略** (`run_volatility_dca`)：基于年化波动率 vs 均值比值（恐慌加仓，平静减仓）
- **ML 随机森林策略** (`strategies.py`)：16维特征工程 + RandomForestClassifier 预测涨跌概率

#### 性能优化
- **Pandas 全向量化改造**：`np.searchsorted`、`np.where`、`pd.merge`+`cumsum` 替代所有 while 循环
- 回测速度提升 **63 倍**（8策略从 4.0s → 0.063s，单策略 7.2ms）
- `_build_trade_dates()`、`_get_trade_data_vectorized()`、`_build_trades_vectorized()` 三个向量化辅助方法

#### 参数优化
- **Optuna 贝叶斯优化** (`optimize_ma_bayesian`)：替代网格搜索，TPESampler 自适应采样
- 训练/测试集分离 + 过拟合检测（Train-Test Sharpe gap）
- **敏感性分析可视化** (`plot_optimization_analysis`)：优化历史 + 参数重要性 + 散点关系 + 平行坐标

#### Web 界面增强（6项）
- 🌙 **黑暗模式**：侧边栏 toggle + 全局 CSS 覆盖 + `st.session_state` 持久化
- ⏳ **实时进度条**：`st.status` 容器 + `st.progress`，每策略显示完成状态和年化收益率
- 📑 **6标签页重组**：策略对比/收益曲线/回撤分析/月度收益/风险雷达/交易记录
- 🔧 **实用工具面板**：
  - 🔄 实时数据更新（清空缓存强制重拉）
  - 🧮 定投计算器（PMT 公式反算每月金额）
  - ⚠️ 风险预警（最新价格/MA250 四级提示）
  - 📸 历史快照（保存/恢复/删除回测参数和结果）
- 📄 **一键PDF报告** (`pdf_report.py`)：reportlab + matplotlib 内嵌图表，4章节
- 🤖 **ML模型详情展示**：训练/测试准确率、特征重要性 Top5

#### 数据层增强
- **智能缓存**：`_is_cache_fresh()` 日期覆盖检测 + 过期天数（>5天自动刷新）
- **异步批量下载**：`batch_download_async()` + `batch_download_async_sync()`（aiohttp 并发，Semaphore 限流）
- **Linux 系统依赖** (`packages.txt`)：kaleido 浏览器引擎 + 中文字体

#### 工程质量
- **57 个 pytest 单元测试** (`tests/`)：15 个测试类，覆盖 8 策略 + 指标计算 + 跨策略一致性
- **公共工具模块** (`utils.py`)：12 个复用函数，消除代码重复
- **Black 格式化**：全部 11 个 Python 文件通过 PEP8 规范
- **完整类型注解**：所有公共函数含 `->` 返回类型和 docstring
- **GitHub Actions CI/CD** (`.github/workflows/deploy.yml`)：自动 lint + test + health check

#### 部署支持
- `DEPLOY.md`：5步部署指南 + 10项验证清单 + 6个故障排查
- `DEFENSE_GUIDE.md`：核心亮点 + 10个 Q&A + 演示视频7段式讲解
- `SUBMISSION_GUIDE.md`：文件清单 + 环境要求 + 运行步骤 + 评分要点
- `TEST_REPORT.md`：57 用例结果 + CLI 验证 + Streamlit 健康检查
- `CHANGELOG.md`：本文件
- `packages.txt`：18个 Linux apt 依赖

### Changed — 变更
- `backtest.py`：`optimize_ma_params`（网格搜索）→ `optimize_ma_bayesian`（Optuna TPE）
- `backtest.py`：`_build_daily_values`：从 `iterrows()` + dict → `pd.merge` + `ffill` + `cumsum`
- `backtest.py`：`_preprocess`：新增 `_build_trade_dates()` 预生成所有定投日期
- `app.py`：从 370 行扩展至 1100 行（新增 UI 组件、实用工具、ML 详情、PDF 按钮）
- `requirements.txt`：从 7 个依赖 → 13 个精确 pinned 依赖 + 3 个 dev 依赖注释
- `.streamlit/config.toml`：新增 `[logger]`、`[client]`、`[global]` 段

### Fixed — 修复
- 修复基金代码 `000001` 在 Excel 导出时被转为数字 `1` 的问题（强制文本格式）
- 修复 `kaleido` 1.3.0 与 `plotly` 5.24.1 不兼容 → 锁定 `kaleido==0.2.1`
- 修复 Windows GBK 编码下 emoji 打印异常
- 修复 `nonlocal` 在 Streamlit 模块级作用域中的语法错误

---

## [0.3.0] — 2026-06-09

### Added
- **批量回测函数** (`run_batch_backtest`)：支持多基金×多策略，生成 Excel 对比表（2个 Sheet）
- **Excel 格式优化**：百分比列自动格式化、基金代码强制文本格式、冻结首行、自动列宽
- `.gitignore` 配置文件

### Changed
- `backtest.py`：从 700 行扩展至 1300 行
- 项目文件数从 7 个增至 11 个

---

## [0.2.0] — 2026-06-08

### Added
- **4 种定投策略**：普通定投、止盈定投、价值平均、AI均线动态
- 网格搜索参数优化（200+ 组合）
- 5 种 Plotly 交互式图表：收益曲线、资产增长、回撤分析、月度热力、风险雷达
- `data_fetcher.py`：天天基金网 API 对接、复权净值计算、CSV 缓存
- `main.py`：CLI 命令行入口（argparse）
- `app.py`：Streamlit Web 界面 v1
- `write_report.py`：Markdown 报告生成

---

## [0.1.0] — 2026-06-07

### Added
- 项目初始化
- `BacktestResult` 数据类（14 项核心指标）
- `FundBacktest` 引擎框架
- 基础数据流：API → DataFrame → 策略 → 结果

---

[1.0.0]: https://github.com/YOUR_USERNAME/fund-backtest/releases/tag/v1.0.0
[0.3.0]: https://github.com/YOUR_USERNAME/fund-backtest/releases/tag/v0.3.0
[0.2.0]: https://github.com/YOUR_USERNAME/fund-backtest/releases/tag/v0.2.0
[0.1.0]: https://github.com/YOUR_USERNAME/fund-backtest/releases/tag/v0.1.0
