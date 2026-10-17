"""Customer phases must agree across the pipeline and opportunity detail."""
from types import SimpleNamespace

import pytest

from app.models.enums import DealStage
from app.services.mcem_service import pipeline_phase


@pytest.mark.parametrize("stage,confirmed,expected", [
    (DealStage.LEAD, [], "Listen and Consult"),
    (DealStage.QUALIFIED, ["problem"], "Listen and Consult"),
    (DealStage.QUALIFIED, ["problem", "outcome"], "Inspire and Design"),
    (DealStage.PROPOSAL, [], "Empower and Achieve"),
    (DealStage.NEGOTIATION, [], "Empower and Achieve"),
    (DealStage.WON, ["delivery", "adoption"], "Realize Value"),
    (DealStage.WON, ["delivery", "adoption", "value"], "Manage and Optimize"),
])
def test_customer_phase(stage, confirmed, expected):
    rows = [SimpleNamespace(key=key, status="confirmed", needs_review=False) for key in confirmed]
    assert pipeline_phase(stage, rows) == expected


def test_value_needing_review_returns_won_customer_to_realize_value():
    rows = [SimpleNamespace(key=key, status="confirmed", needs_review=key == "value")
            for key in ["delivery", "adoption", "value"]]
    assert pipeline_phase(DealStage.WON, rows) == "Realize Value"
