# =============================================================================
# HRU ROUTING LENGTH CALCULATOR
# Uses DEM-derived D8 flow directions to compute the mean overland flow path
# length (routing length) for each HRU polygon, in metres.
#
# Duplicate HRU IDs (same number in multiple polygons) are resolved by taking
# the area-weighted average of routing lengths across all matching polygons.
#
# Requirements:
#   pip install geopandas rasterio numpy pandas shapely
# =============================================================================


# -----------------------------------------------------------------------------
# SECTION 1 — IMPORTS
# -----------------------------------------------------------------------------
import os
import warnings
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.features import rasterize

warnings.filterwarnings("ignore")


# -----------------------------------------------------------------------------
# SECTION 2 — USER-CONFIGURABLE PATHS AND SETTINGS
# -----------------------------------------------------------------------------

# -- Input files --------------------------------------------------------------
# Update the filenames below to match your actual files.
# Common DEM extensions: .tif, .tiff, .img, .asc
# Common HRU shapefile: .shp

HRU_SHAPEFILE = r"C:\Users\ash_i\Downloads\routing_length\hru.shp"
DEM_RASTER    = r"C:\Users\ash_i\Downloads\routing_length\dem.tif"

# -- Output -------------------------------------------------------------------
# A 'results' folder is created inside the input folder automatically.

OUTPUT_DIR = r"C:\Users\ash_i\Downloads\routing_length\results"
OUTPUT_CSV = os.path.join(OUTPUT_DIR, "hru_routing_lengths.csv")

# -- HRU identifier column ----------------------------------------------------
# Set to the exact column name that holds HRU numbers/IDs, e.g. "HRU_ID".
# Set to None to let the script auto-detect it from the shapefile columns.

HRU_ID_FIELD = None   # e.g. "HRU_ID" or "HRUID" or "Subbasin"


# -----------------------------------------------------------------------------
# SECTION 3 — LOAD DATA
# -----------------------------------------------------------------------------
os.makedirs(OUTPUT_DIR, exist_ok=True)
print(f"Output directory : {OUTPUT_DIR}")

print("\n[1/5] Loading HRU shapefile ...")
hru_gdf = gpd.read_file(HRU_SHAPEFILE)
n_polys = len(hru_gdf)
print(f"      Polygons  : {n_polys}")
print(f"      CRS       : {hru_gdf.crs}")

# Print all columns with types, unique counts, and sample values so the user
# can verify which column holds the HRU numbers.
non_geom_cols = [c for c in hru_gdf.columns if c.lower() != "geometry"]
print(f"\n      {'Column':<20} {'dtype':<12} {'unique':>6}  {'sample values'}")
print(f"      {'-'*20} {'-'*12} {'-'*6}  {'-'*30}")
for col in non_geom_cols:
    uvals  = hru_gdf[col].nunique()
    sample = hru_gdf[col].dropna().unique()[:4].tolist()
    print(f"      {col:<20} {str(hru_gdf[col].dtype):<12} {uvals:>6}  {sample}")

# Auto-detect HRU ID field if not specified.
# Strategy: find the integer-type column whose unique-value count is the
# smallest among those that are (a) numeric and (b) have more than 1 unique
# value and (c) have values that look like small positive integers (HRU IDs).
if HRU_ID_FIELD is None:
    candidates = []
    for col in non_geom_cols:
        ser = hru_gdf[col]
        ucount = ser.nunique()
        if ucount < 2:
            continue
        # Try to coerce to numeric
        num = pd.to_numeric(ser, errors="coerce")
        frac_numeric = num.notna().mean()
        if frac_numeric < 0.9:
            continue
        # Values should look like small positive integers
        vals = num.dropna()
        if vals.min() < 0 or vals.max() > 10_000:
            continue
        # Prefer columns where unique count << n_polys (groups exist)
        candidates.append((col, ucount, frac_numeric))

    if candidates:
        # Pick column with fewest unique values (most "grouped") that is
        # also closest to what we expect (ucount <= n_polys)
        candidates.sort(key=lambda x: x[1])
        HRU_ID_FIELD = candidates[0][0]
    else:
        # Last resort: use first non-geometry column
        HRU_ID_FIELD = non_geom_cols[0]

    print(f"\n      >>> HRU ID field selected : '{HRU_ID_FIELD}'")
    print(f"          Unique HRU IDs found  : {hru_gdf[HRU_ID_FIELD].nunique()}")
    print(f"          Set HRU_ID_FIELD at the top if this looks wrong.")
