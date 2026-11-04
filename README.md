# Running the Taxi Laboratories on Google Colab

## 1. Upload the Python files

Open a new notebook at https://colab.research.google.com/.
Using the **Files** panel (folder icon), upload these five files to `/content`:

- `taxi_simulation_v3.py`
- `stationary_analysis.py`
- `taxi_stationary_lab.py`
- `test_taxi_simulation.py`
- `test_stationary_analysis.py`

## 2. Install the dependencies

Run this notebook cell:

```python
%pip install -q numpy==2.3.5 pandas==2.2.3 scipy==1.17.0 matplotlib==3.10.8
```

## 3. Run the tests and both laboratories

Run these cells in order and wait for each to finish:

```python
!python -B -m unittest -v
```

The supplied tests should finish with **39 tests** and **OK**.

```python
!python -B taxi_simulation_v3.py
!python -B taxi_stationary_lab.py --output-dir lab2_results
```

Laboratory 1 creates two CSV files in `/content`.
Laboratory 2 saves its CSV files, configuration and figure in `lab2_results/`.

## 4. Download the results

Run this cell to download all outputs in one ZIP file:

```python
!zip -qr results.zip taxi_simulation_v3_results.csv taxi_simulation_v3_summary.csv lab2_results
from google.colab import files
files.download("results.zip")
```
