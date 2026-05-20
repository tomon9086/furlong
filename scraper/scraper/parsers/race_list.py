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

        ページネーションが見つからない場合は 1 を返す。
        """
        soup = self.parse_html(html)

        # pager div 内のページ番号リンクを収集
        pager = soup.find("div", class_="pager")
        if not pager:
            return 1

        max_page = 1
        for a in pager.find_all("a", href=re.compile(r"page=\d+")):
            m = re.search(r"page=(\d+)", a["href"])
            if m:
                max_page = max(max_page, int(m.group(1)))

        # 現在のページ（リンクなし）も確認
        for span in pager.find_all("span"):
            text = span.get_text(strip=True)
            if text.isdigit():
                max_page = max(max_page, int(text))

        return max_page
