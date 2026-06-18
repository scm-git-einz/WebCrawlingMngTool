import { useState, useEffect, useMemo, useCallback } from 'react'

const AGENT_LABELS = {
  product: '상품', news: '뉴스', cafe: '카페',
  promotion: '이벤트', banner: '배너', directory: '목록',
  order: '주문서', coupon: '쿠폰',
}

const SCHEDULE_LABELS = {
  '': '-', hourly: '시간', daily: '일간', weekly: '주간', monthly: '월간',
}

/* ── config_key 기반으로 해당 필드가 수집 대상인지 판정 ── */
function isFieldCollected(site, fieldKey, configKey) {
  const cfg = site.crawl_config || {}

  if (!configKey) return true

  if (configKey === 'collect_fields') {
    const cf = cfg.collect_fields || []
    const of_ = cfg.optional_fields || []
    if (cf.length === 0 && of_.length === 0) return true
    return cf.includes(fieldKey) || of_.includes(fieldKey)
  }

  if (configKey === 'banner_areas') {
    const areas = cfg.banner_areas || cfg.areas || ['hero', 'sub_banner']
    return areas.length === 0 || areas.includes(fieldKey)
  }

  if (configKey === 'event_coupons') {
    return Array.isArray(cfg.event_coupons) && cfg.event_coupons.length > 0
  }
  if (configKey === 'auto_discovery') {
    return !!(cfg.event_list_url && cfg.event_list_url.trim())
  }
  if (configKey === 'coupon_keywords') {
    return Array.isArray(cfg.coupon_keywords) && cfg.coupon_keywords.length > 0
  }

  const val = cfg[configKey]
  if (val === undefined) return false
  if (typeof val === 'boolean') return val
  if (typeof val === 'string') return val.toLowerCase() !== 'false' && val !== '0' && val !== ''
  return !!val
}

function formatDate(dateStr) {
  if (!dateStr) return '-'
  try {
    const d = new Date(dateStr)
    if (isNaN(d.getTime())) return '-'
    const Y = d.getFullYear()
    const M = String(d.getMonth() + 1).padStart(2, '0')
    const D = String(d.getDate()).padStart(2, '0')
    const h = String(d.getHours()).padStart(2, '0')
    const m = String(d.getMinutes()).padStart(2, '0')
    const s = String(d.getSeconds()).padStart(2, '0')
    return `${Y}-${M}-${D} ${h}:${m}:${s}`
  } catch { return '-' }
}

