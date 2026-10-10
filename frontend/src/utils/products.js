import { todayISO } from "./format";

/** True while a product's promotional price applies (until its end date, inclusive). */
export function onSpecial(product) {
  if (product?.special_price == null) return false;
  return !product.special_until || product.special_until >= todayISO();
}
