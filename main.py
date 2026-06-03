from flask import send_from_directory, send_file
import os
import io
import base64
import shutil
from flask import Flask, render_template, request, jsonify, Response
import json
from datetime import datetime

# ── Directory Setup ───────────────────────────────────────────────────────────
os.makedirs("data",   exist_ok=True)
os.makedirs("static", exist_ok=True)
os.makedirs("temp",   exist_ok=True)

app = Flask(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
SETTINGS_FILE = "settings.json"

# current frame storage (in memory — for live feed from watch)
_current_frames = {}   # { watch_id: jpeg_bytes }

# ── Helpers ───────────────────────────────────────────────────────────────────
def get_watch_id():
    # Railway environment variable takes priority
    env_id = os.environ.get("WATCH_ID")
    if env_id:
        return env_id
    try:
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f).get("watch_id")
    except:
        return None

def watch_dir(watch_id):
    path = f"data/{watch_id}"
    os.makedirs(f"{path}/snapshots",         exist_ok=True)
    os.makedirs(f"{path}/registered_items",  exist_ok=True)
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
    return load_json(SETTINGS_FILE, {"wake_word": "memora"})

def save_settings(data):
    save_json(SETTINGS_FILE, data)

def format_time(saved_time):
    try:
        saved_dt = datetime.strptime(saved_time, "%Y-%m-%d %H:%M:%S")
        now      = datetime.now()
        seconds  = (now - saved_dt).total_seconds()
        if seconds < 60:        return "just now"
        elif seconds < 3600:    return f"{int(seconds//60)} minutes ago"
        elif seconds < 86400:   return f"{int(seconds//3600)} hours ago"
        elif seconds < 172800:  return "yesterday"
        else:                   return saved_dt.strftime("%d %b %Y, %H:%M")
    except:
        return saved_time

def is_local():
    return os.environ.get("RAILWAY_ENVIRONMENT") is None

# ── Camera (local only) ───────────────────────────────────────────────────────
camera         = None
camera_running = False
current_frame  = None

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
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' +
                   buffer.tobytes() + b'\r\n')
    except ImportError:
        pass

# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/")
def home():
    watch_id = get_watch_id()
    return render_template("index.html", watch_id=watch_id, is_local=is_local())

