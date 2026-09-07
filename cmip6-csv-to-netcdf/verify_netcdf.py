#!/usr/bin/env python3
"""
Independent verification of the CSV -> NetCDF conversion (see convert_csv_to_netcdf.py).

For every CSV it re-parses the file with a DIFFERENT code path than the converter
(type-inferred pandas read, not the converter's dtype=str reader) and reads the
matching .nc back with xarray (the converter wrote with netCDF4). It then runs
~30 checks over EVERY data cell and prints one PASS / FAIL per pair.

Checks cover: correct file pairing (source_id/experiment_id/variable_id vs name),
regular grid axes and bounds, exact station -> grid-cell placement, date axis
(string-for-string) and time/lat/lon bounds, every in-domain value (float32
tolerance 1e-3), missing handling (blank cells, 29-Feb on no-leap models, and the
-273.15 sentinel all -> fill), out-of-domain cells all fill, valid-cell counts
equal, units / cell_methods / standard_name / _FillValue / Conventions / dtype,
and an independent grand-sum comparison.

Usage:
    python verify_netcdf.py --src /path/to/csv_folder
    python verify_netcdf.py --src ./csv --out ./csv/nc --csv report.csv
"""
from __future__ import annotations

import argparse
import glob
import os

import numpy as np
import pandas as pd
import xarray as xr

RES = 0.25
FILL = -9999.0

EXP_UNITS = {"pr": "mm", "tmax": "degC", "tmin": "degC"}
EXP_CELLM = {"pr": "time: sum", "tmax": "time: maximum", "tmin": "time: minimum"}
EXP_DAYS = {"historical": 23376, "ssp370": 31411}

CHECKS = [
    "nc_exists", "id_source", "id_expt", "id_var",
    "grid_lat_axis", "grid_lon_axis", "grid_ascending",
    "station_on_node", "station_unique", "shape_ok",
    "time_dates_match", "time_len_expected", "time_bnds_ok", "lat_bnds_ok", "lon_bnds_ok",
    "missing_are_nan", "values_match", "outdomain_fill", "no_disk_nan", "valid_count_match",
    "feb29_ok", "sentinel_are_nan",
    "units_ok", "cellm_ok", "stdname_ok", "fill_value_ok", "no_coord_attr",
    "conventions_ok", "dtype_f32", "sum_ok",
]


