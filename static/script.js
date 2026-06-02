async function addItem() {
    const item     = document.getElementById("item").value.trim();
    const location = document.getElementById("location").value.trim();

    if (!item || !location) return;

    const response = await fetch("/add", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ item, location })
    });

    const data = await response.json();
    const box  = document.getElementById("add-result");
    box.textContent = data.message;
    box.classList.add("visible");
}

async function findItem() {
    const item = document.getElementById("search").value.trim();
    if (!item) return;

    const response = await fetch("/find", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ item })
    });

    const data   = await response.json();
    const result = document.getElementById("result");
    const img    = document.getElementById("snapshot-result");

    result.textContent = data.result;
    result.classList.add("visible");

    if (data.snapshot) {
        img.src = data.snapshot + "?t=" + Date.now();
        img.classList.add("visible");
    } else {
        img.classList.remove("visible");
    }
}

// allow pressing Enter to search
document.addEventListener("DOMContentLoaded", () => {
    const searchInput = document.getElementById("search");
    if (searchInput) {
        searchInput.addEventListener("keydown", e => {
            if (e.key === "Enter") findItem();
        });
    }

    const itemInput = document.getElementById("item");
    if (itemInput) {
        itemInput.addEventListener("keydown", e => {
            if (e.key === "Enter") document.getElementById("location").focus();
        });
    }

    const locationInput = document.getElementById("location");
    if (locationInput) {
        locationInput.addEventListener("keydown", e => {
            if (e.key === "Enter") addItem();
        });
    }
});

function startVoice() {
    const btn = document.getElementById("voice-btn");

    if (!('webkitSpeechRecognition' in window)) {
        alert("Voice not supported in this browser.");
        return;
    }

    const recognition          = new webkitSpeechRecognition();
    recognition.lang           = "en-US";
    recognition.continuous     = false;
    recognition.interimResults = false;

    btn.classList.add("listening");
    btn.textContent = "🎤  Listening...";
    recognition.start();

    recognition.onresult = function(event) {
        const speech = event.results[0][0].transcript.toLowerCase();
        btn.classList.remove("listening");
        btn.textContent = "🎤  Speak";

        // "where is my phone" → search
        if (speech.includes("where is") || speech.includes("find my")) {
            const search = speech.replace("where is", "").replace("find my", "").replace("my", "").trim();
            document.getElementById("search").value = search;
            findItem();
            return;
        }

        // "key at table" or "bag on the desk" → add
        let item = "", location = "";

        if (speech.includes(" at ")) {
            [item, location] = speech.split(" at ").map(s => s.trim());
        } else if (speech.includes(" on the ")) {
            const parts = speech.split(" on the ");
            item     = parts[0].replace("is", "").trim();
            location = parts[1].trim();
        } else {
            document.getElementById("search").value = speech;
            findItem();
            return;
        }

        document.getElementById("item").value     = item;
        document.getElementById("location").value = location;
        addItem();
    };

    recognition.onerror = function() {
        btn.classList.remove("listening");
        btn.textContent = "🎤  Speak";
    };
}