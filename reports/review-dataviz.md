# Data Visualization Review Report

> AD-Research platform — chart, sparkline, and KPI surface layer
> Review date: 2026-07-16
> Scope: `web/src/components/*.tsx` chart primitives, page-level `ReactECharts`
> call sites, supporting data components (`Panel` / `StatCard` / `SparklineCell`
> / `EmptyState`), design tokens (`web/src/styles/theme.css`), and color
> helpers (`web/src/utils/color.ts`, `web/src/utils/cssVar.ts`).
> Mode: **READ-ONLY** — no source files modified.

This report covers 12 P0/P1 issues and 6 P2 issues, plus a list of
missing capabilities. Each item includes file:line citations, a
description of the visualization impact, and a concrete fix path.

---

## 1. Issues

### P0 — Critical

#### 1. Correlation heatmap uses semantic up/down tokens for a diverging scale
- **Location**: `web/src/components/CorrelationHeatmap.tsx:128`
  (`inRange: { color: [colorFall, bgBase, colorRise] }`)
- **Problem**: The visualMap gradient is built from `--color-fall`,
  `--bg-base`, and `--color-rise`. Those tokens are the *market*
  rise/fall colors that swap on `data-color-convention` (China = red up,
  US = green up). Correlation is **not** a return — a `+0.95`
  correlation is not "this instrument is rising", it is "moves together
  with the other." When a Chinese user (default) sees a red cell for
  `+0.95`, they will read it as "both rose today," which is wrong.
  When the user toggles the convention to US, the same `+0.95` cell
  turns green and the chart silently changes meaning.
- **Impact**: Semantic confusion, false reading of the chart, and a
  chart whose meaning depends on a setting that has nothing to do with
  correlation.
- **Fix**: Use a dedicated diverging palette, e.g. add new tokens
  `--corr-positive` / `--corr-negative` / `--corr-zero` (blue/white/red,
  color-blind safe) and bind the visualMap to those instead of
  `--color-rise` / `--color-fall`. Document the choice in `theme.css`.
- **Priority**: P0

#### 2. BacktestDetail NAV chart passes raw `var(--xxx)` strings to ECharts
- **Location**: `web/src/pages/BacktestDetail/index.tsx:119-128`
  (`axisLine: { lineStyle: { color: 'var(--text-tertiary)' } }`,
  `splitLine: { lineStyle: { color: 'var(--border-default)' } }`,
  `lineStyle: { color: 'var(--accent)', width: 2 }`,
  `areaStyle: { color: 'var(--accent-dim)' }`)
