import { useState } from 'react'

// 右侧 pi-web 聊天区：本架子不伪造 pi-web 回复。
// 配好 pi-web 后端地址（下方输入框，默认 WSL 上已部署的 pi-web）后，
// 聊天区以该地址打开 pi-web；未配置时只做本地记录，并明确标注不是 pi-web 回复。
export function PiChat() {
  const [url, setUrl] = useState('')
  const [msgs, setMsgs] = useState<{ role: string; text: string }[]>([])
  const [input, setInput] = useState('')
  function send() {
    if (!input.trim()) return
    setMsgs((m) => [...m, { role: '你', text: input }, { role: '本地记录', text: '（未接 pi-web 后端时仅本地记录，不是 pi-web 回复。请在上方填入 pi-web 地址后打开 pi-web 聊天。）' }])
    setInput('')
  }
  return (
    <section className="panel">
      <h2>右侧 · pi-web 聊天</h2>
      <label>pi-web 地址（例如已部署的 http://100.77.50.49:30141/pi，留空则只本地记录）
        <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="http://100.77.50.49:30141/pi" />
      </label>
      {url ? (
        <div className="piweb-frame-wrap">
          <a className="primary" href={url} target="_blank" rel="noreferrer">在新标签页打开 pi-web</a>
          <p className="note">架子版不把 pi-web 嵌进 iframe 冒充原生聊天；地址填好后点上面按钮打开真正的 pi-web，左侧星澜状态与聊天内容由后端 WS 联动。</p>
        </div>
      ) : (
        <div className="chat-box">
          {msgs.map((m, i) => (<p key={i}><strong>{m.role}：</strong>{m.text}</p>))}
          {msgs.length === 0 && <p className="note">还没有消息。填入 pi-web 地址，或直接在下方输入做本地记录。</p>}
        </div>
      )}
      <div className="form-row">
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="输入问题…" onKeyDown={(e) => { if (e.key === 'Enter') send() }} />
        <button className="primary" onClick={send}>发送</button>
      </div>
    </section>
  )
}
