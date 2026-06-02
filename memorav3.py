import json
from datetime import datetime

FILE_NAME = "memora_data.json"

# Load existing memory
try:
    with open(FILE_NAME, "r") as f:
        memory_log = json.load(f)
except:
    memory_log = []

print("Memora v3 started... 👁️")

while True:
    print("\nWhat do you want to do?")
    print("1. Add item")
    print("2. Find item")
    print("3. Show all history")
    print("4. Exit")

    choice = input("Enter choice: ")

    # ADD ITEM
    if choice == "1":
        item = input("What item did you place? ")
        location = input("Where did you place it? ")

        time_now = datetime.now().strftime("%H:%M:%S")

        log = {
            "item": item.lower(),
            "location": location,
            "time": time_now
        }

        memory_log.append(log)

        # SAVE TO FILE
        with open(FILE_NAME, "w") as f:
            json.dump(memory_log, f, indent=4)

        print(f"✅ Saved permanently: {item}")

    # FIND ITEM
    elif choice == "2":
        search_item = input("What are you looking for? ").lower()

        found = False

        for log in reversed(memory_log):
            if log["item"] == search_item:
                print(f"👁️ Last seen: {log['item']} at {log['location']} around {log['time']}")
                found = True
                break

        if not found:
            print("❌ Item not found")

    # SHOW ALL
    elif choice == "3":
        if not memory_log:
            print("No memory stored yet")
        else:
            print("\n📜 Memory History:")
            for log in memory_log:
                print(f"{log['time']} → {log['item']} at {log['location']}")

    # EXIT
    elif choice == "4":
        print("Memora shutting down 👁️")
        break

    else:
        print("Invalid choice")