- **Problem**: ECharts cannot resolve CSS variables — they are passed
  through to the canvas as literal strings. In ECharts 5, an invalid
  color string silently degrades to the previous valid color, so the
  axis lines, area fill, and split lines will render with whatever the
  last valid color was (often the series' main stroke), making axis
  guidelines invisible and area-fill mismatched.
- **Impact**: The single most important backtest chart loses its
  visual separation (no grid lines, no contrast between line and area).
  Theme switching also breaks because the raw `var(--accent)` is never
  re-evaluated.
- **Fix**: Convert all `var(--xxx)` to literal hex via `resolveChartColor`
  (the same helper used by `CorrelationHeatmap`, `KLineChart`, etc.) or
  refactor `BacktestDetail` to use the `ReturnCurve` primitive (which
  already does this correctly).
- **Priority**: P0

#### 3. Macro chart option omits all theme colors and formatters
- **Location**: `web/src/pages/Macro/index.tsx:394-420`
- **Problem**: The chart option builds `tooltip`, `grid`, `xAxis`,
  `yAxis`, `series` with **no** `backgroundColor`, no `textStyle`, no
  axis colors, no `axisLabel.color`, no unit formatter, and the y-axis
  name is set to `series.unit` (which may be `""` for some indicators).
  Macroeconomic indicators vary wildly in unit (`%`, `BPS`, `Index`,
  `元/吨`, `人`) and range (CPI in low single digits, M2 in trillions);
  the chart still uses a generic `value` axis with no scaling.
- **Impact**: Chart appears as a default white ECharts surface with
  black text and no theme integration; mismatched units produce
  illegible axes (e.g. `global_brent` rendered as `85.32` with no unit,
  versus `m2_yoy` rendered as `8.4%` with the `%` baked into the axis).
- **Fix**:
  1. Resolve all theme colors via `resolveChartColors`.
  2. Branch the y-axis formatter by `series.unit` — e.g. wrap with
     `unit === '%' ? v.toFixed(2) + '%' : v.toLocaleString()`.
  3. Use a log scale when `Math.abs(max/min) > 100` and `min > 0`,
     or split dual axes when positive/negative ranges diverge.
- **Priority**: P0

#### 4. SectorRotation heatmap has a hard-coded ±6% visualMap that hides the actual distribution
- **Location**: `web/src/pages/SectorRotation/index.tsx:255-267`
  (`visualMap: { min: -6, max: 6, ... inRange: { color: [palette.downHex, palette.midHex, palette.upHex] } }`)
- **Problem**: The visualMap domain is hard-pinned to `±6%`. Real
  sector returns are usually inside `[-3%, +3%]` for a normal week,
  but in a bull run the 1-year column can easily hit `+40%`. Every
  cell with `|v| > 6` clamps to the same end color, so all "very hot"
  sectors look identical and a `+30%` and a `+45%` cell are
  indistinguishable. Conversely in a flat market everything is the
  mid-tone and the heatmap communicates nothing.
- **Impact**: The heatmap (the headline visualization of the page) is
  often either all the same color or all clamped. Users can't tell
  whether a sector is "best" or "tied for best" — the differentiation
  the page is built around is lost.
- **Fix**: Compute `min`/`max` from the actual data:
  ```ts
  const all = data.map(d => d[2]);
  const maxAbs = Math.max(1, ...all.map(Math.abs));
  visualMap: { min: -maxAbs, max: maxAbs, ... }
  ```
  Or use a quantile-based (`type: 'piecewise'`) scale for stable
  rendering across market regimes.
- **Priority**: P0

#### 5. KLineChart maps MACD histogram & volume colors to market rise/fall tokens (semantic mismatch)
- **Location**: `web/src/components/KLineChart.tsx:318` (volume bars),
  `web/src/components/KLineChart.tsx:369` (MACD histogram bars)
- **Problem**: Volume bars and MACD histogram bars are colored by
  `resolvedUpColor` / `resolvedDownColor`, which are the *price*
  rise/fall tokens. That conflates two unrelated signals:
  1. Volume is colored by `close >= open` (price direction), but a
     high-volume flat bar should be visually distinct from a low-volume
     move. Volume magnitude is not encoded.
  2. MACD histogram bars are colored by `hist >= 0` (momentum sign).
     Reusing red/green for "bullish/bearish momentum" then reusing the
     same colors for "price up/down" means the user's eye cannot
     disentangle price action from momentum.
- **Impact**: Two channels share the same hue mapping; users who have
  learned that "red = price fell today" will misread MACD bars as
  "price fell" instead of "momentum turned negative."
- **Fix**: Add dedicated tokens (e.g. `--chart-volume-up`,
  `--chart-volume-down`, `--chart-macd-up`, `--chart-macd-down`)
  that are **not** affected by `data-color-convention`, or use
  hue-shifted variants (e.g. teal vs red) so price and momentum are
  visually separable.
- **Priority**: P0

#### 6. ReturnCurve tooltip lacks a formatter — date axis & multi-series hover are unformatted
- **Location**: `web/src/components/ReturnCurve.tsx:79-84`
  (`tooltip: { trigger: 'axis', backgroundColor: bgElevated[0], borderColor: borderDefault[0], textStyle: { color: textPrimary[0] } }`)
- **Problem**: No `tooltip.formatter`. With up to 10 normalized series,
  the default tooltip is a wall of `seriesName: value%` rows on a
  stacked vertical list with no date column showing which day is
  hovered. Because `xAxis.type = 'category'`, the date the user is
  reading is only obvious from the x-axis tick labels, not the
  tooltip.
- **Impact**: The hover layer — the single most important tool for
  cross-comparing instruments at a point in time — is barely usable.
  Two adjacent dates are visually close; the tooltip doesn't tell you
  which one you're on.
- **Fix**: Add `tooltip.formatter(params)` that emits
  `<b>{params[0].axisValue}</b><br/>{rows.map(p => '<span style="color:'+p.color+'">●</span> '+p.seriesName+': '+p.value.toFixed(2)+'%').join('<br/>')}`
  and stagger series by `±0.5%` *tooltip position hint* if it can be
  done cleanly.
- **Priority**: P0

---

### P1 — High priority

#### 7. ReturnCurve lacks non-color encoding for ≥ 5 overlapping series
- **Location**: `web/src/components/ReturnCurve.tsx:110-122`
  (`series.map(...{ type: 'line', smooth: true, symbol: 'none', lineStyle: { width: 2 }, itemStyle: { color: palette[idx % palette.length] } })`)
- **Problem**: Lines are differentiated only by color. `symbol: 'none'`
  means no markers at vertices, no dashed/dotted line variants, and no
  emphasis. With 8+ ETF comparisons (ReturnComparison page allows up
  to `maxCount={10}` per `web/src/pages/ReturnComparison/index.tsx:104`),
  crossing lines become a tangle of same-weight solid strokes. The
  palette comment claims "Okabe-Ito 色盲安全" but `--chart-series-9`
  (`#4f46e5` indigo) and `--chart-series-10` (`#65a30d` lime) are not
  part of Okabe-Ito and may collide with series-1 (blue) and series-3
  (green) for deuteranopes.
- **Impact**: Multi-instrument comparison (the page's raison d'être) is
  hard to read; accessibility for color-blind users is partial.
- **Fix**:
  1. Add line-style cycling: `series[i].lineStyle.type = i % 3 === 0 ? 'solid' : i % 3 === 1 ? 'dashed' : 'dotted'`.
  2. Cap palette to the 8 Okabe-Ito entries, or replace series-9/10
     with tones that don't collide (e.g. `#999999` mid-grey and
     `#CC79A7`-shifted pink).
  3. Set `emphasis: { focus: 'series' }` so hovering highlights the
     selected line and dims others.
