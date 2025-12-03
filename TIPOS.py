import streamlit as st
import pandas as pd
import os
import io
from datetime import datetime
from urllib.parse import quote
import base64
import json
import requests

# -------------------------------------------------
# PAGE CONFIG
# -------------------------------------------------
st.set_page_config(
    page_title="TIP Outstanding & OG/IC Barred Dashboard",
    layout="wide",
)

STATUS_FILE = "tip_contact_status.xlsx"
UPLOAD_LOG_FILE = "bbm_upload_log.xlsx"
CURRENT_MONTH = datetime.now().strftime("%Y-%m")

# -------------------------------------------------
# LOAD LOGIN JSONs
# -------------------------------------------------
MGMT_PASSWORD = ""
BBM_USERS = {}
TIP_USERS = {}

try:
    if os.path.exists("mgmt.json"):
        with open("mgmt.json", "r", encoding="utf-8") as f:
            MGMT_PASSWORD = str(json.load(f).get("password", "")).strip()

    if os.path.exists("bbm_users.json"):
        with open("bbm_users.json", "r", encoding="utf-8") as f:
            BBM_USERS = json.load(f)

    if os.path.exists("tip_users.json"):
        with open("tip_users.json", "r", encoding="utf-8") as f:
            TIP_USERS = json.load(f)

except Exception as e:
    st.error(f"Error loading login JSONs: {e}")

