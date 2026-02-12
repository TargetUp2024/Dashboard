import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange, Dimension, Metric, RunReportRequest
)
import plotly.express as px
from datetime import datetime, timedelta
import requests

from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.adsinsights import AdsInsights

import xmlrpc.client #ODOO

# --- PAGE CONFIG ---
st.set_page_config(page_title="Executive Intelligence System", page_icon="📈", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .big-metric-container { padding-top: 0px; margin-bottom: -20px; }
    .big-metric-value { font-size: 85px !important; font-weight: 800 !important; color: #1f77b4; line-height: 1; margin: 0; }
    .big-metric-label { font-size: 20px !important; color: #666; text-transform: uppercase; margin-bottom: 5px; }
    .today-header { font-size: 24px; font-weight: 700; color: #2c3e50; margin-top: 20px; border-left: 5px solid #1f77b4; padding-left: 10px; }
    .today-date { font-size: 16px; color: #7f8c8d; margin-bottom: 15px; }
    [data-testid="stMetricValue"] { font-weight: 700; font-size: 32px !important; }
    .stPlotlyChart { margin-bottom: 40px; }
    </style>
    """, unsafe_allow_html=True)




@st.cache_data(ttl=3600)
def get_odoo_crm_data():
    url = st.secrets["ODOO_URL"]
    db = st.secrets["ODOO_DB"]
    username = st.secrets["ODOO_USER"]
    api_key = st.secrets["ODOO_API_KEY"]

    try:
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
        uid = common.authenticate(db, username, api_key, {})
        if not uid:
            st.error("Odoo authentication failed")
            return pd.DataFrame(), pd.DataFrame()

        models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

        # -----------------------------
        # CRM LEADS / OPPORTUNITIES
        # -----------------------------
        leads = models.execute_kw(
            db, uid, api_key,
            'crm.lead', 'search_read',
            [[]],
            {
                'fields': [
                    'id',
                    'name',
                    'source_id',
                    'stage_id',
                    'expected_revenue',
                    'probability',
                    'create_date',
                    'date_deadline',
                    'lost_reason_id',
                    'active'
                ],
                'limit': 5000
            }
        )

        # -----------------------------
        # INVOICES (REAL REVENUE)
        # -----------------------------
        invoices = models.execute_kw(
            db, uid, api_key,
            'account.move', 'search_read',
            [[('state','=','posted'), ('move_type','=','out_invoice')]],
            {
                'fields': [
                    'amount_total',
                    'invoice_date',
                    'payment_state',
                    'invoice_origin'
                ],
                'limit': 5000
            }
        )

        return pd.DataFrame(leads), pd.DataFrame(invoices)

    except Exception as e:
        st.error(f"Odoo error: {e}")
        return pd.DataFrame(), pd.DataFrame()



# Initialize FB API
def init_fb_api():
    FacebookAdsApi.init(
        access_token=st.secrets["FB_ACCESS_TOKEN"]
    )

@st.cache_data(ttl=3600)
def get_fb_ads_data(start_date, end_date):
    init_fb_api()
    # Change this line in your get_fb_ads_data function:
    account_id = st.secrets["FB_AD_ACCOUNT_ID"]
    if not account_id.startswith('act_'):
        account_id = f"act_{account_id}"
    
    account = AdAccount(account_id)
        
    fields = [
        AdsInsights.Field.ad_name,
        AdsInsights.Field.impressions,
        AdsInsights.Field.clicks,
        AdsInsights.Field.spend,
        AdsInsights.Field.cpc,
        AdsInsights.Field.ctr,
    ]
    
    params = {
        'level': 'ad',
        'time_range': {
            'since': start_date.strftime('%Y-%m-%d'),
            'until': end_date.strftime('%Y-%m-%d'),
        },
    }
    
    insights = account.get_insights(fields=fields, params=params)
    df = pd.DataFrame(insights)
    
    # Ensure numeric types
    for col in ['spend', 'impressions', 'clicks', 'cpc', 'ctr']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    return df

# --- CLIENT INITIALIZATION ---
def get_ga_client():
    credentials_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(credentials_dict)
    return BetaAnalyticsDataClient(credentials=creds)

# --- DATA FETCHING FUNCTIONS ---

@st.cache_data(ttl=600)
def get_data():
    """Original AO Data Fetching"""
    credentials_dict = st.secrets["gcp_service_account"]
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(credentials_dict, scopes=scope)
    client = gspread.authorize(creds)
    SHEET_URL = st.secrets["private_gsheet_url"]
    sheet = client.open_by_url(SHEET_URL).sheet1
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    df = df.dropna(subset=['Date', 'Source'])
    df['Date'] = pd.to_datetime(df['Date']).dt.date
    df['Nombre'] = pd.to_numeric(df['Nombre'], errors='coerce').fillna(1)
    return df

@st.cache_data(ttl=600)
def get_mail_data():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )
    client = gspread.authorize(creds)
    SHEET = client.open_by_url(st.secrets["mail_gsheet_url"])

    all_data = []

    for ws in SHEET.worksheets():
        df = pd.DataFrame(ws.get_all_records())

        if df.empty or 'Date' not in df.columns:
            continue

        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')

        # DROP INVALID DATES (CRITICAL)
        df = df.dropna(subset=['Date'])

        if df.empty:
            continue

        df['Date'] = df['Date'].dt.date
        df['SheetName'] = ws.title
        all_data.append(df)

    if not all_data:
        return pd.DataFrame(columns=['Date'])

    return pd.concat(all_data, ignore_index=True)


def get_mailgun_stats(duration="30d"):
    try:
        url = f"https://api.mailgun.net/v3/{st.secrets['MAILGUN_DOMAIN']}/stats/total"
        params = {"event": ["accepted", "opened"], "duration": duration}
        res = requests.get(url, auth=("api", st.secrets["MAILGUN_API_KEY"]), params=params)
        if res.status_code == 200:
            data = res.json()
            acc = data.get('stats', [{}])[0].get('accepted', {}).get('total', 0)
            ope = data.get('stats', [{}])[0].get('opened', {}).get('total', 0)
            rate = (ope / acc * 100) if acc > 0 else 0
            return rate, ope
    except: pass
    return 0, 0

def run_ga_report(property_id, dimensions, metrics, start_date, end_date="today"):
    client = get_ga_client()
    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name=d) for d in dimensions],
        metrics=[Metric(name=m) for m in metrics],
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
    )
    response = client.run_report(request)
    output = []
    for row in response.rows:
        res = {dimensions[i]: val.value for i, val in enumerate(row.dimension_values)}
        res.update({metrics[i]: val.value for i, val in enumerate(row.metric_values)})
        output.append(res)
    return pd.DataFrame(output)

# --- SIDEBAR NAVIGATION ---
st.sidebar.image(
    "https://targetupconsulting.com/web/image/website/4/logo/targetupconsulting?unique=c9518b0",
    width=140
)

st.sidebar.title("Main Menu")
page = st.sidebar.selectbox("Go to:", ["🏠 Home", "📊 AO Dashboard", "📧 Mail Tracking", "🌐 Google Analytics", "📱 Meta Ads","💰 Financial Impact"])

# --- PAGE 1: HOME ---
if page == "🏠 Home":
    st.title("AO & Marketing Intelligence System")
    st.markdown("### Bienvenue ! Utilisez la barre latérale pour naviguer.")

# --- PAGE 2: AO DASHBOARD ---
elif page == "📊 AO Dashboard":
    try:
        df = get_data()
    except Exception as e:
        st.error(f"❌ Connection Error: {e}"); st.stop()

    st.sidebar.divider()
    st.sidebar.header("🗓️ AO Filters")
    min_d, max_d = df['Date'].min(), df['Date'].max()
    date_range = st.sidebar.date_input("Date Range", value=(min_d, max_d), min_value=min_d, max_value=max_d)
    sources = st.sidebar.multiselect("Sources", options=df["Source"].unique(), default=df["Source"].unique())
    status_list = st.sidebar.multiselect("Status", options=df["Status"].unique(), default=df["Status"].unique())

    if len(date_range) == 2:
        start_date, end_date = date_range
        df_filtered = df[(df["Date"] >= start_date) & (df["Date"] <= end_date) & 
                         (df["Source"].isin(sources)) & (df["Status"].isin(status_list))]
    else:
        df_filtered = df

    st.title("Appel d'Offres (AO) Tracking")
    st.markdown(f'<div class="big-metric-container"><p class="big-metric-label">Total AO Filtered</p><p class="big-metric-value">{int(df_filtered["Nombre"].sum())}</p></div>', unsafe_allow_html=True)
    st.write("---")

    today_dt = datetime.now().date()
    df_today = df[df['Date'] == today_dt]
    st.markdown(f'<div class="today-header">Aujourd\'hui</div><div class="today-date">{today_dt.strftime("%A %d %B %Y")}</div>', unsafe_allow_html=True)

    t1, t2, t3, t4 = st.columns(4)
    t1.metric("Scrapé Aujourd'hui", int(df_today["Nombre"].sum()))
    t2.metric("Accepté Aujourd'hui", len(df_today[df_today["Status"] == "Accepté"]))
    t3.metric("Refus Aujourd'hui", len(df_today[df_today["Status"] == "Refus"]))
    t4.metric("Opp Aujourd'hui", len(df_today[df_today["Status"] == "Opportunité"]))

    st.write("##"); st.subheader("Conversion KPIs")
    c1, c2, c3 = st.columns(3)
    tot = len(df_filtered)
    if tot > 0:
        rate_refus = (len(df_filtered[df_filtered["Status"] == "Refus"]) / tot) * 100
        rate_accep = (len(df_filtered[df_filtered["Status"] == "Accepté"]) / tot) * 100
        count_accep = len(df_filtered[df_filtered["Status"] == "Accepté"])
        rate_opp = (len(df_filtered[df_filtered["Status"] == "Opportunité"]) / count_accep * 100) if count_accep > 0 else 0
    else: rate_refus = rate_accep = rate_opp = 0
    c1.metric("Taux Scraped ➔ Refus", f"{rate_refus:.1f}%")
    c2.metric("Taux Scraped ➔ Accepté", f"{rate_accep:.1f}%")
    c3.metric("Taux Accepté ➔ Opportunité", f"{rate_opp:.1f}%")

    st.divider()

    # --- BAR CHART: Source Distribution ---
    fig_bar = px.bar(
        df_filtered.groupby("Source")["Nombre"]
        .count()
        .reset_index(),
        x="Nombre",
        y="Source",
        orientation="h",
        color="Source",
        template="plotly_white",
        title="Répartition par source"
    )
    st.plotly_chart(fig_bar, use_container_width=True)
    
    st.divider()
    
    # --- PIE CHART: Status Distribution ---
    fig_pie = px.pie(
        df_filtered,
        names="Status",
        hole=0.5,
        color_discrete_map={
            "Refus": "#FF4B4B",
            "Opportunité": "#00CC96",
            "Accepté": "#636EFA"
        },
        title="Analyse par statut"
    )
    st.plotly_chart(fig_pie, use_container_width=True)


    st.subheader("Activité Timeline")
    df_timeline = df_filtered.groupby('Date').size().reset_index(name='counts')
    st.plotly_chart(px.area(df_timeline, x='Date', y='counts', template="plotly_white"), use_container_width=True)

# --- PAGE 3: MAIL TRACKING ---
elif page == "📧 Mail Tracking":
    st.title("📧 Mail Tracking Dashboard")
    
    try:
        df_m = get_mail_data()
        if df_m.empty or df_m['Date'].isna().all():
            st.warning("No valid mailing data available for date filtering.")
            st.stop()
    except Exception as e:
        st.error(f"Error loading data: {e}"); st.stop()

    # --- SIDEBAR DATE FILTER (Mini Calendar) ---
    st.sidebar.divider()
    st.sidebar.header("🗓️ Mail Date Filter")
    m_min, m_max = df_m['Date'].min(), df_m['Date'].max()
    mail_date_range = st.sidebar.date_input("Select Range", value=(m_min, m_max), min_value=m_min, max_value=m_max)

    # Filter data based on sidebar calendar
    if isinstance(mail_date_range, tuple) and len(mail_date_range) == 2:
        start_m, end_m = mail_date_range
        df_m_filtered = df_m[(df_m['Date'] >= start_m) & (df_m['Date'] <= end_m)]
        # Fetch Mailgun stats relative to days selected (approx)
        days_diff = (end_m - start_m).days
        duration_str = f"{days_diff if days_diff > 0 else 1}d"
        open_rate, opens = get_mailgun_stats(duration_str)
    else:
        df_m_filtered = df_m
        open_rate, opens = get_mailgun_stats("30d")

    # Fetch Today's fixed stats from Mailgun
    today_rate, today_opens = get_mailgun_stats("24h")

    # --- SECTION: AUJOURD'HUI (FIXED) ---
    today_dt = datetime.now().date()
    df_m_today = df_m[df_m['Date'] == today_dt]
    
    st.markdown(f'<div class="today-header">Aujourd\'hui (Mailing)</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="today-date">{today_dt.strftime("%A %d %B %Y")}</div>', unsafe_allow_html=True)

    mt1, mt2, mt3, mt4 = st.columns(4)
    mt1.metric("Prospectés Aujourd'hui", len(df_m_today))
    mt2.metric("Envoyés Aujourd'hui", len(df_m_today[df_m_today['Email Envoyé '].str.contains('Oui', na=False)]))
    mt3.metric("Open Rate (Mailgun 24h)", f"{today_rate:.1f}%")
    mt4.metric("Réponses Aujourd'hui", len(df_m_today[df_m_today['Email Reponse '].astype(str).str.strip() != ""]))

    st.divider()

    # --- SECTION: FILTERED PERFORMANCE (BASED ON CALENDAR) ---
    st.subheader("Performance sur la période sélectionnée")
    g1, g2, g3, g4 = st.columns(4)
    g1.metric("Contacts dans la période", len(df_m_filtered))
    g2.metric("Emails Envoyés", len(df_m_filtered[df_m_filtered['Email Envoyé '].str.contains('Oui', na=False)]))
    g3.metric("Open Rate (Mailgun)", f"{open_rate:.1f}%")
    g4.metric("Réponses Reçues", len(df_m_filtered[df_m_filtered['Email Reponse '].astype(str).str.strip() != ""]))

    st.divider()

    # Graph Timeline
    st.subheader("Volume des envois sur la période")
    mail_timeline = df_m_filtered.groupby('Date').size().reset_index(name='Volume')
    st.plotly_chart(px.line(mail_timeline, x='Date', y='Volume', markers=True, template="plotly_white"), use_container_width=True)

    with st.expander("🔍 View Raw Mailing Database"):
        st.dataframe(df_m_filtered, use_container_width=True, hide_index=True)

elif page == "📱 Meta Ads":
    st.title("📱 Meta Ads Performance")
    
    # Sidebar Filters
    st.sidebar.divider()
    st.sidebar.header("🗓️ Ads Date Filter")
    today = datetime.now().date()
    fb_range = st.sidebar.date_input("Select Range", value=(today - timedelta(days=7), today))
    
    if isinstance(fb_range, tuple) and len(fb_range) == 2:
        df_fb = get_fb_ads_data(fb_range[0], fb_range[1])
        
        if not df_fb.empty:
            # --- TOP METRICS ---
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Spend", f"${df_fb['spend'].sum():,.2f}")
            m2.metric("Impressions", f"{int(df_fb['impressions'].sum()):,}")
            m3.metric("Clicks", f"{int(df_fb['clicks'].sum()):,}")
            m4.metric("Avg CPC", f"${df_fb['spend'].sum()/df_fb['clicks'].sum():,.2f}" if df_fb['clicks'].sum() > 0 else "$0")
            
            st.divider()
            
            # --- CHARTS ---
            col_a, col_b = st.columns(2)
            
            with col_a:
                st.subheader("Spend by Ad")
                fig_spend = px.bar(df_fb.sort_values("spend"), x="spend", y="ad_name", orientation='h', template="plotly_white")
                st.plotly_chart(fig_spend, use_container_width=True)
                
            with col_b:
                st.subheader("Clicks vs Impressions")
                fig_scatter = px.scatter(df_fb, x="impressions", y="clicks", size="spend", hover_name="ad_name", template="plotly_white")
                st.plotly_chart(fig_scatter, use_container_width=True)
                
            # --- RAW DATA ---
            with st.expander("🔍 View Detailed Ad Breakdown"):
                st.dataframe(df_fb, use_container_width=True, hide_index=True)
        else:
            st.info("No active ads found for this period.")

elif page == "💰 Financial Impact":
    st.title("💰 Finance & ROI Executive Overview")
    
    df_leads, df_revenue = get_odoo_crm_data()

    if df_leads.empty:
        st.warning("No CRM data available")
        st.stop()

    # -----------------------
    # CLEAN ODOO DATA
    # -----------------------
    df_leads['source'] = df_leads['source_id'].apply(lambda x: x[1] if isinstance(x, list) else "Unknown")
    df_leads['stage'] = df_leads['stage_id'].apply(lambda x: x[1] if isinstance(x, list) else "Unknown")
    df_leads['expected_revenue'] = pd.to_numeric(df_leads['expected_revenue'], errors='coerce').fillna(0)

    df_revenue['amount_total'] = pd.to_numeric(df_revenue['amount_total'], errors='coerce').fillna(0)

    # -----------------------
    # TOP CEO METRICS
    # -----------------------
    total_pipeline = df_leads['expected_revenue'].sum()
    total_revenue = df_revenue['amount_total'].sum()

    c1, c2 = st.columns(2)
    c1.metric("Total Pipeline", f"€{total_pipeline:,.0f}")
    c2.metric("Total Revenue", f"€{total_revenue:,.0f}")

    st.divider()

    # -----------------------
    # FUNNEL BY SOURCE
    # -----------------------
    st.subheader("📊 Funnel by Acquisition Channel")

    funnel = (
        df_leads
        .groupby(['source','stage'])
        .agg(
            leads=('id','count'),
            pipeline=('expected_revenue','sum')
        )
        .reset_index()
    )

    pivot_leads = funnel.pivot_table(index='source', columns='stage', values='leads', fill_value=0)
    pivot_pipeline = funnel.pivot_table(index='source', columns='stage', values='pipeline', fill_value=0)

    st.write("### Leads by Stage")
    st.dataframe(pivot_leads, use_container_width=True)

    st.write("### Pipeline € by Stage")
    st.dataframe(pivot_pipeline, use_container_width=True)

    # -----------------------
    # LINK INVOICES → LEADS → SOURCE
    # -----------------------
    df_join = df_revenue.merge(
        df_leads[['name','source']],
        left_on='invoice_origin',
        right_on='name',
        how='left'
    )

    revenue_by_source = df_join.groupby('source')['amount_total'].sum().reset_index()

    st.subheader("💶 Real Revenue by Source")
    st.dataframe(revenue_by_source, use_container_width=True)

    # -----------------------
    # META ROI
    # -----------------------
    st.subheader("📈 Meta Ads ROI")

    meta_spend = df_fb['spend'].sum() if 'df_fb' in locals() else 0
    meta_pipeline = pivot_pipeline.loc['Meta Ads'].sum() if 'Meta Ads' in pivot_pipeline.index else 0
    meta_revenue = revenue_by_source[revenue_by_source['source']=="Meta Ads"]['amount_total'].sum()

    m1, m2, m3 = st.columns(3)
    m1.metric("Meta Spend", f"${meta_spend:,.0f}")
    m2.metric("Meta Pipeline", f"€{meta_pipeline:,.0f}")
    m3.metric("Meta Revenue", f"€{meta_revenue:,.0f}")

    roi = ((meta_revenue - meta_spend) / meta_spend * 100) if meta_spend > 0 else 0
    st.metric("Meta ROI", f"{roi:.1f}%")



# --- PAGE 4: GOOGLE ANALYTICS (WITH FILTERS) ---
elif page == "🌐 Google Analytics":
    st.title("🌐 Website Traffic Intelligence")
    
    site = st.sidebar.radio("Select Website:", ["Targetup University", "Targetup Consulting"])
    pid = st.secrets["GA_PROPERTY_ID_1"] if site == "Targetup University" else st.secrets["GA_PROPERTY_ID_2"]
    
    st.sidebar.divider()
    st.sidebar.header("🗓️ Global Filters")
    today = datetime.now().date()
    ga_range = st.sidebar.date_input("Calendar Range", value=(today - timedelta(days=30), today))

    try:
        if isinstance(ga_range, tuple) and len(ga_range) == 2:
            s_str, e_str = ga_range[0].strftime("%Y-%m-%d"), ga_range[1].strftime("%Y-%m-%d")
            
            # Fetch Master Data for Filtering
            with st.spinner('Fetching Analytics Data...'):
                df_master = run_ga_report(
                    pid, 
                    ["date", "sessionDefaultChannelGroup", "country", "pagePath"], 
                    [
                        "activeUsers",
                        "newUsers",
                        "sessions",
                        "screenPageViews",
                        "userEngagementDuration",  # Fixed metric name (was engagementTime)
                        "engagementRate"
                    ],
                    s_str, e_str
                )

            if df_master.empty:
                st.warning("No data found for this period.")
            else:
                # Convert metrics to numeric
                cols_to_fix = [
                    "activeUsers",
                    "newUsers",
                    "sessions",
                    "screenPageViews",
                    "userEngagementDuration",
                    "engagementRate"
                ]                
                for col in cols_to_fix:
                    df_master[col] = pd.to_numeric(df_master[col], errors='coerce').fillna(0)
                
                # --- SESSION DURATION (GA4 SAFE) ---
                df_master["avgSessionDurationSec"] = (
                    df_master["userEngagementDuration"] / df_master["sessions"]
                ).replace([float("inf")], 0).fillna(0)

                # --- SIDEBAR FILTERS ---
                st.sidebar.subheader("🔍 Refine Results")
               
                st.sidebar.subheader("⏱ Session Duration")
                session_duration_filter = st.sidebar.radio(
                    "Session duration filter",
                    ["All sessions", "Sessions > 1 second"],
                    index=0
                )
                 
                selected_countries = st.sidebar.multiselect("Filter by Country", options=sorted(df_master["country"].unique()))
                selected_sources = st.sidebar.multiselect("Filter by Source Type", options=sorted(df_master["sessionDefaultChannelGroup"].unique()))
                selected_pages = st.sidebar.multiselect("Filter by Page Path", options=sorted(df_master["pagePath"].unique()))

                # Apply Filters to Dataframe
                df_filtered = df_master.copy()
                if selected_countries:
                    df_filtered = df_filtered[df_filtered["country"].isin(selected_countries)]
                if selected_sources:
                    df_filtered = df_filtered[df_filtered["sessionDefaultChannelGroup"].isin(selected_sources)]
                if selected_pages:
                    df_filtered = df_filtered[df_filtered["pagePath"].isin(selected_pages)]
                if session_duration_filter == "Sessions > 1 second":
                    df_filtered = df_filtered[df_filtered["avgSessionDurationSec"] > 1]


                # --- A. SNAPSHOTS ---
                st.markdown('<div class="today-header">Performance Metrics</div>', unsafe_allow_html=True)
                
                t_u = df_filtered["activeUsers"].sum()
                t_s = df_filtered["sessions"].sum()
                t_pv = df_filtered["screenPageViews"].sum()
                # Return rate calculation
                ret_rate = ((t_u - df_filtered["newUsers"].sum()) / t_u * 100) if t_u > 0 else 0

                p1, p2, p3, p4 = st.columns(4)

                p1.metric("Users", f"{int(t_u):,}")
                p2.metric("Sessions", f"{int(t_s):,}")
                p3.metric("Page Views", f"{int(t_pv):,}")
                p4.metric("Returning Rate", f"{ret_rate:.1f}%")

                avg_engagement_rate = df_filtered["engagementRate"].mean() * 100
                st.metric("Engagement Rate", f"{avg_engagement_rate:.1f}%")

                st.divider()

                # --- B. GRAPHS ---
                
                # 1. TIMELINE
                st.write("### 📈 Users Timeline")
                df_filtered["date_dt"] = pd.to_datetime(df_filtered["date"])
                df_timeline = df_filtered.groupby("date_dt")["activeUsers"].sum().reset_index()
                st.plotly_chart(px.area(df_timeline.sort_values("date_dt"), x="date_dt", y="activeUsers", template="plotly_white"), use_container_width=True)

                # 2. TOP COUNTRIES
                st.write("### 🌍 Top Countries")
                df_geo = df_filtered.groupby("country")["activeUsers"].sum().reset_index()
                fig_geo = px.bar(df_geo.sort_values("activeUsers", ascending=False).head(10), 
                                 x="country", y="activeUsers", color="activeUsers", template="plotly_white")
                st.plotly_chart(fig_geo, use_container_width=True)

                # 3. SOURCES
                st.write("### 🚥 Traffic Sources")
                df_src = df_filtered.groupby("sessionDefaultChannelGroup")["sessions"].sum().reset_index()
                st.plotly_chart(px.bar(df_src.sort_values("sessions"), x="sessions", y="sessionDefaultChannelGroup", orientation='h', template="plotly_white"), use_container_width=True)

                # 4. PAGES
                st.write("### 📄 Top Pages")
                df_pg = df_filtered.groupby("pagePath")["screenPageViews"].sum().reset_index()
                fig_pg = px.bar(df_pg.sort_values("screenPageViews").tail(15), 
                                x="screenPageViews", y="pagePath", orientation='h', template="plotly_white", color="screenPageViews")
                st.plotly_chart(fig_pg, use_container_width=True)

                # 5. DETAILED TABLE
                with st.expander("🔍 View Raw Filtered Data"):
                    st.dataframe(df_filtered.drop(columns=["date_dt"]), use_container_width=True)

    except Exception as e:
        st.error(f"GA4 Error: {e}")
