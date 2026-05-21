# =============================================================================
# DEM DIAGNOSTIC — Check DEM quality inside every HRU
# =============================================================================
#
# WHAT THIS SCRIPT CHECKS
# -----------------------
#  1. Overview plot  : Full DEM hillshade with all HRU boundaries overlaid.
#                      Red overlay = nodata cells in the DEM.
#                      Lets you see at a glance if any HRU falls outside or
#                      partially outside the DEM extent.
#
#  2. Per-HRU stats  : For every HRU, prints and saves:
#                        - Total cells inside the polygon
#                        - NaN / nodata cell count and percentage
#                        - Elevation min, max, range
#                        - FLAG: "NODATA" if NaN% > 20
#                        - FLAG: "FLAT"   if elevation range < one cell height
#                                         (common pit-fill artifact)
#
#  3. Detail plots for the HRU you specify (CHECK_HRU_ID):
#       Panel A — DEM elevation with NaN cells shown in red
#       Panel B — Flow accumulation (log scale); high = channel, low = divide
#       Panel C — D8 flow direction arrows
#       Panel D — Routing path (divide→outlet) colour-coded by path length
#
#  4. Elevation profile along the routing path of that HRU.
#
# OUTPUTS (all saved to OUTPUT_DIR)
# ---------
#  diagnostic_overview.png
#  diagnostic_hruXX_detail.png
#  diagnostic_hruXX_profile.png
#  dem_diagnostic_stats.csv
#
# Requirements:
#   pip install geopandas rasterio numpy pandas matplotlib shapely
# =============================================================================

import os
import warnings
from collections import deque

import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.features import rasterize
import matplotlib
matplotlib.use("Agg")          # non-interactive backend — works without a display
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import LightSource

warnings.filterwarnings("ignore")


# =============================================================================
# USER SETTINGS  — change these to match your files
# =============================================================================
HRU_SHAPEFILE = r"C:\Users\ash_i\Downloads\routing_length\hru\NO_HRU_UTM45_merge.shp"
DEM_RASTER    = r"C:\Users\ash_i\Downloads\routing_length\phorse_dem\demphortfilll.tif"
OUTPUT_DIR    = r"C:\Users\ash_i\Downloads\routing_length\results"

HRU_ID_FIELD  = "h_r_u"   # column in shapefile that holds HRU number
CHECK_HRU_ID  = 35        # which HRU to examine in detail


# =============================================================================
# LOAD DATA
# =============================================================================
os.makedirs(OUTPUT_DIR, exist_ok=True)
print("=" * 60)
print("  DEM DIAGNOSTIC")
print("=" * 60)

print("\n[1/5] Loading data ...")
hru_gdf = gpd.read_file(HRU_SHAPEFILE)
print(f"      HRU shapefile : {len(hru_gdf)} polygons   CRS: {hru_gdf.crs}")

with rasterio.open(DEM_RASTER) as src:
    dem        = src.read(1).astype(np.float64)
    tf         = src.transform
    dem_crs    = src.crs
    nodata_val = src.nodata if src.nodata is not None else -9999.0
    n_rows, n_cols = dem.shape
    cell_w     = abs(tf.a)
    cell_h     = abs(tf.e)

dem[dem == nodata_val] = np.nan
print(f"      DEM           : {n_rows}×{n_cols}  CRS: {dem_crs}")
print(f"      DEM nodata    : {nodata_val}  "
      f"(NaN cells in DEM: {int(np.isnan(dem).sum()):,})")

# Align CRS
if hru_gdf.crs != dem_crs:
    print(f"      Reprojecting HRU to match DEM CRS ...")
    hru_gdf = hru_gdf.to_crs(dem_crs)

# Cell sizes in metres
if dem_crs.is_geographic:
    try:
        union = hru_gdf.geometry.union_all()
    except AttributeError:
        union = hru_gdf.geometry.unary_union
    lat      = float(union.centroid.y)
    cell_x_m = cell_w * 111_320.0 * abs(np.cos(np.radians(lat)))
    cell_y_m = cell_h * 111_320.0
    print(f"      Cell size     : {cell_x_m:.2f} m (x)  ×  {cell_y_m:.2f} m (y)")
