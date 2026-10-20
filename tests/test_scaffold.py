"""`new-model` on a temporary copy of the package: scaffold, register, pass the truncation test."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from nbatotals import scaffold

ROOT = Path(__file__).resolve().parents[1]

CHECK = """
import nbatotals, sys
from pathlib import Path
from nbatotals import params as params_io, synthetic
from nbatotals.evaluate import leakage
from nbatotals.model import registry
assert Path(nbatotals.__file__).is_relative_to(Path(sys.argv[1])), nbatotals.__file__
p = registry.get("my_model")
assert type(p).__name__ == "MyModel"
games, box = synthetic.generate(seasons=(2021, 2022), days=160, games_per_day=8, seed=0)
sample = leakage.stratified_sample(games, per_cell=10)
res = leakage.projector_truncation_check(p, games, box, params_io.load(), sample)
assert res["mismatches"] == [], res["mismatches"][:3]
print("ok", len(sample))
"""


@pytest.fixture
def copy(tmp_path):
    shutil.copytree(ROOT / "nbatotals", tmp_path / "nbatotals", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "config", tmp_path / "config")
    return tmp_path


def test_new_model_scaffolds_registers_and_passes_truncation(copy):
    path = scaffold.new_model("my_model", copy / "nbatotals")
    assert path == copy / "nbatotals" / "model" / "my_model.py"
    registry_text = (copy / "nbatotals" / "model" / "registry.py").read_text()
    assert "from nbatotals.model.my_model import MyModel\n" in registry_text
    assert "    MyModel.name: MyModel,\n" in registry_text
    with pytest.raises(ValueError, match="already exists"):  # a second run changes nothing
        scaffold.new_model("my_model", copy / "nbatotals")
    assert (copy / "nbatotals" / "model" / "registry.py").read_text() == registry_text
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"} | {"PYTHONPATH": str(copy)}
    out = subprocess.run([sys.executable, "-c", CHECK, str(copy)], cwd=copy, env=env, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.startswith("ok")


@pytest.mark.parametrize("slug", ["MyModel", "my-model", "1model", "class", ""])
def test_new_model_refuses_bad_names(copy, slug):
    before = (copy / "nbatotals" / "model" / "registry.py").read_text()
    with pytest.raises(ValueError):
        scaffold.new_model(slug, copy / "nbatotals")
    assert (copy / "nbatotals" / "model" / "registry.py").read_text() == before


def test_the_guide_shows_the_scaffold_template():
    guide = (ROOT / "docs" / "YOUR_FIRST_MODEL.md").read_text()
    assert scaffold.render("my_model") in guide
