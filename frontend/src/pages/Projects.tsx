import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
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
        <div className="card">
          <div className="card-body">
            <div style={{ overflowX: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>项目 ID</th>
                    <th>名称</th>
                    <th>类型</th>
                    <th>章节数</th>
                    <th>创建时间</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {projects.map((project) => (
                    <tr key={project.project_id}>
                      <td>{project.project_id}</td>
                      <td>{project.name}</td>
                      <td>{tGenre(project.genre)}</td>
                      <td>{project.chapter_count}</td>
                      <td className="text-secondary">{project.created_at}</td>
                      <td>
                        <Link
                          to={`/projects/${project.project_id}`}
                          className="btn btn-sm btn-secondary"
                        >
                          查看工作台
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
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