else:
    cell_x_m = float(cell_w)
    cell_y_m = float(cell_h)
    print(f"      Cell size     : {cell_x_m:.2f} m (x)  ×  {cell_y_m:.2f} m (y)")

diag_m = float(np.sqrt(cell_x_m**2 + cell_y_m**2))

# D8 code → (row_offset, col_offset, step_distance_m)
D8 = {
     64: (-1,  0, cell_y_m),
    128: (-1,  1, diag_m),
      1: ( 0,  1, cell_x_m),
      2: ( 1,  1, diag_m),
      4: ( 1,  0, cell_y_m),
      8: ( 1, -1, diag_m),
     16: ( 0, -1, cell_x_m),
     32: (-1, -1, diag_m),
}


# =============================================================================
# D8 FLOW DIRECTION + FLOW ACCUMULATION  (needed for detail plots)
# =============================================================================
print("\n[2/5] Computing D8 flow direction and flow accumulation ...")


def _d8(dem_arr, cx, cy):
    diag = np.sqrt(cx**2 + cy**2)
    nbrs = [(-1,0,64,cy),(-1,1,128,diag),(0,1,1,cx),(1,1,2,diag),
            (1,0,4,cy),(1,-1,8,diag),(0,-1,16,cx),(-1,-1,32,diag)]
    nr, nc   = dem_arr.shape
    valid    = ~np.isnan(dem_arr)
    best_slp = np.full((nr, nc), -np.inf)
    fdir     = np.zeros((nr, nc), dtype=np.int16)
    for dr, dc, code, dist in nbrs:
        r0,r1   = max(0,-dr), nr-max(0,dr)
        c0,c1   = max(0,-dc), nc-max(0,dc)
        nr0,nr1 = max(0,dr),  nr-max(0,-dr)
        nc0,nc1 = max(0,dc),  nc-max(0,-dc)
        cur  = dem_arr[r0:r1, c0:c1]
        nbr  = dem_arr[nr0:nr1, nc0:nc1]
        ok   = valid[r0:r1, c0:c1] & valid[nr0:nr1, nc0:nc1]
        slp  = np.where(ok, (cur-nbr)/dist, -np.inf)
        b    = slp > best_slp[r0:r1, c0:c1]
        best_slp[r0:r1, c0:c1] = np.where(b, slp,  best_slp[r0:r1, c0:c1])
        fdir[r0:r1, c0:c1]     = np.where(b, code, fdir[r0:r1, c0:c1])
    return fdir


def _facc(fdir, valid):
    nr, nc   = fdir.shape
    in_count = np.zeros((nr, nc), dtype=np.int32)
    for code, (dr, dc, _) in D8.items():
        r0,r1   = max(0,-dr), nr-max(0,dr)
        c0,c1   = max(0,-dc), nc-max(0,dc)
        nr0,nr1 = max(0,dr),  nr-max(0,-dr)
        nc0,nc1 = max(0,dc),  nc-max(0,-dc)
        d = (fdir[r0:r1,c0:c1] == code) & valid[r0:r1,c0:c1]
        in_count[nr0:nr1, nc0:nc1] += d.astype(np.int32)
    facc      = np.zeros((nr, nc), dtype=np.float64)
    facc[valid] = 1.0
    rem       = in_count.copy()
    q         = deque(zip(*np.where(valid & (rem == 0))))
    while q:
        r, c = q.popleft()
        d = int(fdir[r, c])
        if d not in D8:
            continue
        dr, dc, _ = D8[d]
        r2, c2    = r + dr, c + dc
        if 0 <= r2 < nr and 0 <= c2 < nc and valid[r2, c2]:
            facc[r2, c2]  += facc[r, c]
            rem[r2, c2]   -= 1
            if rem[r2, c2] == 0:
                q.append((r2, c2))
    return facc