else:
    print(f"\n      HRU ID field (user-set) : '{HRU_ID_FIELD}'")

print("\n[1/5] Loading DEM ...")
with rasterio.open(DEM_RASTER) as src:
    dem_full   = src.read(1).astype(np.float64)
    transform  = src.transform
    dem_crs    = src.crs
    nodata_val = src.nodata if src.nodata is not None else -9999.0
    n_rows, n_cols = dem_full.shape
    cell_w = abs(transform.a)   # pixel width  in CRS units
    cell_h = abs(transform.e)   # pixel height in CRS units

print(f"      Shape     : {n_rows} x {n_cols}")
print(f"      CRS       : {dem_crs}")
print(f"      Cell size : {cell_w:.6f} x {cell_h:.6f} CRS units")
print(f"      NoData    : {nodata_val}")

dem_full[dem_full == nodata_val] = np.nan


# -----------------------------------------------------------------------------
# SECTION 4 — CRS ALIGNMENT AND CELL SIZE IN METRES
# -----------------------------------------------------------------------------
print("\n[2/5] Aligning coordinate reference systems ...")

if hru_gdf.crs is None:
    raise ValueError(
        "The HRU shapefile has no CRS. Assign a CRS before running this script."
    )

if hru_gdf.crs != dem_crs:
    print(f"      Reprojecting HRU: {hru_gdf.crs}  →  {dem_crs}")
    hru_gdf = hru_gdf.to_crs(dem_crs)

# Determine representative cell size in metres
if dem_crs.is_geographic:
    # Degrees → metres: 1° ≈ 111 320 m, adjusted for latitude
    # union_all() is geopandas ≥0.14; unary_union works on all versions
    try:
        combined = hru_gdf.geometry.union_all()
    except AttributeError:
        combined = hru_gdf.geometry.unary_union
    centroid_lat = float(combined.centroid.y)
    cell_size_m  = cell_w * 111_320.0 * abs(np.cos(np.radians(centroid_lat)))
    print(f"      Geographic CRS  →  estimated cell size = {cell_size_m:.2f} m "
          f"(at lat {centroid_lat:.3f}°)")
else:
    cell_size_m = (cell_w + cell_h) / 2.0
    print(f"      Projected CRS  →  cell size = {cell_size_m:.2f} m")


# -----------------------------------------------------------------------------
# SECTION 5 — D8 FLOW DIRECTION
# -----------------------------------------------------------------------------
print("\n[3/5] Computing D8 flow direction ...")


def _compute_d8_flow_direction(dem_arr: np.ndarray, cell_size: float) -> np.ndarray:
    """
    Vectorised D8 flow direction.
    Each cell is assigned to the neighbour with the steepest downslope gradient.
    Direction codes (ESRI convention):
        64=N  128=NE  1=E  2=SE  4=S  8=SW  16=W  32=NW  0=sink/nodata
    """
    # (row_offset, col_offset, code, distance_multiplier)
    neighbors = [
        (-1,  0,  64, 1.0),
        (-1,  1, 128, 1.41421356),
        ( 0,  1,   1, 1.0),
        ( 1,  1,   2, 1.41421356),
        ( 1,  0,   4, 1.0),
        ( 1, -1,   8, 1.41421356),
        ( 0, -1,  16, 1.0),
        (-1, -1,  32, 1.41421356),
    ]

    nr, nc    = dem_arr.shape
    valid     = ~np.isnan(dem_arr)
    best_slp  = np.full((nr, nc), -np.inf)
    flow_dir  = np.zeros((nr, nc), dtype=np.int16)

    for dr, dc, code, dmult in neighbors:
        r0, r1   = max(0, -dr), nr - max(0,  dr)
        c0, c1   = max(0, -dc), nc - max(0,  dc)
        nr0, nr1 = max(0,  dr), nr - max(0, -dr)
        nc0, nc1 = max(0,  dc), nc - max(0, -dc)

        cur  = dem_arr[r0:r1, c0:c1]
        nbr  = dem_arr[nr0:nr1, nc0:nc1]
        ok   = valid[r0:r1, c0:c1] & valid[nr0:nr1, nc0:nc1]

        slp  = np.where(ok, (cur - nbr) / (dmult * cell_size), -np.inf)
        better = slp > best_slp[r0:r1, c0:c1]

        best_slp[r0:r1, c0:c1]  = np.where(better, slp, best_slp[r0:r1, c0:c1])
        flow_dir[r0:r1, c0:c1]  = np.where(better, code, flow_dir[r0:r1, c0:c1])

    return flow_dir


