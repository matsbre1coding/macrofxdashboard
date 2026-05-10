# Macro FX Cockpit

Erklaerbares Macro-Regime- und FX-Watchlist-Dashboard fuer Forex Research.

Kurz gesagt: Colab berechnet die Daten und exportiert eine ZIP. Streamlit zeigt diese ZIP als sauberes Cockpit mit Marktphase, Watchlist, Historie und Datenqualitaet.

## Dateien

- `macro_fx_regime_dashboard_colab_v1_3_1.ipynb` - aktuelle Google-Colab-Version mit Ensemble Decision Layer plus einfachem ZIP-Export fuer die Web-App.
- `macro_fx_regime_dashboard_colab_v1_3.ipynb` - Vorversion mit Ensemble Decision Layer, Semantic Regime Fit, Strategy Mode Snapshot und Current Signal Board.
- `macro_fx_regime_dashboard_colab_v1_2_1.ipynb` - Vorversion mit kalibriertem probabilistischem Regime-Layer, Driver-Table und konservativem Bayesian Confidence Overlay.
- `macro_fx_regime_dashboard_colab_v1_2.ipynb` - Vorversion mit probabilistischem Regime-Layer, Markov-Smoothing und Bayesian Confidence Overlay.
- `macro_fx_regime_dashboard_colab_v1_1.ipynb` - Vorversion mit finalem Baseline-Backtest, CPI-hardened OOS-Check und Current Policy OOS Decision.
- `macro_fx_regime_dashboard_colab_v1_0_fixed.ipynb` - Vorversion mit eingefrorenen Baseline-Regeln, Actionability-Labels und Currency Data Permissions.
- `macro_fx_regime_dashboard_colab_v0_9.ipynb` - Vorversion mit CPI Data Hardening.
- `macro_fx_regime_dashboard_colab_v0_8.ipynb` - Vorversion mit offizieller Source Registry und Bank-of-Canada-Primary-Source-Pilot.
- `macro_fx_regime_dashboard_colab_v0_7.ipynb` - stabile Vorversion mit Anti-Overfitting-/Out-of-Sample-Block.
- `macro_fx_regime_dashboard_colab.ipynb` - Basisversion / frueherer Stand.
- `streamlit_app.py` - interaktive Streamlit-App v1.6.1 Research Cockpit, die die CSV-Exports aus Colab als professionelles Macro-FX-Cockpit liest.
- `UX_BLUEPRINT_v1_3.md` - Produktstruktur und UX-Blueprint fuer das finale Dashboard.
- `requirements.txt` - minimale Python-Abhaengigkeiten fuer die Streamlit-App.

## Streamlit-App nutzen

1. v1.3.1 in Colab komplett ausfuehren.
2. Am Ende die erzeugte ZIP-Datei herunterladen.
3. Auf Streamlit Cloud die Dateien `streamlit_app.py` und `requirements.txt` hochladen oder ersetzen.
4. In der linken Seitenleiste der App die ZIP-Datei aus Colab hochladen.

Lokal geht es alternativ so:

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## App-Aufbau

- `Overview`: Marktphase, Daten-Gate, Currency Strength, FX-Bias-Heatmap und wichtigste Pair-Ideen.
- `Currencies`: relative Waehrungsstaerke plus Datenstatus pro Waehrung.
- `Pairs`: Watchlist, Kontext- und blockierte Pair-Ideen mit OOS- und CPI/Rates-Historie.
- `Regime`: Scorecard als primaere Marktphase, Markov/Bayes als Warn- und Confidence-Layer.
- `Data Quality`: Freshness, API-/Source-Luecken und warum Signale downgraded werden.

## v1.2 Ansatz

Der erste Datenkern bleibt bewusst robust: US-Macro/FRED fuer globale Makro- und USD-Faktoren plus ECB-FX-Daten fuer Major-Paare und Crosses.

Seit v0.2 arbeitet das Dashboard nicht mehr nur mit einzelnen USD-Paaren. Es baut einzelne Waehrungs-Scores fuer:

- USD
- EUR
- GBP
- JPY
- CHF
- CAD
- AUD
- NZD

Die erste Regime Engine ist eine transparente Scorecard:

- Growth Score
- Inflation Score
- Policy Score
- Risk Score
- Commodity Score
- USD Score

Die Currency-Strength-Engine kombiniert:

- Macro-Archetyp je Waehrung
- Basket-Momentum je Waehrung gegen alle anderen Waehrungen

