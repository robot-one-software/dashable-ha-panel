# Changelog

## v0.3.6

- Fixed WebRTC camera streams timing out with "Called in wrong state: stable" — duplicate/late SDP answers from Home Assistant's WebRTC signaling are now ignored instead of breaking the stream.
- Fixed the color-light and color-picker widgets always rendering on top of other widgets regardless of stacking order.
- Fixed a stray top border on the color-picker's colour-temperature row when colours are disabled.

## v0.3.5

- Toolbar **Edit** button — opens the Dashable web editor.
- Expanded setup documentation and one-click "My Home Assistant" install badge.
- Dashable brand assets (icon + logo).

## v0.3.4

- Fixed-size dashboards anchor to the top-left (better for kiosks).

## v0.3.3

- Dashboard animated background effects (wallpapers) now render in the panel.

## v0.3.2

- Buttons that navigate to another dashboard now switch dashboards in-panel.

## v0.3.1

- Dashboard-level conditional visibility now works in the panel.
- Auto-hiding toolbar for full-screen dashboards.

## v0.3.0

- HACS **integration** with a config flow — no YAML.
- Syncs all dashboards from your Dashable account, stored locally.
- Dashboard **picker** and **Sync** button; offline-resilient.
- Dashboards stored sealed (compressed) on the Home Assistant box.
- Auto-versioned panel asset (no manual cache-busting).

## v0.2.x

- WebRTC camera streaming, display fonts, dark theme, seamless background.

## v0.1.0

- First preview: Dashable dashboards rendered inside Home Assistant.
