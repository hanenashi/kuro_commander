import os
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, colorchooser
import string
import shutil
import json
from datetime import datetime
import tkinter.font as tkfont

ADB_PATH = r"C:\Users\hanenashi\AppData\Local\Android\Sdk\platform-tools\adb.exe"
PIXEL_PATH = "/storage/emulated/0"
CAMERA_PATH = f"{PIXEL_PATH}/DCIM/Camera"
SETTINGS_FILE = "kuro_settings.json"

# --------- Skins (defaults) ----------
DEFAULT_SKINS = {
    "Blue": {
        "bg": "#001a66", "fg": "#f6e27f", "muted": "#a9b7c6",
        "panel_bg": "#001a66", "row_bg": "#001a66", "row_alt": "#002080",
        "sel_bg": "#2947d8", "sel_fg": "#ffffff", "grid": "#335",
        "button": "#223b8f", "button_fg": "#f0f0f0", "status_bg": "#00164f",
        "heading_bg": "#223b8f", "heading_fg": "#f0f0f0"
    },
    "Dark": {
        "bg": "#121212", "fg": "#e0e0e0", "muted": "#9aa0a6",
        "panel_bg": "#121212", "row_bg": "#121212", "row_alt": "#1a1a1a",
        "sel_bg": "#2d5a8b", "sel_fg": "#ffffff", "grid": "#2a2a2a",
        "button": "#2a2a2a", "button_fg": "#e0e0e0", "status_bg": "#0e0e0e",
        "heading_bg": "#2a2a2a", "heading_fg": "#e0e0e0"
    },
    "White": {
        "bg": "#f7f7f7", "fg": "#222", "muted": "#666",
        "panel_bg": "#f7f7f7", "row_bg": "#ffffff", "row_alt": "#f0f0f0",
        "sel_bg": "#cce1ff", "sel_fg": "#000000", "grid": "#dddddd",
        "button": "#e6e6e6", "button_fg": "#111", "status_bg": "#efefef",
        "heading_bg": "#e6e6e6", "heading_fg": "#111"
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
        self.root.title("🐾 Kuro Commander 3.4")
        self.root.geometry("1200x640")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.left_type = tk.StringVar()
        self.right_type = tk.StringVar()
        self.left_path = os.getcwd()
        self.right_path = PIXEL_PATH

        # theme + font
        self.skin_name = tk.StringVar(value="Blue")
        self.skin_overrides = {}
        self.status_var = tk.StringVar(value="Ready")
        self.last_active_side = "left"

        self.font_family = tk.StringVar(value="Segoe UI")
        self.font_bold = tk.BooleanVar(value=False)
        self.ui_font = tkfont.Font(family=self.font_family.get(), size=10,
                                   weight=("bold" if self.font_bold.get() else "normal"))
        self.heading_font = tkfont.Font(family=self.font_family.get(), size=10, weight="bold")

        self.load_settings()
        self.init_ui()
        # Trees exist now; safe to apply styles
        self.apply_skin()
        self.refresh_panel("left", keep_focus=True)
        self.refresh_panel("right", keep_focus=False)
        self.bind_keys()
        self._set_active_styles("left")

    # ---------- UI ----------
    def init_ui(self):
        self.paned = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True)

        # Left pane
        self.left_frame = ttk.Frame(self.paned); self.paned.add(self.left_frame, weight=1)
        self.left_header = ttk.Frame(self.left_frame); self.left_header.pack(fill=tk.X, padx=6, pady=(6,2))
        self.left_selector = ttk.Combobox(self.left_header, textvariable=self.left_type, state="readonly", width=8, takefocus=0)
        self.left_selector['values'] = self.list_sources()
        self.left_selector.bind("<<ComboboxSelected>>", lambda e: self.switch_source("left"))
        self.left_selector.pack(side=tk.LEFT)
        self.left_breadcrumb = ttk.Label(self.left_header, text="", anchor="w")
        self.left_breadcrumb.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8,0))
        self.left_tree = self._make_tree(self.left_frame, "left")
        self.left_tree.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0,6))

        # Right pane
        self.right_frame = ttk.Frame(self.paned); self.paned.add(self.right_frame, weight=1)
        self.right_header = ttk.Frame(self.right_frame); self.right_header.pack(fill=tk.X, padx=6, pady=(6,2))
        self.right_selector = ttk.Combobox(self.right_header, textvariable=self.right_type, state="readonly", width=8, takefocus=0)
        self.right_selector['values'] = self.list_sources()
        self.right_selector.bind("<<ComboboxSelected>>", lambda e: self.switch_source("right"))
        self.right_selector.pack(side=tk.LEFT)
        self.right_breadcrumb = ttk.Label(self.right_header, text="", anchor="w")
        self.right_breadcrumb.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8,0))
        self.right_tree = self._make_tree(self.right_frame, "right")
        self.right_tree.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0,6))

        # Toolbar (bottom, includes Settings)
        self.button_frame = ttk.Frame(self.root, takefocus=0)
        self.button_frame.pack(pady=(0,2))
        ttk.Button(self.button_frame, text="← Copy ←", command=lambda: self._copy_toolbar("right","left"), takefocus=0).pack(side=tk.LEFT, padx=2)
        ttk.Button(self.button_frame, text="→ Copy →", command=lambda: self._copy_toolbar("left","right"), takefocus=0).pack(side=tk.LEFT, padx=2)
        ttk.Button(self.button_frame, text="📸 Copy to Camera", command=self._copy_to_camera_toolbar, takefocus=0).pack(side=tk.LEFT, padx=6)
        ttk.Button(self.button_frame, text="Delete", command=self._delete_toolbar, takefocus=0).pack(side=tk.LEFT, padx=2)
        ttk.Button(self.button_frame, text="Rename", command=self._rename_toolbar, takefocus=0).pack(side=tk.LEFT, padx=2)
        ttk.Button(self.button_frame, text="New Folder", command=self.new_folder, takefocus=0).pack(side=tk.LEFT, padx=6)
        ttk.Button(self.button_frame, text="🔁 Rescan Media", command=self.rescan_media, takefocus=0).pack(side=tk.LEFT, padx=6)
        ttk.Button(self.button_frame, text="Refresh", command=self.refresh_all, takefocus=0).pack(side=tk.LEFT, padx=2)
        ttk.Button(self.button_frame, text="⚙️ Settings", command=self.open_settings, takefocus=0).pack(side=tk.RIGHT, padx=8)

        # Status
        status = ttk.Label(self.root, textvariable=self.status_var, anchor="w", style="Status.TLabel")
        status.pack(fill=tk.X, side=tk.BOTTOM)

        if not self.left_type.get():  self.left_type.set("C:\\")
        if not self.right_type.get(): self.right_type.set("Pixel8")

    def _make_tree(self, parent, side):
        tree = ttk.Treeview(parent, columns=self.COLS, show="headings",
                            selectmode="extended", style="Inactive.Treeview")
        tree.heading("Name", text="Name"); tree.heading("Ext", text="Ext")
        tree.heading("Size", text="Size"); tree.heading("Date", text="Date")
        tree.column("Name", width=360, anchor="w", stretch=True)
        tree.column("Ext",  width=80,  anchor="w", stretch=False)
        tree.column("Size", width=100, anchor="e", stretch=False)
        tree.column("Date", width=150, anchor="e", stretch=False)

        tree.bind("<Double-1>", lambda e, s=side: self.enter(s))
        tree.bind("<Return>",   lambda e, s=side: (self.enter(s), "break"))
        tree.bind("<BackSpace>",lambda e, s=side: (self.navigate_up(s), "break"))
        tree.bind("<FocusIn>",  lambda e, s=side: (self._set_last_active(s), self._set_active_styles(s)))
        tree.bind("<Button-1>", lambda e, s=side: (tree.focus_set(), self._set_last_active(s), self._set_active_styles(s)))
        tree.bind("<Button-3>", lambda e, s=side: (tree.focus_set(), self._set_last_active(s), self._set_active_styles(s), self.context_menu(s, e)))

        tree.tag_configure("odd", background="#ffffff"); tree.tag_configure("even", background="#ffffff")
        return tree

    # ---------- Skin / Font ----------
    def current_skin(self):
        base = dict(DEFAULT_SKINS.get(self.skin_name.get(), DEFAULT_SKINS["Blue"]))
        for k, v in self.skin_overrides.get(self.skin_name.get(), {}).items():
            base[k] = v
        return base

    def apply_skin(self):
        theme = self.current_skin()
        self.root.configure(bg=theme["bg"])

        # fonts
        self.ui_font.config(family=self.font_family.get(), size=10,
                            weight=("bold" if self.font_bold.get() else "normal"))
        self.heading_font.config(family=self.font_family.get(), size=10, weight="bold")

        style = ttk.Style(self.root); style.theme_use("clam")
        style.configure("TFrame", background=theme["bg"])
        style.configure("TLabel", background=theme["bg"], foreground=theme["fg"], font=self.ui_font)
        style.configure("TButton", background=theme["button"], foreground=theme["button_fg"], padding=6, font=self.ui_font)
        style.map("TButton", background=[("active", theme["sel_bg"])], foreground=[("active", theme["sel_fg"])])

        for name, sel_bg, sel_fg in (
            ("Active.Treeview", theme["sel_bg"], theme["sel_fg"]),
            ("Inactive.Treeview", theme["row_bg"], theme["fg"]),
        ):
            style.configure(name,
                            background=theme["row_bg"], fieldbackground=theme["panel_bg"],
                            foreground=theme["fg"], bordercolor=theme["grid"],
                            rowheight=22, font=self.ui_font)
            style.map(name, background=[("selected", sel_bg)], foreground=[("selected", sel_fg)])
        style.configure("Treeview.Heading", background=theme["heading_bg"],
                        foreground=theme["heading_fg"], font=self.heading_font)
        style.configure("Status.TLabel", background=theme["status_bg"],
                        foreground=theme["muted"], padding=4, font=self.ui_font)

        # Trees might not exist in weird timing; guard them
        lt = getattr(self, "left_tree", None)
        rt = getattr(self, "right_tree", None)
        if lt: self._refresh_row_colors(lt)
        if rt: self._refresh_row_colors(rt)
        if lt and rt: self._set_active_styles(self.last_active_side)
        if getattr(self, "left_breadcrumb", None):  self.update_breadcrumb("left")
        if getattr(self, "right_breadcrumb", None): self.update_breadcrumb("right")

    # ---------- Settings ----------
    def open_settings(self):
        if hasattr(self, "_settings") and self._settings.winfo_exists():
            self._settings.lift(); return
        self._settings = tk.Toplevel(self.root)
        self._settings.title("Settings"); self._settings.geometry("520x520"); self._settings.transient(self.root)

        wrapper = ttk.Frame(self._settings); wrapper.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        ttk.Label(wrapper, text="Skin").grid(row=0, column=0, sticky="w")
        skin_box = ttk.Combobox(wrapper, values=list(DEFAULT_SKINS.keys()),
                                state="readonly", textvariable=self.skin_name, width=12)
        skin_box.grid(row=0, column=1, sticky="w", pady=4)

        ttk.Label(wrapper, text="Font family").grid(row=1, column=0, sticky="w")
        families = sorted(set(tkfont.families()))
        font_box = ttk.Combobox(wrapper, values=families, state="readonly",
                                textvariable=self.font_family, width=22)
        font_box.grid(row=1, column=1, sticky="w", pady=4)
        bold_chk = ttk.Checkbutton(wrapper, text="Bold", variable=self.font_bold)
        bold_chk.grid(row=1, column=2, sticky="w")

        row = 2; self._color_vars = {}
        for key in ("bg","fg","muted","panel_bg","row_bg","row_alt","sel_bg","sel_fg",
                    "grid","button","button_fg","status_bg","heading_bg","heading_fg"):
            ttk.Label(wrapper, text=key).grid(row=row, column=0, sticky="w", pady=2)
            var = tk.StringVar(value=self.current_skin().get(key))
            self._color_vars[key] = var
            entry = ttk.Entry(wrapper, textvariable=var, width=18)
            entry.grid(row=row, column=1, sticky="w")
            ttk.Button(wrapper, text="Pick",
                       command=lambda k=key, v=var: self._pick_color(k, v)).grid(row=row, column=2, sticky="w", padx=6)
            row += 1

        btns = ttk.Frame(wrapper); btns.grid(row=row, column=0, columnspan=3, pady=(10,0), sticky="w")
        ttk.Button(btns, text="Apply", command=self._apply_settings).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Save", command=lambda: (self._apply_settings(), self._save_settings_to_disk())).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Reset Skin", command=self._reset_skin_overrides).pack(side=tk.LEFT, padx=12)

    def _pick_color(self, key, var):
        initial = var.get()
        _, hexv = colorchooser.askcolor(color=initial, parent=self._settings)
        if hexv: var.set(hexv)

    def _apply_settings(self):
        # update overrides for current skin
        skin = self.skin_name.get()
        self.skin_overrides.setdefault(skin, {})
        # if color vars exist, pull them (they do when opened from Settings)
        if hasattr(self, "_color_vars"):
            for k, var in self._color_vars.items():
                self.skin_overrides[skin][k] = var.get()
        self.apply_skin()
        self.refresh_all()

    def _reset_skin_overrides(self):
        skin = self.skin_name.get()
        if skin in self.skin_overrides: del self.skin_overrides[skin]
        if hasattr(self, "_color_vars"):
            for k, var in self._color_vars.items():
                var.set(self.current_skin()[k])
        self.apply_skin(); self.refresh_all()

    # ---------- Breadcrumbs ----------
    def update_breadcrumb(self, side):
        dtype, path, tree, label = self.get_panel_widgets(side, want_breadcrumb=True)
        if is_pixel(dtype):
            parts = [p for p in path.strip("/").split("/") if p]
            txt = "/" + ("" if not parts else " > " + " > ".join(parts))
        else:
            abs_path = os.path.abspath(path)
            drive, rest = os.path.splitdrive(abs_path)
            crumbs = [p for p in rest.split(os.sep) if p]
            txt = (drive or "C:") + "\\" + ("" if not crumbs else " > " + " > ".join(crumbs))
        label.config(text=txt)

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
        dtype, path, tree, _ = self.get_panel_widgets(side, want_breadcrumb=True)
        tree.delete(*tree.get_children())

        up = (path != "/") if is_pixel(dtype) else (os.path.abspath(path) != os.path.abspath(os.path.join(path, "..")))
        if up:
            self._insert_row(tree, {"Name":"..","Ext":"","Size":"","Date":""}, idx=0, tag="even")

        rows = self.scan_dir(dtype, path)
        for i, row in enumerate(rows, start=1 if up else 0):
            self._insert_row(tree, row, idx=i, tag=("odd" if i % 2 else "even"))

        self._ensure_selection(side)
        if keep_focus:
            tree.focus_set(); self._set_last_active(side); self._set_active_styles(side)
        self._refresh_row_colors(tree)
        self.update_breadcrumb(side)

    def _refresh_row_colors(self, tree):
        theme = self.current_skin()
        tree.tag_configure("even", background=theme["row_bg"], foreground=theme["fg"])
        tree.tag_configure("odd",  background=theme["row_alt"], foreground=theme["fg"])

    def _insert_row(self, tree, row, idx, tag):
        tree.insert("", "end", iid=f"r{idx}_{row['Name']}",
                    values=(row["Name"], row["Ext"], row["Size"], row["Date"]), tags=(tag,))

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

    # ---------- Active styles ----------
    def _set_last_active(self, side): self.last_active_side = side
    def _set_active_styles(self, active_side):
        lt = getattr(self, "left_tree", None); rt = getattr(self, "right_tree", None)
        if not (lt and rt): return
        if active_side == "left":
            lt.configure(style="Active.Treeview"); rt.configure(style="Inactive.Treeview")
        else:
            rt.configure(style="Active.Treeview"); lt.configure(style="Inactive.Treeview")

    # ---------- Selection helpers ----------
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
                self.right_tree.focus_set(); self._set_last_active("right"); self._set_active_styles("right")
            else:
                self.left_tree.focus_set(); self._set_last_active("left"); self._set_active_styles("left")
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
        tree.selection_set(tree.get_children())

    def clear_selection(self, side):
        _, _, tree = self.get_panel_widgets(side)
        tree.selection_remove(tree.selection()); self._ensure_selection(side)

    # ---------- Status ----------
    def set_status(self, msg: str):
        self.status_var.set(msg)
        # fade back to "Ready" after a short time
        self.root.after(2500, lambda: self.status_var.set("Ready"))

    # ---------- Persistence ----------
    def _save_settings_to_disk(self):
        data = {
            "left_type": self.left_type.get(), "left_path": self.left_path,
            "right_type": self.right_type.get(), "right_path": self.right_path,
            "geometry": self.root.winfo_geometry(),
            "skin": self.skin_name.get(), "skin_overrides": self.skin_overrides,
            "font_family": self.font_family.get(), "font_bold": self.font_bold.get(),
        }
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f: json.dump(data, f, indent=2)
        except Exception: pass

    def on_close(self):
        self._save_settings_to_disk()
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
                self.skin_name.set(data.get("skin", "Blue"))
                self.skin_overrides = data.get("skin_overrides", {})
                self.font_family.set(data.get("font_family", self.font_family.get()))
                self.font_bold.set(bool(data.get("font_bold", self.font_bold.get())))
            except Exception:
                pass

if __name__ == "__main__":
    root = tk.Tk()
    app = KuroCommander(root)
    root.mainloop()
