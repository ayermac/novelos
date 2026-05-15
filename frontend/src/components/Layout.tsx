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
  Feather,
  Menu,
  X,
  Activity,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react'
import { get } from '../lib/api'
import DesktopRuntimeBanner from './DesktopRuntimeBanner'

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

const SIDEBAR_COLLAPSED_STORAGE_KEY = 'novelos.mainSidebar.collapsed'

export default function Layout() {
  const [llmMode, setLlmMode] = useState<string>('stub')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try {
      return window.localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY) === '1'
    } catch {
      return false
    }
  })
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

  useEffect(() => {
    try {
      window.localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, sidebarCollapsed ? '1' : '0')
    } catch {
      // Ignore storage failures; the sidebar still works for the current session.
    }
  }, [sidebarCollapsed])

  return (
    <div className="app-layout">
      <DesktopRuntimeBanner />
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
            <Feather size={22} />
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
                data-tooltip={sidebarCollapsed ? item.label : undefined}
                className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
              >
                {({ isActive }) => (
                  <>
                    {item.icon && <item.icon size={18} />}
                    <span className="nav-label">{item.label}</span>
                    <span className="nav-tooltip" aria-hidden="true">{item.label}</span>
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
        {!isProjectWorkspace && (
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
        )}

        <main className={`content ${isProjectWorkspace ? 'content-project-workspace' : ''}`}>
          <Outlet />
        </main>
      </div>

      <style>{`
        .app-layout {
          display: flex;
          min-height: 100vh;
          background: #f4f4f3;
        }

        .sidebar {
          width: var(--sidebar-width);
          background: #fbfbfa;
          border-right: 1px solid #dedbd4;
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
          overflow: visible;
        }

        .sidebar-brand {
          padding: 22px 16px 18px;
          display: grid;
          grid-template-columns: 42px minmax(0, 1fr) 34px;
          grid-template-areas:
            "icon text toggle"
            "icon version toggle";
          align-items: center;
          column-gap: var(--space-3);
          row-gap: var(--space-2);
          border-bottom: 1px solid #dedbd4;
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
          background: #102338;
          border-radius: 8px;
          color: #fffefc;
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
          font-family: Georgia, 'Times New Roman', 'Songti SC', serif;
          font-size: 20px;
          font-weight: 600;
          color: #191715;
          letter-spacing: 0;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .brand-tagline {
          font-size: 12px;
          color: #68615b;
          margin-top: 2px;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .version {
          grid-area: version;
          justify-self: start;
          align-self: start;
          font-size: 11px;
          color: #761a34;
          background: #f5eef1;
          border: 1px solid rgba(118, 26, 52, 0.18);
          padding: 3px 8px;
          border-radius: 4px;
          font-weight: 650;
          white-space: nowrap;
        }

        .sidebar-collapse-toggle {
          grid-area: toggle;
          width: 34px;
          height: 34px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          border: 1px solid #dedbd4;
          border-radius: 6px;
          background: #fffefc;
          color: #554f49;
          cursor: pointer;
          flex: 0 0 auto;
          align-self: center;
          transition:
            background var(--duration-fast) var(--ease-out),
            color var(--duration-fast) var(--ease-out),
            border-color var(--duration-fast) var(--ease-out);
        }

        .sidebar-collapse-toggle:hover {
          background: #f6f2f0;
          color: #761a34;
          border-color: rgba(118, 26, 52, 0.26);
        }

        .sidebar-collapse-toggle:focus-visible {
          outline: 2px solid rgba(118, 26, 52, 0.24);
          outline-offset: 2px;
        }

        .sidebar.collapsed .brand-text,
        .sidebar.collapsed .version {
          display: none;
        }

        .sidebar-nav {
          flex: 1;
          padding: 16px 12px;
          overflow-y: auto;
          overflow-x: hidden;
        }

        .sidebar.collapsed .sidebar-nav {
          padding: 16px 8px;
          overflow: visible;
        }

        .nav-section {
          font-size: 11px;
          font-weight: 720;
          color: #8b837b;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          margin-top: 18px;
          margin-bottom: 8px;
          padding: 0 12px;
        }

        .nav-section:first-child {
          margin-top: 0;
        }

        .sidebar.collapsed .nav-section {
          height: 1px;
          margin: 12px 8px;
          padding: 0;
          background: #dedbd4;
          color: transparent;
          overflow: hidden;
        }

        .sidebar.collapsed .nav-section:first-child {
          margin-top: 0;
        }

        .nav-link {
          display: flex;
          align-items: center;
          gap: 10px;
          min-height: 38px;
          padding: 0 12px;
          color: #554f49;
          text-decoration: none;
          border-radius: 6px;
          transition: all var(--duration-fast) var(--ease-out);
          margin-bottom: 4px;
          position: relative;
        }

        .sidebar.collapsed .nav-link {
          justify-content: center;
          gap: 0;
          padding: 0;
        }

        .nav-tooltip {
          display: none;
          position: absolute;
          top: 50%;
          left: 56px;
          transform: translateY(-50%);
          z-index: 500;
          min-width: max-content;
          max-width: 180px;
          padding: 6px 9px;
          border: 1px solid rgba(34, 28, 24, 0.1);
          border-radius: 4px;
          background: #191715;
          color: #fffefc;
          box-shadow: 0 12px 28px rgba(31, 27, 25, 0.18);
          font-size: 12px;
          font-weight: 620;
          line-height: 1;
          opacity: 0;
          pointer-events: none;
          transition: opacity var(--duration-fast) var(--ease-out);
        }

        .sidebar.collapsed .nav-link:hover .nav-tooltip,
        .sidebar.collapsed .nav-link:focus .nav-tooltip,
        .sidebar.collapsed .nav-link:focus-visible .nav-tooltip {
          display: block;
          opacity: 1;
        }

        .sidebar.collapsed .nav-link .nav-label {
          display: none;
        }

        .nav-link:hover {
          background: #f6f2f0;
          color: #191715;
        }

        .nav-link.active {
          background: #f3e8eb;
          color: #761a34;
          font-weight: 650;
        }

        .nav-link.active::before {
          content: '';
          position: absolute;
          left: 0;
          top: 50%;
          transform: translateY(-50%);
          width: 3px;
          height: 20px;
          background: #761a34;
          border-radius: 0 999px 999px 0;
        }

        .nav-indicator {
          position: absolute;
          left: 0;
          top: 50%;
          transform: translateY(-50%);
          width: 3px;
          height: 20px;
          background: #761a34;
          border-radius: 0 999px 999px 0;
        }

        .sidebar-footer {
          padding: 14px 18px;
          border-top: 1px solid #dedbd4;
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
          font-size: 12px;
          color: #554f49;
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
          background: #b46b18;
        }

        .mode-dot.real {
          background: #1d7b46;
        }

        .mode-dot.real::after {
          content: '';
          position: absolute;
          inset: -4px;
          border-radius: 50%;
          border: 1px solid #1d7b46;
          animation: pulse-ring 2s ease-out infinite;
        }

        .topbar {
          height: var(--topbar-height);
          background: rgba(252, 252, 250, 0.96);
          backdrop-filter: blur(14px);
          position: relative;
          display: flex;
          align-items: center;
          border-bottom: 1px solid #dedbd4;
        }

        .topbar-gradient {
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          height: 3px;
          background: linear-gradient(90deg, #102338 0%, #761a34 58%, #118384 100%);
        }

        .topbar-content {
          flex: 1;
          height: 100%;
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0 48px;
        }

        .topbar-left {
          display: flex;
          align-items: center;
          gap: var(--space-3);
        }

        .topbar-title {
          font-family: Georgia, 'Times New Roman', 'Songti SC', serif;
          font-size: 18px;
          font-weight: 600;
          color: #191715;
        }

        .topbar-subtitle {
          font-size: 12px;
          color: #6f6862;
          padding: 3px 8px;
          border: 1px solid #dedbd4;
          background: #f7f4ef;
          border-radius: 6px;
        }

        .topbar-right {
          display: flex;
          align-items: center;
          gap: var(--space-3);
        }

        .main-area {
          flex: 1;
          margin-left: var(--sidebar-width);
          width: calc(100vw - var(--sidebar-width));
          display: flex;
          flex-direction: column;
          min-height: 100vh;
          transition: margin-left var(--duration-slow) var(--ease-out);
        }

        .main-area.sidebar-collapsed {
          margin-left: 72px;
          width: calc(100vw - 72px);
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
            width: 100vw;
          }

          .main-area.sidebar-collapsed {
            margin-left: 0;
            width: 100vw;
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
