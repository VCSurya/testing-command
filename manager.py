from flask import Blueprint, json,render_template, jsonify, request, send_from_directory, session,current_app
from utils import get_db_connection, login_required, encrypt_password, decrypt_password,invoice_detailes,delete_user_log
from datetime import datetime
import pytz
from admin import AdminModel

ist = pytz.timezone('Asia/Kolkata')
now_ist = datetime.now(ist)
formatted_time = now_ist.strftime("%d-%m-%Y %H:%M")


# Create a Blueprint for manager routes
manager_bp = Blueprint('manager', __name__)

class ManagerModel:
    def __init__(self):
        self.conn = get_db_connection()
        if not self.conn:
            raise Exception("Database connection failed")
        self.cursor = self.conn.cursor(dictionary=True)
    

    def get_dashboard_data(self,user_id):

        self.cursor.execute(f"CALL manager_dashboard_data({user_id})")
        result_1 = self.cursor.fetchone()
        
        while self.cursor.nextset():
            pass

        self.cursor.execute("CALL admin_dashboard_data()")
        result_2 = self.cursor.fetchone()
        
        return result_1 | result_2

    def get_all_orders_data(self):
        self.cursor.callproc('get_all_orders_data')

        results = []
        for result in self.cursor.stored_results():
            results.append(result.fetchall())

        stage_data = results[0]
        unpaid_orders = results[1]

        from collections import defaultdict
        result = defaultdict(list)

        # Process stage data
        for item in stage_data:
            result[item["pending_stage"]].append({
                "id": item["id"],
                "invoice_number": item["invoice_number"],
                "created_at": item["created_at"].strftime("%d/%m/%Y %I:%M %p"),
                "stage_date_time": item["stage_date_time"].strftime("%d/%m/%Y %I:%M %p") if item["stage_date_time"] else ""
            })

        # Process unpaid
        for i in unpaid_orders:
            i['created_at'] = i['created_at'].strftime("%d/%m/%Y %I:%M %p")

        if unpaid_orders:
            result['Unpaid'] = unpaid_orders

        return dict(result)

    def close(self):
        self.cursor.close()
        self.conn.close() # type: ignore
    
@manager_bp.route('/manager/invoice/<string:invoice_number>')
@login_required('Manager')
def show_invoice(invoice_number):
    result = invoice_detailes(invoice_number)
    return render_template('dashboards/manager/invoice.html', data=result)


# Manager Dashboard
@manager_bp.route('/manager/dashboard')
@login_required('Manager')
def manager_dashboard():
    my_mang = ManagerModel()
    orders = my_mang.get_dashboard_data(session.get('user_id'))
    my_mang.close()
    return render_template('dashboards/manager/manager.html', data=orders)


# Verify Orders Routes
@manager_bp.route('/manager/verify-orders')
@login_required('Manager')
def verify_orders():
    return render_template('dashboards/manager/verify_orders.html')

# all orders Routes
@manager_bp.route('/manager/all-orders')
@login_required('Manager')
def all_orders():
    manager = ManagerModel()
    work_data = manager.get_all_orders_data()
    manager.close()
    return render_template('dashboards/manager/all_orders.html', data=work_data)

@manager_bp.route('/manager/today-performers')
@login_required('Manager')
def today_performers():
    conn = get_db_connection()
    
    if not conn:
        return jsonify({"success": False, "message": "Connection Error"})

    cursor = conn.cursor(dictionary=True)
    try:
        
        manager = AdminModel()
        performers = manager.get_today_performers_data()
        manager.close()
        return jsonify({"success": True, "data": performers})

    finally:
        cursor.close()
        conn.close()


@manager_bp.route("/manager/uploads/packaging/<filename>")
@login_required('Manager')
def uploaded_image(filename):
    return send_from_directory("uploads/packaging", filename)

