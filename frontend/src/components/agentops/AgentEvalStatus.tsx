import React, { useState, useEffect } from "react";

interface AgentEvalStatusProps {
  agentId: string;
}

interface EvalResult {
  passed: number;
  failed: number;
  total: number;
  results?: Array<{ case_id: string; passed: boolean }>;
}

export const AgentEvalStatus: React.FC<AgentEvalStatusProps> = ({ agentId }) => {
  const [status, setStatus] = useState<EvalResult | null>(null);

  useEffect(() => {
    fetch(`/api/agent-ops/agent-eval/${agentId}`)
      .then((r) => r.json())
      .then((data) => {
        if (data.ok) {
          setStatus(data.data);
        }
      });
  }, [agentId]);

  if (!status) {
    return (
      <section className="agentops-eval">
        <h3>Eval 状态</h3>
        <p className="empty">加载中...</p>
      </section>
    );
  }

  return (
    <section className="agentops-eval">
      <h3>Eval 状态</h3>
      <div className="eval-summary">
        <span className="eval-passed">通过: {status.passed}</span>
        <span className="eval-failed">失败: {status.failed}</span>
        <span className="eval-total">总计: {status.total}</span>
      </div>
      {status.results && (
        <ul className="eval-list">
          {status.results.map((r, idx) => (
            <li key={idx} className={r.passed ? "pass" : "fail"}>
              {r.case_id}: {r.passed ? "通过" : "失败"}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
};
