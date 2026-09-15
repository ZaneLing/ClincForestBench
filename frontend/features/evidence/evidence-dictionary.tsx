'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  ArrowRight,
  BookOpenText,
  Braces,
  CircleDot,
  FileJson2,
  GitBranch,
  History,
  Search,
  ShieldCheck,
  Stethoscope,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { api } from '@/lib/api';
import { DatasetCaseWalkthrough } from './dataset-case-walkthrough';

type EvidenceDefinition = {
  evidence_id: string;
  question_en: string;
  is_antecedent: boolean;
  data_type: 'binary' | 'categorical' | 'multi_choice';
  default_value: unknown;
  possible_values: unknown[];
  value_meanings: Record<string, unknown>;
  parent_evidence_id: string | null;
  semantic_role: string;
};

type DatasetName =
  | 'DDXPlus'
  | 'Synthea'
  | 'MedAgentBench'
  | 'MIMIC-IV multimodal'
  | 'MC-MED v1.0.1'
  | 'eICU-CRD v2.0'
  | 'PMC Case Reports'
  | 'NEJM CPC';

type DatasetGuide = {
  name: DatasetName;
  shortName: string;
  title: string;
  subtitle: string;
  source: string;
  cases: number;
  caseType: string;
  playerAction: string;
  checkpoint: string;
  truth: string;
  fields: Array<{
    field: string;
    source: string;
    meaning: string;
    mapsTo: string;
  }>;
  pipeline: Array<{ title: string; detail: string }>;
  rules: string[];
  boundary: string;
  exampleCaseId: string;
  exampleKind: 'CLASSIC' | 'TEMPORAL';
};

