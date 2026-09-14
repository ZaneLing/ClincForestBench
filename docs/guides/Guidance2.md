
# Synthea 与 MedAgentBench 转换为 ClincForestBench 动态森林病例的实施指南

# 1. 两个数据集在 ClincForestBench 中的定位

先固定整个项目的数据层级。

```text
DDXPlus
│
│  病史询问
│  症状逐步暴露
│  诊断先验
│
▼
Synthea
│
│  完整纵向合成 EHR
│  实验室、生命体征、用药、操作、Encounter
│  可主动生成适合 Forest 的病例
│
▼
MedAgentBench
│
│  真实去标识 EHR 档案
│  FHIR API
│  查询 + 写入 + 下医嘱
│  临床工作流和 EHR 行动
│
▼
MIMIC
   真实患者
   真实诊疗时间线
   真实检查和结果
   临床验证
```

其中：

| 数据集 | 最适合的 Forest |
|---|---|
| DDXPlus | 病史询问森林 |
| **Synthea** | **开放诊断/证据获取森林** |
| **MedAgentBench** | **EHR 工作流/临床行动森林** |
| MIMIC | 真实临床决策森林 |

Synthea 本身支持从出生到死亡的纵向患者生成，包括门诊、急诊、症状驱动就诊，以及 Condition、Medication、Observation、Lab、Procedure、CarePlan 等临床资源，并可以直接导出 FHIR R4。citeturn275672view2

MedAgentBench 则有 100 个患者、约 78.5 万条临床记录，包括 Observation、Procedure、Condition 和 MedicationRequest，并通过 FHIR Server 提供交互式访问。citeturn475616search1

---

# 第一部分：Synthea 怎么变成 Forest Case

# 2. Synthea 与 DDXPlus 最大的区别

DDXPlus 一个患者大概是：

```text
Patient

├── Age
├── Sex
├── Symptom A
├── Symptom B
├── Antecedent A
├── Antecedent B
└── True pathology
```

因此医生只能：

```text
问症状
→ 得到答案
```

Synthea 则是纵向 EHR：

```text
Patient
│
├── Encounter 1
│   ├── Condition
│   ├── Observation
│   └── Medication
│
├── Encounter 2
│   ├── Vital signs
│   ├── Laboratory
│   ├── Procedure
│   └── Medication
│
└── Encounter 3
    └── ...
```

所以这里需要首先完成：

> **Longitudinal Patient → Index Clinical Episode**

即：

> 从患者的一生中找出一个值得玩的临床就诊 episode（临床事件段）。

---

# 3. Synthea 建议统一使用 FHIR R4

运行时：

```bash
./run_synthea -p 1000 \
  --exporter.fhir.export=true \
  --exporter.baseDirectory="./output"
```

Synthea 官方支持 FHIR R4、Bulk FHIR、CSV 等格式。citeturn275672view2

会得到类似：

```text
output/
└── fhir/
    ├── patient_A.json
    ├── patient_B.json
    └── ...
```

每个文件通常是：

```json
{
  "resourceType": "Bundle",
  "type": "transaction",
  "entry": [...]
}
```

Bundle 内包含多个 FHIR Resource。

---

# 4. 一个简化的 Synthea 原始患者

下面是**结构化示意**，字段遵循 Synthea FHIR 的资源组织，但为了阅读删掉了大量编码和 metadata。

## 原始 JSON

