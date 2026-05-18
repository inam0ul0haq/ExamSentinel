import requests

BASE = "https://web-production-5a17d.up.railway.app/api/v1"
r = requests.post(f"{BASE}/auth/login",
    json={"email": "baha.udeen.a.t1@pucit.edu.pk", "password": "pass123"}, timeout=15)
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

r2 = requests.post(f"{BASE}/exams/153/activate", headers=H, timeout=15)
print(f"Activate: {r2.status_code}")
print(r2.text[:200])
