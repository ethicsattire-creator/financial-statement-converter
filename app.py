
import io, re
import streamlit as st
import pdfplumber
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import mm

st.set_page_config(page_title="Comparative Vertical Financial Statement Converter", layout="wide")
st.title("Financial Statement Converter — V5 — P&L Fix + Address Header")
st.caption("Upload two years of horizontal financial statements, review accounting classifications, and generate a comparative vertical-format PDF. Missing figures are never invented.")

PL_HEADS = ["Revenue from operations","Other Income","Cost of goods sold","Employee benefits expense",
            "Finance costs","Depreciation and amortization expense","Other expenses"]
BS_HEADS = ["Owners' Capital Account","Reserves and surplus","Long-term borrowings","Deferred tax liabilities (Net)",
            "Other long-term liabilities","Long-term provisions","Short-term borrowings","Trade payables",
            "Other current liabilities","Short-term provisions","Property, Plant and Equipment","Intangible assets",
            "Capital work in progress","Intangible asset under development","Non-current investments",
            "Deferred tax assets (Net)","Long Term Loans and Advances","Other non-current assets","Current investments",
            "Inventories","Trade receivables","Cash and bank balances","Short Term Loans and Advances","Other current assets"]

PL_RULES = {
 "Employee benefits expense":["salary","salaries","wages","bonus","staff welfare","workmen"],
 "Finance costs":["interest","finance"],
 "Depreciation and amortization expense":["depreciation","amort"],
 "Other expenses":["bank exp","rent","travelling","travel","conveyance","sales promotion","printing","stationery",
                   "telephone","festival","petrol","insurance","audit","vepori","accounting","labour","bardana",
                   "out station","loading","unloading"]
}
BS_RULES = {
 "Owners' Capital Account":["capital account"],
 "Long-term borrowings":["car loan","term loan"],
 "Trade payables":["sundry creditors","creditors"],
 "Short-term provisions":["provision"],
 "Property, Plant and Equipment":["fixed assets","land","plant","machinery","vehicle"],
 "Trade receivables":["sundry debtors","debtors"],
 "Cash and bank balances":["cash in hand","cash at bank","bank balance"],
 "Current investments":["fdr","fixed deposit"],
 "Short Term Loans and Advances":["loans and advances"]
}

def text(upload):
    with pdfplumber.open(io.BytesIO(upload.getvalue())) as p:
        return "\n".join((x.extract_text() or "") for x in p.pages)

def amt(s): return float(s.replace(",",""))

def classify(name, rules, default):
    n=name.lower()
    for h, keys in rules.items():
        if any(k in n for k in keys): return h
    return default

def year_from(t):
    m=re.search(r"31(?:st)?\s+March\s+(20\d{2})",t,re.I)
    return m.group(1) if m else ""

def address_from(*texts):
    """Best-effort extraction of the entity address printed below the firm name.
    Stops before statement titles / accounting headings. User can edit before export.
    """
    stop = re.compile(r"(profit\s*(?:&|and)\s*loss|trading\s*(?:a/c|account)|balance\s*sheet|statement of|particulars|year ending|year ended|as at)", re.I)
    for t in texts:
        lines=[" ".join(x.split()).strip() for x in t.splitlines() if x.strip()]
        # Address usually follows the first entity-name line near the top.
        for i,line in enumerate(lines[:12]):
            if re.search(r"(?:M/S\.?|PVT\.?\s*LTD|LIMITED|LLP|TRADERS|ENTERPRISES|ENTERPRISE|FIRM|CO\.?)", line, re.I):
                cand=[]
                for nxt in lines[i+1:i+4]:
                    if stop.search(nxt): break
                    # Avoid numeric account/table rows; retain normal postal address lines.
                    if re.search(r"[A-Za-z]", nxt) and not re.match(r"^(amount|note|debit|credit)$", nxt, re.I):
                        cand.append(nxt)
                if cand:
                    return ", ".join(cand)
    return ""

def _money(s):
    try: return amt(s)
    except: return None

def _clean_ledger(s):
    return re.sub(r"\s+", " ", s).strip(" :-")

