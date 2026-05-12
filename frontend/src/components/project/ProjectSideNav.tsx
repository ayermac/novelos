import {
  BookOpen,
  CheckCircle2,
  ChevronDown,
  Database,
  FileText,
  Globe,
  History,
  LayoutDashboard,
  ListTree,
  Palette,
  ScrollText,
  Settings,
  Sparkles,
  Swords,
  Users,
} from 'lucide-react'
import { useState } from 'react'
import type { ReactNode } from 'react'
import type { ProjectModule } from './ProjectModuleNav'

interface ModuleItem {
  key: ProjectModule
  label: string
  icon: ReactNode
}

interface ModuleGroup {
  label: string
  items: ModuleItem[]
  collapsible?: boolean
  defaultCollapsed?: boolean
}

const MODULE_GROUPS: ModuleGroup[] = [
  {
    label: '作者任务',
    items: [
      { key: 'overview', label: '工作台', icon: <LayoutDashboard size={16} /> },
      { key: 'chapters', label: '写章节', icon: <BookOpen size={16} /> },
      { key: 'review', label: '审稿发布', icon: <CheckCircle2 size={16} /> },
      { key: 'memory', label: '记忆收件箱', icon: <Database size={16} /> },
    ],
  },
  {
    label: '小说设定',
    items: [
      { key: 'genesis', label: '创世设定', icon: <Sparkles size={16} /> },
      { key: 'outline', label: '大纲篇章', icon: <ListTree size={16} /> },
      { key: 'instructions', label: '章节指令', icon: <FileText size={16} /> },
      { key: 'characters', label: '人物', icon: <Users size={16} /> },
      { key: 'factions', label: '势力', icon: <Swords size={16} /> },
      { key: 'worldview', label: '世界资料', icon: <Globe size={16} /> },
      { key: 'plots', label: '伏笔', icon: <Sparkles size={16} /> },
      { key: 'facts', label: '事实账本', icon: <ScrollText size={16} /> },
      { key: 'style', label: '风格规范', icon: <Palette size={16} /> },
    ],
  },
  {
    label: '系统状态',
    collapsible: true,
    defaultCollapsed: true,
    items: [
      { key: 'runs', label: '运行记录', icon: <History size={16} /> },
      { key: 'settings', label: '项目设置', icon: <Settings size={16} /> },
    ],
  },
]

interface ProjectSideNavProps {
  activeModule: ProjectModule
  onModuleChange: (module: ProjectModule) => void
  compact?: boolean
}

export default function ProjectSideNav({ activeModule, onModuleChange, compact }: ProjectSideNavProps) {
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(() => {
    const initial = new Set<string>()
    for (const group of MODULE_GROUPS) {
      if (group.collapsible && group.defaultCollapsed) {
        initial.add(group.label)
      }
    }
    return initial
  })

  const toggleGroup = (label: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev)
      if (next.has(label)) next.delete(label)
      else next.add(label)
      return next
    })
  }

  const isGroupActive = (group: ModuleGroup) =>
    group.items.some((item) => item.key === activeModule)

  return (
    <nav className={`project-side-nav${compact ? ' project-side-nav--compact' : ''}`} aria-label="项目导航">
      {compact && (
        <div className="project-side-nav-compact-header">
          <button
            type="button"
            className={`project-side-nav-item${activeModule === 'chapters' || activeModule === 'overview' ? ' active' : ''}`}
            onClick={() => onModuleChange('chapters')}
            title="工作台"
          >
            <LayoutDashboard size={16} />
            <span>工作台</span>
          </button>
        </div>
      )}
      {MODULE_GROUPS.map((group) => {
        const collapsed = collapsedGroups.has(group.label) && !isGroupActive(group)
        return (
          <section className="project-side-nav-group" key={group.label}>
            <div
              className={`project-side-nav-label${group.collapsible ? ' collapsible' : ''}`}
              onClick={group.collapsible ? () => toggleGroup(group.label) : undefined}
              role={group.collapsible ? 'button' : undefined}
              tabIndex={group.collapsible ? 0 : undefined}
              onKeyDown={group.collapsible ? (e) => { if (e.key === 'Enter' || e.key === ' ') toggleGroup(group.label) } : undefined}
            >
              <span>{group.label}</span>
              {group.collapsible && (
                <ChevronDown
                  size={12}
                  style={{
                    transform: collapsed ? 'rotate(-90deg)' : 'rotate(0)',
                    transition: 'transform 0.15s',
                  }}
                />
              )}
            </div>
            {!collapsed && (
              <div className="project-side-nav-items">
                {group.items.map((item) => (
                  <button
                    type="button"
                    key={item.key}
                    className={`project-side-nav-item${activeModule === item.key ? ' active' : ''}`}
                    onClick={() => onModuleChange(item.key)}
                  >
                    {item.icon}
                    <span>{item.label}</span>
                  </button>
                ))}
              </div>
            )}
          </section>
        )
      })}
      {compact && (
        <style>{`
          .project-side-nav--compact {
            width: 56px !important;
            padding: 8px 4px !important;
          }
          .project-side-nav--compact .project-side-nav-group {
            display: none;
          }
          .project-side-nav--compact .project-side-nav-compact-header {
            display: flex;
            flex-direction: column;
            gap: 4px;
          }
          .project-side-nav--compact .project-side-nav-item {
            padding: 8px;
            justify-content: center;
          }
          .project-side-nav--compact .project-side-nav-item span {
            display: none;
          }
          @media (max-width: 768px) {
            .project-side-nav--compact {
              width: 100% !important;
              flex-direction: row;
              padding: 8px 12px !important;
            }
            .project-side-nav--compact .project-side-nav-compact-header {
              flex-direction: row;
            }
            .project-side-nav--compact .project-side-nav-item span {
              display: inline;
            }
          }
        `}</style>
      )}
    </nav>
  )
}
