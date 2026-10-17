// Run after ticket-qa-server.py and Vite on :5174. Emails are captured locally.
import puppeteer from 'puppeteer-core';
import fs from 'node:fs';
import assert from 'node:assert/strict';
import path from 'node:path';

const BASE = 'http://localhost:5174';
const OUT = 'e2e/out-ticket-qa';
fs.mkdirSync(OUT, { recursive: true });
const captureFile = `${OUT}/queued-emails.jsonl`;
const capturedBefore = fs.existsSync(captureFile) ? fs.readFileSync(captureFile, 'utf8').trim().split('\n').filter(Boolean).length : 0;
fs.writeFileSync(`${OUT}/browser-notes.txt`, 'Steps to reproduce: browser QA attachment.');
const browser = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: false, args: ['--proxy-server=direct://', '--proxy-bypass-list=*'] });
const page = await browser.newPage();
page.setDefaultTimeout(60000);
const errors = [];
page.on('pageerror', e => errors.push(e.message));
page.on('response', r => { if (r.url().includes(':8002/') && r.status() >= 500) errors.push(`${r.status()} ${r.url()}`); });
const clickText = async text => { const el = await page.waitForSelector(`button::-p-text(${text})`); await el.click(); };
const goto = async route => { await page.goto(BASE + route, { waitUntil: 'domcontentloaded', timeout: 90000 }); };
const api = (path, options = {}) => page.evaluate(async (path, options) => {
  const r = await fetch('http://localhost:8002/api/v1' + path, { ...options, headers: { Authorization: 'Bearer ' + localStorage.getItem('access_token'), 'Content-Type': 'application/json' } });
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
}, path, options);

try {
  await page.setViewport({ width: 1440, height: 1000 });
  await goto('/login');
  await page.type('#email', 'demo.admin@example.com');
  await page.type('#password', 'DemoPass-2026');
  await page.click('form button[type=submit]');
  await page.waitForFunction(() => location.pathname === '/');
  await page.waitForSelector('[aria-labelledby=welcome-title]', { timeout: 8000 }).catch(() => {});
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => !document.querySelector('[aria-labelledby=welcome-title]'));
  await new Promise(r => setTimeout(r, 1600));
  for (let i = 0; i < 12 && await page.$('[aria-labelledby=tour-title]'); i++) {
    await page.keyboard.press('Escape');
    await new Promise(r => setTimeout(r, 300));
  }
  await goto('/support');
  await clickText('New ticket');
  await page.waitForSelector('#ticket-form input');
  await page.type('#ticket-form input', 'Browser QA ticket with attachment');
  await page.type('#ticket-form textarea', 'Please investigate the attached reproduction steps.');
  const upload = await page.$('#ticket-form input[type=file]');
  await upload.uploadFile(`${OUT}/browser-notes.txt`);
  await page.click('button[form=ticket-form]');
  await page.waitForFunction(() => /\/support\/tickets\/[0-9a-f-]+$/.test(location.pathname));
  const id = new URL(page.url()).pathname.split('/').pop();
  await page.waitForSelector('section[aria-label="Ticket attachments"]');
  assert.equal((await api(`/support/tickets/${id}`)).attachments[0].filename, 'browser-notes.txt');
  const cdp = await page.createCDPSession();
  const downloads = path.resolve(OUT, 'downloads');
  fs.mkdirSync(downloads, { recursive: true });
  await cdp.send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: downloads });
  await page.click('section[aria-label="Ticket attachments"] button');
  for (let i = 0; i < 50 && !fs.existsSync(path.join(downloads, 'browser-notes.txt')); i++) await new Promise(r => setTimeout(r, 200));
  assert.equal(fs.readFileSync(path.join(downloads, 'browser-notes.txt'), 'utf8'), 'Steps to reproduce: browser QA attachment.');
  await page.screenshot({ path: `${OUT}/customer-desktop.png` });
  console.log('PASS ticket submission with attachment');

  await goto(`/admin/tickets/${id}`);
  await page.waitForSelector('textarea[aria-label="Reply text"]');
  await page.waitForSelector('form select option[value=progress_update]');
  await page.select('form select', 'progress_update');
  await page.waitForFunction(() => document.querySelector('textarea[aria-label="Reply text"]').value.includes('still working'));
  await clickText('Send reply');
  await page.waitForFunction(() => document.querySelector('textarea[aria-label="Reply text"]').value === '');
  console.log('PASS predefined reply');
  await clickText('Edit templates');
  await page.waitForSelector('[role=dialog] textarea');
  await new Promise(r => setTimeout(r, 350));
  await page.screenshot({ path: `${OUT}/template-editor.png` });
  await clickText('Save templates');
  await page.waitForFunction(() => !document.querySelector('[role=dialog]'));
  const status = await page.$('aside select');
  await status.select('in_progress');
  await page.waitForFunction(() => document.querySelector('aside select').disabled === false);
  await page.waitForFunction(() => document.querySelector('ol').innerText.includes("We're working on ticket"));
  const ticket = await api(`/support/tickets/${id}`);
  assert.equal(ticket.status, 'in_progress');
  await page.screenshot({ path: `${OUT}/admin-desktop.png` });
  console.log('PASS automatic status update and customer timeline');

  for (const [name, route] of [['admin', `/admin/tickets/${id}`], ['customer', `/support/tickets/${id}`]]) {
    await page.setViewport({ width: 390, height: 844 });
    await goto(route);
    await page.waitForSelector('section[aria-label="Ticket attachments"]');
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false, `${name}: overflow`);
    await page.screenshot({ path: `${OUT}/${name}-phone.png`, fullPage: true });
  }
  const captured = fs.readFileSync(captureFile, 'utf8').trim().split('\n').slice(capturedBefore).map(JSON.parse);
  const email = captured.filter(x => x.task.endsWith('send_platform_email_task')).map(x => x.args[0]);
  assert(email.some(x => x.subject.includes(`In Progress: #${ticket.number}`) && x.text.includes('Browser QA ticket')));
  assert(email.some(x => x.subject.includes(`Reply: #${ticket.number}`)));
  assert(email.some(x => x.subject.includes(`We've received your ticket #${ticket.number}`)));
  assert.deepEqual(errors, []);
  fs.writeFileSync(`${OUT}/result.json`, JSON.stringify({ passed: true, ticketId: id, errors, capturedEmails: email.length }, null, 2));
  console.log('PASS desktop/phone layouts and captured email; screenshots saved in ' + OUT);
  await page.setViewport({ width: 1440, height: 1000 });
  // Leave Chrome open for review, while allowing this script to finish.
  browser.disconnect();
  process.exit(0);
} catch (error) {
  console.error(error);
  await page.screenshot({ path: `${OUT}/failure.png` }).catch(() => {});
  browser.disconnect();
  process.exit(1);
}
