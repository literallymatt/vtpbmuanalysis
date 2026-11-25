# Drax Energy Solutions (`HAVEN`) — P415 VTP Supplier Compensation & Volume Analysis

**Coverage:** `2024-11-07` (BSC Modification P415 go-live) to `2026-11-18` (latest Elexon SAA-I014 settled date) — **738 daily settlement records** (`100%` daily coverage for all active months from May 2025 onward; 4 missing days in Dec 2024 / Apr 2025 occurred during £0.00/day periods).

**Primary BSC Party analysed:** `HAVEN` — **Drax Energy Solutions Limited** (roles: `BP`, `TS`, `MV`). Other Drax Group BSC Parties (`DRAX` — Drax Power Limited; `DPSL` — Drax Pumped Storage Limited) are generators (`TG`) with **£0.00** in both `sccp` and `scvp` across all dates.

---

## 1. Executive Summary

| Metric (7 Nov 2024 – 18 Nov 2026 · 738 days) | Days | Implied Volume (MWh) | Cashflow (£) |
| --- | ---: | ---: | ---: |
| **Turn-Down (`+QCV`, compensation paid *to* Drax)** | 328 | **+396.02 MWh** | **+£39,750.37** |
| **Turn-Up (`−QCV`, compensation clawed back *from* Drax)** | 20 | **−216.51 MWh** | **−£21,332.21** |
| **Gross VTP Volume (`|turn-down| + |turn-up|`)** | 348 | **612.53 MWh** | — |
| **Net Supplier Compensation Received (`sccp`)** | 738 | **+179.51 MWh** | **+£18,418.16** |
| **Mutualised Compensation Levy Paid (`scvp`)** | 738 | — | **£4,000,728.88** |
| **Net P415 Mutualisation Transfer (`sccp − scvp`)** | 738 | — | **−£3,982,310.72** |

### Headline Findings
1. **Heavily net payer under P415 mutualisation:** Over the first two years of P415, Drax Energy Solutions has paid **£4.00m** into the GB-wide mutualised supplier compensation pot (`scvp`), while receiving only **£18,418.16** net in direct supplier compensation (`sccp`) — recovering just **0.46%** of its mutualised levy.
2. **Negligible direct activity until March 2026:** Across the first 16 months (`2024-11` to `2026-02`), total `sccp` on `HAVEN` was just **£89.07** (**+1.01 MWh**). Direct VTP activity began in March–May 2026 (+85.0 MWh), paused in June 2026 (0.0 MWh), saw large negative turn-up events in August–September 2026 (−212.7 MWh), and ramped up to sustained daily positive turn-down from late September 2026 onward (**+253.0 MWh** across October and 1–18 November 2026).
3. **35-day granular cross-check (`2026-10-01` – `2026-11-04`):** In the exact half-hourly `primary-secondary-bm-unit-level` dataset, `HAVEN` received **£17,898.23** (`sccp`) against **£445,088.71** paid (`scvp`, net **−£427,190.48**), driven by **+168.80 MWh** turn-down and **−0.70 MWh** turn-up (**+168.11 MWh** net). **96.6%** of this compensation came from **FlexiVolt Ltd (`FLXVL824`)**.

---

## 2. How Negative Supplier Compensation (`sccp < 0`) Occurs Under P415

Under BSC Modification P415, supplier compensation is symmetric and computed per settlement period as:

$$\text{Compensation}_{i,j} = QCV_{i,j} \times SSC_j$$

where **`SSC`** is Elexon's fixed quarterly **Supplier Sourcing Cost** (strictly positive — between **£82.26/MWh** and **£106.47/MWh** over the period) and **`QCV`** is the VTP's delivered virtual volume on that supplier's meters:

- **Positive `QCV > 0` (turn-down / export increase) → Positive `sccp` (supplier is paid):** A VTP instructs a customer to consume less (or export more) than baseline. The supplier loses retail sales on energy already hedged, so P415 pays the supplier `QCV × SSC`.
- **Negative `QCV < 0` (turn-up / charging / export reduction) → Negative `sccp` (supplier pays back):** A VTP instructs a customer (e.g., a behind-the-meter battery charging, flexible I&C load ramping up, or embedded generation turning down) to **increase net import above baseline** (or fails to deliver a notified turn-down so actual import exceeds baseline). Because Elexon shifts that extra volume into the VTP's wholesale account while the supplier still bills the customer for the extra metered kWh, P415 claws back `|QCV| × SSC` from the supplier.

