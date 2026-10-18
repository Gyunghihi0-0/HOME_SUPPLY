// Synthetic notices are intercepted only in this test, never written to docs/data.
const {chromium}=require('playwright');
const http=require('node:http'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const real=JSON.parse(fs.readFileSync('docs/data/latest.json','utf8'));
const base=real.listings.find(l=>l.eligibility.yongin_status==='eligible');
const notice=(id,fields={})=>({...structuredClone(base),id,name:id,units:[],status:'upcoming',apply_start_at:'2026-10-18',apply_end_at:'2026-10-20',deadline_note:null,...fields});
const fixture={...real,listings:[
 notice('TEST_DATE'),
 notice('TEST_EXACT',{apply_start_at:'2026-10-18T09:00:00+09:00',apply_end_at:'2026-10-20T18:00:00+09:00'}),
 notice('TEST_CANCELLED',{status:'cancelled'}),
 notice('TEST_UNKNOWN',{status:'unknown',apply_start_at:null,apply_end_at:null}),
 notice('TEST_INVALID',{apply_start_at:'2026-02-30'}),
 notice('TEST_UNKNOWN_VALID',{status:'unknown'}),
 notice('TEST_REVERSED',{apply_start_at:'2026-10-21'})
]};
const prefix='/HOME_SUPPLY/',root=path.resolve('docs');
(async()=>{
 const serverErrors=[],requested=[];
 const server=http.createServer((req,res)=>{
  const u=new URL(req.url,'http://local');requested.push(u.pathname);
  if(!u.pathname.startsWith(prefix)){serverErrors.push(u.pathname);res.writeHead(404).end();return;}
  const p=path.resolve(root,u.pathname.slice(prefix.length)||'index.html');
  if(!p.startsWith(root+path.sep)){res.writeHead(403).end();return;}
  fs.readFile(p,(e,b)=>{if(e){serverErrors.push(u.pathname);res.writeHead(404).end();return;}const types={'.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.json':'application/json'};res.setHeader('Content-Type',types[path.extname(p)]||'text/html');res.end(b);});
 });
 await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
 try{
  browser=await chromium.launch({headless:true,channel:'msedge'});
  // Intentionally use a non-Korean browser timezone. All business dates must stay Korean.
  const page=await browser.newPage({timezoneId:'America/Los_Angeles',viewport:{width:390,height:844}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  await page.clock.install({time:new Date('2026-10-17T23:58:00+09:00')});
  await page.clock.pauseAt(new Date('2026-10-17T23:59:00+09:00'));
  await page.route('**/data/latest.json',r=>r.fulfill({json:fixture}));
  await page.goto(`http://127.0.0.1:${server.address().port}${prefix}`);
  await page.waitForFunction(()=>document.querySelector('#results').getAttribute('aria-busy')==='false');
  const stats=async(open,upcoming)=>{
   assert.equal(await page.locator('#summary article').nth(0).locator('strong').innerText(),open+'단지');
   assert.equal(await page.locator('#summary article').nth(1).locator('strong').innerText(),upcoming+'단지');
  };
  const badge=async(id,state)=>assert.equal(await page.locator('.listing').filter({has:page.locator(`h4 [data-detail="${id}"]`)}).locator('.badge').first().innerText(),state);
  const detail=async id=>{await page.locator(`h4 [data-detail="${id}"]`).click();assert.equal(await page.locator('#detail').evaluate(e=>e.open),true);};
  const tick=async time=>{await page.clock.setSystemTime(new Date(time));await page.clock.runFor(30001);};
  await stats(0,3);await badge('TEST_DATE','접수 예정');
  await detail('TEST_DATE');assert.equal(await page.locator('#detail-status').innerText(),'접수 예정');
  // Leave the dialog open over Korean midnight. A polling tick updates all surfaces.
  await tick('2026-10-18T00:00:00+09:00');
  await stats(2,1);await badge('TEST_DATE','접수 중');assert.equal(await page.locator('#detail-status').innerText(),'접수 중');
  assert.equal(await page.locator('#close-detail').evaluate(e=>e===document.activeElement),true);
  await page.keyboard.press('Escape');await page.locator('[name=status]').selectOption('open');assert.equal(await page.locator('.listing').count(),2);
  await detail('TEST_DATE');
  await tick('2026-10-19T12:00:00+09:00');await stats(3,0);assert.equal(await page.locator('.listing').count(),3);assert.equal(await page.locator('#detail-status').innerText(),'접수 중');
  await tick('2026-10-20T00:00:00+09:00');
  await stats(1,0);assert.equal(await page.locator('.listing').count(),1);await badge('TEST_EXACT','접수 중');
  assert.equal(await page.locator('#detail-status').innerText(),'일정 확인 필요');assert.match(await page.locator('#detail-deadline-note').innerText(),/마감 시각 미확인/);
  await page.keyboard.press('Escape');await page.waitForFunction(()=>document.activeElement===document.querySelector('#results'));
  await page.locator('[name=status]').selectOption('unknown');assert.equal(await page.locator('.listing').count(),5);await badge('TEST_DATE','일정 확인 필요');
  assert.match(await page.locator('.listing').filter({has:page.locator('h4 [data-detail="TEST_DATE"]')}).innerText(),/마감 시각 미확인/);
  await tick('2026-10-21T00:00:00+09:00');await stats(0,0);assert.equal(await page.locator('.listing').count(),3);
  await page.locator('[name=status]').selectOption('');await page.getByRole('button',{name:'종료·과거 공고'}).click();assert.equal(await page.locator('.listing').count(),4);await badge('TEST_CANCELLED','취소');await badge('TEST_DATE','모집 종료');
  // Frozen clock permits checking the exact deadline, including its final instant.
  await page.getByRole('button',{name:'현재 공고',exact:true}).click();
  await tick('2026-10-18T08:59:00+09:00');await stats(2,1);await badge('TEST_EXACT','접수 예정');
  await tick('2026-10-18T09:00:00+09:00');await stats(3,0);await badge('TEST_EXACT','접수 중');
  await page.clock.setSystemTime(new Date('2026-10-20T18:00:00+09:00'));
  await page.locator('[name=status]').selectOption('open');await stats(1,0);await badge('TEST_EXACT','접수 중');
  await page.clock.setSystemTime(new Date('2026-10-20T18:00:00.001+09:00'));
  await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await stats(0,0);assert.equal(await page.locator('.listing').count(),0);
  // Resume/background/page restore handlers must refresh even when timers were suspended.
  for(const event of ['visibilitychange','pageshow']){
   await page.clock.setSystemTime(new Date('2026-10-19T12:00:00+09:00'));
   await page.evaluate(name=>{if(name==='visibilitychange')document.dispatchEvent(new Event(name));else window.dispatchEvent(new Event(name));},event);
   await stats(3,0);assert.equal(await page.locator('.listing').count(),3);
   await page.clock.setSystemTime(new Date('2026-10-21T00:00:00+09:00'));await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await stats(0,0);
  }
  for(const width of [320,390,768,1440]){await page.setViewportSize({width,height:900});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);}
  assert.deepEqual(errors,[]);assert.deepEqual(serverErrors,[]);assert.ok(requested.includes(prefix+'assets/favicon.svg'));
  console.log('PASS: date-only and exact periods, Korean midnight in Los Angeles browser, missing/invalid/unknown/cancelled, list/detail/summary/filter consistency, open-dialog refresh and focus, polling/resume, Pages subpath, favicon, responsive widths; no console/resource errors');
 }finally{if(browser)await browser.close();server.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
