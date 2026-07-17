# Changelog

## v0.3.13

- **Offline image cache** — internet images referenced by dashboards are now downloaded once by the integration, stored on your Home Assistant box, and served locally. Dashboards render fully offline and images load faster. Pressing **Sync** also refreshes the cached copies.
- **Background removal (chroma key)** — image widgets can strip a background colour to transparency (pick the colour, tolerance, and edge softness in the Dashable editor). Processed once per image, so kiosks pay no ongoing cost.

## v0.3.12

- Image widgets can now swap their image based on a condition (conditional styling → Image Source), with fade/dissolve or slide transitions between images.

## v0.3.11

- Weather widgets no longer show a stuck loading spinner in the panel. Their data source isn't available inside Home Assistant, so they now simply don't appear instead of spinning.

## v0.3.10

- WebRTC camera widgets now automatically reconnect after a transient stream error (e.g. a go2rtc/camera hiccup or network blip) instead of showing a stuck error until you refresh. Retries use a backoff and pause while the tab is hidden.

## v0.3.9

- Local Media widget (capture cards / webcams) now works in the panel over HTTPS: the configured device is matched by name so a device picked in the Dashable web app resolves inside Home Assistant. When Home Assistant is served over plain HTTP, the widget now shows a clear "needs HTTPS" message instead of silently disappearing.

## v0.3.8

- Dashable brand icon now shows in the Home Assistant integrations panel and HACS, using the built-in local brand images (Home Assistant 2026.3+).

## v0.3.7

- Fixed the Insight Graph widget failing to load its chart ("fetch failed") inside the panel — history is now fetched over the authenticated Home Assistant WebSocket instead of a REST call that required a token the panel doesn't have.
- Fixed the Web Snippet widget's page/media proxy not working in the panel.
- Fixed the color-light widget's power button still floating on top of other widgets regardless of stacking order.

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
