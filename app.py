import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px

# --- PAGE CONFIG ---
st.set_page_config(page_title="AO Tracking System", page_icon="📈", layout="wide")

# --- STYLE ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    div[data-testid="stMetricValue"] { font-size: 28px; color: #1f77b4; }
    div.stButton > button:first-child { background-color: #007bff; color: white; }
    </style>
    """, unsafe_allow_html=True)

# --- GOOGLE SHEETS CONNECTION ---
def get_data():
    # Load credentials from Streamlit Secrets
    credentials_dict = st.secrets["gcp_service_account"]
    
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(credentials_dict, scopes=scope)
    client = gspread.authorize(creds)
    
    # Open the sheet by URL (Paste your full URL here)
    SHEET_URL = st.secrets["private_gsheet_url"]
    sheet = client.open_by_url(SHEET_URL).sheet1
    
    # Convert to DataFrame
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    
    # DATA CLEANING
    df = df.dropna(subset=['Date', 'Source']) # Remove empty rows
    df['Date'] = pd.to_datetime(df['Date'])
    df['Nombre'] = pd.to_numeric(df['Nombre'], errors='coerce').fillna(1)
    return df

# Initialize Data
try:
    df = get_data()
except Exception as e:
    st.error(f"❌ Connection Error: {e}")
    st.info("Check if you shared the sheet with the Service Account email and set up Secrets.")
    st.stop()

# --- SIDEBAR ---
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/3090/3090116.png", width=100)
st.sidebar.header("Dashboard Filters")
sources = st.sidebar.multiselect("Source Name", options=df["Source"].unique(), default=df["Source"].unique())
status = st.sidebar.multiselect("Status", options=df["Status"].unique(), default=df["Status"].unique())

df_filtered = df[df["Source"].isin(sources) & df["Status"].isin(status)]

# --- MAIN UI ---
st.title("📊 Appel d'Offres (AO) Dashboard")
st.caption("Live monitoring of tender applications and status tracking.")

# KPIs
kpi1, kpi2, kpi3, kpi4 = st.columns(4)
with kpi1:
    st.metric("Total Applications", len(df_filtered))
with kpi2:
    st.metric("Total Volume", int(df_filtered["Nombre"].sum()))
with kpi3:
    st.metric("Sources Used", df_filtered["Source"].nunique())
with kpi4:
    refus_count = len(df_filtered[df_filtered["Status"] == "Refus"])
    st.metric("Refusals", refus_count, delta_color="inverse")

st.write("---")

# Visualizations
col_left, col_right = st.columns([6, 4])

with col_left:
    st.subheader("📁 Distribution by Source")
    fig_bar = px.bar(
        df_filtered.groupby("Source")["Nombre"].count().reset_index(),
        x="Nombre", y="Source", orientation='h',
        color="Source", template="plotly_white",
        labels={'Nombre': 'Count', 'Source': ''}
    )
    fig_bar.update_layout(showlegend=False, height=400)
    st.plotly_chart(fig_bar, use_container_width=True)

with col_right:
    st.subheader("🎯 Status Breakdown")
    fig_pie = px.pie(
        df_filtered, names="Status", 
        color_discrete_sequence=px.colors.qualitative.Safe,
        hole=0.5
    )
    fig_pie.update_layout(margin=dict(t=0, b=0, l=0, r=0))
    st.plotly_chart(fig_pie, use_container_width=True)

# Timeline Chart
st.subheader("📅 Activity Over Time")
df_timeline = df_filtered.groupby('Date').size().reset_index(name='counts')
fig_line = px.area(df_timeline, x='Date', y='counts', template="plotly_white")
fig_line.update_traces(line_color='#007bff')
st.plotly_chart(fig_line, use_container_width=True)

