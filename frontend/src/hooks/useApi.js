import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import apiClient from "../services/apiClient";

const get = (url, params) => apiClient.get(url, { params }).then((res) => res.data);

// List endpoints cap at 200 rows. That covers a small business's whole
// customer/product book; paging can come when a real dataset outgrows it.
const LIST_LIMIT = 200;

export function useCompany() {
  return useQuery({ queryKey: ["company"], queryFn: () => get("/company"), staleTime: 5 * 60_000 });
}

export function useCustomers(params = {}) {
  return useQuery({
    queryKey: ["customers", params],
    queryFn: () => get("/customers", { limit: LIST_LIMIT, ...params }),
  });
}

export function useProducts(params = {}) {
  return useQuery({
    queryKey: ["products", params],
    queryFn: () => get("/products", { limit: LIST_LIMIT, ...params }),
  });
}

export function useInvoices(params = {}) {
  return useQuery({
    queryKey: ["invoices", params],
    queryFn: () => get("/invoices", { limit: LIST_LIMIT, ...params }),
  });
}

export function useInvoice(id) {
  return useQuery({ queryKey: ["invoice", id], queryFn: () => get(`/invoices/${id}`) });
}

export function usePayments(invoiceId) {
  return useQuery({
    queryKey: ["payments", invoiceId],
    queryFn: () => get(`/invoices/${invoiceId}/payments`),
  });
}

export function useReminders(invoiceId) {
  return useQuery({
    queryKey: ["reminders", invoiceId],
    queryFn: () => get(`/invoices/${invoiceId}/reminders`),
  });
}

export function useQuotes(params = {}) {
  return useQuery({
    queryKey: ["quotes", params],
    queryFn: () => get("/quotes", { limit: LIST_LIMIT, ...params }),
  });
}

export function useQuote(id) {
  return useQuery({ queryKey: ["quote", id], queryFn: () => get(`/quotes/${id}`) });
}

export function useSuppliers(params = {}) {
  return useQuery({ queryKey: ["suppliers", params], queryFn: () => get("/suppliers", params) });
}

// Purchase orders only carry supplier_id; lists resolve names through this.
export function useSupplierMap() {
  const { data } = useSuppliers({ include_inactive: true });
  return useMemo(() => new Map((data ?? []).map((s) => [s.id, s])), [data]);
}

export function usePurchaseOrders(params = {}) {
  return useQuery({ queryKey: ["purchase-orders", params], queryFn: () => get("/purchase-orders", { limit: LIST_LIMIT, ...params }) });
}

export function usePurchaseOrder(id) {
  return useQuery({ queryKey: ["purchase-order", id], queryFn: () => get(`/purchase-orders/${id}`) });
}

// Saved sets of line items, shared by everyone in the company.
export function useLineTemplates() {
  return useQuery({ queryKey: ["line-templates"], queryFn: () => get("/line-templates") });
}

// Invoices and quotes only carry customer_id; lists resolve names through
// this map (one cached customers query shared by every screen).
export function useCustomerMap() {
  const { data } = useCustomers();
  return useMemo(() => new Map((data ?? []).map((c) => [c.id, c])), [data]);
}

// ---------- CRM ----------

export function useTeam() {
  return useQuery({ queryKey: ["team"], queryFn: () => get("/team"), staleTime: 5 * 60_000 });
}

export function useTeamMap() {
  const { data } = useTeam();
  return useMemo(() => new Map((data ?? []).map((u) => [u.id, u])), [data]);
}

export function useCustomer(id) {
  return useQuery({ queryKey: ["customer", id], queryFn: () => get(`/customers/${id}`), enabled: Boolean(id) });
}

export function useContacts(customerId) {
  return useQuery({
    queryKey: ["contacts", customerId],
    queryFn: () => get(`/customers/${customerId}/contacts`),
    enabled: Boolean(customerId),
  });
}

export function useDeals(params = {}) {
  return useQuery({ queryKey: ["deals", params], queryFn: () => get("/deals", params) });
}

export function useDeal(id) {
  return useQuery({ queryKey: ["deal", id], queryFn: () => get(`/deals/${id}`) });
}

export function useDealQuotes(id) {
  return useQuery({ queryKey: ["deal-quotes", id], queryFn: () => get(`/deals/${id}/quotes`) });
}

export function useActivities(params = {}, options = {}) {
  return useQuery({ queryKey: ["activities", params], queryFn: () => get("/activities", params), ...options });
}

