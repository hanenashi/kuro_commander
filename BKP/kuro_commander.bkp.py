import os
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import string
import shutil
import json
from datetime import datetime

ADB_PATH = r"C:\Users\hanenashi\AppData\Local\Android\Sdk\platform-tools\adb.exe"
PIXEL_PATH = "/storage/emulated/0"
CAMERA_PATH = f"{PIXEL_PATH}/DCIM/Camera"
SETTINGS_FILE = "kuro_settings.json"

# --------- Skins ----------
SKINS = {
    "Blue": {
        "bg": "#001a66", "fg": "#f6e27f", "muted": "#a9b7c6",
        "panel_bg": "#001a66", "row_bg": "#001a66", "row_alt": "#002080",
        "sel_bg": "#2947d8", "sel_fg": "#ffffff", "grid": "#335",
        "button": "#223b8f", "button_fg": "#f0f0f0", "status_bg": "#00164f"
    },
    "Dark": {
        "bg": "#121212", "fg": "#e0e0e0", "muted": "#9aa0a6",
        "panel_bg": "#121212", "row_bg": "#121212", "row_alt": "#1a1a1a",
        "sel_bg": "#2d5a8b", "sel_fg": "#ffffff", "grid": "#2a2a2a",
        "button": "#2a2a2a", "button_fg": "#e0e0e0", "status_bg": "#0e0e0e"
    },
    "White": {
        "bg": "#f7f7f7", "fg": "#222", "muted": "#666",
        "panel_bg": "#f7f7f7", "row_bg": "#ffffff", "row_alt": "#f0f0f0",
        "sel_bg": "#cce1ff", "sel_fg": "#000", "grid": "#ddd",
        "button": "#e6e6e6", "button_fg": "#111", "status_bg": "#efefef"
    },
}

def is_pixel(dtype: str) -> bool:
    return dtype == "Pixel8"

def join_path(dtype: str, base: str, name: str) -> str:
    if is_pixel(dtype):
        base = (base or "/").rstrip("/")
        name = name.strip("/")
        if name:
            return (base if base else "/") + ("" if base == "/" else "/") + name
        return base if base else "/"
    return os.path.join(base, name) if name else base

def human_size(n: int | None) -> str:
    if n is None: return ""
    units = ["B","K","M","G","T"]
    s = float(n); i = 0
    while s >= 1024 and i < len(units)-1:
        s /= 1024.0; i += 1
    return f"{int(s)} {units[i]}" if i == 0 else f"{s:.2f} {units[i]}"

def ts_to_str(ts: float | int | None) -> str:
    if ts is None: return ""
    try: return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
    except Exception: return ""