```json
{
  "resourceType": "Bundle",
  "entry": [
    {
      "resource": {
        "resourceType": "Patient",
        "id": "patient-001",
        "gender": "male",
        "birthDate": "1964-03-02"
      }
    },

    {
      "resource": {
        "resourceType": "Encounter",
        "id": "encounter-2026-01",
        "status": "finished",
        "class": {
          "code": "EMER"
        },
        "period": {
          "start": "2026-01-15T08:00:00Z",
          "end": "2026-01-15T14:20:00Z"
        },
        "reasonCode": [
          {
            "text": "Chest pain"
          }
        ]
      }
    },

    {
      "resource": {
        "resourceType": "Observation",
        "id": "hr-001",
        "encounter": {
          "reference": "Encounter/encounter-2026-01"
        },
        "code": {
          "text": "Heart rate"
        },
        "effectiveDateTime": "2026-01-15T08:05:00Z",
        "valueQuantity": {
          "value": 108,
          "unit": "beats/min"
        }
      }
    },

    {
      "resource": {
        "resourceType": "Observation",
        "id": "spo2-001",
        "encounter": {
          "reference": "Encounter/encounter-2026-01"
        },
        "code": {
          "text": "Oxygen saturation"
        },
        "effectiveDateTime": "2026-01-15T08:05:00Z",
        "valueQuantity": {
          "value": 92,
          "unit": "%"
        }
      }
    },

    {
      "resource": {
        "resourceType": "Observation",
        "id": "troponin-001",
        "encounter": {
          "reference": "Encounter/encounter-2026-01"
        },
        "code": {
          "text": "Troponin"
        },
        "effectiveDateTime": "2026-01-15T08:40:00Z",
        "valueQuantity": {
          "value": 0.07,
          "unit": "ng/mL"
        }
      }
    },

    {
      "resource": {
        "resourceType": "Observation",
        "id": "ddimer-001",
        "encounter": {
          "reference": "Encounter/encounter-2026-01"
        },
        "code": {
          "text": "D-dimer"
        },
        "effectiveDateTime": "2026-01-15T09:15:00Z",
        "valueQuantity": {
          "value": 1240,
          "unit": "ng/mL"
        }
      }
    },

    {
      "resource": {
        "resourceType": "Procedure",
        "id": "cta-001",
        "encounter": {
          "reference": "Encounter/encounter-2026-01"
        },
        "code": {
          "text": "CT angiography of chest"
        },
        "performedDateTime": "2026-01-15T10:10:00Z"
      }
    },

    {
      "resource": {
        "resourceType": "Condition",
        "id": "pe-001",
        "encounter": {
          "reference": "Encounter/encounter-2026-01"
        },
        "code": {
          "text": "Pulmonary embolism"
        },
        "onsetDateTime": "2026-01-15T10:30:00Z"
      }
    }
  ]
}
```

真实 Synthea 文件会比这复杂得多。

---

# 5. 第一步：把患者一生拆成 Encounter

先提取：

```text
Patient
↓
Encounter[]
```

每个 Encounter 建：

```json
{
  "patient_id": "patient-001",
  "encounter_id": "encounter-2026-01",

  "start": "...",
  "end": "...",

  "encounter_type": "EMERGENCY",

  "reason": [
    "Chest pain"
  ]
}
```

然后把有：

```json
{
  "encounter": {
    "reference": "Encounter/encounter-2026-01"
  }
}
```

的：

- Observation；
- Procedure；
- MedicationRequest；
- Condition；

全部归到这个 Encounter。

---

# 6. 第二步：选“可玩的 Encounter”

不是所有 Encounter 都适合。

例如：

```text
Annual wellness visit

只有：
BP
weight
height
```

几乎没有分叉价值。

需要计算：

## Case Branchability

例如：

```text
clinical_trigger
+
independent_observations
+
lab_count
+
procedure_count
+
medication_count
+
diagnostic_uncertainty
```

MVP 建议：

```text
至少：
1 个明确 presentation/reason
3 个以上不同证据类别
1 个以上 laboratory
1 个以上 procedure 或 medication/action
1 个明确 reference condition
```

---

# 7. 第三步：划分 Initial State 与 Hidden Evidence

这是转换的核心。

假设完整 Encounter 有：

```text
Chest pain

HR 108
SpO2 92%

Troponin
D-dimer
CBC

CTA

Pulmonary embolism
```

不能全部暴露。

## Initial State

只保留：

```text
Patient demographics
+
Encounter reason
+
presentation-time vital signs
```

