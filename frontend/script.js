// ===== الإعدادات =====
const METADATA_URL = 'https://raw.githubusercontent.com/oso28207-glitch/gg/main/data/metadata.json';
// رابط API لتشغيل Action (استبدل اسم المستخدم والمستودع)
const ACTION_API_URL = 'https://api.github.com/repos/oso28207-glitch/gg/actions/workflows/compress_episode.yml/dispatches';
// التوكن سيتم وضعه من قبل المستخدم في متغير بيئي أو يُطلب منه
// سنستخدم طريقة بسيطة: نطلب من المستخدم إدخال التوكن عند الحاجة
let GITHUB_TOKEN = '';

// ===== طلب التوكن من المستخدم =====
function promptForToken() {
    return prompt('أدخل GitHub Personal Access Token لتشغيل الضغط (لن يتم حفظه):');
}

// ===== تشغيل Action عن بعد =====
async function triggerCompression(seriesName, episodeNum) {
    if (!GITHUB_TOKEN) {
        GITHUB_TOKEN = promptForToken();
        if (!GITHUB_TOKEN) {
            alert('لا يمكن المتابعة بدون توكن.');
            return false;
        }
    }
    
    try {
        const response = await fetch(ACTION_API_URL, {
            method: 'POST',
            headers: {
                'Authorization': `token ${GITHUB_TOKEN}`,
                'Accept': 'application/vnd.github.v3+json',
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                ref: 'main',
                inputs: {
                    series_name: seriesName,
                    episode_number: episodeNum.toString()
                }
            })
        });
        
        if (response.status === 204) {
            return true;
        } else {
            const error = await response.text();
            console.error('فشل تشغيل Action:', error);
            alert('فشل تشغيل الضغط. تأكد من التوكن وصلاحياته.');
            return false;
        }
    } catch (err) {
        console.error(err);
        alert('حدث خطأ أثناء الاتصال بـ GitHub.');
        return false;
    }
}

// ===== معالجة الضغط عند الطلب =====
async function handleEpisodeClick(btn) {
    if (btn.classList.contains('loading')) return;
    
    const episodeUrl = btn.dataset.episodeUrl;
    const seriesName = btn.dataset.seriesName;
    const episodeNum = parseInt(btn.dataset.episodeNum);
    const servers = JSON.parse(btn.dataset.servers);
    const compressedUrl = btn.dataset.compressedUrl || '';
    
    // إذا كان الفيديو مضغوطاً بالفعل
    if (compressedUrl) {
        playCompressedVideo(compressedUrl, `${seriesName} - حلقة ${episodeNum}`);
        return;
    }
    
    // إذا كانت السيرفرات فارغة
    if (!servers || servers.length === 0) {
        alert('لا توجد سيرفرات لهذه الحلقة. انتظر التحديث التالي.');
        return;
    }
    
    // طلب الضغط
    btn.textContent = '⏳ جاري طلب الضغط...';
    btn.classList.add('loading');
    
    const success = await triggerCompression(seriesName, episodeNum);
    if (success) {
        btn.textContent = '⏳ قيد المعالجة...';
        alert(`✅ تم بدء ضغط الحلقة ${episodeNum}.\nانتظر بضع دقائق ثم قم بتحديث الصفحة.`);
        // يمكننا تحديث الرابط بعد دقيقة مثلاً
        setTimeout(() => {
            checkForCompressed(btn, seriesName, episodeNum);
        }, 60000); // بعد دقيقة
    } else {
        btn.textContent = '❌ فشل الطلب';
        btn.classList.remove('loading');
    }
}

// ===== التحقق من وجود الفيديو المضغوط =====
async function checkForCompressed(btn, seriesName, episodeNum) {
    try {
        const data = await fetchData();
        const series = data.series[seriesName];
        if (!series) return;
        const ep = series.episodes.find(e => e.episode === episodeNum);
        if (ep && ep.compressed_url) {
            btn.dataset.compressedUrl = ep.compressed_url;
            btn.textContent = '▶️ مشاهدة';
            btn.classList.remove('loading');
            btn.classList.add('done');
            // تحديث الزر ليستخدم دالة التشغيل المباشر
            btn.onclick = () => {
                playCompressedVideo(ep.compressed_url, `${seriesName} - حلقة ${episodeNum}`);
            };
        } else {
            // لم يتم الضغط بعد، ننتظر مرة أخرى
            setTimeout(() => {
                checkForCompressed(btn, seriesName, episodeNum);
            }, 30000);
        }
    } catch (err) {
        console.warn('فشل التحقق:', err);
    }
}

// ===== تشغيل الفيديو المضغوط =====
function playCompressedVideo(url, title) {
    const container = document.getElementById('videoContainer');
    const player = document.getElementById('player');
    const titleEl = document.getElementById('videoTitle');
    container.classList.add('active');
    titleEl.textContent = title;
    player.src = url;
    player.load();
    player.play();
}

// ===== تحديث دالة renderSeries لتضمين compressed_url =====
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

    const episodes = [...series.episodes].sort((a, b) => b.episode - a.episode);
    const grid = document.createElement('div');
    grid.className = 'episode-grid';

    for (const ep of episodes) {
        const btn = document.createElement('button');
        btn.className = 'episode-btn';
        // إذا كان هناك رابط مضغوط، نعرض زر "مشاهدة"
        if (ep.compressed_url) {
            btn.textContent = '▶️ مشاهدة';
            btn.dataset.compressedUrl = ep.compressed_url;
            btn.onclick = () => playCompressedVideo(ep.compressed_url, `${seriesName} - حلقة ${ep.episode}`);
        } else {
            btn.textContent = `📥 حلقة ${ep.episode}`;
            btn.dataset.episodeUrl = ep.url;
            btn.dataset.seriesName = seriesName;
            btn.dataset.episodeNum = ep.episode;
            btn.dataset.servers = JSON.stringify(ep.servers || []);
            btn.onclick = () => handleEpisodeClick(btn);
        }
        grid.appendChild(btn);
    }
    app.appendChild(grid);
}

