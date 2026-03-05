"""
Audio/video transcription via OpenAI Whisper API (whisper-1).

Handles two complications automatically:

1. Video files (.mp4, .mov, .mpeg, .webm)
   ffmpeg extracts the audio track at a low bitrate before sending to Whisper.
   This typically shrinks a 500 MB MP4 to < 15 MB of audio.

2. Large audio files (> 24 MB after extraction)
   ffmpeg splits the audio into 10-minute chunks.  Each chunk is transcribed
   separately and the results are concatenated.

Requirements:
  - openai Python package  (already in requirements.txt)
  - ffmpeg on the system PATH for video files or large audio:
      macOS:  brew install ffmpeg
      Ubuntu: apt-get install ffmpeg

Cost reference: ~$0.006 / minute of audio (Whisper pricing as of 2025).
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

from openai import OpenAI

from app.core.config import get_settings

logger = logging.getLogger(__name__)

WHISPER_MODEL = "whisper-1"
WHISPER_MAX_BYTES = 24 * 1024 * 1024  # 24 MB  (Whisper hard limit is 25 MB)
CHUNK_DURATION_SECS = 600             # 10-minute segments for large files

# Extensions that carry a video track — audio must be extracted first.
_VIDEO_TYPES = frozenset({"mp4", "mov", "mpeg", "webm"})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def transcribe_audio(file_path: str, file_type: str) -> str:
    """
    Transcribe an audio or video file using OpenAI Whisper.

    Returns a formatted transcript string ready for RAG chunking/indexing.

    Raises:
        RuntimeError  – ffmpeg not found or subprocess failed
        ValueError    – Whisper returned an empty transcript
        openai.APIError – Whisper API error
    """
    path = Path(file_path)
    client = OpenAI(api_key=get_settings().openai_api_key)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Step 1: extract audio from video to shrink the file
        if file_type in _VIDEO_TYPES:
            logger.info("Extracting audio from video: %s", path.name)
            work_path = _extract_audio(path, tmp_path)
        else:
            work_path = path

        size_mb = work_path.stat().st_size / (1024 * 1024)
        logger.info(
            "Audio ready for Whisper: %s (%.1f MB)", work_path.name, size_mb
        )

        # Step 2: transcribe — chunking if the audio exceeds the API limit
        if work_path.stat().st_size <= WHISPER_MAX_BYTES:
            raw_text = _transcribe_file(client, work_path)
        else:
            raw_text = _transcribe_chunked(client, work_path, tmp_path)

    if not raw_text.strip():
        raise ValueError("Whisper returned an empty transcript for this file.")

    return _format_transcript(raw_text.strip(), path.name)


# ---------------------------------------------------------------------------
# ffmpeg helpers
# ---------------------------------------------------------------------------


def _ffmpeg(*args: str) -> None:
    """Run ffmpeg with the given positional args. Raises RuntimeError on failure."""
    try:
        subprocess.run(
            ["ffmpeg", *args],
            check=True,
            capture_output=True,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "ffmpeg is required for video/large-audio transcription but was not found. "
            "Install it with:  brew install ffmpeg  (macOS)  or  "
            "apt-get install ffmpeg  (Linux/Ubuntu)"
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"ffmpeg failed: {exc.stderr.decode(errors='replace')}"
        ) from exc


def _extract_audio(video_path: Path, tmp_dir: Path) -> Path:
    """
    Extract the audio track from a video file as a compressed M4A.

    Uses 64 kbps / 16 kHz which is well above the quality floor for speech
    recognition and keeps file sizes small.
    """
    out = tmp_dir / "audio.m4a"
    _ffmpeg(
        "-i", str(video_path),
        "-vn",              # drop video stream
        "-acodec", "aac",
        "-ab", "64k",       # 64 kbps bitrate (speech quality)
        "-ar", "16000",     # 16 kHz sample rate (Whisper's native rate)
        "-y",               # overwrite if exists
        str(out),
    )
    return out


def _split_audio(audio_path: Path, tmp_dir: Path) -> list[Path]:
    """
    Split an audio file into CHUNK_DURATION_SECS-long segments using ffmpeg.

    Returns the chunk paths sorted in order.
    """
    pattern = str(tmp_dir / "chunk_%03d.m4a")
    _ffmpeg(
        "-i", str(audio_path),
        "-f", "segment",
        "-segment_time", str(CHUNK_DURATION_SECS),
        "-acodec", "copy",  # no re-encode; just split at the byte level
        "-y",
        pattern,
    )
    chunks = sorted(tmp_dir.glob("chunk_*.m4a"))
    if not chunks:
        raise RuntimeError("ffmpeg audio splitting produced no output chunks")
    return chunks


# ---------------------------------------------------------------------------
# Whisper helpers
# ---------------------------------------------------------------------------


def _transcribe_file(client: OpenAI, audio_path: Path) -> str:
    """Send a single audio file to Whisper and return plain text."""
    with open(audio_path, "rb") as fh:
        response = client.audio.transcriptions.create(
            model=WHISPER_MODEL,
            file=fh,
            response_format="text",
        )
    # openai >= 1.0: response_format="text" returns a str directly
    return response if isinstance(response, str) else str(response)


def _transcribe_chunked(
    client: OpenAI, audio_path: Path, tmp_dir: Path
) -> str:
    """Split audio into chunks, transcribe each, and join the results."""
    size_mb = audio_path.stat().st_size / (1024 * 1024)
    logger.info(
        "Audio (%.1f MB) exceeds Whisper limit — splitting into %d-second chunks",
        size_mb,
        CHUNK_DURATION_SECS,
    )
    chunks = _split_audio(audio_path, tmp_dir)
    parts: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        logger.info("Transcribing chunk %d / %d", i, len(chunks))
        part = _transcribe_file(client, chunk)
        if part.strip():
            parts.append(part.strip())
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def _format_transcript(text: str, filename: str) -> str:
    """Wrap the Whisper output with a light header for RAG context."""
    return f"Audio Transcript: {filename}\n\n{text}"
