import { Suspense, useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import VerifyEmailBanner from "../components/VerifyEmailBanner";
import MarketingConsentBanner from "../components/MarketingConsentBanner";
import GetTheAppBanner from "../components/GetTheAppBanner";
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
import { LockedBanner, useHasFeature } from "../components/Billing";
import QuoteOfTheWeek from "../components/QuoteOfTheWeek";
import { NotificationList, NotificationPopper, PushToggle, useMyNotifications } from "../components/NotificationCenter";
import { WelcomeSplash, welcomeQueued } from "../components/Startup";
import { useActivityCounts, useCompany, useDiscoveryCounts, useInboxCounts } from "../hooks/useApi";

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
const DiscoveryIcon = (props) => <Icon {...props} d={<><circle cx="12" cy="12" r="9" /><path d="m15.5 8.5-2 5-5 2 2-5 5-2Z" /></>} />;
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
const ReportsIcon = (props) => <Icon {...props} d={<path d="M4 20V10M10 20V4M16 20v-7M21 20H3" />} />;
const BellIcon = (props) => <Icon {...props} d={<><path d="M6 9a6 6 0 1 1 12 0c0 6 2.5 7.5 2.5 7.5h-17S6 15 6 9Z" /><path d="M10 20a2 2 0 0 0 4 0" /></>} />;
const ChevronIcon = (props) => <Icon {...props} d={<path d="m6 9 6 6 6-6" />} />;
const SidebarIcon = (props) => <Icon {...props} d={<><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16" /></>} />;
const LogoutIcon = (props) => (
  <Icon {...props} d={<path d="M15 4h3a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-3M10 8l-4 4 4 4M6 12h10" />} />
);

const NAV = {
  home: { to: "/", navKey: "dashboard", shortKey: "home", icon: HomeIcon, end: true },
  activities: { to: "/activities", navKey: "activities", icon: ActivitiesIcon, badge: "activities" },
  messages: { to: "/messages", navKey: "messages", icon: MessagesIcon, badge: "messages" },
  deals: { to: "/deals", navKey: "deals", icon: DealsIcon },
  discovery: { to: "/discovery", navKey: "discovery", icon: DiscoveryIcon, badge: "discovery" },
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
  reports: { to: "/invoices/aging", navKey: "reports", icon: ReportsIcon, feature: "reports" },
};

// Grouped the way the work flows: your desk, then selling, then the rest.
const NAV_GROUPS = [
  { items: [NAV.home, NAV.activities, NAV.messages] },
  { title: "sales", items: [NAV.customers, NAV.deals, NAV.discovery, NAV.quotes, NAV.invoices, NAV.purchaseOrders] },
  { title: "records", items: [NAV.products, NAV.marketing, NAV.reports] },
];

// Phones: the four places used most, plus "More" for everything else.
const TAB_ITEMS = [NAV.home, NAV.customers, NAV.deals, NAV.invoices];
const MORE_ITEMS = [NAV.activities, NAV.messages, NAV.discovery, NAV.quotes, NAV.purchaseOrders, NAV.products, NAV.marketing, NAV.reports];

// Overdue + due today: the number of things that need doing now.
function useActionCount() {
  const { data } = useActivityCounts();
  return data ? data.overdue + data.today : 0;
}

/** Hides nav items whose feature isn't in the company's plan (e.g. Reports). */
function useVisible() {
  const reports = useHasFeature("reports");
  return (item) => !item.feature || (item.feature === "reports" && reports === true);
}

function CountBadge({ count, urgent, collapsed }) {
  if (!count) return null;
  if (collapsed) {
    return <span className={`absolute right-1.5 top-1.5 h-2 w-2 rounded-full ring-2 ring-midnight ${urgent ? "bg-red-500" : "bg-sky-400"}`} aria-hidden="true" />;
  }
  return (
    <span
      className={`ml-auto min-w-[1.25rem] rounded-full px-1.5 py-px text-center text-[11px] font-semibold tabular-nums ${
        urgent ? "bg-red-500 text-white" : "bg-white/15 text-white"
      }`}
    >
      {count}
    </span>
  );
}

// Navigation is used dozens of times a day, so it doesn't animate: the
// active state changes instantly; only the colour eases, briefly.
function SidebarLink({ to, navKey, icon: ItemIcon, end, badge, collapsed }) {
  const { t } = useTranslation();
  const { data: counts } = useActivityCounts();
  const { data: inbox } = useInboxCounts();
  const { data: found } = useDiscoveryCounts(useHasFeature("discovery") && badge === "discovery");
  const count = { activities: counts ? counts.overdue + counts.today : 0, messages: inbox?.unread ?? 0, discovery: found?.new ?? 0 }[badge] ?? 0;
  const label = t(`nav.${navKey}`);
  const link = (
    <NavLink
      to={to}
      end={end}
      data-tour={navKey}
      aria-label={collapsed ? label : undefined}
      className={({ isActive }) =>
        `group relative flex items-center gap-3 rounded-xl text-sm font-medium transition-colors duration-150 ${collapsed ? "h-10 w-10 justify-center" : "px-3 py-[7px]"} ${
          isActive ? "bg-blue-600 text-white shadow-[0_8px_20px_-8px_rgb(37_99_235/0.7)]" : "text-slate-300 hover:bg-white/[0.07] hover:text-white"
        }`
      }
    >
      {({ isActive }) => (
        <>
          <ItemIcon className={`h-[18px] w-[18px] shrink-0 ${isActive ? "text-white" : "text-slate-400 group-hover:text-white"}`} />
          {!collapsed && <span className="truncate">{label}</span>}
          <CountBadge count={count} urgent={badge === "activities" && Boolean(counts?.overdue)} collapsed={collapsed} />
        </>
      )}
    </NavLink>
  );
  return collapsed ? (
    <Tooltip label={label} side="right">
      {link}
    </Tooltip>
  ) : (
    link
  );
}

function MobileTabItem({ to, navKey, shortKey, icon: TabIcon, end }) {
  const { t } = useTranslation();
  return (
    <NavLink
      to={to}
      end={end}
      data-tour={navKey}
      className={({ isActive }) =>
        `pressable relative flex h-14 flex-1 flex-col items-center justify-center gap-1 text-[11px] font-medium ${isActive ? "text-blue-600" : "text-slate-400"}`
      }
    >
      {({ isActive }) => (
        <>
          {isActive && <span className="absolute inset-x-6 top-0 h-[2px] rounded-b-full bg-blue-600" aria-hidden="true" />}
          <TabIcon className="h-[22px] w-[22px]" strokeWidth={isActive ? 2 : 1.7} />
          <span className="max-w-full truncate px-1">{t(`nav.${shortKey ?? navKey}`)}</span>
        </>
      )}
    </NavLink>
  );
}

/** A small menu under a top-bar button: closes on Escape, an outside click
 *  or choosing an item. Opens instantly (used many times a day). */
function useMenu() {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false);
    const onKey = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  return { open, setOpen, ref };
}

const MENU = "absolute right-0 top-full z-40 mt-2 overflow-hidden rounded-2xl border border-slate-200/80 bg-white py-1.5 shadow-pop";

/** What needs you now, from real counts: things due, unread messages and
 *  new Discovery leads. */
function Notifications() {
  const { t } = useTranslation();
  const { open, setOpen, ref } = useMenu();
  const { data: counts } = useActivityCounts();
  const { data: inbox } = useInboxCounts();
  const discovery = useHasFeature("discovery");
  const { data: found } = useDiscoveryCounts(discovery);
  const rows = [
    { to: "/activities", icon: ActivitiesIcon, count: counts ? counts.overdue + counts.today : 0, text: "activities", urgent: Boolean(counts?.overdue) },
    { to: "/messages", icon: MessagesIcon, count: inbox?.unread ?? 0, text: "messages" },
    ...(discovery ? [{ to: "/discovery", icon: DiscoveryIcon, count: found?.new ?? 0, text: "discovery" }] : []),
  ].filter((r) => r.count > 0);
  const { data: mine } = useMyNotifications();
  const total = rows.reduce((n, r) => n + r.count, 0) + (mine?.unread ?? 0);
  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={total ? t("nav.notificationsCount", { count: total }) : t("nav.notifications")}
        className="pressable relative flex h-10 w-10 items-center justify-center rounded-xl text-slate-500 hover:bg-slate-100 hover:text-slate-900"
      >
        <BellIcon className="h-5 w-5" />
        {total > 0 && (
          <span className="absolute right-1 top-1 min-w-[1.1rem] rounded-full bg-red-500 px-1 text-center text-[10px] font-semibold leading-[1.1rem] text-white ring-2 ring-white">
            {total > 99 ? "99+" : total}
          </span>
        )}
      </button>
      {open && (
        <div className={`${MENU} w-80 max-w-[calc(100vw-2rem)]`} role="menu">
          <p className="px-4 pb-2 pt-1.5 text-xs font-semibold uppercase tracking-wide text-slate-400">{t("nav.notifications")}</p>
          {rows.length ? (
            rows.map((r) => (
              <Link key={r.to} to={r.to} role="menuitem" onClick={() => setOpen(false)} className="flex items-center gap-3 px-4 py-2.5 text-sm text-slate-700 hover:bg-slate-50">
                <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${r.urgent ? "bg-red-50 text-red-600" : "bg-blue-50 text-blue-600"}`}>
                  <r.icon className="h-4 w-4" />
                </span>
                <span className="min-w-0 flex-1">{t(`nav.notify.${r.text}`, { count: r.count })}</span>
              </Link>
            ))
          ) : (
            !mine?.items?.length && <p className="px-4 pb-3 pt-1 text-sm text-slate-500">{t("nav.allCaughtUp")}</p>
          )}
          <NotificationList onNavigate={() => setOpen(false)} />
          <div className="border-t border-slate-100">
            <PushToggle />
          </div>
        </div>
      )}
    </div>
  );
}

function ProfileMenu({ onProfile }) {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const { open, setOpen, ref } = useMenu();
  const name = user?.full_name || user?.email || "";
  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={t("nav.account")}
        className="pressable flex items-center gap-2.5 rounded-xl py-1 pl-1 pr-2 text-left hover:bg-slate-100"
      >
        <Avatar name={name} size="md" />
        <span className="hidden min-w-0 lg:block">
          <span className="block max-w-[11rem] truncate text-sm font-semibold text-slate-900">{name}</span>
          <span className="block text-xs text-slate-500">{user && t(`role.${user.role}`)}</span>
        </span>
        <ChevronIcon className="h-4 w-4 text-slate-400" />
      </button>
      {open && (
        <div className={`${MENU} w-56`} role="menu">
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onProfile();
            }}
            className="block w-full px-4 py-2.5 text-left text-sm text-slate-700 hover:bg-slate-50"
          >
            {t("nav.profile")}
          </button>
          {user?.role === "admin" && (
            <Link to="/settings" role="menuitem" onClick={() => setOpen(false)} className="block px-4 py-2.5 text-sm text-slate-700 hover:bg-slate-50">
              {t("nav.settings")}
            </Link>
          )}
          <div className="my-1 border-t border-slate-100" />
          <button type="button" role="menuitem" onClick={logout} className="block w-full px-4 py-2.5 text-left text-sm text-slate-700 hover:bg-slate-50">
            {t("nav.logout")}
          </button>
        </div>
      )}
    </div>
  );
}

/** The weekly quote, once the welcome tour (if any) is out of the way. */
function TeamQuote() {
  const { user } = useAuth();
  const { busy } = useTour();
  // Just signed in: the team's welcome first, the weekly quote after it.
  const [welcome, setWelcome] = useState(welcomeQueued);
  if (!user) return null;
  return (
    <>
      {/* Been here before (the first visit ends with the tour): "Welcome back". */}
      {welcome && <WelcomeSplash name={user.full_name?.split(" ")[0]} returning={Boolean(user.tour_completed_at)} onClosed={() => setWelcome(false)} />}
      <QuoteOfTheWeek who={user.id} hold={busy || welcome} className="bottom-[calc(var(--tabbar-height)+0.75rem)] md:bottom-6 md:left-[calc(var(--sidebar-w)+1rem)]" />
    </>
  );
}

const SIDEBAR_KEY = "ygt.sidebar.collapsed";
function initiallyCollapsed() {
  try {
    const saved = localStorage.getItem(SIDEBAR_KEY);
    if (saved != null) return saved === "1";
  } catch {
    /* storage blocked: fall through to the screen width */
  }
  return typeof window !== "undefined" && window.innerWidth < 1100;
}

export default function AppLayout() {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const isAdmin = user?.role === "admin";
  const displayName = user?.full_name || user?.email || "";
  const company = useCompany().data;
  const companyName = company?.company_name ?? "";
  const visible = useVisible();
  const actionCount = useActionCount();
  // The company's "Customers"/"Clients" choice; App remounts if it changed.
  useEffect(() => {
    if (company) setCustomerTerm(company.customer_term);
  }, [company]);
  const [moreOpen, setMoreOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(initiallyCollapsed);
  const toggleSidebar = () =>
    setCollapsed((c) => {
      try {
        localStorage.setItem(SIDEBAR_KEY, c ? "0" : "1");
      } catch {
        /* storage blocked: still toggles for this visit */
      }
      return !c;
    });
  // Anywhere can ask for the profile sheet (e.g. "Edit your signature" in Messages).
  useEffect(() => {
    const open = () => setProfileOpen(true);
    window.addEventListener("ygt:open-profile", open);
    return () => window.removeEventListener("ygt:open-profile", open);
  }, []);
  const { pathname } = useLocation();
  const moreItems = MORE_ITEMS.filter(visible);
  const moreActive = [...moreItems.map((i) => i.to), "/settings"].some((to) => pathname.startsWith(to));
  const railCls = collapsed ? "flex flex-col items-center px-0" : "px-3";

  return (
    <TourProvider>
      <div className="min-h-[100dvh] bg-canvas" style={{ "--sidebar-w": collapsed ? "4.75rem" : "16rem" }}>
        <CommandPalette />

        {/* ---- Sidebar: tablets and up. Midnight, the current page in blue. ---- */}
        <aside className="fixed inset-y-0 left-0 z-20 hidden w-[var(--sidebar-w)] flex-col bg-midnight text-white md:flex">
          <Link to="/" className={`flex items-center gap-2.5 pb-4 pt-5 ${collapsed ? "justify-center" : "px-5"}`}>
            <BrandMark size="md" />
            {!collapsed && (
              <span className="min-w-0">
                <span className="block truncate text-[15px] font-semibold tracking-tight">{companyName}</span>
                <span className="block text-[11px] text-slate-400">{t("nav.tagline")}</span>
              </span>
            )}
          </Link>
          <nav className={`flex-1 space-y-4 overflow-y-auto pb-3 pt-1 [scrollbar-width:thin] ${railCls}`} aria-label={t("nav.main")}>
            {NAV_GROUPS.map((group, i) => (
              <div key={i} className={collapsed ? "flex flex-col items-center" : ""}>
                {group.title &&
                  (collapsed ? (
                    <span className="mx-auto mb-2 block h-px w-6 bg-white/10" aria-hidden="true" />
                  ) : (
                    <p className="mb-1.5 px-3 text-[11px] font-semibold uppercase tracking-wider text-slate-500">{i18n.t(`nav.group.${group.title}`)}</p>
                  ))}
                <div className={`space-y-1 ${collapsed ? "flex flex-col items-center" : ""}`}>
                  {group.items.filter(visible).map((item) => (
                    <SidebarLink key={item.to} {...item} collapsed={collapsed} />
                  ))}
                </div>
              </div>
            ))}
          </nav>
          <div className={`space-y-0.5 border-t border-white/10 py-2.5 ${railCls}`}>
            {user?.is_platform_admin && <SidebarLink {...NAV.admin} collapsed={collapsed} />}
            <SidebarLink {...NAV.support} collapsed={collapsed} />
            {isAdmin && <SidebarLink {...NAV.settings} collapsed={collapsed} />}
            <SidebarLink {...NAV.help} collapsed={collapsed} />
            <SidebarLink {...NAV.about} collapsed={collapsed} />
          </div>
        </aside>

        {/* ---- Top bar: tablets and up ---- */}
        <header className="sticky top-0 z-10 hidden h-16 items-center gap-3 border-b border-slate-200/70 bg-white/85 px-4 backdrop-blur-md md:ml-[var(--sidebar-w)] md:flex lg:px-6">
          <Tooltip label={t(collapsed ? "nav.expand" : "nav.collapse")} side="bottom">
            <button
              type="button"
              onClick={toggleSidebar}
              aria-label={t(collapsed ? "nav.expand" : "nav.collapse")}
              aria-pressed={collapsed}
              className="pressable flex h-10 w-10 items-center justify-center rounded-xl text-slate-500 hover:bg-slate-100 hover:text-slate-900"
            >
              <SidebarIcon className="h-5 w-5" />
            </button>
          </Tooltip>
          <button
            type="button"
            onClick={openCommandPalette}
            aria-label={t("nav.searchWide")}
            data-tour="search"
            className="flex h-10 min-w-0 max-w-md flex-1 items-center gap-2.5 rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-400 shadow-xs transition-colors duration-150 hover:border-slate-300 hover:text-slate-600"
          >
            <SearchIcon className="h-4 w-4 shrink-0" />
            <SearchLabel wide={t("nav.searchWide")} short={t("nav.search")} />
            <kbd className="ml-auto hidden shrink-0 rounded-md border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[10px] font-medium text-slate-400 lg:inline">Ctrl K</kbd>
          </button>
          <div className="ml-auto flex shrink-0 items-center gap-1.5">
            <Notifications />
            <div data-tour="language">
              <LanguagePicker variant="compact" />
            </div>
            <span className="mx-1 h-6 w-px bg-slate-200" aria-hidden="true" />
            <ProfileMenu onProfile={() => setProfileOpen(true)} />
          </div>
        </header>

        {/* ---- Top bar: phones only. Padded for the notch via safe-area. ---- */}
        <header className="safe-top sticky top-0 z-20 border-b border-slate-200/80 bg-white/90 backdrop-blur-md md:hidden">
          <div className="flex items-center justify-between gap-2 px-4 pb-2.5">
            <Link to="/" className="flex min-w-0 items-center gap-2">
              <BrandMark size="sm" />
              <span className="truncate text-[15px] font-semibold tracking-tight text-slate-900">{companyName}</span>
            </Link>
            <div className="flex items-center">
              <button type="button" onClick={openCommandPalette} aria-label={t("nav.search")} data-tour="search" className="pressable rounded-lg p-2 text-slate-500">
                <SearchIcon className="h-5 w-5" />
              </button>
              <Notifications />
            </div>
          </div>
        </header>

        <main className="relative z-[1] px-4 pb-[calc(var(--tabbar-height)+1.5rem)] pt-5 md:ml-[var(--sidebar-w)] md:px-6 md:pb-12 md:pt-6 lg:px-8">
          <GetTheAppBanner />
          <div className="mx-auto max-w-[88rem]">
            <LockedBanner />
            <VerifyEmailBanner />
            <MarketingConsentBanner />
            {/* Some pages load on first visit; the frame and menu stay put meanwhile. */}
            <Suspense fallback={<ListSkeleton rows={5} />}>
              <Outlet />
            </Suspense>
          </div>
        </main>

        {/* ---- Bottom tab bar: phones only. Height is --tabbar-height. ---- */}
        <nav
          className="fixed inset-x-0 bottom-0 z-20 flex border-t border-slate-200/80 bg-white/95 backdrop-blur-md md:hidden"
          style={{ paddingBottom: "max(env(safe-area-inset-bottom, 0px), 0.5rem)" }}
          aria-label={t("nav.main")}
        >
          {TAB_ITEMS.map((item) => (
            <MobileTabItem key={item.to} {...item} />
          ))}
          <button
            type="button"
            onClick={() => setMoreOpen(true)}
            className={`pressable relative flex h-14 flex-1 flex-col items-center justify-center gap-1 text-[11px] font-medium ${moreActive ? "text-blue-600" : "text-slate-400"}`}
          >
            <span className="relative">
              <MoreIcon className="h-[22px] w-[22px]" />
              {actionCount > 0 && <span className="absolute -right-1.5 -top-1 h-2.5 w-2.5 rounded-full bg-red-500 ring-2 ring-white" aria-hidden="true" />}
            </span>
            {t("nav.more")}
          </button>
        </nav>

        <Sheet open={moreOpen} onClose={() => setMoreOpen(false)} title={t("nav.more")}>
          <div className="-mx-2 space-y-0.5">
            {[...moreItems, NAV.support, ...(isAdmin ? [NAV.settings] : []), ...(user?.is_platform_admin ? [NAV.admin] : []), NAV.help, NAV.about].map(
              ({ to, navKey, icon: ItemIcon, badge }) => (
                <Link
                  key={to}
                  to={to}
                  onClick={() => setMoreOpen(false)}
                  className="flex items-center gap-3 rounded-lg px-3 py-3 text-[15px] font-medium text-slate-800 active:bg-slate-100"
                >
                  <ItemIcon className="h-5 w-5 text-slate-400" />
                  {t(`nav.${navKey}`)}
                  {badge === "activities" && actionCount > 0 && (
                    <span className="ml-auto min-w-[1.25rem] rounded-full bg-red-500 px-1.5 text-center text-[11px] font-semibold leading-5 text-white">{actionCount}</span>
                  )}
                </Link>
              )
            )}
            <button
              type="button"
              onClick={() => {
                setMoreOpen(false);
                setProfileOpen(true);
              }}
              className="flex w-full items-center gap-3 rounded-lg px-3 py-3 text-[15px] font-medium text-slate-800 active:bg-slate-100"
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
              className="flex w-full items-center gap-3 rounded-lg px-3 py-3 text-[15px] font-medium text-slate-800 active:bg-slate-100"
            >
              <LogoutIcon className="h-5 w-5 text-slate-400" />
              {t("nav.logout")}
            </button>
            <LanguagePicker variant="row" onPicked={() => setMoreOpen(false)} />
          </div>
        </Sheet>
        <TeamQuote />
        <NotificationPopper />
        <ProfileSheet open={profileOpen} onClose={() => setProfileOpen(false)} />
      </div>
    </TourProvider>
  );
}

// The full "Search customers, deals, quotes…" when it fits, otherwise just
// "Search": some languages run much longer, and a cut-off sentence reads badly.
function SearchLabel({ wide, short }) {
  const box = useRef(null);
  const measure = useRef(null);
  const [fits, setFits] = useState(true);
  useEffect(() => {
    const check = () => box.current && measure.current && setFits(measure.current.offsetWidth <= box.current.clientWidth);
    check();
    const observer = new ResizeObserver(check);
    if (box.current) observer.observe(box.current);
    return () => observer.disconnect();
  }, [wide]);
  return (
    <span ref={box} className="relative min-w-0 flex-1 overflow-hidden text-left" aria-hidden="true">
      <span ref={measure} className="invisible absolute whitespace-nowrap">{wide}</span>
      <span className="whitespace-nowrap">{fits ? wide : short}</span>
    </span>
  );
}
