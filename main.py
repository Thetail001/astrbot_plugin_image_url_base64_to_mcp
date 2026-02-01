from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from .tools.image_tool import GetImageFromContextTool, extract_images_from_event

@register("astrbot_plugin_image_url_base64_to_mcp", "Thetail001", "帮助 MCP 工具从上下文中获取图片 URL 或 Base64 数据。", "1.0.7")
class ImageContextPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # Register the tool
        self.context.add_llm_tools(GetImageFromContextTool())

    @filter.command("test_get_image")
    async def test_get_image(self, event: AstrMessageEvent):
        '''Test extracting image from context.'''
        images = await extract_images_from_event(event)
        yield event.plain_result(f"Found images: {images}")