import puppeteer from 'puppeteer-core';import fs from 'node:fs';import assert from 'node:assert/strict';
const tokens=await (await fetch('http://127.0.0.1:8000/api/v1/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:'demo.admin@example.com',password:'DemoPass-2026'})})).json();
const browser=await puppeteer.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
try{
const page=await browser.newPage();
await page.evaluateOnNewDocument(t=>{localStorage.setItem("access_token",t.access_token);localStorage.setItem("refresh_token",t.refresh_token);localStorage.setItem("language","en");},tokens);
await page.goto('http://127.0.0.1:4185/deals',{waitUntil:'networkidle2'});
const token=await page.evaluate(()=>localStorage.getItem('access_token'));
async function api(path,method='GET',body){const r=await fetch('http://127.0.0.1:8000/api/v1'+path,{method,headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});assert.ok(r.ok,`${path}: ${r.status}`);return r.json();}
const account=(await api('/pipeline/accounts'))[0];
const deal=await api('/deals','POST',{title:'Advanced toggle demo '+Date.now(),customer_id:account.id,mcem_enabled:true});
const before=await api(`/deals/${deal.id}/mcem`);
await page.goto(`http://127.0.0.1:4185/deals/${deal.id}`,{waitUntil:'networkidle2'});
async function click(text){await page.waitForFunction(t=>[...document.querySelectorAll('button')].some(e=>e.textContent.trim()===t),{},text);for(const b of await page.$$('button'))if((await b.evaluate(e=>e.textContent.trim()))===text){await b.evaluate(e=>e.scrollIntoView({block:'center'}));await b.click();return;}throw Error('Missing '+text);}
fs.mkdirSync('e2e/out/disable-advanced',{recursive:true});
for(const width of [1440,390]){await page.setViewport({width,height:1000});await page.screenshot({path:`e2e/out/disable-advanced/${width}.png`,fullPage:true});}
await click('Turn off advanced features');
await page.waitForFunction(()=>[...document.querySelectorAll('button')].some(e=>e.textContent.trim()==='Turn on advanced pipeline'));
assert.equal((await api(`/deals/${deal.id}`)).mcem_enabled,false);
await page.reload({waitUntil:'networkidle2'});
await click('Turn on advanced pipeline');
await page.waitForFunction(()=>[...document.querySelectorAll('button')].some(e=>e.textContent.trim()==='Turn off advanced features'));
const after=await api(`/deals/${deal.id}/mcem`);assert.equal(after.journey.id,before.journey.id);assert.equal(after.milestones.length,before.milestones.length);
await page.setViewport({width:1440,height:1000});
console.log('PASS: desktop/mobile turn-off control, off survives reload, reenable reuses saved journey and milestones.');
}finally{await browser.close();}
