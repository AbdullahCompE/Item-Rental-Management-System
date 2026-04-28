from re import S
from MARIADB_CREDS import DB_CONFIG
from mariadb import connect
from models.RentalHistory import RentalHistory
from models.Waitlist import Waitlist
from models.Item import Item
from models.Rental import Rental
from models.Customer import Customer
from datetime import date, timedelta


conn = connect(user=DB_CONFIG["username"], password=DB_CONFIG["password"], host=DB_CONFIG["host"],
               database=DB_CONFIG["database"], port=DB_CONFIG["port"])


cur = conn.cursor()


def add_item(new_item: Item = None):
    """
    new_item - An Item object containing a new item to be inserted into the DB in the item table.
        new_item and its attributes will never be None.
    """

    cur.execute("SELECT MAX(i_item_sk) + 1 FROM item")
    sk = cur.fetchone()[0]
        
    start_date = f"{new_item.start_year}-01-01" # TODO: is there any other way which we can figure out the date?

    cur.execute("""
                INSERT INTO item (
                   i_item_sk,
                   i_item_id,
                   i_rec_start_date,
                   i_product_name,
                   i_brand,
                   i_class,
                   i_category,
                   i_manufact,
                   i_current_price,
                   i_num_owned
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    sk,
                    new_item.item_id,
                    start_date,
                    new_item.product_name,
                    new_item.brand,
                    None,
                    new_item.category,
                    new_item.manufact,
                    new_item.current_price,
                    new_item.num_owned
                )
            )

    return

def parse_address(address: str):
    parts = [p.strip() for p in address.split(",")]

    street = parts[0].split()
    street_number = street[0]
    street_name = street[1]

    city = parts[1]

    state_zip = parts[2].split() 
    state = state_zip[0]
    zip = state_zip[1]

    return street_number, street_name, city, state, zip
   

def add_customer(new_customer: Customer = None):
    """
    new_customer - A Customer object containing a new customer to be inserted into the DB in the customer table.
        new_customer and its attributes will never be None.
    """
    # raise NotImplementedError("you must implement this function")

    street_number, street_name, city, state, zip = parse_address(new_customer.address)

    cur.execute("SELECT MAX(ca_address_sk) + 1 FROM customer_address")
    address_sk = cur.fetchone()[0]

    cur.execute("""
                INSERT INTO customer_address (
                    ca_address_sk,
                    ca_street_number,
                    ca_street_name,
                    ca_city,
                    ca_state,
                    ca_zip
                ) VALUES (?,?,?,?,?,?)
                """, (
                    address_sk,
                    street_number,
                    street_name,
                    city,
                    state,
                    zip
                )
            )


    cur.execute("SELECT MAX(c_customer_sk) + 1 FROM customer")
    sk = cur.fetchone()[0]

    name = new_customer.name.split(" ")
    first_name = name[0]
    last_name = name[1]

    cur.execute("""
                INSERT INTO customer (
                    c_customer_sk,
                    c_customer_id,
                    c_first_name,
                    c_last_name,
                    c_email_address,
                    c_current_addr_sk
                ) VALUES (?,?,?,?,?,?)
                """,
                (
                    sk,
                    new_customer.customer_id,
                    first_name,
                    last_name,
                    new_customer.email,
                    address_sk
                )
            )
    return


def edit_customer(original_customer_id: str = None, new_customer: Customer = None):
    """
    original_customer_id - A string containing the customer id for the customer to be edited.
    new_customer - A Customer object containing attributes to update. If an attribute is None, it should not be altered.
    """

    cur.execute(
        "SELECT c_current_addr_sk FROM customer WHERE c_customer_id = ?",
        (original_customer_id,)
    )
    row = cur.fetchone()
    if not row:
        return False

    address_sk = row[0]
    updates = []
    parameters = []

    if new_customer.customer_id is not None:
        updates.append("c_customer_id = ?")
        parameters.append(new_customer.customer_id)

    if new_customer.name is not None:
        name_parts = new_customer.name.strip().split(" ", 1)
        updates.extend(["c_first_name = ?", "c_last_name = ?"])
        parameters.append(name_parts[0])
        parameters.append(name_parts[1] if len(name_parts) > 1 else "")

    if new_customer.email is not None:
        updates.append("c_email_address = ?")
        parameters.append(new_customer.email)

    if updates:
        parameters.append(original_customer_id)
        sql = f"UPDATE customer SET {', '.join(updates)} WHERE c_customer_id = ?"
        cur.execute(sql, parameters)

    if new_customer.address is not None and address_sk is not None:
        street_number, street_name, city, state, zip_code = parse_address(new_customer.address)
        cur.execute(
            """
            UPDATE customer_address
            SET ca_street_number = ?, ca_street_name = ?,
                ca_city = ?, ca_state = ?, ca_zip = ?
            WHERE ca_address_sk = ?
            """,
            (street_number, street_name, city, state, zip_code, address_sk)
        )

    return True


def rent_item(item_id: str = None, customer_id: str = None):
    """
    item_id - A string containing the Item ID for the item being rented.
    customer_id - A string containing the customer id of the customer renting the item.
    """
    today = date.today()
    due = today + timedelta(days=14)
    cur.execute(
        """
        INSERT INTO rental (
            item_id,
            customer_id,
            rental_date,
            due_date
        ) VALUES (?, ?, ?, ?)
        """,
        (item_id, customer_id, str(today), str(due)),
    )



def waitlist_customer(item_id: str = None, customer_id: str = None) -> int:
    """
    Returns the customer's new place in line.
    """
    pos = line_length(item_id) + 1
    cur.execute(
        """
        INSERT INTO waitlist (item_id, customer_id, place_in_line)
        VALUES (?, ?, ?)
        """,
        (item_id, customer_id, pos),
    )
    return pos

def update_waitlist(item_id: str = None):
    """
    Removes person at position 1 and shifts everyone else down by 1.
    """
    cur.execute(
        "DELETE FROM waitlist WHERE item_id = ? AND place_in_line = 1",
        (item_id,),
    )
    cur.execute(
        "UPDATE waitlist SET place_in_line = place_in_line - 1 WHERE item_id = ? AND place_in_line > 1",
        (item_id,),
    )


def return_item(item_id: str = None, customer_id: str = None):
    """
    Moves a rental from rental to rental_history with return_date = today.
    """
    cur.execute(
        """
        SELECT rental_date, due_date FROM rental
        WHERE item_id = ? AND customer_id = ?
        """,
        (item_id, customer_id),
    )
    row = cur.fetchone()
    if row is None:
        return

    rental_date, due_date = row
    today = str(date.today())

    cur.execute(
        """
        INSERT INTO rental_history (
            item_id,
            customer_id,
            rental_date,
            due_date,
            return_date
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (item_id, customer_id, str(rental_date), str(due_date), today)
    )

    cur.execute(
        "DELETE FROM rental WHERE item_id = ? AND customer_id = ?",
        (item_id, customer_id)
    )



def grant_extension(item_id: str = None, customer_id: str = None):
    """
    Adds 14 days to the due_date.
    """
    cur.execute(
        """
        UPDATE rental
        SET due_date = DATE_ADD(due_date, INTERVAL 14 DAY)
        WHERE item_id = ? AND customer_id = ?
        """,
        (item_id, customer_id),
    )


def create_statement(column: str, use_patterns: bool) -> str:
    if use_patterns:
        return f"{column} LIKE ?"
    return f"{column} = ?"

def get_filtered_items(filter_attributes: Item = None,
                       use_patterns: bool = False,
                       min_price: float = -1,
                       max_price: float = -1,
                       min_start_year: int = -1,
                       max_start_year: int = -1) -> list[Item]:
    """
    Returns a list of Item objects matching the filters.
    """
    conditions = []
    parameters = []

    if filter_attributes.item_id is not None:
        conditions.append(create_statement("i_item_id", use_patterns))
        parameters.append(filter_attributes.item_id)
    if filter_attributes.product_name is not None:
        conditions.append(create_statement("i_product_name", use_patterns))
        parameters.append(filter_attributes.product_name)
    if filter_attributes.brand is not None:
        conditions.append(create_statement("i_brand", use_patterns))
        parameters.append(filter_attributes.brand)
    if filter_attributes.category is not None:
        conditions.append(create_statement("i_category", use_patterns))
        parameters.append(filter_attributes.category)
    if filter_attributes.manufact is not None:
        conditions.append(create_statement("i_manufact", use_patterns))
        parameters.append(filter_attributes.manufact)

    if filter_attributes.current_price != -1 and filter_attributes.current_price is not None:
        conditions.append("i_current_price = ?")
        parameters.append(filter_attributes.current_price)
    if filter_attributes.num_owned != -1 and filter_attributes.num_owned is not None:
        conditions.append("i_num_owned = ?")
        parameters.append(filter_attributes.num_owned)
    if filter_attributes.start_year != -1 and filter_attributes.start_year is not None:
        conditions.append("YEAR(i_rec_start_date) = ?")
        parameters.append(filter_attributes.start_year)

    if min_price != -1:
        conditions.append("i_current_price >= ?")
        parameters.append(min_price)
    if max_price != -1:
        conditions.append("i_current_price <= ?")
        parameters.append(max_price)
    if min_start_year != -1:
        conditions.append("YEAR(i_rec_start_date) >= ?")
        parameters.append(min_start_year)
    if max_start_year != -1:
        conditions.append("YEAR(i_rec_start_date) <= ?")
        parameters.append(max_start_year)

    sql = (
        "SELECT i_item_id, i_product_name, i_brand, i_category, i_manufact, "
        "i_current_price, YEAR(i_rec_start_date), i_num_owned FROM item"
    )
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    cur.execute(sql, parameters)
    items = []
    for row in cur.fetchall():
        items.append(
            Item(
                item_id=row[0].strip(),
                product_name=row[1].strip(),
                brand=row[2].strip(),
                category=row[3].strip(),
                manufact=row[4].strip(),
                current_price=float(row[5]) if row[5] is not None else -1,
                start_year=int(row[6]) if row[6] is not None else -1,
                num_owned=int(row[7]) if row[7] is not None else -1,
            )
        )
    return items


def get_filtered_customers(filter_attributes: Customer = None, use_patterns: bool = False) -> list[Customer]:
    """
    Returns a list of Customer objects matching the filters.
    """
    conditions = []
    parameters = []

    if filter_attributes.customer_id is not None:
        conditions.append(create_statement("c.c_customer_id", use_patterns))
        parameters.append(filter_attributes.customer_id)

    if filter_attributes.name is not None:
        if use_patterns:
            conditions.append(
                "CONCAT(c.c_first_name, ' ', c.c_last_name) LIKE ?"
            )
        else:
            conditions.append(
                "CONCAT(c.c_first_name, ' ', c.c_last_name) = ?"
            )
        parameters.append(filter_attributes.name)

    if filter_attributes.email is not None:
        conditions.append(create_statement("c.c_email_address", use_patterns))
        parameters.append(filter_attributes.email)

    if filter_attributes.address is not None:
        addrress_expression = (
            "CONCAT(ca.ca_street_number, ' ', ca.ca_street_name, ', ', ca.ca_city, ', ', ca.ca_state, ' ', ca.ca_zip)"
        )
        if use_patterns:
            conditions.append(f"{addrress_expression} LIKE ?")
        else:
            conditions.append(f"{addrress_expression} = ?")
        parameters.append(filter_attributes.address)

    sql = """
        SELECT c.c_customer_id,
               CONCAT(c.c_first_name, ' ', c.c_last_name) AS full_name,
               c.c_email_address,
               CASE WHEN ca.ca_address_sk IS NULL THEN NULL
                    ELSE CONCAT(ca.ca_street_number, ' ',
                                ca.ca_street_name, ', ',
                                ca.ca_city, ', ',
                                ca.ca_state, ' ',
                                ca.ca_zip)
               END AS full_address
        FROM customer c
        LEFT JOIN customer_address ca
               ON c.c_current_addr_sk = ca.ca_address_sk
    """
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    cur.execute(sql, parameters)
    customers = []
    for row in cur.fetchall():
        customers.append(
            Customer(
                customer_id=row[0].strip(),
                name=row[1].strip(),
                email=row[2].strip(),
                address=row[3].strip(),
            )
        )
    return customers


def get_filtered_rentals(filter_attributes: Rental = None,
                         min_rental_date: str = None,
                         max_rental_date: str = None,
                         min_due_date: str = None,
                         max_due_date: str = None) -> list[Rental]:
    """
    Returns a list of Rental objects matching the filters.
    """
    conditions = []
    parameters = []

    if filter_attributes.item_id is not None:
        conditions.append("item_id = ?")
        parameters.append(filter_attributes.item_id)
    if filter_attributes.customer_id is not None:
        conditions.append("customer_id = ?")
        parameters.append(filter_attributes.customer_id)
    if filter_attributes.rental_date is not None:
        conditions.append("rental_date = ?")
        parameters.append(filter_attributes.rental_date)
    if filter_attributes.due_date is not None:
        conditions.append("due_date = ?")
        parameters.append(filter_attributes.due_date)

    if min_rental_date is not None:
        conditions.append("rental_date >= ?")
        parameters.append(min_rental_date)
    if max_rental_date is not None:
        conditions.append("rental_date <= ?")
        parameters.append(max_rental_date)
    if min_due_date is not None:
        conditions.append("due_date >= ?")
        parameters.append(min_due_date)
    if max_due_date is not None:
        conditions.append("due_date <= ?")
        parameters.append(max_due_date)

    sql = "SELECT item_id, customer_id, rental_date, due_date FROM rental"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    cur.execute(sql, parameters)
    return [
        Rental(
            item_id=row[0].strip(),
            customer_id=row[1].strip(),
            rental_date=str(row[2]),
            due_date=str(row[3]),
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
    """
    Returns a list of RentalHistory objects matching the filters.
    """
    conditions = []
    parameters = []

    if filter_attributes.item_id is not None:
        conditions.append("item_id = ?")
        parameters.append(filter_attributes.item_id)
    if filter_attributes.customer_id is not None:
        conditions.append("customer_id = ?")
        parameters.append(filter_attributes.customer_id)
    if filter_attributes.rental_date is not None:
        conditions.append("rental_date = ?")
        parameters.append(filter_attributes.rental_date)
    if filter_attributes.due_date is not None:
        conditions.append("due_date = ?")
        parameters.append(filter_attributes.due_date)
    if filter_attributes.return_date is not None:
        conditions.append("return_date = ?")
        parameters.append(filter_attributes.return_date)

    if min_rental_date is not None:
        conditions.append("rental_date >= ?")
        parameters.append(min_rental_date)
    if max_rental_date is not None:
        conditions.append("rental_date <= ?")
        parameters.append(max_rental_date)
    if min_due_date is not None:
        conditions.append("due_date >= ?")
        parameters.append(min_due_date)
    if max_due_date is not None:
        conditions.append("due_date <= ?")
        parameters.append(max_due_date)
    if min_return_date is not None:
        conditions.append("return_date >= ?")
        parameters.append(min_return_date)
    if max_return_date is not None:
        conditions.append("return_date <= ?")
        parameters.append(max_return_date)

    sql = (
        "SELECT item_id, customer_id, rental_date, due_date, return_date "
        "FROM rental_history"
    )
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    cur.execute(sql, parameters)
    return [
        RentalHistory(
            item_id=row[0].strip(),
            customer_id=row[1].strip(),
            rental_date=str(row[2]),
            due_date=str(row[3]),
            return_date=str(row[4]),
        )
        for row in cur.fetchall()
    ]


def get_filtered_waitlist(filter_attributes: Waitlist = None,
                          min_place_in_line: int = -1,
                          max_place_in_line: int = -1) -> list[Waitlist]:
    """
    Returns a list of Waitlist objects matching the filters.
    """
    conditions = []
    parameters = []

    if filter_attributes.item_id is not None:
        conditions.append("item_id = ?")
        parameters.append(filter_attributes.item_id)
    if filter_attributes.customer_id is not None:
        conditions.append("customer_id = ?")
        parameters.append(filter_attributes.customer_id)
    if filter_attributes.place_in_line != -1 and filter_attributes.place_in_line is not None:
        conditions.append("place_in_line = ?")
        parameters.append(filter_attributes.place_in_line)

    if min_place_in_line != -1:
        conditions.append("place_in_line >= ?")
        parameters.append(min_place_in_line)
    if max_place_in_line != -1:
        conditions.append("place_in_line <= ?")
        parameters.append(max_place_in_line)

    sql = "SELECT item_id, customer_id, place_in_line FROM waitlist"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    cur.execute(sql, parameters)
    return [
        Waitlist(
            item_id=row[0].strip(),
            customer_id=row[1].strip(),
            place_in_line=int(row[2]),
        )
        for row in cur.fetchall()
    ]


def number_in_stock(item_id: str = None) -> int:
    """
    Returns num_owned - active rentals. Returns -1 if item doesn't exist.
    """
    cur.execute("SELECT i_num_owned FROM item WHERE i_item_id = ?", (item_id,))
    row = cur.fetchone()
    if row is None:
        return -1
    num_owned = row[0]

    cur.execute("SELECT COUNT(*) FROM rental WHERE item_id = ?", (item_id,))
    rented = cur.fetchone()[0]

    return int(num_owned) - int(rented)

def place_in_line(item_id: str = None, customer_id: str = None) -> int:
    """
    Returns the customer's place_in_line, or -1 if not on waitlist.
    """
    cur.execute(
        """
        SELECT place_in_line FROM waitlist
        WHERE item_id = ? AND customer_id = ?
        """,
        (item_id, customer_id),
    )
    row = cur.fetchone()
    if row is None:
        return -1

    return int(row[0])


def line_length(item_id: str = None) -> int:
    """
    Returns how many people are on the waitlist for this item.
    """
    cur.execute("SELECT COUNT(*) FROM waitlist WHERE item_id = ?", (item_id,))
    return int(cur.fetchone()[0])


def save_changes():
    """
    Commits all changes made to the db.
    """
    conn.commit()


def close_connection():
    """
    Closes the cursor and connection.
    """
    try:
        cur.close()
    finally:
        conn.close()


