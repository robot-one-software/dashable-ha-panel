# Changelog

## v0.3.22

- Fixed several widget types rendering as nothing when placed **inside a group**: Linear Gauge, Color Light, Insight Graph, Smart Group (Viewer), Web Snippet, and Flip Widget. They appeared in the group editor but vanished on the dashboard and in the panel.

## v0.3.21

- The needle Gauge now has a **Show Value Text** toggle (hide it for a clean arc-only gauge) and a **Decimal Places** option — no more surprise decimals like 2407.38; leave it blank to keep the previous automatic behaviour.

## v0.3.20

- Animated background effects now render **inside the dashboard** — above the solid background colour and behind every widget — instead of around it. A solid colour plus an effect on top now works as expected.
- Fixed effect animations stuttering/restarting every ~half-second; they now run continuously and smoothly.

## v0.3.19

- **17 animated background effects** — the new effects system renders in the panel: Floating Dots (rebuilt with full-screen coverage and colour control), Floating Orbs, Morphing Bubbles, Gradient Flow, Aurora, Parallax Stars, Twinkling Stars, Snowfall, Ash Fall, Colour Drops, Cyber Particles, Fireflies, Bokeh, Sliding Diagonals, Floating Shapes, Ripples, and Cascading Waves. Configure per dashboard (or inside Visual Boxes) in the Dashable editor with colours, density, speed, size, and intensity.

## v0.3.18

- Fixed image widgets going blank after a page reload (a transition race, most visible with background removal or cropping enabled) — the widget showed "configure image source" until the URL was re-entered.
- Fixed the Insight Graph showing "WebSocket not connected" after a reload — the history fetch now waits for the Home Assistant connection and fires as soon as it's up.

## v0.3.17

- Fixed the Radial Progress ring not rendering in "single colour (morphs with value)" mode.
- Much smoother colour blending on the gauge's blended-spectrum arc, the radial spectrum ring, and the linear gauge's spectrum bar (finer gradient resolution, no visible colour steps or seams).

## v0.3.16

- **Gauge overhaul** — the needle now spring-animates (no more jumping), and the arc has three modes: classic colour bands, a smooth blended spectrum, or fill-to-value in a colour that morphs with the reading. Optional glow and value-follows-colour.
- **Radial Progress overhaul** — new spectrum mode (colour ranges painted around the ring), segmented-ring style with adjustable count and gap, glow, and value-follows-colour. Colour blending now matches the linear gauge exactly.
- Existing gauges keep rendering exactly as before — all new options are opt-in.

## v0.3.15

- New **Linear Gauge** widget — a display-only animated bar for live values (energy, temperature, volume…). Spring-animated so changing values morph smoothly instead of jumping; horizontal or vertical; solid / segmented / dots / retro styles; user-defined colour ranges that blend as the value moves (single-colour or spectrum modes); optional ticks and value labels.

## v0.3.14

- Image widgets can now be cropped with per-edge sliders (top/bottom/left/right, set in the Dashable editor). Cropping runs in the same one-time pass as background removal, so the two combine cleanly.

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
