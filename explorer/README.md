# NYC Community District Profiles Explorer

Static single-page explorer for NYC's 59 residential community districts.

## Files

```text
explorer/
  index.html
  styles.css
  app.js
  data/
    cd_profiles.json
    nyc_cds.topojson
```

## Run locally

1. From the repo root, generate the slim JSON:

   ```bash
   python3 prepare_data.py
   ```

2. Serve the project with any static file server from the repo root, for example:

   ```bash
   python3 -m http.server 8000
   ```

3. Open `http://localhost:8000/explorer/`.

## Deploy

- GitHub Pages: publish the repo and set Pages to serve from the root or a docs-style branch/folder that includes `explorer/`.
- Vercel: import the repo as a static site from the repo root. `vercel.json` rewrites the site root to `explorer/`, so no build command is required.

### Vercel setup

1. Push the repo to GitHub.
2. In Vercel, choose `Add New Project` and import the repository.
3. Keep the project root as the repository root.
4. Leave these fields empty:
   - Build Command
   - Output Directory
   - Install Command
5. Deploy.

After deployment:

- `/` serves `explorer/index.html`
- `/data/*` resolves to `explorer/data/*`
- static assets like `styles.css`, `app.js`, and the TopoJSON file are served through the same rewrite rule

## TopoJSON source

- Source file: `nycehs/NYC_geography` GitHub repository, `CD.topo.json`
- Local file: `explorer/data/nyc_cds.topojson`
- Local acquisition: downloaded directly from the upstream simplified TopoJSON source
- Local simplification: none required; the upstream repository already distributes a simplified WGS84 TopoJSON
- Upstream processing note: the repository README says the file was transformed to WGS84 and simplified in Mapshaper

## TopoJSON inspection findings

- Object name: `collection`
- ID property name: `GEOCODE`
- Coordinate system: WGS84 longitude/latitude via `transform.translate` near `[-74.255665, 40.496101]`; the explorer uses `d3.geoMercator()`
- Feature count: 71 geometries in the file, filtered to 59 residential CDs by `GEOCODE`

## Data preparation

`prepare_data.py` reads `data/cd_profiles_updated.csv` and writes `explorer/data/cd_profiles.json`.

The output JSON contains:

- `profiles`: the 59 browser-facing profile objects used by the UI
- `medians`: citywide medians for the comparison metrics, plus a citywide age pyramid

The script derives:

- `cd_num` from `borocd`
- `name` as `"${borough} CD ${cd_num}"`
- `puma_partner` from `shared_puma_cd`
- citywide medians across all 59 CDs
- citywide male and female age-bin percentages

## Visible data provenance

- Demographics and household conditions: ACS 2020-2024 5-year estimates, aggregated from 2020 tracts
- Median household income: ACS 2020-2024 PUMA estimates with interpolation logic documented in the main repo README
- Land use and built environment: PLUTO 25v4
- Zoning shares and dominant zone: zoning extract documented in the main repo README
- Amenities: FacDB Oct 2025 counts, with `count_parks` from NYC Parks Properties Mar 2026
- Public safety: NYPD 2024 major felony counts and rates
- Geometry: NYC community districts from `nycehs/NYC_geography`, originally sourced from NYC DCP geography files

## Notes

- Choropleth mode uses `d3.scaleQuantile()` with five classes.
- Shared-PUMA districts display both the interpolated district estimate and the published PUMA median income.
- The map filters out non-residential joint-interest and auxiliary polygons before rendering.