例如：

```json
{
  "age": 61,
  "sex": "male",

  "presentation": {
    "chief_complaint": "Chest pain"
  },

  "initial_vitals": {
    "heart_rate": 108,
    "spo2": 92
  }
}
```

---

# 8. Hidden Evidence Pool

剩余资源全部进入：

```json
"evidence_pool"
```

例如：

```json
[
  {
    "evidence_id": "troponin-001",
    "action_id": "ORDER_TROPONIN",

    "observation": {
      "value": 0.07,
      "unit": "ng/mL"
    },

    "source_resource": "Observation",

    "available": true
  },

  {
    "evidence_id": "ddimer-001",
    "action_id": "ORDER_D_DIMER",

    "observation": {
      "value": 1240,
      "unit": "ng/mL"
    },

    "available": true
  },

  {
    "evidence_id": "cta-001",
    "action_id": "ORDER_CTA_CHEST",

    "observation": {
      "status": "performed"
    },

    "available": true
  }
]
```

---

# 9. 这里 Synthea 有一个很重要的局限

Synthea 原生经常能告诉你：

```text
CTA performed
```

但不一定有：

> 一份像真实 MIMIC radiology report 那样详细的 CTA 报告。

它主要提供：

- Condition；
- Observation；
- Procedure；
- Medication；
- Encounter；

而不是高质量自由文本影像报告。Synthea 官方核心功能也是这些结构化资源。citeturn275672view2

因此：

> **不要把 Synthea 伪装成真实 radiology benchmark。**

第一版可以让：

```text
ORDER_CTA
```

返回：

```text
CTA completed
+
associated structured finding
```

如果需要复杂影像结果，要自己写 Synthea custom module 或额外构造 Observation。

---

# 10. 推荐的 Synthea Forest Case JSON

转换以后统一成：

```json
{
  "case_id": "CFB_SYN_000001",

  "dataset": {
    "name": "Synthea",
    "version": "vX",
    "source_patient_id": "patient-001",
    "source_encounter_id": "encounter-2026-01"
  },

  "case_type": "DIAGNOSTIC_EVIDENCE_ACQUISITION",

  "initial_state": {
    "demographics": {
      "age": 61,
      "sex": "male"
    },

    "presentation": {
      "chief_complaint": "Chest pain"
    },

    "initial_vitals": {
      "heart_rate": 108,
      "spo2": 92
    }
  },

  "action_space": [
    "ORDER_CBC",
    "ORDER_BMP",
    "ORDER_TROPONIN",
    "ORDER_D_DIMER",
    "ORDER_CTA_CHEST",
    "FINAL_DIAGNOSIS"
  ],

  "evidence_pool": [
    {
      "action_id": "ORDER_TROPONIN",
      "result": {
        "value": 0.07,
        "unit": "ng/mL"
      },
      "source": "Observation/troponin-001"
    },

    {
      "action_id": "ORDER_D_DIMER",
      "result": {
        "value": 1240,
        "unit": "ng/mL"
      },
      "source": "Observation/ddimer-001"
    },

    {
      "action_id": "ORDER_CTA_CHEST",
      "result": {
        "finding": "Pulmonary embolism evidence"
      },
      "source": [
        "Procedure/cta-001",
        "Condition/pe-001"
      ]
    }
  ],

  "reference": {
    "primary_condition": "Pulmonary embolism"
  },

  "original_trajectory": {
    "ordered_actions": [
      "ORDER_TROPONIN",
      "ORDER_D_DIMER",
      "ORDER_CTA_CHEST"
    ]
  }
}
```

这就是可以直接塞进你现有 Arena 的格式。

---

# 11. 一个医生怎么玩这个 Synthea Case

## S0

```text
61岁男性
胸痛
HR 108
SpO2 92%
```

医生 A：

```text
ORDER_TROPONIN
```

返回：

```text
0.07 ng/mL
```

形成：

```text
S0
 ↓ Troponin
S1
```