def check_pair(csv_path, out_dir):
    stem = os.path.basename(csv_path)[:-4]
    model, scenario, var = stem.rsplit("_", 2)
    nc_path = os.path.join(out_dir, stem + ".nc")
    r = {"file": stem + ".csv"}
    try:
        r["nc_exists"] = os.path.exists(nc_path)
        if not r["nc_exists"]:
            r["PASS"] = False
            return r

        # ---- independent CSV parse (type-inferred; NOT the converter's reader) ----
        dat = pd.read_csv(csv_path, header=None, skiprows=3)
        while dat.shape[1] > 1 and dat.iloc[:, -1].isna().all():
            dat = dat.iloc[:, :-1]
        nst = dat.shape[1] - 1
        hdr = pd.read_csv(csv_path, header=None, nrows=3, dtype=str).iloc[:, : nst + 1]

        lat_csv = hdr.iloc[0, 1:].astype(float).to_numpy()
        lon_csv = hdr.iloc[1, 1:].astype(float).to_numpy()
        date_csv = dat.iloc[:, 0].astype(str).to_numpy()
        val_csv = dat.iloc[:, 1:].to_numpy(dtype=float)          # blanks -> NaN
        ndays = val_csv.shape[0]
        r["csv_stations"], r["csv_days"] = nst, ndays

        # ---- read NC (xarray; converter wrote with netCDF4) ----
        ds = xr.open_dataset(nc_path, decode_times=True, mask_and_scale=True)     # fill -> NaN
        dsr = xr.open_dataset(nc_path, decode_times=False, mask_and_scale=False)  # raw, -9999
        lat_nc = ds["lat"].to_numpy()
        lon_nc = ds["lon"].to_numpy()
        dat_nc = ds[var].to_numpy()                              # NaN = fill
        raw_nc = dsr[var].to_numpy()                             # float32, -9999 = fill

        # ---- A. identity: right CSV <-> right NC ----
        r["id_source"] = ds.attrs.get("source_id") == model
        r["id_expt"] = ds.attrs.get("experiment_id") == scenario
        r["id_var"] = (ds.attrs.get("variable_id") == var) and (var in ds)

        # ---- B. geometry ----
        lat_exp = np.round(np.arange(lat_csv.min(), lat_csv.max() + RES / 2, RES), 3)
        lon_exp = np.round(np.arange(lon_csv.min(), lon_csv.max() + RES / 2, RES), 3)
        r["grid_lat_axis"] = lat_nc.shape == lat_exp.shape and np.allclose(lat_nc, lat_exp)
        r["grid_lon_axis"] = lon_nc.shape == lon_exp.shape and np.allclose(lon_nc, lon_exp)
        r["grid_ascending"] = bool(np.all(np.diff(lat_nc) > 0) and np.all(np.diff(lon_nc) > 0))
        ilat = np.abs(lat_nc[:, None] - lat_csv[None, :]).argmin(0)
        ilon = np.abs(lon_nc[:, None] - lon_csv[None, :]).argmin(0)
        r["station_on_node"] = bool(
            np.allclose(lat_nc[ilat], lat_csv, atol=1e-6)
            and np.allclose(lon_nc[ilon], lon_csv, atol=1e-6)
        )
        r["station_unique"] = len(set(zip(ilat.tolist(), ilon.tolist()))) == nst
        r["shape_ok"] = dat_nc.shape == (ndays, lat_exp.size, lon_exp.size)

        # ---- C. time & bounds ----
        tstr = pd.DatetimeIndex(ds["time"].to_numpy()).strftime("%Y-%m-%d").to_numpy()
        r["time_dates_match"] = tstr.shape == date_csv.shape and np.array_equal(tstr, date_csv)
        r["time_len_expected"] = ndays == EXP_DAYS[scenario]
        tv = dsr["time"].to_numpy()
        tb = dsr["time_bnds"].to_numpy()
        r["time_bnds_ok"] = np.array_equal(tb[:, 0], tv) and np.array_equal(tb[:, 1], tv + 1)
        lb = dsr["lat_bnds"].to_numpy()
        nb = dsr["lon_bnds"].to_numpy()
        r["lat_bnds_ok"] = np.allclose(lb[:, 0], lat_exp - RES / 2) and np.allclose(lb[:, 1], lat_exp + RES / 2)
        r["lon_bnds_ok"] = np.allclose(nb[:, 0], lon_exp - RES / 2) and np.allclose(nb[:, 1], lon_exp + RES / 2)

        # ---- D. every in-domain value ----
        got = dat_nc[:, ilat, ilon]                              # (ndays, nst), NaN = fill
        bad = ~np.isfinite(val_csv) | np.isclose(val_csv, -273.15, atol=1e-6)
        r["missing_are_nan"] = bool(np.all(np.isnan(got[bad]))) if bad.any() else True
        if (~bad).any():
            diff = np.abs(got[~bad] - val_csv[~bad])
            r["values_match"] = bool(np.all(np.isfinite(got[~bad])) and np.nanmax(diff) <= 1e-3)
            r["max_abs_err"] = float(np.nanmax(diff))
        else:
            r["values_match"], r["max_abs_err"] = True, 0.0

        # ---- E. fill structure ----
        real = np.zeros((lat_exp.size, lon_exp.size), bool)
        real[ilat, ilon] = True
        r["outdomain_fill"] = bool(np.all(raw_nc[:, ~real] == FILL))
        r["no_disk_nan"] = not bool(np.isnan(raw_nc).any())
        r["n_valid_csv"] = int(np.sum(~bad))
        r["n_valid_nc"] = int(np.sum(raw_nc != FILL))
        r["valid_count_match"] = r["n_valid_nc"] == r["n_valid_csv"]

        # ---- F. tricky cases handled automatically ----
        is29 = pd.Series(date_csv).str.endswith("-02-29").to_numpy()
        r["n_feb29_rows"] = int(is29.sum())
        if is29.any():
            g, c = got[is29], val_csv[is29]
            b = ~np.isfinite(c) | np.isclose(c, -273.15, atol=1e-6)
            r["feb29_ok"] = bool(
                (np.all(np.isnan(g[b])) if b.any() else True)
                and (np.all(np.abs(g[~b] - c[~b]) <= 1e-3) if (~b).any() else True)
            )
        else:
            r["feb29_ok"] = True
        sent = np.isclose(val_csv, -273.15, atol=1e-6)
        r["n_sentinel_csv"] = int(sent.sum())
        r["sentinel_are_nan"] = bool(np.all(np.isnan(got[sent]))) if sent.any() else True

        # ---- G. metadata ----
        a = ds[var].attrs

        def fv(v):
            for s in (v.attrs, v.encoding):
                if "missing_value" in s:
                    return float(np.asarray(s["missing_value"]))
                if "_FillValue" in s:
                    return float(np.asarray(s["_FillValue"]))
            return None

        r["units_ok"] = a.get("units") == EXP_UNITS[var]
        r["cellm_ok"] = a.get("cell_methods") == EXP_CELLM[var]
        r["stdname_ok"] = isinstance(a.get("standard_name"), str) and len(a["standard_name"]) > 0
        r["fill_value_ok"] = fv(dsr[var]) == FILL
        r["no_coord_attr"] = ("coordinates" not in a) and ("coordinates" not in ds[var].encoding)
        r["conventions_ok"] = ds.attrs.get("Conventions") == "CF-1.8"
        r["dtype_f32"] = dsr[var].dtype == np.float32

        # ---- H. independent aggregate (sum over all valid values) ----
        csv_sum = float(np.nansum(np.where(bad, np.nan, val_csv)))
        nc_sum = float(np.nansum(np.where(raw_nc == FILL, np.nan, raw_nc.astype(np.float64))))
        r["sum_abs_diff"] = abs(csv_sum - nc_sum)
        r["sum_ok"] = r["sum_abs_diff"] <= (1e-3 * r["n_valid_csv"] + 1.0)

        ds.close()
        dsr.close()
    except Exception as e:  # noqa: BLE001 - report, don't crash the batch
        r["error"] = f"{type(e).__name__}: {e}"

    r["PASS"] = ("error" not in r) and all(bool(r.get(k, False)) for k in CHECKS)
    return r


