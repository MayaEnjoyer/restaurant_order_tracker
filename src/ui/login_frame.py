import tkinter as tk
from tkinter import messagebox


class LoginFrame(tk.Frame):
    """
    Simple login frame.
    On success -> calls on_success(user_tuple)
    'Create one' -> calls on_go_register()
    """
    def __init__(self, master, db_manager, on_success, on_go_register):
        super().__init__(master)
        self.db = db_manager
        self.on_success = on_success
        self.on_go_register = on_go_register
        self._build()

    def _build(self):
        self.grid_columnconfigure(1, weight=1)

        title = tk.Label(self, text="Restaurant Order Tracker", font=("Segoe UI", 16, "bold"))
        title.grid(row=0, column=0, columnspan=2, pady=(10, 20))

        tk.Label(self, text="Username:").grid(row=1, column=0, sticky="e", padx=8, pady=6)
        tk.Label(self, text="Password:").grid(row=2, column=0, sticky="e", padx=8, pady=6)

        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()

        tk.Entry(self, textvariable=self.username_var).grid(row=1, column=1, sticky="ew", padx=8, pady=6)
        tk.Entry(self, textvariable=self.password_var, show="*").grid(row=2, column=1, sticky="ew", padx=8, pady=6)

        tk.Button(self, text="Login", command=self._attempt_login)\
            .grid(row=3, column=0, columnspan=2, pady=(10, 6), ipadx=12)

        nav = tk.Frame(self)
        nav.grid(row=4, column=0, columnspan=2)
        tk.Label(nav, text="No account?").pack(side="left", padx=(0, 4))
        tk.Button(nav, text="Create one", command=self.on_go_register,
                  relief="flat", fg="#1565c0", cursor="hand2")\
            .pack(side="left")

    def _attempt_login(self):
        username = self.username_var.get().strip()
        password = self.password_var.get()
        if not username or not password:
            messagebox.showwarning("Missing data", "Enter both username and password.")
            return
        user = self.db.authenticate_user(username, password)
        if not user:
            messagebox.showerror("Login failed", "Invalid credentials.")
            return
        self.on_success(user)  # (user_id, username, role)
