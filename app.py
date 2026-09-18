
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
st.title("Financial Statement Converter — V9 — Manual Adjustments & Signatories")
st.caption("Upload current and previous-year P&L and Balance Sheet PDFs. Trading Account is optional for either year. Current/latest year is always shown first. Missing figures are never invented. Manual additions are separately identified and reconciled.")

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
    """Parse horizontal Trading/P&L accounts, including wrapped ledger rows.

    Important safeguards:
    - debit and credit sides are read separately;
    - Gross Profit / Net Profit are balancing figures, never expenses;
    - wrapped rows such as ``To Workmen and Staff Welfare`` followed by
      ``76,218.00`` are joined before classification;
    - Sales/Purchases are never double counted.
    """
    rows=[]
    seen=set()
    money=r"[\d,]+(?:\.\d{1,2})?"

    def add(name, value, head):
        name=_clean_ledger(name)
        v=_money(value) if isinstance(value,str) else value
        if v is None or not name: return
        key=(name.lower(), round(v,2), head)
        if key not in seen:
            rows.append({"Source ledger":name,"Amount":v,"Vertical head":head})
            seen.add(key)

    def debit_head(name):
        low=name.lower()
        if any(x in low for x in ["purchase","opening stock","loading","unloading","freight inward","carriage inward","direct expense"]):
            return "Cost of goods sold"
        return classify(name,PL_RULES,"Other expenses")

    def credit_head(name):
        low=name.lower()
        if any(x in low for x in ["sales","sale","turnover","revenue from operations"]):
            return "Revenue from operations"
        return "Other Income"

    lines=[" ".join(x.split()) for x in t.splitlines() if x.strip()]
    pending_debit=None
    pending_credit=None

    for line in lines:
        # Resolve a wrapped ledger from the preceding line when this line starts with its amount.
        if pending_debit:
            # Wrapped Tally rows often look like:
            #   To Workmen and Staff Welfare
            #   Expenses 76,218.00
            # The continuation may contain more ledger words before the amount.
            mm=re.match(r"^(.*?)(%s)(?:\s|$)" % money, line)
            if mm:
                continuation=_clean_ledger(mm.group(1))
                full_name=_clean_ledger(pending_debit + (" " + continuation if continuation else ""))
                low=full_name.lower()
                if not any(x in low for x in ["gross profit","gross loss","net profit","net loss","total"]):
                    add(full_name,mm.group(2),debit_head(full_name))
                pending_debit=None
        if pending_credit:
            mm=re.match(r"^(.*?)(%s)(?:\s|$)" % money, line)
            if mm:
                continuation=_clean_ledger(mm.group(1))
                full_name=_clean_ledger(pending_credit + (" " + continuation if continuation else ""))
                low=full_name.lower()
                if not any(x in low for x in ["gross profit","gross loss","net profit","net loss","closing stock","total"]):
                    add(full_name,mm.group(2),credit_head(full_name))
                pending_credit=None

        # Split a horizontal row at the credit-side By marker.
        parts=re.split(r"\s+By\s+", line, maxsplit=1, flags=re.I)
        debit=parts[0]
        credit=parts[1] if len(parts)>1 else ""

        # Debit: To <ledger> <amount>, or remember a wrapped ledger with no amount yet.
        md=re.search(r"(?:^|\s)To\s+(.+?)\s+(%s)(?:\s|$)" % money, debit, re.I)
        if md:
            name,val=md.groups(); low=name.lower()
            if not any(x in low for x in ["gross profit","gross loss","net profit","net loss","total"]):
                add(name,val,debit_head(name))
            pending_debit=None
        else:
            mn=re.search(r"(?:^|\s)To\s+(.+?)\s*$", debit, re.I)
            if mn:
                name=_clean_ledger(mn.group(1))
                if name and not re.search(r"particulars|amount",name,re.I): pending_debit=name

        # Credit: By <ledger> <amount>, or remember wrapped ledger.
        if credit:
            mc=re.match(r"(.+?)\s+(%s)(?:\s|$)" % money, credit, re.I)
            if mc:
                name,val=mc.groups(); low=name.lower()
                if not any(x in low for x in ["gross profit","gross loss","net profit","net loss","closing stock","total"]):
                    add(name,val,credit_head(name))
                pending_credit=None
            else:
                name=_clean_ledger(credit)
                if name: pending_credit=name

    # Fallback for extracted Trading Accounts without To/By prefixes.
    if not any(r["Vertical head"]=="Revenue from operations" for r in rows):
        for m in re.finditer(r"(?:^|\n)\s*(?:By\s+)?(Sales|Revenue from operations|Turnover)\s+(%s)" % money,t,re.I):
            add(m.group(1),m.group(2),"Revenue from operations")
    if not any(r["Vertical head"]=="Cost of goods sold" and "purchase" in r["Source ledger"].lower() for r in rows):
        for m in re.finditer(r"(?:^|\n)\s*(?:To\s+)?(Purchases?)\s+(%s)" % money,t,re.I):
            add(m.group(1),m.group(2),"Cost of goods sold")
    return rows

