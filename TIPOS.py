import streamlit as st
import pandas as pd
import os
import io
from datetime import datetime
from urllib.parse import quote
import json

# ----------------- BASIC CONFIG -----------------
st.set_page_config(
    page_title="TIP Outstanding & OG/IC Barred Dashboard",
    layout="wide",
)

STATUS_FILE = "tip_contact_status.xlsx"   # TIP call / WhatsApp log (month-wise sheets)
UPLOAD_LOG_FILE = "bbm_upload_log.xlsx"   # BBM file upload log
CURRENT_MONTH = datetime.now().strftime("%Y-%m")  # e.g. 2025-12

# ----------------- LOAD LOGIN JSONS -----------------
MGMT_PASSWORD = ""
BBM_USERS = {}
TIP_USERS = {}

try:
    if os.path.exists("mgmt.json"):
        with open("mgmt.json", "r", encoding="utf-8") as f:
            mgmt_cfg = json.load(f)
            MGMT_PASSWORD = str(mgmt_cfg.get("password", "")).strip()

    if os.path.exists("bbm_users.json"):
        with open("bbm_users.json", "r", encoding="utf-8") as f:
            BBM_USERS = json.load(f)  # { "BBM NAME": "BBM1234", ... }

    if os.path.exists("tip_users.json"):
        with open("tip_users.json", "r", encoding="utf-8") as f:
            TIP_USERS = json.load(f)  # { "TIP NAME": "TIP1234", ... }
except Exception as e:
    st.warning(f"Error loading login JSON files: {e}")

# ----------------- COLUMN NAMES (your Excels) -----------------
# Outstanding List (Ftth OS_25.11.2025.xlsx → Total OS + PRIVATE OS)
COL_OS_TIP_NAME = "Maintanance Franchisee Name"
COL_OS_BBM = "BBM"
COL_OS_BA = "Billing_Account_Number"
COL_OS_MOBILE = "Mobile_Number"
COL_OS_CUST_NAME = "First_Name"
COL_OS_ADDR = "Address"
COL_OS_AMOUNT = "OS_Amount(Rs)"

# Barred Customer List (OGB_ICB_02.11.2025.xlsx → OG IC Barred List)
COL_OG_TIP_NAME = "Maintenance Fanchisee Name"
COL_OG_BBM = "BBM"
COL_OG_BA = "Account Number"
COL_OG_MOBILE = "Mobile Number"
COL_OG_CUST_NAME = "Customer Name"
COL_OG_ADDR = "ADDRESS"
COL_OG_AMOUNT = "OutStanding"

# ----------------- SESSION INIT -----------------
def init_session():
    defaults = {
        "authenticated": False,
        "role": None,          # "TIP" or "BBM" or "MGMT"
        "username": None,
        "current_bbm": "",
        "os_df": None,
        "og_df": None,
        "os_filename": "Not loaded",
        "og_filename": "Not loaded",
        "os_uploaded_at": "",
        "og_uploaded_at": "",
        "os_uploaded_by": "",
        "og_uploaded_by": "",
        "status_sheets": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session()

st.title("📊 TIP Outstanding & OG/IC Barred Dashboard")

# ----------------- COMMON HELPERS -----------------
def df_to_excel_bytes(df, sheet_name="Sheet1"):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    buffer.seek(0)
    return buffer.getvalue()

def make_tel_link(mobile):
    if not mobile:
        return ""
    return f'<a href="tel:{mobile}">📞 {mobile}</a>'

def make_whatsapp_link(mobile, message):
    if not mobile:
        return ""
    return f'<a href="https://wa.me/{mobile}?text={quote(message)}" target="_blank">🟢 WhatsApp</a>'

# ----------------- STATUS: LOAD / SAVE (MONTH-WISE SHEETS) -----------------
STATUS_COLS = [
    "TIP_NAME_STD", "BBM_STD", "SOURCE", "ACCOUNT_NO",
    "LAST_CALL_TIME", "LAST_WHATSAPP_TIME", "MONTH"
]

def load_status_all():
    if st.session_state.status_sheets is not None:
        return st.session_state.status_sheets

    sheets = {}
    if os.path.exists(STATUS_FILE):
        xls = pd.ExcelFile(STATUS_FILE)
        for s in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=s, dtype=str)
            for c in STATUS_COLS:
                if c not in df.columns:
                    df[c] = ""
            sheets[s] = df[STATUS_COLS].copy()
    st.session_state.status_sheets = sheets
    return sheets

