/*
TopoJSON inspection findings for explorer/data/nyc_cds.topojson
1. Object name: collection
2. ID property name: GEOCODE
3. Coordinate system: WGS84 lon/lat via topology.transform.translate near [-74, 40], so use d3.geoMercator()
*/

const DEFAULT_BOROCD = 201;
const DATA_VERSION = "20260420t";
const TOPO_OBJECT_NAME = "collection";
const TOPO_ID_FIELD = "GEOCODE";
// White → yellow single-hue ramp (Bloomberg style)
const CHOROPLETH_COLORS = ["#fef9d9", "#fdf0a0", "#fce46a", "#fbda2e", "#f9ca00"];
const RESIDENTIAL_CD_RANGES = [
  [101, 112],
  [201, 212],
  [301, 318],
  [401, 414],
  [501, 503],
];
const BOROUGH_FILL = {
  Manhattan: "rgba(127, 119, 221, 0.26)",
  Bronx: "rgba(226, 118, 93, 0.26)",
  Brooklyn: "rgba(48, 148, 138, 0.26)",
  Queens: "rgba(223, 132, 160, 0.26)",
  "Staten Island": "rgba(217, 163, 75, 0.26)",
};
// Qualitative race palette — distinct hues, newsroom register
const RACE_COLORS = {
  Hispanic: "#e07640",
  White:    "#8c8c88",
  Black:    "#3d6fa8",
  Asian:    "#3d9970",
  Other:    "#9b6db5",
};
// Muted land-use palette (~20% less saturation than before)
const SLOPE_COLORS = {
  Residential: "#5a7339",
  Commercial: "#c79a3e",
  Manufacturing: "#6b64b8",
  Park: "#397a5a",
  Other: "#76756f",
};
const METRICS = [
  { key: "mdn_hh_inc_interp", label: "Median HH income", format: "currency", better: "higher" },
  { key: "poverty_rate", label: "Poverty rate", format: "percent", better: "lower" },
  { key: "pct_hh_rent_burd", label: "Rent burden", format: "percent", better: "lower" },
  { key: "pct_bach_deg", label: "Bachelor's +", format: "percent", better: "higher" },
  { key: "pct_foreign_born", label: "Foreign born", format: "percent", better: "neutral" },
  { key: "lep_rate", label: "LEP rate", format: "percent", better: "lower" },
  { key: "under18_rate", label: "Under 18", format: "percent", better: "neutral" },
  { key: "over65_rate", label: "Over 65", format: "percent", better: "neutral" },
  { key: "crime_per_1000", label: "Crime per 1,000", format: "number1", better: "lower" },
];
const ECONOMIC_ROWS = [
  {
    key: "mdn_hh_inc_interp",
    label: "Median HH income",
    format: "currency",
    medianKey: "mdn_hh_inc_interp",
    better: "higher",
    description: "Estimated median household income for the community district. Half of households earn more and half earn less.",
  },
  {
    key: "poverty_rate",
    label: "Poverty rate",
    format: "percent",
    medianKey: "poverty_rate",
    better: "lower",
    moeKey: "moe_poverty_rate",
    description: "Share of residents with income below the federal poverty threshold, based on ACS household and family definitions.",
  },
  {
    key: "pct_hh_rent_burd",
    label: "Rent burden",
    format: "percent",
    medianKey: "pct_hh_rent_burd",
    better: "lower",
    moeKey: "moe_hh_rent_burd",
    description: "Share of renter households spending 30 percent or more of income on rent.",
  },
  {
    key: "pct_bach_deg",
    label: "Bachelor's+",
    format: "percent",
    medianKey: "pct_bach_deg",
    better: "higher",
    moeKey: "moe_bach_deg",
    description: "Share of residents age 25 and older with a bachelor's degree, graduate degree, or professional degree.",
  },
  {
    key: "unemployment",
    label: "Unemployment",
    format: "percent",
    medianKey: "unemployment",
    better: "lower",
    moeKey: "moe_unemployment",
    description: "Share of the civilian labor force that is unemployed and actively looking for work.",
  },
  {
    key: "lep_rate",
    label: "Limited English proficiency",
    format: "percent",
    medianKey: "lep_rate",
    better: "lower",
    description: "Share of residents age 5 and older who speak English less than 'very well'.",
  },
];
const AGE_BINS = [
  "Under 5",
  "5-9",
  "10-14",
  "15-19",
  "20-24",
  "25-29",
  "30-34",
  "35-39",
  "40-44",
  "45-49",
  "50-54",
  "55-59",
  "60-64",
  "65-69",
  "70-74",
  "75-79",
  "80-84",
  "85+",
];
const AMENITY_TILES = [
  { key: "count_parks", label: "Parks" },
  { key: "count_public_schools", label: "Public schools" },
  { key: "count_libraries", label: "Libraries" },
  { key: "count_hosp_clinic", label: "Hospitals & clinics" },
  { key: "count_day_care", label: "Day cares" },
  { key: "count_senior_services", label: "Senior service sites" },
];

let zoomBehavior = null;
let mapPathGenerator = null;

const TABS = [
  { key: "demographics", label: "People" },
  { key: "economy",      label: "Economy" },
  { key: "built",        label: "Land use" },
  { key: "civic",        label: "Places" },
];

const state = {
  mode: "neutral",
  metricKey: METRICS[0].key,
  selectedBoroCD: null,
  hoveredBoroCD: null,
  features: [],
  profiles: [],
  profilesByBoroCD: new Map(),
  medians: null,
  colorScale: null,
  mapSelection: null,
  hitAreaSelection: null,
  activeTab: "demographics",
};

const chipRow = document.querySelector(".chip-row");
const detailPanel = document.getElementById("detail-panel");
const mapLabel = document.getElementById("map-label");
const legend = document.querySelector(".legend");
const svg = d3.select("#district-map");

