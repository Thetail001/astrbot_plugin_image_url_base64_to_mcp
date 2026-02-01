from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.provider import LLMResponse
from .tools.image_tool import GetImageFromContextTool, extract_images_from_event

@register("astrbot_plugin_image_url_base64_to_mcp", "Thetail001", "帮助 MCP 工具从上下文中获取图片 URL 或 Base64 数据。", "1.0.9")
class ImageContextPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.context.add_llm_tools(GetImageFromContextTool())

    @filter.on_llm_response()
    async def on_llm_response(self, event: AstrMessageEvent, resp: LLMResponse):
        """
        Robust Hook to inject image data.
        """
        if not resp.tools_call_args:
            return

        # Check if injection is needed
        needs_injection = False
        target_indices = [] # (tool_index, arg_key)
        
        for i, args in enumerate(resp.tools_call_args):
            if not isinstance(args, dict): continue
            
            # Scan for our magic placeholder OR empty image args
            for key, val in args.items():
                if val == "base64://ASTRBOT_PLUGIN_CACHE_PENDING":
                    needs_injection = True
                    target_indices.append((i, key))
                elif key in ["image", "url", "base64"] and (not val or val == "placeholder"):
                    needs_injection = True
                    target_indices.append((i, key))
        
        if not needs_injection:
            return

        logger.info("[ImageContextPlugin] Injection trigger detected. Fetching data...")
        images = await extract_images_from_event(event)
        
        if not images:
            logger.warning("[ImageContextPlugin] No images found to inject.")
            return

        # Prepare injection data
        # We use the first image found
        img_data = images[0]['data']
        img_type = images[0]['type']
        
        val_to_inject = img_data
        if img_type == 'base64' and not img_data.startswith("data:"):
             # Format as data URI for compatibility
             val_to_inject = f"data:image/jpeg;base64,{img_data}"
        
        # Inject!
        for idx, key in target_indices:
            resp.tools_call_args[idx][key] = val_to_inject
            logger.info(f"[ImageContextPlugin] INJECTED data into tool {idx} arg '{key}' (len={len(val_to_inject)})")
            
        # FORCE UPDATE: Although tools_call_args is a ref, we log to confirm.
        # AstrBot's Runner uses resp.tools_call_args directly.
