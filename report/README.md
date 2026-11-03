# Combined taxi-system laboratory report

`taxi_labs_report.tex` is the main English LaTeX document. Its compiled PDF is
**five pages, including figures and references**. The two-column, Times-style
layout follows the supplied example; it uses standard LaTeX packages and does
not require a separately downloaded IEEE class. Author details follow the example.

## Compile locally

From this directory, with a standard TeX Live/MiKTeX installation:

```bash
pdflatex taxi_labs_report.tex
pdflatex taxi_labs_report.tex
```

Or use `latexmk -pdf taxi_labs_report.tex`. The second pass resolves figure,
table, equation and bibliography references. Keep the `figures` directory next
to the main `.tex` file. No BibTeX database, shell escape or network access is
needed to compile the report.

## Overleaf

Create a new project using **Upload Project**, select
`taxi_labs_report_latex.zip`, and choose `taxi_labs_report.tex` as the main
document if it is not selected automatically. Compile with pdfLaTeX.

## Numerical provenance

The report uses the existing, verified outputs of the two laboratories:

- 35 daily runs: seven configurations, five replications each, seeds 1000--1004;
- 100 stationary production runs in five screened configurations, plus 18 pilots
  across six configurations; overload has no reported stationary confidence interval;
- 300 M/M/1 coverage experiments, each with 20 replications of 3000 customers.

The CSV copies in `data/` freeze the inputs used for figures and numerical
cross-checks. They match the corresponding repository outputs at revision
`c5a61be05921b8d721e0eb51094bb882efac37c4` (the removal of automatic runtime report
generation does not change those numerical methods or data).

To rebuild the vector figures from these snapshots:

```bash
python3 generate_figures.py
```

That optional command requires NumPy, pandas and matplotlib. It does not run
simulations, create a narrative report or modify the laboratory programs.
The frozen package versions for the stationary simulation are recorded in
`data/lab2_configuration.json`.

## Reading the statistics

The first-laboratory figure shows sample standard deviations across five runs,
not confidence intervals. Its boarding-conditioned waiting means and backlogs
are identified explicitly. The second-laboratory intervals use independent
replication means after pilot-selected deletion and complete arrival-cohort
follow-up. Their nominal level, heuristic screening limitations, and distinction
between precision and bias are stated in the report.
