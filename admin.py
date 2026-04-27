from flask import Blueprint,json, render_template, jsonify, request, session,current_app
from utils import get_db_connection, login_required, encrypt_password, decrypt_password,invoice_detailes,delete_user_log
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
        
        self.cursor.execute("CALL admin_dashboard_data()")
        result = self.cursor.fetchone()

        return result

    def get_today_performers_data(self):
                      
        self.cursor.execute("CALL today_performance()")
        data = self.cursor.fetchall()
        result = defaultdict(list)

        for item in data:
            result[item["role_name"]].append({
                "username": item["username"],
                "total": item["total"]
            })
        
        return dict(result)

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


# User Management Routes
@admin_bp.route('/admin/users')
@login_required('Admin')
def manager_users():
    return render_template('dashboards/admin/users.html')

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
        cursor.execute(
            "SELECT 1 FROM users WHERE username = %s LIMIT 1",
            (username,)
        )
        user_exists = cursor.fetchone() is not None

        if user_exists:
            return jsonify({
                'success': False,
                'message': f'Username "{username}" already exists'
            }), 409
        
        # Insert new user
        cursor.execute("""
            INSERT INTO users (name, username, password, role, created_by, updated_by, active ,created_at ,updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, 1,%s, %s)
        """, (name, username, encrypted_password, role, created_by, created_by, formatted_time, formatted_time))
        
        conn.commit()
        return jsonify({'success': True, 'message': 'User added successfully'})
    
    except Exception as err:
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
            SET name = %s, username = %s, updated_by = %s, updated_at = %s,password = %s
            WHERE id = %s AND boss = 0 AND active = 1
        """, (name, username,updated_by, formatted_time, password,user_id))
        conn.commit()
        return jsonify({'success': True, 'message': 'User updated successfully'})
    
    except Exception as err:
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
    except Exception as err:
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
    except Exception as err:
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

@admin_bp.route('/admin/customer/add', methods=['POST'])
@login_required('Admin')
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
        
        if cursor.fetchone():
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

@admin_bp.route('/admin/customers/<int:user_id>/update', methods=['PUT'])
@login_required('Admin')
def update_customer(user_id):
    data = request.json
    
    name = data.get('name')
    address = data.get('address')
    state = data.get('state')
    pincode = data.get('pincode')
    mobile = data.get('mobile')
    company_name = data.get('company_name')
    city = data.get('city')
    updated_by = session.get('user_id')
    

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
    
    except Exception as err:
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
        return jsonify({'success': False, 'message': str(err)})
    
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
    except Exception as err:
        return jsonify({'success': False, 'message': str(err)})
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
    
    except Exception as err:
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
    
    except Exception as err:
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
    
    except Exception as err:
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
    
    except Exception as err:
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
    except Exception as err:
        return jsonify({'success': False, 'message': str(err)})
    finally:
        cursor.close()
        conn.close()



@admin_bp.route('/admin/event/<int:event_id>', methods=['GET'])
@login_required(['Admin','Manager'])
def event_dasnbored(event_id):
    
    # Get database connection
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})
    
    cursor = conn.cursor()
    try:
        
        # Update user in database
        cursor.execute("""
            
            SELECT JSON_OBJECT(
                'expoName',           me.name,
                'location',           me.location,
                'event_start_date',     DATE_FORMAT(me.start_date, '%d %M %Y'),
                'event_end_date',       DATE_FORMAT(me.end_date, '%d %M %Y'),
                'totalDaysScheduled', DATEDIFF(me.end_date, me.start_date) + 1,
                'status',             CASE 
                                        WHEN CURDATE() BETWEEN me.start_date AND me.end_date THEN 'Ongoing'
                                        WHEN CURDATE() > me.end_date THEN 'Completed'
                                        ELSE 'Upcoming'
                                    END,
                'targetRevenue',      0,
                'totals', JSON_OBJECT(
                    'revenue',    COALESCE(SUM(inv.grand_total), 0),
                    'received_money',    COALESCE(SUM(inv.paid_amount), 0),
                    'cash',       COALESCE(SUM(CASE WHEN inv.payment_mode = 'cash'   THEN inv.paid_amount ELSE 0 END), 0),
                    'online',     COALESCE(SUM(CASE WHEN inv.payment_mode = 'online' THEN inv.paid_amount ELSE 0 END), 0),
                    'salesCount', COUNT(inv.id)
                ),
                'dailyBreakdown', (
                    SELECT JSON_ARRAYAGG(
                        JSON_OBJECT(
                            'dayNumber',   DATEDIFF(all_days.event_day, me2.start_date) + 1,
                            'label',       CONCAT(DATEDIFF(all_days.event_day, me2.start_date) + 1, ' Day'),
                            'date',        DATE_FORMAT(all_days.event_day, '%M %d'),
                            'revenue',     COALESCE(daily.day_revenue, 0),
                            'cash',        COALESCE(daily.day_cash, 0),
                            'online',      COALESCE(daily.day_online, 0),
                            'salesCount',  COALESCE(daily.day_count, 0),
                            -- 👇 true if the day is in the past OR has actual sales data
                            'isCompleted', IF(all_days.event_day <= CURDATE(), TRUE, FALSE)
                        )
                        ORDER BY all_days.event_day
                    )
                    FROM (
                        -- Generate every date in the event window
                        SELECT DATE(me2.start_date + INTERVAL seq.n DAY) AS event_day
                        FROM market_events me2
                        JOIN (
                            SELECT 0 AS n UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3
                            UNION ALL SELECT 4 UNION ALL SELECT 5 UNION ALL SELECT 6 UNION ALL SELECT 7
                            UNION ALL SELECT 8 UNION ALL SELECT 9 UNION ALL SELECT 10 UNION ALL SELECT 11
                            UNION ALL SELECT 12 UNION ALL SELECT 13 UNION ALL SELECT 14 UNION ALL SELECT 15
                            UNION ALL SELECT 16 UNION ALL SELECT 17 UNION ALL SELECT 18 UNION ALL SELECT 19
                            UNION ALL SELECT 20 UNION ALL SELECT 21 UNION ALL SELECT 22 UNION ALL SELECT 23
                            UNION ALL SELECT 24 UNION ALL SELECT 25 UNION ALL SELECT 26 UNION ALL SELECT 27
                            UNION ALL SELECT 28 UNION ALL SELECT 29 UNION ALL SELECT 30
                        ) AS seq
                        WHERE me2.id = 6
                        AND DATE(me2.start_date + INTERVAL seq.n DAY) <= me2.end_date
                    ) AS all_days

                    JOIN market_events me2 ON me2.id = 6

                    LEFT JOIN (
                        SELECT
                            DATE(lot2.sales_date_time)                                                    AS invoice_date,
                            SUM(inv2.grand_total)                                                         AS day_revenue,
                            SUM(CASE WHEN inv2.payment_mode = 'cash'   THEN inv2.paid_amount ELSE 0 END) AS day_cash,
                            SUM(CASE WHEN inv2.payment_mode = 'online' THEN inv2.paid_amount ELSE 0 END) AS day_online,
                            COUNT(inv2.id)                                                                AS day_count
                        FROM invoices inv2
                        JOIN live_order_track lot2 ON lot2.invoice_id = inv2.id
                        WHERE lot2.sales_proceed_for_packing = 1
                        AND lot2.cancel_order_status      = 0
                        AND inv2.cancel_order_status      = 0
                        AND inv2.event_id                 = 6
                        AND DATE(lot2.sales_date_time) BETWEEN (SELECT start_date FROM market_events WHERE id = 6)
                                                            AND (SELECT end_date   FROM market_events WHERE id = 6)
                        GROUP BY DATE(lot2.sales_date_time)
                    ) AS daily ON daily.invoice_date = all_days.event_day
                )
            ) AS result

            FROM market_events me
            LEFT JOIN invoices inv      ON inv.event_id = me.id
                                    AND inv.cancel_order_status = 0
            LEFT JOIN live_order_track lot ON lot.invoice_id = inv.id
                                        AND lot.sales_proceed_for_packing = 1
                                        AND lot.cancel_order_status = 0
            WHERE me.id = %s
            AND me.active = 1;


        """, (event_id,))
        
        data = cursor.fetchall()
        # return jsonify(json.loads(data[0][0]))
    
        return render_template('dashboards/admin/expo.html', data=json.loads(data[0][0]))

    except Exception as err:
        return jsonify({'success': False, 'message': str(err)})
    finally:
        cursor.close()
        conn.close()