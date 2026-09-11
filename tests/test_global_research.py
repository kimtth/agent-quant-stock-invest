"""Offline contracts for the global research refactor, not performance evidence.

Every market observation below is synthetic. These tests check APIs, accounting,
calendars and causality, never profitability or parity with deployment rules.
No production module is imported during collection; module state is isolated
from the independent portfolio-history suite. All generated files live in tmp_path.
"""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import textwrap
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import yfinance as yf


TOOLS = Path(__file__).resolve().parents[1] / ".old" / "tools"
SCRIPTS = tuple(sorted(path.stem for path in TOOLS.glob("*.py")))
OHLC = ["Open", "High", "Low", "Close"]


def deny_network(*args, **kwargs):
    raise AssertionError("Offline test attempted network access")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.delenv("GLOBAL_RESEARCH_CONFIG", raising=False)
    monkeypatch.setattr(yf, "download", deny_network)
    monkeypatch.setattr(socket.socket, "connect", deny_network)
    monkeypatch.setattr(socket, "create_connection", deny_network)


@pytest.fixture
def modules(monkeypatch):
    """Fresh tool imports without altering other tests' cached module objects."""
    monkeypatch.syspath_prepend(str(TOOLS))
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    for name in SCRIPTS:
        monkeypatch.delitem(sys.modules, name, raising=False)
    try:
        yield importlib.import_module
    finally:
        for name in SCRIPTS:
            sys.modules.pop(name, None)


def bars(n=620, *, scale=1.0):
    """Oscillation keeps RSI defined; the fixture is not a market forecast."""
    index = pd.bdate_range("2020-01-02", periods=n, name="Date")
    t = np.arange(n, dtype=float)
    close = scale * (100 + 0.035 * t + 2 * np.sin(t / 5))
    open_ = close * (1 + 0.002 * np.cos(t / 3))
    return pd.DataFrame(
        {"Open": open_, "High": np.maximum(open_, close) * 1.01,
         "Low": np.minimum(open_, close) * 0.99, "Close": close,
         "Volume": np.full(n, 1_000_000.0)}, index=index,
    )


@pytest.fixture
def data(modules):
    config = modules("market_config").CONFIG
    return {symbol: bars(scale=1 + i / 20)
            for i, symbol in enumerate(sorted(set(config.symbols.values()) | {"SPY", "QQQ"}))}


def vix_for(index):
    return pd.DataFrame({"vix": 20.0, "vixchg5": 0.0}, index=index)