init().catch((error) => {
  console.error(error);
  detailPanel.innerHTML = `<div class="empty-state">The explorer could not load its data files.</div>`;
});

async function init() {
  renderMetricChips();
  bindModeButtons();

  const [profileBundle, topo] = await Promise.all([
    fetch(`./data/cd_profiles.json?v=${DATA_VERSION}`).then((response) => response.json()),
    fetch(`./data/nyc_cds.topojson?v=${DATA_VERSION}`).then((response) => response.json()),
  ]);

  state.profiles = profileBundle.profiles;
  state.medians = profileBundle.medians;
  state.profilesByBoroCD = new Map(state.profiles.map((profile) => [profile.borocd, profile]));

  const features = topojson
    .feature(topo, topo.objects[TOPO_OBJECT_NAME])
    .features
    .filter((feature) => isResidentialCD(feature.properties[TOPO_ID_FIELD]));

  if (features.length !== 59) {
    throw new Error(`Expected 59 residential CDs after filtering, found ${features.length}`);
  }

  state.features = features;
  logJoinDifferences(features, state.profilesByBoroCD);
  drawMap(features);
  updateChoroplethScale();
  deselectDistrict();
}

function isResidentialCD(id) {
  return RESIDENTIAL_CD_RANGES.some(([min, max]) => id >= min && id <= max);
}

function logJoinDifferences(features, profilesByBoroCD) {
  const mapIds = new Set(features.map((feature) => feature.properties[TOPO_ID_FIELD]));
  const profileIds = new Set(profilesByBoroCD.keys());
  const missingProfiles = [...mapIds].filter((id) => !profileIds.has(id));
  const missingGeometry = [...profileIds].filter((id) => !mapIds.has(id));

  if (missingProfiles.length) {
    console.warn("Map paths missing profile data:", missingProfiles);
  }
  if (missingGeometry.length) {
    console.warn("Profiles missing geometry:", missingGeometry);
  }
}

function drawMap(features) {
  const width = 680;
  const height = 560;
  const projection = d3.geoMercator().fitSize([width, height], {
    type: "FeatureCollection",
    features,
  });
  const path = d3.geoPath(projection);
  mapPathGenerator = path;
  const zoomLayer = svg.append("g").attr("class", "map-zoom-layer");
  const mapLayer = zoomLayer.append("g").attr("class", "district-layer");
  const hitAreaLayer = zoomLayer.append("g").attr("class", "district-hit-layer");
  const labelLayer = zoomLayer.append("g").attr("class", "district-label-layer");

  state.mapSelection = mapLayer
    .selectAll("path")
    .data(features)
    .join("path")
    .attr("class", "map-path")
    .attr("d", path)
    .attr("data-borocd", (feature) => feature.properties[TOPO_ID_FIELD])
    .attr("tabindex", 0)
    .attr("aria-label", (feature) => {
      const profile = state.profilesByBoroCD.get(feature.properties[TOPO_ID_FIELD]);
      return profile ? `${profile.name}, ${profile.neighborhoods}` : `Community district ${feature.properties[TOPO_ID_FIELD]}`;
    })
    .attr("fill", (feature) => neutralFill(feature.properties[TOPO_ID_FIELD]))
    .attr("stroke", "#ffffff")
    .attr("stroke-width", 1);

  state.hitAreaSelection = hitAreaLayer
    .selectAll("path")
    .data(features)
    .join("path")
    .attr("class", "district-hit-area")
    .attr("d", path)
    .attr("fill", "transparent")
    .attr("stroke", "none")
    .attr("data-borocd", (feature) => feature.properties[TOPO_ID_FIELD])
    .attr("tabindex", 0)
    .attr("aria-label", (feature) => {
      const profile = state.profilesByBoroCD.get(feature.properties[TOPO_ID_FIELD]);
      return profile ? `${profile.name}, ${profile.neighborhoods}` : `Community district ${feature.properties[TOPO_ID_FIELD]}`;
    })
    .on("mouseenter", (_, feature) => {
      setHoveredDistrict(feature.properties[TOPO_ID_FIELD]);
    })
    .on("mouseleave", () => {
      clearHoveredDistrict();
    })
    .on("click", (event, feature) => {
      event.stopPropagation();
      const borocd = feature.properties[TOPO_ID_FIELD];
      if (borocd === state.selectedBoroCD) {
        deselectDistrict();
      } else {
        collapseIntro();
        selectDistrict(borocd);
      }
    })
    .on("focus", (_, feature) => {
      setHoveredDistrict(feature.properties[TOPO_ID_FIELD]);
    })
    .on("blur", () => {
      clearHoveredDistrict();
    })
    .on("keydown", (event, feature) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        const borocd = feature.properties[TOPO_ID_FIELD];
        if (borocd === state.selectedBoroCD) {
          deselectDistrict();
        } else {
          collapseIntro();
          selectDistrict(borocd);
        }
      }
    });

  labelLayer
    .selectAll("text")
    .data(features)
    .join("text")
    .attr("class", "district-label")
    .attr("x", (feature) => path.centroid(feature)[0])
    .attr("y", (feature) => path.centroid(feature)[1])
    .attr("text-anchor", "middle")
    .attr("dy", "0.35em")
    .text((feature) => feature.properties[TOPO_ID_FIELD] % 100);

  zoomBehavior = d3
    .zoom()
    .scaleExtent([1, 5])
    .translateExtent([
      [-60, -60],
      [width + 60, height + 60],
    ])
    .extent([
      [0, 0],
      [width, height],
    ])
    .on("zoom", (event) => {
      zoomLayer.attr("transform", event.transform);
    });

  svg.call(zoomBehavior);

  // Click on empty map background deselects
  svg.on("click", () => deselectDistrict());
}

