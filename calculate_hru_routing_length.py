# =============================================================================
# HRU ROUTING LENGTH — OPTION A and OPTION B
# =============================================================================
#
# TWO APPROACHES (both replace the previous accumulation-based method):
#
# OPTION A — "Highest-cell trace"
#   Start at the single highest-elevation cell inside the HRU.
#   Follow D8 directions step-by-step until the path exits the HRU polygon.
#   Routing length = cumulative distance walked.
#   Falls back to the next-highest cell only if the top cell is a D8 sink.
#   Concept: "how far does water travel from the watershed divide to the exit?"
#
# OPTION B — "Maximum path"
#   For every cell in the HRU, compute its D8 path distance to the nearest
#   HRU boundary exit. Routing length = the MAXIMUM over all cells.
#   Uses an O(n) backward BFS (seed exits, propagate upstream).
#   Concept: "what is the longest possible flow path inside the HRU?"
#
# Both options use only the DEM (for D8 directions) and HRU polygon.
# Global flow accumulation is NOT needed by either method.
#
# Requirements:
#   pip install geopandas rasterio numpy pandas shapely
# =============================================================================

import os
import warnings
from collections import deque

import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.features import rasterize

warnings.filterwarnings("ignore")


# =============================================================================
# USER-CONFIGURABLE SETTINGS
# =============================================================================

HRU_SHAPEFILE = r"C:\Users\ash_i\Downloads\routing_length\hru\NO_HRU_UTM45_merge.shp"
DEM_RASTER    = r"C:\Users\ash_i\Downloads\routing_length\phorse_dem\demphortfilll.tif"
OUTPUT_DIR    = r"C:\Users\ash_i\Downloads\routing_length\results"
OUTPUT_CSV_A  = os.path.join(OUTPUT_DIR, "hru_routing_lengths_option_a.csv")
OUTPUT_CSV_B  = os.path.join(OUTPUT_DIR, "hru_routing_lengths_option_b.csv")

# Exact column name holding HRU IDs (set to None to auto-detect)
HRU_ID_FIELD  = "h_r_u"


# =============================================================================
# STEP 1 — LOAD DATA
# =============================================================================
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("[1/5] Loading HRU shapefile ...")
hru_gdf = gpd.read_file(HRU_SHAPEFILE)
n_polys = len(hru_gdf)
print(f"      {n_polys} polygons   CRS: {hru_gdf.crs}")

non_geom = [c for c in hru_gdf.columns if c.lower() != "geometry"]
print(f"\n      {'Column':<22} {'dtype':<12} {'unique':>6}  sample values")
print(f"      {'-'*22} {'-'*12} {'-'*6}  {'-'*30}")
for col in non_geom:
    print(f"      {col:<22} {str(hru_gdf[col].dtype):<12} "
          f"{hru_gdf[col].nunique():>6}  "
          f"{hru_gdf[col].dropna().unique()[:4].tolist()}")

if HRU_ID_FIELD is None:
    candidates = []
    for col in non_geom:
        num = pd.to_numeric(hru_gdf[col], errors="coerce")
        if num.notna().mean() < 0.9:
            continue
        vals = num.dropna()
        if vals.min() < 0 or vals.max() > 10_000:
            continue
        ucount = hru_gdf[col].nunique()
        if ucount < 2:
            continue
        is_int = bool((vals == vals.round()).all())
        score  = (3 * is_int) + (2 * (abs(vals.max() - ucount) <= max(3, ucount * 0.1)))
        candidates.append((col, ucount, score))
    candidates.sort(key=lambda x: (-x[2], -x[1]))
    HRU_ID_FIELD = candidates[0][0] if candidates else non_geom[0]
    print(f"\n      >>> Auto-detected HRU ID field: '{HRU_ID_FIELD}'")
    print("          Set HRU_ID_FIELD at the top if wrong.")
else:
    print(f"\n      HRU ID field: '{HRU_ID_FIELD}'  "
          f"({hru_gdf[HRU_ID_FIELD].nunique()} unique values)")

