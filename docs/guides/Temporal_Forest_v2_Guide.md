# ClincForestBench Temporal Forest v2
## 四数据源 → 带时间节点的临床决策树 / DAG 转换实施规范

> 目标：将 **MIMIC-IV + MIMIC-IV-Note + MIMIC-IV-ECG、MC-MED、eICU** 统一转换为带真实时间语义的临床病例，并在 Arena 中形成可回放、可分析、可聚合的 **Temporal Clinical Decision Tree / DAG（时间化临床决策树 / 有向无环图）**。
>
> 本规范假定当前已下载并可读取的新增数据为：
>
> 1. `MIMIC-IV-Note`
> 2. `MIMIC-IV-ECG`
> 3. `MC-MED`
> 4. `eICU-CRD`
>
> 同时本地已有 `MIMIC-IV` 作为 MIMIC 主骨架。
>
> **本版本的核心升级：时间不再只是 event metadata，而进入状态定义、Action 执行、结果返回和图节点合并逻辑。**

---

# 0. 必须先固定的研究边界

第一版 Temporal Forest **不是患者生理反事实模拟器**。

只允许：

```text
真实患者已记录的结果
→ 作为可揭示 observation

真实患者未记录的检查
→ UNOBSERVED_IN_RECORDED_EPISODE
→ 保留 action edge
→ 不生成假结果
```

禁止：

```text
医生点了一个现实中没做的检查
→ 调 LLM 编一个结果
```

因此本项目当前恢复的是：

> **Counterfactual information-acquisition policy space**
>
> 反事实“信息获取策略空间”

而不是：

> “患者如果真的提前做了另一项检查，其生理结果一定是什么”。

---

# 1. v2 最关键的变化：时间成为 State 的一部分

旧版近似：

```text
State = 已经揭示的 Evidence Set
```

v2 改成：

\[
S_t =
(
O_t,
P_t,
\tau_t
)
\]

其中：

- `O_t`：当前已可见证据；
- `P_t`：当前 pending actions（已经下单但结果尚未返回）；
- `τ_t`：当前游戏时间。

如果记录 belief，则：

\[
B_t = \text{当前鉴别诊断 / confidence}
\]

但 `Belief` 仍属于玩家，不属于患者客观 State。

---

# 2. 时间字段必须严格区分

每个临床事件统一保存以下时间语义：

```text
order_time
acquired_time
available_time
documented_time
start_time
end_time
```

不是每个数据源都有全部字段。

统一原则：

| 字段 | 含义 |
|---|---|
| `order_time` | 临床人员下医嘱的时间 |
| `acquired_time` | 标本采集 / 检查完成 / 生理量实际测得时间 |
| `available_time` | 结果原则上可以被临床人员看到的最早代理时间 |
| `documented_time` | 信息写入 / 签署 / 存入 EHR 的时间 |
| `start_time` | 治疗 / procedure / infusion 开始 |
| `end_time` | 治疗 / procedure / infusion 结束 |

**不要把这些字段合成一个 `timestamp`。**

---

# 3. 每条事件都必须有 Temporal Confidence

统一增加：

```text
temporal_confidence =
EXACT
HIGH
MEDIUM
LOW
UNKNOWN
```

建议解释：

```text
EXACT
数据源明确给出该时间语义

HIGH
字段语义清楚，但属于系统代理时间

MEDIUM
通过 encounter 匹配 / 最近邻匹配得到

LOW
只有日期或存在已知时钟偏移

UNKNOWN
无法可靠定位
```

所有正式 MVP Case：

```text
核心诊断事件 temporal_confidence >= MEDIUM
```

优先：

```text
HIGH / EXACT
```

---

# 4. 统一 Canonical Temporal Event Schema

所有四个数据源先转换到同一张事件表。

```json
{
  "case_id": "CFB_xxx",

  "event_id": "unique_event_id",

  "event_type": "LAB_RESULT",

  "clinical_concept": {
    "canonical_id": "LAB_TROPONIN",
    "display": "Troponin",
    "source_code": "...",
    "source_system": "..."
  },

  "action_id": "ORDER_TROPONIN",

  "time": {
    "order_time": null,
    "acquired_time": null,
    "available_time": null,
    "documented_time": null,
    "start_time": null,
    "end_time": null,

    "relative_order_min": null,
    "relative_acquired_min": null,
    "relative_available_min": null,

    "temporal_confidence": "HIGH"
  },

  "result": {},

  "provenance": {
    "dataset": "MIMIC-IV",
    "source_table": "labevents",
    "source_row_id": "...",
    "is_observed_real_result": true
  },

  "arena": {
    "arena_eligible": true,
    "state_changing_intervention_before_result": false,
    "leakage_risk": "LOW"
  }
}
```

