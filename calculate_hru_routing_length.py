# =============================================================================
# HRU ROUTING LENGTH — LONGEST FLOW PATH (DIVIDE → OUTLET)
# =============================================================================
#
# CONCEPT
# -------
# The routing length of an HRU is the LENGTH OF THE LONGEST D8 FLOW PATH
# within that HRU — from the farthest upstream cell (watershed divide) to the
# main outlet of the HRU.
#
# HOW THE DEM IS USED
# -------------------
#   Step 1 — Overlay  : The HRU shapefile is draped on top of the DEM.
#                        Only DEM cells that fall inside the HRU are used.
#   Step 2 — D8 dir   : The DEM elevation surface determines which direction
#                        water flows from every cell (steepest downslope
#                        neighbour among 8 surrounding cells).
#   Step 3 — Flow acc : Count how many upstream cells drain through each cell.
#                        High-accumulation cells = the main channel / valley.
#                        Zero-accumulation cells = ridges / divides.
#   Step 4 — Outlet   : The main outlet of the HRU = the boundary cell
#                        (D8 exits the HRU polygon) with the HIGHEST flow
#                        accumulation — where most water leaves the HRU.
#   Step 5 — Routing  : For every cell whose D8 path reaches the main outlet,
#                        measure the total path length to that outlet.
#                        Routing length = MAXIMUM of those lengths.
#                        = distance from the farthest divide cell to the outlet.
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
OUTPUT_CSV    = os.path.join(OUTPUT_DIR, "hru_routing_lengths.csv")

# Exact column name holding HRU IDs (set to None to auto-detect)
HRU_ID_FIELD  = "h_r_u"


# =============================================================================
# STEP 1 — LOAD DATA
# =============================================================================
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("[1/6] Loading HRU shapefile ...")
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

print("\n[1/6] Loading DEM ...")
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
print("\n[2/6] Aligning CRS ...")

if hru_gdf.crs is None:
    raise ValueError("HRU shapefile has no CRS.")

if hru_gdf.crs != dem_crs:
    print(f"      Reprojecting HRU: {hru_gdf.crs} → {dem_crs}")
    hru_gdf = hru_gdf.to_crs(dem_crs)

# Geographic CRS: longitude degrees are shorter than latitude degrees —
# use separate x and y cell sizes so diagonal distances are correct.
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
print("\n[3/6] Computing D8 flow direction ...")


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


# Tiny random perturbation breaks elevation ties on flat areas that are
# common in pit-filled DEMs; ensures every valid cell gets a D8 direction.
rng        = np.random.default_rng(42)
dem_for_d8 = dem_full.copy()
valid_mask = ~np.isnan(dem_for_d8)
dem_for_d8[valid_mask] += rng.uniform(0, 1e-4, int(valid_mask.sum()))

fdir_full = _compute_d8(dem_for_d8, cell_x_m, cell_y_m)
n_sinks   = int(((fdir_full == 0) & valid_mask).sum())
print(f"      Done.  Remaining sink cells: {n_sinks:,}")


# =============================================================================
# STEP 4 — FLOW ACCUMULATION
# =============================================================================
print("\n[4/6] Computing flow accumulation ...")


def _flow_accumulation(fdir, valid):
    """
    D8 flow accumulation via topological sort (Kahn's algorithm).
    Returns the number of upstream cells that drain through each cell
    (including the cell itself → minimum value = 1 for valid cells).
    """
    nr, nc = fdir.shape

    # Count upstream contributors for each cell (in-degree in flow graph)
    in_count = np.zeros((nr, nc), dtype=np.int32)
    for code, (dr, dc, _) in D8.items():
        r0, r1   = max(0, -dr), nr - max(0,  dr)
        c0, c1   = max(0, -dc), nc - max(0,  dc)
        nr0, nr1 = max(0,  dr), nr - max(0, -dr)
        nc0, nc1 = max(0,  dc), nc - max(0, -dc)
        drains = (fdir[r0:r1, c0:c1] == code) & valid[r0:r1, c0:c1]
        in_count[nr0:nr1, nc0:nc1] += drains.astype(np.int32)

    facc      = np.zeros((nr, nc), dtype=np.float64)
    facc[valid] = 1.0
    remaining = in_count.copy()

    # Seed: cells with no upstream neighbours
    queue = deque(zip(*np.where(valid & (remaining == 0))))

    while queue:
        r, c = queue.popleft()
        d = int(fdir[r, c])
        if d not in D8:
            continue
        dr, dc, _ = D8[d]
        nr2, nc2  = r + dr, c + dc
        if 0 <= nr2 < nr and 0 <= nc2 < nc and valid[nr2, nc2]:
            facc[nr2, nc2] += facc[r, c]
            remaining[nr2, nc2] -= 1
            if remaining[nr2, nc2] == 0:
                queue.append((nr2, nc2))

    return facc


