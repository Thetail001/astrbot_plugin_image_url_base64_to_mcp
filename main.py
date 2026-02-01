from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, FunctionTool
from .tools.image_tool import GetImageFromContextTool, extract_images_from_event

@register("astrbot_plugin_image_url_base64_to_mcp", "Thetail001", "帮助 MCP 工具从上下文中获取图片 URL 或 Base64 数据。", "1.1.1")
class ImageContextPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.context.add_llm_tools(GetImageFromContextTool())

    @filter.on_using_llm_tool()
    async def on_tool_use(self, event: AstrMessageEvent, tool: FunctionTool, tool_args: dict):
        """
        Intercepts tool execution BEFORE it happens.
        Injects real Base64 data if placeholders or empty args are found.
        """
        if tool.name == "get_image_from_context":
            return

        target_keys = ["image", "image_url", "url", "img", "base64", "file", "data"]
        should_inject = False
        target_key = None
        
        for key in target_keys:
            if key in tool_args:
                val = tool_args[key]
                # Detect Placeholder or Empty
                if val == "base64://ASTRBOT_PLUGIN_CACHE_PENDING" or val == "IMAGE_DATA_READY_INTERNAL":
                    should_inject = True
                    target_key = key
                    break
                # Also support implicit injection if arg is empty/placeholder
                elif not val or val in ["placeholder", "image"]:
                    should_inject = True
                    target_key = key
                    break
        
        if should_inject:
            logger.info(f"[ImageContextPlugin] Intercepting tool '{tool.name}'. Injecting image data...")
            
            images = await extract_images_from_event(event)
            if images:
                img_data = images[0]['data']
                img_type = images[0]['type']
                
                val_to_inject = img_data
                if img_type == 'base64' and not img_data.startswith("data:"):
                    val_to_inject = f"data:image/jpeg;base64,{img_data}"
                
                # DIRECTLY MODIFY the tool_args dictionary (Passed by Reference)
                tool_args[target_key] = val_to_inject
                logger.info(f"[ImageContextPlugin] Injection SUCCESS for '{target_key}'. Len: {len(val_to_inject)}")
            else:
                logger.warning("[ImageContextPlugin] Failed to fetch images for injection.")

    @filter.command("test_get_image")
    async def test_get_image(self, event: AstrMessageEvent):
        '''Test extracting image from context.'''
        images = await extract_images_from_event(event)
        yield event.plain_result(f"Found images: {len(images)}")
