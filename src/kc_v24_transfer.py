# Programm zur Datenübertragung PC -> KC
# 
# Daten werden vom COM-Port des PC auf die V.24-Schnittstelle des M003-Moduls im KC84/4 übertragen
# Dabei wird die beim KC85/4 nach einem RESET standardmäßig aktivierte ESC-T-Polling und Interruptmodus genutzt
#
# Version 1.1 vom 23.12.2025
# 
# exe bauen aus dem Projektordner (oberhalb ./src) via:
# python -m PyInstaller --noconfirm --clean --onefile --windowed --name KC-V24-Transfer --paths src --add-data "src\assets;assets" --add-data "src\bin;bin" src\kc_v24_transfer.py
from __future__ import annotations 

import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import font as tkfont
from pathlib import Path
import sys
import configparser
import serial
import time
import os
import ctypes
import threading
import copy
import unicodedata
import math
from collections import deque
from datetime import datetime
from typing import List, Optional
from serial.tools import list_ports

import kc_v24_transfer_gui as gui

from kc_v24_transfer_kcfileformattools import ParseResult

from kc_v24_transfer_kcfileformattools import KC_V24_Transfer_FileFormatTools
from kc_v24_transfer_basicdetokenizer import KC_V24_Transfer_BASICdetokenizer
#from kc_v24_transfer_kcfileformattools import ParseResult
from kc_v24_transfer_kcjob import KC_Job

from enum import Enum, auto

class ProcessingResult(Enum):
    DONE = auto()
    CANCELED = auto()
    FAILED = auto()
    