- **Priority**: P1

#### 8. ScoreBar's gradient is a "stoplight" — color and length double-encode magnitude
- **Location**: `web/src/components/ScoreBar.tsx:18-20` (color via
  `getScoreColor(score)`); `web/src/utils/color.ts:47-52` (buckets:
  ≥80 excellent green, ≥60 good lime, ≥40 average amber, <40 bad red)
- **Problem**: A score of 60 renders green, a score of 80 also renders
  green, but the user only sees "green = good" — not whether it's
  adequate or excellent. Worse: the color suggests a *binary
  acceptable/not* signal, but the underlying data is ordinal
  (`composite_score` 0–100). The score-bar therefore trains users to
  treat scores as pass/fail rather than as a continuum, which is the
  opposite of what scoring is for.
- **Impact**: Fund managers scanning a ranking page will bin scores
  into "good (green)" vs "bad (red)" rather than read the actual
  numeric value. Combined with the 7-day sparkline next to it
  (`web/src/pages/ScoreRanking/index.tsx:90`), the sparkline is
  colored by up/down while the bar is colored by score bucket — two
  semantically different color encodings in adjacent columns.
- **Fix**: Replace the categorical bucket with a continuous hue
  gradient (e.g. red → amber → green on a single HSL axis) or use a
  single brand color (`--accent`) with opacity encoding the score
  magnitude. Document the change in `theme.css` (the score tokens
  `--score-excellent`, `--score-good`, etc. would also need to be
  redefined).
- **Priority**: P1

#### 9. ScoreRadar has no tooltip formatter and no axis scale labels
- **Location**: `web/src/components/ScoreRadar.tsx:103-108`
  (`tooltip: { trigger: 'item', backgroundColor: bgElevated, ... }`)
