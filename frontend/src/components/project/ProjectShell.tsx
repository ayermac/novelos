import type { ReactNode } from 'react'
import type { ProjectModule } from './ProjectModuleNav'
import ProjectHeader from './ProjectHeader'
import ProjectSideNav from './ProjectSideNav'

interface ProjectShellProps {
  activeModule: ProjectModule
  currentChapter: number
  projectId: string
  projectName: string
  publishedCount: number
  isStub: boolean
  onModuleChange: (module: ProjectModule) => void
  children: ReactNode
}

export default function ProjectShell({
  activeModule,
  currentChapter,
  projectId,
  projectName,
  publishedCount,
  isStub,
  onModuleChange,
  children,
}: ProjectShellProps) {
  return (
    <div className="project-shell">
      <ProjectHeader
        projectId={projectId}
        projectName={projectName}
        currentChapter={currentChapter}
        publishedCount={publishedCount}
        isStub={isStub}
      />
      <div className="project-shell-body">
        {/* v5.8: Side nav is consistently compact and user-expandable across project modules. */}
        <ProjectSideNav
          activeModule={activeModule}
          onModuleChange={onModuleChange}
          compact
        />
        <main className="project-shell-main">
          {children}
        </main>
      </div>
    </div>
  )
}
