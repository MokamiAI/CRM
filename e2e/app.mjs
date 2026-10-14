// Browser regression for the signed-in app, against a LOCAL YGT seeded by
// backend/scripts/seed_demo.py. Opens every page (laptop and phone),
// fails on page errors or "couldn't load", saves screenshots, and runs the
// quote → draft invoice flow.
//
//   node e2e/app.mjs [outDir]       (site on :4173, API on :8000)
//
// Refuses to run against anything but localhost.
import puppeteer from "puppeteer-core";
import fs from "fs";
import path from "path";

const BASE = process.env.YGT_WEB || "http://localhost:4173";
const API = process.env.YGT_API || "http://localhost:8000/api/v1";
const OUT = process.argv[2] || "e2e/out";
const CHROME = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const EMAIL = "demo.admin@example.com";
const PASSWORD = "DemoPass-2026";
if (!/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(BASE)) throw new Error(`Refusing: ${BASE} is not local`);

const wait = (ms) => new Promise((r) => setTimeout(r, ms));
for (const d of ["laptop", "phone"]) fs.mkdirSync(path.join(OUT, d), { recursive: true });
const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ["--proxy-server=direct://", "--proxy-bypass-list=*"] });
const page = await browser.newPage();
const problems = [];
page.on("pageerror", (e) => problems.push(`${page.url()}: ${e.message}`));
page.on("response", (r) => r.url().includes("/api/v1/") && r.status() >= 500 && problems.push(`${r.status()} ${r.url()}`));

async function settle() {
  try {
    await page.waitForNetworkIdle({ idleTime: 500, timeout: 4000 });
  } catch {
    /* polling pages */
  }
  for (let i = 0; i < 60; i++) {
    const loading = await page.evaluate(() => [...document.querySelectorAll(".animate-pulse")].some((n) => n.offsetParent && n.getBoundingClientRect().width > 24));
    if (!loading) break;
    await wait(250);
  }
  await page.evaluate(() => document.querySelector("aside.quote-week button[aria-label]")?.click());
  await wait(400);
}

// Sign in through the form, as a person would.
await page.setViewport({ width: 1440, height: 900 });
await page.goto(BASE + "/login", { waitUntil: "networkidle2" });
await page.evaluate(() => localStorage.setItem("language", "en"));
await page.reload({ waitUntil: "networkidle2" });
await page.type("#email", EMAIL);
await page.type("#password", PASSWORD);
await Promise.all([page.waitForFunction(() => location.pathname === "/", { timeout: 20000 }), page.click("form button[type=submit]")]);
// The first sign-in shows the tour; close it (Escape) so pages are visible.
await wait(1500);
for (let i = 0; i < 12 && (await page.$("[aria-labelledby=tour-title]")); i++) {
  await page.keyboard.press("Escape");
  await wait(400);
}

const results = [];
let n = 0;
async function visit(route, name) {
  n += 1;
  const file = `${String(n).padStart(2, "0")} ${name}.png`;
  const issues = [];
  for (const [dir, w, h, mobile] of [["laptop", 1440, 900, false], ["phone", 390, 844, true]]) {
    await page.setViewport({ width: w, height: h, isMobile: mobile, hasTouch: mobile, deviceScaleFactor: mobile ? 2 : 1 });
    await page.goto(BASE + route, { waitUntil: "domcontentloaded" });
    await settle();
    const text = await page.evaluate(() => document.body.innerText);
    if (/Couldn't load this|Something went wrong/.test(text)) issues.push(`${dir}: error message on page`);
    if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)) issues.push(`${dir}: page scrolls sideways`);
    const height = await page.evaluate(() => {
      const main = document.querySelector("main");
      const extra = main && main.scrollHeight > main.clientHeight + 4 ? main.scrollHeight - main.clientHeight : 0;
      return Math.min(Math.max(document.documentElement.scrollHeight, innerHeight + extra), 9000);
    });
    if (height > h) await page.setViewport({ width: w, height, isMobile: mobile, hasTouch: mobile, deviceScaleFactor: mobile ? 2 : 1 });
    await wait(300);
    await page.screenshot({ path: path.join(OUT, dir, file) });
  }
  results.push({ name, route, issues });
}
// Ask the API (as the signed-in user) for a record's id, where the page
// opens records with a button rather than a link.
const apiFirst = (path) =>
  page.evaluate(
    async (url) => {
      const res = await fetch(url, { headers: { Authorization: `Bearer ${localStorage.getItem("access_token")}` } });
      const rows = res.ok ? await res.json() : [];
      return rows[0]?.id || null;
    },
    API + path
  );

