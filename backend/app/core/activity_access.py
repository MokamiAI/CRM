"""Keep activity visibility consistent across queues, history and direct links."""
from sqlalchemy import event, or_, select
from sqlalchemy.orm import Session, with_loader_criteria

from app.core.tenancy import SYSTEM
from app.models.crm import Activity, ActivityAttachment, TaskUpdate
from app.models.enums import UserRole
from app.models.meeting import Meeting

_ACTOR = "activity_actor"
# Availability checks may inspect other calendars without returning their details.
CHECK_AVAILABILITY = "check_activity_availability"


def set_activity_actor(db, user):
    db.sync_session.info[_ACTOR] = (user.id, user.role)


@event.listens_for(Session, "do_orm_execute")
def restrict_activities(state):
    actor = state.session.info.get(_ACTOR)
    if not state.is_select or not actor or state.session.info.get("tenant") is SYSTEM:
        return
    actor_id, role = actor
    if role in (UserRole.ADMIN, UserRole.MANAGER) or state.execution_options.get(CHECK_AVAILABILITY):
        return
    visible = or_(Activity.owner_id == actor_id, Activity.created_by == actor_id,
                  Activity.assignee_ids.contains([str(actor_id)]))
    activity_ids = select(Activity.id).where(visible).correlate(None)
    state.statement = state.statement.options(
        with_loader_criteria(Activity, visible, include_aliases=True),
        with_loader_criteria(TaskUpdate, TaskUpdate.activity_id.in_(activity_ids), include_aliases=True),
        with_loader_criteria(ActivityAttachment, ActivityAttachment.activity_id.in_(activity_ids), include_aliases=True),
        with_loader_criteria(Meeting, Meeting.activity_id.in_(activity_ids), include_aliases=True),
    )
