from flask import send_from_directory, send_file
import os
import shutil
from flask import Flask, render_template, request, jsonify, Response
import json
from datetime import datetime

# ── Directory Setup ───────────────────────────────────────────────────────────
os.makedirs("data",             exist_ok=True)
os.makedirs("static",           exist_ok=True)
os.makedirs("temp",             exist_ok=True)

app = Flask(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
SETTINGS_FILE = "settings.json"

# ── Helpers ───────────────────────────────────────────────────────────────────
def watch_dir(watch_id):
    """Each watch gets its own data folder."""
    path = f"data/{watch_id}"
    os.makedirs(path, exist_ok=True)
    os.makedirs(f"{path}/snapshots", exist_ok=True)
    return path

def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=4)

def load_settings():
    return load_json(SETTINGS_FILE, {"wake_word": "memora", "watch_id": None})

def save_settings(data):
    save_json(SETTINGS_FILE, data)

def format_time(saved_time):
    try:
        saved_dt = datetime.strptime(saved_time, "%Y-%m-%d %H:%M:%S")
        now      = datetime.now()
        seconds  = (now - saved_dt).total_seconds()
        if seconds < 60:
            return "just now"
        elif seconds < 3600:
            return f"{int(seconds // 60)} minutes ago"
        elif seconds < 86400:
            return f"{int(seconds // 3600)} hours ago"
        elif seconds < 172800:
            return "yesterday"
        else:
            return saved_dt.strftime("%d %b %Y, %H:%M")
    except:
        return saved_time

def get_watch_id():
    s = load_settings()
    return s.get("watch_id")

# ── Camera (local only — not available on cloud) ──────────────────────────────
camera        = None
camera_running= False
current_frame = None

def is_local():
    """True when running locally with a camera available."""
    return os.environ.get("RAILWAY_ENVIRONMENT") is None

def gen_frames():
    global current_frame, camera, camera_running
    try:
        import cv2
        if camera is None:
            camera = cv2.VideoCapture(0)
        camera_running = True
        while camera_running:
            success, frame = camera.read()
            if not success:
                break
            current_frame = frame.copy()
            _, buffer = cv2.imencode('.jpg', frame)
            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' +
                buffer.tobytes() +
                b'\r\n'
            )
    except ImportError:
        pass

# ── Main Routes ───────────────────────────────────────────────────────────────
@app.route("/")
def home():
    watch_id = get_watch_id()
    return render_template("index.html", watch_id=watch_id)

