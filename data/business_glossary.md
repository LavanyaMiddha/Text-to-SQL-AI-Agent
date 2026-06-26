# Business Glossary

A translation layer between the language users speak and the database columns
that represent those concepts. When a user asks a natural-language question,
map their terminology through this glossary before generating SQL.

---

## A

**Account**
A financial product held by a customer at the firm.  
→ Table: `accounts`  
→ Key columns: `account_id`, `account_type`, `balance`, `open_date`  
→ Types: Checking, Savings, Brokerage, IRA, Roth IRA, 401k

**Account Balance / Cash Balance**
The current cash value sitting in an account, not including investment holdings.  
→ Column: `accounts.balance`  
→ Note: This is distinct from *portfolio value*, which is computed from holdings × price.

**Advisor / Financial Advisor**
A firm employee who manages customer relationships and may oversee investment strategy.  
→ Table: `advisors`  
→ Key columns: `advisor_id`, `advisor_name`, `region`

**AUM (Assets Under Management)**
The total current market value of all investment holdings managed by an advisor or the firm.  
→ Computed: `SUM(holdings.shares × market_prices.closing_price)`  
→ Always filter `market_prices` to `MAX(price_date)` to get current AUM.

**Annual Income**
Customer's reported gross annual income.  
→ Column: `customers.annual_income`  
→ Unit: USD

---

## B

**Balance**  
See *Account Balance*.

**Brokerage Account**
An account type used to hold investment securities (stocks, ETFs, bonds).  
→ Filter: `accounts.account_type = 'Brokerage'`

---

## C

**Card / Credit Card**
A revolving credit product issued to a customer.  
→ Table: `credit_cards`  
→ Key columns: `card_id`, `credit_limit`, `current_balance`, `rewards_points`

**Client**  
Synonym for *Customer*.  
→ Table: `customers`

**Closing Price**
The market price of a security at the end of a trading day.  
→ Column: `market_prices.closing_price`

**Credit Limit**
The maximum amount a customer is allowed to owe on a credit card.  
→ Column: `credit_cards.credit_limit`

**Credit Utilization / Utilization Rate**
Current credit card balance divided by credit limit, expressed as a percentage.  
→ Formula: `current_balance / credit_limit * 100`  
→ High utilization (>70%) is a risk indicator.

**Customer**
An individual who holds products (accounts, loans, credit cards) at the firm.  
→ Table: `customers`  
→ Key columns: `customer_id`, `first_name`, `last_name`, `age`, `city`, `state`, `annual_income`, `customer_since`, `advisor_id`

**Customer Since / Tenure**
The date the customer first opened a relationship with the firm.  
→ Column: `customers.customer_since`  
→ Tenure in years: `(julianday('now') - julianday(customer_since)) / 365.25`

---

## D

**Debt**
Total money owed by a customer. May refer to loans, credit card balances, or both.  
→ Loans: `loans.outstanding_balance`  
→ Credit cards: `credit_cards.current_balance`  
→ Total debt: SUM of both across all products.

**Debt-to-Income Ratio (DTI)**
Outstanding debt divided by annual income. Standard creditworthiness measure.  
→ Formula: `SUM(outstanding_balance) / annual_income`

**Deposit**
A credit transaction adding funds to an account.  
→ Filter: `transactions.transaction_type = 'Deposit'`

---

## F

**Full Name / Customer Name**
Concatenation of first and last name.  
→ Formula: `first_name || ' ' || last_name`

---

## H

**Holding / Position**
A quantity of a specific security held inside a portfolio.  
→ Table: `holdings`  
→ Key columns: `portfolio_id`, `security_id`, `shares`

---

## I

**Income**  
See *Annual Income*.

**Interest Rate**
The annual percentage rate charged on a loan.  
→ Column: `loans.interest_rate`  
→ Stored as a decimal (0.065 = 6.5%). Multiply by 100 to display as percent.

**IRA (Individual Retirement Account)**
A tax-advantaged retirement savings account type.  
→ Filter: `accounts.account_type IN ('IRA', 'Roth IRA')`

---

## L

**Loan**
A debt product where the firm lends money to a customer.  
→ Table: `loans`  
→ Key columns: `loan_id`, `loan_type`, `principal`, `interest_rate`, `outstanding_balance`  
→ Types: Mortgage, Auto, Personal, Student, Home Equity

**Loan Balance / Outstanding Balance**
The amount still owed on a loan after payments.  
→ Column: `loans.outstanding_balance`

---

## M

