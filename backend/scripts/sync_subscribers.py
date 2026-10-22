"""Brings YGT's own pipeline up to date with everyone who signed up, now
instead of waiting for the next scheduled run (every five minutes). See
app/services/subscriber_pipeline.py for the stages. Nothing is emailed.

    python scripts/sync_subscribers.py            # dry run: shows what it would do
    python scripts/sync_subscribers.py --apply    # does it
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.core.tenancy import set_system  # noqa: E402
from app.services import subscriber_pipeline  # noqa: E402


async def main(apply: bool) -> None:
    async with AsyncSessionLocal() as db:
        set_system(db)
        ygt, admin = await subscriber_pipeline.workspace(db)
        if ygt is None:
            sys.exit("No platform admin with a confirmed email (PLATFORM_ADMIN_EMAILS), so no YGT workspace.")
        print(f"YGT workspace: {ygt.company_name} (deals owned by {admin.email})\n")
        changes = await subscriber_pipeline.sync(db, apply=apply)
        for c in changes:
            print(f"  {c.action:4}  {c.company}: {c.state} -> {c.stage.value}, {c.plan} x{c.seats}, R{c.value:,.2f}/month"
                  + (f", closes {c.close}" if c.close else ""))
        if apply:
            await db.commit()
            print(f"\nDone: {len(changes)} updated.")
        else:
            print(f"\nDry run: {len(changes)} to update. Run again with --apply to do it.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="make the changes (default: dry run)")
    asyncio.run(main(parser.parse_args().apply))
