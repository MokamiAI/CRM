import { useLayoutEffect, useRef } from "react";
import { EASE_OUT, prefersReducedMotion } from "../utils/motion";

const WORDS = [
  ["Y", "ou"],
  ["G", "ot"],
  ["T", "his"],
];
// Strong ease-in-out for on-screen movement (same as --ease-in-out).
const EASE_IN_OUT = "cubic-bezier(0.77, 0, 0.175, 1)";

/**
 * "YGT" becomes "You Got This". The three capitals rise in close together
 * as the monogram, glide apart to where they sit in the full words, and
 * each word writes itself out behind its capital; a gradient line then
 * sweeps underneath. FLIP: the full words are laid out for real, the
 * capitals start translated to the monogram's spot, so only transform,
 * opacity and clip-path animate.
 *
 * `onDone` fires when it has finished (or at once under reduced motion,
 * where the full words simply appear). `delay` holds the start (ms).
 */
export default function YouGotThis({ className = "", delay = 0, onDone }) {
  const root = useRef(null);

  useLayoutEffect(() => {
    const el = root.current;
    if (!el) return undefined;
    const capitals = [...el.querySelectorAll("[data-capital]")];
    const tails = [...el.querySelectorAll("[data-tail]")];
    const line = el.querySelector("[data-line]");
    const phrase = el.querySelector("[data-phrase]").getBoundingClientRect();
    for (const piece of [...capitals, ...tails]) {
      const r = piece.getBoundingClientRect();
      piece.style.backgroundSize = `${phrase.width}px 100%`;
      piece.style.backgroundPosition = `${phrase.left - r.left}px 0`;
    }
    if (prefersReducedMotion()) {
      const fade = el.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 300, delay, easing: "ease", fill: "both" });
      fade.finished.then(() => onDone?.(), () => {});
      return () => fade.cancel();
    }

    // Where each capital would sit if the three stood together, centred.
    const box = el.getBoundingClientRect();
    const rects = capitals.map((c) => c.getBoundingClientRect());
    const total = rects.reduce((sum, r) => sum + r.width, 0);
    let x = box.left + box.width / 2 - total / 2;
    const offsets = rects.map((r) => {
      const dx = x - r.left;
      x += r.width;
      return dx;
    });

    const run = [];
    capitals.forEach((c, i) => {
      const dx = offsets[i];
      // 1. The monogram: capitals rise in, close together.
      run.push(
        c.animate(
          [
            { transform: `translate(${dx}px, 40%)`, opacity: 0 },
            { transform: `translate(${dx}px, 0)`, opacity: 1 },
          ],
          // "both": holds the monogram spot until the glide takes over.
          { duration: 520, delay: delay + i * 70, easing: EASE_OUT, fill: "both" }
        )
      );
      // 2. They glide apart to their places in the words.
      run.push(
        c.animate([{ transform: `translateX(${dx}px)` }, { transform: "translateX(0)" }], {
          duration: 750,
          delay: delay + 900,
          easing: EASE_IN_OUT,
          fill: "forwards", // no effect before it starts, so the rise shows
        })
      );
    });
    // 3. Each word writes itself out from its capital.
    tails.forEach((tail, i) => {
      run.push(
        tail.animate(
          [
            { clipPath: "inset(-0.2em 100% -0.2em 0)", opacity: 0 },
            { clipPath: "inset(-0.2em -0.2em -0.2em 0)", opacity: 1 },
          ],
          { duration: 600, delay: delay + 1250 + i * 90, easing: EASE_OUT, fill: "both" }
        )
      );
    });
    // 4. A gradient line sweeps underneath.
    if (line) {
      run.push(
        line.animate([{ transform: "scaleX(0)" }, { transform: "scaleX(1)" }], { duration: 500, delay: delay + 1750, easing: EASE_OUT, fill: "both" })
      );
    }
    Promise.all(run.map((a) => a.finished)).then(() => onDone?.(), () => {});
    return () => run.forEach((a) => a.cancel());
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <span ref={root} className={`relative inline-flex flex-col items-center ${className}`} aria-label="You Got This" role="img">
      <span data-phrase className="flex items-baseline gap-[0.28em] whitespace-nowrap font-extrabold tracking-[-0.04em]" aria-hidden="true">
        {WORDS.map(([capital, tail]) => (
          <span key={capital} className="inline-flex">
            <span data-capital className="yg-piece inline-block">
              {capital}
            </span>
            <span data-tail className="yg-piece inline-block">
              {tail}
            </span>
          </span>
        ))}
      </span>
      <span data-line className="brand-bg mt-[0.12em] block h-[0.06em] min-h-[3px] w-full origin-left rounded-full" aria-hidden="true" />
    </span>
  );
}
