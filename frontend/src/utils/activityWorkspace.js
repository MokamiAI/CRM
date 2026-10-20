// The same activity record is opened from the queue and its originating record.
export function activityWorkspace(activity) {
  if (activity?.deal_id) return `/deals/${activity.deal_id}`;
  if (activity?.customer_id) return `/customers/${activity.customer_id}`;
  return null;
}