const GUIDES: DatasetGuide[] = [
  {
    name: 'DDXPlus',
    shortName: 'DDX',
    title: '症状问询森林',
    subtitle: '从完整 Evidence 候选池主动问诊，逐轮收敛鉴别诊断。',
    source: 'release_train_patients.zip + release_evidences.json',
    cases: 50,
    caseType: 'DIAGNOSTIC_QUESTIONING',
    playerAction: '选择症状、病史或症状细节问题',
    checkpoint: '每次回答后提交疾病排序',
    truth: 'PATHOLOGY + DIFFERENTIAL_DIAGNOSIS',
    fields: [
      { field: 'AGE / SEX', source: 'patient row', meaning: '患者年龄与生理性别', mapsTo: 'demographics / initial context' },
      { field: 'EVIDENCES', source: 'patient row', meaning: '该病例实际命中的 E_* 证据及取值', mapsTo: 'case evidence values' },
      { field: 'INITIAL_EVIDENCE', source: 'patient row', meaning: '开局直接暴露的主诉证据', mapsTo: 'S0 initial observation' },
      { field: 'PATHOLOGY', source: 'patient row', meaning: '病例 Ground Truth 疾病', mapsTo: 'red diagnosis node' },
      { field: 'DIFFERENTIAL_DIAGNOSIS', source: 'patient row', meaning: '[疾病, 概率] 的完整鉴别诊断列表', mapsTo: 'final diagnosis layer' },
      { field: 'E_* definition', source: 'release_evidences.json', meaning: '问题文本、类型、取值翻译和父问题关系', mapsTo: 'action catalog + dependencies' },
    ],
    pipeline: [
      { title: '读取患者行', detail: '保留原始 AGE、SEX、EVIDENCES 与诊断分布。' },
      { title: '连接字段定义', detail: '把 E_* 编号连接到可读问题、取值与父子关系。' },
      { title: '构造状态树', detail: 'Action → Yes/No/Value Observation；最终展开全部鉴别诊断。' },
      { title: '进入 Arena', detail: '从 223 个 Evidence 中选择；命中为 Yes，未命中为 No。' },
    ],
    rules: [
      '开局只暴露人口学信息与 INITIAL_EVIDENCE。',
      '问题来自完整的 223 项 Evidence 定义，不只来自患者命中的证据。',
      '父问题未询问前，依赖的症状细节不会出现在候选池。',
      '每获得一次回答，都必须提交当下的疾病排序；排序不变也可直接提交。',
    ],
    boundary: '回答完全由原始病例行和 Evidence 字典决定；Arena 进行中不暴露 PATHOLOGY 或鉴别诊断概率。',
    exampleCaseId: 'DDX_TEST_0021752',
    exampleKind: 'CLASSIC',
  },
  {
    name: 'Synthea',
    shortName: 'SYN',
    title: '纵向 EHR 证据森林',
    subtitle: '把完整合成患者时间线切成一个可游玩的 index clinical episode。',
    source: 'Official Synthea CSV sample export',
    cases: 50,
    caseType: 'DIAGNOSTIC_EVIDENCE_ACQUISITION',
    playerAction: '查看该就诊下的检查、操作与用药记录',
    checkpoint: '每次查看记录后提交参考疾病排序',
    truth: 'Encounter reason + linked Condition records',
    fields: [
      { field: 'Id / BIRTHDATE / GENDER', source: 'patients.csv', meaning: '患者标识与人口学信息', mapsTo: 'demographics' },
      { field: 'Id / PATIENT / START / STOP', source: 'encounters.csv', meaning: '就诊归属与时间边界', mapsTo: 'index encounter root' },
      { field: 'ENCOUNTERCLASS / REASONDESCRIPTION', source: 'encounters.csv', meaning: '就诊类型与原因', mapsTo: 'initial_context' },
      { field: 'CODE / DESCRIPTION / VALUE / UNITS', source: 'observations.csv', meaning: '生命体征、检验或结构化观察结果', mapsTo: 'observation action + result node' },
      { field: 'CODE / DESCRIPTION', source: 'procedures.csv', meaning: '该就诊已记录的临床操作', mapsTo: 'procedure action + result node' },
      { field: 'CODE / DESCRIPTION / START / STOP', source: 'medications.csv', meaning: '该就诊关联的用药记录', mapsTo: 'medication action + result node' },
      { field: 'CODE / DESCRIPTION', source: 'conditions.csv', meaning: '该 episode 的参考疾病记录', mapsTo: 'final diagnosis layer' },
    ],
    pipeline: [
      { title: '纵向患者', detail: '以 PATIENT 键关联多个 CSV 资源和全部就诊。' },
      { title: '切取 Episode', detail: '选择具备 reason、检验和处置记录的 index encounter。' },
      { title: '保留原始行', detail: '按 encounter 连接 Observation、Procedure、Medication、Condition。' },
      { title: '构造证据树', detail: '就诊背景先暴露，记录按依赖成为可查看动作，Condition 进入参考层。' },
    ],
    rules: [
      '只可查看当前 case 中确实存在的结构化记录，不提供 223 项通用问诊池。',
      '展示值、单位、编码和时间均来自原始 CSV 行。',
      '查看记录是只读动作，不代表医生真的重新开具了检查或药物。',
      '每获取一条记录后提交当前疾病排序；病例结束后再展示参考 Condition。',
    ],
    boundary: '这是 Synthea 官方 CSV 样本的自然导出，不把资源顺序宣称为真实医生推理顺序，也不虚构影像报告或自由文本病历。',
    exampleCaseId: 'SYN_ENC_0001',
    exampleKind: 'CLASSIC',
  },
  {
    name: 'MedAgentBench',
    shortName: 'MAB',
    title: 'FHIR 临床行动森林',
    subtitle: '把自然语言任务和官方函数定义转换成可逐步执行的 EHR 工作流。',
    source: 'test_data_v2.json + funcs_v1.json',
    cases: 30,
    caseType: 'WORKFLOW_FOREST',
    playerAction: '执行依赖明确的 FHIR 查询、校验或写入步骤',
    checkpoint: '每一步后提交工作流结果排序',
    truth: 'Official task solution / expected workflow family',
    fields: [
      { field: 'id', source: 'test_data_v2.json', meaning: '官方任务编号', mapsTo: 'case_id / provenance' },
      { field: 'instruction', source: 'test_data_v2.json', meaning: '需要完成的临床 EHR 任务', mapsTo: 'initial_context.task' },
      { field: 'context', source: 'test_data_v2.json', meaning: '当前时间、代码、阈值与输出约束', mapsTo: 'initial_context.constraints' },
      { field: 'eval_MRN', source: 'test_data_v2.json', meaning: '任务目标患者标识', mapsTo: 'patient resolution action' },
      { field: 'sol', source: 'test_data_v2.json', meaning: '官方答案或评分参考', mapsTo: 'protected reference' },
      { field: 'name / parameters', source: 'funcs_v1.json', meaning: '允许的 FHIR 函数及参数 schema', mapsTo: 'action schema' },
      { field: 'resourceType / request', source: 'derived workflow', meaning: 'Patient、Observation、ServiceRequest 或 MedicationRequest 操作', mapsTo: 'action / observation nodes' },
    ],
    pipeline: [
      { title: '读取官方任务', detail: '保留 instruction、context、MRN 与 solution，不改写临床约束。' },
      { title: '识别任务族', detail: 'MVP 覆盖近期镁值检索、条件补镁和骨科转诊。' },
      { title: '展开函数步骤', detail: '按 funcs_v1 定义形成 Patient → Resource → Verify/Create 的依赖链。' },
      { title: '工作流 Arena', detail: '医生逐步执行动作，并提交当前最可能的工作流结果。' },
    ],
    rules: [
      '当前 MVP 为 OFFLINE_TASK_REPLAY，动作顺序由官方任务和函数 schema 推导。',
      '患者解析完成后才显示资源查询；查询完成后才显示校验或写入动作。',
      '阶段候选是工作流结果，不是疾病诊断；仍使用选择、排序、删除和逐轮提交。',
      '会创建资源的任务明确标注写入语义，并在状态哈希中跟踪创建结果。',
    ],
    boundary: '本机没有运行官方 FHIR Server，因此不会伪造患者记录、化验值或已创建资源；页面只回放有来源支持的工作流与输出规则。',
    exampleCaseId: 'MAB_TASK4_1',
    exampleKind: 'CLASSIC',
  },
  {
    name: 'MIMIC-IV multimodal',
    shortName: 'MIMIC',
    title: '住院多模态时间森林',
    subtitle: '以真实住院时间为轴，保留医嘱、检验、影像与 ECG 的可用时间差。',
    source: 'MIMIC-IV hosp + MIMIC-IV Note + MIMIC-CXR-JPG/ECG metadata',
    cases: 10,
    caseType: 'TEMPORAL_DIAGNOSTIC_ACTION',
    playerAction: '在当前时刻开检查或调阅资料；系统立即推进模拟时钟',
    checkpoint: '每个结果揭示后提交疾病排序',
    truth: 'Source-supported discharge/diagnosis reference',
    fields: [
      { field: 'subject_id / hadm_id', source: 'admissions / diagnoses_icd', meaning: '患者与住院 episode 主键', mapsTo: 'case provenance / episode root' },
      { field: 'admittime / dischtime', source: 'admissions', meaning: '住院真实时间边界', mapsTo: 'T0 / episode interval' },
      { field: 'order_provider_id / ordertime', source: 'poe', meaning: '医嘱及其发起时间', mapsTo: 'order action node' },
      { field: 'charttime / storetime', source: 'labevents', meaning: '标本结果时间与系统可见时间', mapsTo: 'pending → revealed observation' },
      { field: 'study_id / StudyDateTime', source: 'MIMIC-CXR', meaning: '影像检查与报告时间', mapsTo: 'imaging action + right-side payload' },
      { field: 'ecg_time / report', source: 'MIMIC-IV-ECG', meaning: '心电记录及机器/医师文本', mapsTo: 'ECG observation node' },
    ],
    pipeline: [
      { title: '锁定住院 Episode', detail: '以 hadm_id 连接诊断、医嘱、化验、文本和可用的多模态记录。' },
      { title: '统一到 T+ 分钟', detail: '以 admittime 为 T0，并同时保留原始绝对时间与时间来源。' },
      { title: '建立可用性延迟', detail: '区分 order、performed、result 和 chart/store 时间；点击动作后模拟时钟直接跳到结果可用点。' },
      { title: '生成动态树', detail: '动作分支连接 result observation 与受保护 reference，进入同一 Arena 状态机。' },
    ],
    rules: [
      '医生只能看到当前 game time 已经可用的信息，不能从未来结果反推当前判断。',
      '影像、ECG、实验室报告保存在对应 observation 节点详情中，不只显示一个标签。',
      '不要求现实等待；一次点击在同一请求中推进模拟时间并揭示真实记录结果。',
      '最多执行 30 个动作；可随时锁定唯一诊断并结束病例。',
    ],
    boundary: '每个节点携带时间来源与置信等级；缺少可核验时间或多模态文件时会明确标注，不把推断时间伪装成精确事实。',
    exampleCaseId: 'CFB_MIMIC_20554296',
    exampleKind: 'TEMPORAL',
  },
  {
    name: 'MC-MED v1.0.1',
    shortName: 'MCMED',
    title: '急诊检查回报时间森林',
    subtitle: '从到诊主诉出发，按医嘱和结果时间逐步展开急诊诊断路径。',
    source: 'MC-MED v1.0.1 visits/orders/labs/radiology tables',
    cases: 10,
    caseType: 'TEMPORAL_DIAGNOSTIC_ACTION',
    playerAction: '选择急诊检查或调阅记录；结果同步返回',
    checkpoint: '每次患者状态变化后提交疾病排序',
    truth: 'Source-supported encounter diagnosis',
    fields: [
      { field: 'Visit_ID / Patient_ID', source: 'visits', meaning: '急诊就诊与患者主键', mapsTo: 'case / episode identity' },
      { field: 'Arrival_time', source: 'visits', meaning: '患者到诊时间', mapsTo: 'T0 initial state' },
      { field: 'Chief_complaint', source: 'visits', meaning: '开局可见主诉', mapsTo: 'initial context' },
      { field: 'Order_time', source: 'orders', meaning: '检查或处置发起时间', mapsTo: 'order action' },
      { field: 'Result_time / Value / Unit', source: 'labs', meaning: '检验可见时间与结果', mapsTo: 'delayed observation payload' },
      { field: 'Report_time / Report_text', source: 'radiology', meaning: '影像报告可见时间与全文', mapsTo: 'imaging node detail' },
    ],
    pipeline: [
      { title: '按就诊聚合', detail: '把同一 Visit_ID 的主诉、医嘱、检验和影像记录收拢为 episode。' },
      { title: '规范时间轴', detail: 'Arrival_time 为 T0，其余记录转换为 T+ 分钟并保留原值。' },
      { title: '动作—结果配对', detail: 'Order_time 形成可选动作，Result/Report_time 决定揭示节点。' },
      { title: '输出动态森林', detail: '每个检查分支可独立推进，最终和 reference diagnosis 分层比较。' },
    ],
    rules: [
      '开局只显示到诊时已经知道的患者信息和主诉。',
      '父动作没有执行时，其结果节点不可见；执行后模拟时钟自动推进到结果可见时间。',
      '检查报告全文和结构化值都保存在节点详情，可用于下一轮判断。',
      '每次新信息揭示后必须提交排序，允许保持上一轮不变。',
    ],
    boundary: '仅使用源表中能连接到具体 Visit_ID 的信息；无法确定的先后关系会标注为低时间置信度。',
    exampleCaseId: 'CFB_MC_99221396',
    exampleKind: 'TEMPORAL',
  },
  {
    name: 'eICU-CRD v2.0',
    shortName: 'eICU',
    title: 'ICU 相对时间森林',
    subtitle: '以 ICU 入科为零点，让生命体征、实验室、治疗和病史沿 offset 动态生长。',
    source: 'eICU-CRD v2.0 patient/lab/vitalPeriodic/treatment tables',
    cases: 10,
    caseType: 'TEMPORAL_DIAGNOSTIC_ACTION',
    playerAction: '问询病史、执行查体、开具检查或查看 ICU 数据流',
    checkpoint: '每个 observation state 后提交疾病排序',
    truth: 'Admission/discharge diagnosis reference',
    fields: [
      { field: 'patientunitstayid', source: 'patient', meaning: '一次 ICU stay 的稳定主键', mapsTo: 'case identity' },
      { field: 'unitadmitoffset', source: 'patient', meaning: 'ICU 入科相对时间基准', mapsTo: 'T0' },
      { field: 'labresultoffset / labresult', source: 'lab', meaning: '检验结果相对时间和值', mapsTo: 'timed laboratory observation' },
      { field: 'observationoffset', source: 'vitalPeriodic', meaning: '床旁生命体征采样时间', mapsTo: 'timed vital observation' },
      { field: 'treatmentoffset / treatmentstring', source: 'treatment', meaning: '治疗发生时间和描述', mapsTo: 'treatment branch' },
      { field: 'diagnosisoffset / diagnosisstring', source: 'diagnosis', meaning: '记录诊断出现的时间', mapsTo: 'protected reference / provenance' },
    ],
    pipeline: [
      { title: '选择 ICU Stay', detail: '以 patientunitstayid 关联患者、病史、生命体征、实验室和治疗。' },
      { title: '保留原生 Offset', detail: '所有相对分钟直接进入 game time，避免虚构绝对日期。' },
      { title: '清理临床证据', detail: '过滤 Performed、scored 等工作流标记，把病史、查体和检验拆成具体可选动作。' },
      { title: '运行时间状态机', detail: '执行动作后立即推进到对应 offset，只揭示该动作关联的真实结果。' },
    ],
    rules: [
      '相对 offset 决定先后顺序，因此医生在早期和晚期可能作出不同判断。',
      '高频生命体征采用有来源的代表节点，避免用未来数据淹没当前决策。',
      '治疗记录是临床轨迹信息，不自动等同于正确诊断。',
      '缺失值保持缺失，不使用默认正常值补齐。',
    ],
    boundary: 'eICU 的 offset 是可靠的相对顺序，但不代表跨医院统一的绝对时间；数据缺失和采样偏差在 Case 中显式保留。',
    exampleCaseId: 'CFB_EICU_146133',
    exampleKind: 'TEMPORAL',
  },
  {
    name: 'PMC Case Reports',
    shortName: 'PMC',
    title: '病例报告叙事森林',
    subtitle: '将公开病例报告按临床叙事顺序切成可逐步揭示的信息节点。',
    source: 'PubMed Central open-access case reports',
    cases: 5,
    caseType: 'TEMPORAL_NARRATIVE_REPLAY',
    playerAction: '调阅下一段病史、检查、影像或病理信息',
    checkpoint: '每段新叙事证据后提交疾病排序',
    truth: 'Article-supported final diagnosis',
    fields: [
      { field: 'PMCID / PMID / DOI', source: 'article metadata', meaning: '文章来源标识', mapsTo: 'provenance links' },
      { field: 'title / abstract', source: 'JATS XML', meaning: '病例主题与摘要', mapsTo: 'case metadata, not early evidence' },
      { field: 'case narrative paragraph', source: 'article body', meaning: '按文章顺序描述的病史和临床过程', mapsTo: 'ordered narrative observations' },
      { field: 'figure / caption', source: 'article body', meaning: '影像或病理图及图注', mapsTo: 'imaging/pathology node payload' },
      { field: 'final diagnosis sentence', source: 'article body', meaning: '作者支持的最终诊断', mapsTo: 'protected reference node' },
    ],
    pipeline: [
      { title: '解析开放文章', detail: '保存文章标识、章节、段落和可用图像来源。' },
      { title: '临床段落切片', detail: '从病史、检查、影像、病理和随访句子中提取可揭示节点。' },
      { title: '建立叙事顺序', detail: '原文先后作为 proxy time，并将置信度明确标为 narrative。' },
      { title: '保护结局', detail: '最终诊断和讨论内容在完成前隔离，避免标题或摘要泄漏答案。' },
    ],
    rules: [
      '玩家按临床叙事逐步调阅信息，不能直接跳到讨论或最终诊断。',
      '影像或病理图像存在时放入对应节点详情；只有图注时明确标注。',
      '文章段落顺序不是精确临床分钟，因此只表达先后，不伪造时间间隔。',
      '每段新信息后提交当前排序，也可提前锁定唯一诊断。',
    ],
    boundary: '该模式是公开病例报告的离线重放；叙事顺序仅是临床时间代理，所有自动抽取节点都需要保留原句和来源定位。',
    exampleCaseId: 'CFB_PMC_7665777_6',
    exampleKind: 'TEMPORAL',
  },
  {
    name: 'NEJM CPC',
    shortName: 'NEJM',
    title: 'CPC 分阶段诊断森林',
    subtitle: '按病例陈述顺序逐步揭示复杂线索，在最终病理答案前持续更新鉴别诊断。',
    source: 'PubMed-indexed NEJM Case Records / CPC metadata and abstracts',
    cases: 5,
    caseType: 'TEMPORAL_NARRATIVE_REPLAY',
    playerAction: '调阅下一阶段病例陈述；系统同步推进叙事序列',
    checkpoint: '每个 CPC 信息阶段后提交疾病排序',
    truth: 'Published CPC final diagnosis reference',
    fields: [
      { field: 'PMID / DOI', source: 'PubMed XML', meaning: 'CPC 来源标识', mapsTo: 'case provenance' },
      { field: 'ArticleTitle', source: 'PubMed XML', meaning: '文章标题', mapsTo: 'protected metadata when answer-leaking' },
      { field: 'AbstractText', source: 'PubMed XML', meaning: '病例陈述摘要段落', mapsTo: 'narrative evidence chunks' },
      { field: 'MeSHHeading', source: 'PubMed XML', meaning: '人工主题词', mapsTo: 'reference support, not player-visible evidence' },
      { field: 'clinical phase', source: 'derived from narrative order', meaning: 'presentation、workup、pathology 等信息阶段', mapsTo: 'tree stage / proxy time' },
    ],
    pipeline: [
      { title: '读取 PubMed 记录', detail: '保存 PMID、DOI、标题、摘要段落和 MeSH provenance。' },
      { title: '检测答案泄漏', detail: '含最终诊断的标题、主题词和结论在游戏期间进入受保护层。' },
      { title: '按阶段切分', detail: '病例陈述依次形成 presentation、investigation、pathology 节点。' },
      { title: '形成 CPC 树', detail: '每一阶段触发一次判断更新，结束后展示 reference 和群体森林。' },
    ],
    rules: [
      '病例严格按发布叙事的先后阶段揭示，早期无法看到后续病理或最终讨论。',
      '标题、MeSH 或摘要结论若泄漏答案，会在游戏结束前隐藏。',
      '文本阶段用 proxy time 表示顺序，不声称是患者真实分钟级时间。',
      '任何阶段都可以锁定诊断；未锁定时最多推进 30 个动作。',
    ],
    boundary: '当前 MVP 只使用本地可验证的 PubMed/CPC 来源内容；全文缺失时不补写检查结果，reference 强度和时间置信度会单独展示。',
    exampleCaseId: 'CFB_NEJM_26559575',
    exampleKind: 'TEMPORAL',
  },
];

