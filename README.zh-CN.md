# ClincForestBench

[English](README.md) | [简体中文](README.zh-CN.md)

一个可复现的临床决策基准，用于记录医生和模型如何获取证据、修正诊断，并共同形成决策路径森林。所有患者回答均来自确定的源数据；模型只负责选择动作，不生成患者检查结果。

**当前状态：可运行的研究 MVP；临床裁定与大规模评测仍待完成。** 当前本地清单包含 **14 条数据轨道、188 个病例（Case）**。患者级生成产物不会纳入 Git，需在本地重新构建。

[快速开始](#快速开始) · [数据集覆盖](#数据集覆盖) · [项目进展](#项目进展) · [项目文档](docs/README.md)

## 项目进展

仓库状态核对日期：**2026-10-08**。

当日已通过 `make validate`，包括 Python 测试、前端静态检查和生产构建。本次文档更新未重新验证浏览器端到端流程及 Docker/PostgreSQL 配置。

| 方向 | 已实现 | 待完成 |
| --- | --- | --- |
| 数据流水线 | 原始数据校验、确定性转换、版本化清单、病例哈希及原始数据到病例树审计 | 对映射、参考标签和首诊信息提取进行临床审核 |
| 医生 Arena | 账户、证据动作、分阶段诊断排序、回放、个人历史及群体森林 | 扩大医生参与规模并开展亚组研究 |
| 模型 Arena | OpenRouter 模型选择、决策校验、暂停与恢复、完整交互归档及模型专属森林 | 按固定协议开展多病例、重复模型评测 |
| Temporal Forest v2 | 基于源数据的动作/结果事件、模拟时间、诊断检查点及 58 个本地病例 | 对时间语义和叙事参考语义进行临床裁定 |
| 分析 | 准确率与排名指标、诊断变化、分支熵、参考朴素贝叶斯及导出/快照工具 | 高级轨迹分析及医生对比研究 |
| 本地化 | 中英文界面及病例内容词典 | 病例产物变化后重新生成词典 |

近期功能里程碑包括 Temporal Arena（9 月 15 日），以及交互数据集、可复现下载、仓库整理和中英双语病例本地化（2026 年 9 月 16 日）。

仓库内的临床 QA 表仍有 **10 项待审核**。生成审核页面或通过工程测试不代表已经完成医学裁定。本地探索报告仅包含三个模型在一个病例上的运行结果，不能视为排行榜或总体性能估计。

## 数据集覆盖

以下数字来自当前本地清单，并不表示仓库会分发对应患者记录。系统只加载清单中的病例；生成目录中的遗留文件不会增加病例总数。

| 轨道 | 病例数 | 含义 |
| --- | ---: | --- |
| DDXPlus | 50 | 标准答案证据暴露树；包含 223 个证据字段和 49 个目录疾病 |
| Synthea | 50 | 与就诊关联的观察、操作和用药记录 |
| MedAgentBench | 30 | 离线任务/工作流回放；不执行实时 FHIR 操作 |
| MC-MED | 10 | 基于源数据的急诊首诊病例 |
| MIMIC-IV 多模态 | 10 | 关联 Note、ECG 和 ED 模态的住院病例 |
| eICU-CRD | 10 | ICU 早期临床评估 |
| PMC Case Reports | 5 | 暂定的叙事序列病例 |
| NEJM CPC | 5 | 暂定的 PubMed 记录叙事病例 |
| MediScope | 3 | 多模态问诊 |
| MedPI | 3 | 多轮问诊 |
| PatientSim | 3 | 官方公开演示患者档案 |
| Meddies Persona VIE | 3 | 越南语患者画像 |
| MedMemoryBench | 3 | 纵向医疗记忆 |
| MedDialogRubrics | 3 | 与源事实匹配的专家问诊参考 |
| **合计** | **188** | **130 个经典病例 + 58 个时序/交互病例** |

MIMIC Note、ECG 和 ED 是关联模态，不单独计为数据轨道。交互数据的参考标签均明确标记为未经独立临床裁定。详情见 [Temporal MVP 状态](docs/temporal_v2_mvp.md)和[交互 MVP 约定](docs/interaction_mvp.md)。

## 快速开始

### 1. 安装并构建公开经典轨道

仓库自带的启动脚本面向 **macOS（Apple Silicon 或 Intel）**，并安装项目内独立的 Node 运行环境。需要 Python **3.9+**。其他平台请自行提供兼容的 Node（**22.13+**），并直接安装 Python 和前端依赖；当前 Node 启动脚本下载的是 macOS 二进制文件。

```bash
git clone https://github.com/ZaneLing/ClincForestBench.git
cd ClincForestBench
make setup
./download_data.sh core
make preprocess-ddxplus
make preprocess-guidance2
```

以上命令会构建 130 个经典病例。下载的输入和生成的输出均保留在本地。下载器默认的 `all` 配置包含公开核心数据和交互数据，但**不会**下载需要授权的 PhysioNet 数据源。

### 2. 运行应用

分别在两个终端中启动：

```bash
make api
```

```bash
make web
```

打开[应用](http://localhost:3000)或 [API 文档](http://localhost:8000/docs)。注册本地医生账户后即可进入 Arena。

本地开发使用位于 `data/clincforestbench.db` 的 **SQLite** 数据库，因此账户、经典病例会话和模型运行记录在 API 重启后仍会保留。时序会话和模型运行记录保存在 `data/processed/temporal/v2/`。测试使用隔离的内存仓库或临时数据库。

模型测试还需要在本地 `.env` 中配置 `OPENROUTER_API_KEY`。可从 `.env.example` 开始，替换其中占位值；多人使用时还应设置私有的 `RESEARCH_API_KEY`。独立的服务商连通性探测使用 `tools/api_smoke/.env`。密钥仅由后端加载，不会写入导出的模型交互记录。

### 3. 添加时序和交互轨道

重新构建全部 188 个病例需要取得相应受限数据集的访问许可，同时准备公开数据源。获得许可并配置 PhysioNet 凭据后运行：

```bash
./download_data.sh restricted
./download_data.sh interaction
make preprocess-temporal
make preprocess-interaction-mvp
```

必须先构建基础 Temporal 清单，再合并交互数据。重新构建基础清单会覆盖原清单，因此之后需要再次运行交互构建步骤。数据源要求和下载配置见[数据准备说明](docs/data_setup.md)。

### 4. 验证

```bash
make test       # Python 测试
make validate   # Python 测试、前端静态检查和前端生产构建
make demo       # 命令行 Arena 演示
```

完整测试套件依赖已生成的经典、时序和交互产物。请在完整数据准备后运行；仅构建公开经典轨道并不足以形成完整测试环境。

## 应用路由

| 路由 | 用途 |
| --- | --- |
| `/` | 动态基准概览 |
| `/arena` | 医生 Arena 和轨道选择 |
| `/model-arena` | OpenRouter 模型测试和轮次检查 |
| `/history` | 当前医生已完成的会话 |
| `/forest` | 聚合参与者路径和诊断分布 |
| `/research` | 原始来源、转换后病例及病例树审计 |
| `/evidence` | 数据集约定、映射和证据词典 |
| `/admin` | 由研究密钥保护的本地账户管理 |
| `/temporal?mode=arena` | 时序医生 Arena |
| `/temporal?mode=timeline` | 已记录源轨迹回放 |

模型测试、历史、森林和研究路由均可通过 `?mode=temporal` 进入时序模式。全局 `EN / 中文` 开关会同时切换界面文案和病例内容。完整的交互规则、导出、结果对比和本地化说明见[应用指南](docs/application_guide.md)。

## 仓库结构

| 路径 | 内容 |
| --- | --- |
| `backend/`、`frontend/` | FastAPI 服务，以及基于 Vinext/Vite 的 React/TypeScript 界面 |
| `etl/`、`analysis/` | 数据源转换、校验、指标和快照 |
| `configs/`、`migrations/`、`tests/` | 配置约定、数据库迁移历史和验证 |
| `docs/`、`examples/` | 文档和可审计的小型示例 |
| `scripts/`、`tools/` | 下载、环境启动、演示辅助程序及独立工具 |
| `locales/cases/` | 纳入版本控制的公开中英文病例词典 |
| `dataset/` | 本地源数据及纳入版本控制的来源说明 |
| `data/` | 纳入版本控制的小型清单，以及被忽略的生成产物和数据库 |
| `model/` | 可选本地模型权重及小型模型元数据 |

Git 管理规则见[仓库结构说明](docs/repository_layout.md)。本地编辑器设置、密钥、依赖、构建缓存、模型权重和患者级衍生产物均不会同步。受限数据的翻译保存在 `data/processed/locales/cases/`。

## 保真度与发布边界

- 活跃的经典病例会话只暴露已观察证据，不暴露隐藏真值或标准答案诊断。只有完成病例后才解锁结果对比；研究和模型路由需要研究密钥。
- DDXPlus 病例树表达的是证据暴露过程，不是已记录的医生诊疗时间线。五个已知的证据父级缺失引用和重复记录数量均作为上游例外进行版本管理和漂移检查。
- MedAgentBench 当前使用 `OFFLINE_TASK_REPLAY`，不会声称 FHIR 请求真实返回了结果或创建了资源。
- 已记录结果按原值回放，不生成虚构结果。缺失动作会解析为 `UNOBSERVED_IN_RECORDED_EPISODE`。
- PMC/NEJM 的展示顺序代理值不代表真实临床耗时。叙事和交互参考标签需要经过临床审核后才能用于正式评分。
- 当前 MVP 的本地账户管理会暴露明文密码。请只使用临时密码，并在共享或生产部署前替换该存储方式。

本项目仅用于研究，不是医疗诊断设备。

## PostgreSQL 开发配置

在宿主机上生成所需产物后运行：

```bash
cp .env.example .env  # 仅在本地尚无 .env 时执行，并编辑其中配置
docker compose up --build
```

Compose 配置使用 PostgreSQL、执行数据库迁移，并挂载本地 `data/` 和只读的 `dataset/`。当前 SQLAlchemy 数据结构包含 **21 张表**；数据库初始化会加载可用的经典 MVP 清单（完成两个经典构建步骤后共 130 个病例），而不是加载完整源数据人群。时序产物仍使用本地文件存储。此配置用于开发，不是生产部署方案。

## 项目文档

- [文档索引](docs/README.md)
- [应用指南](docs/application_guide.md)
- [数据准备和下载配置](docs/data_setup.md)
- [架构及 API/数据边界](docs/architecture.md)
- [病例树结构](docs/case_tree_schema.md)
- [Temporal MVP 状态](docs/temporal_v2_mvp.md)及[交互 MVP](docs/interaction_mvp.md)
- [设计到代码的追踪表](docs/guidance_traceability.md)
- [原始设计指南](docs/guides/README.md)
