"""Speech-to-text for a clip, using faster-whisper (runs locally)."""
from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger("clipper.transcribe")

_models: dict[tuple[str, str], object] = {}
_cuda_ok = True  # set to False after the first GPU failure


_dll_dirs_added = False


def _add_cuda_dlls() -> None:
    """Make the CUDA libraries from the nvidia-cublas-cu12 / nvidia-cudnn-cu12 pip packages findable.

    On Windows they live in site-packages/nvidia/<lib>/bin, which is not on the DLL search path.
    """
    global _dll_dirs_added
    if _dll_dirs_added or os.name != "nt":
        return
    _dll_dirs_added = True
    try:
        import nvidia
    except ImportError:
        return
    for root in nvidia.__path__:
        for bin_dir in Path(root).glob("*/bin"):
            os.add_dll_directory(str(bin_dir))
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")


def _load(name: str, device: str):
    if device == "cuda":
        _add_cuda_dlls()
    from faster_whisper import WhisperModel

    key = (name, device)
    if key not in _models:
        compute = "int8_float32" if device == "cuda" else "int8"
        log.info("loading speech model %s on %s (first run downloads it)", name, device)
        _models[key] = WhisperModel(name, device=device, compute_type=compute)
    return _models[key]


def _run(path: Path, name: str, device: str, language: str | None, words: bool) -> dict:
    model = _load(name, device)
    segments, info = model.transcribe(str(path), language=language, vad_filter=True, beam_size=5,
                                      word_timestamps=words)
    segs = []
    for s in segments:
        seg = {"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()}
        if words:
            seg["words"] = [{"start": round(w.start, 2), "end": round(w.end, 2), "word": w.word.strip()}
                            for w in (s.words or []) if w.word.strip()]
        segs.append(seg)
    return {
        "language": info.language,
        "model": f"{name} ({device})",
        "text": " ".join(s["text"] for s in segs),
        "segments": segs,
    }


def transcribe(path: Path, model: str = "auto", language: str | None = None, words: bool = False) -> dict:
    """Return {"language", "model", "text", "segments": [{start, end, text}]}.

    words=True adds "words": [{start, end, word}] to each segment (for subtitles).

    model="auto" picks "medium" on an NVIDIA GPU and "small" on CPU.
    """
    global _cuda_ok
    import ctranslate2

    if _cuda_ok and ctranslate2.get_cuda_device_count() > 0:
        try:
            return _run(path, "medium" if model == "auto" else model, "cuda", language, words)
        except Exception as e:  # usually missing CUDA/cuDNN libraries
            _cuda_ok = False
            log.warning("GPU transcription failed (%s); using CPU from now on", str(e).splitlines()[0][:150])
    return _run(path, "small" if model == "auto" else model, "cpu", language, words)
