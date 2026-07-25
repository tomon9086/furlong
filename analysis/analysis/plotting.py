"""matplotlib のプロットまわりの共通セットアップ。"""

from __future__ import annotations

import warnings

import matplotlib.font_manager as fm
import matplotlib.pyplot as plt

_JAPANESE_FONT_CANDIDATES = [
    "Hiragino Sans",  # macOS
    "Hiragino Kaku Gothic Pro",  # macOS
    "Yu Gothic",  # Windows
    "Meiryo",  # Windows
    "Noto Sans CJK JP",  # Linux
    "Noto Sans JP",  # Linux
    "IPAexGothic",  # Linux
    "TakaoGothic",  # Linux
]


def setup_japanese_font() -> None:
    """matplotlib のフォントを、環境にインストール済みの日本語フォントに切り替える。

    `japanize-matplotlib` は distutils 依存で Python 3.12+ で動かないため使わず、
    OS にプリインストールされているフォントの中から使えるものを探す方式にしている。
    """
    available = {f.name for f in fm.fontManager.ttflist}
    for name in _JAPANESE_FONT_CANDIDATES:
        if name in available:
            plt.rcParams["font.family"] = name
            return
    warnings.warn(
        "日本語フォントが見つかりませんでした。グラフの日本語ラベルが文字化けする可能性があります。"
        f"（候補: {_JAPANESE_FONT_CANDIDATES}）",
        stacklevel=2,
    )
