"""Live clients for Elexon SAA-I014, BMRS BMU Reference, and BSC Signatories."""

from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass
from typing import Any

import httpx

SAA_BASE_URL = "https://data.elexon.co.uk/saa/api/v1/i014"
BMRS_BMU_URL = "https://data.elexon.co.uk/bmrs/api/v1/reference/bmunits/all"
BSC_SIGNATORIES_URL = (
    "https://www.elexon.co.uk/bsc/about/elexon-key-contacts/"
    "bsc-signatories-qualified-persons/?signatory_id=all"
)

# Best-to-initial settlement run priority order
RUN_TYPE_PRIORITY = ("RF", "R3", "R2", "R1", "SF", "II")

GSP_GROUP_NAMES: dict[str, str] = {
    "A": "Eastern",
    "B": "East Midlands",
    "C": "London",
    "D": "Merseyside & North Wales",
    "E": "Midlands",
    "F": "North Eastern",
    "G": "North Western",
    "H": "Southern",
    "J": "South Eastern",
    "K": "South Wales",
    "L": "South Western",
    "M": "Yorkshire",
    "N": "South Scotland",
    "P": "North Scotland",
}

ROLE_DESCRIPTIONS: dict[str, str] = {
    "VT": "Virtual Trading Party",
    "VP": "Virtual Lead Party",
    "AV": "Asset Metering VLP",
    "TS": "Supplier",
    "TG": "Generator",
    "TN": "Non-Physical Trader",
    "BP": "BSC Party",
    "MV": "Metered Volume Reallocator",
    "EN": "Energy Contract Volume Notification Agent",
    "EV": "Embedded Generator / Exempt Export",
    "EC": "Energy Account / CVA",
}


@dataclass
class SignatoryRecord:
    party_id: str
    company_name: str
    address: str
    roles: list[str]

    @property
    def is_vtp(self) -> bool:
        return "VT" in self.roles

    @property
    def is_vlp(self) -> bool:
        return "VP" in self.roles

    @property
    def is_amvlp(self) -> bool:
        return "AV" in self.roles

    @property
    def is_supplier(self) -> bool:
        return "TS" in self.roles


def parse_bsc_signatories_html(raw_html: str) -> list[SignatoryRecord]:
    """Parse Elexon's official BSC Signatories & Qualified Persons HTML directory."""
    pattern = re.compile(
        r"<tr>\s*<td class=\"title\">(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>",
        re.DOTALL,
    )
    records: list[SignatoryRecord] = []
    seen: set[str] = set()
    for name_raw, pid_raw, addr_raw, roles_raw in pattern.findall(raw_html):
        company_name = html_lib.unescape(re.sub(r"<[^>]+>", "", name_raw)).strip()
        party_id = html_lib.unescape(re.sub(r"<[^>]+>", "", pid_raw)).strip()
        address = " ".join(
            html_lib.unescape(re.sub(r"<[^>]+>", "", addr_raw)).split()
        )
        roles_text = html_lib.unescape(re.sub(r"<[^>]+>", "", roles_raw))
        roles = [r.strip() for r in roles_text.split(",") if r.strip()]
        if not party_id or party_id in seen:
            continue
        seen.add(party_id)
        records.append(
            SignatoryRecord(
                party_id=party_id,
                company_name=company_name or party_id,
                address=address,
                roles=roles,
            )
        )
    return records


def extract_gsp_group(bmu_id: str) -> str:
    """Extract single-letter GB GSP Group code from V__X... or 2__X... BMU ID."""
    if not bmu_id:
        return ""
    if len(bmu_id) >= 4 and bmu_id[1:3] == "__":
        code = bmu_id[3].upper()
        if code in GSP_GROUP_NAMES:
            return code
    return ""


async def fetch_bsc_signatories(client: httpx.AsyncClient) -> list[SignatoryRecord]:
    resp = await client.get(
        BSC_SIGNATORIES_URL,
        headers={"User-Agent": "vtpbmuanalysis/0.1 (Elexon BSC research)"},
        timeout=30.0,
    )
    resp.raise_for_status()
    return parse_bsc_signatories_html(resp.text)


async def fetch_bmu_reference(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    resp = await client.get(
        BMRS_BMU_URL,
        headers={"Accept": "application/json"},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()


def preferred_runs_for_date(settlement_date: str) -> tuple[str, ...]:
    """Order Elexon settlement run types by expected availability for a date's age."""
    import datetime as dt

    try:
        age = (dt.date.today() - dt.date.fromisoformat(settlement_date)).days
    except ValueError:
        return RUN_TYPE_PRIORITY

    if age >= 425:
        return ("RF", "R3", "R2", "R1", "SF", "II")
    if age >= 215:
        return ("R3", "RF", "R2", "R1", "SF", "II")
    if age >= 120:
        return ("R2", "R3", "R1", "SF", "RF", "II")
    if age >= 55:
        return ("R1", "R2", "SF", "R3", "II", "RF")
    if age >= 22:
        return ("SF", "R1", "II", "R2", "R3", "RF")
    return ("II", "SF", "R1", "R2", "R3", "RF")


async def resolve_best_run_type(
    client: httpx.AsyncClient,
    settlement_date: str,
    preferred_runs: tuple[str, ...] | None = None,
) -> tuple[str, dict[str, Any]] | None:
    """Find the most reconciled available settlement run for a date via party-level."""
    runs = preferred_runs or preferred_runs_for_date(settlement_date)
    for run_type in runs:
        url = f"{SAA_BASE_URL}/party-level/{settlement_date}/{run_type}"
        for attempt in range(2):
            try:
                resp = await client.get(
                    url, headers={"Accept": "application/json"}, timeout=30.0
                )
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == 0:
                    continue
                break
            if resp.status_code == 200:
                return run_type, resp.json()
            if resp.status_code in (404, 400):
                break
            if resp.status_code >= 500 and attempt == 0:
                continue
            resp.raise_for_status()
    return None


async def fetch_i014_dataset(
    client: httpx.AsyncClient,
    dataset: str,
    settlement_date: str,
    run_type: str,
) -> dict[str, Any]:
    url = f"{SAA_BASE_URL}/{dataset}/{settlement_date}/{run_type}"
    resp = await client.get(url, headers={"Accept": "application/json"}, timeout=60.0)
    resp.raise_for_status()
    return resp.json()
