#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ضغط حلقة عند الطلب (معدل لدعم yt-dlp مع روابط embed و see)
"""

import os
import sys
import json
import time
import subprocess
import requests
from github import Github, Auth
import yt_dlp
import certifi
from bs4 import BeautifulSoup

os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

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

auth = Auth.Token(GITHUB_TOKEN)
g = Github(auth=auth)
repo = g.get_repo(REPO_NAME)

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

def is_direct_video(url):
    return any(ext in url.lower() for ext in ['.mp4', '.m3u8', '.webm'])

def download_direct(url, output_path):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    try:
        with requests.get(url, headers=headers, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(output_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except:
        return False

def extract_iframe_from_page(url):
    """استخراج رابط iframe من صفحة الحلقة"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://aa.3ick.net/',
        }
        resp = requests.get(url, headers=headers, timeout=30)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'html.parser')
        # البحث عن iframe داخل #player_viewer أو .player-viewer
        player_viewer = soup.find('div', id='player_viewer') or soup.find('div', class_='player-viewer')
        if player_viewer:
            iframe = player_viewer.find('iframe', src=True)
            if iframe:
                src = iframe.get('src')
                if src and src.startswith('http'):
                    return src
        # البحث عن أي iframe في الصفحة
        for iframe in soup.find_all('iframe', src=True):
            src = iframe.get('src')
            if src and src.startswith('http'):
                return src
    except Exception as e:
        print(f"⚠️ فشل استخراج iframe: {e}")
    return None

def download_with_ytdlp(url, output_path):
    try:
        ydl_opts = {
            'format': 'best[height<=720]/best',
            'outtmpl': output_path,
            'quiet': False,
            'retries': 10,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://aa.3ick.net/',
            },
            'no_check_certificate': True,
            'ignoreerrors': True,
            'extractor_args': {
                'generic': {
                    'no_playlist': True,
                }
            }
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception as e:
        print(f"⚠️ yt-dlp فشل: {e}")
        return False

def download_and_compress(episode_data, output_path):
    servers = episode_data.get("servers", [])
    if not servers:
        print("❌ لا توجد سيرفرات")
        return False

    temp_file = "temp_input.mp4"

    # محاولة أولى: استخراج iframe من رابط الحلقة نفسه (إذا كان من نوع /watch/episodes/)
    episode_url = episode_data.get("url")
    if episode_url and '/watch/episodes/' in episode_url:
        print(f"🔍 محاولة استخراج iframe من: {episode_url}")
        iframe_url = extract_iframe_from_page(episode_url)
        if iframe_url:
            print(f"✅ تم العثور على iframe: {iframe_url}")
            # نضيف iframe_url كسيرفر إضافي في بداية القائمة
            servers.insert(0, iframe_url)

    # محاولة أيضاً استخدام رابط /see/ إذا كان موجوداً
    see_url = episode_url.replace('/watch/episodes/', '/watch/episodes/') + 'see/' if episode_url else None
    if see_url:
        print(f"🔍 محاولة استخراج iframe من صفحة المشاهدة: {see_url}")
        iframe_from_see = extract_iframe_from_page(see_url)
        if iframe_from_see:
            print(f"✅ تم العثور على iframe في صفحة المشاهدة: {iframe_from_see}")
            servers.insert(0, iframe_from_see)

    # محاولة إنشاء رابط التضمين مباشرة (embed) إذا كان الرابط من نوع /watch/episodes/
    if episode_url and '/watch/episodes/' in episode_url:
        # استخراج معرف الحلقة من الرابط (الجزء الأخير)
        parts = episode_url.rstrip('/').split('/')
        episode_id = parts[-1]  # مثل 'serie-racon-ailem-icin-mudblij-season-1-episode-11'
        # نحاول بناء رابط embed (قد يختلف)
        embed_url = f"https://aa.3ick.net/embed/1/{episode_id}/2/"
        print(f"🔍 محاولة استخدام رابط embed: {embed_url}")
        servers.insert(0, embed_url)

    for idx, server_url in enumerate(servers, 1):
        print(f"🔄 محاولة السيرفر {idx}: {server_url[:80]}...")

        # إذا كان الرابط يحتوي على /embed/ أو /see/ أو mwdy.cc، استخدم yt-dlp
        if '/embed/' in server_url or '/see/' in server_url or 'mwdy.cc' in server_url:
            print("  📥 رابط تضمين أو صفحة مشاهدة، نستخدم yt-dlp...")
            if download_with_ytdlp(server_url, temp_file):
                print("✅ تم التحميل بنجاح (yt-dlp)")
                break
            else:
                print("  ⚠️ فشل التحميل باستخدام yt-dlp")
                continue

        # إذا كان رابطاً مباشراً
        if is_direct_video(server_url):
            print("  📥 رابط مباشر، نحاول التحميل...")
            if download_direct(server_url, temp_file):
                print("✅ تم التحميل بنجاح")
                break
            else:
                print("  ⚠️ فشل التحميل المباشر، نحاول yt-dlp...")
                if download_with_ytdlp(server_url, temp_file):
                    print("✅ تم التحميل بنجاح (yt-dlp)")
                    break
        else:
            print("  🔄 محاولة yt-dlp...")
            if download_with_ytdlp(server_url, temp_file):
                print("✅ تم التحميل بنجاح (yt-dlp)")
                break
    else:
        print("❌ فشل التحميل من جميع السيرفرات")
        return False

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
