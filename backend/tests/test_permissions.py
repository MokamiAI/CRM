"""Every endpoint that changes data checks the person's role, except a short,
deliberate list. A new endpoint without a role check fails this test until
someone decides: add require_role, or add it to an allow-list below with why."""
from fastapi.routing import APIRoute

from app.main import app

# Anyone, signed in or not: sign-in flows, and inbound calls that carry their
# own proof (Paystack signature, per-channel token, unsubscribe token).
PUBLIC = {
    "/api/v1/auth/forgot-password",
    "/api/v1/auth/login",
    "/api/v1/auth/logout",
    "/api/v1/auth/refresh",
    "/api/v1/auth/register",
    "/api/v1/auth/reset-password",
    "/api/v1/auth/verify-email",
    "/api/v1/public/channels/{token}/sms",
    "/api/v1/public/channels/{token}/whatsapp",
    "/api/v1/public/contact",
    "/api/v1/public/inbound/email",
    "/api/v1/public/m/u/{token}",
    "/api/v1/public/paystack/webhook",
}
# Any signed-in person, viewers too: their own profile, asking YGT for help,
# talking to colleagues, and a preview that saves nothing.
ANY_SIGNED_IN = {
    "/api/v1/auth/me",
    "/api/v1/auth/verify-email/resend",
    "/api/v1/bookings",
    "/api/v1/bookings/{booking_id}/cancel",
    "/api/v1/marketing/audience/preview",
    "/api/v1/support/tickets",
    "/api/v1/support/tickets/{ticket_id}/close",
    "/api/v1/support/tickets/{ticket_id}/messages",
    "/api/v1/team-chat/channels/{channel_id}/messages",
}


def _dependency_names(dependant, names: set[str]) -> set[str]:
    for dep in dependant.dependencies:
        names.add(getattr(dep.call, "__qualname__", repr(dep.call)))
        _dependency_names(dep, names)
    return names


def test_every_data_changing_endpoint_checks_the_role():
    unchecked = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or not (route.methods - {"GET", "HEAD", "OPTIONS"}):
            continue
        names = _dependency_names(route.dependant, set())
        if any(n.startswith("require_role") or "require_platform_admin" in n for n in names):
            continue
        if route.path in PUBLIC:
            continue
        if route.path in ANY_SIGNED_IN and any("get_current_user" in n for n in names):
            continue
        unchecked.append(f"{','.join(sorted(route.methods))} {route.path}")
    assert unchecked == [], "No role check on: " + "; ".join(unchecked)
