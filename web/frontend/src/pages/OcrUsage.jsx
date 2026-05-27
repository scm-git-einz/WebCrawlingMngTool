import { useState, useEffect } from 'react'
import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import StatCard from '../components/StatCard'

const PIE_COLORS = ['#3b82f6', '#f59e0b', '#22c55e', '#ef4444']
const STATUS_COLORS = { success: '#22c55e', fail: '#ef4444', rate_limit: '#f59e0b' }

export default function OcrUsage() {
  const [ocrSites, setOcrSites] = useState([])
  const [selectedSite, setSelectedSite] = useState(0)
  const [summary, setSummary] = useState([])
  const [details, setDetails] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/ocr/sites').then(r => r.json()).then(setOcrSites).catch(() => {})
  }, [])

  useEffect(() => {
    setLoading(true)
    const qs = selectedSite ? `?site_id=${selectedSite}` : ''
    Promise.all([
      fetch(`/api/ocr/summary${qs}`).then(r => r.json()),
      fetch(`/api/ocr/detail${qs}&limit=200`).then(r => r.json()),
    ]).then(([sum, det]) => {
      setSummary(sum)
      setDetails(det)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [selectedSite])

  if (loading) return <div className="loading">Loading...</div>

  // 통계 계산
  const totalCalls = summary.reduce((a, s) => a + s.total, 0)
  const totalSuccess = summary.reduce((a, s) => a + s.success_count, 0)
  const totalFail = summary.reduce((a, s) => a + s.fail_count, 0)
  const totalRateLimit = summary.reduce((a, s) => a + s.rate_limit_count, 0)
  const avgElapsed = summary.length
    ? Math.round(summary.reduce((a, s) => a + Number(s.avg_elapsed_ms || 0), 0) / summary.length)
    : 0

  // 차트 데이터
  const enginePieData = summary.map(s => ({
    name: s.engine === 'document-parse' ? 'Document Parse' : 'Tesseract',
    value: s.total,
  }))

  const statusBarData = summary.map(s => ({
    engine: s.engine === 'document-parse' ? 'Doc Parse' : 'Tesseract',
    success: s.success_count,
    fail: s.fail_count,
    rate_limit: s.rate_limit_count,
  }))

  return (
    <>
      <div className="page-header">
        <h1>OCR 사용 이력</h1>
        <p>Document Parse / Tesseract OCR 사용 통계</p>
      </div>

      <div className="filter-bar">
        <select
          className="form-control"
          style={{width:'auto',minWidth:250}}
          value={selectedSite}
          onChange={e => setSelectedSite(Number(e.target.value))}
        >
          <option value={0}>전체 사이트</option>
          {ocrSites.map(s => (
            <option key={s.site_id} value={s.site_id}>{s.site_name}</option>
          ))}
        </select>
      </div>

      {/* 요약 카드 */}
      <div className="stat-cards">
        <StatCard icon={'\u{1F4E1}'} color="blue"   label="총 OCR 호출"   value={totalCalls} />
        <StatCard icon={'✅'}  color="green"  label="성공"           value={totalSuccess} />
        <StatCard icon={'❌'}  color="red"    label="실패"           value={totalFail} />
        <StatCard icon={'\u{26A0}\u{FE0F}'}  color="amber"  label="Rate Limit"   value={totalRateLimit} />
        <StatCard icon={'\u{23F1}\u{FE0F}'}  color="purple" label="평균 처리시간"  value={`${avgElapsed}ms`} />
      </div>

      {/* 엔진별 상세 카드 */}
      {summary.map(s => (
        <div className="card" key={s.engine} style={{marginBottom:16}}>
          <div className="card-header">
            <h2>
              <span className={`badge ${s.engine === 'document-parse' ? 'dp' : 'tess'}`}>
                {s.engine === 'document-parse' ? 'Document Parse' : 'Tesseract'}
              </span>
            </h2>
          </div>
          <div className="card-body">
            <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(150px,1fr))',gap:16,fontSize:13}}>
              <div><span style={{color:'var(--text-secondary)'}}>총 호출</span><br/><strong style={{fontSize:20}}>{s.total}회</strong></div>
              <div><span style={{color:'var(--text-secondary)'}}>성공</span><br/><strong style={{fontSize:20,color:'#16a34a'}}>{s.success_count}회</strong></div>
              <div><span style={{color:'var(--text-secondary)'}}>실패</span><br/><strong style={{fontSize:20,color:'#dc2626'}}>{s.fail_count}회</strong></div>
              <div><span style={{color:'var(--text-secondary)'}}>Rate Limit</span><br/><strong style={{fontSize:20,color:'#d97706'}}>{s.rate_limit_count}회</strong></div>
              <div><span style={{color:'var(--text-secondary)'}}>총 텍스트</span><br/><strong style={{fontSize:20}}>{Number(s.total_text_length || 0).toLocaleString()}자</strong></div>
              <div><span style={{color:'var(--text-secondary)'}}>가격 추출</span><br/><strong style={{fontSize:20}}>{s.total_price_count}건</strong></div>
              <div><span style={{color:'var(--text-secondary)'}}>평균 처리시간</span><br/><strong style={{fontSize:20}}>{s.avg_elapsed_ms}ms</strong></div>
              <div><span style={{color:'var(--text-secondary)'}}>최초 사용</span><br/><strong>{s.first_used || '-'}</strong></div>
              <div><span style={{color:'var(--text-secondary)'}}>최종 사용</span><br/><strong>{s.last_used || '-'}</strong></div>
            </div>
          </div>
        </div>
      ))}

      {/* 차트 */}
      <div className="chart-container">
        {enginePieData.length > 0 && (
          <div className="card">
            <div className="card-header"><h2>엔진별 사용 비율</h2></div>
            <div className="card-body" style={{height:300}}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={enginePieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={100}
                    dataKey="value"
                    label={({ name, percent }) => `${name} ${(percent*100).toFixed(0)}%`}
                  >
                    {enginePieData.map((_, i) => (
                      <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {statusBarData.length > 0 && (
          <div className="card">
            <div className="card-header"><h2>엔진별 상태 분포</h2></div>
            <div className="card-body" style={{height:300}}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={statusBarData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="engine" />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="success" name="성공" fill={STATUS_COLORS.success} />
                  <Bar dataKey="fail" name="실패" fill={STATUS_COLORS.fail} />
                  <Bar dataKey="rate_limit" name="Rate Limit" fill={STATUS_COLORS.rate_limit} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </div>

      {/* 상세 이력 테이블 */}
      <div className="card">
        <div className="card-header">
          <h2>상세 이력 (최근 {details.length}건)</h2>
        </div>
        <div className="card-body no-pad">
          <table className="data-table">
            <thead>
              <tr>
                <th>날짜</th>
                <th>엔진</th>
                <th>상태</th>
                <th>텍스트 길이</th>
                <th>가격 수</th>
                <th>처리시간</th>
                <th>에러</th>
              </tr>
            </thead>
            <tbody>
              {details.map((d, i) => (
                <tr key={i}>
                  <td style={{whiteSpace:'nowrap',fontSize:12}}>{d.created_at}</td>
                  <td>
                    <span className={`badge ${d.engine === 'document-parse' ? 'dp' : 'tess'}`}>
                      {d.engine === 'document-parse' ? 'Doc Parse' : 'Tesseract'}
                    </span>
                  </td>
                  <td>
                    <span className={`badge ${d.status === 'success' ? 'success' : d.status === 'rate_limit' ? 'pending' : 'failed'}`}>
                      {d.status}
                    </span>
                  </td>
                  <td>{d.text_length.toLocaleString()}</td>
                  <td>{d.price_count}</td>
                  <td>{d.elapsed_ms.toLocaleString()}ms</td>
                  <td style={{maxWidth:200,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',fontSize:12,color:'var(--danger)'}}>
                    {d.error_msg || ''}
                  </td>
                </tr>
              ))}
              {details.length === 0 && (
                <tr><td colSpan={7} className="empty-state">이력이 없습니다</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
