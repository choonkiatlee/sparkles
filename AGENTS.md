# Maintaining Sparkles

This repository is the dedicated diamond research and evaluation archive. Read `CONVENTIONS.md` and `Sparkles home.md` before editing.

Use `research-igi-diamond` for research and `evaluate-asscher` for optical assessment. Their archive contract routes to this repository, not Knowledge.

Preserve certificate identity, original evidence bytes and dated report history. Keep links within this repository. Use focused branches and pull requests; do not merge without an explicit request. Verify YAML, local links, artifact manifests and uploaded bytes before reporting success.

## Working incrementally

Work incrementally. Break larger requests into discrete, task-sized pieces. As soon as each piece is complete and verified, commit it and push it to the working branch before moving on to the next piece. Do not accumulate multiple completed pieces locally and wait until the end to commit or push them. Keep each commit focused and independently understandable.

## Website navigation

`index.html` is the GitHub Pages entry point and lists both research-only and evaluated diamonds. Keep research-only cards clearly labelled by assessment status. For evaluated diamonds, link the latest report and preserve assessment history. Show a saved price only as the original amount/currency, optionally linked to its listing; omit the line when no price is saved. Link visual reports and evidence downloads with relative paths that work under `/sparkles/`. Update counts and search metadata. Verify every target exists; keep cards usable without JavaScript.
