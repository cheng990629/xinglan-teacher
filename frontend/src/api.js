const API_BASE = import.meta.env.VITE_API_BASE ?? '';
async function postJson(path, body) {
    const res = await fetch(`${API_BASE}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (!res.ok)
        throw new Error(`请求失败 ${res.status}：${(await res.text()).slice(0, 300)}`);
    return res.json();
}
async function getJson(path) {
    const res = await fetch(`${API_BASE}${path}`);
    if (!res.ok)
        throw new Error(`请求失败 ${res.status}`);
    return res.json();
}
export async function getPlans() { return getJson('/api/v1/teacher/plans'); }
export async function uploadWord(filename, docxBase64, extractor = 'auto') {
    return postJson('/api/v1/teacher/upload', { filename, docx_base64: docxBase64, extractor });
}
export async function generatePlans(extraction) {
    return postJson('/api/v1/teacher/plan', { extraction });
}
export async function checkHealth() {
    try {
        const res = await fetch(`${API_BASE}/health`);
        return res.ok;
    }
    catch {
        return false;
    }
}
export async function getConfig() { return getJson('/api/v1/config'); }
export async function saveConfig(body) {
    return postJson('/api/v1/config', body);
}
export async function testConfig(body) {
    try {
        return await postJson('/api/v1/config/test', body);
    }
    catch (e) {
        return { ok: false, error: String(e) };
    }
}
