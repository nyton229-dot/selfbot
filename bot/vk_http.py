import ssl
from contextlib import asynccontextmanager
from typing import Any

import aiohttp
import certifi
from vkbottle.api import API
from vkbottle.http import AiohttpClient


class VKAiohttpClient(AiohttpClient):
    def __init__(self, verify_ssl: bool) -> None:
        super().__init__()
        self._verify_ssl = verify_ssl

    def _make_connector(self) -> aiohttp.TCPConnector:
        if self._verify_ssl:
            ssl_ctx = ssl.create_default_context(cafile=certifi.where())
            return aiohttp.TCPConnector(ssl=ssl_ctx)
        return aiohttp.TCPConnector(ssl=False)

    @asynccontextmanager
    async def request(
        self,
        url: str,
        method: str = "GET",
        data: dict[str, Any] | None = None,
        **kwargs: Any,
    ):
        if not self.session:
            self.session = aiohttp.ClientSession(connector=self._make_connector())

        async with self.session.request(url=url, method=method, data=data, **kwargs) as response:
            yield response


def build_vk_api(token: str, verify_ssl: bool) -> API:
    return API(token=token, http_client=VKAiohttpClient(verify_ssl))