function zoomToDistrict(borocd) {
  if (!zoomBehavior || !mapPathGenerator) return;
  const feature = state.features.find((f) => f.properties[TOPO_ID_FIELD] === borocd);
  if (!feature) return;

  const width = 680;
  const height = 560;
  const [[x0, y0], [x1, y1]] = mapPathGenerator.bounds(feature);
  const dx = x1 - x0;
  const dy = y1 - y0;
  const cx = (x0 + x1) / 2;
  const cy = (y0 + y1) / 2;
  const scale = Math.min(5, 0.72 / Math.max(dx / width, dy / height));

  svg.transition()
    .duration(650)
    .ease(d3.easeCubicOut)
    .call(
      zoomBehavior.transform,
      d3.zoomIdentity
        .translate(width / 2, height / 2)
        .scale(scale)
        .translate(-cx, -cy),
    );
}

function setHoveredDistrict(borocd) {
  state.hoveredBoroCD = borocd;
  updateMapHoverLabel(borocd);
  applyMapStyles();
}

function clearHoveredDistrict() {
  state.hoveredBoroCD = null;
  updateMapHoverLabel(state.selectedBoroCD);
  applyMapStyles();
}

function selectDistrict(borocd, { zoom = true } = {}) {
  const profile = state.profilesByBoroCD.get(borocd);
  if (!profile) {
    console.warn(`No profile found for borocd ${borocd}`);
    return;
  }

  state.selectedBoroCD = borocd;
  updateMapHoverLabel(borocd);
  applyMapStyles();
  renderPanel(profile);
  if (zoom) zoomToDistrict(borocd);
}

function deselectDistrict() {
  state.selectedBoroCD = null;
  updateMapHoverLabel(null);
  detailPanel.innerHTML = `
    <div class="panel-empty-hint">
      <p class="panel-empty-prompt">Click any district on the map to read its profile.</p>
      <p class="panel-empty-body">Each profile covers demographics, economic conditions, land use, and civic infrastructure — drawn from the American Community Survey, PLUTO, and NYPD complaint data.</p>
    </div>
  `;
  applyMapStyles();
}

function applyMapStyles() {
  const activeBoroCD = state.hoveredBoroCD ?? state.selectedBoroCD;
  state.mapSelection
    .attr("fill", (feature) => fillForFeature(feature.properties[TOPO_ID_FIELD]))
    .attr("stroke", (feature) => {
      const borocd = feature.properties[TOPO_ID_FIELD];
      return borocd === state.selectedBoroCD ? "#1a1a1a" : "#ffffff";
    })
    .attr("stroke-width", (feature) => {
      const borocd = feature.properties[TOPO_ID_FIELD];
      if (borocd === state.selectedBoroCD || borocd === activeBoroCD) {
        return 2.5;
      }
      return 1;
    })
    .classed("is-muted", (feature) => {
      if (state.mode !== "choropleth") return false;
      if (state.hoveredBoroCD === null) return false;
      return feature.properties[TOPO_ID_FIELD] !== state.hoveredBoroCD;
    });

  const selectedPath = state.mapSelection.filter((feature) => feature.properties[TOPO_ID_FIELD] === state.selectedBoroCD);
  if (!selectedPath.empty()) selectedPath.raise();
  if (state.hoveredBoroCD !== null) {
    const hoveredPath = state.mapSelection.filter((feature) => feature.properties[TOPO_ID_FIELD] === state.hoveredBoroCD);
    if (!hoveredPath.empty()) hoveredPath.raise();
  }
}

function neutralFill(borocd) {
  const profile = state.profilesByBoroCD.get(borocd);
  return profile ? BOROUGH_FILL[profile.borough] : "rgba(136,135,128,0.2)";
}

function fillForFeature(borocd) {
  const profile = state.profilesByBoroCD.get(borocd);
  if (!profile) {
    return "rgba(136,135,128,0.12)";
  }
  if (state.mode === "neutral") {
    return BOROUGH_FILL[profile.borough];
  }
  return state.colorScale(profile[state.metricKey]);
}

function renderMetricChips() {
  chipRow.innerHTML = METRICS.map(
    (metric) =>
      `<button type="button" class="metric-chip${metric.key === state.metricKey ? " is-active" : ""}" data-metric="${metric.key}">${metric.label}</button>`,
  ).join("");

  chipRow.querySelectorAll(".metric-chip").forEach((button) => {
    button.addEventListener("click", () => {
      collapseIntro();
      state.metricKey = button.dataset.metric;
      updateChoroplethScale();
      renderMetricChips();
      applyMapStyles();
    });
  });
}

function bindModeButtons() {
  document.querySelectorAll(".mode-button").forEach((button) => {
    button.addEventListener("click", () => {
      collapseIntro();
      state.mode = button.dataset.mode;
      document.querySelectorAll(".mode-button").forEach((target) => {
        target.classList.toggle("is-active", target === button);
      });
      chipRow.classList.toggle("is-hidden", state.mode !== "choropleth");
      legend.classList.toggle("is-hidden", state.mode !== "choropleth");
      updateChoroplethScale();
      applyMapStyles();
    });
  });
}

function updateChoroplethScale() {
  const values = state.profiles.map((profile) => profile[state.metricKey]).filter((value) => Number.isFinite(value));
  state.colorScale = d3.scaleQuantile(values, CHOROPLETH_COLORS).unknown("#d9d7cf");
  renderLegend();
}

