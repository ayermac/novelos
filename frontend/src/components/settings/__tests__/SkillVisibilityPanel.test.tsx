import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import SkillVisibilityPanel from '../SkillVisibilityPanel'
import { del, get, post } from '../../../lib/api'

vi.mock('../../../lib/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  del: vi.fn(),
}))

const skills = [
  {
    id: 'style-polisher',
    name: 'Style Polisher',
    enabled: true,
    kind: 'rewrite',
    package: 'pkg.style',
    class_name: 'StyleSkill',
    description: 'Polish prose and keep house style.',
    mounted_to: [{ agent: 'author', stage: 'draft' }],
    is_mounted: true,
  },
  {
    id: 'risk-legacy',
    name: 'Legacy Risk',
    enabled: true,
    kind: 'legacy',
    description: 'Old local skill without package.',
    mounted_to: [],
    is_mounted: false,
  },
  {
    id: 'disabled-mounted',
    name: 'Disabled Mounted',
    enabled: false,
    kind: 'guard',
    package: 'pkg.guard',
    class_name: 'GuardSkill',
    description: 'Disabled but still mounted.',
    mounted_to: [{ agent: 'planner', stage: 'plan' }],
    is_mounted: true,
  },
]

const skillConfig = {
  agents: ['planner', 'screenwriter', 'author', 'polisher', 'editor', 'memory_curator', 'scout'],
  stages: {
    planner: ['plan', 'after_llm'],
    screenwriter: ['after_llm'],
    author: ['draft', 'revise', 'after_llm'],
    polisher: ['after_llm', 'before_save'],
    editor: ['before_review'],
    memory_curator: ['after_review', 'after_extract'],
    scout: ['research'],
  },
  agent_skills: {
    planner: { plan: ['disabled-mounted'], after_llm: ['chapter-objective-checker'] },
    screenwriter: { after_llm: ['scene-conflict-checker'] },
    author: { draft: ['style-polisher', 'fresh-add'], revise: ['missing-skill'], after_llm: ['event-coverage-checker'] },
    polisher: { after_llm: ['humanizer-zh'], before_save: [] },
    editor: { before_review: ['ai-style-detector'] },
    memory_curator: { after_review: [], after_extract: ['memory-patch-validator'] },
    scout: { research: [] },
  },
  available_skills: [
    {
      id: 'style-polisher',
      name: 'Style Polisher',
      enabled: true,
      kind: 'rewrite',
      package: 'pkg.style',
      legacy: false,
      class_name: 'StyleSkill',
      allowed_targets: [{ agent: 'author', stage: 'draft' }],
      mountable_targets: [{ agent: 'author', stage: 'draft' }],
    },
    {
      id: 'risk-legacy',
      name: 'Legacy Risk',
      enabled: true,
      kind: 'legacy',
      package: null,
      legacy: true,
      class_name: null,
      allowed_targets: [{ agent: 'scout', stage: 'research' }],
      mountable_targets: [{ agent: 'scout', stage: 'research' }],
    },
    {
      id: 'disabled-mounted',
      name: 'Disabled Mounted',
      enabled: false,
      kind: 'guard',
      package: 'pkg.guard',
      legacy: false,
      class_name: 'GuardSkill',
      allowed_targets: [{ agent: 'planner', stage: 'plan' }],
      mountable_targets: [{ agent: 'planner', stage: 'plan' }],
    },
    {
      id: 'fresh-add',
      name: 'Fresh Add',
      enabled: true,
      kind: 'augment',
      package: 'pkg.add',
      legacy: false,
      class_name: 'FreshSkill',
      allowed_targets: [{ agent: 'author', stage: 'draft' }],
      mountable_targets: [{ agent: 'author', stage: 'draft' }],
    },
    {
      id: 'new-add',
      name: 'New Add',
      enabled: true,
      kind: 'augment',
      package: 'pkg.new',
      legacy: false,
      class_name: 'NewSkill',
      allowed_targets: [{ agent: 'author', stage: 'draft' }],
      mountable_targets: [{ agent: 'author', stage: 'draft' }],
    },
    {
      id: 'chapter-objective-checker',
      name: 'Chapter Objective Checker',
      enabled: true,
      kind: 'validator',
      package: null,
      legacy: false,
      class_name: 'ChapterObjectiveCheckerSkill',
      allowed_targets: [{ agent: 'planner', stage: 'after_llm' }],
      mountable_targets: [{ agent: 'planner', stage: 'after_llm' }],
    },
    {
      id: 'scene-conflict-checker',
      name: 'Scene Conflict Checker',
      enabled: true,
      kind: 'validator',
      package: null,
      legacy: false,
      class_name: 'SceneConflictCheckerSkill',
      allowed_targets: [{ agent: 'screenwriter', stage: 'after_llm' }],
      mountable_targets: [{ agent: 'screenwriter', stage: 'after_llm' }],
    },
    {
      id: 'event-coverage-checker',
      name: 'Event Coverage Checker',
      enabled: true,
      kind: 'validator',
      package: null,
      legacy: false,
      class_name: 'EventCoverageCheckerSkill',
      allowed_targets: [{ agent: 'author', stage: 'after_llm' }],
      mountable_targets: [{ agent: 'author', stage: 'after_llm' }],
    },
    {
      id: 'memory-patch-validator',
      name: 'Memory Patch Validator',
      enabled: true,
      kind: 'validator',
      package: null,
      legacy: false,
      class_name: 'MemoryPatchValidatorSkill',
      allowed_targets: [{ agent: 'memory_curator', stage: 'after_extract' }],
      mountable_targets: [{ agent: 'memory_curator', stage: 'after_extract' }],
    },
    {
      id: 'humanizer-zh',
      name: 'Humanizer',
      enabled: true,
      kind: 'transform',
      package: 'skill_packages/humanizer_zh',
      legacy: false,
      class_name: 'HumanizerZhSkill',
      allowed_targets: [{ agent: 'polisher', stage: 'after_llm' }],
      mountable_targets: [{ agent: 'polisher', stage: 'after_llm' }],
    },
    {
      id: 'ai-style-detector',
      name: 'AI Style Detector',
      enabled: true,
      kind: 'validator',
      package: 'skill_packages/ai_style_detector',
      legacy: false,
      class_name: 'AIStyleDetectorSkill',
      allowed_targets: [{ agent: 'editor', stage: 'before_review' }],
      mountable_targets: [{ agent: 'editor', stage: 'before_review' }],
    },
  ],
  missing_skills: [{ id: 'missing-skill', agent: 'author', stage: 'revise' }],
  disabled_skills: [{ id: 'disabled-mounted', name: 'Disabled Mounted' }],
  config_path: 'config/local.yaml',
  total_skills: 10,
  total_mounted: 9,
}

