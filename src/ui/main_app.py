# main_app.py
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from typing import Tuple


class MainApp(tk.Toplevel):
    """
    Role-aware main window for the Restaurant Order Tracker.

    - Always shows the Orders tab.
    - Admin-only Menu Management tab appears after entering the Admin Access Code.
    - Features:
        * Order creation (select items, quantities)
        * Orders table with status and details dialog
        * Mark-as-Completed
        * Change Password (all users)
        * Change Admin Access Code (admin only)
        * Admin: Add / Edit / Delete menu items
    """

    def __init__(self, master, db_manager, user_tuple: Tuple[int, str, str], on_logout):
        super().__init__(master)
        self.db = db_manager
        self.user_id, self.username, self.role = user_tuple
        self.on_logout = on_logout

        self.title("Restaurant Order Tracker")
        self.geometry("900x620")
        self.minsize(820, 560)

        self._build_shell()
        self._build_orders_tab()

        if self.role == "admin":
            self._maybe_add_admin_tab()

        self.protocol("WM_DELETE_WINDOW", self._logout)

    # ---------- shell ----------
    def _build_shell(self):
        topbar = tk.Frame(self)
        topbar.pack(fill="x")

        user_lbl = tk.Label(topbar, text=f"Signed in as: {self.username} ({self.role})")
        user_lbl.pack(side="left", padx=10, pady=8)

        tk.Button(topbar, text="Change Password", command=self._change_password) \
            .pack(side="right", padx=(0, 10), pady=6)

        if self.role == "admin":
            tk.Button(topbar, text="Change Admin Code", command=self._change_admin_code) \
                .pack(side="right", padx=(0, 10), pady=6)

        tk.Button(topbar, text="Logout", command=self._logout) \
            .pack(side="right", padx=10, pady=6)

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)

    # ---------- Orders tab ----------
    def _build_orders_tab(self):
        self.orders_tab = tk.Frame(self.nb)
        self.nb.add(self.orders_tab, text="Orders")

        # Create order form
        form = tk.LabelFrame(self.orders_tab, text="Create New Order")
        form.pack(fill="x", padx=12, pady=8)

        tk.Label(form, text="Customer Name:").grid(row=0, column=0, sticky="e", padx=6, pady=6)
        tk.Label(form, text="Contact:").grid(row=1, column=0, sticky="e", padx=6, pady=6)
        self.cust_name = tk.StringVar()
        self.cust_contact = tk.StringVar()
        tk.Entry(form, textvariable=self.cust_name).grid(row=0, column=1, sticky="ew", padx=6, pady=6)
        tk.Entry(form, textvariable=self.cust_contact).grid(row=1, column=1, sticky="ew", padx=6, pady=6)
        form.grid_columnconfigure(1, weight=1)

        tk.Label(form, text="Item:").grid(row=0, column=2, sticky="e", padx=6, pady=6)
        tk.Label(form, text="Quantity:").grid(row=1, column=2, sticky="e", padx=6, pady=6)

        self.menu_items = self.db.get_menu_items()  # [(id, name, price)]
        item_names = [name for _, name, _ in self.menu_items]

        self.sel_item = tk.StringVar()
        self.item_combo = ttk.Combobox(form, textvariable=self.sel_item, values=item_names, state="readonly")
        self.item_combo.grid(row=0, column=3, padx=6, pady=6)

        self.sel_qty = tk.IntVar(value=1)
        tk.Spinbox(form, from_=1, to=100, textvariable=self.sel_qty, width=6) \
            .grid(row=1, column=3, padx=6, pady=6)

        self.order_items: list[tuple[int, str, int]] = []
        tk.Button(form, text="Add Item", command=self._add_item_to_current) \
            .grid(row=0, column=4, padx=6, pady=6)
        tk.Button(form, text="Place Order", command=self._place_order) \
            .grid(row=1, column=4, padx=6, pady=6)

        self.items_list = tk.Listbox(form, height=4)
        self.items_list.grid(row=2, column=0, columnspan=5, sticky="ew", padx=6, pady=(8, 6))

        # Orders table
        listbox = tk.LabelFrame(self.orders_tab, text="Orders")
        listbox.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        cols = ("ID", "Customer", "Status")
        self.tree = ttk.Treeview(listbox, columns=cols, show="headings")
        for c in cols:
            self.tree.heading(c, text=c)
        self.tree.column("ID", width=80, anchor="center")
        self.tree.column("Customer", width=280)
        self.tree.column("Status", width=120, anchor="center")
        self.tree.pack(side="left", fill="both", expand=True, padx=6, pady=6)

        sb = tk.Scrollbar(listbox, command=self.tree.yview)
        sb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=sb.set)

        btns = tk.Frame(self.orders_tab)
        btns.pack(fill="x", padx=12, pady=(0, 10))
        tk.Button(btns, text="Refresh", command=self._load_orders).pack(side="left")
        tk.Button(btns, text="View Details", command=self._view_details).pack(side="left", padx=8)
        tk.Button(btns, text="Mark as Completed", command=self._mark_completed).pack(side="left", padx=8)

        self.tree.bind("<Double-1>", lambda e: self._view_details())
        self._load_orders()

    def _add_item_to_current(self):
        name = self.sel_item.get()
        if not name:
            messagebox.showwarning("No item", "Select an item first.")
            return
        try:
            qty = max(1, int(self.sel_qty.get()))
        except Exception:
            messagebox.showwarning("Invalid", "Quantity must be a positive integer.")
            return

        found = next((iid for iid, n, _ in self.menu_items if n == name), None)
        if found is None:
            messagebox.showerror("Not found", "Selected item not found in DB.")
            return

        self.order_items.append((found, name, qty))
        self.items_list.insert(tk.END, f"{name} x {qty}")

    def _place_order(self):
        if not self.order_items:
            messagebox.showerror("Empty", "Add at least one item.")
            return
        name = self.cust_name.get().strip()
        contact = self.cust_contact.get().strip()
        try:
            oid = self.db.create_order(name, contact, self.order_items)
        except Exception as e:
            messagebox.showerror("Error", f"Could not create order: {e}")
            return

        messagebox.showinfo("Order placed", f"Order #{oid} has been created.")
        self.cust_name.set("")
        self.cust_contact.set("")
        self.sel_item.set("")
        self.sel_qty.set(1)
        self.order_items.clear()
        self.items_list.delete(0, tk.END)
        self._load_orders()

    def _load_orders(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for oid, cust, status in self.db.get_all_orders():
            self.tree.insert("", "end", values=(oid, cust, status))

    def _mark_completed(self):
        sel = self.tree.focus()
        if not sel:
            messagebox.showinfo("Select", "Choose an order first.")
            return
        oid, _cust, status = self.tree.item(sel, "values")
        if status != "Pending":
            messagebox.showinfo("Info", "This order is already completed.")
            return
        try:
            self.db.update_order_status(oid, "Completed")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update status: {e}")
            return
        self._load_orders()

    def _view_details(self):
        sel = self.tree.focus()
        if not sel:
            messagebox.showinfo("Select", "Choose an order first.")
            return
        oid, cust, status = self.tree.item(sel, "values")
        try:
            items, total = self.db.get_order_items(oid)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load order details: {e}")
            return

        win = tk.Toplevel(self)
        win.title(f"Order #{oid} details")
        win.geometry("520x360")
        win.transient(self)
        win.grab_set()

        tk.Label(win, text=f"Customer: {cust}    Status: {status}") \
            .pack(anchor="w", padx=10, pady=(10, 4))

        cols = ("Item", "Qty", "Price", "Subtotal")
        tv = ttk.Treeview(win, columns=cols, show="headings")
        for c in cols:
            tv.heading(c, text=c)
        tv.column("Item", width=220)
        tv.column("Qty", width=60, anchor="center")
        tv.column("Price", width=90, anchor="e")
        tv.column("Subtotal", width=100, anchor="e")
        tv.pack(fill="both", expand=True, padx=10, pady=6)

        for name, qty, price, sub in items:
            tv.insert("", "end", values=(name, qty, f"{price:.2f}", f"{sub:.2f}"))

        tk.Label(win, text=f"Total: {total:.2f}", font=("Segoe UI", 11, "bold")) \
            .pack(anchor="e", padx=10, pady=(0, 10))

        tk.Button(win, text="Close", command=win.destroy).pack(pady=(0, 10))

    # ---------- Admin tab ----------
    def _maybe_add_admin_tab(self):
        code = simpledialog.askstring(
            "Admin Access", "Enter admin access code:", show="*", parent=self
        )
        if not code:
            messagebox.showinfo("Access denied", "Admin panel not unlocked.")
            return
        if not self.db.verify_admin_access(code):
            messagebox.showerror("Invalid", "Wrong admin access code.")
            return

        self.editing_item_id = None  # track which item is being edited

        self.admin_tab = tk.Frame(self.nb)
        self.nb.add(self.admin_tab, text="Menu Management")

        tk.Label(self.admin_tab, text="Item Name:").grid(row=0, column=0, sticky="e", padx=6, pady=6)
        tk.Label(self.admin_tab, text="Price:").grid(row=1, column=0, sticky="e", padx=6, pady=6)

        self.new_item_name = tk.StringVar()
        self.new_item_price = tk.DoubleVar(value=0.0)

        tk.Entry(self.admin_tab, textvariable=self.new_item_name).grid(row=0, column=1, padx=6, pady=6)
        tk.Entry(self.admin_tab, textvariable=self.new_item_price).grid(row=1, column=1, padx=6, pady=6)

        tk.Button(self.admin_tab, text="Add Item", command=self._admin_add_item) \
            .grid(row=2, column=0, columnspan=2, pady=(4, 6))

        # Edit/Update/Clear buttons
        tk.Button(self.admin_tab, text="Edit Selected", command=self._admin_load_selected) \
            .grid(row=3, column=0, columnspan=2, pady=(0, 6))

        self.btn_update = tk.Button(self.admin_tab, text="Update", state="disabled", command=self._admin_update_item)
        self.btn_update.grid(row=4, column=0, columnspan=2, pady=(0, 6))

        tk.Button(self.admin_tab, text="Clear Form", command=self._admin_clear_form) \
            .grid(row=5, column=0, columnspan=2, pady=(0, 6))

        # Menu list & delete
        self.menu_list = tk.Listbox(self.admin_tab, height=14)
        self.menu_list.grid(row=0, column=2, rowspan=7, sticky="ns", padx=10, pady=6)
        self.menu_list.bind("<Double-1>", lambda e: self._admin_load_selected())

        tk.Button(self.admin_tab, text="Delete Selected", command=self._admin_delete_selected) \
            .grid(row=6, column=0, columnspan=2, pady=(0, 8))

        self._refresh_menu_list()

    def _refresh_menu_list(self):
        if not hasattr(self, "menu_list"):
            return
        self.menu_list.delete(0, tk.END)
        self.menu_items = self.db.get_menu_items()
        for _iid, name, price in self.menu_items:
            self.menu_list.insert(tk.END, f"{name} - ${price:.2f}")

    def _admin_clear_form(self):
        self.new_item_name.set("")
        self.new_item_price.set(0.0)
        self.editing_item_id = None
        self.btn_update.config(state="disabled")

    def _admin_add_item(self):
        name = self.new_item_name.get().strip()
        try:
            price = float(self.new_item_price.get())
        except Exception:
            messagebox.showerror("Error", "Price must be a number.")
            return
        if not name or price < 0:
            messagebox.showwarning("Invalid", "Enter a valid name and non-negative price.")
            return
        try:
            self.db.add_menu_item(name, price)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to add item: {e}")
            return
        self._admin_clear_form()
        self._refresh_menu_list()
        # refresh combobox in Orders tab
        self.menu_items = self.db.get_menu_items()
        self.item_combo["values"] = [n for _, n, _ in self.menu_items]

    def _admin_load_selected(self):
        sel = self.menu_list.curselection()
        if not sel:
            return
        item_text = self.menu_list.get(sel[0])
        item_name = item_text.split(" - $")[0]

        # find the selected item in cached list
        rec = next(((iid, n, p) for iid, n, p in self.menu_items if n == item_name), None)
        if not rec:
            return
        iid, n, p = rec
        self.editing_item_id = iid
        self.new_item_name.set(n)
        self.new_item_price.set(p)
        self.btn_update.config(state="normal")

    def _admin_update_item(self):
        if self.editing_item_id is None:
            return
        name = self.new_item_name.get().strip()
        try:
            price = float(self.new_item_price.get())
        except Exception:
            messagebox.showerror("Error", "Price must be a number.")
            return
        if not name or price < 0:
            messagebox.showwarning("Invalid", "Enter a valid name and non-negative price.")
            return
        try:
            self.db.update_menu_item(self.editing_item_id, name, price)
        except ValueError as e:
            if str(e) == "NAME_TAKEN":
                messagebox.showerror("Error", "Another item with this name already exists.")
                return
            messagebox.showerror("Error", f"{e}")
            return
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update item: {e}")
            return

        self._admin_clear_form()
        self._refresh_menu_list()
        # refresh combobox in Orders tab
        self.menu_items = self.db.get_menu_items()
        self.item_combo["values"] = [n for _, n, _ in self.menu_items]

    def _admin_delete_selected(self):
        sel = self.menu_list.curselection()
        if not sel:
            return
        item_text = self.menu_list.get(sel[0])
        item_name = item_text.split(" - $")[0]

        if not messagebox.askyesno("Confirm", f"Delete '{item_name}' from menu?"):
            return

        try:
            self.db.delete_menu_item_by_name(item_name)
        except ValueError as e:
            if str(e) == "ITEM_IN_USE":
                messagebox.showerror("Cannot delete", "This item is used in existing orders. You cannot delete it.")
            else:
                messagebox.showerror("Error", f"{e}")
            return
        except Exception as e:
            messagebox.showerror("Error", f"Failed to delete item: {e}")
            return

        self._admin_clear_form()
        self._refresh_menu_list()
        self.menu_items = self.db.get_menu_items()
        self.item_combo["values"] = [n for _, n, _ in self.menu_items]

    # ---------- account actions ----------
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
            messagebox.showerror("Error", "Passwords must match and be at least 6 characters.")
            return

        try:
            self.db.change_user_password(self.user_id, old, new1)
            messagebox.showinfo("Done", "Password changed.")
        except ValueError as e:
            if str(e) == "WRONG_OLD_PASSWORD":
                messagebox.showerror("Error", "Wrong current password.")
            else:
                messagebox.showerror("Error", f"{e}")
        except Exception as e:
            messagebox.showerror("Error", f"{e}")

    def _change_admin_code(self):
        if self.role != "admin":
            return
        new1 = simpledialog.askstring("Admin Access Code", "New admin access code:", show="*", parent=self)
        if new1 is None:
            return
        new2 = simpledialog.askstring("Admin Access Code", "Repeat new admin access code:", show="*", parent=self)
        if new2 is None:
            return

        if new1 != new2 or len(new1) < 4:
            messagebox.showerror("Error", "Codes must match and be at least 4 characters.")
            return

        try:
            self.db.change_admin_access_code(self.role, new1)
            messagebox.showinfo("Done", "Admin access code updated.")
        except Exception as e:
            messagebox.showerror("Error", f"{e}")

    # ---------- lifecycle ----------
    def _logout(self):
        try:
            self.on_logout()
        finally:
            self.destroy()
