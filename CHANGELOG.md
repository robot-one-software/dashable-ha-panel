# Changelog

## v0.7.6

- **Toggle knobs no longer vanish while a dashboard loads** — switching dashboards in the panel briefly rendered the sliders without their knobs (a WebKit layout quirk with the panel's fit-to-screen scaling); the knobs now size themselves explicitly and are visible from the first frame.
- **Percentage transform** — a new value transform turns fractions into percentages (0.62 → 62%): set what raw value equals 100% (1, 255, 1000, …), pick decimal places, and optionally append the % sign. Available on every widget with Transformations, including Entity Value.

## v0.7.5

- **Toggle sliders for media players and covers** — the toggle slider can now power TVs and speakers on/off, and open/close covers like garage doors and blinds (it knows a "playing" TV is on and an "opening" garage is open, and uses the proper open/close services for covers).
- **Reverse On/Off option** — flip the slider's direction per widget, e.g. so ON means closed for a blind. Purely visual; the toggle still switches states as expected.

## v0.7.4

- **Cameras recover after backgrounding the app (iOS)** — switching away from the Home Assistant app suspends WebRTC, and iOS often kills the streams without any error the panel could react to, leaving black squares until a manual page refresh. The panel now health-checks every camera the moment the app returns to the foreground: connections that died are reconnected immediately, streams that look connected but stopped decoding frames are detected within ~1.5s and restarted, and paused video elements are resumed.

## v0.7.3

- **Controls-only media player is now a true strip** — with artwork and track info hidden, the transport buttons float to the top with no leftover header space, and the widget can shrink to a ~50px bar (buttons scale down automatically below 70px tall).

## v0.7.2

- **Media Presets now work in the panel** — preset buttons used to need Dashable's cloud library, which doesn't exist inside Home Assistant, so the widget crashed. Each button now carries an embedded copy of its preset. **To migrate existing widgets:** open the dashboard once in the Dashable editor (the widget refreshes its embedded copies automatically), save, then press Sync in the panel.
- **Media player: controls-only mode** — new "Show Artwork" and "Show Track Info" toggles let you strip the widget down to just the transport buttons.
- **Springier page snap** — going to another page now overshoots slightly and settles back, like a real springboard.

## v0.7.1

- **"Go to Page" everywhere** — the page-snap action is now available on every widget that supports navigation: images, camera streams, WebRTC players, visual boxes (including shape/vector drawings), buttons, and icons. Tap a full-screen camera to snap to the next page, or give a visual box region a page action.

## v0.7.0

- **Dashboard pages (springboard screens)** — a fixed-size dashboard can now be several screens side by side. Viewers see one page at a time; buttons or icons with the new "Go to Page" action snap between them with a smooth slide, exactly like an iPhone home screen. All pages stay live while off-screen — camera streams keep playing, so paging back is instant. Set the page count under Dashboard properties in the editor, design across the numbered page boundaries, and sync.

## v0.6.1

Bug-fix release for three panel issues found in live debugging.

- **Images no longer cache as blank** — the offline image cache could save a truncated file when a CDN streamed slowly (the first network chunk was treated as the whole file). A truncated PNG decodes as a fully transparent image, so affected images rendered as nothing. Downloads now read to the end and verify the byte count against the server's declared length. **After updating, press Sync once** — it re-downloads cached images and heals any blank ones.
- **Connection Monitor works in the panel** — it pointed at your Dashable connection id, which doesn't exist inside HA, and showed a broken "select a connection" state. It now monitors the panel's own Home Assistant connection (green when connected).
- **Agenda widget no longer crashes** — it read the calendar-events store before the first fetch and hit an "unavailable in HA viewer" error box; the store is now seeded correctly.

## v0.6.0

- **Create dashboards straight from the panel** — "New for this screen" now asks for a name right in Home Assistant and creates the dashboard in your Dashable account through the integration's sync token. No Dashable login needed on the device: the panel measures the screen, the dashboard is created at exactly that size, appears in the picker immediately, and a confirmation tells you it's ready to design at my.dashable.app. (Requires a Home Assistant restart after updating — the integration gained a new command.)

## v0.5.1

- **"New for this screen" toolbar button** — creates a new dashboard sized exactly for the device you're viewing on. The panel measures its own usable area and opens the Dashable editor with the create dialog pre-filled to that resolution — no more relaying screen sizes by hand when your only access to a device is the Home Assistant app.

## v0.5.0

Stage widget maturity release: production-style camera switching.

- **Any widget can be a Stage member** — not just groups. Drop a WebRTC player, camera, or single widget straight onto the roster; it renders scaled into its slot.
- **Show at home when off stage** — a member can keep its normal spot on the dashboard and "snap" onto the stage only while its rules fire (e.g. a camera thumbnail that jumps to the hero slot on motion, then returns home). The home copy hides only while the member is actually occupying a stage slot.
- **Priority-zero semantics** — base priority 0 (or below) keeps a member off the stage entirely; a boost rule then stages it only while the rule matches. Clean choreography for motion-driven camera walls.
- **Custom slot layouts** — design your own numbered zones (any position/size, per-slot horizontal & vertical alignment, aspect-ratio lock). Members fill zones in priority order: slot 1 = most important.
- **Persistent WebRTC streams** — camera streams now survive moving between the stage and the dashboard, changing slots, and brief hides. No more spinner and full reconnect on every move: streams are shared, kept alive through transitions, and two widgets showing the same camera share one connection.

## v0.4.0

A large feature release bringing the panel viewer up to date with the Dashable web app.

- **Calendar & Agenda widgets now work in the panel** — events are fetched through Home Assistant's own API instead of a cross-origin request that CORS blocked.
- **Looping video backgrounds** — image widgets play `.mp4`/`.webm` URLs as muted, looping video. The offline cache now downloads referenced videos too, so they keep playing without internet.
- **New Stage widget** — a region whose occupants are chosen live by rules and priority: e.g. show the sports scoreboard while a game is on, otherwise a camera; boost a camera into the hero slot when it sees motion. Auto/hero/split/grid layouts, fit or fill scaling.
- **Event Log feed** — the Historical Ticker gains a "Feed" mode: events slide in at the top with live "5m ago" timestamps, older rows push down. Per-entity value filters ("only log 'on'") and custom event text.
- **Smart Repeater upgrades** — live sorting (numeric-aware) and value filters, so lists like battery levels re-order themselves and can show only entries below a threshold.
- **Dynamic colours** — visual box and icon colours can bind to a light's live colour (`entity:light.x`), with graceful fallbacks.
- **Tappable visual boxes** and camera streams that can fill their tile (`cover` fit) for uniform camera walls.
- **Fixes**: 3D-tilted groups losing touch response on part of the widget; circular visual boxes' borders being clipped flat when combined with the glass effect; six widget types invisible inside groups on older panels; smoother gauge/radial rendering.


## v0.3.23

- **Conditional animated effects** — dashboard backgrounds and visual boxes can now switch their animated effect based on an entity (e.g. Colour Drops while it’s raining, off otherwise). Configure under Background Effects (dashboard) or Conditional Styling (visual box) in the editor.
- Visual box animated effects are now clipped to the box’s shape (heart, star, circle…) instead of spilling into the square bounds.
- Fixed a stray "0" appearing under a visual box after clearing its border.

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
