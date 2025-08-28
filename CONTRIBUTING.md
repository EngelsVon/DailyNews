# Contributing to DailyNews / 贡献指南

Thank you for considering contributing! / 感谢你愿意为本项目贡献！

## Getting Started / 开始之前
- Fork the repo and create your branch from `main`. / Fork 本仓库，从 `main` 分支创建你的功能分支。
- Set up the dev environment following README. / 按 README 配置开发环境。
- Use a Python virtualenv and install dependencies via `pip install -r requirements.txt`. / 建议使用虚拟环境并通过 `pip install -r requirements.txt` 安装依赖。

## Development Workflow / 开发流程
1. Create a descriptive branch name (e.g., `feat/rss-parser`, `fix/sorting`). / 创建描述性分支名。
2. Write clear commits (English or Chinese). / 提交信息请清晰描述（中英文均可）。
3. Ensure app starts locally: `python app.py` with no errors. / 确保本地可 `python app.py` 启动无报错。
4. Before PR, self-check: / 提交 PR 前自检：
   - No secrets or API keys committed. / 不要提交任何密钥或私密信息。
   - Code style consistent with existing code. / 代码风格与现有一致。
   - UI changes include screenshots if applicable. / 如涉及 UI，请附截图。

## Pull Request Guidelines / PR 指南
- Link related issues and describe motivation. / 关联相关 issue 并说明动机。
- Keep PRs focused; large changes split into smaller PRs. / 主题聚焦，过大改动请拆分。
- Maintainers may request changes; please be responsive. / 维护者可能提出修改建议，请及时响应。

## Issue Reports / 提交 Issue
- Provide environment, steps to reproduce, expected/actual behavior. / 提供环境、复现步骤、预期/实际结果。
- For feature requests, describe scenario and benefits. / 功能需求请描述场景与收益。

## Code of Conduct / 行为准则
Be respectful and inclusive. / 保持尊重与包容。