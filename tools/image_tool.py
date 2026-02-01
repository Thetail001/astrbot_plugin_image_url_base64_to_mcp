from astrbot.api import FunctionTool, logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Image
from astrbot.core.utils.io import download_image_by_url
import json
import base64
import os

async def extract_images_from_event(event: AstrMessageEvent, look_back_limit: int = 5):
    """
    Extracts images from the event context.
    Returns list of dicts with keys: 'type' (url/base64/path), 'data', 'source'.
    This function returns RAW/REAL data for the Hook to use.
    """
    images = []
    
    # 1. Check current message
    if event.message_obj and event.message_obj.message:
        for component in event.message_obj.message:
            if isinstance(component, Image):
                res = await _process_image(component)
                if res:
                    images.append(res)
    
    if images:
        return images

    # 2. Check history
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
                                    res = await _process_url_string(url)
                                    if res:
                                        images.append(res)
                    if images: break
                    count += 1
                    if count >= look_back_limit: break
    except Exception as e:
        logger.error(f"Error retrieving history: {e}")
    
    return images

async def _process_image(image_comp: Image):
    """
    Priorities:
    1. Raw Base64 in message body (base64://)
    2. Local Cached File (path) -> convert to base64 immediately for consistency
    3. URL
    """
    # 1. Raw Base64
    if image_comp.file and image_comp.file.startswith("base64://"):
        return {"type": "base64", "data": image_comp.file[9:], "source": "raw_msg"}
    
    # 2. Local Cached Path (e.g., Telegram images)
    if image_comp.path and os.path.exists(image_comp.path):
        try:
            with open(image_comp.path, "rb") as f:
                data = f.read()
                b64_str = base64.b64encode(data).decode('utf-8')
            return {"type": "base64", "data": b64_str, "source": "local_cache"}
        except Exception as e:
            logger.warning(f"Failed to read local path {image_comp.path}: {e}")

    # 3. URL
    return await _process_url_string(image_comp.url)

async def _process_url_string(url: str):
    if not url: return None
    
    if url.startswith("base64://"):
        return {"type": "base64", "data": url[9:], "source": "raw_url"}
    elif url.startswith("data:image"):
        if "base64," in url:
            return {"type": "base64", "data": url.split("base64,")[1], "source": "data_uri"}
    elif url.startswith("file:///"):
        # Local file URI
        path = url[8:]
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    b64_str = base64.b64encode(f.read()).decode('utf-8')
                return {"type": "base64", "data": b64_str, "source": "local_file_uri"}
            except: pass
        return {"type": "path", "data": path, "source": "path_uri"}
    
    # Standard URL
    return {"type": "url", "data": url, "source": "http_url"}

class GetImageFromContextTool(FunctionTool):
    def __init__(self):
        super().__init__(
            name="get_image_from_context",
            description="Get image data from context. Returns URL by default. If URL fails (e.g., restricted access), retry with return_type='base64'.",
            parameters={
                "type": "object",
                "properties": {
                    "look_back_limit": {
                        "type": "integer",
                        "description": "Messages to look back.",
                        "default": 5
                    },
                    "return_type": {
                        "type": "string",
                        "enum": ["url", "base64"],
                        "description": "Default 'url'. Use 'base64' ONLY if URL fails.",
                        "default": "url"
                    }
                },
                "required": [],
            }
        )

    async def run(self, event: AstrMessageEvent, look_back_limit: int = 5, return_type: str = "url"):
        images = await extract_images_from_event(event, look_back_limit)
        
        if not images:
            return "No images found."
        
        results = []
        for img in images:
            # If asking for URL and we have a valid HTTP URL, return it
            if return_type == "url" and img['type'] == 'url':
                results.append(img)
            
            # If asking for Base64 OR we only have Base64/Path (no URL available)
            else:
                # TOKEN SAVING: Return a placeholder!
                # Do NOT return the raw base64 string here.
                results.append({
                    "type": "base64_placeholder",
                    "data": "IMAGE_DATA_READY_INTERNAL",
                    "source": img.get('source', 'unknown'),
                    "instruction": "I have the image data ready internally. Please call your target tool with this placeholder string: 'IMAGE_DATA_READY_INTERNAL'. The system will automatically inject the real data."
                })
        
        return json.dumps(results)