export default function Matrix() {
  const [sites, setSites] = useState([])
  const [lastCrawlMap, setLastCrawlMap] = useState({})
  const [agentFieldDefs, setAgentFieldDefs] = useState({})
  const [loading, setLoading] = useState(true)
  const [filterAgent, setFilterAgent] = useState('all')
  const [filterCategory, setFilterCategory] = useState('all')

  const loadData = useCallback(() => {
    Promise.all([
      fetch('/api/sites').then(r => r.json()),
      fetch('/api/dashboard/stats').then(r => r.json()),
      fetch('/api/agent-fields').then(r => r.json()),
    ])
      .then(([sitesData, statsData, fieldDefs]) => {
        setSites(sitesData)
        const map = {}
        for (const ss of (statsData.site_status || [])) {
          if (ss.crawl_date) map[ss.site_id] = ss.crawl_date
        }
        setLastCrawlMap(map)
        setAgentFieldDefs(fieldDefs)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  useEffect(() => {
    loadData()
    const onFocus = () => loadData()
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [loadData])

  const allAgents = useMemo(() => Object.keys(agentFieldDefs), [agentFieldDefs])

  const filtered = useMemo(() => {
    let list = sites
    if (filterAgent !== 'all') list = list.filter(s => s.agent_type === filterAgent)
    if (filterCategory !== 'all') list = list.filter(s => s.category === filterCategory)
    return list
  }, [sites, filterAgent, filterCategory])

  const categories = useMemo(() => {
    const set = new Set(sites.map(s => s.category || '미분류'))
    return [...set].sort()
  }, [sites])

  const categoryGroups = useMemo(() => {
    const groups = {}
    for (const s of filtered) {
      const cat = s.category || '미분류'
      if (!groups[cat]) groups[cat] = []
      groups[cat].push(s)
    }
    return groups
  }, [filtered])

  const categoryFieldsMap = useMemo(() => {
    const map = {}
    for (const [cat, catSites] of Object.entries(categoryGroups)) {
      const seen = new Set()
      const fields = []
      for (const s of catSites) {
        const agentFields = agentFieldDefs[s.agent_type] || []
        for (const f of agentFields) {
          if (!seen.has(f.key)) {
            seen.add(f.key)
            fields.push(f)
          }
        }
      }
      map[cat] = fields
    }
    return map
  }, [categoryGroups, agentFieldDefs])

  const totalSites = sites.length
  const activeSites = sites.filter(s => s.is_active).length
  const agentCounts = useMemo(() => {
    const counts = {}
    for (const s of sites) {
      counts[s.agent_type] = (counts[s.agent_type] || 0) + 1
    }
    return counts
  }, [sites])

  if (loading) {
    return (
      <div className="page-container">
        <h1 className="page-title">📊 수집 설정 매트릭스</h1>
        <p style={{color:'var(--text-secondary)'}}>데이터를 불러오는 중...</p>
      </div>
    )
  }

  return (
    <div className="page-container">
      <h1 className="page-title">📊 수집 설정 매트릭스</h1>
      <p className="page-subtitle">
        수집 대상 사이트별 수집항목 설정 현황을 한눈에 확인합니다.
      </p>

      {/* ── 요약 카드 ── */}
      <div className="matrix-summary">
        <div className="matrix-stat-card">
          <div className="matrix-stat-value">{totalSites}</div>
          <div className="matrix-stat-label">전체 사이트</div>
        </div>
        <div className="matrix-stat-card">
          <div className="matrix-stat-value" style={{color:'var(--success-color, #059669)'}}>{activeSites}</div>
          <div className="matrix-stat-label">활성</div>
        </div>
        {Object.entries(agentCounts).map(([agent, count]) => (
          <div className="matrix-stat-card" key={agent}>
            <div className="matrix-stat-value">{count}</div>
            <div className="matrix-stat-label">{AGENT_LABELS[agent] || agent}</div>
          </div>
        ))}
      </div>

      {/* ── 필터 바 ── */}
      <div className="matrix-filter-bar">
        <label>
          <span>에이전트</span>
          <select value={filterAgent} onChange={e => setFilterAgent(e.target.value)}>
            <option value="all">전체</option>
            {allAgents.map(a => (
              <option key={a} value={a}>{AGENT_LABELS[a] || a} ({agentCounts[a] || 0})</option>
            ))}
          </select>
        </label>
        <label>
          <span>카테고리</span>
          <select value={filterCategory} onChange={e => setFilterCategory(e.target.value)}>
            <option value="all">전체</option>
            {categories.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
        <span className="matrix-filter-count">
          {filtered.length}건 표시
        </span>
      </div>

      {/* ── 카테고리별 매트릭스 테이블 ── */}
      {Object.entries(categoryGroups).map(([cat, catSites]) => {
        const fields = categoryFieldsMap[cat] || []

        return (
          <div className="matrix-agent-section" key={cat}>
            <h3 className="matrix-agent-title">
              <span className="matrix-category-badge">{cat}</span>
              <span className="matrix-agent-count">{catSites.length}개 사이트</span>
            </h3>

            <div className="matrix-table-scroll">
              <table className="matrix-table">
                <thead>
                  <tr>
                    <th className="matrix-th-fixed matrix-col-num">#</th>
                    <th className="matrix-th-fixed matrix-col-name">사이트명</th>
                    <th className="matrix-th-fixed matrix-col-url">URL</th>
                    <th className="matrix-th-fixed matrix-col-agent">Agent</th>
                    <th className="matrix-th-fixed matrix-col-schedule">수집주기</th>
                    <th className="matrix-th-fixed matrix-col-date">설정일</th>
                    <th className="matrix-th-fixed matrix-col-date">변경일</th>
                    <th className="matrix-th-fixed matrix-col-date">최근수집일</th>
                    {fields.map(f => (
                      <th key={f.key} className="matrix-th-field" title={f.key}>
                        <div className="matrix-field-header">{f.label}</div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {catSites.map((site, idx) => {
                    const siteAgentFields = new Set((agentFieldDefs[site.agent_type] || []).map(f => f.key))
                    return (
                      <tr key={site.id} className={site.is_active ? '' : 'matrix-row-inactive'}>
                        <td className="matrix-td-num">{idx + 1}</td>
                        <td className="matrix-td-name" title={site.site_name}>
                          {site.is_active
                            ? site.site_name
                            : <span style={{opacity:0.5}}>{site.site_name} (비활성)</span>
                          }
                        </td>
                        <td className="matrix-td-url" title={site.site_url}>
                          {site.site_url ? site.site_url.replace(/^https?:\/\//, '').slice(0, 35) : '-'}
                        </td>
                        <td className="matrix-td-agent">
                          <span className={`badge ${site.agent_type === 'product' ? 'dp' : site.agent_type === 'banner' ? 'running' : site.agent_type === 'order' ? 'pending' : 'success'}`}>
                            {AGENT_LABELS[site.agent_type] || site.agent_type}
                          </span>
                        </td>
                        <td className="matrix-td-schedule">
                          {SCHEDULE_LABELS[site.crawl_schedule || ''] || site.crawl_schedule || '-'}
                        </td>
                        <td className="matrix-td-date">
                          {formatDate(site.created_at)}
                        </td>
                        <td className="matrix-td-date">
                          {formatDate(site.updated_at)}
                        </td>
                        <td className="matrix-td-date matrix-td-last-crawl">
                          {lastCrawlMap[site.id] ? formatDate(lastCrawlMap[site.id]) : '-'}
                        </td>
                        {fields.map(f => {
                          if (!siteAgentFields.has(f.key)) {
                            return <td key={f.key} className="matrix-td-field matrix-td-na">-</td>
                          }
                          const fieldDef = (agentFieldDefs[site.agent_type] || []).find(d => d.key === f.key)
                          const collected = isFieldCollected(site, f.key, fieldDef?.config_key || '')
                          return (
                            <td key={f.key} className={`matrix-td-field ${collected ? 'matrix-collected' : ''}`}>
                              {collected ? 'O' : ''}
                            </td>
                          )
                        })}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )
      })}

      {Object.keys(categoryGroups).length === 0 && (
        <div style={{textAlign:'center',padding:40,color:'var(--text-secondary)'}}>
          조건에 맞는 사이트가 없습니다.
        </div>
      )}
    </div>
  )
}
