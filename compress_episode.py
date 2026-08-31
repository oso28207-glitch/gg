#!/usr/bin/env python3
"""
ضغط حلقة معينة عند الطلب عبر GitHub Actions.
يستقبل اسم المسلسل ورقم الحلقة كمتغيرات بيئية.
"""
import os
import sys
import json
import time
import re
import requests
import subprocess
from bs4 import BeautifulSoup
from github import Github, Auth

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
auth = Auth.Token(GITHUB_TOKEN)
g = Github(auth=auth)
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

# ===== محاولة استخراج الرابط المباشر من streamtape =====
def extract_streamtape_direct(url):
    """محاولة استخراج الرابط المباشر من صفحة streamtape"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, 'html.parser')
        # البحث عن الرابط في JavaScript
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string:
                # البحث عن الرابط بصيغة .mp4
                match = re.search(r'(https?://[^\s"\']+\.mp4[^\s"\']*)', script.string)
                if match:
                    return match.group(1)
        return None
    except:
        return None

# ===== البحث عن سيرفر صالح =====
def find_working_server(servers):
    """محاولة العثور على رابط مباشر للفيديو"""
    # نفضل الروابط التي تنتهي بـ .mp4 أو .m3u8
    for url in servers:
        # إذا كان من streamtape، نحاول استخراج الرابط المباشر
        if 'streamtape.com/e/' in url:
            print(f"🔄 محاولة استخراج رابط مباشر من streamtape: {url[:60]}...")
            direct = extract_streamtape_direct(url)
            if direct:
                print(f"✅ تم استخراج رابط مباشر: {direct[:80]}...")
                return direct
            else:
                print("⚠️ فشل استخراج الرابط المباشر من streamtape")
                # نستمر في البحث عن روابط أخرى
                continue
        
        # إذا كان الرابط مباشراً (ينتهي بـ .mp4 أو .m3u8)
        if any(ext in url.lower() for ext in ['.mp4', '.m3u8']):
            # نتحقق مما إذا كان الرابط يعمل
            try:
                head = requests.head(url, timeout=10)
                if head.status_code == 200:
                    return url
                else:
                    print(f"⚠️ الرابط {url[:60]}... لا يعمل (HTTP {head.status_code})")
                    continue
            except:
                continue
        
        # بالنسبة للروابط الأخرى (fembed, ok.ru, إلخ) نعيدها كما هي مع أمل أنها تعمل
        return url
    
    # إذا لم نجد أي رابط، نعيد أول رابط
    return servers[0] if servers else None

# ===== تحميل وضغط الفيديو =====
def download_and_compress(video_url, output_path):
    print(f"⬇️ تحميل الفيديو من: {video_url[:80]}...")
    try:
        # تحميل الفيديو
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        # محاولة التحميل مع إعادة المحاولات
        max_retries = 3
        for attempt in range(max_retries):
            try:
                resp = requests.get(video_url, headers=headers, stream=True, timeout=120)
                resp.raise_for_status()
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                print(f"⚠️ محاولة {attempt+1} فشلت، إعادة المحاولة...")
                time.sleep(2)
        
        temp_input = "temp_input.mp4"
        total_size = int(resp.headers.get('content-length', 0))
        downloaded = 0
        with open(temp_input, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        print(f"\r⏳ تحميل: {percent:.1f}%", end='')
        print("\n✅ تم التحميل")
        
        # ضغط الفيديو
        print("🔄 جاري الضغط إلى 240p...")
        cmd = [
            'ffmpeg', '-i', temp_input,
            '-vf', 'scale=-2:240',
            '-c:v', 'libx264', '-crf', '30', '-preset', 'veryfast',
            '-c:a', 'aac', '-b:a', '48k',
            '-y', output_path
        ]
        subprocess.run(cmd, check=True, timeout=600)
        print("✅ تم الضغط")
        
        os.remove(temp_input)
        return True
    except Exception as e:
        print(f"❌ فشل التحميل أو الضغط: {e}")
        if os.path.exists("temp_input.mp4"):
            os.remove("temp_input.mp4")
        return False

# ===== رفع الفيديو المضغوط إلى Releases =====
def upload_to_release(file_path):
    # الحصول على الإصدار أو إنشاؤه
    try:
        release = repo.get_release(RELEASE_TAG)
    except:
        release = repo.create_git_release(RELEASE_TAG, "فيديوهات مضغوطة", "فيديوهات مضغوطة إلى 240p")
    
    # اسم الملف: اسم_المسلسل_Eرقم_240p.mp4
    safe_name = SERIES_NAME.replace(' ', '_').replace('/', '_')
    file_name = f"{safe_name}_E{EPISODE_NUM:02d}_240p.mp4"
    
    # حذف الملف القديم إن وجد (لتجنب التكرار)
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
    
    # البحث عن الحلقة
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
    
    # اختيار سيرفر صالح
    video_url = find_working_server(servers)
    if not video_url:
        print("❌ لا يوجد سيرفر صالح")
        sys.exit(1)
    print(f"🔗 تم اختيار السيرفر: {video_url[:80]}...")
    
    # تحميل وضغط
    output_file = f"compressed_{int(time.time())}.mp4"
    if not download_and_compress(video_url, output_file):
        sys.exit(1)
    
    # رفع إلى Releases
    print("⬆️ رفع الملف إلى GitHub Releases...")
    download_url = upload_to_release(output_file)
    print(f"✅ رابط التحميل: {download_url}")
    
    # تحديث الميتاداتا بإضافة compressed_url
    episode_data["compressed_url"] = download_url
    episode_data["compressed_date"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_metadata(data)
    print("✅ تم تحديث الميتاداتا")
    
    # تنظيف
    os.remove(output_file)
    print("🎉 انتهى الضغط بنجاح")

if __name__ == "__main__":
    main()
