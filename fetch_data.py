import cloudscraper
import os
import json

BASE = "https://data-cdn.gaming.tools/paxdei/data/en"
VERSION = "1765296186223"

FILES_TO_FETCH = [
    "item.json",
    "recipe.json",
    "wearable.json",
    "consumable.json"
]

def ensure_data_folder():
    if not os.path.exists("data"):
        os.makedirs("data")
        print("[INFO] Created data/ folder")

def fetch_and_save(filename):
    url = f"{BASE}/{filename}?version={VERSION}"

    print(f"[FETCH] {url}")

    scraper = cloudscraper.create_scraper(
        browser={
            "browser": "chrome",
            "platform": "linux",
            "mobile": False
        }
    )

    try:
        r = scraper.get(url)
        r.raise_for_status()

        data = r.json()
        out_path = os.path.join("data", filename)

        with open(out_path, "w") as f:
            json.dump(data, f, indent=2)

        print(f"[OK] Saved → data/{filename}  ({len(data)} records)")

    except Exception as e:
        print(f"[ERROR] Failed to fetch {filename}: {e}")

def main():
    ensure_data_folder()
    for file in FILES_TO_FETCH:
        fetch_and_save(file)

if __name__ == "__main__":
    main()
