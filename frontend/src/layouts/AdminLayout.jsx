import { Link, NavLink, Navigate, Outlet } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import apiClient from "../services/apiClient";
import { useAuth } from "../context/AuthContext";
import { BrandMark } from "../components/Brand";

// The admin site is for YGT's own team, so it's English only.
const NAV = [
  { to: "/admin", label: "Overview", end: true },
  { to: "/admin/tenants", label: "Tenants" },
  { to: "/admin/tickets", label: "Help desk", badge: "open_tickets" },
  { to: "/admin/contact", label: "Contact requests", badge: "new_contacts" },
  { to: "/admin/bookings", label: "Sessions", badge: "upcoming_bookings" },
  { to: "/admin/errors", label: "Error log", badge: "errors_24h", danger: true },
  { to: "/admin/activity", label: "Activity" },
];

export function useAdminOverview() {
  return useQuery({ queryKey: ["admin", "overview"], queryFn: () => apiClient.get("/admin/overview").then((r) => r.data), refetchInterval: 60_000 });
}

export default function AdminLayout() {
  const { user, logout } = useAuth();
  const { data: overview } = useAdminOverview();
  if (!user?.is_platform_admin) return <Navigate to="/" replace />;
  return (
    <div className="min-h-[100dvh] bg-zinc-50 md:grid md:grid-cols-[15rem_minmax(0,1fr)]">
      <aside className="flex flex-col bg-zinc-950 text-zinc-300 md:sticky md:top-0 md:h-[100dvh]">
        <div className="flex items-center gap-2.5 px-5 py-5">
          <BrandMark size="sm" />
          <span className="font-semibold text-white">YGT admin</span>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-1 md:flex-col md:overflow-visible" aria-label="Admin">
          {NAV.map((item) => {
            const count = item.badge && overview ? overview[item.badge] : 0;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `flex shrink-0 items-center justify-between gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors duration-150 ${
                    isActive ? "bg-white/10 text-white" : "hover:bg-white/5 hover:text-white"
                  }`
                }
              >
                {item.label}
                {count > 0 && (
                  <span className={`rounded-full px-1.5 text-[11px] font-semibold tabular-nums ${item.danger ? "bg-rose-500 text-white" : "bg-white/15 text-white"}`}>{count}</span>
                )}
              </NavLink>
            );
          })}
        </nav>
        <div className="hidden border-t border-white/10 p-4 text-sm md:block">
          <p className="truncate text-white">{user.full_name}</p>
          <p className="truncate text-xs text-zinc-500">{user.email}</p>
          <div className="mt-3 flex gap-3 text-xs">
            <Link to="/" className="hover:text-white">
              Back to the app
            </Link>
            <button type="button" onClick={logout} className="hover:text-white">
              Sign out
            </button>
          </div>
        </div>
      </aside>
      <main className="min-w-0 px-4 py-6 md:px-8 md:py-8">
        <div className="mx-auto max-w-6xl">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
