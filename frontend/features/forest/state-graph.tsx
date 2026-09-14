import type { Graph } from '@/features/arena/types';

export function StateGraph({ graph }: { graph: Graph | null }) {
  if (!graph || !graph.nodes.length)
    return (
      <div className="grid min-h-56 place-items-center border border-dashed border-slate-300 bg-slate-50 text-sm text-slate-400">
        No completed trajectory data yet
      </div>
    );
  return (
    <div className="overflow-x-auto border border-slate-200 bg-slate-50 p-4">
      <div className="flex min-w-max items-center gap-3">
        {graph.nodes.slice(0, 8).map((node, index) => (
          <div className="flex items-center gap-3" key={node.state_hash}>
            <div className="w-36 border border-slate-300 bg-white p-3 shadow-sm">
              <p className="font-mono text-xs font-semibold">
                S · {node.state_hash.slice(0, 6)}
              </p>
              <p className="mt-1 text-xs text-slate-500">
                {node.revealed_evidence_ids.length} observations
              </p>
              <p className="text-xs text-teal-700">support {node.support}</p>
            </div>
            {index < graph.nodes.length - 1 && (
              <span className="font-mono text-xs text-slate-400">→</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
