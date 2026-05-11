from __future__ import annotations

import io
import html
import json
import os
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Dict

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


APP_VERSION = "v1.8.1 Research Cockpit"


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


NARRATIVE_FILE_NAMES = {
    "narrative_monitor.csv",
    "macro_fx_public_narrative_monitor.csv",
    "narrative_monitor.json",
    "macro_fx_public_narrative_monitor.json",
}


NARRATIVE_COLUMNS = [
    "currency",
    "source_name",
    "source_type",
    "title",
    "url",
    "published_at",
    "summary",
    "sentiment",
    "confidence",
    "relevance",
    "themes",
    "supports",
    "risks",
    "reason",
]


FX_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD"}


CURRENCY_DETECTION_TERMS = {
    "USD": ["USD", "dollar", "US dollar", "U.S. dollar", "DXY", "Fed", "Federal Reserve", "FOMC", "Treasury yields", "Treasury yield", "Treasuries", "greenback"],
    "EUR": ["EUR", "euro", "ECB", "eurozone", "euro area"],
    "GBP": ["GBP", "sterling", "pound", "BoE", "UK"],
    "JPY": ["JPY", "yen", "BoJ", "Japan"],
    "CHF": ["CHF", "franc", "Swiss franc", "SNB", "Switzerland"],
    "CAD": ["CAD", "loonie", "Canadian dollar", "BoC", "Canada"],
    "AUD": ["AUD", "Aussie", "Australian dollar", "RBA", "Australia"],
    "NZD": ["NZD", "kiwi", "New Zealand dollar", "RBNZ", "New Zealand"],
}


NARRATIVE_SENTIMENT_SCORE = {"Bullish": 1.0, "Bearish": -1.0, "Neutral": 0.0, "Mixed": 0.0}


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


REGIME_EXPLANATIONS.update(
    {
        "Stagflation / Policy Squeeze": "Inflation and commodity pressure are elevated while growth and risk do not provide a clean trend setup.",
        "Crisis / Liquidity Stress": "Growth and risk can be under stress. Safe-haven and liquidity logic tends to matter more, but it still needs driver confirmation.",
        "Deflationary Slowdown": "Growth and inflation can cool together. Trend-following signals tend to become more fragile.",
        "Reflation / Expansion": "Growth and risk can improve. Trend and carry ideas can receive more support when data quality also passes.",
        "Goldilocks / Disinflationary Growth": "Growth can be acceptable while inflation pressure cools. Risk assets can receive a friendlier backdrop.",
        "Neutral / Transition": "No clean macro backdrop. Signal quality needs stricter confirmation.",
    }
)


BACKDROP_LABEL = "US/USD-led Global FX Backdrop"
BACKDROP_EXPLANATION = (
    "This regime is derived mainly from US macro data, US rates, risk markets, "
    "commodities and USD momentum. It is a global FX backdrop, not a country-by-country macro diagnosis."
)


REGIME_FX_IMPLICATIONS = {
    "Stagflation / Policy Squeeze": [
        "Commodity-linked currencies such as CAD and AUD can benefit if commodity strength persists.",
        "High-beta currencies such as AUD and NZD remain vulnerable if risk sentiment turns lower.",
        "USD can be mixed because inflation/policy support may conflict with risk and commodity dynamics.",
        "JPY and CHF usually need clearer risk-off confirmation.",
    ],
    "Crisis / Liquidity Stress": [
        "USD, JPY and CHF can receive support if risk-off pressure is confirmed by growth and risk drivers.",
        "High-beta and commodity-linked currencies can come under pressure if liquidity stress dominates.",
        "Carry and pro-risk FX ideas tend to need smaller sizing or stronger confirmation.",
    ],
    "Deflationary Slowdown": [
        "JPY and CHF can receive support if lower yields and weaker growth dominate the backdrop.",
        "Commodity-linked currencies can be pressured if demand expectations weaken.",
        "USD can be mixed depending on whether safe-haven demand or lower US yields dominate.",
    ],
    "Reflation / Expansion": [
        "High-beta and commodity-linked currencies can receive support when risk appetite confirms the backdrop.",
        "JPY and CHF can lag if safe-haven demand fades.",
        "USD can be mixed when growth support conflicts with broader risk appetite.",
    ],
    "Goldilocks / Disinflationary Growth": [
        "Risk-sensitive currencies can receive support when growth is stable and inflation pressure cools.",
        "JPY and CHF can lag unless risk-off pressure returns.",
        "USD can soften if lower inflation reduces policy support while risk appetite improves.",
    ],
    "Neutral / Transition": [
        "FX implications are less reliable because the backdrop is not decisive.",
        "Pair ideas should lean more heavily on data quality, OOS history and fresh confirmation.",
        "Avoid treating one currency as structurally strong or weak from the backdrop alone.",
    ],
}


