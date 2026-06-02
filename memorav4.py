import json
from datetime import datetime

FILE_NAME = "memora_data.json"

try:
    with open(FILE_NAME, "r") as f:
        memory_log = json.load(f)
except:
    memory_log = []

print("Memora v4 started... 👁️")

while True:
    print("\n1. Add item")
    print("2. Find item")
    print("3. Show all history")
    print("4. Exit")

    choice = input("Enter choice: ")

    if choice == "1":
        item = input("What item did you place? ").lower()
        location = input("Where did you place it? ")

        time_now = datetime.now().strftime("%H:%M:%S")

        memory_log.append({
            "item": item,
            "location": location,
            "time": time_now
        })

        with open(FILE_NAME, "w") as f:
            json.dump(memory_log, f, indent=4)

        print(f"✅ Saved: {item}")

    elif choice == "2":
        search_item = input("What are you looking for? ").lower()

        found = False

        for log in reversed(memory_log):
            if search_item in log["item"]:
                print(f"\n👁️ I last saw your {log['item']} on the {log['location']} at {log['time']}")
                found = True
                break

        if not found:
            print("❌ I couldn’t find that in your memory")

    elif choice == "3":
        for log in memory_log:
            print(f"{log['time']} → {log['item']} at {log['location']}")

    elif choice == "4":
        print("Memora shutting down 👁️")
        break

    else:
        print("Invalid choice")