def parse_pl(t):
    """Parse horizontal Trading/P&L without merging debit and credit columns.
    Handles extracted lines such as 'To Purchases 1,000 By Sales 1,200' and
    excludes balancing figures (Gross/Net Profit/Loss) from expense/income totals.
    """
    rows=[]
    seen=set()
    money=r"[\d,]+(?:\.\d{1,2})?"

    def add(name, value, head):
        name=_clean_ledger(name)
        v=_money(value) if isinstance(value,str) else value
        if v is None: return
        key=(name.lower(), round(v,2), head)
        if key not in seen:
            rows.append({"Source ledger":name,"Amount":v,"Vertical head":head})
            seen.add(key)

    # Work line-by-line and split a horizontal row at the credit-side 'By'.
    for raw in t.splitlines():
        line=" ".join(raw.split())
        if not line: continue
        parts=re.split(r"\s+By\s+", line, maxsplit=1, flags=re.I)
        debit=parts[0]
        credit=parts[1] if len(parts)>1 else ""

        # Debit side: To <ledger> <amount>
        md=re.search(r"(?:^|\s)To\s+(.+?)\s+(%s)(?:\s|$)" % money, debit, re.I)
        if md:
            name,val=md.groups(); low=name.lower()
            if not any(x in low for x in ["gross profit","gross loss","net profit","net loss","total"]):
                head="Cost of goods sold" if any(x in low for x in ["purchase","opening stock","loading","unloading","freight inward","carriage inward","direct expense"]) else classify(name,PL_RULES,"Other expenses")
                add(name,val,head)

        # Credit side: By <ledger> <amount>. Only genuine revenue/income is included.
        if credit:
            mc=re.match(r"(.+?)\s+(%s)(?:\s|$)" % money, credit, re.I)
            if mc:
                name,val=mc.groups(); low=name.lower()
                if not any(x in low for x in ["gross profit","gross loss","net profit","net loss","closing stock","total"]):
                    head="Revenue from operations" if any(x in low for x in ["sales","sale","turnover","revenue from operations"]) else "Other Income"
                    add(name,val,head)

    # Fallback for PDFs where Trading Account is extracted without To/By prefixes.
    # Anchor labels to their own amount only; never consume the amount from the opposite column.
    if not any(r["Vertical head"]=="Revenue from operations" for r in rows):
        for m in re.finditer(r"(?:^|\n)\s*(?:By\s+)?(Sales|Revenue from operations|Turnover)\s+(%s)" % money,t,re.I):
            add(m.group(1),m.group(2),"Revenue from operations")
    if not any(r["Vertical head"]=="Cost of goods sold" and "purchase" in r["Source ledger"].lower() for r in rows):
        for m in re.finditer(r"(?:^|\n)\s*(?:To\s+)?(Purchases?)\s+(%s)" % money,t,re.I):
            add(m.group(1),m.group(2),"Cost of goods sold")
    return rows

def source_net_profit(t):
    """Return explicit source Net Profit/Loss where extractable."""
    money=r"[\d,]+(?:\.\d{1,2})?"
    # Prefer debit-side Net Profit (normal profitable P&L); loss is negative.
    m=re.search(r"(?:^|\n).*?To\s+Net\s+Profit(?:[^\d\n]*)(%s)" % money,t,re.I)
    if m:return _money(m.group(1))
    m=re.search(r"(?:^|\n).*?By\s+Net\s+Loss(?:[^\d\n]*)(%s)" % money,t,re.I)
    if m:return -_money(m.group(1))
    return None

def parse_bs(t):
    known=["Capital Account","PNB CAR LOAN","Other Provision","Sundry Creditors Others","Fixed Assets",
           "Cash in Hand","Sundry Debtors Others","PNB FDR","Cash at Bank","Land Agriculter jogiender hp","Loans and Advances"]
    rows=[]
    for name in known:
        m=re.search(re.escape(name)+r"\s+([\d,]+(?:\.\d{1,2})?)",t,re.I)
        if m: rows.append({"Source ledger":name,"Amount":amt(m.group(1)),"Vertical head":classify(name,BS_RULES,"Other current assets")})
    return rows

def aggregate(rows, heads):
    d={h:0.0 for h in heads}
    for r in rows: d[r["Vertical head"]]+=r["Amount"]
    return d

def fmt(x): return f"{x:,.2f}"

