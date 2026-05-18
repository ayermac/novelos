import { useState, useEffect } from 'react'
import { api } from '../lib/api'
import { AgentOpsPanel } from '../components/agentops/AgentOpsPanel'
import { FormField, TextInput } from '../components/ui'

export default function AgentOps() {
  const [projectId, setProjectId] = useState('')
  const [health, setHealth] = useState<{ ok: boolean } | null>(null)

  useEffect(() => {
    api('/health').then((r) => setHealth({ ok: r.ok })).catch(() => setHealth({ ok: false }))
  }, [])

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">Agent Ops</h1>
      <div className="mb-4 flex gap-2 items-center">
        <FormField label="项目 ID" helper="留空时默认查看 demo 项目">
          <TextInput
            placeholder="输入 projectId"
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
          />
        </FormField>
        {health && (
          <span className={`text-sm ${health.ok ? 'text-green-600' : 'text-red-600'}`}>
            {health.ok ? 'API 在线' : 'API 离线'}
          </span>
        )}
      </div>
      <AgentOpsPanel projectId={projectId || 'demo'} />
    </div>
  )
}
