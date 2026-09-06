# OSINT Watch interaction contract

Business source: the user-approved implementation plan; docs/architecture.md records operational policy.
Single administrator, source-specific export access, 7-day raw and 90-day normalized retention.
No billing. Asset deletion removes its exposure alerts; event evidence remains until retention cleanup.

| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
|---|---|---|---|---|
| Select/Listbox | Native select | DESIGN.md | native | keyboard and narrow viewport |
| Date | Native input | DESIGN.md | native | keyboard |
| Form | Field / AssetEditor | API schema | create/edit | browser import and validation |
| Scrollbar | styles.css | DESIGN.md | global | computed style |
| Toast | StatusMessage | UX-CONTRACT.md | info/error/success | live region |
| CRUD | API + page components | API schema | save to list | end-to-end |

Navigation and category/time filters persist in URL. Credentials stay in HttpOnly cookies;
new API tokens are shown once in a masked field and never saved to client storage.
All writes show pending state, disable repeat submit, preserve errors and entered values.
Save returns to owning list and refreshes it; cancel keeps list state.
Native dialog supplies focus trapping, Escape, and inert background; close restores trigger focus.
Delete/revoke actions require an explicit object-named confirmation dialog.
Event inspector is a non-modal region. Empty feeds display source setup guidance.
Network failures leave retry available and never masquerade as empty healthy data.

NetBox uses the shared Button and StatusMessage in Saved assets. Its secret is deployment-only.
Sync queues once, polls status, refreshes assets on success, and preserves prior results on failure.
Imported names/coordinates are read-only; exposure rules remain editable. Missing/unlocated
imports are retained with an explicit monitoring-paused label, and are omitted from map/exposure.

Appearance is a browser-local Light/Dark/System preference, available on the login screen
and every workspace page, including mobile. System is the default and follows live OS
changes; explicit choices persist across reloads and synchronize across tabs. Storage errors
leave the control usable for the current session. An early head script applies the preference
before CSS loads. Theme changes preserve filters, form drafts and map camera/overlay settings.
