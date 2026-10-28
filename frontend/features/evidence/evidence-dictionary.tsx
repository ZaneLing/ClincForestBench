'use client';

import { useEffect, useMemo, useState } from 'react';
import { Database, GitBranch, Search, ShieldCheck } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { api } from '@/lib/api';
import { useLanguage } from '@/features/i18n/language-context';
import type { CaseSummary } from '@/features/arena/types';
import { DatasetCaseWalkthrough } from './dataset-case-walkthrough';

type Evidence = {
  evidence_id: string;
  question_en: string;
  data_type: string;
  parent_evidence_id: string | null;
};

const SOURCES: Record<string, string> = {
  DDXPlus: 'Patient rows + evidence and condition dictionaries',
  Synthea: 'Encounter-linked observations, procedures and medications',
  MedAgentBench: 'Official task instructions + FHIR function definitions',
  'MC-MED': 'Visits, laboratory results and radiology reports',
  MIMIC: 'Admissions + linked laboratory, Note, ECG and ED records',
  'eICU-CRD': 'ICU encounter records and early assessment findings',
  'PMC Case Reports': 'Published patient case narratives',
  'NEJM CPC': 'CPC source records and narratives',
  MediScope: 'Source-authored consultation answers and report images',
  MedPI: 'Source doctor questions and patient answers',
  PatientSim: 'Official public demo patient profiles',
  'Meddies Persona VIE': 'Published Vietnamese patient profiles',
  MedMemoryBench: 'Published patient history and health records',
  MedDialogRubrics: 'Expert inquiry criteria matched to source facts',
};

export function EvidenceDictionary() {
  const { isChinese: zh } = useLanguage();
  const t = (en: string, cn: string) => zh ? cn : en;
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [evidences, setEvidences] = useState<Evidence[]>([]);
  const [selected, setSelected] = useState('DDXPlus');
  const [query, setQuery] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let live = true;
    void Promise.all([
      api<{ cases: CaseSummary[] }>('/cases'),
      api<{ evidences: Evidence[] }>('/catalog/evidences'),
    ]).then(([catalog, dictionary]) => {
      if (!live) return;
      setCases(catalog.cases);
      setEvidences(dictionary.evidences);
    }).catch((e: Error) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, []);

  const datasets = useMemo(() => {
    const counts = new Map<string, number>();
    cases.forEach(item => counts.set(item.dataset_name, (counts.get(item.dataset_name) ?? 0) + 1));
    return [...counts.entries()];
  }, [cases]);
  const selectedCases = cases.filter(item => item.dataset_name === selected);
  const example = selectedCases[0];
  const filtered = evidences.filter(item =>
    `${item.evidence_id} ${item.question_en}`.toLowerCase().includes(query.toLowerCase()),
  );

  return (
    <main className="evidence-page">
      <header className="evidence-header">
        <div><Database /><h1>{t('Datasets and evidence rules', '数据集与证据规则')}</h1></div>
        <Badge>{cases.length || '…'} {t('cases', '病例')} · {datasets.length || '…'} {t('datasets', '数据集')}</Badge>
      </header>
      {error && <p role="alert">{error}</p>}
      <section className="dataset-real-walkthrough">
        <header className="dataset-real-walkthrough-head">
          <ShieldCheck />
          <div>
            <h2>{t('Choose evidence in your own order', '自主选择问询与检查顺序')}</h2>
            <p>{t('All cases use source-backed evidence. A selected action immediately reveals its recorded result.', '所有病例都由源记录构建。选择动作后立即返回已记录的回答或检查结果。')}</p>
          </div>
        </header>
        <div className="dataset-real-summary">
          <div><span><small>{t('Initial information', '初始信息')}</small><b>{t('Patient details and presentation', '患者信息与首诊描述')}</b></span></div>
          <div><span><small>{t('Evidence acquisition', '证据获取')}</small><b>{t('Questions and examinations', '问询与检查')}</b></span></div>
          <div><span><small>{t('Decision', '判断')}</small><b>{t('Update and finalize a diagnosis', '更新判断并完成诊断')}</b></span></div>
          <div><GitBranch /><span><small>{t('Analysis', '分析')}</small><b>{t('Actions, diagnosis changes and branches', '动作、诊断变化与分支')}</b></span></div>
        </div>
        <ul>
          <li>{t('There is no simulated clock, waiting action or required source-record order.', '不设置模拟时钟、等待动作或源记录顺序要求。')}</li>
          <li>{t('Results are never invented. A missing result in the clinician Visit ends the case and preserves the trajectory.', '不补造结果。医生 Visit 选择缺失结果的项目时结束病例，并保留完整轨迹。')}</li>
          <li>{t('Model runs record a ranked differential after each observation and use a hard action budget.', '模型每次获取证据后记录诊断排序，并受动作预算约束。')}</li>
          <li>{t('Source dates remain provenance or clinical history; they do not unlock actions or affect state identity.', '源日期保留为来源信息或临床病史，不用于解锁动作或定义信息状态。')}</li>
          <li>{t('Reference labels remain hidden during play. Unadjudicated references retain their source quality labels.', '运行中隐藏参考答案；未经裁定的参考保留来源与质量标记。')}</li>
        </ul>
      </section>
      <section className="dataset-real-walkthrough">
        <label>
          {t('Dataset', '数据集')}{' '}
          <select value={selected} onChange={event => setSelected(event.target.value)}>
            {datasets.map(([name, count]) => <option key={name} value={name}>{name} · {count}</option>)}
          </select>
        </label>
        <h2>{selected}</h2>
        <p>{SOURCES[selected] ?? t('Source-backed clinical records', '源临床记录')}</p>
        <p>{selectedCases.length} {t('cases in the shared catalog', '个病例进入统一病例库')}</p>
        {example && <DatasetCaseWalkthrough key={example.case_id} caseId={example.case_id} datasetName={selected} enabled />}
      </section>
      <section className="dataset-real-walkthrough">
        <h2>{t('DDXPlus evidence dictionary', 'DDXPlus 证据词典')}</h2>
        <label htmlFor="evidence-search"><Search /><Input id="evidence-search" aria-label={t('Search evidence', '搜索证据')} value={query} onChange={event => setQuery(event.target.value)} placeholder={t('Evidence ID or question', '证据 ID 或问题')} /></label>
        <table>
          <thead><tr><th>ID</th><th>{t('Question', '问题')}</th><th>{t('Type', '类型')}</th><th>{t('Parent question', '父问题')}</th></tr></thead>
          <tbody>{filtered.map(item => <tr key={item.evidence_id}><td>{item.evidence_id}</td><td>{item.question_en}</td><td>{item.data_type}</td><td>{item.parent_evidence_id ?? '—'}</td></tr>)}</tbody>
        </table>
      </section>
    </main>
  );
}