async function firstLink(list, re) {
  await page.setViewport({ width: 1440, height: 900 });
  await page.goto(BASE + list, { waitUntil: "domcontentloaded" });
  await settle();
  return page.evaluate((src) => [...document.querySelectorAll("a[href]")].map((a) => a.getAttribute("href")).find((h) => new RegExp(src).test(h)) || null, re.source);
}

const ID = "[0-9a-f-]{36}";
const pages = [
  ["/", "Dashboard"],
  ["/customers", "Customers"],
  ["@/customers", new RegExp(`^/customers/${ID}$`), "Customer detail"],
  ["@/customers", new RegExp(`^/customers/${ID}$`), "Customer statement", "/statement"],
  ["/deals", "Deals"],
  ["/discovery", "Discovery"],
  ["@/deals", new RegExp(`^/deals/${ID}$`), "Deal detail"],
  ["/quotes", "Quotes"],
  ["/quotes/new", "New quote"],
  ["@/quotes", new RegExp(`^/quotes/${ID}$`), "Quote detail"],
  ["/invoices", "Invoices"],
  ["/invoices/new", "New invoice"],
  ["/invoices/aging", "Who owes you"],
  ["/invoices/recurring", "Recurring invoices"],
  ["api:/recurring-invoices", "/invoices/recurring/", "Recurring invoice detail"],
  ["/invoices/recurring/new", "New recurring invoice"],
  ["@/invoices", new RegExp(`^/invoices/${ID}$`), "Invoice detail"],
  ["/purchase-orders", "Purchase orders"],
  ["@/purchase-orders", new RegExp(`^/purchase-orders/${ID}$`), "Purchase order detail"],
  ["/products", "Products"],
  ["/activities", "Activities"],
  ["/messages", "Messages"],
  ["/marketing", "Marketing"],
  ["/support", "Support"],
  ["api:/support/tickets", "/support/tickets/", "Support ticket"],
  ["/help", "Help"],
  ...["general", "team", "billing", "documents", "email", "data"].map((tab) => [`/settings?tab=${tab}`, `Settings ${tab}`]),
  ["/admin", "Admin overview"],
  ["/admin/tenants", "Admin companies"],
];
for (const entry of pages) {
  if (entry[0].startsWith("api:")) {
    const [source, prefix, name] = entry;
    const id = await apiFirst(source.slice(4));
    if (id) await visit(prefix + id, name);
    else results.push({ name, route: source, issues: ["no record to open (is the demo data seeded?)"] });
  } else if (entry[0].startsWith("@")) {
    const [list, re, name, suffix = ""] = entry;
    const href = await firstLink(list.slice(1), re);
    if (!href) {
      results.push({ name, route: list, issues: ["no record to open (is the demo data seeded?)"] });
      continue;
    }
    await visit(href + suffix, name);
  } else {
    await visit(entry[0], entry[1]);
  }
}

