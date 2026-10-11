import { Suspense, useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import VerifyEmailBanner from "../components/VerifyEmailBanner";
import { useTranslation } from "react-i18next";
import { useAuth } from "../context/AuthContext";
import { Avatar, ListSkeleton, Tooltip } from "../components/ui";
import CommandPalette, { openCommandPalette } from "../components/CommandPalette";
import LanguagePicker from "../components/LanguagePicker";
import i18n, { setCustomerTerm } from "../i18n";
import Sheet from "../components/Sheet";
import { BrandMark } from "../components/Brand";
import { TourProvider, useTour } from "../components/Tour";
import { ProfileSheet } from "../components/Signature";
import { LockedBanner } from "../components/Billing";
import QuoteOfTheWeek from "../components/QuoteOfTheWeek";
import { useActivityCounts, useCompany, useInboxCounts } from "../hooks/useApi";

const Icon = ({ d, ...props }) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
    {d}
  </svg>
);

const HomeIcon = (props) => <Icon {...props} d={<path d="M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-4v-6H9v6H5a1 1 0 0 1-1-1v-9.5Z" />} />;
const InvoiceIcon = (props) => (
  <Icon {...props} d={<><path d="M6 3h9l4 4v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" /><path d="M14 3v5h5M9 13h6M9 17h4" /></>} />
);
const PurchaseIcon = (props) => (
  <Icon {...props} d={<><path d="M3 4h2l2.2 10.2a1 1 0 0 0 1 .8h8.6a1 1 0 0 0 1-.8L20 8H6.2" /><circle cx="9" cy="19" r="1.5" /><circle cx="17" cy="19" r="1.5" /></>} />
);
const QuoteIcon = (props) => (
  <Icon {...props} d={<><path d="M4 5a1 1 0 0 1 1-1h14a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H9l-4 3v-3H5a1 1 0 0 1-1-1V5Z" /><path d="M8 9h8M8 12h5" /></>} />
);
const CustomersIcon = (props) => (
  <Icon {...props} d={<><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0M16 4.5a3.5 3.5 0 0 1 0 7M18.5 20a6.5 6.5 0 0 0-3-5.5" /></>} />
);
const ProductsIcon = (props) => (
  <Icon {...props} d={<><path d="M12 3 4 7v10l8 4 8-4V7l-8-4Z" /><path d="m4 7 8 4 8-4M12 11v10" /></>} />
);
const DealsIcon = (props) => (
  <Icon {...props} d={<><rect x="3" y="4" width="5" height="16" rx="1.5" /><rect x="10" y="4" width="5" height="11" rx="1.5" /><rect x="17" y="4" width="4" height="7" rx="1.5" /></>} />
);
const ActivitiesIcon = (props) => (
  <Icon {...props} d={<><circle cx="12" cy="12" r="9" /><path d="m8.5 12 2.5 2.5 4.5-5" /></>} />
);
const MarketingIcon = (props) => (
  <Icon {...props} d={<><path d="M3 10.5v3a1 1 0 0 0 1 1h2l6 4.5V5L6 9.5H4a1 1 0 0 0-1 1Z" /><path d="M16 9a3.5 3.5 0 0 1 0 6M18.5 6.5a7 7 0 0 1 0 11" /></>} />
);
const MessagesIcon = (props) => (
  <Icon {...props} d={<><path d="M4 6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H9l-5 4V6Z" /><path d="M8 9h8M8 12.5h5" /></>} />
);
const AboutIcon = (props) => (
  <Icon {...props} d={<><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 7.5v.5" /></>} />
);
const HelpIcon = (props) => (
  <Icon {...props} d={<><circle cx="12" cy="12" r="9" /><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6M12 17h.01" /></>} />
);
const SupportIcon = (props) => (
  <Icon {...props} d={<><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="3.5" /><path d="m5.6 5.6 3.9 3.9M14.5 14.5l3.9 3.9M18.4 5.6l-3.9 3.9M9.5 14.5l-3.9 3.9" /></>} />
);
const ShieldIcon = (props) => <Icon {...props} d={<><path d="M12 3 4 6.5v5c0 4.4 3.4 8.4 8 9.5 4.6-1.1 8-5.1 8-9.5v-5L12 3Z" /><path d="m9 12 2 2 4-4" /></>} />;
const SearchIcon = (props) => <Icon {...props} d={<><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></>} />;
const MoreIcon = (props) => <Icon {...props} d={<><circle cx="5" cy="12" r="1.2" /><circle cx="12" cy="12" r="1.2" /><circle cx="19" cy="12" r="1.2" /></>} />;
const GearIcon = (props) => (
  <Icon
    {...props}
    d={<><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1.03 1.56V21a2 2 0 1 1-4 0v-.09A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.56-1.03H3a2 2 0 1 1 0-4h.09A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1.03-1.56V3a2 2 0 1 1 4 0v.09A1.7 1.7 0 0 0 15 4.6a1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 9a1.7 1.7 0 0 0 1.56 1.03H21a2 2 0 1 1 0 4h-.09A1.7 1.7 0 0 0 19.4 15Z" /></>}
  />
);
const LogoutIcon = (props) => (
  <Icon {...props} d={<path d="M15 4h3a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-3M10 8l-4 4 4 4M6 12h10" />} />
);

const NAV = {
  home: { to: "/", navKey: "dashboard", shortKey: "home", icon: HomeIcon, end: true },
  activities: { to: "/activities", navKey: "activities", icon: ActivitiesIcon, badge: "activities" },
  messages: { to: "/messages", navKey: "messages", icon: MessagesIcon, badge: "messages" },
  deals: { to: "/deals", navKey: "deals", icon: DealsIcon },
  quotes: { to: "/quotes", navKey: "quotes", icon: QuoteIcon },
  invoices: { to: "/invoices", navKey: "invoices", icon: InvoiceIcon },
  purchaseOrders: { to: "/purchase-orders", navKey: "purchaseOrders", icon: PurchaseIcon },
  marketing: { to: "/marketing", navKey: "marketing", icon: MarketingIcon },
  customers: { to: "/customers", navKey: "customers", icon: CustomersIcon },
  products: { to: "/products", navKey: "products", icon: ProductsIcon },
  settings: { to: "/settings", navKey: "settings", icon: GearIcon },
  about: { to: "/about", navKey: "about", icon: AboutIcon },
  help: { to: "/help", navKey: "help", icon: HelpIcon },
  support: { to: "/support", navKey: "support", icon: SupportIcon },
  admin: { to: "/admin", navKey: "admin", icon: ShieldIcon },
};

// Grouped the way the work flows: your day, then selling, then records.
const NAV_GROUPS = [
  { items: [NAV.home, NAV.activities, NAV.messages] },
  { title: "sales", items: [NAV.deals, NAV.quotes, NAV.invoices, NAV.purchaseOrders, NAV.marketing] },
  { title: "records", items: [NAV.customers, NAV.products] },
];

// Phones get the four most-used places plus "More" for the rest.
const TAB_ITEMS = [NAV.home, NAV.deals, NAV.activities, NAV.invoices];
const MORE_ITEMS = [NAV.messages, NAV.customers, NAV.quotes, NAV.purchaseOrders, NAV.products, NAV.marketing];

// Overdue + due today: the number of things that need doing now.
function useActionCount() {
  const { data } = useActivityCounts();
  return data ? data.overdue + data.today : 0;
}

function CountBadge({ count, overdue }) {
  if (!count) return null;
  return (
    <span
      className={`ml-auto min-w-[1.25rem] rounded-full px-1.5 py-px text-center text-[11px] font-semibold tabular-nums ${
        overdue ? "bg-red-100 text-red-700" : "bg-zinc-200 text-zinc-700"
      }`}
    >
      {count}
    </span>
  );
}

// Navigation is used dozens of times a day, so it doesn't animate: the
// active state changes instantly; only the color eases, briefly.
function SidebarLink({ to, navKey, icon: ItemIcon, end, badge }) {
  const { t } = useTranslation();
  const { data: counts } = useActivityCounts();
  const { data: inbox } = useInboxCounts();
  const actionCount = counts ? counts.overdue + counts.today : 0;
  return (
    <NavLink
      to={to}
      end={end}
      data-tour={navKey}
      className={({ isActive }) =>
        `group relative flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm font-medium transition-colors duration-150 ${
          isActive ? "bg-white text-zinc-900 shadow-xs ring-1 ring-zinc-200/80" : "text-zinc-600 hover:bg-white/60 hover:text-zinc-900"
        }`
      }
    >
      {({ isActive }) => (
        <>
          {/* Where you are: the one place the spectrum marks navigation. */}
          {isActive && <span className="brand-bg-vertical absolute -left-3 bottom-1.5 top-1.5 w-[3px] rounded-r-full" aria-hidden="true" />}
          <ItemIcon className={`h-[18px] w-[18px] ${isActive ? "text-zinc-900" : "text-zinc-400 group-hover:text-zinc-600"}`} />
          {t(`nav.${navKey}`)}
          {badge === "activities" && <CountBadge count={actionCount} overdue={Boolean(counts?.overdue)} />}
          {badge === "messages" && <CountBadge count={inbox?.unread ?? 0} overdue={false} />}
        </>
      )}
    </NavLink>
  );
}

function MobileTabItem({ to, navKey, shortKey, icon: TabIcon, end, badge }) {
  const { t } = useTranslation();
  const actionCount = useActionCount();
  return (
    <NavLink
      to={to}
      end={end}
      data-tour={navKey}
      className={({ isActive }) =>
        `pressable relative flex h-14 flex-1 flex-col items-center justify-center gap-1 text-[11px] font-medium ${
          isActive ? "text-zinc-900" : "text-zinc-400"
        }`
      }
    >
      {({ isActive }) => (
        <>
          {isActive && <span className="brand-bg absolute inset-x-5 top-0 h-[2px] rounded-b-full" aria-hidden="true" />}
          <span className="relative">
            <TabIcon className="h-[22px] w-[22px]" strokeWidth={isActive ? 2 : 1.7} />
            {badge === "activities" && actionCount > 0 && (
              <span className="absolute -right-2 -top-1 min-w-[1rem] rounded-full bg-red-500 px-1 text-center text-[10px] font-semibold leading-4 text-white">
                {actionCount}
              </span>
            )}
          </span>
          {t(`nav.${shortKey ?? navKey}`)}
        </>
      )}
    </NavLink>
  );
}

/** The weekly quote, once the welcome tour (if any) is out of the way. */
function TeamQuote() {
  const { user } = useAuth();
  const { busy } = useTour();
  if (!user) return null;
  return (
    <QuoteOfTheWeek
      who={user.id}
      hold={busy}
      className="bottom-[calc(var(--tabbar-height)+0.75rem)] md:bottom-6 md:left-[calc(15rem+1rem)]"
    />
  );
}

export default function AppLayout() {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const isAdmin = user?.role === "admin";
  const displayName = user?.full_name || user?.email || "";
  const company = useCompany().data;
  const companyName = company?.company_name ?? "";
  // The company's "Customers"/"Clients" choice; App remounts if it changed.
  useEffect(() => {
    if (company) setCustomerTerm(company.customer_term);
  }, [company]);
  const [moreOpen, setMoreOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  // Anywhere can ask for the profile sheet (e.g. "Edit your signature" in Messages).
  useEffect(() => {
    const open = () => setProfileOpen(true);
    window.addEventListener("ygt:open-profile", open);
    return () => window.removeEventListener("ygt:open-profile", open);
  }, []);
  const { pathname } = useLocation();
  const moreActive = [...MORE_ITEMS.map((i) => i.to), "/settings"].some((to) => pathname.startsWith(to));

  return (
    <TourProvider>
    <div className="min-h-[100dvh] bg-zinc-50">
      <CommandPalette />

      {/* The sign-in aurora, frozen and faint: brand colour at the top of
          every page without anything moving in an app used all day. */}
      <div className="app-ambient" aria-hidden="true">
        <span className="ambient-blob -top-32 left-[18%] h-80 w-[28rem] bg-violet-400" />
        <span className="ambient-blob -top-40 left-[48%] h-80 w-[26rem] bg-sky-300" />
        <span className="ambient-blob -top-24 right-[-6rem] h-72 w-96 bg-emerald-300" />
      </div>

      {/* ---- Sidebar: tablets and up ---- */}
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-60 flex-col border-r border-zinc-200/70 bg-white/55 backdrop-blur-xl md:flex">
        <Link to="/" className="flex items-center gap-2.5 px-5 pb-3 pt-5">
          <BrandMark size="sm" />
          <span className="truncate text-[15px] font-semibold tracking-tight text-zinc-900">{companyName}</span>
        </Link>
        <div className="px-3 pb-2">
          <button
            type="button"
            onClick={openCommandPalette}
            data-tour="search"
            className="flex w-full items-center gap-2 rounded-lg border border-zinc-200/80 bg-white px-2.5 py-1.5 text-sm text-zinc-400 shadow-xs hover:text-zinc-600"
          >
            <SearchIcon className="h-4 w-4" />
            {t("nav.search")}
            <kbd className="ml-auto rounded border border-zinc-200 px-1 text-[10px] font-medium text-zinc-400">Ctrl K</kbd>
          </button>
        </div>
        <nav className="flex-1 space-y-5 overflow-y-auto px-3 pt-2">
          {NAV_GROUPS.map((group, i) => (
            <div key={i}>
              {group.title && <p className="mb-1.5 px-2.5 text-[11px] font-medium uppercase tracking-wider text-zinc-400">{i18n.t(`nav.group.${group.title}`)}</p>}
              <div className="space-y-0.5">
                {group.items.map((item) => (
                  <SidebarLink key={item.to} {...item} />
                ))}
              </div>
            </div>
          ))}
        </nav>
        <div className="space-y-0.5 border-t border-zinc-200/80 p-3">
          {user?.is_platform_admin && <SidebarLink {...NAV.admin} />}
          <SidebarLink {...NAV.support} />
          {isAdmin && <SidebarLink {...NAV.settings} />}
          <SidebarLink {...NAV.help} />
          <SidebarLink {...NAV.about} />
          <div className="px-1 pt-1" data-tour="language">
            <LanguagePicker />
          </div>
          <div className="mt-2 flex items-center gap-2.5 rounded-lg px-2.5 py-2">
            <button
              type="button"
              onClick={() => setProfileOpen(true)}
              className="-m-1 flex min-w-0 flex-1 items-center gap-2.5 rounded-md p-1 text-left transition-colors duration-150 hover:bg-zinc-200/60"
              aria-label={t("nav.profile")}
            >
              <Avatar name={displayName} size="sm" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13px] font-medium text-zinc-900">{displayName}</span>
                <span className="block truncate text-xs text-zinc-500">{user && t(`role.${user.role}`)}</span>
              </span>
            </button>
            <Tooltip label={t("nav.logout")} side="top">
              <button
                type="button"
                onClick={logout}
                aria-label={t("nav.logout")}
                className="pressable rounded-md p-1.5 text-zinc-400 hover:bg-zinc-200/60 hover:text-zinc-700"
              >
                <LogoutIcon className="h-4 w-4" />
              </button>
            </Tooltip>
          </div>
        </div>
      </aside>

      {/* ---- Top bar: phones only. Padded for the notch via safe-area. ---- */}
      <header className="safe-top sticky top-0 z-20 border-b border-zinc-200/80 bg-white/85 backdrop-blur-md md:hidden">
        <div className="flex items-center justify-between px-4 pb-2.5">
          <Link to="/" className="flex min-w-0 items-center gap-2">
            <BrandMark size="sm" />
            <span className="truncate text-[15px] font-semibold tracking-tight text-zinc-900">{companyName}</span>
          </Link>
          <button type="button" onClick={openCommandPalette} aria-label={t("nav.search")} data-tour="search" className="pressable rounded-lg p-2 text-zinc-500">
            <SearchIcon className="h-5 w-5" />
          </button>
        </div>
      </header>

      <main className="relative z-[1] px-4 pb-[calc(var(--tabbar-height)+1.5rem)] pt-5 md:ml-60 md:px-8 md:pb-12 md:pt-8">
        <div className="mx-auto max-w-6xl">
          <LockedBanner />
          <VerifyEmailBanner />
          {/* Some pages load on first visit; the frame and menu stay put meanwhile. */}
          <Suspense fallback={<ListSkeleton rows={5} />}>
            <Outlet />
          </Suspense>
        </div>
      </main>

      {/* ---- Bottom tab bar: phones only. Height is --tabbar-height. ---- */}
      <nav
        className="fixed inset-x-0 bottom-0 z-20 flex border-t border-zinc-200/80 bg-white/90 backdrop-blur-md md:hidden"
        style={{ paddingBottom: "max(env(safe-area-inset-bottom, 0px), 0.5rem)" }}
      >
        {TAB_ITEMS.map((item) => (
          <MobileTabItem key={item.to} {...item} />
        ))}
        <button
          type="button"
          onClick={() => setMoreOpen(true)}
          className={`pressable flex h-14 flex-1 flex-col items-center justify-center gap-1 text-[11px] font-medium ${moreActive ? "text-zinc-900" : "text-zinc-400"}`}
        >
          <MoreIcon className="h-[22px] w-[22px]" />
          {t("nav.more")}
        </button>
      </nav>

      <Sheet open={moreOpen} onClose={() => setMoreOpen(false)} title={t("nav.more")}>
        <div className="-mx-2 space-y-0.5">
          {[...MORE_ITEMS, NAV.support, ...(isAdmin ? [NAV.settings] : []), ...(user?.is_platform_admin ? [NAV.admin] : []), NAV.help, NAV.about].map(({ to, navKey, icon: ItemIcon }) => (
            <Link
              key={to}
              to={to}
              onClick={() => setMoreOpen(false)}
              className="flex items-center gap-3 rounded-lg px-3 py-3 text-[15px] font-medium text-zinc-800 active:bg-zinc-100"
            >
              <ItemIcon className="h-5 w-5 text-zinc-400" />
              {t(`nav.${navKey}`)}
            </Link>
          ))}
          <button
            type="button"
            onClick={() => {
              setMoreOpen(false);
              setProfileOpen(true);
            }}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-3 text-[15px] font-medium text-zinc-800 active:bg-zinc-100"
          >
            <Avatar name={displayName} size="sm" />
            {t("nav.profile")}
          </button>
          <button
            type="button"
            onClick={() => {
              setMoreOpen(false);
              logout();
            }}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-3 text-[15px] font-medium text-zinc-800 active:bg-zinc-100"
          >
            <LogoutIcon className="h-5 w-5 text-zinc-400" />
            {t("nav.logout")}
          </button>
          <LanguagePicker variant="row" onPicked={() => setMoreOpen(false)} />
        </div>
      </Sheet>
      <TeamQuote />
      <ProfileSheet open={profileOpen} onClose={() => setProfileOpen(false)} />
    </div>
    </TourProvider>
  );
}
