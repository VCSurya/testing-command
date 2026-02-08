from flask import Blueprint, redirect, url_for, render_template, jsonify, request, send_from_directory, session,current_app
from utils import get_db_connection, get_invoice_id, login_required, encrypt_password, decrypt_password,invoice_detailes,delete_user_log
import mysql.connector
from datetime import datetime
import pytz
from collections import defaultdict


ist = pytz.timezone('Asia/Kolkata')
now_ist = datetime.now(ist)
formatted_time = now_ist.strftime("%d-%m-%Y %H:%M")


# Create a Blueprint for admin routes
admin_bp = Blueprint('admin', __name__)

class AdminModel:
    def __init__(self):
        self.conn = get_db_connection()
        if not self.conn:
            raise Exception("Database connection failed")
        self.cursor = self.conn.cursor(dictionary=True)
    
    def get_dashboard_data(self):
        
        query = """

            SELECT 

                -- Case totals

                SUM(total_amount) AS today_paid_amount,
            
                -- Transaction counts

                SUM(Cash_) AS Total_cash_transaction,

                SUM(Online_) AS Total_online_transaction,

                SUM(Card_) AS Total_card_transaction,
            
                -- Payment mode amounts

                SUM(cash_amount) AS Total_cash_amount,

                SUM(online_amount) AS Total_online_amount,

                SUM(card_amount) AS Total_card_amount,
            
                -- Today's full revenue

                (SELECT SUM(inv.grand_total)

                FROM invoices inv

                JOIN live_order_track lot ON lot.invoice_id = inv.id

                WHERE DATE(inv.created_at) = CURRENT_DATE()

                AND lot.sales_proceed_for_packing = 1

                AND lot.cancel_order_status = 0

                AND inv.cancel_order_status = 0

                ) AS Today_revenue,

                 -- Today Sales
            
            	(SELECT COUNT(inv.id)

                FROM invoices inv

                JOIN live_order_track lot ON lot.invoice_id = inv.id

                WHERE DATE(inv.created_at) = CURRENT_DATE()

                AND lot.sales_proceed_for_packing = 1

                AND lot.cancel_order_status = 0

                AND inv.cancel_order_status = 0

                ) AS Today_sales,
            
                -- Today Not-Paid Money

                (SELECT SUM(inv.left_to_paid)

                FROM invoices inv

                JOIN live_order_track lot ON lot.invoice_id = inv.id

                WHERE DATE(inv.created_at) = CURRENT_DATE()

                AND lot.sales_proceed_for_packing = 1

                AND lot.cancel_order_status = 0

                AND inv.cancel_order_status = 0

                AND lot.left_to_paid_mode = 'not_paid'

                ) AS Today_not_paid_money
            
            FROM (

                -- Case 2

                SELECT 

                    SUM(invoices.left_to_paid) AS total_amount,
            
                    -- transaction count

                    SUM(live_order_track.left_to_paid_mode = 'cash') AS Cash_,

                    SUM(live_order_track.left_to_paid_mode = 'online') AS Online_,

                    SUM(live_order_track.left_to_paid_mode = 'card') AS Card_,
            
                    -- amount per mode

                    SUM(CASE WHEN live_order_track.left_to_paid_mode = 'cash' THEN invoices.left_to_paid ELSE 0 END) AS cash_amount,

                    SUM(CASE WHEN live_order_track.left_to_paid_mode = 'online' THEN invoices.left_to_paid ELSE 0 END) AS online_amount,

                    SUM(CASE WHEN live_order_track.left_to_paid_mode = 'card' THEN invoices.left_to_paid ELSE 0 END) AS card_amount
            
                FROM invoices

                JOIN live_order_track ON live_order_track.invoice_id = invoices.id

                WHERE DATE(invoices.created_at) = CURRENT_DATE()

                AND live_order_track.sales_proceed_for_packing = 1

                AND live_order_track.cancel_order_status = 0

                AND invoices.cancel_order_status = 0

                AND live_order_track.left_to_paid_mode != 'not_paid'

                AND DATE(live_order_track.payment_date_time) = CURRENT_DATE()
            
                UNION ALL
            
                -- Case 1

                SELECT 

                    SUM(invoices.paid_amount) AS total_amount,

                    SUM(invoices.payment_mode = 'cash') AS Cash_,

                    SUM(invoices.payment_mode = 'online') AS Online_,

                    SUM(invoices.payment_mode = 'card') AS Card_,
            
                    SUM(CASE WHEN invoices.payment_mode = 'cash' THEN invoices.paid_amount ELSE 0 END) AS cash_amount,

                    SUM(CASE WHEN invoices.payment_mode = 'online' THEN invoices.paid_amount ELSE 0 END) AS online_amount,

                    SUM(CASE WHEN invoices.payment_mode = 'card' THEN invoices.paid_amount ELSE 0 END) AS card_amount
            
                FROM invoices

                JOIN live_order_track ON live_order_track.invoice_id = invoices.id

                WHERE DATE(invoices.created_at) = CURRENT_DATE()

                AND live_order_track.sales_proceed_for_packing = 1

                AND live_order_track.cancel_order_status = 0

                AND invoices.cancel_order_status = 0

            ) AS combined;
            

        """

        self.cursor.execute(query)
        result = self.cursor.fetchone()
        
        return result

    def get_today_performers_data(self):
        query = """
            WITH role_stats AS (

                -- 1. Sales
                SELECT 
                    'Sales' AS role_name,
                    u.username,
                    COUNT(*) AS total
                FROM invoices i
                JOIN live_order_track lot ON lot.invoice_id = i.id
                JOIN users u ON u.id = i.invoice_created_by_user_id
                WHERE lot.sales_proceed_for_packing = 1
                AND lot.cancel_order_status = 0
                AND i.cancel_order_status = 0
                AND DATE(lot.sales_date_time) = CURRENT_DATE()
                AND u.role = 'Sales'
                GROUP BY u.username

                UNION ALL

                -- 2. Packaging
                SELECT 
                    'Packaging' AS role_name,
                    u.username,
                    COUNT(*) AS total
                FROM live_order_track lot
                JOIN users u ON u.id = lot.packing_proceed_by
                WHERE lot.sales_proceed_for_packing = 1
                AND lot.packing_proceed_for_transport = 1
                AND lot.cancel_order_status = 0
                AND DATE(lot.packing_date_time) = CURRENT_DATE()
                AND u.role = 'Packaging'
                GROUP BY u.username

                UNION ALL

                -- 3. Transport
                SELECT 
                    'Transport' AS role_name,
                    u.username,
                    COUNT(*) AS total
                FROM live_order_track lot
                JOIN users u ON u.id = lot.transport_proceed_by
                WHERE lot.sales_proceed_for_packing = 1
                AND lot.packing_proceed_for_transport = 1
                AND lot.transport_proceed_for_builty = 1
                AND lot.cancel_order_status = 0
                AND DATE(lot.transport_date_time) = CURRENT_DATE()
                AND u.role = 'Transport'
                GROUP BY u.username

                UNION ALL

                -- 4. Builty
                SELECT 
                    'Builty' AS role_name,
                    u.username,
                    COUNT(*) AS total
                FROM live_order_track lot
                JOIN users u ON u.id = lot.builty_proceed_by
                WHERE lot.sales_proceed_for_packing = 1
                AND lot.packing_proceed_for_transport = 1
                AND lot.builty_received = 1
                AND lot.cancel_order_status = 0
                AND DATE(lot.builty_date_time) = CURRENT_DATE()
                AND u.role = 'Builty'
                GROUP BY u.username

                UNION ALL

                -- 5. Account
                SELECT 
                    'Account' AS role_name,
                    u.username,
                    COUNT(*) AS total
                FROM live_order_track lot
                JOIN users u ON u.id = lot.payment_verify_by
                WHERE lot.sales_proceed_for_packing = 1
                AND lot.payment_confirm_status = 1
                AND lot.cancel_order_status = 0
                AND DATE(lot.payment_date_time) = CURRENT_DATE()
                AND u.role = 'Account'
                GROUP BY u.username
            )

            SELECT role_name, username, total
            FROM (
                SELECT 
                    role_name,
                    username,
                    total,
                    RANK() OVER (PARTITION BY role_name ORDER BY total DESC) AS rnk
                FROM role_stats
            ) ranked
            WHERE rnk = 1;

        """
        
        self.cursor.execute(query,)
        data = self.cursor.fetchall()

        result = defaultdict(list)
    
        for item in data:
            result[item["role_name"]].append({
                "username": item["username"],
                "total": item["total"]
            })
        return dict(result)

    def get_all_orders_data(self):
        query = f"""
                    SELECT 
                            invoices.invoice_number,
                            invoices.created_at,
                            invoices.id,

                            CASE
                                -- Cancelled stage (only when both cancel flags = 1)
                                WHEN invoices.cancel_order_status = 1
                                    AND live_order_track.cancel_order_status = 1
                                THEN cancelled_orders.cancelled_at

                                WHEN invoices.completed = 0
                                    AND live_order_track.sales_proceed_for_packing = 1
                                    AND live_order_track.payment_confirm_status = 0
                                THEN invoices.created_at

                                WHEN invoices.completed = 0
                                    AND live_order_track.payment_confirm_status = 1
                                    AND live_order_track.packing_proceed_for_transport = 0
                                THEN live_order_track.payment_date_time

                                WHEN invoices.completed = 0
                                    AND live_order_track.packing_proceed_for_transport = 1
                                    AND live_order_track.transport_proceed_for_builty = 0
                                THEN live_order_track.packing_date_time

                                WHEN invoices.completed = 0
                                    AND live_order_track.transport_proceed_for_builty = 1
                                    AND live_order_track.builty_received = 0
                                THEN live_order_track.transport_date_time

                                WHEN invoices.completed = 0
                                    AND live_order_track.builty_received = 1
                                    AND live_order_track.verify_by_manager = 0
                                THEN live_order_track.builty_date_time

                                WHEN invoices.completed = 1
                                    AND live_order_track.verify_by_manager = 1
                                THEN live_order_track.verify_manager_date_time
                            END AS stage_date_time,

                            CASE
                                WHEN invoices.cancel_order_status = 1
                                    AND live_order_track.cancel_order_status = 1
                                THEN 'Cancelled'

                                WHEN invoices.completed = 0
                                    AND live_order_track.sales_proceed_for_packing = 1
                                    AND live_order_track.payment_confirm_status = 0
                                THEN 'Payment'

                                WHEN invoices.completed = 0
                                    AND live_order_track.payment_confirm_status = 1
                                    AND live_order_track.packing_proceed_for_transport = 0
                                THEN 'Packing'

                                WHEN invoices.completed = 0
                                    AND live_order_track.packing_proceed_for_transport = 1
                                    AND live_order_track.transport_proceed_for_builty = 0
                                THEN 'Transport'

                                WHEN invoices.completed = 0
                                    AND live_order_track.transport_proceed_for_builty = 1
                                    AND live_order_track.builty_received = 0
                                THEN 'Builty'

                                WHEN invoices.completed = 0
                                    AND live_order_track.builty_received = 1
                                    AND live_order_track.verify_by_manager = 0
                                THEN 'Verification'

                                WHEN invoices.completed = 1
                                    AND live_order_track.verify_by_manager = 1
                                THEN 'Completed'
                            END AS pending_stage

                        FROM invoices
                        JOIN live_order_track 
                            ON live_order_track.invoice_id = invoices.id

                        LEFT JOIN cancelled_orders
                            ON cancelled_orders.invoice_id = invoices.id

                        WHERE 
                            (
                                -- show cancelled orders
                                invoices.cancel_order_status = 1
                                AND live_order_track.cancel_order_status = 1
                            )
                            OR
                            (
                                -- show non-cancelled orders
                                invoices.cancel_order_status = 0
                                AND live_order_track.cancel_order_status = 0
                                AND live_order_track.sales_proceed_for_packing = 1
                            )

                        ORDER BY stage_date_time ASC;
        """
        self.cursor.execute(query)
        data = self.cursor.fetchall()
        result = defaultdict(list)
        for item in data:
            result[item["pending_stage"]].append({
                "id":item["id"],
                "invoice_number": item["invoice_number"],
                "created_at": item["created_at"].strftime("%d/%m/%Y %I:%M %p"),
                "stage_date_time": item["stage_date_time"].strftime("%d/%m/%Y %I:%M %p") if item["stage_date_time"] else "" 
            })


        self.cursor.execute("""
            SELECT 
                inv.invoice_number, 
                inv.created_at, 
                inv.id
       
                FROM invoices inv 

                LEFT JOIN live_order_track lot ON inv.id = lot.invoice_id 

                where lot.verify_by_manager = 1 
                AND lot.cancel_order_status = 0 
                AND lot.sales_proceed_for_packing = 1 
                AND lot.packing_proceed_for_transport = 1 
                AND lot.transport_proceed_for_builty = 1 
                AND lot.builty_received = 1 
                AND lot.payment_confirm_status = 1 
                AND inv.completed = 1
                AND lot.left_to_paid_mode = 'not_paid'
                ORDER BY inv.created_at DESC;
        """)
        unpaid_orders = self.cursor.fetchall()
        for i in unpaid_orders:
            i['created_at'] = i['created_at'].strftime("%d/%m/%Y %I:%M %p")
    
        result['Unpaid'] = unpaid_orders
        return dict(result)

    def close(self):
        self.cursor.close()
        self.conn.close() # type: ignore
    
