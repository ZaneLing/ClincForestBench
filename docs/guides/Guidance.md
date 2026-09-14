# ClincForestBench：基于 DDXPlus 的临床决策游戏与动态森林 MVP 工程指南

## 0. 项目目标

### 0.1 第一阶段不是做“完整临床模拟器”

DDXPlus 适合构建的是：

> **基于病史证据逐步获取的临床推理与鉴别诊断游戏环境。**

它不包含真实实验室检查、影像检查、药物干预以及治疗后患者状态变化，因此在 DDXPlus 阶段：

- `Action` 定义为：主动询问或获取一个临床证据；
- `Observation` 定义为：患者针对该证据的真实预设回答；
- `Belief` 定义为：医生当前鉴别诊断及置信度；
- `State` 定义为：当前已经暴露给医生的信息集合；
- `Outcome` 定义为：最终诊断、诊断排序、信息获取效率等；
- 多个医生对同一病例产生的不同查询路径组成病例级临床决策图；
- 多个病例的图组成 Clinical Decision Forest，即“临床决策森林”。

DDXPlus 包含约 130 万个合成患者、49 种疾病和 223 类临床证据，其中包括 110 类症状和 113 类既往史/危险因素。证据既包含二元信息，也包含分类和多选信息；每个患者平均约有 13.6 条实际证据，并提供真实疾病、初始证据及带概率的参考鉴别诊断。citeturn107040search12turn417256view2

DDXPlus 原始项目与数据定义应作为整个预处理实现的唯一上游规范。citeturn107040search0turn139617academia24

---

# 1. 整个系统首先固定四个概念

不要直接把 DDXPlus CSV 变成网页。

先建立四层严格分离的数据概念：

```text
Truth
完整患者真实状态
        ↓
Observation
医生目前已经看到的信息
        ↓
Action
医生下一步主动获取什么证据
        ↓
Belief
医生当前认为病人可能是什么疾病
```

分别定义如下。

## 1.1 Truth：患者完整真实状态

对于病例 \(i\)：

\[
T_i =
\{
年龄,
性别,
真实疾病,
全部证据,
参考鉴别诊断
\}
\]

这一层永远不能在游戏过程中直接暴露。

---

## 1.2 Observation：医生当前可见信息

在第 \(t\) 步：

\[
O_t =
\{
年龄,
性别,
初始主诉,
已经询问获得的证据
\}
\]

游戏开始时：

```text
O0 =
年龄
+ 性别
+ Initial Evidence
```

之后：

```text
O1 = O0 + Evidence A
O2 = O1 + Evidence B
O3 = O2 + Evidence C
```

---

## 1.3 Action：医生主动做什么

DDXPlus 第一阶段只允许：

```text
ASK_EVIDENCE
SUBMIT_BELIEF
FINAL_DIAGNOSIS
STOP
```

其中真正改变患者可见状态的只有：

```text
ASK_EVIDENCE
```

例如：

> 是否咳嗽？

> 疼痛是什么性质？

> 是否吸烟？

> 是否近期旅行？

不是：

> 查 CBC。

不是：

> 做 CT。

这些属于之后 MIMIC 环境。

---

## 1.4 Belief：医生当前临床判断

Belief 不属于 Patient State。

同样的患者信息状态：

```text
State S
```

Doctor A 可能认为：

```text
Pneumonia 60%
Influenza 25%
Bronchitis 15%
```

Doctor B 可能认为：

```text
Influenza 50%
URTI 30%
Pneumonia 20%
```

因此：

> **State 是客观观察状态；Belief 是医生内部判断。**

数据库必须分开存储。

这是以后研究：

- 临床先验；
- 信念更新；
- 专科差异；
- 信息增益；
- 医生—AI 差异；

的基础。

---

# 2. DDXPlus 原始数据首先怎样处理

## 2.1 原始数据永久只读

建立：

```text
data/
├── raw/
│   └── ddxplus/
│       └── original/
│           ├── release_train_patients.csv
│           ├── release_validate_patients.csv
│           ├── release_test_patients.csv
│           ├── release_evidences.json
│           └── release_conditions.json
│
├── processed/
│
├── manifests/
│
└── exports/
```

原则：

> **任何代码都不得修改 raw 文件。**

处理后数据必须写入新的版本目录：

```text
data/processed/ddxplus/v1/
```

---

# 3. 第一张基础表：Evidence Catalog

DDXPlus 的 `release_evidences.json` 需要首先被转换成统一的证据目录。

每一个 evidence 建议至少存：

```text
evidence_id
question_en
is_antecedent
data_type
default_value
possible_values
value_meanings
code_question
parent_evidence_id
is_root_question
semantic_role
exposure_tier
mapping_version
```

---

## 3.1 三种原始证据类型必须原样保留

### Binary：二元证据

例如：

```text
Does the patient have fever?
→ Yes / No
```

内部：

```text
data_type = binary
```

---

### Categorical：分类证据

例如：

```text
What color is the rash?
→ red
→ pink
→ pale
...
```

内部：

```text
data_type = categorical
```

---

### Multi-choice：多选证据

例如某个症状可能同时出现在多个位置：

```text
location:
- forehead
- cheek
- temple
```

内部必须保存为：

```json
["forehead", "cheek", "temple"]
```

禁止拆成三个互相独立的症状。

DDXPlus 官方定义本身就允许同一个 evidence 出现多个 `_@_value` 项。citeturn417256view2

---

# 4. Evidence token 必须先完全标准化

原始患者文件可能出现：

```text
E_54_@_V_161
E_54_@_V_183
E_56_@_4
E_91
```

实现统一解析器：

```text
parse_evidence_token(token)
```

规则：

### 二元

```text
E_91
```

解析成：

```json
{
  "evidence_id": "E_91",
  "value": true
}
```

### 带值证据

只按照第一次：

```text
_@_
```

进行 split。

例如：

```text
E_56_@_4
```

→

```json
{
  "evidence_id": "E_56",
  "value": "4"
}
```

禁止假设 value 一定以 `V_` 开头。

