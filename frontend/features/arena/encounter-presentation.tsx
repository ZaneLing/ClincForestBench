'use client';

import { API_BASE } from '@/lib/api';

export const categories: Record<string, string> = {
  Laboratory: '检验科',
  Endocrinology: '内分泌',
  Obstetrics: '产科',
  Microbiology: '微生物',
  Immunology: '免疫',
  Hematology: '血液',
  Toxicology: '毒理',
  Oncology: '肿瘤',
  Genetics: '遗传',
  Imaging: '影像',
  'Nuclear medicine': '核医学',
  Cardiology: '心血管',
  Respiratory: '呼吸',
  Endoscopy: '内镜',
  Neurology: '神经',
  Sampling: '穿刺取样',
  Pathology: '病理',
  Gynecology: '妇科',
  'Reproductive medicine': '生殖医学',
  Urology: '泌尿',
  Ophthalmology: '眼科',
  ENT: '耳鼻喉',
  Dermatology: '皮肤',
  'Physical examination': '体格检查',
  Records: '既往记录',
  Presentation: '就诊信息',
  Symptoms: '症状',
  'Systems review': '系统回顾',
  'Mental health': '心理健康',
  Lifestyle: '生活方式',
  History: '病史',
  'Medication and allergy': '用药与过敏',
  'Family history': '家族史',
  Exposure: '暴露史',
  'Reproductive history': '生殖史',
  Pediatrics: '儿科',
  Prevention: '预防',
  'Social context': '社会情况',
  Preferences: '意愿',
  Workflow: '工作流',
  'Source catalog': '源数据扩展目录',
};
const fieldNames: Record<string, [string, string]> = {
  age: ['Age', '年龄'],
  age_range: ['Age range', '年龄范围'],
  sex: ['Sex', '性别'],
  gender: ['Gender', '性别'],
  occupation: ['Occupation', '职业'],
  question: ['Presentation', '首诊描述'],
  answer: ['Answer', '回答'],
  components: ['Components', '检查分项'],
  name: ['Name', '名称'],
  label: ['Item', '项目'],
  value: ['Value', '结果'],
  number_value: ['Value', '数值'],
  unit: ['Unit', '单位'],
  units: ['Unit', '单位'],
  text: ['Result', '结果'],
  flag: ['Flag', '标记'],
  finding: ['Finding', '所见'],
  impression: ['Impression', '报告结论'],
  narrative_text: ['Record', '记录'],
  patient_answer: ['Answer', '回答'],
  caption: ['Description', '说明'],
  status: ['Evidence status', '证据状态'],
  note: ['Note', '备注'],
  report: ['Report', '报告'],
  heart_rate: ['Heart rate', '心率'],
  respiratory_rate: ['Respiratory rate', '呼吸频率'],
  sbp: ['Systolic pressure', '收缩压'],
  dbp: ['Diastolic pressure', '舒张压'],
  spo2: ['SpO₂', '血氧饱和度'],
  temperature_c: ['Temperature (°C)', '体温（℃）'],
  temperature_f: ['Temperature (°F)', '体温（℉）'],
};
export const statuses: Record<string, [string, string]> = {
  ACTIVE: ['In progress', '进行中'],
  COMPLETED: ['Completed', '已完成'],
  TERMINATED_MISSING_RESULT: [
    'Case ended: no recorded answer or result',
    '病例已结束：没有答案或检查结果',
  ],
  PRESENT: ['Present', '存在'],
  ABSENT: ['Absent', '不存在'],
  DEFAULT: ['Dataset default', '数据集默认值'],
  NOT_APPLICABLE: ['Not applicable', '不适用'],
  VALUE: ['Recorded value', '已记录结果'],
  M: ['Male', '男'],
  F: ['Female', '女'],
  unknown: ['Not recorded', '未记载'],
};

export function ResultValue({
  value,
  chinese,
  caseId,
}: {
  value: unknown;
  chinese: boolean;
  caseId: string;
}) {
  if (value == null || value === '')
    return (
      <span className="enc-muted">{chinese ? '未记载' : 'Not recorded'}</span>
    );
  if (Array.isArray(value))
    return (
      <div className="enc-values">
        {value.map((v, i) => (
          <ResultValue key={i} value={v} chinese={chinese} caseId={caseId} />
        ))}
      </div>
    );
  if (typeof value === 'object') {
    const data = value as Record<string, unknown>;
    return (
      <dl className="enc-result">
        {Object.entries(data)
          .filter(
            ([key]) =>
              ![
                'source_path',
                'source_sentence_index',
                'source_patient_turn',
                'time_is_sequence_proxy',
                'specimen_id',
                'media_type',
                'panel_abnormal',
              ].includes(key),
          )
          .map(([key, val]) =>
            key === 'media_asset' ? (
              <div key={key}>
                <a
                  target="_blank"
                  rel="noreferrer"
                  href={`${API_BASE}/temporal/media/${encodeURIComponent(caseId)}/${encodeURIComponent(typeof val === 'string' ? val : '')}`}
                >
                  {chinese ? '打开原始报告图像' : 'Open original report image'}
                </a>
              </div>
            ) : (
              <div key={key}>
                <dt>
                  {fieldNames[key]?.[chinese ? 1 : 0] ??
                    key.replaceAll('_', ' ')}
                </dt>
                <dd>
                  <ResultValue value={val} chinese={chinese} caseId={caseId} />
                </dd>
              </div>
            ),
          )}
      </dl>
    );
  }
  const text =
    typeof value === 'string' ||
    typeof value === 'number' ||
    typeof value === 'boolean'
      ? `${value}`
      : '';
  return <span>{statuses[text]?.[chinese ? 1 : 0] ?? text}</span>;
}
