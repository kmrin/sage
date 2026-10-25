from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import aiohttp
import crescent
import hikari
import pytest
from crescent.locale import str_or_build_locale

from conftest import make_ctx
from commands.web.models import ImageResult, parse_image_results
from commands.web.searxng import search_images
from core.i18n import t

RESULTS = [ImageResult(image_url=f"https://img.example/{i}.jpg", title=f"Cat {i}", page_url=f"https://www.site{i}.com/cats") for i in range(3)]


def _commands() -> Any:
    from commands.web import commands

    return commands


@pytest.fixture
def client() -> crescent.Client:
    bot = hikari.GatewayBot("MTAwMDAwMDAwMDAwMDAwMDAx.fake.token", banner=None, logs=None, suppress_optimization_warning=True)
    client = crescent.Client(bot, model=None)
    client.plugins.load("commands.web.commands")
    return client


def ctx(locale: str = "en-US") -> Any:
    context = make_ctx(locale=locale)
    context.defer = AsyncMock()
    context.delete = AsyncMock()
    context.interaction.execute = AsyncMock()
    settings = SimpleNamespace(searxng=SimpleNamespace(url="http://searxng:8080"))
    context.client.model = SimpleNamespace(http=object(), settings=settings, miru=object())
    return context


# Parsing


def test_parse_image_results() -> None:
    data = {
        "results": [
            {"img_src": "https://a.example/1.jpg", "title": "  One  ", "url": "https://a.example/page"},
            {"img_src": "https://a.example/1.jpg", "title": "duplicate"},
            {"img_src": "//b.example/2.png", "title": "", "url": "//b.example/page"},
            {"img_src": "data:image/png;base64,xx", "title": "inline"},
            {"img_src": None},
            "garbage",
            {"img_src": "https://c.example/3.jpg", "title": "x" * 300},
        ]
    }
    results = parse_image_results(data, limit=10)
    assert [r.image_url for r in results] == ["https://a.example/1.jpg", "https://b.example/2.png", "https://c.example/3.jpg"]
    assert [r.title for r in results][:2] == ["One", None]
    assert len(results[2].title or "") == 256
    assert results[1].page_url == "https://b.example/page"


def test_parse_image_results_stops_at_the_limit() -> None:
    data = {"results": [{"img_src": f"https://a.example/{i}.jpg"} for i in range(30)]}
    assert len(parse_image_results(data, limit=10)) == 10


@pytest.mark.parametrize("data", [None, [], {"results": "nope"}, {"error": "bad"}])
def test_parse_image_results_rejects_bad_responses(data: Any) -> None:
    with pytest.raises(ValueError):
        parse_image_results(data, limit=10)


def test_result_domain() -> None:
    assert RESULTS[0].domain == "site0.com"
    assert ImageResult(image_url="https://img.example/x.jpg").domain == "img.example"


async def test_search_images_asks_for_strict_safe_search() -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    class Response:
        async def __aenter__(self) -> Any:
            return self

        async def __aexit__(self, *_: Any) -> None: ...

        async def json(self) -> Any:
            return {"results": [{"img_src": "https://a.example/1.jpg"}]}

    class Http:
        def get(self, url: str, params: dict[str, str]) -> Response:
            calls.append((url, params))
            return Response()

    results = await search_images(Http(), "http://searxng:8080/", "cute cats", language="pt-BR", limit=10)  # type: ignore[arg-type]
    assert len(results) == 1
    url, params = calls[0]
    assert url == "http://searxng:8080/search"
    assert params == {"q": "cute cats", "categories": "images", "format": "json", "safesearch": "2", "language": "pt-BR"}


# /search image


def test_command_is_search_image(client: crescent.Client) -> None:
    meta = _commands().SearchImage.metadata
    assert str_or_build_locale(meta.group.name) == ("search", {"pt-BR": "pesquisar"})
    assert str_or_build_locale(meta.app_command.name) == ("image", {"pt-BR": "imagem"})
    assert set(meta.app_command.context_types) == {hikari.ApplicationContextType.GUILD, hikari.ApplicationContextType.BOT_DM}


async def test_search_image_paginates_results(client: crescent.Client, monkeypatch: pytest.MonkeyPatch) -> None:
    search = AsyncMock(return_value=RESULTS)
    monkeypatch.setattr(_commands(), "search_images", search)
    sent: dict[str, Any] = {}

    class FakePaginator:
        def __init__(self, pages: list[hikari.Embed], *, owner_id: int) -> None:
            sent.update(pages=pages, owner_id=owner_id)

        async def send(self, context: Any, miru_client: Any) -> None:
            sent.update(miru=miru_client)

    monkeypatch.setattr(_commands(), "PaginatedResponse", FakePaginator)
    context = ctx("pt-BR")
    await _commands().SearchImage.metadata.callback(context, query="  cats  ")

    assert search.await_args.args[1:] == ("http://searxng:8080", "cats")
    assert search.await_args.kwargs == {"language": "pt-BR", "limit": 10}
    pages: list[hikari.Embed] = sent["pages"]
    assert len(pages) == 3 and sent["owner_id"] == context.user.id
    first = pages[0]
    assert (first.title, first.url) == ("Cat 0", "https://www.site0.com/cats")
    assert first.image is not None and first.image.url == "https://img.example/0.jpg"
    assert first.footer is not None and first.footer.text == t("commands.web.search.image.footer", "pt-BR", query="cats", source="site0.com")


async def test_search_image_with_no_results(client: crescent.Client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_commands(), "search_images", AsyncMock(return_value=[]))
    context = ctx()
    await _commands().SearchImage.metadata.callback(context, query="asdfghjkl")
    context.delete.assert_awaited_once()
    assert context.interaction.execute.await_args.args == (t("commands.web.search.image.no_results", "en-US", query="asdfghjkl"),)


@pytest.mark.parametrize("error", [aiohttp.ClientConnectionError("searxng down"), TimeoutError(), ValueError("bad json")])
async def test_search_image_when_searxng_fails(client: crescent.Client, monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    monkeypatch.setattr(_commands(), "search_images", AsyncMock(side_effect=error))
    context = ctx()
    await _commands().SearchImage.metadata.callback(context, query="cats")
    assert context.interaction.execute.await_args.args == (t("commands.web.search.image.unavailable", "en-US"),)
