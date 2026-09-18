import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

function NavItem({ to, children }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `rounded px-3 py-2 text-sm font-medium ${
          isActive ? "bg-indigo-50 text-indigo-700" : "text-gray-600 hover:bg-gray-100"
        }`
      }
    >
      {children}
    </NavLink>
  );
}

export default function AppLayout() {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="flex items-center justify-between border-b bg-white px-6 py-3">
        <div className="flex items-center gap-1">
          <span className="mr-4 text-sm font-semibold text-gray-800">CRM</span>
          <NavItem to="/">Dashboard</NavItem>
          {user?.role === "admin" && <NavItem to="/settings">Settings</NavItem>}
        </div>
        <div className="flex items-center gap-3 text-sm text-gray-600">
          <span>{user?.email}</span>
          <button onClick={logout} className="rounded px-2 py-1 hover:bg-gray-100">
            Log out
          </button>
        </div>
      </header>
      <main className="p-6">
        <Outlet />
      </main>
    </div>
  );
}
