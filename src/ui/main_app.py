# ui/main_app.py
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from typing import Tuple, List, Optional
from datetime import datetime, timedelta
import csv


class MainApp(tk.Toplevel):
    """
    USER:
      - Ліва панель: кошик і створення замовлення (DINE_IN/TAKEAWAY/DELIVERY).
      - Права панель 'My Orders' з переглядом і відміною СВОГО замовлення.

    ADMIN:
      - Після входу під адміном запитуємо:
          1) Admin Access Code
          2) Другий код (admin / chef / courier)
        Відповідно відкривається вкладка(и) всередині Admin.
    """

    # --------------------------------------------------------------------- init
    def __init__(self, master, db_manager, user_tuple: Tuple[int, str, str], on_logout):
        super().__init__(master)
        self.db = db_manager
        self.user_id, self.username, self.role = user_tuple
        self.on_logout = on_logout

        self.title("Restaurant Order Tracker")
        self.geometry("1100x700")
        self.minsize(1000, 640)

        self._user_right_visible = False
        self.admin_tab = None
        self.admin_nb = None

        self._build_shell()
        self._build_orders_tab()

        if self.role == "admin":
            self._maybe_add_admin_tab()  # подвійний код і відкриття потрібної вкладки

        self.protocol("WM_DELETE_WINDOW", self._logout)

    # --------------------------------------------------------------- shell/topbar
    def _build_shell(self):
        topbar = tk.Frame(self)
        topbar.pack(fill="x")

        tk.Label(
            topbar,
            text=f"Signed in as: {self.username} ({self.role})",
            font=("Segoe UI", 10),
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

    # --------------------------------------------------------------- Orders tab
    def _build_orders_tab(self):
        self.orders_tab = tk.Frame(self.nb)
        self.nb.add(self.orders_tab, text="Orders")

        # ----------------------------- Left pane: New Order
        left = tk.LabelFrame(self.orders_tab, text="New Order")
        left.pack(side="left", fill="y", padx=10, pady=10)

        # Categories
        tk.Label(left, text="Category:").grid(row=0, column=0, sticky="w", padx=6, pady=(6, 2))
        self.categories = self.db.get_categories()
        self.cat_id_by_name = {name: cid for cid, name in self.categories}
        self.cat_sel = tk.StringVar()
        cat_names = [name for _, name in self.categories]
        self.cat_combo = ttk.Combobox(left, textvariable=self.cat_sel, values=cat_names,
                                      state="readonly", width=24)
        self.cat_combo.grid(row=1, column=0, padx=6, pady=(0, 6))
        self.cat_combo.bind("<<ComboboxSelected>>", lambda e: self._load_items_for_category())

        # Items list
        self.items_listbox = tk.Listbox(left, width=28, height=14)
        self.items_listbox.grid(row=2, column=0, padx=6, pady=(0, 6))

        # Qty + Add
        qty_row = tk.Frame(left)
        qty_row.grid(row=3, column=0, sticky="ew", padx=6, pady=(0, 6))
        tk.Label(qty_row, text="Qty:").pack(side="left")
        self.qty_var = tk.IntVar(value=1)
        tk.Spinbox(qty_row, from_=1, to=100, textvariable=self.qty_var, width=6)\
            .pack(side="left", padx=(4, 8))
        tk.Button(qty_row, text="Add to cart", command=self._cart_add)\
            .pack(side="left")

        # Cart
        tk.Label(left, text="Cart:").grid(row=4, column=0, sticky="w", padx=6)
        self.cart_list = tk.Listbox(left, width=28, height=10)
        self.cart_list.grid(row=5, column=0, padx=6, pady=(0, 6))

        row_btns = tk.Frame(left)
        row_btns.grid(row=6, column=0, sticky="ew", padx=6, pady=(0, 8))
        tk.Button(row_btns, text="Remove selected", command=self._cart_remove)\
            .pack(side="left")
        tk.Button(row_btns, text="Create Order...", command=self._open_create_order_dialog)\
            .pack(side="right")

        # Customer (optional)
        tk.Label(left, text="Customer name:").grid(row=7, column=0, sticky="w", padx=6)
        self.customer_var = tk.StringVar(value=self.username if self.role == "user" else "")
        tk.Entry(left, textvariable=self.customer_var, width=28)\
            .grid(row=8, column=0, padx=6, pady=(0, 4))

        # ----------------------------- Right pane
        if self.role == "admin":
            self._build_admin_right_panel()
            self._reload_orders_admin()
        else:
            try:
                has_any = len(self.db.get_orders_for_user(self.user_id, limit=1)) > 0
            except Exception:
                has_any = False
            self._build_user_right_panel(hidden=not has_any)
            if has_any:
                self.u_status_sel.set("")
                self._reload_orders_user()

        # Init items list
        if cat_names:
            self.cat_sel.set(cat_names[0])
            self._load_items_for_category()

    # ------------------------------------------ Orders helpers (left pane / cart)
    def _load_items_for_category(self):
        self.items_listbox.delete(0, tk.END)
        cat = self.cat_sel.get()
        if not cat:
            return
        cid = self.cat_id_by_name.get(cat)
        if cid is None:
            return
        items = self.db.get_menu_items(category_id=cid, active_only=True)
        self.items_cache = {f"{name} (${price:.2f})": (iid, price) for iid, name, price, _cid, _act in items}
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

    # ------------------------------------------------------- Create order flow
    def _open_create_order_dialog(self):
        if self.cart_list.size() == 0:
            messagebox.showwarning("Cart is empty", "Add items to the cart first.")
            return

        dlg = tk.Toplevel(self)
        dlg.title("Create Order")
        dlg.geometry("380x220")
        dlg.transient(self)
        dlg.grab_set()

        tk.Label(dlg, text="Service type:", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 4))
        self._dlg_service_type = tk.StringVar(value="TAKEAWAY")
        rframe = tk.Frame(dlg); rframe.pack(anchor="w", padx=10, pady=(0, 6))
        tk.Radiobutton(rframe, text="Dine-in", value="DINE_IN", variable=self._dlg_service_type,
                       command=lambda: self._toggle_dlg_address()).pack(side="left", padx=(0, 10))
        tk.Radiobutton(rframe, text="Takeaway", value="TAKEAWAY", variable=self._dlg_service_type,
                       command=lambda: self._toggle_dlg_address()).pack(side="left", padx=(0, 10))
        tk.Radiobutton(rframe, text="Delivery", value="DELIVERY", variable=self._dlg_service_type,
                       command=lambda: self._toggle_dlg_address()).pack(side="left")

        self._dlg_addr_label = tk.Label(dlg, text="Delivery address:")
        self._dlg_addr_var = tk.StringVar()
        self._dlg_addr_entry = tk.Entry(dlg, textvariable=self._dlg_addr_var, width=46)

        self._toggle_dlg_address()

        btm = tk.Frame(dlg); btm.pack(fill="x", padx=10, pady=10)
        tk.Button(btm, text="Cancel", command=dlg.destroy).pack(side="right")
        tk.Button(btm, text="Confirm", command=lambda: self._confirm_create_order(dlg)).pack(side="right", padx=(0, 8))

    def _toggle_dlg_address(self):
        if self._dlg_service_type.get() == "DELIVERY":
            self._dlg_addr_label.pack(anchor="w", padx=10, pady=(4, 2))
            self._dlg_addr_entry.pack(anchor="w", padx=10)
        else:
            self._dlg_addr_label.pack_forget()
            self._dlg_addr_entry.pack_forget()
            self._dlg_addr_var.set("")

    def _confirm_create_order(self, dlg: tk.Toplevel):
        items: List[Tuple[int, int]] = []
        for i in range(self.cart_list.size()):
            row = self.cart_list.get(i)
            try:
                name_part, qty_str = row.rsplit(" x ", 1)
            except ValueError:
                continue
            item_id, _price = self.items_cache[name_part]
            items.append((item_id, int(qty_str)))

        customer = (self.customer_var.get() or "").strip()
        stype = self._dlg_service_type.get()
        addr = (self._dlg_addr_var.get() or "").strip()

        if stype == "DELIVERY" and not addr:
            messagebox.showerror("Address required", "Please enter delivery address.")
            return

        try:
            oid = self.db.create_order(
                customer_name=customer,
                customer_contact="",
                items=items,
                notes="",
                service_type=stype,
                delivery_address=addr or None,
            )
        except TypeError:
            extra = f" | Service: {stype}"
            if addr:
                extra += f" | Delivery address: {addr}"
            oid = self.db.create_order(customer, "", items, extra)
        except Exception as e:
            messagebox.showerror("Order failed", str(e))
            return

        dlg.destroy()
        messagebox.showinfo("Success", f"Order #{oid} created.")

        self.cart_list.delete(0, tk.END)
        self.qty_var.set(1)

        if self.role == "user":
            self._ensure_user_right_visible()
            self.u_status_sel.set("")
            self._reload_orders_user()
        else:
            self._reload_orders_admin()

    # ------------------------------------------------------ user right panel
    def _build_user_right_panel(self, hidden: bool = False):
        self.user_right = tk.LabelFrame(self.orders_tab, text="My Orders")

        filt = tk.Frame(self.user_right)
        filt.pack(fill="x", padx=6, pady=4)

        tk.Label(filt, text="Status:").pack(side="left")
        self.u_statuses = ["", "RECEIVED", "IN_PROGRESS", "READY", "COMPLETED", "CANCELED"]
        self.u_status_sel = tk.StringVar(value="")
        ttk.Combobox(filt, textvariable=self.u_status_sel, values=self.u_statuses,
                     width=14, state="readonly").pack(side="left", padx=(4, 12))

        tk.Label(filt, text="Search:").pack(side="left")
        self.u_search_var = tk.StringVar()
        tk.Entry(filt, textvariable=self.u_search_var, width=26)\
            .pack(side="left", padx=(4, 8))
        tk.Button(filt, text="Apply", command=self._reload_orders_user)\
            .pack(side="left")

        cols = ("ID", "Date", "Customer", "Status", "Total")
        self.user_tree = ttk.Treeview(self.user_right, columns=cols, show="headings", height=18)
        for c in cols:
            self.user_tree.heading(c, text=c)
        self.user_tree.column("ID", width=70, anchor="center")
        self.user_tree.column("Date", width=150)
        self.user_tree.column("Customer", width=220)
        self.user_tree.column("Status", width=120, anchor="center")
        self.user_tree.column("Total", width=90, anchor="e")
        self.user_tree.pack(fill="both", expand=True, padx=6, pady=6)
        self.user_tree.bind("<Double-1>", lambda e: self._view_order_details_user())

        btns = tk.Frame(self.user_right)
        btns.pack(fill="x", padx=6, pady=(0, 8))
        tk.Button(btns, text="Details", command=self._view_order_details_user).pack(side="left")
        tk.Button(btns, text="Cancel Order", command=self._user_cancel_order).pack(side="left", padx=(6, 0))
        tk.Button(btns, text="Refresh", command=self._reload_orders_user).pack(side="right")

        if not hidden:
            self.user_right.pack(side="right", fill="both", expand=True, padx=10, pady=10)
            self._user_right_visible = True

    def _ensure_user_right_visible(self):
        if self.role == "user" and not self._user_right_visible:
            self.user_right.pack(side="right", fill="both", expand=True, padx=10, pady=10)
            self._user_right_visible = True

    # ------------------------------------------------------ admin right panel
    def _build_admin_right_panel(self):
        right = tk.LabelFrame(self.orders_tab, text="Existing Orders")
        right.pack(side="right", fill="both", expand=True, padx=10, pady=10)

        filters = tk.Frame(right); filters.pack(fill="x", padx=6, pady=4)
        tk.Label(filters, text="Status:").pack(side="left")
        self.a_statuses = ["", "RECEIVED", "IN_PROGRESS", "READY", "COMPLETED", "CANCELED"]
        self.a_status_sel = tk.StringVar(value="")
        ttk.Combobox(filters, textvariable=self.a_status_sel, values=self.a_statuses,
                     width=14, state="readonly").pack(side="left", padx=(4, 12))
        tk.Label(filters, text="Search:").pack(side="left")
        self.a_search_var = tk.StringVar()
        tk.Entry(filters, textvariable=self.a_search_var, width=26)\
            .pack(side="left", padx=(4, 8))
        tk.Button(filters, text="Apply", command=self._reload_orders_admin).pack(side="left")

        cols = ("ID", "Date", "Customer", "Status", "Total")
        self.admin_tree = ttk.Treeview(right, columns=cols, show="headings", height=18)
        for c in cols:
            self.admin_tree.heading(c, text=c)
        self.admin_tree.column("ID", width=70, anchor="center")
        self.admin_tree.column("Date", width=150)
        self.admin_tree.column("Customer", width=220)
        self.admin_tree.column("Status", width=120, anchor="center")
        self.admin_tree.column("Total", width=90, anchor="e")
        self.admin_tree.pack(fill="both", expand=True, padx=6, pady=6)
        self.admin_tree.bind("<Double-1>", lambda e: self._view_order_details_admin())

        btns = tk.Frame(right); btns.pack(fill="x", padx=6, pady=(0, 8))
        tk.Button(btns, text="Details", command=self._view_order_details_admin).pack(side="left")
        tk.Button(btns, text="Next Status", command=self._advance_status_admin).pack(side="left", padx=6)
        tk.Button(btns, text="Cancel", command=self._cancel_order_admin).pack(side="left")
        tk.Button(btns, text="Refresh", command=self._reload_orders_admin).pack(side="right")

    # ---------------------------------------------------------- reload (right)
    def _reload_orders_user(self):
        if self.role != "user" or not hasattr(self, "user_tree"):
            return
        for i in self.user_tree.get_children():
            self.user_tree.delete(i)
        status = self.u_status_sel.get() or None
        search = self.u_search_var.get()
        try:
            rows = self.db.get_orders_for_user(self.user_id, status=status, search_text=search, limit=600)
        except Exception:
            rows = self.db.get_orders(status=status, search_text=search, limit=600)
        for oid, dt, cust, st, total in rows:
            self.user_tree.insert("", "end", values=(oid, dt, cust, st, f"{total:.2f}"))

    def _reload_orders_admin(self):
        if self.role != "admin" or not hasattr(self, "admin_tree"):
            return
        for i in self.admin_tree.get_children():
            self.admin_tree.delete(i)
        status = self.a_status_sel.get() or None
        search = self.a_search_var.get()
        for oid, dt, cust, st, total in self.db.get_orders(status=status, search_text=search, limit=600):
            self.admin_tree.insert("", "end", values=(oid, dt, cust, st, f"{total:.2f}"))

    # ----------------------------------------------------- details helpers
    def _get_selected_id_from_tree(self, tree: ttk.Treeview) -> Optional[int]:
        sel = tree.focus()
        if not sel:
            return None
        return int(tree.item(sel, "values")[0])

    def _view_order_details_user(self):
        oid = self._get_selected_id_from_tree(self.user_tree)
        if not oid:
            return
        self._open_details_window(oid)

    def _view_order_details_admin(self):
        oid = self._get_selected_id_from_tree(self.admin_tree)
        if not oid:
            return
        self._open_details_window(oid)

    def _open_details_window(self, oid: int):
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

    def _open_details_window_with_address(self, oid: int, address: str):
        items, total = self.db.get_order_items(oid)
        win = tk.Toplevel(self)
        win.title(f"Order #{oid} (Delivery)")
        win.geometry("600x420")
        win.transient(self)
        win.grab_set()

        tk.Label(win, text=f"Delivery address: {address}", font=("Segoe UI", 10, "bold"))\
            .pack(anchor="w", padx=10, pady=(10, 0))

        cols = ("Item", "Qty", "Price", "Subtotal")
        tv = ttk.Treeview(win, columns=cols, show="headings")
        for c in cols:
            tv.heading(c, text=c)
        tv.column("Item", width=260)
        tv.column("Qty", width=60, anchor="center")
        tv.column("Price", width=100, anchor="e")
        tv.column("Subtotal", width=120, anchor="e")
        tv.pack(fill="both", expand=True, padx=10, pady=10)

        for name, qty, price, sub in items:
            tv.insert("", "end", values=(name, qty, f"{price:.2f}", f"{sub:.2f}"))

        tk.Label(win, text=f"Total: {total:.2f}", font=("Segoe UI", 11, "bold"))\
            .pack(anchor="e", padx=12, pady=(0, 10))
        tk.Button(win, text="Close", command=win.destroy).pack(pady=(0, 10))

    # ---------------------------------------------------------- admin actions
    def _advance_status_admin(self):
        oid = self._get_selected_id_from_tree(self.admin_tree)
        if not oid:
            return
        st = self.admin_tree.item(self.admin_tree.focus(), "values")[3]
        nexts = self.db.get_next_statuses(st)
        if not nexts:
            messagebox.showinfo("No action", f"Status '{st}' has no next steps.")
            return
        choice = simpledialog.askstring("Next Status", f"Choose: {', '.join(nexts)}", parent=self)
        if not choice or choice not in nexts:
            return
        try:
            self.db.update_order_status(oid, choice)
        except ValueError as e:
            messagebox.showerror("Error", str(e))
            return
        self._reload_orders_admin()

    def _cancel_order_admin(self):
        oid = self._get_selected_id_from_tree(self.admin_tree)
        if not oid:
            return
        if not messagebox.askyesno("Cancel", "Cancel this order?"):
            return
        try:
            self.db.update_order_status(oid, "CANCELED")
        except ValueError as e:
            messagebox.showerror("Error", str(e))
            return
        self._reload_orders_admin()

    # ---------------------------------------------------------- user actions
    def _user_cancel_order(self):
        if self.role != "user":
            return
        oid = self._get_selected_id_from_tree(self.user_tree)
        if not oid:
            return
        if not messagebox.askyesno("Cancel", f"Cancel order #{oid}?"):
            return
        try:
            self.db.cancel_order_by_user(oid, self.user_id)
        except AttributeError:
            self.db.update_order_status(oid, "CANCELED")
        except (ValueError, PermissionError) as e:
            messagebox.showerror("Error", str(e))
            return
        messagebox.showinfo("Canceled", f"Order #{oid} canceled.")
        self._reload_orders_user()

    # ----------------------------------------------------------- Admin tab (UI)
    def _maybe_add_admin_tab(self):
        # 1) admin code
        admin_code = simpledialog.askstring("Admin Access", "Enter admin access code:", show="*", parent=self)
        if not admin_code or not self.db.verify_admin_access(admin_code):
            messagebox.showinfo("Access denied", "Admin area is locked.")
            return

        # 2) area code (admin / chef / courier)
        area_code = simpledialog.askstring("Area Access",
                                           "Enter code for Admin / Chef / Courier:",
                                           show="*", parent=self)
        area = None
        if area_code and self.db.verify_admin_access(area_code):
            area = "admin"
        elif area_code and self.db.verify_chef_access(area_code):
            area = "chef"
        elif area_code and self.db.verify_courier_access(area_code):
            area = "courier"
        else:
            messagebox.showerror("Access denied", "Unknown area code.")
            return

        # створюємо вкладку Admin і додаємо підвкладки залежно від area
        self.admin_tab = tk.Frame(self.nb)
        self.nb.add(self.admin_tab, text="Admin")
        self.nb.select(self.admin_tab)

        self.admin_nb = ttk.Notebook(self.admin_tab)
        self.admin_nb.pack(fill="both", expand=True)

        if area == "admin":
            self._build_admin_menu_tab()
            self._build_admin_orders_tab()
            self._build_admin_analytics_tab()
        elif area == "chef":
            self._add_chef_subtab()
        elif area == "courier":
            self._add_courier_subtab()

    # ------------------------------------------- Admin / Menu management (tabs)
    def _build_admin_menu_tab(self):
        tab = tk.Frame(self.admin_nb)
        self.admin_nb.add(tab, text="Menu")

        left = tk.LabelFrame(tab, text="Item Editor")
        left.pack(side="left", fill="y", padx=10, pady=10)

        tk.Label(left, text="Category:").grid(row=0, column=0, sticky="w", padx=6, pady=(8, 2))
        self.admin_categories = self.db.get_categories()
        self.admin_cat_by_name = {name: cid for cid, name in self.admin_categories}
        self.admin_cat_sel = tk.StringVar()
        cat_names = [n for _, n in self.admin_categories]
        self.admin_cat_combo = ttk.Combobox(left, textvariable=self.admin_cat_sel, values=cat_names,
                                            state="readonly", width=22)
        self.admin_cat_combo.grid(row=1, column=0, padx=6, pady=(0, 6))
        self.admin_cat_combo.bind("<<ComboboxSelected>>", lambda e: self._admin_refresh_items())

        addc = tk.Frame(left); addc.grid(row=2, column=0, padx=6, pady=(0, 8), sticky="w")
        tk.Button(addc, text="Add Category", command=self._admin_add_category).pack(side="left")
        tk.Button(addc, text="Delete Category", command=self._admin_delete_category).pack(side="left", padx=(6, 0))

        tk.Label(left, text="Item name:").grid(row=3, column=0, sticky="w", padx=6, pady=(6, 2))
        self.admin_item_name = tk.StringVar()
        tk.Entry(left, textvariable=self.admin_item_name, width=24).grid(row=4, column=0, padx=6, pady=(0, 6))

        tk.Label(left, text="Price:").grid(row=5, column=0, sticky="w", padx=6, pady=(6, 2))
        self.admin_item_price = tk.DoubleVar(value=0.0)
        tk.Entry(left, textvariable=self.admin_item_price, width=24).grid(row=6, column=0, padx=6, pady=(0, 6))

        self.admin_item_active = tk.IntVar(value=1)
        tk.Checkbutton(left, text="Active (available to order)", variable=self.admin_item_active)\
            .grid(row=7, column=0, sticky="w", padx=6, pady=(0, 6))

        tk.Button(left, text="Add Item", command=self._admin_add_item).grid(row=8, column=0, padx=6, pady=(4, 4))
        self.btn_admin_update = tk.Button(left, text="Update Item", state="disabled",
                                          command=self._admin_update_item)
        self.btn_admin_update.grid(row=9, column=0, padx=6, pady=(0, 4))
        tk.Button(left, text="Clear", command=self._admin_clear_item_form).grid(row=10, column=0, padx=6, pady=(0, 10))

        right = tk.LabelFrame(tab, text="Items")
        right.pack(side="right", fill="both", expand=True, padx=10, pady=10)
        self.admin_items_tree = ttk.Treeview(right, columns=("ID", "Name", "Price", "Active"), show="headings")
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
        for i in self.admin_items_tree.get_children():
            self.admin_items_tree.delete(i)
        cat = self.admin_cat_sel.get()
        if not cat:
            return
        cid = self.admin_cat_by_name[cat]
        self.admin_items_cache = self.db.get_menu_items(category_id=cid, active_only=False)
        for iid, name, price, _cid, active in self.admin_items_cache:
            self.admin_items_tree.insert("", "end", values=(iid, name, f"{price:.2f}", "Yes" if active else "No"))

        # sync з користувацькою вкладкою
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
        if not messagebox.askyesno("Delete Category",
                                   f"Delete category '{cat}'? Items must be moved/deleted first."):
            return
        try:
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
            self.db.update_menu_item(self.editing_item_id, name, price, cid, bool(self.admin_item_active.get()))
        except ValueError as e:
            if str(e) == "NAME_TAKEN":
                messagebox.showerror("Error", "Another item with this name already exists.")
                return
            raise
        self._admin_clear_item_form()
        self._admin_refresh_items()

    # ------------------------------------------- Admin / Orders management
    def _build_admin_orders_tab(self):
        tab = tk.Frame(self.admin_nb)
        self.admin_nb.add(tab, text="Orders")

        filter_bar = tk.Frame(tab)
        filter_bar.pack(fill="x", padx=10, pady=(10, 0))
        tk.Label(filter_bar, text="Status:").pack(side="left")
        self.admin_status_sel2 = tk.StringVar(value="")
        ttk.Combobox(filter_bar, textvariable=self.admin_status_sel2,
                     values=["", "RECEIVED", "IN_PROGRESS", "READY", "COMPLETED", "CANCELED"],
                     width=14, state="readonly").pack(side="left", padx=(4, 10))
        tk.Label(filter_bar, text="Search:").pack(side="left")
        self.admin_search_var2 = tk.StringVar()
        tk.Entry(filter_bar, textvariable=self.admin_search_var2, width=26)\
            .pack(side="left", padx=(4, 8))
        tk.Button(filter_bar, text="Apply", command=self._admin_reload_orders_tab).pack(side="left")

        cols = ("ID", "Date", "Customer", "Status", "Total")
        self.admin_orders_tree2 = ttk.Treeview(tab, columns=cols, show="headings")
        for c in cols:
            self.admin_orders_tree2.heading(c, text=c)
        self.admin_orders_tree2.column("ID", width=70, anchor="center")
        self.admin_orders_tree2.column("Date", width=150)
        self.admin_orders_tree2.column("Customer", width=220)
        self.admin_orders_tree2.column("Status", width=120, anchor="center")
        self.admin_orders_tree2.column("Total", width=90, anchor="e")
        self.admin_orders_tree2.pack(fill="both", expand=True, padx=10, pady=10)
        self.admin_orders_tree2.bind("<Double-1>", lambda e: self._view_order_details_admin_tab())

        btns = tk.Frame(tab)
        btns.pack(fill="x", padx=10, pady=(0, 10))
        tk.Button(btns, text="Details", command=self._view_order_details_admin_tab).pack(side="left")
        tk.Button(btns, text="Advance", command=self._admin_advance_status_tab).pack(side="left", padx=6)
        tk.Button(btns, text="Cancel", command=self._admin_cancel_order_tab).pack(side="left")
        tk.Button(btns, text="Refresh", command=self._admin_reload_orders_tab).pack(side="right")

        self._admin_reload_orders_tab()

    def _admin_reload_orders_tab(self):
        for i in self.admin_orders_tree2.get_children():
            self.admin_orders_tree2.delete(i)
        status = self.admin_status_sel2.get() or None
        search = self.admin_search_var2.get()
        for oid, dt, cust, st, total in self.db.get_orders(status=status, search_text=search, limit=600):
            self.admin_orders_tree2.insert("", "end", values=(oid, dt, cust, st, f"{total:.2f}"))

    def _view_order_details_admin_tab(self):
        oid = self._get_selected_id_from_tree(self.admin_orders_tree2)
        if not oid:
            return
        self._open_details_window(oid)

    def _admin_advance_status_tab(self):
        oid = self._get_selected_id_from_tree(self.admin_orders_tree2)
        if not oid:
            return
        st = self.admin_orders_tree2.item(self.admin_orders_tree2.focus(), "values")[3]
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
        self._admin_reload_orders_tab()

    def _admin_cancel_order_tab(self):
        oid = self._get_selected_id_from_tree(self.admin_orders_tree2)
        if not oid:
            return
        if not messagebox.askyesno("Cancel", f"Cancel order #{oid}?"):
            return
        try:
            self.db.update_order_status(oid, "CANCELED")
        except ValueError as e:
            messagebox.showerror("Error", str(e))
            return
        self._admin_reload_orders_tab()

    # ------------------------------------------------------ Admin / Analytics
    def _build_admin_analytics_tab(self):
        tab = tk.Frame(self.admin_nb)
        self.admin_nb.add(tab, text="Analytics")

        filters = tk.LabelFrame(tab, text="Filters")
        filters.pack(fill="x", padx=10, pady=(10, 6))

        today = datetime.now().date()
        start_default = today.replace(day=1).strftime("%Y-%m-%d")
        end_default = today.strftime("%Y-%m-%d")

        tk.Label(filters, text="From (YYYY-MM-DD):").pack(side="left", padx=(8, 4))
        self.an_start_var = tk.StringVar(value=start_default)
        tk.Entry(filters, textvariable=self.an_start_var, width=12).pack(side="left")
        tk.Label(filters, text="To (YYYY-MM-DD):").pack(side="left", padx=(10, 4))
        self.an_end_var = tk.StringVar(value=end_default)
        tk.Entry(filters, textvariable=self.an_end_var, width=12).pack(side="left")

        tk.Label(filters, text="Statuses:").pack(side="left", padx=(16, 4))
        self.an_status_list = tk.Listbox(filters, height=5, exportselection=False, selectmode="multiple")
        try:
            statuses = self.db.get_status_list()
        except Exception:
            statuses = ["RECEIVED", "IN_PROGRESS", "READY", "COMPLETED", "CANCELED"]
        for s in statuses:
            self.an_status_list.insert(tk.END, s)
        self.an_status_list.pack(side="left", padx=(0, 10))

        tk.Button(filters, text="Run", command=self._run_analytics).pack(side="left", padx=(4, 2))
        tk.Button(filters, text="Export Orders CSV", command=self._export_orders_csv).pack(side="left", padx=(4, 2))
        tk.Button(filters, text="Export Top Items CSV", command=self._export_top_items_csv).pack(side="left", padx=(4, 2))

        summary = tk.LabelFrame(tab, text="Summary")
        summary.pack(fill="x", padx=10, pady=(0, 6))
        self.sum_orders_var = tk.StringVar(value="0")
        self.sum_revenue_var = tk.StringVar(value="0.00")
        self.sum_avg_var = tk.StringVar(value="0.00")

        tk.Label(summary, text="Orders:").pack(side="left", padx=(10, 4))
        tk.Label(summary, textvariable=self.sum_orders_var, font=("Segoe UI", 10, "bold")).pack(side="left")
        tk.Label(summary, text="   Revenue:").pack(side="left", padx=(20, 4))
        tk.Label(summary, textvariable=self.sum_revenue_var, font=("Segoe UI", 10, "bold")).pack(side="left")
        tk.Label(summary, text="   Avg order:").pack(side="left", padx=(20, 4))
        tk.Label(summary, textvariable=self.sum_avg_var, font=("Segoe UI", 10, "bold")).pack(side="left")

        split = tk.PanedWindow(tab, sashrelief="sunken")
        split.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        left = tk.LabelFrame(split, text="Orders")
        cols_o = ("ID", "Date", "Customer", "Status", "Service", "Total")
        self.an_orders_tree = ttk.Treeview(left, columns=cols_o, show="headings")
        for c in cols_o:
            self.an_orders_tree.heading(c, text=c)
        self.an_orders_tree.column("ID", width=70, anchor="center")
        self.an_orders_tree.column("Date", width=150)
        self.an_orders_tree.column("Customer", width=200)
        self.an_orders_tree.column("Status", width=120, anchor="center")
        self.an_orders_tree.column("Service", width=100, anchor="center")
        self.an_orders_tree.column("Total", width=100, anchor="e")
        self.an_orders_tree.pack(fill="both", expand=True, padx=6, pady=6)

        right = tk.LabelFrame(split, text="Top Items")
        cols_i = ("Item", "Qty", "Revenue")
        self.an_items_tree = ttk.Treeview(right, columns=cols_i, show="headings")
        for c in cols_i:
            self.an_items_tree.heading(c, text=c)
        self.an_items_tree.column("Item", width=260)
        self.an_items_tree.column("Qty", width=80, anchor="center")
        self.an_items_tree.column("Revenue", width=120, anchor="e")
        self.an_items_tree.pack(fill="both", expand=True, padx=6, pady=6)

        split.add(left)
        split.add(right)

        self._run_analytics()

    def _parse_period(self) -> Optional[Tuple[str, str]]:
        try:
            start = datetime.strptime(self.an_start_var.get().strip(), "%Y-%m-%d")
            end = datetime.strptime(self.an_end_var.get().strip(), "%Y-%m-%d")
            if end < start:
                raise ValueError
            end_dt = end + timedelta(days=1) - timedelta(seconds=1)
            return start.strftime("%Y-%m-%d %H:%M:%S"), end_dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            messagebox.showerror("Invalid period", "Use YYYY-MM-DD for dates and ensure From ≤ To.")
            return None

    def _selected_statuses(self) -> Optional[List[str]]:
        sel = [self.an_status_list.get(i) for i in self.an_status_list.curselection()]
        return sel or None

    def _run_analytics(self):
        period = self._parse_period()
        if not period:
            return
        start_dt, end_dt = period
        statuses = self._selected_statuses()

        for t in (self.an_orders_tree, self.an_items_tree):
            for i in t.get_children():
                t.delete(i)

        try:
            orders = self.db.report_orders(start_dt, end_dt, statuses=statuses)
        except AttributeError:
            orders = self.db.get_orders(status=None, search_text="", limit=1000)
            orders = [(oid, dt, cust, st, "", total) for (oid, dt, cust, st, total) in orders]

        total_revenue = 0.0
        for oid, dt, cust, st, service, total in orders:
            total_revenue += float(total)
            self.an_orders_tree.insert("", "end",
                                       values=(oid, dt, cust, st, service or "", f"{float(total):.2f}"))

        count = len(orders)
        avg = (total_revenue / count) if count else 0.0
        self.sum_orders_var.set(str(count))
        self.sum_revenue_var.set(f"{total_revenue:.2f}")
        self.sum_avg_var.set(f"{avg:.2f}")

        try:
            items = self.db.report_top_items(start_dt, end_dt, statuses=statuses, limit=20)
        except AttributeError:
            items = []
        for name, qty, revenue in items:
            self.an_items_tree.insert("", "end", values=(name, int(qty), f"{float(revenue):.2f}"))

    def _export_orders_csv(self):
        period = self._parse_period()
        if not period:
            return
        start_dt, end_dt = period
        statuses = self._selected_statuses()

        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            title="Save Orders CSV",
            initialfile="orders_report.csv",
        )
        if not path:
            return

        try:
            rows = self.db.report_orders(start_dt, end_dt, statuses=statuses)
        except AttributeError:
            rows = self.db.get_orders(status=None, search_text="", limit=1000)
            rows = [(oid, dt, cust, st, "", total) for (oid, dt, cust, st, total) in rows]

        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["OrderID", "Date", "Customer", "Status", "ServiceType", "Total"])
            for oid, dt, cust, st, service, total in rows:
                w.writerow([oid, dt, cust, st, service or "", f"{float(total):.2f}"])

        messagebox.showinfo("Export", "Orders CSV saved.")

    def _export_top_items_csv(self):
        period = self._parse_period()
        if not period:
            return
        start_dt, end_dt = period
        statuses = self._selected_statuses()

        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            title="Save Top Items CSV",
            initialfile="top_items.csv",
        )
        if not path:
            return

        try:
            items = self.db.report_top_items(start_dt, end_dt, statuses=statuses, limit=1000)
        except AttributeError:
            items = []

        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Item", "Qty", "Revenue"])
            for name, qty, revenue in items:
                w.writerow([name, int(qty), f"{float(revenue):.2f}"])

        messagebox.showinfo("Export", "Top Items CSV saved.")

    # ----------------------------- підвкладки Chef/Courier всередині Admin ----
    def _add_chef_subtab(self):
        parent = tk.Frame(self.admin_nb)
        self.admin_nb.add(parent, text="Chef")

        nb = ttk.Notebook(parent)
        nb.pack(fill="both", expand=True)

        # ---- Orders
        orders_tab = tk.Frame(nb); nb.add(orders_tab, text="Orders")
        filt = tk.Frame(orders_tab); filt.pack(fill="x", padx=10, pady=(10, 0))
        tk.Label(filt, text="Status:").pack(side="left")
        self.chef_status = tk.StringVar(value="")
        ttk.Combobox(filt, textvariable=self.chef_status,
                     values=["", "RECEIVED", "IN_PROGRESS", "READY", "COMPLETED", "CANCELED"],
                     width=14, state="readonly").pack(side="left", padx=(4, 10))
        tk.Label(filt, text="Search:").pack(side="left")
        self.chef_search = tk.StringVar()
        tk.Entry(filt, textvariable=self.chef_search, width=26).pack(side="left", padx=(4, 8))
        tk.Button(filt, text="Apply", command=self._reload_chef_orders).pack(side="left")

        cols = ("ID", "Date", "Customer", "Status", "Total")
        self.chef_tree = ttk.Treeview(orders_tab, columns=cols, show="headings", height=18)
        for c in cols:
            self.chef_tree.heading(c, text=c)
        self.chef_tree.column("ID", width=70, anchor="center")
        self.chef_tree.column("Date", width=150)
        self.chef_tree.column("Customer", width=220)
        self.chef_tree.column("Status", width=120, anchor="center")
        self.chef_tree.column("Total", width=90, anchor="e")
        self.chef_tree.pack(fill="both", expand=True, padx=10, pady=10)
        self.chef_tree.bind("<Double-1>", lambda e: self._view_order_details_chef())

        btns = tk.Frame(orders_tab); btns.pack(fill="x", padx=10, pady=(0, 10))
        tk.Button(btns, text="Details", command=self._view_order_details_chef).pack(side="left")
        tk.Button(btns, text="Advance", command=self._chef_advance_status).pack(side="left", padx=6)
        tk.Button(btns, text="Cancel", command=self._chef_cancel).pack(side="left")
        tk.Button(btns, text="Refresh", command=self._reload_chef_orders).pack(side="right")

        self._reload_chef_orders()

        # ---- Kitchen menu (read-only)
        menu_tab = tk.Frame(nb); nb.add(menu_tab, text="Kitchen Menu")
        left = tk.Frame(menu_tab); left.pack(side="left", fill="y", padx=10, pady=10)
        tk.Label(left, text="Category:").grid(row=0, column=0, sticky="w")
        self.chef_cats = self.db.get_categories()
        self.chef_cat_by_name = {n: i for i, n in self.chef_cats}
        self.chef_cat_sel = tk.StringVar()
        ttk.Combobox(left, textvariable=self.chef_cat_sel,
                     values=[n for _, n in self.chef_cats], state="readonly", width=22)\
            .grid(row=1, column=0, sticky="w", pady=(2, 6))
        self.chef_cat_sel.trace_add("write", lambda *_: self._chef_refresh_menu())

        right = tk.LabelFrame(menu_tab, text="Items")
        right.pack(side="right", fill="both", expand=True, padx=10, pady=10)
        self.chef_menu_tree = ttk.Treeview(right, columns=("ID", "Name", "Price", "Active"), show="headings")
        for c in ("ID", "Name", "Price", "Active"):
            self.chef_menu_tree.heading(c, text=c)
        self.chef_menu_tree.column("ID", width=60, anchor="center")
        self.chef_menu_tree.column("Name", width=260)
        self.chef_menu_tree.column("Price", width=120, anchor="e")
        self.chef_menu_tree.column("Active", width=80, anchor="center")
        self.chef_menu_tree.pack(fill="both", expand=True, padx=6, pady=6)

        if self.chef_cats:
            self.chef_cat_sel.set(self.chef_cats[0][1])

    def _reload_chef_orders(self):
        if not hasattr(self, "chef_tree"):
            return
        for i in self.chef_tree.get_children():
            self.chef_tree.delete(i)
        status = self.chef_status.get() or None
        search = self.chef_search.get()
        for oid, dt, cust, st, total in self.db.get_orders(status=status, search_text=search, limit=600):
            self.chef_tree.insert("", "end", values=(oid, dt, cust, st, f"{total:.2f}"))

    def _view_order_details_chef(self):
        oid = self._get_selected_id_from_tree(self.chef_tree)
        if not oid:
            return
        self._open_details_window(oid)

    def _chef_advance_status(self):
        oid = self._get_selected_id_from_tree(self.chef_tree)
        if not oid:
            return
        st = self.chef_tree.item(self.chef_tree.focus(), "values")[3]
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
        self._reload_chef_orders()

    def _chef_cancel(self):
        oid = self._get_selected_id_from_tree(self.chef_tree)
        if not oid:
            return
        if not messagebox.askyesno("Cancel", f"Cancel order #{oid}?"):
            return
        try:
            self.db.update_order_status(oid, "CANCELED")
        except ValueError as e:
            messagebox.showerror("Error", str(e))
            return
        self._reload_chef_orders()

    def _chef_refresh_menu(self):
        for i in self.chef_menu_tree.get_children():
            self.chef_menu_tree.delete(i)
        cat = self.chef_cat_sel.get()
        if not cat:
            return
        cid = self.chef_cat_by_name.get(cat)
        rows = self.db.get_menu_items(category_id=cid, active_only=False)
        for iid, name, price, _cid, active in rows:
            self.chef_menu_tree.insert("", "end", values=(iid, name, f"{price:.2f}", "Yes" if active else "No"))

    def _add_courier_subtab(self):
        parent = tk.Frame(self.admin_nb)
        self.admin_nb.add(parent, text="Courier")

        filt = tk.Frame(parent); filt.pack(fill="x", padx=10, pady=(10, 0))
        tk.Label(filt, text="Status:").pack(side="left")
        self.courier_status = tk.StringVar(value="")
        ttk.Combobox(filt, textvariable=self.courier_status,
                     values=["", "RECEIVED", "IN_PROGRESS", "READY", "COMPLETED", "CANCELED"],
                     width=14, state="readonly").pack(side="left", padx=(4, 10))
        tk.Label(filt, text="Search:").pack(side="left")
        self.courier_search = tk.StringVar()
        tk.Entry(filt, textvariable=self.courier_search, width=26).pack(side="left", padx=(4, 8))
        tk.Button(filt, text="Apply", command=self._reload_courier_orders).pack(side="left")

        cols = ("ID", "Date", "Customer", "Status", "Total", "Address")
        self.courier_tree = ttk.Treeview(parent, columns=cols, show="headings")
        for c in cols:
            self.courier_tree.heading(c, text=c)
        self.courier_tree.column("ID", width=70, anchor="center")
        self.courier_tree.column("Date", width=150)
        self.courier_tree.column("Customer", width=180)
        self.courier_tree.column("Status", width=120, anchor="center")
        self.courier_tree.column("Total", width=90, anchor="e")
        self.courier_tree.column("Address", width=260)
        self.courier_tree.pack(fill="both", expand=True, padx=10, pady=10)
        self.courier_tree.bind("<Double-1>", lambda e: self._view_order_details_courier())

        btns = tk.Frame(parent); btns.pack(fill="x", padx=10, pady=(0, 10))
        tk.Button(btns, text="Details", command=self._view_order_details_courier).pack(side="left")
        tk.Button(btns, text="Next Status", command=self._courier_advance_status).pack(side="left", padx=6)
        tk.Button(btns, text="Cancel", command=self._courier_cancel).pack(side="left")
        tk.Button(btns, text="Refresh", command=self._reload_courier_orders).pack(side="right")

        self._reload_courier_orders()

    def _reload_courier_orders(self):
        if not hasattr(self, "courier_tree"):
            return
        for i in self.courier_tree.get_children():
            self.courier_tree.delete(i)
        status = self.courier_status.get() or None
        search = self.courier_search.get()
        rows = self.db.get_delivery_orders(status=status, search_text=search, limit=600)
        for oid, dt, cust, st, total, addr in rows:
            self.courier_tree.insert("", "end", values=(oid, dt, cust, st, f"{total:.2f}", addr))

    def _view_order_details_courier(self):
        sel = self.courier_tree.focus()
        if not sel:
            return
        vals = self.courier_tree.item(sel, "values")
        oid = int(vals[0])
        addr = vals[5]
        self._open_details_window_with_address(oid, addr)

    def _courier_advance_status(self):
        oid = self._get_selected_id_from_tree(self.courier_tree)
        if not oid:
            return
        st = self.courier_tree.item(self.courier_tree.focus(), "values")[3]
        nexts = self.db.get_next_statuses(st)
        if not nexts:
            messagebox.showinfo("No action", f"'{st}' has no next steps.")
            return
        choice = simpledialog.askstring("Next Status", f"Choose: {', '.join(nexts)}", parent=self)
        if not choice or choice not in nexts:
            return
        try:
            self.db.update_order_status(oid, choice)
        except ValueError as e:
            messagebox.showerror("Error", str(e))
            return
        self._reload_courier_orders()

    def _courier_cancel(self):
        oid = self._get_selected_id_from_tree(self.courier_tree)
        if not oid:
            return
        if not messagebox.askyesno("Cancel", f"Cancel order #{oid}?"):
            return
        try:
            self.db.update_order_status(oid, "CANCELED")
        except ValueError as e:
            messagebox.showerror("Error", str(e))
            return
        self._reload_courier_orders()

    # --------------------------------------------------------------- account ops
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

    # ---------------------------------------------------------------- lifecycle
    def _logout(self):
        try:
            self.on_logout()
        finally:
            self.destroy()
