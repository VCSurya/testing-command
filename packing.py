from flask import Blueprint, json, render_template, jsonify, request, session
from sympy import im
from utils import get_db_connection, login_required, get_invoice_id,cancel_order
import mysql.connector
from datetime import datetime
import pytz
import os
from werkzeug.utils import secure_filename
import uuid
from flask import send_from_directory

ist = pytz.timezone('Asia/Kolkata')
now_ist = datetime.now(ist)
formatted_time = now_ist.strftime("%d-%m-%Y %H:%M")

UPLOAD_FOLDER = "uploads/packaging"

# Create a Blueprint for packaging routes
packaging_bp = Blueprint('packaging', __name__)


@packaging_bp.route('/dashboard')
@login_required('Packaging')
def packaging_dashboard():
    return render_template('dashboards/packaging/packaging.html')

class PackagingModel:

    UPLOAD_FOLDER = "uploads/packaging"

    def __init__(self):
        self.conn = get_db_connection()
        if not self.conn:
            raise Exception("Database connection failed")
        self.cursor = self.conn.cursor(dictionary=True)
    
    def get_dasebored_data(self,user_id):
        
        self.cursor.execute(f"CALL packing_dashbored_data({user_id})")
        result = self.cursor.fetchone()
        self.conn.close()

        return result
    
    def get_additional_charges(self,invoice_id):
        
        query = '''
            SELECT charge_name,amount FROM `additional_charges` WHERE invoice_id = %s;
        '''

        self.cursor.execute(query, (invoice_id,))
        additional_charges = self.cursor.fetchall()

        if not additional_charges:
            return []

        return additional_charges


    def fetch_packing_orders(self):
        query = f"""
                    SELECT
    
                        inv.id,                    
                        inv.invoice_number,
                        DATE_FORMAT(lot.sales_date_time, '%d/%m/%Y %h:%i %p') AS sales_date_time

                    FROM invoices inv
                    LEFT JOIN live_order_track lot ON inv.id = lot.invoice_id
                    WHERE 

                    lot.packing_proceed_for_transport = 0
                    AND lot.cancel_order_status = 0
                    AND lot.sales_proceed_for_packing = 1
                    AND inv.completed = 0
                    AND (inv.delivery_mode = "transport" OR inv.delivery_mode = "post")
                    AND lot.payment_confirm_status = 1
                    AND lot.pack_lock = 0
                    ORDER BY lot.sales_date_time DESC;                
                    
                """

        
        self.cursor.execute(query)
        all_order_data = self.cursor.fetchall()
        
        if not all_order_data:
            return []
        
        return all_order_data


    def fetch_my_packing_orders(self):
        query = f"""
                    SELECT
    
                        inv.id,                    
                        inv.invoice_number,
                        inv.customer_id,
                        inv.grand_total,
                        inv.payment_mode,
                        inv.paid_amount,
                        inv.left_to_paid,
                        inv.sales_note,
                        inv.invoice_created_by_user_id,
                        inv.payment_note,
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
                        lot.verify_by_manager_id,
                        lot.verify_manager_date_time,
                        transport.pincode AS transport_pincode,
                        transport.name AS transport_name,
                        transport.city AS transport_city

                    FROM invoices inv

                    LEFT JOIN buddy b ON inv.customer_id = b.id
                    LEFT JOIN users u ON inv.invoice_created_by_user_id = u.id
                    LEFT JOIN invoice_items ii ON inv.id = ii.invoice_id
                    LEFT JOIN products p ON ii.product_id = p.id
                    LEFT JOIN live_order_track lot ON inv.id = lot.invoice_id
                    LEFT JOIN transport ON inv.transport_id = transport.id

                    WHERE 

                    lot.packing_proceed_for_transport = 0
                    AND lot.cancel_order_status = 0
                    AND lot.sales_proceed_for_packing = 1
                    AND inv.completed = 0
                    AND (inv.delivery_mode = "transport" OR inv.delivery_mode = "post")
                    AND lot.payment_confirm_status = 1
                    AND lot.pack_lock = 0 
                    ORDER BY inv.created_at DESC;                 
                    
                """

        
        self.cursor.execute(query,)
        all_order_data = self.cursor.fetchall()
        
        if not all_order_data:
            return []
    
        # !!!!! Make the store procedure for this query and call here !!!!!   

        return None


    def strat_Dispatch(self,data):
        try:
            update_query = """
            UPDATE live_order_track
            SET packing_proceed_for_transport = 1, packing_note = %s, packing_proceed_by = %s,packing_date_time = NOW()
            WHERE id = %s;
            """
            self.cursor.execute(update_query, (data.get('packingNote'),session.get('user_id'),data.get('lot_id'),))
            self.conn.commit() 
            return {"success": True}
            
        except Exception as e:
            self.conn.rollback()  # rollback on connection, not cursor
            return {"success": False,"msg":e}
        
    def lock_packing(self,data):
        try:
            update_query = """
            UPDATE live_order_track
            SET pack_lock = 1, packing_proceed_by = %s,packing_date_time = NOW()
            WHERE id = %s;
            """
            self.cursor.execute(update_query, (session.get('user_id'),data.get('lot_id'),))
            self.conn.commit() 
            return {"success": True}
            
        except Exception as e:
            self.conn.rollback()  # rollback on connection, not cursor
            return {"success": False,"msg":e}

    def generate_unique_filename(self,invoice_id, original_filename):
        ext = os.path.splitext(original_filename)[1]  # .jpg, .png, etc.
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        random_id = uuid.uuid4().hex[:8]
        safe_name = secure_filename(f"inv_{invoice_id}_{timestamp}_{random_id}{ext}")
        return safe_name

    def save_images(self, invoice_id, files):
        try:
            os.makedirs(self.UPLOAD_FOLDER, exist_ok=True)

            for file in files:
                # Auto rename file to avoid collisions
                filename = self.generate_unique_filename(invoice_id, file.filename)
                save_path = os.path.join(self.UPLOAD_FOLDER, filename)

                file.save(save_path)

                db_path = f"/uploads/packaging/{filename}"

                insert_query = """
                    INSERT INTO packing_images (invoice_id, image_url, uploaded_by)
                    VALUES (%s, %s, %s)
                """
                self.cursor.execute(insert_query, (invoice_id, db_path, session.get('user_id')))

            self.conn.commit()
            return {"success": True}

        except Exception as e:
            self.conn.rollback()
            return {"success": False, "error": str(e)}

    def get_images(self, invoice_id):
        try:
            query = """
                SELECT image_id , image_url
                FROM packing_images
                WHERE invoice_id = %s
            """
            self.cursor.execute(query, (invoice_id,))
            rows = self.cursor.fetchall()
            return {"success": True, "images": rows}

        except Exception as e:
            return {"success": False, "message": f"From Server Side: {e}"}

    def delete_image(self, image_id):
        try:
            delete_query = """
            DELETE FROM packing_images
            WHERE image_id = %s
            """
            self.cursor.execute(delete_query, (image_id,))
            self.conn.commit()

            return {"success": True}

        except Exception as e:
            self.conn.rollback()
            return {"success": False, "message": f"From Server Side: {e}"}

    def close(self):
        self.cursor.close()
        self.conn.close() # type: ignore

