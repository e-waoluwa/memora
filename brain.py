import os
import cv2
import json
import time
import base64
import requests as req
import numpy as np
from datetime import datetime
from ultralytics import YOLO
from location import get_location, infer_room

# ── Config ────────────────────────────────────────────────────────────────────
ITEMS_FILE        = "items.json"
MEMORY_FILE       = "memora_data.json"
TIMELINE_FILE     = "timeline.json"
SETTINGS_FILE     = "settings.json"
SNAPSHOTS_DIR     = "snapshots"
COOLDOWN_SECONDS  = 30
RELOAD_EVERY      = 5
CONFIDENCE_MIN    = 0.65
ORB_MATCH_MIN     = 6
FRAME_PUSH_INTERVAL = 1   # push frame every 1 second
last_frame_push     = 0

# ── Setup ─────────────────────────────────────────────────────────────────────
os.makedirs(SNAPSHOTS_DIR, exist_ok=True)
model = YOLO("yolov8n.pt")
orb   = cv2.ORB_create()
bf    = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)


# ── Settings ──────────────────────────────────────────────────────────────────
def load_settings():
    try:
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

settings = load_settings()
WATCH_ID  = settings.get("watch_id")
CLOUD_URL = settings.get("cloud_url")   # e.g. https://memora.railway.app

if WATCH_ID:
    print(f"    Watch ID: {WATCH_ID}")
else:
    print("    ⚠️  No Watch ID found — run setup.py first")

if CLOUD_URL:
    print(f"    Cloud URL: {CLOUD_URL}")
else:
    print("    ⚠️  No cloud URL — saving locally only")


# ── File Helpers ──────────────────────────────────────────────────────────────
def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=4)


# ── Cloud sync ────────────────────────────────────────────────────────────────
def sync_frame(frame):
    """Push current camera frame to cloud every second."""
    if not CLOUD_URL or not WATCH_ID:
        return
    try:
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
        img_b64   = base64.b64encode(buffer).decode("utf-8")
        req.post(
            f"{CLOUD_URL}/api/{WATCH_ID}/frame",
            json={"frame": img_b64},
            timeout=2
        )
    except Exception:
        pass

