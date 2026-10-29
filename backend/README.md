# 槽位填充后端：基于 LLM 的槽位填充程序（v2）

一句话：用户给一份文本（256K–5M，md / txt / docx / pdf）+ 一份槽位 JSON，
程序返回一份填好槽的 JSON 的 URL，不用 SSE。

```
槽位设计 → 提取器设计 → 方案文件 → 槽位填充
slots.json → 编译校验 → 结构化分块 + 确定性选块 → code / llm / hybrid / agent → Python 校验门 → result.json
```

## 1. 三种模式（+ agent 档 + auto）

| 模式 | 怎么跑 | 适用 | 速度 / 代价 |
|---|---|---|---|
| `code` | 纯 Python 规则：键值、表格、格式、枚举、布尔，零 LLM | 标签化、表格化文档 | 最快：验证集平均 0.008 秒/用例，0 LLM 调用 |
| `llm` | LLM 分组提取，输出 YAML，Python 转 JSON（`python` 是它的旧别名） | 散文、语义槽、疑难槽 | 调用数 ≈ 组数 + 缺失重试数 |
| `hybrid`（默认推荐） | 代码先行，只把缺失、低置信（<0.8）、校验警告、semantic 槽交给 LLM | 绝大多数真实文档 | 代码能解决 40 个槽，LLM 只跑剩下的 10 个 |
| `agent` | ReAct harness：模型自己调 list_sections / search_chunks / read_chunk / submit | 小文档、疑难槽 | 步数预算默认 20 步 |
| `auto` | 先跑代码，覆盖率满且无语义缺失就直接返回（0 LLM 调用），否则走 hybrid；无模型时退化为代码档 | 不想选的时候 | 同 hybrid，但满覆盖时更快 |

三种模式共用同一套槽位编译、选块、校验代码，换模式不换正确性标准。
agent 的工具调用不用原生 `tool_calls`（本地 8b/27b 经常格式漂移），改用文本 JSON action，
submit 的值也可以是 YAML 字符串，解析失败当 observation 喂回。

## 2. 为什么 LLM 输出 YAML，Python 再转 JSON

小模型输出 JSON 常因引号未转义、尾逗号、括号不配对整轮作废；
YAML 的 plain scalar 不需要给中文、引号加转义，长文本还能用块标量，
解析成功率明显高于 JSON。最后统一由 Python（`yaml.safe_load` + 递归转 JSON 兼容类型，
date/datetime 转 ISO 字符串）转成标准 JSON，下游永远拿到 JSON。

YAML 解析失败时有两层兜底，不整轮作废：
1. JSON 抠取回退；2. 行级容错解析（缩进错乱、引号未闭合时逐行抠顶层键值）。
哪一层生效写进 trace 的 `formats_used`，不静默混用。

## 3. 错版格式也要认，保证提取完整

错版指：破表、分隔符混用、值被断行、重复键、空格/编码乱、标题样式乱。
处理分三层，缺一层都会丢槽：

- **解析层**（`documents.py`）：BOM、全角空格、制表符归一化；表格按“含 | 的连续行”成组、
  列数按最长行补齐；docx 表格行列不齐补空串，图片转成 `[图片：alt]` 占位行。
- **代码提取层**（`extract_code.py`）：分隔符全角：、半角:、=、-、多空格、【】、粗体统一认；
  断行值拼回（编码/中文名用 "" 拼，英文句子用空格拼）；重复键同分时后胜；
  数字认中文数字（壹佰贰拾伍万）、日期认 2026/10/29、邮箱认带空格的写法；
  同格式双字段（发件人/收件人邮箱、出发/返程日期）先按键值行区分，不再被第一个值抢。
- **完整性多阶段兜底**（`pipeline.py`）：代码容错 → LLM 扩大选块重试 → 全文格式/枚举扫描 →
  agent 复查（仅显式开启 + 小文档）。每一阶段只填仍缺失的槽，不覆盖已校验的高置信结果；
  最终 missing 清单和每槽的填充阶段都写进 trace，完整率可审计，不是口头保证。

## 4. 标题错乱：大标题小标题段落

标题层级本身不可信，所以：

- **不按 H1>H2>H3 建树**：所有标题（#、章节、编号、【】）只当扁平分界线，
  层级跳号（H3 后面直接 H1）、同标题在不同层级重复，都不影响切分，内容按顺序保留。
- **标题归一化**：`### 合同金额`、`#合同金额：`、`1. 合同金额`、`【合同金额】`归一后都是“合同金额”，
  选块、分组、代码提取按标题匹配时，不会因为作者把大标题写成小标题就丢证据。
- **段落误作标题**：带冒号且冒号后有值的行是键值行，不是标题（例如“甲方：沈阳晨光科技有限公司”），
  绝不当标题切分；docx 里 Heading 被误标在长段落/键值行上时降级为正文。
