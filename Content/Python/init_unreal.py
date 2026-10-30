# Project start-up script: start the editor MCP server automatically once the editor has finished loading.
import unreal

_handle = None


def _start_mcp(_delta):
    global _handle
    unreal.unregister_slate_post_tick_callback(_handle)
    unreal.SystemLibrary.execute_console_command(None, "ModelContextProtocol.StartServer")


_handle = unreal.register_slate_post_tick_callback(_start_mcp)
