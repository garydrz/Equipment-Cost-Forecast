# EPC Parametric Cost Estimator — PRD

## Original Problem Statement
Build a mono-user application maintaining a historical repository of industrial equipment and using it to generate parametric cost estimates for single equipment and full EPC projects, via AACE capacity factor method corrected by a steel/oil temporal escalation index, producing expected value + confidence interval at both equipment and project level.

## Architecture
- Backend: FastAPI + MongoDB (motor)
- Frontend: React 19 + Shadcn UI + Tailwind (Swiss / Klein Blue technical design)
- External APIs: FRED (steel PPI WPU101706, Brent oil DCOILBRENTEU) with 6h in-memory cache & fallback data; Frankfurter for EUR/USD FX
- Collections: `equipment_historical`, `projects`, `equipment_rows`, `scale_exponents`, `escalation_weights`

## User Personas
- Cost engineer / EPC project manager evaluating oil & gas / petrochemical / power plant CAPEX

## Core Requirements (Static)
- 9 equipment categories, 6 materials
- AACE 18R-97 capacity factor method: Cost_new = Cost_hist × (Size_new / Size_hist)^n
- Escalation composite = 1 + steel_w × Δ%_steel + oil_w × Δ%_oil (per category)
- Confidence intervals: observed dispersion when ≥3 refs, else AACE class defaults (Class 3/4/5)
- Project total via statistical propagation (sum in quadrature of per-row half-ranges)
- Currency: EUR/USD with historical + latest FX conversion

## Implemented (2026-02)
- Full CRUD: historical equipment, projects, equipment rows
- Admin panel: editable scale exponents & steel/oil weights per category
- Live estimate preview endpoint + on-form preview
- Seed: 13 historical records + 1 DUMMY project with 8 equipment lines
- Sidebar layout: Projects, Historical Repository, Admin, Indices
- Backend testing: 15/15 passed (100%)

## Backlog
- P1: CSV/Excel import for historical repository
- P1: Multi-reference explicit selection dialog (currently automatic)
- P2: Export project estimate to PDF/Excel
- P2: Chart visualisation of cost drivers per project
- P2: Historical vs current cost comparison charts
