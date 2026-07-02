# 后端 LLM 适配层文档

> **更新日期**：2026-07-02
> **版本**：v0.9.6
> **Commit**：e717e5b
> **代码定位**：`backend/adapters/`

---

## 目录

1. [适配层定位](#1-适配层定位)
2. [类型与配置（types.py）](#2-类型与配置typespy)
3. [LLMAdapter 统一入口](#3-llmadapter-统一入口)
4. [LLMRouter（路由表）](#4-llmrouter路由表)
5. [重试机制（retry.py）](#5-重试机制retrypy)
6. [流式回调（streaming.py）](#6-流式回调streamingpy)
7. [Provider 实现](#7-provider-实现)
8. [数据流示例](#8-数据流示例)

---

## 1. 适配层定位

`backend/adapters/` 是**隔离 LLM 协议差异**的适配层。业务代码（agent / service / api）只调 `LLMAdapter`，不直接依赖 OpenAI SDK / Google SDK / 其他提供方。

### 1.1 设计目标

- **统一接口**：4 个调用入口（`complete / complete_with_messages / stream / generate_image`）覆盖所有业务场景
- **路由**：根据 `ModelRole` 选 Provider（text → DeepSeek，image → Gemini）
- **重试**：指数退避 1s → 2s → 4s，自动重试 3 次
- **流式**：async generator 模式 + 回调（WS 推送）
- **协议透明**：DeepSeek 走 OpenAI 兼容协议（thinking 模式 + tool_calls）；Gemini 走 Google 原生异步 submit + poll

### 1.2 模块结构

```
adapters/
├── llm_adapter.py          # 统一入口
├── llm_router.py           # 路由表
├── types.py                # Pydantic Schema
├── retry.py                # 指数退避
├── streaming.py            # 流式回调封装
└── providers/
    ├── base.py             # LLMProvider Protocol
    ├── deepseek.py         # friday/deepseek-v4-pro-tencent
    └── gemini.py           # friday/gemini-3.1-flash-image-preview
```

### 1.3 调用规则

- ❌ 业务代码不直接 `import openai` 或 `import google.generativeai`
- ✅ 业务代码只 `from backend.adapters.llm_adapter import get_llm_adapter`
- ❌ 业务代码不直接 new Provider
- ✅ 业务代码只 `await adapter.complete(request)` / `await adapter.generate_image(...)`

---

## 2. 类型与配置（types.py）

`backend/adapters/types.py`

### 2.1 Enum

```python
class ModelRole(str, Enum):
    TEXT = "text"      # 推理/对话 → friday/deepseek-v4-pro-tencent
    IMAGE = "image"    # 图片生成 → friday/gemini-3.1-flash-image-preview

class ModelProvider(str, Enum):
    DEEPSEEK = "friday/deepseek-v4-pro-tencent"
    GEMINI = "friday/gemini-3.1-flash-image-preview"
```

`ModelProvider` 命名规范：v0.7 起加 `friday/` 前缀表示「**提供方**」，未来会有 `deepseek/xxx`、`minimax/xxx` 等原生 Provider。

### 2.2 LLMRequest

`types.py:24` — 统一的 LLM 调用请求。

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `prompt` | str | `""` | 单轮模式：纯 prompt（与 messages 互斥） |
| `messages` | List[Dict] | `[]` | 多轮模式：OpenAI 格式 messages 数组（v0.4.1 加） |
| `role` | ModelRole | TEXT | 决定走哪个 Provider |
| `temperature` | float | 0.7 | 0~2 |
| `max_tokens` | int | 8192 | 1~16384 |
| `system_prompt` | Optional[str] | None | 单独字段（自动插到 messages 首位） |
| `stream` | bool | False | 是否流式（实际由 `adapter.stream` 单独走） |
| `response_format` | Optional[Dict] | None | 强制 JSON 输出（透传 OpenAI） |
| `frequency_penalty` | float | 0.0 | -2~2，v0.8.1 探索度旋钮用 |
| `presence_penalty` | float | 0.0 | -2~2，v0.8.1 探索度旋钮用 |
| `enable_thinking` | bool | True | v0.8.2 DeepSeek thinking 模式开关 |
| `tools` | Optional[List[Dict]] | None | v0.6 OpenAI function calling 工具列表 |
| `tool_choice` | Optional[Any] | None | `'auto' / 'none' / 'required' / {type:function, ...}` |

### 2.3 LLMResponse

`types.py:73` — 同步调用响应。

| 字段 | 类型 | 说明 |
|------|------|------|
| `content` | str | LLM 文本回复（无 tool_calls 时） |
| `tool_calls` | Optional[List[ToolCall]] | v0.6 LLM 决定调工具时填这个 |
| `provider` | ModelProvider | 实际命中的 Provider |
| `input_tokens / output_tokens` | int | Token 用量 |
| `duration_ms` | int | 耗时（毫秒） |
| `cached` | bool | 是否命中缓存（v0.9 预留） |

### 2.4 LLMStreamChunk

`types.py:91` — 流式输出 chunk。

| 字段 | 类型 | 说明 |
|------|------|------|
| `delta` | str | 本 chunk 的内容增量 |
| `reasoning` | str | thinking 模式的 reasoning_content（DeepSeek） |
| `provider` | ModelProvider | |
| `is_final` | bool | 是否最后一个 chunk |
| `finish_reason` | Optional[str] | `stop` / `length` / `tool_calls` / `content_filter` |
| `tool_calls_delta` | Optional[List[Dict]] | v0.6 流式累积 tool_calls 增量 |

### 2.5 ToolCall / ToolCallFunction

`types.py:60` — OpenAI 协议格式：
```python
class ToolCallFunction(BaseModel):
    name: str
    arguments: str  # JSON 字符串，调用方需手动 json.loads

class ToolCall(BaseModel):
    id: str
    type: str = "function"
    function: ToolCallFunction
```

---

## 3. LLMAdapter 统一入口

`backend/adapters/llm_adapter.py`

### 3.1 4 个调用入口

#### `complete(request: LLMRequest) -> LLMResponse`

`llm_adapter.py:69` — **同步调用（带重试）**

```python
provider = self.router.get_provider(request.role)
return await with_retry(provider.complete, request, max_retries=3, base_delay=1.0)
```

#### `complete_with_messages(messages, system_prompt, temperature, max_tokens, role, frequency_penalty, presence_penalty, enable_thinking) -> LLMResponse`

`llm_adapter.py:80` — **多轮对话便捷调用**（v0.4.1 加）。内部构造 `LLMRequest(prompt="", messages=messages, ...)` 再调 `complete`。

#### `stream(request: LLMRequest) -> AsyncIterator[LLMStreamChunk]`

`llm_adapter.py:118` — **流式调用（不重试）**

```python
async for chunk in provider.stream(request):
    yield chunk
```

#### `stream_with_callback(request, on_chunk) -> LLMStreamChunk`

`llm_adapter.py:127` — **流式 + 回调（WS 推送用）**。内部调 `streaming.stream_with_callback`。

#### `generate_image(prompt, aspect_ratio="1:1", image_size="1K", reference_image_url=None) -> dict`

`llm_adapter.py:135` — **图片生成**（Gemini 专属）

```python
provider = self.router.get_provider(ModelRole.IMAGE)
if not hasattr(provider, "generate_image"):
    raise NotImplementedError(...)
return await with_retry(provider.generate_image, prompt, aspect_ratio, image_size, reference_image_url, max_retries=3, base_delay=1.0)
```

返回 `dict: {image_urls, description, duration_ms, cached}`。

### 3.2 全局单例

```python
# llm_adapter.py:160
_adapter: Optional[LLMAdapter] = None

def get_llm_adapter() -> LLMAdapter:
    global _adapter
    if _adapter is None:
        _adapter = LLMAdapter()
    return _adapter

def reset_llm_adapter() -> None:
    global _adapter
    _adapter = None
```

### 3.3 Prompt 日志

`llm_adapter.py:23` — 设置环境变量 `LLM_PROMPT_LOG=1` 即可开启完整 prompt 打印（独立于 `LOG_LEVEL`），便于调试。

### 3.4 典型调用代码

```python
# 文本生成（带重试）
adapter = get_llm_adapter()
request = LLMRequest(
    prompt="写一段剑客",
    temperature=0.7,
    max_tokens=2048,
    role=ModelRole.TEXT,
    enable_thinking=True,
)
response = await adapter.complete(request)
print(response.content)

# 多轮对话
response = await adapter.complete_with_messages(
    messages=[
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！"},
        {"role": "user", "content": "继续"},
    ],
    system_prompt="你是助手",
)

# 流式
async for chunk in adapter.stream(request):
    if chunk.delta:
        print(chunk.delta, end="", flush=True)

# 图片生成
result = await adapter.generate_image(
    prompt="A fantasy sword hero",
    aspect_ratio="1:1",
    image_size="1K",
)
image_urls = result["image_urls"]
```

---

## 4. LLMRouter（路由表）

`backend/adapters/llm_router.py`

### 4.1 路由策略

**v0.7 改造**：不再写死 primary_map，从 `agents.json` 的 `models` 池查 Provider。

```python
# llm_router.py:22
_MODEL_TO_PROVIDER = {
    "friday/deepseek-v4-pro-tencent": ModelProvider.DEEPSEEK,
    "friday/gemini-3.1-flash-image-preview": ModelProvider.GEMINI,
}
```

### 4.2 关键方法

#### `get_provider_by_name(model_name) -> LLMProvider`

`llm_router.py:33` — 根据 model_name 查 Provider：
1. 查静态映射 `_MODEL_TO_PROVIDER` → ModelProvider enum
2. fallback：遍历 `providers` 字典匹配 `provider_name`
3. 都没找到 → `raise RuntimeError`

#### `get_provider(role) -> LLMProvider`

`llm_router.py:49` — **保留旧接口（向后兼容）**：根据 `ModelRole` 选 Provider
- `TEXT` → DeepSeek
- `IMAGE` → Gemini
- 其它 → `raise RuntimeError`

#### `get_provider_names() -> list[str]`

`llm_router.py:62` — 列所有已注册的 Provider 名（供 `/api/info` 使用）

### 4.3 全局单例

```python
# llm_router.py:73
def get_router() -> LLMRouter:
    global _router
    if _router is None:
        cfg = load_agents_config()  # 读 agents.json
        models = cfg["models"]
        providers: dict[ModelProvider, LLMProvider] = {}
        for model_name in models:
            if model_name == "friday/deepseek-v4-pro-tencent":
                providers[ModelProvider.DEEPSEEK] = DeepSeekProvider()
            elif model_name == "friday/gemini-3.1-flash-image-preview":
                providers[ModelProvider.GEMINI] = GeminiProvider()
        _router = LLMRouter(providers)
    return _router
```

`get_model_config(model_name)` 走 `config_loader` 读 `base_url / model_id / submit_url / default_params`。

### 4.4 扩展新 Provider

1. 在 `backend/adapters/providers/` 新建 `<name>.py`，实现 `LLMProvider` Protocol
2. 在 `llm_router.py:97` 加 `elif` 分支：`providers[ModelProvider.<NAME>] = <Name>Provider()`
3. 在 `types.py` 的 `ModelProvider` enum 加新值
4. 在 `agents.json` 加新 model 字段
5. 在 `ModelRole` 加新 role（如 `AUDIO`）如适用

---

## 5. 重试机制（retry.py）

`backend/adapters/retry.py`

### 5.1 指数退避

```python
# retry.py:25
async def with_retry(func, *args, max_retries=3, base_delay=1.0, **kwargs):
    """指数退避：1s → 2s → 4s（最多 3 次重试）"""
    for attempt in range(max_retries + 1):  # 0,1,2,3 = 4 次
        try:
            return await func(*args, **kwargs)
        except AuthenticationError:
            raise  # 鉴权失败立即抛
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)  # 1, 2, 4
                await asyncio.sleep(delay)
    if last_error:
        raise last_error
```

**退避序列**：`base_delay * 2^attempt` = 1s, 2s, 4s（attempt=0,1,2 重试前各 sleep 一次）

### 5.2 异常分类

| 异常 | 是否重试 | 触发条件 |
|------|---------|---------|
| `AuthenticationError` | ❌ 立即抛 | 鉴权失败（API key 错、模型无权限） |
| `RateLimitError` | ✅ 退避 | 限流 |
| 其它 `Exception` | ✅ 退避 | 网络、超时、上游 5xx |

`AuthenticationError / RateLimitError` 均为 `retry.py:7,15` 自定义异常，目前**没有 Provider 主动抛**，是预留扩展点。

### 5.3 调用约定

`LLMAdapter` 在两个地方用 `with_retry`：
- `complete`（`llm_adapter.py:74`）：`max_retries=3, base_delay=1.0`
- `generate_image`（`llm_adapter.py:144`）：`max_retries=3, base_delay=1.0`
- `stream`：**不重试**（`llm_adapter.py:118`），调用方自己处理

---

## 6. 流式回调（streaming.py）

`backend/adapters/streaming.py`

```python
# streaming.py:9
async def stream_with_callback(
    provider: LLMProvider,
    request: LLMRequest,
    on_chunk: Callable[[LLMStreamChunk], Awaitable[None]],
) -> LLMStreamChunk:
    """流式输出 + 回调（用于 WebSocket 实时推送）"""
    last_chunk: LLMStreamChunk | None = None
    async for chunk in provider.stream(request):
        await on_chunk(chunk)
        last_chunk = chunk
    if last_chunk is None:
        raise RuntimeError("Provider produced no chunks")
    return last_chunk
```

**返回最后一个 chunk**（含 `finish_reason`），调用方在所有 chunk 处理完后可读 `last_chunk.finish_reason`。

---

## 7. Provider 实现

`backend/adapters/providers/` 下 2 个 Provider（v0.9.6），全部实现 `LLMProvider` Protocol（`base.py:9`）。

### 7.1 LLMProvider Protocol

```python
# base.py:9
@runtime_checkable
class LLMProvider(Protocol):
    provider_name: str
    supported_roles: list[str]
    
    async def complete(self, request: LLMRequest) -> LLMResponse
    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamChunk]
    def is_available(self) -> bool
    async def generate_image(self, prompt, aspect_ratio, image_size, reference_image_url) -> dict
```

**text-only Provider**（如 DeepSeek）实现 `generate_image` 时直接 `raise NotImplementedError`。
**image-only Provider**（如 Gemini）实现 `complete / stream` 时直接 `raise NotImplementedError`。

### 7.2 DeepSeekProvider

`backend/adapters/providers/deepseek.py`

**元信息**：
- `provider_name = "friday/deepseek-v4-pro-tencent"`
- `supported_roles = ["text"]`
- 协议：OpenAI 兼容（经 friday 代理）
- SDK：`openai.AsyncOpenAI`
- 模型：`deepseek-v4-pro-tencent`（去掉 `friday/` 前缀的真实 model id）

**构造**（`deepseek.py:24`）：
- `api_key` 走 `config_loader.load_llm_api_key()`（读 `.llm_api_key` 文件）
- `base_url` / `model` 走 `config_loader.get_model_config("friday/deepseek-v4-pro-tencent")`
- `default_params` 走 model_cfg

**complete() — 同步调用**（`deepseek.py:42`）

> DeepSeek v4-pro thinking 模式下**非流式调用 content 始终为空**，答案在 `reasoning_content` 里且容易被 max_tokens 截断。改用**流式聚合 content delta**，与 `stream()` 行为一致。

```python
stream_kwargs = {
    "model": self.model,
    "messages": self._build_messages(request),
    "temperature": request.temperature,
    "max_tokens": request.max_tokens,
    "stream": True,
    "extra_body": {"thinking": {"type": "enabled" if request.enable_thinking else "disabled"}},
}
# 透传 frequency_penalty / presence_penalty / response_format / tools / tool_choice
```

累积 `content_parts` + `tool_calls_accumulator`（OpenAI 协议按 fragment 返回）。

**stream() — 流式调用**（`deepseek.py:131`）

每 chunk 提取：
- `delta.content` → `LLMStreamChunk.delta`
- `delta.reasoning_content` → `LLMStreamChunk.reasoning`（thinking 模式）
- `delta.tool_calls` → `LLMStreamChunk.tool_calls_delta`（v0.6）

**_build_messages()**（`deepseek.py:200`）

优先用 `request.messages`（多轮），自动补 `system_prompt` 到首位。兼容旧单轮 `request.prompt`。

**Thinking 模式开关**（v0.8.2）：
- `enable_thinking=True` → `thinking.type=enabled`（默认）
- `enable_thinking=False` → `thinking.type=disabled`（轻量任务如 summary/分类，防止 reasoning token 占用 max_tokens）

**generate_image()**：`raise NotImplementedError("DeepSeek only supports text, use GeminiProvider for images")`

### 7.3 GeminiProvider

`backend/adapters/providers/gemini.py`

**元信息**：
- `provider_name = "friday/gemini-3.1-flash-image-preview"`
- `supported_roles = ["image"]`
- 协议：Google 原生异步（submit + poll，经 friday 代理）
- SDK：`httpx.AsyncClient`（不用 google SDK）
- 端点：`submit_url` / `query_url_template` 走 `agents.json`

**构造**（`gemini.py:21`）：
- `api_key` 走 `config_loader.load_llm_api_key()`
- `SUBMIT_URL` / `QUERY_URL_TEMPLATE` 走 `get_model_config`
- `POLL_INTERVAL` / `POLL_TIMEOUT` 走 `default_params`（默认 3s / 120s）

**generate_image()**（`gemini.py:35`）— **异步提交 + 轮询**：

```
1. parts = [{"text": prompt}] + (可选 reference image file_data)
2. payload = {
     "contents": [{"parts": parts}],
     "generationConfig": {
       "responseModalities": ["TEXT", "IMAGE"],
       "imageConfig": {"aspectRatio": "1:1", "imageSize": "1K"},
     },
   }
3. POST SUBMIT_URL → 拿 task_id（纯字符串）
4. loop (until POLL_TIMEOUT):
     GET QUERY_URL_TEMPLATE.format(operation_id=task_id)
     status=0: 生成中 → sleep POLL_INTERVAL
     status=1: 成功 → parse + return
     status=-1: 失败 → raise RuntimeError
5. 超过 POLL_TIMEOUT → raise TimeoutError
```

**结果解析**（`_parse_gemini_result`，`gemini.py:91`）：

遍历 `data.candidates[].content.parts[]`：
- `part.text` → `description`（截断 200 字）
- `part.inlineData.data` → `image_urls`（base64 raw bytes）
- `part.fileData.fileUri` → `image_urls`（直接 URL）
- fallback：`data.imageUrl` 字段

返回 `{"image_urls": [...], "description": "..."}`，外加 `duration_ms` 和 `cached=False`（由 `generate_image` 包装时加）。

**complete() / stream()**：`raise NotImplementedError("Gemini only supports image generation, use generate_image() instead")`

**Reference Image**：`reference_image_url` 非空时拼到 parts 末尾：
```python
{"file_data": {"mime_type": "image/png", "file_uri": reference_image_url}}
```

---

## 8. 数据流示例

### 8.1 章节生成：Butlers → NovelWriter → LLMAdapter → DeepSeek 流式

```
[NovelWriterAgent] 需要生成第 N 章
  ↓
[Chapter Context Builder]
  ├── 读 7 件基座 (WorldTree / StyleCharter / GenreResonance / MainPlot / SubPlot / CharacterCard / SeedTable)
  ├── 读历史章节摘要 (last 3)
  ├── 读 seeds 当前状态
  ├── 读 chapter_status 查最新
  └── 组装 prompt + messages
  ↓
[NovelWriterAgent]
  request = LLMRequest(
      messages=[{"role": "system", "content": "你是文笔家..."}, ...],
      system_prompt=None,  # 已放 messages 首位
      temperature=0.8,
      max_tokens=8192,
      role=ModelRole.TEXT,
      enable_thinking=True,
  )
  ↓
[LLMAdapter.stream]
  provider = router.get_provider(ModelRole.TEXT)
  → DeepSeekProvider
  ↓
[DeepSeekProvider.stream]
  async for chunk in self.client.chat.completions.create(model=..., stream=True, extra_body={thinking: enabled}):
      yield LLMStreamChunk(
          delta=chunk.choices[0].delta.content or "",
          reasoning=chunk.choices[0].delta.reasoning_content or "",
          ...
      )
  ↓
[NovelWriterAgent WS 推送循环]
  async for chunk in adapter.stream(request):
      if chunk.reasoning:
          await ws.send_json({"type": "reasoning", "delta": chunk.reasoning})
      if chunk.delta:
          accumulated += chunk.delta
          await ws.send_json({"type": "content", "delta": chunk.delta})
      if chunk.is_final:
          await ws.send_json({"type": "done", "finish_reason": chunk.finish_reason})
  ↓
[ContentValidator]
  ├── 字数检查 (2000~4000 汉字)
  ├── ConsistencyChecker.check_hard_rules (硬约束)
  ├── ConsistencyChecker.check_world_entries (知识矛盾)
  └── 通过 → 落库
  ↓
[ChapterRepository.create]
  ├── 写 data/projects/{id}/chapters/chapter_NNN.md
  ├── 落 DB (chapters + chapter_status)
  └── 推 WS chapter_generated
```

### 8.2 封面图生成：CoverImageGenerator → LLMAdapter → Gemini 异步轮询

```
[Onboarding Hooks.handle_step4_confirmed]
  payload = load_payload(project_id)
  ↓
[CoverImageGenerator.generate_and_save_cover]
  prompt = build_cover_prompt(payload)
  ↓
[LLMAdapter.generate_image]
  provider = router.get_provider(ModelRole.IMAGE)
  → GeminiProvider
  with_retry(provider.generate_image, prompt, "1:1", "1K", None, max_retries=3, base_delay=1.0)
  ↓
[GeminiProvider.generate_image]
  Step 1: POST SUBMIT_URL → task_id="op-abc123"
  Step 2: loop (interval=3s, timeout=120s):
            GET query_url/op-abc123
            status=0 → sleep 3
            status=1 → break
  Step 3: _parse_gemini_result → {image_urls: [<base64>], description: "..."}
  ↓
[CoverImageGenerator.generate_and_save_cover]
  image_data = result["image_urls"][0]  # base64 raw bytes
  image_bytes = base64.b64decode(image_data)
  cover_path.write_bytes(image_bytes)
  return "/static/projects/{id}/cover.png"
  ↓
[Onboarding Hooks]
  ProjectRepository.update_cover_image_url(project_id, "/static/projects/{id}/cover.png")
  ↓
[WS 推送]
  await ws.send_json({"type": "cover_image_updated", "url": "..."})
  ↓
[前端]
  显示封面图
```