Darauf basieren:

- globales Macro-Regime
- Currency Strength Ranking
- Pair Bias Matrix
- Top Macro Pair Expressions
- Validated Current Ideas
- Pair Validation Table
- USD Bias
- Risk-on/Risk-off Bias
- Pair Bias fuer Majors und Crosses wie CADJPY, EURJPY, AUDJPY, EURGBP, AUDCAD
- Signal-Backtest gegen 1M/3M/6M Forward Returns

Neu in v0.3 ist der Signal-Validation-Layer:

- historische Qualitaet pro Pair ueber 1M/3M/6M
- gewichtete Validation Scores
- Labels wie Strong, Watch, Mixed, Avoid und Contrarian / broken
- aktuelle Pair-Ideen werden nach historischer Signalqualitaet gefiltert

Neu in v0.3.1 ist die Signal-Hygiene:

- nur noch konventionelle Marktpaarungen statt inverse Duplikate
- keine doppelte Anzeige wie GBPJPY und JPYGBP gleichzeitig
- nicht-konventionelle Ideen wie CADEUR werden als EURCAD bearish bzw. Long CAD / Short EUR angezeigt
- Actionable Validated Ideas zeigen nur Strong/Watch-Ideen mit positivem validiertem Score
- Avoid und Contrarian / broken werden aus dem Actionable-Ranking herausgefiltert

Neu in v0.4 ist der Walk-forward-Portfolio-Backtest:

- Top-N Portfolio aus den staerksten konventionellen Pair-Biases
- 1M, 3M und 6M Halteperioden
- Rebalance-Termine werden fuer laengere Horizonte weiter auseinandergelegt, um Ueberlappung zu reduzieren
- einfache Round-trip-Kosten fuer Majors und Crosses
- Portfolio Summary mit Hit Rate, annualisiertem Return, Volatilitaet, Sharpe-Proxy und Max Drawdown
- Equity Curve und Trade-Export

Neu in v0.4.1 sind Diagnostics & Robustness:

- Priced-in Diagnostics: Pre-1M/Pre-3M Moves gegen spaetere Forward Returns
- Extreme-score Check: testen, ob sehr hohe Scores Trendfortsetzung oder Mean Reversion anzeigen
- Walk-forward Parameter Grid fuer Top 1/2/3 und Thresholds 0.6/0.8/1.0/1.2
- Pair Verdicts: Trend candidate, Watch, Priced-in risk, Avoid, Mixed / context
- Group Verdicts fuer USD majors, JPY crosses, CHF crosses und Commodity crosses

Neu in v0.4.2 ist der Fresh-Signal Filter:

- Vergleich von naivem Top-3-Portfolio gegen gefilterte Varianten
- `no_high_premove`: vermeidet Signale nach starkem 3M-Pre-Move
- `moderate_score`: vermeidet extreme Bias-Scores
- `fresh_moderate`: kombiniert Pre-Move- und Score-Filter
- `strict_fresh`: kleinere Top-N-Auswahl mit strengeren Frische-Filtern

Neu in v0.4.3 ist Strict-Fresh Attribution:

- Zerlegung des `strict_fresh`-Szenarios nach Pair
- Zerlegung nach Pair-Gruppe
- Jahresanalyse
- Regimeanalyse
- Attribution nach Horizon und Pair

Neu in v0.4.4 ist der Regime & Group Gate Test:

- einfache, wirtschaftlich begruendbare Gates statt feinoptimierter Regeln
- Regime-Gate fuer Crisis/Liquidity Stress, Reflation/Expansion und Goldilocks
- Gruppen-Gate fuer CHF crosses, USD majors und JPY crosses
- Kombination aus Regime- und Gruppen-Gate
- nicht erlaubte Perioden bleiben als Cash-Perioden mit 0% Return im Backtest

Neu in v0.5 ist die Strategy Mode Decision Layer:

- aktive Walk-forward-Kennzahlen wie `active_hit_rate`, `active_avg_return`, `active_periods` und `cash_periods`
- Strategy Snapshot fuer Macro Trend, Policy Divergence, Defensive/Liquidity und Mean Reversion Watch
- aktuelle strict-fresh Kandidaten werden mit Regime-Gate, Gruppen-Gate und historischem Pair Verdict verbunden
- klarere Trennung zwischen getesteter Macro-Trend-Strategie und noch nicht getesteten Research-Modi
- neue Exporte fuer Strategy Mode Dashboard, Decision Snapshot und Current Strategy Candidates

