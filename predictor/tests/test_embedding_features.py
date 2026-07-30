"""predictor.embedding_features の単体テスト。"""

import pickle

import numpy as np
import pandas as pd
import pytest

from predictor.embedding_features import (
    add_embedding_features,
    apply_pca,
    load_embeddings,
)


def _save(embeddings: dict, embedding_dir, version: str = "20260101_000000") -> None:
    """embedding.save_embeddings と同じ形式で保存する（torch 非依存のヘルパー）。"""
    version_dir = embedding_dir / version
    version_dir.mkdir(parents=True, exist_ok=True)
    with open(version_dir / "embeddings.pkl", "wb") as f:
        pickle.dump(embeddings, f)


def _make_embeddings() -> dict[str, dict[str, np.ndarray]]:
    return {
        "jockey_id": {
            "J0": np.array([1.0, 0.0, 0.0]),
            "J1": np.array([0.0, 1.0, 0.0]),
            "__mean__": np.array([0.5, 0.5, 0.0]),
        },
        "trainer_id": {
            "T0": np.array([1.0, 2.0]),
            "T1": np.array([3.0, -1.0]),
            "__mean__": np.array([2.0, 0.5]),
        },
    }


class TestAddEmbeddingFeatures:
    def test_known_id_maps_to_vector(self):
        df = pd.DataFrame({"jockey_id": ["J0", "J1"]})
        embeddings = _make_embeddings()
        result, cols = add_embedding_features(df, embeddings, categories=["jockey_id"])
        assert cols == ["jockey_id_emb_0", "jockey_id_emb_1", "jockey_id_emb_2"]
        assert result.loc[0, "jockey_id_emb_0"] == pytest.approx(1.0)
        assert result.loc[1, "jockey_id_emb_1"] == pytest.approx(1.0)

    def test_unknown_id_falls_back_to_mean(self):
        df = pd.DataFrame({"jockey_id": ["UNKNOWN_JOCKEY"]})
        embeddings = _make_embeddings()
        result, _ = add_embedding_features(df, embeddings, categories=["jockey_id"])
        assert result.loc[0, "jockey_id_emb_0"] == pytest.approx(0.5)
        assert result.loc[0, "jockey_id_emb_1"] == pytest.approx(0.5)

    def test_missing_value_falls_back_to_mean(self):
        df = pd.DataFrame({"jockey_id": [None]})
        embeddings = _make_embeddings()
        result, _ = add_embedding_features(df, embeddings, categories=["jockey_id"])
        assert result.loc[0, "jockey_id_emb_0"] == pytest.approx(0.5)

    def test_multiple_categories(self):
        df = pd.DataFrame({"jockey_id": ["J0"], "trainer_id": ["T0"]})
        embeddings = _make_embeddings()
        result, cols = add_embedding_features(
            df, embeddings, categories=["jockey_id", "trainer_id"]
        )
        assert "trainer_id_emb_0" in cols
        assert result.loc[0, "trainer_id_emb_1"] == pytest.approx(2.0)

    def test_category_not_in_df_is_skipped(self):
        df = pd.DataFrame({"jockey_id": ["J0"]})
        embeddings = _make_embeddings()
        result, cols = add_embedding_features(
            df, embeddings, categories=["jockey_id", "trainer_id"]
        )
        assert "trainer_id_emb_0" not in result.columns
        assert cols == ["jockey_id_emb_0", "jockey_id_emb_1", "jockey_id_emb_2"]


class TestApplyPca:
    def test_reduces_dimension(self):
        embeddings = _make_embeddings()
        reduced = apply_pca(embeddings, n_components=1)
        for table in reduced.values():
            for vec in table.values():
                assert len(vec) == 1

    def test_preserves_keys(self):
        embeddings = _make_embeddings()
        reduced = apply_pca(embeddings, n_components=1)
        assert set(reduced["jockey_id"].keys()) == set(
            embeddings["jockey_id"].keys()
        )

    def test_n_components_capped_at_original_dim(self):
        embeddings = _make_embeddings()
        reduced = apply_pca(embeddings, n_components=100)
        # trainer_id は元々2次元なので2次元のまま
        for vec in reduced["trainer_id"].values():
            assert len(vec) == 2


class TestLoadEmbeddings:
    def test_loads_latest_version(self, tmp_path):
        embeddings = _make_embeddings()
        _save(embeddings, tmp_path)
        loaded = load_embeddings(embedding_dir=tmp_path)
        assert set(loaded.keys()) == set(embeddings.keys())

    def test_raises_if_no_versions(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_embeddings(embedding_dir=tmp_path)
