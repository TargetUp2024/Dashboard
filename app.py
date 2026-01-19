import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px
from datetime import datetime

# --- PAGE CONFIG ---
st.set_page_config(page_title="AO & Mail System", page_icon="📈", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .big-metric-container { padding-top: 0px; margin-bottom: -20px; }
    .big-metric-value { font-size: 85px !important; font-weight: 800 !important; color: #1f77b4; line-height: 1; margin: 0; }
    .big-metric-label { font-size: 20px !important; color: #666; text-transform: uppercase; margin-bottom: 5px; }
    .today-header { font-size: 22px; font-weight: 700; color: #2c3e50; margin-top: 20px; margin-bottom: 2px; }
    .today-date { font-size: 16px; color: #7f8c8d; margin-bottom: 15px; }
    [data-testid="stMetricValue"] { font-weight: 700; }
    </style>
    """, unsafe_allow_html=True)

# --- DATA FETCHING ---
@st.cache_data(ttl=600)
def get_ao_data():
    # Your existing AO Data fetching logic
    credentials_dict = st.secrets["gcp_service_account"]
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(credentials_dict, scopes=scope)
    client = gspread.authorize(creds)
    SHEET_URL = st.secrets["private_gsheet_url"]
    sheet = client.open_by_url(SHEET_URL).sheet1 # Assumes sheet1 is AO
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    df['Date'] = pd.to_datetime(df['Date']).dt.date
    df['Nombre'] = pd.to_numeric(df['Nombre'], errors='coerce').fillna(1)
    return df

@st.cache_data(ttl=600)
def get_mail_data():
    # If your Mails are in a different Tab (e.g., "Sheet2"), change it here
    credentials_dict = st.secrets["gcp_service_account"]
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(credentials_dict, scopes=scope)
    client = gspread.authorize(creds)
    SHEET_URL = st.secrets["private_gsheet_url"]
    
    # Open the second sheet (Tab 2) for Mails
    # Change .get_worksheet(1) to the correct index or name
    try:
        sheet = client.open_by_url(SHEET_URL).get_worksheet(1) 
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        if not df.empty:
            df['Date'] = pd.to_datetime(df['Date']).dt.date
        return df
    except:
        # Returns empty dataframe if sheet doesn't exist yet
        return pd.DataFrame(columns=['Date', 'Subject', 'Status', 'Recipient'])

# --- SIDEBAR NAVIGATION ---
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/3090/3090116.png", width=80)
st.sidebar.title("Main Menu")

# ADDED "📧 Mail Tracking" TO THE LIST BELOW
page = st.sidebar.selectbox("Go to:", ["🏠 Home", "📊 AO Dashboard", "📧 Mail Tracking"])

# --- PAGE 1: HOME ---
if page == "🏠 Home":
    st.title("Welcome to the Management System")
    st.markdown("""
    ### Select a module from the sidebar:
    *   **AO Dashboard**: Track your Appels d'Offres and conversions.
    *   **Mail Tracking**: Monitor outgoing emails and responses.
    """)

# --- PAGE 2: AO DASHBOARD ---
elif page == "📊 AO Dashboard":
    df = get_ao_data()
    # ... (Keep all your existing AO Tracking code here) ...
    st.title("Appel d'Offres (AO) Tracking")
    
    # Filters
    st.sidebar.header("🗓️ AO Filters")
    min_d, max_d = df['Date'].min(), df['Date'].max()
    date_range = st.sidebar.date_input("Date Range", value=(min_d, max_d))
    
    # (Existing AO Logic continues...)
    st.metric("Total AO", len(df))
    st.write("Current AO data shown here.")

# --- PAGE 3: MAIL TRACKING (NEW PAGE) ---
elif page == "📧 Mail Tracking":
    st.title("📧 Mail Tracking System")
    
    try:
        df_mail = get_mail_data()
        
        if df_mail.empty:
            st.warning("No mail data found. Please check your Google Sheet (Tab 2).")
        else:
            # --- MAIL METRICS ---
            m1, m2, m3 = st.columns(3)
            with m1:
                st.metric("Total Mails Sent", len(df_mail))
            with m2:
                opened = len(df_mail[df_mail['Status'] == 'Opened']) if 'Status' in df_mail.columns else 0
                st.metric("Mails Opened", opened)
            with m3:
                replied = len(df_mail[df_mail['Status'] == 'Replied']) if 'Status' in df_mail.columns else 0
                st.metric("Responses", replied)

            st.divider()

            # --- MAIL CHARTS ---
            c1, c2 = st.columns(2)
            
            with c1:
                st.subheader("Mails by Status")
                if 'Status' in df_mail.columns:
                    fig_mail_pie = px.pie(df_mail, names='Status', hole=0.4)
                    st.plotly_chart(fig_mail_pie, use_container_width=True)
            
            with c2:
                st.subheader("Daily Mail Volume")
                df_mail_time = df_mail.groupby('Date').size().reset_index(name='Count')
                fig_mail_line = px.line(df_mail_time, x='Date', y='Count')
                st.plotly_chart(fig_mail_line, use_container_width=True)

            # --- DATA TABLE ---
            with st.expander("View Detailed Mail Log"):
                st.dataframe(df_mail, use_container_width=True)
                
    except Exception as e:
        st.error(f"Error loading Mail Data: {e}")