@manager_bp.route('/manager/my-orders-list', methods=['GET'])
@login_required('Manager')
def verify_order_list():
    try:

        query = """

            SELECT 
                invoices.id, 
                invoices.invoice_number,
                DATE_FORMAT(
                        CONVERT_TZ(lot.sales_date_time, '+00:00', '+05:30'),
                        '%d/%m/%Y %h:%i %p'
                    ) AS sales_date_time

            FROM invoices
            LEFT JOIN live_order_track lot 
                ON invoices.id = lot.invoice_id 
            WHERE lot.verify_by_manager = 0 
                AND lot.cancel_order_status = 0 
                AND lot.sales_proceed_for_packing = 1 
                AND lot.packing_proceed_for_transport = 1 
                AND lot.transport_proceed_for_builty = 1 
                AND lot.builty_received = 1 
                AND lot.payment_confirm_status = 1 
                AND invoices.completed = 0
            ORDER BY invoices.created_at DESC;

        """

        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Database connection error'})

        cursor = conn.cursor(dictionary=True)

        cursor.execute(query)
        all_order_data = cursor.fetchall()

        if not all_order_data:
            return []

        return jsonify(all_order_data)        

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}),500

    finally:
        cursor.close()
        conn.close()


@manager_bp.route('/manager/order-verify', methods=['POST'])
@login_required('Manager')
def confirm_verification():
    try:
        data = request.json

        if not data or not data.get('InvoiceNumber'):
            return jsonify({'success': False, 'message': 'Invalid input data'}), 400

        if not session.get('user_id'):
            return jsonify({'success': False, 'message': 'User Not Found!'}), 401

        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Database connection error'}), 500

        cursor = conn.cursor()
        
        cursor.execute(
            "CALL verify_manager_order(%s, %s)",
            (data.get('InvoiceNumber'), session.get('user_id'))
        )
        conn.commit()

        return jsonify({"success": True, "message": "Done"})

    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

    finally:
        cursor.close()
        conn.close()


# User Management Routes
@manager_bp.route('/manager/users')
@login_required('Manager')
def manager_users():
    return render_template('dashboards/manager/users.html')


@manager_bp.route('/manager/users/data')
@login_required(['Admin', 'Manager'])
def get_users_data():
    conn = get_db_connection()
    if not conn:
        return jsonify([])

    cursor = conn.cursor(dictionary=True)

    try:

        if session.get('role') == 'Admin':
            cursor.execute("""
            SELECT id, name, username, role, created_by, updated_by,active
            FROM users WHERE boss = 0""")
        else:
            cursor.execute("""
            SELECT id, name, username, role, created_by, updated_by, active
            FROM users WHERE boss = 0 AND role != 'Manager' AND role != 'Admin'""")

        users = cursor.fetchall()
        return jsonify(users)

    finally:
        cursor.close()
        conn.close()

@manager_bp.route('/manager/users/deactivate-all', methods=['POST'])
@login_required('Manager')
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
    except Exception as err:
        return jsonify({'success': False, 'message': str(err)})
    finally:
        cursor.close()
        conn.close()

@manager_bp.route('/manager/users/<int:user_id>/restore', methods=['PUT'])
@login_required('Manager')
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
            WHERE id = %s AND boss = 0 AND role != 'Manager' AND role != 'Admin'
        """, (user_id,))
        conn.commit()
        return jsonify({'success': True, 'message': 'User restore successfully'})
    except Exception as err:
        return jsonify({'success': False, 'message': str(err)})
    finally:
        cursor.close()
        conn.close()

@manager_bp.route('/manager/users/add', methods=['POST'])
@login_required('Manager')
def add_user():
    data = request.json
    name = data.get('name')
    username = data.get('username')
    password = data.get('password')
    role = data.get('role')
    created_by = session.get('username')  # Get current user's ID from session

    if not all([name, username, password, role]):
        return jsonify({'success': False, 'message': 'Required fields are missing'})

    if role not in ["Sales","Packaging","Transport","Account","Builty","Retail"]:
        return jsonify({'success': False, 'message': 'Please select the right user role'})

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
            INSERT INTO users 
            (name, username, password, role, created_by, updated_by, active, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, 1, NOW(), NOW())
        """, (name, username, encrypted_password, role, created_by, created_by))
        conn.commit()
        return jsonify({'success': True, 'message': 'User added successfully'})
    except Exception as err:
        return jsonify({'success': False, 'message': str(err)})
    finally:
        cursor.close()
        conn.close()


