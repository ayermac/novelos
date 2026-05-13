import { useEffect, useState } from 'react'
import { Outlet, NavLink, useLocation } from 'react-router-dom'
import {
  FolderPlus,
  CheckSquare,
  Palette,
  Settings,
  LayoutDashboard,
  FolderOpen,
  LucideIcon,
  Factory,
  Menu,
  X,
  Activity,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react'
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
]

export default function Layout() {
  const [llmMode, setLlmMode] = useState<string>('stub')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
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
  const isProjectWorkspace = /^\/projects\/[^/]+/.test(location.pathname)

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

      <aside
        className={`sidebar ${sidebarOpen ? 'open' : ''} ${sidebarCollapsed ? 'collapsed' : ''}`}
        aria-label="主菜单"
      >
        <div className="sidebar-brand">
          <div className="brand-icon">
            <Factory size={22} />
          </div>
          <div className="brand-text">
            <span className="brand-name">墨流工厂</span>
            <span className="brand-tagline">长篇小说生产系统</span>
          </div>
          <span className="version">v5.5.9</span>
          <button
            type="button"
            className="sidebar-collapse-toggle"
            onClick={() => setSidebarCollapsed((value) => !value)}
            aria-label={sidebarCollapsed ? '展开主菜单' : '收起主菜单'}
            aria-expanded={!sidebarCollapsed}
            title={sidebarCollapsed ? '展开主菜单' : '收起主菜单'}
          >
            {sidebarCollapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
          </button>
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
                aria-label={sidebarCollapsed ? item.label : undefined}
                title={sidebarCollapsed ? item.label : undefined}
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

      <div className={`main-area ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
        <header className="topbar">
          <div className="topbar-gradient" />
          <div className="topbar-content">
            <div className="topbar-left">
              <span className="topbar-title">生产控制台</span>
              <span className="topbar-subtitle">Auto-Run Resilience</span>
            </div>
            <div className="topbar-right">
              <span className="badge badge-neutral">
                <Activity size={13} />
                工厂在线
              </span>
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

        <main className={`content ${isProjectWorkspace ? 'content-project-workspace' : ''}`}>
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
          background: linear-gradient(180deg, var(--paper-surface) 0%, var(--paper-bg) 100%);
          border-right: 1px solid var(--border-color);
          display: flex;
          flex-direction: column;
          position: fixed;
          left: 0;
          top: 0;
          bottom: 0;
          z-index: 200;
          transition:
            width var(--duration-slow) var(--ease-out),
            transform var(--duration-slow) var(--ease-out);
          overflow: hidden;
        }

        .sidebar.collapsed {
          width: 72px;
        }

        .sidebar-brand {
          padding: var(--space-5) var(--space-4) var(--space-4);
          display: grid;
          grid-template-columns: 42px minmax(0, 1fr) 34px;
          grid-template-areas:
            "icon text toggle"
            "icon version toggle";
          align-items: center;
          column-gap: var(--space-3);
          row-gap: var(--space-2);
          border-bottom: 1px solid var(--border-color);
        }

        .sidebar.collapsed .sidebar-brand {
          display: flex;
          flex-direction: column;
          justify-content: center;
          gap: var(--space-2);
          padding: var(--space-4) var(--space-3);
        }

        .brand-icon {
          grid-area: icon;
          width: 42px;
          height: 42px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: var(--gradient-ink);
          border-radius: var(--radius-md);
          color: white;
          flex: 0 0 auto;
        }

        .brand-text {
          grid-area: text;
          display: flex;
          flex-direction: column;
          flex: 1;
          min-width: 0;
          align-self: end;
        }

        .brand-name {
          font-family: var(--font-brand);
          font-size: var(--text-lg);
          font-weight: var(--font-bold);
          color: var(--text-ink);
          letter-spacing: 0;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .brand-tagline {
          font-size: var(--text-xs);
          color: var(--text-gray);
          margin-top: 2px;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .version {
          grid-area: version;
          justify-self: start;
          align-self: start;
          font-size: var(--text-xs);
          color: var(--ink-accent);
          background: rgba(176, 138, 75, 0.12);
          border: 1px solid rgba(124, 95, 52, 0.18);
          padding: 3px 8px;
          border-radius: var(--radius-md);
          font-weight: var(--font-semibold);
          white-space: nowrap;
        }

        .sidebar-collapse-toggle {
          grid-area: toggle;
          width: 34px;
          height: 34px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          border: 1px solid rgba(124, 95, 52, 0.16);
          border-radius: var(--radius-md);
          background: rgba(255, 254, 250, 0.72);
          color: var(--text-charcoal);
          cursor: pointer;
          flex: 0 0 auto;
          align-self: center;
          transition:
            background var(--duration-fast) var(--ease-out),
            color var(--duration-fast) var(--ease-out),
            border-color var(--duration-fast) var(--ease-out);
        }

        .sidebar-collapse-toggle:hover {
          background: var(--paper-hover);
          color: var(--ink-accent);
          border-color: rgba(124, 95, 52, 0.28);
        }

        .sidebar-collapse-toggle:focus-visible {
          outline: 2px solid rgba(124, 95, 52, 0.34);
          outline-offset: 2px;
        }

        .sidebar.collapsed .brand-text,
        .sidebar.collapsed .version {
          display: none;
        }

        .sidebar-nav {
          flex: 1;
          padding: var(--space-4) var(--space-3);
          overflow-y: auto;
          overflow-x: hidden;
        }

        .sidebar.collapsed .sidebar-nav {
          padding: var(--space-4) var(--space-2);
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

        .sidebar.collapsed .nav-section {
          height: 1px;
          margin: var(--space-3) var(--space-2);
          padding: 0;
          background: var(--border-color);
          color: transparent;
          overflow: hidden;
        }

        .sidebar.collapsed .nav-section:first-child {
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

        .sidebar.collapsed .nav-link {
          justify-content: center;
          gap: 0;
          padding: var(--space-3);
        }

        .sidebar.collapsed .nav-link span {
          display: none;
        }

        .nav-link:hover {
          background: var(--paper-hover);
          color: var(--text-ink);
        }

        .nav-link.active {
          background: rgba(124, 95, 52, 0.10);
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
          border-top: 1px solid var(--border-color);
        }

        .sidebar.collapsed .sidebar-footer {
          display: flex;
          justify-content: center;
          padding: var(--space-4) var(--space-2);
        }

        .status-indicator {
          display: flex;
          align-items: center;
          gap: var(--space-2);
          font-size: var(--text-sm);
          color: var(--text-charcoal);
        }

        .sidebar.collapsed .status-indicator span {
          display: none;
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
          background: rgba(255, 254, 250, 0.94);
          backdrop-filter: blur(12px);
          position: relative;
          display: flex;
          align-items: center;
          border-bottom: 1px solid var(--border-color);
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

        .topbar-subtitle {
          font-size: var(--text-xs);
          color: var(--text-gray);
          padding: 3px 8px;
          border: 1px solid rgba(124, 95, 52, 0.16);
          background: rgba(176, 138, 75, 0.10);
          border-radius: var(--radius-md);
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
          transition: margin-left var(--duration-slow) var(--ease-out);
        }

        .main-area.sidebar-collapsed {
          margin-left: 72px;
        }

        .content {
          flex: 1;
          padding: var(--space-6);
          max-width: var(--content-max-width);
          margin: 0 auto;
          width: 100%;
        }

        .content-project-workspace {
          max-width: none;
          margin: 0;
          padding: var(--space-6);
          min-width: 0;
          background: transparent;
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
            width: var(--sidebar-width);
          }

          .sidebar.open {
            transform: translateX(0);
          }

          .sidebar.collapsed {
            width: var(--sidebar-width);
          }

          .sidebar.collapsed .sidebar-brand {
            display: grid;
            grid-template-columns: 42px minmax(0, 1fr);
            grid-template-areas:
              "icon text"
              "icon version";
            justify-content: flex-start;
            column-gap: var(--space-3);
            row-gap: var(--space-2);
            padding: var(--space-5) var(--space-5) var(--space-4);
          }

          .sidebar.collapsed .brand-text,
          .sidebar.collapsed .version,
          .sidebar.collapsed .nav-link span,
          .sidebar.collapsed .status-indicator span {
            display: flex;
          }

          .sidebar.collapsed .version {
            display: inline-flex;
          }

          .sidebar.collapsed .nav-section {
            height: auto;
            margin-top: var(--space-4);
            margin-bottom: var(--space-2);
            padding: 0 var(--space-3);
            background: transparent;
            color: var(--text-gray);
            overflow: visible;
          }

          .sidebar.collapsed .nav-link {
            justify-content: flex-start;
            gap: var(--space-3);
            padding: var(--space-3) var(--space-4);
          }

          .sidebar-collapse-toggle {
            display: none;
          }

          .main-area {
            margin-left: 0;
          }

          .main-area.sidebar-collapsed {
            margin-left: 0;
          }

          .content {
            padding: calc(var(--topbar-height) + var(--space-4)) var(--space-4) var(--space-4);
          }

          .content-project-workspace {
            padding: calc(var(--topbar-height) + var(--space-4)) 0 0;
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
