import json
import re
import time
import cloudscraper
from bs4 import BeautifulSoup
from firestore_utils import FirestoreClient

firebaseConfig = {
    "projectId": "money-d9517",
    "apiKey": "AIzaSyA8TptV1xahItjFpexfqB1OtEZ71DtaogA"
}

def scrape_metadata():
    db = FirestoreClient(firebaseConfig["projectId"], firebaseConfig["apiKey"])
    scraper = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'android', 'desktop': False}
    )

    pending_novels = db.query_documents("novels", "status", "EQUAL", "discovered")

    if not pending_novels:
        print("[Metadata] No pending novels found.")
        return

    print(f"[Metadata] Found {len(pending_novels)} novels to process.")

    for novel in pending_novels:
        novel_id = novel["_id"]
        url = novel["url"]
        print(f"[Metadata] Processing: {novel_id} -> {url}")

        try:
            response = scraper.get(url, timeout=15)
            if response.status_code != 200:
                print(f"  [Error] Failed to fetch {url}: {response.status_code}")
                continue

            soup = BeautifulSoup(response.text, 'html.parser')

            schema_meta = {}
            ld_json_scripts = soup.find_all('script', type='application/ld+json')
            for script in ld_json_scripts:
                if script.string:
                    try:
                        data = json.loads(script.string)
                        if isinstance(data, list): data = data[0]
                        if data.get('@type') in ['ComicSeries', 'Article']:
                            schema_meta.update(data)
                    except: continue

            title = schema_meta.get('name') or schema_meta.get('headline') or "Unknown Title"
            genres = []
            genre_val = schema_meta.get('genre')
            if isinstance(genre_val, list): genres = genre_val
            elif isinstance(genre_val, str): genres = [g.strip() for g in genre_val.split(',') if g.strip()]

            description = schema_meta.get('description') or ""
            cover_url = ""
            if isinstance(schema_meta.get('image'), dict): cover_url = schema_meta['image'].get('url', '')
            elif isinstance(schema_meta.get('image'), str): cover_url = schema_meta['image']

            unique_chapters = {}
            for a in soup.find_all('a', href=True):
                href = a['href']
                if '/chapter/' in href or re.search(r'/chapter/\d+', href):
                    full_url = href if href.startswith('http') else f"https://asurascans.com{href}"
                    if full_url not in unique_chapters:
                        unique_chapters[full_url] = True

            for ch_url in unique_chapters.keys():
                match = re.search(r'chapter-(\d+)', ch_url)
                if not match:
                    match = re.search(r'/chapter/(\d+)', ch_url)
                ch_num = int(match.group(1)) if match else 0

                ch_data = {
                    "url": ch_url,
                    "chapter_number": ch_num,
                    "status": "pending",
                    "created_at": int(time.time())
                }
                db.save_document(f"novels/{novel_id}/chapters", f"chapter_{ch_num}", ch_data)

            novel_update = {
                "title": title,
                "genres": genres,
                "description": description,
                "cover_url": cover_url,
                "status": "metadata_scraped",
                "last_updated": int(time.time())
            }
            db.save_document("novels", novel_id, novel_update, merge=True)
            print(f"  [Success] Metadata and {len(unique_chapters)} chapters saved for {novel_id}")

            time.sleep(2)

        except Exception as e:
            print(f"  [Error] Failed processing {novel_id}: {e}")

if __name__ == "__main__":
    scrape_metadata()
