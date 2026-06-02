import time
import threading
import requests

# ── Config ────────────────────────────────────────────────────────────────────
CACHE_SECONDS = 60
API_TIMEOUT   = 4

# ── Room inference map ────────────────────────────────────────────────────────
ROOM_CLUES = {
    "kitchen":     ["refrigerator", "microwave", "oven", "sink", "toaster", "knife", "fork", "spoon"],
    "bedroom":     ["bed", "pillow", "clock", "wardrobe"],
    "living room": ["couch", "sofa", "tv", "remote"],
    "dining room": ["dining table", "wine glass", "cup", "bowl"],
    "bathroom":    ["toilet", "bathtub", "toothbrush", "hair drier"],
    "office":      ["laptop", "keyboard", "mouse", "chair", "book"],
}

ALL_INDOOR_CLUES = set(clue for clues in ROOM_CLUES.values() for clue in clues)

# ── Cache — shared between main thread and background thread ──────────────────
_cache = {
    "location_str": "locating...",
    "lat":          None,
    "lng":          None,
    "type":         "unknown",
    "last_fetched": 0,
    "fetching":     False,   # True while background fetch is running
}
_cache_lock = threading.Lock()


# ── Indoor detection ──────────────────────────────────────────────────────────
def is_indoors(detected_labels):
    detected_lower = set(label.lower() for label in detected_labels)
    return bool(detected_lower & ALL_INDOOR_CLUES)


# ── Room inference ────────────────────────────────────────────────────────────
def infer_room(detected_labels):
    detected_lower = [label.lower() for label in detected_labels]
    scores = {}
    for room, clues in ROOM_CLUES.items():
        score = sum(1 for clue in clues if clue in detected_lower)
        if score > 0:
            scores[room] = score
    return max(scores, key=scores.get) if scores else "indoor space"


# ── Network calls (run in background thread) ──────────────────────────────────
def _get_coords_from_ip():
    try:
        r    = requests.get("http://ip-api.com/json/", timeout=API_TIMEOUT)
        data = r.json()
        if data.get("status") == "success":
            return data["lat"], data["lon"]
    except Exception:
        pass
    return None, None


def _reverse_geocode(lat, lng):
    try:
        url     = "https://nominatim.openstreetmap.org/reverse"
        params  = {"lat": lat, "lon": lng, "format": "json"}
        headers = {"User-Agent": "Memora/1.0"}
        r       = requests.get(url, params=params, headers=headers, timeout=API_TIMEOUT)
        data    = r.json()
        address = data.get("address", {})
        parts   = []
        for key in ["road", "suburb", "neighbourhood", "city_district", "city", "town"]:
            val = address.get(key)
            if val:
                parts.append(val)
            if len(parts) == 2:
                break
        return ", ".join(parts) if parts else "unknown location"
    except Exception:
        return "unknown location"


def _fetch_outdoor_location():
    """Runs in background thread — fetches IP location and updates cache."""
    lat, lng = _get_coords_from_ip()
    if lat and lng:
        location_str  = _reverse_geocode(lat, lng)
        location_type = "outdoor"
    else:
        location_str  = "unknown location"
        location_type = "unknown"
        lat = lng = None

    with _cache_lock:
        _cache["location_str"] = location_str
        _cache["type"]         = location_type
        _cache["lat"]          = lat
        _cache["lng"]          = lng
        _cache["last_fetched"] = time.time()
        _cache["fetching"]     = False


# ── Main location getter ──────────────────────────────────────────────────────
def get_location(detected_labels=None):
    """
    Called every frame from brain.py — NEVER blocks.

    - If YOLO sees indoor objects → return room instantly (no network)
    - Otherwise → return cached outdoor location instantly,
                  trigger background refresh if cache is stale
    """
    labels = detected_labels or []

    # indoor check is instant — no network needed
    if is_indoors(labels):
        room = infer_room(labels)
        return {
            "location_str": room,
            "type":         "indoor",
            "lat":          None,
            "lng":          None,
        }

    # outdoor — return cache immediately, refresh in background if stale
    with _cache_lock:
        cached_str      = _cache["location_str"]
        cached_type     = _cache["type"]
        cached_lat      = _cache["lat"]
        cached_lng      = _cache["lng"]
        last_fetched    = _cache["last_fetched"]
        already_fetching = _cache["fetching"]

    cache_stale = (time.time() - last_fetched) >= CACHE_SECONDS

    if cache_stale and not already_fetching:
        with _cache_lock:
            _cache["fetching"] = True
        t = threading.Thread(target=_fetch_outdoor_location, daemon=True)
        t.start()

    return {
        "location_str": cached_str,
        "type":         cached_type,
        "lat":          cached_lat,
        "lng":          cached_lng,
    }