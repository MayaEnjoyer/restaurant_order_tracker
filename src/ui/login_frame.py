# ui/login_frame.py
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from typing import Optional, Tuple, Callable


class LoginFrame(tk.Frame):
    """
    Экран входа + ссылка на регистрацию.
    on_success(user_tuple) -> (user_id, username, role)
    on_go_register()       -> опциональный колбэк из main.py для показа окна регистрации.
                              Если не передан, используется встроенное RegisterFrame.
    """

    def __init__(
        self,
        master,
        db_manager,
        on_success: Callable[[Tuple[int, str, str]], None],
        on_go_register: Optional[Callable[[], None]] = None,
    ):
        super().__init__(master)
        self.db = db_manager
        self.on_success = on_success
        self.on_go_register = on_go_register

        self._build_login()

    # ---------------- UI ----------------
    def _build_login(self) -> None:
        self.pack(fill="both", expand=True)
        self.columnconfigure(0, weight=1)

        title = tk.Label(self, text="Restaurant Order Tracker", font=("Segoe UI", 16, "bold"))
        title.grid(row=0, column=0, pady=(18, 8))

        form = tk.Frame(self)
        form.grid(row=1, column=0, padx=18, pady=8, sticky="ew")
        form.grid_columnconfigure(1, weight=1)

        tk.Label(form, text="Username:").grid(row=0, column=0, sticky="e", padx=(0, 8), pady=6)
        tk.Label(form, text="Password:").grid(row=1, column=0, sticky="e", padx=(0, 8), pady=6)

        self.username = tk.StringVar()
        self.password = tk.StringVar()

        tk.Entry(form, textvariable=self.username).grid(row=0, column=1, sticky="ew", pady=6)
        tk.Entry(form, textvariable=self.password, show="*").grid(row=1, column=1, sticky="ew", pady=6)

        buttons = tk.Frame(self)
        buttons.grid(row=2, column=0, pady=(6, 2))

        ttk.Button(buttons, text="Login", command=self._login_user).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Login as Admin", command=self._login_as_admin).pack(side="left")

        footer = tk.Frame(self)
        footer.grid(row=3, column=0, pady=(10, 6))
        tk.Label(footer, text="No account?").pack(side="left")
        link = tk.Label(footer, text="Create one", fg="#1b6ac9", cursor="hand2")
        link.pack(side="left", padx=(4, 0))
        link.bind("<Button-1>", lambda _e: self._open_register())

    # ------------- handlers -------------
    def _login_user(self) -> None:
        u = self.username.get().strip()
        p = self.password.get()
        if not u or not p:
            messagebox.showwarning("Missing", "Enter username and password.")
            return

        user = self.db.authenticate_user(u, p)
        if not user:
            messagebox.showerror("Login failed", "Invalid username or password.")
            return

        self.on_success(user)

    def _login_as_admin(self) -> None:
        pw = simpledialog.askstring("Admin login", "Admin password:", show="*", parent=self)
        if pw is None:
            return
        user = self.db.authenticate_admin_password(pw)
        if not user:
            messagebox.showerror("Access denied", "Wrong admin password.")
            return
        self.on_success(user)

    def _open_register(self) -> None:
        """Либо вызываем колбэк из main.py, либо показываем встроенную форму регистрации."""
        if callable(self.on_go_register):
            self.on_go_register()
        else:
            RegisterFrame(self.master, self.db, self.on_success)
            self.destroy()


class RegisterFrame(tk.Frame):
    """Регистрация только обычных пользователей (role='user')."""

    def __init__(self, master, db_manager, on_success: Callable[[Tuple[int, str, str]], None]):
        super().__init__(master)
        self.db = db_manager
        self.on_success = on_success

        self.pack(fill="both", expand=True)
        self.columnconfigure(0, weight=1)

        tk.Label(self, text="Create Account", font=("Segoe UI", 16, "bold")).grid(row=0, column=0, pady=(18, 8))

        form = tk.Frame(self)
        form.grid(row=1, column=0, padx=18, pady=8, sticky="ew")
        form.grid_columnconfigure(1, weight=1)

        tk.Label(form, text="Username:").grid(row=0, column=0, sticky="e", padx=(0, 8), pady=6)
        tk.Label(form, text="Password:").grid(row=1, column=0, sticky="e", padx=(0, 8), pady=6)
        tk.Label(form, text="Confirm:").grid(row=2, column=0, sticky="e", padx=(0, 8), pady=6)

        self.username = tk.StringVar()
        self.password = tk.StringVar()
        self.confirm = tk.StringVar()

        tk.Entry(form, textvariable=self.username).grid(row=0, column=1, sticky="ew", pady=6)
        tk.Entry(form, textvariable=self.password, show="*").grid(row=1, column=1, sticky="ew", pady=6)
        tk.Entry(form, textvariable=self.confirm, show="*").grid(row=2, column=1, sticky="ew", pady=6)

        btns = tk.Frame(self)
        btns.grid(row=2, column=0, pady=(6, 2))
        ttk.Button(btns, text="Create Account", command=self._register).pack(side="left", padx=(0, 8))
        ttk.Button(btns, text="Back to Login", command=self._back).pack(side="left")

        tip = tk.Label(self, text="Only regular users can be registered. Admin is unique.", fg="#666")
        tip.grid(row=3, column=0, pady=(10, 6))

    def _register(self) -> None:
        u = self.username.get().strip()
        p = self.password.get()
        c = self.confirm.get()

        if len(u) < 3:
            messagebox.showwarning("Invalid", "Username must be at least 3 characters.")
            return
        if p != c or len(p) < 6:
            messagebox.showwarning("Invalid", "Passwords must match and be at least 6 characters.")
            return

        try:
            uid = self.db.create_user(u, p, role="user")
        except ValueError as e:
            if str(e) == "USERNAME_TAKEN":
                messagebox.showerror("Oops", "Username already taken.")
                return
            raise

        messagebox.showinfo("Done", "Account created. You can log in now.")
        self.on_success((uid, u, "user"))

    def _back(self) -> None:
        LoginFrame(self.master, self.db, self.on_success)  # без внешнего колбэка
        self.destroy()
