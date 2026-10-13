// Click-through of every button and link on the public site (home page,
// pricing, FAQ, footer), signed out, against a LOCAL YGT.
//   node e2e/public.mjs        (site on :4173, API on :8000)
import puppeteer from "puppeteer-core";

const BASE = (process.env.YGT_WEB || "http://localhost:4173") + "/";
const CHROME = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
if (!/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?\/$/.test(BASE)) throw new Error(`Refusing: ${BASE} is not local`);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const b = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ["--proxy-server=direct://", "--proxy-bypass-list=*"] });
const results = [];
const errors = [];
const ok = (name, pass, detail = "") => results.push(`${pass ? "PASS" : "FAIL"}  ${name}${detail ? "  (" + detail + ")" : ""}`);

async function fresh(w = 1366, h = 860) {
  const p = await b.newPage();
  await p.setViewport({ width: w, height: h });
  p.on("pageerror", (e) => errors.push(e.message));
  await p.goto(BASE, { waitUntil: "networkidle2" });
  await p.evaluate(() => localStorage.setItem("language", "en"));
  await p.reload({ waitUntil: "networkidle2" });
  await wait(600);
  return p;
}
const path = (p) => p.evaluate(() => location.pathname + location.search + location.hash);
const inView = (p, sel) =>
  p.evaluate((s) => {
    const r = document.querySelector(s).getBoundingClientRect();
    return r.top > -40 && r.top < innerHeight * 0.5;
  }, sel);
const clickText = (p, scope, text) =>
  p.evaluate(
    (scope, text) => {
      const el = [...document.querySelectorAll(scope)].find((n) => n.textContent.trim() === text && n.offsetParent !== null);
      if (!el) return false;
      el.scrollIntoView({ block: "center", behavior: "instant" });
      el.click();
      return true;
    },
    scope,
    text
  );
async function navTest(name, scope, text, expect) {
  const p = await fresh();
  const found = await clickText(p, scope, text);
  await wait(900);
  const at = await path(p);
  const body = await p.evaluate(() => document.body.innerText.length);
  ok(name, found && at.startsWith(expect) && body > 50, found ? `-> ${at}` : "button not found");
  await p.close();
}
async function anchorTest(name, scope, text, hash, sel) {
  const p = await fresh();
  const found = await clickText(p, scope, text);
  await wait(1200);
  const at = await path(p);
  ok(name, found && at.endsWith(hash) && (await inView(p, sel)), found ? `-> ${at}, section in view` : "not found");
  await p.close();
}

