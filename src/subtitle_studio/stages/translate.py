"""Stage 4: translate the timestamped transcript to a target language.

Timing and speakers are copied verbatim from the source; `words` is emptied (word
timings cannot cross languages) and every segment keeps its `source_text`. The
translated variant is a full transcript.<lang>.json, so style/render work on it
unchanged."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from subtitle_studio import paths
from subtitle_studio.config import Settings
from subtitle_studio.schema import Transcript, load_transcript, save_transcript
from subtitle_studio.state import hash_file, hash_obj, record_stage
from subtitle_studio.translate import get_provider

ProgressFn = Callable[[str, float], None]


SWAP_TRACK = "swap"


def run_translate(
    input_media: Path,
    workdir: Path,
    settings: Settings,
    to_lang: str | None = None,
    translate_all: bool = False,
    swap: bool = False,
    on_progress: ProgressFn | None = None,
) -> Path:
    """Produce transcript.<lang>.json — three selectable behaviors:

    - `to_lang` (invert/unify): segments already IN the target pass through
      untouched (text AND word timestamps kept), the rest are translated.
    - `to_lang` + `translate_all`: every segment translated, old behavior.
    - `swap`: video must contain exactly two languages; EVERY segment is
      translated to the *other* one (EN speech -> ES subs and ES speech -> EN
      subs in the same track, written as transcript.swap.json).
    """
    source_file = paths.transcript_path(workdir)
    source = load_transcript(source_file)

    from subtitle_studio.langid import annotate_segments

    if any(seg.language is None for seg in source.segments):  # older transcripts
        annotate_segments(source)

    if swap:
        present = sorted({seg.language or source.language or "und" for seg in source.segments})
        if len(present) != 2:
            raise ValueError(
                f"--swap needs exactly two languages in the video, found {present} — "
                "use --to LANG to unify instead"
            )
        other = {present[0]: present[1], present[1]: present[0]}
        targets = {seg.id: other[seg.language or source.language] for seg in source.segments}
        todo = list(source.segments)
        track = SWAP_TRACK
        if on_progress:
            on_progress(f"swapping {present[0]} <-> {present[1]} across {len(todo)} segments", 0.02)
    else:
        if not to_lang:
            raise ValueError("pass --to LANG (or --swap for a two-language cross)")
        targets = {seg.id: to_lang for seg in source.segments}
        todo = [
            seg for seg in source.segments
            if translate_all or (seg.language or source.language) != to_lang
        ]
        if not todo:
            raise ValueError(f"every segment is already in {to_lang!r} — nothing to translate")
        track = to_lang
        if on_progress:
            kept = len(source.segments) - len(todo)
            on_progress(
                f"{len(todo)} segment(s) to translate, {kept} already in {to_lang!r} kept as-is", 0.02
            )

    provider = get_provider(settings)
    if on_progress:
        on_progress(f"loading {provider.name} model", 0.05)

    translated_texts: dict[int, str] = {}
    batch = settings.translation.batch_size
    done = 0
    try:
        # group by target language so each provider batch has a single target
        for target in sorted({targets[seg.id] for seg in todo}):
            group = [seg for seg in todo if targets[seg.id] == target]
            for i in range(0, len(group), batch):
                chunk = group[i : i + batch]
                outputs = provider.translate_batch(
                    [seg.text for seg in chunk], source.language or "und", target
                )
                translated_texts.update({seg.id: out for seg, out in zip(chunk, outputs)})
                done += len(chunk)
                if on_progress:
                    on_progress(
                        f"translating -> {target} ({done}/{len(todo)} segments)",
                        0.1 + 0.85 * done / max(len(todo), 1),
                    )
    finally:
        unload = getattr(provider, "unload", None)
        if unload:
            unload()
        from subtitle_studio.gpu import free_cuda

        free_cuda()

    def convert(seg):
        if seg.id in translated_texts:
            return seg.model_copy(
                update={
                    "text": translated_texts[seg.id], "language": targets[seg.id],
                    "words": [], "source_text": seg.text,
                }
            )
        return seg.model_copy()  # already in the target language: keep words + text

    translated = Transcript(
        source=source.source,
        language=track,
        language_probability=None,
        translated_from=source.language,
        models=source.models.model_copy(update={"translation": f"{provider.name}:madlad400-3b-mt"}),
        speakers={k: v.model_copy() for k, v in source.speakers.items()},
        segments=[convert(seg) for seg in source.segments],
    )
    out = paths.transcript_path(workdir, track)
    save_transcript(translated, out)
    record_stage(
        workdir,
        f"translate:{track}",
        {
            "transcript": hash_file(source_file),
            "config:translation": hash_obj(settings.translation.model_dump()),
            "to": track,
            "mode": "swap" if swap else ("all" if translate_all else "invert"),
        },
    )
    if on_progress:
        on_progress("translation done", 1.0)
    return out
