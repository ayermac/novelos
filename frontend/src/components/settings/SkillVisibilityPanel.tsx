import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { get, post, del } from '../../lib/api'

interface SkillMount {
  agent: string
  stage: string
}

interface SkillInfo {
  id: string
  name?: string
  enabled: boolean
  kind?: string
  type?: string
  version?: string | null
  package?: string
  class_name?: string
  class?: string
  description?: string
  mounted_to: SkillMount[]
  is_mounted: boolean
}

interface ValidateResult {
  ok: boolean
  errors: string[]
  warnings: string[]
}

interface MountMap {
  [agent: string]: {
    [stage: string]: string[]
  }
}

interface MatrixSkill {
  id: string
  name?: string | null
  enabled: boolean
  missing: boolean
  package?: string | null
  legacy: boolean
  kind?: string | null
}

interface MatrixStage {
  stage: string
  skill_ids: string[]
  skills: MatrixSkill[]
  warnings: { code: string; message: string }[]
}

interface MatrixAgent {
  agent: string
  stages: MatrixStage[]
}

interface AgentMatrix {
  agents: MatrixAgent[]
  unmounted_enabled_skills: MatrixSkill[]
  warnings: { code: string; message: string; skill_id?: string }[]
}

interface TestSkillResult {
  ok: boolean
  error?: string | null
  data?: {
    passed?: number
    failed?: number
    total?: number
    cases?: unknown[]
  }
}

interface TestAllResult {
  total: number
  passed: number
  failed: number
  skipped: number
  skipped_ids: string[]
  results: Record<string, TestSkillResult>
}

interface RunResult {
  skill_id: string
  result: TestSkillResult
}

interface ConfigSkill {
  id: string
  name: string
  enabled: boolean
  kind?: string | null
  package?: string | null
  legacy: boolean
  class_name?: string | null
}

interface SkillConfig {
  agents: string[]
  stages: Record<string, string[]>
  agent_skills: MountMap
  available_skills: ConfigSkill[]
  missing_skills: { id: string; agent: string; stage: string }[]
  disabled_skills: { id: string; name: string }[]
  config_path: string
  total_skills: number
  total_mounted: number
}

interface OpenClawCandidate {
  id: string
  name: string
  description: string
  source_agent?: string | null
  target_agent?: string | null
  source_path: string
  status: 'import_ready' | 'needs_adapter' | 'not_recommended' | 'invalid'
  features: Record<string, boolean>
  blockers: string[]
  error?: string | null
}

interface OpenClawReadiness {
  root: string
  root_exists: boolean
  total: number
  summary: {
    import_ready: number
    needs_adapter: number
    not_recommended: number
    invalid: number
  }
  candidates: OpenClawCandidate[]
  warnings: string[]
}

const panelStyle: CSSProperties = {
  marginBottom: 'var(--space-4)',
  padding: 'var(--space-4)',
  borderRadius: 'var(--radius-md)',
  background: 'var(--bg-secondary)',
  border: '1px solid rgba(30, 58, 95, 0.06)',
}

const sectionTitleStyle: CSSProperties = {
  fontSize: 'var(--text-sm)',
  fontWeight: 'var(--font-semibold)',
  margin: '0 0 var(--space-3) 0',
  color: 'var(--text-primary)',
}

const compactCodeStyle: CSSProperties = {
  fontSize: '12px',
  whiteSpace: 'normal',
  overflowWrap: 'anywhere',
}

function statusChipStyle(kind: 'ok' | 'warn' | 'danger' | 'muted' = 'ok'): CSSProperties {
  const palette = {
    ok: { background: 'rgba(34, 197, 94, 0.12)', color: '#166534' },
    warn: { background: '#fef3c7', color: '#92400e' },
    danger: { background: '#fee2e2', color: '#991b1b' },
    muted: { background: '#e5e7eb', color: '#6b7280' },
  }[kind]

  return {
    ...palette,
    display: 'inline-flex',
    alignItems: 'center',
    maxWidth: '100%',
    padding: '2px 8px',
    borderRadius: '4px',
    fontSize: '12px',
    fontWeight: 500,
    overflowWrap: 'anywhere',
  }
}

function matrixSkillChipStyle(skill: MatrixSkill): CSSProperties {
  if (skill.missing) return statusChipStyle('danger')
  if (!skill.enabled) return statusChipStyle('muted')
  return {
    ...statusChipStyle('ok'),
    background: 'rgba(59, 130, 246, 0.1)',
    color: '#1e40af',
  }
}

function configSkillChipStyle(skill: { missing?: boolean; enabled?: boolean; legacy?: boolean }): CSSProperties {
  if (skill.missing) return statusChipStyle('danger')
  if (skill.enabled === false) return statusChipStyle('muted')
  return {
    ...statusChipStyle('ok'),
    background: 'rgba(59, 130, 246, 0.1)',
    color: '#1e40af',
  }
}