export function useActivityCounts() {
  return useQuery({ queryKey: ["activities", "counts"], queryFn: () => get("/activities/counts") });
}

export function useTimeline(kind, id) {
  const path = kind === "deal" ? `/deals/${id}/timeline` : `/customers/${id}/timeline`;
  return useQuery({ queryKey: ["timeline", kind, id], queryFn: () => get(path) });
}

// Admin-defined extra fields; rarely change, so cache them for a while.
export function useCustomFields(entity) {
  return useQuery({
    queryKey: ["custom-fields", entity],
    queryFn: () => get("/custom-fields", { entity }),
    staleTime: 5 * 60_000,
  });
}

// ---------- Messages ----------

export function useConversations(params = {}) {
  return useQuery({ queryKey: ["conversations", params], queryFn: () => get("/conversations", params), refetchInterval: 15_000 });
}

export function useConversation(id) {
  return useQuery({
    queryKey: ["conversation", id],
    queryFn: () => get(`/conversations/${id}`),
    enabled: Boolean(id),
    // Customer replies arrive by email at any moment; poll the open thread.
    refetchInterval: 8_000,
  });
}

export function useInboxCounts() {
  return useQuery({ queryKey: ["conversations", "counts"], queryFn: () => get("/conversations/counts"), refetchInterval: 30_000 });
}

/** Which channels this company has connected (Settings), for the composer. */
export function useAvailableChannels() {
  return useQuery({ queryKey: ["available-channels"], queryFn: () => get("/conversations/channels"), staleTime: 60_000 });
}

export function useInboxAddress() {
  return useQuery({ queryKey: ["inbox-address"], queryFn: () => get("/conversations/inbox-address"), staleTime: Infinity });
}

export function useChannels() {
  return useQuery({ queryKey: ["team-channels"], queryFn: () => get("/team-chat/channels") });
}

export function useTeamMessages(channelId) {
  return useQuery({
    queryKey: ["team-messages", channelId],
    queryFn: () => get(`/team-chat/channels/${channelId}/messages`),
    enabled: Boolean(channelId),
    refetchInterval: 4_000,
  });
}

// ---------- Marketing ----------

export function useCampaigns() {
  return useQuery({ queryKey: ["campaigns"], queryFn: () => get("/marketing/campaigns") });
}

export function useCampaign(id) {
  return useQuery({
    queryKey: ["campaign", id],
    queryFn: () => get(`/marketing/campaigns/${id}`),
    // A campaign that's going out updates its counts as the worker sends.
    refetchInterval: (query) => (query.state.data?.status === "sending" ? 2000 : false),
  });
}

export function useCampaignRecipients(id, enabled) {
  return useQuery({ queryKey: ["campaign", id, "recipients"], queryFn: () => get(`/marketing/campaigns/${id}/recipients`), enabled });
}

export function useSegments() {
  return useQuery({ queryKey: ["segments"], queryFn: () => get("/marketing/segments") });
}

/** Live count of who matches a set of audience rules (saved or not). */
export function useAudience(rules) {
  return useQuery({
    queryKey: ["audience", rules],
    queryFn: () => apiClient.post("/marketing/audience/preview", { rules }).then((r) => r.data),
    placeholderData: (previous) => previous,
  });
}

// ---------- Reports ----------

export function useReportSummary() {
  return useQuery({ queryKey: ["reports", "summary"], queryFn: () => get("/reports/summary") });
}

export function useAgedReceivables({ enabled = true } = {}) {
  return useQuery({ queryKey: ["reports", "aged-receivables"], queryFn: () => get("/reports/aged-receivables"), enabled });
}

export function useCustomerOverview(params = {}) {
  return useQuery({ queryKey: ["reports", "customers", params], queryFn: () => get("/reports/customers", params) });
}

// The company's plan, what it includes and how much of it is used.
// New Discovery leads (Scale only: pass whether the plan includes it).
export function useDiscoveryCounts(enabled) {
  return useQuery({ queryKey: ["discovery", "counts"], queryFn: () => get("/discovery/counts"), enabled: Boolean(enabled), staleTime: 60_000 });
}

export function useBilling() {
  return useQuery({ queryKey: ["billing"], queryFn: () => get("/billing"), staleTime: 60_000 });
}

// Prices, for Settings > Billing (signed in) and the About page (anyone).
export function usePlans() {
  return useQuery({ queryKey: ["plans"], queryFn: () => get("/public/plans"), staleTime: 60 * 60_000 });
}
