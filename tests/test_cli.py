"""CLI smoke tests: every command runs, writes a manifest, and refuses bad input."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from wildfireguardian_forecast_value.cli.config import DEFAULTS, load_config, write_manifest
from wildfireguardian_forecast_value.cli.main import main


@pytest.fixture
def tiny_config(tmp_path) -> Path:
    cfg = {
        "name": "tiny",
        "seed": 3,
        "study": {"n_worlds": 12},
        "statistics": {"n_boot": 60, "frontier_boot": 20, "equivalence_margin": 2.0},
        "sweep": {
            "x": {"name": "eps_theta", "kind": "degradation",
                  "start": -0.3, "stop": 0.3, "num": 3},
            "y": {"name": "latency", "kind": "latency", "start": 0.0, "stop": 0.8, "num": 3},
        },
        "output": {"dir": str(tmp_path / "out")},
    }
    p = tmp_path / "tiny.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return p


class TestConfig:
    def test_defaults_load(self):
        cfg = load_config(None)
        assert cfg.name == DEFAULTS["name"]
        assert cfg.scenario().decision_time == 1.0
        assert len(cfg.pipeline()) == 6

    def test_unknown_top_level_key_is_an_error(self, tmp_path):
        p = tmp_path / "bad.yaml"
        p.write_text(yaml.safe_dump({"scenarios": {}}), encoding="utf-8")
        with pytest.raises(KeyError, match="unknown top-level key"):
            load_config(p)

    def test_unknown_nested_key_is_an_error(self, tmp_path):
        p = tmp_path / "bad.yaml"
        p.write_text(yaml.safe_dump({"loss": {"burnover_cost": 10}}), encoding="utf-8")
        with pytest.raises(KeyError, match="unknown configuration key"):
            load_config(p)

    def test_missing_file_is_an_error(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nope.yaml")

    def test_scenario_keys_pass_through(self, tmp_path):
        p = tmp_path / "s.yaml"
        p.write_text(yaml.safe_dump({"scenario": {"n_receptors": 7}}), encoding="utf-8")
        assert load_config(p).scenario().n_receptors == 7

    def test_error_model_is_built_when_present(self, tmp_path):
        p = tmp_path / "e.yaml"
        p.write_text(yaml.safe_dump({"error_model": {
            "channels": {"eps_theta": {"kind": "normal", "mu": 0.0, "sigma": 0.2},
                         "eps_r": {"kind": "normal", "mu": 0.0, "sigma": 0.2}},
            "correlation": [["eps_theta", "eps_r", 0.5]],
        }}), encoding="utf-8")
        em = load_config(p).error_model()
        assert em is not None and em.correlation_matrix[0, 1] == pytest.approx(0.5)

    def test_manifest_records_everything_needed_to_reproduce(self, tmp_path):
        cfg = load_config(None)
        path = write_manifest(cfg, tmp_path, {"command": "test"})
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["command"] == "test"
        assert payload["config"]["seed"] == cfg.seed
        assert "resolved_scenario" in payload and "resolved_pipeline" in payload
        assert payload["resolved_scenario"]["loss"]["burnover_loss"] == 50.0


class TestCommands:
    def test_validate(self, capsys):
        assert main(["validate"]) == 0
        out = capsys.readouterr().out
        assert "hand-solvable examples passed" in out
        assert "structural invariants passed" in out

    def test_validate_verbose_prints_derivations(self, capsys):
        main(["validate", "-v"])
        assert "->" in capsys.readouterr().out

    def test_degrade(self, tiny_config, tmp_path, capsys):
        assert main(["degrade", str(tiny_config), "--out", str(tmp_path / "d")]) == 0
        out = capsys.readouterr().out
        assert "Degradation pipeline" in out
        assert "None of these scores is consulted" in out
        assert (tmp_path / "d" / "manifest.json").exists()
        assert (tmp_path / "d" / "degrade.json").exists()

    def test_cases(self, capsys):
        assert main(["cases"]) == 0
        out = capsys.readouterr().out
        for key in ("case_1", "case_2", "case_3", "case_4"):
            assert key in out
        assert "value column is close to reversed" in out

    def test_run_toy_study(self, tiny_config, tmp_path, capsys):
        assert main(["run-toy-study", str(tiny_config)]) == 0
        out = capsys.readouterr().out
        assert "unit of analysis is the WORLD" in out
        assert "clustering diagnostics" in out
        d = tmp_path / "out"
        assert (d / "manifest.json").exists() and (d / "summary.json").exists()
        assert any(d.glob("worlds.*"))
        summary = json.loads((d / "summary.json").read_text(encoding="utf-8"))
        assert summary["unit_of_analysis"] == "world"
        assert summary["n_worlds"] == 12

    def test_sweep_then_estimate_frontier(self, tiny_config, tmp_path, capsys):
        assert main(["sweep", str(tiny_config)]) == 0
        d = tmp_path / "out"
        results = next(iter(d.glob("sweep.*")))
        assert (d / "sweep_axes.json").exists()
        capsys.readouterr()
        assert main(["estimate-frontier", str(results), "--n-boot", "25",
                     "--no-figure"]) == 0
        out = capsys.readouterr().out
        assert "monotonicity (measured, not assumed)" in out
        frontier = json.loads((d / "frontier.json").read_text(encoding="utf-8"))
        assert "monotonicity" in frontier and "band" in frontier

    def test_estimate_frontier_without_axes_explains_itself(self, tmp_path):
        import pandas as pd
        p = tmp_path / "orphan.csv"
        pd.DataFrame({"y_index": [0], "x_index": [0], "world_id": [0], "delta_j": [1.0],
                      "value_fraction": [1.0], "action_changed": [True],
                      "forecast_available": [True]}).to_csv(p, index=False)
        with pytest.raises(FileNotFoundError, match="sweep_axes.json"):
            main(["estimate-frontier", str(p)])

    def test_estimate_frontier_rejects_unknown_format(self, tmp_path):
        p = tmp_path / "x.nc"
        p.write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="unsupported results format"):
            main(["estimate-frontier", str(p)])

    @pytest.mark.slow
    def test_demo_writes_every_figure(self, tiny_config, tmp_path):
        assert main(["demo", str(tiny_config), "--out", str(tmp_path / "demo"),
                     "--figures", str(tmp_path / "figs"), "--n-worlds", "8"]) == 0
        figs = tmp_path / "figs"
        for name in ("scenario_map.png", "case_comparison.png", "skill_vs_value.png",
                     "frontier_direction_latency.png"):
            assert (figs / name).exists(), name
        assert (tmp_path / "demo" / "manifest.json").exists()


class TestParser:
    def test_requires_a_subcommand(self):
        with pytest.raises(SystemExit):
            main([])

    def test_version(self, capsys):
        with pytest.raises(SystemExit) as e:
            main(["--version"])
        assert e.value.code == 0
