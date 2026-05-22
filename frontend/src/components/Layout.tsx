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
  Menu,
  X,
  Activity,
  PanelLeftClose,
  PanelLeftOpen,
  Moon,
  Sun,
} from 'lucide-react'
import { get } from '../lib/api'
import DesktopRuntimeBanner from './DesktopRuntimeBanner'
import DesktopFirstRunSetup from './desktop/DesktopFirstRunSetup'
import packageInfo from '../../package.json'

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
const THEME_STORAGE_KEY = 'novelos.theme'
const APP_VERSION = packageInfo.version
type ThemeMode = 'light' | 'dark'

function getInitialTheme(): ThemeMode {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY)
    if (stored === 'light' || stored === 'dark') return stored
    if (window.matchMedia?.('(prefers-color-scheme: dark)').matches) return 'dark'
  } catch {
    // Ignore storage/media failures and fall back to the calmer daytime theme.
  }
  return 'light'
}

export default function Layout() {
  const [llmMode, setLlmMode] = useState<string>('stub')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [theme, setTheme] = useState<ThemeMode>(getInitialTheme)
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
  const logoSrc = window.__NOVELOS_DESKTOP__ ? './logo.png' : '/logo.png'

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

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.documentElement.style.colorScheme = theme
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, theme)
    } catch {
      // Theme still applies for this session.
    }
  }, [theme])

  const nextTheme = theme === 'dark' ? 'light' : 'dark'
  const themeLabel = theme === 'dark' ? '切换到日间模式' : '切换到夜间模式'

  return (
    <div className="app-layout">
      <DesktopRuntimeBanner />
      <DesktopFirstRunSetup />
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
            <img src={logoSrc} alt="" aria-hidden="true" />
          </div>
          <div className="brand-text">
            <span className="brand-name">墨流工厂</span>
            <span className="brand-tagline">长篇小说生产系统</span>
          </div>
          <div className="brand-meta-row">
            <span className="version">v{APP_VERSION}</span>
            <div className="sidebar-brand-actions">
              <button
                type="button"
                className="sidebar-icon-toggle"
                onClick={() => setTheme(nextTheme)}
                aria-label={themeLabel}
                title={themeLabel}
              >
                {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
              </button>
              <button
                type="button"
                className="sidebar-icon-toggle"
                onClick={() => setSidebarCollapsed((value) => !value)}
                aria-label={sidebarCollapsed ? '展开主菜单' : '收起主菜单'}
                aria-expanded={!sidebarCollapsed}
                title={sidebarCollapsed ? '展开主菜单' : '收起主菜单'}
              >
                {sidebarCollapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
              </button>
            </div>
          </div>
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
          background: var(--app-bg);
          color: var(--text-primary);
        }

        .sidebar {
          width: var(--sidebar-width);
          background: var(--sidebar-bg);
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
          overflow: visible;
        }

        .sidebar-brand {
          padding: 22px 16px 18px;
          display: grid;
          grid-template-columns: 52px minmax(0, 1fr);
          grid-template-areas:
            "icon text"
            "meta meta";
          align-items: center;
          column-gap: 14px;
          row-gap: 12px;
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
          width: 52px;
          height: 52px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: transparent;
          border-radius: 10px;
          flex: 0 0 auto;
          overflow: hidden;
          box-shadow: 0 10px 22px rgba(17, 24, 39, 0.16);
        }

        .brand-icon img {
          width: 100%;
          height: 100%;
          display: block;
          object-fit: cover;
        }

        .sidebar-brand-actions {
          display: flex;
          align-items: center;
          gap: 6px;
        }

        .sidebar-icon-toggle {
          width: 32px;
          height: 32px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          border: 1px solid var(--border-color);
          border-radius: 8px;
          background: var(--bg-primary);
          color: var(--text-secondary);
          cursor: pointer;
          transition:
            background var(--duration-fast) var(--ease-out),
            color var(--duration-fast) var(--ease-out),
            border-color var(--duration-fast) var(--ease-out),
            transform var(--duration-fast) var(--ease-out);
        }

        .sidebar-icon-toggle:hover,
        .sidebar-icon-toggle:focus-visible {
          background: var(--bg-tertiary);
          color: var(--primary);
          border-color: var(--border-strong);
          outline: none;
        }

        .sidebar-icon-toggle:active {
          transform: translateY(1px);
        }

        .sidebar.collapsed .sidebar-brand-actions {
          align-self: center;
          flex-direction: column;
        }

        .brand-meta-row {
          grid-area: meta;
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
          min-width: 0;
          padding-left: 66px;
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
          color: var(--text-primary);
          letter-spacing: 0;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .brand-tagline {
          font-size: 12px;
          color: var(--text-secondary);
          margin-top: 2px;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .version {
          font-size: 11px;
          color: var(--primary);
          background: var(--accent-soft);
          border: 1px solid var(--accent-border);
          padding: 3px 8px;
          border-radius: 4px;
          font-weight: 650;
          white-space: nowrap;
        }

        .sidebar.collapsed .brand-text {
          display: none;
        }

        .sidebar.collapsed .brand-meta-row {
          display: flex;
          justify-content: center;
          padding-left: 0;
          width: 100%;
        }

        .sidebar.collapsed .version,
        .sidebar.collapsed .sidebar-brand-actions .sidebar-icon-toggle:first-child {
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
          color: var(--text-muted);
        }

        .nav-section:first-child {
          margin-top: 0;
        }

        .sidebar.collapsed .nav-section {
          height: 1px;
          margin: 12px 8px;
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
          gap: 10px;
          min-height: 38px;
          padding: 0 12px;
          color: var(--text-secondary);
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
          background: var(--bg-tertiary);
          color: var(--text-primary);
        }

        .nav-link.active {
          background: var(--accent-soft);
          color: var(--primary);
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
          background: var(--primary);
          border-radius: 0 999px 999px 0;
        }

        .nav-indicator {
          position: absolute;
          left: 0;
          top: 50%;
          transform: translateY(-50%);
          width: 3px;
          height: 20px;
          background: var(--primary);
          border-radius: 0 999px 999px 0;
        }

        .sidebar-footer {
          padding: 14px 18px;
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
          font-size: 12px;
          color: var(--text-secondary);
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
          background: var(--warning);
        }

        .mode-dot.real {
          background: var(--success);
        }

        .mode-dot.real::after {
          content: '';
          position: absolute;
          inset: -4px;
          border-radius: 50%;
          border: 1px solid var(--success);
          animation: pulse-ring 2s ease-out infinite;
        }

        .topbar {
          height: var(--topbar-height);
          background: var(--topbar-bg);
          backdrop-filter: blur(14px);
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
          color: var(--text-primary);
        }

        .topbar-subtitle {
          font-size: 12px;
          color: var(--text-secondary);
          padding: 3px 8px;
          border: 1px solid var(--border-color);
          background: var(--bg-tertiary);
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
            grid-template-columns: 52px minmax(0, 1fr);
            grid-template-areas:
              "icon text"
              "meta meta";
            justify-content: flex-start;
            column-gap: 14px;
            row-gap: 12px;
            padding: var(--space-5) var(--space-5) var(--space-4);
          }

          .sidebar.collapsed .brand-text,
          .sidebar.collapsed .brand-meta-row,
          .sidebar.collapsed .nav-link span,
          .sidebar.collapsed .status-indicator span {
            display: flex;
          }

          .sidebar.collapsed .version,
          .sidebar.collapsed .sidebar-brand-actions .sidebar-icon-toggle:first-child {
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

          .sidebar.collapsed .sidebar-brand-actions {
            flex-direction: row;
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