print("\n[1/5] Loading DEM ...")
with rasterio.open(DEM_RASTER) as src:
    dem_full   = src.read(1).astype(np.float64)
    transform  = src.transform
    dem_crs    = src.crs
    nodata_val = src.nodata if src.nodata is not None else -9999.0
    n_rows, n_cols = dem_full.shape
    cell_w = abs(transform.a)
    cell_h = abs(transform.e)

dem_full[dem_full == nodata_val] = np.nan
print(f"      Shape: {n_rows} x {n_cols}   CRS: {dem_crs}")


# =============================================================================
# STEP 2 — CRS ALIGNMENT + CELL SIZES IN METRES
# =============================================================================
print("\n[2/5] Aligning CRS ...")

if hru_gdf.crs is None:
    raise ValueError("HRU shapefile has no CRS.")

if hru_gdf.crs != dem_crs:
    print(f"      Reprojecting HRU: {hru_gdf.crs} → {dem_crs}")
    hru_gdf = hru_gdf.to_crs(dem_crs)

if dem_crs.is_geographic:
    try:
        union = hru_gdf.geometry.union_all()
    except AttributeError:
        union = hru_gdf.geometry.unary_union
    lat      = float(union.centroid.y)
    cell_x_m = cell_w * 111_320.0 * abs(np.cos(np.radians(lat)))
    cell_y_m = cell_h * 111_320.0
    print(f"      Geographic CRS → cell_x={cell_x_m:.2f} m  cell_y={cell_y_m:.2f} m")
else:
    cell_x_m = float(cell_w)
    cell_y_m = float(cell_h)
    print(f"      Projected CRS  → cell_x={cell_x_m:.2f} m  cell_y={cell_y_m:.2f} m")

diag_m = float(np.sqrt(cell_x_m**2 + cell_y_m**2))

# D8 code → (row_offset, col_offset, step_distance_m)
D8 = {
     64: (-1,  0, cell_y_m),   # N
    128: (-1,  1, diag_m),     # NE
      1: ( 0,  1, cell_x_m),   # E
      2: ( 1,  1, diag_m),     # SE
      4: ( 1,  0, cell_y_m),   # S
      8: ( 1, -1, diag_m),     # SW
     16: ( 0, -1, cell_x_m),   # W
     32: (-1, -1, diag_m),     # NW
}


# =============================================================================
# STEP 3 — D8 FLOW DIRECTION
# =============================================================================
print("\n[3/5] Computing D8 flow direction ...")


def _compute_d8(dem, cx, cy):
    diag = np.sqrt(cx**2 + cy**2)
    nbrs = [
        (-1,  0,  64, cy),
        (-1,  1, 128, diag),
        ( 0,  1,   1, cx),
        ( 1,  1,   2, diag),
        ( 1,  0,   4, cy),
        ( 1, -1,   8, diag),
        ( 0, -1,  16, cx),
        (-1, -1,  32, diag),
    ]
    nr, nc   = dem.shape
    valid    = ~np.isnan(dem)
    best_slp = np.full((nr, nc), -np.inf)
    fdir     = np.zeros((nr, nc), dtype=np.int16)

    for dr, dc, code, dist in nbrs:
        r0, r1   = max(0, -dr), nr - max(0,  dr)
        c0, c1   = max(0, -dc), nc - max(0,  dc)
        nr0, nr1 = max(0,  dr), nr - max(0, -dr)
        nc0, nc1 = max(0,  dc), nc - max(0, -dc)
        cur  = dem[r0:r1, c0:c1]
        nbr  = dem[nr0:nr1, nc0:nc1]
        ok   = valid[r0:r1, c0:c1] & valid[nr0:nr1, nc0:nc1]
        slp  = np.where(ok, (cur - nbr) / dist, -np.inf)
        better = slp > best_slp[r0:r1, c0:c1]
        best_slp[r0:r1, c0:c1] = np.where(better, slp,  best_slp[r0:r1, c0:c1])
        fdir[r0:r1, c0:c1]     = np.where(better, code, fdir[r0:r1, c0:c1])

    return fdir


# Tiny random perturbation breaks elevation ties on flat areas common in
# pit-filled DEMs, ensuring every valid cell gets a non-zero D8 direction.
rng        = np.random.default_rng(42)
dem_for_d8 = dem_full.copy()
valid_mask = ~np.isnan(dem_for_d8)
dem_for_d8[valid_mask] += rng.uniform(0, 1e-4, int(valid_mask.sum()))

