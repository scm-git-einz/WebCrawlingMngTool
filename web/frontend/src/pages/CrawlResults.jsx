import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'

const STATUS_CLASS = {
  success: 'success', running: 'running',
  pending: 'pending', failed: 'failed',
}

const AGENT_LABELS = {
  product: '상품 수집', news: '뉴스 검색', cafe: '카페 수집',
  promotion: '이벤트 수집', banner: '배너 수집', directory: '목록 수집',
}

export default function CrawlResults() {
  const [searchParams] = useSearchParams()
  const initialSite = Number(searchParams.get('site') || 0)

  const [sites, setSites] = useState([])
  const [selectedSite, setSelectedSite] = useState(initialSite)
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState(null)
  const [detail, setDetail] = useState(null)

  useEffect(() => {
    fetch('/api/sites').then(r => r.json()).then(data => {
      setSites(data)
      // URL에서 site 파라미터가 있으면 해당 사이트 선택
      if (initialSite) setSelectedSite(initialSite)
    }).catch(() => {})
  }, [])

  useEffect(() => {
    setLoading(true)
    setExpandedId(null)
    setDetail(null)
    const url = selectedSite
      ? `/api/results?site_id=${selectedSite}`
      : '/api/results'
    fetch(url)
      .then(r => r.json())
      .then(data => { setResults(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [selectedSite])

  const toggleExpand = async (id) => {
    if (expandedId === id) {
      setExpandedId(null)
      setDetail(null)
      return
    }
    setExpandedId(id)
    const res = await fetch(`/api/results/${id}`)
    const data = await res.json()
    setDetail(data)
  }

  // 사이트 카테고리별 그룹
  const sitesByCategory = {}
  sites.forEach(s => {
    const cat = s.category || '(미분류)'
    if (!sitesByCategory[cat]) sitesByCategory[cat] = []
    sitesByCategory[cat].push(s)
  })

  return (
    <>
      <div className="page-header">
        <h1>수집 결과</h1>
        <p>도메인별 크롤링 결과를 확인합니다</p>
      </div>

      <div className="filter-bar">
        <select
          className="form-control"
          style={{width:'auto',minWidth:280}}
          value={selectedSite}
          onChange={e => setSelectedSite(Number(e.target.value))}
        >
          <option value={0}>전체 사이트</option>
          {Object.entries(sitesByCategory).map(([cat, catSites]) => (
            <optgroup key={cat} label={cat}>
              {catSites.map(s => (
                <option key={s.id} value={s.id}>{s.site_name}</option>
              ))}
            </optgroup>
          ))}
        </select>
        {selectedSite > 0 && (() => {
          const site = sites.find(s => s.id === selectedSite)
          return site ? (
            <span style={{fontSize:12,color:'var(--text-secondary)'}}>
              <span className={`badge ${site.agent_type === 'product' ? 'dp' : site.agent_type === 'news' ? 'pending' : 'tess'}`} style={{fontSize:11}}>
                {AGENT_LABELS[site.agent_type] || site.agent_type}
              </span>
            </span>
          ) : null
        })()}
      </div>

      <div className="card">
        <div className="card-header">
          <h2>크롤링 결과 ({results.length}건)</h2>
        </div>
        <div className="card-body no-pad">
          {loading ? <div className="loading">Loading...</div> : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>사이트</th>
                  <th>유형</th>
                  <th>크롤링 날짜</th>
                  <th>상태</th>
                  <th>수집 건수</th>
                  <th>소요시간</th>
                  <th>상세</th>
                </tr>
              </thead>
              <tbody>
                {results.map(r => (
                  <ResultRow
                    key={r.id}
                    r={r}
                    isExpanded={expandedId === r.id}
                    detail={expandedId === r.id ? detail : null}
                    onToggle={() => toggleExpand(r.id)}
                  />
                ))}
                {results.length === 0 && (
                  <tr><td colSpan={8} className="empty-state">결과가 없습니다</td></tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </>
  )
}


function ResultRow({ r, isExpanded, detail, onToggle }) {
  return (
    <>
      <tr>
        <td>{r.id}</td>
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
        <td>
          <button className="btn btn-outline btn-sm" onClick={onToggle}>
            {isExpanded ? '접기' : '펼치기'}
          </button>
        </td>
      </tr>
      {isExpanded && (
        <tr className="expand-row">
          <td colSpan={8}>
            <ExpandedDetail detail={detail} />
          </td>
        </tr>
      )}
    </>
  )
}


/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   에이전트 유형별 상세 뷰
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function ExpandedDetail({ detail }) {
  if (!detail) return <div className="loading">Loading...</div>

  const agentType = detail.agent_type || 'product'

  return (
    <div className="expand-content">
      {agentType === 'product'   && <ProductDetail    detail={detail} />}
      {agentType === 'news'      && <NewsDetail       detail={detail} />}
      {agentType === 'cafe'      && <CafeDetail       detail={detail} />}
      {agentType === 'promotion' && <PromotionDetail  detail={detail} />}
      {agentType === 'banner'    && <BannerDetail     detail={detail} />}
      {agentType === 'directory' && <DirectoryDetail  detail={detail} />}
    </div>
  )
}


/* ── product: 매장 상품 결과 ────────────────────── */
function ProductDetail({ detail }) {
  const products = detail.products || []
  const storeInfo = detail.store_info || {}
  const storeName = storeInfo.store_name || storeInfo.name || ''
  const hasStore = storeName && storeName !== 'N/A'

  // 상품 필드 헬퍼: agent가 저장하는 다양한 필드명에 대응
  const getName = (p) => p.product_name || p.name || p.title || p.goodsNm || ''
  const getBrand = (p) => p.brand_name || p.brand || ''
  const getPrice = (p) => {
    const v = p.selling_price ?? p.price ?? p.sale_price ?? p.salePrice ?? null
    if (v === null || v === '') return '-'
    if (typeof v === 'number') return v.toLocaleString()
    return String(v).length > 40 ? '-' : String(v)
  }
  const getOrigPrice = (p) => {
    const v = p.original_price ?? p.retail_price ?? p.listPrice ?? null
    if (v === null || v === '' || v === 0) return ''
    if (typeof v === 'number') return v.toLocaleString()
    return String(v).length > 40 ? '' : String(v)
  }
  const getImage = (p) => p.image_url || p.imageUrl || p.img || ''
  const getUrl = (p) => p.product_url || p.url || p.link || ''

  return (
    <>
      {/* 매장 정보 카드 */}
      {hasStore && (
        <div className="store-info-card">
          {storeInfo.logo_url && (
            <img
              src={storeInfo.logo_url}
              alt="logo"
              className="store-logo"
              onError={e => { e.target.style.display = 'none' }}
            />
          )}
          <div className="store-info-body">
            <div className="store-info-name">{storeName}</div>
            {storeInfo.description && (
              <div className="store-info-desc">
                {String(storeInfo.description).slice(0, 120)}
              </div>
            )}
            <div className="store-info-meta">
              {storeInfo.category && <span>카테고리: {storeInfo.category}</span>}
              {storeInfo.follower_count && <span>팔로워: {Number(storeInfo.follower_count).toLocaleString()}</span>}
              {storeInfo.product_count && <span>상품: {Number(storeInfo.product_count).toLocaleString()}개</span>}
              {detail.site_url && (
                <a href={detail.site_url} target="_blank" rel="noreferrer" style={{color:'var(--primary)',textDecoration:'none'}}>
                  사이트 방문
                </a>
              )}
            </div>
          </div>
        </div>
      )}

      <div style={{display:'flex',gap:24,marginBottom:16,fontSize:13,color:'var(--text-secondary)'}}>
        <span>총 상품: <strong>{products.length}</strong>개</span>
      </div>

      {products.length > 0 ? (
        <table className="price-table">
          <thead>
            <tr>
              <th style={{width:40}}>#</th>
              <th style={{width:50}}>이미지</th>
              <th>상품명</th>
              <th>브랜드</th>
              <th>판매가</th>
              <th>정가</th>
            </tr>
          </thead>
          <tbody>
            {products.slice(0, 100).map((p, i) => {
              const name = getName(p)
              const url = getUrl(p)
              const img = getImage(p)
              return (
                <tr key={i}>
                  <td style={{color:'var(--text-secondary)'}}>{i + 1}</td>
                  <td>
                    {img ? (
                      <img
                        src={img}
                        alt=""
                        style={{width:40,height:40,objectFit:'cover',borderRadius:4,background:'#f5f5f5'}}
                        onError={e => { e.target.style.display = 'none' }}
                      />
                    ) : (
                      <div style={{width:40,height:40,background:'#f0f0f0',borderRadius:4}} />
                    )}
                  </td>
                  <td style={{fontWeight:600,maxWidth:280,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
                    {url && !url.startsWith('javascript') ? (
                      <a href={url} target="_blank" rel="noreferrer" style={{color:'var(--text)',textDecoration:'none'}}>
                        {name || '-'}
                      </a>
                    ) : (name || '-')}
                  </td>
                  <td style={{fontSize:12}}>{getBrand(p) || '-'}</td>
                  <td style={{fontWeight:600,whiteSpace:'nowrap'}}>
                    {getPrice(p)}
                  </td>
                  <td style={{fontSize:12,color:'var(--text-secondary)',whiteSpace:'nowrap',textDecoration: getOrigPrice(p) ? 'line-through' : 'none'}}>
                    {getOrigPrice(p)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      ) : (
        <div className="empty-state">수집된 상품이 없습니다</div>
      )}
      {products.length > 100 && (
        <div style={{textAlign:'center',padding:12,fontSize:13,color:'var(--text-secondary)'}}>
          ... 외 {products.length - 100}개 상품
        </div>
      )}
    </>
  )
}


/* ── news: 뉴스 기사 결과 ──────────────────────── */
function NewsDetail({ detail }) {
  const articles = detail.products || []

  // 키워드별 그룹핑
  const byKeyword = {}
  articles.forEach(a => {
    const kw = a.keyword || a.search_keyword || '기타'
    if (!byKeyword[kw]) byKeyword[kw] = []
    byKeyword[kw].push(a)
  })

  return (
    <>
      <div style={{display:'flex',gap:24,marginBottom:16,fontSize:13,color:'var(--text-secondary)'}}>
        <span>총 기사: <strong>{articles.length}</strong>건</span>
        <span>키워드: <strong>{Object.keys(byKeyword).length}</strong>개</span>
      </div>

      {Object.entries(byKeyword).map(([kw, kwArticles]) => (
        <div key={kw} style={{marginBottom:20}}>
          <h4 style={{fontSize:14,fontWeight:600,marginBottom:8,display:'flex',alignItems:'center',gap:8}}>
            <span className="badge dp">{kw}</span>
            <span style={{fontSize:12,fontWeight:400,color:'var(--text-secondary)'}}>
              {kwArticles.length}건
            </span>
          </h4>
          <table className="price-table">
            <thead>
              <tr>
                <th style={{width:40}}>#</th>
                <th>제목</th>
                <th>언론사</th>
                <th>날짜</th>
              </tr>
            </thead>
            <tbody>
              {kwArticles.map((a, i) => (
                <tr key={i}>
                  <td style={{color:'var(--text-secondary)'}}>{i + 1}</td>
                  <td style={{fontWeight:600}}>
                    {a.link || a.url ? (
                      <a href={a.link || a.url} target="_blank" rel="noreferrer"
                         style={{color:'var(--primary)',textDecoration:'none'}}>
                        {a.title || a.name || '-'}
                      </a>
                    ) : (a.title || a.name || '-')}
                  </td>
                  <td style={{fontSize:12,whiteSpace:'nowrap'}}>
                    {a.source || a.publisher || a.press || '-'}
                  </td>
                  <td style={{fontSize:12,whiteSpace:'nowrap'}}>
                    {a.date || a.published_date || a.pub_date || '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}

      {articles.length === 0 && (
        <div className="empty-state">수집된 기사가 없습니다</div>
      )}
    </>
  )
}


/* ── cafe: 카페 게시글 + 가격 결과 ──────────────── */
function CafeDetail({ detail }) {
  const products = detail.products || []

  // 가격 정보 추출
  const allPrices = []
  const postsWithPrices = []
  const postsWithoutPrices = []

  products.forEach(p => {
    const title = p.title || p.post_title || ''
    const prices = p.prices || []
    if (prices.length > 0) {
      postsWithPrices.push(p)
      prices.forEach(pr => {
        allPrices.push({
          postTitle: title,
          productName: pr.product_name || pr.name || '',
          price: pr.price || '',
          source: pr.source || '',
          ocrEngine: pr.ocr_engine || '',
        })
      })
    } else {
      postsWithoutPrices.push(p)
    }
  })

  const textCount = allPrices.filter(p => p.source === 'text').length
  const ocrCount = allPrices.filter(p => p.source === 'ocr').length

  return (
    <>
      <div style={{display:'flex',gap:24,marginBottom:16,fontSize:13,color:'var(--text-secondary)',flexWrap:'wrap'}}>
        <span>게시글: <strong>{products.length}</strong></span>
        <span>가격 포함: <strong>{postsWithPrices.length}</strong></span>
        <span>총 가격 항목: <strong>{allPrices.length}</strong></span>
        <span>본문 텍스트: <strong>{textCount}</strong></span>
        <span>이미지 OCR: <strong>{ocrCount}</strong></span>
      </div>

      {allPrices.length > 0 && (
        <>
          <h4 style={{fontSize:14,fontWeight:600,marginBottom:8}}>가격 정보</h4>
          <table className="price-table">
            <thead>
              <tr>
                <th>게시글</th>
                <th>상품명</th>
                <th>가격</th>
                <th>출처</th>
                <th>OCR 엔진</th>
              </tr>
            </thead>
            <tbody>
              {allPrices.slice(0, 100).map((p, i) => (
                <tr key={i}>
                  <td style={{maxWidth:180,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
                    {p.postTitle}
                  </td>
                  <td style={{maxWidth:220,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
                    {p.productName || '-'}
                  </td>
                  <td style={{fontWeight:600,whiteSpace:'nowrap'}}>{p.price}</td>
                  <td>
                    <span className={`badge ${p.source === 'ocr' ? 'dp' : 'text-src'}`}>
                      {p.source}
                    </span>
                  </td>
                  <td>
                    {p.ocrEngine && (
                      <span className={`badge ${p.ocrEngine === 'document-parse' ? 'dp' : 'tess'}`}>
                        {p.ocrEngine === 'document-parse' ? 'Doc Parse' : 'Tesseract'}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {allPrices.length > 100 && (
            <div style={{textAlign:'center',padding:12,fontSize:13,color:'var(--text-secondary)'}}>
              ... 외 {allPrices.length - 100}개 항목
            </div>
          )}
        </>
      )}

      {postsWithoutPrices.length > 0 && (
        <>
          <h4 style={{fontSize:14,fontWeight:600,marginTop:20,marginBottom:8}}>가격 없는 게시글</h4>
          <table className="price-table">
            <thead>
              <tr>
                <th style={{width:40}}>#</th>
                <th>제목</th>
                <th>작성시간</th>
              </tr>
            </thead>
            <tbody>
              {postsWithoutPrices.map((p, i) => (
                <tr key={i}>
                  <td style={{color:'var(--text-secondary)'}}>{i + 1}</td>
                  <td>{p.title || p.post_title || '-'}</td>
                  <td style={{fontSize:12,whiteSpace:'nowrap'}}>{p.time || p.date || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {products.length === 0 && (
        <div className="empty-state">수집된 게시글이 없습니다</div>
      )}
    </>
  )
}


/* ── promotion: 이벤트/프로모션 결과 ──────────────── */
function PromotionDetail({ detail }) {
  const events = detail.products || []
  const storeInfo = detail.store_info || {}
  const storeName = storeInfo.store_name || ''

  const eventsWithDetail = events.filter(e => e.detail)
  const eventsWithProducts = events.filter(e => e.products && e.products.length > 0)
  const totalProducts = events.reduce((sum, e) => sum + (e.products ? e.products.length : 0), 0)

  const [expandedEvent, setExpandedEvent] = useState(null)

  return (
    <>
      {/* 사이트 정보 */}
      {storeName && storeName !== 'N/A' && (
        <div className="store-info-card" style={{marginBottom:16}}>
          <div className="store-info-body">
            <div className="store-info-name">{storeName}</div>
            {storeInfo.description && (
              <div className="store-info-desc">{storeInfo.description}</div>
            )}
          </div>
        </div>
      )}

      {/* 요약 통계 */}
      <div style={{display:'flex',gap:24,marginBottom:16,fontSize:13,color:'var(--text-secondary)',flexWrap:'wrap'}}>
        <span>이벤트: <strong>{events.length}</strong></span>
        <span>상세 수집: <strong>{eventsWithDetail.length}</strong></span>
        <span>상품 포함: <strong>{eventsWithProducts.length}</strong></span>
        <span>총 상품: <strong>{totalProducts}</strong></span>
      </div>

      {/* 이벤트 목록 */}
      {events.length > 0 && (
        <table className="price-table">
          <thead>
            <tr>
              <th style={{width:40}}>#</th>
              <th style={{width:60}}>이미지</th>
              <th>이벤트명</th>
              <th style={{width:140}}>기간</th>
              <th style={{width:70}}>상태</th>
              <th style={{width:60}}>상품</th>
              <th style={{width:50}}>상세</th>
            </tr>
          </thead>
          <tbody>
            {events.map((ev, i) => {
              const isExpanded = expandedEvent === i
              return (
                <>
                  <tr key={i}
                    onClick={() => setExpandedEvent(isExpanded ? null : i)}
                    style={{cursor:'pointer'}}
                    className={isExpanded ? 'row-running' : ''}
                  >
                    <td style={{color:'var(--text-secondary)'}}>{ev.display_order || i + 1}</td>
                    <td>
                      {ev.image_url ? (
                        <img src={ev.image_url} alt="" style={{width:48,height:32,objectFit:'cover',borderRadius:4}} />
                      ) : '-'}
                    </td>
                    <td style={{fontWeight:500,maxWidth:260,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
                      {ev.event_url ? (
                        <a href={ev.event_url} target="_blank" rel="noreferrer"
                           style={{color:'var(--primary)',textDecoration:'none'}}
                           onClick={e => e.stopPropagation()}>
                          {ev.title || '(제목 없음)'}
                        </a>
                      ) : (ev.title || '(제목 없음)')}
                    </td>
                    <td style={{fontSize:12,whiteSpace:'nowrap'}}>
                      {ev.date_text || (ev.start_date ? `${ev.start_date} ~ ${ev.end_date || ''}` : '-')}
                    </td>
                    <td>
                      {ev.status ? (
                        <span className={`badge ${/진행|ongoing|active/i.test(ev.status) ? 'success' : /종료|ended|closed/i.test(ev.status) ? 'failed' : 'pending'}`}>
                          {ev.status}
                        </span>
                      ) : '-'}
                    </td>
                    <td style={{textAlign:'center'}}>
                      {ev.products && ev.products.length > 0
                        ? <span className="badge dp">{ev.products.length}</span>
                        : '-'}
                    </td>
                    <td style={{textAlign:'center'}}>
                      {ev.detail ? '>' : '-'}
                    </td>
                  </tr>
                  {isExpanded && ev.detail && (
                    <tr key={`detail-${i}`}>
                      <td colSpan={7} style={{background:'var(--bg-secondary)',padding:16}}>
                        <div style={{fontSize:13}}>
                          <h4 style={{fontSize:14,fontWeight:600,marginBottom:8}}>{ev.detail.title || ev.title}</h4>
                          {ev.detail.period && (
                            <div style={{fontSize:12,color:'var(--text-secondary)',marginBottom:8}}>기간: {ev.detail.period}</div>
                          )}
                          {ev.detail.benefits && (
                            <div style={{marginBottom:8}}>
                              <strong style={{fontSize:12}}>혜택:</strong>
                              <div style={{fontSize:12,color:'var(--text-secondary)',whiteSpace:'pre-wrap',maxHeight:100,overflow:'auto'}}>
                                {ev.detail.benefits}
                              </div>
                            </div>
                          )}
                          {ev.detail.content_text && (
                            <div style={{marginBottom:8}}>
                              <strong style={{fontSize:12}}>내용:</strong>
                              <div style={{fontSize:12,color:'var(--text-secondary)',whiteSpace:'pre-wrap',maxHeight:150,overflow:'auto'}}>
                                {ev.detail.content_text.substring(0, 500)}
                                {ev.detail.content_text.length > 500 ? '...' : ''}
                              </div>
                            </div>
                          )}
                          {ev.products && ev.products.length > 0 && (
                            <div style={{marginTop:12}}>
                              <strong style={{fontSize:12}}>이벤트 상품 ({ev.products.length})</strong>
                              <table className="price-table" style={{marginTop:8}}>
                                <thead>
                                  <tr>
                                    <th style={{width:30}}>#</th>
                                    <th>상품명</th>
                                    <th>브랜드</th>
                                    <th>가격</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {ev.products.map((p, pi) => (
                                    <tr key={pi}>
                                      <td style={{color:'var(--text-secondary)'}}>{pi + 1}</td>
                                      <td style={{maxWidth:200,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
                                        {p.product_url ? (
                                          <a href={p.product_url} target="_blank" rel="noreferrer"
                                             style={{color:'var(--primary)',textDecoration:'none'}}>
                                            {p.product_name || '-'}
                                          </a>
                                        ) : (p.product_name || '-')}
                                      </td>
                                      <td>{p.brand_name || '-'}</td>
                                      <td style={{fontWeight:600,whiteSpace:'nowrap'}}>{p.price || '-'}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              )
            })}
          </tbody>
        </table>
      )}

      {events.length === 0 && (
        <div className="empty-state">수집된 이벤트가 없습니다</div>
      )}
    </>
  )
}


/* ── banner: 배너/비주얼 결과 ───────────────────── */
function BannerDetail({ detail }) {
  const banners = detail.products || []
  const storeInfo = detail.store_info || {}
  const storeName = storeInfo.store_name || storeInfo.name || ''

  const heroBanners = banners.filter(b => b.area_type === 'hero')
  const subBanners = banners.filter(b => b.area_type === 'sub_banner')
  const popupBanners = banners.filter(b => b.area_type === 'popup')

  return (
    <>
      {storeName && storeName !== 'N/A' && (
        <div className="store-info-card" style={{marginBottom:16}}>
          <div className="store-info-body">
            <div className="store-info-name">{storeName}</div>
          </div>
        </div>
      )}

      <div style={{display:'flex',gap:24,marginBottom:16,fontSize:13,color:'var(--text-secondary)',flexWrap:'wrap'}}>
        <span>전체: <strong>{banners.length}</strong></span>
        {heroBanners.length > 0 && <span>히어로: <strong>{heroBanners.length}</strong></span>}
        {subBanners.length > 0 && <span>서브: <strong>{subBanners.length}</strong></span>}
        {popupBanners.length > 0 && <span>팝업: <strong>{popupBanners.length}</strong></span>}
      </div>

      {banners.length > 0 && (
        <div className="banner-grid">
          {banners.map((b, i) => (
            <div key={i} className="banner-card">
              <div className="banner-card-header">
                <span className={`badge ${b.area_type === 'hero' ? 'success' : b.area_type === 'popup' ? 'failed' : 'pending'}`}>
                  {b.area_type === 'hero' ? '히어로' : b.area_type === 'sub_banner' ? '서브' : b.area_type === 'popup' ? '팝업' : b.area_type}
                </span>
                <span style={{fontSize:11,color:'var(--text-secondary)'}}>#{b.position || i + 1}</span>
              </div>
              {b.image_url && (
                <div className="banner-card-image">
                  <img src={b.image_url} alt="" style={{width:'100%',maxHeight:180,objectFit:'cover',borderRadius:4}} />
                </div>
              )}
              {b.text && (
                <div className="banner-card-text">{b.text}</div>
              )}
              <div className="banner-card-meta">
                {b.width > 0 && <span>{b.width}×{b.height}</span>}
                {b.link_url && (
                  <a href={b.link_url} target="_blank" rel="noreferrer"
                     style={{color:'var(--primary)',textDecoration:'none',fontSize:11}}
                     onClick={e => e.stopPropagation()}>
                    링크 →
                  </a>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {banners.length === 0 && (
        <div className="empty-state">수집된 배너가 없습니다</div>
      )}
    </>
  )
}


/* ── directory: 브랜드/이벤트 목록 결과 ─────────── */
function DirectoryDetail({ detail }) {
  const items = detail.products || []
  const storeInfo = detail.store_info || {}
  const storeName = storeInfo.store_name || storeInfo.name || ''

  const withDetail = items.filter(it => it.description)
  const initials = [...new Set(items.map(it => it.brand_initial).filter(Boolean))]

  return (
    <>
      {storeName && storeName !== 'N/A' && (
        <div className="store-info-card" style={{marginBottom:16}}>
          <div className="store-info-body">
            <div className="store-info-name">{storeName}</div>
          </div>
        </div>
      )}

      <div style={{display:'flex',gap:24,marginBottom:16,fontSize:13,color:'var(--text-secondary)',flexWrap:'wrap'}}>
        <span>총 항목: <strong>{items.length}</strong></span>
        {withDetail.length > 0 && <span>상세 수집: <strong>{withDetail.length}</strong></span>}
        {initials.length > 0 && <span>인덱스: <strong>{initials.length}</strong>개</span>}
      </div>

      {items.length > 0 && (
        <table className="price-table">
          <thead>
            <tr>
              <th style={{width:40}}>#</th>
              {initials.length > 0 && <th style={{width:40}}>색인</th>}
              <th>이름</th>
              <th style={{width:100}}>카테고리</th>
              {items.some(it => it.period) && <th style={{width:160}}>기간</th>}
              {items.some(it => it.status) && <th style={{width:70}}>상태</th>}
              <th style={{width:50}}>상세</th>
            </tr>
          </thead>
          <tbody>
            {items.map((it, i) => (
              <tr key={i}>
                <td style={{color:'var(--text-secondary)'}}>{i + 1}</td>
                {initials.length > 0 && (
                  <td style={{textAlign:'center',fontWeight:600,color:'var(--primary)'}}>{it.brand_initial || '-'}</td>
                )}
                <td style={{fontWeight:500,maxWidth:250,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
                  {it.detail_url ? (
                    <a href={it.detail_url} target="_blank" rel="noreferrer"
                       style={{color:'var(--primary)',textDecoration:'none'}}>
                      {it.name || '(이름 없음)'}
                    </a>
                  ) : (it.name || '(이름 없음)')}
                </td>
                <td style={{fontSize:12,color:'var(--text-secondary)'}}>{it.category || '-'}</td>
                {items.some(x => x.period) && (
                  <td style={{fontSize:12,whiteSpace:'nowrap'}}>{it.period || '-'}</td>
                )}
                {items.some(x => x.status) && (
                  <td>
                    {it.status ? (
                      <span className={`badge ${/진행|ongoing|active/i.test(it.status) ? 'success' : /종료|ended|closed/i.test(it.status) ? 'failed' : 'pending'}`}>
                        {it.status}
                      </span>
                    ) : '-'}
                  </td>
                )}
                <td style={{textAlign:'center'}}>
                  {it.description ? '>' : '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {items.length === 0 && (
        <div className="empty-state">수집된 항목이 없습니다</div>
      )}
    </>
  )
}
