// ===== الإعدادات =====
const GITHUB_TOKEN = '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';

// ===== دالة لتحديث التوكن يدوياً =====
function updateToken() {
    const newToken = prompt('أدخل GitHub Personal Access Token (صلاحيات مطلوبة: repo + workflow):', GITHUB_TOKEN);
    if (newToken && newToken.trim()) {
        GITHUB_TOKEN = newToken.trim();
        alert('✅ تم تحديث التوكن بنجاح.');
    }
}

// ===== تشغيل Action مع التعامل مع الأخطاء =====
async function triggerCompression(seriesName, episodeNum) {
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
        } else if (response.status === 401 || response.status === 403) {
            // إذا كان التوكن غير صالح، نطلب من المستخدم إدخال توكن جديد
            alert('❌ التوكن غير صالح أو انتهت صلاحيته. سيُطلب منك إدخال توكن جديد.');
            updateToken();
            // نعيد المحاولة مرة واحدة
            return await triggerCompression(seriesName, episodeNum);
        } else {
            const errorData = await response.json().catch(() => ({}));
            alert(`❌ فشل تشغيل الضغط (${response.status}): ${errorData.message || 'خطأ غير معروف'}`);
            return false;
        }
    } catch (err) {
        console.error(err);
        alert('❌ حدث خطأ في الاتصال بـ GitHub.');
        return false;
    }
}

// أضف زراً لتحديث التوكن في الواجهة (اختياري):
// يمكنك إضافة زر في index.html: <button onclick="updateToken()">تحديث التوكن</button>
