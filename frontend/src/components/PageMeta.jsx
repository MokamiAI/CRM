import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { PAGES } from "../seo/pages";

const DEFAULT = PAGES["/"];

function setMeta(selector, value) {
  const el = document.head.querySelector(selector);
  if (el && value != null) el.setAttribute("content", value);
}

/** Keeps the tab title and description right on public pages as people
 *  move between them (the first load already has them: see seo/pages.js).
 *  Pages inside the app keep the home page's title. */
export default function PageMeta() {
  const { pathname } = useLocation();
  useEffect(() => {
    const page = PAGES[pathname] ?? DEFAULT;
    document.title = page.title;
    setMeta('meta[name="description"]', page.description);
  }, [pathname]);
  return null;
}
