from astrbot.api import FunctionTool, logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Image
from astrbot.core.utils.io import download_image_by_url
import json
import base64
import os

async def extract_images_from_event(event: AstrMessageEvent, look_back_limit: int = 5):
    """
    Extracts images from the event context (current message + history).
    Returns a list of dicts: {"type": "url"|"base64"|"path", "data": "..."}
    Note: This returns the RAW data.
    """
    images = []
    
    # 1. Check current message
    if event.message_obj and event.message_obj.message:
        for component in event.message_obj.message:
            if isinstance(component, Image):
                res = await _process_image(component)
                if res:
                    images.append(res)
    
    # If we found images in current message, usually that's what we want.
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
                    
                    if images:
                        break
                    
                    count += 1
                    if count >= look_back_limit:
                        break
    except Exception as e:
        logger.error(f"Error retrieving history in extract_images_from_event: {e}")
    
    return images

async def _process_image(image_comp: Image):
    # Check internal base64 file property first
    if image_comp.file and image_comp.file.startswith("base64://"):
        return {"type": "base64", "data": image_comp.file[9:]}
    
    url = image_comp.url or image_comp.file
    return await _process_url_string(url)

async def _process_url_string(url: str):
    if not url:
        return None
        
    if url.startswith("base64://"):
        return {"type": "base64", "data": url[9:]}
    elif url.startswith("data:image"):
        if "base64," in url:
            return {"type": "base64", "data": url.split("base64,")[1]}
        else:
            return {"type": "url", "data": url}
    elif url.startswith("http"):
        # Force download and convert to base64
        try:
            # logger.info(f"Downloading image from {url}...")
            file_path = await download_image_by_url(url)
            if file_path and os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    data = f.read()
                    b64_str = base64.b64encode(data).decode('utf-8')
                return {"type": "base64", "data": b64_str}
        except Exception as e:
            logger.error(f"Failed to download image from {url}: {e}")
            # Fallback to URL if download fails
            return {"type": "url", "data": url}
            
        return {"type": "url", "data": url}
    elif url.startswith("file:///"):
        # For local files, also try convert to base64
        try:
            path = url[8:]
            if os.path.exists(path):
                 with open(path, "rb") as f:
                    data = f.read()
                    b64_str = base64.b64encode(data).decode('utf-8')
                 return {"type": "base64", "data": b64_str}
        except Exception:
            pass
        return {"type": "path", "data": url[8:]}
    else:
        return {"type": "url", "data": url}

class GetImageFromContextTool(FunctionTool):
    def __init__(self):
        super().__init__(
            name="get_image_from_context",
            description="Get the image URL or Base64 content from the current conversation context. Use this when you need to process an image that the user has sent. It returns a list of images found.",
            parameters={
                "type": "object",
                "properties": {
                    "look_back_limit": {
                        "type": "integer",
                        "description": "How many recent messages to check for images. Default is 5.",
                        "default": 5
                    }
                },
                "required": [],
            }
        )

    async def run(self, event: AstrMessageEvent, look_back_limit: int = 5):
        # Fetch raw data
        images = await extract_images_from_event(event, look_back_limit)
        
        if not images:
            return "No images found in the recent context."
        
        # Process specifically for LLM consumption (Token Saving)
        safe_images = []
        for img in images:
            safe_img = img.copy()
            if safe_img['type'] == 'base64':
                data_len = len(safe_img['data'])
                # Replace raw data with a token-safe placeholder
                safe_img['data'] = f"<BASE64_IMAGE_DATA_HIDDEN_SIZE_{data_len}_BYTES>"
                safe_img['instruction'] = "I have located the image data. Please call the target tool with an empty string (or 'placeholder') for the image/url argument. The system will automatically inject the real data during execution."
            safe_images.append(safe_img)
        
        return json.dumps(safe_images)
