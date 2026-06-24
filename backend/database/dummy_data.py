import sqlite3

DB_NAME = "financial_agent.db"

schema = """
DROP TABLE IF EXISTS support_tickets;
DROP TABLE IF EXISTS credit_cards;
DROP TABLE IF EXISTS loans;
DROP TABLE IF EXISTS transactions;
DROP TABLE IF EXISTS market_prices;
DROP TABLE IF EXISTS holdings;
DROP TABLE IF EXISTS portfolios;
DROP TABLE IF EXISTS securities;
DROP TABLE IF EXISTS accounts;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS advisors;

CREATE TABLE advisors (
    advisor_id INTEGER PRIMARY KEY,
    advisor_name TEXT,
    region TEXT
);

CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    first_name TEXT,
    last_name TEXT,
    age INTEGER,
    city TEXT,
    state TEXT,
    annual_income REAL,
    customer_since DATE,
    advisor_id INTEGER,
    FOREIGN KEY (advisor_id) REFERENCES advisors(advisor_id)
);

CREATE TABLE accounts (
    account_id INTEGER PRIMARY KEY,
    customer_id INTEGER,
    account_type TEXT,
    balance REAL,
    open_date DATE,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE portfolios (
    portfolio_id INTEGER PRIMARY KEY,
    account_id INTEGER,
    portfolio_name TEXT,
    FOREIGN KEY (account_id) REFERENCES accounts(account_id)
);

CREATE TABLE securities (
    security_id INTEGER PRIMARY KEY,
    ticker TEXT,
    company_name TEXT,
    sector TEXT
);

CREATE TABLE holdings (
    holding_id INTEGER PRIMARY KEY,
    portfolio_id INTEGER,
    security_id INTEGER,
    shares REAL,
    FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id),
    FOREIGN KEY (security_id) REFERENCES securities(security_id)
);

CREATE TABLE market_prices (
    security_id INTEGER,
    price_date DATE,
    closing_price REAL,
    FOREIGN KEY (security_id) REFERENCES securities(security_id)
);

CREATE TABLE transactions (
    transaction_id INTEGER PRIMARY KEY,
    account_id INTEGER,
    transaction_date DATE,
    transaction_type TEXT,
    amount REAL,
    merchant TEXT,
    FOREIGN KEY (account_id) REFERENCES accounts(account_id)
);

CREATE TABLE loans (
    loan_id INTEGER PRIMARY KEY,
    customer_id INTEGER,
    loan_type TEXT,
    principal REAL,
    interest_rate REAL,
    outstanding_balance REAL,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE credit_cards (
    card_id INTEGER PRIMARY KEY,
    customer_id INTEGER,
    credit_limit REAL,
    current_balance REAL,
    rewards_points INTEGER,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE support_tickets (
    ticket_id INTEGER PRIMARY KEY,
    customer_id INTEGER,
    created_date DATE,
    category TEXT,
    status TEXT,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);
"""


schema2 = """
"""
conn = sqlite3.connect(DB_NAME)

# Enable foreign key support
conn.execute("PRAGMA foreign_keys = ON;")

conn.executescript(schema)

conn.commit()
conn.close()

print(f"Database created successfully: {DB_NAME}")