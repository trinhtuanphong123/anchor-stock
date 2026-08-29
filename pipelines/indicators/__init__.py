"""pipelines.indicators — display-only technical indicators over ``daily_bars``.

Two modules, matching the split the rest of the repo already uses:

* :mod:`pipelines.indicators.compute` — pure numpy, no I/O, no storage imports.
* :mod:`pipelines.indicators.build`   — orchestration, records, CLI.

Nothing here is an input to the factor model, the similarity matrix, or anchor selection
(``docs/04`` §5). It exists so the dashboard has something to chart.
"""
