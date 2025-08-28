# DailyNews 聚合与翻译平台

DailyNews 是一个轻量、开箱即用的技术资讯聚合与翻译平台。它基于 Flask + SQLAlchemy + APScheduler 实现，支持按板块（Section）从多种来源定时抓取新闻，提供前端浏览、手动刷新、以及前后端协同翻译（MyMemory 免费 API 或本地 Gemini CLI）。

- 简单部署，SQLite 本地数据库，零外部服务依赖（可通过环境变量对接其他数据库）
- 板块化管理：RSS、arXiv、Gemini 自定义抓取
- 前端便捷：按条数折叠、时区切换、全局/分板块翻译、展开摘要
- 后台任务：定时抓取、批量后台翻译

## 目录
- [特性概览](#特性概览)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [使用指南](#使用指南)
- [进阶功能](#进阶功能)
- [常见问题](#常见问题)
- [许可协议](#许可协议)

## 特性概览
- 多源抓取：支持 RSS、arXiv、以及 Gemini Collector（可通过命令行执行本地模型/云模型）
- 去重保存：基于 (title + url) 简单去重
- 排序友好：首页按创建时间优先排序，最新抓取立刻可见
- 翻译方式：
  - 浏览器“伪翻译”（前端示例）
  - MyMemory 免费 API（可配置邮箱提升配额）
  - Gemini CLI（本地命令调用，需 GEMINI_API_KEY 或本地图形化工具支持）
- 后台翻译：可手动启动，也可周期性调度

## 快速开始
1) 克隆并进入目录
```
git clone https://github.com/yourname/DailyNews.git
cd DailyNews
```
2) 创建虚拟环境并安装依赖
```
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```
3) 准备环境变量（可选）
复制 .env.example 为 .env，按需修改：
```
cp .env.example .env
```
关键项：
- SECRET_KEY
- DATABASE_URL（默认 sqlite:///data/dailynews.db）
- GEMINI_CLI_CMD / GEMINI_API_KEY（如使用 Gemini 翻译）
- MYMEMORY_EMAIL（如使用免费翻译）

4) 运行开发服务器
```
python app.py
```
浏览器打开 http://127.0.0.1:5000/

## 配置说明
应用配置位于 <mcfile name="config.py" path="d:\PythonProjects\DailyNews\config.py"></mcfile>，关键点：
- 数据库：默认 SQLite，路径为 data/dailynews.db，可通过环境变量 DATABASE_URL 重写
- 调度：APScheduler 后台调度器，默认启用 API
- 翻译：GEMINI_CLI_CMD、GEMINI_API_KEY、MYMEMORY_EMAIL

模板与静态资源：
- 模板目录 <mcfolder name="templates" path="d:\PythonProjects\DailyNews\templates\"></mcfolder>
- 静态目录 <mcfolder name="static" path="d:\PythonProjects\DailyNews\static\"></mcfolder>

## 使用指南
1) 创建板块
- 打开“Sections”页面，填写名称、描述、抓取方式（rss/arxiv/gemini）与更新频率，保存后可手动刷新
- 各方式配置示例在弹窗中有模板

2) 首页浏览
- 每个板块支持滑杆控制显示条数、切换时区、开/关翻译
- 标题右侧“新”徽标表示近12小时内抓取的新内容
- “手动刷新”将触发后端抓取并自动刷新页面

3) 翻译
- 设置页选择翻译方式：browser/free/gemini
- free：建议填写 MYMEMORY_EMAIL 以提升限额
- gemini：在设置页填写命令（例如 gemini 或 gemini-cli），并确保系统可用 GEMINI_API_KEY
- 首页可“翻译”“后台翻译”，后者会批量处理未译内容

## 进阶功能
- 后台轮询翻译任务：通过环境变量 AUTO_TRANSLATE_INTERVAL_MINUTES 控制运行间隔（app.py 中注册）
- 自定义 Collector：在 collectors 目录内新增实现，配置板块 fetch_method 与 config_json 即可接入
- 生产部署：建议使用 WSGI（如 gunicorn + gevent）或 ASGI 适配器，并配置持久数据库（PostgreSQL/MySQL）

## 常见问题
- 页面不更新？首页已按 created_at 优先排序；手动刷新后会 reload。
- 新条目不显示“新”？由后端基于 created_at <= 12 小时计算，可按需调整阈值。
- 免费翻译速率/限额？适当减少批量大小或配置邮箱。

## 许可协议
本项目采用开源许可证，详见 LICENSE 文件。