// The new flow: accept a sent quote on screen → toast → Review draft → the draft invoice.
const flow = { name: "Accept quote → draft invoice", route: "/quotes", issues: [] };
await page.setViewport({ width: 1440, height: 900 });
await page.goto(BASE + "/quotes", { waitUntil: "domcontentloaded" });
await settle();
const sentId = await apiFirst("/quotes?status=sent");
if (!sentId) flow.issues.push("no sent quote to accept");
else {
  await page.goto(`${BASE}/quotes/${sentId}`, { waitUntil: "domcontentloaded" });
  await settle();
  const clicked = await page.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find((x) => x.textContent.trim() === "Mark accepted");
    b?.click();
    return !!b;
  });
  if (!clicked) flow.issues.push("no Mark accepted button");
  else {
    try {
      await page.waitForFunction(() => document.body.innerText.includes("is ready to review"), { timeout: 10000 });
      await page.screenshot({ path: path.join(OUT, "laptop", "flow 1 accepted toast.png") });
      await page.evaluate(() => [...document.querySelectorAll("button")].find((x) => x.textContent.trim() === "Review draft").click());
      await page.waitForFunction(() => /^\/invoices\/[0-9a-f-]{36}$/.test(location.pathname), { timeout: 10000 });
      await settle();
      const text = await page.evaluate(() => document.body.innerText);
      if (!/Draft/.test(text)) flow.issues.push("invoice page does not show Draft");
      await page.screenshot({ path: path.join(OUT, "laptop", "flow 2 draft invoice.png") });
    } catch (e) {
      flow.issues.push(e.message.split("\n")[0]);
    }
  }
}
results.push(flow);

// Recurring: fill the form on screen, save, and find the first draft made.
const recurring = { name: "New recurring invoice → first draft", route: "/invoices/recurring/new", issues: [] };
try {
  await page.setViewport({ width: 1440, height: 900 });
  await page.goto(BASE + "/invoices/recurring/new", { waitUntil: "domcontentloaded" });
  await settle();
  await page.select("form select.input", await page.evaluate(() => document.querySelector("form select.input option:not([disabled])").value));
  await page.type("input[aria-label='Description']", "Monthly bookkeeping");
  await page.click("input[aria-label='Unit price']");
  await page.type("input[aria-label='Unit price']", "3500");
  await Promise.all([
    page.waitForFunction(() => /^\/invoices\/recurring\/[0-9a-f-]{36}$/.test(location.pathname), { timeout: 15000 }),
    page.click("form button[type=submit]"),
  ]);
  await settle();
  const text = await page.evaluate(() => document.body.innerText);
  if (!/INV-\d+/.test(text)) recurring.issues.push("no draft invoice listed after saving");
  if (!/Draft/.test(text)) recurring.issues.push("first invoice is not a draft");
  await page.screenshot({ path: path.join(OUT, "laptop", "flow 3 recurring saved.png") });
} catch (e) {
  recurring.issues.push(e.message.split("\n")[0]);
}
results.push(recurring);

// Edit everywhere: a draft invoice in the editor, a sent invoice corrected
// (voided + draft copy), a sent quote back to draft, an activity's pencil,
// and the pencils on the dashboard.
async function step(name, route, fn) {
  const r = { name, route, issues: [] };
  try {
    await page.setViewport({ width: 1440, height: 900 });
    await fn(r);
  } catch (e) {
    r.issues.push(e.message.split("\n")[0]);
  }
  results.push(r);
}
const clickText = (text) =>
  page.evaluate((txt) => {
    const b = [...document.querySelectorAll("button, a")].find((x) => x.textContent.trim() === txt && x.offsetParent);
    b?.click();
    return Boolean(b);
  }, text);
const onPath = (re) => page.waitForFunction((src) => new RegExp(src).test(location.pathname), { timeout: 15000 }, re.source);