def guarded_process(code, tmp_path, *, config=None):
    """A separate interpreter must never download, even if an exception is caught."""
    bootstrap = """
import importlib, runpy, socket, sys
import yfinance as yf
attempts = []
def forbidden(*args, **kwargs):
    attempts.append('network')
    raise AssertionError('Offline subprocess attempted network access')
yf.download = forbidden
socket.socket.connect = forbidden
socket.create_connection = forbidden
"""
    env = os.environ.copy()
    env.pop("GLOBAL_RESEARCH_CONFIG", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    if config is not None:
        env["GLOBAL_RESEARCH_CONFIG"] = str(config)
    command = textwrap.dedent(bootstrap) + f"\nsys.path.insert(0, {str(TOOLS)!r})\n"
    command += textwrap.dedent(code) + "\nassert not attempts, attempts\n"
    result = subprocess.run(
        [sys.executable, "-B", "-c", command], cwd=tmp_path, env=env,
        capture_output=True, text=True, encoding="utf-8", timeout=90,
    )
    # Preserve the complete production traceback rather than hiding it behind a skip.
    assert result.returncode == 0, result.stderr + "\n" + result.stdout
    return result


@pytest.mark.parametrize("script", SCRIPTS)
def test_every_script_import_is_silent_and_offline(script, tmp_path):
    result = guarded_process(f"importlib.import_module({script!r})", tmp_path)
    assert result.stdout == "", result.stdout
    assert result.stderr == "", result.stderr
    assert not list(tmp_path.iterdir()), "Import created files in the working directory"


def test_default_config_and_global_role_aliases(modules):
    mc = modules("market_config")
    cfg = mc.CONFIG
    assert cfg == mc.ResearchConfig()
    assert (cfg.benchmark, cfg.symbol("growth_2x"), cfg.symbol("equity_2x")) == ("SPY", "QLD", "SSO")
    assert (cfg.symbol("semiconductor_2x"), cfg.symbol("dollar")) == ("USD", "UUP")
    assert cfg.cost == 0.001 and cfg.warmup == 260
    assert not any(t.endswith((".KS", ".KQ")) for t in cfg.symbols.values())
    for name in ("backtest_momentum_v2", "backtest_sleeves", "eval_unified"):
        module = modules(name)
        assert module.NDX2 == "QLD"
        assert module.SOX2 == "USD"
        assert module.USD == "UUP"
    core = modules("backtest_etf_combos")
    universe = set().union(*(set(s.tickers) for s in core.STRATEGIES))
    assert {"SPY", "SSO", "QLD", "USD", "UUP"} <= universe


@pytest.mark.parametrize("values", [
    {"benchmark": "IWM"}, {"benchmark": "spy"},
    {"start": "2021-01-01", "end": "2021-01-01"},
    {"start": "2022-01-01", "end": "2021-01-01"},
    {"start": "not-a-date"}, {"end": "2021-02-30"},
    {"cost": -0.01}, {"cost": 1.0}, {"cost": float("nan")},
    {"cost": float("inf")}, {"warmup": 259},
    {"min_daily_value": -1}, {"min_daily_value": float("nan")},
    {"min_daily_value": float("inf")}, {"symbols": {}},
])
def test_config_rejects_invalid_contracts(modules, values):
    with pytest.raises(ValueError):
        modules("market_config").ResearchConfig(**values)


@pytest.mark.parametrize("bad_symbol", ["", "  ", None, 123])
def test_config_rejects_invalid_ticker_values(modules, bad_symbol):
    mc = modules("market_config")
    with pytest.raises(ValueError, match="non-empty ticker"):
        mc.ResearchConfig(symbols=mc.DEFAULT_SYMBOLS | {"growth": bad_symbol})


def test_config_defaults_are_independent_and_boundaries_valid(modules):
    mc = modules("market_config")
    first = mc.ResearchConfig(benchmark="QQQ", cost=0, warmup=260, min_daily_value=0)
    second = mc.ResearchConfig()
    first.symbols["growth"] = "TEST"
    assert second.symbol("growth") == mc.DEFAULT_SYMBOLS["growth"] == "QQQ"
    assert mc.ResearchConfig(cost=0.999, warmup=300).cost == 0.999


def test_json_config_resolves_all_paths_and_merges_roles(modules, tmp_path, monkeypatch):
    mc = modules("market_config")
    folder = tmp_path / "contract"
    folder.mkdir()
    fields = ("cache_dir", "data_dir", "history_csv", "compare_csv", "workbook", "output")
    values = {field: f"inputs/{field}" for field in fields}
    values.update(benchmark="QQQ", cost=0.002, symbols={"growth_2x": "TEST"})
    source = folder / "config.json"
    source.write_text(json.dumps(values), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    cfg = mc.load_config(source)
    for field in fields:
        assert getattr(cfg, field) == (folder / values[field]).resolve()
    assert cfg.symbol("growth_2x") == "TEST"
    assert cfg.symbol("equity_2x") == "SSO"
    assert cfg.benchmark == "QQQ" and cfg.cost == 0.002
    assert json.loads(json.dumps(cfg.manifest()))["data_dir"] == str(cfg.data_dir)
    monkeypatch.setenv("GLOBAL_RESEARCH_CONFIG", str(source))
    assert mc.load_config() == cfg
    override = folder / "override.json"
    override.write_text('{"benchmark": "SPY", "output": null}', encoding="utf-8")
    assert mc.load_config(override).benchmark == "SPY"
    assert mc.load_config(override).output is None


@pytest.mark.parametrize("content,error", [
    ("{", json.JSONDecodeError), ('{"unknown": 1}', TypeError),
    ('{"symbols": {"unknown_role": "TEST"}}', ValueError),
])
def test_config_json_errors_are_explicit(modules, tmp_path, content, error):
    path = tmp_path / "bad.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(error):
        modules("market_config").load_config(path)


def test_missing_config_is_not_silently_defaulted(modules, tmp_path):
    with pytest.raises(FileNotFoundError):
        modules("market_config").load_config(tmp_path / "absent.json")


@pytest.mark.parametrize("layout", ["flat", "ticker_first", "price_first"])
@pytest.mark.parametrize("symbols", [["SPY"], ["SPY", "QQQ", "SPY"]], ids=["single", "multi-deduplicated"])
def test_download_yfinance_shapes_and_contract(modules, monkeypatch, layout, symbols):
    if layout == "flat" and len(set(symbols)) > 1:
        # Yahoo's flat-column form is only a single-ticker response.
        symbols = ["SPY", "SPY"]
    md = modules("market_data")
    expected = {symbol: bars(12, scale=i + 1) for i, symbol in enumerate(dict.fromkeys(symbols))}
    raw = next(iter(expected.values())).copy() if layout == "flat" else pd.concat(expected, axis=1)
    if layout == "price_first":
        raw = raw.swaplevel(axis=1)
    raw.loc[pd.Timestamp("2020-02-01")] = np.nan
    calls = []

    def download(tickers, **kwargs):
        calls.append((tickers, kwargs))
        return raw.copy()

    monkeypatch.setattr(yf, "download", download)
    result = md.download_ohlcv(symbols, "2020-01-03", "2020-01-15")
    assert calls == [(list(expected), {"start": "2020-01-03", "end": "2020-01-15",
                                       "auto_adjust": True, "progress": False, "group_by": "ticker"})]
    assert list(result) == list(expected)
    for symbol in expected:
        want = expected[symbol].loc["2020-01-03":"2020-01-14"]
        pd.testing.assert_frame_equal(result[symbol], want, check_freq=False)


def test_download_missing_ticker_and_empty_request(modules, monkeypatch):
    md = modules("market_data")
    with pytest.raises(ValueError, match="At least one"):
        md.download_ohlcv([], "2020-01-01", "2021-01-01")
    monkeypatch.setattr(yf, "download", lambda *a, **k: pd.concat({"SPY": bars(5)}, axis=1))
    with pytest.raises(ValueError, match="No data returned for QQQ"):
        md.download_ohlcv(["QQQ"], "2020-01-01", "2021-01-01")


def test_local_csv_bounds_normalization_and_no_download(modules, monkeypatch, tmp_path):
    md = modules("market_data")
    monkeypatch.setattr(md, "CONFIG", replace(md.CONFIG, data_dir=tmp_path))
    frame = bars(10).rename(columns=str.lower).iloc[::-1]
    frame.index.name = "date"
    frame.to_csv(tmp_path / "SPY.csv")
    result = md.download_ohlcv(["SPY", "SPY"], "2020-01-03", "2020-01-10")
    pd.testing.assert_frame_equal(result["SPY"], bars(10).loc["2020-01-03":"2020-01-09"].rename_axis("date"), check_freq=False)
    with pytest.raises(ValueError, match="no data in"):
        md.download_ohlcv(["SPY"], "2030-01-01", "2031-01-01")
    with pytest.raises(FileNotFoundError, match="QQQ.csv"):
        md.download_ohlcv(["QQQ"], "2020-01-01", "2021-01-01")


@pytest.mark.parametrize("fault,message", [
    ("missing_date", "Date column"), ("missing_column", "expected Date"),
    ("duplicate", "duplicate or invalid dates"), ("invalid_date", None),
    ("nan", "missing OHLCV"), ("infinite", "non-finite"),
    ("zero_price", "prices must be positive"), ("negative_volume", "volume non-negative"),
    ("high_below_close", "inconsistent OHLC"), ("low_above_open", "inconsistent OHLC"),
    ("nonnumeric", None), ("empty", "empty data"),
])
def test_local_csv_invalid_bars_fail(modules, monkeypatch, tmp_path, fault, message):
    md = modules("market_data")
    monkeypatch.setattr(md, "CONFIG", replace(md.CONFIG, data_dir=tmp_path))
    frame = bars(5).reset_index()
    if fault == "missing_date":
        frame = frame.drop(columns="Date")
    elif fault == "missing_column":
        frame = frame.drop(columns="High")
    elif fault == "duplicate":
        frame.loc[1, "Date"] = frame.loc[0, "Date"]
    elif fault == "invalid_date":
        frame["Date"] = frame["Date"].astype(str)
        frame.loc[0, "Date"] = "invalid"
    elif fault == "empty":
        frame = frame.iloc[:0]
    else:
        column, value = {
            "nan": ("Close", np.nan), "infinite": ("Close", np.inf),
            "zero_price": ("Open", 0.0), "negative_volume": ("Volume", -1.0),
            "high_below_close": ("High", 1.0), "low_above_open": ("Low", 1000.0),
            "nonnumeric": ("Volume", "invalid"),
        }[fault]
        if fault == "nonnumeric":
            frame[column] = frame[column].astype(object)
        frame.loc[0, column] = value
    frame.to_csv(tmp_path / "SPY.csv", index=False)
    with pytest.raises(ValueError, match=message):
        md.download_ohlcv(["SPY"], "2020-01-01", "2021-01-01")


def test_validate_bars_copies_sorts_and_removes_timezone(modules):
    md = modules("market_data")
    source = bars(5).iloc[::-1].rename(columns=lambda c: f" {c.lower()} ")
    source.index = source.index.tz_localize("America/New_York")
    original = source.copy(deep=True)
    got = md.validate_bars(source, "SPY")
    pd.testing.assert_frame_equal(source, original)
    pd.testing.assert_frame_equal(got, bars(5), check_freq=False)


@pytest.mark.parametrize("benchmark", ["SPY", "QQQ"])
def test_load_all_uses_benchmark_sessions_without_proxies(modules, monkeypatch, tmp_path, data, benchmark):
    core = modules("backtest_etf_combos")
    proxy = modules("etf_proxy_history")
    monkeypatch.setattr(proxy, "build_proxies", deny_network)
    monkeypatch.setattr(core, "CONFIG", replace(core.CONFIG, benchmark=benchmark, data_dir=tmp_path))
    monkeypatch.setattr(core, "CACHE", tmp_path / "unused.pkl")
    absent_session = data[benchmark].index[100]
    data[benchmark] = data[benchmark].drop(index=absent_session)
    # A late inception and a missing session must remain absent, not be backfilled.
    data["USD"] = data["USD"].iloc[30:].drop(index=data["USD"].index[150])
    expected_calendar = data[benchmark].index
    requested = []

    def download(symbols, start, end):
        requested.append((symbols, start, end))
        return {t: (bars() if t == "^VIX" else data[t]).copy() for t in symbols}

    monkeypatch.setattr(core, "download_ohlcv", download)
    actual, vix, regime, report = core.load_all()
    assert len(requested) == 2
    assert set(requested[0][0]) == set(core.CONFIG.symbols.values()) | {"SPY", "QQQ"}
    assert requested[1][0] == ["^VIX"]
    pd.testing.assert_index_equal(regime.index, expected_calendar)
    expected_regime = (data[benchmark].Close >= data[benchmark].Close.rolling(200).mean()).astype(float)
    pd.testing.assert_series_equal(regime, expected_regime)
    for symbol, frame in actual.items():
        pd.testing.assert_frame_equal(frame, data[symbol].loc[data[symbol].index.intersection(expected_calendar)])
        assert absent_session not in frame.index
    assert actual["USD"].index[0] == data["USD"].index[0]
    assert set(report.source) == {"actual adjusted OHLCV"}
    assert report.set_index("ticker").sessions.to_dict() == {t: len(f) for t, f in actual.items()}
    pd.testing.assert_series_equal(vix.vix, bars().Close, check_names=False)
    assert not core.CACHE.exists()


def test_load_all_cache_hit_refresh_and_offline_bypass(modules, monkeypatch, tmp_path, data):
    core = modules("backtest_etf_combos")
    monkeypatch.setattr(core, "CACHE", tmp_path / "cache" / "fixture.pkl")
    monkeypatch.setattr(core, "download_ohlcv", lambda ts, *a: {t: bars() if t == "^VIX" else data[t].copy() for t in ts})
    first = core.load_all()
    assert core.CACHE.is_file()
    monkeypatch.setattr(core, "download_ohlcv", deny_network)
    cached = core.load_all()
    pd.testing.assert_frame_equal(first[0]["SPY"], cached[0]["SPY"])
    with pytest.raises(AssertionError, match="Offline test"):
        core.load_all(refresh=True)
    monkeypatch.setattr(core, "CONFIG", replace(core.CONFIG, data_dir=tmp_path))
    with pytest.raises(AssertionError, match="Offline test"):
        core.load_all()


@pytest.mark.parametrize("change", [
    {"benchmark": "QQQ"}, {"start": "2006-01-01"}, {"end": "2026-08-01"},
    {"cost": 0.002}, {"warmup": 300}, {"min_daily_value": 10.0},
    {"symbols": {"growth_2x": "TEST"}}, {"data_dir": "fixtures"},
])
def test_cache_names_distinguish_configurations(modules, monkeypatch, tmp_path, change):
    mc = modules("market_config")
    monkeypatch.setattr(mc, "CONFIG", replace(mc.CONFIG, cache_dir=tmp_path))
    core = modules("backtest_etf_combos")
    first = core.CACHE
    values = dict(change)
    if "symbols" in values:
        values["symbols"] = mc.DEFAULT_SYMBOLS | values["symbols"]
    if "data_dir" in values:
        values["data_dir"] = tmp_path / values["data_dir"]
    monkeypatch.setattr(mc, "CONFIG", replace(mc.CONFIG, **values))
    importlib.reload(core)
    assert core.CACHE != first
    assert core.CACHE.parent == first.parent == tmp_path
    assert core.CACHE != TOOLS / "_etf_cache.pkl"
    changed = core.CACHE
    importlib.reload(core)
    assert core.CACHE == changed


def test_loader_rejects_short_and_nonoverlapping_histories(modules, monkeypatch, tmp_path):
    core = modules("backtest_etf_combos")
    monkeypatch.setattr(core, "download_ohlcv", lambda *a: {"SPY": bars(core.WARMUP)})
    with pytest.raises(ValueError, match="Insufficient history for warmup"):
        core.load(["SPY"])
    monkeypatch.setattr(core, "CONFIG", replace(core.CONFIG, data_dir=tmp_path))
    late = bars(300)
    late.index = late.index + pd.DateOffset(years=5)
    monkeypatch.setattr(core, "load", lambda *a: {"SPY": bars(300), "QLD": late})
    monkeypatch.setattr(core, "load_vix", lambda: vix_for(late.index))
    with pytest.raises(ValueError, match="Insufficient overlapping sessions"):
        core.load_all()


def core_run(core, frame, *, buy=None, sell=None, **kwargs):
    strategy = core.Strategy("TEST", "Synthetic accounting only", {"SPY": "fixture"},
                             buy or (lambda f, v: True), sell or (lambda f, v: False))
    return core.backtest(strategy, {"SPY": frame}, {"SPY": core.build_features(frame)},
                         vix_for(frame.index), kwargs.pop("target", None), kwargs.pop("stop", None),
                         max_pos=1, **kwargs)


def test_core_first_close_signal_fills_next_open_and_sell_is_delayed(modules):
    core = modules("backtest_etf_combos")
    frame = bars()
    w = core.WARMUP
    # One buy at the first eligible close, one sell on the following close.
    frame.iloc[w + 1, frame.columns.get_indexer(OHLC)] = [200, 222, 198, 220]
    frame.iloc[w + 2, frame.columns.get_indexer(OHLC)] = [180, 184, 176, 182]
    features = core.build_features(frame)
    assert features.iloc[w].notna().all(), "Fixture must actually produce an eligible signal"
    marker = features.iloc[w]["value"]
    result = core_run(core, frame, buy=lambda f, v: f["value"] == marker, sell=lambda f, v: True)
    assert result is not None
    curve = result["curve"]
    assert curve.index[0] == frame.index[w]
    assert curve.iloc[0] == 1.0
    shares = 1 / (200 * (1 + core.COST))
    assert curve.iloc[1] == pytest.approx(shares * 220)
    assert curve.iloc[2] == pytest.approx(shares * 180 * (1 - core.COST))
    np.testing.assert_allclose(curve.iloc[2:], curve.iloc[2])
    assert result["trades"] == 1


@pytest.mark.parametrize("open_price,expected_exit", [(100.0, 90.0), (80.0, 80.0)])
def test_core_stop_precedes_target_and_respects_gap_open(modules, open_price, expected_exit):
    core = modules("backtest_etf_combos")
    frame = bars()
    w = core.WARMUP
    frame.iloc[w + 1, frame.columns.get_indexer(OHLC)] = [100, 101, 99, 100]
    frame.iloc[w + 2, frame.columns.get_indexer(OHLC)] = [open_price, 120, 75, 100]
    marker = core.build_features(frame).iloc[w]["value"]
    result = core_run(core, frame, buy=lambda f, v: f["value"] == marker, target=10, stop=-10)
    assert result is not None
    expected = expected_exit * (1 - core.COST) / (100 * (1 + core.COST))
    assert result["curve"].iloc[2] == pytest.approx(expected)
    assert result["trades"] == 1


def test_core_future_mutations_do_not_change_past_features_or_equity(modules):
    core = modules("backtest_etf_combos")
    original = bars()
    changed = original.copy(deep=True)
    cut = 480
    changed.loc[changed.index[cut:], OHLC] *= 0.35
    changed.loc[changed.index[cut:], "Volume"] *= 7
    pd.testing.assert_frame_equal(core.build_features(original).iloc[:cut], core.build_features(changed).iloc[:cut])
    rule = {"buy": lambda f, v: f["ret20"] > 0, "sell": lambda f, v: f["ret20"] < 0}
    before, after = core_run(core, original, **rule), core_run(core, changed, **rule)
    assert before is not None and after is not None
    pd.testing.assert_series_equal(before["curve"].loc[:original.index[cut - 1]], after["curve"].loc[:original.index[cut - 1]])
    assert not before["curve"].equals(after["curve"]), "Mutation must exercise a different future"


def test_core_short_window_and_risk_off_gate(modules):
    core = modules("backtest_etf_combos")
    assert core_run(core, bars(core.WARMUP + 249)) is None
    frame = bars()
    result = core_run(core, frame, regime=pd.Series(0.0, index=frame.index))
    assert result is not None
    np.testing.assert_array_equal(result["curve"], 1.0)
    assert result["trades"] == result["exposure"] == 0


def assert_series_finite(series, index):
    assert isinstance(series, pd.Series)
    # Engines rebuild calendars from observed dates; names/freq are not API contracts.
    pd.testing.assert_index_equal(series.index, index, check_names=False)
    assert np.isfinite(series.to_numpy()).all()


@pytest.mark.parametrize("mode", ["cont", "step"])
def test_shared_voltarget_build_stats_and_causality(modules, data, mode):
    vt = modules("backtest_voltarget")
    args = ("QQQ", "QLD", "QQQ", ["IEF", "GLD", "UUP"], 15, mode, 200, 12.0)
    result = vt.build(data, *args, cap=2.0)
    assert_series_finite(result, data["QQQ"].index)
    summary = vt.stats(result, label="synthetic", note="not performance evidence")
    assert summary["label"] == "synthetic"
    assert summary["curve"].index[0] == result.index[vt.WARMUP]
    assert np.isfinite(summary["curve"]).all()
    changed = {t: f.copy(deep=True) for t, f in data.items()}
    for frame in changed.values():
        frame.loc[frame.index[480:], OHLC] *= 0.5
    pd.testing.assert_series_equal(result.iloc[:480], vt.build(changed, *args).iloc[:480])


def test_shared_panel_trims_overlap_forward_fills_only_after_inception(modules, data):
    vt = modules("backtest_voltarget")
    data["QLD"] = data["QLD"].iloc[20:-5]
    missing = data["QLD"].index[50]
    prior = data["QLD"].index[49]
    data["QLD"] = data["QLD"].drop(index=missing)
    close, high = vt.panel(data, ["QQQ", "QLD"])
    assert close.index[0] == data["QLD"].index[0]
    assert close.index[-1] == data["QLD"].index[-1]
    assert close.at[missing, "QLD"] == data["QLD"].at[prior, "Close"]
    assert high.at[missing, "QLD"] == data["QLD"].at[prior, "High"]
    assert not close.isna().any().any()


def test_shared_helpers_reject_missing_empty_and_short_inputs(modules):
    vt = modules("backtest_voltarget")
    with pytest.raises(ValueError, match="Missing or empty ETF data: QLD"):
        vt.require_symbols({"SPY": bars()}, ["QLD"])
    with pytest.raises(ValueError, match="Missing or empty"):
        vt.require_symbols({"QLD": bars(0)}, ["QLD"])
    with pytest.raises(ValueError, match="At least one ETF"):
        vt.panel({}, [])
    with pytest.raises(ValueError, match="Insufficient common"):
        vt.panel({"SPY": bars(261)}, ["SPY"])
    with pytest.raises(ValueError, match="At least two evaluation"):
        vt.stats(pd.Series([0.0]))


def test_genport_vol_build_multi_bandwidth_and_weights(modules, data):
    gv = modules("backtest_genport_vol")
    port, w2, w1 = gv.build(data, 2.2, 4.0, 15.0, ma=200, entry_dd=3.0)
    assert_series_finite(port, data["QLD"].index[gv.WARMUP:])
    for weight in (w2, w1):
        assert_series_finite(weight, data["QLD"].index)
        assert set(weight.unique()) <= {0.0, 1.0}
        assert weight.iloc[0] == 0
    assert ((w2 + w1) <= 1).all()
    assert (w2 + w1).max() == 1, "Fixture must exercise offense, not only defense"
    pd.testing.assert_series_equal(gv.bandwidth(data["QLD"].Close), data["QLD"].Close.pct_change().rolling(20).std() * 100)
    pd.testing.assert_index_equal(gv.stats(port)["curve"].index, port.index)
    multi = gv.multi(data, ["QLD", "USD"], 2.2, 4.0, 15.0)
    assert_series_finite(multi, port.index)
    with pytest.raises(ValueError, match="At least one traded ETF"):
        gv.multi(data, [], 2.2, 4.0, 15.0)


@pytest.mark.parametrize("scorer,weekly", [("adm", False), ("vaa", True), ("12-1", False)])
def test_momentum_actual_api_and_future_causality(modules, data, scorer, weekly):
    mom = modules("backtest_momentum_v2")
    strategy = mom.Mom("synthetic", ["QLD", "SPY", "SPY"], ["IEF", "UUP"],
                       scorer=scorer, top=1, canary=False, trail=12.0,
                       ma_gate=200, re_entry=3.0, weekly=weekly)
    result = mom.run(strategy, data)
    assert result is not None
    assert_series_finite(result["curve"], data["SPY"].index)
    assert all(holding == "CASH" for _, holding in result["log"][:mom.WARMUP + 1])
    assert any(holding != "CASH" for _, holding in result["log"][mom.WARMUP + 1:])
    changed = {t: f.copy(deep=True) for t, f in data.items()}
    changed["QLD"].loc[changed["QLD"].index[480:], OHLC] *= 0.3
    other = mom.run(strategy, changed)
    assert other is not None
    pd.testing.assert_series_equal(result["curve"].iloc[:480], other["curve"].iloc[:480])
    assert result["log"][:480] == other["log"][:480]
    short = {t: f.iloc[:500] for t, f in data.items()}
    assert mom.run(strategy, short) is None


def test_momentum_scores_and_rebalance_calendar(modules):
    mom = modules("backtest_momentum_v2")
    returns = {n: pd.Series([i, -i], index=["SPY", "QQQ"], dtype=float)
               for i, n in enumerate((mom.M1, mom.M3, mom.M6, mom.M12), 1)}
    pd.testing.assert_series_equal(mom.score_adm(returns), (returns[21] + returns[63] + returns[126]) / 3)
    pd.testing.assert_series_equal(mom.score_vaa(returns), 12 * returns[21] + 4 * returns[63] + 2 * returns[126] + returns[252])
    pd.testing.assert_series_equal(mom.score_12_1(returns), returns[252] - returns[21])
    calendar = list(pd.to_datetime(["2020-01-30", "2020-01-31", "2020-02-03", "2020-02-07", "2020-02-10"]))
    assert mom.month_end_signals(calendar) == [calendar[1], calendar[-1]]
    assert mom.month_end_signals(calendar, weekly=True) == [calendar[1], calendar[3], calendar[-1]]


def test_sleeves_signal_mapping_shifted_accounting_and_causality(modules, data):
    sl = modules("backtest_sleeves")
    strategy = sl.Sleeve("synthetic", ["QLD"], ["IEF", "UUP"],
                         ma=200, trail=12.0, entry_dd=3.0, mom=60, sig_of={"QLD": "QQQ"})
    assert strategy.tickers == ["IEF", "QLD", "QQQ", "UUP"]
    result = sl.run(strategy, data)
    assert result is not None
    position = sl.sleeve_position(data["QQQ"].Close, data["QQQ"].High, 200, 12.0, 3.0, 60)
    held = position.shift(1).fillna(0.0)
    assert set(position.unique()) == {0.0, 1.0}
    close = pd.DataFrame({t: data[t].Close for t in strategy.tickers})
    ret = close.pct_change().fillna(0.0).clip(-0.5, 0.5)
    port = held * ret.QLD + (1 - held) * ret[["IEF", "UUP"]].mean(axis=1)
    port -= held.diff().abs().fillna(0.0) * sl.COST * 2
    pd.testing.assert_series_equal(result["curve"], (1 + port.iloc[sl.WARMUP:]).cumprod(), check_names=False, check_freq=False)
    changed = {t: f.copy(deep=True) for t, f in data.items()}
    changed["QQQ"].loc[changed["QQQ"].index[480:], OHLC] *= 0.4
    other = sl.run(strategy, changed)
    assert other is not None
    pd.testing.assert_series_equal(result["curve"].loc[:data["QQQ"].index[479]], other["curve"].loc[:data["QQQ"].index[479]])
    assert sl.run(strategy, {t: f.iloc[:500] for t, f in data.items()}) is None
    with pytest.raises(ValueError, match="QQQ"):
        sl.run(strategy, {t: f for t, f in data.items() if t != "QQQ"})


@pytest.mark.parametrize("api", ["hold", "vol_trend", "voltarget", "csv_exact"])
def test_unified_generators_metrics_and_causality(modules, data, api):
    unified = modules("eval_unified")

    def generate(source):
        if api == "hold":
            return unified.hold(source, "SPY")
        if api == "vol_trend":
            return unified.vol_trend(source, 2.2, 4.0, 15.0, ma=200, entry_dd=3.0)
        if api == "voltarget":
            return unified.voltarget(source, 15.0, trail=15.0, cap=2.0, ma=200, entry_dd=3.0)
        return unified.csv_exact(source, "QLD", 2.2, 4.0, trail=15.0, cash_yield=0.0)

    returns, exposure = generate(data)
    for series in (returns, exposure):
        assert_series_finite(series, data["SPY"].index)
    assert exposure.between(0, 1).all()
    if api == "hold":
        pd.testing.assert_series_equal(returns, data["SPY"].Close.pct_change().fillna(0.0), check_names=False, check_freq=False)
        assert (exposure == 1).all()
    else:
        assert exposure.iloc[0] == 0
        assert exposure.max() > 0
    start, end = returns.index[unified.WARMUP], returns.index[-1]
    metrics = unified.metrics(returns, start, end, exposure)
    assert {"cagr", "mdd", "sharpe", "calmar", "worst12", "expo", "from", "to"} == set(metrics)
    assert metrics["expo"] == pytest.approx(exposure.loc[start:end].mean() * 100)
    assert unified.metrics(returns.iloc[:249], returns.index[0], end) == {}
    changed = {t: f.copy(deep=True) for t, f in data.items()}
    for frame in changed.values():
        frame.loc[frame.index[480:], OHLC] *= 0.45
    future_r, future_e = generate(changed)
    pd.testing.assert_series_equal(returns.iloc[:480], future_r.iloc[:480])
    pd.testing.assert_series_equal(exposure.iloc[:480], future_e.iloc[:480])


def test_representative_unified_main_subprocess_with_local_fixtures(modules, data, tmp_path):
    folder = tmp_path / "bars"
    folder.mkdir()
    for ticker, frame in data.items():
        frame.to_csv(folder / f"{ticker}.csv")
    bars().to_csv(folder / "^VIX.csv")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"data_dir": "bars", "cache_dir": "cache",
                                  "start": "2020-01-01", "end": "2023-01-01"}), encoding="utf-8")
    result = guarded_process("runpy.run_module('eval_unified', run_name='__main__')", tmp_path, config=config)
    assert "Common-date USD research evaluation" in result.stdout
    assert "common sessions" in result.stdout
    assert "[BM] SPY gross hold" in result.stdout and "[BM] QQQ gross hold" in result.stdout
    assert "Not validation: execution/cost models differ" in result.stdout
    assert "Start-date sensitivity" in result.stdout
    assert not (tmp_path / "cache").exists()