// ===== قراءة المعامل من الرابط =====
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
    const seriesNames = Object.keys(data.series).filter(name => 
        data.series[name].episodes?.length > 0
    );
    
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

// ===== عرض حلقات مسلسل معين =====
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

// ===== التحقق مما إذا كان الرابط مباشراً =====
function isDirectVideoUrl(url) {
    const directExtensions = ['.mp4', '.m3u8', '.webm', '.ogg'];
    return directExtensions.some(ext => url.toLowerCase().includes(ext));
}

// ===== محاولة تشغيل الفيديو مباشرة =====
function playDirectVideo(url, title) {
    const container = document.getElementById('videoContainer');
    const player = document.getElementById('player');
    const titleEl = document.getElementById('videoTitle');
    container.classList.add('active');
    titleEl.textContent = title;
    player.src = url;
    player.load();
    player.play();
}

// ===== عرض الفيديو في iframe (حل بديل) =====
function playInIframe(url, title) {
    const container = document.getElementById('videoContainer');
    const player = document.getElementById('player');
    const titleEl = document.getElementById('videoTitle');
    container.classList.add('active');
    titleEl.textContent = `${title} (مشاهدة عبر الموقع الأصلي)`;
    // إخفاء مشغل الفيديو وعرض iframe
    player.style.display = 'none';
    // إزالة أي iframe سابق
    const oldIframe = container.querySelector('iframe');
    if (oldIframe) oldIframe.remove();
    const iframe = document.createElement('iframe');
    iframe.src = url;
    iframe.style.width = '100%';
    iframe.style.height = '70vh';
    iframe.style.border = 'none';
    iframe.allowFullscreen = true;
    container.appendChild(iframe);
}

// ===== معالجة الضغط والعرض =====
async function handleEpisodeClick(btn) {
    if (btn.classList.contains('loading')) return;
    
    const servers = JSON.parse(btn.dataset.servers);
    if (!servers || servers.length === 0) {
        alert('لا توجد سيرفرات لهذه الحلقة. انتظر التحديث التالي.');
        return;
    }

    // نبحث عن سيرفر يعمل
    for (let i = 0; i < servers.length; i++) {
        const videoUrl = servers[i];
        btn.textContent = `⏳ محاولة ${i+1}/${servers.length}...`;
        btn.classList.add('loading');

        try {
            // إذا كان الرابط مباشراً، شغله بدون ضغط
            if (isDirectVideoUrl(videoUrl)) {
                playDirectVideo(videoUrl, `${btn.dataset.seriesName} - حلقة ${btn.dataset.episodeNum}`);
                btn.textContent = '▶️ مشاهدة';
                btn.classList.remove('loading');
                btn.classList.add('done');
                return;
            }

            // محاولة تحميل الفيديو كـ ArrayBuffer (مع تجاوز CORS)
            const response = await fetch(videoUrl, {
                headers: {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': 'video/mp4,video/webm,video/*'
                },
                mode: 'cors' // قد يفشل إذا كان السيرفر لا يدعم CORS
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            // تحقق من نوع المحتوى
            const contentType = response.headers.get('content-type') || '';
            if (contentType.includes('text/html')) {
                // إذا كان الجواب HTML، فهذا يعني أن الرابط ليس مباشراً
                throw new Error('Not a direct video');
            }

            const fileBuffer = await response.arrayBuffer();
            const inputFileName = `input_${Date.now()}.mp4`;
            const outputFileName = `output_${Date.now()}.mp4`;

            // ضغط الفيديو باستخدام FFmpeg.wasm
            btn.textContent = '🔄 جاري الضغط إلى 240p...';
            const { createFFmpeg, fetchFile } = FFmpeg;
            const ffmpeg = createFFmpeg({ log: true });
            await ffmpeg.load();

            ffmpeg.FS('writeFile', inputFileName, await fetchFile(new Blob([fileBuffer])));

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

            const data = ffmpeg.FS('readFile', outputFileName);
            const blob = new Blob([data.buffer], { type: 'video/mp4' });
            const url = URL.createObjectURL(blob);

            playDirectVideo(url, `${btn.dataset.seriesName} - حلقة ${btn.dataset.episodeNum}`);
            
            // تنظيف
            ffmpeg.FS('unlink', inputFileName);
            ffmpeg.FS('unlink', outputFileName);

            btn.textContent = '▶️ مشاهدة';
            btn.classList.remove('loading');
            btn.classList.add('done');
            return; // نجاح

        } catch (err) {
            console.warn(`فشل السيرفر ${i+1}:`, err.message);
            // استمر في محاولة السيرفرات التالية
            continue;
        }
    }

    // إذا فشلت جميع السيرفرات، نعرض خيار iframe كحل أخير
    const lastServer = servers[0]; // نأخذ أول سيرفر لعرضه في iframe
    btn.textContent = '⚠️ فشل التحميل، عرض عبر iframe';
    btn.classList.remove('loading');
    playInIframe(lastServer, `${btn.dataset.seriesName} - حلقة ${btn.dataset.episodeNum}`);
    btn.textContent = '▶️ مشاهدة (iframe)';
    btn.classList.add('done');
}

// ===== تحديد الصفحة الحالية =====
if (window.location.pathname.includes('series.html')) {
    renderSeries();
} else {
    renderHome();
}
