"""
db_handler.py
CIS4301 Project — Item Rental Management System
Database query layer for the TPC-DS-backed rental system.

All SQL statements use parameterized queries (? placeholders) to prevent
SQL injection. CHAR columns from TPC-DS are space-padded; we strip
trailing whitespace whenever building model objects from query rows.
"""

from MARIADB_CREDS import DB_CONFIG
from mariadb import connect
from models.RentalHistory import RentalHistory
from models.Waitlist import Waitlist
from models.Item import Item
from models.Rental import Rental
from models.Customer import Customer
from datetime import date, timedelta


# Module-level connection (matches the names referenced by public_tests.py
# and by main.py / helper_functions.py via db.save_changes / db.close_connection).
conn = connect(user=DB_CONFIG["username"], password=DB_CONFIG["password"], host=DB_CONFIG["host"],
               database=DB_CONFIG["database"], port=DB_CONFIG["port"])

cur = conn.cursor()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _s(value):
    """Strip a CHAR-padded string; leave None alone."""
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip()
    return value


def _date_str(value):
    """Convert a datetime.date (or None) into a YYYY-MM-DD string."""
    if value is None:
        return None
    return str(value)


def _parse_address(address_str: str):
    """
    Parse 'street_number street_name, city, state zip' into the 5 columns of
    customer_address. Mirrors how helper_functions.add_customer constructs
    the address string.
    """
    parts = [p.strip() for p in address_str.split(",")]
    street_part = parts[0] if len(parts) > 0 else ""
    city = parts[1] if len(parts) > 1 else ""
    state_zip = parts[2].split() if len(parts) > 2 else ["", ""]
    state = state_zip[0] if len(state_zip) > 0 else ""
    zip_code = state_zip[1] if len(state_zip) > 1 else ""

    street_split = street_part.split(" ", 1)
    street_number = street_split[0]
    street_name = street_split[1] if len(street_split) > 1 else ""
    return street_number, street_name, city, state, zip_code


def _string_pred(column: str, use_patterns: bool) -> str:
    """
    Build a single-column predicate using either '=' or LIKE.
    For LIKE we wrap the column in TRIM() so patterns interact correctly with
    CHAR-padded values (CHAR equality is already padding-aware in MariaDB).
    """
    if use_patterns:
        return f"TRIM({column}) LIKE ?"
    return f"{column} = ?"


