import streamlit as st
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date
import plotly.express as px
import plotly.graph_objects as go
import os
import json
import config

DB_NAME = config.DB_PATH

# Load config options from centralized module
MERGE_GAP = timedelta(seconds=config.MERGE_GAP_SECONDS)
CROSS_PROJECT_MERGE = config.CROSS_PROJECT_MERGE


st.set_page_config(
    page_title="Devlog Tracker",
    page_icon="⏱️",
    layout="wide"
)

st.title("⏱️ Devlog Tracking Dashboard")
st.markdown("Monitor your ongoing and past coding sessions.")

# --- Data Loading ---
@st.cache_data(ttl=5)
def load_data():
    if not os.path.exists(DB_NAME):
        return pd.DataFrame()
        
    try:
        conn = sqlite3.connect(DB_NAME)
        try:
            # Try to get category as well
            query = "SELECT id, project, git_branch, category, start_time, end_time, duration FROM sessions ORDER BY id DESC"
            df = pd.read_sql_query(query, conn)
        except sqlite3.OperationalError:
            # Fallback for old schema
            query = "SELECT id, project, git_branch, start_time, end_time, duration FROM sessions ORDER BY id DESC"
            df = pd.read_sql_query(query, conn)
            df['category'] = 'default'

        conn.close()
        
        if not df.empty:
            df['duration_sec'] = df['duration'].fillna(0).astype(int)
            df['duration_str'] = df['duration_sec'].apply(lambda x: str(timedelta(seconds=int(x))))
            
            # Keep raw datetime for analytics before formatting
            df['start_dt'] = pd.to_datetime(df['start_time'], format='mixed', errors='coerce')
            df['start_time_fmt'] = df['start_dt'].dt.strftime('%Y-%m-%d %H:%M:%S')
            
            df['end_dt'] = pd.to_datetime(df['end_time'], format='mixed', errors='coerce')
            df['end_time_fmt'] = df['end_dt'].dt.strftime('%Y-%m-%d %H:%M:%S')
            
        return df
    except Exception as e:
        st.error(f"Error loading database: {e}")
        return pd.DataFrame()

def get_active_session():
    """Reads the live session state dumped by tracker.py"""
    live_file = config.ACTIVE_SESSION_FILE
    if os.path.exists(live_file):
        try:
            with open(live_file, "r") as f:
                data = json.load(f)
                start = datetime.fromisoformat(data['start_time'])
                duration = datetime.now() - start
                duration_str = str(duration).split('.')[0]
                return data, duration_str
        except Exception:
            pass
    return None, None

# --- Helper Functions ---
def compute_deep_work_sessions(df):
    """Merge consecutive sessions (gap ≤ MERGE_GAP) and sum those ≥ 15 min."""
    if df.empty:
        return 0, 0
    
    # Ensure we have valid datetimes
    df = df.dropna(subset=['start_dt', 'duration_sec'])
    if df.empty: return 0, 0
    
    sorted_df = df.sort_values('start_dt').copy()
    sorted_df['end_dt'] = sorted_df['start_dt'] + pd.to_timedelta(sorted_df['duration_sec'], unit='s')

    merged = []
    for _, row in sorted_df.iterrows():
        # Check gap
        if merged and (row['start_dt'] - merged[-1]['end_dt']) <= MERGE_GAP:
            # Check project match if strict merging is enabled
            if CROSS_PROJECT_MERGE or row['project'] == merged[-1]['project']:
                merged[-1]['end_dt'] = max(merged[-1]['end_dt'], row['end_dt'])
            else:
                merged.append({'project': row['project'], 'start_dt': row['start_dt'], 'end_dt': row['end_dt']})
        else:
            merged.append({'project': row['project'], 'start_dt': row['start_dt'], 'end_dt': row['end_dt']})

    deep_count = 0
    deep_sec = 0
    for s in merged:
        dur = (s['end_dt'] - s['start_dt']).total_seconds()
        if dur >= 900: # 15 minutes
            deep_count += 1
            deep_sec += dur
            
    return deep_count, deep_sec

