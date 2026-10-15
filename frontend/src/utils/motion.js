import { useEffect, useState } from "react";

export const EASE_OUT = "cubic-bezier(0.23, 1, 0.32, 1)"; // same as --ease-out

export function prefersReducedMotion() {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * True the first time `key` is shown today, in this browser; false after
 * that (and when storage is unavailable). The dashboard is opened many
 * times a day, so its entrance plays once each morning and never again
 * that day: the rest of the time it is simply there.
 */
export function useFirstToday(key) {
  const [first] = useState(() => {
    try {
      return localStorage.getItem(`ygt.motion.${key}`) !== new Date().toDateString();
    } catch {
      return false;
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem(`ygt.motion.${key}`, new Date().toDateString());
    } catch {
      /* private mode: no entrance, which is fine */
    }
  }, [key]);
  return first;
}

/** True once per `key`, ever (e.g. a goal reached in a given year). */
export function firstTime(key) {
  try {
    if (localStorage.getItem(`ygt.once.${key}`)) return false;
    localStorage.setItem(`ygt.once.${key}`, "1");
    return true;
  } catch {
    return false;
  }
}

const COLORS = ["#10b981", "#f59e0b", "#0ea5e9", "#8b5cf6", "#f43f5e", "#18181b"];

/**
 * A small burst from an element: winning a deal. Rare, high-emotion, so
 * this is where the delight budget goes; still short (≤750ms) and never
 * in the way. WAAPI keeps it on the compositor (transform + opacity only)
 * with no library. Skipped entirely under reduced motion.
 */
export function celebrate(element, { count = 16 } = {}) {
  if (!element || prefersReducedMotion()) return;
  const rect = element.getBoundingClientRect();
  const originX = rect.left + rect.width / 2;
  const originY = rect.top + rect.height / 2;

  const layer = document.createElement("div");
  layer.setAttribute("aria-hidden", "true");
  layer.style.cssText = "position:fixed;inset:0;pointer-events:none;z-index:60;overflow:hidden";
  document.body.appendChild(layer);

  const animations = Array.from({ length: count }, (_, i) => {
    const piece = document.createElement("span");
    const size = 5 + Math.random() * 4;
    const round = i % 3 === 0;
    piece.style.cssText = `position:absolute;left:${originX}px;top:${originY}px;width:${size}px;height:${round ? size : size * 0.45}px;border-radius:${round ? "50%" : "1px"};background:${COLORS[i % COLORS.length]}`;
    layer.appendChild(piece);

    // Fan upward and out, then fall: a peak keyframe, then gravity.
    const angle = -Math.PI / 2 + (Math.random() - 0.5) * Math.PI * 1.1;
    const distance = 60 + Math.random() * 70;
    const peakX = Math.cos(angle) * distance;
    const peakY = Math.sin(angle) * distance;
    const spin = (Math.random() - 0.5) * 540;
    return piece.animate(
      [
        { transform: "translate(-50%, -50%) scale(0.6) rotate(0deg)", opacity: 1 },
        { transform: `translate(calc(${peakX}px - 50%), calc(${peakY}px - 50%)) scale(1) rotate(${spin / 2}deg)`, opacity: 1, offset: 0.45 },
        { transform: `translate(calc(${peakX * 1.25}px - 50%), calc(${peakY + 90}px - 50%)) scale(0.9) rotate(${spin}deg)`, opacity: 0 },
      ],
      { duration: 650 + Math.random() * 150, easing: EASE_OUT, fill: "forwards" }
    );
  });

  Promise.all(animations.map((a) => a.finished)).finally(() => layer.remove());
}
