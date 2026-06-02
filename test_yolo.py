from ultralytics import YOLO

model = YOLO("yolov8n.pt")

results = model("https://ultralytics.com/images/bus.jpg")

print(results[0].boxes)
print("Detection done 👁️")