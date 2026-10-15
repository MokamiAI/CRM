"""The invoice list can put the soonest due first (the dashboard's "Who owes
you?" asks for five that way), and still lists newest first by default."""
import pytest

from .conftest import new_company

ITEM = [{"description": "Catering", "quantity": "1", "unit_price": "100.00", "tax_rate": "15"}]


@pytest.mark.asyncio
async def test_sort_by_due_date(api):
    owner = await new_company(api, "Sort Catering")
    headers = owner["headers"]
    customer = (await api.post("/customers", json={"name": "Naledi Events"}, headers=headers)).json()
    made = []
    for due in ["2026-11-20", "2026-10-05", "2026-12-31", "2026-10-30"]:
        body = {"customer_id": customer["id"], "issue_date": "2026-10-01", "items": ITEM, "due_date": due}
        res = await api.post("/invoices", json=body, headers=headers)
        assert res.status_code == 201, res.text
        made.append(res.json()["id"])

    by_due = (await api.get("/invoices", params={"sort": "due", "limit": 3}, headers=headers)).json()
    assert [i["due_date"] for i in by_due] == ["2026-10-05", "2026-10-30", "2026-11-20"]

    newest_first = (await api.get("/invoices", headers=headers)).json()
    assert [i["id"] for i in newest_first] == made[::-1]

    assert (await api.get("/invoices", params={"sort": "nonsense"}, headers=headers)).status_code == 422
