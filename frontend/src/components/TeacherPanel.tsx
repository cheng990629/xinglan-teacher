import { useEffect, useRef, useState } from 'react'

// 左侧星澜教师面板：状态机 idle / thinking / explaining，与星澜真人版同一套状态语义。
// 真模型通过 VITE_VTUBER_WS 连 Open-LLM-VTuber 的 /client-ws；连不上时如实显示“数字人后端未连接”，
// 只出文字字幕，不伪造一个假数字人在动。VITE_VTUBER_WS 未配置时默认不连。
export type TeacherState = 'idle' | 'thinking' | 'explaining'
const WS_URL = import.meta.env.VITE_VTUBER_WS ?? ''

export function TeacherPanel({ state, caption }: { state: TeacherState; caption: string }) {
  const [connected, setConnected] = useState<boolean | null>(null)
  const ws = useRef<WebSocket | null>(null)
  useEffect(() => {
    if (!WS_URL) { setConnected(false); return }
    try {
      const s = new WebSocket(WS_URL)
      ws.current = s
      s.onopen = () => setConnected(true)
      s.onclose = () => setConnected(false)
      s.onerror = () => setConnected(false)
    } catch { setConnected(false) }
    return () => { try { ws.current?.close() } catch { /* ignore */ } }
  }, [])
  return (
    <aside className="teacher-panel">
      <div className="teacher-stage">
        <span className={`teacher-dot ${state}`} aria-hidden="true" />
        <div className="teacher-figure" aria-label="星澜数字人教师">
          <span className="teacher-nameplate">星澜</span>
          <span className="teacher-role">数字人教师 · 空军蓝制服讲解员</span>
        </div>
        <p className="teacher-status">
          {connected === null ? '正在检测数字人后端…' : connected ? '● 数字人后端已连接' : '● 数字人后端未连接（仅显示字幕）'}
        </p>
      </div>
      <div className="teacher-caption">
        <span className="caption-state">{state === 'idle' ? '待命' : state === 'thinking' ? '思考中' : '讲解中'}</span>
        <p>{caption || '上传今日手写 Word，星澜会按平台标准讲出提取与筹划结果。'}</p>
      </div>
      <p className="note">真人模型与语音走已部署的 Open-LLM-VTuber（WS /client-ws）与 TTS 服务；本架子不内置假模型，VTUBER 地址用 VITE_VTUBER_WS 配置。</p>
    </aside>
  )
}
