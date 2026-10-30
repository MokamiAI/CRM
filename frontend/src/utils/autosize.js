// Every text box in the app grows with what's typed into it (and shrinks
// back), up to half the screen, then scrolls. Installed once, from main.jsx,
// so new text boxes get it without doing anything. A box opts out with
// data-autosize="off".
//
// Three ways a box's text changes: typing (the input event), a box that
// appears already filled (an edit sheet opening), and the app setting the
// text itself (cleared after Send, a template inserted). React sets that
// last one through the value property, which fires no event, so the
// property's setter is wrapped to resize too.

const queued = new Set();

function fit(el) {
  if (!el.isConnected || el.dataset.autosize === "off" || el.offsetParent === null) return;
  const style = getComputedStyle(el);
  const borders = parseFloat(style.borderTopWidth) + parseFloat(style.borderBottomWidth);
  const cssMax = parseFloat(style.maxHeight);
  const max = Number.isFinite(cssMax) ? cssMax : Math.round(window.innerHeight * 0.5);
  // Shrinking to "auto" for a moment can scroll the page; put it back.
  const scrollY = window.scrollY;
  el.style.height = "auto";
  const wanted = el.scrollHeight + borders;
  el.style.height = `${Math.min(wanted, max)}px`;
  el.style.overflowY = wanted > max ? "auto" : "hidden";
  if (window.scrollY !== scrollY) window.scrollTo({ top: scrollY });
}

function schedule(el) {
  if (queued.has(el)) return;
  queued.add(el);
  requestAnimationFrame(() => {
    queued.delete(el);
    fit(el);
  });
}

function fitWithin(node) {
  if (node.nodeType !== 1) return;
  if (node.tagName === "TEXTAREA") schedule(node);
  else node.querySelectorAll?.("textarea").forEach(schedule);
}

export function installAutosize() {
  if (typeof window === "undefined" || window.__autosize) return;
  window.__autosize = true;

  document.addEventListener("input", (e) => e.target.tagName === "TEXTAREA" && fit(e.target), true);
  // A box that was hidden (a closed tab or sheet) is sized when it's used.
  document.addEventListener("focusin", (e) => e.target.tagName === "TEXTAREA" && schedule(e.target), true);

  const { set, get } = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value");
  Object.defineProperty(HTMLTextAreaElement.prototype, "value", {
    configurable: true,
    enumerable: true,
    get,
    set(v) {
      set.call(this, v);
      schedule(this);
    },
  });

  new MutationObserver((records) => records.forEach((r) => r.addedNodes.forEach(fitWithin))).observe(document.body, { childList: true, subtree: true });

  let width = window.innerWidth;
  window.addEventListener("resize", () => {
    if (window.innerWidth === width) return; // a phone's address bar, not a new width
    width = window.innerWidth;
    document.querySelectorAll("textarea").forEach(schedule);
  });
}
