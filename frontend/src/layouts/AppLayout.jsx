import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

const NAV_ITEMS = [
  { to: "/", label: "Dashboard", icon: HomeIcon },
  { to: "/settings", label: "Settings", icon: GearIcon, adminOnly: true },
];

function HomeIcon(props) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} {...props}>
      <path d="M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-4v-6H9v6H5a1 1 0 0 1-1-1v-9.5Z" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function GearIcon(props) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} {...props}>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 13a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1.03 1.56V19a2 2 0 1 1-4 0v-.09A1.7 1.7 0 0 0 9 17.35a1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.65 13a1.7 1.7 0 0 0-1.56-1.03H3a2 2 0 1 1 0-4h.09A1.7 1.7 0 0 0 4.65 6.6a1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34H9a1.7 1.7 0 0 0 1.03-1.56V1a2 2 0 1 1 4 0v.09A1.7 1.7 0 0 0 15 4.65a1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87V9a1.7 1.7 0 0 0 1.56 1.03H21a2 2 0 1 1 0 4h-.09A1.7 1.7 0 0 0 19.4 13Z" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function DesktopNavItem({ to, label }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `rounded px-3 py-2 text-sm font-medium ${
          isActive ? "bg-indigo-50 text-indigo-700" : "text-gray-600 hover:bg-gray-100"
        }`
      }
    >
      {label}
    </NavLink>
  );
}

function MobileTabItem({ to, label, Icon }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `flex flex-1 flex-col items-center gap-0.5 py-1.5 text-xs font-medium ${
          isActive ? "text-indigo-700" : "text-gray-500"
        }`
      }
    >
      <Icon className="h-6 w-6" />
      {label}
    </NavLink>
  );
}

export default function AppLayout() {
  const { user, logout } = useAuth();
  const items = NAV_ITEMS.filter((item) => !item.adminOnly || user?.role === "admin");

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Top bar: full nav on desktop, just branding + logout on mobile
          (nav moves to the bottom tab bar below sm). Padded for the iOS
          status bar / notch via safe-area-inset in index.css. */}
      <header className="safe-top flex items-center justify-between border-b bg-white px-4 py-3 sm:px-6">
        <div className="flex items-center gap-1">
          <span className="mr-4 text-sm font-semibold text-gray-800">CRM</span>
          <nav className="hidden sm:flex sm:items-center sm:gap-1">
            {items.map((item) => (
              <DesktopNavItem key={item.to} to={item.to} label={item.label} />
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-3 text-sm text-gray-600">
          <span className="hidden truncate sm:inline">{user?.email}</span>
          <button onClick={logout} className="rounded px-2 py-1 hover:bg-gray-100">
            Log out
          </button>
        </div>
      </header>

      <main className="p-4 pb-20 sm:p-6 sm:pb-6">
        <Outlet />
      </main>

      {/* Bottom tab bar: mobile only. safe-bottom pads for the iOS home
          indicator so tap targets stay clear of the gesture area. */}
      <nav className="safe-bottom fixed inset-x-0 bottom-0 flex border-t bg-white sm:hidden">
        {items.map((item) => (
          <MobileTabItem key={item.to} to={item.to} label={item.label} Icon={item.icon} />
        ))}
      </nav>
    </div>
  );
}
