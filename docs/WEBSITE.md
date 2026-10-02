# Website

The landing page lives in `site/`. It is static HTML, CSS, and JavaScript.
There is no build step or browser framework. Fonts are self-hosted with their
SIL Open Font License files in `site/assets/`. The site adds no analytics.
GitHub's hosting privacy policy still applies.

## Purpose and design

The page helps developers see why separate port ownership matters, then install
and configure the CLI. A clearly labeled interactive example switches between
three colliding port requests and three separate assignments. It runs entirely
in the browser and does not claim ports on the visitor's machine.

A docs-first page, a terminal walkthrough, and an interactive example were
considered. The example makes the benefit visible before installation. The
visual direction uses a dark steel-blue workbench, copper and pale blue
connections, Barlow Condensed headings, Barlow body text, and native monospace
code. A built-in imagegen concept informs the composition; its fictional install
URL and absolute no-conflict claims are excluded from the implementation.

## Preview

Claim the preview service before starting a server:

```bash
portmanager claim . site --kind web
portmanager sync .
portmanager run . -- python3 scripts/preview-site.py
```

The preview reads `PM_HOST`, `PM_PORT_SITE`, and `PM_URL_SITE` from Portmanager.
It binds only to loopback and serves only `site/`, never the repository root.
Use the existing service if already claimed. Run `portmanager doctor .` before
finishing a port-related change.

## Publication

The `Website` GitHub Actions workflow deploys only `site/` to GitHub Pages.
Enable Pages with GitHub Actions as its publishing source before the first run.
The default project URL is `https://initiator1.github.io/portmanager/`.
Relative asset URLs support this project path and a future custom domain.

The displayed install command pins the tested launcher repair commit
`d099075663037d363ef3541f25c4d079193bad99`. Push that commit and verify the
remote installation before publishing the page. Switch to a verified release
tag after publication. Never point visitors at the older release with the broken
launcher. Confirm the final name before publishing the page. Domain registration needs BOSS's chosen name and
approval of the actual registrar quote. Do not add a `CNAME` until the domain is
owned and its DNS records are ready.

For a custom domain, configure Pages and the registrar using GitHub's current
custom-domain instructions. Verify DNS, HTTPS, redirects, assets, and the
install command after deployment. Keep existing unrelated domain and mail
records intact.

## Checks

Run `node --check site/app.js`. Render the page at desktop and narrow phone
widths. Check overflow, keyboard focus, example switching, copy behavior,
expandable setup and FAQs, and external links. Record measured CSS viewport
sizes; browser zoom can differ from requested physical sizes. The generated
screenshots under `output/` are ignored by Git.

The launcher regression suite and fresh wheel installation are documented in
`RELEASE.md`. Site checks do not replace release CI.

Local review on 2026-10-02: measured CSS widths 1920, 1440, 391, and 320 pixels have
no horizontal overflow. The example assigns distinct ports and returns to the
collision state. Setup and FAQ disclosures expand. Copy handlers report success,
but Browser Use's virtual clipboard does not receive native browser clipboard
writes, so independent clipboard readback is not verified. HTML asset paths,
anchors, unique IDs, ARIA references, and JavaScript syntax pass. Screenshots
under `output/site-review/` preserve the rendered review.
