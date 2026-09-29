import tkinter as tk
from tkinter import colorchooser, ttk, simpledialog, messagebox, filedialog
import json, os, sys, copy, threading

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "crosshair_config.json")

try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

try:
    import pystray
    from PIL import Image, ImageDraw
    HAVE_TRAY = True
except Exception:
    HAVE_TRAY = False

CONFIG_VERSION = 4

THEMES = {
    "dark": {
        "bg": "#1e1e1e", "fg": "#e6e6e6", "panel": "#262626",
        "accent": "#3a3a3a", "button_bg": "#333333",
        "button_active": "#454545", "entry_bg": "#2a2a2a",
        "muted": "#8a8a8a", "border": "#111111",
    },
    "light": {
        "bg": "#cfc9bd", "fg": "#2a2a2a", "panel": "#c2bcae",
        "accent": "#b0aa9c", "button_bg": "#bcb6a8",
        "button_active": "#a8a294", "entry_bg": "#c8c2b4",
        "muted": "#5a5750", "border": "#a29c8e",
    },
}
PREVIEW_BG = "#3a3a3a"

CROSSHAIR_TYPES = ["cross", "cross_dot", "dot", "circle", "chevron"]
TYPE_LABELS = {
    "cross": "Крест", "cross_dot": "Крест + точка", "dot": "Точка",
    "circle": "Круг", "chevron": "Шеврон (V)",
}

HOTKEY_CHOICES = {
    "F6": 0x75, "F7": 0x76, "F8": 0x77, "F9": 0x78, "F10": 0x79,
    "Insert": 0x2D, "Home": 0x24, "End": 0x23,
    "Page Up": 0x21, "Page Down": 0x22,
}
MOD_NOREPEAT = 0x4000

# ============ Только два прицела ============
PRO_PRESETS = {
    "ZywOo": {
        "type": "cross",
        "size": 5.0, "gap": 2.0, "thick": 1.0,
        "color": "#00ff00", "outline": "#000000", "show_outline": False,
        "dot": 0.0, "dot_color": "#00ff00",
    },
    "ScreaM": {
        "type": "dot",
        "size": 0.0, "gap": 0.0, "thick": 1.0,
        "color": "#00bfff", "outline": "#000000", "show_outline": True,
        "dot": 2.0, "dot_color": "#00bfff",
    },
}

DEFAULT_PRESETS = copy.deepcopy(PRO_PRESETS)

NEW_PRESET_TEMPLATE = {
    "type": "cross", "size": 10.0, "gap": 4.0, "thick": 1.5,
    "color": "#00ff00", "outline": "#000000", "show_outline": True,
    "dot": 0.0, "dot_color": "#00ff00",
}


