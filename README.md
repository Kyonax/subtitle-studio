# subtitle-studio

Turn any local video or audio into accurate, timestamped, speaker-aware
subtitles, styled from one TOML file, translated offline into 400+ languages,
and optionally burned back into the video. Everything runs on your own machine,
nothing is uploaded and nothing needs a subscription.

## The documentation map

| File | Audience | Carries |
|---|---|---|
| `README.md` | you, first read | setup, every command, the TUI, styles.toml |
| `STUDIO.doc.org` | you, reference | what the tool is, architecture, pipeline model |
| `STUDIO.ai.org` | agents | exact recipes, model sources, pitfalls, rulings |
| `CHANGELOG.org` | both | dated feature history |

One fact lives in one file. This README shows how to use the tool, the doc file
says what it is, the ai file holds the exact values an agent needs.

## Setup

1. Install [uv](https://docs.astral.sh/uv/) and sync the project. The venv pins
   Python 3.12 automatically, the system Python is not used.

   ```bash
   cd "/run/media/kyonax/Da_ Disk/dev/github-kyonax/subtitle-studio"
   uv sync --all-extras
   ```

2. Download the models once, about 8 GB total:

   ```bash
   uv run subtitle-studio models all
   ```

3. Only for speaker identification, one-time and free: create a HuggingFace
   account, accept the terms on `pyannote/speaker-diarization-3.1` **and**
   `pyannote/segmentation-3.0`, then `export HF_TOKEN=hf_...`. Skip this if
   your videos have a single speaker, everything else works without it.

## Quick start

```bash
uv run subtitle-studio run video.mp4 --no-diarize --burn        # subtitles as spoken, burned in
uv run subtitle-studio run video.mp4 --to en --burn             # everything in English
uv run subtitle-studio run video.mp4 --swap --burn              # bilingual video, languages crossed
uv run subtitle-studio ui video.mp4                             # the TUI
```

Artifacts land in `video.studio/` next to the input: `transcript.json` (the
timestamped transcript), `subs.<track>.ass` (styled subtitles any player reads),
`render.<track>.mp4` (the burned video), `state.json` (what is up to date).
Re-running skips every stage whose inputs did not change.

## Commands

Each stage is also its own command, useful when you want to inspect or fix
things between steps.

### Transcribe

```bash
uv run subtitle-studio transcribe video.mp4                 # language auto-detected
uv run subtitle-studio transcribe video.mp4 --language es   # or force it
```

Writes `transcript.json` with word-level timestamps and a per-segment detected
language. Check what languages the video actually contains:

```bash
uv run subtitle-studio languages video.mp4
```

### Identify and name speakers

```bash
uv run subtitle-studio diarize video.mp4 --max-speakers 3
uv run subtitle-studio speakers list video.mp4
uv run subtitle-studio speakers rename video.mp4 SPEAKER_00 "María"
```

Renames update every transcript variant at once, and the next `style` picks the
name up automatically.

### Translate

| You want | Command |
|---|---|
| everything in one language | `translate video.mp4 --to es` |
| bilingual video, cross the languages | `translate video.mp4 --swap` |
| force-retranslate native parts too | `translate video.mp4 --to es --all` |

With `--to`, parts already spoken in the target language pass through
untouched and keep their word timing. With `--swap`, a two-language video shows
each part in the other language, English speech gets Spanish subtitles and
Spanish speech gets English ones, written as the `swap` track. Translation is
local (MADLAD-400), free, and covers 400+ languages: `--to pt`, `--to fr`,
`--to ja`, any ISO code.

### Style and render

```bash
uv run subtitle-studio style video.mp4 --preset neon --position top-center
uv run subtitle-studio render video.mp4                     # burn the current track
uv run subtitle-studio style video.mp4 --lang swap          # style a translated track
uv run subtitle-studio render video.mp4 --lang swap
```

`--position` takes one of the nine anchors (`bottom-center`, `bottom-left`,
`center`, `top-right`, ...) or exact coordinates as `'x,y'`. Position is chosen
here or in the TUI, it is never part of the styles file.

### Full pipeline

```bash
uv run subtitle-studio run video.mp4 --to en --preset shorts --position "1280,1000" --burn
uv run subtitle-studio run video.mp4 --force diarize        # redo from a stage onward
```

## The TUI

```bash
uv run subtitle-studio ui video.mp4
```

Three tabs in the nano-core HUD look, hairline panels on black, status badges:

| Tab | What you do there |
|---|---|
| PIPELINE | one row per stage with a plain-words explanation, a status badge and its button, plus options and RUN FULL PIPELINE |
| TRANSCRIPT | read segments, fix text with `enter`, rename a row's speaker with `r` |
| STYLE | pick preset and position, watch the live preview follow |

Each PIPELINE row tells you what the stage does: TRANSCRIBE turns the speech
into timed text, DIARIZE detects who speaks when (optional, HF token),
TRANSLATE rewrites the text in another language offline, STYLE + RENDER builds
the subtitles and burns them when Burn is ticked. Badges show `● done` /
`○ pending` / `◍ working` per stage, computed from the work directory.

The STYLE tab is selection only, the file itself is edited outside:

- the preset list and position select re-render the preview as you move
  through them (over a real video frame when a transcript exists, over a
  neutral backdrop otherwise)
- `styles.toml` is **watched**: save it in your editor and the preview
  refreshes by itself, `EDIT FILE` opens it for you
- `APPLY TO VIDEO` runs style (+ render when Burn is ticked) with the
  selected preset and position

The preview keeps the video's aspect. `z` toggles fit ↔ **full size**: the
original image, unscaled, in a scrollable pane that opens on the subtitle
anchor, `shift+arrows` or the mouse wheel move around.

Terminals without pixel graphics (Alacritty) can only draw the preview as
coarse blocks, that is a terminal limit, not a setting. The tool detects it and
**opens the watch window by itself**: the preview in an image viewer (imv),
full quality, refreshed live with every change (`w` reopens it if closed).
Terminals with pixel graphics (kitty, ghostty, wezterm, foot) render the
preview sharp inline instead. Press `?` anytime for the full key list.

Keys :: `?` help · `enter` edit row · `r` rename speaker · `e` edit styles.toml ·
`p` preview now · `z` fit/full size · `shift+arrows` move · `w` watch window ·
`o` open preview once · `F5` reload · `q` quit.

`subtitle-studio ui` with no video opens STYLE-only mode for pure look
tweaking. Stage work runs in background threads, the log streams progress.

## styles.toml

One central file holds every look: **`styles.toml` at the subtitle-studio
root**. It ships as the reference, one `[default]` style carrying every
supported key with a comment explaining each. Add your own `[style.NAME]`
presets there and reference them by name, no per-video setup needed. See what
is in effect:

```bash
uv run subtitle-studio styles                # resolved file + preset table
uv run subtitle-studio preview --open        # see the style, no video needed
```

`preview` renders one complete subtitle with sample text over a neutral
backdrop into a PNG, honoring the resolved styles, `--preset` and `--position`.
Use `--text "..."` for your own words and `--res 1080x1920` for vertical. In
the TUI the `Preview frame` button does the same, over a real frame when the
loaded video has a transcript, over the backdrop otherwise, and
`subtitle-studio ui` with no video opens straight into style tweaking.

Search order when styling: `--styles PATH`, else a `styles.toml` next to the
video (per-video override), else **the project `styles.toml`**, else
`~/.config/subtitle-studio/styles.toml`, else built-in defaults. The TUI Style
tab shows which file it is editing.

### `[meta]`

| Key | Does |
|---|---|
| `play_res` | coordinate space for every size, `"video"` = each video's real resolution, `[1920, 1080]` = one frozen space |
| `default_preset` | preset applied when no `--preset` is passed, must name a `[style.NAME]` |

### The base look

Every key `[default]` supports, the central file documents each one in place:

```toml
[default]
font = "Roboto"             # family name or file stem inside fonts/
size = 56
color = "#FFFFFF"           # #RRGGBB or #RRGGBBAA, AA 00=transparent FF=opaque
bold = false
italic = false
uppercase = false           # force ALL CAPS
letter_spacing = 0.0        # extra px between letters
scale_x = 100               # width stretch, percent
scale_y = 100
stroke = { enabled = true, color = "#000000", width = 3.0 }
glow = { enabled = false, color = "#00D5FF", radius = 6.0, size = 2.0 }
shadow = { enabled = false, color = "#000000AA", offset = 2.0 }
background = { enabled = true, color = "#000000AA", padding = { x = 16, y = 10 }, rounded = false, radius = 16.0, mode = "box" }
margin = { left = 80, right = 80, vertical = 60 }
max_line_chars = 42         # wrap limit per line
max_lines = 2               # more text splits into another subtitle
max_words = 0               # words shown at once, 0 = unlimited
```

Drop font files into `fonts/`, they are matched by real family name and also
measured so rounded boxes fit the text exactly.

### Named presets

A preset is a `[style.NAME]` table added to the central file, it only lists
what differs from `[default]` and is picked per run with `--preset NAME` or
the TUI dropdown. Four ready-to-paste examples:

```toml
[style.rounded]             # soft dark pill, keeps the text stroke
background = { enabled = true, color = "#101018CC", padding = { x = 22, y = 12 }, rounded = true, radius = 18.0 }

[style.neon]                # caps, spaced letters, cyan glow, rounded box
uppercase = true
letter_spacing = 1.5
glow = { enabled = true, color = "#00D5FF", radius = 7.0, size = 2.5 }
background = { enabled = true, color = "#0A0A14B0", padding = { x = 24, y = 12 }, rounded = true, radius = 22.0 }

[style.clean]               # no box, stroked text with a soft shadow
background = { enabled = false }
stroke = { color = "#000000", width = 3.5 }
shadow = { enabled = true, color = "#00000090", offset = 3.0 }

[style.shorts]              # big words, few at a time, for vertical clips
size = 72
bold = true
uppercase = true
max_words = 4
max_lines = 1
```

```bash
uv run subtitle-studio style video.mp4 --preset rounded
uv run subtitle-studio run video.mp4 --preset shorts --position center --burn
```

### Per-speaker colors

Speaker overrides apply on top of whichever preset is active. The key is the
stable id, or the display name once you renamed it:

```toml
[speaker.SPEAKER_01]
color = "#7FD4FF"

[speaker."María"]
color = "#FFD700"
```

### Worked example, short-form clip in Spanish

```bash
uv run subtitle-studio run clip.mp4 --no-diarize --to es --preset shorts --position "960,540" --burn
```

One command: transcribe, translate everything into Spanish, big four-word
subtitles dead center, burned into `clip.studio/render.es.mp4`.

## Requirements

| Piece | Detail |
|---|---|
| Python | 3.12 via uv, `uv sync` sets it up |
| ffmpeg | with libass and NVENC, Arch package `ffmpeg` works |
| GPU | NVIDIA ~6 GB VRAM, models load one at a time, CPU fallback exists |
| Disk | ~8 GB of model caches after `models all` |
| HF token | only for diarization, free account, see Setup step 3 |

## Notes

- Translation quality: the local model sometimes doubles short sentences, the
  tool collapses those automatically and always keeps your original text in
  `source_text`.
- Mixed-language videos transcribe both languages, word timing is tightest for
  the video's main language.
- `transcript.json` writes are atomic and keep a `.bak` of the previous
  version, hand-editing is safe.
