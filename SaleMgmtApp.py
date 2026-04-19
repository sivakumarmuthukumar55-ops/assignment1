import streamlit as st
import mysql.connector
import pandas as pd
from datetime import date
import warnings

# --- 1. SILENCE EXTERNAL WARNINGS ---
# This stops the Pandas/SQLAlchemy warnings from flooding your terminal
warnings.filterwarnings("ignore", category=UserWarning, module="pandas")

# --- 2. CONFIGURATION & SESSION ---
st.set_page_config(page_title="Sales MS", layout="wide")

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user_info = {}

# --- 3. DATABASE CORE ---
def get_db_connection():
    return mysql.connector.connect(
        host="localhost", 
        user="root", 
        password="", 
        database="sales_management_system"
    )

def run_query(query, params=None, is_select=True):
    conn = get_db_connection()
    if is_select:
        # If it's a SELECT, return a DataFrame
        df = pd.read_sql(query, conn, params=params)
        conn.close()
        return df
    else:
        # If it's an action, execute and commit
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        conn.close()
        return None

def run_action(query, params=None):
    """Helper for INSERT/UPDATE/DELETE"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(query, params)
    conn.commit()
    conn.close()

# --- 4. AUTHENTICATION MODULE ---
def login_page():
    st.title("🔐 System Login")
    with st.form("login_form"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            res = run_query("SELECT * FROM users WHERE username=%s AND password=%s", (u, p))
            if not res.empty:
                st.session_state.authenticated = True
                st.session_state.user_info = res.iloc[0].to_dict()
                st.rerun()
            else:
                st.error("Invalid credentials")

# --- 5. FEATURE: UNIFIED DASHBOARD ---

def show_dashboard():
    st.header("📊 Unified Business Dashboard")
    user = st.session_state.user_info

    # --- FILTERS ---
    with st.container(border=True):
        # Added a 4th column for Product Filter
        f1, f2, f3, f4 = st.columns([1, 1, 1, 1])
        
        with f1:
            if user['role'] == 'Super Admin':
                branches_df = run_query("SELECT branch_id, branch_name FROM branches")
                branch_options = ["All Branches"] + list(branches_df['branch_name'])
                selected_branch = st.selectbox("Select Branch", branch_options)
            else:
                st.info(f"Branch: {user['username']}")
                selected_branch = "My Branch"

        with f2:
            status_filter = st.multiselect("Status", ["Open", "Close"], default=["Open", "Close"])

        with f3:
            # Fetch unique products for the filter
            products_df = run_query("SELECT DISTINCT product_name FROM customer_sales")
            product_options = ["All Products"] + list(products_df['product_name'])
            selected_product = st.selectbox("Select Product", product_options)

        with f4:
            date_range = st.date_input("Select Date Range", [])

    # --- DYNAMIC SQL BUILDING ---
    query = """
        SELECT s.*, b.branch_name 
        FROM customer_sales s 
        JOIN branches b ON s.branch_id = b.branch_id 
        WHERE 1=1
    """
    params = []

    # Branch Filtering Logic
    if user['role'] == 'Super Admin' and selected_branch != "All Branches":
        b_id = branches_df[branches_df['branch_name'] == selected_branch]['branch_id'].values[0]
        query += " AND s.branch_id = %s"
        params.append(int(b_id))
    elif user['role'] == 'Admin':
        query += " AND s.branch_id = %s"
        params.append(user['branch_id'])

    # Status Filtering Logic
    if status_filter:
        placeholders = ', '.join(['%s'] * len(status_filter))
        query += f" AND s.status IN ({placeholders})"
        params.extend(status_filter)

    # Product Filtering Logic (NEW)
    if selected_product != "All Products":
        query += " AND s.product_name = %s"
        params.append(selected_product)

    # Date Filtering Logic
    if len(date_range) == 2:
        query += " AND s.date BETWEEN %s AND %s"
        params.append(date_range[0])
        params.append(date_range[1])

    df = run_query(query, tuple(params))

    if df.empty:
        st.warning("No data found for selected filters.")
        return

    # --- KPIs ---
    t_gross = df['gross_sales'].sum()
    t_rec = df['received_amount'].sum()
    t_pen = df['pending_amount'].sum()
    
    k1, k2, k3 = st.columns(3)
    k1.metric("Gross Sales", f"₹{t_gross:,.0f}")
    k2.metric("Received", f"₹{t_rec:,.0f}")
    k3.metric("Pending", f"₹{t_pen:,.0f}")

    # --- CHARTS ---
    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Product-wise Sales")
        st.bar_chart(df.groupby('product_name')['gross_sales'].sum(), use_container_width=True)
    with c2:
        st.subheader("Branch-wise Sales")
        st.bar_chart(df.groupby('branch_name')['gross_sales'].sum(), use_container_width=True)

    # --- DATA TABLE ---
    st.subheader("Detailed Sales Data")
    st.dataframe(df, use_container_width=True, hide_index=True)

    
# --- 6. FEATURE: SQL QUERY MENU ---
def show_sql_query_menu():
    st.header("🔍SQL Reports for All Branches")
    
    # Define your reports here
    query_dict = {
        "--- Select a Report ---": None,
        "Retrieve all records from the customer_sales table": "SELECT * FROM customer_sales;",
        "Retrieve all records from the branches table": "SELECT * FROM branches;",
        "Retrieve all records from the payment_splits table": "SELECT * FROM payment_splits;",
        "Display all sales with status = 'Open'.": "SELECT * FROM customer_sales where status = 'Open';",
        "Calculate the total gross sales across all branches.": "SELECT SUM(gross_sales) AS Total_Sale_Amount FROM customer_sales;",
        "Calculate the total received amount across all sales": "SELECT SUM(Received_amount) AS Total_Amount_Received  FROM customer_sales;",
        "Calculate the total pending amount across all sales": "SELECT SUM(pending_amount) AS Total_Amount_Pending   FROM customer_sales;",
        "Count the total number of sales per branch": "SELECT  s.branch_id,b.branch_name,count(Sale_id)  FROM customer_sales s join branches b on s.branch_id=b.branch_id group by s.branch_id; ",
        "Find the average gross sales amount": "SELECT AVG(gross_sales) FROM customer_sales;",
        "Retrieve all sales belonging to the Chennai branch": "SELECT * FROM customer_sales where branch_id = 1;",
        "Total Sales by Product": "SELECT product_name, SUM(gross_sales) AS 'Total Sales' FROM customer_sales GROUP BY product_name;",
        "Total Pending by Product": "SELECT product_name, SUM(pending_amount) AS 'Total Pending' FROM customer_sales GROUP BY product_name;",
        "Count of Open Sales": "SELECT COUNT(*) AS 'Count' FROM customer_sales WHERE status = 'Open'",
        "Sales Count by Payment Method": "SELECT payment_method, COUNT(*) AS 'Count' FROM payment_splits GROUP BY payment_method;",
        "Retrieve sales details along with the branch name": "SELECT b.branch_name, s.* FROM customer_sales s Left join branches b on s.branch_id=b.branch_id;",
        "Retrieve sales details along with total payment received (using payment_splits)": "SELECT s.sale_id, s.name AS customer_name, s.gross_sales, SUM(p.amount_paid) AS total_received FROM customer_sales s LEFT JOIN payment_splits p ON s.sale_id = p.sale_id GROUP BY s.sale_id;",
        "Show branch-wise total gross sales (using JOIN & GROUP BY)": "Select b.branch_name,s.branch_id,sum(s.gross_sales) as total_sale from customer_sales s join branches b on s.branch_id = b.branch_id GROUP BY s.branch_id;",
        "Display sales along with payment method used": "Select p.payment_method, s.* from customer_sales s join payment_splits p on s.sale_id = p.sale_id;",
        "Retrieve sales along with branch admin name": "Select u.username as Admin_name, s.* from customer_sales s join users u on s.branch_id = u.branch_id;",
        "Find sales where the pending amount is greater than 5000": "Select * from customer_sales where pending_amount > 5000;",
        "Retrieve top 3 highest gross sales": "Select  * from customer_sales ORDER by gross_sales desc LIMIT 3;",
        "Find the branch with highest total gross sales": "select b.branch_name,s.branch_id,max(s.gross_sales) as highest_gross from customer_sales s join branches b on s.branch_id = b.branch_id GROUP by s.branch_id ORDER by highest_gross desc limit 1;",
        "Retrieve monthly sales summary (group by month & year)": "select YEAR(date) as Year,MONTHNAME(date) as Month, sum(gross_sales) as total_month_sales from customer_sales group by Year,Month;",
        "Calculate payment method-wise total collection (Cash / UPI / Card)": "select payment_method,sum(amount_paid) as total from payment_splits group by payment_method;",

    }

    # 1. Selection UI
    report_name = st.selectbox("Choose a report to generate:", list(query_dict.keys()))
    query = query_dict[report_name]

    # 2. Execution Logic
    if query:
        if st.button("Generate Report"):
            res = run_query(query)
            
            if res is not None and not res.empty:
                st.success(f"Showing results for: {report_name}")
                st.dataframe(res, width="stretch", hide_index=True)
            else:
                st.info("No data found for this report.")
    else:
        st.write("Please select a report from the dropdown above to begin.")
    
# --- 6. PLACEHOLDERS FOR WORKING FUNCTIONS ---

def add_sale_form():
    st.header("📝 New Sale")
    user = st.session_state.user_info
    
    with st.form("sale_form", clear_on_submit=True):
        # RBAC: Super Admin chooses branch, Admin is fixed
        if user['role'] == 'Super Admin':
            branches = run_query("SELECT branch_id, branch_name FROM branches")
            b_name = st.selectbox("Branch", branches['branch_name'])
            b_id = branches[branches['branch_name'] == b_name]['branch_id'].values[0]
        else:
            b_id = user['branch_id']
            st.info(f"Branch ID: {b_id}")

        name = st.text_input("Customer Name")
        prod = st.text_input("Product")
        gross = st.number_input("Gross Amount", min_value=0)
        rec = st.number_input("Initial Payment", min_value=0)

        if st.form_submit_button("Save Sale"):
            sql = "INSERT INTO customer_sales (branch_id, date, name, product_name, gross_sales, received_amount, status) VALUES (%s, CURDATE(), %s, %s, %s, %s, 'Open')"
            run_query(sql, (int(b_id), name, prod, gross, rec), is_select=False)
            st.success("Sale Recorded!")

def add_payment():
    st.header("💸 Record Payment Split")
    user = st.session_state.user_info
    
    # Predefined SQL: Only show 'Open' sales with pending money
    q = "SELECT sale_id, name, pending_amount FROM customer_sales WHERE status='Open'"
    if user['role'] == 'Admin':
        q += f" AND branch_id={user['branch_id']}"
    
    open_sales = run_query(q)
    
    if open_sales.empty:
        st.warning("No pending sales found.")
    else:
        with st.form("pay_form", clear_on_submit=True):
            sale_label = st.selectbox("Select Sale", open_sales['name'])
            s_id = open_sales[open_sales['name'] == sale_label]['sale_id'].values[0]
            amt = st.number_input("Amount", min_value=1)
            method = st.selectbox("Method", ["Cash", "UPI", "Card"])
            
            if st.form_submit_button("Submit Payment"):
                sql = "INSERT INTO payment_splits (sale_id, payment_date, amount_paid, payment_method) VALUES (%s, CURDATE(), %s, %s)"
                run_query(sql, (int(s_id), amt, method), is_select=False)
                st.success("Payment Added!")


# --- 7. MAIN NAVIGATION ---
if not st.session_state.authenticated:
    login_page()
else:
    st.sidebar.title(f"Hi, {st.session_state.user_info['username']}")
    choice = st.sidebar.radio("Menu", ["Dashboard", "Add Sale", "Add Payment", "SQL Query"])
    
    if st.sidebar.button("Logout"):
        st.session_state.authenticated = False
        st.rerun()

    if choice == "Dashboard": show_dashboard()
    elif choice == "Add Sale": add_sale_form()
    elif choice == "Add Payment": add_payment()
    elif choice == "SQL Query": show_sql_query_menu()