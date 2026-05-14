import { useEffect, useState } from 'react'
import { get, post } from '../lib/api'
import StatusBadge from '../components/StatusBadge'
import EmptyState from '../components/EmptyState'
import ErrorState from '../components/ErrorState'
import PageHeader from '../components/PageHeader'
import { useAppDialog } from '../components/AppDialogContext'
import { DataTable } from '../components/ui'

interface StyleBible {
  project_id: string
  project_name: string
  status: string
  version: number
  updated_at: string
}

interface StyleGateConfig {
  project_id: string
  project_name: string
  enabled: boolean
  threshold: number
}

interface StyleSample {
  project_id: string
  sample_id: string
  source: string
  word_count: number
}

interface StyleData {
  style_bibles: StyleBible[]
  style_gate_configs: StyleGateConfig[]
  style_samples: StyleSample[]
  health: {
    total_projects: number
    projects_with_bible: number
    gate_configs: number
  }
}

export default function Style() {
  const dialog = useAppDialog()
  const [data, setData] = useState<StyleData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [initLoading, setInitLoading] = useState<string | null>(null)
  const [initSuccess, setInitSuccess] = useState<string | null>(null)

  const handleInitStyleBible = async (projectId: string) => {
    setInitLoading(projectId)
    setInitSuccess(null)
    try {
      const res = await post('/style/init', { project_id: projectId })
      if (res.ok) {
        setInitSuccess(projectId)
        load()
      } else {
        setError(res.error?.message || '初始化 Style Bible 失败')
      }
    } catch {
      setError('操作失败')
    } finally {
      setInitLoading(null)
    }
  }

  const load = () => {
    setLoading(true)
    setError('')
    get<StyleData>('/style/console').then((res) => {
      if (res.ok && res.data) {
        setData(res.data)
      } else {
        setError(res.error?.message || '获取风格管理数据失败')
      }
      setLoading(false)
    })
  }

  useEffect(() => {
    load()
  }, [])

  if (loading) {
    return <div>加载中...</div>
  }

  if (error) {
    return (
      <ErrorState
        title="加载失败"
        message={error}
        onRetry={load}
      />
    )
  }

  if (!data) {
    return (
      <ErrorState
        title="加载失败"
        message="无法获取风格数据"
        onRetry={load}
      />
    )
  }

  const hasAnyData =
    data.style_bibles.length > 0 ||
    data.style_gate_configs.length > 0 ||
    data.style_samples.length > 0

  return (
    <div>
      <PageHeader title="风格管理" />

      {/* Info Banner */}
      <div className="alert alert-info" style={{ marginBottom: 'var(--spacing-lg)' }}>
        <strong>风格管理说明</strong>
        <div style={{ marginTop: '4px', fontSize: '14px' }}>
          风格圣经用于统一项目写作风格，包含词汇偏好、句式模板、叙事视角等。
          生成章节时会自动提取风格特征。风格门禁可在生成前检查风格一致性。
        </div>
      </div>

      {/* Capability Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginBottom: 'var(--spacing-lg)' }}>
        <div className="card">
          <div className="card-body" style={{ textAlign: 'center', padding: '20px' }}>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '4px' }}>总项目</div>
            <div style={{ fontSize: '28px', fontWeight: 700, color: 'var(--text-primary)' }}>{data.health.total_projects}</div>
            <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>已创建的小说项目</div>
          </div>
        </div>
        <div className="card">
          <div className="card-body" style={{ textAlign: 'center', padding: '20px' }}>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '4px' }}>风格圣经</div>
            <div style={{ fontSize: '28px', fontWeight: 700, color: data.health.projects_with_bible > 0 ? 'var(--success)' : 'var(--text-muted)' }}>
              {data.health.projects_with_bible}
            </div>
            <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>已建立风格档案</div>
          </div>
        </div>
        <div className="card">
          <div className="card-body" style={{ textAlign: 'center', padding: '20px' }}>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '4px' }}>风格门禁</div>
            <div style={{ fontSize: '28px', fontWeight: 700, color: data.health.gate_configs > 0 ? 'var(--primary)' : 'var(--text-muted)' }}>
              {data.health.gate_configs}
            </div>
            <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>启用的门禁规则</div>
          </div>
        </div>
      </div>

      {!hasAnyData ? (
        <div className="card">
          <div className="card-body">
            <EmptyState
              title="暂无风格数据"
              hint="风格圣经用于统一项目写作风格。生成章节时会自动提取风格特征。请先创建项目并生成章节，系统将自动建立风格档案。"
              actions={[
                { label: '查看项目列表', to: '/projects' },
                { label: '创建新项目', to: '/onboarding' },
              ]}
            />
          </div>
        </div>
      ) : (
        <>
          {/* Style Bibles */}
          <div className="card" style={{ marginBottom: 'var(--spacing-lg)' }}>
            <div className="card-header">
              <h3>风格圣经</h3>
            </div>
            <div className="card-body">
              {data.style_bibles.length > 0 ? (
                <DataTable
                  compact
                  data={data.style_bibles}
                  getRowKey={(bible) => bible.project_id}
                  columns={[
                    { key: 'project', header: '项目', render: (bible) => bible.project_name },
                    { key: 'status', header: '状态', render: (bible) => <StatusBadge status={bible.status} /> },
                    { key: 'version', header: '版本', render: (bible) => `v${bible.version}` },
                    { key: 'updated', header: '更新时间', render: (bible) => <span className="text-secondary">{bible.updated_at}</span> },
                    { key: 'actions', header: '操作', render: () => <span className="text-secondary">已建立</span> },
                  ]}
                />
              ) : (
                <div>
                  <EmptyState
                    title="暂无风格圣经"
                    hint="点击下方按钮为项目初始化 Style Bible"
                  />
                  {initSuccess && (
                    <div className="alert alert-success" style={{ marginTop: '12px' }}>
                      Style Bible 初始化成功！
                    </div>
                  )}
                  <div style={{ marginTop: '12px', textAlign: 'center' }}>
                    <button
                      className="btn btn-primary"
                      onClick={async () => {
                        const projectId = await dialog.prompt({
                          title: '初始化 Style Bible',
                          message: '请输入需要初始化风格圣经的项目 ID。',
                          placeholder: 'project_id',
                          confirmLabel: '开始初始化',
                        })
                        if (projectId) handleInitStyleBible(projectId)
                      }}
                      disabled={initLoading !== null}
                    >
                      {initLoading ? '初始化中...' : '初始化 Style Bible'}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Style Gate */}
          {data.style_gate_configs.length > 0 && (
            <div className="card" style={{ marginBottom: 'var(--spacing-lg)' }}>
              <div className="card-header">
                <h3>风格门禁</h3>
              </div>
              <div className="card-body">
                <DataTable
                  compact
                  data={data.style_gate_configs}
                  getRowKey={(config) => config.project_id}
                  columns={[
                    { key: 'project', header: '项目', render: (config) => config.project_name },
                    {
                      key: 'enabled',
                      header: '启用',
                      render: (config) => (
                        <span className={`status-badge ${config.enabled ? 'status-active' : 'status-inactive'}`}>
                          {config.enabled ? '已启用' : '已停用'}
                        </span>
                      ),
                    },
                    { key: 'threshold', header: '阈值', render: (config) => config.threshold },
                  ]}
                />
              </div>
            </div>
          )}

          {/* Style Samples */}
          {data.style_samples.length > 0 && (
            <div className="card">
              <div className="card-header">
                <h3>风格样本</h3>
              </div>
              <div className="card-body">
                <DataTable
                  compact
                  data={data.style_samples}
                  getRowKey={(sample) => sample.sample_id}
                  columns={[
                    { key: 'source', header: '来源', render: (sample) => sample.source },
                    { key: 'words', header: '字数', render: (sample) => sample.word_count },
                  ]}
                />
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
