import hashlib
import json
from typing import Any
from langchain_core.tools import StructuredTool


class ToolProxyLayer:
    def __init__(self):
        self._cache: dict[str, Any] = {}
        self.no_cache_tools: set[str] = set()

    def _cache_key(self, tool_name: str, kwargs: dict) -> str:
        raw = json.dumps({"tool": tool_name, "args": kwargs}, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def wrap_tools(self, tools: list) -> list:
        return [self._wrap_single(t) for t in tools]

    def _wrap_single(self, tool) -> StructuredTool:
        proxy = self
        original_coroutine = tool.coroutine

        async def proxied_coroutine(*args, **kwargs) -> Any:
            if tool.name not in proxy.no_cache_tools:
                key = proxy._cache_key(tool.name, kwargs)
                if key in proxy._cache:
                    print(f"[mcp_tool_proxy] Cache HIT for {tool.name}")
                    return proxy._cache[key]

            result = await original_coroutine(*args, **kwargs)

            if tool.name not in proxy.no_cache_tools:
                proxy._cache[proxy._cache_key(tool.name, kwargs)] = result

            return result

        return StructuredTool(
            name=tool.name,
            description=tool.description,
            args_schema=tool.args_schema,
            func=lambda *a, **kw: None,
            coroutine=proxied_coroutine,
            response_format=tool.response_format,
        )