---

## 4.1 Multi-choice 合并

如果患者拥有：

```text
E_55_@_V_89
E_55_@_V_108
E_55_@_V_167
```

最终 Case Truth 中只能生成一个对象：

```json
{
  "evidence_id": "E_55",
  "values": [
    "V_89",
    "V_108",
    "V_167"
  ]
}
```

不能生成三个 Evidence Node。

---

# 5. 重建 DDXPlus 的证据层级关系

这是整个项目非常重要的一步。

DDXPlus 中：

```text
code_question
```

本身包含问题之间的依赖关系。

例如：

```text
Do you have a rash?
        ↓ YES
What color is the rash?
        ↓
Where is the rash?
```

官方定义明确说明，具有相同 `code_question` 的证据属于相关问题组，某些子证据只有在对应基础证据被激活后才有意义。citeturn729968view1

因此建立：

```text
Evidence Question Graph
```

至少包含：

```text
parent_evidence_id
child_evidence_id
activation_condition
```

---

## 5.1 游戏规则

如果：

```text
Rash = No
```

则：

```text
Rash color
Rash location
Rash size
```

不能继续被询问。

应返回：

```text
NOT_APPLICABLE
```

而不是：

```text
No
```

这是医学语义上完全不同的状态。

---

# 6. 每一个 Case 不应该只是保存“阳性证据”

这是整个数据处理最重要的要求之一。

原始 DDXPlus `EVIDENCES` 主要保存患者实际生成出来的非默认证据。

但游戏运行需要知道：

> 医生问一个不在 EVIDENCES 里的东西时，患者怎么回答？

因此，对**进入 Benchmark 的病例**必须构造：

# Dense Case Truth Table

也就是针对全部 223 类 evidence 建立患者级查询真值。

例如：

| Case | Evidence | 状态 | Value |
|---|---|---|---|
| P001 | Fever | Positive | Yes |
| P001 | Cough | Positive | Yes |
| P001 | Smoking | Negative | No |
| P001 | Rash | Negative | No |
| P001 | Rash color | Not Applicable | — |
| P001 | Pain intensity | Present | 7 |

标准状态统一为：

```text
PRESENT
ABSENT
VALUE
DEFAULT
NOT_APPLICABLE
```

---

## 6.1 为什么必须做 Dense Truth

否则后面会不断出现：

> “这个患者到底有没有被问过这个问题？”

> “没有记录是不是 No？”

> “这个 multi-choice 到底有几个值？”

这些问题会污染整个行为分析。

---

## 6.2 不需要给 130 万患者全部展开成 223 行

这会产生约：

```text
1.3M × 223
```

条记录。

没有必要。

整个训练数据维持 sparse representation。

只有：

> **被选入 ForestBench 的正式 Case**

才建立 Dense Truth Table。

例如 500 cases：

```text
500 × 223 = 111,500
```

完全可控。

---

# 7. 建立标准 Case Object

每个正式病例必须最终生成固定版本的：

```text
case_bundle.json
```

建议结构：

```json
{
  "case_id": "DDX_TEST_000001",
  "dataset": {
    "name": "DDXPlus",
    "split": "test",
    "dataset_version": "original_en",
    "pipeline_version": "v1"
  },

  "demographics": {
    "age": 57,
    "sex": "M"
  },

  "initial_evidence": {
    "evidence_id": "E_xxx",
    "response": {}
  },

  "truth": {
    "evidences": []
  },

  "oracle": {
    "pathology": "...",
    "severity": 2,
    "differential": [
      {
        "condition": "...",
        "probability": 0.32
      }
    ]
  },

  "metadata": {
    "evidence_count": 18,
    "symptom_count": 13,
    "antecedent_count": 5,
    "nonbinary_count": 4,
    "differential_entropy": 1.82,
    "branchability_score": 0.77
  }
}
```

其中：

```text
truth
oracle
```

任何活跃游戏 API 都不得直接返回给前端。

---

# 8. 不要直接把 Initial Evidence 当自然语言主诉

DDXPlus 英文版 evidence ID 是非语义编码。

每个 evidence 有：

```text
question_en
```

因此 MVP 最稳妥的表达方式是：

```text
Initial clinical information

Age: 57
Sex: Male

Patient reports:
[deterministically formatted initial evidence]
```

不要第一版使用 LLM 把它改写成“像患者一样说话”。

否则会引入第二个不必要变量：

> patient language generation。

第一版环境必须 deterministic，即完全确定。

---

# 9. 为后续“分层暴露”提前建立 Evidence Semantic Layer

这是你后面研究先验和信息更新必须提前做的。

不能只有：

```text
E_72
E_94
E_103
```

需要另外建立：

```text
evidence_semantics.csv
```

至少增加：

```text
evidence_id
clinical_domain
semantic_role
is_root
parent_id
research_tier
curation_source
curation_version
```

---

# 10. Evidence 的最小医学分类

第一版不要过度细分。

可靠的自动分类只有：

```text
SYMPTOM
ANTECEDENT
```

以及：

```text
ROOT
ATTRIBUTE
```

进一步建议人工校准：

```text
PRESENTING_SYMPTOM
SYMPTOM_ATTRIBUTE
ASSOCIATED_SYMPTOM
PERSONAL_HISTORY
FAMILY_HISTORY
EXPOSURE_RISK
OTHER_ANTECEDENT
```

不要让 LLM 临时分类。

如果使用模型辅助分类：

1. 模型生成候选标签；
2. 输出到 CSV；
3. 人工复核；
4. 固定版本；
5. Arena 只读取固定映射。

---

# 11. Exposure Tier：提前为“信息逐层暴露实验”设计

DDXPlus 没有真实临床时间顺序。

因此：

> **不能声称 Tier 1、Tier 2、Tier 3 是患者真实就诊顺序。**

它们只能定义成：

> Research Exposure Protocol，即“研究用信息暴露协议”。

建议：

### Tier 0：初始状态

```text
年龄
性别
INITIAL_EVIDENCE
```

---

