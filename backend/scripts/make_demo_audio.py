"""Make the demo's synthetic meeting recording and transcribe it offline with faster-whisper.

Usage, on Windows from backend/ with faster-whisper==1.2.1 and av==18.1.0 installed:
    python -m scripts.make_demo_audio [--model large-v3] [--compute int8]

Each "Speaker: text" line of evals/audio/standup.txt is spoken by an offline Windows voice
(System.Speech), the clips are joined into one AAC recording for the demo page, and each
clip is transcribed separately. Whisper does not identify speakers, so names come from the
script; the words are Whisper's, unedited. The demo fixture is updated by hand from the
JSON this writes, after reviewing it. The first run also downloads the model.
"""

import argparse
import io
import json
import platform
import subprocess
import tempfile
import time
import wave
from datetime import date
from pathlib import Path

from app import transcription as speech
from scripts.evaluate_transcription import word_error_rate, words

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / "evals" / "audio" / "standup.txt"
RESULT = BACKEND / "evals" / "audio" / "standup.whisper.json"
AUDIO = BACKEND.parent / "frontend" / "public" / "demo" / "standup.m4a"
VOICES = {"Morgan": "Microsoft Zira Desktop", "Alex": "Microsoft David Desktop"}
RATE, GAP_SECONDS = 16000, 0.35


def speak(lines: list[tuple[str, str]], folder: Path) -> list[Path]:
    """Synthesize every line to 16 kHz mono WAV with System.Speech, in one PowerShell call."""
    clips = [folder / f"line-{index:02d}.wav" for index in range(len(lines))]
    jobs = [
        {"voice": VOICES[speaker], "text": text, "path": str(path)}
        for (speaker, text), path in zip(lines, clips, strict=True)
    ]
    spec = folder / "lines.json"
    spec.write_text(json.dumps(jobs), encoding="utf-8")
    command = (
        "Add-Type -AssemblyName System.Speech; "
        f"$jobs = Get-Content -Raw -Encoding UTF8 '{spec}' | ConvertFrom-Json; "
        "$format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo("
        f"{RATE}, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, "
        "[System.Speech.AudioFormat.AudioChannel]::Mono); "
        "foreach ($job in $jobs) { $voice = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$voice.SelectVoice($job.voice); $voice.SetOutputToWaveFile($job.path, $format); "
        "$voice.Speak($job.text); $voice.Dispose() }"
    )
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command], check=True)
    return clips


def pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as clip:
        assert (clip.getframerate(), clip.getnchannels(), clip.getsampwidth()) == (RATE, 1, 2)
        return clip.readframes(clip.getnframes())


def encode_aac(samples: bytes, target: Path) -> None:
    import av  # pyright: ignore[reportMissingImports]
    import numpy  # pyright: ignore[reportMissingImports]

    target.parent.mkdir(parents=True, exist_ok=True)
    with av.open(str(target), "w", format="mp4") as container:
        stream = container.add_stream("aac", rate=RATE, layout="mono")
        stream.bit_rate = 48000
        frame = av.AudioFrame.from_ndarray(
            numpy.frombuffer(samples, dtype=numpy.int16).reshape(1, -1), format="s16", layout="mono"
        )
        frame.sample_rate = RATE
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)


def wav_bytes(samples: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as clip:
        clip.setnchannels(1)
        clip.setsampwidth(2)
        clip.setframerate(RATE)
        clip.writeframes(samples)
    return buffer.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--model", default="large-v3")
    parser.add_argument("--compute", default="int8")
    args = parser.parse_args()
    lines = [
        (speaker.strip(), text.strip())
        for speaker, text in (
            line.split(":", 1) for line in SCRIPT.read_text(encoding="utf-8").splitlines() if line
        )
    ]
    with tempfile.TemporaryDirectory(prefix="m2o-demo-audio-") as folder:
        clips = [pcm(path) for path in speak(lines, Path(folder))]
    gap = bytes(int(RATE * GAP_SECONDS) * 2)
    encode_aac(gap.join(clips), AUDIO)
    speech.load_model(args.model, args.compute)
    started = time.perf_counter()
    heard = [
        speech.transcribe(wav_bytes(clip), model_name=args.model, compute_type=args.compute, max_seconds=600)
        for clip in clips
    ]
    elapsed = time.perf_counter() - started
    duration = sum(result.duration_seconds for result in heard)
    reference = words(" ".join(text for _, text in lines))
    hypothesis = words(" ".join(result.text for result in heard))
    report = {
        "model": f"faster-whisper {args.model} ({args.compute}, CPU)",
        "date": date.today().isoformat(),
        "machine": f"{platform.system()} {platform.release()}, {platform.processor()}",
        "audio_seconds": round(duration, 1),
        "transcription_seconds": round(elapsed, 1),
        "real_time_factor": round(elapsed / duration, 2),
        "wer": round(word_error_rate(reference, hypothesis), 3),
        "reference_words": len(reference),
        "audio_bytes": AUDIO.stat().st_size,
        "transcript": "\n".join(
            f"{speaker}: {' '.join(result.text.split())}"
            for (speaker, _), result in zip(lines, heard, strict=True)
        ),
    }
    RESULT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "transcript"}, indent=2))
    print(report["transcript"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