### Empirical Evidence from August–September 2026
- On Drax's three largest negative days — `2026-08-13` (**−£4,883.98** / −49.57 MWh), `2026-09-18` (**−£4,658.30** / −47.28 MWh), and `2026-08-31` (**−£3,033.77** / −30.79 MWh) — quarterly `SSC` was **£98.53/MWh** (positive).
- Across the entire GB market on all three dates, **only two suppliers** recorded material negative `sccp` (`< −£10`): **Drax Energy Solutions (`HAVEN`)** and **Coulomb Energy Supply (`COULOMB`)**, both commercial/industrial & flexibility-oriented suppliers rather than domestic EV-tariff suppliers.

---

## 3. Monthly Cashflow & Implied Volume Breakdown (`2024-11` – `2026-11`)

Daily implied volumes are calculated as `sccp ÷ SSC` using Elexon's verified quarterly `SSC` schedule:

| Quarter | Period | `SSC` (£/MWh) |
| --- | --- | ---: |
| 2024 Q4 | `2024-11-07` – `2024-12-31` | £93.15 |
| 2025 Q1 | `2025-01-01` – `2025-03-31` | £91.58 |
| 2025 Q2 | `2025-04-01` – `2025-06-30` | £99.95 |
| 2025 Q3 | `2025-07-01` – `2025-09-30` | £90.91 |
| 2025 Q4 | `2025-10-01` – `2025-12-31` | £89.47 |
| 2026 Q1 | `2026-01-01` – `2026-03-31` | £87.21 |
| 2026 Q2 | `2026-04-01` – `2026-06-30` | £82.26 |
| 2026 Q3 | `2026-07-01` – `2026-09-30` | £98.53 |
| 2026 Q4 | `2026-10-01` – `2026-11-18` | £106.47 |

### Full Monthly Table

| Month | Settled Days | Turn-Down (+MWh) | Turn-Up (−MWh) | Net `sccp` (£) | Mutualised `scvp` (£) | Net (`sccp − scvp`) (£) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2024-11 | 24 | 0.00 | 0.00 | £0.00 | £0.00 | £0.00 |
| 2024-12 | 29 | 0.00 | 0.00 | £0.00 | £0.41 | −£0.41 |
| 2025-01 | 31 | 0.02 | −0.01 | £1.45 | −£101.76 | £103.21 |
| 2025-02 | 28 | 0.00 | 0.00 | −£0.04 | £703.92 | −£703.96 |
| 2025-03 | 31 | 0.00 | 0.00 | £0.00 | £3,997.41 | −£3,997.41 |
| 2025-04 | 28 | 0.00 | 0.00 | £0.00 | £11,276.58 | −£11,276.58 |
| 2025-05 | 31 | 0.00 | 0.00 | £0.00 | £16,782.04 | −£16,782.04 |
| 2025-06 | 30 | 0.00 | 0.00 | £0.00 | £21,007.06 | −£21,007.06 |
| 2025-07 | 31 | 0.00 | 0.00 | £0.00 | £23,320.65 | −£23,320.65 |
| 2025-08 | 31 | 0.00 | 0.00 | £0.00 | £32,816.47 | −£32,816.47 |
| 2025-09 | 30 | 0.00 | 0.00 | £0.00 | £36,114.06 | −£36,114.06 |
| 2025-10 | 31 | 0.01 | 0.00 | £1.34 | £49,059.95 | −£49,058.61 |
| 2025-11 | 30 | 0.26 | 0.00 | £23.04 | £86,745.10 | −£86,722.06 |
| 2025-12 | 31 | 0.25 | 0.00 | £22.27 | £130,800.50 | −£130,778.23 |
| 2026-01 | 31 | 0.27 | 0.00 | £23.62 | £220,745.72 | −£220,722.10 |
| 2026-02 | 28 | 0.20 | 0.00 | £17.39 | £233,261.54 | −£233,244.15 |
| 2026-03 | 31 | 23.15 | 0.00 | £2,019.07 | £114,905.64 | −£112,886.57 |
| 2026-04 | 30 | 40.05 | 0.00 | £3,294.77 | £123,087.18 | −£119,792.41 |
| 2026-05 | 31 | 21.78 | 0.00 | £1,791.70 | £246,928.31 | −£245,136.61 |
| 2026-06 | 30 | 0.00 | 0.00 | £0.00 | £331,023.74 | −£331,023.74 |
| 2026-07 | 31 | 26.14 | −3.77 | £2,203.89 | £626,784.79 | −£624,580.90 |
| 2026-08 | 31 | 0.28 | −126.38 | −£12,424.32 | £679,584.71 | −£692,009.03 |
| 2026-09 | 30 | 30.60 | −86.35 | −£5,493.23 | £368,076.45 | −£373,569.68 |
| 2026-10 | 31 | 139.89 | 0.00 | £14,893.82 | £383,515.33 | −£368,621.51 |
| 2026-11 *(to 18 Nov)* | 18 | 113.12 | 0.00 | £12,043.39 | £260,293.08 | −£248,249.69 |
| **Total** | **738** | **+396.02** | **−216.51** | **£18,418.16** | **£4,000,728.88** | **−£3,982,310.72** |

