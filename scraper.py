#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
سكربت جلب المسلسلات التركية المدبلجة من مصادر متعددة
(معدل لدعم موقع قصة عشق 3ick.net مع استخراج روابط السيرفرات من صفحة /see/)
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
            "https://laaroza.mom/search.php?keywords=%D9%85%D8%AF%D8%A8%D9%84%D8%AC%D8%A9&video-id=",
            "https://aa.3ick.net/genre/series-mudablij-121/"
        ],
        "max_series": 50
    }
else:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        CONFIG = json.load(f)

SEARCH_SOURCES = CONFIG.get("search_sources", [])
MAX_SERIES = CONFIG.get("max_series", 50)

# ===== دوال مساعدة =====
def get_domain_from_url(url):
    """استخراج النطاق الأساسي من الرابط لتحديد نوع الموقع"""
    if 'laaroza.mom' in url:
        return 'laaroza'
    elif 'aa.3ick.net' in url or '3isk' in url:
        return '3ick'
    else:
        return 'other'

# ===== جلب قائمة المسلسلات من مصدر =====
def get_all_series_from_source(url):
    """استخراج قائمة المسلسلات من صفحة بحث أو تصنيف معينة"""
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
    domain_type = get_domain_from_url(url)

    if domain_type == 'laaroza':
        # منطق لاروزا (الحالي)
        for link in soup.find_all('a', href=True):
            href = link['href']
            if '/video/' in href or '/watch/' in href or '/embed/' in href:
                title = link.get_text(strip=True) or link.get('title', '')
                if title and any(k in title for k in ['مدبلج', 'مدبلجة', 'تركي', 'تركية']):
                    full_url = urljoin(url, href)
                    series_list.append({
                        'name': title.strip(),
                        'url': full_url,
                        'cover': ''
                    })
    elif domain_type == '3ick':
        # منطق قصة عشق (aa.3ick.net)
        # نبحث عن عناصر المسلسلات داخل .type_item_box
        items = soup.find_all('li', class_='type_item_box')
        for item in items:
            link = item.find('a', class_='type_item')
            if not link:
                continue
            href = link.get('href')
            if not href:
                continue
            title_elem = link.find('div', class_='item_title')
            title = title_elem.get_text(strip=True) if title_elem else ''
            # استخراج الصورة (اختياري)
            img = link.find('img', class_='item_img')
            cover = img.get('src') if img else ''
            if title and href:
                series_list.append({
                    'name': title.strip(),
                    'url': urljoin(url, href),
                    'cover': cover
                })
    else:
        # محاولة عامة (البحث عن روابط video)
        for link in soup.find_all('a', href=True):
            href = link['href']
            if '/video/' in href or '/watch/' in href or '/embed/' in href:
                title = link.get_text(strip=True) or link.get('title', '')
                if title:
                    full_url = urljoin(url, href)
                    series_list.append({
                        'name': title.strip(),
                        'url': full_url,
                        'cover': ''
                    })

    # إزالة التكرارات
    seen = set()
    unique = []
    for s in series_list:
        if s['url'] not in seen:
            seen.add(s['url'])
            unique.append(s)

    print(f"✅ تم العثور على {len(unique)} مسلسل/فيديو من هذا المصدر")
    return unique[:MAX_SERIES]

