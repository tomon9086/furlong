"""predictor.embedding の単体テスト。"""

import numpy as np
import pandas as pd

from predictor.embedding import auto_embedding_dim, save_embeddings, train_embeddings


class TestAutoEmbeddingDim:
    def test_small_cardinality(self):
        assert auto_embedding_dim(10) == max(2, round(10**0.25 * 4))

    def test_capped_at_50(self):
        assert auto_embedding_dim(10**8) == 50

    def test_minimum_is_2(self):
        assert auto_embedding_dim(1) >= 2


def _make_df(n: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    jockeys = [f"J{i}" for i in range(5)]
    trainers = [f"T{i}" for i in range(4)]
    sires = [f"S{i}" for i in range(3)]
    bms = [f"B{i}" for i in range(3)]
    return pd.DataFrame(
        {
            "jockey_id": rng.choice(jockeys, n),
            "trainer_id": rng.choice(trainers, n),
            "sire": rng.choice(sires, n),
            "broodmare_sire": rng.choice(bms, n),
            "is_placed": rng.integers(0, 2, n),
        }
    )


class TestTrainEmbeddings:
    def test_returns_vector_per_known_id(self):
        df = _make_df()
        result = train_embeddings(df, epochs=1, batch_size=32)
        assert set(result.keys()) == {
            "jockey_id",
            "trainer_id",
            "sire",
            "broodmare_sire",
        }
        for jid in df["jockey_id"].unique():
            assert jid in result["jockey_id"]

    def test_includes_mean_fallback(self):
        df = _make_df()
        result = train_embeddings(df, epochs=1, batch_size=32)
        for table in result.values():
            assert "__mean__" in table

    def test_vector_dim_matches_auto_embedding_dim(self):
        df = _make_df()
        result = train_embeddings(df, epochs=1, batch_size=32)
        n_jockeys = df["jockey_id"].nunique()
        expected_dim = auto_embedding_dim(n_jockeys)
        any_vec = next(v for k, v in result["jockey_id"].items() if k != "__mean__")
        assert len(any_vec) == expected_dim

    def test_rows_with_missing_category_excluded(self):
        df = _make_df()
        df["sire"] = "ONLY_SIRE"
        df.loc[0, "sire"] = None
        result = train_embeddings(df, epochs=1, batch_size=32)
        # 欠損値自体は vocab に含まれず、"__mean__" と実在する値のみが残る
        assert set(result["sire"].keys()) == {"ONLY_SIRE", "__mean__"}


class TestSaveEmbeddings:
    def test_save_creates_pickle(self, tmp_path):
        df = _make_df()
        embeddings = train_embeddings(df, epochs=1, batch_size=32)
        version_dir = save_embeddings(embeddings, embedding_dir=tmp_path)
        assert (version_dir / "embeddings.pkl").exists()
