# Taxi-System Simulation — Instructions for Reproducing Both Laboratories

This submission contains a taxi-system simulator and the statistical procedures
used to analyse its output. The instructions below work with the five Python
files alone: no input datasets, previously generated CSV files, notebooks,
LaTeX files or repository configuration are required.

## 1. Files to keep together

Place the following files in the same directory:

```text
taxi_labs/
├── README.md
├── taxi_simulation_v3.py
├── stationary_analysis.py
├── taxi_stationary_lab.py
├── test_taxi_simulation.py
└── test_stationary_analysis.py
```

| File | Purpose |
| --- | --- |
| `taxi_simulation_v3.py` | Shared simulator and executable entry point for Laboratory 1. |
| `stationary_analysis.py` | Online warm-up detection, independent-replication confidence intervals and reference-model validation. Imported by Laboratory 2. |
| `taxi_stationary_lab.py` | Executable entry point for Laboratory 2: runs the parameter study and saves numerical results and a figure. |
| `test_taxi_simulation.py` | Tests of the simulator, time ordering, metrics and physical constraints. |
| `test_stationary_analysis.py` | Tests of transient detection, confidence intervals and the measurement procedure. |

The first three Python files are needed for the experiments; the two test files
allow the implementation checks to be reproduced. `stationary_analysis.py` is
an imported module and does not need to be executed separately.

## 2. Python and dependencies

Use **Python 3.12**. The reference results were obtained with Python 3.12.14
and the package versions below. From a terminal, open the directory containing
the five files and install:

```bash
python -m pip install numpy==2.3.5 pandas==2.2.3 scipy==1.17.0 matplotlib==3.10.8
```

Use `python3` instead of `python` if that is the command provided by your system.
An optional virtual environment can be used. `unittest` is included in Python;
no separate testing package is needed. A `requirements.txt` file is not needed
when using the installation command above.

All subsequent terminal commands must be run from the directory containing the
five Python files. The experiments run on a CPU; a GPU and a graphical desktop
are not required.

## 3. Check the implementation

Run all tests:

```bash
python -B -m unittest -v
```

The supplied version contains **39 tests**. A successful run ends with:

```text
Ran 39 tests in ...s

OK
```

The tests exercise the implementation; they do not establish that its illustrative
parameters are calibrated to a real city or prove that a warm-up decision is correct.

## 4. Laboratory 1 — Daily taxi-system scenarios

Run:

```bash
python -B taxi_simulation_v3.py
```

The script first runs its built-in sanity checks and then executes **seven
24-hour scenarios with five replications each**, using seeds 1000–1004. It prints
`Sanity checks passed.` and the scenario summary when execution completes.

Two CSV files are created in the current working directory:

| Output file | Contents |
| --- | --- |
| `taxi_simulation_v3_results.csv` | 35 rows: one row for each scenario/replication, with passenger and fleet KPIs. |
| `taxi_simulation_v3_summary.csv` | Seven scenario summaries, including the actual replication count and sample standard deviations. |

The scenarios are:

- **Baseline + hubs:** Wednesday demand, 40 taxis, station and airport enabled,
  and fleet rebalancing enabled. Wednesday is an illustrative ordinary weekday,
  not an observation of a real calendar date.
- **No station/airport bursts:** the *No hubs* case in the report. Both hubs,
  their dedicated stands, hub-bound urban destinations and local congestion
  effects are disabled. Eight ordinary stands remain, rather than ten.
- **Heavy rain — demand only:** rain increases urban demand by 35%, with no
  weather-related speed reduction.
- **Heavy rain — demand + slower taxis:** the same generated requests as the
  demand-only rain case, with a 30% weather-related speed reduction.
- **Public transport strike:** reduced public-transport availability affects
  demand and vehicle speed.
- **Phased large evening event:** directional inbound and outbound event demand.
- **Combined stress:** Friday demand, heavy rain, a strike and the event together.

The daily means of app and stand waiting use passengers who have boarded,
including those still travelling. Walking means include everyone who reached a
stand. Backlogs and observed lower-bound means are reported separately; an
unfinished journey is not automatically an abandoned request. Columns ending
in `_std` are **sample standard deviations**, not confidence intervals.

Running this command again replaces the two CSV files in the working directory.
To preserve a previous experiment, copy its outputs before rerunning or execute
the script by its full path from another working directory.

## 5. Laboratory 2 — Transient detection and confidence intervals

Run the complete study:

```bash
python -B taxi_stationary_lab.py --output-dir lab2_results
```

