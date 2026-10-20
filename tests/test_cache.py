import json

import numpy as np
import pandas as pd
import pytest

from nbatotals import cache

pytest.importorskip("pyarrow")


def frame():
    return pd.DataFrame({"game_id": [1, 2, 3], "season": [2022, 2022, 2023], "proj": [221.5, np.nan, 230.25],
                         "label": ["a", None, "c"], "flag": [True, False, True]})


def test_round_trip_is_exact(tmp_path):
    df = frame()
    cache.save(tmp_path / "c", "demo", {"df": df}, {"n": 3})
    frames, meta = cache.load(tmp_path / "c", "demo")
    pd.testing.assert_frame_equal(frames["df"], df, check_exact=True)
    assert meta == {"n": 3}
    assert not any(p.suffix == ".pkl" for p in (tmp_path / "c").iterdir())


def test_refuses_another_kind_and_other_schema_versions(tmp_path):
    path = cache.save(tmp_path / "c", "demo", {"df": frame()})
    with pytest.raises(cache.CacheError, match="expected 'other'"):
        cache.load(path, "other")
    manifest = json.loads((path / cache.MANIFEST).read_text())
    for version, word in ((cache.SCHEMA_VERSION + 1, "newer"), (cache.SCHEMA_VERSION - 1, "older")):
        (path / cache.MANIFEST).write_text(json.dumps(manifest | {"schema_version": version}))
        with pytest.raises(cache.CacheError, match=word):
            cache.load(path, "demo")
    with pytest.raises(cache.CacheError, match="no cache"):
        cache.load(tmp_path / "missing", "demo")


def test_overwrite_replaces_old_frames(tmp_path):
    cache.save(tmp_path / "c", "demo", {"a": frame(), "b": frame()})
    cache.save(tmp_path / "c", "demo", {"a": frame().head(1)})
    frames, _ = cache.load(tmp_path / "c", "demo")
    assert list(frames) == ["a"] and len(frames["a"]) == 1
    assert not (tmp_path / "c" / "b.parquet").exists()


def test_fit_tuple_and_paths(tmp_path):
    pred, fits = frame(), pd.DataFrame({"test_season": [2022], "trained_on": ["2021-22"], "train_n": [1230]})
    path = cache.fit_cache_path(tmp_path, "elo_total")
    assert path == tmp_path / "cache" / "fit_elo_total"
    assert cache.fit_cache_path(tmp_path, "pace_eff") == tmp_path / "cache" / "fit"
    cache.save_fit(path, (pred, fits, 34650))
    p2, f2, n = cache.load_fit(path)
    pd.testing.assert_frame_equal(p2, pred)
    pd.testing.assert_frame_equal(f2, fits)
    assert n == 34650
