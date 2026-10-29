import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from 'react';
// 右侧 pi-web 聊天区：本架子不伪造 pi-web 回复。
// 配好 pi-web 后端地址（下方输入框，默认 WSL 上已部署的 pi-web）后，
// 聊天区以该地址打开 pi-web；未配置时只做本地记录，并明确标注不是 pi-web 回复。
export function PiChat() {
    const [url, setUrl] = useState('');
    const [msgs, setMsgs] = useState([]);
    const [input, setInput] = useState('');
    function send() {
        if (!input.trim())
            return;
        setMsgs((m) => [...m, { role: '你', text: input }, { role: '本地记录', text: '（未接 pi-web 后端时仅本地记录，不是 pi-web 回复。请在上方填入 pi-web 地址后打开 pi-web 聊天。）' }]);
        setInput('');
    }
    return (_jsxs("section", { className: "panel", children: [_jsx("h2", { children: "\u53F3\u4FA7 \u00B7 pi-web \u804A\u5929" }), _jsxs("label", { children: ["pi-web \u5730\u5740\uFF08\u4F8B\u5982\u5DF2\u90E8\u7F72\u7684 http://100.77.50.49:30141/pi\uFF0C\u7559\u7A7A\u5219\u53EA\u672C\u5730\u8BB0\u5F55\uFF09", _jsx("input", { value: url, onChange: (e) => setUrl(e.target.value), placeholder: "http://100.77.50.49:30141/pi" })] }), url ? (_jsxs("div", { className: "piweb-frame-wrap", children: [_jsx("a", { className: "primary", href: url, target: "_blank", rel: "noreferrer", children: "\u5728\u65B0\u6807\u7B7E\u9875\u6253\u5F00 pi-web" }), _jsx("p", { className: "note", children: "\u67B6\u5B50\u7248\u4E0D\u628A pi-web \u5D4C\u8FDB iframe \u5192\u5145\u539F\u751F\u804A\u5929\uFF1B\u5730\u5740\u586B\u597D\u540E\u70B9\u4E0A\u9762\u6309\u94AE\u6253\u5F00\u771F\u6B63\u7684 pi-web\uFF0C\u5DE6\u4FA7\u661F\u6F9C\u72B6\u6001\u4E0E\u804A\u5929\u5185\u5BB9\u7531\u540E\u7AEF WS \u8054\u52A8\u3002" })] })) : (_jsxs("div", { className: "chat-box", children: [msgs.map((m, i) => (_jsxs("p", { children: [_jsxs("strong", { children: [m.role, "\uFF1A"] }), m.text] }, i))), msgs.length === 0 && _jsx("p", { className: "note", children: "\u8FD8\u6CA1\u6709\u6D88\u606F\u3002\u586B\u5165 pi-web \u5730\u5740\uFF0C\u6216\u76F4\u63A5\u5728\u4E0B\u65B9\u8F93\u5165\u505A\u672C\u5730\u8BB0\u5F55\u3002" })] })), _jsxs("div", { className: "form-row", children: [_jsx("input", { value: input, onChange: (e) => setInput(e.target.value), placeholder: "\u8F93\u5165\u95EE\u9898\u2026", onKeyDown: (e) => { if (e.key === 'Enter')
                            send(); } }), _jsx("button", { className: "primary", onClick: send, children: "\u53D1\u9001" })] })] }));
}