---

# 5. 所有 Case 必须先定义 T0

每个病例都有唯一：

```text
T0 = case anchor time
```

然后所有时间统一转换为：

```text
relative_minutes_from_T0
```

---

## 5.1 推荐 T0

### MC-MED

```text
T0 = Arrival_time
```

### MIMIC-IV

优先：

```text
T0 = admissions.admittime
```

如果 Case 以 ICU 为入口：

```text
T0 = icustays.intime
```

### eICU

```text
T0 = ICU admission
```

eICU 本身大量事件使用相对 `patientunitstayid` 的 offset，因此：

```text
relative_minutes_from_T0 = source_offset
```

---

# 6. Temporal Case Schema

每个正式病例最终必须生成：

```json
{
  "case_id": "CFB_MC_000001",

  "case_version": "2.0.0",

  "source": {},

  "anchor": {
    "anchor_type": "ED_ARRIVAL",
    "absolute_time": "...",
    "time_system": "DEIDENTIFIED",
    "timezone_policy": "SOURCE_NATIVE"
  },

  "initial_state": {},

  "timeline_events": [],

  "queryable_context": [],

  "hidden_evidence_pool": [],

  "realized_trajectory": [],

  "reference": {},

  "case_quality": {},

  "temporal_quality": {},

  "arena_config": {}
}
```

---

# 7. Arena 时间机制：结果不再瞬间返回

## 7.1 Action 发生时

例如：

```text
当前时间 = +10 min

Doctor:
ORDER_TROPONIN
```

如果该真实病例 Troponin：

```text
available_time = +47 min
```

则系统不能立即返回 Troponin。

创建：

```json
{
  "status": "PENDING",
  "action": "ORDER_TROPONIN",
  "ordered_at_game_time": 10,
  "result_available_at": 47
}
```

State：

```text
Current time: +10 min

Known:
...

Pending:
Troponin
```

---

## 7.2 新增 Action

Temporal Arena 至少支持：

```text
ORDER_*
REVIEW_*
WAIT
ADVANCE_TIME
REVIEW_RESULT
SUBMIT_DIFFERENTIAL
FINAL_DIAGNOSIS
STOP
```

---

## 7.3 时间推进规则

推荐：

### 自动模式

如果玩家选择：

```text
WAIT_FOR_NEXT_RESULT
```

则：

```text
τ_next = min(pending available_time)
```

并返回刚刚变得 available 的所有结果。

### 手动模式

```text
ADVANCE_TIME +15 min
```

用于研究医生是否愿意等待 serial test。

MVP 默认：

```text
WAIT_FOR_NEXT_RESULT
```

即可。

---

# 8. Action 不是“穿越回真实时间线”

这是 v2 必须避免的逻辑错误。

假设真实病例：

```text
Real world:
+20  Troponin ordered
+50  Troponin result
```

实验医生在：

```text
+5
```

就选择：

```text
ORDER_TROPONIN
```

不能简单说：

```text
结果 +50 返回
```

因为这相当于把真实 order time 当固定条件。

MVP 推荐采用：

## Relative Turnaround Time 模式

计算真实：

\[
TAT =
available\_time_{real}
-
order\_time_{real}
\]

例如：

```text
50 - 20 = 30 min
```

如果游戏医生：

```text
+5 ORDER_TROPONIN
```

则：

```text
simulated_available_time = +35
```

但结果值仍然使用真实记录值。

必须标记：

```text
temporal_replay_mode =
OBSERVED_RESULT_WITH_SHIFTED_TAT
```

这比直接把结果锁在原始绝对时间更加合理。

---

# 9. 三种时间重放模式必须显式保存

```text
OBSERVED_FIXED_TIME
OBSERVED_RESULT_WITH_SHIFTED_TAT
UNOBSERVED
```

## OBSERVED_FIXED_TIME

适用于：

```text
已经自然发生、与医生 Action 无关的 observation
```

例如：

```text
连续生命体征
```

## OBSERVED_RESULT_WITH_SHIFTED_TAT

适用于：

```text
lab
imaging
```

即：

> 结果是真实患者结果；
> 返回等待时间采用这个患者真实检查的 turnaround time。

## UNOBSERVED

病例没有该检查。

---

# 10. State-changing intervention 必须进入时间逻辑

任何可能改变后续患者结果的事件标记：

```text
state_changing_intervention = true
```

第一版至少包括：

```text
vasopressor
major fluid resuscitation
anticoagulation
antibiotic
intubation
mechanical ventilation change
surgery / invasive procedure
major cardiac intervention
```

