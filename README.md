# Dashable for Home Assistant

Run your **[Dashable](https://dashable.app)** dashboards **inside Home Assistant** —
as a sidebar panel, synced from your Dashable account and fully local at
runtime.

Dashable is a drag-and-drop dashboard builder for Home Assistant: design rich,
good-looking touch dashboards in a web editor (widgets for entities, cameras,
media, gauges, charts, clocks, weather, and more), then view and control them
anywhere. This integration brings those dashboards **into Home Assistant
itself** — no separate app, no browser bookmarks, and it keeps working with no
internet at all.

- **Web editor:** <https://my.dashable.app>
- **Learn more / sign up:** <https://dashable.app>

---

## What you need

1. **A Dashable account** and at least one dashboard.
   Sign up free at <https://dashable.app> and build a dashboard in the editor at
   <https://my.dashable.app>.
2. **A sync token** from Dashable (Settings → **HA Panel**). This is how the
   integration securely pulls your dashboards — see [Setup](#setup).
3. **Home Assistant 2024.6 or newer** with [HACS](https://hacs.xyz) installed.

You do **not** need to expose Home Assistant to the internet, set up HTTPS, or
paste any Home Assistant tokens into Dashable. The panel talks to Home
Assistant directly through your existing logged-in session.

---

## Install

1. In Home Assistant, open **HACS → three-dot menu → Custom repositories**.
2. Add:
   - **Repository:** `https://github.com/robot-one-software/dashable-ha-panel`
   - **Category:** `Integration`
3. Find **Dashable** in HACS, **Download**, then **restart Home Assistant**.

## Setup

1. In Dashable (web), go to **Settings → HA Panel** and **Generate a sync token**.
   Copy it — it's shown only once.
2. In Home Assistant, go to **Settings → Devices & Services → Add Integration**,
   search for **Dashable**, and paste the sync token.
   (Leave the URL as `https://my.dashable.app` unless you're on a beta build.)
3. **Dashable** now appears in your Home Assistant sidebar.

That's it — no YAML and no manual files.

---

## Using the panel

Open **Dashable** in the sidebar. A slim toolbar sits at the top:

- **Dashboard picker** — switch between all your synced dashboards.
- **Sync** — pull the latest from Dashable after you change a dashboard.
- **Edit** — opens the Dashable web editor (<https://my.dashable.app>) in a new
  tab to make changes.

The toolbar **auto-hides** after a few seconds for a clean full-screen look;
tap the top edge (a small grabber peeks there) to bring it back.

Buttons inside a dashboard that navigate to another dashboard work in-panel,
and dashboard-level features (conditional visibility, animated backgrounds,
etc.) render just like the web app.

---

## How it works

- **Synced, not live-linked.** The integration pulls your dashboard definitions
  from Dashable and stores them on your Home Assistant box. They keep working
  across restarts, even with no internet.
- **Local at runtime.** Entity states, camera streams (WebRTC), media, and
  service calls go **straight to Home Assistant** — not through Dashable.
- **Sealed on disk.** Stored dashboards are compressed and tagged so they aren't
  trivially hand-edited; editing happens in the Dashable web editor.
- **Authenticated transport.** The panel loads dashboards over Home Assistant's
  own authenticated connection — they're never exposed on an unauthenticated
  URL — and connection references in a dashboard are automatically mapped to
  *this* Home Assistant instance.
- **Auto-updating frontend.** The panel's asset URL is versioned by the
  integration, so HACS updates are picked up without any cache-busting steps.

---

## Notes & limitations

- **View / control only.** Editing is done in the Dashable web editor; use the
  **Edit** button in the toolbar.
- Widgets that depend on Dashable's cloud (text-to-speech announcements, the
  cloud image proxy, weather locations) show a small "unavailable" tile in the
  panel.
- Requires Home Assistant **2024.6+**.

## Troubleshooting

- **"Sync token was rejected"** — generate a fresh token in Dashable → Settings
  → HA Panel, then reconfigure the integration.
- **A dashboard doesn't appear** — press **Sync** in the panel toolbar. New and
  renamed dashboards land after a sync.
- **Panel looks stale after an update** — the asset URL is versioned
  automatically, but if a browser still shows an old build, hard-refresh the
  Home Assistant tab once.

---

Dashable is a product of Robot One Software. Home Assistant is a trademark of
the Open Home Foundation.
