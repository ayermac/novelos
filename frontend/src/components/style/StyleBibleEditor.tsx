import { useState, useEffect } from 'react'
import { put } from '../../lib/api'

export interface BibleFormData {
  name: string
  genre: string
  target_platform: string
  target_audience: string
  tone_keywords: string
  pacing: string
  pov: string
  dialogue_style: string
  prose_style: string
  tension_style: string
  humor_style: string
  emotional_intensity: string
  forbidden_expressions: string
  preferred_expressions: string
  sentence_rules: string
  paragraph_rules: string
  chapter_opening_rules: string
  chapter_ending_rules: string
  ai_trace_avoidance_notes: string
  ai_trace_avoid_patterns: string
  ai_trace_prefer_patterns: string
}

function bibleToForm(data: Record<string, unknown>): BibleFormData {
  const arr = (v: unknown) => {
    if (Array.isArray(v)) return v.map((i) => (typeof i === 'string' ? i : JSON.stringify(i))).join('\n')
    return String(v || '')
  }
  const objArr = (v: unknown) => {
    if (Array.isArray(v)) return v.map((i) => (typeof i === 'object' && i !== null ? JSON.stringify(i) : String(i))).join('\n')
    return String(v || '')
  }
  const ai = (data.ai_trace_avoidance || {}) as Record<string, unknown>
  return {
    name: String(data.name || ''),
    genre: String(data.genre || ''),
    target_platform: String(data.target_platform || ''),
    target_audience: String(data.target_audience || ''),
    tone_keywords: arr(data.tone_keywords),
    pacing: String(data.pacing || 'balanced'),
    pov: String(data.pov || 'third_person_limited'),
    dialogue_style: String(data.dialogue_style || ''),
    prose_style: String(data.prose_style || ''),
    tension_style: String(data.tension_style || ''),
    humor_style: String(data.humor_style || ''),
    emotional_intensity: String(data.emotional_intensity || 'medium'),
    forbidden_expressions: objArr(data.forbidden_expressions),
    preferred_expressions: objArr(data.preferred_expressions),
    sentence_rules: objArr(data.sentence_rules),
    paragraph_rules: objArr(data.paragraph_rules),
    chapter_opening_rules: objArr(data.chapter_opening_rules),
    chapter_ending_rules: objArr(data.chapter_ending_rules),
    ai_trace_avoidance_notes: String(ai.notes || ''),
    ai_trace_avoid_patterns: arr(ai.avoid_patterns),
    ai_trace_prefer_patterns: arr(ai.prefer_patterns),
  }
}

function formToBible(form: BibleFormData): Record<string, unknown> {
  const parseLines = (v: string) =>
    v
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean)

  const parseObjLines = (v: string, fallback: (line: string) => Record<string, unknown>): unknown[] => {
    const lines = parseLines(v)
    return lines
      .map((line) => {
        try {
          return JSON.parse(line)
        } catch {
          return fallback(line)
        }
      })
      .filter(Boolean)
  }

  return {
    name: form.name,
    genre: form.genre,
    target_platform: form.target_platform,
    target_audience: form.target_audience,
    tone_keywords: parseLines(form.tone_keywords),
    pacing: form.pacing,
    pov: form.pov,
    dialogue_style: form.dialogue_style,
    prose_style: form.prose_style,
    tension_style: form.tension_style,
    humor_style: form.humor_style,
    emotional_intensity: form.emotional_intensity,
    forbidden_expressions: parseObjLines(form.forbidden_expressions, (line) => ({ pattern: line, reason: '', severity: 'warning' })),
    preferred_expressions: parseObjLines(form.preferred_expressions, (line) => ({ pattern: line, context: '' })),
    sentence_rules: parseObjLines(form.sentence_rules, (line) => ({ description: line, severity: 'warning' })),
    paragraph_rules: parseObjLines(form.paragraph_rules, (line) => ({ description: line, severity: 'warning' })),
    chapter_opening_rules: parseObjLines(form.chapter_opening_rules, (line) => ({ description: line, severity: 'warning' })),
    chapter_ending_rules: parseObjLines(form.chapter_ending_rules, (line) => ({ description: line, severity: 'warning' })),
    ai_trace_avoidance: {
      avoid_patterns: parseLines(form.ai_trace_avoid_patterns),
      prefer_patterns: parseLines(form.ai_trace_prefer_patterns),
      notes: form.ai_trace_avoidance_notes,
    },
  }
}

interface Props {
  projectId: string
  initialBible: Record<string, unknown>
  onSaved?: () => void
}