**Market Value / Portfolio Value**
Current value of investment holdings = shares × latest closing price.  
→ Formula: `SUM(holdings.shares × market_prices.closing_price)`  
→ Always join `market_prices` filtered to `MAX(price_date)`.

**Merchant**
The payee or vendor associated with a transaction.  
→ Column: `transactions.merchant`

**Most Recent Price / Current Price**
Latest available closing price for a security.  
→ Filter: `WHERE price_date = (SELECT MAX(price_date) FROM market_prices)`

---

## N

**Net Worth (Estimated)**
A customer's total assets minus total liabilities.  
→ Formula: `(account balances + portfolio value) − (outstanding loans + credit card balances)`  
→ This is an estimate; actual net worth may include external assets.

---

## O

**Open Date**
Date an account was opened.  
→ Column: `accounts.open_date`

**Open Ticket**
A support ticket that has not been resolved or closed.  
→ Filter: `support_tickets.status NOT IN ('Resolved', 'Closed')`

**Outstanding Balance**  
See *Loan Balance*.

---

## P

**Portfolio**
A named collection of investment holdings within an account.  
→ Table: `portfolios`  
→ One account may have multiple portfolios (e.g., "Growth", "Income").

**Portfolio Value**  
See *Market Value*.

**Position**  
Synonym for *Holding*.

**Principal**
The original loan amount disbursed before any repayments.  
→ Column: `loans.principal`

---

## R

**Region**
The geographic territory an advisor is assigned to.  
→ Column: `advisors.region`

**Rewards Points / Points**
Loyalty points accumulated on a credit card.  
→ Column: `credit_cards.rewards_points`

---

## S

**Security / Stock / Ticker**
A tradable financial instrument (stock, ETF, bond, fund).  
→ Table: `securities`  
→ Key columns: `security_id`, `ticker`, `company_name`, `sector`

**Sector**
The industry classification of a security (e.g., Technology, Healthcare).  
→ Column: `securities.sector`

**Shares**
Number of units of a security held in a portfolio position.  
→ Column: `holdings.shares`  
→ May be fractional.

**Spend / Spending**
Outflows from an account — typically negative-amount transactions or those typed as Purchase/Payment/Withdrawal.  
→ Table: `transactions`  
→ Common filter: `amount < 0` OR `transaction_type IN ('Purchase', 'Payment', 'Withdrawal')`

**State**
US state abbreviation for a customer's address.  
→ Column: `customers.state`

**Support Ticket**
A logged customer service issue or request.  
→ Table: `support_tickets`  
→ Key columns: `ticket_id`, `created_date`, `category`, `status`

---

## T

**Tenure**  
See *Customer Since*.

**Ticker / Ticker Symbol**
The exchange abbreviation for a security (e.g., AAPL, MSFT, SPY).  
→ Column: `securities.ticker`

**Transaction**
A single financial event on an account (deposit, withdrawal, purchase, payment, etc.).  
→ Table: `transactions`  
→ Key columns: `transaction_id`, `account_id`, `transaction_date`, `transaction_type`, `amount`, `merchant`

**Transaction Type**
The category of a transaction event.  
→ Column: `transactions.transaction_type`  
→ Values: Deposit, Withdrawal, Purchase, Payment, Transfer, Fee, Interest, Dividend

---

## U

**Utilization**  
See *Credit Utilization*.

---

## W

**Withdrawal**
A debit transaction removing funds from an account.  
→ Filter: `transactions.transaction_type = 'Withdrawal'`

---

## Ambiguous / Watch-Out Terms

| User Says              | Could Mean                                      | Disambiguation                                         |
|------------------------|-------------------------------------------------|--------------------------------------------------------|
| "balance"              | `accounts.balance` OR portfolio market value    | Cash balance → `accounts.balance`; investment value → compute from `holdings × market_prices` |
| "account value"        | cash balance OR market value of holdings        | Clarify or sum both                                    |
| "debt"                 | loans only OR loans + credit cards              | Usually both; ask if unclear                           |
| "income"               | `customers.annual_income` OR transaction inflow | Stored value → `annual_income`; activity → `transactions` |
| "portfolio"            | `portfolios` table OR all investments           | `portfolios` is a named container; "all investments" means all holdings |
| "current price"        | latest `market_prices.closing_price`            | Always filter: `WHERE price_date = (SELECT MAX(price_date) FROM market_prices)` |
| "top customers"        | by AUM? income? tenure? spending?               | Always confirm the ranking dimension                   |
| "transactions"         | all types OR specific type?                     | Check if user means "purchases", "deposits", etc.      |
| "open accounts"        | accounts with `status = 'Open'`?                | Schema has no status column on accounts; open_date exists |