如果一个检查真实发生于重大干预之后：

```text
S0
→ Treatment
→ 4h
→ CT
```

不能无条件把该 CT 作为 S0 的反事实检查结果。

标记：

```text
arena_eligible = false
```

或：

```text
arena_eligible_scope = "POST_INTERVENTION_ONLY"
```

MVP 第一版：

> **只允许 pre-major-intervention diagnostic evidence 自由重排。**

---

# 11. Canonical Temporal State Hash

旧版：

```text
hash(case_id + revealed evidence IDs)
```

v2 必须升级。

建议：

```text
hash(
  case_id,
  sorted(revealed_event_ids),
  sorted(pending_action_ids + expected_available_bucket),
  time_bucket
)
```

其中：

```text
time_bucket = floor(relative_time_min / 5)
```

默认：

```text
5 min
```

---

## 为什么时间必须进入 hash

下面两个状态不能合并：

```text
State A
+15 min
Troponin pending

State B
+60 min
Troponin result available
```

即使玩家历史 Action 相同。

---

# 12. Forest 同时保留两种图

## A. Trajectory Tree

严格保留：

```text
Action 顺序
时间顺序
等待
结果返回
belief update
```

用于：

```text
path analysis
time-to-diagnosis
order effect
waiting strategy
```

---

## B. Canonical Temporal DAG

只有在：

```text
相同 case
+
相同 visible evidence
+
相同 pending set
+
相同 time bucket
```

时才合并节点。

用于：

```text
P(Action | State, time)
branch entropy
physician policy
specialty comparison
```

---

# 13. MIMIC-IV + Note + ECG Adapter

# 13.1 MIMIC Case Anchor

无 ED 数据时优先：

```text
hospital admission
```

筛：

```text
EW EMER.
DIRECT EMER.
URGENT
```

或具有：

```text
admission_location = emergency room
```

的住院患者。

---

# 13.2 Initial State

来源：

```text
MIMIC-IV admissions
+
MIMIC-IV-Note discharge summary
```

Discharge summary 只能用于回顾性构建：

```text
chief complaint
pre-admission HPI
past medical history
```

必须：

```text
自动 section parser
→ temporal sentence classifier
→ 人工审核
```

只允许：

```text
PRE_ADMISSION
AT_PRESENTATION
```

禁止：

```text
POST_ADMISSION
diagnosis result
hospital course
future imaging
treatment response
```

---

# 14. MIMIC Lab 时间映射

`labevents`：

```text
charttime
= 通常接近 specimen acquisition

storetime
= measurement 在 laboratory system 中可用
= care provider 原则上可看到的时间代理
```

所以：

```text
acquired_time  = charttime
available_time = storetime
```

如果 `storetime` 缺失：

```text
available_time = charttime
temporal_confidence = MEDIUM
```

不要把：

```text
charttime
```

直接当结果可见时间。

---

# 15. MIMIC Lab Panel 聚合

优先使用：

```text
specimen_id
```

把同一 specimen 上多个 measurement 聚合。

再结合：

```text
itemid → d_labitems
```

映射 canonical panel。

例如：

```text
CBC
BMP
CMP
Blood gas
Troponin
Coagulation
```

保存：

```text
panel_id
component[]
```

Action 以 panel 为单位。

---

# 16. MIMIC POE：真实医生 Action 线

`poe.ordertime`：

```text
provider 真正下 order 的时间
```

用于恢复：

```text
realized_trajectory
```

至少抽：

```text
Lab
Radiology
Cardiology
Consults
Respiratory
Critical Care
```

第一版药物可以记录但不作为自由诊断 Action。

---

# 17. MIMIC Radiology 时间映射

MIMIC-IV-Note `radiology`：

```text
charttime
= note 被 charted 的时间
= 更接近报告临床事件时间

storetime
= note 被完成 / 签署 / 存入数据库时间
```

MVP 建议：

```text
acquired_time =
radiology.charttime

available_time =
storetime if not null
else charttime
```

并保存：

```text
availability_semantics = REPORT_SIGNED_PROXY
```

`radiology_detail`：

```text
exam_name
exam_code
cpt_code
```

用于建立：

```text
ORDER_CHEST_XRAY
ORDER_CT_CHEST
ORDER_CTA_CHEST
ORDER_ULTRASOUND
...
```

---

# 18. MIMIC ECG 时间映射

使用：

```text
record_list.csv
machine_measurements.csv
waveform_note_links.csv
```

核心：

```text
subject_id
study_id
ecg_time
```

### 重要限制

`ecg_time` 来自 ECG 机器内部时钟。

官方明确指出：

> 机器时钟没有保证与其他 MIMIC 系统同步；
> 时间戳可能存在明显偏移。

