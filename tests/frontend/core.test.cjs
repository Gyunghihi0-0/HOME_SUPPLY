const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const c = require('../../docs/app.js');
const now = new Date('2026-10-18T10:00:00+09:00');
const eligible = {yongin_status:'eligible',disability_scope:'both',evidence_url:'https://example.org',evidence_text:'test evidence'};
const unit = {type_id:'TEST',sale_price_krw:500000000,comparison_median_krw:600000000,estimated_gap_krw:100000000,gap_rate_pct:20,confidence:'low',area_sqm:84};
const listing = {id:'TEST_ONLY',name:'TEST_ONLY',status:'open',eligibility:eligible,units:[unit]};
test('null and invalid numbers never become zero prices',()=>{for(const v of [null,undefined,'0',NaN]) assert.equal(c.money(v),'미확인');assert.equal(c.money(0),'0억원');assert.equal(c.money(-100000000),'-1억원');});
test('date-only deadlines respect Korea and never invent closing time',()=>{assert.equal(c.status({...listing,apply_end_at:'2026-10-18'},now),'unknown');assert.equal(c.status({...listing,apply_end_at:'2026-10-17'},now),'closed');assert.equal(c.date('2026-10-18'),'2026.10.18 (시간 미확인)');assert.equal(c.status({...listing,apply_end_at:'2026-10-18T09:00:00+09:00'},now),'closed');});
test('unknown eligibility remains visible in mild and severe filters',()=>{const unknown={...listing,eligibility:{}};for(const scope of ['all','mild','severe']){assert.equal(c.select([unknown],{scope},'current',now).length,1);assert.equal(c.eligibility(unknown,scope),'check');}assert.equal(c.eligibility({...listing,eligibility:{...eligible,evidence_text:null}}),'check');});
test('severity and excluded eligibility do not leak into eligible results',()=>{assert.equal(c.select([{...listing,eligibility:{...eligible,disability_scope:'severe_only'}}],{scope:'mild'},'current',now).length,0);assert.equal(c.select([{...listing,eligibility:{...eligible,yongin_status:'ineligible'}}],{},'ineligible',now).length,1);});
test('combined filters require a single matching unit',()=>{const l={...listing,region:'TEST',units:[{...unit,area_sqm:50,sale_price_krw:null},{...unit,area_sqm:100}]};assert.equal(c.select([l],{region:'TEST',area:'small',price:'known'},'current',now).length,0);assert.equal(c.select([l],{search:'test',region:'TEST',area:'large',price:'known'},'current',now).length,1);});
test('gap sorting includes negative values and puts missing analysis last',()=>{const rows=[-200, null,100,0].map((gap,i)=>({l:{name:String(i)},us:[{...unit,estimated_gap_krw:gap}]}));assert.deepEqual(c.sortRows(rows,'gap').map(r=>r.us[0].estimated_gap_krw),[100,0,-200,null]);});
test('closed and cancelled records appear only in history',()=>{for(const status of ['closed','cancelled']){const l={...listing,status};assert.equal(c.select([l],{},'current',now).length,0);assert.equal(c.select([l],{},'history',now).length,1);}});
test('unknown fields and dangerous links are handled safely',()=>{assert.equal(c.status({},now),'unknown');assert.equal(c.select([{}],{},'current',now).length,1);for(const url of ['javascript:alert(1)','http://example.org','https://u:p@example.org',null]) assert.equal(c.safeURL(url),null);});
test('source freshness uses successful update, not last attempt',()=>{assert.equal(c.delayed({last_success_at:'2026-10-16T10:00:00+09:00',checked_at:now.toISOString()},now),true);assert.equal(c.delayed({last_success_at:null},now),false);});
test('real operating snapshot renders without fabricated analysis',()=>{const d=JSON.parse(fs.readFileSync('docs/data/latest.json','utf8'));assert.equal(d.schema_version,'1.0.0');assert.ok(d.listings.length>0);for(const scope of ['all','mild','severe']){const rows=c.select(d.listings,{scope},'current',now);assert.ok(rows.length>0);for(const row of rows)assert.ok(d.listings.includes(row.l));}assert.ok(d.listings.every(l=>!l.units.some(c.analyzed)));});

const period = {...listing,status:'upcoming',apply_start_at:'2026-10-18',apply_end_at:'2026-10-20'};
for(const [time,expected] of [
  ['2026-10-17T23:59:59.999+09:00','upcoming'],
  ['2026-10-18T00:00:00+09:00','open'],
  ['2026-10-19T12:00:00+09:00','open'],
  ['2026-10-19T23:59:59.999+09:00','open'],
  ['2026-10-20T00:00:00+09:00','unknown'],
  ['2026-10-20T23:59:59.999+09:00','unknown'],
  ['2026-10-21T00:00:00+09:00','closed'],
  ['2026-10-17T15:00:00Z','open'],
  ['2026-10-19T15:00:00Z','unknown'],
  ['2026-10-20T15:00:00Z','closed']
]) test(`date-only period at ${time} is ${expected}`,()=>assert.equal(c.status(period,new Date(time)),expected));

const exactPeriod = {...period,apply_start_at:'2026-10-18T09:00:00+09:00',apply_end_at:'2026-10-20T18:00:00+09:00'};
for(const [time,expected] of [
  ['2026-10-18T08:59:59.999+09:00','upcoming'],
  ['2026-10-18T09:00:00+09:00','open'],
  ['2026-10-20T17:59:59.999+09:00','open'],
  ['2026-10-20T18:00:00+09:00','open'],
  ['2026-10-20T18:00:00.001+09:00','closed'],
  ['2026-10-20T09:00:00.001Z','closed']
]) test(`exact period at ${time} is ${expected}`,()=>assert.equal(c.status(exactPeriod,new Date(time)),expected));

