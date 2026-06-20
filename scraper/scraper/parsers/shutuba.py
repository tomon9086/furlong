"""出馬表HTMLパーサー (race.netkeiba.com)."""

import logging
import re

from .base import BaseParser
from repository.models import RaceDetailRow, RaceInfo

logger = logging.getLogger(__name__)


class ShutsubaParser(BaseParser):
    """出馬表ページ (/race/shutuba.html?race_id=...) のHTMLパーサー."""

    def parse(self, html: str) -> list[RaceDetailRow]:
        """tr.HorseList から出走馬一覧を取得する.

        枠順未確定時は tr の id="tr_XX" から馬番を取得する。
        """
        soup = self.parse_html(html)

        rows: list[RaceDetailRow] = []
        for tr in soup.find_all("tr", class_="HorseList"):
            row = self._parse_horse_row(tr)
            if row:
                rows.append(row)

        if not rows:
            raise ValueError("出馬表にデータ行が見つかりません")

        return rows

    def _parse_horse_row(self, tr) -> RaceDetailRow | None:  # type: ignore[return]
        tds = tr.find_all("td")
        if not tds:
            return None

        row: RaceDetailRow = {}

        # 枠番: class が "Waku" で始まる td（例: Waku1, Waku2）
        waku_td = tr.find("td", class_=re.compile(r"^Waku"))
        if waku_td:
            row["枠番"] = waku_td.get_text(strip=True)

        # 馬番: class が "Umaban" で始まる td 優先、なければ tr の id="tr_XX" から取得
        umaban_td = tr.find("td", class_=re.compile(r"^Umaban"))
        if umaban_td:
            row["馬番"] = umaban_td.get_text(strip=True)
        else:
            tr_id = tr.get("id", "")
            m = re.search(r"tr_(\d+)", tr_id)
            if m:
                row["馬番"] = str(int(m.group(1)))

        # 馬名・馬ID: class="HorseInfo"
        horse_td = tr.find("td", class_="HorseInfo")
        if horse_td:
            row["馬名"] = horse_td.get_text(strip=True)
            horse_link = horse_td.find("a", href=re.compile(r"/horse/"))
            if horse_link and horse_link.get("href"):
                m = re.search(r"/horse/(\d+)", horse_link["href"])
                if m:
                    row["馬ID"] = m.group(1)

        # 性齢
        sexage_td = tr.find("td", class_="Barei")
        if sexage_td:
            row["性齢"] = sexage_td.get_text(strip=True)

        # 斤量: Barei td の次の td（クラスなし）
        barei_td = tr.find("td", class_="Barei")
        if barei_td:
            kinryo_td = barei_td.find_next_sibling("td")
            if kinryo_td:
                row["斤量"] = kinryo_td.get_text(strip=True)

        # 騎手・騎手ID
        jockey_td = tr.find("td", class_="Jockey")
        if jockey_td:
            row["騎手"] = jockey_td.get_text(strip=True)
            jockey_link = jockey_td.find("a", href=re.compile(r"/jockey/"))
            if jockey_link and jockey_link.get("href"):
                m = re.search(r"/jockey/(?:result/recent/)?(\d+)", jockey_link["href"])
                if m:
                    row["騎手ID"] = m.group(1)

        # 調教師・調教師ID
        trainer_td = tr.find("td", class_="Trainer")
        if trainer_td:
            row["調教師"] = trainer_td.get_text(strip=True)
            trainer_link = trainer_td.find("a", href=re.compile(r"/trainer/"))
            if trainer_link and trainer_link.get("href"):
                m = re.search(
                    r"/trainer/(?:result/recent/)?(\d+)", trainer_link["href"]
                )
                if m:
                    row["調教師ID"] = m.group(1)

        # 馬体重・体重変化: class="Weight"（例: "484(0)"）
        weight_td = tr.find("td", class_="Weight")
        if weight_td:
            row["馬体重"] = weight_td.get_text(strip=True)

        # 単勝オッズ: class="Txt_R" (Popular クラスと共存)
        odds_td = tr.find("td", class_="Txt_R")
        if odds_td:
            row["単勝オッズ"] = odds_td.get_text(strip=True)

        # 人気: class="Popular_Ninki"
        popular_td = tr.find("td", class_="Popular_Ninki")
        if popular_td:
            row["人気"] = popular_td.get_text(strip=True)

        return row if row.get("馬番") else None

    def parse_race_info(self, html: str) -> RaceInfo:
        """レースのメタ情報を抽出する."""
        soup = self.parse_html(html)
        info: RaceInfo = {}

        # レース名
        race_name_tag = soup.find("h1", class_="RaceName")
        if race_name_tag:
            info["レース名"] = race_name_tag.get_text(strip=True)

        # RaceData01: 発走時刻 / コース種別・距離・回り / 天候 / 馬場状態
        data01 = soup.find("div", class_="RaceData01")
        if data01:
            spans = [s.get_text(strip=True) for s in data01.find_all("span")]
            text01 = " ".join(spans)

            m = re.search(r"(\d{1,2}:\d{2})発走", text01)
            if m:
                info["発走時刻"] = m.group(1)

            m = re.search(r"(芝|ダート|障害)", text01)
            if m:
                info["コース種別"] = m.group(1)

            m = re.search(r"(\d{3,4})m", text01)
            if m:
                info["距離"] = m.group(1)

            m = re.search(r"(右|左|直線)", text01)
            if m:
                info["回り"] = m.group(1)

            m = re.search(r"天候\s*[:：]?\s*(\S+?)(?:\s|$|／)", text01)
            if m:
                info["天候"] = m.group(1)
            else:
                for span_text in spans:
                    m = re.search(r"天候\s*[:：]?\s*(\S+)", span_text)
                    if m:
                        info["天候"] = m.group(1)
                        break

            for span_text in spans:
                m = re.search(r"馬場\s*[:：]?\s*(\S+)", span_text)
                if m:
                    info["馬場状態"] = m.group(1)
                    break

        # RaceData02: 日付 / 開催場 / レース番号 / グレード / レース条件
        data02 = soup.find("div", class_="RaceData02")
        if data02:
            text02 = data02.get_text(strip=True)

            m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", text02)
            if m:
                info["日付"] = (
                    f"{m.group(1)}/{m.group(2).zfill(2)}/{m.group(3).zfill(2)}"
                )

            m = re.search(r"\d+回(\S+?)\d+日目", text02)
            if m:
                info["開催"] = m.group(1)

            m = re.search(r"(\d+)\s*R", text02)
            if m:
                info["R"] = m.group(1)

            for li in data02.find_all("li"):
                grade_img = li.find("img")
                if grade_img and grade_img.get("alt"):
                    info["グレード"] = grade_img["alt"]
                    break
                grade_span = li.find("span", class_=re.compile(r"Grade|Icon_Grade"))
                if grade_span:
                    info["グレード"] = grade_span.get_text(strip=True)
                    break

            # レース条件: 日付・開催回次・R番号・発走時刻・グレード以外の li テキスト
            for li in data02.find_all("li"):
                if li.find("img") or li.find("span"):
                    continue
                li_text = li.get_text(strip=True)
                if (
                    not re.search(r"^\d+回", li_text)
                    and not re.search(r"^\d{4}年", li_text)
                    and not re.search(r"^\d+R$", li_text)
                    and not re.search(r"^発走", li_text)
                    and re.search(r"歳|勝|オープン|マイル|ハンデ|別定|定量|馬齢|新馬|未勝利|牝|牡|障害", li_text)
                ):
                    info["レース条件"] = li_text
                    break

        # title タグからのフォールバック（RaceData02 で取れなかった場合）
        title_tag = soup.find("title")
        if title_tag:
            title_text = title_tag.get_text(strip=True)
            if "日付" not in info:
                m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", title_text)
                if m:
                    info["日付"] = (
                        f"{m.group(1)}/{m.group(2).zfill(2)}/{m.group(3).zfill(2)}"
                    )
            if "R" not in info:
                m = re.search(r"(\d+)R", title_text)
                if m:
                    info["R"] = m.group(1)

        return info
