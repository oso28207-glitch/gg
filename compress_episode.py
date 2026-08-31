#!/usr/bin/env python3
"""
ضغط حلقة معينة عند الطلب باستخدام Selenium لاستخراج الروابط المباشرة.
يستقبل اسم المسلسل ورقم الحلقة كمتغيرات بيئية.
"""
import os
import sys
import json
import time
import re
import base64
import requests
import subprocess
from github import Github
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ===== قراءة المتغيرات البيئية =====
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    print("❌ GITHUB_TOKEN غير موجود")
    sys.exit(1)

REPO_NAME = os.environ.get("GITHUB_REPOSITORY")
if not REPO_NAME:
    print("❌ GITHUB_REPOSITORY غير موجود")
    sys.exit(1)

SERIES_NAME = os.environ.get("SERIES_NAME")
EPISODE_NUM = os.environ.get("EPISODE_NUM")

if not SERIES_NAME or not EPISODE_NUM:
    print("❌ يجب توفير SERIES_NAME و EPISODE_NUM")
    sys.exit(1)

EPISODE_NUM = int(EPISODE_NUM)
RELEASE_TAG = "compressed-episodes"

# ===== الاتصال بـ GitHub =====
g = Github(GITHUB_TOKEN)
repo = g.get_repo(REPO_NAME)

# ===== دوال التعامل مع metadata.json =====
def load_metadata():
    try:
        contents = repo.get_contents("data/metadata.json")
        return json.loads(contents.decoded_content.decode('utf-8'))
    except:
        return {"series": {}}

def save_metadata(data):
    try:
        contents = repo.get_contents("data/metadata.json")
        repo.update_file(
            "data/metadata.json",
            f"تحديث رابط حلقة {SERIES_NAME} - {EPISODE_NUM}",
            json.dumps(data, ensure_ascii=False, indent=2),
            contents.sha
        )
    except:
        repo.create_file(
            "data/metadata.json",
            "إنشاء ملف الميتاداتا",
            json.dumps(data, ensure_ascii=False, indent=2)
        )

# ===== إعداد Selenium =====
def setup_selenium():
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--disable-notifications')
    chrome_options.add_argument('--ignore-certificate-errors')
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver
    except Exception as e:
        print(f"❌ فشل إعداد Selenium: {e}")
        return None

# ===== استخراج الرابط المباشر باستخدام Selenium =====
def extract_direct_video_with_selenium(server_url):
    driver = setup_selenium()
    if not driver:
        return None
    try:
        print(f"🔄 فتح السيرفر باستخدام Selenium: {server_url[:80]}...")
        driver.get(server_url)
        # انتظر حتى يتم تحميل الصفحة
        time.sleep(5)
        page_source = driver.page_source
        
        # البحث عن رابط mp4 مباشر
        match = re.search(r'(https?://[^"\']+\.mp4[^"\']*)', page_source)
        if match:
            return match.group(1)
        
        # البحث عن sources في JavaScript
        match = re.search(r'sources:\s*\[\s*"([^"]+\.mp4[^"]*)"\s*\]', page_source)
        if match:
            return match.group(1)
        
        # البحث عن رابط m3u8
        match = re.search(r'(https?://[^"\']+\.m3u8[^"\']*)', page_source)
        if match:
            return match.group(1)
        
        return None
    except Exception as e:
        print(f"❌ خطأ في Selenium: {e}")
        return None
    finally:
        driver.quit()