@manager_bp.route('/manager/users/<int:user_id>')
@login_required('Manager')
def get_user(user_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT id, name, username, role ,password
            FROM users
            WHERE id = %s AND boss = 0 AND active = 1 AND role != 'Admin' AND role != 'Manager'
        """, (user_id,))
        user = cursor.fetchone()
        
        user['password'] = decrypt_password(user['password'])
        
        if user:
            return jsonify(user)
        return jsonify({'success': False, 'message': 'User not found'})
    finally:
        cursor.close()
        conn.close()



@manager_bp.route('/manager/users/<int:user_id>/update', methods=['PUT'])
@login_required('Manager')
def update_user(user_id):
    data = request.json
    name = data.get('name')
    username = data.get('username')
    password = data.get('password')
    updated_by = session.get('username')  # Get current user's username from session
    
    
    # Get database connection
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})
    
    cursor = conn.cursor()
    try:
        password = encrypt_password(password) if password else None

        # Update user in database
        if not password:
            return jsonify({'success': False, 'message': 'Sommething went wrong'})
        cursor.execute("""
            UPDATE users
            SET name = %s, username = %s, updated_by = %s, updated_at = NOW(),password = %s
            WHERE id = %s AND boss = 0 AND active = 1
        """, (name, username,updated_by, password,user_id))
        conn.commit()
        return jsonify({'success': True, 'message': 'User updated successfully'})
    except Exception as err:
        return jsonify({'success': False, 'message': str(err)})
    finally:
        cursor.close()
        conn.close()


@manager_bp.route('/manager/users/delete', methods=['POST'])
@login_required('Manager')
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
        
            cursor.callproc('delete_user_procedure', [
                data.get('deleteUserName'),
                int(data.get('selectedUserId') or 0)
            ])

            conn.commit()

            data['updated_at'] = formatted_time
            
            delete_user_log(data)

            cursor.execute("""

                    SELECT id FROM users
                    WHERE username = %s
                
            """, (data.get('deleteUserName'),))

            user_exists = cursor.fetchone()
            current_app.deactivate_user(user_exists.get('id'))
            return jsonify({'success': True, 'message': 'User deleted successfully'})
    
    except Exception as err:
        return jsonify({'success': False, 'message': str(err)})
    
    finally:
        cursor.close()
        conn.close()


# Market Events Management Routes

@manager_bp.route('/manager/events')
@login_required('Manager')
def manager_events_page():
    return render_template('dashboards/manager/events.html')

@manager_bp.route('/manager/all_events_details', methods=['GET','POST'])
@login_required('Manager')
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


@manager_bp.route('/manager/delete-event', methods=['DELETE'])
@login_required('Manager')
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
    
@manager_bp.route('/manager/add-event', methods=['POST'])
@login_required('Manager')
def add_event():
    event_data = request.json
    print(event_data)
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
@manager_bp.route('/manager/customers', methods=['GET'])
@login_required('Manager')
def manager_customers():
    return render_template('dashboards/manager/customers.html')

@manager_bp.route('/manager/customers/data')
@login_required('Manager')
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
            b.city,
            b.company,                                  
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

@manager_bp.route('/manager/customer/add', methods=['POST'])
@login_required('Manager')
def add_new_customer():
    try:
        data = request.get_json()
        required_fields = ['name', 'address', 'pincode', 'mobile']
        if not all(field in data for field in required_fields):
            return jsonify({'message': 'Missing required fields'}), 400

        name = data.get('name', '')
        state = data.get('state', '')
        address = data.get('address', '')
        pincode = data.get('pincode', '')
        mobile = data.get('mobile', '')
        city = data.get('city', '')
        company = data.get('company', '')

        conn = get_db_connection()

        if not conn:
            return jsonify({'success': False,'message': 'Database connection failed'}), 500

        if not all([name, address, state, pincode, mobile]):
            return jsonify({'success': False,'message': 'Please fill in all fields with valid information.'}),500

        if not mobile.isdigit():
            return jsonify({'success': False,'message': 'Enter valid mobile number'}),500

        if not pincode.isdigit():
            return jsonify({'success': False,'message': 'Enter valid PINCODE number'}),500
    
        cursor = conn.cursor(dictionary=True)

        # Check if mobile exists
        cursor.execute("SELECT 1 FROM buddy WHERE mobile = %s LIMIT 1", (mobile,))
        existing_user = cursor.fetchone()
        
        if existing_user:
            return jsonify({'success': False, 'message': f'{mobile}: Customer already exists'})
                
        # Insert into database
        cursor.execute("INSERT INTO buddy (name, address, state, pincode, mobile, city, company, created_by) VALUES (%s, %s, %s, %s, %s,%s,%s,%s)",
                                          (name, address, state, pincode, mobile, city, company, session.get('user_id')))
        conn.commit()
        
        mobile = int(mobile)
        cursor.execute("SELECT name, address,pincode, mobile FROM buddy WHERE mobile = %s",(mobile,))
        exist = cursor.fetchone()
        
        cursor.close()
        conn.close()

        if exist:
            return jsonify({'success': True, 'message': 'Customer added successfully'})
        
        else:
            return jsonify({'success': False, "message":"Somthing went wrong, Try Again!"})


    except Exception as e:
        conn.rollback()
        import traceback
        print(traceback.print_exc())
        return jsonify({'success': False,'message': 'Internal server error'}), 500

@manager_bp.route('/manager/customers/<int:user_id>/update', methods=['PUT'])
@login_required('Manager')
def update_customer(user_id):
    data = request.json
    
    name = data.get('name')
    address = data.get('address')
    state = data.get('state')
    pincode = data.get('pincode')
    mobile = data.get('mobile')
    company_name = data.get('company_name')
    city = data.get('city')
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
            SET name = %s, address = %s, state = %s, pincode = %s, mobile = %s, company=%s, city=%s, updated_by = %s, updated_at = NOW()
            WHERE id = %s AND active = 1;
        """, (name, address, state, pincode, mobile, company_name, city, updated_by, user_id))
        conn.commit()
        return jsonify({'success': True, 'message': 'Customer detailes updated successfully'})
    except Exception as err:
        return jsonify({'success': False, 'message': "Something went wrong, please try again later"})
    finally:
        cursor.close()
        conn.close()