# -------------------------------------------------
# SESSION INIT
# -------------------------------------------------
def init_session():
    defaults = {
        "authenticated": False,
        "role": None,
        "username": None,
        "current_bbm": "",
        "os_df": None,
        "og_df": None,
        "os_filename": "",
        "og_filename": "",
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

# -------------------------------------------------
# ICON LINKS
# -------------------------------------------------
def make_tel_link(m):
    if not m:
        return ""
    return f'<a href="tel:{m}">📞 {m}</a>'

def make_whatsapp_link(m, msg):
    if not m:
        return ""
    return f'<a href="https://wa.me/{m}?text={quote(msg)}" target="_blank">🟢 WhatsApp</a>'

# -------------------------------------------------
# STATUS ENGINE — PERMANENT STORAGE
# -------------------------------------------------
STATUS_COLS = [
    "TIP_NAME_STD", "BBM_STD", "SOURCE", "ACCOUNT_NO",
    "LAST_CALL_TIME", "LAST_WHATSAPP_TIME", "MONTH"
]

def load_status_all():
    if st.session_state.status_sheets is not None:
        return st.session_state.status_sheets
    
    sheets = {}
    if os.path.exists(STATUS_FILE):
        x = pd.ExcelFile(STATUS_FILE)
        for s in x.sheet_names:
            df = pd.read_excel(x, sheet_name=s, dtype=str)
            for c in STATUS_COLS:
                if c not in df.columns:
                    df[c] = ""
            sheets[s] = df[STATUS_COLS].copy()
    st.session_state.status_sheets = sheets
    return sheets

def save_status_all(sheets):
    with pd.ExcelWriter(STATUS_FILE, engine="openpyxl") as w:
        for name, df in sheets.items():
            df.to_excel(w, sheet_name=name, index=False)
    st.session_state.status_sheets = sheets

def update_status(tip, src, acc, update_call=False, update_wa=False):
    sheets = load_status_all()
    month = CURRENT_MONTH
    tip = tip.upper().strip()
    bbm = st.session_state.current_bbm.upper().strip()
    acc = str(acc)

    df = sheets.get(month, pd.DataFrame(columns=STATUS_COLS))
    for c in STATUS_COLS:
        if c not in df.columns:
            df[c] = ""

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    mask = (
        (df["TIP_NAME_STD"] == tip) &
        (df["BBM_STD"] == bbm) &
        (df["SOURCE"] == src.upper()) &
        (df["ACCOUNT_NO"] == acc)
    )

    if mask.any():
        i = df.index[mask][0]
        if update_call:
            df.at[i, "LAST_CALL_TIME"] = now
        if update_wa:
            df.at[i, "LAST_WHATSAPP_TIME"] = now
        df.at[i, "MONTH"] = month
    else:
        df = pd.concat([df, pd.DataFrame([{
            "TIP_NAME_STD": tip,
            "BBM_STD": bbm,
            "SOURCE": src.upper(),
            "ACCOUNT_NO": acc,
            "LAST_CALL_TIME": now if update_call else "",
            "LAST_WHATSAPP_TIME": now if update_wa else "",
            "MONTH": month,
        }])])

    sheets[month] = df
    save_status_all(sheets)

def status_map(tip, src):
    sheets = load_status_all()
    df = sheets.get(CURRENT_MONTH, pd.DataFrame())
    if df.empty:
        return {}
    tip = tip.upper().strip()
    bbm = st.session_state.current_bbm.upper().strip()
    df = df[
        (df["TIP_NAME_STD"] == tip) &
        (df["BBM_STD"] == bbm) &
        (df["SOURCE"] == src.upper())
    ]
    m = {}
    for _, r in df.iterrows():
        m[str(r["ACCOUNT_NO"])] = (
            r["LAST_CALL_TIME"], r["LAST_WHATSAPP_TIME"]
        )
    return m

# -------------------------------------------------
# LOGIN FORM WITH JSON BASED AUTH + BBM DROPDOWN
# -------------------------------------------------
def login_form():
    st.subheader("🔐 Login")

    with st.form("login_form"):
        st.radio("Login as", ["TIP", "BBM", "MGMT"], key="login_role", horizontal=True)
        role = st.session_state["login_role"]

        bbm_for_tip = None

        if role == "TIP":
            username = st.selectbox("Select TIP Name", sorted(TIP_USERS.keys()))
            bbm_for_tip = st.selectbox("Select your BBM", sorted(BBM_USERS.keys()))
            pwd = st.text_input("Enter TIP Login Code", type="password")

        elif role == "BBM":
            username = st.selectbox("Select BBM Name", sorted(BBM_USERS.keys()))
            pwd = st.text_input("Enter BBM Login Code", type="password")

        else:
            username = st.text_input("MGMT User ID")
            pwd = st.text_input("Enter MGMT Password", type="password")

        submitted = st.form_submit_button("Login")

        if submitted:
            u = username.strip()

            if role == "MGMT":
                if pwd != MGMT_PASSWORD:
                    st.error("❌ Wrong MGMT password")
                    return

            elif role == "BBM":
                expected = BBM_USERS.get(u)
                if pwd != expected:
                    st.error("❌ Invalid BBM code")
                    return

            elif role == "TIP":
                expected = TIP_USERS.get(u)
                if pwd != expected:
                    st.error("❌ Invalid TIP code")
                    return

            # SUCCESS → clear + set session
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            init_session()

            st.session_state.authenticated = True
            st.session_state.role = role
            st.session_state.username = u.upper()

            if role == "TIP":
                st.session_state.current_bbm = bbm_for_tip.upper()
            elif role == "BBM":
                st.session_state.current_bbm = u.upper()

            st.success("Login successful!")
            st.rerun()

if not st.session_state.authenticated:
    login_form()
    st.stop()
# -------------------------------------------------
# NORMALIZATION
# -------------------------------------------------
def normalize(s):
    if not s:
        return ""
    return str(s).strip().upper().replace("  ", " ").replace("\n", " ")


# -------------------------------------------------
# READ UPLOADED EXCEL
# -------------------------------------------------
def read_uploaded_excel(uploaded_file):
    try:
        df = pd.read_excel(uploaded_file, dtype=str)
        df.columns = [normalize(c) for c in df.columns]
        return df
    except Exception as e:
        st.error(f"❌ Failed to read Excel: {e}")
        return pd.DataFrame()


# -------------------------------------------------
# FIND CRITICAL COLUMNS IN OS FILE
# -------------------------------------------------
def infer_os_columns(df):
    cname = {}
    for c in df.columns:
        u = c.upper()

        if "ACCOUNT" in u:
            cname["ACCOUNT_NO"] = c
        if "FTTH" in u and "TIP" in u:
            cname["TIP_NAME"] = c
        if "MOBILE" in u:
            cname["MOBILE"] = c
        if "BBM" in u or "INCH" in u:
            cname["BBM_NAME"] = c
        if "CUSTOMER" in u or "NAME" in u:
            cname["CUST_NAME"] = c

    return cname


# -------------------------------------------------
# FIND CRITICAL COLUMNS IN OG FILE
# -------------------------------------------------
def infer_og_columns(df):
    cname = {}
    for c in df.columns:
        u = c.upper()

        if "ACCOUNT" in u or "SERVICE" in u:
            cname["ACCOUNT_NO"] = c
        if "TIP" in u:
            cname["TIP_NAME"] = c
        if "MOBILE" in u:
            cname["MOBILE"] = c
        if "BBM" in u or "INCH" in u:
            cname["BBM_NAME"] = c
        if "CUSTOMER" in u or "NAME" in u:
            cname["CUST_NAME"] = c

    return cname


# -------------------------------------------------
# CLEAN / STANDARDIZE OS
# -------------------------------------------------
def preprocess_os_df(df):
    c = infer_os_columns(df)
    missing = [x for x in ["ACCOUNT_NO", "TIP_NAME", "MOBILE", "BBM_NAME"] if x not in c]
    if missing:
        st.warning(f"Some OS columns missing → {missing}")

    df2 = pd.DataFrame()
    df2["ACCOUNT_NO"] = df[c.get("ACCOUNT_NO")] if c.get("ACCOUNT_NO") else ""
    df2["TIP_NAME"] = df[c.get("TIP_NAME")] if c.get("TIP_NAME") else ""
    df2["TIP_NAME_STD"] = df2["TIP_NAME"].apply(normalize)
    df2["BBM_NAME"] = df[c.get("BBM_NAME")] if c.get("BBM_NAME") else ""
    df2["BBM_STD"] = df2["BBM_NAME"].apply(normalize)
    df2["MOBILE"] = df[c.get("MOBILE")] if c.get("MOBILE") else ""
    df2["CUST_NAME"] = df[c.get("CUST_NAME")] if c.get("CUST_NAME") else ""
    df2["SOURCE"] = "OS"
    return df2


# -------------------------------------------------
# CLEAN / STANDARDIZE OG
# -------------------------------------------------
def preprocess_og_df(df):
    c = infer_og_columns(df)
    missing = [x for x in ["ACCOUNT_NO", "TIP_NAME", "MOBILE", "BBM_NAME"] if x not in c]
    if missing:
        st.warning(f"Some OG columns missing → {missing}")

    df2 = pd.DataFrame()
    df2["ACCOUNT_NO"] = df[c.get("ACCOUNT_NO")] if c.get("ACCOUNT_NO") else ""
    df2["TIP_NAME"] = df[c.get("TIP_NAME")] if c.get("TIP_NAME") else ""
    df2["TIP_NAME_STD"] = df2["TIP_NAME"].apply(normalize)
    df2["BBM_NAME"] = df[c.get.get("BBM_NAME")] if c.get("BBM_NAME") else ""
    df2["BBM_STD"] = df2["BBM_NAME"].apply(normalize)
    df2["MOBILE"] = df[c.get("MOBILE")] if c.get("MOBILE") else ""
    df2["CUST_NAME"] = df[c.get("CUST_NAME")] if c.get("CUST_NAME") else ""
    df2["SOURCE"] = "OG"
    return df2


# -------------------------------------------------
# SAVE UPLOADED FILE LOG
# -------------------------------------------------
def load_upload_log():
    if os.path.exists(UPLOAD_LOG_FILE):
        return pd.read_excel(UPLOAD_LOG_FILE)
    return pd.DataFrame(columns=[
        "TYPE", "FILENAME", "UPLOADED_BY", "UPLOADED_AT"
    ])


def append_upload_log(type_, filename, user):
    df = load_upload_log()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    df.loc[len(df)] = [type_, filename, user, now]
    df.to_excel(UPLOAD_LOG_FILE, index=False)


# -------------------------------------------------
# BBM UPLOAD SCREEN
# -------------------------------------------------
def bbm_upload_screen():
    role = st.session_state.role
    user = st.session_state.username

    st.subheader(f"📤 Upload OS / OG Files (Logged in as {user})")

    os_file = st.file_uploader("Upload OS File", type=["xlsx"], key="os_up")
    og_file = st.file_uploader("Upload OG/IC Barred File", type=["xlsx"], key="og_up")

    # ------------------ OS ------------------
    if os_file is not None:
        df = read_uploaded_excel(os_file)
        if not df.empty:
            df2 = preprocess_os_df(df)
            st.session_state.os_df = df2
            st.session_state.os_filename = os_file.name
            st.session_state.os_uploaded_at = datetime.now().strftime("%Y-%m-%d %H:%M")
            st.session_state.os_uploaded_by = user

            append_upload_log("OS", os_file.name, user)
            st.success("OS file processed & saved!")

    # ------------------ OG ------------------
    if og_file is not None:
        df = read_uploaded_excel(og_file)
        if not df.empty:
            df2 = preprocess_og_df(df)
            st.session_state.og_df = df2
            st.session_state.og_filename = og_file.name
            st.session_state.og_uploaded_at = datetime.now().strftime("%Y-%m-%d %H:%M")
            st.session_state.og_uploaded_by = user

            append_upload_log("OG", og_file.name, user)
            st.success("OG file processed & saved!")

    st.info("After upload → TIP users will see updated lists in real-time.")
# -------------------------------------------------
# TIP DASHBOARD (OUTSTANDING + OG/IC BARRED)
# -------------------------------------------------
def tip_dashboard():
    st.title("📞 TIP Outstanding & OG/IC Barred Dashboard")

    tip_name = st.session_state.username
    bbm = st.session_state.current_bbm

    st.info(f"Logged in as: **{tip_name}** | BBM: **{bbm}**")

    # Get OS & OG
    os_df = st.session_state.os_df
    og_df = st.session_state.og_df

    # If BBM filter selected
    if os_df is not None:
        os_df = os_df[os_df["TIP_NAME_STD"] == tip_name]
        os_df = os_df[os_df["BBM_STD"] == bbm]

    if og_df is not None:
        og_df = og_df[og_df["TIP_NAME_STD"] == tip_name]
        og_df = og_df[og_df["BBM_STD"] == bbm]

    tab1, tab2 = st.tabs(["📌 Outstanding List", "📌 OG / IC Barred List"])

    # -------------------------------------------------
    # OUTSTANDING TAB
    # -------------------------------------------------
    with tab1:
        if os_df is None or os_df.empty:
            st.warning("No OS data uploaded by BBM.")
        else:
            st.subheader("Outstanding Customers")

            status_dict = status_map(tip_name, "OS")

            for idx, row in os_df.iterrows():
                acc = row["ACCOUNT_NO"]
                mobile = row["MOBILE"]
                cust = row["CUST_NAME"]

                # previous contact info
                call_time, wa_time = status_dict.get(acc, ("", ""))

                # status color
                green = (call_time != "" or wa_time != "")

                with st.container():
                    if green:
                        st.markdown(
                            f"<div style='background:#d4ffd4;padding:10px;border-radius:6px;'>"
                            f"🔹 <b>{cust}</b> — {acc}<br>"
                            f"{make_tel_link(mobile)} | {make_whatsapp_link(mobile, 'Dear Customer, your FTTH bill is pending.')}"
                            f"<br><small>Last Call: {call_time} | WhatsApp: {wa_time}</small>"
                            "</div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            f"<div style='background:#fff7d4;padding:10px;border-radius:6px;'>"
                            f"🔹 <b>{cust}</b> — {acc}<br>"
                            f"{make_tel_link(mobile)} | {make_whatsapp_link(mobile, 'Kindly pay your BSNL FTTH bill.')}"
                            "</div>",
                            unsafe_allow_html=True,
                        )

                c1, c2 = st.columns(2)
                with c1:
                    if st.button(f"📞 Mark Call Done {acc}", key=f"oscall_{acc}"):
                        update_status(tip_name, "OS", acc, update_call=True)
                        st.rerun()

                with c2:
                    if st.button(f"🟢 Mark WhatsApp Sent {acc}", key=f"oswa_{acc}"):
                        update_status(tip_name, "OS", acc, update_wa=True)
                        st.rerun()

                st.write("---")

    # -------------------------------------------------
    # OG TAB
    # -------------------------------------------------
    with tab2:
        if og_df is None or og_df.empty:
            st.warning("No OG/IC data uploaded by BBM.")
        else:
            st.subheader("OG/IC Barred Customers")

            status_dict = status_map(tip_name, "OG")

            for idx, row in og_df.iterrows():
                acc = row["ACCOUNT_NO"]
                mobile = row["MOBILE"]
                cust = row["CUST_NAME"]

                call_time, wa_time = status_dict.get(acc, ("", ""))

                green = (call_time != "" or wa_time != "")

                with st.container():
                    if green:
                        st.markdown(
                            f"<div style='background:#d4ffd4;padding:10px;border-radius:6px;'>"
                            f"🔹 <b>{cust}</b> — {acc}<br>"
                            f"{make_tel_link(mobile)} | {make_whatsapp_link(mobile, 'Your FTTH is OG/IC barred. Kindly clear dues.')}"
                            f"<br><small>Last Call: {call_time} | WhatsApp: {wa_time}</small>"
                            "</div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            f"<div style='background:#fff7d4;padding:10px;border-radius:6px;'>"
                            f"🔹 <b>{cust}</b> — {acc}<br>"
                            f"{make_tel_link(mobile)} | {make_whatsapp_link(mobile, 'Please clear dues to resume service.')}"
                            "</div>",
                            unsafe_allow_html=True,
                        )

                c1, c2 = st.columns(2)
                with c1:
                    if st.button(f"📞 Mark Call Done {acc}", key=f"ogcall_{acc}"):
                        update_status(tip_name, "OG", acc, update_call=True)
                        st.rerun()
                with c2:
                    if st.button(f"🟢 Mark WhatsApp Sent {acc}", key=f"ogwa_{acc}"):
                        update_status(tip_name, "OG", acc, update_wa=True)
                        st.rerun()

                st.write("---")


# -------------------------------------------------
# BBM DASHBOARD (VIEW UPLOAD LOGS)
# -------------------------------------------------
def bbm_dashboard():
    st.title("📊 BBM Dashboard")

    log = load_upload_log()
    if log.empty:
        st.info("No files uploaded yet.")
        return

    st.subheader("Uploaded Files Log")
    st.dataframe(log, use_container_width=True)


# -------------------------------------------------
# MGMT DASHBOARD
# -------------------------------------------------
def mgmt_dashboard():
    st.title("🛡️ Management Dashboard")

    os_df = st.session_state.os_df
    og_df = st.session_state.og_df
    log = load_upload_log()

    st.subheader("📘 Latest OS Summary")
    if os_df is None:
        st.warning("No OS uploaded")
    else:
        st.dataframe(os_df.head(50))

    st.subheader("📙 Latest OG Summary")
    if og_df is None:
        st.warning("No OG uploaded")
    else:
        st.dataframe(og_df.head(50))

    st.subheader("📁 Upload Logs")
    st.dataframe(log)


# -------------------------------------------------
# MAIN ROUTER
# -------------------------------------------------
def main_app():
    role = st.session_state.role

    if role == "TIP":
        tip_dashboard()

    elif role == "BBM":
        bbm_upload_screen()
        st.write("---")
        bbm_dashboard()

    elif role == "MGMT":
        mgmt_dashboard()


# -------------------------------------------------
# RUN APP
# -------------------------------------------------
if st.session_state.authenticated:
    main_app()
