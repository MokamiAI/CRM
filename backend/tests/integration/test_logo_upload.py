"""An admin uploads a logo; it is served publicly and printed on documents.
Only real PNG/JPEG/WebP files up to 500 KB, never SVG."""
import struct
import zlib
from datetime import date

import pytest

from .conftest import new_company


def _png() -> bytes:
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) + chunk(b"IEND", b"")


@pytest.mark.asyncio
async def test_logo_upload_serve_print_and_remove(api):
    owner = await new_company(api, "Logo Co")
    h = owner["headers"]
    png = _png()
    res = await api.post("/settings/logo", files={"file": ("logo.png", png, "image/png")}, headers=h)
    assert res.status_code == 200, res.text
    url = res.json()["logo_url"]
    assert f"/api/v1/public/logo/{owner['company_id']}?v=" in url

    served = await api.get(f"/public/logo/{owner['company_id']}")
    assert served.status_code == 200 and served.content == png and served.headers["content-type"] == "image/png"

    customer = (await api.post("/customers", json={"name": "Client"}, headers=h)).json()
    inv = (await api.post("/invoices", json={"customer_id": customer["id"], "issue_date": date.today().isoformat(), "items": [{"description": "x", "quantity": "1", "unit_price": "10", "tax_rate": "15"}]}, headers=h)).json()
    assert url in (await api.get(f"/invoices/{inv['id']}/document", headers=h)).text

    removed = await api.delete("/settings/logo", headers=h)
    assert removed.json()["logo_url"] is None
    assert (await api.get(f"/public/logo/{owner['company_id']}")).status_code == 404


@pytest.mark.asyncio
async def test_logo_rejects_svg_fakes_big_files_and_non_admins(api):
    owner = await new_company(api, "Careful Co")
    h = owner["headers"]
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    assert (await api.post("/settings/logo", files={"file": ("logo.svg", svg, "image/svg+xml")}, headers=h)).status_code == 422
    fake = b"<html>not a png</html>"
    assert (await api.post("/settings/logo", files={"file": ("logo.png", fake, "image/png")}, headers=h)).status_code == 422
    big = _png() + b"\x00" * (501 * 1024)
    assert (await api.post("/settings/logo", files={"file": ("big.png", big, "image/png")}, headers=h)).status_code == 413

    import uuid
    email = f"{uuid.uuid4().hex[:10]}@example.com"
    await api.post("/users", json={"email": email, "password": "Correct-Horse-9", "full_name": "Sam", "role": "staff"}, headers=h)
    staff = {"Authorization": f"Bearer {(await api.post('/auth/login', json={'email': email, 'password': 'Correct-Horse-9'})).json()['access_token']}"}
    assert (await api.post("/settings/logo", files={"file": ("logo.png", _png(), "image/png")}, headers=staff)).status_code == 403
