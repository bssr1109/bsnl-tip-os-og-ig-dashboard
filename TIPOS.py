import streamlit as st
import pandas as pd
import os
import io
from datetime import datetime
from urllib.parse import quote
import base64
import json
import requests  # for GitHub API

# ----------------- BASIC CONFIG -----------------
st.set_page_config(
    page_title="TIP Outstanding & OG/IC Barred Dashboard",
    layout="wide",
)

PASSWORD = "1234"
STATUS_FILE = "tip_contact_status.xlsx"   # TIP call / WhatsApp log (month-wise sheets)
UPLOAD_LOG_FILE = "bbm_upload_log.xlsx"   # BBM file upload log
CURRENT_MONTH = datetime.now().strftime("%Y-%m")  # e.g. 2025-11

# ----------------- GITHUB CONFIG -----------------
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")
GITHUB_USERNAME = st.secrets.get("GITHUB_USERNAME", "bssr1109")
GITHUB_REPO = st.secrets.get("GITHUB_REPO", "bsnl-tip-os-og-ig-dashboard")
GITHUB_BRANCH = st.secrets.get("GITHUB_BRANCH", "main")


def github_upload_file(local_path: str, repo_path: str, commit_message: str):
    """
    Upload/overwrite a file in the GitHub repo using the REST API.
    - local_path: file on this machine (e.g. 'tip_contact_status.xlsx')
    - repo_path: path inside repo (e.g. 'data/tip_contact_status.xlsx')
    """
    if not GITHUB_TOKEN:
        st.warning("GitHub token not configured – cannot sync to GitHub.")
        return

    if not os.path.exists(local_path):
        st.warning(f"GitHub sync skipped, file not found: {local_path}")
        return

    url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/{repo_path}"

    with open(local_path, "rb") as f:
        content = f.read()
    encoded = base64.b64encode(content).decode("utf-8")

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }

    # Get existing file SHA (required for update)
    r_get = requests.get(url, headers=headers)
    if r_get.status_code == 200:
        sha = r_get.json().get("sha")
    else:
        sha = None

    data = {
        "message": commit_message,
        "content": encoded,
        "branch": GITHUB_BRANCH,
    }
    if sha:
        data["sha"] = sha  # update existing file

    r_put = requests.put(url, headers=headers, data=json.dumps(data))

    if r_put.status_code in (200, 201):
        st.toast(f"✅ Synced to GitHub: {repo_path}", icon="✅")
    else:
        st.error(f"GitHub upload failed ({r_put.status_code}): {r_put.text}")


# ----------------- COLUMN NAMES (as per your Excels) -----------------
# Outstanding List (Ftth OS_25.11.2025.xlsx → Total OS + PRIVATE OS)
COL_OS_TIP_NAME = "Maintanance Franchisee Name"
COL_OS_BBM = "BBM"
COL_OS_BA = "Billing_Account_Number"
COL_OS_MOBILE = "Mobile_Number"
COL_OS_CUST_NAME = "First_Name"
COL_OS_ADDR = "Address"
COL_OS_AMOUNT = "OS_Amount(Rs)"

# Barred Customer List (OGB_ICB_02.11.2025 (1).xlsx → OG IC Barred List)
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
        "current_bbm": "",     # BBM name whose data is loaded (for TIP/BBM filtering)
        "os_df": None,         # combined Total OS + PRIVATE OS (filtered to BBM)
        "og_df": None,         # OG/IC barred (filtered to BBM)
        "os_filename": "Not loaded",
        "og_filename": "Not loaded",
        "os_uploaded_at": "",
        "og_uploaded_at": "",
        "os_uploaded_by": "",
        "og_uploaded_by": "",
        "status_sheets": None,  # dict: month_str -> DataFrame
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
    return f'<a href="tel:{mobile}">{mobile}</a>'


def make_whatsapp_link(mobile, message):
    if not mobile:
        return ""
    return f'<a href="https://wa.me/{mobile}?text={quote(message)}" target="_blank">WhatsApp</a>'


# ----------------- STATUS: LOAD / SAVE (MONTH-WISE SHEETS) -----------------
def load_status_all():
    """
    Load all monthly sheets from STATUS_FILE into a dict:
    { sheet_name (month_str) : DataFrame }
    """
    if st.session_state.status_sheets is not None:
        return st.session_state.status_sheets

    sheets = {}
    if os.path.exists(STATUS_FILE):
        xls = pd.ExcelFile(STATUS_FILE)
        for s in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=s, dtype=str)
            sheets[s] = df
    else:
        sheets = {}

    st.session_state.status_sheets = sheets
    return sheets