- **Problem**: The tooltip's default behavior shows just the series
  name. The radar polygon does show the shape, but the actual
  per-axis numeric values (0–100) are not labeled anywhere — the user
  must hover each of the 5 vertices individually to read the score.
  On mobile (`radius: '55%'`) the polygon is even smaller, and the
  5 indicator names (收益能力 / 风险控制 / 夏普比率 / 流动性 / 趋势
  强度) can crowd the chart edges.
- **Impact**: The "score breakdown" card does not communicate the
  underlying numbers on first glance — it requires 5 hovers to read.
  Adjacent cards (total return, sharpe ratio) are direct numbers.
- **Fix**: Add a tooltip formatter that emits
  `收益能力: 78.5\n风险控制: 65.0\n...`, and place the numbers as
  small text inside the polygon, or as a side list with color dots.
- **Priority**: P1

#### 10. KLineChart's RSI/MACD scales are added but never get their own panes
- **Location**: `web/src/components/KLineChart.tsx:251-265` (RSI /
  MACD series added with `priceScaleId: 'rsi' / 'macd'`), no
  `priceScale().applyOptions({ scaleMargins })` on the rsi/macd panes
- **Problem**: Volume uses `priceScale().applyOptions({ scaleMargins:
  { top: 0.85, bottom: 0 } })` (line 239), which gives it the bottom
  15% of the chart. RSI and MACD have `priceScaleId: 'rsi'` /
  `'macd'` but the `rsi`/`macd` price scales are never given
  `scaleMargins`, so they default to occupying the *entire* price
  range (0–100%) and are overlaid on top of the candles (invisible).
  RSI will only show if `overlays.rsi` is `true` (default) — but with
  no pane reservation, it draws on the candle body and is unreadable.
- **Impact**: The default `DEFAULT_OVERLAYS` has `rsi: true` and `macd:
  false` (`web/src/components/KLineChart.tsx:142-150`). Users see RSI
  lines drawn on top of the candle chart and either mistake them for
  MAs or assume the chart is broken.
- **Fix**: Reserve separate panes:
  ```ts
  chart.priceScale('rsi').applyOptions({ scaleMargins: { top: 0.78, bottom: 0.18 } });
  chart.priceScale('macd').applyOptions({ scaleMargins: { top: 0.62, bottom: 0.30 } });
  ```
  And use a `pane` index rather than overlapping `priceScaleId`.
  lightweight-charts v5 supports `paneIndex` on series options.
- **Priority**: P1

#### 11. Sparkline grid uses pre-rounded two-decimal values via `parseFloat(val.toFixed(2))` — precision loss
- **Location**: `web/src/components/CorrelationHeatmap.tsx:26`
  (`data.push([i, j, parseFloat(val.toFixed(2))])`)
- **Problem**: Every correlation value is rounded to 2 decimal places
  before being placed in the heatmap. `0.847` becomes `0.85`. For
  users comparing similar correlations (`0.81` vs `0.84`), the visual
  difference is a single hue step but the rounded tooltip will show
  identical `0.81` and `0.82` as the same number.
- **Impact**: Heatmap labels become lossy; tooltip hover reveals a
  value that disagrees with the cell's perceived color. This is a
  classic chart-data mismatch.
- **Fix**: Use the full-precision value in `data`; only round in the
  `label.formatter` and `tooltip.formatter`. E.g.
  `data.push([i, j, val])` and `formatter: (p) => p.data[2].toFixed(3)`.
- **Priority**: P1

#### 12. TickerTape cells lack `:focus-visible` styling for keyboard navigation
- **Location**: `web/src/components/TickerTape.tsx:159-170` (cells
  with `role="button"` and `tabIndex={0}`); no `ticker-cell:focus`
  rule in the matched CSS is referenced.
- **Problem**: Cells are interactive (clicking navigates to the
  instrument detail), and they advertise themselves as buttons to
  screen readers. Keyboard users can `Tab` into the cell, but the
  infinite-scrolling track means the focused cell is constantly
  moving off-screen. There is also no visible focus ring on the cell
  itself (no `outline` or `box-shadow` rule is described in this
  file).