def main():
    ap = argparse.ArgumentParser(description="Verify every CSV <-> NetCDF pair.")
    ap.add_argument("--src", default=".", help="folder containing the *.csv files (default: .)")
    ap.add_argument("--out", default=None, help="folder containing the *.nc files (default: <src>/nc)")
    ap.add_argument("--csv", default=None, help="optional path to write the full report as CSV")
    args = ap.parse_args()

    src = os.path.abspath(args.src)
    out = os.path.abspath(args.out) if args.out else os.path.join(src, "nc")

    files = sorted(glob.glob(os.path.join(src, "*.csv")))
    if not files:
        raise SystemExit(f"no CSV files found in {src}")

    rows = []
    for i, f in enumerate(files, 1):
        row = check_pair(f, out)
        rows.append(row)
        tag = "PASS" if row["PASS"] else "FAIL  <<<"
        extra = "" if "error" not in row else f"  {row['error']}"
        print(f"[{i:3d}/{len(files)}] {row['file']:38s} {tag}{extra}")

    rep = pd.DataFrame(rows)
    print("\n" + "=" * 60)
    print(f"pairs checked      : {len(rep)}")
    print(f"ALL PAIRS PASS     : {bool(rep['PASS'].all())}")
    print(f"failing pairs      : {int((~rep['PASS']).sum())}")
    print(f"worst max_abs_err  : {rep.get('max_abs_err', pd.Series([0.0])).max():.2e}")
    print(f"worst sum_abs_diff : {rep.get('sum_abs_diff', pd.Series([0.0])).max():.2e}")

    if not rep["PASS"].all():
        print("\nFailing files and which checks failed:")
        for _, row in rep.loc[~rep["PASS"]].iterrows():
            failed = [c for c in CHECKS if row.get(c) is False]
            print(f"  {row['file']}: {failed or row.get('error')}")

    if args.csv:
        rep.to_csv(args.csv, index=False)
        print(f"\nreport written -> {os.path.abspath(args.csv)}")

    raise SystemExit(0 if bool(rep["PASS"].all()) else 1)


if __name__ == "__main__":
    main()
