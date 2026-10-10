// The product's name and mark, in one place.
export const APP_NAME = "YGT";
export const APP_FULL_NAME = "You Got This";

/** The YGT monogram on the brand gradient. `join` lets the letters rise into
 *  place once (sign-in and About only; never in the sidebar). */
export function BrandMark({ size = "md", className = "", join = false }) {
  const box = { sm: "h-7 w-7 rounded-lg text-[9px]", md: "h-9 w-9 rounded-xl text-[11px]", lg: "h-16 w-16 rounded-2xl text-[19px]" }[size];
  return (
    <span
      className={`brand-bg inline-flex shrink-0 items-center justify-center font-extrabold tracking-[-0.04em] text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.3),0_1px_3px_rgb(139_92_246/0.35)] ${box} ${className}`}
      aria-hidden="true"
    >
      <span className={`inline-flex leading-none ${join ? "brand-join" : ""}`}>
        <span>Y</span>
        <span>G</span>
        <span>T</span>
      </span>
    </span>
  );
}
