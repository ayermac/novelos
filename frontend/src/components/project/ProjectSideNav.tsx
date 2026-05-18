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

const NAV_COLLAPSED_STORAGE_KEY = 'novelos.projectSideNav.collapsed'

interface ProjectSideNavProps {
  activeModule: ProjectModule
  onModuleChange: (module: ProjectModule) => void
  compact?: boolean
}

export default function ProjectSideNav({ activeModule, onModuleChange, compact }: ProjectSideNavProps) {
  const [navCollapsed, setNavCollapsed] = useState(() => {
    if (!compact) return false
    try {
      const saved = window.localStorage.getItem(NAV_COLLAPSED_STORAGE_KEY)
      if (saved === '0') return false
      if (saved === '1') return true
    } catch {
      // Ignore storage failures; the menu still works for the current session.
    }
    return true
  })
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

  useEffect(() => {
    if (!compact) return
    try {
      window.localStorage.setItem(NAV_COLLAPSED_STORAGE_KEY, navCollapsed ? '1' : '0')
    } catch {
      // Ignore storage failures.
    }
  }, [compact, navCollapsed])

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
          title={navCollapsed ? '项目菜单' : undefined}
          data-tooltip={navCollapsed ? '项目菜单' : undefined}
        >
          <Menu size={16} />
          <span className="project-side-nav-toggle-label">项目菜单</span>
          {navCollapsed && <span className="project-side-nav-tooltip" aria-hidden="true">项目菜单</span>}
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
                    data-tooltip={navCollapsed ? item.label : undefined}
                  >
                    {item.icon}
                    <span className="project-side-nav-item-label">{item.label}</span>
                    {navCollapsed && <span className="project-side-nav-tooltip" aria-hidden="true">{item.label}</span>}
                  </button>
                ))}
              </div>
            )}
          </section>
        )
      })}
      <style>{`
        .project-side-nav {
          width: 224px;
          flex-shrink: 0;
          overflow-y: auto;
          padding: 12px 10px;
          border-right: 1px solid var(--border-color);
          background: var(--sidebar-bg, var(--bg-primary));
          transition: width 0.18s ease, padding 0.18s ease;
        }
        .project-side-nav--compact {
          width: 224px;
          padding: 12px 10px;
        }
        .project-side-nav--collapsed {
          width: 56px;
          padding: 12px 8px;
          overflow: visible;
        }
        .project-side-nav-top {
          margin-bottom: 12px;
        }
        .project-side-nav-toggle {
          display: flex;
          align-items: center;
          justify-content: flex-start;
          gap: 8px;
          width: 100%;
          min-height: 34px;
          padding: 0 10px;
          border: 1px solid var(--border-color);
          border-radius: 6px;
          background: var(--bg-primary);
          color: var(--text-secondary);
          cursor: pointer;
          font-size: 12px;
          font-weight: 680;
          box-shadow: none;
          transition: background 0.12s ease, border-color 0.12s ease, color 0.12s ease;
        }
        .project-side-nav-toggle:hover,
        .project-side-nav-toggle:focus-visible {
          background: var(--bg-tertiary);
          border-color: var(--border-strong);
          color: var(--primary);
          outline: none;
        }
        .project-side-nav--collapsed .project-side-nav-toggle {
          justify-content: center;
          padding: 0;
        }
        .project-side-nav--collapsed .project-side-nav-toggle-label {
          display: none;
        }
        .project-side-nav-group + .project-side-nav-group {
          margin-top: 16px;
        }
        .project-side-nav--collapsed .project-side-nav-group + .project-side-nav-group {
          margin-top: 7px;
        }
        .project-side-nav-label {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 6px;
          padding: 0 8px 7px;
          font-size: 11px;
          font-weight: 720;
          color: var(--text-muted);
          text-transform: uppercase;
          letter-spacing: 0.04em;
        }
        .project-side-nav-label.collapsible {
          cursor: pointer;
          border-radius: 6px;
        }
        .project-side-nav-label.collapsible:hover {
          color: var(--text-secondary);
          background: var(--bg-tertiary);
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
          gap: 4px;
        }
        .project-side-nav--collapsed .project-side-nav-items {
          gap: 4px;
        }
        .project-side-nav-item {
          display: flex;
          align-items: center;
          gap: 9px;
          width: 100%;
          min-height: 36px;
          padding: 0 9px;
          border: 1px solid transparent;
          border-radius: 6px;
          background: transparent;
          color: var(--text-secondary);
          cursor: pointer;
          font-size: 12px;
          text-align: left;
          transition: background 0.12s ease, border-color 0.12s ease, color 0.12s ease;
        }
        .project-side-nav--collapsed .project-side-nav-item {
          justify-content: center;
          min-height: 38px;
          padding: 0;
          gap: 0;
          position: relative;
        }
        .project-side-nav--collapsed .project-side-nav-toggle {
          position: relative;
        }
        .project-side-nav-tooltip {
          display: none;
          position: absolute;
          top: 50%;
          left: 44px;
          transform: translateY(-50%);
          z-index: 500;
          min-width: max-content;
          max-width: 180px;
          padding: 6px 9px;
          border: 1px solid var(--border-color);
          border-radius: 4px;
          background: var(--tooltip-bg);
          color: var(--tooltip-text);
          box-shadow: var(--shadow-md);
          font-size: 12px;
          font-weight: 620;
          line-height: 1;
          opacity: 0;
          pointer-events: none;
          transition: opacity 0.12s ease;
        }
        .project-side-nav--collapsed .project-side-nav-item:hover .project-side-nav-tooltip,
        .project-side-nav--collapsed .project-side-nav-item:focus .project-side-nav-tooltip,
        .project-side-nav--collapsed .project-side-nav-item:focus-visible .project-side-nav-tooltip,
        .project-side-nav--collapsed .project-side-nav-toggle:hover .project-side-nav-tooltip,
        .project-side-nav--collapsed .project-side-nav-toggle:focus .project-side-nav-tooltip,
        .project-side-nav--collapsed .project-side-nav-toggle:focus-visible .project-side-nav-tooltip {
          display: block;
          opacity: 1;
        }
        .project-side-nav-item:hover {
          background: var(--bg-tertiary);
          color: var(--text-primary);
        }
        .project-side-nav-item.active {
          background: var(--accent-soft);
          border-color: var(--accent-border);
          color: var(--primary);
          font-weight: 680;
        }
        .project-side-nav-item svg {
          flex-shrink: 0;
        }
        .project-side-nav-item-label {
          min-width: 0;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .project-side-nav--collapsed .project-side-nav-item-label {
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
