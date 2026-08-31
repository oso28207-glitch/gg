const METADATA_URL = 'https://raw.githubusercontent.com/YourUsername/YourRepoName/main/data/metadata.json';

async function fetchData() {
    try {
        const res = await fetch(METADATA_URL);
        return await res.json();
    } catch {
        return { series: {} };
    }
}

function renderSeries(data) {
    const app = document.getElementById('app');
    app.innerHTML = '';
    const seriesNames = Object.keys(data.series).reverse(); // الأحدث أولاً (حسب الترتيب)

    if (seriesNames.length === 0) {
        app.innerHTML = '<p style="text-align:center; margin-top:50px;">لا توجد حلقات مضغوطة حتى الآن. انتظر التحديث التلقائي.</p>';
        return;
    }

    for (const name of seriesNames) {
        const episodes = data.series[name].episodes;
        if (!episodes || episodes.length === 0) continue;

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
            btn.dataset.url = ep.url;
            btn.dataset.title = `${name} - حلقة ${ep.episode}`;
            btn.onclick = () => playVideo(btn.dataset.url, btn.dataset.title);
            grid.appendChild(btn);
        }
        card.appendChild(grid);
        app.appendChild(card);
    }
}

function playVideo(url, title) {
    // إزالة أي مشغل سابق
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

// التحميل والعرض
fetchData().then(renderSeries);
