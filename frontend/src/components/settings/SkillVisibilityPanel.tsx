import { useEffect, useState } from 'react'
import { get, post } from '../../lib/api'

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

export default function SkillVisibilityPanel() {
  const [skills, setSkills] = useState<SkillInfo[]>([])
  const [mounts, setMounts] = useState<MountMap>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [validating, setValidating] = useState(false)
  const [validateResult, setValidateResult] = useState<ValidateResult | null>(null)

  const load = async () => {
    setLoading(true)
    setError('')

    const [skillsRes, mountsRes] = await Promise.all([
      get<{ skills: SkillInfo[] }>('/skills'),
      get<MountMap>('/skills/mounts'),
    ])

    if (skillsRes.ok && skillsRes.data) {
      setSkills(skillsRes.data.skills)
    } else {
      setError(skillsRes.error?.message || '获取 Skill 列表失败')
    }

    if (mountsRes.ok && mountsRes.data) {
      setMounts(mountsRes.data)
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

  return (
    <div style={{ padding: 'var(--space-5)' }}>
      {/* Validate button */}
      <div style={{ marginBottom: 'var(--space-4)', display: 'flex', alignItems: 'center', gap: 12 }}>
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
                  padding: '2px 8px',
                  borderRadius: '4px',
                  background: '#fde68a',
                  fontSize: '12px',
                  fontWeight: 500,
                }}
              >
                {s.id}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Mount relationships */}
      {Object.keys(mounts).length > 0 && (
        <div style={{ marginBottom: 'var(--space-4)' }}>
          <h4
            style={{
              fontSize: 'var(--text-sm)',
              fontWeight: 'var(--font-semibold)',
              margin: '0 0 var(--space-3) 0',
              color: 'var(--text-primary)',
            }}
          >
            挂载关系
          </h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            {Object.entries(mounts).map(([agent, stages]) => (
              <div
                key={agent}
                style={{
                  padding: 'var(--space-3)',
                  borderRadius: 'var(--radius-md)',
                  background: 'var(--bg-secondary)',
                  border: '1px solid rgba(30, 58, 95, 0.06)',
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
                    <div key={stage} style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                      <span
                        style={{
                          fontSize: '12px',
                          color: 'var(--text-secondary)',
                          minWidth: 100,
                          fontFamily: 'monospace',
                        }}
                      >
                        {stage}
                      </span>
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                        {skillIds.map((id) => (
                          <span
                            key={id}
                            style={{
                              padding: '2px 8px',
                              borderRadius: '4px',
                              background: 'rgba(59, 130, 246, 0.1)',
                              color: '#1e40af',
                              fontSize: '12px',
                              fontWeight: 500,
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
          style={{
            fontSize: 'var(--text-sm)',
            fontWeight: 'var(--font-semibold)',
            margin: '0 0 var(--space-3) 0',
            color: 'var(--text-primary)',
          }}
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
                    <code style={{ fontSize: '12px' }}>{skill.id}</code>
                  </td>
                  <td>{skill.name || '-'}</td>
                  <td>{skill.kind || skill.type || '-'}</td>
                  <td>{skill.version || '-'}</td>
                  <td>
                    <code style={{ fontSize: '11px' }}>{skill.package || '-'}</code>
                  </td>
                  <td>
                    <code style={{ fontSize: '11px' }}>{skill.class_name || skill.class || '-'}</code>
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
                            fontSize: '11px',
                            padding: '1px 6px',
                            borderRadius: '4px',
                            background: '#fde68a',
                            color: '#92400e',
                            fontWeight: 500,
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
