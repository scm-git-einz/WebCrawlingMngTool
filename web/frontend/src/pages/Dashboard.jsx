import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import StatCard from '../components/StatCard'

const STATUS_CLASS = {
  success: 'success', running: 'running',
  pending: 'pending', failed: 'failed',
}

const CATEGORY_ICONS = {
  '트렌드매장': '\u{1F6CD}\u{FE0F}', '트렌드Global매장': '\u{1F30D}',
  '경쟁사': '\u{1F3E2}', '경쟁사중국': '\u{1F1E8}\u{1F1F3}',
  '경쟁사이벤트': '\u{1F389}', '브랜드공식': '\u{2B50}',
  '네이버스토어': '\u{1F4E6}', '당사온라인몰': '\u{1F3E0}',
  '뉴스': '\u{1F4F0}', '카페': '\u{2615}',
}

const AGENT_LABELS = {
  product: '상품 수집', news: '뉴스 검색', cafe: '카페 수집',
}

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    fetch('/api/dashboard/stats')
      .then(r => r.json())
      .then(data => { setStats(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  if (loading) return <div className="loading">Loading...</div>
  if (!stats) return <div className="empty-state">데이터를 불러올 수 없습니다</div>

  const successRate = stats.total_crawls
    ? Math.round((stats.success_crawls / stats.total_crawls) * 100) : 0

  // 카테고리별 그룹핑
  const grouped = {}
  ;(stats.site_status || []).forEach(s => {
    const cat = s.category || '(미분류)'
    if (!grouped[cat]) grouped[cat] = []
    grouped[cat].push(s)
  })

  return (
    <>
      <div className="page-header">
        <h1>대시보드</h1>
        <p>크롤링 시스템 현황 요약</p>
      </div>

      <div className="stat-cards">
        <StatCard icon={'\u{1F310}'} color="blue"   label="등록 사이트" value={stats.total_sites} />
        <StatCard icon={'\u{2705}'}  color="green"  label="활성 사이트" value={stats.active_sites} />
        <StatCard icon={'\u{1F504}'} color="amber"  label="전체 크롤링" value={stats.total_crawls} />
        <StatCard icon={'\u{1F3AF}'} color="purple" label="성공률"     value={`${successRate}%`} />
      </div>

      {/* ── 카테고리별 사이트 수집 현황 ── */}
      <div className="page-header" style={{marginTop:8}}>
        <h2 style={{fontSize:18}}>사이트별 수집 현황</h2>
      </div>

      {Object.entries(grouped).map(([cat, sites]) => {
        const icon = CATEGORY_ICONS[cat] || '\u{1F4C1}'
        const collected = sites.filter(s => s.result_id).length
        return (
          <div className="card" key={cat}>
            <div className="card-header">
              <h2 style={{display:'flex',alignItems:'center',gap:8,fontSize:15}}>
                <span>{icon}</span> {cat}
                <span style={{fontSize:12,fontWeight:400,color:'var(--text-secondary)'}}>
                  {collected}/{sites.length} 수집됨
                </span>
              </h2>
            </div>
            <div className="card-body no-pad">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>사이트</th>
                    <th>유형</th>
                    <th>최근 수집일</th>
                    <th>상태</th>
                    <th>수집 건수</th>
                    <th>소요시간</th>
                  </tr>
                </thead>
                <tbody>
                  {sites.map(s => (
                    <tr
                      key={s.site_id}
                      style={{cursor: s.result_id ? 'pointer' : 'default'}}
                      onClick={() => s.result_id && navigate(`/results?site=${s.site_id}`)}
                    >
                      <td>
                        <div style={{fontWeight:600,fontSize:13}}>{s.site_name}</div>
                        <div style={{fontSize:11,color:'var(--text-secondary)',maxWidth:240,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
                          {s.site_url}
                        </div>
                      </td>
                      <td>
                        <span className={`badge ${s.agent_type === 'product' ? 'dp' : s.agent_type === 'news' ? 'pending' : 'tess'}`} style={{fontSize:11}}>
                          {AGENT_LABELS[s.agent_type] || s.agent_type}
                        </span>
                      </td>
                      <td style={{fontSize:12,whiteSpace:'nowrap'}}>
                        {s.crawl_date || <span style={{color:'#cbd5e1'}}>미수집</span>}
                      </td>
                      <td>
                        {s.result_id ? (
                          <span className={`badge ${STATUS_CLASS[s.status] || ''}`}>{s.status}</span>
                        ) : (
                          <span className="badge inactive">대기</span>
                        )}
                      </td>
                      <td style={{fontWeight:600}}>
                        {s.result_id ? s.product_count : '-'}
                      </td>
                      <td style={{fontSize:12}}>
                        {s.elapsed_sec ? `${s.elapsed_sec.toFixed(1)}s` : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )
      })}

      {/* ── 최근 크롤링 이력 ── */}
      <div className="card">
        <div className="card-header"><h2>최근 크롤링 이력</h2></div>
        <div className="card-body no-pad">
          <table className="data-table">
            <thead>
              <tr>
                <th>카테고리</th>
                <th>사이트</th>
                <th>유형</th>
                <th>날짜</th>
                <th>상태</th>
                <th>수집 건수</th>
                <th>소요시간</th>
              </tr>
            </thead>
            <tbody>
              {(stats.recent_crawls || []).map(r => (
                <tr key={r.id}>
                  <td style={{fontSize:12,color:'var(--text-secondary)'}}>{r.category || '-'}</td>
                  <td style={{fontWeight:600}}>{r.site_name}</td>
                  <td>
                    <span className={`badge ${r.agent_type === 'product' ? 'dp' : r.agent_type === 'news' ? 'pending' : 'tess'}`} style={{fontSize:11}}>
                      {r.agent_type}
                    </span>
                  </td>
                  <td style={{fontSize:12,whiteSpace:'nowrap'}}>{r.crawl_date}</td>
                  <td><span className={`badge ${STATUS_CLASS[r.status] || ''}`}>{r.status}</span></td>
                  <td>{r.product_count}</td>
                  <td>{r.elapsed_sec ? `${r.elapsed_sec.toFixed(1)}s` : '-'}</td>
                </tr>
              ))}
              {(!stats.recent_crawls || stats.recent_crawls.length === 0) && (
                <tr><td colSpan={7} className="empty-state">크롤링 이력이 없습니다</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
