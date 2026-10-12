"""scheduler のジョブ失敗通知のテスト."""

import httpx
import pytest

from scraper import scheduler


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes]] = []

    def __call__(self, url: str, content: bytes, **kwargs) -> httpx.Response:
        self.calls.append((url, content))
        return httpx.Response(200, request=httpx.Request("POST", url))


def test_notifies_on_job_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """ジョブが例外で終わると NTFY_TOPIC_URL に通知が送られる。"""
    recorder = _Recorder()
    monkeypatch.setenv("NTFY_TOPIC_URL", "https://ntfy.example/topic")
    monkeypatch.setattr(scheduler.httpx, "post", recorder)

    def _fail() -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(scheduler, "scrape_incremental", _fail)
    scheduler._job_incremental()

    assert len(recorder.calls) == 1
    url, content = recorder.calls[0]
    assert url == "https://ntfy.example/topic"
    assert "scrape_incremental" in content.decode("utf-8")
    assert "RuntimeError: boom" in content.decode("utf-8")


def test_does_not_notify_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """ジョブが正常終了した場合は通知しない。"""
    recorder = _Recorder()
    monkeypatch.setenv("NTFY_TOPIC_URL", "https://ntfy.example/topic")
    monkeypatch.setattr(scheduler.httpx, "post", recorder)
    monkeypatch.setattr(scheduler, "scrape_shutuba_upcoming", lambda: None)

    scheduler._job_shutuba()

    assert recorder.calls == []


def test_skips_notification_without_topic_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """NTFY_TOPIC_URL が未設定なら通知しない。"""
    recorder = _Recorder()
    monkeypatch.delenv("NTFY_TOPIC_URL", raising=False)
    monkeypatch.setattr(scheduler.httpx, "post", recorder)

    scheduler._notify("message")

    assert recorder.calls == []


def test_notification_failure_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """通知に失敗してもジョブ側に例外を伝播させない。"""
    monkeypatch.setenv("NTFY_TOPIC_URL", "https://ntfy.example/topic")

    def _raise(*args, **kwargs) -> httpx.Response:
        raise httpx.ConnectError("unreachable")

    monkeypatch.setattr(scheduler.httpx, "post", _raise)

    scheduler._notify("message")
