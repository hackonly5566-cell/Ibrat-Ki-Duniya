
import os, json, random, hashlib, time, subprocess, asyncio, requests
import edge_tts

GEMINI_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
PIXABAY_KEY = os.environ[58580632-07c43614bd6c680f9ee0a443d]
CLOUD_NAME = os.environ["CLOUDINARY_CLOUD_NAME"]
CLOUD_KEY = os.environ["CLOUDINARY_API_KEY"]
CLOUD_SECRET = os.environ["CLOUDINARY_API_SECRET"]
TW_SID = os.environ["TWILIO_ACCOUNT_SID"]
TW_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
TW_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
TW_TO = os.environ["MY_WHATSAPP"]
VOICE = os.environ.get("TTS_VOICE", "ur-PK-AsadNeural")

THEMES = [
    "ماں کی دعا کا اثر", "غرور کا انجام", "وقت کی قدر",
    "سچ بولنے کا انعام", "والدین کی خدمت", "صبر کا پھل",
    "دوست کی پہچان", "لالچ کا نقصان", "نیکی کا بدلہ", "شکر گزاری",
]

def make_story():
    theme = random.choice(THEMES)
    prompt = f"""تم ایک اردو کہانی کار ہو۔ موضوع: "{theme}"۔
ایک مختصر سبق آموز کہانی لکھو جو بولنے میں تقریباً 45 سے 60 سیکنڈ لے (120 سے 150 الفاظ)۔
سادہ اردو، آخر میں ایک سبق۔
صرف JSON لوٹاؤ، اس کے علاوہ کچھ نہیں، ان کیز کے ساتھ:
title: اردو عنوان
script: وائس اوور کا مکمل متن (اردو رسم الخط)
caption: فیس بک کیپشن، اردو، ایموجی کے ساتھ، 2 سے 3 جملے
hashtags: 5 اردو ہیش ٹیگز ایک سٹرنگ میں
pexels_query: انگریزی میں 2 سے 3 الفاظ، جو کہانی کے مزاج سے ملتی ویڈیو تلاش کریں (مثلاً sad old man, sunset village, rain window)"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}"
    r = requests.post(url, json={
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }, timeout=120)
    r.raise_for_status()
    text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)

async def make_voice(text, path):
    await edge_tts.Communicate(text, VOICE).save(path)

def download_clips(query, n=3):
    r = requests.get("https://api.pexels.com/videos/search",
                     headers={"Authorization": PEXELS_KEY},
                     params={"query": query, "orientation": "portrait", "per_page": 10},
                     timeout=60)
    r.raise_for_status()
    videos = r.json().get("videos", [])
    if not videos:
        r = requests.get("https://api.pexels.com/videos/search",
                         headers={"Authorization": PEXELS_KEY},
                         params={"query": "nature sky", "orientation": "portrait", "per_page": 10},
                         timeout=60)
        videos = r.json()["videos"]
    random.shuffle(videos)
    paths = []
    for i, v in enumerate(videos[:n]):
        files = [f for f in v["video_files"] if f.get("width") and f["width"] <= 1080]
        files.sort(key=lambda f: abs(f["width"] - 720))
        data = requests.get(files[0]["link"], timeout=180).content
        p = f"raw_{i}.mp4"
        open(p, "wb").write(data)
        paths.append(p)
    return paths

def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

def build_video(clips, audio, out):
    norm = []
    for i, c in enumerate(clips):
        n = f"clip_{i}.mp4"
        run(["ffmpeg", "-y", "-i", c, "-an", "-t", "12",
             "-vf", "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps=30",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", n])
        norm.append(n)
    with open("list.txt", "w") as f:
        for n in norm:
            f.write(f"file '{n}'\n")
    run(["ffmpeg", "-y", "-stream_loop", "-1", "-f", "concat", "-safe", "0", "-i", "list.txt",
         "-i", audio, "-map", "0:v", "-map", "1:a", "-shortest",
         "-c:v", "libx264", "-crf", "30", "-preset", "veryfast", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", out])

def upload_cloudinary(path):
    ts = str(int(time.time()))
    sig = hashlib.sha1(f"timestamp={ts}{CLOUD_SECRET}".encode()).hexdigest()
    with open(path, "rb") as f:
        r = requests.post(f"https://api.cloudinary.com/v1_1/{CLOUD_NAME}/video/upload",
                          data={"api_key": CLOUD_KEY, "timestamp": ts, "signature": sig},
                          files={"file": f}, timeout=300)
    r.raise_for_status()
    return r.json()["secure_url"]

def send_whatsapp(video_url, body):
    r = requests.post(f"https://api.twilio.com/2010-04-01/Accounts/{TW_SID}/Messages.json",
                      auth=(TW_SID, TW_TOKEN),
                      data={"From": TW_FROM, "To": TW_TO, "Body": body, "MediaUrl": video_url},
                      timeout=60)
    print(r.status_code, r.text[:300])
    r.raise_for_status()

def main():
    story = make_story()
    print("Title:", story["title"])
    asyncio.run(make_voice(story["script"], "voice.mp3"))
    clips = download_clips(story["pexels_query"])
    build_video(clips, "voice.mp3", "final.mp4")
    print("Video MB:", round(os.path.getsize("final.mp4") / 1e6, 2))
    url = upload_cloudinary("final.mp4")
    body = f"{story['title']}\n\n{story['caption']}\n\n{story['hashtags']}"
    send_whatsapp(url, body)
    print("Done:", url)

if __name__ == "__main__":
    main()