因此：

```text
acquired_time = ecg_time
temporal_confidence = LOW/MEDIUM
```

不能默认：

```text
ECG 10:01
早于
Troponin 10:02
```

就是精确一分钟关系。

---

# 19. ECG 匹配规则

一个 ECG 只有同时满足以下条件才进入正式 Case：

```text
subject_id 一致
+
ecg_time 落在 hospitalization 扩展窗口
+
距离住院关键事件时间合理
```

建议：

```text
hospital admission - 24h
to
hospital discharge + 24h
```

初步匹配。

然后根据：

```text
cardiology POE
ECG note
其他 ECG temporal clues
```

打：

```text
temporal_confidence
```

正式 MVP：

```text
MEDIUM+
```

优先 HIGH。

---

# 20. MIMIC Reference

不要使用：

```text
diagnoses_icd top1
```

直接当绝对 ground truth。

统一保存：

```json
{
  "reference": {
    "hospital_principal_diagnosis": [],
    "discharge_diagnoses": [],
    "definitive_findings": [],
    "adjudicated_primary_diagnosis": null,
    "reference_strength": "..."
  }
}
```

MVP 5 case 必须人工审核。

---

# 21. MC-MED Adapter

MC-MED 是目前最适合 Temporal Forest 的数据源。

# 21.1 Anchor

```text
T0 = visits.Arrival_time
```

---

# 21.2 Initial State

直接来自 `visits.csv`：

```text
Age
Gender
Chief complaint
Means of arrival
Triage acuity

Triage Temp
HR
RR
SpO2
SBP
DBP
```

只有：

```text
arrival-time available information
```

进入 S0。

隐藏：

```text
Dx_name
ICD
ED disposition
hospital disposition
```

---

# 22. MC-MED Queryable Context

`pmh.csv`：

```text
REVIEW_PAST_MEDICAL_HISTORY
```

`meds.csv`：

```text
REVIEW_HOME_MEDICATIONS
```

必须基于时间过滤：

```text
PMH noted before current visit

medication active at current visit
```

---

# 23. MC-MED Order 时间

`orders.csv`：

```text
Order_time
= 真实 ED physician order time
```

用于：

```text
realized_trajectory
```

`Result_time`：

```text
lab / imaging reported result time
```

对于药物：

```text
First_admin_time
```

是首次给药时间。

---

# 24. MC-MED Lab 时间

`labs.csv`：

```text
Order_time
Result_time
```

因此：

```text
order_time = Order_time
available_time = Result_time
```

数据没有单独 specimen acquisition time 时：

```text
acquired_time = null
```

不要自行填。

TAT：

```text
Result_time - Order_time
```

直接可用于 Temporal Arena。

---

# 25. MC-MED Radiology 时间

`rads.csv`：

```text
Order_time
Result_time
Study
Impression
```

因此：

```text
order_time = Order_time
available_time = Result_time
```

`Result_time` 是 attending radiologist impression posted 的时间。

所以：

```text
availability_semantics = RADIOLOGY_IMPRESSION_POSTED
temporal_confidence = HIGH
```

这是 MC-MED 非常大的优势。

---

# 26. MC-MED Numeric Vitals

如果已下载 `numerics.csv`：

不要把每分钟都变成 graph node。

建立：

```text
Temporal Vital Segments
```

例如：

```text
0–15 min
15–60 min
1–3 h
3–6 h
```

每段输出：

```text
median
min
max
last
slope
abnormal_duration
```

生成：

```text
REVIEW_VITAL_TREND
```

Observation 示例：

```json
{
  "heart_rate": {
    "median": 112,
    "min": 105,
    "max": 124,
    "trend": "increasing"
  },
  "spo2": {
    "median": 91,
    "min": 87,
    "max": 94,
    "trend": "worsening"
  }
}
```

---

# 27. MC-MED Case Eligibility

MVP 优先：

```text
chief complaint 非空

>= 4 diagnostic orders
>= 2 distinct lab panels
>= 1 radiology
primary diagnosis 非空
timeline monotonicity acceptable
```

优先：

```text
Chest pain
Shortness of breath
Abdominal pain
```

第一批建议只选一个 chief complaint。

---

# 28. eICU Adapter

eICU 不要伪装成 ED diagnosis。

定义：

```text
task_type =
ICU_EARLY_CLINICAL_ASSESSMENT
```

---

# 29. eICU 时间系统

eICU 大量事件使用：

```text
xxxoffset
```

单位通常是：

```text
minutes from ICU admission
```

因此：

```text
T0 = ICU admission
relative_time_min = offset
```

不要尝试恢复真实绝对日期。

---

