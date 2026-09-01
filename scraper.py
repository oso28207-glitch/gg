#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
سكربت جلب المسلسلات التركية المدبلجة من مصادر متعددة
(معدل لدعم موقع قصة عشق مع استخراج روابط embed والسيرفرات)
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
    if 'laaroza.mom' in url:
        return 'laaroza'
    elif 'aa.3ick.net' in url or '3isk' in url:
        return '3ick'
    else:
        return 'other'

# ===== جلب قائمة المسلسلات من مصدر =====
def get_all_series_from_source(url):
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
            img = link.find('img', class_='item_img')
            cover = img.get('src') if img else ''
            if title and href:
                series_list.append({
                    'name': title.strip(),
                    'url': urljoin(url, href),
                    'cover': cover
                })
    else:
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
    domain_type = get_domain_from_url(series_url)

    if domain_type == '3ick':
        eps_container = soup.find('div', class_='season-eps')
        if eps_container:
            for a in eps_container.find_all('a', class_='ep-num'):
                href = a.get('href')
                if not href:
                    continue
                ep_num = a.get('data-ep-num')
                if not ep_num:
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
        text = soup.get_text()
        pattern = r'(?:حلقة\s*رقم\s*|الحلقة\s*)(\d+)'
        matches = re.findall(pattern, text)
        for match in matches:
            ep_num = int(match)
            if re.search(r'-(\d+)/?$', series_url):
                new_url = re.sub(r'-(\d+)/?$', f'-{ep_num}/', series_url)
            else:
                base = series_url.rstrip('/')
                new_url = f"{base}-{ep_num}/"
            episodes.append((ep_num, new_url))

    seen_nums = set()
    unique_eps = []
    for ep_num, url in episodes:
        if ep_num not in seen_nums:
            seen_nums.add(ep_num)
            unique_eps.append((ep_num, url))

    unique_eps.sort(key=lambda x: x[0])
    print(f"    ✅ تم العثور على {len(unique_eps)} حلقة")
    return unique_eps

# ===== بناء بيانات الحلقات =====
def build_episode_data(series_name, episodes_with_urls):
    episodes = []
    for ep_num, ep_url in episodes_with_urls:
        episodes.append({
            'episode': ep_num,
            'url': ep_url,
            'date_added': datetime.now().isoformat()
        })
    return episodes

# ===== استخراج سيرفرات المشاهدة (معدل) =====
def extract_server_urls(episode_url):
    print(f"    🔗 جلب سيرفرات: {episode_url[:60]}...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': episode_url,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ar-EG,ar;q=0.9,en;q=0.8',
        'Connection': 'keep-alive',
    }
    session = requests.Session()
    servers = []

    try:
        resp = session.get(episode_url, headers=headers, timeout=30)
        resp.encoding = 'utf-8'
    except Exception as e:
        print(f"    ❌ فشل تحميل الصفحة: {e}")
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')

    # البحث عن iframe داخل حاوية المشغل
    player_viewer = soup.find('div', id='player_viewer') or soup.find('div', class_='player-viewer')
    if player_viewer:
        iframe = player_viewer.find('iframe', src=True)
        if iframe:
            src = iframe.get('src')
            if src and src.startswith('http'):
                servers.append(src)
                print(f"    ✅ تم العثور على iframe في الصفحة الحالية: {src}")
    else:
        # البحث عن أي iframe في الصفحة
        for iframe in soup.find_all('iframe', src=True):
            src = iframe.get('src')
            if src and src.startswith('http'):
                servers.append(src)
                print(f"    ✅ تم العثور على iframe في الصفحة الحالية: {src}")
                break

    # إذا لم نجد، نحاول البحث في صفحة /see/ إن وجدت
    if not servers:
        watch_btn = soup.find('a', class_='single-watch-btn')
        if watch_btn:
            see_url = watch_btn.get('href')
            if see_url and '/see/' in see_url:
                full_see_url = urljoin(episode_url, see_url)
                print(f"    🔍 جلب صفحة المشاهدة: {full_see_url}")
                try:
                    see_resp = session.get(full_see_url, headers=headers, timeout=30)
                    see_resp.encoding = 'utf-8'
                    see_soup = BeautifulSoup(see_resp.text, 'html.parser')
                    player_viewer = see_soup.find('div', id='player_viewer') or see_soup.find('div', class_='player-viewer')
                    if player_viewer:
                        iframe = player_viewer.find('iframe', src=True)
                        if iframe:
                            src = iframe.get('src')
                            if src and src.startswith('http'):
                                servers.append(src)
                                print(f"    ✅ تم العثور على iframe في صفحة المشاهدة: {src}")
                except Exception as e:
                    print(f"    ⚠️ فشل جلب صفحة المشاهدة: {e}")

    # إذا لم نجد أي سيرفر، نضيف رابط الحلقة نفسه كاحتياطي
    if not servers:
        print(f"    💡 لم يتم العثور على سيرفرات، سنستخدم رابط الحلقة نفسه للتحميل عبر yt-dlp")
        servers.append(episode_url)

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

    all_series = []
    for source in SEARCH_SOURCES:
        series_from_source = get_all_series_from_source(source)
        for s in series_from_source:
            if not any(existing['url'] == s['url'] for existing in all_series):
                all_series.append(s)

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

        episodes_with_urls = get_episodes_for_series(url)
        if not episodes_with_urls:
            print(f"  ⚠️ لم يتم العثور على حلقات لـ {name}")
            continue

        new_episodes = [(ep_num, ep_url) for ep_num, ep_url in episodes_with_urls if ep_num not in existing_episodes]

        if new_episodes:
            print(f"  🆕 إضافة {len(new_episodes)} حلقة جديدة لـ {name}")
            new_ep_data = build_episode_data(name, new_episodes)
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
