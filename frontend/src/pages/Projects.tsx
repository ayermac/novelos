import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { get } from '../lib/api'

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

  useEffect(() => {
    get<Project[]>('/projects').then((res) => {
      if (res.ok && res.data) {
        setProjects(res.data)
      }
      setLoading(false)
    })
  }, [])

  if (loading) {
    return <div>加载中...</div>
  }

  return (
    <div>
      <div className="flex justify-between items-center" style={{ marginBottom: '24px' }}>
        <h2>项目列表</h2>
        <Link to="/onboarding" className="btn btn-primary">
          创建项目
        </Link>
      </div>

      {projects.length > 0 ? (
        <div className="card">
          <div className="card-body">
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
                    <td>{project.genre || '-'}</td>
                    <td>{project.chapter_count}</td>
                    <td className="text-secondary">{project.created_at}</td>
                    <td>
                      <Link
                        to={`/projects/${project.project_id}`}
                        className="btn btn-sm btn-secondary"
                      >
                        查看
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="card">
          <div className="card-body">
            <div className="empty-state">
              <div className="empty-title">暂无项目</div>
              <div className="empty-hint">创建第一个小说项目开始创作</div>
              <div className="flex gap-2 mt-3" style={{ justifyContent: 'center' }}>
                <Link to="/onboarding" className="btn btn-primary">
                  创建项目
                </Link>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
