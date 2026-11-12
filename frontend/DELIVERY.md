# MedTreeBench frontend redesign

Implementation follows the repository's Chinese frontend implementation guide.
Scope: frontend only; existing API contracts and forest placement algorithm stay intact.

## Validation

| Stage                         | Status      | Checks                                                                                                                                                  |
| ----------------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P0 — workspace shell          | Implemented | pnpm 10.11.0 lint: 0 warnings, 0 errors. Production build passed. Browser confirms 56px top bar and 56px rail on the existing case library.             |
| P1 — case library             | Implemented | Lint: 0 warnings/errors; production build passed. 393-case index, 14 datasets, 50-row pages; 1440×900 screenshot checked.                               |
| P2 — case details             | Implemented | Lint and production build passed. Chrome confirms 24 nodes, 23 edges, four source-matched visits; trace 300px, inspector 400px, no horizontal overflow. |
| P3 — model comparison         | Implemented | Lint and production build passed. Five existing runs (two completed); dynamically union API metric metadata, with an explicit missing-metrics state.    |
| P4 — redirects and acceptance | Verified    | All three legacy redirects retain query state. Desktop, drawer, mobile, keyboard, empty/error-state and dark-theme checks passed.                       |

## Delivered workspace

- Shared 56px top bar, 56px icon rail and 32px status bar; language switch, account menu, theme toggle and Cmd/Ctrl+K case search.
- `/cases`: 393-case inventory, 14 dataset filters, type/operation/reference filters, sorting, 50-row pagination, column chooser, JSON expansion, Cmd/Ctrl-click selection, summary export and comparison handoff.
- `/cases/[case_id]`: 300px trace tree, existing forest placement, count-weighted edges, trace/layout controls, keyboard navigation and a 400px inspector adjustable between 320 and 560px.
- `/compare`: model overview, case-level run comparison, dynamic metric metadata, HIGHER/LOWER ranking, unranked DESCRIPTIVE values and Preview/Scores/JSON inspection. Existing model execution remains in the Run models tab.
- `/arena`, `/history`, `/evidence`, `/admin` and classic forest remain available in the shared shell. `/forest`, `/research` and `/model-arena` redirect permanently (HTTP 308), preserving query parameters.

## Acceptance evidence

Chrome checks used real UI interactions against local services. Fixtures were intercepted only in an isolated browser context; they were never written to the API or application data.

- [x] 1440×900: no document overflow; top/rail/status measured 56/56/32px, trace 300px, inspector 400px.
- [x] Inspector pointer drag reached 500.5px within its 320–560px constraints. The canvas viewport updates after the splitter gesture, avoiding a ResizeObserver feedback loop.
- [x] At 1200px, the trace tree defaults closed and the inspector opens as a drawer. At 390px, the shell stays within the viewport; the graph supports pan and zoom.
- [x] Case search, dataset selection, pagination, Cmd-click multiselect, JSON keyboard expansion, export and comparison handoff.
- [x] Node and inspector tab state survive reload; trace filtering and layout selection are URL-backed.
- [x] Arrow navigation, branch expansion/collapse, Escape and Cmd+K.
- [x] 50-node fixture collapse/expand: 115ms including browser automation round trips.
- [x] Edge weights: live count 1/2 edges measured 1/1.5px; isolated count 4 fixture measured 2.5px.
- [x] All inspector tabs render without `example`; empty doctor forests link to source evidence. Inline API errors recover through Retry.
- [x] Two-run metric fixture verifies API labels, HIGHER/LOWER/DESCRIPTIVE, zero, null and maximum-normalized bars.
- [x] Dark-theme visible-text contrast samples: minimum 5.86:1 for Cases, 4.16:1 for case detail, 5.86:1 for Compare; no sampled value below 3:1.
- [x] Preserved routes return HTTP 200; legacy redirects return HTTP 308 and retain case/node/tab/trace.
- [x] Live browser acceptance: zero page errors, console errors or failed HTTP responses.

Local screenshots are deliberately ignored by Git:

| View                     | File                           |
| ------------------------ | ------------------------------ |
| Cases / shared shell     | `.delivery/p1-cases.png`       |
| Three-column case detail | `.delivery/p2-detail.png`      |
| Compare / Scores         | `.delivery/p3-compare.png`     |
| 1200px inspector drawer  | `.delivery/p4-1200-drawer.png` |
| 390px viewport           | `.delivery/p4-mobile.png`      |
| Dark theme               | `.delivery/p4-dark.png`        |

Machine-readable local checks: `.delivery/acceptance.json`, `.delivery/fixtures.json`, `.delivery/contrast.json`, `.delivery/performance.json`.

## Reproducible commands

Use the repository's Node runtime (`.tools/node/bin`) on PATH.
Install the existing locked dependencies with `npm ci` in `frontend/`.
Run checks with `corepack pnpm@10.11.0 run lint` and `corepack pnpm@10.11.0 run build`.
This explicit pnpm version avoids pnpm 12's automatic dependency installation before scripts.

The existing deployment entry point is `./deploy.command start --no-install`.
It starts project-local API and web services, bound to the loopback interface.
Check deployment with `./deploy.command status`; stop it with `./deploy.command stop`.
The primary entry is `http://127.0.0.1:3000/cases`.
This is a persistent local deployment, not a public hosted environment.

## Performance interpretation

Measurements use Chrome's navigation clock and DOM insertion of the table shell, first real case row and first canvas node, with the existing Vinext development server.
The first measurement pass recorded a 58–68ms table shell, 167–197ms warm case rows and 120–169ms canvas nodes.
After formatting invalidated development modules, another pass measured 643ms for cold case rows, 168–218ms warm rows and 131–404ms canvas nodes.
The guide's 300ms table target is met for warmed local navigation but is not guaranteed for development-server cold compilation.
These are local acceptance measurements, not production performance guarantees.

## API compatibility

- The list API returns case summaries. Initial presentation and oracle fields are available from the per-case detail API.
- Forest filtering uses `case_id`, although the frontend URL uses `case`.
- The sample simulation currently contains 24 nodes, 23 edges and four visits.
- Individual visit events require authentication. Aggregate forest responses do not contain event timestamps.
- The DDX source projection and encounter forest traverse the same saved encounters in source order. Visit IDs are mapped only after matching the complete evidence sequence and diagnosis to exactly one forest path; otherwise the tree explicitly shows aggregate paths.
- No timestamps, durations, evidence results, or evaluation scores are fabricated. The live sample has four distinct leaf nodes, rather than the guide's illustrative three.
- Existing model run responses provide `review`; top-level `evaluation.metrics` is not currently present.
- Case table exports are explicitly scoped as case-library summaries; original case evidence remains available in the detail inspector.
- Patient-level screenshots and exports stay local and are excluded from Git.