export function EvidenceDictionary() {
  const [evidences, setEvidences] = useState<EvidenceDefinition[]>([]);
  const [query, setQuery] = useState('');
  const [domain, setDomain] = useState<'ALL' | 'SYMPTOM' | 'ANTECEDENT'>('ALL');
  const [notice, setNotice] = useState('正在读取 DDXPlus Evidence 字典…');
  const [datasetName, setDatasetName] = useState<DatasetName>('DDXPlus');

  useEffect(() => {
    let active = true;
    void api<{ evidences: EvidenceDefinition[] }>('/catalog/evidences')
      .then((result) => {
        if (!active) return;
        setEvidences(result.evidences);
        setNotice(`DDXPlus 字典已载入 ${result.evidences.length} 项 Evidence`);
      })
      .catch((error: Error) => {
        if (active) setNotice(`Evidence 字典读取失败：${error.message}`);
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <main className="dataset-guide-page h-dvh overflow-hidden">
      <header className="dataset-guide-header">
        <span className="brand-mark"><BookOpenText /></span>
        <div><p>ClincForestBench · Data contract</p><h1>数据集、转换与 Arena 规则</h1></div>
        <Badge><ShieldCheck /> 8 DATASET CONTRACTS</Badge>
      </header>

      <Tabs className="dataset-guide-tabs" onValueChange={(value) => setDatasetName(value as DatasetName)} value={datasetName}>
        <TabsList aria-label="选择数据集说明">
          {GUIDES.map((guide) => (
            <TabsTrigger key={guide.name} value={guide.name}>
              <span>{guide.shortName}</span><b>{guide.name}</b><small>{guide.title}</small>
            </TabsTrigger>
          ))}
        </TabsList>
        {GUIDES.map((guide) => (
          <TabsContent key={guide.name} value={guide.name}>
            <DatasetGuideContent
              domain={domain}
              evidences={evidences}
              guide={guide}
              notice={notice}
              walkthroughEnabled={datasetName === guide.name}
              onDomainChange={setDomain}
              onQueryChange={setQuery}
              query={query}
            />
          </TabsContent>
        ))}
      </Tabs>
    </main>
  );
}

function DatasetGuideContent({
  guide,
  evidences,
  query,
  domain,
  notice,
  onQueryChange,
  onDomainChange,
  walkthroughEnabled,
}: {
  guide: DatasetGuide;
  evidences: EvidenceDefinition[];
  query: string;
  domain: 'ALL' | 'SYMPTOM' | 'ANTECEDENT';
  notice: string;
  onQueryChange: (value: string) => void;
  onDomainChange: (value: 'ALL' | 'SYMPTOM' | 'ANTECEDENT') => void;
  walkthroughEnabled: boolean;
}) {
  return (
    <div className="dataset-guide-scroll">
      <section className="dataset-contract-hero">
        <div><p>{guide.caseType}</p><h2>{guide.name} · {guide.title}</h2><span>{guide.subtitle}</span></div>
        <dl>
          <div><dt>Source</dt><dd>{guide.source}</dd></div>
          <div><dt>MVP</dt><dd>{guide.cases} cases</dd></div>
          <div><dt>Player action</dt><dd>{guide.playerAction}</dd></div>
          <div><dt>Checkpoint</dt><dd>{guide.checkpoint}</dd></div>
        </dl>
      </section>

      <section className="dataset-transform-section">
        <header><GitBranch /><div><p>RAW → CASE → TREE → ARENA</p><h3>数据如何变成一棵可玩的树</h3></div></header>
        <div className="dataset-transform-pipeline">
          {guide.pipeline.map((step, index) => (
            <div key={step.title}>
              <span>{index + 1}</span><b>{step.title}</b><p>{step.detail}</p>
              {index < guide.pipeline.length - 1 && <ArrowRight />}
            </div>
          ))}
        </div>
      </section>

      <section className="dataset-model-contract">
        <header><ShieldCheck /><div><p>MODEL ACTION CONTRACT</p><h3>模型能问什么、做什么，以及数据中没有时如何处理</h3></div></header>
        <div>
          <article><span>01</span><b>只从当前候选库选择</b><p>每轮都把疾病库和 action_id 库完整交给模型；依赖未满足、已使用条目不可选择。</p></article>
          <article><span>02</span><b>本病例有记录</b><p>{guide.exampleKind === 'TEMPORAL' ? '动作进入 pending，到 available_time 后揭示真实结果。' : '命中规范条目后，环境返回该病例中已有的真实或确定性回答。'}</p></article>
          <article><span>03</span><b>库内但本例没做</b><p>{guide.exampleKind === 'TEMPORAL' ? '返回 UNOBSERVED_IN_RECORDED_EPISODE，计一次动作，但绝不生成假的阴性或检查值。' : '经典病例使用本例确定的 action space；不适用条目不会被伪装成新的检查结果。'}</p></article>
          <article><span>04</span><b>库外、重复或被锁定</b><p>该轮 REJECTED，患者状态不前进；错误回传给模型自动改选，连续 3 次无效才暂停。</p></article>
          <article><span>05</span><b>结束完全由模型判断</b><p>没有 Top-1 稳定轮数或固定早停阈值；模型可随时 final，30 次只作为硬安全上限。</p></article>
        </div>
      </section>

      <DatasetCaseWalkthrough
        caseId={guide.exampleCaseId}
        datasetName={guide.name}
        enabled={walkthroughEnabled}
        kind={guide.exampleKind}
      />

      <div className="dataset-guide-columns">
        <details className="dataset-guide-card" open>
          <summary><FileJson2 /><span><b>原始字段 → Case Tree</b><small>{guide.fields.length} 项关键映射</small></span></summary>
          <div className="dataset-field-table-wrap">
            <Table className="dataset-field-table">
              <TableHeader><TableRow><TableHead>原始字段</TableHead><TableHead>来源</TableHead><TableHead>含义</TableHead><TableHead>进入 Bench 后</TableHead></TableRow></TableHeader>
              <TableBody>
                {guide.fields.map((field) => (
                  <TableRow key={`${field.source}-${field.field}`}>
                    <TableCell><code>{field.field}</code></TableCell><TableCell>{field.source}</TableCell><TableCell>{field.meaning}</TableCell><TableCell>{field.mapsTo}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </details>

        <div className="dataset-rules-stack">
          <details className="dataset-guide-card" open>
            <summary><Stethoscope /><span><b>该数据集怎么玩</b><small>共享规则 + 数据集特有约束</small></span></summary>
            <ol className="dataset-rule-list">
              {guide.rules.map((rule, index) => <li key={rule}><span>{index + 1}</span>{rule}</li>)}
            </ol>
          </details>
          <details className="dataset-guide-card dataset-boundary-card" open>
            <summary><ShieldCheck /><span><b>真实性边界</b><small>不会被转换过程越过的边界</small></span></summary>
            <p>{guide.boundary}</p><dl><dt>受保护参考</dt><dd>{guide.truth}</dd></dl>
          </details>
        </div>
      </div>

      {guide.name === 'DDXPlus' && (
        <DdxEvidenceCatalog
          domain={domain}
          evidences={evidences}
          notice={notice}
          onDomainChange={onDomainChange}
          onQueryChange={onQueryChange}
          query={query}
        />
      )}
    </div>
  );
}

function DdxEvidenceCatalog({
  evidences,
  query,
  domain,
  notice,
  onQueryChange,
  onDomainChange,
}: {
  evidences: EvidenceDefinition[];
  query: string;
  domain: 'ALL' | 'SYMPTOM' | 'ANTECEDENT';
  notice: string;
  onQueryChange: (value: string) => void;
  onDomainChange: (value: 'ALL' | 'SYMPTOM' | 'ANTECEDENT') => void;
}) {
  const byId = useMemo(
    () => new Map(evidences.map((item) => [item.evidence_id, item])),
    [evidences],
  );
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return evidences.filter(
      (item) =>
        (domain === 'ALL' || (domain === 'ANTECEDENT') === item.is_antecedent) &&
        (!needle || item.evidence_id.toLowerCase().includes(needle) || item.question_en.toLowerCase().includes(needle) || item.semantic_role.toLowerCase().includes(needle)),
    );
  }, [domain, evidences, query]);

  return (
    <details className="dataset-guide-card ddx-evidence-catalog" open>
      <summary><Braces /><span><b>DDXPlus E_* 完整字段字典</b><small>{notice}</small></span></summary>
      <div className="evidence-dictionary-toolbar">
        <div className="relative min-w-0 flex-1"><Search /><Input aria-label="搜索 Evidence 编号或含义" onChange={(event) => onQueryChange(event.target.value)} placeholder="搜索 E_214、wheezing、symptom…" value={query} /></div>
        <select aria-label="字段类别" onChange={(event) => onDomainChange(event.target.value as typeof domain)} value={domain}>
          <option value="ALL">全部字段</option><option value="SYMPTOM">症状与表现</option><option value="ANTECEDENT">病史与风险</option>
        </select>
        <span className="evidence-result-count">显示 <b>{filtered.length}</b> / {evidences.length}</span>
      </div>
      <div className="evidence-table-shell">
        <Table className="evidence-table">
          <TableHeader><TableRow><TableHead>字段编号</TableHead><TableHead>Evidence / 问询含义</TableHead><TableHead>类别</TableHead><TableHead>数据类型</TableHead><TableHead>父字段</TableHead><TableHead>取值含义</TableHead></TableRow></TableHeader>
          <TableBody>
            {!filtered.length && <TableRow><TableCell className="evidence-empty-row" colSpan={6}>{evidences.length ? '没有匹配字段。' : notice}</TableCell></TableRow>}
            {filtered.map((item) => (
              <TableRow key={item.evidence_id}>
                <TableCell><code>{item.evidence_id}</code></TableCell>
                <TableCell><b>{item.question_en}</b><small>{humanizeRole(item.semantic_role)}</small></TableCell>
                <TableCell><span className="evidence-domain">{item.is_antecedent ? <History /> : <CircleDot />}{item.is_antecedent ? '病史' : '症状'}</span></TableCell>
                <TableCell>{dataTypeLabel(item.data_type)}</TableCell>
                <TableCell>{item.parent_evidence_id ? <><code>{item.parent_evidence_id}</code><small>{byId.get(item.parent_evidence_id)?.question_en ?? '—'}</small></> : '根字段'}</TableCell>
                <TableCell><ValueMeanings item={item} /></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </details>
  );
}

function ValueMeanings({ item }: { item: EvidenceDefinition }) {
  const labels = item.possible_values.map((value) => {
    const meaning = item.value_meanings[String(value)];
    if (meaning !== null && typeof meaning === 'object' && 'en' in meaning && typeof meaning.en === 'string') return `${String(value)} = ${meaning.en}`;
    return String(value);
  });
  if (!labels.length) return <span className="text-slate-400">是 / 否</span>;
  return <details className="evidence-values"><summary>{labels.length} 个可选值</summary><div>{labels.map((label) => <span key={label}>{label}</span>)}</div></details>;
}

function dataTypeLabel(value: EvidenceDefinition['data_type']) {
  if (value === 'binary') return '二元';
  if (value === 'categorical') return '单值';
  return '多选';
}

function humanizeRole(value: string) {
  return value.toLowerCase().replaceAll('_', ' ');
}
