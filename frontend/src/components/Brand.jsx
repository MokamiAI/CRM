import { useTranslation } from "react-i18next";

// The product's name and mark, in one place.
export const APP_NAME = "YGT";
export const APP_FULL_NAME = "You Got This";
// The company that develops and runs YGT, and its own website.
export const COMPANY_NAME = "YGT Nexovanta Technologies";
export const COMPANY_URL = "https://ynexovantatech.co.za";

/** "Developed by YGT Nexovanta Technologies", the name linking to the
 *  company's website (a new tab, so YGT stays open). */
export function DevelopedBy() {
  const { t } = useTranslation();
  const [before, after = ""] = t("about.developedBy", { company: "%COMPANY%" }).split("%COMPANY%");
  return (
    <>
      {before}
      <a href={COMPANY_URL} target="_blank" rel="noopener" className="underline-offset-2 hover:text-zinc-800 hover:underline">
        {COMPANY_NAME}
      </a>
      {after}
    </>
  );
}

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