function renderLegend() {
  if (state.mode !== "choropleth") {
    legend.innerHTML = "";
    return;
  }

  const metric = METRICS.find((item) => item.key === state.metricKey);
  const quantiles = state.colorScale.quantiles();
  const thresholds = [d3.min(state.colorScale.domain()), ...quantiles, d3.max(state.colorScale.domain())];
  const lastIndex = state.colorScale.range().length - 1;
  const labels = state.colorScale.range().map((_, index) => {
    const val = compactLegendValue(thresholds[index], metric);
    return index === lastIndex ? `≥${val}` : val;
  });

  legend.innerHTML = `
    <p class="legend-caption">${metric.label.toUpperCase()}, 2020\u20132024</p>
    <div class="legend-scale">
      ${state.colorScale.range().map((color) => `<span class="legend-swatch" style="background:${color}"></span>`).join("")}
    </div>
    <div class="legend-labels">
      ${labels.map((label) => `<span>${label}</span>`).join("")}
    </div>
  `;
}

function compactLegendValue(value, metric) {
  if (!Number.isFinite(value)) {
    return "NA";
  }
  if (metric.format === "currency") {
    return `$${Math.round(value / 1000)}k`;
  }
  if (metric.format === "number1") {
    return d3.format(".1f")(value);
  }
  return `${Math.round(value)}%`;
}

function updateMapHoverLabel(borocd) {
  if (!borocd) {
    mapLabel.textContent = "NYC Community Districts";
    return;
  }
  const profile = state.profilesByBoroCD.get(borocd);
  if (!profile) return;
  mapLabel.textContent = profile.name;
}

function renderPanel(profile) {
  detailPanel.innerHTML = "";
  detailPanel.scrollTop = 0;

  // Intro always visible above tabs
  detailPanel.append(sectionIntro(profile));

  // Tab nav
  const nav = document.createElement("div");
  nav.className = "tab-nav";
  nav.setAttribute("role", "tablist");

  const sectionFns = {
    demographics: sectionWhoLivesHere,
    economy:      sectionEconomic,
    built:        sectionBuiltEnvironment,
    civic:        sectionAmenities,
  };

  TABS.forEach(({ key, label }) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "tab-button" + (key === state.activeTab ? " is-active" : "");
    btn.dataset.tab = key;
    btn.setAttribute("role", "tab");
    btn.setAttribute("aria-selected", key === state.activeTab ? "true" : "false");
    btn.textContent = label;
    btn.addEventListener("click", () => {
      state.activeTab = key;
      detailPanel.querySelectorAll(".tab-button").forEach((b) => {
        b.classList.toggle("is-active", b.dataset.tab === key);
        b.setAttribute("aria-selected", b.dataset.tab === key ? "true" : "false");
      });
      detailPanel.querySelectorAll(".tab-panel").forEach((p) => {
        p.classList.toggle("is-active", p.dataset.tab === key);
      });
    });
    nav.append(btn);
  });
  detailPanel.append(nav);

  // Tab panels — all rendered, only active is visible
  TABS.forEach(({ key }) => {
    const panel = document.createElement("div");
    panel.className = "tab-panel" + (key === state.activeTab ? " is-active" : "");
    panel.dataset.tab = key;
    panel.setAttribute("role", "tabpanel");
    panel.append(sectionFns[key](profile));
    detailPanel.append(panel);
  });
}

function collapseIntro() {
  const intro = document.getElementById("page-intro");
  if (intro) {
    intro.classList.add("is-collapsed");
  }
}

function calculateYouthShare(profile) {
  const bins = ["under_5", "5_9", "10_14", "15_19"];
  const count = bins.reduce((sum, bin) => sum + (profile[`male_${bin}`] || 0) + (profile[`female_${bin}`] || 0), 0);
  return profile.pop_acs ? (count / profile.pop_acs) * 100 : 0;
}

function generateLede(profile, medians) {
  const cityIncome = medians.mdn_hh_inc_interp;
  const hoods = profile.name; // "Manhattan CD 9", not the long neighborhood list

  // Angle 1: Extreme poverty
  if (profile.poverty_rate > 35) {
    const pct = Math.round(profile.poverty_rate);
    const incomeStr = formatValue(profile.mdn_hh_inc_interp, "currency");
    return `${pct} percent of ${hoods} residents live below the federal poverty line. The median household earns ${incomeStr} a year, among the lower figures in the city.`;
  }

  // Angle 1b: Extreme wealth
  if (profile.mdn_hh_inc_interp > 150000) {
    const incomeStr = formatValue(profile.mdn_hh_inc_interp, "currency");
    const bachPct = Math.round(profile.pct_bach_deg);
    if (profile.mdn_hh_inc_interp > 180000) {
      return `The median household in ${hoods} earns ${incomeStr} a year, making it one of the wealthiest community districts in New York${bachPct > 65 ? `; ${bachPct} percent of adults hold a college degree` : ""}.`;
    }
    return `${hoods} ranks among the more prosperous parts of the city. The median household earns ${incomeStr}${bachPct > 55 ? `, and ${bachPct} percent of adults hold a college degree` : ""}.`;
  }

  // Angle 2a: Strong racial concentration
  const raceGroups = [
    { name: "Hispanic", value: profile.pct_hispanic },
    { name: "white", value: profile.pct_white_nh },
    { name: "Black", value: profile.pct_black_nh },
    { name: "Asian", value: profile.pct_asian_nh },
  ];
  const dominant = raceGroups.find((r) => r.value > 65);
  if (dominant) {
    const pct = Math.round(dominant.value);
    const incomeStr = formatValue(profile.mdn_hh_inc_interp, "currency");
    return `${pct} percent of ${hoods} residents are ${dominant.name}, one of the highest concentrations in any New York community district. The median household earns ${incomeStr}.`;
  }

  // Angle 2b: High foreign-born share
  if (profile.pct_foreign_born > 45) {
    const pct = Math.round(profile.pct_foreign_born);
    const incomeStr = formatValue(profile.mdn_hh_inc_interp, "currency");
    return `${pct} percent of ${hoods} residents were born outside the United States \u2014 one of the highest foreign-born shares in any community district. The median household earns ${incomeStr}.`;
  }

  // Angle 3a: Old population
  if (profile.over65_rate > 20) {
    const pct = Math.round(profile.over65_rate);
    const incomeStr = formatValue(profile.mdn_hh_inc_interp, "currency");
    return `${pct} percent of ${hoods} residents are 65 or older, well above the citywide share. The median household earns ${incomeStr}.`;
  }

  // Angle 3b: Young population
  const youthPct = calculateYouthShare(profile);
  if (youthPct > 28) {
    const pct = Math.round(youthPct);
    const incomeStr = formatValue(profile.mdn_hh_inc_interp, "currency");
    return `${pct} percent of ${hoods} residents are under 20, among the higher youth shares in the city. The median household earns ${incomeStr}.`;
  }

  // Angle 4: Manufacturing-heavy zoning
  if (profile.pct_lot_area_zoned_manufacturing > 25) {
    const pct = Math.round(profile.pct_lot_area_zoned_manufacturing);
    return `${pct} percent of ${hoods}\u2019 lot area is still zoned for manufacturing, reflecting an industrial legacy that has come under steady rezoning pressure as the district\u2019s population has grown.`;
  }

  // Fallback: income-anchored description
  const incomeStr = formatValue(profile.mdn_hh_inc_interp, "currency");
  if (cityIncome && profile.mdn_hh_inc_interp) {
    const ratio = profile.mdn_hh_inc_interp / cityIncome;
    const context = ratio > 1.15 ? "above the citywide median" : ratio < 0.85 ? "below the citywide median" : "near the citywide median";
    const secondSentence = profile.pct_foreign_born > 30
      ? `About ${Math.round(profile.pct_foreign_born)} percent of residents were born outside the United States.`
      : `Its ${d3.format(",")(profile.pop_acs)} residents span a broad range of the city\u2019s demographic mix.`;
    return `${hoods} has a median household income of ${incomeStr} \u2014 ${context}. ${secondSentence}`;
  }
  return `${hoods} is home to ${d3.format(",")(profile.pop_acs)} residents. The median household earns ${incomeStr} a year.`;
}

