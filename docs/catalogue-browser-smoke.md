# C3 real-browser acceptance smoke

Run the GitHub Actions **catalogue-browser-smoke** workflow, or (with Chromium
and Playwright installed) serve the repo root via \`python -m http.server 8765\`
and run \`node tests/catalogue-browser-smoke.mjs\`.

This is *not* a mocked image test. The UI, index and both per-diamond manifests
are served locally, while Chromium fetches the **real original published 256
JPEG frame sequences** directly from their GitHub Release asset URLs.

The browser smoke opens the full comparison on desktop Chromium and Pixel 7
mobile emulation, checks that both rotation images have decoded, waits for
complete 512-frame full prefetch, plays the synchronized motion for ~4.5 seconds,
samples every browser paint for blank/mismatched frames, verifies multiple
distinct ordinal advances, tests an explicit 50% scrub and keyboard/touch
slider input. Screenshots and \`results.json\` are uploaded even on failure.
Output includes time to first images, time to full prefetch and progress text.

Limits:
- Chromium mobile emulation is not a physical Android/iPhone or Safari test.
- A blank-paint regression check is not a human judgment of perceptual fluidity.
- External GitHub Releases availability/rate limits may cause a failure.
- 2 x 256 original JPEGs total ~16.9 MiB per uncached browser profile;
  run this expensive live-media workflow intentionally, not on every code push.

A full human acceptance pass on a real mobile device is still worth doing.
If this test fails, keep #153/#138 open and address concrete failures before
closing the programme. This test must never silently skip missing assets or
claim that a timed-out warmup is a success.