rng        = np.random.default_rng(42)
dem_p      = dem.copy()
vm         = ~np.isnan(dem_p)
dem_p[vm] += rng.uniform(0, 1e-4, int(vm.sum()))

fdir_full  = _d8(dem_p, cell_x_m, cell_y_m)
facc_full  = _facc(fdir_full, vm)
print(f"      Done.  Max flow accumulation: {facc_full.max():,.0f} cells")


# =============================================================================
# PER-HRU STATISTICS
# =============================================================================
print("\n[3/5] Computing per-HRU DEM statistics ...")

rows = []
for _, hru_row in hru_gdf.iterrows():
    hid  = hru_row[HRU_ID_FIELD]
    geom = hru_row.geometry
    if geom is None or geom.is_empty:
        rows.append({"HRU_ID": hid, "n_cells": 0, "n_nan": 0,
                     "nan_pct": 100, "elev_min": np.nan,
                     "elev_max": np.nan, "elev_range": np.nan,
                     "flag": "EMPTY GEOMETRY"})
        continue

    mask = rasterize(
        [(geom, 1)], out_shape=(n_rows, n_cols),
        transform=tf, fill=0, dtype=np.uint8,
    ).astype(bool)

    n_cells = int(mask.sum())
    if n_cells == 0:
        rows.append({"HRU_ID": hid, "n_cells": 0, "n_nan": 0,
                     "nan_pct": 100, "elev_min": np.nan,
                     "elev_max": np.nan, "elev_range": np.nan,
                     "flag": "OUTSIDE DEM EXTENT"})
        continue

    elev    = dem[mask]
    n_nan   = int(np.isnan(elev).sum())
    nan_pct = 100.0 * n_nan / n_cells
    valid_e = elev[~np.isnan(elev)]
    emin    = float(valid_e.min())    if len(valid_e) else np.nan
    emax    = float(valid_e.max())    if len(valid_e) else np.nan
    erange  = emax - emin             if not np.isnan(emin) else np.nan

    flags = []
    if nan_pct > 20:
        flags.append("NODATA")
    if (not np.isnan(erange)) and erange < cell_y_m and n_cells > 4:
        flags.append("FLAT")

    rows.append({
        "HRU_ID":    hid,
        "n_cells":   n_cells,
        "n_nan":     n_nan,
        "nan_pct":   round(nan_pct, 1),
        "elev_min":  round(emin, 1)    if not np.isnan(emin)    else np.nan,
        "elev_max":  round(emax, 1)    if not np.isnan(emax)    else np.nan,
        "elev_range": round(erange, 1) if not np.isnan(erange)  else np.nan,
        "flag":      ", ".join(flags) if flags else "OK",
    })

df = pd.DataFrame(rows)
df.to_csv(os.path.join(OUTPUT_DIR, "dem_diagnostic_stats.csv"), index=False)

# Print table
print(f"\n  {'HRU':>4}  {'cells':>6}  {'NaN':>5}  {'NaN%':>5}  "
      f"{'elev_min':>9}  {'elev_max':>9}  {'range_m':>8}  flag")
print(f"  {'-'*4}  {'-'*6}  {'-'*5}  {'-'*5}  "
      f"{'-'*9}  {'-'*9}  {'-'*8}  {'-'*20}")
for _, s in df.iterrows():
    marker = " <<<" if s["flag"] != "OK" else ""
    print(f"  {int(s['HRU_ID']):>4}  {int(s['n_cells']):>6}  "
          f"{int(s['n_nan']):>5}  {s['nan_pct']:>4.0f}%  "
          f"{s['elev_min']:>9.1f}  {s['elev_max']:>9.1f}  "
          f"{s['elev_range']:>8.1f}  {s['flag']}{marker}")

