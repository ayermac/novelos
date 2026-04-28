import { useEffect, useState } from 'react'
import { Outlet, NavLink, useLocation } from 'react-router-dom'
import { FolderPlus, Play, CheckSquare, Palette, Settings, LayoutDashboard, FolderOpen, LucideIcon, Feather, Menu, X } from 'lucide-react'
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
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const location = useLocation()

  useEffect(() => {
    get<{ llm_mode: string }>('/health')
      .then((res) => {
        if (res.ok && res.data) {
          setLlmMode(res.data.llm_mode)
        }
      })
      .catch(() => {})
  }, [])

  const isStub = llmMode === 'stub'

  useEffect(() => {
    setSidebarOpen(false)
  }, [location.pathname])

  return (
    <div className="app-layout">
      {/* Mobile Toggle */}
      <button
        className="mobile-toggle"
        onClick={() => setSidebarOpen(!sidebarOpen)}
        aria-label={sidebarOpen ? '关闭菜单' : '打开菜单'}
      >
        {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
      </button>

      {sidebarOpen && <div className="sidebar-overlay" onClick={() => setSidebarOpen(false)} />}

      <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
        <div className="sidebar-brand">
          <div className="brand-icon">
            <Feather size={22} />
          </div>
          <div className="brand-text">
            <span className="brand-name">墨流</span>
            <span className="brand-tagline">小说创作工作台</span>
          </div>
          <span className="version">v5.3</span>
        </div>

        <nav className="sidebar-nav">
          {navItems.map((item, index) => {
            if (item.isSectionLabel) {
              return (
                <div key={`section-${index}`} className="nav-section">
                  {item.label}
                </div>
              )
            }
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
              >
                {({ isActive }) => (
                  <>
                    {item.icon && <item.icon size={18} />}
                    <span>{item.label}</span>
                    {isActive && <div className="nav-indicator" />}
                  </>
                )}
              </NavLink>
            )
          })}
        </nav>

        <div className="sidebar-footer">
          <div className="status-indicator">
            <div className={`mode-dot ${isStub ? 'stub' : 'real'}`} />
            <span>{isStub ? '演示模式' : '真实 LLM'}</span>
          </div>
        </div>
      </aside>

      <div className="main-area">
        <header className="topbar">
          <div className="topbar-gradient" />
          <div className="topbar-content">
            <div className="topbar-left">
              <span className="topbar-title">创作中心</span>
            </div>
            <div className="topbar-right">
              {isStub ? (
                <span className="badge badge-warning">
                  <span className="badge-dot" />
                  演示模式
                </span>
              ) : (
                <span className="badge badge-success">
                  <span className="badge-dot" />
                  真实模式
                </span>
              )}
            </div>
          </div>
        </header>

        <main className="content">
          <Outlet />
        </main>
      </div>

      <style>{`
        .app-layout {
          display: flex;
          min-height: 100vh;
          background: var(--paper-bg);
        }

        .sidebar {
          width: var(--sidebar-width);
          background: var(--paper-surface);
          border-right: 1px solid rgba(30, 58, 95, 0.06);
          display: flex;
          flex-direction: column;
          position: fixed;
          left: 0;
          top: 0;
          bottom: 0;
          z-index: 200;
          transition: transform var(--duration-slow) var(--ease-out);
        }

        .sidebar-brand {
          padding: var(--space-5) var(--space-5) var(--space-4);
          display: flex;
          align-items: center;
          gap: var(--space-3);
          border-bottom: 1px solid rgba(30, 58, 95, 0.04);
        }

        .brand-icon {
          width: 40px;
          height: 40px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: var(--gradient-ink);
          border-radius: var(--radius-lg);
          color: white;
        }

        .brand-text {
          display: flex;
          flex-direction: column;
          flex: 1;
        }

        .brand-name {
          font-family: var(--font-brand);
          font-size: var(--text-lg);
          font-weight: var(--font-bold);
          color: var(--text-ink);
          letter-spacing: -0.02em;
        }

        .brand-tagline {
          font-size: var(--text-xs);
          color: var(--text-gray);
          margin-top: 2px;
        }

        .version {
          font-size: var(--text-xs);
          color: var(--text-muted);
          background: var(--paper-elevated);
          padding: 2px 8px;
          border-radius: var(--radius-full);
        }

        .sidebar-nav {
          flex: 1;
          padding: var(--space-4) var(--space-3);
          overflow-y: auto;
        }

        .nav-section {
          font-size: 11px;
          font-weight: var(--font-semibold);
          color: var(--text-gray);
          text-transform: uppercase;
          letter-spacing: 0.08em;
          margin-top: var(--space-4);
          margin-bottom: var(--space-2);
          padding: 0 var(--space-3);
        }

        .nav-section:first-child {
          margin-top: 0;
        }

        .nav-link {
          display: flex;
          align-items: center;
          gap: var(--space-3);
          padding: var(--space-3) var(--space-4);
          color: var(--text-charcoal);
          text-decoration: none;
          border-radius: var(--radius-md);
          transition: all var(--duration-fast) var(--ease-out);
          margin-bottom: var(--space-1);
          position: relative;
        }

        .nav-link:hover {
          background: var(--paper-hover);
          color: var(--text-ink);
        }

        .nav-link.active {
          background: rgba(79, 70, 229, 0.08);
          color: var(--ink-accent);
          font-weight: var(--font-medium);
        }

        .nav-link.active::before {
          content: '';
          position: absolute;
          left: 0;
          top: 50%;
          transform: translateY(-50%);
          width: 3px;
          height: 20px;
          background: var(--gradient-glow);
          border-radius: 0 var(--radius-full) var(--radius-full) 0;
        }

        .nav-indicator {
          position: absolute;
          left: 0;
          top: 50%;
          transform: translateY(-50%);
          width: 3px;
          height: 20px;
          background: var(--gradient-glow);
          border-radius: 0 var(--radius-full) var(--radius-full) 0;
        }

        .sidebar-footer {
          padding: var(--space-4) var(--space-5);
          border-top: 1px solid rgba(30, 58, 95, 0.04);
        }

        .status-indicator {
          display: flex;
          align-items: center;
          gap: var(--space-2);
          font-size: var(--text-sm);
          color: var(--text-charcoal);
        }

        .mode-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          position: relative;
        }

        .mode-dot.stub {
          background: var(--status-warning);
        }

        .mode-dot.real {
          background: var(--status-success);
        }

        .mode-dot.real::after {
          content: '';
          position: absolute;
          inset: -4px;
          border-radius: 50%;
          border: 1px solid var(--status-success);
          animation: pulse-ring 2s ease-out infinite;
        }

        .topbar {
          height: var(--topbar-height);
          background: var(--paper-surface);
          position: relative;
          display: flex;
          align-items: center;
          border-bottom: 1px solid rgba(30, 58, 95, 0.06);
        }

        .topbar-gradient {
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          height: 3px;
          background: var(--gradient-ink);
        }

        .topbar-content {
          flex: 1;
          height: 100%;
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0 var(--space-6);
        }

        .topbar-left {
          display: flex;
          align-items: center;
          gap: var(--space-3);
        }

        .topbar-title {
          font-family: var(--font-brand);
          font-size: var(--text-lg);
          font-weight: var(--font-semibold);
          color: var(--text-ink);
        }

        .topbar-right {
          display: flex;
          align-items: center;
          gap: var(--space-3);
        }

        .main-area {
          flex: 1;
          margin-left: var(--sidebar-width);
          display: flex;
          flex-direction: column;
          min-height: 100vh;
        }

        .content {
          flex: 1;
          padding: var(--space-6);
          max-width: var(--content-max-width);
          margin: 0 auto;
          width: 100%;
        }

        .mobile-toggle {
          display: none;
          position: fixed;
          top: var(--space-4);
          left: var(--space-4);
          z-index: 210;
          width: 40px;
          height: 40px;
          border: none;
          border-radius: var(--radius-md);
          background: var(--paper-surface);
          box-shadow: var(--shadow-md);
          color: var(--text-ink);
          cursor: pointer;
          align-items: center;
          justify-content: center;
        }

        .sidebar-overlay {
          display: none;
          position: fixed;
          inset: 0;
          background: rgba(0, 0, 0, 0.3);
          z-index: 199;
          backdrop-filter: blur(2px);
        }

        @keyframes pulse-ring {
          0% { transform: scale(1); opacity: 1; }
          100% { transform: scale(2); opacity: 0; }
        }

        @media (max-width: 768px) {
          .mobile-toggle {
            display: flex;
          }

          .sidebar-overlay {
            display: block;
          }

          .sidebar {
            transform: translateX(-100%);
          }

          .sidebar.open {
            transform: translateX(0);
          }

          .main-area {
            margin-left: 0;
          }

          .content {
            padding: calc(var(--topbar-height) + var(--space-4)) var(--space-4) var(--space-4);
          }

          .topbar-content {
            padding: 0 var(--space-4);
            padding-left: calc(var(--space-4) + 48px);
          }
        }
      `}</style>
    </div>
  )
}