def test_launcher_overrides_config_and_propagates_child_status(modules, monkeypatch, tmp_path, capsys):
    launcher = modules("run_research")
    config = tmp_path / "base.json"
    config.write_text(json.dumps({"benchmark": "SPY", "cost": 0.001, "data_dir": "bars"}), encoding="utf-8")
    captured = []

    def child(command, *, env):
        path = Path(env["GLOBAL_RESEARCH_CONFIG"])
        values = json.loads(path.read_text(encoding="utf-8"))
        captured.append((command, path, values))
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(launcher.subprocess, "run", child)
    status = launcher.main(["etf_proxy_history", "--config", str(config), "--benchmark", "QQQ",
                            "--cost-bps", "25", "--warmup", "280", "--min-daily-value", "100"])
    assert status == 7
    assert len(captured) == 1
    command, path, values = captured[0]
    assert command == [sys.executable, str(TOOLS / "etf_proxy_history.py")]
    assert values["benchmark"] == "QQQ"
    assert values["cost"] == 0.0025 and values["warmup"] == 280
    assert values["min_daily_value"] == 100
    assert Path(values["data_dir"]) == tmp_path / "bars"
    assert not path.exists(), "Temporary child config should be cleaned up"
    assert "Research contract:" in capsys.readouterr().out


def test_launcher_invalid_contract_never_starts_child(modules, monkeypatch):
    launcher = modules("run_research")
    monkeypatch.setattr(launcher.subprocess, "run", deny_network)
    with pytest.raises(ValueError, match="warmup must be at least 260"):
        launcher.main(["etf_proxy_history", "--warmup", "100"])