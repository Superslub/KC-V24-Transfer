from __future__ import annotations
from tkinter import messagebox
import serial
import time
import threading

from dataclasses import dataclass, field
from serial.tools import list_ports
from typing import Callable, List, Optional, Union, TYPE_CHECKING

from kc_v24_transfer_kcfileformattools import ParseResult
from kc_v24_transfer_basiclinedimanalyzer import BasicLineDimAnalyzer
from kc_v24_transfer_basiclinevaranalyzer import BasicLineVarAnalyzer

if TYPE_CHECKING:
    from kc_v24_transfer import KC_V24_TransferApp  # nur für Typprüfung, kein Laufzeit-Import
import re
import sys

if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)

class KC_Job:

    # Konstanten: Job-Status
    _JS_NONE       = None
    _JS_WAITING    = 1          # Wartet auf Abarbeitung
    _JS_RUNNING    = 2          # Läuft aktuell
    _JS_CANCELED   = 3          # wurde abgebrochen
    _JS_DONE       = 4          # Erledigt/Abgearbeitet
    _JS_IGNORED    = 5          # ignoriert (z.B. weil der Schnittstellenzustand "BROKE" war)
    _JS_FAILED     = 6          # gescheitert
    _JS_NOAFTERASK = 7          # Benutzer hat auf Starten-Frage mit "nein" geantwortet

    # Konstanten: Typ des Jobs / Aufgabe
    _JT_NONE           = None
    _JT_STARTKEYBMODE  = 1   # sendet ein CR und startet so den Interrupt-Modus, wenn parent.transState nicht BROKE oder bereits KEY ist
    _JT_SENDBIN        = 2   # sendet ESC-T (Polling-Modus EIN) und sendet jpr.transferdata wenn parent.transState nicht BROKE oder bereits BIN ist
    _JT_RUNBIN         = 3   # sendet ESC-U (Polling-Modus EIN) und startet den Code an Adresse des jpr.callu wenn parent.transState nicht BROKE oder bereits BIN ist
    _JT_RUNBINMENU     = 4   # startet das Programm in CAOS über den Prolognamen
    _JT_SENDTEXT       = 5   # überträgt pr.tarnsferdata als keyboardeingaben an den BASIC-Prompt
    _JT_SENDBASICTEXT  = 6   # überträgt pr.tarnsferdata als keyboardeingaben an den BASIC-Prompt
    _JT_STARTBASIC     = 7   # startet aus CAOS das BASIC-System (durch Keyboardeingaben)
    _JT_STARTREBASIC   = 8   # startet aus CAOS REBASIC (durch Keyboardeingaben)
    _JT_RUNBASIC       = 9   # startet ein BASIC-Programm per "RUN" am BASIC-Prompt
    _JT_RESETBASCODER  = 10  # TODO Setzt den Bascoder in der Bascoder-Oberfläche zurück
    
    # Properties
    parent: KC_V24_TransferApp | None       # Hauptklasse
    
    type:   int | None                  # Typ des Jobs (_JT_xxx)
    pr:     ParseResult | None          # Parseresult, welches übertragen werden soll (Nutzdatenobjekt aus dem die auszuführenden Funktionsusfufe abgeleitet werden)
    pause:  int | None                  # Zeit in ms, die nach der Abarbeitung gewartet wird
    state:  int | None                  # aktueller Status des Jobs (_JS_xxx)
    askstart: bool = False              # wenn True, wird "Programm jetzt starten" gefragt und bei Antwort "OK"
    sent:   int = 0                     # Anzahl aktuell gesendeter Bytes
    total:  int = 0                     # Anzahl der durch diesen Job zu sendenden (Nutz-)Daten
    cancelable: bool = False            # ist JOB aktuell cancelbar
    savelastline:bool = False           # wenn gesetzt, wird die letzte gelesene Basic-Zeilennummer von einem _JT_SENDBASICTEXT-Typ per set_last_basicodelinenumber global gespeichert
    
    set_ser_br = None                   # Soll-Geschwindigkeit für Schnittstelle nach Umschaltung
    
    def __init__(self, parent: KC_V24_TransferApp, type: int, pr: ParseResult, pause: int = 0, askstart=False, savelastline=False, set_ser_br=None, basiclinesoffset=0) -> None:
        self.parent           = parent
        self.type             = type
        self.askstart         = askstart
        self.pr               = pr
        self.state            = self._JS_WAITING
        self.pause            = pause
        self.savelastline     = savelastline
        self.set_ser_br       = set_ser_br
        self.basiclinesoffset = basiclinesoffset

        self.total   = len(pr.transferdata)
        #print(f"TRANSFERDATA: {len(pr.transferdata)}")
        
        self._lock   = threading.Lock()   # schützt Status-/Zählerzugriffe
        self._cancel = threading.Event()  # Abbruchsignal
        self._done   = threading.Event()  # Fertig-Signal (optional)
        
        print(f"Job [Typ: {self.type}] [{self.total} Bytes] erzeugt")

        
    def cancel(self) -> None:
        # WICHTIGER FUNKTIONSAUFRUF: setzt Abbruchsignal
        self._cancel.set()

    def snapshot(self) -> tuple[Optional[int], int, bool]:
        """Thread-sicherer Schnappschuss für Statusabfragen im Haupt-/GUI-Thread."""
        with self._lock:
            return self.state, self.sent, self.cancelable


    def _get_ser(self) -> serial.Serial:
        """Liefert das aktuelle COM-Portobjekt aus dem Parent (wird erst zur Laufzeit gebunden)."""
        ser = getattr(self.parent, "com_port", None)
        if ser is None or not getattr(ser, "is_open", False):
            raise serial.PortNotOpenError("COM-Port ist nicht geöffnet.")
        return ser


    def startjob(self) -> None:
        """
        Wird im Worker-Thread aufgerufen und läuft dort BLOCKIEREND durch.
        Währenddessen kann der GUI-/Haupt-Thread self.state/self.sent auslesen.
        """
        try:
            # Wenn die Schnittstelle defekt ist, Job ignorieren/überspringen
            if self.parent.get_trans_state() == "BROKE":
                with self._lock:
                    self.state = self._JS_IGNORED
                return True
        
            with self._lock:
                self.state = self._JS_RUNNING
            
            result = None
            print(f"Job {self.type} wird gestartet")
            # eigentliche Job-Logik nach Typ
            if self.type == self._JT_STARTKEYBMODE:
                result = self.job_startkeybmode()
                
            elif self.type == self._JT_STARTBASIC:
                result = self.job_startbasic()

            elif self.type == self._JT_STARTREBASIC:
                result = self.job_startrebasic()
                
            elif self.type == self._JT_RUNBASIC:
                result = self.job_runbasic()
            
            elif self.type == self._JT_RESETBASCODER:
                result = self.job_resetbascoder()
                
            elif self.type == self._JT_SENDBASICTEXT:
                result = self.job_sendtext(fastmode=True, endreturn=True, sll=self.savelastline, basiclinesoffset=self.basiclinesoffset)
                
            elif self.type == self._JT_SENDTEXT:
                result = self.job_sendtext(fastmode=False)
                    
            elif self.type == self._JT_SENDBIN:
                result = self.job_sendbin()
                
            elif self.type == self._JT_RUNBIN:
                result = self.job_runbin()
                
            elif self.type == self._JT_RUNBINMENU:
                result = self.job_runbinmenu()
            else:
                # Typ nicht implementiert -> als Fehler markieren
                raise NotImplementedError(f"Job-Typ {self.type} nicht implementiert")

            # Umschalten auf 9600 Baud
            if self.state == self._JS_DONE and self.set_ser_br:
                new_br = int(self.set_ser_br)
                print(f"COM -> neue Baudrate: {new_br}")
                try:
                    if self.parent.com_port is not None:
                        self.parent.com_port.flush()
                except Exception:
                    pass
                self.parent._close_current_port()
                self.parent.com_port = self.parent.open_port(new_br)
                if self.parent.com_port is None:
                    with self._lock:
                        self.state = self._JS_FAILED
                
                # debug text
                #print (f"------{new_br}----------")
                #time.sleep(0.1)
                #ser = self._get_ser()
                #ser.write(b"\x0D")
                #ser.flush()

            # Frage nach einem Start
            if self.state == self._JS_DONE and self.askstart:
                print("Frage-Starten")
                starten = messagebox.askyesno("Frage", "Programm jetzt starten?", parent=self.parent.root)
                if starten:
                    print("Frage-Starten: Ja")
                    pass
                else:
                    print("Frage-Starten: Nein")
                    with self._lock:
                        self.state = self._JS_NOAFTERASK
            
            if result:
                if (self.state == self._JS_DONE) and self.pause is not None and self.pause > 0:
                    print(f"startjob() Pause: {self.pause}")
                    time.sleep(self.pause / 1000.0)
                #with self._lock:
                #    self.state = self._JS_DONE
            else:
                with self._lock:
                    self.state = self._JS_FAILED
                    
        except Exception as e:
            print(f"startjob: {e}")
            with self._lock:
                self.state = self._JS_FAILED

        finally:
            self._done.set()  # signalisiert threading "fertig"

            
    # schaltet am KC den Keyboard-Modus ein
    # (Tastaturausgaben)
    def job_startkeybmode(self) -> bool:
        print("job_startkeybmode() wird gestartet")
        
        
        try:
            ser = self._get_ser()
            ser.write(b"\x0D")
            ser.flush()
            
            # Schnittstellen-Modus wurde umgeschaltet
            self.parent.set_trans_state("KEY")
            
            # Initial-Verzögerung nach Konfiguration
            time.sleep(self.parent.textconfig_init_delay / 1000.0)
            
            
            print("Keyboard-Modus eingeschaltet")
            with self._lock:
                self.state = self._JS_DONE
            
            return True
            
        except serial.SerialException as e:
            print(f"job_startkeybmode: {e}")
            return False

    # startet am KC aus CAOS heraus BASIC
    # der Keyboardmodus sollte dafür schon gesetzt sein
    def job_startbasic(self) -> bool:
        print("job_startbasic() wird gestartet")
        
        try:
            ser = self._get_ser()
            
            ser.write("B".encode("ascii", errors="replace"))# B in CHAOS
            ser.flush()
            time.sleep(self.parent.textconfig_char_delay / 1000.0)
            ser.write(b"\x0D") # ENTER
            ser.flush()
            time.sleep(self.parent.textconfig_init_basic1delay / 1000.0)
            ser.write(b"\x0D") # ENTER
            ser.flush()
            time.sleep(self.parent.textconfig_init_basic2delay / 1000.0)
            #ser.write("RUN".encode("ascii", errors="replace"))# B in CHAOS
            #ser.flush()
            with self._lock:
                self.state = self._JS_DONE
                
            return True
            
        except serial.SerialException as e:
            print(f"job_startbasic: {e}")
            return False

    # startet am KC aus BASIC heraus ein geladenenes BASIC-Programm mit RUN
    # (Tastaturausgaben)
    def job_runbasic(self) -> bool:
        print("job_runbasic() wird gestartet")
        
        try:
            ser = self._get_ser()
            #time.sleep(self.parent.textconfig_init_basic2delay / 1000.0)
            ser.write("RUN".encode("ascii", errors="replace"))# B in CHAOS
            ser.write(b"\x0D") # ENTER
            ser.flush()
            
            with self._lock:
                self.state = self._JS_DONE
            
            return True
            
        except serial.SerialException as e:
            print(f"job_runbasic: {e}")
            return False
    
    # startet am KC aus BASIC heraus ein geladenenes BASIC-Programm mit RUN
    # (Tastaturausgaben)
    def job_resetbascoder(self) -> bool:
        print("job_resetbascoder() wird gestartet")
        
        try:
            ser = self._get_ser()
            lln = self.parent.get_last_basicodelinenumber()
            print(f"job_resetbascoder() letzte Zeile: {lln}")

            if lln is not None:
                
                ser.write(b"\x03")  # besser ein BRK senden
                ser.flush()
                time.sleep(300 / 1000.0)
                
                ser.write(f"DELETE 1000,{lln}".encode("ascii"))
                ser.write(b"\x0D") # ENTER
                ser.flush()
                time.sleep(300 / 1000.0)
                
                ser.write("CLEAR".encode("ascii"))
                ser.write(b"\x0D") # ENTER
                ser.flush()
                time.sleep(300 / 1000.0)
                
            with self._lock:
                self.state = self._JS_DONE
            
            return True
            
        except serial.SerialException as e:
            print(f"job_resetbascoder: {e}")
            return False
    
    
            
    # startet am KC aus CAOS heraus REBASIC
    # (Tastaturausgaben)
    def job_startrebasic(self) -> bool:
        print("job_startrebasic() wird gestartet")
        
        try:
            ser = self._get_ser()
            ser.write("REBASIC".encode("ascii", errors="replace"))# B in CHAOS
            ser.write(b"\x0D") # ENTER
            ser.flush()
            time.sleep(self.parent.textconfig_init_rebasicdelay / 1000.0)
            with self._lock:
                self.state = self._JS_DONE
            
            return True
            
        except serial.SerialException as e:
            print(f"job_startrebasic: {e}")
            return False

    # sendet transferdata als Tastatureingaben
    # tarnsferdata sollte also im HC-Zeichsatz kodiert sein
    # der Keyboardmodus sollte da schon gesetzt sein
    def job_sendtext(self, fastmode: bool = False, endreturn: bool | None = None, sll: bool | None = None, basiclinesoffset: int = 0) -> bool:
        print(f"job_sendtext() fastmode: {fastmode}")
        print(f"job_sendtext() endreturn: {endreturn}")
        
        dimanalyzer = BasicLineDimAnalyzer(option_base=0)
        varanalyzer = BasicLineVarAnalyzer()
        
        def is_charbyte_printable(byte) -> bool:
            if (byte < 0x20 or byte >= 0x80): # Zulässiger Zeichenbereich nur von 0x20 bis 0x7F
                return False
            return True
        
        try:
            ser = self._get_ser()    
            cursor_line      = 0    # aktuelle Zeile des Cursors auf dem KC
            cursor_row       = self.parent.textconfig_promptwidth             # Cursor steht am Prompt 
            cursor_is_in_string = False # True, wenn der Cursor in einem Strinliteral steht
            linecommandcount = 0    # Anzahl der ZUSÄTZLICHEN Befehle in einer Zeile (:)
            totallinecount   = 0    # Anzahl der verarbeiteten Zeilen
            currentlinetext  = ""   # Text der aktuellen Zeile
            lastlinenumber   = None # die letzte BASIC-Zeilennummer des übertragenen Programmes 
            
            # Regex für ON GOTO - ON GOSUB Befehlszählung in Zeile
            rx = re.compile(
                r'(?i)(?:^|(?<=\s)|(?<=:)|(?<=THEN)|(?<=ELSE)|(?<=\d))'
                r'ON\s*[^:]*?GO(?:TO|SUB)\s*([0-9]+(?:\s*,\s*[0-9]+)*)'
            )

            if fastmode:  # im Fastmode wird der Bildschirm initial und nach dem Vollschreiben gelöscht (Verhinderung von Zeilenscrolling)
                #time.sleep(delay_ms / 1000.0)   
                ser.write(b"\x0C")
                time.sleep(self.parent.textconfig_char_delay / 1000)
                
                #ser.write(b"C")
                #time.sleep(self.parent.textconfig_char_delay / 1000)
                #ser.write(b"L")
                #time.sleep(self.parent.textconfig_char_delay / 1000)
                #ser.write(b"S")
                #time.sleep(self.parent.textconfig_char_delay / 1000)
                ser.write(b"\x0D")
                ser.flush()
                time.sleep(self.parent.textconfig_init_clsdelay / 1000)
                cursor_line = 2

            i = 0
            total = len(self.pr.transferdata)

            self.cancelable = True   # als cancelbar kennzeichnen

            while i < total and not self._cancel.is_set():
                charbyte = self.pr.transferdata[i]
                #charbyte = self.pr.transferdata[i:i+1]   # bytes/bytearray der Länge 1
                i += 1
                
                if charbyte == 0x0A:  # nur CR 0x0D soll im text gesendet werden
                    continue  # Rest überspringen, nächster Durchlauf
                
                ser.write(bytes([charbyte]))
                ser.flush()
                
                with self._lock:
                    self.sent = i
                    
                delay_ms = self.parent.textconfig_char_delay
                #print(ch)
                
                # Text der aktuellen Zeile ergänzen
                if charbyte != 0x0D: # quasi Enter
                    currentlinetext += chr(charbyte)
                
                # Zeilenende immer chr(0x0D) + chr(0x0A)
                if charbyte == 0x0D: # quasi Enter
                    
                    if self.pr.type == self.pr._TYPE_BASICODE:
                        m = re.match(r'^\s*(\d{1,5})', currentlinetext)
                        if m:
                            lastlinenumber = m.group(1)   # str

                    # Zeilenende: Verarbeitung
                    cursor_row  = self.parent.textconfig_promptwidth
                    cursor_line = cursor_line + 1
                    cursor_is_in_string  = False       # Cursor befindet sich nicht in einem Stringliteral
                    totallinecount += 1

                    # Mehrfach-Sprünge mit ON GOTO, ON GOSUB als Einzelbefehle auswerten
                    linecommandcount += sum(m.group(1).count(',') + 1 for m in rx.finditer(currentlinetext))

                    delay_ms += self.parent.textconfig_process_delay                       # Verarbeitungszeit
                    delay_ms += linecommandcount * self.parent.textconfig_command_addition # zusätzliche Berechnungszeit bei mehreren Befehlen
                    delay_ms += (totallinecount + basiclinesoffset) * self.parent.textconfig_linethrottle       # mehr Zeit bei vielen Zeilen

                    # Zusatz-delay für zeitaufwendige DIM-Operationen im BASIC-Text bestimmen
                    dim_refs, dim_units = dimanalyzer.analyze_line(currentlinetext)
                    delay_ms += dim_refs  * self.parent.textconfig_dim_ref_delay
                    delay_ms += dim_units * self.parent.textconfig_dim_unit_delay
                    
                    # Zusatz-delay für zeitaufwendige Variablen-Referenzen im BASIC-Text bestimmen
                    var_refs, vars      = varanalyzer.analyze_line(currentlinetext)
                    delay_ms += var_refs  * self.parent.textconfig_var_ref_delay
                    
                    print(f"({totallinecount}) {currentlinetext[:5]} - Befehle: {linecommandcount + 1} - Vars: {var_refs} - DIM: {dim_refs} | {dim_units}- Delay: {delay_ms:.0f}")

                    linecommandcount = 0
                    currentlinetext = ""

                    if fastmode and cursor_line >= self.parent.textconfig_lines - 1:  # x0C braucht 1 Zeile  - CLS braucht 2(!) Zeilen (inkl. Enter)
                        time.sleep(delay_ms / 1000.0)   # Prozessdauer etc abwarten
                        ser.write(b"\x0C")
                        time.sleep(self.parent.textconfig_char_delay / 1000)
                        #ser.write(b"C")
                        #time.sleep(self.parent.textconfig_char_delay / 1000)
                        #ser.write(b"L")
                        #time.sleep(self.parent.textconfig_char_delay / 1000)
                        #ser.write(b"S")
                        #time.sleep(self.parent.textconfig_char_delay / 1000)
                        ser.write(b"\x0D")
                        ser.flush()
                        time.sleep(self.parent.textconfig_init_clsdelay / 1000)
                        #print("CLS")
                        cursor_line = 2
                        cursor_row = self.parent.textconfig_promptwidth
                        delay_ms = 0

                else:
                    if is_charbyte_printable(charbyte):
                        cursor_row = cursor_row + 1
                        # Hochkomma-> Stringliterale
                        if charbyte == 0x22:
                            cursor_is_in_string = not cursor_is_in_string
                            #print ("\"")
                        # Doppelpunkt
                        if charbyte == 0x3A and not cursor_is_in_string and linecommandcount < 8:  #mehr als 8 Befehle in einer Zeile sind unwahrscheinlich
                            linecommandcount += 1
                    else:
                        #print(f"ungültiges Zeichen {charbyte:02X} in Zeile: {totallinecount}")
                        pass
                        
                    if cursor_row >= self.parent.textconfig_linewidth - self.parent.textconfig_promptwidth:
                        cursor_row = 0
                        cursor_line += 1
                        #print(f"line: {cursor_line} - {cursor_row}")
                        if not fastmode:	# es besteht die Möglichkeit, das gescrollt werden muss
                            delay_ms += self.parent.textconfig_linescroll_delay

                if delay_ms > 0:
                    time.sleep(delay_ms / 1000.0)
            
            
            if sll and lastlinenumber is not None:
                self.parent.set_last_basicodelinenumber(lastlinenumber)
            else:
                self.parent.set_last_basicodelinenumber(None)
            

            # Nach der Schleife: ggf. abschließendes CR senden (wenn nicht abgebrochen)
            if (
                endreturn
                and self.pr.transferdata[-1] != 0x0A 
                and self.pr.transferdata[-1] != 0x0D 
            ):
                print("setze endreturn")
                delay_ms = self.parent.textconfig_process_delay                          # Verarbeitungszeit
                delay_ms += linecommandcount * self.parent.textconfig_command_addition   # zusätzliche Berechnungszeit bei mehreren Befehlen
                delay_ms += totallinecount * self.parent.textconfig_linethrottle         # mehr Zeit bei vielen Zeilen
                time.sleep(delay_ms / 1000.0)
                ser.write(b"\x0D")
                #time.sleep(self.parent.textconfig_char_delay / 1000.0)
                #ser.write(b"\x0A")
                ser.flush()
                self.parent.textconfig_linescroll_delay
                delay_ms = self.parent.textconfig_process_delay                          # Verarbeitungszeit
                delay_ms += linecommandcount * self.parent.textconfig_command_addition   # zusätzliche Berechnungszeit bei mehreren Befehlen
                delay_ms += totallinecount * self.parent.textconfig_linethrottle         # mehr Zeit bei vielen Zeilen
                time.sleep(delay_ms / 1000.0)

                
            print(f"Bytes gesendet: {i} von {total} - Zeilen: {totallinecount}")
            
            self.cancelable = False   # als nicht cancelbar kennzeichnen

            if self._cancel.is_set() and i < total:
                with self._lock:
                    self.state = self._JS_CANCELED
                #raise RuntimeError("Job abgebrochen")
            else:
                with self._lock:
                    self.state = self._JS_DONE
                    
            return True
            
        except serial.SerialException as e:
            print(f"job_sendtext: {e}")
            return False
        except Exception as e:
            # fängt praktisch alle "normalen" Ausnahmen ab
            print("Fehler:", type(e).__name__, str(e))
         
    # sendet pr.transferdata an den KC
    # (Polling-Modus)
    def job_sendbin(self) -> bool:
        print("job_sendbin() wird gestartet")
        
        self.parent.set_last_basicodelinenumber(None)  # nach einem BIN-Senden ist kein Bascoder mehr geladen
        
        if self.pr.errorstate: print("job_sendbin: pr.errorstate"); return False
        if not self.pr.transferdata or len(self.pr.transferdata) == 0: print("job_sendbin: pr.transferdata"); return False
        if not self.pr.start or not self.pr.end: print("job_sendbin: pr.start - pr.end"); return False
        if self.parent.get_trans_state() == "BROKE": print("job_sendbin: transfer_state BROKE"); return False
        
        # ESC - Binärdatenübertragungsanweisung
        # 1B 54  aa aa  nn nn  <nnnn Datenbytes>
        #  ^  ^   ^  ^   ^  ^
        #  |  |   |  |   |  +-- Länge high
        #  |  |   |  |   +----- Länge low
        #  |  |   |  +--------- Adresse high
        #  |  |   +------------ Adresse low
        #  |  +---------------- "T"
        #  +------------------- ESC
        # ESC-T-Header: ESC 'T' start_low start_high len_low len_high
        header = bytearray(6)
        #header[0] = 27
        #header[1] = ord('T')
        header[0] = 0x1B # ESC
        header[1] = 0x54 # T
        header[2] = self.pr.start & 0xFF                          # Adresse low Byte
        header[3] = (self.pr.start >> 8) & 0xFF                   # Adresse high Byte
        header[4] = (len(self.pr.transferdata)) & 0xFF            # Länge low Byte
        header[5] = ((len(self.pr.transferdata)) >> 8) & 0xFF     # Länge high Byte
        
        # Header - Nutzdaten senden
        try:
            ser = self._get_ser()
            print("--- job_sendbin: Sende Header ---")
            print(" ".join(f"{b:02X}" for b in header))

            ser.write(header[0:1])
            ser.flush()
            time.sleep(0.1)

            ser.write(header[1:])
            ser.flush()
             
            # Schnittstellen-Modus wurde umgeschaltet
            self.parent.set_trans_state("BIN")
            
            with self._lock:
                self.sent = 0
                
            # Daten blockweise senden
            block_size = 64
            total = len(self.pr.transferdata)
            offset = 0
            print("--- job_sendbin: Sende Daten ---")

            self.cancelable = True   # als cancelbar kennzeichnen

            while offset < total and not self._cancel.is_set():  # _cancel aus threading
                chunk = self.pr.transferdata[offset:offset + block_size]
                try:
                    ser.write(chunk)
                    ser.flush()
                except serial.SerialException as e:
                    print(f"job_sendbin: {e}")
                    #self.binary_error = str(e)
                    break

                offset += len(chunk)
                with self._lock:
                    self.sent = offset
                #print(f"Bytes gesendet: {offset} von {total}", flush=True)
            
            #print(self.hexdump(self.pr.transferdata, 8))
            print(f"Laenge: {len(self.pr.transferdata):04X} - {len(self.pr.transferdata)}")
            print(f"Bytes gesendet (gesamt): {offset}")
            
            self.cancelable = False   # als nicht cancelbar kennzeichnen

            if self._cancel.is_set() and offset < total:
                self.parent.set_trans_state("BROKE")
                with self._lock:
                    self.state = self._JS_CANCELED

            else:
                with self._lock:
                    self.state = self._JS_DONE
                    
            return True
            
        except serial.SerialException as e:
            print(f"job_sendbin: {e}")
            return False


    # startet per CALL auf pr.callu ein Programm auf dem KC
    # (Polling-Modus)
    def job_runbin(self) -> bool:
        print("job_runbin() wird gestartet")
        
        if self.pr.errorstate: print("job_runbin: pr.errorstate"); return False
        if not self.pr.callu: print("job_runbin: pr.callu"); return False
        if self.parent.get_trans_state() == "BROKE": print("job_runbin: transfer_state BROKE"); return False
        
        # ESC-Autostart-Anweisungen
        # 1B 55  ss ss
        #  ^  ^   ^  ^
        #  |  |   |  +-- Startadresse high
        #  |  |   +----- Startadresse low
        #  |  +--------- "U"
        #  +------------ ESC
        # ESC-U-Header: ESC 'U' call_low call_high
        header = bytearray(4)
        #header[0] = 27
        #header[1] = ord('U')
        header[0] = 0x1B # ESC
        header[1] = 0x55 # U
        header[2] = self.pr.callu & 0xFF                         # Adresse low Byte
        header[3] = (self.pr.callu >> 8) & 0xFF                  # Adresse high Byte
        
        # Header - Nutzdaten senden
        try:
            ser = self._get_ser()
            print("Sende Header")
            print(" ".join(f"{b:02X}" for b in header))

            ser.write(header[0:1])
            ser.flush()
            time.sleep(0.1)

            ser.write(header[1:])
            ser.flush()
            
            # Schnittstellen-Modus wurde umgeschaltet
            self.parent.set_trans_state("BIN")
            with self._lock:
                self.state = self._JS_DONE       
            return True
            
        except serial.SerialException as e:
            print(f"job_runbin: {e}")
            return False
            
            
    # startet ein CAOS-Programm über die Eingabe des Programmnamens im CAOS-Menu
    # (Tastaturausgaben)
    def job_runbinmenu(self) -> bool:
        print("job_runbasic() wird gestartet")
        
        try:
            ser = self._get_ser()
            if self.pr.namep:
                #time.sleep(self.parent.textconfig_init_basic2delay / 1000.0)
                ser.write(self.pr.namep.encode("ascii", errors="replace"))# B in CHAOS
                ser.write(b"\x0D") # ENTER
                ser.flush()

                with self._lock:
                    self.state = self._JS_DONE
            else:
                print("job_runbasic: keinen Prolognamen in pr gefunden")
                return False
            
            return True
            
        except serial.SerialException as e:
            print(f"job_runbasic: {e}")
            return False
    
    def hexdump(self, data: Union[bytes, bytearray], width: int = 16, with_offset: bool = True) -> str:
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("data muss bytes oder bytearray sein")
        if width <= 0:
            raise ValueError("width muss > 0 sein")

        lines = []
        for off in range(0, len(data), width):
            chunk = data[off:off + width]
            hexpart = " ".join(f"{b:02X}" for b in chunk)
            lines.append(f"{off:04X}: {hexpart}" if with_offset else hexpart)
        return "\n".join(lines)