医生更新 differential。

然后：

```text
ORDER_D_DIMER
```

返回：

```text
1240 ng/mL
```

再：

```text
ORDER_CTA_CHEST
```

最后：

```text
FINAL_DIAGNOSIS = PE
```

路径：

```text
S0
→ Troponin
→ D-dimer
→ CTA
→ PE
```

---

# 12. 医生 B

```text
S0
→ D-dimer
→ CTA
→ PE
```

---

# 13. 医生 C

```text
S0
→ CBC
→ Troponin
→ D-dimer
→ CTA
→ PE
```

最终：

```text
                   Troponin
                  /         \
S0 ───────── D-dimer        D-dimer
  \               \            |
   CBC             CTA         CTA
    \               |           |
   Troponin         PE          PE
```

形成：

> Synthea Patient Decision Graph。

---

# 14. 但是 Synthea 真正最值得你的地方：你可以主动生成“Forest-ready Case”

这比 MIMIC 强。

MIMIC：

> 病人现实中没做的检查，你永远没有真实结果。

Synthea：

> 你本来就在控制数据生成程序。

因此可以进一步做：

# Forest-ready Synthea Module

例如专门设计：

```text
Chest Pain Module
```

患者进入：

```text
Initial State
```

后台同时生成：

```text
CBC
BMP
Troponin
D-dimer
BNP
CXR structured result
CTA structured result
```

但这些全部：

```text
hidden = true
```

游戏时医生点哪个，就揭示哪个。

---

# 15. Forest-ready Module 概念结构

例如：

```text
Chest Pain Presentation
          │
          ├─ hidden CBC
          ├─ hidden BMP
          ├─ hidden Troponin
          ├─ hidden D-dimer
          ├─ hidden CXR result
          └─ hidden CTA result
```

注意：

> 这些不是医生真正按照这个顺序做的检查。

而是：

> **预先生成的患者证据银行。**

这样就解决：

```text
医生想查 D-dimer
→ 有结果

医生想查 Troponin
→ 有结果

医生想查 CXR
→ 有结果
```

开放 benchmark 的 branch coverage 会非常好。

---

# 16. Synthea 我建议保留两个版本

## Synthea-Natural

完全使用默认生成患者。

用途：

> 看正常 Synthea trajectory 能不能自然产生 Forest。

---

## Synthea-Forest

自己编写 Forest-ready module。

用途：

> 获得完整、可控制、可复现的证据空间。

两者千万不要混。

Case metadata：

```json
{
  "generation_mode": "NATURAL"
}
```

或者：

```json
{
  "generation_mode": "FOREST_READY_CUSTOM_MODULE"
}
```

---

# 第二部分：MedAgentBench 怎么变成 Forest Case

# 17. 首先要重新理解 MedAgentBench

它不是一个 diagnosis dataset。

它原本测试：

> AI 能不能操作真实风格的 EHR API。

MedAgentBench 有：

- 300 个医生编写任务；
- 10 类任务；
- 100 个患者；
- 78.5 万左右 EHR records；
- FHIR-compliant environment。 citeturn475616search0turn275672view1


原始患者来自 Stanford STARR 数据仓库，经过 de-identification（去标识）和时间扰动；提取了最近约 5 年：

- laboratory；
- vital signs；
- procedure orders；
- diagnoses；
- medication orders。 citeturn475616search0


因此它非常适合：

> **EHR Clinical Workflow Forest（电子病历临床工作流森林）**

---

# 18. MedAgentBench 已经天然拥有 Action Space

它公开的函数中包括：

```text
GET Patient

GET Condition
GET Observation
GET MedicationRequest
GET Procedure

POST Observation
POST MedicationRequest
POST ServiceRequest
```

官方函数 schema 就是通过这些 FHIR API 来完成 benchmark。citeturn866025view0

这几乎已经是你 Forest 的：

```text
Action Ontology
```

不需要重新发明。

---