@packaging_bp.route('/packaging/packing-dasebored-orders', methods=['GET'])
@login_required('Packaging')
def packaging_dasebored():
    try:
        my_pack = PackagingModel()
        orders = my_pack.get_dasebored_data(session.get('user_id'))
        return jsonify(orders)

    except Exception as e:
        print(f"Error fetching orders: {e}")
        return jsonify({'error': 'Failed to fetch orders'}), 500

    finally:
        my_pack.close()   

@packaging_bp.route('/packaging/packing-orders-list', methods=['GET'])
@login_required('Packaging')
def packaging_my_pack_list():
    """
    Fetch the list of orders for the logged-in packaging user.
    """    
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not logged in'}), 401
        
        my_pack = PackagingModel()
        orders = my_pack.fetch_packing_orders()
        
        my_pack.close()

        if not orders:
            return jsonify([]), 200
        
        return jsonify(orders)

    except Exception as e:
        print(f"Error fetching orders: {e}")
        return jsonify({'error': 'Failed to fetch orders'}), 500

    finally:
        my_pack.close()

@packaging_bp.route('/packing/invoice-detailes/<invoiceNumber>', methods=['GET'])
@login_required('Packaging')
def packing_invoice_details(invoiceNumber):
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = conn.cursor(dictionary=True)
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not logged in'}), 401
        
        cursor.callproc('get_packing_invoice_details', (invoiceNumber,))
            
        result = None
        for res in cursor.stored_results():
            result = res.fetchone()

        if not result:
            return None

        for field in ["products", "charges"]:
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

@packaging_bp.route('/packing/cancel_order', methods=['POST'])
@login_required('Packaging')
def packing_cancel_order():
    try:
        data = request.get_json()
        invoiceNumber = data.get('invoiceNumber')

        if not invoiceNumber:
            return jsonify({"success": False, "message": "Invalid Invoice Number"}), 400

        response = cancel_order(
            invoiceNumber, data.get('reason')
        )

        if response.get('success') == 1:
            return jsonify({"success": True, "message": "Order Cancelled Successfully"}), 200

        return {"success": False, "message": response.get('message')}, 500

    except Exception as e:
        return jsonify({"success": False, "message": "Internal server error"}), 500

@packaging_bp.route('/ready-to-go-for-transport')
@login_required('Packaging')
def send_for_transport():
    return render_template('dashboards/packaging/ready_packaging.html')

