import React, { useState, useEffect } from "react";
import { useAppDialog } from "../AppDialogContext";

interface AgentMemoryPanelProps {
  projectId: string;
  agentId: string;
}

interface MemoryItem {
  id: number;
  memory_type: string;
  key: string;
  value: unknown;
  confidence: number;
  enabled: boolean;
}

export const AgentMemoryPanel: React.FC<AgentMemoryPanelProps> = ({
  projectId,
  agentId,
}) => {
  const [items, setItems] = useState<MemoryItem[]>([]);
  const dialog = useAppDialog();

  const load = React.useCallback(() => {
    fetch(`/api/agent-memory/${projectId}?agent_id=${agentId}`)
      .then((r) => r.json())
      .then((data) => {
        if (data.ok) {
          setItems(data.data?.items || []);
        }
      });
  }, [projectId, agentId]);

  useEffect(() => {
    load();
  }, [load]);

  const toggle = (id: number, enabled: boolean) => {
    fetch(`/api/agent-memory/${id}/${enabled ? "disable" : "enable"}`, {
      method: "PATCH",
    }).then(() => load());
  };

  const remove = async (id: number) => {
    const ok = await dialog.confirm({
      title: "删除 Agent 记忆",
      message: "确定删除这条记忆？删除后不会再注入该 Agent 的上下文。",
      confirmLabel: "删除",
      cancelLabel: "取消",
      tone: "danger",
    });
    if (!ok) return;
    fetch(`/api/agent-memory/${id}`, { method: "DELETE" }).then(() => load());
  };

  return (
    <section className="agentops-memory">
      <h3>Agent Memory</h3>
      {items.length === 0 ? (
        <p className="empty">暂无记忆记录</p>
      ) : (
        <ul className="memory-list">
          {items.map((item) => (
            <li key={item.id} className={`memory-item ${item.enabled ? "" : "disabled"}`}>
              <div className="memory-meta">
                <span className="memory-type">{item.memory_type}</span>
                <span className="memory-key">{item.key}</span>
                <span className="memory-confidence">
                  置信度: {item.confidence}
                </span>
              </div>
              <div className="memory-value">
                {JSON.stringify(item.value)}
              </div>
              <div className="memory-actions">
                <button onClick={() => toggle(item.id, item.enabled)}>
                  {item.enabled ? "禁用" : "启用"}
                </button>
                <button onClick={() => remove(item.id)}>删除</button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
};
