import { Link, Navigate, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../context/AuthContext";

export default function ProtectedRoute({ children, roles }) {
  const { user, isLoading, logout } = useAuth();
  const { t } = useTranslation();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-zinc-500">
        {t("common.loading")}
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }

  if (user.account_suspended) {
    return (
      <div className="flex min-h-[100dvh] items-center justify-center bg-zinc-50 p-6">
        <div className="card max-w-md p-6 text-center">
          <h1 className="text-xl font-semibold text-zinc-900">{t("suspended.title")}</h1>
          <p className="mt-2 text-sm text-zinc-600">{t("suspended.body")}</p>
          <div className="mt-5 flex justify-center gap-2">
            <Link to="/contact" className="btn btn-primary">
              {t("contact.link")}
            </Link>
            <button type="button" className="btn btn-secondary" onClick={logout}>
              {t("nav.logout")}
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (roles && !roles.includes(user.role)) {
    return <Navigate to="/" replace />;
  }

  return children;
}
