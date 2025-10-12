import tkinter as tk
from db import DatabaseManager
from ui.login_frame import LoginFrame
from ui.register_frame import RegisterFrame
from ui.main_app import MainApp


def main():
    db = DatabaseManager()
    root = tk.Tk()
    root.title("Restaurant Order Tracker")
    root.geometry("520x300")
    root.minsize(480, 280)

    def clear_root():
        for w in root.winfo_children():
            w.destroy()

    def show_login():
        clear_root()
        lf = LoginFrame(root, db_manager=db, on_success=on_login_success, on_go_register=show_register)
        lf.pack(fill="both", expand=True, padx=12, pady=12)

    def show_register():
        clear_root()
        rf = RegisterFrame(root, db_manager=db, on_go_login=show_login)
        rf.pack(fill="both", expand=True, padx=12, pady=12)

    def on_login_success(user_tuple):
        user_id, username, role = user_tuple
        db.set_current_user(user_id)
        clear_root()

        def do_logout():
            show_login()

        MainApp(root, db_manager=db, user_tuple=user_tuple, on_logout=do_logout)

    show_login()
    root.mainloop()


if __name__ == "__main__":
    main()
