/* Contract 1.0.0 consumer. No personal settings are persisted or transmitted. */
(function () {
  'use strict';
  const arr = v => Array.isArray(v) ? v.filter(x => x && typeof x === 'object') : [];
  const num = v => typeof v === 'number' && Number.isFinite(v);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const safeURL = v => { try { const u = new URL(v); return u.protocol === 'https:' && !u.username && !u.password ? u.href : null; } catch { return null; } };
  const link = (url, label) => safeURL(url) ? `<a href="${esc(safeURL(url))}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗<span class="sr-only"> (새 창)</span></a>` : '<span class="muted">링크 미확인</span>';
  const money = v => num(v) ? `${new Intl.NumberFormat('ko-KR', {maximumFractionDigits:2}).format(v / 100000000)}억원` : '미확인';
  const dateOnly = v => typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v);
  const kday = now => new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).format(now);
  // Validate before Date.parse: JavaScript otherwise normalizes dates such as February 30.
  // Date-only values remain calendar dates, never fabricated deadline timestamps.
  function scheduleDate(value) {
    if (typeof value !== 'string') return null;
    const match = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(Z|[+-]\d{2}:\d{2}))?$/.exec(value);
    if (!match) return null;
    const [, y, m, d, h, min, sec, zone] = match;
    const year = Number(y), month = Number(m), day = Number(d);
    const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    const days = [31,leap ? 29 : 28,31,30,31,30,31,31,30,31,30,31];
    if (year < 1 || month < 1 || month > 12 || day < 1 || day > days[month-1]) return null;
    if (h === undefined) return {day:value, instant:null};
    if (+h > 23 || +min > 59 || +sec > 59 || (zone !== 'Z' && (+zone.slice(1,3) > 23 || +zone.slice(4) > 59))) return null;
    const instant = Date.parse(value);
    return Number.isFinite(instant) ? {day:kday(new Date(instant)), instant} : null;
  }
  function date(v) {
    if (!scheduleDate(v)) return '미확인';
    if (dateOnly(v)) return v.replaceAll('-', '.') + ' (시간 미확인)';
    const d = new Date(v); return Number.isNaN(+d) ? '미확인' : new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(d);
  }
  function status(l, now = new Date()) {
    if (l.status === 'cancelled') return 'cancelled';
    if (l.status === 'closed') return 'closed';
    if (!['open','upcoming','unknown'].includes(l.status) || !Number.isFinite(+now)) return 'unknown';
    const start = scheduleDate(l.apply_start_at), end = scheduleDate(l.apply_end_at);
    // A missing boundary may establish upcoming/closed, but never establishes open.
    // Malformed or contradictory boundaries are not trusted at all.
    if (l.apply_start_at != null && !start || l.apply_end_at != null && !end) return 'unknown';
    if (start && end && (start.day > end.day || start.instant !== null && end.instant !== null && start.instant > end.instant)) return 'unknown';
    const today = kday(now);
    if (end) {
      if (end.instant === null) {
        if (today > end.day) return 'closed';
        if (today === end.day) return 'unknown';
      } else if (+now > end.instant) return 'closed'; // The backend includes the exact deadline instant.
    }
    if (start && (start.instant === null ? today < start.day : +now < start.instant)) return 'upcoming';
    return start && end ? 'open' : 'unknown';
  }
  function deadlineNote(l) {
    const end = scheduleDate(l.apply_end_at);
    const note = end && end.instant === null ? '마감 시각 미확인 · 정확한 마감 시각은 공식 공고에서 확인하세요.' : !end ? '마감 일정 미확인 · 공식 공고에서 확인하세요.' : '정확한 일정은 공식 공고에서 확인하세요.';
    return l.deadline_note ? `${l.deadline_note} · ${note}` : note;
  }
  const statusText = {open:'접수 중',upcoming:'접수 예정',closed:'모집 종료',cancelled:'취소',unknown:'일정 확인 필요'};
  function eligibility(l, scope = 'all') {
    const e = l.eligibility || {};
    if (e.yongin_status === 'ineligible') return 'excluded';
    if (e.yongin_status !== 'eligible' || !safeURL(e.evidence_url) || !e.evidence_text || !['both','mild_only','severe_only'].includes(e.disability_scope)) return 'check';
    if (scope === 'mild' && e.disability_scope === 'severe_only' || scope === 'severe' && e.disability_scope === 'mild_only') return 'excluded';
    return 'eligible';
  }
  const analyzed = u => num(u.sale_price_krw) && num(u.comparison_median_krw) && num(u.estimated_gap_krw) && num(u.gap_rate_pct) && ['high','medium','low'].includes(u.confidence);
  const confidence = {high:'높음',medium:'보통',low:'낮음',unavailable:'분석 불가'};
  function units(l, f = {}) { return arr(l.units).filter(u => (!f.area || num(u.area_sqm) && (f.area === 'small' ? u.area_sqm <= 60 : f.area === 'medium' ? u.area_sqm > 60 && u.area_sqm <= 85 : u.area_sqm > 85)) && (!f.price || (f.price === 'known' ? num(u.sale_price_krw) : !num(u.sale_price_krw)))); }
  function select(listings, f, view, now = new Date()) {
    return arr(listings).flatMap(l => {
      const s = status(l, now), e = eligibility(l, f.scope), history = ['closed','cancelled'].includes(s);
      if (view === 'history' ? !history || e === 'excluded' : view === 'ineligible' ? e !== 'excluded' : history || e === 'excluded') return [];
      if (f.search && !String(l.name || '').toLocaleLowerCase().includes(f.search.toLocaleLowerCase())) return [];
      if (f.region && (l.region || '미확인') !== f.region || f.status && s !== f.status || f.housing && (l.housing_type || 'unknown') !== f.housing) return [];
      const us = units(l,f);
      if ((f.area || f.price === 'known') && !us.length || f.price === 'unknown' && arr(l.units).length && !us.length) return [];
      return [{l,s,e,us}];
    });
  }
  function representative(row, sort) {
    const key = sort === 'rate' ? 'gap_rate_pct' : 'estimated_gap_krw';
    return [...row.us].sort((a,b) => (analyzed(b) ? b[key] : -Infinity) - (analyzed(a) ? a[key] : -Infinity))[0];
  }
  function compareDates(a, b, descending = false) {
    const left = scheduleDate(a), right = scheduleDate(b);
    if (!left || !right) return left ? -1 : right ? 1 : 0;
    const days = left.day.localeCompare(right.day);
    if (days) return descending ? -days : days;
    // Unknown times follow known times on the same day, without assigning a clock time.
    if (left.instant === null || right.instant === null) return left.instant !== null ? -1 : right.instant !== null ? 1 : 0;
    return descending ? right.instant - left.instant : left.instant - right.instant;
  }
  function sortRows(rows, sort) {
    return [...rows].sort((a,b) => {
      if (sort === 'deadline') return compareDates(a.l.apply_end_at,b.l.apply_end_at);
      if (sort === 'recent') return compareDates(a.l.notice_updated_at,b.l.notice_updated_at,true);
      const key = sort === 'rate' ? 'gap_rate_pct' : 'estimated_gap_krw', ua = representative(a,sort), ub = representative(b,sort);
      return (ub && analyzed(ub) ? ub[key] : -Infinity) - (ua && analyzed(ua) ? ua[key] : -Infinity) || String(a.l.name).localeCompare(String(b.l.name),'ko');
    });
  }
  function delayed(source, now = new Date()) { return !!source.last_success_at && Number.isFinite(Date.parse(source.last_success_at)) && +now - Date.parse(source.last_success_at) > 36 * 3600000; }
  const core = {money,date,status,deadlineNote,eligibility,analyzed,select,sortRows,safeURL,delayed};
  if (typeof module !== 'undefined' && module.exports) module.exports = core;
  if (typeof document === 'undefined') return;
  const $ = s => document.querySelector(s);
  let data = null, view = 'current', loaded = false, timeSignature = '', detailId = null, detailOpener = null;
  function filters() { return Object.fromEntries(new FormData($('#filters'))); }
  function empty(title, text) { return `<div class="empty"><strong>${esc(title)}</strong>${esc(text)}</div>`; }
  function render(now = new Date()) {
    if (!data) return;
    const f = filters(), sort = $('#sort').value;
    const rows = sortRows(select(data.listings,f,view,now),sort);
    $('#result-count').textContent = `검색 결과 ${rows.length}건 · 전체 ${data.listings.length}건`;
    const labels = {scope:'장애 정도',region:'지역',status:'모집 상태',area:'면적',price:'분양가',housing:'공급 유형'};
    $('#active-filters').textContent = Object.entries(f).filter(([k,v]) => v && v !== 'all').map(([k,v]) => k === 'search' ? `검색: ${v}` : `${labels[k]}: ${k === 'scope' ? (v === 'mild' ? '경증' : '중증') : $(`[name="${k}"] option:checked`).textContent}`).join(' · ') || '전체 조건 · 자격 미확인 공고는 별도로 표시합니다.';
    if (!rows.length) { $('#results').innerHTML = empty(data.listings.length ? '조건에 맞는 공고가 없습니다' : '등록된 공고가 없습니다',data.listings.length ? '필터를 조정하거나 종료·과거 공고를 확인해 보세요.' : '데이터 출처의 수집 상태를 함께 확인해 주세요.'); return; }
    const groups = view !== 'current' ? [{title:view === 'history' ? '종료·과거 공고' : '선택 조건의 지역·장애 정도 요건 제외',items:rows}] : [
      {title:'예상 시세차익 분석 완료',note:'표시한 주택형 기준 · 주변 거래 중앙값과 공식 분양금액의 차이',items:rows.filter(r=>r.e==='eligible' && r.us.some(analyzed))},
      {title:'분양가 확인 대기',note:'공식 가격과 주택형 연결이 확인되면 분석할 수 있습니다. 가격차 순위에 포함하지 않습니다.',items:rows.filter(r=>r.e==='eligible' && !r.us.some(analyzed) && !r.us.some(u=>num(u.sale_price_krw)))},
      {title:'분석 근거 부족',note:'분양가는 있으나 비교 거래 또는 분석 근거가 부족합니다.',items:rows.filter(r=>r.e==='eligible' && !r.us.some(analyzed) && r.us.some(u=>num(u.sale_price_krw)))},
      {title:'자격 확인 필요',note:'신청 불가를 의미하지 않습니다. 원문에서 지역·장애 정도별 요건을 확인하세요.',items:rows.filter(r=>r.e==='check')}
    ];
    $('#results').innerHTML = groups.map(g => `<section class="group"><div class="group-title"><h3>${esc(g.title)}</h3><span class="count">${g.items.length}</span></div>${g.note ? `<p class="group-note">${esc(g.note)}</p>` : ''}${g.items.length ? g.items.map((r,i) => card(r,i,sort,g.title === '예상 시세차익 분석 완료')).join('') : empty('확인된 공고가 없습니다','제공된 공식 데이터만 표시합니다.')}</section>`).join('');
  }
  function card(r,i,sort,ranked) {
    const {l,s,e} = r, u = representative(r,sort);
    const eText = e === 'eligible' ? ({both:'경증·중증 지역 요건 충족',mild_only:'경증 지역 요건 충족',severe_only:'중증 지역 요건 충족'}[l.eligibility.disability_scope]) : e === 'check' ? '자격 확인 필요' : '선택 요건 제외';
    return `<article class="listing"><div><span class="badge ${s}">${statusText[s]}</span><span class="badge ${e === 'check' ? 'check' : ''}">${eText}</span><h4><button type="button" data-detail="${esc(l.id)}">${ranked ? `${i+1}. ` : ''}${esc(l.name || '이름 미확인')}</button></h4><p>${esc(l.region || '지역 미확인')} · ${esc(l.district || '상세 지역 미확인')}</p><p>${u ? `${esc(u.type_id || '주택형 미확인')} · 전용 ${num(u.area_sqm) ? esc(u.area_sqm) + '㎡' : '면적 미확인'}` : '주택형 · 전용면적 확인 대기'}</p></div><div class="metric"><small>${u?.sale_price_basis === 'maximum_base_price' ? '주택형별 최고 분양금액' : '공식 분양금액'}</small><strong>${money(u?.sale_price_krw)}</strong><p>거래 중앙값 ${money(u?.comparison_median_krw)}</p>${u && analyzed(u) ? `<strong class="gap">${money(u.estimated_gap_krw)}</strong><p>차익률 ${esc(u.gap_rate_pct)}% · 신뢰도 ${confidence[u.confidence]}</p>` : '<p>가격차 분석 대기</p>'}</div><div class="metric"><small>기관추천 신청 마감</small><strong>${esc(date(l.apply_end_at))}</strong><p>${esc(deadlineNote(l))}</p></div><button type="button" data-detail="${esc(l.id)}" aria-label="${esc(l.name)} 상세 보기">상세 보기 ↗</button></article>`;
  }
  function details(id, now = new Date()) {
    const l = data.listings.find(x=>x.id===id); if (!l) return;
    detailId = id; detailOpener = document.activeElement;
    const e = l.eligibility || {};
    const fields = [['공급 위치',l.address || '미확인'],['모집 상태',statusText[status(l,now)]],['공급 유형',({private_apt:'민영 아파트',public_apt:'공공 아파트'})[l.housing_type] || '미확인'],['신청 시작',date(l.apply_start_at)],['신청 마감',date(l.apply_end_at)],['일정 안내',deadlineNote(l)],['게시일',date(l.notice_updated_at)],['데이터 확인',date(l.updated_at)]];
    $('#detail-content').innerHTML = `<h2 id="detail-title">${esc(l.name)}</h2><p>${link(l.notice_url,'공식 모집 공고 확인')}</p><dl>${fields.map(([a,b])=>`<dt>${a}</dt><dd${a === '모집 상태' ? ' id="detail-status"' : a === '일정 안내' ? ' id="detail-deadline-note"' : ''}>${esc(b)}</dd>`).join('')}</dl><h3>신청 자격과 판정 근거</h3><p>${eligibility(l)==='eligible' ? '용인시 거주자의 지역 요건 충족 · '+ ({both:'경증·중증',mild_only:'경증',severe_only:'중증'}[e.disability_scope]) : eligibility(l)==='check' ? '자격 확인 필요 · 미확인은 신청 불가를 의미하지 않습니다.' : '공고상 지역 요건 제외'}</p><p>${esc(e.evidence_text || '확인된 자격 근거 문장이 없습니다.')}</p><p>${link(e.evidence_url,'자격 근거 확인')}</p>${Array.isArray(e.conditions) ? `<ul>${e.conditions.map(c=>`<li>${esc(c)}</li>`).join('')}</ul>` : ''}<p>${esc(e.scoring_note || '선정 배점 정보 미확인')}</p><p class="notice">개인별 최종 자격과 선정 가능성을 보장하지 않습니다.</p><h3>주택형별 가격 및 실거래 비교</h3>${arr(l.units).length ? arr(l.units).map(unitDetail).join('') : empty('공식 주택형 연결 확인 대기','전용면적·장애인 배정물량·분양가·가격차를 임의 생성하지 않습니다.')}<h3>공식 첨부자료</h3>${arr(l.attachments).map(a=>`<p>${link(a.url,a.name || '첨부자료')} <span class="badge">${a.parse_status === 'parsed' ? '텍스트 추출됨 · 구조 검토 별도' : '문서 확인 필요'}</span></p>`).join('') || '<p>제공된 첨부자료가 없습니다.</p>'}<h3>공고 변경 이력</h3>${arr(l.notice_history).map(h=>`<p>${esc(date(h.published_on))} · ${esc(({initial:'최초 관찰',changed:'변경',correction:'정정',cancellation:'취소'})[h.change_type] || '유형 미확인')} · ${link(h.notice_url,'원문')}<br><span class="muted">관찰 ${esc(date(h.observed_at))}</span></p>`).join('') || '<p>제공된 변경 이력이 없습니다.</p>'}`;
    $('#detail').showModal(); $('#close-detail').focus();
  }
  function unitDetail(u) {
    return `<section class="unit"><h4>${esc(u.type_id || '주택형 미확인')} · 전용 ${num(u.area_sqm) ? esc(u.area_sqm)+'㎡' : '면적 미확인'}</h4><dl><dt>장애인 배정</dt><dd>${num(u.allocation_count) ? esc(u.allocation_count)+'세대' : '미확인'}</dd><dt>공식 분양금액</dt><dd>${money(u.sale_price_krw)} · ${esc(({maximum_base_price:'주택형별 최고 분양금액',exact_base_price:'공식 확인 기본금액'})[u.sale_price_basis] || '금액 기준 미확인')} ${link(u.sale_price_evidence_url,'가격 근거')}</dd><dt>거래 중앙값</dt><dd>${money(u.comparison_median_krw)}</dd><dt>예상 가격차</dt><dd>${money(u.estimated_gap_krw)} / ${num(u.gap_rate_pct) ? esc(u.gap_rate_pct)+'%' : '비율 미확인'}</dd><dt>분석 신뢰도</dt><dd>${confidence[u.confidence] || '미확인'} · ${num(u.comparables_count) ? u.comparables_count+'건' : '표본 수 미확인'}</dd></dl><p>${analyzed(u) ? '가격차 = 비교 거래 중앙값 − 공식 분양금액. 차익률 = 가격차 ÷ 분양금액 × 100.' : '분석 근거가 부족해 가격차를 제공하지 않습니다.'}</p>${u.analysis_reason ? `<p>백엔드 분석 사유: ${esc(u.analysis_reason)}</p>` : ''}<p class="muted">정책: 반경 2km · 면적 ±10% · 준공연도 차이 10년 이내 · 최근 6개월 최소 3건, 부족하면 12개월. 표본의 신뢰도이며 투자수익을 보장하지 않습니다.</p>${arr(u.comparables).map(t=>`<div class="trade"><strong>${esc(t.apartment_name || '이름 미확인')}</strong><p>${esc(date(t.trade_date))} · ${num(t.area_sqm) ? esc(t.area_sqm)+'㎡' : '면적 미확인'} · ${money(t.price_krw)}</p><p>${esc(t.location || '위치 미확인')} · ${num(t.distance_m) ? esc(t.distance_m)+'m' : '거리 미확인'} · 준공 ${esc(t.build_year || '미확인')}</p>${link(t.source_url,'거래 출처')}</div>`).join('') || '<p>제공된 비교 거래가 없습니다.</p>'}</section>`;
  }
  function renderMeta(now = new Date()) {
    const delayedSources = data.sources.filter(s=>delayed(s,now));
    const oldAttempt = Number.isFinite(Date.parse(data.generated_at)) && +now-Date.parse(data.generated_at)>36*3600000;
    const healthText = {ok:'정상 갱신',partial:'일부 자료 확인 대기',stale:'수집 실패 · 이전 자료 표시',error:'수집 오류'};
    $('#health').textContent = `${healthText[data.data_status] || '데이터 상태 확인 필요'}${oldAttempt || delayedSources.length ? ' · 36시간 이상 갱신 지연' : ''} — 미확인 자격·가격은 확정하지 않습니다. 신청 전 공식 공고를 확인하세요.`;
    $('#updated').textContent = `JSON 생성: ${date(data.generated_at)} · 전체 출처 마지막 정상 갱신: ${data.last_success_at ? date(data.last_success_at) : '아직 전체 정상 갱신 기록 없음'}`;
    const active = data.listings.filter(l=>eligibility(l)==='eligible');
    const current = active.filter(l=>['open','upcoming'].includes(status(l,now)));
    const nearest = [...current].filter(l=>l.apply_end_at).sort((a,b)=>compareDates(a.apply_end_at,b.apply_end_at))[0];
    const stats = [['접수 중',active.filter(l=>status(l,now)==='open').length,'단지'],['접수 예정',active.filter(l=>status(l,now)==='upcoming').length,'단지'],['차익 분석 가능',current.filter(l=>arr(l.units).some(analyzed)).length,'단지'],['가장 가까운 마감',nearest ? date(nearest.apply_end_at) : '확인된 일정 없음','']];
    $('#summary').innerHTML = stats.map(([a,b,c])=>`<article>${a}<strong>${esc(b)}<small>${c}</small></strong></article>`).join('');
    const sourceStatus = {ok:'정상',partial:'일부 수집 미완료',error:'수집 실패',not_configured:'연동 준비 필요',not_checked:'미확인'};
    $('#source-list').innerHTML = data.sources.map(s=>`<article class="source-card"><h3>${esc(s.name || '출처 미확인')}</h3><span class="badge check">${esc(sourceStatus[s.status] || '상태 미확인')}${delayed(s) ? ' · 36시간 초과 지연' : ''}</span><p>마지막 정상 갱신: ${esc(s.last_success_at ? date(s.last_success_at) : '정상 갱신 기록 없음')}</p><p>최근 확인: ${esc(date(s.checked_at))}<br>수집 건수: ${s.status === 'not_configured' || s.status === 'not_checked' || !num(s.records_count) ? '확인되지 않음' : esc(s.records_count)+'건'}</p>${s.error_code ? `<p>수집 상태 코드: ${esc(s.error_code)}</p>` : ''}${link(s.url,'공식 출처')}</article>`).join('') || empty('출처 정보 없음','제공된 수집 상태를 확인할 수 없습니다.');
  }
  async function load() {
    $('#reload').disabled = true; $('#results').setAttribute('aria-busy','true');
    $('#health').textContent = '공식 데이터를 불러오는 중입니다…';
    try {
      const response = await fetch('data/latest.json',{cache:'no-store',signal:AbortSignal.timeout(20000)});
      if (!response.ok) throw new Error('HTTP '+response.status);
      const raw = await response.json();
      if (!raw || raw.schema_version !== '1.0.0' || !Array.isArray(raw.listings)) throw new Error('지원하지 않는 데이터 형식');
      data = {...raw,listings:arr(raw.listings),sources:arr(raw.sources)};
      const previous = $('#filters [name="region"]').value;
      const regions = [...new Set(data.listings.map(l=>l.region || '미확인'))].sort((a,b)=>a.localeCompare(b,'ko'));
      $('#filters [name="region"]').innerHTML = '<option value="">전체 지역</option>'+regions.map(r=>`<option value="${esc(r)}">${esc(r)}</option>`).join('');
      if (regions.includes(previous)) $('#filters [name="region"]').value=previous;
      loaded=true; refreshCurrentTime(true);
    } catch (error) {
      $('#health').textContent = loaded ? '새 데이터 불러오기 실패 · 이전에 불러온 자료를 표시합니다.' : '데이터를 불러오지 못했습니다. 연결 상태를 확인하고 다시 시도해 주세요.';
      if (!loaded) { $('#results').innerHTML=empty('모집정보 로드 실패','아래의 데이터 다시 불러오기 버튼으로 재시도할 수 있습니다.'); $('#result-count').textContent='데이터 미확인 · 공고 0건을 의미하지 않습니다.'; }
    } finally { $('#reload').disabled=false; $('#results').setAttribute('aria-busy','false'); }
  }
  function refreshCurrentTime(force = false) {
    if (!data || !force && $('#reload').disabled) return;
    const now = new Date();
    const signature = JSON.stringify([kday(now),data.listings.map(l=>status(l,now)),data.sources.map(s=>delayed(s,now)),+now-Date.parse(data.generated_at)>36*3600000]);
    // Avoid rebuilding controls/focused links every tick when nothing has changed.
    if (force || signature !== timeSignature) {
      const focused = document.activeElement;
      const focusedId = focused?.dataset?.detail;
      renderMeta(now); render(now); timeSignature = signature;
      if (focusedId && !document.contains(focused)) {
        const replacement = [...document.querySelectorAll('[data-detail]')].find(b=>b.dataset.detail===focusedId);
        (replacement || $('#results')).focus({preventScroll:true});
      }
    }
    if ($('#detail').open) {
      const listing = data.listings.find(l=>l.id===detailId);
      if (listing) {
        $('#detail-status').textContent = statusText[status(listing,now)];
        $('#detail-deadline-note').textContent = deadlineNote(listing);
      }
    }
  }
  $('#filters').addEventListener('input',()=>refreshCurrentTime(true));
  $('#filters').addEventListener('reset',()=>{ setTimeout(()=>refreshCurrentTime(true),0); });
  $('#filters').addEventListener('submit',e=>e.preventDefault());
  $('#sort').addEventListener('change',()=>refreshCurrentTime(true));
  document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>{view=b.dataset.view;document.querySelectorAll('[data-view]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));refreshCurrentTime(true);}));
  $('#results').addEventListener('click',e=>{const b=e.target.closest('[data-detail]');if(b) details(b.dataset.detail);});
  $('#close-detail').addEventListener('click',()=>$('#detail').close());
  $('#detail').addEventListener('close',()=>{
    if (detailOpener && !document.contains(detailOpener)) {
      const replacement = [...document.querySelectorAll('[data-detail]')].find(b=>b.dataset.detail===detailId);
      (replacement || $('#results')).focus({preventScroll:true});
    }
    detailId = null; detailOpener = null;
  });
  $('#reload').addEventListener('click',load);
  setInterval(()=>refreshCurrentTime(),30000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden) refreshCurrentTime();});
  window.addEventListener('focus',()=>refreshCurrentTime());
  window.addEventListener('pageshow',()=>refreshCurrentTime());
  load();
})();
