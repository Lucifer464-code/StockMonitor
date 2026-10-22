# Stock Monitor

A light, mobile-friendly Streamlit page listing, for US and Indian stocks:

- **Near 52w high (PTH):** within 5% of the 52-week high
- **All-time high (ATH):** within 5% of the all-time high
- **Fallen, stabilising:** down 80–90% from the 52-week high, with no new low in the last 10 sessions

A batch job (`highs_data.py`) computes the lists and writes the Google Sheet tabs
`H&L US` and `H&L India`. The app (`app.py`) only reads those tabs.

## Setup

```
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
```

Both the job and the app need a Google service account with edit access to the sheet:

- the job reads `service_account.json` in the repo root;
- the app reads the `[GOOGLE_SERVICE_ACCOUNT]` block in `.streamlit/secrets.toml`.

Neither file is committed.

## Run the job

```
.venv/Scripts/python.exe highs_data.py
```

It prices every stock from one settled session and rewrites both tabs. In
production it is launched by `run_all.py` in the Data Bot repo, after `stocks_data.py`.

## Run the app locally

```
.venv/Scripts/python.exe -m streamlit run app.py
```

The app is open, with no login. Sheet reads are cached for 30 minutes.

## Tests

```
.venv/Scripts/python.exe -m pytest -q
```

## Deploy to Streamlit Community Cloud

1. In Streamlit Cloud, create an app from the repo `Lucifer464-code/StockMonitor`,
   with main file `app.py`.
2. In the app's **Settings → Secrets**, paste the `[GOOGLE_SERVICE_ACCOUNT]` block
   from your local `.streamlit/secrets.toml`.
3. Deploy. The theme comes from `.streamlit/config.toml`.
