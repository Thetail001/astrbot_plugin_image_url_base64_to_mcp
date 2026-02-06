from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, FunctionTool

# 根据仓库结构，从 tools.image_tool 导入图片提取函数
# 注意：我们不再需要导入 GetImageFromContextTool，因为工具逻辑已经移入下方的主类中
from .tools.image_tool import extract_images_from_event

@register("astrbot_plugin_image_url_base64_to_mcp", "Thetail001", "帮助 MCP 工具从上下文中获取图片 URL 或 Base64 数据。", "1.1.4")
class ImageContextPlugin(Star):
    # 修改处：将 config 设置为可选参数 (= None)，以修复 missing argument 错误
    def __init__(self, context: Context, config: dict = None):
        # 即使 config 为 None，传给父类也是安全的，或者父类会自动处理
        super().__init__(context, config)
        # 移除了 self.context.add_llm_tools(...) 
        # 现在工具通过下方的 @filter.llm_tool 自动注册，并自动绑定到本插件

    # ==================== 核心修改：将工具定义移入插件类 ====================
    @filter.llm_tool(name="get_image_from_context")
    async def get_image_from_context(self, event: AstrMessageEvent):
        """
        从当前的对话上下文中获取图片。
        
        当需要获取用户发送的图片、或者上下文中的图片 URL/Base64 数据时调用此工具。
        """
        # 调用 tools/image_tool.py 中的逻辑
        images = await extract_images_from_event(event, prefer_base64=True)
        
        if not images:
            return "上下文中未找到图片。"
        
        # 获取第一张图片
        image_data = images[0]
        img_type = image_data.get('type')
        img_content = image_data.get('data')

        # 如果是 URL，直接返回 URL，这对 LLM 最友好
        if img_type == 'url':
            return f"获取成功 (URL): {img_content}"
        
        # 如果是 Base64，考虑到文本长度，通常返回摘要信息
        # 如果你的特定场景需要直接把 Base64 给 LLM（虽然不推荐作为文本返回），可以去掉 len() 限制
        return f"获取成功 (Base64): 数据长度 {len(str(img_content))} 字符。类型: {img_type}"
    # ======================================================================

    @filter.on_using_llm_tool()
    async def on_tool_use(self, event: AstrMessageEvent, tool: FunctionTool, tool_args: dict):
        """
        Intercepts tool execution BEFORE it happens.
        Injects real Base64 data if placeholders or empty args are found.
        """
        # 防止递归调用自己
        if tool.name == "get_image_from_context":
            return

        target_keys = ["image", "image_url", "url", "img", "base64", "file", "data"]
        should_inject = False
        target_key = None
        
        for key in target_keys:
            if key in tool_args:
                val = tool_args[key]
                # 检查特殊占位符或空值
                if val == "base64://ASTRBOT_PLUGIN_CACHE_PENDING" or val == "IMAGE_DATA_READY_INTERNAL":
                    should_inject = True
                    target_key = key
                    break
                elif not val or val in ["placeholder", "image"]:
                    should_inject = True
                    target_key = key
                    break
        
        if should_inject:
            logger.info(f"[ImageContextPlugin] Intercepting tool '{tool.name}'. Injecting image data...")
            
            # Hook phase: We MUST force download/convert to Base64 to satisfy MCP
            images = await extract_images_from_event(event, prefer_base64=True)
            if images:
                img_data = images[0]['data']
                img_type = images[0]['type']
                
                val_to_inject = img_data
                # 自动补全 data URI scheme，方便前端或某些工具识别
                if img_type == 'base64' and not img_data.startswith("data:"):
                    val_to_inject = f"data:image/jpeg;base64,{img_data}"
                
                tool_args[target_key] = val_to_inject
                logger.info(f"[ImageContextPlugin] Injection SUCCESS for '{target_key}'. Len: {len(val_to_inject)}")
            else:
                logger.warning("[ImageContextPlugin] Failed to fetch images for injection.")

    @filter.command("test_get_image")
    async def test_get_image(self, event: AstrMessageEvent):
        """测试命令：检查是否能从当前消息提取图片"""
        images = await extract_images_from_event(event)
        yield event.plain_result(f"Found images: {len(images)}")
