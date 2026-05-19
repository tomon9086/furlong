"""馬情報HTMLパーサー."""

import logging
import re

from repository.models import HorseProfile, HorseRaceResult
from .base import BaseParser

logger = logging.getLogger(__name__)


class HorseParser(BaseParser):
    """馬詳細ページ (/horse/{horse_id}/) のHTMLパーサー."""

    def parse(self, html: str) -> tuple[HorseProfile, list[HorseRaceResult]]:
        """プロフィールと競走成績をまとめて返す."""
        return self.parse_profile(html), self.parse_race_results(html)

    def parse_profile(self, html: str) -> HorseProfile:
        """馬のプロフィール情報を抽出する."""
        soup = self.parse_html(html)
        profile: HorseProfile = {}

        horse_title = soup.find("div", class_="horse_title")
        if horse_title:
            h1 = horse_title.find("h1")
            if h1:
                profile["馬名"] = h1.get_text(strip=True)

            txt_01 = horse_title.find("p", class_="txt_01")
            if txt_01:
                parts = re.split(r"[\s　]+", txt_01.get_text(strip=True))
                parts = [p for p in parts if p]
                if len(parts) >= 2:
                    profile["性別"] = re.sub(r"\d+歳$", "", parts[-2])
                if len(parts) >= 1:
                    profile["毛色"] = parts[-1]

        prof_table = soup.find("table", class_="db_prof_table")
        if prof_table:
            for tr in prof_table.find_all("tr"):
                th = tr.find("th")
                td = tr.find("td")
                if not (th and td):
                    continue
                key = th.get_text(strip=True)
                value = td.get_text(strip=True)
                if key in HorseProfile.__optional_keys__:
                    profile[key] = value  # type: ignore[literal-required]

                if key == "調教師":
                    link = td.find("a", href=re.compile(r"/trainer/"))
                    if link:
                        m = re.search(r"/trainer/(\w+)", link["href"])
                        if m:
                            profile["調教師ID"] = m.group(1).rstrip("/")
                elif key == "馬主":
                    link = td.find("a", href=re.compile(r"/owner/"))
                    if link:
                        m = re.search(r"/owner/(\w+)", link["href"])
                        if m:
                            profile["馬主ID"] = m.group(1).rstrip("/")

        blood_table = soup.find("table", class_="blood_table")
        if blood_table:
            profile.update(self._parse_blood_table(blood_table))  # type: ignore[arg-type]

        return profile

    def _parse_blood_table(self, table) -> dict[str, str]:
        """血統テーブル（父・母・母父）をパースする."""
        blood: dict[str, str] = {}
        sire_dam_cells = []
        grandsire_cells = []

        for tr in table.find_all("tr"):
            for td in tr.find_all("td"):
                if td.get("rowspan"):
                    sire_dam_cells.append(td)
                else:
                    grandsire_cells.append(td)

        def _text(cell) -> str:
            a = cell.find("a")
            return a.get_text(strip=True) if a else cell.get_text(strip=True)

        if len(sire_dam_cells) >= 1:
            blood["父"] = _text(sire_dam_cells[0])
        if len(sire_dam_cells) >= 2:
            blood["母"] = _text(sire_dam_cells[1])
        # grandsire_cells: [父父, 父母, 母父, 母母]
        if len(grandsire_cells) >= 3:
            blood["母父"] = _text(grandsire_cells[2])

        return blood

    def parse_race_results(self, html: str) -> list[HorseRaceResult]:
        """馬の競走成績を抽出する."""
        soup = self.parse_html(html)
        results: list[HorseRaceResult] = []

        table = soup.find("table", class_="db_h_race_results")
        if not table:
            table = soup.find("table", attrs={"summary": re.compile(r"競走成績")})
        if not table:
            logger.debug("競走成績テーブルが見つかりません")
            return results

        headers: list[str] = []
        thead = table.find("thead")
        if thead:
            headers = [th.get_text(strip=True) for th in thead.find_all("th")]

        tbody = table.find("tbody")
        data_rows = tbody.find_all("tr") if tbody else table.find_all("tr")[1:]

        for tr in data_rows:
            td_elements = tr.find_all("td")
            if not td_elements:
                continue

            cells = [td.get_text(strip=True) for td in td_elements]

            race_id = ""
            for td in td_elements:
                race_link = td.find("a", href=re.compile(r"/race/\d+"))
                if race_link and race_link.get("href"):
                    m = re.search(r"/race/(\d+)", race_link["href"])
                    if m:
                        race_id = m.group(1).rstrip("/")
                    break

            jockey_id = ""
            for td in td_elements:
                jockey_link = td.find("a", href=re.compile(r"/jockey/"))
                if jockey_link and jockey_link.get("href"):
                    m = re.search(r"/jockey/(\w+)", jockey_link["href"])
                    if m:
                        jockey_id = m.group(1).rstrip("/")
                    break

            cells.extend([race_id, jockey_id])
            all_headers = headers + ["レースID", "騎手ID"]

            if headers:
                row: HorseRaceResult = dict(zip(all_headers, cells))  # type: ignore[assignment]
            else:
                row = {f"col_{i}": cell for i, cell in enumerate(cells)}  # type: ignore[assignment]

            results.append(row)

        return results

    def parse_pedigree_json(self, json_text: str) -> dict[str, str]:
        """AJAX 血統レスポンス (JSON) から血統情報を抽出する.

        netkeiba の馬ページでは血統テーブルが AJAX で読み込まれる。
        レスポンス形式: {"status": "OK", "data": "<table class='blood_table'>..."}
        """
        import json as _json

        try:
            obj = _json.loads(json_text)
        except (ValueError, TypeError):
            logger.warning("血統 JSON のパース失敗")
            return {}

        html = obj.get("data", "")
        if not html:
            return {}

        soup = self.parse_html(html)
        blood_table = soup.find("table", class_="blood_table")
        if not blood_table:
            return {}
        return self._parse_blood_table(blood_table)
