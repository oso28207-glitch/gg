#!/usr/bin/env python3
import os
import sys
import json
import time
import re
import base64
import subprocess
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from github import Github

# ===== تثبيت المتطلبات =====
def install_reqs():
    print("📦 تثبيت المتطلبات...")
    reqs = ["beautifulsoup4", "requests", "PyGithub", "json5"]
    for r in reqs:
        subprocess.check_call([sys.executable, "-m", "pip", "install", r, "--quiet"])
install_reqs()

import json5

# ===== قراءة الإعدادات =====
with open("config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

CATEGORY_URL = CONFIG["category_url"]
MAX_PER_RUN = CONFIG.get("max_episodes_per_run", 3)

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

# ===== دوال استخراج البيانات (مأخوذة من ملفك) =====
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
        return json5.loads(post_data_str)
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

def get_direct_link(server_url, referer):
    """محاولة استخراج رابط مباشر .mp4 من السيرفر"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': referer
    }
    try:
        resp = requests.get(server_url, headers=headers, timeout=20)
        # بحث بسيط عن رابط mp4
        matches = re.findall(r'(https?://[^"\']+\.mp4[^"\']*)', resp.text)
        if matches:
            return matches[0]
        return None
    except:
        return None

# ===== ضغط الفيديو =====
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
    """رفع الملف إلى Release وإرجاع رابط التحميل المباشر"""
    try:
        release = repo.get_release(RELEASE_TAG)
    except:
        release = repo.create_git_release(RELEASE_TAG, "Compressed Episodes", "Videos compressed to 240p")

    file_name = f"{series_name}_E{episode_num:02d}_240p.mp4"
    # حذف الاسم القديم إن وجد (لتجنب التكرار)
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

# ===== جلب جميع المسلسلات من الفئة =====
def get_all_series():
    print(f"🔍 جلب المسلسلات من: {CATEGORY_URL}")
    resp = requests.get(CATEGORY_URL, headers={'User-Agent': 'Mozilla/5.0'})
    soup = BeautifulSoup(resp.text, 'html.parser')
    series_list = []
    # البحث عن عناوين المسلسلات (حسب هيكل الموقع)
    for link in soup.select('a[href*="/series/"]'):
        href = link.get('href')
        title = link.get('title') or link.text.strip()
        if href and title and 'مسلسل' in title:
            full_url = href if href.startswith('http') else f"https://lodynet.watch{href}"
            series_list.append({"name": title.strip(), "url": full_url})
    # إزالة التكرارات
    seen = set()
    unique = []
    for s in series_list:
        if s['name'] not in seen:
            seen.add(s['name'])
            unique.append(s)
    return unique

# ===== معالجة حلقة معينة =====
def process_episode(series_name, episode_num, referer_url):
    print(f"🎬 معالجة {series_name} - حلقة {episode_num}")
    page_url = f"https://lodynet.watch/{series_name.replace(' ', '-')}-حلقة-{episode_num}"
    # تبسيط: استخدام الرابط المرجعي لاستخراج PostData
    html = requests.get(page_url, headers={'User-Agent': 'Mozilla/5.0'}).text
    post_data = extract_post_data(html)
    if not post_data:
        return None
    server_urls = extract_server_urls(post_data)
    if not server_urls:
        return None
    
    direct_url = None
    for srv in server_urls:
        direct_url = get_direct_link(srv, page_url)
        if direct_url:
            break
    
    if not direct_url:
        return None

    # تحميل مؤقت
    temp_raw = f"temp_{int(time.time())}.mp4"
    print(f"⬇️ تحميل الفيديو من: {direct_url[:80]}...")
    r = requests.get(direct_url, stream=True)
    with open(temp_raw, 'wb') as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    
    # ضغط
    output_file = f"compressed_{int(time.time())}.mp4"
    print("🔄 جاري الضغط إلى 240p (قد يستغرق دقائق)...")
    if not compress_to_240p(temp_raw, output_file):
        os.remove(temp_raw)
        return None
    
    # رفع إلى Releases
    print("⬆️ رفع الملف إلى GitHub Releases...")
    download_url = upload_to_release(output_file, series_name, episode_num)
    
    # تنظيف
    os.remove(temp_raw)
    os.remove(output_file)
    
    return download_url

# ===== الدالة الرئيسية =====
def main():
    print("🚀 بدء تشغيل سكريبت التحديث اليومي...")
    
    # تحميل البيانات الحالية
    try:
        with open("data/metadata.json", "r", encoding="utf-8") as f:
            all_data = json.load(f)
    except:
        all_data = {"series": {}}

    # جلب جميع المسلسلات
    series_list = get_all_series()
    print(f"✅ تم العثور على {len(series_list)} مسلسل.")

    new_count = 0
    for series in series_list:
        if new_count >= MAX_PER_RUN:
            break
        name = series['name']
        # تحديد رقم الحلقة التالية لهذا المسلسل
        last_ep = all_data["series"].get(name, {}).get("last_episode", 0)
        next_ep = last_ep + 1
        
        print(f"\n--- {name} --- الحلقة التالية: {next_ep}")
        # محاولة معالجة الحلقة
        url = process_episode(name, next_ep, series['url'])
        if url:
            # حفظ في JSON
            if name not in all_data["series"]:
                all_data["series"][name] = {"episodes": []}
            all_data["series"][name]["episodes"].append({
                "episode": next_ep,
                "url": url,
                "date_added": datetime.now().isoformat()
            })
            all_data["series"][name]["last_episode"] = next_ep
            new_count += 1
            print(f"✅ تمت إضافة الحلقة {next_ep}")
            # تحديث الملف على GitHub
            with open("data/metadata.json", "w", encoding="utf-8") as f:
                json.dump(all_data, f, ensure_ascii=False, indent=2)
            # دفع التغيير إلى الريبو (سنفعلها عبر git في الـ Action)
        else:
            print(f"⚠️ لا توجد حلقة {next_ep} أو فشل التحميل.")
            # إذا لم توجد حلقة جديدة، نتوقف عن هذا المسلسل
            break

    print("🎉 انتهى السكريبت.")

if __name__ == "__main__":
    main()