#!/usr/bin/env python3
"""
جلب المسلسلات التركية المدبلجة، تحميل الحلقات الجديدة، ضغطها إلى 240p،
وتخزينها في GitHub Releases مع تحديث metadata.json
"""
import os
import sys
import json
import re
import time
import requests
import subprocess
import base64
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
from github import Github

# ===== قراءة الإعدادات =====
CONFIG_FILE = "config.json"
if not os.path.exists(CONFIG_FILE):
    print("❌ config.json غير موجود، سيتم استخدام الإعدادات الافتراضية")
    CONFIG = {
        "series_page": "https://lodynet.watch/dubbed-turkish-series-g/",
        "max_series": 10,
        "max_episodes_per_run": 2
    }
else:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        CONFIG = json.load(f)

SERIES_PAGE = CONFIG.get("series_page", "https://lodynet.watch/dubbed-turkish-series-g/")
MAX_SERIES = CONFIG.get("max_series", 10)
MAX_EPISODES_PER_RUN = CONFIG.get("max_episodes_per_run", 2)

# ===== إعداد GitHub =====
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    print("❌ GITHUB_TOKEN غير موجود في البيئة")
    sys.exit(1)

REPO_NAME = os.environ.get("GITHUB_REPOSITORY")
if not REPO_NAME:
    print("❌ GITHUB_REPOSITORY غير موجود")
    sys.exit(1)

g = Github(GITHUB_TOKEN)
repo = g.get_repo(REPO_NAME)
RELEASE_TAG = "compressed-episodes"

# ===== إعداد متصفح Selenium =====
def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver
    except Exception as e:
        print(f"❌ فشل إعداد Selenium: {e}")
        return None

# ===== جلب جميع المسلسلات باستخدام Selenium =====
def get_all_series(url):
    print(f"🔍 جلب المسلسلات من: {url}")
    driver = setup_driver()
    if not driver:
        return get_series_from_requests(url)
    series_list = []
    try:
        driver.get(url)
        wait = WebDriverWait(driver, 15)
        items = wait.until(EC.presence_of_all_elements_located((By.CLASS_NAME, "ItemNewly")))
        for item in items:
            try:
                link = item.find_element(By.TAG_NAME, "a")
                href = link.get_attribute("href")
                title = link.get_attribute("title") or link.text.strip()
                if href and title and '/category/' in href:
                    # استخراج رابط الصورة
                    cover_div = item.find_element(By.CLASS_NAME, "NewlyCover")
                    style = cover_div.get_attribute("style")
                    cover_url = None
                    if style:
                        match = re.search(r'url\("?([^")]+)"?\)', style)
                        if match:
                            cover_url = match.group(1)
                    series_list.append({
                        'name': title.strip(),
                        'url': href,
                        'cover': cover_url
                    })
            except Exception as e:
                print(f"⚠️ خطأ في معالجة عنصر: {e}")
    except Exception as e:
        print(f"❌ فشل تحميل الصفحة: {e}")
        return get_series_from_requests(url)
    finally:
        driver.quit()
    # إزالة التكرارات
    seen = set()
    unique = []
    for s in series_list:
        if s['url'] not in seen:
            seen.add(s['url'])
            unique.append(s)
    print(f"✅ تم العثور على {len(unique)} مسلسل")
    return unique[:MAX_SERIES]

