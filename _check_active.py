import requests

BASE = "https://web-production-5a17d.up.railway.app/api/v1"
r = requests.post(f"{BASE}/auth/login",
    json={"email": "ikramah.r.s001@pucit.edu.pk", "password": "pass123"}, timeout=15)
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}"}

r2 = requests.get(f"{BASE}/exams/active?page_size=100", headers=H, timeout=15)
items = r2.json().get("items", [])
print(f"Active exams: {len(items)}")
for e in items:
    print(f"  #{e['id']} '{e['title']}' sid={e.get('session_id')} status={e.get('session_status')}")

# Test re-submit on session 16 (already submitted)
r3 = requests.post(f"{BASE}/sessions/16/submit", headers=H, timeout=15)
print(f"\nRe-submit session 16: {r3.status_code} (expect 409)")
print(f"  {r3.text[:150]}")
