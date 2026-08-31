#!/usr/bin/env python3
"""
جلب قائمة المسلسلات التركية المدبلجة وحلقاتها من lodynet
بدون تحميل أي فيديو - فقط بيانات (ميتاداتا)
"""
import os
import sys
import json
import re
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# ===== قراءة الإعدادات =====
with open("config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

SERIES_PAGE = CONFIG.get("series_page", "https://lodynet.watch/dubbed-turkish-series-g/")
MAX_SERIES = CONFIG.get("max_series", 50)  # حد أقصى للمسلسلات لجمعها

# ===== جلب جميع المسلسلات من صفحة التصنيف =====
def get_all_series(url):
    """استخراج أسماء وروابط جميع المسلسلات من صفحة التصنيف"""
    print(f"🔍 جلب المسلسلات من: {url}")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.encoding = 'utf-8'
    except Exception as e:
        print(f"❌ فشل تحميل الصفحة: {e}")
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')
    series_list = []

    # البحث عن روابط التصنيفات (category) التي تحوي أسماء المسلسلات
    for link in soup.find_all('a', href=True):
        href = link['href']
        # نبحث عن روابط بصيغة /category/اسم-المسلسل-مدب/
        if '/category/' in href and href.endswith('/'):
            # نستثني روابط التصنيفات العامة
            if 'page/' in href or 'category/%' in href:
                continue
            title = link.get_text(strip=True)
            if title and any(k in title for k in ['مدبلج', 'مدبلجة', 'مسلسل']):
                # نكمل الرابط إذا كان نسبياً
                if href.startswith('/'):
                    href = 'https://lodynet.watch' + href
                series_list.append({
                    'name': title,
                    'url': href
                })

    # إزالة التكرارات
    seen = set()
    unique = []
    for s in series_list:
        if s['url'] not in seen:
            seen.add(s['url'])
            unique.append(s)

    print(f"✅ تم العثور على {len(unique)} مسلسل")
    return unique[:MAX_SERIES]

# ===== جلب حلقات مسلسل معين من صفحة التصنيف =====
def get_episodes_for_series(series_url):
    """استخراج أرقام الحلقات من صفحة المسلسل"""
    print(f"  📂 جلب حلقات من: {series_url[:60]}...")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        resp = requests.get(series_url, headers=headers, timeout=30)
        resp.encoding = 'utf-8'
    except:
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')
    episodes = []

    # البحث عن النص "حلقة رقم X" أو "الحلقة X"
    # في صفحة التصنيف، تظهر الحلقات كنص عادي
    text = soup.get_text()
    # نمط للبحث عن أرقام الحلقات
    pattern = r'(?:حلقة\s*رقم\s*|الحلقة\s*)(\d+)'
    matches = re.findall(pattern, text)
    for match in matches:
        ep_num = int(match)
        if ep_num not in episodes:
            episodes.append(ep_num)

    # إذا لم نجد بالطريقة السابقة، نبحث عن روابط داخل الصفحة
    if not episodes:
        for link in soup.find_all('a', href=True):
            href = link['href']
            # نبحث عن روابط تنتهي برقم (صفحات الحلقات)
            # مثال: /مسلسل-منتصف-الليل-في-قصر-بيرا-بالاس-مد-8/
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
    for ep_num in episode_numbers:
        # بناء رابط صفحة الحلقة
        # نأخذ الاسم من الرابط ونضيف رقم الحلقة
        # مثال: /category/مسلسل-منتصف-الليل-في-قصر-بيرا-بالاس-مدب/
        # تصبح: /مسلسل-منتصف-الليل-في-قصر-بيرا-بالاس-مد-8/
        series_slug = series_url.rstrip('/').split('/')[-1]
        # نزيل "category" من البداية إن وجدت
        if series_slug.startswith('category-'):
            series_slug = series_slug[9:]
        # نزيل "-مدب" من النهاية إن وجدت
        if series_slug.endswith('-مدب'):
            series_slug = series_slug[:-4]
        # نزيل "مسلسل-" من البداية إن وجدت (لأنها قد تتكرر)
        if series_slug.startswith('مسلسل-'):
            series_slug = series_slug[7:]

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

    # تحميل البيانات الحالية إن وجدت
    try:
        with open("data/metadata.json", "r", encoding="utf-8") as f:
            all_data = json.load(f)
    except:
        all_data = {"series": {}, "last_update": None}

    # جلب جميع المسلسلات
    series_list = get_all_series(SERIES_PAGE)

    updated_count = 0
    for series in series_list:
        name = series['name']
        url = series['url']

        # التحقق مما إذا كان هذا المسلسل موجوداً بالفعل
        if name in all_data["series"]:
            # نتحقق من وجود حلقات جديدة
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

        # ننتظر قليلاً بين الطلبات
        time.sleep(2)

    all_data["last_update"] = datetime.now().isoformat()

    # حفظ البيانات
    os.makedirs("data", exist_ok=True)
    with open("data/metadata.json", "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

    print(f"✅ تم تحديث {updated_count} حلقة جديدة")
    print(f"📂 إجمالي المسلسلات: {len(all_data['series'])}")

if __name__ == "__main__":
    main()