def sync_memory(entry, snap_path):
    """Send memory entry + snapshot to cloud in background."""
    if not CLOUD_URL or not WATCH_ID:
        return
    try:
        # send memory entry
        req.post(
            f"{CLOUD_URL}/api/{WATCH_ID}/memory",
            json=entry,
            timeout=5
        )
        # send snapshot as base64
        if snap_path and os.path.exists(snap_path):
            with open(snap_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("utf-8")
            req.post(
                f"{CLOUD_URL}/api/{WATCH_ID}/snapshot",
                json={
                    "image":    img_b64,
                    "filename": os.path.basename(snap_path)
                },
                timeout=10
            )
    except Exception as e:
        print(f"    ⚠️  Cloud sync failed: {e}")

def sync_timeline(entry):
    """Send timeline entry to cloud in background."""
    if not CLOUD_URL or not WATCH_ID:
        return
    try:
        req.post(
            f"{CLOUD_URL}/api/{WATCH_ID}/timeline",
            json=entry,
            timeout=5
        )
    except Exception as e:
        print(f"    ⚠️  Timeline sync failed: {e}")


# ── Label Matching ────────────────────────────────────────────────────────────
def find_label_match(yolo_label, registered_items):
    yolo_label = yolo_label.lower()
    for custom_name, img_path in registered_items.items():
        custom_lower = custom_name.lower()
        if yolo_label in custom_lower:
            return custom_name, img_path
        for word in custom_lower.split():
            if len(word) > 3 and word in yolo_label:
                return custom_name, img_path
    return None, None


# ── ORB Image Matching ────────────────────────────────────────────────────────
def is_my_item(frame, box, registered_img_path):
    x1, y1, x2, y2 = map(int, box.xyxy[0])
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return False
    ref = cv2.imread(registered_img_path)
    if ref is None:
        return True
    gray_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray_ref  = cv2.cvtColor(ref,  cv2.COLOR_BGR2GRAY)
    _, des1 = orb.detectAndCompute(gray_crop, None)
    _, des2 = orb.detectAndCompute(gray_ref,  None)
    if des1 is None or des2 is None:
        return True
    matches      = bf.match(des1, des2)
    good_matches = [m for m in matches if m.distance < 50]
    print(f"    ORB matches: {len(good_matches)} (need {ORB_MATCH_MIN})")
    return len(good_matches) >= ORB_MATCH_MIN


# ── Timeline Logger ───────────────────────────────────────────────────────────
def log_timeline(location_data, detected_labels):
    timeline = load_json(TIMELINE_FILE, [])
    now      = datetime.now()
    location = infer_room(detected_labels) if location_data["type"] == "inferred" \
               else location_data["location_str"]

    entry = {
        "time":          now.strftime("%Y-%m-%d %H:%M:%S"),
        "location":      location,
        "location_type": location_data["type"],
        "lat":           location_data.get("lat"),
        "lng":           location_data.get("lng"),
    }

    if timeline and timeline[-1]["location"] == location:
        return

    timeline.append(entry)
    save_json(TIMELINE_FILE, timeline)

    # sync to cloud in background thread
    import threading
    threading.Thread(target=sync_timeline, args=(entry,), daemon=True).start()

    print(f"📍 Timeline: {location} ({location_data['type']})")


# ── State ─────────────────────────────────────────────────────────────────────
registered_items  = load_json(ITEMS_FILE, {})
memory_log        = load_json(MEMORY_FILE, [])
last_saved        = {}
last_reload_time  = datetime.now()
last_timeline_log = time.time() - TIMELINE_INTERVAL
last_frame_push   = 0


# ── Camera ────────────────────────────────────────────────────────────────────
cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
if not cap.isOpened():
    print("❌ Could not open camera.")
    exit()

print("👁️  Memora Brain is running...")
print(f"    Registered items: {list(registered_items.keys()) or 'none yet'}")
print(f"    Confidence threshold: {int(CONFIDENCE_MIN*100)}%")
print("    Press Q to quit\n")


# ── Main Loop ─────────────────────────────────────────────────────────────────
while True:
    success, frame = cap.read()
    if not success:
        continue

    # reload items.json periodically
    if (datetime.now() - last_reload_time).total_seconds() >= RELOAD_EVERY:
        fresh = load_json(ITEMS_FILE, {})
        if fresh != registered_items:
            registered_items = fresh
            print(f"🔄 Items updated: {list(registered_items.keys())}")
        last_reload_time = datetime.now()

    results         = model(frame, verbose=False)
    names           = results[0].names
    now             = datetime.now()
    detected_labels = [names[int(b.cls[0])] for b in results[0].boxes]
    location_data   = get_location(detected_labels)

    # push live frame to cloud every second
    if time.time() - last_frame_push >= FRAME_PUSH_INTERVAL:
        import threading
        threading.Thread(target=sync_frame, args=(frame,), daemon=True).start()
        last_frame_push = time.time()

    # log timeline
    if time.time() - last_timeline_log >= TIMELINE_INTERVAL:
        log_timeline(location_data, detected_labels)
        last_timeline_log = time.time()

    for box in results[0].boxes:
        cls        = int(box.cls[0])
        yolo_label = names[cls]
        confidence = float(box.conf[0])

        if confidence < CONFIDENCE_MIN:
            continue

        matched, ref_path = find_label_match(yolo_label, registered_items)
        if not matched:
            continue

        if not is_my_item(frame, box, ref_path):
            continue

        if matched in last_saved:
            if (now - last_saved[matched]).total_seconds() < COOLDOWN_SECONDS:
                continue

        # save snapshot locally
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        safe_name = matched.replace(" ", "_")
        snap_path = f"{SNAPSHOTS_DIR}/{safe_name}_{timestamp}.jpg"
        cv2.imwrite(snap_path, frame)

        entry = {
            "item":          matched,
            "location":      location_data["location_str"],
            "location_type": location_data["type"],
            "lat":           location_data.get("lat"),
            "lng":           location_data.get("lng"),
            "time":          now.strftime("%Y-%m-%d %H:%M:%S"),
            "snapshot":      snap_path,
            "confidence":    round(confidence, 2),
        }

        memory_log.append(entry)
        save_json(MEMORY_FILE, memory_log)
        last_saved[matched] = now

        # sync to cloud in background thread
        import threading
        threading.Thread(
            target=sync_memory,
            args=(entry, snap_path),
            daemon=True
        ).start()

        # also log timeline
        log_timeline(location_data, detected_labels)
        last_timeline_log = time.time()

        print(f"👁️  Saved → '{matched}'  [{int(confidence*100)}%]")
        print(f"    Location: {location_data['location_str']}")
        print(f"    Snapshot: {snap_path}")

    # annotate frame
    annotated = results[0].plot()
    text      = "Watching for: " + ", ".join(registered_items.keys()) if registered_items \
                else "No items registered yet"
    watching  = text[:60] + "..." if len(text) > 60 else text
    loc_text  = f"📍 {location_data['location_str']}  [{location_data['type']}]"

    cv2.putText(annotated, watching, (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 100), 2)
    cv2.putText(annotated, loc_text, (10, 58),
                cv2.FONT_HERSHEY_SIMPLEX, 0.50, (100, 220, 255), 2)

    cv2.imshow("Memora Brain 👁️", annotated)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
print("👁️  Memora Brain stopped.")