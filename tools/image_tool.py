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
    Attempts to fetch REAL Base64 data if possible (downloading if necessary).
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
                                    # Force download for history items to ensure we get Base64
                                    res = await _process_url_string(url, force_download=True)
                                    if res:
                                        images.append(res)
                    if images: break
                    count += 1
                    if count >= look_back_limit: break
    except Exception as e:
        logger.error(f"[ImageTool] Error retrieving history: {e}")
    
    return images

async def _process_image(image_comp: Image):
    # 1. Raw Base64
    if image_comp.file and image_comp.file.startswith("base64://"):
        return {"type": "base64", "data": image_comp.file[9:], "source": "raw_msg"}
    
    # 2. Local Cached Path
    if image_comp.path and os.path.exists(image_comp.path):
        try:
            with open(image_comp.path, "rb") as f:
                b64_str = base64.b64encode(f.read()).decode('utf-8')
            return {"type": "base64", "data": b64_str, "source": "local_cache"}
        except Exception as e:
            logger.warning(f"Failed to read local path {image_comp.path}: {e}")

    # 3. URL (Force download to ensure availability)
    return await _process_url_string(image_comp.url, force_download=True)

async def _process_url_string(url: str, force_download=False):
    if not url: return None
    
    if url.startswith("base64://"):
        return {"type": "base64", "data": url[9:], "source": "raw_url"}
    elif url.startswith("data:image"):
        if "base64," in url:
            return {"type": "base64", "data": url.split("base64,")[1], "source": "data_uri"}
    elif url.startswith("file:///"):
        path = url[8:]
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    b64_str = base64.b64encode(f.read()).decode('utf-8')
                return {"type": "base64", "data": b64_str, "source": "local_file_uri"}
            except: pass
        return {"type": "path", "data": path, "source": "path_uri"}
    
    if url.startswith("http"):
        # If force_download is True, or it looks restricted, try to download
        is_restricted = "api.telegram.org" in url or "localhost" in url or "127.0.0.1" in url or force_download
        
        if is_restricted:
            try:
                # logger.info(f"Downloading {url}...")
                file_path = await download_image_by_url(url)
                if file_path and os.path.exists(file_path):
                    with open(file_path, "rb") as f:
                        b64_str = base64.b64encode(f.read()).decode('utf-8')
                    return {"type": "base64", "data": b64_str, "source": "downloaded"}
            except Exception as e:
                logger.error(f"[ImageTool] Failed to download {url}: {e}")
                # Return URL as fallback
                return {"type": "url", "data": url, "source": "http_url_failed_dl"}
        
        return {"type": "url", "data": url, "source": "http_url"}
    
    return {"type": "url", "data": url, "source": "unknown"}

class GetImageFromContextTool(FunctionTool):
    def __init__(self):
        super().__init__(
            name="get_image_from_context",
            description="Get image data from context. Returns URL by default. If URL fails, use return_type='base64' to get raw data.",
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
                        "description": "Default 'url'. Use 'base64' to get the full image data (fixes download issues).",
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
            if return_type == "url" and img['type'] == 'url':
                results.append(img)
            else:
                # Direct return of Base64 data!
                # NO PLACEHOLDERS.
                results.append(img)
        
        return json.dumps(results)
