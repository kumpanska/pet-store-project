CREATE TABLE IF NOT EXISTS product_category (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE IF NOT EXISTS supplier (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_name VARCHAR(150) NOT NULL,
    contact_person VARCHAR(100) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS customer (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    phone VARCHAR(20) NOT NULL UNIQUE,
    email VARCHAR(100) UNIQUE,
    discount_percent DECIMAL(5,2) NOT NULL DEFAULT 0 
        CHECK (discount_percent >= 0 AND discount_percent <= 100)
);

CREATE TABLE IF NOT EXISTS employee (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    position VARCHAR(50) NOT NULL,
    phone VARCHAR(20) NOT NULL
);

CREATE TABLE IF NOT EXISTS store (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    address VARCHAR(255),
    type VARCHAR(20) NOT NULL CHECK (type IN ('магазин', 'склад'))
);

CREATE TABLE IF NOT EXISTS role_in_store (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE CHECK (name IN ('директор', 'продавець-консультант', 'бухгалтер', 'менеджер')),
    description TEXT
);


CREATE TABLE IF NOT EXISTS product (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    barcode VARCHAR(20) NOT NULL UNIQUE,
    sale_price DECIMAL(10,2) NOT NULL CHECK (sale_price >= 0),
    purchase_price DECIMAL(10,2) NOT NULL CHECK (purchase_price >= 0),
    stock_quantity INT NOT NULL DEFAULT 0 CHECK (stock_quantity >= 0),
    category_id INT NOT NULL,
    supplier_id INT NOT NULL,
    CONSTRAINT fk_product_category FOREIGN KEY (category_id) REFERENCES product_category(id),
    CONSTRAINT fk_product_supplier FOREIGN KEY (supplier_id) REFERENCES supplier(id)
);

CREATE TABLE IF NOT EXISTS goods_receipt (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    date DATE NOT NULL,
    total DECIMAL(12,2) NOT NULL CHECK (total >= 0),
    supplier_id INT NOT NULL,
    CONSTRAINT fk_goods_receipt_supplier FOREIGN KEY (supplier_id) REFERENCES supplier(id)
);

CREATE TABLE IF NOT EXISTS goods_receipt_item (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    goods_receipt_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity INT NOT NULL CHECK (quantity > 0),
    purchase_price DECIMAL(10,2) NOT NULL CHECK (purchase_price >= 0),
    total DECIMAL(12,2) GENERATED ALWAYS AS (quantity * purchase_price) STORED,
    CONSTRAINT fk_gri_goods_receipt FOREIGN KEY (goods_receipt_id) REFERENCES goods_receipt(id) ON DELETE CASCADE,
    CONSTRAINT fk_gri_product FOREIGN KEY (product_id) REFERENCES product(id)
);

CREATE TABLE IF NOT EXISTS sale (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    date DATE NOT NULL,
    time TIME NOT NULL,
    payment_method VARCHAR(20) NOT NULL CHECK (payment_method IN ('готівка', 'картка', 'змішана')),
    total DECIMAL(12,2) NOT NULL CHECK (total >= 0),
    customer_id INT NULL,
    employee_id INT NOT NULL,
    CONSTRAINT fk_sale_customer FOREIGN KEY (customer_id) REFERENCES customer(id),
    CONSTRAINT fk_sale_employee FOREIGN KEY (employee_id) REFERENCES employee(id)
);

CREATE TABLE IF NOT EXISTS sale_item (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    receipt_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity INT NOT NULL CHECK (quantity > 0),
    sale_price DECIMAL(10,2) NOT NULL CHECK (sale_price >= 0),
    discount DECIMAL(5,2) NOT NULL DEFAULT 0 CHECK (discount >= 0 AND discount <= 100),
    CONSTRAINT fk_sale_item_receipt FOREIGN KEY (receipt_id) REFERENCES sale(id) ON DELETE CASCADE,
    CONSTRAINT fk_sale_item_product FOREIGN KEY (product_id) REFERENCES product(id)
);

CREATE TABLE IF NOT EXISTS return_product (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sale_item_id INT NOT NULL,
    employee_id INT NOT NULL,
    date DATE NOT NULL,
    quantity INT NOT NULL CHECK (quantity > 0),
    reason VARCHAR(255),
    CONSTRAINT fk_return_sale_item FOREIGN KEY (sale_item_id) REFERENCES sale_item(id),
    CONSTRAINT fk_return_employee FOREIGN KEY (employee_id) REFERENCES employee(id)
);

CREATE TABLE IF NOT EXISTS write_off_act (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    date DATE NOT NULL,
    reason VARCHAR(255) NOT NULL,
    employee_id INT NOT NULL,
    CONSTRAINT fk_write_off_act_employee FOREIGN KEY (employee_id) REFERENCES employee(id)
);

CREATE TABLE IF NOT EXISTS write_off_item (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    write_off_act_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity INT NOT NULL CHECK (quantity > 0),
    CONSTRAINT fk_woi_write_off_act FOREIGN KEY (write_off_act_id) REFERENCES write_off_act(id) ON DELETE CASCADE,
    CONSTRAINT fk_woi_product FOREIGN KEY (product_id) REFERENCES product(id)
);

CREATE TABLE IF NOT EXISTS stock_transfer (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    date DATE NOT NULL,
    from_store_id INT NOT NULL,
    to_store_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity INT NOT NULL CHECK (quantity > 0),
    employee_id INT NOT NULL,
    CONSTRAINT chk_different_stores CHECK (from_store_id <> to_store_id),
    CONSTRAINT fk_stock_transfer_from_store FOREIGN KEY (from_store_id) REFERENCES store(id),
    CONSTRAINT fk_stock_transfer_to_store FOREIGN KEY (to_store_id) REFERENCES store(id),
    CONSTRAINT fk_stock_transfer_product FOREIGN KEY (product_id) REFERENCES product(id),
    CONSTRAINT fk_stock_transfer_employee FOREIGN KEY (employee_id) REFERENCES employee(id)
);

CREATE TABLE IF NOT EXISTS inventory_check (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    date DATE NOT NULL,
    product_id INT NOT NULL,
    expected_quantity INT NOT NULL CHECK (expected_quantity >= 0),
    actual_quantity INT NOT NULL CHECK (actual_quantity >= 0),
    employee_id INT NOT NULL,
    CONSTRAINT fk_inventory_check_product FOREIGN KEY (product_id) REFERENCES product(id),
    CONSTRAINT fk_inventory_check_employee FOREIGN KEY (employee_id) REFERENCES employee(id)
);

CREATE TABLE IF NOT EXISTS price_change (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id INT NOT NULL,
    old_price DECIMAL(10,2) CHECK (old_price >= 0),
    new_price DECIMAL(10,2) NOT NULL CHECK (new_price >= 0),
    change_date DATE NOT NULL,
    employee_id INT NOT NULL,
    CONSTRAINT fk_price_change_product FOREIGN KEY (product_id) REFERENCES product(id),
    CONSTRAINT fk_price_change_employee FOREIGN KEY (employee_id) REFERENCES employee(id)
);

CREATE TABLE IF NOT EXISTS supplier_order (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    supplier_id INT NOT NULL,
    date DATE NOT NULL,
    status VARCHAR(20) NOT NULL CHECK (status IN ('нове', 'відправлене', 'отримане', 'скасоване')),
    total DECIMAL(12,2) CHECK (total >= 0),
    CONSTRAINT fk_supplier_order_supplier FOREIGN KEY (supplier_id) REFERENCES supplier(id)
);

CREATE TABLE IF NOT EXISTS supplier_order_item (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    supplier_order_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity INT NOT NULL CHECK (quantity > 0),
    price DECIMAL(10,2) CHECK (price >= 0),
    CONSTRAINT fk_soi_supplier_order FOREIGN KEY (supplier_order_id) REFERENCES supplier_order(id) ON DELETE CASCADE,
    CONSTRAINT fk_soi_product FOREIGN KEY (product_id) REFERENCES product(id)
);

CREATE TABLE IF NOT EXISTS supplier_payment (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    supplier_id INT NOT NULL,
    goods_receipt_id INT NOT NULL,
    date DATE NOT NULL,
    amount DECIMAL(12,2) NOT NULL CHECK (amount > 0),
    CONSTRAINT fk_supplier_payment_supplier FOREIGN KEY (supplier_id) REFERENCES supplier(id),
    CONSTRAINT fk_supplier_payment_goods_receipt FOREIGN KEY (goods_receipt_id) REFERENCES goods_receipt(id)
);

CREATE TABLE IF NOT EXISTS work_shift (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    employee_id INT NOT NULL,
    open_time TIMESTAMP NOT NULL,
    close_time TIMESTAMP CHECK (close_time IS NULL OR close_time >= open_time),
    cash_start DECIMAL(12,2) NOT NULL CHECK (cash_start >= 0),
    cash_end DECIMAL(12,2) CHECK (cash_end >= 0),
    total_sales DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (total_sales >= 0),
    CONSTRAINT fk_work_shift_employee FOREIGN KEY (employee_id) REFERENCES employee(id)
);

CREATE TABLE IF NOT EXISTS salary (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    employee_id INT NOT NULL,
    period_month DATE NOT NULL,
    base_amount DECIMAL(10,2) NOT NULL CHECK (base_amount >= 0),
    bonus DECIMAL(10,2) NOT NULL DEFAULT 0 CHECK (bonus >= 0),
    total DECIMAL(10,2) GENERATED ALWAYS AS (base_amount + bonus) STORED,
    CONSTRAINT uq_salary_employee_month UNIQUE (employee_id, period_month),
    CONSTRAINT fk_salary_employee FOREIGN KEY (employee_id) REFERENCES employee(id)
);

CREATE TABLE IF NOT EXISTS user_account (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    employee_id INT NOT NULL UNIQUE,
    login VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role_id INT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT fk_user_account_employee FOREIGN KEY (employee_id) REFERENCES employee(id),
    CONSTRAINT fk_user_account_role FOREIGN KEY (role_id) REFERENCES role_in_store(id)
);