def source_gross_profit(t):
    money=r"[\d,]+(?:\.\d{1,2})?"
    m=re.search(r"By\s+Gross\s+Profit(?:[^\d\n]*)(%s)" % money,t,re.I)
    return _money(m.group(1)) if m else None

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

def pdf(entity, address, cy, py, cpl, ppl, cbs, pbs, warnings, c_source_profit=None, p_source_profit=None, c_has_trading=True, p_has_trading=True, sign=None):
    out=io.BytesIO()
    doc=SimpleDocTemplate(out,pagesize=A4,rightMargin=11*mm,leftMargin=11*mm,topMargin=12*mm,bottomMargin=12*mm)
    sign = sign or {}
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
    # When no separate Trading Account exists, Revenue/COGS may legitimately be unavailable.
    # In that case the face statement must not manufacture a loss from zero revenue;
    # use the explicit source Net Profit for the final profit line and mark unavailable
    # Revenue/COGS cells as N/A.
    def face_profit(a, source_profit, has_trading):
        return p(a) if has_trading else (source_profit if source_profit is not None else p(a))
    def cell(v, available=True):
        return fmt(v) if available else "N/A"
    pdata=[["Particulars","Note",f"31 March {cy}",f"31 March {py}"],
           ["Revenue from operations","19",cell(ca["Revenue from operations"],c_has_trading),cell(pa["Revenue from operations"],p_has_trading)],
           ["Other Income","20",fmt(ca["Other Income"]),fmt(pa["Other Income"])],
           ["Total Income (I+II)","",cell(ti(ca),c_has_trading),cell(ti(pa),p_has_trading)],
           ["Expenses:","","",""],
           ["Cost of goods sold","21",cell(ca["Cost of goods sold"],c_has_trading),cell(pa["Cost of goods sold"],p_has_trading)],
           ["Employee benefits expense","22",fmt(ca["Employee benefits expense"]),fmt(pa["Employee benefits expense"])],
           ["Finance costs","23",fmt(ca["Finance costs"]),fmt(pa["Finance costs"])],
           ["Depreciation and amortization expense","24",fmt(ca["Depreciation and amortization expense"]),fmt(pa["Depreciation and amortization expense"])],
           ["Other expenses","25",fmt(ca["Other expenses"]),fmt(pa["Other expenses"])],
           ["Total expenses","",cell(te(ca),c_has_trading),cell(te(pa),p_has_trading)],
           ["Profit/(loss) before tax","",fmt(face_profit(ca,c_source_profit,c_has_trading)),fmt(face_profit(pa,p_source_profit,p_has_trading))],
           ["Profit/(Loss) for the year","",fmt(face_profit(ca,c_source_profit,c_has_trading)),fmt(face_profit(pa,p_source_profit,p_has_trading))]]
    t=Table(pdata,colWidths=[96*mm,15*mm,36*mm,36*mm],repeatRows=1)
    t.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.35,colors.black),("BACKGROUND",(0,0),(-1,0),colors.lightgrey),
                           ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTNAME",(0,3),(-1,3),"Helvetica-Bold"),
                           ("FONTNAME",(0,10),(-1,-1),"Helvetica-Bold"),("ALIGN",(1,0),(-1,-1),"RIGHT"),
                           ("FONTSIZE",(0,0),(-1,-1),7.7),("VALIGN",(0,0),(-1,-1),"TOP")]))
    story += [t,Spacer(1,7)]
    for w in warnings: story.append(Paragraph("• "+w,note))

    def signature_block():
        ca_firm=sign.get("ca_firm","").strip(); ca_des=sign.get("ca_designation","").strip()
        ca_name=sign.get("ca_name","").strip(); mem=sign.get("membership","").strip()
        ent_for=sign.get("entity_for","").strip(); ent_name=sign.get("entity_signatory","").strip(); ent_des=sign.get("entity_designation","").strip()
        place=sign.get("place","").strip(); date=sign.get("date","").strip()
        left=[]; right=[]
        if ca_firm: left.append(Paragraph("<b>For "+ca_firm+"</b>",note))
        if ca_des: left.append(Paragraph(ca_des,note))
        left += [Spacer(1,16)]
        if ca_name: left.append(Paragraph("<b>"+ca_name+"</b>",note))
        if mem: left.append(Paragraph("Membership No.: "+mem,note))
        if ent_for: right.append(Paragraph("<b>For "+ent_for+"</b>",note))
        right += [Spacer(1,16)]
        if ent_name: right.append(Paragraph("<b>"+ent_name+"</b>",note))
        if ent_des: right.append(Paragraph(ent_des,note))
        sig=Table([[left,right]],colWidths=[91*mm,91*mm])
        sig.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),4)]))
        tail=[]
        if place or date:
            tail.append(Spacer(1,8)); tail.append(Paragraph(("Place: "+place if place else "") + ("&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; Date: "+date if date else ""),note))
        return [Spacer(1,10),sig]+tail

    story += signature_block()
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
    story += [tb]
    story += signature_block()
    story += [PageBreak(),Paragraph("Source Ledger Mapping / Review Schedule",title)]
    m=[["Year","Statement","Source ledger","Vertical head","Amount"]]
    for yr,stname,rows in [(cy,"P&L",cpl),(py,"P&L",ppl),(cy,"Balance Sheet",cbs),(py,"Balance Sheet",pbs)]:
        for r in rows:m.append([yr,stname,r["Source ledger"],r["Vertical head"],fmt(r["Amount"])])
    mt=Table(m,colWidths=[17*mm,22*mm,52*mm,62*mm,30*mm],repeatRows=1)
    mt.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.25,colors.grey),("BACKGROUND",(0,0),(-1,0),colors.lightgrey),
                            ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),6.8),
                            ("VALIGN",(0,0),(-1,-1),"TOP"),("ALIGN",(-1,1),(-1,-1),"RIGHT")]))
    story.append(mt); doc.build(story); out.seek(0); return out.getvalue()