@admin_bp.route('/admin/invoice/<string:invoice_number>')
@login_required('Admin')
def show_invoice(invoice_number):
    result = invoice_detailes(invoice_number)
    return render_template('dashboards/admin/invoice.html', data=result)

# Admin Dashboard
@admin_bp.route('/admin/dashboard')
@login_required('Admin')
def admin_dashboard():
    my_mang = AdminModel()
    orders = my_mang.get_dashboard_data()
    my_mang.close()
    return render_template('dashboards/admin/admin.html', data=orders)

# all orders Routes
@admin_bp.route('/admin/all-orders')
@login_required('Admin')
def all_orders():
    admin = AdminModel()
    work_data = admin.get_all_orders_data()
    admin.close()
    return render_template('dashboards/admin/all_orders.html', data=work_data)

@admin_bp.route('/admin/today-performers')
@login_required('Admin')
def today_performers():
    conn = get_db_connection()
    
    if not conn:
        return jsonify({"success": False, "message": "Connection Error"})

    cursor = conn.cursor(dictionary=True)
    try:
        
        admin = AdminModel()
        performers = admin.get_today_performers_data()
        admin.close()
        return jsonify({"success": True, "data": performers})

    finally:
        cursor.close()
        conn.close()

def merge_orders_products(data):

        merged = {}

        for item in data:

            # change created_at date formate 
            item['created_at'] = item['created_at'].strftime("%d/%m/%Y %I:%M %p") 
            item['sales_date_time'] = item['sales_date_time'].strftime("%d/%m/%Y %I:%M %p")
            item['packing_date_time'] = item['packing_date_time'].strftime("%d/%m/%Y %I:%M %p")
            item['payment_date_time'] = item['payment_date_time'].strftime("%d/%m/%Y %I:%M %p")
            # passed tracking status with date            
            trackingStatus = 0
            trackingDates = []

            if item['sales_proceed_for_packing']:

                if item['sales_date_time']:
                    trackingDates.append(item['sales_date_time'])
                else:
                    trackingDates.append('')
                trackingStatus = 1                
            
                if item['packing_proceed_for_transport']:
                    
                    if item['packing_proceed_for_transport']:
                        trackingDates.append(item['packing_date_time'])
                    else:
                        trackingDates.append('')
                    trackingStatus = 2                
                
                    if item['transport_proceed_for_builty']:
                        
                        if item['transport_proceed_for_builty']:
                            trackingDates.append(item['transport_date_time'].strftime("%d/%m/%Y %I:%M %p"))
                        else:
                            trackingDates.append('')
                        trackingStatus = 3
            
                        if item['builty_received']:

                            if item['builty_received']:
                                trackingDates.append(item['builty_date_time'].strftime("%d/%m/%Y %I:%M %p"))
                            else:
                                trackingDates.append('')
                            trackingStatus = 4
            
                            if item['payment_confirm_status']:
                                
                                if item['payment_confirm_status']:
                                    trackingDates.append(item['payment_date_time'])
                                else:
                                    trackingDates.append('')
                                trackingStatus = 5


            item['trackingStatus'] = trackingStatus
            item['trackingDates'] = trackingDates


            # merge products
            order_id = item["id"]
            product_info = {
                "name": item["name"],
                "qty": item["quantity"],
                "price": float(item["price"]),
                "tax_amount": float(item["gst_tax_amount"]),
                "total": float(item["total_amount"]),
            }

            if order_id not in merged:
                # Create a new entry if the id doesn't exist yet
                merged[order_id] = {
                    **{k: v for k, v in item.items() if k not in ["name", "quantity", "price", "gst_tax_amount", "total_amount", "invoices_items_id", "product_id", "products_id"]},
                    "products": [product_info],
                }
            else:
                # If it already exists, just append the product info
                merged[order_id]["products"].append(product_info)

        return list(merged.values())

