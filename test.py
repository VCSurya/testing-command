sp_main: BEGIN

    DECLARE v_count        INT           DEFAULT 0;
    DECLARE v_left_to_pay  DECIMAL(12,2) DEFAULT 0;
    DECLARE v_inv_num      VARCHAR(20)   DEFAULT '';
    DECLARE v_idx          INT           DEFAULT 0;
    DECLARE v_total        INT           DEFAULT 0;
    DECLARE v_prod_id      BIGINT        DEFAULT 0;
    DECLARE v_qty          INT           DEFAULT 0;
    DECLARE v_price        DECIMAL(12,4) DEFAULT 0;
    DECLARE v_gst          DECIMAL(12,4) DEFAULT 0;
    DECLARE v_tamount      DECIMAL(12,2) DEFAULT 0;
    DECLARE v_cname        VARCHAR(255)  DEFAULT '';
    DECLARE v_camount      INT           DEFAULT 0;
    DECLARE v_had_error    TINYINT       DEFAULT 0;
    DECLARE v_err_msg      VARCHAR(500)  DEFAULT '';

    DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
    BEGIN
        SET v_had_error = 1;
        GET DIAGNOSTICS CONDITION 1 v_err_msg = MESSAGE_TEXT;
    END;

    -- Initialize OUT params
    SET p_invoice_id     = -1;
    SET p_invoice_number = '';
    SET p_error          = '';

    -- ── 1. Duplicate bill check ──────────────────────────────────────────
    SELECT COUNT(*) INTO v_count FROM invoices WHERE id = p_bill_id;

    IF v_had_error THEN
        SET p_error = CONCAT('BILL_CHECK_ERR: ', v_err_msg);
        SELECT p_invoice_id AS invoice_id, p_invoice_number AS invoice_number, p_error AS error;
        LEAVE sp_main;
    END IF;

    IF v_count > 0 THEN
        SET p_error = 'DUPLICATE_BILL';
        SELECT p_invoice_id AS invoice_id, p_invoice_number AS invoice_number, p_error AS error;
        LEAVE sp_main;
    END IF;

    -- ── 2. Stock check ───────────────────────────────────────────────────
    SET v_total = JSON_LENGTH(p_products_json);
    SET v_idx   = 0;

    WHILE v_idx < v_total DO
        SET v_prod_id = CAST(JSON_UNQUOTE(JSON_EXTRACT(p_products_json, CONCAT('$[', v_idx, '][0]'))) AS UNSIGNED);
        SET v_qty     = CAST(JSON_UNQUOTE(JSON_EXTRACT(p_products_json, CONCAT('$[', v_idx, '][1]'))) AS UNSIGNED);

        SET v_count = 0;
        SELECT COUNT(*) INTO v_count
        FROM products
        WHERE id = v_prod_id AND quantity >= v_qty;

        IF v_had_error THEN
            SET p_error = CONCAT('STOCK_CHECK_ERR: ', v_err_msg);
            SELECT p_invoice_id AS invoice_id, p_invoice_number AS invoice_number, p_error AS error;
            LEAVE sp_main;
        END IF;

        IF v_count = 0 THEN
            SET p_error = CONCAT('OUT_OF_STOCK: product_id=', v_prod_id);
            SELECT p_invoice_id AS invoice_id, p_invoice_number AS invoice_number, p_error AS error;
            LEAVE sp_main;
        END IF;

        SET v_idx = v_idx + 1;
    END WHILE;

    -- ── 3. Generate unique invoice number ────────────────────────────────
    SET v_count = 1;
    WHILE v_count > 0 DO
        SET v_inv_num   = CONVERT(UPPER(SUBSTRING(MD5(UUID()), 1, 10)) USING utf8mb4);
        SET v_count     = 0;
        SET v_had_error = 0;

        SELECT COUNT(*) INTO v_count
        FROM invoices
        WHERE invoice_number = v_inv_num COLLATE utf8mb4_general_ci;

        IF v_had_error THEN
            SET p_error = CONCAT('INV_NUM_ERR: ', v_err_msg);
            SELECT p_invoice_id AS invoice_id, p_invoice_number AS invoice_number, p_error AS error;
            LEAVE sp_main;
        END IF;
    END WHILE;

    -- ── 4. START TRANSACTION ─────────────────────────────────────────────
    START TRANSACTION;

    SET v_left_to_pay = p_grand_total - p_paid_amount;
    SET v_had_error   = 0;

    -- ── 5. Insert invoice ────────────────────────────────────────────────
    INSERT INTO invoices (
        id, customer_id, delivery_mode, grand_total, gst_included,
        invoice_created_by_user_id, left_to_paid, paid_amount,
        payment_mode, payment_note, sales_note, transport_id,
        invoice_number, event_id, completed, created_at
    ) VALUES (
        p_bill_id, p_customer_id, p_delivery_mode, p_grand_total, p_gst_included,
        p_created_by, v_left_to_pay, p_paid_amount,
        p_payment_mode, p_payment_note, p_sales_note, p_transport_id,
        v_inv_num, p_event_id, p_completed, NOW()
    );

    IF v_had_error THEN
        ROLLBACK;
        SET p_error = CONCAT('INSERT_INVOICE_ERR: ', v_err_msg);
        SELECT p_invoice_id AS invoice_id, p_invoice_number AS invoice_number, p_error AS error;
        LEAVE sp_main;
    END IF;

    SET p_invoice_id     = p_bill_id;
    SET p_invoice_number = v_inv_num;

    -- ── 6. Insert invoice items + decrement stock ────────────────────────
    SET v_idx = 0;
    WHILE v_idx < v_total DO
        SET v_had_error = 0;

        SET v_prod_id = CAST(JSON_UNQUOTE(JSON_EXTRACT(p_products_json, CONCAT('$[', v_idx, '][0]'))) AS UNSIGNED);
        SET v_qty     = CAST(JSON_UNQUOTE(JSON_EXTRACT(p_products_json, CONCAT('$[', v_idx, '][1]'))) AS UNSIGNED);
        SET v_price   = CAST(JSON_UNQUOTE(JSON_EXTRACT(p_products_json, CONCAT('$[', v_idx, '][2]'))) AS DECIMAL(12,4));
        SET v_gst     = CAST(JSON_UNQUOTE(JSON_EXTRACT(p_products_json, CONCAT('$[', v_idx, '][3]'))) AS DECIMAL(12,4));
        SET v_tamount = CAST(JSON_UNQUOTE(JSON_EXTRACT(p_products_json, CONCAT('$[', v_idx, '][4]'))) AS DECIMAL(12,2));

        INSERT INTO invoice_items (
            invoice_id, product_id, quantity, price,
            total_amount, gst_tax_amount, created_at
        ) VALUES (
            p_invoice_id, v_prod_id, v_qty, v_price,
            v_tamount, v_gst, NOW()
        );

        IF v_had_error THEN
            ROLLBACK;
            SET p_invoice_id = -1;
            SET p_error      = CONCAT('INSERT_ITEM_ERR: ', v_err_msg);
            SELECT p_invoice_id AS invoice_id, p_invoice_number AS invoice_number, p_error AS error;
            LEAVE sp_main;
        END IF;

        UPDATE products SET quantity = quantity - v_qty WHERE id = v_prod_id;

        IF v_had_error THEN
            ROLLBACK;
            SET p_invoice_id = -1;
            SET p_error      = CONCAT('STOCK_UPDATE_ERR: ', v_err_msg);
            SELECT p_invoice_id AS invoice_id, p_invoice_number AS invoice_number, p_error AS error;
            LEAVE sp_main;
        END IF;

        SET v_idx = v_idx + 1;
    END WHILE;

    -- ── 7. Insert additional charges ─────────────────────────────────────
    SET v_total = JSON_LENGTH(p_charges_json);
    SET v_idx   = 0;

    WHILE v_idx < v_total DO
        SET v_had_error = 0;
        SET v_cname   = JSON_UNQUOTE(JSON_EXTRACT(p_charges_json, CONCAT('$[', v_idx, '].name')));
        SET v_camount = CAST(JSON_UNQUOTE(JSON_EXTRACT(p_charges_json, CONCAT('$[', v_idx, '].amount'))) AS SIGNED);

        INSERT INTO additional_charges (invoice_id, charge_name, amount, created_at)
        VALUES (p_invoice_id, v_cname, v_camount, NOW());

        IF v_had_error THEN
            ROLLBACK;
            SET p_invoice_id = -1;
            SET p_error      = CONCAT('INSERT_CHARGE_ERR: ', v_err_msg);
            SELECT p_invoice_id AS invoice_id, p_invoice_number AS invoice_number, p_error AS error;
            LEAVE sp_main;
        END IF;

        SET v_idx = v_idx + 1;
    END WHILE;

    -- ── 8. Live order track ──────────────────────────────────────────────
    IF p_completed = 0 THEN
        SET v_had_error = 0;

        INSERT IGNORE INTO live_order_track (invoice_id) VALUES (p_invoice_id);

        IF v_had_error THEN
            ROLLBACK;
            SET p_invoice_id = -1;
            SET p_error      = CONCAT('LIVE_TRACK_ERR: ', v_err_msg);
            SELECT p_invoice_id AS invoice_id, p_invoice_number AS invoice_number, p_error AS error;
            LEAVE sp_main;
        END IF;
    END IF;

    COMMIT;

    -- ── SUCCESS result set ───────────────────────────────────────────────
    SELECT p_invoice_id AS invoice_id, p_invoice_number AS invoice_number, p_error AS error;

END sp_main