### Tier 1：初始症状详细信息

和初始主诉处于同一 question group 的：

```text
性质
位置
程度
相关描述
```

---

### Tier 2：其他症状

```text
associated symptoms
```

---

### Tier 3：既往史和危险因素

```text
antecedents
exposure
family history
...
```

---

### Tier 4：完整病例历史

所有可查询信息。

---

# 12. 因此 Arena 必须从一开始支持三种模式

这非常重要。

## Mode A：自由探索模式

医生决定：

> 下一步问什么？

形成真实决策森林。

---

## Mode B：标准分层暴露模式

系统按照：

```text
Tier 0
↓
Tier 1
↓
Tier 2
↓
Tier 3
```

逐层提供信息。

每一层后采集一次诊断判断。

用于研究：

> 少量信息时医生/模型如何形成先验？

> 哪层信息造成最大信念更新？

---

## Mode C：锚点状态模式

给所有医生完全相同：

```text
State S
```

然后问：

> 下一步你最想获取什么？

这是未来研究：

```text
专科
资历
模型
医生
```

差异时最严谨的模式。

---

# 13. DDXPlus 的“先验”必须定义清楚

后续不要把 DDXPlus 的疾病频率称为：

> “真实医学疾病患病率”。

DDXPlus 是合成数据，患者来自专有知识库和规则系统，其人口结构也与生成设定有关。citeturn107040search13

因此统一命名：

> **DDXPlus empirical prior：DDXPlus 数据经验先验**

---

# 14. 至少预计算三套先验

只使用 TRAIN split 计算。

严禁用 validation/test case 本身重新估计。

## 14.1 全局疾病先验

\[
P(C)
\]

---

## 14.2 人口学条件先验

\[
P(C|Age,Sex)
\]

年龄区间写入 config，例如：

```text
0–4
5–17
18–39
40–64
65+
```

---

## 14.3 初始证据条件先验

\[
P(C|Age,Sex,E_0)
\]

用于研究：

> 医生仅看到患者初始情况时，判断和数据经验先验之间有什么关系？

---

# 15. 建立一个 Analysis-only Reference Bayesian Model

为了以后分析每一条证据产生了多少信息增益，可以建立一个简单参考模型。

训练集计算：

\[
P(E=e|C)
\]

然后给定当前观察集合：

\[
O_t
\]

估计：

\[
P(C|O_t)
\]

第一版可以使用：

> Naive Bayes（朴素贝叶斯）

并使用固定平滑参数。

注意：

这个模型：

- 不是医生；
- 不是 benchmark gold standard；
- 不参与 Arena；
- 只用于事后计算参考信息变化。

例如：

```text
Step 0:
Pneumonia 0.18

Ask fever → Yes

Step 1:
Pneumonia 0.31
```

则可以计算：

```text
Evidence Information Gain
```

---

# 16. DDXPlus 自带 Differential Diagnosis 应怎样使用

DDXPlus 每个患者提供：

```text
DIFFERENTIAL_DIAGNOSIS
```

例如：

```text
Pneumonia        0.31
Bronchitis       0.21
Influenza        0.18
...
```

它应该定义成：

> **Oracle Reference Differential：数据集参考鉴别诊断**

而不是：

> 医生正确思维过程。

游戏时完全隐藏。

Session 完成后才用于：

- Top-K coverage；
- final diagnosis comparison；
- differential rank；
- differential entropy；
- physician vs dataset differential；
- model vs dataset differential。

---

# 17. Case Selection 不要随机抽 100 个患者就结束

需要构建：

# Case Quality Profile

每个 patient 计算：

```text
evidence_count
symptom_count
antecedent_count
independent_root_count
child_attribute_count
nonbinary_count
differential_size
differential_entropy
top1_probability
top1_top2_margin
condition_severity
initial_evidence_type
```

---

# 18. 建立 Branchability Score

用于选择“容易形成森林”的 case。

例如综合：

```text
独立症状数量
+
层级症状数量
+
鉴别诊断不确定性
+
非二元信息数量
+
总可获取证据数量
```

可以定义工程采样指标：

\[
B_i =
w_1R_i +
w_2H_i +
w_3D_i +
w_4N_i +
w_5E_i
\]

但：

> Branchability Score 只是选 case 的工具，不作为论文核心医学指标。

原始组成变量必须全部保留。

---

# 19. 第一批 Case 推荐

不要马上用整个测试集。

建立：

```text
MVP-50
```

建议：

- 30–50 个病例；
- 覆盖不同疾病；
- 每个病例至少 8–10 条真实证据；
- 优先 Differential Diagnosis ≥3；
- 优先中高 differential entropy；
- 至少若干非 binary evidence；
- 尽量排除只有极少信息即可确定诊断的 trivial cases；
- INITIAL_EVIDENCE 优先选择症状，而不是 antecedent。

第二阶段再构建：

```text
Benchmark-500
```

---

# 20. 正式 Dataset Split 原则

推荐：

```text
TRAIN
→ 只用于计算数据先验、证据条件概率、开发分析模型

VALIDATE
→ 开发 Arena 和调试

TEST
→ 正式医生/模型 benchmark
```

正式评估病例尽量来自原始 test split。

---

# 21. Arena 核心状态机

游戏核心不要写在前端。

后端实现：

```text
CaseEnvironment
```

主要状态：

```text
READY
ACTIVE
COMPLETED
ABORTED
```

---

# 22. 一个 Session 的完整循环

## Step 0

创建：

```text
Session
```

加载：

```text
Age
Sex
Initial Evidence
```

形成：

```text
State S0
```

要求医生先提交一次：

```text
Initial Differential
Initial Confidence
```

这个动作非常重要。

因为它就是：

> 医生的临床先验。

---

## Step 1

医生选择：

```text
ASK_EVIDENCE
```

例如：

> Do you have shortness of breath?

---

## Step 2

Backend：

1. 验证 Evidence 是否存在；
2. 检查 parent dependency；
3. 查询 Case Truth；
4. 返回 deterministic response；
5. 写 Event；
6. 创建新的 Observation State；
7. 计算新的 state hash。