# Separate upload boxes make the accounting source explicit. Trading Account is optional.
st.markdown("### Current / latest year")
c1,c2,c3=st.columns(3)
with c1:
    ctrdf=st.file_uploader("Current-year Trading Account PDF (optional)",type=["pdf"],key="ctrd")
    c_no_trading=st.checkbox("No separate Trading Account for current year",key="cnt")
with c2:
    cplf=st.file_uploader("Current-year Profit & Loss Account PDF",type=["pdf"],key="cpl")
with c3:
    cbsf=st.file_uploader("Current-year Balance Sheet PDF",type=["pdf"],key="cbs")

st.markdown("### Previous year")
p1,p2,p3=st.columns(3)
with p1:
    ptrdf=st.file_uploader("Previous-year Trading Account PDF (optional)",type=["pdf"],key="ptrd")
    p_no_trading=st.checkbox("No separate Trading Account for previous year",key="pnt")
with p2:
    pplf=st.file_uploader("Previous-year Profit & Loss Account PDF",type=["pdf"],key="ppl")
with p3:
    pbsf=st.file_uploader("Previous-year Balance Sheet PDF",type=["pdf"],key="pbs")

entity=st.text_input("Entity name",value="M/S DEV BHUMI APPLE TRADERS")
address=st.text_input("Entity address",value="B-10, FLAT NO-9, SECTOR-18, ROHINI, DELHI", help="Editable. For other clients, replace this with the address appearing in the uploaded statements.")

st.markdown("### Signatory / footer details (printed on both P&L and Balance Sheet)")
sg1,sg2=st.columns(2)
with sg1:
    ca_firm=st.text_input("Chartered Accountant firm", value="Lakshya Budhiraja & Associates")
    ca_designation=st.text_input("CA designation", value="Chartered Accountant")
    ca_name=st.text_input("CA / Proprietor name", value="LAKSHYA BUDHIRAJA (PROPREITOR)")
    membership=st.text_input("Membership No.", value="535942")