def load_config():
    cfg = {
        "version": CONFIG_VERSION,
        "theme": "dark",
        "current": next(iter(DEFAULT_PRESETS)),
        "overlay_visible": True,
        "presets": copy.deepcopy(DEFAULT_PRESETS),
        "hotkeys": {
            "toggle_overlay": "F8",
            "next_preset": "F9",
            "prev_preset": "F10",
        },
        "close_to_tray": True,
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                for k in ("theme", "current", "overlay_visible", "presets",
                          "version", "hotkeys", "close_to_tray"):
                    if k in saved:
                        cfg[k] = saved[k]
            # При апдейте версии доливаем дефолтные прицелы, не затирая пользовательские
            saved_version = saved.get("version", 1)
            if saved_version < CONFIG_VERSION:
                for name, p in DEFAULT_PRESETS.items():
                    if name not in cfg["presets"]:
                        cfg["presets"][name] = copy.deepcopy(p)
                cfg.setdefault("hotkeys", {})
                cfg["hotkeys"].setdefault("toggle_overlay", "F8")
                cfg["hotkeys"].setdefault("next_preset", "F9")
                cfg["hotkeys"].setdefault("prev_preset", "F10")
                cfg.setdefault("close_to_tray", True)
                cfg["version"] = CONFIG_VERSION
        except Exception as e:
            print("config load:", e)

    if not cfg.get("presets"):
        cfg["presets"] = copy.deepcopy(DEFAULT_PRESETS)
    if cfg.get("current") not in cfg["presets"]:
        cfg["current"] = next(iter(cfg["presets"]))
    if cfg.get("theme") not in THEMES:
        cfg["theme"] = "dark"
    return cfg


def save_config(cfg):
    cfg["version"] = CONFIG_VERSION
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("config save:", e)


def contrast_fg(hex_color):
    try:
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        return "#000000" if (0.299 * r + 0.587 * g + 0.114 * b) > 128 else "#ffffff"
    except Exception:
        return "#ffffff"


def draw_crosshair(canvas, cx, cy, p, scale=1.0):
    canvas.delete("all")
    size = float(p.get("size", 10)) * scale
    gap = float(p.get("gap", 4)) * scale
    thick = max(1.0, float(p.get("thick", 2)) * scale)
    color = p.get("color", "#00ff00")
    outline = p.get("outline", "#000000")
    use_outline = p.get("show_outline", True)
    dot = float(p.get("dot", 0)) * scale
    dot_color = p.get("dot_color", color)
    t = p.get("type", "cross")

    def line(x1, y1, x2, y2, col, w):
        canvas.create_line(x1, y1, x2, y2, fill=col, width=w,
                           capstyle="round")

    def with_outline(fn):
        if use_outline and outline:
            fn(outline, thick + 2)
        fn(color, thick)

    if t in ("cross", "cross_dot"):
        with_outline(lambda c, w: (
            line(cx - gap - size, cy, cx - gap, cy, c, w),
            line(cx + gap, cy, cx + gap + size, cy, c, w),
            line(cx, cy - gap - size, cx, cy - gap, c, w),
            line(cx, cy + gap, cx, cy + gap + size, c, w),
        ))
    if t == "chevron":
        with_outline(lambda c, w: (
            line(cx - size, cy + size / 2, cx, cy - size / 2, c, w),
            line(cx, cy - size / 2, cx + size, cy + size / 2, c, w),
        ))
    if t == "circle":
        r = size + gap
        if use_outline and outline:
            canvas.create_oval(cx - r - 1, cy - r - 1, cx + r + 1, cy + r + 1,
                               outline=outline, width=thick + 2)
        canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                           outline=color, width=thick)
    if t == "dot" or dot > 0:
        r = dot if dot > 0 else 3.0
        r = max(1.0, r)
        if use_outline and outline:
            canvas.create_oval(cx - r - 1, cy - r - 1, cx + r + 1, cy + r + 1,
                               fill=outline, outline="")
        canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                           fill=dot_color, outline="")


class Overlay:
    def __init__(self, master, params, visible=True):
        self.win = tk.Toplevel(master)
        self.win.overrideredirect(True)
        self.win.config(bg="black")
        self.sw = self.win.winfo_screenwidth()
        self.sh = self.win.winfo_screenheight()
        self.win.geometry(f"{self.sw}x{self.sh}+0+0")
        self.canvas = tk.Canvas(self.win, width=self.sw, height=self.sh,
                                bg="black", highlightthickness=0)
        self.canvas.pack()
        self.visible = True
        self.params = params
        self.win.update_idletasks()
        self._make_overlay()
        self.redraw()
        if not visible:
            self.toggle()

    def _make_overlay(self):
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetParent(self.win.winfo_id()) or self.win.winfo_id()
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_TOOLWINDOW = 0x00000080
            ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ex |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex)
            LWA_COLORKEY = 0x00000001
            user32.SetLayeredWindowAttributes(hwnd, 0x000000, 0, LWA_COLORKEY)
            HWND_TOPMOST = -1
            SWP_NOMOVE, SWP_NOSIZE = 0x0002, 0x0001
            SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x0010, 0x0040
            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                                SWP_NOMOVE | SWP_NOSIZE |
                                SWP_NOACTIVATE | SWP_SHOWWINDOW)
        except Exception as e:
            print("overlay setup:", e)

    def redraw(self):
        draw_crosshair(self.canvas, self.sw // 2, self.sh // 2, self.params, 1.0)

    def toggle(self):
        self.visible = not self.visible
        if self.visible:
            self.win.deiconify()
            self.win.lift()
            self.win.attributes("-topmost", True)
        else:
            self.win.withdraw()
        return self.visible

    def destroy(self):
        try:
            self.win.destroy()
        except Exception:
            pass


class HotkeysDialog:
    def __init__(self, parent, theme, hotkeys, on_save):
        self.on_save = on_save
        self.theme = theme

        self.win = tk.Toplevel(parent)
        self.win.title("Горячие клавиши")
        self.win.geometry("360x230")
        self.win.transient(parent)
        self.win.grab_set()
        self.win.resizable(False, False)
        self.win.configure(bg=theme["bg"])

        tk.Label(self.win, text="Горячие клавиши", bg=theme["bg"], fg=theme["fg"],
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=12, pady=(10, 4))
        tk.Label(self.win, text="Выбери клавишу для каждого действия.\n"
                                "Изменения применятся сразу.",
                 bg=theme["bg"], fg=theme["muted"],
                 font=("Segoe UI", 9), justify="left").pack(anchor="w", padx=12)

        self.vars = {}
        rows = [
            ("toggle_overlay", "Показать / Скрыть оверлей"),
            ("next_preset", "Следующий прицел"),
            ("prev_preset", "Предыдущий прицел"),
        ]

        form = tk.Frame(self.win, bg=theme["bg"])
        form.pack(fill="x", padx=12, pady=10)
        form.columnconfigure(1, weight=1)

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TCombobox",
                        fieldbackground=theme["entry_bg"],
                        background=theme["button_bg"],
                        foreground=theme["fg"],
                        arrowcolor=theme["fg"],
                        bordercolor=theme["border"])
        style.map("TCombobox",
                  fieldbackground=[("readonly", theme["entry_bg"])],
                  foreground=[("readonly", theme["fg"])])

        for i, (key, label) in enumerate(rows):
            tk.Label(form, text=label, bg=theme["bg"], fg=theme["fg"]).grid(
                row=i, column=0, sticky="w", pady=3)
            var = tk.StringVar(value=hotkeys.get(key, "F8"))
            cb = ttk.Combobox(form, textvariable=var,
                              values=list(HOTKEY_CHOICES.keys()),
                              state="readonly", width=12)
            cb.grid(row=i, column=1, sticky="w", pady=3)
            self.vars[key] = var

        btns = tk.Frame(self.win, bg=theme["bg"])
        btns.pack(fill="x", padx=12, pady=(0, 12))
        tk.Button(btns, text="Сохранить", command=self._save,
                  bg=theme["button_bg"], fg=theme["fg"],
                  activebackground=theme["button_active"],
                  activeforeground=theme["fg"],
                  relief="flat", bd=0, padx=10, pady=4).pack(side="left")
        tk.Button(btns, text="Отмена", command=self.win.destroy,
                  bg=theme["button_bg"], fg=theme["fg"],
                  activebackground=theme["button_active"],
                  activeforeground=theme["fg"],
                  relief="flat", bd=0, padx=10, pady=4).pack(side="left", padx=6)

    def _save(self):
        new_hotkeys = {k: v.get() for k, v in self.vars.items()}
        vals = list(new_hotkeys.values())
        if len(vals) != len(set(vals)):
            messagebox.showerror("Ошибка", "Клавиши не должны повторяться.",
                                 parent=self.win)
            return
        self.on_save(new_hotkeys)
        self.win.destroy()


