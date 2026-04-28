sp_label: BEGIN

    DECLARE v_inv_id             INT DEFAULT NULL;
    DECLARE v_lot_id             INT DEFAULT NULL;
    DECLARE v_delivery_mode      VARCHAR(50) DEFAULT NULL;
    DECLARE v_payment_mode       VARCHAR(50) DEFAULT NULL;
    DECLARE v_left_to_paid       INT DEFAULT 0;
    DECLARE v_left_to_paid_mode  VARCHAR(50) DEFAULT NULL;
    DECLARE v_step               VARCHAR(100) DEFAULT 'init';  -- 👈 tracks current step

    DECLARE v_errno              INT DEFAULT 0;
    DECLARE v_errmsg             VARCHAR(255) DEFAULT '';

    -- Capture actual error code + message
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1
            v_errno  = MYSQL_ERRNO,
            v_errmsg = MESSAGE_TEXT;
        ROLLBACK;
        SET p_success = 0;
        SET p_message = CONCAT('Error at step [', v_step, '] — ', v_errno, ': ', v_errmsg);
    END;

    START TRANSACTION;

    SET v_step = 'fetch_invoice';
    SELECT
        i.id,
        lot.id,
        i.delivery_mode,
        i.payment_mode,
        CAST(i.left_to_paid AS SIGNED)
    INTO
        v_inv_id,
        v_lot_id,
        v_delivery_mode,
        v_payment_mode,
        v_left_to_paid
    FROM live_order_track AS lot
    JOIN invoices AS i ON i.id = lot.invoice_id
    WHERE i.invoice_number COLLATE utf8mb4_unicode_ci = p_invoice_number
    LIMIT 1
    FOR UPDATE;

    SET v_step = 'validate_invoice';
    IF v_lot_id IS NULL THEN
        ROLLBACK;
        SET p_success = 0;
        SET p_message = 'Invoice not found';
        LEAVE sp_label;
    END IF;

    SET v_step = 'check_stock';
    IF EXISTS (
        SELECT 1
        FROM invoice_items ii
        JOIN products p ON p.id = ii.product_id
        WHERE ii.invoice_id = v_inv_id
          AND p.quantity < ii.quantity
    ) THEN
        ROLLBACK;
        SET p_success = 0;
        SET p_message = 'Insufficient stock for one or more products';
        LEAVE sp_label;
    END IF;

    SET v_step = 'update_live_order_track';
    IF v_delivery_mode IN ('transport', 'post') THEN
        UPDATE live_order_track
        SET sales_proceed_for_packing = 1,
            sales_date_time           = NOW()
        WHERE id = v_lot_id;
    ELSE
        SET v_left_to_paid_mode = IF(v_left_to_paid = 0, v_payment_mode, 'not_paid');
        UPDATE live_order_track
        SET
            sales_proceed_for_packing     = 1,
            sales_date_time               = NOW(),
            packing_proceed_for_transport = 1,
            packing_date_time             = NOW(),
            packing_proceed_by            = p_user_id,
            transport_proceed_for_builty  = 1,
            transport_date_time           = NOW(),
            transport_proceed_by          = p_user_id,
            builty_proceed_by             = p_user_id,
            builty_received               = 1,
            builty_date_time              = NOW(),
            verify_by_manager             = 1,
            verify_by_manager_id          = p_user_id,
            verify_manager_date_time      = NOW(),
            left_to_paid_mode             = v_left_to_paid_mode
        WHERE id = v_lot_id;
    END IF;

    SET v_step = 'deduct_stock';
    UPDATE products p
    JOIN   invoice_items ii ON ii.product_id = p.id
    SET    p.quantity = p.quantity - ii.quantity
    WHERE  ii.invoice_id = v_inv_id;

    SET v_step = 'commit';
    COMMIT;
    SET p_success = 1;
    SET p_message = 'Order successfully shipped';

END sp_label