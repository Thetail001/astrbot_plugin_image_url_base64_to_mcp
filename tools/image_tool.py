from astrbot.api import FunctionTool, logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Image
from astrbot.core.utils.io import download_image_by_url
import json
import base64
import os
import asyncio

async def extract_images_from_event(event: AstrMessageEvent, look_back_limit: int = 5):
    images = []
    
    if event.message_obj and event.message_obj.message:
        for component in event.message_obj.message:
            if isinstance(component, Image):
                res = await _process_image(component)
                if res: images.append(res)
    
    if images: return images

    try:
        ctx = event.context
        conv_mgr = ctx.conversation_manager
        uid = event.unified_msg_origin
        curr_cid = await conv_mgr.get_curr_conversation_id(uid)
        conversation = await conv_mgr.get_conversation(uid, curr_cid)
        
        if conversation and conversation.history:
            history_list = json.loads(conversation.history)
            count = 0
            for msg in reversed(history_list):
                if msg.get("role") == "user":
                    content = msg.get("content")
                    if isinstance(content, list):
                        for part in content:
                            if isinstance(part, dict) and part.get("type") == "image_url":
                                img_url_obj = part.get("image_url", {})
                                url = img_url_obj.get("url")
                                if url:
                                    res = await _process_url_string(url, force_download=True)
                                    if res: images.append(res)
                    if images: break
                    count += 1
                    if count >= look_back_limit: break
    except Exception as e:
        logger.error(f"[ImageTool] Error: {e}")
    
    return images

async def _process_image(image_comp: Image):
    if image_comp.file and image_comp.file.startswith("base64://"):
        return {"type": "base64", "data": image_comp.file[9:]}
    if image_comp.path and os.path.exists(image_comp.path):
        try:
            with open(image_comp.path, "rb") as f:
                b64_str = base64.b64encode(f.read()).decode('utf-8')
            return {"type": "base64", "data": b64_str}
        except: pass
    return await _process_url_string(image_comp.url, force_download=True)

async def _process_url_string(url: str, force_download=False):
    if not url: return None
    if url.startswith("base64://"):
        return {"type": "base64", "data": url[9:]}
    if url.startswith("http"):
        is_restricted = "api.telegram.org" in url or "localhost" in url or force_download
        if is_restricted:
            try:
                file_path = await asyncio.wait_for(download_image_by_url(url), timeout=15.0)
                if file_path and os.path.exists(file_path):
                    with open(file_path, "rb") as f:
                        b64_str = base64.b64encode(f.read()).decode('utf-8')
                    return {"type": "base64", "data": b64_str}
            except:
                return {"type": "url", "data": url}
        return {"type": "url", "data": url}
    return {"type": "url", "data": url}

class GetImageFromContextTool(FunctionTool):
    def __init__(self):
        super().__init__(
            name="get_image_from_context",
            description="Get image data. Default returns URL. If URL fails, use return_type='base64'.",
            parameters={
                "type": "object",
                "properties": {
                    "look_back_limit": { "type": "integer", "default": 5 },
                    "return_type": { "type": "string", "enum": ["url", "base64"], "default": "url" }
                },
                "required": [],
            }
        )

    async def run(self, event: AstrMessageEvent, look_back_limit: int = 5, return_type: str = "url"):
        # Just check if images exist, don't fetch full data yet to save resources
        # Actually we need to fetch to know if it's URL or Base64
        images = await extract_images_from_event(event, look_back_limit)
        
        if not images:
            return "No images found."
        
        results = []
        for img in images:
            if return_type == "url" and img['type'] == 'url':
                results.append(img)
            else:
                # TOKEN SAVING: Return a Magic Placeholder
                results.append({
                    "type": "base64_placeholder",
                    "data": "base64://ASTRBOT_PLUGIN_CACHE_PENDING", # Looks like a valid URI but needs injection
                    "instruction": "Image is ready. Please pass 'base64://ASTRBOT_PLUGIN_CACHE_PENDING' to the target tool. The system will replace it with real data."
                })
        
        return json.dumps(results)