# ===== تحميل الفيديو باستخدام requests =====
def download_with_requests(url, output_path, referer):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': referer,
        'Accept-Language': 'ar-SA,ar;q=0.9,en;q=0.8',
    }
    try:
        with requests.get(url, headers=headers, stream=True, timeout=120) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            block_size = 8192
            downloaded = 0
            with open(output_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=block_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = (downloaded / total_size) * 100
                            print(f"\r⏳ جاري التحميل: {percent:.1f}%", end='')
            print()
        return os.path.exists(output_path)
    except Exception as e:
        print(f"❌ فشل التنزيل عبر requests: {e}")
        return False

# ===== ضغط الفيديو =====
def compress_to_240p(input_path, output_path):
    if not os.path.exists(input_path):
        return False
    print("🔄 جاري الضغط إلى 240p...")
    cmd = [
        'ffmpeg', '-i', input_path,
        '-vf', 'scale=-2:240',
        '-c:v', 'libx264', '-crf', '30', '-preset', 'veryfast',
        '-c:a', 'aac', '-b:a', '48k',
        '-y', output_path
    ]
    try:
        subprocess.run(cmd, check=True, timeout=600)
        return os.path.exists(output_path)
    except Exception as e:
        print(f"❌ فشل الضغط: {e}")
        return False

# ===== رفع الفيديو المضغوط إلى Releases =====
def upload_to_release(file_path):
    try:
        release = repo.get_release(RELEASE_TAG)
    except:
        release = repo.create_git_release(RELEASE_TAG, "فيديوهات مضغوطة", "فيديوهات مضغوطة إلى 240p")
    
    safe_name = SERIES_NAME.replace(' ', '_').replace('/', '_')
    file_name = f"{safe_name}_E{EPISODE_NUM:02d}_240p.mp4"
    
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

# ===== الدالة الرئيسية =====
def main():
    print(f"🚀 بدء ضغط الحلقة: {SERIES_NAME} - {EPISODE_NUM}")
    
    # تحميل الميتاداتا
    data = load_metadata()
    series = data.get("series", {}).get(SERIES_NAME)
    if not series:
        print(f"❌ المسلسل '{SERIES_NAME}' غير موجود")
        sys.exit(1)
    
    episode_data = None
    for ep in series.get("episodes", []):
        if ep.get("episode") == EPISODE_NUM:
            episode_data = ep
            break
    
    if not episode_data:
        print(f"❌ الحلقة {EPISODE_NUM} غير موجودة")
        sys.exit(1)
    
    servers = episode_data.get("servers", [])
    if not servers:
        print("❌ لا توجد سيرفرات لهذه الحلقة")
        sys.exit(1)
    
    temp_file = f"temp_{int(time.time())}.mp4"
    downloaded = False
    direct_url = None
    
    # محاولة استخراج رابط مباشر من كل سيرفر
    for idx, server_url in enumerate(servers, 1):
        print(f"🔄 محاولة السيرفر {idx}: {server_url[:80]}...")
        
        direct_url = extract_direct_video_with_selenium(server_url)
        if direct_url:
            print(f"✅ تم استخراج رابط مباشر: {direct_url[:80]}...")
            if download_with_requests(direct_url, temp_file, server_url):
                downloaded = True
                break
            else:
                print("⚠️ فشل التنزيل من هذا السيرفر، نحاول التالي...")
                continue
    
    if not downloaded:
        print("❌ فشل تحميل الفيديو من جميع السيرفرات")
        sys.exit(1)
    
    # ضغط الفيديو
    output_file = f"compressed_{int(time.time())}.mp4"
    if not compress_to_240p(temp_file, output_file):
        print("❌ فشل الضغط")
        # نحتفظ بالملف الأصلي مؤقتاً
        shutil.copy2(temp_file, output_file)
        print("⚠️ تم حفظ الملف الأصلي بدلاً من المضغوط")
    
    # تنظيف الملف المؤقت
    try:
        os.remove(temp_file)
    except:
        pass
    
    # رفع إلى Releases
    print("⬆️ رفع الملف إلى GitHub Releases...")
    download_url = upload_to_release(output_file)
    print(f"✅ رابط التحميل: {download_url}")
    
    # تحديث الميتاداتا
    episode_data["compressed_url"] = download_url
    episode_data["compressed_date"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_metadata(data)
    print("✅ تم تحديث الميتاداتا")
    
    # تنظيف
    try:
        os.remove(output_file)
    except:
        pass
    
    print("🎉 انتهى الضغط بنجاح")

if __name__ == "__main__":
    main()
