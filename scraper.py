#!/usr/bin/env python3
"""
جلب قائمة المسلسلات التركية المدبلجة وحلقاتها من lodynet
باستخدام JSON-LD لاستخراج البيانات
"""
import os
import sys
import json
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import unquote
from datetime import datetime

# ===== قراءة الإعدادات =====
CONFIG_FILE = "config.json"
if not os.path.exists(CONFIG_FILE):
    print("❌ config.json غير موجود، سيتم استخدام الإعدادات الافتراضية")
    CONFIG = {
        "series_page": "https://lodynet.watch/dubbed-turkish-series-g/",
        "max_series": 50
    }
else:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        CONFIG = json.load(f)

SERIES_PAGE = CONFIG.get("series_page", "https://lodynet.watch/dubbed-turkish-series-g/")
MAX_SERIES = CONFIG.get("max_series", 50)

# ===== جلب جميع المسلسلات من صفحة التصنيف (باستخدام JSON-LD) =====
def get_all_series(url):
    """استخراج أسماء وروابط جميع المسلسلات من بيانات JSON-LD"""
    print(f"🔍 جلب المسلسلات من: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept-Language': 'ar-SA,ar;q=0.9'
    }
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.encoding = 'utf-8'
    except Exception as e:
        print(f"❌ فشل تحميل الصفحة: {e}")
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')

    # البحث عن كود JSON-LD (قد يكون في script type application/ld+json)
    script_tags = soup.find_all('script', type='application/ld+json')
    if not script_tags:
        print("❌ لم يتم العثور على بيانات JSON-LD")
        # محاولة بديلة: البحث عن روابط مباشرة في HTML
        return get_series_from_html(soup)

    series_list = []
    for script in script_tags:
        try:
            data = json.loads(script.string)
            # استخراج الروابط من البيانات
            extracted = extract_series_from_json(data)
            series_list.extend(extracted)
        except json.JSONDecodeError as e:
            print(f"⚠️ فشل تحليل JSON: {e}")
            continue

    # إزالة التكرارات
    seen = set()
    unique = []
    for s in series_list:
        key = s['url']
        if key not in seen:
            seen.add(key)
            unique.append(s)

    print(f"✅ تم العثور على {len(unique)} مسلسل")
    return unique[:MAX_SERIES]

# ===== استخراج المسلسلات من كائن JSON (تعاودي) =====
def extract_series_from_json(obj):
    """استخراج روابط التصنيفات من JSON بشكل تعاودي"""
    results = []
    if isinstance(obj, dict):
        # نبحث عن المفتاح "@id" الذي يحتوي على رابط category
        if '@id' in obj and isinstance(obj['@id'], str) and '/category/' in obj['@id']:
            url = obj['@id']
            # استخراج اسم المسلسل من الرابط
            name_match = re.search(r'/category/([^/]+)/?$', url)
            if name_match:
                name = name_match.group(1).replace('-', ' ').strip()
                name = unquote(name)  # فك ترميز النسبة المئوية
                # تنظيف الاسم
                name = re.sub(r'\s+', ' ', name).strip()
                results.append({'name': name, 'url': url})
        # البحث في القيم الأخرى
        for value in obj.values():
            results.extend(extract_series_from_json(value))
    elif isinstance(obj, list):
        for item in obj:
            results.extend(extract_series_from_json(item))
    return results

# ===== طريقة بديلة: استخراج المسلسلات من روابط HTML المباشرة =====
def get_series_from_html(soup):
    """استخراج المسلسلات من روابط HTML العادية (في حال عدم وجود JSON-LD)"""
    print("🔄 محاولة استخراج المسلسلات من HTML...")
    series_list = []
    for link in soup.find_all('a', href=True):
        href = link['href']
        if '/category/' in href and href.endswith('/'):
            # استبعاد روابط الصفحات (page)
            if 'page/' in href:
                continue
            title = link.get_text(strip=True)
            if title and any(k in title for k in ['مدبلج', 'مدبلجة', 'مسلسل']):
                if href.startswith('/'):
                    href = 'https://lodynet.watch' + href
                series_list.append({'name': title.strip(), 'url': href})
    # إزالة التكرارات
    seen = set()
    unique = []
    for s in series_list:
        if s['url'] not in seen:
            seen.add(s['url'])
            unique.append(s)
    return unique

