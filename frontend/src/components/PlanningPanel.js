import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from 'react';
import { generatePlans } from '../api';
export function PlanningPanel({ plans, extraction }) {
    const [data, setData] = useState(plans);
    const [msg, setMsg] = useState('');
    const [busy, setBusy] = useState(false);
    const shown = data ?? plans;
    async function gen() {
        setBusy(true);
        setMsg('正在生成筹划…（未配置模型时会原样返回模板并注明）');
        try {
            const r = await generatePlans(extraction);
            setData(r);
            setMsg(r.note ?? '');
        }
        catch (e) {
            setMsg(`生成失败：${String(e)}`);
        }
        finally {
            setBusy(false);
        }
    }
    if (!shown)
        return _jsxs("section", { className: "panel", children: [_jsx("h2", { children: "\u7B79\u5212 \u00B7 21 \u660E\u786E / 4 \u77E5 / 6 \u6784\u60F3" }), _jsx("p", { className: "panel-desc", children: "\u5148\u4E0A\u4F20 Word\uFF0C\u63D0\u53D6\u5B8C\u6210\u540E\u8FD9\u91CC\u4F1A\u51FA\u73B0 21/4/6 \u7ED3\u6784\u3002" })] });
    return (_jsxs("section", { className: "panel", children: [_jsx("h2", { children: "\u7B79\u5212 \u00B7 21 \u660E\u786E / 4 \u77E5 / 6 \u6784\u60F3" }), shown.note && _jsx("p", { className: "note", children: shown.note }), _jsx("div", { className: "form-row", children: _jsx("button", { className: "primary", disabled: busy, onClick: gen, children: "\u751F\u6210\u7B79\u5212\uFF08\u9700\u914D\u7F6E\u6A21\u578B\uFF09" }) }), shown.stages.map((s) => (_jsxs("div", { children: [_jsxs("h3", { children: [s.stage, "\uFF08", s.count, " \u9879\uFF09"] }), _jsx("p", { className: "note", children: s.note }), _jsxs("table", { className: "table", children: [_jsx("thead", { children: _jsxs("tr", { children: [_jsx("th", { children: "\u7F16\u53F7" }), _jsx("th", { children: "\u5185\u5BB9" }), _jsx("th", { children: "\u72B6\u6001" }), _jsx("th", { children: "\u6EAF\u6E90" })] }) }), _jsx("tbody", { children: s.items.map((it) => (_jsxs("tr", { children: [_jsx("td", { children: it.id }), _jsx("td", { children: it.title || '（待生成）' }), _jsx("td", { children: it.status }), _jsx("td", { children: it.source || '—' })] }, it.id))) })] })] }, s.prefix)))] }));
}