def pdf(entity, address, cy, py, cpl, ppl, cbs, pbs, warnings):
    out=io.BytesIO()
    doc=SimpleDocTemplate(out,pagesize=A4,rightMargin=11*mm,leftMargin=11*mm,topMargin=12*mm,bottomMargin=12*mm)
    styles=getSampleStyleSheet()
    title=ParagraphStyle("t",parent=styles["Heading2"],alignment=TA_CENTER,fontSize=11,leading=13,spaceAfter=3)
    note=ParagraphStyle("n",parent=styles["BodyText"],fontSize=7.5,leading=9)
    story=[Paragraph(entity,title)]
    if address.strip(): story.append(Paragraph(address.strip(), ParagraphStyle("addr",parent=styles["BodyText"],alignment=TA_CENTER,fontSize=8.5,leading=10,spaceAfter=3)))
    story += [Paragraph(f"Statement of Profit and Loss for the year ended 31 March {cy}",title),Spacer(1,4)]
    ca,pa=aggregate(cpl,PL_HEADS),aggregate(ppl,PL_HEADS)
    ti=lambda a:a["Revenue from operations"]+a["Other Income"]
    te=lambda a:sum(a[h] for h in ["Cost of goods sold","Employee benefits expense","Finance costs","Depreciation and amortization expense","Other expenses"])
    p=lambda a:ti(a)-te(a)
    pdata=[["Particulars","Note",f"31 March {cy}",f"31 March {py}"],
           ["Revenue from operations","19",fmt(ca["Revenue from operations"]),fmt(pa["Revenue from operations"])],
           ["Other Income","20",fmt(ca["Other Income"]),fmt(pa["Other Income"])],
           ["Total Income (I+II)","",fmt(ti(ca)),fmt(ti(pa))],
           ["Expenses:","","",""],
           ["Cost of goods sold","21",fmt(ca["Cost of goods sold"]),fmt(pa["Cost of goods sold"])],
           ["Employee benefits expense","22",fmt(ca["Employee benefits expense"]),fmt(pa["Employee benefits expense"])],
           ["Finance costs","23",fmt(ca["Finance costs"]),fmt(pa["Finance costs"])],
           ["Depreciation and amortization expense","24",fmt(ca["Depreciation and amortization expense"]),fmt(pa["Depreciation and amortization expense"])],
           ["Other expenses","25",fmt(ca["Other expenses"]),fmt(pa["Other expenses"])],
           ["Total expenses","",fmt(te(ca)),fmt(te(pa))],
           ["Profit/(loss) before tax","",fmt(p(ca)),fmt(p(pa))],
           ["Profit/(Loss) for the year","",fmt(p(ca)),fmt(p(pa))]]
    t=Table(pdata,colWidths=[96*mm,15*mm,36*mm,36*mm],repeatRows=1)
    t.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.35,colors.black),("BACKGROUND",(0,0),(-1,0),colors.lightgrey),
                           ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTNAME",(0,3),(-1,3),"Helvetica-Bold"),
                           ("FONTNAME",(0,10),(-1,-1),"Helvetica-Bold"),("ALIGN",(1,0),(-1,-1),"RIGHT"),
                           ("FONTSIZE",(0,0),(-1,-1),7.7),("VALIGN",(0,0),(-1,-1),"TOP")]))
    story += [t,Spacer(1,7)]
    for w in warnings: story.append(Paragraph("• "+w,note))
    story += [PageBreak(),Paragraph(entity,title)]
    if address.strip(): story.append(Paragraph(address.strip(), ParagraphStyle("addr2",parent=styles["BodyText"],alignment=TA_CENTER,fontSize=8.5,leading=10,spaceAfter=3)))
    story += [Paragraph(f"Balance Sheet as at 31 March {cy}",title),Spacer(1,4)]
    cb,pb=aggregate(cbs,BS_HEADS),aggregate(pbs,BS_HEADS)
    notes={"Owners' Capital Account":"3","Reserves and surplus":"4","Long-term borrowings":"5","Short-term borrowings":"5",
           "Deferred tax liabilities (Net)":"6","Deferred tax assets (Net)":"6","Other long-term liabilities":"7",
           "Long-term provisions":"8","Short-term provisions":"8","Trade payables":"9","Other current liabilities":"10",
           "Property, Plant and Equipment":"11","Intangible assets":"11","Capital work in progress":"11",
           "Intangible asset under development":"11","Non-current investments":"12","Current investments":"12",
           "Long Term Loans and Advances":"13","Short Term Loans and Advances":"13","Other non-current assets":"14",
           "Inventories":"15","Trade receivables":"16","Cash and bank balances":"17","Other current assets":"18"}
    liab=BS_HEADS[:10]; assets=BS_HEADS[10:]
    data=[["Particulars","Note",f"31 March {cy}",f"31 March {py}"],["EQUITY AND LIABILITIES","","",""]]
    for h in liab:data.append([h,notes.get(h,""),fmt(cb[h]),fmt(pb[h])])
    data.append(["Total","",fmt(sum(cb[h] for h in liab)),fmt(sum(pb[h] for h in liab))])
    data.append(["ASSETS","","",""])
    for h in assets:data.append([h,notes.get(h,""),fmt(cb[h]),fmt(pb[h])])
    data.append(["Total","",fmt(sum(cb[h] for h in assets)),fmt(sum(pb[h] for h in assets))])
    tb=Table(data,colWidths=[96*mm,15*mm,36*mm,36*mm],repeatRows=1)
    tb.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.35,colors.black),("BACKGROUND",(0,0),(-1,0),colors.lightgrey),
                            ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTNAME",(0,1),(-1,1),"Helvetica-Bold"),
                            ("FONTNAME",(0,len(liab)+3),(-1,len(liab)+3),"Helvetica-Bold"),
                            ("ALIGN",(1,0),(-1,-1),"RIGHT"),("FONTSIZE",(0,0),(-1,-1),7.5)]))
    story += [tb,PageBreak(),Paragraph("Source Ledger Mapping / Review Schedule",title)]
    m=[["Year","Statement","Source ledger","Vertical head","Amount"]]
    for yr,stname,rows in [(cy,"P&L",cpl),(py,"P&L",ppl),(cy,"Balance Sheet",cbs),(py,"Balance Sheet",pbs)]:
        for r in rows:m.append([yr,stname,r["Source ledger"],r["Vertical head"],fmt(r["Amount"])])
    mt=Table(m,colWidths=[17*mm,22*mm,52*mm,62*mm,30*mm],repeatRows=1)
    mt.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.25,colors.grey),("BACKGROUND",(0,0),(-1,0),colors.lightgrey),
                            ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),6.8),
                            ("VALIGN",(0,0),(-1,-1),"TOP"),("ALIGN",(-1,1),(-1,-1),"RIGHT")]))
    story.append(mt); doc.build(story); out.seek(0); return out.getvalue()

