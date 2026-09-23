# GitHub + Streamlit deployment

## Recommended repository layout

```text
shower-drainage-comparator/
├── app.py
├── drainage_data.py
├── v2_excel_loader.py
├── requirements.txt
├── config/
│   ├── classification_rules.csv
│   └── length_rules.csv
└── data/
    ├── WEDI_FINAL_v2_TECHNICAL_LOCK.xlsx
    ├── VIEGA_...xlsx
    ├── GEBERIT_...xlsx
    └── ...
```

The web application reads manufacturer FINAL Excel masters directly. The large combined SQLite database is not part of this deployment.

## GitHub workflow

1. Put only canonical/current manufacturer masters intended for the app under `data/`.
2. Commit application code, `config/`, and the Excel masters to the repository.
3. Push to the branch used by Streamlit.
4. Streamlit rebuilds/restarts the application from that repository state.

Keep generated temporary files, local virtual environments, and Python caches out of Git.

## Streamlit

Create a Streamlit app from the repository and use `app.py` as the entrypoint. Install dependencies from `requirements.txt`.

If password protection in `app.py` is enabled, configure the expected secret/environment value in the deployment environment rather than committing credentials to GitHub.

## Adding or updating a manufacturer

For a normal data update no application code change should be required:

1. replace or add the manufacturer's canonical FINAL workbook in `data/`;
2. keep filenames stable where practical;
3. run `python -m unittest -v` locally;
4. start the app locally once and verify classification/data status;
5. commit and push.

The loader supports mixed legacy and v2 masters during the transition period.

## Performance

Workbook loading is cached with Streamlit `@st.cache_data`. A cold start must decode and consolidate the Excel masters once; subsequent reruns reuse the cached result until a workbook or configuration signature changes.

If the number/size of manufacturer masters later makes cold starts too slow, keep the Excel masters as source-of-truth and add a generated deployment cache as a separate build step. Do not change the canonical masters merely for UI performance.
