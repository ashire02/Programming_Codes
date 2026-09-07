# HRU Routing Length — DEM-based D8 Flow Paths

Computes the overland flow routing length of every HRU (Hydrologic
Response Unit) polygon directly from a DEM, using D8 flow directions —
no pre-computed flow accumulation raster required. Includes a separate
diagnostic script for checking DEM quality inside each HRU before you
trust the numbers.

Two scripts:

| Script | Purpose |
|---|---|
| `calculate_hru_routing_length.py` | Computes routing length per HRU, two ways (Option A and Option B) |
| `dem_diagnostic.py` | Visual + tabular DEM quality check per HRU (run this first) |

---

## Background: why two options?

An earlier accumulation-based approach (global flow accumulation,
routing length = distance along the accumulation-defined channel)
fragmented on small or oddly-shaped HRUs. Both scripts here instead
work purely from **local D8 flow direction** computed from the DEM
plus the HRU polygon boundary — no global accumulation grid needed.

- **Option A — "Highest-cell trace":** starts at the single
  highest-elevation cell inside the HRU, follows its D8 direction
  step-by-step until the path exits the HRU polygon, and returns the
  cumulative distance walked. Falls back to the next-highest cell only
  if the top cell is a D8 sink (no valid downslope direction).
  Interpretation: *"how far does water travel from the watershed
  divide to the outlet?"*
- **Option B — "Maximum path":** for **every** cell in the HRU,
  computes its D8 path distance to the nearest exit from the HRU
  polygon, then returns the maximum over all cells. Implemented as an
  O(n) backward breadth-first search (seed the exit cells, propagate
  distances upstream through the D8 graph) rather than tracing forward
  from every cell, so it stays fast even on large HRUs.
  Interpretation: *"what is the longest possible flow path inside the
  HRU?"*

Both routing lengths, plus per-HRU elevation range and DEM-NaN
percentage, are written to CSV so you can compare them and sanity-check
against DEM quality.

## `calculate_hru_routing_length.py`

### What it does, step by step

1. Loads the HRU shapefile and DEM raster.
2. Auto-detects (or uses a fixed) HRU ID column, printing all non-geometry
   columns with dtype/uniqueness/sample values to help you verify it picked
   the right one.
3. Reprojects the HRU polygons to the DEM's CRS if needed, and derives
   per-cell size in **metres** even for a geographic (lat/lon) DEM CRS
   (approximated at the HRU centroid latitude).
4. Computes a full-DEM D8 flow-direction grid (8 neighbours, steepest
   descent). A tiny deterministic random perturbation
   (`np.random.default_rng(42)`, ≤ 1e-4) is added to break elevation ties
   on flat, pit-filled areas so every valid cell gets a direction.
5. For every HRU polygon: rasterizes it onto the DEM grid, checks DEM
   coverage/quality (NaN %, elevation range), computes both routing
   lengths, and records area, cell counts, and elevation stats.
6. If the same `HRU_ID` appears on multiple polygon rows (multipart
   features), aggregates them into one row via an **area-weighted
   average** of routing length and elevation stats.
7. Writes two CSVs — one per option — plus a printed side-by-side
   comparison table.

### Configuration (top of the script)

```python
HRU_SHAPEFILE = r"C:\path\to\your\hru.shp"
DEM_RASTER    = r"C:\path\to\your\dem.tif"        # should be pit-filled
OUTPUT_DIR    = r"C:\path\to\results"
OUTPUT_CSV_A  = os.path.join(OUTPUT_DIR, "hru_routing_lengths_option_a.csv")
OUTPUT_CSV_B  = os.path.join(OUTPUT_DIR, "hru_routing_lengths_option_b.csv")

HRU_ID_FIELD  = "h_r_u"   # exact column name holding HRU IDs; set to None to auto-detect
```

Set `HRU_ID_FIELD = None` on a new dataset to let the script pick the
most likely ID column (it favours integer columns whose max value is
close to the number of unique values), then check the printed
`>>> Auto-detected HRU ID field:` line and hard-code it once confirmed.

### How to run

```bash
pip install geopandas rasterio numpy pandas shapely
cd hru_routing_length
python calculate_hru_routing_length.py
```

### Output CSVs

Both `hru_routing_lengths_option_a.csv` and `..._option_b.csv` share
these columns:

| Column | Meaning |
|---|---|
| `HRU_ID` | HRU identifier |
| `routing_length_m` | Option A or B routing length, in metres |
| `total_area_m2` | HRU polygon area (area-weighted sum if aggregated) |
| `n_polygons` | Number of polygon parts merged into this HRU_ID |
| `total_cells` | DEM cells covered by the HRU |
| `total_nan_cells` | DEM cells with no data inside the HRU |
| `nan_pct` | `total_nan_cells / total_cells * 100` |
| `elev_min_m`, `elev_max_m`, `elev_range_m` | Elevation range inside the HRU |

### Reading the console warnings

- **`*** CHECK DEM ***` / zero DEM cells:** the HRU polygon doesn't
  overlap the DEM extent at all — reproject/re-clip your DEM.
- **NaN % > 20:** the DEM has significant gaps inside this HRU;
  routing length for it is unreliable.
- **Elevation range < one cell height:** the HRU is nearly flat inside
  the DEM — a common sign of a pit-filling artifact rather than real
  terrain; routing length here may be dominated by the tie-breaking
  perturbation rather than real slope.

Run `dem_diagnostic.py` on any HRU that triggers these warnings before
trusting its routing length.

## `dem_diagnostic.py`

A companion visual/tabular check of DEM quality per HRU — run this
**before** relying on the routing-length output, especially for any
HRU flagged above.

### What it produces (all saved to `OUTPUT_DIR`)

| Output | Contents |
|---|---|
| `diagnostic_overview.png` | Full-DEM hillshade with all HRU boundaries overlaid; red = DEM nodata cells, so you can see at a glance whether any HRU falls outside or partially outside the DEM extent |
| `diagnostic_hru<ID>_detail.png` | Four panels for one chosen HRU: (A) elevation with NaN in red, (B) flow accumulation (log scale), (C) D8 flow-direction arrows, (D) routing path from divide to outlet, colour-coded by path length |
| `diagnostic_hru<ID>_profile.png` | Elevation profile along that HRU's routing path |
| `dem_diagnostic_stats.csv` | Per-HRU cell count, NaN count/%, elevation min/max/range, and `NODATA`/`FLAT` flags |

### Configuration

Same `HRU_SHAPEFILE`, `DEM_RASTER`, `OUTPUT_DIR`, `HRU_ID_FIELD`
pattern as the main script, plus a `CHECK_HRU_ID` setting near the top
picking which single HRU gets the detail plots and elevation profile.

### How to run

```bash
pip install geopandas rasterio numpy pandas matplotlib shapely
cd hru_routing_length
python dem_diagnostic.py
```

Uses matplotlib's non-interactive `Agg` backend, so it runs fine
without a display (e.g. over SSH or in a headless environment) — plots
are written straight to PNG.

## Requirements

```
geopandas
rasterio
numpy
pandas
shapely
matplotlib   # dem_diagnostic.py only
```

## Notes / gotchas

- Both scripts expect a **pit-filled** DEM. An unfilled DEM will
  produce many D8 sinks and unreliable routing lengths.
- File paths in both scripts currently point at a specific local
  Windows path (`C:\Users\...`) — edit `HRU_SHAPEFILE`, `DEM_RASTER`,
  and `OUTPUT_DIR` at the top of each script before running.
- The tie-breaking perturbation uses a fixed random seed (`42`), so
  results are reproducible run-to-run given the same inputs.
