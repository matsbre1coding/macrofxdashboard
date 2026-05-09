from __future__ import annotations

import io
import html
import os
import zipfile
from pathlib import Path
from typing import Dict

import pandas as pd
import plotly.express as px
import streamlit as st


APP_VERSION = "v1.5.1 Product UX"


st.set_page_config(
    page_title="Macro FX Cockpit",
    layout="wide",
    initial_sidebar_state="expanded",
)


CSV_FILES = {
    "ensemble_regime": "macro_fx_ensemble_regime_dashboard.csv",
    "ensemble_alignment": "macro_fx_ensemble_driver_alignment.csv",
    "ensemble_scores": "macro_fx_ensemble_latest_macro_scores.csv",
    "ensemble_strategy": "macro_fx_ensemble_strategy_dashboard.csv",
    "ensemble_signals": "macro_fx_ensemble_current_signal_board.csv",
    "calibrated_latest": "macro_fx_calibrated_prob_regime_latest.csv",
    "calibration_comparison": "macro_fx_probability_calibration_comparison.csv",
    "prob_driver": "macro_fx_prob_regime_driver_table.csv",
    "final_baseline": "macro_fx_final_baseline_decision.csv",
    "final_split": "macro_fx_final_baseline_split_summary.csv",
    "currency_permission": "macro_fx_currency_data_permission.csv",
    "source_freshness": "macro_fx_source_freshness_audit.csv",
    "source_readiness": "macro_fx_primary_source_readiness.csv",
}


NUMERIC_COLUMN_HINTS = [
    "score",
    "return",
    "hit_rate",
    "probability",
    "confidence",
    "conviction",
    "drawdown",
    "periods",
    "positions",
    "vol",
    "sharpe",
    "pairs",
]


ACTION_ORDER = {
    "Baseline candidate": 0,
    "Research watch only": 1,
    "Context watch": 2,
    "Research / no action": 3,
}


ACTION_LABELS = {
    "Baseline candidate": "Handelbar",
    "Research watch only": "Beobachten",
    "Context watch": "Nur Kontext",
    "Research / no action": "Ignorieren",
}


PERMISSION_LABELS = {
    "Allowed by baseline": "Baseline erlaubt",
    "Paper / tiny only": "Nur Paper / sehr klein",
    "Paper only": "Nur Paper",
    "No live baseline": "Kein Live-Signal",
}


FIT_LABELS = {
    "Strong semantic fit": "Passt stark",
    "Plausible semantic fit": "Plausibel",
    "Weak / mixed fit": "Gemischt",
    "Poor semantic fit": "Passt nicht",
}


STATUS_LABELS = {
    "Active": "Aktiv",
    "Research watch": "Beobachten",
    "Research": "Research",
    "Closed": "Geschlossen",
    "Off": "Aus",
    "Good": "Gut",
}


MODE_LABELS = {
    "Data Health": "Datenqualität",
    "Policy Divergence": "Zins-/Policy-Divergenz",
    "Mean Reversion / Exhaustion": "Überdehnung / Rücklauf",
    "Macro Trend Baseline": "Makro-Trend",
    "Defensive / Liquidity": "Defensive / Liquidität",
}


FIELD_LABELS = {
    "growth_score": "Wachstum",
    "inflation_score": "Inflation",
    "policy_score": "Zinsen/Policy",
    "risk_score": "Risiko",
    "commodity_score": "Rohstoffe",
    "usd_score": "USD",
}


HISTORY_LABELS = {
    "Robust OOS": "OOS robust",
    "Validation ok / test weak": "Validierung ok, jüngster Test schwach",
    "Recent-only watch": "Nur zuletzt auffällig",
    "Train-only risk": "Nur im Training gut",
    "Mixed / weak": "Gemischt / schwach",
    "": "n/a",
}


REASON_LABELS = {
    "OOS/watch support exists, but regime conflict or stale CPI blocks clean actionability.": "Historie ist interessant, aber Regime-Konflikt oder CPI-Lücke blockiert ein sauberes Live-Signal.",
    "Historical support exists, but current ensemble does not promote it.": "Historie ist teilweise interessant, aktuell aber nur Kontext.",
    "Fails at least one frozen baseline or ensemble gate.": "Fällt durch mindestens einen festen Filter.",
}


BAYES_LABELS = {
    "Soft conflict": "weicher Konflikt",
    "Conflict": "Konflikt",
    "Mixed / uncertain": "unsicher",
    "Soft confirmation": "leichte Bestätigung",
    "Confirmed": "bestätigt",
}