- **Impact**: Keyboard users can navigate but cannot see where the
  focus is, because the animation continues. Click handlers fire on
  `Enter`/`Space` (`web/src/components/TickerTape.tsx:165-170`) but
  without `:focus-visible` styling, this is hidden functionality.
- **Fix**:
  1. Pause the animation while a cell has focus (CSS `:focus-within
     { animation-play-state: paused }`).
  2. Add a 2px solid `--accent` outline with 2px offset on
     `ticker-cell:focus-visible`.
  3. Make each cell `aria-label` describe price + change (currently
     only the code/name are in the visual, with no aria).
- **Priority**: P1

---

### P2 — Medium

#### 13. ReturnComparison daily-return mode computes `((items[i].close - items[i-1].close) / items[i-1].close) * 100` without handling non-trading-day gaps
- **Location**: `web/src/pages/ReturnComparison/index.tsx:73-86`
- **Problem**: When a user selects "全部" with a long history, the
  series iterates raw `items[i].close` against `items[i-1].close`.
  If the underlying data has gaps (holidays, weekends, missing
  trading days), the "daily" return is actually a multi-day return
  divided by the previous close, mislabeled as daily. The x-axis
  drops `items[0]` from the dates array, so the gap is invisible but
  the return number is wrong.
- **Impact**: Numbers on a "daily" mode are silently wrong when the
  upstream history has gaps; users may misjudge volatility.
- **Fix**: Either label the y-axis `(period return)` and remove the
  "daily" word, or use only consecutive trading-day pairs and
  visually mark skipped weekends with a vertical gap (`xAxis:
  { boundaryGap: false }` plus explicit `null` between dates).
- **Priority**: P2

#### 14. Macro chart's tooltip `transitionDuration` defaults ignore reduced-motion for non-Apple pages
- **Location**: `web/src/pages/Macro/index.tsx:582-585`
  (`option={{ ...chartOption, animation: !prefersReducedMotion }}`)
- **Problem**: `chartOption` is built without `animation: false` baked
  in, and the `notMerge` flag is set, which means every re-render of
  the panel will restart the entrance animation — *even* when the
  user only switched the segmented region. The animation flag only
  suppresses the initial draw, not subsequent renders.
- **Impact**: Every region switch replays the entrance animation,
  which can feel sluggish on lower-power laptops and conflicts with
  the page's own `prefers-reduced-motion` block.
- **Fix**: Set `animation: false` (or `animationDuration: 0`) in
  `chartOption` directly, then only enable animation on the first
  render via a ref-tracked boolean.
- **Priority**: P2

#### 15. CategoryPie mixes full-saturation and 8%-opacity tokens in one palette
- **Location**: `web/src/components/CategoryPie.tsx:30-44`
- **Problem**: The palette interleaves `var(--accent)`, `var(--color-rise)`,
  `var(--color-fall)` (full saturation) with `var(--text-tertiary)`,
  `var(--accent-dim)`, `var(--color-rise-dim)`, `var(--color-fall-dim)`
  (8% opacity, near-invisible on a white background). The pie's
  `itemStyle.borderColor: bgElevated[0]` and `borderWidth: 2` give a
  thin white separator, but the dim slices blend into the background.
- **Impact**: Pie slices assigned to dim tokens (3rd, 6th, 7th, 8th
  categories) appear as blank/grey wedges; users see only a partial
  breakdown.
- **Fix**: Replace dim tokens with mid-saturation tones (e.g. add
  `--chart-cat-mid-1..8` at ~50% opacity), or define a dedicated
  8-color categorical palette in `theme.css` separate from the
  market-rise/fall tokens.
- **Priority**: P2

#### 16. StatCard has no delta/period-comparison encoding
- **Location**: `web/src/components/StatCard.tsx:42-60`
- **Problem**: StatCard renders a title, value, suffix, and optional
  explainer. There is no slot for a delta vs prior period (e.g.
  `+1.2% vs yesterday`), no sparkline, and no up/down indicator.
  Many consumers wrap StatCard with hand-rolled `delta-pill` divs
  (e.g. `SectorRotation/index.tsx:503-516` does it inline).