@admin_bp.route("/admin/uploads/packaging/<filename>")
@login_required('Admin')
def uploaded_image(filename):
    return send_from_directory("uploads/packaging", filename)

@admin_bp.route('/admin/my-orders-list', methods=['GET'])
@login_required('Admin')
def verify_order_list():
    try:
        query = f"""
               SELECT 
                inv.id, 
                inv.invoice_number, 
                inv.customer_id, 
                inv.grand_total, 
                inv.payment_mode, 
                inv.paid_amount, 
                inv.left_to_paid, 
                inv.transport_company_name,
                inv.invoice_created_by_user_id, 
                inv.payment_note as payment_note_1, 
                inv.gst_included, 
                inv.created_at, 
                inv.delivery_mode, 
                b.id AS buddy_id, 
                b.name AS customer, 
                b.address, 
                b.state, 
                b.pincode, 
                b.mobile, 

                u.id AS users_id, 
                u.username, 

                up.id AS pu_id, 
                up.username AS pu_name, 

                ut.id AS tu_id, 
                ut.username AS tu_name, 

                ub.id AS bu_id, 
                ub.username AS bu_name, 

                upay.id AS payu_id, 
                upay.username AS payu_name,

                ii.id AS invoices_items_id, 

                ii.product_id, 
                ii.quantity, 
                ii.price, 
                ii.gst_tax_amount, 
                ii.total_amount, 
                ii.created_at, 

                p.id AS products_id, 
                p.name, 

                lot.id AS live_order_track_id,
                lot.sales_proceed_for_packing,
                lot.sales_date_time,
                lot.packing_proceed_for_transport,
                lot.packing_date_time,
                lot.packing_proceed_by,
                lot.transport_proceed_for_builty,
                lot.transport_date_time,
                lot.transport_proceed_by,
                lot.builty_proceed_by,
                lot.builty_received,
                lot.builty_date_time,
                lot.payment_confirm_status,
                lot.cancel_order_status,
                lot.verify_by_manager,
                lot.payment_date_time,
                lot.left_to_paid_mode,
                lot.payment_note as payment_note_2 

                FROM invoices inv 

                LEFT JOIN buddy b ON inv.customer_id = b.id 
                LEFT JOIN invoice_items ii ON inv.id = ii.invoice_id 
                LEFT JOIN products p ON ii.product_id = p.id 
                LEFT JOIN live_order_track lot ON inv.id = lot.invoice_id 

                LEFT JOIN users u ON inv.invoice_created_by_user_id = u.id 
                LEFT JOIN users up ON lot.packing_proceed_by = up.id 
                LEFT JOIN users ut ON lot.transport_proceed_by = ut.id 
                LEFT JOIN users ub ON lot.builty_proceed_by = ub.id 
                LEFT JOIN users upay ON lot.payment_verify_by = upay.id 

                where lot.verify_by_manager = 0 
                AND lot.cancel_order_status = 0 
                AND lot.sales_proceed_for_packing = 1 
                AND lot.packing_proceed_for_transport = 1 
                AND lot.transport_proceed_for_builty = 1 
                AND lot.builty_received = 1 
                AND lot.payment_confirm_status = 1 
                AND inv.completed = 0
                AND lot.left_to_paid_mode != 'not_paid'
                ORDER BY inv.created_at DESC;
        """
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Database connection error'})

        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(query)
            events = cursor.fetchall()
        finally:
            cursor.close()
            conn.close()

        if events:
            merged_orders = merge_orders_products(events)
            return jsonify(merged_orders)
        
        return jsonify({'success': False, 'message': 'No events found'}),500

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}),500

