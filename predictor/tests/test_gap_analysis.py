"""predictor.gap_analysis_experiment の単体テスト."""

import numpy as np
import pandas as pd
import pytest

from predictor import gap_analysis_experiment as gap


def test_summarize_gap_by_segment():
    """区切りごとの差と、全体の差に占める割合（合計1）を出す。"""
    values = pd.DataFrame(
        {"model": [2.0, 2.0, 3.0, 3.0], "market": [1.0, 1.0, 1.0, 1.0]}
    )
    segments = pd.DataFrame({"芝ダート": ["芝", "芝", "ダート", "ダート"]})
    result = gap._summarize(
        values, segments, np.arange(4), 4, 200, np.random.default_rng(0)
    ).set_index("値")
    assert result.loc["芝", "差"] == pytest.approx(1.0)
    assert result.loc["ダート", "差"] == pytest.approx(2.0)
    assert result["全体の差に占める割合"].sum() == pytest.approx(1.0)
    assert result.loc["ダート", "全体の差に占める割合"] == pytest.approx(2 / 3)
    assert (result["差_CI下限"] <= result["差"]).all()
