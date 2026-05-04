import { Link } from 'react-router-dom'

interface ProjectHeaderProps {
  projectName: string
  currentChapter: number
  publishedCount: number
  isStub: boolean
}

export default function ProjectHeader({
  projectName,
  currentChapter,
  publishedCount,
  isStub,
}: ProjectHeaderProps) {
  return (
    <header className="project-header">
      <div className="project-header-main">
        <Link to="/projects" className="project-header-back">
          返回项目列表
        </Link>
        <div>
          <h1>{projectName}</h1>
          <div className="project-header-meta">
            <span>第 {currentChapter} 章</span>
            <span>已发布 {publishedCount} 章</span>
          </div>
        </div>
      </div>
      <span className={`status-badge ${isStub ? 'status-stub' : 'status-real'}`}>
        {isStub ? '演示模式' : '真实 LLM'}
      </span>
    </header>
  )
}
