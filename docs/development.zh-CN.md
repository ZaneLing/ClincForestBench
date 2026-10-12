# 本地开发

[English](development.md) | [简体中文](development.zh-CN.md)

推荐使用统一入口同时启动 FastAPI 后端和 Vinext 前端：

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
