# GUI-Bausteine für KC-V24-Transfer
#
# Ausgelagert aus kc_v24_transfer.py

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog


def create_widgets(app):
    style = ttk.Style()
    try:
        style.theme_use("vista")
    except tk.TclError:
        # Fallback, falls das Theme nicht verfügbar ist (z. B. unter Linux)
        pass
    #print(style.theme_use())       # aktuelles Theme
    #print(style.theme_names())     # verfügbare Themes


    # Frame
    app.button_frame = ttk.Frame(app.root, padding=5)
    app.button_frame.grid(row=0, column=0, sticky="we")
    app.root.grid_columnconfigure(0, weight=1)

    # Buttons
    app.btn_load = ttk.Button(app.button_frame, text="Datei", command=app.load_file)
    app.btn_load.grid(row=0, column=0, padx=(1, 5), sticky="w")

    app.btn_send = ttk.Button(app.button_frame, text="Übertragen", command=app.on_send_clicked)
    app.btn_send.grid(row=0, column=1, padx=(5, 0), sticky="w")

    app.button_frame.grid_columnconfigure(2, weight=1)

    style.configure("KeybOff.TButton",       foreground="#AAAAAA")
    style.configure("KeybOn.TButton",        foreground="#009020")
    style.configure("KeybDisabled.TButton",  foreground="#808080")
    app._img_keyb_on       = tk.PhotoImage(file=(str(app.ASSET_PATH) + "/keyboard_24_on.png"))
    app._img_keyb_off      = tk.PhotoImage(file=(str(app.ASSET_PATH) + "/keyboard_24_off.png"))
    app._img_keyb_disabled = tk.PhotoImage(file=(str(app.ASSET_PATH) + "/keyboard_24_disabled.png"))

    app.keybmode_button = ttk.Button(
        app.button_frame,
        text="Tastatur",
        style="KeybOff.TButton",
        state="normal",     # nicht "enable"
        takefocus=False,     # wichtig: kein Fokusrahmen
        image=app._img_keyb_off,
        compound="left",   # Icon links, Text rechts
    )
    app.keybmode_button.grid(row=0, column=2, padx=(10, 1), sticky="e")
    app.keybmode_button.bind("<Double-Button-1>", app.on_keybmode_button_doubleclicked, add="+")

    bind_single_double(
        app.keybmode_button,
        on_single=lambda e: app.on_keybmode_button_pressed(),
        on_double=lambda e: app.on_keybmode_button_doubleclicked(),  # diese Methode im App-Objekt vorsehen
        delay_ms=350,
    )


    frame_text = ttk.Frame(app.root, padding=(7,0))
    frame_text.grid(row=1, column=0, sticky="wens")

    app.statusfeld = tk.Text(frame_text, width=40, height=6, wrap="none", padx=10, pady=10,font=("Consolas", 10),
            bg="#304530",
            fg="#00FF66",
            borderwidth=3,   # Rahmenbreite
            relief="sunken",  # 3D-Effekt

                              )
    app.statusfeld.grid(row=0, column=0, sticky="nsew")

    frame_progress = ttk.Frame(app.root, padding=5)
    frame_progress.grid(row=2, column=0, sticky="we")

    # Rahmen soll Spalte 1 (Fortschrittsbalken) flexibel verbreitern
    frame_progress.columnconfigure(1, weight=1)

    # Dropdown für COM-Port unten links (ohne Beschriftung)
    app.com_port_menu_name.set("COM-Port")
    app.port_option = tk.OptionMenu(frame_progress, app.com_port_menu_name, "COM-Port")
    app.port_option.grid(row=1, column=0, padx=(0, 5), sticky="w")

    #menu = app.port_option["menu"]
    #menu.configure(postcommand=app.refresh_port_menu)

    # Fortschrittsbalken rechts daneben, Breite dynamisch
    app.progress = ttk.Progressbar(
        frame_progress,
        orient="horizontal",
        mode="determinate",   # length weglassen oder nur als Startwert verstehen
    )
    app.progress.grid(row=1, column=1, pady=2, padx=(3, 1), sticky="wens")