# 30. eICU Initial State

以：

```text
patientunitstayid
```

为 Case。

S0：

```text
age
gender
ICU unit
admission source
initial admission context
first 15 min vitals
```

`admissionDx`：

不要完整展示。

可只用于：

```text
reference / case classification
```

---

# 31. eICU Past History / Physical Exam

`pastHistory.csv`：

```text
REVIEW_PAST_MEDICAL_HISTORY
```

`physicalExam.csv`：

```text
REVIEW_PHYSICAL_EXAM
```

注意：

eICU 不同医院 / ICU interface 完整度不同。

**缺数据不代表临床上没做。**

所以：

```text
missingness_semantics =
INTERFACE_DEPENDENT
```

必须保存。

---

# 32. eICU Laboratory

从：

```text
lab.csv
```

转换。

保留：

```text
labresultoffset
```

作为结果时间代理。

如果有：

```text
labresultrevisedoffset
```

则保留 revision。

一个 lab event：

```json
{
  "available_time_relative_min": 37,
  "temporal_confidence": "HIGH",
  "availability_semantics": "EICU_RECORDED_RESULT_OFFSET"
}
```

---

# 33. eICU Vitals

`vitalPeriodic`：

高频生命体征。

不要逐条进入 Tree。

和 MC-MED 一样压缩：

```text
0–15 min
15–60 min
1–3 h
3–6 h
```

用于：

```text
REVIEW_VITAL_TREND
```

---

# 34. eICU Diagnosis / Treatment

`diagnosis.csv`：

```text
diagnosisoffset
```

代表 diagnosis 记录相对于 ICU 入科时间的位置。

用于：

```text
realized diagnostic timeline
```

但：

```text
diagnosis != absolute truth
```

`treatment.csv`：

用 treatment offset 标记真实治疗事件。

治疗事件优先用于：

```text
state-changing intervention boundary
```

第一版不让玩家自由模拟治疗后的生理结果。

---

# 35. eICU Arena Eligibility

初始自由 evidence pool 建议只允许：

```text
0–6 h
```

并且：

```text
before first major state-changing intervention
```

如果治疗特别早：

```text
缩短 evidence window
```

---

# 36. 四数据源统一 Action Ontology

定义：

```text
HISTORY
├ REVIEW_PAST_MEDICAL_HISTORY
├ REVIEW_HOME_MEDICATIONS
└ REVIEW_PHYSICAL_EXAM

MONITORING
├ REVIEW_CURRENT_VITALS
└ REVIEW_VITAL_TREND

LAB
├ ORDER_CBC
├ ORDER_BMP
├ ORDER_CMP
├ ORDER_TROPONIN
├ ORDER_D_DIMER
├ ORDER_BLOOD_GAS
└ ...

IMAGING
├ ORDER_CHEST_XRAY
├ ORDER_CT_CHEST
├ ORDER_CTA_CHEST
├ ORDER_CT_ABDOMEN
└ ...

CARDIOLOGY
├ ORDER_ECG
└ ...

META
├ WAIT_FOR_NEXT_RESULT
├ ADVANCE_TIME
├ SUBMIT_DIFFERENTIAL
├ FINAL_DIAGNOSIS
└ STOP
```

每个 dataset adapter 只负责：

```text
source code
→ canonical action
```

Arena 不知道原始数据源字段。

---

# 37. Pending Action 是 v2 的一级对象

数据库新增：

```text
pending_actions
```

字段：

```text
pending_id
session_id
action_id

ordered_game_time
expected_available_game_time

source_event_id
temporal_replay_mode

status
```

status：

```text
PENDING
AVAILABLE
REVIEWED
CANCELLED
UNOBSERVED
```

---

# 38. 时间化 Session Event

```json
{
  "event_type": "ORDER_ACTION",

  "action": {
    "action_id": "ORDER_TROPONIN"
  },

  "game_time_before_min": 10,
  "game_time_after_min": 10,

  "pending_created": {
    "available_at_min": 35
  },

  "state_before_hash": "...",
  "state_after_hash": "...",

  "wall_clock_timestamp": "..."
}
```

等待之后：

```json
{
  "event_type": "RESULT_BECAME_AVAILABLE",

  "source_event_id": "LAB_TROP_001",

  "game_time_before_min": 10,
  "game_time_after_min": 35,

  "observation": {
    "troponin": "..."
  }
}
```

---

# 39. 一个完整 Temporal Case 示例

假设 MC-MED 胸痛病例。