// Header
await anchorTest("Header: Features", "header nav a", "Features", "#features", "#features");
await anchorTest("Header: Pricing", "header nav a", "Pricing", "#pricing", "#pricing");
await anchorTest("Header: Questions", "header nav a", "Questions", "#faq", "#faq");
await navTest("Header: About", "header nav a", "About", "/about");
await navTest("Header: Sign in", "header a", "Sign in", "/login");
await navTest("Header: Start free trial", "header a", "Start free trial", "/register");
{
  const p = await fresh();
  await p.goto(BASE + "about", { waitUntil: "networkidle2" });
  await p.evaluate(() => document.querySelector("header a[href='/']").click());
  await wait(900);
  ok("Logo (from About) goes home", (await path(p)) === "/" && (await p.evaluate(() => !!document.querySelector(".scene"))), await path(p));
  await p.close();
}
{
  const p = await fresh();
  await p.evaluate(() => document.querySelector("header button[aria-label]").click());
  await wait(500);
  const opened = await p.evaluate(() => document.querySelectorAll("button[role=radio]").length);
  await p.evaluate(() => [...document.querySelectorAll("button[role=radio]")].find((x) => x.textContent.includes("Afrikaans")).click());
  await wait(1500);
  const h1 = await p.evaluate(() => document.querySelector("h1").textContent);
  ok("Header: language picker opens and switches", opened >= 11 && h1.includes("Minder admin"), `${opened} languages, h1 "${h1}"`);
  await p.close();
}
// Hero
await navTest("Hero: Start your free trial", "section a", "Start your free trial", "/register");
await anchorTest("Hero: See pricing", "section a", "See pricing", "#pricing", "#pricing");
// People picker
{
  const p = await fresh();
  const labels = await p.evaluate(() => [...document.querySelectorAll("button[aria-pressed]")].map((x) => x.textContent.trim()));
  const seen = [];
  for (let i = labels.length - 1; i >= 0; i--) {
    await p.evaluate((i) => {
      const x = document.querySelectorAll("button[aria-pressed]")[i];
      x.scrollIntoView({ block: "center", behavior: "instant" });
      x.click();
    }, i);
    await wait(600);
    const st = await p.evaluate((i) => {
      const btn = document.querySelectorAll("button[aria-pressed]")[i];
      const active = document.querySelector(".people-photo[data-active=true]");
      return { pressed: btn.getAttribute("aria-pressed"), label: document.querySelector(".people-label").textContent, loaded: active.complete && active.naturalWidth > 0 };
    }, i);
    seen.push(st.pressed === "true" && st.label === labels[i] && st.loaded);
  }
  ok("People: each business-type button shows its photo and feed", seen.every(Boolean), `${labels.join(", ")}`);
  await p.close();
}
// Savings sliders
{
  const p = await fresh();
  const read = () => p.evaluate(() => [...document.querySelectorAll("section[aria-labelledby=home-savings] .tabular-nums")].map((n) => n.textContent.trim()));
  await p.evaluate(() => document.querySelector(".savings-range").scrollIntoView({ block: "center", behavior: "instant" }));
  await wait(700);
  const before = await read();
  const ranges = await p.$$(".savings-range");
  await ranges[0].focus();
  for (let i = 0; i < 12; i++) await p.keyboard.press("ArrowRight");
  await ranges[1].focus();
  for (let i = 0; i < 4; i++) await p.keyboard.press("ArrowRight");
  await wait(200);
  const after = await read();
  ok("Savings: both sliders work by keyboard and the results update", JSON.stringify(before) !== JSON.stringify(after), `${before.join(" | ")}  ->  ${after.join(" | ")}`);
  const box = await ranges[0].boundingBox();
  await p.mouse.click(box.x + box.width * 0.9, box.y + box.height / 2);
  await wait(200);
  const clicked = await read();
  ok("Savings: clicking along the slider track works", clicked[0] !== after[0], `docs ${after[0]} -> ${clicked[0]}`);
  await p.close();
}
// Pricing
{
  const p = await fresh();
  await p.evaluate(() => document.getElementById("pricing").scrollIntoView({ behavior: "instant" }));
  await wait(900);
  const cards = await p.evaluate(() => [...document.querySelectorAll("#pricing a")].map((a) => a.getAttribute("href")));
  const monthly = await p.evaluate(() => document.getElementById("pricing").innerText);
  const toggles = await p.evaluate(() => [...document.querySelectorAll("#pricing [role=radio]")].map((x) => x.textContent.trim()));
  await p.evaluate(() => [...document.querySelectorAll("#pricing [role=radio]")][1].click());
  await wait(400);
  const annual = await p.evaluate(() => document.getElementById("pricing").innerText);
  ok("Pricing: monthly / yearly toggle changes prices", toggles.length === 2 && monthly !== annual, toggles.join(" / "));
  await p.close();
  ok("Pricing: plan cards loaded", cards.length === 3, cards.join(", "));
  for (const href of cards) {
    const q = await fresh();
    await q.evaluate((h) => {
      const a = document.querySelector(`#pricing a[href="${h}"]`);
      a.scrollIntoView({ block: "center" });
      a.click();
    }, href);
    await wait(900);
    const at = await path(q);
    ok(`Pricing: plan button ${href}`, at === href, `-> ${at}`);
    await q.close();
  }
}
// FAQ
{
  const p = await fresh();
  const n = await p.evaluate(() => document.querySelectorAll("#faq button").length);
  const res = [];
  for (let i = 0; i < n; i++) {
    await p.evaluate((i) => {
      const x = document.querySelectorAll("#faq button")[i];
      x.scrollIntoView({ block: "center" });
      x.click();
    }, i);
    await wait(400);
    const st = await p.evaluate((i) => {
      const li = document.querySelectorAll("#faq li")[i];
      return [li.querySelector("button").getAttribute("aria-expanded"), li.querySelector(".faq-panel").getBoundingClientRect().height > 20, document.querySelectorAll(".faq-panel[data-open=true]").length];
    }, i);
    res.push(st[0] === "true" && st[1] && st[2] === 1);
  }
  await p.evaluate((n) => document.querySelectorAll("#faq button")[n - 1].click(), n);
  await wait(400);
  const closed = await p.evaluate(() => document.querySelectorAll(".faq-panel[data-open=true]").length === 0);
  ok("FAQ: each question opens (one at a time) and closes again", res.every(Boolean) && closed, `${n} questions`);
  await p.close();
}
// Closing band + footer
await navTest("Closing band: Start your free trial", ".cta-band a", "Start your free trial", "/register");
await navTest("Closing band: Talk to us", ".cta-band a", "Talk to us", "/contact");
for (const [t, to] of [["About", "/about"], ["Contact us", "/contact"], ["Terms", "/terms"], ["Privacy", "/privacy"], ["Refund policy", "/refunds"]])
  await navTest(`Footer: ${t}`, "footer a", t, to);

// Phone
{
  const p = await fresh(390, 844);
  const vis = await p.evaluate(() => [...document.querySelectorAll("header a, header button")].filter((n) => n.offsetParent !== null).map((n) => n.textContent.trim() || n.getAttribute("aria-label")));
  ok("Phone header: language and Sign in visible", vis.some((v) => v.includes("Sign in")), vis.join(", "));
  const small = await p.evaluate(() =>
    [...document.querySelectorAll("a, button, input")]
      .filter((n) => n.offsetParent !== null)
      .map((n) => [n.textContent.trim().slice(0, 30) || n.getAttribute("aria-label") || n.type, Math.round(n.getBoundingClientRect().height)])
      .filter(([, h]) => h < 32)
  );
  ok("Phone: tap targets at least 32px tall", small.length === 0, small.map(([t, h]) => `${t}=${h}px`).join("; "));
  await p.close();
}
console.log(results.join("\n"));
console.log(errors.length ? "page errors: " + errors.join(" | ") : "no page errors");
await b.close();
const failed = results.filter((r) => r.startsWith("FAIL")).length;
console.log(`${results.length - failed} of ${results.length} passed`);
process.exit(failed || errors.length ? 1 : 0);
