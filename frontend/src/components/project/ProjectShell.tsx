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
  const isWorkbench = activeModule === 'chapters' || activeModule === 'overview'

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
        {/* v5.6: Side nav becomes a compact secondary panel when workbench is active */}
        <ProjectSideNav
          activeModule={activeModule}
          onModuleChange={onModuleChange}
          compact={isWorkbench}
        />
        <main className="project-shell-main">
          {children}
        </main>
      </div>
    </div>
  )
}
