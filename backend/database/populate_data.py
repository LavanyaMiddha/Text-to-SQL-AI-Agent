import sqlite3
import random
from faker import Faker
from datetime import date, timedelta

DB_NAME = "financial_agent.db"

fake = Faker()
random.seed(42)
Faker.seed(42)

conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

# -----------------------------------
# CONFIG
# -----------------------------------

NUM_ADVISORS = 25
NUM_CUSTOMERS = 1000
NUM_ACCOUNTS = 4000
NUM_PORTFOLIOS = 1800
NUM_SECURITIES = 200
NUM_TRANSACTIONS = 100000

# -----------------------------------
# ADVISORS
# -----------------------------------

regions = ["East", "West", "Central", "South"]

for advisor_id in range(1, NUM_ADVISORS + 1):
    cursor.execute(
        """
        INSERT INTO advisors
        VALUES (?, ?, ?)
        """,
        (
            advisor_id,
            fake.name(),
            random.choice(regions),
        ),
    )

print("Advisors inserted")

# -----------------------------------
# CUSTOMERS
# -----------------------------------

for customer_id in range(1, NUM_CUSTOMERS + 1):

    cursor.execute(
        """
        INSERT INTO customers
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            customer_id,
            fake.first_name(),
            fake.last_name(),
            random.randint(21, 80),
            fake.city(),
            fake.state_abbr(),
            random.randint(40000, 500000),
            fake.date_between(start_date="-12y"),
            random.randint(1, NUM_ADVISORS),
        ),
    )

print("Customers inserted")

# -----------------------------------
# ACCOUNTS
# -----------------------------------

account_customer_map = {}

for account_id in range(1, NUM_ACCOUNTS + 1):

    customer_id = random.randint(1, NUM_CUSTOMERS)

    account_customer_map[account_id] = customer_id

    cursor.execute(
        """
        INSERT INTO accounts
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            account_id,
            customer_id,
            random.choice(
                [
                    "Checking",
                    "Savings",
                    "Investment",
                ]
            ),
            round(
                random.uniform(
                    1000,
                    2500000,
                ),
                2,
            ),
            fake.date_between(start_date="-10y"),
        ),
    )

print("Accounts inserted")

# -----------------------------------
# PORTFOLIOS
# -----------------------------------

portfolio_account_map = {}

for portfolio_id in range(1, NUM_PORTFOLIOS + 1):

    account_id = random.randint(
        1,
        NUM_ACCOUNTS,
    )

    portfolio_account_map[
        portfolio_id
    ] = account_id

    cursor.execute(
        """
        INSERT INTO portfolios
        VALUES (?, ?, ?)
        """,
        (
            portfolio_id,
            account_id,
            f"Portfolio_{portfolio_id}",
        ),
    )

print("Portfolios inserted")

# -----------------------------------
# SECURITIES
# -----------------------------------

sectors = [
    "Technology",
    "Healthcare",
    "Financials",
    "Energy",
    "Consumer",
    "Industrial",
    "Utilities",
    "Materials",
]

for security_id in range(
    1,
    NUM_SECURITIES + 1,
):

    cursor.execute(
        """
        INSERT INTO securities
        VALUES (?, ?, ?, ?)
        """,
        (
            security_id,
            f"SEC{security_id}",
            f"Company {security_id}",
            random.choice(sectors),
        ),
    )

print("Securities inserted")

# -----------------------------------
# HOLDINGS
# -----------------------------------

holding_id = 1

for portfolio_id in portfolio_account_map:

    num_holdings = random.randint(
        5,
        20,
    )

    for _ in range(num_holdings):

        cursor.execute(
            """
            INSERT INTO holdings
            VALUES (?, ?, ?, ?)
            """,
            (
                holding_id,
                portfolio_id,
                random.randint(
                    1,
                    NUM_SECURITIES,
                ),
                round(
                    random.uniform(
                        10,
                        5000,
                    ),
                    2,
                ),
            ),
        )

        holding_id += 1

print("Holdings inserted")

# -----------------------------------
# MARKET PRICES
# -----------------------------------

today = date.today()

