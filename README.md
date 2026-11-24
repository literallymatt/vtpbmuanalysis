# GB VTP Settlement Forensics (`vtpbmuanalysis`)

An interactive forensic analytics web application for Great Britain **Virtual Trading Party (VTP / BSC Modification P415)** activities, **mutualised supplier compensation payments**, and **EV charger baselining behaviour** built directly on public **Elexon SAA-I014** settlement data.

## Core Questions Answered

1. **When are VTPs trading?**
   - Half-hourly (`SP 1–48`) trading profiles overlaid against GB **System Buy Price (`sbp`)**, **Market Index Price (`mpj`)**, **Supplier Sourcing Cost (`ssc`)**, and the **23:30–05:30 EV off-peak tariff window**.
   - Interactive **Day × 48-Settlement-Period heatmap**, weekday vs weekend comparison, and per-VTP schedule overlays (e.g. Axle Energy, Reflexi, Joulen, Zenobe, Powerverse, Capture).
2. **Who (which suppliers) are receiving compensation — and who is paying?**
   - Aggregates granular **Primary × Secondary BMU × Settlement Period** records (`qcviji2 × ssc`) up to BSC Party level using Elexon's live **BSC Signatories directory** (`Party ID → Company Name` & registered BSC roles: `VT`, `VP`, `AV`, `TS`, `TG`).
   - Reconciles to **£0.00 variance** against Elexon's daily `party-level` mutualised pot (`scvp`) and computes every GB supplier's **Net Mutualisation Transfer (`sccp − scvp`)** and **Over-Index Ratio** (`Comp Share ÷ GB Demand Share`).
   - Separates **P415 wholesale compensation actions (`qcv ≠ 0`)** from **Balancing Mechanism VLP actions (`qsd ≠ 0, qcv = 0`)**.
3. **Are VTPs primarily focussing on EV chargers abusing baselining?**
   - A transparent **6-signal forensic engine** scores every active VTP on both **EV Charger Footprint (0–100)** and **Baselining Distortion Risk (0–100)**:
     1. **EV-Tariff Supplier Over-Representation**: share of volume landing on major EV-tariff domestic suppliers (Octopus Energy, E.ON Next, British Gas, OVO, ScottishPower) vs their true GB demand share derived from `scvp`.
     2. **National Domestic Footprint**: dispersion across all 14 GB GSP Groups (`_A`–`_P`) and share hitting `2__` Base Supplier (domestic/SME) BMUs, plus `AV` (Asset Metering VLP / CoP11) registration.
     3. **Energy Conservation Violation (Missing Rebound)**: ratio of positive turn-down (`+qcv`) to negative turn-up (`-qcv`). Energy-neutral load shifters must recharge shifted kWh; near-100% one-sided positive notifications imply un-notified overnight charging.
     4. **Wholesale Price Insensitivity (Low-Price Farming)**: % of turn-down triggered when `sbp < ssc` or `sbp < £60/MWh`, plus daily volume-vs-SBP scatter & Pearson correlation.
     5. **Continuous Duty Cycle & 00:00–05:30 EV Cliff**: average active hours/day and daytime-to-overnight drop-off aligned with Intelligent Octopus Go / Next Drive windows, plus pre-evening turn-up detection.
     6. **Multi-Day Persistence (Frozen BL01 Baseline)**: active day consistency and Coefficient of Variation (`CoV`) testing whether BL01 non-event lookback exclusions freeze an inflated baseline across weeks.

## Summary Report (HTML / Print-to-PDF)

A standalone, self-contained executive policy report with embedded inline SVG charts from **35 consecutive days of live Elexon SAA-I014 data (`2026-10-01` – `2026-11-04`, 647,682 SBMU×SP rows)** is checked into the repository:

- **[reports/vtp_baseline_bl01_audit_report.html](reports/vtp_baseline_bl01_audit_report.html)** (open in any browser; regenerated via `uv run python scripts/generate_report.py`)
- **[reports/vtp_baseline_bl01_audit_report.pdf](reports/vtp_baseline_bl01_audit_report.pdf)** (PDF rendering of the same report)

## Empirical Snapshot (35 Settled Days: `2026-10-01` – `2026-11-04`)

