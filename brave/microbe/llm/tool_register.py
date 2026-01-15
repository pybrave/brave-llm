
from brave.microbe.llm.tool_manager import ToolManager
from brave.microbe.llm.tools.format_tools import format_tools
from brave.microbe.llm.tools.log_tools import get_error_log
from brave.microbe.llm.tools.rag_tools import rag_tools

from .tools import component_tools

def register_tools(tool_manager: ToolManager):
    """注册所有工具到 ToolManager"""
    pass
    tool_manager.register(
        name="rag_tools",
        func=rag_tools,
        description="查询与用户输入内容相关的信息",
        parameters={
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "string",
                    "description": "搜索的关键字",
                },

            },
            "required": ["keywords"],
        },
    )

    # tool_manager.register(
    #     name="format_tools",
    #     func=format_tools,
    #     description="来源引用格式化工具",
    #     parameters={
    #         "type": "object",
    #         "properties": {
    #             "citation": {
    #                 "type": "array",
    #                 "description": "list of citation information",
    #                 "items": {
    #                     "id": {
    #                         "type": "string",
    #                         "description": "文章ID"
    #                     },
    #                     "sentence": {
    #                         "type": "string",
    #                         "description": "引用的句子"
    #                     }
    #                 }
    #             }
    #         },
    #         "required": ["citation"],
    #     },
    # )

    # tool_manager.register(
    #     name="create_script_component",
    #     func=component_tools.create_script_component,
    #     description="为tools创建脚本",
    #      parameters={
    #         "type": "object",
    #         "properties": {
    #             "script": {
    #                 "type": "string",
    #                 "description": "LLM 生成的完整脚本内容，必须是可执行或可保存的脚本代码",
    #             },
         
    #         },
    #         "required": ["script"],
    #     },
    # )