from flask import Blueprint, render_template, jsonify, request, send_from_directory, session
from packaging import UPLOAD_FOLDER
from utils import get_db_connection, login_required, get_invoice_id
from datetime import datetime
import pytz

ist = pytz.timezone('Asia/Kolkata')
now_ist = datetime.now(ist)
formatted_time = now_ist.strftime("%d-%m-%Y %H:%M")

# Create a Blueprint for packaging routes
transport_bp = Blueprint('transport', __name__)

@transport_bp.route('/dashboard')
@login_required('Transport')
def transport_dashboard():
    return render_template('dashboards/transport/transport.html')

class TransportModel:
    def __init__(self):
        self.conn = get_db_connection()
        if not self.conn:
            raise Exception("Database connection failed")
        self.cursor = self.conn.cursor(dictionary=True)
    
    def get_dasebored_data(self,user_id):
        query = f"""
            
            SELECT 
                -- Total Draft Transport Order
                COUNT(CASE WHEN sales_proceed_for_packing = 1 
               		AND cancel_order_status = 0 
               		AND packing_proceed_for_transport = 1 
               		AND payment_confirm_status = 1
      		   		AND transport_proceed_for_builty = 0		
          		THEN 1 END) AS total_draft_transport_order,

                -- Total Proceed Transport Order From User
                COUNT(CASE WHEN sales_proceed_for_packing = 1 
                        AND payment_confirm_status = 1 
                        AND cancel_order_status = 0 
                        AND packing_proceed_for_transport = 1
      					AND transport_proceed_for_builty = 1
                        AND transport_proceed_by = {user_id}
                THEN 1 END) AS total_proceed_transport_order_from_user,


                -- Replaced Canceled orders from cancelled_orders table
                COALESCE(co.total_canceled_orders, 0) AS total_canceled_orders,
                COALESCE(co.pending_canceled_orders, 0) AS pending_canceled_orders,
                COALESCE(co.confirmed_canceled_orders, 0) AS confirmed_canceled_orders,

                -- Total Order Which Is Transport But Builty Not Recived 
                COUNT(CASE WHEN sales_proceed_for_packing = 1 
                        AND payment_confirm_status = 1 
                        AND cancel_order_status = 0 
                        AND packing_proceed_for_transport = 1 
                        AND transport_proceed_for_builty = 1 
      				    AND builty_received = 0 
      					AND transport_proceed_by = {user_id}
                THEN 1 END) AS total_transport_but_builty_not_recived,

                -- Total Today Order Transport By User
                COUNT(CASE WHEN sales_proceed_for_packing = 1 
                        AND payment_confirm_status = 1 
                        AND cancel_order_status = 0 
      					AND sales_proceed_for_packing = 1
                        AND packing_proceed_for_transport = 1 
      					AND transport_proceed_for_builty = 1
      					AND transport_proceed_by = {user_id}
                        AND DATE(transport_date_time) = CURRENT_DATE 
                THEN 1 END) AS total_today_order_transport_by_user

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
            item['sales_date_time'] = item['sales_date_time'].strftime("%d/%m/%Y %I:%M %p")
            item['packing_date_time'] = item['packing_date_time'].strftime("%d/%m/%Y %I:%M %p")
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

    def fetch_transport_orders(self):
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

                        up.username AS pack_by,

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
                        lot.packing_note,

                        transport.pincode AS transport_pincode,
                        transport.name AS transport_name,
                        transport.city AS transport_city,
                        transport.days AS transport_days

                    FROM invoices inv

                    LEFT JOIN buddy b ON inv.customer_id = b.id
                    LEFT JOIN users u ON inv.invoice_created_by_user_id = u.id
                    LEFT JOIN live_order_track lot ON inv.id = lot.invoice_id
                        AND lot.cancel_order_status = 0
                        AND lot.sales_proceed_for_packing = 1
                        AND lot.packing_proceed_for_transport = 1
                    LEFT JOIN users up ON lot.packing_proceed_by = up.id
                    LEFT JOIN invoice_items ii ON inv.id = ii.invoice_id
                    LEFT JOIN products p ON ii.product_id = p.id
                    LEFT JOIN transport ON inv.transport_id = transport.id

                    WHERE lot.transport_proceed_for_builty = 0
                        AND inv.completed = 0
                        AND (inv.delivery_mode = 'transport' OR inv.delivery_mode = 'post')

                    ORDER BY inv.created_at DESC;
       
                """

        
        self.cursor.execute(query)
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
            WHERE invoice_id = %s;
            """
            self.cursor.execute(update_query, (data.get('invoice_id'),))
            self.conn.commit()  # commit on connection, not cursor
            
            update_query = """

            UPDATE invoices
            SET cancel_order_status = 1
            WHERE id = %s;
            """
            self.cursor.execute(update_query, (data.get('invoice_id'),))
            self.conn.commit()  # commit on connection, not cursor
            
            track_order_id_query = """
            SELECT id FROM live_order_track
            WHERE invoice_id = %s;
            """
            
            self.cursor.execute(track_order_id_query,(data.get('invoice_id'),))
            track_order_id = self.cursor.fetchone()['id']
            print(track_order_id)
            
            insert_query = """
                
                INSERT INTO cancelled_orders (
                    invoice_id,cancelled_by, reason,live_order_track_id 
                ) VALUES (%s, %s, %s,%s)
            """

            self.cursor.execute(insert_query, (data.get('invoice_id'),session.get('user_id'),data.get('reason'),track_order_id,))
            self.conn.commit()  # commit on connection, not cursor
            
            return {"success": True, "message": f"Order successfully Cancel"}
            
        except Exception as e:
            self.conn.rollback()  # rollback on connection, not cursor
            return {"success": False, "message": f"Somthing went wrong to cancel order"}

    def done_transportaion(self,data):
        try:
            update_query = """
            UPDATE live_order_track
            SET transport_proceed_for_builty = 1, transport_note = %s, transport_proceed_by = %s,transport_date_time = NOW()
            WHERE invoice_id = %s;
            """
            self.cursor.execute(update_query, (data.get('transportNote'),session.get('user_id'),data.get('invoice_id'),))
            self.conn.commit() 
            return {"success": True}
            
        except Exception as e:
            self.conn.rollback()  # rollback on connection, not cursor
            return {"success": False,"msg":e}

    def get_images(self, invoice_id):
        try:
            query = """
                SELECT image_url
                FROM packing_images
                WHERE invoice_id = %s
            """
            self.cursor.execute(query, (invoice_id,))
            rows = self.cursor.fetchall()
            return {"success": True, "images": rows}

        except Exception as e:
            return {"success": False, "message": f"From Server Side: {e}"}
    
    def close(self):
        self.cursor.close()
        self.conn.close() # type: ignore

@transport_bp.route('/transport/transport-dasebored-orders', methods=['GET'])
@login_required('Transport')
def transport_dasebored():
    try:
        my_trans = TransportModel()
        orders = my_trans.get_dasebored_data(session.get('user_id'))
        return jsonify(orders)

    except Exception as e:
        print(f"Error fetching orders: {e}")
        return jsonify({'error': 'Failed to fetch orders'}), 500

    finally:
        my_trans.close()  

@transport_bp.route('/transport/transport-orders-list', methods=['GET'])
@login_required('Transport')
def transport_my_pack_list():
    """
    Fetch the list of orders for the logged-in transport user.
    """    
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not logged in'}), 401
        
        my_pack = TransportModel()
        orders = my_pack.fetch_transport_orders()
        
        my_pack.close()

        if not orders:
            return jsonify([]), 200
        
        return jsonify(orders)

    except Exception as e:
        print(f"Error fetching orders: {e}")
        return jsonify({'error': 'Failed to fetch orders'}), 500

    finally:
        my_pack.close()

@transport_bp.route('/transport/cancel_order', methods=['POST'])
@login_required('Transport')
def cancel_order():
    try:
        data = request.get_json()
        invoiceNumber = data.get('invoiceNumber') #reason

        if not invoiceNumber:
            return jsonify({"success": False, "message": "Invalid Order!"}), 400

        result = get_invoice_id(invoiceNumber)
        if result['status']:
            data['invoice_id'] = result['invoice_id']

        for_cancel_order = TransportModel()
        response = for_cancel_order.cancel_order(data)

        if response.get('success'):
            return jsonify({"success": True, "message": "Order Cancelled Successfully"}), 200
        
        for_cancel_order.close()
        return {"success": False, "message": f"Somthing went wrong!"},500

    except Exception as e:
        return jsonify({"success": False, "message": f"From Server Side: {e}"}), 500

@transport_bp.route('/transport/ready-to-go-for-transport')
@login_required('Transport')
def send_for_transport():
    return render_template('dashboards/transport/ready_transport.html')

@transport_bp.route('/transport/done-transportation', methods=['POST'])
@login_required('Transport')
def done_transportaion():
    try:
        data = request.get_json()
        if not data.get('invoice_number'):
            return jsonify({"success": True, 'message': 'Missing Invoice Number!'}), 400

        result = get_invoice_id(data.get('invoice_number'))
        if result['status']:
            data['invoice_id'] = result['invoice_id']
        else:
            return jsonify({"success": True, 'message': 'Invoice not found'}), 404

        transport_obj = TransportModel()
        response = transport_obj.done_transportaion(data)

        if response.get('success'):
            return jsonify({"success": True, "message": "Order Transported Successfully"}),200

        transport_obj.close()
        return jsonify({"success": False, "message": f"Somthing went wrong!"}),500
    
    except Exception as e:
        return jsonify({"success": False, "message": f"From Server Side: {e}"}), 500

@transport_bp.route("/transport/uploads/packaging/<filename>")
@login_required('Transport')
def uploaded_image(filename):
    print(filename)
    return send_from_directory(UPLOAD_FOLDER, filename)

@transport_bp.route('/transport/images_page/<string:invoice_number>', methods=['GET'])
@login_required('Transport')
def show_images_page(invoice_number):
    transport_model = TransportModel()

    result = get_invoice_id(invoice_number)
    invoice_id = None
    
    if result['status']:
        invoice_id = result['invoice_id']
    else:
        return jsonify({'error': 'Invoice not found'}), 404

    images = transport_model.get_images(invoice_id)
    return render_template('dashboards/transport/images_page.html', images=images, invoice_id=invoice_number)