"""Bounded local media rendering. Fixed argv only; no remote URLs or model calls."""

import asyncio
import json
import math
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Edit(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    mode: Literal["video", "narration", "sound"] = "video"
    start: float = Field(default=0, ge=0, le=7200)
    duration: float = Field(default=15, ge=1, le=60)
    original_volume: float = Field(default=1, ge=0, le=2)
    music_volume: float = Field(default=0.25, ge=0, le=1)
    narration: str = Field(default="", max_length=1500)
    voice: Literal["en-us", "en-gb", "es", "fr", "de"] = "en-us"
    speed: int = Field(default=165, ge=100, le=230)
    effect: Literal["none", "chime", "beep", "soft_tone"] = "none"
    effect_volume: float = Field(default=0.15, ge=0, le=0.5)
    fade: float = Field(default=0.4, ge=0, le=3)

    @model_validator(mode="after")
    def content(self):
        if self.mode == "narration" and not self.narration.strip():
            raise ValueError("Enter narration text.")
        if self.mode == "sound" and self.effect == "none":
            raise ValueError("Choose a sound effect.")
        return self


async def command(*argv, timeout=180):
    process = await asyncio.create_subprocess_exec(
        *map(str, argv),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout)
        if process.returncode:
            raise ValueError("Media could not be decoded or rendered. Try an MP4 video or WAV/MP3 audio file.")
        return output
    except BaseException:
        if process.returncode is None:
            process.kill()
            await process.wait()
        raise


INPUT = ("-protocol_whitelist", "file,pipe", "-format_whitelist", "mov,matroska,webm,wav,mp3,ogg,flac,aac")


async def probe(path):
    raw = await command(
        "ffprobe", "-v", "error", *INPUT, "-show_streams", "-show_format", "-of", "json", path, timeout=15
    )
    info = json.loads(raw)
    duration = float(info.get("format", {}).get("duration", 0))
    if not math.isfinite(duration) or duration <= 0 or duration > 7200:
        raise ValueError("Use media with a known duration of at most two hours.")
    for stream in info.get("streams", []):
        if (
            stream.get("codec_type") == "video"
            and int(stream.get("width", 0)) * int(stream.get("height", 0)) > 3840 * 2160
        ):
            raise ValueError("Use a video no larger than 4K.")
    return info, duration


async def render(folder: Path, edit: Edit):
    video = folder / "video.input"
    music = folder / "audio.input"
    speech = folder / "speech.wav"
    if edit.narration.strip():
        text = folder / "narration.txt"
        text.write_text(edit.narration, encoding="utf-8")
        await command("espeak-ng", "-v", edit.voice, "-s", edit.speed, "-w", speech, "-f", text, timeout=30)
    if edit.mode == "narration":
        # Do not silently truncate a long spoken script at the video duration.
        _, length = await probe(speech)
        if length > 180:
            raise ValueError("Narration exceeds three minutes. Shorten the script.")
        output = folder / "Narration.wav"
        speech.replace(output)
        return output
    duration = edit.duration
    args = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-threads", "1", "-filter_complex_threads", "1"]
    filters, tracks = [], []
    index = 0
    if edit.mode == "video":
        if not video.is_file():
            raise ValueError("Upload a video first.")
        info, length = await probe(video)
        if not any(s.get("codec_type") == "video" for s in info["streams"]):
            raise ValueError("The selected file has no video track.")
        if edit.start >= length or edit.start + duration > length + 0.15:
            raise ValueError("Trim start plus duration exceeds the source video. Reduce the duration.")
        args += [*INPUT, "-ss", str(edit.start), "-i", str(video)]
        index += 1
        filters.append("[0:v]scale=1280:720:force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1,fps=30[v]")
        if edit.original_volume and any(s.get("codec_type") == "audio" for s in info["streams"]):
            filters.append(
                f"[0:a]volume={edit.original_volume},apad,atrim=duration={duration},asetpts=PTS-STARTPTS[a0]"
            )
            tracks.append("[a0]")
    if edit.mode == "video" and music.is_file():
        info, _ = await probe(music)
        if not any(s.get("codec_type") == "audio" for s in info["streams"]):
            raise ValueError("The soundtrack has no audio track.")
        args += [*INPUT, "-i", str(music)]
        filters.append(
            f"[{index}:a]volume={edit.music_volume},apad,atrim=duration={duration},asetpts=PTS-STARTPTS[music]"
        )
        tracks.append("[music]")
        index += 1
    if edit.mode == "video" and speech.is_file():
        _, length = await probe(speech)
        if length > duration + 0.1:
            raise ValueError("Narration is longer than the clip. Shorten the script or increase the duration.")
        args += [*INPUT, "-i", str(speech)]
        filters.append(f"[{index}:a]apad,atrim=duration={duration},asetpts=PTS-STARTPTS[speech]")
        tracks.append("[speech]")
        index += 1
    if edit.effect != "none":
        frequency = {"chime": 880, "beep": 660, "soft_tone": 220}[edit.effect]
        tone_length = min(duration, 1.2 if edit.effect == "chime" else 0.4 if edit.effect == "beep" else duration)
        # lavfi is only used for this fixed, numeric generated source.
        args += ["-f", "lavfi", "-i", f"sine=frequency={frequency}:duration={tone_length}:sample_rate=44100"]
        fade = min(0.15, tone_length / 2)
        filters.append(
            f"[{index}:a]volume={edit.effect_volume},afade=t=out:st={tone_length - fade}:d={fade},apad,atrim=duration={duration}[effect]"  # noqa: E501 - bounded fixed schema/filter or installer metadata
        )
        tracks.append("[effect]")
    if tracks:
        fade = min(edit.fade, duration / 2)
        filters.append(
            "".join(tracks)
            + f"amix=inputs={len(tracks)}:normalize=0,alimiter=limit=0.95,afade=t=in:d={fade},afade=t=out:st={duration - fade}:d={fade}[audio]"  # noqa: E501 - bounded fixed schema/filter or installer metadata
        )
    args += ["-filter_complex", ";".join(filters)]
    if edit.mode == "video":
        output = folder / "Edited_video.mp4"
        args += [
            "-map",
            "[v]",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-threads",
            "1",
            "-movflags",
            "+faststart",
        ]
        args += ["-map", "[audio]", "-c:a", "aac", "-b:a", "128k"] if tracks else ["-an"]
    else:
        output = folder / "Sound_effect.wav"
        args += ["-map", "[audio]", "-c:a", "pcm_s16le"]
    args += ["-t", str(duration), "-map_metadata", "-1", "-fs", str(100 * 1024 * 1024), str(output)]
    await command(*args)
    _, actual_duration = await probe(output)
    if abs(actual_duration - duration) > 0.3:
        raise ValueError("Export was incomplete. Reduce clip size or duration and try again.")
    return output