########################################################################################################
# Hilfsfunktionen / Workarounds
########################################################################################################
# Hilftsfunktion bzgl. Doppelklick auf Tastatur-Button
def bind_single_double(widget, on_single=None, on_double=None, *, delay_ms=250, add=False):
    _attr = "_single_after_id"
    if not hasattr(widget, _attr):
        setattr(widget, _attr, None)

    def cancel_pending():
        after_id = getattr(widget, _attr, None)
        if after_id:
            try:
                widget.after_cancel(after_id)
            except Exception:
                pass
            setattr(widget, _attr, None)

    def _schedule_single(event):
        cancel_pending()
        if on_single is None:
            return

        def fire():
            try:
                if not widget.winfo_exists():
                    return
            except Exception:
                return
            setattr(widget, _attr, None)
            on_single(event)

        setattr(widget, _attr, widget.after(delay_ms, fire))

    def _handle_double(event):
        cancel_pending()
        if on_double is not None:
            on_double(event)

    widget.bind("<Button-1>", _schedule_single, add=add)
    widget.bind("<Double-Button-1>", _handle_double, add=add)

def show_text_transferconfig_dialog(app) -> bool:

    dialog = tk.Toplevel(app.root)
    dialog.title("Einstellungen Textübertragung")
    dialog.resizable(False, False)
    dialog.transient(app.root)
    dialog.grab_set()

    frame = ttk.Frame(dialog, padding=10)
    frame.grid(row=0, column=0, sticky="nsew")

    # Variablen mit aktuellen Werten vorbelegen
    text_lw_var      = tk.IntVar(value=app.textconfig_linewidth)
    text_init_var    = tk.IntVar(value=app.textconfig_init_delay)
    text_char_var    = tk.IntVar(value=app.textconfig_char_delay)
    text_scroll_var  = tk.IntVar(value=app.textconfig_linescroll_delay)
    text_proc_var    = tk.IntVar(value=app.textconfig_process_delay)
    text_show_var    = tk.BooleanVar(value=app.textconfig_showkonfigdialog)

    # Zeilen 0–4: Label + Entry
    row = 0
    ttk.Label(frame, text="Zeilenbreite (Zeichen):").grid(row=row, column=0, sticky="w", pady=2)
    ttk.Entry(frame, textvariable=text_lw_var, width=6).grid(row=row, column=1, sticky="e", pady=2)

    row += 1
    ttk.Label(frame, text="Initial-Verzögerung (ms):").grid(row=row, column=0, sticky="w", pady=2)
    ttk.Entry(frame, textvariable=text_init_var, width=6).grid(row=row, column=1, sticky="e", pady=2)

    row += 1
    ttk.Label(frame, text="Zeichen-Verzögerung (ms):").grid(row=row, column=0, sticky="w", pady=2)
    ttk.Entry(frame, textvariable=text_char_var, width=6).grid(row=row, column=1, sticky="e", pady=2)

    row += 1
    ttk.Label(frame, text="Scroll-Verzögerung (ms):").grid(row=row, column=0, sticky="w", pady=2)
    ttk.Entry(frame, textvariable=text_scroll_var, width=6).grid(row=row, column=1, sticky="e", pady=2)

    row += 1
    ttk.Label(frame, text="Verarbeitungszeit (ms):").grid(row=row, column=0, sticky="w", pady=2)
    ttk.Entry(frame, textvariable=text_proc_var, width=6).grid(row=row, column=1, sticky="e", pady=2)

    row += 1
    chk = ttk.Checkbutton(
        frame,
        text="Diesen Dialog immer wieder anzeigen",
        variable=text_show_var
    )
    chk.grid(row=row, column=0, columnspan=2, sticky="w", pady=(6, 0))


    row += 1
    btn_frame = ttk.Frame(frame)
    btn_frame.grid(row=row, column=0, columnspan=2, pady=(8, 0))


    # Button-Leiste
    row += 1
    btn_frame = ttk.Frame(frame)
    btn_frame.grid(row=row, column=0, columnspan=2, pady=(8, 0))

    # Flag, ob OK gedrückt wurde
    ok_clicked = False

    def on_ok():
        nonlocal ok_clicked
        try:
            lw     = int(text_lw_var.get())
            init   = int(text_init_var.get())
            chd    = int(text_char_var.get())
            scroll = int(text_scroll_var.get())
            proc   = int(text_proc_var.get())
        except ValueError:
            messagebox.showerror(
                "Fehler",
                "Bitte in allen Feldern ganze Zahlen eingeben.",
                parent=dialog,
            )
            return

        # einfache Plausibilitätsprüfung (optional)
        if lw <= 0:
            messagebox.showerror(
                "Fehler",
                "Die Zeilenbreite muss größer als 0 sein.",
                parent=dialog,
            )
            return

        # Werte übernehmen
        app.textconfig_linewidth        = lw
        app.textconfig_init_delay       = init
        app.textconfig_char_delay       = chd
        app.textconfig_linescroll_delay = scroll
        app.textconfig_process_delay    = proc
        app.textconfig_showkonfigdialog = bool(text_show_var.get())

        ok_clicked = True
        dialog.destroy()

    def on_cancel():
        dialog.destroy()

    ttk.Button(btn_frame, text="Starten", command=on_ok).grid(row=0, column=0, padx=5)
    #ttk.Button(btn_frame, text="Abbrechen", command=on_cancel).grid(row=0, column=1, padx=5)

    dialog.protocol("WM_DELETE_WINDOW", on_cancel)

    # Dialog ungefähr über dem Hauptfenster zentrieren (optional)
    app.root.update_idletasks()
    dialog.update_idletasks()
    x_root = app.root.winfo_rootx()
    y_root = app.root.winfo_rooty()
    w_root = app.root.winfo_width()
    h_root = app.root.winfo_height()
    w = dialog.winfo_width()
    h = dialog.winfo_height()
    x = x_root + (w_root - w) // 2
    y = y_root + (h_root - h) // 2
    dialog.geometry(f"+{x}+{y}")

    dialog.wait_window()

    return ok_clicked

