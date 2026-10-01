---
name: Clinical Intelligence
colors:
  surface: '#f8f9ff'
  surface-dim: '#cbdbf5'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dce9ff'
  surface-container-highest: '#d3e4fe'
  on-surface: '#0b1c30'
  on-surface-variant: '#3d4947'
  inverse-surface: '#213145'
  inverse-on-surface: '#eaf1ff'
  outline: '#6d7a77'
  outline-variant: '#bcc9c6'
  surface-tint: '#006a61'
  primary: '#00685f'
  on-primary: '#ffffff'
  primary-container: '#008378'
  on-primary-container: '#f4fffc'
  inverse-primary: '#6bd8cb'
  secondary: '#565e74'
  on-secondary: '#ffffff'
  secondary-container: '#dae2fd'
  on-secondary-container: '#5c647a'
  tertiary: '#00638a'
  on-tertiary: '#ffffff'
  tertiary-container: '#007dad'
  on-tertiary-container: '#fcfcff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#89f5e7'
  primary-fixed-dim: '#6bd8cb'
  on-primary-fixed: '#00201d'
  on-primary-fixed-variant: '#005049'
  secondary-fixed: '#dae2fd'
  secondary-fixed-dim: '#bec6e0'
  on-secondary-fixed: '#131b2e'
  on-secondary-fixed-variant: '#3f465c'
  tertiary-fixed: '#c6e7ff'
  tertiary-fixed-dim: '#82cfff'
  on-tertiary-fixed: '#001e2d'
  on-tertiary-fixed-variant: '#004c6b'
  background: '#f8f9ff'
  on-background: '#0b1c30'
  surface-variant: '#d3e4fe'
  slate-bg: '#F8FAFC'
  card-bg: '#FFFFFF'
  sidebar-surface: '#0F172A'
  sidebar-elevated: '#1E293B'
  border-subtle: '#E2E8F0'
  border-strong: '#CBD5E1'
  brand-magenta: '#E91E63'
  brand-rose: '#FF6FA5'
  metric-ga4: '#F59E0B'
  metric-gsc: '#0284C7'
  metric-keywords: '#10B981'
  status-fresh: '#14B8A6'
  status-stale: '#EF4444'
typography:
  headline-xl:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.015em
  headline-md:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  data-metric:
    fontFamily: Inter
    fontSize: 28px
    fontWeight: '700'
    lineHeight: 32px
    letterSpacing: -0.02em
  data-table:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.02em
  label-xs:
    fontFamily: Inter
    fontSize: 10px
    fontWeight: '700'
    lineHeight: 12px
    letterSpacing: 0.04em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1.25rem
  gutter-desktop: 1.5rem
  margin: 1rem
  margin-desktop: 2rem
  space-2xs: 0.25rem
  space-xs: 0.5rem
  space-sm: 0.75rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2rem
  space-2xl: 3rem
---

## Brand & Style

This design system delivers an enterprise-grade medical analytics workspace bridging pediatric clinical authority with modern business intelligence. The aesthetic merges **Corporate / Modern** precision with high-density clinical data presentation. It must project uncompromising trust, scientific rigor, and operational clarity while remaining accessible to pediatric clinic administrators, CMOs, and marketing analysts.

Visual clarity prioritizes readability across dense data sets, operational monitoring, and multi-channel acquisition funnels (Google Analytics 4, Google Search Console, local patient bookings). The system avoids playful infant tropes, grounding itself in deep slate anchors, clinical teal precision, and targeted diagnostic badge systems to facilitate rapid decision-making.

## Colors

The palette balances institutional stability with purposeful data visualization accents.

- **Primary (`#0D9488`)**: Clinical teal signals actionable outcomes, selected filters, primary command triggers, and system active states.
- **Secondary (`#0F172A`)**: Deep obsidian navy anchors administrative sidebars, persistent left-rail navigation, and high-emphasis metric headings.
- **Tertiary (`#00ADEE`)**: Extracted from the parent identity, this electric cerulean highlights integration pathways, link structures, and secondary chart series.
- **Neutral (`#64748B`)**: Slate gray standardizes secondary metadata, axis labels, borders, and contextual helper text without competing with tabular values.

### Integration & Domain Badges
- **GA4 Orange-Amber (`#F59E0B`)**: Analytics events, conversion rates, and session logs.
- **Search Console Sky (`#0284C7`)**: Organic search impressions, queries, and indexing metrics.
- **Keyword Tracking Emerald (`#10B981`)**: SERP position increments and ranking gains.
- **Clinical Accent Magenta (`#E91E63`)**: Direct patient conversion points, urgent booking anomalies, and critical notices.

## Typography

The design system exclusively leverages **Inter** across all display, tabular, and navigational contexts to maximize legibility in data-dense interfaces.

- **Tabular Figures**: All numerical records, table metrics, and financial or volume data points must enforce OpenType `font-variant-numeric: tabular-nums` to guarantee vertical column alignment.
- **Hierarchy Disciplines**: Headings enforce modest negative tracking to maintain structural tightness on desktop dashboards. 
- **Data Densities**: `data-table` (13px/18px) balances rapid vertical scanning with comfortable touch-or-click targets for dense marketing matrices, keyword tables, and patient acquisition paths.

