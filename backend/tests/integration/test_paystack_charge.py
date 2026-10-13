"""A Paystack charge switches a plan on only when it is a full rand payment
for one of YGT's own plans, and a replayed charge is recorded once."""
import uuid

import pytest
from sqlalchemy import func, select

from app.core.database import AsyncSessionLocal
from app.core.tenancy import set_system, set_tenant
from app.models.billing import BillingPayment, PaystackPlan
from app.services.billing_service import BillingService

from .conftest import new_company


@pytest.mark.asyncio
async def test_charge_must_match_the_plan_and_counts_once(api):
    owner = await new_company(api, "Epsilon Consulting")
    company_id = owner["company_id"]
    plan_code = f"PLN_test_{uuid.uuid4().hex[:10]}"
    reference = f"ygt_test_{uuid.uuid4().hex}"

    async with AsyncSessionLocal() as db:
        set_system(db)
        db.add(PaystackPlan(key=f"test:{uuid.uuid4().hex}", plan_code=plan_code, amount_cents=44700))
        await db.flush()
        set_tenant(db, company_id)
        service = BillingService(db)
        sub = await service.subscription()

        def charge(**overrides) -> dict:
            data = {
                "reference": reference,
                "amount": 44700,
                "currency": "ZAR",
                "plan": plan_code,
                "metadata": {"company_id": str(company_id), "plan": "grow", "interval": "monthly", "seats": 3},
                "customer": {"email": owner["email"], "customer_code": "CUS_test"},
            }
            return {**data, **overrides}

        async def payments() -> int:
            return await db.scalar(select(func.count()).select_from(BillingPayment).where(BillingPayment.company_id == company_id))

        for bad in (charge(amount=100), charge(currency="USD"), charge(plan="PLN_not_ours"), charge(plan=None)):
            await service._apply_charge(sub, bad)
            assert sub.status != "active"
            assert await payments() == 0

        await service._apply_charge(sub, charge())
        assert sub.status == "active" and sub.plan == "grow" and sub.seats == 3
        assert await payments() == 1

        # The webhook and the redirect back both arrive, or Paystack retries.
        await service._apply_charge(sub, charge())
        assert await payments() == 1
        await db.rollback()
