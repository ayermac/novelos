import { useState, useEffect } from 'react'
import { put } from '../../lib/api'

export interface GateFormData {
  enabled: boolean
  mode: string
  blocking_threshold: number
  revision_target: string
  apply_stages: string
}

function gateToForm(data: Record<string, unknown>): GateFormData {
  return {
    enabled: Boolean(data.enabled),
    mode: String(data.mode || 'warn'),
    blocking_threshold: Number(data.blocking_threshold || 70),
    revision_target: String(data.revision_target || 'polisher'),
    apply_stages: Array.isArray(data.apply_stages) ? data.apply_stages.join('\n') : String(data.apply_stages || 'polished\nfinal_gate'),
  }
}

function formToGate(form: GateFormData): Record<string, unknown> {
  return {
    enabled: form.enabled,
    mode: form.mode,
    blocking_threshold: form.blocking_threshold,
    revision_target: form.revision_target,
    apply_stages: form.apply_stages
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean),
  }
}

interface Props {
  projectId: string
  initialGate: Record<string, unknown>
  onSaved?: () => void
}

export default function StyleGateEditor({ projectId, initialGate, onSaved }: Props) {
  const [form, setForm] = useState<GateFormData>(gateToForm(initialGate))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)

  useEffect(() => {
    setForm(gateToForm(initialGate))
  }, [initialGate])

  const update = (field: keyof GateFormData, value: string | boolean | number) => {
    setForm((prev) => ({ ...prev, [field]: value }))
    setSuccess(false)
  }

  const handleSave = async () => {
    setSaving(true)
    setError('')
    setSuccess(false)
    const gate = formToGate(form)
    const res = await put(`/style/bible/${projectId}`, { gate_config: gate })
    setSaving(false)
    if (res.ok) {
      setSuccess(true)
      onSaved?.()
    } else {
      setError(res.error?.message || '保存失败')
    }
  }

  const fieldStyle: React.CSSProperties = {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: 4,
    marginBottom: 12,
  }

  const labelStyle: React.CSSProperties = {
    fontSize: 13,
    fontWeight: 600,
    color: 'var(--text-secondary)',
  }

  const inputStyle: React.CSSProperties = {
    padding: '8px 10px',
    borderRadius: 6,
    border: '1px solid var(--border)',
    fontSize: 14,
    background: 'var(--surface)',
    color: 'var(--text-primary)',
  }

  return (
    <div>
      {error && <div className="alert alert-error" style={{ marginBottom: 12 }}>{error}</div>}
      {success && <div className="alert alert-success" style={{ marginBottom: 12 }}>保存成功</div>}

      <div style={fieldStyle}>
        <label style={labelStyle}>
          <input
            type="checkbox"
            checked={form.enabled}
            onChange={(e) => update('enabled', e.target.checked)}
            style={{ marginRight: 8 }}
          />
          启用风格门禁
        </label>
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          默认不启用，启用后也不会默认阻断创作，仅做警告记录。
        </div>
      </div>

      <div style={fieldStyle}>
        <label style={labelStyle}>模式</label>
        <select style={inputStyle} value={form.mode} onChange={(e) => update('mode', e.target.value)}>
          <option value="off">关闭（仅记录）</option>
          <option value="warn">警告（不阻断）</option>
          <option value="block">阻断（需明确设置）</option>
        </select>
      </div>

      <div style={fieldStyle}>
        <label style={labelStyle}>阻断阈值（0-100，分数低于此值时阻断）</label>
        <input
          type="number"
          style={inputStyle}
          min={0}
          max={100}
          value={form.blocking_threshold}
          onChange={(e) => update('blocking_threshold', Number(e.target.value))}
        />
      </div>

      <div style={fieldStyle}>
        <label style={labelStyle}>返修目标</label>
        <select style={inputStyle} value={form.revision_target} onChange={(e) => update('revision_target', e.target.value)}>
          <option value="author">作者</option>
          <option value="polisher">润色</option>
        </select>
      </div>

      <div style={fieldStyle}>
        <label style={labelStyle}>应用阶段（每行一个）</label>
        <textarea
          style={{ ...inputStyle, minHeight: 60, resize: 'vertical', fontFamily: 'monospace' }}
          value={form.apply_stages}
          onChange={(e) => update('apply_stages', e.target.value)}
        />
      </div>

      <div style={{ marginTop: 20 }}>
        <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? '保存中...' : '保存门禁配置'}
        </button>
      </div>
    </div>
  )
}
