'use client';

import { useMemo, useState } from 'react';
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react';
import { Activity, CircleDot, UserRound } from 'lucide-react';
import type { ObservationState } from './types';

export type PatientPathStep = {
  evidence_id: string;
  evidence: string;
  answer: string;
  status: string;
  domain: string;
  state_hash: string;
};

type PathNodeData = {
  kind: 'patient' | 'state';
  step: number;
  title: string;
  question: string;
  answer: string;
  status: string;
  evidenceId?: string;
  stateHash?: string;
};

type PatientFlowNode = Node<PathNodeData, 'patientPath'>;
const nodeTypes = { patientPath: PatientPathNode };

export function PatientPathTree({
  state,
  path,
  beliefSubmitted,
}: {
  state: ObservationState;
  path: PatientPathStep[];
  beliefSubmitted: boolean;
}) {
  const graph = useMemo(() => buildPatientPath(state, path), [path, state]);
  const [selectedId, setSelectedId] = useState(
    graph.nodes.at(-1)?.id ?? 'patient',
  );
  const selected =
    graph.nodes.find((node) => node.id === selectedId)?.data ??
    graph.nodes.at(-1)?.data;

  return (
    <div className="patient-path-tree-shell">
      <div className="patient-tree-summary">
        <span>
          <b>{state.dataset_name}</b> dataset
        </span>
        {state.demographics.age > 0 && (
          <span>
            <b>{state.demographics.age}</b> years
          </span>
        )}
        <span>
          <b>{path.length}</b> actions
        </span>
      </div>

      {selected && (
        <div className="patient-tree-detail" aria-live="polite">
          <span className={`patient-tree-detail-mark ${statusTone(selected)}`}>
            {selected.kind === 'patient' ? <UserRound /> : `S${selected.step}`}
          </span>
          <div>
            <small>{selected.title}</small>
            <b>{selected.question}</b>
            <em>{selected.answer}</em>
          </div>
        </div>
      )}

      <div className="patient-path-canvas">
        <ReactFlow
          edges={graph.edges}
          fitView
          fitViewOptions={{ padding: 0.22, maxZoom: 1.15 }}
          maxZoom={2.3}
          minZoom={0.2}
          nodes={graph.nodes}
          nodesConnectable={false}
          nodesDraggable={false}
          nodeTypes={nodeTypes}
          onNodeClick={(_, node) => setSelectedId(node.id)}
          panOnDrag
          panOnScroll={false}
          proOptions={{ hideAttribution: true }}
          zoomOnScroll
        >
          <Background
            color="#bae6fd"
            gap={24}
            size={1}
            variant={BackgroundVariant.Dots}
          />
          <Controls showInteractive={false} />
        </ReactFlow>
        <span
          className={`patient-tree-checkpoint ${beliefSubmitted ? 'is-ready' : 'is-waiting'}`}
        >
          {beliefSubmitted
            ? `S${state.question_count} judgment saved`
            : `S${state.question_count} judgment required`}
        </span>
      </div>
    </div>
  );
}

function buildPatientPath(
  state: ObservationState,
  path: PatientPathStep[],
): { nodes: PatientFlowNode[]; edges: Edge[] } {
  const entries: PathNodeData[] = [
    {
      kind: 'patient',
      step: -1,
      title: 'Patient',
      question: `Case ${state.case_id}`,
      answer:
        state.demographics.age > 0
          ? `${state.demographics.age} years · ${state.demographics.sex}`
          : `${state.dataset_name} · ${state.case_type}`,
      status: 'PATIENT',
    },
    {
      kind: 'state',
      step: 0,
      title:
        state.case_type === 'WORKFLOW_FOREST'
          ? 'Workflow task'
          : 'Initial presentation',
      question: state.initial_evidence_question,
      answer: state.initial_evidence_answer,
      status:
        state.revealed_evidences.find(
          (item) => item.evidence_id === state.initial_evidence_id,
        )?.status ?? 'PRESENT',
      evidenceId: state.initial_evidence_id,
    },
    ...path.map<PathNodeData>((item, index) => ({
      kind: 'state',
      step: index + 1,
      title: pathTitle(item.domain),
      question: item.evidence,
      answer: item.answer,
      status: item.status,
      evidenceId: item.evidence_id,
      stateHash: item.state_hash,
    })),
  ];
  const nodes: PatientFlowNode[] = entries.map((entry, index) => ({
    id: index === 0 ? 'patient' : `state-${entry.step}`,
    type: 'patientPath',
    position: { x: 118 + (index % 2 === 0 ? -18 : 18), y: index * 100 },
    data: entry,
  }));
  const edges: Edge[] = nodes.slice(1).map((node, index) => ({
    id: `patient-path-${index}`,
    source: nodes[index].id,
    target: node.id,
    type: 'smoothstep',
    animated: index === nodes.length - 2,
    markerEnd: {
      type: MarkerType.ArrowClosed,
      color: pathColor(node.data.status),
      width: 12,
    },
    style: { stroke: pathColor(node.data.status), strokeWidth: 2 },
  }));
  return { nodes, edges };
}

function pathTitle(domain: string) {
  const labels: Record<string, string> = {
    ANTECEDENT: 'History finding',
    SYMPTOM: 'Symptom finding',
    OBSERVATION: 'Observation result',
    PROCEDURE: 'Recorded procedure',
    MEDICATION: 'Medication record',
    PATIENT: 'Patient lookup',
    WORKFLOW: 'Workflow decision',
    SERVICEREQUEST: 'Service request',
    MEDICATIONREQUEST: 'Medication request',
  };
  return labels[domain] ?? domain.replaceAll('_', ' ');
}

function PatientPathNode({ data, selected }: NodeProps<PatientFlowNode>) {
  return (
    <div
      className={`patient-path-node ${statusTone(data)} ${selected ? 'is-selected' : ''}`}
      title={`${data.title}\n${data.question}\n${data.answer}`}
    >
      <Handle position={Position.Top} type="target" />
      <span>
        {data.kind === 'patient' ? (
          <UserRound />
        ) : data.status === 'PRESENT' || data.status === 'VALUE' ? (
          <Activity />
        ) : (
          <CircleDot />
        )}
      </span>
      <small>{data.kind === 'patient' ? 'P' : `S${data.step}`}</small>
      <Handle position={Position.Bottom} type="source" />
      <span className="patient-path-tooltip">
        <b>{data.question}</b>
        <em>{data.answer}</em>
      </span>
    </div>
  );
}

function statusTone(data: Pick<PathNodeData, 'kind' | 'status'>) {
  if (data.kind === 'patient') return 'is-patient';
  if (data.status === 'PRESENT' || data.status === 'VALUE')
    return 'is-positive';
  if (data.status === 'ABSENT') return 'is-negative';
  return 'is-neutral';
}

function pathColor(status: string) {
  if (status === 'PRESENT' || status === 'VALUE') return '#0891b2';
  if (status === 'ABSENT') return '#64748b';
  return '#d97706';
}