```json
{
  "case_id": "CFB_MC_CP_001",

  "anchor": {
    "anchor_type": "ED_ARRIVAL",
    "relative_zero": 0
  },

  "initial_state": {
    "age": 58,
    "sex": "M",
    "chief_complaint": "chest pain",
    "triage": {
      "hr": 105,
      "spo2": 94,
      "sbp": 142,
      "dbp": 86
    }
  },

  "timeline_events": [
    {
      "event_id": "E_TROP_1",
      "action_id": "ORDER_TROPONIN",
      "order_time_min": 12,
      "available_time_min": 41,
      "turnaround_time_min": 29,
      "result": {
        "value": 0.08,
        "flag": "elevated"
      },
      "arena_eligible": true
    },

    {
      "event_id": "E_CXR_1",
      "action_id": "ORDER_CHEST_XRAY",
      "order_time_min": 18,
      "available_time_min": 56,
      "turnaround_time_min": 38,
      "result": {
        "impression": "No acute cardiopulmonary abnormality."
      },
      "arena_eligible": true
    },

    {
      "event_id": "E_DDIMER_1",
      "action_id": "ORDER_D_DIMER",
      "order_time_min": 31,
      "available_time_min": 58,
      "turnaround_time_min": 27,
      "result": {
        "value": 1430,
        "flag": "elevated"
      },
      "arena_eligible": true
    },

    {
      "event_id": "E_CTA_1",
      "action_id": "ORDER_CTA_CHEST",
      "order_time_min": 72,
      "available_time_min": 108,
      "turnaround_time_min": 36,
      "result": {
        "impression": "Acute pulmonary embolism."
      },
      "arena_eligible": true
    }
  ],

  "realized_trajectory": [
    {
      "action": "ORDER_TROPONIN",
      "time_min": 12
    },
    {
      "action": "ORDER_CHEST_XRAY",
      "time_min": 18
    },
    {
      "action": "ORDER_D_DIMER",
      "time_min": 31
    },
    {
      "action": "ORDER_CTA_CHEST",
      "time_min": 72
    }
  ],

  "reference": {
    "primary_diagnosis": "pulmonary embolism",
    "reference_strength": "HIGH"
  }
}
```

---

# 40. 三个医生如何形成时间树

## Doctor A

```text
T+0
S0

T+2
ORDER_D_DIMER
→ pending until T+29

T+2
ORDER_CHEST_XRAY
→ pending until T+40

T+29
D-dimer available ↑

T+30
ORDER_CTA
→ pending until T+66

T+40
CXR available

T+66
CTA available → PE

T+68
FINAL_DIAGNOSIS
```

---

## Doctor B

```text
T+0
S0

T+1
ORDER_TROPONIN
→ pending until T+30

T+3
ORDER_CHEST_XRAY
→ pending until T+41

T+30
Troponin elevated

T+31
ORDER_D_DIMER
→ pending until T+58

T+41
CXR negative

T+58
D-dimer high

T+59
ORDER_CTA
→ T+95

T+95
PE
```

---

## Doctor C

```text
T+0
REVIEW_HOME_MEDICATIONS

T+1
ORDER_D_DIMER

T+28
D-dimer high

T+29
ORDER_CTA

T+65
PE
```

---

# 41. 最终 Temporal Tree

```text
                                  ┌─ D-dimer pending
                    ORDER D-dimer│
                   /              └─ T+29 high
                  /                      │
                 /                     CTA
                /                        │
S0 @ T0 ────────                         └─ T+66 PE
                \
                 \ ORDER Troponin
                  └─ pending
                       │
                     T+30 ↑
                       │
                    D-dimer
                       │
                      CTA
                       │
                    T+95 PE


S0 @ T0
  \
   REVIEW HOME MEDS
       \
       D-dimer
          \
          CTA
            \
            T+65 PE
```

Tree 的 edge 不再只有：

```text
Action
```

而是：

```text
Action
+
time delta
+
pending duration
+
result availability
```

---

# 42. Graph Edge Schema

```json
{
  "edge_id": "...",

  "source_node": "...",
  "target_node": "...",

  "action_id": "ORDER_D_DIMER",

  "action_time_min": 2,

  "result_available_time_min": 29,

  "latency_min": 27,

  "result_status": "OBSERVED",

  "support": 4,

  "player_distribution": {},

  "source_event_id": "..."
}
```

---

# 43. Graph Node Schema

```json
{
  "node_id": "...",

  "case_id": "...",

  "game_time_min": 29,

  "time_bucket": 25,

  "visible_event_ids": [
    "..."
  ],

  "pending_actions": [
    "..."
  ],

  "state_hash": "...",

  "node_metrics": {
    "branch_entropy": null,
    "support": 1
  }
}
```

---

# 44. 这次升级后可以做的新指标

## Time to correct hypothesis

