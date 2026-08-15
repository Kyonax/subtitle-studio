from subtitle_studio.translate.madlad import collapse_repetition


def test_exact_doubled_sentence_collapses():
    assert collapse_repetition("Exactly. Exactly.") == "Exactly."


def test_near_duplicate_halves_collapse():
    doubled = "Thanks for the introduction. Thank you for the introduction."
    assert collapse_repetition(doubled) == "Thanks for the introduction."


def test_comma_joined_repeat_collapses():
    doubled = (
        "Today we are going to try the transcription with time stamps, "
        "we are going to try the transcription with time stamps."
    )
    assert collapse_repetition(doubled) == "Today we are going to try the transcription with time stamps."


def test_legit_text_untouched():
    text = "In the end we exported a file with each word, its start time and its speaker."
    assert collapse_repetition(text) == text


def test_different_sentences_survive():
    text = "Hello everyone. Welcome to the show."
    assert collapse_repetition(text) == text