class App:
    def __init__(self):
        self.cfg = load_config()
        self._updating = False
        self.overlay = None
        self.tray_icon = None
        self._hotkey_ids = {}
        self._hotkey_counter = 10

        self.root = tk.Tk()
        self.root.title("Crosshair Overlay")
        self.root.resizable(False, False)

        self._build_ui()
        self._refresh_preset_list()
        self._select_preset(self.cfg["current"])
        self._apply_theme()

        self.root.after(200, self._create_overlay)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close_request)
        self._register_all_hotkeys()
        self._start_hotkey_poll()
        self._start_tray()

        self.root.mainloop()

    # ---------- UI ----------
    def _build_ui(self):
        self.top = tk.Frame(self.root)
        self.top.pack(fill="x", padx=12, pady=(10, 0))
        tk.Label(self.top, text="Crosshair Overlay",
                 font=("Segoe UI", 12, "bold")).pack(side="left")
        self.theme_btn = tk.Button(self.top, text="Тема: Тёмная",
                                   command=self._toggle_theme)
        self.theme_btn.pack(side="right")

        self.main = tk.Frame(self.root)
        self.main.pack(fill="both", expand=True, padx=12, pady=10)

        self.left = tk.Frame(self.main)
        self.left.pack(side="left", fill="y")
        tk.Label(self.left, text="Прицелы  (ПКМ — удалить)").pack(anchor="w")
        self.preset_list = tk.Listbox(self.left, width=22, height=22,
                                      exportselection=False)
        self.preset_list.pack(fill="y", expand=True, pady=4)
        self.preset_list.bind("<<ListboxSelect>>", self._on_preset_select)
        self.preset_list.bind("<Double-Button-1>", lambda e: self._rename_preset())
        # ПКМ — контекстное меню
        self.preset_list.bind("<Button-3>", self._on_preset_right_click)

        # Меню для ПКМ
        self.ctx_menu = tk.Menu(self.root, tearoff=0)
        self.ctx_menu.add_command(label="Переименовать", command=self._rename_preset)
        self.ctx_menu.add_command(label="Дублировать", command=self._duplicate_preset)
        self.ctx_menu.add_separator()
        self.ctx_menu.add_command(label="Удалить", command=self._delete_preset)

        btn_row = tk.Frame(self.left)
        btn_row.pack(fill="x")
        tk.Button(btn_row, text="+", width=3,
                  command=self._add_preset).pack(side="left")
        tk.Button(btn_row, text="Копия",
                  command=self._duplicate_preset).pack(side="left", padx=2)
        tk.Button(btn_row, text="×", width=3,
                  command=self._delete_preset).pack(side="left")

        io_row = tk.Frame(self.left)
        io_row.pack(fill="x", pady=(4, 0))
        tk.Button(io_row, text="Импорт",
                  command=self._import_library).pack(side="left", expand=True, fill="x")
        tk.Button(io_row, text="Экспорт",
                  command=self._export_library).pack(side="left", expand=True,
                                                     fill="x", padx=(4, 0))

        self.right = tk.Frame(self.main)
        self.right.pack(side="left", fill="both", expand=True, padx=(14, 0))

        self.preview = tk.Canvas(self.right, width=240, height=200,
                                 bg=PREVIEW_BG, highlightthickness=0)
        self.preview.pack()

        self.form = tk.Frame(self.right)
        self.form.pack(fill="x", pady=(10, 0))
        self.form.columnconfigure(1, weight=1)

        row = 0
        tk.Label(self.form, text="Тип").grid(row=row, column=0, sticky="w", pady=2)
        self.type_var = tk.StringVar()
        self.type_combo = ttk.Combobox(
            self.form, textvariable=self.type_var,
            values=[TYPE_LABELS[t] for t in CROSSHAIR_TYPES],
            state="readonly", width=16)
        self.type_combo.grid(row=row, column=1, sticky="ew", pady=2)
        self.type_combo.bind("<<ComboboxSelected>>", self._on_param_change)
        row += 1

        self.size_var = tk.DoubleVar()
        self.size_scale = self._make_slider(row, "Длина", self.size_var,
                                            0.0, 30.0, 0.05); row += 1
        self.gap_var = tk.DoubleVar()
        self.gap_scale = self._make_slider(row, "Отступ", self.gap_var,
                                           0.0, 20.0, 0.05); row += 1
        self.thick_var = tk.DoubleVar()
        self.thick_scale = self._make_slider(row, "Толщина", self.thick_var,
                                             0.1, 8.0, 0.05); row += 1
        self.dot_var = tk.DoubleVar()
        self.dot_scale = self._make_slider(row, "Точка (размер)", self.dot_var,
                                           0.0, 12.0, 0.05); row += 1

        tk.Label(self.form, text="Цвет").grid(row=row, column=0, sticky="w", pady=2)
        self.color_btn = tk.Button(self.form, text="  ", width=10, relief="flat",
                                   command=lambda: self._pick_color("color"))
        self.color_btn.grid(row=row, column=1, sticky="w", pady=2); row += 1

        tk.Label(self.form, text="Цвет точки").grid(row=row, column=0, sticky="w", pady=2)
        self.dot_color_btn = tk.Button(self.form, text="  ", width=10, relief="flat",
                                       command=lambda: self._pick_color("dot_color"))
        self.dot_color_btn.grid(row=row, column=1, sticky="w", pady=2); row += 1

        tk.Label(self.form, text="Обводка").grid(row=row, column=0, sticky="w", pady=2)
        outline_row = tk.Frame(self.form)
        outline_row.grid(row=row, column=1, sticky="w", pady=2)
        self.outline_var = tk.BooleanVar()
        self.outline_check = tk.Checkbutton(outline_row, text="вкл",
            variable=self.outline_var, command=self._on_param_change)
        self.outline_check.pack(side="left")
        self.outline_btn = tk.Button(outline_row, text="  ", width=10, relief="flat",
                                     command=lambda: self._pick_color("outline"))
        self.outline_btn.pack(side="left", padx=(6, 0))
        row += 1

        self.bottom = tk.Frame(self.right)
        self.bottom.pack(fill="x", pady=(12, 0))
        self.toggle_btn = tk.Button(self.bottom, text="Показать / Скрыть",
                                    command=self.toggle_overlay)
        self.toggle_btn.pack(side="left")
        tk.Button(self.bottom, text="Сбросить пресет",
                  command=self._reset_preset).pack(side="left", padx=4)
        tk.Button(self.bottom, text="Хоткеи…",
                  command=self._open_hotkeys_dialog).pack(side="left")

        self.hotkey_hint = tk.Label(self.right, text="", fg="gray",
                                    font=("Segoe UI", 8))
        self.hotkey_hint.pack(anchor="w", pady=(6, 0))
        self._update_hotkey_hint()

    def _make_slider(self, row, label, var, frm, to, resolution):
        tk.Label(self.form, text=label).grid(row=row, column=0, sticky="w", pady=2)
        s = tk.Scale(self.form, from_=frm, to=to, orient="horizontal",
                     variable=var, resolution=resolution, digits=3,
                     length=170, sliderlength=14, highlightthickness=0, bd=0,
                     command=lambda v: self._on_param_change())
        s.grid(row=row, column=1, sticky="ew", pady=2)
        return s

    def _update_hotkey_hint(self):
        hk = self.cfg.get("hotkeys", {})
        text = (f'Хоткеи: {hk.get("toggle_overlay","F8")} — показать/скрыть · '
                f'{hk.get("next_preset","F9")} — след. · '
                f'{hk.get("prev_preset","F10")} — пред.')
        try:
            self.hotkey_hint.configure(text=text)
        except Exception:
            pass

    # ---------- логика ----------
    def _on_param_change(self, *args):
        if self._updating:
            return
        name = self.cfg["current"]
        p = self.cfg["presets"][name]
        label = self.type_var.get()
        for k, v in TYPE_LABELS.items():
            if v == label:
                p["type"] = k
                break
        p["size"] = round(float(self.size_var.get()), 3)
        p["gap"] = round(float(self.gap_var.get()), 3)
        p["thick"] = round(float(self.thick_var.get()), 3)
        p["dot"] = round(float(self.dot_var.get()), 3)
        p["show_outline"] = bool(self.outline_var.get())
        self._redraw_preview()
        self._update_overlay()
        save_config(self.cfg)

    def _pick_color(self, key):
        p = self.cfg["presets"][self.cfg["current"]]
        initial = p.get(key, "#ffffff")
        res = colorchooser.askcolor(color=initial, parent=self.root)
        if res and res[1]:
            p[key] = res[1].lower()
            self._refresh_color_buttons()
            self._redraw_preview()
            self._update_overlay()
            save_config(self.cfg)

    def _refresh_color_buttons(self):
        p = self.cfg["presets"][self.cfg["current"]]
        c = p.get("color", "#00ff00")
        dc = p.get("dot_color", c)
        oc = p.get("outline", "#000000")
        self.color_btn.configure(bg=c, activebackground=c, fg=contrast_fg(c))
        self.dot_color_btn.configure(bg=dc, activebackground=dc, fg=contrast_fg(dc))
        self.outline_btn.configure(bg=oc, activebackground=oc, fg=contrast_fg(oc))

    def _redraw_preview(self):
        p = self.cfg["presets"][self.cfg["current"]]
        draw_crosshair(self.preview, 120, 100, p, scale=1.3)

    def _update_overlay(self):
        if self.overlay is None:
            return
        self.overlay.params = self.cfg["presets"][self.cfg["current"]]
        self.overlay.redraw()

    def _select_preset(self, name):
        if name not in self.cfg["presets"]:
            return
        self.cfg["current"] = name
        p = self.cfg["presets"][name]
        self._updating = True
        try:
            self.size_var.set(float(p.get("size", 10)))
            self.gap_var.set(float(p.get("gap", 4)))
            self.thick_var.set(float(p.get("thick", 2)))
            self.dot_var.set(float(p.get("dot", 0)))
            self.type_var.set(TYPE_LABELS.get(p.get("type", "cross"), "Крест"))
            self.outline_var.set(bool(p.get("show_outline", True)))
        finally:
            self._updating = False
        self._refresh_color_buttons()
        self._redraw_preview()
        self._update_overlay()

        names = list(self.cfg["presets"].keys())
        if name in names:
            idx = names.index(name)
            self.preset_list.selection_clear(0, tk.END)
            self.preset_list.selection_set(idx)
            self.preset_list.see(idx)
        save_config(self.cfg)

    def _refresh_preset_list(self):
        self.preset_list.delete(0, tk.END)
        for name in self.cfg["presets"]:
            self.preset_list.insert(tk.END, name)

    def _on_preset_select(self, event):
        sel = self.preset_list.curselection()
        if not sel:
            return
        name = self.preset_list.get(sel[0])
        if name != self.cfg["current"]:
            self._select_preset(name)

    def _on_preset_right_click(self, event):
        """ПКМ по элементу списка: выбираем его и показываем меню."""
        idx = self.preset_list.nearest(event.y)
        if idx < 0:
            return
        bbox = self.preset_list.bbox(idx)
        if bbox is None:
            return
        # Проверяем, что клик действительно внутри строки
        x, y, w, h = bbox
        if not (y <= event.y <= y + h):
            return
        self.preset_list.selection_clear(0, tk.END)
        self.preset_list.selection_set(idx)
        self.preset_list.activate(idx)
        name = self.preset_list.get(idx)
        if name != self.cfg["current"]:
            self._select_preset(name)
        try:
            self.ctx_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.ctx_menu.grab_release()

    def _add_preset(self):
        name = simpledialog.askstring("Новый прицел", "Имя:", parent=self.root)
        if not name:
            return
        base = name; i = 2
        while name in self.cfg["presets"]:
            name = f"{base} {i}"; i += 1
        self.cfg["presets"][name] = copy.deepcopy(NEW_PRESET_TEMPLATE)
        self.cfg["current"] = name
        save_config(self.cfg)
        self._refresh_preset_list()
        self._select_preset(name)

    def _duplicate_preset(self):
        name = self.cfg["current"]
        base = f"{name} копия"
        new = base; i = 2
        while new in self.cfg["presets"]:
            new = f"{base} {i}"; i += 1
        self.cfg["presets"][new] = copy.deepcopy(self.cfg["presets"][name])
        self.cfg["current"] = new
        save_config(self.cfg)
        self._refresh_preset_list()
        self._select_preset(new)

    def _delete_preset(self):
        name = self.cfg["current"]
        if len(self.cfg["presets"]) <= 1:
            messagebox.showinfo("Нельзя", "Должен остаться хотя бы один прицел.")
            return
        if not messagebox.askyesno("Удалить", f'Удалить прицел "{name}"?'):
            return
        del self.cfg["presets"][name]
        self.cfg["current"] = next(iter(self.cfg["presets"]))
        save_config(self.cfg)
        self._refresh_preset_list()
        self._select_preset(self.cfg["current"])

    def _rename_preset(self):
        name = self.cfg["current"]
        new = simpledialog.askstring("Переименовать", "Новое имя:",
                                     initialvalue=name, parent=self.root)
        if not new or new == name or new in self.cfg["presets"]:
            return
        new_presets = {}
        for k, v in self.cfg["presets"].items():
            new_presets[new if k == name else k] = v
        self.cfg["presets"] = new_presets
        self.cfg["current"] = new
        save_config(self.cfg)
        self._refresh_preset_list()
        self._select_preset(new)

    def _reset_preset(self):
        name = self.cfg["current"]
        if name in DEFAULT_PRESETS:
            self.cfg["presets"][name] = copy.deepcopy(DEFAULT_PRESETS[name])
        else:
            self.cfg["presets"][name] = copy.deepcopy(NEW_PRESET_TEMPLATE)
        save_config(self.cfg)
        self._select_preset(name)

    # ---------- импорт/экспорт библиотеки ----------
    def _export_library(self):
        path = filedialog.asksaveasfilename(
            parent=self.root,
            defaultextension=".json",
            filetypes=[("Crosshair library", "*.json"), ("All files", "*.*")],
            initialfile="crosshairs.json",
            title="Сохранить библиотеку прицелов",
        )
        if not path:
            return
        try:
            data = {
                "version": CONFIG_VERSION,
                "presets": self.cfg["presets"],
                "current": self.cfg["current"],
                "exported_at": __import__("datetime").datetime.now().isoformat(),
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("Готово",
                                f"Сохранено {len(self.cfg['presets'])} прицелов.",
                                parent=self.root)
        except Exception as e:
            messagebox.showerror("Ошибка", str(e), parent=self.root)

    def _import_library(self):
        path = filedialog.askopenfilename(
            parent=self.root,
            filetypes=[("Crosshair library", "*.json"), ("All files", "*.*")],
            title="Загрузить библиотеку прицелов",
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            presets = data.get("presets") if isinstance(data, dict) else None
            if not isinstance(presets, dict) or not presets:
                raise ValueError("В файле нет прицелов.")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось прочитать файл:\n{e}",
                                 parent=self.root)
            return

        mode = messagebox.askyesnocancel(
            "Импорт библиотеки",
            f"Найдено {len(presets)} прицелов.\n\n"
            f"«Да» — добавить к текущим (дубликаты получат суффикс).\n"
            f"«Нет» — заменить текущую библиотеку.\n"
            f"«Отмена» — отменить.",
            parent=self.root,
        )
        if mode is None:
            return

        if mode:
            added = 0
            for name, p in presets.items():
                base = name; i = 2; new = name
                while new in self.cfg["presets"]:
                    new = f"{base} ({i})"; i += 1
                self.cfg["presets"][new] = copy.deepcopy(p)
                added += 1
            messagebox.showinfo("Готово", f"Добавлено {added} прицелов.",
                                parent=self.root)
        else:
            self.cfg["presets"] = copy.deepcopy(presets)
            if self.cfg.get("current") not in self.cfg["presets"]:
                self.cfg["current"] = next(iter(self.cfg["presets"]))
            messagebox.showinfo("Готово",
                                f"Загружено {len(self.cfg['presets'])} прицелов.",
                                parent=self.root)

        save_config(self.cfg)
        self._refresh_preset_list()
        self._select_preset(self.cfg["current"])

    # ---------- оверлей ----------
    def _create_overlay(self):
        visible = self.cfg.get("overlay_visible", True)
        self.overlay = Overlay(self.root,
                               self.cfg["presets"][self.cfg["current"]],
                               visible=visible)

    def toggle_overlay(self):
        if self.overlay:
            self.cfg["overlay_visible"] = self.overlay.toggle()
            save_config(self.cfg)

    def next_preset(self):
        names = list(self.cfg["presets"].keys())
        if not names:
            return
        i = names.index(self.cfg["current"]) if self.cfg["current"] in names else 0
        self._select_preset(names[(i + 1) % len(names)])

    def prev_preset(self):
        names = list(self.cfg["presets"].keys())
        if not names:
            return
        i = names.index(self.cfg["current"]) if self.cfg["current"] in names else 0
        self._select_preset(names[(i - 1) % len(names)])

    # ---------- хоткеи ----------
    def _register_hotkey(self, name, key_name):
        try:
            import ctypes
            user32 = ctypes.windll.user32
            vk = HOTKEY_CHOICES.get(key_name)
            if vk is None:
                return False
            hwnd = self.root.winfo_id()
            hk_id = self._hotkey_counter
            self._hotkey_counter += 1
            if not user32.RegisterHotKey(hwnd, hk_id, MOD_NOREPEAT, vk):
                print(f"RegisterHotKey: {key_name} занята")
                return False
            self._hotkey_ids[name] = (hk_id, vk)
            return True
        except Exception as e:
            print("register hotkey:", e)
            return False

    def _unregister_all_hotkeys(self):
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = self.root.winfo_id()
            for name, (hk_id, vk) in list(self._hotkey_ids.items()):
                try:
                    user32.UnregisterHotKey(hwnd, hk_id)
                except Exception:
                    pass
            self._hotkey_ids.clear()
        except Exception as e:
            print("unregister hotkey:", e)

    def _register_all_hotkeys(self):
        self._unregister_all_hotkeys()
        hk = self.cfg.get("hotkeys", {})
        self._register_hotkey("toggle_overlay", hk.get("toggle_overlay", "F8"))
        self._register_hotkey("next_preset", hk.get("next_preset", "F9"))
        self._register_hotkey("prev_preset", hk.get("prev_preset", "F10"))
        self._update_hotkey_hint()

    def _start_hotkey_poll(self):
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            hwnd = self.root.winfo_id()

            def poll():
                msg = wintypes.MSG()
                while user32.PeekMessageW(ctypes.byref(msg), hwnd, 0, 0, 1):
                    if msg.message == 0x0312:
                        hk_id = msg.wParam
                        for name, (hid, vk) in self._hotkey_ids.items():
                            if hid == hk_id:
                                if name == "toggle_overlay":
                                    self.toggle_overlay()
                                elif name == "next_preset":
                                    self.next_preset()
                                elif name == "prev_preset":
                                    self.prev_preset()
                                break
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
                self.root.after(50, poll)

            self.root.after(50, poll)
        except Exception as e:
            print("hotkey poll:", e)

    def _open_hotkeys_dialog(self):
        HotkeysDialog(self.root, THEMES[self.cfg["theme"]],
                      self.cfg.get("hotkeys", {}),
                      on_save=self._apply_hotkeys)

    def _apply_hotkeys(self, new_hotkeys):
        self.cfg["hotkeys"] = new_hotkeys
        save_config(self.cfg)
        self._register_all_hotkeys()
        messagebox.showinfo("Готово", "Хоткеи обновлены.", parent=self.root)

    # ---------- трей ----------
    def _start_tray(self):
        if not HAVE_TRAY:
            return
        try:
            img = self._make_tray_image()
            menu = pystray.Menu(
                pystray.MenuItem("Показать окно", self._tray_show, default=True),
                pystray.MenuItem("Показать / Скрыть оверлей", self._tray_toggle_overlay),
                pystray.MenuItem("Следующий прицел", self._tray_next),
                pystray.MenuItem("Предыдущий прицел", self._tray_prev),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Выход", self._tray_exit),
            )
            self.tray_icon = pystray.Icon("Crosshair", img, "Crosshair Overlay", menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        except Exception as e:
            print("tray start:", e)

    def _make_tray_image(self):
        img = Image.new("RGBA", (64, 64), (30, 30, 30, 255))
        d = ImageDraw.Draw(img)
        cx = cy = 32
        d.line([(cx, cy - 20), (cx, cy - 6)], fill=(0, 255, 0, 255), width=4)
        d.line([(cx, cy + 6), (cx, cy + 20)], fill=(0, 255, 0, 255), width=4)
        d.line([(cx - 20, cy), (cx - 6, cy)], fill=(0, 255, 0, 255), width=4)
        d.line([(cx + 6, cy), (cx + 20, cy)], fill=(0, 255, 0, 255), width=4)
        return img

    def _tray_show(self, icon=None, item=None):
        self.root.after(0, self._show_window)

    def _show_window(self):
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass

    def _tray_toggle_overlay(self, icon=None, item=None):
        self.root.after(0, self.toggle_overlay)

    def _tray_next(self, icon=None, item=None):
        self.root.after(0, self.next_preset)

    def _tray_prev(self, icon=None, item=None):
        self.root.after(0, self.prev_preset)

    def _tray_exit(self, icon=None, item=None):
        self.root.after(0, self._real_exit)

    # ---------- закрытие ----------
    def on_close_request(self):
        if self.cfg.get("close_to_tray", True) and self.tray_icon is not None:
            self.root.withdraw()
        else:
            self._real_exit()

    def _real_exit(self):
        save_config(self.cfg)
        self._unregister_all_hotkeys()
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        if self.overlay:
            self.overlay.destroy()
        try:
            self.root.destroy()
        except Exception:
            pass

    # ---------- темы ----------
    def _toggle_theme(self):
        self.cfg["theme"] = "light" if self.cfg["theme"] == "dark" else "dark"
        save_config(self.cfg)
        self._apply_theme()

    def _apply_theme(self):
        t = THEMES[self.cfg["theme"]]
        color_btns = (self.color_btn, self.dot_color_btn, self.outline_btn)
        overlay_win = self.overlay.win if self.overlay else None
        overlay_canvas = self.overlay.canvas if self.overlay else None

        def walk(w):
            if w is overlay_win or w is overlay_canvas:
                return
            cls = w.winfo_class()
            try:
                if cls in ("Frame", "Toplevel"):
                    w.configure(bg=t["bg"])
                elif cls == "Label":
                    w.configure(bg=t["bg"], fg=t["fg"])
                elif cls == "Button":
                    if w in color_btns:
                        pass
                    else:
                        w.configure(bg=t["button_bg"], fg=t["fg"],
                                    activebackground=t["button_active"],
                                    activeforeground=t["fg"],
                                    relief="flat", bd=0, highlightthickness=0)
                elif cls == "Checkbutton":
                    w.configure(bg=t["bg"], fg=t["fg"],
                                activebackground=t["bg"], activeforeground=t["fg"],
                                selectcolor=t["entry_bg"],
                                highlightthickness=0, bd=0)
                elif cls == "Scale":
                    w.configure(bg=t["bg"], fg=t["fg"],
                                troughcolor=t["accent"],
                                activebackground=t["button_active"],
                                highlightthickness=0, bd=0)
                elif cls == "Listbox":
                    w.configure(bg=t["entry_bg"], fg=t["fg"],
                                selectbackground=t["accent"],
                                selectforeground=t["fg"],
                                highlightthickness=0, bd=0)
                elif cls == "Canvas":
                    w.configure(bg=PREVIEW_BG if w is self.preview else t["bg"])
            except Exception:
                pass
            for c in w.winfo_children():
                walk(c)

        self.root.configure(bg=t["bg"])
        walk(self.root)
        self.theme_btn.configure(
            text="Тема: Тёмная" if self.cfg["theme"] == "dark" else "Тема: Светлая")

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TCombobox",
                        fieldbackground=t["entry_bg"],
                        background=t["button_bg"],
                        foreground=t["fg"],
                        arrowcolor=t["fg"],
                        bordercolor=t["border"])
        style.map("TCombobox",
                  fieldbackground=[("readonly", t["entry_bg"])],
                  foreground=[("readonly", t["fg"])])
        self.root.option_add("*TCombobox*Listbox.background", t["entry_bg"])
        self.root.option_add("*TCombobox*Listbox.foreground", t["fg"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", t["accent"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", t["fg"])


if __name__ == "__main__":
    App()