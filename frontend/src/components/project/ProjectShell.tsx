import type { ReactNode } from 'react'
import type { ProjectModule } from './ProjectModuleNav'
import ProjectHeader from './ProjectHeader'
import ProjectSideNav from './ProjectSideNav'

interface ProjectShellProps {
  activeModule: ProjectModule
  currentChapter: number
  projectName: string
  publishedCount: number
  isStub: boolean
  onModuleChange: (module: ProjectModule) => void
  children: ReactNode
}

export default function ProjectShell({
  activeModule,
  currentChapter,
  projectName,
  publishedCount,
  isStub,
  onModuleChange,
  children,
}: ProjectShellProps) {
  return (
    <div className="project-shell">
      <ProjectHeader
        projectName={projectName}
        currentChapter={currentChapter}
        publishedCount={publishedCount}
        isStub={isStub}
      />
      <div className="project-shell-body">
        <ProjectSideNav activeModule={activeModule} onModuleChange={onModuleChange} />
        <main className="project-shell-main">
          {children}
        </main>
      </div>
    </div>
  )
}