flow_dir_full = _compute_d8_flow_direction(dem_full, cell_size_m)
print("      Done.")


# -----------------------------------------------------------------------------
# SECTION 6 — ROUTING LENGTH PER HRU POLYGON
# -----------------------------------------------------------------------------

# D8 direction code → (row offset, col offset, distance multiplier)
_D8_OFFSETS = {
     64: (-1,  0, 1.0),
    128: (-1,  1, 1.41421356),
      1: ( 0,  1, 1.0),
      2: ( 1,  1, 1.41421356),
      4: ( 1,  0, 1.0),
      8: ( 1, -1, 1.41421356),
     16: ( 0, -1, 1.0),
     32: (-1, -1, 1.41421356),
}


def _routing_length_for_hru(
    hru_mask: np.ndarray,
    dem_arr:  np.ndarray,
    fdir_arr: np.ndarray,
    cell_size: float,
) -> float:
    """
    Compute the mean D8 flow-path routing length (metres) for one HRU.

    For each DEM cell inside the HRU the D8 path is traced downstream until
    it leaves the HRU boundary.  Each cell's 'routing length' is the
    accumulated travel distance along that path.

    Cells are processed in ascending elevation order so that outlet cells
    (lowest elevation, i.e. first to drain out) are resolved before the
    headwater cells that depend on them.

    Returns
    -------
    float : mean routing length in metres, or NaN if no valid cells exist.
    """
    r_idx, c_idx = np.where(hru_mask)
    if len(r_idx) == 0:
        return np.nan

    elevs = dem_arr[r_idx, c_idx]
    ok    = ~np.isnan(elevs)
    r_idx, c_idx, elevs = r_idx[ok], c_idx[ok], elevs[ok]
    if len(r_idx) == 0:
        return np.nan

    # Clip arrays to HRU bounding box (+ 1-cell pad) for memory efficiency
    pad  = 1
    rmin = max(0, int(r_idx.min()) - pad)
    rmax = min(dem_arr.shape[0], int(r_idx.max()) + pad + 1)
    cmin = max(0, int(c_idx.min()) - pad)
    cmax = min(dem_arr.shape[1], int(c_idx.max()) + pad + 1)

    mask_clip = hru_mask[rmin:rmax, cmin:cmax]
    fdir_clip = fdir_arr[rmin:rmax, cmin:cmax]

    # Re-index to clipped coordinates
    r_local = r_idx - rmin
    c_local = c_idx - cmin

    # Sort ascending elevation (outlet cells first)
    order    = np.argsort(elevs)
    r_sorted = r_local[order]
    c_sorted = c_local[order]

    path_len = np.zeros(fdir_clip.shape, dtype=np.float64)
    max_r, max_c = fdir_clip.shape

    for r, c in zip(r_sorted, c_sorted):
        d = int(fdir_clip[r, c])
        if d not in _D8_OFFSETS:
            path_len[r, c] = 0.0
            continue

        dr, dc, dmult = _D8_OFFSETS[d]
        nr, nc = r + dr, c + dc
        step   = dmult * cell_size

        if 0 <= nr < max_r and 0 <= nc < max_c and mask_clip[nr, nc]:
            # Downstream cell is still inside the HRU
            path_len[r, c] = step + path_len[nr, nc]
        else:
            # Path exits the HRU (or hits DEM edge / sink)
            path_len[r, c] = step

    cell_lengths = path_len[r_local, c_local]
    return float(np.mean(cell_lengths))


