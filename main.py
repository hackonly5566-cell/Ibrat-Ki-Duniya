
import os
import re
import json
import time
import random
import hashlib
import subprocess
import asyncio
from pathlib import Path

import requests
import edge_tts


# =========================================================
# IBRAT KI DUNIYA - AUTOMATIC PASHTO STORY VIDEO STUDIO
# Target: 10 minutes | Vertical 9:16 | MP4
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
WORK_DIR = BASE_DIR / "work"
WORK_DIR.mkdir(exist_ok=True)

OUTPUT = BASE_DIR / "final.mp4"
AUDIO = WORK_DIR / "voice.mp3"

GEMINI_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

PIXABAY_KEY = os.environ["PIXABAY_API_KEY"]

CLOUD_NAME = os.environ["CLOUDINARY_CLOUD_NAME"]
CLOUD_KEY = os.environ["CLOUDINARY_API_KEY"]
CLOUD_SECRET = os.environ["CLOUDINARY_API_SECRET"]

TW_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TW_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TW_TO = os.environ.get("MY_WHATSAPP", "")

TW_FROM = os.environ.get(
    "TWILIO_WHATSAPP_FROM",
    "whatsapp:+14155238886"
)

VOICE = os.environ.get(
    "TTS_VOICE",
    "ps-AF-LatifaNeural"
)

VIDEO_SECONDS = 600
VIDEO_WIDTH = 720
VIDEO_HEIGHT = 1280
FPS = 30

GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/"
    f"v1beta/models/{GEMINI_MODEL}:generateContent"
)

PIXABAY_URL = "https://pixabay.com/api/videos/"


THEMES = [
    "د مور د دعا اغېز",
    "د غرور بد انجام",
    "د رښتيا ويلو انعام",
    "د پلار او مور خدمت",
    "د صبر خوږه مېوه",
    "د ملګري اصلي پېژندنه",
    "د حرص او لالچ تاوان",
    "د نېکۍ بدله",
    "د وخت ارزښت",
    "د غريب انسان عزت",
    "د يتيم ماشوم مرسته",
    "د ورورولۍ او مينې ارزښت",
    "د يوې وړې نېکۍ لوی اجر",
]


def log(message):
    print(f"[IBRAT] {message}", flush=True)


def run(command):
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Command failed:\n" +
            result.stderr[-2500:]
        )

    return result


def check_tools():
    for tool in ["ffmpeg", "ffprobe"]:
        result = subprocess.run(
            ["which", tool],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"{tool} is missing. Install FFmpeg first."
            )


def gemini_request(prompt):
    for attempt in range(3):
        try:
            response = requests.post(
                GEMINI_URL,
                params={"key": GEMINI_KEY},
                json={
                    "contents": [{
                        "parts": [{"text": prompt}]
                    }],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                        "temperature": 0.9,
                        "maxOutputTokens": 8192
                    }
                },
                timeout=240
            )

            response.raise_for_status()

            data = response.json()
            candidates = data.get("candidates", [])

            if not candidates:
                raise RuntimeError(
                    "Gemini returned no story candidate."
                )

            parts = candidates[0]["content"]["parts"]
            raw = "".join(
                part.get("text", "") for part in parts
            )

            raw = raw.strip()

            raw = re.sub(
                r"^```(?:json)?\s*|\s*```$",
                "",
                raw
            )

            return json.loads(raw)

        except Exception as exc:
            log(f"Gemini attempt {attempt + 1}: {exc}")

            if attempt == 2:
                raise

            time.sleep(5 * (attempt + 1))


