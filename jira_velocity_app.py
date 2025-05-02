import streamlit as st
st.set_page_config(page_title="Jira Sprint Dashboard", layout="wide")

# --- Session state initialization ---
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "login_user" not in st.session_state:
    st.session_state["login_user"] = ""

from jira import JIRA
from collections import defaultdict
import pandas as pd
import plotly.express as px
#from st_aggrid import AgGrid, GridOptionsBuilder
from datetime import datetime

import sqlite3
import bcrypt

import os
from cryptography.fernet import Fernet


def load_or_create_key():
    if not os.path.exists("secret.key"):
        key = Fernet.generate_key()
        with open("secret.key", "wb") as f:
            f.write(key)
    with open("secret.key", "rb") as f:
        return f.read()


def encrypt_api_token(token: str) -> str:
    key = load_or_create_key()
    f = Fernet(key)
    return f.encrypt(token.encode()).decode()


def decrypt_api_token(token: str) -> str:
    key = load_or_create_key()
    f = Fernet(key)
    return f.decrypt(token.encode()).decode()


# --- Auth setup ---
DB_NAME = "users.db"
REGISTRATION_CODE = st.secrets["REGISTRATION_CODE"]


def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT,
            api_key TEXT
        )
        """)
    conn.commit()
    conn.close()


def register_user(username, password):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    try:
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_pw))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    conn.close()
    return success


def authenticate_user(username, password):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT password FROM users WHERE username = ?", (username,))
    result = c.fetchone()
    conn.close()
    if result and bcrypt.checkpw(password.encode('utf-8'), result[0].encode('utf-8')):
        return True
    return False


init_db()

if not st.session_state["authenticated"]:
    # --- Login/Register UI ---
    mode = st.sidebar.radio("Login or Register", ["Login", "Register"])

    if mode == "Register":
        st.title("📝 Register New User")
        reg_user = st.text_input("Choose a Username")
        reg_pass = st.text_input("Choose a Password", type="password")
        reg_code = st.text_input("Enter Registration Code", type="password")
        if st.button("Register"):
            if reg_code != REGISTRATION_CODE:
                st.error("Invalid registration code.")
            elif register_user(reg_user, reg_pass):
                st.success("Registration successful. Please login.")
            else:
                st.error("Username already exists.")
        st.stop()

    if mode == "Login" and not st.session_state.get("authenticated", False):
        st.title("🔐 Login")
        # Widgets
        username = st.text_input("Username", key="username_input")
        password = st.text_input("Password", type="password", key="password_input")

        # On login button click
        if st.button("Login"):
            if authenticate_user(username, password):
                st.session_state["authenticated"] = True
                st.session_state["login_user"] = username
                st.rerun()
            else:
                st.error("Invalid credentials")
        st.stop()

# --- If authenticated, show app ---
# --- Your main dashboard logic starts here ---
def time_to_hours(time_str):
    if not time_str:
        return 0.0
    parts = time_str.split()
    total = 0.0
    for part in parts:
        if "h" in part:
            total += float(part.replace("h", ""))
        elif "m" in part:
            total += float(part.replace("m", "")) / 60.0
    return total


#st.set_page_config(page_title="Jira Sprint Dashboard", layout="wide")
st.title("📊 Jira Sprint Velocity Dashboard")

# Sidebar: Jira connection and selection
with st.sidebar:
    if st.session_state.get("authenticated"):
        user = st.session_state.get("login_user", "Unknown")
        st.sidebar.markdown("---")
        st.sidebar.success(f"👋 Logged in as {user}")
        if st.sidebar.button("🚪 Logout"):
            st.session_state.clear()
            st.rerun()

    st.header("🔐 Jira Connection")
    jira_url = st.text_input("Jira URL", value="https://yourdomain.atlassian.net")
    email = st.text_input("Email", value="", help="Your Jira account email")
    # token = st.text_input("API Token", type="password")
    if st.session_state.get("authenticated", False):
        conn = sqlite3.connect("users.db")
        cursor = conn.cursor()
        cursor.execute("SELECT api_key FROM users WHERE username = ?", (st.session_state["login_user"],))
        row = cursor.fetchone()
        conn.close()

        try:
            default_api_key = decrypt_api_token(row[0]) if row and row[0] else ""
        except Exception:
            default_api_key = ""

        token = st.text_input("API Token", type="password", value=default_api_key)

        if st.button("💾 Save API Key"):
            encrypted_token = encrypt_api_token(token)
            conn = sqlite3.connect("users.db")
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET api_key = ? WHERE username = ?", (encrypted_token, st.session_state["login_user"]))
            conn.commit()
            conn.close()
            st.success("🔐 API key saved securely.")

    fetch_data = False
    selected_board_id = selected_sprint_id = None

    if jira_url and email and token:
        try:
            jira = JIRA(server=jira_url, basic_auth=(email, token))

            view_mode = st.radio("Generate Report By:", ["Sprint", "Project"], horizontal=True)

            boards = jira.boards()
            board_names = {b.name: b.id for b in boards}
            board_choice = st.selectbox("Select Board", list(board_names.keys()))
            selected_board_id = board_names[board_choice]

            sprints = jira.sprints(selected_board_id)
            sprint_names = {s.name: s.id for s in sprints}

            sprint_choice = None
            project_choice = None
            selected_sprint_id = None
            selected_fix_version = None
            selected_epic = None



            # project_key = "PPP"
            # fix_versions = sorted({version.name for issue in jira.search_issues(f'project={project_key}', maxResults=200)
            #         for version in issue.fields.fixVersions})
            # epics = sorted({label for issue in jira.search_issues(f'project={project_key}', maxResults=200)
            #         for label in issue.fields.labels})

            # epics = sorted({
            #     getattr(issue.fields, "customfield_10011", None)
            #     for issue in jira.search_issues(f'project={project_key}', fields="customfield_10011", maxResults=200)
            #     if getattr(issue.fields, "customfield_10011", None)
            # })

            if view_mode == "Sprint":
                sprint_choice = st.selectbox("Select Sprint", list(sprint_names.keys()))
                selected_sprint_id = sprint_names[sprint_choice]
            elif view_mode == "Project":
                projects = jira.projects()
                project_names = {p.name: p.key for p in projects}
                project_choice = st.selectbox("Select Project", list(project_names.keys()))

                # project_key = "PPP"

                # try:
                #     fix_versions = sorted({version.name for issue in jira.search_issues(f'project={project_key}', maxResults=200)
                #             for version in issue.fields.fixVersions})
                #     selected_fix_version = st.selectbox("Filter by Fix Version", fix_versions)
                # except Exception as e:
                #     st.error(f"Error loading project fix versions: {e}")

                # try:
                #     epics = sorted({getattr(issue.fields, "customfield_10011", None) for issue in jira.search_issues(f'project={project_key}', maxResults=200) if getattr(issue.fields, "customfield_10011", None)})
                #     selected_epic = st.selectbox("Filter by Epic (Label)", ["All"] + epics)
                # except Exception as e:
                #     st.error(f"Error loading project epics: {e}")

            # sprint_choice = st.selectbox("Select Sprint", list(sprint_names.keys()))
            # selected_sprint_id = sprint_names[sprint_choice]

            fetch_data = st.button("Generate Report")

            st.markdown("### ⚙️ Contingency Configuration")

            contingency_hours = st.number_input(
                "Available Contingency Hours (Total for Sprint):",
                min_value=0.0,
                value=1.0,
                step=1.0
            )

            recalc_button = st.button("🔁 Recalculate with Contingency")

        except Exception as e:
            st.sidebar.error(f"❌ Jira login failed:\n{e}")


def GenerateAllTasksChart(filtered_tasks):
    melted_tasks = filtered_tasks.melt(
        id_vars=["Assignee", "Issue Key", "Summary", "Due Date", "Overdue"],
        value_vars=["Estimated (hrs)", "Logged (hrs)", "Remaining (hrs)"],
        var_name="Type",
        value_name="Hours"
    )

    fig2 = px.bar(
        melted_tasks,
        x="Issue Key",
        y="Hours",
        color="Type",
        barmode="group",
        text_auto=True,
        hover_data=["Assignee", "Summary", "Due Date", "Overdue"],
        title="Effort Breakdown Per Task",
        height=600
    )

    st.plotly_chart(fig2, use_container_width=True)


def GenerateOpenIssuesByRemainingHoursChart(open_tasks_sorted):
    # Melt for charting
    melted_open = open_tasks_sorted.melt(
        id_vars=["Issue Key", "Assignee", "Summary", "Due Date", "Overdue", "Status"],
        value_vars=["Estimated (hrs)", "Logged (hrs)", "Remaining (hrs)"],
        var_name="Type",
        value_name="Hours"
    )

    # Optional: Visual marker for overdue
    melted_open["Overdue Label"] = melted_open["Overdue"].apply(lambda x: "🔴 Overdue" if x == "Yes" else "✅ On Track")

    fig3 = px.bar(
        melted_open,
        x="Issue Key",
        y="Hours",
        color="Type",
        barmode="group",
        text_auto=True,
        hover_data=["Assignee", "Summary", "Due Date", "Overdue Label", "Status"],
        title="Open (Not Done) Tasks by Remaining Hours",
        height=600
    )

    st.plotly_chart(fig3, use_container_width=True)


def RenderBody(selected_sprint_id=None, project_key=None, fix_version=None, epic=None):
    try:
        if selected_sprint_id:
            jql = f"sprint = {selected_sprint_id}"
        elif project_key:
            jql = f"project = {project_key} ORDER BY updated DESC"
            # jql = f'project = {project_key} AND fixVersion = "{fix_version}"'

            # if epic != "All":
            #     jql += f' AND labels = "{epic}"'

        else:
            st.error("No sprint or project specified.")
            return

        issues = jira.search_issues(
            jql,
            fields="assignee,timetracking,summary,duedate,status,customfield_10076",
            maxResults=500
        )

        velocity = defaultdict(lambda: {"estimate_hr": 0.0, "logged_hr": 0.0, "remaining_hr": 0.0, "Issue Key": []})
        velocity_dev = defaultdict(lambda: {"estimate_hr": 0.0, "logged_hr": 0.0, "remaining_hr": 0.0, "Issue Key": []})
        task_data = []
        today = datetime.today().date()

        for issue in issues:
            assignee = issue.fields.assignee.displayName if issue.fields.assignee else "Unassigned"
            dev_assignee_obj = getattr(issue.fields, "customfield_10076", None)
            dev_assignee = dev_assignee_obj.displayName if dev_assignee_obj else "Unknown"
            tracking = issue.fields.timetracking
            due_str = issue.fields.duedate
            due_date = due_str if due_str else "N/A"
            status = issue.fields.status.name if hasattr(issue.fields, "status") else "Unknown"

            estimate = time_to_hours(getattr(tracking, "originalEstimate", ""))
            logged = time_to_hours(getattr(tracking, "timeSpent", ""))
            overage = logged - estimate
            remaining = time_to_hours(getattr(tracking, "remainingEstimate", ""))
            efficiency = round((logged / estimate * 100) if estimate else 0, 1)

            # Determine if overdue
            overdue = False
            if due_str:
                try:
                    due_obj = datetime.strptime(due_str, "%Y-%m-%d").date()
                    overdue = due_obj < today
                except:
                    overdue = False

            # Build user summary
            velocity[assignee]["estimate_hr"] += estimate
            velocity[assignee]["logged_hr"] += logged
            velocity[assignee]["remaining_hr"] += remaining
            if velocity[assignee]["Issue Key"]:
                velocity[assignee]["Issue Key"] = velocity[assignee]["Issue Key"].append(issue.key)
                print(velocity[assignee]["Issue Key"])
            else:
                velocity[assignee]["Issue Key"] = []

            velocity_dev[dev_assignee]["estimate_hr"] += estimate
            velocity_dev[dev_assignee]["logged_hr"] += logged
            velocity_dev[dev_assignee]["remaining_hr"] += remaining
            if velocity_dev[dev_assignee]["Issue Key"]:
                velocity_dev[dev_assignee]["Issue Key"] = velocity_dev[dev_assignee]["Issue Key"].append(issue.key)
                print(velocity_dev[dev_assignee]["Issue Key"])
            else:
                velocity_dev[dev_assignee]["Issue Key"] = []

            # Store task
            task_data.append({
                "Assignee": assignee,
                "Development Assignee": dev_assignee,
                "Issue Key": issue.key,
                "Summary": issue.fields.summary,
                "Estimated (hrs)": round(estimate, 2),
                "Logged (hrs)": round(logged, 2),
                "Overage (hrs)": round(overage, 2),
                "Remaining (hrs)": round(remaining, 2),
                "Efficiency (%)": efficiency,
                "Contingency Used % (gain/loss)": round(overage / contingency_hours * 100, 2),
                "Due Date": due_date,
                "Overdue": "Yes" if overdue else "No",
                "Status": status
            })

        # === Summary - Assignee===
        df_summary = pd.DataFrame([
            {
                "User": user,
                "Issue Key": stats["Issue Key"],
                "Estimated (hrs)": round(stats["estimate_hr"], 2),
                "Logged (hrs)": round(stats["logged_hr"], 2),
                "Overage (hrs)": round(stats["logged_hr"] - stats["estimate_hr"], 2),
                "Remaining (hrs)": round(stats["remaining_hr"], 2),
                "Efficiency (%)": round((stats["logged_hr"] / stats["estimate_hr"] * 100) if stats["estimate_hr"] else 0, 2)
            }
            for user, stats in velocity.items()
        ])

        df_summary["Contingency Used % (gain/loss)"] = round(
            df_summary["Overage (hrs)"] / contingency_hours * 100, 2
        )
        total_overage = df_summary["Overage (hrs)"].sum()
        remaining_contingency = contingency_hours - total_overage

        df_tasks = pd.DataFrame(task_data)

        # ✅ Calculate Earned Value
        earned_value = df_tasks[
            df_tasks["Status"].str.lower().isin(["done", "closed"])
        ]["Estimated (hrs)"].sum()

        st.success(f"✅ Data fetched for {len(df_summary)} users and {len(df_tasks)} tasks.")

        with st.expander("⬇️ Summary - Assignee (Completed & Outstanding Tasks)👥"):
            st.markdown("""
            ### 👥 Summary Table

            **ℹ️ Efficiency (%)** = Logged ÷ Estimated × 100
            > **⬆️ >100%** = actuals exceeded estimate using contingency
            > **⬇️ <100%** = under estimate, subject to adding released contingency

            ℹ️ Assignee = Unassigned means Status is Done or Closed
            """)
            st.dataframe(df_summary, use_container_width=True)


            # === Summary Totals Row with 2 Decimal Rounding ===
            # Total row
            totals = {
                "User": "TOTAL",
                "Estimated (hrs)": round(df_summary["Estimated (hrs)"].sum(), 2),
                "Logged (hrs)": round(df_summary["Logged (hrs)"].sum(), 2),
                "Overage (hrs)": round(total_overage, 2),
                "Remaining (hrs)": round(df_summary["Remaining (hrs)"].sum(), 2),
                "Efficiency (%)": round((df_summary["Logged (hrs)"].sum() / df_summary["Estimated (hrs)"].sum() * 100), 2),
                "Contingency Used % (gain/loss)": round((total_overage / contingency_hours) * 100, 2) if contingency_hours > 0 else 0
            }

            df_totals = pd.DataFrame([totals])
            st.dataframe(
                df_totals.style
                    .format({
                        "Estimated (hrs)": "{:.2f}",
                        "Logged (hrs)": "{:.2f}",
                        "Overage (hrs)": "{:.2f}",
                        "Remaining (hrs)": "{:.2f}",
                        "Efficiency (%)": "{:.2f}",
                        "Contingency Used % (gain/loss)": "{:.2f}"
                    })
                    .set_properties(**{
                        'font-weight': 'bold',
                        'background-color': '#222'
                    }),
                use_container_width=True
            )

            # st.success(f"Remaining Contingency: {round(remaining_contingency, 2)} hrs")
            if remaining_contingency >= contingency_hours:
                st.success(f"✅ Remaining Contingency: {round(remaining_contingency, 2)} hrs, we gained {round(total_overage, 2)} hrs")
            else:
                st.error(f"⚠️ Remaining Contingency: {round(remaining_contingency, 2)} hrs, we lost {round(total_overage, 2)} hrs")

            st.info(f"📈 Earned Value (Completed Estimates): {round(earned_value, 2)} hrs")

        # === Summary - Development Assignee===
        df_summary_dev = pd.DataFrame([
            {
                "Development Assignee": user,
                "Estimated (hrs)": round(stats["estimate_hr"], 2),
                "Logged (hrs)": round(stats["logged_hr"], 2),
                "Overage (hrs)": round(stats["logged_hr"] - stats["estimate_hr"], 2),
                "Remaining (hrs)": round(stats["remaining_hr"], 2),
                "Efficiency (%)": round((stats["logged_hr"] / stats["estimate_hr"] * 100) if stats["estimate_hr"] else 0, 2)
            }
            for user, stats in velocity_dev.items()
        ])

        df_summary_dev["Contingency Used % (gain/loss)"] = round(
            df_summary_dev["Overage (hrs)"] / contingency_hours * 100, 2
        )
        total_overage = df_summary_dev["Overage (hrs)"].sum()
        remaining_contingency = contingency_hours - total_overage

        with st.expander("⬇️ Summary - Development Assignee (Sprint Tasks) 👥"):
            st.markdown("""
            ### 👥 Summary Table

            **ℹ️ Efficiency (%)** = Logged ÷ Estimated × 100
            > **⬆️ >100%** = actuals exceeded estimate using contingency
            > **⬇️ <100%** = under estimate, subject to adding released contingency
            """)
            st.dataframe(df_summary_dev, use_container_width=True)


            # === Summary Totals Row with 2 Decimal Rounding ===
            # Total row
            totals_dev = {
                "User": "TOTAL",
                "Estimated (hrs)": round(df_summary_dev["Estimated (hrs)"].sum(), 2),
                "Logged (hrs)": round(df_summary_dev["Logged (hrs)"].sum(), 2),
                "Overage (hrs)": round(total_overage, 2),
                "Remaining (hrs)": round(df_summary_dev["Remaining (hrs)"].sum(), 2),
                "Efficiency (%)": round((df_summary_dev["Logged (hrs)"].sum() / df_summary_dev["Estimated (hrs)"].sum() * 100), 2),
                "Contingency Used % (gain/loss)": round((total_overage / contingency_hours) * 100, 2) if contingency_hours > 0 else 0
            }

            df_totals_dev = pd.DataFrame([totals_dev])
            st.dataframe(
                df_totals_dev.style
                    .format({
                        "Estimated (hrs)": "{:.2f}",
                        "Logged (hrs)": "{:.2f}",
                        "Overage (hrs)": "{:.2f}",
                        "Remaining (hrs)": "{:.2f}",
                        "Efficiency (%)": "{:.2f}",
                        "Contingency Used % (gain/loss)": "{:.2f}"
                    })
                    .set_properties(**{
                        'font-weight': 'bold',
                        'background-color': '#222'
                    }),
                use_container_width=True
            )

            # st.success(f"Remaining Contingency: {round(remaining_contingency, 2)} hrs")
            if remaining_contingency >= contingency_hours:
                st.success(f"✅ Remaining Contingency: {round(remaining_contingency, 2)} hrs, we gained {round(total_overage, 2)} hrs")
            else:
                st.error(f"⚠️ Remaining Contingency: {round(remaining_contingency, 2)} hrs, we lost {round(total_overage, 2)} hrs")

            st.info(f"📈 Earned Value (Completed Estimates): {round(earned_value, 2)} hrs")

        # For session state after sorting / filtering etc
        st.session_state["issues"] = issues.copy()
        st.session_state["df_summary"] = df_summary.copy()
        st.session_state["df_summary_dev"] = df_summary_dev.copy()
        st.session_state["df_tasks"] = df_tasks.copy()
        st.session_state["df_totals"] = df_totals.copy()
        st.session_state["df_totals_dev"] = df_totals_dev.copy()


        with st.expander("⬇️ Charts - Sprint Totals 📉 📊"):
            # Bar Chart: Flat Per-Task View (No Facet by Assignee)
            st.subheader("📉 Issue Breakdown – All Tasks")

            filtered_tasks = df_tasks[
                (df_tasks["Estimated (hrs)"] > 0) |
                (df_tasks["Logged (hrs)"] > 0) |
                (df_tasks["Remaining (hrs)"] > 0)
            ]

            GenerateAllTasksChart(filtered_tasks)
            # melted_tasks = filtered_tasks.melt(
            #     id_vars=["Assignee", "Issue Key", "Summary", "Due Date", "Overdue"],
            #     value_vars=["Estimated (hrs)", "Logged (hrs)", "Remaining (hrs)"],
            #     var_name="Type",
            #     value_name="Hours"
            # )

            # fig2 = px.bar(
            #     melted_tasks,
            #     x="Issue Key",
            #     y="Hours",
            #     color="Type",
            #     barmode="group",
            #     text_auto=True,
            #     hover_data=["Assignee", "Summary", "Due Date", "Overdue"],
            #     title="Effort Breakdown Per Task",
            #     height=600
            # )

            # st.plotly_chart(fig2, use_container_width=True)


            # 📊 Additional Chart: Effort Breakdown by Development Assignee
            st.subheader("🧑‍💻 Effort Breakdown by Development Assignee")

            # If the column exists but has nulls, you can fill them
            df_tasks["Development Assignee"] = df_tasks["Development Assignee"].fillna("Unknown")

            if "Development Assignee" in df_tasks.columns and "Issue Key" in df_tasks.columns:
                dev_melted = df_tasks.melt(
                    id_vars=["Development Assignee", "Issue Key"],
                    value_vars=["Estimated (hrs)", "Logged (hrs)", "Remaining (hrs)"],
                    var_name="Type",
                    value_name="Hours"
                )

                fig_dev = px.bar(
                    dev_melted,
                    x="Development Assignee",
                    y="Hours",
                    color="Type",
                    barmode="group",
                    hover_data=["Issue Key", "Type", "Hours"],
                    title="Effort Breakdown by Development Assignee",
                    text_auto=True,
                    height=500
                )

                st.plotly_chart(fig_dev, use_container_width=True)
            else:
                st.warning("Development Assignee or Issue Key column is missing.")


        with st.expander("⬇️ Charts - Remaining Work 📉 📊"):
            # === Chart: Incomplete Tasks Only, Sorted by Remaining Descending ===
            st.subheader("📌 Open Issues (Not Done) – Sorted by Remaining Hours")

            # Filter: Exclude Done status
            open_tasks = df_tasks[
                (df_tasks["Status"].str.lower() != "closed") &
                (df_tasks["Status"].str.lower() != "done") &
                (df_tasks["Remaining (hrs)"] > 0)
            ]

            # Sort by Remaining hours
            open_tasks_sorted = open_tasks.sort_values("Remaining (hrs)", ascending=False)
            GenerateOpenIssuesByRemainingHoursChart(open_tasks_sorted)


            # Bar Chart: User-Level Breakdown
            st.subheader("📊 Effort Breakdown per User")
            melted_summary = df_summary.melt(
                id_vars=["User", "Issue Key"],
                value_vars=["Estimated (hrs)", "Logged (hrs)", "Remaining (hrs)"],
                var_name="Type",
                value_name="Hours"
            )
            fig1 = px.bar(
                melted_summary,
                x="User",
                y="Hours",
                color="Type",
                barmode="group",
                title="Effort Breakdown by User (Outstanding Tasks & Completed)",
                text_auto=True,
                hover_data=["Issue Key", "User", "Type", "Hours"],
            )
            st.plotly_chart(fig1, use_container_width=True)


        def style_metrics(df):
            numeric_cols = ["Overage (hrs)", "Efficiency (%)", "Contingency Used % (gain/loss)", "Estimated (hrs)", "Logged (hrs)", "Remaining (hrs)"]
            df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors="coerce")

            # Ensure status string format
            df["Status"] = df["Status"].astype(str)

            def row_color_logic(row):
                est = row["Estimated (hrs)"]
                over = row["Overage (hrs)"]
                remaining = row["Remaining (hrs)"]
                due_date = row["Due Date"]
                status = row["Status"].strip().lower()

                percent_over = (over / est) if est else 0

                today = datetime.today().date()

                # Default styles
                style_row = [""] * len(df.columns)

                # Color for shared columns
                if over <= 0:
                    color = "green"
                elif percent_over <= 0.10:
                    color = "orange"
                else:
                    color = "red"

                for i, col in enumerate(df.columns):
                    if col in ["Overage (hrs)", "Efficiency (%)", "Contingency Used % (gain/loss)"]:
                        style_row[i] = f"color: {color}; font-weight: bold"

                    elif col == "Remaining (hrs)":
                        if remaining == 0 and status not in ["done", "closed"]:
                            style_row[i] = "color: #ffeb3b; font-weight: bold"
                        elif remaining > 0 and over > 0:
                            style_row[i] = "color: orange; font-weight: bold"

                    elif col == "Due Date":
                        if due_date == "N/A":
                            style_row[i] = "color: #ffeb3b; font-weight: bold"
                        elif due_date != "N/A" and status not in ["done", "closed"]:
                            due_obj = datetime.strptime(due_date, "%Y-%m-%d").date()
                            days_overdue = (today - due_obj).days

                            if days_overdue > 3:
                                # More than 3 days overdue → RED
                                style_row[i] = "color: red; font-weight: bold"
                            elif 0 < days_overdue <= 3:
                                # 1–3 days overdue → ORANGE
                                style_row[i] = "color: orange; font-weight: bold"

                return style_row

            def color_overdue(val):
                return "color: red; font-weight: bold" if str(val).strip().lower() == "yes" else ""

            return (
                df.style
                .apply(lambda row: row_color_logic(row), axis=1)
                .map(color_overdue, subset=["Overdue"])
                .format("{:.2f}", subset=numeric_cols)
            )

        def style_totals(cols, totals_row):
            for i, (col, val) in enumerate(totals_row.items()):
                val_display = round(val, 2) if isinstance(val, (int, float)) else val
                delta = None
                delta_color = "gray"

                if col == "Overage (hrs)" and isinstance(val, (int, float)):
                    delta = f"{val:+.2f}"
                    if val > 0.1 * totals_row["Estimated (hrs)"]:
                        delta_color = "#ff4d4d"  # red
                    elif val > 0:
                        delta_color = "orange"

                elif col == "Contingency Used % (gain/loss)" and isinstance(val, (int, float)):
                    delta = f"{val:+.2f}%"
                    if val > 10:
                        delta_color = "#ff4d4d"  # red
                    elif val > 0:
                        delta_color = "orange"

                elif col == "Efficiency (%)" and isinstance(val, (int, float)):
                    delta = f"{val - 100:+.2f}%"
                    if val > 110:
                        delta_color = "#ff4d4d"
                    elif val > 100:
                        delta_color = "orange"

                badge_html = f"""
                    <span style="padding:3px 8px; border-radius:12px; background-color:{delta_color}; color:white; font-size:0.8rem;">
                        {delta if delta else ""}
                    </span>
                """ if delta else ""

                html = f"""
                    <div style="background-color:#111; padding:15px; border-radius:10px; text-align:center; border:1px solid #333;">
                        <div style="color:#AAA; font-size:0.85rem; margin-bottom:4px;">{col}</div>
                        <div style="color:white; font-size:1.4rem; font-weight:600; margin-bottom:6px;">{val_display}</div>
                        {badge_html}
                    </div>
                """
                cols[i].markdown(html, unsafe_allow_html=True)

        with st.expander("⬇️ Grids (Team) 🚧 🧩"):
            # Drill down Grids
            st.subheader("🚧 In-Progress Tasks Only")
            st.dataframe(style_metrics(open_tasks))

            open_totals_row = {
                "Assignee": "TOTAL",
                "Estimated (hrs)": round(open_tasks["Estimated (hrs)"].sum(), 2),
                "Logged (hrs)": round(open_tasks["Logged (hrs)"].sum(), 2),
                "Overage (hrs)": round(open_tasks["Overage (hrs)"].sum(), 2),
                "Remaining (hrs)": round(open_tasks["Remaining (hrs)"].sum(), 2),
                "Efficiency (%)": round((open_tasks["Logged (hrs)"].sum() / open_tasks["Estimated (hrs)"].sum() * 100), 2)
                    if open_tasks["Estimated (hrs)"].sum() > 0 else 0,
                "Contingency Used % (gain/loss)": round((open_tasks["Overage (hrs)"].sum() / contingency_hours * 100), 2)
                    if contingency_hours > 0 else 0
            }

            cols = st.columns(len(open_totals_row))
            style_totals(cols, open_totals_row)


            st.subheader("🧩 Per-Person Task Progress (Sprint)")
            st.dataframe(style_metrics(df_tasks))

            df_totals_row = {
                "Assignee": "TOTAL",
                "Estimated (hrs)": round(df_tasks["Estimated (hrs)"].sum(), 2),
                "Logged (hrs)": round(df_tasks["Logged (hrs)"].sum(), 2),
                "Overage (hrs)": round(df_tasks["Overage (hrs)"].sum(), 2),
                "Remaining (hrs)": round(df_tasks["Remaining (hrs)"].sum(), 2),
                "Efficiency (%)": round((df_tasks["Logged (hrs)"].sum() / df_tasks["Estimated (hrs)"].sum() * 100), 2)
                    if df_tasks["Estimated (hrs)"].sum() > 0 else 0,
                "Contingency Used % (gain/loss)": round((df_tasks["Overage (hrs)"].sum() / contingency_hours * 100), 2)
                    if contingency_hours > 0 else 0
            }

            cols = st.columns(len(df_totals_row))
            style_totals(cols, df_totals_row)

        assignees = df_tasks["Development Assignee"].dropna().unique()

        for assignee in sorted(assignees):
            with st.expander(f"👤 {assignee}"):
                # Filter each DataFrame
                assignee_in_progress_tasks = df_tasks[
                    (df_tasks["Development Assignee"] == assignee) &
                    (~df_tasks["Status"].str.lower().isin(["done", "closed"]))
                ]

                assignee_all_tasks = df_tasks[df_tasks["Development Assignee"] == assignee]

                st.subheader(f"🚧 {assignee} In-Progress Tasks Only")
                if not assignee_in_progress_tasks.empty:
                    st.dataframe(style_metrics(assignee_in_progress_tasks))

                    assignee_open_totals_row = {
                        "Assignee": f"{assignee}",
                        "Estimated (hrs)": round(assignee_in_progress_tasks["Estimated (hrs)"].sum(), 2),
                        "Logged (hrs)": round(assignee_in_progress_tasks["Logged (hrs)"].sum(), 2),
                        "Overage (hrs)": round(assignee_in_progress_tasks["Overage (hrs)"].sum(), 2),
                        "Remaining (hrs)": round(assignee_in_progress_tasks["Remaining (hrs)"].sum(), 2),
                        "Efficiency (%)": round((assignee_in_progress_tasks["Logged (hrs)"].sum() / assignee_in_progress_tasks["Estimated (hrs)"].sum() * 100), 2)
                            if assignee_in_progress_tasks["Estimated (hrs)"].sum() > 0 else 0,
                        "Contingency Used % (gain/loss)": round((assignee_in_progress_tasks["Overage (hrs)"].sum() / contingency_hours * 100), 2)
                            if contingency_hours > 0 else 0
                    }

                    cols = st.columns(len(assignee_open_totals_row))
                    style_totals(cols, assignee_open_totals_row)

                    # === Chart: Incomplete Tasks Only, Sorted by Remaining Descending ===
                    st.subheader("📌 Open Issues (Not Done) – Sorted by Remaining Hours")

                    # Sort by Remaining hours
                    assignee_open_tasks_sorted = assignee_in_progress_tasks.sort_values("Remaining (hrs)", ascending=False)
                    GenerateOpenIssuesByRemainingHoursChart(assignee_open_tasks_sorted)

                else:
                    st.info("No in-progress tasks.")

                st.subheader(f"🧩 {assignee} Task Progress (Sprint)")
                if not assignee_all_tasks.empty:
                    st.dataframe(style_metrics(assignee_all_tasks))

                    assignee_totals_row = {
                        "Assignee": f"{assignee}",
                        "Estimated (hrs)": round(assignee_all_tasks["Estimated (hrs)"].sum(), 2),
                        "Logged (hrs)": round(assignee_all_tasks["Logged (hrs)"].sum(), 2),
                        "Overage (hrs)": round(assignee_all_tasks["Overage (hrs)"].sum(), 2),
                        "Remaining (hrs)": round(assignee_all_tasks["Remaining (hrs)"].sum(), 2),
                        "Efficiency (%)": round((assignee_all_tasks["Logged (hrs)"].sum() / assignee_all_tasks["Estimated (hrs)"].sum() * 100), 2)
                            if assignee_all_tasks["Estimated (hrs)"].sum() > 0 else 0,
                        "Contingency Used % (gain/loss)": round((assignee_all_tasks["Overage (hrs)"].sum() / contingency_hours * 100), 2)
                            if contingency_hours > 0 else 0
                    }

                    cols = st.columns(len(assignee_totals_row))
                    style_totals(cols, assignee_totals_row)

                    # ✅ Calculate Earned Value
                    earned_value = assignee_all_tasks[
                        assignee_all_tasks["Status"].str.lower().isin(["done", "closed"])
                    ]["Estimated (hrs)"].sum()

                    st.info(f"📈 Earned Value (Completed Estimates): {round(earned_value, 2)} hrs")

                    # Bar Chart: Flat Per-Task View (No Facet by Assignee)
                    st.subheader("📉 Issue Breakdown – All Tasks")

                    assignee_filtered_tasks = assignee_all_tasks[
                        (df_tasks["Estimated (hrs)"] > 0) |
                        (df_tasks["Logged (hrs)"] > 0) |
                        (df_tasks["Remaining (hrs)"] >= 0)
                    ]

                    assignee_filtered_tasks_sorted = assignee_filtered_tasks.sort_values("Overage (hrs)", ascending=False)
                    GenerateAllTasksChart(assignee_filtered_tasks_sorted)
                else:
                    st.info("No tasks for this sprint.")


        # Downloads
        st.markdown("### 📁 File Export")
        with st.expander("⬇️ Export Options"):
            save_path = st.text_input("Optional Server Path to Save (e.g., c:\\Posse\\Sprint\\Reports):")

            summary_combined = pd.concat([df_summary, df_totals], ignore_index=True)

            st.download_button(
                "📥 Download Summary CSV",
                data=summary_combined.to_csv(index=False).encode("utf-8"),
                file_name="jira_velocity_summary.csv",
                mime="text/csv"
            )

            st.download_button(
                "📥 Download Open Tasks CSV",
                data=open_tasks.to_csv(index=False).encode("utf-8"),
                file_name=f"jira_sprint_{sprint_choice}_open_tasks.csv",
                mime="text/csv"
            )

            st.download_button(
                "📥 Download Task Breakdown CSV",
                data=df_tasks.to_csv(index=False).encode("utf-8"),
                file_name=f"jira_sprint_{sprint_choice}_tasks.csv",
                mime="text/csv"
            )

            st.caption("To change where files are saved, update your browser's download settings or paste a path above for server-side saving.")


    except Exception as e:
        st.error(f"❌ Error: {e}")


if st.session_state.get("authenticated", False):
    # Reload after sort / filter
    if "df_tasks" in st.session_state and "df_summary" in st.session_state \
            and "df_summary_dev" in st.session_state and not recalc_button and not fetch_data:
        try:
            df_tasks = st.session_state["df_tasks"]
            df_summary = st.session_state["df_summary"]
            df_summary_dev = st.session_state["df_summary_dev"]
            df_totals = st.session_state["df_totals"]
            df_totals_dev = st.session_state["df_totals_dev"]

            # RenderBody(selected_sprint_id)
            if view_mode == "Sprint":
                RenderBody(selected_sprint_id=selected_sprint_id, project_key=None, fix_version=None, epic=None)
            else:
                RenderBody(selected_sprint_id=None, project_key=project_names[project_choice], fix_version=selected_fix_version, epic=selected_epic)

        except Exception as e:
            st.error(f"❌ Error: {e}")

    # Reload after sort / filter
    if "df_tasks" in st.session_state and "df_summary" in st.session_state \
            and "df_summary_dev" in st.session_state and recalc_button:
        try:
            df_tasks = st.session_state["df_tasks"]
            df_summary = st.session_state["df_summary"]
            df_summary_dev = st.session_state["df_summary_dev"]
            df_totals = st.session_state["df_totals"]
            df_totals_dev = st.session_state["df_totals_dev"]


            # RenderBody(selected_sprint_id)
            if view_mode == "Sprint":
                RenderBody(selected_sprint_id=selected_sprint_id, project_key=None, fix_version=None, epic=None)
            else:
                RenderBody(selected_sprint_id=None, project_key=project_names[project_choice], fix_version=selected_fix_version, epic=selected_epic)

        except Exception as e:
            st.error(f"❌ Error: {e}")


    # Main load processing
    if fetch_data and selected_sprint_id:
        with st.spinner("📡 Fetching data from Jira..."):
            try:
                # RenderBody(selected_sprint_id)
                if view_mode == "Sprint":
                    RenderBody(selected_sprint_id=selected_sprint_id, project_key=None, fix_version=None, epic=None)
                else:
                    RenderBody(selected_sprint_id=None, project_key=project_names[project_choice], fix_version=selected_fix_version, epic=selected_epic)
            except Exception as e:
                st.error(f"❌ Error: {e}")

