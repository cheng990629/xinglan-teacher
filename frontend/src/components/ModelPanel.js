import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useState } from 'react';
import { getConfig, saveConfig, testConfig } from '../api';
// 模型配置页：只做三件事——填百炼 Key、选地址、选模型档位/模型名。
// Key 只发给后端、只存后端 .env（600 权限），接口永不回完整 Key；
// 档位只是建议值，真正生效的是模型名框里的值，框里可自由改。
const TIERS = [
    { key: '35B', label: '35B 级（大）', suggestion: 'qwen3-32b', note: '百炼 32B 级大模型，抽取最稳，适合错版多的文档' },
    { key: '27B', label: '27B 级（中）', suggestion: 'gemma-2-27b-it', note: '按你百炼开通的模型名改，框里可自由填' },
    { key: '9B', label: '9B 级（小）', suggestion: 'qwen3-8b', note: '百炼 8B 级小模型，最快最便宜，适合格式规整的文档' },
    { key: 'custom', label: '自定义', suggestion: '', note: '百炼千问 Plus/Max（qwen-plus、qwen-max 等）直接填模型名' },
];
export function ModelPanel() {
    const [cfg, setCfg] = useState(null);
    const [baseUrl, setBaseUrl] = useState('https://dashscope.aliyuncs.com/compatible-mode/v1');
    const [apiKey, setApiKey] = useState('');
    const [tier, setTier] = useState('9B');
    const [model, setModel] = useState('qwen3-8b');
    const [msg, setMsg] = useState('');
    const [busy, setBusy] = useState(false);
    useEffect(() => {
        void getConfig().then((c) => {
            setCfg(c);
            if (c.base_url)
                setBaseUrl(c.base_url);
            if (c.model)
                setModel(c.model);
        }).catch((e) => setMsg(`读取配置失败：${String(e)}`));
    }, []);
    function pickTier(key) {
        setTier(key);
        const t = TIERS.find((x) => x.key === key);
        if (t && t.suggestion)
            setModel(t.suggestion);
    }
    async function onSave() {
        setBusy(true);
        setMsg('');
        try {
            const c = await saveConfig({ api_key: apiKey || undefined, base_url: baseUrl, model });
            setCfg(c);
            setApiKey('');
            setMsg('已保存到后端 .env，之后提交的提取任务无需重启即可用新配置。');
        }
        catch (e) {
            setMsg(`保存失败：${String(e)}`);
        }
        finally {
            setBusy(false);
        }
    }
    async function onTest() {
        setBusy(true);
        setMsg('正在测试连接…');
        try {
            const r = await testConfig({ api_key: apiKey || undefined, base_url: baseUrl, model });
            setMsg(r.ok ? `连接成功：模型 ${r.model}，耗时 ${r.latency_ms}ms，模型回复：${r.reply}` : `连接失败：${r.error}`);
        }
        catch (e) {
            setMsg(`测试失败：${String(e)}`);
        }
        finally {
            setBusy(false);
        }
    }
    return (_jsxs("section", { className: "panel", children: [_jsx("h2", { children: "\u6A21\u578B\u914D\u7F6E \u00B7 \u963F\u91CC\u4E91\u767E\u70BC" }), _jsxs("p", { className: "panel-desc", children: ["\u767E\u70BC\u8D70 OpenAI \u517C\u5BB9\u534F\u8BAE\uFF0C\u53EA\u6539\u5730\u5740\u3001Key\u3001\u6A21\u578B\u540D\u4E09\u9879\u5C31\u80FD\u7528\u3002\u540E\u7AEF\u5DF2\u7ECF\u662F\u8FD9\u4E2A\u534F\u8BAE\uFF0C \u4E0D\u7528\u6362\u4EE3\u7801\u3002\u5F53\u524D\u72B6\u6001\uFF1A", cfg ? (cfg.has_api_key ? `已填 Key（${cfg.api_key_masked}）` : '未填 Key') : '读取中…', cfg && cfg.model ? `，当前模型 ${cfg.model}` : '', cfg && cfg.is_bailian ? '，地址是百炼' : ''] }), _jsxs("div", { className: "form-grid", children: [_jsxs("label", { children: ["\u767E\u70BC\u5730\u5740\uFF08base_url\uFF09", _jsx("input", { value: baseUrl, onChange: (e) => setBaseUrl(e.target.value), placeholder: "https://dashscope.aliyuncs.com/compatible-mode/v1" }), _jsxs("span", { className: "note", children: ["\u9ED8\u8BA4\u662F\u767E\u70BC\u901A\u7528\u5730\u5740\uFF1B\u5982\u679C\u4F60\u7684 Key \u5C5E\u4E8E\u67D0\u4E2A\u4E1A\u52A1\u7A7A\u95F4\uFF0C\u6539\u6210 https://", '{WorkspaceId}', ".cn-beijing.maas.aliyuncs.com/compatible-mode/v1\uFF0C\u4E0D\u8981\u5E26 /chat/completions\u3002"] })] }), _jsxs("label", { children: ["\u767E\u70BC API Key", _jsx("input", { type: "password", value: apiKey, onChange: (e) => setApiKey(e.target.value), placeholder: "\u7559\u7A7A\u8868\u793A\u4E0D\u6539\u5DF2\u4FDD\u5B58\u7684 Key" }), _jsx("span", { className: "note", children: "\u53EA\u53D1\u7ED9\u540E\u7AEF\u3001\u53EA\u5B58\u540E\u7AEF .env\uFF08600 \u6743\u9650\uFF09\uFF0C\u9875\u9762\u548C\u63A5\u53E3\u90FD\u4E0D\u4F1A\u518D\u663E\u793A\u5B8C\u6574 Key\u3002\u4E0D\u8981\u628A Key \u53D1\u5230\u804A\u5929\u91CC\u3002" })] })] }), _jsx("h3", { children: "\u6A21\u578B\u6863\u4F4D" }), _jsx("div", { className: "mode-row", children: TIERS.map((t) => (_jsxs("label", { className: `mode ${tier === t.key ? 'active' : ''}`, children: [_jsx("input", { type: "radio", name: "tier", checked: tier === t.key, onChange: () => pickTier(t.key) }), _jsx("strong", { children: t.label }), _jsx("span", { children: t.note })] }, t.key))) }), _jsxs("label", { children: ["\u6A21\u578B\u540D\uFF08\u771F\u6B63\u751F\u6548\u7684\u503C\uFF0C\u53EF\u81EA\u7531\u6539\uFF09", _jsx("input", { value: model, onChange: (e) => setModel(e.target.value), placeholder: "\u4F8B\u5982 qwen3-32b\u3001qwen-plus\u3001qwen-max" })] }), _jsxs("div", { className: "form-row", children: [_jsx("button", { className: "primary", disabled: busy, onClick: onSave, children: "\u4FDD\u5B58\u914D\u7F6E" }), _jsx("button", { className: "ghost", disabled: busy, onClick: onTest, children: "\u6D4B\u8BD5\u8FDE\u63A5" })] }), msg && _jsx("p", { className: "note", "aria-live": "polite", children: msg }), _jsx("h3", { children: "\u4FDD\u5B58\u540E\u600E\u4E48\u7528" }), _jsx("p", { className: "panel-desc", children: "\u56DE\u5230\u201C\u63D0\u53D6\u201D\u9875\uFF0C\u6A21\u5F0F\u9009 llm\u3001hybrid \u6216 agent \u5C31\u4F1A\u7528\u8FD9\u91CC\u4FDD\u5B58\u7684\u6A21\u578B\u8DD1\uFF1Bcode \u6A21\u5F0F\u4E0D\u8D70\u6A21\u578B\uFF0C\u4E0D\u53D7\u5F71\u54CD\u3002 \u4E5F\u53EF\u4EE5\u76F4\u63A5\u6539\u540E\u7AEF\u76EE\u5F55\u7684 .env\uFF08LLM_BASE_URL / LLM_API_KEY / LLM_MODEL\uFF09\uFF0C\u6548\u679C\u4E00\u6837\uFF0C\u91CD\u542F\u540E\u7AEF\u624D\u751F\u6548\uFF1B \u9875\u9762\u4E0A\u4FDD\u5B58\u662F\u7ACB\u5373\u751F\u6548\uFF0C\u4E0D\u7528\u91CD\u542F\u3002" })] }));
}
