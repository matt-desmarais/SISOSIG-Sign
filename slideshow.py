import time
import requests
from io import BytesIO
from PIL import Image
from inky.auto import auto
import datetime
import subprocess

# ---------------- CONFIG ----------------
IMAGE_URLS = [
    "https://sisosig.info/temp/massdot.jpg",
    "https://sisosig.info/temp/massdot_graph.jpg"
]

LOGO_PATH = "sisosig.png"
QR_PATH = "qr-code.png"

SLIDE_SECONDS = 30
MAX_RETRIES = 3
TIMEOUT = 10  # seconds per request

# Offline/online debounce
OFFLINE_THRESHOLD = 3
ONLINE_THRESHOLD = 1

# ---------------- DISPLAY SETUP ----------------
display = auto(ask_user=False, verbose=False)
WIDTH, HEIGHT = display.resolution
print(f"[DEBUG] Display resolution: {WIDTH}x{HEIGHT}")

# ---------------- PRELOAD LOGO ----------------
with open(LOGO_PATH, "rb") as f:
    logo_bytes = f.read()
print("[DEBUG] Logo preloaded into memory")

# ---------------- WIFI CHECK ----------------
def wifi_connected(interface="wlan0"):
    try:
        result = subprocess.run(
            ["ip", "addr", "show", interface],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True
        )
        output = result.stdout
        connected = "state UP" in output and "inet " in output
        print(f"[DEBUG] Wi-Fi check ({interface}): {'CONNECTED' if connected else 'DISCONNECTED'}")
        return connected
    except Exception as e:
        print(f"[DEBUG] Wi-Fi check exception: {e}")
        return False

# ---------------- QR SLIDE ----------------
def load_qr_slide():
    img = Image.open(QR_PATH).convert("RGB")
    iw, ih = img.size
    scale = min(WIDTH / iw, HEIGHT / ih)
    img = img.resize((int(iw * scale), int(ih * scale)), Image.Resampling.NEAREST)

    canvas = Image.new("RGB", (WIDTH, HEIGHT), (255, 255, 255))
    x = (WIDTH - img.width) // 2
    y = (HEIGHT - img.height) // 2
    canvas.paste(img, (x, y))
    print("[DEBUG] QR slide loaded")
    return canvas

offline_slide = load_qr_slide()

# ---------------- IMAGE DOWNLOAD ----------------
def download_image(url):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"[DEBUG] Downloading image {url}, attempt {attempt}")
            response = requests.get(url, timeout=TIMEOUT)
            response.raise_for_status()
            print(f"[DEBUG] Successfully downloaded {url}")
            return Image.open(BytesIO(response.content)).convert("RGB")
        except Exception as e:
            print(f"[DEBUG] Attempt {attempt} failed for {url}: {e}")
            time.sleep(1)
    print(f"[DEBUG] Failed to download {url} after {MAX_RETRIES} attempts")
    return None

# ---------------- PREPARE SLIDE ----------------
def prepare_slide(image_url):
    print(f"[DEBUG] Preparing slide for {image_url}")
    canvas = Image.new("RGB", (WIDTH, HEIGHT), (255, 255, 255))
    img = download_image(image_url)
    if not img:
        print(f"[DEBUG] No image available for {image_url}, skipping slide")
        return None

    iw, ih = img.size
    scale = WIDTH / iw
    new_h = int(ih * scale)
    img = img.resize((WIDTH, new_h), Image.Resampling.LANCZOS)
    canvas.paste(img, (0, 0))
    print(f"[DEBUG] Main image pasted, resized to {WIDTH}x{new_h}")

    # Footer logo
    footer_y = min(new_h, HEIGHT)
    footer_h = HEIGHT - footer_y
    if footer_h > 5:
        try:
            logo = Image.open(BytesIO(logo_bytes)).convert("RGBA")
            lw, lh = logo.size
            scale = footer_h / lh
            logo = logo.resize((int(lw*scale), int(lh*scale)), Image.Resampling.LANCZOS)
            logo_x = (WIDTH - logo.width)//2
            canvas.paste(logo, (logo_x, footer_y), logo)
            print(f"[DEBUG] Logo pasted at {logo_x},{footer_y}, size {logo.width}x{logo.height}")
        except Exception as e:
            print(f"[DEBUG] Logo warning: {e}")

    return canvas

# ---------------- FETCH SLIDES ----------------
def fetch_slides():
    print("[DEBUG] Fetching slides...")
    slides = []
    for url in IMAGE_URLS:
        slide = prepare_slide(url)
        if slide:
            slides.append(slide)
            print(f"[DEBUG] Slide added for {url}")
        else:
            print(f"[DEBUG] Slide skipped for {url}")
    print(f"[DEBUG] Total slides fetched: {len(slides)}")
    return slides

# ---------------- CONNECTIVITY AND DEBOUNCE ----------------
offline_failures = 0
online_successes = 0
offline_mode = True
slide_index = 0
next_slide_time = time.monotonic()

def check_connectivity():
    global offline_failures, online_successes, offline_mode, slides, slide_index, next_slide_time

    connected = wifi_connected("wlan0")
    if connected:
        online_successes += 1
        offline_failures = 0
    else:
        offline_failures += 1
        online_successes = 0

    # Offline transition
    if offline_failures >= OFFLINE_THRESHOLD and not offline_mode:
        print("[DEBUG] Transition to OFFLINE mode")
        display.set_image(offline_slide)
        display.show()
        offline_mode = True

    # Online transition
    if online_successes >= ONLINE_THRESHOLD and offline_mode:
        print("[DEBUG] Transition to ONLINE mode")
        slides = fetch_slides()
        slide_index = 0
        next_slide_time = time.monotonic()
        offline_mode = False

    return not offline_mode

# ---------------- INITIAL DISPLAY ----------------
display.set_image(offline_slide)
display.show()
print("[DEBUG] Initial QR slide displayed")

# ---------------- MAIN LOOP ----------------
last_image_refresh_minute = None
last_slide_refresh_minute = None

while True:
    now_mono = time.monotonic()
    wall = datetime.datetime.now()

    # ---- Connectivity ----
    online = check_connectivity()
    if not online:
        print("[DEBUG] Currently offline, skipping slide updates")
        time.sleep(5)
        continue

    # ---- Image refresh at :12 ----
    if wall.minute % 5 == 0 and 10 <= wall.second <= 14 and last_image_refresh_minute != wall.minute:
        print("[DEBUG] Triggering image refresh (@:12)")
        slides = fetch_slides()
        slide_index %= max(len(slides), 1)
        last_image_refresh_minute = wall.minute

    # ---- Slide refresh at :30 ----
    if wall.minute % 5 == 0 and 28 <= wall.second <= 32 and last_slide_refresh_minute != wall.minute:
        print("[DEBUG] Triggering slide refresh (@:30)")
        slides = fetch_slides()
        slide_index = 0
        last_slide_refresh_minute = wall.minute

    # ---- Slide timing ----
    if slides and now_mono >= next_slide_time:
        display.set_image(slides[slide_index])
        display.show()
        print(f"[DEBUG] Displayed slide index {slide_index}")
        slide_index = (slide_index + 1) % len(slides)
        next_slide_time += SLIDE_SECONDS
        print(f"[DEBUG] Next slide scheduled at {next_slide_time:.2f} (monotonic)")

    time.sleep(0.1)
