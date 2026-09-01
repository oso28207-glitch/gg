#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
سكربت جلب المسلسلات التركية المدبلجة من مصادر متعددة
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
        "search_sources": [
            "https://laaroza.mom/search.php?keywords=%D9%85%D8%AF%D8%A8%D9%84%D8%AC%D8%A9&video-id="
        ],
        "max_series": 50
    }
else:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        CONFIG = json.load(f)

SEARCH_SOURCES = CONFIG.get("search_sources", [])
MAX_SERIES = CONFIG.get("max_series", 50)

# ===== جلب قائمة الفيديوهات من مصدر =====
def get_all_series_from_source(url):
    """استخراج قائمة الفيديوهات من صفحة بحث معينة"""
    print(f"🔍 جلب من: {url}")
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

    # البحث عن روابط الفيديوهات (قد تختلف حسب الموقع)
    for link in soup.find_all('a', href=True):
        href = link['href']
        if '/video/' in href or '/watch/' in href or '/embed/' in href:
            title = link.get_text(strip=True) or link.get('title', '')
            # تصفية للتركي المدبلج (يمكن تعديل الكلمات)
            if title and any(k in title for k in ['مدبلج', 'مدبلجة', 'تركي', 'تركية']):
                full_url = urljoin(url, href)
                series_list.append({
                    'name': title.strip(),
                    'url': full_url,
                    'cover': ''  # قد تتوفر صور لاحقاً
                })

    # إزالة التكرارات
    seen = set()
    unique = []
    for s in series_list:
        if s['url'] not in seen:
            seen.add(s['url'])
            unique.append(s)

    print(f"✅ تم العثور على {len(unique)} فيديو/مسلسل من هذا المصدر")
    return unique[:MAX_SERIES]

# ===== جلب حلقات مسلسل =====
def get_episodes_for_series(series_url):
    """استخراج أرقام الحلقات من صفحة المسلسل"""
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

    # محاولة استخراج أرقام الحلقات من النص
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
    """بناء قائمة الحلقات مع روابط صفحاتها"""
    episodes = []
    for ep_num in episode_numbers:
        # بناء رابط الحلقة (افتراضي)
        if re.search(r'-(\d+)/?$', series_url):
            new_url = re.sub(r'-(\d+)/?$', f'-{ep_num}/', series_url)
        else:
            base = series_url.rstrip('/')
            new_url = f"{base}-{ep_num}/"
        episodes.append({
            'episode': ep_num,
            'url': new_url,
            'date_added': datetime.now().isoformat()
        })
    return episodes

# ===== استخراج سيرفرات المشاهدة =====
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
    print("🚀 بدء جلب البيانات من المصادر...")
    os.makedirs("data", exist_ok=True)

    metadata_path = "data/metadata.json"
    if os.path.exists(metadata_path):
        with open(metadata_path, "r", encoding="utf-8") as f:
            all_data = json.load(f)
    else:
        all_data = {"series": {}, "last_update": None}

    updated_count = 0

    # جلب المسلسلات من كل مصدر
    all_series = []
    for source in SEARCH_SOURCES:
        series_from_source = get_all_series_from_source(source)
        for s in series_from_source:
            # تجنب التكرار بناءً على الاسم أو الرابط
            if not any(existing['url'] == s['url'] for existing in all_series):
                all_series.append(s)

    # الآن نقوم بمعالجة كل مسلسل
    for series in all_series:
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
        time.sleep(1)  # تجنب الحظر

    all_data["last_update"] = datetime.now().isoformat()

    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

    print(f"✅ تم تحديث {updated_count} حلقة جديدة")
    print(f"📂 إجمالي المسلسلات: {len(all_data['series'])}")

if __name__ == "__main__":
    main()
