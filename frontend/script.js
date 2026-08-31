const METADATA_URL = 'https://raw.githubusercontent.com/oso28207-glitch/gg/main/data/metadata.json';

// ===== جلب البيانات =====
async function fetchData() {
    try {
        const res = await fetch(METADATA_URL);
        return await res.json();
    } catch {
        return { series: {} };
    }
}

// ===== عرض المسلسلات والحلقات =====
function renderSeries(data) {
    const app = document.getElementById('app');
    app.innerHTML = '';
    const seriesNames = Object.keys(data.series);

    if (seriesNames.length === 0) {
        app.innerHTML = '<div class="loading">📭 لا توجد بيانات حالياً. انتظر التحديث التلقائي.</div>';
        return;
    }

    // ترتيب المسلسلات حسب تاريخ آخر تحديث (الأحدث أولاً)
    // نعرض المسلسلات التي لها حلقات فقط
    const sorted = seriesNames
        .filter(name => data.series[name].episodes?.length > 0)
        .sort((a, b) => {
            const epsA = data.series[a].episodes;
            const epsB = data.series[b].episodes;
            const lastA = epsA[epsA.length - 1]?.date_added || '';
            const lastB = epsB[epsB.length - 1]?.date_added || '';
            return lastB.localeCompare(lastA);
        });

    for (const name of sorted) {
        const episodes = data.series[name].episodes;
        // ترتيب الحلقات تنازلياً (الأحدث أولاً)
        const sortedEps = [...episodes].sort((a, b) => b.episode - a.episode);

        const card = document.createElement('div');
        card.className = 'series-card';

        const title = document.createElement('div');
        title.className = 'series-title';
        title.textContent = name;
        card.appendChild(title);

        const grid = document.createElement('div');
        grid.className = 'episode-grid';

        for (const ep of sortedEps) {
            const btn = document.createElement('button');
            btn.className = 'episode-btn';
            btn.textContent = `🎬 حلقة ${ep.episode}`;
            btn.dataset.episodeUrl = ep.url;
            btn.dataset.seriesName = name;
            btn.dataset.episodeNum = ep.episode;
            btn.onclick = () => handleEpisodeClick(btn);
            grid.appendChild(btn);
        }
        card.appendChild(grid);
        app.appendChild(card);
    }
}

// ===== معالجة الضغط عند الطلب =====
async function handleEpisodeClick(btn) {
    const episodeUrl = btn.dataset.episodeUrl;
    const seriesName = btn.dataset.seriesName;
    const episodeNum = btn.dataset.episodeNum;

    // منع الضغط المتكرر
    if (btn.classList.contains('loading')) return;

    // تغيير حالة الزر
    btn.textContent = '⏳ جاري التحميل...';
    btn.classList.add('loading');

    try {
        // 1. طلب تحميل وضغط الفيديو من السيرفر (GitHub Actions أو خدمة خارجية)
        //    سنستخدم GitHub Actions كـ "سيرفر" عبر تشغيل Workflow يدوياً أو عبر webhook
        //    لكن GitHub Actions لا يمكن تشغيلها مباشرة من المتصفح.
        //    لذا سنستخدم حلاً بديلاً: نطلب من المستخدم الانتظار، ونجهز الفيديو مسبقاً.
        
        // === الحل المؤقت: نعرض رسالة ونفتح صفحة الحلقة الأصلية ===
        // (يمكن استبدال هذا لاحقاً باستدعاء API حقيقي)
        btn.textContent = '🔄 جاري الضغط... قد يستغرق دقائق';
        
        // محاكاة طلب الضغط (في الواقع ستستدعي API هنا)
        // نفتح صفحة الحلقة في إطار خفي لاستخراج الرابط المباشر
        const videoUrl = await fetchAndCompress(episodeUrl, seriesName, episodeNum);
        
        if (videoUrl) {
            btn.textContent = '▶️ مشاهدة';
            btn.classList.remove('loading');
            btn.classList.add('done');
            playVideo(videoUrl, `${seriesName} - حلقة ${episodeNum}`);
        } else {
            btn.textContent = '❌ فشل';
            btn.classList.remove('loading');
        }
    } catch (err) {
        console.error(err);
        btn.textContent = '❌ خطأ';
        btn.classList.remove('loading');
    }
}

// ===== دالة تجلب الفيديو وتضغطه (محاكاة) =====
async function fetchAndCompress(episodeUrl, seriesName, episodeNum) {
    // في التطبيق الحقيقي، هنا ستستدعي خدمة خارجية (مثل AWS Lambda أو Cloudflare Worker)
    // تقوم بتحميل الفيديو من lodynet وضغطه وإرجاع رابط الفيديو المضغوط.
    
    // الحل البديل: استخدام proxy لتحميل الفيديو مباشرة في المتصفح باستخدام ffmpeg.wasm
    // لكن هذا سيكون بطيئاً ومكثفاً على المتصفح.
    
    // للتوضيح: نعيد رابط تجريبي
    // في الإصدار النهائي، ستستدعي API حقيقي
    console.log(`طلب ضغط: ${seriesName} - حلقة ${episodeNum} من ${episodeUrl}`);
    
    // محاكاة تأخير
    await new Promise(resolve => setTimeout(resolve, 3000));
    
    // نعيد رابط فيديو تجريبي (في الحقيقة ستجلب الرابط من السيرفر)
    // يمكنك استخدام https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4
    return 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4';
}

// ===== تشغيل الفيديو =====
function playVideo(url, title) {
    const oldContainer = document.querySelector('.video-container');
    if (oldContainer) oldContainer.remove();

    const container = document.createElement('div');
    container.className = 'video-container active';
    container.innerHTML = `
        <h3 style="padding:15px; background:#111; margin:0;">▶️ ${title}</h3>
        <video controls autoplay>
            <source src="${url}" type="video/mp4">
            متصفحك لا يدعم تشغيل الفيديو.
        </video>
    `;
    document.getElementById('app').appendChild(container);
    container.scrollIntoView({ behavior: 'smooth' });
}

// ===== التحميل والعرض =====
fetchData().then(renderSeries);