---

## Step 3

医生可以：

```text
继续询问
```

或者更新：

```text
Differential Diagnosis
Confidence
```

---

## Step N

医生选择：

```text
FINAL_DIAGNOSIS
```

并填写：

```text
Primary diagnosis
Confidence
Optional differential
```

Session 锁定。

---

# 23. Belief Capture 必须做成可配置模式

真实医生以后如果每一步都填 differential，负担过重。

因此设计：

```text
belief_capture_mode
```

支持：

### every_step

每获取一个 Evidence 后填。

适合你自己模拟医生测试。

---

### checkpoint

例如：

```text
Step 0
Step 3
Step 6
Final
```

---

### on_change

医生主动点击：

> Update differential

---

### tier_based

每完成一个 Exposure Tier 后提交。

---

# 24. 医生提交的鉴别诊断不要只是字符串

统一结构：

```json
{
  "diagnoses": [
    {
      "condition_id": "...",
      "rank": 1,
      "probability": 0.60
    },
    {
      "condition_id": "...",
      "rank": 2,
      "probability": 0.25
    }
  ],
  "overall_confidence": 0.72
}
```

第一版诊断只能选择 DDXPlus 49 个 conditions。

以后真实临床环境再允许自由文本。

---

# 25. Graph Node 到底是什么

这一点要提前定义正确。

Clinical Decision Graph 中：

> **Node 不应该是某个医生本人，也不应该包含医生 belief。**

Node 定义：

\[
Node =
Case
+
Observed Evidence Set
\]

例如：

```text
Age 55
Male
Chest pain
Fever = no
Dyspnea = yes
```

就是一个 Node。

---

# 26. State Hash

定义：

```text
state_hash =
HASH(
 case_id
 +
 sorted(revealed_evidence_responses)
)
```

注意：

> Evidence 按 ID 排序后 hash。

因此：

```text
Doctor A:
Fever → Cough

Doctor B:
Cough → Fever
```

最终到达相同信息集合时：

```text
state_hash 相同
```

所以可以合并成一个 canonical information node。

---

# 27. 但是顺序信息绝不能丢

因此系统同时保存两种结构。

## Structure A：Trajectory

严格保留：

```text
Fever
↓
Cough
↓
Smoking
↓
Diagnosis
```

用于分析：

- 信息获取顺序；
- path length；
- temporal belief update；
- physician strategy。

---

## Structure B：Information-state DAG

如果两个医生最终得到相同 evidence set：

```text
合并成同一个 Node
```

用于研究：

- 相同状态下医生下一步如何分叉；
- branch entropy；
- action distribution。

---

# 28. DDXPlus 第一版严格说是 DAG，而不是环图

因为：

```text
Observation
```

只会不断增加。

状态不会删除已经知道的信息。

因此：

\[
S_t \subseteq S_{t+1}
\]

不会真正形成 clinical cycle。

如果医生重复询问同一个问题：

```text
ASK fever
ASK fever again
```

系统：

- 记录 repeat event；
- 返回相同答案；
- State Hash 不改变。

这种行为可以记录为 self-loop，但默认 Forest Visualization 中不显示。

以后 MIMIC / longitudinal management 环境才可能出现真正循环。

---

# 29. Forest 的定义

一个患者：

```text
Case Graph
```

例如：

```text
                  Fever
                /
S0 ───────── Cough
                \
                  Smoking
```

几十名医生以后：

```text
edge:
action
support
percentage
specialty_distribution
experience_distribution
```

例如：

```text
S0 → Ask Fever

support = 12
ED = 7
IM = 3
Cardiology = 2
```

所有病例：

```text
Case Graph 1
Case Graph 2
...
Case Graph N
```

共同构成：

> Clinical Decision Forest。

---

# 30. 数据库架构

推荐：

> PostgreSQL 作为 Arena operational database。

不要使用 SQLite 作为正式版本。

---

# 31. 数据层建议分为两部分

## Offline Analytical Warehouse

使用：

```text
Parquet
+
DuckDB
```

保存：

- 全部 DDXPlus 处理结果；
- train statistics；
- priors；
- case quality；
- benchmark manifests。

---

## Arena Database

PostgreSQL 只保存：

- benchmark cases；
- player；
- session；
- events；
- belief；
- states；
- graph；
- configuration。

这样不会把 130 万 patient 全塞进在线数据库。

---

# 32. PostgreSQL 主要表

至少建立：

```text
dataset_versions

evidence_catalog
evidence_hierarchy
condition_catalog

case_manifests
cases
case_evidence_truth
case_oracle_differential

players

sessions
session_events
state_snapshots
belief_snapshots

case_graph_nodes
case_graph_edges

experiment_configs
analysis_versions
```

---

# 33. Player Table

未来医生数据提前支持：

```text
player_id
player_type
specialty
training_level
years_experience
site
country
```

其中：

```text
player_type:
RESEARCHER
PHYSICIAN
MODEL
```

第一版你自己玩：

```text
RESEARCHER
```

以后可以直接变：

```text
PHYSICIAN
```

完全不用修改 schema。

---

# 34. Session Table

保存：

```text
session_id
case_id
player_id

arena_mode
belief_capture_mode

started_at
completed_at

dataset_version
case_version
arena_version
ui_version

random_seed
status
```

---

# 35. 最重要的表：Session Events

整个系统采用：

# Event Sourcing

原则：

> **事件永远追加，不修改过去。**

例如：

```json
{
  "event_id": "...",
  "session_id": "...",
  "sequence": 4,

  "event_type": "ASK_EVIDENCE",

  "action": {
    "evidence_id": "E_91"
  },

  "observation": {
    "response_type": "binary",
    "value": true
  },

  "state_before_hash": "...",
  "state_after_hash": "...",

  "server_timestamp": "...",
  "client_timestamp": "...",

  "latency_ms": 4300,

  "schema_version": "1.0"
}
```

---

# 36. 为什么 Event Sourcing 对你的研究极其重要

