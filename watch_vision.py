import os
from ultralytics import YOLO
import cv2
import json
from datetime import datetime

model = YOLO("yolov8n.pt")

os.makedirs("snapshots", exist_ok=True)

cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

FILE_NAME = "memora_data.json"

ITEM_FILE = "items.json"

try:
    with open(ITEM_FILE, "r") as f:
        registered_items = json.load(f)
except:
    registered_items = {}
    
try:
    with open(FILE_NAME, "r") as f:
        memory_log = json.load(f)
except:
    memory_log = []

last_saved = {}

while True:

    success, frame = cap.read()

    if not success:
        break

    results = model(frame)

    names = results[0].names

    for box in results[0].boxes:

        cls = int(box.cls[0])

        detected_object = names[cls]

        current_time = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        if detected_object not in last_saved:

            timestamp = datetime.now().strftime(
                "%Y%m%d_%H%M%S"
            )

            filename = (
                f"snapshots/"
                f"{detected_object}_{timestamp}.jpg"
            )

            cv2.imwrite(
                filename,
                frame
            )

            memory = {
                "item": detected_object,
                "location": "camera view",
                "time": current_time
            }

            memory_log.append(memory)

            with open(
                FILE_NAME,
                "w"
            ) as f:

                json.dump(
                    memory_log,
                    f,
                    indent=4
                )

            last_saved[
                detected_object
            ] = datetime.now()

            print(
                f"👁️ Saved: {detected_object}"
            )

    annotated_frame = results[0].plot()

    cv2.imshow(
        "Memora Watch Vision 👁️",
        annotated_frame
    )

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()