import { lazy, Suspense } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../context/AuthContext";
import { VerifyGate, verificationOverdue } from "./VerifyEmailBanner";

// The public home page: what YGT is, for visitors who aren't signed in.
const HomePage = lazy(() => import("../pages/HomePage"));

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
    // yougt.co.za itself shows the home page; any other app page asks to sign in.
    if (location.pathname === "/") {
      return (
        <Suspense fallback={null}>
          <HomePage />
        </Suspense>
      );
    }
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

  // 48 hours on without a confirmed email: confirm first, then carry on.
  if (verificationOverdue(user)) return <VerifyGate />;

  if (roles && !roles.includes(user.role)) {
    return <Navigate to="/" replace />;
  }

  return children;
}
