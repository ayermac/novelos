import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { BookOpen } from 'lucide-react'
import { get } from '../lib/api'
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

function ProjectCard({ project }: { project: Project }) {
  return (
    <Link
      to={`/projects/${project.project_id}`}
      className="card project-card"
      style={{
        textDecoration: 'none',
        transition: 'transform 0.15s, box-shadow 0.15s',
      }}
    >
      <div className="card-body" style={{ padding: '20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
          <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)' }}>
            {project.name || project.project_id}
          </h3>
          {project.genre && (
            <span
              style={{
                padding: '2px 8px',
                background: 'var(--bg-tertiary)',
                borderRadius: '4px',
                fontSize: '12px',
                color: 'var(--text-secondary)',
              }}
            >
              {tGenre(project.genre)}
            </span>
          )}
        </div>
        {project.description && (
          <p style={{ margin: '0 0 12px 0', fontSize: '13px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            {project.description.length > 80 ? project.description.slice(0, 80) + '...' : project.description}
          </p>
        )}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px', color: 'var(--text-muted)' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
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

  useEffect(() => {
    load()
  }, [])

  if (loading) {
    return <div><PageHeader title="项目列表" /><div className="card"><div className="card-body" style={{ textAlign: 'center', padding: '40px' }}>加载中...</div></div></div>
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
          <Link to="/onboarding" className="btn btn-primary">
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
            gap: '16px',
          }}
        >
          {projects.map((project) => (
            <ProjectCard key={project.project_id} project={project} />
          ))}
        </div>
      ) : (
        <div className="card">
          <div className="card-body">
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
