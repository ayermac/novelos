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
  Menu,
  Palette,
  ScrollText,
  Settings,
  Sparkles,
  Swords,
  Users,
} from 'lucide-react'
import { useEffect, useState } from 'react'
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
    collapsible: true,
    items: [
      { key: 'overview', label: '工作台', icon: <LayoutDashboard size={16} /> },
      { key: 'chapters', label: '写章节', icon: <BookOpen size={16} /> },
      { key: 'review', label: '审稿发布', icon: <CheckCircle2 size={16} /> },
      { key: 'memory', label: '记忆收件箱', icon: <Database size={16} /> },
    ],
  },
  {
    label: '小说设定',
    collapsible: true,
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
  const [navCollapsed, setNavCollapsed] = useState(Boolean(compact))
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(() => {
    const initial = new Set<string>()
    for (const group of MODULE_GROUPS) {
      if (group.collapsible && group.defaultCollapsed) {
        initial.add(group.label)
      }
    }
    return initial
  })

  useEffect(() => {
    if (!compact) setNavCollapsed(false)
  }, [compact])

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
    <nav
      className={`project-side-nav${compact ? ' project-side-nav--compact' : ''}${navCollapsed ? ' project-side-nav--collapsed' : ''}`}
      aria-label="项目导航"
    >
      <div className="project-side-nav-top">
        <button
          type="button"
          className="project-side-nav-toggle"
          onClick={() => setNavCollapsed((value) => !value)}
          aria-label={navCollapsed ? '展开项目菜单' : '收起项目菜单'}
          aria-expanded={!navCollapsed}
        >
          <Menu size={16} />
          <span>项目菜单</span>
        </button>
      </div>
      {MODULE_GROUPS.map((group) => {
        const collapsed = !navCollapsed && collapsedGroups.has(group.label) && !isGroupActive(group)
        return (
          <section className="project-side-nav-group" key={group.label}>
            {!navCollapsed && (
              <div
                className={`project-side-nav-label${group.collapsible ? ' collapsible' : ''}`}
                onClick={group.collapsible ? () => toggleGroup(group.label) : undefined}
                role={group.collapsible ? 'button' : undefined}
                tabIndex={group.collapsible ? 0 : undefined}
                aria-expanded={group.collapsible ? !collapsed : undefined}
                onKeyDown={group.collapsible ? (e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    toggleGroup(group.label)
                  }
                } : undefined}
              >
                <span>{group.label}</span>
                {group.collapsible && (
                  <ChevronDown
                    size={12}
                    className={`project-side-nav-chevron${collapsed ? ' collapsed' : ''}`}
                  />
                )}
              </div>
            )}
            {!collapsed && (
              <div className="project-side-nav-items">
                {group.items.map((item) => (
                  <button
                    type="button"
                    key={item.key}
                    className={`project-side-nav-item${activeModule === item.key ? ' active' : ''}`}
                    onClick={() => onModuleChange(item.key)}
                    aria-label={navCollapsed ? item.label : undefined}
                    title={navCollapsed ? item.label : undefined}
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
      <style>{`
        .project-side-nav {
          width: 206px;
          flex-shrink: 0;
          overflow-y: auto;
          padding: 10px;
          border-right: 1px solid var(--border-color, #e2e8f0);
          background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
          transition: width 0.18s ease, padding 0.18s ease;
        }
        .project-side-nav--compact {
          width: 188px;
          padding: 10px 8px;
        }
        .project-side-nav--collapsed {
          width: 58px;
          padding: 10px 7px;
        }
        .project-side-nav-top {
          margin-bottom: 10px;
        }
        .project-side-nav-toggle {
          display: flex;
          align-items: center;
          justify-content: flex-start;
          gap: 8px;
          width: 100%;
          min-height: 36px;
          padding: 0 9px;
          border: 1px solid var(--border-color, #e2e8f0);
          border-radius: 8px;
          background: #fff;
          color: var(--text-secondary, #64748b);
          cursor: pointer;
          font-size: 13px;
          font-weight: 600;
          box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
          transition: background 0.12s ease, border-color 0.12s ease, color 0.12s ease;
        }
        .project-side-nav-toggle:hover,
        .project-side-nav-toggle:focus-visible {
          background: var(--bg-secondary, #f6f8fb);
          border-color: rgba(15, 118, 110, 0.22);
          color: var(--primary, #0f766e);
          outline: none;
        }
        .project-side-nav--collapsed .project-side-nav-toggle {
          justify-content: center;
          padding: 0;
        }
        .project-side-nav--collapsed .project-side-nav-toggle span {
          display: none;
        }
        .project-side-nav-group + .project-side-nav-group {
          margin-top: 14px;
        }
        .project-side-nav--collapsed .project-side-nav-group + .project-side-nav-group {
          margin-top: 6px;
        }
        .project-side-nav-label {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 6px;
          padding: 0 8px 6px;
          font-size: 12px;
          font-weight: 600;
          color: var(--text-muted, #94a3b8);
        }
        .project-side-nav-label.collapsible {
          cursor: pointer;
          border-radius: 6px;
        }
        .project-side-nav-label.collapsible:hover {
          color: var(--text-secondary, #64748b);
          background: var(--bg-secondary, #f6f8fb);
        }
        .project-side-nav-chevron {
          transition: transform 0.15s ease;
        }
        .project-side-nav-chevron.collapsed {
          transform: rotate(-90deg);
        }
        .project-side-nav-items {
          display: flex;
          flex-direction: column;
          gap: 3px;
        }
        .project-side-nav--collapsed .project-side-nav-items {
          gap: 4px;
        }
        .project-side-nav-item {
          display: flex;
          align-items: center;
          gap: 8px;
          width: 100%;
          min-height: 34px;
          padding: 7px 8px;
          border: 1px solid transparent;
          border-radius: 7px;
          background: transparent;
          color: var(--text-secondary, #64748b);
          cursor: pointer;
          font-size: 13px;
          text-align: left;
          transition: background 0.12s ease, border-color 0.12s ease, color 0.12s ease;
        }
        .project-side-nav--collapsed .project-side-nav-item {
          justify-content: center;
          min-height: 40px;
          padding: 0;
          gap: 0;
        }
        .project-side-nav-item:hover {
          background: var(--bg-secondary, #f6f8fb);
          color: var(--text-primary, #0f172a);
        }
        .project-side-nav-item.active {
          background: rgba(15, 118, 110, 0.09);
          border-color: rgba(15, 118, 110, 0.16);
          color: var(--primary, #0f766e);
          font-weight: 600;
        }
        .project-side-nav-item svg {
          flex-shrink: 0;
        }
        .project-side-nav-item span {
          min-width: 0;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .project-side-nav--collapsed .project-side-nav-item span {
          display: none;
        }
        @media (max-width: 768px) {
          .project-side-nav,
          .project-side-nav--compact {
            width: 100%;
            max-height: 180px;
            padding: 8px 12px;
            border-right: none;
            border-bottom: 1px solid var(--border-color, #e2e8f0);
          }
          .project-side-nav-group + .project-side-nav-group {
            margin-top: 8px;
          }
          .project-side-nav-items {
            flex-direction: row;
            overflow-x: auto;
            padding-bottom: 2px;
          }
          .project-side-nav-item {
            width: auto;
            flex-shrink: 0;
          }
          .project-side-nav--collapsed {
            width: 100%;
            max-height: 72px;
            padding: 8px 12px;
          }
          .project-side-nav--collapsed .project-side-nav-top {
            margin-bottom: 6px;
          }
          .project-side-nav--collapsed .project-side-nav-items {
            flex-direction: row;
            overflow-x: auto;
          }
        }
      `}</style>
    </nav>
  )
}