# 19. 原始 MedAgentBench Task 长什么样

例如它真实包含这种任务：

```json
{
  "id": "task5_1",

  "instruction":
    "Check patient S6315806's last serum magnesium level
     within last 24 hours.
     If low, order replacement IV magnesium according
     to dosing instructions.",

  "context":
    "It's 2023-11-13T10:15:00+00:00 now.
     The code for magnesium is MG.
     ..."
}
```

官方 benchmark 中确实存在“查最近 magnesium，如果低则按规则开 IV magnesium”这类多步任务。citeturn203650view0

原版 Benchmark 的正确轨迹可能是：

```text
GET Observation(MG)
        ↓
判断 magnesium
        ↓
POST MedicationRequest
        ↓
完成
```

---

# 20. 直接把这个 Task 拿来做 Forest 有一个问题

原始 prompt 已经告诉医生：

> 查 magnesium。

那么根本不会产生真正的决策分叉。

所有医生：

```text
GET magnesium
```

所以不能直接拿：

```text
instruction
```

作为 Forest 起点。

---

# 21. 我建议 MedAgentBench 做两种 Forest

# A. Workflow Forest

保留原始任务目标。

研究：

> **不同医生/模型用什么 EHR 操作序列完成相同工作。**

例如：

```text
任务：
处理这个患者当前的低镁风险。
```

Doctor A：

```text
GET magnesium
→ POST replacement
```

Doctor B：

```text
GET magnesium
→ GET medication
→ GET creatinine
→ POST replacement
```

Doctor C：

```text
GET magnesium
→ GET diagnoses
→ GET medications
→ POST replacement
```

最终形成：

> Workflow Forest。

---

# B. Clinical Management Forest

去掉明确操作提示，只保留患者触发状态。

例如：

```text
某住院患者晨间电解质监测出现需要进一步处理的异常。
请评估患者，并决定下一步管理。
```

不同医生自行决定：

```text
查 Mg？
查 K？
查 renal function？
看 medication？
直接 replacement？
```

这个分叉更接近：

> clinical policy。

但它需要你另外设计临床场景和安全标准。

---

# 22. 推荐第一版先做 Workflow Forest

因为：

- 原数据有明确 benchmark solution；
- 已有任务；
- 已有 FHIR server；
- 已有 evaluator；
- 工程成本最低；
- 可以马上产生路径树。

---

# 23. 一个 MedAgentBench 原始患者怎么读

你实际上不必先下载一个巨大 JSON。

官方 Docker 本身就是 HAPI FHIR Server。

启动：

```bash
docker pull jyxsu6/medagentbench:latest

docker run -p 8080:8080 medagentbench
```

官方仓库就是这样启动环境。citeturn275672view0

然后查询：

```text
GET /Patient
GET /Observation
GET /Condition
GET /MedicationRequest
GET /Procedure
```

---

# 24. 假设查询患者得到下面这些资源

下面仍然是为解释转换逻辑而简化的 JSON。

```json
{
  "patient": {
    "id": "S6315806",
    "age": 68,
    "sex": "male"
  },

  "conditions": [
    {
      "code": "I10",
      "display": "Hypertension"
    }
  ],

  "observations": [
    {
      "code": "MG",
      "display": "Magnesium",
      "time": "2023-11-13T07:00:00Z",
      "value": 1.3,
      "unit": "mg/dL"
    },

    {
      "code": "CREAT",
      "display": "Creatinine",
      "time": "2023-11-13T06:55:00Z",
      "value": 1.1,
      "unit": "mg/dL"
    },

    {
      "code": "K",
      "display": "Potassium",
      "time": "2023-11-13T07:00:00Z",
      "value": 3.5,
      "unit": "mmol/L"
    }
  ],

  "medications": [
    {
      "display": "Furosemide"
    }
  ]
}
```

---

# 25. 转换成 Forest Case

