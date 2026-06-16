# Streamlit Community Cloud 完整部署指南

本指南帮助你将基金定投回测系统部署到 Streamlit Community Cloud，包含 GitHub Actions 自动 CI/CD。

---

## 📋 前置条件

| 条件 | 说明 |
|------|------|
| GitHub 账号 | https://github.com （免费注册） |
| Streamlit Cloud 账号 | https://share.streamlit.io （用 GitHub 账号直接登录） |
| Git 客户端 | 本地已安装 Git |
| 项目代码 | 当前目录下所有文件已就绪 |

---

## 🔧 项目中的部署配置文件

| 文件 | 用途 |
|------|------|
| `.streamlit/config.toml` | 主题颜色、CORS、生产模式、日志级别、WebSocket 压缩 |
| `requirements.txt` | 13 个 Python 依赖（精确 pinned 版本） |
| `packages.txt` | Linux apt 系统依赖（kaleido 浏览器引擎 + 中文字体） |
| `.github/workflows/deploy.yml` | GitHub Actions CI/CD：自动 lint + 测试 + 健康检查 |
| `.gitignore` | 排除 `data/*.csv`、`output/*.html`、`__pycache__` 等 |

---

## 第 1 步：初始化本地 Git 仓库

打开终端，进入项目目录：

```bash
cd fund_backtest

# 初始化 Git 仓库
git init

# 配置用户信息（替换为你的信息）
git config user.name "Your Name"
git config user.email "your-email@example.com"

# 添加所有代码文件（缓存和输出文件会被 .gitignore 自动排除）
git add .

# 提交
git commit -m "Initial commit: Fund DCA Backtest & AI Optimization System"
```

> **截图说明**：终端显示 `git init` → `git add .` → `git commit` 三步操作及成功输出。

---

## 第 2 步：创建 GitHub 远程仓库

### 2.1 在 GitHub 网页端创建仓库

1. 打开浏览器，登录 https://github.com
2. 点击右上角头像旁的 **"+"** 图标，选择 **"New repository"**
3. 填写仓库信息：

   | 字段 | 填写内容 |
   |------|----------|
   | Repository name | `fund-backtest` |
   | Description | `Smart Fund DCA Backtest & AI Optimization System` |
   | Visibility | **Public**（Streamlit Cloud 免费版要求） |
   | Add a README file | ❌ 不勾选（项目已有代码） |
   | Add .gitignore | ❌ 不勾选（项目已包含） |
   | Choose a license | 可选：MIT License |

4. 点击绿色 **"Create repository"** 按钮

> **截图说明**：GitHub 的 "Create a new repository" 页面，表单已填写。

### 2.2 推送本地代码到 GitHub

创建仓库后，GitHub 会显示推送命令。在终端执行：

```bash
# 添加远程仓库（替换 YOUR_USERNAME 为你的 GitHub 用户名）
git remote add origin https://github.com/YOUR_USERNAME/fund-backtest.git

# 推送到 main 分支
git branch -M main
git push -u origin main
```

> **截图说明**：终端显示 `git push` 成功输出，以及 GitHub 仓库页面刷新后可见全部文件。

---

## 第 3 步：验证 GitHub Actions CI/CD

推送代码后，GitHub Actions 自动触发工作流：

1. 在 GitHub 仓库页面，点击顶部 **"Actions"** 标签
2. 看到 `Deploy to Streamlit Cloud` 工作流正在运行
3. 等待约 2 分钟，两个 Job（Lint & Test + Health Check）均应显示绿色 ✅

> **截图说明**：GitHub Actions 页面，两个 Job 均为绿色通过。

**工作流自动执行的项目**：
- ✅ Black 代码格式检查
- ✅ 8 个 Python 模块语法检查
- ✅ 57 个 pytest 单元测试
- ✅ Core 模块导入验证
- ✅ Streamlit 服务器启动健康检查

---

## 第 4 步：在 Streamlit Cloud 部署

### 4.1 登录 Streamlit Cloud

1. 打开 https://share.streamlit.io
2. 点击 **"Continue with GitHub"** 按钮
3. 首次登录会弹出 GitHub 授权页面 → 点击 **"Authorize streamlit"**

> **截图说明**：Streamlit Cloud 登录页面，Show "Continue with GitHub" button.

### 4.2 创建新 App

1. 登录后进入 Dashboard，点击右上角蓝色 **"New app"** 按钮
2. 在弹出窗口中填写部署配置：

   | 字段 | 填写内容 |
   |------|----------|
   | Repository | `YOUR_USERNAME/fund-backtest`（从下拉列表中选择） |
   | Branch | `main` |
   | Main file path | `app.py` |
   | App URL | 自动生成，可自定义子域名（如 `fund-dca-backtest`） |

3. 点击蓝色 **"Deploy!"** 按钮

> **截图说明**：Streamlit Cloud 的 "Deploy an app" 弹窗，三个字段已填写。

### 4.3 等待部署

