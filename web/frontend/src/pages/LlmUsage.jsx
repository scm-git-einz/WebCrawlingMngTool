import { useState, useEffect, useMemo, useCallback } from 'react'

/* ── 작업 유형 한글 라벨 ── */
const TASK_LABELS = {
  structure_detection:     '페이지 구조 분석',
  description_summary:     '상품 설명 요약',
  category_classification: '카테고리 자동 분류',
  news_relevance:          '뉴스 관련성 분석',
  news_sentiment:          '뉴스 감성 분석',
  ocr_correction:          'OCR 결과 보정',
  field_extraction:        '필드 추출',
  data_cleaning:           '데이터 정제',
}

const AGENT_LABELS = {
  product: '상품', news: '뉴스', cafe: '카페',
  promotion: '이벤트', banner: '배너', directory: '목록',
  order: '주문서', coupon: '쿠폰',
}

function fmtNum(n) {
  if (n == null) return '0'
  return Number(n).toLocaleString()
}

function fmtCost(n) {
  if (!n) return '$0.0000'
  return '$' + Number(n).toFixed(4)
}

function fmtDate(s) {
  if (!s) return '-'
  try {
    const d = new Date(s)
    if (isNaN(d.getTime())) return '-'
    const Y = d.getFullYear()
    const M = String(d.getMonth() + 1).padStart(2, '0')
    const D = String(d.getDate()).padStart(2, '0')
    const h = String(d.getHours()).padStart(2, '0')
    const m = String(d.getMinutes()).padStart(2, '0')
    const sec = String(d.getSeconds()).padStart(2, '0')
    return `${Y}-${M}-${D} ${h}:${m}:${sec}`
  } catch { return '-' }
}

/* ── 간단한 바 차트 (CSS only) ── */
function BarChart({ data, labelKey, valueKey, colorVar }) {
  const max = Math.max(...data.map(d => d[valueKey] || 0), 1)
  return (
    <div className="llm-bar-chart">
      {data.map((d, i) => (
        <div className="llm-bar-row" key={i}>
          <span className="llm-bar-label">{d[labelKey]}</span>
          <div className="llm-bar-track">
            <div
              className="llm-bar-fill"
              style={{
                width: `${Math.max((d[valueKey] / max) * 100, 2)}%`,
                background: `var(${colorVar || '--primary'})`,
              }}
            />
          </div>
          <span className="llm-bar-value">{fmtNum(d[valueKey])}</span>
        </div>
      ))}
    </div>
  )
}

