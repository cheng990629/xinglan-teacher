const API_BASE = import.meta.env.VITE_API_BASE ?? ''

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!res.ok) throw new Error(`请求失败 ${res.status}：${(await res.text()).slice(0, 300)}`)
  return res.json() as Promise<T>
}
async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`)
  if (!res.ok) throw new Error(`请求失败 ${res.status}`)
  return res.json() as Promise<T>
}
export type PlanItem = { id: string; title: string; status: string; source: string }
export type Plans = { stages: { stage: string; count: number; prefix: string; note: string; items: PlanItem[] }[]; generated?: boolean; note?: string }
export type UploadResult = { filename: string; chars: number; text: string; extraction: Record<string, unknown>; missing: string[]; warnings: string[]; plans: Plans }

export async function getPlans(): Promise<Plans> { return getJson('/api/v1/teacher/plans') }
export async function uploadWord(filename: string, docxBase64: string, extractor = 'auto'): Promise<UploadResult> {
  return postJson('/api/v1/teacher/upload', { filename, docx_base64: docxBase64, extractor })
}
export async function generatePlans(extraction: unknown): Promise<Plans> {
  return postJson('/api/v1/teacher/plan', { extraction })
}
export async function checkHealth(): Promise<boolean> {
  try { const res = await fetch(`${API_BASE}/health`); return res.ok } catch { return false }
}

export type ModelConfig = {
  has_api_key: boolean
  api_key_masked: string
  base_url: string
  model: string
  is_bailian: boolean
  mock: boolean
  bailian_default_base_url: string
  tier_suggestions: Record<string, string>
}
export async function getConfig(): Promise<ModelConfig> { return getJson('/api/v1/config') }
export async function saveConfig(body: { api_key?: string; base_url?: string; model?: string }): Promise<ModelConfig> {
  return postJson('/api/v1/config', body)
}
export async function testConfig(body: { api_key?: string; base_url?: string; model?: string }): Promise<{ ok: boolean; model?: string; base_url?: string; latency_ms?: number; reply?: string; error?: string }> {
  try { return await postJson('/api/v1/config/test', body) } catch (e) { return { ok: false, error: String(e) } }
}
