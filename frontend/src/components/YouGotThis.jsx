import { forwardRef, useImperativeHandle, useLayoutEffect, useRef } from "react";
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
 *
 * `ref.current.outro()` plays it backwards to close: the words un-write
 * into their capitals, the line draws back, the capitals glide together
 * into YGT, hold a beat, then rise away. Resolves when it's gone.
 */
const YouGotThis = forwardRef(function YouGotThis({ className = "", delay = 0, onDone }, ref) {
  const root = useRef(null);
  const parts = useRef(null);

  useImperativeHandle(ref, () => ({
    outro() {
      const el = root.current;
      if (!el) return Promise.resolve();
      if (prefersReducedMotion() || !parts.current) {
        return el.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 250, easing: "ease", fill: "forwards" }).finished.catch(() => {});
      }
      const { capitals, tails, line, offsets } = parts.current;
      const run = [];
      // 1. The words un-write back into their capitals, last word first.
      [...tails].reverse().forEach((tail, i) => {
        run.push(
          tail.animate(
            [
              { clipPath: "inset(-0.2em -0.2em -0.2em 0)", opacity: 1 },
              { clipPath: "inset(-0.2em 100% -0.2em 0)", opacity: 0 },
            ],
            { duration: 500, delay: i * 90, easing: EASE_IN_OUT, fill: "forwards" }
          )
        );
      });
      // 2. The line draws back the way it came.
      if (line) {
        run.push(line.animate([{ transform: "scaleX(1)" }, { transform: "scaleX(0)" }], { duration: 450, easing: EASE_IN_OUT, fill: "forwards" }));
      }
      capitals.forEach((c, i) => {
        const dx = offsets[i];
        // 3. The capitals glide back together: YGT again.
        run.push(
          c.animate([{ transform: "translate(0, 0)" }, { transform: `translate(${dx}px, 0)` }], {
            duration: 750,
            delay: 550,
            easing: EASE_IN_OUT,
            fill: "forwards",
          })
        );
        // 4. A beat as YGT, then they rise away one after another.
        run.push(
          c.animate(
            [
              { transform: `translate(${dx}px, 0)`, opacity: 1 },
              { transform: `translate(${dx}px, -40%)`, opacity: 0 },
            ],
            { duration: 450, delay: 1700 + i * 70, easing: EASE_OUT, fill: "forwards" }
          )
        );
      });
      return Promise.all(run.map((a) => a.finished)).catch(() => {});
    },
  }));

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

    parts.current = { capitals, tails, line, offsets };

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
});

export default YouGotThis;
