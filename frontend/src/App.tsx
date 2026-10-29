import { useEffect, useState } from 'react'
import { TeacherPanel, type TeacherState } from './components/TeacherPanel'
import { PiChat } from './components/PiChat'
import { UploadPanel } from './components/UploadPanel'
import { PlanningPanel } from './components/PlanningPanel'
import { ModelPanel } from './components/ModelPanel'
import { checkHealth, type Plans, type UploadResult } from './api'
import './styles.css'

// 布局：左侧 440px 星澜教师固定，右侧页签（pi-web 聊天 / 上传提取 / 筹划 / 模型配置）。
// 端口：前端 5179（5175 是槽位填充，不要占用），后端 8005，见 vite.config.ts 与 README。
export default function App() {
  const [tab, setTab] = useState('chat')
  const [healthy, setHealthy] = useState<boolean | null>(null)
  const [state, setState] = useState<TeacherState>('idle')
  const [caption, setCaption] = useState('')
  const [upload, setUpload] = useState<UploadResult | null>(null)
  useEffect(() => { void checkHealth().then(setHealthy) }, [])
  function onExtracted(r: UploadResult) {
    setUpload(r); setState('explaining')
    setCaption(`已按平台标准提取 ${r.filename}：${Object.keys(r.extraction).length} 个槽位，缺失 ${r.missing.length} 个；筹划结构已就绪。`)
    setTab('plans')
  }
  return (
    <div className="app">
      <header className="header">
        <span className="brand-text"><strong>星澜数字人教师</strong><small>XINGLAN TEACHER · 左侧数字人 / 右侧 pi-web</small></span>
        <nav className="nav">
          <button onClick={() => setTab('chat')}>pi-web 聊天</button>
          <button onClick={() => setTab('upload')}>上传 Word</button>
          <button onClick={() => setTab('plans')}>筹划 21/4/6</button>
          <button onClick={() => setTab('model')}>模型配置</button>
        </nav>
        <span className={`health ${healthy === null ? '' : healthy ? 'ok' : 'bad'}`}>{healthy === null ? '正在检测后端…' : healthy ? '● 后端在线' : '● 后端未启动'}</span>
      </header>
      <main className="teacher-layout">
        <TeacherPanel state={state} caption={caption} />
        <div className="teacher-main">
          {tab === 'chat' && <PiChat />}
          {tab === 'upload' && (<>
            <UploadPanel onExtracted={onExtracted} />
            {upload && (<section className="panel"><h2>平台标准提取结果</h2>
              <table className="table"><thead><tr><th>槽位</th><th>提取值</th></tr></thead>
              <tbody>{Object.entries(upload.extraction).map(([k, v]) => (<tr key={k}><td>{k}</td><td className="value-cell">{v === null ? 'null（未找到，不编造）' : Array.isArray(v) ? v.join('；') : String(v)}</td></tr>))}</tbody></table>
              {upload.missing.length > 0 && <p className="note">缺失：{upload.missing.join('、')}</p>}
              {upload.warnings.length > 0 && <p className="note">警告：{upload.warnings.join('；')}</p>}
            </section>)}
          </>)}
          {tab === 'plans' && <PlanningPanel plans={upload?.plans ?? null} extraction={upload?.extraction ?? null} />}
          {tab === 'model' && <ModelPanel />}
        </div>
      </main>
      <footer className="footer"><span>前端 5179（5175 是槽位填充）</span><span>后端 8005 · 提取引擎复用槽位填充（代码/LLM/混合/Agent）</span></footer>
    </div>
  )
}
