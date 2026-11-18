# 科研手记 · 本地运营工作台

Python FastAPI + SQLAlchemy/SQLite + 独立任务进程 + React/TypeScript。

将「了解用户 → 吸引用户 → 审核发布 → 复盘」放到一台电脑上：从公开讨论整理需求，按32类人群与96条提示词生成候选内容，经人工审核后排队提交小红书。

## 首次安装

支持 macOS / Linux，Python 3.12+、Node.js 22+、Git，以及 [uv](https://docs.astral.sh/uv/getting-started/installation/)。当前使用 POSIX 文件锁，暂不支持原生 Windows；macOS 提供双击启动入口。

```sh
git clone https://github.com/Gilbert5210/medical-ops-workbench.git
cd medical-ops-workbench
uv sync --locked --group dev
npm --prefix frontend ci
npm --prefix frontend run build
uv run playwright install chromium
.venv/bin/python scripts/manage.py start
```

然后打开 <http://127.0.0.1:18765/>。Linux 的 Chromium 可能需要额外系统依赖，可使用 `uv run playwright install --with-deps chromium`。

以上步骤可先使用人群库、手动导入、稿件与复盘功能；AI 功能需要在「连接与设置」配置模型，小红书搜索与发布还需要[安装本地连接器](integrations/xiaohongshu/README.md)。连接器未安装时也可以启动工作台。

自定义模型支持 URL、Key、模型名称，以及 Responses / Chat Completions 接口。Key 通过系统密钥服务保存；Linux 需要配置可用的 keyring 后端。也可直接引用本机已有的 Codex 提供商配置。仓库不提供模型密钥，不读取 `.env` 作为模型配置。

## 使用

双击“启动工作台.command”，打开 http://127.0.0.1:18765 。使用完毕双击“停止工作台.command”。也可以执行 `.venv/bin/python scripts/manage.py start|stop|status`。

1. 在“连接与设置”测试模型。默认引用本机 `~/.codex/config.toml` 当前提供商、模型和密钥，每次请求重新读取，不修改原配置、不复制密钥。自定义模式支持URL、Key、模型名称和两种接口；自定义Key写入macOS钥匙串。
2. 在“用户需求”导入原话、JSON或CSV（至少包含text列，可选title、url），也可搜索小红书笔记。不知道搜什么时，先在“从小红书发现问题”选择人群和内容类型，使用提示词建议；点击“AI 推荐近期话题”，结合对应提示词生成最多4组搜索词并按近一周、最多评论检索，每词最多10篇。再由AI初筛标题相关性，展示相关样本、来源及相关样本的单篇最高评论数，缺失指标保持未知，不将样本当作全站热榜。推荐结果保存到任务记录，超过24小时提示刷新；失败时仍提供提示词搜索起点。推荐本身不导入素材，点击“搜这个问题”后才采集。选择高相关笔记，再读取正文和最多30条一级评论；不展开二级评论，不保证完整采集。
3. 选择素材进行AI分类，或者从32类人群/96条提示词创建内容。所有AI任务在独立进程执行，页面可以关闭。
4. 打开候选稿，检查正文、图卡和待核实事项。修改后先保存，再审核。
5. 登录并核验小红书账号，选择立即发布或自由选择预约时间，勾选审核后批准。后台再次核对版本和账号。适合连接工具预约窗口的任务提前交给平台；其他时间由本地队列等待，到点后按立即发布提交，避免连接工具自身的预约时间检查。等待本地提交期间请保持电脑和后台运行；恢复运行后已到时间的任务会继续提交。
6. 到平台创作后台核对实际预约/发布结果，再更新本地发布记录。工具成功响应只记为“已提交”。
7. 有素材后可生成运营复盘。数字由程序统计，AI根据样本提出建议，不自动调整排期。

每日候选稿默认关闭。在设置中手动开启并指定北京时间，工作进程会每天生成一份待审稿；不是自动发布。电脑休眠或程序停止期间不执行，错过的时间不会补跑。

## 运行与数据

- 前端构建后由FastAPI提供；默认仅监听127.0.0.1，拒绝跨站写入。
- 本机小红书连接服务同样只监听127.0.0.1，使用本地随机令牌鉴权，页面无法直接调用发布接口。
- `data/workbench.sqlite3`：需求、稿件、版本、报告、审批与任务。
- `data/assets/`：批准版本渲染的图片。
- `data/connector/`：下载的第三方连接程序及其本地登录状态，属于敏感资料。
- `data/*.log`：服务运行记录，不记录模型Key、提示词或上游原始错误响应。
- 暂停备份：先停止工作台，再备份整个data目录。自定义模型Key在系统钥匙串中，不在备份目录内。
- AI只接收必要的任务文本；外部服务仍会处理这些文本。导入前请去除身份与患者信息。

## 已实现与限制

已实现：导入/去重/导出、搜索与评论连接层、人群提示词、按人群与内容类型推荐搜索词及近期讨论样本、需求分类、指标分布、AI复盘、图文生成/修改/预览、版本审批、持久任务队列、平台预约提交、人工结果核对、每日生成设置。

初版不包含：公众号接入、自动私信或评论、自动联系用户、曝光/阅读/成交指标接入、全量评论承诺、自动判断平台已公开发布。真实登录、页面验证与专业内容审核需要本人完成。

小红书工具基于公开版本v2.7.4，已应用本地创作者登录兼容修复，补丁与构建说明见 [连接器说明](integrations/xiaohongshu/README.md)。仓库不附带二进制或登录状态。连接能力依赖平台和账号当前状态。

第三方代码许可不等于平台授权。连接工具来源和许可：https://github.com/xpzouying/xiaohongshu-mcp （Apache-2.0）。

## 开发与检查

```sh
uv sync --locked --group dev
cd frontend
npm ci
npm run build
```

后台测试：`.venv/bin/python -m pytest`。前端开发：`npm run dev`，由Vite代理/api到本机18765。

依赖检查（2026-11-18）：`npm audit` 报告 picomatch 的高危 ReDoS 告警（[GHSA-fc5q-39xc-vjpf](https://github.com/advisories/GHSA-fc5q-39xc-vjpf)），经 Vite 等构建依赖传递，共4项；当前注册表最新版本4.0.7仍在影响范围，`npm audit fix` 未消除。它属于开发/构建工具链，不打包进浏览器产物；更新依赖后应重新检查。

图卡使用本机Google Chrome进行无头渲染，开启独立临时环境，不读取日常Chrome登录状态；其他系统可安装Playwright Chromium后运行。后台任务进程和API通过文件锁串行访问小红书浏览器。

发布状态：待审核→批准→等待定时提交（如需）→提交中→已提交→核对预约/发布。明确的发布前校验失败标记为“未提交·可重试”，显示具体原因；经用户确认后可以重试同一审批版本，并保存历史。无法确认执行结果的异常或中断仍标记为结果不明，不自动重试。修改待执行版本会取消原审批；已提交版本需新建副本。取消本地任务不会取消已存在的平台预约。

## 目录与提交范围

| 目录 | 用途 |
| --- | --- |
| `backend/` | API、SQLite 模型、AI 分析与内容生成、任务执行、小红书连接层 |
| `frontend/` | React 页面、审稿与排期界面、平台内使用说明 |
| `resources/` | 32类人群索引和96条内容提示词，首次运行自动导入 |
| `scripts/` | 启停服务、获取固定版本连接器源码、应用补丁并构建 |
| `integrations/xiaohongshu/` | 连接器补丁、上游许可和安装说明 |
| `tests/` | 独立临时数据库中的工作流和边界测试 |

`data/`、`output/`、浏览器记录、登录文件、数据库、运行日志、依赖和构建产物都被 Git 忽略。请勿强制加入这些文件。测试和自动检查不需要真实模型密钥或社交平台登录。

上游连接器的 Apache-2.0 许可见 [LICENSE](integrations/xiaohongshu/LICENSE) 与[来源说明](integrations/xiaohongshu/NOTICE)。本项目其他代码尚未另行指定开源许可证。