@admin_bp.route('/admin/order-verify',methods=['POST'])
@login_required('Admin')
def confirm_verification():
    try:
        
        data = request.json
        
        if data is None or 'InvoiceNumber' not in data or not data.get('InvoiceNumber'):
            return jsonify({'success': False, 'message': 'Invalid input data'}),400

        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Database connection error'})

        if not session.get('user_id'):
            return jsonify({'success': False, 'message': 'User Not Found!'})


        _query = f"""
        SELECT id FROM `live_order_track` WHERE invoice_id = (SELECT id FROM `invoices` WHERE invoice_number = '{data.get('InvoiceNumber')}');
        """
        cursor_ = conn.cursor(dictionary=True)
        
        cursor_.execute(_query)
        live_order_track = cursor_.fetchone()   
        if not live_order_track:
            return jsonify({'success': False, 'message': 'Live Order Track Not Found!'}),500
        
        live_order_track_id = live_order_track.get('id')

        query = """
        UPDATE live_order_track
        set verify_by_manager = 1, verify_by_manager_id = %s ,verify_manager_date_time = NOW()
        WHERE id = %s
        """

        query_ = """
        UPDATE invoices
        set completed = 1
        WHERE id = (SELECT invoice_id FROM live_order_track WHERE id = %s);
        """

        cursor = conn.cursor(dictionary=True)
        
        try:
            cursor.execute(query,(session.get('user_id'),live_order_track_id))
            cursor.execute(query_,(live_order_track_id,))
            conn.commit()
        finally:
            cursor.close()
            conn.close()

        return {"success": True, "message": f"Done"}

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}),500

