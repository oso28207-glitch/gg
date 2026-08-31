#!/usr/bin/env python3
"""
ضغط حلقة معينة عند الطلب باستخدام Selenium و yt-dlp مع محاكاة متقدمة.
"""
import os
import sys
import json
import time
import re
import requests
import subprocess
from github import Github, Auth
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import yt_dlp

# ===== إصلاح SSL =====
import ssl
import certifi
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

# ===== قراءة المتغيرات =====
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

# ===== GitHub =====
auth = Auth.Token(GITHUB_TOKEN)
g = Github(auth=auth)
repo = g.get_repo(REPO_NAME)

# ===== دوال الميتاداتا =====
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

# ===== إعداد Selenium المتقدم =====
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
    chrome_options.add_argument('--allow-insecure-localhost')
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver
    except Exception as e:
        print(f"❌ فشل إعداد Selenium: {e}")
        return None

# ===== استخراج الرابط المباشر باستخدام Selenium (محسّن) =====
def extract_direct_video_with_selenium(server_url, referer):
    driver = setup_selenium()
    if not driver:
        return None
    try:
        print(f"🔄 فتح السيرفر: {server_url[:80]}...")
        driver.get(server_url)
        
        # الانتظار حتى يتم تحميل الصفحة (زيادة الوقت)
        time.sleep(10)
        
        # محاولة العثور على زر التشغيل والنقر عليه (للسيرفرات التي تحتاج تفعيل)
        try:
            play_buttons = driver.find_elements(By.CSS_SELECTOR, 'button[aria-label*="play"], button[aria-label*="Play"], .play-button, .vjs-big-play-button')
            for btn in play_buttons:
                try:
                    btn.click()
                    print("  ▶️ تم النقر على زر التشغيل")
                    time.sleep(3)
                    break
                except:
                    continue
        except:
            pass
        
        # البحث عن فيديو مباشر
        # 1. عنصر video
        videos = driver.find_elements(By.TAG_NAME, 'video')
        for video in videos:
            src = video.get_attribute('src')
            if src and src.startswith('http') and ('.mp4' in src or '.m3u8' in src):
                print(f"✅ تم العثور على رابط من video: {src[:80]}")
                driver.quit()
                return src
            # البحث عن مصدر داخل video
            sources = video.find_elements(By.TAG_NAME, 'source')
            for src_elem in sources:
                src = src_elem.get_attribute('src')
                if src and src.startswith('http'):
                    print(f"✅ تم العثور على رابط من source: {src[:80]}")
                    driver.quit()
                    return src
        
        # 2. البحث في كود الصفحة
        page_source = driver.page_source
        matches = re.findall(r'(https?://[^"\']+\.(?:mp4|m3u8|webm)[^"\']*)', page_source)
        for url in matches:
            if 'novideo' not in url and 'player' not in url:
                print(f"✅ تم استخراج رابط من الصفحة: {url[:80]}")
                driver.quit()
                return url
        
        # 3. البحث داخل iframes (الأكثر أهمية)
        iframes = driver.find_elements(By.TAG_NAME, 'iframe')
        for iframe in iframes:
            src = iframe.get_attribute('src')
            if src and ('video' in src or 'embed' in src or 'player' in src or 'ok.ru' in src or 'dood' in src):
                try:
                    driver.switch_to.frame(iframe)
                    time.sleep(5)  # انتظار تحميل المحتوى داخل الإطار
                    iframe_source = driver.page_source
                    # البحث عن فيديو داخل الإطار
                    inner_videos = driver.find_elements(By.TAG_NAME, 'video')
                    for v in inner_videos:
                        src2 = v.get_attribute('src')
                        if src2 and src2.startswith('http'):
                            print(f"✅ تم العثور على رابط داخل iframe: {src2[:80]}")
                            driver.switch_to.default_content()
                            driver.quit()
                            return src2
                    # البحث عن روابط في النص
                    matches2 = re.findall(r'(https?://[^"\']+\.(?:mp4|m3u8)[^"\']*)', iframe_source)
                    if matches2:
                        for url in matches2:
                            if 'novideo' not in url:
                                print(f"✅ تم استخراج رابط من iframe: {url[:80]}")
                                driver.switch_to.default_content()
                                driver.quit()
                                return url
                    driver.switch_to.default_content()
                except:
                    driver.switch_to.default_content()
                    continue
        
        print("⚠️ لم يتم العثور على رابط مباشر عبر Selenium.")
        driver.quit()
        return None
    except Exception as e:
        print(f"❌ خطأ في Selenium: {e}")
        try:
            driver.quit()
        except:
            pass
        return None

