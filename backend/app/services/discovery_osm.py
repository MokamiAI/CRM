"""OpenStreetMap lookups for Discovery: where an area is (Nominatim) and
which businesses of the chosen kinds are near it (Overpass). Both are free
public services with fair-use rules: a descriptive User-Agent, one request
at a time, and no bulk downloads. Discovery runs once a week per company.

Data © OpenStreetMap contributors, under the Open Database Licence; the
Discovery page says so wherever these leads appear."""
import asyncio
import logging
import math
import re
from dataclasses import dataclass

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Busy public servers can take a minute; Discovery never waits on them
# while a person watches (see DiscoveryService.run).
_TIMEOUT = httpx.Timeout(90.0, connect=15.0)
# Everything in the circle, so the nearest can be picked (the map service
# returns results in no particular order).
MAX_RESULTS = 1000
# Every server busy: wait this long, then try them all once more.
RETRY_PAUSE_SECONDS = 20

# National chains decide at head office, so a branch isn't a lead. The map
# tags most with "brand"; these are the common South African ones it often
# doesn't. Matched on the whole name, ignoring case.
CHAINS = {
    "ackermans", "absa", "boxer", "bradlows", "builders", "builders warehouse", "capitec", "cashbuild", "cell c", "checkers",
    "chicken licken", "clicks", "debonairs", "debonairs pizza", "dis-chem", "edgars", "engen", "fnb", "foschini", "game",
    "hi-fi corporation", "incredible connection", "jet", "kfc", "lewis", "makro", "mcdonald's", "mr price", "mtn", "nando's",
    "nedbank", "ok foods", "pep", "pick n pay", "postnet", "roman's pizza", "russells", "sasol", "shell", "shoe city",
    "shoprite", "spar", "spur", "standard bank", "steers", "superspar", "telkom", "total", "truworths", "usave", "vodacom",
    "wimpy", "woolworths",
}

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
    distance_km: float | None = None

    @property
    def reachable(self) -> bool:
        """Has a phone number, email or website to get in touch."""
        return bool(self.phone or self.email or self.website)


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


def _distance_km(el: dict, lat: float | None, lon: float | None) -> float | None:
    point = el.get("center") or el
    if lat is None or lon is None or point.get("lat") is None or point.get("lon") is None:
        return None
    # Haversine: accurate enough for "how far away".
    p1, p2 = math.radians(lat), math.radians(point["lat"])
    dp, dl = p2 - p1, math.radians(point["lon"] - lon)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(6371 * 2 * math.asin(math.sqrt(a)), 1)


def _is_chain(tags: dict, name: str, branches: dict[str, int]) -> bool:
    """A branch of a national chain: tagged with a brand, a well-known
    name, or the same name three times or more in one search."""
    key = name.lower()
    return bool(tags.get("brand") or tags.get("brand:wikidata")) or key in CHAINS or branches.get(key, 0) >= 3


def parse(payload: dict, industries: list[str], lat: float | None = None, lon: float | None = None) -> list[Place]:
    """The independent businesses found, best leads first: those with a way
    to get in touch, then the nearest."""
    elements = payload.get("elements", [])
    branches: dict[str, int] = {}
    for el in elements:
        name = _clean((el.get("tags") or {}).get("name"), 255)
        if name:
            branches[name.lower()] = branches.get(name.lower(), 0) + 1
    places: list[Place] = []
    for el in elements:
        tags = el.get("tags") or {}
        name = _clean(tags.get("name"), 255)
        match = _industry_of(tags, industries)
        if not name or not match or _is_chain(tags, name, branches):
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
                distance_km=_distance_km(el, lat, lon),
            )
        )
    far = float("inf")
    places.sort(key=lambda p: (not p.reachable, p.distance_km if p.distance_km is not None else far))
    return places


async def nearby(lat: float, lon: float, radius_km: int, industries: list[str]) -> list[Place]:
    searchable = [c for c in industries if c in OSM_TAGS]
    if not searchable:
        return []
    query = build_query(lat, lon, radius_km, searchable)
    servers = [u.strip() for u in settings.OVERPASS_URL.split(",") if u.strip()]
    # The public servers are often busy for a moment: each one, then all of
    # them once more after a pause.
    attempts = servers + servers
    for i, url in enumerate(attempts):
        if i == len(servers):
            await asyncio.sleep(RETRY_PAUSE_SECONDS)
        try:
            res = await _get(url, method="POST", data={"data": query})
            return parse(res.json(), searchable, lat, lon)
        except OsmUnavailable:
            if i == len(attempts) - 1:
                raise
    return []