# User Management Routes
@admin_bp.route('/admin/users')
@login_required('Admin')
def manager_users():
    return render_template('dashboards/admin/users.html')


@admin_bp.route('/admin/users/data')
@login_required('Admin')
def get_users_data():
    conn = get_db_connection()
    if not conn:
        return jsonify([])

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
        SELECT id, name, username, role, created_by, updated_by,active
        FROM users WHERE boss = 0""")

        users = cursor.fetchall()
        return jsonify(users)

    finally:
        cursor.close()
        conn.close()


@admin_bp.route('/admin/users/add', methods=['POST'])
@login_required('Admin')
def add_user():
    data = request.json
    name = data.get('name')
    username = data.get('username')
    password = data.get('password')
    role = data.get('role')
    created_by = session.get('username')  # Get current user's ID from session

    if not all([name, username, password, role]):
        return jsonify({'success': False, 'message': 'Required fields are missing'})

    # Encrypt password
    encrypted_password = encrypt_password(password)

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})

    cursor = conn.cursor()

    try:
        # Check if username already exists
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        existing_user = cursor.fetchone()
        if existing_user:
            return jsonify({'success': False, 'message': f'{username}: Username already exists'})

        # Insert new user
        cursor.execute("""
            INSERT INTO users (name, username, password, role, created_by, updated_by, active ,created_at ,updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, 1,%s, %s)
        """, (name, username, encrypted_password, role, created_by, created_by, formatted_time, formatted_time))
        conn.commit()
        return jsonify({'success': True, 'message': 'User added successfully'})
    except mysql.connector.Error as err:
        return jsonify({'success': False, 'message': str(err)})
    finally:
        cursor.close()
        conn.close()


@admin_bp.route('/admin/users/<int:user_id>')
@login_required('Admin')
def get_user(user_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT id, name, username, role ,password
            FROM users
            WHERE id = %s AND boss = 0
        """, (user_id,))
        user = cursor.fetchone()
        
        user['password'] = decrypt_password(user['password'])
        
        if user:
            return jsonify(user)
        return jsonify({'success': False, 'message': 'User not found'})
    finally:
        cursor.close()
        conn.close()



@admin_bp.route('/admin/users/<int:user_id>/update', methods=['PUT'])
@login_required('Admin')
def update_user(user_id):
    data = request.json
    name = data.get('name')
    username = data.get('username')
    role = data.get('role')
    password = data.get('password')
    updated_by = session.get('username')  # Get current user's username from session
    

    # Get database connection
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})
    
    cursor = conn.cursor()
    try:
        # Get current timestamp for updated_at
        formatted_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        password = encrypt_password(password) if password else None

        # Update user in database
        if not password:
            return jsonify({'success': False, 'message': 'Sommething went wrong'})
        cursor.execute("""
            UPDATE users
            SET name = %s, username = %s, role = %s, updated_by = %s, updated_at = %s,password = %s
            WHERE id = %s AND boss = 0 AND active = 1
        """, (name, username,role, updated_by, formatted_time, password,user_id))
        conn.commit()
        return jsonify({'success': True, 'message': 'User updated successfully'})
    except mysql.connector.Error as err:
        return jsonify({'success': False, 'message': str(err)})
    finally:
        cursor.close()
        conn.close()

@admin_bp.route('/admin/users/deactivate-all', methods=['POST'])
@login_required('Admin')
def deactive_users():
    
    # Get database connection
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})
    
    cursor = conn.cursor()
    try:
    
        cursor.execute("""
            UPDATE users
            SET active = 0
        """)
        conn.commit()
        current_app.deactivate_all_user()
        return jsonify({'success': True, 'message': "All User's deactivat successfully"})
    except mysql.connector.Error as err:
        return jsonify({'success': False, 'message': str(err)})
    finally:
        cursor.close()
        conn.close()

@admin_bp.route('/admin/users/<int:user_id>/restore', methods=['PUT'])
@login_required('Admin')
def restor_user(user_id):
    
    # Get database connection
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})
    
    cursor = conn.cursor()
    try:
        
        # Update user in database
        cursor.execute("""
            UPDATE users
            SET active = 1
            WHERE id = %s AND boss = 0
        """, (user_id,))
        conn.commit()
        return jsonify({'success': True, 'message': 'User restore successfully'})
    except mysql.connector.Error as err:
        return jsonify({'success': False, 'message': str(err)})
    finally:
        cursor.close()
        conn.close()