```json
{
  "case_id": "CFB_MAB_MG_0001",

  "dataset": {
    "name": "MedAgentBench",
    "source_patient_id": "S6315806",
    "source_task_id": "task5_1"
  },

  "case_type": "EHR_WORKFLOW",

  "anchor_time": "2023-11-13T10:15:00Z",

  "initial_state": {
    "patient": {
      "age": 68,
      "sex": "male"
    },

    "clinical_goal": {
      "type": "ELECTROLYTE_MANAGEMENT",
      "text": "Review this patient's current electrolyte status and determine whether intervention is needed."
    }
  },

  "action_space": [
    {
      "action_id": "QUERY_MAGNESIUM",
      "fhir_operation": "GET Observation"
    },

    {
      "action_id": "QUERY_CREATININE",
      "fhir_operation": "GET Observation"
    },

    {
      "action_id": "QUERY_POTASSIUM",
      "fhir_operation": "GET Observation"
    },

    {
      "action_id": "QUERY_MEDICATIONS",
      "fhir_operation": "GET MedicationRequest"
    },

    {
      "action_id": "QUERY_CONDITIONS",
      "fhir_operation": "GET Condition"
    },

    {
      "action_id": "ORDER_MAGNESIUM",
      "fhir_operation": "POST MedicationRequest"
    },

    {
      "action_id": "STOP"
    }
  ],

  "hidden_state": {
    "magnesium": {
      "value": 1.3,
      "unit": "mg/dL"
    },

    "creatinine": {
      "value": 1.1,
      "unit": "mg/dL"
    },

    "potassium": {
      "value": 3.5,
      "unit": "mmol/L"
    },

    "medications": [
      "Furosemide"
    ]
  },

  "reference": {
    "task_success": {
      "requires_magnesium_replacement": true
    }
  }
}
```

---

# 26. 医生 A 玩

初始：

```text
68岁男性
住院患者

请评估当前电解质状态，并决定是否需要干预。
```

Doctor A：

```text
QUERY_MAGNESIUM
```

返回：

```text
Mg = 1.3 mg/dL
```

然后：

```text
ORDER_MAGNESIUM
```

完成。

路径：

```text
S0
→ Mg
→ replacement
```

---

# 27. 医生 B

```text
S0
→ Mg
→ Creatinine
→ Medication list
→ replacement
```

---

# 28. 医生 C

```text
S0
→ Medication list
→ Mg
→ K
→ Creatinine
→ replacement
```

最后：

```text
                       Mg
                     /    \
S0 ───────── Medications   Creatinine
  \               |            |
   Mg             Mg       Medications
    \              |            |
     K         Creatinine    replacement
      \
   Creatinine
       \
    replacement
```

这就是：

> **同一患者、同一临床目标、不同医生的信息获取和管理路径。**

---

# 29. 这与 Synthea Forest 的区别

Synthea 主要是：

```text
Patient presentation
↓
Which evidence do you acquire?
↓
What diagnosis do you reach?
```

MedAgentBench 主要是：

```text
Patient + clinical task
↓
Which EHR data do you inspect?
↓
Which action do you execute?
↓
Did you complete the clinical workflow?
```

所以应该分别命名：

```text
Synthea Diagnostic Forest
```

和：

```text
MedAgentBench Workflow Forest
```

不要混成一个 task。

---

# 30. MedAgentBench 的另一个巨大优势：Action 是真正可执行的

DDXPlus：

```text
ASK
```

只是 reveal data。

Synthea：

```text
ORDER_LAB
```

第一版通常也是：

> reveal already-generated hidden observation。

MedAgentBench：

```text
POST MedicationRequest
POST ServiceRequest
POST Observation
```

是真的会修改 FHIR Server 状态。官方环境明确支持这些读取和写入操作。citeturn866025view0

因此开始具有：

\[
S_t + A_t \rightarrow S_{t+1}
\]

的意味。

例如：

```text
S0
↓
POST MedicationRequest
↓
EHR 中新增 MedicationRequest
↓
S1
```

这比 DDXPlus 更接近真正的：

