"""Stage 2: speech-to-text with word-level timestamps -> transcript.json."""

from __future__ import annotations

from pathlib import Path

from subtitle_studio import paths
from subtitle_studio.asr.engine import ProgressFn, get_engine
from subtitle_studio.config import Settings
from subtitle_studio.schema import ModelsInfo, Segment, SourceInfo, Transcript, VideoInfo, save_transcript
from subtitle_studio.stages.extract import probe_media, run_extract
from subtitle_studio.state import hash_file, hash_obj, record_stage


def interpolate_missing_word_times(segment: Segment) -> None:
    """Forced alignment leaves numerals/OOV tokens without timings (start/end == -1).

    Fill them by linear interpolation between the nearest timed neighbors, falling
    back to the segment boundaries at the edges.
    """
    words = segment.words
    for i, w in enumerate(words):
        if w.start >= 0 and w.end >= 0:
            continue
        prev_end = next((words[j].end for j in range(i - 1, -1, -1) if words[j].end >= 0), segment.start)
        nxt = next((j for j in range(i + 1, len(words)) if words[j].start >= 0), None)
        next_start = words[nxt].start if nxt is not None else segment.end
        gap_slots = (nxt - i + 1) if nxt is not None else 2
        step = max(0.0, (next_start - prev_end)) / gap_slots
        w.start = round(prev_end + step * 1, 3) if step else round(prev_end, 3)
        w.end = round(w.start + step, 3) if step else round(next_start, 3)


def split_long_segments(segments: list[Segment], max_seconds: float) -> list[Segment]:
    """Cap segment duration by splitting at word boundaries, preferring breaks
    after punctuation. Short segments keep relisten and review cheap."""
    if max_seconds <= 0:
        return segments
    out: list[Segment] = []
    for seg in segments:
        if seg.end - seg.start <= max_seconds or len(seg.words) < 4:
            out.append(seg)
            continue
        groups: list[list] = [[]]
        for w in seg.words:
            groups[-1].append(w)
            duration = groups[-1][-1].end - groups[-1][0].start
            at_pause = w.word.strip().endswith((".", ",", "!", "?", "…", ";", ":"))
            if (duration >= max_seconds and at_pause) or duration >= max_seconds * 1.5:
                groups.append([])
        if groups and not groups[-1]:
            groups.pop()
        for words in groups:
            out.append(Segment(
                id=0, start=words[0].start, end=words[-1].end,
                speaker=seg.speaker, language=seg.language,
                text=" ".join(w.word.strip() for w in words),
                words=words,
                avg_logprob=seg.avg_logprob, no_speech_prob=seg.no_speech_prob,
            ))
    for i, seg in enumerate(out):
        seg.id = i
    return out


def run_transcribe(
    input_media: Path,
    workdir: Path,
    settings: Settings,
    language: str | None = None,
    batch_size: int | None = None,
    on_progress: ProgressFn | None = None,
) -> Path:
    audio = paths.audio_path(workdir)
    if not audio.exists():
        run_extract(input_media, workdir, on_progress)

    probe = probe_media(input_media)
    engine = get_engine(settings)
    result = engine.transcribe(
        audio,
        language=language or settings.asr.language,
        batch_size=batch_size or settings.asr.batch_size,
        on_progress=on_progress,
    )
    for segment in result.segments:
        interpolate_missing_word_times(segment)
    result.segments = split_long_segments(result.segments, settings.asr.max_segment_seconds)

    if on_progress:
        on_progress("identifying per-segment languages", 0.95)

    transcript = Transcript(
        source=SourceInfo(
            media_path=str(input_media.resolve()),
            audio_path=audio.name,
            duration_s=probe["duration_s"],
            video=VideoInfo(**probe["video"]) if probe["video"] else None,
        ),
        language=result.language,
        language_probability=result.language_probability,
        models=ModelsInfo(**result.models),
        segments=result.segments,
    )
    from subtitle_studio.langid import annotate_segments

    annotate_segments(transcript)

    out = paths.transcript_path(workdir)
    save_transcript(transcript, out)
    record_stage(
        workdir,
        "transcribe",
        {"audio": hash_file(audio), "config:asr": hash_obj(settings.asr.model_dump())},
    )
    return out


def relisten_segment(
    input_media: Path,
    workdir: Path,
    settings: Settings,
    seg_id: int,
    on_progress: ProgressFn | None = None,
) -> Path:
    """Fresh listening of ONE segment: cut its audio range, run the ASR on the
    slice, replace that segment's text and word timings only."""
    import subprocess
    import tempfile

    from subtitle_studio.schema import Word, load_transcript

    audio = paths.audio_path(workdir)
    transcript_file = paths.transcript_path(workdir)
    transcript = load_transcript(transcript_file)
    seg = next((s for s in transcript.segments if s.id == seg_id), None)
    if seg is None:
        raise ValueError(f"segment {seg_id} not found")

    pad = 0.15
    start = max(0.0, seg.start - pad)
    end = seg.end + pad
    slice_path = Path(tempfile.gettempdir()) / f"subtitle-studio-relisten-{seg_id}.wav"
    if on_progress:
        on_progress(f"cutting audio {start:.2f}s to {end:.2f}s", 0.05)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
         "-i", str(audio), "-c:a", "pcm_s16le", str(slice_path)],
        check=True, capture_output=True, stdin=subprocess.DEVNULL,
    )
    try:
        engine = get_engine(settings)
        language = seg.language or transcript.language
        result = engine.transcribe(
            slice_path, language=language,
            batch_size=settings.asr.batch_size, on_progress=on_progress,
        )
    finally:
        slice_path.unlink(missing_ok=True)

    new_text = " ".join(part.text.strip() for part in result.segments).strip()
    if not new_text:
        raise ValueError("the relisten heard nothing in this range, old text kept")

    seg.text = new_text
    seg.words = [
        Word(word=w.word, start=round(w.start + start, 3), end=round(w.end + start, 3),
             score=w.score, speaker=seg.speaker)
        for part in result.segments for w in part.words
    ]
    interpolate_missing_word_times(seg)

    from subtitle_studio.langid import detect_language

    code, confidence = detect_language(new_text)
    if confidence >= 0.55 and len(new_text.split()) >= 2:
        seg.language = code

    save_transcript(transcript, transcript_file)
    if on_progress:
        on_progress(f"segment {seg_id} relistened", 1.0)
    return transcript_file
