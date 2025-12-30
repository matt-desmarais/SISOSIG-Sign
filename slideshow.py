import time
import requests
from io import BytesIO
from PIL import Image
from inky.auto import auto
import datetime

# ---------------- CONFIG ----------------
IMAGE_URLS = [
    "https://sisosig.info/temp/massdot.jpg",
    "https://sisosig.info/temp/massdot_graph.jpg"
]

LOGO_PATH = "sisosig.png"   # local file
SLIDE_SECONDS = 20  # seconds per slide
MAX_RETRIES = 3     # retry for main image
TIMEOUT = 10        # seconds per request

# ----------------------------------------
display = auto()
WIDTH, HEIGHT = display.resolution

# ---------------- PRELOAD LOGO ----------------
with open(LOGO_PATH, "rb") as f:
    logo_bytes = f.read()

# ---------------- DOWNLOAD IMAGE WITH RETRY ----------------
def download_image(url):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, timeout=TIMEOUT)
            response.raise_for_status()
            return Image.open(BytesIO(response.content)).convert("RGB")
        except Exception as e:
            print(f"Attempt {attempt} failed for {url}: {e}")
            time.sleep(1)  # small delay before retry
    print(f"Failed to download {url} after {MAX_RETRIES} attempts")
    return None

# ---------------- PREPARE SLIDE ----------------
def prepare_slide(image_url):
    canvas = Image.new("RGB", (WIDTH, HEIGHT), (255, 255, 255))

    # -------- MAIN IMAGE --------
    img = download_image(image_url)
    if img:
        iw, ih = img.size
        scale = WIDTH / iw
        new_h = int(ih * scale)
        img = img.resize((WIDTH, new_h), Image.Resampling.LANCZOS)
        canvas.paste(img, (0, 0))
    else:
        new_h = 0  # skip main image if download fails

    # -------- FOOTER LOGO --------
    footer_y = min(new_h, HEIGHT)
    footer_h = HEIGHT - footer_y
    if footer_h > 5:
        try:
            logo = Image.open(BytesIO(logo_bytes)).convert("RGBA")
            lw, lh = logo.size
            logo_scale = footer_h / lh
            logo_w = int(lw * logo_scale)
            logo_h = int(lh * logo_scale)
            logo = logo.resize((logo_w, logo_h), Image.Resampling.LANCZOS)

            # Center horizontally
            logo_x = (WIDTH - logo_w) // 2
            canvas.paste(logo, (logo_x, footer_y), logo)
        except Exception as e:
            print(f"Warning: Logo failed to load from memory: {e}")

    return canvas

# ---------------- FETCH SLIDES ----------------
def fetch_slides():
    return [prepare_slide(url) for url in IMAGE_URLS]

slides = fetch_slides()
slide_index = 0

# ---------------- MAIN LOOP ----------------
while True:
    display.set_image(slides[slide_index])
    display.show()
    slide_index = (slide_index + 1) % len(slides)

    time.sleep(SLIDE_SECONDS)
    slides = fetch_slides()
    # Refresh images every 5 minutes at :30s
#    now = datetime.datetime.now()
#    if now.minute % 5 == 0 and 25 <= now.second <= 35:
#        print("Refreshing images...")
#        slides = fetch_slides()
