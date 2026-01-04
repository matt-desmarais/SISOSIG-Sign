#!/usr/bin/env python3

import time
import requests
from io import BytesIO
from PIL import Image
from inky.auto import auto
import datetime
import subprocess

# ================= CONFIG =================
IMAGE_URLS = [
    "https://sisosig.info/temp/massdot.jpg",
    "https://sisosig.info/temp/massdot_graph.jpg",
]

LOGO_PATH = "sisosig.png"
QR_PATH = "qr-code.png"

SLIDE_SECONDS = 30
MAX_RETRIES = 3
TIMEOUT = 10

OFFLINE_THRESHOLD = 3
ONLINE_THRESHOLD = 1

WIFI_INTERFACE = "wlan0"

REFRESH_RETRY_SECONDS = 10   # retry downloads until success
# ==========================================

# ================= DISPLAY =================
display = auto(ask_user=False, verbose=False)
WIDTH, HEIGHT = display.resolution
print(f"[DEBUG] Display resolution: {WIDTH}x{HEIGHT}")

# ================= LOAD LOGO =================
with open(LOGO_PATH, "rb") as f:
    logo_bytes = f.read()
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
        connected = "state UP" in out and "inet " in out
        print(f"[DEBUG] WiFi {interface}: {'CONNECTED' if connected else 'DISCONNECTED'}")
        return connected
    except Exception as e:
        print(f"[DEBUG] WiFi check error: {e}")
        return False

# ================= QR SLIDE =================
def load_qr_slide():
    img = Image.open(QR_PATH).convert("RGB")
    iw, ih = img.size
    scale = min(WIDTH / iw, HEIGHT / ih)
    img = img.resize((int(iw * scale), int(ih * scale)), Image.Resampling.NEAREST)

    canvas = Image.new("RGB", (WIDTH, HEIGHT), (255, 255, 255))
    canvas.paste(img, ((WIDTH - img.width)//2, (HEIGHT - img.height)//2))
    print("[DEBUG] QR slide prepared")
    return canvas

offline_slide = load_qr_slide()

# ================= IMAGE DOWNLOAD =================
def download_image(url):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"[DEBUG] Downloading {url} (attempt {attempt})")
            r = requests.get(url, timeout=TIMEOUT)
            r.raise_for_status()
            return Image.open(BytesIO(r.content)).convert("RGB")
        except Exception as e:
            print(f"[DEBUG] Download failed: {e}")
            time.sleep(1)
    return None

# ================= PREPARE SLIDE =================
def prepare_slide(url):
    img = download_image(url)
    if not img:
        return None

    canvas = Image.new("RGB", (WIDTH, HEIGHT), (255, 255, 255))

    iw, ih = img.size
    scale = WIDTH / iw
    new_h = int(ih * scale)
    img = img.resize((WIDTH, new_h), Image.Resampling.LANCZOS)
    canvas.paste(img, (0, 0))

    footer_y = min(new_h, HEIGHT)
    footer_h = HEIGHT - footer_y

    if footer_h > 5:
        logo = Image.open(BytesIO(logo_bytes)).convert("RGBA")
        lw, lh = logo.size
        scale = footer_h / lh
        logo = logo.resize(
            (int(lw * scale), int(lh * scale)),
            Image.Resampling.LANCZOS,
        )
        canvas.paste(
            logo,
            ((WIDTH - logo.width)//2, footer_y),
            logo,
        )

    return canvas

# ================= ATOMIC FETCH =================
def fetch_slides_atomic():
    print("[DEBUG] Fetching slides (atomic)")
    new_slides = []

    for url in IMAGE_URLS:
        slide = prepare_slide(url)
        if not slide:
            print("[DEBUG] Slide refresh FAILED — keeping current slides")
            return None
        new_slides.append(slide)

    print("[DEBUG] Slide refresh SUCCESS")
    return new_slides

# ================= STATE =================
slides = []
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
        print("[DEBUG] Transition to OFFLINE")
        display.set_image(offline_slide)
        display.show()
        offline_mode = True

    if online_successes >= ONLINE_THRESHOLD and offline_mode:
        print("[DEBUG] Transition to ONLINE")
        new_slides = fetch_slides_atomic()
        if new_slides:
            slides = new_slides
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
        print("[DEBUG] Attempting refresh (retry-until-success)")
        last_refresh_attempt = now_mono

        new_slides = fetch_slides_atomic()
        if new_slides:
            print("[DEBUG] Refresh committed immediately")
            slides = new_slides
            slide_index = 0
            last_refresh_bucket = bucket

    # ---------- Slide timing ----------
    if slides and now_mono >= next_slide_time:
        display.set_image(slides[slide_index])
        display.show()
        print(f"[DEBUG] Displayed slide {slide_index}")
        slide_index = (slide_index + 1) % len(slides)
        next_slide_time += SLIDE_SECONDS

    time.sleep(0.1)
