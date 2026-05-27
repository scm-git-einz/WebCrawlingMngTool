import { NavLink } from 'react-router-dom'

const mainNav = [
  { path: '/',        icon: '\u{1F4CA}', label: '대시보드' },
  { path: '/sites',   icon: '\u{1F310}', label: '수집 대상 설정' },
  { path: '/results', icon: '\u{1F4C4}', label: '수집 결과' },
]

const adminNav = [
  { path: '/admin/ocr', icon: '\u{1F50D}', label: 'OCR 사용 이력' },
]

export default function Layout({ children }) {
  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <span>{'\u{1F577}\u{FE0F}'}</span> Crawling Manager
        </div>
        <ul className="sidebar-nav">
          {mainNav.map(item => (
            <li key={item.path}>
              <NavLink
                to={item.path}
                end={item.path === '/'}
                className={({ isActive }) => isActive ? 'active' : ''}
              >
                <span className="nav-icon">{item.icon}</span>
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>
        <div className="sidebar-section-label">관리자</div>
        <ul className="sidebar-nav" style={{paddingTop:0}}>
          {adminNav.map(item => (
            <li key={item.path}>
              <NavLink
                to={item.path}
                className={({ isActive }) => isActive ? 'active' : ''}
              >
                <span className="nav-icon">{item.icon}</span>
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </aside>
      <main className="main-content">
        {children}
      </main>
    </div>
  )
}