@admin_bp.route('/admin/users/delete', methods=['POST'])
@login_required('Admin')
def delete_user():

    data = request.json
    # {'deleteUserName': 'trans', 'selectedUserId': ''}
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})
    
    if data.get('deleteUserName') is None or data.get('deleteUserName') == "":
        return jsonify({'success': False, 'message': 'Invalid Inofrmation!'})
        
    cursor = conn.cursor(dictionary=True)
    try:
        
        cursor.execute("""

                SELECT id FROM users
                WHERE username = %s AND active = 1
            
        """, (data.get('deleteUserName'),))

        user_exists = cursor.fetchone() 

        if user_exists is None: 
            return jsonify({'success': False, 'message': 'User not found.'})


        if data.get('selectedUserId') == "":
            cursor.execute("""
                UPDATE users
                SET active = 0
                WHERE id = %s
            """, (user_exists.get('id'),))
            conn.commit()
            current_app.deactivate_user(user_exists.get('id'))
            return jsonify({'success': True, 'message': 'User deleted successfully'})
        else:

            cursor.execute("""

                    SELECT id FROM users
                    WHERE id = %s AND active = 1 AND role = 'Sales'
                
            """, (data.get('selectedUserId'),))

            select_user_exists = cursor.fetchone()

            if not select_user_exists: 
                return jsonify({'success': False, 'message': 'Selected User not found.'})

            cursor.execute("""
                UPDATE invoices
                SET invoices.invoice_created_by_user_id = %s
                LEFT JOIN cancelled_orders 
                    ON cancelled_orders.invoice_id = invoices.id
                WHERE completed = 0
                AND invoice_created_by_user_id = %s
                AND NOT (
                        cancel_order_status = 1
                    AND confirm_by_saler = 1
                );
            """, (select_user_exists.get('id'),user_exists.get('id')))

            cursor.execute("""
                UPDATE users
                SET active = 0
                WHERE id = %s
            """, (user_exists.get('id'),))

            data['updated_by'] = session.get('username')
            data['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            delete_user_log(data)
    
            conn.commit()
            current_app.deactivate_user(user_exists.get('id'))
            return jsonify({'success': True, 'message': 'User deleted successfully'})
    
    except mysql.connector.Error as err:
        return jsonify({'success': False, 'message': str(err)})
    
    finally:
        cursor.close()
        conn.close()



# Market Events Management Routes

@admin_bp.route('/admin/events')
@login_required('Admin')
def manager_events_page():
    return render_template('dashboards/admin/events.html')

@admin_bp.route('/admin/all_events_details', methods=['GET','POST'])
@login_required('Admin')
def manager_events():

    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Database connection error'})

        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT 
                    id, 
                    name, 
                    location, 
                    DATE_FORMAT(start_date, '%d/%m/%Y') AS formatted_start_date, 
                    DATE_FORMAT(end_date, '%d/%m/%Y') AS formatted_end_date
                FROM market_events
                WHERE active = 1
                ORDER BY start_date ASC;
            """)
            events = cursor.fetchall()
        finally:
            cursor.close()
            conn.close()
        if not events:
            return jsonify({'success': False, 'message': 'No events found'}) if not events else jsonify(events)

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

    return jsonify({'success': False, 'message': 'No events found'}) if not events else jsonify(events)


@admin_bp.route('/admin/delete-event', methods=['DELETE'])
@login_required('Admin')
def delete_event():
    event_id = request.json.get('id') # Get event ID from request data
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Database connection error'})

        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE market_events
                SET active = 0
                WHERE id = %s AND active = 1
            """, (event_id,))
            conn.commit()
            if cursor.rowcount == 0:
                return jsonify({'success': False, 'message': 'Event not found or already deleted'})
        finally:
            cursor.close()
            conn.close()

        return jsonify({'success': True, 'message': 'Event deleted successfully'})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
    
@admin_bp.route('/admin/add-event', methods=['POST'])
@login_required('Admin')
def add_event():
    event_data = request.json
    if not all([event_data.get('event_name'), event_data.get('location'), event_data.get('start_date'), event_data.get('end_date')]):
        return jsonify({'success': False, 'message': 'Required fields are missing'})
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Database connection error'}), 500
        
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO market_events (name, location, start_date, end_date, active)
                VALUES (%s, %s, %s, %s, %s)
            """, (event_data.get('event_name'), event_data.get('location'), event_data.get('start_date'), event_data.get('end_date'), 1))
            conn.commit()
            if cursor.rowcount == 0:
                return jsonify({'success': False, 'message': 'Failed to add event'}), 500

        except Exception as e:
            conn.rollback()
            return jsonify({'success': False, 'message': "Something went wrong, please try again later"}), 500
        finally:
            cursor.close()
            conn.close()

        return jsonify({'success': True, 'message': 'Event added successfully'}), 200

    except Exception as e:
        return jsonify({'success': False, 'message': "Something went wrong, please try again later"}), 500
    

# Cutomer Management Routes
@admin_bp.route('/admin/customers', methods=['GET'])
@login_required('Admin')
def manager_customers():
    return render_template('dashboards/admin/customers.html')

@admin_bp.route('/admin/customers/data')
@login_required('Admin')
def get_customers_data():
    conn = get_db_connection()
    if not conn:
        return jsonify([])

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT 
            b.id,
            b.name,
            b.address,
            b.state,
            b.pincode,
            b.mobile,
            u1.name AS created_by,
            u2.name AS updated_by
            
            from buddy b
            LEFT JOIN users u1 on b.created_by = u1.id
            LEFT JOIN users u2 on b.updated_by = u2.id
            WHERE b.active = 1;
        """)

        customers = cursor.fetchall()
        return jsonify(customers)

    finally:
        cursor.close()
        conn.close()