function readinessStatusLabel(status: OpenClawCandidate['status']) {
  const labels = {
    import_ready: '可导入候选',
    needs_adapter: '需要适配',
    not_recommended: '不建议导入',
    invalid: '无效',
  }
  return labels[status]
}

function readinessStatusKind(status: OpenClawCandidate['status']): 'ok' | 'warn' | 'danger' | 'muted' {
  if (status === 'import_ready') return 'ok'
  if (status === 'needs_adapter') return 'warn'
  if (status === 'not_recommended') return 'muted'
  return 'danger'
}

export default function SkillVisibilityPanel() {
  const [skills, setSkills] = useState<SkillInfo[]>([])
  const [mounts, setMounts] = useState<MountMap>({})
  const [agentMatrix, setAgentMatrix] = useState<AgentMatrix | null>(null)
  const [skillConfig, setSkillConfig] = useState<SkillConfig | null>(null)
  const [openClawReadiness, setOpenClawReadiness] = useState<OpenClawReadiness | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [validating, setValidating] = useState(false)
  const [validateResult, setValidateResult] = useState<ValidateResult | null>(null)

  const [testingAll, setTestingAll] = useState(false)
  const [testAllResult, setTestAllResult] = useState<TestAllResult | null>(null)
  const [testAllError, setTestAllError] = useState('')
  const [testingSkill, setTestingSkill] = useState<string | null>(null)
  const [testSingleResult, setTestSingleResult] = useState<Record<string, TestSkillResult>>({})

  const [runSkillId, setRunSkillId] = useState('')
  const [runText, setRunText] = useState('')
  const [runPayload, setRunPayload] = useState('')
  const [runPayloadError, setRunPayloadError] = useState('')
  const [running, setRunning] = useState(false)
  const [runResult, setRunResult] = useState<RunResult | null>(null)

  // Mount editor state
  const [savingMount, setSavingMount] = useState(false)
  const [mountError, setMountError] = useState('')
  const [selectedAddSkill, setSelectedAddSkill] = useState<Record<string, string>>({})

  const load = async () => {
    setLoading(true)
    setError('')

    const [skillsRes, mountsRes, matrixRes, configRes, openClawRes] = await Promise.all([
      get<{ skills: SkillInfo[] }>('/skills'),
      get<MountMap>('/skills/mounts'),
      get<AgentMatrix>('/skills/agent-matrix'),
      get<SkillConfig>('/skills/config'),
      get<OpenClawReadiness>('/skills/openclaw-readiness'),
    ])

    if (skillsRes.ok && skillsRes.data) {
      setSkills(skillsRes.data.skills)
    } else {
      setError(skillsRes.error?.message || '获取 Skill 列表失败')
    }

    if (mountsRes.ok && mountsRes.data) {
      setMounts(mountsRes.data)
    }

    if (matrixRes.ok && matrixRes.data) {
      setAgentMatrix(matrixRes.data)
    }

    if (configRes.ok && configRes.data) {
      setSkillConfig(configRes.data)
    }

    if (openClawRes.ok && openClawRes.data) {
      setOpenClawReadiness(openClawRes.data)
    } else {
      setOpenClawReadiness(null)
    }

    setLoading(false)
  }

  useEffect(() => {
    load()
  }, [])

  const handleValidate = async () => {
    setValidating(true)
    setValidateResult(null)

    const res = await post<ValidateResult>('/skills/validate')
    setValidating(false)

    if (res.ok && res.data) {
      setValidateResult(res.data)
    } else {
      setValidateResult({ ok: false, errors: [res.error?.message || '验证请求失败'], warnings: [] })
    }
  }

  const handleTestAll = async () => {
    setTestingAll(true)
    setTestAllResult(null)
    setTestAllError('')

    const res = await post<TestAllResult>('/skills/test', { all: true })
    setTestingAll(false)

    if (res.ok && res.data) {
      setTestAllResult(res.data)
    } else {
      setTestAllResult({ total: 0, passed: 0, failed: 0, skipped: 0, skipped_ids: [], results: {} })
      setTestAllError(res.error?.message || '测试全部 Package Skill 失败')
    }
  }

  const handleTestSingle = async (skillId: string) => {
    setTestingSkill(skillId)

    const res = await post<{ skill_id: string; result: TestSkillResult }>('/skills/test', {
      skill_id: skillId,
    })

    setTestingSkill(null)

    if (res.ok && res.data) {
      setTestSingleResult((prev) => ({ ...prev, [skillId]: res.data!.result }))
    } else {
      setTestSingleResult((prev) => ({
        ...prev,
        [skillId]: { ok: false, error: res.error?.message || '测试失败' },
      }))
    }
  }

  const handleRun = async () => {
    if (!runSkillId) return
    setRunPayloadError('')

    const hasText = runText.trim().length > 0
    const hasPayload = runPayload.trim().length > 0
    if (!hasText && !hasPayload) {
      setRunResult({
        skill_id: runSkillId,
        result: { ok: false, error: '请输入文本或 payload' },
      })
      return
    }

    let customPayload: Record<string, unknown> | undefined
    if (hasPayload) {
      try {
        customPayload = JSON.parse(runPayload) as Record<string, unknown>
      } catch {
        setRunPayloadError('JSON 格式错误，请检查输入')
        return
      }
    }

    setRunning(true)
    setRunResult(null)

    const reqBody: { skill_id: string; text?: string; payload?: Record<string, unknown> } = {
      skill_id: runSkillId,
    }
    if (hasText) reqBody.text = runText
    if (customPayload) reqBody.payload = customPayload

    const res = await post<RunResult>('/skills/run', reqBody)

    setRunning(false)

    if (res.ok && res.data) {
      setRunResult(res.data)
    } else {
      setRunResult({
        skill_id: runSkillId,
        result: { ok: false, error: res.error?.message || '运行失败' },
      })
    }
  }

  // Mount editor handlers
  const handleMount = async (agent: string, stage: string, skillId: string) => {
    if (!skillId) return
    setSavingMount(true)
    setMountError('')

    const res = await post<{ agent: string; stage: string; skill_id: string }>('/skills/mount', {
      agent,
      stage,
      skill_id: skillId,
    })

    setSavingMount(false)

    if (res.ok && res.data) {
      setSelectedAddSkill((prev) => ({ ...prev, [`${agent}-${stage}`]: '' }))
      await load()
    } else {
      setMountError(res.error?.message || '挂载失败')
    }
  }

  const handleUnmount = async (agent: string, stage: string, skillId: string) => {
    setSavingMount(true)
    setMountError('')

    const res = await del<{ agent: string; stage: string; skill_id: string }>('/skills/mount', {
      agent,
      stage,
      skill_id: skillId,
    })

    setSavingMount(false)

    if (res.ok && res.data) {
      await load()
    } else {
      setMountError(res.error?.message || '卸载失败')
    }
  }

  const handleMove = async (agent: string, stage: string, skillId: string, direction: 'up' | 'down') => {
    const current = skillConfig?.agent_skills[agent]?.[stage] || []
    const idx = current.indexOf(skillId)
    if (idx === -1) return
    const newIdx = direction === 'up' ? idx - 1 : idx + 1
    if (newIdx < 0 || newIdx >= current.length) return

    const reordered = [...current]
    const temp = reordered[idx]
    reordered[idx] = reordered[newIdx]
    reordered[newIdx] = temp

    setSavingMount(true)
    setMountError('')

    const res = await post<{ agent: string; stage: string; skill_ids: string[] }>('/skills/reorder', {
      agent,
      stage,
      skill_ids: reordered,
    })

    setSavingMount(false)

    if (res.ok && res.data) {
      await load()
    } else {
      setMountError(res.error?.message || '排序失败')
    }
  }

  if (loading) {
    return (
      <div style={{ padding: 'var(--space-5)', textAlign: 'center', color: 'var(--text-charcoal)' }}>
        加载 Skill 信息...
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ padding: 'var(--space-5)', color: 'var(--danger)' }}>
        {error}
        <button onClick={load} className="btn btn-secondary" style={{ marginLeft: 12 }}>
          重试
        </button>
      </div>
    )
  }

  const enabledUnmounted = skills.filter((s) => s.enabled && !s.is_mounted)
  const matrixStats = agentMatrix
    ? {
        agents: agentMatrix.agents.length,
        stages: agentMatrix.agents.reduce((total, agent) => total + agent.stages.length, 0),
        mounted: agentMatrix.agents.reduce(
          (total, agent) => total + agent.stages.reduce((stageTotal, stage) => stageTotal + stage.skills.length, 0),
          0,
        ),
        missing: agentMatrix.agents.reduce(
          (total, agent) => total + agent.stages.reduce(
            (stageTotal, stage) => stageTotal + stage.skills.filter((skill) => skill.missing).length,
            0,
          ),
          0,
        ),
      }
    : null

  // Build available skills for each agent/stage from config
  const getAvailableSkillsForStage = (agent: string, stage: string) => {
    if (!skillConfig) return []
    const mountedSet = new Set(skillConfig.agent_skills[agent]?.[stage] || [])
    return skillConfig.available_skills.filter((s) => !mountedSet.has(s.id))
  }

  return (
    <div style={{ padding: 'var(--space-5)' }}>
      {/* Validate button */}
      <div style={{ marginBottom: 'var(--space-4)', display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <button onClick={handleValidate} className="btn btn-secondary" disabled={validating}>
          {validating ? '验证中...' : '验证 Skill 配置'}
        </button>
        {validateResult && (
          <span
            style={{
              fontSize: '13px',
              fontWeight: 500,
              color: validateResult.ok ? 'var(--success)' : 'var(--danger)',
            }}
          >
            {validateResult.ok ? 'Skill 配置有效' : `发现 ${validateResult.errors.length} 个错误`}
          </span>
        )}
      </div>

      {validateResult && !validateResult.ok && (
        <div
          style={{
            marginBottom: 'var(--space-4)',
            padding: '12px',
            borderRadius: '6px',
            background: '#fef2f2',
            color: '#991b1b',
            fontSize: '13px',
          }}
        >
          {validateResult.errors.map((e, i) => (
            <div key={`err-${i}`} style={{ marginBottom: 4 }}>
              {e}
            </div>
          ))}
          {validateResult.warnings.map((w, i) => (
            <div key={`warn-${i}`} style={{ color: '#92400e', marginBottom: 4 }}>
              {w}
            </div>
          ))}
        </div>
      )}

      {validateResult && validateResult.ok && validateResult.warnings.length > 0 && (
        <div
          style={{
            marginBottom: 'var(--space-4)',
            padding: '12px',
            borderRadius: '6px',
            background: '#fef3c7',
            color: '#92400e',
            fontSize: '13px',
          }}
        >
          {validateResult.warnings.map((w, i) => (
            <div key={`warn-${i}`} style={{ marginBottom: 4 }}>
              {w}
            </div>
          ))}
        </div>
      )}

      {/* Unmounted reminder */}
      {enabledUnmounted.length > 0 && (
        <div
          style={{
            marginBottom: 'var(--space-4)',
            padding: '12px',
            borderRadius: '6px',
            background: '#fef3c7',
            color: '#92400e',
            fontSize: '13px',
          }}
        >
          <strong>以下 Skill 已启用，但未挂载到工作流：</strong>
          <div style={{ marginTop: 6, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {enabledUnmounted.map((s) => (
              <span
                key={s.id}
                style={{
                  ...statusChipStyle('warn'),
                  background: '#fde68a',
                }}
              >
                {s.id}
              </span>
            ))}
          </div>
        </div>
      )}

      {agentMatrix && (
        <div style={panelStyle}>
          <div
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              justifyContent: 'space-between',
              gap: '12px',
              marginBottom: 'var(--space-3)',
              flexWrap: 'wrap',
            }}
          >
            <h4 style={{ ...sectionTitleStyle, marginBottom: 0 }}>
              Agent Skill Matrix
            </h4>
            {matrixStats && (
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                <span style={statusChipStyle('muted')}>{matrixStats.agents} agents</span>
                <span style={statusChipStyle('muted')}>{matrixStats.stages} stages</span>
                <span style={statusChipStyle(matrixStats.missing > 0 ? 'warn' : 'ok')}>
                  {matrixStats.mounted} mounted
                </span>
                {matrixStats.missing > 0 && (
                  <span style={statusChipStyle('danger')}>{matrixStats.missing} missing</span>
                )}
              </div>
            )}
          </div>
          {agentMatrix.warnings.length > 0 && (
            <div
              style={{
                marginBottom: 'var(--space-3)',
                padding: '10px 12px',
                borderRadius: '6px',
                background: '#fef3c7',
                color: '#92400e',
                fontSize: '13px',
              }}
            >
              {agentMatrix.warnings.slice(0, 4).map((warning, index) => (
                <div key={`${warning.code}-${index}`} style={{ overflowWrap: 'anywhere' }}>
                  {warning.message}
                </div>
              ))}
              {agentMatrix.warnings.length > 4 && (
                <div style={{ marginTop: 4, color: '#78350f' }}>
                  另有 {agentMatrix.warnings.length - 4} 条警告，请在 Skill 列表中继续排查。
                </div>
              )}
            </div>
          )}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 280px), 1fr))', gap: '12px' }}>
            {agentMatrix.agents.map((agent) => (
              <div
                key={agent.agent}
                style={{
                  padding: '12px',
                  borderRadius: '8px',
                  background: 'var(--paper-surface)',
                  border: '1px solid rgba(30, 58, 95, 0.06)',
                  minWidth: 0,
                }}
              >
                <div style={{ fontWeight: 600, marginBottom: 10, textTransform: 'capitalize' }}>
                  {agent.agent}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {agent.stages.map((stage) => (
                    <div
                      key={`${agent.agent}-${stage.stage}`}
                      style={{
                        display: 'grid',
                        gridTemplateColumns: 'minmax(88px, 0.35fr) minmax(0, 1fr)',
                        gap: 8,
                        alignItems: 'start',
                        minWidth: 0,
                      }}
                    >
                      <div
                        style={{
                          fontSize: '12px',
                          color: 'var(--text-secondary)',
                          fontFamily: 'monospace',
                          overflowWrap: 'anywhere',
                        }}
                      >
                        {stage.stage}
                      </div>
                      {stage.skills.length > 0 ? (
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, minWidth: 0 }}>
                          {stage.skills.map((skill) => (
                            <span
                              key={skill.id}
                              title={skill.name || skill.id}
                              style={matrixSkillChipStyle(skill)}
                            >
                              {skill.id}{skill.legacy ? ' · legacy' : ''}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>未挂载</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Mount Editor */}
      <div style={panelStyle}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', marginBottom: 'var(--space-3)' }}>
          <h4 style={{ ...sectionTitleStyle, marginBottom: 0 }}>挂载编辑器 / Mount Editor</h4>
          <button onClick={load} className="btn btn-secondary" disabled={savingMount} style={{ fontSize: '12px', padding: '4px 10px' }}>
            刷新
          </button>
        </div>

        {mountError && (
          <div
            style={{
              marginBottom: 'var(--space-3)',
              padding: '10px 12px',
              borderRadius: '6px',
              background: '#fef2f2',
              color: '#991b1b',
              fontSize: '13px',
            }}
          >
            {mountError}
            <button
              onClick={() => setMountError('')}
              style={{ marginLeft: 8, fontSize: '12px', background: 'none', border: 'none', color: '#991b1b', cursor: 'pointer', textDecoration: 'underline' }}
            >
              清除
            </button>
          </div>
        )}

        {savingMount && (
          <div style={{ marginBottom: 'var(--space-3)', fontSize: '13px', color: 'var(--text-secondary)' }}>
            保存中...
          </div>
        )}

        {/* OpenClaw / skill count explanation */}
        <div
          style={{
            marginBottom: 'var(--space-3)',
            padding: '10px 12px',
            borderRadius: '6px',
            background: '#eff6ff',
            color: '#1e40af',
            fontSize: '13px',
          }}
        >
          <strong>关于 Skill 数量</strong>
          <div style={{ marginTop: 4 }}>
            当前仅展示已被 Novelos SkillRegistry 加载的 Skill（共 {skillConfig?.total_skills ?? 0} 个）。OpenClaw legacy skill 需要导入/注册后才会出现在这里。
            {skillConfig && skillConfig.available_skills.filter((s) => !s.enabled).length > 0 && (
              <span> 另有 {skillConfig.available_skills.filter((s) => !s.enabled).length} 个已禁用 Skill。</span>
            )}
          </div>
        </div>

        {skillConfig && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 320px), 1fr))', gap: '12px' }}>
            {skillConfig.agents.map((agent) => {
              const stages = skillConfig.stages[agent] || []
              const agentMounts = skillConfig.agent_skills[agent] || {}
              return (
                <div
                  key={agent}
                  style={{
                    padding: '12px',
                    borderRadius: '8px',
                    background: 'var(--paper-surface)',
                    border: '1px solid rgba(30, 58, 95, 0.06)',
                    minWidth: 0,
                  }}
                >
                  <div style={{ fontWeight: 600, marginBottom: 10, textTransform: 'capitalize' }}>
                    {agent}
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    {stages.map((stage) => {
                      const mountedSkills = agentMounts[stage] || []
                      const available = getAvailableSkillsForStage(agent, stage)
                      const selectKey = `${agent}-${stage}`
                      return (
                        <div key={selectKey} style={{ minWidth: 0 }}>
                          <div
                            style={{
                              fontSize: '12px',
                              color: 'var(--text-secondary)',
                              fontFamily: 'monospace',
                              marginBottom: 6,
                              overflowWrap: 'anywhere',
                            }}
                          >
                            {stage}
                          </div>
                          {mountedSkills.length > 0 ? (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 8 }}>
                              {mountedSkills.map((skillId, idx) => {
                                const skillInfo = skillConfig.available_skills.find((s) => s.id === skillId)
                                const chipSkill = skillInfo
                                  ? { missing: false, enabled: skillInfo.enabled, legacy: skillInfo.legacy }
                                  : { missing: true, enabled: false, legacy: false }
                                return (
                                  <div
                                    key={skillId}
                                    style={{
                                      display: 'flex',
                                      alignItems: 'center',
                                      gap: 6,
                                      flexWrap: 'wrap',
                                      minWidth: 0,
                                    }}
                                  >
                                    <span style={configSkillChipStyle(chipSkill)}>
                                      {skillId}
                                      {chipSkill.missing && ' · missing'}
                                      {!chipSkill.missing && !chipSkill.enabled && ' · disabled'}
                                      {!chipSkill.missing && chipSkill.legacy && ' · legacy'}
                                    </span>
                                    <div style={{ display: 'flex', gap: 4 }}>
                                      <button
                                        onClick={() => handleMove(agent, stage, skillId, 'up')}
                                        disabled={savingMount || idx === 0}
                                        className="btn btn-secondary"
                                        style={{ fontSize: '11px', padding: '2px 6px' }}
                                        title="上移"
                                      >
                                        ↑
                                      </button>
                                      <button
                                        onClick={() => handleMove(agent, stage, skillId, 'down')}
                                        disabled={savingMount || idx === mountedSkills.length - 1}
                                        className="btn btn-secondary"
                                        style={{ fontSize: '11px', padding: '2px 6px' }}
                                        title="下移"
                                      >
                                        ↓
                                      </button>
                                      <button
                                        onClick={() => handleUnmount(agent, stage, skillId)}
                                        disabled={savingMount}
                                        className="btn btn-secondary"
                                        style={{ fontSize: '11px', padding: '2px 6px', color: '#991b1b' }}
                                        title="移除"
                                      >
                                        ×
                                      </button>
                                    </div>
                                  </div>
                                )
                              })}
                            </div>
                          ) : (
                            <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: 8 }}>
                              未挂载
                            </div>
                          )}
                          {available.length > 0 && (
                            <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                              <select
                                className="form-control"
                                value={selectedAddSkill[selectKey] || ''}
                                onChange={(e) => setSelectedAddSkill((prev) => ({ ...prev, [selectKey]: e.target.value }))}
                                disabled={savingMount}
                                style={{ fontSize: '12px', padding: '4px 8px', minWidth: 120, flex: 1 }}
                              >
                                <option value="">-- 选择 Skill --</option>
                                {available.map((s) => (
                                  <option key={s.id} value={s.id}>
                                    {s.id}
                                  </option>
                                ))}
                              </select>
                              <button
                                onClick={() => handleMount(agent, stage, selectedAddSkill[selectKey] || '')}
                                disabled={savingMount || !selectedAddSkill[selectKey]}
                                className="btn btn-secondary"
                                style={{ fontSize: '12px', padding: '4px 10px' }}
                              >
                                添加
                              </button>
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* OpenClaw Import Readiness */}
      {openClawReadiness && (
        <div style={panelStyle}>
          <div
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              justifyContent: 'space-between',
              gap: 12,
              flexWrap: 'wrap',
              marginBottom: 'var(--space-3)',
            }}
          >
            <div>
              <h4 style={{ ...sectionTitleStyle, marginBottom: 4 }}>
                OpenClaw Skill 导入体检
              </h4>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)', overflowWrap: 'anywhere' }}>
                只读扫描：不复制、不启用、不挂载。Root: <code style={compactCodeStyle}>{openClawReadiness.root}</code>
              </div>
            </div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
              <span style={statusChipStyle('muted')}>{openClawReadiness.total} candidates</span>
              <span style={statusChipStyle('ok')}>{openClawReadiness.summary.import_ready} 可导入</span>
              <span style={statusChipStyle('warn')}>{openClawReadiness.summary.needs_adapter} 需适配</span>
              <span style={statusChipStyle('muted')}>{openClawReadiness.summary.not_recommended} 不建议</span>
              {openClawReadiness.summary.invalid > 0 && (
                <span style={statusChipStyle('danger')}>{openClawReadiness.summary.invalid} 无效</span>
              )}
            </div>
          </div>

          {!openClawReadiness.root_exists && (
            <div
              style={{
                padding: '10px 12px',
                borderRadius: '6px',
                background: '#fef3c7',
                color: '#92400e',
                fontSize: '13px',
              }}
            >
              未找到 OpenClaw legacy workspace。当前页面仍只展示 Novelos SkillRegistry 已加载的 Skill。
            </div>
          )}

          {openClawReadiness.root_exists && openClawReadiness.candidates.length > 0 && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 280px), 1fr))', gap: '12px' }}>
              {openClawReadiness.candidates.map((candidate) => (
                <div
                  key={candidate.id}
                  style={{
                    padding: '12px',
                    borderRadius: '8px',
                    background: 'var(--paper-surface)',
                    border: '1px solid rgba(30, 58, 95, 0.06)',
                    minWidth: 0,
                  }}
                >
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap', marginBottom: 6 }}>
                    <strong style={{ fontSize: '13px', overflowWrap: 'anywhere' }}>{candidate.name}</strong>
                    <span style={statusChipStyle(readinessStatusKind(candidate.status))}>
                      {readinessStatusLabel(candidate.status)}
                    </span>
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: 6, overflowWrap: 'anywhere' }}>
                    {candidate.source_agent || 'unknown'} → {candidate.target_agent || '无直接目标'}
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: 8, overflowWrap: 'anywhere' }}>
                    <code style={compactCodeStyle}>{candidate.source_path}</code>
                  </div>
                  {candidate.blockers.length > 0 && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      {candidate.blockers.slice(0, 3).map((blocker, index) => (
                        <span key={`${candidate.id}-blocker-${index}`} style={{ fontSize: '12px', color: '#92400e', overflowWrap: 'anywhere' }}>
                          {blocker}
                        </span>
                      ))}
                      {candidate.blockers.length > 3 && (
                        <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                          另有 {candidate.blockers.length - 3} 项需检查
                        </span>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Fixtures Test Bench */}
      <div style={panelStyle}>
        <h4 style={sectionTitleStyle}>Fixtures 测试</h4>
        <div
          style={{
            marginBottom: 'var(--space-3)',
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            flexWrap: 'wrap',
          }}
        >
          <button onClick={handleTestAll} className="btn btn-secondary" disabled={testingAll}>
            {testingAll ? '测试中...' : '测试全部 Package Skill'}
          </button>
          {testAllResult && (
            <span style={{ fontSize: '13px', fontWeight: 500 }}>
              {testAllResult.failed === 0 ? (
                <span style={{ color: 'var(--success)' }}>
                  {testAllResult.passed}/{testAllResult.total} 通过
                  {testAllResult.skipped > 0 && `，${testAllResult.skipped} 个跳过`}
                </span>
              ) : (
                <span style={{ color: 'var(--danger)' }}>
                  {testAllResult.passed}/{testAllResult.total} 通过，{testAllResult.failed} 失败
                  {testAllResult.skipped > 0 && `，${testAllResult.skipped} 个跳过`}
                </span>
              )}
            </span>
          )}
        </div>

        {testAllResult && testAllResult.failed > 0 && (
          <div
            style={{
              marginBottom: 'var(--space-3)',
              padding: '12px',
              borderRadius: '6px',
              background: '#fef2f2',
              color: '#991b1b',
              fontSize: '13px',
            }}
          >
            {Object.entries(testAllResult.results)
              .filter(([, r]) => !r.ok)
              .map(([sid, r]) => (
                <div key={sid} style={{ marginBottom: 4 }}>
                  <strong>{sid}</strong>: {r.error || '未知错误'}
                </div>
              ))}
          </div>
        )}

        {testAllError && (
          <div
            style={{
              marginBottom: 'var(--space-3)',
              padding: '12px',
              borderRadius: '6px',
              background: '#fef2f2',
              color: '#991b1b',
              fontSize: '13px',
            }}
          >
            {testAllError}
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 260px), 1fr))', gap: 'var(--space-2)' }}>
          {skills.map((skill) => {
            const singleRes = testSingleResult[skill.id]
            return (
              <div
                key={`test-${skill.id}`}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 10,
                  padding: '8px 12px',
                  borderRadius: '6px',
                  background: 'var(--paper-surface)',
                  border: '1px solid rgba(30, 58, 95, 0.06)',
                  minWidth: 0,
                }}
              >
                <div style={{ fontSize: '13px', minWidth: 0 }}>
                  <code style={compactCodeStyle}>{skill.id}</code>
                  {singleRes && (
                    <span style={{ display: 'block', marginTop: 3, fontSize: '12px', overflowWrap: 'anywhere' }}>
                      {singleRes.ok ? (
                        <span style={{ color: 'var(--success)' }}>
                          {singleRes.data?.passed ?? 0}/{singleRes.data?.total ?? 0} 通过
                        </span>
                      ) : (
                        <span style={{ color: 'var(--danger)' }}>{singleRes.error || '失败'}</span>
                      )}
                    </span>
                  )}
                </div>
                {skill.package ? (
                  <button
                    onClick={() => handleTestSingle(skill.id)}
                    className="btn btn-secondary"
                    disabled={testingSkill === skill.id}
                    style={{ fontSize: '12px', padding: '4px 10px' }}
                  >
                    {testingSkill === skill.id ? '测试中...' : '测试'}
                  </button>
                ) : (
                  <span
                    style={{
                      fontSize: '12px',
                      color: 'var(--text-muted)',
                      padding: '4px 10px',
                    }}
                  >
                    无 fixtures
                  </span>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Manual Run Bench */}
      <div style={panelStyle}>
        <h4 style={sectionTitleStyle}>手动试运行</h4>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 240px), 1fr))', gap: '12px', marginBottom: '12px' }}>
          <div className="form-group">
            <label>选择 Skill</label>
            <select
              className="form-control"
              value={runSkillId}
              onChange={(e) => setRunSkillId(e.target.value)}
            >
              <option value="">-- 请选择 --</option>
              {skills.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.id}
                </option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label>输入文本</label>
            <textarea
              className="form-control"
              rows={4}
              value={runText}
              onChange={(e) => setRunText(e.target.value)}
              placeholder="输入要测试的文本..."
            />
          </div>
          <div className="form-group" style={{ gridColumn: '1 / -1' }}>
            <label>Custom Payload (JSON)</label>
            <textarea
              className="form-control"
              rows={4}
              value={runPayload}
              onChange={(e) => { setRunPayload(e.target.value); setRunPayloadError('') }}
              placeholder={'例如: {\n  "style_bible": {\n    "tone": "正式"\n  }\n}'}
            />
            {runPayloadError && (
              <div style={{ color: 'var(--danger)', fontSize: '12px', marginTop: 4 }}>
                {runPayloadError}
              </div>
            )}
          </div>
        </div>
        <button
          onClick={handleRun}
          className="btn btn-primary"
          disabled={running || !runSkillId || (!runText.trim() && !runPayload.trim())}
        >
          {running ? '运行中...' : '试运行'}
        </button>

        {runResult && (
          <div style={{ marginTop: 'var(--space-3)' }}>
            <div
              style={{
                padding: '12px',
                borderRadius: '6px',
                background: runResult.result.ok ? '#dcfce7' : '#fef2f2',
                color: runResult.result.ok ? '#166534' : '#991b1b',
                fontSize: '13px',
                marginBottom: 'var(--space-2)',
              }}
            >
              <strong>{runResult.result.ok ? '运行成功' : '运行失败'}</strong>
              {runResult.result.error && (
                <div style={{ marginTop: 4 }}>{runResult.result.error}</div>
              )}
            </div>
            {runResult.result.data && (
              <pre
                style={{
                  background: '#1f2937',
                  color: '#f9fafb',
                  padding: '12px',
                  borderRadius: '6px',
                  fontSize: '12px',
                  overflow: 'auto',
                  maxHeight: 300,
                }}
              >
                {JSON.stringify(runResult.result.data, null, 2)}
              </pre>
            )}
          </div>
        )}
      </div>

      {/* Mount relationships */}
      {Object.keys(mounts).length > 0 && (
        <div style={{ marginBottom: 'var(--space-4)' }}>
          <h4 style={sectionTitleStyle}>挂载关系</h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            {Object.entries(mounts).map(([agent, stages]) => (
              <div
                key={agent}
                style={{
                  padding: 'var(--space-3)',
                  borderRadius: 'var(--radius-md)',
                  background: 'var(--bg-secondary)',
                  border: '1px solid rgba(30, 58, 95, 0.06)',
                  minWidth: 0,
                }}
              >
                <div
                  style={{
                    fontWeight: 'var(--font-semibold)',
                    fontSize: 'var(--text-sm)',
                    marginBottom: 'var(--space-2)',
                    textTransform: 'capitalize',
                  }}
                >
                  {agent}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {Object.entries(stages).map(([stage, skillIds]) => (
                    <div
                      key={stage}
                      style={{
                        display: 'grid',
                        gridTemplateColumns: 'minmax(92px, 0.25fr) minmax(0, 1fr)',
                        gap: 8,
                        alignItems: 'baseline',
                      }}
                    >
                      <span
                        style={{
                          fontSize: '12px',
                          color: 'var(--text-secondary)',
                          fontFamily: 'monospace',
                          overflowWrap: 'anywhere',
                        }}
                      >
                        {stage}
                      </span>
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                        {skillIds.map((id) => (
                          <span
                            key={id}
                            style={{
                              ...statusChipStyle('ok'),
                              background: 'rgba(59, 130, 246, 0.1)',
                              color: '#1e40af',
                            }}
                          >
                            {id}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Skill list table */}
      <div>
        <h4
          style={sectionTitleStyle}
        >
          Skill 列表
        </h4>
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>名称</th>
                <th>类型</th>
                <th>版本</th>
                <th>Package</th>
                <th>Class</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              {skills.map((skill) => (
                <tr key={skill.id}>
                  <td>
                    <code style={compactCodeStyle}>{skill.id}</code>
                  </td>
                  <td>{skill.name || '-'}</td>
                  <td>{skill.kind || skill.type || '-'}</td>
                  <td>{skill.version || '-'}</td>
                  <td>
                    <code style={{ ...compactCodeStyle, fontSize: '11px' }}>{skill.package || '-'}</code>
                  </td>
                  <td>
                    <code style={{ ...compactCodeStyle, fontSize: '11px' }}>{skill.class_name || skill.class || '-'}</code>
                  </td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span
                        style={{
                          display: 'inline-block',
                          width: 8,
                          height: 8,
                          borderRadius: '50%',
                          background: skill.enabled ? 'var(--success)' : 'var(--text-muted)',
                        }}
                      />
                      <span style={{ fontSize: '12px' }}>
                        {skill.enabled ? '已启用' : '已禁用'}
                      </span>
                      {skill.enabled && !skill.is_mounted && (
                        <span
                          style={{
                            ...statusChipStyle('warn'),
                            padding: '1px 6px',
                            fontSize: '11px',
                          }}
                        >
                          未挂载
                        </span>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Descriptions */}
      <div style={{ marginTop: 'var(--space-4)' }}>
        {skills.map((skill) => (
          <div
            key={`desc-${skill.id}`}
            style={{
              marginBottom: 'var(--space-2)',
              padding: 'var(--space-3)',
              borderRadius: 'var(--radius-md)',
              background: 'var(--bg-secondary)',
              border: '1px solid rgba(30, 58, 95, 0.06)',
            }}
          >
            <div style={{ fontWeight: 600, fontSize: '13px', marginBottom: 4 }}>
              {skill.name || skill.id}
            </div>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              {skill.description || '无描述'}
            </div>
            {skill.mounted_to.length > 0 && (
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: 4 }}>
                挂载到:{" "}
                {skill.mounted_to.map((m) => `${m.agent}/${m.stage}`).join(', ')}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
