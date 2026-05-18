import requests

BASE = "https://web-production-5a17d.up.railway.app/api/v1"
r = requests.post(f"{BASE}/auth/login",
    json={"email": "baha.udeen.a.t1@pucit.edu.pk", "password": "pass123"}, timeout=15)
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}"}

# Session 14 was from "Midterm: Processes & Scheduling" (exam 140)
# Session 15 was from "Midterm: Requirements & Design" (exam 142)
for sid in [14, 15]:
    r2 = requests.get(f"{BASE}/teacher/sessions/{sid}/detail", headers=H, timeout=15)
    print(f"Session {sid}: status={r2.status_code}")
    if r2.status_code == 200:
        d = r2.json()
        incs = d.get("incidents", [])
        print(f"  Incidents: {len(incs)}")
        for i in incs:
            print(f"    {i['type']} / {i['severity']} - {i.get('description','')}")
    else:
        print(f"  {r2.text[:100]}")
