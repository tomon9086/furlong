"""netkeiba.com HTTP クライアント."""

from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://db.netkeiba.com"
_RACE_BASE_URL = "https://race.netkeiba.com"
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
_REQUEST_INTERVAL = 3.0
_TIMEOUT = 30
_MAX_RETRIES = 3
_RETRY_STATUS = {429, 500, 502, 503, 504}


class NetkeibaClient:
    """netkeiba.com へのリクエストを管理するクライアント."""

    def __init__(
        self,
        request_interval: float = _REQUEST_INTERVAL,
        timeout: int = _TIMEOUT,
        max_retries: int = _MAX_RETRIES,
    ) -> None:
        self.request_interval = request_interval
        self.timeout = timeout
        self.max_retries = max_retries
        self._last_request_time: float = 0.0
        self._client = httpx.Client(
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
            timeout=timeout,
        )

    def get_race_list(
        self,
        start_year: int,
        start_mon: int,
        end_year: int,
        end_mon: int,
        page: int = 1,
        list_size: int = 100,
    ) -> str:
        """レース一覧ページを取得してHTMLを返す."""
        url = (
            f"{_BASE_URL}/?pid=race_list"
            f"&start_year={start_year}&start_mon={start_mon}"
            f"&end_year={end_year}&end_mon={end_mon}"
            f"&sort=date&list={list_size}&page={page}"
        )
        return self._get(url)

    def get_race(self, race_id: str) -> str:
        """レース詳細ページを取得してHTMLを返す."""
        url = f"{_BASE_URL}/race/{race_id}/"
        return self._get(url)

    def get_horse(self, horse_id: str) -> str:
        """馬詳細ページを取得してHTMLを返す."""
        url = f"{_BASE_URL}/horse/{horse_id}/"
        return self._get(url)

    def get_jockey(self, jockey_id: str) -> str:
        """騎手プロフィールページを取得してHTMLを返す."""
        url = f"{_BASE_URL}/jockey/profile/{jockey_id}/"
        return self._get(url)

    def get_trainer(self, trainer_id: str) -> str:
        """調教師プロフィールページを取得してHTMLを返す."""
        url = f"{_BASE_URL}/trainer/profile/{trainer_id}/"
        return self._get(url)

    def get_shutuba(self, race_id: str) -> str:
        """出馬表ページを取得してHTMLを返す."""
        url = f"{_RACE_BASE_URL}/race/shutuba.html?race_id={race_id}"
        return self._get(url)

    def get_race_list_by_date(self, kaisai_date: str) -> str:
        """開催日指定でレース一覧ページを取得してHTMLを返す (race.netkeiba.com).

        Args:
            kaisai_date: 開催日 (YYYYMMDD 形式)
        """
        url = f"{_RACE_BASE_URL}/top/race_list.html?kaisai_date={kaisai_date}"
        return self._get(url)

    def _get(self, url: str) -> str:
        """レートリミット・リトライ付きHTTP GETリクエスト."""
        last_exc: Exception | None = None

        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                wait = self.request_interval * (2 ** (attempt - 1))
                logger.debug(
                    "リトライ %d/%d: %.1f秒待機", attempt, self.max_retries, wait
                )
                time.sleep(wait)

            # レートリミット
            elapsed = time.monotonic() - self._last_request_time
            if self._last_request_time > 0 and elapsed < self.request_interval:
                time.sleep(self.request_interval - elapsed)

            try:
                logger.debug("GET %s", url)
                response = self._client.get(url)
                self._last_request_time = time.monotonic()

                if response.status_code in _RETRY_STATUS:
                    last_exc = httpx.HTTPStatusError(
                        f"{response.status_code}",
                        request=response.request,
                        response=response,
                    )
                    logger.warning(
                        "ステータスコード %d、リトライします", response.status_code
                    )
                    continue

                response.raise_for_status()
                # netkeiba は EUC-JP
                return response.content.decode("euc-jp", errors="replace")

            except httpx.RequestError as e:
                last_exc = e
                if attempt >= self.max_retries:
                    raise
                logger.warning(
                    "リクエストエラー: %s (試行 %d/%d)",
                    e,
                    attempt + 1,
                    self.max_retries + 1,
                )

        if last_exc is not None:
            raise last_exc
        raise httpx.RequestError("リクエストが失敗しました")

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "NetkeibaClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
