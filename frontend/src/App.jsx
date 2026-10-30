import { lazy, Suspense, useEffect, useState } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getCustomerTerm } from "./i18n";
import ProtectedRoute from "./components/ProtectedRoute";
import { VisitTracker } from "./utils/visits";

// Pages people open less often load the first time they're visited, so the
// everyday screens above reach a phone sooner.
const named = (load, name) => lazy(() => load().then((module) => ({ default: module[name] })));
// Every page loads on its own, when it's first opened: a visitor reading the
// home page or signing in doesn't download the whole app first.
const AppLayout = lazy(() => import("./layouts/AppLayout"));
const ActivitiesPage = lazy(() => import("./pages/ActivitiesPage"));
const CustomerDetailPage = lazy(() => import("./pages/CustomerDetailPage"));
const CustomersPage = lazy(() => import("./pages/CustomersPage"));
const DealDetailPage = lazy(() => import("./pages/DealDetailPage"));
const DealsPage = lazy(() => import("./pages/DealsPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const InvoiceDetailPage = lazy(() => import("./pages/InvoiceDetailPage"));
const invoicePages = () => import("./pages/InvoicesPage");
const InvoicesPage = named(invoicePages, "InvoicesPage");
const NewInvoicePage = named(invoicePages, "NewInvoicePage");
const loginPages = () => import("./pages/LoginPage");
const LoginPage = lazy(loginPages);
const RegisterPage = named(loginPages, "RegisterPage");
const ProductsPage = lazy(() => import("./pages/ProductsPage"));
const quotePages = () => import("./pages/QuotesPage");
const NewQuotePage = named(quotePages, "NewQuotePage");
const QuoteDetailPage = named(quotePages, "QuoteDetailPage");
const QuotesPage = named(quotePages, "QuotesPage");
const AboutPage = lazy(() => import("./pages/AboutPage"));
const AssessmentPage = lazy(() => import("./pages/AssessmentPage"));
const MarketingPage = lazy(() => import("./pages/MarketingPage"));
const MessagesPage = lazy(() => import("./pages/MessagesPage"));
const HelpPage = lazy(() => import("./pages/HelpPage"));
const CampaignPage = lazy(() => import("./pages/CampaignPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const StatementPage = lazy(() => import("./pages/StatementPage"));
const ReceivablesPage = lazy(() => import("./pages/ReceivablesPage"));
const DiscoveryPage = lazy(() => import("./pages/DiscoveryPage"));
const EditDocumentPage = lazy(() => import("./pages/EditDocumentPage"));
const EditRecurringInvoicePage = named(() => import("./pages/RecurringInvoicesPage"), "EditRecurringInvoicePage");
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
const InvitePage = named(publicPages, "InvitePage");
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
const AdminVisitors = named(adminPages, "AdminVisitors");

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
    <VisitTracker />
    <Routes key={`${i18n.language}-${term}`}>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/about" element={<AboutPage />} />
      <Route path="/assessment" element={<AssessmentPage />} />
      <Route path="/contact" element={<ContactPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/verify-email" element={<VerifyEmailPage />} />
      <Route path="/invite" element={<InvitePage />} />
      <Route path="/terms" element={<LegalPage kind="terms" />} />
      <Route path="/privacy" element={<LegalPage kind="privacy" />} />
      <Route path="/refunds" element={<LegalPage kind="refunds" />} />
      <Route path="/delete-account" element={<LegalPage kind="deleteAccount" />} />
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
        <Route path="visitors" element={<AdminVisitors />} />
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
        <Route path="/discovery" element={<DiscoveryPage />} />
        <Route path="/invoices/recurring" element={<RecurringInvoicesPage />} />
        <Route path="/invoices/recurring/new" element={<NewRecurringInvoicePage />} />
        <Route path="/invoices/recurring/:id" element={<RecurringInvoiceDetailPage />} />
        <Route path="/invoices/recurring/:id/edit" element={<EditRecurringInvoicePage />} />
        <Route path="/invoices/:id/edit" element={<EditDocumentPage kind="invoice" />} />
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
        <Route path="/quotes/:id/edit" element={<EditDocumentPage kind="quote" />} />
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
        <Route path="/purchase-orders/:id/edit" element={<EditDocumentPage kind="purchaseOrder" />} />
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
