# src/util/seed_demo_data.py
import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

cnx = mysql.connector.connect(
    host=os.getenv("DB_HOST", "127.0.0.1"),
    port=int(os.getenv("DB_PORT", "3307")),
    user=os.getenv("DB_USER", "restaurant_app"),
    password=os.getenv("DB_PASSWORD", "app_password"),
    database=os.getenv("DB_NAME", "restaurant"),
    auth_plugin="mysql_native_password",
)
cur = cnx.cursor(buffered=True)

def exec_ddl(sql: str):
    cur.execute(sql)
    cnx.commit()

def table_exists(name: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = DATABASE() AND table_name = %s",
        (name,),
    )
    return cur.fetchone()[0] > 0

def column_exists(table: str, col: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
        (table, col),
    )
    return cur.fetchone()[0] > 0

def index_exists(table: str, index_name: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.statistics "
        "WHERE table_schema = DATABASE() AND table_name = %s AND index_name = %s",
        (table, index_name),
    )
    return cur.fetchone()[0] > 0

def referenced_category_table_from_fk() -> str | None:
    cur.execute(
        "SELECT REFERENCED_TABLE_NAME "
        "FROM information_schema.KEY_COLUMN_USAGE "
        "WHERE table_schema = DATABASE() "
        "  AND table_name = 'MenuItems' "
        "  AND column_name = 'category_id' "
        "  AND REFERENCED_TABLE_NAME IS NOT NULL "
        "LIMIT 1"
    )
    row = cur.fetchone()
    return row[0] if row else None

# ---------- 1) Определяем / создаём таблицу категорий ----------
cat_table = referenced_category_table_from_fk()
if not cat_table:
    # если FK не найден, выбираем приоритетно MenuCategories, иначе Categories, иначе создаём MenuCategories
    if table_exists("MenuCategories"):
        cat_table = "MenuCategories"
    elif table_exists("Categories"):
        cat_table = "Categories"
    else:
        cat_table = "MenuCategories"
        exec_ddl("""
        CREATE TABLE IF NOT EXISTS MenuCategories (
            category_id INT PRIMARY KEY AUTO_INCREMENT,
            name VARCHAR(100) NOT NULL UNIQUE
        )
        """)

# если выбранной таблицы нет — создадим
if not table_exists(cat_table):
    exec_ddl(f"""
    CREATE TABLE {cat_table} (
        category_id INT PRIMARY KEY AUTO_INCREMENT,
        name VARCHAR(100) NOT NULL UNIQUE
    )
    """)

# ---------- 2) Гарантируем колонки в MenuItems ----------
if not column_exists("MenuItems", "is_active"):
    exec_ddl("ALTER TABLE MenuItems ADD COLUMN is_active TINYINT(1) NOT NULL DEFAULT 1")
if not column_exists("MenuItems", "category_id"):
    exec_ddl("ALTER TABLE MenuItems ADD COLUMN category_id INT NULL")

# Индекс (is_active, category_id) — удобно для выборок
if not index_exists("MenuItems", "idx_menuitems_active"):
    exec_ddl("CREATE INDEX idx_menuitems_active ON MenuItems (is_active, category_id)")

# ---------- 3) Гарантируем FK MenuItems -> <cat_table> ----------
# Сначала убедимся, что существует хотя бы одна категория 'General'
cur.execute(f"SELECT category_id FROM {cat_table} WHERE name='General'")
row = cur.fetchone()
if not row:
    exec_ddl(f"INSERT INTO {cat_table}(name) VALUES ('General')")
    cur.execute(f"SELECT category_id FROM {cat_table} WHERE name='General'")
    row = cur.fetchone()
general_id = int(row[0])

# Заполним NULL category_id у существующих товаров
exec_ddl(f"UPDATE MenuItems SET category_id={general_id} WHERE category_id IS NULL")

# Если уже есть какой-то FK — оставляем. Если нет — добавим.
cur.execute(
    "SELECT COUNT(*) FROM information_schema.KEY_COLUMN_USAGE "
    "WHERE table_schema = DATABASE() "
    "  AND table_name = 'MenuItems' "
    "  AND column_name = 'category_id' "
    "  AND referenced_table_name IS NOT NULL"
)
has_fk = cur.fetchone()[0] > 0

if not has_fk:
    # имя FK используем единообразное
    try:
        exec_ddl(f"""
        ALTER TABLE MenuItems
          ADD CONSTRAINT fk_item_cat
          FOREIGN KEY (category_id) REFERENCES {cat_table}(category_id)
          ON DELETE RESTRICT
        """)
    except mysql.connector.Error:
        pass  # если вдруг параллельно уже создали

# ---------- 4) UPSERT-утилиты ----------
def upsert_category(name: str) -> int:
    cur.execute(f"SELECT category_id FROM {cat_table} WHERE name=%s", (name,))
    row = cur.fetchone()
    if row:
        return int(row[0])
    cur.execute(f"INSERT INTO {cat_table}(name) VALUES (%s)", (name,))
    cnx.commit()
    return int(cur.lastrowid)

def upsert_item(name: str, price: float, category_id: int, is_active: bool = True):
    cur.execute("SELECT item_id FROM MenuItems WHERE name=%s", (name,))
    row = cur.fetchone()
    if row:
        cur.execute(
            "UPDATE MenuItems SET price=%s, category_id=%s, is_active=%s WHERE item_id=%s",
            (price, category_id, 1 if is_active else 0, int(row[0])),
        )
    else:
        cur.execute(
            "INSERT INTO MenuItems(name, price, category_id, is_active) VALUES (%s,%s,%s,%s)",
            (name, price, category_id, 1 if is_active else 0),
        )
    cnx.commit()

cats = {
    "General": upsert_category("General"),
    "Pizza": upsert_category("Pizza"),
    "Drinks": upsert_category("Drinks"),
    "Desserts": upsert_category("Desserts"),
}

items = [
    ("Margherita", 7.90, "Pizza"),
    ("Pepperoni", 8.90, "Pizza"),
    ("Four Cheese", 9.90, "Pizza"),
    ("Coke 0.5L", 1.80, "Drinks"),
    ("Orange Juice", 2.50, "Drinks"),
    ("Cheesecake", 3.90, "Desserts"),
    ("Brownie", 3.50, "Desserts"),
    ("Daily Soup", 4.20, "General"),
]

for name, price, cat_name in items:
    upsert_item(name, price, cats[cat_name], True)

print(f"Schema aligned. Categories table = {cat_table}. Demo data seeded ✔")

cur.close()
cnx.close()