@admin_bp.route('/admin/customer/add', methods=['POST'])
@login_required('Admin')
def add_customer():

    data = request.json
    
    name = data.get('name')
    address = data.get('address')
    state = data.get('state')
    pincode = data.get('pincode')
    mobile = data.get('mobile')

    if not all([name, address, state, pincode, mobile]):
        return jsonify({'success': False, 'message': 'Required fields are missing'})

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})

    created_by = session.get('user_id')  # Get current user's ID from session
    
    cursor = conn.cursor()

    try:
        # Check if username already exists
        cursor.execute("SELECT * FROM buddy WHERE mobile = %s and active = 1", (mobile,))
        existing_user = cursor.fetchone()
        
        if existing_user:
            return jsonify({'success': False, 'message': f'{mobile}: Mobile already exists'})

        # Insert new user
        cursor.execute("""
            INSERT INTO buddy (name, address, state, pincode, mobile, created_by, updated_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (name, address, state, pincode, mobile, created_by, created_by))
        conn.commit()

        return jsonify({'success': True, 'message': 'Customer added successfully'})
    except mysql.connector.Error as err:
        return jsonify({'success': False, 'message': "Something went wrong, please try again later"})
    finally:
        cursor.close()
        conn.close()

@admin_bp.route('/admin/customers/<int:user_id>/update', methods=['PUT'])
@login_required('Admin')
def update_customer(user_id):
    data = request.json
    
    name = data.get('name')
    address = data.get('address')
    state = data.get('state')
    pincode = data.get('pincode')
    mobile = data.get('mobile')
    updated_by = session.get('user_id')  # Get current user's username from session
    

    # Validate required fields
    if not all([name, address, state, pincode, mobile]):
        return jsonify({'success': False, 'message': 'Required fields are missing'})
    
    # Get database connection
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})
    
    cursor = conn.cursor()
    try:
        # Update user in database
        cursor.execute("""
            UPDATE buddy
            SET name = %s, address = %s, state = %s, pincode = %s, mobile = %s,updated_by = %s, updated_at = NOW()
            WHERE id = %s AND active = 1;
        """, (name, address, state, pincode, mobile, updated_by, user_id))
        conn.commit()
        return jsonify({'success': True, 'message': 'Customer detailes updated successfully'})
    except mysql.connector.Error as err:
        print(err)
        return jsonify({'success': False, 'message': "Something went wrong, please try again later"})
    finally:
        cursor.close()
        conn.close()

@admin_bp.route('/admin/customers/<int:user_id>/delete', methods=['DELETE'])
@login_required('Admin')
def delete_customer(user_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})

    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE buddy
            SET active = 0 , updated_at = NOW() , updated_by = %s
            WHERE id = %s
        """, (session.get('user_id'),user_id,))
        conn.commit()
        return jsonify({'success': True, 'message': 'Customer deleted successfully'})
    
    except mysql.connector.Error as err:
        return jsonify({'success': False, 'message': str(err)})
    
    finally:
        cursor.close()
        conn.close()

# Product Management Routes
@admin_bp.route('/admin/products', methods=['GET'])
@login_required('Admin')
def manager_products():
    return render_template('dashboards/admin/products.html')

@admin_bp.route('/admin/products/data')
@login_required('Admin')
def get_products_data():
    conn = get_db_connection()
    if not conn:
        return jsonify([])

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT 
            p.id,
            p.name,
            p.purchase_price,
            p.selling_price,
            u1.name AS created_by,
            u2.name AS updated_by

            from products p
            LEFT JOIN users u1 on p.created_by = u1.id
            LEFT JOIN users u2 on p.updated_by = u2.id
            WHERE p.active = 1;
        """)

        customers = cursor.fetchall()
        return jsonify(customers)

    finally:
        cursor.close()
        conn.close()

@admin_bp.route('/admin/products/add', methods=['POST'])
@login_required('Admin')
def add_product():

    data = request.json
    
    name = data.get('name')
    selling_price = data.get('selling_price')
    purchase_price = data.get('purchase_price')

    if not all([name, selling_price, purchase_price]):
        return jsonify({'success': False, 'message': 'Required fields are missing'})

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})

    created_by = session.get('user_id')  # Get current user's ID from session
    
    cursor = conn.cursor()

    try:
        # Check if username already exists
        cursor.execute("SELECT * FROM products WHERE name = %s and active = 1", (name,))
        existing_user = cursor.fetchone()
        
        if existing_user:
            return jsonify({'success': False, 'message': f'{name}: Product already exists'})

        # Insert new user
        cursor.execute("""
            INSERT INTO products (name, selling_price, purchase_price, created_by, updated_by)
            VALUES (%s, %s, %s, %s, %s)
        """, (name, selling_price, purchase_price, created_by, created_by))
        conn.commit()

        return jsonify({'success': True, 'message': 'Product added successfully'})
    except mysql.connector.Error as err:
        return jsonify({'success': False, 'message': "Something went wrong, please try again later"})
    finally:
        cursor.close()
        conn.close()

@admin_bp.route('/admin/products/<int:user_id>/update', methods=['PUT'])
@login_required('Admin')
def update_product(user_id):
    data = request.json
    
    name = data.get('name')
    selling_price = data.get('selling_price')
    purchase_price = data.get('purchase_price')

    updated_by = session.get('user_id')  # Get current user's username from session
    

    # Validate required fields
    if not all([name, selling_price, purchase_price]):
        return jsonify({'success': False, 'message': 'Required fields are missing'})
    
    # Get database connection
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})
    
    cursor = conn.cursor()
    try:
        # Update user in database
        cursor.execute("""
            UPDATE products
            SET name = %s, selling_price = %s, purchase_price = %s, updated_by = %s, updated_at = NOW()
            WHERE id = %s AND active = 1;
        """, (name, selling_price, purchase_price, updated_by, user_id))
        conn.commit()
        return jsonify({'success': True, 'message': 'Product details updated successfully'})
    except mysql.connector.Error as err:
        print(err)
        return jsonify({'success': False, 'message': "Something went wrong, please try again later"})
    finally:
        cursor.close()
        conn.close()

@admin_bp.route('/admin/products/<int:user_id>/delete', methods=['DELETE'])
@login_required('Admin')
def delete_products(user_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})

    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE products
            SET active = 0 , updated_at = NOW() , updated_by = %s
            WHERE id = %s
        """, (session.get('user_id'),user_id,))
        conn.commit()
        return jsonify({'success': True, 'message': 'Product deleted successfully'})
    
    except mysql.connector.Error as err:
        return jsonify({'success': False, 'message': str(err)})
    
    finally:
        cursor.close()
        conn.close()