class KuroCommander:
    COLS = ("Name","Ext","Size","Date")

    def __init__(self, root):
        self.root = root
        self.root.title("🐾 Kuro Commander 3.1")
        self.root.geometry("1200x640")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.left_type = tk.StringVar()
        self.right_type = tk.StringVar()
        self.left_path = os.getcwd()
        self.right_path = PIXEL_PATH
        self.skin = tk.StringVar(value="Blue")

        self.status_var = tk.StringVar(value="Ready")
        self.last_active_side = "left"

        self.load_settings()
        self.init_ui()
        self.apply_skin(self.skin.get())
        self.refresh_panel("left", keep_focus=True)
        self.refresh_panel("right", keep_focus=False)
        self.bind_keys()

    # ---------- UI ----------
    def init_ui(self):
        top = ttk.Frame(self.root)
        top.pack(fill=tk.X)

        self.left_selector = ttk.Combobox(top, textvariable=self.left_type, state="readonly", width=8, takefocus=0)
        self.left_selector['values'] = self.list_sources()
        self.left_selector.bind("<<ComboboxSelected>>", lambda e: self.switch_source("left"))
        self.left_selector.pack(side=tk.LEFT, padx=(6,4), pady=4)

        self.left_breadcrumb = ttk.Frame(top, takefocus=0)
        self.left_breadcrumb.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,10))

        ttk.Button(top, text="⚙️ Settings", command=self.open_settings, takefocus=0).pack(side=tk.RIGHT, padx=6)

        self.right_selector = ttk.Combobox(top, textvariable=self.right_type, state="readonly", width=8, takefocus=0)
        self.right_selector['values'] = self.list_sources()
        self.right_selector.bind("<<ComboboxSelected>>", lambda e: self.switch_source("right"))
        self.right_selector.pack(side=tk.RIGHT, padx=(4,6), pady=4)

        self.right_breadcrumb = ttk.Frame(top, takefocus=0)
        self.right_breadcrumb.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10,0))

        self.paned = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True)
        self.left_frame = ttk.Frame(self.paned); self.right_frame = ttk.Frame(self.paned)
        self.paned.add(self.left_frame, weight=1); self.paned.add(self.right_frame, weight=1)

        self.left_tree = self._make_tree(self.left_frame, "left")
        self.right_tree = self._make_tree(self.right_frame, "right")

        self.button_frame = ttk.Frame(self.root, takefocus=0)
        self.button_frame.pack(pady=(2,2))
        ttk.Button(self.button_frame, text="← Copy ←", command=lambda: self._copy_toolbar("right","left"), takefocus=0).pack(side=tk.LEFT, padx=2)
        ttk.Button(self.button_frame, text="→ Copy →", command=lambda: self._copy_toolbar("left","right"), takefocus=0).pack(side=tk.LEFT, padx=2)
        ttk.Button(self.button_frame, text="📸 Copy to Camera", command=self._copy_to_camera_toolbar, takefocus=0).pack(side=tk.LEFT, padx=6)
        ttk.Button(self.button_frame, text="Delete", command=self._delete_toolbar, takefocus=0).pack(side=tk.LEFT, padx=2)
        ttk.Button(self.button_frame, text="Rename", command=self._rename_toolbar, takefocus=0).pack(side=tk.LEFT, padx=2)
        ttk.Button(self.button_frame, text="New Folder", command=self.new_folder, takefocus=0).pack(side=tk.LEFT, padx=6)
        ttk.Button(self.button_frame, text="🔁 Rescan Media", command=self.rescan_media, takefocus=0).pack(side=tk.LEFT, padx=6)
        ttk.Button(self.button_frame, text="Refresh", command=self.refresh_all, takefocus=0).pack(side=tk.LEFT, padx=2)

        status = ttk.Label(self.root, textvariable=self.status_var, anchor="w")
        status.pack(fill=tk.X, side=tk.BOTTOM)

        if not self.left_type.get():  self.left_type.set("C:\\")
        if not self.right_type.get(): self.right_type.set("Pixel8")

    def _make_tree(self, parent, side):
        tree = ttk.Treeview(parent, columns=self.COLS, show="headings", selectmode="extended")
        tree.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0,6))

        tree.heading("Name", text="Name")
        tree.heading("Ext", text="Ext")
        tree.heading("Size", text="Size")
        tree.heading("Date", text="Date")
        tree.column("Name", width=360, anchor="w", stretch=True)
        tree.column("Ext",  width=80,  anchor="w", stretch=False)
        tree.column("Size", width=100, anchor="e", stretch=False)
        tree.column("Date", width=150, anchor="e", stretch=False)

        tree.bind("<Double-1>", lambda e, s=side: self.enter(s))
        tree.bind("<Return>",   lambda e, s=side: (self.enter(s), "break"))
        tree.bind("<BackSpace>",lambda e, s=side: (self.navigate_up(s), "break"))
        tree.bind("<FocusIn>",  lambda e, s=side: self._set_last_active(s))
        tree.bind("<Button-1>", lambda e, s=side: (tree.focus_set(), self._set_last_active(s)))
        tree.bind("<Button-3>", lambda e, s=side: self.context_menu(s, e))

        # Valid placeholders; real colors applied later by _refresh_row_colors
        tree.tag_configure("odd", background="#ffffff")
        tree.tag_configure("even", background="#ffffff")
        return tree

    def apply_skin(self, name: str):
        theme = SKINS.get(name, SKINS["Blue"])
        self.root.configure(bg=theme["bg"])

        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background=theme["bg"])
        style.configure("TLabel", background=theme["bg"], foreground=theme["fg"])
        style.configure("TButton", background=theme["button"], foreground=theme["button_fg"], padding=6)
        style.map("TButton", background=[("active", theme["sel_bg"])], foreground=[("active", theme["sel_fg"])])

        style.configure("Treeview",
                        background=theme["row_bg"],
                        fieldbackground=theme["panel_bg"],
                        foreground=theme["fg"],
                        bordercolor=theme["grid"],
                        rowheight=22)
        style.configure("Treeview.Heading", background=theme["button"], foreground=theme["button_fg"])
        style.map("Treeview", background=[("selected", theme["sel_bg"])],
                               foreground=[("selected", theme["sel_fg"])])

        style.configure("Status.TLabel", background=theme["status_bg"], foreground=theme["muted"], padding=4)
        for w in self.root.pack_slaves():
            if isinstance(w, ttk.Label) and w.cget("textvariable") == str(self.status_var):
                w.configure(style="Status.TLabel")

        self.refresh_all()

    def open_settings(self):
        if hasattr(self, "_settings") and self._settings.winfo_exists():
            self._settings.lift(); return
        self._settings = tk.Toplevel(self.root)
        self._settings.title("Settings"); self._settings.geometry("360x180"); self._settings.transient(self.root)

        ttk.Label(self._settings, text="Skin").pack(anchor="w", padx=12, pady=(12,4))
        skin_box = ttk.Combobox(self._settings, values=list(SKINS.keys()), state="readonly", textvariable=self.skin)
        skin_box.pack(fill=tk.X, padx=12)
        ttk.Button(self._settings, text="Apply", command=lambda: self.apply_skin(self.skin.get())).pack(pady=12)
        ttk.Label(self._settings, text="Edit colors in code at SKINS[skin]").pack(anchor="w", padx=12)

    def set_status(self, msg: str):
        self.status_var.set(msg)
        self.root.after(3000, lambda: self.status_var.set("Ready"))

    def build_breadcrumb(self, side):
        dtype, path, tree, bc_frame = self.get_panel_widgets(side, want_breadcrumb=True)
        for w in bc_frame.winfo_children(): w.destroy()

        def add_btn(text, go_path):
            b = ttk.Button(bc_frame, text=text, style="TButton", command=lambda: self.navigate_to(side, go_path), width=0, takefocus=0)
            b.pack(side=tk.LEFT, padx=(0,2))

        if is_pixel(dtype):
            parts = [p for p in path.strip("/").split("/") if p]
            add_btn("/", "/"); cur = ""
            for p in parts:
                cur = join_path(dtype, cur or "/", p); add_btn(p, cur)
        else:
            abs_path = os.path.abspath(path)
            drive, rest = os.path.splitdrive(abs_path); drive = drive or "C:"
            add_btn(drive + "\\", drive + "\\")
            crumbs = [p for p in rest.split(os.sep) if p]
            cur = drive + "\\"
            for p in crumbs:
                cur = os.path.join(cur, p); add_btn(p, cur)

    # ---------- Data ----------
    def list_sources(self):
        drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
        return drives + ["Pixel8"]

    def get_panel_widgets(self, side, want_breadcrumb=False):
        if side == "left":
            dtype, path, tree, bc = self.left_type.get(), self.left_path, self.left_tree, self.left_breadcrumb
        else:
            dtype, path, tree, bc = self.right_type.get(), self.right_path, self.right_tree, self.right_breadcrumb
        return (dtype, path, tree, bc) if want_breadcrumb else (dtype, path, tree)

    def switch_source(self, side):
        dtype = self.left_type.get() if side == "left" else self.right_type.get()
        path = PIXEL_PATH if dtype == "Pixel8" else dtype
        if side == "left": self.left_path = path
        else:              self.right_path = path
        self.refresh_panel(side, keep_focus=True)

    def refresh_all(self):
        self.refresh_panel("left")
        self.refresh_panel("right")
        self._ensure_selection(self.last_active_side)
        self.set_status("Refreshed")

    def refresh_panel(self, side, keep_focus=False):
        dtype, path, tree, bc = self.get_panel_widgets(side, want_breadcrumb=True)
        tree.delete(*tree.get_children())
        self.build_breadcrumb(side)

        # add ".."
        up = (path != "/") if is_pixel(dtype) else (os.path.abspath(path) != os.path.abspath(os.path.join(path, "..")))
        if up:
            self._insert_row(tree, {"Name":"..","Ext":"","Size":"","Date":""}, idx=0, tag="even")

        rows = self.scan_dir(dtype, path)
        for i, row in enumerate(rows, start=1 if up else 0):
            self._insert_row(tree, row, idx=i, tag=("odd" if i % 2 else "even"))

        self._ensure_selection(side)
        if keep_focus:
            tree.focus_set(); self._set_last_active(side)
        self._refresh_row_colors(tree)

    def _refresh_row_colors(self, tree):
        theme = SKINS.get(self.skin.get(), SKINS["Blue"])
        tree.tag_configure("even", background=theme["row_bg"])
        tree.tag_configure("odd",  background=theme["row_alt"])

    def _insert_row(self, tree, row, idx, tag):
        values = (row["Name"], row["Ext"], row["Size"], row["Date"])
        tree.insert("", "end", iid=f"r{idx}_{row['Name']}", values=values, tags=(tag,))

    def _ensure_selection(self, side):
        _, _, tree = self.get_panel_widgets(side)
        kids = tree.get_children()
        if kids and not tree.selection():
            tree.selection_set(kids[0]); tree.focus(kids[0]); tree.see(kids[0])

    # --------- Scanners ----------
    def scan_dir(self, dtype, path):
        rows = []
        if not is_pixel(dtype):
            try:
                with os.scandir(path) as it:
                    for entry in it:
                        is_dir = entry.is_dir()
                        name = entry.name
                        ext = "<DIR>" if is_dir else os.path.splitext(name)[1][1:].upper()
                        try:
                            st = entry.stat()
                            size = "" if is_dir else human_size(st.st_size)
                            date = ts_to_str(st.st_mtime)
                        except Exception:
                            size = "" if is_dir else ""
                            date = ""
                        rows.append({"Name": name, "Ext": ext, "Size": size, "Date": date})
            except Exception as e:
                messagebox.showerror("File Error", str(e))
        else:
            try:
                ls = subprocess.run([ADB_PATH, "shell", "ls", "-p", path], capture_output=True)
                names = [n for n in ls.stdout.decode("utf-8", errors="replace").splitlines() if n]
                for n in names:
                    is_dir = n.endswith("/")
                    clean = n.rstrip("/")
                    ext = "<DIR>" if is_dir else (os.path.splitext(clean)[1][1:].upper())
                    size = ""; mtime = ""
                    full = f"{path.rstrip('/')}/{clean}"
                    try:
                        if is_dir:
                            st = subprocess.run([ADB_PATH, "shell", "toybox", "stat", "-c", "%Y", full], capture_output=True, timeout=2)
                            ts = st.stdout.decode().strip()
                            mtime = ts_to_str(float(ts)) if ts else ""
                        else:
                            st = subprocess.run([ADB_PATH, "shell", "toybox", "stat", "-c", "%s|%Y", full], capture_output=True, timeout=2)
                            out = st.stdout.decode().strip()
                            if "|" in out:
                                s, ts = out.split("|",1)
                                size = human_size(int(s)); mtime = ts_to_str(float(ts))
                    except Exception:
                        pass
                    rows.append({"Name": clean, "Ext": ext, "Size": size, "Date": mtime})
            except Exception as e:
                messagebox.showerror("ADB Error", str(e))
        rows.sort(key=lambda r: (0 if r["Ext"] == "<DIR>" else 1, r["Name"].lower()))
        return rows

    # ---------- Navigation ----------
    def enter(self, side):
        dtype, path, tree = self.get_panel_widgets(side)
        sel = tree.selection()
        if not sel: return
        name = tree.item(sel[0])["values"][0]
        if name == "..": self.navigate_up(side); return
        ext = tree.item(sel[0])["values"][1]
        if ext == "<DIR>":
            self.navigate_to(side, join_path(dtype, path, name))

    def navigate_to(self, side, new_path):
        if side == "left": self.left_path = new_path
        else:              self.right_path = new_path
        self.refresh_panel(side, keep_focus=True)

    def navigate_up(self, side):
        dtype, path, _ = self.get_panel_widgets(side)
        if is_pixel(dtype):
            new_path = "/".join(path.rstrip("/").split("/")[:-1]) or "/"
        else:
            new_path = os.path.abspath(os.path.join(path, ".."))
        self.navigate_to(side, new_path)

    # ---------- Selection helpers ----------
    def _set_last_active(self, side): self.last_active_side = side

    def pane_with_selection(self):
        for side in ("left","right"):
            _, _, tree = self.get_panel_widgets(side)
            if tree.selection(): return side
        return None

    def target_side_for_toolbar(self):
        return self.pane_with_selection() or self.last_active_side

    def selected_items(self, side):
        dtype, path, tree = self.get_panel_widgets(side)
        names = []
        for item in tree.selection():
            vals = tree.item(item)["values"]
            if vals and vals[0] != "..":
                names.append(vals[0])
        return dtype, path, names

    # ---------- Operations ----------
    def _copy_toolbar(self, from_side, to_side):
        side_sel = self.pane_with_selection()
        if side_sel:
            self.copy_files(side_sel, "right" if side_sel=="left" else "left")
        else:
            self.copy_files(from_side, to_side)

    def copy_files(self, from_side, to_side):
        from_dtype, from_path, names = self.selected_items(from_side)
        to_dtype, to_path, _ = self.get_panel_widgets(to_side)
        if not names:
            self.set_status("Nothing selected to copy."); return
        for name in names:
            src = join_path(from_dtype, from_path, name)
            dst = join_path(to_dtype, to_path, name)
            try:
                if is_pixel(from_dtype) and not is_pixel(to_dtype):
                    subprocess.run([ADB_PATH, "pull", src, dst])
                elif not is_pixel(from_dtype) and is_pixel(to_dtype):
                    subprocess.run([ADB_PATH, "push", src, dst])
                elif not is_pixel(from_dtype) and not is_pixel(to_dtype):
                    if os.path.isdir(src): shutil.copytree(src, dst, dirs_exist_ok=True)
                    else: shutil.copy2(src, dst)
                else:
                    subprocess.run([ADB_PATH, "shell", "cp", src, dst])
            except Exception as e:
                messagebox.showerror("Copy Error", f"{name}: {e}")
        self.refresh_panel(to_side); self.set_status(f"Copied {len(names)} item(s).")

    def _copy_to_camera_toolbar(self):
        self.copy_to_camera_from(self.target_side_for_toolbar())

    def copy_to_camera_from(self, side):
        from_dtype, from_path, names = self.selected_items(side)
        if not names:
            messagebox.showinfo("Nothing Selected", "No files selected to copy."); return
        copied = False
        for name in names:
            src = join_path(from_dtype, from_path, name)
            dst = f"{CAMERA_PATH}/{name}"
            try:
                if is_pixel(from_dtype): subprocess.run([ADB_PATH, "shell", "cp", src, dst])
                else: subprocess.run([ADB_PATH, "push", src, dst])
                copied = True
            except Exception as e:
                messagebox.showerror("Copy to Camera Error", f"{name}: {e}")
        if copied:
            self.rescan_media(); self.set_status(f"Copied {len(names)} item(s) to Camera.")

    def rescan_media(self):
        try:
            subprocess.run([ADB_PATH,"shell","content","call","--method","scan_volume","--uri","content://media","--arg","external_primary"])
            messagebox.showinfo("Scan Complete", "Media scan triggered successfully.")
            self.set_status("Media scan requested.")
        except Exception as e:
            messagebox.showerror("Scan Failed", str(e))

    def _delete_toolbar(self):
        self.delete_files_from(self.target_side_for_toolbar())

    def delete_files(self): self._delete_toolbar()

    def delete_files_from(self, side):
        dtype, path, names = self.selected_items(side)
        if not names: self.set_status("Nothing selected to delete."); return
        if not messagebox.askyesno("Delete", f"Delete {len(names)} selected item(s) in {side} pane?"): return
        for name in names:
            full = join_path(dtype, path, name)
            try:
                if is_pixel(dtype): subprocess.run([ADB_PATH, "shell", "rm", "-rf", full])
                else:
                    if os.path.isdir(full): shutil.rmtree(full)
                    else: os.remove(full)
            except Exception as e:
                messagebox.showerror("Delete Error", f"{name}: {e}")
        self.refresh_panel(side, keep_focus=True); self.set_status(f"Deleted {len(names)} item(s).")

    def _rename_toolbar(self):
        self.rename_files_from(self.target_side_for_toolbar())

    def rename_files(self): self._rename_toolbar()

    def rename_files_from(self, side):
        dtype, path, names = self.selected_items(side)
        if not names: self.set_status("Nothing selected to rename."); return
        suffix = simpledialog.askstring("Rename", "Append this to selected filenames:")
        if suffix is None: return
        count = 0
        for name in names:
            base, ext = os.path.splitext(name)
            new_name = base + suffix + ext
            src = join_path(dtype, path, name)
            dst = join_path(dtype, path, new_name)
            try:
                if is_pixel(dtype): subprocess.run([ADB_PATH, "shell", "mv", src, dst])
                else: os.rename(src, dst)
                count += 1
            except Exception as e:
                messagebox.showerror("Rename Error", f"{name}: {e}")
        self.refresh_panel(side, keep_focus=True); self.set_status(f"Renamed {count} item(s).")

    def new_folder(self):
        side = self.target_side_for_toolbar()
        dtype, path, _ = self.get_panel_widgets(side)
        name = simpledialog.askstring("New Folder", "Folder name:")
        if not name: return
        full = join_path(dtype, path, name)
        try:
            if is_pixel(dtype): subprocess.run([ADB_PATH, "shell", "mkdir", "-p", full])
            else: os.makedirs(full, exist_ok=True)
            self.refresh_panel(side, keep_focus=True)
            self.set_status(f"Created folder: {name}")
        except Exception as e:
            messagebox.showerror("New Folder Error", str(e))

    # ---------- Context Menu ----------
    def context_menu(self, side, event):
        _, _, tree = self.get_panel_widgets(side)
        tree.focus_set(); self._set_last_active(side)
        menu = tk.Menu(self.root, tearoff=0)
        other = "right" if side == "left" else "left"
        menu.add_command(label="Open", command=lambda: self.enter(side))
        menu.add_command(label="Up", command=lambda: self.navigate_up(side))
        menu.add_separator()
        menu.add_command(label=f"Copy → {other}", command=lambda: self.copy_files(side, other))
        menu.add_command(label="Delete", command=lambda: self.delete_files_from(side))
        menu.add_command(label="Rename", command=lambda: self.rename_files_from(side))
        menu.add_separator()
        menu.add_command(label="New Folder", command=self.new_folder)
        menu.add_command(label="Refresh", command=lambda: self.refresh_panel(side, keep_focus=True))
        try: menu.tk_popup(event.x_root, event.y_root)
        finally: menu.grab_release()

    # ---------- Keys ----------
    def bind_keys(self):
        def tab_switch(e):
            if self.root.focus_get() is self.left_tree:
                self.right_tree.focus_set(); self._set_last_active("right")
            else:
                self.left_tree.focus_set(); self._set_last_active("left")
            return "break"
        self.root.bind_all("<Tab>", tab_switch)

        for tree, side in ((self.left_tree,"left"),(self.right_tree,"right")):
            tree.bind("<Control-a>", lambda e, s=side: (self.select_all(s), "break"))
            tree.bind("+", lambda e, s=side: (self.select_all(s), "break"))
            tree.bind("-", lambda e, s=side: (self.clear_selection(s), "break"))

        self.root.bind_all("<Delete>", lambda e: (self._delete_toolbar(), "break"))
        self.root.bind_all("<F2>",     lambda e: (self._rename_toolbar(), "break"))
        self.root.bind_all("<F5>",     lambda e: (self.refresh_all(), "break"))
        self.root.bind_all("<Control-c>", lambda e: (self._copy_toolbar("left","right"), "break"))
        self.root.bind_all("<Control-m>", lambda e: (self.rescan_media(), "break"))
        self.root.bind_all("<Control-n>", lambda e: (self.new_folder(), "break"))

    def select_all(self, side):
        _, _, tree = self.get_panel_widgets(side)
        kids = tree.get_children(); tree.selection_set(kids)

    def clear_selection(self, side):
        _, _, tree = self.get_panel_widgets(side)
        tree.selection_remove(tree.selection()); self._ensure_selection(side)

    # ---------- Persistence ----------
    def on_close(self):
        data = {
            "left_type": self.left_type.get(), "left_path": self.left_path,
            "right_type": self.right_type.get(), "right_path": self.right_path,
            "geometry": self.root.winfo_geometry(), "skin": self.skin.get()
        }
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f: json.dump(data, f, indent=2)
        except Exception: pass
        self.root.destroy()

    def load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.left_type.set(data.get("left_type", "C:\\"))
                self.left_path = data.get("left_path", os.getcwd())
                self.right_type.set(data.get("right_type", "Pixel8"))
                self.right_path = data.get("right_path", PIXEL_PATH)
                if (g := data.get("geometry")): self.root.geometry(g)
                self.skin.set(data.get("skin", "Blue"))
            except Exception:
                pass

if __name__ == "__main__":
    root = tk.Tk()
    app = KuroCommander(root)
    root.mainloop()