// Wrap currency and percentage figures in a bold <span> for the lede
function boldFigs(text) {
  return text
    .replace(/(\$[\d,]+(?:\.\d+)?(?:k|K)?)/g, '<span class="fig">$1</span>')
    .replace(/(\d+(?:\.\d+)?)\s+(percent)/g, '<span class="fig">$1</span> $2')
    .replace(/(\d+(?:\.\d+)?)(%)/g, '<span class="fig">$1</span>%');
}

function sectionIntro(profile) {
  const wrapper = document.createElement("section");
  wrapper.className = "section-block";
  const lede = generateLede(profile, state.medians);
  const ledeHtml = lede ? `<p class="district-lede">${boldFigs(lede)}</p>` : "";
  wrapper.innerHTML = `
    <h2 class="district-name">${profile.name}</h2>
    <p class="district-neighborhoods">${profile.neighborhoods}</p>
    ${ledeHtml}
  `;
  return wrapper;
}

function sectionWhoLivesHere(profile) {
  const section = buildSection("Who lives here");
  section.innerHTML += `
    <div class="metric-grid">
      <article class="metric-card">
        <div class="metric-card-label" data-tooltip="ACS 2020–2024 5-year estimate">Population</div>
        <div class="metric-card-value">${formatValue(profile.pop_acs, "integer")}</div>
      </article>
      <article class="metric-card">
        <div class="metric-card-label" data-tooltip="ACS 2020–2024 5-year estimate">Foreign born</div>
        <div class="metric-card-value">${formatValue(profile.pct_foreign_born, "percent")}</div>
      </article>
      <article class="metric-card">
        <div class="metric-card-label" data-tooltip="Share of residents under age 18, ACS 2020–2024.">Under 18</div>
        <div class="metric-card-value">${formatValue(profile.under18_rate, "percent")}</div>
      </article>
      <article class="metric-card">
        <div class="metric-card-label" data-tooltip="Share of residents age 65 and older, ACS 2020–2024.">65 and over</div>
        <div class="metric-card-value">${formatValue(profile.over65_rate, "percent")}</div>
      </article>
    </div>
    <div class="chart-wrap">
      <div class="pyramid-shell">
        <div id="pyramid-chart"></div>
      </div>
      <div class="legend-inline">
        <span class="legend-inline-item"><span class="dot" style="background:#1a1a1a; opacity:1"></span>Male</span>
        <span class="legend-inline-item"><span class="dot" style="background:#1a1a1a; opacity:0.42"></span>Female</span>
        <span class="legend-inline-item"><span class="dot" style="background:transparent; border:1px dashed #7a7a77"></span>Citywide</span>
      </div>
      <p class="chart-caption">Population by age and sex.</p>
    </div>
    <div class="chart-wrap" style="margin-top:20px">
      <div class="race-track">
        ${raceSegments(profile)}
      </div>
      <div class="swatch-list">
        ${raceLegend(profile)}
      </div>
      <p class="chart-caption">Population by race and Hispanic origin.</p>
    </div>
  `;
  drawAgePyramid(section.querySelector("#pyramid-chart"), profile, state.medians.citywide_pyramid);
  return section;
}