\[
T_{\text{correct-top-k}}
\]

---

## Time to final diagnosis

\[
T_{\text{diagnosis}}
\]

---

## Diagnostic latency

正确证据 available 后：

\[
T_{\text{final}}
-
T_{\text{critical evidence available}}
\]

---

## Waiting efficiency

医生是否：

```text
无意义等待
```

或者在 pending 期间合理并行下单。

---

## Parallelization

例如：

```text
Doctor A:
同时下 CBC + Troponin + CXR

Doctor B:
一次只下一个
```

比较：

```text
parallel order strategy
```

---

## Time-aware path efficiency

不只：

```text
number of actions
```

还包括：

```text
time cost
resource cost
diagnostic delay
```

---

# 45. 输出数据目录

```text
data/
├── canonical/
│   ├── mimic/
│   │   ├── cases.parquet
│   │   └── temporal_events.parquet
│   │
│   ├── mcmed/
│   │   ├── cases.parquet
│   │   └── temporal_events.parquet
│   │
│   └── eicu/
│       ├── cases.parquet
│       └── temporal_events.parquet
│
├── case_bundles/
│   ├── mimic/
│   ├── mcmed/
│   └── eicu/
│
└── exports/
```

---

# 46. 每个正式 MVP Case 输出

```text
case_001/
├── case.json
├── timeline.parquet
├── realized_path.json
├── temporal_graph.json
├── review.html
└── tree.png
```

---

# 47. 数据库新增表

已有：

```text
sessions
session_events
state_snapshots
belief_snapshots
graph_nodes
graph_edges
```

新增：

```text
clinical_source_events
pending_actions
temporal_state_snapshots
case_temporal_quality
```

---

# 48. Event Sourcing 原则继续保持

任何动作：

```text
ORDER
WAIT
RESULT AVAILABLE
REVIEW RESULT
BELIEF UPDATE
FINAL DIAGNOSIS
```

全部写 event。

绝不：

```text
UPDATE 过去 event
```

这样未来才能完整分析：

```text
parallel orders
waiting
diagnostic delay
belief before/after result
```

---

# 49. Replay 必须支持时间

```text
replay_session(session_id)
```

必须重建：

```text
每一步 current time
visible evidence
pending actions
available results
belief
final state
```

最后：

```text
replayed_state_hash == stored_state_hash
```

---

# 50. 数据质量检查

每个 Adapter 都必须运行：

## 时间顺序检查

```text
available_time >= order_time
```

如果不满足：

```text
flag = TEMPORAL_INCONSISTENCY
```

不静默修复。

---

## Case Anchor 检查

```text
所有主要事件 relative time 可计算
```

---

## 泄漏检查

S0 不能包含：

```text
future diagnosis
future imaging result
future lab
hospital course
discharge outcome
```

---

## 干预检查

任何：

```text
post-major-intervention evidence
```

默认：

```text
arena_eligible = false
```

---

## ECG 检查

MIMIC ECG：

```text
known clock uncertainty
```

必须在 case metadata 中记录。

---

## eICU missingness

缺事件不能解释成：

```text
test not performed
```

因为 eICU 存在 unit interface missingness。

---

# 51. 第一轮 MVP 不要每个数据集做很多病例

正式执行：

```text
MIMIC      5 cases
MC-MED     5 cases
eICU       5 cases
```

总共：

```text
15 cases
```

MIMIC-IV-Note 和 ECG 属于 MIMIC Case 的扩展模态，不单独算 Case source。

---

# 52. MVP Case 类型

## MC-MED

优先：

```text
Chest pain
```

如果不足：

```text
Shortness of breath
```

---

## MIMIC

优先：

```text
acute respiratory / infection
```

因为没有 ED：

```text
discharge HPI
+
lab
+
radiology
```

更容易重建。

---

## eICU

优先：

```text
ICU early assessment
```

不要称：

```text
diagnosis from presentation
```

---

# 53. Codex 实施顺序

严格按下面顺序。

## Phase 1 — Source Validation

实现：

```text
validate_mimic_sources.py
validate_mcmed_sources.py
validate_eicu_sources.py
```

输出：

```text
文件存在
schema
row count
时间字段 null rate
ID join coverage
```

---

## Phase 2 — Dataset Adapters

实现：

```text
MIMICTemporalAdapter
MCMEDTemporalAdapter
EICUTemporalAdapter
```

共同实现：

```text
list_cases()
load_case()
build_initial_state()
build_timeline_events()
build_realized_trajectory()
build_reference()
```

---

## Phase 3 — Canonical Temporal Event Layer

全部转换：

```text
source tables
↓
canonical temporal_events.parquet
```

此阶段不做 Arena。

