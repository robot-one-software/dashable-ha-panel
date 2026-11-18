# Panel bundle provenance

`custom_components/dashable/frontend/dashable-panel.js` is a compiled artefact.
It is **not** authored here. Since 0.11.0 it is built from the public
[robot-one-software/dashable-viewer](https://github.com/robot-one-software/dashable-viewer)
repository, and `viewer-source.json` at the root of this repository names the
tag it was built from, the commit of the Dashable app the source was exported
from, and the SHA-256 of the file. The Verify bundle workflow rebuilds the
pinned tag on every push and the Release workflow will not publish unless the
rebuilt file is byte-identical to the committed one.

The viewer repository is itself an export: a script in the Dashable app
repository (`billwhyte/HADashboard`, private) walks every import from the
viewer entry and copies exactly those files, with their paths unchanged, so
the same Vite config builds them there. Its `SOURCE.json` records the app
commit each export came from.

## Why this file exists

The 0.10.1 bundle was rebuilt from app `master` HEAD, which was seven weeks
ahead of the commit the 0.10.0 bundle had been built from. The net size change
was 850 bytes, which reads as "nothing moved" — but ten widget renderers had in
fact changed. The CHANGELOG said nothing about any of it. Net minified bytes
measure the size of the output, not the size of the behaviour change; a release
that cannot name its source commit cannot tell the difference. (POT-2782.)

## How a bundle is released

1. **In the app repository.** Bump `PANEL_BUNDLE_VERSION` in
   `viewer/src/version.ts` (it is shown in the panel toolbar), commit, then
   export: `node scripts/export-viewer-source.mjs ../dashable-viewer`. The
   export builds the viewer with a sourcemap and refuses to finish if the
   bundle contains a file the import walk did not reach.
2. **In the viewer repository.** If `package.json` changed, `npm install` to
   refresh the lockfile — the export copies the app's lockfile verbatim, so
   this prunes it back to the viewer's own dependencies. Commit, tag `vX.Y.Z`
   (the tag must equal the version in `package.json`), push. The Build workflow
   typechecks, runs `npm test` (the security guards the export carries, on
   node's built-in runner), builds twice, fails if the two outputs differ, and
   attaches `dashable-panel.js` and its `.sha256` to the release.
3. **Here.** `scripts/update-bundle.sh vX.Y.Z` downloads that release's bundle,
   verifies the checksum, writes the bundle and `viewer-source.json`, and
   prints the row for the table below. Bump the manifest version, write the
   CHANGELOG entry, add the row, commit, tag, push.

## Rules

1. **Record the source below in the same commit that updates the bundle.**
   A bundle whose source is not written down is unauditable; CI now enforces
   the `viewer-source.json` half of this, the table is for people.
2. **Choose the export base deliberately.** Exporting from app `master` HEAD
   ships every app change merged since the last panel release, not just the one
   you set out to make. If some of that should not ship, export from a pinned
   commit instead.
3. **Declare the drift in CHANGELOG.md**, in user-facing terms, whenever the
   app commit moves by more than the change you intended. "No visible effect"
   is a fine thing to write; silence is not.
4. **Determine what actually ships from the module graph, not from paths.**
   A changed file under `src/components/dashboard/` is not necessarily in the
   panel's closure. The viewer repository's file list *is* the closure, so the
   intersection of the app's changed files with it is the list of shipped
   changes:

   ```sh
   # in the HADashboard checkout
   git diff --name-only <old-app-commit> <new-app-commit> \
     | grep -F -x -f <(cd ../dashable-viewer && git ls-files src viewer)
   ```

   Type-only modules are in that list but contribute no bytes; a change to one
   is a change to what the code means, not to what it does.

## Shipped bundles

| Panel release | Viewer tag | App commit | Bundle bytes | sha256 (first 16) |
|---|---|---|---|---|
| 0.11.1 | `v0.11.1` | `27c8e667` (`master`, 18 Nov 2026) | 2,332,308 | `e64ace1741ee9ddc` |
| 0.11.0 | `v0.11.0` | `8eeb4bba` (`master`, 16 Nov 2026) | 2,331,336 | `74d3863f8abfb2ff` |
| 0.10.5 | — | `6d37169c` (`master`, 15 Nov 2026) | 2,409,888 | `11e7c63297b7c1cb` |
| 0.10.4 | — | `4261c630` (`master`, 15 Nov 2026) | 2,409,790 | `b0364254e75ee6b5` |
| 0.10.3 | — | `84e1bb9a` (`master`, 15 Nov 2026) | 2,409,617 | `1887e838efef3f23` |
| 0.10.2 | — | `565a3b90` (`master`, 15 Nov 2026) | 2,409,388 | `4609d9f9c3178b2c` |
| 0.10.1 | — | `6f9a678d` (`master`, 15 Nov 2026) | 2,408,747 | `5fe53c51c65f3b47` |
| 0.10.1 (earlier untagged build, superseded) | — | `c9c87f7e` (`master`, 12 Nov 2026) | 2,407,525 | `07a985b55abc07f1` |
| 0.10.0 | — | built 25 Sep 2026; app commit not recorded at the time, `04676308` is the last `master` commit of that day | 3,079,573 | `8ee74c393e5ba223` |

Releases before 0.10.1 predate this file and have no recorded source commit.
Releases before 0.11.0 were built privately in the app repository; their
source is not published.