class KC_V24_TransferApp:
    
    APP_NAME = "KC-V24-Transfer"
    VERSION  = "1.3"
    
    BASE_DIR      = Path(__file__).resolve().parent
    
    if os.name == "nt":
        _cfg_root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        CONFIG_DIR = Path(_cfg_root) / APP_NAME if _cfg_root else (BASE_DIR / APP_NAME)
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_NAME)
        
    else:
        _xdg = os.environ.get("XDG_CONFIG_HOME")
        CONFIG_DIR = (Path(_xdg) if _xdg else (Path.home() / ".config")) / APP_NAME

    CONFIG_PATH   = CONFIG_DIR / (APP_NAME + ".ini")
    ASSET_PATH    = BASE_DIR / "assets"
    BIN_PATH      = BASE_DIR / "bin"
    
    # Zeichen ersetzen für Inhalte aus dem Clipboard
    UNICODE_CLIPBOARD_MAP = str.maketrans({
        "\u00a0": " ",   # NBSP
        "\u2013": "-",   # en dash
        "\u2014": "-",   # em dash
        "\u2212": "-",   # minus
        "\u2018": "'", "\u2019": "'",  # quotes
        "\u201c": '"', "\u201d": '"',
        "\u2026": "...", # ellipsis
        "\ufeff": "",    # BOM
    })

    # KC-Steuercodes (KC85/4): CUL=08, CUR=09, CUD=0A, CUU=0B; HOME=10; PAGE=11; SCROLL=12; ENTER=0D;
    # CEL=18 (Zeilenende), CCR=19 (Zeilenanfang), DEL=1F, ESC=1B.
    
    # Modifizierer-Bitmasks (Tk): je nach Plattform kann Alt/Meta variieren, Shift ist i. d. R. stabil.
    _TK_SHIFT_MASK = 0x0001
    _TK_CTRL_MASK  = 0x0004
    _TK_ALT_MASK   = 0x0008  # häufig Mod1/Alt

    # Erweiterbar: Kombinationen aus (keysym, mods) -> Payload
    # mods als Tupel von Strings, z. B. ("Shift",) oder ("Control","Shift")
    KC_KEYCOMBO_MAP = {
        # HOME / Zweitbelegung
        ("Home", ()):              b"\x10",  # HOME
        ("Home", ("Shift",)):      b"\x0C",  # Zweitbelegung HOME (CLEAR SCREEN)

        # Cursortasten / Zweitbelegungen
        ("Down", ()):              b"\x0A",  # CURSOR DOWN
        ("Down", ("Shift",)):      b"\x12",  # Zweitbelegung CURSOR DOWN (SCROLL-Modus)
        ("Up", ()):                b"\x0B",  # CURSOR UP
        ("Up", ("Shift",)):        b"\x11",  # Zweitbelegung CURSOR UP (PAGE-Modus)

        ("Left", ()):              b"\x08",  # CURSOR LINKS
        ("Left", ("Shift",)):      b"\x19",  # Zweitbelegung CURSOR LINKS (Cursor auf Zeilenanfang)
        ("Right", ()):             b"\x09",  # CURSOR RECHTS
        ("Right", ("Shift",)):     b"\x18",  # Zweitbelegung CURSOR RECHTS (Cursor auf Zeilenende)

        ("Escape", ()):            b"\x03",  # BRK

        ("Pause", ()):             b"\x13",  # STOP
        ("Pause", ("Shift",)):     b"\x1B",  # Zweitbelegung STOP (ESC-Code zum Einschalten der "3. Tastaturebene")

        ("Insert", ()):            b"\x1A",  # INS
        ("Insert", ("Shift",)):    b"\x14",  # Tastenquittierungston ein/ausschalten (Zweitbelegung INS)

        ("Delete", ()):            b"\x1F",  # DEL
        ("Delete", ("Shift",)):    b"\x02",  # Zweitbelegung DEL (Zeile löschen)

        ("Delete", ("Control",)):              b"\x01",  # CLR
        ("Delete", ("Control", "Shift")):      b"\x0F",  # Zweitbelegung CLR (Aufruf eines Sonderprogramms)

        ("BackSpace", ()):         b"\x08\x1F",  # CursorLinks + DEL

        ("CapsLock", ()):          b"\x16",  # SHIFT LOCK
        ("Caps_Lock", ()):         b"\x16",  # SHIFT LOCK (Tk-Keysym-Variante)
        
        ("Return", ()):            b"\x0D",  # ENTER
        ("KP_Enter", ()):          b"\x0D",
    }    
        
    def __init__(self, root):

        # -------------------------------------------------------------------------
        # GUI-Texte
        # -------------------------------------------------------------------------
        self.SBTN_SEND              = "Übertragen" # Hilfvariable Button-Beschriftung
        self.SBTN_CANCEL            = "Abbruch"    # Hilfvariable Button-Beschriftung
        

        self.root = root
        self.root.title(f"{self.APP_NAME} v{self.VERSION}")
        self.root.resizable(False, False)
        
        try:
            logo_path_png = str(self.ASSET_PATH / "kc85logo.png")  # z.B. ./assets/logo.png
            logo_path_ico = str(self.ASSET_PATH / "kc85logo.ico")  # z.B. ./assets/logo.png
            self._img_app_icon_png = tk.PhotoImage(file=logo_path_png)
            #self._img_app_icon_ico = tk.PhotoImage(file=logo_path_ico)
            self.root.iconphoto(True, self._img_app_icon_png)
            self.root.iconbitmap(logo_path_ico)
        except Exception as e:
            print(f"Logo konnte nicht geladen werden: {e}")
        
        self.com_port           = None            # hält das COM-Portobjekt
        self.com_port_name      = ""              # Name des aktuellen COM-Ports (vom COM-Portobjekt)
        self.com_port_menu_name = tk.StringVar(value="") # Name der aktuellen COM-Port-Menüauswahl in self.port_option

        self._keybmode_enabled  = False           # (Tastaturnmodus) True: Zeicheneingaben werden (in trans_state "KEY") an den KC weitergeleitet
        self.trans_state        = None            # hält den aktuellen Status des Transfersystems
                                                  # None:    uninitialisiert
                                                  # "BROKE": nach Abgebrochener Binärübertragung - der KC wartet dann auf seiner Seite auf Abschluss, bis er wieder in den Tastaturmodus wechseln kann 
                                                  # "BIN":   im ESC-U/ESC-T-Polling-Modus
                                                  # "KEY":   Interupt-Modus (Tastatureingaben)

        self.pr                  = None           # hält das ParseResult der zuletzt geladenen Datei
        self.file_name           = None           # nur Dateiname ohne Pfad
         
        self.pr_bascoder         = None           # hält das ParseResult der geladenen Bascoderdatei
        self.file_name_bascoder  = None           # Dateiname der geladenen Bascoder-Datei
        
        # die stubs schalten die Schnittstellengeschwindigkeit zum Laden des Hauptprogramms auf 2400 Baud
        # je nach Ladeadresse des Hauptprogramms wird ein stub vorgeladen, der ausserhalb des Speicherbereichs liegt
        
        self.use_turboload       = True           # wenn True, wird vor Binärübertragungen ein Stub mit 2400 Baud-Pollingroutine geladen
        self.pr_0200stub         = None           # hält ein parseResult mit den Binärdaten des Schnittstellen-Umschalters auf 2400 Baud, der unten geladen wird
        self.file_name_0200stub  = None           # Dateiname des Umschalter-bins
        self.pr_BF00stub         = None           # hält ein parseResult mit den Binärdaten des Schnittstellen-Umschalters auf 2400 Baud, der oben geladen wird
        self.file_name_BF00stub  = None           # Dateiname des Umschalter-bins
        
        self.last_basicodelinenumber = None       # die letzte Zeilennummer des BASICODE-Programmes

        self._rlz_hist_seconds = deque(maxlen=20) # Hilfsvariable zur Glättung der Restlaufzeitanzeige

        # werden in update_gui() ausgewertet
        self.gui_sendbutton_state = False          # Aktueller Soll-Status des Senden-Schalters False: deaktiviert, True: aktiviert
        self.gui_sendbutton_text  = self.SBTN_SEND # Aktueller Senden-Modus der App 0: Übertragen, 1: Abbruch

        
        # -------------------------------------------------------------------------
        # Zeugs für Nebenläufigkeit
        # -------------------------------------------------------------------------
        self.jobs: List[KC_Job] = []             # Liste der aktuellen Jobs verschiedenen Status
        self._worker: Optional[threading.Thread] = None
        self._current_job: Optional[KC_Job]      = None
        self._stop_all        = threading.Event()
        self._lock = threading.Lock()            # der Lock für das Theading
    
        self._processing_done = threading.Event()
        self._processing_result: ProcessingResult | None = None

        self._jobssent              = 0          # Anzahl der durch bereits abgearbeitete Jobs gesendeter Bytes
        self._jobstotal             = 0          # Anzahl der durch alle Jobs zu sendender Bytes
        self._currentjobnr          = 0          # Nummer aktuell abgearbeiteter Jobs
        self._totaljobcount         = 0          # Anzahl aller vorhandenen Jobs

        
        
        # -------------------------------------------------------------------------
        # Timeout-Überwachung (COM-Port / Jobs)
        # -------------------------------------------------------------------------
        # self.timeout_comport / self.timeout_job werden extern gesetzt (Sekunden, None = deaktiviert)
        self.timeout_comport: int | None = 10    # sendende Jobs (job.total > 0): max. Stillstand ohne Fortschritt
        self.timeout_job: int | None     = 10    # sonstige Jobs (job.total == 0) ohne askstart: max. Laufzeit

        # interne Überwachung (GUI-Thread, time.monotonic())
        self._watch_job: KC_Job | None             = None
        self._watch_job_started_mono: float | None = None
        self._watch_last_sent: int                 = 0
        self._watch_last_sent_mono: float | None   = None

        self._timeout_handled: bool                = False
        self._timeout_status_text: str | None      = None

        # -------------------------------------------------------------------------
        # Übertragungs-Konfiguration für Übertragungen im Keyboard-Übertragungsmodus
        # -------------------------------------------------------------------------
        self.textconfig_showkonfigdialog  = True    # der Textkonfigdialog soll bei der nächsten übertragung wieder angezeigt werden
        self.textconfig_linewidth         = 40      # nach wievielen Zeichen wird die Zeile umgebrochen und gescrollt (40 - BASIC-Promptlänge)
        self.textconfig_promptwidth       = 1       # wieviele Zeichen nimmt der BASIC-Prompt in Anspruch
        self.textconfig_init_delay        = 300     # ms Wartezeit nach dem init der Schnittstelle
        self.textconfig_init_clsdelay     = 600     # ms Wartezeit bis der Eingabeprompt nach einem CLS bereit ist
        self.textconfig_init_basic1delay  = 700     # ms Wartezeit nach einem Start von BASIC in CAOS
        self.textconfig_init_basic2delay  = 3800    # ms Wartezeit nach einem Start von BASIC (EIngabe von "MEMORY END")
        self.textconfig_init_rebasicdelay = 300     # ms Wartezeit nach einem Start von BASIC in CAOS
        self.textconfig_char_delay        = 0       # ms warten nach jeder Zeicheneingabe
        self.textconfig_linescroll_delay  = 300     # nach Zeilenumbruch (ms Zeit, die der Rechner zum Scrollen einer Zeile braucht)
        self.textconfig_process_delay     = 200     # nach Zeilenübergabe (ms Zeit, die der Rechner zur Verarbeitung der Eingabe braucht)
        self.textconfig_command_addition  = 80      # zusätzliche Zeit für jeden zusätzlichen Befehl in der Zeile (es wird stumpf nach Doppelpunkten gesucht)
        self.textconfig_linethrottle      = 0.4     # 0.4 = 400ms/1000 Zeilen - wird mit jeder zusätzlichen Zeile Programmcode dem Zeilendelay hinzugefügt - die BASIC Befehlsübernahme wird mit zunehmender Zeilenzahl langsamer
        self.textconfig_lines             = 32      # maximal darstellbare Zeilen auf dem Bildschirm
        self.textconfig_basicode_delay    = 50      # wenn Basicode schon im Speicher ist, wird der BASIC-Editor langsamer
        self.textconfig_dim_ref_delay     = 40      # (20 gemessen)  DIM-Sonderbehandlung - dim_ref:  Zeit für Zugriff auf eine Feldvariable
        self.textconfig_dim_unit_delay    = 0.2     # (0.3 gemessen) DIM-Sonderbehandlung - dim_unit: Zeit für Deklaration EINER einzelnen Feldvariable
        self.textconfig_var_ref_delay     = 50      # Variablenaufruf-Sonderbehandlung - Zeit für Referenzierung einer Variable
         
        # -------------------------------------------------------------------------
        # UI bauen
        # -------------------------------------------------------------------------
        gui.create_widgets(self)
        self.root.after(0, self._center_on_primary_screen)

        self.root.protocol("WM_DELETE_WINDOW", self.on_exit)

        # neu: zentral am Hauptfenster binden (greift, sobald das Fenster aktiv ist)
        self.root.bind("<KeyPress>",  self.on_key, "+")
        self.root.bind("<Control-v>", self.on_pastebasic, "+")
        self.root.bind("<Control-b>", lambda event: self.on_pastebasic(event, slow=True), "+")
        self.root.bind("<Control-V>", self.on_pastetext, "+")
        
        # Fokus sicherstellen, sobald das Fenster aktiv wird
        self.root.bind("<FocusIn>", self._ensure_focus, "+")

        # Im Tastaturmodus: Aktivierungstasten (Return/Space) dürfen keine GUI-Buttons auslösen
        self.button_frame.bind("<Return>",   self._swallow_widget_activation_keys, "+")
        self.button_frame.bind("<KP_Enter>", self._swallow_widget_activation_keys, "+")
        self.button_frame.bind("<space>",    self._swallow_widget_activation_keys, "+")  # optional, aber sinnvoll

        self.register_descendants(self.root, self.button_frame)

        # Kontextmenü (Rechtsklick): Einfügen aus Zwischenablage im Tastaturmodus
        self._context_menu = tk.Menu(self.root, tearoff=0)
        self._context_menu.add_command(label="Einfügen (Code) <STRG+V>",         command=self.on_pastebasic)
        self._context_menu.add_command(label="Einfügen (Code langsam) <STRG+B>", command=lambda: self.on_pastebasic(slow=True))
        self._context_menu.add_command(label="Einfügen (Text) <UMSCH+STRG+V>",  command=self.on_pastetext)
        # Rechtsklick global abfangen (auch wenn Fokus in einem anderen Widget liegt)
        self.root.bind_all("<Button-3>", self._show_context_menu, "+")           # Windows/Linux
        self.root.bind_all("<Button-2>", self._show_context_menu, "+")           # macOS (je nach System)
        self.root.bind_all("<Control-Button-1>", self._show_context_menu, "+")   # macOS (Alternative)

        self.btn_load.focus_set()                   # Fokus auf ein Widget setzen, damit Tastatureingaben ankommen
        
        # -------------------------------------------------------------------------------------------------
        # die App initialisieren - Zustand initial setzen
        # -------------------------------------------------------------------------------------------------
        self.set_transfer_status(status="bereit")
        
        # Konfiguration laden
        if not self.load_config():
            pass
        
        # Serieller Port
        self.PORT_CHOOSE   = "Port auswählen!"
        self.PORT_OCCUPIED = "(belegt)"
        
        self.init_port_menu()
        
        self.load_bascoder() # Bascoder aus datei unter ./bascoder/ laden
        self.load_stubs()    # Umschalter-Stubs laden
        
        self.set_controls_send(text=self.SBTN_SEND, send_enabled=False)
        
        self.gui_sendbutton_state = False         
        self.gui_sendbutton_text  = self.SBTN_SEND
        self.update_gui()
        
        self._update_keybmode_button()
       
        self.set_transfer_status(status=f"bereit (py: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro})")
    
    
    #  de-/aktiviert den Lade- und Senden-Schalter und die COM-Portauswahl
    def update_gui(self):
    
        if self.com_port is None:
            self.btn_send.config(state="disabled", text=self.gui_sendbutton_text)
        
        else:
            state = "normal" if self.gui_sendbutton_state else "disabled"
            
            if state != self.btn_send.cget("state") or self.gui_sendbutton_text != self.btn_send.cget("text"): # nur bei Änderung config neu setzen
                self.btn_send.config(state=state, text=self.gui_sendbutton_text)
        
        # während einer Datenübertragung Button disablen
        if self._worker and self._worker.is_alive():
            if self.btn_load.cget("state")    != "disabled": self.btn_load.config(state="disabled")             # nur bei Änderung config neu setzen
            if self.port_option.cget("state") != "disabled": self.port_option.configure(state="disabled")    # nur bei Änderung config neu setzen
        else:
            if self.btn_load.cget("state")    != "normal": self.btn_load.config(state="normal")                 # nur bei Änderung config neu setzen
            if self.port_option.cget("state") != "normal": self.port_option.configure(state="normal")           # nur bei Änderung config neu setzen
        
        self._update_keybmode_button()

    # quasi ein wrapper für update_gui 
    def set_controls_send(self, text: str | None, send_enabled: bool | None):
        
        self.gui_sendbutton_state = send_enabled         
        self.gui_sendbutton_text  = text
        self.update_gui()
        return
        
    ##################################################################################################
    # GUI - Tasteneingaben über Mainframe fangen
    ##################################################################################################
    def _ensure_focus(self, event=None):
        # Wenn kein Widget den Fokus hat, Fokus auf das Hauptfenster setzen
        if self.root.focus_get() is None:
            self.root.focus_set()

    def _center_on_primary_screen(self) -> None:
        """Zentriert das Hauptfenster auf dem primären Bildschirm."""
        try:
            # Layout berechnen lassen
            self.root.update_idletasks()

            w = self.root.winfo_width()
            h = self.root.winfo_height()
            if w <= 1 or h <= 1:
                w = self.root.winfo_reqwidth()
                h = self.root.winfo_reqheight()

            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()

            x = max(0, (sw - w) // 2)
            y = max(0, (sh - h) // 2)

            self.root.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            # Keine harte Abhängigkeit von der Fensterverwaltung erzwingen
            pass

    ##################################################################################################
    # Threading-Zeugs
    ##################################################################################################
    
    # threadsicheres Setzen der Variable (aus den Jobs)
    def set_trans_state(self, value: str) -> None:
        with self._lock:
            self.trans_state = value  
             
    # threadsicheres Lesen der Variable (aus den Jobs)
    def get_trans_state(self) -> str:
        with self._lock:
            return self.trans_state
            
    # threadsicheres Setzen der Variable (aus den Jobs)
    def set_last_basicodelinenumber(self, value: str | None) -> None:
        with self._lock:
            self.last_basicodelinenumber = value
            print(f"set_last_basicodelinenumber: {value}")
            
    # threadsicheres Holen der Variable (in die Jobs)
    def get_last_basicodelinenumber(self) -> str | None:
        with self._lock:
            return self.last_basicodelinenumber
    
    # startet die Abarbeitung der KC_Jobs
    def start_processing(self) -> None:
        if self._worker and self._worker.is_alive():
            return  # läuft bereits

        self._stop_all.clear()
        self._processing_done.clear()
        self._processing_result = None

        # Timeout-Überwachung zurücksetzen
        self._timeout_handled = False
        self._timeout_status_text = None
        self._watch_job = None
        self._watch_job_started_mono = None
        self._watch_last_sent = 0
        self._watch_last_sent_mono = None

        self._jobssent      = 0
        self._jobstotal     = 0
        self._currentjobnr  = 1
        self._totaljobcount = 0
        for job in self.jobs:
            self._jobstotal     += job.total
            self._totaljobcount += 1

        self._keybmode_enabled = False
        self.jobs_starttime = datetime.now()
        self._rlz_hist_seconds.clear()

        # WICHTIGER FUNKTIONSAUFRUF: separater Worker-Thread startet die Abarbeitung
        self._worker = threading.Thread(target=self._run_jobs_sequentially, daemon=True)
        self._worker.start()
        
        self._poll_status()
    
    # wird nebenläufig ausgeführt    
    def _run_jobs_sequentially(self) -> None:
        """
        Läuft im Worker-Thread:
        - nimmt Job 1
        - führt startjob() aus (blockierend)
        - nach DONE/FAIL -> nächster Job
        """
        any_failed = False
        try:
            for job in self.jobs:
                if self._stop_all.is_set():
                    break

                self._current_job = job
                job.startjob()  # WICHTIG: Job läuft hier im Worker-Thread

                """Thread-sicherer Schnappschuss für Statusabfragen im Haupt-/GUI-Thread."""
                state, sent, _ = job.snapshot()  # liefert state/sent threadsicher
                with self._lock:
                    self._jobssent += self._current_job.total
                    self._currentjobnr += 1
                    
                if state == KC_Job._JS_FAILED:
                    any_failed = True
                    print(f"any_failed {job.type}")
                if state == KC_Job._JS_NOAFTERASK:   # Startfrage wurde mit nein beantwortet
                    break

        finally:
            self._current_job = None  # wird bei Ihnen ohnehin am Ende gesetzt

            if self._stop_all.is_set():
                self._processing_result = ProcessingResult.CANCELED
            elif any_failed:
                self._processing_result = ProcessingResult.FAILED
            else:
                self._processing_result = ProcessingResult.DONE

            self._processing_done.set()
            self.jobs.clear()
    
    # holt Informationen aus den nebenläufigen Jobs    
    def _poll_status(self) -> None:
        job = self._current_job

        # Keyboardschalter aktualisieren
        self._update_keybmode_button()

        self.jobs_currenttime = datetime.now()
        now_mono = time.monotonic()

        if job is None:
            # Überwachung zurücksetzen, wenn kein Job aktiv ist
            self._watch_job = None
            self._watch_job_started_mono = None
            self._watch_last_sent = 0
            self._watch_last_sent_mono = None

            # Ende nur dann, wenn Worker wirklich fertig ist
            if self._worker and not self._worker.is_alive():
                res = self._processing_result

                if res == ProcessingResult.CANCELED:
                    self.set_transfer_status("Übertragung abgebrochen")
                elif res == ProcessingResult.FAILED:
                    self.set_transfer_status("Übertragung fehlgeschlagen")
                else:
                    self.set_transfer_status("Übertragung abgeschlossen")

                self.set_controls_send(text=self.SBTN_SEND, send_enabled=True)

                self._keybmode_enabled = True   # remote keyboard einschalten
                self._update_keybmode_button()

                self.jobs_currenttime = None
                self.jobs_starttime = None

                # Timeout-Status zurücksetzen (für die nächste Übertragung)
                self._timeout_handled = False
                self._timeout_status_text = None

                return  # wichtig: kein weiteres after()
            else:
                self.root.after(100, self._poll_status)
                return

        state, sent, cancelable = job.snapshot()

        # ---------------------------------------------------------------------
        # Timeout-Prüfung:
        # - sendende Jobs (job.total > 0): Fortschritt über "sent"
        # - Jobs ohne Nutzdaten (job.total == 0) und askstart=False: Laufzeit
        # ---------------------------------------------------------------------
        if job is not self._watch_job:
            self._watch_job = job
            self._watch_job_started_mono = now_mono
            self._watch_last_sent = sent
            self._watch_last_sent_mono = now_mono
        elif sent != self._watch_last_sent:
            self._watch_last_sent = sent
            self._watch_last_sent_mono = now_mono

        if (not self._timeout_handled) and state == KC_Job._JS_RUNNING:
            if (
                self.timeout_comport is not None
                and self.timeout_comport > 0
                and job.total > 0
                and self._watch_last_sent_mono is not None
                and (now_mono - self._watch_last_sent_mono) > self.timeout_comport
            ):
                self.on_comport_timeout(job, now_mono - self._watch_last_sent_mono)
                cancelable = False

            elif (
                self.timeout_job is not None
                and self.timeout_job > 0
                and job.total <= 0
                and (not getattr(job, "askstart", False))
                and self._watch_job_started_mono is not None
                and (now_mono - self._watch_job_started_mono) > self.timeout_job
            ):
                self.on_job_timeout(job, now_mono - self._watch_job_started_mono)
                cancelable = False

        allsent = self._jobssent + sent   # bislang über alle Jobs gesendete Datenmenge

        # Nach Timeout: Status einfrieren, aber weiter pollen (damit Abschluss sauber erkannt wird)
        if self._timeout_handled and self._timeout_status_text:
            self.set_transfer_status(
                status=self._timeout_status_text,
                sent=allsent,
                total=self._jobstotal,
                currentjobnr=self._currentjobnr,
                totaljobcount=self._totaljobcount,
                restlaufzeit=None,
                cancelable=False,
            )
            self.set_controls_send(text=self.SBTN_SEND, send_enabled=False)
            self.root.after(200, self._poll_status)
            return

        rlzStr = self.get_restlaufzeit(
            starttime=self.jobs_starttime,
            currenttime=self.jobs_currenttime,
            sent=allsent,
            total=self._jobstotal,
        )
        self.set_transfer_status(
            "Übertragung läuft",
            allsent,
            self._jobstotal,
            self._currentjobnr,
            self._totaljobcount,
            rlzStr,
            cancelable,
        )
        self.set_controls_send(text=self.SBTN_CANCEL, send_enabled=cancelable)
        self.root.after(100, self._poll_status)


    def stop_all(self) -> None:
        # optional: globale Stop-Funktion
        self._stop_all.set()
        if self._current_job:
            self._current_job.cancel()


    def _interrupt_and_close_com_port(self) -> None:
        """Versucht blockierende Schreib-/Leseoperationen zu unterbrechen und den Port zu schließen."""
        ser = self.com_port
        self.com_port = None  # Referenz früh lösen

        if ser is None:
            return

        try:
            if hasattr(ser, "cancel_write"):
                try:
                    ser.cancel_write()
                except Exception:
                    pass
            if hasattr(ser, "cancel_read"):
                try:
                    ser.cancel_read()
                except Exception:
                    pass
        finally:
            try:
                ser.close()
            except Exception:
                pass

        # GUI aktualisieren
        try:
            self.refresh_port_menu()
        except Exception:
            pass
        try:
            self.update_gui()
        except Exception:
            pass
        try:
            self._update_keybmode_button()
        except Exception:
            pass

    def on_comport_timeout(self, job: KC_Job, idle_seconds: float) -> None:
        """Callback bei blockierendem COM-Port (aus _poll_status(), GUI-Thread)."""
        if self._timeout_handled:
            return
        self._timeout_handled = True
        self._timeout_status_text = f"COM-Port blockiert (keine Daten seit {idle_seconds:.1f}s)"
        self.stop_all()
        self.set_trans_state("BROKE")
        self._interrupt_and_close_com_port()
        try:
            messagebox.showerror(
                "Fehler",
                "Die Übertragung wurde beendet,\n"
                "weil der COM-Port blockiert war.\n"
                "Bitte Verbindung/Porteinstellung prüfen.",
                parent=self.root,
            )
        except Exception:
            pass

    def on_job_timeout(self, job: KC_Job, run_seconds: float) -> None:
        """Callback bei Job-Timeout (Jobs ohne Nutzdaten; askstart=False)."""
        if self._timeout_handled:
            return
        self._timeout_handled = True
        self._timeout_status_text = f"Job-Timeout (läuft seit {run_seconds:.1f}s)"
        self.stop_all()
        self.set_trans_state("BROKE")
        self._interrupt_and_close_com_port()
        try:
            messagebox.showerror(
                "Fehler",
                "Die Übertragung wurde beendet,\n"
                "weil der COM-Port blockiert war.\n"
                "Bitte Verbindung/Porteinstellung prüfen.",
                parent=self.root,
            )
        except Exception:
            pass


    # ------------------------------------------------------------------------------------------------------------------------
    # Logik zum Abfangen aller Tastatureingaben
    # ------------------------------------------------------------------------------------------------------------------------
    #
    # Events werden in Tk in der Reihenfolge der bindtags abgearbeitet:
    # (widget, class, toplevel, "all").###
    #
    # Sobald ein Handler "break" zurückgibt, werden keine weiteren Bindings ausgeführt.
    #
    # Wenn dem Frame als erstes bindtag einfügt wird und dort "break" liefert,
    # bekommen wir das Event, aber das Widget (z. B. Entry) bekommt es nicht mehr.
    def on_key(self, event):
        """Zentrale Tastaturbehandlung: sendet KC-Codes über V.24."""
        
        if self.trans_state != "KEY":
            return

        if self.com_port is None:
            print("on_key: kein aktiver COM-Port")
            return "break"
        if self._keybmode_enabled:
            latin2kc = KC_V24_Transfer_BASICdetokenizer._LATIN_2_KC

            keysym = event.keysym
            
            # 1) Kombinationen (z. B. Shift+Pause) zuerst prüfen
            mods = self._mods_from_event(event)
            combo_key = (keysym, mods)
            if combo_key in self.KC_KEYCOMBO_MAP:
                payload = self.KC_KEYCOMBO_MAP[combo_key]
            # 2) Funktionstasten    
            elif keysym.startswith("F") and keysym[1:].isdigit():
                n = int(keysym[1:])
                if 1 <= n <= 12:
                    payload = bytes([0xF0 + n])  # F1=0xF1 ... F12=0xFC
                else:
                    return "break"
            else:
                ch = event.char
                if not ch:
                    return "break"

                # Upper/LowerCase invertieren für Buchstaben
                if len(ch) == 1:
                    o = ord(ch)
                    if 0x41 <= o <= 0x5A:      # A-Z
                        ch = chr(o + 0x20)     # -> a-z
                    elif 0x61 <= o <= 0x7A:    # a-z
                        ch = chr(o - 0x20)     # -> A-Z

                # latin-1 kodieren und via _LATIN_2_KC umsetzen
                try:
                    raw = ch.encode("latin-1", errors="strict")
                except UnicodeEncodeError:
                    return "break"

                payload = bytes(latin2kc.get(b, b) for b in raw)

            try:
                self.com_port.write(payload)
                self.com_port.flush()
            except serial.SerialException as e:
                print(f"on_key: {e}")

            return "break"
    
    # Tastatur-Events auseinanderdröseln
    def _mods_from_event(self, event) -> tuple[str, ...]:
        st = getattr(event, "state", 0) or 0
        mods = []
        if st & self._TK_SHIFT_MASK:
            mods.append("Shift")
        if st & self._TK_CTRL_MASK:
            mods.append("Control")
        # Mod1/Alt hier bewusst ignorieren, da es unter Windows/Tk teils gesetzt ist,
        # obwohl die Taste nicht aktiv gedrückt wird (sonst schlägt das Mapping fehl).
        return tuple(sorted(mods))

                
    def _swallow_widget_activation_keys(self, event):
        """
        Im Tastaturmodus sollen Return/Space keine Widgets (z.B. Buttons) auslösen.
        Bei aktiver Tastaturweitergabe wird das Zeichen dennoch an den KC gesendet.
        """
        if self.trans_state == "KEY":
            if self._keybmode_enabled:
                self.on_key(event)  # sendet und würde sonst über root erst zu spät kommen
            return "break"
        return None

    def on_pastetext(self, event=None):
        """Leitet Paste aus der Zwischenablage an die serielle Schnittstelle weiter."""
        if self.trans_state is not None and self.trans_state != "KEY":
            return

        if self.com_port is None:
            return "break"

        try:
            clip = self.root.clipboard_get()
        except tk.TclError:
            return "break"

        if not isinstance(clip, str) or clip == "":
            return "break"

        text = clip.translate(self.UNICODE_CLIPBOARD_MAP)
        # Zeilenenden normalisieren (Clipboard: CRLF/CR -> LF)
        text = text.replace("\r\n", "\r").replace("\n", "\r")
        
        raw_kc = self._kc_payload_from_text(text)
       
        pr = ParseResult()
        pr.type         = pr._TYPE_TEXT
        pr.format       = pr._FORMAT_RAW
        pr.transferdata = raw_kc
        
        pr_nodata = copy.deepcopy(pr)
        pr_nodata.transferdata = bytearray()
        
        if self.trans_state != "KEY":
            self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_STARTKEYBMODE, pr=pr_nodata))
        
        self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_SENDTEXT, pr=pr))    
                
        self.start_processing()

        print(pr)

        return "break"

    def on_pastebasic(self, event=None, slow=False):
        """Leitet Paste aus der Zwischenablage an die serielle Schnittstelle weiter."""
        if self.trans_state is not None and self.trans_state != "KEY":
            return

        if self.com_port is None:
            return "break"

        try:
            clip = self.root.clipboard_get()
        except tk.TclError:
            return "break"

        if not isinstance(clip, str) or clip == "":
            return "break"

        text = clip.translate(self.UNICODE_CLIPBOARD_MAP)
        # Zeilenenden normalisieren (Clipboard: CRLF/CR -> LF)
        text = text.replace("\r\n", "\r").replace("\n", "\r")
        ####
        raw_kc = self._kc_payload_from_text(text)
        
        pr = ParseResult()
        pr.type         = pr._TYPE_TEXT
        pr.format       = pr._FORMAT_RAW
        pr.transferdata = raw_kc
        
        pr_nodata = copy.deepcopy(pr)
        pr_nodata.transferdata = bytearray()
        
        if self.trans_state != "KEY":
            self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_STARTKEYBMODE, pr=pr_nodata))

        if(slow):       # Eingabe/Übergabe verlangsamen?
            basiclinesoffset=2000
        else:
            basiclinesoffset=0

        self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_SENDBASICTEXT, pr=pr, basiclinesoffset=basiclinesoffset))
        
        self.start_processing()

        print(pr)

        return "break"
        

    def _kc_payload_from_text(self, text: str) -> bytearray:
        """Wandelt Unicode-Text in KC-Tastaturcodes um (wie bei Einzeltasten)."""
        latin2kc = KC_V24_Transfer_BASICdetokenizer._LATIN_2_KC

        try:
            raw = text.encode("latin-1", "strict")
        except UnicodeEncodeError:
            # Nicht-Latin-1-Zeichen auf eine „näherungsweise“ Form bringen
            text = unicodedata.normalize("NFKD", text)
            raw = text.encode("latin-1", "replace")
            print("on_pastetext() UNICODE")

        # Latin-1 Bytes -> KC Bytes
        raw_kc = bytearray()
        for b in raw:
            b = latin2kc.get(b, b)

            # Zeilenende vereinheitlichen: \n -> überspringen (job_sendtext ignoriert 0x0A ohnehin)
            if b == 0x0A:
                continue

            # Zulässige KC-Textbytes: CR oder 0x20..0x7F
            if b == 0x0D or (0x20 <= b < 0x80):
                raw_kc.append(b)
            else:
                # Ersatz für nicht darstellbare Bytes (z.B. 0xBD)
                raw_kc.append(0x20)  # oder ord('?')
        
        return raw_kc


    def _clipboard_has_text(self) -> bool:
        try:
            clip = self.root.clipboard_get()
            return isinstance(clip, str) and clip != ""
        except tk.TclError:
            return False

    def _show_context_menu(self, event):
        # Nur im Tastaturmodus und mit aktiver Verbindung anzeigen
        if self.trans_state is not None and self.trans_state != "KEY" or self.com_port is None:
            return

        # Während einer Übertragung keine Eingaben anbieten
        if self._worker and self._worker.is_alive():
            return

        # Einfügen nur aktivieren, wenn Tastaturweitergabe aktiv ist und Text in der Zwischenablage liegt
        can_paste = self._clipboard_has_text()
        self._context_menu.entryconfigure(0, state=("normal" if can_paste else "disabled"))
        self._context_menu.entryconfigure(1, state=("normal" if can_paste else "disabled"))

        try:
            self._context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self._context_menu.grab_release()
            except tk.TclError:
                pass

        return "break"

    def register_widget(self, widget, frame):
        """Frame als erstes bindtag für ein einzelnes Widget eintragen."""
        tags = list(widget.bindtags())
        if frame not in tags:
            tags.insert(0, frame)      # Frame-Tag nach vorne
            widget.bindtags(tuple(tags))

    def register_descendants(self, parent, frame):
        """Alle Kinder (rekursiv) so registrieren, dass der Frame zuerst Ereignisse erhält."""
        for child in parent.winfo_children():
            self.register_widget(child, frame)
            self.register_descendants(child, frame)

    def on_keybmode_button_pressed(self) -> None:

        print("Keybmode-Einfachklick")
        # während einer Datenübertragung Button disablen
        if self._worker and self._worker.is_alive():
            return

        # ohne com_port -> Meldung
        if self.com_port is None:
            messagebox.showerror("Fehler", f"Kein serielle Verbindung zum KC\nErst COM-Port auswählen.")
            return

        # wenn keine Übertragung läuft
        if self.trans_state is None:
            self.enable_keyboardmodus_on_kc(enable_keybmode=True)
            
        elif self.trans_state == "KEY":
            self._keybmode_enabled = not self._keybmode_enabled
                
        elif self.trans_state == "BIN":
            self.enable_keyboardmodus_on_kc(enable_keybmode=True)
            
        elif self.trans_state == "BROKE":
            # RESET erfragen
            text="Zum Aktivieren des Tastaturmodus jetzt\n\n RESET\n\nam KC drücken!"
            dlg = gui.DualOptionsDialog(self.root, title="Tastaturmodus", text=text, okbuttontext="Erledigt!")
            if dlg.result:   # Option 1 (OK) gedrückt
                self.enable_keyboardmodus_on_kc(enable_keybmode=True)
            else:            # Option 2 (Abbrechen) gedrückt
                pass

        self._update_keybmode_button()
        
    def on_keybmode_button_doubleclicked(self, event=None):

        print("Keybmode-Doppelklick")
        # während einer Datenübertragung Button disablen
        if self._worker and self._worker.is_alive():
            return

        # ohne com_port -> Meldung
        if self.com_port is None:
            messagebox.showerror("Fehler", f"Kein serielle Verbindung zum KC\nErst COM-Port auswählen.")
            return

        if self.trans_state is None or self.trans_state == "KEY":  # bei Doppelklick immer nochmals senden
            self.enable_keyboardmodus_on_kc(enable_keybmode=True)

        self._update_keybmode_button()
        

    def _update_keybmode_button(self) -> None:
    
        def on(self):       self.keybmode_button.configure(style="KeybOn.TButton",       image=self._img_keyb_on,       text="aktiv",       state="normal")
        def off(self):      self.keybmode_button.configure(style="KeybOff.TButton",      image=self._img_keyb_disabled, text="einschalten", state="normal")
        def disabled(self): self.keybmode_button.configure(style="KeybDisabled.TButton", image=self._img_keyb_disabled, text="einschalten", state="normal")
        def inactive(self): self.keybmode_button.configure(style="KeybOff.TButton",      image=self._img_keyb_off,      text="aus",         state="disabled")
        
        # während einer Datenübertragung Button disablen
        if self._worker and self._worker.is_alive():
            inactive(self)
            return

        # ohne com_port Button disablen
        if self.com_port is None:
            inactive(self)
            return

        # wenn keine Übertragung läuft
        if self.trans_state is None:
            off(self)
        elif self.trans_state == "KEY":
            on(self) if self._keybmode_enabled else off(self)
        elif self.trans_state == "BIN":
            off(self) if self._keybmode_enabled else on(self)
        elif self.trans_state == "BROKE":
            disabled(self)
    
    # ------------------------ Datei laden ------------------------
    
    def enable_keyboardmodus_on_kc(self, enable_keybmode=True):
        """
        schaltet den KC in den Tastaturmodus
        """    
    
        print(f"enable_keyboardmodus({enable_keybmode}) wird gestartet - trans_state: {self.get_trans_state()}")
        if self.com_port is None: print("job_startkeybmode: kein com_port"); return False
        
        # während einer Datenübertragung Button disablen
        if self._worker and self._worker.is_alive():
            print("job_startkeybmode: andere Übertragung aktiv"); return
            return
        
        try:
            self.com_port.write(b"\x0D")
            self.com_port.flush()
            
            # Schnittstellen-Modus wurde umgeschaltet
            self.set_trans_state("KEY")
            
            # Initial-Verzögerung nach Konfiguration
            time.sleep(self.textconfig_init_delay / 1000.0)
            
            print("enable_keyboardmodus: Keyboard-Modus eingeschaltet")

            if enable_keybmode:
                self._keybmode_enabled = True

            return
            
        except serial.SerialException as e:
            print(f"enable_keyboardmodus: {e}")
            return
    
        finally:
            self._update_keybmode_button()
            
    
    def load_stubs(self) -> None:
        """
        Lädt 2400-Baud-Umschaltstubs und bereitet ParseResults vor,
        die oben oder unten im Speicherraum als Preloader geladen werden können
        """
        try:
        
            # Stub für den unteren Speicherbereich
            
            stub_path = self.BASE_DIR / "bin" / "Polling_2400_8N1_ESC-T_0200.bin"  # Dateiname ggf. anpassen
            data = bytearray(stub_path.read_bytes())
            if not data:
                raise ValueError("200-Stub ist leer.")

            pr = ParseResult()
            pr.format = ParseResult._FORMAT_RAW
            pr.type = ParseResult._TYPE_MC
            pr.errorstate = False
            pr.validstate = 0

            pr.transferdata = data
            pr.start = 0x200
            pr.end = pr.start + len(pr.transferdata)

            pr.callp = pr.start
            pr.callh = pr.start
            pr.callu = pr.start

            self.pr_0200stub = pr

            # Stub für den oberen Speicherbereich

            stub_path = self.BASE_DIR / "bin" / "Polling_2400_8N1_ESC-T_BF00.bin"  # Dateiname ggf. anpassen
            data = bytearray(stub_path.read_bytes())
            if not data:
                raise ValueError("BF00-Stub ist leer.")

            pr = ParseResult()
            pr.format = ParseResult._FORMAT_RAW
            pr.type = ParseResult._TYPE_MC
            pr.errorstate = False
            pr.validstate = 0

            pr.transferdata = data
            pr.start = 0xBF00
            pr.end = pr.start + len(pr.transferdata)

            pr.callp = pr.start
            pr.callh = pr.start
            pr.callu = pr.start

            self.pr_BF00stub = pr

        except Exception as e:
            self.pr_BF00stub = None
            self.pr_0200stub = None
            messagebox.showerror("Fehler", f"Ein Stub konnte nicht geladen werden:\n{e}", parent=self.root)
          
    def load_bascoder(self):
        """
        Die (mitgegebene) Bascoderdatei laden und bereithalten
        """
        print("load_bascoder")
        try:
            path = str(self.BIN_PATH) + "/BAC854-5.KCB"
            with open(path, "rb") as f:
                filedata = bytearray(f.read())
            if not filedata:
                raise ValueError("Datei ist leer.")
            # neuen Dateinamen merken
            file_name = os.path.basename(path)
            ft = KC_V24_Transfer_FileFormatTools()
            pr = ft.parseBinData(filedata)  # pr ist eine Class ParseResult

            print(pr)
            if pr.errorstate:
                #self.set_transfer_status(status="Format der Bascoder-Datei ungültig")
                return

            elif pr.validstate > 0:  # konnte geparst werden, aber es gab ein Problem mit dem Dateiformat - Sendeversuch aber möglich
                #TODO Hinweismeldung ausgeben
                pass

            if pr.callp: pr.callu = pr.callp
            else: pr.callu = pr.callh
            
            self.pr_bascoder = pr
            
            self.file_name_bascoder = file_name
            
            print(f"load_bascoder -> Bascoder-Datei \"{self.file_name_bascoder}\" geladen")
            
        except Exception as e:
            self.set_controls_send(text=self.SBTN_SEND, send_enabled=False)
            self.set_transfer_status(status="Dateiladefehler")
            messagebox.showerror("Fehler", f"Fehler beim Laden der Datei:\n{e}")
            print(f"load_bascoder{e}")

    def load_file(self):
        print("load_file")
        
        filetypes = [
            ("Alle Dateien", "*.*"),
            ("KCC-Programme", "*.kcc"),
            ("KCB-Programme", "*.kcb"),
            ("BASIC-Dateien", "*.sss"),
            ("Binärdateien", "*.bin"),
            ("Textdateien", "*.txt;*.bas"),
        ]
        path = filedialog.askopenfilename(title="Datei laden", filetypes=filetypes)
        if not path:
            return

        # neuen Dateinamen merken
        file_name = os.path.basename(path)
        
        _, ext = os.path.splitext(path)
        ext = ext.lower()

        # Dateiinhalt untersuchen und Inhalt klassifizieren -> Start, End, Einsprungadresse herausfinden
        try:
            with open(path, "rb") as f:
                filedata = bytearray(f.read())
            if not filedata:
                raise ValueError("Datei ist leer.")
            
            ft = KC_V24_Transfer_FileFormatTools()
            pr = ft.parseBinData(filedata)  # pr ist eine Class ParseResult

            print(pr)
            if pr.errorstate:
                #TODO Fehlermeldung und Rückkehr
                self.set_transfer_status(status="Dateiformat ungültig")
                return

            elif pr.validstate > 0:  # konnte geparst werden, aber es gab ein Problem mit dem Dateiformat - Sendeversuch aber möglich
                #TODO Hinweismeldung ausgeben
                pass

            if pr.callp: pr.callu = pr.callp
            else: pr.callu = pr.callh
            self.pr = pr
            
            self.file_name = file_name
            self.set_transfer_status(status="bereit zur Datenübertragung")
            self.set_controls_send(text=self.SBTN_SEND, send_enabled=True)

            print("load_file -> Datei geladen")
            
        except Exception as e:
            self.set_controls_send(text=self.SBTN_SEND, send_enabled=False)
            self.set_transfer_status(status="Dateiladefehler")
            messagebox.showerror("Fehler", f"Fehler beim Laden der Datei:\n{e}")
            print(e)

        
    # ------------------------ Senden ------------------------

    def on_send_clicked(self):
        # hält den aktuellen Status des Transfersystems
        # None:    uninitialisiert
        # "BROKE": nach Abgebrochener Binärübertragung - der KC wartet dann auf seiner Seite auf Abschluss, bis er wieder in den Tastaturmodus wechseln kann 
        # "BIN":   im ESC-U/ESC-T-Polling-Modus
        # "KEY":   Interupt-Modus (Tastatureingaben)
        
        # Wenn gerade abgearbeitet wird: Abbruch anfordern
        if self._worker and self._worker.is_alive():
            self.stop_all()
            #self.set_controls_send(text=self.SBTN_CANCEL, send_enabled=False)
            self.set_transfer_status(status="Abbruch angefordert.")
            return
            
        else: #Schalter steht auf Übertragen

            # prüfen, ob überhaupt etwas geladen wurde
            if self.pr is None:
                messagebox.showwarning(
                    "Hinweis",
                    "Keine Daten zur Übertragung."
                )
                return
            
            # "leeres" ParseResult für Jobs ohne Datenübertagung erzeugen (spart Speicher)
            pr_nodata = copy.deepcopy(self.pr)
            pr_nodata.transferdata = bytearray()
            
            pr_bascoder_nodata = copy.deepcopy(self.pr_bascoder)
            pr_bascoder_nodata.transferdata = bytearray()
            #self.last_basicodelinenumber = None
            
            pr_0200stub_nodata = copy.deepcopy(self.pr_0200stub)
            pr_0200stub_nodata.transferdata = bytearray()
            
            pr_BF00stub_nodata = copy.deepcopy(self.pr_BF00stub)
            pr_BF00stub_nodata.transferdata = bytearray()
            
            
            # testweise Jobs bauen und abarbeiten
            self.jobs = []

            #_TYPE_MC         = "Speicherabbild"  # binärer Maschinencode (Speicherabzug)
            #_TYPE_BASICMC    = "BASIC (Speicherabbild)"   # binärer BASIC-Code (auch binär!) geladen (Speicherabzug)
            #_TYPE_BASICTEXT  = "BASIC (Text)"    # Basic-Programlisting in ASCII-Form - muss als Tastatureingaben übertragen werden
            #_TYPE_BASICODE   = "BASICODE (Text)" # Basic-Programcode in ASCII-Form - muss als Tastatureingaben übertragen werden - benötigt geladenen BASCODER
            #_TYPE_TEXT       = "TEXT"            # Einfacher Text ohne bekanntes Format zur Übertragung

            #_JT_NONE           = None
            #_JT_STARTKEYBMODE  = 1   # sendet ein CR und startet so den Interrupt-Modus, wenn parent.transState nicht BROKE oder bereits KEY ist
            #_JT_SENDBIN        = 2   # sendet ESC-T (Polling-Modus EIN) und sendet jpr.transferdata wenn parent.transState nicht BROKE oder bereits BIN ist
            #_JT_RUNBIN         = 3   # sendet ESC-U (Polling-Modus EIN) und startet den Code an Adresse des jpr.callu wenn parent.transState nicht BROKE oder bereits BIN ist
            #_JT_SENDTEXT      = 4   # überträgt pr.tarnsferdata als keyboardeingaben an den BASIC-Prompt
            #_JT_STARTBASIC     = 5   # startet aus CAOS das BASIC-System (durch Keyboardeingaben)
            #_JT_STARTREBASIC   = 6   # startet aus CAOS REBASIC (durch Keyboardeingaben)
            #_JT_RUNBASIC       = 7   # startet ein BASIC-Programm per "RUN" am BASIC-Prompt

            if self.pr.type == self.pr._TYPE_TEXT:
                # Tastaturmodus einschalten
                # transferdata als Tastatureingaben übertragen

                # RESET am KC erfragen
                dlg = gui.DualOptionsDialog(self.root, title="Achtung", text="Vor der Übertragung\n\n RESET\n\nam KC drücken!", okbuttontext="Erledigt!")
                if dlg.result: self.trans_state = None
                else: return

                self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_STARTKEYBMODE, pr=pr_nodata))
                self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_SENDTEXT,      pr=self.pr))
                self.start_processing()
                
            elif self.pr.type == self.pr._TYPE_BASICTEXT:
                # Tastaturmodus einschalten
                # BASIC starten
                # transferdata als Tastatureingaben übertragen
                # wenn Autostart: BASIC-Programm starten

                dlg = gui.DualOptionsDialog(self.root, title="Achtung", text="Vor der Übertragung\n\n RESET\n\nam KC drücken!", okbuttontext="Erledigt!")
                if dlg.result: self.trans_state = None
                else: return
                
                self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_STARTKEYBMODE, pr=pr_nodata))
                self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_STARTBASIC,    pr=pr_nodata))
                self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_SENDBASICTEXT, pr=self.pr, pause=None, askstart=True))
                self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_RUNBASIC,      pr=pr_nodata))
                self.start_processing()
                

            elif self.pr.type == self.pr._TYPE_BASICODE:
                # BASCODER schon geladen?
                
                # BASCODER laden
                # Tastaturmodus einschalten
                # REBASIC
                # BASIC-Programm starten (BASCODER)
                # transferdata als Tastatureingaben übertragen
                # wenn Autostart: BASIC-Programm starten
                
                if self.last_basicodelinenumber:   # wir haben die letzte Zeilennummer des zuletzt geladenen BASICODE-Programmes, evtl. läuft der BASCODER noch
                    print("Frage-Bascoder")
                    bascoderload = messagebox.askyesno("BASICODE-Programm", "Ist der Bascoder bereits geladen?\"Ja\": Das Programm wird direkt geladen.\n\n\"Nein\": Der Bascoder wird mitübertragen", parent=self.root)
                    if not bascoderload:

                        print("Frage-Bascoder mitladen: Ja")

                        # RESET am KC erfragen
                        dlg = gui.DualOptionsDialog(self.root, title="Achtung", text="Vor der Übertragung\n\n RESET\n\nam KC drücken!", okbuttontext="Erledigt!")
                        if dlg.result: self.trans_state = None
                        else: return

                        if self.use_turboload:   # stub mit 2400 Baud-Routine vorladen und starten
                            # passenden Stub (Preloader) auswählen
                            if self.pr_bascoder.start <= self.pr_0200stub.end:
                                print(f"-- oberen Stub vorladen {self.pr_BF00stub.start:04X}")
                                pr_stub        = self.pr_BF00stub
                                pr_stub_nodata = pr_BF00stub_nodata
                            else:
                                print(f"-- unteren Stub vorladen {self.pr_0200stub.start:04X}")
                                pr_stub        = self.pr_0200stub
                                pr_stub_nodata = pr_0200stub_nodata

                            self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_SENDBIN,       pr=pr_stub))
                            self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_RUNBIN,        pr=pr_stub_nodata, set_ser_br=2400, pause=100))

                        # Bascoder vorladen
                        self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_SENDBIN,       pr=self.pr_bascoder))
                        self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_STARTKEYBMODE, pr=pr_nodata))
                        self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_STARTREBASIC,  pr=pr_nodata, pause=500))
                        self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_RUNBASIC,      pr=pr_nodata, pause=3000))
                        # Binärstart des Bascoder funktioniert nicht
                        #self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_SENDBIN,       pr=self.pr_bascoder))
                        #self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_RUNBIN,        pr=pr_bascoder_nodata, pause=5000))

                    else:
                        print("Frage-Bascoder mitladen: Nein")
                        # Bascoder - geladenes Programm zurücksetzen
                        self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_STARTKEYBMODE,  pr=pr_nodata))
                        self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_RESETBASCODER, pr=pr_nodata))

                else:   # Bascoder auf jeden Fall laden
                    # Bascoder vorladen
                    dlg = gui.DualOptionsDialog(self.root, title="Achtung", text="Vor der Übertragung\n\n RESET\n\nam KC drücken!", okbuttontext="Erledigt!")
                    if dlg.result: self.trans_state = None
                    else: return
                    
                    if self.use_turboload:   # stub mit 2400 Baud-Routine vorladen und starten
                        # passenden Stub (Preloader) auswählen
                        if self.pr_bascoder.start <= self.pr_0200stub.end:
                            print(f"-- oberen Stub vorladen {self.pr_BF00stub.start:04X}")
                            pr_stub        = self.pr_BF00stub
                            pr_stub_nodata = pr_BF00stub_nodata
                        else:
                            print(f"-- unteren Stub vorladen {self.pr_0200stub.start:04X}")
                            pr_stub        = self.pr_0200stub
                            pr_stub_nodata = pr_0200stub_nodata

                        self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_SENDBIN,       pr=pr_stub))
                        self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_RUNBIN,        pr=pr_stub_nodata, set_ser_br=2400, pause=100))
                    
                    self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_SENDBIN,       pr=self.pr_bascoder, set_ser_br=1200))
                    self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_STARTKEYBMODE, pr=pr_nodata))
                    self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_STARTREBASIC,  pr=pr_nodata, pause=500))
                    self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_RUNBASIC,      pr=pr_nodata, pause=3000))

                # Basicode-Programm laden    
                self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_SENDBASICTEXT,  pr=self.pr, pause=None, askstart=True, savelastline=True))
                self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_RUNBASIC,       pr=pr_nodata))
                self.start_processing()
                

            elif self.pr.type == self.pr._TYPE_BASICMC:
                # BIN laden
                # Tastaturmodus einschalten
                # REBASIC starten
                # wenn Autostart: BASIC-Programm starten
                # RESET am KC erfragen
                dlg = gui.DualOptionsDialog(self.root, title="Achtung", text="Vor der Übertragung\n\n RESET\n\nam KC drücken!", okbuttontext="Erledigt!")
                if dlg.result: self.trans_state = None
                else: return
                
                if self.use_turboload:   # stub mit 2400 Baud-Routine vorladen und starten
                    # passenden Stub (Preloader) auswählen
                    if self.pr.start <= self.pr_0200stub.end:
                        print(f"-- oberen Stub vorladen {self.pr_BF00stub.start:04X}")
                        pr_stub        = self.pr_BF00stub
                        pr_stub_nodata = pr_BF00stub_nodata
                    else:
                        print(f"-- unteren Stub vorladen {self.pr_0200stub.start:04X}")
                        pr_stub        = self.pr_0200stub
                        pr_stub_nodata = pr_0200stub_nodata

                    self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_SENDBIN,       pr=pr_stub))
                    self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_RUNBIN,        pr=pr_stub_nodata, set_ser_br=2400, pause=100))

                self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_SENDBIN,       pr=self.pr, set_ser_br=1200, pause=100, askstart=True))
                self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_STARTKEYBMODE, pr=pr_nodata))
                self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_STARTREBASIC,  pr=pr_nodata, pause=500))
                self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_RUNBASIC,      pr=pr_nodata))
                
                self.start_processing()
                pass
                
            elif self.pr.type == self.pr._TYPE_MC:
                # BIN laden
                # BIN starten
                # Tastaturmodus einschalten
                
                # RESET am KC erfragen
                dlg = gui.DualOptionsDialog(self.root, title="Achtung", text="Vor der Übertragung\n\n RESET\n\nam KC drücken!", okbuttontext="Erledigt!")
                if dlg.result: self.trans_state = None
                else: return

                if self.use_turboload:   # stub mit 2400 Baud-Routine vorladen und starten
                    # passenden Stub (Preloader) auswählen
                    if self.pr.start <= self.pr_0200stub.end:
                        print(f"-- oberen Stub vorladen {self.pr_BF00stub.start:04X}")
                        pr_stub        = self.pr_BF00stub
                        pr_stub_nodata = pr_BF00stub_nodata
                    else:
                        print(f"-- unteren Stub vorladen {self.pr_0200stub.start:04X}")
                        pr_stub        = self.pr_0200stub
                        pr_stub_nodata = pr_0200stub_nodata

                    self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_SENDBIN,       pr=pr_stub))
                    self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_RUNBIN,        pr=pr_stub_nodata, set_ser_br=2400, pause=100))
                
                if self.pr.callu:   # nur wenn Startadresse gegeben ist, nach Start fragen
                    self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_SENDBIN,       pr=self.pr, set_ser_br=1200, pause=100, askstart=True))
                    self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_STARTKEYBMODE, pr=pr_nodata))
                    self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_RUNBINMENU,    pr=pr_nodata))
                else:
                    self.jobs.append(KC_Job(parent=self, type=KC_Job._JT_SENDBIN,       pr=self.pr, set_ser_br=1200))
                
                self.start_processing()

    #######################################################################################################
    # Hilfsfunktionen 
    #######################################################################################################
    
    def get_restlaufzeit(self, starttime: datetime, currenttime: datetime, sent: int, total: int) -> str | None:
        if total <= 0:
            raise ValueError("T muss > 0 sein.")
        if sent < 0:
            raise ValueError("S darf nicht negativ sein.")
        if sent > total:
            sent = total
        if currenttime < starttime:
            raise ValueError("B darf nicht vor A liegen.")

        elapsed = (currenttime - starttime).total_seconds()
        if sent == 0 or elapsed <= 10:
            return None

        rate = sent / elapsed
        if rate <= 0:
            return None

        remaining_bytes = total - sent
        if remaining_bytes <= 0:
            self._rlz_hist_seconds.clear()
            return "0m00s"

        remaining_seconds = int(math.ceil(remaining_bytes / rate))

        # gleitender Mittelwert über die letzten 10 Restsekunden
        self._rlz_hist_seconds.append(remaining_seconds)
        avg_seconds = int(math.ceil(sum(self._rlz_hist_seconds) / len(self._rlz_hist_seconds)))

        m, s = divmod(avg_seconds, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h}h{m:02d}m{s:02d}s"
        return f"{m}m{s:02d}s"

    
    def open_port(self, br=1200) -> Optional[serial.Serial]:
        port_name = self.com_port_name
        try:
            ser = serial.Serial(
                port_name,
                baudrate=br,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1,
                xonxoff=True,
            )
            return ser
        except serial.SerialException as e:
            messagebox.showerror(
                "Fehler",
                f"Schnittstelle {port_name} konnte nicht geöffnet werden:\n{e}",
                parent=self.root,
            )
            self.refresh_port_menu()
            return None
            
    def _close_current_port(self) -> None:
        try:
            if self.com_port and getattr(self.com_port, "is_open", False):
                self.com_port.close()
        except Exception:
            pass
        self.com_port = None
   
    def get_system_ports(self):
        """
        Liefert eine Liste von Tupeln (portname, busy),
        z.B. [("COM3", False), ("COM4", True), ...]
        """
        ports = []
        for info in list_ports.comports():
            port = info.device  # z.B. "COM3"
            busy = not self._port_is_free(port)
            ports.append((port, busy))
        return ports

    def _port_is_free(self, port: str) -> bool:
        """
        Prüft, ob ein COM-Port geöffnet werden kann.
        """
        try:
            tmp = serial.Serial(port, baudrate=1200, timeout=0.1)
            tmp.close()
            return True
        except serial.SerialException:
            return False


    
    # -------------------------------------------------------------------------------------------------
    # COM-Port-Menü (OptionMenu)
    # -------------------------------------------------------------------------------------------------
    def _port_display_name(self, port: str, busy: bool) -> str:
        """Erzeugt die Anzeige im COM-Port-Menü."""
        return f"{port} {self.PORT_OCCUPIED}" if busy else port

    def _port_from_menu_label(self, label: str) -> str:
        """Extrahiert aus einem Menüeintrag den Portnamen (z. B. 'COM3')."""
        if not label:
            return ""
        lbl = label.strip()
        if lbl == self.PORT_CHOOSE:
            return ""
        
        if lbl.endswith(self.PORT_OCCUPIED):
            lbl = lbl[: -len(self.PORT_OCCUPIED)].rstrip()
        return lbl.strip()

    def _ensure_port_menu_bold_font(self):
        if getattr(self, "_port_menu_font_bold", None) is None and hasattr(self, "port_option"):
            try:
                base = tkfont.Font(font=self.port_option.cget("font"))
                actual = base.actual()
                actual["weight"] = "bold"
                self._port_menu_font_bold = tkfont.Font(**actual)
            except Exception:
                self._port_menu_font_bold = None
        return getattr(self, "_port_menu_font_bold", None)

    def _on_port_menu_select(self, label: str, port: str) -> None:
        """Hilfsfunktion: Menüauswahl setzen und Wechsel-Logik auslösen."""
        try:
            self.com_port_menu_name.set(label)
        except Exception:
            pass
        self.on_port_changed(port)

    def init_port_menu(self, onmenuopen=False) -> None:
        """
        Baut das Menü nach aktuell vorhandenen Ports zusammen.
        """
        if not hasattr(self, "port_option"):
            return
            
        if not onmenuopen and not self.com_port_name:
            messagebox.showwarning("Hinweis", "Bitte den zu nutzenden COM-Port wählen!", parent=self.root)
       
        ports = self.get_system_ports()

        # Eigenen, bereits geöffneten Port nicht als "(belegt)" markieren.
        current_open_port = None
        if self.com_port and getattr(self.com_port, "is_open", False):
            current_open_port = getattr(self.com_port, "port", None)

        ports_norm = []
        for port, busy in ports:
            if current_open_port and port == current_open_port:
                busy = False
            ports_norm.append((port, busy))

        port_map = {p: b for p, b in ports_norm}

        menu = self.port_option["menu"]
        menu.delete(0, "end")

        # Klicklistener zum Aktualisieren vor dem Öffnen binden
        try:
            menu.configure(postcommand=self.on_port_menu_click)
        except Exception:
            pass

        # 1) Menüeinträge aufbauen (frei / belegt)
        for port, busy in ports_norm:
            label = self._port_display_name(port, busy)
            menu.add_command(
                label=label,
                command=lambda p=port, lbl=label: self._on_port_menu_select(lbl, p),
            )

        # 2/3) Auswahl setzen (Platzhalter oder vorhandener Port)
        configured = self.com_port_name
        
        if not configured or configured not in port_map:
            
            menu.insert_command(
                0,
                label=self.PORT_CHOOSE,
                command=lambda: self._on_port_menu_select(self.PORT_CHOOSE, ""),
            )
            self.com_port_menu_name.set(self.PORT_CHOOSE)

            # Port ggf. schließen, wenn er nicht mehr verfügbar ist
            if configured and self.com_port and getattr(self.com_port, "is_open", False):
                if getattr(self.com_port, "port", None) == configured:
                    self._close_current_port()

        else:
            busy = port_map[configured]
            label = self._port_display_name(configured, busy)
            self.com_port_menu_name.set(label)

            # 4/5) bei gespeicherter Auswahl verbinden oder Warnung ausgeben
            if busy:
                if getattr(self, "_busy_warning_port", None) != configured:
                    messagebox.showwarning("Hinweis", "COM-Port prüfen", parent=self.root)
                    self._busy_warning_port = configured
                # ggf. offene Verbindung schließen
                if self.com_port and getattr(self.com_port, "is_open", False):
                    self._close_current_port()
            else:
                need_open = True
                if self.com_port and getattr(self.com_port, "is_open", False):
                    if getattr(self.com_port, "port", None) == configured:
                        need_open = False
                if need_open:
                    self._close_current_port()
                    self.com_port = self.open_port()

        # 6) GUI-Refresh
        self.refresh_port_menu()
        self._update_keybmode_button()
        
    def on_port_changed(self, newport: str) -> None:
        """
        Wird aufgerufen, wenn im Menü eine Auswahl getroffen wird.
        """
        newport = (newport or "").strip()
        current = self.com_port_name

        if newport == current:
            self.refresh_port_menu()
            self.update_gui()
            self._update_keybmode_button()
            self.set_transfer_status(None)
            return

        # aktuellen Port schließen (wenn vorhanden)
        self._close_current_port()

        # Platzhalter gewählt
        if newport == "":
            self.com_port_name = ""
            self.refresh_port_menu()
            self.update_gui()
            self._update_keybmode_button()
            self.set_transfer_status(None)
            return

        # neuen Port öffnen, wenn frei
        sys_ports = {p: b for p, b in self.get_system_ports()}
        if newport not in sys_ports:
            # Port zwischenzeitlich verschwunden
            self.com_port_menu_name.set(self.PORT_CHOOSE)
            self.refresh_port_menu()
            self.update_gui()
            self._update_keybmode_button()
            self.set_transfer_status(None)
            return

        self.com_port_name = newport

        if sys_ports.get(newport, False):
            if getattr(self, "_busy_warning_port", None) != newport:
                messagebox.showwarning("Hinweis", "COM-Port prüfen", parent=self.root)
                self._busy_warning_port = newport
            self.refresh_port_menu()
            self.update_gui()
            self._update_keybmode_button()
            self.set_transfer_status(None)
            return

        self.com_port = self.open_port()
        self.refresh_port_menu()
        self.update_gui()
        self._update_keybmode_button()
        self.set_transfer_status(None)
        
    def refresh_port_menu(self) -> None:
        """GUI-Refresh: Menüanzeige aktualisieren."""
        if not hasattr(self, "port_option"):
            return

        selected_label = self.com_port_menu_name.get().strip()
        selected_port = self._port_from_menu_label(selected_label)

        is_open = bool(self.com_port and getattr(self.com_port, "is_open", False))
        open_port = getattr(self.com_port, "port", "") if is_open else ""

        ok = bool(is_open and selected_port and open_port == selected_port)

        color = "#00993D" if ok else "red"
        bold_font = self._ensure_port_menu_bold_font()

        cfg = {"fg": color, "activeforeground": color}
        if bold_font is not None:
            cfg["font"] = bold_font

        try:
            self.port_option.config(**cfg)
        except Exception:
            pass

    def on_port_menu_click(self) -> None:
        """Aktualisiert vor dem Öffnen des Port-Menüs die Einträge."""
        self.init_port_menu(onmenuopen=True)

    #######################################################################################################
    # gespeicherte Konfiguration 
    #######################################################################################################
    def load_config(self) -> bool:
        cfg = configparser.ConfigParser()
        if not self.CONFIG_PATH.exists():
            if self.save_config():
                print("load_config() Konfigurationsdatei angelegt")
                return True
            else:
                return False

        try:
            cfg.read(self.CONFIG_PATH, encoding="utf-8")

            # [serial]
            if cfg.has_section("serial"):
            #if cfg.has_option("serial", "com_port_name"):
                self.com_port_name = cfg.get("serial", "com_port_name", fallback="").strip()
                self.use_turboload = cfg.getboolean("serial", "use_turboload", fallback=self.use_turboload)
                
            """    
            # [timeouts]
            if cfg.has_section("timeouts"):
                self.timeout_comport              = cfg.getint("timeouts", "comport", fallback=self.timeout_comport)
                self.timeout_job                  = cfg.getint("timeouts", "job",     fallback=self.timeout_job)
                
            # [textconfig]
            if cfg.has_section("textconfig"):
                self.timeout_comport              = cfg.getint("textconfig", "comport", fallback=self.timeout_comport)
                self.timeout_job                  = cfg.getint("textconfig", "job",     fallback=self.timeout_job)
                
                self.textconfig_showkonfigdialog  = cfg.getboolean("textconfig", "showkonfigdialog", fallback=self.textconfig_showkonfigdialog)
                self.textconfig_linewidth         = cfg.getint("textconfig", "linewidth",         fallback=self.textconfig_linewidth)
                self.textconfig_promptwidth       = cfg.getint("textconfig", "promptwidth",       fallback=self.textconfig_promptwidth)
                self.textconfig_init_delay        = cfg.getint("textconfig", "init_delay",        fallback=self.textconfig_init_delay)
                self.textconfig_init_clsdelay     = cfg.getint("textconfig", "init_clsdelay",     fallback=self.textconfig_init_clsdelay)
                self.textconfig_init_basic1delay  = cfg.getint("textconfig", "init_basic1delay",  fallback=self.textconfig_init_basic1delay)
                self.textconfig_init_basic2delay  = cfg.getint("textconfig", "init_basic2delay",  fallback=self.textconfig_init_basic2delay)
                self.textconfig_init_rebasicdelay = cfg.getint("textconfig", "init_rebasicdelay", fallback=self.textconfig_init_rebasicdelay)
                self.textconfig_char_delay        = cfg.getint("textconfig", "char_delay",        fallback=self.textconfig_char_delay)
                self.textconfig_linescroll_delay  = cfg.getint("textconfig", "linescroll_delay",  fallback=self.textconfig_linescroll_delay)
                self.textconfig_process_delay     = cfg.getint("textconfig", "process_delay",     fallback=self.textconfig_process_delay)
                self.textconfig_command_addition  = cfg.getint("textconfig", "command_addition",  fallback=self.textconfig_command_addition)
                self.textconfig_linethrottle      = cfg.getint("textconfig", "linethrottle",      fallback=self.textconfig_linethrottle)
                self.textconfig_lines             = cfg.getint("textconfig", "lines",             fallback=self.textconfig_lines)
                self.textconfig_basicode_delay    = cfg.getint("textconfig", "basicode_delay",    fallback=self.textconfig_basicode_delay)
                self.textconfig_dim_ref_delay     = cfg.getint("textconfig", "dim_ref_delay",     fallback=self.textconfig_dim_ref_delay)
                self.textconfig_dim_unit_delay    = cfg.getint("textconfig", "dim_unit_delay",    fallback=self.textconfig_dim_unit_delay)
                self.textconfig_var_ref_delay     = cfg.getint("textconfig", "var_ref_delay",     fallback=self.textconfig_var_ref_delay)
            """
            return True
        except Exception as e:
            print(f"load_config() Konfiguration konnte nicht geladen werden: {e}")
            return False

    def save_config(self) -> bool:
        try:
            self.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"save_config() Konfigurationsverzeichnis konnte nicht angelegt werden: {e}")
            return False
            
        cfg = configparser.ConfigParser()

        cfg["serial"] = {
            "com_port_name":     self.com_port_name.strip(),
            "use_turboload":     self.use_turboload
        }
        
        """
        cfg["timeouts"] = {
            "comport":           str(int(self.timeout_comport)),
            "job":               str(int(self.timeout_job)),
        }       
        
        cfg["textconfig"] = {
            "showkonfigdialog":  str(bool(self.textconfig_showkonfigdialog)),
            "linewidth":         str(int(self.textconfig_linewidth)),
            "promptwidth":       str(int(self.textconfig_promptwidth)),
            "init_delay":        str(int(self.textconfig_init_delay)),
            "init_clsdelay":     str(int(self.textconfig_init_clsdelay)),
            "init_basic1delay":  str(int(self.textconfig_init_basic1delay)),
            "init_basic2delay":  str(int(self.textconfig_init_basic2delay)),
            "init_rebasicdelay": str(int(self.textconfig_init_rebasicdelay)),
            "char_delay":        str(int(self.textconfig_char_delay)),
            "linescroll_delay":  str(int(self.textconfig_linescroll_delay)),
            "process_delay":     str(int(self.textconfig_process_delay)),
            "command_addition":  str(int(self.textconfig_command_addition)),
            "linethrottle":      str(int(self.textconfig_linethrottle)),
            "lines":             str(int(self.textconfig_lines)),
            "basicode_delay":    str(int(self.textconfig_basicode_delay)),
            "dim_ref_delay":     str(int(self.textconfig_dim_ref_delay)),
            "dim_unit_delay":    str(int(self.textconfig_dim_unit_delay)),
            "var_ref_delay":     str(int(self.textconfig_var_ref_delay)),
        }
        """
        try:
            with self.CONFIG_PATH.open("w", encoding="utf-8") as f:
                cfg.write(f)
        except Exception as e:
            print(f"save_config() Konfiguration konnte nicht gespeichert werden: {e}")
            return False

        return True
    
    # Ausgabe in das Statusfeld 
    def set_transfer_status(self,
                            status=None,
                            sent=None,
                            total=None,
                            currentjobnr=None,
                            totaljobcount=None,
                            restlaufzeit=None,
                            cancelable=None
                            ):
        """
        Schreibt einen Status in das Textfeld.

        mode   : z.B. "KCC", "BIN", "KCB", "TEXT"
        sent   : bereits übertragene Bytes (int oder None)
        total  : gesamte Datenlänge (int oder None)
        status : Text, z.B. "bereit zur Datenübertragung"
        """
        
        #print(sent, total, currentjobnr,totaljobcount, cancelable, "----", sep="\n")
        
        name   = ""
        format = None
        type   = None
        prtotal  = None
        if self.pr:
            format = self.pr.format
            type   = self.pr.type
            prtotal  = len(self.pr.transferdata) or None
            #if self.caos_start is not None and self.caos_end is not None:         # Daten beim Senden
            #    format = f"{format} [{self.caos_start:04X} {self.caos_end:04X}]"
            #    if self.caos_call is not None:
            #        format = f"{format} C:{self.caos_call:04X}"
            #else:
            if self.pr.start is not None and self.pr.end is not None:     # Daten nach Dateiauswahl
                format = f"{format} [{self.pr.start:04X} {self.pr.end:04X}]"

                if self.pr.callp is not None:
                    format = f"{format} P:{self.pr.callp:04X}"
                if self.pr.callh is not None:
                    format = f"{format} H:{self.pr.callh:04X}"

            if self.pr.nameh is not None or self.pr.namep is not None:
                if self.pr.namep is not None:
                    name = f"P:{str(self.pr.namep)} "
                if self.pr.nameh is not None:
                    name = f"{name}[H:{str(self.pr.nameh)}]"

        # Grundstruktur: MODE [(... Byte)] - STATUS
        parts = []

        if self.file_name:
            parts.append(f" Datei: {self.file_name}\n")
        
        if format is not None:
            parts.append(f"Format: {format}\n")
                
        if type is not None:
            parts.append(f"Inhalt: {type}\n")
        
        if name != "":
            parts.append(f"  Name: {name}\n")        

        # Länge zusammensetzen
        if sent is not None and total is not None and total > 0:
            prozent = sent * 100 / total
            rlz = f" {restlaufzeit}" if restlaufzeit is not None else ""
            parts.append(f"Senden: {int(sent)}/{int(total)} Byte [{prozent:.1f}%{rlz}]\n")
        elif prtotal is not None:
            parts.append(f" Größe: {int(prtotal)} Byte\n")
        
        # Status anhängen
        if self.com_port is None:# and (status is None or status == "" or str(status).startswith("bereit")):
            status = "COM-Port prüfen!"
            #pass
        elif status is None:
            if self.pr is not None and len(self.pr.transferdata) > 0 and not self.pr.errorstate:
                status = "bereit zur Datenübertragung"
            else:
                status = "bereit"
                
        if status:
        
            if currentjobnr is not None and totaljobcount is not None and totaljobcount > 1:
                parts.append(f"Status: [{currentjobnr}/{totaljobcount}] {status}")
            else:
                parts.append(f"Status: {status}")

        text = "".join(parts) if parts else ""

        # Textfeld als Statusfeld benutzen (Inhalt komplett ersetzen)
        self.statusfeld.config(state="normal")
        self.statusfeld.delete("1.0", "end")
        self.statusfeld.insert("1.0", text)
        self.statusfeld.config(state="disabled")
        
        # progressbar setzen
        if total is not None and sent is not None:
            self.progress["maximum"] = total
            self.progress["value"]   = sent
        else:
            self.progress["maximum"] = 1
            self.progress["value"]   = 0
    

    def on_exit(self, event=None):
        try:
            self.save_config()
        except Exception as e:
            print(f"Konfiguration konnte nicht gespeichert werden: {e}")

        # optional: Port sauber schließen
        try:
            if self.com_port:
                self.com_port.close()
        except Exception:
            pass

        self.root.destroy() 
# ------------------------------------------------------------------------------------------------------------------------

if __name__ == "__main__":
    master = tk.Tk()
    app = KC_V24_TransferApp(master)

    print(f"\n{app.APP_NAME} {app.VERSION}")

    master.mainloop()