fdir_full = _compute_d8(dem_for_d8, cell_x_m, cell_y_m)
n_sinks   = int(((fdir_full == 0) & valid_mask).sum())
print(f"      Done.  Remaining sink cells: {n_sinks:,}")


# =============================================================================
# STEP 4 — ROUTING LENGTH FUNCTIONS
# =============================================================================

def _routing_length_a(hru_mask, fdir_arr, dem_arr):
    """
    Option A — D8 path from the highest elevation cell to the HRU boundary.

    Finds the highest-elevation cell, follows its D8 path step-by-step, stops
    when the path exits the HRU polygon. Returns the cumulative distance.
    Falls back to the next-highest cell only if the top cell is a D8 sink.
    """
    r_idx, c_idx = np.where(hru_mask)
    if len(r_idx) == 0:
        return np.nan

    hru_elevs  = dem_arr[r_idx, c_idx]
    sort_order = np.argsort(-np.where(np.isnan(hru_elevs), -np.inf, hru_elevs))
    n_rows, n_cols = fdir_arr.shape

    for idx in sort_order:
        if np.isnan(hru_elevs[idx]):
            continue

        r, c = int(r_idx[idx]), int(c_idx[idx])
        dist    = 0.0
        visited = set()

        while True:
            if (r, c) in visited:
                break                          # cycle guard
            visited.add((r, c))

            d = int(fdir_arr[r, c])
            if d not in D8:
                break                          # D8 sink — stop tracing

            dr, dc, step = D8[d]
            r2, c2 = r + dr, c + dc
            dist += step

            if (r2 < 0 or r2 >= n_rows or c2 < 0 or c2 >= n_cols
                    or not hru_mask[r2, c2]):
                break                          # exited the HRU polygon

            r, c = r2, c2

        if dist > 0:
            return dist                        # first non-sink cell → done

    return np.nan


def _routing_length_b(hru_mask, fdir_arr):
    """
    Option B — Maximum D8 path from any cell to the HRU boundary.

    For every HRU cell, computes the D8 path distance to where it first exits
    the HRU polygon. Returns the maximum over all cells.

    Uses an O(n) backward BFS: seeds exit cells (whose D8 leaves the HRU),
    then propagates upstream through the D8 graph to assign distances to all
    reachable cells. This avoids the forward-ordering fragmentation issue that
    plagued the previous flow-accumulation approach.
    """
    r_idx, c_idx = np.where(hru_mask)
    if len(r_idx) == 0:
        return np.nan

    pad  = 1
    rmin = max(0, int(r_idx.min()) - pad)
    rmax = min(fdir_arr.shape[0], int(r_idx.max()) + pad + 1)
    cmin = max(0, int(c_idx.min()) - pad)
    cmax = min(fdir_arr.shape[1], int(c_idx.max()) + pad + 1)

    mask = hru_mask[rmin:rmax, cmin:cmax]
    fdir = fdir_arr[rmin:rmax, cmin:cmax]
    rl   = r_idx - rmin
    cl   = c_idx - cmin
    MR, MC = mask.shape

    dist  = np.full((MR, MC), np.nan)
    queue = deque()

    # Seed: HRU cells whose D8 exits the HRU polygon (or are sinks)
    for r, c in zip(rl, cl):
        d = int(fdir[r, c])
        if d not in D8:
            dist[r, c] = 0.0             # D8 sink — path ends here
            queue.append((r, c))
            continue
        dr, dc, step = D8[d]
        r2, c2 = r + dr, c + dc
        if r2 < 0 or r2 >= MR or c2 < 0 or c2 >= MC or not mask[r2, c2]:
            dist[r, c] = step            # one step to exit
            queue.append((r, c))

    # Backward BFS: propagate distances from exits to upstream cells
    while queue:
        r2, c2 = queue.popleft()
        d2 = dist[r2, c2]
        # Find all HRU cells that flow INTO (r2, c2)
        for code, (dr, dc, step) in D8.items():
            r, c = r2 - dr, c2 - dc
            if r < 0 or r >= MR or c < 0 or c >= MC:
                continue
            if not mask[r, c]:
                continue
            if int(fdir[r, c]) != code:
                continue
            if np.isnan(dist[r, c]):
                dist[r, c] = step + d2
                queue.append((r, c))

    vals  = dist[rl, cl]
    valid = vals[~np.isnan(vals)]
    return float(np.max(valid)) if len(valid) > 0 else np.nan