########################################################################################################
# Dialog vor der Übertragung von Binärdaten im CAOS-Mode
# - wird mit aus der geladenen Datei automatisch ermittelten Daten vorbelegt
########################################################################################################

def show_caos_transferconfig_dialog(app) -> bool:

    """
    Dialog der Konfiguration der CAOS-Binärübertragung.
    Setzt:
        app.caos_start        (int | None)
        app.caos_end          (int | None)
        app.caos_call         (int | None)
        app.autostart_want    (True, False)

    Vorbelegung aus:
        app.file_start / app.file_end / app.file_call / app.autostart_want
    """
    dialog = tk.Toplevel(app.root)
    dialog.title("Einstellungen")
    dialog.resizable(False, False)
    dialog.transient(app.root)
    dialog.grab_set()

    frame = ttk.Frame(dialog, padding=10)
    frame.grid(row=0, column=0, sticky="nsew")
    frame.grid_columnconfigure(0, minsize=90)
    frame.grid_columnconfigure(1, minsize=90)


    # Hilfsfunktion: int -> 4‑stellige HEX oder leer
    def fmt_hex4(value):
        return "" if value is None else f"{value & 0xFFFF:04X}"

    # Defaultwerte aus der Datei
    start_var = tk.StringVar(value=fmt_hex4(app.file_start))
    end_var   = tk.StringVar(value=fmt_hex4(app.file_end))
    call_var  = tk.StringVar(value=fmt_hex4(app.file_callp or app.file_callf))

    # --- GUI-Felder ----------------------------------------------------
    style = ttk.Style()
    style.configure("RightPad.TEntry", padding=(8, 0, 8, 0))  # (links, oben, rechts, unten)
    fg = "#444444"

    row = 0
    ttk.Label(frame, text="START", foreground=fg).grid(row=row, column=0, sticky="e", pady=3, padx=[10,2])
    ttk.Entry(frame, textvariable=start_var, width=4, font=("Consolas", 10), justify="right", style="RightPad.TEntry").grid(row=row, column=1, sticky="w", pady=3, padx=[2,10])

    row += 1
    ttk.Label(frame, text="ENDE", foreground=fg).grid(row=row, column=0, sticky="e", pady=3, padx=[10,2])
    ttk.Entry(frame, textvariable=end_var, width=4, font=("Consolas", 10), justify="right", style="RightPad.TEntry").grid(row=row, column=1, sticky="w", pady=3, padx=[2,10])

    row += 1
    ttk.Label(frame, text="CALL", foreground=fg).grid(row=row, column=0, sticky="e", pady=3, padx=[10,2])
    ttk.Entry(frame, textvariable=call_var, width=4, font=("Consolas", 10), justify="right", style="RightPad.TEntry").grid(row=row, column=1, sticky="w", pady=3, padx=[2,10])

    # Autostart-Checkbox
    row += 1

    ttk.Label(frame, text="Autostart", foreground=fg).grid(row=row, column=0, sticky="e", pady=3, padx=[10,2])

    autostart_var = tk.BooleanVar(value=bool(app.autostart_want))
    autostart_chk = ttk.Checkbutton(
        frame,
        variable=autostart_var,
        takefocus=False,     # oder 0
    )
    autostart_chk.grid(row=row, column=1, sticky="w", pady=3, padx=[2, 10])


    # --- Validierung CALL & Aktivieren/Deaktivieren des OptionMenu -----
    def is_valid_hex_1_to_4(s: str) -> bool:
        s = s.strip()
        if not s:
            return False
        if len(s) > 4:
            return False
        try:
            int(s, 16)
            return True
        except ValueError:
            return False


    # --- Button-Leiste -------------------------------------------------
    row += 1
    btn_frame = ttk.Frame(frame)
    btn_frame.grid(row=row, column=0, columnspan=2, pady=(8, 0))

    ok_clicked = False

    # Hilfsfunktion: HEX-Feld parsen (leer => None, Fehler => Ellipsis)
    def parse_hex_field(var, feldname: str):
        s = var.get().strip()
        if not s:
            return None
        try:
            return int(s, 16)
        except ValueError:
            messagebox.showerror(
                "Fehler",
                f"Ungültige Hex-Zahl im Feld '{feldname}'. Bitte 1–4 Hex-Zeichen (0–9, A–F) eingeben.",
                parent=dialog,
            )
            return ...

    def on_ok():
        nonlocal ok_clicked

        start_int = parse_hex_field(start_var, "Start")
        if start_int is ...:
            return

        end_int = parse_hex_field(end_var, "Ende")
        if end_int is ...:
            return

        call_int = parse_hex_field(call_var, "CALL / Einsprung")
        if call_int is ...:
            return

        # einfache Plausibilitätsprüfung
        if start_int is not None and end_int is not None and end_int <= start_int:
            messagebox.showerror(
                "Fehler",
                "Endadresse muss größer als Startadresse sein.",
                parent=dialog,
            )
            return

        # Werte übernehmen (int oder None)
        app.caos_start = start_int
        app.caos_end   = end_int
        app.caos_call  = call_int
        app.autostart_want = bool(autostart_var.get())
        ok_clicked = True
        dialog.destroy()

    def on_cancel():
        dialog.destroy()

    ttk.Button(btn_frame, text="Übertragung starten", command=on_ok).grid(row=0, column=0, padx=5)
    #ttk.Button(btn_frame, text="Abbrechen", command=on_cancel).grid(row=0, column=1, padx=5)
    dialog.protocol("WM_DELETE_WINDOW", on_cancel)

    # Dialog ungefähr über dem Hauptfenster zentrieren (optional)
    app.root.update_idletasks()
    dialog.update_idletasks()
    x_root = app.root.winfo_rootx()
    y_root = app.root.winfo_rooty()
    w_root = app.root.winfo_width()
    h_root = app.root.winfo_height()
    w = dialog.winfo_width()
    h = dialog.winfo_height()
    x = x_root + (w_root - w) // 2
    y = y_root + (h_root - h) // 2
    dialog.geometry(f"+{x}+{y}")

    dialog.wait_window()
    return ok_clicked



class DualOptionsDialog(simpledialog.Dialog):
    def __init__(self, parent, title="Hinweis", text="Fertig.", okbuttontext="OK", cancelbuttontext=None):
        self._text = text
        self.okbuttontext = okbuttontext
        self.cancelbuttontext = cancelbuttontext
        self.result = False  # Standard: Abbruch
        super().__init__(parent, title)

    def body(self, master):
        tk.Label(master, text=self._text).pack(padx=20, pady=15)

    def buttonbox(self):
        box = tk.Frame(self)

        btn_done = tk.Button(box, text=self.okbuttontext, width=12, command=self.ok, default=tk.ACTIVE)
        btn_done.pack(side=tk.LEFT, padx=5, pady=10)

        if self.cancelbuttontext:
            btn_cancel = tk.Button(box, text=self.cancelbuttontext, width=12, command=self.cancel)
            btn_cancel.pack(side=tk.LEFT, padx=5, pady=10)

        self.bind("<Return>", lambda e: self.ok())
        self.bind("<Escape>", lambda e: self.cancel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)  # Fenster-X => Abbruch

        box.pack()

    def apply(self):
        # Wird von ok() aufgerufen
        self.result = True

