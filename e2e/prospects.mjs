import puppeteer from 'puppeteer-core';import fs from 'node:fs';import assert from 'node:assert/strict';
const port=fs.readFileSync('.playwright-cli/contacts-demo-chrome/DevToolsActivePort','utf8').split('\n')[0].trim();
const browser=await puppeteer.connect({browserURL:`http://127.0.0.1:${port}`,defaultViewport:null});
try {
const page=(await browser.pages()).find(p=>p.url().includes('4185'));assert.ok(page);
const errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.goto('http://127.0.0.1:4185/deals?new=1',{waitUntil:'networkidle2'});
await page.waitForSelector('#deal-form');await new Promise(r=>setTimeout(r,300));
const token=await page.evaluate(()=>localStorage.getItem('access_token'));
async function api(path,method='GET',body){const r=await fetch('http://127.0.0.1:8000/api/v1'+path,{method,headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});assert.ok(r.ok,`${path}: ${r.status}`);return r.status===204?null:r.json();}
const name='Prospect Browser Check '+Date.now();
await page.type('#deal-form input',name+' opportunity');await page.type('#deal-form input[role=combobox]',name);await page.keyboard.press('Tab');
const fields=await page.$$('#deal-form fieldset input:not([type=radio]):not([type=checkbox])');
await fields[0].type('Lerato Dube');await fields[1].type('lerato@example.com');await fields[2].type('082 555 0101');
await page.click('#deal-form input[type=checkbox]');
await page.click('button[form=deal-form]');await page.waitForFunction(()=>!document.querySelector('#deal-form'),{timeout:15000});
const accounts=await api('/pipeline/accounts');const prospect=accounts.find(c=>c.name===name);assert.equal(prospect.is_prospect,true);
assert.ok(!(await api('/customers?limit=200')).some(c=>c.id===prospect.id));
const deal=(await api('/deals?status=all')).find(d=>d.customer_id===prospect.id);assert.ok(deal?.contact_id);
await page.goto('http://127.0.0.1:4185/customers',{waitUntil:'networkidle2'});
assert.ok(!(await page.evaluate(()=>document.body.innerText)).includes(name));
await page.goto('http://127.0.0.1:4185/deals?new=1',{waitUntil:'networkidle2'});
await page.type('#deal-form input[role=combobox]',name);await page.keyboard.press('Tab');
await page.waitForFunction(()=>document.querySelector('#deal-form fieldset input')?.value==='Lerato Dube');
fs.mkdirSync('e2e/out/prospects',{recursive:true});
for(const width of [1440,390]){await page.setViewport({width,height:1000});await page.screenshot({path:`e2e/out/prospects/${width}.png`,fullPage:true});}
await api(`/deals/${deal.id}`,'PATCH',{stage:'won'});
assert.ok((await api('/customers?limit=200')).some(c=>c.id===prospect.id));
await page.goto('http://127.0.0.1:4185/customers',{waitUntil:'networkidle2'});
assert.ok((await page.evaluate(()=>document.body.innerText)).includes(name));
assert.deepEqual(errors,[]);
await page.setViewport({width:1440,height:1000});
await page.goto('http://127.0.0.1:4185/deals?new=1',{waitUntil:'networkidle2'});
console.log('PASS: new lead saved as prospect; hidden from Customers; reusable contact prefills; Won converts to visible customer; desktop/mobile rendered without errors.');
}finally{browser.disconnect();}