This is a separate **constant-input** study. Time-of-day effects, scheduled hubs,
events, temporary transit disruptions and periodic rebalancing are disabled.
The stationary-input baseline uses 20 taxis and an urban arrival rate of 20 users
per hour. It is distinct from the daily baseline in Laboratory 1.

The default study evaluates six configurations: baseline, fewer taxis, higher
demand, longer measurement, a shorter detector window, and overload. Three
pilots per configuration select the warm-up deletion time. For configurations
that pass screening, 20 new independent production replications estimate the
KPIs. Useful measurement lasts 24 hours, or 48 hours in the longer-measurement
case. The first ten and all twenty replications form two predeclared precision
comparisons. The script also performs 300 M/M/1 coverage-validation experiments.

Wait for the process to finish: the overload pilots may use their entire
96-hour **simulated** screening horizon. Simulated hours are not wall-clock hours.

### Generated files

All files below are written to `lab2_results/`:

| Output file | Contents |
| --- | --- |
| `confidence_intervals.csv` | Estimates, nominal confidence levels, interval limits, half-widths, sample sizes and measurement status. |
| `replications.csv` | Results of individual production replications. |
| `pilots.csv` | Pilot seeds, detection times and screening outcomes. |
| `detector_trace.csv` | Online detector observations and stability checks over time. |
| `coverage_validation.csv` | Empirical coverage on the analytically solvable M/M/1 reference queue. |
| `configuration.json` | Study parameters, seed configuration and relevant package versions. |
| `precision.png` | Parameter comparisons, confidence-interval precision and reference-model coverage. |

The program saves the figure directly; it does not open an interactive plot
window. **No Markdown report is generated.** Existing outputs in the chosen
directory are replaced; use a new `--output-dir` to preserve earlier results.

### Interpreting the results

In `confidence_intervals.csv`, `estimate` is a mean across replication-level
statistics; `lower` and `upper` are confidence-interval limits. `half_width`
measures estimated precision, and `n` is the number of replications used. For
app waiting, select `metric = mean_app_wait_min`; `n = 20` selects the full
production sample. The `n = 10` rows reuse the first ten replications.

With the reference defaults, the stationary baseline app-wait estimate is
approximately **6.524 minutes**, with a nominal 95% interval of **[6.300, 6.747]**.
The reference study produced 100 complete production replications across five
screened configurations and 18 pilots across all six configurations.

- `ok`: the specified fixed sample has complete, finite measurements.
- `warmup_not_detected`: at least one pilot did not detect stability within the
  maximum horizon. No steady-state interval is produced for that configuration.
  This is the expected reference outcome for `overload`, not a program crash.
- `incomplete_measurements`: the sample contains an incomplete arrival cohort
  or an undefined metric. Failed replications are not silently discarded.

The warm-up detector is a heuristic, not a proof of stationarity. The confidence
intervals use independent replication means, not supposedly independent
minute-by-minute observations. Arrivals during each measurement window are
followed to pickup while normal arrivals continue; a 48-hour follow-up limit
prevents unresolved customers from being silently omitted. Utilization is
measured only over the fixed useful observation window.

### Optional shorter execution check

To check the Laboratory 2 entry point with a smaller workload:

```bash
python -B taxi_stationary_lab.py --scenarios baseline --replications 2 --pilots 1 --pilot-hours 48 --coverage-trials 10 --output-dir lab2_smoke
```

This is an execution check only. Its reduced sample is **not** the experiment
used for the report. Use the complete-study command above to reproduce the
reported results. Available command-line options can be displayed with:

```bash
python taxi_stationary_lab.py --help
```

## 6. Reproducibility and Google Colab

The daily scenarios fix seeds 1000–1004. The stationary study uses root seed
20261025, with separate pilot and production seed families. The M/M/1 reference
validation uses seed 71023. Keep the supplied parameters and package versions
for comparison with the reference results; small numerical differences may
occur with other software versions.

For Google Colab, upload **all five Python files** to the same runtime directory.
Install the packages in a notebook cell using the installation command above
with `%pip install` instead of `python -m pip install`. Then prefix each execution
command with `!`, for example:

```python
!python -B -m unittest -v
!python -B taxi_simulation_v3.py
!python -B taxi_stationary_lab.py --output-dir lab2_results
```

The CSV files and `lab2_results/precision.png` can be opened or downloaded through
Colab's Files panel. The report PDF and previously generated results are not
required inputs for either laboratory.
