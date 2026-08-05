# Print Bleed Tool

This is the flat GitHub upload version. There are no required subfolders.

Upload every file in this package directly to the top level of your GitHub repository.

## Streamlit deployment settings

- Repository: your `print-bleed-tool` repository
- Branch: `main`
- Main file path: `app.py`
- Python version: `3.12`

Important: Python cannot be changed on an existing Streamlit Community Cloud deployment.
If the app was deployed with Python 3.14, delete that Streamlit deployment and create it
again. During deployment, open **Advanced settings** and choose Python 3.12.

## Files required at the GitHub repository root

```text
app.py
analyzer.py
bleed.py
bleed_cli.py
document.py
exporter.py
models.py
preview.py
requirements.txt
README.md
DEPLOY_INSTRUCTIONS.txt
LICENSE
.gitignore
```

## Local run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```
