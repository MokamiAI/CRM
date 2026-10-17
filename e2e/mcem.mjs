// Local-only MCEM operating journey. Start ticket-qa-server.py and Vite :5174.
import puppeteer from 'puppeteer-core';
import fs from 'node:fs';
import assert from 'node:assert/strict';

const BASE = process.env.MCEM_WEB || 'http://localhost:5174';
const API = process.env.MCEM_API || 'http://localhost:8002/api/v1';
for (const url of [BASE, API]) assert(['localhost', '127.0.0.1'].includes(new URL(url).hostname), 'Local QA only');
const OUT = 'e2e/out-mcem';
fs.mkdirSync(OUT, { recursive: true });
const browser = await puppeteer.launch({ executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: false, args: ['--proxy-server=direct://', '--proxy-bypass-list=*'] });
const page = await browser.newPage();
page.setDefaultTimeout(20000);
const errors = [];
page.on('pageerror', e => errors.push(e.message));
page.on('response', r => { if (r.url().startsWith(API) && r.status() >= 500) errors.push(`${r.status()} ${r.url()}`); });
const api = (route, method = 'GET', body) => page.evaluate(async (url, method, body) => {
  const r = await fetch(url, { method, headers: { Authorization: 'Bearer ' + localStorage.getItem('access_token'), 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
  const data = await r.json();
  if (!r.ok) throw new Error(`${r.status} ${url}: ${JSON.stringify(data)}`);
  return data;
}, API + route, method, body);
const click = async (label, root = 'body') => {
  await page.waitForFunction((root, label) => [...document.querySelectorAll(root + ' button')].some(b => b.textContent.trim() === label && b.getBoundingClientRect().height > 0), {}, root, label);
  for (const button of await page.$$(root + ' button')) if (await button.evaluate((el, text) => el.textContent.trim() === text, label)) { await button.click(); return; }
  throw new Error('Missing button: ' + label);
};
const fill = async (selector, value) => { await page.waitForSelector(selector); await page.focus(selector); await page.keyboard.down('Control'); await page.keyboard.press('A'); await page.keyboard.up('Control'); await page.keyboard.type(value); };
const goto = route => page.goto(BASE + route, { waitUntil: 'domcontentloaded', timeout: 60000 });
let deal, note;
const today = new Date().toLocaleDateString('en-CA', { timeZone: 'Africa/Johannesburg' });
const tomorrow = new Date(Date.now() + 86400000).toLocaleDateString('en-CA', { timeZone: 'Africa/Johannesburg' });
const confirm = async key => {
  await api(`/deals/${deal.id}/mcem/milestones/${key}/evidence`, 'POST', { kind: 'note', ref_id: note.id, explanation: 'Customer workshop confirmation for ' + key, occurred_on: today });
  await api(`/deals/${deal.id}/mcem/milestones/${key}`, 'PATCH', { status: 'confirmed', confirmed_on: today, summary: 'Customer reviewed the result and agreed the next action.' });
};
async function screenshots(label) {
  await page.evaluate(() => document.querySelector('aside.quote-week button[aria-label]')?.click());
  await new Promise(r => setTimeout(r, 300));
  for (const [suffix, width, height] of [['desktop', 1440, 1000], ['phone', 390, 844]]) {
    await page.setViewport({ width, height });
    await new Promise(r => setTimeout(r, 250));
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false, label + ': sideways scrolling');
    await page.screenshot({ path: `${OUT}/${label}-${suffix}.png`, fullPage: true });
  }
  await page.setViewport({ width: 1440, height: 1000 });
}

try {
  await page.setViewport({ width: 1440, height: 1000 });
  await goto('/login');
  await page.waitForSelector('#email');
  await page.type('#email', 'demo.admin@example.com');
  await page.type('#password', 'DemoPass-2026');
  await page.click('form button[type=submit]');
  await page.waitForFunction(() => location.pathname === '/');
  await page.waitForSelector('[aria-labelledby=welcome-title]', { timeout: 5000 }).catch(() => {});
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => !document.querySelector('[aria-labelledby=welcome-title]'));
  await new Promise(r => setTimeout(r, 1500));
  for (let i = 0; i < 12 && await page.$('[aria-labelledby=tour-title]'); i++) { await page.keyboard.press('Escape'); await new Promise(r => setTimeout(r, 250)); }
  const customer = await api('/customers', 'POST', { name: 'MCEM Procurement QA ' + Date.now() });
  const contact = await api(`/customers/${customer.id}/contacts`, 'POST', { first_name: 'Lerato', email: 'lerato@example.com' });
  deal = await api('/deals', 'POST', { title: 'Procurement workflow — MCEM local QA', customer_id: customer.id, contact_id: contact.id, value: '25000' });
  note = await api('/notes', 'POST', { deal_id: deal.id, body: 'Customer workshop: agreed problem, requirements, solution direction and acceptance criteria.' });
  await api('/activities', 'POST', { deal_id: deal.id, type: 'meeting', subject: 'Review workflow with Lerato', due_date: tomorrow });
  await goto(`/deals/${deal.id}`);
  await click('Turn on advanced pipeline');
  await page.waitForSelector('details[data-milestone=fit]');
  await click('Qualified', '[role=group]');
  await page.waitForFunction(() => document.body.innerText.includes('Confirm: Solution fit established'));
  console.log('PASS missing evidence blocks the commercial stage');
  await click('Qualification & handover');
  for (const [name, value] of Object.entries({ qualification_reason: 'Manual tender preparation is a fit for our workflow', decision_process: 'Procurement director approves after the workshop', scope: 'Tender preparation workflow and training', commitments: 'Configure workflow and train five users', success_measure: 'Hours per tender', baseline: '12', target: '4', unit: 'hours per tender' })) await fill(`[name=${name}]`, value);
  await page.$eval('[name=next_review_date]', (e, value) => { const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; setter.call(e, value); e.dispatchEvent(new Event('input', { bubbles: true })); }, tomorrow);
  await click('Save customer journey');
  await page.waitForFunction(() => document.body.innerText.includes('Customer journey saved'));
  await click('Milestones');
  await page.click('details[data-milestone=fit] > summary');
  const root = 'details[data-milestone=fit]';
  await page.waitForSelector(root + ' select[name=evidence_source] option[value="note:' + note.id + '"]');
  await page.select(root + ' select[name=evidence_source]', 'note:' + note.id);
  await fill(root + ' [name=evidence_explanation]', 'Lerato confirmed the procurement need and solution fit in the workshop.');
  await click('Link customer evidence', root);
  await page.waitForFunction(() => document.querySelector('details[data-milestone=fit]').innerText.includes('Lerato confirmed'));
  await page.select(root + ' select[name=status]', 'confirmed');
  await page.$eval(root + ' input[name=confirmed_on]', (e, value) => { const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; setter.call(e, value); e.dispatchEvent(new Event('input', { bubbles: true })); }, today);
  await click('Save milestone', root);
  await page.waitForFunction(() => document.querySelector('details[data-milestone=fit] > summary').innerText.includes('Confirmed'));
  await click('Qualified', '[role=group]');
  await page.waitForFunction(() => document.querySelector('button[aria-current=step]')?.innerText === 'Qualified');
  console.log('PASS evidence selection, confirmation and Qualified transition in the UI');
  await screenshots('qualified-milestones');
  for (const [stage, keys] of [['proposal', ['problem', 'outcome', 'solution']], ['negotiation', ['validation', 'proposal_review']], ['won', ['agreement']]]) {
    for (const key of keys) await confirm(key);
    await api(`/deals/${deal.id}`, 'PATCH', { stage });
  }
  await goto(`/deals/${deal.id}`);
  await page.waitForSelector('details[data-milestone=delivery]');
  assert.equal((await api(`/deals/${deal.id}/mcem`)).journey.state, 'active');
  await screenshots('won-delivery');
  await confirm('delivery'); await confirm('adoption');
  await api(`/deals/${deal.id}/mcem/journey`, 'PATCH', { actual: '5' });
  await confirm('value');
  await goto(`/deals/${deal.id}`);
  await page.waitForFunction(() => document.querySelector('[aria-label="Customer progress"]')?.innerText.includes('Manage and Optimize'));
  await click('Customer journey');
  await screenshots('customer-journey');
  await click('History');
  await screenshots('history');
  await click('Customer journey');
  await click('Create expansion opportunity');
  await fill('[name=expansion_title]', 'Supplier onboarding expansion');
  await click('Create Lead');
  await page.waitForFunction(original => location.pathname.startsWith('/deals/') && !location.pathname.endsWith(original), {}, deal.id);
  const expansion = await api('/deals/' + new URL(page.url()).pathname.split('/').pop());
  assert.equal(expansion.stage, 'lead'); assert.equal(expansion.parent_deal_id, deal.id);
  assert.equal((await api(`/deals/${deal.id}`)).stage, 'won');
  await goto('/deals');
  await page.waitForFunction(() => document.body.innerText.includes('Customer progress attention'));
  assert.deepEqual(errors, []);
  fs.writeFileSync(`${OUT}/result.json`, JSON.stringify({ passed: true, originalDealId: deal.id, expansionDealId: expansion.id, errors }, null, 2));
  console.log('PASS Won journey, value phase, expansion Lead, desktop/phone layouts and reporting');
  await goto(`/deals/${deal.id}`);
  browser.disconnect(); process.exit(0);
} catch (error) {
  console.error(error);
  await page.screenshot({ path: `${OUT}/failure.png`, fullPage: true }).catch(() => {});
  browser.disconnect(); process.exit(1);
}
