# EQM Bias Correction — CMIP6 Point Data

Empirical Quantile Mapping (EQM) bias correction for daily CMIP6 point
data (Tmax, Tmin, precipitation) against DHM in-situ observations,
with a train/validation split and a built-in validation report.

---

## What it does

For each variable, the script builds a **monthly** statistical transfer
function from the observed (DHM) data during a calibration period, then
applies that transfer function to the raw CMIP6 model data to remove its
bias — separately for the calibration period (in-sample check) and a
validation period (out-of-sample skill check).

- **Temperature (Tmax, Tmin):** classic EQM —
  `x_corrected = F_obs^-1( F_model(x) )`, built per calendar month
  (12 separate transfer functions per variable) and applied by linear
  interpolation between sampled quantile pairs.
- **Precipitation:** EQM with a **wet-day frequency correction** step
  first (so the corrected series reproduces the observed fraction of wet
  days), then quantile mapping on wet-day amounts only. Dry days stay 0;
  corrected values are clipped to ≥ 0.

At the end it prints a validation table (Mean, Std Dev, RMSE vs
observed, Bias vs observed, Pearson r) comparing **observed vs raw
CMIP6 vs EQM-corrected CMIP6** for Tmax, Tmin, and precipitation.

## Method summary

| Step | Temperature | Precipitation |
|---|---|---|
| 1 | Split obs + model into calibration / validation periods | Same |
| 2 | Per month, sample both distributions at `N_QUANTILES` probability levels | Compute observed wet-day fraction; find the matching model quantile threshold |
| 3 | Build transfer function `(model_quantiles → obs_quantiles)` | Build transfer function on wet-day amounts only |
| 4 | Apply to calibration data (in-sample) and validation data (out-of-sample) via linear interpolation | Apply to days above the model wet-day threshold; everything else set to 0 |
| 5 | Values outside the training range are clamped to the boundary quantiles (no extrapolation) | Corrected values clipped to ≥ 0 |

## Input files

Four CSVs, each with a date column plus one or more value columns, all
sharing the **same date column name**:

| File (constant) | Must contain |
|---|---|
| `DHM_TEMP_FILE` | `Date`, `Tmax`, `Tmin` — observed daily temperature |
| `DHM_PRECIP_FILE` | `Date`, `Precip` — observed daily precipitation |
| `CMIP6_TEMP_FILE` | `Date`, `Tmax`, `Tmin` — raw CMIP6 daily temperature |
| `CMIP6_PRECIP_FILE` | `Date`, `Precip` — raw CMIP6 daily precipitation |

Dates must be parseable by `pandas.to_datetime`. Files do not need to
share the same date range — calibration/validation slicing handles that.

## Configuration (top of the script)

All settings are plain constants near the top of
`eqm_bias_correction.py` — edit them, then run the script (no CLI args):

```python
# file paths
DHM_TEMP_FILE   = "DHM_temperature.csv"
DHM_PRECIP_FILE = "DHM_precipitation.csv"
CMIP6_TEMP_FILE   = "CMIP6_temperature.csv"
CMIP6_PRECIP_FILE = "CMIP6_precipitation.csv"

# output files
OUT_TEMP_CALIB    = "EQM_temperature_calibration.csv"
OUT_TEMP_VALID    = "EQM_temperature_validation.csv"
OUT_PRECIP_CALIB  = "EQM_precipitation_calibration.csv"
OUT_PRECIP_VALID  = "EQM_precipitation_validation.csv"

# column names — must match your CSV headers exactly
DATE_COL, TMAX_COL, TMIN_COL, PRECIP_COL = "Date", "Tmax", "Tmin", "Precip"

# calibration / validation periods
CALIB_START, CALIB_END = "1980-01-01", "2008-12-31"
VALID_START, VALID_END = "2009-01-01", "2024-12-31"

# EQM parameters
N_QUANTILES   = 100   # number of quantile levels (100 = percentiles)
WET_THRESHOLD = 0.1   # mm/day — minimum to count as a "wet" day

# set True if CMIP6 precip is in kg m-2 s-1 (script multiplies by 86400 -> mm/day)
CONVERT_PRECIP_UNITS = False
```

Change `CALIB_START`/`CALIB_END`/`VALID_START`/`VALID_END` to match
whatever periods your observed and model records actually overlap on.

## How to run

```bash
pip install numpy pandas
cd eqm_bias_correction
python eqm_bias_correction.py
```

Place the four input CSVs in the same folder you run the script from
(or edit the constants to point at full paths). The script prints its
progress (loaded date ranges, per-month skip warnings when a month has
fewer than 10 calibration days, the validation table) and writes four
output CSVs to that same folder.

## Output files

| File | Contents |
|---|---|
| `EQM_temperature_calibration.csv` | `Tmax_EQM`, `Tmin_EQM` for the calibration period (in-sample) |
| `EQM_temperature_validation.csv` | `Tmax_EQM`, `Tmin_EQM` for the validation period (out-of-sample) |
| `EQM_precipitation_calibration.csv` | `Precip_EQM` for the calibration period |
| `EQM_precipitation_validation.csv` | `Precip_EQM` for the validation period |

## Notes / gotchas

- A calendar month with fewer than 10 valid days in either the observed
  or model calibration series is **skipped** (left as NaN) and a warning
  is printed — check for this if a whole month comes back empty.
- The precipitation wet-day threshold is derived independently for each
  calendar month, so a dry-season month and a monsoon month get
  different thresholds.
- No extrapolation: temperature/precip values outside the calibration
  period's observed range are clamped to the nearest quantile boundary,
  not linearly extended.

## Requirements

```
numpy
pandas
```

## Reference

Empirical/Equidistant Quantile Mapping is a standard bias-correction
technique for climate model output, widely used to correct CMIP-class
daily temperature and precipitation series against station
observations. (I am not citing a specific paper here — verify the
method reference independently before citing it elsewhere.)
