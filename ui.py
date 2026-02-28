import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
import os
import json

DB_NAME = "devlog.db"

st.set_page_config(
    page_title="Devlog Tracker",
    page_icon="⏱️",
    layout="wide"
)

st.title("⏱️ Devlog Tracking Dashboard")
st.markdown("Monitor your ongoing and past coding sessions.")

# --- Data Loading ---
@st.cache_data(ttl=5) # Cache data for 5 seconds to prevent spamming DB on every interaction
def load_data():
    if not os.path.exists(DB_NAME):
        return pd.DataFrame()
        
    try:
        conn = sqlite3.connect(DB_NAME)
        # Attempt to read git_branch if it exists, fallback if DB hasn't been migrated yet
        try:
            query = "SELECT id, project, git_branch, start_time, end_time, duration FROM sessions ORDER BY id DESC"
            df = pd.read_sql_query(query, conn)
        except sqlite3.OperationalError:
            # Fallback for old schema
            query = "SELECT id, project, start_time, end_time, duration FROM sessions ORDER BY id DESC"
            df = pd.read_sql_query(query, conn)
            df['git_branch'] = None

        conn.close()
        
        if not df.empty:
             # Convert duration to int safely
            df['duration_sec'] = df['duration'].fillna(0).astype(int)
            # Create a formatted duration string HH:MM:SS
            df['duration_str'] = df['duration_sec'].apply(lambda x: str(timedelta(seconds=x)))
            
            # Format dates nicely
            df['start_time'] = pd.to_datetime(df['start_time']).dt.strftime('%Y-%m-%d %H:%M:%S')
            
            # Handle ongoing sessions (where end_time might be missing/null depending on how tracker works)
            df['end_time'] = pd.to_datetime(df['end_time'], errors='ignore')
            df['end_time'] = df['end_time'].apply(
                lambda x: x.strftime('%Y-%m-%d %H:%M:%S') if pd.notnull(x) and isinstance(x, pd.Timestamp) else str(x)
            )
            
        return df
    except Exception as e:
        st.error(f"Error loading database: {e}")
        return pd.DataFrame()

def get_active_session():
    """Reads the live session state dumped by tracker.py"""
    live_file = "/tmp/devlog_active.json"
    if os.path.exists(live_file):
        try:
            with open(live_file, "r") as f:
                data = json.load(f)
                start = datetime.fromisoformat(data['start_time'])
                duration = datetime.now() - start
                # Format duration cleanly
                duration_str = str(duration).split('.')[0]
                return data, duration_str
        except Exception:
            pass
    return None, None

df = load_data()

# --- Live Active Session Banner ---
active_data, active_duration = get_active_session()
if active_data:
    st.info(f"⚡ **Currently Tracking:** `{active_data['project']}` (Branch: *{active_data['git_branch'] or 'N/A'}*) | **Active for:** {active_duration}")
else:
    st.caption("No active session detected. Waiting for file changes...")

# --- Sidebar Filters ---
st.sidebar.header("Filters")
if not df.empty:
    df['date_only'] = pd.to_datetime(df['start_time']).dt.date
    min_date = df['date_only'].min()
    max_date = df['date_only'].max()
    
    date_range = st.sidebar.date_input(
        "Date Range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date
    )
    
    if len(date_range) == 2:
        start_date, end_date = date_range
        df = df[(df['date_only'] >= start_date) & (df['date_only'] <= end_date)]

# --- Top Level Metrics ---
if not df.empty:
    col1, col2, col3 = st.columns(3)
    
    total_sessions = len(df)
    total_time_sec = df['duration_sec'].sum()
    total_time_str = str(timedelta(seconds=int(total_time_sec)))
    unique_projects = df['project'].nunique()
    
    col1.metric("Total Sessions", total_sessions)
    col2.metric("Total Time Tracked", total_time_str)
    col3.metric("Projects Worked On", unique_projects)
    
    st.divider()

# --- Main Content Area ---
tab1, tab2 = st.tabs(["📋 Session Log", "📊 Analytics"])

with tab1:
    col_refresh, _ = st.columns([1, 5])
    with col_refresh:
        if st.button("🔄 Refresh Data"):
            st.cache_data.clear()
            st.rerun()

    if df.empty:
        st.info("No tracking data available for this range. Start coding to log sessions!")
    else:
        # Display data table (filtering out the raw duration_sec column for cleaner UI)
        display_df = df[['id', 'project', 'git_branch', 'start_time', 'end_time', 'duration_str']].copy()
        
        # Format NULL/None branches for cleaner display
        display_df['git_branch'] = display_df['git_branch'].fillna('N/A')
        
        display_df.columns = ['ID', 'Project', 'Git Branch', 'Start Time', 'End Time', 'Duration']
        
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True
        )

with tab2:
    if not df.empty and df['duration_sec'].sum() > 0:
        
        # --- Heatmap (Daily Coding Hours) ---
        st.subheader("Daily Coding Heatmap")
        heatmap_data = df.groupby('date_only')['duration_sec'].sum().reset_index()
        heatmap_data['Hours'] = heatmap_data['duration_sec'] / 3600
        
        fig_heat = px.bar(
            heatmap_data,
            x='date_only',
            y='Hours',
            title='Total Hours Coded Per Day',
            labels={'date_only': 'Date', 'Hours': 'Hours'},
            color='Hours',
            color_continuous_scale='Blues'
        )
        st.plotly_chart(fig_heat, use_container_width=True)
        st.divider()
        
        
        col_chart1, col_chart2 = st.columns(2)
        
        with col_chart1:
            st.subheader("Time Spent per Project")
            
            # Aggregate data
            project_time = df.groupby('project')['duration_sec'].sum().reset_index()
            project_time['Hours'] = project_time['duration_sec'] / 3600
            
            # Plot using Plotly
            fig = px.pie(
                project_time, 
                values='Hours', 
                names='project', 
                hole=0.4,
                color_discrete_sequence=px.colors.sequential.Teal
            )
            fig.update_traces(textposition='inside', textinfo='percent+label')
            
            st.plotly_chart(fig, use_container_width=True)
            
        with col_chart2:
            st.subheader("Time Spent per Branch")
            branch_data = df.groupby('git_branch')['duration_sec'].sum().reset_index()
            branch_data['Hours'] = branch_data['duration_sec'] / 3600
            
            fig_branch = px.pie(
                branch_data,
                values='Hours',
                names='git_branch',
                hole=0.4,
                color_discrete_sequence=px.colors.sequential.Purp
            )
            fig_branch.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_branch, use_container_width=True)
            
        # Bar chart
        st.subheader("Recent Sessions Overview")
        fig_bar = px.bar(
            df.head(20), # Show last 20 sessions max
            x='id', 
            y='duration_sec', 
            color='project',
            hover_data=['git_branch'],
            labels={'duration_sec': 'Duration (Seconds)', 'id': 'Session ID'},
        )
        st.plotly_chart(fig_bar, use_container_width=True)
        
    else:
        st.info("Not enough data for analytics yet.")
