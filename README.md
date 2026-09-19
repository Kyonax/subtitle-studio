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
uv run subtitle-studio web video.mp4                            # the browser studio
uv run subtitle-studio mux video.mp4                            # every built subtitle into one video
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
`center`, `top-right`, ...) or exact coordinates as `'x,y'`, measured from the
centre of the frame: `0,0` is the middle, +x runs right and +y runs down, so
the same pair lands in the same relative spot at any resolution. Position is
chosen here or in the TUI; the styles file only pins one per track
(`[track.es.position]`) or per speaker.

### Full pipeline

```bash
uv run subtitle-studio run video.mp4 --to en --preset shorts --position "320,460" --burn
uv run subtitle-studio run video.mp4 --force diarize        # redo from a stage onward
```

## The web studio

The same pipeline on one page, for when there is more to manage than a terminal
window holds comfortably. Vue 3 + Vite on the front, a small local HTTP server
in the tool itself, no dependency added to the Python side and nothing leaving
your machine — the server binds to localhost and refuses anything else.

Build the page once (Node 20+):

```bash
cd web
npm install
npm run build
```

Then run it from anywhere in the project:

```bash
uv run subtitle-studio web video.mp4      # opens http://127.0.0.1:8765
uv run subtitle-studio web                # no video yet, pick one in the page
uv run subtitle-studio web --port 9000 --no-open
```

The page is a guided flow. A spine across the top states the whole job in
three sentences — each step carries its state in one word, its situation in one
sentence, and the single action that moves it forward:

| Step | What it is | What it holds |
|---|---|---|
| 1 SOURCE | happens once per video | prepare audio, transcribe, identify speakers, name the voices |
| 2 SUBTITLES | happens once per language | the track rail (source · english · french · + add), the selected track's state and actions, its text and its style |
| 3 DELIVER | happens last | one video with every language embedded, or one language burned into the picture |

Click a step to work on it; the workspace shows that step and nothing else,
beside a preview that never moves because every step changes what it shows.
A status bar along the bottom carries what is running, its progress, and the
files produced — the log opens from there when you want it.

### One video, many languages

The rail across the top of the SUBTITLES column is every subtitle this video
carries. Click one and the rest of the page follows it: its text, its look, its
preview frame. `+ add` takes a language code, translates the transcript offline
and builds that subtitle — repeat it for as many languages as you want. Each
track carries its own three states (text, subtitles, video) and its own
buttons: build, burn, download the `.ass`, remove.

DELIVER, in the footer, is where subtitles become a video, and there are two
honest ways to do that:

- **generate video with all subtitles** — every ticked track is written INTO one
  Matroska file as a switchable stream. The player picks the language, the ASS
  styling survives intact, and nothing is re-encoded, so a 100 MB video is done
  in seconds. This is the answer to "one video, five languages".
- **burn `<language>` into the picture** — one language painted into the frames
  with NVENC, the version for platforms that ignore subtitle streams.

The same thing from the command line:

```bash
uv run subtitle-studio translate video.mp4 --to en    # add a language
uv run subtitle-studio translate video.mp4 --to fr    # and another
uv run subtitle-studio style video.mp4 --lang fr      # build its subtitle file
uv run subtitle-studio mux video.mp4                  # all of them into one video
uv run subtitle-studio mux video.mp4 --tracks es,en   # or just these, in this order
```

### The controls

Every control on the page is the same widget — a label, a `?` mark, the control
— grouped into titled bands, the way the nano-core dashboard organises its
settings. Explanations live in the `?` tooltips instead of under every field,
which is what keeps thirty settings readable as five decisions.

One vocabulary says where anything stands, everywhere on the page:

| Word | Means |
|---|---|
| ready | nothing to do |
| out of date | something changed after this was made |
| not made yet | never built |
| working | running right now |

The preview is the honest one: with a transcript it is a real frame of your
video, taken at the midpoint of the selected row's first on-screen chunk and
rendered through the same layout engine that writes the burned subtitles — what
you see is what burns. Without a transcript it falls back to the sample-text
card, so a look can be judged before anything is transcribed. Selecting a row
moves the frame, changing a style value re-renders it.

Editing works the same way it does in the TUI, with the same guarantee: a text
edit retimes that segment's words, so what you typed always reaches the screen
and every artifact built from it. The style form writes single keys through
tomlkit, so `styles.toml` keeps its comments and stays the reference it was
written to be; the `file` tab edits the whole file when that is faster.

Stages run one at a time, because the models load onto the card one at a time.
A second request while something is working is refused with a plain message
instead of queueing two model loads.

Working on the page itself:

```bash
cd web && npm run dev        # Vite on :5173, /api proxied to the Python server
uv run subtitle-studio web --no-open   # in another terminal
```

Keys in the transcript list: `j`/`k` or the arrows walk the rows, `enter` edits
the selected one, `t` relistens it.

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

**How much text one subtitle holds.** Two caps decide it and the smaller one
wins: characters (`max_line_chars` × `max_lines`) and words (`max_words`).
`max_words` is a ceiling, not a target — with `max_line_chars = 7` and
`max_lines = 2` every subtitle stops at 14 characters, so `max_words = 46`
never applies and nothing appears to change. Fitting W words needs at least
2W-1 characters, so raise the line length or the line count first. The web
studio prints which cap is active under the wrapping fields and warns when the
word cap can never be reached.

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
uv run subtitle-studio run clip.mp4 --no-diarize --to es --preset shorts --position "0,0" --burn
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
| Node | 20+, only to build the web studio page, the CLI and TUI need nothing |

## Notes

- Translation quality: the local model sometimes doubles short sentences, the
  tool collapses those automatically and always keeps your original text in
  `source_text`.
- Mixed-language videos transcribe both languages, word timing is tightest for
  the video's main language.
- `transcript.json` writes are atomic and keep a `.bak` of the previous
  version, hand-editing is safe.
