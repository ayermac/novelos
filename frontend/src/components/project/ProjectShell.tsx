import type { ReactNode } from 'react'
import type { ProjectModule } from './ProjectModuleNav'
import ProjectHeader from './ProjectHeader'
import ProjectSideNav from './ProjectSideNav'

interface ProjectShellProps {
  activeModule: ProjectModule
  projectId: string
  projectName: string
  isStub: boolean
  onModuleChange: (module: ProjectModule) => void
  children: ReactNode
}

export default function ProjectShell({
  activeModule,
  projectId,
  projectName,
  isStub,
  onModuleChange,
  children,
}: ProjectShellProps) {
  return (
    <div className="project-shell">
      <ProjectHeader
        projectId={projectId}
        projectName={projectName}
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
