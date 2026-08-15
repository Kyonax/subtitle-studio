from subtitle_studio.state import (
    hash_file,
    hash_obj,
    invalidate_from,
    load_state,
    record_stage,
    stage_fresh,
)

ORDER = ["extract", "transcribe", "diarize", "translate", "style", "render"]


def test_hash_obj_is_order_insensitive():
    assert hash_obj({"a": 1, "b": 2}) == hash_obj({"b": 2, "a": 1})
    assert hash_obj({"a": 1}) != hash_obj({"a": 2})


def test_stage_freshness_tracks_input_hashes(tmp_path):
    artifact = tmp_path / "audio.wav"
    artifact.write_bytes(b"fake audio")
    inputs = {"audio": hash_file(artifact)}
    record_stage(tmp_path, "transcribe", inputs)
    assert stage_fresh(load_state(tmp_path), "transcribe", inputs)

    artifact.write_bytes(b"different audio")
    changed = {"audio": hash_file(artifact)}
    assert not stage_fresh(load_state(tmp_path), "transcribe", changed)


def test_invalidate_from_drops_stage_and_later(tmp_path):
    for stage in ORDER[:4]:
        record_stage(tmp_path, stage, {"k": "v"})
    invalidate_from(tmp_path, "diarize", ORDER)
    stages = load_state(tmp_path)["stages"]
    assert set(stages) == {"extract", "transcribe"}