def make_story():
    theme = random.choice(THEMES)

    prompt = f"""
You are an expert Pashto moral-story writer.

Write ONE original, emotionally powerful story
for a Facebook page called Ibrat Ki Duniya.

THEME:
{theme}

LANGUAGE:
Natural spoken Pashto used by people in Khyber
Pakhtunkhwa and Afghanistan.

SCRIPT:
Use Pashto Arabic script.
Do not write Urdu.
Do not write Roman Pashto.
Avoid difficult literary vocabulary.

LENGTH:
The narration must target approximately
1000 to 1150 Pashto words.

This is for a TEN-MINUTE voice-over.
Do not write a short story.
Do not summarize.
Do not finish early.

STORY STRUCTURE:
1. Powerful opening hook.
2. Introduce believable characters.
3. Establish a village or family setting.
4. Build emotional suspense gradually.
5. Include natural dialogue.
6. Include an unexpected but believable turning point.
7. Give a satisfying conclusion.
8. End with a meaningful moral lesson.

IMPORTANT:
Make it original.
Do not copy existing stories.
Keep characters and names consistent.
Make it suitable for a family audience.

Also generate:
- A short Pashto title.
- A Facebook caption in Pashto.
- Five Pashto hashtags.
- Four to six English Pixabay video search queries.

Return ONLY valid JSON with this structure:

{{
  "title": "Pashto title",
  "script": "Complete Pashto narration",
  "caption": "Pashto Facebook caption",
  "hashtags": "#tag1 #tag2 #tag3 #tag4 #tag5",
  "pixabay_queries": [
    "village life",
    "mountain village",
    "family walking",
    "sunset countryside"
  ]
}}
"""

    story = gemini_request(prompt)

    required = [
        "title",
        "script",
        "caption",
        "hashtags",
        "pixabay_queries"
    ]

    for key in required:
        if key not in story:
            raise ValueError(f"Story missing field: {key}")

    if len(story["script"].split()) < 600:
        log("Story too short. Requesting a longer version.")

        story = gemini_request(
            prompt +
            "\nIMPORTANT: Your previous output was too short. "
            "Write a complete long story of at least 1000 words."
        )

    if len(story["script"].split()) < 600:
        raise RuntimeError(
            "Story is too short. Stopping instead of "
            "creating a misleading 10-minute video."
        )

    return story


async def make_voice(text, path):
    communicate = edge_tts.Communicate(
        text=text,
        voice=VOICE,
        rate="+0%",
        volume="+0%"
    )

    await communicate.save(str(path))


def audio_duration(path):
    result = run([
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path)
    ])

    return float(result.stdout.strip())


def search_pixabay(query):
    response = requests.get(
        PIXABAY_URL,
        params={
            "key": PIXABAY_KEY,
            "q": query,
            "video_type": "film",
            "safesearch": "true",
            "per_page": 10,
            "order": "popular"
        },
        timeout=60
    )

    response.raise_for_status()

    return response.json().get("hits", [])


def download_file(url, destination):
    for attempt in range(3):
        try:
            with requests.get(
                url,
                stream=True,
                timeout=(30, 180)
            ) as response:

                response.raise_for_status()

                with open(destination, "wb") as file:
                    for chunk in response.iter_content(
                        chunk_size=1024 * 1024
                    ):
                        if chunk:
                            file.write(chunk)

            if Path(destination).stat().st_size < 10000:
                raise RuntimeError("Downloaded video is too small.")

            return destination

        except Exception:
            if attempt == 2:
                raise

            time.sleep(4)

    raise RuntimeError("Video download failed.")


def download_clips(queries):
    clip_dir = WORK_DIR / "clips"
    clip_dir.mkdir(exist_ok=True)

    clips = []
    seen_ids = set()

    for query in queries[:6]:
        log(f"Searching Pixabay: {query}")

        try:
            hits = search_pixabay(query)

            for hit in hits:
                if len(clips) >= 12:
                    break

                video_id = hit.get("id")

                if video_id in seen_ids:
                    continue

                videos = hit.get("videos", {})

                video = (
                    videos.get("medium")
                    or videos.get("small")
                    or videos.get("tiny")
                )

                if not video or not video.get("url"):
                    continue

                destination = (
                    clip_dir / f"pixabay_{video_id}.mp4"
                )

                download_file(
                    video["url"],
                    destination
                )

                clips.append(str(destination))
                seen_ids.add(video_id)

                log(f"Downloaded clip {len(clips)}")

        except Exception as exc:
            log(f"Pixabay query failed: {exc}")

        if len(clips) >= 8:
            break

        time.sleep(2)

    if not clips:
        raise RuntimeError(
            "No Pixabay videos downloaded. "
            "Check PIXABAY_API_KEY and network."
        )

    return clips


