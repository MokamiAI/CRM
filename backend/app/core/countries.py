"""Where a company trades: the country fills in its defaults (currency, tax,
dialling code, time zone, financial year), and every one of them can be
changed in Settings afterwards.

Tax rates are each country's standard rate as of 2026 (sources: national
revenue authorities via KPMG/EY/PwC tax alerts and afrotools.com, checked
November 2026). Rates change: they are only the starting value for new
companies, never applied to a company that already exists.

YGT's own subscriptions are always charged in rand (see app/core/plans.py);
this file is only about how a company invoices its own customers.
"""
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Country:
    code: str  # ISO 3166-1 alpha-2; "ZZ" = another country
    name: str
    currency: str  # ISO 4217
    dial: str  # international dialling code, no "+"; "" = none assumed
    timezone: str
    tax_rate: Decimal  # standard VAT/GST rate, %
    tax_name: str = "VAT"  # on documents: "Total excl. VAT"
    tax_id: str = "TIN"  # what the tax number is called: "KRA PIN", "TIN"
    fy_start: int = 1  # month the usual financial year starts


def _c(code, name, currency, dial, tz, rate, tax_name="VAT", tax_id="TIN", fy=1):
    return Country(code, name, currency, dial, tz, Decimal(str(rate)), tax_name, tax_id, fy)