From live Elexon SAA-I014 settlement data (`bm-unit-level` + `primary-secondary-bm-unit-level`):
- **Baseline & BL01 Audit (647,682 SBMU×SP rows across 399 `V__*` SBMUs & 26 VTPs):**
  - **145,368 MWh** settled turn-down vs **59,811 MWh** un-notified overnight rebound (**41.1% leakage**, **£6.37M** implied unsettled SSC compensation).
  - **0.603 MWh/SP** non-active baseline MAE (`-0.216` bias), **+63.6 pp** asymmetric selection gap (`96.4%` positive on active SPs vs `32.8%` inactive), and **15,688 MWh (10.8%)** counter-economic turn-down (`SBP < SSC`).
  - **10 BL01** vs **3 self-nominated** VTPs (including `AXLEENER` frozen ~2× daytime BL01 lookback, `REFLEXI` 108.1% overnight rebound leakage, and `POWONTEC` 100% 2dp quantised self-nominated SEV).
- **October 30-day Mutualisation Snapshot (`2026-10-01` to `2026-10-30`, 678,111 BMU×SP records):**
  - **Total BMU-attributed compensation:** **£8.36m** (£278.7k/day, **~£101.7m/yr** annualised), reconciling to **£0.00** against total mutualised `scvp` (£8.36m).
  - **Net mutualisation winners:** Octopus Energy (`MERCURY`, +£2.92m net), E.ON Next (`NITTWO01`, +£1.05m net), British Gas (`BRITGAS`, +£659k net).
  - **Net mutualisation payers:** EDF Energy (`LENCO`, -£879k net), TotalEnergies (`TFEGP`, -£470k net), Npower Commercial (`NPOWER02`, -£419k net), Drax Energy Solutions (`HAVEN`, -£352k net).
  - **EV & Baselining Forensics:** **95.8%** (£8.01m) of compensation stems from EV-focused domestic aggregators (`EV Focus ≥ 65`), and **73.4%** (£6.13m) simultaneously exhibits high-risk baselining signatures (`Risk ≥ 65`).

## Public Elexon Data Sources (No API Key Required)

| Dataset | Endpoint |
| --- | --- |
| Primary / Secondary BMU × SP | `https://data.elexon.co.uk/saa/api/v1/i014/primary-secondary-bm-unit-level/{date}/{runType}` |
| Settlement Period Prices & SSC | `https://data.elexon.co.uk/saa/api/v1/i014/settlement-period-level/{date}/{runType}` |
| Party Daily Settlement (`sccp`/`scvp`) | `https://data.elexon.co.uk/saa/api/v1/i014/party-level/{date}/{runType}` |
| BMRS BM Unit Reference | `https://data.elexon.co.uk/bmrs/api/v1/reference/bmunits/all` |
| BSC Signatories Directory | `https://www.elexon.co.uk/bsc/about/elexon-key-contacts/bsc-signatories-qualified-persons/?signatory_id=all` |

## Quickstart

### Fast setup on a new PC (pre-built database — no ingest needed)

A ready-made SQLite database (`2026-10-01` – `2026-11-04` granular BMU×SP + SBMU baselines, plus 2-year macro history and reference data) is published as a GitHub Release asset, so you can skip the ~13 GB Elexon download.

1. Clone the repo and install dependencies:
   ```bash
   git clone https://github.com/literallymatt/vtpbmuanalysis.git
   cd vtpbmuanalysis
   uv sync --extra dev
   cd frontend && npm install && npm run build && cd ..
   ```
2. Download **`vtp_analysis_db.zip`** (~86 MB) from the [`data-2026-11-04` release](https://github.com/literallymatt/vtpbmuanalysis/releases/tag/data-2026-11-04).
3. Unzip it so the file ends up at **`data/vtp_analysis.db`** (create the `data/` folder if it doesn't exist). On Windows: right-click → *Extract All*; on Mac/Linux: `unzip vtp_analysis_db.zip -d data/`.
4. Run the dashboard (step 3 below) and open http://127.0.0.1:8000.

You can still fetch newer dates at any time from the web UI via **Fetch Elexon dates**, or with the ingest commands below.

### 1. Install dependencies

```bash
uv sync --extra dev
cd frontend && npm install && npm run build && cd ..
```

### 2. Ingest live Elexon settlement data

```bash
# Sync live BSC Signatories + BMRS BMUs + 30 days of granular BMU×SP data
uv run python -m backend.ingest --sync-ref --start 2026-10-01 --end 2026-10-30

# Optional: backfill 2-year macro P415 history (party-level + SP-level, every 3 days)
uv run python -m backend.ingest --start 2024-11-07 --end 2026-11-12 --macro-only --step 3
```

You can also fetch any additional date range directly from the web UI via **Fetch Elexon dates**.

### 3. Run the application

```bash
# Serves both the FastAPI backend and the built React frontend on http://127.0.0.1:8000
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

For frontend hot-reload development:

```bash
# Terminal 1
uv run uvicorn backend.main:app --reload --port 8000
# Terminal 2
cd frontend && npm run dev
```

### 4. Run tests

```bash
uv run pytest -v
```