# =============================================================================
# STEP 5 — PROCESS EVERY HRU POLYGON
# =============================================================================
print(f"\n[5/5] Computing routing lengths for {n_polys} HRUs ...")

records    = []
warn_lines = []

print(f"  {'HRU':>4}  {'cells':>6}  {'elev_min':>9}  {'elev_max':>9}  "
      f"{'opt_A_m':>10}  {'opt_B_m':>10}  {'area_m2':>14}")
print(f"  {'-'*4}  {'-'*6}  {'-'*9}  {'-'*9}  "
      f"{'-'*10}  {'-'*10}  {'-'*14}")

for _, row in hru_gdf.iterrows():
    hru_id = row[HRU_ID_FIELD]
    geom   = row.geometry

    if geom is None or geom.is_empty:
        print(f"  HRU {hru_id}: empty geometry — skipped")
        continue

    # Area in m²
    if dem_crs.is_geographic:
        try:
            utm     = gpd.GeoSeries([geom], crs=hru_gdf.crs).estimate_utm_crs()
            area_m2 = float(
                gpd.GeoSeries([geom], crs=hru_gdf.crs).to_crs(utm).area.iloc[0]
            )
        except Exception:
            area_m2 = None
    else:
        area_m2 = float(geom.area)

    # Rasterize HRU polygon onto the DEM grid
    hru_mask = rasterize(
        [(geom, 1)],
        out_shape=(n_rows, n_cols),
        transform=transform,
        fill=0,
        dtype=np.uint8,
    ).astype(bool)

    n_cells = int(hru_mask.sum())
    if n_cells == 0:
        print(f"  HRU {hru_id}: no overlapping DEM cells — "
              f"HRU may lie OUTSIDE the DEM extent  *** CHECK DEM ***")
        warn_lines.append(f"  HRU {hru_id}: zero DEM cells — outside DEM extent?")
        continue

    if area_m2 is None:
        area_m2 = n_cells * cell_x_m * cell_y_m

    # ── DEM quality check ─────────────────────────────────────────────────
    elev_in_hru = dem_full[hru_mask]
    n_nan       = int(np.isnan(elev_in_hru).sum())
    nan_pct     = 100.0 * n_nan / n_cells
    valid_elevs = elev_in_hru[~np.isnan(elev_in_hru)]
    elev_min    = float(valid_elevs.min()) if len(valid_elevs) > 0 else np.nan
    elev_max    = float(valid_elevs.max()) if len(valid_elevs) > 0 else np.nan
    elev_range  = elev_max - elev_min if not np.isnan(elev_min) else np.nan
    n_valid     = n_cells - n_nan

    if nan_pct > 20:
        warn_lines.append(
            f"  HRU {hru_id:>3}: {nan_pct:.0f}% NaN — DEM has gaps  *** CHECK DEM ***"
        )
    if n_valid > 4 and not np.isnan(elev_range) and elev_range < cell_y_m:
        warn_lines.append(
            f"  HRU {hru_id:>3}: elevation range {elev_range:.1f} m — "
            f"nearly flat (pit-fill artifact?)  *** CHECK DEM ***"
        )

    # ── Compute both routing lengths ──────────────────────────────────────
    rl_a = _routing_length_a(hru_mask, fdir_full, dem_full)
    rl_b = _routing_length_b(hru_mask, fdir_full)

    records.append({
        "HRU_ID":                hru_id,
        "routing_length_a_m":   round(rl_a, 3) if not np.isnan(rl_a) else np.nan,
        "routing_length_b_m":   round(rl_b, 3) if not np.isnan(rl_b) else np.nan,
        "area_m2":              round(area_m2, 2),
        "n_cells":              n_cells,
        "n_nan_cells":          n_nan,
        "nan_pct":              round(nan_pct, 1),
        "elev_min_m":           round(elev_min, 1) if not np.isnan(elev_min) else np.nan,
        "elev_max_m":           round(elev_max, 1) if not np.isnan(elev_max) else np.nan,
        "elev_range_m":         round(elev_range, 1) if not np.isnan(elev_range) else np.nan,
    })

    def _fmt(v):
        return f"{v:10.2f}" if not np.isnan(v) else f"{'NaN':>10}"

    print(f"  {str(hru_id):>4}  {n_cells:>6}  {elev_min:>9.1f}  {elev_max:>9.1f}  "
          f"{_fmt(rl_a)}  {_fmt(rl_b)}  {area_m2:>14,.1f}")

