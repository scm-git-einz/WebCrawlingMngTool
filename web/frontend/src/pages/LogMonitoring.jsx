import { useState, useEffect, useRef, useCallback } from 'react'

const AGENT_LABELS = {
  product: '상품', news: '뉴스', cafe: '카페',
  promotion: '이벤트', banner: '배너', directory: '목록',
  order: '주문서', coupon: '쿠폰',
}

const PHASE_ICONS = {
  init: '\u{1F680}', browser_init: '\u{1F310}', login: '\u{1F511}',
  detection: '\u{1F50D}', scroll: '\u{1F4DC}', pagination: '\u{1F4DC}',
  detail_start: '\u{1F4CB}', detail_progress: '\u{23F3}', detail_done: '\u{2705}',
  item_start: '\u{1F4E6}', item_progress: '\u{1F4E6}', coupon_skip: '\u{1F3F7}',
  save: '\u{1F4BE}', complete: '\u{2705}', browser_close: '\u{1F6D1}',
  system: '\u{2699}', header: '\u{1F4CC}', separator: '',
}

function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function timeAgo(dateStr) {
  if (!dateStr) return ''
  const diff = (Date.now() - new Date(dateStr).getTime()) / 1000
  if (diff < 60) return `${Math.floor(diff)}초 전`
  if (diff < 3600) return `${Math.floor(diff / 60)}분 전`
  if (diff < 86400) return `${Math.floor(diff / 3600)}시간 전`
  return `${Math.floor(diff / 86400)}일 전`
}