const agentMatrix = {
  agents: [
    {
      agent: 'planner',
      stages: [
        {
          stage: 'plan',
          skill_ids: ['disabled-mounted'],
          skills: [{ id: 'disabled-mounted', name: 'Disabled Mounted', enabled: false, missing: false, package: 'pkg.guard', legacy: false, kind: 'guard' }],
          warnings: [{ code: 'disabled', message: 'disabled-mounted is disabled' }],
        },
        {
          stage: 'after_llm',
          skill_ids: ['chapter-objective-checker'],
          skills: [{ id: 'chapter-objective-checker', name: 'Chapter Objective Checker', enabled: true, missing: false, package: null, legacy: false, kind: 'validator' }],
          warnings: [],
        },
      ],
    },
    {
      agent: 'screenwriter',
      stages: [
        {
          stage: 'after_llm',
          skill_ids: ['scene-conflict-checker'],
          skills: [{ id: 'scene-conflict-checker', name: 'Scene Conflict Checker', enabled: true, missing: false, package: null, legacy: false, kind: 'validator' }],
          warnings: [],
        },
      ],
    },
    {
      agent: 'author',
      stages: [
        {
          stage: 'draft',
          skill_ids: ['style-polisher', 'fresh-add'],
          skills: [
            { id: 'style-polisher', name: 'Style Polisher', enabled: true, missing: false, package: 'pkg.style', legacy: false, kind: 'rewrite' },
            { id: 'fresh-add', name: 'Fresh Add', enabled: true, missing: false, package: 'pkg.add', legacy: false, kind: 'augment' },
          ],
          warnings: [],
        },
        {
          stage: 'revise',
          skill_ids: ['missing-skill'],
          skills: [{ id: 'missing-skill', name: null, enabled: false, missing: true, package: null, legacy: false, kind: null }],
          warnings: [{ code: 'missing', message: 'missing-skill is missing' }],
        },
      ],
    },
    {
      agent: 'polisher',
      stages: [
        {
          stage: 'after_llm',
          skill_ids: ['humanizer-zh'],
          skills: [{ id: 'humanizer-zh', name: 'Humanizer', enabled: true, missing: false, package: 'skill_packages/humanizer_zh', legacy: false, kind: 'transform' }],
          warnings: [],
        },
      ],
    },
    {
      agent: 'editor',
      stages: [
        {
          stage: 'before_review',
          skill_ids: ['ai-style-detector'],
          skills: [{ id: 'ai-style-detector', name: 'AI Style Detector', enabled: true, missing: false, package: 'skill_packages/ai_style_detector', legacy: false, kind: 'validator' }],
          warnings: [],
        },
      ],
    },
    {
      agent: 'memory_curator',
      stages: [
        {
          stage: 'after_extract',
          skill_ids: ['memory-patch-validator'],
          skills: [{ id: 'memory-patch-validator', name: 'Memory Patch Validator', enabled: true, missing: false, package: null, legacy: false, kind: 'validator' }],
          warnings: [],
        },
      ],
    },
  ],
  unmounted_enabled_skills: [{ id: 'risk-legacy', name: 'Legacy Risk', enabled: true, missing: false, package: null, legacy: true, kind: 'legacy' }],
  warnings: [{ code: 'matrix_warning', message: 'disabled-mounted is mounted but disabled', skill_id: 'disabled-mounted' }],
}