cplf=st.file_uploader("Current-year P&L / Trading PDF",type=["pdf"])
cbsf=st.file_uploader("Current-year Balance Sheet PDF",type=["pdf"])
pplf=st.file_uploader("Previous-year P&L / Trading PDF",type=["pdf"])
pbsf=st.file_uploader("Previous-year Balance Sheet PDF",type=["pdf"])
entity=st.text_input("Entity name",value="M/S DEV BHUMI APPLE TRADERS")
address=st.text_input("Entity address",value="B-10, FLAT NO-9, SECTOR-18, ROHINI, DELHI", help="Editable. For other clients, replace this with the address appearing in the uploaded statements.")

if all([cplf,cbsf,pplf,pbsf]):
    ct,bt,pt,pbt=map(text,[cplf,cbsf,pplf,pbsf])
    detected_address=address_from(ct,bt,pt,pbt)
    if detected_address and detected_address.lower() != address.strip().lower():
        st.info(f"Address detected in uploaded statements: {detected_address}. Edit the Entity address field above if required.")
    cy=year_from(ct) or year_from(bt) or "Current"
    py=year_from(pt) or year_from(pbt) or "Previous"
    cpl,ppl,cbs,pbs=parse_pl(ct),parse_pl(pt),parse_bs(bt),parse_bs(pbt)
    warnings=[]
    # Hard accounting control: compare computed vertical profit with source Net Profit where available.
    def computed_profit(rows):
        a=aggregate(rows,PL_HEADS)
        income=a["Revenue from operations"]+a["Other Income"]
        expenses=sum(a[h] for h in ["Cost of goods sold","Employee benefits expense","Finance costs","Depreciation and amortization expense","Other expenses"])
        return income-expenses
    for yr,txt,rows in [(cy,ct,cpl),(py,pt,ppl)]:
        snp=source_net_profit(txt)
        if snp is not None and abs(computed_profit(rows)-snp)>1.0:
            warnings.append(f"{yr}: P&L DOES NOT RECONCILE — REVIEW REQUIRED. Computed profit ₹{computed_profit(rows):,.2f} differs from source Net Profit ₹{snp:,.2f}.")
    if not any(r["Vertical head"]=="Revenue from operations" for r in cpl):
        warnings.append(f"{cy}: Trading Account / Sales is not present in the uploaded current-year P&L, so Revenue from Operations and Cost of Goods Sold remain incomplete. Upload the current-year Trading Account for a final statutory-format P&L.")
    warnings += ["Review car-loan maturity before deciding long-term vs short-term borrowing.",
                 "Review FDR maturity, loans/advances tenure, and agricultural land classification before finalisation."]
    st.subheader("Review classifications")
    for label,rows,heads,prefix in [("Current P&L",cpl,PL_HEADS,"cp"),("Previous P&L",ppl,PL_HEADS,"pp"),
                                    ("Current Balance Sheet",cbs,BS_HEADS,"cb"),("Previous Balance Sheet",pbs,BS_HEADS,"pb")]:
        with st.expander(label,expanded=False):
            for i,r in enumerate(rows):
                a,b,c=st.columns([3,2,4]); a.write(r["Source ledger"]); b.write(f"₹{r['Amount']:,.2f}")
                r["Vertical head"]=c.selectbox("Head",heads,index=heads.index(r["Vertical head"]),key=f"{prefix}{i}",label_visibility="collapsed")
    for w in warnings: st.warning(w)
    data=pdf(entity,address,cy,py,cpl,ppl,cbs,pbs,warnings)
    st.download_button("Generate comparative vertical PDF (review before finalisation)",data=data,file_name=f"{entity.replace(' ','_')}_comparative_vertical.pdf",mime="application/pdf")
else:
    st.info("Upload all four PDFs to create the comparative vertical statements.")
