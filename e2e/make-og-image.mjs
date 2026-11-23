// Renders frontend/brand/og-image.html into frontend/public/og-image.png
// (the link preview shown when yougt.co.za is shared).
//   node e2e/make-og-image.mjs
import puppeteer from "puppeteer-core";
import { fileURLToPath, pathToFileURL } from "node:url";

const CHROME = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const from = (p) => fileURLToPath(new URL(p, import.meta.url));
const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ["--allow-file-access-from-files"] });
const page = await browser.newPage();
await page.setViewport({ width: 1200, height: 630, deviceScaleFactor: 1 });
await page.goto(pathToFileURL(from("../frontend/brand/og-image.html")).href, { waitUntil: "load" });
await page.evaluate(() => document.fonts.ready);
await new Promise((r) => setTimeout(r, 300));
await page.screenshot({ path: from("../frontend/public/og-image.png") });
await browser.close();
console.log("Wrote frontend/public/og-image.png");