def get_series_from_requests(url):
    print("📡 محاولة الجلب باستخدام requests...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.encoding = 'utf-8'
    except:
        return []
    soup = BeautifulSoup(resp.text, 'html.parser')
    series_list = []
    for link in soup.find_all('a', href=True):
        href = link['href']
        if '/category/' in href and 'page/' not in href:
            title = link.get('title') or link.text.strip()
            if title and any(k in title for k in ['مدبلج', 'مدبلجة', 'مسلسل']):
                if href.startswith('/'):
                    href = 'https://lodynet.watch' + href
                series_list.append({'name': title.strip(), 'url': href})
    return series_list

# ===== جلب حلقات مسلسل معين =====
def get_episodes_for_series(series_url):
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
        if '-مد-' in href or '-حلقة-' in href:
            match = re.search(r'-(\d+)/?$', href)
            if match:
                ep_num = int(match.group(1))
                if ep_num not in episodes:
                    episodes.append(ep_num)
    episodes.sort()
    print(f"    ✅ تم العثور على {len(episodes)} حلقة")
    return episodes

# ===== استخراج روابط السيرفرات من صفحة الحلقة =====
def extract_server_urls(episode_url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = requests.get(episode_url, headers=headers, timeout=30)
        resp.encoding = 'utf-8'
    except:
        return []
    soup = BeautifulSoup(resp.text, 'html.parser')
    # البحث عن كود PostData في السكريبتات
    for script in soup.find_all('script'):
        if script.string and 'PostData' in script.string:
            # استخراج Embed URLs مشفرة base64
            matches = re.findall(r'"Embed"\s*:\s*"([^"]+)"', script.string)
            for match in matches:
                try:
                    decoded = base64.b64decode(match).decode('utf-8')
                    if decoded.startswith('http'):
                        return [decoded]
                except:
                    continue
    return []

# ===== الحصول على رابط فيديو مباشر من سيرفر =====
def get_direct_video_url(server_url, referer):
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Referer': referer
    }
    try:
        resp = requests.get(server_url, headers=headers, timeout=20)
        # البحث عن رابط mp4
        match = re.search(r'(https?://[^"\']+\.mp4[^"\']*)', resp.text)
        if match:
            return match.group(1)
        return None
    except:
        return None

# ===== تحميل الفيديو =====
def download_video(url, output_path):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        with requests.get(url, headers=headers, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(output_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        return os.path.exists(output_path)
    except Exception as e:
        print(f"❌ فشل التحميل: {e}")
        return False

# ===== ضغط الفيديو إلى 240p =====
def compress_to_240p(input_path, output_path):
    if not os.path.exists(input_path):
        return False
    cmd = [
        'ffmpeg', '-i', input_path,
        '-vf', 'scale=-2:240',
        '-c:v', 'libx264', '-crf', '30', '-preset', 'veryfast',
        '-c:a', 'aac', '-b:a', '48k',
        '-y', output_path
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=600)
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except:
        return False

# ===== رفع الملف إلى GitHub Releases =====
def upload_to_release(file_path, series_name, episode_num):
    try:
        release = repo.get_release(RELEASE_TAG)
    except:
        release = repo.create_git_release(RELEASE_TAG, "Compressed Episodes", "Videos compressed to 240p")
    
    file_name = f"{series_name}_E{episode_num:02d}_240p.mp4"
    # حذف الاسم القديم إن وجد
    for asset in release.get_assets():
        if asset.name == file_name:
            asset.delete_asset()
            break
    
    with open(file_path, "rb") as f:
        asset = release.upload_asset_from_memory(
            f.read(),
            name=file_name,
            content_type="video/mp4"
        )
    return asset.browser_download_url

# ===== معالجة حلقة واحدة =====
def process_episode(series_name, series_url, episode_num):
    print(f"  🎬 معالجة {series_name} - حلقة {episode_num}")
    # بناء رابط الحلقة
    series_slug = series_url.rstrip('/').split('/')[-1]
    if series_slug.startswith('category-'):
        series_slug = series_slug[9:]
    if series_slug.endswith('-مدب'):
        series_slug = series_slug[:-4]
    if series_slug.startswith('مسلسل-'):
        series_slug = series_slug[7:]
    episode_url = f"https://lodynet.watch/{series_slug}-الحلقة-{episode_num}/"
    
    # استخراج روابط السيرفرات
    server_urls = extract_server_urls(episode_url)
    if not server_urls:
        print(f"    ❌ لا توجد سيرفرات للحلقة {episode_num}")
        return None
    
    # محاولة الحصول على رابط مباشر
    direct_url = None
    for srv in server_urls:
        direct_url = get_direct_video_url(srv, episode_url)
        if direct_url:
            break
    
    if not direct_url:
        print(f"    ❌ لم نجد رابط فيديو مباشر للحلقة {episode_num}")
        return None
    
    # تحميل الفيديو
    temp_raw = f"temp_{int(time.time())}.mp4"
    print(f"    ⬇️ تحميل الفيديو...")
    if not download_video(direct_url, temp_raw):
        return None
    
    # ضغط الفيديو
    compressed_file = f"compressed_{int(time.time())}.mp4"
    print(f"    🔄 ضغط الفيديو إلى 240p...")
    if not compress_to_240p(temp_raw, compressed_file):
        os.remove(temp_raw)
        return None
    
    # رفع إلى GitHub Releases
    print(f"    ⬆️ رفع الملف إلى GitHub Releases...")
    download_url = upload_to_release(compressed_file, series_name, episode_num)
    
    # تنظيف
    os.remove(temp_raw)
    os.remove(compressed_file)
    
    return download_url

# ===== الدالة الرئيسية =====
def main():
    print("🚀 بدء تشغيل السكريبت المتكامل (جلب البيانات + تحميل وضغط الحلقات)...")
    
    # إنشاء مجلد البيانات
    os.makedirs("data", exist_ok=True)
    metadata_path = "data/metadata.json"
    
    # تحميل البيانات الحالية
    if os.path.exists(metadata_path):
        with open(metadata_path, "r", encoding="utf-8") as f:
            all_data = json.load(f)
    else:
        all_data = {"series": {}, "last_update": None}
    
    # جلب المسلسلات
    series_list = get_all_series(SERIES_PAGE)
    if not series_list:
        print("⚠️ لم يتم العثور على أي مسلسل.")
        return
    
    updated_count = 0
    for series in series_list:
        name = series['name']
        url = series['url']
        cover = series.get('cover')
        
        # تحديث بيانات المسلسل في الملف
        if name not in all_data["series"]:
            all_data["series"][name] = {"episodes": [], "cover": cover}
        else:
            # تحديث الصورة إذا تغيرت
            all_data["series"][name]["cover"] = cover
        
        # جلب الحلقات
        episode_numbers = get_episodes_for_series(url)
        existing_episodes = {e['episode'] for e in all_data["series"][name].get('episodes', [])}
        new_episodes = [ep for ep in episode_numbers if ep not in existing_episodes]
        
        # معالجة الحلقات الجديدة (مع حد أقصى)
        processed = 0
        for ep_num in new_episodes:
            if processed >= MAX_EPISODES_PER_RUN:
                break
            # معالجة الحلقة (تحميل وضغط)
            video_url = process_episode(name, url, ep_num)
            if video_url:
                # إضافة الحلقة إلى البيانات
                all_data["series"][name]["episodes"].append({
                    'episode': ep_num,
                    'url': episode_url,
                    'video_url': video_url,
                    'date_added': datetime.now().isoformat()
                })
                updated_count += 1
                processed += 1
            time.sleep(5)  # تجنب الحظر
        
        time.sleep(2)  # بين المسلسلات
    
    all_data["last_update"] = datetime.now().isoformat()
    
    # حفظ البيانات
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ تم تحديث {updated_count} حلقة جديدة (تم تحميلها وضغطها)")
    print(f"📂 إجمالي المسلسلات: {len(all_data['series'])}")

if __name__ == "__main__":
    main()
