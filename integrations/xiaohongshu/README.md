# 小红书连接器登录兼容修复

上游版本：xpzouying/xiaohongshu-mcp v2.7.4，提交 bb6fa2e208719ee634fec37881be29d3aa4699b3。

问题：创作者后台已通过现有网页登录，但不再提供 `galaxy_creator_session_id`，上游仅检查这个 cookie，导致发布前误报登录失效。

修复：进入真实创作者首页，等待页面同时出现账号名称和“小红书账号”标识，并核对页面域名和非登录页状态。缺少这些证据仍拒绝继续，保留原有账号与审批核验。新增只读 `/api/v1/login/creator-status` 检查接口，供工作台诊断；不上传、不发布。

这里保存替换源文件与回归测试。下列命令均在工作台根目录执行。安装满足上游 `go.mod` 要求的 Go（当前固定版本要求 Go 1.27.3），然后获取固定提交并构建：

```sh
.venv/bin/python scripts/fetch_connector.py
.venv/bin/python scripts/build_connector.py /absolute/path/to/go
```

获取脚本从 GitHub 下载固定提交的源码归档，检查归档目录，并拒绝覆盖已有目录。构建脚本应用补丁、运行针对性回归测试，生成 `data/connector/build/xiaohongshu-mcp-candidate`，不会自动替换运行中的二进制。Go 依赖下载受网络影响时，可自行配置 `GOPROXY`，例如 `https://goproxy.cn,direct`。

首次安装：

```sh
.venv/bin/python scripts/manage.py stop
cp data/connector/build/xiaohongshu-mcp-candidate data/connector/xiaohongshu-mcp
chmod +x data/connector/xiaohongshu-mcp
.venv/bin/python scripts/manage.py start
```

更新已有安装时，请先备份原二进制，再执行替换。在「连接与设置」扫码登录并核验账号。启动脚本会为连接器生成本机鉴权令牌，监听 `127.0.0.1:18060`；浏览器及必要依赖可能在首次运行时下载。所有源码下载、二进制、令牌与登录状态均保存在被 Git 忽略的 `data/connector/`。

补丁来源与许可见 [NOTICE](NOTICE) 和 [LICENSE](LICENSE)。