def save_status_all(sheets_dict):
    """
    Save the dict of month->DataFrame back to STATUS_FILE as multiple sheets.
    Then sync to GitHub.
    """
    if not sheets_dict:
        empty = pd.DataFrame(columns=[
            "TIP_NAME_STD", "BBM_STD", "SOURCE", "ACCOUNT_NO",
            "LAST_CALL_TIME", "LAST_WHATSAPP_TIME", "MONTH"
        ])
        sheets_dict[CURRENT_MONTH] = empty

    with pd.ExcelWriter(STATUS_FILE, engine="openpyxl") as writer:
        for sheet_name, df in sheets_dict.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    st.session_state.status_sheets = sheets_dict

    # 🔁 sync to GitHub
    try:
        github_upload_file(
            STATUS_FILE,
            f"data/{STATUS_FILE}",
            f"Update TIP contact status ({CURRENT_MONTH})"
        )
    except Exception as e:
        st.warning(f"Could not sync TIP status to GitHub: {e}")


def update_status(tip_name, source, account_no, update_call=False, update_whatsapp=False):
    """
    Update ONE row per (TIP_NAME_STD, BBM_STD, SOURCE, ACCOUNT_NO) for the CURRENT_MONTH.
    If row exists in that month's sheet, update times. Else create new row.
    """
    tip_name = str(tip_name).upper().strip()
    account_no = str(account_no).strip()
    source = source.upper()   # "OS" or "OG"
    bbm_name = st.session_state.get("current_bbm", "").upper().strip()

    sheets = load_status_all()
    month_str = CURRENT_MONTH

    # Get the sheet for this month or create new
    if month_str in sheets:
        df = sheets[month_str].copy()
    else:
        df = pd.DataFrame(columns=[
            "TIP_NAME_STD", "BBM_STD", "SOURCE", "ACCOUNT_NO",
            "LAST_CALL_TIME", "LAST_WHATSAPP_TIME", "MONTH"
        ])

    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M")

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
    """
    Returns dict: account_no -> (last_call_time, last_whatsapp_time)
    for a given TIP & source ("OS" or "OG") in a given month (default CURRENT_MONTH),
    filtered to the current_bbm.
    """
    if month_str is None:
        month_str = CURRENT_MONTH

    sheets = load_status_all()
    tip_name = str(tip_name).upper().strip()
    bbm_name = st.session_state.get("current_bbm", "").upper().strip()

    if month_str not in sheets or sheets[month_str].empty:
        return {}

    df = sheets[month_str]
    if "BBM_STD" not in df.columns:
        return {}

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


