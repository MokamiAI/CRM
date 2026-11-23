// What each public page is called in search results, browser tabs and
// link previews (WhatsApp, Facebook, LinkedIn, email). One list, used twice:
// - at build time (vite.config.js) to write a page's own HTML file, e.g.
//   dist/about.html, so link previews and crawlers see the right title
//   without running the app;
// - in the browser (components/PageMeta.jsx) to keep the tab title right
//   as people move between pages.
// Plain data, no imports: vite.config.js loads this file in Node.

export const SITE_URL = "https://yougt.co.za";
export const OG_IMAGE = `${SITE_URL}/og-image.png?v=2`;

const HOME_DESCRIPTION =
  "One place for your customers, deals, quotes, invoices and payments. YGT follows up and chases payments for you, saving hours every week, so you can focus on running your business. 14-day free trial, no card needed.";

export const PAGES = {
  "/": {
    title: "YGT · Quotes, invoices and payment reminders for South African businesses",
    description: HOME_DESCRIPTION,
    ogTitle: "YGT · You Got This",
    ogDescription: "Less admin. More business. Quotes, invoices and payment reminders in one place. 14-day free trial, no card needed.",
  },
  "/about": {
    title: "About YGT · You Got This",
    description:
      "Why we built YGT: simple sales, quotes and invoicing for South African businesses, in all 11 official languages. Grow. Manage. Succeed.",
  },
  "/assessment": {
    title: "Free business check-up · YGT",
    description:
      "10 quick questions about how you run things. Get your business operations score, your three biggest gaps and how much admin time you could save. No sign-up.",
  },
  "/contact": {
    title: "Contact YGT",
    description: "Questions about YGT, pricing or getting set up? Email, WhatsApp or send us a message. We usually reply within one working day.",
  },
  "/register": {
    title: "Start your free trial · YGT",
    description: "Set up YGT for your business in a minute. 14 days free, no card needed, cancel any time.",
  },
  "/login": {
    title: "Sign in · YGT",
    description: "Sign in to YGT: your customers, deals, quotes and invoices in one place.",
    noindex: true,
  },
  "/forgot-password": {
    title: "Reset your password · YGT",
    description: "Reset your YGT password.",
    noindex: true,
  },
  "/terms": {
    title: "Terms and conditions · YGT",
    description: "The terms for using YGT, from YGT Nexovanta Technologies (Pty) Ltd.",
  },
  "/privacy": {
    title: "Privacy policy · YGT",
    description: "How YGT looks after personal information, in line with POPIA.",
  },
  "/refunds": {
    title: "Refund policy · YGT",
    description: "Cancelling, the 7-day cooling-off period, and refunds for monthly and yearly YGT plans.",
  },
};
