# CMIP6 (Nepal) CSV to gridded NetCDF

Converts the Mishra et al. bias-corrected CMIP6 projections for Nepal from wide
CSV files to CF-1.8 gridded NetCDF, and verifies every converted file against its
source cell-by-cell.

- **13 models** x **2 scenarios** (`historical` 1951-2014, `ssp370` 2015-2100)
  x **3 variables** (`pr`, `tmax`, `tmin`) = **78 files**, one `.nc` per `.csv`.
- Source: Mishra, V., Bhatia, U. & Tiwari, A. D. (2020). *Bias-corrected climate
  projections for South Asia from CMIP6.* Scientific Data 7, 338.
  https://doi.org/10.1038/s41597-020-00681-1

## Input CSV layout (wide)

| row | col 0 | cols 1..215 |
|-----|-------|-------------|
| 0 | `lat` | latitude of each station |
| 1 | `lon` | longitude of each station |
| 2 | `station_id` | integer id `1..215` |
| 3+ | `YYYY-MM-DD` | daily value at each station |

## Output NetCDF

| | |
|---|---|
| layout | gridded `(time, lat, lon)`, regular 0.25 deg, 16 lat x 33 lon, ascending |
| units | unchanged: `pr` in `mm` (`cell_methods = "time: sum"`), `tmax`/`tmin` in `degC` (`"time: maximum"` / `"time: minimum"`) |
| calendar | `standard`; every 29 Feb kept; no-leap models get fill on 29 Feb |
| fill value | `-9999.0` (float32) for out-of-domain cells, no-leap 29 Feb, and the `-273.15` (0 K) sentinel |
| time | integer days since `1951-01-01`; `time_bnds`, `lat_bnds`, `lon_bnds` included |
| extras | `station_id(lat, lon)` int helper (fill `-1`) mapping each cell to its CSV column |
| storage | float32, zlib level 4 + shuffle, chunks `(365, 16, 33)`, NetCDF-4 |

## Usage

```bash
# convert every CSV in a folder -> <folder>/nc/*.nc
python convert_csv_to_netcdf.py --src /path/to/csv_folder

# verify every CSV <-> NetCDF pair (exits non-zero if any fail)
python verify_netcdf.py --src /path/to/csv_folder --csv verification_report.csv
```

The verifier re-parses each CSV through a different code path than the converter
and reads the `.nc` back with `xarray` (converter writes with `netCDF4`), then
runs ~30 checks over every data cell. Expected result:

```
ALL PAIRS PASS     : True
failing pairs      : 0
worst max_abs_err  : ~1e-05   # float32 rounding of 2-decimal data; lossless at this precision
worst sum_abs_diff : ~1e-02   # accumulated float32 rounding over ~6.7M cells
```

Optional fully independent structural check with CDO:

```bash
cdo sinfon ACCESS-CM2_historical_pr.nc
cdo -outputtab,date,value -sellonlatbox,80.124,80.126,28.874,28.876 ACCESS-CM2_historical_pr.nc | head
```

## Requirements

```
numpy
pandas
netCDF4
xarray
```

## Notes

- `float32` storage rounds each value by ~1e-5, ~1000x below the data's 0.01
  precision. For bit-exact storage change `"f4"` to `"f8"` in
  `convert_csv_to_netcdf.py` (doubles file size).
- Six models are 365-day (no-leap): BCC-CSM2-MR, CanESM5, INM-CM4-8, INM-CM5-0,
  NorESM2-LM, NorESM2-MM. Their 29 Feb rows exist but are fill.
- The `-273.15` sentinel appears only in the 13 `ssp370` temperature files.
