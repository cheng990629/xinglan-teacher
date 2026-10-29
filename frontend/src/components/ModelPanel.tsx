import { useEffect, useState } from 'react'
import { getConfig, saveConfig, testConfig, type ModelConfig } from '../api'

// 模型配置页：只做三件事——填百炼 Key、选地址、选模型档位/模型名。
// Key 只发给后端、只存后端 .env（600 权限），接口永不回完整 Key；
// 档位只是建议值，真正生效的是模型名框里的值，框里可自由改。
const TIERS = [
  { key: '35B', label: '35B 级（大）', suggestion: 'qwen3-32b', note: '百炼 32B 级大模型，抽取最稳，适合错版多的文档' },
  { key: '27B', label: '27B 级（中）', suggestion: 'gemma-2-27b-it', note: '按你百炼开通的模型名改，框里可自由填' },
  { key: '9B', label: '9B 级（小）', suggestion: 'qwen3-8b', note: '百炼 8B 级小模型，最快最便宜，适合格式规整的文档' },
  { key: 'custom', label: '自定义', suggestion: '', note: '百炼千问 Plus/Max（qwen-plus、qwen-max 等）直接填模型名' },
]

export function ModelPanel() {
  const [cfg, setCfg] = useState<ModelConfig | null>(null)
  const [baseUrl, setBaseUrl] = useState('https://dashscope.aliyuncs.com/compatible-mode/v1')
  const [apiKey, setApiKey] = useState('')
  const [tier, setTier] = useState('9B')
  const [model, setModel] = useState('qwen3-8b')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    void getConfig().then((c) => {
      setCfg(c)
      if (c.base_url) setBaseUrl(c.base_url)
      if (c.model) setModel(c.model)
    }).catch((e) => setMsg(`读取配置失败：${String(e)}`))
  }, [])

  function pickTier(key: string) {
    setTier(key)
    const t = TIERS.find((x) => x.key === key)
    if (t && t.suggestion) setModel(t.suggestion)
  }

  async function onSave() {
    setBusy(true); setMsg('')
    try {
      const c = await saveConfig({ api_key: apiKey || undefined, base_url: baseUrl, model })
      setCfg(c); setApiKey('')
      setMsg('已保存到后端 .env，之后提交的提取任务无需重启即可用新配置。')
    } catch (e) { setMsg(`保存失败：${String(e)}`) } finally { setBusy(false) }
  }

  async function onTest() {
    setBusy(true); setMsg('正在测试连接…')
    try {
      const r = await testConfig({ api_key: apiKey || undefined, base_url: baseUrl, model })
      setMsg(r.ok ? `连接成功：模型 ${r.model}，耗时 ${r.latency_ms}ms，模型回复：${r.reply}` : `连接失败：${r.error}`)
    } catch (e) { setMsg(`测试失败：${String(e)}`) } finally { setBusy(false) }
  }

  return (
    <section className="panel">
      <h2>模型配置 · 阿里云百炼</h2>
      <p className="panel-desc">
        百炼走 OpenAI 兼容协议，只改地址、Key、模型名三项就能用。后端已经是这个协议，
        不用换代码。当前状态：{cfg ? (cfg.has_api_key ? `已填 Key（${cfg.api_key_masked}）` : '未填 Key') : '读取中…'}
        {cfg && cfg.model ? `，当前模型 ${cfg.model}` : ''}{cfg && cfg.is_bailian ? '，地址是百炼' : ''}
      </p>
      <div className="form-grid">
        <label>百炼地址（base_url）
          <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1" />
          <span className="note">默认是百炼通用地址；如果你的 Key 属于某个业务空间，改成 https://{'{WorkspaceId}'}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1，不要带 /chat/completions。</span>
        </label>
        <label>百炼 API Key
          <input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="留空表示不改已保存的 Key" />
          <span className="note">只发给后端、只存后端 .env（600 权限），页面和接口都不会再显示完整 Key。不要把 Key 发到聊天里。</span>
        </label>
      </div>
      <h3>模型档位</h3>
      <div className="mode-row">
        {TIERS.map((t) => (
          <label key={t.key} className={`mode ${tier === t.key ? 'active' : ''}`}>
            <input type="radio" name="tier" checked={tier === t.key} onChange={() => pickTier(t.key)} />
            <strong>{t.label}</strong>
            <span>{t.note}</span>
          </label>
        ))}
      </div>
      <label>模型名（真正生效的值，可自由改）
        <input value={model} onChange={(e) => setModel(e.target.value)} placeholder="例如 qwen3-32b、qwen-plus、qwen-max" />
      </label>
      <div className="form-row">
        <button className="primary" disabled={busy} onClick={onSave}>保存配置</button>
        <button className="ghost" disabled={busy} onClick={onTest}>测试连接</button>
      </div>
      {msg && <p className="note" aria-live="polite">{msg}</p>}
      <h3>保存后怎么用</h3>
      <p className="panel-desc">
        回到“提取”页，模式选 llm、hybrid 或 agent 就会用这里保存的模型跑；code 模式不走模型，不受影响。
        也可以直接改后端目录的 .env（LLM_BASE_URL / LLM_API_KEY / LLM_MODEL），效果一样，重启后端才生效；
        页面上保存是立即生效，不用重启。
      </p>
    </section>
  )
}
