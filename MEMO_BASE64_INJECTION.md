# 备忘录：AstrBot 图像 Base64 自动注入机制

## 1. 设计目标
在不将庞大的 Base64 原始数据发送给大语言模型（LLM）的前提下，确保 MCP 等工具在调用时能够获取到完整的图像数据。
- **节省 Token**：LLM 只处理轻量级的占位符。
- **解决连通性**：针对 Telegram 等平台链接不可直接访问的问题，在服务器本地完成数据准备。
- **自动化**：无需模型手动处理复杂的 Base64 转换。

## 2. 核心架构：Magic Placeholder + Pre-Execution Hook

### A. 占位符机制 (Explicit Tool)
当 LLM 调用 `get_image_from_context` 请求 Base64 模式时，插件不会返回真实的 Base64 字符串，而是返回一个特殊的**魔术占位符**：
- **占位符文本**：`base64://ASTRBOT_PLUGIN_CACHE_PENDING`
- **作用**：作为信号告知 LLM “图片已就绪”，同时通过其特殊的 URI 格式欺骗 LLM 的参数校验（让 LLM 认为这是一个合法的图片地址）。

### B. 拦截注入 (Implicit Hook)
使用 AstrBot 核心提供的 **`@filter.on_using_llm_tool()`** 钩子。
- **触发时机**：在 LLM 决定调用工具之后，但在 `tool_executor` 真正执行工具逻辑**之前**。
- **注入逻辑**：
    1. 拦截所有非 `get_image_from_context` 的工具调用。
    2. 遍历工具参数（`tool_args`）。
    3. **命中条件**：
        - 参数值等于魔术占位符 `base64://ASTRBOT_PLUGIN_CACHE_PENDING`。
        - 参数名属于常用图像字段（`image`, `url`, `data` 等）且值为空或为通用占位符。
    4. **就地修改**：利用 Python 字典的引用传递特性，直接在 `tool_args` 中将占位符替换为真实的 `data:image/jpeg;base64,...` 数据。

## 3. 图像提取与优先级策略
为了保证获取数据的速度和成功率，插件采用以下优先级：

1.  **内存/原生 (Raw Msg)**：检查消息组件中是否已有 `base64://` 开头的数据。
2.  **本地缓存 (Local Path) - [关键]**：检查 `image.path`。如果 AstrBot 核心已经下载了图片（Telegram/QQ 常见情况），直接读取本地文件。**这是最快且最稳定的路径。**
3.  **本地文件 URI (file:///)**：处理本地文件协议。
4.  **网络下载 (Download)**：作为最后手段，调用 `download_image_by_url`。
    - **超时保护**：设置 15 秒硬超时，防止网络波动导致整个插件挂起。

## 4. 流程全图
1. **用户** -> 发送图片 -> **AstrBot** (下载到本地缓存)。
2. **用户** -> “编辑这张图” -> **LLM**。
3. **LLM** -> 调用 `get_image` -> **插件** (返回占位符)。
4. **LLM** -> 调用 `image_edit` (参数含占位符) -> **AstrBot Core**。
5. **插件 Hook** -> 拦截 `image_edit` -> 读取本地缓存 -> **注入 Base64**。
6. **MCP 工具** -> 接收到真实 Base64 -> 执行成功。

## 5. 关键代码位置
- **逻辑封装**：`tools/image_tool.py` -> `extract_images_from_event()`
- **注入入口**：`main.py` -> `@filter.on_using_llm_tool()`

---

**版本记录：** v1.1.1 (2026-02-01)
**维护者：** Thetail001 & Gemini CLI