facc_full = _flow_accumulation(fdir_full, valid_mask)
print(f"      Done.  Max accumulation: {facc_full.max():,.0f} cells")


# =============================================================================
# STEP 5 — ROUTING LENGTH PER HRU
# =============================================================================
print(f"\n[5/6] Computing routing lengths for {n_polys} HRUs ...")


def _local_flow_accumulation(fdir, mask):
    """
    Flow accumulation computed ONLY within the HRU cells.

    Every HRU cell starts with value 1. Flow is only passed to neighbours
    that are also inside the HRU. Cells whose D8 exits the HRU keep their
    accumulated value but do not pass it further.

    Result: high value = near the HRU outlet (many cells drain through it)
            value = 1  = at the divide (no upstream HRU cells feed it)

    WHY LOCAL, NOT GLOBAL:
    A large river may enter the HRU from outside with enormous global
    accumulation. Using global accumulation to order cells causes those
    river-entry cells to be processed first, before their downstream
    neighbours within the HRU are resolved — they get NaN and the path
    is broken. Local accumulation gives the correct topological order.
    """
    MR, MC   = fdir.shape
    in_count = np.zeros((MR, MC), dtype=np.int32)

    for code, (dr, dc, _) in D8.items():
        r0,r1   = max(0,-dr), MR-max(0,dr)
        c0,c1   = max(0,-dc), MC-max(0,dc)
        nr0,nr1 = max(0,dr),  MR-max(0,-dr)
        nc0,nc1 = max(0,dc),  MC-max(0,-dc)
        # Only count flow between two cells that are BOTH inside the HRU
        drains = ((fdir[r0:r1,c0:c1] == code)
                  & mask[r0:r1,c0:c1]
                  & mask[nr0:nr1,nc0:nc1])
        in_count[nr0:nr1, nc0:nc1] += drains.astype(np.int32)

    facc_local = np.zeros((MR, MC), dtype=np.float64)
    facc_local[mask] = 1.0
    rem = in_count.copy()

    # Seed: HRU cells that receive no flow from other HRU cells (divides)
    q = deque(zip(*np.where(mask & (rem == 0))))
    while q:
        r, c = q.popleft()
        d = int(fdir[r, c])
        if d not in D8:
            continue
        dr, dc, _ = D8[d]
        r2, c2 = r + dr, c + dc
        if 0 <= r2 < MR and 0 <= c2 < MC and mask[r2, c2]:
            facc_local[r2, c2] += facc_local[r, c]
            rem[r2, c2] -= 1
            if rem[r2, c2] == 0:
                q.append((r2, c2))

    return facc_local