# Transport Management Routes
@admin_bp.route('/admin/transport', methods=['GET'])
@login_required('Admin')
def transport():
    return render_template('dashboards/admin/transport.html')


@admin_bp.route('/admin/transport/data')
@login_required('Admin')
def get_transport_data():
    conn = get_db_connection()
    if not conn:
        return jsonify([])

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT 
            p.id,
            p.name,
            p.pincode,
            p.city,
            p.days,
            p.charges,
            p.active,
            u1.name AS created_by,
            u2.name AS updated_by
            from transport p
            LEFT JOIN users u1 on p.created_by = u1.id
            LEFT JOIN users u2 on p.updated_by = u2.id
        """)

        customers = cursor.fetchall()
        return jsonify(customers)

    finally:
        cursor.close()
        conn.close()


@admin_bp.route('/admin/transport/add', methods=['POST'])
@login_required('Admin')
def add_transport():

    data = request.json
    name = data.get('name')
    pincode = data.get('pincode')
    city = data.get('city')
    charges = data.get('charges')
    days = data.get('days')
    created_by = session.get('user_id')  # Get current user's ID from session

    if not all([name, pincode, city, charges, days]):
        return jsonify({'success': False, 'message': 'Required fields are missing'})

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})

    cursor = conn.cursor()

    if not pincode.isdigit():
        return jsonify({'success': False, 'message': 'Enter Valid Pincode.'})
    
    if not charges.isdigit():
        return jsonify({'success': False, 'message': 'Enter Valid Charges.'})
    
    if not days.isdigit():
        return jsonify({'success': False, 'message': 'Enter Valid Days.'})
    
    if int(days) <= 0 or int(charges) <= 0:
        return jsonify({'success': False, 'message': 'Enter Valid Data.'})

    try:
        # Insert new user
        cursor.execute("""
            INSERT INTO transport (name, pincode, city, charges, days, created_by, updated_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (name, pincode, city, charges, days, created_by, created_by))
        conn.commit()
        return jsonify({'success': True, 'message': 'Transport added successfully'})
    except mysql.connector.Error as err:
        return jsonify({'success': False, 'message': str(err)})
    finally:
        cursor.close()
        conn.close()


@admin_bp.route('/admin/transport/<int:user_id>/update', methods=['PUT'])
@login_required('Admin')
def update_transport(user_id):
    data = request.json
    
    name = data.get('name')
    city = data.get('city')
    charges = data.get('charges')
    pincode = data.get('pincode')
    days = data.get('days')
    updated_by = session.get('user_id')  # Get current user's username from session


    # Validate required fields
    if not all([name, pincode, city, charges, days]):
        return jsonify({'success': False, 'message': 'Required fields are missing'})

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})

    cursor = conn.cursor()

    if not pincode.isdigit():
        return jsonify({'success': False, 'message': 'Enter Valid Pincode.'})
    
    if not charges.isdigit():
        return jsonify({'success': False, 'message': 'Enter Valid Charges.'})
    
    if not days.isdigit():
        return jsonify({'success': False, 'message': 'Enter Valid Days.'})
    
    if int(days) <= 0 or int(charges) <= 0:
        return jsonify({'success': False, 'message': 'Enter Valid Data.'})
    
    # Get database connection
    conn = get_db_connection()
    
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})
    
    cursor = conn.cursor()
    
    try:
        # Update user in database
        cursor.execute("""
            UPDATE transport
            SET name = %s, city = %s, charges = %s, pincode = %s, days = %s, updated_by = %s, updated_at = NOW()
            WHERE id = %s;
        """, (name, city, charges, pincode, days, updated_by, user_id))
        conn.commit()
        return jsonify({'success': True, 'message': 'Transport details updated successfully'})
    
    except mysql.connector.Error as err:
        return jsonify({'success': False, 'message': "Something went wrong, please try again later"})
    
    finally:
        cursor.close()
        conn.close()


@admin_bp.route('/admin/transport/<int:user_id>/delete', methods=['DELETE'])
@login_required('Admin')
def delete_transport(user_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})

    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE transport
            SET active = 0 , updated_at = NOW() , updated_by = %s
            WHERE id = %s
        """, (session.get('user_id'),user_id,))
        conn.commit()
        return jsonify({'success': True, 'message': 'Transport deleted successfully'})
    
    except mysql.connector.Error as err:
        return jsonify({'success': False, 'message': str(err)})
    
    finally:
        cursor.close()
        conn.close()


@admin_bp.route('/admin/transport/<int:user_id>/restore', methods=['PUT'])
@login_required('Admin')
def restor_transport(user_id):
    
    # Get database connection
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})
    
    cursor = conn.cursor()
    try:
        
        # Update user in database
        cursor.execute("""
            UPDATE transport
            SET active = 1
            WHERE id = %s
        """, (user_id,))
        conn.commit()
        return jsonify({'success': True, 'message': 'Transport restore successfully'})
    except mysql.connector.Error as err:
        return jsonify({'success': False, 'message': str(err)})
    finally:
        cursor.close()
        conn.close()