## Layout & Spacing

The workspace implements a **fluid grid** architecture framed by a fixed-width deep slate sidebar (`260px` expanded, `72px` collapsed).

- **Grid Architecture**: The central operational view utilizes a 12-column layout. Desktop screen sizes (>1440px) maintain a `1.5rem` (`24px`) gutter and `2rem` outer padding, ensuring analytics modules stretch smoothly across widescreen enterprise monitors without drifting apart.
- **Rhythm**: Component spacing strictly adheres to an 8-point structural increment, with 4px (`space-2xs`) micro-spacers dedicated to table row compression, indicator tags, and status dots.
- **Reflow Logic**: Below 1024px, the left navigation transitions to an off-canvas drawer, multi-column KPI rows step down from 4 columns to 2 columns, and data tables enable horizontal overflow scroll with fixed primary index columns.

## Elevation & Depth

This system avoids heavy drop shadows, instead utilizing **low-contrast outlines** paired with subtle ambient diffusion to maintain clinical cleanliness and surgical precision.

- **Level 0 (Canvas Base)**: `#F8FAFC` flat canvas surface.
- **Level 1 (Card & Content Blocks)**: `#FFFFFF` surface enclosed by a 1px border (`#E2E8F0`). A light ambient shadow (`0 1px 3px rgba(15, 23, 42, 0.04), 0 1px 2px rgba(15, 23, 42, 0.02)`) provides separation against the slate canvas.
- **Level 2 (Dropdowns, Date Pickers, Hover States)**: `#FFFFFF` surface, `#CBD5E1` border, backed by `0 10px 15px -3px rgba(15, 23, 42, 0.08), 0 4px 6px -4px rgba(15, 23, 42, 0.03)`.
- **Level 3 (Modal Dialogs & Export Overlays)**: Centered planar modals elevated with `0 20px 25px -5px rgba(15, 23, 42, 0.12), 0 8px 10px -6px rgba(15, 23, 42, 0.04)` over a 50% opacity slate scrim (`#0F172A80`).
- **Sidebar Depth**: Created purely through tonal contrast using `#0F172A` with `#1E293B` active module highlights, bypassing artificial shadows.

## Shapes

The design system employs **Soft** boundary definitions (`roundedness: 1` — base `0.25rem` / `4px`, containers `0.5rem` / `8px`).

This subtle radius creates a crisp, professional, and institutional dashboard feel suitable for health care administration, steering clear of ultra-rounded consumer geometries while remaining cleaner than stark brutalist edges.

- Form fields, buttons, and badges leverage the 4px baseline radius.
- Analytical tiles, chart cards, and modal sheets use the 8px container radius (`rounded-lg`).
- Status dots and contextual source indicator pips retain full circular bounds (50%).

## Components

### Buttons
- **Primary Action**: Solid teal (`#0D9488`) fill, white text, 4px border radius. Hover: `#0F766E`. Active: `#115E59`.
- **Secondary Action**: Slate border (`#CBD5E1`), background white, text `#0F172A`. Hover: `#F8FAFC`.
- **Export Trigger**: Primary background with integrated download vector icon, right-aligned chevron for dropdown format choices (Excel, CSV, PDF).

### Chips & Source Status Badges
- Compact indicators (height: 22px, font: `label-xs`, uppercase).
- **GA4**: `#FFFBEB` fill, `#F59E0B` text, `#FDE68A` border.
- **Search Console**: `#F0F9FF` fill, `#0284C7` text, `#BAE6FD` border.
- **Keywords**: `#ECFDF5` fill, `#10B981` text, `#A7F3D0` border.

### Data Tables
- Header row with `#F8FAFC` background, 11px uppercase bold labels in `#64748B`, 1px solid bottom border (`#E2E8F0`).
- Row height: 44px compact, hover state `#F1F5F9`.
- Numerical columns right-aligned with monospace/tabular Inter figures.

### Input Fields & Date Pickers
- Border: 1px `#CBD5E1`, background `#FFFFFF`, text `#0F172A`, placeholder `#94A3B8`.
- Focus ring: 2px `#0D9488` with 2px offset.
- Date Range Presets: Floating side-segmented bar (Today, Last 7 Days, Last 30 Days, MTD, Custom Range).

### KPI Trend Cards
- Top micro-row: KPI label in `#64748B` + contextual info tooltip.
- Center value: `data-metric` typography (`28px` bold `#0F172A`).
- Footer row: Delta percentage pill (positive: `#DCFCE7` bg with `#15803D` text; negative: `#FEE2E2` bg with `#B91C1C` text) paired with comparative timeframe note.

### Data Freshness Banners
- Top-anchored contextual bar displaying last sync timestamp, background `#F0FDFA`, border `#CCFBF1`, text `#0F766E`, right-aligned quick-sync button.

### Modal Dialogs (Excel Export)
- Centered 480px width sheet, `#FFFFFF` surface with `#E2E8F0` border.
- Includes step-wise dataset toggles (Date span, Column inclusions, Masked patient data flags) with clear action footer (Cancel vs. Generate `.xlsx`).