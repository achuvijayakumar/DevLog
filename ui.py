import streamlit as st
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date
import plotly.express as px
import plotly.graph_objects as go
import os
import json

DB_NAME = "/home/memoryping/apps/Devlog/devlog.db"

with open("/home/memoryping/apps/Devlog/config.json") as f:
    config = json.load(f)

# Load config options with logical defaults
MERGE_GAP = timedelta(seconds=config.get("merge_gap_seconds", 300))
CROSS_PROJECT_MERGE = config.get("cross_project_merge", False)


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
            query = "SELECT id, project, git_branch, start_time, end_time, duration FROM sessions ORDER BY id DESC"
            df = pd.read_sql_query(query, conn)
        except sqlite3.OperationalError:
            query = "SELECT id, project, start_time, end_time, duration FROM sessions ORDER BY id DESC"
            df = pd.read_sql_query(query, conn)
            df['git_branch'] = None

        conn.close()
        
        if not df.empty:
            df['duration_sec'] = df['duration'].fillna(0).astype(int)
            df['duration_str'] = df['duration_sec'].apply(lambda x: str(timedelta(seconds=x)))
            
            # Keep raw datetime for analytics before formatting
            df['start_dt'] = pd.to_datetime(df['start_time'], format='mixed', errors='coerce')
            df['start_time'] = df['start_dt'].dt.strftime('%Y-%m-%d %H:%M:%S')
            
            df['end_time'] = pd.to_datetime(df['end_time'], format='mixed', errors='ignore')
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
        if dur >= 900:
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
    
    # Convert to date objects if needed
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
    st.info(f"⚡ **Currently Tracking:** `{active_data['project']}` (Branch: *{active_data['git_branch'] or 'N/A'}*) | **Active for:** {active_duration}")
else:
    st.caption("No active session detected. Waiting for file changes...")

