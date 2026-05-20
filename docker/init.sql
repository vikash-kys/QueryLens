-- ============================================================
-- Text-to-SQL Demo Database: E-Commerce Analytics Schema
-- ============================================================

-- Create read-only user for query sandboxing
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'readonly') THEN
    CREATE ROLE readonly WITH LOGIN PASSWORD 'readonly';
  END IF;
END
$$;

-- ============================================================
-- SCHEMA
-- ============================================================

CREATE TABLE IF NOT EXISTS customers (
    customer_id     SERIAL PRIMARY KEY,
    email           VARCHAR(255) UNIQUE NOT NULL,
    full_name       VARCHAR(255) NOT NULL,
    country         VARCHAR(100) NOT NULL,
    city            VARCHAR(100),
    age             INTEGER,
    segment         VARCHAR(50) CHECK (segment IN ('Enterprise', 'SMB', 'Consumer')),
    joined_at       TIMESTAMP NOT NULL DEFAULT NOW(),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE
);

COMMENT ON TABLE customers IS 'Registered customers across all regions';
COMMENT ON COLUMN customers.segment IS 'Customer tier: Enterprise (large orgs), SMB (small-medium biz), Consumer (individual)';

CREATE TABLE IF NOT EXISTS products (
    product_id      SERIAL PRIMARY KEY,
    sku             VARCHAR(100) UNIQUE NOT NULL,
    name            VARCHAR(255) NOT NULL,
    category        VARCHAR(100) NOT NULL,
    subcategory     VARCHAR(100),
    unit_price      NUMERIC(10,2) NOT NULL,
    cost_price      NUMERIC(10,2) NOT NULL,
    stock_quantity  INTEGER NOT NULL DEFAULT 0,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE products IS 'Product catalog with pricing and inventory';
COMMENT ON COLUMN products.unit_price IS 'Selling price to customer';
COMMENT ON COLUMN products.cost_price IS 'Our cost (used to calculate gross margin)';

CREATE TABLE IF NOT EXISTS orders (
    order_id        SERIAL PRIMARY KEY,
    customer_id     INTEGER NOT NULL REFERENCES customers(customer_id),
    status          VARCHAR(50) NOT NULL CHECK (status IN ('pending','processing','shipped','delivered','cancelled','refunded')),
    channel         VARCHAR(50) CHECK (channel IN ('web','mobile','api','partner')),
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    shipped_at      TIMESTAMP,
    delivered_at    TIMESTAMP,
    shipping_country VARCHAR(100),
    discount_pct    NUMERIC(5,2) DEFAULT 0,
    notes           TEXT
);

COMMENT ON TABLE orders IS 'Customer orders. status lifecycle: pending→processing→shipped→delivered';
COMMENT ON COLUMN orders.channel IS 'Acquisition channel where order was placed';

CREATE TABLE IF NOT EXISTS order_items (
    item_id         SERIAL PRIMARY KEY,
    order_id        INTEGER NOT NULL REFERENCES orders(order_id),
    product_id      INTEGER NOT NULL REFERENCES products(product_id),
    quantity        INTEGER NOT NULL CHECK (quantity > 0),
    unit_price      NUMERIC(10,2) NOT NULL,
    discount_pct    NUMERIC(5,2) DEFAULT 0
);

COMMENT ON TABLE order_items IS 'Line items within each order';
COMMENT ON COLUMN order_items.unit_price IS 'Price at time of purchase (may differ from current product price)';

CREATE TABLE IF NOT EXISTS returns (
    return_id       SERIAL PRIMARY KEY,
    order_id        INTEGER NOT NULL REFERENCES orders(order_id),
    item_id         INTEGER REFERENCES order_items(item_id),
    reason          VARCHAR(100) CHECK (reason IN ('defective','wrong_item','not_as_described','changed_mind','other')),
    requested_at    TIMESTAMP NOT NULL DEFAULT NOW(),
    resolved_at     TIMESTAMP,
    refund_amount   NUMERIC(10,2)
);

COMMENT ON TABLE returns IS 'Product return and refund requests';

CREATE TABLE IF NOT EXISTS marketing_campaigns (
    campaign_id     SERIAL PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    channel         VARCHAR(100) CHECK (channel IN ('email','social','search','display','affiliate')),
    budget          NUMERIC(12,2),
    spend           NUMERIC(12,2) DEFAULT 0,
    impressions     INTEGER DEFAULT 0,
    clicks          INTEGER DEFAULT 0,
    conversions     INTEGER DEFAULT 0,
    started_at      DATE NOT NULL,
    ended_at        DATE
);

COMMENT ON TABLE marketing_campaigns IS 'Marketing campaigns with performance metrics';

-- ============================================================
-- SEED DATA
-- ============================================================

INSERT INTO customers (email, full_name, country, city, age, segment, joined_at, is_active) VALUES
('alice.chen@acme.com','Alice Chen','USA','San Francisco',34,'Enterprise','2022-01-15',true),
('bob.smith@gmail.com','Bob Smith','USA','New York',28,'Consumer','2022-03-22',true),
('carlos.m@techcorp.com','Carlos Mendez','Mexico','Mexico City',42,'SMB','2022-02-10',true),
('diana.k@shop.de','Diana Klein','Germany','Berlin',31,'Consumer','2022-04-05',true),
('evan.p@bigco.com','Evan Park','South Korea','Seoul',39,'Enterprise','2022-01-30',true),
('fiona.w@startup.io','Fiona Walsh','UK','London',27,'SMB','2022-05-18',true),
('george.b@example.com','George Brown','Canada','Toronto',45,'Consumer','2022-06-01',true),
('hana.t@corp.jp','Hana Tanaka','Japan','Tokyo',36,'Enterprise','2022-03-14',true),
('ivan.p@mail.ru','Ivan Petrov','Russia','Moscow',29,'Consumer','2022-07-20',false),
('julia.r@biz.com','Julia Rodriguez','Spain','Madrid',33,'SMB','2022-08-09',true),
('kevin.l@enterprise.com','Kevin Liu','China','Shanghai',47,'Enterprise','2022-02-28',true),
('laura.m@home.com','Laura Martinez','Brazil','São Paulo',25,'Consumer','2022-09-15',true),
('mike.d@agency.com','Mike Davis','Australia','Sydney',38,'SMB','2022-10-03',true),
('nina.f@company.fr','Nina Fontaine','France','Paris',32,'SMB','2022-11-12',true),
('oscar.g@tech.com','Oscar Garcia','Argentina','Buenos Aires',41,'Consumer','2023-01-07',true),
('paula.s@firm.com','Paula Santos','Portugal','Lisbon',30,'SMB','2023-02-14',true),
('quinn.b@startup.com','Quinn Brown','USA','Austin',26,'SMB','2023-03-21',true),
('rachel.k@corp.com','Rachel Kim','USA','Chicago',35,'Enterprise','2023-04-08',true),
('samuel.n@biz.ng','Samuel Nwosu','Nigeria','Lagos',43,'SMB','2023-05-16',true),
('tina.v@example.nl','Tina Visser','Netherlands','Amsterdam',29,'Consumer','2023-06-22',true);

INSERT INTO products (sku, name, category, subcategory, unit_price, cost_price, stock_quantity) VALUES
('LAPTOP-PRO-15','ProBook 15 Laptop','Electronics','Computers',1299.99,720.00,45),
('LAPTOP-AIR-13','AirBook 13 Laptop','Electronics','Computers',899.99,500.00,82),
('PHONE-X12','Nexus X12 Smartphone','Electronics','Phones',799.99,420.00,130),
('PHONE-LITE','Nexus Lite Smartphone','Electronics','Phones',399.99,180.00,210),
('TABLET-10','Slate 10 Tablet','Electronics','Tablets',549.99,280.00,60),
('HEADPHONE-PRO','SoundMax Pro Headphones','Electronics','Audio',249.99,90.00,155),
('HEADPHONE-BASIC','SoundMax Basic Headphones','Electronics','Audio',79.99,25.00,300),
('KEYBOARD-MECH','MechType Pro Keyboard','Electronics','Accessories',129.99,45.00,200),
('MOUSE-WIRELESS','ErgoClick Wireless Mouse','Electronics','Accessories',59.99,18.00,350),
('MONITOR-27','ClearView 27" Monitor','Electronics','Displays',449.99,210.00,40),
('DESK-STAND','ErgoDesk Monitor Stand','Office','Furniture',89.99,32.00,175),
('CHAIR-ERGO','ErgoSeat Pro Chair','Office','Furniture',599.99,250.00,28),
('NOTEBOOK-A5','Premium A5 Notebook','Stationery','Notebooks',14.99,4.00,800),
('PEN-SET-10','Executive Pen Set (10pk)','Stationery','Writing',24.99,7.00,500),
('BACKPACK-PRO','TechPack Pro Backpack','Accessories','Bags',89.99,35.00,120),
('CABLE-USB-C','USB-C Pro Cable 2m','Electronics','Cables',19.99,5.00,600),
('CHARGER-65W','GaN 65W USB-C Charger','Electronics','Accessories',49.99,18.00,280),
('WEBCAM-HD','ClearCam HD Webcam','Electronics','Accessories',99.99,38.00,95),
('SSD-1TB','SpeedDrive 1TB SSD','Electronics','Storage',149.99,65.00,110),
('RAM-32GB','MaxRAM 32GB DDR5','Electronics','Storage',129.99,55.00,90);

-- Generate 500 orders spread over 2 years
INSERT INTO orders (customer_id, status, channel, created_at, shipped_at, delivered_at, shipping_country, discount_pct)
SELECT
    (RANDOM() * 19 + 1)::INTEGER,
    (ARRAY['pending','processing','shipped','delivered','delivered','delivered','cancelled','refunded'])[(RANDOM()*7+1)::INTEGER],
    (ARRAY['web','web','web','mobile','mobile','api','partner'])[(RANDOM()*6+1)::INTEGER],
    NOW() - (RANDOM() * 730)::INTEGER * INTERVAL '1 day' - (RANDOM()*86400)::INTEGER * INTERVAL '1 second',
    CASE WHEN RANDOM() > 0.2 THEN NOW() - (RANDOM()*700)::INTEGER * INTERVAL '1 day' ELSE NULL END,
    CASE WHEN RANDOM() > 0.3 THEN NOW() - (RANDOM()*680)::INTEGER * INTERVAL '1 day' ELSE NULL END,
    (ARRAY['USA','USA','USA','UK','Germany','Canada','France','Japan','Australia','Brazil','Mexico'])[(RANDOM()*10+1)::INTEGER],
    ROUND((RANDOM()*25)::NUMERIC, 2)
FROM generate_series(1, 500);

-- Generate order items (1-5 items per order)
INSERT INTO order_items (order_id, product_id, quantity, unit_price, discount_pct)
SELECT
    o.order_id,
    (RANDOM()*19+1)::INTEGER,
    (RANDOM()*4+1)::INTEGER,
    p.unit_price * (1 - o.discount_pct/100),
    ROUND((RANDOM()*15)::NUMERIC, 2)
FROM orders o
CROSS JOIN LATERAL (
    SELECT generate_series(1, (RANDOM()*4+1)::INTEGER)
) items(n)
JOIN products p ON p.product_id = (RANDOM()*19+1)::INTEGER
LIMIT 1800;

-- Generate returns
INSERT INTO returns (order_id, reason, requested_at, resolved_at, refund_amount)
SELECT
    order_id,
    (ARRAY['defective','wrong_item','not_as_described','changed_mind','other'])[(RANDOM()*4+1)::INTEGER],
    created_at + INTERVAL '7 days',
    CASE WHEN RANDOM() > 0.3 THEN created_at + INTERVAL '14 days' ELSE NULL END,
    ROUND((RANDOM()*200+20)::NUMERIC, 2)
FROM orders
WHERE status IN ('refunded','cancelled') OR RANDOM() < 0.05
LIMIT 80;

-- Marketing campaigns
INSERT INTO marketing_campaigns (name, channel, budget, spend, impressions, clicks, conversions, started_at, ended_at) VALUES
('Q1 Email Blast','email',5000,4800,85000,6200,340,'2024-01-01','2024-03-31'),
('Spring Social Push','social',12000,11500,420000,18000,820,'2024-03-15','2024-05-15'),
('Summer Search Ads','search',20000,19200,380000,32000,1450,'2024-06-01','2024-08-31'),
('Back to School','email',8000,7600,120000,9500,510,'2024-08-01','2024-09-15'),
('Product Launch Q3','social',15000,14200,680000,25000,1120,'2024-07-01','2024-09-30'),
('Holiday Affiliate','affiliate',10000,9800,250000,41000,2100,'2024-11-01','2024-12-31'),
('New Year Display','display',6000,5500,900000,12000,280,'2025-01-01','2025-01-31'),
('Valentine Email','email',3000,2900,60000,5100,290,'2025-02-01','2025-02-14'),
('Spring Display','display',8000,6200,750000,14000,340,'2025-03-01','2025-04-30'),
('Q2 Search Push','search',25000,22000,520000,45000,1980,'2025-04-01','2025-06-30');

-- Grant read-only permissions
GRANT CONNECT ON DATABASE analytics TO readonly;
GRANT USAGE ON SCHEMA public TO readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly;

-- Helpful views
CREATE OR REPLACE VIEW revenue_by_month AS
SELECT
    DATE_TRUNC('month', o.created_at) AS month,
    SUM(oi.quantity * oi.unit_price) AS gross_revenue,
    COUNT(DISTINCT o.order_id) AS orders,
    COUNT(DISTINCT o.customer_id) AS unique_customers
FROM orders o
JOIN order_items oi ON oi.order_id = o.order_id
WHERE o.status NOT IN ('cancelled','refunded')
GROUP BY 1
ORDER BY 1;

CREATE OR REPLACE VIEW product_performance AS
SELECT
    p.product_id, p.name, p.category, p.subcategory,
    SUM(oi.quantity) AS units_sold,
    SUM(oi.quantity * oi.unit_price) AS revenue,
    SUM(oi.quantity * (oi.unit_price - p.cost_price)) AS gross_profit,
    ROUND(100.0 * SUM(oi.quantity * (oi.unit_price - p.cost_price)) / NULLIF(SUM(oi.quantity * oi.unit_price),0), 2) AS margin_pct
FROM products p
LEFT JOIN order_items oi ON oi.product_id = p.product_id
LEFT JOIN orders o ON o.order_id = oi.order_id AND o.status NOT IN ('cancelled','refunded')
GROUP BY 1,2,3,4;

COMMENT ON VIEW revenue_by_month IS 'Monthly gross revenue, order counts, and unique customers. Excludes cancelled/refunded orders.';
COMMENT ON VIEW product_performance IS 'Per-product sales metrics: units sold, revenue, gross profit, and margin percentage.';
