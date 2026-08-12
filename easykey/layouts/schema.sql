-- EasyKey layout database schema

CREATE TABLE IF NOT EXISTS keyboards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    via_name TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    vendor_id INTEGER,
    product_id INTEGER,
    rows INTEGER NOT NULL DEFAULT 0,
    cols INTEGER NOT NULL DEFAULT 0,
    num_keys INTEGER NOT NULL DEFAULT 0,
    kle_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS key_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyboard_id INTEGER NOT NULL,
    matrix_row INTEGER NOT NULL,
    matrix_col INTEGER NOT NULL,
    x REAL NOT NULL DEFAULT 0,
    y REAL NOT NULL DEFAULT 0,
    width REAL NOT NULL DEFAULT 1,
    height REAL NOT NULL DEFAULT 1,
    legend TEXT,
    FOREIGN KEY (keyboard_id) REFERENCES keyboards(id)
);

CREATE TABLE IF NOT EXISTS keycodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    code INTEGER NOT NULL,
    category TEXT NOT NULL DEFAULT 'standard',
    label TEXT NOT NULL,
    description TEXT
);

CREATE INDEX IF NOT EXISTS idx_key_positions_keyboard ON key_positions(keyboard_id);
CREATE INDEX IF NOT EXISTS idx_keycodes_category ON keycodes(category);
