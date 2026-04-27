import { Outlet, NavLink } from 'react-router-dom'
import { Book, FolderPlus, Play, CheckSquare, Palette, Settings, CheckCircle, LayoutDashboard, FolderOpen } from 'lucide-react'

const navItems = [
  { to: '/', label: '总览', icon: LayoutDashboard },
  { to: '/projects', label: '项目', icon: FolderOpen },
  { to: '/onboarding', label: '创建项目', icon: FolderPlus },
  { to: '/run', label: '生成章节', icon: Play },
  { to: '/review', label: '审核', icon: CheckSquare },
  { to: '/style', label: '风格', icon: Palette },
  { to: '/settings', label: '配置', icon: Settings },
  { to: '/acceptance', label: '验收', icon: CheckCircle },
]

export default function Layout() {
  return (
    <div className="app-layout">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-brand">
          <Book size={20} />
          <span>小说工厂</span>
          <span className="version">v5.1.2</span>
        </div>

        <nav className="sidebar-nav">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) => (isActive ? 'active' : '')}
            >
              <item.icon size={18} />
              {item.label}
            </NavLink>
          ))}
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
            <span className="status-badge status-stub">演示模式</span>
          </div>
        </header>

        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