test('cancelled and explicitly closed notices are never reopened',()=>{
  for(const state of ['cancelled','closed'])for(const t of ['2026-10-17','2026-10-19','2026-10-21'])assert.equal(c.status({...period,status:state},new Date(t+'T12:00:00+09:00')),state);
});
test('unknown notices require a valid complete period before becoming open',()=>{
  assert.equal(c.status({...period,status:'unknown'},new Date('2026-10-19T12:00:00+09:00')),'open');
  for(const fields of [{},{apply_start_at:null},{apply_end_at:null},{apply_start_at:null,apply_end_at:null}]){
    const l=Object.keys(fields).length ? {...period,...fields,status:'unknown'} : {status:'unknown'};
    assert.equal(c.status(l,new Date('2026-10-19T12:00:00+09:00')),'unknown');
  }
  assert.equal(c.status({...period,status:'new_enum'},now),'unknown');
});
test('missing boundaries never fall back to stored open or upcoming',()=>{
  for(const state of ['open','upcoming','unknown']){
    assert.equal(c.status({...period,status:state,apply_end_at:null},new Date('2026-10-19T12:00:00+09:00')),'unknown');
    assert.equal(c.status({...period,status:state,apply_start_at:null},new Date('2026-10-19T12:00:00+09:00')),'unknown');
  }
});
test('invalid dates, time zones and reversed periods stay unknown',()=>{
  for(const value of ['',0,{},'not-a-date','2026-02-29','2026-02-30','2026-04-31','2026-13-01','2026-00-10','2026-10-00','0000-10-18','2026-10-18T09:00:00','2026-10-18T24:00:00+09:00','2026-10-18T09:60:00+09:00','2026-10-18T09:00:60+09:00','2026-10-18T09:00:00+24:00']) {
    for(const field of ['apply_start_at','apply_end_at']) assert.equal(c.status({...period,[field]:value},now),'unknown',field+' '+JSON.stringify(value));
    assert.equal(c.date(value),'미확인');
  }
  assert.equal(c.status({...period,apply_start_at:'2026-10-21'},now),'unknown');
  assert.equal(c.status({...exactPeriod,apply_start_at:'2026-10-20T19:00:00+09:00'},now),'unknown');
  assert.equal(c.status(period,new Date('invalid')),'unknown');
});
test('mixed dates and timestamps use Korean calendar days',()=>{
  const l={...period,apply_start_at:'2026-10-17T15:30:00Z'};
  assert.equal(c.status(l,new Date('2026-10-18T00:29:59+09:00')),'upcoming');
  assert.equal(c.status(l,new Date('2026-10-18T00:30:00+09:00')),'open');
  assert.equal(c.status(l,new Date('2026-10-20T00:00:00+09:00')),'unknown');
  assert.equal(c.status({...period,apply_end_at:'2026-10-19T15:30:00Z'},new Date('2026-10-20T00:29:59+09:00')),'open');
});
test('leap days are validated rather than normalized',()=>{
  assert.equal(c.status({...period,apply_start_at:'2024-02-29',apply_end_at:'2024-03-02'},new Date('2024-03-01T00:00:00+09:00')),'open');
  assert.equal(c.date('2100-02-29'),'미확인');assert.equal(c.date('2000-02-29'),'2000.02.29 (시간 미확인)');
});
test('date-only deadline guidance retains backend note without inventing time',()=>{
  const note=c.deadlineNote({...period,deadline_note:'기관 공고 확인 필요'});
  assert.match(note,/기관 공고 확인 필요/);assert.match(note,/마감 시각 미확인/);assert.doesNotMatch(note,/18:00|23:59/);
});
test('status filters and history share the same current-time classification',()=>{
  for(const [time,state] of [['2026-10-17','upcoming'],['2026-10-19','open'],['2026-10-20','unknown'],['2026-10-21','closed']]){
    const at=new Date(time+'T12:00:00+09:00');
    for(const filter of ['upcoming','open','unknown','closed'])assert.equal(c.select([period],{status:filter},state==='closed'?'history':'current',at).length,filter===state?1:0);
  }
});
test('date sorting never fabricates a deadline time and missing dates sort last',()=>{
  const rows=[null,'2026-10-20','2026-10-18T10:00:00+09:00','2026-10-18T09:00:00+09:00','bad'].map(v=>({l:{apply_end_at:v,notice_updated_at:v}}));
  assert.deepEqual(c.sortRows(rows,'deadline').map(r=>r.l.apply_end_at),['2026-10-18T09:00:00+09:00','2026-10-18T10:00:00+09:00','2026-10-20',null,'bad']);
  assert.deepEqual(c.sortRows(rows,'recent').map(r=>r.l.notice_updated_at),['2026-10-20','2026-10-18T10:00:00+09:00','2026-10-18T09:00:00+09:00',null,'bad']);
  const sameDay=['2026-10-18T10:00:00+09:00','2026-10-18','2026-10-18T09:00:00+09:00'].map(v=>({l:{apply_end_at:v}}));
  assert.deepEqual(c.sortRows(sameDay,'deadline').map(r=>r.l.apply_end_at),['2026-10-18T09:00:00+09:00','2026-10-18T10:00:00+09:00','2026-10-18']);
});
