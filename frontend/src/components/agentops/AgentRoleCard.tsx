import React from "react";

interface AgentRoleCardProps {
  profile: {
    agent_id: string;
    display_name: string;
    mission: string;
    default_capability_packs: string[];
    eval_dimensions: string[];
  };
  isSelected: boolean;
  onClick: () => void;
}

export const AgentRoleCard: React.FC<AgentRoleCardProps> = ({
  profile,
  isSelected,
  onClick,
}) => {
  return (
    <button
      type="button"
      className={`agent-role-card ${isSelected ? "selected" : ""}`}
      onClick={onClick}
      aria-pressed={isSelected}
    >
      <div className="role-card-header">
        <h4>{profile.display_name}</h4>
        <span className="role-id">{profile.agent_id}</span>
      </div>
      <p className="role-mission">{profile.mission}</p>
      <div className="role-packs">
        <strong>能力包:</strong>{" "}
        {profile.default_capability_packs.length > 0
          ? profile.default_capability_packs.join(", ")
          : "无"}
      </div>
      <div className="role-dims">
        <strong>评测维度:</strong>{" "}
        {profile.eval_dimensions.join(", ")}
      </div>
    </button>
  );
};