export default function StyleBibleEditor({ projectId, initialBible, onSaved }: Props) {
  const [form, setForm] = useState<BibleFormData>(bibleToForm(initialBible))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)

  useEffect(() => {
    setForm(bibleToForm(initialBible))
  }, [initialBible])

  const update = (field: keyof BibleFormData, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }))
    setSuccess(false)
  }

  const handleSave = async () => {
    setSaving(true)
    setError('')
    setSuccess(false)
    const bible = formToBible(form)
    const res = await put(`/style/bible/${projectId}`, { bible })
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

  const textareaStyle: React.CSSProperties = {
    ...inputStyle,
    minHeight: 80,
    resize: 'vertical' as const,
    fontFamily: 'monospace',
  }

  return (
    <div>
      {error && <div className="alert alert-error" style={{ marginBottom: 12 }}>{error}</div>}
      {success && <div className="alert alert-success" style={{ marginBottom: 12 }}>保存成功</div>}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16 }}>
        <div style={fieldStyle}>
          <label style={labelStyle}>名称</label>
          <input style={inputStyle} value={form.name} onChange={(e) => update('name', e.target.value)} />
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>题材</label>
          <input style={inputStyle} value={form.genre} onChange={(e) => update('genre', e.target.value)} />
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>目标平台</label>
          <input style={inputStyle} value={form.target_platform} onChange={(e) => update('target_platform', e.target.value)} />
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>目标读者</label>
          <input style={inputStyle} value={form.target_audience} onChange={(e) => update('target_audience', e.target.value)} />
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>基调关键词（每行一个）</label>
          <textarea style={textareaStyle} value={form.tone_keywords} onChange={(e) => update('tone_keywords', e.target.value)} />
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>节奏</label>
          <select style={inputStyle} value={form.pacing} onChange={(e) => update('pacing', e.target.value)}>
            <option value="slow">慢</option>
            <option value="balanced">适中</option>
            <option value="fast">快</option>
          </select>
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>视角</label>
          <select style={inputStyle} value={form.pov} onChange={(e) => update('pov', e.target.value)}>
            <option value="first_person">第一人称</option>
            <option value="third_person_limited">第三人称有限</option>
            <option value="omniscient">全知</option>
            <option value="mixed">混合</option>
          </select>
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>对白风格</label>
          <input style={inputStyle} value={form.dialogue_style} onChange={(e) => update('dialogue_style', e.target.value)} />
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>行文风格</label>
          <input style={inputStyle} value={form.prose_style} onChange={(e) => update('prose_style', e.target.value)} />
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>张力风格</label>
          <input style={inputStyle} value={form.tension_style} onChange={(e) => update('tension_style', e.target.value)} />
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>幽默风格</label>
          <input style={inputStyle} value={form.humor_style} onChange={(e) => update('humor_style', e.target.value)} />
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>情感强度</label>
          <select style={inputStyle} value={form.emotional_intensity} onChange={(e) => update('emotional_intensity', e.target.value)}>
            <option value="low">低</option>
            <option value="medium">中</option>
            <option value="high">高</option>
          </select>
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>禁用表达（每行一个词/短语，也支持 JSON）</label>
          <textarea style={textareaStyle} value={form.forbidden_expressions} onChange={(e) => update('forbidden_expressions', e.target.value)} />
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>推荐表达（每行一个词/短语，也支持 JSON）</label>
          <textarea style={textareaStyle} value={form.preferred_expressions} onChange={(e) => update('preferred_expressions', e.target.value)} />
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>句式规则（每行一条规则，也支持 JSON）</label>
          <textarea style={textareaStyle} value={form.sentence_rules} onChange={(e) => update('sentence_rules', e.target.value)} />
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>段落规则（每行一条规则，也支持 JSON）</label>
          <textarea style={textareaStyle} value={form.paragraph_rules} onChange={(e) => update('paragraph_rules', e.target.value)} />
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>开头规则（每行一条规则，也支持 JSON）</label>
          <textarea style={textareaStyle} value={form.chapter_opening_rules} onChange={(e) => update('chapter_opening_rules', e.target.value)} />
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>结尾规则（每行一条规则，也支持 JSON）</label>
          <textarea style={textareaStyle} value={form.chapter_ending_rules} onChange={(e) => update('chapter_ending_rules', e.target.value)} />
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>AI 痕迹规避 - 避免模式（每行一个）</label>
          <textarea style={textareaStyle} value={form.ai_trace_avoid_patterns} onChange={(e) => update('ai_trace_avoid_patterns', e.target.value)} />
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>AI 痕迹规避 - 推荐模式（每行一个）</label>
          <textarea style={textareaStyle} value={form.ai_trace_prefer_patterns} onChange={(e) => update('ai_trace_prefer_patterns', e.target.value)} />
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>AI 痕迹规避 - 备注</label>
          <textarea style={textareaStyle} value={form.ai_trace_avoidance_notes} onChange={(e) => update('ai_trace_avoidance_notes', e.target.value)} />
        </div>
      </div>

      <div style={{ marginTop: 20 }}>
        <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? '保存中...' : '保存风格圣经'}
        </button>
      </div>
    </div>
  )
}