def compute_streak(dates_series):
    """Compute current and longest streak of consecutive coding days."""
    if dates_series.empty:
        return 0, 0
    unique_dates = sorted(dates_series.unique())
    if len(unique_dates) == 0:
        return 0, 0
    
    # Convert to date objects
    unique_dates = [pd.Timestamp(d).date() if not isinstance(d, date) else d for d in unique_dates]
    
    today = date.today()
    
    # Compute longest streak
    longest = 1
    current = 1
    for i in range(1, len(unique_dates)):
        if (unique_dates[i] - unique_dates[i-1]).days == 1:
            current += 1
            longest = max(longest, current)
        else:
            current = 1
    longest = max(longest, current)
    
    # Compute current streak (must include today or yesterday)
    if unique_dates[-1] < today - timedelta(days=1):
        current_streak = 0
    else:
        current_streak = 1
        for i in range(len(unique_dates) - 2, -1, -1):
            if (unique_dates[i+1] - unique_dates[i]).days == 1:
                current_streak += 1
            else:
                break
    
    return current_streak, longest

def fmt_duration(seconds):
    """Format seconds into a human-readable string."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    else:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h}h {m}m"


df = load_data()

# --- Live Active Session Banner ---
active_data, active_duration = get_active_session()
if active_data:
    st.info(f"⚡ **Currently Tracking:** `{active_data['project']}` ({active_data.get('category', 'default')}) | Branch: *{active_data.get('git_branch') or 'N/A'}* | **Active for:** {active_duration}")
else:
    st.caption("No active session detected. Waiting for file changes...")

# --- Sidebar Filters ---
st.sidebar.header("Filters")
if not df.empty:
    df['date_only'] = df['start_dt'].dt.date
    min_date = df['date_only'].min()
    max_date = df['date_only'].max()
    
    # Handle case where min_date == max_date
    if min_date == max_date:
        date_range = st.sidebar.date_input("Date Range", value=[min_date])
    else:
        date_range = st.sidebar.date_input("Date Range", value=(min_date, max_date))
    
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start_date, end_date = date_range
        df = df[(df['date_only'] >= start_date) & (df['date_only'] <= end_date)]
    elif isinstance(date_range, date):
         df = df[df['date_only'] == date_range]
    
    # Category filter
    all_categories = sorted(df['category'].fillna('default').unique().tolist())
    selected_categories = st.sidebar.multiselect("Categories", all_categories, default=all_categories)
    if selected_categories:
        df = df[df['category'].isin(selected_categories)]

    # Project filter
    all_projects = sorted(df['project'].unique().tolist())
    selected_projects = st.sidebar.multiselect("Projects", all_projects, default=all_projects)
    if selected_projects:
        df = df[df['project'].isin(selected_projects)]

# --- Top Level Metrics ---
if not df.empty:
    mcol1, mcol2, mcol3, mcol4 = st.columns(4)
    
    total_sessions = len(df)
    total_time_sec = df['duration_sec'].sum()
    total_time_str = fmt_duration(total_time_sec)
    unique_projects = df['project'].nunique()
    avg_session_sec = df['duration_sec'].mean()
    
    # Deep work metrics
    deep_work_count, deep_work_sec = compute_deep_work_sessions(df)
    deep_work_hours_str = f"{deep_work_sec / 3600:.1f}h" if deep_work_sec > 0 else "0h"
    focus_pct = (deep_work_sec / total_time_sec * 100) if total_time_sec > 0 else 0
    
    merge_gap_min = MERGE_GAP.total_seconds() / 60
    merge_desc = f"gap ≤ {merge_gap_min:.0f}m"
    if CROSS_PROJECT_MERGE: merge_desc += ", cross-project"
    
    mcol1.metric("Total Time", total_time_str)
    mcol2.metric("Avg Session", fmt_duration(avg_session_sec))
    mcol3.metric("Deep Work", deep_work_hours_str, help=f"Total hours in merged sessions ({merge_desc}) ≥ 15 min")
    mcol4.metric("Focus Score", f"{focus_pct:.0f}%", help="Deep Work Hours ÷ Total Hours")
    
    # Streak row
    current_streak, longest_streak = compute_streak(df['date_only'])

    scol1, scol2, scol3, scol4 = st.columns(4)
    
    today = date.today()
    yesterday = today - timedelta(days=1)
    today_sec = df[df['date_only'] == today]['duration_sec'].sum()
    yesterday_sec = df[df['date_only'] == yesterday]['duration_sec'].sum()
    delta_str = None
    if yesterday_sec > 0:
        delta_pct = ((today_sec - yesterday_sec) / yesterday_sec) * 100
        delta_str = f"{delta_pct:+.0f}%"
    
    scol1.metric("🔥 Current Streak", f"{current_streak} day{'s' if current_streak != 1 else ''}")
    scol2.metric("🏆 Longest Streak", f"{longest_streak} day{'s' if longest_streak != 1 else ''}")
    scol3.metric("📅 Today", fmt_duration(today_sec), delta=delta_str)
    scol4.metric("📅 Yesterday", fmt_duration(yesterday_sec))
    
    st.divider()

# --- Main Content Area ---
tab1, tab2, tab3 = st.tabs(["📋 Session Log", "📊 Analytics", "🧠 Insights"])

with tab1:
    col_refresh, _ = st.columns([1, 5])
    with col_refresh:
        if st.button("🔄 Refresh Data"):
            st.cache_data.clear()
            st.rerun()

    if df.empty:
        st.info("No tracking data available for this range. Start coding to log sessions!")
    else:
        display_df = df[['id', 'project', 'category', 'git_branch', 'start_time_fmt', 'end_time_fmt', 'duration_str']].copy()
        display_df['git_branch'] = display_df['git_branch'].fillna('N/A')
        display_df.columns = ['ID', 'Project', 'Category', 'Git Branch', 'Start Time', 'End Time', 'Duration']
        
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True
        )

with tab2:
    if not df.empty and df['duration_sec'].sum() > 0:
        
        # --- Row 1: Daily Coding Heatmap ---
        st.subheader("📆 Daily Coding Heatmap")
        heatmap_data = df.groupby('date_only')['duration_sec'].sum().reset_index()
        heatmap_data['Hours'] = heatmap_data['duration_sec'] / 3600
        heatmap_data = heatmap_data.sort_values('date_only')
        
        # Calculate rolling averages
        heatmap_data['7d_Avg'] = heatmap_data['Hours'].rolling(window=7, min_periods=1).mean()
        
        fig_heat = go.Figure()
        
        fig_heat.add_trace(go.Bar(
            x=heatmap_data['date_only'],
            y=heatmap_data['Hours'],
            name='Daily Hours',
            marker_color=heatmap_data['Hours'],
            marker_colorscale='Blues',
            hovertemplate='%{y:.1f}h<extra></extra>'
        ))
        
        fig_heat.add_trace(go.Scatter(
            x=heatmap_data['date_only'],
            y=heatmap_data['7d_Avg'],
            name='7d Avg',
            mode='lines',
            line=dict(color='orange', width=2),
            hovertemplate='%{y:.1f}h (7d avg)<extra></extra>'
        ))
            
        fig_heat.update_layout(
            margin=dict(t=10),
            xaxis_title='Date',
            yaxis_title='Hours',
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
        )

        st.plotly_chart(fig_heat, use_container_width=True)
        st.divider()
        
        # --- Row 2: Category & Project donuts ---
        col_chart1, col_chart2 = st.columns(2)
        
        with col_chart1:
            st.subheader("📁 Time per Category")
            cat_time = df.groupby('category')['duration_sec'].sum().reset_index()
            cat_time['Hours'] = cat_time['duration_sec'] / 3600
            
            fig_cat = px.pie(
                cat_time, 
                values='Hours', 
                names='category', 
                hole=0.4,
                color_discrete_sequence=px.colors.sequential.Teal
            )
            fig_cat.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_cat, use_container_width=True)
            
        with col_chart2:
            st.subheader("🗂️ Time per Project")
            project_time = df.groupby('project')['duration_sec'].sum().reset_index()
            project_time['Hours'] = project_time['duration_sec'] / 3600
            
            fig_proj = px.pie(
                project_time, 
                values='Hours', 
                names='project', 
                hole=0.4,
                color_discrete_sequence=px.colors.sequential.Purp
            )
            fig_proj.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_proj, use_container_width=True)
        
        st.divider()
        
        # --- Row 3: Peak Hours & Day-of-Week ---
        col_peak, col_dow = st.columns(2)
        
        with col_peak:
            st.subheader("🕐 Peak Coding Hours")
            df['hour'] = df['start_dt'].dt.hour
            hour_data = df.groupby('hour')['duration_sec'].sum().reset_index()
            all_hours = pd.DataFrame({'hour': range(24)})
            hour_data = all_hours.merge(hour_data, on='hour', how='left').fillna(0)
            hour_data['Minutes'] = hour_data['duration_sec'] / 60
            hour_data['Label'] = hour_data['hour'].apply(lambda h: f"{h:02d}:00")
            
            fig_peak = px.bar(
                hour_data,
                x='Label',
                y='Minutes',
                labels={'Label': 'Hour of Day', 'Minutes': 'Minutes'},
                color='Minutes',
                color_continuous_scale='Sunset'
            )
            fig_peak.update_layout(margin=dict(t=10), showlegend=False)
            st.plotly_chart(fig_peak, use_container_width=True)
        
        with col_dow:
            st.subheader("📅 Day-of-Week Pattern")
            day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            df['day_name'] = df['start_dt'].dt.day_name()
            dow_data = df.groupby('day_name')['duration_sec'].sum().reset_index()
            dow_data['Hours'] = dow_data['duration_sec'] / 3600
            all_days = pd.DataFrame({'day_name': day_order})
            dow_data = all_days.merge(dow_data, on='day_name', how='left').fillna(0)
            
            fig_dow = px.bar(
                dow_data,
                x='day_name',
                y='Hours',
                labels={'day_name': 'Day', 'Hours': 'Hours'},
                color='Hours',
                color_continuous_scale='Tealgrn',
                category_orders={'day_name': day_order}
            )
            fig_dow.update_layout(margin=dict(t=10))
            st.plotly_chart(fig_dow, use_container_width=True)
        
    else:
        st.info("Not enough data for analytics yet.")

with tab3:
    if not df.empty and df['duration_sec'].sum() > 0:
        st.subheader("🧠 Productivity Insights")
        
        # Determine persona
        df['hour'] = df['start_dt'].dt.hour
        morning = df[(df['hour'] >= 6) & (df['hour'] < 12)]['duration_sec'].sum()
        afternoon = df[(df['hour'] >= 12) & (df['hour'] < 18)]['duration_sec'].sum()
        evening = df[(df['hour'] >= 18) & (df['hour'] < 22)]['duration_sec'].sum()
        night = df[((df['hour'] >= 22) | (df['hour'] < 6))]['duration_sec'].sum()
        
        profile = {'Morning': morning, 'Afternoon': afternoon, 'Evening': evening, 'Night': night}
        max_period = max(profile, key=profile.get)
        
        if max_period == 'Night':
            st.success("🦉 **You're a Night Owl.** Your peak productivity is late at night.")
        elif max_period == 'Morning':
            st.success("🐦 **You're an Early Bird.** You get your best work done in the morning.")
        else:
            st.success(f"☀️ **You're an {max_period} Warrior.** You favor consistent work during the day.")

        st.divider()
        
        # Avg session per project
        avg_by_project = df.groupby('project')['duration_sec'].agg(['mean', 'count']).reset_index()
        avg_by_project.columns = ['Project', 'Avg (sec)', 'Sessions']
        avg_by_project['Avg Duration'] = avg_by_project['Avg (sec)'].apply(fmt_duration)
        
        st.markdown("#### ⏱️ Average Session Duration by Project")
        st.dataframe(avg_by_project[['Project', 'Sessions', 'Avg Duration']], use_container_width=True, hide_index=True)
    else:
        st.info("Not enough data for insights yet.")
