# 星澜数字人教师 xinglan-teacher

左侧星澜数字人教师，右侧 pi-web 聊天；教师上传今日手写 Word（.docx，5M 以内），
后端按平台标准槽位提取（找不到填 null，不编造），再做 21 明确 / 4 知 / 6 构想筹划。

## 端口（不要和槽位填充混了）
- 本应用前端：5179（5175 是槽位填充）
- 本应用后端：8005
- pi-web（已部署那套）：30141，数字人后端：12393，见 PiChat 页填地址

## 运行
后端（backend 目录）：`python3 run.py --port 8005`（需 python-docx 才能解析 docx：`pip install python-docx`）
前端（frontend 目录）：`npm install`，再 `npm run dev` → http://localhost:5179
模型配置：前端“模型配置”页填阿里云百炼 Key、地址、模型名（35B/27B/9B 档位，见槽位填充那套），
筹划生成需要模型；未配置时筹划页原样返回 21/4/6 结构模板并注明，不假装生成过。

## 结构
- backend/slotfill/：提取引擎，复用槽位填充（代码/LLM/混合/Agent、校验门、百炼配置）
- backend/teacher.py：Word 上传、平台标准槽位（platform_slots.json，可改）、21/4/6 模板（plans.json）
- frontend/src/components/TeacherPanel.tsx：左侧星澜状态机 idle/thinking/explaining，连 VTuber WS（VITE_VTUBER_WS）
- frontend/src/components/PiChat.tsx：右侧 pi-web，地址由用户填，不嵌 iframe 冒充、不伪造回复

## 诚实边界
- 21/4/6 只是结构模板，内容必须由 Word 或已配置模型生成后填入；知项必须带溯源。
- 数字人真模型与语音走已部署的 Open-LLM-VTuber 与 TTS 服务，本仓库不内置假模型。
- 图片与文档二进制不走 GitHub 连接器推送；如需 WSL 部署，先 clone 源码，再传 public 资源包。