# ===== التنزيل باستخدام yt-dlp مع خيارات محاكاة =====
def download_with_ytdlp(url, output_path, referer):
    try:
        safe_referer = re.sub(r'[^\x00-\x7F]+', '', referer) if referer else ''
        ydl_opts = {
            'format': 'best[height<=720]/best',
            'outtmpl': output_path,
            'quiet': False,
            'retries': 5,
            'fragment_retries': 5,
            'socket_timeout': 60,
            'extractor_args': {
                'generic': {
                    'impersonate': ['chrome'],  # محاكاة متصفح Chrome
                    'no-playlist': True,
                }
            },
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': safe_referer,
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
            }
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception as e:
        print(f"⚠️ فشل yt-dlp: {e}")
        return False

# ===== التنزيل باستخدام requests مع تجاوز SSL =====
def download_with_requests(url, output_path, referer):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': referer,
        'Accept-Language': 'en-US,en;q=0.9',
    }
    try:
        with requests.get(url, headers=headers, stream=True, timeout=120, verify=False) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            downloaded = 0
            with open(output_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            print(f"\r⏳ تحميل: {downloaded/total_size*100:.1f}%", end='')
            print()
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception as e:
        print(f"❌ فشل requests: {e}")
        return False

# ===== دالة التحميل والضغط الرئيسية =====
def download_and_compress(episode_data, output_path):
    servers = episode_data.get("servers", [])
    page_url = episode_data.get("url", "")
    
    if not servers:
        print("❌ لا توجد سيرفرات")
        return False

    print(f"🔍 تم العثور على {len(servers)} سيرفر.")
    temp_file = "temp_input.mp4"

    for idx, server_url in enumerate(servers, 1):
        print(f"\n🔄 محاولة السيرفر {idx}: {server_url[:80]}...")
        
        # 1. محاولة استخراج رابط مباشر باستخدام Selenium
        direct_url = extract_direct_video_with_selenium(server_url, page_url)
        if direct_url and 'novideo' not in direct_url:
            print(f"✅ تم استخراج رابط مباشر: {direct_url[:80]}...")
            # محاولة التحميل باستخدام requests
            if download_with_requests(direct_url, temp_file, page_url):
                print("✅ تم التحميل بنجاح (requests)")
                break
            # إذا فشل requests، نحاول yt-dlp على نفس الرابط
            print("🔄 محاولة yt-dlp على الرابط المباشر...")
            if download_with_ytdlp(direct_url, temp_file, page_url):
                print("✅ تم التحميل بنجاح (yt-dlp)")
                break
        
        # 2. محاولة استخدام yt-dlp مباشرة على رابط السيرفر (كحل أخير)
        print("🔄 محاولة yt-dlp على رابط السيرفر...")
        if download_with_ytdlp(server_url, temp_file, page_url):
            print("✅ تم التحميل بنجاح (yt-dlp مباشرة)")
            break
    else:
        print("❌ فشل التحميل من جميع السيرفرات")
        return False

    # التحقق من الملف
    if not os.path.exists(temp_file) or os.path.getsize(temp_file) == 0:
        print("❌ الملف المحمل غير صالح")
        return False

    # ضغط الفيديو
    print("🔄 جاري الضغط إلى 240p...")
    cmd = [
        'ffmpeg', '-i', temp_file,
        '-vf', 'scale=-2:240',
        '-c:v', 'libx264', '-crf', '30', '-preset', 'veryfast',
        '-c:a', 'aac', '-b:a', '48k',
        '-y', output_path
    ]
    try:
        subprocess.run(cmd, check=True, timeout=600)
        print("✅ تم الضغط بنجاح")
        os.remove(temp_file)
        return True
    except Exception as e:
        print(f"❌ فشل الضغط: {e}")
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return False

# ===== رفع الملف إلى Releases =====
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
    
    output_file = f"compressed_{int(time.time())}.mp4"
    
    if not download_and_compress(episode_data, output_file):
        print("❌ فشل تحميل وضغط الفيديو")
        sys.exit(1)
    
    print("⬆️ رفع الملف إلى GitHub Releases...")
    download_url = upload_to_release(output_file)
    print(f"✅ رابط التحميل: {download_url}")
    
    episode_data["compressed_url"] = download_url
    episode_data["compressed_date"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_metadata(data)
    print("✅ تم تحديث الميتاداتا")
    
    os.remove(output_file)
    print("🎉 انتهى الضغط بنجاح")

if __name__ == "__main__":
    main()