/* ── 섹션 뷰어 (실시간/이력 공용) ── */
function LogSectionViewer({ sections, searchText }) {
  const [collapsed, setCollapsed] = useState(() => {
    const init = {}
    sections.forEach(s => { init[s.id] = !s.default_expanded })
    return init
  })

  useEffect(() => {
    const init = {}
    sections.forEach(s => { init[s.id] = !s.default_expanded })
    setCollapsed(init)
  }, [sections])

  const toggle = (id) => setCollapsed(prev => ({ ...prev, [id]: !prev[id] }))

  const expandAll = () => {
    const next = {}
    sections.forEach(s => { next[s.id] = false })
    setCollapsed(next)
  }
  const collapseAll = () => {
    const next = {}
    sections.forEach(s => { next[s.id] = true })
    setCollapsed(next)
  }

  const filteredSections = searchText
    ? sections.filter(s => s.lines.some(l => l.toLowerCase().includes(searchText.toLowerCase())))
    : sections

  return (
    <div className="log-section-viewer">
      <div className="log-section-toolbar">
        <span className="log-section-toolbar-info">
          {filteredSections.length}개 단계 / {filteredSections.reduce((s, x) => s + x.line_count, 0)}줄
        </span>
        <div className="log-section-toolbar-actions">
          <button className="btn-sm" onClick={expandAll}>모두 펼치기</button>
          <button className="btn-sm" onClick={collapseAll}>모두 접기</button>
        </div>
      </div>
      {filteredSections.length === 0 && (
        <div className="log-section-empty">
          {searchText ? `"${searchText}" 검색 결과가 없습니다.` : '로그가 비어 있습니다.'}
        </div>
      )}
      {filteredSections.map(section => (
        <div key={section.id} className="log-section">
          <div
            className="log-section-header"
            onClick={() => toggle(section.id)}
          >
            <span className={`log-section-chevron ${collapsed[section.id] ? '' : 'expanded'}`}>
              {'▶'}
            </span>
            <span className="log-section-icon">
              {PHASE_ICONS[section.phase] || '\u{1F4AC}'}
            </span>
            <span className="log-section-label">{section.label}</span>
            {section.agent_types?.map(at => (
              <span key={at} className={`log-section-badge badge-${at}`}>
                {AGENT_LABELS[at] || at}
              </span>
            ))}
            <span className="log-section-count">{section.line_count}줄</span>
          </div>
          {!collapsed[section.id] && (
            <div className="log-section-body">
              <pre className="log-viewer-pre">
                {section.lines.map((line, li) => {
                  if (searchText && line.toLowerCase().includes(searchText.toLowerCase())) {
                    const idx = line.toLowerCase().indexOf(searchText.toLowerCase())
                    return (
                      <div key={li} className="log-line log-line-highlight">
                        {line.slice(0, idx)}
                        <mark className="log-search-match">{line.slice(idx, idx + searchText.length)}</mark>
                        {line.slice(idx + searchText.length)}
                      </div>
                    )
                  }
                  return <div key={li} className="log-line">{line}</div>
                })}
              </pre>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

/* ── 실시간 탭 ── */
function LiveTab({ filterAgent, searchText }) {
  const [running, setRunning] = useState([])
  const [selectedFile, setSelectedFile] = useState(null)
  const [logData, setLogData] = useState(null)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const viewerRef = useRef(null)

  const loadRunning = useCallback(() => {
    fetch('/api/logs/running')
      .then(r => r.json())
      .then(data => {
        setRunning(data)
        if (data.length > 0 && !selectedFile) {
          setSelectedFile(data[0].log_file)
        }
        if (data.length === 0) {
          setSelectedFile(null)
          setLogData(null)
        }
      })
      .catch(() => {})
  }, [selectedFile])

  const loadLogData = useCallback(() => {
    if (!selectedFile) return
    fetch(`/api/logs/files/${selectedFile}?tail=2000`)
      .then(r => r.json())
      .then(data => {
        setLogData(data)
        if (!data.is_running) setAutoRefresh(false)
      })
      .catch(() => {})
  }, [selectedFile])

  useEffect(() => {
    loadRunning()
  }, [])

  useEffect(() => {
    loadLogData()
  }, [selectedFile])

  useEffect(() => {
    if (!autoRefresh) return
    const id = setInterval(() => {
      loadRunning()
      loadLogData()
    }, 2000)
    return () => clearInterval(id)
  }, [autoRefresh, loadRunning, loadLogData])

  useEffect(() => {
    if (viewerRef.current) {
      viewerRef.current.scrollTop = viewerRef.current.scrollHeight
    }
  }, [logData])

  const filteredRunning = filterAgent
    ? running.filter(r => {
        const firstLine = r.preview_lines?.[0] || ''
        return firstLine.includes(`[${filterAgent}]`)
      })
    : running

  return (
    <div className="log-monitor-live">
      {filteredRunning.length === 0 ? (
        <div className="log-monitor-empty">
          <div className="log-monitor-empty-icon">{'\u{1F4AD}'}</div>
          <div>현재 실행 중인 크롤링이 없습니다.</div>
          <div className="log-monitor-empty-sub">수집 대상 설정에서 크롤링을 실행해 주세요.</div>
        </div>
      ) : (
        <>
          <div className="log-monitor-live-grid">
            {filteredRunning.map(proc => (
              <div
                key={proc.pid}
                className={`log-monitor-live-card ${selectedFile === proc.log_file ? 'selected' : ''}`}
                onClick={() => { setSelectedFile(proc.log_file); setAutoRefresh(true) }}
              >
                <div className="log-monitor-live-card-header">
                  <span className="log-monitor-live-dot" />
                  <span className="log-monitor-live-name">{proc.site_name}</span>
                  <span className="log-monitor-live-time">{timeAgo(proc.started_at?.replace('_', ' ').replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3'))}</span>
                </div>
                <div className="log-monitor-live-preview">
                  {(proc.preview_lines || []).slice(-3).map((l, i) => (
                    <div key={i} className="log-monitor-live-preview-line">{l}</div>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {logData && (
            <div className="log-monitor-viewer-wrap">
              <div className="log-monitor-viewer-header">
                <span>{logData.site_name} — {logData.filename}</span>
                <label className="log-monitor-auto-refresh">
                  <input
                    type="checkbox"
                    checked={autoRefresh}
                    onChange={e => setAutoRefresh(e.target.checked)}
                  />
                  자동 갱신
                </label>
              </div>
              <div className="log-monitor-viewer-body" ref={viewerRef}>
                <LogSectionViewer sections={logData.sections || []} searchText={searchText} />
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

/* ── 이력 탭 ── */
function HistoryTab({ filterAgent, searchText }) {
  const [files, setFiles] = useState([])
  const [selectedFile, setSelectedFile] = useState(null)
  const [logData, setLogData] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const params = new URLSearchParams()
    if (filterAgent) params.set('agent_type', filterAgent)
    params.set('limit', '100')
    fetch(`/api/logs/files?${params}`)
      .then(r => r.json())
      .then(data => setFiles(data))
      .catch(() => {})
  }, [filterAgent])

  useEffect(() => {
    if (!selectedFile) { setLogData(null); return }
    setLoading(true)
    fetch(`/api/logs/files/${selectedFile}?tail=2000`)
      .then(r => r.json())
      .then(data => { setLogData(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [selectedFile])

  return (
    <div className="log-monitor-history">
      <div className="log-monitor-split">
        <div className="log-monitor-filelist">
          <div className="log-monitor-filelist-header">로그 파일 ({files.length})</div>
          <div className="log-monitor-filelist-body">
            {files.length === 0 && (
              <div className="log-monitor-filelist-empty">로그 파일이 없습니다.</div>
            )}
            {files.map(f => (
              <div
                key={f.filename}
                className={`log-monitor-file-item ${selectedFile === f.filename ? 'selected' : ''}`}
                onClick={() => setSelectedFile(f.filename)}
              >
                <div className="log-monitor-file-item-top">
                  <span className={`log-section-badge badge-${f.agent_type}`}>
                    {AGENT_LABELS[f.agent_type] || f.agent_type}
                  </span>
                  <span className="log-monitor-file-item-name">{f.site_name}</span>
                  {f.is_running && <span className="log-monitor-live-dot" />}
                </div>
                <div className="log-monitor-file-item-bottom">
                  <span>{f.started_at}</span>
                  <span>{formatFileSize(f.file_size)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="log-monitor-viewer-panel">
          {!selectedFile && (
            <div className="log-monitor-empty">
              <div className="log-monitor-empty-icon">{'\u{1F4C2}'}</div>
              <div>왼쪽에서 로그 파일을 선택하세요.</div>
            </div>
          )}
          {selectedFile && loading && (
            <div className="log-monitor-empty">
              <div>로딩 중...</div>
            </div>
          )}
          {logData && !loading && (
            <div className="log-monitor-viewer-wrap">
              <div className="log-monitor-viewer-header">
                <span>
                  {logData.site_name} — {logData.started_at}
                  {logData.is_running && <span className="log-monitor-running-badge">실행 중</span>}
                </span>
                <span className="log-monitor-viewer-meta">
                  {logData.total_lines}줄 / {logData.sections?.length || 0}단계
                </span>
              </div>
              <div className="log-monitor-viewer-body">
                <LogSectionViewer sections={logData.sections || []} searchText={searchText} />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/* ── 메인 ── */
export default function LogMonitoring() {
  const [tab, setTab] = useState('live')
  const [filterAgent, setFilterAgent] = useState('')
  const [searchText, setSearchText] = useState('')

  return (
    <div className="page-wrap">
      <h2 className="page-title">{'\u{1F4DD}'} 로그 모니터링</h2>
      <p className="page-subtitle">에이전트별 크롤링 로그를 실시간 모니터링하고 이력을 조회합니다.</p>

      <div className="log-monitor-controls">
        <div className="log-monitor-tabs">
          <button
            className={`log-monitor-tab ${tab === 'live' ? 'active' : ''}`}
            onClick={() => setTab('live')}
          >
            {'\u{1F7E2}'} 실시간
          </button>
          <button
            className={`log-monitor-tab ${tab === 'history' ? 'active' : ''}`}
            onClick={() => setTab('history')}
          >
            {'\u{1F4C1}'} 이력
          </button>
        </div>

        <div className="log-monitor-filters">
          <select
            value={filterAgent}
            onChange={e => setFilterAgent(e.target.value)}
            className="log-monitor-select"
          >
            <option value="">전체 에이전트</option>
            {Object.entries(AGENT_LABELS).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
          <input
            type="text"
            placeholder="로그 검색..."
            value={searchText}
            onChange={e => setSearchText(e.target.value)}
            className="log-monitor-search"
          />
        </div>
      </div>

      {tab === 'live' && <LiveTab filterAgent={filterAgent} searchText={searchText} />}
      {tab === 'history' && <HistoryTab filterAgent={filterAgent} searchText={searchText} />}
    </div>
  )
}