def build_video(clips, audio, output):
    duration = audio_duration(audio)

    log(f"Voice duration: {duration:.1f} seconds")

    normalized_dir = WORK_DIR / "normalized"
    normalized_dir.mkdir(exist_ok=True)

    normalized = []

    for index, clip in enumerate(clips):
        target = normalized_dir / f"clip_{index}.mp4"

        log(f"Preparing clip {index + 1}/{len(clips)}")

        run([
            "ffmpeg", "-y",
            "-stream_loop", "-1",
            "-i", clip,
            "-t", "20",
            "-an",
            "-vf",
            (
                f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:"
                "force_original_aspect_ratio=increase,"
                f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},"
                f"fps={FPS},setsar=1"
            ),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "27",
            "-pix_fmt", "yuv420p",
            str(target)
        ])

        normalized.append(target)

    playlist = WORK_DIR / "playlist.txt"

    segment_duration = 20
    segments_needed = int(
        duration / segment_duration
    ) + 2

    with open(playlist, "w", encoding="utf-8") as file:
        for index in range(segments_needed):
            clip = normalized[index % len(normalized)]

            safe_path = str(clip.resolve()).replace(
                "'", "'\\''"
            )

            file.write(f"file '{safe_path}'\n")

    log("Joining video clips and voice-over.")

    run([
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(playlist),
        "-i", str(audio),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-vf",
        (
            f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT},"
            f"fps={FPS},format=yuv420p"
        ),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "29",
        "-c:a", "aac",
        "-b:a", "96k",
        "-ar", "44100",
        "-shortest",
        "-movflags", "+faststart",
        str(output)
    ])

    actual_duration = audio_duration(output)

    if actual_duration < duration - 2:
        raise RuntimeError(
            "Final video is shorter than the voice-over."
        )

    log(f"Final duration: {actual_duration:.1f} seconds")


def upload_cloudinary(path):
    timestamp = str(int(time.time()))

    signature_text = (
        f"timestamp={timestamp}{CLOUD_SECRET}"
    )

    signature = hashlib.sha1(
        signature_text.encode("utf-8")
    ).hexdigest()

    log("Uploading video to Cloudinary.")

    with open(path, "rb") as file:
        response = requests.post(
            (
                f"https://api.cloudinary.com/v1_1/"
                f"{CLOUD_NAME}/video/upload"
            ),
            data={
                "api_key": CLOUD_KEY,
                "timestamp": timestamp,
                "signature": signature
            },
            files={"file": file},
            timeout=900
        )

    response.raise_for_status()

    result = response.json()

    if not result.get("secure_url"):
        raise RuntimeError("Cloudinary returned no video URL.")

    return result["secure_url"]


def send_whatsapp(video_url, story, file_size):
    body = (
        f"{story['title']}\n\n"
        f"{story['caption']}\n\n"
        f"{story['hashtags']}\n\n"
        f"Watch the complete video:\n{video_url}\n\n"
        "Ibrat Ki Duniya"
    )

    data = {
        "From": TW_FROM,
        "To": TW_TO,
        "Body": body
    }

    # WhatsApp video attachments have size restrictions.
    # Send a public link instead of attaching oversized files.
    if file_size <= 15 * 1024 * 1024:
        data["MediaUrl"] = video_url

    response = requests.post(
        (
            f"https://api.twilio.com/2010-04-01/"
            f"Accounts/{TW_SID}/Messages.json"
        ),
        auth=(TW_SID, TW_TOKEN),
        data=data,
        timeout=120
    )

    response.raise_for_status()

    log("WhatsApp message accepted by Twilio.")


def save_story(story):
    destination = BASE_DIR / "latest_story.json"

    with open(destination, "w", encoding="utf-8") as file:
        json.dump(
            story,
            file,
            ensure_ascii=False,
            indent=2
        )


def main():
    log("Starting Ibrat Ki Duniya AI Studio.")

    check_tools()

    log("Step 1: Creating Pashto story.")
    story = make_story()

    log(f"Title: {story['title']}")

    save_story(story)

    log("Step 2: Generating female Pashto narration.")

    asyncio.run(
        make_voice(story["script"], AUDIO)
    )

    voice_length = audio_duration(AUDIO)

    log(f"Voice created: {voice_length:.1f} seconds")

    if voice_length < 480:
        raise RuntimeError(
            "Voice-over is shorter than 8 minutes. "
            "Not publishing a short video as a 10-minute video."
        )

    log("Step 3: Downloading Pixabay footage.")

    queries = story.get("pixabay_queries", [])

    if not queries:
        queries = [
            "village life",
            "mountain village",
            "family walking",
            "sunset countryside"
        ]

    clips = download_clips(queries)

    log(f"Downloaded {len(clips)} video clips.")

    log("Step 4: Editing final vertical video.")

    build_video(
        clips,
        AUDIO,
        OUTPUT
    )

    file_size = OUTPUT.stat().st_size

    log(
        f"Final MP4 size: {file_size / 1024 / 1024:.2f} MB"
    )

    log("Step 5: Uploading to Cloudinary.")

    video_url = upload_cloudinary(OUTPUT)

    log("Step 6: Sending WhatsApp delivery.")

    send_whatsapp(
        video_url,
        story,
        file_size
    )

    log("=" * 45)
    log("VIDEO GENERATION SUCCESSFUL")
    log(f"TITLE: {story['title']}")
    log(f"VIDEO: {video_url}")
    log("=" * 45)


if __name__ == "__main__":
    main()
