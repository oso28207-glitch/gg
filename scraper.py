#!/usr/bin/env python3
"""
جلب قائمة المسلسلات التركية المدبلجة وحلقاتها من lodynet
باستخدام Selenium للتعامل مع المحتوى الديناميكي
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
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

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

# ===== إعداد متصفح Selenium =====
def setup_driver():
    """إعداد متصفح Chrome في وضع headless"""
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver
    except Exception as e:
        print(f"❌ فشل إعداد Selenium: {e}")
        return None

# ===== جلب جميع المسلسلات باستخدام Selenium =====
def get_all_series(url):
    """استخراج أسماء وروابط جميع المسلسلات من الصفحة الديناميكية"""
    print(f"🔍 جلب المسلسلات من: {url}")
    
    driver = setup_driver()
    if not driver:
        print("❌ فشل تهيئة المتصفح، جرب الطريقة البديلة (requests)")
        return get_series_from_requests(url)
    
    series_list = []
    try:
        driver.get(url)
        wait = WebDriverWait(driver, 15)
        items = wait.until(EC.presence_of_all_elements_located((By.CLASS_NAME, "ItemNewly")))
        
        print(f"✅ تم العثور على {len(items)} عنصر مسلسل")
        
        for item in items:
            try:
                link = item.find_element(By.TAG_NAME, "a")
                href = link.get_attribute("href")
                title = link.get_attribute("title") or link.text.strip()
                
                if href and title and '/category/' in href:
                    title = re.sub(r'\s+', ' ', title).strip()
                    series_list.append({
                        'name': title,
                        'url': href
                    })
            except Exception as e:
                print(f"⚠️ خطأ في معالجة عنصر: {e}")
                continue
                
    except Exception as e:
        print(f"❌ فشل في تحميل الصفحة أو العثور على العناصر: {e}")
        print("🔄 محاولة الجلب باستخدام requests...")
        return get_series_from_requests(url)
    finally:
        driver.quit()
    
    # إزالة التكرارات
    seen = set()
    unique = []
    for s in series_list:
        if s['url'] not in seen:
            seen.add(s['url'])
            unique.append(s)
    
    print(f"✅ تم العثور على {len(unique)} مسلسل")
    return unique[:MAX_SERIES]

# ===== طريقة بديلة: جلب المسلسلات باستخدام requests =====
def get_series_from_requests(url):
    """محاولة استخراج المسلسلات من HTML باستخدام requests"""
    print("📡 محاولة الجلب باستخدام requests...")
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
    series_list = []
    
    for link in soup.find_all('a', href=True):
        href = link['href']
        if '/category/' in href and 'page/' not in href:
            title = link.get('title') or link.text.strip()
            if title and any(k in title for k in ['مدبلج', 'مدبلجة', 'مسلسل']):
                if href.startswith('/'):
                    href = 'https://lodynet.watch' + href
                series_list.append({'name': title.strip(), 'url': href})
    
    seen = set()
    unique = []
    for s in series_list:
        if s['url'] not in seen:
            seen.add(s['url'])
            unique.append(s)
    
    return unique

# ===== جلب حلقات مسلسل معين باستخدام Selenium =====
def get_episodes_for_series(series_url):
    """استخراج أرقام الحلقات من صفحة المسلسل باستخدام Selenium"""
    print(f"  📂 جلب حلقات من: {series_url[:60]}...")
    
    driver = setup_driver()
    if not driver:
        print("    ❌ فشل تهيئة المتصفح")
        return []
    
    episodes = []
    try:
        driver.get(series_url)
        # انتظر حتى تظهر عناصر الحلقات (باستخدام الكلاس المناسب)
        wait = WebDriverWait(driver, 15)
        # نبحث عن أي عناصر قد تحتوي على أرقام حلقات
        # في الموقع، الحلقات تظهر كروابط داخل الصفحة
        # قد تكون داخل عناصر <a> تحتوي على "حلقة رقم X" أو في النص العادي
        
        # محاولة 1: البحث عن الروابط التي تحتوي على "-الحلقة-" أو "-مد-"
        links = driver.find_elements(By.XPATH, "//a[contains(@href, '-الحلقة-') or contains(@href, '-مد-')]")
        for link in links:
            href = link.get_attribute('href')
            if href:
                # استخراج رقم الحلقة من الرابط
                match = re.search(r'-(\d+)/?$', href)
                if match:
                    ep_num = int(match.group(1))
                    if ep_num not in episodes:
                        episodes.append(ep_num)
        
        # محاولة 2: البحث عن النص "حلقة رقم X" أو "الحلقة X" في الصفحة
        page_text = driver.find_element(By.TAG_NAME, "body").text
        pattern = r'(?:حلقة\s*رقم\s*|الحلقة\s*)(\d+)'
        matches = re.findall(pattern, page_text)
        for match in matches:
            ep_num = int(match)
            if ep_num not in episodes:
                episodes.append(ep_num)
        
        # إذا لم نجد شيئاً، قد يكون هناك عناصر مخصصة مثل div بالكلاس "ItemNewly" أو "episode"
        # لكننا سنكتفي بالطرق أعلاه
        
    except Exception as e:
        print(f"    ❌ فشل في تحميل صفحة المسلسل: {e}")
    finally:
        driver.quit()
    
    episodes.sort()
    print(f"    ✅ تم العثور على {len(episodes)} حلقة")
    return episodes

# ===== بناء هيكل الحلقات مع روابط الصفحات =====
def build_episode_data(series_name, series_url, episode_numbers):
    """
    بناء بيانات الحلقات مع روابط صفحاتها
    التنسيق الصحيح للرابط: /اسم-المسلسل-الحلقة-رقم/
    """
    episodes = []
    # استخراج الاسم الأساسي من رابط المسلسل
    series_slug = series_url.rstrip('/').split('/')[-1]
    
    # إزالة بادئة "category-" إن وجدت
    if series_slug.startswith('category-'):
        series_slug = series_slug[9:]
    
    # إزالة لاحقة "-مدب" إن وجدت
    if series_slug.endswith('-مدب'):
        series_slug = series_slug[:-4]
    
    # إزالة بادئة "مسلسل-" إن وجدت (لتجنب التكرار)
    if series_slug.startswith('مسلسل-'):
        series_slug = series_slug[7:]
    
    for ep_num in episode_numbers:
        episode_url = f"https://lodynet.watch/{series_slug}-الحلقة-{ep_num}/"
        episodes.append({
            'episode': ep_num,
            'url': episode_url,
            'date_added': datetime.now().isoformat()
        })
    return episodes

# ===== الدالة الرئيسية =====
def main():
    print("🚀 بدء جلب الميتاداتا (باستخدام Selenium)...")
    
    os.makedirs("data", exist_ok=True)
    
    metadata_path = "data/metadata.json"
    if os.path.exists(metadata_path):
        with open(metadata_path, "r", encoding="utf-8") as f:
            all_data = json.load(f)
    else:
        all_data = {"series": {}, "last_update": None}
    
    series_list = get_all_series(SERIES_PAGE)
    
    if not series_list:
        print("⚠️ لم يتم العثور على أي مسلسل. تحقق من الرابط أو من هيكل الموقع.")
        return
    
    updated_count = 0
    for series in series_list:
        name = series['name']
        url = series['url']
        
        if name in all_data["series"]:
            existing_episodes = {e['episode'] for e in all_data["series"][name].get('episodes', [])}
        else:
            existing_episodes = set()
            all_data["series"][name] = {"episodes": []}
        
        episode_numbers = get_episodes_for_series(url)
        
        new_episodes = [ep for ep in episode_numbers if ep not in existing_episodes]
        
        if new_episodes:
            print(f"  🆕 إضافة {len(new_episodes)} حلقة جديدة لـ {name}")
            new_ep_data = build_episode_data(name, url, new_episodes)
            all_data["series"][name]["episodes"].extend(new_ep_data)
            updated_count += len(new_episodes)
        
        all_data["series"][name]["url"] = url
        
        time.sleep(2)
    
    all_data["last_update"] = datetime.now().isoformat()
    
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ تم تحديث {updated_count} حلقة جديدة")
    print(f"📂 إجمالي المسلسلات: {len(all_data['series'])}")

if __name__ == "__main__":
    main()