以后突然想研究：

> 医生第几步开始收敛？

不需要重新跑病例。

研究：

> 哪个 evidence 最容易改变 diagnosis？

不需要重新跑。

研究：

> 第一次 inquiry 是否受到 age/sex 先验影响？

不需要重新跑。

研究：

> 医生是不是出现 confirmation bias（确认偏差）？

仍然不需要重新跑。

因为完整的：

```text
State
Action
Observation
Belief
Timestamp
```

都已经存在。

---

# 37. State Snapshot 同时保留

虽然 Event Log 可以重建所有 State，但建议每步另外缓存：

```text
state_snapshots
```

字段：

```text
session_id
step
state_hash

revealed_evidence_ids
revealed_evidence_values

created_at
```

Event 是最终事实来源。

Snapshot 是方便查询和分析的 cache。

---

# 38. Belief Snapshot 独立保存

```text
belief_id
session_id
step
state_hash

diagnosis_id
rank
probability
overall_confidence

timestamp
```

不要存在 event JSON 里就结束。

必须另外规范化成表。

---

# 39. 前端架构

推荐：

```text
Next.js
React
TypeScript
```

---

# 40. Arena 主页面布局

建议三列。

## 左侧：Patient State

显示：

```text
Patient

Age
Sex

Initial presentation

Known symptoms
Known symptom characteristics
Known antecedents
```

只显示已经获得的信息。

---

## 中间：Clinical Interaction

核心操作区域：

```text
Ask next question
```

### MVP 不使用自由文本 NLP 映射

医生输入：

```text
cough
```

系统 autocomplete：

```text
Do you have a cough?
```

医生点击 canonical evidence。

原因：

> 如果直接把自然语言交给 LLM 映射 Evidence，第一版会额外引入 action parsing error。

所以：

> **MVP = searchable structured question catalog。**

以后再增加自由文本。

---

# 41. Question Search 不能把答案泄漏给医生

Autocomplete 只显示：

```text
question text
```

不能显示：

```text
是否阳性
和哪个疾病相关
信息增益
出现概率
```

---

# 42. 右侧：Doctor Workspace

显示：

```text
Current Differential
Confidence
Number of Questions Asked
Personal Path
```

只允许看到：

> 自己的 path。

---

# 43. 游戏过程中绝对不能显示 Aggregate Forest

否则：

> Doctor B 会看到 Doctor A 做了什么。

研究立即受到污染。

所以：

```text
PLAYER VIEW
```

和：

```text
RESEARCHER VIEW
```

必须完全分开。

---

# 44. Research Dashboard

单独路由：

```text
/research
```

包括：

### Case Explorer

显示：

```text
完整 patient truth
oracle pathology
oracle differential
case metadata
```

---

### Session Explorer

显示：

```text
Doctor A

S0
↓ Fever
S1
↓ Cough
S2
↓ Smoking
S3
↓ Diagnosis
```

并同步展示 belief trajectory。

---

### Forest Explorer

建议使用：

```text
Cytoscape.js
```

或者：

```text
React Flow
```

展示：

```text
Node
Edge
Support
Branch probability
```

---

# 45. Forest 至少提供两种 Visualization

## Path Tree View

保留顺序：

```text
S0
├── Fever
│   ├── Cough
│   └── Smoking
└── Cough
    └── Fever
```

---

## Canonical State Graph

把相同 Evidence Set 合并：

```text
{Fever,Cough}
```

只有一个 Node。

---

# 46. Graph 必须支持 Filter

以后医生多了后，可以：

```text
All physicians
Emergency Medicine only
Cardiology only
Residents only
Attendings only
Models only
```

比较不同策略。

所以 Edge 必须能够统计 subgroup information。

---

# 47. Backend 建议

推荐：

```text
Python
FastAPI
Pydantic
SQLAlchemy
Alembic
PostgreSQL
```

---

# 48. 核心 Backend 模块

```text
domain/
├── case.py
├── evidence.py
├── environment.py
├── state.py
├── action.py
├── belief.py
└── graph.py

services/
├── case_service.py
├── arena_service.py
├── state_reducer.py
├── response_engine.py
├── graph_builder.py
└── export_service.py
```

---

# 49. Response Engine 必须 deterministic

定义：

```text
resolve(case, evidence_id)
```

同一个：

```text
case_id + evidence_id
```

永远得到同样回答。

禁止第一版调用任何 LLM。

---

# 50. Query Validation

收到 Evidence Query 后：

### 1. 是否存在？

不存在：

```text
INVALID_ACTION
```

### 2. 是否已经询问？

已经问过：

```text
REPEATED_QUERY
```

仍然记录事件。

### 3. 是否存在 Parent？

如果 Parent 未激活：

```text
DEPENDENCY_NOT_MET
```

### 4. 如果 Parent 已经为 Negative？

返回：

```text
NOT_APPLICABLE
```

### 5. 查询 Truth

返回：

```text
PRESENT
ABSENT
VALUE
```

---

# 51. API 最小集合

```text
POST /sessions
GET  /sessions/{id}

GET  /sessions/{id}/state

POST /sessions/{id}/actions/evidence
POST /sessions/{id}/beliefs
POST /sessions/{id}/finalize

GET /research/cases/{id}
GET /research/cases/{id}/graph
GET /research/sessions/{id}

POST /exports
```

---

# 52. 不要让 active-session API 返回 Oracle

例如：

```text
GET /sessions/{id}/state
```

永远不能返回：

```text
PATHOLOGY
DIFFERENTIAL_DIAGNOSIS
full evidence list
case quality
```

即使前端不展示，也不能返回。

否则 debug 时非常容易泄漏。

Oracle 使用：

```text
/research/*
```

单独权限。

---

# 53. 工程目录建议