> dynamic environment（动态环境）。

---

# 31. 但是不要误认为这是患者生理状态变化

例如：

```text
POST magnesium replacement
```

只是：

> EHR 中新增一个 MedicationRequest。

它不会自动模拟：

```text
Mg 1.3
↓ 治疗
Mg 1.8
```

所以它仍然不是 patient world model（患者世界模型）。

这一点和真正 longitudinal clinical simulator 必须区分。

---

# 32. MedAgentBench Case 转换流水线

建议写：

```text
medagentbench_adapter/
├── discover_patients.py
├── fetch_patient_resources.py
├── parse_tasks.py
├── identify_task_patient.py
├── build_task_context.py
├── build_action_catalog.py
├── build_hidden_resource_index.py
└── export_forest_cases.py
```

流程：

```text
Docker FHIR Server
        ↓
读取 test_data_v1.json
        ↓
找到 task_id
        ↓
找到 eval_MRN
        ↓
FHIR 查询 Patient
        ↓
FHIR 查询：
Condition
Observation
MedicationRequest
Procedure
        ↓
形成 patient resource cache
        ↓
转换成 Forest Case
```

---

# 33. MedAgentBench 不要把 70 万条数据全部塞进一个 Case JSON

一个患者可能有大量纵向记录。

应该分：

```text
case.json
```

只保存索引。

例如：

```json
{
  "case_id": "...",

  "patient_id": "...",

  "resource_index": {
    "conditions": 34,
    "observations": 9214,
    "medications": 183,
    "procedures": 1103
  }
}
```

实际资源保存在：

```text
resources/
├── observations.parquet
├── conditions.parquet
├── medications.parquet
└── procedures.parquet
```

Arena 根据 Action 动态查询。

---

# 34. MedAgentBench 的 State Hash

不能只用：

```text
revealed evidence set
```

还要包括 EHR modifications。

例如：

```text
state_hash =
hash(
 patient_id,
 revealed_resource_ids,
 created_resource_ids
)
```

因为：

```text
Doctor A:
已经开了 Mg
```

和：

```text
Doctor B:
还没有开 Mg
```

不是同一个 State。

---

# 35. 最终统一的数据模型

这样四个数据集可以全部进入同一个 ForestBench。

## DDXPlus

```json
{
  "action": "ASK_EVIDENCE",
  "observation": "PATIENT_RESPONSE"
}
```

## Synthea

```json
{
  "action": "QUERY_OR_ORDER_CLINICAL_EVIDENCE",
  "observation": "FHIR_CLINICAL_RESOURCE"
}
```

## MedAgentBench

```json
{
  "action": "FHIR_READ_OR_WRITE",
  "observation": "FHIR_RESPONSE"
}
```

## MIMIC

```json
{
  "action": "ORDER_OR_ACQUIRE_REAL_EVIDENCE",
  "observation": "REAL_RECORDED_CLINICAL_RESULT"
}
```

但共同抽象为：

```text
State
   ↓
Action
   ↓
Observation
   ↓
Belief
   ↓
New State
```

这就是整个 ForestBench 最核心的数据接口。

---

# 36. 我建议你实际开发顺序

## 第一阶段：Synthea Natural

先生成：

```text
1000 patients
```

把每个患者：

```text
FHIR Bundle
```

拆成：

```text
Encounter
```

筛：

```text
50 个 evidence-rich encounter
```

生成：

```text
CFB_SYN_NATURAL_50
```

目的：

> 验证纵向 FHIR → Forest Case 转换。

---

# 37. 第二阶段：Synthea Forest-ready

选择一个疾病场景，例如：

> Chest pain。

自己写 Synthea module。

明确生成：

```text
Initial presentation

+
5–10 个 hidden evidence

+
Reference diagnosis
```

生成：

```text
CFB_SYN_FOREST_CHESTPAIN_500
```

这里非常适合成为你 benchmark 的：