@manager_bp.route('/manager/customers/<int:user_id>/delete', methods=['DELETE'])
@login_required('Manager')
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
    
    except Exception as err:
        return jsonify({'success': False, 'message': str(err)})
    
    finally:
        cursor.close()
        conn.close()

# Product Management Routes
@manager_bp.route('/manager/products', methods=['GET'])
@login_required('Manager')
def manager_products():
    return render_template('dashboards/manager/products.html')

@manager_bp.route('/manager/products/data')
@login_required('Manager')
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
            p.quantity,
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

@manager_bp.route('/manager/products/add', methods=['POST'])
@login_required('Manager')
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
        cursor.execute("SELECT 1 FROM products WHERE name = %s and active = 1 LIMIT 1", (name,))
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
    except Exception as err:
        return jsonify({'success': False, 'message': "Something went wrong, please try again later"})
    finally:
        cursor.close()
        conn.close()

@manager_bp.route('/manager/products/<int:user_id>/update', methods=['PUT'])
@login_required('Manager')
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
    except Exception as err:
        return jsonify({'success': False, 'message': "Something went wrong, please try again later"})
    finally:
        cursor.close()
        conn.close()

@manager_bp.route('/manager/products/<int:user_id>/update-stock', methods=['PUT'])
@login_required('Manager')
def update_product_stock(user_id):
    data = request.json
    
    qty = data.get('qty')
    price = data.get('price')
    note = data.get('note')

    updated_by = session.get('user_id')  # Get current user's username from session
    
    # Validate required fields
    if not all([qty, price]):
        return jsonify({'success': False, 'message': 'Required fields are missing'})
    
    if int(qty) <= 0 and int(price) <= 0:
        return jsonify({'success': False, 'message': 'Required valid input'})

    # Get database connection
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})
    
    cursor = conn.cursor()
    try:
        note = note + f' purchase_price : {price}'
        cursor.execute(f"CALL update_stock({user_id}, {qty}, {price}, {updated_by}, '{note}')")
        conn.commit()
        return jsonify({'success': True, 'message': 'Product stock updated successfully'})
    
    except Exception as err:
        conn.rollback()
        return jsonify({'success': False, 'message': str(err)})
    
    finally:
        cursor.close()
        conn.close()


@manager_bp.route('/manager/products/<int:user_id>/update-wastage-stock', methods=['PUT'])
@login_required('Manager')
def update_product_wastage_stock(user_id):
    data = request.json
    
    qty = data.get('qty')
    reason = data.get('reason')

    updated_by = session.get('user_id')  # Get current user's username from session
    
    # Validate required fields
    if not all([qty, reason]):
        return jsonify({'success': False, 'message': 'Required fields are missing'})
    
    # Get database connection
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})
    
    cursor = conn.cursor()
    try:
        
        cursor.execute(f"CALL update_out_stock({user_id}, {qty}, {updated_by}, '{reason}')")
        conn.commit()
        return jsonify({'success': True, 'message': 'Product stock updated successfully'})
    
    except Exception as err:
        conn.rollback()
        return jsonify({'success': False, 'message': str(err)})
    finally:
        cursor.close()
        conn.close()