function mockApi() {
  vi.mocked(get).mockImplementation(async (path: string) => {
    if (path === '/skills') return { ok: true, data: { skills } }
    if (path === '/skills/agent-matrix') return { ok: true, data: agentMatrix }
    if (path === '/skills/config') return { ok: true, data: skillConfig }
    return { ok: false, error: { code: 'NOT_FOUND', message: path } }
  })
  vi.mocked(post).mockImplementation(async (path: string, body?: unknown) => {
    if (path === '/skills/validate') return { ok: true, data: { ok: false, errors: ['missing-skill not found'], warnings: ['risk-legacy is enabled but unmounted'] } }
    if (path === '/skills/review') return {
      ok: true,
      data: {
        skill_id: (body as { skill_id: string }).skill_id,
        verdict: 'warn',
        enabled: true,
        imported: false,
        manifest: true,
        findings: [{ severity: 'warn', code: 'legacy', message: 'legacy target requires review' }],
        recommended_actions: ['Review mount target'],
        allowed_targets: [{ agent: 'scout', stage: 'research' }],
        mountable_targets: [{ agent: 'scout', stage: 'research' }],
      },
    }
    if (path === '/skills/mount') return { ok: true, data: body }
    if (path === '/skills/reorder') return { ok: true, data: body }
    if (path === '/skills/enabled') return { ok: true, data: { skill_id: 'x', enabled: true, mounted_to: [], is_mounted: false } }
    if (path === '/skills/test') return { ok: true, data: { total: 1, passed: 1, failed: 0, skipped: 0, skipped_ids: [], results: {} } }
    return { ok: false, error: { code: 'NOT_FOUND', message: path } }
  })
  vi.mocked(del).mockResolvedValue({ ok: true, data: { agent: 'author', stage: 'draft', skill_id: 'style-polisher' } })
}

