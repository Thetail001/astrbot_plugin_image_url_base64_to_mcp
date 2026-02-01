from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.provider import LLMResponse
from astrbot.core.utils.io import download_image_by_url
from .tools.image_tool import GetImageFromContextTool, extract_images_from_event
import base64
import os

@register("astrbot_plugin_image_url_base64_to_mcp", "Thetail001", "帮助 MCP 工具从上下文中获取图片 URL 或 Base64 数据。", "1.0.5")
class ImageContextPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.context.add_llm_tools(GetImageFromContextTool())

    @filter.on_llm_response()
    async def on_llm_response(self, event: AstrMessageEvent, resp: LLMResponse):
        if not resp.tools_call_args:
            return

        logger.info(f"[ImageContextPlugin] Hook triggered. Checking {len(resp.tools_call_args)} tool calls.")

        images = None 

        for i, tool_name in enumerate(resp.tools_call_name):
            if tool_name == "get_image_from_context":
                continue 

            args = resp.tools_call_args[i]
            if not isinstance(args, dict):
                continue

            target_keys = ["image", "image_url", "url", "img", "base64", "file", "data"]
            
            should_inject = False
            target_key = None
            
            for key in target_keys:
                if key in args:
                    val = args[key]
                    if not val or val in ["", "placeholder", "image_url", "base64", "string", "IMAGE_DATA_READY_INTERNAL"]:
                        target_key = key
                        should_inject = True
                        logger.info(f"[ImageContextPlugin] Found injection target: tool={tool_name}, arg={key}, val={val}")
                        break
            
            if should_inject:
                if images is None:
                    logger.info("[ImageContextPlugin] Fetching images from context...")
                    images = await extract_images_from_event(event)
                    logger.info(f"[ImageContextPlugin] Fetched {len(images) if images else 0} images.")
                
                if images:
                    img_data = images[0]['data']
                    img_type = images[0]['type']
                    logger.info(f"[ImageContextPlugin] Selected image type: {img_type}")

                    val_to_inject = img_data
                    
                    need_base64 = (target_key == "base64") or (args.get(target_key) == "IMAGE_DATA_READY_INTERNAL")
                    
                    if img_type == 'url' and need_base64:
                        logger.info(f"[ImageContextPlugin] Converting URL to Base64 for injection: {img_data}")
                        try:
                            file_path = await download_image_by_url(img_data)
                            if file_path and os.path.exists(file_path):
                                with open(file_path, "rb") as f:
                                    b64_str = base64.b64encode(f.read()).decode('utf-8')
                                img_data = b64_str
                                img_type = 'base64'
                        except Exception as e:
                            logger.error(f"[ImageContextPlugin] Failed to download image for injection: {e}")

                    # Formatting
                    if target_key in ["url", "image_url", "image"] and img_type == "base64":
                        val_to_inject = f"data:image/jpeg;base64,{img_data}"
                    elif target_key == "base64" and img_type == "base64":
                        val_to_inject = img_data
                    else:
                        val_to_inject = img_data
                        
                    args[target_key] = val_to_inject
                    logger.info(f"[ImageContextPlugin] Injected image data into tool '{tool_name}' argument '{target_key}' (Length: {len(val_to_inject)})")
                else:
                    logger.warning("[ImageContextPlugin] No images found to inject!")

    @filter.command("test_get_image")
    async def test_get_image(self, event: AstrMessageEvent):
        images = await extract_images_from_event(event)
        yield event.plain_result(f"Found images: {images}")
