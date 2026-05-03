import {
  LayoutDashboard, BookOpen, Globe, Users, Swords, ListTree,
  Sparkles, FileText, Palette, CheckCircle2, History, Settings,
  Database, ScrollText,
} from 'lucide-react'

export type ProjectModule =
  | 'overview' | 'chapters' | 'worldview' | 'characters'
  | 'factions' | 'outline' | 'plots' | 'instructions'
  | 'style' | 'review' | 'runs' | 'settings' | 'genesis'
  | 'memory' | 'facts'

interface ModuleTab {
  key: ProjectModule
  label: string
  icon: React.ReactNode
}

const MODULE_TABS: ModuleTab[] = [
  { key: 'overview', label: '总览', icon: <LayoutDashboard size={16} /> },
  { key: 'genesis', label: '创世', icon: <Sparkles size={16} /> },
  { key: 'chapters', label: '章节', icon: <BookOpen size={16} /> },
  { key: 'worldview', label: '世界观', icon: <Globe size={16} /> },
  { key: 'characters', label: '角色', icon: <Users size={16} /> },
  { key: 'factions', label: '势力', icon: <Swords size={16} /> },
  { key: 'outline', label: '大纲', icon: <ListTree size={16} /> },
  { key: 'plots', label: '伏笔', icon: <Sparkles size={16} /> },
  { key: 'instructions', label: '章节指令', icon: <FileText size={16} /> },
  { key: 'memory', label: '记忆更新', icon: <Database size={16} /> },
  { key: 'facts', label: '事实账本', icon: <ScrollText size={16} /> },
  { key: 'style', label: '风格指南', icon: <Palette size={16} /> },
  { key: 'review', label: '审核', icon: <CheckCircle2 size={16} /> },
  { key: 'runs', label: '运行记录', icon: <History size={16} /> },
  { key: 'settings', label: '设置', icon: <Settings size={16} /> },
]

interface ProjectModuleNavProps {
  activeModule: ProjectModule
  onModuleChange: (module: ProjectModule) => void
}

export default function ProjectModuleNav({ activeModule, onModuleChange }: ProjectModuleNavProps) {
  return (
    <nav className="project-module-nav">
      {MODULE_TABS.map((tab) => (
        <button
          key={tab.key}
          className={`module-tab${activeModule === tab.key ? ' active' : ''}`}
          onClick={() => onModuleChange(tab.key)}
          type="button"
        >
          {tab.icon}
          <span>{tab.label}</span>
        </button>
      ))}
      <style>{`
        .project-module-nav {
          display: flex;
          gap: 2px;
          padding: 0 16px;
          border-bottom: 1px solid var(--border, #e5e7eb);
          overflow-x: auto;
          scrollbar-width: none;
          max-width: 100vw;
          box-sizing: border-box;
        }
        .project-module-nav::-webkit-scrollbar { display: none; }
        .module-tab {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 10px 14px;
          border: none;
          background: none;
          cursor: pointer;
          font-size: 13px;
          color: var(--text-secondary, #6b7280);
          white-space: nowrap;
          border-bottom: 2px solid transparent;
          transition: color 0.15s, border-color 0.15s;
        }
        .module-tab:hover {
          color: var(--text-primary, #111827);
          background: var(--bg-hover, #f9fafb);
        }
        .module-tab.active {
          color: var(--accent, #2563eb);
          border-bottom-color: var(--accent, #2563eb);
          font-weight: 500;
        }
      `}</style>
    </nav>
  )
}