@packaging_bp.route('/packaging/start-shipment', methods=['POST'])
@login_required('Packaging')
def start_shipment():
    try:
        data = request.get_json()
        if not data.get('lot_id'):
            return jsonify({'error': 'Missing Some IMP Information!'}), 400

        dispatch_obj = PackagingModel()
        response = dispatch_obj.strat_Dispatch(data)

        if response.get('success'):
            return jsonify({"success": True, "message": "Order Dispatch Successfully"}),200

        dispatch_obj.close()
        return jsonify({"success": False, "message": f"Somthing went wrong!"}),500
    
    except Exception as e:
        return jsonify({"success": False, "message": f"From Server Side: {e}"}), 500

@packaging_bp.route('/packaging/lock-packing', methods=['POST'])
@login_required('Packaging')
def lock_packing_order():
    try:
        data = request.get_json()
        if not data.get('lot_id'):
            return jsonify({'error': 'Missing Some IMP Information!'}), 400

        locking_obj = PackagingModel()
        response = locking_obj.lock_packing(data)

        if response.get('success'):
            return jsonify({"success": True, "message": "Order Claimed Successfully"}),200

        locking_obj.close()
        return jsonify({"success": False, "message": f"Something went wrong!"}),500
    
    except Exception as e:
        locking_obj.close()
        return jsonify({"success": False, "message": f"From Server Side: {e}"}), 500


@packaging_bp.route('/my-packaging-orders')
@login_required('Packaging')
def my_pack_orders():
    return render_template('dashboards/packaging/my_pack_orders.html')

@packaging_bp.route('/packaging/my-packing-orders', methods=['GET'])
@login_required('Packaging')
def my_orders():
    """
    Fetch the list of orders for the logged-in packaging user.
    """    
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not logged in'}), 401
        
        my_pack = PackagingModel()
        orders = my_pack.fetch_my_packing_orders()
        
        my_pack.close()

        if not orders:
            return jsonify([]), 200
        
        return jsonify(orders)

    except Exception as e:
        print(f"Error fetching orders: {e}")
        return jsonify({'error': 'Failed to fetch orders'}), 500

    finally:
        my_pack.close()

@packaging_bp.route("/uploads/packaging/<filename>")
@login_required('Packaging')
def uploaded_image(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@packaging_bp.route('/packaging/saveimages', methods=['POST'])
@login_required('Packaging')
def save_images():
    try:
        invoice_number = request.form.get("invoiceId")
        files = request.files.getlist("images")

        if not invoice_number or not files:
            return jsonify({"success": False, "message": "Invalid data!"}), 400

        result = get_invoice_id(invoice_number)
        invoice_id = None
        if result['status']:
            invoice_id = result['invoice_id']
        else:
            return jsonify({'error': 'Invoice not found'}), 404

        packaging_model = PackagingModel()
        result = packaging_model.save_images(invoice_id, files)

        if result.get("success"):
            return jsonify({"success": True, "message": "Images saved successfully!"})

        return jsonify({"success": False, "message": "Failed!"}), 500

    except Exception as e:
        return jsonify({"success": False, "message": f"Server Error: {str(e)}"}), 500



@packaging_bp.route('/packaging/images/<string:invoice_id>', methods=['GET'])
@login_required('Packaging')
def get_images(invoice_id):
    try:
        packaging_model = PackagingModel()

        result = get_invoice_id(invoice_id)
        invoice_id = None
        if result['status']:
            invoice_id = result['invoice_id']
        else:
            return jsonify({"success": True,'message': 'Invoice not found'}), 404

        images = packaging_model.get_images(invoice_id)

        return jsonify({"success": True, "images": images['images']}), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@packaging_bp.route('/packaging/image/delete', methods=['POST'])
@login_required('Packaging')
def delete_image():
    try:
        data = request.get_json()
        image_id = data.get('imageId')

        if not image_id:
            return jsonify({"success": False, "message": "Invalid data!"}), 400

        if not int(image_id) or image_id == 0:
            return jsonify({"success": False, "message": "Invalid data!"}), 400

        packaging_model = PackagingModel()
        response = packaging_model.delete_image(image_id)

        if response.get('success'):
            return jsonify({"success": True, "message": "Image deleted successfully!"}), 200

        return jsonify({"success": False, "message": "Failed to delete image!"}), 500

    except Exception as e:
        return jsonify({"success": False, "message": f"From Server Side: {e}"}), 500

@packaging_bp.route('/packaging/images_page/<string:invoice_number>', methods=['GET'])
@login_required('Packaging')
def show_images_page(invoice_number):
    packaging_model = PackagingModel()

    result = get_invoice_id(invoice_number)
    invoice_id = None
    
    if result['status']:
        invoice_id = result['invoice_id']
    else:
        return jsonify({'error': 'Invoice not found'}), 404

    images = packaging_model.get_images(invoice_id)
    return render_template('dashboards/packaging/images_page.html', images=images, invoice_id=invoice_number,id=invoice_id)