# ---- Process every polygon --------------------------------------------------
print(f"\n[4/5] Computing routing lengths for {len(hru_gdf)} HRU polygons ...")

records = []

for i, (feat_idx, row) in enumerate(hru_gdf.iterrows()):
    hru_id = row[HRU_ID_FIELD]
    geom   = row.geometry

    if geom is None or geom.is_empty:
        print(f"  [{i+1:>4d}/{len(hru_gdf)}] HRU {hru_id}: empty geometry — skipped.")
        continue

    # --- Polygon area in m² ---
    if dem_crs.is_geographic:
        try:
            utm_crs = gpd.GeoSeries([geom], crs=hru_gdf.crs).estimate_utm_crs()
            area_m2 = float(
                gpd.GeoSeries([geom], crs=hru_gdf.crs)
                   .to_crs(utm_crs)
                   .area.iloc[0]
            )
        except Exception:
            area_m2 = None   # will be estimated from cell count below
    else:
        area_m2 = float(geom.area)

    # --- Rasterize polygon onto DEM grid ---
    hru_mask = rasterize(
        [(geom, 1)],
        out_shape=(n_rows, n_cols),
        transform=transform,
        fill=0,
        dtype=np.uint8,
    ).astype(bool)

    n_cells = int(hru_mask.sum())

    if n_cells == 0:
        print(f"  [{i+1:>4d}/{len(hru_gdf)}] HRU {hru_id}: no overlapping DEM cells — skipped.")
        continue

    if area_m2 is None:
        area_m2 = n_cells * (cell_size_m ** 2)

    # --- Routing length ---
    rl = _routing_length_for_hru(hru_mask, dem_full, flow_dir_full, cell_size_m)

    records.append(
        {
            "HRU_ID":           hru_id,
            "routing_length_m": round(rl, 3),
            "area_m2":          round(area_m2, 2),
            "n_cells":          n_cells,
        }
    )

    if (i + 1) % 20 == 0 or (i + 1) == len(hru_gdf):
        print(
            f"  [{i+1:>4d}/{len(hru_gdf)}] HRU {hru_id:>8} | "
            f"routing_length = {rl:>9.2f} m | area = {area_m2:>14,.1f} m²"
        )

print(f"\n      Valid polygons processed : {len(records)}")


# -----------------------------------------------------------------------------
# SECTION 7 — AGGREGATE DUPLICATE HRU IDs (AREA-WEIGHTED AVERAGE)
# -----------------------------------------------------------------------------
print("\n[5/5] Aggregating duplicate HRU IDs ...")

df_raw = pd.DataFrame(records)

dup_ids = df_raw[df_raw.duplicated("HRU_ID", keep=False)]["HRU_ID"].nunique()
if dup_ids:
    print(f"      Found {dup_ids} HRU ID(s) present in more than one polygon.")
    print("      Applying area-weighted average for routing length.")
else:
    print("      No duplicate HRU IDs — no aggregation needed.")


def _weighted_mean_group(group: pd.DataFrame) -> pd.Series:
    w = group["area_m2"]
    v = group["routing_length_m"]
    wav = float(np.average(v, weights=w)) if w.sum() > 0 else float(v.mean())
    return pd.Series(
        {
            "routing_length_m": round(wav, 3),
            "total_area_m2":    round(w.sum(), 2),
            "n_polygons":       len(group),
            "total_cells":      int(group["n_cells"].sum()),
        }
    )


try:
    df_out = (df_raw.groupby("HRU_ID", sort=False)
              .apply(_weighted_mean_group, include_groups=False)
              .reset_index())
except TypeError:
    # pandas < 2.2 does not have include_groups
    df_out = (df_raw.groupby("HRU_ID", sort=False)
              .apply(_weighted_mean_group)
              .reset_index())


# -----------------------------------------------------------------------------
# SECTION 8 — SAVE OUTPUT
# -----------------------------------------------------------------------------
df_out.to_csv(OUTPUT_CSV, index=False)

print(f"\n{'='*60}")
print(f"  Output saved  : {OUTPUT_CSV}")
print(f"  Total HRUs    : {len(df_out)}")
print(f"{'='*60}")
print("\nSample results:")
print(df_out.to_string(index=False))
