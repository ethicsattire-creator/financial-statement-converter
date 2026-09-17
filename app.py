
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
st.title("Financial Statement Converter — Production Prototype")
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

def parse_pl(t):
    rows=[]
    # Trading account values
    for label, head in [("Sales","Revenue from operations"),("Purchases","Cost of goods sold"),
                        ("Loading and unLoading Expenses","Cost of goods sold")]:
        m=re.search(r"(?:To|By)\s+"+re.escape(label)+r"\s+([\d,]+(?:\.\d{1,2})?)",t,re.I)
        if m: rows.append({"Source ledger":label,"Amount":amt(m.group(1)),"Vertical head":head})
    # P&L debit-side expenses
    for line in t.splitlines():
        line=" ".join(line.split())
        m=re.match(r"^To\s+(.+?)\s+([\d,]+(?:\.\d{1,2})?)$",line,re.I)
        if m:
            name, val=m.groups()
            if name.lower() in ["purchases","gross profit","net profit","net loss","loading and unloading expenses"]: continue
            rows.append({"Source ledger":name,"Amount":amt(val),"Vertical head":classify(name,PL_RULES,"Other expenses")})
    return rows

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

def pdf(entity, cy, py, cpl, ppl, cbs, pbs, warnings):
    out=io.BytesIO()
    doc=SimpleDocTemplate(out,pagesize=A4,rightMargin=11*mm,leftMargin=11*mm,topMargin=12*mm,bottomMargin=12*mm)
    styles=getSampleStyleSheet()
    title=ParagraphStyle("t",parent=styles["Heading2"],alignment=TA_CENTER,fontSize=11,leading=13,spaceAfter=3)
    note=ParagraphStyle("n",parent=styles["BodyText"],fontSize=7.5,leading=9)
    story=[Paragraph(entity,title),Paragraph(f"Statement of Profit and Loss for the year ended 31 March {cy}",title),Spacer(1,4)]
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
    story += [PageBreak(),Paragraph(entity,title),Paragraph(f"Balance Sheet as at 31 March {cy}",title),Spacer(1,4)]
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

if all([cplf,cbsf,pplf,pbsf]):
    ct,bt,pt,pbt=map(text,[cplf,cbsf,pplf,pbsf])
    cy=year_from(ct) or year_from(bt) or "Current"
    py=year_from(pt) or year_from(pbt) or "Previous"
    cpl,ppl,cbs,pbs=parse_pl(ct),parse_pl(pt),parse_bs(bt),parse_bs(pbt)
    warnings=[]
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
    data=pdf(entity,cy,py,cpl,ppl,cbs,pbs,warnings)
    st.download_button("Generate comparative vertical PDF",data=data,file_name=f"{entity.replace(' ','_')}_comparative_vertical.pdf",mime="application/pdf")
else:
    st.info("Upload all four PDFs to create the comparative vertical statements.")