- **标题误作段落**：没用 #、没用 Heading 样式的编号/【】标题也认作分界线。
- **碎小节合并**：标题错乱常把文档切成一堆只有标题、没有正文的碎块，分块时 <800 字的碎块和下一块合并，
  避免 LLM 一块只能看到标题、看不到正文。

## 5. 文档类型与图片、表格

- **txt / md**：标题、键值、表格、图片行原样保留；md 表格和图片 `![alt](...)` 都进证据。
- **docx**：段落按样式转标题，表格转成 `| 列 | 行`（保留行列关系），图片转成 `[图片：alt]` 占位行并记入 trace 的 `image_count`。
- **pdf**：按页切分（需要 pypdf）。
- **图片诚实边界**：图片像素本身不含文本，程序不假装能“读图”。能用的是图片的 alt、
  紧邻的图片说明段落、以及图片位置。需要读图里文字时，必须另接 OCR，那是可选外挂，不是默认能力。
- **表格**：array-of-objects 恒走表格（真实订单明细本来就是表格），表头按属性描述/键匹配列，
  破表时按最长行补齐、缺分隔行也认。

## 6. 槽位 JSON（强约束原样支持）

```json
{"slots": {
  "company_name": {"desc": "合同甲方公司全称", "type": "string", "required": true, "length": {"min": 1, "max": 100}},
  "signed_date": {"desc": "合同签署日期", "type": "string", "format": "date", "required": true},
  "service_type": {"desc": "服务类型", "type": "string", "enum": ["咨询", "开发", "运维", "其他"], "required": true},
  "parties": {"desc": "合同各方", "type": "object", "required": true,
              "properties": {"party_a": {"desc": "甲方", "type": "string", "required": true}}},
  "deliverables": {"desc": "交付物清单", "type": "array", "length": {"max": 20},
                   "items": {"desc": "单个交付物", "type": "string"}},
  "summary": {"desc": "一句话归纳核心内容", "type": "semantic", "length": {"max": 100}}
}}
```

支持：`string | number | boolean | object | array | semantic`，以及
`items / properties / length / enum / format / nullable / required`。
约定：string 的 length 是字符数，array 的 length 是元素个数；
`semantic` 一定是 string，是“综合归纳”不是“原文照抄”，代码档注定缺失、混合/LLM 档才填；
非必填缺失统一输出 `null`，必填缺失进 `missing`。

## 7. AgentScope 能不能借鉴？能，但只借骨架

AgentScope 2.0 的核心是 ReAct 循环 + Toolkit + Hook；它的 HarnessAgent 是在 ReAct 之上包的
“长期稳定运行”答案：工作区注入、会话持久化、压缩、子 agent 编排。
本程序借了 ReAct 循环、工具注册表、步数预算和兜底，写成了 `slotfill/harness.py`；
没借会话记忆、工作区人格、SSE 流式、沙箱 shell——那些全是“陪用户聊很久”的能力，
不是“一次性抽完一张表”的能力，搬过来只会污染 prompt、浪费小模型上下文。

为什么 harness agent 感觉“偏向前端、非常好用”：前端错了看得见，截图一对比就知道；
槽位填错了长得像对的，必须靠校验门和 golden 数据。所以后端 harness 的重点不是“跑起来好看”，
而是“错了要老实标 missing，绝不编一个像样的值”。RAG 不精准的根因也一样：
向量相似不等于槽位证据，top-k 丢长尾，跨块字段拼不起来，表格结构被抹掉，
语义字段根本不是检索出来的——所以本程序用结构化分块 + 确定性 BM25 选块 + Python 校验门代替 RAG 作答案来源。

## 8. API（强约束原样落地）

```bash
cp .env.example .env   # 填 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL
python run.py --port 8000
```

```bash
# 异步（推荐，大文档）：先返回 202 + 结果 URL，跑完再取
curl -X POST http://127.0.0.1:8000/api/v1/fill \
  -H 'Content-Type: application/json' \
  -d '{"document_url": "https://example.com/contract.docx",
       "slots_url": "https://example.com/slots.json",
       "extractor": "auto"}'
# -> {"job_id": "...", "status": "processing",
#     "result_url": "/api/v1/results/<job_id>.json",
#     "trace_url": "/api/v1/results/<job_id>/trace.json",
#     "job_url": "/api/v1/jobs/<job_id>"}

curl http://127.0.0.1:8000/api/v1/results/<job_id>.json   # 处理中 202，完成后 200，纯填槽 JSON
curl http://127.0.0.1:8000/api/v1/results/<job_id>/trace.json  # 每槽证据块、警告、missing、阶段
# 同步（小文档 / curl 演示）：body 加 "sync": true，仍带 result_url
# 本地测试也可用 {"document_text": "...", "slots": {...}} 代替两个 URL
# code 模式零 LLM：不配 .env 也能跑；llm/hybrid/agent 模式需要 .env
```

