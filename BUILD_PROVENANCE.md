# Panel bundle provenance

`custom_components/dashable/frontend/dashable-panel.js` is a compiled artefact.
It is **not** authored here — it is built by `npm run build:viewer` in the
Dashable app repository (`billwhyte/HADashboard`), whose `viewer/` directory
compiles the same widget engine the web app uses, with the Dashable-only
integrations (Firebase, auth, the Next runtime) aliased to inert stubs.

Because the bundle's source lives in another repository, the commit it was built
from is the only thing that says what is in it. Record it here on every rebuild.

## Why this file exists

The 0.10.1 bundle was rebuilt from app `master` HEAD, which was seven weeks
ahead of the commit the 0.10.0 bundle had been built from. The net size change
was 850 bytes, which reads as "nothing moved" — but ten widget renderers had in
fact changed. The CHANGELOG said nothing about any of it. Net minified bytes
measure the size of the output, not the size of the behaviour change; a release
that cannot name its source commit cannot tell the difference. (POT-2782.)

## Rules

1. **Record the source commit below in the same commit that updates the
   bundle.** A bundle whose source commit is not written down is unauditable.
2. **Choose the rebuild base deliberately.** Building from app `master` HEAD
   ships every app change merged since the last panel release, not just the one
   you set out to make. If some of that should not ship, build from a pinned
   commit instead.
3. **Declare the drift in CHANGELOG.md**, in user-facing terms, whenever the
   source commit moves by more than the change you intended. "No visible
   effect" is a fine thing to write; silence is not.
4. **Determine what actually ships from the module graph, not from paths.**
   A changed file under `src/components/dashboard/` is not necessarily in the
   panel's closure — the viewer entry pulls in a subset, and app-router pages,
   stubbed modules and type-only modules are not in it. Build with
   `--sourcemap` and intersect the `sources` array of `dashable-panel.js.map`
   with the changed-file list:

   ```sh
   # in the HADashboard checkout
   npx vite build --config viewer/vite.config.ts --sourcemap
   python3 - <<'PY'
   import json, subprocess
   m = json.load(open('viewer/dist/dashable-panel.js.map'))
   closure = {s.replace('../../', '') for s in m['sources'] if 'node_modules' not in s}
   changed = subprocess.run(
       ['git', 'diff', '--name-only', '<old-base>', '<new-base>'],
       capture_output=True, text=True).stdout.split()
   for f in sorted(set(changed) & closure):
       print(f)
   PY
   ```

   Caveat: a module whose exports are all types is erased at transpile and so
   never appears in `sources`. That is correct for behaviour — it contributes no
   bytes — but it means the intersection is a floor on files, not on types.

5. **Verify the shipped file reproduces.** A `--sourcemap` build is
   byte-identical to the shipped one once the trailing `//# sourceMappingURL`
   comment is stripped, so the sourcemap can be trusted to describe the
   artefact actually in this repository:

   ```sh
   python3 - <<'PY'
   import re, hashlib
   a = open('viewer/dist/dashable-panel.js', 'rb').read()
   b = open('<panel-repo>/custom_components/dashable/frontend/dashable-panel.js', 'rb').read()
   a = re.sub(rb'//# sourceMappingURL=[^\n]*\n?$', b'', a)
   print(hashlib.sha256(a).hexdigest()[:16], hashlib.sha256(b).hexdigest()[:16], a == b)
   PY
   ```

## Shipped bundles

| Panel release | App commit | Bundle bytes | sha256 (first 16) |
|---|---|---|---|
| 0.10.1 (untagged) | `c9c87f7e` (`master`, 12 Nov 2026) | 2,407,525 | `07a985b55abc07f1` |
| 0.10.0 | built 25 Sep 2026; app commit not recorded at the time, `04676308` is the last `master` commit of that day | 3,079,573 | `8ee74c393e5ba223` |

Releases before 0.10.1 predate this file and have no recorded source commit.
