import { ArchitectureDiagnosisPanel } from './ArchitectureDiagnosisPanel'
import { BudgetMonitorPanel } from './BudgetMonitorPanel'
import { SteerPanel } from './SteerPanel'

interface ArchitecturePanelProps {
  projectId: string
  isRunning?: boolean
  onSteerSubmitted?: () => void
}

/**
 * ArchitecturePanel — v6.10.13 architecture hardening components.
 *
 * Combines diagnosis, budget monitoring, and user intervention panels.
 */
export function ArchitecturePanel({
  projectId,
  isRunning = false,
  onSteerSubmitted,
}: ArchitecturePanelProps) {
  return (
    <div className="space-y-4">
      {/* Diagnosis */}
      <ArchitectureDiagnosisPanel projectId={projectId} />

      {/* Budget */}
      <BudgetMonitorPanel projectId={projectId} />

      {/* Steer */}
      <SteerPanel
        projectId={projectId}
        isRunning={isRunning}
        onSteerSubmitted={onSteerSubmitted}
      />
    </div>
  )
}
