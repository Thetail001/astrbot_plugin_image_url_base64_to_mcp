from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.provider import LLMResponse
from .tools.image_tool import GetImageFromContextTool, extract_images_from_event

@register("astrbot_plugin_image_url_base64_to_mcp", "Thetail001", "帮助 MCP 工具从上下文中获取图片 URL 或 Base64 数据。", "1.0.3")
class ImageContextPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 1. Register the tool (Explicit mode)
        self.context.add_llm_tools(GetImageFromContextTool())

    # 2. Hook to intercept Tool Calls (Implicit mode)
    @filter.on_llm_response()
    async def on_llm_response(self, event: AstrMessageEvent, resp: LLMResponse):
        """
        Intercepts LLM response. If it contains tool calls with missing image arguments,
        attempts to inject image data from context.
        """
        # If no tool calls, do nothing
        if not resp.tools_call_args:
            return

        images = None 

        for i, tool_name in enumerate(resp.tools_call_name):
            if tool_name == "get_image_from_context":
                continue # Skip our own tool

            args = resp.tools_call_args[i]
            if not isinstance(args, dict):
                continue

            # Heuristic matching for image arguments
            target_keys = ["image", "image_url", "url", "img", "base64", "file", "data"]
            
            should_inject = False
            target_key = None
            
            for key in target_keys:
                if key in args:
                    val = args[key]
                    # If value is empty, None, or looks like a placeholder
                    if not val or val in ["", "placeholder", "image_url", "base64", "string"]:
                        target_key = key
                        should_inject = True
                        break
            
            if should_inject:
                if images is None:
                    # Fetch images now
                    images = await extract_images_from_event(event)
                
                if images:
                    # Use the first image found
                    img_data = images[0]['data']
                    img_type = images[0]['type']
                    
                    # Smart formatting:
                    # If target is 'url'/'image_url' but we have base64, usually data URI is expected.
                    if target_key in ["url", "image_url", "image"] and img_type == "base64":
                        val_to_inject = f"data:image/jpeg;base64,{img_data}"
                    # If target is 'base64' and we have base64, use raw.
                    elif target_key == "base64" and img_type == "base64":
                        val_to_inject = img_data
                    else:
                        val_to_inject = img_data # Fallback
                        
                    args[target_key] = val_to_inject
                    logger.info(f"[ImageContextPlugin] Injected image data into tool '{tool_name}' argument '{target_key}'")

    @filter.command("test_get_image")
    async def test_get_image(self, event: AstrMessageEvent):
        '''Test extracting image from context.'''
        images = await extract_images_from_event(event)
        yield event.plain_result(f"Found images: {images}")
