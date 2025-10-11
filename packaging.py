from flask import Blueprint, make_response, render_template, jsonify, request, session
from sympy import im
from utils import get_db_connection, login_required, encrypt_password,decrypt_password
import mysql.connector
from datetime import datetime
import pytz

ist = pytz.timezone('Asia/Kolkata')
now_ist = datetime.now(ist)
formatted_time = now_ist.strftime("%d-%m-%Y %H:%M")

# Create a Blueprint for packaging routes
packaging_bp = Blueprint('packaging', __name__)


@packaging_bp.route('/dashboard')
@login_required('Packaging')
def packaging_dashboard():
    return render_template('dashboards/packaging/packaging.html')

class PackagingModel:
    def __init__(self):
        self.conn = get_db_connection()
        if not self.conn:
            raise Exception("Database connection failed")
        self.cursor = self.conn.cursor(dictionary=True)
    
    def get_dasebored_data(self,user_id):
        query = f"""
            
            SELECT 
                -- Total Draft Packing Order
                COUNT(CASE WHEN sales_proceed_for_packing = 1 
                        AND cancel_order_status = 0 
                        AND packing_proceed_for_transport = 0 
                        AND payment_confirm_status = 1 
                    THEN 1 END) AS total_draft_packing_order,

                -- Total Proceed Packing Order From User
                COUNT(CASE WHEN sales_proceed_for_packing = 1 
                        AND payment_confirm_status = 1 
                        AND cancel_order_status = 0 
                        AND packing_proceed_for_transport = 1 
                        AND packing_proceed_by = {user_id} 
                    THEN 1 END) AS total_proceed_packing_order_from_user,

                -- Replaced Canceled orders from cancelled_orders table
                COALESCE(co.total_canceled_orders, 0) AS total_canceled_orders,
                COALESCE(co.pending_canceled_orders, 0) AS pending_canceled_orders,
                COALESCE(co.confirmed_canceled_orders, 0) AS confirmed_canceled_orders,

                -- Total Order Which Is Packed But Not Transport
                COUNT(CASE WHEN sales_proceed_for_packing = 1 
                        AND payment_confirm_status = 1 
                        AND cancel_order_status = 0 
                        AND packing_proceed_for_transport = 1 
                        AND packing_proceed_by = {user_id}
                        AND transport_proceed_for_builty = 0 
                    THEN 1 END) AS total_packed_but_not_transport,

                -- Total Today Order Packed By User
                COUNT(CASE WHEN sales_proceed_for_packing = 1 
                        AND payment_confirm_status = 1 
                        AND cancel_order_status = 0 
                        AND packing_proceed_for_transport = 1 
                        AND packing_proceed_by = {user_id}
                        AND DATE(packing_date_time) = CURRENT_DATE 
                    THEN 1 END) AS total_today_order_packed_by_user

            FROM live_order_track

            LEFT JOIN (
                SELECT
                    cancelled_by,
                    COUNT(*) AS total_canceled_orders,
                    COUNT(CASE WHEN confirm_by_saler = 0 THEN 1 END) AS pending_canceled_orders,
                    COUNT(CASE WHEN confirm_by_saler = 1 THEN 1 END) AS confirmed_canceled_orders
                FROM cancelled_orders
                WHERE cancelled_by = {user_id}
                GROUP BY cancelled_by
            ) co ON co.cancelled_by = {user_id};

        """

        
        self.cursor.execute(query,)
        result = self.cursor.fetchone()
        self.conn.close()

        return result



    def merge_orders_products(self,data):

        merged = {}

        for item in data:

            # change created_at date formate 
            item['created_at'] = item['created_at'].strftime("%d/%m/%Y %I:%M %p") 

            # passed tracking status with date            
            trackingStatus = 0
            trackingDates = []

            if item['sales_proceed_for_packing']:

                if item['sales_date_time']:
                    trackingDates.append(item['sales_date_time'].strftime("%d/%m/%Y %I:%M %p"))
                else:
                    trackingDates.append('')
                trackingStatus = 1                
            
                if item['packing_proceed_for_transport']:
                    
                    if item['packing_proceed_for_transport']:
                        trackingDates.append(item['packing_date_time'].strftime("%d/%m/%Y %I:%M %p"))
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
            
                            if item['verify_by_manager']:
                                
                                if item['verify_by_manager']:
                                    trackingDates.append(item['verify_manager_date_time'].strftime("%d/%m/%Y %I:%M %p"))
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

    def fetch_packing_orders(self):
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

                        lot.verify_manager_date_time

                    FROM invoices inv

                    LEFT JOIN buddy b ON inv.customer_id = b.id

                    LEFT JOIN users u ON inv.invoice_created_by_user_id = u.id

                    LEFT JOIN invoice_items ii ON inv.id = ii.invoice_id

                    LEFT JOIN products p ON ii.product_id = p.id

                    LEFT JOIN live_order_track lot ON inv.id = lot.invoice_id

                        AND lot.cancel_order_status = 0

                        AND lot.sales_proceed_for_packing = 1

                    WHERE lot.packing_proceed_for_transport = 0

                    AND inv.completed = 0

                    AND (inv.delivery_mode = "transport" OR inv.delivery_mode = "post")

                    AND lot.payment_confirm_status = 1

                    ORDER BY inv.created_at DESC;                
                    
                """

        
        self.cursor.execute(query)
        all_order_data = self.cursor.fetchall()
        
        if not all_order_data:
            return []

    
        # Merge products into orders
        merged_orders = self.merge_orders_products(all_order_data)

        return merged_orders

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
                    
                        inv.transport_company_name,
                    
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
                        lot.packing_note


                    FROM invoices inv

                    LEFT JOIN buddy b ON inv.customer_id = b.id

                    LEFT JOIN users u ON inv.invoice_created_by_user_id = u.id

                    LEFT JOIN invoice_items ii ON inv.id = ii.invoice_id

                    LEFT JOIN products p ON ii.product_id = p.id

                    LEFT JOIN live_order_track lot ON inv.id = lot.invoice_id

                        AND lot.cancel_order_status = 0

                        AND lot.sales_proceed_for_packing = 1

                        AND lot.packing_proceed_for_transport = 1

                        AND lot.transport_proceed_for_builty = 0 

                    WHERE lot.packing_proceed_by = %s
                    
                    AND inv.completed = 0

                    AND (inv.delivery_mode = "transport" OR inv.delivery_mode = "post")

                    AND lot.payment_confirm_status = 1

                    ORDER BY inv.created_at DESC;                
                    
                """

        
        self.cursor.execute(query,(session.get('user_id'),))
        all_order_data = self.cursor.fetchall()
        
        if not all_order_data:
            return []

    
        # Merge products into orders
        merged_orders = self.merge_orders_products(all_order_data)

        return merged_orders

    def cancel_order(self,data):
        try:
            update_query = """

            UPDATE live_order_track
            SET cancel_order_status = 1
            WHERE id = %s;
            """
            self.cursor.execute(update_query, (data.get('track_order_id'),))
            self.conn.commit()  # commit on connection, not cursor
            
            update_query = """

            UPDATE invoices
            SET cancel_order_status = 1
            WHERE invoices.id = (SELECT invoice_id from live_order_track WHERE id = %s );
            """
            self.cursor.execute(update_query, (data.get('track_order_id'),))
            self.conn.commit()  # commit on connection, not cursor
            

            insert_query = """
                
                INSERT INTO cancelled_orders (
                    invoice_id,cancelled_by, reason,live_order_track_id 
                ) VALUES (%s, %s, %s,%s)
            """

            self.cursor.execute(insert_query, (data.get('invoice_id'),session.get('user_id'),data.get('reason'),data.get('track_order_id'),))
            self.conn.commit()  # commit on connection, not cursor
            
            return {"success": True, "message": f"Order successfully Cancel"}
            
        except Exception as e:
            self.conn.rollback()  # rollback on connection, not cursor
            return {"success": False, "message": f"Somthing went wrong to cancel order"}

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

    def save_images(self, invoice_id, images):
        try:
            # Convert images to a format suitable for storage, e.g., base64 or binary
            # Here we assume images is a list of base64 strings
            for image in images:
                insert_query = """
                    INSERT INTO packing_images (invoice_id, image_base64, uploaded_by)
                    VALUES (%s, %s, %s)
                """
                self.cursor.execute(insert_query, (invoice_id[10:], image, session.get('user_id')))

            self.conn.commit()  # commit on connection, not cursor
            return {"success": True}
        
        except Exception as e:
            self.conn.rollback()

    def get_images(self, invoice_id):
        try:
            query = """
            SELECT image_id, image_base64
            FROM packing_images
            WHERE invoice_id = %s
            """
            self.cursor.execute(query, (invoice_id[10:],))
            images = self.cursor.fetchall()

            return images  # Extract base64 strings

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
        print(orders)
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