> **完全公开、任何人都能直接运行的标准 Diagnostic Track。**

---

# 38. 第三阶段：MedAgentBench

不要先转换全部 300 task。

先从三种 task 开始：

### A. Laboratory retrieval

例如：

> 查询最近 Mg。

### B. Conditional management

例如：

> Mg 低 → replacement。

### C. Medication / procedure action

例如：

> 根据 EHR state 创建正确 order。

每类先 10 个：

```text
30 cases
```

先验证：

> 多次玩家执行以后能否形成 Workflow Forest。

---

# 39. 第四阶段再做真正 Physician Study

一个很漂亮的实验设计是：

同一个临床 trigger：

```text
Patient S6315806
+
electrolyte management
```

给：

```text
Resident
Attending
Hospitalist
AI
```

完全相同环境。

最后比较：

```text
查询顺序
查询数量
不必要查询
遗漏信息
最终 Action
到正确 Action 的步数
```

得到：

\[
P(A|S,Z)
\]

这就已经非常符合 ClincForestBench 的核心思想。

---

# 40. 两个数据集我最终建议怎么用

## Synthea 的真正价值

不是“再多一个 synthetic dataset”。

而是：

> **可以主动设计完全开放、证据覆盖完整、可重复生成的 Forest-ready patient environment。**

它能解决 MIMIC 最大的问题：

> 医生要一个原病例没做过的检查 → 没有结果。

因为在 Synthea-Forest 里，可以事先把标准证据集合全部生成。

---

## MedAgentBench 的真正价值

不是“拿它做 diagnosis”。

而是：

> **第一次把你的 Forest 从 information reveal 扩展到真正 EHR read/write action。**

它能让：

```text
Clinical Decision Forest
```

从：

> “医生想知道什么？”

向：

> “医生真正做了什么？”

推进一步。

---

# 41. 因此我现在建议的 ForestBench 四层结构

```text
LEVEL 1
DDXPlus
────────────────────
History Forest

ASK
→ patient evidence
→ belief


LEVEL 2
Synthea
────────────────────
Diagnostic Evidence Forest

clinical presentation
→ lab / observation / procedure
→ diagnosis


LEVEL 3
MedAgentBench
────────────────────
Workflow / Action Forest

EHR state
→ query
→ order
→ modify record
→ task outcome


LEVEL 4
MIMIC
────────────────────
Real Clinical Forest

real patient
→ real evidence
→ physician policy
→ real clinical validation
```

这四层不是重复 benchmark。

而是：

> **从病史推理 → 合成 EHR 诊断 → EHR 工作流执行 → 真实临床决策逐层增加真实性与复杂度。**

这会比单独做 DDXPlus + MIMIC 的故事完整很多。

---

# 42. 下一步工程上最推荐先做什么

如果你当前 DDXPlus Arena 已经基本完成，我建议顺序是：

```text
第一步
实现通用 FHIR adapter

        ↓

第二步
接 Synthea 一个 patient Bundle

        ↓

第三步
自动识别 Encounter

        ↓

第四步
把 Encounter 转成：
Initial State
Hidden Evidence Pool
Reference

        ↓

第五步
接入现有 Arena

        ↓

第六步
自己玩三次
生成第一棵 Synthea Tree

        ↓

第七步
再接 MedAgentBench FHIR Server

        ↓

第八步
把 GET / POST 调用转换成 Forest Action

        ↓

第九步
完成第一棵 Workflow Tree
```

**最重要的工程决定是现在就增加一个统一的 `FHIRClinicalEnvironment`。**

以后：

```text
SyntheaFHIRAdapter
MedAgentBenchFHIRAdapter
MIMICFHIRAdapter（如果以后转 FHIR）
```

都实现相同接口：

```text
load_case()

get_initial_state()

list_actions()

execute_action()

get_observation()

submit_belief()

finalize()

replay()
```

这样你现在的 DDXPlus 前端、Session、Event Log、Graph Builder、Forest Explorer 全部不需要重写。