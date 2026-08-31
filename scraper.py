#!/usr/bin/env python3
"""
جلب بيانات المسلسلات التركية المدبلجة مع روابط السيرفرات لكل حلقة
"""
import os
import json
import re
import time
import base64
import requests
from bs4 import BeautifulSoup
from urllib.parse import unquote
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ===== الإعدادات =====
CONFIG_FILE = "config.json"
if not os.path.exists(CONFIG_FILE):
    CONFIG = {
        "series_page": "https://lodynet.watch/dubbed-turkish-series-g/",
        "max_series": 50,
        "max_new_episodes_per_series": 5
    }
else:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        CONFIG = json.load(f)

SERIES_PAGE = CONFIG.get("series_page", "https://lodynet.watch/dubbed-turkish-series-g/")
MAX_SERIES = CONFIG.get("max_series", 50)
MAX_NEW_EPISODES = CONFIG.get("max_new_episodes_per_series", 5)

# ===== إعداد Selenium =====
def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0')
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver
    except Exception as e:
        print(f"❌ فشل إعداد Selenium: {e}")
        return None

# ===== جلب المسلسلات مع الصور =====
def get_all_series(url):
    print(f"🔍 جلب المسلسلات من: {url}")
    driver = setup_driver()
    if not driver:
        return []
    series_list = []
    try:
        driver.get(url)
        wait = WebDriverWait(driver, 15)
        items = wait.until(EC.presence_of_all_elements_located((By.CLASS_NAME, "ItemNewly")))
        print(f"✅ تم العثور على {len(items)} عنصر مسلسل")
        for item in items:
            try:
                link = item.find_element(By.TAG_NAME, "a")
                href = link.get_attribute("href")
                title = link.get_attribute("title") or link.text.strip()
                cover_div = item.find_element(By.CLASS_NAME, "NewlyCover")
                style = cover_div.get_attribute("style")
                img_match = re.search(r'url\(["\']?(.*?)["\']?\)', style)
                cover_url = img_match.group(1) if img_match else ""
                if href and title and '/category/' in href:
                    series_list.append({
                        'name': title.strip(),
                        'url': href,
                        'cover': cover_url
                    })
            except Exception as e:
                print(f"⚠️ خطأ في عنصر: {e}")
                continue
    except Exception as e:
        print(f"❌ فشل تحميل الصفحة: {e}")
        return []
    finally:
        driver.quit()
    seen = set()
    unique = []
    for s in series_list:
        if s['url'] not in seen:
            seen.add(s['url'])
            unique.append(s)
    print(f"✅ تم العثور على {len(unique)} مسلسل")
    return unique[:MAX_SERIES]

