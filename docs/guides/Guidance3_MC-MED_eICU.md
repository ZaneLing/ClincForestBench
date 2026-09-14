
# ClincForestBench：MC-MED + eICU MVP 构建指令

## 目标

构建两个最小真实数据 MVP：

```text
MC-MED
→ 5 个急诊诊断病例
→ 每个病例生成可玩的 Clinical Decision Tree/DAG

eICU Demo
→ 5 个 ICU 早期评估病例
→ 每个病例生成可玩的 Clinical Decision Tree/DAG
```

统一输出到现有 ForestBench Arena。

---

# 一、下载数据

## 1. MC-MED

版本固定：

```text
MC-MED v1.0.1
```

首先检查用户是否已经取得 PhysioNet MC-MED 权限。

如果没有权限：

```text
STOP
```

提示用户进入 MC-MED PhysioNet 页面完成：

```text
Credentialed user
→ CITI Data or Specimens Only Research
→ Sign DUA
```

不要尝试绕过认证。

取得权限后，从 PhysioNet Files 页面使用官方 terminal download 命令。

### MVP 只下载这些

```text
visits.csv
pmh.csv
meds.csv
orders.csv
labs.csv
rads.csv
```

暂时不要下载：

```text
waveforms/
numerics.csv
```

波形和连续生命体征第二阶段再加。

MC-MED 官方确实提供上述顶层表，其中 `visits` 包含主诉和分诊生命体征，`orders` 包含医生医嘱及时间，`labs` 包含实验室结果，`rads` 包含影像及 Impression。citeturn157979view1

保存：

```text
data/raw/mcmed_v1_0_1/
```

---

## 2. eICU

MVP 首先使用完全公开的：

```text
eICU Collaborative Research Database Demo v2.0
```

从官方 Demo Files 页面直接下载。

只需要：

```text
patient.csv.gz
admissionDx.csv.gz
pastHistory.csv.gz
physicalExam.csv.gz
lab.csv.gz
diagnosis.csv.gz
treatment.csv.gz
medication.csv.gz
vitalPeriodic.csv.gz
```

这些文件在公开 Demo 中均存在。citeturn157979search1

保存：

```text
data/raw/eicu_demo_v2/
```

转换流程验证完成后，如果用户已有完整 eICU 权限，只需要把数据路径换成完整 eICU v2.0，不修改代码。

---

# 二、建立统一 Case Schema

两个 adapter 最终都必须输出：

```json
{
  "case_id": "",

  "source": {
    "dataset": "",
    "version": "",
    "source_case_id": ""
  },

  "task_type": "",

  "initial_state": {},

  "queryable_context": [],

  "hidden_evidence_pool": [],

  "realized_trajectory": [],

  "reference": {},

  "metadata": {}
}
```

禁止为两个数据集建立两套 Arena schema。

---

# 三、MC-MED 转换

## Step 1：以急诊就诊为 Case

使用：

```text
CSN
```

作为一次病例。

连接关系：

```text
visits.CSN
→ orders.CSN
→ labs.CSN
→ rads.CSN

visits.MRN
→ pmh.MRN
→ meds.MRN
```

---

## Step 2：筛选候选病例

第一版只选：

```text
Chest pain
或
Shortness of breath
```

优先只选其中一个主诉，如果病例数量足够，首选：

```text
Chest pain
```

要求：

```text
chief complaint 非空
triage vitals 基本完整
primary diagnosis 非空

>= 4 个 physician orders
>= 2 个不同 lab panels
>= 1 个 radiology study
```

计算：

```text
branchability_score
```

简单定义：

```text
unique_lab_panels
+ 2 × imaging_count
+ unique_order_types
+ PMH_available
+ home_med_available
```

按得分排序，保留：

```text
Top 20
```

生成 review page。

---

## Step 3：构建 Initial State

仅从 `visits.csv` 提取：

```text
Age
Gender
Chief complaint
Means of arrival
Triage acuity

Triage temperature
Triage HR
Triage RR
Triage SpO2
Triage SBP
Triage DBP
```

禁止暴露：

