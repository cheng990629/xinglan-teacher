import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from 'react';
import { uploadWord } from '../api';
function fileToBase64(file) {
    return new Promise((resolve, reject) => {
        const r = new FileReader();
        r.onload = () => resolve(String(r.result).split(',')[1]);
        r.onerror = () => reject(new Error('读取文件失败'));
        r.readAsDataURL(file);
    });
}
export function UploadPanel({ onExtracted }) {
    const [msg, setMsg] = useState('');
    const [busy, setBusy] = useState(false);
    async function onFile(file) {
        if (!file)
            return;
        if (!file.name.toLowerCase().endsWith('.docx')) {
            setMsg('只接受 .docx：请上传教师手写的 Word 文档');
            return;
        }
        setBusy(true);
        setMsg('正在解析并按平台标准提取…');
        try {
            const b64 = await fileToBase64(file);
            const r = await uploadWord(file.name, b64, 'auto');
            onExtracted(r);
            setMsg(`已解析 ${file.name}，共 ${r.chars} 字；缺失槽位 ${r.missing.length} 个，见下方结果表。`);
        }
        catch (e) {
            setMsg(`提取失败：${String(e)}`);
        }
        finally {
            setBusy(false);
        }
    }
    return (_jsxs("section", { className: "panel", children: [_jsx("h2", { children: "\u4E0A\u4F20\u6559\u5E08\u4ECA\u65E5\u624B\u5199 Word" }), _jsx("p", { className: "panel-desc", children: "\u53EA\u63A5\u53D7 .docx\uFF085M \u4EE5\u5185\uFF09\u3002\u540E\u7AEF\u5148\u89E3\u6790\u6587\u6863\uFF0C\u518D\u6309\u5E73\u53F0\u6807\u51C6\u69FD\u4F4D\uFF08\u8BFE\u7A0B\u3001\u4E3B\u9898\u3001\u76EE\u6807\u3001\u77E5\u8BC6\u70B9\u3001\u73AF\u8282\u3001\u4F5C\u4E1A\u3001\u677F\u4E66\uFF09\u63D0\u53D6\uFF0C\u627E\u4E0D\u5230\u586B null\uFF0C\u4E0D\u7F16\u9020\u3002" }), _jsx("input", { type: "file", accept: ".docx", disabled: busy, onChange: (e) => { void onFile(e.target.files?.[0]); e.target.value = ''; } }), msg && _jsx("p", { className: "note", "aria-live": "polite", children: msg })] }));
}
