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

/** The YGT logo. Every page shows it through this one component, from
 *  copies of the master file frontend/brand/ygt-app-icon.png (see
 *  frontend/brand/README.md). `join` fades it in once (sign-in, About and
 *  the welcome tour; never in the sidebar). */
export function BrandMark({ size = "md", className = "", join = false }) {
  const box = { sm: "h-7 w-7 rounded-lg", md: "h-9 w-9 rounded-xl", lg: "h-16 w-16 rounded-2xl" }[size];
  // Sharp on high-density screens: about three times the shown size.
  const file = size === "lg" ? 256 : 128;
  return (
    <img
      src={`/brand/ygt-logo-${file}.png`}
      alt=""
      aria-hidden="true"
      width={file}
      height={file}
      decoding="async"
      draggable="false"
      className={`inline-block shrink-0 select-none shadow-[0_1px_3px_rgb(79_70_229/0.25)] ${box} ${join ? "brand-join" : ""} ${className}`}
    />
  );
}
