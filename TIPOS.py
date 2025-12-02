import streamlit as st
import pandas as pd
import os
import io
from datetime import datetime
from urllib.parse import quote
import base64
import json
import requests

# ----------------- BASIC CONFIG -----------------
st.set_page_config(
    page_title="TIP Outstanding & OG/IC Barred Dashboard",
    layout="wide",
)

PASSWORD = "1234"
STATUS_FILE = "tip_contact_status.xlsx"   # TIP call / WhatsApp log (month-wise sheets)
UPLOAD_LOG_FILE = "bbm_upload_log.xlsx"   # BBM file upload log
CURRENT_MONTH = datetime.now().strftime("%Y-%m")  # e.g. 2025-12

# ----------------- OPTIONAL GITHUB CONFIG (SAFE) -----------------
try:
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    GITHUB_USERNAME = st.secrets.get("GITHUB_USERNAME", "bssr1109")
    GITHUB_REPO = st.secrets.get("GITHUB_REPO", "bsnl-tip-os-og-ig-dashboard")
    GITHUB_BRANCH = st.secrets.get("GITHUB_BRANCH", "main")
except Exception:
    # If not configured, sync is simply disabled
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
    GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "bssr1109")
    GITHUB_REPO = os.getenv("GITHUB_REPO", "bsnl-tip-os-og-ig-dashboard")
    GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")


def github_upload_file(local_path: str, repo_path: str, commit_message: str):
    """Upload/overwrite a file in the GitHub repo. If no token, silently skip."""
    if not GITHUB_TOKEN:
        return
    if not os.path.exists(local_path):
        return

    url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/{repo_path}"

    with open(local_path, "rb") as f:
        content = f.read()
    encoded = base64.b64encode(content).decode("utf-8")

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }

    r_get = requests.get(url, headers=headers)
    sha = r_get.json().get("sha") if r_get.status_code == 200 else None

    data = {
        "message": commit_message,
        "content": encoded,
        "branch": GITHUB_BRANCH,
    }
    if sha:
        data["sha"] = sha

    r_put = requests.put(url, headers=headers, data=json.dumps(data))
    if r_put.status_code not in (200, 201):
        st.warning(f"GitHub upload failed ({r_put.status_code}): {r_put.text}")


# ----------------- COLUMN NAMES (as per your Excels) -----------------
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
        "os_df": None,         # cleaned OS (all BBMs)
        "og_df": None,         # cleaned OG (all BBMs)
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


# ----------------- UTIL HELPERS -----------------
def df_to_excel_bytes(df, sheet_name="Sheet1"):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    buf.seek(0)
    return buf.getvalue()


def make_tel_link(mobile):
    if not mobile:
        return ""
    return f'<a href="tel:{mobile}">{mobile}</a>'


def make_whatsapp_link(mobile, message):
    if not mobile:
        return ""
    return f'<a href="https://wa.me/{mobile}?text={quote(message)}" target="_blank">WhatsApp</a>'


# ----------------- STATUS FILE (TIP CALL / WA LOG) -----------------
def load_status_all():
    if st.session_state.status_sheets is not None:
        return st.session_state.status_sheets

    sheets = {}
    if os.path.exists(STATUS_FILE):
        xls = pd.ExcelFile(STATUS_FILE)
        for s in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=s, dtype=str)
            sheets[s] = df
    st.session_state.status_sheets = sheets
    return sheets


def save_status_all(sheets):
    if not sheets:
        sheets = {
            CURRENT_MONTH: pd.DataFrame(
                columns=[
                    "TIP_NAME_STD", "BBM_STD", "SOURCE", "ACCOUNT_NO",
                    "LAST_CALL_TIME", "LAST_WHATSAPP_TIME", "MONTH"
                ]
            )
        }

    with pd.ExcelWriter(STATUS_FILE, engine="openpyxl") as writer:
        for sheet_name, df in sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    st.session_state.status_sheets = sheets
    try:
        github_upload_file(
            STATUS_FILE,
            f"data/{STATUS_FILE}",
            f"Update TIP contact status ({CURRENT_MONTH})",
        )
    except Exception as e:
        st.warning(f"Could not sync TIP status to GitHub: {e}")