function sectionEconomic(profile) {
  const section = buildSection("Economic conditions");
  const rows = ECONOMIC_ROWS.map((row) => {
    if (row.key === "mdn_hh_inc_interp" && profile.shared_puma) {
      return { ...row, description: `${row.description} Covers this CD and ${profile.puma_partner} — income is published at the PUMA level and the figure shown is an estimate.` };
    }
    return row;
  });
  const rowsMarkup = rows.map((row) => renderStatRow(profile, row)).join("");
  const comparison = comparisonText(profile.crime_per_1000, state.medians.crime_per_1000, "number1", "lower");
  const safetyRow = `
    <div class="stat-row">
      <div class="stat-label" data-tooltip="Reported major felony incidents per 1,000 residents, using NYPD 2024 counts for the seven major felony categories.">Major felonies / 1,000</div>
      <div class="stat-value-group">
        <div class="stat-value">${formatValue(profile.crime_per_1000, "number1")}</div>
        <div class="comparison-text ${comparison.className}">${comparison.text}</div>
      </div>
    </div>
  `;
  section.innerHTML += `<div class="stat-list">${rowsMarkup}${safetyRow}</div>`;
  return section;
}

function sectionBuiltEnvironment(profile) {
  const section = buildSection("Built environment");
  section.innerHTML += `
    <p class="chart-description">Each row shows what share of the district's total lot area falls into that land-use category. <strong>Filled marks</strong> reflect how lots are actually used today; <strong>outlined marks</strong> show the official zoning designation. A gap between the two indicates that current use and zoning designation don't align.</p>
    <div class="chart-wrap">
      <div class="chart-dot-legend">
        <span class="chart-dot-legend-item"><span class="chart-dot-legend-swatch current"></span>Current use</span>
        <span class="chart-dot-legend-item"><span class="chart-dot-legend-swatch zoning"></span>Zoning</span>
      </div>
      <div id="slope-chart"></div>
      <p class="chart-caption">Share of total lot area, by land-use category.</p>
    </div>
  `;
  drawSlopeChart(section.querySelector("#slope-chart"), profile);
  return section;
}

function sectionAmenities(profile) {
  const section = buildSection("Civic places");
  section.innerHTML += `
    <div class="amenity-grid">
      ${AMENITY_TILES.map((tile) => amenityTile(profile, tile)).join("")}
    </div>
    <p class="chart-caption">Raw facility counts by type.</p>
  `;
  return section;
}

function buildSection(title) {
  const section = document.createElement("section");
  section.className = "section-block";
  section.innerHTML = `
    <div class="section-header">
      <div class="section-header-bar"></div>
      <h3 class="section-header-label">${title.toUpperCase()}</h3>
    </div>
  `;
  return section;
}

function renderStatRow(profile, row) {
  const value = profile[row.key];
  const comparison = comparisonText(value, state.medians[row.medianKey], row.format, row.better);
  const secondary = "";

  return `
    <div class="stat-row">
      <div class="stat-label" data-tooltip="${row.description}">${row.label}</div>
      <div class="stat-value-group">
        <div class="stat-value">${formatValue(value, row.format)}</div>
        <div class="comparison-text ${comparison.className}">${comparison.text}</div>
        ${secondary}
      </div>
    </div>
  `;
}

function hasHighRelativeMoe(value, moe) {
  if (!Number.isFinite(value) || !Number.isFinite(moe) || value === 0) {
    return false;
  }
  return Math.abs(moe / value) > 0.15;
}

function comparisonText(value, cityValue, format, better = "neutral") {
  if (!Number.isFinite(value) || !Number.isFinite(cityValue) || cityValue === 0) {
    return { text: "No citywide comparison", className: "comparison-neutral" };
  }
  const difference = value - cityValue;
  const comparisonClassName = classifyComparison(difference, better);
  if (format === "currency") {
    if (Math.abs(difference) < 2500) {
      return { text: "In line with city", className: "comparison-neutral" };
    }
    return {
      text: `${difference > 0 ? "+" : "-"}${formatCompactCurrency(Math.abs(difference))} vs city`,
      className: comparisonClassName,
    };
  }

  if (format === "percent") {
    if (Math.abs(difference) < 0.75) {
      return { text: "In line with city", className: "comparison-neutral" };
    }
    return {
      text: `${difference > 0 ? "+" : "-"}${d3.format(".1f")(Math.abs(difference))} pp vs city`,
      className: comparisonClassName,
    };
  }

  if (format === "number1") {
    if (Math.abs(difference) < 0.3) {
      return { text: "In line with city", className: "comparison-neutral" };
    }
    return {
      text: `${difference > 0 ? "+" : "-"}${d3.format(".1f")(Math.abs(difference))} vs city`,
      className: comparisonClassName,
    };
  }

  const delta = (difference / cityValue) * 100;
  if (Math.abs(delta) < 3) {
    return { text: "In line with city", className: "comparison-neutral" };
  }
  return {
    text: `${delta > 0 ? "+" : ""}${Math.round(delta)}% vs city`,
    className: comparisonClassName,
  };
}

function classifyComparison(difference, better) {
  if (difference === 0 || better === "neutral") {
    return "comparison-neutral";
  }
  if (better === "higher") {
    return difference > 0 ? "comparison-good" : "comparison-bad";
  }
  if (better === "lower") {
    return difference < 0 ? "comparison-good" : "comparison-bad";
  }
  return difference > 0 ? "comparison-good" : "comparison-bad";
}

