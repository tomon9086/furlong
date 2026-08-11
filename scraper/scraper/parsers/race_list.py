"""レース一覧ページ HTMLパーサー (db.netkeiba.com/?pid=race_list)."""

import re

from .base import BaseParser


class RaceListParser(BaseParser):
    """レース一覧ページのパーサー.

    URL 例:
        https://db.netkeiba.com/?pid=race_list
            &start_year=2026&start_mon=1
            &end_year=2026&end_mon=1
            &sort=date&list=20&page=1
    """

    def parse(self, html: str) -> list[str]:
        """ページ内に掲載されているレース ID の一覧を返す.

        レース ID は `/race/{race_id}/` 形式のリンクから抽出する。
        """
        soup = self.parse_html(html)
        race_ids: list[str] = []

        for a in soup.find_all("a", href=re.compile(r"/race/\d{12}/?")):
            m = re.search(r"/race/(\d{12})", a["href"])
            if m:
                race_id = m.group(1)
                if race_id not in race_ids:
                    race_ids.append(race_id)

        return race_ids

    def parse_total_pages(self, html: str) -> int:
        """ページネーションから総ページ数を返す.

        `class="pager"` の div はページ送りリンクを含まない「1,717件中1~100件目」
        という件数サマリーのテキストのみで、実際のページ送りリンク（`<li>` 内、
        pager クラスなし）は DOM 構造が不安定なため頼らない。件数サマリーから
        総件数・1ページあたり件数を読み取り、ページ数を計算する。
        サマリーが見つからない場合は 1 を返す。
        """
        soup = self.parse_html(html)

        pager = soup.find("div", class_="pager")
        if not pager:
            return 1

        text = pager.get_text(strip=True)
        m = re.search(r"([\d,]+)件中(\d+)[~〜](\d+)件目", text)
        if not m:
            return 1

        total = int(m.group(1).replace(",", ""))
        start = int(m.group(2))
        end = int(m.group(3))
        per_page = end - start + 1
        if per_page <= 0:
            return 1

        return -(-total // per_page)  # ceil division

    def parse_by_date(self, html: str) -> list[str]:
        """race.netkeiba.com の開催日別レース一覧ページからレースIDを取得する.

        race_id=XXXXXXXXXXXX 形式のリンクを抽出する。
        """
        soup = self.parse_html(html)
        race_ids: list[str] = []

        for a in soup.find_all("a", href=re.compile(r"race_id=\d{12}")):
            m = re.search(r"race_id=(\d{12})", a["href"])
            if m:
                race_id = m.group(1)
                if race_id not in race_ids:
                    race_ids.append(race_id)

        return race_ids
