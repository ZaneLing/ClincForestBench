'use client';

import { useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import { useLanguage } from '@/features/i18n/language-context';
import type {
  EncounterForestData,
  EncounterForestNode,
} from './encounter-forest-graph';

export type ForestTrace = {
  id: string;
  label: string;
  encounterId?: string;
  status?: string;
  nodes: EncounterForestNode[];
};
type SourceTrace = {
  evidence_ids: string[];
  diagnoses?: string[];
  status?: string;
};
type Projection = { source_trajectories: SourceTrace[] };

export function forestStatistics(forest: EncounterForestData | null) {
  const parents = new Set(forest?.edges.map((edge) => edge.source));
  return {
    nodes: forest?.nodes.length ?? 0,
    edges: forest?.edges.length ?? 0,
    sessions: forest?.session_count ?? 0,
    endpoints:
      forest?.nodes.filter((node) => !parents.has(node.id)).length ?? 0,
  };
}

export function forestPaths(
  forest: EncounterForestData,
): EncounterForestNode[][] {
  const byId = new Map(forest.nodes.map((node) => [node.id, node]));
  const incoming = new Set(forest.edges.map((edge) => edge.target));
  const children = new Map<string, string[]>();
  forest.edges.forEach((edge) =>
    children.set(edge.source, [
      ...(children.get(edge.source) ?? []),
      edge.target,
    ]),
  );
  const paths: EncounterForestNode[][] = [];
  function walk(node: EncounterForestNode, path: EncounterForestNode[]) {
    if (path.some((row) => row.id === node.id) || paths.length >= 1000) return;
    const next = [...path, node];
    const descendants = (children.get(node.id) ?? [])
      .map((id) => byId.get(id))
      .filter((row): row is EncounterForestNode => Boolean(row));
    if (!descendants.length) paths.push(next);
    else descendants.forEach((child) => walk(child, next));
  }
  forest.nodes
    .filter((node) => !incoming.has(node.id))
    .forEach((node) => walk(node, []));
  return paths;
}

export function useForest(caseId: string, simulation = true) {
  const { locale, isChinese: zh } = useLanguage();
  const [result, setResult] = useState<{
    key: string;
    forest: EncounterForestData;
  } | null>(null);
  const [projection, setProjection] = useState<{
    key: string;
    data: Projection;
  } | null>(null);
  const [failure, setFailure] = useState<{
    key: string;
    message: string;
  } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const key = `${caseId}:${simulation}:${locale}:${attempt}`;
  useEffect(() => {
    const controller = new AbortController();
    const query = new URLSearchParams({ simulation: String(simulation) });
    if (caseId) query.set('case_id', caseId);
    api<EncounterForestData>(`/research/encounter-forest?${query}`, {
      signal: controller.signal,
    })
      .then((forest) => {
        setResult({ key, forest });
      })
      .catch((e) => {
        if (!controller.signal.aborted)
          setFailure({
            key,
            message: e instanceof Error ? e.message : 'Unable to load forest',
          });
      });
    // These two endpoints traverse the same encounter list in source order.
    // Accept a visit mapping only when the entire recorded evidence path matches.
    if (simulation && caseId.startsWith('DDX_')) {
      api<Projection>(
        `/research/classic-simulation-forest/cases/${encodeURIComponent(caseId)}`,
        { signal: controller.signal },
      )
        .then((data) => setProjection({ key, data }))
        .catch(() => {
          /* Aggregate paths remain available without the optional projection. */
        });
    }
    return () => controller.abort();
  }, [caseId, simulation, locale, key]);
  const forest = result?.key === key ? result.forest : null;
  const source = projection?.key === key ? projection.data : null;
  const traces = useMemo<ForestTrace[]>(() => {
    if (!forest) return [];
    const paths = forestPaths(forest);
    const visits = forest.demo_visits ?? [];
    if (source?.source_trajectories.length === visits.length && visits.length) {
      const mapped = source.source_trajectories.map((trace, index) => {
        const candidates = paths.filter((path) => {
          const evidence = path
            .filter((node) => node.event_type === 'ACTION')
            .flatMap(
              (node) =>
                node.example?.records?.map((record) => record.source_id) ?? [],
            );
          return (
            JSON.stringify(evidence) === JSON.stringify(trace.evidence_ids) &&
            path.some(
              (node) =>
                JSON.stringify(node.example?.diagnoses) ===
                JSON.stringify(trace.diagnoses),
            )
          );
        });
        return {
          id: String(index + 1),
          label: `visit ${String(index + 1).padStart(2, '0')}`,
          encounterId: visits[index].encounter_id,
          status: trace.status,
          nodes: candidates.length === 1 ? candidates[0] : [],
        };
      });
      if (mapped.every((trace) => trace.nodes.length)) return mapped;
    }
    return paths.map((nodes, index) => ({
      id: String(index + 1),
      label: `${zh ? '聚合路径' : 'Aggregate path'} ${String(index + 1).padStart(2, '0')}`,
      nodes,
    }));
  }, [forest, source, zh]);
  const stats = useMemo(() => forestStatistics(forest), [forest]);
  const error = failure?.key === key ? failure.message : '';
  return {
    forest,
    traces,
    stats,
    error,
    busy: !forest && !error,
    retry: () => setAttempt((value) => value + 1),
  };
}
