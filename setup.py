"""
Run this ONCE when setting up your Memora watch.
It generates a unique Watch ID and saves it to settings.json,
then creates a QR code image for pairing with the phone app.
"""

import json
import os
import random
import string
import qrcode

SETTINGS_FILE = "settings.json"
QR_FILE       = "static/watchid_qr.png"

# ── Load existing settings ────────────────────────────────────────────────────
try:
    with open(SETTINGS_FILE, "r") as f:
        settings = json.load(f)
except:
    settings = {}

# ── Only generate if no Watch ID exists yet ───────────────────────────────────
if "watch_id" in settings:
    watch_id = settings["watch_id"]
    print(f"✅ Watch ID already exists: {watch_id}")
    print("   Delete it from settings.json and re-run to generate a new one.")
else:
    # generate unique ID — 3 letters + 4 numbers e.g. EWA-4829
    letters = "".join(random.choices(string.ascii_uppercase, k=3))
    numbers = "".join(random.choices(string.digits, k=4))
    watch_id = f"{letters}-{numbers}"

    settings["watch_id"] = watch_id
    settings.setdefault("wake_word", "memora")

    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=4)

    print(f"🎉 Watch ID generated: {watch_id}")
    print(f"   Saved to {SETTINGS_FILE}")

# ── Generate QR code ──────────────────────────────────────────────────────────
os.makedirs("static", exist_ok=True)

qr = qrcode.QRCode(
    version=1,
    error_correction=qrcode.constants.ERROR_CORRECT_H,
    box_size=10,
    border=4,
)
qr.add_data(watch_id)
qr.make(fit=True)

img = qr.make_image(fill_color="black", back_color="white")
img.save(QR_FILE)

print(f"📱 QR code saved to {QR_FILE}")
print(f"\n   Share your Watch ID or QR code with your phone to pair.")
print(f"   Watch ID: {watch_id}")