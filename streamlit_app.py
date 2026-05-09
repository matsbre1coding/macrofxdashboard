from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path
from typing import Dict, Iterable, Optional

import pandas as pd
import plotly.express as px
import streamlit as st


st.set_page_config(
    page_title="Macro FX Regime Dashboard",
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


STATUS_ORDER = {
    "Baseline candidate": 0,
    "Research watch only": 1,
    "Context watch": 2,
    "Research / no action": 3,
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


def inject_css() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.1rem;
            padding-bottom: 2rem;
        }
        div[data-testid="stMetricValue"] {
            font-size: 1.4rem;
        }
        .metric-card {
            border: 1px solid #d7dee8;
            border-radius: 8px;
            padding: 12px 14px;
            background: #ffffff;
            min-height: 104px;
        }
        .metric-card .label {
            color: #526070;
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0;
            margin-bottom: 6px;
        }
        .metric-card .value {
            color: #111827;
            font-size: 1.12rem;
            font-weight: 700;
            line-height: 1.22;
        }
        .metric-card .detail {
            color: #667085;
            font-size: 0.82rem;
            margin-top: 6px;
            line-height: 1.25;
        }
        .tone-good { border-left: 5px solid #168a4a; }
        .tone-warn { border-left: 5px solid #d99a00; }
        .tone-bad { border-left: 5px solid #c24131; }
        .tone-info { border-left: 5px solid #2563eb; }
        .small-caption {
            color: #667085;
            font-size: 0.84rem;
            margin-top: -0.35rem;
            margin-bottom: 0.6rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
def read_csv_bytes(data: bytes) -> pd.DataFrame:
    return normalize_frame(pd.read_csv(io.BytesIO(data)))


@st.cache_data(show_spinner=False)
def read_csv_path(path: str) -> pd.DataFrame:
    return normalize_frame(pd.read_csv(path))


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
        "Colab CSV oder ZIP",
        type=["csv", "zip"],
        accept_multiple_files=True,
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


def missing_files_panel(frames: Dict[str, pd.DataFrame]) -> None:
    missing = [filename for key, filename in CSV_FILES.items() if key not in frames]
    if not missing:
        return
    with st.sidebar.expander("Fehlende CSVs", expanded=False):
        st.dataframe(pd.DataFrame({"file": missing}), use_container_width=True, hide_index=True)


def sort_signal_board(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    out = frame.copy()
    out["_order"] = out.get("ensemble_action", "").map(STATUS_ORDER).fillna(99)
    if "ensemble_final_score" in out.columns:
        out = out.sort_values(["_order", "ensemble_final_score"], ascending=[True, False])
    else:
        out = out.sort_values("_order")
    return out.drop(columns=["_order"])


def percent_columns(frame: pd.DataFrame) -> Dict[str, str]:
    return {
        col: "{:.2%}"
        for col in frame.columns
        if any(token in col.lower() for token in ["return", "hit_rate", "probability", "drawdown", "active_period_rate"])
    }


def render_dataframe(frame: pd.DataFrame, height: int = 420) -> None:
    if frame.empty:
        st.info("Keine Daten geladen.")
        return
    st.dataframe(frame, use_container_width=True, height=height, hide_index=True)


def decision_board(frames: Dict[str, pd.DataFrame]) -> None:
    regime = get_frame(frames, "ensemble_regime")
    alignment = get_frame(frames, "ensemble_alignment")
    strategy = get_frame(frames, "ensemble_strategy")

    cols = st.columns(5)
    with cols[0]:
        metric_card(
            "Final regime",
            lookup(regime, "Final regime read"),
            lookup(regime, "Final regime read", "detail"),
            "warn",
        )
    with cols[1]:
        posture = lookup(regime, "Current posture")
        metric_card("Current posture", posture, lookup(regime, "Current posture", "detail"), "bad" if "No clean" in posture else "info")
    with cols[2]:
        gate = lookup(regime, "Macro trend gate")
        metric_card("Macro trend gate", gate, lookup(regime, "Macro trend gate", "detail"), "bad" if gate == "Closed" else "good")
    with cols[3]:
        metric_card("Policy watch", lookup(regime, "Policy watch candidates"), lookup(regime, "Policy watch candidates", "detail"), "warn")
    with cols[4]:
        metric_card("Data health", lookup(regime, "Stale CPI currencies"), lookup(regime, "Stale CPI currencies", "detail"), "warn")

    st.divider()
    left, right = st.columns([1.15, 1.0])
    with left:
        st.subheader("Semantic Regime Fit")
        if not alignment.empty and {"regime", "semantic_fit_score"}.issubset(alignment.columns):
            fig = px.bar(
                alignment.sort_values("semantic_fit_score"),
                x="semantic_fit_score",
                y="regime",
                color="semantic_fit_label" if "semantic_fit_label" in alignment.columns else None,
                orientation="h",
                range_x=[0, 100],
            )
            fig.update_layout(height=430, margin=dict(l=10, r=10, t=20, b=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            render_dataframe(alignment)
    with right:
        st.subheader("Strategy Mode")
        if not strategy.empty and {"mode", "conviction"}.issubset(strategy.columns):
            fig = px.bar(
                strategy.sort_values("conviction"),
                x="conviction",
                y="mode",
                color="status" if "status" in strategy.columns else None,
                orientation="h",
                range_x=[0, 100],
            )
            fig.update_layout(height=430, margin=dict(l=10, r=10, t=20, b=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            render_dataframe(strategy)

    st.subheader("Regime Decision Table")
    render_dataframe(regime, height=340)


def signal_board(frames: Dict[str, pd.DataFrame]) -> None:
    signals = sort_signal_board(get_frame(frames, "ensemble_signals"))
    if signals.empty:
        st.info("Keine Ensemble-Signaldatei geladen.")
        return

    actions = sorted(signals["ensemble_action"].dropna().unique()) if "ensemble_action" in signals.columns else []
    selected_actions = st.multiselect("Ensemble action", actions, default=actions)
    filtered = signals
    if selected_actions and "ensemble_action" in filtered.columns:
        filtered = filtered[filtered["ensemble_action"].isin(selected_actions)]

    left, right = st.columns([1.0, 2.0])
    with left:
        counts = filtered.get("ensemble_action", pd.Series(dtype=str)).value_counts().rename_axis("ensemble_action").reset_index(name="pairs")
        render_dataframe(counts, height=220)
    with right:
        if {"pair", "ensemble_final_score"}.issubset(filtered.columns):
            fig = px.bar(
                filtered.head(15).sort_values("ensemble_final_score"),
                x="ensemble_final_score",
                y="pair",
                color="ensemble_action" if "ensemble_action" in filtered.columns else None,
                text="expression" if "expression" in filtered.columns else None,
                orientation="h",
            )
            fig.update_layout(height=430, margin=dict(l=10, r=10, t=20, b=10))
            st.plotly_chart(fig, use_container_width=True)

    render_dataframe(filtered, height=520)


def regime_view(frames: Dict[str, pd.DataFrame]) -> None:
    latest = get_frame(frames, "calibrated_latest")
    comparison = get_frame(frames, "calibration_comparison")
    scores = get_frame(frames, "ensemble_scores")
    prob_driver = get_frame(frames, "prob_driver")

    left, right = st.columns([1.1, 0.9])
    with left:
        st.subheader("Raw vs Calibrated Regime Probability")
        if not latest.empty and {"regime", "raw_probability", "calibrated_probability"}.issubset(latest.columns):
            plot_df = latest.melt(
                id_vars=["regime"],
                value_vars=["raw_probability", "calibrated_probability"],
                var_name="type",
                value_name="probability",
            )
            fig = px.bar(plot_df, x="probability", y="regime", color="type", barmode="group", orientation="h")
            fig.update_layout(height=420, xaxis_tickformat=".0%", margin=dict(l=10, r=10, t=20, b=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            render_dataframe(latest)
    with right:
        st.subheader("Calibration Comparison")
        render_dataframe(comparison, height=420)

    left2, right2 = st.columns([0.9, 1.1])
    with left2:
        st.subheader("Latest Macro Scores")
        if not scores.empty and {"feature", "latest_score"}.issubset(scores.columns):
            fig = px.bar(scores, x="feature", y="latest_score", color="feature")
            fig.update_layout(height=360, showlegend=False, margin=dict(l=10, r=10, t=20, b=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            render_dataframe(scores)
    with right2:
        st.subheader("Probabilistic Driver Table")
        render_dataframe(prob_driver, height=360)


def backtest_view(frames: Dict[str, pd.DataFrame]) -> None:
    baseline = get_frame(frames, "final_baseline")
    split = get_frame(frames, "final_split")

    st.subheader("Final Baseline Decision")
    if not baseline.empty and {"strategy", "annualized_return", "oos_annualized_return"}.issubset(baseline.columns):
        top = baseline.head(20)
        plot_df = top.melt(
            id_vars=["strategy", "family", "horizon"] if {"family", "horizon"}.issubset(top.columns) else ["strategy"],
            value_vars=[c for c in ["annualized_return", "oos_annualized_return"] if c in top.columns],
            var_name="return_type",
            value_name="return",
        )
        fig = px.bar(plot_df, x="strategy", y="return", color="return_type", facet_col="horizon" if "horizon" in plot_df.columns else None)
        fig.update_layout(height=430, yaxis_tickformat=".1%", margin=dict(l=10, r=10, t=20, b=80))
        st.plotly_chart(fig, use_container_width=True)
    render_dataframe(baseline, height=430)

    st.subheader("Split Summary")
    render_dataframe(split, height=430)


def data_health_view(frames: Dict[str, pd.DataFrame]) -> None:
    permission = get_frame(frames, "currency_permission")
    freshness = get_frame(frames, "source_freshness")
    readiness = get_frame(frames, "source_readiness")

    left, right = st.columns([1.0, 1.0])
    with left:
        st.subheader("Currency Data Permission")
        render_dataframe(permission, height=420)
    with right:
        st.subheader("Source Readiness")
        render_dataframe(readiness, height=420)

    st.subheader("Source Freshness Audit")
    if not freshness.empty and {"currency", "field", "is_current_fresh"}.issubset(freshness.columns):
        fig = px.histogram(freshness, x="currency", color="is_current_fresh", facet_col="field")
        fig.update_layout(height=360, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig, use_container_width=True)
    render_dataframe(freshness, height=430)


def main() -> None:
    inject_css()
    st.sidebar.title("Macro FX")
    frames = load_frames()
    missing_files_panel(frames)

    st.title("Macro FX Regime Dashboard")
    st.markdown('<div class="small-caption">v1.3 ensemble decision layer</div>', unsafe_allow_html=True)

    if not frames:
        st.warning("Keine CSV-Exports gefunden.")
        st.stop()

    tab_decision, tab_signals, tab_regime, tab_backtest, tab_data = st.tabs(
        ["Decision Board", "Signal Board", "Regime View", "Backtest View", "Data Health"]
    )

    with tab_decision:
        decision_board(frames)
    with tab_signals:
        signal_board(frames)
    with tab_regime:
        regime_view(frames)
    with tab_backtest:
        backtest_view(frames)
    with tab_data:
        data_health_view(frames)


if __name__ == "__main__":
    main()