function slopeValues(profile) {
  const residentialUse =
    profile.pct_lot_area_res_1_2_family_bldg +
    profile.pct_lot_area_res_multifamily_walkup +
    profile.pct_lot_area_res_multifamily_elevator;
  const commercialUse = profile.pct_lot_area_commercial_office + profile.pct_lot_area_mixed_use;
  const manufacturingUse = profile.pct_lot_area_industrial_manufacturing;
  const parkUse = profile.pct_lot_area_open_space;
  const otherUse =
    profile.pct_lot_area_transportation_utility +
    profile.pct_lot_area_public_facility_institution +
    profile.pct_lot_area_parking +
    profile.pct_lot_area_vacant +
    profile.pct_lot_area_other_no_data;

  return [
    { label: "Residential", use: residentialUse, zone: profile.pct_lot_area_zoned_residential, color: SLOPE_COLORS.Residential },
    { label: "Commercial", use: commercialUse, zone: profile.pct_lot_area_zoned_commercial, color: SLOPE_COLORS.Commercial },
    { label: "Manufacturing", use: manufacturingUse, zone: profile.pct_lot_area_zoned_manufacturing, color: SLOPE_COLORS.Manufacturing },
    { label: "Park", use: parkUse, zone: profile.pct_lot_area_zoned_park, color: SLOPE_COLORS.Park },
    { label: "Other", use: otherUse, zone: profile.pct_lot_area_zoned_other + profile.pct_lot_area_zoned_unzoned, color: SLOPE_COLORS.Other },
  ].map((item) => ({ ...item, delta: item.use - item.zone, absDelta: Math.abs(item.use - item.zone) }));
}

function slopeHeadline(profile) {
  const [largest] = slopeValues(profile).sort((a, b) => b.absDelta - a.absDelta);
  if (!largest || largest.absDelta < 10) {
    return "Current land use and zoning designation are closely aligned.";
  }
  if (largest.delta > 0) {
    return `${largest.label} use exceeds ${largest.label.toLowerCase()} zoning by ${Math.round(largest.absDelta)}pp`;
  }
  return `${largest.label} zoning exceeds ${largest.label.toLowerCase()} use by ${Math.round(largest.absDelta)}pp`;
}

function drawSlopeChart(container, profile) {
  const data = slopeValues(profile);
  const width = 388;
  const height = 248;
  const margin = { top: 20, right: 12, bottom: 24, left: 94 };
  const x = d3.scaleLinear().domain([0, 100]).range([margin.left, width - margin.right]);
  const y = d3
    .scalePoint()
    .domain(data.map((item) => item.label))
    .range([margin.top, height - margin.bottom])
    .padding(0.5);
  const ticks = [0, 25, 50, 75, 100];
  const dotR = 4.2;

  const root = d3.select(container).html("").append("svg").attr("viewBox", `0 0 ${width} ${height}`).attr("width", "100%");

  ticks.forEach((tick) => {
    root
      .append("line")
      .attr("class", "dumbbell-grid")
      .attr("x1", x(tick))
      .attr("x2", x(tick))
      .attr("y1", margin.top - 10)
      .attr("y2", height - margin.bottom + 6);

    root
      .append("text")
      .attr("class", "axis-label")
      .attr("x", x(tick))
      .attr("y", 12)
      .attr("text-anchor", "middle")
      .text(`${tick}%`);
  });

  data.forEach((item) => {
    const rowY = y(item.label);
    const useX = x(item.use);
    const zoneX = x(item.zone);
    const leftX = Math.min(useX, zoneX);
    const rightX = Math.max(useX, zoneX);

    root
      .append("text")
      .attr("class", "dumbbell-category")
      .attr("x", margin.left - 12)
      .attr("y", rowY + 4)
      .attr("text-anchor", "end")
      .text(item.label);

    root
      .append("line")
      .attr("class", "dumbbell-line")
      .attr("x1", leftX)
      .attr("x2", rightX)
      .attr("y1", rowY)
      .attr("y2", rowY)
      .attr("stroke", item.color)
      .attr("stroke-width", 2);

    // Filled square — current use
    root
      .append("rect")
      .attr("class", "dumbbell-point use")
      .attr("x", useX - dotR / 2)
      .attr("y", rowY - dotR / 2)
      .attr("width", dotR)
      .attr("height", dotR)
      .attr("fill", item.color);

    // Outlined square — zoning
    root
      .append("rect")
      .attr("class", "dumbbell-point zone")
      .attr("x", zoneX - dotR / 2)
      .attr("y", rowY - dotR / 2)
      .attr("width", dotR)
      .attr("height", dotR)
      .attr("fill", "#ffffff")
      .attr("stroke", item.color)
      .attr("stroke-width", 1.5);

    root
      .append("text")
      .attr("class", "endpoint-label")
      .attr("x", useX)
      .attr("y", rowY - 8)
      .attr("text-anchor", "middle")
      .text(`${Math.round(item.use)}%`);

    root
      .append("text")
      .attr("class", "endpoint-label")
      .attr("x", zoneX)
      .attr("y", rowY + 18)
      .attr("text-anchor", "middle")
      .text(`${Math.round(item.zone)}%`);
  });
}

