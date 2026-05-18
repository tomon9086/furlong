"""HTMLパーサーの基底クラス."""

from abc import ABC, abstractmethod
from typing import Any

from bs4 import BeautifulSoup


class BaseParser(ABC):
    """HTMLパーサーの基底クラス."""

    def parse_html(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "html.parser")

    @abstractmethod
    def parse(self, html: str) -> Any:
        pass
