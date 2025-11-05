import os
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import string
import shutil
import json

ADB_PATH = r"C:\Users\hanenashi\AppData\Local\Android\Sdk\platform-tools\adb.exe"
PIXEL_PATH = "/storage/emulated/0"
CAMERA_PATH = f"{PIXEL_PATH}/DCIM/Camera"
SETTINGS_FILE = "kuro_settings.json"

class KuroCommander:
    def __init__(self, root):
        self.root = root
        self.root.title("🐾 Kuro Commander 2.6")
        self.root.geometry("1100x600")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.left_type = tk.StringVar()
        self.right_type = tk.StringVar()
        self.left_path = os.getcwd()
        self.right_path = PIXEL_PATH

        self.load_settings()
        self.init_ui()
        self.refresh_panel("left")
        self.refresh_panel("right")

    def init_ui(self):
        self.paned = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True)

        self.left_frame = ttk.Frame(self.paned)
        self.right_frame = ttk.Frame(self.paned)
        self.paned.add(self.left_frame, weight=1)
        self.paned.add(self.right_frame, weight=1)

        self.left_selector = ttk.Combobox(self.left_frame, textvariable=self.left_type, state="readonly")
        self.left_selector['values'] = self.list_sources()
        self.left_selector.bind("<<ComboboxSelected>>", lambda e: self.switch_source("left"))
        self.left_selector.pack(fill=tk.X)

        self.left_path_label = ttk.Label(self.left_frame, text=self.left_path)
        self.left_path_label.pack(fill=tk.X)

        self.left_listbox = tk.Listbox(self.left_frame, selectmode=tk.EXTENDED)
        self.left_listbox.pack(fill=tk.BOTH, expand=True)
        self.left_listbox.bind("<Double-Button-1>", lambda e: self.enter("left"))

        self.right_selector = ttk.Combobox(self.right_frame, textvariable=self.right_type, state="readonly")
        self.right_selector['values'] = self.list_sources()
        self.right_selector.bind("<<ComboboxSelected>>", lambda e: self.switch_source("right"))
        self.right_selector.pack(fill=tk.X)

        self.right_path_label = ttk.Label(self.right_frame, text=self.right_path)
        self.right_path_label.pack(fill=tk.X)

        self.right_listbox = tk.Listbox(self.right_frame, selectmode=tk.EXTENDED)
        self.right_listbox.pack(fill=tk.BOTH, expand=True)
        self.right_listbox.bind("<Double-Button-1>", lambda e: self.enter("right"))

        self.button_frame = ttk.Frame(self.root)
        self.button_frame.pack()
        ttk.Button(self.button_frame, text="→ Copy →", command=self.copy_files).pack(side=tk.LEFT)
        ttk.Button(self.button_frame, text="📸 Copy to Camera", command=self.copy_to_camera).pack(side=tk.LEFT)
        ttk.Button(self.button_frame, text="Delete", command=self.delete_files).pack(side=tk.LEFT)
        ttk.Button(self.button_frame, text="Rename", command=self.rename_files).pack(side=tk.LEFT)
        ttk.Button(self.button_frame, text="🔁 Rescan Media", command=self.rescan_media).pack(side=tk.LEFT)
        ttk.Button(self.button_frame, text="Refresh", command=self.refresh_all).pack(side=tk.LEFT)

    def list_sources(self):
        drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
        return drives + ["Pixel8"]

    def get_panel_info(self, side):
        t = self.left_type.get() if side == "left" else self.right_type.get()
        p = self.left_path if side == "left" else self.right_path
        lb = self.left_listbox if side == "left" else self.right_listbox
        label = self.left_path_label if side == "left" else self.right_path_label
        return t, p, lb, label

    def switch_source(self, side):
        dtype = self.left_type.get() if side == "left" else self.right_type.get()
        path = PIXEL_PATH if dtype == "Pixel8" else dtype
        if side == "left":
            self.left_path = path
        else:
            self.right_path = path
        self.refresh_panel(side)

    def refresh_all(self):
        self.refresh_panel("left")
        self.refresh_panel("right")

    def refresh_panel(self, side):
        dtype, path, lb, label = self.get_panel_info(side)
        label.config(text=path)
        lb.delete(0, tk.END)
        if dtype == "Pixel8":
            if path != "/":
                lb.insert(tk.END, "..")
            try:
                result = subprocess.run([ADB_PATH, "shell", "ls", "-p", path], capture_output=True)
                output = result.stdout.decode('utf-8', errors='replace')
                for f in output.strip().splitlines():
                    lb.insert(tk.END, f)
            except Exception as e:
                messagebox.showerror("ADB Error", str(e))
        else:
            if os.path.abspath(path) != os.path.abspath(os.path.join(path, "..")):
                lb.insert(tk.END, "..")
            try:
                for f in os.listdir(path):
                    lb.insert(tk.END, f)
            except Exception as e:
                messagebox.showerror("File Error", str(e))

    def enter(self, side):
        dtype, path, lb, _ = self.get_panel_info(side)
        selection = lb.get(tk.ACTIVE)
        new_path = os.path.dirname(path.rstrip("/\\")) if selection == ".." else os.path.join(path, selection.strip("/")) if dtype != "Pixel8" else f"{path.rstrip('/')}/{selection.strip('/')}"
        if dtype == "Pixel8" or os.path.isdir(new_path):
            if side == "left":
                self.left_path = new_path
            else:
                self.right_path = new_path
            self.refresh_panel(side)

    def copy_files(self):
        from_type, from_path, from_lb, _ = self.get_panel_info("left")
        to_type, to_path, _, _ = self.get_panel_info("right")
        selected = from_lb.curselection()
        for i in selected:
            name = from_lb.get(i).rstrip("/")
            src = os.path.join(from_path, name) if from_type != "Pixel8" else f"{from_path.rstrip('/')}/{name}"
            dst = os.path.join(to_path, name) if to_type != "Pixel8" else f"{to_path.rstrip('/')}/{name}"
            try:
                if from_type == "Pixel8" and to_type != "Pixel8":
                    subprocess.run([ADB_PATH, "pull", src, dst])
                elif from_type != "Pixel8" and to_type == "Pixel8":
                    subprocess.run([ADB_PATH, "push", src, dst])
                elif from_type != "Pixel8" and to_type != "Pixel8":
                    shutil.copy2(src, dst)
                elif from_type == "Pixel8" and to_type == "Pixel8":
                    subprocess.run([ADB_PATH, "shell", "cp", src, dst])
            except Exception as e:
                messagebox.showerror("Copy Error", str(e))
        self.refresh_panel("right")

    def copy_to_camera(self):
        from_type, from_path, from_lb, _ = self.get_panel_info("left")
        selected = from_lb.curselection()
        if not selected:
            messagebox.showinfo("Nothing Selected", "No files selected to copy.")
            return

        copied = False
        for i in selected:
            name = from_lb.get(i).rstrip("/")
            src = os.path.join(from_path, name) if from_type != "Pixel8" else f"{from_path.rstrip('/')}/{name}"
            dst = f"{CAMERA_PATH}/{name}"
            try:
                if from_type == "Pixel8":
                    subprocess.run([ADB_PATH, "shell", "cp", src, dst])
                else:
                    subprocess.run([ADB_PATH, "push", src, dst])
                copied = True
            except Exception as e:
                messagebox.showerror("Copy to Camera Error", str(e))

        if copied:
            self.rescan_media()

    def rescan_media(self):
        try:
            subprocess.run([
                ADB_PATH, "shell", "content", "call",
                "--method", "scan_volume",
                "--uri", "content://media",
                "--arg", "external_primary"
            ])
            messagebox.showinfo("Scan Complete", "Media scan triggered successfully.")
        except Exception as e:
            messagebox.showerror("Scan Failed", str(e))

    def delete_files(self):
        dtype, path, lb, _ = self.get_panel_info("right")
        selected = lb.curselection()
        if not messagebox.askyesno("Delete", "Delete selected files in right pane?"):
            return
        for i in selected:
            name = lb.get(i).rstrip("/")
            full = os.path.join(path, name) if dtype != "Pixel8" else f"{path.rstrip('/')}/{name}"
            try:
                if dtype == "Pixel8":
                    subprocess.run([ADB_PATH, "shell", "rm", "-rf", full])
                else:
                    if os.path.isdir(full):
                        shutil.rmtree(full)
                    else:
                        os.remove(full)
            except Exception as e:
                messagebox.showerror("Delete Error", str(e))
        self.refresh_panel("right")

    def rename_files(self):
        suffix = simpledialog.askstring("Rename", "Append this to selected filenames:")
        if not suffix:
            return
        for side in ("left", "right"):
            dtype, path, lb, _ = self.get_panel_info(side)
            selected = lb.curselection()
            for i in selected:
                name = lb.get(i).rstrip("/")
                base, ext = os.path.splitext(name)
                new_name = base + suffix + ext
                src = os.path.join(path, name) if dtype != "Pixel8" else f"{path.rstrip('/')}/{name}"
                dst = os.path.join(path, new_name) if dtype != "Pixel8" else f"{path.rstrip('/')}/{new_name}"
                try:
                    if dtype == "Pixel8":
                        subprocess.run([ADB_PATH, "shell", "mv", src, dst])
                    else:
                        os.rename(src, dst)
                except Exception as e:
                    messagebox.showerror("Rename Error", str(e))
            self.refresh_panel(side)

    def on_close(self):
        data = {
            "left_type": self.left_type.get(),
            "left_path": self.left_path,
            "right_type": self.right_type.get(),
            "right_path": self.right_path
        }
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass
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
            except Exception:
                pass

if __name__ == "__main__":
    root = tk.Tk()
    app = KuroCommander(root)
    root.mainloop()