PUBLIC_NARRATIVE_SOURCE_REGISTRY = [
    {"source_name": "Federal Reserve", "source_type": "Central bank", "coverage": "USD", "url": "https://www.federalreserve.gov/newsevents.htm", "feed_url": "https://www.federalreserve.gov/feeds/press_all.xml", "fetch_enabled": True},
    {"source_name": "Federal Reserve speeches", "source_type": "Central bank", "coverage": "USD", "url": "https://www.federalreserve.gov/newsevents/speeches.htm", "feed_url": "https://www.federalreserve.gov/feeds/speeches.xml", "fetch_enabled": True},
    {"source_name": "European Central Bank", "source_type": "Central bank", "coverage": "EUR", "url": "https://www.ecb.europa.eu/press/html/index.en.html", "feed_url": "", "fetch_enabled": False},
    {"source_name": "Bank of England", "source_type": "Central bank", "coverage": "GBP", "url": "https://www.bankofengland.co.uk/news", "feed_url": "", "fetch_enabled": False},
    {"source_name": "Bank of Japan", "source_type": "Central bank", "coverage": "JPY", "url": "https://www.boj.or.jp/en/about/press/index.htm", "feed_url": "", "fetch_enabled": False},
    {"source_name": "Swiss National Bank", "source_type": "Central bank", "coverage": "CHF", "url": "https://www.snb.ch/en/the-snb/mandates-goals/statistics", "feed_url": "", "fetch_enabled": False},
    {"source_name": "Bank of Canada", "source_type": "Central bank", "coverage": "CAD", "url": "https://www.bankofcanada.ca/publications/", "feed_url": "", "fetch_enabled": False},
    {"source_name": "Reserve Bank of Australia", "source_type": "Central bank", "coverage": "AUD", "url": "https://www.rba.gov.au/media-releases/", "feed_url": "", "fetch_enabled": False},
    {"source_name": "Reserve Bank of New Zealand", "source_type": "Central bank", "coverage": "NZD", "url": "https://www.rbnz.govt.nz/news-and-events", "feed_url": "", "fetch_enabled": False},
    {"source_name": "BIS speeches", "source_type": "Official macro commentary", "coverage": "Global", "url": "https://www.bis.org/list/cbspeeches/index.htm", "feed_url": "https://www.bis.org/doclist/cbspeeches.rss", "fetch_enabled": True},
    {"source_name": "IMF Blog", "source_type": "Official macro commentary", "coverage": "Global", "url": "https://www.imf.org/en/Blogs", "feed_url": "", "fetch_enabled": False},
    {"source_name": "OECD Economic Outlook", "source_type": "Official macro commentary", "coverage": "Global", "url": "https://www.oecd.org/economic-outlook/", "feed_url": "", "fetch_enabled": False},
    {"source_name": "World Bank Blogs", "source_type": "Official macro commentary", "coverage": "Global", "url": "https://blogs.worldbank.org/", "feed_url": "", "fetch_enabled": False},
    {"source_name": "New York Fed Liberty Street Economics", "source_type": "Public research blog", "coverage": "USD", "url": "https://libertystreeteconomics.newyorkfed.org/", "feed_url": "https://libertystreeteconomics.newyorkfed.org/feed/", "fetch_enabled": True},
    {"source_name": "Dallas Fed Economics", "source_type": "Public research blog", "coverage": "USD", "url": "https://www.dallasfed.org/research/economics", "feed_url": "", "fetch_enabled": False},
    {"source_name": "Cleveland Fed Economic Commentary", "source_type": "Public research blog", "coverage": "USD", "url": "https://www.clevelandfed.org/publications/economic-commentary", "feed_url": "", "fetch_enabled": False},
    {"source_name": "BlackRock Market Insights", "source_type": "Public asset-manager commentary", "coverage": "Global", "url": "https://www.blackrock.com/corporate/insights", "feed_url": "", "fetch_enabled": False},
    {"source_name": "Vanguard Market Perspectives", "source_type": "Public asset-manager commentary", "coverage": "Global", "url": "https://corporate.vanguard.com/content/corporatesite/us/en/corp/articles/market-perspectives.html", "feed_url": "", "fetch_enabled": False},
    {"source_name": "PIMCO Insights", "source_type": "Public asset-manager commentary", "coverage": "Global", "url": "https://www.pimco.com/en-us/insights", "feed_url": "", "fetch_enabled": False},
    {"source_name": "State Street Global Markets Insights", "source_type": "Public asset-manager commentary", "coverage": "Global", "url": "https://www.statestreet.com/us/en/asset-manager/insights", "feed_url": "", "fetch_enabled": False},
]


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
        .pair-card .kv {
            border-top: 1px solid rgba(148, 163, 184, 0.14);
            padding-top: 7px;
            margin-top: 7px;
        }
        .pair-card .kv span {
            display: block;
            color: #94a3b8;
            font-size: 0.68rem;
            font-weight: 750;
            text-transform: uppercase;
            margin-bottom: 2px;
        }
        .pair-card .kv p {
            color: #cbd5e1;
            font-size: 0.77rem;
            line-height: 1.34;
            margin: 0;
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
        .narrative-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 12px;
            margin: 12px 0 18px 0;
        }
        .narrative-card {
            border: 1px solid rgba(148, 163, 184, 0.24);
            border-radius: 8px;
            padding: 13px 14px;
            background: rgba(15, 23, 42, 0.62);
            min-height: 220px;
        }
        .narrative-card .ccy {
            color: #f8fafc;
            font-size: 1.15rem;
            font-weight: 780;
            margin-bottom: 4px;
        }
        .narrative-card .sentiment {
            color: #f8fafc;
            font-size: 1.02rem;
            font-weight: 740;
            margin-bottom: 8px;
        }
        .narrative-card .line {
            color: #cbd5e1;
            font-size: 0.8rem;
            line-height: 1.34;
            margin-top: 4px;
        }
        .narrative-card .label {
            color: #94a3b8;
            font-size: 0.68rem;
            font-weight: 760;
            text-transform: uppercase;
            margin-top: 8px;
        }
        .narrative-card .mini {
            color: #94a3b8;
            font-size: 0.75rem;
            line-height: 1.3;
        }
        .tone-neutral { border-left: 5px solid #64748b; }
        .tone-mixed { border-left: 5px solid #d99a00; }
        .status-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 12px;
            margin: 12px 0 18px 0;
        }
        .status-card {
            border: 1px solid rgba(148, 163, 184, 0.22);
            border-radius: 8px;
            padding: 12px 14px;
            background: rgba(15, 23, 42, 0.58);
            min-height: 100px;
        }
        .status-card .k {
            color: #94a3b8;
            font-size: 0.72rem;
            text-transform: uppercase;
            margin-bottom: 5px;
        }
        .status-card .v {
            color: #f8fafc;
            font-size: 1.22rem;
            font-weight: 760;
            line-height: 1.2;
        }
        .status-card .d {
            color: #cbd5e1;
            font-size: 0.8rem;
            margin-top: 6px;
            line-height: 1.35;
        }
        .data-gate {
            border: 1px solid rgba(148, 163, 184, 0.22);
            border-radius: 8px;
            padding: 12px 14px;
            background: rgba(2, 6, 23, 0.30);
            margin: 10px 0 16px 0;
        }
        .data-gate strong {
            color: #f8fafc;
        }
        .data-gate span {
            color: #cbd5e1;
        }
        .implication-list {
            border: 1px solid rgba(148, 163, 184, 0.22);
            border-radius: 8px;
            background: rgba(15, 23, 42, 0.58);
            padding: 14px 16px;
            margin: 8px 0 18px 0;
        }
        .implication-list .title {
            color: #f8fafc;
            font-size: 1.02rem;
            font-weight: 760;
            margin-bottom: 8px;
        }
        .implication-list .context {
            color: #94a3b8;
            font-size: 0.84rem;
            line-height: 1.38;
            margin-bottom: 9px;
        }
        .implication-list ul {
            margin: 0;
            padding-left: 18px;
        }
        .implication-list li {
            color: #cbd5e1;
            margin: 5px 0;
            line-height: 1.38;
        }
        .pair-card .meta {
            color: #94a3b8;
            font-size: 0.76rem;
            line-height: 1.35;
            margin-top: 8px;
        }
        .pair-card .reason {
            color: #cbd5e1;
            font-size: 0.76rem;
            line-height: 1.35;
            margin-top: 8px;
        }
        .explain-box {
            border: 1px solid rgba(148, 163, 184, 0.22);
            border-radius: 8px;
            background: rgba(15, 23, 42, 0.58);
            padding: 14px 16px;
            color: #cbd5e1;
            line-height: 1.45;
            margin-bottom: 14px;
        }
        .explain-box strong {
            color: #f8fafc;
        }
        @media (max-width: 980px) {
            .mini-grid,
            .pair-grid,
            .currency-strip,
            .narrative-grid,
            .status-grid {
                grid-template-columns: 1fr;
            }
            .overview-panel .headline {
                font-size: 1.45rem;
            }
            .metric-card,
            .status-card,
            .pair-card {
                min-height: auto;
            }
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


@st.cache_data(show_spinner=False)
def read_json_bytes(data: bytes) -> pd.DataFrame:
    payload = json.loads(data.decode("utf-8-sig"))
    if isinstance(payload, dict):
        if isinstance(payload.get("items"), list):
            payload = payload["items"]
        elif isinstance(payload.get("data"), list):
            payload = payload["data"]
        else:
            payload = [payload]
    return normalize_frame(pd.DataFrame(payload))


@st.cache_data(show_spinner=False)
def read_json_path(path: str) -> pd.DataFrame:
    with open(path, "rb") as handle:
        return read_json_bytes(handle.read())


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


def discover_local_narrative(data_dir: Path) -> Path | None:
    search_dirs = [data_dir, Path.cwd() / "data", Path.cwd()]
    for folder in search_dirs:
        if not folder.exists():
            continue
        for filename in NARRATIVE_FILE_NAMES:
            candidate = folder / filename
            if candidate.exists():
                return candidate
    return None


def read_narrative_payload(name: str, payload: bytes) -> pd.DataFrame:
    if name.lower().endswith(".json"):
        return read_json_bytes(payload)
    return read_csv_bytes(payload)


def parse_uploaded_files() -> Dict[str, pd.DataFrame]:
    uploads = st.sidebar.file_uploader(
        "Colab-ZIP hochladen",
        type=["csv", "zip", "json"],
        accept_multiple_files=True,
        help="Nimm die ZIP-Datei aus dem letzten Colab-Abschnitt Web-App ZIP Export. Optional auch narrative_monitor.csv/json.",
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
                    elif base in NARRATIVE_FILE_NAMES:
                        frames["narrative_monitor"] = read_narrative_payload(base, zf.read(member))
        else:
            base = Path(name).name
            key = filename_to_key.get(base)
            if key:
                frames[key] = read_csv_bytes(payload)
            elif base in NARRATIVE_FILE_NAMES:
                frames["narrative_monitor"] = read_narrative_payload(base, payload)
    return frames


def load_frames() -> Dict[str, pd.DataFrame]:
    data_dir = Path(os.getenv("MACRO_FX_DATA_DIR", "data"))
    local_paths = discover_local_csvs(data_dir)
    frames = {key: read_csv_path(str(path)) for key, path in local_paths.items()}
    narrative_path = discover_local_narrative(data_dir)
    if narrative_path is not None:
        if narrative_path.suffix.lower() == ".json":
            frames["narrative_monitor"] = read_json_path(str(narrative_path))
        else:
            frames["narrative_monitor"] = read_csv_path(str(narrative_path))
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
        (
            f'<div class="metric-card tone-{tone}">'
            f'<div class="label">{esc(label)}</div>'
            f'<div class="value">{esc(value)}</div>'
            f'<div class="detail">{esc(detail)}</div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def hero_card(title: str, text: str, eyebrow: str = "Overview") -> None:
    st.markdown(
        (
            '<div class="hero">'
            f'<div class="eyebrow">{esc(eyebrow)}</div>'
            f'<div class="headline">{esc(title)}</div>'
            f'<div class="copy">{esc(text)}</div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def status_card(label: str, value: object, detail: str = "", tone: str = "info") -> str:
    return (
        f'<div class="status-card tone-{tone}">'
        f'<div class="k">{esc(label)}</div>'
        f'<div class="v">{esc(value)}</div>'
        f'<div class="d">{esc(detail)}</div>'
        "</div>"
    )


def render_status_grid(cards: list[str]) -> None:
    st.markdown(f'<div class="status-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def style_chart(fig: go.Figure, height: int = 420, showlegend: bool | None = None) -> go.Figure:
    fig.update_layout(
        template="plotly_dark",
        height=height,
        margin=dict(l=10, r=10, t=22, b=18),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#dbeafe", size=12),
    )
    fig.update_xaxes(
        showgrid=True,
        gridcolor="rgba(148, 163, 184, 0.16)",
        zeroline=True,
        zerolinecolor="rgba(148, 163, 184, 0.42)",
    )
    fig.update_yaxes(showgrid=False, automargin=True)
    fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0))
    if showlegend is not None:
        fig.update_layout(showlegend=showlegend)
    return fig


def shorten(value: object, limit: int = 120) -> str:
    text = safe_text(value, "")
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 1)].rstrip() + "..."


def quality_tone(value: object) -> str:
    text = safe_text(value, "").lower()
    if any(token in text for token in ["blocked", "no live", "avoid", "contrarian", "broken"]):
        return "bad"
    if any(token in text for token in ["stale", "watch", "rates-only", "limited", "missing", "key"]):
        return "watch"
    if any(token in text for token in ["good", "fresh", "allowed", "ok"]):
        return "good"
    return "info"


def infer_long_short(row: pd.Series) -> tuple[str, str]:
    long_ccy = safe_text(row.get("long_currency", "")).upper()
    short_ccy = safe_text(row.get("short_currency", "")).upper()
    if long_ccy in FX_CURRENCIES and short_ccy in FX_CURRENCIES and long_ccy != short_ccy:
        return long_ccy, short_ccy

    expression = safe_text(row.get("expression", "")).upper()
    match = re.search(r"LONG\s+(USD|EUR|GBP|JPY|CHF|CAD|AUD|NZD)\s*/\s*SHORT\s+(USD|EUR|GBP|JPY|CHF|CAD|AUD|NZD)", expression)
    if match and match.group(1) != match.group(2):
        return match.group(1), match.group(2)

    pair = re.sub(r"[^A-Z]", "", safe_text(row.get("pair", "")).upper())
    if len(pair) >= 6:
        base, quote = pair[:3], pair[3:6]
        if base in FX_CURRENCIES and quote in FX_CURRENCIES:
            direction = safe_text(row.get("direction", "")).lower()
            bias = to_float(row.get("bias_score", 0.0))
            if "bear" in direction or bias < 0:
                return quote, base
            return base, quote
    return "", ""


def data_quality_summary(permission: pd.DataFrame, freshness: pd.DataFrame, readiness: pd.DataFrame) -> dict[str, int]:
    summary = {
        "total_currencies": 0,
        "clean_real_rate": 0,
        "rates_only": 0,
        "stale_fields": 0,
        "key_required": 0,
    }
    if not permission.empty and "currency" in permission.columns:
        summary["total_currencies"] = int(permission["currency"].nunique())
        real_rate = to_bool_series(frame_col(permission, "can_use_real_rate", False))
        rates_only = to_bool_series(frame_col(permission, "can_use_rates_only", False)) & ~real_rate
        summary["clean_real_rate"] = int(real_rate.sum())
        summary["rates_only"] = int(rates_only.sum())
    if not freshness.empty and "is_current_fresh" in freshness.columns:
        summary["stale_fields"] = int((~to_bool_series(freshness["is_current_fresh"])).sum())
    if not readiness.empty and "api_key_required" in readiness.columns:
        summary["key_required"] = int(to_bool_series(readiness["api_key_required"]).sum())
    return summary


def signal_bucket_counts(signals: pd.DataFrame) -> dict[str, int]:
    if signals.empty or "ensemble_action" not in signals.columns:
        return {"watch": 0, "context": 0, "blocked": 0, "trade": 0}
    actions = signals["ensemble_action"].astype(str)
    return {
        "trade": int(actions.eq("Baseline candidate").sum()),
        "watch": int(actions.eq("Research watch only").sum()),
        "context": int(actions.eq("Context watch").sum()),
        "blocked": int(actions.eq("Research / no action").sum()),
    }


def render_data_gate_note(permission: pd.DataFrame, freshness: pd.DataFrame, readiness: pd.DataFrame) -> None:
    summary = data_quality_summary(permission, freshness, readiness)
    st.markdown(
        (
            '<div class="data-gate">'
            "<strong>Data gate:</strong> "
            f'<span>{summary["clean_real_rate"]}/{summary["total_currencies"]} currencies have clean real-rate context. '
            f'{summary["rates_only"]} are rates-only or limited. '
            f'{summary["stale_fields"]} source fields are stale. '
            f'{summary["key_required"]} source rows need an API key or manual upgrade.</span>'
            "</div>"
        ),
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
    except (TypeError, ValueError):
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


def score_lookup(scores: pd.DataFrame, feature: str) -> float | None:
    if scores.empty or not {"feature", "latest_score"}.issubset(scores.columns):
        return None
    row = scores[scores["feature"].astype(str).eq(feature)]
    if row.empty:
        return None
    return to_float(row.iloc[0].get("latest_score"), default=float("nan"))


def render_fx_implications(regime: str, scores: pd.DataFrame) -> None:
    lines = list(REGIME_FX_IMPLICATIONS.get(regime, REGIME_FX_IMPLICATIONS["Neutral / Transition"]))
    commodity_score = score_lookup(scores, "commodity_score")
    policy_score = score_lookup(scores, "policy_score")
    if regime == "Stagflation / Policy Squeeze" and commodity_score is not None and policy_score is not None:
        if commodity_score >= 1.0 and policy_score < 0.75:
            lines.append(
                "In the current data, this looks more like an inflation/commodity squeeze than pure policy tightening because commodity_score is high while policy_score is not strongly positive."
            )
    items = "".join(f"<li>{esc(line)}</li>" for line in lines)
    st.markdown(
        (
            '<div class="implication-list">'
            '<div class="title">FX Implications</div>'
            f'<div class="context">{esc(BACKDROP_EXPLANATION)}</div>'
            f"<ul>{items}</ul>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def currency_data_issue(currency: str, permission: pd.DataFrame, freshness: pd.DataFrame) -> str:
    ccy = safe_text(currency, "").upper()
    if not ccy:
        return ""

    issues: list[str] = []
    if not freshness.empty and {"currency", "field", "is_current_fresh"}.issubset(freshness.columns):
        rows = freshness[freshness["currency"].astype(str).str.upper().eq(ccy)]
        stale_rows = rows[~to_bool_series(rows["is_current_fresh"])]
        for _, stale in stale_rows.iterrows():
            field = safe_text(stale.get("field", "")).lower()
            if "cpi" in field:
                issues.append(f"{ccy} CPI stale")
            elif "short" in field:
                issues.append(f"{ccy} short-rate stale")
            elif "long" in field:
                issues.append(f"{ccy} long-rate stale")
            elif field:
                issues.append(f"{ccy} {field} stale")

    if not permission.empty and "currency" in permission.columns:
        rows = permission[permission["currency"].astype(str).str.upper().eq(ccy)]
        if not rows.empty:
            row = rows.iloc[0]
            if "cpi_fresh" in rows.columns and not to_bool_series(pd.Series([row.get("cpi_fresh")])).iloc[0]:
                issues.append(f"{ccy} CPI stale")
            if "rates_fresh" in rows.columns and not to_bool_series(pd.Series([row.get("rates_fresh")])).iloc[0]:
                issues.append(f"{ccy} rates stale")

    unique = []
    for issue in issues:
        if issue not in unique:
            unique.append(issue)
    return "; ".join(unique)


def pair_data_quality_note(row: pd.Series, permission: pd.DataFrame, freshness: pd.DataFrame) -> str:
    long_ccy, short_ccy = infer_long_short(row)
    issues = [currency_data_issue(ccy, permission, freshness) for ccy in [long_ccy, short_ccy]]
    issues = [issue for issue in issues if issue]
    if issues:
        return "Rates-only / limited: " + "; ".join(issues)
    return "No current data blocker detected for the two currencies."


def pair_support_note(row: pd.Series, strength_map: dict[str, float]) -> str:
    long_ccy, short_ccy = infer_long_short(row)
    if long_ccy and short_ccy:
        long_strength = strength_map.get(long_ccy, 0.0)
        short_strength = strength_map.get(short_ccy, 0.0)
        if long_strength > short_strength:
            return f"{long_ccy} appears stronger than {short_ccy} in the current signal-implied board."
    expression = safe_text(row.get("expression", ""))
    if expression:
        return f"The current exported score can support {expression}."
    return "The current exported score can support this pair idea."


def pair_blocker_note(row: pd.Series, permission: pd.DataFrame, freshness: pd.DataFrame) -> str:
    action = safe_text(row.get("ensemble_action", ""))
    reason = friendly_reason(safe_text(row.get("ensemble_reason", "")))
    data_note = pair_data_quality_note(row, permission, freshness)
    if "No current data blocker" not in data_note:
        return data_note
    if action == "Research watch only":
        return "Macro gate, Bayesian conflict or data freshness still blocks clean live action."
    if action == "Context watch":
        return "Current ensemble keeps this as context rather than a clean baseline signal."
    if action == "Research / no action":
        return reason or "Blocked by at least one frozen baseline or ensemble gate."
    return "No major blocker shown by the exported gate."


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
    regime_text = REGIME_EXPLANATIONS.get(
        regime,
        "The backdrop is derived from growth, inflation, rates, risk, commodities and USD pressure.",
    )
    gate_text = "closed" if gate == "Closed" else safe_text(gate)
    model_note = ""
    if prob_top not in ["", "n/a", regime]:
        model_note = (
            f" Markov/Bayes gives a second-opinion warning for {prob_top}, "
            f"but the driver check is {friendly_bayes(bayes_read)}."
        )
    if "No clean" in str(posture):
        return f"{regime_text} Trend gate is {gate_text}; stale CPI can block clean real-rate use for {stale}.{model_note}"
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
            currencies.update(
                value
                for value in signals[column].dropna().astype(str).str.upper().tolist()
                if value in FX_CURRENCIES
            )
    for _, row in signals.iterrows():
        long_ccy, short_ccy = infer_long_short(row)
        if long_ccy:
            currencies.add(long_ccy)
        if short_ccy:
            currencies.add(short_ccy)
    if "currency" in permission.columns:
        currencies.update(
            value
            for value in permission["currency"].dropna().astype(str).str.upper().tolist()
            if value in FX_CURRENCIES
        )
    if not currencies:
        currencies = {"USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD"}

    rows = {
        currency: {"currency": currency, "strength": 0.0, "ideas": 0, "contribution_pairs": []}
        for currency in sorted(currencies)
    }
    for _, row in signals.iterrows():
        long_ccy, short_ccy = infer_long_short(row)
        if not long_ccy or not short_ccy:
            continue
        pair = safe_text(row.get("pair", ""), "")
        score = abs(to_float(row.get("abs_score", row.get("ensemble_final_score", row.get("bias_score", 0.0)))))
        action = safe_text(row.get("ensemble_action", ""))
        weight = {"Research watch only": 1.0, "Context watch": 0.65, "Research / no action": 0.25}.get(action, 0.55)
        contribution = score * weight
        rows.setdefault(long_ccy, {"currency": long_ccy, "strength": 0.0, "ideas": 0, "contribution_pairs": []})
        rows.setdefault(short_ccy, {"currency": short_ccy, "strength": 0.0, "ideas": 0, "contribution_pairs": []})
        rows[long_ccy]["strength"] += contribution
        rows[short_ccy]["strength"] -= contribution
        rows[long_ccy]["ideas"] += 1
        rows[short_ccy]["ideas"] += 1
        if pair:
            rows[long_ccy]["contribution_pairs"].append((pair, contribution))
            rows[short_ccy]["contribution_pairs"].append((pair, -contribution))

    strength = pd.DataFrame(rows.values())
    if not permission.empty and "currency" in permission.columns:
        meta_cols = [col for col in ["currency", "data_quality", "permission", "policy_mode", "can_use_real_rate", "can_use_rates_only"] if col in permission.columns]
        meta = permission[meta_cols].copy()
        meta["currency"] = meta["currency"].astype(str).str.upper()
        strength = strength.merge(meta.drop_duplicates("currency"), on="currency", how="left")
    strength["strength"] = pd.to_numeric(strength["strength"], errors="coerce").fillna(0.0).round(2)
    strength["read"] = strength["strength"].apply(lambda x: "Strong" if x > 0.25 else ("Weak" if x < -0.25 else "Neutral"))
    strength["top_pairs"] = strength["contribution_pairs"].apply(
        lambda pairs: ", ".join(
            f"{pair} {value:+.2f}"
            for pair, value in sorted(pairs, key=lambda item: abs(item[1]), reverse=True)[:3]
        )
        if isinstance(pairs, list)
        else ""
    )
    return strength.sort_values("strength", ascending=False)


def build_pair_matrix(signals: pd.DataFrame, currencies: list[str]) -> pd.DataFrame:
    matrix = pd.DataFrame(0.0, index=currencies, columns=currencies)
    if signals.empty:
        return matrix
    for _, row in signals.iterrows():
        long_ccy, short_ccy = infer_long_short(row)
        if long_ccy not in matrix.index or short_ccy not in matrix.columns:
            continue
        score = abs(to_float(row.get("abs_score", row.get("ensemble_final_score", row.get("bias_score", 0.0)))))
        if abs(score) >= abs(matrix.loc[long_ccy, short_ccy]):
            matrix.loc[long_ccy, short_ccy] = score
            matrix.loc[short_ccy, long_ccy] = -score
    return matrix.round(2)


def build_pair_hover_text(matrix: pd.DataFrame) -> pd.DataFrame:
    hover = pd.DataFrame("", index=matrix.index, columns=matrix.columns)
    for row_currency in matrix.index:
        for column_currency in matrix.columns:
            value = to_float(matrix.loc[row_currency, column_currency])
            if value > 0:
                direction = f"Long {row_currency} / Short {column_currency}"
            elif value < 0:
                direction = f"Long {column_currency} / Short {row_currency}"
            else:
                direction = "No directional edge"
            hover.loc[row_currency, column_currency] = (
                f"{direction}<br>"
                f"Signed bias: {value:+.2f}<br>"
                f"Absolute bias: {abs(value):.2f}<br>"
                "Source: signal-implied pair board"
            )
    return hover


def term_pattern(term: str) -> str:
    escaped = re.escape(term.lower())
    escaped = escaped.replace(r"\ ", r"\s+")
    return rf"(?<![a-z0-9]){escaped}(?![a-z0-9])"


def text_has_term(text: str, term: str) -> bool:
    return bool(re.search(term_pattern(term), text.lower()))


def text_has_any(text: str, terms: list[str]) -> bool:
    lowered = safe_text(text, "").lower()
    return any(text_has_term(lowered, term) for term in terms)


def extract_currencies(value: object) -> list[str]:
    text = safe_text(value, "")
    found = []
    for currency in sorted(FX_CURRENCIES):
        terms = CURRENCY_DETECTION_TERMS.get(currency, [currency])
        if text_has_any(text, terms):
            found.append(currency)
    return found


def detected_currency_string(value: object, fallback: object = "") -> str:
    currencies = extract_currencies(value)
    if not currencies:
        currencies = extract_currencies(fallback)
    return ", ".join(currencies)


def normalize_label(value: object, allowed: set[str], default: str) -> str:
    text = safe_text(value, default).strip()
    if not text:
        return default
    for label in allowed:
        if text.lower() == label.lower():
            return label
    return default


def normalize_loaded_narrative_items(frame: pd.DataFrame, dedupe_mode: str = "item") -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=NARRATIVE_COLUMNS + ["detected_currencies", "published_dt", "age_days", "exclusion_reason", "included_in_aggregation"])
    out = frame.copy()
    out.columns = [str(column).strip().lower() for column in out.columns]
    for column in NARRATIVE_COLUMNS:
        if column not in out.columns:
            out[column] = ""
    out["sentiment"] = out["sentiment"].apply(lambda value: normalize_label(value, {"Bullish", "Bearish", "Neutral", "Mixed"}, "Neutral"))
    out["confidence"] = out["confidence"].apply(lambda value: normalize_label(value, {"Low", "Medium", "High"}, "Low"))
    out["relevance"] = out["relevance"].apply(
        lambda value: normalize_label(
            value,
            {"Currency-specific", "Direct macro-policy relevance", "General market commentary", "Weak mention"},
            "General market commentary",
        )
    )
    out["published_dt"] = pd.to_datetime(out["published_at"], errors="coerce", utc=True)
    out["age_days"] = out["published_dt"].apply(narrative_age_days)
    detection_columns = [col for col in ["currency", "detected_currencies", "title", "summary", "themes", "supports", "risks", "reason", "source_name"] if col in out.columns]
    out["detection_text"] = out[detection_columns].astype(str).agg(" ".join, axis=1) if detection_columns else ""
    out["detected_currencies"] = out["detection_text"].apply(detected_currency_string)
    out["dedupe_key"] = (
        out["url"].astype(str).str.strip().str.lower()
        + "|"
        + out["title"].astype(str).str.strip().str.lower()
    )
    if dedupe_mode == "currency":
        out["dedupe_key"] = out["dedupe_key"] + "|" + out["currency"].astype(str).str.strip().str.upper()
    out = out.drop_duplicates("dedupe_key").drop(columns=["dedupe_key"])
    out["source_item_id"] = range(1, len(out) + 1)
    out["included_in_aggregation"] = out.apply(
        lambda row: bool(row.get("detected_currencies")) and to_float(row.get("age_days"), 999.0) <= 14 and row.get("relevance") != "Weak mention",
        axis=1,
    )
    out["exclusion_reason"] = out.apply(narrative_exclusion_reason, axis=1)
    return out.drop(columns=[col for col in ["detection_text"] if col in out.columns])


def narrative_exclusion_reason(row: pd.Series) -> str:
    detected = safe_text(row.get("detected_currencies", ""), "")
    age_days = to_float(row.get("age_days"), 999.0)
    relevance = safe_text(row.get("relevance", ""))
    sentiment = safe_text(row.get("sentiment", ""))
    if not detected:
        return "Excluded: no currency detected"
    if age_days > 14:
        return "Excluded from firm read: older than 14 days"
    if relevance == "Weak mention":
        return "Weak clue only: currency mention is weak"
    if sentiment in ["Neutral", "Mixed"]:
        return "Included as context: no clear directional score"
    return "Included in aggregation"


def normalize_narrative_frame(frame: pd.DataFrame) -> pd.DataFrame:
    loaded = normalize_loaded_narrative_items(frame, dedupe_mode="currency")
    if loaded.empty:
        return pd.DataFrame(columns=NARRATIVE_COLUMNS + ["detected_currencies", "published_dt", "age_days", "weighted_source_score", "exclusion_reason", "included_in_aggregation"])

    exploded_rows = []
    for _, row in loaded.iterrows():
        explicit_currencies = extract_currencies(row.get("currency", ""))
        detected_currencies = extract_currencies(row.get("detected_currencies", ""))
        currencies = explicit_currencies or detected_currencies
        for currency in currencies:
            if currency in FX_CURRENCIES:
                clone = row.copy()
                clone["currency"] = currency
                exploded_rows.append(clone)
    if not exploded_rows:
        return pd.DataFrame(columns=NARRATIVE_COLUMNS + ["detected_currencies", "published_dt", "age_days", "weighted_source_score", "exclusion_reason", "included_in_aggregation"])

    out = pd.DataFrame(exploded_rows)
    out["dedupe_key"] = (
        out["url"].astype(str).str.strip().str.lower()
        + "|"
        + out["title"].astype(str).str.strip().str.lower()
        + "|"
        + out["currency"].astype(str)
    )
    out = out.drop_duplicates("dedupe_key").drop(columns=["dedupe_key"])
    return out


def narrative_age_days(value: object) -> float:
    if value is None or pd.isna(value):
        return 999.0
    published = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(published):
        return 999.0
    return max((pd.Timestamp.now(tz="UTC") - published).total_seconds() / 86400.0, 0.0)


def narrative_freshness_weight(age_days: float) -> float:
    if age_days <= 2:
        return 1.25
    if age_days <= 7:
        return 1.0
    if age_days <= 14:
        return 0.7
    return 0.4


def narrative_weighted_score(row: pd.Series) -> float:
    sentiment_weight = {"Bullish": 1.0, "Bearish": -1.0, "Neutral": 0.0, "Mixed": 0.0}.get(safe_text(row.get("sentiment")), 0.0)
    confidence_weight = {"Low": 0.5, "Medium": 1.0, "High": 1.5}.get(safe_text(row.get("confidence")), 0.5)
    relevance_weight = {
        "Currency-specific": 1.3,
        "Direct macro-policy relevance": 1.0,
        "General market commentary": 0.8,
        "Weak mention": 0.4,
    }.get(safe_text(row.get("relevance")), 0.8)
    freshness_weight = narrative_freshness_weight(to_float(row.get("age_days"), 999.0))
    return sentiment_weight * confidence_weight * freshness_weight * relevance_weight


def split_theme_tokens(values: pd.Series) -> list[str]:
    tokens: list[str] = []
    for value in values.dropna().astype(str):
        for token in re.split(r"[;,|]", value):
            clean = token.strip()
            if clean:
                tokens.append(clean)
    return tokens


def top_texts(rows: pd.DataFrame, columns: list[str], limit: int = 2) -> str:
    snippets = []
    for _, row in rows.iterrows():
        for column in columns:
            text = safe_text(row.get(column, ""), "")
            if text and text not in snippets:
                snippets.append(shorten(text, 110))
                break
        if len(snippets) >= limit:
            break
    return " | ".join(snippets) if snippets else "n/a"


def aggregate_public_narratives(narrative: pd.DataFrame, strength: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    details = normalize_narrative_frame(narrative)
    if details.empty:
        empty_summary = pd.DataFrame(
            {
                "currency": sorted(FX_CURRENCIES),
                "sentiment": "Not enough data",
                "confidence": "Low",
                "weighted_score": 0.0,
                "bullish_sources": 0,
                "bearish_sources": 0,
                "neutral_mixed_sources": 0,
                "latest_source_date": "n/a",
                "source_count": 0,
                "main_themes": "n/a",
                "supporting_arguments": "n/a",
                "opposing_arguments": "n/a",
                "weak_clues": "n/a",
                "loaded_source_titles": "n/a",
                "why_no_firm_read": "No public narrative data loaded for this currency.",
                "used_source_count": 0,
                "fresh_source_count": 0,
                "narrative_vs_dashboard": "Not enough data",
            }
        )
        return empty_summary, details

    details = details.copy()
    if "age_days" not in details.columns:
        details["age_days"] = details["published_dt"].apply(narrative_age_days)
    details["weighted_source_score"] = details.apply(narrative_weighted_score, axis=1).round(3)
    if "included_in_aggregation" not in details.columns:
        details["included_in_aggregation"] = details["age_days"].le(14) & details["detected_currencies"].astype(str).ne("") & details["relevance"].astype(str).ne("Weak mention")
    details["exclusion_reason"] = details.apply(narrative_exclusion_reason, axis=1)

    strength_map = {}
    if not strength.empty and {"currency", "strength"}.issubset(strength.columns):
        strength_map = dict(zip(strength["currency"].astype(str).str.upper(), pd.to_numeric(strength["strength"], errors="coerce").fillna(0.0)))

    summary_rows = []
    for currency in sorted(FX_CURRENCIES):
        rows = details[details["currency"].eq(currency)].copy()
        fresh_rows = rows[rows["age_days"].le(14)]
        used_rows = rows[to_bool_series(rows["included_in_aggregation"])] if not rows.empty else rows
        working = used_rows if not used_rows.empty else (fresh_rows if not fresh_rows.empty else rows)
        source_count = int(len(rows))
        fresh_count = int(len(fresh_rows))
        used_count = int(len(used_rows))
        bullish_sources = int(working["sentiment"].eq("Bullish").sum())
        bearish_sources = int(working["sentiment"].eq("Bearish").sum())
        neutral_mixed_sources = int(working["sentiment"].isin(["Neutral", "Mixed"]).sum())
        weighted_score = float(used_rows["weighted_source_score"].sum()) if not used_rows.empty else 0.0
        bull_weight = float(working.loc[working["weighted_source_score"] > 0, "weighted_source_score"].sum()) if not working.empty else 0.0
        bear_weight = abs(float(working.loc[working["weighted_source_score"] < 0, "weighted_source_score"].sum())) if not working.empty else 0.0
        contradiction = bull_weight > 0.75 and bear_weight > 0.75 and min(bull_weight, bear_weight) / max(bull_weight, bear_weight) > 0.35

        if used_count < 2:
            sentiment = "Not enough data"
        elif contradiction:
            sentiment = "Mixed"
        elif weighted_score >= 1.5:
            sentiment = "Bullish"
        elif weighted_score <= -1.5:
            sentiment = "Bearish"
        elif bullish_sources or bearish_sources:
            sentiment = "Mixed"
        else:
            sentiment = "Neutral"

        if sentiment == "Not enough data":
            confidence = "Low"
        elif abs(weighted_score) >= 2.5 and used_count >= 4 and not contradiction:
            confidence = "High"
        elif abs(weighted_score) >= 1.0 and used_count >= 2:
            confidence = "Medium"
        else:
            confidence = "Low"

        strength_value = strength_map.get(currency, 0.0)
        if sentiment == "Bullish" and strength_value > 0.25:
            narrative_vs_dashboard = "Supports dashboard"
        elif sentiment == "Bearish" and strength_value < -0.25:
            narrative_vs_dashboard = "Supports dashboard"
        elif sentiment == "Bullish" and strength_value < -0.25:
            narrative_vs_dashboard = "Conflicts with dashboard"
        elif sentiment == "Bearish" and strength_value > 0.25:
            narrative_vs_dashboard = "Conflicts with dashboard"
        else:
            narrative_vs_dashboard = "Not enough data"

        themes = split_theme_tokens(working["themes"]) if not working.empty else []
        top_themes = pd.Series(themes).value_counts().head(4).index.tolist() if themes else []
        latest_date = "n/a"
        if not rows.empty and rows["published_dt"].notna().any():
            latest_date = str(rows["published_dt"].max().date())
        weak_clues = top_texts(rows.sort_values("age_days"), ["title", "summary", "reason"], limit=3) if not rows.empty else "n/a"
        loaded_titles = top_texts(rows.sort_values("age_days"), ["title"], limit=4) if not rows.empty else "n/a"
        if used_count < 2:
            if rows.empty:
                why_no_firm_read = "No loaded source detected this currency."
            elif fresh_count < 2:
                why_no_firm_read = f"Only {fresh_count} fresh detected item(s); at least 2 good fresh sources are required."
            else:
                why_no_firm_read = f"Only {used_count} good item(s) after weak-mention and freshness filters; at least 2 are required."
        elif contradiction:
            why_no_firm_read = "Bullish and bearish public evidence both matter, so the read stays mixed."
        elif sentiment in ["Neutral", "Mixed"]:
            why_no_firm_read = "Loaded sources do not produce a clear directional public narrative."
        else:
            why_no_firm_read = "A directional narrative exists, but it remains research context only."

        summary_rows.append(
            {
                "currency": currency,
                "sentiment": sentiment,
                "confidence": confidence,
                "weighted_score": round(weighted_score, 2),
                "bullish_sources": bullish_sources,
                "bearish_sources": bearish_sources,
                "neutral_mixed_sources": neutral_mixed_sources,
                "latest_source_date": latest_date,
                "source_count": source_count,
                "fresh_source_count": fresh_count,
                "used_source_count": used_count,
                "main_themes": ", ".join(top_themes) if top_themes else "n/a",
                "supporting_arguments": top_texts(working[working["weighted_source_score"] > 0].sort_values("weighted_source_score", ascending=False), ["supports", "summary", "reason"]),
                "opposing_arguments": top_texts(working[working["weighted_source_score"] < 0].sort_values("weighted_source_score"), ["risks", "summary", "reason"]),
                "weak_clues": weak_clues,
                "loaded_source_titles": loaded_titles,
                "why_no_firm_read": why_no_firm_read,
                "narrative_vs_dashboard": narrative_vs_dashboard,
            }
        )

    return pd.DataFrame(summary_rows), details


def narrative_tone(sentiment: str) -> str:
    if sentiment == "Bullish":
        return "good"
    if sentiment == "Bearish":
        return "bad"
    if sentiment == "Mixed":
        return "mixed"
    if sentiment == "Neutral":
        return "neutral"
    return "info"


def classify_relevance(source_type: str, text: str, detected_from_text: bool) -> str:
    if not detected_from_text:
        return "Weak mention"
    if any(term in text for term in ["currency", "fx", "foreign exchange", "dollar", "yen", "sterling", "euro", "aussie", "kiwi", "loonie"]):
        return "Currency-specific"
    if any(term in text for term in ["central bank", "rates", "rate", "yield", "inflation", "cpi", "fomc", "ecb", "boe", "boj", "boc", "rba", "rbnz", "snb"]):
        return "Direct macro-policy relevance"
    if "Central bank" in source_type or "Official" in source_type:
        return "Direct macro-policy relevance"
    return "General market commentary"


def classify_currency_sentiment(currency: str, text: str) -> tuple[str, str, str, str, str, str]:
    support: list[str] = []
    risk: list[str] = []
    themes: list[str] = []

    hawkish = text_has_any(text, ["hawkish", "higher yields", "higher rates", "rising yields", "yields rise", "yields rose", "tightening", "rate hike", "restrictive policy"])
    dovish = text_has_any(text, ["dovish", "rate cuts", "rate cut", "cut rates", "lower yields", "lower rates", "easing", "policy easing"])
    hot_inflation = text_has_any(text, ["hot inflation", "sticky inflation", "inflation pressure", "higher inflation", "above-target inflation", "price pressures"])
    weak_growth = text_has_any(text, ["weak growth", "growth weakness", "slowdown", "recession", "contraction", "stagnation", "downturn"])
    risk_off = text_has_any(text, ["risk-off", "risk off", "risk aversion", "safe haven", "market stress", "volatility spike", "liquidity stress"])
    risk_on = text_has_any(text, ["risk-on", "risk on", "risk appetite", "soft landing", "equities rally", "carry demand"])
    commodity_strength = text_has_any(text, ["commodity strength", "commodities higher", "higher commodities", "higher oil", "oil strength", "higher metals", "metals rally"])
    oil_weakness = text_has_any(text, ["oil weakness", "lower oil", "oil prices fall", "oil prices fell", "weaker oil", "oil selloff"])

    if hawkish:
        support.append("hawkish central bank / higher yields can support the currency")
        themes.append("rates")
    if dovish:
        risk.append("dovish central bank / rate-cut pressure can weigh on the currency")
        themes.append("rates")
    if hot_inflation:
        if weak_growth:
            support.append("hot inflation can support rates")
            risk.append("weak growth makes the inflation signal mixed")
        else:
            support.append("hot inflation can support the currency through rates expectations")
        themes.append("inflation")
    if weak_growth:
        risk.append("weak growth / recession language can pressure the currency")
        themes.append("growth")
    if risk_off:
        themes.append("risk-off")
        if currency in ["JPY", "CHF"]:
            support.append("risk-off language can support safe-haven currencies")
        elif currency in ["AUD", "NZD", "CAD"]:
            risk.append("risk-off language can pressure high-beta / commodity-linked currencies")
        elif currency == "USD":
            support.append("risk-off language can support USD liquidity demand")
            risk.append("risk-off can also conflict with growth-sensitive USD narratives")
    if risk_on:
        themes.append("risk-on")
        if currency in ["AUD", "NZD", "CAD"]:
            support.append("risk-on language can support high-beta / commodity-linked currencies")
        elif currency in ["JPY", "CHF"]:
            risk.append("risk-on language can reduce safe-haven demand")
    if commodity_strength:
        themes.append("commodities")
        if currency in ["CAD", "AUD"]:
            support.append("commodity strength can support CAD/AUD")
    if oil_weakness and currency == "CAD":
        themes.append("oil")
        risk.append("oil weakness can pressure CAD")

    support = list(dict.fromkeys(support))
    risk = list(dict.fromkeys(risk))
    themes = list(dict.fromkeys(themes)) or ["public commentary"]

    if support and risk:
        sentiment = "Mixed"
    elif support:
        sentiment = "Bullish"
    elif risk:
        sentiment = "Bearish"
    else:
        sentiment = "Neutral"

    evidence_count = len(support) + len(risk)
    if sentiment in ["Bullish", "Bearish"] and evidence_count >= 2:
        confidence = "Medium"
    elif sentiment == "Mixed" and evidence_count >= 2:
        confidence = "Medium"
    else:
        confidence = "Low"

    reason = "No strong directional FX rule matched; kept as public context."
    if sentiment != "Neutral":
        reason = " | ".join((support + risk)[:3])
    return sentiment, confidence, "; ".join(themes), " | ".join(support), " | ".join(risk), reason


def classify_public_item(source: dict, title: str, summary: str, published_at: str, url: str) -> list[dict]:
    source_name = safe_text(source.get("source_name", "Unknown source"))
    source_type = safe_text(source.get("source_type", "Public commentary"))
    coverage = safe_text(source.get("coverage", "")).upper()
    content_text = f"{title} {summary}".lower()
    source_context = f"{source_name} {coverage}".lower()
    text = f"{content_text} {source_context}"
    detected = extract_currencies(text)
    detected_from_text = bool(extract_currencies(content_text))
    if not detected and coverage in FX_CURRENCIES:
        detected = [coverage]
    if not detected:
        return []

    relevance = classify_relevance(source_type, text, detected_from_text or coverage in FX_CURRENCIES)
    if coverage in FX_CURRENCIES and any(label in source_type.lower() for label in ["central bank", "official"]):
        relevance = "Direct macro-policy relevance"
    rows = []
    for currency in detected:
        sentiment, confidence, themes, supports, risks, reason = classify_currency_sentiment(currency, text)
        if relevance == "Weak mention" and confidence == "Medium":
            confidence = "Low"
        rows.append(
            {
                "currency": currency,
                "detected_currencies": ", ".join(detected),
                "source_name": source_name,
                "source_type": source_type,
                "title": title,
                "url": url,
                "published_at": published_at,
                "summary": shorten(summary, 260),
                "sentiment": sentiment,
                "confidence": confidence,
                "relevance": relevance,
                "themes": themes,
                "supports": supports,
                "risks": risks,
                "reason": reason,
            }
        )
    return rows


def clean_feed_text(value: object) -> str:
    text = safe_text(value, "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def parse_feed_date(value: object) -> str:
    text = safe_text(value, "")
    if not text:
        return ""
    try:
        return parsedate_to_datetime(text).isoformat()
    except Exception:
        parsed = pd.to_datetime(text, errors="coerce", utc=True)
        return "" if pd.isna(parsed) else parsed.isoformat()


def fetch_feed_items(source: dict, per_source_limit: int = 6) -> tuple[list[dict], list[dict]]:
    feed_url = safe_text(source.get("feed_url", ""), "")
    if not feed_url:
        return [], []
    request = urllib.request.Request(feed_url, headers={"User-Agent": "MacroFXCockpitPublicNarrativeMonitor/1.0"})
    with urllib.request.urlopen(request, timeout=8) as response:
        payload = response.read()
    root = ET.fromstring(payload)
    items = root.findall(".//item")
    if not items:
        items = root.findall(".//{http://www.w3.org/2005/Atom}entry")

    raw_rows = []
    classified_rows = []
    for item in items[:per_source_limit]:
        title = clean_feed_text(item.findtext("title") or item.findtext("{http://www.w3.org/2005/Atom}title"))
        summary = clean_feed_text(
            item.findtext("description")
            or item.findtext("summary")
            or item.findtext("{http://www.w3.org/2005/Atom}summary")
            or ""
        )
        link = clean_feed_text(item.findtext("link") or "")
        atom_link = item.find("{http://www.w3.org/2005/Atom}link")
        if not link and atom_link is not None:
            link = atom_link.attrib.get("href", "")
        published_at = parse_feed_date(
            item.findtext("pubDate")
            or item.findtext("published")
            or item.findtext("updated")
            or item.findtext("{http://www.w3.org/2005/Atom}published")
            or item.findtext("{http://www.w3.org/2005/Atom}updated")
        )
        url = link or safe_text(source.get("url", ""))
        source_context = f"{safe_text(source.get('source_name', ''))} {safe_text(source.get('coverage', ''))}"
        detection_text = f"{title} {summary} {source_context}"
        detected = detected_currency_string(detection_text)
        source_type = safe_text(source.get("source_type", "Public commentary"))
        coverage = safe_text(source.get("coverage", "")).upper()
        relevance = classify_relevance(source_type, detection_text.lower(), bool(extract_currencies(f"{title} {summary}")) or coverage in FX_CURRENCIES)
        if coverage in FX_CURRENCIES and any(label in source_type.lower() for label in ["central bank", "official"]):
            relevance = "Direct macro-policy relevance"
        raw_rows.append(
            {
                "currency": detected,
                "detected_currencies": detected,
                "source_name": source.get("source_name", "Unknown source"),
                "source_type": source_type,
                "title": title,
                "url": url,
                "published_at": published_at,
                "summary": shorten(summary, 320),
                "sentiment": "Neutral",
                "confidence": "Low",
                "relevance": relevance,
                "themes": "public commentary",
                "supports": "",
                "risks": "",
                "reason": "Raw fetched public item. Classification happens per detected currency.",
            }
        )
        classified_rows.extend(classify_public_item(source, title, summary, published_at, url))
    return raw_rows, classified_rows


@st.cache_data(ttl=14400, show_spinner=False)
def fetch_public_narratives(refresh_token: int) -> tuple[pd.DataFrame, list[dict], str, dict, pd.DataFrame]:
    rows = []
    raw_rows = []
    failures = []
    attempted = 0
    successful = 0
    for source in PUBLIC_NARRATIVE_SOURCE_REGISTRY:
        if not source.get("fetch_enabled"):
            continue
        attempted += 1
        try:
            source_raw, source_rows = fetch_feed_items(source, per_source_limit=6)
            raw_rows.extend(source_raw)
            rows.extend(source_rows)
            successful += 1
        except (urllib.error.URLError, urllib.error.HTTPError, ET.ParseError, TimeoutError, OSError) as exc:
            failures.append(
                {
                    "source_name": source.get("source_name", "Unknown source"),
                    "source_type": source.get("source_type", ""),
                    "url": source.get("feed_url") or source.get("url"),
                    "error": shorten(str(exc), 180),
                }
            )
        if len(rows) >= 120:
            rows = rows[:120]
            break
    refreshed_at = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC")
    raw_frame = pd.DataFrame(raw_rows)
    classified_frame = pd.DataFrame(rows)
    normalized_raw = normalize_loaded_narrative_items(raw_frame)
    normalized_details = normalize_narrative_frame(classified_frame)
    diagnostics = {
        "sources_configured": len(PUBLIC_NARRATIVE_SOURCE_REGISTRY),
        "sources_attempted": attempted,
        "sources_successful": successful,
        "sources_failed": len(failures),
        "items_fetched": len(raw_rows),
        "items_after_dedupe": len(normalized_raw),
        "items_after_freshness_filter": int(normalized_raw["age_days"].le(14).sum()) if not normalized_raw.empty and "age_days" in normalized_raw.columns else 0,
        "items_with_detected_currencies": int(normalized_raw["detected_currencies"].astype(str).str.len().gt(0).sum()) if not normalized_raw.empty and "detected_currencies" in normalized_raw.columns else 0,
        "items_used_in_aggregation": int(to_bool_series(normalized_details["included_in_aggregation"]).sum()) if not normalized_details.empty and "included_in_aggregation" in normalized_details.columns else 0,
    }
    return classified_frame, failures, refreshed_at, diagnostics, normalized_raw


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
        (
            '<div class="overview-panel">'
            f'<div class="headline">{esc(headline)}</div>'
            f'<div class="body">{esc(body)}</div>'
            '<div class="mini-grid">'
            f'<div class="mini-stat"><div class="k">{esc(BACKDROP_LABEL)}</div><div class="v">{esc(final_regime)}</div></div>'
            f'<div class="mini-stat"><div class="k">Confidence</div><div class="v">{esc(confidence)}/100</div></div>'
            f'<div class="mini-stat"><div class="k">Clean Currencies</div><div class="v">{clean}/{total}</div></div>'
            "</div></div>"
        ),
        unsafe_allow_html=True,
    )


def render_pair_cards(
    signals: pd.DataFrame,
    permission: pd.DataFrame | None = None,
    freshness: pd.DataFrame | None = None,
    strength: pd.DataFrame | None = None,
    limit: int = 4,
) -> None:
    if signals.empty:
        st.info("No pair ideas loaded.")
        return
    permission = pd.DataFrame() if permission is None else permission
    freshness = pd.DataFrame() if freshness is None else freshness
    strength_map = {}
    if strength is not None and not strength.empty and {"currency", "strength"}.issubset(strength.columns):
        strength_map = dict(zip(strength["currency"].astype(str).str.upper(), pd.to_numeric(strength["strength"], errors="coerce").fillna(0.0)))
    top = sort_signal_board(signals).head(limit)
    cards = []
    for _, row in top.iterrows():
        pair = row.get("pair", "n/a")
        idea = row.get("expression", "n/a")
        score = to_float(row.get("ensemble_final_score", row.get("abs_score", 0.0)))
        status = friendly_action(safe_text(row.get("ensemble_action", "")))
        use = friendly_permission(safe_text(row.get("position_permission", "")))
        rates = friendly_history(safe_text(row.get("rates_oos_label", "")))
        cpi = friendly_history(safe_text(row.get("cpi_oos_label", "")))
        reason = friendly_reason(safe_text(row.get("ensemble_reason", "")))
        tone = action_tone(safe_text(row.get("ensemble_action", "")))
        support = pair_support_note(row, strength_map)
        blocker = pair_blocker_note(row, permission, freshness)
        data_quality = pair_data_quality_note(row, permission, freshness)
        cards.append(
            (
                '<div class="pair-card">'
                f'<div class="pair">{esc(pair)}</div>'
                f'<div class="idea">Signal: {esc(idea)}</div>'
                f'<div class="score">{score:.2f}</div>'
                f'<span class="pill pill-{tone}">{esc(status)}</span>'
                f'<span class="pill pill-info">{esc(use)}</span>'
                f'<div class="kv"><span>Status</span><p>{esc(status)}</p></div>'
                f'<div class="kv"><span>Permission</span><p>{esc(use)}</p></div>'
                f'<div class="kv"><span>Main support</span><p>{esc(shorten(support, 120))}</p></div>'
                f'<div class="kv"><span>Main blocker</span><p>{esc(shorten(blocker, 140))}</p></div>'
                f'<div class="kv"><span>History</span><p>Rates: {esc(rates)} | Real-rate: {esc(cpi)}</p></div>'
                f'<div class="kv"><span>Data quality</span><p>{esc(shorten(data_quality, 130))}</p></div>'
                f'<div class="reason">{esc(shorten(reason, 130))}</div>'
                "</div>"
            )
        )
    st.markdown(f'<div class="pair-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def overview_view(frames: Dict[str, pd.DataFrame]) -> None:
    regime = get_frame(frames, "ensemble_regime")
    signals = sort_signal_board(get_frame(frames, "ensemble_signals"))
    permission = get_frame(frames, "currency_permission")
    freshness = get_frame(frames, "source_freshness")
    readiness = get_frame(frames, "source_readiness")
    calibrated = get_frame(frames, "calibrated_latest")
    scores = get_frame(frames, "ensemble_scores")
    baseline = get_frame(frames, "final_baseline")
    split = get_frame(frames, "final_split")

    render_overview_panel(regime, permission)
    render_data_gate_note(permission, freshness, readiness)

    buckets = signal_bucket_counts(signals)
    baseline_candidates = 0
    if not baseline.empty and "baseline_decision" in baseline.columns:
        baseline_candidates = int(baseline["baseline_decision"].astype(str).eq("Baseline candidate").sum())
    clean, total = clean_currency_count(permission)
    final_regime = lookup(regime, "Final regime read")
    final_confidence = lookup(regime, "Final regime confidence")
    posture = lookup(regime, "Current posture")
    render_status_grid(
        [
            status_card(BACKDROP_LABEL, final_regime, f"Confidence {final_confidence}/100", "good"),
            status_card("Live signal status", readable_posture(posture), "Research cockpit, not an auto-trader.", "watch" if "No clean" in posture else "good"),
            status_card("Clean data coverage", f"{clean}/{total}", "Currencies with usable real-rate context.", "good" if clean >= max(total - 2, 1) else "watch"),
            status_card("Watchlist / baseline", f'{buckets["watch"]} / {baseline_candidates}', "Current watch ideas and frozen baseline candidates.", "watch"),
        ]
    )
    st.markdown(f'<div class="section-note">{esc(BACKDROP_EXPLANATION)}</div>', unsafe_allow_html=True)
    render_fx_implications(final_regime, scores)

    strength = build_currency_strength(signals, permission)
    currencies = strength["currency"].tolist()
    matrix = build_pair_matrix(signals, currencies)
    hover_text = build_pair_hover_text(matrix)

    left, right = st.columns([0.95, 1.05])
    with left:
        st.subheader("Signal-Implied Currency Strength")
        st.markdown(
            '<div class="section-note">This is aggregated from current pair ideas. A currency receives positive contribution when it appears on the long side and negative contribution when it appears on the short side. It is not a full country macro score.</div>',
            unsafe_allow_html=True,
        )
        plot_df = strength.copy()
        fig = px.bar(
            plot_df.sort_values("strength"),
            x="strength",
            y="currency",
            color="read",
            color_discrete_map={"Strong": "#22c55e", "Neutral": "#60a5fa", "Weak": "#ef4444"},
            orientation="h",
            hover_data=[col for col in ["data_quality", "permission", "ideas", "top_pairs"] if col in plot_df.columns],
            labels={"strength": "Relative strength", "currency": "Currency"},
        )
        fig.update_layout(legend_title_text="")
        style_chart(fig, height=440)
        st.plotly_chart(fig, use_container_width=True)

    with right:
        st.subheader("Relative FX Bias")
        st.markdown('<div class="section-note">Green means row currency is favored over column currency. Red means column currency is favored over row currency. This visualizes the exported pair ideas; it is not a new model calculation.</div>', unsafe_allow_html=True)
        fig = go.Figure(
            data=go.Heatmap(
                z=matrix.values,
                x=matrix.columns,
                y=matrix.index,
                customdata=hover_text.values,
                colorscale="RdYlGn",
                zmid=0,
                colorbar=dict(title="Bias"),
                hovertemplate="%{customdata}<extra></extra>",
            )
        )
        fig.update_xaxes(title="Against")
        fig.update_yaxes(title="Currency")
        style_chart(fig, height=440, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    bottom_left, bottom_right = st.columns([0.86, 1.14])
    with bottom_left:
        st.subheader("Backdrop Confidence")
        if not calibrated.empty and {"regime", "calibrated_probability"}.issubset(calibrated.columns):
            plot_df = calibrated.copy().sort_values("calibrated_probability", ascending=True)
            fig = px.bar(
                plot_df,
                x="calibrated_probability",
                y="regime",
                orientation="h",
                color="is_scorecard_regime" if "is_scorecard_regime" in plot_df.columns else None,
                color_discrete_map={True: "#22c55e", False: "#60a5fa"},
                labels={"calibrated_probability": "Probability", "regime": "Backdrop"},
            )
            fig.update_layout(xaxis_tickformat=".0%")
            style_chart(fig, height=320, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No calibrated regime probabilities loaded.")
    with bottom_right:
        st.subheader("Top Pair Ideas")
        st.markdown('<div class="section-note">Cards show research priority and data-gated permission. They are watchlist/context signals unless the exported baseline explicitly allows action.</div>', unsafe_allow_html=True)
        render_pair_cards(signals, permission, freshness, strength, limit=6)

    with st.expander("Technical details: regime decision export"):
        render_dataframe(regime, height=260)
    with st.expander("Technical details: frozen baseline and split exports"):
        render_dataframe(baseline, height=280)
        render_dataframe(split, height=240)


def currencies_view(frames: Dict[str, pd.DataFrame]) -> None:
    signals = sort_signal_board(get_frame(frames, "ensemble_signals"))
    permission = get_frame(frames, "currency_permission")
    freshness = get_frame(frames, "source_freshness")
    readiness = get_frame(frames, "source_readiness")
    strength = build_currency_strength(signals, permission)

    st.subheader("Currencies")
    st.markdown(
        '<div class="section-note">Signal-implied currency strength is aggregated from current pair ideas. It is not a full country macro score; data quality decides whether the read is clean, rates-only or stale.</div>',
        unsafe_allow_html=True,
    )
    render_data_gate_note(permission, freshness, readiness)

    summary = data_quality_summary(permission, freshness, readiness)
    render_status_grid(
        [
            status_card("Clean real-rate", summary["clean_real_rate"], "Rates and CPI are fresh enough for full policy context.", "good"),
            status_card("Rates-only", summary["rates_only"], "Rates are usable, but CPI blocks clean real-rate interpretation.", "watch"),
            status_card("Stale source fields", summary["stale_fields"], "These fields explain why a currency is downgraded.", "bad" if summary["stale_fields"] else "good"),
            status_card("API/key upgrades", summary["key_required"], "Potential future source upgrades.", "info"),
        ]
    )

    if not strength.empty:
        fig = px.bar(
            strength.sort_values("strength"),
            x="strength",
            y="currency",
            color="read",
            color_discrete_map={"Strong": "#22c55e", "Neutral": "#60a5fa", "Weak": "#ef4444"},
            orientation="h",
            hover_data=[col for col in ["data_quality", "policy_mode", "ideas", "top_pairs"] if col in strength.columns],
            labels={"strength": "Relative strength", "currency": "Currency"},
        )
        fig.update_layout(legend_title_text="")
        style_chart(fig, height=460)
        st.plotly_chart(fig, use_container_width=True)

    cards = []
    for _, row in strength.iterrows():
        quality = safe_text(row.get("data_quality", "n/a"))
        tone = quality_tone(quality)
        cards.append(
            (
                '<div class="currency-card">'
                f'<div class="ccy">{esc(row.get("currency"))} / {row.get("strength", 0):.2f}</div>'
                f'<div class="line">Read: {esc(row.get("read"))}</div>'
                f'<div class="line">Data: <span class="pill pill-{tone}">{esc(quality)}</span></div>'
                f'<div class="line">Policy mode: {esc(row.get("policy_mode", "n/a"))}</div>'
                f'<div class="line">Main pairs: {esc(row.get("top_pairs", "n/a"))}</div>'
                "</div>"
            )
        )
    st.markdown(f'<div class="currency-strip">{"".join(cards)}</div>', unsafe_allow_html=True)

    with st.expander("Technical details: currency data permissions"):
        render_dataframe(permission, height=420)


def pairs_view(frames: Dict[str, pd.DataFrame]) -> None:
    signals = sort_signal_board(get_frame(frames, "ensemble_signals"))
    permission = get_frame(frames, "currency_permission")
    freshness = get_frame(frames, "source_freshness")
    readiness = get_frame(frames, "source_readiness")
    strength = build_currency_strength(signals, permission)
    if signals.empty:
        st.info("No pair data loaded.")
        return

    st.subheader("Pairs")
    st.markdown(
        '<div class="section-note">Macro-derived research ideas ranked by current score and filtered by data quality, OOS history and ensemble gates. These are not automatic trade recommendations.</div>',
        unsafe_allow_html=True,
    )
    render_data_gate_note(permission, freshness, readiness)

    buckets = signal_bucket_counts(signals)
    render_status_grid(
        [
            status_card("Handelbar", buckets["trade"], "Only if the frozen baseline export allows it.", "good" if buckets["trade"] else "info"),
            status_card("Beobachten", buckets["watch"], "Research watchlist with OOS/watch support.", "watch"),
            status_card("Nur Kontext", buckets["context"], "Useful for market narrative, not clean action.", "info"),
            status_card("Ignorieren", buckets["blocked"], "Blocked by data, history or ensemble gates.", "bad" if buckets["blocked"] else "good"),
        ]
    )

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
            color_discrete_map={"Handelbar": "#22c55e", "Beobachten": "#f59e0b", "Nur Kontext": "#60a5fa", "Ignorieren": "#ef4444"},
            orientation="h",
            hover_data=[col for col in ["expression", "position_permission", "rates_oos_label", "cpi_oos_label"] if col in top.columns],
            labels={"ensemble_final_score": "Current score", "pair": "Pair"},
        )
        fig.update_layout(legend_title_text="")
        style_chart(fig, height=470)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Pair Cards")
    render_pair_cards(filtered, permission, freshness, strength, limit=8)

    with st.expander("Technical details: simplified pair table"):
        render_dataframe(simplified_signals(filtered), height=430)

    with st.expander("Technical details: raw pair export"):
        render_dataframe(filtered, height=520)


def regime_view(frames: Dict[str, pd.DataFrame]) -> None:
    regime = get_frame(frames, "ensemble_regime")
    alignment = get_frame(frames, "ensemble_alignment")
    scores = get_frame(frames, "ensemble_scores")
    calibrated = get_frame(frames, "calibrated_latest")
    prob_driver = get_frame(frames, "prob_driver")

    st.subheader(BACKDROP_LABEL)
    st.markdown(
        f'<div class="section-note">{esc(BACKDROP_EXPLANATION)} Scorecard is primary; Markov/Bayesian acts as a second-opinion confidence and warning layer.</div>',
        unsafe_allow_html=True,
    )

    final_regime = lookup(regime, "Final regime read")
    prob_top = lookup(regime, "Probabilistic top regime")
    bayes_read = lookup(regime, "Bayesian read")
    confidence = lookup(regime, "Final regime confidence")
    cols = st.columns(3)
    with cols[0]:
        metric_card("Scorecard backdrop", final_regime, f"Confidence {confidence}/100", "good")
    with cols[1]:
        metric_card("Markov/Bayes warning", prob_top, f"Second opinion: {friendly_bayes(bayes_read)}", "watch")
    with cols[2]:
        metric_card("Final regime decision", final_regime, "Scorecard remains primary unless drivers confirm the warning.", "info")

    prob_fit = "n/a"
    scorecard_fit = "n/a"
    prob_fit_value = None
    scorecard_fit_value = None
    if not alignment.empty and {"regime", "semantic_fit_score"}.issubset(alignment.columns):
        scorecard_row = alignment[alignment["regime"].astype(str).eq(final_regime)]
        prob_row = alignment[alignment["regime"].astype(str).eq(prob_top)]
        if not scorecard_row.empty:
            scorecard_fit_value = to_float(scorecard_row.iloc[0].get("semantic_fit_score"))
            scorecard_fit = f"{scorecard_fit_value:.0f}/100"
        if not prob_row.empty:
            prob_fit_value = to_float(prob_row.iloc[0].get("semantic_fit_score"))
            prob_fit = f"{prob_fit_value:.0f}/100"
    if prob_top not in ["", "n/a", final_regime]:
        warning_title = "Markov/Bayes warning, not a regime switch."
        if "Crisis" in prob_top and (prob_fit_value is None or prob_fit_value < 50):
            warning_title = "Crisis warning, not crisis confirmation."
        st.markdown(
            (
                '<div class="explain-box">'
                f"<strong>{esc(warning_title)}</strong> "
                "Scorecard remains primary because the exported driver alignment fits "
                f"<strong>{esc(final_regime)}</strong> at {esc(scorecard_fit)} while the probabilistic top regime "
                f"<strong>{esc(prob_top)}</strong> fits the current macro drivers at {esc(prob_fit)}. "
                "This is accepted as a confidence warning, not as a replacement for the final backdrop."
                "</div>"
            ),
            unsafe_allow_html=True,
        )
    render_fx_implications(final_regime, scores)

    left, right = st.columns([1.0, 1.0])
    with left:
        st.markdown("#### Backdrop probabilities")
        if not calibrated.empty and {"regime", "calibrated_probability"}.issubset(calibrated.columns):
            plot_df = calibrated.copy().sort_values("calibrated_probability")
            fig = px.bar(
                plot_df,
                x="calibrated_probability",
                y="regime",
                orientation="h",
                color="is_scorecard_regime" if "is_scorecard_regime" in plot_df.columns else None,
                color_discrete_map={True: "#22c55e", False: "#60a5fa"},
                labels={"calibrated_probability": "Probability", "regime": "Backdrop"},
            )
            fig.update_layout(xaxis_tickformat=".0%")
            style_chart(fig, height=420, showlegend=False)
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
            style_chart(fig, height=420, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            render_dataframe(scores, height=320)

    st.markdown("#### Driver fit")
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
            labels={"semantic_fit_score": "Fit", "regime": "Backdrop"},
        )
        fig.update_layout(legend_title_text="")
        style_chart(fig, height=360)
        st.plotly_chart(fig, use_container_width=True)

    with st.expander("Technical details: probabilistic driver export"):
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
        fig.update_layout(legend_title_text="")
        style_chart(fig, height=360)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### What needs fixing")
    if not freshness.empty:
        needs = freshness.copy()
        if "is_current_fresh" in needs.columns:
            needs = needs[~to_bool_series(needs["is_current_fresh"])]
        show_cols = [col for col in ["currency", "field", "current_latest", "current_age_days", "primary_source", "access", "api_key_required", "priority", "notes"] if col in needs.columns]
        if show_cols and not needs.empty:
            if "priority" in needs.columns:
                priority_counts = needs["priority"].astype(str).value_counts().reset_index()
                priority_counts.columns = ["priority", "fields"]
                fig = px.bar(
                    priority_counts,
                    x="fields",
                    y="priority",
                    orientation="h",
                    color="priority",
                    color_discrete_sequence=["#ef4444", "#f59e0b", "#60a5fa"],
                    labels={"fields": "Fields", "priority": "Source priority"},
                )
                style_chart(fig, height=260, showlegend=False)
                st.plotly_chart(fig, use_container_width=True)
            with st.expander("Technical details: stale source rows", expanded=False):
                render_dataframe(needs[show_cols], height=280)
        else:
            st.success("No stale source rows found.")

    with st.expander("Technical details: source readiness"):
        render_dataframe(readiness, height=440)
    with st.expander("Technical details: currency permissions"):
        render_dataframe(permission, height=340)


def render_narrative_cards(summary: pd.DataFrame) -> None:
    cards = []
    for _, row in summary.sort_values("currency").iterrows():
        sentiment = safe_text(row.get("sentiment", "Not enough data"))
        tone = narrative_tone(sentiment)
        dashboard_read = safe_text(row.get("narrative_vs_dashboard", "Not enough data"))
        cards.append(
            (
                f'<div class="narrative-card tone-{tone}">'
                f'<div class="ccy">{esc(row.get("currency"))}</div>'
                f'<div class="sentiment">{esc(sentiment)}</div>'
                f'<span class="pill pill-{tone if tone in ["good", "bad", "info"] else "watch"}">{esc(row.get("confidence", "Low"))} confidence</span>'
                f'<div class="line">Weighted narrative score: <strong>{to_float(row.get("weighted_score")):+.2f}</strong></div>'
                f'<div class="line">Sources: {esc(row.get("source_count", 0))} | Latest: {esc(row.get("latest_source_date", "n/a"))}</div>'
                f'<div class="line">Used / fresh: {esc(row.get("used_source_count", 0))} / {esc(row.get("fresh_source_count", 0))}</div>'
                f'<div class="line">Bullish / Bearish / Neutral-Mixed: {esc(row.get("bullish_sources", 0))} / {esc(row.get("bearish_sources", 0))} / {esc(row.get("neutral_mixed_sources", 0))}</div>'
                f'<div class="label">Main themes</div><div class="mini">{esc(shorten(row.get("main_themes", "n/a"), 130))}</div>'
                f'<div class="label">Weak clues</div><div class="mini">{esc(shorten(row.get("weak_clues", "n/a"), 150))}</div>'
                f'<div class="label">Why no firm read?</div><div class="mini">{esc(shorten(row.get("why_no_firm_read", "n/a"), 150))}</div>'
                f'<div class="label">Narrative vs Dashboard</div><div class="mini">{esc(dashboard_read)}</div>'
                "</div>"
            )
        )
    st.markdown(f'<div class="narrative-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def render_fetch_diagnostics(diagnostics: dict, failures: list[dict]) -> None:
    st.markdown("#### Fetch diagnostics")
    diagnostic_cards = [
        status_card("Sources configured", diagnostics.get("sources_configured", len(PUBLIC_NARRATIVE_SOURCE_REGISTRY)), "Curated public source registry.", "info"),
        status_card("Sources attempted", diagnostics.get("sources_attempted", 0), "Only fetch-enabled sources are attempted.", "info"),
        status_card("Sources successful", diagnostics.get("sources_successful", 0), "Returned a readable feed/API response.", "good" if diagnostics.get("sources_successful", 0) else "watch"),
        status_card("Sources failed", diagnostics.get("sources_failed", len(failures)), "Errors are shown below.", "bad" if failures else "good"),
        status_card("Items fetched", diagnostics.get("items_fetched", 0), "Raw public-source items before classification.", "info"),
        status_card("Items after dedupe", diagnostics.get("items_after_dedupe", 0), "Unique by URL/title.", "info"),
        status_card("Fresh items", diagnostics.get("items_after_freshness_filter", 0), "Within the 14-day narrative window.", "good" if diagnostics.get("items_after_freshness_filter", 0) else "watch"),
        status_card("Detected currencies", diagnostics.get("items_with_detected_currencies", 0), "Items with at least one FX currency clue.", "good" if diagnostics.get("items_with_detected_currencies", 0) else "watch"),
        status_card("Used in aggregation", diagnostics.get("items_used_in_aggregation", 0), "Fresh, detected and not weak mention.", "good" if diagnostics.get("items_used_in_aggregation", 0) else "watch"),
    ]
    render_status_grid(diagnostic_cards)
    if failures:
        with st.expander("Failed source errors", expanded=False):
            render_dataframe(pd.DataFrame(failures), height=260)


def render_narrative_source_expanders(summary: pd.DataFrame, details: pd.DataFrame, all_items: pd.DataFrame) -> None:
    st.markdown("#### Source details")
    if not all_items.empty:
        show_cols = [
            col
            for col in [
                "source_name",
                "source_type",
                "title",
                "published_at",
                "detected_currencies",
                "sentiment",
                "confidence",
                "relevance",
                "exclusion_reason",
                "url",
            ]
            if col in all_items.columns
        ]
        with st.expander("All loaded source items, including excluded items", expanded=False):
            render_dataframe(all_items[show_cols], height=420)
    for currency in summary.sort_values("currency")["currency"].tolist():
        rows = details[details["currency"].eq(currency)].copy() if not details.empty and "currency" in details.columns else pd.DataFrame()
        label = f"{currency} sources"
        if rows.empty:
            with st.expander(label, expanded=False):
                st.info("No public narrative data loaded for this currency.")
            continue
        rows = rows.sort_values(["published_dt", "weighted_source_score"], ascending=[False, False], na_position="last").head(12)
        with st.expander(label, expanded=False):
            for _, row in rows.iterrows():
                title = safe_text(row.get("title", "Untitled public item"))
                url = safe_text(row.get("url", ""))
                link = f"[{esc(title)}]({url})" if url else f"**{esc(title)}**"
                published = row.get("published_dt")
                date_text = "n/a" if pd.isna(published) else str(pd.to_datetime(published).date())
                st.markdown(
                    (
                        f"{link}\n\n"
                        f"Source: `{esc(row.get('source_name', 'n/a'))}` | Type: `{esc(row.get('source_type', 'n/a'))}` | Date: `{esc(date_text)}`  \n"
                        f"Detected currencies: `{esc(row.get('detected_currencies', row.get('currency')))} ` | Item currency: `{esc(row.get('currency'))}` | Sentiment: `{esc(row.get('sentiment'))}` | "
                        f"Confidence: `{esc(row.get('confidence'))}` | Relevance: `{esc(row.get('relevance'))}`  \n"
                        f"Exclusion reason: `{esc(row.get('exclusion_reason', 'n/a'))}`  \n"
                        f"Summary: {esc(shorten(row.get('summary', 'n/a'), 220))}  \n"
                        f"Reason: {esc(shorten(row.get('reason', 'n/a'), 180))}"
                    ),
                    unsafe_allow_html=False,
                )
                st.divider()


def narrative_monitor_view(frames: Dict[str, pd.DataFrame]) -> None:
    signals = sort_signal_board(get_frame(frames, "ensemble_signals"))
    permission = get_frame(frames, "currency_permission")
    strength = build_currency_strength(signals, permission)
    csv_narrative = get_frame(frames, "narrative_monitor")

    st.subheader("Public Narrative Monitor")
    st.markdown(
        '<div class="section-note">This tab summarizes public market commentary from accessible sources. It is not bank consensus, not proprietary research and not a trading signal.</div>',
        unsafe_allow_html=True,
    )

    if "narrative_refresh_token" not in st.session_state:
        st.session_state["narrative_refresh_token"] = 0
    if "narrative_live_frame" not in st.session_state:
        st.session_state["narrative_live_frame"] = pd.DataFrame()
    if "narrative_failures" not in st.session_state:
        st.session_state["narrative_failures"] = []
    if "narrative_refreshed_at" not in st.session_state:
        st.session_state["narrative_refreshed_at"] = ""
    if "narrative_raw_items" not in st.session_state:
        st.session_state["narrative_raw_items"] = pd.DataFrame()
    if "narrative_diagnostics" not in st.session_state:
        st.session_state["narrative_diagnostics"] = {}

    cols = st.columns([0.8, 0.2])
    with cols[0]:
        enable_live_fetch = st.checkbox(
            "Enable experimental public-source fetching",
            value=False,
            help="Optional RSS/API-first MVP. Disabled by default; CSV/JSON upload is the stable path.",
        )
    with cols[1]:
        refresh_clicked = st.button("Refresh public narratives", use_container_width=True)

    if refresh_clicked:
        if enable_live_fetch:
            st.session_state["narrative_refresh_token"] += 1
            with st.spinner("Refreshing public narrative sources..."):
                live_frame, failures, refreshed_at, diagnostics, raw_items = fetch_public_narratives(st.session_state["narrative_refresh_token"])
            st.session_state["narrative_live_frame"] = live_frame
            st.session_state["narrative_failures"] = failures
            st.session_state["narrative_refreshed_at"] = refreshed_at
            st.session_state["narrative_diagnostics"] = diagnostics
            st.session_state["narrative_raw_items"] = raw_items
            if live_frame.empty:
                st.warning("Live public-source refresh returned no usable narrative rows. CSV/JSON data or the empty state remains available.")
        else:
            st.info("Live fetching is disabled. Upload narrative_monitor.csv/json or enable experimental fetching before refreshing.")

    live_narrative = st.session_state.get("narrative_live_frame", pd.DataFrame())
    live_raw_items = st.session_state.get("narrative_raw_items", pd.DataFrame())
    has_live_narrative = isinstance(live_narrative, pd.DataFrame) and not live_narrative.empty
    has_live_raw = isinstance(live_raw_items, pd.DataFrame) and not live_raw_items.empty
    has_live_attempt = bool(st.session_state.get("narrative_refreshed_at"))
    narrative = live_narrative if has_live_narrative else csv_narrative
    data_source = "Live public-source cache" if (has_live_narrative or has_live_raw or has_live_attempt) else "Uploaded/local CSV or JSON"
    summary, details = aggregate_public_narratives(narrative, strength)
    if data_source == "Live public-source cache" and has_live_raw:
        all_items = live_raw_items.copy()
    else:
        all_items = normalize_loaded_narrative_items(narrative)

    source_count = int(details["url"].astype(str).nunique()) if not details.empty and "url" in details.columns else 0
    fresh_count = int(details["age_days"].le(14).sum()) if not details.empty and "age_days" in details.columns else 0
    supports = int(summary["narrative_vs_dashboard"].eq("Supports dashboard").sum()) if not summary.empty else 0
    conflicts = int(summary["narrative_vs_dashboard"].eq("Conflicts with dashboard").sum()) if not summary.empty else 0
    render_status_grid(
        [
            status_card("Narrative rows", len(details), f"{source_count} unique source links.", "info"),
            status_card("Fresh rows", fresh_count, "Items within the last 14 days.", "good" if fresh_count else "watch"),
            status_card("Supports dashboard", supports, "Narrative direction broadly aligns with signal-implied strength.", "good" if supports else "info"),
            status_card("Conflicts", conflicts, "Narrative direction conflicts with signal-implied strength.", "bad" if conflicts else "info"),
        ]
    )

    if st.session_state.get("narrative_refreshed_at"):
        st.caption(f"Last refreshed: {st.session_state['narrative_refreshed_at']} | Data source: {data_source}")
    else:
        st.caption(f"Data source: {data_source}")

    diagnostics = st.session_state.get("narrative_diagnostics", {})
    if data_source != "Live public-source cache" or not diagnostics:
        diagnostics = {
            "sources_configured": len(PUBLIC_NARRATIVE_SOURCE_REGISTRY),
            "sources_attempted": 0,
            "sources_successful": 0,
            "sources_failed": len(st.session_state.get("narrative_failures", [])),
            "items_fetched": len(narrative),
            "items_after_dedupe": len(all_items),
            "items_after_freshness_filter": int(all_items["age_days"].le(14).sum()) if not all_items.empty and "age_days" in all_items.columns else 0,
            "items_with_detected_currencies": int(all_items["detected_currencies"].astype(str).str.len().gt(0).sum()) if not all_items.empty and "detected_currencies" in all_items.columns else 0,
            "items_used_in_aggregation": int(to_bool_series(details["included_in_aggregation"]).sum()) if not details.empty and "included_in_aggregation" in details.columns else 0,
        }
    render_fetch_diagnostics(diagnostics, st.session_state.get("narrative_failures", []))

    if details.empty:
        st.info("No public narrative data loaded yet. Add a narrative CSV/JSON export or enable public-source fetching later.")
        if not all_items.empty:
            render_narrative_source_expanders(summary, details, all_items)
        with st.expander("Curated source registry", expanded=True):
            registry = pd.DataFrame(PUBLIC_NARRATIVE_SOURCE_REGISTRY)
            render_dataframe(registry[["source_name", "source_type", "coverage", "url", "feed_url", "fetch_enabled"]], height=420)
        return

    st.markdown("#### Currency narrative read")
    render_narrative_cards(summary)
    render_narrative_source_expanders(summary, details, all_items)

    failures = st.session_state.get("narrative_failures", [])
    if failures:
        with st.expander("Failed public sources from last refresh", expanded=False):
            render_dataframe(pd.DataFrame(failures), height=260)

    with st.expander("Curated source registry", expanded=False):
        registry = pd.DataFrame(PUBLIC_NARRATIVE_SOURCE_REGISTRY)
        render_dataframe(registry[["source_name", "source_type", "coverage", "url", "feed_url", "fetch_enabled"]], height=420)
    with st.expander("Technical details: narrative aggregation"):
        render_dataframe(summary, height=320)
    with st.expander("Technical details: raw narrative rows"):
        render_dataframe(details.drop(columns=[col for col in ["published_dt"] if col in details.columns]), height=460)


def main() -> None:
    inject_css()
    st.sidebar.title("Macro FX")
    st.sidebar.caption("Upload the latest ZIP exported by the Colab notebook.")
    frames = load_frames()
    missing_files_panel(frames)

    st.title("Macro FX Cockpit")
    st.markdown(
        f'<div class="subtle">{APP_VERSION} - US/USD-led FX backdrop, signal-implied currency strength, relative FX bias, public narrative context and data quality.</div>',
        unsafe_allow_html=True,
    )

    if not frames:
        st.warning("Upload the ZIP file from the final Colab export in the left sidebar.")
        st.stop()

    tab_overview, tab_currencies, tab_pairs, tab_regime, tab_narrative, tab_data = st.tabs(
        ["Overview", "Currencies", "Pairs", "Regime", "Narrative Monitor", "Data Quality"]
    )

    with tab_overview:
        overview_view(frames)
    with tab_currencies:
        currencies_view(frames)
    with tab_pairs:
        pairs_view(frames)
    with tab_regime:
        regime_view(frames)
    with tab_narrative:
        narrative_monitor_view(frames)
    with tab_data:
        data_quality_view(frames)


if __name__ == "__main__":
    main()
