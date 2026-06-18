import { useState, useEffect, useCallback } from 'react'

const AGENT_LABELS = {
  product: '상품', news: '뉴스', cafe: '카페',
  promotion: '이벤트', banner: '배너', directory: '목록',
  order: '주문서', coupon: '쿠폰',
}

const FAILURE_TYPE_LABELS = {
  http_block: 'HTTP 차단',
  soft_block: '소프트 차단',
  login_fail: '로그인 실패',
  click_fail: '클릭 실패',
  nav_fail: '이동 실패',
  data_fail: '데이터 실패',
  exception: '예외',
}

const FAILURE_TYPE_ICONS = {
  http_block: '\u{1F6AB}',
  soft_block: '\u{1F6E1}',
  login_fail: '\u{1F511}',
  click_fail: '\u{1F5B1}',
  nav_fail: '\u{27A1}',
  data_fail: '\u{1F4CA}',
  exception: '\u{26A0}',
}

const PERIOD_OPTIONS = [
  { value: 7, label: '최근 7일' },
  { value: 14, label: '최근 14일' },
  { value: 30, label: '최근 30일' },
  { value: 90, label: '최근 90일' },
]

function formatDate(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function formatDateFull(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}


/* ── StatCard ── */
function StatCard({ label, value, icon, color }) {
  return (
    <div className="failure-stat-card" style={{ borderTopColor: `var(--${color || 'primary'})` }}>
      <div className="failure-stat-icon">{icon}</div>
      <div className="failure-stat-value">{value}</div>
      <div className="failure-stat-label">{label}</div>
    </div>
  )
}


/* ── 상세 펼침 ── */
function FailureEventList({ events }) {
  if (!events || events.length === 0) return <div className="failure-no-events">이벤트 없음</div>

  return (
    <div className="failure-event-list">
      {events.map((ev, i) => (
        <div key={i} className="failure-event-item">
          <div className="failure-event-header">
            <span className="failure-event-time">{ev.time?.split(' ')[1] || ev.time}</span>
            <span className={`failure-event-badge failure-badge-${ev.type}`}>
              {FAILURE_TYPE_ICONS[ev.type] || '\u{2753}'} {FAILURE_TYPE_LABELS[ev.type] || ev.type}
            </span>
            {ev.subtype && <span className="failure-event-subtype">{ev.subtype}</span>}
          </div>
          <div className="failure-event-message">{ev.message}</div>
          {ev.target && <div className="failure-event-detail">대상: {ev.target}</div>}
          {ev.domain && <div className="failure-event-detail">도메인: {ev.domain}</div>}
          {ev.url && <div className="failure-event-detail url">URL: {ev.url}</div>}
          {ev.context && (
            <div className="failure-event-context">
              {Object.entries(ev.context).map(([k, v]) => (
                <span key={k} className="failure-context-tag">{k}: {String(v)}</span>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}


/* ── 메인 페이지 ── */
export default function FailureMonitoring() {
  const [stats, setStats] = useState(null)
  const [failures, setFailures] = useState([])
  const [loading, setLoading] = useState(true)

  // 필터 상태
  const [filterAgent, setFilterAgent] = useState('')
  const [filterPeriod, setFilterPeriod] = useState(30)
  const [filterSiteId, setFilterSiteId] = useState('')

  // 사이트 목록 (필터 드롭다운용)
  const [sites, setSites] = useState([])

  // 펼침 상태
  const [expandedId, setExpandedId] = useState(null)
  const [expandedDetail, setExpandedDetail] = useState(null)

  // 사이트 목록 로드
  useEffect(() => {
    fetch('/api/sites')
      .then(r => r.json())
      .then(data => setSites(Array.isArray(data) ? data : []))
      .catch(() => {})
  }, [])

  // 통계 로드
  const loadStats = useCallback(() => {
    fetch(`/api/failures/stats?days=${filterPeriod}`)
      .then(r => r.json())
      .then(data => setStats(data))
      .catch(() => {})
  }, [filterPeriod])

  // 목록 로드
  const loadFailures = useCallback(() => {
    setLoading(true)
    const params = new URLSearchParams()
    if (filterAgent) params.set('agent_type', filterAgent)
    if (filterSiteId) params.set('site_id', filterSiteId)
    params.set('limit', '100')

    // 기간 필터: date_from 계산
    const from = new Date()
    from.setDate(from.getDate() - filterPeriod)
    params.set('date_from', from.toISOString().split('T')[0])

    fetch(`/api/failures?${params}`)
      .then(r => r.json())
      .then(data => {
        setFailures(Array.isArray(data) ? data : [])
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [filterAgent, filterPeriod, filterSiteId])

  useEffect(() => { loadStats() }, [loadStats])
  useEffect(() => { loadFailures() }, [loadFailures])

  // 행 클릭 → 상세 로드
  const toggleExpand = (id) => {
    if (expandedId === id) {
      setExpandedId(null)
      setExpandedDetail(null)
      return
    }
    setExpandedId(id)
    setExpandedDetail(null)
    fetch(`/api/failures/${id}`)
      .then(r => r.json())
      .then(data => setExpandedDetail(data))
      .catch(() => {})
  }

  // 사이트명 찾기
  const siteName = (siteId) => {
    const s = sites.find(s => s.id === siteId)
    return s ? s.site_name : `ID ${siteId}`
  }

  // 주요 실패 유형 요약 (summary 기반)
  const topFailureTypes = (summary) => {
    if (!summary) return ''
    const types = Object.entries(summary)
      .filter(([k, v]) => k !== 'total' && v > 0)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
    return types.map(([k, v]) => `${FAILURE_TYPE_LABELS[k] || k} ${v}`).join(', ')
  }

  return (
    <div className="failure-monitor-page">
      <div className="failure-monitor-header">
        <h2>{'⚠️'} 실패 모니터링</h2>
        <p className="failure-monitor-desc">수집 실패 이력을 유형별로 분석합니다.</p>
      </div>

      {/* ── StatCards ── */}
      <div className="failure-stat-grid">
        <StatCard
          label="전체 실패"
          value={stats?.total_events ?? '-'}
          icon={'\u{1F4CB}'}
          color="danger"
        />
        <StatCard
          label="HTTP 차단"
          value={stats?.http_block ?? '-'}
          icon={'\u{1F6AB}'}
          color="warning"
        />
        <StatCard
          label="클릭/이동 실패"
          value={(stats?.click_fail ?? 0) + (stats?.nav_fail ?? 0) || '-'}
          icon={'\u{1F5B1}'}
          color="primary"
        />
        <StatCard
          label="데이터 실패"
          value={stats?.data_fail ?? '-'}
          icon={'\u{1F4CA}'}
          color="warning"
        />
      </div>

      {/* ── 필터 바 ── */}
      <div className="failure-filter-bar">
        <div className="failure-filter-item">
          <label>에이전트</label>
          <select value={filterAgent} onChange={e => setFilterAgent(e.target.value)}>
            <option value="">전체</option>
            {Object.entries(AGENT_LABELS).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </div>

        <div className="failure-filter-item">
          <label>기간</label>
          <select value={filterPeriod} onChange={e => setFilterPeriod(Number(e.target.value))}>
            {PERIOD_OPTIONS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>

        <div className="failure-filter-item">
          <label>사이트</label>
          <select value={filterSiteId} onChange={e => setFilterSiteId(e.target.value)}>
            <option value="">전체</option>
            {sites.map(s => (
              <option key={s.id} value={s.id}>{s.site_name}</option>
            ))}
          </select>
        </div>

        <button className="failure-filter-refresh" onClick={() => { loadStats(); loadFailures() }}>
          {'\u{1F504}'} 새로고침
        </button>
      </div>

      {/* ── 테이블 ── */}
      <div className="failure-table-wrap">
        {loading ? (
          <div className="failure-loading">로딩 중...</div>
        ) : failures.length === 0 ? (
          <div className="failure-empty">해당 기간에 실패 기록이 없습니다.</div>
        ) : (
          <table className="failure-table">
            <thead>
              <tr>
                <th>날짜</th>
                <th>사이트</th>
                <th>에이전트</th>
                <th>실패 유형</th>
                <th>건수</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {failures.map(row => (
                <>
                  <tr
                    key={row.id}
                    className={`failure-row ${expandedId === row.id ? 'expanded' : ''}`}
                    onClick={() => toggleExpand(row.id)}
                  >
                    <td className="failure-cell-date">{formatDate(row.crawl_date)}</td>
                    <td className="failure-cell-site">{siteName(row.site_id)}</td>
                    <td>
                      <span className={`badge-agent badge-${row.agent_type}`}>
                        {AGENT_LABELS[row.agent_type] || row.agent_type}
                      </span>
                    </td>
                    <td className="failure-cell-types">{topFailureTypes(row.failure_summary)}</td>
                    <td className="failure-cell-count">
                      <span className="failure-count-badge">{row.failure_summary?.total || 0}</span>
                    </td>
                    <td className="failure-cell-arrow">
                      {expandedId === row.id ? '▼' : '▶'}
                    </td>
                  </tr>
                  {expandedId === row.id && (
                    <tr key={`${row.id}-detail`} className="failure-detail-row">
                      <td colSpan={6}>
                        <div className="failure-detail-wrap">
                          <div className="failure-detail-meta">
                            <span>크롤 일시: {formatDateFull(row.crawl_date)}</span>
                            {row.log_file && <span>로그: {row.log_file}</span>}
                          </div>
                          <div className="failure-detail-summary">
                            {row.failure_summary && Object.entries(row.failure_summary)
                              .filter(([k, v]) => k !== 'total' && v > 0)
                              .map(([k, v]) => (
                                <span key={k} className={`failure-summary-chip failure-badge-${k}`}>
                                  {FAILURE_TYPE_ICONS[k]} {FAILURE_TYPE_LABELS[k] || k}: {v}
                                </span>
                              ))
                            }
                          </div>
                          {expandedDetail?.failure_events ? (
                            <FailureEventList events={expandedDetail.failure_events} />
                          ) : (
                            <div className="failure-loading-detail">상세 로딩 중...</div>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