n_issues = int((df["flag"] != "OK").sum())
print(f"\n  HRUs with issues : {n_issues} / {len(df)}")
print(f"  Stats saved      : {os.path.join(OUTPUT_DIR, 'dem_diagnostic_stats.csv')}")


# =============================================================================
# PLOT 1 — OVERVIEW: full DEM + all HRU boundaries
# =============================================================================
print("\n[4/5] Generating plots ...")

fig, ax = plt.subplots(figsize=(13, 11))

# DEM hillshade + colour
dem_disp = dem.copy()
dem_disp[np.isnan(dem_disp)] = float(np.nanmin(dem))
ls = LightSource(azdeg=315, altdeg=45)
hs = ls.hillshade(dem_disp, vert_exag=2)
# Geographic extent of the DEM in world coordinates
left   = tf.c
right  = tf.c + n_cols * tf.a
bottom = tf.f + n_rows * tf.e
top    = tf.f
ext = [left, right, bottom, top]

ax.imshow(hs, cmap="gray", extent=ext, origin="upper", alpha=0.5)
im = ax.imshow(
    np.where(np.isnan(dem), np.nan, dem),
    cmap="terrain", extent=ext, origin="upper", alpha=0.55,
)
plt.colorbar(im, ax=ax, label="Elevation (m)", fraction=0.03, pad=0.02)

# Red overlay where DEM is nodata
nan_img = np.where(np.isnan(dem), 1.0, np.nan)
ax.imshow(nan_img, cmap="Reds", extent=ext, origin="upper",
          alpha=0.6, vmin=0, vmax=1)

# All HRU boundaries
hru_gdf.boundary.plot(ax=ax, color="blue", linewidth=0.6, alpha=0.8)

