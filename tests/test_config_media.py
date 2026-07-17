from src.config.media import SUPPORTED_AUDIO_EXTENSIONS, is_supported_audio_extension


def test_supported_audio_extensions_are_canonical() -> None:
    assert SUPPORTED_AUDIO_EXTENSIONS == frozenset({".mp3", ".wav", ".m4a", ".webm"})


def test_is_supported_audio_extension_is_case_insensitive() -> None:
    assert is_supported_audio_extension(".MP3")
    assert is_supported_audio_extension(".webm")
    assert not is_supported_audio_extension(".aac")