- **Impact**: KPI rows across the platform miss a key data-viz
  affordance — change vs baseline — and each page reinvents it
  inconsistently.
- **Fix**: Add `delta?: number`, `deltaLabel?: string`, and a
  `trend?: 'up'|'down'|'flat'` prop. Render the delta inline
  beside the value with `tabular-nums` and the appropriate
  `--color-rise`/`--color-fall` token.
- **Priority**: P2

#### 17. Panel.tsx provides no `role="region"` or `aria-labelledby` for screen-reader landmark navigation
- **Location**: `web/src/components/Panel.tsx:46-55`
- **Problem**: `Panel` renders a `<div className="ad-panel">` with no
  ARIA landmark role. Screen-reader users can't quickly jump between
  panels via the landmark menu (`D` in NVDA, `R` in VoiceOver). The
  title is a `<span>` and is not linked to the panel body via
  `aria-labelledby`.
- **Impact**: Major accessibility gap for a panel-based UI.
- **Fix**: Add `role="region"` and `aria-labelledby={titleId}` on
  the panel root; set `id={titleId}` on the title `<span>`.
- **Priority**: P2

#### 18. EmptyState has no icon-only / heading-only size variant
- **Location**: `web/src/components/EmptyState.tsx:20-33`
- **Problem**: EmptyState always renders a full vertical stack
  (icon, h3, p, action). In tables, the consumers wrap it inside
  AntD `Table.locale.emptyText` (`web/src/pages/Macro/index.tsx:546-548`,
  `web/src/pages/SignalDashboard/index.tsx:211-213`), where the
  table cell is ~50px tall. The full EmptyState is then squashed or
  the title is clipped.
- **Impact**: Empty tables look broken or have hidden icons.
- **Fix**: Add a `density?: 'compact' | 'default'` prop. In
  `compact` mode, hide the description and shrink the icon to 24px.
- **Priority**: P2

---

## 2. Missing Capabilities

1. **Cross-filter / brush linking** between `ReturnComparison` and
   `CorrelationAnalysis` — selecting a date range in one chart does
   not propagate to the other. A brush component (e.g.
   `echarts.dataZoom`) on the return curve with a shared store
   (Zustand or React Query cache key) would let users answer
   "what was the correlation during the March drawdown?" in two
   clicks.

2. **Drill-down navigation from chart primitives** — `SectorRotation`
   heatmap cells render labels (`+3.45%`) but are not clickable. A
   user who sees a hot row can't pivot to the constituents without
   switching tabs to the dropdown.

3. **Y-axis log scale option** for `Macro` indicators where range
   spans orders of magnitude (e.g. SHIBOR ~2 vs M2 ~10^15). The
   current linear axis clamps the small series to a flat line.

4. **Outlier-aware heatmap scale** — `SectorRotation` should expose
   a "robust" mode that clips to the 5th/95th percentile instead of
   min/max, so a single mega-cap outlier doesn't wash out the rest.

5. **Sparkline tooltips** — `SparklineCell` renders a non-interactive
   80×20 SVG with no tooltip on hover. Users see a shape but cannot
   read individual point values. A `title` element or hover-anchored
   popover would help.

6. **Accessibility summary on echarts instances** — none of the
   ECharts wrappers expose a `aria-label` describing the chart type
   and series count. Screen readers hear "graphic" with no context.
   Each chart needs `chart.setOption({ aria: { enabled: true } })`.

7. **Chart export (PNG / CSV)** — none of the chart components
   expose `echarts.getDataURL()` or a "download data" action. Power
   users who want to put a chart into a memo have no path.

8. **Empty-data placeholder for `BacktestDetail` NAV curve** — when
   `data.daily_nav.length === 0` the chart still renders an empty
   `ReactECharts` (line 216), showing just an axis with no series.
   An `EmptyState` should replace the chart in that case.

