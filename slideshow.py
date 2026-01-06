#!/usr/bin/env python3

import time
import requests
from io import BytesIO
from PIL import Image
from inky.auto import auto
import datetime
import subprocess
import hashlib

# ================= CONFIG =================
IMAGE_URLS = [
    "https://sisosig.info/temp/massdot.jpg",
    "https://sisosig.info/temp/massdot_graph.jpg",
]

LOGO_PATH = "sisosig.png"
QR_PATH = "qr-code.png"

SLIDE_SECONDS = 32
MAX_RETRIES = 3
TIMEOUT = 10

OFFLINE_THRESHOLD = 3
ONLINE_THRESHOLD = 1

WIFI_INTERFACE = "wlan0"

REFRESH_RETRY_SECONDS = 10
# ==========================================

# ================= DISPLAY =================
display = auto(ask_user=False, verbose=False)
WIDTH, HEIGHT = display.resolution
print(f"[DEBUG] Display resolution: {WIDTH}x{HEIGHT}")

# ================= LOAD ASSETS =================
with open(LOGO_PATH, "rb") as f:
    logo_bytes = f.read()

LOGO_IMAGE = Image.open(BytesIO(logo_bytes)).convert("RGBA")
print("[DEBUG] Logo loaded")

# ================= WIFI CHECK =================
def wifi_connected(interface=WIFI_INTERFACE):
    try:
        out = subprocess.run(
            ["ip", "addr", "show", interface],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        ).stdout
        return "state UP" in out and "inet " in out
    except Exception:
        return False

# ================= QR SLIDE =================
def load_qr_slide():
    img = Image.open(QR_PATH).convert("RGB")
    iw, ih = img.size
    scale = min(WIDTH / iw, HEIGHT / ih)
    img = img.resize((int(iw * scale), int(ih * scale)), Image.Resampling.NEAREST)

    canvas = Image.new("RGB", (WIDTH, HEIGHT), (255, 255, 255))
    canvas.paste(img, ((WIDTH - img.width)//2, (HEIGHT - img.height)//2))
    return canvas

offline_slide = load_qr_slide()

# ================= IMAGE DOWNLOAD =================
def download_image(url):
    for _ in range(MAX_RETRIES):
        try:
            r = requests.get(url, timeout=TIMEOUT)
            r.raise_for_status()
            data = r.content
            h = hashlib.sha256(data).hexdigest()
            img = Image.open(BytesIO(data)).convert("RGB")
            return img, h
        except Exception:
            time.sleep(1)
    return None, None

# ================= PREPARE SLIDE =================
def prepare_slide(url):
    img, h = download_image(url)
    if not img:
        return None, None

    canvas = Image.new("RGB", (WIDTH, HEIGHT), (255, 255, 255))

    iw, ih = img.size
    scale = WIDTH / iw
    new_h = int(ih * scale)
    img = img.resize((WIDTH, new_h), Image.Resampling.LANCZOS)
    canvas.paste(img, (0, 0))

    footer_y = min(new_h, HEIGHT)
    footer_h = HEIGHT - footer_y

    if footer_h > 5:
        lw, lh = LOGO_IMAGE.size
        s = footer_h / lh
        logo = LOGO_IMAGE.resize(
            (int(lw * s), int(lh * s)),
            Image.Resampling.LANCZOS,
        )
        canvas.paste(
            logo,
            ((WIDTH - logo.width)//2, footer_y),
            logo,
        )

    return canvas, h

# ================= ATOMIC FETCH =================
def fetch_slides_atomic():
    slides = []
    hashes = []

    for url in IMAGE_URLS:
        slide, h = prepare_slide(url)
        if not slide:
            return None
        slides.append(slide)
        hashes.append(h)

    return slides, hashes

# ================= STATE =================
slides = []
slide_hashes = []
slide_index = 0
next_slide_time = time.monotonic()

offline_failures = 0
online_successes = 0
offline_mode = True

last_refresh_bucket = None
last_refresh_attempt = 0

# ================= INITIAL DISPLAY =================
display.set_image(offline_slide)
display.show()
print("[DEBUG] Initial QR displayed")

# ================= MAIN LOOP =================
while True:
    now_mono = time.monotonic()
    wall = datetime.datetime.now()

    # ---------- Connectivity debounce ----------
    if wifi_connected():
        online_successes += 1
        offline_failures = 0
    else:
        offline_failures += 1
        online_successes = 0

    if offline_failures >= OFFLINE_THRESHOLD and not offline_mode:
        display.set_image(offline_slide)
        display.show()
        offline_mode = True

    if online_successes >= ONLINE_THRESHOLD and offline_mode:
        result = fetch_slides_atomic()
        if result:
            slides, slide_hashes = result
            slide_index = 0
            next_slide_time = now_mono
            offline_mode = False

    if offline_mode:
        time.sleep(5)
        continue

    # ---------- 5-minute bucket ----------
    bucket = (wall.hour, wall.minute // 5)

    # ---------- Retry-until-success refresh ----------
    if (
        wall.second >= 12
        and last_refresh_bucket != bucket
        and now_mono - last_refresh_attempt >= REFRESH_RETRY_SECONDS
    ):
        last_refresh_attempt = now_mono
        result = fetch_slides_atomic()

        if result:
            new_slides, new_hashes = result

            if new_hashes != slide_hashes:

                # Only commit and refresh if we successfully have all slides
                if all(new_slides):
                    # Optional: very quick flash to reduce ghosting
                    # display.set_image(Image.new("RGB", (WIDTH, HEIGHT), (255, 255, 255)))
                    # display.show()
                    # time.sleep(0.05)

                    slides = new_slides
                    slide_hashes = new_hashes
                    slide_index = 0
                    last_refresh_bucket = bucket
                    next_slide_time = now_mono
                    print("[DEBUG] Content changed — refresh committed")
                else:
                    print("[DEBUG] Slide download incomplete — keeping current display")


            else:
                print("[DEBUG] Content identical — retrying")

    # ---------- Slide timing ----------
    if slides and now_mono >= next_slide_time:
        display.set_image(slides[slide_index])
        display.show()
        slide_index = (slide_index + 1) % len(slides)
        next_slide_time = now_mono + SLIDE_SECONDS

    time.sleep(0.1)
