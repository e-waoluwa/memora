import json
import time
import threading
import speech_recognition as sr
import pyttsx3
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
SETTINGS_FILE = "settings.json"
MEMORY_FILE   = "memora_data.json"
ITEMS_FILE    = "items.json"

# ── Load helpers ──────────────────────────────────────────────────────────────
def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default

def get_wake_word():
    settings = load_json(SETTINGS_FILE, {})
    return settings.get("wake_word", "memora").lower()

# ── Text to speech engine ─────────────────────────────────────────────────────
engine = pyttsx3.init()
engine.setProperty("rate", 165)    # speaking speed
engine.setProperty("volume", 1.0)

# pick a voice — prefer female if available
voices = engine.getProperty("voices")
for v in voices:
    if "female" in v.name.lower() or "zira" in v.name.lower():
        engine.setProperty("voice", v.id)
        break

def speak(text):
    print(f"🔊 Memora: {text}")
    engine.say(text)
    engine.runAndWait()

# ── Memory search ─────────────────────────────────────────────────────────────
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
            return saved_dt.strftime("%d %B")
    except:
        return saved_time

def search_memory(query):
    """Search memora_data.json for the item and return a spoken response."""
    memory_log = load_json(MEMORY_FILE, [])

    # clean up query — remove filler words
    stop_words = ["my", "the", "a", "an", "where", "is", "find", "i", "put", "left"]
    words      = [w for w in query.lower().split() if w not in stop_words]
    search     = " ".join(words).strip()

    if not search:
        return "I'm not sure what you're looking for. Try asking about a specific item."

    for log in reversed(memory_log):
        item = log.get("item", "").lower()
        if search in item or item in search:
            location  = log.get("location", "unknown location")
            time_str  = format_time(log.get("time", ""))
            # remove "my" from item name to avoid "your my phone"
            item_name = log["item"]
            item_name = item_name.replace("my ", "").replace("My ", "")
            return f"I last saw your {item_name} at {location}, {time_str}."

    return f"I couldn't find any memory of {search}. Make sure brain.py has seen it."

def list_registered():
    """Tell the user what items Memora is watching for."""
    items = load_json(ITEMS_FILE, {})
    if not items:
        return "You haven't registered any items yet. Use the app to register items."
    names = ", ".join(items.keys())
    return f"I'm currently watching for: {names}."

# ── Command parser ────────────────────────────────────────────────────────────
def handle_command(text):
    """Parse the voice command and return a response."""
    text = text.lower().strip()
    print(f"🎤 Command: {text}")

    # where is / find my
    if any(p in text for p in ["where is", "where's", "find my", "find"]):
        return search_memory(text)

    # what are you watching / what do you know
    if any(p in text for p in ["what are you watching", "what do you remember",
                                "what items", "what do you know", "list items"]):
        return list_registered()

    # time
    if "what time" in text or "what's the time" in text:
        now = datetime.now().strftime("%I:%M %p")
        return f"It's {now}."

    # hello / hi
    if text in ["hello", "hi", "hey", "how are you"]:
        return "I'm watching and remembering. How can I help?"

    # help
    if "help" in text:
        return ("You can ask me: where is my phone, "
                "what are you watching, or what time is it.")

    # fallback — try memory search anyway
    return search_memory(text)

# ── Recogniser ────────────────────────────────────────────────────────────────
recogniser = sr.Recognizer()
recogniser.energy_threshold         = 200
recogniser.dynamic_energy_threshold = True
recogniser.pause_threshold          = 0.6

def listen(timeout=5, phrase_limit=6):
    """
    Listen from the microphone and return recognised text.
    Returns None if nothing heard or recognition fails.
    """
    with sr.Microphone() as source:
        recogniser.adjust_for_ambient_noise(source, duration=0.3)
        try:
            audio = recogniser.listen(source, timeout=timeout,
                                      phrase_time_limit=phrase_limit)
            text  = recogniser.recognize_google(audio)
            return text.lower()
        except sr.WaitTimeoutError:
            return None
        except sr.UnknownValueError:
            return None
        except sr.RequestError:
            print("⚠️  Speech recognition service unavailable")
            return None

# ── Main loop ─────────────────────────────────────────────────────────────────
def run():
    wake_word = get_wake_word()
    print(f"\n👁️  Memora Voice Assistant started")
    print(f"    Wake word: 'Hey {wake_word.capitalize()}' or '{wake_word.capitalize()}'")
    print(f"    Listening...\n")

    speak(f"Memora voice assistant ready. Say hey {wake_word} to wake me.")

    while True:
        # ── Phase 1: listen for wake word ─────────────────────────────
        text = listen(timeout=10, phrase_limit=4)

        if text is None:
            continue

        # reload wake word in case it was changed in settings
        wake_word = get_wake_word()

        # show what was heard so we can debug
        print(f"👂 Heard: '{text}'")

        # reload wake word in case it was changed in settings
        wake_word = get_wake_word()

        # common misrecognitions Google makes for "memora"
        aliases = [wake_word, "moira", "memoria", "memory", "mirror", "aurora"]

        # also add the first 4 letters in case Google cuts it short
        if len(wake_word) > 4:
            aliases.append(wake_word[:4])

        if not any(alias in text for alias in aliases):
            print(f"    (not the wake word '{wake_word}' — still listening...)")
            continue

        # ── Wake word detected ────────────────────────────────────────
        print(f"\n✅ Wake word detected — listening for command...")
        speak("Yes?")

        # ── Phase 2: listen for the command ──────────────────────────
        command = listen(timeout=6, phrase_limit=15)

        if not command:
            speak("I didn't catch that. Try again.")
            continue

        # ── Phase 3: respond ──────────────────────────────────────────
        response = handle_command(command)
        speak(response)

        print()   # blank line between sessions
        time.sleep(0.5)

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    run()