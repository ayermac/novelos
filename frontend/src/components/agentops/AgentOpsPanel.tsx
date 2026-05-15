import React, { useState, useEffect } from "react";
import { AgentRoleCard } from "./AgentRoleCard";
import { AgentTraceView } from "./AgentTraceView";
import { AgentMemoryPanel } from "./AgentMemoryPanel";
import { AgentEvalStatus } from "./AgentEvalStatus";
import "./AgentOpsPanel.css";

interface AgentOpsPanelProps {
  projectId: string;
}

interface RoleProfile {
  agent_id: string;
  display_name: string;
  mission: string;
  default_capability_packs: string[];
  eval_dimensions: string[];
}

export const AgentOpsPanel: React.FC<AgentOpsPanelProps> = ({ projectId }) => {
  const [profiles, setProfiles] = useState<RoleProfile[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/agent-ops/role-profiles")
      .then((r) => r.json())
      .then((data) => {
        if (data.ok) {
          setProfiles(data.data?.profiles || []);
        }
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className="agentops-loading">加载 Agent 能力信息...</div>;
  }

  return (
    <div className="agentops-panel">
      <header className="agentops-header">
        <h2>Agent 能力诊断</h2>
        <p>查看每个 Agent 的角色目标、启用能力和最近运行状态</p>
      </header>

      <section className="agentops-roles">
        <h3>角色目标</h3>
        <div className="agentops-role-grid">
          {profiles.map((profile) => (
            <AgentRoleCard
              key={profile.agent_id}
              profile={profile}
              isSelected={selectedAgent === profile.agent_id}
              onClick={() => setSelectedAgent(profile.agent_id)}
            />
          ))}
        </div>
      </section>

      {selectedAgent && (
        <>
          <AgentTraceView projectId={projectId} agentId={selectedAgent} />
          <AgentMemoryPanel projectId={projectId} agentId={selectedAgent} />
          <AgentEvalStatus agentId={selectedAgent} />
        </>
      )}
    </div>
  );
};