命令行：

```bash
python -m slotfill.cli --document-file examples/document.example.md \
  --slots-file examples/slots.example.json --extractor hybrid \
  --llm-output-format yaml --llm-concurrency 4 \
  --out result.json --trace-out trace.json
```

安全：默认拒绝 `file://` 和内网/回环地址（防 SSRF）；本地联调在 `.env` 里开
`ALLOW_PRIVATE_URLS=1` / `ALLOW_FILE_URLS=1` 再开。文档上限 5M，超了直接拒收。

## 9. 验证集：50 个文件，实测结果

生成：`python validation/generate.py`（10 类 x 5 变体：合同、发票、简历、会议、产品、报告、邮件、订单、招聘、行程）
评分：`python validation/evaluate.py --modes code`（llm/hybrid 模式需 `--allow-llm` 且配好 .env，否则跳过、不造假分）

评分规则：抽取分只算非 semantic 槽（semantic 单独列 filled 数）；object 按子属性计分；
array 按交集/并集或行属性匹配计部分分；速度记每用例耗时和 LLM 调用数。

2026-10-29 本机实测（代码档，零 LLM）：

- **整体抽取分 0.9775，总耗时 0.399 秒，平均 0.008 秒/用例，LLM 调用 0**
- **结构化变体 1.0，错版+标题错乱变体 0.8875**
- 按格式：md 0.9812，txt 0.9718，docx 0.9768；按类型最低是 invoice 0.9333，其余均 ≥0.96
- 未满分用例 6 个，全部是错版用例（contract_04、email_04、invoice_04、job_04、product_04、report_04），
  正好是混合/LLM 档该补的地方，不再为这 6 个特调模板
- 单测：`python -m unittest discover -s tests` —— **13/13 通过**
  （含代码档、错版、标题错乱、YAML 输出、混合档省调用）

**没有实测的部分，老实写出来：** 本机没有配真实模型 key，
真实 8b/27b/35b 的 llm/hybrid/agent 档准确率没有在本轮测到——验证集脚本对这些模式默认跳过，
不拿 FakeLLM 冒充真实模型分数。接上模型后第一步该跑
`python validation/evaluate.py --modes code,hybrid --allow-llm`，看混合档在错版 10 个用例上的提升。

## 10. 模型大小对应的用法（35b / 27b / 8b）

- **8b：** 一次只给一组槽（组内 ≤8 个）、证据总量控制在 12000 字内、temperature 0、
  不用原生 tool_calls、不要一次塞 50 个槽——这是它丢值的头号原因。
- **27b / 35b：** 可以放宽到 agent 模式、组内槽位更多、语义槽更长，但校验门不变：
  模型越大越会编得像，越需要 Python 校验兜底。
- **所有规模共用的底线：** 找不到填 null、不在 enum 里填 null、
  格式不对先纠正（中文日期→ISO）再不行填 null，绝不输出一个“看起来像”的值。

## 11. 目录

```
slotfill/
  config.py         .env 配置（base_url / api_key / model / output_format / concurrency）
  slots.py          槽位编译 + 定义校验
  documents.py      txt / md / docx / pdf 解析，标题归一化、扁平切分、图片占位、错版归一化
  chunking.py       结构化分块 + 碎小节合并
  retrieval.py      确定性 BM25 选块（不用向量）
  llm.py            OpenAI 兼容客户端 + JSON 修复 + FakeLLM（测试用）
  yaml_output.py    YAML 输出 → Python 转 JSON + 两层错版 YAML 兜底
  validate.py       校验门：类型 / 长度 / enum / format / 必填 / 可纠正的格式
  harness.py        AgentScope 骨架的最小实现：ReAct + Toolkit + Hook + 预算
  extract_code.py   代码逻辑提取器（零 LLM）
  extract_llm.py    LLM 提取器（YAML + 分组并发）
  extract_hybrid.py 混合提取器（代码先行，LLM 只补缺）
  extract_agent.py  ReAct harness 提取器（工具只读）
  extract_python.py 兼容层：python = llm 的旧别名
  pipeline.py       编排 + 多阶段完整性兜底 + 阶段记账
  service.py        job 落盘 + URL 取回 + SSRF guard
  server.py         标准库 HTTP 服务（零框架依赖）
  cli.py            命令行入口
tests/              13 个单测
examples/           slots.example.json / document.example.md
validation/         generate.py（50 用例生成）/ evaluate.py（评分）/ cases/ / report.md
```
