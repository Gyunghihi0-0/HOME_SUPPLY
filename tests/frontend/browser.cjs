// Run with bundled Node and NODE_PATH pointing to the bundled node_modules.
const {chromium}=require('playwright');
const http=require('node:http');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const output=process.env.TEST_ARTIFACT_DIR || path.join(require('node:os').tmpdir(),'home-supply-frontend');
fs.mkdirSync(output,{recursive:true});
(async()=>{
 const root=path.resolve('docs');
 const server=http.createServer((req,res)=>{const p=path.resolve(root,'.'+decodeURIComponent(req.url.split('?')[0]==='/'?'/index.html':req.url.split('?')[0]));if(!p.startsWith(root+path.sep)){res.writeHead(403).end();return;}fs.readFile(p,(e,b)=>{if(e){res.writeHead(404).end();return;}res.setHeader('Content-Type',p.endsWith('.js')?'text/javascript':p.endsWith('.css')?'text/css':p.endsWith('.json')?'application/json':p.endsWith('.svg')?'image/svg+xml':'text/html');res.end(b);});});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 let browser;
 try{
 browser=await chromium.launch({headless:true,channel:'msedge'});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[],consoleErrors=[],resourceErrors=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text());});page.on('response',r=>{if(r.status()>=400)resourceErrors.push(r.url());});
 await page.goto(`http://127.0.0.1:${server.address().port}`);await page.waitForFunction(()=>document.querySelector('#results').getAttribute('aria-busy')==='false');
 assert.ok(await page.locator('.listing').count()>0);assert.match(await page.locator('#health').innerText(),/일부 자료/);
 await page.screenshot({path:path.join(output,'desktop.png'),fullPage:true});
 await page.getByRole('radio',{name:'경증',exact:true}).check();assert.ok(await page.locator('.listing').count()>0);
 await page.getByRole('radio',{name:'중증',exact:true}).check();assert.ok(await page.locator('.listing').count()>0);
 await page.locator('[name=search]').fill('존재하지않는검색조건');assert.equal(await page.locator('.listing').count(),0);
 await page.getByRole('button',{name:'조건 초기화'}).click();await page.waitForFunction(()=>document.querySelectorAll('.listing').length>0);
 const first=page.locator('[data-detail]').first();await first.focus();await page.keyboard.press('Enter');assert.equal(await page.locator('#detail').evaluate(e=>e.open),true);await page.keyboard.press('Escape');assert.equal(await page.locator('#detail').evaluate(e=>e.open),false);assert.equal(await first.evaluate(e=>e===document.activeElement),true);
 await page.getByRole('button',{name:'종료·과거 공고'}).click();assert.ok(await page.locator('.listing').count()>0);
 await page.setViewportSize({width:390,height:844});await page.getByRole('button',{name:'현재 공고',exact:true}).click();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 await page.screenshot({path:path.join(output,'mobile.png'),fullPage:false});
 await page.locator('[data-detail]').first().click();assert.equal(await page.locator('#detail').evaluate(e=>e.scrollWidth>e.clientWidth),false);await page.screenshot({path:path.join(output,'mobile-detail.png')});await page.keyboard.press('Escape');
 assert.deepEqual(consoleErrors,[]);assert.deepEqual(resourceErrors,[]);
 await page.route('**/data/latest.json',r=>r.fulfill({status:500,body:'fail'}));await page.getByRole('button',{name:'데이터 다시 불러오기'}).click();await page.waitForFunction(()=>!document.querySelector('#reload').disabled);assert.match(await page.locator('#health').innerText(),/이전에 불러온/);
 await page.reload();await page.waitForFunction(()=>!document.querySelector('#reload').disabled);assert.match(await page.locator('#results').innerText(),/로드 실패/);
 assert.deepEqual(errors,[]);console.log('PASS: actual JSON, search/reset, severity, history, dialog keyboard/focus, mobile overflow, reload failure, initial failure; no browser errors');
 }finally{if(browser)await browser.close();server.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
