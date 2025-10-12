# src/util/reset_admin_password.py
import os
import bcrypt
import mysql.connector
from dotenv import load_dotenv

load_dotenv()  # возьмёт DB_HOST/PORT/USER/PASSWORD/NAME из .env, если он есть

cnx = mysql.connector.connect(
    host=os.getenv("DB_HOST", "127.0.0.1"),
    port=int(os.getenv("DB_PORT", "3307")),
    user=os.getenv("DB_USER", "restaurant_app"),
    password=os.getenv("DB_PASSWORD", "app_password"),
    database=os.getenv("DB_NAME", "restaurant"),
    auth_plugin="mysql_native_password",
)
cur = cnx.cursor()

new_pw = "rootpasswordilovemaya2003200716042007"
hash_ = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt()).decode()

cur.execute("UPDATE Users SET password_hash=%s WHERE role='admin' LIMIT 1", (hash_,))
cnx.commit()
print("Admin password reset OK.")

cur.close()
cnx.close()
