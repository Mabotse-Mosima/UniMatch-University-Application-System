import requests, json

resp = requests.post("http://127.0.0.1:8000/api/auth/login", json={"email": "schooladmin@gov.com", "password": "Admin123!"})
cookies = resp.cookies

progs = requests.get("http://127.0.0.1:8000/api/programmes", cookies=cookies).json()
unis = requests.get("http://127.0.0.1:8000/api/universities/catalog", cookies=cookies).json()
uni_map = {u['university_id']: u['name'] for u in unis}

print(f"Total programmes in DB: {len(progs)}")
for p in progs:
    uni_name = uni_map.get(p['university_id'], 'Unknown')
    print(f" - {p['name']} ({p['faculty']}) -> University: {uni_name}")
