import hashlib
import json
import logging
from collections import OrderedDict
from typing import Any

from langchain_core.tools import StructuredTool

logger = logging.getLogger(__name__)


class ToolProxyLayer:
    def __init__(self, max_cache_size: int = 1000):
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._max_cache_size = max_cache_size
        self.no_cache_tools: set[str] = set()

    def _cache_key(self, tool_name: str, kwargs: dict) -> str:
        raw = json.dumps({"tool": tool_name, "args": kwargs}, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def wrap_tools(self, tools: list[StructuredTool]) -> list[StructuredTool]:
        return [self._wrap_single(t) for t in tools]

    def _wrap_single(self, tool: StructuredTool) -> StructuredTool:
        original_coroutine = tool.coroutine

        async def proxied_coroutine(*args, **kwargs) -> Any:
            cache_enabled = tool.name not in self.no_cache_tools

            if cache_enabled:
                try:
                    key = self._cache_key(tool.name, kwargs)
                except (TypeError, ValueError):
                    logger.warning("[mcp_tool_proxy] Non-serializable args for %s, skipping cache", tool.name)
                    cache_enabled = False
                    key = None
            else:
                key = None

            if cache_enabled and key in self._cache:
                self._cache.move_to_end(key)
                logger.info("[mcp_tool_proxy] Cache HIT for %s", tool.name)
                return self._cache[key]

            result = await original_coroutine(*args, **kwargs)

            if cache_enabled and key is not None:
                self._cache[key] = result
                if len(self._cache) > self._max_cache_size:
                    self._cache.popitem(last=False)

            return result

        return StructuredTool(
            name=tool.name,
            description=tool.description,
            args_schema=tool.args_schema,
            func=None,
            coroutine=proxied_coroutine,
            response_format=tool.response_format,
        )
