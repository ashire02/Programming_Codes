# NDVI Analysis — Nepal (Google Earth Engine)

Compute and visualise a **Normalized Difference Vegetation Index (NDVI)** map over Nepal using **Landsat 8 & 9 Surface Reflectance** imagery inside Google Earth Engine (GEE).

---

## Overview

| Item | Detail |
|---|---|
| **Platform** | Google Earth Engine (JavaScript API) |
| **AOI Asset** | `projects/ashire02/assets/Nepal` |
| **Satellites** | Landsat 8 OLI + Landsat 9 OLI (Collection 2, Tier 1, Surface Reflectance) |
| **Default period** | 2023-10-01 → 2024-04-30 (dry/growing season) |
| **Spatial resolution** | 30 m |
| **Composite method** | Pixel-wise median (cloud-masked) |

---

## NDVI Classification Scheme

The script uses a standard 6-class scheme widely adopted in vegetation remote sensing:

| Class | NDVI Range | Land Cover Type | Colour |
|---|---|---|---|
| 1 | < 0.0 | Water / Snow / Bare rock | Blue |
| 2 | 0.0 – 0.1 | Bare soil / Built-up / Urban | Red |
| 3 | 0.1 – 0.2 | Very sparse vegetation / Degraded land | Orange |
| 4 | 0.2 – 0.4 | Moderate vegetation (shrubs, grassland) | Light yellow-green |
| 5 | 0.4 – 0.6 | Dense vegetation (mixed forest, cropland) | Green |
| 6 | > 0.6 | Very dense / Healthy forest | Dark green |

---

## Script Features

- **Cloud & shadow masking** using Landsat `QA_PIXEL` bitmask (bits 3, 4, 5)
- **Radiometric scaling** of Collection 2 SR bands (× 0.0000275 − 0.2)
- **Sensor fusion** — Landsat 8 and Landsat 9 merged for maximum coverage
- **Median composite** for robust outlier rejection
- **Continuous NDVI layer** with RdYlGn colour ramp
- **Classified NDVI layer** (6 classes)
- **Interactive map legend** rendered with `ui.Panel`
- **Zonal statistics** printed to the console (mean, min, max, std dev)
- **Export blocks** (commented out) for Drive, Asset export

---

## How to Run

1. Open [Google Earth Engine Code Editor](https://code.earthengine.google.com/)
2. Create a new script and paste the contents of [`ndvi_nepal_landsat.js`](./ndvi_nepal_landsat.js)
3. Click **Run**

The map will centre on Nepal and display two layers:
- `NDVI (Median Composite)` — continuous gradient, enabled by default
- `NDVI Classification` — 6-class discrete map, toggle in the Layers panel

Console output shows scene count and NDVI statistics.

---

## Customisation

| Parameter | Location in script | What to change |
|---|---|---|
| Date range | `START_DATE` / `END_DATE` | Any season or multi-year period |
| Cloud threshold | `CLOUD_COVER` | Lower = stricter (fewer scenes) |
| Classification thresholds | Section 5 `where()` chain | Adjust per local land-cover context |
| Export settings | Section 10 | Uncomment the relevant `Export.*` block |

> **Tip — multi-year average:** Change `END_DATE` to a later year and switch `.median()` to `.mean()` for a long-term NDVI baseline.

---

## Outputs

| Output | Description |
|---|---|
| Map layer 1 | Continuous NDVI (−0.2 to 0.8) |
| Map layer 2 | Discrete classified NDVI (6 classes) |
| Console | Scene count + zonal statistics |
| Drive export | `Nepal_NDVI.tif` (30 m, EPSG:4326) — optional |
| Asset export | `projects/ashire02/assets/Nepal_NDVI` — optional |

---

## Dependencies

- GEE account with access to `projects/ashire02/assets/Nepal`
- No external libraries required

---

## References

- Rouse et al. (1974) — original NDVI formulation
- USGS Landsat Collection 2 Surface Reflectance product guide
- GEE Landsat algorithms: [developers.google.com/earth-engine/datasets/catalog/landsat](https://developers.google.com/earth-engine/datasets/catalog/landsat)
