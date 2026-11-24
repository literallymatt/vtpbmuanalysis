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


_PARTY_START_RE = re.compile(r'\{\s*"bscPartyId"\s*:')


def _extract_sbmu_records_from_party(
    party: dict[str, Any], extracted: list[dict[str, Any]]
) -> None:
    pid = party.get("bscPartyId") or ""
    for sp_block in party.get("bmUnitSettlementPeriods", []):
        sp_num = int(sp_block.get("sp", 0))
        if sp_num <= 0:
            continue
        for bmu in sp_block.get("bmUnitPeriodData", []):
            bmu_id = bmu.get("bmUnitId") or ""
            if not bmu_id.startswith("V__"):
                continue
            extracted.append(
                {
                    "sp": sp_num,
                    "sec_party_id": pid,
                    "sec_bmu_id": bmu_id,
                    "pc_flag": bmu.get("pcFlag") or "",
                    "fpn": bmu.get("fpnij"),
                    "qme": bmu.get("qmeij"),
                    "sev": bmu.get("sevij"),
                    "qm": bmu.get("qmij"),
                    "qdei": bmu.get("qdei2j"),
                    "qsd": bmu.get("qsdij"),
                    "qcv": bmu.get("qcviji2"),
                    "wmi": bmu.get("wmi2j"),
                    "wmi_flag": bmu.get("wmi2jF"),
                }
            )


async def _parse_sbmu_baselines_stream(
    chunks: Any,
) -> list[dict[str, Any]]:
    """Parse streamed JSON text chunks from bm-unit-level into V__* SBMU records.

    Uses a fast C-speed party-boundary scanner (~1s per 380MB) when party objects
    begin with `{"bscPartyId":`, with automatic fallback to a general brace-depth
    JSON object scanner if the upstream key order differs.
    """
    import json

    extracted: list[dict[str, Any]] = []
    decoder = json.JSONDecoder()

    in_parties = False
    mode: str | None = None  # "fast" | "brace"
    prefix_buf = ""

    # Fast-mode state
    fast_buf = ""
    scan_from = 1

    # Fallback brace-depth state
    in_string = False
    escape = False
    brace_depth = 0
    party_buf: list[str] = []

    def _flush_fast_segment(seg: str) -> None:
        if '"V__' not in seg:
            return
        party, _ = decoder.raw_decode(seg, 0)
        _extract_sbmu_records_from_party(party, extracted)

    def _flush_brace_obj(raw_obj: str) -> None:
        if '"V__' not in raw_obj:
            return
        party = json.loads(raw_obj)
        _extract_sbmu_records_from_party(party, extracted)

    async for chunk in chunks:
        if not in_parties:
            prefix_buf += chunk
            marker = prefix_buf.find('"bscParties"')
            if marker == -1:
                prefix_buf = prefix_buf[-64:]
                continue
            arr_start = prefix_buf.find("[", marker)
            if arr_start == -1:
                continue
            in_parties = True
            chunk = prefix_buf[arr_start + 1 :]
            prefix_buf = ""

        if mode is None:
            prefix_buf += chunk
            stripped = prefix_buf.lstrip()
            if not stripped:
                continue
            if stripped[0] == "]":
                return extracted
            if stripped[0] == "{":
                if ":" not in stripped and "}" not in stripped:
                    # Wait for enough bytes to inspect first key
                    continue
                if _PARTY_START_RE.match(stripped):
                    mode = "fast"
                    fast_buf = stripped
                    scan_from = 1
                    chunk = ""
                    prefix_buf = ""
                else:
                    mode = "brace"
                    chunk = stripped
                    prefix_buf = ""
            else:
                mode = "brace"
                chunk = stripped
                prefix_buf = ""

        if mode == "fast":
            if chunk:
                fast_buf += chunk
            prev = 0
            search_start = max(1, scan_from - 32)
            for m in _PARTY_START_RE.finditer(fast_buf, search_start):
                pos = m.start()
                if pos > prev:
                    _flush_fast_segment(fast_buf[prev:pos])
                    prev = pos
            if prev > 0:
                fast_buf = fast_buf[prev:]
            scan_from = len(fast_buf)
            continue

        # Fallback brace-depth scanner
        i = 0
        n = len(chunk)
        obj_start = 0 if brace_depth > 0 else -1
        while i < n:
            ch = chunk[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
            else:
                if ch == '"':
                    in_string = True
                elif ch == "{":
                    if brace_depth == 0:
                        obj_start = i
                        party_buf = []
                    brace_depth += 1
                elif ch == "}":
                    brace_depth -= 1
                    if brace_depth == 0 and obj_start != -1:
                        party_buf.append(chunk[obj_start : i + 1])
                        _flush_brace_obj("".join(party_buf))
                        party_buf = []
                        obj_start = -1
                elif ch == "]" and brace_depth == 0:
                    return extracted
            i += 1

        if brace_depth > 0 and obj_start != -1:
            party_buf.append(chunk[obj_start:])

    if mode == "fast" and fast_buf:
        _flush_fast_segment(fast_buf)
    elif mode is None and prefix_buf:
        stripped = prefix_buf.lstrip()
        if stripped.startswith("{") and '"V__' in stripped:
            party, _ = decoder.raw_decode(stripped, 0)
            _extract_sbmu_records_from_party(party, extracted)

    return extracted


async def stream_sbmu_baselines(
    client: httpx.AsyncClient,
    settlement_date: str,
    run_type: str,
) -> list[dict[str, Any]]:
    """Stream bm-unit-level and extract only Secondary BMU (V__*) records cleanly.

    bm-unit-level payloads are ~350-400 MB uncompressed across ~500 parties.
    We stream text chunks, isolate each top-level party object inside `bscParties`,
    skip any party buffer that does not reference a `V__` Secondary BMU without
    JSON-parsing it, and extract only the Secondary BMU settlement period records.
    """
    import asyncio

    url = f"{SAA_BASE_URL}/bm-unit-level/{settlement_date}/{run_type}"
    timeout = httpx.Timeout(30.0, read=180.0)
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            async with client.stream(
                "GET", url, headers={"Accept": "application/json"}, timeout=timeout
            ) as resp:
                resp.raise_for_status()
                return await _parse_sbmu_baselines_stream(
                    resp.aiter_text(chunk_size=262144)
                )
        except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
            last_exc = exc
            if attempt < 2:
                await asyncio.sleep(2.0 * (attempt + 1))
                continue
            raise
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            if exc.response.status_code >= 500 and attempt < 2:
                await asyncio.sleep(2.0 * (attempt + 1))
                continue
            raise
    assert last_exc is not None
    raise last_exc
