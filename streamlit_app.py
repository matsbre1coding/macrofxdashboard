from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path
from typing import Dict

import pandas as pd
import plotly.express as px
import streamlit as st


APP_VERSION = "v1.4 UX"


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


FIELD_LABELS = {
    "growth_score": "Wachstum",
    "inflation_score": "Inflation",
    "policy_score": "Zinsen/Policy",
    "risk_score": "Risiko",
    "commodity_score": "Rohstoffe",
    "usd_score": "USD",
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


def hero_card(title: str, text: str, eyebrow: str = "Heute") -> None:
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


def signal_tone(posture: str) -> str:
    text = str(posture).lower()
    if "no clean" in text or "kein" in text:
        return "bad"
    if "watch" in text or "research" in text or "beobachten" in text:
        return "watch"
    return "good"


def sort_signal_board(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    out = frame.copy()
    out["_order"] = out.get("ensemble_action", "").map(ACTION_ORDER).fillna(99)
    if "ensemble_final_score" in out.columns:
        out = out.sort_values(["_order", "ensemble_final_score"], ascending=[True, False])
    else:
        out = out.sort_values("_order")
    return out.drop(columns=["_order"])


def simplified_signals(signals: pd.DataFrame) -> pd.DataFrame:
    if signals.empty:
        return signals
    out = signals.copy()
    out["Status"] = out.get("ensemble_action", "").map(friendly_action)
    out["Einsatz"] = out.get("position_permission", "").map(friendly_permission)
    out["Idee"] = out.get("expression", "")
    out["Historie"] = out.get("rates_oos_label", "").astype(str) + " / " + out.get("cpi_oos_label", "").astype(str)
    out["Hinweis"] = out.get("ensemble_reason", "")
    out["Score"] = pd.to_numeric(
        out.get("ensemble_final_score", pd.Series(index=out.index, dtype=float)),
        errors="coerce",
    ).round(2)
    cols = ["pair", "Idee", "Status", "Einsatz", "Score", "Historie", "Hinweis"]
    cols = [col for col in cols if col in out.columns]
    result = out[cols].rename(columns={"pair": "Pair"})
    return result


def explain_today(regime: str, posture: str, gate: str, stale: str) -> str:
    regime_text = REGIME_EXPLANATIONS.get(regime, "Das aktuelle Regime wird aus Wachstum, Inflation, Zinsen, Risiko, Rohstoffen und USD-Stärke abgeleitet.")
    if "No clean" in posture:
        return (
            f"{regime_text} Das Dashboard gibt deshalb aktuell kein sauberes Baseline-Signal frei. "
            f"Der Trend-Filter steht auf {gate}; Datenlücken gibt es bei {stale}."
        )
    return f"{regime_text} Der aktuelle Signalstatus lautet: {posture}."


def today_view(frames: Dict[str, pd.DataFrame]) -> None:
    regime = get_frame(frames, "ensemble_regime")
    alignment = get_frame(frames, "ensemble_alignment")
    strategy = get_frame(frames, "ensemble_strategy")
    signals = sort_signal_board(get_frame(frames, "ensemble_signals"))

    final_regime = lookup(regime, "Final regime read")
    posture = lookup(regime, "Current posture")
    gate = lookup(regime, "Macro trend gate")
    policy_watch = lookup(regime, "Policy watch candidates")
    stale = lookup(regime, "Stale CPI currencies")
    confidence = lookup(regime, "Final regime confidence")

    readable_posture = "Kein sauberes Signal" if "No clean" in posture else posture
    hero_card(
        readable_posture,
        explain_today(final_regime, posture, gate, stale),
        "Aktueller Markt-Check",
    )

    cols = st.columns(5)
    with cols[0]:
        metric_card("Marktphase", final_regime, f"Vertrauen: {confidence}/100", "watch")
    with cols[1]:
        metric_card("Signalstatus", readable_posture, lookup(regime, "Current posture", "detail"), signal_tone(posture))
    with cols[2]:
        gate_label = "Geschlossen" if gate == "Closed" else gate
        metric_card("Trend-Signal erlaubt?", gate_label, "Nur wenn der Regime-Filter offen ist.", "bad" if gate == "Closed" else "good")
    with cols[3]:
        metric_card("Watchlist", policy_watch, "Ideen zum Beobachten, nicht automatisch handeln.", "watch")
    with cols[4]:
        metric_card("Datenlücken", stale, "Diese Währungen sind noch nicht sauber genug für Real-Rate-Signale.", "watch")

    st.divider()
    left, right = st.columns([1.05, 1.0])
    with left:
        st.subheader("Passt die Marktphase zu den Daten?")
        st.markdown('<div class="section-note">Je höher der Wert, desto besser passt das Regime zu Growth, Inflation, Policy und Risk.</div>', unsafe_allow_html=True)
        if not alignment.empty and {"regime", "semantic_fit_score"}.issubset(alignment.columns):
            plot_df = alignment.copy()
            plot_df["Bewertung"] = plot_df.get("semantic_fit_label", "").map(friendly_fit)
            fig = px.bar(
                plot_df.sort_values("semantic_fit_score"),
                x="semantic_fit_score",
                y="regime",
                color="Bewertung",
                orientation="h",
                range_x=[0, 100],
                labels={"semantic_fit_score": "Passung", "regime": "Marktphase"},
            )
            fig.update_layout(height=390, margin=dict(l=10, r=10, t=10, b=10), legend_title_text="")
            st.plotly_chart(fig, use_container_width=True)
        else:
            render_dataframe(alignment)

    with right:
        st.subheader("Welche Modi sind aktiv?")
        st.markdown('<div class="section-note">Das ist die Betriebsart des Dashboards: handeln, beobachten, forschen oder Daten verbessern.</div>', unsafe_allow_html=True)
        if not strategy.empty and {"mode", "conviction"}.issubset(strategy.columns):
            plot_df = strategy.copy()
            plot_df["Status"] = plot_df.get("status", "").map(friendly_status)
            fig = px.bar(
                plot_df.sort_values("conviction"),
                x="conviction",
                y="mode",
                color="Status",
                orientation="h",
                range_x=[0, 100],
                labels={"conviction": "Relevanz", "mode": "Modus"},
            )
            fig.update_layout(height=390, margin=dict(l=10, r=10, t=10, b=10), legend_title_text="")
            st.plotly_chart(fig, use_container_width=True)
        else:
            render_dataframe(strategy)

    st.subheader("Top Watchlist")
    st.markdown('<div class="section-note">Das sind Beobachtungsideen. Wenn “Einsatz” nicht Baseline erlaubt sagt, ist es kein sauberes Live-Signal.</div>', unsafe_allow_html=True)
    simple = simplified_signals(signals).head(6)
    render_dataframe(simple, height=260)

    with st.expander("Technische Details anzeigen"):
        render_dataframe(regime, height=340)


def watchlist_view(frames: Dict[str, pd.DataFrame]) -> None:
    signals = sort_signal_board(get_frame(frames, "ensemble_signals"))
    if signals.empty:
        st.info("Keine Watchlist-Daten geladen.")
        return

    st.subheader("Watchlist")
    st.markdown('<div class="section-note">Hier siehst du Pair-Ideen nach Nutzungsstatus. Beobachten heisst nicht automatisch handeln.</div>', unsafe_allow_html=True)

    actions = sorted(signals["ensemble_action"].dropna().unique()) if "ensemble_action" in signals.columns else []
    readable_options = {friendly_action(action): action for action in actions}
    default_labels = [label for label in readable_options if label in ["Beobachten", "Nur Kontext"]]
    selected_labels = st.multiselect("Status", list(readable_options.keys()), default=default_labels or list(readable_options.keys()))
    selected_actions = [readable_options[label] for label in selected_labels]

    filtered = signals
    if selected_actions and "ensemble_action" in filtered.columns:
        filtered = filtered[filtered["ensemble_action"].isin(selected_actions)]

    left, right = st.columns([0.8, 1.4])
    with left:
        counts = (
            filtered.get("ensemble_action", pd.Series(dtype=str))
            .map(friendly_action)
            .value_counts()
            .rename_axis("Status")
            .reset_index(name="Paare")
        )
        render_dataframe(counts, height=190)
    with right:
        if {"pair", "ensemble_final_score"}.issubset(filtered.columns):
            plot_df = filtered.head(12).copy()
            plot_df["Status"] = plot_df.get("ensemble_action", "").map(friendly_action)
            fig = px.bar(
                plot_df.sort_values("ensemble_final_score"),
                x="ensemble_final_score",
                y="pair",
                color="Status",
                text="expression" if "expression" in plot_df.columns else None,
                orientation="h",
                labels={"ensemble_final_score": "Score", "pair": "Pair"},
            )
            fig.update_layout(height=390, margin=dict(l=10, r=10, t=10, b=10), legend_title_text="")
            st.plotly_chart(fig, use_container_width=True)

    simple = simplified_signals(filtered)
    render_dataframe(simple, height=420)

    with st.expander("Alle technischen Spalten anzeigen"):
        render_dataframe(filtered, height=520)


def market_phase_view(frames: Dict[str, pd.DataFrame]) -> None:
    latest = get_frame(frames, "calibrated_latest")
    comparison = get_frame(frames, "calibration_comparison")
    scores = get_frame(frames, "ensemble_scores")
    prob_driver = get_frame(frames, "prob_driver")

    st.subheader("Marktphase verstehen")
    st.markdown('<div class="section-note">Diese Seite erklaert, warum das Dashboard die aktuelle Marktphase akzeptiert oder verwirft.</div>', unsafe_allow_html=True)

    left, right = st.columns([1.0, 1.0])
    with left:
        st.markdown("#### Modell-Warnung vs geglättete Sicht")
        if not latest.empty and {"regime", "raw_probability", "calibrated_probability"}.issubset(latest.columns):
            plot_df = latest.melt(
                id_vars=["regime"],
                value_vars=["raw_probability", "calibrated_probability"],
                var_name="Sicht",
                value_name="Wahrscheinlichkeit",
            )
            plot_df["Sicht"] = plot_df["Sicht"].replace({"raw_probability": "Rohes Modell", "calibrated_probability": "Geglättet"})
            fig = px.bar(
                plot_df,
                x="Wahrscheinlichkeit",
                y="regime",
                color="Sicht",
                barmode="group",
                orientation="h",
                labels={"regime": "Marktphase"},
            )
            fig.update_layout(height=390, xaxis_tickformat=".0%", margin=dict(l=10, r=10, t=10, b=10), legend_title_text="")
            st.plotly_chart(fig, use_container_width=True)
        else:
            render_dataframe(latest)

    with right:
        st.markdown("#### Aktuelle Makro-Treiber")
        if not scores.empty and {"feature", "latest_score"}.issubset(scores.columns):
            plot_df = scores.copy()
            plot_df["Treiber"] = plot_df["feature"].map(FIELD_LABELS).fillna(plot_df["feature"])
            fig = px.bar(
                plot_df,
                x="Treiber",
                y="latest_score",
                color="Treiber",
                labels={"latest_score": "Score"},
            )
            fig.update_layout(height=390, showlegend=False, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            render_dataframe(scores)

    st.markdown("#### Warum sagt das Modell das?")
    driver = prob_driver.copy()
    if not driver.empty:
        driver = driver.rename(columns={
            "feature": "Treiber",
            "latest_score": "Aktueller Score",
            "top_state_mapped_regime": "Modell-Regime",
            "top_state_average": "Typischer Score im Modell-Regime",
            "gap_to_state_average": "Abweichung",
            "driver_read": "Lesart",
        })
        if "Treiber" in driver.columns:
            driver["Treiber"] = driver["Treiber"].map(FIELD_LABELS).fillna(driver["Treiber"])
    render_dataframe(driver, height=300)

    with st.expander("Rohdaten zum Modellvergleich anzeigen"):
        render_dataframe(comparison, height=240)


def history_view(frames: Dict[str, pd.DataFrame]) -> None:
    baseline = get_frame(frames, "final_baseline")
    split = get_frame(frames, "final_split")

    st.subheader("Historie & Vertrauen")
    st.markdown('<div class="section-note">Hier geht es um die Frage: Welche Strategie-Varianten waren historisch robust genug?</div>', unsafe_allow_html=True)

    if not baseline.empty and {"strategy", "annualized_return", "oos_annualized_return"}.issubset(baseline.columns):
        top = baseline.head(16).copy()
        plot_df = top.melt(
            id_vars=["strategy", "family", "horizon"] if {"family", "horizon"}.issubset(top.columns) else ["strategy"],
            value_vars=[c for c in ["annualized_return", "oos_annualized_return"] if c in top.columns],
            var_name="Zeitraum",
            value_name="Rendite",
        )
        plot_df["Zeitraum"] = plot_df["Zeitraum"].replace({"annualized_return": "Gesamt", "oos_annualized_return": "Out-of-sample"})
        fig = px.bar(
            plot_df,
            x="strategy",
            y="Rendite",
            color="Zeitraum",
            facet_col="horizon" if "horizon" in plot_df.columns else None,
            labels={"strategy": "Strategie"},
        )
        fig.update_layout(height=430, yaxis_tickformat=".1%", margin=dict(l=10, r=10, t=20, b=80), legend_title_text="")
        st.plotly_chart(fig, use_container_width=True)

    display_baseline = baseline.rename(columns={
        "family": "Familie",
        "strategy": "Strategie",
        "horizon": "Horizont",
        "annualized_return": "Rendite p.a.",
        "oos_annualized_return": "OOS Rendite p.a.",
        "sharpe_proxy": "Sharpe Proxy",
        "max_drawdown": "Max Drawdown",
        "baseline_decision": "Entscheidung",
        "decision_note": "Kommentar",
    })
    render_dataframe(display_baseline, height=430)

    with st.expander("Split-Auswertung anzeigen"):
        render_dataframe(split, height=430)


def data_quality_view(frames: Dict[str, pd.DataFrame]) -> None:
    permission = get_frame(frames, "currency_permission")
    freshness = get_frame(frames, "source_freshness")
    readiness = get_frame(frames, "source_readiness")

    st.subheader("Datenqualität")
    st.markdown('<div class="section-note">Diese Seite zeigt, welche Daten sauber genug sind und welche Signale deshalb blockiert werden.</div>', unsafe_allow_html=True)

    left, right = st.columns([1.0, 1.0])
    with left:
        st.markdown("#### Welche Währungen sind sauber?")
        display_permission = permission.rename(columns={
            "currency": "Währung",
            "rates_fresh": "Zinsen frisch",
            "cpi_fresh": "Inflation frisch",
            "data_quality": "Datenstatus",
            "permission": "Nutzung",
            "policy_mode": "Policy-Modus",
        })
        render_dataframe(display_permission, height=370)
    with right:
        st.markdown("#### Quellenstatus")
        display_readiness = readiness.rename(columns={
            "currency": "Währung",
            "field": "Datenfeld",
            "primary_source": "Quelle",
            "implementation_status": "Status",
            "readiness": "Bereit?",
            "notes": "Notiz",
        })
        render_dataframe(display_readiness, height=370)

    st.markdown("#### Frische der Daten")
    if not freshness.empty and {"currency", "field", "is_current_fresh"}.issubset(freshness.columns):
        plot_df = freshness.copy()
        plot_df["Daten frisch?"] = plot_df["is_current_fresh"].map({True: "Frisch", False: "Veraltet"}).fillna(plot_df["is_current_fresh"].astype(str))
        fig = px.histogram(
            plot_df,
            x="currency",
            color="Daten frisch?",
            facet_col="field",
            labels={"currency": "Währung", "count": "Anzahl"},
        )
        fig.update_layout(height=360, margin=dict(l=10, r=10, t=30, b=10), legend_title_text="")
        st.plotly_chart(fig, use_container_width=True)
    render_dataframe(freshness, height=430)


def main() -> None:
    inject_css()
    st.sidebar.title("Macro FX")
    st.sidebar.caption("1. Colab v1.3.1 ausführen. 2. ZIP hier hochladen.")
    frames = load_frames()
    missing_files_panel(frames)

    st.title("Macro FX Cockpit")
    st.markdown(
        f'<div class="subtle">{APP_VERSION} · Einfacher Überblick für Marktphase, Watchlist, Historie und Datenqualität.</div>',
        unsafe_allow_html=True,
    )

    if not frames:
        st.warning("Bitte lade links die ZIP-Datei aus Colab hoch.")
        st.stop()

    tab_today, tab_watchlist, tab_market, tab_history, tab_data = st.tabs(
        ["Heute", "Watchlist", "Marktphase", "Historie", "Datenqualität"]
    )

    with tab_today:
        today_view(frames)
    with tab_watchlist:
        watchlist_view(frames)
    with tab_market:
        market_phase_view(frames)
    with tab_history:
        history_view(frames)
    with tab_data:
        data_quality_view(frames)


if __name__ == "__main__":
    main()
