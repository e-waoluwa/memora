import requests

url = "http://127.0.0.1:5000/watch/add"

data = {
    "item": "key",
    "location": "table"
}

response = requests.post(url, json=data)

print(response.json()); 
