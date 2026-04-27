import { useEffect, useState } from 'react'
import { Outlet, NavLink } from 'react-router-dom'
import { Book, FolderPlus, Play, CheckSquare, Palette, Settings, LayoutDashboard, FolderOpen, LucideIcon } from 'lucide-react'
import { get } from '../lib/api'

interface NavItem {
  to: string
  label: string
  icon: LucideIcon | null
  isSectionLabel?: boolean
}

const navItems: NavItem[] = [
  { to: '', label: '创作', icon: null, isSectionLabel: true },
  { to: '/', label: '创作中心', icon: LayoutDashboard },
  { to: '/projects', label: '项目', icon: FolderOpen },
  { to: '/onboarding', label: '创建项目', icon: FolderPlus },
  { to: '', label: '工具', icon: null, isSectionLabel: true },
  { to: '/review', label: '审核', icon: CheckSquare },
  { to: '/style', label: '风格', icon: Palette },
  { to: '/settings', label: '配置', icon: Settings },
  { to: '', label: '开发', icon: null, isSectionLabel: true },
  { to: '/run', label: '高级运行', icon: Play },
]

export default function Layout() {
  const [llmMode, setLlmMode] = useState<string>('stub')

  useEffect(() => {
    // Fetch LLM mode from health endpoint
    get<{ llm_mode: string }>('/health')
      .then((res) => {
        if (res.ok && res.data) {
          setLlmMode(res.data.llm_mode)
        }
      })
      .catch(() => {
        // Default to stub on error
      })
  }, [])

  const isStub = llmMode === 'stub'

  return (
    <div className="app-layout">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-brand">
          <Book size={20} />
          <span>小说工厂</span>
          <span className="version">v5.1.5</span>
        </div>

        <nav className="sidebar-nav">
          {navItems.map((item, index) => {
            if (item.isSectionLabel) {
              return (
                <div
                  key={`section-${index}`}
                  style={{
                    fontSize: '11px',
                    color: 'var(--text-muted)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                    marginTop: index === 0 ? '0' : '16px',
                    marginBottom: '4px',
                    padding: '0 12px',
                  }}
                >
                  {item.label}
                </div>
              )
            }
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) => (isActive ? 'active' : '')}
              >
                {item.icon && <item.icon size={18} />}
                {item.label}
              </NavLink>
            )
          })}
        </nav>

        <div className="sidebar-footer">作者工作台</div>
      </aside>

      {/* Main Area */}
      <div className="main-area">
        <header className="topbar">
          <div className="topbar-left">
            <span className="topbar-title">作者工作台</span>
          </div>
          <div className="topbar-right">
            {isStub ? (
              <span className="status-badge status-stub" title="不调用真实 LLM，内容由本地 Stub 模板生成">
                演示模式
              </span>
            ) : (
              <span className="status-badge status-real" title="调用真实 LLM API 生成内容">
                真实模式
              </span>
            )}
          </div>
        </header>

        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
