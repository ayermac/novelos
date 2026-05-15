import React, { useState, useEffect } from "react";

interface AgentTraceViewProps {
  projectId: string;
  agentId: string;
}

interface AutonomyDecision {
  decision?: string;
}

interface SelfCheck {
  passed?: boolean;
}

interface TraceItem {
  stage: string;
  created_at: string;
  input_summary?: string;
  autonomy_decision?: AutonomyDecision;
  capability_packs?: string[];
  self_check?: SelfCheck;
  repair_attempts?: Array<Record<string, unknown>>;
}

export const AgentTraceView: React.FC<AgentTraceViewProps> = ({
  projectId,
  agentId,
}) => {
  const [traces, setTraces] = useState<TraceItem[]>([]);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  useEffect(() => {
    const params = new URLSearchParams({ project_id: projectId, agent_id: agentId })
    fetch(`/api/agent-ops/agent-traces?${params.toString()}`)
      .then((r) => r.json())
      .then((data) => {
        if (data.ok) {
          setTraces(data.data?.traces || []);
        }
      });
  }, [projectId, agentId]);

  if (traces.length === 0) {
    return (
      <section className="agentops-traces">
        <h3>决策 Trace</h3>
        <p className="empty">暂无 {agentId} 的运行记录</p>
      </section>
    );
  }

  return (
    <section className="agentops-traces">
      <h3>决策 Trace</h3>
      {traces.map((trace, idx) => (
        <div key={idx} className="trace-item">
          <button
            type="button"
            className="trace-summary"
            onClick={() => {
              const next = new Set(expanded);
              if (next.has(idx)) next.delete(idx);
              else next.add(idx);
              setExpanded(next);
            }}
            aria-expanded={expanded.has(idx)}
          >
            <span className="trace-stage">{trace.stage}</span>
            <span className="trace-decision">
              {trace.autonomy_decision?.decision || "continue"}
            </span>
            <span className="trace-time">{trace.created_at}</span>
          </button>
          {expanded.has(idx) && (
            <div className="trace-detail">
              {trace.input_summary && (
                <p>
                  <strong>输入摘要:</strong> {trace.input_summary}
                </p>
              )}
              {trace.capability_packs && trace.capability_packs.length > 0 && (
                <p>
                  <strong>能力包:</strong> {trace.capability_packs.join(", ")}
                </p>
              )}
              {trace.self_check && (
                <p>
                  <strong>自检:</strong>{" "}
                  {trace.self_check.passed ? "通过" : "未通过"}
                </p>
              )}
              {trace.repair_attempts && trace.repair_attempts.length > 0 && (
                <p>
                  <strong>修复尝试:</strong> {trace.repair_attempts.length} 次
                </p>
              )}
            </div>
          )}
        </div>
      ))}
    </section>
  );
};