await step("Edit a draft invoice", "/invoices/:id/edit", async (r) => {
  const id = await apiFirst("/invoices?status=draft");
  if (!id) return r.issues.push("no draft invoice");
  await page.goto(`${BASE}/invoices/${id}`, { waitUntil: "domcontentloaded" });
  await settle();
  if (!(await clickText("Edit"))) return r.issues.push("no Edit button on a draft");
  await onPath(/^\/invoices\/[0-9a-f-]{36}\/edit$/);
  await settle();
  const ref = "Edited by e2e";
  await page.click("input[maxlength='100']", { clickCount: 3 });
  await page.type("input[maxlength='100']", ref);
  await page.click("form button[type=submit]");
  await onPath(/^\/invoices\/[0-9a-f-]{36}$/);
  await settle();
  if (!(await page.evaluate((x) => document.body.innerText.includes(x), ref))) r.issues.push("new reference not shown after saving");
  await page.screenshot({ path: path.join(OUT, "laptop", "flow 4 edited draft invoice.png") });
});

await step("Correct a sent invoice", "/invoices/:id?edit=1", async (r) => {
  const id = await apiFirst("/invoices?status=overdue");
  if (!id) return r.issues.push("no overdue unpaid invoice");
  await page.goto(`${BASE}/invoices/${id}?edit=1`, { waitUntil: "domcontentloaded" });
  await settle();
  await page.screenshot({ path: path.join(OUT, "laptop", "flow 5 correct invoice.png") });
  if (!(await clickText("Void and make a corrected copy"))) return r.issues.push("no correct confirmation");
  await page.waitForFunction((old) => /^\/invoices\/[0-9a-f-]{36}\/edit$/.test(location.pathname) && !location.pathname.includes(old), { timeout: 15000 }, id);
  await settle();
  const status = await page.evaluate(async (url) => {
    const res = await fetch(url, { headers: { Authorization: `Bearer ${localStorage.getItem("access_token")}` } });
    return (await res.json()).status;
  }, `${API}/invoices/${id}`);
  if (status !== "void") r.issues.push(`old invoice is ${status}, not void`);
});

await step("Revise a sent quote", "/quotes/:id?edit=1", async (r) => {
  const id = await apiFirst("/quotes?status=sent");
  if (!id) return r.issues.push("no sent quote");
  await page.goto(`${BASE}/quotes/${id}?edit=1`, { waitUntil: "domcontentloaded" });
  await settle();
  if (!(await clickText("Make it a draft and edit"))) return r.issues.push("no revise confirmation");
  await onPath(/^\/quotes\/[0-9a-f-]{36}\/edit$/);
  await settle();
  if (!(await page.$("form input[aria-label='Description']"))) r.issues.push("editor did not open with lines");
});

await step("Edit an activity from its pencil", "/activities", async (r) => {
  await page.goto(`${BASE}/activities`, { waitUntil: "domcontentloaded" });
  await settle();
  const pencil = await page.$("button[aria-label^='Edit \"']");
  if (!pencil) return r.issues.push("no pencil on activities");
  await pencil.click();
  await page.waitForFunction(() => document.body.innerText.includes("Edit activity"), { timeout: 5000 });
  await page.screenshot({ path: path.join(OUT, "laptop", "flow 6 edit activity.png") });
  await page.keyboard.press("Escape");
});

await step("Dashboard has edit pencils", "/", async (r) => {
  await page.goto(`${BASE}/`, { waitUntil: "domcontentloaded" });
  await settle();
  const n = await page.evaluate(() => document.querySelectorAll("main button[aria-label^='Edit']").length);
  if (n < 3) r.issues.push(`only ${n} edit buttons on the dashboard`);
});

await browser.close();
const failed = results.filter((r) => r.issues.length);
for (const r of results) console.log(`${r.issues.length ? "FAIL" : "PASS"}  ${r.name}${r.issues.length ? "  (" + r.issues.join("; ") + ")" : ""}`);
console.log(problems.length ? "Page/API errors:\n  " + problems.join("\n  ") : "No page errors, no API 5xx.");
console.log(`${results.length - failed.length} of ${results.length} passed. Screenshots: ${OUT}`);
process.exit(failed.length || problems.length ? 1 : 0);
