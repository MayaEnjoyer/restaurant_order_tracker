# db.py
import os
from typing import List, Optional, Sequence, Tuple, Union

import bcrypt
import mysql.connector
from dotenv import load_dotenv
from mysql.connector import Error as MySQLError
from mysql.connector.errors import IntegrityError

# Load .env if present (DB creds, admin code/password)
load_dotenv()


class DatabaseManager:
    """
    Thin data-access layer around MySQL.

    Guarantees:
      - Exactly one admin is seeded on first run (username='admin').
      - Admin panel is guarded by a separate access code stored as a bcrypt hash in AppSettings.
      - Passwords and admin access code are stored hashed (bcrypt).
    """

    # ----------------- lifecycle -----------------
    def __init__(self):
        self.conn = mysql.connector.connect(
            host=os.getenv("DB_HOST", "127.0.0.1"),
            port=int(os.getenv("DB_PORT", "3307")),  # match your docker port mapping
            user=os.getenv("DB_USER", "restaurant_app"),
            password=os.getenv("DB_PASSWORD", "app_password"),
            database=os.getenv("DB_NAME", "restaurant"),
            auth_plugin="mysql_native_password",
        )
        self.cur = self.conn.cursor(buffered=True)
        self.current_user_id: Optional[int] = None
        self._ensure_schema()

    def close(self) -> None:
        try:
            if getattr(self, "cur", None):
                self.cur.close()
        finally:
            if getattr(self, "conn", None):
                self.conn.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    # ----------------- schema & bootstrap -----------------
    def _ensure_schema(self) -> None:
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS Users (
                user_id INT PRIMARY KEY AUTO_INCREMENT,
                username VARCHAR(50) NOT NULL UNIQUE,
                password_hash VARCHAR(100) NOT NULL,
                role VARCHAR(10) NOT NULL CHECK (role IN ('admin','user'))
            )
            """
        )

        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS MenuItems (
                item_id INT PRIMARY KEY AUTO_INCREMENT,
                name VARCHAR(100) NOT NULL UNIQUE,
                price DECIMAL(10,2) NOT NULL CHECK (price >= 0)
            )
            """
        )

        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS Orders (
                order_id INT PRIMARY KEY AUTO_INCREMENT,
                customer_name VARCHAR(100),
                customer_contact VARCHAR(100),
                order_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                status VARCHAR(20) NOT NULL DEFAULT 'Pending',
                user_id INT,
                CONSTRAINT fk_orders_user
                    FOREIGN KEY (user_id) REFERENCES Users(user_id)
                    ON DELETE SET NULL
            )
            """
        )

        # Keep RESTRICT on item_id so items used by orders cannot be deleted by mistake.
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS OrderItems (
                order_id INT NOT NULL,
                item_id INT NOT NULL,
                quantity INT NOT NULL CHECK (quantity > 0),
                PRIMARY KEY (order_id, item_id),
                CONSTRAINT fk_oi_order
                    FOREIGN KEY (order_id) REFERENCES Orders(order_id)
                    ON DELETE CASCADE,
                CONSTRAINT fk_oi_item
                    FOREIGN KEY (item_id) REFERENCES MenuItems(item_id)
                    ON DELETE RESTRICT
            )
            """
        )

        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS AppSettings (
                setting_key VARCHAR(64) PRIMARY KEY,
                setting_value VARCHAR(255) NOT NULL
            )
            """
        )

        self.conn.commit()
        self._bootstrap_admin()
        self._bootstrap_admin_access_code()

    def _bootstrap_admin(self) -> None:
        self.cur.execute("SELECT COUNT(*) FROM Users WHERE role='admin'")
        count_admin = self.cur.fetchone()[0]

        if count_admin == 0:
            default_pw = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin")
            pw_hash = bcrypt.hashpw(default_pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            self.cur.execute(
                "INSERT INTO Users (username, password_hash, role) VALUES (%s,%s,%s)",
                ("admin", pw_hash, "admin"),
            )
            self.conn.commit()
            print("Initialized default admin (username='admin', password='admin'). Change it ASAP.")
        elif count_admin > 1:
            print("WARNING: More than one admin exists. Please keep exactly one.")

    def _bootstrap_admin_access_code(self) -> None:
        self.cur.execute("SELECT setting_value FROM AppSettings WHERE setting_key='admin_access_code_hash'")
        row = self.cur.fetchone()
        if not row:
            raw = os.getenv("ADMIN_ACCESS_CODE", "ADMIN123")
            hashed = bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            self.cur.execute(
                "INSERT INTO AppSettings (setting_key, setting_value) VALUES ('admin_access_code_hash', %s)",
                (hashed,),
            )
            self.conn.commit()
            print("Initialized default admin access code 'ADMIN123'. Change it via AppSettings or UI.")

    # ----------------- auth & users -----------------
    def authenticate_user(self, username: str, password: str) -> Optional[Tuple[int, str, str]]:
        self.cur.execute(
            "SELECT user_id, username, password_hash, role FROM Users WHERE username=%s",
            (username,),
        )
        row = self.cur.fetchone()
        if not row:
            return None
        user_id, uname, pw_hash, role = row
        if bcrypt.checkpw(password.encode("utf-8"), pw_hash.encode("utf-8")):
            return user_id, uname, role
        return None

    def set_current_user(self, user_id: int) -> None:
        self.current_user_id = user_id

    def create_user(self, username: str, password: str, role: str = "user") -> int:
        if role == "admin":
            raise ValueError("Creating additional admins is not allowed.")
        pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        try:
            self.cur.execute(
                "INSERT INTO Users (username, password_hash, role) VALUES (%s,%s,%s)",
                (username, pw_hash, role),
            )
            self.conn.commit()
            return self.cur.lastrowid
        except IntegrityError as e:
            if getattr(e, "errno", None) == 1062:  # duplicate username
                raise ValueError("USERNAME_TAKEN")
            raise

    def change_user_password(self, user_id: int, old_password: str, new_password: str) -> None:
        self.cur.execute("SELECT password_hash FROM Users WHERE user_id=%s", (user_id,))
        row = self.cur.fetchone()
        if not row:
            raise ValueError("NO_SUCH_USER")
        if not bcrypt.checkpw(old_password.encode("utf-8"), row[0].encode("utf-8")):
            raise ValueError("WRONG_OLD_PASSWORD")
        new_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        self.cur.execute("UPDATE Users SET password_hash=%s WHERE user_id=%s", (new_hash, user_id))
        self.conn.commit()

    def verify_admin_access(self, code: str) -> bool:
        self.cur.execute("SELECT setting_value FROM AppSettings WHERE setting_key='admin_access_code_hash'")
        row = self.cur.fetchone()
        if not row:
            return False
        stored_hash = row[0]
        return bcrypt.checkpw(code.encode("utf-8"), stored_hash.encode("utf-8"))

    def change_admin_access_code(self, requester_role: str, new_code: str) -> None:
        if requester_role != "admin":
            raise PermissionError("Only admin can change the access code.")
        new_hash = bcrypt.hashpw(new_code.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        self.cur.execute(
            "UPDATE AppSettings SET setting_value=%s WHERE setting_key='admin_access_code_hash'",
            (new_hash,),
        )
        self.conn.commit()

    # ----------------- menu -----------------
    def get_menu_items(self) -> List[Tuple[int, str, float]]:
        self.cur.execute("SELECT item_id, name, price FROM MenuItems ORDER BY name ASC")
        return [(int(r[0]), r[1], float(r[2])) for r in self.cur.fetchall()]

    def add_menu_item(self, name: str, price: float) -> int:
        self.cur.execute("INSERT INTO MenuItems (name, price) VALUES (%s,%s)", (name, price))
        self.conn.commit()
        return int(self.cur.lastrowid)

    def update_menu_item(self, item_id: int, new_name: str, new_price: float) -> None:
        try:
            self.cur.execute(
                "UPDATE MenuItems SET name=%s, price=%s WHERE item_id=%s",
                (new_name, new_price, item_id),
            )
            self.conn.commit()
        except IntegrityError as e:
            if getattr(e, "errno", None) == 1062:
                raise ValueError("NAME_TAKEN")
            raise

    def delete_menu_item_by_name(self, name: str) -> None:
        """Will raise ValueError('ITEM_IN_USE') if FK restricts deletion."""
        try:
            self.cur.execute("DELETE FROM MenuItems WHERE name=%s", (name,))
            self.conn.commit()
        except MySQLError as e:
            raise ValueError("ITEM_IN_USE") from e

    # ----------------- orders -----------------
    def create_order(
        self,
        customer_name: str,
        customer_contact: str,
        items: Sequence[Union[Tuple[int, int], Tuple[int, str, int]]],
    ) -> int:
        if self.current_user_id is None:
            raise RuntimeError("No current user set before creating orders.")
        self.cur.execute(
            "INSERT INTO Orders (customer_name, customer_contact, status, user_id) VALUES (%s,%s,%s,%s)",
            (customer_name, customer_contact, "Pending", self.current_user_id),
        )
        order_id = int(self.cur.lastrowid)
        for tpl in items:
            if len(tpl) == 2:
                item_id, qty = tpl
            else:
                item_id, _name, qty = tpl
            self.cur.execute(
                "INSERT INTO OrderItems (order_id, item_id, quantity) VALUES (%s,%s,%s)",
                (order_id, int(item_id), int(qty)),
            )
        self.conn.commit()
        return order_id

    def get_all_orders(self) -> List[Tuple[int, str, str]]:
        self.cur.execute("SELECT order_id, customer_name, status FROM Orders ORDER BY order_date DESC")
        return [(int(r[0]), r[1] or "", r[2]) for r in self.cur.fetchall()]

    def update_order_status(self, order_id: Union[int, str], status: str) -> None:
        self.cur.execute("UPDATE Orders SET status=%s WHERE order_id=%s", (status, int(order_id)))
        self.conn.commit()

    def get_order_items(self, order_id: Union[int, str]) -> Tuple[List[Tuple[str, int, float, float]], float]:
        """
        Return (items, total) for an order.
        items: list of (item_name, quantity, unit_price, subtotal)
        """
        self.cur.execute(
            """
            SELECT mi.name, oi.quantity, mi.price, (oi.quantity * mi.price) AS subtotal
            FROM OrderItems oi
            JOIN MenuItems mi ON mi.item_id = oi.item_id
            WHERE oi.order_id = %s
            ORDER BY mi.name ASC
            """,
            (int(order_id),),
        )
        rows = self.cur.fetchall()
        items = [(r[0], int(r[1]), float(r[2]), float(r[3])) for r in rows]
        total = sum(x[3] for x in items)
        return items, total