```text
Dx_name
ICD9 / ICD10
ED disposition
hospital disposition
future events
```

---

## Step 4：构建 Queryable Context

### Past Medical History

从：

```text
pmh.csv
```

取：

```text
Noted_date <= Arrival_time
```

转换为：

```text
REVIEW_PAST_MEDICAL_HISTORY
```

### Home Medications

从：

```text
meds.csv
```

获取到诊时 active medication。

转换为：

```text
REVIEW_HOME_MEDICATIONS
```

默认隐藏。

---

## Step 5：构建 Lab Evidence

从：

```text
labs.csv
```

按照：

```text
CSN
+ Display_name
+ Order_time
```

聚合。

不要把每一个 component 当 Action。

例如：

```text
CBC with Differential
```

成为：

```text
ORDER_CBC
```

Observation 返回该 panel 下全部：

```text
Component_name
Component_result
Component_value
Component_units
Component_abnormal
normal range
```

保留：

```text
Order_time
Result_time
```

---

## Step 6：构建 Imaging Evidence

从：

```text
rads.csv
```

每个 study 转为：

```text
ORDER_<NORMALIZED_STUDY>
```

例如：

```text
XR CHEST 1 VIEW
→ ORDER_CHEST_XRAY

CT ANGIO CHEST
→ ORDER_CTA_CHEST
```

Observation：

```text
Study
Impression
Order_time
Result_time
```

---

## Step 7：重建真实原始路径

从：

```text
orders.csv
```

选择：

```text
Lab
Imaging
Consult
```

第一版不要加入 medication。

按：

```text
Order_time
```

排序。

输出：

```json
"realized_trajectory": [
  "ORDER_ECG",
  "ORDER_TROPONIN",
  "ORDER_CHEST_XRAY",
  "ORDER_D_DIMER",
  "ORDER_CTA_CHEST"
]
```

这是：

```text
Observed Real Clinical Path
```

不要称为最佳路径。

---

## Step 8：构建 Reference

从 `visits.csv` 保存但隐藏：

```text
primary diagnosis
ICD code
ED disposition
hospital disposition
```

写入：

```json
"reference": {}
```

---

## Step 9：选择最终 5 Cases

从 Top 20 中人工或规则选择：

```text
5 个证据最丰富
时间线清楚
有至少两个合理信息获取方向
最终 diagnosis 明确
```

输出：

```text
data/processed/mcmed_mvp5/
    case_001.json
    ...
    case_005.json
```

---

# 四、eICU Demo 转换

eICU 不要包装成“急诊诊断”。

定义：

```text
task_type =
ICU_EARLY_CLINICAL_ASSESSMENT
```

---

## Step 1：以 ICU Stay 为 Case

使用：

```text
patientunitstayid
```

连接所有表。

---

## Step 2：Initial State

从：

```text
patient.csv
```

提取：

```text
age
gender
unit type
admission source
hospital admission offset
ICU admission information
```

加上 `vitalPeriodic` 最早期生命体征窗口。

固定：

```text
ICU 入科后前 15 分钟
```

压缩为初始生命体征：

```text
HR
RR
SpO2
SBP
DBP
MAP
```

---

## Step 3：Queryable Context

从：

```text
pastHistory.csv
```

建立：

```text
REVIEW_PAST_MEDICAL_HISTORY
```

从：

```text
physicalExam.csv
```

建立：

```text
REVIEW_PHYSICAL_EXAM
```

`admissionDx` 默认不要完整暴露，以免直接泄漏诊断。

---

## Step 4：Hidden Evidence Pool

### Laboratory

从：

```text
lab.csv
```

选择 ICU 入科后：

```text
0–6 hours
```

的数据。

按 lab name + 时间分组。

### Vital Trend

从：

```text
vitalPeriodic.csv
```

生成：

```text
REVIEW_VITAL_TREND
```

不要逐分钟返回。

压缩成：

```text
0–1 h
1–3 h
3–6 h
```

的：

```text
median
min
max
trend
```

### Treatments / Medications

第一版只记录，不进入自由 Action Space。

