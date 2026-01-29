# AstrBot Plugin: Image Context Helper

此插件旨在解决 AstrBot 中大语言模型（LLM）调用 MCP 工具（Model Context Protocol）时，无法方便地获取上下文中图片数据（URL 或 Base64）的问题。

## 功能介绍

本插件提供两种机制来确保 MCP 工具能获取到正确的图片数据：

### 1. 自动注入（隐式模式 - 推荐）
这是最自动化的方式。当 LLM 决定调用某个 MCP 工具（例如 `analyze_image`），但因为不知道具体的图片数据而将参数（如 `image`, `url`, `base64`）留空时，本插件会自动拦截该请求：
1. 检测到 MCP 工具调用的参数为空或为占位符。
2. 自动回溯上下文（当前消息及最近历史），找到最近的一张图片。
3. 提取图片的 URL 或 Base64 数据。
4. **自动注入**到工具调用的参数中。
5. 放行请求，MCP 工具顺利执行。

**支持自动注入的参数名匹配：** `image`, `image_url`, `url`, `img`, `base64`, `file`, `data`。

### 2. 主动获取（显式模式）
插件注册了一个名为 `get_image_from_context` 的工具。
- LLM 可以主动调用此工具来查询上下文中有哪些图片。
- **Token 节省优化**：为了防止返回巨大的 Base64 字符串消耗 Token，此工具返回的 JSON 中会隐藏具体的 Base64 数据，只返回一个占位符。
- LLM 确认有图后，只需发起 MCP 调用（参数留空），后续依然由“自动注入”机制完成数据填充。

## 安装与使用

1. 将本插件文件夹放置在 AstrBot 的 `data/plugins/` 目录下。
2. 重启 AstrBot 或在 WebUI 中重载插件。
3. 确保你的 AstrBot 已配置好支持 Vision 的大模型（如 GPT-4o, Claude-3.5-Sonnet）。
4. 对 Bot 发送图片，并要求调用相关的 MCP 工具（例如：“用 mcp 分析这张图”）。

## 兼容性

- 兼容 AstrBot 的多模态消息链。
- 兼容 OpenAI 格式及 AstrBot 内部的图片存储格式。
- 优化了 Token 消耗，避免在对话历史中存储冗余的 Base64 数据。