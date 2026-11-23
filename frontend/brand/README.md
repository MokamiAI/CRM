# YGT logo

There is one logo: **`ygt-app-icon.png`** in this folder. Everything else is made from it.
Don't add another version anywhere; change this file and remake the copies.

| Copy | Used for |
|---|---|
| `public/brand/ygt-logo-64.png`, `-128.png`, `-256.png` (rounded corners see-through) | The logo on every page (`BrandMark` in `src/components/Brand.jsx`) and in YGT's own emails |
| `public/favicon-32.png`, `favicon-48.png` | Browser tab |
| `public/apple-touch-icon.png`, `icon-72.png`, `icon-192.png`, `icon-512.png`, `icon-maskable-512.png` | Home screen, installed app, push alerts |
| `public/og-image.png` | Link preview when yougt.co.za is shared (from `og-image.html`; run `node e2e/make-og-image.mjs`) |

When a copy changes, bump the `?v=` on its links (`index.html`, `manifest.webmanifest`, `sw.js`, `src/seo/pages.js`) so browsers fetch the new one.

Not the YGT logo, so leave them alone: a company's own logo on its invoices, quotes and emails to its clients.