for security_id in range(
    1,
    NUM_SECURITIES + 1,
):

    for month in range(24):

        price_date = (
            today
            - timedelta(days=30 * month)
        )

        cursor.execute(
            """
            INSERT INTO market_prices
            VALUES (?, ?, ?)
            """,
            (
                security_id,
                price_date,
                round(
                    random.uniform(
                        10,
                        1500,
                    ),
                    2,
                ),
            ),
        )

print("Market prices inserted")

# -----------------------------------
# TRANSACTIONS
# -----------------------------------

transaction_types = [
    "Deposit",
    "Withdrawal",
    "Buy",
    "Sell",
]

merchants = [
    "Payroll",
    "ATM",
    "Amazon",
    "Apple",
    "Microsoft",
    "NVIDIA",
    "Google",
    "Brokerage",
]

for transaction_id in range(
    1,
    NUM_TRANSACTIONS + 1,
):

    cursor.execute(
        """
        INSERT INTO transactions
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            transaction_id,
            random.randint(
                1,
                NUM_ACCOUNTS,
            ),
            fake.date_between(
                start_date="-3y"
            ),
            random.choice(
                transaction_types
            ),
            round(
                random.uniform(
                    5,
                    50000,
                ),
                2,
            ),
            random.choice(
                merchants
            ),
        ),
    )

    if transaction_id % 5000 == 0:
        conn.commit()
        print(
            f"{transaction_id:,} transactions inserted..."
        )

print("Transactions inserted")

# -----------------------------------
# LOANS
# -----------------------------------

loan_id = 1

for customer_id in range(
    1,
    NUM_CUSTOMERS + 1,
):

    if random.random() < 0.35:

        principal = round(
            random.uniform(
                10000,
                900000,
            ),
            2,
        )

        outstanding = round(
            principal
            * random.uniform(
                0.2,
                0.95,
            ),
            2,
        )

        cursor.execute(
            """
            INSERT INTO loans
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                loan_id,
                customer_id,
                random.choice(
                    [
                        "Mortgage",
                        "Auto",
                        "Personal",
                        "Business",
                    ]
                ),
                principal,
                round(
                    random.uniform(
                        3,
                        12,
                    ),
                    2,
                ),
                outstanding,
            ),
        )

        loan_id += 1

print("Loans inserted")

# -----------------------------------
# CREDIT CARDS
# -----------------------------------

card_id = 1

for customer_id in range(
    1,
    NUM_CUSTOMERS + 1,
):

    if random.random() < 0.65:

        limit_amt = random.choice(
            [
                5000,
                10000,
                15000,
                25000,
                50000,
            ]
        )

        cursor.execute(
            """
            INSERT INTO credit_cards
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                card_id,
                customer_id,
                limit_amt,
                round(
                    limit_amt
                    * random.uniform(
                        0,
                        0.9,
                    ),
                    2,
                ),
                random.randint(
                    0,
                    100000,
                ),
            ),
        )

        card_id += 1

print("Credit cards inserted")

# -----------------------------------
# SUPPORT TICKETS
# -----------------------------------

ticket_id = 1

categories = [
    "Account Access",
    "Investment",
    "Loan",
    "Credit Card",
    "Fraud",
]

statuses = [
    "Open",
    "Closed",
    "In Progress",
]

for customer_id in range(
    1,
    NUM_CUSTOMERS + 1,
):

    for _ in range(
        random.randint(
            0,
            5,
        )
    ):

        cursor.execute(
            """
            INSERT INTO support_tickets
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                ticket_id,
                customer_id,
                fake.date_between(
                    start_date="-2y"
                ),
                random.choice(
                    categories
                ),
                random.choice(
                    statuses
                ),
            ),
        )

        ticket_id += 1

print("Support tickets inserted")

# -----------------------------------
# FINAL COMMIT
# -----------------------------------

conn.commit()

# Row counts
tables = [
    "advisors",
    "customers",
    "accounts",
    "portfolios",
    "securities",
    "holdings",
    "market_prices",
    "transactions",
    "loans",
    "credit_cards",
    "support_tickets",
]

print("\nRow Counts:")
for table in tables:
    count = cursor.execute(
        f"SELECT COUNT(*) FROM {table}"
    ).fetchone()[0]

    print(
        f"{table:<20} {count:,}"
    )

conn.close()

print("\nDatabase population complete.")