# ===== جلب حلقات مسلسل =====
def get_episodes_for_series(series_url):
    """
    استخراج أرقام الحلقات وروابطها من صفحة المسلسل.
    تُرجع قائمة من tuples: (episode_number, episode_url)
    """
    print(f"  📂 جلب حلقات من: {series_url[:60]}...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = requests.get(series_url, headers=headers, timeout=30)
        resp.encoding = 'utf-8'
    except Exception as e:
        print(f"    ❌ فشل تحميل الصفحة: {e}")
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')
    episodes = []  # قائمة (رقم, رابط)

    domain_type = get_domain_from_url(series_url)

    if domain_type == '3ick':
        # نبحث عن روابط الحلقات داخل .season-eps
        eps_container = soup.find('div', class_='season-eps')
        if eps_container:
            for a in eps_container.find_all('a', class_='ep-num'):
                href = a.get('href')
                if not href:
                    continue
                # استخراج رقم الحلقة من data-ep-num أو من النص
                ep_num = a.get('data-ep-num')
                if not ep_num:
                    # محاولة استخراج من النص
                    text = a.get_text(strip=True)
                    match = re.search(r'(\d+)', text)
                    if match:
                        ep_num = match.group(1)
                if ep_num:
                    try:
                        ep_num = int(ep_num)
                    except:
                        continue
                    full_url = urljoin(series_url, href)
                    episodes.append((ep_num, full_url))
        else:
            # محاولة البحث عن أي روابط تحتوي على /watch/episodes/
            for a in soup.find_all('a', href=True):
                href = a['href']
                if '/watch/episodes/' in href:
                    ep_num = a.get('data-ep-num') or re.search(r'episode-(\d+)', href)
                    if ep_num:
                        try:
                            if isinstance(ep_num, re.Match):
                                ep_num = int(ep_num.group(1))
                            else:
                                ep_num = int(ep_num)
                        except:
                            continue
                        full_url = urljoin(series_url, href)
                        episodes.append((ep_num, full_url))
    else:
        # المنطق القديم (لاروزا وغيره) - استخراج الأرقام وبناء الروابط
        text = soup.get_text()
        pattern = r'(?:حلقة\s*رقم\s*|الحلقة\s*)(\d+)'
        matches = re.findall(pattern, text)
        for match in matches:
            ep_num = int(match)
            # بناء رابط (كما كان)
            if re.search(r'-(\d+)/?$', series_url):
                new_url = re.sub(r'-(\d+)/?$', f'-{ep_num}/', series_url)
            else:
                base = series_url.rstrip('/')
                new_url = f"{base}-{ep_num}/"
            episodes.append((ep_num, new_url))

    # إزالة التكرارات حسب الرقم
    seen_nums = set()
    unique_eps = []
    for ep_num, url in episodes:
        if ep_num not in seen_nums:
            seen_nums.add(ep_num)
            unique_eps.append((ep_num, url))

    unique_eps.sort(key=lambda x: x[0])
    print(f"    ✅ تم العثور على {len(unique_eps)} حلقة")
    return unique_eps

# ===== بناء بيانات الحلقات (باستخدام الروابط المستخرجة) =====
def build_episode_data(series_name, episodes_with_urls):
    """
    episodes_with_urls: list of (episode_number, episode_url)
    """
    episodes = []
    for ep_num, ep_url in episodes_with_urls:
        episodes.append({
            'episode': ep_num,
            'url': ep_url,
            'date_added': datetime.now().isoformat()
        })
    return episodes

# ===== استخراج سيرفرات المشاهدة (معدل لدعم قصة عشق) =====
def extract_server_urls(episode_url):
    """
    استخراج روابط السيرفرات من صفحة الحلقة.
    - إذا كان الموقع من نوع قصة عشق، يتم جلب صفحة /see/ واستخراج iframe.
    - وإلا، يتم البحث عن iframe و video و روابط مباشرة في الصفحة الحالية.
    """
    print(f"    🔗 جلب سيرفرات: {episode_url[:60]}...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    servers = []

    # 1. جلب الصفحة الحالية
    try:
        resp = requests.get(episode_url, headers=headers, timeout=30)
        resp.encoding = 'utf-8'
    except Exception as e:
        print(f"    ❌ فشل تحميل الصفحة: {e}")
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')

    # 2. البحث عن زر "مشاهدة الحلقة" (خاص بموقع قصة عشق)
    watch_btn = soup.find('a', class_='single-watch-btn')
    if watch_btn:
        see_url = watch_btn.get('href')
        if see_url and '/see/' in see_url:
            full_see_url = urljoin(episode_url, see_url)
            print(f"    🔍 جلب صفحة المشاهدة: {full_see_url}")
            try:
                see_resp = requests.get(full_see_url, headers=headers, timeout=30)
                see_resp.encoding = 'utf-8'
                see_soup = BeautifulSoup(see_resp.text, 'html.parser')

                # البحث عن iframe داخل حاوية المشغل
                iframe = see_soup.find('iframe', src=True)
                if iframe:
                    src = iframe.get('src')
                    if src and src.startswith('http'):
                        servers.append(src)
                        print(f"    ✅ تم العثور على iframe: {src}")
                else:
                    # البحث عن أي iframe في الصفحة
                    for iframe in see_soup.find_all('iframe', src=True):
                        src = iframe.get('src')
                        if src and src.startswith('http'):
                            servers.append(src)
                            print(f"    ✅ تم العثور على iframe: {src}")
                            break
            except Exception as e:
                print(f"    ⚠️ فشل جلب صفحة المشاهدة: {e}")

    # 3. إذا لم نجد iframe، نبحث في الصفحة الحالية (طريقة قديمة)
    if not servers:
        # البحث عن iframe
        for iframe in soup.find_all('iframe', src=True):
            src = iframe.get('src')
            if src and src.startswith('http'):
                servers.append(src)

        # البحث عن عناصر video
        for video in soup.find_all('video'):
            src = video.get('src')
            if src and src.startswith('http'):
                servers.append(src)
            for source in video.find_all('source'):
                src = source.get('src')
                if src and src.startswith('http'):
                    servers.append(src)

        # البحث عن روابط مباشرة في النص
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
            if not any(existing['url'] == s['url'] for existing in all_series):
                all_series.append(s)

    # معالجة كل مسلسل
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

        # جلب الحلقات مع روابطها
        episodes_with_urls = get_episodes_for_series(url)
        if not episodes_with_urls:
            print(f"  ⚠️ لم يتم العثور على حلقات لـ {name}")
            continue

        # تصفية الحلقات الجديدة (غير الموجودة)
        new_episodes = [(ep_num, ep_url) for ep_num, ep_url in episodes_with_urls if ep_num not in existing_episodes]

        if new_episodes:
            print(f"  🆕 إضافة {len(new_episodes)} حلقة جديدة لـ {name}")
            new_ep_data = build_episode_data(name, new_episodes)
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