# ===== جلب حلقات مسلسل معين من صفحة التصنيف =====
def get_episodes_for_series(series_url):
    """استخراج أرقام الحلقات من صفحة المسلسل"""
    print(f"  📂 جلب حلقات من: {series_url[:60]}...")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        resp = requests.get(series_url, headers=headers, timeout=30)
        resp.encoding = 'utf-8'
    except Exception as e:
        print(f"    ❌ فشل تحميل الصفحة: {e}")
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')
    episodes = []

    # الطريقة الأولى: البحث عن النص المباشر "حلقة رقم X"
    text = soup.get_text()
    pattern = r'(?:حلقة\s*رقم\s*|الحلقة\s*)(\d+)'
    matches = re.findall(pattern, text)
    for match in matches:
        ep_num = int(match)
        if ep_num not in episodes:
            episodes.append(ep_num)

    # الطريقة الثانية: البحث عن روابط تنتهي برقم (صفحات الحلقات)
    for link in soup.find_all('a', href=True):
        href = link['href']
        # نبحث عن روابط تحتوي على "-مد-" أو "-حلقة-" وتنتهي برقم
        if '-مد-' in href or '-حلقة-' in href:
            match = re.search(r'-(\d+)/?$', href)
            if match:
                ep_num = int(match.group(1))
                if ep_num not in episodes:
                    episodes.append(ep_num)

    episodes.sort()
    print(f"    ✅ تم العثور على {len(episodes)} حلقة")
    return episodes

# ===== بناء هيكل الحلقات مع روابط الصفحات =====
def build_episode_data(series_name, series_url, episode_numbers):
    """بناء بيانات الحلقات مع روابط صفحاتها"""
    episodes = []
    # استخراج الاسم الأساسي من رابط المسلسل
    series_slug = series_url.rstrip('/').split('/')[-1]
    if series_slug.startswith('category-'):
        series_slug = series_slug[9:]
    if series_slug.endswith('-مدب'):
        series_slug = series_slug[:-4]
    if series_slug.startswith('مسلسل-'):
        series_slug = series_slug[7:]

    for ep_num in episode_numbers:
        episode_url = f"https://lodynet.watch/{series_slug}-{ep_num}/"
        episodes.append({
            'episode': ep_num,
            'url': episode_url,
            'date_added': datetime.now().isoformat()
        })
    return episodes

# ===== الدالة الرئيسية =====
def main():
    print("🚀 بدء جلب الميتاداتا (بدون تحميل فيديو)...")

    # إنشاء مجلد البيانات
    os.makedirs("data", exist_ok=True)

    # تحميل البيانات الحالية إن وجدت
    metadata_path = "data/metadata.json"
    if os.path.exists(metadata_path):
        with open(metadata_path, "r", encoding="utf-8") as f:
            all_data = json.load(f)
    else:
        all_data = {"series": {}, "last_update": None}

    # جلب جميع المسلسلات
    series_list = get_all_series(SERIES_PAGE)

    if not series_list:
        print("⚠️ لم يتم العثور على أي مسلسل. تحقق من الرابط أو من هيكل الموقع.")
        # لا نعدل الملف الحالي
        return

    updated_count = 0
    for series in series_list:
        name = series['name']
        url = series['url']

        # التحقق مما إذا كان هذا المسلسل موجوداً بالفعل
        if name in all_data["series"]:
            existing_episodes = {e['episode'] for e in all_data["series"][name].get('episodes', [])}
        else:
            existing_episodes = set()
            all_data["series"][name] = {"episodes": []}

        # جلب حلقات المسلسل
        episode_numbers = get_episodes_for_series(url)

        # إضافة الحلقات الجديدة فقط
        new_episodes = [ep for ep in episode_numbers if ep not in existing_episodes]

        if new_episodes:
            print(f"  🆕 إضافة {len(new_episodes)} حلقة جديدة لـ {name}")
            new_ep_data = build_episode_data(name, url, new_episodes)
            all_data["series"][name]["episodes"].extend(new_ep_data)
            updated_count += len(new_episodes)

        # تحديث رابط المسلسل (قد يتغير)
        all_data["series"][name]["url"] = url

        # ننتظر قليلاً بين الطلبات لتجنب الحظر
        time.sleep(2)

    all_data["last_update"] = datetime.now().isoformat()

    # حفظ البيانات
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

    print(f"✅ تم تحديث {updated_count} حلقة جديدة")
    print(f"📂 إجمالي المسلسلات: {len(all_data['series'])}")

if __name__ == "__main__":
    main()