_ALL = [
    _c("DZ", "Algeria", "DZD", "213", "Africa/Algiers", 19, tax_id="NIF"),
    _c("AO", "Angola", "AOA", "244", "Africa/Luanda", 14, tax_id="NIF"),
    _c("BJ", "Benin", "XOF", "229", "Africa/Porto-Novo", 18, tax_id="IFU"),
    _c("BW", "Botswana", "BWP", "267", "Africa/Gaborone", 14, fy=7),
    _c("BF", "Burkina Faso", "XOF", "226", "Africa/Ouagadougou", 18, tax_id="IFU"),
    _c("BI", "Burundi", "BIF", "257", "Africa/Bujumbura", 18, tax_id="NIF"),
    _c("CV", "Cabo Verde", "CVE", "238", "Atlantic/Cape_Verde", 15, tax_id="NIF"),
    _c("CM", "Cameroon", "XAF", "237", "Africa/Douala", 19.25, tax_id="NIU"),
    _c("CF", "Central African Republic", "XAF", "236", "Africa/Bangui", 19, tax_id="NIF"),
    _c("TD", "Chad", "XAF", "235", "Africa/Ndjamena", 18, tax_id="NIF"),
    _c("KM", "Comoros", "KMF", "269", "Indian/Comoro", 0, tax_name="Tax", tax_id="NIF"),
    _c("CG", "Congo", "XAF", "242", "Africa/Brazzaville", 18.9, tax_id="NIU"),
    _c("CD", "DR Congo", "CDF", "243", "Africa/Kinshasa", 16, tax_id="NIF"),
    _c("CI", "Côte d'Ivoire", "XOF", "225", "Africa/Abidjan", 18, tax_id="NCC"),
    _c("DJ", "Djibouti", "DJF", "253", "Africa/Djibouti", 10, tax_id="NIF"),
    _c("EG", "Egypt", "EGP", "20", "Africa/Cairo", 14, tax_id="Tax registration number"),
    _c("GQ", "Equatorial Guinea", "XAF", "240", "Africa/Malabo", 15, tax_id="NIF"),
    _c("ER", "Eritrea", "ERN", "291", "Africa/Asmara", 0, tax_name="Sales tax"),
    _c("SZ", "Eswatini", "SZL", "268", "Africa/Mbabane", 15, fy=7),
    _c("ET", "Ethiopia", "ETB", "251", "Africa/Addis_Ababa", 15, fy=7),
    _c("GA", "Gabon", "XAF", "241", "Africa/Libreville", 18, tax_id="NIF"),
    _c("GM", "Gambia", "GMD", "220", "Africa/Banjul", 15),
    # 15% VAT + 2.5% NHIL + 2.5% GETFund on the same base: 20% in all (2026).
    _c("GH", "Ghana", "GHS", "233", "Africa/Accra", 20),
    _c("GN", "Guinea", "GNF", "224", "Africa/Conakry", 18, tax_id="NIF"),
    _c("GW", "Guinea-Bissau", "XOF", "245", "Africa/Bissau", 15, tax_id="NIF"),
    _c("KE", "Kenya", "KES", "254", "Africa/Nairobi", 16, tax_id="KRA PIN"),
    _c("LS", "Lesotho", "LSL", "266", "Africa/Maseru", 15, fy=4),
    _c("LR", "Liberia", "LRD", "231", "Africa/Monrovia", 10, tax_name="GST"),
    _c("LY", "Libya", "LYD", "218", "Africa/Tripoli", 0, tax_name="Tax"),
    _c("MG", "Madagascar", "MGA", "261", "Indian/Antananarivo", 20, tax_id="NIF"),
    _c("MW", "Malawi", "MWK", "265", "Africa/Blantyre", 17.5, tax_id="TPIN", fy=7),
    _c("ML", "Mali", "XOF", "223", "Africa/Bamako", 18, tax_id="NIF"),
    _c("MR", "Mauritania", "MRU", "222", "Africa/Nouakchott", 16, tax_id="NIF"),
    _c("MU", "Mauritius", "MUR", "230", "Indian/Mauritius", 15, tax_id="VAT number", fy=7),
    _c("MA", "Morocco", "MAD", "212", "Africa/Casablanca", 20, tax_id="ICE"),
    _c("MZ", "Mozambique", "MZN", "258", "Africa/Maputo", 16, tax_id="NUIT"),
    _c("NA", "Namibia", "NAD", "264", "Africa/Windhoek", 15, tax_id="VAT number", fy=3),
    _c("NE", "Niger", "XOF", "227", "Africa/Niamey", 19, tax_id="NIF"),
    _c("NG", "Nigeria", "NGN", "234", "Africa/Lagos", 7.5),
    _c("RW", "Rwanda", "RWF", "250", "Africa/Kigali", 18),
    _c("ST", "São Tomé and Príncipe", "STN", "239", "Africa/Sao_Tome", 15, tax_id="NIF"),
    _c("SN", "Senegal", "XOF", "221", "Africa/Dakar", 18, tax_id="NINEA"),
    _c("SC", "Seychelles", "SCR", "248", "Indian/Mahe", 15),
    _c("SL", "Sierra Leone", "SLE", "232", "Africa/Freetown", 15, tax_name="GST"),
    _c("SO", "Somalia", "SOS", "252", "Africa/Mogadishu", 10, tax_name="Sales tax"),
    _c("ZA", "South Africa", "ZAR", "27", "Africa/Johannesburg", 15, tax_id="VAT number", fy=3),
    _c("SS", "South Sudan", "SSP", "211", "Africa/Juba", 18),
    _c("SD", "Sudan", "SDG", "249", "Africa/Khartoum", 17),
    _c("TZ", "Tanzania", "TZS", "255", "Africa/Dar_es_Salaam", 18),
    _c("TG", "Togo", "XOF", "228", "Africa/Lome", 18, tax_id="NIF"),
    _c("TN", "Tunisia", "TND", "216", "Africa/Tunis", 19, tax_id="Matricule fiscal"),
    _c("UG", "Uganda", "UGX", "256", "Africa/Kampala", 18, fy=7),
    _c("ZM", "Zambia", "ZMW", "260", "Africa/Lusaka", 16, tax_id="TPIN"),
    # Most Zimbabwean businesses invoice in US dollars; ZWG is in the list too.
    _c("ZW", "Zimbabwe", "USD", "263", "Africa/Harare", 15.5, tax_id="VAT number"),
    _c("ZZ", "Another country", "USD", "", "UTC", 0, tax_name="Tax", tax_id="Tax number"),
]

COUNTRIES: dict[str, Country] = {c.code: c for c in _ALL}
DEFAULT_COUNTRY = "ZA"

# Every currency a company can invoice in: each African country's own, the
# dollar, euro and pound (common for export work), and Zimbabwe Gold.
CURRENCIES: tuple[str, ...] = tuple(
    sorted({c.currency for c in _ALL} | {"USD", "EUR", "GBP", "ZWG"})
)


def country(code: str | None) -> Country:
    return COUNTRIES.get((code or "").upper(), COUNTRIES[DEFAULT_COUNTRY])


def format_money(currency: str | None, amount) -> str:
    """'KES 1,500.00': the code, then the amount to the cent (documents,
    emails and WhatsApp messages; the app formats for the reader's locale)."""
    return f"{(currency or 'ZAR').upper()} {Decimal(str(amount or 0)):,.2f}"


def as_dict(c: Country) -> dict:
    return {
        "code": c.code,
        "name": c.name,
        "currency": c.currency,
        "dial": c.dial,
        "timezone": c.timezone,
        "tax_rate": str(c.tax_rate),
        "tax_name": c.tax_name,
        "tax_id": c.tax_id,
        "fy_start": c.fy_start,
    }