@manager_bp.route('/manager/products/<int:user_id>/delete', methods=['DELETE'])
@login_required('Manager')
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
    
    except Exception as err:
        return jsonify({'success': False, 'message': str(err)})
    
    finally:
        cursor.close()
        conn.close()


# Transport Management Routes
@manager_bp.route('/manager/transport', methods=['GET'])
@login_required('Manager')
def transport():
    return render_template('dashboards/manager/transport.html')


@manager_bp.route('/manager/transport/data')
@login_required('Manager')
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
            u1.name AS created_by,
            u2.name AS updated_by
            from transport p
            LEFT JOIN users u1 on p.created_by = u1.id
            LEFT JOIN users u2 on p.updated_by = u2.id
            WHERE p.active = 1;
        """)

        customers = cursor.fetchall()
        return jsonify(customers)

    finally:
        cursor.close()
        conn.close()


@manager_bp.route('/manager/transport/add', methods=['POST'])
@login_required('Manager')
def add_transport():

    data = request.json
    name = data.get('name')
    pincode = data.get('pincode')
    city = data.get('city')

    created_by = session.get('user_id')  # Get current user's ID from session

    if not all([name, pincode, city]):
        return jsonify({'success': False, 'message': 'Required fields are missing'})

    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})

    cursor = conn.cursor()

    if not pincode.isdigit():
        return jsonify({'success': False, 'message': 'Enter Valid Pincode.'})
    
    try:
        # Insert new user
        cursor.execute("""
            INSERT INTO transport (name, pincode, city, charges, days, created_by, updated_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (name, pincode, city, 0, 1, created_by, created_by))
        conn.commit()
        return jsonify({'success': True, 'message': 'Transport added successfully'})
    except Exception as err:
        return jsonify({'success': False, 'message': str(err)})
    finally:
        cursor.close()
        conn.close()


@manager_bp.route('/manager/transport/<int:user_id>/update', methods=['PUT'])
@login_required('Manager')
def update_transport(user_id):
    data = request.json
    
    name = data.get('name')
    city = data.get('city')
    pincode = data.get('pincode')
    updated_by = session.get('user_id')  # Get current user's username from session


    # Validate required fields
    if not all([name, pincode, city]):
        return jsonify({'success': False, 'message': 'Required fields are missing'})

    if not pincode.isdigit():
        return jsonify({'success': False, 'message': 'Enter Valid Pincode.'})
    
    # Get database connection
    conn = get_db_connection()
    
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})
    
    cursor = conn.cursor()
    
    try:
        # Update user in database
        cursor.execute("""
            UPDATE transport
            SET name = %s, city = %s, pincode = %s, updated_by = %s, updated_at = NOW()
            WHERE id = %s AND active = 1;
        """, (name, city, pincode, updated_by, user_id))
        conn.commit()
        return jsonify({'success': True, 'message': 'Transport details updated successfully'})
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
    
    finally:
        cursor.close()
        conn.close()


@manager_bp.route('/manager/transport/<int:user_id>/delete', methods=['DELETE'])
@login_required('Manager')
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
    
    except Exception as err:
        return jsonify({'success': False, 'message': str(err)})
    
    finally:
        cursor.close()
        conn.close()


@manager_bp.route('/manager/invoice-details/<invoiceNumber>', methods=['GET'])
@login_required(['Manager'])
def manager_invoice_details(invoiceNumber):
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = conn.cursor(dictionary=True)
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not logged in'}), 401
        
        cursor.callproc('get_manager_invoice_details', (invoiceNumber,))
            
        result = None
        for res in cursor.stored_results():
            result = res.fetchone()

        if not result:
            return None

        for field in ["trackingDates", "products", "charges"]:
            if result.get(field):
                try:
                    result[field] = json.loads(result[field])
                except Exception:
                    result[field] = []
            else:
                result[field] = []

        return result

    except Exception as e:
        return jsonify({'error': str(e)}), 500

    finally:
        cursor.close()
        conn.close()