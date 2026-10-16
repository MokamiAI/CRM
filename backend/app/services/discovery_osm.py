"""OpenStreetMap lookups for Discovery: where an area is (Nominatim) and
which businesses of the chosen kinds are near it (Overpass). Both are free
public services with fair-use rules: a descriptive User-Agent, one request
at a time, and no bulk downloads. Discovery runs once a week per company.

Data © OpenStreetMap contributors, under the Open Database Licence; the
Discovery page says so wherever these leads appear."""
import logging
import re
from dataclasses import dataclass

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Busy public servers can take a minute; Discovery never waits on them
# while a person watches (see DiscoveryService.run).
_TIMEOUT = httpx.Timeout(90.0, connect=15.0)
MAX_RESULTS = 300

# Each industry code (app/models/enums.py INDUSTRIES) and the OpenStreetMap
# tags of businesses in it. "other" has none: nothing to search for.
OSM_TAGS: dict[str, dict[str, tuple[str, ...]]] = {
    "agriculture": {"shop": ("agrarian", "garden_centre"), "craft": ("agricultural_engines",)},
    "automotive": {"shop": ("car", "car_repair", "car_parts", "tyres", "motorcycle"), "amenity": ("car_wash",)},
    "construction": {"office": ("construction_company", "architect"), "craft": ("builder", "electrician", "plumber", "carpenter", "roofer"), "shop": ("hardware", "doityourself")},
    "education": {"amenity": ("school", "kindergarten", "college", "university", "driving_school", "language_school", "training")},
    "energy": {"office": ("energy_supplier",), "craft": ("photovoltaic", "electrician")},
    "financial_services": {"office": ("financial", "financial_advisor", "accountant", "tax_advisor"), "amenity": ("bank",)},
    "food_beverage": {"amenity": ("restaurant", "cafe", "fast_food"), "shop": ("bakery", "butcher", "deli"), "craft": ("caterer", "brewery")},
    "government": {"office": ("government",), "amenity": ("townhall", "courthouse")},
    "healthcare": {"amenity": ("clinic", "doctors", "dentist", "pharmacy", "veterinary"), "healthcare": ("physiotherapist", "optometrist", "psychotherapist")},
    "hospitality": {"tourism": ("hotel", "guest_house", "hostel", "motel"), "amenity": ("events_venue", "conference_centre", "bar")},
    "insurance": {"office": ("insurance",)},
    "it_software": {"office": ("it", "telecommunication"), "shop": ("computer",)},
    "legal": {"office": ("lawyer", "notary")},
    "manufacturing": {"man_made": ("works",), "industrial": ("factory",)},
    "media_marketing": {"office": ("advertising_agency", "newspaper"), "shop": ("copyshop",), "craft": ("photographer", "signmaker")},
    "mining": {"industrial": ("mine",), "office": ("mining",)},
    "non_profit": {"office": ("ngo", "association", "charity", "foundation"), "amenity": ("place_of_worship", "community_centre")},
    "professional_services": {"office": ("accountant", "consulting", "architect", "company", "employment_agency")},
    "real_estate": {"office": ("estate_agent", "property_management")},
    "retail": {"shop": ("clothes", "convenience", "supermarket", "shoes", "furniture", "electronics", "hairdresser", "beauty")},
    "telecoms": {"office": ("telecommunication",), "shop": ("mobile_phone",)},
    "transport_logistics": {"office": ("logistics", "moving_company", "courier"), "amenity": ("fuel",)},
    "wholesale": {"shop": ("wholesale",), "office": ("wholesale",)},
}


@dataclass
class Place:
    ref: str  # "osm:node/123"
    name: str
    industry: str
    kind: str
    address: str | None
    phone: str | None
    email: str | None
    website: str | None


class OsmUnavailable(Exception):
    """OpenStreetMap couldn't be reached or didn't understand the request."""


def _headers() -> dict:
    contact = settings.PUBLIC_SUPPORT_EMAIL or "support@yougt.co.za"
    return {"User-Agent": f"YGT-CRM-Discovery/1.0 ({contact})", "Accept": "application/json"}


async def _get(url: str, **kwargs) -> httpx.Response:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_headers()) as client:
            res = await client.request(kwargs.pop("method", "GET"), url, **kwargs)
            res.raise_for_status()
            return res
    except httpx.HTTPError as exc:
        logger.warning("OpenStreetMap lookup failed: %s", exc)
        raise OsmUnavailable(str(exc)) from exc


async def geocode(area: str) -> tuple[float, float, str] | None:
    """The middle of a place name ("Soweto, Johannesburg"): (lat, lon, full name)."""
    res = await _get(settings.NOMINATIM_URL, params={"q": area, "format": "jsonv2", "limit": 1, "addressdetails": 0})
    rows = res.json()
    if not rows:
        return None
    return float(rows[0]["lat"]), float(rows[0]["lon"]), rows[0].get("display_name") or area


def build_query(lat: float, lon: float, radius_km: int, industries: list[str]) -> str:
    metres = max(1, min(radius_km, 50)) * 1000
    lines = []
    for code in industries:
        for key, values in OSM_TAGS.get(code, {}).items():
            lines.append(f'nw["name"]["{key}"~"^({"|".join(values)})$"](around:{metres},{lat:.6f},{lon:.6f});')
    return f"[out:json][timeout:25];({''.join(lines)});out center tags {MAX_RESULTS};"


def _industry_of(tags: dict, industries: list[str]) -> tuple[str, str] | None:
    for code in industries:
        for key, values in OSM_TAGS.get(code, {}).items():
            if tags.get(key) in values:
                return code, tags[key]
    return None


def _address(tags: dict) -> str | None:
    street = " ".join(p for p in (tags.get("addr:housenumber"), tags.get("addr:street")) if p)
    parts = [street, tags.get("addr:suburb"), tags.get("addr:city"), tags.get("addr:postcode")]
    text = ", ".join(p for p in parts if p)
    return text or None


def _clean(value: str | None, limit: int) -> str | None:
    if not value:
        return None
    value = re.sub(r"\s+", " ", value.split(";")[0]).strip()
    return value[:limit] or None


def parse(payload: dict, industries: list[str]) -> list[Place]:
    places: list[Place] = []
    for el in payload.get("elements", []):
        tags = el.get("tags") or {}
        name = _clean(tags.get("name"), 255)
        match = _industry_of(tags, industries)
        if not name or not match:
            continue
        website = _clean(tags.get("website") or tags.get("contact:website"), 500)
        if website and not website.startswith(("http://", "https://")):
            website = "https://" + website
        places.append(
            Place(
                ref=f"osm:{el.get('type')}/{el.get('id')}",
                name=name,
                industry=match[0],
                kind=match[1],
                address=_clean(_address(tags), 1000),
                phone=_clean(tags.get("phone") or tags.get("contact:phone"), 50),
                email=_clean(tags.get("email") or tags.get("contact:email"), 255),
                website=website,
            )
        )
    return places


async def nearby(lat: float, lon: float, radius_km: int, industries: list[str]) -> list[Place]:
    searchable = [c for c in industries if c in OSM_TAGS]
    if not searchable:
        return []
    query = build_query(lat, lon, radius_km, searchable)
    servers = [u.strip() for u in settings.OVERPASS_URL.split(",") if u.strip()]
    for i, url in enumerate(servers):
        try:
            res = await _get(url, method="POST", data={"data": query})
            return parse(res.json(), searchable)
        except OsmUnavailable:
            if i == len(servers) - 1:
                raise
    return []
