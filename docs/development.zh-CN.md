# 本地开发

[English](development.md) | [简体中文](development.zh-CN.md)

推荐使用一键后台部署入口（也可在 Finder 双击 `deploy.command`）：

```bash
./deploy.command          # 按需安装依赖、启动前后端，关闭终端仍运行
./deploy.command status   # 查看健康状态与访问地址
./deploy.command stop     # 只停止本入口启动的服务，不删除数据库或病例
```

默认应用地址为 `http://127.0.0.1:3000/`，API 文档为 `http://127.0.0.1:8000/docs`，
只绑定本机回环地址，不向公网或局域网开放。需要其它端口时，三条命令均添加
`--api-port 8100 --web-port 3100`（必须先停止原实例，Vinext 不支持同项目双开）。
依赖已安装时可加 `--no-install`。

重复部署会复用健康的当前项目服务，不会抢占端口或按端口杀进程。
如果服务原来由 `start.command` 在终端启动，新入口只复用，不接管停止；
需在原终端按 `Ctrl-C` 后再运行 `deploy.command` 才转为后台管理。
状态保存在 `.run/deployment-<API端口>-<网页端口>.json`，后台日志单独保存在
`.run/deploy-*`，与原入口日志互不覆盖。重启电脑后需再次运行部署入口；不安装开机自启。
部署不会自动下载受限数据、重建病例，或配置模型服务密钥；使用本机已有产物。
账户系统仍为研究 MVP，请使用临时测试密码，不作生产部署。

原来的前台入口保持可用：

```bash
./start.command
```

在 macOS 中也可以直接从 Finder 打开 `start.command`。启动器会：

1. 在缺失时创建 Python 虚拟环境；
2. 在 macOS 上按需安装项目独立的 Node 运行环境；
3. 安装缺失的前端依赖；
4. 检查 `8000` 和 `3000` 端口是否可用；
5. 启动 API 和网页、等待健康检查通过并打开应用；
6. 在按下 `Ctrl-C` 或关闭终端时停止两个服务。

运行日志写入已被 Git 忽略的 `.run/` 目录。默认本地 SQLite 数据库仍位于
`data/clincforestbench.db`。

常用参数：

```bash
./start.command --no-open
./start.command --api-port 8100 --web-port 3100
./start.command --host 0.0.0.0
./start.command --no-install
./start.command --help
```

等价的 Make 命令是 `make start`。需要在不同终端中独立重启服务时，仍可使用
`make api` 和 `make web`。

启动器也支持环境变量 `CFB_HOST`、`CFB_API_PORT`、`CFB_WEB_PORT`、
`CFB_OPEN_BROWSER`、`CFB_AUTO_INSTALL` 和 `CFB_STARTUP_TIMEOUT`。后端的
`OPENROUTER_API_KEY` 等配置仍从项目根目录的 `.env` 或当前环境读取。

## 验证

提交改动前运行完整本地验证：

```bash
make validate
```

该命令会运行 Python 测试、前端静态检查和前端生产构建。完整测试套件依赖
[数据准备说明](data_setup.md)中列出的生成产物。
