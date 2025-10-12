# ui/main_app.py
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from typing import Tuple, List, Optional


class MainApp(tk.Toplevel):
    """
    Главное окно приложения.

    Вкладки:
      • Orders — оформление нового заказа (категория → товары → корзина), список заказов,
                  фильтры по статусу и поиску, просмотр деталей, перевод статуса, отмена.
      • Admin  — (только после ввода Admin Access Code и только для роли admin)
                 управление меню (категории/позиции), а также диспетчер заказов.
    Аккаунт:
      • Смена пароля пользователем.
      • Смена Admin Access Code (только admin).
    """

    def __init__(self, master, db_manager, user_tuple: Tuple[int, str, str], on_logout):
        super().__init__(master)
        self.db = db_manager
        self.user_id, self.username, self.role = user_tuple
        self.on_logout = on_logout

        self.title("Restaurant Order Tracker")
        self.geometry("1100x700")
        self.minsize(1000, 640)

        self._build_shell()
        self._build_orders_tab()
        if self.role == "admin":
            self._maybe_add_admin_tab()

        self.protocol("WM_DELETE_WINDOW", self._logout)

    # ---------- Shell (верхняя панель, Notebook) ----------
    def _build_shell(self):
        topbar = tk.Frame(self)
        topbar.pack(fill="x")

        tk.Label(
            topbar, text=f"Signed in as: {self.username} ({self.role})", font=("Segoe UI", 10)
        ).pack(side="left", padx=10, pady=6)

        tk.Button(topbar, text="Change Password", command=self._change_password)\
            .pack(side="right", padx=(0, 8), pady=6)

        if self.role == "admin":
            tk.Button(topbar, text="Change Admin Code", command=self._change_admin_code)\
                .pack(side="right", padx=(0, 8), pady=6)

        tk.Button(topbar, text="Logout", command=self._logout)\
            .pack(side="right", padx=(0, 10), pady=6)

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)

    # ---------- Orders tab ----------
    def _build_orders_tab(self):
        self.orders_tab = tk.Frame(self.nb)
        self.nb.add(self.orders_tab, text="Orders")

        # ===== ЛЕВАЯ ПАНЕЛЬ: Новый заказ =====
        left = tk.LabelFrame(self.orders_tab, text="New Order")
        left.pack(side="left", fill="y", padx=10, pady=10)

        # Категории
        tk.Label(left, text="Category:").grid(row=0, column=0, sticky="w", padx=6, pady=(6, 2))
        self.categories = self.db.get_categories()  # -> List[(category_id, name)]
        self.cat_id_by_name = {name: cid for cid, name in self.categories}
        self.cat_sel = tk.StringVar()
        names = [name for _, name in self.categories]
        self.cat_combo = ttk.Combobox(
            left, textvariable=self.cat_sel, values=names, state="readonly", width=24
        )
        self.cat_combo.grid(row=1, column=0, padx=6, pady=(0, 6))
        self.cat_combo.bind("<<ComboboxSelected>>", lambda e: self._load_items_for_category())

        # Товары
        self.items_listbox = tk.Listbox(left, width=28, height=14)
        self.items_listbox.grid(row=2, column=0, padx=6, pady=(0, 6))

        # Количество + Добавить в корзину
        qty_row = tk.Frame(left)
        qty_row.grid(row=3, column=0, sticky="ew", padx=6, pady=(0, 6))
        tk.Label(qty_row, text="Qty:").pack(side="left")
        self.qty_var = tk.IntVar(value=1)
        tk.Spinbox(qty_row, from_=1, to=100, textvariable=self.qty_var, width=6)\
            .pack(side="left", padx=(4, 8))
        tk.Button(qty_row, text="Add to cart", command=self._cart_add).pack(side="left")

        # Корзина
        tk.Label(left, text="Cart:").grid(row=4, column=0, sticky="w", padx=6)
        self.cart_list = tk.Listbox(left, width=28, height=10)
        self.cart_list.grid(row=5, column=0, padx=6, pady=(0, 6))
        tk.Button(left, text="Remove selected", command=self._cart_remove)\
            .grid(row=6, column=0, padx=6, pady=(0, 10))

        # Инфо о клиенте
        tk.Label(left, text="Customer name:").grid(row=7, column=0, sticky="w", padx=6)
        self.customer_var = tk.StringVar()
        tk.Entry(left, textvariable=self.customer_var, width=28)\
            .grid(row=8, column=0, padx=6, pady=(0, 4))

        tk.Label(left, text="Contact:").grid(row=9, column=0, sticky="w", padx=6)
        self.contact_var = tk.StringVar()
        tk.Entry(left, textvariable=self.contact_var, width=28)\
            .grid(row=10, column=0, padx=6, pady=(0, 4))

        tk.Label(left, text="Notes:").grid(row=11, column=0, sticky="w", padx=6)
        self.notes_var = tk.StringVar()
        tk.Entry(left, textvariable=self.notes_var, width=28)\
            .grid(row=12, column=0, padx=6, pady=(0, 6))

        tk.Button(left, text="Place Order", command=self._place_order, width=24)\
            .grid(row=13, column=0, padx=6, pady=(0, 10))

        # ===== ПРАВАЯ ПАНЕЛЬ: Сетка заказов =====
        right = tk.LabelFrame(self.orders_tab, text="Existing Orders")
        right.pack(side="right", fill="both", expand=True, padx=10, pady=10)

        filters = tk.Frame(right)
        filters.pack(fill="x", padx=6, pady=4)

        tk.Label(filters, text="Status:").pack(side="left")
        self.statuses = ["", "RECEIVED", "IN_PROGRESS", "READY", "COMPLETED", "CANCELED"]
        self.status_sel = tk.StringVar(value="")
        ttk.Combobox(filters, textvariable=self.status_sel, values=self.statuses,
                     width=14, state="readonly").pack(side="left", padx=(4, 12))

        tk.Label(filters, text="Search:").pack(side="left")
        self.search_var = tk.StringVar()
        tk.Entry(filters, textvariable=self.search_var, width=26)\
            .pack(side="left", padx=(4, 8))
        tk.Button(filters, text="Apply", command=self._reload_orders)\
            .pack(side="left")

        cols = ("ID", "Date", "Customer", "Status", "Total")
        self.orders_tree = ttk.Treeview(right, columns=cols, show="headings", height=18)
        for c in cols:
            self.orders_tree.heading(c, text=c)
        self.orders_tree.column("ID", width=70, anchor="center")
        self.orders_tree.column("Date", width=150)
        self.orders_tree.column("Customer", width=220)
        self.orders_tree.column("Status", width=120, anchor="center")
        self.orders_tree.column("Total", width=90, anchor="e")
        self.orders_tree.pack(fill="both", expand=True, padx=6, pady=6)
        self.orders_tree.bind("<Double-1>", lambda e: self._view_order_details())

        btns = tk.Frame(right)
        btns.pack(fill="x", padx=6, pady=(0, 8))
        tk.Button(btns, text="Details", command=self._view_order_details).pack(side="left")
        tk.Button(btns, text="Next Status", command=self._advance_status).pack(side="left", padx=6)
        tk.Button(btns, text="Cancel", command=self._cancel_order).pack(side="left")
        tk.Button(btns, text="Refresh", command=self._reload_orders).pack(side="right")

        # Инициализация
        if names:
            self.cat_sel.set(names[0])
            self._load_items_for_category()
        self._reload_orders()

    # ---------- Orders helpers ----------
    def _load_items_for_category(self):
        """Загрузить товары выбранной категории в список."""
        self.items_listbox.delete(0, tk.END)
        self.items_cache = {}

        cat = self.cat_sel.get()
        if not cat:
            return
        cid = self.cat_id_by_name[cat]

        # Ожидается: get_menu_items(category_id=?, active_only=True)
        # -> List[(item_id, name, price, category_id, is_active)]
        items = self.db.get_menu_items(category_id=cid, active_only=True)
        self.items_cache = {f"{name} (${price:.2f})": (iid, price)
                            for iid, name, price, _cid, _act in items}
        for label in self.items_cache.keys():
            self.items_listbox.insert(tk.END, label)

    def _cart_add(self):
        sel = self.items_listbox.curselection()
        if not sel:
            return
        label = self.items_listbox.get(sel[0])
        qty = max(1, int(self.qty_var.get()))
        self.cart_list.insert(tk.END, f"{label} x {qty}")

    def _cart_remove(self):
        sel = list(self.cart_list.curselection())
        for i in reversed(sel):
            self.cart_list.delete(i)

    def _place_order(self):
        """Оформление заказа из корзины."""
        if self.cart_list.size() == 0:
            messagebox.showwarning("Cart is empty", "Add items to the cart first.")
            return

        items: List[Tuple[int, int]] = []
        for i in range(self.cart_list.size()):
            row = self.cart_list.get(i)  # "Pizza ($10.00) x 2"
            try:
                name_part, qty_str = row.rsplit(" x ", 1)
                item_id, _price = self.items_cache[name_part]
                items.append((item_id, int(qty_str)))
            except Exception:
                # Если строка неожиданного формата — пропустим её
                continue

        if not items:
            messagebox.showwarning("Cart is empty", "No valid items to place.")
            return

        try:
            oid = self.db.create_order(
                self.customer_var.get().strip(),
                self.contact_var.get().strip(),
                items,
                self.notes_var.get().strip(),
            )
        except Exception as e:
            messagebox.showerror("Order failed", str(e))
            return

        messagebox.showinfo("Success", f"Order #{oid} created (status: RECEIVED).")
        # Reset
        self.cart_list.delete(0, tk.END)
        self.customer_var.set("")
        self.contact_var.set("")
        self.notes_var.set("")
        self.qty_var.set(1)
        self._reload_orders()

    def _reload_orders(self):
        """Перезагрузить таблицу заказов справа с учётом фильтров."""
        for i in self.orders_tree.get_children():
            self.orders_tree.delete(i)

        status = self.status_sel.get() or None
        search = self.search_var.get()

        # Ожидается: get_orders(status: Optional[str], search_text: str, limit: int)
        # -> List[(order_id, order_date, customer_name, status, total)]
        for oid, dt, cust, st, total in self.db.get_orders(
            status=status, search_text=search, limit=400
        ):
            self.orders_tree.insert("", "end", values=(oid, dt, cust, st, f"{total:.2f}"))

    def _get_selected_order_id(self) -> Optional[int]:
        sel = self.orders_tree.focus()
        if not sel:
            return None
        return int(self.orders_tree.item(sel, "values")[0])

    def _view_order_details(self):
        oid = self._get_selected_order_id()
        if not oid:
            return
        # Ожидается: get_order_items(order_id) -> ([(name, qty, price, subtotal)], total)
        items, total = self.db.get_order_items(oid)

        win = tk.Toplevel(self)
        win.title(f"Order #{oid} details")
        win.geometry("560x380")
        win.transient(self)
        win.grab_set()

        cols = ("Item", "Qty", "Price", "Subtotal")
        tv = ttk.Treeview(win, columns=cols, show="headings")
        for c in cols:
            tv.heading(c, text=c)
        tv.column("Item", width=240)
        tv.column("Qty", width=60, anchor="center")
        tv.column("Price", width=100, anchor="e")
        tv.column("Subtotal", width=120, anchor="e")
        tv.pack(fill="both", expand=True, padx=10, pady=10)

        for name, qty, price, sub in items:
            tv.insert("", "end", values=(name, qty, f"{price:.2f}", f"{sub:.2f}"))

        tk.Label(win, text=f"Total: {total:.2f}", font=("Segoe UI", 11, "bold"))\
            .pack(anchor="e", padx=12, pady=(0, 10))
        tk.Button(win, text="Close", command=win.destroy).pack(pady=(0, 10))

    def _advance_status(self):
        oid = self._get_selected_order_id()
        if not oid:
            return

        st = self.orders_tree.item(self.orders_tree.focus(), "values")[3]
        nexts = self.db.get_next_statuses(st)  # -> List[str]
        if not nexts:
            messagebox.showinfo("No action", f"Status '{st}' has no next steps.")
            return

        choice = simpledialog.askstring(
            "Next Status", f"Choose: {', '.join(nexts)}", parent=self
        )
        if not choice or choice not in nexts:
            return

        try:
            self.db.update_order_status(oid, choice)
        except ValueError as e:
            messagebox.showerror("Error", str(e))
            return
        self._reload_orders()

    def _cancel_order(self):
        oid = self._get_selected_order_id()
        if not oid:
            return
        if not messagebox.askyesno("Cancel", "Cancel this order?"):
            return
        try:
            self.db.update_order_status(oid, "CANCELED")
        except ValueError as e:
            messagebox.showerror("Error", str(e))
            return
        self._reload_orders()

    # ---------- Admin Tab ----------
    def _maybe_add_admin_tab(self):
        code = simpledialog.askstring(
            "Admin Access", "Enter admin access code:", show="*", parent=self
        )
        if not code or not self.db.verify_admin_access(code):
            messagebox.showinfo("Access denied", "Admin area is locked.")
            return

        self.admin_tab = tk.Frame(self.nb)
        self.nb.add(self.admin_tab, text="Admin")

        self.admin_nb = ttk.Notebook(self.admin_tab)
        self.admin_nb.pack(fill="both", expand=True)

        self._build_admin_menu_tab()
        self._build_admin_orders_tab()

    # -------- Admin / Menu management --------
    def _build_admin_menu_tab(self):
        tab = tk.Frame(self.admin_nb)
        self.admin_nb.add(tab, text="Menu")

        left = tk.LabelFrame(tab, text="Item Editor")
        left.pack(side="left", fill="y", padx=10, pady=10)

        # Категория для редактируемых позиций
        tk.Label(left, text="Category:").grid(row=0, column=0, sticky="w", padx=6, pady=(8, 2))
        self.admin_categories = self.db.get_categories()
        self.admin_cat_by_name = {name: cid for cid, name in self.admin_categories}
        self.admin_cat_sel = tk.StringVar()
        cat_names = [n for _, n in self.admin_categories]
        self.admin_cat_combo = ttk.Combobox(
            left, textvariable=self.admin_cat_sel, values=cat_names, state="readonly", width=22
        )
        self.admin_cat_combo.grid(row=1, column=0, padx=6, pady=(0, 6))
        self.admin_cat_combo.bind("<<ComboboxSelected>>", lambda e: self._admin_refresh_items())

        # Управление категориями
        addc = tk.Frame(left)
        addc.grid(row=2, column=0, padx=6, pady=(0, 8), sticky="w")
        tk.Button(addc, text="Add Category", command=self._admin_add_category).pack(side="left")
        tk.Button(addc, text="Delete Category", command=self._admin_delete_category)\
            .pack(side="left", padx=(6, 0))

        # Поля позиции меню
        tk.Label(left, text="Item name:").grid(row=3, column=0, sticky="w", padx=6, pady=(6, 2))
        self.admin_item_name = tk.StringVar()
        tk.Entry(left, textvariable=self.admin_item_name, width=24)\
            .grid(row=4, column=0, padx=6, pady=(0, 6))

        tk.Label(left, text="Price:").grid(row=5, column=0, sticky="w", padx=6, pady=(6, 2))
        self.admin_item_price = tk.DoubleVar(value=0.0)
        tk.Entry(left, textvariable=self.admin_item_price, width=24)\
            .grid(row=6, column=0, padx=6, pady=(0, 6))

        self.admin_item_active = tk.IntVar(value=1)
        tk.Checkbutton(left, text="Active (available to order)", variable=self.admin_item_active)\
            .grid(row=7, column=0, sticky="w", padx=6, pady=(0, 6))

        tk.Button(left, text="Add Item", command=self._admin_add_item)\
            .grid(row=8, column=0, padx=6, pady=(4, 4))
        self.btn_admin_update = tk.Button(left, text="Update Item", state="disabled",
                                          command=self._admin_update_item)
        self.btn_admin_update.grid(row=9, column=0, padx=6, pady=(0, 4))
        tk.Button(left, text="Clear", command=self._admin_clear_item_form)\
            .grid(row=10, column=0, padx=6, pady=(0, 10))

        # Список позиций
        right = tk.LabelFrame(tab, text="Items")
        right.pack(side="right", fill="both", expand=True, padx=10, pady=10)
        self.admin_items_tree = ttk.Treeview(
            right, columns=("ID", "Name", "Price", "Active"), show="headings"
        )
        for c in ("ID", "Name", "Price", "Active"):
            self.admin_items_tree.heading(c, text=c)
        self.admin_items_tree.column("ID", width=60, anchor="center")
        self.admin_items_tree.column("Name", width=260)
        self.admin_items_tree.column("Price", width=120, anchor="e")
        self.admin_items_tree.column("Active", width=80, anchor="center")
        self.admin_items_tree.pack(fill="both", expand=True, padx=6, pady=6)
        self.admin_items_tree.bind("<ButtonRelease-1>", lambda e: self._admin_item_row_selected())

        if cat_names:
            self.admin_cat_sel.set(cat_names[0])
        self._admin_refresh_items()

    def _admin_refresh_items(self):
        """Обновить список позиций для выбранной категории (и синхронизировать левую вкладку Orders)."""
        for i in self.admin_items_tree.get_children():
            self.admin_items_tree.delete(i)

        cat = self.admin_cat_sel.get()
        if not cat:
            return
        cid = self.admin_cat_by_name[cat]

        # Ожидается: get_menu_items(category_id=?, active_only=False)
        # -> List[(item_id, name, price, category_id, is_active)]
        self.admin_items_cache = self.db.get_menu_items(category_id=cid, active_only=False)
        for iid, name, price, _cid, active in self.admin_items_cache:
            self.admin_items_tree.insert(
                "", "end", values=(iid, name, f"{price:.2f}", "Yes" if active else "No")
            )

        # Синхронизация вкладки Orders (категории и список)
        self.categories = self.db.get_categories()
        self.cat_id_by_name = {n: i for i, n in self.categories}
        self.cat_combo["values"] = [n for _, n in self.categories]
        if self.cat_sel.get() and self.cat_sel.get() in self.cat_id_by_name:
            self._load_items_for_category()

    def _admin_item_row_selected(self):
        sel = self.admin_items_tree.focus()
        if not sel:
            return
        iid, name, price, active = self.admin_items_tree.item(sel, "values")
        self.editing_item_id = int(iid)
        self.admin_item_name.set(name)
        self.admin_item_price.set(float(price))
        self.admin_item_active.set(1 if active == "Yes" else 0)
        self.btn_admin_update.config(state="normal")

    def _admin_clear_item_form(self):
        self.editing_item_id = None
        self.admin_item_name.set("")
        self.admin_item_price.set(0.0)
        self.admin_item_active.set(1)
        self.btn_admin_update.config(state="disabled")

    def _admin_add_category(self):
        name = simpledialog.askstring("New Category", "Category name:", parent=self)
        if not name:
            return
        try:
            # Ожидается: add_category(name) -> может бросить ValueError("CATEGORY_EXISTS")
            self.db.add_category(name.strip())
        except ValueError as e:
            if str(e) == "CATEGORY_EXISTS":
                messagebox.showerror("Error", "Category already exists.")
                return
            raise

        self.admin_categories = self.db.get_categories()
        self.admin_cat_by_name = {n: i for i, n in self.admin_categories}
        self.admin_cat_combo["values"] = [n for _, n in self.admin_categories]
        self.admin_cat_sel.set(name.strip())
        self._admin_refresh_items()

    def _admin_delete_category(self):
        cat = self.admin_cat_sel.get()
        if not cat:
            return
        cid = self.admin_cat_by_name[cat]
        if not messagebox.askyesno(
            "Delete Category", f"Delete category '{cat}'? Items must be moved/deleted first."
        ):
            return
        try:
            # Ожидается: delete_category(category_id) -> ValueError("CATEGORY_IN_USE") если есть позиции
            self.db.delete_category(cid)
        except ValueError as e:
            if str(e) == "CATEGORY_IN_USE":
                messagebox.showerror("Blocked", "Category has items. Move or delete them first.")
                return
            raise

        self.admin_categories = self.db.get_categories()
        self.admin_cat_by_name = {n: i for i, n in self.admin_categories}
        names = [n for _, n in self.admin_categories]
        self.admin_cat_combo["values"] = names
        self.admin_cat_sel.set(names[0] if names else "")
        self._admin_refresh_items()

    def _admin_add_item(self):
        cat = self.admin_cat_sel.get()
        if not cat:
            return
        cid = self.admin_cat_by_name[cat]
        name = self.admin_item_name.get().strip()
        try:
            price = float(self.admin_item_price.get())
        except Exception:
            messagebox.showerror("Error", "Price must be a number.")
            return
        if not name or price < 0:
            messagebox.showerror("Invalid", "Enter name and non-negative price.")
            return

        try:
            # Ожидается: add_menu_item(name, price, category_id, is_active) -> ValueError("NAME_TAKEN")
            self.db.add_menu_item(name, price, cid, bool(self.admin_item_active.get()))
        except ValueError as e:
            if str(e) == "NAME_TAKEN":
                messagebox.showerror("Error", "An item with this name already exists.")
                return
            raise

        self._admin_clear_item_form()
        self._admin_refresh_items()

    def _admin_update_item(self):
        if not getattr(self, "editing_item_id", None):
            return
        cat = self.admin_cat_sel.get()
        cid = self.admin_cat_by_name[cat]
        name = self.admin_item_name.get().strip()
        try:
            price = float(self.admin_item_price.get())
        except Exception:
            messagebox.showerror("Error", "Price must be a number.")
            return

        try:
            # Ожидается: update_menu_item(item_id, name, price, category_id, is_active)
            #            -> ValueError("NAME_TAKEN") при дубле имени
            self.db.update_menu_item(
                self.editing_item_id, name, price, cid, bool(self.admin_item_active.get())
            )
        except ValueError as e:
            if str(e) == "NAME_TAKEN":
                messagebox.showerror("Error", "Another item with this name already exists.")
                return
            raise

        self._admin_clear_item_form()
        self._admin_refresh_items()

    # -------- Admin / Orders management --------
    def _build_admin_orders_tab(self):
        tab = tk.Frame(self.admin_nb)
        self.admin_nb.add(tab, text="Orders")

        filter_bar = tk.Frame(tab)
        filter_bar.pack(fill="x", padx=10, pady=(10, 0))
        tk.Label(filter_bar, text="Status:").pack(side="left")
        self.admin_status_sel = tk.StringVar(value="")
        ttk.Combobox(
            filter_bar, textvariable=self.admin_status_sel,
            values=["", "RECEIVED", "IN_PROGRESS", "READY", "COMPLETED", "CANCELED"],
            width=14, state="readonly"
        ).pack(side="left", padx=(4, 10))
        tk.Label(filter_bar, text="Search:").pack(side="left")
        self.admin_search_var = tk.StringVar()
        tk.Entry(filter_bar, textvariable=self.admin_search_var, width=26)\
            .pack(side="left", padx=(4, 8))
        tk.Button(filter_bar, text="Apply", command=self._admin_reload_orders)\
            .pack(side="left")

        cols = ("ID", "Date", "Customer", "Status", "Total")
        self.admin_orders_tree = ttk.Treeview(tab, columns=cols, show="headings")
        for c in cols:
            self.admin_orders_tree.heading(c, text=c)
        self.admin_orders_tree.column("ID", width=70, anchor="center")
        self.admin_orders_tree.column("Date", width=150)
        self.admin_orders_tree.column("Customer", width=220)
        self.admin_orders_tree.column("Status", width=120, anchor="center")
        self.admin_orders_tree.column("Total", width=90, anchor="e")
        self.admin_orders_tree.pack(fill="both", expand=True, padx=10, pady=10)
        self.admin_orders_tree.bind("<Double-1>", lambda e: self._view_order_details_admin())

        btns = tk.Frame(tab)
        btns.pack(fill="x", padx=10, pady=(0, 10))
        tk.Button(btns, text="Details", command=self._view_order_details_admin).pack(side="left")
        tk.Button(btns, text="Advance", command=self._admin_advance_status).pack(side="left", padx=6)
        tk.Button(btns, text="Cancel", command=self._admin_cancel_order).pack(side="left")
        tk.Button(btns, text="Refresh", command=self._admin_reload_orders).pack(side="right")

        self._admin_reload_orders()

    def _admin_reload_orders(self):
        for i in self.admin_orders_tree.get_children():
            self.admin_orders_tree.delete(i)
        status = self.admin_status_sel.get() or None
        search = self.admin_search_var.get()
        for oid, dt, cust, st, total in self.db.get_orders(status=status, search_text=search, limit=600):
            self.admin_orders_tree.insert("", "end", values=(oid, dt, cust, st, f"{total:.2f}"))

    def _view_order_details_admin(self):
        sel = self.admin_orders_tree.focus()
        if not sel:
            return
        oid = int(self.admin_orders_tree.item(sel, "values")[0])
        items, total = self.db.get_order_items(oid)

        win = tk.Toplevel(self)
        win.title(f"Order #{oid}")
        win.geometry("560x380")
        win.transient(self)
        win.grab_set()

        cols = ("Item", "Qty", "Price", "Subtotal")
        tv = ttk.Treeview(win, columns=cols, show="headings")
        for c in cols:
            tv.heading(c, text=c)
        tv.column("Item", width=240)
        tv.column("Qty", width=60, anchor="center")
        tv.column("Price", width=100, anchor="e")
        tv.column("Subtotal", width=120, anchor="e")
        tv.pack(fill="both", expand=True, padx=10, pady=10)
        for name, qty, price, sub in items:
            tv.insert("", "end", values=(name, qty, f"{price:.2f}", f"{sub:.2f}"))
        tk.Label(win, text=f"Total: {total:.2f}", font=("Segoe UI", 11, "bold"))\
            .pack(anchor="e", padx=12, pady=(0, 10))
        tk.Button(win, text="Close", command=win.destroy).pack(pady=(0, 10))

    def _admin_selected_order(self) -> Tuple[int, str]:
        sel = self.admin_orders_tree.focus()
        if not sel:
            return 0, ""
        vals = self.admin_orders_tree.item(sel, "values")
        return int(vals[0]), vals[3]

    def _admin_advance_status(self):
        oid, st = self._admin_selected_order()
        if not oid:
            return
        nexts = self.db.get_next_statuses(st)
        if not nexts:
            messagebox.showinfo("No action", f"'{st}' has no next steps.")
            return
        choice = simpledialog.askstring("Advance", f"Next: {', '.join(nexts)}", parent=self)
        if not choice or choice not in nexts:
            return
        try:
            self.db.update_order_status(oid, choice)
        except ValueError as e:
            messagebox.showerror("Error", str(e))
            return
        self._admin_reload_orders()

    def _admin_cancel_order(self):
        oid, _st = self._admin_selected_order()
        if not oid:
            return
        if not messagebox.askyesno("Cancel", f"Cancel order #{oid}?"):
            return
        try:
            self.db.update_order_status(oid, "CANCELED")
        except ValueError as e:
            messagebox.showerror("Error", str(e))
            return
        self._admin_reload_orders()

    # ---------- Account ----------
    def _change_password(self):
        old = simpledialog.askstring("Change Password", "Current password:", show="*", parent=self)
        if old is None:
            return
        new1 = simpledialog.askstring("Change Password", "New password:", show="*", parent=self)
        if new1 is None:
            return
        new2 = simpledialog.askstring("Change Password", "Repeat new password:", show="*", parent=self)
        if new2 is None:
            return
        if len(new1) < 6 or new1 != new2:
            messagebox.showerror("Error", "Passwords must match and be ≥ 6 chars.")
            return
        try:
            self.db.change_user_password(self.user_id, old, new1)
            messagebox.showinfo("Done", "Password changed.")
        except ValueError as e:
            messagebox.showerror("Error", str(e))

    def _change_admin_code(self):
        if getattr(self, "role", "") != "admin":
            return
        new1 = simpledialog.askstring("Admin Access Code", "New code:", show="*", parent=self)
        if new1 is None:
            return
        new2 = simpledialog.askstring("Admin Access Code", "Repeat code:", show="*", parent=self)
        if new2 is None:
            return
        if new1 != new2 or len(new1) < 4:
            messagebox.showerror("Error", "Codes must match and be ≥ 4 chars.")
            return
        try:
            self.db.change_admin_access_code(self.role, new1)
            messagebox.showinfo("Done", "Admin access code updated.")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    # ---------- lifecycle ----------
    def _logout(self):
        try:
            self.on_logout()
        finally:
            self.destroy()