---

## Phase 4 — Case Candidate Scoring

为每 case 计算：

```text
evidence_count
modality_count
temporal_completeness
timeline_consistency
branchability
reference_quality
pre_intervention_evidence_count
```

输出 Top 20 / dataset。

---

## Phase 5 — Human Review

生成：

```text
review.html
```

一页显示：

```text
S0

完整真实 Timeline

可进入 Arena 的 Evidence

被排除的 Evidence
+ 排除原因

Reference

Temporal warnings
```

人工从每个数据集选：

```text
5 cases
```

---

## Phase 6 — Temporal Arena Engine

升级已有：

```text
ClinicalEnvironment
```

增加：

```text
current_time
pending_actions
advance_time()
resolve_pending()
```

---

## Phase 7 — Temporal Graph Builder

生成：

```text
Trajectory Tree
Canonical Temporal DAG
```

---

## Phase 8 — MVP Test

每病例自己模拟：

```text
3 条不同路径
```

至少：

```text
FAST_TARGETED
BROAD_WORKUP
CONTEXT_FIRST
```

只作为工程测试。

---

## Phase 9 — Export

输出：

```text
15 case folders
+
summary.md
+
all_graphs.html
```

---

# 54. Codex 不允许做的事情

禁止：

```text
LLM 补造未记录检查结果
```

禁止：

```text
把 acquisition time 当 result available time
```

禁止：

```text
MIMIC ECG 时间精确到分钟比较而不标时钟不确定性
```

禁止：

```text
把 post-treatment imaging 提前作为 S0 反事实结果
```

禁止：

```text
eICU 缺记录 = test not done
```

禁止：

```text
discharge diagnosis = absolute ground truth
```

禁止：

```text
只保存最终 tree，不保存 raw event trajectory
```

---

# 55. 验收标准

只有全部满足才算 Temporal Forest v2 MVP 完成：

- [ ] 三个 Case Adapter 均能独立运行；
- [ ] 每条 evidence 区分 order / acquisition / availability 时间；
- [ ] 所有时间可转换为 relative minutes；
- [ ] State 包含 current time；
- [ ] State 包含 pending actions；
- [ ] Action 后结果不会瞬间返回；
- [ ] WAIT 能推进到下一可用结果；
- [ ] Lab / imaging 使用真实结果；
- [ ] 未观测检查返回 `UNOBSERVED_IN_RECORDED_EPISODE`；
- [ ] MIMIC ECG 明确记录时钟不确定性；
- [ ] post-intervention evidence 可自动标记不可前移；
- [ ] trajectory tree 保留完整顺序；
- [ ] canonical temporal DAG 可正确 merge；
- [ ] 相同 Evidence 但不同时间状态不会错误 merge；
- [ ] completed session 可 100% replay；
- [ ] 每个正式 Case 有 review page；
- [ ] 每数据集完成 5 个高质量病例；
- [ ] 每病例至少能人工跑出 3 条不同时间路径；
- [ ] 最终 Tree/DAG 可视化显示 action 时间和 result latency。

---

# 56. 本版本最终研究对象

Temporal Forest v2 不再只是：

```text
医生先看什么？
```

而是同时记录：

```text
医生什么时候做？
做了什么？
结果什么时候回来？
等待期间又做什么？
看到结果后多久改变判断？
什么时候停止继续检查？
```

因此最终估计的是：

\[
P(A_t \mid S_t,\tau_t,Z)
\]

其中：

- `S_t`：当前患者信息状态；
- `τ_t`：当前临床时间；
- `Z`：医生专科 / 经验等属性。

这才是本版本相对于旧版 ForestBench 最重要的升级：

> **从“证据顺序树”升级为“带真实临床时间与结果延迟的动态决策图”。**

---

# 57. 官方字段语义核对依据

实现时必须以官方定义为准：

- MIMIC-IV `labevents`：`charttime` 通常接近标本采集；`storetime` 是结果在实验室系统中可用的时间。
- MIMIC-IV `poe.ordertime`：provider 下医嘱时间。
- MIMIC-IV-Note `radiology.charttime/storetime`：分别对应报告 charted 与 stored/signed 的代理时间。
- MIMIC-IV-ECG `ecg_time`：ECG 机器记录时间，但官方明确提示机器内部时钟可能与其他 MIMIC 数据源不同步。
- MC-MED：`Arrival_time`、`Order_time`、`Result_time` 在同一患者内保留相对时间关系；`orders/labs/rads` 均提供用于重建临床时间线的时间字段。
- eICU：事件主要以 ICU admission 为零点的 offset 表示；同时必须考虑不同 ICU interface 完整度不同导致的非随机缺失。

