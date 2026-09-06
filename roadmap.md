# OSINT Watch roadmap

These are proposed additions for richer physical-hazard coverage and operational
workflows, not implemented features or delivery commitments. Prioritize information
that explains how hazards could affect saved sites, while preserving source
attribution and uncertainty.

## First priority

- **Air quality near sites:** Add AQI and PM₂.₅ observations, trends, and forecasts
  using AirNow. Help identify poor air quality near sites, including impacts far
  from wildfire boundaries; do not automatically attribute pollution to a fire.
  Reference: [AirNow API documentation](https://docs.airnowapi.org/webservices).
- **River levels and flood forecasts:** Add nearby gauge observations, rising-water
  trends, flood-stage thresholds, and forecast crests using NOAA's National Water
  Prediction Service. Keep observations distinct from forecasts, and gauge
  thresholds distinct from predicted inundation boundaries.
  Reference: [NOAA NWPS API](https://water.noaa.gov/about/api).
- **Site-level coverage:** Show which hazard sources provide usable coverage for
  each site, their last successful updates, and known geographic gaps. Make
  missing or stale coverage explicit rather than implying an absence of hazards.

## Following additions

- **Official evacuation orders and warnings:** Display official boundaries,
  issuing authorities, update times, and cancellations. Preserve the distinction
  between warnings and orders. Coverage depends on selected jurisdictions and
  verification of their available public feeds.
- **Regional road closures and access disruption:** Identify potential disruption
  where reported closures intersect known site access roads, including sites
  outside the hazard boundary. Coverage depends on selected jurisdictions and
  available regional feeds; do not imply nationwide coverage or guaranteed access.
  Reference: [Bay Area 511 Traffic API](https://511.org/open-data/traffic), an example
  regional source.
- **Wildfire progression playback:** Animate retained perimeter revisions, show
  newly affected areas, and highlight observed changes in proximity to saved
  sites. Clearly label this as observed perimeter history, not a spread prediction.

## Selected operational features

The following nine features were selected for the roadmap. Their implementation
order has not yet been set.

- **“What changed?” briefings:** Summarize new hazards, worsening conditions, newly
  exposed sites, and resolved alerts since the user's last visit. Link each change
  to its underlying evidence.
- **Site intelligence pages:** Give each saved site a dedicated view of current
  hazards, exposure history, coverage gaps, NetBox details, contacts, and response
  notes.
- **Smarter notifications:** Add per-site subscriptions, quiet hours, repeat-alert
  cooldowns, and escalation for unacknowledged alerts. Focus notifications on
  meaningful changes rather than repeated reports of the same condition.
- **Incident workspaces:** Let analysts group related reports, track affected
  sites, assign tasks, and maintain notes and a timeline. Preserve each source's
  independent evidence when reports are grouped.
- **Network and service dependencies:** Map relationships between sites, circuits,
  upstream facilities, and business services to show potential downstream impacts
  when a dependency is exposed. Keep potential exposure distinct from a confirmed
  outage.
- **Route and corridor monitoring:** Support fiber routes, supply corridors, and
  travel routes as line assets with configurable hazard-distance buffers,
  alongside saved points and areas. Detect exposure along a route even when its
  endpoints are outside the hazard area.
- **Rule previews and historical testing:** Show which retained events would
  trigger alerts before an exposure rule is enabled or changed. Use previews to
  tune noisy rules without sending real notifications.
- **Saved operational views:** Save named combinations of map extent, sites,
  layers, and filters so recurring monitoring views are easy to reopen.
- **Evidence-backed report exports:** Export daily briefings and incident reports
  with maps, affected sites, timestamps, evidence links, and uncertainty. Apply
  source-specific export permissions to report content.

## Maybe later

- **Business criticality and ownership tags:** Consider tagging sites by business
  importance, owner, region, and business function to prioritize responses without
  changing the underlying hazard severity. Deferred rather than selected for the
  current roadmap additions.

## Suggested hazard-coverage sequence

Start with air quality, river forecasts, and site-level coverage. Then select the
states and counties that matter most for evacuation and road-closure integrations.
Add wildfire progression playback using retained revisions, with source update
times and gaps visible throughout.