```text
ClincForestBench/

├── frontend/
│   ├── app/
│   ├── components/
│   ├── features/
│   │   ├── arena/
│   │   ├── belief/
│   │   └── forest/
│   └── lib/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── domain/
│   │   ├── services/
│   │   ├── repositories/
│   │   ├── schemas/
│   │   └── models/
│   └── migrations/
│
├── etl/
│   ├── inspect_raw.py
│   ├── build_evidence_catalog.py
│   ├── build_condition_catalog.py
│   ├── normalize_patients.py
│   ├── compute_priors.py
│   ├── score_cases.py
│   ├── select_cases.py
│   └── build_case_bundles.py
│
├── analysis/
│   ├── case_quality/
│   ├── trajectories/
│   ├── belief_update/
│   ├── priors/
│   ├── branching/
│   └── physician_comparison/
│
├── configs/
│   ├── ddxplus.yaml
│   ├── case_selection.yaml
│   ├── exposure_protocols.yaml
│   └── arena.yaml
│
├── data/
│   ├── raw/
│   ├── processed/
│   ├── manifests/
│   └── exports/
│
├── tests/
│
├── docker-compose.yml
├── Makefile
└── README.md
```

---

# 54. 数据处理流水线

必须能够通过单条命令重建。

例如：

```text
make preprocess-ddxplus
```

依次执行：

```text
Raw validation
↓
Evidence catalog
↓
Condition catalog
↓
Patient normalization
↓
Train priors
↓
Case quality calculation
↓
Case selection
↓
Dense Case Truth
↓
Case Bundle
↓
Manifest
```

---

# 55. 每个处理阶段必须有版本

例如：

```text
dataset_version
pipeline_version
semantic_mapping_version
case_manifest_version
```

正式 session 同时记录这些版本。

---

# 56. Case Hash

每个正式 Case Bundle 生成：

```text
SHA256
```

保存：

```text
case_hash
```

这样以后数据更新后可以确定：

> Doctor A 和 Doctor B 玩的是不是完全相同版本的患者。

---

# 57. 导出体系

Session 完成后不要只生成一个 JSON。

至少支持：

```text
cases.parquet
sessions.parquet
events.parquet
states.parquet
beliefs.parquet
graph_nodes.parquet
graph_edges.parquet
```

另外提供：

```text
session_bundle.json
```

用于完整重放单个 session。

---

# 58. Analysis Snapshot

每次正式分析生成：

```text
analysis_runs/
└── analysis_v001/
    ├── metadata.json
    ├── case_metrics.parquet
    ├── session_metrics.parquet
    ├── state_metrics.parquet
    ├── edge_metrics.parquet
    └── figures/
```

metadata 记录：

```text
analysis_version
git_commit
dataset_version
manifest_version
timestamp
config
```

---

# 59. 第一阶段应该提前支持哪些分析

这是设计数据结构时必须反向考虑的。

---

## A. Clinical Prior Analysis

比较：

```text
医生 t=0 diagnosis
```

和：

```text
P(C)
P(C|Age,Sex)
P(C|Age,Sex,Initial Evidence)
```

回答：

> 医生在极少信息下主要依赖什么先验？

---

# 60. Belief Updating

对于每一步：

\[
B_t \rightarrow B_{t+1}
\]

计算：

```text
Top-1 change
Top-k change
probability shift
confidence shift
entropy change
```

可以知道：

> 哪个 evidence 最容易让医生改变判断？

---

# 61. Evidence Information Gain

参考模型计算：

\[
IG(E_t)
=
H(C|O_t)
-
H(C|O_{t+1})
\]

然后比较：

> 医生主动选择的信息是不是高信息价值信息？

---

# 62. Decision Efficiency

记录：

```text
number_of_questions
time_to_diagnosis
time_to_correct_top1
redundant_question_count
negative_query_count
```

---

# 63. Diagnostic Performance

至少：

```text
Final accuracy
Top-3 accuracy
Top-5 accuracy
Oracle differential coverage
Pathology rank
```

---

# 64. Branch Entropy

在同一个 canonical state：

\[
H(S)
=
-\sum_a P(a|S)\log P(a|S)
\]

用于找到：

> 医生意见最分裂的 decision fork。

---

# 65. Physician Policy Distribution

例如：

```text
State S

Ask fever      35%
Ask cough      25%
Ask smoking    15%
Ask dyspnea    15%
Other          10%
```

这就是：

\[
P_{\text{human}}(a|S)
\]

以后模型加入后比较：

\[
P_{\text{model}}(a|S)
\]

---

# 66. Path-level 分析

不要只分析单个 action。

保存完整 path 后，可以研究：

```text
平均 path length
unique path count
path overlap
sequence similarity
convergence point
divergence point
```

---

# 67. Confirmation Bias 未来也能分析

假设医生在 Step 2 已认为：

```text
Pneumonia 80%
```

后续是否只查询：

> 支持 pneumonia 的 evidence？

还是主动寻找：

> alternative diagnosis discriminators？

因为 action、belief、condition-evidence statistics 都完整保存，所以以后可以做，不需要重新跑。

---

# 68. Layered Exposure 实验

例如固定：

```text
Tier 0
→ physician belief

Tier 1
→ physician belief

Tier 2
→ physician belief

Tier 3
→ physician belief
```

计算：

\[
\Delta Belief_t
\]

以及：

\[
\Delta Confidence_t
\]

回答：

> 症状细节、其他症状、既往史分别贡献多少诊断信息？

---

# 69. 数据库设计要支持未来模型 Agent

`player_type` 已经有：

```text
MODEL
```

将来 Agent Session 额外记录：

```text
provider
model_name
model_version
temperature
top_p
seed
system_prompt_hash
prompt_template_version
raw_response
parsed_action
parser_version
```

因此医生和模型进入的是：

> 完全同一个 Environment。

---

# 70. 最重要的可复现原则

任何 Session 都必须可以仅通过：

```text
case_bundle
+
session_events
```

100% 重放。

需要实现：

```text
replay_session(session_id)
```

输出最终 state。

如果 replay 后 state hash 与数据库最终 state hash 不一致：

```text
TEST FAIL
```

---

# 71. 必须做的 Unit Tests

### Evidence parser

覆盖：

```text
binary
categorical
multi-choice
numeric value
```