def _routing_length(hru_mask, fdir_arr):
    """
    Longest D8 flow path (metres) within the HRU =
    distance from the farthest upstream cell (true divide) to the outlet.

    1. OVERLAY      : Extract cells inside the HRU polygon.
    2. LOCAL FACC   : Compute flow accumulation using only intra-HRU flow.
    3. OUTLET       : Boundary cell with highest LOCAL accumulation
                      (most HRU cells drain through it).
    4. ORDER        : Process cells descending local accumulation
                      → outlet resolved first, divide cells resolved last.
                      This guarantees every cell's downstream neighbour is
                      already computed before the cell itself is processed.
    5. PATH LENGTHS : path_len[cell] = step + path_len[downstream neighbour]
    6. RESULT       : max(path_len) = full divide-to-outlet distance.
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

    # ── LOCAL flow accumulation ───────────────────────────────────────────
    facc_local = _local_flow_accumulation(fdir, mask)

    # ── Main outlet: boundary cell with highest LOCAL accumulation ────────
    out_r, out_c, out_dist = None, None, None
    max_local_acc = -1.0
    for r, c in zip(rl, cl):
        d = int(fdir[r, c])
        if d not in D8:
            continue
        dr, dc, dist = D8[d]
        r2, c2 = r + dr, c + dc
        exits = (r2 < 0 or r2 >= MR or c2 < 0 or c2 >= MC
                 or not mask[r2, c2])
        if exits and facc_local[r, c] > max_local_acc:
            max_local_acc    = facc_local[r, c]
            out_r, out_c     = r, c
            out_dist         = dist

    if out_r is None:
        return np.nan

    # ── Path lengths (outlet first → divide last) ─────────────────────────
    path_len = np.full((MR, MC), np.nan)
    path_len[out_r, out_c] = out_dist

    order = np.argsort(-facc_local[rl, cl])   # descending LOCAL accumulation
    for r, c in zip(rl[order], cl[order]):
        if not np.isnan(path_len[r, c]):
            continue
        d = int(fdir[r, c])
        if d not in D8:
            continue
        dr, dc, dist = D8[d]
        r2, c2 = r + dr, c + dc
        exits = (r2 < 0 or r2 >= MR or c2 < 0 or c2 >= MC
                 or not mask[r2, c2])
        if not exits and not np.isnan(path_len[r2, c2]):
            path_len[r, c] = dist + path_len[r2, c2]

    # ── Routing length = longest path to the main outlet ─────────────────
    vals       = path_len[rl, cl]
    valid_vals = vals[~np.isnan(vals)]
    if len(valid_vals) > 0:
        return float(np.nanmax(valid_vals))

    # Fallback: max path to ANY boundary exit (e.g. HRU with multiple exits)
    for r, c in zip(rl, cl):
        d = int(fdir[r, c])
        if d not in D8:
            path_len[r, c] = 0.0
            continue
        dr, dc, dist = D8[d]
        r2, c2 = r + dr, c + dc
        exits = (r2 < 0 or r2 >= MR or c2 < 0 or c2 >= MC
                 or not mask[r2, c2])
        if exits:
            path_len[r, c] = dist

    for r, c in zip(rl[order], cl[order]):
        if not np.isnan(path_len[r, c]):
            continue
        d = int(fdir[r, c])
        if d not in D8:
            continue
        dr, dc, dist = D8[d]
        r2, c2 = r + dr, c + dc
        if (0 <= r2 < MR and 0 <= c2 < MC
                and mask[r2, c2]
                and not np.isnan(path_len[r2, c2])):
            path_len[r, c] = dist + path_len[r2, c2]

    fallback = path_len[rl, cl]
    fallback = fallback[~np.isnan(fallback)]
    return float(np.nanmax(fallback)) if len(fallback) > 0 else np.nan


# ── Process every HRU polygon ─────────────────────────────────────────────────
records    = []
warn_lines = []   # DEM quality warnings collected here

print(f"  {'HRU':>4}  {'cells':>6}  {'NaN':>6}  {'NaN%':>5}  "
      f"{'elev_min':>9}  {'elev_max':>9}  {'routing_m':>10}  {'area_m2':>14}")
print(f"  {'-'*4}  {'-'*6}  {'-'*6}  {'-'*5}  "
      f"{'-'*9}  {'-'*9}  {'-'*10}  {'-'*14}")

for i, (_, row) in enumerate(hru_gdf.iterrows()):
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

    # Rasterize HRU polygon onto the DEM grid (overlay HRU on DEM)
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

    # ── DEM quality check within this HRU ─────────────────────────────────
    elev_in_hru  = dem_full[hru_mask]
    n_nan        = int(np.isnan(elev_in_hru).sum())
    nan_pct      = 100.0 * n_nan / n_cells
    valid_elevs  = elev_in_hru[~np.isnan(elev_in_hru)]
    elev_min     = float(valid_elevs.min()) if len(valid_elevs) > 0 else np.nan
    elev_max     = float(valid_elevs.max()) if len(valid_elevs) > 0 else np.nan
    elev_range   = elev_max - elev_min if not np.isnan(elev_min) else np.nan
    n_valid      = n_cells - n_nan

    # Flag suspicious HRUs
    if nan_pct > 20:
        warn_lines.append(
            f"  HRU {hru_id:>3}: {nan_pct:.0f}% of cells are NaN — "
            f"DEM has nodata gaps inside this HRU  *** CHECK DEM ***"
        )
    if n_valid > 4 and elev_range < cell_y_m:
        warn_lines.append(
            f"  HRU {hru_id:>3}: elevation range only {elev_range:.1f} m — "
            f"DEM is nearly flat here (pit-fill artifact?)  *** CHECK DEM ***"
        )

    rl = _routing_length(hru_mask, fdir_full)

    records.append({
        "HRU_ID":           hru_id,
        "routing_length_m": round(rl, 3) if not np.isnan(rl) else np.nan,
        "area_m2":          round(area_m2, 2),
        "n_cells":          n_cells,
        "n_nan_cells":      n_nan,
        "nan_pct":          round(nan_pct, 1),
        "elev_min_m":       round(elev_min, 1) if not np.isnan(elev_min) else np.nan,
        "elev_max_m":       round(elev_max, 1) if not np.isnan(elev_max) else np.nan,
        "elev_range_m":     round(elev_range, 1) if not np.isnan(elev_range) else np.nan,
    })

    print(f"  {str(hru_id):>4}  {n_cells:>6}  {n_nan:>6}  {nan_pct:>4.0f}%  "
          f"{elev_min:>9.1f}  {elev_max:>9.1f}  {rl:>10.2f}  {area_m2:>14,.1f}")

print(f"\n      Valid polygons: {len(records)}")

# ── Print DEM quality warnings ────────────────────────────────────────────────
if warn_lines:
    print(f"\n{'!'*60}")
    print("  DEM QUALITY WARNINGS")
    print(f"{'!'*60}")
    for w in warn_lines:
        print(w)
    print(f"{'!'*60}")
    print("\n  These HRUs may produce unreliable routing lengths.")
    print("  Recommended checks:")
    print("  1. Open the DEM and HRU shapefile together in QGIS or ArcGIS")
    print("  2. Confirm the HRU polygon overlaps valid DEM data visually")
    print("  3. Check for nodata gaps or flat areas inside the flagged HRUs")
    print("  4. If the DEM has large flat areas, consider using the original")
    print("     unfilled DEM or a higher-resolution source (SRTM/Copernicus 30m)")
else:
    print("\n  No DEM quality warnings — all HRUs have valid elevation coverage.")


# =============================================================================
# STEP 6 — AGGREGATE DUPLICATE HRU IDs (AREA-WEIGHTED)
# =============================================================================
print("\n[6/6] Aggregating duplicate HRU IDs ...")

df_raw = pd.DataFrame(records)
dup    = df_raw[df_raw.duplicated("HRU_ID", keep=False)]["HRU_ID"].nunique()
if dup:
    print(f"      {dup} duplicate HRU ID(s) → area-weighted average")
else:
    print("      No duplicate HRU IDs.")


def _agg(group):
    w   = group["area_m2"]
    v   = group["routing_length_m"]
    wav = float(np.average(v, weights=w)) if w.sum() > 0 else float(v.mean())
    return pd.Series({
        "routing_length_m": round(wav, 3),
        "total_area_m2":    round(w.sum(), 2),
        "n_polygons":       len(group),
        "total_cells":      int(group["n_cells"].sum()),
        "total_nan_cells":  int(group["n_nan_cells"].sum()),
        "nan_pct":          round(group["nan_pct"].mean(), 1),
        "elev_min_m":       round(group["elev_min_m"].min(), 1),
        "elev_max_m":       round(group["elev_max_m"].max(), 1),
        "elev_range_m":     round(group["elev_range_m"].max(), 1),
    })


try:
    df_out = (df_raw.groupby("HRU_ID", sort=True)
              .apply(_agg, include_groups=False)
              .reset_index())
except TypeError:
    df_out = (df_raw.groupby("HRU_ID", sort=True)
              .apply(_agg)
              .reset_index())

df_out.to_csv(OUTPUT_CSV, index=False)

print(f"\n{'='*60}")
print(f"  Output : {OUTPUT_CSV}")
print(f"  HRUs   : {len(df_out)}")
print(f"{'='*60}")
print("\nFinal results:")
print(df_out.to_string(index=False))
