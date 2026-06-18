import { useState, useEffect, useCallback, useRef, useMemo } from 'react'

const SCHEDULE_OPTIONS = [
  { value: '',       label: '미설정' },
  { value: 'hourly', label: '시간' },
  { value: 'daily',  label: '일간' },
  { value: 'weekly', label: '주간' },
  { value: 'monthly',label: '월간' },
]

const SCHEDULE_LABELS = {
  '': '미설정', hourly: '시간', daily: '일간', weekly: '주간', monthly: '월간',
}

const CATEGORY_LABELS = {
  '트렌드매장':       { icon: '\u{1F6CD}\u{FE0F}', color: '#3b82f6' },
  '트렌드Global매장': { icon: '\u{1F30D}', color: '#8b5cf6' },
  '경쟁사':           { icon: '\u{1F3E2}', color: '#ef4444' },
  '경쟁사중국':       { icon: '\u{1F1E8}\u{1F1F3}', color: '#f97316' },
  '경쟁사이벤트':     { icon: '\u{1F389}', color: '#ec4899' },
  '브랜드공식':       { icon: '\u{2B50}', color: '#eab308' },
  '네이버스토어':     { icon: '\u{1F4E6}', color: '#22c55e' },
  '당사온라인몰':     { icon: '\u{1F3E0}', color: '#06b6d4' },
  '경쟁사배너':       { icon: '\u{1F5BC}\u{FE0F}', color: '#f43f5e' },
  '브랜드목록':       { icon: '\u{1F4CB}', color: '#0ea5e9' },
  '뉴스':             { icon: '\u{1F4F0}', color: '#64748b' },
  '카페':             { icon: '\u{2615}', color: '#a855f7' },
  '주문서':           { icon: '\u{1F4B3}', color: '#059669' },
  '쿠폰':             { icon: '\u{1F3AB}', color: '#d97706' },
}


/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   확인 대화상자 (Confirm Modal)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function ConfirmModal({ title, message, detail, confirmLabel, confirmType, onConfirm, onCancel }) {
  return (
    <div className="modal-overlay" style={{zIndex:2000}} onClick={onCancel}>
      <div className="confirm-dialog" onClick={e => e.stopPropagation()}>
        <div className="confirm-icon">
          {confirmType === 'danger' ? '⚠️' : confirmType === 'run' ? '▶️' : 'ℹ️'}
        </div>
        <h3 className="confirm-title">{title || '변경 확인'}</h3>
        <p className="confirm-message">{message}</p>
        {detail && <div className="confirm-detail">{detail}</div>}
        <div className="confirm-actions">
          <button className="btn btn-outline" onClick={onCancel}>취소</button>
          <button
            className={`btn ${confirmType === 'danger' ? 'btn-danger' : 'btn-primary'}`}
            onClick={onConfirm}
          >
            {confirmLabel || '확인'}
          </button>
        </div>
      </div>
    </div>
  )
}


