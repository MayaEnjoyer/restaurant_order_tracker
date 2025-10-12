import tkinter as tk
from tkinter import messagebox


class RegisterFrame(tk.Frame):
    """
    Registration form for regular users (role='user').
    On success: calls on_go_login() to return to Login.
    """
    def __init__(self, master, db_manager, on_go_login):
        super().__init__(master)
        self.db = db_manager
        self.on_go_login = on_go_login
        self._build()

    def _build(self):
        self.grid_columnconfigure(1, weight=1)

        title = tk.Label(self, text="Create Account", font=("Segoe UI", 16, "bold"))
        title.grid(row=0, column=0, columnspan=2, pady=(10, 20))

        tk.Label(self, text="Username:").grid(row=1, column=0, sticky="e", padx=8, pady=6)
        tk.Label(self, text="Password:").grid(row=2, column=0, sticky="e", padx=8, pady=6)
        tk.Label(self, text="Confirm:").grid(row=3, column=0, sticky="e", padx=8, pady=6)

        self.u = tk.StringVar()
        self.p1 = tk.StringVar()
        self.p2 = tk.StringVar()

        tk.Entry(self, textvariable=self.u).grid(row=1, column=1, sticky="ew", padx=8, pady=6)
        tk.Entry(self, textvariable=self.p1, show="*").grid(row=2, column=1, sticky="ew", padx=8, pady=6)
        tk.Entry(self, textvariable=self.p2, show="*").grid(row=3, column=1, sticky="ew", padx=8, pady=6)

        tk.Button(self, text="Create Account", command=self._register)\
            .grid(row=4, column=0, columnspan=2, pady=(10, 6), ipadx=12)
        tk.Button(self, text="Back to Login", command=self.on_go_login)\
            .grid(row=5, column=0, columnspan=2, pady=(2, 10))

        tk.Label(self, text="Only regular users can be registered. Admin is unique.",
                 fg="#666").grid(row=6, column=0, columnspan=2, pady=(0, 6))

    def _register(self):
        username = self.u.get().strip()
        p1 = self.p1.get()
        p2 = self.p2.get()

        if len(username) < 3:
            messagebox.showwarning("Invalid", "Username must be at least 3 characters.")
            return
        if len(p1) < 6:
            messagebox.showwarning("Invalid", "Password must be at least 6 characters.")
            return
        if p1 != p2:
            messagebox.showerror("Mismatch", "Passwords do not match.")
            return

        try:
            self.db.create_user(username, p1, role="user")
        except ValueError as e:
            if str(e) == "USERNAME_TAKEN":
                messagebox.showerror("Error", "This username is already taken.")
                return
            messagebox.showerror("Error", f"Could not create user: {e}")
            return

        messagebox.showinfo("Success", "Account created. You can now log in.")
        self.on_go_login()
