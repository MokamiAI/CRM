// Costs and bills: the account owner, and whoever the owner allowed to
// view them or also manage them (backend User.can_view_costs / can_manage_costs).
export const canViewCosts = (user) => Boolean(user?.is_account_owner || ["view", "manage"].includes(user?.cost_access));
export const canManageCosts = (user) => Boolean(user?.is_account_owner || (user?.cost_access === "manage" && user?.role !== "viewer"));