# ----------------- BBM UPLOAD LOG (PERSISTENT + GITHUB) -----------------
def log_upload(bbm_name, file_type, filename):
    """
    Append a row to UPLOAD_LOG_FILE whenever a BBM uploads OS/OG file.
    file_type: "OS" or "OG"
    """
    bbm_std = str(bbm_name).upper().strip()
    month_str = CURRENT_MONTH
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    if os.path.exists(UPLOAD_LOG_FILE):
        df = pd.read_excel(UPLOAD_LOG_FILE, dtype=str)
    else:
        df = pd.DataFrame(columns=["BBM_STD", "FILE_TYPE", "FILENAME", "UPLOADED_AT", "MONTH"])

    new_row = {
        "BBM_STD": bbm_std,
        "FILE_TYPE": file_type,
        "FILENAME": filename,
        "UPLOADED_AT": now,
        "MONTH": month_str,
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_excel(UPLOAD_LOG_FILE, index=False)

    # sync to GitHub
    try:
        github_upload_file(
            UPLOAD_LOG_FILE,
            f"data/{UPLOAD_LOG_FILE}",
            "Update BBM upload log"
        )
    except Exception as e:
        st.warning(f"Could not sync BBM upload log to GitHub: {e}")


def load_upload_log():
    if os.path.exists(UPLOAD_LOG_FILE):
        return pd.read_excel(UPLOAD_LOG_FILE, dtype=str)
    else:
        return pd.DataFrame(columns=["BBM_STD", "FILE_TYPE", "FILENAME", "UPLOADED_AT", "MONTH"])


# ----------------- LOGIN -----------------
def login_form():
    st.subheader("🔐 Login")

    with st.form("login_form"):
        role = st.radio("Login as", ["TIP", "BBM", "MGMT"], horizontal=True)
        username = st.text_input("User ID (TIP Name / BBM Name / MGMT Name)")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

        if submitted:
            if password != PASSWORD:
                st.error("❌ Invalid password")
            else:
                u = username.strip()
                if not u:
                    st.error("❌ Please enter User ID")
                else:
                    st.session_state.authenticated = True
                    st.session_state.role = role
                    st.session_state.username = u.upper()
                    if role == "BBM":
                        st.session_state.current_bbm = st.session_state.username
                    st.success(f"✅ Logged in as {role}: {u}")
                    st.rerun()


if not st.session_state.authenticated:
    login_form()
    st.stop()


# ----------------- LOGOUT BAR -----------------
col_logout, col_user = st.columns([1, 4])
with col_logout:
    if st.button("🚪 Logout"):
        st.session_state.authenticated = False
        st.session_state.role = None
        st.session_state.username = None
        st.rerun()

with col_user:
    st.info(f"Logged in as **{st.session_state.role}** – `{st.session_state.username}`")


# ----------------- DATA LOAD (BBM uploads) -----------------
def load_data():
    role = st.session_state.role

    if role == "BBM":
        st.subheader("📥 Upload Monthly Files (BBM Only)")

        os_file = st.file_uploader(
            "Upload **Outstanding List** Excel for the month (with 'Total OS' & 'PRIVATE OS' sheets)",
            type=["xls", "xlsx"],
            key="os_file",
        )
        og_file = st.file_uploader(
            "Upload **Barred Customer List** Excel for the month (2nd sheet = OG/IC Barred List)",
            type=["xls", "xlsx"],
            key="og_file",
        )

        # ---- OUTSTANDING LIST FILE: Total OS + PRIVATE OS ----
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

                # Save local copy and sync to GitHub
                local_os_copy = "Outstanding_latest.xlsx"
                os_df.to_excel(local_os_copy, index=False)
                try:
                    github_upload_file(
                        local_os_copy,
                        f"monthly_data/{CURRENT_MONTH}/Outstanding_{st.session_state.username}.xlsx",
                        f"BBM {st.session_state.username} uploaded Outstanding list for {CURRENT_MONTH}"
                    )
                    github_upload_file(
                        local_os_copy,
                        "latest/Outstanding_latest.xlsx",
                        "Update latest Outstanding list"
                    )
                except Exception as e:
                    st.warning(f"Could not sync OS file to GitHub: {e}")

                st.success(
                    f"✅ Outstanding List loaded (sheets used: '{sheet_total}', '{sheet_private}')"
                )
            except Exception as e:
                st.error(f"Error reading Outstanding List file: {e}")

        # ---- BARRED CUSTOMER LIST FILE: 2nd sheet ----
        if og_file is not None:
            try:
                xls_og = pd.ExcelFile(og_file)
                if len(xls_og.sheet_names) < 2:
                    st.error("Barred Customer List file must have at least 2 sheets.")
                else:
                    sheet_og = xls_og.sheet_names[1]
                    og_df = pd.read_excel(xls_og, sheet_name=sheet_og)
                    st.session_state.og_df = og_df
                    st.session_state.og_filename = og_file.name
                    st.session_state.og_uploaded_at = datetime.now().strftime("%Y-%m-%d %H:%M")
                    st.session_state.og_uploaded_by = st.session_state.username
                    st.session_state.current_bbm = st.session_state.username

                    log_upload(st.session_state.username, "OG", og_file.name)

                    # Save local copy and sync to GitHub
                    local_og_copy = "Barred_latest.xlsx"
                    og_df.to_excel(local_og_copy, index=False)
                    try:
                        github_upload_file(
                            local_og_copy,
                            f"monthly_data/{CURRENT_MONTH}/Barred_{st.session_state.username}.xlsx",
                            f"BBM {st.session_state.username} uploaded Barred list for {CURRENT_MONTH}"
                        )
                        github_upload_file(
                            local_og_copy,
                            "latest/Barred_latest.xlsx",
                            "Update latest Barred list"
                        )
                    except Exception as e:
                        st.warning(f"Could not sync OG file to GitHub: {e}")

                    st.success(
                        f"✅ Barred Customer List loaded (sheet used: '{sheet_og}')"
                    )
            except Exception as e:
                st.error(f"Error reading Barred Customer List file: {e}")

    else:
        st.subheader("📁 Data Source")
        if st.session_state.os_df is None:
            st.warning("Outstanding List (disconnected OS) not loaded yet. BBM must upload.")
        if st.session_state.og_df is None:
            st.warning("Barred Customer List (working OG/IC barred) not loaded yet. BBM must upload.")

    return st.session_state.os_df, st.session_state.og_df


os_df_raw, og_df_raw = load_data()

# For TIP/BBM, need data to continue; for MGMT we can still show logs
if os_df_raw is None and og_df_raw is None and st.session_state.role in ("TIP", "BBM"):
    st.stop()


# ----------------- PREPROCESS -----------------
def preprocess(os_df, og_df):
    # If file not uploaded, create an empty dataframe with correct columns
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

    if not df_os.empty:
        req_os = [COL_OS_TIP_NAME, COL_OS_BBM, COL_OS_BA,
                  COL_OS_MOBILE, COL_OS_CUST_NAME, COL_OS_ADDR, COL_OS_AMOUNT]
        missing_os = [c for c in req_os if c not in df_os.columns]
        if missing_os:
            st.error(f"OS file missing columns: {missing_os}")
            st.stop()

    if not df_og.empty:
        req_og = [COL_OG_TIP_NAME, COL_OG_BBM, COL_OG_BA,
                  COL_OG_MOBILE, COL_OG_CUST_NAME, COL_OG_ADDR, COL_OG_AMOUNT]
        missing_og = [c for c in req_og if c not in df_og.columns]
        if missing_og:
            st.error(f"Barred Customer List file missing columns: {missing_og}")
            st.stop()

    if not df_os.empty:
        df_os["TIP_NAME_STD"] = df_os[COL_OS_TIP_NAME].astype(str).str.strip().str.upper()
        df_os["BBM_STD"] = df_os[COL_OS_BBM].astype(str).str.strip().str.upper()
        df_os[COL_OS_AMOUNT] = pd.to_numeric(df_os[COL_OS_AMOUNT], errors="coerce").fillna(0)
    else:
        df_os["TIP_NAME_STD"] = []
        df_os["BBM_STD"] = []

    if not df_og.empty:
        df_og["TIP_NAME_STD"] = df_og[COL_OG_TIP_NAME].astype(str).str.strip().str.upper()
        df_og["BBM_STD"] = df_og[COL_OG_BBM].astype(str).str.strip().str.upper()
        df_og[COL_OG_AMOUNT] = pd.to_numeric(df_og[COL_OG_AMOUNT], errors="coerce").fillna(0)
    else:
        df_og["TIP_NAME_STD"] = []
        df_og["BBM_STD"] = []

    def clean_mobile(x):
        if pd.isna(x):
            return ""
        x = str(x).strip()
        if x.endswith(".0"):
            x = x[:-2]
        x = ''.join(ch for ch in x if ch.isdigit())
        return x

    if not df_os.empty:
        df_os[COL_OS_MOBILE] = df_os[COL_OS_MOBILE].apply(clean_mobile)
    if not df_og.empty:
        df_og[COL_OG_MOBILE] = df_og[COL_OG_MOBILE].apply(clean_mobile)

    role = st.session_state.role
    bbm_filter = st.session_state.get("current_bbm", "").upper().strip()

    # TIP/BBM views are restricted to current BBM
    if role in ("TIP", "BBM") and bbm_filter:
        if not df_os.empty:
            df_os = df_os[df_os["BBM_STD"] == bbm_filter]
        if not df_og.empty:
            df_og = df_og[df_og["BBM_STD"] == bbm_filter]
    # MGMT sees combined

    return df_os, df_og


os_df, og_df = preprocess(os_df_raw, og_df_raw)


# ----------------- TIP VIEW -----------------
def tip_view():
    tip_name = st.session_state.username  # upper
    bbm_name = st.session_state.get("current_bbm", "")

    tip_os = os_df[os_df["TIP_NAME_STD"] == tip_name].copy()
    tip_og = og_df[og_df["TIP_NAME_STD"] == tip_name].copy()

    if tip_os.empty and tip_og.empty:
        st.error(
            f"No records found for TIP Name: `{tip_name}` under BBM `{bbm_name}`.\n"
            "Check that login name exactly matches the TIP name in Excel and BBM has uploaded his data."
        )
        return

    st.subheader(f"📌 TIP Dashboard – {tip_name} (BBM: {bbm_name or 'N/A'})")

    st.caption(
        f"📄 Outstanding List: **{st.session_state.os_filename}** "
        f"(Last updated: {st.session_state.os_uploaded_at or 'N/A'} by {st.session_state.os_uploaded_by or 'N/A'})"
    )
    st.caption(
        f"📄 Barred Customer List: **{st.session_state.og_filename}** "
        f"(Last updated: {st.session_state.og_uploaded_at or 'N/A'} by {st.session_state.og_uploaded_by or 'N/A'})"
    )
    st.caption(f"🗓 Contact log month: **{CURRENT_MONTH}** ({STATUS_FILE} synced to GitHub)")

    total_os = tip_os[COL_OS_AMOUNT].sum() if not tip_os.empty else 0
    total_og = tip_og[COL_OG_AMOUNT].sum() if not tip_og.empty else 0
    total_os_customers = len(tip_os) if not tip_os.empty else 0
    total_og_customers = len(tip_og) if not tip_og.empty else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("💰 Total OS (Disconnected) ₹", f"{total_os:,.2f}")
    with c2:
        st.metric("🚫 Total OG/IC Barred (Working) ₹", f"{total_og:,.2f}")
    with c3:
        st.metric("👥 OS Customers", total_os_customers)
    with c4:
        st.metric("👥 Barred Customers (Working)", total_og_customers)

    # TIP CONTACT SUMMARY + DOWNLOAD (THIS MONTH)
    st.markdown("### 📈 My Contact Summary (This Month)")
    sheets = load_status_all()
    df_tip_log = pd.DataFrame()
    bbm_filter = st.session_state.get("current_bbm", "").upper().strip()

    if CURRENT_MONTH in sheets:
        df_month = sheets[CURRENT_MONTH]
        if not df_month.empty and "BBM_STD" in df_month.columns:
            df_tip_log = df_month[
                (df_month["TIP_NAME_STD"] == tip_name) &
                (df_month["BBM_STD"] == bbm_filter)
            ].copy()

    if df_tip_log.empty:
        st.info("No Call / WhatsApp actions recorded for you in this month.")
    else:
        df_tmp = df_tip_log.copy()
        calls = df_tmp["LAST_CALL_TIME"].fillna("").ne("")
        wapps = df_tmp["LAST_WHATSAPP_TIME"].fillna("").ne("")
        total_accounts = df_tmp["ACCOUNT_NO"].nunique()
        total_calls = calls.sum()
        total_wapps = wapps.sum()

        csa, csb, csc = st.columns(3)
        with csa:
            st.metric("Accounts with some contact", total_accounts)
        with csb:
            st.metric("Call Done entries", int(total_calls))
        with csc:
            st.metric("WhatsApp Sent entries", int(total_wapps))

        st.caption("🧾 Detailed log (per account) – this TIP, this BBM, this month:")
        st.dataframe(df_tip_log, use_container_width=True)

        excel_bytes_tip = df_to_excel_bytes(df_tip_log, sheet_name=CURRENT_MONTH)
        st.download_button(
            label="⬇️ Download my contact log (Excel)",
            data=excel_bytes_tip,
            file_name=f"{tip_name}_contact_log_{CURRENT_MONTH}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    st.markdown("### 👀 What do you want to view?")
    view_choice = st.radio(
        "Select:",
        ["Both OS & Barred", "Only OS (Disconnected)", "Only Barred (Working OG/IC)"],
        horizontal=False,
    )

    show_os = view_choice in ["Both OS & Barred", "Only OS (Disconnected)"]
    show_og = view_choice in ["Both OS & Barred", "Only Barred (Working OG/IC)"]

    # SECTION 1: DISCONNECTED OS CUSTOMERS
    if show_os:
        st.markdown("---")
        st.subheader("📴 Disconnected Customers – OS (Total OS + PRIVATE OS)")
        st.caption("📞 After actually calling or sending WhatsApp, press the respective button to record it.")

        status_map_os = get_status_map(tip_name, "OS")

        if tip_os.empty:
            st.info("No disconnected OS customers for this TIP in Outstanding List.")
        else:
            for idx, row in tip_os.iterrows():
                cust_name = str(row[COL_OS_CUST_NAME])
                addr = str(row[COL_OS_ADDR])
                mobile = row[COL_OS_MOBILE]
                amount = row[COL_OS_AMOUNT]
                acc_no = str(row[COL_OS_BA])

                last_call, last_wa = status_map_os.get(acc_no, ("", ""))

                c1, c2, c3, c4, c5 = st.columns([3, 4, 2, 2, 3])

                with c1:
                    st.write(f"**{cust_name}**")
                    st.write(addr)
                    st.write(f"Acc: `{acc_no}`")

                with c2:
                    st.write(f"OS: ₹{amount:,.2f}")
                    st.markdown(make_tel_link(mobile), unsafe_allow_html=True)
                    msg = f"Dear {cust_name}, your BSNL FTTH outstanding is Rs {amount:.2f}. Kindly pay immediately."
                    st.markdown(make_whatsapp_link(mobile, msg), unsafe_allow_html=True)

                with c3:
                    if st.button("Call Done", key=f"os_call_{idx}"):
                        update_status(tip_name, "OS", acc_no, update_call=True)
                        st.rerun()

                with c4:
                    if st.button("WA Sent", key=f"os_wa_{idx}"):
                        update_status(tip_name, "OS", acc_no, update_whatsapp=True)
                        st.rerun()

                with c5:
                    if last_call:
                        st.write(f"📞 Last Call: {last_call}")
                    if last_wa:
                        st.write(f"💬 Last WA: {last_wa}")

    # SECTION 2: WORKING OG/IC BARRED CUSTOMERS
    if show_og:
        st.markdown("---")
        st.subheader("📡 Working Customers – OG/IC Barred (Payment Overdue)")
        st.caption("📞 After actually calling or sending WhatsApp, press the respective button to record it.")

        status_map_og = get_status_map(tip_name, "OG")

        if tip_og.empty:
            st.info("No OG/IC barred working customers for this TIP in Barred Customer List.")
        else:
            for idx, row in tip_og.iterrows():
                cust_name = str(row[COL_OG_CUST_NAME])
                addr = str(row[COL_OG_ADDR])
                mobile = row[COL_OG_MOBILE]
                amount = row[COL_OG_AMOUNT]
                acc_no = str(row[COL_OG_BA])

                last_call, last_wa = status_map_og.get(acc_no, ("", ""))

                c1, c2, c3, c4, c5 = st.columns([3, 4, 2, 2, 3])

                with c1:
                    st.write(f"**{cust_name}**")
                    st.write(addr)
                    st.write(f"Acc: `{acc_no}`")

                with c2:
                    st.write(f"Outstanding: ₹{amount:,.2f}")
                    st.markdown(make_tel_link(mobile), unsafe_allow_html=True)
                    msg = f"Dear {cust_name}, your BSNL FTTH bill is overdue. Outstanding Rs {amount:.2f}. Kindly pay immediately."
                    st.markdown(make_whatsapp_link(mobile, msg), unsafe_allow_html=True)

                with c3:
                    if st.button("Call Done", key=f"og_call_{idx}"):
                        update_status(tip_name, "OG", acc_no, update_call=True)
                        st.rerun()

                with c4:
                    if st.button("WA Sent", key=f"og_wa_{idx}"):
                        update_status(tip_name, "OG", acc_no, update_whatsapp=True)
                        st.rerun()

                with c5:
                    if last_call:
                        st.write(f"📞 Last Call: {last_call}")
                    if last_wa:
                        st.write(f"💬 Last WA: {last_wa}")


# ----------------- BBM VIEW -----------------
def bbm_view():
    bbm_name = st.session_state.username
    st.subheader(f"📌 BBM Dashboard – {bbm_name}")

    os_name = st.session_state.get("os_filename", "Not loaded")
    og_name = st.session_state.get("og_filename", "Not loaded")

    st.caption(
        f"📄 Outstanding List: **{os_name}** "
        f"(Last updated: {st.session_state.os_uploaded_at or 'N/A'} by {st.session_state.os_uploaded_by or 'N/A'})"
    )
    st.caption(
        f"📄 Barred Customer List: **{og_name}** "
        f"(Last updated: {st.session_state.og_uploaded_at or 'N/A'} by {st.session_state.og_uploaded_by or 'N/A'})"
    )

    total_os_all = os_df[COL_OS_AMOUNT].sum() if not os_df.empty else 0
    total_og_all = og_df[COL_OG_AMOUNT].sum() if not og_df.empty else 0
    total_os_cust = len(os_df)
    total_og_cust = len(og_df)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("💰 Total OS (Disconnected) – This BBM", f"{total_os_all:,.2f}")
    with c2:
        st.metric("🚫 Total OG/IC Barred (Working) – This BBM", f"{total_og_all:,.2f}")
    with c3:
        st.metric("👥 OS Customers (Disconnected)", total_os_cust)
    with c4:
        st.metric("👥 Barred Customers (Working)", total_og_cust)

    st.markdown("---")
    st.markdown("### 📋 TIP-wise Summary (This BBM Only)")

    if not os_df.empty:
        os_tip_group = os_df.groupby("TIP_NAME_STD").agg(
            Total_OS=(COL_OS_AMOUNT, "sum"),
            OS_Customers=(COL_OS_CUST_NAME, "count")
        )
    else:
        os_tip_group = pd.DataFrame(columns=["Total_OS", "OS_Customers"])

    if not og_df.empty:
        og_tip_group = og_df.groupby("TIP_NAME_STD").agg(
            Total_OGIC=(COL_OG_AMOUNT, "sum"),
            OG_Customers=(COL_OG_CUST_NAME, "count")
        )
    else:
        og_tip_group = pd.DataFrame(columns=["Total_OGIC", "OG_Customers"])

    tip_summary = os_tip_group.join(og_tip_group, how="outer").fillna(0).reset_index()
    if not tip_summary.empty:
        tip_summary = tip_summary.rename(columns={
            "TIP_NAME_STD": "TIP Name",
            "Total_OS": "Total OS (Disconnected) ₹",
            "Total_OGIC": "Total OG/IC Barred (Working) ₹",
        })
    st.dataframe(tip_summary, use_container_width=True)

    # Call / WhatsApp status at BBM side
    st.markdown("---")
    st.markdown("### 📞 Call / 💬 WhatsApp Status – This BBM")

    sheets = load_status_all()
    if not sheets:
        st.info("No Call / WhatsApp actions recorded yet by TIPs.")
    else:
        month_list = sorted(sheets.keys())
        selected_month = st.selectbox(
            "Select month sheet:",
            month_list,
            index=month_list.index(CURRENT_MONTH) if CURRENT_MONTH in month_list else len(month_list) - 1,
        )
        df_month = sheets[selected_month]

        if "BBM_STD" in df_month.columns:
            df_month_bbm = df_month[df_month["BBM_STD"] == bbm_name.upper()].copy()
        else:
            df_month_bbm = df_month.copy()

        st.caption(f"🗓 Showing log for month: **{selected_month}** ({STATUS_FILE})")

        if df_month_bbm.empty:
            st.info("No contacts recorded for this BBM in the selected month.")
        else:
            st.markdown("#### 📈 TIP Contact Summary (This Month, This BBM)")
            df_tmp = df_month_bbm.copy()
            df_tmp["has_call"] = df_tmp["LAST_CALL_TIME"].fillna("").ne("")
            df_tmp["has_wa"] = df_tmp["LAST_WHATSAPP_TIME"].fillna("").ne("")

            summary = df_tmp.groupby("TIP_NAME_STD").agg(
                Accounts_Contacted=("ACCOUNT_NO", "nunique"),
                Calls_Done=("has_call", "sum"),
                WhatsApp_Sent=("has_wa", "sum"),
            ).reset_index()

            summary = summary.rename(columns={"TIP_NAME_STD": "TIP Name"})

            st.dataframe(summary, use_container_width=True)

            st.markdown("#### 🧾 Detailed TIP Contact Log (This Month, This BBM)")
            st.dataframe(df_month_bbm, use_container_width=True)

            excel_bytes_bbm = df_to_excel_bytes(df_month_bbm, sheet_name=selected_month)
            st.download_button(
                label="⬇️ Download TIP contact log for this month (Excel)",
                data=excel_bytes_bbm,
                file_name=f"{bbm_name}_TIP_contact_log_{selected_month}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    st.markdown("---")
    st.markdown("### 🔍 Drill-down into a TIP (This BBM Only)")

    if not os_df.empty or not og_df.empty:
        tip_names = sorted(set(
            os_df["TIP_NAME_STD"].dropna().tolist() +
            og_df["TIP_NAME_STD"].dropna().tolist()
        ))
    else:
        tip_names = []

    selected_tip = st.selectbox("Select TIP to view details", tip_names)

    if selected_tip:
        old_username = st.session_state.username
        old_role = st.session_state.role

        st.session_state.username = selected_tip
        st.session_state.role = "TIP"

        tip_view()

        st.session_state.username = old_username
        st.session_state.role = old_role

    st.markdown("---")
    if st.button("➡️ Go to TIP login screen"):
        st.session_state.authenticated = False
        st.session_state.role = None
        st.session_state.username = None
        st.rerun()


# ----------------- MGMT VIEW -----------------
def mgmt_view():
    st.subheader("🏛 Management Dashboard (All BBMs & TIPs)")

    # BBM Upload Summary
    st.markdown("### 📂 BBM File Upload Summary (All BBMs)")
    upload_df = load_upload_log()

    if upload_df.empty:
        st.info("No BBM uploads logged yet.")
    else:
        df_latest = (
            upload_df.sort_values("UPLOADED_AT")
            .groupby(["BBM_STD", "FILE_TYPE"], as_index=False)
            .tail(1)
            .sort_values(["BBM_STD", "FILE_TYPE"])
        )
        st.caption("Latest upload per BBM & file type:")
        st.dataframe(df_latest, use_container_width=True)

        st.caption("Full upload log:")
        st.dataframe(upload_df, use_container_width=True)

        excel_bytes_upload = df_to_excel_bytes(upload_df, sheet_name="Uploads")
        st.download_button(
            label="⬇️ Download full BBM upload log (Excel)",
            data=excel_bytes_upload,
            file_name="BBM_Upload_Log.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    st.markdown("---")

    # Global Contact Summary
    st.markdown("### 📞 Global TIP Contact Summary (All BBMs & TIPs)")
    sheets = load_status_all()
    if not sheets:
        st.info("No Call / WhatsApp actions recorded yet.")
        return

    month_list = sorted(sheets.keys())
    selected_month = st.selectbox(
        "Select month:",
        month_list,
        index=month_list.index(CURRENT_MONTH) if CURRENT_MONTH in month_list else len(month_list) - 1,
    )
    df_month = sheets[selected_month].copy()

    if df_month.empty:
        st.info("No contacts recorded in this month.")
        return

    df_month["has_call"] = df_month["LAST_CALL_TIME"].fillna("").ne("")
    df_month["has_wa"] = df_month["LAST_WHATSAPP_TIME"].fillna("").ne("")

    total_accounts = df_month["ACCOUNT_NO"].nunique()
    total_calls = df_month["has_call"].sum()
    total_wapps = df_month["has_wa"].sum()
    total_tips = df_month["TIP_NAME_STD"].nunique()
    total_bbms = df_month["BBM_STD"].nunique()

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("BBMs Active", total_bbms)
    with c2:
        st.metric("TIPs Active", total_tips)
    with c3:
        st.metric("Accounts Contacted", total_accounts)
    with c4:
        st.metric("Calls Logged", int(total_calls))
    with c5:
        st.metric("WhatsApps Logged", int(total_wapps))

    st.markdown("#### 📈 BBM-wise Summary")
    bbm_summary = df_month.groupby("BBM_STD").agg(
        TIPs=("TIP_NAME_STD", "nunique"),
        Accounts_Contacted=("ACCOUNT_NO", "nunique"),
        Calls_Done=("has_call", "sum"),
        WhatsApp_Sent=("has_wa", "sum"),
    ).reset_index().rename(columns={"BBM_STD": "BBM"})
    st.dataframe(bbm_summary, use_container_width=True)

    st.markdown("#### 📊 TIP-wise Summary (All BBMs)")
    tip_summary = df_month.groupby(["BBM_STD", "TIP_NAME_STD"]).agg(
        Accounts_Contacted=("ACCOUNT_NO", "nunique"),
        Calls_Done=("has_call", "sum"),
        WhatsApp_Sent=("has_wa", "sum"),
    ).reset_index().rename(columns={"BBM_STD": "BBM", "TIP_NAME_STD": "TIP Name"})
    st.dataframe(tip_summary, use_container_width=True)

    st.markdown("#### 🧾 Full TIP Contact Log (Selected Month)")
    st.dataframe(df_month, use_container_width=True)

    excel_bytes_month = df_to_excel_bytes(df_month, sheet_name=selected_month)
    st.download_button(
        label="⬇️ Download full TIP contact log for this month (Excel)",
        data=excel_bytes_month,
        file_name=f"All_TIP_Contact_Log_{selected_month}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ----------------- MAIN ROLE SWITCH -----------------
if st.session_state.role == "TIP":
    tip_view()
elif st.session_state.role == "BBM":
    bbm_view()
else:  # MGMT
    mgmt_view()