---

## 4. Largest Single-Day Events

### Top 5 Negative Compensation Days (Net Turn-Up)

| Date | Run Type | `sccp` (£) | Implied Volume (MWh) | `scvp` (£) |
| --- | --- | ---: | ---: | ---: |
| `2026-08-13` | `R1` | −£4,883.98 | −49.57 | £26,628.03 |
| `2026-09-18` | `R1` | −£4,658.30 | −47.28 | £15,994.03 |
| `2026-08-31` | `R1` | −£3,033.77 | −30.79 | £13,760.67 |
| `2026-08-30` | `R1` | −£2,481.35 | −25.18 | £15,606.66 |
| `2026-09-01` | `R1` | −£2,475.92 | −25.13 | £16,972.03 |

### Top 5 Positive Compensation Days (Net Turn-Down)

| Date | Run Type | `sccp` (£) | Implied Volume (MWh) | `scvp` (£) |
| --- | --- | ---: | ---: | ---: |
| `2026-11-18` | `II` | +£1,065.50 | +10.01 | £14,401.29 |
| `2026-11-11` | `II` | +£997.23 | +9.37 | £13,193.72 |
| `2026-11-02` | `SF` | +£908.79 | +8.54 | £16,535.66 |
| `2026-11-14` | `II` | +£866.36 | +8.14 | £11,952.44 |
| `2026-11-12` | `II` | +£829.29 | +7.79 | £12,895.07 |

---

## 5. Granular VTP Attribution & Intra-Day Netting Check (`2026-10-01` – `2026-11-04`)

Because Elexon's `party-level` dataset aggregates each day to a single net `sccp`, dividing daily `sccp` by `SSC` separates **net turn-down days** from **net turn-up days** (intra-day turn-up and turn-down within the same settlement day net out).

Cross-checking against the 35-day half-hourly granular `primary-secondary-bm-unit-level` dataset (`2026-10-01` – `2026-11-04`, 959 `HAVEN` BMU×SP rows) shows that intra-day netting is minimal (**0.4%**):

| VTP Party ID | Company Name | Turn-Down (`+qcv` MWh) | Turn-Up (`−qcv` MWh) | Net Compensation (£) | Share |
| --- | --- | ---: | ---: | ---: | ---: |
| `FLXVL824` | FlexiVolt Ltd | +162.93 | −0.61 | £17,282.72 | 96.6% |
| `ZENOBER1` | Zenobe Rental 1 Limited | +5.43 | −0.09 | £568.77 | 3.2% |
| `REFLEXI` | REFLEXI UK LIMITED | +0.40 | 0.00 | £42.08 | 0.2% |
| `LONDELEC` | EDF Energy Limited | +0.04 | 0.00 | £4.66 | 0.0% |
| **Total (35 days)** | | **+168.80** | **−0.70** | **£17,898.23** | **100.0%** |

---

## 6. Data & Reproducibility

- **Daily CSV dataset:** [`reports/drax_haven_daily_sccp.csv`](drax_haven_daily_sccp.csv) (738 rows: `date`, `run_type`, `sccp`, `scvp`, `ssc`, `implied_mwh`).
- **Source API:** Public Elexon SAA-I014 `party-level` endpoint (`https://data.elexon.co.uk/saa/api/v1/i014/party-level/{date}/{runType}`), selecting the most reconciled available settlement run (`RF` → `R3` → `R2` → `R1` → `SF` → `II`).
- **Regenerate dataset:**
  ```bash
  uv run python scripts/pull_drax_supplier_compensation.py
  ```