- 部署过程约 **2~5 分钟**（首次需要安装所有依赖）
- 底部日志区实时显示安装进度：
  1. Cloning repository...
  2. Installing apt packages from `packages.txt`...
  3. Installing Python dependencies from `requirements.txt`...
  4. Starting `streamlit run app.py`...
- 部署完成后浏览器自动打开应用

> **截图说明**：Streamlit Cloud 部署日志，显示 "Your app is now live!" 或类似成功消息。

---

## 第 5 步：访问和分享

- **App URL**：`https://YOUR_SUBDOMAIN.streamlit.app`
- 任何人打开此链接即可使用，无需安装任何软件
- 分享给老师/同学时附上此链接即可

> **截图说明**：浏览器中打开的 Streamlit 应用首页，显示完整的侧边栏和主界面。

---

## 🔄 更新代码后自动重新部署

每次 `git push` 到 GitHub 后：

1. **GitHub Actions** 自动运行 lint + test（约 2 分钟）
2. 如果测试通过，**Streamlit Cloud** 自动检测 GitHub 更新并重新部署
3. 也可以在 Streamlit Cloud 控制台的 App 设置中手动点击 **"Reboot app"**

```bash
# 修改代码后只需三步
git add .
git commit -m "update: xxx"
git push
# → GitHub Actions 自动测试 → Streamlit Cloud 自动部署
```

---

## ✅ 部署后验证清单

| # | 验证项 | 操作 | 预期结果 |
|---|--------|------|----------|
| 1 | 应用打开 | 访问 App URL | 显示 Web 界面，无错误 |
| 2 | 数据加载 | 默认基金 161725 | 加载成功，显示"✅ 数据加载成功" |
| 3 | 普通定投 | 仅勾选"普通定投"，点击运行 | 显示 66 笔交易，年化约 -3.30% |
| 4 | 全部策略 | 勾选所有 9 个策略（含 ML），运行 | 全部成功，对比表格完整 |
| 5 | 图表渲染 | 切换 6 个标签页 | 收益曲线/回撤/热力图/雷达图均正常 |
| 6 | PDF 报告 | 点击"生成并下载 PDF 报告" | 下载 ~400KB PDF，含图表 |
| 7 | 黑暗模式 | 侧边栏切换 🌙 黑暗模式 | 全局主题变暗 |
| 8 | 定投计算器 | 侧边栏实用工具展开计算器 | 显示每月需定投金额 |
| 9 | 风险预警 | 运行回测后展开风险预警 | 显示价格/MA250比值分析 |
| 10 | GitHub Actions | 查看 Actions 标签 | 两个 Job 均为绿色 ✅ |

---

## ❗ 常见问题排查

### 1. 部署失败：`ModuleNotFoundError`

**症状**：App 日志显示 `ModuleNotFoundError: No module named 'xxx'`

**原因**：`requirements.txt` 缺少某个依赖。

**解决**：
```bash
# 本地运行，获取完整依赖
pip freeze > requirements_full.txt
# 找到缺失的包，添加到 requirements.txt
git add requirements.txt && git commit -m "fix: add missing dep" && git push
```

### 2. kaleido 静态导出失败

**症状**：PDF 生成时报错 `BrowserFailedError`

**原因**：kaleido 需要 Chromium 浏览器依赖。

**解决**：确保 `packages.txt` 中包含 `libgconf-2-4` 等系统依赖。已在项目中配置好。

### 3. 中文字体缺失

**症状**：PDF 报告中文显示为方块或乱码。

**原因**：Linux 系统缺少中文字体。

**解决**：`packages.txt` 已配置 `fonts-wqy-microhei`。如果仍有问题，在 `pdf_report.py` 中改用备选字体路径。

### 4. 应用首次加载慢

**症状**：打开应用后数据加载需要 10 秒以上。

**原因**：首次访问时从 API 拉取数据。

**解决**：正常现象。第二次访问时从缓存读取，仅需 0.05 秒。数据缓存在 Cloud 容器的 `data/` 目录中。

### 5. Optuna 优化内存不足

**症状**：贝叶斯优化报 `MemoryError`。

**原因**：Streamlit Cloud 免费版内存限制（1GB）。

**解决**：减少 `n_trials` 参数。默认 80 可降至 30-50 仍可获得较好结果。

### 6. GitHub Actions 测试失败

**症状**：Actions 页面显示红色 ❌。

**解决**：
1. 点击失败的 Job 查看日志
2. 在本地运行 `pytest tests/ -v` 复现问题
3. 修复后 `git commit` + `git push` 重新触发

---

## 🔗 相关链接

| 资源 | URL |
|------|-----|
| Streamlit Cloud 控制台 | https://share.streamlit.io |
| Streamlit 官方部署文档 | https://docs.streamlit.io/deploy/streamlit-community-cloud |
| GitHub Actions 文档 | https://docs.github.com/en/actions |
| 项目 GitHub 仓库 | https://github.com/YOUR_USERNAME/fund-backtest |
| 线上 App | https://YOUR_SUBDOMAIN.streamlit.app |

---

*最后更新：2026年6月10日*
