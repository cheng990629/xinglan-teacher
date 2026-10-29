import { useState } from 'react'
import { generatePlans, type Plans } from '../api'

export function PlanningPanel({ plans, extraction }: { plans: Plans | null; extraction: unknown }) {
  const [data, setData] = useState<Plans | null>(plans)
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const shown = data ?? plans
  async function gen() {
    setBusy(true); setMsg('正在生成筹划…（未配置模型时会原样返回模板并注明）')
    try { const r = await generatePlans(extraction); setData(r); setMsg(r.note ?? '') }
    catch (e) { setMsg(`生成失败：${String(e)}`) } finally { setBusy(false) }
  }
  if (!shown) return <section className="panel"><h2>筹划 · 21 明确 / 4 知 / 6 构想</h2><p className="panel-desc">先上传 Word，提取完成后这里会出现 21/4/6 结构。</p></section>
  return (
    <section className="panel">
      <h2>筹划 · 21 明确 / 4 知 / 6 构想</h2>
      {shown.note && <p className="note">{shown.note}</p>}
      <div className="form-row"><button className="primary" disabled={busy} onClick={gen}>生成筹划（需配置模型）</button></div>
      {shown.stages.map((s) => (
        <div key={s.prefix}>
          <h3>{s.stage}（{s.count} 项）</h3>
          <p className="note">{s.note}</p>
          <table className="table"><thead><tr><th>编号</th><th>内容</th><th>状态</th><th>溯源</th></tr></thead>
          <tbody>{s.items.map((it) => (<tr key={it.id}><td>{it.id}</td><td>{it.title || '（待生成）'}</td><td>{it.status}</td><td>{it.source || '—'}</td></tr>))}</tbody></table>
        </div>
      ))}
    </section>
  )
}
