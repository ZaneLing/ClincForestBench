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

type DatasetName = 'DDXPlus' | 'Synthea' | 'MedAgentBench';

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
  },
];

export function EvidenceDictionary() {
  const [evidences, setEvidences] = useState<EvidenceDefinition[]>([]);
  const [query, setQuery] = useState('');
  const [domain, setDomain] = useState<'ALL' | 'SYMPTOM' | 'ANTECEDENT'>('ALL');
  const [notice, setNotice] = useState('正在读取 DDXPlus Evidence 字典…');

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
        <Badge><ShieldCheck /> 3 DATASET CONTRACTS</Badge>
      </header>

      <Tabs className="dataset-guide-tabs" defaultValue="DDXPlus">
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
}: {
  guide: DatasetGuide;
  evidences: EvidenceDefinition[];
  query: string;
  domain: 'ALL' | 'SYMPTOM' | 'ANTECEDENT';
  notice: string;
  onQueryChange: (value: string) => void;
  onDomainChange: (value: 'ALL' | 'SYMPTOM' | 'ANTECEDENT') => void;
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
