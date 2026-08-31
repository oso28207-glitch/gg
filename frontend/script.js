// ===== الإعدادات =====
const METADATA_URL = 'https://raw.githubusercontent.com/YourUsername/YourRepoName/main/data/metadata.json';
let currentSeries = null; // اسم المسلسل الحالي (في صفحة الحلقات)

// ===== قراءة المعامل من الرابط (لصفحة الحلقات) =====
function getQueryParam(param) {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get(param);
}

// ===== جلب البيانات =====
async function fetchData() {
    try {
        const res = await fetch(METADATA_URL);
        return await res.json();
    } catch {
        return { series: {} };
    }
}

// ===== عرض المسلسلات في الصفحة الرئيسية =====
async function renderHome() {
    const app = document.getElementById('app');
    const data = await fetchData();
    const seriesNames = Object.keys(data.series).filter(name => data.series[name].episodes?.length > 0);
    
    if (seriesNames.length === 0) {
        app.innerHTML = '<div class="loading">📭 لا توجد مسلسلات حالياً.</div>';
        return;
    }

    app.innerHTML = '';
    for (const name of seriesNames) {
        const series = data.series[name];
        const cover = series.cover || '';
        const epCount = series.episodes.length;
        
        const card = document.createElement('div');
        card.className = 'series-card';
        card.onclick = () => {
            window.location.href = `series.html?name=${encodeURIComponent(name)}`;
        };
        
        card.innerHTML = `
            ${cover ? `<img src="${cover}" alt="${name}" loading="lazy">` : ''}
            <div class="info">
                <h3>${name}</h3>
                <p>${epCount} حلقة</p>
            </div>
        `;
        app.appendChild(card);
    }
}

// ===== عرض حلقات مسلسل معين (صفحة الحلقات) =====
async function renderSeries() {
    const seriesName = getQueryParam('name');
    if (!seriesName) {
        document.getElementById('app').innerHTML = '<div class="loading">⚠️ لم يتم تحديد مسلسل.</div>';
        return;
    }

    const data = await fetchData();
    const series = data.series[seriesName];
    if (!series || !series.episodes || series.episodes.length === 0) {
        document.getElementById('app').innerHTML = '<div class="loading">📭 لا توجد حلقات لهذا المسلسل.</div>';
        return;
    }

    document.getElementById('seriesTitle').textContent = seriesName;
    const app = document.getElementById('app');
    app.innerHTML = '';

    // ترتيب الحلقات تنازلياً (الأحدث أولاً)
    const episodes = [...series.episodes].sort((a, b) => b.episode - a.episode);
    const grid = document.createElement('div');
    grid.className = 'episode-grid';

    for (const ep of episodes) {
        const btn = document.createElement('button');
        btn.className = 'episode-btn';
        btn.textContent = `🎬 حلقة ${ep.episode}`;
        btn.dataset.episodeUrl = ep.url;
        btn.dataset.seriesName = seriesName;
        btn.dataset.episodeNum = ep.episode;
        btn.dataset.servers = JSON.stringify(ep.servers || []);
        btn.onclick = () => handleEpisodeClick(btn);
        grid.appendChild(btn);
    }
    app.appendChild(grid);
}

// ===== معالجة الضغط والعرض =====
async function handleEpisodeClick(btn) {
    if (btn.classList.contains('loading')) return;
    const servers = JSON.parse(btn.dataset.servers);
    if (!servers || servers.length === 0) {
        alert('لا توجد سيرفرات لهذه الحلقة. انتظر التحديث التالي.');
        return;
    }

    // نأخذ أول سيرفر (يمكن تحسينها لاختيار الأسرع)
    const videoUrl = servers[0];
    btn.textContent = '⏳ جاري التحميل...';
    btn.classList.add('loading');

    try {
        // 1. تحميل الفيديو كـ ArrayBuffer
        const response = await fetch(videoUrl);
        if (!response.ok) throw new Error('فشل تحميل الفيديو');
        const fileBuffer = await response.arrayBuffer();
        const inputFileName = `input_${Date.now()}.mp4`;
        const outputFileName = `output_${Date.now()}.mp4`;

        // 2. ضغط الفيديو باستخدام FFmpeg.wasm
        btn.textContent = '🔄 جاري الضغط إلى 240p...';
        const { createFFmpeg, fetchFile } = FFmpeg;
        const ffmpeg = createFFmpeg({ log: true });
        await ffmpeg.load();

        // كتابة الملف في الذاكرة الافتراضية
        ffmpeg.FS('writeFile', inputFileName, await fetchFile(new Blob([fileBuffer])));

        // تشغيل أمر الضغط
        ffmpeg.setProgress(({ ratio }) => {
            const percent = Math.round(ratio * 100);
            document.getElementById('compressProgress').value = percent;
            document.getElementById('progressText').textContent = `${percent}%`;
        });

        await ffmpeg.run(
            '-i', inputFileName,
            '-vf', 'scale=-2:240',
            '-c:v', 'libx264', '-crf', '30', '-preset', 'veryfast',
            '-c:a', 'aac', '-b:a', '48k',
            '-y', outputFileName
        );

        // قراءة الملف المضغوط
        const data = ffmpeg.FS('readFile', outputFileName);
        const blob = new Blob([data.buffer], { type: 'video/mp4' });
        const url = URL.createObjectURL(blob);

        // 3. عرض الفيديو
        const container = document.getElementById('videoContainer');
        const player = document.getElementById('player');
        const title = document.getElementById('videoTitle');
        container.classList.add('active');
        title.textContent = `${btn.dataset.seriesName} - حلقة ${btn.dataset.episodeNum}`;
        player.src = url;
        player.load();
        player.play();

        // تنظيف الملفات من الذاكرة الافتراضية
        ffmpeg.FS('unlink', inputFileName);
        ffmpeg.FS('unlink', outputFileName);

        btn.textContent = '▶️ مشاهدة';
        btn.classList.remove('loading');
        btn.classList.add('done');

    } catch (err) {
        console.error(err);
        btn.textContent = '❌ فشل';
        btn.classList.remove('loading');
        alert('حدث خطأ أثناء التحميل أو الضغط. تأكد من الرابط وحاول مرة أخرى.');
    }
}

// ===== تحديد الصفحة الحالية =====
if (window.location.pathname.includes('series.html')) {
    renderSeries();
} else {
    renderHome();
}