用于形成 observed clinical trajectory。

---

## Step 5：Reference

使用：

```text
diagnosis.csv
```

和：

```text
admissionDx.csv
```

构建参考诊断集合。

不要假装存在 DDXPlus 那种唯一真值。

---

## Step 6：筛 5 Cases

要求：

```text
past history 非空
physical exam 非空
early vital signs 完整
>= 5 个 early labs
diagnosis 非空
>= 2 个不同 treatment/medication event
```

计算 branchability。

选 Top 5。

输出：

```text
data/processed/eicu_mvp5/
```

---

# 五、统一 Action Space

## MC-MED

允许：

```text
REVIEW_PAST_MEDICAL_HISTORY
REVIEW_HOME_MEDICATIONS

ORDER_LAB_PANEL
ORDER_IMAGING

REVIEW_VITAL_TREND

SUBMIT_DIFFERENTIAL
FINAL_DIAGNOSIS
STOP
```

---

## eICU

允许：

```text
REVIEW_PAST_MEDICAL_HISTORY
REVIEW_PHYSICAL_EXAM

REVIEW_LAB
REVIEW_VITAL_TREND

SUBMIT_DIFFERENTIAL
FINAL_ASSESSMENT
STOP
```

---

# 六、没有真实结果的 Action

如果医生请求：

```text
ORDER_ECHOCARDIOGRAM
```

但该患者没有结果：

```json
{
  "observation_status": "UNOBSERVED_IN_RECORDED_EPISODE"
}
```

必须：

```text
记录 edge
不生成结果
不调用 LLM
```

---

# 七、生成第一批 Tree

每个 case 建立三个测试 Session。

仅用于验证系统，不作为科研结果。

标记：

```text
player_type = SIMULATED_TEST_PLAYER
```

实现三个测试策略：

```text
LAB_FIRST
IMAGING_FIRST
CONTEXT_FIRST
```

例如 MC-MED：

```text
LAB_FIRST:
S0 → CBC → Troponin → CXR → CTA

IMAGING_FIRST:
S0 → CXR → CTA → Troponin

CONTEXT_FIRST:
S0 → PMH → Home Medications → Troponin → CTA
```

然后再允许用户本人从 Arena 手工玩。

---

# 八、Tree 输出

每个 Case 必须输出：

```text
case.json
trajectories.json
graph.json
```

`graph.json`：

```json
{
  "case_id": "CFB_MCMED_001",

  "nodes": [
    {
      "node_id": "S0",
      "state_hash": "...",
      "revealed_evidence": []
    }
  ],

  "edges": [
    {
      "source": "S0",
      "target": "S1",
      "action": "ORDER_CBC",
      "support": 2,
      "player_types": [
        "SIMULATED_TEST_PLAYER"
      ]
    }
  ]
}
```

---

# 九、前端 MVP

增加 Dataset Filter：

```text
DDXPlus
MC-MED
eICU
```

Case 页面必须显示：

```text
Initial State
Current Known Evidence
Action Search
Current Differential
Personal Trajectory
```

Research 页面显示：

```text
Original Realized Path

vs

Current Forest
```

这是 MC-MED 最重要的可视化。

---

# 十、最终验收

完成后根目录生成：

```text
mvp_report/
├── mcmed/
│   ├── case_001/
│   │   ├── case.json
│   │   ├── graph.json
│   │   └── tree.png
│   └── ... 共5个
│
├── eicu/
│   ├── case_001/
│   │   ├── case.json
│   │   ├── graph.json
│   │   └── tree.png
│   └── ... 共5个
│
└── summary.md
```

`summary.md` 只报告：

```text
每个病例初始状态
隐藏证据数量
可执行 Action 数量
真实原始路径
模拟 Session 数量
产生的节点数
产生的边数
未解析 Action 数量
最终 tree.png 路径
```

不要运行模型 benchmark。

不要生成假检查结果。

不要下载 MC-MED waveform。

先证明：

> MC-MED / eICU → Case → Arena → 多条路径 → Tree/DAG

整条数据链可以稳定跑通。