---

### Hierarchy

验证：

```text
parent negative
→ child NOT_APPLICABLE
```

---

### State hash

验证：

```text
Fever → Cough
```

和：

```text
Cough → Fever
```

得到：

```text
同一个 canonical state hash
```

但 trajectory 不同。

---

### Oracle leakage

活跃 Session API response 中不得出现：

```text
PATHOLOGY
DIFFERENTIAL_DIAGNOSIS
unrevealed evidence
```

---

### Replay

所有 completed session：

```text
event replay
→ final_state_hash
```

必须一致。

---

### Idempotency

前端 double click 不允许产生两个完全相同操作。

每次操作提供：

```text
client_event_id
```

Backend 去重。

---

# 72. Data Quality Tests

正式建立 Benchmark 前自动输出：

```text
unknown evidence token count
invalid value count
missing condition count
invalid differential condition count
initial evidence not in evidence list count
hierarchy reference error count
duplicate case count
```

理想状态：

```text
0
```

如果非 0，pipeline 直接失败，而不是继续。

---

# 73. 医学人工 QA

随机抽取至少一批 Case Bundle 做人工检查：

检查：

```text
Initial evidence 是否合理
Question hierarchy 是否自然
Category response 是否正确
Multi-choice 是否正确
Not Applicable 是否正确
症状/既往史分类是否合理
```

生成：

```text
clinical_qa.csv
```

记录：

```text
case_id
reviewer
issue_type
severity
comment
status
```

不要直接修改数据库。

通过 mapping/version 修复后重新 build。

---

# 74. 第一个真正跑通的 End-to-End Loop

Codex 第一目标不是做漂亮 Dashboard。

必须先完成下面这一条链：

```text
选择一个 processed case
↓
创建 Session
↓
显示 Age + Sex + Initial Evidence
↓
填写 Initial Differential
↓
选择 Evidence A
↓
Backend 返回真实回答
↓
State 更新
↓
填写 Belief
↓
选择 Evidence B
↓
State 更新
↓
Final Diagnosis
↓
Session Complete
↓
Event Log 保存
↓
Session Replay 成功
↓
生成个人 trajectory
↓
同 Case 多次 Session 合并
↓
出现第一个 Case Decision Tree
```

只有这条完整跑通，才开始美化 UI。

---

# 75. 第一个 Demo 应该怎么测试

选一个 Evidence 丰富的 case。

你自己分别模拟三个医生策略。

### Session A：快速型

```text
S0
→ Ask high-value symptom
→ Ask second discriminator
→ Diagnosis
```

### Session B：广泛采集型

```text
S0
→ symptom
→ symptom
→ antecedent
→ symptom
→ diagnosis
```

### Session C：另一种假设

```text
S0
→ risk factor
→ associated symptom
→ symptom attribute
→ diagnosis
```

最后 Forest 页面应该自动出现：

```text
                    Action A
                  /
S0 ──────────── Action B
                  \
                    Action C
```

这就是第一版必须证明的核心。

---

# 76. 第二个 Demo：Layered Exposure

同一个 Case：

```text
Tier 0
```

提交 differential。

然后：

```text
Reveal Tier 1
```

提交 differential。

直到完整信息。

最后自动画：

```text
Diagnosis probability
       ↑
       │
       │
       │
       └──────── Evidence exposure stage
```

用于验证：

> 系统已经具备“先验—证据—信念更新”的研究能力。

---

# 77. 第三个 Demo：Canonical State Merge

设计两个 session：

```text
Session A:
Fever → Cough

Session B:
Cough → Fever
```

两者 trajectory 不同。

但最终：

```text
Observed Evidence Set
=
{Fever,Cough}
```

Forest DAG 必须自动 merge。

这是整个“临床决策图”而不仅仅是“游戏日志”的关键测试。

---

# 78. MVP 阶段不要做的事情

第一版暂时不要加入：

### 不做 LLM Patient Simulator

因为 DDXPlus 已经提供 truth。

---

### 不做自由文本 Action Parsing

避免多一个 NLP mapping error。

---

### 不做 Treatment

DDXPlus 没有对应数据。

---

### 不做 Lab / Imaging

DDXPlus 不能支持。

---

### 不让医生看到别人的 Forest

避免行为污染。

---

### 不训练诊断模型

第一目标是：

> Benchmark Environment。

不是模型性能。

---

# 79. 但是架构必须提前为 MIMIC 留接口

现在定义通用：

```text
ClinicalAction
```

DDXPlus：

```text
ASK_HISTORY_EVIDENCE
```

未来 MIMIC：

```text
ASK_HISTORY
ORDER_LAB
ORDER_IMAGING
REQUEST_ECG
CONSULT
DIAGNOSE
```

Observation 统一：

```text
ClinicalObservation
```

DDXPlus：

```text
patient_response
```

未来：

```text
lab_result
imaging_report
ecg
consult_note
```

因此：

> **Environment API 不要写死成 DDXPlus API。**

DDXPlus 只是：

```text
DDXPlusEnvironment implements ClinicalEnvironment
```

以后：

```text
MIMICEnvironment implements ClinicalEnvironment
```

---

# 80. 推荐核心 Interface

概念上定义：

```text
ClinicalEnvironment

reset(case_id)
get_state()
get_available_actions()
step(action)
finalize()
```

DDXPlus 实现：

```text
DDXPlusEnvironment
```

这样未来整个：

```text
Frontend
Session
Event
Belief
Forest
Analytics
```

全部不用重写。

---

# 81. 完整数据流

最终系统数据流应该固定为：

```text
DDXPlus Raw
        ↓
Immutable Raw Layer
        ↓
ETL / Validation
        ↓
Canonical Parquet Layer
        ↓
Evidence + Condition Catalog
        ↓
Case Quality & Priors
        ↓
Benchmark Manifest
        ↓
Case Bundles
        ↓
PostgreSQL Arena DB
        ↓
Clinical Environment
        ↓
FastAPI
        ↓
Doctor / Model Arena
        ↓
Immutable Event Log
        ↓
State + Belief Snapshots
        ↓
Case Decision Graph
        ↓
Clinical Decision Forest
        ↓
Parquet Export
        ↓
DuckDB / Python Analysis
        ↓
Versioned Analysis Results
```