Neu in v0.6 ist der Country & Policy Divergence Layer:

- lokale Policy-/Rates-Daten pro Waehrung ueber FRED/OECD/Eurostat-nahe Reihen
- 3M-Rates, 10Y-Yields, CPI-YoY bzw. HICP/CPI-Index-YoY
- einfache Real-Rate-Proxies: Short Rate minus CPI-YoY und 10Y Yield minus CPI-YoY
- Cross-Sectional Policy Scores fuer USD, EUR, GBP, JPY, CHF, CAD, AUD und NZD
- Policy Pair Matrix und aktuelle Policy-Divergence-Ideen
- erster Backtest der Policy-Divergence-Pair-Biases gegen 1M/3M/6M Forward Returns
- Datenqualitaets-Label, damit alte CPI-Reihen nicht unbemerkt als frische Signale gelesen werden

Neu in v0.6.2 ist das Policy Data Quality Gate:

- stale CPI-Daten werden nicht als frische Real-Rate-Information behandelt
- zusaetzlicher `rates_only_policy_score` fuer frische Rate-Divergenz
- Trennung in `Real-rate clean`, `Rates-only clean` und `Rejected: stale rates`
- separate Tabellen fuer data-clean Policy-Ideen und verworfene Ideen

Neu in v0.7 ist der Anti-Overfitting-/Out-of-Sample-Block:

- feste Zeitsplits: 2000-2014 Development, 2015-2020 Validation, 2021-heute Out-of-Sample
- OOS-Robustheitscheck fuer rates-only Policy-Pairs
- eigener Walk-forward-Test fuer rates-only Policy-Divergence-Signale
- Split-Auswertung der Walk-forward-Performance, damit Gewinner nicht nur aus einer Marktphase stammen
- Exporte fuer OOS Summary, Pair Robustness, Current OOS Check und rates-only Walk-forward Trades

Neu in v0.8 ist das Official Data Source Upgrade:

- offizielle Source-Registry fuer USD, EUR, GBP, JPY, CHF, CAD, AUD und NZD
- klare Trennung zwischen FRED/OECD-Fallbacks, no-key Primaerquellen und API-Key-Quellen
- erster Primary-Source-Pilot ueber Bank of Canada Valet fuer CAD 3M Treasury Bill und CAD 10Y Benchmark Yield
- Freshness Audit pro Waehrung und Datenfeld: Short Rate, Long Rate, CPI YoY
- Upgrade-Priorisierung: OK for now, Upgrade now: no-key source, Needs API key / manual mapping
- Exporte fuer Source Registry, Primary Status, Override Log, Source Freshness Audit und Source Readiness

Neu in v0.9 ist CPI Data Hardening:

- no-key CPI-Overlay fuer CAD ueber Statistics Canada WDS / Vector `V41690973`
- no-key CPI-Overlay fuer GBP ueber ONS `D7G7`
- no-key offizieller CHF-HICP-Fallback ueber Eurostat, solange direktes FSO/SNB-CPI-Mapping noch offen ist
- CPI Overrides laufen auf die v0.8 Primary-Rate-Daten, also CAD-Rates bleiben verbessert
- Freshness-Vergleich vor/nach v0.9 zeigt, ob CPI-Daten von 2 auf bis zu 5 frische Felder steigen
- neue Exporte fuer CPI Primary Status, Override Log, Hardened Source Freshness Audit und aktuelle CPI-hardened Policy Ideas

Neu in v1.0 ist der Baseline Freeze:

- feste Regeln fuer Datenqualitaet, Signaltypen und Actionability
- AUD, NZD und JPY werden bei stale CPI nicht ausgeschlossen, sondern als rates-only Policy / Research behandelt
- Real-rate Policy ist nur erlaubt, wenn beide Waehrungen frische CPI-Daten haben
- Rates-only Policy bleibt erlaubt, wenn beide Waehrungen frische Rate-Daten haben
- HMM/Bayesian Layer ist explizit als spaetere zweite Meinung definiert, nicht als Ersatz fuer die Baseline
- neue Exporte fuer Freeze Summary, Freeze Rules, Currency Data Permissions und Current Frozen Policy Ideas

Neu in v1.1 ist der finale Baseline-Backtest:

- Vergleich der eingefrorenen Macro/Fresh-Signal-, Regime/Group-Gate-, rates-only Policy- und CPI-hardened Policy-Varianten
- CPI-hardened OOS Pair Robustness nach denselben festen Splits wie v0.7
- Final Baseline Decision mit Labels wie Baseline candidate, Watch / needs confirmation, In-sample only und Research only
- Current Policy OOS Decision verbindet aktuelle Freeze-Labels mit rates-only und CPI-hardened OOS-Historie
- Exporte fuer Final Baseline Dashboard, Summary, Split Summary, Decision und Current Policy OOS Decision

Neu in v1.2 ist der Probabilistic Regime Layer:

- HMM-lite/Markov-Smoothing als probabilistische zweite Meinung zur Scorecard
- Gaussian-Regime-Cluster auf Growth, Inflation, Policy, Risk, Commodity und USD Scores
- Markov-Transition-Matrix fuer Regime-Persistenz und Uebergangsrisiko
- Bayesian Regime Summary mit Confirmed, Soft confirmation, Mixed / uncertain oder Conflict
- Probability-adjusted Current Policy Context, ohne die v1.1-Baseline-Regeln zu ueberschreiben
- Exporte fuer Prob Regime Summary, Latest Regime Distribution, State Map, Transition Matrix und Prob Current Policy Context

Neu in v1.2.1 ist die Probabilistic Calibration:

- Probability Floor, Temperature-Smoothing und kleiner Scorecard-Prior gegen ueberharte 0%/100%-Reads
- Raw-vs-Calibrated Regime Distribution, damit Modell-Ueberzeugung und konservativer Decision-Layer getrennt sichtbar bleiben
- Regime Driver Table: aktuelle Macro-Scores gegen latente State-Durchschnitte
- Calibrated Current Policy Context, ohne die eingefrorene v1.1-Baseline zu veraendern
- Exporte fuer Calibrated Prob Regime Summary, Latest, Probabilities, Calibration Comparison, Driver Table und Calibrated Current Policy Context

Neu in v1.3 ist der Ensemble Decision Layer:

- Scorecard-Regime bleibt primaere Baseline, solange der probabilistische Layer semantisch nicht sauber bestaetigt wird
- Semantic Regime Fit prueft, ob Growth, Inflation, Policy, Risk, Commodity und USD wirklich zum Regime-Label passen
- probabilistische Crisis-Warnungen werden nur akzeptiert, wenn Growth/Risk-Treiber sie plausibel machen
- Strategy Mode Snapshot fasst Macro Trend, Policy Divergence, Defensive/Liquidity, Mean Reversion und Data Health zusammen
- Current Signal Board trennt Baseline Candidate, Research Watch, Context Watch und No Action
- Exporte fuer Ensemble Regime Dashboard, Driver Alignment, Latest Macro Scores, Strategy Dashboard und Current Signal Board

Neu in v1.4 ist die Streamlit UX:

- einfache Tabs: Heute, Watchlist, Marktphase, Historie und Datenqualitaet
- technische Begriffe werden in der App in klare Namen uebersetzt
- Rohdaten bleiben verfuegbar, aber nur in aufklappbaren Detailbereichen
- Signalstatus und Datenqualitaet stehen vor jeder Pair-Idee
- `UX_BLUEPRINT_v1_4.md` beschreibt den finalen App-Aufbau

v1.4.1 verbessert die Heute-Seite:

- Scorecard, Markov/Bayes-Warnung und Handlung werden direkt sichtbar
- Watchlist-Gruende sind einfacher formuliert
- Modusnamen sind nutzerfreundlicher

v1.5 ist der Product-UX-Umbau:

- Tabs heissen jetzt `Overview`, `Currencies`, `Pairs`, `Regime`, `Data Quality`
- Tabellen sind nicht mehr die Hauptansicht, sondern wandern in Details
- Overview zeigt Currency Strength, Relative FX Bias, Regime Confidence und Top Pair Ideas
- Currencies zeigt starke/schwache Waehrungen und Datenstatus
- Pairs zeigt Pair-Ideen als Ranking und Karten
- Regime zeigt Scorecard vs Markov/Bayesian als Confidence Layer
- Data Quality zeigt, welche Daten frisch oder veraltet sind und was verbessert werden muss

## Naechste sinnvolle Schritte

1. `streamlit_app.py` und `requirements.txt` in GitHub ersetzen.
2. Streamlit Cloud neu deployen lassen.
3. In der App die aktuelle Colab-ZIP hochladen.
4. Danach gemeinsam die Optik und die Informations-Hierarchie weiter schaerfen.
