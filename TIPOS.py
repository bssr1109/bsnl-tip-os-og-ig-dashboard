# TIPOS_FINAL_v2.py — FULL SYSTEM WITH ALL FEATURES
# Features:
# ✔ BBM Upload (auto-merge Total OS + PRIVATE OS)
# ✔ Auto-refresh toggle (60 sec)
# ✔ Status badges (🟩 Contact Done / 🟧 Pending)
# ✔ WhatsApp Deep Link
# ✔ JSON-based login for TIP / BBM / MGMT
# ✔ TIP sees only assigned BBM
# ✔ BBM sees only his TIPs
# ✔ MGMT sees all
# ✔ Month-wise status logging
# -------------------------------------------------------------

import streamlit as st
import pandas as pd
import json, os
from datetime import datetime

# -------------------------------------------------------------
# LOAD PASSWORDS
# -------------------------------------------------------------
with open("tip_users.json") as f:
    TIP_PASSWORDS = json.load(f)

with open("bbm_users.json") as f:
    BBM_PASSWORDS = json.load(f)

with open("mgmt.json") as f:
    MGMT_PASSWORD = json.load(f)["password"]

# -------------------------------------------------------------
# SESSION INIT
# -------------------------------------------------------------
def init_session():
    defaults = {
        "authenticated": False,
        "role": None,
        "username": None,
        "current_bbm": None,
        "os_df": None,
        "og_df": None,
        "status": {},
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session()

st.set_page_config(page_title="TIP Dashboard", layout="wide")
st.title("📡 TIP Outstanding & OG/IC Dashboard — v2")

# -------------------------------------------------------------
# AUTO-REFRESH FEATURE
# -------------------------------------------------------------
if st.checkbox("🔁 Auto-refresh every 60 seconds"):
    st.experimental_rerun()

# -------------------------------------------------------------
# LOGIN
# -------------------------------------------------------------
def login_screen():
    with st.form("login_form"):
        role = st.radio("Login as", ["TIP", "BBM", "MGMT"], horizontal=True)
        user = st.text_input("Username (exact)")
        pwd = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")

        if submit:
            u = user.strip().upper()

            if role == "MGMT":
                if pwd == MGMT_PASSWORD:
                    st.session_state.update({"authenticated": True, "role": role, "username": u})
                    st.rerun()
                else:
                    st.error("Invalid MGMT password")

            elif role == "BBM":
                if u in BBM_PASSWORDS and pwd == BBM_PASSWORDS[u]:
                    st.session_state.update({"authenticated": True, "role": role, "username": u, "current_bbm": u})
                    st.rerun()
                else:
                    st.error("Invalid BBM credentials")

            elif role == "TIP":
                if u in TIP_PASSWORDS and pwd == TIP_PASSWORDS[u]:
                    st.session_state.update({"authenticated": True, "role": role, "username": u})
                    st.rerun()
                else:
                    st.error("Invalid TIP credentials")

if not st.session_state.authenticated:
    login_screen()
    st.stop()

# -------------------------------------------------------------
# BBM UPLOAD SECTION — AUTO MERGE OS
# -------------------------------------------------------------
def handle_bbm_upload():
    st.subheader("⬆ Upload Monthly OS / OG Files (BBM Only)")

    os_up = st.file_uploader("Upload OS Excel (with Total OS + PRIVATE OS)", type=["xlsx","xls"], key="up_os")
    og_up = st.file_uploader("Upload OG/IC Excel", type=["xlsx","xls"], key="up_og")

    if os_up:
        xls = pd.ExcelFile(os_up)
        sheets = xls.sheet_names

        # auto detect 2 sheets
        sheet1 = sheets[0]
        sheet2 = sheets[1] if len(sheets) > 1 else sheets[0]

        df1 = pd.read_excel(xls, sheet1)
        df2 = pd.read_excel(xls, sheet2)

        merged = pd.concat([df1, df2], ignore_index=True)
        merged.to_excel("Outstanding_latest.xlsx", index=False)
        st.session_state.os_df = merged
        st.success("OS file uploaded & merged successfully.")
        st.rerun()

    if og_up:
        xls = pd.ExcelFile(og_up)
        sheet = xls.sheet_names[1] if len(xls.sheet_names) > 1 else xls.sheet_names[0]
        ogdf = pd.read_excel(xls, sheet)
        ogdf.to_excel("Barred_latest.xlsx", index=False)
        st.session_state.og_df = ogdf
        st.success("OG/IC file uploaded successfully.")
        st.rerun()

if st.session_state.role == "BBM":
    handle_bbm_upload()

# -------------------------------------------------------------
# LOAD OS / OG
# -------------------------------------------------------------
def load_files():
    if os.path.exists("Outstanding_latest.xlsx"):
        st.session_state.os_df = pd.read_excel("Outstanding_latest.xlsx")
    if os.path.exists("Barred_latest.xlsx"):
        st.session_state.og_df = pd.read_excel("Barred_latest.xlsx")

load_files()
os_raw = st.session_state.os_df
og_raw = st.session_state.og_df

# -------------------------------------------------------------
# TIP → AUTO MAP TO BBM
# -------------------------------------------------------------
if st.session_state.role == "TIP" and os_raw is not None:
    tip = st.session_state.username
    try:
        bbm = os_raw.loc[
            os_raw["Maintanance Franchisee Name"].astype(str).str.upper() == tip,
            "BBM"
        ].iloc[0]
        st.session_state.current_bbm = str(bbm).upper()
    except:
        st.error("TIP not found in OS file.")
        st.stop()

# -------------------------------------------------------------
# NORMALIZE + FILTER
# -------------------------------------------------------------
def preprocess():
    """Normalize and filter OS / OG safely.
    Handles cases where OG file is not uploaded or missing columns.
    """
    # If nothing loaded at all
    if os_raw is None and og_raw is None:
        return pd.DataFrame(), pd.DataFrame()

    # Copies or empty frames
    osdf = os_raw.copy() if os_raw is not None else pd.DataFrame()
    ogdf = og_raw.copy() if og_raw is not None else pd.DataFrame()

    # Convert all columns to string where data exists
    for df in (osdf, ogdf):
        if not df.empty:
            for c in df.columns:
                df[c] = df[c].astype(str)

    # ---- OS standardisation ----
    if not osdf.empty:
        osdf["TIP_STD"] = osdf["Maintanance Franchisee Name"].str.upper().str.strip()
        osdf["BBM_STD"] = osdf["BBM"].str.upper().str.strip()

    # ---- OG standardisation (only if columns exist & not empty) ----
    if (
        not ogdf.empty
        and "Maintenance Fanchisee Name" in ogdf.columns
        and "BBM" in ogdf.columns
    ):
        ogdf["TIP_STD"] = ogdf["Maintenance Fanchisee Name"].str.upper().str.strip()
        ogdf["BBM_STD"] = ogdf["BBM"].str.upper().str.strip()

    role = st.session_state.role

    if role == "TIP":
        tip = st.session_state.username
        bbm = st.session_state.current_bbm

        if not osdf.empty and {"TIP_STD","BBM_STD"}.issubset(osdf.columns):
            osdf = osdf[(osdf["TIP_STD"] == tip) & (osdf["BBM_STD"] == bbm)]

        if not ogdf.empty and {"TIP_STD","BBM_STD"}.issubset(ogdf.columns):
            ogdf = ogdf[(ogdf["TIP_STD"] == tip) & (ogdf["BBM_STD"] == bbm)]
        else:
            ogdf = pd.DataFrame()

    elif role == "BBM":
        bbm = st.session_state.username

        if not osdf.empty and "BBM_STD" in osdf.columns:
            osdf = osdf[osdf["BBM_STD"] == bbm]

        if not ogdf.empty and "BBM_STD" in ogdf.columns:
            ogdf = ogdf[ogdf["BBM_STD"] == bbm]
        else:
            ogdf = pd.DataFrame()

    # MGMT: no extra filter, they see all

    return osdf, ogdf

os_df, og_df = preprocess()

# -------------------------------------------------------------
# STATUS SYSTEM
# -------------------------------------------------------------
STATUS_FILE = "tip_contact_status.xlsx"
MONTH = datetime.now().strftime("%Y-%m")

if os.path.exists(STATUS_FILE):
    status = pd.read_excel(STATUS_FILE, sheet_name=None, dtype=str)
else:
    status = {}

if MONTH not in status:
    status[MONTH] = pd.DataFrame(columns=["TIP", "BBM", "SOURCE", "ACCOUNT", "LAST_CALL", "LAST_WA"])

def save_status():
    with pd.ExcelWriter(STATUS_FILE, engine="openpyxl") as w:
        for s, df in status.items():
            df.to_excel(w, sheet_name=s, index=False)

def mark_status(tip, bbm, src, acc, call=False, wa=False):
    df = status[MONTH]
    idx = (df["TIP"] == tip) & (df["BBM"] == bbm) & (df["SOURCE"] == src) & (df["ACCOUNT"] == acc)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if df[idx].empty:
        new = {"TIP": tip, "BBM": bbm, "SOURCE": src, "ACCOUNT": acc,
               "LAST_CALL": now if call else "", "LAST_WA": now if wa else ""}
        status[MONTH] = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
    else:
        if call:
            df.loc[idx, "LAST_CALL"] = now
        if wa:
            df.loc[idx, "LAST_WA"] = now
        status[MONTH] = df
    save_status()

# -------------------------------------------------------------
# BADGE RENDER
# -------------------------------------------------------------
def badge(tip, bbm, src, acc):
    df = status[MONTH]
    row = df[(df["TIP"] == tip) & (df["BBM"] == bbm) & (df["SOURCE"] == src) & (df["ACCOUNT"] == acc)]
    if row.empty:
        return "🟧 Pending"
    if row.iloc[0]["LAST_CALL"] or row.iloc[0]["LAST_WA"]:
        return "🟩 Done"
    return "🟧 Pending"

# -------------------------------------------------------------
# DISPLAY OS
# -------------------------------------------------------------
if not os_df.empty:
    st.header("📘 Outstanding (OS)")
    for _, r in os_df.iterrows():
        tip = r.get("Maintanance Franchisee Name", "").upper()
        bbm = r.get("BBM", "").upper()
        acc = r.get("Billing_Account_Number", "")
        mob = r.get("Mobile_Number", "")
        amt = r.get("OS_Amount(Rs)", "0")
        nm = r.get("First_Name", r.get("Customer Name", ""))

        st.markdown(f"### {acc} — ₹{amt} {badge(tip, bbm, 'OS', acc)}")
        c1, c2, c3 = st.columns(3)

        if c1.button("Call Done", key=f"os_call_{acc}"):
            mark_status(tip, bbm, "OS", acc, call=True)
            st.rerun()

        if c2.button("WhatsApp Sent", key=f"os_wa_{acc}"):
            mark_status(tip, bbm, "OS", acc, wa=True)
            st.rerun()

        wa_link = f"https://wa.me/91{mob}?text=Dear {nm}, your OS is ₹{amt}. Please pay soon."
        c3.markdown(f"[📩 WhatsApp Customer]({wa_link})")

# -------------------------------------------------------------
# DISPLAY OG
# -------------------------------------------------------------
if not og_df.empty:
    st.header("📗 OG/IC Barred")
    for _, r in og_df.iterrows():
        tip = r.get("Maintenance Fanchisee Name", "").upper()
        bbm = r.get("BBM", "").upper()
        acc = r.get("Account Number", "")
        mob = r.get("Mobile Number", "")
        nm = r.get("Customer Name", "")
        amt = r.get("OutStanding", "0")

        st.markdown(f"### {acc} — ₹{amt} {badge(tip, bbm, 'OG', acc)}")
        c1, c2, c3 = st.columns(3)

        if c1.button("Call Done", key=f"og_call_{acc}"):
            mark_status(tip, bbm, "OG", acc, call=True)
            st.rerun()

        if c2.button("WhatsApp Sent", key=f"og_wa_{acc}"):
            mark_status(tip, bbm, "OG", acc, wa=True)
            st.rerun()

        wa_link = f"https://wa.me/91{mob}?text=Dear {nm}, your OG/IC barred amount is ₹{amt}."
        c3.markdown(f"[📩 WhatsApp Customer]({wa_link})")

# -------------------------------------------------------------
# LOGOUT
# -------------------------------------------------------------
if st.button("🚪 Logout"):
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()
