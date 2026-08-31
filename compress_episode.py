#!/usr/bin/env python3
"""
ضغط حلقة معينة عند الطلب باستخدام GitHub Actions
يستقبل اسم المسلسل ورقم الحلقة كمعاملات
"""
import os
import sys
import json
import requests
import subprocess
import time
from github import Github

# ===== الإعدادات =====
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    print("❌ GITHUB_TOKEN غير موجود")
    sys.exit(1)

REPO_NAME = os.environ.get("GITHUB_REPOSITORY")
if not REPO_NAME:
    print("❌ GITHUB_REPOSITORY غير موجود")
    sys.exit(1)

# قراءة معاملات الإدخال من GitHub Actions
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

# ===== تحميل الميتاداتا =====
def load_metadata():
    try:
        # قراءة الملف من المستودع
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

# ===== البحث عن سيرفر يعمل =====
def find_working_server(servers):
    for url in servers:
        try:
            # التحقق مما إذا كان الرابط يعطي فيديو مباشر
            if '.mp4' in url.lower() or '.m3u8' in url.lower():
                return url
            # محاولة تحميل جزء صغير للتحقق
            resp = requests.head(url, timeout=10)
            if resp.status_code == 200:
                content_type = resp.headers.get('content-type', '')
                if 'video' in content_type or 'mp4' in content_type:
                    return url
        except:
            continue
    return servers[0] if servers else None

# ===== تحميل وضغط الفيديو =====
def download_and_compress(video_url, output_path):
    print(f"⬇️ تحميل الفيديو من: {video_url[:80]}...")
    try:
        # تحميل الفيديو
        resp = requests.get(video_url, stream=True, timeout=120)
        resp.raise_for_status()
        temp_input = "temp_input.mp4"
        with open(temp_input, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        print("✅ تم التحميل")
        
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
        return False

# ===== رفع الفيديو المضغوط إلى Releases =====
def upload_to_release(file_path):
    try:
        release = repo.get_release(RELEASE_TAG)
    except:
        release = repo.create_git_release(RELEASE_TAG, "Compressed Episodes", "فيديوهات مضغوطة إلى 240p")
    
    # اسم الملف
    file_name = f"{SERIES_NAME.replace(' ', '_')}_E{EPISODE_NUM:02d}_240p.mp4"
    
    # حذف الملف القديم إن وجد
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
    
    # اختيار سيرفر يعمل
    video_url = find_working_server(servers)
    if not video_url:
        print("❌ لا يوجد سيرفر صالح")
        sys.exit(1)
    
    # تحميل وضغط
    output_file = f"compressed_{int(time.time())}.mp4"
    if not download_and_compress(video_url, output_file):
        sys.exit(1)
    
    # رفع إلى Releases
    print("⬆️ رفع الملف إلى GitHub Releases...")
    download_url = upload_to_release(output_file)
    print(f"✅ رابط التحميل: {download_url}")
    
    # تحديث الميتاداتا
    episode_data["compressed_url"] = download_url
    episode_data["compressed_date"] = time.strftime("%Y-%m-%d %H:%M:%S")
    
    # حفظ التغييرات
    save_metadata(data)
    print("✅ تم تحديث الميتاداتا")
    
    # تنظيف
    os.remove(output_file)

if __name__ == "__main__":
    main()
