-- Demo dataset 1 (F39): an online store. Fixture for evals only; no code depends on its names.
-- Deterministic (setseed). Planted patterns are listed in planted_patterns.yaml.
-- Runs inside the target database; idempotent (drops and recreates its tables).
SET TIME ZONE 'UTC';
SELECT setseed(0.39);

DROP TABLE IF EXISTS refunds, order_items, orders, products, customers CASCADE;

CREATE TABLE customers (
    customer_id integer PRIMARY KEY,
    region text NOT NULL,
    segment text NOT NULL,
    signup_date date NOT NULL,
    email text
);
COMMENT ON TABLE customers IS 'One row per registered customer.';
COMMENT ON COLUMN customers.region IS 'Sales region of the customer: north, south, east, or west.';
COMMENT ON COLUMN customers.segment IS 'consumer or business.';
COMMENT ON COLUMN customers.email IS 'Contact email. Missing for some customers.';

CREATE TABLE products (
    product_id integer PRIMARY KEY,
    category text NOT NULL,
    product_name text NOT NULL,
    unit_price numeric(10, 2) NOT NULL
);
COMMENT ON TABLE products IS 'Product catalog with the current list price.';

CREATE TABLE orders (
    order_id integer PRIMARY KEY,
    customer_id integer NOT NULL REFERENCES customers (customer_id),
    ordered_at timestamptz NOT NULL,
    channel text NOT NULL,
    status text NOT NULL
);
COMMENT ON TABLE orders IS 'One row per order. Revenue counts completed orders only.';
COMMENT ON COLUMN orders.ordered_at IS 'When the order was placed (UTC).';
COMMENT ON COLUMN orders.channel IS 'Where the order was placed: web, app, or marketplace.';
COMMENT ON COLUMN orders.status IS 'completed or cancelled.';

CREATE TABLE order_items (
    line_id serial PRIMARY KEY,
    order_id integer NOT NULL REFERENCES orders (order_id),
    product_id integer NOT NULL REFERENCES products (product_id),
    quantity integer NOT NULL,
    unit_price numeric(10, 2) NOT NULL
);
COMMENT ON TABLE order_items IS 'Order lines. Line amount is quantity * unit_price.';
COMMENT ON COLUMN order_items.unit_price IS 'Price paid per unit at order time.';

CREATE TABLE refunds (
    refund_id serial PRIMARY KEY,
    order_id integer NOT NULL REFERENCES orders (order_id),
    refunded_at timestamptz NOT NULL,
    amount numeric(10, 2) NOT NULL
);
COMMENT ON TABLE refunds IS 'Money returned to customers, at most one refund per order.';

INSERT INTO customers
SELECT g,
       (ARRAY['north', 'south', 'east', 'west'])[1 + floor(random() * 4)::int],
       CASE WHEN random() < 0.3 THEN 'business' ELSE 'consumer' END,
       DATE '2024-01-01' + floor(random() * 600)::int,
       CASE WHEN random() < 0.08 THEN NULL ELSE 'customer' || g || '@example.com' END
FROM generate_series(1, 2000) AS g;

INSERT INTO products
SELECT g,
       (ARRAY['books', 'electronics', 'home', 'toys', 'sports', 'beauty'])[1 + (g - 1) % 6],
       'Product ' || g,
       round((5 + random() * 195)::numeric, 2)
FROM generate_series(1, 60) AS g;

-- Daily volume: +60% in November and December, +30% on weekends. No orders 2026-03-10..16.
CREATE TEMP TABLE order_days AS
SELECT day::date AS day,
       round(30 * (1
                   + CASE WHEN extract(month FROM day) IN (11, 12) THEN 0.6 ELSE 0 END
                   + CASE WHEN extract(isodow FROM day) IN (6, 7) THEN 0.3 ELSE 0 END)
                * (0.85 + random() * 0.3))::int AS order_count
FROM generate_series(DATE '2025-01-01', DATE '2026-10-31', INTERVAL '1 day') AS day
WHERE day::date NOT BETWEEN DATE '2026-03-10' AND DATE '2026-03-16';

CREATE TEMP TABLE draft_orders AS
SELECT d.day + make_interval(secs => floor(random() * 86400)) AS ordered_at,
       1 + floor(random() * 2000)::int AS customer_id,
       (ARRAY['web', 'app', 'marketplace'])[1 + floor(random() * 3)::int] AS channel,
       CASE WHEN random() < 0.05 THEN 'cancelled' ELSE 'completed' END AS status,
       random() AS keep_draw
FROM order_days AS d
CROSS JOIN LATERAL generate_series(1, d.order_count) AS n;

-- Region west loses about half of its orders from 2026-06-01.
INSERT INTO orders
SELECT row_number() OVER (ORDER BY d.ordered_at, d.customer_id, d.channel),
       d.customer_id, d.ordered_at, d.channel, d.status
FROM draft_orders AS d
JOIN customers AS c USING (customer_id)
WHERE NOT (c.region = 'west' AND d.ordered_at >= TIMESTAMPTZ '2026-06-01' AND d.keep_draw < 0.5);

-- Lines of one order always have different products, so every repeated line is a planted duplicate.
CREATE TEMP TABLE draft_items AS
SELECT o.order_id,
       1 + (o.order_id * 7 + line * 13) % 60 AS product_id,
       1 + floor(random() * 3)::int AS quantity
FROM orders AS o
CROSS JOIN generate_series(1, 4) AS line
WHERE line = 1 OR random() < 0.45;

INSERT INTO order_items (order_id, product_id, quantity, unit_price)
SELECT i.order_id, i.product_id, i.quantity, p.unit_price
FROM draft_items AS i
JOIN products AS p USING (product_id)
ORDER BY i.order_id, i.product_id, i.quantity;

-- Outlier: one completed order line with quantity 500.
UPDATE order_items SET quantity = 500
WHERE line_id = (
    SELECT min(i.line_id)
    FROM order_items AS i
    JOIN orders AS o USING (order_id)
    WHERE o.status = 'completed' AND o.ordered_at >= TIMESTAMPTZ '2026-08-15'
);

-- Duplicates: some order lines were ingested twice (same order, product, quantity, price).
INSERT INTO order_items (order_id, product_id, quantity, unit_price)
SELECT order_id, product_id, quantity, unit_price
FROM order_items
WHERE line_id % 997 = 0
ORDER BY line_id;

INSERT INTO refunds (order_id, refunded_at, amount)
SELECT o.order_id,
       o.ordered_at + make_interval(days => 1 + floor(random() * 14)::int),
       round(t.total * (0.3 + random() * 0.7)::numeric, 2)
FROM orders AS o
JOIN (
    SELECT order_id, sum(quantity * unit_price) AS total FROM order_items GROUP BY order_id
) AS t USING (order_id)
WHERE o.status = 'completed' AND random() < 0.03
ORDER BY o.order_id;

DROP TABLE order_days, draft_orders, draft_items;
ANALYZE;