REGIME_EXPLANATIONS = {
    "Stagflation / Policy Squeeze": "Inflation/Rohstoffe sind stark, aber Wachstum und Risiko liefern kein klares Trend-Setup.",
    "Crisis / Liquidity Stress": "Wachstum und Risiko stehen unter Stress. Safe-haven- und Liquiditätslogik wird wichtiger.",
    "Deflationary Slowdown": "Wachstum und Inflation kühlen ab. Trendfolge kann brüchig werden.",
    "Reflation / Expansion": "Wachstum/Risiko verbessern sich. Trend- und Carry-Ideen werden interessanter.",
    "Goldilocks / Disinflationary Growth": "Wachstum ok, Inflation entspannt. Risikoassets haben oft Rückenwind.",
    "Neutral / Transition": "Kein klares Makrobild. Signalqualität muss besonders streng geprüft werden.",
}


def inject_css() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.0rem;
            padding-bottom: 2.0rem;
        }
        h1 {
            letter-spacing: 0;
        }
        .subtle {
            color: #94a3b8;
            font-size: 0.92rem;
            line-height: 1.35;
        }
        .hero {
            border: 1px solid rgba(148, 163, 184, 0.28);
            border-radius: 8px;
            padding: 18px 20px;
            background: rgba(15, 23, 42, 0.72);
            margin-bottom: 14px;
        }
        .hero .eyebrow {
            color: #94a3b8;
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0;
            margin-bottom: 8px;
        }
        .hero .headline {
            color: #f8fafc;
            font-size: 1.65rem;
            font-weight: 750;
            line-height: 1.18;
            margin-bottom: 8px;
        }
        .hero .copy {
            color: #cbd5e1;
            font-size: 0.98rem;
            line-height: 1.45;
        }
        .metric-card {
            border: 1px solid rgba(148, 163, 184, 0.28);
            border-radius: 8px;
            padding: 12px 14px;
            background: rgba(15, 23, 42, 0.64);
            min-height: 108px;
        }
        .metric-card .label {
            color: #94a3b8;
            font-size: 0.76rem;
            text-transform: uppercase;
            letter-spacing: 0;
            margin-bottom: 7px;
        }
        .metric-card .value {
            color: #f8fafc;
            font-size: 1.08rem;
            font-weight: 750;
            line-height: 1.24;
        }
        .metric-card .detail {
            color: #cbd5e1;
            font-size: 0.82rem;
            margin-top: 6px;
            line-height: 1.28;
        }
        .tone-good { border-left: 5px solid #168a4a; }
        .tone-watch { border-left: 5px solid #d99a00; }
        .tone-bad { border-left: 5px solid #c24131; }
        .tone-info { border-left: 5px solid #2563eb; }
        .section-note {
            color: #94a3b8;
            font-size: 0.9rem;
            margin-top: -0.25rem;
            margin-bottom: 0.9rem;
        }
        .overview-panel {
            border: 1px solid rgba(148, 163, 184, 0.24);
            border-radius: 10px;
            padding: 18px 20px;
            background: linear-gradient(135deg, rgba(15, 23, 42, 0.92), rgba(17, 24, 39, 0.74));
            min-height: 174px;
        }
        .overview-panel .headline {
            color: #f8fafc;
            font-size: 1.9rem;
            font-weight: 760;
            line-height: 1.12;
            margin-bottom: 8px;
        }
        .overview-panel .body {
            color: #cbd5e1;
            font-size: 0.98rem;
            line-height: 1.45;
            max-width: 980px;
        }
        .mini-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 10px;
            margin-top: 16px;
        }
        .mini-stat {
            border: 1px solid rgba(148, 163, 184, 0.18);
            border-radius: 8px;
            padding: 10px 12px;
            background: rgba(2, 6, 23, 0.28);
        }
        .mini-stat .k {
            color: #94a3b8;
            font-size: 0.72rem;
            text-transform: uppercase;
            margin-bottom: 4px;
        }
        .mini-stat .v {
            color: #f8fafc;
            font-size: 1.0rem;
            font-weight: 730;
        }
        .pair-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 12px;
            margin-top: 8px;
        }
        .pair-card {
            border: 1px solid rgba(148, 163, 184, 0.24);
            border-radius: 8px;
            padding: 13px 14px;
            background: rgba(15, 23, 42, 0.66);
            min-height: 142px;
        }
        .pair-card .pair {
            color: #f8fafc;
            font-size: 1.1rem;
            font-weight: 760;
            margin-bottom: 4px;
        }
        .pair-card .idea {
            color: #cbd5e1;
            font-size: 0.84rem;
            margin-bottom: 10px;
            min-height: 28px;
        }
        .pair-card .score {
            color: #f8fafc;
            font-size: 1.35rem;
            font-weight: 760;
            margin-bottom: 6px;
        }
        .pill {
            display: inline-block;
            border-radius: 999px;
            padding: 3px 8px;
            font-size: 0.73rem;
            font-weight: 700;
            margin-right: 5px;
            margin-top: 4px;
        }
        .pill-watch { background: rgba(245, 158, 11, 0.18); color: #fbbf24; }
        .pill-good { background: rgba(34, 197, 94, 0.16); color: #86efac; }
        .pill-bad { background: rgba(239, 68, 68, 0.16); color: #fca5a5; }
        .pill-info { background: rgba(96, 165, 250, 0.16); color: #93c5fd; }
        .currency-strip {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 10px;
            margin-top: 8px;
        }
        .currency-card {
            border: 1px solid rgba(148, 163, 184, 0.22);
            border-radius: 8px;
            padding: 12px;
            background: rgba(15, 23, 42, 0.58);
        }
        .currency-card .ccy {
            color: #f8fafc;
            font-weight: 760;
            font-size: 1.08rem;
        }
        .currency-card .line {
            color: #94a3b8;
            font-size: 0.8rem;
            margin-top: 4px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def parse_numberish(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return series
    text = series.astype(str).str.strip()
    has_percent = text.str.contains("%", na=False).any()
    cleaned = text.str.replace("%", "", regex=False).str.replace(",", "", regex=False)
    numeric = pd.to_numeric(cleaned, errors="coerce")
    if numeric.notna().mean() < 0.70:
        return series
    if has_percent:
        numeric = numeric / 100.0
    return numeric


def normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for column in out.columns:
        lower = str(column).lower()
        if any(hint in lower for hint in NUMERIC_COLUMN_HINTS):
            out[column] = parse_numberish(out[column])
    return out


@st.cache_data(show_spinner=False)
def read_csv_bytes(data: bytes) -> pd.DataFrame:
    return normalize_frame(pd.read_csv(io.BytesIO(data)))


@st.cache_data(show_spinner=False)
def read_csv_path(path: str) -> pd.DataFrame:
    return normalize_frame(pd.read_csv(path))


def discover_local_csvs(data_dir: Path) -> Dict[str, Path]:
    search_dirs = [data_dir, Path.cwd() / "data", Path.cwd()]
    found: Dict[str, Path] = {}
    for folder in search_dirs:
        if not folder.exists():
            continue
        for key, filename in CSV_FILES.items():
            candidate = folder / filename
            if candidate.exists() and key not in found:
                found[key] = candidate
    return found


def parse_uploaded_files() -> Dict[str, pd.DataFrame]:
    uploads = st.sidebar.file_uploader(
        "Colab-ZIP hochladen",
        type=["csv", "zip"],
        accept_multiple_files=True,
        help="Nimm die ZIP-Datei aus dem letzten Colab-Abschnitt Web-App ZIP Export.",
    )
    frames: Dict[str, pd.DataFrame] = {}
    if not uploads:
        return frames

    filename_to_key = {filename: key for key, filename in CSV_FILES.items()}
    for upload in uploads:
        payload = upload.getvalue()
        name = upload.name
        if name.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(payload)) as zf:
                for member in zf.namelist():
                    base = Path(member).name
                    key = filename_to_key.get(base)
                    if key:
                        frames[key] = read_csv_bytes(zf.read(member))
        else:
            key = filename_to_key.get(Path(name).name)
            if key:
                frames[key] = read_csv_bytes(payload)
    return frames


def load_frames() -> Dict[str, pd.DataFrame]:
    data_dir = Path(os.getenv("MACRO_FX_DATA_DIR", "data"))
    local_paths = discover_local_csvs(data_dir)
    frames = {key: read_csv_path(str(path)) for key, path in local_paths.items()}
    frames.update(parse_uploaded_files())
    return frames


def get_frame(frames: Dict[str, pd.DataFrame], key: str) -> pd.DataFrame:
    return frames.get(key, pd.DataFrame()).copy()


def lookup(frame: pd.DataFrame, item: str, column: str = "value", default: str = "n/a") -> str:
    if frame.empty or "item" not in frame.columns or column not in frame.columns:
        return default
    row = frame.loc[frame["item"].astype(str).eq(item)]
    if row.empty:
        return default
    value = row.iloc[0][column]
    return default if pd.isna(value) else str(value)


def friendly_action(value: str) -> str:
    return ACTION_LABELS.get(str(value), str(value))


def friendly_permission(value: str) -> str:
    return PERMISSION_LABELS.get(str(value), str(value))


def friendly_fit(value: str) -> str:
    return FIT_LABELS.get(str(value), str(value))


def friendly_status(value: str) -> str:
    return STATUS_LABELS.get(str(value), str(value))


def friendly_mode(value: str) -> str:
    return MODE_LABELS.get(str(value), str(value))


def friendly_history(value: str) -> str:
    return HISTORY_LABELS.get(str(value), str(value))


def friendly_reason(value: str) -> str:
    return REASON_LABELS.get(str(value), str(value))


def friendly_bayes(value: str) -> str:
    return BAYES_LABELS.get(str(value), str(value))


def metric_card(label: str, value: str, detail: str = "", tone: str = "info") -> None:
    st.markdown(
        f"""
        <div class="metric-card tone-{tone}">
            <div class="label">{label}</div>
            <div class="value">{value}</div>
            <div class="detail">{detail}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def hero_card(title: str, text: str, eyebrow: str = "Overview") -> None:
    st.markdown(
        f"""
        <div class="hero">
            <div class="eyebrow">{eyebrow}</div>
            <div class="headline">{title}</div>
            <div class="copy">{text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_dataframe(frame: pd.DataFrame, height: int = 420) -> None:
    if frame.empty:
        st.info("Keine Daten geladen.")
        return
    st.dataframe(frame, use_container_width=True, height=height, hide_index=True)


def missing_files_panel(frames: Dict[str, pd.DataFrame]) -> None:
    missing = [filename for key, filename in CSV_FILES.items() if key not in frames]
    if not missing:
        return
    with st.sidebar.expander("Fehlende Dateien", expanded=False):
        st.dataframe(pd.DataFrame({"Datei": missing}), use_container_width=True, hide_index=True)


def safe_text(value: object, default: str = "n/a") -> str:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except TypeError:
        pass
    return str(value)


def esc(value: object, default: str = "n/a") -> str:
    return html.escape(safe_text(value, default))


def frame_col(frame: pd.DataFrame, column: str, default: object = "") -> pd.Series:
    if column in frame.columns:
        return frame[column]
    return pd.Series(default, index=frame.index)


def to_float(value: object, default: float = 0.0) -> float:
    try:
        parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
        if pd.isna(parsed):
            return default
        return float(parsed)
    except Exception:
        return default


def to_bool_series(series: pd.Series) -> pd.Series:
    if series.empty:
        return series.astype(bool)
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    text = series.astype(str).str.strip().str.lower()
    return text.isin(["true", "1", "yes", "y", "ja"])


def sort_signal_board(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    out = frame.copy()
    out["_order"] = frame_col(out, "ensemble_action").map(ACTION_ORDER).fillna(99)
    if "ensemble_final_score" in out.columns:
        out = out.sort_values(["_order", "ensemble_final_score"], ascending=[True, False])
    else:
        out = out.sort_values("_order")
    return out.drop(columns=["_order"])


def action_tone(action: str) -> str:
    label = friendly_action(action)
    if label == "Beobachten":
        return "watch"
    if label == "Ignorieren":
        return "bad"
    if label == "Handelbar":
        return "good"
    return "info"


def readable_posture(value: str) -> str:
    if "No clean" in str(value):
        return "No clean live signal"
    return safe_text(value)


def overview_reason(regime: str, posture: str, gate: str, stale: str, prob_top: str, bayes_read: str) -> str:
    regime_text = REGIME_EXPLANATIONS.get(regime, "Die Marktphase wird aus Wachstum, Inflation, Zinsen, Risiko, Rohstoffen und USD-Druck abgeleitet.")
    gate_text = "closed" if gate == "Closed" else safe_text(gate)
    model_note = ""
    if prob_top not in ["", "n/a", regime]:
        model_note = (
            f" Markov/Bayes gives a second-opinion warning for {prob_top}, "
            f"but the driver check is {friendly_bayes(bayes_read)}."
        )
    if "No clean" in str(posture):
        return f"{regime_text} Trend gate is {gate_text}; stale CPI blocks clean real-rate use for {stale}.{model_note}"
    return f"{regime_text} Current posture: {posture}.{model_note}"


def clean_currency_count(permission: pd.DataFrame) -> tuple[int, int]:
    if permission.empty or "currency" not in permission.columns:
        return 0, 0
    total = permission["currency"].nunique()
    if "can_use_real_rate" in permission.columns:
        clean = int(to_bool_series(permission["can_use_real_rate"]).sum())
    elif "data_quality" in permission.columns:
        clean = int(permission["data_quality"].astype(str).eq("Good").sum())
    else:
        clean = 0
    return clean, total


def build_currency_strength(signals: pd.DataFrame, permission: pd.DataFrame) -> pd.DataFrame:
    currencies = set()
    for column in ["long_currency", "short_currency", "base_currency", "quote_currency"]:
        if column in signals.columns:
            currencies.update(signals[column].dropna().astype(str).str.upper().tolist())
    if "currency" in permission.columns:
        currencies.update(permission["currency"].dropna().astype(str).str.upper().tolist())
    if not currencies:
        currencies = {"USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD"}

    rows = {currency: {"currency": currency, "strength": 0.0, "ideas": 0} for currency in sorted(currencies)}
    for _, row in signals.iterrows():
        long_ccy = safe_text(row.get("long_currency", "")).upper()
        short_ccy = safe_text(row.get("short_currency", "")).upper()
        if not long_ccy or not short_ccy or long_ccy == "N/A" or short_ccy == "N/A":
            continue
        score = abs(to_float(row.get("abs_score", row.get("bias_score", 0.0))))
        action = safe_text(row.get("ensemble_action", ""))
        weight = {"Research watch only": 1.0, "Context watch": 0.65, "Research / no action": 0.25}.get(action, 0.55)
        contribution = score * weight
        rows.setdefault(long_ccy, {"currency": long_ccy, "strength": 0.0, "ideas": 0})
        rows.setdefault(short_ccy, {"currency": short_ccy, "strength": 0.0, "ideas": 0})
        rows[long_ccy]["strength"] += contribution
        rows[short_ccy]["strength"] -= contribution
        rows[long_ccy]["ideas"] += 1
        rows[short_ccy]["ideas"] += 1

    strength = pd.DataFrame(rows.values())
    if not permission.empty and "currency" in permission.columns:
        meta_cols = [col for col in ["currency", "data_quality", "permission", "policy_mode", "can_use_real_rate", "can_use_rates_only"] if col in permission.columns]
        meta = permission[meta_cols].copy()
        meta["currency"] = meta["currency"].astype(str).str.upper()
        strength = strength.merge(meta.drop_duplicates("currency"), on="currency", how="left")
    strength["strength"] = pd.to_numeric(strength["strength"], errors="coerce").fillna(0.0).round(2)
    strength["read"] = strength["strength"].apply(lambda x: "Strong" if x > 0.25 else ("Weak" if x < -0.25 else "Neutral"))
    return strength.sort_values("strength", ascending=False)


def build_pair_matrix(signals: pd.DataFrame, currencies: list[str]) -> pd.DataFrame:
    matrix = pd.DataFrame(0.0, index=currencies, columns=currencies)
    if signals.empty:
        return matrix
    for _, row in signals.iterrows():
        long_ccy = safe_text(row.get("long_currency", "")).upper()
        short_ccy = safe_text(row.get("short_currency", "")).upper()
        if long_ccy not in matrix.index or short_ccy not in matrix.columns:
            continue
        score = abs(to_float(row.get("abs_score", row.get("bias_score", 0.0))))
        if abs(score) >= abs(matrix.loc[long_ccy, short_ccy]):
            matrix.loc[long_ccy, short_ccy] = score
            matrix.loc[short_ccy, long_ccy] = -score
    return matrix.round(2)


def simplified_signals(signals: pd.DataFrame) -> pd.DataFrame:
    if signals.empty:
        return signals
    out = signals.copy()
    out["Status"] = frame_col(out, "ensemble_action").astype(str).map(friendly_action)
    out["Use"] = frame_col(out, "position_permission").astype(str).map(friendly_permission)
    out["Idea"] = frame_col(out, "expression")
    rates_history = frame_col(out, "rates_oos_label").astype(str).map(friendly_history)
    real_history = frame_col(out, "cpi_oos_label").astype(str).map(friendly_history)
    out["History"] = "Rates: " + rates_history + " | Real-rate: " + real_history
    out["Why"] = frame_col(out, "ensemble_reason").astype(str).map(friendly_reason)
    out["Score"] = pd.to_numeric(frame_col(out, "ensemble_final_score", 0.0), errors="coerce").round(2)
    cols = ["pair", "Idea", "Status", "Use", "Score", "History", "Why"]
    cols = [col for col in cols if col in out.columns]
    return out[cols].rename(columns={"pair": "Pair"})


def render_overview_panel(regime: pd.DataFrame, permission: pd.DataFrame) -> None:
    final_regime = lookup(regime, "Final regime read")
    posture = lookup(regime, "Current posture")
    gate = lookup(regime, "Macro trend gate")
    stale = lookup(regime, "Stale CPI currencies")
    confidence = lookup(regime, "Final regime confidence")
    prob_top = lookup(regime, "Probabilistic top regime")
    bayes_read = lookup(regime, "Bayesian read")
    clean, total = clean_currency_count(permission)
    headline = readable_posture(posture)
    body = overview_reason(final_regime, posture, gate, stale, prob_top, bayes_read)
    st.markdown(
        f"""
        <div class="overview-panel">
            <div class="headline">{esc(headline)}</div>
            <div class="body">{esc(body)}</div>
            <div class="mini-grid">
                <div class="mini-stat"><div class="k">Macro Regime</div><div class="v">{esc(final_regime)}</div></div>
                <div class="mini-stat"><div class="k">Confidence</div><div class="v">{esc(confidence)}/100</div></div>
                <div class="mini-stat"><div class="k">Clean Currencies</div><div class="v">{clean}/{total}</div></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_pair_cards(signals: pd.DataFrame, limit: int = 4) -> None:
    if signals.empty:
        st.info("No pair ideas loaded.")
        return
    top = sort_signal_board(signals).head(limit)
    cards = []
    for _, row in top.iterrows():
        pair = row.get("pair", "n/a")
        idea = row.get("expression", "n/a")
        score = to_float(row.get("ensemble_final_score", row.get("abs_score", 0.0)))
        status = friendly_action(safe_text(row.get("ensemble_action", "")))
        use = friendly_permission(safe_text(row.get("position_permission", "")))
        tone = action_tone(safe_text(row.get("ensemble_action", "")))
        cards.append(
            f"""
            <div class="pair-card">
                <div class="pair">{esc(pair)}</div>
                <div class="idea">{esc(idea)}</div>
                <div class="score">{score:.2f}</div>
                <span class="pill pill-{tone}">{esc(status)}</span>
                <span class="pill pill-info">{esc(use)}</span>
            </div>
            """
        )
    st.markdown(f'<div class="pair-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def overview_view(frames: Dict[str, pd.DataFrame]) -> None:
    regime = get_frame(frames, "ensemble_regime")
    signals = sort_signal_board(get_frame(frames, "ensemble_signals"))
    permission = get_frame(frames, "currency_permission")
    calibrated = get_frame(frames, "calibrated_latest")

    render_overview_panel(regime, permission)
    st.divider()

    strength = build_currency_strength(signals, permission)
    currencies = strength["currency"].tolist()
    matrix = build_pair_matrix(signals, currencies)

    left, right = st.columns([0.95, 1.05])
    with left:
        st.subheader("Currency Strength")
        st.markdown('<div class="section-note">Relative Stärke aus aktuellen Macro-/Policy-Pair-Scores aggregiert. Grüne Währungen werden bevorzugt, rote eher gemieden.</div>', unsafe_allow_html=True)
        plot_df = strength.copy()
        fig = px.bar(
            plot_df.sort_values("strength"),
            x="strength",
            y="currency",
            color="read",
            color_discrete_map={"Strong": "#22c55e", "Neutral": "#60a5fa", "Weak": "#ef4444"},
            orientation="h",
            hover_data=[col for col in ["data_quality", "permission", "ideas"] if col in plot_df.columns],
            labels={"strength": "Relative strength", "currency": "Currency"},
        )
        fig.update_layout(height=440, margin=dict(l=10, r=10, t=10, b=10), legend_title_text="")
        st.plotly_chart(fig, use_container_width=True)

    with right:
        st.subheader("Relative FX Bias")
        st.markdown('<div class="section-note">Row currency stronger vs column currency when the cell is green.</div>', unsafe_allow_html=True)
        fig = px.imshow(
            matrix,
            color_continuous_scale="RdYlGn",
            color_continuous_midpoint=0,
            aspect="auto",
            labels=dict(x="Against", y="Currency", color="Bias"),
        )
        fig.update_layout(height=440, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

    bottom_left, bottom_right = st.columns([0.86, 1.14])
    with bottom_left:
        st.subheader("Regime Confidence")
        if not calibrated.empty and {"regime", "calibrated_probability"}.issubset(calibrated.columns):
            plot_df = calibrated.copy().sort_values("calibrated_probability", ascending=True)
            fig = px.bar(
                plot_df,
                x="calibrated_probability",
                y="regime",
                orientation="h",
                color="is_scorecard_regime" if "is_scorecard_regime" in plot_df.columns else None,
                color_discrete_map={True: "#22c55e", False: "#60a5fa"},
                labels={"calibrated_probability": "Probability", "regime": "Regime"},
            )
            fig.update_layout(height=320, xaxis_tickformat=".0%", margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No calibrated regime probabilities loaded.")
    with bottom_right:
        st.subheader("Top Pair Ideas")
        st.markdown('<div class="section-note">Cards show research priority, not an automatic trade signal.</div>', unsafe_allow_html=True)
        render_pair_cards(signals, limit=4)

    with st.expander("Raw overview details"):
        render_dataframe(regime, height=260)


def currencies_view(frames: Dict[str, pd.DataFrame]) -> None:
    signals = sort_signal_board(get_frame(frames, "ensemble_signals"))
    permission = get_frame(frames, "currency_permission")
    strength = build_currency_strength(signals, permission)

    st.subheader("Currencies")
    st.markdown('<div class="section-note">Which currencies currently look strong, weak, clean or data-limited.</div>', unsafe_allow_html=True)

    if not strength.empty:
        fig = px.bar(
            strength.sort_values("strength"),
            x="strength",
            y="currency",
            color="read",
            color_discrete_map={"Strong": "#22c55e", "Neutral": "#60a5fa", "Weak": "#ef4444"},
            orientation="h",
            hover_data=[col for col in ["data_quality", "policy_mode", "ideas"] if col in strength.columns],
            labels={"strength": "Relative strength", "currency": "Currency"},
        )
        fig.update_layout(height=460, margin=dict(l=10, r=10, t=10, b=10), legend_title_text="")
        st.plotly_chart(fig, use_container_width=True)

    cards = []
    for _, row in strength.iterrows():
        quality = safe_text(row.get("data_quality", "n/a"))
        tone = "good" if quality == "Good" else ("watch" if "stale" in quality.lower() or "rates" in quality.lower() else "info")
        cards.append(
            f"""
            <div class="currency-card">
                <div class="ccy">{esc(row.get("currency"))} · {row.get("strength", 0):.2f}</div>
                <div class="line">Read: {esc(row.get("read"))}</div>
                <div class="line">Data: <span class="pill pill-{tone}">{esc(quality)}</span></div>
            </div>
            """
        )
    st.markdown(f'<div class="currency-strip">{"".join(cards)}</div>', unsafe_allow_html=True)

    with st.expander("Currency data details"):
        render_dataframe(permission, height=420)


def pairs_view(frames: Dict[str, pd.DataFrame]) -> None:
    signals = sort_signal_board(get_frame(frames, "ensemble_signals"))
    if signals.empty:
        st.info("No pair data loaded.")
        return

    st.subheader("Pairs")
    st.markdown('<div class="section-note">Macro-derived pair ideas ranked by current score and filtered by data quality and historical checks.</div>', unsafe_allow_html=True)

    filter_choice = st.radio(
        "View",
        ["All", "Watch only", "Context only", "Blocked"],
        horizontal=True,
        label_visibility="collapsed",
    )
    filtered = signals.copy()
    if filter_choice == "Watch only" and "ensemble_action" in filtered.columns:
        filtered = filtered[filtered["ensemble_action"].eq("Research watch only")]
    elif filter_choice == "Context only" and "ensemble_action" in filtered.columns:
        filtered = filtered[filtered["ensemble_action"].eq("Context watch")]
    elif filter_choice == "Blocked" and "ensemble_action" in filtered.columns:
        filtered = filtered[filtered["ensemble_action"].eq("Research / no action")]

    top = filtered.head(14).copy()
    top["Status"] = frame_col(top, "ensemble_action").astype(str).map(friendly_action)
    if {"pair", "ensemble_final_score"}.issubset(top.columns):
        fig = px.bar(
            top.sort_values("ensemble_final_score"),
            x="ensemble_final_score",
            y="pair",
            color="Status",
            orientation="h",
            hover_data=[col for col in ["expression", "position_permission", "rates_oos_label", "cpi_oos_label"] if col in top.columns],
            labels={"ensemble_final_score": "Current score", "pair": "Pair"},
        )
        fig.update_layout(height=470, margin=dict(l=10, r=10, t=10, b=10), legend_title_text="")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Top Cards")
    render_pair_cards(filtered, limit=4)

    with st.expander("Pair details"):
        render_dataframe(simplified_signals(filtered), height=430)

    with st.expander("Raw pair export"):
        render_dataframe(filtered, height=520)


def regime_view(frames: Dict[str, pd.DataFrame]) -> None:
    regime = get_frame(frames, "ensemble_regime")
    alignment = get_frame(frames, "ensemble_alignment")
    scores = get_frame(frames, "ensemble_scores")
    calibrated = get_frame(frames, "calibrated_latest")
    prob_driver = get_frame(frames, "prob_driver")

    st.subheader("Regime")
    st.markdown('<div class="section-note">Scorecard is the primary regime. Markov/Bayesian acts as second-opinion confidence and warning layer.</div>', unsafe_allow_html=True)

    final_regime = lookup(regime, "Final regime read")
    prob_top = lookup(regime, "Probabilistic top regime")
    bayes_read = lookup(regime, "Bayesian read")
    confidence = lookup(regime, "Final regime confidence")
    cols = st.columns(3)
    with cols[0]:
        metric_card("Scorecard regime", final_regime, f"Confidence {confidence}/100", "good")
    with cols[1]:
        metric_card("Markov/Bayes view", prob_top, f"Second opinion: {friendly_bayes(bayes_read)}", "watch")
    with cols[2]:
        metric_card("Final use", "Confidence layer", "Does not override the baseline unless drivers confirm.", "info")

    left, right = st.columns([1.0, 1.0])
    with left:
        st.markdown("#### Regime probabilities")
        if not calibrated.empty and {"regime", "calibrated_probability"}.issubset(calibrated.columns):
            plot_df = calibrated.copy().sort_values("calibrated_probability")
            fig = px.bar(
                plot_df,
                x="calibrated_probability",
                y="regime",
                orientation="h",
                color="is_scorecard_regime" if "is_scorecard_regime" in plot_df.columns else None,
                color_discrete_map={True: "#22c55e", False: "#60a5fa"},
                labels={"calibrated_probability": "Probability", "regime": "Regime"},
            )
            fig.update_layout(height=420, xaxis_tickformat=".0%", margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            render_dataframe(calibrated, height=320)
    with right:
        st.markdown("#### Macro drivers")
        if not scores.empty and {"feature", "latest_score"}.issubset(scores.columns):
            plot_df = scores.copy()
            plot_df["Driver"] = plot_df["feature"].map(FIELD_LABELS).fillna(plot_df["feature"])
            fig = px.bar(
                plot_df,
                x="Driver",
                y="latest_score",
                color="Driver",
                labels={"latest_score": "Score"},
            )
            fig.update_layout(height=420, showlegend=False, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            render_dataframe(scores, height=320)

    st.markdown("#### Regime fit")
    if not alignment.empty and {"regime", "semantic_fit_score"}.issubset(alignment.columns):
        plot_df = alignment.copy()
        plot_df["Fit"] = frame_col(plot_df, "semantic_fit_label").astype(str).map(friendly_fit)
        fig = px.bar(
            plot_df.sort_values("semantic_fit_score"),
            x="semantic_fit_score",
            y="regime",
            color="Fit",
            orientation="h",
            range_x=[0, 100],
            labels={"semantic_fit_score": "Fit", "regime": "Regime"},
        )
        fig.update_layout(height=360, margin=dict(l=10, r=10, t=10, b=10), legend_title_text="")
        st.plotly_chart(fig, use_container_width=True)

    with st.expander("Driver details"):
        render_dataframe(prob_driver, height=330)


def data_quality_view(frames: Dict[str, pd.DataFrame]) -> None:
    permission = get_frame(frames, "currency_permission")
    freshness = get_frame(frames, "source_freshness")
    readiness = get_frame(frames, "source_readiness")

    st.subheader("Data Quality")
    st.markdown('<div class="section-note">The dashboard uses the newest available observations. If data is stale, that currency is downgraded or blocked.</div>', unsafe_allow_html=True)

    clean, total = clean_currency_count(permission)
    stale_count = max(total - clean, 0)
    cols = st.columns(3)
    with cols[0]:
        metric_card("Clean real-rate currencies", f"{clean}/{total}", "Full policy stack allowed.", "good" if clean else "watch")
    with cols[1]:
        metric_card("Rates-only / limited", str(stale_count), "Usable as context, not clean real-rate signal.", "watch")
    with cols[2]:
        missing_keys = int(to_bool_series(readiness["api_key_required"]).sum()) if not readiness.empty and "api_key_required" in readiness.columns else 0
        metric_card("API/key dependent", str(missing_keys), "Future upgrades for cleaner data.", "info")

    st.markdown("#### Freshness by currency")
    if not freshness.empty and {"currency", "field", "is_current_fresh"}.issubset(freshness.columns):
        plot_df = freshness.copy()
        plot_df["Fresh"] = to_bool_series(plot_df["is_current_fresh"]).map({True: "Fresh", False: "Stale"})
        fig = px.histogram(
            plot_df,
            x="currency",
            color="Fresh",
            facet_col="field",
            color_discrete_map={"Fresh": "#22c55e", "Stale": "#ef4444"},
            labels={"currency": "Currency", "count": "Fields"},
        )
        fig.update_layout(height=360, margin=dict(l=10, r=10, t=30, b=10), legend_title_text="")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### What needs fixing")
    if not freshness.empty:
        needs = freshness.copy()
        if "is_current_fresh" in needs.columns:
            needs = needs[~to_bool_series(needs["is_current_fresh"])]
        show_cols = [col for col in ["currency", "field", "current_latest", "current_age_days", "primary_source", "access", "api_key_required", "priority", "notes"] if col in needs.columns]
        if show_cols:
            render_dataframe(needs[show_cols], height=260)
        else:
            st.success("No stale source rows found.")

    with st.expander("Source readiness details"):
        render_dataframe(readiness, height=440)
    with st.expander("Currency permission details"):
        render_dataframe(permission, height=340)


def main() -> None:
    inject_css()
    st.sidebar.title("Macro FX")
    st.sidebar.caption("Upload the ZIP exported by Colab v1.3.1.")
    frames = load_frames()
    missing_files_panel(frames)

    st.title("Macro FX Cockpit")
    st.markdown(
        f'<div class="subtle">{APP_VERSION} · Regime, currency strength, relative FX bias and data quality.</div>',
        unsafe_allow_html=True,
    )

    if not frames:
        st.warning("Upload the ZIP file from the final Colab export in the left sidebar.")
        st.stop()

    tab_overview, tab_currencies, tab_pairs, tab_regime, tab_data = st.tabs(
        ["Overview", "Currencies", "Pairs", "Regime", "Data Quality"]
    )

    with tab_overview:
        overview_view(frames)
    with tab_currencies:
        currencies_view(frames)
    with tab_pairs:
        pairs_view(frames)
    with tab_regime:
        regime_view(frames)
    with tab_data:
        data_quality_view(frames)


if __name__ == "__main__":
    main()
