import { useEffect } from "react";
import { useLocation } from "react-router-dom";

// Counts visits to the public pages for YGT's website report, without
// cookies: nothing is stored on the visitor's device, and signed-in people
// aren't counted. The server keeps only the page, where the visit came
// from and the kind of device (backend/app/services/site_visits.py).
const BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";
const PUBLIC = new Set(["/", "/assessment", "/about", "/contact", "/register", "/login", "/terms", "/privacy", "/refunds", "/delete-account"]);

// Where this visit came from: the first page's ?src= tag (our QR codes and
// links) or the site that linked here. Kept for the visit's later pages.
let origin;
function arrival() {
  if (!origin) {
    const params = new URLSearchParams(window.location.search);
    origin = { src: params.get("src") || params.get("utm_source") || null, referrer: document.referrer || null };
  }
  return origin;
}

function signedIn() {
  try {
    return Boolean(localStorage.getItem("access_token"));
  } catch {
    return false;
  }
}

/** event: "view" (a page), "checkup_start" or "checkup_done". */
export function trackVisit(event = "view", path = window.location.pathname) {
  const page = path.replace(/\/+$/, "") || "/";
  if (signedIn() || !PUBLIC.has(page)) return;
  fetch(`${BASE}/public/visit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event, path: page, ...arrival() }),
    keepalive: true,
  }).catch(() => {});
}

/** Reports each public page as it's shown. */
export function VisitTracker() {
  const { pathname } = useLocation();
  useEffect(() => {
    trackVisit("view", pathname);
  }, [pathname]);
  return null;
}
