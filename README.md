# space-life-news

A live wire for the search for life beyond Earth, and the interactive that reads it.

The space front and the environment have their own repositories: `space-feed` and
`environment-feed`.

`harvest.py` runs every two hours in GitHub Actions, reads 51 feeds in 25 languages, keeps
what is about biosignatures and habitability, tags each story by subject, and writes
`wire.json`. `index.html` — the Biosignature Evidence Assessment interactive — loads that
file and renders it.

Nothing here rewrites a headline. Titles and snippets are the publishers' own, truncated
but never reworded, and every row keeps its original link. There is no model in the
pipeline, no API key, and no paid service.

## Files

| File | What it does |
|---|---|
| `harvest.py` | Reads every wire, filters, tags, deduplicates, writes `wire.json`. Standard library only. |
| `sources.json` | The wire list. Edit to add, drop or retune a feed. |
| `wire.json` | The output the page reads. Rewritten by the Action; do not hand-edit. |
| `index.html` | The interactive. Self-contained, embeddable, reads `wire.json` over HTTPS. |
| `weebly-embed.html` | The same interactive wrapped for a Weebly Embed Code element — paste-only, nothing hosted. Regenerate it whenever `index.html` changes. |
| `.github/workflows/harvest.yml` | The schedule (every two hours), plus a manual run button in the Actions tab. |

## Setup

1. Push these files to the repository root.
2. Settings → Actions → General → Workflow permissions → **Read and write permissions**, save.
   Without this the Action cannot commit `wire.json`.
3. Actions tab → **Harvest wires** → *Run workflow*. The first run takes about two minutes.
4. Confirm `wire.json` appears in the repo and that
   `https://raw.githubusercontent.com/WelcomeToYourGalaxy/space-life-news/main/wire.json`
   loads in a browser.

## Embedding the interactive

Two ways, neither needing a host for the page itself.

**Weebly, paste-only.** Open `weebly-embed.html`, copy all of it, and paste it into a Weebly
*Embed Code* element. It carries the whole interactive inside a frame it builds itself, so
Weebly's theme CSS cannot reach in and the interactive's styles cannot leak out. Nothing is
uploaded. The only runtime fetch is `wire.json`. Regenerate this file after any change to
`index.html`.

**Anywhere else.** `index.html` is one file with no dependencies beyond the Inter and
Instrument Serif webfonts. Host it and iframe it, or paste its `<style>`, markup and
`<script>` straight into a page. It reads `wire.json` from
`raw.githubusercontent.com`, falling back to `cdn.jsdelivr.net` if raw is blocked or rate
limited, and re-reads every 15 minutes while the tab is open.

If you fork or rename the repo, change `REPO` and `BRANCH` at the top of the feed script
in `index.html`.

## Sources

**Institutional** — NASA, NASA JPL, ESA Space Science, CNES, DLR, JAXA, SETI Institute,
Planetary Society.

**Science desks** — Phys.org (astrobiology, planetary science), ScienceDaily, EurekAlert,
Universe Today, Space.com, Astrobiology.com, Sky & Telescope.

**Preprints** — two arXiv queries: biosignatures/astrobiology/Enceladus/K2-18b, and
habitability/ocean worlds/technosignatures/prebiotic chemistry. Tagged `preprint` so
unreviewed work is never mistaken for a published result.

**Regional press** — Google News editions in English (US, UK, India, Australia, South
Africa, Nigeria), Spanish (Spain, Mexico), Portuguese, French, German, Italian, Dutch,
Swedish, Greek, Polish, Russian, Ukrainian, Turkish, Arabic, Hebrew, Persian, Hindi,
Bengali, Indonesian, Vietnamese, Thai, Japanese, Chinese (simplified and traditional),
Korean, Swahili. Each query is written in that language, not translated at read time.

## What gets kept

The feed is about the search for life, not about space. A story gets in one of
three ways:

- **CORE** — it says so outright: astrobiology, biosignature, extraterrestrial
  life, technosignature, panspermia, habitability, prebiotic chemistry, the
  named missions, dimethyl sulfide, hycean, K2-18 b.
- **A guarded target** — Enceladus, Europa, Titan or the tiger stripes named
  alongside an astronomical word (Saturn, moon, ocean, ice, plume, a mission,
  an agency). These bodies are only in the news because of the life question.
- **Anything weaker** — Mars, Venus, exoplanets, organics, methane, comets —
  only alongside a word for life, biology or habitability in any of the 25
  languages.

Wires marked `"strict": true` in `sources.json` are general space desks. Naming
a body is not enough from them: a life word must be present either way. That is
what keeps GPS-free orbit navigation "near the Moon and Mars" out of an
astrobiology feed.

Matching respects word edges in Latin script, so "view" no longer satisfies the
French word for life and "titanium" no longer satisfies Titan. A trailing `*`
matches a word family — `astrobiolog*` covers astrobiology, astrobiologist and
astrobiological. Terms in scripts without word breaks, like Chinese and Thai,
stay substring matches.

Guards also separate a moon from its namesakes: Enceladus is a racehorse and a
Chinese television serial, Europa is a continent and a football tournament, and
*mars* is the month of March in French.

Deduplication runs on a nine-word title fingerprint and on the URL with tracking
parameters stripped, so the same wire story arriving through six outlets appears
once. Stories carry forward between runs — the feed keeps 45 days and up to 900
rows, rather than showing only what happens to sit in an RSS window today.

## Coverage is uneven, and the file says so

`wire.json` carries a per-wire record: what each feed returned, or that it could not be
reached. The interactive prints all of it under *Sources and coverage*, zeros included.

Expect Swahili, Bengali, Persian and Thai to read zero most days. That is a real finding
about where this science gets covered, not a bug to paper over. The counts belong on the
page.

Two known limits: Google News caps a query at roughly 100 results and about 30 days, so a
very active month in one language can be truncated; and a regional edition can carry a
syndicated wire story rather than local reporting, which inflates a language count without
adding a local perspective.

## Running it locally

```bash
python3 harvest.py              # full run, writes wire.json
python3 harvest.py --dry-run    # harvest and report, write nothing
python3 harvest.py --fixtures tests/  # read *.xml from a directory instead of the network
```

Python 3.9 or later. No dependencies.

