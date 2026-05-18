"""レース詳細HTMLパーサー."""

import logging
import re

from .base import BaseParser
from ..types import PayoffRow, RaceDetailRow, RaceInfo

logger = logging.getLogger(__name__)


class RaceDetailParser(BaseParser):
    """レース詳細ページ (/race/{race_id}/) のHTMLパーサー."""

    def parse(self, html: str) -> list[RaceDetailRow]:
        """出走馬ごとのレース結果を抽出する."""
        soup = self.parse_html(html)

        table = soup.find("table", class_="race_table_01")
        if not table:
            raise ValueError("レース結果テーブルが見つかりません")

        all_trs = table.find_all("tr")

        # ヘッダー行
        headers: list[str] = []
        for tr in all_trs:
            if tr.find("th"):
                headers = [th.get_text(strip=True) for th in tr.find_all("th")]
                break

        # データ行
        data_rows = [tr for tr in all_trs if tr.find("td") and not tr.find("th")]

        rows: list[RaceDetailRow] = []
        for tr in data_rows:
            td_elements = tr.find_all("td")
            if not td_elements:
                continue

            cells = [td.get_text(strip=True) for td in td_elements]

            horse_id = ""
            jockey_id = ""
            trainer_id = ""

            if len(td_elements) > 3:
                horse_link = td_elements[3].find("a", href=re.compile(r"/horse/"))
                if horse_link and horse_link.get("href"):
                    m = re.search(r"/horse/(\d+)", horse_link["href"])
                    if m:
                        horse_id = m.group(1)

            for td in td_elements:
                jockey_link = td.find("a", href=re.compile(r"/jockey/"))
                if jockey_link and jockey_link.get("href"):
                    m = re.search(r"/jockey/(?:result/recent/)?(\d+)", jockey_link["href"])
                    if m:
                        jockey_id = m.group(1)
                    break

            for td in td_elements:
                trainer_link = td.find("a", href=re.compile(r"/trainer/"))
                if trainer_link and trainer_link.get("href"):
                    m = re.search(r"/trainer/(?:result/recent/)?(\d+)", trainer_link["href"])
                    if m:
                        trainer_id = m.group(1)
                    break

            if headers:
                if len(headers) != len(cells):
                    logger.warning(
                        "ヘッダー数(%d)とデータセル数(%d)が一致しません",
                        len(headers),
                        len(cells),
                    )
                row: RaceDetailRow = dict(zip(headers, cells))  # type: ignore[assignment]
            else:
                row = {f"col_{i}": cell for i, cell in enumerate(cells)}  # type: ignore[assignment]

            row["馬ID"] = horse_id
            row["騎手ID"] = jockey_id
            row["調教師ID"] = trainer_id

            rows.append(row)

        if not rows:
            raise ValueError("レース結果にデータ行が見つかりません")

        return rows

    def parse_race_info(self, html: str) -> RaceInfo:
        """レースのメタ情報を抽出する."""
        soup = self.parse_html(html)
        info: RaceInfo = {}

        # レース名
        race_name_tag = None
        race_data_dl = soup.find("dl", class_="racedata")
        if race_data_dl:
            dd = race_data_dl.find("dd")
            if dd:
                race_name_tag = dd.find("h1")
        if not race_name_tag:
            race_name_tag = soup.find("h1", class_="racedata_fc")
        if race_name_tag:
            info["レース名"] = race_name_tag.get_text(strip=True)

        # レース番号
        if race_data_dl:
            dt = race_data_dl.find("dt")
            if dt:
                m = re.search(r"(\d+)\s*R", dt.get_text(strip=True))
                if m:
                    info["R"] = m.group(1)

        # グレード
        if race_name_tag:
            grade_img = race_name_tag.find("img")
            if grade_img and grade_img.get("alt"):
                info["グレード"] = grade_img["alt"]

        # コース条件（距離・コース種別・天候・馬場・発走時刻）
        if race_data_dl:
            dd = race_data_dl.find("dd")
            if dd:
                span = dd.find("span")
                condition_text = (
                    span.get_text(strip=True)
                    if span
                    else (dd.find("p") or dd).get_text(strip=True)
                )
                info.update(self._parse_condition_text(condition_text))  # type: ignore[arg-type]

        # 日付・開催場
        diary_tag = soup.find("p", class_="smalltxt")
        if diary_tag:
            diary_text = diary_tag.get_text(strip=True)
            m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", diary_text)
            if m:
                info["日付"] = f"{m.group(1)}/{m.group(2).zfill(2)}/{m.group(3).zfill(2)}"
            m = re.search(r"\d+回(\S+?)\d+日目", diary_text)
            if m:
                info["開催"] = m.group(1)

        return info

    def parse_payoff(self, html: str) -> list[PayoffRow]:
        """払い戻し情報を抽出する."""
        soup = self.parse_html(html)
        payoffs: list[PayoffRow] = []

        pay_tables = soup.find_all("table", class_="pay_table_01")
        if not pay_tables:
            return payoffs

        for table in pay_tables:
            for tr in table.find_all("tr"):
                th = tr.find("th")
                tds = tr.find_all("td")
                if not (th and len(tds) >= 2):
                    continue

                券種 = th.get_text(strip=True)
                組番list = [s.strip() for s in tds[0].get_text("\n").split("\n") if s.strip()]
                払戻金list = [s.strip() for s in tds[1].get_text("\n").split("\n") if s.strip()]
                人気list = (
                    [s.strip() for s in tds[2].get_text("\n").split("\n") if s.strip()]
                    if len(tds) > 2
                    else []
                )

                n = max(len(組番list), len(払戻金list), len(人気list), 1)
                for i in range(n):
                    payoffs.append({
                        "券種": 券種,
                        "組番": 組番list[i] if i < len(組番list) else "",
                        "払戻金": 払戻金list[i] if i < len(払戻金list) else "",
                        "人気": 人気list[i] if i < len(人気list) else "",
                    })

        return payoffs

    def _parse_condition_text(self, text: str) -> dict[str, str]:
        """コース条件テキストをパースする.

        例: "ダ右1200m / 天候 : 晴 / ダート : 稍重 / 発走 : 11:35"
        """
        result: dict[str, str] = {}

        course_match = re.search(r"(芝|ダ|障)(右|左|直)?\s*(?:外|内)?\s*(\d+)m", text)
        if course_match:
            course_type_map = {"芝": "芝", "ダ": "ダート", "障": "障害"}
            result["コース種別"] = course_type_map.get(course_match.group(1), course_match.group(1))
            if course_match.group(2):
                result["回り"] = course_match.group(2)
            result["距離"] = course_match.group(3)

        m = re.search(r"天候\s*[:：]\s*(\S+)", text)
        if m:
            result["天候"] = m.group(1)

        m = re.search(r"(?:芝|ダート|障害)\s*[:：]\s*(\S+)", text)
        if m:
            result["馬場状態"] = m.group(1)

        m = re.search(r"(\d{1,2}:\d{2})\s*発走", text)
        if not m:
            m = re.search(r"発走\s*[:：]\s*(\d{1,2}:\d{2})", text)
        if m:
            result["発走時刻"] = m.group(1)

        return result