@packaging_bp.route('/packing/cancel_order', methods=['POST'])
@login_required('Packaging')
def cancel_order():
    try:
        data = request.get_json()
        track_order_id = data.get('track_order_id') #reason
        if not track_order_id or not str(track_order_id).isdigit() or not data.get('invoice_id'):
            return jsonify({"success": False, "message": "Invalid Order!"}), 400

        for_cancel_order = PackagingModel()
        response = for_cancel_order.cancel_order(data)

        if response.get('success'):
            return jsonify({"success": True, "message": "Order Cancelled Successfully"}), 200
        
        for_cancel_order.close()
        return {"success": False, "message": f"Somthing went wrong!"},500

    except Exception as e:
        return jsonify({"success": False, "message": f"From Server Side: {e}"}), 500

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


@packaging_bp.route('/packaging/saveimages', methods=['POST'])
@login_required('Packaging')
def save_images():
    try:
        data = request.get_json()
        invoice_id = data.get('invoiceId')
        images = data.get('images')

        if not invoice_id or not images:
            return jsonify({"success": False, "message": "Invalid data!"}), 400

        packaging_model = PackagingModel()
        
        response = packaging_model.save_images(invoice_id, images)

        if response.get('success'):
            return jsonify({"success": True, "message": "Images saved successfully!"}), 200

        return jsonify({"success": False, "message": "Failed to save images!"}), 500

    except Exception as e:
        return jsonify({"success": False, "message": f"From Server Side: {e}"}), 500


@packaging_bp.route('/packaging/images/<string:invoice_id>', methods=['GET'])
@login_required('Packaging')
def get_images(invoice_id):
    try:
        packaging_model = PackagingModel()
        images = packaging_model.get_images(invoice_id)

        if len(images) > 0:
            return jsonify({"success": True, "images": images}), 200
        
        elif len(images) == 0:
            return jsonify({"success": False, "message": "No images found!"}), 200
        
        else:
            return jsonify({"success": False, "message": "Unexpected error occurred!"}), 500

    except Exception as e:
        return jsonify({"success": False, "message": f"From Server Side: {e}"}), 500


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

@packaging_bp.route('/packaging/images_page/<string:invoice_id>', methods=['GET'])
@login_required('Packaging')
def show_images_page(invoice_id):
    packaging_model = PackagingModel()
    images = packaging_model.get_images(invoice_id)
    return render_template('dashboards/packaging/images_page.html', images=images, invoice_id=invoice_id)
