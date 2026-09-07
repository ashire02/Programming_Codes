#!/usr/bin/env python3
"""
Convert Mishra et al. CMIP6 (Nepal) wide CSV files to gridded CF-1.8 NetCDF.

One .nc per CSV. 13 models x {historical, ssp370} x {pr, tmax, tmin} = 78 files.

Input CSV layout (wide):
    row 0 : lat        , <215 latitude values>
    row 1 : lon        , <215 longitude values>
    row 2 : station_id , <215 integer ids 1..215>
    row 3+: YYYY-MM-DD  , <215 daily values>
Some files carry one trailing empty column (dropped automatically).
Six no-leap models keep the 29-Feb date rows but leave them blank.
Thirteen ssp370 temperature files contain a -273.15 (0 K) missing sentinel.

Output NetCDF:
    - gridded (time, lat, lon); regular 0.25 deg grid, 16 lat x 33 lon, ascending
    - units unchanged: pr in mm (cell_methods "time: sum"),
      tmax/tmin in degC ("time: maximum" / "time: minimum")
    - calendar "standard"; every 29 Feb retained, set to fill on no-leap models
    - fill value -9999.0 (float32) as both _FillValue and missing_value, used for
      out-of-domain cells, no-leap 29 Feb, and the -273.15 sentinel
    - time = integer days since 1951-01-01; time_bnds, lat_bnds, lon_bnds included
    - station_id(lat, lon) int helper (fill -1) mapping each cell to its CSV column
    - float32 data, zlib level 4 + shuffle, chunks (365, 16, 33)

Usage:
    python convert_csv_to_netcdf.py --src /path/to/csv_folder
    python convert_csv_to_netcdf.py --src ./csv --out ./csv/nc
"""
from __future__ import annotations

import argparse
import glob
import os

import numpy as np
import pandas as pd
from netCDF4 import Dataset

# --------------------------------------------------------------------------- #
# fixed parameters (from a full profile of all 78 source files)
# --------------------------------------------------------------------------- #
RES = 0.25
FILL = -9999.0
EPOCH = "1951-01-01"
LAT0, LAT1 = 26.625, 30.375          # regular-grid latitude extent  (inclusive) -> 16
LON0, LON1 = 80.125, 88.125          # regular-grid longitude extent (inclusive) -> 33

EXPECTED = {                          # (first date, last date, n_days) per scenario
    "historical": ("1951-01-01", "2014-12-31", 23376),
    "ssp370":     ("2015-01-01", "2100-12-31", 31411),
}

# variable -> (long_name, standard_name, units, cell_methods)
META = {
    "pr":   ("Daily total precipitation",                  "lwe_thickness_of_precipitation_amount", "mm",   "time: sum"),
    "tmax": ("Daily maximum near-surface air temperature", "air_temperature",                       "degC", "time: maximum"),
    "tmin": ("Daily minimum near-surface air temperature", "air_temperature",                       "degC", "time: minimum"),
}

REFERENCES = (
    "Mishra, V., Bhatia, U., and Tiwari, A. D. (2020): Bias-corrected climate "
    "projections for South Asia from Coupled Model Intercomparison Project-6 (CMIP6). "
    "Scientific Data 7, 338. https://doi.org/10.1038/s41597-020-00681-1"
)

COMMENT = (
    "Domain masked to 215 grid points over Nepal; cells outside the domain set to -9999. "
    "Calendar is standard with all 29 February dates retained; for no-leap models "
    "(BCC-CSM2-MR, CanESM5, INM-CM4-8, INM-CM5-0, NorESM2-LM, NorESM2-MM) "
    "29 February is set to -9999."
)


# --------------------------------------------------------------------------- #
def read_csv_block(csv_path):
    """Parse one wide CMIP6 CSV.

    Returns lat(215), lon(215), sid(215), dates(ntime), vals(ntime, 215).
    Blank cells -> NaN; the -273.15 sentinel is left untouched here.
    """
    raw = pd.read_csv(csv_path, header=None, dtype=str)

    # strip trailing all-empty column(s) present in some files
    j = raw.shape[1] - 1
    while j > 0 and raw.iloc[:, j].isna().all():
        j -= 1
    raw = raw.iloc[:, : j + 1]

    nst = raw.shape[1] - 1
    assert nst == 215, f"{os.path.basename(csv_path)}: found {nst} station columns, expected 215"

    lat = pd.to_numeric(raw.iloc[0, 1:]).to_numpy(float)
    lon = pd.to_numeric(raw.iloc[1, 1:]).to_numpy(float)
    sid = pd.to_numeric(raw.iloc[2, 1:]).round().astype(int).to_numpy()

    dates = pd.to_datetime(raw.iloc[3:, 0].to_numpy(), format="%Y-%m-%d")
    vals = raw.iloc[3:, 1:].apply(pd.to_numeric, errors="coerce").to_numpy("float64")
    return lat, lon, sid, dates, vals