# ── Manual memory add ─────────────────────────────────────────────────────────
@app.route("/add", methods=["POST"])
def add():
    data     = request.json
    watch_id = data.get("watch_id") or get_watch_id()
    if not watch_id:
        return jsonify({"message": "No Watch ID — run setup.py first"})
    wdir     = watch_dir(watch_id)
    memory   = load_json(f"{wdir}/memory.json", [])
    memory.append({
        "item":     data["item"].lower(),
        "location": data["location"],
        "time":     datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    save_json(f"{wdir}/memory.json", memory)
    return jsonify({"message": "Saved successfully 👁️"})

# ── Find item ─────────────────────────────────────────────────────────────────
@app.route("/find", methods=["POST"])
def find():
    data     = request.json
    search   = data["item"].lower()
    watch_id = data.get("watch_id") or get_watch_id()
    if not watch_id:
        return jsonify({"result": "No Watch ID configured", "snapshot": None})
    wdir     = watch_dir(watch_id)
    memory   = load_json(f"{wdir}/memory.json", [])
    for log in reversed(memory):
        if search in log["item"] or log["item"] in search:
            snap         = log.get("snapshot", None)
            snap_url     = f"/watch/{watch_id}/snapshots/{os.path.basename(snap)}" if snap else None
            return jsonify({
                "result":   f"I last saw your {log['item']} at {log['location']} {format_time(log['time'])}",
                "snapshot": snap_url
            })
    return jsonify({"result": "I couldn't find that ❌", "snapshot": None})

@app.route("/all")
def all_data():
    watch_id = get_watch_id()
    if not watch_id:
        return jsonify([])
    memory = load_json(f"{watch_dir(watch_id)}/memory.json", [])
    return jsonify(memory)

# ── Camera Routes (local only) ────────────────────────────────────────────────
@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/video')
def video():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route("/stop-camera", methods=["POST"])
def stop_camera():
    global camera, camera_running
    camera_running = False
    if camera:
        try:
            camera.release()
        except:
            pass
        camera = None
    return jsonify({"message": "Camera stopped"})

@app.route("/capture-frame", methods=["POST"])
def capture_frame():
    global current_frame
    if not is_local():
        return jsonify({"status": "error", "message": "Camera not available on cloud"})
    if current_frame is None:
        return jsonify({"status": "error", "message": "No camera frame yet"})
    try:
        import cv2
        cv2.imwrite("temp/capture.jpg", current_frame)
        return jsonify({"status": "ok", "image": "/temp-preview"})
    except:
        return jsonify({"status": "error", "message": "Camera error"})

@app.route("/temp-preview")
def temp_preview():
    return send_file("temp/capture.jpg", mimetype="image/jpeg")

# ── Registration ──────────────────────────────────────────────────────────────
@app.route("/register-item")
def register_item():
    return render_template("register_item.html", is_local=is_local())

@app.route("/save-item", methods=["POST"])
def save_item():
    data     = request.get_json()
    name     = data.get("name", "").strip()
    watch_id = get_watch_id()
    if not name:
        return jsonify({"status": "error", "message": "No name given"})
    if not watch_id:
        return jsonify({"status": "error", "message": "No Watch ID — run setup.py first"})
    if not os.path.exists("temp/capture.jpg"):
        return jsonify({"status": "error", "message": "Snap the item first"})
    wdir = watch_dir(watch_id)
    os.makedirs(f"{wdir}/registered_items", exist_ok=True)
    dest  = f"{wdir}/registered_items/{name}.jpg"
    shutil.copy2("temp/capture.jpg", dest)
    items = load_json(f"{wdir}/items.json", {})
    items[name] = dest
    save_json(f"{wdir}/items.json", items)
    return jsonify({"status": "ok", "message": f"'{name}' registered ✅"})

# ── Gallery ───────────────────────────────────────────────────────────────────
@app.route("/gallery")
def gallery():
    watch_id = request.args.get("id") or get_watch_id()
    query    = request.args.get("q", "").lower()
    if not watch_id:
        return render_template("gallery.html", items=[], query=query)
    wdir         = watch_dir(watch_id)
    memory       = load_json(f"{wdir}/memory.json", [])
    memory_lookup = {}
    for log in memory:
        snap = log.get("snapshot", "")
        if snap:
            memory_lookup[os.path.basename(snap)] = log
    try:
        all_images = os.listdir(f"{wdir}/snapshots")
    except:
        all_images = []
    if query:
        all_images = [img for img in all_images if query in img.lower()]
    all_images    = sorted(all_images, reverse=True)
    gallery_items = []
    for filename in all_images:
        log       = memory_lookup.get(filename, {})
        item_name = log.get("item", filename.split("_")[0].replace("-", " "))
        raw_time  = log.get("time", "")
        gallery_items.append({
            "filename": filename,
            "item":     item_name,
            "time":     format_time(raw_time) if raw_time else "",
            "watch_id": watch_id,
        })
    return render_template("gallery.html", items=gallery_items, query=query, watch_id=watch_id)

@app.route("/watch/<watch_id>/snapshots/<filename>")
def get_snapshot(watch_id, filename):
    return send_from_directory(f"data/{watch_id}/snapshots", filename)

# ── Memory detail ─────────────────────────────────────────────────────────────
@app.route("/memory/<watch_id>/<filename>")
def memory_detail(watch_id, filename):
    wdir   = watch_dir(watch_id)
    memory = load_json(f"{wdir}/memory.json", [])
    entry  = next(
        (log for log in reversed(memory)
         if log.get("snapshot") and os.path.basename(log["snapshot"]) == filename),
        {"item": filename.split("_")[0], "location": "", "time": ""}
    )
    return render_template(
        "memory.html",
        image=filename,
        watch_id=watch_id,
        item=entry.get("item", ""),
        location=entry.get("location", ""),
        time=format_time(entry["time"]) if entry.get("time") else "",
    )

# ── Timeline ──────────────────────────────────────────────────────────────────
@app.route("/timeline")
def timeline():
    watch_id = request.args.get("id") or get_watch_id()
    if not watch_id:
        return render_template("timeline.html", entries=[], outdoor_count=0,
                               indoor_count=0, unique_locations=0,
                               map_points=[], has_outdoor=False)
    wdir    = watch_dir(watch_id)
    entries = list(reversed(load_json(f"{wdir}/timeline.json", [])))
    outdoor_count    = sum(1 for e in entries if e.get("location_type") == "outdoor")
    indoor_count     = sum(1 for e in entries if e.get("location_type") == "indoor")
    unique_locations = len(set(e.get("location", "") for e in entries))
    map_points = [
        {"lat": e["lat"], "lng": e["lng"],
         "location": e.get("location", ""), "time": e.get("time", "")}
        for e in entries if e.get("lat") and e.get("lng")
    ]
    return render_template(
        "timeline.html",
        entries=entries,
        outdoor_count=outdoor_count,
        indoor_count=indoor_count,
        unique_locations=unique_locations,
        map_points=map_points,
        has_outdoor=len(map_points) > 0,
    )

# ── Pair ──────────────────────────────────────────────────────────────────────
@app.route("/pair")
def pair():
    s        = load_settings()
    watch_id = s.get("watch_id", "NOT SET — run setup.py first")
    return render_template("pair.html", watch_id=watch_id)

# ── Settings ──────────────────────────────────────────────────────────────────
@app.route("/settings")
def settings():
    s = load_settings()
    return render_template("settings.html", wake_word=s.get("wake_word", "memora"))

@app.route("/settings/wake-word", methods=["POST"])
def update_wake_word():
    data = request.get_json()
    word = data.get("wake_word", "").strip().lower()
    if not word:
        return jsonify({"status": "error", "message": "No word given"})
    s = load_settings()
    s["wake_word"] = word
    save_settings(s)
    return jsonify({"status": "ok", "wake_word": word})

# ── Watch API — brain.py posts data here ─────────────────────────────────────
@app.route("/api/<watch_id>/memory", methods=["POST"])
def api_receive_memory(watch_id):
    """brain.py calls this to log a memory entry to the cloud."""
    data  = request.get_json()
    wdir  = watch_dir(watch_id)
    memory = load_json(f"{wdir}/memory.json", [])

    entry = {
        "item":          data.get("item", ""),
        "location":      data.get("location", "camera view"),
        "location_type": data.get("location_type", ""),
        "lat":           data.get("lat"),
        "lng":           data.get("lng"),
        "time":          data.get("time", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        "confidence":    data.get("confidence"),
        "snapshot":      data.get("snapshot"),
    }
    memory.append(entry)
    save_json(f"{wdir}/memory.json", memory)
    return jsonify({"status": "ok"})

@app.route("/api/<watch_id>/timeline", methods=["POST"])
def api_receive_timeline(watch_id):
    """brain.py calls this to log a timeline entry to the cloud."""
    data     = request.get_json()
    wdir     = watch_dir(watch_id)
    timeline = load_json(f"{wdir}/timeline.json", [])

    entry = {
        "time":          data.get("time", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        "location":      data.get("location", ""),
        "location_type": data.get("location_type", ""),
        "lat":           data.get("lat"),
        "lng":           data.get("lng"),
    }

    # don't log duplicate back-to-back
    if timeline and timeline[-1]["location"] == entry["location"]:
        return jsonify({"status": "ok", "note": "duplicate skipped"})

    timeline.append(entry)
    save_json(f"{wdir}/timeline.json", timeline)
    return jsonify({"status": "ok"})

@app.route("/api/<watch_id>/snapshot", methods=["POST"])
def api_receive_snapshot(watch_id):
    """brain.py sends snapshot image as base64."""
    import base64
    data     = request.get_json()
    image_b64 = data.get("image")
    filename  = data.get("filename")
    if not image_b64 or not filename:
        return jsonify({"status": "error", "message": "Missing image or filename"})
    wdir = watch_dir(watch_id)
    img_data = base64.b64decode(image_b64)
    with open(f"{wdir}/snapshots/{filename}", "wb") as f:
        f.write(img_data)
    return jsonify({"status": "ok", "filename": filename})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)