# ---------------------------------------------------------------------------
# Item operations
# ---------------------------------------------------------------------------
def add_item(new_item: Item = None):
    """Insert a new item. Generates fresh i_item_sk and constructs i_rec_start_date."""
    cur.execute("SELECT COALESCE(MAX(i_item_sk), 0) + 1 FROM item")
    new_sk = cur.fetchone()[0]

    rec_start_date = f"{new_item.start_year}-01-01"

    cur.execute(
        """
        INSERT INTO item
            (i_item_sk, i_item_id, i_rec_start_date, i_product_name,
             i_brand, i_class, i_category, i_manufact,
             i_current_price, i_num_owned)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_sk,
            new_item.item_id,
            rec_start_date,
            new_item.product_name,
            new_item.brand,
            None,                       # i_class is not tracked by the Item model
            new_item.category,
            new_item.manufact,
            new_item.current_price,
            new_item.num_owned,
        ),
    )


# ---------------------------------------------------------------------------
# Customer operations
# ---------------------------------------------------------------------------
def add_customer(new_customer: Customer = None):
    """Insert a customer_address row, then a customer row referencing it."""
    street_number, street_name, city, state, zip_code = _parse_address(
        new_customer.address
    )

    cur.execute("SELECT COALESCE(MAX(ca_address_sk), 0) + 1 FROM customer_address")
    new_addr_sk = cur.fetchone()[0]

    cur.execute(
        """
        INSERT INTO customer_address
            (ca_address_sk, ca_street_number, ca_street_name,
             ca_city, ca_state, ca_zip)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (new_addr_sk, street_number, street_name, city, state, zip_code),
    )

    cur.execute("SELECT COALESCE(MAX(c_customer_sk), 0) + 1 FROM customer")
    new_cust_sk = cur.fetchone()[0]

    # Split full name on the first space.
    name_split = new_customer.name.split(" ", 1)
    first_name = name_split[0]
    last_name = name_split[1] if len(name_split) > 1 else ""

    cur.execute(
        """
        INSERT INTO customer
            (c_customer_sk, c_customer_id, c_first_name, c_last_name,
             c_email_address, c_current_addr_sk)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            new_cust_sk,
            new_customer.customer_id,
            first_name,
            last_name,
            new_customer.email,
            new_addr_sk,
        ),
    )


def edit_customer(original_customer_id: str = None, new_customer: Customer = None):
    """Update only fields of new_customer that are not None.
    Identifies the existing customer by original_customer_id."""

    # Look up the address surrogate key BEFORE mutating the customer row,
    # so renaming the customer_id won't break the address lookup.
    addr_sk = None
    if new_customer.address is not None:
        cur.execute(
            "SELECT c_current_addr_sk FROM customer WHERE c_customer_id = ?",
            (original_customer_id,),
        )
        row = cur.fetchone()
        if row is not None:
            addr_sk = row[0]

    updates = []
    params = []

    if new_customer.customer_id is not None:
        updates.append("c_customer_id = ?")
        params.append(new_customer.customer_id)

    if new_customer.name is not None:
        name_split = new_customer.name.split(" ", 1)
        first_name = name_split[0]
        last_name = name_split[1] if len(name_split) > 1 else ""
        updates.append("c_first_name = ?")
        params.append(first_name)
        updates.append("c_last_name = ?")
        params.append(last_name)

    if new_customer.email is not None:
        updates.append("c_email_address = ?")
        params.append(new_customer.email)

    if updates:
        params.append(original_customer_id)
        sql = (
            "UPDATE customer SET "
            + ", ".join(updates)
            + " WHERE c_customer_id = ?"
        )
        cur.execute(sql, params)

    if new_customer.address is not None and addr_sk is not None:
        street_number, street_name, city, state, zip_code = _parse_address(
            new_customer.address
        )
        cur.execute(
            """
            UPDATE customer_address
            SET ca_street_number = ?, ca_street_name = ?,
                ca_city = ?, ca_state = ?, ca_zip = ?
            WHERE ca_address_sk = ?
            """,
            (street_number, street_name, city, state, zip_code, addr_sk),
        )


# ---------------------------------------------------------------------------
# Rental operations
# ---------------------------------------------------------------------------
def rent_item(item_id: str = None, customer_id: str = None):
    """Insert a new active rental: rental_date = today, due_date = today + 14d."""
    today = date.today()
    due = today + timedelta(days=14)
    cur.execute(
        """
        INSERT INTO rental (item_id, customer_id, rental_date, due_date)
        VALUES (?, ?, ?, ?)
        """,
        (item_id, customer_id, str(today), str(due)),
    )


def return_item(item_id: str = None, customer_id: str = None):
    """Move a rental row from `rental` to `rental_history` with today's return_date."""
    cur.execute(
        """
        SELECT rental_date, due_date FROM rental
        WHERE item_id = ? AND customer_id = ?
        """,
        (item_id, customer_id),
    )
    row = cur.fetchone()
    if row is None:
        return  # nothing to return

    rental_date, due_date = row
    today = str(date.today())

    cur.execute(
        """
        INSERT INTO rental_history
            (item_id, customer_id, rental_date, due_date, return_date)
        VALUES (?, ?, ?, ?, ?)
        """,
        (item_id, customer_id, str(rental_date), str(due_date), today),
    )

    cur.execute(
        "DELETE FROM rental WHERE item_id = ? AND customer_id = ?",
        (item_id, customer_id),
    )


def grant_extension(item_id: str = None, customer_id: str = None):
    """Add 14 days to due_date of an active rental."""
    cur.execute(
        """
        UPDATE rental
        SET due_date = DATE_ADD(due_date, INTERVAL 14 DAY)
        WHERE item_id = ? AND customer_id = ?
        """,
        (item_id, customer_id),
    )


# ---------------------------------------------------------------------------
# Waitlist operations
# ---------------------------------------------------------------------------
def waitlist_customer(item_id: str = None, customer_id: str = None) -> int:
    """Append the customer to the waitlist; return their new place_in_line."""
    new_place = line_length(item_id) + 1
    cur.execute(
        """
        INSERT INTO waitlist (item_id, customer_id, place_in_line)
        VALUES (?, ?, ?)
        """,
        (item_id, customer_id, new_place),
    )
    return new_place


def update_waitlist(item_id: str = None):
    """Remove place_in_line=1 for that item, then shift everyone else up by one."""
    cur.execute(
        "DELETE FROM waitlist WHERE item_id = ? AND place_in_line = 1",
        (item_id,),
    )
    cur.execute(
        "UPDATE waitlist SET place_in_line = place_in_line - 1 WHERE item_id = ?",
        (item_id,),
    )


# ---------------------------------------------------------------------------
# Stock / waitlist queries
# ---------------------------------------------------------------------------
def number_in_stock(item_id: str = None) -> int:
    """num_owned - active rentals. Returns -1 if the item doesn't exist."""
    cur.execute("SELECT i_num_owned FROM item WHERE i_item_id = ?", (item_id,))
    row = cur.fetchone()
    if row is None:
        return -1
    num_owned = row[0]

    cur.execute("SELECT COUNT(*) FROM rental WHERE item_id = ?", (item_id,))
    rented = cur.fetchone()[0]

    return int(num_owned) - int(rented)


def place_in_line(item_id: str = None, customer_id: str = None) -> int:
    """Customer's position on the item's waitlist, or -1 if not present."""
    cur.execute(
        """
        SELECT place_in_line FROM waitlist
        WHERE item_id = ? AND customer_id = ?
        """,
        (item_id, customer_id),
    )
    row = cur.fetchone()
    return int(row[0]) if row is not None else -1


def line_length(item_id: str = None) -> int:
    """Number of customers currently on the waitlist for this item (0 if none)."""
    cur.execute("SELECT COUNT(*) FROM waitlist WHERE item_id = ?", (item_id,))
    return int(cur.fetchone()[0])


# ---------------------------------------------------------------------------
# Filtered SELECT helpers
# ---------------------------------------------------------------------------
def get_filtered_items(filter_attributes: Item = None,
                       use_patterns: bool = False,
                       min_price: float = -1,
                       max_price: float = -1,
                       min_start_year: int = -1,
                       max_start_year: int = -1) -> list[Item]:
    conditions = []
    params = []

    if filter_attributes.item_id is not None:
        conditions.append(_string_pred("i_item_id", use_patterns))
        params.append(filter_attributes.item_id)
    if filter_attributes.product_name is not None:
        conditions.append(_string_pred("i_product_name", use_patterns))
        params.append(filter_attributes.product_name)
    if filter_attributes.brand is not None:
        conditions.append(_string_pred("i_brand", use_patterns))
        params.append(filter_attributes.brand)
    if filter_attributes.category is not None:
        conditions.append(_string_pred("i_category", use_patterns))
        params.append(filter_attributes.category)
    if filter_attributes.manufact is not None:
        conditions.append(_string_pred("i_manufact", use_patterns))
        params.append(filter_attributes.manufact)

    # Numeric Item fields default to -1 (per Item.__init__).
    if filter_attributes.current_price != -1 and filter_attributes.current_price is not None:
        conditions.append("i_current_price = ?")
        params.append(filter_attributes.current_price)
    if filter_attributes.num_owned != -1 and filter_attributes.num_owned is not None:
        conditions.append("i_num_owned = ?")
        params.append(filter_attributes.num_owned)
    if filter_attributes.start_year != -1 and filter_attributes.start_year is not None:
        conditions.append("YEAR(i_rec_start_date) = ?")
        params.append(filter_attributes.start_year)

    # Inclusive range filters.
    if min_price != -1:
        conditions.append("i_current_price >= ?")
        params.append(min_price)
    if max_price != -1:
        conditions.append("i_current_price <= ?")
        params.append(max_price)
    if min_start_year != -1:
        conditions.append("YEAR(i_rec_start_date) >= ?")
        params.append(min_start_year)
    if max_start_year != -1:
        conditions.append("YEAR(i_rec_start_date) <= ?")
        params.append(max_start_year)

    sql = (
        "SELECT i_item_id, i_product_name, i_brand, i_category, i_manufact, "
        "i_current_price, YEAR(i_rec_start_date), i_num_owned FROM item"
    )
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    cur.execute(sql, params)
    items = []
    for row in cur.fetchall():
        items.append(
            Item(
                item_id=_s(row[0]),
                product_name=_s(row[1]),
                brand=_s(row[2]),
                category=_s(row[3]),
                manufact=_s(row[4]),
                current_price=float(row[5]) if row[5] is not None else -1,
                start_year=int(row[6]) if row[6] is not None else -1,
                num_owned=int(row[7]) if row[7] is not None else -1,
            )
        )
    return items


def get_filtered_customers(filter_attributes: Customer = None,
                           use_patterns: bool = False) -> list[Customer]:
    conditions = []
    params = []

    if filter_attributes.customer_id is not None:
        conditions.append(_string_pred("c.c_customer_id", use_patterns))
        params.append(filter_attributes.customer_id)

    if filter_attributes.name is not None:
        # Match against the trimmed concatenation "first last".
        if use_patterns:
            conditions.append(
                "CONCAT(TRIM(c.c_first_name), ' ', TRIM(c.c_last_name)) LIKE ?"
            )
        else:
            conditions.append(
                "CONCAT(TRIM(c.c_first_name), ' ', TRIM(c.c_last_name)) = ?"
            )
        params.append(filter_attributes.name)

    if filter_attributes.email is not None:
        conditions.append(_string_pred("c.c_email_address", use_patterns))
        params.append(filter_attributes.email)

    if filter_attributes.address is not None:
        full_addr_expr = (
            "CONCAT(TRIM(ca.ca_street_number), ' ', TRIM(ca.ca_street_name), "
            "', ', TRIM(ca.ca_city), ', ', TRIM(ca.ca_state), ' ', TRIM(ca.ca_zip))"
        )
        if use_patterns:
            conditions.append(f"{full_addr_expr} LIKE ?")
        else:
            conditions.append(f"{full_addr_expr} = ?")
        params.append(filter_attributes.address)

    sql = """
        SELECT c.c_customer_id,
               CONCAT(TRIM(c.c_first_name), ' ', TRIM(c.c_last_name)) AS full_name,
               c.c_email_address,
               CASE WHEN ca.ca_address_sk IS NULL THEN NULL
                    ELSE CONCAT(TRIM(ca.ca_street_number), ' ',
                                TRIM(ca.ca_street_name), ', ',
                                TRIM(ca.ca_city), ', ',
                                TRIM(ca.ca_state), ' ',
                                TRIM(ca.ca_zip))
               END AS full_address
        FROM customer c
        LEFT JOIN customer_address ca
               ON c.c_current_addr_sk = ca.ca_address_sk
    """
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    cur.execute(sql, params)
    customers = []
    for row in cur.fetchall():
        customers.append(
            Customer(
                customer_id=_s(row[0]),
                name=_s(row[1]),
                email=_s(row[2]),
                address=_s(row[3]),
            )
        )
    return customers


def get_filtered_rentals(filter_attributes: Rental = None,
                         min_rental_date: str = None,
                         max_rental_date: str = None,
                         min_due_date: str = None,
                         max_due_date: str = None) -> list[Rental]:
    conditions = []
    params = []

    if filter_attributes.item_id is not None:
        conditions.append("item_id = ?")
        params.append(filter_attributes.item_id)
    if filter_attributes.customer_id is not None:
        conditions.append("customer_id = ?")
        params.append(filter_attributes.customer_id)
    if filter_attributes.rental_date is not None:
        conditions.append("rental_date = ?")
        params.append(filter_attributes.rental_date)
    if filter_attributes.due_date is not None:
        conditions.append("due_date = ?")
        params.append(filter_attributes.due_date)

    if min_rental_date is not None:
        conditions.append("rental_date >= ?")
        params.append(min_rental_date)
    if max_rental_date is not None:
        conditions.append("rental_date <= ?")
        params.append(max_rental_date)
    if min_due_date is not None:
        conditions.append("due_date >= ?")
        params.append(min_due_date)
    if max_due_date is not None:
        conditions.append("due_date <= ?")
        params.append(max_due_date)

    sql = "SELECT item_id, customer_id, rental_date, due_date FROM rental"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    cur.execute(sql, params)
    return [
        Rental(
            item_id=_s(row[0]),
            customer_id=_s(row[1]),
            rental_date=_date_str(row[2]),
            due_date=_date_str(row[3]),
        )
        for row in cur.fetchall()
    ]


def get_filtered_rental_histories(filter_attributes: RentalHistory = None,
                                  min_rental_date: str = None,
                                  max_rental_date: str = None,
                                  min_due_date: str = None,
                                  max_due_date: str = None,
                                  min_return_date: str = None,
                                  max_return_date: str = None) -> list[RentalHistory]:
    conditions = []
    params = []

    if filter_attributes.item_id is not None:
        conditions.append("item_id = ?")
        params.append(filter_attributes.item_id)
    if filter_attributes.customer_id is not None:
        conditions.append("customer_id = ?")
        params.append(filter_attributes.customer_id)
    if filter_attributes.rental_date is not None:
        conditions.append("rental_date = ?")
        params.append(filter_attributes.rental_date)
    if filter_attributes.due_date is not None:
        conditions.append("due_date = ?")
        params.append(filter_attributes.due_date)
    if filter_attributes.return_date is not None:
        conditions.append("return_date = ?")
        params.append(filter_attributes.return_date)

    if min_rental_date is not None:
        conditions.append("rental_date >= ?")
        params.append(min_rental_date)
    if max_rental_date is not None:
        conditions.append("rental_date <= ?")
        params.append(max_rental_date)
    if min_due_date is not None:
        conditions.append("due_date >= ?")
        params.append(min_due_date)
    if max_due_date is not None:
        conditions.append("due_date <= ?")
        params.append(max_due_date)
    if min_return_date is not None:
        conditions.append("return_date >= ?")
        params.append(min_return_date)
    if max_return_date is not None:
        conditions.append("return_date <= ?")
        params.append(max_return_date)

    sql = (
        "SELECT item_id, customer_id, rental_date, due_date, return_date "
        "FROM rental_history"
    )
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    cur.execute(sql, params)
    return [
        RentalHistory(
            item_id=_s(row[0]),
            customer_id=_s(row[1]),
            rental_date=_date_str(row[2]),
            due_date=_date_str(row[3]),
            return_date=_date_str(row[4]),
        )
        for row in cur.fetchall()
    ]


def get_filtered_waitlist(filter_attributes: Waitlist = None,
                          min_place_in_line: int = -1,
                          max_place_in_line: int = -1) -> list[Waitlist]:
    conditions = []
    params = []

    if filter_attributes.item_id is not None:
        conditions.append("item_id = ?")
        params.append(filter_attributes.item_id)
    if filter_attributes.customer_id is not None:
        conditions.append("customer_id = ?")
        params.append(filter_attributes.customer_id)
    if filter_attributes.place_in_line != -1 and filter_attributes.place_in_line is not None:
        conditions.append("place_in_line = ?")
        params.append(filter_attributes.place_in_line)

    if min_place_in_line != -1:
        conditions.append("place_in_line >= ?")
        params.append(min_place_in_line)
    if max_place_in_line != -1:
        conditions.append("place_in_line <= ?")
        params.append(max_place_in_line)

    sql = "SELECT item_id, customer_id, place_in_line FROM waitlist"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    cur.execute(sql, params)
    return [
        Waitlist(
            item_id=_s(row[0]),
            customer_id=_s(row[1]),
            place_in_line=int(row[2]),
        )
        for row in cur.fetchall()
    ]


# ---------------------------------------------------------------------------
# Connection lifecycle
# ---------------------------------------------------------------------------
def save_changes():
    """Commit all pending changes."""
    conn.commit()


def close_connection():
    """Close the cursor and connection cleanly."""
    try:
        cur.close()
    finally:
        conn.close()