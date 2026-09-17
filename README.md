# Financial Statement Converter V3

## Use
Upload:
1. Current-year Profit & Loss / Trading Account PDF
2. Current-year Balance Sheet PDF
3. Previous-year Profit & Loss / Trading Account PDF
4. Previous-year Balance Sheet PDF

Review the automatically suggested vertical heads and generate the comparative PDF.

## Run locally
python -m pip install -r requirements.txt
streamlit run app.py

## Put it online with Streamlit Community Cloud
1. Create a GitHub repository.
2. Upload app.py and requirements.txt from this folder.
3. In Streamlit Community Cloud, create a new app from that repository.
4. Select app.py as the entry file and deploy.
5. Bookmark the resulting web-app URL.

## Accounting safeguards
- The review screen remains mandatory because source PDFs and ledger terminology vary.
- The application does not manufacture missing Sales, Purchases, stock, maturity, tenure, or classification information.
- Scanned/image-only PDFs require OCR support, which is not included in this build.
- Final accounts should be reviewed before signing/filing.