def save_status_all(sheets_dict):
    if not sheets_dict:
        sheets_dict[CURRENT_MONTH] = pd.DataFrame(columns=STATUS_COLS)

    with pd.ExcelWriter(STATUS_FILE, engine="openpyxl") as writer:
        for sheet_name, df in sheets_dict.items():
            for c in STATUS_COLS:
                if c not in df.columns:
                    df[c] = ""
            df[STATUS_COLS].to_excel(writer, sheet_name=sheet_name, index=False)

    st.session_state.status_sheets = sheets_dict

def update_status(tip_name, source, account_no, update_call=False, update_whatsapp=False):
    tip_name = str(tip_name).upper().strip()
    account_no = str(account_no).strip()
    source = source.upper()   # "OS" or "OG"
    bbm_name = st.session_state.get("current_bbm", "").upper().strip()

    sheets = load_status_all()
    month_str = CURRENT_MONTH

    if month_str in sheets:
        df = sheets[month_str].copy()
        for c in STATUS_COLS:
            if c not in df.columns:
                df[c] = ""
        df = df[STATUS_COLS]
    else:
        df = pd.DataFrame(columns=STATUS_COLS)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    if not df.empty:
        mask = (
            (df["TIP_NAME_STD"] == tip_name) &
            (df["BBM_STD"] == bbm_name) &
            (df["SOURCE"] == source) &
            (df["ACCOUNT_NO"] == account_no)
        )
    else:
        mask = pd.Series(False, index=df.index)

    if mask.any():
        idx = df[mask].index[0]
        if update_call:
            df.at[idx, "LAST_CALL_TIME"] = now_str
        if update_whatsapp:
            df.at[idx, "LAST_WHATSAPP_TIME"] = now_str
        df.at[idx, "MONTH"] = month_str
    else:
        new_row = {
            "TIP_NAME_STD": tip_name,
            "BBM_STD": bbm_name,
            "SOURCE": source,
            "ACCOUNT_NO": account_no,
            "LAST_CALL_TIME": now_str if update_call else "",
            "LAST_WHATSAPP_TIME": now_str if update_whatsapp else "",
            "MONTH": month_str,
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

    sheets[month_str] = df
    save_status_all(sheets)

def get_status_map(tip_name, source, month_str=None):
    if month_str is None:
        month_str = CURRENT_MONTH

    sheets = load_status_all()
    tip_name = str(tip_name).upper().strip()
    bbm_name = st.session_state.get("current_bbm", "").upper().strip()

    if month_str not in sheets:
        return {}

    df = sheets[month_str]
    if df.empty:
        return {}

    for c in STATUS_COLS:
        if c not in df.columns:
            df[c] = ""

    sub = df[
        (df["TIP_NAME_STD"] == tip_name) &
        (df["BBM_STD"] == bbm_name) &
        (df["SOURCE"] == source.upper())
    ]
    m = {}
    for _, row in sub.iterrows():
        acc = str(row["ACCOUNT_NO"])
        m[acc] = (row.get("LAST_CALL_TIME", ""), row.get("LAST_WHATSAPP_TIME", ""))
    return m

# ----------------- BBM UPLOAD LOG (PERSISTENT) -----------------
def load_upload_log():
    if os.path.exists(UPLOAD_LOG_FILE):
        return pd.read_excel(UPLOAD_LOG_FILE, dtype=str)
    else:
        return pd.DataFrame(columns=["BBM_STD", "FILE_TYPE", "FILENAME", "UPLOADED_AT", "MONTH"])

def log_upload(bbm_name, file_type, filename):
    bbm_std = str(bbm_name).upper().strip()
    month_str = CURRENT_MONTH
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    df = load_upload_log()
    new_row = {
        "BBM_STD": bbm_std,
        "FILE_TYPE": file_type,
        "FILENAME": filename,
        "UPLOADED_AT": now,
        "MONTH": month_str,
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_excel(UPLOAD_LOG_FILE, index=False)

# ----------------- LOGIN -----------------
def login_form():
    st.subheader("🔐 Login")

    if not MGMT_PASSWORD and not BBM_USERS and not TIP_USERS:
        st.error(
            "Login JSON files (mgmt.json, bbm_users.json, tip_users.json) "
            "not loaded. Keep them in the same folder as TIPOS.py."
        )
        return

    # ---- VERY IMPORTANT: radio OUTSIDE form ----
    role = st.radio(
        "Login as",
        ["TIP", "BBM", "MGMT"],
        horizontal=True,
        key="login_role",
    )

    with st.form("login_form"):
        bbm_for_tip = None

        # ---------------- TIP ----------------
        if role == "TIP":
            if TIP_USERS:
                username = st.selectbox(
                    "Select TIP Name",
                    options=sorted(TIP_USERS.keys()),
                    key="tip_username",
                )
            else:
                username = st.text_input("TIP Name", key="tip_username")

            if BBM_USERS:
                bbm_for_tip = st.selectbox(
                    "Select your BBM (for filtering OS / OG list)",
                    options=sorted(BBM_USERS.keys()),
                    key="tip_bbm",
                )
            else:
                bbm_for_tip = st.text_input(
                    "BBM Name (for filtering)", key="tip_bbm_text"
                )

            pwd_label = "Enter TIP Login Code (as per tip_users.json)"

        # ---------------- BBM ----------------
        elif role == "BBM":
            if BBM_USERS:
                username = st.selectbox(
                    "Select BBM Name",
                    options=sorted(BBM_USERS.keys()),
                    key="bbm_username",
                )
            else:
                username = st.text_input("BBM Name", key="bbm_username")

            pwd_label = "Enter BBM Login Code (as per bbm_users.json)"

        # ---------------- MGMT ----------------
        else:  # MGMT
            username = st.text_input("MGMT User ID", key="mgmt_user")
            pwd_label = "Enter Management Password (from mgmt.json)"

        password = st.text_input(pwd_label, type="password", key="login_password")
        submitted = st.form_submit_button("Login")

        if not submitted:
            return

        u = username.strip()
        if not u:
            st.error("❌ Please select / enter User ID")
            return

        # ---------- AUTH ----------
        if role == "MGMT":
            if not MGMT_PASSWORD:
                st.error("❌ MGMT password not configured in mgmt.json")
                return
            if password != MGMT_PASSWORD:
                st.error("❌ Invalid MGMT password")
                return

        elif role == "BBM":
            expected = BBM_USERS.get(u)
            if expected is None:
                st.error("❌ BBM not found in bbm_users.json")
                return
            if password != expected:
                st.error("❌ Invalid code for this BBM")
                return

        elif role == "TIP":
            expected = TIP_USERS.get(u)
            if expected is None:
                st.error("❌ TIP not found in tip_users.json")
                return
            if password != expected:
                st.error("❌ Invalid code for this TIP")
                return
            if not bbm_for_tip:
                st.error("❌ Please select / enter your BBM")
                return

        # ---------- SUCCESS: reset & set session ----------
        for key in list(st.session_state.keys()):
            del st.session_state[key]

        init_session()
        st.session_state.authenticated = True
        st.session_state.role = role
        st.session_state.username = u.upper()

        if role == "BBM":
            st.session_state.current_bbm = st.session_state.username
        elif role == "TIP":
            st.session_state.current_bbm = str(bbm_for_tip).upper().strip()
        else:
            st.session_state.current_bbm = ""

        st.rerun()

if not st.session_state.authenticated:
    login_form()
    if not st.session_state.authenticated:
        st.stop()

# ----------------- LOGOUT BAR -----------------
col_logout, col_user = st.columns([1, 4])
with col_logout:
    if st.button("🚪 Logout"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        init_session()
        st.rerun()

with col_user:
    st.info(f"Logged in as **{st.session_state.role}** – `{st.session_state.username}` (BBM filter: `{st.session_state.current_bbm or 'ALL'}`)")

# ----------------- DATA LOAD (PERSIST AFTER RESTART) -----------------
def load_data():
    role = st.session_state.role

    # if already in session
    if st.session_state.os_df is not None or st.session_state.og_df is not None:
        return st.session_state.os_df, st.session_state.og_df

    os_df = None
    og_df = None

    if os.path.exists("Outstanding_latest.xlsx"):
        try:
            os_df = pd.read_excel("Outstanding_latest.xlsx")
            st.session_state.os_df = os_df
            st.session_state.os_filename = "Outstanding_latest.xlsx"
            if not st.session_state.os_uploaded_at:
                st.session_state.os_uploaded_at = "Loaded from last saved file"
        except Exception as e:
            st.warning(f"Could not read Outstanding_latest.xlsx: {e}")

    if os.path.exists("Barred_latest.xlsx"):
        try:
            og_df = pd.read_excel("Barred_latest.xlsx")
            st.session_state.og_df = og_df
            st.session_state.og_filename = "Barred_latest.xlsx"
            if not st.session_state.og_uploaded_at:
                st.session_state.og_uploaded_at = "Loaded from last saved file"
        except Exception as e:
            st.warning(f"Could not read Barred_latest.xlsx: {e}")

    if role == "BBM":
        st.subheader("📥 Upload Monthly Files (BBM Only)")

        os_file = st.file_uploader(
            "Upload **Outstanding List** (with 'Total OS' & 'PRIVATE OS' sheets)",
            type=["xls", "xlsx"],
            key="os_file",
        )
        og_file = st.file_uploader(
            "Upload **Barred Customer List** (2nd sheet = OG/IC Barred List)",
            type=["xls", "xlsx"],
            key="og_file",
        )

        # OUTSTANDING
        if os_file is not None:
            try:
                xls_os = pd.ExcelFile(os_file)
                sheet_names = xls_os.sheet_names
                sheet_total = "Total OS" if "Total OS" in sheet_names else sheet_names[-2]
                sheet_private = "PRIVATE OS" if "PRIVATE OS" in sheet_names else sheet_names[-1]

                df_total = pd.read_excel(xls_os, sheet_name=sheet_total)
                df_private = pd.read_excel(xls_os, sheet_name=sheet_private)
                os_df = pd.concat([df_total, df_private], ignore_index=True)

                st.session_state.os_df = os_df
                st.session_state.os_filename = os_file.name
                st.session_state.os_uploaded_at = datetime.now().strftime("%Y-%m-%d %H:%M")
                st.session_state.os_uploaded_by = st.session_state.username
                st.session_state.current_bbm = st.session_state.username

                log_upload(st.session_state.username, "OS", os_file.name)

                os_df.to_excel("Outstanding_latest.xlsx", index=False)
                st.success(f"✅ Outstanding List loaded (sheets used: '{sheet_total}', '{sheet_private}')")
            except Exception as e:
                st.error(f"Error reading Outstanding List file: {e}")

        # BARRED
        if og_file is not None:
            try:
                xls_og = pd.ExcelFile(og_file)
                if len(xls_og.sheet_names) < 2:
                    st.error("Barred file must have at least 2 sheets.")
                else:
                    sheet_og = xls_og.sheet_names[1]
                    og_df = pd.read_excel(xls_og, sheet_name=sheet_og)
                    st.session_state.og_df = og_df
                    st.session_state.og_filename = og_file.name
                    st.session_state.og_uploaded_at = datetime.now().strftime("%Y-%m-%d %H:%M")
                    st.session_state.og_uploaded_by = st.session_state.username
                    st.session_state.current_bbm = st.session_state.username

                    log_upload(st.session_state.username, "OG", og_file.name)

                    og_df.to_excel("Barred_latest.xlsx", index=False)
                    st.success(f"✅ Barred Customer List loaded (sheet used: '{sheet_og}')")
            except Exception as e:
                st.error(f"Error reading Barred List file: {e}")
    else:
        st.subheader("📁 Data Source")
        if os_df is None:
            st.warning("Outstanding List not loaded yet. BBM must upload once.")
        if og_df is None:
            st.warning("Barred Customer List not loaded yet. BBM must upload once.")

    return os_df, og_df

os_df_raw, og_df_raw = load_data()

# For TIP/BBM, need data to continue; for MGMT we can still show logs
if os_df_raw is None and og_df_raw is None and st.session_state.role in ("TIP", "BBM"):
    st.stop()

# ----------------- PREPROCESS -----------------
def preprocess(os_df, og_df):
    if os_df is None:
        df_os = pd.DataFrame(columns=[
            COL_OS_TIP_NAME, COL_OS_BBM, COL_OS_BA,
            COL_OS_MOBILE, COL_OS_CUST_NAME, COL_OS_ADDR, COL_OS_AMOUNT
        ])
    else:
        df_os = os_df.copy()

    if og_df is None:
        df_og = pd.DataFrame(columns=[
            COL_OG_TIP_NAME, COL_OG_BBM, COL_OG_BA,
            COL_OG_MOBILE, COL_OG_CUST_NAME, COL_OG_ADDR, COL_OG_AMOUNT
        ])
    else:
        df_og = og_df.copy()

    def clean_mobile(x):
        if pd.isna(x):
            return ""
        x = str(x).strip()
        if x.endswith(".0"):
            x = x[:-2]
        return "".join(ch for ch in x if ch.isdigit())

    if not df_os.empty:
        df_os["TIP_NAME_STD"] = df_os[COL_OS_TIP_NAME].astype(str).str.strip().str.upper()
        df_os["BBM_STD"] = df_os[COL_OS_BBM].astype(str).str.strip().str.upper()
        df_os[COL_OS_MOBILE] = df_os[COL_OS_MOBILE].apply(clean_mobile)
        df_os[COL_OS_AMOUNT] = pd.to_numeric(df_os[COL_OS_AMOUNT], errors="coerce").fillna(0)
    else:
        df_os["TIP_NAME_STD"] = []
        df_os["BBM_STD"] = []

    if not df_og.empty:
        df_og["TIP_NAME_STD"] = df_og[COL_OG_TIP_NAME].astype(str).str.strip().str.upper()
        df_og["BBM_STD"] = df_og[COL_OG_BBM].astype(str).str.strip().str.upper()
        df_og[COL_OG_MOBILE] = df_og[COL_OG_MOBILE].apply(clean_mobile)
        df_og[COL_OG_AMOUNT] = pd.to_numeric(df_og[COL_OG_AMOUNT], errors="coerce").fillna(0)
    else:
        df_og["TIP_NAME_STD"] = []
        df_og["BBM_STD"] = []

    role = st.session_state.role
    bbm_filter = st.session_state.get("current_bbm", "").upper().strip()

    if role in ("TIP", "BBM") and bbm_filter:
        if not df_os.empty:
            df_os = df_os[df_os["BBM_STD"] == bbm_filter]
        if not df_og.empty:
            df_og = df_og[df_og["BBM_STD"] == bbm_filter]

    return df_os, df_og

os_df, og_df = preprocess(os_df_raw, og_df_raw)

# ----------------- TIP VIEW -----------------
def tip_view():
    tip_name = st.session_state.username
    bbm_name = st.session_state.current_bbm

    tip_os = os_df[os_df["TIP_NAME_STD"] == tip_name].copy()
    tip_og = og_df[og_df["TIP_NAME_STD"] == tip_name].copy()

    st.subheader(f"📌 TIP Dashboard – {tip_name} (BBM: {bbm_name})")

    st.caption(
        f"📄 Outstanding List: **{st.session_state.os_filename}** "
        f"(Last updated: {st.session_state.os_uploaded_at or 'N/A'} by {st.session_state.os_uploaded_by or 'N/A'})"
    )
    st.caption(
        f"📄 Barred Customer List: **{st.session_state.og_filename}** "
        f"(Last updated: {st.session_state.og_uploaded_at or 'N/A'} by {st.session_state.og_uploaded_by or 'N/A'})"
    )
    st.caption(f"🗓 Contact log month: **{CURRENT_MONTH}** ({STATUS_FILE})")

    total_os = tip_os[COL_OS_AMOUNT].sum() if not tip_os.empty else 0
    total_og = tip_og[COL_OG_AMOUNT].sum() if not tip_og.empty else 0
    total_os_customers = len(tip_os)
    total_og_customers = len(tip_og)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("💰 Total OS (Disconnected) ₹", f"{total_os:,.2f}")
    with c2:
        st.metric("🚫 Total OG/IC Barred (Working) ₹", f"{total_og:,.2f}")
    with c3:
        st.metric("👥 OS Customers", total_os_customers)
    with c4:
        st.metric("👥 Barred Customers (Working)", total_og_customers)

    view_choice = st.radio(
        "What to show?",
        ["Both OS & Barred", "Only OS (Disconnected)", "Only Barred (Working OG/IC)"],
        horizontal=True,
    )
    show_os = view_choice in ["Both OS & Barred", "Only OS (Disconnected)"]
    show_og = view_choice in ["Both OS & Barred", "Only Barred (Working OG/IC)"]

    # OS
    if show_os:
        st.markdown("---")
        st.subheader("📴 Disconnected Customers – OS")
        status_map_os = get_status_map(tip_name, "OS")

        if tip_os.empty:
            st.info("No disconnected OS customers for this TIP.")
        else:
            for idx, row in tip_os.iterrows():
                cust_name = str(row[COL_OS_CUST_NAME])
                addr = str(row[COL_OS_ADDR])
                mobile = row[COL_OS_MOBILE]
                amount = row[COL_OS_AMOUNT]
                acc_no = str(row[COL_OS_BA])

                last_call, last_wa = status_map_os.get(acc_no, ("", ""))

                green = bool(last_call or last_wa)
                bg = "#d4ffd4" if green else "#fff7d4"

                st.markdown(
                    f"<div style='background:{bg};padding:8px;border-radius:6px;'>"
                    f"<b>{cust_name}</b> | Acc: {acc_no}<br>"
                    f"{addr}<br>"
                    f"OS: ₹{amount:,.2f}<br>"
                    f"{make_tel_link(mobile)}&nbsp;&nbsp;{make_whatsapp_link(mobile, f'Dear {cust_name}, your BSNL FTTH outstanding is Rs {amount:.2f}. Kindly pay immediately.')}"
                    f"<br><small>Last Call: {last_call or '-'} | Last WA: {last_wa or '-'}</small>"
                    "</div>",
                    unsafe_allow_html=True,
                )

                c1, c2 = st.columns(2)
                with c1:
                    if st.button("📞 Call Done", key=f"os_call_{idx}"):
                        update_status(tip_name, "OS", acc_no, update_call=True)
                        st.rerun()
                with c2:
                    if st.button("🟢 WA Sent", key=f"os_wa_{idx}"):
                        update_status(tip_name, "OS", acc_no, update_whatsapp=True)
                        st.rerun()
                st.write("")

    # OG
    if show_og:
        st.markdown("---")
        st.subheader("📡 Working Customers – OG/IC Barred")
        status_map_og = get_status_map(tip_name, "OG")

        if tip_og.empty:
            st.info("No OG/IC barred working customers for this TIP.")
        else:
            for idx, row in tip_og.iterrows():
                cust_name = str(row[COL_OG_CUST_NAME])
                addr = str(row[COL_OG_ADDR])
                mobile = row[COL_OG_MOBILE]
                amount = row[COL_OG_AMOUNT]
                acc_no = str(row[COL_OG_BA])

                last_call, last_wa = status_map_og.get(acc_no, ("", ""))

                green = bool(last_call or last_wa)
                bg = "#d4ffd4" if green else "#fff7d4"

                st.markdown(
                    f"<div style='background:{bg};padding:8px;border-radius:6px;'>"
                    f"<b>{cust_name}</b> | Acc: {acc_no}<br>"
                    f"{addr}<br>"
                    f"Outstanding: ₹{amount:,.2f}<br>"
                    f"{make_tel_link(mobile)}&nbsp;&nbsp;{make_whatsapp_link(mobile, f'Dear {cust_name}, your BSNL FTTH bill is overdue. Outstanding Rs {amount:.2f}. Kindly pay immediately.')}"
                    f"<br><small>Last Call: {last_call or '-'} | Last WA: {last_wa or '-'}</small>"
                    "</div>",
                    unsafe_allow_html=True,
                )

                c1, c2 = st.columns(2)
                with c1:
                    if st.button("📞 Call Done", key=f"og_call_{idx}"):
                        update_status(tip_name, "OG", acc_no, update_call=True)
                        st.rerun()
                with c2:
                    if st.button("🟢 WA Sent", key=f"og_wa_{idx}"):
                        update_status(tip_name, "OG", acc_no, update_whatsapp=True)
                        st.rerun()
                st.write("")

# ----------------- BBM VIEW -----------------
def bbm_view():
    bbm_name = st.session_state.username
    st.subheader(f"📌 BBM Dashboard – {bbm_name}")

    # os_df / og_df are already filtered by current_bbm in preprocess()
    global os_df, og_df

    total_os_all = os_df[COL_OS_AMOUNT].sum() if not os_df.empty else 0
    total_og_all = og_df[COL_OG_AMOUNT].sum() if not og_df.empty else 0
    total_os_cust = len(os_df)
    total_og_cust = len(og_df)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("💰 Total OS (Disconnected)", f"{total_os_all:,.2f}")
    with c2:
        st.metric("🚫 Total OG/IC Barred (Working)", f"{total_og_all:,.2f}")
    with c3:
        st.metric("👥 OS Customers", total_os_cust)
    with c4:
        st.metric("👥 Barred Customers", total_og_cust)

    # ---------- TIP-wise Summary ----------
    st.markdown("---")
    st.markdown("### 📊 TIP-wise Summary for this BBM")

    if os_df.empty and og_df.empty:
        st.info("No OS / OG data available for this BBM.")
    else:
        if not os_df.empty:
            os_tip_group = os_df.groupby("TIP_NAME_STD").agg(
                Total_OS=(COL_OS_AMOUNT, "sum"),
                OS_Customers=(COL_OS_CUST_NAME, "count"),
            )
        else:
            os_tip_group = pd.DataFrame(columns=["Total_OS", "OS_Customers"])

        if not og_df.empty:
            og_tip_group = og_df.groupby("TIP_NAME_STD").agg(
                Total_OGIC=(COL_OG_AMOUNT, "sum"),
                OG_Customers=(COL_OG_CUST_NAME, "count"),
            )
        else:
            og_tip_group = pd.DataFrame(columns=["Total_OGIC", "OG_Customers"])

        tip_summary = os_tip_group.join(og_tip_group, how="outer").fillna(0).reset_index()
        tip_summary = tip_summary.rename(columns={
            "TIP_NAME_STD": "TIP Name",
            "Total_OS": "Total OS (Disconnected) ₹",
            "Total_OGIC": "Total OG/IC Barred (Working) ₹",
        })
        st.dataframe(tip_summary, use_container_width=True)

    # ---------- TIP Drill-down with Call / WhatsApp ----------
    st.markdown("---")
    st.markdown("### 📞 Call / 💬 WhatsApp – TIP-wise Customers")

    if os_df.empty and og_df.empty:
        st.info("No customer records to show.")
    else:
        tip_names = sorted(set(
            os_df["TIP_NAME_STD"].dropna().tolist() +
            og_df["TIP_NAME_STD"].dropna().tolist()
        ))

        if not tip_names:
            st.info("No TIPs found under this BBM.")
        else:
            selected_tip = st.selectbox("Select TIP", tip_names)
            view_choice = st.radio(
                "What to show for this TIP?",
                ["Both OS & Barred", "Only OS (Disconnected)", "Only Barred (Working OG/IC)"],
                horizontal=True,
            )

            show_os = view_choice in ["Both OS & Barred", "Only OS (Disconnected)"]
            show_og = view_choice in ["Both OS & Barred", "Only Barred (Working OG/IC)"]

            tip_os = os_df[os_df["TIP_NAME_STD"] == selected_tip].copy()
            tip_og = og_df[og_df["TIP_NAME_STD"] == selected_tip].copy()

            # ---- OS section ----
            if show_os:
                st.markdown("#### 📴 Disconnected (OS) Customers")
                status_map_os = get_status_map(selected_tip, "OS")

                if tip_os.empty:
                    st.info("No OS customers for this TIP.")
                else:
                    for idx, row in tip_os.iterrows():
                        cust_name = str(row[COL_OS_CUST_NAME])
                        addr = str(row[COL_OS_ADDR])
                        mobile = row[COL_OS_MOBILE]
                        amount = row[COL_OS_AMOUNT]
                        acc_no = str(row[COL_OS_BA])

                        last_call, last_wa = status_map_os.get(acc_no, ("", ""))

                        green = bool(last_call or last_wa)
                        bg = "#d4ffd4" if green else "#fff7d4"

                        st.markdown(
                            f"<div style='background:{bg};padding:8px;border-radius:6px;'>"
                            f"<b>{cust_name}</b> | Acc: {acc_no}<br>"
                            f"{addr}<br>"
                            f"OS: ₹{amount:,.2f}<br>"
                            f"{make_tel_link(mobile)}&nbsp;&nbsp;"
                            f"{make_whatsapp_link(mobile, f'Dear {cust_name}, your BSNL FTTH outstanding is Rs {amount:.2f}. Kindly pay immediately.')}"
                            f"<br><small>Last Call: {last_call or '-'} | Last WA: {last_wa or '-'}</small>"
                            "</div>",
                            unsafe_allow_html=True,
                        )

                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button("📞 Call Done", key=f"bbm_os_call_{selected_tip}_{idx}"):
                                update_status(selected_tip, "OS", acc_no, update_call=True)
                                st.rerun()
                        with c2:
                            if st.button("🟢 WA Sent", key=f"bbm_os_wa_{selected_tip}_{idx}"):
                                update_status(selected_tip, "OS", acc_no, update_whatsapp=True)
                                st.rerun()
                        st.write("")

            # ---- OG section ----
            if show_og:
                st.markdown("#### 📡 Working (OG/IC Barred) Customers")
                status_map_og = get_status_map(selected_tip, "OG")

                if tip_og.empty:
                    st.info("No OG/IC barred customers for this TIP.")
                else:
                    for idx, row in tip_og.iterrows():
                        cust_name = str(row[COL_OG_CUST_NAME])
                        addr = str(row[COL_OG_ADDR])
                        mobile = row[COL_OG_MOBILE]
                        amount = row[COL_OG_AMOUNT]
                        acc_no = str(row[COL_OG_BA])

                        last_call, last_wa = status_map_og.get(acc_no, ("", ""))

                        green = bool(last_call or last_wa)
                        bg = "#d4ffd4" if green else "#fff7d4"

                        st.markdown(
                            f"<div style='background:{bg};padding:8px;border-radius:6px;'>"
                            f"<b>{cust_name}</b> | Acc: {acc_no}<br>"
                            f"{addr}<br>"
                            f"Outstanding: ₹{amount:,.2f}<br>"
                            f"{make_tel_link(mobile)}&nbsp;&nbsp;"
                            f"{make_whatsapp_link(mobile, f'Dear {cust_name}, your BSNL FTTH bill is overdue. Outstanding Rs {amount:.2f}. Kindly pay immediately.')}"
                            f"<br><small>Last Call: {last_call or '-'} | Last WA: {last_wa or '-'}</small>"
                            "</div>",
                            unsafe_allow_html=True,
                        )

                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button("📞 Call Done", key=f"bbm_og_call_{selected_tip}_{idx}"):
                                update_status(selected_tip, "OG", acc_no, update_call=True)
                                st.rerun()
                        with c2:
                            if st.button("🟢 WA Sent", key=f"bbm_og_wa_{selected_tip}_{idx}"):
                                update_status(selected_tip, "OG", acc_no, update_whatsapp=True)
                                st.rerun()
                        st.write("")

    # ---------- Upload Log at bottom ----------
    st.markdown("---")
    st.markdown("### 📁 BBM Upload Log (this BBM)")

    upload_df = load_upload_log()
    if upload_df.empty:
        st.info("No uploads logged yet.")
    else:
        st.dataframe(
            upload_df[upload_df["BBM_STD"] == bbm_name],
            use_container_width=True,
        )
# ----------------- MGMT VIEW -----------------
def mgmt_view():
    st.subheader("🏛 Management Dashboard (All BBMs & TIPs)")
    upload_df = load_upload_log()

    st.markdown("### 📂 BBM File Upload Summary")
    if upload_df.empty:
        st.info("No BBM uploads logged yet.")
    else:
        st.dataframe(upload_df, use_container_width=True)

    st.markdown("---")
    st.markdown("### 📞 Global TIP Contact Summary")
    sheets = load_status_all()
    if not sheets:
        st.info("No Call / WhatsApp actions recorded yet.")
        return

    month_list = sorted(sheets.keys())
    selected_month = st.selectbox("Select month:", month_list, index=month_list.index(CURRENT_MONTH) if CURRENT_MONTH in month_list else len(month_list)-1)
    df_month = sheets[selected_month].copy()
    if df_month.empty:
        st.info("No contacts in this month.")
        return

    df_month["has_call"] = df_month["LAST_CALL_TIME"].fillna("").ne("")
    df_month["has_wa"] = df_month["LAST_WHATSAPP_TIME"].fillna("").ne("")

    bbm_summary = df_month.groupby("BBM_STD").agg(
        TIPs=("TIP_NAME_STD", "nunique"),
        Accounts_Contacted=("ACCOUNT_NO", "nunique"),
        Calls_Done=("has_call", "sum"),
        WhatsApp_Sent=("has_wa", "sum"),
    ).reset_index().rename(columns={"BBM_STD": "BBM"})

    st.markdown("#### BBM-wise Summary")
    st.dataframe(bbm_summary, use_container_width=True)

# ----------------- MAIN ROLE SWITCH -----------------
if st.session_state.role == "TIP":
    tip_view()
elif st.session_state.role == "BBM":
    bbm_view()
else:  # MGMT
    mgmt_view()


