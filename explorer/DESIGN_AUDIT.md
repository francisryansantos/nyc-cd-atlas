# Design Audit: NYC Community District Explorer

*Note: This audit is based on close reading of index.html, styles.css, and app.js in their current state. I cannot open a live browser from this environment, so observations about rendering are grounded in CSS/JS analysis rather than visual inspection. Items that would require live verification are marked.*

---

## 1. First impressions

The site has made real progress toward editorial. The warm cream background (`#f6f3eb`) is noticeably warmer than the earlier white, the compact header lets the map dominate, and the 2-column panel grid is a structural idea worth keeping. The first impression is of something purpose-built and considered, not a boilerplate dashboard.

But there's a font problem that undermines the entire typographic concept. `--font-serif` in `:root` is set to `"Inter", -apple-system, ...` — the same value as `--font-sans`. Source Serif 4 is fetched from Google Fonts and never applied. Every element meant to signal editorial authority — the page title, the district name, the section hints, the footer methodology paragraph, the chart captions — renders in Inter. The serif/sans distinction that was supposed to separate narrative from data doesn't exist in the rendered output. The site looks like a well-considered sans-serif tool rather than the publication it's trying to be. This is the single most important thing to fix.

---

## 2. Interpretation friction

**Understanding what any single number means — moderate**

The comparison text uses absolute differences now ("+4.1 pp vs city," "+$22k vs city"), which is correct and much clearer than the previous relative-percent approach. That's a real improvement. The remaining problem: the city median is never shown directly. A user reading "Poverty rate: 42.1% / +20.5 pp vs city" has to mentally subtract to find the city rate. Adding the city figure — "(city: 21.6%)" — below the delta costs nothing and removes the arithmetic.

**Comparing a district to the city — good, with one exception**