print(f"\n      Valid polygons: {len(records)}")

# ── DEM quality warnings ───────────────────────────────────────────────────────
if warn_lines:
    print(f"\n{'!'*60}")
    print("  DEM QUALITY WARNINGS")
    print(f"{'!'*60}")
    for w in warn_lines:
        print(w)
    print(f"{'!'*60}")
else:
    print("\n  No DEM quality warnings.")


# =============================================================================
# AGGREGATE DUPLICATE HRU IDs (AREA-WEIGHTED) AND SAVE
# =============================================================================
print("\nAggregating duplicate HRU IDs ...")

df_raw = pd.DataFrame(records)
dup    = df_raw[df_raw.duplicated("HRU_ID", keep=False)]["HRU_ID"].nunique()
if dup:
    print(f"  {dup} duplicate HRU ID(s) → area-weighted average")
else:
    print("  No duplicate HRU IDs.")


def _agg(group):
    w    = group["area_m2"]
    wsum = w.sum()

    def wavg(col):
        v = group[col]
        return float(np.average(v, weights=w)) if wsum > 0 else float(v.mean())

    return pd.Series({
        "routing_length_a_m":  round(wavg("routing_length_a_m"), 3),
        "routing_length_b_m":  round(wavg("routing_length_b_m"), 3),
        "total_area_m2":       round(wsum, 2),
        "n_polygons":          len(group),
        "total_cells":         int(group["n_cells"].sum()),
        "total_nan_cells":     int(group["n_nan_cells"].sum()),
        "nan_pct":             round(group["nan_pct"].mean(), 1),
        "elev_min_m":          round(group["elev_min_m"].min(), 1),
        "elev_max_m":          round(group["elev_max_m"].max(), 1),
        "elev_range_m":        round(group["elev_range_m"].max(), 1),
    })


try:
    df_out = (df_raw.groupby("HRU_ID", sort=True)
              .apply(_agg, include_groups=False)
              .reset_index())
except TypeError:
    df_out = (df_raw.groupby("HRU_ID", sort=True)
              .apply(_agg)
              .reset_index())

# ── Option A CSV ──────────────────────────────────────────────────────────────
cols_a = ["HRU_ID", "routing_length_a_m", "total_area_m2", "n_polygons",
          "total_cells", "total_nan_cells", "nan_pct",
          "elev_min_m", "elev_max_m", "elev_range_m"]
df_a = df_out[cols_a].rename(columns={"routing_length_a_m": "routing_length_m"})
df_a.to_csv(OUTPUT_CSV_A, index=False)

# ── Option B CSV ──────────────────────────────────────────────────────────────
cols_b = ["HRU_ID", "routing_length_b_m", "total_area_m2", "n_polygons",
          "total_cells", "total_nan_cells", "nan_pct",
          "elev_min_m", "elev_max_m", "elev_range_m"]
df_b = df_out[cols_b].rename(columns={"routing_length_b_m": "routing_length_m"})
df_b.to_csv(OUTPUT_CSV_B, index=False)

print(f"\n{'='*60}")
print(f"  Option A CSV : {OUTPUT_CSV_A}")
print(f"  Option B CSV : {OUTPUT_CSV_B}")
print(f"  HRUs         : {len(df_out)}")
print(f"{'='*60}")

print("\nFinal comparison (Option A = from highest cell, Option B = max path):")
compare_cols = ["HRU_ID", "routing_length_a_m", "routing_length_b_m",
                "elev_range_m", "total_cells"]
print(df_out[compare_cols].to_string(index=False))
