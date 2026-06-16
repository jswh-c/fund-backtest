# Streamlit Community Cloud 部署检查清单

---

## ✅ 需要上传到 GitHub 的文件（26 个）

### 源代码（9 个）
```
app.py                  Streamlit Web 主界面
backtest.py             回测引擎 (8策略 + Optuna优化)
strategies.py           机器学习策略 (随机森林)
data_fetcher.py          数据获取 + 缓存 + 异步下载
visualization.py         Plotly 交互式图表
pdf_report.py            PDF 报告生成 (reportlab)
utils.py                 公共工具模块
main.py                  CLI 命令行入口
write_report.py          Markdown 报告生成
```

### 配置文件（5 个）
```
requirements.txt         13 个 Python 依赖 (精确 pinned 版本)
packages.txt             18 个 Linux apt 系统依赖
.streamlit/config.toml   主题/端口/生产模式/CORS 配置
.github/workflows/deploy.yml  GitHub Actions CI/CD
.gitignore               Git 排除规则
```

### 测试（3 个）
```
tests/__init__.py        包初始化
tests/conftest.py        pytest fixtures
tests/test_backtest.py   57 个单元测试
```

### 目录占位（2 个）
```
data/.gitkeep            数据缓存目录 (运行后自动填充 CSV)
output/.gitkeep           输出目录 (运行后自动生成图表)
```

### 文档（7 个）
```
README.md                项目主页文档
PROJECT_REPORT.md        详细项目报告 (6000 字)
TEST_REPORT.md           测试验证报告
CHANGELOG.md             版本变更记录
DEPLOY.md                部署指南
DEFENSE_GUIDE.md         答辩指南
SUBMISSION_GUIDE.md      作业提交说明
```

---

## ❌ 不需要上传的文件

| 文件/目录 | 原因 |
|-----------|------|
| `data/*.csv` | 基金净值缓存 — 运行时自动从 API 下载 |
| `output/*.html` | 图表输出 — 运行时自动生成 |
| `__pycache__/` | Python 字节码缓存 |
| `.pytest_cache/` | pytest 缓存 |
| `*.pyc` / `*.pyo` | 编译字节码 |
| `deploy.zip` | 打包产物（提交源码即可） |
| `batch_backtest_result.xlsx` | 测试生成的 Excel |
| `test_report.pdf` | 测试生成的 PDF |
| `venv/` / `.venv/` | 虚拟环境 |
| `.vscode/` / `.idea/` | IDE 配置 |

---

## 🔧 部署前自动验证

```bash
# 1. 语法检查
python -c "
import py_compile
for f in ['app.py','backtest.py','strategies.py','data_fetcher.py',
          'visualization.py','pdf_report.py','utils.py','main.py']:
    py_compile.compile(f, doraise=True)
print('All syntax OK')
"

# 2. 测试运行
pytest tests/ -v

# 3. Streamlit 启动验证
streamlit run app.py --server.headless true &
sleep 5 && curl -s http://localhost:8501/_stcore/health
```

---

## 📦 一键部署命令

```bash
# 推送到 GitHub（自动触发 CI + Streamlit Cloud 部署）
git init && git add . && git commit -m "v1.0.0: Fund DCA Backtest System"
git remote add origin https://github.com/YOUR_USERNAME/fund-backtest.git
git branch -M main && git push -u origin main

# 然后打开 https://share.streamlit.io → New app → Deploy
```

---

## 🌐 线上地址

```
App URL:  https://YOUR_SUBDOMAIN.streamlit.app
Repo:     https://github.com/YOUR_USERNAME/fund-backtest
CI/CD:    https://github.com/YOUR_USERNAME/fund-backtest/actions
```

---

*最后更新：2026-06-10*
