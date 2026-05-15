# NDVI Analysis — Nepal (Google Earth Engine)

Interactive NDVI mapping over Nepal using **Landsat 5 / 8 / 9** Surface Reflectance imagery, built with a fully interactive side-panel UI inside Google Earth Engine.

---

## Landsat Sensor Coverage

| Sensor | Collection | Red band | NIR band | Available in script |
|---|---|---|---|---|
| **Landsat 5 TM** | `LANDSAT/LT05/C02/T1_L2` | SR_B3 | SR_B4 | 1990 – May 2013 |
| **Landsat 8 OLI** | `LANDSAT/LC08/C02/T1_L2` | SR_B4 | SR_B5 | Apr 2013 – present |
| **Landsat 9 OLI-2** | `LANDSAT/LC09/C02/T1_L2` | SR_B4 | SR_B5 | Oct 2022 – present |

**Sensor selection is automatic** based on the year range you choose in the panel:
- Years ≤ 2013 → Landsat 5 included
- Years ≥ 2013 → Landsat 8 included
- Years ≥ 2022 → Landsat 9 included (from Oct 2022, one year after its Sep 2021 launch)

During overlap periods (e.g. Apr–May 2013, Oct 2022 onwards), multiple sensors are merged automatically.

---

## Side-Panel UI Controls

| Widget | Description |
|---|---|
| **Start / End Year** | Dropdowns, 1990 – 2025 |
| **Season** | Annual, Dry/Winter, Pre-Monsoon, Monsoon, Post-Monsoon |
| **Max Cloud Cover** | Slider (5 – 80 %) |
| **Composite Method** | Median (default), Mean, Max (greenest pixel) |
| **Display Layer** | Continuous NDVI, Classified NDVI, or Both |
| **Active Sensors** | Auto-updated on Run — shows which sensors are active |
| **▶ Run Analysis** | Builds collection, composites, adds map layers |
| **NDVI Statistics** | Mean / Min / Max / StdDev computed at 500 m (async, non-blocking) |
| **Export to Drive** | Submits a 30 m export task for continuous or classified NDVI |

---

## NDVI Classification Scheme

| Class | NDVI Range | Land Cover | Colour |
|---|---|---|---|
| 1 | < 0.0 | Water / Snow / Non-vegetated | Blue |
| 2 | 0.0 – 0.1 | Bare soil / Built-up | Red |
| 3 | 0.1 – 0.2 | Very sparse vegetation | Orange |
| 4 | 0.2 – 0.4 | Moderate vegetation (shrubs, grassland) | Light yellow-green |
| 5 | 0.4 – 0.6 | Dense vegetation (forest, cropland) | Green |
| 6 | > 0.6 | Very dense / Healthy forest | Dark green |

---

## Season Windows

| Season option | Months |
|---|---|
| Annual (Jan–Dec) | Full calendar year |
| Dry/Winter (Oct–Apr) | Post-monsoon + winter |
| Pre-Monsoon (Mar–May) | Spring dry season |
| Monsoon (Jun–Sep) | South Asian monsoon |
| Post-Monsoon (Oct–Nov) | Harvest season |

---

## How to Run

1. Open [Google Earth Engine Code Editor](https://code.earthengine.google.com/)
2. Create a new script and paste the full contents of [`ndvi_nepal_landsat.js`](./ndvi_nepal_landsat.js)
3. Click **Run** — the editor loads the split-panel UI
4. Set your year range, season, and options in the left panel
5. Click **▶ Run Analysis**

The map centres on Nepal. Statistics appear below the button once computed (async — the map does not wait for them).

---

## Why the Side Panel Prevents Browser Freezing

GEE's default script runs all `Map.addLayer` calls synchronously on page load. This script defers all computation until the **Run** button is clicked, and uses:
- `image.evaluate()` (async callback) for statistics — never blocks the UI thread
- Scale 500 m for stats (fast preview), 30 m only on export
- `bestEffort: true` to avoid quota timeouts
- `mapPanel.layers().reset()` to clear old layers cleanly before adding new ones

---

## Export

Click **⬇ Export to Drive** after running an analysis. The task appears in the **Tasks** tab (top-right corner of the Code Editor). Files are saved to your Google Drive under the folder `GEE_Exports` at 30 m resolution, EPSG:4326.

---

## Asset

AOI shapefile: `projects/ashire02/assets/Nepal`

---

## References

- Rouse et al. (1974) — NDVI formulation
- USGS Landsat Collection 2 Surface Reflectance product guide
- [GEE Landsat catalog](https://developers.google.com/earth-engine/datasets/catalog/landsat)
- Landsat 9 launch & operations — USGS/NASA (Sep 2021 launch, Feb 2022 science ops)
