#!/usr/bin/env python3
"""
جلب بيانات المسلسلات المدبلجة من موقع laaroza.mom
"""
import os
import sys
import json
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote, unquote
from datetime import datetime

# ===== الإعدادات =====
CONFIG_FILE = "config.json"
if not os.path.exists(CONFIG_FILE):
    CONFIG = {
        "search_url": "https://laaroza.mom/search.php?keywords=%D9%85%D8%AF%D8%A8%D9%84%D8%AC%D8%A9&video-id=",
        "max_series": 50
    }
else:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        CONFIG = json.load(f)

SEARCH_URL = CONFIG.get("search_url", "https://laaroza.mom/search.php?keywords=%D9%85%D8%AF%D8%A8%D9%84%D8%AC%D8%A9&video-id=")
MAX_SERIES = CONFIG.get("max_series", 50)

# ===== جلب قائمة الفيديوهات من نتائج البحث =====
def get_all_series(url):
    """استخراج قائمة الفيديوهات من صفحة البحث"""
    print(f"🔍 جلب الفيديوهات من: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.encoding = 'utf-8'
    except Exception as e:
        print(f"❌ فشل تحميل الصفحة: {e}")
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')
    series_list = []

    # البحث عن روابط الفيديوهات (افتراض هيكل بسيط)
    # في الغالب ستكون الروابط داخل عناصر <a> أو <div> مع class محدد
    # نحتاج إلى تفحص الموقع لتحديد selector المناسب
    # هذه محاولة عامة:
    for link in soup.find_all('a', href=True):
        href = link['href']
        # نبحث عن روابط تحتوي على "video" أو "watch" أو "embed"
        if '/video/' in href or '/watch/' in href or '/embed/' in href:
            title = link.get_text(strip=True) or link.get('title', '')
            if title and any(k in title for k in ['مدبلج', 'مدبلجة', 'مسلسل']):
                full_url = urljoin('https://laaroza.mom', href)
                # استخراج اسم المسلسل من العنوان (قد يكون اسم الحلقة)
                series_list.append({
                    'name': title.strip(),
                    'url': full_url,
                    'cover': ''  # قد لا تتوفر صور
                })

    # إزالة التكرارات
    seen = set()
    unique = []
    for s in series_list:
        if s['url'] not in seen:
            seen.add(s['url'])
            unique.append(s)

    print(f"✅ تم العثور على {len(unique)} فيديو/مسلسل")
    return unique[:MAX_SERIES]

# ===== جلب حلقات مسلسل معين (قد يكون فيديو واحد أو قائمة) =====
def get_episodes_for_series(series_url):
    """استخراج أرقام الحلقات من صفحة المسلسل (إن وجدت)"""
    print(f"  📂 جلب بيانات من: {series_url[:60]}...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = requests.get(series_url, headers=headers, timeout=30)
        resp.encoding = 'utf-8'
    except Exception as e:
        print(f"    ❌ فشل تحميل الصفحة: {e}")
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')
    episodes = []

    # إذا كانت الصفحة تعرض حلقة واحدة، نعيد رقم 1
    # أو يمكن البحث عن قائمة حلقات داخل الصفحة
    # في البداية نفترض أن كل رابط هو حلقة مستقلة
    # ونستخدم الرابط نفسه مع رقم 1
    episodes.append(1)

    # البحث عن روابط حلقات أخرى (مثل "الحلقة 2", "الحلقة 3")
    text = soup.get_text()
    pattern = r'(?:حلقة\s*رقم\s*|الحلقة\s*)(\d+)'
    matches = re.findall(pattern, text)
    for match in matches:
        ep_num = int(match)
        if ep_num not in episodes:
            episodes.append(ep_num)

    # البحث عن روابط تشبه الحلقات
    for link in soup.find_all('a', href=True):
        href = link['href']
        if '/video/' in href or '/watch/' in href:
            match = re.search(r'-(\d+)/?$', href)
            if match:
                ep_num = int(match.group(1))
                if ep_num not in episodes:
                    episodes.append(ep_num)

    episodes.sort()
    print(f"    ✅ تم العثور على {len(episodes)} حلقة")
    return episodes

# ===== بناء بيانات الحلقات =====
def build_episode_data(series_name, series_url, episode_numbers):
    """بناء بيانات الحلقات مع روابط صفحاتها"""
    episodes = []
    for ep_num in episode_numbers:
        # بناء رابط الحلقة - قد يكون بنفس الرابط أو بصيغة مختلفة
        # إذا كان الرابط يحتوي على رقم، نستبدله، وإلا نضيفه
        if re.search(r'-(\d+)/?$', series_url):
            # استبدال الرقم في الرابط
            new_url = re.sub(r'-(\d+)/?$', f'-{ep_num}/', series_url)
        else:
            # إضافة الرقم في نهاية الرابط
            base = series_url.rstrip('/')
            new_url = f"{base}-{ep_num}/"
        
        episodes.append({
            'episode': ep_num,
            'url': new_url,
            'date_added': datetime.now().isoformat()
        })
    return episodes

# ===== استخراج سيرفرات المشاهدة من صفحة الحلقة =====
def extract_server_urls(episode_url):
    """استخراج روابط السيرفرات من صفحة الحلقة"""
    print(f"    🔗 جلب سيرفرات: {episode_url[:60]}...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = requests.get(episode_url, headers=headers, timeout=30)
        resp.encoding = 'utf-8'
    except:
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')
    servers = []

    # البحث عن iframe (المشغل)
    iframes = soup.find_all('iframe')
    for iframe in iframes:
        src = iframe.get('src')
        if src and src.startswith('http'):
            servers.append(src)

    # البحث عن عنصر video مباشر
    videos = soup.find_all('video')
    for video in videos:
        src = video.get('src')
        if src and src.startswith('http'):
            servers.append(src)
        # البحث عن مصادر داخل video
        sources = video.find_all('source')
        for source in sources:
            src = source.get('src')
            if src and src.startswith('http'):
                servers.append(src)

    # البحث عن روابط في النص
    text = soup.get_text()
    matches = re.findall(r'(https?://[^"\'\s]+\.(?:mp4|m3u8|webm)[^"\'\s]*)', text)
    servers.extend(matches)

    # إزالة التكرارات
    servers = list(dict.fromkeys(servers))
    print(f"    ✅ تم العثور على {len(servers)} سيرفر")
    return servers

# ===== الدالة الرئيسية =====
def main():
    print("🚀 بدء جلب البيانات من لاروزا...")
    os.makedirs("data", exist_ok=True)

    metadata_path = "data/metadata.json"
    if os.path.exists(metadata_path):
        with open(metadata_path, "r", encoding="utf-8") as f:
            all_data = json.load(f)
    else:
        all_data = {"series": {}, "last_update": None}

    series_list = get_all_series(SEARCH_URL)
    if not series_list:
        print("⚠️ لم يتم العثور على أي فيديو.")
        return

    updated_count = 0
    for series in series_list:
        name = series['name']
        url = series['url']
        cover = series.get('cover', '')

        if name in all_data["series"]:
            existing_episodes = {e['episode'] for e in all_data["series"][name].get('episodes', [])}
        else:
            existing_episodes = set()
            all_data["series"][name] = {"episodes": [], "cover": cover}

        all_data["series"][name]["cover"] = cover
        episode_numbers = get_episodes_for_series(url)

        new_episodes = [ep for ep in episode_numbers if ep not in existing_episodes]

        if new_episodes:
            print(f"  🆕 إضافة {len(new_episodes)} حلقة جديدة لـ {name}")
            new_ep_data = build_episode_data(name, url, new_episodes)
            # جلب السيرفرات لكل حلقة جديدة
            for ep in new_ep_data:
                servers = extract_server_urls(ep['url'])
                ep['servers'] = servers
            all_data["series"][name]["episodes"].extend(new_ep_data)
            updated_count += len(new_ep_data)

        all_data["series"][name]["url"] = url
        time.sleep(1)

    all_data["last_update"] = datetime.now().isoformat()

    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

    print(f"✅ تم تحديث {updated_count} حلقة جديدة")
    print(f"📂 إجمالي المسلسلات: {len(all_data['series'])}")

if __name__ == "__main__":
    main()