# Label each HRU with its ID
for _, hru_row in hru_gdf.iterrows():
    cx = hru_row.geometry.centroid.x
    cy = hru_row.geometry.centroid.y
    ax.text(cx, cy, str(int(hru_row[HRU_ID_FIELD])),
            fontsize=5, ha="center", va="center", color="white",
            fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.1", facecolor="navy", alpha=0.6))

# Highlight the HRU being inspected
hru_sel = hru_gdf[hru_gdf[HRU_ID_FIELD] == CHECK_HRU_ID]
if not hru_sel.empty:
    hru_sel.plot(ax=ax, color="yellow", alpha=0.35)
    hru_sel.boundary.plot(ax=ax, color="red", linewidth=2.5)

# Flag HRUs with issues in orange
flagged = hru_gdf[hru_gdf[HRU_ID_FIELD].isin(
    df.loc[df["flag"] != "OK", "HRU_ID"]
)]
if not flagged.empty:
    flagged.boundary.plot(ax=ax, color="orange", linewidth=1.8,
                          linestyle="--", label="HRU with DEM issue")

ax.set_title(
    f"DEM Overview — All HRU Boundaries\n"
    f"DEM: {n_rows}×{n_cols}  cell={cell_x_m:.1f}×{cell_y_m:.1f} m  "
    f"CRS: {dem_crs}\n"
    f"Red shading = DEM nodata  |  Yellow = HRU {CHECK_HRU_ID} (inspected)",
    fontsize=10,
)
xlabel = "Longitude" if dem_crs.is_geographic else "Easting (m)"
ylabel = "Latitude"  if dem_crs.is_geographic else "Northing (m)"
ax.set_xlabel(xlabel)
ax.set_ylabel(ylabel)

legend_handles = [
    mpatches.Patch(color="blue",   alpha=0.7, label="HRU boundary"),
    mpatches.Patch(color="yellow", alpha=0.5, label=f"HRU {CHECK_HRU_ID} (detail)"),
    mpatches.Patch(color="red",    alpha=0.6, label="DEM nodata"),
    mpatches.Patch(color="orange", alpha=0.7, label="HRU with DEM issue"),
]
ax.legend(handles=legend_handles, loc="upper right", fontsize=8)

plt.tight_layout()
out1 = os.path.join(OUTPUT_DIR, "diagnostic_overview.png")
plt.savefig(out1, dpi=150, bbox_inches="tight")
plt.close()
print(f"  Saved: {out1}")


# =============================================================================
# PLOT 2 — DETAIL: 4-panel view of CHECK_HRU_ID
# =============================================================================
hru_sel = hru_gdf[hru_gdf[HRU_ID_FIELD] == CHECK_HRU_ID]
if hru_sel.empty:
    print(f"  HRU {CHECK_HRU_ID} not found — skipping detail plots")
else:
    geom = hru_sel.geometry.iloc[0]
    mask_full = rasterize(
        [(geom, 1)], out_shape=(n_rows, n_cols),
        transform=tf, fill=0, dtype=np.uint8,
    ).astype(bool)

    r_idx, c_idx = np.where(mask_full)
    if len(r_idx) == 0:
        print(f"  HRU {CHECK_HRU_ID} has no DEM cells — skipping detail plots")
    else:
        # Clip arrays to HRU bounding box with padding
        pad  = 4
        rmin = max(0, r_idx.min() - pad)
        rmax = min(n_rows, r_idx.max() + pad + 1)
        cmin = max(0, c_idx.min() - pad)
        cmax = min(n_cols, c_idx.max() + pad + 1)

        dem_c  = dem[rmin:rmax, cmin:cmax]
        fdir_c = fdir_full[rmin:rmax, cmin:cmax]
        facc_c = facc_full[rmin:rmax, cmin:cmax]
        mask_c = mask_full[rmin:rmax, cmin:cmax]

        rl = r_idx - rmin
        cl = c_idx - cmin
        MR, MC = mask_c.shape

        # ── Recompute routing path for this HRU ─────────────────────────
        out_r, out_c, out_dist = None, None, None
        max_acc = -1.0
        for r, c in zip(rl, cl):
            d = int(fdir_c[r, c])
            if d not in D8:
                continue
            dr, dc, dist = D8[d]
            r2, c2 = r + dr, c + dc
            exits = (r2 < 0 or r2 >= MR or c2 < 0 or c2 >= MC
                     or not mask_c[r2, c2])
            if exits and facc_c[r, c] > max_acc:
                max_acc = facc_c[r, c]
                out_r, out_c, out_dist = r, c, dist

        path_len = np.full((MR, MC), np.nan)
        if out_r is not None:
            path_len[out_r, out_c] = out_dist
            order = np.argsort(-facc_c[rl, cl])
            for r, c in zip(rl[order], cl[order]):
                if not np.isnan(path_len[r, c]):
                    continue
                d = int(fdir_c[r, c])
                if d not in D8:
                    continue
                dr, dc, dist = D8[d]
                r2, c2 = r + dr, c + dc
                exits = (r2 < 0 or r2 >= MR or c2 < 0 or c2 >= MC
                         or not mask_c[r2, c2])
                if not exits and not np.isnan(path_len[r2, c2]):
                    path_len[r, c] = dist + path_len[r2, c2]

        vals        = path_len[rl, cl]
        valid_vals  = vals[~np.isnan(vals)]
        routing_len = float(np.nanmax(valid_vals)) if len(valid_vals) > 0 else np.nan
        if len(valid_vals) > 0:
            div_idx  = np.nanargmax(vals)
            divide_r = int(rl[div_idx])
            divide_c = int(cl[div_idx])
        else:
            divide_r = divide_c = None

        # Trace the routing path cells (divide → outlet)
        route_cells = []
        if divide_r is not None and out_r is not None:
            r, c = divide_r, divide_c
            for _ in range(100_000):
                route_cells.append((r, c))
                if r == out_r and c == out_c:
                    break
                d = int(fdir_c[r, c])
                if d not in D8:
                    break
                dr, dc, _ = D8[d]
                r, c = r + dr, c + dc
                if not (0 <= r < MR and 0 <= c < MC and mask_c[r, c]):
                    break

        # ── 4-panel figure ───────────────────────────────────────────────
        n_nan_hru = int(np.isnan(dem_c[mask_c]).sum())
        er        = float(np.nanmax(dem_c[mask_c]) - np.nanmin(dem_c[mask_c]))

        fig, axes = plt.subplots(2, 2, figsize=(14, 12))
        fig.suptitle(
            f"HRU {CHECK_HRU_ID} — DEM Diagnostic Detail\n"
            f"Cells: {mask_c.sum()}   NaN inside HRU: {n_nan_hru}   "
            f"Elevation range: {er:.1f} m   "
            f"Routing length: {routing_len:.1f} m",
            fontsize=12,
        )

        # Helper: draw HRU boundary on an axis using contour
        def draw_boundary(ax_):
            ax_.contour(mask_c.astype(float), levels=[0.5],
                        colors="blue", linewidths=1.8)

        # ── Panel A: DEM elevation ───────────────────────────────────────
        ax = axes[0, 0]
        dem_show = dem_c.copy()
        dem_show[~mask_c] = np.nan
        im_a = ax.imshow(dem_show, cmap="terrain", origin="upper",
                         interpolation="nearest")
        ax.contour(dem_show, levels=12, colors="black",
                   linewidths=0.4, alpha=0.4)
        plt.colorbar(im_a, ax=ax, label="Elevation (m)",
                     fraction=0.046, pad=0.04)
        # Highlight NaN cells inside HRU in red
        nan_in = np.isnan(dem_c) & mask_c
        if nan_in.any():
            ax.imshow(np.where(nan_in, 1.0, np.nan),
                      cmap="Reds", origin="upper", alpha=0.85,
                      interpolation="nearest", vmin=0, vmax=1)
            ax.set_title(f"(A) Elevation  ⚠  {nan_in.sum()} NaN cells (red)",
                         color="red", fontsize=10)
        else:
            ax.set_title("(A) Elevation  ✓  No NaN cells inside HRU",
                         color="green", fontsize=10)
        draw_boundary(ax)
        ax.set_xticks([]); ax.set_yticks([])

        # ── Panel B: Flow accumulation ───────────────────────────────────
        ax = axes[0, 1]
        fa_show = facc_c.copy()
        fa_show[~mask_c] = np.nan
        im_b = ax.imshow(np.log1p(fa_show), cmap="Blues", origin="upper",
                         interpolation="nearest")
        plt.colorbar(im_b, ax=ax, label="log(1 + accumulation)",
                     fraction=0.046, pad=0.04)
        if out_r is not None:
            ax.plot(out_c, out_r, "rv", markersize=12,
                    label=f"Outlet (acc={max_acc:.0f})")
            ax.legend(fontsize=8, loc="lower right")
        ax.set_title("(B) Flow Accumulation\n"
                     "High (dark) = channel / valley   Low = ridge / divide",
                     fontsize=10)
        draw_boundary(ax)
        ax.set_xticks([]); ax.set_yticks([])

        # ── Panel C: D8 flow direction (quiver arrows) ───────────────────
        ax = axes[1, 0]
        dem_bg = dem_c.copy(); dem_bg[~mask_c] = np.nan
        ax.imshow(dem_bg, cmap="terrain", origin="upper",
                  interpolation="nearest", alpha=0.5)
        # Build quiver arrays
        # In imshow with origin='upper': x=col, y=row (y increases downward)
        # quiver u=col_offset, v=row_offset gives correct arrow on screen
        U = np.zeros((MR, MC), dtype=float)
        V = np.zeros((MR, MC), dtype=float)
        for code, (dr, dc, _) in D8.items():
            cells = (fdir_c == code) & mask_c
            U[cells] = dc
            V[cells] = dr   # positive row = downward = positive y on screen
        Y, X = np.mgrid[0:MR, 0:MC]
        # Only draw arrows for cells inside the HRU
        m = mask_c.ravel()
        ax.quiver(
            X.ravel()[m], Y.ravel()[m],
            U.ravel()[m], V.ravel()[m],
            scale=20, scale_units="xy", angles="xy",
            width=0.004, headwidth=4, headlength=5,
            color="black", alpha=0.75,
        )
        # Mark NaN cells (no arrow = no direction)
        if nan_in.any():
            ax.imshow(np.where(nan_in, 1.0, np.nan),
                      cmap="Reds", origin="upper", alpha=0.6,
                      interpolation="nearest", vmin=0, vmax=1)
        ax.set_title("(C) D8 Flow Direction\n"
                     "Each arrow shows where that cell drains   Red = NaN (no direction)",
                     fontsize=10)
        draw_boundary(ax)
        ax.set_xticks([]); ax.set_yticks([])

        # ── Panel D: Routing path ────────────────────────────────────────
        ax = axes[1, 1]
        ax.imshow(dem_bg, cmap="terrain", origin="upper",
                  interpolation="nearest", alpha=0.45)
        # Colour every cell by its path length to outlet
        pl_show = path_len.copy(); pl_show[~mask_c] = np.nan
        im_d = ax.imshow(pl_show, cmap="YlOrRd", origin="upper",
                         interpolation="nearest", alpha=0.75)
        plt.colorbar(im_d, ax=ax, label="Path length to outlet (m)",
                     fraction=0.046, pad=0.04)
        # Draw the routing path in green
        if route_cells:
            rc_r = [rc[0] for rc in route_cells]
            rc_c = [rc[1] for rc in route_cells]
            ax.plot(rc_c, rc_r, "g-", linewidth=3, alpha=0.9,
                    label="Routing path")
        # Mark divide and outlet
        if divide_r is not None:
            ax.plot(divide_c, divide_r, "b^", markersize=12,
                    label=f"Divide")
        if out_r is not None:
            ax.plot(out_c, out_r, "rv", markersize=12,
                    label=f"Outlet")
        ax.set_title(
            f"(D) Routing Path: Divide ▲ → Outlet ▼\n"
            f"Routing length = {routing_len:.1f} m   "
            f"(green line = traced path)",
            fontsize=10,
        )
        ax.legend(fontsize=8, loc="lower right")
        draw_boundary(ax)
        ax.set_xticks([]); ax.set_yticks([])

        plt.tight_layout()
        out2 = os.path.join(OUTPUT_DIR, f"diagnostic_hru{CHECK_HRU_ID}_detail.png")
        plt.savefig(out2, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  Saved: {out2}")

        # ── PLOT 3: Elevation profile along routing path ─────────────────
        if len(route_cells) > 1:
            dist_list = [0.0]
            elev_list = [float(dem_c[route_cells[0]])]
            cum = 0.0
            for k in range(1, len(route_cells)):
                r_prev, c_prev = route_cells[k - 1]
                r_curr, c_curr = route_cells[k]
                d = int(fdir_c[r_prev, c_prev])
                step = D8[d][2] if d in D8 else min(cell_x_m, cell_y_m)
                cum += step
                dist_list.append(cum)
                e = dem_c[r_curr, c_curr]
                elev_list.append(float(e) if not np.isnan(e) else np.nan)

            fig, ax = plt.subplots(figsize=(11, 4))
            ax.plot(dist_list, elev_list, "b-o", markersize=5,
                    linewidth=2, label="Elevation along path")
            ax.fill_between(
                dist_list,
                [min(e for e in elev_list if not np.isnan(e)) - 20] * len(dist_list),
                [e if not np.isnan(e) else np.nan for e in elev_list],
                alpha=0.15, color="blue",
            )
            # Mark NaN positions in the profile
            nan_pos = [d for d, e in zip(dist_list, elev_list) if np.isnan(e)]
            if nan_pos:
                ax.axvline(x=nan_pos[0], color="red", linestyle="--",
                           alpha=0.7, label="NaN cell on path")
                for np_ in nan_pos[1:]:
                    ax.axvline(x=np_, color="red", linestyle="--", alpha=0.7)

            total_drop = elev_list[0] - elev_list[-1] if (
                not np.isnan(elev_list[0]) and not np.isnan(elev_list[-1])
            ) else np.nan
            avg_slope  = (total_drop / cum * 100) if (
                not np.isnan(total_drop) and cum > 0
            ) else np.nan

            ax.set_xlabel("Distance from divide (m)", fontsize=11)
            ax.set_ylabel("Elevation (m)", fontsize=11)
            ax.set_title(
                f"HRU {CHECK_HRU_ID} — Elevation Profile Along Routing Path\n"
                f"Total path: {cum:.1f} m   "
                f"Elevation drop: {total_drop:.1f} m   "
                f"Avg slope: {avg_slope:.1f}%",
                fontsize=11,
            )
            ax.legend(fontsize=9)
            ax.grid(True, alpha=0.3)

            # Annotate divide and outlet
            if not np.isnan(elev_list[0]):
                ax.annotate(
                    "Divide",
                    xy=(dist_list[0], elev_list[0]),
                    xytext=(dist_list[0] + cum * 0.03, elev_list[0]),
                    fontsize=9, color="darkblue",
                    arrowprops=dict(arrowstyle="->", color="darkblue"),
                )
            if not np.isnan(elev_list[-1]):
                ax.annotate(
                    "Outlet",
                    xy=(dist_list[-1], elev_list[-1]),
                    xytext=(dist_list[-1] - cum * 0.15, elev_list[-1] + 20),
                    fontsize=9, color="darkred",
                    arrowprops=dict(arrowstyle="->", color="darkred"),
                )

            plt.tight_layout()
            out3 = os.path.join(
                OUTPUT_DIR, f"diagnostic_hru{CHECK_HRU_ID}_profile.png"
            )
            plt.savefig(out3, dpi=150, bbox_inches="tight")
            plt.close()
            print(f"  Saved: {out3}")


# =============================================================================
# SUMMARY
# =============================================================================
print("\n[5/5] Done.")
print(f"\n{'='*60}")
print("  OUTPUT FILES")
print(f"{'='*60}")
print(f"  {os.path.join(OUTPUT_DIR, 'diagnostic_overview.png')}")
print(f"  {os.path.join(OUTPUT_DIR, f'diagnostic_hru{CHECK_HRU_ID}_detail.png')}")
print(f"  {os.path.join(OUTPUT_DIR, f'diagnostic_hru{CHECK_HRU_ID}_profile.png')}")
print(f"  {os.path.join(OUTPUT_DIR, 'dem_diagnostic_stats.csv')}")
print(f"{'='*60}")

print(f"\n  WHAT TO LOOK FOR")
print(f"{'='*60}")
print(f"  Panel A (Elevation):")
print(f"    - Any red cells = NaN/nodata inside the HRU → breaks flow path")
print(f"    - Contours should run roughly parallel and show clear gradient")
print(f"    - If contours are all cramped at one end → flat pit-fill area")
print(f"")
print(f"  Panel B (Flow Accumulation):")
print(f"    - Should show a tree-like branching pattern (dark = channel)")
print(f"    - If entire HRU is same colour → accumulation is broken (flat DEM)")
print(f"")
print(f"  Panel C (Flow Direction):")
print(f"    - Arrows should generally point toward the outlet")
print(f"    - Chaotic/random arrows → flat area, epsilon perturbation routing")
print(f"    - Red cells = NaN cells with no flow direction")
print(f"")
print(f"  Panel D (Routing Path):")
print(f"    - Green line should go from one end of HRU to the other")
print(f"    - If path is short (middle only) → path is broken by NaN or flat cells")
print(f"")
print(f"  Profile plot:")
print(f"    - Elevation should decrease smoothly from divide to outlet")
print(f"    - Flat sections = pit-fill artifacts")
print(f"    - Red dashed lines = NaN cells encountered on the path")