export default function SiteSettings() {
  const [sites, setSites] = useState([])
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [configEdit, setConfigEdit] = useState(null)
  const [filterCat, setFilterCat] = useState('')
  const [runningStatus, setRunningStatus] = useState([])
  const [runResults, setRunResults] = useState(null)
  const [logView, setLogView] = useState(null)  // { siteId, siteName }
  // 확인 대화상자 상태
  const [confirmState, setConfirmState] = useState(null)
  const [agentFieldDefs, setAgentFieldDefs] = useState({})

  const showConfirm = ({ title, message, detail, confirmLabel, confirmType, onConfirm }) => {
    setConfirmState({ title, message, detail, confirmLabel, confirmType, onConfirm })
  }
  const closeConfirm = () => setConfirmState(null)

  const loadSites = () => {
    setLoading(true)
    Promise.all([
      fetch('/api/sites').then(r => r.json()),
      fetch('/api/agent-fields').then(r => r.json()),
    ])
      .then(([data, fieldDefs]) => {
        setSites(data)
        setAgentFieldDefs(fieldDefs)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }

  const loadRunningStatus = useCallback(() => {
    fetch('/api/crawl/status')
      .then(r => r.json())
      .then(data => setRunningStatus(data))
      .catch(() => {})
  }, [])

  useEffect(() => {
    loadSites()
    loadRunningStatus()
    const interval = setInterval(loadRunningStatus, 5000)
    return () => clearInterval(interval)
  }, [loadRunningStatus])

  const toggleActive = (id) => {
    const site = sites.find(s => s.id === id)
    const nextState = site.is_active ? '비활성화' : '활성화'
    showConfirm({
      title: '상태 변경',
      message: `"${site.site_name}" 사이트를 ${nextState}하시겠습니까?`,
      confirmLabel: nextState,
      confirmType: site.is_active ? 'danger' : 'default',
      onConfirm: async () => {
        closeConfirm()
        await fetch(`/api/sites/${id}/toggle`, { method: 'PUT' })
        loadSites()
      },
    })
  }

  const openConfig = async (id) => {
    const res = await fetch(`/api/sites/${id}`)
    const site = await res.json()
    setConfigEdit({
      id,
      name: site.site_name,
      url: site.site_url,
      agent_type: site.agent_type,
      config: site.crawl_config || {},
      keywords: site.keywords || [],
      credentials: site.credentials || [],
    })
  }

  const updateSchedule = (siteId, schedule) => {
    const site = sites.find(s => s.id === siteId)
    const label = SCHEDULE_LABELS[schedule] || '미설정'
    showConfirm({
      title: '수집 주기 변경',
      message: `"${site.site_name}" 사이트의 수집 주기를 변경하시겠습니까?`,
      detail: `수집 주기: ${SCHEDULE_LABELS[site.crawl_schedule || ''] || '미설정'} → ${label}`,
      confirmLabel: '변경',
      onConfirm: async () => {
        closeConfirm()
        await fetch(`/api/sites/${siteId}/schedule`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ schedule }),
        })
        loadSites()
      },
    })
  }

  // 크롤링 실행
  const requestRunCrawl = (siteIds, description) => {
    if (!siteIds.length) return
    const names = siteIds.map(id => {
      const s = sites.find(x => x.id === id)
      return s ? s.site_name : `#${id}`
    })
    const summary = names.length <= 5
      ? names.join(', ')
      : `${names.slice(0, 5).join(', ')} 외 ${names.length - 5}개`

    showConfirm({
      title: '크롤링 실행',
      message: `${description || '선택한 사이트'}의 크롤링을 실행하시겠습니까?`,
      detail: `대상: ${summary} (${siteIds.length}개)`,
      confirmLabel: '실행',
      confirmType: 'run',
      onConfirm: async () => {
        closeConfirm()
        setRunResults(null)
        try {
          const res = await fetch('/api/crawl/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ site_ids: siteIds, use_proxy: true }),
          })
          const data = await res.json()
          setRunResults(data.results)
          loadRunningStatus()
          setTimeout(() => setRunResults(null), 5000)
        } catch {
          setRunResults([{ status: 'error', message: '실행 요청 실패' }])
          setTimeout(() => setRunResults(null), 5000)
        }
      },
    })
  }

  const isRunning = (siteId) => runningStatus.some(r => r.site_id === siteId)

  // 크롤링 종료
  const requestStopCrawl = (siteId, siteName) => {
    showConfirm({
      title: '크롤링 중지',
      message: `"${siteName}" 크롤링을 중지하시겠습니까?`,
      detail: '실행 중인 수집 작업이 즉시 종료됩니다',
      confirmLabel: '중지',
      confirmType: 'danger',
      onConfirm: async () => {
        closeConfirm()
        try {
          const res = await fetch('/api/crawl/stop', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ site_ids: [siteId] }),
          })
          const data = await res.json()
          setRunResults(data.results)
          // 즉시 running 상태에서 제거하여 ▶ 버튼으로 전환
          setRunningStatus(prev => prev.filter(r => r.site_id !== siteId))
          // 서버와 동기화 (백업)
          setTimeout(loadRunningStatus, 500)
          setTimeout(() => setRunResults(null), 3000)
        } catch {
          setRunResults([{ status: 'error', message: '중지 요청 실패' }])
          setTimeout(() => setRunResults(null), 3000)
        }
      },
    })
  }

  if (loading) return <div className="loading">Loading...</div>

  const categories = [...new Set(sites.map(s => s.category || '(미분류)'))]
  const filtered = filterCat
    ? sites.filter(s => (s.category || '(미분류)') === filterCat)
    : sites

  const grouped = {}
  filtered.forEach(s => {
    const cat = s.category || '(미분류)'
    if (!grouped[cat]) grouped[cat] = []
    grouped[cat].push(s)
  })

  const scheduleGroups = {}
  sites.forEach(s => {
    const sch = s.crawl_schedule || ''
    if (sch) {
      if (!scheduleGroups[sch]) scheduleGroups[sch] = []
      scheduleGroups[sch].push(s)
    }
  })

  return (
    <>
      <div className="page-header">
        <h1>수집 대상 설정</h1>
        <p>크롤링 사이트를 카테고리별로 관리합니다 ({sites.length}개 사이트)</p>
      </div>

      {/* 실행 결과 알림 */}
      {runResults && (
        <div className="run-results-bar">
          {runResults.map((r, i) => (
            <span key={i} className={`run-result-item ${r.status}`}>
              {r.status === 'started' ? '✅' : r.status === 'already_running' ? '🔄' : '❌'}{' '}
              {r.message}
            </span>
          ))}
        </div>
      )}

      {/* 실행 상태 바 */}
      {runningStatus.length > 0 && (
        <div className="running-status-bar">
          <span style={{fontWeight:600,fontSize:13}}>{'🔄'} 실행 중 ({runningStatus.length})</span>
          {runningStatus.map(r => (
            <span key={r.pid} className="badge running" style={{fontSize:11}}>
              {r.site_name} (PID: {r.pid})
            </span>
          ))}
        </div>
      )}

      {/* 일괄 실행 영역 */}
      <div className="card" style={{marginBottom:16}}>
        <div className="card-header">
          <h2 style={{fontSize:15}}>{'⚡'} 수집 실행</h2>
        </div>
        <div className="card-body" style={{padding:'12px 20px'}}>
          <div style={{display:'flex',gap:12,alignItems:'center',flexWrap:'wrap'}}>
            <button
              className="btn btn-primary btn-sm"
              onClick={() => {
                const activeIds = sites.filter(s => s.is_active).map(s => s.id)
                requestRunCrawl(activeIds, '전체 활성 사이트')
              }}
              disabled={sites.filter(s => s.is_active).length === 0}
            >
              {'▶'} 전체 실행 ({sites.filter(s => s.is_active).length})
            </button>

            <span style={{color:'var(--border)',fontSize:16}}>|</span>

            <span style={{fontSize:12,color:'var(--text-secondary)',fontWeight:600}}>주기별:</span>
            {Object.entries(scheduleGroups).map(([sch, schSites]) => (
              <button
                key={sch}
                className="btn btn-outline btn-sm"
                onClick={() => {
                  const ids = schSites.filter(s => s.is_active).map(s => s.id)
                  requestRunCrawl(ids, `${SCHEDULE_LABELS[sch]} 주기 사이트`)
                }}
                title={`${schSites.map(s => s.site_name).join(', ')}`}
              >
                {'📅'} {SCHEDULE_LABELS[sch]} ({schSites.filter(s => s.is_active).length})
              </button>
            ))}
            {Object.keys(scheduleGroups).length === 0 && (
              <span style={{fontSize:12,color:'var(--text-secondary)'}}>주기 설정된 사이트 없음</span>
            )}
          </div>
        </div>
      </div>

      {/* 카테고리 필터 */}
      <div className="filter-bar">
        <button
          className={`btn btn-sm ${!filterCat ? 'btn-primary' : 'btn-outline'}`}
          onClick={() => setFilterCat('')}
        >
          전체 ({sites.length})
        </button>
        {categories.map(cat => {
          const info = CATEGORY_LABELS[cat] || { icon: '\u{1F4C1}', color: '#64748b' }
          const cnt = sites.filter(s => (s.category || '(미분류)') === cat).length
          return (
            <button
              key={cat}
              className={`btn btn-sm ${filterCat === cat ? 'btn-primary' : 'btn-outline'}`}
              onClick={() => setFilterCat(cat)}
            >
              {info.icon} {cat} ({cnt})
            </button>
          )
        })}
        <div style={{marginLeft:'auto'}}>
          <button className="btn btn-primary btn-sm" onClick={() => setShowAdd(true)}>
            + 사이트 추가
          </button>
        </div>
      </div>

      {/* 카테고리별 사이트 테이블 */}
      {Object.entries(grouped).map(([cat, catSites]) => {
        const info = CATEGORY_LABELS[cat] || { icon: '\u{1F4C1}', color: '#64748b' }
        const activeIds = catSites.filter(s => s.is_active).map(s => s.id)
        return (
          <div className="card" key={cat}>
            <div className="card-header">
              <h2 style={{display:'flex',alignItems:'center',gap:8}}>
                <span style={{
                  display:'inline-flex',alignItems:'center',justifyContent:'center',
                  width:28,height:28,borderRadius:6,fontSize:16,
                  background:`${info.color}18`,
                }}>{info.icon}</span>
                {cat}
                <span style={{fontSize:13,fontWeight:400,color:'var(--text-secondary)',marginLeft:8}}>
                  {catSites.length}개
                </span>
              </h2>
              <button
                className="btn btn-outline btn-sm"
                onClick={() => requestRunCrawl(activeIds, `${cat} 카테고리`)}
                disabled={activeIds.length === 0}
                title={`${cat} 카테고리 활성 사이트 일괄 실행`}
              >
                {'▶'} 일괄 실행 ({activeIds.length})
              </button>
            </div>
            <div className="card-body no-pad">
              <table className="data-table">
                <thead>
                  <tr>
                    <th style={{width:40}}>ID</th>
                    <th>사이트명</th>
                    <th>URL</th>
                    <th style={{width:80}}>에이전트</th>
                    <th style={{width:100}}>수집 주기</th>
                    <th style={{width:60}}>상태</th>
                    <th style={{width:50}}>설정</th>
                    <th style={{width:80}}>실행</th>
                  </tr>
                </thead>
                <tbody>
                  {catSites.map(s => {
                    const running = isRunning(s.id)
                    return (
                      <tr key={s.id} className={running ? 'row-running' : ''}>
                        <td>{s.id}</td>
                        <td style={{fontWeight:600}}>
                          {s.site_name}
                          {running && <span className="badge running" style={{fontSize:10,marginLeft:6}}>실행중</span>}
                        </td>
                        <td style={{maxWidth:260,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
                          <a href={s.site_url} target="_blank" rel="noreferrer"
                             style={{color:'var(--primary)',textDecoration:'none',fontSize:12}}>
                            {s.site_url}
                          </a>
                        </td>
                        <td>
                          <span className={`badge ${AGENT_BADGE_CLASS[s.agent_type] || 'dp'}`}>
                            {s.agent_type}
                          </span>
                        </td>
                        <td>
                          <select
                            className="schedule-select"
                            value={s.crawl_schedule || ''}
                            onChange={e => updateSchedule(s.id, e.target.value)}
                          >
                            {SCHEDULE_OPTIONS.map(opt => (
                              <option key={opt.value} value={opt.value}>{opt.label}</option>
                            ))}
                          </select>
                        </td>
                        <td>
                          <label className="toggle">
                            <input type="checkbox" checked={!!s.is_active} onChange={() => toggleActive(s.id)} />
                            <span className="slider"></span>
                          </label>
                        </td>
                        <td>
                          <button className="btn btn-outline btn-sm" onClick={() => openConfig(s.id)}>
                            설정
                          </button>
                        </td>
                        <td style={{whiteSpace:'nowrap'}}>
                          {running ? (
                            <button
                              className="btn btn-sm btn-stop"
                              onClick={() => requestStopCrawl(s.id, s.site_name)}
                              title="크롤링 중지"
                            >
                              ■
                            </button>
                          ) : (
                            <button
                              className="btn btn-sm btn-run"
                              onClick={() => requestRunCrawl([s.id], `${s.site_name}`)}
                              disabled={!s.is_active}
                              title={!s.is_active ? '비활성 사이트' : '크롤링 실행'}
                            >
                              ▶
                            </button>
                          )}
                          {' '}
                          <button
                            className="btn btn-outline btn-sm"
                            onClick={() => setLogView({ siteId: s.id, siteName: s.site_name })}
                            title="크롤링 로그 보기"
                            style={{fontSize:12,padding:'2px 6px'}}
                          >
                            📋
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )
      })}

      {showAdd && (
        <AddSiteModal
          categories={categories}
          onClose={() => setShowAdd(false)}
          onSaved={loadSites}
          showConfirm={showConfirm}
          closeConfirm={closeConfirm}
          agentFieldDefs={agentFieldDefs}
        />
      )}

      {configEdit && (
        <ConfigModal
          site={configEdit}
          onClose={() => setConfigEdit(null)}
          onSaved={() => { setConfigEdit(null); loadSites() }}
          showConfirm={showConfirm}
          closeConfirm={closeConfirm}
          agentFieldDefs={agentFieldDefs}
        />
      )}

      {/* 확인 대화상자 */}
      {logView && (
        <LogViewerModal
          siteId={logView.siteId}
          siteName={logView.siteName}
          onClose={() => setLogView(null)}
        />
      )}

      {confirmState && (
        <ConfirmModal
          title={confirmState.title}
          message={confirmState.message}
          detail={confirmState.detail}
          confirmLabel={confirmState.confirmLabel}
          confirmType={confirmState.confirmType}
          onConfirm={confirmState.onConfirm}
          onCancel={closeConfirm}
        />
      )}
    </>
  )
}


/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   크롤링 로그 뷰어 모달
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function LogViewerModal({ siteId, siteName, onClose }) {
  const [logData, setLogData] = useState(null)
  const [error, setError] = useState(null)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const logEndRef = useRef(null)

  const fetchLog = async () => {
    try {
      const res = await fetch(`/api/crawl/logs/${siteId}?tail=500`)
      if (res.status === 404) {
        setError('로그 파일이 없습니다. 크롤링을 실행해 주세요.')
        setLogData(null)
        return
      }
      if (!res.ok) { setError('로그 조회 실패'); return }
      const data = await res.json()
      setLogData(data)
      setError(null)
      // 실행 완료 시 자동 새로고침 중지
      if (!data.is_running) setAutoRefresh(false)
    } catch {
      setError('서버 연결 실패')
    }
  }

  useEffect(() => { fetchLog() }, [])

  useEffect(() => {
    if (!autoRefresh) return
    const timer = setInterval(fetchLog, 2000)
    return () => clearInterval(timer)
  }, [autoRefresh])

  useEffect(() => {
    if (logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logData?.content])

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal log-viewer-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3 style={{display:'flex',alignItems:'center',gap:8}}>
            📋 {siteName} 크롤링 로그
            {logData?.is_running && <span className="badge dp" style={{fontSize:10,animation:'pulse 1.5s infinite'}}>실행 중</span>}
            {logData && !logData.is_running && <span className="badge tess" style={{fontSize:10}}>완료</span>}
          </h3>
          <button className="modal-close" onClick={onClose}>x</button>
        </div>
        <div className="modal-body" style={{padding:0}}>
          {/* 상태 바 */}
          <div className="log-viewer-toolbar">
            {logData && (
              <span className="log-viewer-info">
                {logData.log_file} | {logData.total_lines}줄
                {logData.showing_lines < logData.total_lines && ` (최근 ${logData.showing_lines}줄 표시)`}
              </span>
            )}
            <div style={{display:'flex',gap:8,alignItems:'center'}}>
              <label style={{fontSize:12,display:'flex',alignItems:'center',gap:4,cursor:'pointer'}}>
                <input type="checkbox" checked={autoRefresh} onChange={e => setAutoRefresh(e.target.checked)} />
                자동 새로고침
              </label>
              <button className="btn btn-outline btn-sm" onClick={fetchLog} style={{fontSize:11,padding:'2px 8px'}}>
                새로고침
              </button>
            </div>
          </div>

          {/* 로그 내용 */}
          <div className="log-viewer-content">
            {error && <div className="log-viewer-empty">{error}</div>}
            {!error && !logData && <div className="log-viewer-empty">로딩 중...</div>}
            {logData && !logData.content && <div className="log-viewer-empty">로그가 비어있습니다 (수집 준비 중...)</div>}
            {logData?.content && (
              <pre className="log-viewer-pre">
                {logData.content}
                <span ref={logEndRef} />
              </pre>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}


/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   에이전트 유형별 설정 모달
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
const AGENT_BADGE_CLASS = {
  product: 'dp', news: 'pending', cafe: 'tess', promotion: 'promo', banner: 'banner-badge', directory: 'dir-badge', order: 'order-badge', coupon: 'coupon-badge',
}


/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   URL 자동 분석 패널 (공용 컴포넌트)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function UrlAnalyzePanel({ url, existingFieldKeys, textColor, onExistingFieldsFound, onExtraFieldsChange, onAnalyzeComplete, savedExtraFields }) {
  const [analyzing, setAnalyzing] = useState(false)
  const [analyzeResult, setAnalyzeResult] = useState(null)
  const [discoveredFields, setDiscoveredFields] = useState(() => {
    if (savedExtraFields && savedExtraFields.length > 0) {
      return savedExtraFields.map(f => ({
        raw_key: f.raw_key, standard_key: f.standard_key, label: f.label,
        value_preview: f.value_preview || '',
      }))
    }
    return []
  })
  const [discoveredChecked, setDiscoveredChecked] = useState(() => {
    if (savedExtraFields && savedExtraFields.length > 0) {
      const init = {}
      savedExtraFields.forEach(f => { init[f.standard_key] = true })
      return init
    }
    return {}
  })

  const handleAnalyze = async () => {
    if (!url) return
    setAnalyzing(true)
    setAnalyzeResult(null)
    setDiscoveredFields([])
    setDiscoveredChecked({})
    try {
      const res = await fetch('/api/sites/analyze-url', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      })
      const data = await res.json()
      setAnalyzeResult(data)

      if (data.status === 'success') {
        const existingSet = new Set(existingFieldKeys || [])
        const discovered = (data.discovered_fields || []).filter(
          f => !existingSet.has(f.standard_key)
        )
        setDiscoveredFields(discovered)

        const initChecked = {}
        discovered.forEach(f => { initChecked[f.standard_key] = true })
        setDiscoveredChecked(initChecked)

        if (onExistingFieldsFound) {
          const foundKeys = new Set((data.discovered_fields || []).map(f => f.standard_key))
          onExistingFieldsFound(foundKeys)
        }

        if (onExtraFieldsChange && discovered.length > 0) {
          onExtraFieldsChange(discovered.map(f => ({
            raw_key: f.raw_key, standard_key: f.standard_key, label: f.label,
          })))
        }

        if (onAnalyzeComplete) onAnalyzeComplete(data)
      }
    } catch {
      setAnalyzeResult({ status: 'error', error: '분석 요청 실패' })
    } finally {
      setAnalyzing(false)
    }
  }

  const toggleDiscovered = (stdKey) => {
    const next = { ...discoveredChecked, [stdKey]: !discoveredChecked[stdKey] }
    setDiscoveredChecked(next)
    if (onExtraFieldsChange) {
      onExtraFieldsChange(
        discoveredFields
          .filter(f => next[f.standard_key])
          .map(f => ({ raw_key: f.raw_key, standard_key: f.standard_key, label: f.label }))
      )
    }
  }

  const labelColor = textColor || 'var(--text)'

  return (
    <>
      <div style={{marginBottom:12}}>
        <button
          className="btn btn-outline btn-sm url-analyze-btn"
          onClick={handleAnalyze}
          disabled={analyzing || !url}
          style={{width:'100%',justifyContent:'center'}}
          title="URL을 방문하여 수집 가능한 데이터를 분석합니다"
        >
          {analyzing ? (
            <><span className="url-analyze-spinner" /> 분석중...</>
          ) : (
            <><span style={{fontSize:14}}>{'🔍'}</span> URL 분석하여 수집 가능 항목 확인</>
          )}
        </button>
      </div>

      {analyzing && (
        <div className="url-analyze-progress">
          <div className="url-analyze-progress-bar">
            <div className="url-analyze-progress-fill" />
          </div>
          <p>페이지를 방문하여 수집 가능한 데이터를 분석하고 있습니다...</p>
          <p style={{fontSize:11,color:'var(--text-secondary)'}}>최대 30초 소요될 수 있습니다</p>
        </div>
      )}

      {analyzeResult && !analyzing && (
        <div className={`url-analyze-result ${analyzeResult.status === 'success' ? 'success' : 'error'}`}>
          {analyzeResult.status === 'success' ? (
            <>
              <div className="url-analyze-result-header">
                <span>{'✅'} 분석 완료</span>
                <span className="url-analyze-elapsed">{analyzeResult.elapsed}초</span>
              </div>
              {analyzeResult.page_title && (
                <div className="url-analyze-page-title">{analyzeResult.page_title}</div>
              )}
              <div className="url-analyze-summary">
                {analyzeResult.products && (
                  <span className="url-analyze-tag products">
                    {'📦'} 상품 {analyzeResult.products.count}개
                    <span className="url-analyze-tag-method">{analyzeResult.products.method}</span>
                  </span>
                )}
                {analyzeResult.banners && (
                  <span className="url-analyze-tag banners">
                    {'🖼️'} 배너 {analyzeResult.banners.count}개
                  </span>
                )}
                {analyzeResult.directory && (
                  <span className="url-analyze-tag directory">
                    {'📋'} 목록 {analyzeResult.directory.count}개
                  </span>
                )}
                {!analyzeResult.products && !analyzeResult.banners && !analyzeResult.directory && (
                  <span style={{fontSize:12,color:'var(--text-secondary)'}}>탐지된 데이터가 없습니다</span>
                )}
              </div>
            </>
          ) : analyzeResult.status === 'blocked' ? (
            <div className="url-analyze-result-header">
              <span>{'🚫'} 접근 차단됨 ({analyzeResult.error || 'HTTP 403/429'})</span>
            </div>
          ) : (
            <div className="url-analyze-result-header">
              <span>{'❌'} 분석 실패: {analyzeResult.error || '알 수 없는 오류'}</span>
            </div>
          )}
        </div>
      )}

      {discoveredFields.length > 0 && (
        <div style={{marginBottom:12}}>
          <div style={{fontSize:12,fontWeight:600,color:labelColor,marginBottom:6,display:'flex',alignItems:'center',gap:6}}>
            {analyzeResult ? '🔍' : '📌'} {analyzeResult ? 'URL 분석으로 발견된 추가 필드' : '저장된 추가 수집 필드'}
            <span style={{fontSize:10,fontWeight:400,opacity:0.7}}>({discoveredFields.length}개)</span>
          </div>
          <div className="field-checkbox-grid">
            {discoveredFields.map(f => (
              <label key={f.standard_key}
                className={`field-checkbox discovered ${discoveredChecked[f.standard_key] ? 'checked' : ''}`}
                title={f.value_preview ? `미리보기: ${f.value_preview}` : f.raw_key}
              >
                <input
                  type="checkbox"
                  checked={!!discoveredChecked[f.standard_key]}
                  onChange={() => toggleDiscovered(f.standard_key)}
                />
                <span>{f.label}</span>
                <span className="field-badge-discovered">{analyzeResult ? '발견' : '저장됨'}</span>
              </label>
            ))}
          </div>
        </div>
      )}
    </>
  )
}


/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   로그인 계정 관리 (모든 에이전트 공통)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function CredentialManager({ siteId, credentials: initialCreds, showConfirm, closeConfirm }) {
  const [creds, setCreds] = useState(initialCreds || [])
  const [showForm, setShowForm] = useState(false)
  const [editId, setEditId] = useState(null)
  const [form, setForm] = useState({ login_id: '', login_pwd: '', label: '' })
  const [showPwd, setShowPwd] = useState({})

  const reload = async () => {
    try {
      const res = await fetch(`/api/sites/${siteId}/credentials`)
      if (res.ok) setCreds(await res.json())
    } catch {}
  }

  const resetForm = () => {
    setForm({ login_id: '', login_pwd: '', label: '' })
    setEditId(null)
    setShowForm(false)
  }

  const handleSave = async () => {
    if (!form.login_id.trim() || !form.login_pwd.trim()) {
      alert('ID와 비밀번호를 입력해주세요.')
      return
    }
    const isEdit = editId !== null
    const url = isEdit
      ? `/api/sites/credentials/${editId}`
      : `/api/sites/${siteId}/credentials`
    const method = isEdit ? 'PUT' : 'POST'
    try {
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      if (!res.ok) throw new Error()
      resetForm()
      reload()
    } catch {
      alert('계정 저장에 실패했습니다.')
    }
  }

  const startEdit = (c) => {
    setForm({ login_id: c.login_id, login_pwd: c.login_pwd, label: c.label || '' })
    setEditId(c.id)
    setShowForm(true)
  }

  const handleDelete = (c) => {
    showConfirm({
      title: '계정 삭제',
      message: `"${c.login_id}" 계정을 삭제하시겠습니까?`,
      confirmLabel: '삭제',
      confirmType: 'danger',
      onConfirm: async () => {
        closeConfirm()
        try {
          await fetch(`/api/sites/credentials/${c.id}`, { method: 'DELETE' })
          reload()
        } catch {}
      },
    })
  }

  const handleToggle = async (c) => {
    try {
      await fetch(`/api/sites/credentials/${c.id}/toggle`, { method: 'PUT' })
      reload()
    } catch {}
  }

  const togglePwd = (id) => setShowPwd(prev => ({ ...prev, [id]: !prev[id] }))

  return (
    <div className="credential-section">
      <div className="credential-header">
        <h4 className="config-section-title" style={{margin:0}}>
          로그인 계정
          <span style={{fontSize:12,color:'var(--text-secondary)',fontWeight:400,marginLeft:6}}>
            ({creds.length}개)
          </span>
        </h4>
        {!showForm && (
          <button className="btn btn-outline btn-xs" onClick={() => { resetForm(); setShowForm(true) }}>
            + 추가
          </button>
        )}
      </div>
      <p className="config-section-desc">
        로그인이 필요한 사이트의 계정을 등록합니다. 여러 계정을 등록하면 크롤링 시 순환 사용됩니다.
      </p>

      {creds.length > 0 && (
        <table className="credential-table">
          <thead>
            <tr>
              <th>라벨</th><th>ID</th><th>비밀번호</th><th>상태</th><th>최근 사용</th><th></th>
            </tr>
          </thead>
          <tbody>
            {creds.map(c => (
              <tr key={c.id} className={c.is_active ? '' : 'inactive-row'}>
                <td>{c.label || '-'}</td>
                <td><code>{c.login_id}</code></td>
                <td>
                  <span className="pwd-cell">
                    <code>{showPwd[c.id] ? c.login_pwd : '••••••'}</code>
                    <button className="btn-icon" onClick={() => togglePwd(c.id)} title={showPwd[c.id] ? '숨기기' : '보기'}>
                      {showPwd[c.id] ? '🙈' : '👁'}
                    </button>
                  </span>
                </td>
                <td>
                  <span
                    className={`badge ${c.is_active ? 'active' : 'inactive'}`}
                    style={{cursor:'pointer'}}
                    onClick={() => handleToggle(c)}
                    title="클릭하여 상태 변경"
                  >
                    {c.is_active ? '활성' : '비활성'}
                  </span>
                </td>
                <td style={{fontSize:12,color:'var(--text-secondary)'}}>
                  {c.last_used_at || '-'}
                </td>
                <td>
                  <span className="credential-actions">
                    <button className="btn-icon" onClick={() => startEdit(c)} title="수정">✏️</button>
                    <button className="btn-icon" onClick={() => handleDelete(c)} title="삭제">🗑️</button>
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {showForm && (
        <div className="credential-form">
          <div className="credential-form-title">
            {editId ? '계정 수정' : '새 계정 추가'}
          </div>
          <div className="credential-form-grid">
            <label>
              <span>라벨 (선택)</span>
              <input
                className="form-control"
                placeholder="예: 본계정, 테스트용"
                value={form.label}
                onChange={e => setForm(f => ({...f, label: e.target.value}))}
              />
            </label>
            <label>
              <span>로그인 ID <em>*</em></span>
              <input
                className="form-control"
                placeholder="아이디 입력"
                value={form.login_id}
                onChange={e => setForm(f => ({...f, login_id: e.target.value}))}
              />
            </label>
            <label>
              <span>비밀번호 <em>*</em></span>
              <input
                className="form-control"
                type="password"
                placeholder="비밀번호 입력"
                value={form.login_pwd}
                onChange={e => setForm(f => ({...f, login_pwd: e.target.value}))}
              />
            </label>
          </div>
          <div className="credential-form-actions">
            <button className="btn btn-outline btn-xs" onClick={resetForm}>취소</button>
            <button className="btn btn-primary btn-xs" onClick={handleSave}>
              {editId ? '수정' : '추가'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}


function ConfigModal({ site, onClose, onSaved, showConfirm, closeConfirm, agentFieldDefs }) {
  const agentType = site.agent_type
  const modalWidth = agentType === 'news' ? 560 : agentType === 'product' ? 580 : agentType === 'order' ? 600 : agentType === 'coupon' ? 580 : agentType === 'brand' ? 560 : agentType === 'local' ? 520 : 520

  const [editInfo, setEditInfo] = useState({ name: site.name, url: site.url })
  const [infoEditing, setInfoEditing] = useState(false)
  const [infoSaving, setInfoSaving] = useState(false)

  const infoChanged = editInfo.name !== site.name || editInfo.url !== site.url

  const handleSaveInfo = () => {
    if (!editInfo.name.trim() || !editInfo.url.trim()) return
    showConfirm({
      title: '사이트 정보 수정',
      message: `사이트명/URL을 변경하시겠습니까?`,
      detail: (editInfo.name !== site.name ? `이름: ${site.name} → ${editInfo.name}\n` : '')
            + (editInfo.url !== site.url ? `URL: ${site.url} → ${editInfo.url}` : ''),
      confirmLabel: '변경',
      onConfirm: async () => {
        closeConfirm()
        setInfoSaving(true)
        try {
          const body = {}
          if (editInfo.name !== site.name) body.site_name = editInfo.name.trim()
          if (editInfo.url !== site.url) body.site_url = editInfo.url.trim()
          await fetch(`/api/sites/${site.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          })
          setInfoEditing(false)
          onSaved()
        } catch (e) {
          alert('수정 실패: ' + (e.message || '네트워크 오류'))
        } finally {
          setInfoSaving(false)
        }
      },
    })
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{width: modalWidth}}>
        <div className="modal-header">
          <h3 style={{display:'flex',alignItems:'center',gap:8}}>
            {site.name}
            <span className={`badge ${AGENT_BADGE_CLASS[agentType] || 'dp'}`} style={{fontSize:11}}>
              {agentType}
            </span>
          </h3>
          <button className="modal-close" onClick={onClose}>x</button>
        </div>
        <div className="modal-body">
          {/* ── 사이트 정보 편집 ── */}
          <div className="site-info-edit-section">
            {!infoEditing ? (
              <div style={{display:'flex',alignItems:'center',gap:8,marginBottom:12,fontSize:13,color:'var(--text-secondary)'}}>
                <span style={{overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',maxWidth:380}}>{site.url}</span>
                <button
                  className="btn btn-outline btn-sm"
                  style={{fontSize:11,padding:'2px 8px',flexShrink:0}}
                  onClick={() => setInfoEditing(true)}
                >
                  편집
                </button>
              </div>
            ) : (
              <div style={{marginBottom:16,padding:'12px 14px',background:'var(--bg-secondary)',borderRadius:8,border:'1px solid var(--border)'}}>
                <div style={{marginBottom:8}}>
                  <label style={{fontSize:12,color:'var(--text-secondary)',display:'block',marginBottom:3}}>사이트명</label>
                  <input
                    type="text"
                    className="form-control"
                    value={editInfo.name}
                    onChange={e => setEditInfo({ ...editInfo, name: e.target.value })}
                    style={{width:'100%',padding:'6px 10px',fontSize:13}}
                  />
                </div>
                <div style={{marginBottom:10}}>
                  <label style={{fontSize:12,color:'var(--text-secondary)',display:'block',marginBottom:3}}>URL</label>
                  <input
                    type="text"
                    className="form-control"
                    value={editInfo.url}
                    onChange={e => setEditInfo({ ...editInfo, url: e.target.value })}
                    style={{width:'100%',padding:'6px 10px',fontSize:13}}
                  />
                </div>
                <div style={{display:'flex',gap:6,justifyContent:'flex-end'}}>
                  <button
                    className="btn btn-outline btn-sm"
                    style={{fontSize:11}}
                    onClick={() => { setEditInfo({ name: site.name, url: site.url }); setInfoEditing(false) }}
                  >
                    취소
                  </button>
                  <button
                    className="btn btn-primary btn-sm"
                    style={{fontSize:11}}
                    disabled={!infoChanged || infoSaving || !editInfo.name.trim() || !editInfo.url.trim()}
                    onClick={handleSaveInfo}
                  >
                    {infoSaving ? '저장 중...' : '정보 저장'}
                  </button>
                </div>
              </div>
            )}
          </div>

          {agentType === 'product'   && <ProductConfig   site={site} onSaved={onSaved} showConfirm={showConfirm} closeConfirm={closeConfirm} fieldDefs={agentFieldDefs['product'] || []} />}
          {agentType === 'news'      && <NewsConfig      site={site} onSaved={onSaved} showConfirm={showConfirm} closeConfirm={closeConfirm} />}
          {agentType === 'cafe'      && <CafeConfig      site={site} onSaved={onSaved} showConfirm={showConfirm} closeConfirm={closeConfirm} />}
          {agentType === 'promotion' && <PromotionConfig site={site} onSaved={onSaved} showConfirm={showConfirm} closeConfirm={closeConfirm} />}
          {agentType === 'banner'    && <BannerConfig    site={site} onSaved={onSaved} showConfirm={showConfirm} closeConfirm={closeConfirm} />}
          {agentType === 'directory' && <DirectoryConfig site={site} onSaved={onSaved} showConfirm={showConfirm} closeConfirm={closeConfirm} fieldDefs={agentFieldDefs['directory'] || []} />}
          {agentType === 'order'     && <OrderConfig     site={site} onSaved={onSaved} showConfirm={showConfirm} closeConfirm={closeConfirm} fieldDefs={agentFieldDefs['order'] || []} />}
          {agentType === 'coupon'    && <CouponConfig    site={site} onSaved={onSaved} showConfirm={showConfirm} closeConfirm={closeConfirm} />}
          {agentType === 'brand'     && <BrandConfig     site={site} onSaved={onSaved} showConfirm={showConfirm} closeConfirm={closeConfirm} fieldDefs={agentFieldDefs['brand'] || []} />}
          {agentType === 'local'     && <LocalConfig     site={site} onSaved={onSaved} showConfirm={showConfirm} closeConfirm={closeConfirm} fieldDefs={agentFieldDefs['local'] || []} />}
          <CredentialManager siteId={site.id} credentials={site.credentials} showConfirm={showConfirm} closeConfirm={closeConfirm} />
        </div>
      </div>
    </div>
  )
}


/* ── product: 상품/랭킹 수집 설정 (v2) ───────────── */

const LIST_TYPE_OPTIONS = [
  { value: 'ranking', label: '랭킹',       icon: '🏆', desc: '순위 기반 목록 (베스트, 인기순)' },
  { value: 'catalog', label: '카탈로그',    icon: '📦', desc: '일반 상품 목록 페이지' },
  { value: 'search',  label: '검색',       icon: '🔍', desc: '검색 결과 페이지' },
]

const PAGINATION_OPTIONS = [
  { value: 'scroll', label: '무한 스크롤', desc: '스크롤 시 상품 추가 로드' },
  { value: 'click',  label: '페이지 클릭', desc: '다음 페이지 버튼 클릭' },
  { value: 'api',    label: 'API',        desc: 'API 페이지 파라미터 변경' },
  { value: 'none',   label: '단일 페이지', desc: '현재 페이지만 수집' },
]

const DETAIL_FIELD_DEFS = [
  { key: 'category_breadcrumb', label: '카테고리 경로' },
  { key: 'reference_code',      label: '레퍼런스코드' },
  { key: 'product_code',        label: '상품코드' },
  { key: 'regular_price_usd',   label: '정상가(달러)' },
  { key: 'regular_price_krw',   label: '정상가(원화)' },
  { key: 'discount_rate',       label: '할인율' },
  { key: 'sale_price_usd',      label: '판매가(달러)' },
  { key: 'sale_price_krw',      label: '판매가(원화)' },
  { key: 'max_benefit_info',    label: '최대혜택가(프로모션)' },
  { key: 'benefits',            label: '구매혜택' },
  { key: 'related_products',    label: '관련상품' },
  { key: 'description',         label: '상품설명' },
  { key: 'detail_images',       label: '상세이미지' },
  { key: 'spec',                label: '제품스펙' },
]

function ProductConfig({ site, onSaved, showConfirm, closeConfirm, fieldDefs }) {
  const collectFieldDefs = fieldDefs.filter(f => f.config_key === 'collect_fields')
  const defaultFieldKeys = collectFieldDefs.slice(0, 4).map(f => f.key)

  const [config, setConfig] = useState(() => {
    const c = site.config || {}
    const merged = [...new Set([...(c.collect_fields || []), ...(c.optional_fields || [])])]
    return {
      collect_fields: merged.length > 0 ? merged : [...defaultFieldKeys],
      list_type: c.list_type || 'catalog',
      pagination: c.pagination || 'scroll',
      max_pages: c.max_pages ?? 5,
      max_items: c.max_items ?? 100,
      item_limit_type: (c.max_items === 0 || c.max_items === undefined) ? 'all' : 'n',
      detail_page: c.detail_page ?? false,
      detail_fields: (c.detail_fields && c.detail_fields.length > 0)
        ? c.detail_fields
        : (c.detail_page ? DETAIL_FIELD_DEFS.map(f => ({ key: f.key })) : []),
      extra_fields: c.extra_fields || [],
    }
  })
  const [saving, setSaving] = useState(false)
  const [extraFields, setExtraFields] = useState(config.extra_fields || [])

  const toggleField = (key) => {
    if (config.collect_fields.includes(key)) {
      setConfig({ ...config, collect_fields: config.collect_fields.filter(f => f !== key) })
    } else {
      setConfig({ ...config, collect_fields: [...config.collect_fields, key] })
    }
  }

  const isFieldChecked = (key) => {
    return config.collect_fields.includes(key)
  }

  const handleSave = () => {
    const listLabel = LIST_TYPE_OPTIONS.find(o => o.value === config.list_type)?.label || config.list_type
    showConfirm({
      title: '설정 저장',
      message: `"${site.name}" 사이트의 수집 설정을 변경하시겠습니까?`,
      detail: `목록 유형: ${listLabel} | 수집 필드: ${config.collect_fields.length}개`,
      confirmLabel: '저장',
      onConfirm: async () => {
        closeConfirm()
        setSaving(true)
        try {
          const payload = {
            collect_fields: config.collect_fields,
            list_type: config.list_type,
            pagination: config.pagination,
            max_pages: config.max_pages,
            max_items: config.item_limit_type === 'all' ? 0 : config.max_items,
            detail_page: config.detail_page,
            detail_fields: config.detail_fields,
          }
          if (extraFields.length > 0) payload.extra_fields = extraFields
          const res = await fetch(`/api/sites/${site.id}/config`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ crawl_config: payload }),
          })
          if (!res.ok) {
            alert('저장 실패: 서버 오류가 발생했습니다')
            return
          }
          onSaved()
        } catch (e) {
          alert('저장 실패: ' + (e.message || '네트워크 오류'))
        } finally {
          setSaving(false)
        }
      },
    })
  }

  return (
    <>
      <div style={{background:'#eff6ff',padding:'12px 16px',borderRadius:8,marginBottom:20,fontSize:13,color:'#1e40af'}}>
        상품 목록 페이지에서 상품 정보를 수집합니다. 수집 필드와 방식을 설정하세요.
      </div>

      {/* ── URL 분석 ── */}
      {site.url && (
        <UrlAnalyzePanel
          url={site.url}
          existingFieldKeys={collectFieldDefs.map(f => f.key)}
          textColor="#1d4ed8"
          savedExtraFields={config.extra_fields}
          onExistingFieldsFound={(foundKeys) => {
            setConfig(prev => {
              const existing = new Set(prev.collect_fields)
              const newFields = [...prev.collect_fields]
              collectFieldDefs.forEach(f => {
                if (foundKeys.has(f.key) && !existing.has(f.key)) newFields.push(f.key)
              })
              return { ...prev, collect_fields: newFields }
            })
          }}
          onExtraFieldsChange={setExtraFields}
        />
      )}

      {/* ── 수집 필드 설정 ── */}
      <div className="product-config-section active">
        <h4 className="config-section-title">수집 필드</h4>
        <div className="config-section-desc">이 URL에서 수집할 데이터 항목을 선택합니다</div>
        <div className="field-checkbox-grid">
          {collectFieldDefs.map(f => (
            <label key={f.key} className={`field-checkbox ${isFieldChecked(f.key) ? 'checked' : ''}`}>
              <input
                type="checkbox"
                checked={isFieldChecked(f.key)}
                onChange={() => toggleField(f.key)}
              />
              <span>{f.label}</span>
            </label>
          ))}
        </div>
      </div>

      {/* ── 목록 유형 ── */}
      <div className="product-config-section active">
        <h4 className="config-section-title">목록 유형</h4>
        <div className="config-section-desc">수집 대상 페이지의 목록 유형을 선택합니다</div>
        <div className="list-type-options">
          {LIST_TYPE_OPTIONS.map(opt => (
            <label
              key={opt.value}
              className={`list-type-option ${config.list_type === opt.value ? 'selected' : ''}`}
              onClick={() => setConfig({ ...config, list_type: opt.value })}
            >
              <input
                type="radio" name="list_type"
                checked={config.list_type === opt.value}
                onChange={() => setConfig({ ...config, list_type: opt.value })}
              />
              <span className="list-type-icon">{opt.icon}</span>
              <div>
                <strong>{opt.label}</strong>
                <p>{opt.desc}</p>
              </div>
            </label>
          ))}
        </div>
      </div>

      {/* ── 페이지네이션 방식 ── */}
      <div className="product-config-section active">
        <h4 className="config-section-title">페이지네이션 방식</h4>
        <div className="config-section-desc">상품 목록 페이지 이동 방식을 선택합니다</div>
        <div className="config-sub">
          <div style={{display:'flex',gap:10,flexWrap:'wrap'}}>
            {PAGINATION_OPTIONS.map(opt => (
              <label key={opt.value} style={{display:'flex',alignItems:'center',gap:5,cursor:'pointer'}}>
                <input
                  type="radio" name="pagination"
                  checked={config.pagination === opt.value}
                  onChange={() => setConfig({ ...config, pagination: opt.value })}
                />
                <span style={{fontSize:13}} title={opt.desc}>{opt.label}</span>
              </label>
            ))}
          </div>
        </div>
      </div>

      {/* ── 수집 범위 ── */}
      <div className="product-config-section active">
        <h4 className="config-section-title">수집 범위</h4>
        <div className="config-section-desc">최대 수집 건수와 페이지 수를 설정합니다</div>
        <div className="config-sub">
          <span className="config-sub-label">최대 수집 건수</span>
          <div style={{display:'flex',gap:12,alignItems:'center'}}>
            <label style={{display:'flex',alignItems:'center',gap:5,cursor:'pointer'}}>
              <input
                type="radio" name="item_limit"
                checked={config.item_limit_type === 'all'}
                onChange={() => setConfig({ ...config, item_limit_type: 'all' })}
              />
              <span style={{fontSize:13}}>전체</span>
            </label>
            <label style={{display:'flex',alignItems:'center',gap:5,cursor:'pointer'}}>
              <input
                type="radio" name="item_limit"
                checked={config.item_limit_type === 'n'}
                onChange={() => setConfig({ ...config, item_limit_type: 'n' })}
              />
              <span style={{fontSize:13}}>건수 지정</span>
            </label>
            {config.item_limit_type === 'n' && (
              <div style={{display:'flex',alignItems:'center',gap:6}}>
                <input
                  type="number" className="form-control"
                  style={{width:90,padding:'4px 8px',fontSize:13}}
                  min={1}
                  value={config.max_items}
                  onChange={e => setConfig({ ...config, max_items: parseInt(e.target.value) || 1 })}
                />
                <span style={{fontSize:12,color:'var(--text-secondary)'}}>건</span>
              </div>
            )}
          </div>
        </div>
        <div className="config-sub" style={{marginTop:8}}>
          <span className="config-sub-label">최대 페이지 수</span>
          <div style={{display:'flex',alignItems:'center',gap:6}}>
            <input
              type="number" className="form-control"
              style={{width:90,padding:'4px 8px',fontSize:13}}
              min={1}
              value={config.max_pages}
              onChange={e => setConfig({ ...config, max_pages: parseInt(e.target.value) || 1 })}
            />
            <span style={{fontSize:12,color:'var(--text-secondary)'}}>페이지</span>
          </div>
        </div>
      </div>

      {/* ── 상품 상세 수집 ── */}
      <div className="product-config-section active">
        <h4 className="config-section-title">상품 상세 수집</h4>
        <div className="config-section-desc">각 상품의 상세 페이지를 방문하여 추가 정보를 수집합니다</div>
        <div className="config-toggle">
          <input
            type="checkbox" id="detail_page"
            checked={!!config.detail_page}
            onChange={e => {
              const checked = e.target.checked
              if (checked && config.detail_fields.length === 0) {
                setConfig({ ...config, detail_page: true,
                  detail_fields: DETAIL_FIELD_DEFS.map(f => ({ key: f.key }))
                })
              } else {
                setConfig({ ...config, detail_page: checked })
              }
            }}
          />
          <label htmlFor="detail_page">상세 페이지 진입 (상품별 상세 정보 수집)</label>
        </div>
        {config.detail_page && (
          <div className="detail-fields-panel" style={{marginTop:12}}>
            <div style={{fontSize:12,color:'var(--text-secondary)',marginBottom:8}}>
              수집할 상세 정보를 선택하세요
            </div>
            <div className="detail-fields-grid">
              {DETAIL_FIELD_DEFS.map(fd => {
                const checked = config.detail_fields.some(
                  f => (typeof f === 'string' ? f : f.key) === fd.key
                )
                return (
                  <label key={fd.key} className={`detail-field-item${checked ? ' checked' : ''}`}>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={e => {
                        const newFields = e.target.checked
                          ? [...config.detail_fields, { key: fd.key }]
                          : config.detail_fields.filter(
                              f => (typeof f === 'string' ? f : f.key) !== fd.key
                            )
                        setConfig({ ...config, detail_fields: newFields })
                      }}
                    />
                    <span>{fd.label}</span>
                  </label>
                )
              })}
            </div>
            <div style={{display:'flex',gap:8,marginTop:8}}>
              <button
                type="button" className="btn btn-xs btn-outline"
                onClick={() => setConfig({ ...config,
                  detail_fields: DETAIL_FIELD_DEFS.map(f => ({ key: f.key }))
                })}
              >전체 선택</button>
              <button
                type="button" className="btn btn-xs btn-outline"
                onClick={() => setConfig({ ...config, detail_fields: [] })}
              >전체 해제</button>
            </div>
          </div>
        )}
      </div>

      <div style={{display:'flex',justifyContent:'flex-end',gap:8,marginTop:20}}>
        <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? '저장 중...' : '저장'}
        </button>
      </div>
    </>
  )
}


/* ── news: 뉴스 검색 키워드 설정 ───────────────── */
function NewsConfig({ site, onSaved, showConfirm, closeConfirm }) {
  const [keywords, setKeywords] = useState(site.keywords || [])
  const [newKw, setNewKw] = useState('')
  const [config, setConfig] = useState({
    max_articles_per_keyword: 10,
    collect_body: false,
    ...site.config,
  })
  const [saving, setSaving] = useState(false)

  const addKeyword = () => {
    const parts = newKw
      .split(/[,\n]/)
      .map(s => s.trim())
      .filter(Boolean)
    if (parts.length === 0) return
    const existing = new Set(keywords.map(k => k.keyword))
    const fresh = Array.from(new Set(parts)).filter(k => !existing.has(k))
    if (fresh.length === 0) { setNewKw(''); return }
    const label = fresh.length === 1
      ? `"${fresh[0]}" 키워드를 추가하시겠습니까?`
      : `${fresh.length}개 키워드를 추가하시겠습니까?\n${fresh.join(', ')}`
    showConfirm({
      title: '키워드 추가',
      message: label,
      confirmLabel: '추가',
      onConfirm: async () => {
        closeConfirm()
        for (const kw of fresh) {
          await fetch(`/api/sites/${site.id}/keywords`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ keyword: kw }),
          })
        }
        setNewKw('')
        const res = await fetch(`/api/sites/${site.id}/keywords`)
        setKeywords(await res.json())
      },
    })
  }

  const removeKeyword = (kw) => {
    showConfirm({
      title: '키워드 삭제',
      message: `"${kw}" 키워드를 삭제하시겠습니까?`,
      confirmLabel: '삭제',
      confirmType: 'danger',
      onConfirm: async () => {
        closeConfirm()
        await fetch(`/api/sites/${site.id}/keywords/${encodeURIComponent(kw)}`, {
          method: 'DELETE',
        })
        const res = await fetch(`/api/sites/${site.id}/keywords`)
        setKeywords(await res.json())
      },
    })
  }

  const handleSaveConfig = () => {
    showConfirm({
      title: '설정 저장',
      message: `"${site.name}" 사이트의 수집 설정을 변경하시겠습니까?`,
      confirmLabel: '저장',
      onConfirm: async () => {
        closeConfirm()
        setSaving(true)
        try {
          const res = await fetch(`/api/sites/${site.id}/config`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ crawl_config: config }),
          })
          if (!res.ok) { alert('저장 실패: 서버 오류가 발생했습니다'); return }
          onSaved()
        } catch (e) {
          alert('저장 실패: ' + (e.message || '네트워크 오류'))
        } finally {
          setSaving(false)
        }
      },
    })
  }

  return (
    <>
      <div style={{background:'#f8fafc',padding:'12px 16px',borderRadius:8,marginBottom:20,fontSize:13,color:'#475569'}}>
        뉴스 검색 키워드를 등록하면 해당 키워드로 기사를 검색하여 수집합니다
      </div>

      <h4 style={{fontSize:14,fontWeight:600,marginBottom:12}}>검색 키워드</h4>

      <div style={{display:'flex',flexWrap:'wrap',gap:8,marginBottom:12}}>
        {keywords.map(k => (
          <span key={k.keyword} style={{
            display:'inline-flex',alignItems:'center',gap:6,
            background: k.is_active ? '#dbeafe' : '#f1f5f9',
            color: k.is_active ? '#1e40af' : '#94a3b8',
            padding:'5px 12px',borderRadius:16,fontSize:13,
          }}>
            {k.keyword}
            <button
              onClick={() => removeKeyword(k.keyword)}
              style={{
                background:'none',border:'none',cursor:'pointer',
                color:'#94a3b8',fontSize:16,lineHeight:1,padding:0,
              }}
              title="삭제"
            >x</button>
          </span>
        ))}
        {keywords.length === 0 && (
          <span style={{color:'var(--text-secondary)',fontSize:13}}>등록된 키워드가 없습니다</span>
        )}
      </div>

      <div style={{display:'flex',gap:8,marginBottom:20}}>
        <input
          className="form-control"
          style={{flex:1}}
          placeholder="새 키워드를 입력하세요 (예: 해외여행)"
          value={newKw}
          onChange={e => setNewKw(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') addKeyword() }}
        />
        <button className="btn btn-primary btn-sm" onClick={addKeyword}>추가</button>
      </div>

      <div style={{borderTop:'1px solid var(--border)',paddingTop:16}}>
        <h4 style={{fontSize:14,fontWeight:600,marginBottom:12}}>수집 설정</h4>

        <div className="form-group">
          <label>키워드당 최대 수집 기사 수</label>
          <input
            type="number"
            className="form-control"
            style={{width:120}}
            min={1}
            value={config.max_articles_per_keyword}
            onChange={e => setConfig({ ...config, max_articles_per_keyword: parseInt(e.target.value) || 1 })}
          />
        </div>

        <div className="config-toggle">
          <input
            type="checkbox" id="news_body"
            checked={!!config.collect_body}
            onChange={e => setConfig({ ...config, collect_body: e.target.checked })}
          />
          <label htmlFor="news_body">기사 본문 수집</label>
        </div>
      </div>

      <div style={{display:'flex',justifyContent:'flex-end',gap:8,marginTop:20}}>
        <button className="btn btn-primary" onClick={handleSaveConfig} disabled={saving}>
          {saving ? '저장 중...' : '저장'}
        </button>
      </div>
    </>
  )
}


/* ── cafe: 네이버 카페 설정 ────────────────────── */
function CafeConfig({ site, onSaved, showConfirm, closeConfirm }) {
  const [config, setConfig] = useState({
    collect_body: true,
    collect_links: true,
    collect_images: true,
    collect_ocr: false,
    date_from: '',
    date_to: '',
    ...site.config,
  })
  const [saving, setSaving] = useState(false)

  const handleSave = () => {
    showConfirm({
      title: '설정 저장',
      message: `"${site.name}" 사이트의 수집 설정을 변경하시겠습니까?`,
      confirmLabel: '저장',
      onConfirm: async () => {
        closeConfirm()
        setSaving(true)
        try {
          const res = await fetch(`/api/sites/${site.id}/config`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ crawl_config: config }),
          })
          if (!res.ok) { alert('저장 실패: 서버 오류가 발생했습니다'); return }
          onSaved()
        } catch (e) {
          alert('저장 실패: ' + (e.message || '네트워크 오류'))
        } finally {
          setSaving(false)
        }
      },
    })
  }

  const CAFE_TOGGLES = [
    { key: 'collect_body',   label: '본문 수집' },
    { key: 'collect_links',  label: '링크 수집' },
    { key: 'collect_images', label: '이미지 수집' },
    { key: 'collect_ocr',    label: 'OCR 가격 추출 (이미지에서 상품/가격 추출)' },
  ]

  return (
    <>
      <div style={{background:'#faf5ff',padding:'12px 16px',borderRadius:8,marginBottom:20,fontSize:13,color:'#6b21a8'}}>
        네이버 카페 인기 게시판의 게시글에서 상품/가격 정보를 수집합니다
      </div>

      <h4 style={{fontSize:14,fontWeight:600,marginBottom:12}}>수집 기간</h4>
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12,marginBottom:20}}>
        <div className="form-group" style={{marginBottom:0}}>
          <label>시작일 (date_from)</label>
          <input
            type="date" className="form-control"
            value={config.date_from || ''}
            onChange={e => setConfig({ ...config, date_from: e.target.value })}
          />
        </div>
        <div className="form-group" style={{marginBottom:0}}>
          <label>종료일 (date_to)</label>
          <input
            type="date" className="form-control"
            value={config.date_to || ''}
            onChange={e => setConfig({ ...config, date_to: e.target.value })}
          />
        </div>
      </div>

      <h4 style={{fontSize:14,fontWeight:600,marginBottom:12}}>수집 항목</h4>
      {CAFE_TOGGLES.map(cb => (
        <div className="config-toggle" key={cb.key}>
          <input
            type="checkbox" id={cb.key}
            checked={!!config[cb.key]}
            onChange={e => setConfig({ ...config, [cb.key]: e.target.checked })}
          />
          <label htmlFor={cb.key}>{cb.label}</label>
        </div>
      ))}

      <div style={{display:'flex',justifyContent:'flex-end',gap:8,marginTop:20}}>
        <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? '저장 중...' : '저장'}
        </button>
      </div>
    </>
  )
}


/* ── promotion: 이벤트/프로모션 수집 설정 ──────── */
function PromotionConfig({ site, onSaved, showConfirm, closeConfirm }) {
  const [config, setConfig] = useState({
    event_limit_type: 'all',
    event_limit_count: 50,
    collect_details: true,
    collect_event_products: true,
    event_status_filter: 'all',
    ...site.config,
  })
  const [saving, setSaving] = useState(false)

  const handleSave = () => {
    showConfirm({
      title: '설정 저장',
      message: `"${site.name}" 사이트의 이벤트 수집 설정을 변경하시겠습니까?`,
      confirmLabel: '저장',
      onConfirm: async () => {
        closeConfirm()
        setSaving(true)
        try {
          const payload = { ...config }
          if (payload.event_limit_type === 'all') payload.event_limit_count = 0
          const res = await fetch(`/api/sites/${site.id}/config`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ crawl_config: payload }),
          })
          if (!res.ok) { alert('저장 실패: 서버 오류가 발생했습니다'); return }
          onSaved()
        } catch (e) {
          alert('저장 실패: ' + (e.message || '네트워크 오류'))
        } finally {
          setSaving(false)
        }
      },
    })
  }

  return (
    <>
      <div style={{background:'#fdf2f8',padding:'12px 16px',borderRadius:8,marginBottom:20,fontSize:13,color:'#9d174d'}}>
        경쟁사 이벤트 페이지에서 진행 중인 이벤트 목록과 상세 정보를 수집합니다
      </div>

      {/* ── 이벤트 수집 범위 ── */}
      <div className="product-config-section active">
        <h4 className="config-section-title">이벤트 수집 범위</h4>
        <div className="config-section-desc">이벤트 목록 페이지에서 수집할 이벤트 수를 설정합니다</div>
        <div className="config-sub">
          <span className="config-sub-label">수집 범위</span>
          <div style={{display:'flex',gap:12,alignItems:'center'}}>
            <label style={{display:'flex',alignItems:'center',gap:5,cursor:'pointer'}}>
              <input
                type="radio" name="event_limit"
                checked={config.event_limit_type === 'all'}
                onChange={() => setConfig({ ...config, event_limit_type: 'all' })}
              />
              <span style={{fontSize:13}}>전체</span>
            </label>
            <label style={{display:'flex',alignItems:'center',gap:5,cursor:'pointer'}}>
              <input
                type="radio" name="event_limit"
                checked={config.event_limit_type === 'n'}
                onChange={() => setConfig({ ...config, event_limit_type: 'n' })}
              />
              <span style={{fontSize:13}}>건수 지정</span>
            </label>
            {config.event_limit_type === 'n' && (
              <div style={{display:'flex',alignItems:'center',gap:6}}>
                <input
                  type="number" className="form-control"
                  style={{width:90,padding:'4px 8px',fontSize:13}}
                  min={1}
                  value={config.event_limit_count}
                  onChange={e => setConfig({ ...config, event_limit_count: parseInt(e.target.value) || 1 })}
                />
                <span style={{fontSize:12,color:'var(--text-secondary)'}}>건</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── 이벤트 상태 필터 ── */}
      <div className="product-config-section active">
        <h4 className="config-section-title">이벤트 상태 필터</h4>
        <div className="config-section-desc">수집할 이벤트의 상태를 선택합니다</div>
        <div className="config-sub">
          <span className="config-sub-label">상태</span>
          <div style={{display:'flex',gap:12,alignItems:'center'}}>
            <label style={{display:'flex',alignItems:'center',gap:5,cursor:'pointer'}}>
              <input
                type="radio" name="event_status"
                checked={config.event_status_filter === 'all'}
                onChange={() => setConfig({ ...config, event_status_filter: 'all' })}
              />
              <span style={{fontSize:13}}>전체 (진행 + 종료)</span>
            </label>
            <label style={{display:'flex',alignItems:'center',gap:5,cursor:'pointer'}}>
              <input
                type="radio" name="event_status"
                checked={config.event_status_filter === 'active'}
                onChange={() => setConfig({ ...config, event_status_filter: 'active' })}
              />
              <span style={{fontSize:13}}>진행 중만</span>
            </label>
          </div>
        </div>
      </div>

      {/* ── 수집 항목 토글 ── */}
      <h4 style={{fontSize:14,fontWeight:600,marginBottom:12,marginTop:16}}>수집 항목</h4>
      <div className="config-toggle">
        <input
          type="checkbox" id="promo_details"
          checked={!!config.collect_details}
          onChange={e => setConfig({ ...config, collect_details: e.target.checked })}
        />
        <label htmlFor="promo_details">이벤트 상세 수집 (각 이벤트 페이지 방문)</label>
      </div>
      <div className="config-toggle">
        <input
          type="checkbox" id="promo_products"
          checked={!!config.collect_event_products}
          onChange={e => setConfig({ ...config, collect_event_products: e.target.checked })}
        />
        <label htmlFor="promo_products">이벤트 내 상품 수집 (이벤트에 포함된 상품 정보)</label>
      </div>

      <div style={{display:'flex',justifyContent:'flex-end',gap:8,marginTop:20}}>
        <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? '저장 중...' : '저장'}
        </button>
      </div>
    </>
  )
}


/* ── banner: 배너/비주얼 수집 설정 ────────────────── */
const BANNER_AREA_OPTIONS = [
  { key: 'hero',       label: '히어로 배너',  desc: '메인 상단 대형 배너' },
  { key: 'sub_banner', label: '서브 배너',    desc: '중간/하단 프로모션 배너' },
  { key: 'popup',      label: '팝업',        desc: '팝업/레이어 배너' },
]

function BannerConfig({ site, onSaved, showConfirm, closeConfirm }) {
  const [config, setConfig] = useState(() => {
    const c = site.config || {}
    return {
      banner_areas: c.banner_areas || ['hero'],
      capture_screenshot: c.capture_screenshot ?? true,
      download_images: c.download_images ?? false,
      include_text: c.include_text ?? true,
      max_slides: c.max_slides ?? 10,
    }
  })
  const [saving, setSaving] = useState(false)
  const [extraFields, setExtraFields] = useState(() => (site.config || {}).extra_fields || [])

  const toggleArea = (key) => {
    const areas = config.banner_areas.includes(key)
      ? config.banner_areas.filter(a => a !== key)
      : [...config.banner_areas, key]
    setConfig({ ...config, banner_areas: areas })
  }

  const handleSave = () => {
    showConfirm({
      title: '설정 저장',
      message: `"${site.name}" 사이트의 배너 수집 설정을 변경하시겠습니까?`,
      detail: `배너 영역: ${config.banner_areas.length}개 선택`,
      confirmLabel: '저장',
      onConfirm: async () => {
        closeConfirm()
        setSaving(true)
        try {
          const payload = { ...config }
          if (extraFields.length > 0) payload.extra_fields = extraFields
          const res = await fetch(`/api/sites/${site.id}/config`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ crawl_config: payload }),
          })
          if (!res.ok) { alert('저장 실패: 서버 오류가 발생했습니다'); return }
          onSaved()
        } catch (e) {
          alert('저장 실패: ' + (e.message || '네트워크 오류'))
        } finally {
          setSaving(false)
        }
      },
    })
  }

  return (
    <>
      <div style={{background:'#fff1f2',padding:'12px 16px',borderRadius:8,marginBottom:20,fontSize:13,color:'#9f1239'}}>
        경쟁사 페이지의 배너 이미지/텍스트를 수집합니다
      </div>

      {/* ── URL 분석 ── */}
      {site.url && (
        <UrlAnalyzePanel
          url={site.url}
          existingFieldKeys={BANNER_AREA_OPTIONS.map(o => o.key)}
          textColor="#9f1239"
          savedExtraFields={extraFields}
          onAnalyzeComplete={(data) => {
            if (data.banners && data.banners.areas) {
              setConfig(prev => {
                const newAreas = [...prev.banner_areas]
                data.banners.areas.forEach(a => {
                  if (!newAreas.includes(a)) newAreas.push(a)
                })
                return { ...prev, banner_areas: newAreas }
              })
            }
          }}
          onExtraFieldsChange={setExtraFields}
        />
      )}

      {/* ── 배너 영역 선택 ── */}
      <div className="product-config-section active">
        <h4 className="config-section-title">배너 영역</h4>
        <div className="config-section-desc">수집할 배너 영역을 선택합니다</div>
        <div className="field-checkbox-grid">
          {BANNER_AREA_OPTIONS.map(opt => (
            <label key={opt.key} className={`field-checkbox ${config.banner_areas.includes(opt.key) ? 'checked' : ''}`} title={opt.desc}>
              <input
                type="checkbox"
                checked={config.banner_areas.includes(opt.key)}
                onChange={() => toggleArea(opt.key)}
              />
              <span>{opt.label}</span>
            </label>
          ))}
        </div>
      </div>

      {/* ── 수집 옵션 ── */}
      <div className="product-config-section active">
        <h4 className="config-section-title">수집 옵션</h4>
        <div className="config-section-desc">배너 데이터 수집 방식을 설정합니다</div>
        <div className="config-toggle">
          <input type="checkbox" id="banner_screenshot"
            checked={!!config.capture_screenshot}
            onChange={e => setConfig({ ...config, capture_screenshot: e.target.checked })}
          />
          <label htmlFor="banner_screenshot">스크린샷 캡처 (배너 영역 이미지 저장)</label>
        </div>
        <div className="config-toggle">
          <input type="checkbox" id="banner_download"
            checked={!!config.download_images}
            onChange={e => setConfig({ ...config, download_images: e.target.checked })}
          />
          <label htmlFor="banner_download">이미지 다운로드 (원본 배너 이미지 파일 저장)</label>
        </div>
        <div className="config-toggle">
          <input type="checkbox" id="banner_text"
            checked={!!config.include_text}
            onChange={e => setConfig({ ...config, include_text: e.target.checked })}
          />
          <label htmlFor="banner_text">배너 텍스트 수집 (오버레이 텍스트 추출)</label>
        </div>
      </div>

      {/* ── 슬라이더 설정 ── */}
      <div className="product-config-section active">
        <h4 className="config-section-title">슬라이더 설정</h4>
        <div className="config-section-desc">슬라이더/캐러셀 배너의 최대 슬라이드 수를 설정합니다</div>
        <div className="config-sub">
          <span className="config-sub-label">최대 슬라이드 수</span>
          <div style={{display:'flex',alignItems:'center',gap:6}}>
            <input
              type="number" className="form-control"
              style={{width:90,padding:'4px 8px',fontSize:13}}
              min={1} max={50}
              value={config.max_slides}
              onChange={e => setConfig({ ...config, max_slides: parseInt(e.target.value) || 1 })}
            />
            <span style={{fontSize:12,color:'var(--text-secondary)'}}>개</span>
          </div>
        </div>
      </div>

      <div style={{display:'flex',justifyContent:'flex-end',gap:8,marginTop:20}}>
        <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? '저장 중...' : '저장'}
        </button>
      </div>
    </>
  )
}


/* ── directory: 브랜드/이벤트 목록 수집 설정 ─────── */
const DIR_LIST_TYPE_OPTIONS = [
  { value: 'brand_directory', label: '브랜드 디렉토리', icon: '🏷️', desc: '브랜드 목록 (A~Z / ㄱ~ㅎ 인덱스)' },
  { value: 'brand_branch',    label: '브랜드 지점',     icon: '🏬', desc: '면세점 브랜드 매장 (지점/층/전화번호)' },
  { value: 'event_list',      label: '이벤트 목록',     icon: '📅', desc: '이벤트/프로모션 리스트' },
]


function DirectoryConfig({ site, onSaved, showConfirm, closeConfirm, fieldDefs }) {
  const collectFieldDefs = fieldDefs.filter(f => f.config_key === 'collect_fields')
  const [config, setConfig] = useState(() => {
    const c = site.config || {}
    return {
      list_type: c.list_type || 'brand_directory',
      collect_fields: c.collect_fields || ['name', 'category'],
      index_navigation: c.index_navigation ?? false,
      collect_details: c.collect_details ?? false,
      max_items: c.max_items ?? 0,
      item_limit_type: (c.max_items === 0 || c.max_items === undefined) ? 'all' : 'n',
    }
  })
  const [saving, setSaving] = useState(false)
  const [extraFields, setExtraFields] = useState(() => (site.config || {}).extra_fields || [])

  const toggleField = (key) => {
    const fields = config.collect_fields.includes(key)
      ? config.collect_fields.filter(f => f !== key)
      : [...config.collect_fields, key]
    setConfig({ ...config, collect_fields: fields })
  }

  const handleSave = () => {
    const typeLabel = DIR_LIST_TYPE_OPTIONS.find(o => o.value === config.list_type)?.label || config.list_type
    showConfirm({
      title: '설정 저장',
      message: `"${site.name}" 사이트의 목록 수집 설정을 변경하시겠습니까?`,
      detail: `목록 유형: ${typeLabel} | 수집 필드: ${config.collect_fields.length}개`,
      confirmLabel: '저장',
      onConfirm: async () => {
        closeConfirm()
        setSaving(true)
        try {
          const payload = {
            list_type: config.list_type,
            collect_fields: config.collect_fields,
            index_navigation: config.index_navigation,
            collect_details: config.collect_details,
            max_items: config.item_limit_type === 'all' ? 0 : config.max_items,
          }
          if (extraFields.length > 0) payload.extra_fields = extraFields
          const res = await fetch(`/api/sites/${site.id}/config`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ crawl_config: payload }),
          })
          if (!res.ok) { alert('저장 실패: 서버 오류가 발생했습니다'); return }
          onSaved()
        } catch (e) {
          alert('저장 실패: ' + (e.message || '네트워크 오류'))
        } finally {
          setSaving(false)
        }
      },
    })
  }

  return (
    <>
      <div style={{background:'#ecfeff',padding:'12px 16px',borderRadius:8,marginBottom:20,fontSize:13,color:'#0e7490'}}>
        브랜드 디렉토리 또는 이벤트 목록 페이지에서 항목을 수집합니다
      </div>

      {/* ── URL 분석 ── */}
      {site.url && (
        <UrlAnalyzePanel
          url={site.url}
          existingFieldKeys={collectFieldDefs.map(f => f.key)}
          textColor="#0e7490"
          savedExtraFields={extraFields}
          onExistingFieldsFound={(foundKeys) => {
            setConfig(prev => {
              const existing = new Set(prev.collect_fields)
              const newFields = [...prev.collect_fields]
              collectFieldDefs.forEach(f => {
                if (foundKeys.has(f.key) && !existing.has(f.key)) newFields.push(f.key)
              })
              return { ...prev, collect_fields: newFields }
            })
          }}
          onAnalyzeComplete={(data) => {
            if (data.directory && data.directory.has_index) {
              setConfig(prev => ({ ...prev, index_navigation: true }))
            }
          }}
          onExtraFieldsChange={setExtraFields}
        />
      )}

      {/* ── 목록 유형 ── */}
      <div className="product-config-section active">
        <h4 className="config-section-title">목록 유형</h4>
        <div className="config-section-desc">수집할 목록의 유형을 선택합니다</div>
        <div className="list-type-options">
          {DIR_LIST_TYPE_OPTIONS.map(opt => (
            <label
              key={opt.value}
              className={`list-type-option ${config.list_type === opt.value ? 'selected' : ''}`}
              onClick={() => {
                const update = { ...config, list_type: opt.value }
                if (opt.value === 'brand_branch') {
                  update.collect_fields = ['name', 'category', 'branch', 'location', 'phone']
                  update.index_navigation = false
                }
                setConfig(update)
              }}
            >
              <input
                type="radio" name="dir_list_type"
                checked={config.list_type === opt.value}
                onChange={() => setConfig({ ...config, list_type: opt.value })}
              />
              <span className="list-type-icon">{opt.icon}</span>
              <div>
                <strong>{opt.label}</strong>
                <p>{opt.desc}</p>
              </div>
            </label>
          ))}
        </div>
      </div>

      {/* ── 수집 필드 ── */}
      <div className="product-config-section active">
        <h4 className="config-section-title">수집 필드</h4>
        <div className="config-section-desc">각 항목에서 수집할 데이터를 선택합니다</div>
        <div className="field-checkbox-grid" style={{gridTemplateColumns:'1fr 1fr'}}>
          {collectFieldDefs.map(f => (
            <label key={f.key} className={`field-checkbox ${config.collect_fields.includes(f.key) ? 'checked' : ''}`}>
              <input
                type="checkbox"
                checked={config.collect_fields.includes(f.key)}
                onChange={() => toggleField(f.key)}
              />
              <span>{f.label}</span>
            </label>
          ))}
        </div>
      </div>

      {/* ── 수집 옵션 ── */}
      <div className="product-config-section active">
        <h4 className="config-section-title">수집 옵션</h4>
        <div className="config-toggle">
          <input type="checkbox" id="dir_index"
            checked={!!config.index_navigation}
            onChange={e => setConfig({ ...config, index_navigation: e.target.checked })}
          />
          <label htmlFor="dir_index">인덱스 탐색 (A~Z / ㄱ~ㅎ 순서로 순회)</label>
        </div>
        <div className="config-toggle">
          <input type="checkbox" id="dir_details"
            checked={!!config.collect_details}
            onChange={e => setConfig({ ...config, collect_details: e.target.checked })}
          />
          <label htmlFor="dir_details">상세 진입 (각 항목 상세 페이지 방문)</label>
        </div>
      </div>

      {/* ── 수집 범위 ── */}
      <div className="product-config-section active">
        <h4 className="config-section-title">수집 범위</h4>
        <div className="config-sub">
          <span className="config-sub-label">최대 항목 수</span>
          <div style={{display:'flex',gap:12,alignItems:'center'}}>
            <label style={{display:'flex',alignItems:'center',gap:5,cursor:'pointer'}}>
              <input
                type="radio" name="dir_item_limit"
                checked={config.item_limit_type === 'all'}
                onChange={() => setConfig({ ...config, item_limit_type: 'all' })}
              />
              <span style={{fontSize:13}}>전체</span>
            </label>
            <label style={{display:'flex',alignItems:'center',gap:5,cursor:'pointer'}}>
              <input
                type="radio" name="dir_item_limit"
                checked={config.item_limit_type === 'n'}
                onChange={() => setConfig({ ...config, item_limit_type: 'n' })}
              />
              <span style={{fontSize:13}}>건수 지정</span>
            </label>
            {config.item_limit_type === 'n' && (
              <div style={{display:'flex',alignItems:'center',gap:6}}>
                <input
                  type="number" className="form-control"
                  style={{width:90,padding:'4px 8px',fontSize:13}}
                  min={1}
                  value={config.max_items}
                  onChange={e => setConfig({ ...config, max_items: parseInt(e.target.value) || 1 })}
                />
                <span style={{fontSize:12,color:'var(--text-secondary)'}}>건</span>
              </div>
            )}
          </div>
        </div>
      </div>

      <div style={{display:'flex',justifyContent:'flex-end',gap:8,marginTop:20}}>
        <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? '저장 중...' : '저장'}
        </button>
      </div>
    </>
  )
}


/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   사이트 추가 모달
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
/* ─── 카테고리별 기본 수집 Config 템플릿 ─── */
const CATEGORY_DEFAULT_CONFIGS = {
  /* product 카테고리들 */
  '트렌드매장': {
    collect_fields: ['name','price','brand','image','rank','original_price','discount_rate','reference_no'],
    list_type: 'ranking', pagination: 'scroll', max_pages: 5, max_items: 100, detail_page: true,
  },
  '경쟁사': {
    collect_fields: ['name','price','brand','image','rank','original_price','discount_rate','gift','reference_no'],
    list_type: 'ranking', pagination: 'scroll', max_pages: 10, max_items: 0, detail_page: true,
  },
  '브랜드공식': {
    collect_fields: ['name','price','brand','image','reference_no','category'],
    list_type: 'catalog', pagination: 'scroll', max_pages: 10, max_items: 0, detail_page: true,
  },
  '네이버스토어': {
    collect_fields: ['name','price','brand','image','original_price','discount_rate','reference_no'],
    list_type: 'catalog', pagination: 'scroll', max_pages: 10, max_items: 0, detail_page: true,
  },
  '경쟁사중국': {
    collect_fields: ['name','price','brand','image','rank','original_price','discount_rate','reference_no'],
    list_type: 'ranking', pagination: 'scroll', max_pages: 10, max_items: 0, detail_page: true,
  },
  '트렌드Global매장': {
    collect_fields: ['name','price','brand','image','rank','original_price','discount_rate'],
    list_type: 'ranking', pagination: 'scroll', max_pages: 5, max_items: 100, detail_page: false,
  },
  '당사온라인몰': {
    collect_fields: ['name','price','brand','image','original_price','discount_rate','category'],
    list_type: 'catalog', pagination: 'scroll', max_pages: 10, max_items: 0, detail_page: true,
  },
  '로컬': {
    local_type: 'oliveyoung',
    collect_fields: ['brand', 'name', 'regular_price', 'discounted_price', 'discount_rate'],
  },
  /* banner */
  '경쟁사배너': {
    banner_areas: ['hero','sub_banner'], capture_screenshot: true,
    download_images: false, include_text: true, max_slides: 10,
  },
  /* directory */
  '브랜드목록': {
    collect_fields: ['name','category','branch','location','phone'],
    list_type: 'brand_branch', collect_details: false, index_navigation: false, load_all_pages: true, max_items: 0,
  },
}

/* ─── 에이전트별 수집 가능 항목 정의 ─── */
const COLLECT_ITEMS_BY_AGENT = {
  product: {
    label: '상품 수집 항목',
    desc: '수집할 상품 정보를 선택합니다',
    color: '#eff6ff',
    textColor: '#1d4ed8',
    fields: [
      { key: 'name',           label: '상품명',       default: true },
      { key: 'price',          label: '가격',         default: true },
      { key: 'brand',          label: '브랜드',       default: true },
      { key: 'image',          label: '이미지',       default: true },
      { key: 'rank',           label: '순위',         default: false },
      { key: 'original_price', label: '원가',         default: false },
      { key: 'discount_rate',  label: '할인율',       default: false },
      { key: 'gift',           label: '사은품',       default: false },
      { key: 'reference_no',   label: '레퍼런스번호', default: false },
      { key: 'category',       label: '카테고리',     default: false },
    ],
    options: [
      { key: 'detail_page', label: '상품 상세 수집', desc: '상품 상세 페이지에 진입하여 추가 정보를 수집합니다' },
    ],
    listTypes: LIST_TYPE_OPTIONS,
    paginations: PAGINATION_OPTIONS,
  },
  banner: {
    label: '배너 수집 항목',
    desc: '수집할 배너 영역과 옵션을 선택합니다',
    color: '#fff1f2',
    textColor: '#9f1239',
    fields: [
      { key: 'hero',       label: '히어로 배너',  group: 'area', default: true },
      { key: 'sub_banner', label: '서브 배너',    group: 'area', default: true },
      { key: 'popup',      label: '팝업',        group: 'area', default: false },
    ],
    options: [
      { key: 'capture_screenshot', label: '스크린샷 캡처',    desc: '배너 영역 스크린샷을 저장합니다' },
      { key: 'download_images',    label: '이미지 다운로드',  desc: '배너 이미지를 파일로 다운로드합니다' },
      { key: 'include_text',       label: '배너 텍스트 수집', desc: '배너 내 텍스트를 추출합니다' },
    ],
  },
  directory: {
    label: '목록 수집 항목',
    desc: '수집할 목록 정보를 선택합니다',
    color: '#ecfeff',
    textColor: '#0e7490',
    fields: [
      { key: 'name',        label: '이름 (브랜드/이벤트)', group: 'field', default: true },
      { key: 'category',    label: '카테고리',             group: 'field', default: true },
      { key: 'description', label: '설명',                group: 'field', default: false },
      { key: 'period',      label: '기간',                group: 'field', default: false },
      { key: 'status',      label: '상태',                group: 'field', default: false },
      { key: 'detail_url',  label: '상세 URL',            group: 'field', default: false },
    ],
    options: [
      { key: 'index_navigation', label: '인덱스 탐색 (A~Z)',  desc: '알파벳/가나다 인덱스를 순회합니다' },
      { key: 'collect_details',  label: '상세 페이지 수집',     desc: '각 항목의 상세 페이지를 방문합니다' },
    ],
    listTypes: DIR_LIST_TYPE_OPTIONS,
  },
  local: {
    label: '로컬 수집 항목',
    desc: '수집할 상품 정보를 선택합니다',
    color: '#ecfdf5',
    textColor: '#065f46',
    fields: [
      { key: 'brand',            label: '브랜드',        group: 'basic', default: true },
      { key: 'name',             label: '상품명',        group: 'basic', default: true },
      { key: 'regular_price',    label: '정상가격(원화)', group: 'basic', default: true },
      { key: 'discount_rate',    label: '할인율',        group: 'basic', default: true },
      { key: 'discounted_price', label: '할인가격(원화)', group: 'basic', default: true },
    ],
  },
}

/* ─── 카테고리 기본 config에서 체크 상태를 추출 ─── */
function buildCheckedState(agentType, catConfig) {
  const spec = COLLECT_ITEMS_BY_AGENT[agentType]
  if (!spec) return { fields: {}, options: {}, listType: '', pagination: '' }

  const fields = {}
  spec.fields.forEach(f => {
    if (agentType === 'product') {
      const coll = catConfig?.collect_fields || []
      fields[f.key] = coll.includes(f.key)
    } else if (agentType === 'banner') {
      const areas = catConfig?.banner_areas || []
      fields[f.key] = areas.includes(f.key)
    } else if (agentType === 'directory') {
      const coll = catConfig?.collect_fields || []
      fields[f.key] = coll.includes(f.key)
    } else if (agentType === 'local') {
      const coll = catConfig?.collect_fields || []
      fields[f.key] = coll.includes(f.key)
    }
  })

  const options = {}
  if (spec.options) {
    spec.options.forEach(o => {
      options[o.key] = catConfig?.[o.key] ?? false
    })
  }

  const listType = catConfig?.list_type || (spec.listTypes?.[0]?.value || '')
  const pagination = catConfig?.pagination || ''

  return { fields, options, listType, pagination }
}

/* ── order: 주문서 결제정보 수집 설정 ─────────── */
const MAX_PRODUCT_CODES = 1000
const MAX_EVENT_COUPONS = 50


/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   쿠폰 다운로드 에이전트 설정
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function CouponConfig({ site, onSaved, showConfirm, closeConfirm }) {
  const [config, setConfig] = useState(() => {
    const c = site.config || {}
    return {
      login_url: c.login_url || '',
      lps_login_url: c.lps_login_url || '',
      product_detail_url_template: c.product_detail_url_template || '',
      product_codes: Array.isArray(c.product_codes) ? c.product_codes : [],
      detail_coupon_selector: c.detail_coupon_selector || '',
      event_coupons: Array.isArray(c.event_coupons) ? c.event_coupons : [],
      event_list_url: c.event_list_url || '',
      coupon_keywords: Array.isArray(c.coupon_keywords) ? c.coupon_keywords : [],
      login_config: {
        id_selector: '', pwd_selector: '', submit_selector: '', success_indicator: '',
        ...(c.login_config || {}),
      },
    }
  })
  const [codesText, setCodesText] = useState(() => (config.product_codes || []).join('\n'))
  const [keywordsText, setKeywordsText] = useState(() => (config.coupon_keywords || []).join('\n'))
  const [newEventUrl, setNewEventUrl] = useState('')
  const [newEventSelector, setNewEventSelector] = useState('')

  const parsedKeywords = useMemo(() => {
    const seen = new Set()
    const out = []
    for (const line of keywordsText.split(/\r?\n/)) {
      const t = line.trim()
      if (!t || seen.has(t)) continue
      seen.add(t)
      out.push(t)
    }
    return out
  }, [keywordsText])

  const parsedCodes = useMemo(() => {
    const seen = new Set()
    const out = []
    for (const line of codesText.split(/\r?\n/)) {
      const t = line.trim()
      if (!t || seen.has(t)) continue
      seen.add(t)
      out.push(t)
      if (out.length >= MAX_PRODUCT_CODES) break
    }
    return out
  }, [codesText])

  const addEventCoupon = () => {
    const url = newEventUrl.trim()
    const sel = newEventSelector.trim()
    if (!url || !sel) return
    if (config.event_coupons.length >= MAX_EVENT_COUPONS) return
    setConfig(c => ({
      ...c,
      event_coupons: [...c.event_coupons, { url, selector: sel }],
    }))
    setNewEventUrl('')
    setNewEventSelector('')
  }

  const removeEventCoupon = (idx) => {
    setConfig(c => ({
      ...c,
      event_coupons: c.event_coupons.filter((_, i) => i !== idx),
    }))
  }

  const handleSave = () => {
    showConfirm({
      title: '설정 저장',
      message: `"${site.name}" 쿠폰 다운로드 설정을 저장하시겠습니까?`,
      confirmLabel: '저장',
      onConfirm: async () => {
        closeConfirm()
        try {
          const payload = { ...config, product_codes: parsedCodes, coupon_keywords: parsedKeywords }
          const res = await fetch(`/api/sites/${site.id}/config`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ crawl_config: payload }),
          })
          if (!res.ok) throw new Error()
          onSaved()
        } catch {
          alert('설정 저장에 실패했습니다.')
        }
      },
    })
  }

  const productCount = parsedCodes.length
  const eventCount = config.event_coupons.length
  const hasAutoDiscovery = !!(config.event_list_url.trim() && parsedKeywords.length > 0)
  const workflowSteps = [
    { label: '로그인', desc: '메인+LPS 도메인 로그인 → 쿠키 공유', icon: '🔑' },
    ...(eventCount > 0 ? [{
      label: '이벤트 쿠폰',
      desc: `이벤트 페이지 ${eventCount}건 순회 → 쿠폰 다운로드`,
      icon: '🎁',
      repeat: eventCount > 1,
    }] : []),
    ...(hasAutoDiscovery ? [{
      label: '자동 탐색 쿠폰',
      desc: `이벤트 목록 자동 순회 → 키워드 ${parsedKeywords.length}개로 쿠폰 탐색`,
      icon: '🔍',
      repeat: true,
    }] : []),
    ...(config.detail_coupon_selector.trim() ? [{
      label: '상품상세 쿠폰',
      desc: `상품 ${productCount}건 상세페이지 → 쿠폰 다운로드`,
      icon: '🎫',
      repeat: productCount > 1,
    }] : []),
    { label: '완료', desc: '쿠키 저장 → 결과 JSON 출력', icon: '✅', terminal: true },
  ]

  return (
    <div>
      <p className="config-section-desc">
        이벤트 페이지와 상품 상세에서 쿠폰을 다운로드합니다.
        주문서 수집 전에 실행하면 쿠키를 공유하여 할인 적용된 결제정보를 수집할 수 있습니다.
      </p>

      <div className="product-config-section active" style={{marginTop:12}}>
        <div className="config-section-title">수집 워크플로우</div>
        <div className="order-workflow">
          {workflowSteps.map((s, i) => (
            <div key={i} className="order-workflow-step">
              <div className={`order-workflow-node${s.terminal ? ' terminal' : ''}`}>
                <span className="order-workflow-num">{s.icon || (i + 1)}</span>
                <div className="order-workflow-label">
                  {s.label}
                  {s.repeat && <span className="order-workflow-loop">↻ 반복</span>}
                </div>
                <div className="order-workflow-desc">{s.desc}</div>
              </div>
              {i < workflowSteps.length - 1 && (
                <div className="order-workflow-arrow">→</div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* ── 이벤트 쿠폰 URL 관리 ── */}
      <div className="product-config-section active" style={{marginTop:12}}>
        <div className="config-section-title">
          이벤트 페이지 쿠폰
          <span style={{fontSize:11,color:'var(--text-secondary)',marginLeft:8}}>
            ({eventCount}건 등록)
          </span>
        </div>
        <p className="config-section-desc">
          쿠폰 다운로드가 필요한 이벤트 페이지 URL과 쿠폰 버튼 텍스트/셀렉터를 등록합니다.
          (#, . 으로 시작하면 CSS 셀렉터, 그 외에는 텍스트 매칭)
        </p>

        {config.event_coupons.length > 0 && (
          <div style={{marginTop:8,display:'flex',flexDirection:'column',gap:6}}>
            {config.event_coupons.map((ec, i) => (
              <div key={i} style={{
                display:'flex', alignItems:'center', gap:8,
                padding:'6px 10px', background:'var(--bg-secondary)',
                borderRadius:6, border:'1px solid var(--border)', fontSize:12,
              }}>
                <div style={{flex:1,overflow:'hidden'}}>
                  <div style={{fontWeight:500,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
                    {ec.url}
                  </div>
                  <div style={{color:'var(--text-secondary)',fontSize:11,marginTop:2}}>
                    버튼: {ec.selector}
                  </div>
                </div>
                <button
                  className="btn btn-outline btn-sm"
                  style={{fontSize:11,padding:'2px 8px',flexShrink:0,color:'var(--danger, #d33)'}}
                  onClick={() => removeEventCoupon(i)}
                >
                  삭제
                </button>
              </div>
            ))}
          </div>
        )}

        <div style={{display:'flex',gap:6,marginTop:8,alignItems:'flex-end'}}>
          <div style={{flex:2}}>
            <label style={{fontSize:11,color:'var(--text-secondary)'}}>이벤트 페이지 URL</label>
            <input
              className="form-control"
              placeholder="https://kor.lottedfs.com/kr/event/..."
              value={newEventUrl}
              onChange={e => setNewEventUrl(e.target.value)}
              style={{fontSize:12,marginTop:2}}
            />
          </div>
          <div style={{flex:1}}>
            <label style={{fontSize:11,color:'var(--text-secondary)'}}>쿠폰 버튼</label>
            <input
              className="form-control"
              placeholder="쿠폰 받기"
              value={newEventSelector}
              onChange={e => setNewEventSelector(e.target.value)}
              style={{fontSize:12,marginTop:2}}
            />
          </div>
          <button
            className="btn btn-outline btn-sm"
            style={{fontSize:11,padding:'6px 12px',flexShrink:0}}
            disabled={!newEventUrl.trim() || !newEventSelector.trim() || eventCount >= MAX_EVENT_COUPONS}
            onClick={addEventCoupon}
          >
            + 추가
          </button>
        </div>
      </div>

      {/* ── 이벤트 자동 탐색 쿠폰 ── */}
      <div className="product-config-section active" style={{marginTop:12}}>
        <div className="config-section-title" style={{display:'flex',alignItems:'center',gap:8}}>
          🔍 이벤트 자동 탐색
          {hasAutoDiscovery && (
            <span style={{fontSize:11,color:'var(--success, #16a34a)',fontWeight:400}}>
              활성 (키워드 {parsedKeywords.length}개)
            </span>
          )}
        </div>
        <p className="config-section-desc">
          이벤트 목록 페이지를 자동 순회하여 쿠폰 버튼을 탐색합니다.
          목록 진입 URL과 쿠폰 버튼 키워드를 등록하면 자동으로 하위 이벤트 페이지를 방문합니다.
        </p>
        <div style={{display:'flex',flexDirection:'column',gap:8,marginTop:8}}>
          <label style={{fontSize:12}}>
            <span style={{color:'var(--text-secondary)'}}>이벤트 목록 진입 URL</span>
            <span style={{fontSize:11,color:'var(--text-secondary)',marginLeft:4}}>(하위 이벤트 링크가 있는 페이지)</span>
            <input
              className="form-control"
              placeholder="https://kor.lottedfs.com/kr/event/eventDetail?evtDispNo=1044712"
              value={config.event_list_url}
              onChange={e => setConfig(c => ({...c, event_list_url: e.target.value}))}
              style={{marginTop:4,fontSize:12}}
            />
          </label>
          <div style={{fontSize:12}}>
            <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',gap:8}}>
              <div>
                <span style={{color:'var(--text-secondary)'}}>쿠폰 버튼 키워드</span>
                <span style={{fontSize:11,color:'var(--text-secondary)',marginLeft:4}}>
                  (엔터로 구분, 버튼 텍스트 매칭용)
                </span>
              </div>
              <span style={{fontSize:11,color:'var(--text-secondary)'}}>
                등록 {parsedKeywords.length}건
              </span>
            </div>
            <textarea
              className="form-control"
              placeholder={'쿠폰 다운로드\n혜택받기\n쿠폰받기\n다운받기'}
              value={keywordsText}
              onChange={e => setKeywordsText(e.target.value)}
              rows={4}
              spellCheck={false}
              style={{
                marginTop:4,fontSize:12,fontFamily:'monospace',
                resize:'vertical',minHeight:60,
              }}
            />
          </div>
        </div>
      </div>

      {/* ── 상품상세 쿠폰 ── */}
      <div className="product-config-section active" style={{marginTop:12}}>
        <div className="config-section-title">상품상세 쿠폰</div>
        <p className="config-section-desc">
          상품 상세페이지에서 쿠폰을 다운로드할 버튼의 텍스트나 CSS 셀렉터를 입력합니다.
          비워두면 상품상세 쿠폰 다운로드를 건너뜁니다.
        </p>
        <input
          className="form-control"
          placeholder="오늘의 혜택받기 또는 .benefit-btn"
          value={config.detail_coupon_selector}
          onChange={e => setConfig(c => ({...c, detail_coupon_selector: e.target.value}))}
          style={{marginTop:4,fontSize:12}}
        />
      </div>

      {/* ── 페이지 URL ── */}
      <div className="product-config-section active" style={{marginTop:12}}>
        <div className="config-section-title">페이지 URL</div>
        <div style={{display:'flex',flexDirection:'column',gap:8,marginTop:8}}>
          <label style={{fontSize:12}}>
            <span style={{color:'var(--text-secondary)'}}>로그인 URL</span>
            <span style={{fontSize:11,color:'var(--text-secondary)',marginLeft:4}}>(비워두면 사이트 URL 사용)</span>
            <input
              className="form-control"
              placeholder="https://kor.lottedfs.com/kr/login"
              value={config.login_url}
              onChange={e => setConfig(c => ({...c, login_url: e.target.value}))}
              style={{marginTop:4,fontSize:12}}
            />
          </label>
          <label style={{fontSize:12}}>
            <span style={{color:'var(--text-secondary)'}}>LPS 로그인 URL</span>
            <span style={{fontSize:11,color:'var(--text-secondary)',marginLeft:4}}>(서브도메인 로그인, 비워두면 자동감지)</span>
            <input
              className="form-control"
              placeholder="https://kor.lps.lottedfs.com/kr/member/login"
              value={config.lps_login_url}
              onChange={e => setConfig(c => ({...c, lps_login_url: e.target.value}))}
              style={{marginTop:4,fontSize:12}}
            />
          </label>
          <label style={{fontSize:12}}>
            <span style={{color:'var(--text-secondary)'}}>상품상세 URL</span>
            <span style={{fontSize:11,color:'var(--text-secondary)',marginLeft:4}}>{'(상품코드 위치에 {prdNo} 사용)'}</span>
            <input
              className="form-control"
              placeholder="https://kor.lottedfs.com/kr/product/productDetail?prdNo={prdNo}"
              value={config.product_detail_url_template}
              onChange={e => setConfig(c => ({...c, product_detail_url_template: e.target.value}))}
              style={{marginTop:4,fontSize:12}}
            />
          </label>
          <div style={{fontSize:12}}>
            <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',gap:8}}>
              <div>
                <span style={{color:'var(--text-secondary)'}}>상품코드</span>
                <span style={{fontSize:11,color:'var(--text-secondary)',marginLeft:4}}>
                  (엔터로 구분, 쿠폰 다운로드 대상)
                </span>
              </div>
              <span style={{fontSize:11,color:'var(--text-secondary)'}}>
                등록 {parsedCodes.length.toLocaleString()}건
              </span>
            </div>
            <textarea
              className="form-control"
              placeholder={'20000996458\n20000996459\n...'}
              value={codesText}
              onChange={e => setCodesText(e.target.value)}
              rows={5}
              spellCheck={false}
              style={{
                marginTop:4,fontSize:12,fontFamily:'monospace',
                resize:'vertical',minHeight:80,
              }}
            />
          </div>
        </div>
      </div>

      {/* ── 로그인 폼 셀렉터 ── */}
      <div className="product-config-section active" style={{marginTop:12}}>
        <div className="config-section-title">로그인 폼 셀렉터 (선택)</div>
        <p className="config-section-desc">비워두면 자동 탐지합니다. 로그인 실패 시 수동 지정하세요.</p>
        <div className="order-selector-grid">
          <label>
            <span>ID 입력 셀렉터</span>
            <input className="form-control" placeholder="#userId"
              value={config.login_config.id_selector || ''}
              onChange={e => setConfig(c => ({...c, login_config: {...c.login_config, id_selector: e.target.value}}))}
            />
          </label>
          <label>
            <span>비밀번호 셀렉터</span>
            <input className="form-control" placeholder="#password"
              value={config.login_config.pwd_selector || ''}
              onChange={e => setConfig(c => ({...c, login_config: {...c.login_config, pwd_selector: e.target.value}}))}
            />
          </label>
          <label>
            <span>로그인 버튼 셀렉터</span>
            <input className="form-control" placeholder="#loginBtn"
              value={config.login_config.submit_selector || ''}
              onChange={e => setConfig(c => ({...c, login_config: {...c.login_config, submit_selector: e.target.value}}))}
            />
          </label>
          <label>
            <span>로그인 성공 지표</span>
            <input className="form-control" placeholder=".my-page, .logout"
              value={config.login_config.success_indicator || ''}
              onChange={e => setConfig(c => ({...c, login_config: {...c.login_config, success_indicator: e.target.value}}))}
            />
          </label>
        </div>
      </div>

      <div style={{textAlign:'right',marginTop:16}}>
        <button className="btn btn-primary" onClick={handleSave}>저장</button>
      </div>
    </div>
  )
}


function OrderConfig({ site, onSaved, showConfirm, closeConfirm, fieldDefs }) {
  const collectFieldDefs = fieldDefs.filter(f => f.config_key === 'collect_fields')
  const allFieldKeys = collectFieldDefs.map(f => f.key)

  const [config, setConfig] = useState(() => {
    const c = site.config || {}
    return {
      login_url: c.login_url || '',
      product_detail_url_template: c.product_detail_url_template || '',
      order_url: c.order_url || '',
      product_codes: Array.isArray(c.product_codes) ? c.product_codes : [],
      collect_payment: c.collect_payment !== false,
      collect_fields: Array.isArray(c.collect_fields) ? c.collect_fields : [...allFieldKeys],
      order_coupon_selector: c.order_coupon_selector || '',
      lps_login_url: c.lps_login_url || '',
      event_coupons: Array.isArray(c.event_coupons) ? c.event_coupons : [],
      event_list_url: c.event_list_url || '',
      coupon_keywords: Array.isArray(c.coupon_keywords) ? c.coupon_keywords : [],
      detail_coupon_selector: c.detail_coupon_selector || '',
      login_config: {
        id_selector: '', pwd_selector: '', submit_selector: '', success_indicator: '',
        ...(c.login_config || {}),
      },
    }
  })
  const [codesText, setCodesText] = useState(() => (config.product_codes || []).join('\n'))
  const [keywordsText, setKeywordsText] = useState(() => (config.coupon_keywords || []).join('\n'))
  const [newEventUrl, setNewEventUrl] = useState('')
  const [newEventSelector, setNewEventSelector] = useState('')

  const addEventCoupon = () => {
    const url = newEventUrl.trim()
    const sel = newEventSelector.trim()
    if (!url || !sel) return
    if (config.event_coupons.length >= MAX_EVENT_COUPONS) return
    setConfig(c => ({
      ...c,
      event_coupons: [...c.event_coupons, { url, selector: sel }],
    }))
    setNewEventUrl('')
    setNewEventSelector('')
  }

  const removeEventCoupon = (idx) => {
    setConfig(c => ({
      ...c,
      event_coupons: c.event_coupons.filter((_, i) => i !== idx),
    }))
  }

  const parsedCodes = useMemo(() => {
    const seen = new Set()
    const out = []
    for (const line of codesText.split(/\r?\n/)) {
      const t = line.trim()
      if (!t || seen.has(t)) continue
      seen.add(t)
      out.push(t)
      if (out.length >= MAX_PRODUCT_CODES) break
    }
    return out
  }, [codesText])

  const parsedKeywords = useMemo(() => {
    const seen = new Set()
    const out = []
    for (const line of keywordsText.split(/\r?\n/)) {
      const t = line.trim()
      if (!t || seen.has(t)) continue
      seen.add(t)
      out.push(t)
    }
    return out
  }, [keywordsText])

  const rawLineCount = useMemo(
    () => codesText.split(/\r?\n/).filter(l => l.trim()).length,
    [codesText],
  )
  const overLimit = rawLineCount > MAX_PRODUCT_CODES
  const dupCount = rawLineCount - parsedCodes.length - Math.max(0, rawLineCount - MAX_PRODUCT_CODES)

  const handleSave = () => {
    showConfirm({
      title: '설정 저장',
      message: `"${site.name}" 주문서 수집 설정을 저장하시겠습니까? (상품코드 ${parsedCodes.length}건)`,
      confirmLabel: '저장',
      onConfirm: async () => {
        closeConfirm()
        try {
          const payload = { ...config, product_codes: parsedCodes, coupon_keywords: parsedKeywords }
          const res = await fetch(`/api/sites/${site.id}/config`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ crawl_config: payload }),
          })
          if (!res.ok) throw new Error()
          onSaved()
        } catch {
          alert('설정 저장에 실패했습니다.')
        }
      },
    })
  }

  const productCount = parsedCodes.length
  const hasOrderCoupon = !!config.order_coupon_selector.trim()
  const hasEventCoupons = config.event_coupons.length > 0
  const hasAutoDiscovery = !!(config.event_list_url.trim() && parsedKeywords.length > 0)
  const hasDetailCoupon = !!config.detail_coupon_selector.trim()
  const hasCouponPhase = hasEventCoupons || hasDetailCoupon || hasAutoDiscovery

  /* ── 쿠폰 다운로드 Agent 영역 ── */
  const couponSteps = [
    ...(hasEventCoupons ? [{
      label: '이벤트 쿠폰',
      desc: `이벤트 페이지 ${config.event_coupons.length}건 → 쿠폰 다운로드`,
      icon: '🎁',
      repeat: config.event_coupons.length > 1,
    }] : []),
    ...(hasAutoDiscovery ? [{
      label: '자동 탐색 쿠폰',
      desc: `이벤트 목록 자동 순회 → 키워드 ${parsedKeywords.length}개로 쿠폰 탐색`,
      icon: '🔍',
      repeat: true,
    }] : []),
    ...(hasDetailCoupon ? [{
      label: '상품상세 쿠폰',
      desc: `상품 ${productCount}건 상세페이지 → 쿠폰 다운로드`,
      icon: '🎫',
      repeat: productCount > 1,
    }] : []),
  ]

  /* ── 주문서 수집 Agent 영역 ── */
  const orderSteps = [
    { label: '상품상세', desc: '등록한 상품상세 URL로 순회', icon: '📦' },
    {
      label: '바로구매',
      desc: `등록 ${productCount.toLocaleString()}건 × 바로구매 클릭`,
      repeat: productCount > 1,
      icon: '🛒',
    },
    ...(hasOrderCoupon ? [{
      label: '주문서 쿠폰',
      desc: '주문서 내 쿠폰 다운로드',
      icon: '🏷️',
    }] : []),
    { label: '출입국 확인', desc: '출입국정보 등록 확인 → 미등록 시 스킵', icon: '✈️' },
    {
      label: '결제정보 수집',
      desc: '상품명·결제금액(USD/KRW)·할인율 추출',
      repeat: productCount > 1,
      icon: '💳',
    },
    { label: '로그아웃', desc: '메인 홈 이동 → logout() 호출', terminal: true, icon: '🚪' },
  ]

  const renderSteps = (steps) => (
    <div className="order-workflow">
      {steps.map((s, i) => (
        <div key={i} className="order-workflow-step">
          <div className={`order-workflow-node${s.terminal ? ' terminal' : ''}`}>
            <span className="order-workflow-num">{s.icon || (i + 1)}</span>
            <div className="order-workflow-label">
              {s.label}
              {s.repeat && <span className="order-workflow-loop">↻ 반복</span>}
            </div>
            <div className="order-workflow-desc">{s.desc}</div>
          </div>
          {i < steps.length - 1 && (
            <div className="order-workflow-arrow">→</div>
          )}
        </div>
      ))}
    </div>
  )

  return (
    <div>
      <p className="config-section-desc">
        상품 코드별로 상품상세 → 주문서 이동 → 결제정보 수집을 반복합니다.
        로그인 계정은 하단에서 등록하세요.
      </p>

      <div className="product-config-section active" style={{marginTop:12}}>
        <div className="config-section-title">수집 워크플로우</div>

        {/* ── 공통: 로그인 ── */}
        <div className="order-flow-login-bar">
          <span className="order-flow-login-icon">🔑</span>
          <span>로그인 (메인 + LPS 도메인, 1회)</span>
        </div>

        {/* ── Phase 1: 쿠폰 다운로드 Agent ── */}
        <div className={`order-flow-phase coupon-phase${hasCouponPhase ? '' : ' empty'}`}>
          <div className="order-flow-phase-header">
            <span className="badge coupon-badge" style={{fontSize:11}}>쿠폰 다운로드</span>
            <span style={{fontSize:11,color:'var(--text-secondary)'}}>
              {hasCouponPhase
                ? '이벤트 페이지 + 상품상세 쿠폰 다운로드'
                : '아래에서 쿠폰 설정을 등록하면 표시됩니다'}
            </span>
          </div>
          {hasCouponPhase && renderSteps(couponSteps)}
        </div>

        {/* ── 연결 ── */}
        <div className="order-flow-connector">
          <div className="order-flow-connector-line" />
          <span className="order-flow-connector-label">같은 세션</span>
          <div className="order-flow-connector-line" />
        </div>

        {/* ── Phase 2: 주문서 수집 Agent ── */}
        <div className="order-flow-phase order-phase">
          <div className="order-flow-phase-header">
            <span className="badge order-badge" style={{fontSize:11}}>주문서 수집</span>
            <span style={{fontSize:11,color:'var(--text-secondary)'}}>바로구매 → 결제정보 수집</span>
          </div>
          {renderSteps(orderSteps)}
        </div>
      </div>

      {/* ── 이벤트 페이지 쿠폰 (CouponAgent 설정) ── */}
      <div className="product-config-section active" style={{marginTop:12}}>
        <div className="config-section-title" style={{display:'flex',alignItems:'center',gap:8}}>
          🎁 이벤트 페이지 쿠폰
          <span style={{fontSize:11,color:'var(--text-secondary)',fontWeight:400}}>
            ({config.event_coupons.length}건 등록)
          </span>
        </div>
        <p className="config-section-desc">
          쿠폰 다운로드가 필요한 이벤트 페이지 URL과 쿠폰 버튼의 텍스트 또는 CSS 셀렉터를 등록합니다.
          (#, . 시작 = CSS 셀렉터, 그 외 = 텍스트 매칭). 비워두면 이벤트 쿠폰 단계를 건너뜁니다.
        </p>

        {config.event_coupons.length > 0 && (
          <div style={{marginTop:8,display:'flex',flexDirection:'column',gap:6}}>
            {config.event_coupons.map((ec, i) => (
              <div key={i} style={{
                display:'flex', alignItems:'center', gap:8,
                padding:'6px 10px', background:'var(--bg-secondary)',
                borderRadius:6, border:'1px solid var(--border)', fontSize:12,
              }}>
                <div style={{flex:1,overflow:'hidden'}}>
                  <div style={{fontWeight:500,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
                    {ec.url}
                  </div>
                  <div style={{color:'var(--text-secondary)',fontSize:11,marginTop:2}}>
                    버튼: <code style={{background:'rgba(0,0,0,0.06)',padding:'1px 4px',borderRadius:3}}>{ec.selector}</code>
                  </div>
                </div>
                <button
                  className="btn btn-outline btn-sm"
                  style={{fontSize:11,padding:'2px 8px',flexShrink:0,color:'var(--danger, #d33)'}}
                  onClick={() => removeEventCoupon(i)}
                >
                  삭제
                </button>
              </div>
            ))}
          </div>
        )}

        <div style={{display:'flex',gap:6,marginTop:8,alignItems:'flex-end'}}>
          <div style={{flex:2}}>
            <label style={{fontSize:11,color:'var(--text-secondary)'}}>이벤트 페이지 URL</label>
            <input
              className="form-control"
              placeholder="https://kor.lottedfs.com/kr/event/..."
              value={newEventUrl}
              onChange={e => setNewEventUrl(e.target.value)}
              style={{fontSize:12,marginTop:2}}
            />
          </div>
          <div style={{flex:1}}>
            <label style={{fontSize:11,color:'var(--text-secondary)'}}>쿠폰 버튼</label>
            <input
              className="form-control"
              placeholder="쿠폰 받기"
              value={newEventSelector}
              onChange={e => setNewEventSelector(e.target.value)}
              style={{fontSize:12,marginTop:2}}
            />
          </div>
          <button
            className="btn btn-outline btn-sm"
            style={{fontSize:11,padding:'6px 12px',flexShrink:0}}
            disabled={!newEventUrl.trim() || !newEventSelector.trim() || config.event_coupons.length >= MAX_EVENT_COUPONS}
            onClick={addEventCoupon}
          >
            + 추가
          </button>
        </div>
      </div>

      {/* ── 이벤트 자동 탐색 쿠폰 (CouponAgent 설정) ── */}
      <div className="product-config-section active" style={{marginTop:12}}>
        <div className="config-section-title" style={{display:'flex',alignItems:'center',gap:8}}>
          🔍 이벤트 자동 탐색
          {hasAutoDiscovery && (
            <span style={{fontSize:11,color:'var(--success, #16a34a)',fontWeight:400}}>
              활성 (키워드 {parsedKeywords.length}개)
            </span>
          )}
        </div>
        <p className="config-section-desc">
          이벤트 목록 페이지를 자동 순회하여 쿠폰 버튼을 탐색합니다.
          목록 진입 URL과 쿠폰 버튼 키워드를 등록하면 자동으로 하위 이벤트 페이지를 방문합니다.
        </p>
        <div style={{display:'flex',flexDirection:'column',gap:8,marginTop:8}}>
          <label style={{fontSize:12}}>
            <span style={{color:'var(--text-secondary)'}}>이벤트 목록 진입 URL</span>
            <span style={{fontSize:11,color:'var(--text-secondary)',marginLeft:4}}>(하위 이벤트 링크가 있는 페이지)</span>
            <input
              className="form-control"
              placeholder="https://kor.lottedfs.com/kr/event/eventDetail?evtDispNo=1044712"
              value={config.event_list_url}
              onChange={e => setConfig(c => ({...c, event_list_url: e.target.value}))}
              style={{marginTop:4,fontSize:12}}
            />
          </label>
          <div style={{fontSize:12}}>
            <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',gap:8}}>
              <div>
                <span style={{color:'var(--text-secondary)'}}>쿠폰 버튼 키워드</span>
                <span style={{fontSize:11,color:'var(--text-secondary)',marginLeft:4}}>
                  (엔터로 구분, 버튼 텍스트 매칭용)
                </span>
              </div>
              <span style={{fontSize:11,color:'var(--text-secondary)'}}>
                등록 {parsedKeywords.length}건
              </span>
            </div>
            <textarea
              className="form-control"
              placeholder={'쿠폰 다운로드\n혜택받기\n쿠폰받기\n다운받기'}
              value={keywordsText}
              onChange={e => setKeywordsText(e.target.value)}
              rows={4}
              spellCheck={false}
              style={{
                marginTop:4,fontSize:12,fontFamily:'monospace',
                resize:'vertical',minHeight:60,
              }}
            />
          </div>
        </div>
      </div>

      {/* ── 상품상세 쿠폰 (CouponAgent 설정) ── */}
      <div className="product-config-section active" style={{marginTop:12}}>
        <div className="config-section-title">🎫 상품상세 쿠폰</div>
        <p className="config-section-desc">
          상품 상세페이지에서 쿠폰을 다운로드할 버튼의 텍스트나 CSS 셀렉터를 입력합니다.
          비워두면 상품상세 쿠폰 다운로드를 건너뜁니다.
        </p>
        <input
          className="form-control"
          placeholder="오늘의 혜택받기 또는 .benefit-btn"
          value={config.detail_coupon_selector}
          onChange={e => setConfig(c => ({...c, detail_coupon_selector: e.target.value}))}
          style={{marginTop:4,fontSize:12}}
        />
      </div>

      <div className="product-config-section active" style={{marginTop:12}}>
        <div className="config-section-title">페이지 URL</div>
        <div style={{display:'flex',flexDirection:'column',gap:8,marginTop:8}}>
          <label style={{fontSize:12}}>
            <span style={{color:'var(--text-secondary)'}}>로그인 URL</span>
            <span style={{fontSize:11,color:'var(--text-secondary)',marginLeft:4}}>(비워두면 사이트 URL 사용)</span>
            <input
              className="form-control"
              placeholder="https://kor.lottedfs.com/kr/login"
              value={config.login_url}
              onChange={e => setConfig(c => ({...c, login_url: e.target.value}))}
              style={{marginTop:4,fontSize:12}}
            />
          </label>
          <label style={{fontSize:12}}>
            <span style={{color:'var(--text-secondary)'}}>상품상세 URL</span>
            <span style={{fontSize:11,color:'var(--text-secondary)',marginLeft:4}}>{'(상품코드 위치에 {prdNo} 사용)'}</span>
            <input
              className="form-control"
              placeholder="https://kor.lottedfs.com/kr/product/productDetail?prdNo={prdNo}&adltPrdYn=Y&onOff=on"
              value={config.product_detail_url_template}
              onChange={e => setConfig(c => ({...c, product_detail_url_template: e.target.value}))}
              style={{marginTop:4,fontSize:12}}
            />
          </label>
          <div style={{fontSize:12}}>
            <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',gap:8}}>
              <div>
                <span style={{color:'var(--text-secondary)'}}>상품코드</span>
                <span style={{fontSize:11,color:'var(--text-secondary)',marginLeft:4}}>
                  (엔터로 구분, 최대 {MAX_PRODUCT_CODES.toLocaleString()}건)
                </span>
              </div>
              <span style={{
                fontSize:11,
                color: overLimit ? 'var(--danger, #d33)' : 'var(--text-secondary)',
                fontWeight: overLimit ? 600 : 400,
              }}>
                등록 {parsedCodes.length.toLocaleString()}건
                {dupCount > 0 && ` (중복 ${dupCount}건 제외)`}
                {overLimit && ` · 최대 ${MAX_PRODUCT_CODES.toLocaleString()}건 초과`}
              </span>
            </div>
            <textarea
              className="form-control"
              placeholder={'20000996458\n20000996459\n...'}
              value={codesText}
              onChange={e => setCodesText(e.target.value)}
              rows={8}
              spellCheck={false}
              style={{
                marginTop:4,fontSize:12,fontFamily:'monospace',
                resize:'vertical',minHeight:120,
              }}
            />
          </div>
          <label style={{fontSize:12}}>
            <span style={{color:'var(--text-secondary)'}}>주문서 URL</span>
            <span style={{fontSize:11,color:'var(--text-secondary)',marginLeft:4}}>(구매 클릭 후 도달 URL 패턴)</span>
            <input
              className="form-control"
              placeholder="https://kor.lps.lottedfs.com/kr/newOrder"
              value={config.order_url}
              onChange={e => setConfig(c => ({...c, order_url: e.target.value}))}
              style={{marginTop:4,fontSize:12}}
            />
          </label>
          <label style={{fontSize:12}}>
            <span style={{color:'var(--text-secondary)'}}>LPS 로그인 URL</span>
            <span style={{fontSize:11,color:'var(--text-secondary)',marginLeft:4}}>(서브도메인 로그인, 비워두면 자동감지)</span>
            <input
              className="form-control"
              placeholder="https://kor.lps.lottedfs.com/kr/member/login"
              value={config.lps_login_url}
              onChange={e => setConfig(c => ({...c, lps_login_url: e.target.value}))}
              style={{marginTop:4,fontSize:12}}
            />
          </label>
        </div>
      </div>

      <div className="product-config-section active" style={{marginTop:12}}>
        <div className="config-section-title">주문서 쿠폰 다운로드</div>
        <p className="config-section-desc">
          주문서 페이지에서 쿠폰을 다운로드할 버튼의 텍스트나 CSS 셀렉터를 입력합니다.
          비워두면 쿠폰 다운로드를 건너뜁니다. (#, . 으로 시작하면 CSS 셀렉터, 그 외에는 텍스트 매칭
        </p>
        <input
          className="form-control"
          placeholder="쿠폰 다운로드 또는 .coupon-download-btn"
          value={config.order_coupon_selector}
          onChange={e => setConfig(c => ({...c, order_coupon_selector: e.target.value}))}
          style={{marginTop:4,fontSize:12}}
        />
      </div>

      <div className="product-config-section active" style={{marginTop:12}}>
        <div className="config-section-title" style={{display:'flex',alignItems:'center',justifyContent:'space-between'}}>
          <span>수집 항목 ({config.collect_fields.length}/{collectFieldDefs.length})</span>
          <div style={{display:'flex',gap:6}}>
            <button type="button" className="btn btn-sm"
              style={{fontSize:11,padding:'2px 8px'}}
              onClick={() => setConfig(c => ({...c, collect_fields: [...allFieldKeys]}))}
            >전체선택</button>
            <button type="button" className="btn btn-sm"
              style={{fontSize:11,padding:'2px 8px'}}
              onClick={() => setConfig(c => ({...c, collect_fields: []}))}
            >전체해제</button>
          </div>
        </div>
        <div className="field-checkbox-grid" style={{marginTop:8}}>
          {collectFieldDefs.map(f => {
            const checked = config.collect_fields.includes(f.key)
            return (
              <label key={f.key}
                className={`field-checkbox ${checked ? 'checked' : ''}`}
                title={f.group}
              >
                <input type="checkbox" checked={checked}
                  onChange={() => setConfig(c => ({
                    ...c,
                    collect_fields: checked
                      ? c.collect_fields.filter(k => k !== f.key)
                      : [...c.collect_fields, f.key],
                  }))}
                />
                <span>{f.label}</span>
              </label>
            )
          })}
        </div>
      </div>

      <div className="product-config-section active" style={{marginTop:12}}>
        <div className="config-section-title">로그인 폼 셀렉터 (선택)</div>
        <p className="config-section-desc">비워두면 자동 탐지합니다. 로그인 실패 시 수동 지정하세요.</p>
        <div className="order-selector-grid">
          <label>
            <span>ID 입력 셀렉터</span>
            <input className="form-control" placeholder="#userId"
              value={config.login_config.id_selector || ''}
              onChange={e => setConfig(c => ({...c, login_config: {...c.login_config, id_selector: e.target.value}}))}
            />
          </label>
          <label>
            <span>비밀번호 셀렉터</span>
            <input className="form-control" placeholder="#password"
              value={config.login_config.pwd_selector || ''}
              onChange={e => setConfig(c => ({...c, login_config: {...c.login_config, pwd_selector: e.target.value}}))}
            />
          </label>
          <label>
            <span>로그인 버튼 셀렉터</span>
            <input className="form-control" placeholder="#loginBtn"
              value={config.login_config.submit_selector || ''}
              onChange={e => setConfig(c => ({...c, login_config: {...c.login_config, submit_selector: e.target.value}}))}
            />
          </label>
          <label>
            <span>로그인 성공 지표</span>
            <input className="form-control" placeholder=".my-page, .logout"
              value={config.login_config.success_indicator || ''}
              onChange={e => setConfig(c => ({...c, login_config: {...c.login_config, success_indicator: e.target.value}}))}
            />
          </label>
        </div>
      </div>

      <div style={{textAlign:'right',marginTop:16}}>
        <button className="btn btn-primary" onClick={handleSave}>저장</button>
      </div>
    </div>
  )
}


/* ── brand: 브랜드 공식홈 상품가격 수집 설정 ──────── */
const BRAND_COLLECT_FIELDS = [
  // 기본 필드
  { key: 'brand',          label: '브랜드',     group: 'basic' },
  { key: 'name',           label: '상품명',     group: 'basic' },
  { key: 'original_price', label: '정상가격(원화)', group: 'basic' },
  // 추가 필드
  { key: 'reference_no',   label: 'Ref No',     group: 'extra' },
  { key: 'is_new',         label: '신제품여부', group: 'extra' },
  { key: 'category',       label: '카테고리',   group: 'extra' },
]

/* ── local: 로컬 e커머스 상품 상세 수집 설정 ──────── */
function LocalConfig({ site, onSaved, showConfirm, closeConfirm, fieldDefs }) {
  const localFields = fieldDefs.filter(f => f.config_key === 'collect_fields')
  const defaultFieldKeys = localFields.map(f => f.key)
  const initConfig = {
    local_type: 'oliveyoung',
    collect_fields: (site.config?.collect_fields?.length > 0) ? site.config.collect_fields : defaultFieldKeys,
    ...site.config,
  }
  const [config, setConfig]   = useState(initConfig)
  const [urlText, setUrlText] = useState((site.keywords || []).map(k => k.keyword).join('\n'))
  const [saving, setSaving]   = useState(false)

  const urlCount = urlText.split(/\n/).filter(s => s.trim()).length

  const toggleField = (key) => {
    const fields = config.collect_fields || []
    setConfig({
      ...config,
      collect_fields: fields.includes(key) ? fields.filter(f => f !== key) : [...fields, key],
    })
  }

  const handleSave = () => {
    showConfirm({
      title: '설정 저장',
      message: `"${site.name}" 로컬 수집 설정을 저장하시겠습니까?`,
      confirmLabel: '저장',
      onConfirm: async () => {
        closeConfirm()
        setSaving(true)
        try {
          const res = await fetch(`/api/sites/${site.id}/config`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ crawl_config: config }),
          })
          if (!res.ok) { alert('저장 실패: 서버 오류'); return }

          const prevKeywords = (site.keywords || []).map(k => k.keyword)
          const nextKeywords = urlText.split(/\n/).map(s => s.trim()).filter(Boolean)
          for (const kw of prevKeywords.filter(k => !nextKeywords.includes(k))) {
            await fetch(`/api/sites/${site.id}/keywords/${encodeURIComponent(kw)}`, { method: 'DELETE' })
          }
          for (const kw of nextKeywords.filter(k => !prevKeywords.includes(k))) {
            await fetch(`/api/sites/${site.id}/keywords`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ keyword: kw }),
            })
          }
          onSaved()
        } catch (e) {
          alert('저장 실패: ' + (e.message || '네트워크 오류'))
        } finally {
          setSaving(false)
        }
      },
    })
  }

  return (
    <>
      <div style={{background:'#ecfdf5',padding:'12px 16px',borderRadius:8,marginBottom:20,fontSize:13,color:'#065f46'}}>
        상품 상세 페이지 URL에서 브랜드·상품명·가격 정보를 수집합니다.
      </div>

      {/* ── 수집 필드 ── */}
      <div className="product-config-section active">
        <h4 className="config-section-title">수집 필드</h4>
        <div className="config-section-desc">수집할 데이터 항목을 선택합니다</div>
        <div className="field-checkbox-grid">
          {localFields.map(f => {
            const checked = (config.collect_fields || []).includes(f.key)
            return (
              <label key={f.key} className={`field-checkbox ${checked ? 'checked' : ''}`}>
                <input type="checkbox" checked={checked} onChange={() => toggleField(f.key)} />
                <span>{f.label}</span>
              </label>
            )
          })}
        </div>
      </div>

      {/* ── 상품 상세 URL ── */}
      <div className="product-config-section active">
        <h4 className="config-section-title">상품 상세 URL</h4>
        <div className="config-section-desc">수집할 상품 상세 페이지 URL을 입력합니다 (줄바꿈으로 구분)</div>
        <textarea
          className="kw-textarea"
          value={urlText}
          onChange={e => setUrlText(e.target.value)}
          placeholder={"https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=...\nhttps://..."}
          rows={8}
          style={{ fontFamily:'monospace', fontSize:'12px', marginTop:8 }}
        />
        <div className="kw-count" style={{marginTop:4}}>{urlCount.toLocaleString()}건 등록</div>
      </div>

      <div style={{display:'flex',justifyContent:'flex-end',gap:8,marginTop:20}}>
        <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? '저장 중...' : '저장'}
        </button>
      </div>
    </>
  )
}

function BrandConfig({ site, onSaved, showConfirm, closeConfirm, fieldDefs }) {
  const brandFields = fieldDefs.filter(f => f.config_key === 'collect_fields')
  const defaultFieldKeys = brandFields.map(f => f.key)
  const [keywordText, setKeywordText] = useState(
    (site.keywords || []).map(k => k.keyword).join('\n')
  )
  const [config, setConfig] = useState({
    collect_fields: (site.config?.collect_fields?.length > 0) ? site.config.collect_fields : defaultFieldKeys,
    ...site.config,
  })
  const [saving, setSaving] = useState(false)
  const [checkingUrl, setCheckingUrl] = useState(false)
  const [urlCheckResult, setUrlCheckResult] = useState(null)

  const handleCheckUrl = async () => {
    if (!config.search_url_template) return
    const kw = keywordText.split(/[,\n]/).map(s => s.trim()).filter(Boolean)[0]
    if (!kw) { alert('연결 확인을 위해 검색어(SKU)를 먼저 입력해주세요.'); return }
    setCheckingUrl(true)
    setUrlCheckResult(null)
    try {
      const res = await fetch(`/api/sites/${site.id}/check-url`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url_template: config.search_url_template, keyword: kw }),
      })
      const data = await res.json()
      setUrlCheckResult(data)
    } catch (e) {
      setUrlCheckResult({ ok: false, message: '요청 실패: ' + e.message })
    } finally {
      setCheckingUrl(false)
    }
  }

  const toggleField = (key) => {
    const fields = config.collect_fields || []
    const next = fields.includes(key)
      ? fields.filter(f => f !== key)
      : [...fields, key]
    setConfig({ ...config, collect_fields: next })
  }

  const handleSaveConfig = () => {
    showConfirm({
      title: '설정 저장',
      message: `"${site.name}" 브랜드 수집 설정을 저장하시겠습니까?`,
      confirmLabel: '저장',
      onConfirm: async () => {
        closeConfirm()
        setSaving(true)
        try {
          // crawl_config 저장
          const res = await fetch(`/api/sites/${site.id}/config`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ crawl_config: config }),
          })
          if (!res.ok) { alert('저장 실패: 서버 오류가 발생했습니다'); return }

          // 검색어 동기화 (기존 삭제 후 재등록)
          const prevKeywords = (site.keywords || []).map(k => k.keyword)
          const nextKeywords = keywordText.split(/[,\n]/).map(s => s.trim()).filter(Boolean)
          for (const kw of prevKeywords.filter(k => !nextKeywords.includes(k))) {
            await fetch(`/api/sites/${site.id}/keywords/${encodeURIComponent(kw)}`, { method: 'DELETE' })
          }
          for (const kw of nextKeywords.filter(k => !prevKeywords.includes(k))) {
            await fetch(`/api/sites/${site.id}/keywords`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ keyword: kw }),
            })
          }
          onSaved()
        } catch (e) {
          alert('저장 실패: ' + (e.message || '네트워크 오류'))
        } finally {
          setSaving(false)
        }
      },
    })
  }

  const fields = config.collect_fields || []

  return (
    <>
      {/* 상품 상세 URL */}
      <div className="product-config-section active" style={{marginBottom:14}}>
        <h4 className="config-section-title">상품 상세 URL</h4>
        <div style={{display:'flex', gap:8, marginTop:8}}>
          <input
            className="form-control"
            style={{flex:1}}
            placeholder="예) https://www.brand.com/products/{keyword}.html"
            value={config.search_url_template || ''}
            onChange={e => { setConfig({ ...config, search_url_template: e.target.value }); setUrlCheckResult(null) }}
          />
          <button
            className="btn btn-secondary btn-sm"
            style={{whiteSpace:'nowrap'}}
            onClick={handleCheckUrl}
            disabled={checkingUrl || !config.search_url_template}
          >
            {checkingUrl ? '확인 중...' : '연결 확인'}
          </button>
        </div>
        {urlCheckResult && (
          <div style={{marginTop:6, fontSize:12, color: urlCheckResult.ok ? 'var(--success, #16a34a)' : 'var(--danger, #dc2626)'}}>
            {urlCheckResult.ok ? '✓' : '✗'} {urlCheckResult.message}
            {urlCheckResult.url && <span style={{marginLeft:6, color:'#94a3b8'}}>{urlCheckResult.url}</span>}
          </div>
        )}
      </div>

      {/* 상품 검색 */}
      <div className="product-config-section active" style={{marginBottom:14}}>
        <h4 className="config-section-title">상품 검색</h4>
        <textarea
          className="form-control"
          style={{marginTop:8, resize:'vertical'}}
          rows={4}
          placeholder={'상품코드 입력 (엔터로 여러 개 입력)'}
          value={keywordText}
          onChange={e => setKeywordText(e.target.value)}
        />
      </div>

      {/* 상품 수집 항목 */}
      <div className="product-config-section active">
        <h4 className="config-section-title">상품 수집 항목</h4>
        <div className="field-checkbox-grid">
          {brandFields.map(f => (
            <label key={f.key} className={`field-checkbox ${fields.includes(f.key) ? 'checked' : ''}`}>
              <input type="checkbox" checked={fields.includes(f.key)} onChange={() => toggleField(f.key)} />
              <span>{f.label}</span>
            </label>
          ))}
        </div>
      </div>

      <div style={{display:'flex',justifyContent:'flex-end',gap:8,marginTop:20}}>
        <button className="btn btn-primary" onClick={handleSaveConfig} disabled={saving}>
          {saving ? '저장 중...' : '저장'}
        </button>
      </div>
    </>
  )
}


/* ─── 체크 상태 → crawl_config 변환 ─── */
function buildCrawlConfig(agentType, checked) {
  if (agentType === 'product') {
    const collect_fields = Object.entries(checked.fields).filter(([,v]) => v).map(([k]) => k)
    return {
      collect_fields,
      list_type: checked.listType || 'catalog',
      pagination: checked.pagination || 'scroll',
      max_pages: 5, max_items: 100,
      detail_page: checked.options?.detail_page ?? false,
    }
  }
  if (agentType === 'banner') {
    const banner_areas = Object.entries(checked.fields).filter(([,v]) => v).map(([k]) => k)
    return {
      banner_areas,
      capture_screenshot: checked.options?.capture_screenshot ?? true,
      download_images: checked.options?.download_images ?? false,
      include_text: checked.options?.include_text ?? true,
      max_slides: 10,
    }
  }
  if (agentType === 'directory') {
    const collect_fields = Object.entries(checked.fields).filter(([,v]) => v).map(([k]) => k)
    return {
      collect_fields,
      list_type: checked.listType || 'brand_directory',
      collect_details: checked.options?.collect_details ?? false,
      index_navigation: checked.options?.index_navigation ?? false,
      max_items: 0,
    }
  }
  if (agentType === 'local') {
    const collect_fields = Object.entries(checked.fields).filter(([,v]) => v).map(([k]) => k)
    return { collect_fields }
  }
  return {}
}


function AddSiteModal({ categories, onClose, onSaved, showConfirm, closeConfirm, agentFieldDefs }) {
  const orderFieldDefs = (agentFieldDefs['order'] || []).filter(f => f.config_key === 'collect_fields')
  const allFieldKeys = orderFieldDefs.map(f => f.key)
  const collectFieldDefs = orderFieldDefs
  const agentTypeFromCategory = (cat) => {
    const c = (cat || '').trim()
    if (c === '뉴스') return 'news'
    if (c === '카페') return 'cafe'
    if (c === '경쟁사이벤트') return 'promotion'
    if (c === '경쟁사배너') return 'banner'
    if (c === '브랜드목록') return 'directory'
    if (c === '주문서') return 'order'
    if (c === '쿠폰') return 'coupon'
    return 'product'
  }

  const AGENT_TYPE_LABELS = {
    product: '상품 수집', news: '뉴스 기사', cafe: '카페 게시글',
    promotion: '이벤트 수집', banner: '배너 수집', directory: '목록 수집',
    order: '주문서 수집', coupon: '쿠폰 다운로드',
  }

  const initCat = categories[0] || ''
  const initAgent = agentTypeFromCategory(initCat)
  const initConfig = CATEGORY_DEFAULT_CONFIGS[initCat] || {}
  const initChecked = buildCheckedState(initAgent, initConfig)

  const [form, setForm] = useState({
    site_name: '', site_url: '', agent_type: initAgent, category: initCat,
  })
  const [customCat, setCustomCat] = useState('')
  const [checked, setChecked] = useState(initChecked)
  const [saving, setSaving] = useState(false)

  /* ── URL 자동 분석 상태 ── */
  const [analyzing, setAnalyzing] = useState(false)
  const [analyzeResult, setAnalyzeResult] = useState(null)
  const [discoveredFields, setDiscoveredFields] = useState([])
  const [discoveredChecked, setDiscoveredChecked] = useState({})

  /* ── 주문서(order) 전용 상태 ── */
  const [orderConfig, setOrderConfig] = useState({
    login_url: '',
    product_detail_url_template: '',
    order_url: '',
    product_codes: [],
    collect_payment: true,
    collect_fields: [...allFieldKeys],
    order_coupon_selector: '',
    lps_login_url: '',
    event_coupons: [],
    event_list_url: '',
    coupon_keywords: [],
    detail_coupon_selector: '',
    login_config: { id_selector: '', pwd_selector: '', submit_selector: '', success_indicator: '' },
  })
  const [orderCodesText, setOrderCodesText] = useState('')
  const [orderKeywordsText, setOrderKeywordsText] = useState('')
  const [newEventUrl, setNewEventUrl] = useState('')
  const [newEventSelector, setNewEventSelector] = useState('')

  const addEventCoupon = () => {
    const url = newEventUrl.trim()
    const sel = newEventSelector.trim()
    if (!url || !sel) return
    if (orderConfig.event_coupons.length >= MAX_EVENT_COUPONS) return
    setOrderConfig(c => ({
      ...c,
      event_coupons: [...c.event_coupons, { url, selector: sel }],
    }))
    setNewEventUrl('')
    setNewEventSelector('')
  }

  const removeEventCoupon = (idx) => {
    setOrderConfig(c => ({
      ...c,
      event_coupons: c.event_coupons.filter((_, i) => i !== idx),
    }))
  }

  const orderParsedCodes = useMemo(() => {
    const seen = new Set()
    const out = []
    for (const line of orderCodesText.split(/\r?\n/)) {
      const t = line.trim()
      if (!t || seen.has(t)) continue
      seen.add(t)
      out.push(t)
      if (out.length >= MAX_PRODUCT_CODES) break
    }
    return out
  }, [orderCodesText])

  const orderParsedKeywords = useMemo(() => {
    const seen = new Set()
    const out = []
    for (const line of orderKeywordsText.split(/\r?\n/)) {
      const t = line.trim()
      if (!t || seen.has(t)) continue
      seen.add(t)
      out.push(t)
    }
    return out
  }, [orderKeywordsText])

  const orderRawLineCount = useMemo(
    () => orderCodesText.split(/\r?\n/).filter(l => l.trim()).length,
    [orderCodesText],
  )
  const orderOverLimit = orderRawLineCount > MAX_PRODUCT_CODES
  const orderDupCount = orderRawLineCount - orderParsedCodes.length - Math.max(0, orderRawLineCount - MAX_PRODUCT_CODES)

  const handleCategoryChange = (cat) => {
    const agentType = agentTypeFromCategory(cat)
    const catConfig = CATEGORY_DEFAULT_CONFIGS[cat] || {}
    const newChecked = buildCheckedState(agentType, catConfig)
    setForm({ ...form, category: cat, agent_type: agentType })
    setChecked(newChecked)
  }

  const handleCustomCatChange = (val) => {
    setCustomCat(val)
    const agentType = agentTypeFromCategory(val)
    const catConfig = CATEGORY_DEFAULT_CONFIGS[val] || {}
    const newChecked = buildCheckedState(agentType, catConfig)
    setForm({ ...form, category: val, agent_type: agentType })
    setChecked(newChecked)
  }

  const toggleField = (key) => {
    setChecked(prev => ({
      ...prev,
      fields: { ...prev.fields, [key]: !prev.fields[key] },
    }))
  }

  const toggleOption = (key) => {
    setChecked(prev => ({
      ...prev,
      options: { ...prev.options, [key]: !prev.options[key] },
    }))
  }

  const toggleDiscovered = (stdKey) => {
    setDiscoveredChecked(prev => ({ ...prev, [stdKey]: !prev[stdKey] }))
  }

  /* ── URL 분석 실행 ── */
  const handleAnalyzeUrl = async () => {
    const url = form.site_url.trim()
    if (!url) return
    setAnalyzing(true)
    setAnalyzeResult(null)
    setDiscoveredFields([])
    setDiscoveredChecked({})
    try {
      const res = await fetch('/api/sites/analyze-url', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      })
      const data = await res.json()
      setAnalyzeResult(data)

      if (data.status === 'success') {
        /* 기존 spec 필드 키 목록 (이미 표시 중인 필드는 제외) */
        const spec = COLLECT_ITEMS_BY_AGENT[form.agent_type]
        const existingKeys = new Set(spec ? spec.fields.map(f => f.key) : [])

        /* 발견된 필드 중 기존에 없는 것만 추가 후보로 표시 */
        const discovered = (data.discovered_fields || []).filter(
          f => !existingKeys.has(f.standard_key)
        )
        setDiscoveredFields(discovered)

        /* 기존 필드 중 분석 결과에 매칭되면 자동 체크 */
        if (spec) {
          const foundKeys = new Set((data.discovered_fields || []).map(f => f.standard_key))
          setChecked(prev => {
            const newFields = { ...prev.fields }
            spec.fields.forEach(f => {
              if (foundKeys.has(f.key)) newFields[f.key] = true
            })
            return { ...prev, fields: newFields }
          })
        }

        /* 발견된 추가 필드는 기본 체크 */
        const initDiscChecked = {}
        discovered.forEach(f => { initDiscChecked[f.standard_key] = true })
        setDiscoveredChecked(initDiscChecked)

        /* 배너/디렉토리 감지 시 알림 표시 (analyzeResult에 포함) */
      }
    } catch (e) {
      setAnalyzeResult({ status: 'error', error: '분석 요청 실패' })
    } finally {
      setAnalyzing(false)
    }
  }

  const spec = COLLECT_ITEMS_BY_AGENT[form.agent_type]
  const checkedFieldCount = spec ? Object.values(checked.fields).filter(Boolean).length : 0
  const checkedOptCount = spec ? Object.values(checked.options).filter(Boolean).length : 0
  const discoveredCheckedCount = Object.values(discoveredChecked).filter(Boolean).length

  const handleSave = () => {
    if (!form.site_name || !form.site_url) return
    const agentLabel = AGENT_TYPE_LABELS[form.agent_type] || form.agent_type

    let crawl_config
    if (form.agent_type === 'order') {
      crawl_config = { ...orderConfig, product_codes: orderParsedCodes, coupon_keywords: orderParsedKeywords }
    } else {
      crawl_config = buildCrawlConfig(form.agent_type, checked)
      /* 발견된 추가 필드 중 체크된 것을 extra_fields로 추가 */
      const extraFields = discoveredFields
        .filter(f => discoveredChecked[f.standard_key])
        .map(f => ({ raw_key: f.raw_key, standard_key: f.standard_key, label: f.label }))
      if (extraFields.length > 0) {
        crawl_config.extra_fields = extraFields
      }
    }

    const totalFields = form.agent_type === 'order'
      ? orderParsedCodes.length
      : checkedFieldCount + discoveredCheckedCount
    const detailText = form.agent_type === 'order'
      ? `카테고리: ${form.category || '미분류'} | 수집 유형: ${agentLabel} | 상품코드: ${orderParsedCodes.length}건`
      : `카테고리: ${form.category || '미분류'} | 수집 유형: ${agentLabel} | 수집 항목: ${totalFields}개`
    showConfirm({
      title: '사이트 추가',
      message: `"${form.site_name}" 사이트를 추가하시겠습니까?`,
      detail: detailText,
      confirmLabel: '추가',
      onConfirm: async () => {
        closeConfirm()
        setSaving(true)
        try {
          const res = await fetch('/api/sites', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ...form, crawl_config }),
          })
          if (!res.ok) { alert('사이트 추가 실패: 서버 오류가 발생했습니다'); return }
          onSaved()
          onClose()
        } catch (e) {
          alert('사이트 추가 실패: ' + (e.message || '네트워크 오류'))
        } finally {
          setSaving(false)
        }
      },
    })
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{maxWidth: form.agent_type === 'order' ? 680 : spec ? 640 : 520}} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>새 사이트 추가</h3>
          <button className="modal-close" onClick={onClose}>x</button>
        </div>
        <div className="modal-body">
          {/* ── 기본 정보 ── */}
          <div className="form-group">
            <label>카테고리</label>
            <select
              className="form-control"
              value={categories.includes(form.category) ? form.category : ''}
              onChange={e => {
                if (e.target.value === '') {
                  setForm({ ...form, category: '', agent_type: 'product' })
                  setCustomCat('')
                  setChecked(buildCheckedState('product', {}))
                } else {
                  handleCategoryChange(e.target.value)
                }
              }}
            >
              {categories.map(c => <option key={c} value={c}>{c}</option>)}
              <option value="">직접 입력</option>
            </select>
          </div>
          {!categories.includes(form.category) && (
            <div className="form-group">
              <label>새 카테고리명</label>
              <input
                className="form-control"
                placeholder="새 카테고리 이름 (예: 뉴스, 카페, 트렌드매장)"
                value={customCat}
                onChange={e => handleCustomCatChange(e.target.value)}
              />
            </div>
          )}
          <div className="form-group">
            <label>사이트명</label>
            <input
              className="form-control"
              value={form.site_name}
              onChange={e => setForm({ ...form, site_name: e.target.value })}
              placeholder="예: 롯데면세점"
            />
          </div>
          <div className="form-group">
            <label>URL</label>
            <div className="url-analyze-row">
              <input
                className="form-control"
                style={{flex:1}}
                value={form.site_url}
                onChange={e => setForm({ ...form, site_url: e.target.value })}
                placeholder="https://example.com"
                onKeyDown={e => { if (e.key === 'Enter' && form.site_url.trim()) handleAnalyzeUrl() }}
              />
              <button
                className="btn btn-outline btn-sm url-analyze-btn"
                onClick={handleAnalyzeUrl}
                disabled={analyzing || !form.site_url.trim()}
                title="URL을 방문하여 수집 가능한 데이터를 분석합니다"
              >
                {analyzing ? (
                  <><span className="url-analyze-spinner" /> 분석중...</>
                ) : (
                  <><span style={{fontSize:14}}>{'🔍'}</span> URL 분석</>
                )}
              </button>
            </div>
          </div>

          {/* ── URL 분석 진행 표시 ── */}
          {analyzing && (
            <div className="url-analyze-progress">
              <div className="url-analyze-progress-bar">
                <div className="url-analyze-progress-fill" />
              </div>
              <p>페이지를 방문하여 수집 가능한 데이터를 분석하고 있습니다...</p>
              <p style={{fontSize:11,color:'var(--text-secondary)'}}>최대 30초 소요될 수 있습니다</p>
            </div>
          )}

          {/* ── URL 분석 결과 요약 ── */}
          {analyzeResult && !analyzing && (
            <div className={`url-analyze-result ${analyzeResult.status === 'success' ? 'success' : 'error'}`}>
              {analyzeResult.status === 'success' ? (
                <>
                  <div className="url-analyze-result-header">
                    <span>{'✅'} 분석 완료</span>
                    <span className="url-analyze-elapsed">{analyzeResult.elapsed}초</span>
                  </div>
                  {analyzeResult.page_title && (
                    <div className="url-analyze-page-title">{analyzeResult.page_title}</div>
                  )}
                  <div className="url-analyze-summary">
                    {analyzeResult.products && (
                      <span className="url-analyze-tag products">
                        {'📦'} 상품 {analyzeResult.products.count}개
                        <span className="url-analyze-tag-method">{analyzeResult.products.method}</span>
                      </span>
                    )}
                    {analyzeResult.banners && (
                      <span className="url-analyze-tag banners">
                        {'🖼️'} 배너 {analyzeResult.banners.count}개
                      </span>
                    )}
                    {analyzeResult.directory && (
                      <span className="url-analyze-tag directory">
                        {'📋'} 목록 {analyzeResult.directory.count}개
                      </span>
                    )}
                    {!analyzeResult.products && !analyzeResult.banners && !analyzeResult.directory && (
                      <span style={{fontSize:12,color:'var(--text-secondary)'}}>탐지된 데이터가 없습니다</span>
                    )}
                  </div>
                </>
              ) : analyzeResult.status === 'blocked' ? (
                <div className="url-analyze-result-header">
                  <span>{'🚫'} 접근 차단됨 ({analyzeResult.error || 'HTTP 403/429'})</span>
                </div>
              ) : (
                <div className="url-analyze-result-header">
                  <span>{'❌'} 분석 실패: {analyzeResult.error || '알 수 없는 오류'}</span>
                </div>
              )}
            </div>
          )}

          {/* ── 수집 유형 배지 ── */}
          <div className="form-group">
            <label>수집 유형</label>
            <div className="agent-type-badge-row">
              <span className={`badge ${AGENT_BADGE_CLASS[form.agent_type] || 'dp'}`}
                style={{fontSize:13,padding:'6px 14px'}}>
                {AGENT_TYPE_LABELS[form.agent_type]}
              </span>
              <span style={{fontSize:11,color:'var(--text-secondary)'}}>
                카테고리에 따라 자동 설정됩니다
              </span>
            </div>
          </div>

          {/* ── 주문서(order) 전용 설정 ── */}
          {form.agent_type === 'order' && (
            <div style={{marginTop:12}}>
              {/* ── 워크플로우 시각화 ── */}
              <div className="product-config-section active" style={{marginTop:0}}>
                <div className="config-section-title">수집 워크플로우</div>

                <div className="order-flow-login-bar">
                  <span className="order-flow-login-icon">🔑</span>
                  <span>로그인 (메인 + LPS 도메인, 1회)</span>
                </div>

                {(() => {
                  const hasEventCoupons = orderConfig.event_coupons.length > 0
                  const hasAutoDiscovery = !!(orderConfig.event_list_url.trim() && orderParsedKeywords.length > 0)
                  const hasDetailCoupon = !!orderConfig.detail_coupon_selector.trim()
                  const hasCouponPhase = hasEventCoupons || hasDetailCoupon || hasAutoDiscovery
                  const hasOrderCoupon = !!orderConfig.order_coupon_selector.trim()
                  const productCount = orderParsedCodes.length

                  const couponSteps = [
                    ...(hasEventCoupons ? [{
                      label: '이벤트 쿠폰', icon: '🎁',
                      desc: `이벤트 페이지 ${orderConfig.event_coupons.length}건 → 쿠폰 다운로드`,
                      repeat: orderConfig.event_coupons.length > 1,
                    }] : []),
                    ...(hasAutoDiscovery ? [{
                      label: '자동 탐색 쿠폰', icon: '🔍',
                      desc: `이벤트 목록 자동 순회 → 키워드 ${orderParsedKeywords.length}개로 쿠폰 탐색`,
                      repeat: true,
                    }] : []),
                    ...(hasDetailCoupon ? [{
                      label: '상품상세 쿠폰', icon: '🎫',
                      desc: `상품 ${productCount}건 상세페이지 → 쿠폰 다운로드`,
                      repeat: productCount > 1,
                    }] : []),
                  ]

                  const orderSteps = [
                    { label: '상품상세', desc: '등록한 상품상세 URL로 순회', icon: '📦' },
                    { label: '바로구매', desc: `등록 ${productCount.toLocaleString()}건 × 바로구매 클릭`, repeat: productCount > 1, icon: '🛒' },
                    ...(hasOrderCoupon ? [{ label: '주문서 쿠폰', desc: '주문서 내 쿠폰 다운로드', icon: '🏷️' }] : []),
                    { label: '출입국 확인', desc: '출입국정보 등록 확인 → 미등록 시 스킵', icon: '✈️' },
                    { label: '결제정보 수집', desc: '상품명·결제금액(USD/KRW)·할인율 추출', repeat: productCount > 1, icon: '💳' },
                    { label: '로그아웃', desc: '메인 홈 이동 → logout() 호출', terminal: true, icon: '🚪' },
                  ]

                  const renderSteps = (steps) => (
                    <div className="order-workflow">
                      {steps.map((s, i) => (
                        <div key={i} className="order-workflow-step">
                          <div className={`order-workflow-node${s.terminal ? ' terminal' : ''}`}>
                            <span className="order-workflow-num">{s.icon || (i + 1)}</span>
                            <div className="order-workflow-label">
                              {s.label}
                              {s.repeat && <span className="order-workflow-loop">↻ 반복</span>}
                            </div>
                            <div className="order-workflow-desc">{s.desc}</div>
                          </div>
                          {i < steps.length - 1 && <div className="order-workflow-arrow">→</div>}
                        </div>
                      ))}
                    </div>
                  )

                  return (
                    <>
                      <div className={`order-flow-phase coupon-phase${hasCouponPhase ? '' : ' empty'}`}>
                        <div className="order-flow-phase-header">
                          <span className="badge coupon-badge" style={{fontSize:11}}>쿠폰 다운로드</span>
                          <span style={{fontSize:11,color:'var(--text-secondary)'}}>
                            {hasCouponPhase
                              ? '이벤트 페이지 + 상품상세 쿠폰 다운로드'
                              : '아래에서 쿠폰 설정을 등록하면 표시됩니다'}
                          </span>
                        </div>
                        {hasCouponPhase && renderSteps(couponSteps)}
                      </div>

                      <div className="order-flow-connector">
                        <div className="order-flow-connector-line" />
                        <span className="order-flow-connector-label">같은 세션</span>
                        <div className="order-flow-connector-line" />
                      </div>

                      <div className="order-flow-phase order-phase">
                        <div className="order-flow-phase-header">
                          <span className="badge order-badge" style={{fontSize:11}}>주문서 수집</span>
                          <span style={{fontSize:11,color:'var(--text-secondary)'}}>바로구매 → 결제정보 수집</span>
                        </div>
                        {renderSteps(orderSteps)}
                      </div>
                    </>
                  )
                })()}
              </div>

              {/* ── 이벤트 페이지 쿠폰 ── */}
              <div className="product-config-section active" style={{marginTop:12}}>
                <div className="config-section-title" style={{display:'flex',alignItems:'center',gap:8}}>
                  🎁 이벤트 페이지 쿠폰
                  <span style={{fontSize:11,color:'var(--text-secondary)',fontWeight:400}}>
                    ({orderConfig.event_coupons.length}건 등록)
                  </span>
                </div>
                <p className="config-section-desc">
                  쿠폰 다운로드가 필요한 이벤트 페이지 URL과 쿠폰 버튼의 텍스트 또는 CSS 셀렉터를 등록합니다.
                  (#, . 시작 = CSS 셀렉터, 그 외 = 텍스트 매칭). 비워두면 이벤트 쿠폰 단계를 건너뜁니다.
                </p>

                {orderConfig.event_coupons.length > 0 && (
                  <div style={{marginTop:8,display:'flex',flexDirection:'column',gap:6}}>
                    {orderConfig.event_coupons.map((ec, i) => (
                      <div key={i} style={{
                        display:'flex', alignItems:'center', gap:8,
                        padding:'6px 10px', background:'var(--bg-secondary)',
                        borderRadius:6, border:'1px solid var(--border)', fontSize:12,
                      }}>
                        <div style={{flex:1,overflow:'hidden'}}>
                          <div style={{fontWeight:500,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
                            {ec.url}
                          </div>
                          <div style={{color:'var(--text-secondary)',fontSize:11,marginTop:2}}>
                            버튼: <code style={{background:'rgba(0,0,0,0.06)',padding:'1px 4px',borderRadius:3}}>{ec.selector}</code>
                          </div>
                        </div>
                        <button
                          className="btn btn-outline btn-sm"
                          style={{fontSize:11,padding:'2px 8px',flexShrink:0,color:'var(--danger, #d33)'}}
                          onClick={() => removeEventCoupon(i)}
                        >
                          삭제
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                <div style={{display:'flex',gap:6,marginTop:8,alignItems:'flex-end'}}>
                  <div style={{flex:2}}>
                    <label style={{fontSize:11,color:'var(--text-secondary)'}}>이벤트 페이지 URL</label>
                    <input
                      className="form-control"
                      placeholder="https://kor.lottedfs.com/kr/event/..."
                      value={newEventUrl}
                      onChange={e => setNewEventUrl(e.target.value)}
                      style={{fontSize:12,marginTop:2}}
                    />
                  </div>
                  <div style={{flex:1}}>
                    <label style={{fontSize:11,color:'var(--text-secondary)'}}>쿠폰 버튼</label>
                    <input
                      className="form-control"
                      placeholder="쿠폰 받기"
                      value={newEventSelector}
                      onChange={e => setNewEventSelector(e.target.value)}
                      style={{fontSize:12,marginTop:2}}
                    />
                  </div>
                  <button
                    className="btn btn-outline btn-sm"
                    style={{fontSize:11,padding:'6px 12px',flexShrink:0}}
                    disabled={!newEventUrl.trim() || !newEventSelector.trim() || orderConfig.event_coupons.length >= MAX_EVENT_COUPONS}
                    onClick={addEventCoupon}
                  >
                    + 추가
                  </button>
                </div>
              </div>

              {/* ── 이벤트 자동 탐색 ── */}
              <div className="product-config-section active" style={{marginTop:12}}>
                <div className="config-section-title" style={{display:'flex',alignItems:'center',gap:8}}>
                  🔍 이벤트 자동 탐색
                  {orderConfig.event_list_url.trim() && orderParsedKeywords.length > 0 && (
                    <span style={{fontSize:11,color:'var(--success, #16a34a)',fontWeight:400}}>
                      활성 (키워드 {orderParsedKeywords.length}개)
                    </span>
                  )}
                </div>
                <p className="config-section-desc">
                  이벤트 목록 페이지를 자동 순회하여 쿠폰 버튼을 탐색합니다.
                </p>
                <div style={{display:'flex',flexDirection:'column',gap:8,marginTop:8}}>
                  <label style={{fontSize:12}}>
                    <span style={{color:'var(--text-secondary)'}}>이벤트 목록 진입 URL</span>
                    <input
                      className="form-control"
                      placeholder="https://kor.lottedfs.com/kr/event/eventDetail?evtDispNo=1044712"
                      value={orderConfig.event_list_url}
                      onChange={e => setOrderConfig(c => ({...c, event_list_url: e.target.value}))}
                      style={{marginTop:4,fontSize:12}}
                    />
                  </label>
                  <div style={{fontSize:12}}>
                    <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',gap:8}}>
                      <div>
                        <span style={{color:'var(--text-secondary)'}}>쿠폰 버튼 키워드</span>
                        <span style={{fontSize:11,color:'var(--text-secondary)',marginLeft:4}}>
                          (엔터로 구분)
                        </span>
                      </div>
                      <span style={{fontSize:11,color:'var(--text-secondary)'}}>
                        등록 {orderParsedKeywords.length}건
                      </span>
                    </div>
                    <textarea
                      className="form-control"
                      placeholder={'쿠폰 다운로드\n혜택받기\n쿠폰받기\n다운받기'}
                      value={orderKeywordsText}
                      onChange={e => setOrderKeywordsText(e.target.value)}
                      rows={4}
                      spellCheck={false}
                      style={{
                        marginTop:4,fontSize:12,fontFamily:'monospace',
                        resize:'vertical',minHeight:60,
                      }}
                    />
                  </div>
                </div>
              </div>

              {/* ── 상품상세 쿠폰 ── */}
              <div className="product-config-section active" style={{marginTop:12}}>
                <div className="config-section-title">🎫 상품상세 쿠폰</div>
                <p className="config-section-desc">
                  상품 상세페이지에서 쿠폰을 다운로드할 버튼의 텍스트나 CSS 셀렉터를 입력합니다.
                  비워두면 상품상세 쿠폰 다운로드를 건너뜁니다.
                </p>
                <input
                  className="form-control"
                  placeholder="오늘의 혜택받기 또는 .benefit-btn"
                  value={orderConfig.detail_coupon_selector}
                  onChange={e => setOrderConfig(c => ({...c, detail_coupon_selector: e.target.value}))}
                  style={{marginTop:4,fontSize:12}}
                />
              </div>

              {/* ── 페이지 URL ── */}
              <div className="product-config-section active" style={{marginTop:12}}>
                <div className="config-section-title">페이지 URL</div>
                <div style={{display:'flex',flexDirection:'column',gap:8,marginTop:8}}>
                  <label style={{fontSize:12}}>
                    <span style={{color:'var(--text-secondary)'}}>로그인 URL</span>
                    <span style={{fontSize:11,color:'var(--text-secondary)',marginLeft:4}}>(비워두면 사이트 URL 사용)</span>
                    <input
                      className="form-control"
                      placeholder="https://kor.lottedfs.com/kr/login"
                      value={orderConfig.login_url}
                      onChange={e => setOrderConfig(c => ({...c, login_url: e.target.value}))}
                      style={{marginTop:4,fontSize:12}}
                    />
                  </label>
                  <label style={{fontSize:12}}>
                    <span style={{color:'var(--text-secondary)'}}>상품상세 URL</span>
                    <span style={{fontSize:11,color:'var(--text-secondary)',marginLeft:4}}>{'(상품코드 위치에 {prdNo} 사용)'}</span>
                    <input
                      className="form-control"
                      placeholder="https://kor.lottedfs.com/kr/product/productDetail?prdNo={prdNo}&adltPrdYn=Y&onOff=on"
                      value={orderConfig.product_detail_url_template}
                      onChange={e => setOrderConfig(c => ({...c, product_detail_url_template: e.target.value}))}
                      style={{marginTop:4,fontSize:12}}
                    />
                  </label>
                  <div style={{fontSize:12}}>
                    <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',gap:8}}>
                      <div>
                        <span style={{color:'var(--text-secondary)'}}>상품코드</span>
                        <span style={{fontSize:11,color:'var(--text-secondary)',marginLeft:4}}>
                          (엔터로 구분, 최대 {MAX_PRODUCT_CODES.toLocaleString()}건)
                        </span>
                      </div>
                      <span style={{
                        fontSize:11,
                        color: orderOverLimit ? 'var(--danger, #d33)' : 'var(--text-secondary)',
                        fontWeight: orderOverLimit ? 600 : 400,
                      }}>
                        등록 {orderParsedCodes.length.toLocaleString()}건
                        {orderDupCount > 0 && ` (중복 ${orderDupCount}건 제외)`}
                        {orderOverLimit && ` · 최대 ${MAX_PRODUCT_CODES.toLocaleString()}건 초과`}
                      </span>
                    </div>
                    <textarea
                      className="form-control"
                      placeholder={'20000996458\n20000996459\n...'}
                      value={orderCodesText}
                      onChange={e => setOrderCodesText(e.target.value)}
                      rows={8}
                      spellCheck={false}
                      style={{
                        marginTop:4,fontSize:12,fontFamily:'monospace',
                        resize:'vertical',minHeight:120,
                      }}
                    />
                  </div>
                  <label style={{fontSize:12}}>
                    <span style={{color:'var(--text-secondary)'}}>주문서 URL</span>
                    <span style={{fontSize:11,color:'var(--text-secondary)',marginLeft:4}}>(구매 클릭 후 도달 URL 패턴)</span>
                    <input
                      className="form-control"
                      placeholder="https://kor.lps.lottedfs.com/kr/newOrder"
                      value={orderConfig.order_url}
                      onChange={e => setOrderConfig(c => ({...c, order_url: e.target.value}))}
                      style={{marginTop:4,fontSize:12}}
                    />
                  </label>
                  <label style={{fontSize:12}}>
                    <span style={{color:'var(--text-secondary)'}}>LPS 로그인 URL</span>
                    <span style={{fontSize:11,color:'var(--text-secondary)',marginLeft:4}}>(서브도메인 로그인, 비워두면 자동감지)</span>
                    <input
                      className="form-control"
                      placeholder="https://kor.lps.lottedfs.com/kr/member/login"
                      value={orderConfig.lps_login_url}
                      onChange={e => setOrderConfig(c => ({...c, lps_login_url: e.target.value}))}
                      style={{marginTop:4,fontSize:12}}
                    />
                  </label>
                </div>
              </div>

              {/* ── 주문서 쿠폰 다운로드 ── */}
              <div className="product-config-section active" style={{marginTop:12}}>
                <div className="config-section-title">🏷️ 주문서 쿠폰 다운로드</div>
                <p className="config-section-desc">
                  주문서 페이지에서 쿠폰을 다운로드할 버튼의 텍스트나 CSS 셀렉터를 입력합니다.
                  비워두면 쿠폰 다운로드를 건너뜁니다. (#, . 으로 시작하면 CSS 셀렉터, 그 외에는 텍스트 매칭)
                </p>
                <input
                  className="form-control"
                  placeholder="쿠폰 다운로드 또는 .coupon-download-btn"
                  value={orderConfig.order_coupon_selector}
                  onChange={e => setOrderConfig(c => ({...c, order_coupon_selector: e.target.value}))}
                  style={{marginTop:4,fontSize:12}}
                />
              </div>

              {/* ── 수집 항목 ── */}
              <div className="product-config-section active" style={{marginTop:12}}>
                <div className="config-section-title" style={{display:'flex',alignItems:'center',justifyContent:'space-between'}}>
                  <span>수집 항목 ({orderConfig.collect_fields.length}/{collectFieldDefs.length})</span>
                  <div style={{display:'flex',gap:6}}>
                    <button type="button" className="btn btn-sm"
                      style={{fontSize:11,padding:'2px 8px'}}
                      onClick={() => setOrderConfig(c => ({...c, collect_fields: [...allFieldKeys]}))}
                    >전체선택</button>
                    <button type="button" className="btn btn-sm"
                      style={{fontSize:11,padding:'2px 8px'}}
                      onClick={() => setOrderConfig(c => ({...c, collect_fields: []}))}
                    >전체해제</button>
                  </div>
                </div>
                <div className="field-checkbox-grid" style={{marginTop:8}}>
                  {collectFieldDefs.map(f => {
                    const isChecked = orderConfig.collect_fields.includes(f.key)
                    return (
                      <label key={f.key}
                        className={`field-checkbox ${isChecked ? 'checked' : ''}`}
                        title={f.group}
                      >
                        <input type="checkbox" checked={isChecked}
                          onChange={() => setOrderConfig(c => ({
                            ...c,
                            collect_fields: isChecked
                              ? c.collect_fields.filter(k => k !== f.key)
                              : [...c.collect_fields, f.key],
                          }))}
                        />
                        <span>{f.label}</span>
                      </label>
                    )
                  })}
                </div>
              </div>

              {/* ── 로그인 폼 셀렉터 ── */}
              <div className="product-config-section active" style={{marginTop:12}}>
                <div className="config-section-title">로그인 폼 셀렉터 (선택)</div>
                <p className="config-section-desc">비워두면 자동 탐지합니다. 로그인 실패 시 수동 지정하세요.</p>
                <div className="order-selector-grid">
                  <label>
                    <span>ID 입력 셀렉터</span>
                    <input className="form-control" placeholder="#userId"
                      value={orderConfig.login_config.id_selector || ''}
                      onChange={e => setOrderConfig(c => ({...c, login_config: {...c.login_config, id_selector: e.target.value}}))}
                    />
                  </label>
                  <label>
                    <span>비밀번호 셀렉터</span>
                    <input className="form-control" placeholder="#password"
                      value={orderConfig.login_config.pwd_selector || ''}
                      onChange={e => setOrderConfig(c => ({...c, login_config: {...c.login_config, pwd_selector: e.target.value}}))}
                    />
                  </label>
                  <label>
                    <span>로그인 버튼 셀렉터</span>
                    <input className="form-control" placeholder="#loginBtn"
                      value={orderConfig.login_config.submit_selector || ''}
                      onChange={e => setOrderConfig(c => ({...c, login_config: {...c.login_config, submit_selector: e.target.value}}))}
                    />
                  </label>
                  <label>
                    <span>로그인 성공 지표</span>
                    <input className="form-control" placeholder=".my-page, .logout"
                      value={orderConfig.login_config.success_indicator || ''}
                      onChange={e => setOrderConfig(c => ({...c, login_config: {...c.login_config, success_indicator: e.target.value}}))}
                    />
                  </label>
                </div>
              </div>
            </div>
          )}

          {/* ── 수집 항목 선택 (에이전트별 동적 표시) ── */}
          {spec && form.agent_type !== 'order' && (
            <div className="add-site-collect-section" style={{background: spec.color, borderRadius:8, padding:16, marginTop:8}}>
              <div style={{fontWeight:600,fontSize:14,color:spec.textColor,marginBottom:4}}>{spec.label}</div>
              <div style={{fontSize:12,color:spec.textColor,opacity:0.8,marginBottom:12}}>{spec.desc}</div>

              {/* 수집 필드 체크박스 */}
              <div className="field-checkbox-grid" style={{marginBottom: spec.options?.length || discoveredFields.length ? 12 : 0}}>
                {spec.fields.map(f => (
                  <label key={f.key}
                    className={`field-checkbox ${checked.fields[f.key] ? 'checked' : ''}`}
                  >
                    <input
                      type="checkbox"
                      checked={!!checked.fields[f.key]}
                      onChange={() => toggleField(f.key)}
                    />
                    <span>{f.label}</span>
                  </label>
                ))}
              </div>

              {/* ── URL 분석으로 발견된 추가 필드 ── */}
              {discoveredFields.length > 0 && (
                <div style={{marginBottom:12}}>
                  <div style={{fontSize:12,fontWeight:600,color:spec.textColor,marginBottom:6,display:'flex',alignItems:'center',gap:6}}>
                    {'🔍'} URL 분석으로 발견된 추가 필드
                    <span style={{fontSize:10,fontWeight:400,opacity:0.7}}>({discoveredFields.length}개)</span>
                  </div>
                  <div className="field-checkbox-grid">
                    {discoveredFields.map(f => (
                      <label key={f.standard_key}
                        className={`field-checkbox discovered ${discoveredChecked[f.standard_key] ? 'checked' : ''}`}
                        title={f.value_preview ? `미리보기: ${f.value_preview}` : f.raw_key}
                      >
                        <input
                          type="checkbox"
                          checked={!!discoveredChecked[f.standard_key]}
                          onChange={() => toggleDiscovered(f.standard_key)}
                        />
                        <span>{f.label}</span>
                        <span className="field-badge-discovered">발견</span>
                      </label>
                    ))}
                  </div>
                </div>
              )}

              {/* 목록 유형 (product, directory) */}
              {spec.listTypes && (
                <div style={{marginBottom:12}}>
                  <div style={{fontSize:12,fontWeight:600,color:spec.textColor,marginBottom:6}}>목록 유형</div>
                  <div style={{display:'flex',gap:8,flexWrap:'wrap'}}>
                    {spec.listTypes.map(opt => (
                      <label key={opt.value}
                        className={`add-site-chip ${checked.listType === opt.value ? 'selected' : ''}`}
                        onClick={() => setChecked(prev => ({ ...prev, listType: opt.value }))}
                      >
                        <span>{opt.icon || ''} {opt.label}</span>
                      </label>
                    ))}
                  </div>
                </div>
              )}

              {/* 페이지네이션 (product only) */}
              {spec.paginations && (
                <div style={{marginBottom:12}}>
                  <div style={{fontSize:12,fontWeight:600,color:spec.textColor,marginBottom:6}}>페이지네이션</div>
                  <div style={{display:'flex',gap:8,flexWrap:'wrap'}}>
                    {spec.paginations.map(opt => (
                      <label key={opt.value}
                        className={`add-site-chip ${checked.pagination === opt.value ? 'selected' : ''}`}
                        onClick={() => setChecked(prev => ({ ...prev, pagination: opt.value }))}
                      >
                        <span>{opt.label}</span>
                      </label>
                    ))}
                  </div>
                </div>
              )}

              {/* 수집 옵션 토글 */}
              {spec.options && spec.options.length > 0 && (
                <div>
                  <div style={{fontSize:12,fontWeight:600,color:spec.textColor,marginBottom:6}}>수집 옵션</div>
                  {spec.options.map(opt => (
                    <label key={opt.key} className="add-site-option-row">
                      <input
                        type="checkbox"
                        checked={!!checked.options[opt.key]}
                        onChange={() => toggleOption(opt.key)}
                      />
                      <div>
                        <span style={{fontSize:13,fontWeight:500}}>{opt.label}</span>
                        {opt.desc && <span style={{fontSize:11,color:'var(--text-secondary)',marginLeft:6}}>{opt.desc}</span>}
                      </div>
                    </label>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
        <div className="modal-footer">
          <button className="btn btn-outline" onClick={onClose}>취소</button>
          <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
            {saving ? '저장 중...' : '추가'}
          </button>
        </div>
      </div>
    </div>
  )
}
