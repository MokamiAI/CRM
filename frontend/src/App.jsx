import { lazy, Suspense, useEffect, useState } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getCustomerTerm } from "./i18n";
import ProtectedRoute from "./components/ProtectedRoute";
import AppLayout from "./layouts/AppLayout";
import ActivitiesPage from "./pages/ActivitiesPage";
import CustomerDetailPage from "./pages/CustomerDetailPage";
import CustomersPage from "./pages/CustomersPage";
import DealDetailPage from "./pages/DealDetailPage";
import DealsPage from "./pages/DealsPage";
import DashboardPage from "./pages/DashboardPage";
import InvoiceDetailPage from "./pages/InvoiceDetailPage";
import { InvoicesPage, NewInvoicePage } from "./pages/InvoicesPage";
import LoginPage, { RegisterPage } from "./pages/LoginPage";
import ProductsPage from "./pages/ProductsPage";
import { NewQuotePage, QuoteDetailPage, QuotesPage } from "./pages/QuotesPage";

// Pages people open less often load the first time they're visited, so the
// everyday screens above reach a phone sooner.
const named = (load, name) => lazy(() => load().then((module) => ({ default: module[name] })));
const AboutPage = lazy(() => import("./pages/AboutPage"));
const MarketingPage = lazy(() => import("./pages/MarketingPage"));
const MessagesPage = lazy(() => import("./pages/MessagesPage"));
const HelpPage = lazy(() => import("./pages/HelpPage"));
const CampaignPage = lazy(() => import("./pages/CampaignPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const StatementPage = lazy(() => import("./pages/StatementPage"));
const ReceivablesPage = lazy(() => import("./pages/ReceivablesPage"));
const RecurringInvoicesPage = named(() => import("./pages/RecurringInvoicesPage"), "RecurringInvoicesPage");
const NewRecurringInvoicePage = named(() => import("./pages/RecurringInvoicesPage"), "NewRecurringInvoicePage");
const RecurringInvoiceDetailPage = named(() => import("./pages/RecurringInvoicesPage"), "RecurringInvoiceDetailPage");
const PurchaseOrdersPage = lazy(() => import("./pages/PurchaseOrdersPage"));
const NewPurchaseOrderPage = named(() => import("./pages/PurchaseOrdersPage"), "NewPurchaseOrderPage");
const PurchaseOrderDetailPage = named(() => import("./pages/PurchaseOrdersPage"), "PurchaseOrderDetailPage");
const SupportPage = lazy(() => import("./pages/SupportPage"));
const TicketPage = named(() => import("./pages/SupportPage"), "TicketPage");
const publicPages = () => import("./pages/PublicPages");
const ContactPage = named(publicPages, "ContactPage");
const ForgotPasswordPage = named(publicPages, "ForgotPasswordPage");
const LegalPage = named(publicPages, "LegalPage");
const ResetPasswordPage = named(publicPages, "ResetPasswordPage");
const VerifyEmailPage = named(publicPages, "VerifyEmailPage");
const AdminLayout = lazy(() => import("./layouts/AdminLayout"));
const adminPages = () => import("./pages/admin/AdminPages");
const AdminActivity = named(adminPages, "AdminActivity");
const AdminBookings = named(adminPages, "AdminBookings");
const AdminContact = named(adminPages, "AdminContact");
const AdminErrors = named(adminPages, "AdminErrors");
const AdminOverview = named(adminPages, "AdminOverview");
const AdminTenant = named(adminPages, "AdminTenant");
const AdminTenants = named(adminPages, "AdminTenants");
const AdminTicket = named(adminPages, "AdminTicket");
const AdminTickets = named(adminPages, "AdminTickets");

const WRITERS = ["admin", "manager", "staff"];

export default function App() {
  // Keyed on the language (and the customer/client wording) so a switch
  // re-renders every screen at once: text, and also the dates and amounts
  // formatted for that locale.
  const { i18n } = useTranslation();
  const [term, setTerm] = useState(getCustomerTerm);
  useEffect(() => {
    i18n.on("customerTermChanged", setTerm);
    return () => i18n.off("customerTermChanged", setTerm);
  }, [i18n]);
  return (
    <Suspense fallback={null}>
    <Routes key={`${i18n.language}-${term}`}>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/about" element={<AboutPage />} />
      <Route path="/contact" element={<ContactPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/verify-email" element={<VerifyEmailPage />} />
      <Route path="/terms" element={<LegalPage kind="terms" />} />
      <Route path="/privacy" element={<LegalPage kind="privacy" />} />
      <Route path="/refunds" element={<LegalPage kind="refunds" />} />
      {/* YGT's own admin site; AdminLayout lets only platform admins in. */}
      <Route
        path="/admin"
        element={
          <ProtectedRoute>
            <AdminLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<AdminOverview />} />
        <Route path="tenants" element={<AdminTenants />} />
        <Route path="tenants/:id" element={<AdminTenant />} />
        <Route path="tickets" element={<AdminTickets />} />
        <Route path="tickets/:id" element={<AdminTicket />} />
        <Route path="contact" element={<AdminContact />} />
        <Route path="bookings" element={<AdminBookings />} />
        <Route path="errors" element={<AdminErrors />} />
        <Route path="activity" element={<AdminActivity />} />
      </Route>
      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<DashboardPage />} />
        <Route path="/invoices" element={<InvoicesPage />} />
        <Route
          path="/invoices/new"
          element={
            <ProtectedRoute roles={WRITERS}>
              <NewInvoicePage />
            </ProtectedRoute>
          }
        />
        <Route path="/invoices/aging" element={<ReceivablesPage />} />
        <Route path="/invoices/recurring" element={<RecurringInvoicesPage />} />
        <Route path="/invoices/recurring/new" element={<NewRecurringInvoicePage />} />
        <Route path="/invoices/recurring/:id" element={<RecurringInvoiceDetailPage />} />
        <Route path="/invoices/:id" element={<InvoiceDetailPage />} />
        <Route path="/quotes" element={<QuotesPage />} />
        <Route
          path="/quotes/new"
          element={
            <ProtectedRoute roles={WRITERS}>
              <NewQuotePage />
            </ProtectedRoute>
          }
        />
        <Route path="/quotes/:id" element={<QuoteDetailPage />} />
        <Route path="/purchase-orders" element={<PurchaseOrdersPage />} />
        <Route
          path="/purchase-orders/new"
          element={
            <ProtectedRoute roles={WRITERS}>
              <NewPurchaseOrderPage />
            </ProtectedRoute>
          }
        />
        <Route path="/purchase-orders/:id" element={<PurchaseOrderDetailPage />} />
        <Route path="/activities" element={<ActivitiesPage />} />
        <Route path="/messages" element={<MessagesPage />} />
        <Route path="/help" element={<HelpPage />} />
        <Route path="/support" element={<SupportPage />} />
        <Route path="/support/tickets/:id" element={<TicketPage />} />
        <Route path="/deals" element={<DealsPage />} />
        <Route path="/deals/:id" element={<DealDetailPage />} />
        <Route path="/customers" element={<CustomersPage />} />
        <Route path="/customers/:id" element={<CustomerDetailPage />} />
        <Route path="/customers/:id/statement" element={<StatementPage />} />
        <Route path="/products" element={<ProductsPage />} />
        <Route path="/marketing" element={<MarketingPage />} />
        <Route path="/marketing/campaigns/:id" element={<CampaignPage />} />
        <Route
          path="/settings"
          element={
            <ProtectedRoute roles={["admin"]}>
              <SettingsPage />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
    </Suspense>
  );
}
