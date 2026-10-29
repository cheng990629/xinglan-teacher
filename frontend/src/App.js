import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useEffect, useState } from 'react';
import { TeacherPanel } from './components/TeacherPanel';
import { PiChat } from './components/PiChat';
import { UploadPanel } from './components/UploadPanel';
import { PlanningPanel } from './components/PlanningPanel';
import { ModelPanel } from './components/ModelPanel';
import { checkHealth } from './api';
import './styles.css';
// 布局：左侧 440px 星澜教师固定，右侧页签（pi-web 聊天 / 上传提取 / 筹划 / 模型配置）。
// 端口：前端 5179（5175 是槽位填充，不要占用），后端 8005，见 vite.config.ts 与 README。
export default function App() {
    const [tab, setTab] = useState('chat');
    const [healthy, setHealthy] = useState(null);
    const [state, setState] = useState('idle');
    const [caption, setCaption] = useState('');
    const [upload, setUpload] = useState(null);
    useEffect(() => { void checkHealth().then(setHealthy); }, []);
    function onExtracted(r) {
        setUpload(r);
        setState('explaining');
        setCaption(`已按平台标准提取 ${r.filename}：${Object.keys(r.extraction).length} 个槽位，缺失 ${r.missing.length} 个；筹划结构已就绪。`);
        setTab('plans');
    }
    return (_jsxs("div", { className: "app", children: [_jsxs("header", { className: "header", children: [_jsxs("span", { className: "brand-text", children: [_jsx("strong", { children: "\u661F\u6F9C\u6570\u5B57\u4EBA\u6559\u5E08" }), _jsx("small", { children: "XINGLAN TEACHER \u00B7 \u5DE6\u4FA7\u6570\u5B57\u4EBA / \u53F3\u4FA7 pi-web" })] }), _jsxs("nav", { className: "nav", children: [_jsx("button", { onClick: () => setTab('chat'), children: "pi-web \u804A\u5929" }), _jsx("button", { onClick: () => setTab('upload'), children: "\u4E0A\u4F20 Word" }), _jsx("button", { onClick: () => setTab('plans'), children: "\u7B79\u5212 21/4/6" }), _jsx("button", { onClick: () => setTab('model'), children: "\u6A21\u578B\u914D\u7F6E" })] }), _jsx("span", { className: `health ${healthy === null ? '' : healthy ? 'ok' : 'bad'}`, children: healthy === null ? '正在检测后端…' : healthy ? '● 后端在线' : '● 后端未启动' })] }), _jsxs("main", { className: "teacher-layout", children: [_jsx(TeacherPanel, { state: state, caption: caption }), _jsxs("div", { className: "teacher-main", children: [tab === 'chat' && _jsx(PiChat, {}), tab === 'upload' && (_jsxs(_Fragment, { children: [_jsx(UploadPanel, { onExtracted: onExtracted }), upload && (_jsxs("section", { className: "panel", children: [_jsx("h2", { children: "\u5E73\u53F0\u6807\u51C6\u63D0\u53D6\u7ED3\u679C" }), _jsxs("table", { className: "table", children: [_jsx("thead", { children: _jsxs("tr", { children: [_jsx("th", { children: "\u69FD\u4F4D" }), _jsx("th", { children: "\u63D0\u53D6\u503C" })] }) }), _jsx("tbody", { children: Object.entries(upload.extraction).map(([k, v]) => (_jsxs("tr", { children: [_jsx("td", { children: k }), _jsx("td", { className: "value-cell", children: v === null ? 'null（未找到，不编造）' : Array.isArray(v) ? v.join('；') : String(v) })] }, k))) })] }), upload.missing.length > 0 && _jsxs("p", { className: "note", children: ["\u7F3A\u5931\uFF1A", upload.missing.join('、')] }), upload.warnings.length > 0 && _jsxs("p", { className: "note", children: ["\u8B66\u544A\uFF1A", upload.warnings.join('；')] })] }))] })), tab === 'plans' && _jsx(PlanningPanel, { plans: upload?.plans ?? null, extraction: upload?.extraction ?? null }), tab === 'model' && _jsx(ModelPanel, {})] })] }), _jsxs("footer", { className: "footer", children: [_jsx("span", { children: "\u524D\u7AEF 5179\uFF085175 \u662F\u69FD\u4F4D\u586B\u5145\uFF09" }), _jsx("span", { children: "\u540E\u7AEF 8005 \u00B7 \u63D0\u53D6\u5F15\u64CE\u590D\u7528\u69FD\u4F4D\u586B\u5145\uFF08\u4EE3\u7801/LLM/\u6DF7\u5408/Agent\uFF09" })] })] }));
}