export default function LlmUsage() {
  const [summary, setSummary] = useState(null)
  const [detail, setDetail] = useState([])
  const [loading, setLoading] = useState(true)
  const [filterAgent, setFilterAgent] = useState('')
  const [filterTask, setFilterTask] = useState('')
  const [tab, setTab] = useState('overview') // overview | detail

  const loadData = useCallback(() => {
    Promise.all([
      fetch('/api/llm/summary').then(r => r.json()),
      fetch(`/api/llm/detail?agent_type=${filterAgent}&task_type=${filterTask}&limit=100`)
        .then(r => r.json()),
    ])
      .then(([sum, det]) => {
        setSummary(sum)
        setDetail(det)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [filterAgent, filterTask])

  useEffect(() => { loadData() }, [loadData])

  /* 에이전트 / 작업유형 목록 (summary 기반) */
  const agents = useMemo(() =>
    (summary?.by_agent || []).map(a => a.agent_type),
  [summary])

  const tasks = useMemo(() =>
    (summary?.by_task || []).map(t => t.task_type),
  [summary])

  if (loading) {
    return (
      <div className="page-container">
        <h1 className="page-title">🤖 LLM 토큰 사용량</h1>
        <p style={{ color: 'var(--text-secondary)' }}>데이터를 불러오는 중...</p>
      </div>
    )
  }

  const s = summary || {}
  const hasData = s.total_calls > 0

  return (
    <div className="page-container">
      <h1 className="page-title">🤖 LLM 토큰 사용량</h1>
      <p className="page-subtitle">
        에이전트별 LLM API 호출 현황 — 토큰 사용량 및 비용을 추적합니다.
      </p>

      {/* ── 탭 ── */}
      <div className="llm-tabs">
        <button className={`llm-tab ${tab === 'overview' ? 'active' : ''}`}
          onClick={() => setTab('overview')}>📊 전체 현황</button>
        <button className={`llm-tab ${tab === 'detail' ? 'active' : ''}`}
          onClick={() => setTab('detail')}>📋 상세 이력</button>
      </div>

      {!hasData && (
        <div className="llm-empty">
          <div className="llm-empty-icon">🤖</div>
          <h3>LLM 사용 이력이 없습니다</h3>
          <p>에이전트에서 LLM API를 호출하면 토큰 사용량이 여기에 기록됩니다.</p>
          <div className="llm-empty-guide">
            <h4>사용 방법</h4>
            <pre>{`from core.llm_client import LLMClient

llm = LLMClient(agent_type="product", site_id=5)
result = llm.ask(
    task_type="description_summary",
    prompt="상품 설명을 요약해줘: ...",
)
print(result["text"])       # 응답 텍스트
print(result["tokens"])     # 토큰 사용량
print(result["cost_usd"])   # 비용 (USD)`}</pre>
          </div>
        </div>
      )}

      {hasData && tab === 'overview' && (
        <>
          {/* ── 요약 카드 ── */}
          <div className="llm-summary-cards">
            <div className="llm-card">
              <div className="llm-card-value">{fmtNum(s.total_calls)}</div>
              <div className="llm-card-label">총 호출 수</div>
            </div>
            <div className="llm-card">
              <div className="llm-card-value">{fmtNum(s.total_prompt_tokens)}</div>
              <div className="llm-card-label">입력 토큰</div>
            </div>
            <div className="llm-card">
              <div className="llm-card-value">{fmtNum(s.total_completion_tokens)}</div>
              <div className="llm-card-label">출력 토큰</div>
            </div>
            <div className="llm-card">
              <div className="llm-card-value llm-highlight">{fmtNum(s.total_tokens)}</div>
              <div className="llm-card-label">전체 토큰</div>
            </div>
            <div className="llm-card">
              <div className="llm-card-value llm-cost">{fmtCost(s.total_cost_usd)}</div>
              <div className="llm-card-label">총 비용</div>
            </div>
          </div>

          {/* ── 차트 그리드 ── */}
          <div className="llm-chart-grid">
            {/* 에이전트별 */}
            <div className="llm-chart-panel">
              <h3 className="llm-chart-title">에이전트별 토큰 사용량</h3>
              <BarChart
                data={(s.by_agent || []).map(a => ({
                  label: AGENT_LABELS[a.agent_type] || a.agent_type,
                  tokens: a.total_tokens,
                  cost: a.cost_usd,
                }))}
                labelKey="label"
                valueKey="tokens"
                colorVar="--primary"
              />
              <table className="llm-mini-table">
                <thead>
                  <tr><th>에이전트</th><th>호출</th><th>입력</th><th>출력</th><th>합계</th><th>비용</th></tr>
                </thead>
                <tbody>
                  {(s.by_agent || []).map(a => (
                    <tr key={a.agent_type}>
                      <td>{AGENT_LABELS[a.agent_type] || a.agent_type}</td>
                      <td>{fmtNum(a.calls)}</td>
                      <td>{fmtNum(a.prompt_tokens)}</td>
                      <td>{fmtNum(a.completion_tokens)}</td>
                      <td><strong>{fmtNum(a.total_tokens)}</strong></td>
                      <td>{fmtCost(a.cost_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* 작업유형별 */}
            <div className="llm-chart-panel">
              <h3 className="llm-chart-title">작업유형별 토큰 사용량</h3>
              <BarChart
                data={(s.by_task || []).map(t => ({
                  label: TASK_LABELS[t.task_type] || t.task_type,
                  tokens: t.total_tokens,
                }))}
                labelKey="label"
                valueKey="tokens"
                colorVar="--success"
              />
              <table className="llm-mini-table">
                <thead>
                  <tr><th>작업유형</th><th>호출</th><th>입력</th><th>출력</th><th>합계</th><th>비용</th></tr>
                </thead>
                <tbody>
                  {(s.by_task || []).map(t => (
                    <tr key={t.task_type}>
                      <td>{TASK_LABELS[t.task_type] || t.task_type}</td>
                      <td>{fmtNum(t.calls)}</td>
                      <td>{fmtNum(t.prompt_tokens)}</td>
                      <td>{fmtNum(t.completion_tokens)}</td>
                      <td><strong>{fmtNum(t.total_tokens)}</strong></td>
                      <td>{fmtCost(t.cost_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* 모델별 */}
            {(s.by_model || []).length > 0 && (
              <div className="llm-chart-panel">
                <h3 className="llm-chart-title">모델별 사용량</h3>
                <table className="llm-mini-table">
                  <thead>
                    <tr><th>모델</th><th>호출</th><th>입력</th><th>출력</th><th>합계</th><th>비용</th></tr>
                  </thead>
                  <tbody>
                    {(s.by_model || []).map(m => (
                      <tr key={m.model}>
                        <td style={{ fontSize: 11 }}>{m.model || '(미지정)'}</td>
                        <td>{fmtNum(m.calls)}</td>
                        <td>{fmtNum(m.prompt_tokens)}</td>
                        <td>{fmtNum(m.completion_tokens)}</td>
                        <td><strong>{fmtNum(m.total_tokens)}</strong></td>
                        <td>{fmtCost(m.cost_usd)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* 일별 추이 */}
            {(s.daily || []).length > 0 && (
              <div className="llm-chart-panel">
                <h3 className="llm-chart-title">일별 사용 추이 (최근 30일)</h3>
                <BarChart
                  data={(s.daily || []).map(d => ({
                    label: d.date.slice(5),  // MM-DD
                    tokens: d.total_tokens,
                  }))}
                  labelKey="label"
                  valueKey="tokens"
                  colorVar="--warning"
                />
              </div>
            )}
          </div>
        </>
      )}

      {hasData && tab === 'detail' && (
        <>
          {/* ── 필터 ── */}
          <div className="llm-filter-bar">
            <label>
              <span>에이전트</span>
              <select value={filterAgent} onChange={e => setFilterAgent(e.target.value)}>
                <option value="">전체</option>
                {agents.map(a => <option key={a} value={a}>{AGENT_LABELS[a] || a}</option>)}
              </select>
            </label>
            <label>
              <span>작업유형</span>
              <select value={filterTask} onChange={e => setFilterTask(e.target.value)}>
                <option value="">전체</option>
                {tasks.map(t => <option key={t} value={t}>{TASK_LABELS[t] || t}</option>)}
              </select>
            </label>
            <span className="llm-filter-count">{detail.length}건</span>
          </div>

          {/* ── 상세 테이블 ── */}
          <div className="llm-detail-scroll">
            <table className="llm-detail-table">
              <thead>
                <tr>
                  <th>일시</th>
                  <th>에이전트</th>
                  <th>작업유형</th>
                  <th>사이트</th>
                  <th>모델</th>
                  <th>입력</th>
                  <th>출력</th>
                  <th>합계</th>
                  <th>비용</th>
                  <th>소요(ms)</th>
                  <th>입력 미리보기</th>
                  <th>출력 미리보기</th>
                </tr>
              </thead>
              <tbody>
                {detail.map(d => (
                  <tr key={d.id}>
                    <td className="llm-td-date">{fmtDate(d.created_at)}</td>
                    <td>
                      <span className="badge success">
                        {AGENT_LABELS[d.agent_type] || d.agent_type}
                      </span>
                    </td>
                    <td className="llm-td-task">{TASK_LABELS[d.task_type] || d.task_type}</td>
                    <td>{d.site_name || '-'}</td>
                    <td className="llm-td-model">{d.model || '-'}</td>
                    <td className="llm-td-num">{fmtNum(d.prompt_tokens)}</td>
                    <td className="llm-td-num">{fmtNum(d.completion_tokens)}</td>
                    <td className="llm-td-num"><strong>{fmtNum(d.total_tokens)}</strong></td>
                    <td className="llm-td-cost">{fmtCost(d.cost_usd)}</td>
                    <td className="llm-td-num">{fmtNum(d.elapsed_ms)}</td>
                    <td className="llm-td-preview" title={d.input_preview}>{d.input_preview || '-'}</td>
                    <td className="llm-td-preview" title={d.output_preview}>{d.output_preview || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