function drawAgePyramid(container, profile, citywide) {
  const boroughColor = "#1a1a1a";
  const orderedBins = AGE_BINS.map((label, index) => ({
    label,
    key: normalizeAgeBin(index),
    cityMale: citywide.male[index],
    cityFemale: citywide.female[index],
  })).reverse();
  const male = orderedBins.map((bin) => profile[`male_${bin.key}`]);
  const female = orderedBins.map((bin) => profile[`female_${bin.key}`]);
  const total = d3.sum(male) + d3.sum(female);
  const malePct = male.map((value) => (total ? (value / total) * 100 : 0));
  const femalePct = female.map((value) => (total ? (value / total) * 100 : 0));
  const maxValue = d3.max([...malePct, ...femalePct, ...orderedBins.map((bin) => bin.cityMale), ...orderedBins.map((bin) => bin.cityFemale)]) ?? 0;

  const width = 348;
  const height = 218;
  const margin = { top: 12, right: 8, bottom: 22, left: 8 };
  const center = width / 2;
  const barHeight = 7;
  const gap = 3;
  const centerGap = 48;
  const barRange = 128;
  const x = d3.scaleLinear().domain([0, maxValue]).range([0, barRange]);
  const axisTicks = [0, Math.ceil(maxValue / 2), Math.ceil(maxValue)];

  const root = d3.select(container).html("").append("svg").attr("viewBox", `0 0 ${width} ${height}`).attr("width", "100%");
  root.append("line").attr("class", "midline").attr("x1", center).attr("x2", center).attr("y1", margin.top).attr("y2", height - margin.bottom);

  orderedBins.forEach((bin, index) => {
    const yPos = margin.top + index * (barHeight + gap);
    const maleWidth = x(malePct[index]);
    const femaleWidth = x(femalePct[index]);
    const cityMaleWidth = x(bin.cityMale);
    const cityFemaleWidth = x(bin.cityFemale);

    root
      .append("rect")
      .attr("class", "city-outline")
      .attr("x", center - centerGap / 2 - cityMaleWidth)
      .attr("y", yPos)
      .attr("width", cityMaleWidth)
      .attr("height", barHeight);
    root
      .append("rect")
      .attr("class", "city-outline")
      .attr("x", center + centerGap / 2)
      .attr("y", yPos)
      .attr("width", cityFemaleWidth)
      .attr("height", barHeight);

    root
      .append("rect")
      .attr("class", "pyramid-bar male")
      .attr("x", center - centerGap / 2 - maleWidth)
      .attr("y", yPos)
      .attr("width", maleWidth)
      .attr("height", barHeight)
      .attr("fill", boroughColor);
    root
      .append("rect")
      .attr("class", "pyramid-bar female")
      .attr("x", center + centerGap / 2)
      .attr("y", yPos)
      .attr("width", femaleWidth)
      .attr("height", barHeight)
      .attr("fill", boroughColor);

    root
      .append("text")
      .attr("class", "age-label")
      .attr("x", center)
      .attr("y", yPos + 6.5)
      .attr("text-anchor", "middle")
      .text(bin.label);
  });

  axisTicks.forEach((tick) => {
    const span = x(tick);
    root
      .append("text")
      .attr("class", "axis-label")
      .attr("x", center - centerGap / 2 - span)
      .attr("y", height - 6)
      .attr("text-anchor", "middle")
      .text(`${tick}%`);
    root
      .append("text")
      .attr("class", "axis-label")
      .attr("x", center + centerGap / 2 + span)
      .attr("y", height - 6)
      .attr("text-anchor", "middle")
      .text(`${tick}%`);
  });

  root
    .append("text")
    .attr("class", "axis-label")
    .attr("x", center - centerGap / 2 - barRange / 2)
    .attr("y", 10)
    .attr("text-anchor", "middle")
    .text(`Male (${formatValue(totalSexShare(profile, "male"), "percent")})`);
  root
    .append("text")
    .attr("class", "axis-label")
    .attr("x", center + centerGap / 2 + barRange / 2)
    .attr("y", 10)
    .attr("text-anchor", "middle")
    .text(`Female (${formatValue(totalSexShare(profile, "female"), "percent")})`);
}

function normalizeAgeBin(index) {
  return [
    "under_5",
    "5_9",
    "10_14",
    "15_19",
    "20_24",
    "25_29",
    "30_34",
    "35_39",
    "40_44",
    "45_49",
    "50_54",
    "55_59",
    "60_64",
    "65_69",
    "70_74",
    "75_79",
    "80_84",
    "85_over",
  ][index];
}

function totalSexShare(profile, sex) {
  const total = AGE_BINS.reduce((sum, _, index) => sum + (profile[`${sex}_${normalizeAgeBin(index)}`] || 0), 0);
  return profile.pop_acs ? (total / profile.pop_acs) * 100 : 0;
}

function raceSegments(profile) {
  const parts = [
    { label: "Hispanic", value: profile.pct_hispanic, color: RACE_COLORS.Hispanic },
    { label: "White", value: profile.pct_white_nh, color: RACE_COLORS.White },
    { label: "Black", value: profile.pct_black_nh, color: RACE_COLORS.Black },
    { label: "Asian", value: profile.pct_asian_nh, color: RACE_COLORS.Asian },
    { label: "Other", value: profile.pct_other_nh, color: RACE_COLORS.Other },
  ];
  return parts
    .map(
      (part) =>
        `<span class="race-segment" style="width:${Math.max(part.value, 0)}%; background:${part.color}" title="${part.label}: ${formatValue(part.value, "percent")}"></span>`,
    )
    .join("");
}

function raceLegend(profile) {
  const parts = [
    { label: "Hispanic", value: profile.pct_hispanic, color: RACE_COLORS.Hispanic },
    { label: "White", value: profile.pct_white_nh, color: RACE_COLORS.White },
    { label: "Black", value: profile.pct_black_nh, color: RACE_COLORS.Black },
    { label: "Asian", value: profile.pct_asian_nh, color: RACE_COLORS.Asian },
    { label: "Other", value: profile.pct_other_nh, color: RACE_COLORS.Other },
  ];
  return parts
    .map(
      (part) =>
        `<span class="swatch-item"><span class="dot" style="background:${part.color}"></span>${part.label} ${formatValue(part.value, "percent")}</span>`,
    )
    .join("");
}

function amenityTile(profile, tile) {
  return `
    <div class="amenity-tile" aria-label="${tile.label}: ${formatValue(profile[tile.key], "integer")}">
      <div class="tile-value">${formatValue(profile[tile.key], "integer")}</div>
      <div class="tile-label">${tile.label}</div>
    </div>
  `;
}

function formatValue(value, format) {
  if (!Number.isFinite(value)) {
    return "NA";
  }
  if (format === "currency") {
    return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
  }
  if (format === "percent") {
    return `${d3.format(".1f")(value)}%`;
  }
  if (format === "integer") {
    return d3.format(",")(value);
  }
  if (format === "number1") {
    return d3.format(".1f")(value);
  }
  return String(value);
}

function formatCompactCurrency(value) {
  if (!Number.isFinite(value)) {
    return "NA";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}