with sg2:
    entity_for=st.text_input("For (Entity)", value=entity)
    entity_signatory=st.text_input("Entity signatory name", value="MAN SINGH THAKUR")
    entity_designation=st.text_input("Entity signatory designation", value="Proprietor")
    place=st.text_input("Place", value="NEW DELHI")
    sign_date=st.text_input("Date", value="16/09/2026", help="Use DD/MM/YYYY")
sign={"ca_firm":ca_firm,"ca_designation":ca_designation,"ca_name":ca_name,"membership":membership,"entity_for":entity_for,"entity_signatory":entity_signatory,"entity_designation":entity_designation,"place":place,"date":sign_date}

required_ok=all([cplf,cbsf,pplf,pbsf])
if required_ok:
    cplt=text(cplf); bt=text(cbsf); pplt=text(pplf); pbt=text(pbsf)
    ctrdt=text(ctrdf) if ctrdf else ""
    ptrdt=text(ptrdf) if ptrdf else ""
    ct=cplt + ("\n"+ctrdt if ctrdt else "")
    pt=pplt + ("\n"+ptrdt if ptrdt else "")

    detected_address=address_from(cplt,bt,pplt,pbt)
    if detected_address and detected_address.lower() != address.strip().lower():
        st.info(f"Address detected in uploaded statements: {detected_address}. Edit the Entity address field above if required.")

    cy=year_from(cplt) or year_from(ctrdt) or year_from(bt) or "Current"
    py=year_from(pplt) or year_from(ptrdt) or year_from(pbt) or "Previous"
    # Safety: latest year must appear first even if the user accidentally swaps files.
    try:
        if int(py)>int(cy):
            st.error("The files selected as Previous Year contain a later year than the Current Year. Please swap the uploads so the latest/subsequent year is Current Year.")
            st.stop()
    except Exception:
        pass

    cpl=parse_pl(ct); ppl=parse_pl(pt); cbs=parse_bs(bt); pbs=parse_bs(pbt)

    st.markdown("### Manual additions / missing items")
    st.caption("Use this only where an item or amount is missing from automatic extraction. Added rows are included in the PDF and all reconciliation checks. Leave the number of rows at 0 if nothing is missing.")
    def manual_rows(label, heads, key):
        n=st.number_input(f"Number of manual rows — {label}", min_value=0, max_value=20, value=0, step=1, key=key+"n")
        out=[]
        for i in range(int(n)):
            a,b,c,d=st.columns([3,3,2,1])
            name=a.text_input("Particular / ledger", key=f"{key}name{i}")
            head=b.selectbox("Vertical head", heads, key=f"{key}head{i}")
            amount=c.number_input("Amount (₹)", value=0.0, step=1.0, format="%.2f", key=f"{key}amt{i}")
            note=d.text_input("Note", key=f"{key}note{i}")
            if name.strip() or abs(amount)>0.005:
                out.append({"Source ledger": (name.strip() or "Manual adjustment") + (f" [Note {note}]" if note.strip() else "") + " [MANUAL]", "Vertical head":head, "Amount":float(amount)})
        return out
    ma1,ma2=st.columns(2)
    with ma1:
        cpl += manual_rows(f"{cy} Profit & Loss", PL_HEADS, "mcpl")
        cbs += manual_rows(f"{cy} Balance Sheet", BS_HEADS, "mcbs")
    with ma2:
        ppl += manual_rows(f"{py} Profit & Loss", PL_HEADS, "mppl")
        pbs += manual_rows(f"{py} Balance Sheet", BS_HEADS, "mpbs")

    c_has_trading=bool(ctrdf) or any(r["Vertical head"]=="Revenue from operations" for r in cpl)
    p_has_trading=bool(ptrdf) or any(r["Vertical head"]=="Revenue from operations" for r in ppl)
    csnp=source_net_profit(cplt); psnp=source_net_profit(pplt)
    warnings=[]

    def bs_difference(rows):
        a=aggregate(rows,BS_HEADS); liab=BS_HEADS[:10]; assets=BS_HEADS[10:]
        return sum(a[h] for h in assets)-sum(a[h] for h in liab)
    for yr,rows in [(cy,cbs),(py,pbs)]:
        d=bs_difference(rows)
        if abs(d)>1.0: warnings.append(f"{yr}: BALANCE SHEET DOES NOT RECONCILE — Assets less Equity & Liabilities = ₹{d:,.2f}.")
        else: warnings.append(f"{yr}: Balance Sheet reconciled (difference ₹{d:,.2f}).")

    def computed_profit(rows):
        a=aggregate(rows,PL_HEADS)
        income=a["Revenue from operations"]+a["Other Income"]
        expenses=sum(a[h] for h in ["Cost of goods sold","Employee benefits expense","Finance costs","Depreciation and amortization expense","Other expenses"])
        return income-expenses
    def source_aware_profit(rows, pltxt, tradingtxt):
        a=aggregate(rows,PL_HEADS)
        if tradingtxt or abs(a["Revenue from operations"]) > 0.005:
            return computed_profit(rows), "complete Trading + P&L statement"
        gp=source_gross_profit(pltxt)
        if gp is not None:
            indirect=sum(a[h] for h in ["Employee benefits expense","Finance costs","Depreciation and amortization expense","Other expenses"])
            return gp + a["Other Income"] - indirect, "Gross Profit less extracted P&L expenses"
        return computed_profit(rows), "P&L-only statement"

    for yr,pltxt,tradingtxt,rows,snp in [(cy,cplt,ctrdt,cpl,csnp),(py,pplt,ptrdt,ppl,psnp)]:
        calc,basis=source_aware_profit(rows,pltxt,tradingtxt)
        if snp is not None and abs(calc-snp)>1.0:
            warnings.append(f"{yr}: P&L DOES NOT RECONCILE — REVIEW REQUIRED. {basis} gives ₹{calc:,.2f}, while source Net Profit is ₹{snp:,.2f}.")
        elif snp is not None:
            warnings.append(f"{yr}: P&L RECONCILED. {basis} agrees with source Net Profit ₹{snp:,.2f}.")

    if not c_has_trading:
        if c_no_trading:
            warnings.append(f"{cy}: No separate Trading Account declared. Revenue from operations and Cost of Goods Sold are shown as N/A unless available directly in the P&L; the source Net Profit is preserved.")
        else:
            warnings.append(f"{cy}: No Trading Account uploaded. If one exists, upload it to populate Revenue from Operations and Cost of Goods Sold. If none exists, tick 'No separate Trading Account for current year'.")
    if not p_has_trading:
        if p_no_trading:
            warnings.append(f"{py}: No separate Trading Account declared. Revenue from operations and Cost of Goods Sold are shown as N/A unless available directly in the P&L; the source Net Profit is preserved.")
        else:
            warnings.append(f"{py}: No Trading Account uploaded. If one exists, upload it; otherwise tick 'No separate Trading Account for previous year'.")

    warnings += ["Review borrowing maturity before deciding long-term vs short-term classification.",
                 "Review FDR maturity, loans/advances tenure, and land classification before finalisation."]

    st.subheader("Review classifications")
    for label,rows,heads,prefix_key in [("Current P&L + Trading",cpl,PL_HEADS,"cp"),("Previous P&L + Trading",ppl,PL_HEADS,"pp"),
                                    ("Current Balance Sheet",cbs,BS_HEADS,"cb"),("Previous Balance Sheet",pbs,BS_HEADS,"pb")]:
        with st.expander(label,expanded=False):
            for i,r in enumerate(rows):
                a,b,c=st.columns([3,2,4]); a.write(r["Source ledger"]); b.write(f"₹{r['Amount']:,.2f}")
                r["Vertical head"]=c.selectbox("Head",heads,index=heads.index(r["Vertical head"]),key=f"{prefix_key}{i}",label_visibility="collapsed")
    for w in warnings: st.warning(w)
    data=pdf(entity,address,cy,py,cpl,ppl,cbs,pbs,warnings,csnp,psnp,c_has_trading,p_has_trading,sign)
    st.download_button("Generate comparative vertical PDF (review before finalisation)",data=data,file_name=f"{entity.replace(' ','_')}_comparative_vertical.pdf",mime="application/pdf")
else:
    st.info("Upload the four required PDFs: current P&L, current Balance Sheet, previous P&L and previous Balance Sheet. Trading Account PDFs are optional for either year.")
