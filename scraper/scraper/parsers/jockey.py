"""騎手情報HTMLパーサー."""

import logging
import re

from repository.models import JockeyProfile
from .base import BaseParser

logger = logging.getLogger(__name__)

# db_prof_table のキーと JockeyProfile キーの対応
_PROF_KEY_MAP = {
    "所属": "所属",
    "生年月日": "生年月日",
    "初免許年": "初免許年",
}


class JockeyParser(BaseParser):
    """騎手プロフィールページ (/jockey/profile/{jockey_id}/) のHTMLパーサー."""

    def parse(self, html: str) -> JockeyProfile:
        soup = self.parse_html(html)
        profile: JockeyProfile = {}

        # 騎手名: <h1> または <div class="horse_title"> 内の <h1>
        title_div = soup.find("div", class_="horse_title")
        if title_div:
            h1 = title_div.find("h1")
            if h1:
                profile["騎手名"] = h1.get_text(strip=True)
        else:
            h1 = soup.find("h1")
            if h1:
                profile["騎手名"] = h1.get_text(strip=True)

        # プロフィールテーブル
        prof_table = soup.find("table", class_="db_prof_table")
        if prof_table:
            for tr in prof_table.find_all("tr"):
                th = tr.find("th")
                td = tr.find("td")
                if not (th and td):
                    continue
                key = th.get_text(strip=True)
                value = td.get_text(strip=True)
                mapped = _PROF_KEY_MAP.get(key)
                if mapped:
                    profile[mapped] = value  # type: ignore[literal-required]

                # 初免許年を年数だけ取り出す
                if key == "初免許年":
                    m = re.search(r"(\d{4})", value)
                    if m:
                        profile["初免許年"] = m.group(1)

        return profile
