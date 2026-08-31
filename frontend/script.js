// ===== الإعدادات =====
const METADATA_URL = 'https://raw.githubusercontent.com/oso28207-glitch/gg/main/data/metadata.json';
const ACTION_API_URL = 'https://api.github.com/repos/oso28207-glitch/gg/actions/workflows/compress_episode.yml/dispatches';
let GITHUB_TOKEN = '';

// ===== دوال مساعدة =====
function getQueryParam(param) {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get(param);
}

async function fetchData() {
    try {
        const res = await fetch(METADATA_URL);
        return await res.json();
    } catch {
        return { series: {} };
    }
}

// ===== طلب التوكن من المستخدم =====
function promptForToken() {
    return prompt('أدخل GitHub Personal Access Token (لن يتم حفظه):');
}

// ===== تشغيل Action عبر API =====
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
            alert('فشل تشغيل الضغط. تأكد من التوكن وصلاحياته (repo + workflow).');
            return false;
        }
    } catch (err) {
        console.error(err);
        alert('حدث خطأ أثناء الاتصال بـ GitHub.');
        return false;
    }
}

// ===== التحقق الدوري من وجود الفيديو المضغوط =====
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
            btn.onclick = () => playCompressedVideo(ep.compressed_url, `${seriesName} - حلقة ${episodeNum}`);
        } else {
            // لم يتم الضغط بعد، ننتظر 30 ثانية أخرى
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

// ===== معالجة الضغط عند الطلب =====
async function handleEpisodeClick(btn) {
    if (btn.classList.contains('loading')) return;
    
    const seriesName = btn.dataset.seriesName;
    const episodeNum = parseInt(btn.dataset.episodeNum);
    const servers = JSON.parse(btn.dataset.servers);
    
    // إذا كان هناك رابط مضغوط مسبقاً (غير متوقع هنا، لكن للتأكيد)
    if (btn.dataset.compressedUrl) {
        playCompressedVideo(btn.dataset.compressedUrl, `${seriesName} - حلقة ${episodeNum}`);
        return;
    }
    
    if (!servers || servers.length === 0) {
        alert('لا توجد سيرفرات لهذه الحلقة. انتظر التحديث التالي.');
        return;
    }
    
    btn.textContent = '⏳ جاري طلب الضغط...';
    btn.classList.add('loading');
    
    const success = await triggerCompression(seriesName, episodeNum);
    if (success) {
        btn.textContent = '⏳ قيد المعالجة...';
        alert(`✅ تم بدء ضغط الحلقة ${episodeNum}.\nقد يستغرق الضغط بضع دقائق. سيتم تحديث الزر تلقائياً عند الانتهاء.`);
        // بدء التحقق الدوري
        setTimeout(() => {
            checkForCompressed(btn, seriesName, episodeNum);
        }, 30000); // أول فحص بعد 30 ثانية
    } else {
        btn.textContent = '❌ فشل الطلب';
        btn.classList.remove('loading');
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
        if (ep.compressed_url) {
            // الحلقة مضغوطة بالفعل
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

// ===== تحديد الصفحة الحالية =====
if (window.location.pathname.includes('series.html')) {
    renderSeries();
} else {
    renderHome();
}