@app.route("/add", methods=["POST"])
def add():
    data     = request.json
    watch_id = data.get("watch_id") or get_watch_id()
    if not watch_id:
        return jsonify({"message": "No Watch ID"})
    wdir   = watch_dir(watch_id)
    memory = load_json(f"{wdir}/memory.json", [])
    memory.append({
        "item":     data["item"].lower(),
        "location": data["location"],
        "time":     datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    save_json(f"{wdir}/memory.json", memory)
    return jsonify({"message": "Saved successfully 👁️"})

@app.route("/find", methods=["POST"])
def find():
    data     = request.json
    search   = data["item"].lower()
    watch_id = data.get("watch_id") or get_watch_id()
    if not watch_id:
        return jsonify({"result": "No Watch ID configured", "snapshot": None})
    wdir   = watch_dir(watch_id)
    memory = load_json(f"{wdir}/memory.json", [])
    for log in reversed(memory):
        if search in log.get("item","") or log.get("item","") in search:
            snap     = log.get("snapshot")
            snap_url = f"/watch/{watch_id}/snapshots/{os.path.basename(snap)}" if snap else None
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
    return jsonify(load_json(f"{watch_dir(watch_id)}/memory.json", []))

# ── Local camera stream ───────────────────────────────────────────────────────
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
        try: camera.release()
        except: pass
        camera = None
    return jsonify({"message": "Camera stopped"})

@app.route("/capture-frame", methods=["POST"])
def capture_frame():
    global current_frame
    if not is_local():
        return jsonify({"status": "error", "message": "Use phone camera on cloud version"})
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

# ── Watch live frame (cloud) ──────────────────────────────────────────────────
@app.route("/api/<watch_id>/frame", methods=["POST"])
def receive_frame(watch_id):
    """brain.py pushes current frame here every second."""
    data      = request.get_json()
    img_b64   = data.get("frame")
    if img_b64:
        _current_frames[watch_id] = base64.b64decode(img_b64)
    return jsonify({"status": "ok"})

@app.route("/watch/<watch_id>/live")
def watch_live(watch_id):
    """Serves the latest frame from the watch as a JPEG."""
    frame = _current_frames.get(watch_id)
    if not frame:
        # return a placeholder
        placeholder = b'\xff\xd8\xff\xe0\x00\x10JFIF'
        return Response(placeholder, mimetype="image/jpeg")
    return Response(frame, mimetype="image/jpeg")

# ── Registration ──────────────────────────────────────────────────────────────
@app.route("/register-item")
def register_item():
    return render_template("register_item.html", is_local=is_local())

@app.route("/save-item", methods=["POST"])
def save_item():
    watch_id = get_watch_id()
    if not watch_id:
        return jsonify({"status": "error", "message": "No Watch ID"})

    name = request.form.get("name", "").strip() or \
           (request.get_json() or {}).get("name", "").strip()

    if not name:
        return jsonify({"status": "error", "message": "No name given"})

    wdir = watch_dir(watch_id)

    # handle phone camera upload (multipart form)
    if "photo" in request.files:
        file = request.files["photo"]
        dest = f"{wdir}/registered_items/{name}.jpg"
        file.save(dest)
    elif os.path.exists("temp/capture.jpg"):
        dest = f"{wdir}/registered_items/{name}.jpg"
        shutil.copy2("temp/capture.jpg", dest)
    else:
        return jsonify({"status": "error", "message": "No photo captured"})

    items       = load_json(f"{wdir}/items.json", {})
    items[name] = dest
    save_json(f"{wdir}/items.json", items)
    return jsonify({"status": "ok", "message": f"'{name}' registered ✅"})

# ── Gallery ───────────────────────────────────────────────────────────────────
@app.route("/gallery")
def gallery():
    watch_id = request.args.get("id") or get_watch_id()
    query    = request.args.get("q", "").lower()
    if not watch_id:
        return render_template("gallery.html", items=[], query=query, watch_id=None)
    wdir          = watch_dir(watch_id)
    memory        = load_json(f"{wdir}/memory.json", [])
    memory_lookup = {os.path.basename(l.get("snapshot","")): l
                     for l in memory if l.get("snapshot")}
    try:    all_images = os.listdir(f"{wdir}/snapshots")
    except: all_images = []
    if query:
        all_images = [i for i in all_images if query in i.lower()]
    all_images    = sorted(all_images, reverse=True)
    gallery_items = []
    for filename in all_images:
        log       = memory_lookup.get(filename, {})
        item_name = log.get("item", filename.split("_")[0].replace("-"," "))
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

@app.route("/memory/<watch_id>/<filename>")
def memory_detail(watch_id, filename):
    wdir   = watch_dir(watch_id)
    memory = load_json(f"{wdir}/memory.json", [])
    entry  = next(
        (l for l in reversed(memory)
         if l.get("snapshot") and os.path.basename(l["snapshot"]) == filename),
        {"item": filename.split("_")[0], "location": "", "time": ""}
    )
    return render_template("memory.html",
        image=filename, watch_id=watch_id,
        item=entry.get("item",""),
        location=entry.get("location",""),
        time=format_time(entry["time"]) if entry.get("time") else "")

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
    unique_locations = len(set(e.get("location","") for e in entries))
    map_points = [{"lat": e["lat"], "lng": e["lng"],
                   "location": e.get("location",""), "time": e.get("time","")}
                  for e in entries if e.get("lat") and e.get("lng")]
    return render_template("timeline.html",
        entries=entries, outdoor_count=outdoor_count,
        indoor_count=indoor_count, unique_locations=unique_locations,
        map_points=map_points, has_outdoor=len(map_points) > 0)

# ── Pair ──────────────────────────────────────────────────────────────────────
@app.route("/pair")
def pair():
    watch_id = get_watch_id()
    # generate QR code dynamically as base64 — no file needed
    qr_base64 = None
    if watch_id:
        try:
            import qrcode, io
            qr  = qrcode.QRCode(version=1,
                                 error_correction=qrcode.constants.ERROR_CORRECT_H,
                                 box_size=8, border=3)
            qr.add_data(watch_id)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            qr_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        except Exception as e:
            print(f"QR error: {e}")
    return render_template("pair.html",
                           watch_id=watch_id or "NOT SET",
                           qr_base64=qr_base64)

# ── Settings ──────────────────────────────────────────────────────────────────
@app.route("/settings")
def settings():
    s = load_settings()
    return render_template("settings.html", wake_word=s.get("wake_word", "memora"))

@app.route("/settings/wake-word", methods=["POST"])
def update_wake_word():
    data = request.get_json()
    word = data.get("wake_word","").strip().lower()
    if not word:
        return jsonify({"status": "error", "message": "No word given"})
    s = load_settings()
    s["wake_word"] = word
    save_settings(s)
    return jsonify({"status": "ok", "wake_word": word})

# ── PWA Manifest ─────────────────────────────────────────────────────────────
@app.route("/static/manifest.json")
def manifest():
    return send_from_directory("static", "manifest.json",
                               mimetype="application/manifest+json")

# ── Watch API — brain.py posts data here ─────────────────────────────────────
@app.route("/api/<watch_id>/memory", methods=["POST"])
def api_receive_memory(watch_id):
    data   = request.get_json()
    wdir   = watch_dir(watch_id)
    memory = load_json(f"{wdir}/memory.json", [])
    memory.append({
        "item":          data.get("item",""),
        "location":      data.get("location","camera view"),
        "location_type": data.get("location_type",""),
        "lat":           data.get("lat"),
        "lng":           data.get("lng"),
        "time":          data.get("time", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        "confidence":    data.get("confidence"),
        "snapshot":      data.get("snapshot"),
    })
    save_json(f"{wdir}/memory.json", memory)
    return jsonify({"status": "ok"})

@app.route("/api/<watch_id>/timeline", methods=["POST"])
def api_receive_timeline(watch_id):
    data     = request.get_json()
    wdir     = watch_dir(watch_id)
    timeline = load_json(f"{wdir}/timeline.json", [])
    entry    = {
        "time":          data.get("time", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        "location":      data.get("location",""),
        "location_type": data.get("location_type",""),
        "lat":           data.get("lat"),
        "lng":           data.get("lng"),
    }
    if timeline and timeline[-1]["location"] == entry["location"]:
        return jsonify({"status": "ok", "note": "duplicate skipped"})
    timeline.append(entry)
    save_json(f"{wdir}/timeline.json", timeline)
    return jsonify({"status": "ok"})

@app.route("/api/<watch_id>/snapshot", methods=["POST"])
def api_receive_snapshot(watch_id):
    data      = request.get_json()
    img_b64   = data.get("image")
    filename  = data.get("filename")
    if not img_b64 or not filename:
        return jsonify({"status": "error", "message": "Missing data"})
    wdir = watch_dir(watch_id)
    with open(f"{wdir}/snapshots/{filename}", "wb") as f:
        f.write(base64.b64decode(img_b64))
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)