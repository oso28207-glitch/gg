#!/usr/bin/env python3
"""
ضغط حلقة معينة عند الطلب عبر GitHub Actions.
يستقبل اسم المسلسل ورقم الحلقة كمتغيرات بيئية.
"""
import os
import sys
import json
import time
import subprocess
from github import Github

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

# ===== البحث عن سيرفر صالح باستخدام yt-dlp =====
def find_working_server(servers):
    """محاولة العثور على رابط مباشر للفيديو باستخدام yt-dlp"""
    for url in servers:
        print(f"  🔍 محاولة السيرفر: {url[:60]}...")
        try:
            # استخدام yt-dlp للحصول على معلومات الفيديو (بدون تحميل)
            cmd = [
                'yt-dlp',
                '--no-playlist',      # للتأكد من أنه ليس قائمة تشغيل
                '--get-url',          # للحصول على رابط الفيديو المباشر فقط
                '--quiet',            # لتقليل الإخراج غير الضروري
                '--no-warnings',
                url
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0 and result.stdout.strip():
                direct_url = result.stdout.strip().split('\n')[0]  # خذ أول رابط
                print(f"  ✅ تم العثور على رابط مباشر: {direct_url[:80]}...")
                return direct_url
            else:
                print(f"  ⚠️ فشل yt-dlp في استخراج رابط من هذا السيرفر")
                continue
        except subprocess.TimeoutExpired:
            print(f"  ⚠️ انتهى الوقت المحدد لـ yt-dlp مع هذا السيرفر")
            continue
        except Exception as e:
            print(f"  ⚠️ خطأ في yt-dlp: {e}")
            continue
    
    print("❌ لم يتم العثور على أي سيرفر صالح")
    return None

# ===== تحميل الفيديو باستخدام yt-dlp وضغطه =====
def download_and_compress(video_url, output_path):
    print(f"⬇️ تحميل الفيديو باستخدام yt-dlp...")
    temp_input = "temp_input.mp4"
    
    try:
        # تحميل الفيديو باستخدام yt-dlp
        cmd_download = [
            'yt-dlp',
            '--no-playlist',
            '-f', 'best[ext=mp4]/best',  # أفضل جودة بصيغة mp4
            '-o', temp_input,
            '--quiet',
            '--no-warnings',
            video_url
        ]
        subprocess.run(cmd_download, check=True, timeout=300)
        print("✅ تم التحميل بنجاح")
        
        # ضغط الفيديو
        print("🔄 جاري الضغط إلى 240p...")
        cmd_compress = [
            'ffmpeg', '-i', temp_input,
            '-vf', 'scale=-2:240',
            '-c:v', 'libx264', '-crf', '30', '-preset', 'veryfast',
            '-c:a', 'aac', '-b:a', '48k',
            '-y', output_path
        ]
        subprocess.run(cmd_compress, check=True, timeout=600)
        print("✅ تم الضغط بنجاح")
        
        os.remove(temp_input)
        return True
    except subprocess.TimeoutExpired:
        print("❌ انتهى الوقت المحدد للتحميل أو الضغط")
        if os.path.exists(temp_input):
            os.remove(temp_input)
        return False
    except Exception as e:
        print(f"❌ فشل التحميل أو الضغط: {e}")
        if os.path.exists(temp_input):
            os.remove(temp_input)
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
    
    video_url = find_working_server(servers)
    if not video_url:
        print("❌ لا يوجد سيرفر صالح للتحميل")
        sys.exit(1)
    
    output_file = f"compressed_{int(time.time())}.mp4"
    if not download_and_compress(video_url, output_file):
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