9. **Quantile bucketing for correlation** — currently the
   `visualMap` is linear from -1 to +1, so most cells (~0 to ±0.5)
   cluster near the mid tone and the strong/weak distinctions
   (`±0.7`+) are highlighted. A piecewise scale (e.g.
   `[-1, -0.7, -0.3, 0.3, 0.7, 1]`) would make clusters of moderate
   correlation visible.

10. **Time-zone-aware date axis labels** — `ReturnCurve` and the
    Macro chart both render category axes with raw dates. A user in
    Beijing vs New York sees the same label but interprets it
    differently. The `datetime.ts` utility exists
    (`web/src/utils/datetime.ts`) but neither chart calls it for
    axis formatting.

11. **Color-blind toggle / palette swatch** — `theme.css` provides a
    China/US convention toggle, but no simulation for protanopia /
    deuteranopia / tritanopia. The Okabe-Ito palette
    (`--chart-series-*`) is color-blind safe in pairs but the
    semantic `--color-rise`/`--color-fall` pair is not.

12. **Annotation layer for events** — `KLineChart` and the NAV curve
    have no way to overlay user annotations (e.g. "earnings release
    on 2026-04-15"). A future `markPoint` / `markLine` API would let
    researchers tag events.

---

## Appendix A — File inventory verified during review

| File | Lines read | Notes |
|---|---|---|
| `web/src/components/CorrelationHeatmap.tsx` | 1-139 | full |
| `web/src/components/ReturnCurve.tsx` | 1-126 | full |
| `web/src/components/ScoreRadar.tsx` | 1-112 | full |
| `web/src/components/ScoreBar.tsx` | 1-37 | full |
| `web/src/components/TickerTape.tsx` | 1-189 | full |
| `web/src/components/Panel.tsx` | 1-57 | full |
| `web/src/components/StatCard.tsx` | 1-62 | full |
| `web/src/components/SparklineCell.tsx` | 1-22 | full |
| `web/src/components/EmptyState.tsx` | 1-35 | full |
| `web/src/components/Sparkline.tsx` | 1-168 | full |
| `web/src/components/CategoryPie.tsx` | 1-93 | full |
| `web/src/components/KLineChart.tsx` | 1-419 | full |
| `web/src/components/ReturnTag.tsx` | 1-46 | full |
| `web/src/utils/color.ts` | 1-73 | full |
| `web/src/utils/cssVar.ts` | 1-42 | full |
| `web/src/styles/theme.css` | 1-764 | full |
| `web/src/pages/BacktestDetail/index.tsx` | 1-334 | full |
| `web/src/pages/Macro/index.tsx` | 1-606 | full |
| `web/src/pages/ReturnComparison/index.tsx` | 1-164 | full |
| `web/src/pages/CorrelationAnalysis/index.tsx` | 1-117 | full |
| `web/src/pages/SectorRotation/index.tsx` | 1-944 | full |
| `web/src/pages/SignalDashboard/index.tsx` | 1-232 | full |
| `web/src/pages/ScoreRanking/index.tsx` | 1-120 | partial (column definitions) |

`web/src/utils/colorForValue.ts` is referenced in the task scope but
does **not** exist in the repo (`color.ts` is the only color helper
file). All color logic lives in `color.ts` and the CSS token layer in
`theme.css`.

## Appendix B — Cross-cutting patterns

- **Raw `var(--xxx)` strings inside ECharts options** appear in
  `BacktestDetail/index.tsx:119-128` and the `Macro` chart option
  (`web/src/pages/Macro/index.tsx:394-420`). These will render as
  invalid color strings on every render — see P0-2 and P0-3.
- **`useEffect` theme listener pattern** is duplicated across 5+
  files (`CorrelationHeatmap`, `ReturnCurve`, `ScoreRadar`,
  `CategoryPie`, `SectorRotation`) with no shared hook. A
  `useChartThemeTokens()` hook would centralize the resolution and
  remove the `themeTick` state boilerplate.
- **Reduced-motion handling** is inconsistent: `BacktestDetail` and
  `Macro` set `animation: !prefersReducedMotion`, but the entrance
  re-animation on `notMerge` re-renders is not gated (P2-14).