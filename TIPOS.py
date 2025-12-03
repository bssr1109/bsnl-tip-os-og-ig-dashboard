# TIPOS_FINAL_v3.py — TIP / BBM / MGMT Dashboard (Mobile-friendly, Option C)
# ---------------------------------------------------------------------
# Features
# - Unified login (TIP / BBM / MGMT) using JSON files
# - BBM uploads OS (Total OS + PRIVATE OS auto-merged) & OG/IC barred
# - TIP dashboard with OS + OG accounts, Call/WhatsApp buttons, status badges
# - BBM dashboard with summary cards, TIP-wise tables & drill-down TIP view
# - MGMT dashboard with global contact summary
# - Month-wise Call / WhatsApp status stored in tip_contact_status.xlsx
# - Designed to work well on mobile (mostly vertical layout)
# ---------------------------------------------------------------------

import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime
from urllib.parse import quote

# ---------------------------------------------------------------------
# BASIC CONFIG
# ---------------------------------------------------------------------
st.set_page_config(page_title="TIP / BBM Dashboard", layout="wide")

# ---------------------------------------------------------------------
# SESSION INIT
# ---------------------------------------------------------------------
def init_session():
    defaults = {
        "authenticated": False,
        "role": None,          # "TIP", "BBM", "MGMT"
        "username": None,      # login name (upper)
        "os_df": None,
        "og_df": None,
        "status_sheets": None,  # month -> DataFrame
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session()

CURRENT_MONTH = datetime.now().strftime("%Y-%m")
STATUS_FILE = "tip_contact_status.xlsx"
OS_LATEST_FILE = "Outstanding_latest.xlsx"
OG_LATEST_FILE = "Barred_latest.xlsx"

# ---------------------------------------------------------------------
# USER DB LOADERS (JSON)
# ---------------------------------------------------------------------
TIP_USERS_FILE = "tip_users.json"
BBM_USERS_FILE = "bbm_users.json"
MGMT_FILE = "mgmt.json"


def load_json_safe(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def load_user_db():
    # keys must be UPPERCASE login IDs
    tip_users = load_json_safe(TIP_USERS_FILE, {})
    bbm_users = load_json_safe(BBM_USERS_FILE, {})
    mgmt = load_json_safe(MGMT_FILE, {"password": "1234"})

    # normalize keys to uppercase
    tip_users_norm = {k.upper(): v for k, v in tip_users.items()}
    bbm_users_norm = {k.upper(): v for k, v in bbm_users.items()}

    st.session_state["user_tip"] = tip_users_norm
    st.session_state["user_bbm"] = bbm_users_norm
    st.session_state["user_mgmt_pwd"] = mgmt.get("password", "1234")


load_user_db()

# ---------------------------------------------------------------------
# LOGIN UI
# ---------------------------------------------------------------------

def login_ui():
    st.title("📡 TIP / BBM / MGMT Dashboard")
    st.subheader("🔐 Login")

    role = st.radio("Login as", ["TIP", "BBM", "MGMT"], horizontal=True)
    col_user, col_pwd = st.columns(2)

    with col_user:
        username = st.text_input("User ID", help="TIP name / BBM name / MGMT ID")
    with col_pwd:
        password = st.text_input("Password", type="password")

    if st.button("Login", use_container_width=True):
        u = username.strip().upper()
        if not u:
            st.error("Please enter User ID")
            return

        if role == "TIP":
            users = st.session_state["user_tip"]
            if u in users and users[u] == password:
                st.session_state.authenticated = True
                st.session_state.role = "TIP"
                st.session_state.username = u
                st.experimental_rerun()
            else:
                st.error("Invalid TIP credentials")

        elif role == "BBM":
            users = st.session_state["user_bbm"]
            if u in users and users[u] == password:
                st.session_state.authenticated = True
                st.session_state.role = "BBM"
                st.session_state.username = u
                st.experimental_rerun()
            else:
                st.error("Invalid BBM credentials")

        else:  # MGMT
            mgmt_pwd = st.session_state["user_mgmt_pwd"]
            if password == mgmt_pwd:
                st.session_state.authenticated = True
                st.session_state.role = "MGMT"
                st.session_state.username = u or "MGMT"
                st.experimental_rerun()
            else:
                st.error("Invalid MGMT password")


if not st.session_state.authenticated:
    login_ui()
    st.stop()

# ---------------------------------------------------------------------
# TOP BAR + LOGOUT + REFRESH
# ---------------------------------------------------------------------
left, right = st.columns([3, 1])
with left:
    st.markdown(
        f"**Logged in as:** `{st.session_state.role}` — `{st.session_state.username}`"
    )
with right:
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        if st.button("🔁 Refresh"):
            st.experimental_rerun()
    with col_r2:
        if st.button("🚪 Logout"):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.experimental_rerun()

# ---------------------------------------------------------------------
# BBM FILE UPLOAD (OS / OG)
# ---------------------------------------------------------------------

def bbm_upload_ui():
    st.markdown("---")
    st.subheader("📤 Upload Monthly Files (BBM Only)")
    st.caption("Only .xlsx files are supported (openpyxl engine)")

    os_file = st.file_uploader(
        "Upload Outstanding (OS) Excel — with 'Total OS' and 'PRIVATE OS' sheets",
        type=["xlsx"],
        key="os_up",
    )
    og_file = st.file_uploader(
        "Upload OG/IC Barred Excel (.xlsx)",
        type=["xlsx"],
        key="og_up",
    )

    if os_file is not None:
        try:
            xls = pd.ExcelFile(os_file, engine="openpyxl")
            sheets = xls.sheet_names
            if "Total OS" in sheets:
                s1 = "Total OS"
            else:
                s1 = sheets[0]
            if "PRIVATE OS" in sheets:
                s2 = "PRIVATE OS"
            else:
                s2 = sheets[1] if len(sheets) > 1 else sheets[0]

            df_total = pd.read_excel(xls, sheet_name=s1)
            df_private = pd.read_excel(xls, sheet_name=s2)
            merged = pd.concat([df_total, df_private], ignore_index=True)
            merged.to_excel(OS_LATEST_FILE, index=False)
            st.session_state.os_df = merged
            st.success(f"OS file uploaded and merged (sheets: {s1}, {s2})")
        except Exception as e:
            st.error(f"Error reading OS file: {e}")

    if og_file is not None:
        try:
            xls = pd.ExcelFile(og_file, engine="openpyxl")
            sheet = xls.sheet_names[1] if len(xls.sheet_names) > 1 else xls.sheet_names[0]
            og_df = pd.read_excel(xls, sheet_name=sheet)
            og_df.to_excel(OG_LATEST_FILE, index=False)
            st.session_state.og_df = og_df
            st.success(f"OG/IC file uploaded (sheet: {sheet})")
        except Exception as e:
            st.error(f"Error reading OG file: {e}")


if st.session_state.role == "BBM":
    bbm_upload_ui()

# ---------------------------------------------------------------------
# LOAD OS / OG FROM DISK (for all roles)
# ---------------------------------------------------------------------

def load_latest_data():
    if st.session_state.os_df is None and os.path.exists(OS_LATEST_FILE):
        try:
            st.session_state.os_df = pd.read_excel(OS_LATEST_FILE)
        except Exception as e:
            st.warning(f"Could not read {OS_LATEST_FILE}: {e}")

    if st.session_state.og_df is None and os.path.exists(OG_LATEST_FILE):
        try:
            st.session_state.og_df = pd.read_excel(OG_LATEST_FILE)
        except Exception as e:
            st.warning(f"Could not read {OG_LATEST_FILE}: {e}")


load_latest_data()
os_raw = st.session_state.os_df
og_raw = st.session_state.og_df

if os_raw is None and og_raw is None:
    st.error("No OS / OG data available. BBM must upload files.")
    st.stop()

# ---------------------------------------------------------------------
# STATUS SYSTEM (MONTH-WISE SHEETS)
# ---------------------------------------------------------------------

def load_status_all():
    if st.session_state.status_sheets is not None:
        return st.session_state.status_sheets

    sheets = {}
    if os.path.exists(STATUS_FILE):
        try:
            xls = pd.ExcelFile(STATUS_FILE, engine="openpyxl")
            for s in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=s, dtype=str)
                sheets[s] = df
        except Exception:
            sheets = {}
    st.session_state.status_sheets = sheets
    return sheets


def save_status_all(sheets):
    if not sheets:
        sheets = {}
    with pd.ExcelWriter(STATUS_FILE, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name, index=False)
    st.session_state.status_sheets = sheets


def update_status_row(tip_name, bbm_name, source, account_no, update_call=False, update_wa=False):
    tip_std = str(tip_name).upper().strip()
    bbm_std = str(bbm_name).upper().strip() if bbm_name else ""
    source = source.upper()  # "OS" or "OG"
    acc = str(account_no).strip()

    sheets = load_status_all()
    month = CURRENT_MONTH

    if month in sheets:
        df = sheets[month].copy()
    else:
        df = pd.DataFrame(columns=[
            "TIP_STD", "BBM_STD", "SOURCE", "ACCOUNT_NO",
            "LAST_CALL_TIME", "LAST_WHATSAPP_TIME", "MONTH",
        ])

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    mask = (
        (df["TIP_STD"] == tip_std) &
        (df["BBM_STD"] == bbm_std) &
        (df["SOURCE"] == source) &
        (df["ACCOUNT_NO"] == acc)
    ) if not df.empty else pd.Series(False, index=df.index)

    if mask.any():
        idx = df[mask].index[0]
        if update_call:
            df.at[idx, "LAST_CALL_TIME"] = now
        if update_wa:
            df.at[idx, "LAST_WHATSAPP_TIME"] = now
        df.at[idx, "MONTH"] = month
    else:
        new_row = {
            "TIP_STD": tip_std,
            "BBM_STD": bbm_std,
            "SOURCE": source,
            "ACCOUNT_NO": acc,
            "LAST_CALL_TIME": now if update_call else "",
            "LAST_WHATSAPP_TIME": now if update_wa else "",
            "MONTH": month,
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

    sheets[month] = df
    save_status_all(sheets)


def get_status_map_for(tip_name, bbm_name, source, month=None):
    if month is None:
        month = CURRENT_MONTH
    sheets = load_status_all()
    tip_std = str(tip_name).upper().strip()
    bbm_std = str(bbm_name).upper().strip() if bbm_name else ""

    if month not in sheets or sheets[month].empty:
        return {}
    df = sheets[month]
    if "BBM_STD" not in df.columns:
        return {}

    sub = df[
        (df["TIP_STD"] == tip_std) &
        (df["BBM_STD"] == bbm_std) &
        (df["SOURCE"] == source.upper())
    ]
    m = {}
    for _, row in sub.iterrows():
        acc = str(row["ACCOUNT_NO"])
        m[acc] = (
            row.get("LAST_CALL_TIME", ""),
            row.get("LAST_WHATSAPP_TIME", ""),
        )
    return m


# ---------------------------------------------------------------------
# PREPROCESS OS / OG (STANDARDIZE & FILTER BY ROLE)
# ---------------------------------------------------------------------

def clean_mobile(val: str) -> str:
    if pd.isna(val):
        return ""
    s = str(val).strip()
    if s.endswith(".0"):
        s = s[:-2]
    digits = "".join(ch for ch in s if ch.isdigit())
    return digits


def preprocess_for_role(role: str, username: str):
    # Start from raw copies
    osdf = os_raw.copy() if os_raw is not None else pd.DataFrame()
    ogdf = og_raw.copy() if og_raw is not None else pd.DataFrame()

    # Basic type cleaning
    for df in (osdf, ogdf):
        if not df.empty:
            for c in df.columns:
                df[c] = df[c].astype(str)

    # OS
    if not osdf.empty and "Maintanance Franchisee Name" in osdf.columns and "BBM" in osdf.columns:
        osdf["TIP_STD"] = osdf["Maintanance Franchisee Name"].str.upper().str.strip()
        osdf["BBM_STD"] = osdf["BBM"].str.upper().str.strip()
        if "OS_Amount(Rs)" in osdf.columns:
            osdf["OS_Amount(Rs)"] = pd.to_numeric(osdf["OS_Amount(Rs)"], errors="coerce").fillna(0)
        if "Mobile_Number" in osdf.columns:
            osdf["Mobile_Number"] = osdf["Mobile_Number"].apply(clean_mobile)
    else:
        osdf = pd.DataFrame()

    # OG
    if not ogdf.empty and "Maintenance Fanchisee Name" in ogdf.columns and "BBM" in ogdf.columns:
        ogdf["TIP_STD"] = ogdf["Maintenance Fanchisee Name"].str.upper().str.strip()
        ogdf["BBM_STD"] = ogdf["BBM"].str.upper().str.strip()
        if "OutStanding" in ogdf.columns:
            ogdf["OutStanding"] = pd.to_numeric(ogdf["OutStanding"], errors="coerce").fillna(0)
        if "Mobile Number" in ogdf.columns:
            ogdf["Mobile Number"] = ogdf["Mobile Number"].apply(clean_mobile)
    else:
        ogdf = pd.DataFrame()

    uname = username.upper().strip()

    if role == "TIP":
        # TIP sees all his accounts across BBMs
        if not osdf.empty:
            osdf = osdf[osdf["TIP_STD"] == uname]
        if not ogdf.empty:
            ogdf = ogdf[ogdf["TIP_STD"] == uname]

    elif role == "BBM":
        # BBM sees accounts tagged to his BBM name
        if not osdf.empty:
            osdf = osdf[osdf["BBM_STD"] == uname]
        if not ogdf.empty:
            ogdf = ogdf[ogdf["BBM_STD"] == uname]

    # MGMT sees all (no filter)
    return osdf, ogdf


role = st.session_state.role
user = st.session_state.username
os_df, og_df = preprocess_for_role(role, user)

# ---------------------------------------------------------------------
# COMMON RENDER: CUSTOMER ROW
# ---------------------------------------------------------------------

def render_customer_row(source: str, row: pd.Series, bbm_name: str, tip_name: str):
    """Render one OS / OG customer block with buttons & status badge."""
    source = source.upper()  # OS / OG
    if source == "OS":
        acc = str(row.get("Billing_Account_Number", ""))
        mobile = row.get("Mobile_Number", "")
        amount = float(row.get("OS_Amount(Rs)", 0) or 0)
        cust_name = row.get("First_Name", "") or row.get("Customer Name", "")
        addr = row.get("Address", "")
    else:
        acc = str(row.get("Account Number", ""))
        mobile = row.get("Mobile Number", "")
        amount = float(row.get("OutStanding", 0) or 0)
        cust_name = row.get("Customer Name", "")
        addr = row.get("ADDRESS", "") or row.get("Address", "")

    tip_std = tip_name
    bbm_std = bbm_name

    status_map = get_status_map_for(tip_std, bbm_std, source)
    last_call, last_wa = status_map.get(acc, ("", ""))

    if last_call or last_wa:
        badge = "🟩 Contact Done"
    else:
        badge = "🟧 Pending"

    # Layout for mobile: vertical stacked
    with st.container():
        st.markdown(
            f"**{cust_name}**  "+
            f"Acc: `{acc}`  "
        )
        if addr:
            st.caption(addr)

        st.write(f"Amount: ₹{amount:,.2f}  {badge}")
        if mobile:
            st.write(f"📱 {mobile}")

        # Buttons row
        c1, c2, c3 = st.columns([1, 1, 2])
        btn_key_call = f"{source}_call_{acc}"
        btn_key_wa = f"{source}_wa_{acc}"

        with c1:
            if st.button("Call Done", key=btn_key_call):
                update_status_row(tip_std, bbm_std, source, acc, update_call=True)
                st.experimental_rerun()
        with c2:
            if st.button("WA Sent", key=btn_key_wa):
                update_status_row(tip_std, bbm_std, source, acc, update_wa=True)
                st.experimental_rerun()
        with c3:
            if mobile:
                msg = (
                    f"Dear {cust_name}, your BSNL FTTH outstanding is Rs {amount:.2f}. "
                    "Kindly pay immediately."
                    if source == "OS"
                    else f"Dear {cust_name}, your BSNL FTTH bill is overdue. Outstanding Rs {amount:.2f}. Kindly pay immediately."
                )
                wa_url = f"https://wa.me/91{mobile}?text=" + quote(msg)
                st.markdown(f"[💬 WhatsApp Customer]({wa_url})")

        # Status footer
        if last_call or last_wa:
            info = []
            if last_call:
                info.append(f"📞 {last_call}")
            if last_wa:
                info.append(f"💬 {last_wa}")
            st.caption("  |  ".join(info))

        st.markdown("---")


# ---------------------------------------------------------------------
# TIP DASHBOARD (OPTION C)
# ---------------------------------------------------------------------

def tip_dashboard():
    tip_name = st.session_state.username
    st.subheader(f"📘 TIP Dashboard — {tip_name}")

    # Metrics
    total_os_amt = os_df["OS_Amount(Rs)"].sum() if not os_df.empty else 0
    total_og_amt = og_df["OutStanding"].sum() if not og_df.empty else 0
    total_os_cnt = len(os_df) if not os_df.empty else 0
    total_og_cnt = len(og_df) if not og_df.empty else 0

    c1, c2 = st.columns(2)
    with c1:
        st.metric("💰 Total OS (Disconnected)", f"₹{total_os_amt:,.2f}", help="Total outstanding of disconnected customers")
        st.metric("👥 OS Customers", total_os_cnt)
    with c2:
        st.metric("🚫 Total OG/IC Barred", f"₹{total_og_amt:,.2f}", help="Outstanding of working but OG/IC barred customers")
        st.metric("👥 Barred Customers", total_og_cnt)

    st.markdown("---")

    # Search / filter for mobile screens
    st.markdown("### 🔍 Search / Filter")
    search_text = st.text_input("Search by Account / Name / Mobile (optional)")

    def apply_search(df, source):
        if df.empty or not search_text.strip():
            return df
        s = search_text.strip().upper()
        df2 = df.copy()
        if source == "OS":
            cols = ["Billing_Account_Number", "First_Name", "Customer Name", "Mobile_Number"]
        else:
            cols = ["Account Number", "Customer Name", "Mobile Number"]
        mask = pd.Series(False, index=df2.index)
        for c in cols:
            if c in df2.columns:
                mask |= df2[c].astype(str).str.upper().str.contains(s, na=False)
        return df2[mask]

    # OS SECTION
    st.markdown("### 📴 Disconnected OS Customers")
    tip_std = tip_name
    # Try to guess a BBM name (first unique)
    bbm_name = ""
    if not os_df.empty and "BBM_STD" in os_df.columns:
        bbms = os_df["BBM_STD"].dropna().unique().tolist()
        bbm_name = bbms[0] if bbms else ""

    os_tip = os_df.copy()
    os_tip = apply_search(os_tip, "OS")

    if os_tip.empty:
        st.info("No disconnected OS customers found for this TIP.")
    else:
        for _, r in os_tip.iterrows():
            render_customer_row("OS", r, bbm_name, tip_std)

    # OG SECTION
    st.markdown("### 📡 Working Customers – OG/IC Barred")
    og_tip = og_df.copy()
    og_tip = apply_search(og_tip, "OG")

    if og_tip.empty:
        st.info("No OG/IC barred working customers found for this TIP.")
    else:
        # Try to guess BBM from OG df if present
        if not og_df.empty and "BBM_STD" in og_df.columns and not bbm_name:
            bbms = og_df["BBM_STD"].dropna().unique().tolist()
            bbm_name = bbms[0] if bbms else ""
        for _, r in og_tip.iterrows():
            render_customer_row("OG", r, bbm_name, tip_std)


# ---------------------------------------------------------------------
# BBM DASHBOARD (OPTION C)
# ---------------------------------------------------------------------

def bbm_dashboard():
    bbm_name = st.session_state.username
    st.subheader(f"📙 BBM Dashboard — {bbm_name}")

    # Metrics
    total_os_amt = os_df["OS_Amount(Rs)"].sum() if not os_df.empty else 0
    total_og_amt = og_df["OutStanding"].sum() if not og_df.empty else 0
    total_os_cnt = len(os_df) if not os_df.empty else 0
    total_og_cnt = len(og_df) if not og_df.empty else 0

    c1, c2 = st.columns(2)
    with c1:
        st.metric("💰 Total OS (This BBM)", f"₹{total_os_amt:,.2f}")
        st.metric("👥 OS Customers", total_os_cnt)
    with c2:
        st.metric("🚫 Total OG/IC Barred (This BBM)", f"₹{total_og_amt:,.2f}")
        st.metric("👥 Barred Customers", total_og_cnt)

    st.markdown("---")
    st.markdown("### 📊 TIP-wise Summary")

    # TIP-wise summary
    if not os_df.empty:
        os_grp = os_df.groupby("TIP_STD").agg(
            OS_Amount=("OS_Amount(Rs)", "sum"),
            OS_Customers=("Billing_Account_Number", "count"),
        )
    else:
        os_grp = pd.DataFrame(columns=["OS_Amount", "OS_Customers"])

    if not og_df.empty:
        og_grp = og_df.groupby("TIP_STD").agg(
            OG_Amount=("OutStanding", "sum"),
            OG_Customers=("Account Number", "count"),
        )
    else:
        og_grp = pd.DataFrame(columns=["OG_Amount", "OG_Customers"])

    tip_summary = os_grp.join(og_grp, how="outer").fillna(0)
    tip_summary = tip_summary.reset_index().rename(columns={"TIP_STD": "TIP Name"})

    st.dataframe(tip_summary, use_container_width=True)

    # Contact Summary
    st.markdown("### 📞 Contact Summary (This BBM)")
    sheets = load_status_all()
    month_list = sorted(sheets.keys())
    if not month_list:
        st.info("No contact actions recorded yet.")
    else:
        month_sel = st.selectbox(
            "Select month", month_list,
            index=month_list.index(CURRENT_MONTH) if CURRENT_MONTH in month_list else len(month_list) - 1,
        )
        df_m = sheets[month_sel]
        if df_m.empty:
            st.info("No records in selected month.")
        else:
            df_m = df_m[df_m["BBM_STD"] == bbm_name]
            if df_m.empty:
                st.info("No contacts recorded for this BBM in selected month.")
            else:
                df_m["has_call"] = df_m["LAST_CALL_TIME"].fillna("").ne("")
                df_m["has_wa"] = df_m["LAST_WHATSAPP_TIME"].fillna("").ne("")
                summary = df_m.groupby("TIP_STD").agg(
                    Accounts=("ACCOUNT_NO", "nunique"),
                    Calls=("has_call", "sum"),
                    WhatsApps=("has_wa", "sum"),
                ).reset_index().rename(columns={"TIP_STD": "TIP Name"})
                st.dataframe(summary, use_container_width=True)

    st.markdown("---")
    st.markdown("### 🔍 Drill-down into a TIP (Customer-level view)")

    if os_df.empty and og_df.empty:
        st.info("No data loaded for this BBM.")
        return

    tips = sorted(set(os_df["TIP_STD"].tolist() + og_df["TIP_STD"].tolist()))
    if not tips:
        st.info("No TIPs found for this BBM.")
        return

    tip_sel = st.selectbox("Select TIP", tips)
    if not tip_sel:
        return

    st.markdown(f"#### 👀 TIP View: {tip_sel}")
    # Filter data for this TIP
    os_tip = os_df[os_df["TIP_STD"] == tip_sel] if not os_df.empty else pd.DataFrame()
    og_tip = og_df[og_df["TIP_STD"] == tip_sel] if not og_df.empty else pd.DataFrame()

    search_text = st.text_input("Search within this TIP (Account / Name / Mobile)")

    def apply_search_local(df, source):
        if df.empty or not search_text.strip():
            return df
        s = search_text.strip().upper()
        df2 = df.copy()
        if source == "OS":
            cols = ["Billing_Account_Number", "First_Name", "Customer Name", "Mobile_Number"]
        else:
            cols = ["Account Number", "Customer Name", "Mobile Number"]
        mask = pd.Series(False, index=df2.index)
        for c in cols:
            if c in df2.columns:
                mask |= df2[c].astype(str).str.upper().str.contains(s, na=False)
        return df2[mask]

    os_tip = apply_search_local(os_tip, "OS")
    og_tip = apply_search_local(og_tip, "OG")

    st.markdown("##### 📴 OS Customers")
    if os_tip.empty:
        st.info("No OS customers for this TIP.")
    else:
        for _, r in os_tip.iterrows():
            render_customer_row("OS", r, bbm_name, tip_sel)

    st.markdown("##### 📡 OG/IC Barred Customers")
    if og_tip.empty:
        st.info("No OG/IC barred customers for this TIP.")
    else:
        for _, r in og_tip.iterrows():
            render_customer_row("OG", r, bbm_name, tip_sel)


# ---------------------------------------------------------------------
# MGMT DASHBOARD
# ---------------------------------------------------------------------

def mgmt_dashboard():
    st.subheader("🏛️ Management Dashboard")

    # Use unfiltered raw data for MGMT
    os_m = os_raw.copy() if os_raw is not None else pd.DataFrame()
    og_m = og_raw.copy() if og_raw is not None else pd.DataFrame()

    # Clean minimal for summary
    if not os_m.empty and "OS_Amount(Rs)" in os_m.columns:
        os_m["OS_Amount(Rs)"] = pd.to_numeric(os_m["OS_Amount(Rs)"], errors="coerce").fillna(0)
    if not og_m.empty and "OutStanding" in og_m.columns:
        og_m["OutStanding"] = pd.to_numeric(og_m["OutStanding"], errors="coerce").fillna(0)

    total_os_amt = os_m["OS_Amount(Rs)"].sum() if not os_m.empty else 0
    total_og_amt = og_m["OutStanding"].sum() if not og_m.empty else 0

    c1, c2 = st.columns(2)
    with c1:
        st.metric("💰 Total OS (All BBMs)", f"₹{total_os_amt:,.2f}")
    with c2:
        st.metric("🚫 Total OG/IC Barred (All BBMs)", f"₹{total_og_amt:,.2f}")

    st.markdown("---")
    st.markdown("### 📞 Global Contact Summary")

    sheets = load_status_all()
    month_list = sorted(sheets.keys())
    if not month_list:
        st.info("No contact actions recorded yet.")
        return

    month_sel = st.selectbox(
        "Select month", month_list,
        index=month_list.index(CURRENT_MONTH) if CURRENT_MONTH in month_list else len(month_list) - 1,
    )
    df_m = sheets[month_sel]
    if df_m.empty:
        st.info("No records in selected month.")
        return

    df_m["has_call"] = df_m["LAST_CALL_TIME"].fillna("").ne("")
    df_m["has_wa"] = df_m["LAST_WHATSAPP_TIME"].fillna("").ne("")

    total_accounts = df_m["ACCOUNT_NO"].nunique()
    total_calls = int(df_m["has_call"].sum())
    total_wapps = int(df_m["has_wa"].sum())
    total_tips = df_m["TIP_STD"].nunique()
    total_bbms = df_m["BBM_STD"].nunique()

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("BBMs Active", total_bbms)
    with c2:
        st.metric("TIPs Active", total_tips)
    with c3:
        st.metric("Accounts Contacted", total_accounts)
    with c4:
        st.metric("Calls Logged", total_calls)
    with c5:
        st.metric("WhatsApps Logged", total_wapps)

    st.markdown("### 📊 BBM-wise Summary")
    bbm_summary = df_m.groupby("BBM_STD").agg(
        TIPs=("TIP_STD", "nunique"),
        Accounts=("ACCOUNT_NO", "nunique"),
        Calls=("has_call", "sum"),
        WhatsApps=("has_wa", "sum"),
    ).reset_index().rename(columns={"BBM_STD": "BBM"})
    st.dataframe(bbm_summary, use_container_width=True)

    st.markdown("### 📋 Full Contact Log (Selected Month)")
    st.dataframe(df_m, use_container_width=True)


# ---------------------------------------------------------------------
# MAIN ROLE SWITCH
# ---------------------------------------------------------------------

if role == "TIP":
    tip_dashboard()
elif role == "BBM":
    bbm_dashboard()
else:
    mgmt_dashboard()