def update_status(tip_name, bbm_name, source, account_no,
                  update_call=False, update_whatsapp=False):
    tip_name = str(tip_name).upper().strip()
    bbm_name = str(bbm_name).upper().strip()
    account_no = str(account_no).strip()
    source = source.upper()  # "OS" / "OG"

    sheets = load_status_all()
    month_str = CURRENT_MONTH

    if month_str in sheets:
        df = sheets[month_str].copy()
    else:
        df = pd.DataFrame(
            columns=[
                "TIP_NAME_STD", "BBM_STD", "SOURCE", "ACCOUNT_NO",
                "LAST_CALL_TIME", "LAST_WHATSAPP_TIME", "MONTH"
            ]
        )

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    if not df.empty:
        mask = (
            (df["TIP_NAME_STD"] == tip_name)
            & (df["BBM_STD"] == bbm_name)
            & (df["SOURCE"] == source)
            & (df["ACCOUNT_NO"] == account_no)
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


def get_status_map(tip_name, bbm_name, source, month_str=None):
    if month_str is None:
        month_str = CURRENT_MONTH

    tip_name = str(tip_name).upper().strip()
    bbm_name = str(bbm_name).upper().strip()
    source = source.upper()

    sheets = load_status_all()
    if month_str not in sheets or sheets[month_str].empty:
        return {}

    df = sheets[month_str]
    if "BBM_STD" not in df.columns:
        return {}

    df_sub = df[
        (df["TIP_NAME_STD"] == tip_name)
        & (df["BBM_STD"] == bbm_name)
        & (df["SOURCE"] == source)
    ]

    m = {}
    for _, row in df_sub.iterrows():
        acc = str(row["ACCOUNT_NO"])
        m[acc] = (
            row.get("LAST_CALL_TIME", ""),
            row.get("LAST_WHATSAPP_TIME", ""),
        )
    return m


# ----------------- BBM UPLOAD LOG -----------------
def log_upload(bbm_name, file_type, filename):
    bbm_std = str(bbm_name).upper().strip()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    if os.path.exists(UPLOAD_LOG_FILE):
        df = pd.read_excel(UPLOAD_LOG_FILE, dtype=str)
    else:
        df = pd.DataFrame(
            columns=["BBM_STD", "FILE_TYPE", "FILENAME", "UPLOADED_AT", "MONTH"]
        )

    new_row = {
        "BBM_STD": bbm_std,
        "FILE_TYPE": file_type,
        "FILENAME": filename,
        "UPLOADED_AT": now,
        "MONTH": CURRENT_MONTH,
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_excel(UPLOAD_LOG_FILE, index=False)

    try:
        github_upload_file(
            UPLOAD_LOG_FILE,
            f"data/{UPLOAD_LOG_FILE}",
            "Update BBM upload log",
        )
    except Exception as e:
        st.warning(f"Could not sync BBM upload log to GitHub: {e}")


def load_upload_log():
    if os.path.exists(UPLOAD_LOG_FILE):
        return pd.read_excel(UPLOAD_LOG_FILE, dtype=str)
    return pd.DataFrame(
        columns=["BBM_STD", "FILE_TYPE", "FILENAME", "UPLOADED_AT", "MONTH"]
    )


# ----------------- LOGIN -----------------
def login_form():
    st.subheader("🔐 Login")

    with st.form("login_form"):
        role = st.radio("Login as", ["TIP", "BBM", "MGMT"], horizontal=True)
        username = st.text_input("User ID (TIP Name / BBM Name / MGMT)")
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
                    st.success(f"✅ Logged in as {role}: {u}")
                    st.rerun()


if not st.session_state.authenticated:
    login_form()
    st.stop()

# ----------------- TOP BAR -----------------
left, right = st.columns([1, 4])
with left:
    if st.button("🚪 Logout"):
        st.session_state.clear()
        st.experimental_rerun()
with right:
    st.info(
        f"Logged in as **{st.session_state.role}** – `{st.session_state.username}`"
    )


# ----------------- LOAD RAW DATA (PERSIST ACROSS RESTARTS) -----------------
def load_raw_files():
    """Load Outstanding_latest.xlsx and Barred_latest.xlsx if present."""
    os_df = None
    og_df = None

    if os.path.exists("Outstanding_latest.xlsx"):
        try:
            os_df = pd.read_excel("Outstanding_latest.xlsx")
            st.session_state.os_filename = "Outstanding_latest.xlsx"
            if not st.session_state.os_uploaded_at:
                st.session_state.os_uploaded_at = "Loaded from last saved file"
        except Exception as e:
            st.warning(f"Could not read Outstanding_latest.xlsx: {e}")

    if os.path.exists("Barred_latest.xlsx"):
        try:
            og_df = pd.read_excel("Barred_latest.xlsx")
            st.session_state.og_filename = "Barred_latest.xlsx"
            if not st.session_state.og_uploaded_at:
                st.session_state.og_uploaded_at = "Loaded from last saved file"
        except Exception as e:
            st.warning(f"Could not read Barred_latest.xlsx: {e}")

    return os_df, og_df


def bbm_upload_ui(os_df_current, og_df_current):
    """For BBM only: upload UI and update latest files."""
    st.subheader("📥 Upload Monthly Files (BBM Only)")

    os_file = st.file_uploader(
        "Upload Outstanding List (Total OS + PRIVATE OS sheets)",
        type=["xls", "xlsx"],
        key="os_file",
    )
    og_file = st.file_uploader(
        "Upload Barred Customer List (2nd sheet = OG/IC Barred List)",
        type=["xls", "xlsx"],
        key="og_file",
    )

    # OS upload
    if os_file is not None:
        try:
            xls = pd.ExcelFile(os_file)
            names = xls.sheet_names
            sheet_total = "Total OS" if "Total OS" in names else names[-2]
            sheet_priv = "PRIVATE OS" if "PRIVATE OS" in names else names[-1]

            df_total = pd.read_excel(xls, sheet_name=sheet_total)
            df_priv = pd.read_excel(xls, sheet_name=sheet_priv)
            os_df_new = pd.concat([df_total, df_priv], ignore_index=True)

            os_df_new.to_excel("Outstanding_latest.xlsx", index=False)
            st.session_state.os_filename = os_file.name
            st.session_state.os_uploaded_at = datetime.now().strftime(
                "%Y-%m-%d %H:%M"
            )
            st.session_state.os_uploaded_by = st.session_state.username

            log_upload(st.session_state.username, "OS", os_file.name)

            try:
                github_upload_file(
                    "Outstanding_latest.xlsx",
                    f"latest/Outstanding_latest.xlsx",
                    "Update latest Outstanding list",
                )
            except Exception as e:
                st.warning(f"Could not sync OS file to GitHub: {e}")

            st.success(
                f"✅ Outstanding List loaded (sheets: '{sheet_total}', '{sheet_priv}')"
            )
            os_df_current = os_df_new
        except Exception as e:
            st.error(f"Error reading Outstanding List file: {e}")

    # OG upload
    if og_file is not None:
        try:
            xls = pd.ExcelFile(og_file)
            if len(xls.sheet_names) < 2:
                st.error("Barred Customer List must have at least 2 sheets.")
            else:
                sheet_og = xls.sheet_names[1]
                og_df_new = pd.read_excel(xls, sheet_name=sheet_og)

                og_df_new.to_excel("Barred_latest.xlsx", index=False)
                st.session_state.og_filename = og_file.name
                st.session_state.og_uploaded_at = datetime.now().strftime(
                    "%Y-%m-%d %H:%M"
                )
                st.session_state.og_uploaded_by = st.session_state.username

                log_upload(st.session_state.username, "OG", og_file.name)

                try:
                    github_upload_file(
                        "Barred_latest.xlsx",
                        f"latest/Barred_latest.xlsx",
                        "Update latest Barred list",
                    )
                except Exception as e:
                    st.warning(f"Could not sync OG file to GitHub: {e}")

                st.success(f"✅ Barred Customer List loaded (sheet: '{sheet_og}')")
                og_df_current = og_df_new
        except Exception as e:
            st.error(f"Error reading Barred List file: {e}")

    return os_df_current, og_df_current


# Load base files (persisted)
base_os_df, base_og_df = load_raw_files()

# For BBM, show upload UI and update base data
if st.session_state.role == "BBM":
    base_os_df, base_og_df = bbm_upload_ui(base_os_df, base_og_df)

# If still no data and role is TIP/BBM, stop
if base_os_df is None and base_og_df is None and st.session_state.role in ("TIP", "BBM"):
    st.warning("No OS/OG data loaded yet. BBM must upload at least once.")
    st.stop()


# ----------------- PREPROCESS (CLEAN ONLY, NO FILTER BY ROLE) -----------------
def preprocess(os_df_raw, og_df_raw):
    if os_df_raw is None:
        df_os = pd.DataFrame(
            columns=[
                COL_OS_TIP_NAME,
                COL_OS_BBM,
                COL_OS_BA,
                COL_OS_MOBILE,
                COL_OS_CUST_NAME,
                COL_OS_ADDR,
                COL_OS_AMOUNT,
            ]
        )
    else:
        df_os = os_df_raw.copy()

    if og_df_raw is None:
        df_og = pd.DataFrame(
            columns=[
                COL_OG_TIP_NAME,
                COL_OG_BBM,
                COL_OG_BA,
                COL_OG_MOBILE,
                COL_OG_CUST_NAME,
                COL_OG_ADDR,
                COL_OG_AMOUNT,
            ]
        )
    else:
        df_og = og_df_raw.copy()

    # Check required columns
    if not df_os.empty:
        req_os = [
            COL_OS_TIP_NAME,
            COL_OS_BBM,
            COL_OS_BA,
            COL_OS_MOBILE,
            COL_OS_CUST_NAME,
            COL_OS_ADDR,
            COL_OS_AMOUNT,
        ]
        missing = [c for c in req_os if c not in df_os.columns]
        if missing:
            st.error(f"OS file missing columns: {missing}")
            st.stop()

    if not df_og.empty:
        req_og = [
            COL_OG_TIP_NAME,
            COL_OG_BBM,
            COL_OG_BA,
            COL_OG_MOBILE,
            COL_OG_CUST_NAME,
            COL_OG_ADDR,
            COL_OG_AMOUNT,
        ]
        missing = [c for c in req_og if c not in df_og.columns]
        if missing:
            st.error(f"Barred List file missing columns: {missing}")
            st.stop()

    # Standardize columns
    def clean_mobile(x):
        if pd.isna(x):
            return ""
        x = str(x).strip()
        if x.endswith(".0"):
            x = x[:-2]
        x = "".join(ch for ch in x if ch.isdigit())
        return x

    if not df_os.empty:
        df_os["TIP_NAME_STD"] = (
            df_os[COL_OS_TIP_NAME].astype(str).str.strip().str.upper()
        )
        df_os["BBM_STD"] = df_os[COL_OS_BBM].astype(str).str.strip().str.upper()
        df_os[COL_OS_AMOUNT] = pd.to_numeric(
            df_os[COL_OS_AMOUNT], errors="coerce"
        ).fillna(0)
        df_os[COL_OS_MOBILE] = df_os[COL_OS_MOBILE].apply(clean_mobile)
    else:
        df_os["TIP_NAME_STD"] = []
        df_os["BBM_STD"] = []

    if not df_og.empty:
        df_og["TIP_NAME_STD"] = (
            df_og[COL_OG_TIP_NAME].astype(str).str.strip().str.upper()
        )
        df_og["BBM_STD"] = df_og[COL_OG_BBM].astype(str).str.strip().str.upper()
        df_og[COL_OG_AMOUNT] = pd.to_numeric(
            df_og[COL_OG_AMOUNT], errors="coerce"
        ).fillna(0)
        df_og[COL_OG_MOBILE] = df_og[COL_OG_MOBILE].apply(clean_mobile)
    else:
        df_og["TIP_NAME_STD"] = []
        df_og["BBM_STD"] = []

    return df_os, df_og


os_df_all, og_df_all = preprocess(base_os_df, base_og_df)


# ----------------- TIP VIEW -----------------
def tip_view():
    tip_name = st.session_state.username  # already upper
    st.subheader(f"📌 TIP Dashboard – {tip_name}")

    tip_os = os_df_all[os_df_all["TIP_NAME_STD"] == tip_name].copy()
    tip_og = og_df_all[og_df_all["TIP_NAME_STD"] == tip_name].copy()

    # Determine BBM(s) for this TIP (from data)
    bbms = sorted(
        set(tip_os["BBM_STD"].dropna().unique().tolist()
            + tip_og["BBM_STD"].dropna().unique().tolist())
    )
    if len(bbms) == 0:
        bbm_for_tip = ""
    elif len(bbms) == 1:
        bbm_for_tip = bbms[0]
    else:
        bbm_for_tip = st.selectbox("Select your BBM", bbms)

    st.caption(f"BBM for this TIP (from data): **{bbm_for_tip or 'Not found'}**")

    if tip_os.empty and tip_og.empty:
        st.error(
            "No OS / OG records found for this TIP name. "
            "Check that login name matches the 'Maintanance Franchisee Name' in Excel."
        )
        return

    st.caption(
        f"📄 Outstanding List: **{st.session_state.os_filename}** "
        f"(Last updated: {st.session_state.os_uploaded_at or 'N/A'} by {st.session_state.os_uploaded_by or 'N/A'})"
    )
    st.caption(
        f"📄 Barred Customer List: **{st.session_state.og_filename}** "
        f"(Last updated: {st.session_state.og_uploaded_at or 'N/A'} by {st.session_state.og_uploaded_by or 'N/A'})"
    )
    st.caption(f"🗓 Contact log month: **{CURRENT_MONTH}**")

    total_os = tip_os[COL_OS_AMOUNT].sum()
    total_og = tip_og[COL_OG_AMOUNT].sum()
    total_os_cust = len(tip_os)
    total_og_cust = len(tip_og)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("💰 Total OS (Disconnected)", f"{total_os:,.2f}")
    with c2:
        st.metric("🚫 Total OG/IC Barred (Working)", f"{total_og:,.2f}")
    with c3:
        st.metric("👥 OS Customers", total_os_cust)
    with c4:
        st.metric("👥 Barred Customers", total_og_cust)

    # TIP CONTACT SUMMARY
    st.markdown("### 📈 My Contact Summary (This Month)")
    sheets = load_status_all()
    df_tip_log = pd.DataFrame()
    if CURRENT_MONTH in sheets:
        df_month = sheets[CURRENT_MONTH]
        if not df_month.empty:
            if bbm_for_tip:
                df_tip_log = df_month[
                    (df_month["TIP_NAME_STD"] == tip_name)
                    & (df_month["BBM_STD"] == bbm_for_tip)
                ].copy()
            else:
                df_tip_log = df_month[
                    (df_month["TIP_NAME_STD"] == tip_name)
                ].copy()

    if df_tip_log.empty:
        st.info("No Call / WhatsApp actions recorded for you this month.")
    else:
        df_tmp = df_tip_log.copy()
        df_tmp["has_call"] = df_tmp["LAST_CALL_TIME"].fillna("").ne("")
        df_tmp["has_wa"] = df_tmp["LAST_WHATSAPP_TIME"].fillna("").ne("")
        total_accounts = df_tmp["ACCOUNT_NO"].nunique()
        total_calls = df_tmp["has_call"].sum()
        total_wapps = df_tmp["has_wa"].sum()

        csa, csb, csc = st.columns(3)
        with csa:
            st.metric("Accounts contacted", total_accounts)
        with csb:
            st.metric("Calls logged", int(total_calls))
        with csc:
            st.metric("WhatsApps logged", int(total_wapps))

        st.dataframe(df_tip_log, use_container_width=True)
        st.download_button(
            "⬇️ Download my contact log (Excel)",
            data=df_to_excel_bytes(df_tip_log, sheet_name=CURRENT_MONTH),
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

    # SECTION 1: OS CUSTOMERS
    if show_os:
        st.markdown("---")
        st.subheader("📴 Disconnected Customers – OS")
        st.caption("Click Call / WA buttons AFTER you actually call or message.")

        status_map_os = (
            get_status_map(tip_name, bbm_for_tip, "OS") if bbm_for_tip else {}
        )

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
                msg = (
                    f"Dear {cust_name}, your BSNL FTTH outstanding is "
                    f"Rs {amount:.2f}. Kindly pay immediately."
                )
                st.markdown(
                    make_whatsapp_link(mobile, msg), unsafe_allow_html=True
                )
            with c3:
                if st.button("Call Done", key=f"os_call_{idx}") and bbm_for_tip:
                    update_status(
                        tip_name,
                        bbm_for_tip,
                        "OS",
                        acc_no,
                        update_call=True,
                    )
                    st.experimental_rerun()
            with c4:
                if st.button("WA Sent", key=f"os_wa_{idx}") and bbm_for_tip:
                    update_status(
                        tip_name,
                        bbm_for_tip,
                        "OS",
                        acc_no,
                        update_whatsapp=True,
                    )
                    st.experimental_rerun()
            with c5:
                if last_call:
                    st.write(f"📞 Last Call: {last_call}")
                if last_wa:
                    st.write(f"💬 Last WA: {last_wa}")

    # SECTION 2: OG CUSTOMERS
    if show_og:
        st.markdown("---")
        st.subheader("📡 Working Customers – OG/IC Barred")
        st.caption("Click Call / WA buttons AFTER you actually call or message.")

        status_map_og = (
            get_status_map(tip_name, bbm_for_tip, "OG") if bbm_for_tip else {}
        )

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
                msg = (
                    f"Dear {cust_name}, your BSNL FTTH bill is overdue. "
                    f"Outstanding Rs {amount:.2f}. Kindly pay immediately."
                )
                st.markdown(
                    make_whatsapp_link(mobile, msg), unsafe_allow_html=True
                )
            with c3:
                if st.button("Call Done", key=f"og_call_{idx}") and bbm_for_tip:
                    update_status(
                        tip_name,
                        bbm_for_tip,
                        "OG",
                        acc_no,
                        update_call=True,
                    )
                    st.experimental_rerun()
            with c4:
                if st.button("WA Sent", key=f"og_wa_{idx}") and bbm_for_tip:
                    update_status(
                        tip_name,
                        bbm_for_tip,
                        "OG",
                        acc_no,
                        update_whatsapp=True,
                    )
                    st.experimental_rerun()
            with c5:
                if last_call:
                    st.write(f"📞 Last Call: {last_call}")
                if last_wa:
                    st.write(f"💬 Last WA: {last_wa}")


# ----------------- BBM VIEW -----------------
def bbm_view():
    bbm_name = st.session_state.username
    st.subheader(f"📌 BBM Dashboard – {bbm_name}")

    bbm_os = os_df_all[os_df_all["BBM_STD"] == bbm_name].copy()
    bbm_og = og_df_all[og_df_all["BBM_STD"] == bbm_name].copy()

    st.caption(
        f"📄 Outstanding List: **{st.session_state.os_filename}** "
        f"(Last updated: {st.session_state.os_uploaded_at or 'N/A'} by {st.session_state.os_uploaded_by or 'N/A'})"
    )
    st.caption(
        f"📄 Barred Customer List: **{st.session_state.og_filename}** "
        f"(Last updated: {st.session_state.og_uploaded_at or 'N/A'} by {st.session_state.og_uploaded_by or 'N/A'})"
    )

    total_os = bbm_os[COL_OS_AMOUNT].sum()
    total_og = bbm_og[COL_OG_AMOUNT].sum()
    total_os_cust = len(bbm_os)
    total_og_cust = len(bbm_og)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("💰 Total OS (Disconnected) – This BBM", f"{total_os:,.2f}")
    with c2:
        st.metric("🚫 Total OG/IC Barred (Working) – This BBM", f"{total_og:,.2f}")
    with c3:
        st.metric("👥 OS Customers", total_os_cust)
    with c4:
        st.metric("👥 Barred Customers", total_og_cust)

    st.markdown("---")
    st.markdown("### 📋 TIP-wise Summary (This BBM Only)")

    if not bbm_os.empty:
        os_tip_group = bbm_os.groupby("TIP_NAME_STD").agg(
            Total_OS=(COL_OS_AMOUNT, "sum"),
            OS_Customers=(COL_OS_CUST_NAME, "count"),
        )
    else:
        os_tip_group = pd.DataFrame(columns=["Total_OS", "OS_Customers"])

    if not bbm_og.empty:
        og_tip_group = bbm_og.groupby("TIP_NAME_STD").agg(
            Total_OGIC=(COL_OG_AMOUNT, "sum"),
            OG_Customers=(COL_OG_CUST_NAME, "count"),
        )
    else:
        og_tip_group = pd.DataFrame(columns=["Total_OGIC", "OG_Customers"])

    tip_summary = os_tip_group.join(og_tip_group, how="outer").fillna(0).reset_index()
    if not tip_summary.empty:
        tip_summary = tip_summary.rename(
            columns={
                "TIP_NAME_STD": "TIP Name",
                "Total_OS": "Total OS (Disconnected) ₹",
                "Total_OGIC": "Total OG/IC Barred (Working) ₹",
            }
        )
    st.dataframe(tip_summary, use_container_width=True)

    # TIP contact status (this BBM)
    st.markdown("---")
    st.markdown("### 📞 Call / 💬 WhatsApp Status – This BBM")

    sheets = load_status_all()
    if not sheets:
        st.info("No Call / WhatsApp actions recorded yet by TIPs.")
    else:
        months = sorted(sheets.keys())
        selected_month = st.selectbox(
            "Select month:", months,
            index=months.index(CURRENT_MONTH) if CURRENT_MONTH in months else len(months) - 1,
        )
        df_month = sheets[selected_month]
        if df_month.empty:
            st.info("No contacts recorded in this month.")
        else:
            df_bbm = df_month[df_month["BBM_STD"] == bbm_name].copy()
            if df_bbm.empty:
                st.info("No contacts recorded for this BBM in the selected month.")
            else:
                df_bbm["has_call"] = df_bbm["LAST_CALL_TIME"].fillna("").ne("")
                df_bbm["has_wa"] = df_bbm["LAST_WHATSAPP_TIME"].fillna("").ne("")

                summary = (
                    df_bbm.groupby("TIP_NAME_STD")
                    .agg(
                        Accounts_Contacted=("ACCOUNT_NO", "nunique"),
                        Calls_Done=("has_call", "sum"),
                        WhatsApp_Sent=("has_wa", "sum"),
                    )
                    .reset_index()
                    .rename(columns={"TIP_NAME_STD": "TIP Name"})
                )
                st.markdown("#### TIP Contact Summary (This Month, This BBM)")
                st.dataframe(summary, use_container_width=True)

                st.markdown("#### Detailed TIP Contact Log")
                st.dataframe(df_bbm, use_container_width=True)

                st.download_button(
                    "⬇️ Download TIP contact log (Excel)",
                    data=df_to_excel_bytes(df_bbm, sheet_name=selected_month),
                    file_name=f"{bbm_name}_TIP_contact_log_{selected_month}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )


# ----------------- MGMT VIEW -----------------
def mgmt_view():
    st.subheader("🏛 Management Dashboard (All BBMs & TIPs)")

    # BBM upload summary
    st.markdown("### 📂 BBM File Upload Summary")
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

    st.markdown("---")
    st.markdown("### 📞 Global TIP Contact Summary")

    sheets = load_status_all()
    if not sheets:
        st.info("No Call / WhatsApp actions recorded yet.")
        return

    months = sorted(sheets.keys())
    selected_month = st.selectbox(
        "Select month:", months,
        index=months.index(CURRENT_MONTH) if CURRENT_MONTH in months else len(months) - 1,
    )
    df_month = sheets[selected_month]
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

    st.markdown("#### BBM-wise Summary")
    bbm_summary = (
        df_month.groupby("BBM_STD")
        .agg(
            TIPs=("TIP_NAME_STD", "nunique"),
            Accounts_Contacted=("ACCOUNT_NO", "nunique"),
            Calls_Done=("has_call", "sum"),
            WhatsApp_Sent=("has_wa", "sum"),
        )
        .reset_index()
        .rename(columns={"BBM_STD": "BBM"})
    )
    st.dataframe(bbm_summary, use_container_width=True)

    st.markdown("#### TIP-wise Summary (All BBMs)")
    tip_summary = (
        df_month.groupby(["BBM_STD", "TIP_NAME_STD"])
        .agg(
            Accounts_Contacted=("ACCOUNT_NO", "nunique"),
            Calls_Done=("has_call", "sum"),
            WhatsApp_Sent=("has_wa", "sum"),
        )
        .reset_index()
        .rename(columns={"BBM_STD": "BBM", "TIP_NAME_STD": "TIP Name"})
    )
    st.dataframe(tip_summary, use_container_width=True)

    st.markdown("#### Full TIP Contact Log")
    st.dataframe(df_month, use_container_width=True)


# ----------------- ROLE SWITCH -----------------
if st.session_state.role == "TIP":
    tip_view()
elif st.session_state.role == "BBM":
    bbm_view()
else:
    mgmt_view()