def convert(csv_path, out_dir):
    """Convert one CSV to a gridded NetCDF file. Returns the output path."""
    fn = os.path.basename(csv_path)
    model, scenario, var = fn[:-4].rsplit("_", 2)
    long_name, std_name, units, cellm = META[var]

    lat, lon, sid, dates, vals = read_csv_block(csv_path)

    # sanity vs known profile
    d0, d1, n = EXPECTED[scenario]
    assert str(dates[0].date()) == d0 and str(dates[-1].date()) == d1, f"{fn}: date span"
    assert len(dates) == n == vals.shape[0], f"{fn}: n_days"
    t = (dates - pd.Timestamp(EPOCH)).days.to_numpy()
    assert np.all(np.diff(t) == 1), f"{fn}: non-contiguous daily axis"

    # regular grid + station -> cell map
    lat_axis = np.round(np.arange(LAT0, LAT1 + RES / 2, RES), 3)   # 16
    lon_axis = np.round(np.arange(LON0, LON1 + RES / 2, RES), 3)   # 33
    nlat, nlon, ntime = lat_axis.size, lon_axis.size, t.size

    la = np.round((lat - LAT0) / RES).astype(int)
    lo = np.round((lon - LON0) / RES).astype(int)
    assert la.min() >= 0 and la.max() < nlat, f"{fn}: lat out of grid"
    assert lo.min() >= 0 and lo.max() < nlon, f"{fn}: lon out of grid"
    assert len(set(zip(la.tolist(), lo.tolist()))) == 215, f"{fn}: cell collision"
    assert np.allclose(lat_axis[la], lat, atol=1e-6) and np.allclose(lon_axis[lo], lon, atol=1e-6)

    # build cube: fill everywhere, scatter valid values in
    cube = np.full((ntime, nlat, nlon), FILL, dtype="float32")
    bad = ~np.isfinite(vals) | np.isclose(vals, -273.15, atol=1e-6)   # blank rows + 0-K sentinel
    cube[:, la, lo] = np.where(bad, FILL, vals).astype("float32")

    sid_grid = np.full((nlat, nlon), -1, dtype="int32")
    sid_grid[la, lo] = sid.astype("int32")

    out_path = os.path.join(out_dir, fn[:-4] + ".nc")
    with Dataset(out_path, "w", format="NETCDF4") as ds:
        ds.createDimension("time", ntime)
        ds.createDimension("lat", nlat)
        ds.createDimension("lon", nlon)
        ds.createDimension("nv", 2)

        v = ds.createVariable("time", "i4", ("time",))
        v[:] = t.astype("int32")
        v.units, v.calendar = f"days since {EPOCH} 00:00:00", "standard"
        v.standard_name, v.long_name, v.axis, v.bounds = "time", "time", "T", "time_bnds"
        ds.createVariable("time_bnds", "i4", ("time", "nv"))[:, :] = np.stack([t, t + 1], 1).astype("int32")

        v = ds.createVariable("lat", "f8", ("lat",))
        v[:] = lat_axis
        v.units, v.standard_name, v.long_name, v.axis, v.bounds = \
            "degrees_north", "latitude", "latitude", "Y", "lat_bnds"
        ds.createVariable("lat_bnds", "f8", ("lat", "nv"))[:, :] = \
            np.stack([lat_axis - RES / 2, lat_axis + RES / 2], 1)

        v = ds.createVariable("lon", "f8", ("lon",))
        v[:] = lon_axis
        v.units, v.standard_name, v.long_name, v.axis, v.bounds = \
            "degrees_east", "longitude", "longitude", "X", "lon_bnds"
        ds.createVariable("lon_bnds", "f8", ("lon", "nv"))[:, :] = \
            np.stack([lon_axis - RES / 2, lon_axis + RES / 2], 1)

        d = ds.createVariable(
            var, "f4", ("time", "lat", "lon"),
            zlib=True, complevel=4, shuffle=True,
            chunksizes=(min(365, ntime), nlat, nlon),
            fill_value=np.float32(FILL),
        )
        d[:, :, :] = cube
        d.units, d.long_name, d.standard_name, d.cell_methods = units, long_name, std_name, cellm
        d.missing_value = np.float32(FILL)

        s = ds.createVariable(
            "station_id", "i4", ("lat", "lon"),
            zlib=True, complevel=4, shuffle=True, fill_value=-1,
        )
        s[:, :] = sid_grid
        s.long_name = "source CSV station identifier"
        s.comment = "grid cell -> original CSV column; -1 where no station"

        ds.title = f"Bias-corrected CMIP6 {long_name.lower()} over Nepal - {model}, {scenario}"
        ds.Conventions = "CF-1.8"
        ds.source_id = model
        ds.experiment_id = scenario
        ds.variable_id = var
        ds.frequency = "day"
        ds.realm = "atmos"
        ds.geospatial_lat_min = float(lat_axis[0])
        ds.geospatial_lat_max = float(lat_axis[-1])
        ds.geospatial_lon_min = float(lon_axis[0])
        ds.geospatial_lon_max = float(lon_axis[-1])
        ds.geospatial_lat_resolution = RES
        ds.geospatial_lon_resolution = RES
        ds.references = REFERENCES
        ds.comment = COMMENT

    return out_path


def main():
    ap = argparse.ArgumentParser(description="Convert CMIP6 Nepal wide CSVs to gridded NetCDF.")
    ap.add_argument("--src", default=".", help="folder containing the *.csv files (default: .)")
    ap.add_argument("--out", default=None, help="output folder (default: <src>/nc)")
    args = ap.parse_args()

    src = os.path.abspath(args.src)
    out = os.path.abspath(args.out) if args.out else os.path.join(src, "nc")
    os.makedirs(out, exist_ok=True)

    files = sorted(glob.glob(os.path.join(src, "*.csv")))
    if not files:
        raise SystemExit(f"no CSV files found in {src}")
    print(f"{len(files)} CSV files in {src}")

    for i, f in enumerate(files, 1):
        p = convert(f, out)
        print(f"[{i:3d}/{len(files)}] {os.path.basename(p)}")
    print(f"done -> {out}")


if __name__ == "__main__":
    main()