describe('SkillVisibilityPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi()
  })

  it('section navigation switches console views', async () => {
    render(<SkillVisibilityPanel />)
    expect(await screen.findByText('Skill 管理工作台')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Agent 编排/ }))
    expect(screen.getByText('Agent × Stage Orchestration')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /能力库/ }))
    expect(screen.getByText('Style Polisher')).toBeInTheDocument()
  })

  it('capability filters and search apply across id, package, description, and class', async () => {
    render(<SkillVisibilityPanel />)
    fireEvent.click(await screen.findByRole('button', { name: /能力库/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Legacy' }))
    expect(screen.getByText('Legacy Risk')).toBeInTheDocument()
    expect(screen.queryByText('Style Polisher')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '全部' }))
    fireEvent.change(screen.getByPlaceholderText('搜索 id、名称、package、描述或 class'), { target: { value: 'StyleSkill' } })
    expect(screen.getByText('Style Polisher')).toBeInTheDocument()
    expect(screen.queryByText('Legacy Risk')).not.toBeInTheDocument()

    fireEvent.change(screen.getByPlaceholderText('搜索 id、名称、package、描述或 class'), { target: { value: 'pkg.guard' } })
    expect(screen.getByText('Disabled Mounted')).toBeInTheDocument()
  })

  it('risk filter only shows actionable missing, disabled-mounted, or reviewed-risk skills', async () => {
    render(<SkillVisibilityPanel />)
    fireEvent.click(await screen.findByRole('button', { name: /能力库/ }))
    fireEvent.click(screen.getByRole('button', { name: '缺失/风险' }))

    expect(screen.getByText('Disabled Mounted')).toBeInTheDocument()
    expect(screen.getAllByText('missing-skill').length).toBeGreaterThan(0)
    expect(screen.queryByText('Style Polisher')).not.toBeInTheDocument()
    expect(screen.queryByText('Legacy Risk')).not.toBeInTheDocument()
  })

  it('orchestration matrix renders agent and stage cells', async () => {
    render(<SkillVisibilityPanel />)
    fireEvent.click(await screen.findByRole('button', { name: /Agent 编排/ }))
    expect(screen.getByText('Creative Agents')).toBeInTheDocument()
    expect(screen.getByText('Support Agents')).toBeInTheDocument()
    expect(screen.getByText('Diagnostic/Research Agents')).toBeInTheDocument()
    expect(screen.getAllByText('planner').length).toBeGreaterThan(0)
    expect(screen.getAllByText('draft').length).toBeGreaterThan(0)
    expect(screen.getByText('style-polisher')).toBeInTheDocument()
    expect(screen.getByText('missing')).toBeInTheDocument()
  })

  it('shows core Agent coverage and stage explanations', async () => {
    render(<SkillVisibilityPanel />)
    expect(await screen.findByText('Core Agent coverage')).toBeInTheDocument()
    expect(screen.getByText('6/6')).toBeInTheDocument()
    expect(screen.getByText(/planner、screenwriter、author/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Agent 编排/ }))
    expect(screen.getByText('生成前上下文增强')).toBeInTheDocument()
    expect(screen.getByText('生成后校验/改写')).toBeInTheDocument()
    expect(screen.getByText('记忆抽取后校验')).toBeInTheDocument()
    expect(screen.getByText('审稿前质量检查')).toBeInTheDocument()
  })

  it('renders default core Agent mounts in the matrix', async () => {
    render(<SkillVisibilityPanel />)
    fireEvent.click(await screen.findByRole('button', { name: /Agent 编排/ }))
    expect(screen.getByText('chapter-objective-checker')).toBeInTheDocument()
    expect(screen.getByText('scene-conflict-checker')).toBeInTheDocument()
    expect(screen.getByText('event-coverage-checker')).toBeInTheDocument()
    expect(screen.getByText('memory-patch-validator')).toBeInTheDocument()
  })

  it('add, remove, and reorder controls call existing APIs', async () => {
    render(<SkillVisibilityPanel />)
    fireEvent.click(await screen.findByRole('button', { name: /Agent 编排/ }))

    fireEvent.change(screen.getByLabelText('author draft 添加 Skill'), { target: { value: 'new-add' } })
    fireEvent.click(screen.getByLabelText('author draft 确认添加'))
    await waitFor(() => expect(post).toHaveBeenCalledWith('/skills/mount', { agent: 'author', stage: 'draft', skill_id: 'new-add' }))

    fireEvent.click(screen.getByLabelText('style-polisher 下移'))
    await waitFor(() => expect(post).toHaveBeenCalledWith('/skills/reorder', { agent: 'author', stage: 'draft', skill_ids: ['fresh-add', 'style-polisher'] }))

    fireEvent.click(screen.getByLabelText('style-polisher 移除'))
    await waitFor(() => expect(del).toHaveBeenCalledWith('/skills/mount', { agent: 'author', stage: 'draft', skill_id: 'style-polisher' }))
  })

  it('validation warnings appear in overview and route to the relevant console', async () => {
    render(<SkillVisibilityPanel />)
    fireEvent.click(await screen.findByRole('button', { name: '验证配置' }))
    await waitFor(() => expect(screen.getAllByText('missing-skill not found').length).toBeGreaterThan(0))
    fireEvent.click(screen.getByRole('button', { name: /配置验证失败/ }))
    expect(screen.getByText('Config validation')).toBeInTheDocument()
  })
})
