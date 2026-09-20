import json, re, sys
from datetime import date
import requests
from bs4 import BeautifulSoup

USER = "Metecode"   # kendi kullanici adin
URL = f"https://github.com/users/{USER}/contributions"

r = requests.get(URL, headers={"User-Agent": "profile-art/1.0"}, timeout=30)
r.raise_for_status()
soup = BeautifulSoup(r.text, "html.parser")

# tooltip'leri topla: hucre id -> o gunun katki sayisi
tips = {}
for t in soup.select("tool-tip"):
    target = t.get("for")
    if not target:
        continue
    txt = t.get_text(" ", strip=True)
    m = re.search(r"(\d[\d,]*)\s+contribution", txt)
    tips[target] = int(m.group(1).replace(",", "")) if m else 0

days = []
for td in soup.select("td.ContributionCalendar-day"):
    d = td.get("data-date")
    if not d:
        continue
    days.append({
        "date": d,
        "count": tips.get(td.get("id"), 0),
        "level": int(td.get("data-level", 0)),
    })

if len(days) < 300:
    sys.exit(f"HATA: sadece {len(days)} gun bulundu, markup degismis olabilir")

days.sort(key=lambda x: x["date"])
total = sum(d["count"] for d in days)
best = max(days, key=lambda x: x["count"])

if total == 0 and any(d["level"] > 0 for d in days):
    print("UYARI: seviye verisi var ama sayilar 0 - tooltip yapisi degismis olabilir")

# en uzun seri
longest = cur = 0
for d in days:
    cur = cur + 1 if d["count"] > 0 else 0
    longest = max(longest, cur)

# guncel seri: sondan geriye, bugun bos ise bir onceki gunden say
current = 0
for i, d in enumerate(reversed(days)):
    if d["count"] > 0:
        current += 1
    elif i == 0:
        continue
    else:
        break

out = {
    "user": USER,
    "generated": date.today().isoformat(),
    "total": total,
    "current_streak": current,
    "longest_streak": longest,
    "best_day": best,
    "days": days,
}
with open("data/contributions.json", "w", encoding="utf-8") as f:
    json.dump(out, f, indent=1)

print(f"yazildi: data/contributions.json")
print(f"  {len(days)} gun | {total} katki | guncel seri {current}g | en uzun {longest}g")
print(f"  en iyi gun: {best['date']} ({best['count']})")