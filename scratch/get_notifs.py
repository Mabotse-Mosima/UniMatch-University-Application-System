import requests, json

resp = requests.post("http://127.0.0.1:8000/api/auth/login", json={"email": "schooladmin@gov.com", "password": "Admin123!"})
cookies = resp.cookies

notifs = requests.get("http://127.0.0.1:8000/api/notifications", cookies=cookies).json()
print("NOTIFICATIONS IN DB:")
print(json.dumps(notifs, indent=2))
