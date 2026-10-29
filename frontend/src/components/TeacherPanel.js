import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useRef, useState } from 'react';
const WS_URL = import.meta.env.VITE_VTUBER_WS ?? '';
export function TeacherPanel({ state, caption }) {
    const [connected, setConnected] = useState(null);
    const ws = useRef(null);
    useEffect(() => {
        if (!WS_URL) {
            setConnected(false);
            return;
        }
        try {
            const s = new WebSocket(WS_URL);
            ws.current = s;
            s.onopen = () => setConnected(true);
            s.onclose = () => setConnected(false);
            s.onerror = () => setConnected(false);
        }
        catch {
            setConnected(false);
        }
        return () => { try {
            ws.current?.close();
        }
        catch { /* ignore */ } };
    }, []);
    return (_jsxs("aside", { className: "teacher-panel", children: [_jsxs("div", { className: "teacher-stage", children: [_jsx("span", { className: `teacher-dot ${state}`, "aria-hidden": "true" }), _jsxs("div", { className: "teacher-figure", "aria-label": "\u661F\u6F9C\u6570\u5B57\u4EBA\u6559\u5E08", children: [_jsx("span", { className: "teacher-nameplate", children: "\u661F\u6F9C" }), _jsx("span", { className: "teacher-role", children: "\u6570\u5B57\u4EBA\u6559\u5E08 \u00B7 \u7A7A\u519B\u84DD\u5236\u670D\u8BB2\u89E3\u5458" })] }), _jsx("p", { className: "teacher-status", children: connected === null ? '正在检测数字人后端…' : connected ? '● 数字人后端已连接' : '● 数字人后端未连接（仅显示字幕）' })] }), _jsxs("div", { className: "teacher-caption", children: [_jsx("span", { className: "caption-state", children: state === 'idle' ? '待命' : state === 'thinking' ? '思考中' : '讲解中' }), _jsx("p", { children: caption || '上传今日手写 Word，星澜会按平台标准讲出提取与筹划结果。' })] }), _jsx("p", { className: "note", children: "\u771F\u4EBA\u6A21\u578B\u4E0E\u8BED\u97F3\u8D70\u5DF2\u90E8\u7F72\u7684 Open-LLM-VTuber\uFF08WS /client-ws\uFF09\u4E0E TTS \u670D\u52A1\uFF1B\u672C\u67B6\u5B50\u4E0D\u5185\u7F6E\u5047\u6A21\u578B\uFF0CVTUBER \u5730\u5740\u7528 VITE_VTUBER_WS \u914D\u7F6E\u3002" })] }));
}
