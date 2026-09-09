# Geospatial and remote sensing

## Spatial data model

* **`admin_units`** — a hierarchy: country → state → district → sub-district → village, each with
  `MULTIPOLYGON(4326)` geometry, parent link, code, geodesic `area_km2` and centroid. Demo units are
  synthetic jittered cells flagged `is_demo`; real boundaries come from geoBoundaries (CC BY 4.0).
* **`gis_layers`** — thematic layers with a category, geometry type, `class_field` / `value_field`,
  a colour legend, temporal validity, licence and visibility.
* **`gis_features`** — individual geometries with a class, numeric value, validity dates, arbitrary
  JSON properties and the administrative unit they fall in (assigned by centroid on ingest).

All areas and distances are computed on the `geography` type, so results are in km²/metres rather
than degrees. Layer and feature geometry can be simplified on read (`?simplify=`) for map delivery.

## Spatial operations (`POST /gis/ops/...`)

| Operation | Input | Output |
| --- | --- | --- |
| `area` | unit, feature or geometry | geodesic area, perimeter, validity check |
| `intersection` | layer × (layer \| unit \| geometry) | intersected geometry, total area, area by class |
| `proximity` | layer, point, radius | features sorted by distance with distances in metres |
| `aggregate` | layer, level, metric (area/count/sum/mean) | per-unit totals and share of unit area |
| `hotspot` | layer, cell size | grid cells with z-scores classified hot/cold (MODELLED) |
| `boundary-select` | geometry, level, intersects/within | units touched, with overlap percentage |
| `affected-area` | geometry, buffer, layers | buffered zone, units affected, per-layer impact |

Each run is recorded in `spatial_runs` with inputs, duration and status; analytical operations also
produce a recommendation with an evidence trace. Read operations need `gis.view`; analyses need
`gis.analyze`.

## Remote sensing

* **Scene search** — a STAC connector (`STAC_ENDPOINT`) queries Sentinel/Landsat catalogues by bbox
  and date. Without an endpoint a demo adapter generates labelled synthetic reflectance so the
  pipeline is exercisable offline.
* **Products** — NDVI `(NIR−Red)/(NIR+Red)`, NDWI `(Green−NIR)/(Green+NIR)`,
  NDBI `(SWIR−NIR)/(SWIR+NIR)` and a rule-based land-cover classification, each stored with band
  statistics and labelled MODELLED.
* **Change detection** — NDVI difference between two scenes with thresholds at ±0.15 yields
  vegetation loss/gain, urban expansion and water change in km², plus a recommendation whose trace
  includes both scenes, the products and the model version.

Accuracy caveats are recorded on the model version and surfaced in the UI: thresholds are calibrated
per agro-climatic zone, built-up and barren classes are frequently confused in dry regions, and cloud
cover limits monsoon coverage.
