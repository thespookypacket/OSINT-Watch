---
version: alpha
colors:
  primary: '#16796b'
  background: '#f4f6f8'
  surface: '#ffffff'
  ink: '#122333'
  muted: '#526172'
  border: '#d7dfe5'
  fire: '#c44914'
  warning: '#926000'
  quake: '#285bb5'
typography:
  body:
    fontFamily: 'IBM Plex Sans, system-ui, sans-serif'
  utility:
    fontFamily: 'IBM Plex Mono, monospace'
rounded:
  panel: '6px'
  control: '4px'
spacing:
  unit: '4px'
  gutter: '24px'
components:
  button:
    rounded: '{rounded.control}'
    backgroundColor: '{colors.primary}'
    textColor: '{colors.surface}'
  page:
    backgroundColor: '{colors.background}'
    textColor: '{colors.ink}'
  mutedLabel:
    textColor: '{colors.muted}'
  divider:
    backgroundColor: '{colors.border}'
  fireLabel:
    textColor: '{colors.fire}'
  warningLabel:
    textColor: '{colors.warning}'
  quakeLabel:
    textColor: '{colors.quake}'
---
# OSINT Watch

## Overview
An operational cartographic desk for a homelab operator monitoring fixed sites.
Product register. The map is the focal point; source freshness is always visible.
The generated concept establishes the navy rail, light map, horizontal metric strip,
exposure side panel and compact event table. Sample concept numbers are never production data.

## Colors
The runtime owner is frontend/src/styles.css. Named colors above map to corresponding
CSS custom properties. White surfaces on cool gray, navy navigation, restrained teal actions.
Hazard categories use consistent color plus text; never color alone.

## Typography
IBM Plex Sans for product controls and headings; IBM Plex Mono for time, distance and counts.
Fonts are bundled locally. Body 15px, labels 13px, heading 28px. English UI; dates display local
time with explicit timezone in event details. Source content retains its original language.

## Layout
224px navigation rail, 24px main gutter, 1fr/310px map and exposure grid. At 1100px the
exposure panel moves below the map; at 720px navigation becomes a horizontal scroll row.
Forms use natural page scroll. Tables own horizontal overflow; map has a fixed minimum height.

## Elevation & Depth
Thin borders define panels. Only map controls and the native modal dialog have shadows.
No gradients, decorative glow, or fabricated live counters.

## Shapes
6px panel corners and 4px controls, no nested card grids. Signature: the map and adjacent
source-attributed exposure ledger read as one working surface.

## Components
Shared Button, Field, Secret, Modal, Empty and StatusMessage are canonical. Lucide outline
icons use 18px size and 1.7 stroke weight. Motion only for hover feedback; reduced motion honored.
Native selects and dates deliberately retain platform popup behavior.

## Do's and Don'ts
Show missing data as missing. Keep hotspots and fire perimeters distinct. Use real evidence
links. Do not render provider HTML, report peaceful protests as high-risk by default, show
illustrative data as live, or let local AI replace source evidence.

## Dark appearance
`styles.css` owns both palettes through semantic custom properties; `data-theme` selects
light/dark. Dark background #0d1822, surface #192a39, text #e5edf4, muted #afbdcb,
border #384d60 and accent #78d4bf extend the navy/teal identity. Solid action buttons
retain #16796b with white labels. Status surfaces use separate neutral, info, warning,
fire, success and error tokens. Navigation has its own background token, separate from text.
Native controls use `color-scheme`; map controls share surface/text tokens. Hazard geometry
colors are never inverted. The default OpenFreeMap Liberty map switches to its Dark style;
custom basemap URLs retain their configured style. ThemeSelect is the shared native selector.
