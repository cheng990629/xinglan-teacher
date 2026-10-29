import { useState } from 'react'
import { uploadWord, type UploadResult } from '../api'

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => resolve(String(r.result).split(',')[1])
    r.onerror = () => reject(new Error('读取文件失败'))
    r.readAsDataURL(file)
  })
}

export function UploadPanel({ onExtracted }: { onExtracted: (r: UploadResult) => void }) {
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  async function onFile(file: File | undefined) {
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.docx')) { setMsg('只接受 .docx：请上传教师手写的 Word 文档'); return }
    setBusy(true); setMsg('正在解析并按平台标准提取…')
    try {
      const b64 = await fileToBase64(file)
      const r = await uploadWord(file.name, b64, 'auto')
      onExtracted(r)
      setMsg(`已解析 ${file.name}，共 ${r.chars} 字；缺失槽位 ${r.missing.length} 个，见下方结果表。`)
    } catch (e) { setMsg(`提取失败：${String(e)}`) } finally { setBusy(false) }
  }
  return (
    <section className="panel">
      <h2>上传教师今日手写 Word</h2>
      <p className="panel-desc">只接受 .docx（5M 以内）。后端先解析文档，再按平台标准槽位（课程、主题、目标、知识点、环节、作业、板书）提取，找不到填 null，不编造。</p>
      <input type="file" accept=".docx" disabled={busy} onChange={(e) => { void onFile(e.target.files?.[0]); e.target.value = '' }} />
      {msg && <p className="note" aria-live="polite">{msg}</p>}
    </section>
  )
}
