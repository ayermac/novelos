import {
  BookOpen,
  CheckCircle2,
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
}

const MODULE_GROUPS: ModuleGroup[] = [
  {
    label: '日常工作',
    items: [
      { key: 'overview', label: '工作台', icon: <LayoutDashboard size={16} /> },
      { key: 'chapters', label: '写章节', icon: <BookOpen size={16} /> },
      { key: 'review', label: '审核发布', icon: <CheckCircle2 size={16} /> },
      { key: 'memory', label: '记忆收纳', icon: <Database size={16} /> },
    ],
  },
  {
    label: '小说资料',
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
    label: '系统',
    items: [
      { key: 'runs', label: '运行记录', icon: <History size={16} /> },
      { key: 'settings', label: '项目设置', icon: <Settings size={16} /> },
    ],
  },
]

interface ProjectSideNavProps {
  activeModule: ProjectModule
  onModuleChange: (module: ProjectModule) => void
}

export default function ProjectSideNav({ activeModule, onModuleChange }: ProjectSideNavProps) {
  return (
    <nav className="project-side-nav" aria-label="项目模块">
      {MODULE_GROUPS.map((group) => (
        <section className="project-side-nav-group" key={group.label}>
          <div className="project-side-nav-label">{group.label}</div>
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
        </section>
      ))}
    </nav>
  )
}