---

# 82. Codex 的实施顺序

## Phase 1：数据理解和 ETL

完成：

```text
raw validator
evidence parser
hierarchy builder
condition parser
patient normalizer
```

输出 canonical Parquet。

---

## Phase 2：Case Builder

完成：

```text
case quality
priors
case selection
dense truth
case bundle
case hash
```

先生成：

```text
MVP-50
```

---

## Phase 3：Environment Engine

完成：

```text
reset
state
query
response
dependency
finalize
replay
```

先用 CLI 测试，不做网页。

例如：

```text
Patient 001

Age: 54
Sex: M
Initial symptom: ...

> ask E_17

Answer: Yes

> diagnose Pneumonia
```

---

## Phase 4：Database + API

完成：

```text
Session
Events
States
Beliefs
Clinical Environment API
```

---

## Phase 5：Arena Frontend

优先完成：

```text
Patient State
Question Search
Patient Answer
Differential Panel
Finish Session
```

---

## Phase 6：Forest Builder

多个 session 后：

```text
trajectory tree
canonical information-state graph
edge frequency
branch entropy
```

---

## Phase 7：Research Dashboard

加入：

```text
case explorer
session explorer
forest explorer
belief trajectory
basic metrics
```

---

## Phase 8：Export + Analysis

完成：

```text
Parquet exports
analysis snapshots
prior analysis
belief update
path analysis
branch analysis
```

---

# 83. MVP 验收标准

只有以下项目全部通过，才算 DDXPlus Arena 第一版完成：

- 原始 DDXPlus 可以一键预处理；
- Case 可以稳定版本化；
- 所有 Evidence 类型正确解析；
- hierarchy 正确；
- 每个正式 Case 都有完整 Truth representation；
- 游戏期间无 Oracle leakage；
- 一个 Session 可以完整完成；
- 每个 Action 都留下不可修改事件；
- Belief 可以逐步保存；
- Session 可以完整 replay；
- 相同信息状态可以通过 state hash merge；
- 多个 Session 可以形成 Case Graph；
- 多个 Case 可以组成 Forest；
- 数据可导出为 Parquet；
- 后续分析不需要重新运行 Arena；
- prior、belief update、branch entropy、path efficiency 至少可以从现有日志直接计算；
- Environment abstraction 没有写死 DDXPlus。

---

# 84. 第一版研究能力最终应该达到什么程度

当 MVP 完成后，应当能够直接回答：

### 病例层面

> 这个患者有哪些隐藏临床证据？

> 哪些证据属于症状、症状属性和既往史？

> 数据集给出的参考鉴别诊断是什么？

---

### 医生行为层面

> 医生第一步最想问什么？

> 医生用了多少步形成诊断？

> 哪些问题是重复或低价值的？

---

### 临床认知层面

> 在只有年龄、性别、初始症状时，医生的先验是什么？

> 哪一条信息最大程度改变了医生诊断？

> 什么时候形成 anchoring（锚定）？

> 什么时候重新调整 differential？

---

### 群体层面

> 同一个 State 下，不同医生选择 Action 的分布是什么？

> 哪些 State 是高度一致的？

> 哪些 State 是高分叉点？

---

### Forest 层面

> 一个病例有多少条不同诊断路径？

> 不同路径最后是否收敛？

> 哪些 Evidence 是共同必经信息？

---

### AI 层面

以后模型接入后，同样可以回答：

> AI 的初始先验与医生是否不同？

> AI 是否需要更多证据？

> AI 是不是过早锁定 diagnosis？

> AI 在哪些关键分叉点选择了与医生完全不同的 action？

---

# 85. 这一阶段最核心的研究思想

整个 DDXPlus MVP 不应该被理解成：

> “做一个 symptom checker。”

而应该被定义成：

> **建立一个可复现的、部分可观察的临床证据环境，在完全相同的潜在患者状态下，让不同决策者主动选择下一条临床证据，并完整记录证据获取顺序、诊断信念更新和最终决策，由多条独立轨迹经验性构建患者级临床决策图。**

DDXPlus 在这里的价值不是它能模拟完整医院。

而是它天然拥有：

```text
完整隐藏患者状态
+
初始信息
+
可查询证据
+
层级证据结构
+
真实疾病标签
+
参考鉴别诊断
```

因此特别适合验证：

```text
Latent Patient
↓
Partial Observation
↓
Clinical Action
↓
Evidence Reveal
↓
Belief Update
↓
Next Action
↓
Diagnosis
↓
Multi-player Decision Graph
```

这一整条 ClincForestBench 核心链路。

等这条链路稳定后，再迁移到 MIMIC：

```text
症状询问
→
实验室
→
ECG
→
影像
→
会诊
→
诊断
→
处置
```

届时变化的是临床环境复杂度，而不是 ForestBench 的基本数据范式。

---

# 86. 给 Codex 的最高优先级约束

实现过程中优先遵守以下原则：

1. **数据原始层不可修改。**
2. **Oracle 与 Observation 物理隔离。**
3. **所有游戏操作事件化、不可覆盖。**
4. **State 与 Belief 分离。**
5. **Trajectory 与 Canonical State Graph 同时保存。**
6. **每个 Case、Dataset、Mapping、Analysis 全部版本化。**
7. **第一版 Response Engine 完全 deterministic。**
8. **所有正式结果都必须可以 replay。**
9. **研究分析必须基于保存数据完成，不允许要求重新玩病例。**
10. **DDXPlus-specific logic 必须封装在 DDXPlusEnvironment，不能渗透整个系统。**
11. **任何医学语义人工映射都必须保存 mapping version 和 provenance。**
12. **所有未来医生、模型、专科、资历比较都必须建立在相同 Observation State 上。**

这 12 条比前端视觉效果优先级更高。