# ===== جلب أرقام الحلقات =====
def get_episode_numbers(series_url):
    print(f"  📂 جلب حلقات من: {series_url[:60]}...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = requests.get(series_url, headers=headers, timeout=30)
        resp.encoding = 'utf-8'
    except Exception as e:
        print(f"    ❌ فشل تحميل الصفحة: {e}")
        return []
    soup = BeautifulSoup(resp.text, 'html.parser')
    episodes = []
    text = soup.get_text()
    pattern = r'(?:حلقة\s*رقم\s*|الحلقة\s*)(\d+)'
    matches = re.findall(pattern, text)
    for match in matches:
        ep_num = int(match)
        if ep_num not in episodes:
            episodes.append(ep_num)
    for link in soup.find_all('a', href=True):
        href = link['href']
        if '-الحلقة-' in href:
            match = re.search(r'-(\d+)/?$', href)
            if match:
                ep_num = int(match.group(1))
                if ep_num not in episodes:
                    episodes.append(ep_num)
    episodes.sort()
    print(f"    ✅ تم العثور على {len(episodes)} حلقة")
    return episodes

# ===== استخراج PostData =====
def extract_post_data(html):
    start_match = re.search(r'PostData\s*=\s*\{', html)
    if not start_match:
        return None
    start_index = start_match.start()
    brace_count = 0
    end_index = start_index
    in_string = False
    escape = False
    for i in range(start_index, len(html)):
        char = html[i]
        if escape:
            escape = False
            continue
        if char == '\\' and in_string:
            escape = True
            continue
        if char == '"' and not escape:
            in_string = not in_string
            continue
        if not in_string:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_index = i + 1
                    break
    if brace_count != 0:
        return None
    post_data_str = html[start_index:end_index].replace('PostData = ', '').strip()
    if post_data_str.endswith(';'):
        post_data_str = post_data_str[:-1]
    try:
        import json5
        return json5.loads(post_data_str)
    except:
        try:
            return json.loads(post_data_str)
        except:
            return None

def decode_embed(embed_str):
    if not embed_str:
        return None
    try:
        decoded = base64.b64decode(embed_str).decode('utf-8')
        if decoded.startswith('http'):
            return decoded
    except:
        pass
    return embed_str

def extract_server_urls(post_data):
    servers = post_data.get('ServersWatch', [])
    urls = []
    for server in servers:
        embed = server.get('Embed')
        if embed:
            decoded = decode_embed(embed)
            if decoded:
                urls.append(decoded)
    return urls

def get_episode_servers(episode_url):
    print(f"    🔗 جلب سيرفرات: {episode_url[:60]}...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = requests.get(episode_url, headers=headers, timeout=30)
        resp.encoding = 'utf-8'
    except Exception as e:
        print(f"    ❌ فشل تحميل صفحة الحلقة: {e}")
        return []
    post_data = extract_post_data(resp.text)
    if not post_data:
        return []
    return extract_server_urls(post_data)

def build_episode_data(series_name, series_url, episode_numbers, max_new=5):
    episodes = []
    series_slug = series_url.rstrip('/').split('/')[-1]
    if series_slug.startswith('category-'):
        series_slug = series_slug[9:]
    if series_slug.endswith('-مدب'):
        series_slug = series_slug[:-4]
    if series_slug.startswith('مسلسل-'):
        series_slug = series_slug[7:]

    count = 0
    for ep_num in episode_numbers:
        episode_url = f"https://lodynet.watch/{series_slug}-الحلقة-{ep_num}/"
        servers = []
        if count < max_new:
            servers = get_episode_servers(episode_url)
            time.sleep(1)
            count += 1
        episodes.append({
            'episode': ep_num,
            'url': episode_url,
            'servers': servers,
            'date_added': datetime.now().isoformat()
        })
    return episodes

def main():
    print("🚀 بدء جلب الميتاداتا مع سيرفرات الحلقات...")
    os.makedirs("data", exist_ok=True)

    metadata_path = "data/metadata.json"
    if os.path.exists(metadata_path):
        with open(metadata_path, "r", encoding="utf-8") as f:
            all_data = json.load(f)
    else:
        all_data = {"series": {}, "last_update": None}

    series_list = get_all_series(SERIES_PAGE)
    if not series_list:
        print("⚠️ لم يتم العثور على أي مسلسل.")
        return

    updated_count = 0
    for series in series_list:
        name = series['name']
        url = series['url']
        cover = series.get('cover', '')

        if name in all_data["series"]:
            existing_episodes = {e['episode']: e for e in all_data["series"][name].get('episodes', [])}
        else:
            existing_episodes = {}
            all_data["series"][name] = {"episodes": [], "cover": cover}

        all_data["series"][name]["cover"] = cover
        episode_numbers = get_episode_numbers(url)

        new_eps = [ep for ep in episode_numbers if ep not in existing_episodes]
        if new_eps:
            new_eps_limited = new_eps[:MAX_NEW_EPISODES]
            print(f"  🆕 إضافة {len(new_eps_limited)} حلقة جديدة (من أصل {len(new_eps)}) لـ {name}")
            new_ep_data = build_episode_data(name, url, new_eps_limited, max_new=len(new_eps_limited))
            all_data["series"][name]["episodes"].extend(new_ep_data)
            updated_count += len(new_ep_data)

        all_data["series"][name]["url"] = url
        time.sleep(2)

    all_data["last_update"] = datetime.now().isoformat()
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

    print(f"✅ تم تحديث {updated_count} حلقة جديدة مع سيرفراتها")
    print(f"📂 إجمالي المسلسلات: {len(all_data['series'])}")

if __name__ == "__main__":
    main()
