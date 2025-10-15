# db.py
import os
from typing import List, Optional, Sequence, Tuple, Union, Dict

import bcrypt
import mysql.connector
from dotenv import load_dotenv
from mysql.connector.errors import IntegrityError, Error as MySQLError

load_dotenv()

OrderRow = Tuple[int, str, str, str, float]


class DatabaseManager:
    """
    Доступ к MySQL + миграции.
    Таблицы:
      - Users (единственный admin + обычные пользователи)
      - MenuCategories, MenuItems (с is_active)
      - OrderStatusRef (RECEIVED, IN_PROGRESS, READY, COMPLETED, CANCELED)
      - Orders (status_code, notes, user_id, service_type, delivery_address)
      - OrderItems (price_at_order — "снимок" цены на момент заказа)
      - AppSettings (admin/chef/courier access codes в хешах)
    """

    STATUS_FLOW: Dict[str, List[str]] = {
        "RECEIVED":    ["IN_PROGRESS", "CANCELED"],
        "IN_PROGRESS": ["READY", "CANCELED"],
        "READY":       ["COMPLETED", "CANCELED"],
        "COMPLETED":   [],
        "CANCELED":    [],
    }

    # ---------- lifecycle ----------
    def __init__(self):
        self.conn = mysql.connector.connect(
            host=os.getenv("DB_HOST", "127.0.0.1"),
            port=int(os.getenv("DB_PORT", "3307")),
            user=os.getenv("DB_USER", "restaurant_app"),
            password=os.getenv("DB_PASSWORD", "app_password"),
            database=os.getenv("DB_NAME", "restaurant"),
            auth_plugin="mysql_native_password",
        )
        # buffered=True — можно безопасно переиспользовать курсор
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

    # ---------- helpers ----------
    def _column_exists(self, table: str, column: str) -> bool:
        self.cur.execute(
            """
            SELECT COUNT(*) FROM information_schema.columns
            WHERE table_schema = DATABASE() AND table_name=%s AND column_name=%s
            """,
            (table, column),
        )
        return self.cur.fetchone()[0] > 0

    def _index_exists(self, table: str, index_name: str) -> bool:
        self.cur.execute(
            """
            SELECT COUNT(*) FROM information_schema.statistics
            WHERE table_schema = DATABASE() AND table_name=%s AND index_name=%s
            """,
            (table, index_name),
        )
        return self.cur.fetchone()[0] > 0

    def _create_index_if_missing(self, table: str, index_name: str, index_cols_sql: str) -> None:
        if not self._index_exists(table, index_name):
            self.cur.execute(f"CREATE INDEX {index_name} ON {table} {index_cols_sql}")
            self.conn.commit()

    def _create_or_replace_view(self, name: str, select_sql: str) -> None:
        self.cur.execute(f"DROP VIEW IF EXISTS {name}")
        self.cur.execute(f"CREATE VIEW {name} AS {select_sql}")
        self.conn.commit()

    def _add_column_if_missing(self, table: str, column: str, ddl_sql: str) -> None:
        """Удобный помощник для миграций."""
        if not self._column_exists(table, column):
            self.cur.execute(f"ALTER TABLE {table} ADD COLUMN {ddl_sql}")
            self.conn.commit()

    # ---------- schema & migrations ----------
    def _ensure_schema(self) -> None:
        # Users
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS Users (
                user_id INT PRIMARY KEY AUTO_INCREMENT,
                username VARCHAR(50) NOT NULL UNIQUE,
                password_hash VARCHAR(100) NOT NULL,
                role ENUM('admin','user') NOT NULL
            )
            """
        )

        # MenuCategories
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS MenuCategories (
                category_id INT PRIMARY KEY AUTO_INCREMENT,
                name VARCHAR(60) NOT NULL UNIQUE
            )
            """
        )

        # MenuItems (новая схема — с category_id и is_active)
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS MenuItems (
                item_id INT PRIMARY KEY AUTO_INCREMENT,
                category_id INT NOT NULL,
                name VARCHAR(100) NOT NULL UNIQUE,
                price DECIMAL(10,2) NOT NULL CHECK (price >= 0),
                is_active TINYINT(1) NOT NULL DEFAULT 1,
                CONSTRAINT fk_item_cat FOREIGN KEY (category_id)
                    REFERENCES MenuCategories(category_id) ON DELETE RESTRICT
            )
            """
        )

        # Справочник статусов
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS OrderStatusRef (
                status_code VARCHAR(20) PRIMARY KEY,
                sort_order INT NOT NULL
            )
            """
        )

        # Orders
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS Orders (
                order_id INT PRIMARY KEY AUTO_INCREMENT,
                customer_name VARCHAR(100),
                customer_contact VARCHAR(100),
                order_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                status_code VARCHAR(20) NOT NULL,
                user_id INT,
                notes VARCHAR(255),
                service_type ENUM('DINE_IN','TAKEAWAY','DELIVERY') DEFAULT 'TAKEAWAY',
                delivery_address VARCHAR(255) NULL,
                CONSTRAINT fk_orders_user FOREIGN KEY (user_id)
                    REFERENCES Users(user_id) ON DELETE SET NULL,
                CONSTRAINT fk_orders_status FOREIGN KEY (status_code)
                    REFERENCES OrderStatusRef(status_code) ON DELETE RESTRICT
            )
            """
        )

        # OrderItems (с "снимком" цены)
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS OrderItems (
                order_id INT NOT NULL,
                item_id INT NOT NULL,
                quantity INT NOT NULL CHECK (quantity > 0),
                price_at_order DECIMAL(10,2) NOT NULL,
                PRIMARY KEY (order_id, item_id),
                CONSTRAINT fk_oi_order FOREIGN KEY (order_id)
                    REFERENCES Orders(order_id) ON DELETE CASCADE,
                CONSTRAINT fk_oi_item FOREIGN KEY (item_id)
                    REFERENCES MenuItems(item_id) ON DELETE RESTRICT
            )
            """
        )

        # Настройки
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS AppSettings (
                setting_key VARCHAR(64) PRIMARY KEY,
                setting_value VARCHAR(255) NOT NULL
            )
            """
        )
        self.conn.commit()

        # ----- MIGRATIONS -----

        # 1) Гарантируем наличие категории General
        self.cur.execute("SELECT category_id FROM MenuCategories WHERE name=%s", ("General",))
        r = self.cur.fetchone()
        if r:
            general_id = int(r[0])
        else:
            self.cur.execute("INSERT INTO MenuCategories(name) VALUES ('General')")
            self.conn.commit()
            general_id = int(self.cur.lastrowid)

        # 2) MenuItems.category_id
        if not self._column_exists("MenuItems", "category_id"):
            self.cur.execute("ALTER TABLE MenuItems ADD COLUMN category_id INT NULL AFTER item_id")
            self.cur.execute("UPDATE MenuItems SET category_id=%s WHERE category_id IS NULL", (general_id,))
            self.conn.commit()
            self.cur.execute("ALTER TABLE MenuItems MODIFY category_id INT NOT NULL")
            try:
                self.cur.execute(
                    """
                    ALTER TABLE MenuItems
                    ADD CONSTRAINT fk_item_cat FOREIGN KEY (category_id)
                    REFERENCES MenuCategories(category_id) ON DELETE RESTRICT
                    """
                )
            except MySQLError:
                pass
            self.conn.commit()

        # 3) MenuItems.is_active
        self._add_column_if_missing("MenuItems", "is_active", "is_active TINYINT(1) NOT NULL DEFAULT 1 AFTER price")

        # 4) OrderItems.price_at_order
        if not self._column_exists("OrderItems", "price_at_order"):
            self.cur.execute(
                "ALTER TABLE OrderItems ADD COLUMN price_at_order DECIMAL(10,2) NOT NULL DEFAULT 0 AFTER quantity"
            )
            self.cur.execute(
                """
                UPDATE OrderItems oi
                JOIN MenuItems mi ON mi.item_id = oi.item_id
                SET oi.price_at_order = mi.price
                WHERE oi.price_at_order = 0
                """
            )
            self.conn.commit()

        # 5) Orders.status_code (миграция со старого поля status)
        if not self._column_exists("Orders", "status_code"):
            self.cur.execute(
                "ALTER TABLE Orders ADD COLUMN status_code VARCHAR(20) NOT NULL DEFAULT 'RECEIVED' AFTER order_date"
            )
            if self._column_exists("Orders", "status"):
                self.cur.execute(
                    """
                    UPDATE Orders
                    SET status_code = CASE
                        WHEN status IN ('Pending','RECEIVED')        THEN 'RECEIVED'
                        WHEN status IN ('In Progress','IN_PROGRESS')  THEN 'IN_PROGRESS'
                        WHEN status IN ('Ready','READY')              THEN 'READY'
                        WHEN status IN ('Completed','COMPLETED')      THEN 'COMPLETED'
                        WHEN status IN ('Canceled','CANCELED')        THEN 'CANCELED'
                        ELSE 'RECEIVED' END
                    """
                )
            self.conn.commit()

        # 6) Orders.notes
        self._add_column_if_missing("Orders", "notes", "notes VARCHAR(255)")

        # 7) Тип обслуживания и адрес доставки
        self._add_column_if_missing(
            "Orders",
            "service_type",
            "service_type ENUM('DINE_IN','TAKEAWAY','DELIVERY') DEFAULT 'TAKEAWAY'",
        )
        self._add_column_if_missing(
            "Orders",
            "delivery_address",
            "delivery_address VARCHAR(255) NULL",
        )

        # ----- seed -----
        self._bootstrap_admin()
        self._bootstrap_statuses()
        self._bootstrap_categories()
        self._bootstrap_admin_access_code()
        self._bootstrap_staff_access_codes()  # chef/courier codes

        # ----- view & indices -----
        self._create_or_replace_view(
            "v_order_totals",
            """
            SELECT o.order_id, COALESCE(SUM(oi.quantity * oi.price_at_order),0) AS total
            FROM Orders o
            LEFT JOIN OrderItems oi ON oi.order_id = o.order_id
            GROUP BY o.order_id
            """,
        )
        self._create_index_if_missing("Orders", "idx_orders_status_date", "(status_code, order_date)")
        self._create_index_if_missing("Orders", "idx_orders_user_date", "(user_id, order_date)")
        self._create_index_if_missing("MenuItems", "idx_menuitems_active", "(is_active, category_id)")

    # ---------- bootstrap ----------
    def _bootstrap_admin(self) -> None:
        self.cur.execute("SELECT COUNT(*) FROM Users WHERE role='admin'")
        if self.cur.fetchone()[0] == 0:
            default_pw = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin")
            pw_hash = bcrypt.hashpw(default_pw.encode(), bcrypt.gensalt()).decode()
            self.cur.execute(
                "INSERT INTO Users (username, password_hash, role) VALUES (%s,%s,%s)",
                ("admin", pw_hash, "admin"),
            )
            self.conn.commit()
            print("Seeded default admin (username='admin', password='admin'). Change it ASAP.")

    def _bootstrap_statuses(self) -> None:
        self.cur.execute("SELECT COUNT(*) FROM OrderStatusRef")
        if self.cur.fetchone()[0] == 0:
            rows = [
                ("RECEIVED", 1),
                ("IN_PROGRESS", 2),
                ("READY", 3),
                ("COMPLETED", 4),
                ("CANCELED", 5),
            ]
            self.cur.executemany("INSERT INTO OrderStatusRef (status_code, sort_order) VALUES (%s,%s)", rows)
            self.conn.commit()

    def _bootstrap_categories(self) -> None:
        self.cur.execute("SELECT COUNT(*) FROM MenuCategories")
        if self.cur.fetchone()[0] == 0:
            self.cur.executemany(
                "INSERT INTO MenuCategories (name) VALUES (%s)",
                [("Mains",), ("Drinks",), ("Desserts",)],
            )
            self.conn.commit()

    def _bootstrap_admin_access_code(self) -> None:
        self.cur.execute("SELECT setting_value FROM AppSettings WHERE setting_key='admin_access_code_hash'")
        row = self.cur.fetchone()
        if not row:
            raw = os.getenv("ADMIN_ACCESS_CODE", "ADMIN123")
            hashed = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
            self.cur.execute(
                "INSERT INTO AppSettings (setting_key, setting_value) VALUES ('admin_access_code_hash', %s)",
                (hashed,),
            )
            self.conn.commit()

    def _bootstrap_staff_access_codes(self) -> None:
        # CHEF
        self.cur.execute("SELECT setting_value FROM AppSettings WHERE setting_key='chef_access_code_hash'")
        if not self.cur.fetchone():
            raw = os.getenv("CHEF_ACCESS_CODE", "CHEF123")
            hashed = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
            self.cur.execute(
                "INSERT INTO AppSettings (setting_key, setting_value) VALUES ('chef_access_code_hash', %s)",
                (hashed,),
            )
            self.conn.commit()
        # COURIER
        self.cur.execute("SELECT setting_value FROM AppSettings WHERE setting_key='courier_access_code_hash'")
        if not self.cur.fetchone():
            raw = os.getenv("COURIER_ACCESS_CODE", "COURIER123")
            hashed = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
            self.cur.execute(
                "INSERT INTO AppSettings (setting_key, setting_value) VALUES ('courier_access_code_hash', %s)",
                (hashed,),
            )
            self.conn.commit()

    # ---------- auth / users ----------
    def authenticate_user(self, username: str, password: str) -> Optional[Tuple[int, str, str]]:
        self.cur.execute(
            "SELECT user_id, username, password_hash, role FROM Users WHERE username=%s",
            (username,),
        )
        row = self.cur.fetchone
        if callable(row):
            row = row()
        if not row:
            return None
        user_id, uname, pw_hash, role = row
        if bcrypt.checkpw(password.encode(), pw_hash.encode()):
            return int(user_id), uname, role
        return None

    def authenticate_admin_password(self, password: str) -> Optional[Tuple[int, str, str]]:
        """Вход админа только по паролю (username не спрашиваем)."""
        self.cur.execute("SELECT user_id, password_hash FROM Users WHERE role='admin' ORDER BY user_id LIMIT 1")
        row = self.cur.fetchone()
        if not row:
            return None
        uid, pw_hash = int(row[0]), row[1]
        if bcrypt.checkpw(password.encode(), pw_hash.encode()):
            return uid, "admin", "admin"
        return None

    def set_current_user(self, user_id: int) -> None:
        self.current_user_id = user_id

    def create_user(self, username: str, password: str, role: str = "user") -> int:
        if role == "admin":
            raise ValueError("Creating additional admins is not allowed.")
        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        try:
            self.cur.execute(
                "INSERT INTO Users (username, password_hash, role) VALUES (%s,%s,%s)",
                (username, pw_hash, role),
            )
            self.conn.commit()
            return int(self.cur.lastrowid)
        except IntegrityError as e:
            if getattr(e, "errno", None) == 1062:
                raise ValueError("USERNAME_TAKEN")
            raise

    def change_user_password(self, user_id: int, old_password: str, new_password: str) -> None:
        self.cur.execute("SELECT password_hash FROM Users WHERE user_id=%s", (int(user_id),))
        row = self.cur.fetchone()
        if not row:
            raise ValueError("NO_SUCH_USER")
        if not bcrypt.checkpw(old_password.encode(), row[0].encode()):
            raise ValueError("WRONG_OLD_PASSWORD")
        new_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        self.cur.execute("UPDATE Users SET password_hash=%s WHERE user_id=%s", (new_hash, int(user_id)))
        self.conn.commit()

    # ---------- role access codes ----------
    def _verify_code_by_key(self, key: str, code: str) -> bool:
        self.cur.execute("SELECT setting_value FROM AppSettings WHERE setting_key=%s", (key,))
        row = self.cur.fetchone()
        return bool(row and bcrypt.checkpw(code.encode(), row[0].encode()))

    def verify_admin_access(self, code: str) -> bool:
        return self._verify_code_by_key("admin_access_code_hash", code)

    def verify_chef_access(self, code: str) -> bool:
        return self._verify_code_by_key("chef_access_code_hash", code)

    def verify_courier_access(self, code: str) -> bool:
        return self._verify_code_by_key("courier_access_code_hash", code)

    def change_admin_access_code(self, requester_role: str, new_code: str) -> None:
        if requester_role != "admin":
            raise PermissionError("Only admin can change the access code.")
        new_hash = bcrypt.hashpw(new_code.encode(), bcrypt.gensalt()).decode()
        self.cur.execute(
            "UPDATE AppSettings SET setting_value=%s WHERE setting_key='admin_access_code_hash'",
            (new_hash,),
        )
        self.conn.commit()

    # ---------- categories ----------
    def get_categories(self) -> List[Tuple[int, str]]:
        self.cur.execute("SELECT category_id, name FROM MenuCategories ORDER BY name")
        return [(int(r[0]), r[1]) for r in self.cur.fetchall()]

    def add_category(self, name: str) -> int:
        try:
            self.cur.execute("INSERT INTO MenuCategories (name) VALUES (%s)", (name,))
            self.conn.commit()
            return int(self.cur.lastrowid)
        except IntegrityError as e:
            if getattr(e, "errno", None) == 1062:
                raise ValueError("CATEGORY_EXISTS")
            raise

    def delete_category(self, category_id: int) -> None:
        try:
            self.cur.execute("DELETE FROM MenuCategories WHERE category_id=%s", (int(category_id),))
            self.conn.commit()
        except MySQLError as e:
            if getattr(e, "errno", None) == 1451:
                raise ValueError("CATEGORY_IN_USE")
            raise

    # ---------- menu ----------
    def get_menu_items(
        self, category_id: Optional[int] = None, active_only: bool = True
    ) -> List[Tuple[int, str, float, int, bool]]:
        """Возвращает [(item_id, name, price, category_id, is_active), ...]"""
        sql = "SELECT item_id, name, price, category_id, is_active FROM MenuItems WHERE 1=1"
        params: List[Union[int, str]] = []
        if category_id is not None:
            sql += " AND category_id=%s"
            params.append(int(category_id))
        if active_only:
            sql += " AND is_active=1"
        sql += " ORDER BY name"
        self.cur.execute(sql, tuple(params))
        rows = self.cur.fetchall()
        return [(int(r[0]), r[1], float(r[2]), int(r[3]), bool(r[4])) for r in rows]

    def add_menu_item(self, name: str, price: float, category_id: int, is_active: bool = True) -> int:
        try:
            self.cur.execute(
                "INSERT INTO MenuItems (name, price, category_id, is_active) VALUES (%s,%s,%s,%s)",
                (name, price, int(category_id), 1 if is_active else 0),
            )
            self.conn.commit()
            return int(self.cur.lastrowid)
        except IntegrityError as e:
            if getattr(e, "errno", None) == 1062:
                raise ValueError("NAME_TAKEN")
            raise

    def update_menu_item(self, item_id: int, new_name: str, new_price: float, new_category_id: int, is_active: bool) -> None:
        try:
            self.cur.execute(
                "UPDATE MenuItems SET name=%s, price=%s, category_id=%s, is_active=%s WHERE item_id=%s",
                (new_name, new_price, int(new_category_id), 1 if is_active else 0, int(item_id)),
            )
            self.conn.commit()
        except IntegrityError as e:
            if getattr(e, "errno", None) == 1062:
                raise ValueError("NAME_TAKEN")
            raise

    def delete_menu_item_by_id(self, item_id: int) -> None:
        try:
            self.cur.execute("DELETE FROM MenuItems WHERE item_id=%s", (int(item_id),))
            self.conn.commit()
        except MySQLError as e:
            if getattr(e, "errno", None) == 1451:
                raise ValueError("ITEM_IN_USE")
            raise

    def delete_menu_item_by_name(self, name: str) -> None:
        try:
            self.cur.execute("DELETE FROM MenuItems WHERE name=%s", (name,))
            self.conn.commit()
        except MySQLError as e:
            if getattr(e, "errno", None) == 1451:
                raise ValueError("ITEM_IN_USE")
            raise

    def get_item_id_by_name(self, name: str) -> Optional[int]:
        """Найти item_id по точному имени (активность не важна)."""
        self.cur.execute("SELECT item_id FROM MenuItems WHERE name=%s LIMIT 1", (name,))
        r = self.cur.fetchone()
        return int(r[0]) if r else None

    # ---------- orders ----------
    def create_order(
        self,
        customer_name: str,
        customer_contact: str,
        items: Sequence[Tuple[int, int]],
        notes: str = "",
        service_type: Optional[str] = None,
        delivery_address: Optional[str] = None,
    ) -> int:
        """
        Создаёт заказ и его позиции.
        items: [(item_id, qty), ...]
        Для каждой позиции фиксируем текущую цену (price_at_order).
        """
        if self.current_user_id is None:
            raise RuntimeError("No current user set before creating orders.")

        stype = service_type or "TAKEAWAY"
        if not self._column_exists("Orders", "service_type"):
            # Совместимость со старыми БД — пишем тип обслуживания в notes
            extra = f" | Service: {stype}"
            if delivery_address:
                extra += f" | Delivery address: {delivery_address}"
            notes = (notes or "") + extra
            self.cur.execute(
                """
                INSERT INTO Orders (customer_name, customer_contact, order_date, status_code, user_id, notes)
                VALUES (%s,%s,NOW(),%s,%s,%s)
                """,
                (customer_name, customer_contact, "RECEIVED", self.current_user_id, notes),
            )
        else:
            self.cur.execute(
                """
                INSERT INTO Orders (customer_name, customer_contact, order_date, status_code, user_id, notes, service_type, delivery_address)
                VALUES (%s,%s,NOW(),%s,%s,%s,%s,%s)
                """,
                (customer_name, customer_contact, "RECEIVED", self.current_user_id, notes, stype, delivery_address),
            )

        order_id = int(self.cur.lastrowid)

        for item_id, qty in items:
            self.cur.execute("SELECT price FROM MenuItems WHERE item_id=%s", (int(item_id),))
            row = self.cur.fetchone()
            if not row:
                raise ValueError(f"Menu item {item_id} not found")
            price = float(row[0])
            self.cur.execute(
                "INSERT INTO OrderItems (order_id, item_id, quantity, price_at_order) VALUES (%s,%s,%s,%s)",
                (order_id, int(item_id), int(qty), price),
            )

        self.conn.commit()
        return order_id

    def replace_order_items(self, order_id: int, items: Sequence[Tuple[int, int]], requester_user_id: int) -> None:
        """
        Полностью заменить позиции заказа.
        Разрешено только:
          - если заказ принадлежит requester_user_id
          - и находится в статусе RECEIVED
        """
        self.cur.execute("SELECT user_id, status_code FROM Orders WHERE order_id=%s", (int(order_id),))
        row = self.cur.fetchone()
        if not row:
            raise ValueError("ORDER_NOT_FOUND")
        owner_id, status_code = (int(row[0]) if row[0] is not None else None), row[1]
        if owner_id != int(requester_user_id):
            raise PermissionError("You can edit only your own orders.")
        if status_code != "RECEIVED":
            raise ValueError("ONLY_RECEIVED_EDITABLE")

        self.cur.execute("DELETE FROM OrderItems WHERE order_id=%s", (int(order_id),))
        for item_id, qty in items:
            self.cur.execute("SELECT price FROM MenuItems WHERE item_id=%s", (int(item_id),))
            r = self.cur.fetchone()
            if not r:
                raise ValueError(f"Menu item {item_id} not found")
            price = float(r[0])
            self.cur.execute(
                "INSERT INTO OrderItems (order_id, item_id, quantity, price_at_order) VALUES (%s,%s,%s,%s)",
                (int(order_id), int(item_id), int(qty), price),
            )
        self.conn.commit()

    def get_orders(self, status: Optional[str] = None, search_text: str = "", limit: int = 200) -> List[OrderRow]:
        """Возвращает заказы (сумма приходит из вью v_order_totals)."""
        sql = """
        SELECT o.order_id, DATE_FORMAT(o.order_date, '%Y-%m-%d %H:%i'),
               COALESCE(o.customer_name,''), o.status_code, COALESCE(v.total,0)
        FROM Orders o
        LEFT JOIN v_order_totals v ON v.order_id = o.order_id
        WHERE 1=1
        """
        params: List[Union[str, int]] = []
        if status:
            sql += " AND o.status_code=%s"
            params.append(status)
        if search_text:
            like = f"%{search_text.strip()}%"
            sql += " AND (o.customer_name LIKE %s OR o.customer_contact LIKE %s OR o.notes LIKE %s)"
            params += [like, like, like]
        sql += " ORDER BY o.order_date DESC LIMIT %s"
        params.append(int(limit))
        self.cur.execute(sql, tuple(params))
        rows = self.cur.fetchall()
        return [(int(r[0]), r[1], r[2], r[3], float(r[4])) for r in rows]

    def get_orders_for_user(
        self,
        user_id: int,
        status: Optional[str] = None,
        search_text: str = "",
        limit: int = 400,
    ) -> List[OrderRow]:
        """Список заказов конкретного пользователя."""
        sql = """
        SELECT o.order_id, DATE_FORMAT(o.order_date, '%Y-%m-%d %H:%i'),
               COALESCE(o.customer_name,''), o.status_code, COALESCE(v.total,0)
        FROM Orders o
        LEFT JOIN v_order_totals v ON v.order_id = o.order_id
        WHERE o.user_id=%s
        """
        params: List[Union[str, int]] = [int(user_id)]
        if status:
            sql += " AND o.status_code=%s"
            params.append(status)
        if search_text:
            like = f"%{search_text.strip()}%"
            sql += " AND (o.customer_name LIKE %s OR o.customer_contact LIKE %s OR o.notes LIKE %s)"
            params += [like, like, like]
        sql += " ORDER BY o.order_date DESC LIMIT %s"
        params.append(int(limit))
        self.cur.execute(sql, tuple(params))
        rows = self.cur.fetchall()
        return [(int(r[0]), r[1], r[2], r[3], float(r[4])) for r in rows]

    # совместимость со старым кодом
    def get_all_orders(self) -> List[Tuple[int, str, str]]:
        self.cur.execute("SELECT order_id, customer_name, status_code FROM Orders ORDER BY order_date DESC")
        return [(int(r[0]), r[1] or "", r[2]) for r in self.cur.fetchall()]

    def get_order_items(self, order_id: Union[int, str]) -> Tuple[List[Tuple[str, int, float, float]], float]:
        """Возвращает (items, total) для заказа."""
        self.cur.execute(
            """
            SELECT mi.name, oi.quantity, oi.price_at_order, (oi.quantity * oi.price_at_order) AS subtotal
            FROM OrderItems oi
            JOIN MenuItems mi ON mi.item_id = oi.item_id
            WHERE oi.order_id=%s
            ORDER BY mi.name
            """,
            (int(order_id),),
        )
        rows = self.cur.fetchall()
        items = [(r[0], int(r[1]), float(r[2]), float(r[3])) for r in rows]
        total = sum(x[3] for x in items)
        return items, total

    def get_next_statuses(self, current_status: str) -> List[str]:
        return self.STATUS_FLOW.get(current_status, [])

    def update_order_status(self, order_id: Union[int, str], new_status: str) -> None:
        self.cur.execute("SELECT status_code FROM Orders WHERE order_id=%s", (int(order_id),))
        row = self.cur.fetchone()
        if not row:
            raise ValueError("ORDER_NOT_FOUND")
        current = row[0]
        # Правила переходов
        if new_status == "CANCELED":
            if current in ("COMPLETED", "CANCELED"):
                raise ValueError("INVALID_TRANSITION")
        elif new_status not in self.get_next_statuses(current):
            raise ValueError("INVALID_TRANSITION")
        self.cur.execute("UPDATE Orders SET status_code=%s WHERE order_id=%s", (new_status, int(order_id)))
        self.conn.commit()

    # ---------- user cancellation ----------
    def cancel_order_by_user(self, order_id: Union[int, str], requester_user_id: int) -> None:
        """
        Отмена заказа пользователем:
          - Разрешено только владельцу заказа
          - Разрешены статусы: RECEIVED / IN_PROGRESS / READY
        """
        self.cur.execute("SELECT user_id, status_code FROM Orders WHERE order_id=%s", (int(order_id),))
        row = self.cur.fetchone()
        if not row:
            raise ValueError("ORDER_NOT_FOUND")
        owner_id, status_code = (int(row[0]) if row[0] is not None else None), row[1]
        if owner_id != int(requester_user_id):
            raise PermissionError("You can cancel only your own orders.")
        if status_code not in ("RECEIVED", "IN_PROGRESS", "READY"):
            raise ValueError("CANNOT_CANCEL_THIS_STATUS")
        self.cur.execute("UPDATE Orders SET status_code='CANCELED' WHERE order_id=%s", (int(order_id),))
        self.conn.commit()

    # ---------- courier view ----------
    def get_delivery_orders(
        self,
        status: Optional[str] = None,
        search_text: str = "",
        limit: int = 400,
    ) -> List[Tuple[int, str, str, str, float, str]]:
        """
        Заказы типа DELIVERY (для курьера):
        -> [(order_id, date, customer, status, total, delivery_address)]
        """
        sql = """
        SELECT o.order_id,
               DATE_FORMAT(o.order_date, '%Y-%m-%d %H:%i'),
               COALESCE(o.customer_name,''),
               o.status_code,
               COALESCE(v.total,0),
               COALESCE(o.delivery_address,'')
        FROM Orders o
        LEFT JOIN v_order_totals v ON v.order_id = o.order_id
        WHERE o.service_type='DELIVERY'
        """
        params: List[Union[str, int]] = []
        if status:
            sql += " AND o.status_code=%s"
            params.append(status)
        if search_text:
            like = f"%{search_text.strip()}%"
            sql += " AND (o.customer_name LIKE %s OR o.customer_contact LIKE %s OR o.notes LIKE %s OR o.delivery_address LIKE %s)"
            params += [like, like, like, like]
        sql += " ORDER BY o.order_date DESC LIMIT %s"
        params.append(int(limit))
        self.cur.execute(sql, tuple(params))
        rows = self.cur.fetchall()
        return [(int(r[0]), r[1], r[2], r[3], float(r[4]), r[5]) for r in rows]

    # ---------- analytics ----------
    def get_status_list(self) -> List[str]:
        """Список кодов статусов в порядке sort_order (для UI-виджета)."""
        self.cur.execute("SELECT status_code FROM OrderStatusRef ORDER BY sort_order")
        return [r[0] for r in self.cur.fetchall()]

    def report_orders(
        self,
        start_dt: str,
        end_dt: str,
        statuses: Optional[List[str]] = None,
    ) -> List[Tuple[int, str, str, str, Optional[str], float]]:
        """
        Возвращает заказы за период:
        [(order_id, date, customer, status, service_type, total)]
        """
        have_service = self._column_exists("Orders", "service_type")
        service_sql = "o.service_type" if have_service else "NULL"

        sql = f"""
        SELECT o.order_id,
               DATE_FORMAT(o.order_date, '%Y-%m-%d %H:%i'),
               COALESCE(o.customer_name,''),
               o.status_code,
               {service_sql} AS service_type,
               COALESCE(v.total,0)
        FROM Orders o
        LEFT JOIN v_order_totals v ON v.order_id = o.order_id
        WHERE o.order_date BETWEEN %s AND %s
        """
        params: List[Union[str, int]] = [start_dt, end_dt]
        if statuses:
            sql += " AND o.status_code IN (" + ",".join(["%s"] * len(statuses)) + ")"
            params.extend(statuses)
        sql += " ORDER BY o.order_date DESC"
        self.cur.execute(sql, tuple(params))
        rows = self.cur.fetchall()
        # (oid, dt, customer, status, service, total)
        return [(int(r[0]), r[1], r[2], r[3], (r[4] if r[4] is not None else None), float(r[5])) for r in rows]

    def report_top_items(
        self,
        start_dt: str,
        end_dt: str,
        statuses: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[Tuple[str, int, float]]:
        """
        ТОП блюд за период (по количеству), с выручкой:
        [(item_name, qty, revenue)]
        """
        sql = """
        SELECT mi.name,
               SUM(oi.quantity) AS qty,
               SUM(oi.quantity * oi.price_at_order) AS revenue
        FROM OrderItems oi
        JOIN Orders o ON o.order_id = oi.order_id
        JOIN MenuItems mi ON mi.item_id = oi.item_id
        WHERE o.order_date BETWEEN %s AND %s
        """
        params: List[Union[str, int]] = [start_dt, end_dt]
        if statuses:
            sql += " AND o.status_code IN (" + ",".join(["%s"] * len(statuses)) + ")"
            params.extend(statuses)
        sql += " GROUP BY mi.name ORDER BY qty DESC, revenue DESC LIMIT %s"
        params.append(int(limit))
        self.cur.execute(sql, tuple(params))
        rows = self.cur.fetchall()
        return [(r[0], int(r[1]), float(r[2])) for r in rows]