# --- Sidebar Filters ---
st.sidebar.header("Filters")
if not df.empty:
    df['date_only'] = df['start_dt'].dt.date
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
        display_df = df[['id', 'project', 'git_branch', 'start_time', 'end_time', 'duration_str']].copy()
        display_df['git_branch'] = display_df['git_branch'].fillna('N/A')
        display_df.columns = ['ID', 'Project', 'Git Branch', 'Start Time', 'End Time', 'Duration']
        
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
        heatmap_data['30d_Avg'] = heatmap_data['Hours'].rolling(window=30, min_periods=1).mean()
        
        fig_heat = go.Figure()
        
        # Bar chart for daily hours
        fig_heat.add_trace(go.Bar(
            x=heatmap_data['date_only'],
            y=heatmap_data['Hours'],
            name='Daily Hours',
            marker_color=heatmap_data['Hours'],
            marker_colorscale='Blues',
            hovertemplate='%{y:.1f}h<extra></extra>'
        ))
        
        # 7-day rolling average
        fig_heat.add_trace(go.Scatter(
            x=heatmap_data['date_only'],
            y=heatmap_data['7d_Avg'],
            name='7d Avg',
            mode='lines',
            line=dict(color='orange', width=2),
            hovertemplate='%{y:.1f}h (7d avg)<extra></extra>'
        ))
        
        # 30-day rolling average
        if len(heatmap_data) >= 14:  # Only show if we have decent data
            fig_heat.add_trace(go.Scatter(
                x=heatmap_data['date_only'],
                y=heatmap_data['30d_Avg'],
                name='30d Avg',
                mode='lines',
                line=dict(color='red', width=2, dash='dot'),
                hovertemplate='%{y:.1f}h (30d avg)<extra></extra>'
            ))
            
        fig_heat.update_layout(
            margin=dict(t=10),
            xaxis_title='Date',
            yaxis_title='Hours',
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
        )

        st.plotly_chart(fig_heat, use_container_width=True)
        st.divider()
        
        # --- Row 2: Project & Branch donuts ---
        col_chart1, col_chart2 = st.columns(2)
        
        with col_chart1:
            st.subheader("🗂️ Time per Project")
            project_time = df.groupby('project')['duration_sec'].sum().reset_index()
            project_time['Hours'] = project_time['duration_sec'] / 3600
            
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
            st.subheader("🌿 Time per Branch")
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
        
        st.divider()
        
        # --- Row 3: Peak Hours & Day-of-Week ---
        col_peak, col_dow = st.columns(2)
        
        with col_peak:
            st.subheader("🕐 Peak Coding Hours")
            df['hour'] = df['start_dt'].dt.hour
            hour_data = df.groupby('hour')['duration_sec'].sum().reset_index()
            # Fill missing hours with 0
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
            # Ensure all days present
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
        
        st.divider()
        
        # --- Row 4: Session Duration Distribution & Weekly Trend ---
        col_hist, col_trend = st.columns(2)
        
        with col_hist:
            st.subheader("📊 Session Length Distribution")
            df['duration_min'] = df['duration_sec'] / 60
            
            fig_hist = px.histogram(
                df,
                x='duration_min',
                nbins=20,
                labels={'duration_min': 'Duration (minutes)', 'count': 'Sessions'},
                color_discrete_sequence=['#636EFA']
            )
            fig_hist.update_layout(
                margin=dict(t=10),
                bargap=0.1,
                yaxis_title='Number of Sessions'
            )
            st.plotly_chart(fig_hist, use_container_width=True)
        
        with col_trend:
            st.subheader("📈 Weekly Coding Trend")
            df['week'] = df['start_dt'].dt.isocalendar().week.astype(int)
            df['year'] = df['start_dt'].dt.year
            df['year_week'] = df['year'].astype(str) + '-W' + df['week'].astype(str).str.zfill(2)
            
            weekly_data = df.groupby('year_week')['duration_sec'].sum().reset_index()
            weekly_data['Hours'] = weekly_data['duration_sec'] / 3600
            weekly_data = weekly_data.sort_values('year_week')
            
            fig_weekly = px.line(
                weekly_data,
                x='year_week',
                y='Hours',
                labels={'year_week': 'Week', 'Hours': 'Hours'},
                markers=True
            )
            fig_weekly.update_layout(margin=dict(t=10))
            fig_weekly.update_traces(line=dict(width=3, color='#00CC96'), marker=dict(size=8))
            st.plotly_chart(fig_weekly, use_container_width=True)
        
        st.divider()
        
        # --- Row 5: Session Gantt Chart & Recent Sessions ---
        st.subheader("🗺️ Session Timeline")
        # Format for Plotly Gantt (timeline)
        timeline_df = df.copy()
        
        # Convert times to proper datetimes if not already for plotting
        timeline_df['start_dt'] = pd.to_datetime(timeline_df['start_time'])
        # Handle cases where end span might be identical to start (0 sec) to ensure it renders
        timeline_df['end_dt'] = timeline_df.apply(
            lambda x: x['start_dt'] + timedelta(seconds=max(60, x['duration_sec'])), 
            axis=1
        )
        
        # We'll just show the last 7 days of sessions to not overload the chart
        week_ago = pd.Timestamp.now() - pd.Timedelta(days=7)
        recent_timeline = timeline_df[timeline_df['start_dt'] >= week_ago].copy()
        
        if not recent_timeline.empty:
            # Map projects to colors so they are consistent per row
            projects = recent_timeline['project'].unique()
            colors = px.colors.qualitative.Plotly * (len(projects) // len(px.colors.qualitative.Plotly) + 1)
            color_map = {proj: colors[i] for i, proj in enumerate(projects)}
            
            # Use 'project' for the Y axis
            fig_gantt = px.timeline(
                recent_timeline,
                x_start="start_dt",
                x_end="end_dt",
                y="project",
                color="project",
                color_discrete_map=color_map,
                hover_name="git_branch",
                hover_data={"duration_str": True, "project": False, "start_dt": False, "end_dt": False}
            )
            fig_gantt.update_yaxes(autorange="reversed")  # Top down
            fig_gantt.update_layout(
                margin=dict(t=10), 
                showlegend=False,
                xaxis_title="Time",
                yaxis_title="Project"
            )
            st.plotly_chart(fig_gantt, use_container_width=True)
            st.caption("Showing sessions from the last 7 days.")
        else:
            st.info("No sessions in the last 7 days to display on timeline.")
            
        st.divider()
        
        st.subheader("🕓 Recent Sessions Overview")
        fig_bar = px.bar(
            df.head(20),
            x='id', 
            y='duration_sec', 
            color='project',
            hover_data=['git_branch'],
            labels={'duration_sec': 'Duration (Seconds)', 'id': 'Session ID'},
        )
        fig_bar.update_layout(margin=dict(t=10))
        st.plotly_chart(fig_bar, use_container_width=True)
        
    else:
        st.info("Not enough data for analytics yet.")

with tab3:
    if not df.empty and df['duration_sec'].sum() > 0:
        
        st.subheader("🧠 Productivity Insights")
        st.markdown("Auto-generated insights based on your coding patterns.")
        
        # --- Avg session per project ---
        st.markdown("#### ⏱️ Average Session Duration by Project")
        avg_by_project = df.groupby('project')['duration_sec'].agg(['mean', 'median', 'count', 'sum']).reset_index()
        avg_by_project.columns = ['Project', 'Avg (sec)', 'Median (sec)', 'Sessions', 'Total (sec)']
        avg_by_project['Avg Duration'] = avg_by_project['Avg (sec)'].apply(fmt_duration)
        avg_by_project['Median Duration'] = avg_by_project['Median (sec)'].apply(fmt_duration)
        avg_by_project['Total Time'] = avg_by_project['Total (sec)'].apply(fmt_duration)
        
        st.dataframe(
            avg_by_project[['Project', 'Sessions', 'Avg Duration', 'Median Duration', 'Total Time']],
            use_container_width=True,
            hide_index=True
        )
        
        st.divider()
        
        # --- Longest sessions ---
        st.markdown("#### 🏅 Top 5 Longest Sessions")
        top_sessions = df.nlargest(5, 'duration_sec')[['project', 'git_branch', 'start_time', 'duration_str']].copy()
        top_sessions.columns = ['Project', 'Branch', 'Started', 'Duration']
        top_sessions['Branch'] = top_sessions['Branch'].fillna('N/A')
        st.dataframe(top_sessions, use_container_width=True, hide_index=True)
        
        st.divider()
        
        # --- Consistency score ---
        st.markdown("#### 📐 Consistency Score")
        if 'date_only' in df.columns:
            unique_dates = df['date_only'].nunique()
            date_range_days = (df['date_only'].max() - df['date_only'].min()).days + 1
            consistency = (unique_dates / date_range_days * 100) if date_range_days > 0 else 0
            
            ccol1, ccol2, ccol3 = st.columns(3)
            ccol1.metric("Days Coded", unique_dates)
            ccol2.metric("Date Range", f"{date_range_days} days")
            ccol3.metric("Consistency", f"{consistency:.0f}%", help="% of days in range with at least one session")
            
            # Progress bar
            st.progress(min(consistency / 100, 1.0))
        
        st.divider()
        
        # --- Time-of-day profile ---
        st.markdown("#### 🌗 Coding Time Profile")
        df['hour'] = df['start_dt'].dt.hour
        morning = df[(df['hour'] >= 6) & (df['hour'] < 12)]['duration_sec'].sum()
        afternoon = df[(df['hour'] >= 12) & (df['hour'] < 18)]['duration_sec'].sum()
        evening = df[(df['hour'] >= 18) & (df['hour'] < 22)]['duration_sec'].sum()
        night = df[((df['hour'] >= 22) | (df['hour'] < 6))]['duration_sec'].sum()
        
        profile_data = pd.DataFrame({
            'Period': ['🌅 Morning (6-12)', '☀️ Afternoon (12-18)', '🌆 Evening (18-22)', '🌙 Night (22-6)'],
            'Seconds': [morning, afternoon, evening, night]
        })
        profile_data['Hours'] = profile_data['Seconds'] / 3600
        profile_data['Formatted'] = profile_data['Seconds'].apply(fmt_duration)
        
        pcol1, pcol2, pcol3, pcol4 = st.columns(4)
        for i, (col, row) in enumerate(zip([pcol1, pcol2, pcol3, pcol4], profile_data.itertuples())):
            col.metric(row.Period, row.Formatted)
        
        # Determine persona
        max_period = profile_data.loc[profile_data['Seconds'].idxmax(), 'Period']
        if 'Night' in max_period or 'Evening' in max_period:
            st.markdown("🦉 **You're a night owl coder!**")
        elif 'Morning' in max_period:
            st.markdown("🐦 **You're an early bird coder!**")
        else:
            st.markdown("☀️ **You're an afternoon warrior!**")

    else:
        st.info("Not enough data for insights yet.")