The pp-difference format works. The one exception: the `comparisonText` function still has a fallback branch (when `format` doesn't match currency, percent, or number1) that uses a relative percent calculation: `${Math.round(delta)}% vs city`. If this branch is ever reached, users see the confusing old format. Verify it's unreachable or remove the branch.

**Understanding what's notable about this district — hard**

`sectionIntro` was stripped back to just district name and neighborhoods. The `generateLede()` function exists, is fully written, and produces contextual sentences with specific numbers — but it isn't called anywhere. The panel opens with "Bronx CD 1 / Mott Haven, Port Morris" and then immediately jumps into charts. There's no sentence that frames what makes this place distinctive. The lede was the single most editorial element in the redesign and it's not being used.

**Reading the age pyramid — moderate**

The combined caption ("Population composition by age, sex, race, and Hispanic origin. The dashed outline in the pyramid shows the citywide distribution...") covers both charts adequately. The weak point is the legend label "Male (48.2%)" at the top of the pyramid — some users will read this as "48.2% of the data is male" rather than "48.2% of the total population is male," but this is a minor ambiguity, not a blocking problem.

**Understanding the dumbbell chart — moderate**

The chart legend shows "Current use" as a filled dark dot and "Zoning" as an outlined dot. That correctly encodes the shape distinction. But the chart-dot-legend swatches are colored `#3c3b37` (near-black), while the actual dots are colored by category (green for Residential, amber for Commercial, etc.). A user who reads the legend first expects dark dots and finds colored ones. The legend should show the encoding as: colored filled circle = current use, outlined circle = zoning, with the category colors below or omitted (since category labels are on the left of each row). The legend as written is accurate about shape but misleading about color.

**The dumbbell label position — possible collision**

Percentage labels appear above the "use" dot and below the "zone" dot. When use and zone are close (small delta, de-emphasized rows), the labels are only `8px / 18px` apart vertically on the same column. At 7.5–8.5px font size, these could visually merge. Needs live verification.

**Understanding "PUMA-published" — hard**

The `district-partner` note currently reads "Income data shared with [CD] (same PUMA)." Most users don't know what a PUMA is. The parenthetical doesn't explain why it matters. Proposed: "Income is published at the PUMA level and covers both this CD and [partner]. The figure shown is an estimate." That's still short but answers the "why does this matter" question.

---

## 3. Visual design issues

### Typography

**1. `--font-serif: "Inter"` is a copy-paste bug.**
`--font-serif` and `--font-sans` are identical in `:root`. Source Serif 4 is loaded and never applied. Fix: `--font-serif: "Source Serif 4", Georgia, "Times New Roman", serif;`. This one change unlocks the entire typographic hierarchy the stylesheet describes.

**2. `.section-header` is too heavy.**
`font-size: 19px; font-weight: 700` makes "Who lives here" and "Economic conditions" the visually loudest elements in the panel, heavier than the district name appears in compact panel columns. These are structural labels, not headlines. Fix: `font-size: 14px; font-weight: 500; font-variant: small-caps; letter-spacing: 0.05em; color: var(--ink-tertiary)`. Small-caps at tertiary ink recedes enough to be a separator, not a shout. (This also reads differently once `--font-serif` is fixed and the header is in serif.)

**3. `.chart-caption` is understyled.**
`font-size: 11px; font-style: normal` renders captions as tiny plain text. At 11px non-italic in Inter, they look like system UI cruft rather than editorial attribution. Fix: `font-size: 12px; font-style: italic`. The difference between 11px and 12px is barely perceptible in absolute terms but the weight shift from Inter-normal to Inter-italic makes them read as intentional.

### Color

**1. Legend swatch colors don't match chart.**
The `.chart-dot-legend-swatch.current` uses `background: #3c3b37` and `.zoning` uses `border: 1.4px solid #3c3b37`. The actual dumbbell dots are colored by category (green, amber, purple, green, gray). The legend encodes shape correctly but colors incorrectly. Either match the legend swatch colors to category colors or simplify the legend to show only the shape distinction using a neutral color, with a clear label explaining "fill = current use, outline = zoning designation."

**2. Accent color drift.**
`--accent: #b55436` in CSS vs `#c4502e` hardcoded in `applyMapStyles()` for the selected-CD stroke. These should match. The selected district outline doesn't use the CSS variable, so changing `--accent` in CSS won't affect the map selection state. Fix: change the hardcoded `#c4502e` in `applyMapStyles()` to `#b55436`, or unify to one value.

**3. Residential vs Park color similarity in dumbbell chart.**
`SLOPE_COLORS.Residential = "#639922"` (yellow-green) and `SLOPE_COLORS.Park = "#3F8A66"` (forest green). On a cream background, these two greens will be distinguishable but not effortlessly so. For users with mild deuteranopia they may be nearly identical. The labels on the left ("Residential", "Park") mitigate this — but it's worth monitoring if the chart ever gets used without labels.

### Spacing and rhythm

**1. `page-shell` top padding is too tight.**
`padding: 14px 34px 40px` — the 14px top gives the header almost no crown. The eyebrow text ("NYC Community District Profiles") sits close to the viewport edge. At the target editorial register, more breathing room at the top (28–32px) would help.

**2. The intro section has almost no padding.**
`#page-intro { padding: 6px 0 0 }` — 6px top padding. After the header's bottom rule, the instruction text appears immediately. It reads as a footnote to the header rather than as a distinct orientation layer. The instruction sentence is the first thing a new user should read comfortably, not skim past in the margin between header and map.

**3. Panel section gap at 22px row / 24px column.**
At the `1.14fr / 0.86fr` column split, the narrower "econ" column (~300px at typical viewport) is workable for stats but the `stat-label max-width: 20ch` at 13px + `info-marker` creates a tight row. The `info-marker` tooltip `left: calc(100% + 10px)` positions the popover to the right — in the narrow "econ" column this will overflow the panel edge. *Needs live verification.*

### Layout

**1. Map constrained to 390px.**
`.map-frame { max-width: 390px }` caps the map at 390px on all desktop sizes. The map column is `minmax(260px, 0.68fr)` — at 1200px viewport this gives roughly 380–390px for the map column, meaning the max-width is just barely activating. The map is already small relative to the panel; the max-width cap doesn't help. Consider removing it and letting the map fill its column naturally.

**2. The amenity tile grid at narrow column widths is very compressed.**
In the `"built amenities"` grid-area row, "Civic places" gets the 0.86fr column (~300px). With 3 columns of tiles and 10px gaps, each tile is about 93px wide. "Senior services" at `max-width: 12ch` in a 12px/500 font is right at the limit. At slightly narrower viewports the labels will wrap to 2 lines, making tiles uneven heights. Either reduce to 2-column amenity grid or set `grid-template-areas` to give amenities the wider column.

### Component polish

**1. `metric-card::before` partial rule is an excellent detail.**
The 48px partial top rule above each metric card (population, foreign born) is a subtle editorial touch — the kind of thing that signals craft to attentive readers without calling attention to itself. Don't change it.

**2. Amenity tiles are center-aligned inside bordered boxes.**
Center-aligned tiles look fine. The `::before` pseudo-element adds a 2px top stripe in `--bg-surface-3`. This is decorative but clean. What's slightly odd: `background: rgba(252, 251, 247, 0.55)` — this is an alpha value over the page background, which adds a barely-perceptible lightening effect. Whether it reads as intended depends on what's behind the tile. On the cream background it may be indistinguishable from the page. Either set it to `var(--bg-surface)` (solid) or remove the tile background entirely and rely on the border.

---

## 4. Interaction and state

**Clickability:** The map hit areas have `cursor: pointer` and the paths have visible fill. Clear affordance. The mode toggle and metric chips are `<button>` elements. Good.

**Zoom:** `d3.zoom` with `scaleExtent([1, 5])` is implemented. The "Scroll or pinch to zoom" hint is accurate. The `translateExtent` prevents panning outside the district bounds. One concern: when the SVG is scaled, the `stroke-width` on district paths scales with the transform, so at 5× zoom the 1px borders become effectively 0.2px and the 2.5px selected-district stroke becomes 0.5px. The selected accent outline disappears at high zoom. This is a known d3.zoom limitation; a fix would re-scale strokes inversely with zoom.

**Selection state:** The accent-colored stroke (currently hardcoded at `#c4502e`, a warm rust) on the selected district is unambiguous. The `raise()` call ensures it's on top. The `mapLabel.textContent` update is immediate. Clear.

**Mode changes:** The chip row appearing/disappearing on mode toggle is a clean affordance. The filled pill on `.mode-button.is-active` (dark background) is an obvious active state. The one issue: switching modes doesn't update the panel content — the panel keeps showing whatever district is selected, which is correct behavior, but new users may expect the panel to change when they click "Choropleth."

**Default landing state:** The site opens with the Bronx CD 1 panel pre-populated and the instruction text "Click any district to read its profile." The panel content is immediately present, which is good. The problem is there's no introductory framing — the user sees a map with data and one instruction sentence. They don't know what community districts are, why 59 of them exist, or what this tool covers. The instruction collapses on first click, which is correct; but what it replaces isn't informative enough to orient a first-time visitor.

---

## 5. Mobile experience

*Based on CSS analysis; not live-verified.*

**900px and below:** Layout switches to single-column (map over panel). The panel becomes `flex-direction: column; max-height: 74vh; overflow-y: auto`. The `border: 1px solid var(--rule-strong)` around the panel on mobile is a reasonable container. The 2-column panel grid correctly reverts (`grid-area: auto` on all children resets auto-flow). **However:** the mobile reset sets all five `.section-block:nth-child(n)` to `grid-area: auto`, but the `display: flex; flex-direction: column` also on the panel means the grid areas never applied anyway. This works, but the CSS is redundant.

**640px and below:** The `section-block` gets `margin-bottom: 34px`. This is good — generous separation between sections in the stacked single-column layout. The `page-title` gets `font-size: 36px; white-space: normal; max-width: 15ch`. "An atlas of New York's 59 community districts" is 43 characters, wrapping to 2–3 lines at 36px in a 375px viewport. The title will be visually large relative to the map below it. If the page-subtitle were present, that area would be even taller.

**Note:** `.page-subtitle` is defined in CSS but doesn't exist in the HTML (it was removed from the header). The responsive rule at 900px (`font-size: 16px`) applies to `.page-subtitle, .intro-instruction` — the page-subtitle rule is dead.

**375px worst case:** Map renders at full container width (max-width: none at 900px). The `map-frame` has padding `12px 10px 10px`, so the SVG gets 355px width. At 355px, district labels at 10px are readable. The amenity tile grid switches to 2 columns at 900px (not at 640px — check if this is intentional or should be 640px). At 375px, 2-column tile grid gives ~159px per tile. Fine.

---

## 6. Accessibility issues

**1. `info-marker` uses `role="img"`.**
The info-marker spans use `tabindex="0" role="img" aria-label="[tooltip text]"`. Using `role="img"` on an interactive element that reveals tooltip content on focus is semantically wrong — this is a button, not an image. The `aria-label` correctly describes the content, but the role should be `role="button"` or the element should be `<button>` with `aria-describedby` pointing to the tooltip text. A screen reader announcing "image" when a user tabs to "i" is confusing.

**2. The CSS-only tooltip (`:hover::after` / `:focus::after`) is inaccessible in some contexts.**
The `.info-marker::after` tooltip appears on `:hover` and `:focus`. But `:focus` on a non-button element in some browsers/AT combinations may not expose the pseudo-element content as text. For screen reader users who navigate to the `role="img"` element, the `aria-label` on the element itself contains the full description — that's acceptable as a fallback. But the tooltip's CSS content isn't in the DOM as text, so it won't be read by AT without the `aria-label`. This is a known CSS-tooltip limitation.

**3. Selected map district has no `aria-pressed` or `aria-selected`.**
When a district is clicked, the panel updates (via `aria-live="polite"` on the panel — good). But the selected hit-area path doesn't set `aria-pressed="true"` or `aria-selected="true"`. A keyboard user navigating with Tab across the hit areas has no announcement of which district is "currently selected." The panel announces the change on district click, but navigating through the map grid without clicking gives no current-selection feedback.

**4. The `.district-hit-area` and `.map-path` both have `tabindex="0"` and `aria-label`.**
This creates duplicate focusable elements for each district — one opaque hit area and one map path, both with the same `aria-label`, stacked on top of each other. Screen readers may announce the same district twice per tab stop. The map paths should have `tabindex="-1"` and `aria-hidden="true"`, with only the hit areas being keyboard-focusable.

---

## 7. The five fixes worth doing first

**1. Fix `--font-serif`**
- Current: `--font-serif: "Inter", -apple-system, ...` (identical to `--font-sans`)
- Proposed: `--font-serif: "Source Serif 4", Georgia, "Times New Roman", serif;`
- Why: Every element designed to signal editorial weight — page title, district name, section hints, footer, chart captions — currently renders in Inter. The serif/sans hierarchy is the core of the editorial concept and it doesn't exist in the output. This also changes the character of `.district-name` (from a heavy Inter 600 to a Source Serif 4 600, which will feel warmer), `.section-hint`, and `.footer-methodology`.
- Complexity: **Trivial** — one line in `:root`.

**2. Call `generateLede()` in `sectionIntro`**
- Current: `sectionIntro` renders district name + neighborhoods only. `generateLede()` is written and correct but never called.
- Proposed: Add `<p class="district-lede">${generateLede(profile, state.medians)}</p>` to `sectionIntro`'s innerHTML, and add `.district-lede` to the stylesheet (`font-family: var(--font-serif); font-size: 16px; font-style: italic; color: var(--ink-secondary); line-height: 1.58; margin: 8px 0 0; max-width: 60ch;`).
- Why: The lede is the editorial differentiator between this tool and DCP's own fact sheets. A sentence like "42 percent of Mott Haven residents live below the federal poverty line" framed as prose gives a human entry point before the numbers. The code to generate it already exists and is well-written.
- Complexity: **Small** — two additions (one JS call, one CSS block).

**3. Lighten `.section-header`**
- Current: `font-size: 19px; font-weight: 700; color: var(--ink-primary)`. These labels compete with the district name visually.
- Proposed: `font-size: 13px; font-weight: 500; font-variant: small-caps; letter-spacing: 0.06em; color: var(--ink-tertiary); border-bottom: 1px solid var(--rule); padding-bottom: 7px;`
- Why: Section headers mark transitions, they don't headline. At 700/19px in a narrow panel column, "Who lives here" is louder than it needs to be. Small-caps at tertiary ink reads as a document marker, not a title. The bottom rule gives the section a clean edge to push content away from.
- Complexity: **Trivial** — CSS change only.

**4. Fix the chart-dot-legend swatch colors**
- Current: Both swatches use dark gray (`#3c3b37` / outlined). The chart uses category colors (green, amber, purple, etc.).
- Proposed: Remove the specific color from the swatch CSS and instead show a generic filled/outlined pair that explains the encoding without implying a specific color. Use `var(--ink-secondary)` for both. Or, more completely: drop the color swatches and replace with text labels: "● current use  ○ zoning designation."
- Why: The legend currently teaches users the wrong color encoding. A user who reads the legend and then looks at the chart will see filled amber dots where they expected filled dark dots. The mismatch is small but erodes the chart's credibility.
- Complexity: **Trivial** — CSS values for two classes.

**5. Add the introductory paragraph to `#page-intro`**
- Current: `#page-intro` contains only: "Click any district to read its profile, or switch to choropleth mode to compare all 59 at once."
- Proposed: Add before the instruction: `<p class="intro-text">The city's 59 community districts are small enough to feel like neighborhoods and large enough to publish data on. This explorer draws on ACS 2020–2024, city tax-lot records, and crime statistics, updated through 2024.</p>` with `.intro-text { font-family: var(--font-serif); font-size: 15px; color: var(--ink-secondary); line-height: 1.55; max-width: 58ch; margin: 0 0 14px; }`.
- Why: The site currently opens with data and a prompt. Without framing, a new visitor doesn't know what community districts are, why they exist, or what differentiates this tool from DCP's own profiles. Two sentences fixes this. The intro collapses on first interaction so it doesn't persist past the initial orientation.
- Complexity: **Trivial** — one HTML element, one CSS block.

---

## 8. What to leave alone

**The `comparisonText` rewrite.** Using absolute pp differences for percentage metrics ("+4.1 pp vs city") and absolute currency differences for income ("+$22k vs city") is correct. The previous relative-percent format ("-91% vs city" for poverty) was genuinely confusing. This is better, leave it.

**The dumbbell chart replacing the slope chart.** The horizontal dumbbell with category labels on the left reads more intuitively than the old slope chart. The `highlight` logic (10pp threshold for full opacity/weight) correctly de-emphasizes close pairs. The gap annotation ("Difference: 14pp") for highlighted rows is the right addition.

**The `info-marker` tooltip component.** The CSS-only tooltip that appears on hover/focus is well-styled and the descriptions in `ECONOMIC_ROWS` are accurate and useful. "Share of renter households spending 30 percent or more of income on rent" is exactly what a curious user wants to know. The mechanism needs accessibility fixes (see Section 6) but the content and concept are right.

**The SON priorities block.** If `profile.son_issue_1` / `son_issue_2` / `son_issue_3` are present in the data, showing community board's reported priorities as a numbered list inside the economic section is an excellent editorial addition — it surfaces qualitative context that no amount of ACS data can capture. The `issue-header` ALL CAPS treatment at 11px/600 is fine here as a tertiary label.

**The warm background palette.** `#f6f3eb` is warmer and more distinctive than the earlier `#fafaf7`. The full tonal range (bg-surface, bg-surface-2, bg-surface-3, rule, rule-strong) is internally coherent. The cream page against the white map frame (`--bg-surface`) creates a subtle depth distinction without shadows. Don't touch it.
