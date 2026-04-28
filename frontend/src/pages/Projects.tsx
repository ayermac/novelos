import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { BookOpen, Trash2, Plus } from 'lucide-react'
import { get, del } from '../lib/api'
import { tGenre } from '../lib/i18n'
import EmptyState from '../components/EmptyState'
import ErrorState from '../components/ErrorState'
import PageHeader from '../components/PageHeader'

interface Project {
  project_id: string
  name: string
  genre?: string
  description?: string
  chapter_count: number
  created_at: string
}

function ProjectCard({ project, onDelete }: { project: Project; onDelete: (id: string) => void }) {
  const handleDelete = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (window.confirm(`确定要删除项目「${project.name || project.project_id}」吗？此操作不可撤销。`)) {
      onDelete(project.project_id)
    }
  }

  return (
    <Link
      to={`/projects/${project.project_id}`}
      style={{
        display: 'block',
        background: 'var(--paper-surface)',
        borderRadius: 'var(--radius-lg)',
        boxShadow: 'var(--shadow-flat)',
        border: '1px solid rgba(30, 58, 95, 0.06)',
        textDecoration: 'none',
        transition: 'all var(--duration-normal) var(--ease-out)',
        overflow: 'hidden',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.transform = 'translateY(-2px)'
        e.currentTarget.style.boxShadow = 'var(--shadow-md)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.transform = ''
        e.currentTarget.style.boxShadow = 'var(--shadow-flat)'
      }}
    >
      <div style={{ padding: 'var(--space-5)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'var(--space-3)' }}>
          <h3 style={{ margin: 0, fontSize: 'var(--text-md)', fontWeight: 'var(--font-semibold)', color: 'var(--text-ink)' }}>
            {project.name || project.project_id}
          </h3>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            {project.genre && (
              <span
                style={{
                  padding: 'var(--space-1) var(--space-2)',
                  background: 'var(--paper-bg)',
                  borderRadius: 'var(--radius-full)',
                  fontSize: 'var(--text-xs)',
                  color: 'var(--text-charcoal)',
                  fontWeight: 'var(--font-medium)',
                }}
              >
                {tGenre(project.genre)}
              </span>
            )}
            <button
              onClick={handleDelete}
              style={{
                padding: 'var(--space-1) var(--space-2)',
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
                color: 'var(--text-gray)',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                fontSize: 'var(--text-xs)',
                borderRadius: 'var(--radius-sm)',
                transition: 'all var(--duration-fast) var(--ease-out)',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'var(--paper-hover)'
                e.currentTarget.style.color = 'var(--status-danger)'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'transparent'
                e.currentTarget.style.color = 'var(--text-gray)'
              }}
              title="删除项目"
            >
              <Trash2 size={14} />
            </button>
          </div>
        </div>
        {project.description && (
          <p style={{ margin: '0 0 var(--space-3) 0', fontSize: 'var(--text-sm)', color: 'var(--text-charcoal)', lineHeight: 1.5 }}>
            {project.description.length > 80 ? project.description.slice(0, 80) + '...' : project.description}
          </p>
        )}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 'var(--text-xs)', color: 'var(--text-gray)' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-1)' }}>
            <BookOpen size={14} strokeWidth={1.5} />
            {project.chapter_count} 章
          </span>
          <span>{project.created_at || '-'}</span>
        </div>
      </div>
    </Link>
  )
}

export default function Projects() {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = () => {
    setLoading(true)
    setError('')
    get<Project[]>('/projects').then((res) => {
      if (res.ok && res.data) {
        setProjects(res.data)
      } else {
        setError(res.error?.message || '获取项目列表失败')
      }
      setLoading(false)
    })
  }

  const handleDelete = async (projectId: string) => {
    const res = await del<{ deleted: boolean }>(`/projects/${projectId}`)
    if (res.ok) {
      setProjects((prev) => prev.filter((p) => p.project_id !== projectId))
    } else {
      alert(res.error?.message || '删除项目失败')
    }
  }

  useEffect(() => {
    load()
  }, [])

  if (loading) {
    return (
      <div>
        <PageHeader title="项目列表" />
        <div style={{
          background: 'var(--paper-surface)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: 'var(--shadow-flat)',
          border: '1px solid rgba(30, 58, 95, 0.06)',
          padding: 'var(--space-10)',
          textAlign: 'center',
          color: 'var(--text-charcoal)',
        }}>
          <div style={{
            width: '32px',
            height: '32px',
            border: '2px solid var(--paper-elevated)',
            borderTopColor: 'var(--ink-accent)',
            borderRadius: '50%',
            animation: 'spin 1s linear infinite',
            margin: '0 auto var(--space-3)',
          }} />
          加载中...
        </div>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    )
  }

  if (error) {
    return (
      <div>
        <PageHeader title="项目列表" />
        <ErrorState
          title="加载失败"
          message={error}
          onRetry={load}
        />
      </div>
    )
  }

  return (
    <div>
      <PageHeader
        title="项目列表"
        actions={
          <Link
            to="/onboarding"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 'var(--space-2)',
              padding: 'var(--space-2) var(--space-4)',
              background: 'var(--gradient-ink)',
              color: 'white',
              borderRadius: 'var(--radius-md)',
              fontSize: 'var(--text-base)',
              fontWeight: 'var(--font-medium)',
              textDecoration: 'none',
              transition: 'all var(--duration-fast) var(--ease-out)',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.transform = 'translateY(-1px)'
              e.currentTarget.style.boxShadow = 'var(--shadow-md)'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = ''
              e.currentTarget.style.boxShadow = ''
            }}
          >
            <Plus size={16} />
            创建项目
          </Link>
        }
      />

      {projects.length > 0 ? (
        <div
          className="projects-grid"
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
            gap: 'var(--space-4)',
          }}
        >
          {projects.map((project) => (
            <ProjectCard key={project.project_id} project={project} onDelete={handleDelete} />
          ))}
        </div>
      ) : (
        <div style={{
          background: 'var(--paper-surface)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: 'var(--shadow-flat)',
          border: '1px solid rgba(30, 58, 95, 0.06)',
          overflow: 'hidden',
        }}>
          <div style={{ padding: 'var(--space-5)' }}>
            <EmptyState
              title="暂无项目"
              hint="创建第一个小说项目开始创作"
              action={{ label: '创建项目', to: '/onboarding' }}
            />
          </div>
        </div>
      )}
    </div>
  )
}
