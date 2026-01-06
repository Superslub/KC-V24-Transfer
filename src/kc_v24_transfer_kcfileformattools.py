#from __future__ import annotations
from typing import Optional
#from dataclasses import dataclass
from kc_v24_transfer_basicdetokenizer import KC_V24_Transfer_BASICdetokenizer
import re

#@dataclass
class ParseResult:
    # interne Format-IDs - Format der Datei
    _FORMAT_TEXT = "Textdatei"          # Textdatei
    _FORMAT_KCC  = "KCC"                # klassisches KCC-MC-Programm  (Speicherabzug)
    _FORMAT_KCB  = "KCB"                # BASIC-Programm im KCC/KCB-Container (Speicherabzug)
    _FORMAT_SSSD = "SSS (Disk)"         # SSS mit BASIC-Datei (FSAVE) - BASIC-Arbeitszellen, die detokenisiert werden müssen 
    _FORMAT_SSSK = "SSS (Tape)"         # SSS mit BASIC-Datei (CSAVE) - BASIC-Arbeitszellen, die detokenisiert werden müssen
    _FORMAT_RAW  = "unbekannt"          # unbekanntes Format (alle Daten der Datei werden übertragen)
    
    
    # interne Typ-IDs - Format der Daten in der Datei
    _TYPE_MC         = "Speicherabbild"           # binärer Maschinencode (Speicherabzug)
    _TYPE_BASICMC    = "BASIC (Speicherabbild)"   # binärer BASIC-Code (auch binär!) geladen (Speicherabzug)
    _TYPE_BASICTEXT  = "BASIC (Zeilen)"           # Basic-Programmlisting in ASCII-Form - muss als Tastatureingaben übertragen werden
    _TYPE_BASICODE   = "BASICODE (Zeilen)"        # Basic-Programcode in ASCII-Form - muss als Tastatureingaben übertragen werden - benötigt geladenen BASCODER
    _TYPE_TEXT       = "TEXT"                     # Einfacher Text ohne bekanntes Format zur Übertragung
    
    start:        Optional[int] = None  # None oder (int) Start-Adresse
    end:          Optional[int] = None  # None oder (int) End-Adresse (+1)
    format:       Optional[str] = None  # Das erkannte Dateiformat - None oder (int) Fileformat (KCC, KCB, SSS)
    type:         Optional[str] = None  # Der erkannte Programmtyp - None oder Programmtyp ("BASIC", "CM")
    callh:        Optional[int] = None  # None oder (int) Einsprungadresse aus der Datei
    callp:        Optional[int] = None  # None oder (int) Einsprungadresse aus CAOS-Prolog
    callu:        Optional[int] = None  # None oder (int) - zu nutzende Einsprungadresse (Benutzerwahl)
    nameh:        Optional[str] = None  # None oder ProgrammName aus dem Dateiheader
    namep:        Optional[str] = None  # None oder ProgrammName aus CAOS-Prolog (= CAOS-Menüeintrag)
    transferdata: bytearray = bytearray()  # Bytearray mit den zu sendenden Bytes
    ramclass:     Optional[str] = None  # None oder "16k", "32k" oder "48k"
    validstate:   int = 0               # 0, wenn Format valide ist -> alles größer null sind Hinweise auf Fehler
    errorstate:   bool = True           # False, wenn geparst werden konnte, True im Fehlerfall
    runlinebasic: Optional[str] = None  # Die Zeilennummer, mit der ein Basic-Progtamm gestartet werden soll

    def _fmt_addr(self, value: Optional[int]) -> str:
        """Adresswerte konsistent im HEX-Format darstellen."""
        if value is None:
            return "None"
        return f"0x{value:04X}"

    def __str__(self) -> str:
        """String-Repräsentation, damit print(result) ebenfalls HEX-Adressen zeigt."""
        return (
            "ParseResult(\n"
            f"       start={self._fmt_addr(self.start)}\n"
            f"         end={self._fmt_addr(self.end)}\n"
            f"      format={self.format}\n"
            f"       callf={self._fmt_addr(self.callh)}\n"
            f"       callp={self._fmt_addr(self.callp)}\n"
            f"       callu={self._fmt_addr(self.callu)}\n"
            
            f"       nameh={self.nameh!r}\n"
            f"       namep={self.namep!r}\n"
            f"        type={self.type!r}\n"
            f"    ramclass={self.ramclass!r}\n"
            f"  validstate={self.validstate}\n"
            f"  errorstate={self.errorstate})\n"
            f"runlinebasic={self.runlinebasic})"
        )
        
class KC_V24_Transfer_FileFormatTools:

    # KC85/4 BASIC-Systembereich 0x0300..0x03D6 (215 Bytes)
    _KCB_SYS_MEM0300 = bytes.fromhex("""
        C3 89 C0 C3 67 C9 00 00 01 00 00 D6 00 6F 7C DE
        00 67 78 DE 00 47 3E 00 C9 00 00 00 35 4A CA 99
        39 1C 76 98 22 95 B3 98 0A DD 47 98 53 D1 99 99
        0A 1A 9F 98 65 BC CD 98 D6 77 3E 98 52 C7 4F 80
        0B FF 1B 00 0A 00 0A 00 00 00 C3 AE C5 00 00 00
        00 00 00 00 00 00 FF BE FF FF 00 00 C9 00 00 01
        04 00 20 00 20 8F C0 00 00 00 00 00 00 00 00 00
        00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
        00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
        00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
        00 00 00 00 00 00 00 00 00 00 00 00 01 00 01 00
        FF BF B4 03 03 00 1D C3 00 00 00 00 00 00 00 00
        03 00 1D C3 FF BF 00 00 00 00 00 00 00 00 00 00
        04 00 00 00 00 00 00
    """)

    # KC85/4 BASIC-Systembereich 0x03DD..0x0400 (36 Bytes)
    _KCB_SYS_MEM03DD = bytes.fromhex("""
        00 04 00 00 00 00 00 00 B4 03 00 30 F4 20 34 37
        38 35 34 00 30 00 00 00 00 00 00 00 00 00 00 AF
        00 00 00 00
    """)

    _KCB_SYS_START_ADDR   = 0x0300
    _KCB_BASIC_START_ADDR = 0x0401
    # Laut KC85/4-Dokumentation explizit "nicht benutzt"
    _KC_UNUSED_CODES = {0x04, 0x05, 0x06, 0x0E, 0x15, 0x17}

    # Steuerzeichen, die wir trotzdem zulassen:
    # 0x0D: CR (ENTER), 0x0A: LF (Zeilenumbruch)
    _ALLOWED_CONTROL_CODES = {0x0A, 0x0D}

    _BASICODE_START_RE = re.compile(r"^\s*1000(?!\d).*?(?<![A-Za-z])GOTO\s*20(?!\d)", re.IGNORECASE)
    _BASIC_LINE_RE = re.compile(r"^\s*(\d{1,5})(?!\d)")
    _BASIC_KW_RE = re.compile(
        r"(?<![A-Za-z])(?:PRINT|INPUT|IF|THEN|ELSE|FOR|NEXT|GOTO|GOSUB|RETURN|REM|DIM|DATA|READ|RESTORE|END|STOP|CLS|CLEAR|CALL|USR|POKE|PEEK|RANDOMIZE|ON|DEF|LET|RUN|LIST|NEW)(?![A-Za-z])",
        re.IGNORECASE,
    )
    
    # ---------------------------------------------------------
    # Textprüfung - auch für "aufgefüllte" Dateien
    # gibt Nutztext oder None zurück
    # ---------------------------------------------------------
    def _is_valid_textbyte(self, b: int) -> bool:
        """
        Prüft, ob ein Byte als Textzeichen für den KC85/4 zulässig ist
        (inklusive erlaubter Steuerzeichen CR/LF). Entspricht der bisherigen
        Prüflogik in checktext().
        """
        #b = bytes(b)
        #b = bytes([b & 0xFF]) # b ist jetzt ein byte
        
        b = int(b) & 0xFF  # 0..255
        # explizit "nicht benutzte" Codes verbieten
        if b in self._KC_UNUSED_CODES:
            return False

        if b < 0x20:
            # Unterhalb 0x20 nur explizit erlaubte Steuerzeichen zulassen
            return b in self._ALLOWED_CONTROL_CODES

        if 0x7F <= b < 0xA0:
            # 0x7F (DEL) und 0x80–0x9F nicht als Textzeichen zulassen
            return False

        if b < 0x20 or b > 0x7F: # Zulässiger Zeichenbereich nur von 0x20 bis 0x7F
            return False

        return True

    # viele in eine SSS-Datei abgespeicherte BASIC-Programme haben als erste Zeile ähnliche Aufrufe wie 
    # 0 CLOSE I#1 : RUN10
    # die funktion prüft die erste Basic-Zeile auf solche Muster und gibt die von RUN aufgerufene Zeilennummer zurück
    # gibt None zurück, wenn kein Muster erkannt wurde
    def get_runline_from_basic(self, data: bytearray) -> str:
        """
        Viele in eine SSS-Datei abgespeicherte BASIC-Programme haben als erste Zeile Aufrufe wie:
            0 CLOSE I#1 : RUN10
            10CLOSEI#1:RUN50

        Die Funktion prüft die erste BASIC-Zeile auf solche Muster und gibt die von RUN
        aufgerufene Zeilennummer zurück (als String). Gibt None zurück, wenn kein Muster passt.
        """
        if data is None or len(data) == 0:
            return None

        if isinstance(data, bytes):
            data = bytearray(data)
        if not isinstance(data, bytearray):
            raise TypeError("data muss vom Typ bytearray sein")

        text = bytes(data).decode("latin1", errors="ignore")
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # 1) erste nichtleere Zeile ermitteln
        first_line = None
        for ln in text.split("\n"):
            s = ln.strip()
            if s:
                first_line = s
                print(f"BASIC - erste Zeile: {first_line}")
                break
        if not first_line:
            return None

        # 2) muss mit Zeilennummer beginnen
        m_line = self._BASIC_LINE_RE.match(first_line)
        if not m_line:
            return None

        rest = first_line[m_line.end():]  # nach der Zeilennummer

        # 3) String-Literale maskieren (damit RUN/CLOSE in Strings ignoriert wird)
        def _mask_string_literals(s: str) -> str:
            out = []
            i = 0
            in_str = False
            while i < len(s):
                ch = s[i]
                if ch == '"':
                    # "" innerhalb eines Strings
                    if in_str and i + 1 < len(s) and s[i + 1] == '"':
                        out.append(" ")
                        out.append(" ")
                        i += 2
                        continue
                    in_str = not in_str
                    out.append(" ")
                    i += 1
                    continue
                out.append(" " if in_str else ch)
                i += 1
            return "".join(out)

        masked = _mask_string_literals(rest)

        # 4) Kommentare abschneiden: '!' oder REM (auch kompakt, z.B. ':REM...')
        excl = masked.find("!")
        if excl != -1:
            masked = masked[:excl]

        m_rem = re.search(r"(?i)(^|[^A-Z0-9$])REM", masked)
        if m_rem:
            cut = m_rem.start(0) + (0 if m_rem.group(1) == "" else 1)
            masked = masked[:cut]

        upper = masked.upper()

        # 5) RUN<zeile> finden (RUN10, RUN 10)
        m_run = re.search(r"(?<![A-Z0-9$])RUN\s*(\d{1,5})(?!\d)", upper)
        if not m_run:
            return None

        run_target = m_run.group(1)

        # 6) optionaler Musteranker: CLOSE I#1 (auch CLOSEI#1, CLOSE I # 1, CLOSE #1)
        before_run = upper[:m_run.start()]
        has_close_i1 = re.search(
            r"(?<![A-Z0-9$])CLOSE\s*(?:I\s*)?#\s*1(?![A-Z0-9$])",
            before_run
        ) is not None

        # primär: genau das typische SSS-Muster
        if has_close_i1:
            return str(int(run_target))  # normalisieren (z.B. "0010" -> "10")

        # sekundär (häufige Variante): erste Zeile enthält schlicht RUN<zeile>
        # (hier bewusst konservativ: RUN muss „als Befehl“ vorkommen, nicht als Teil eines Namens)
        return str(int(run_target))


    # klassifiziert den im Text enthaltenen Code
    # gibt einen ParseResulte.type-String zurück (_TYPE_BASICTEXT, _TYPE_BASICODE oder _TYPE_TEXT)
    def classify_basic_text(self, data: bytearray) -> str:
        if data is None:
            return ParseResult._TYPE_TEXT
        if isinstance(data, bytes):  # Robustheit, falls Alt-Code noch bytes übergibt
            data = bytearray(data)
        if not isinstance(data, bytearray):
            raise TypeError("data muss vom Typ bytearray sein")
        if len(data) == 0:
            return ParseResult._TYPE_TEXT

        text = bytes(data).decode("ascii", errors="ignore")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        
        lines = text.split("\n")
        # 0) Frühtest: Ein BASIC-Listing beginnt (nach Leerzeilen) mit einer Zeilennummer.
        for ln in lines:
            s = ln.strip()
            if not s:
                continue
            if not self._BASIC_LINE_RE.match(s):
                return ParseResult._TYPE_TEXT
            break
            
        # 1) BASICODE: Zeile 1000 ... GOTO 20 (auch ohne Leerzeichen) früh suchen
        seen = 0
        for ln in lines:
            s = ln.strip()
            if not s:
                continue
            if self._BASICODE_START_RE.search(s):
                return ParseResult._TYPE_BASICODE
            seen += 1
            if seen >= 200:
                break

        # 3) BASIC-Listing-Heuristik (auch kompakt)
        nonempty = 0
        numbered = 0
        keyworded = 0
        syntax_hits = 0
        line_nums: list[int] = []

        for ln in lines:
            s = ln.strip()
            if not s:
                continue
            nonempty += 1

            m = self._BASIC_LINE_RE.match(s)
            if not m:
                continue

            numbered += 1
            try:
                line_nums.append(int(m.group(1)))
            except ValueError:
                pass

            rest = s[m.end():]  # Rest nach der Zeilennummer (ggf. ohne Leerzeichen)
            if self._BASIC_KW_RE.search(rest):
                keyworded += 1
            if any(ch in rest for ch in ("=", ":", '"', "(", ")", "<", ">", ";", ",")):
                syntax_hits += 1

        if nonempty == 0:
            return ParseResult._TYPE_TEXT

        ratio = numbered / nonempty

        mono_ratio = 0.0
        if len(line_nums) > 1:
            mono = sum(1 for a, b in zip(line_nums, line_nums[1:]) if b >= a)
            mono_ratio = mono / (len(line_nums) - 1)

        if numbered >= 2 and ratio >= 0.5 and (keyworded >= 1 or syntax_hits >= 2):
            return ParseResult._TYPE_BASICTEXT
        if numbered >= 5 and ratio >= 0.6 and (mono_ratio >= 0.7 or keyworded >= 2):
            return ParseResult._TYPE_BASICTEXT
        if numbered >= 20 and ratio >= 0.8:
            return ParseResult._TYPE_BASICTEXT

        return ParseResult._TYPE_TEXT


    # ---------------------------------------------------------
    # Hauptklassifikation
    # ---------------------------------------------------------
    def parseBinData(self, filedata: bytearray) -> ParseResult:
        """
        Klassifiziert eine übergebene Binärdatei.

        Soll u. a. zurückgeben:
            start         - None oder (int) Start-Adresse
            end           - None oder (int) End-Adresse (+1)
            format        - None oder (int) Fileformat (KCC, KCB, SSS)
            callf         - None oder (int) Einsprungadresse aus der Datei
            callp         - None oder (int) Einsprungadresse aus CAOS-Prolog
            namef         - None oder Name aus dem Dateiheader
            namep         - None oder Name aus CAOS-Prolog (= CAOS-Menüeintrag)
            type          - None oder Programmtyp ("BASIC", "CM")
            ramclass       - None oder (int) Größe des benötigten Speichers
            validstate    - 0, wenn Format valide ist
            errorstate    - False, wenn geparst werden konnte, True im Fehlerfall
        """
        if not isinstance(filedata, bytearray):
            raise TypeError("filedata muss vom Typ bytearray sein")

        result = self.parseformatTEXT(filedata)        # Erst auf simples Latin-1-Text-Format prüfen
        if not result.errorstate:
            return result
        
        result = self.parseformatSSSBand(filedata)     # Erst auf SSS-Bandformate prüfen
        if not result.errorstate:
            return result
        
        result = self.parseformatSSSDatei(filedata)    # Dann auf SSS-Dateiformate prüfen
        if not result.errorstate:                      
            return result
        
        result = self.parseformatKCC(filedata)         # Dann auf KCC/KCB_Format prüfen
        if not result.errorstate:
            return result
        
        result = self.parseRAWBytes(filedata)          # unbekanntes Binärformat unterstellen
        
        return result
        
        
    _KCB_SYS_START_ADDR   = 0x0300
    _KCB_BASIC_START_ADDR = 0x0401

    def build_basicmc_from_basic_program(self, prog_bytes, *,
                                       nameh: Optional[str] = None,
                                       fmt: str = ParseResult._FORMAT_SSSD,
                                       runlinebasic: Optional[str] = None) -> ParseResult:
        result = ParseResult()

        if isinstance(prog_bytes, bytearray):
            prog_bytes = bytes(prog_bytes)
        if not isinstance(prog_bytes, (bytes, bytearray)):
            raise TypeError("prog_bytes muss bytes/bytearray sein")

        if len(prog_bytes) < 3 or prog_bytes[-3:] != b"\x00\x00\x00":
            result.validstate = 311
            result.errorstate = True
            return result

        prog_len = len(prog_bytes)
        end_addr = self._KCB_BASIC_START_ADDR + prog_len  # 0x0401 + len

        transferdata = bytearray()
        transferdata += self._KCB_SYS_MEM0300

        # 3× endAddr (Little Endian)
        for _ in range(3):
            transferdata.append(end_addr & 0xFF)
            transferdata.append((end_addr >> 8) & 0xFF)

        transferdata += self._KCB_SYS_MEM03DD
        transferdata += prog_bytes

        result.start        = self._KCB_SYS_START_ADDR
        result.end          = end_addr  # Ladebereich endet bei endAddr-1
        result.format       = fmt
        result.type         = ParseResult._TYPE_BASICMC
        result.nameh        = nameh
        result.transferdata = transferdata
        result.ramclass     = self._calc_ramclass(result.end)
        result.validstate   = 0
        result.errorstate   = False
        result.runlinebasic = runlinebasic
        return result

    # gibt ein parseResult mit gesetzten errorstate und type zurück,
    # der errorstate ist True, wenn die übergebenen filedata ungültige Zeichen enthalten,
    # ansonsten wird der type und die enthaltenen textdaten in transferdata des ParseResult zurückgegeben (der Text (als bytes) ohne evtl. Füllzeichen am Ende)
    def parseformatTEXT(self, filedata: bytearray) -> ParseResult:
        """
        Prüft, ob filedata ausschließlich Zeichen enthält, die auf dem KC85/4
        als Text darstellbar sind (inklusive Sonderzeichen) sowie CR/LF
        für Zeilenumbrüche. Alle anderen Steuerzeichen werden abgelehnt.

        Zusätzlich wird am Dateiende eine mögliche Auffüllung mit einem
        Füllzeichen bis zum Ende eines 128-Byte-Blocks (maximal 127 identische
        Bytes) erkannt und ignoriert, sofern dieses Füllzeichen selbst kein
        zulässiges Textzeichen wäre.

        Rückgabe:
            ParseResult mit gesetzten errorstate, type und transferdata
        """

        result = ParseResult()
        
        if not isinstance(filedata, bytearray):
            raise TypeError("parseformatTEXT() filedata muss vom Typ bytearray sein")


        data = bytes(KC_V24_Transfer_BASICdetokenizer._LATIN_2_KC.get(b, b) for b in filedata)   # angenommenen LATIN-1-Code in KC-Codes umwandeln
        #data = bytes(filedata)
        length = len(data)

        # Standardfall: nichts abschneiden
        cut_index = length

        # Auffüllung nur berücksichtigen, wenn die Datei genau auf 128-Byte-Blöcke endet
        
        if length >= 128 and (length % 128) == 0:
            fill_byte = data[-1]

            # Nur dann als Füllzeichen betrachten, wenn dieses Byte selbst
            # KEIN zulässiges Textzeichen wäre (typisch: 0x00, 0x1A o. ä.).
            if not self._is_valid_textbyte(fill_byte):
                run_len = 0
                i = length - 1

                # Bis zu 127 identische Bytes am Ende als Auffüllung akzeptieren
                while i >= 0 and data[i] == fill_byte and run_len < 127:
                    run_len += 1
                    i -= 1

                if run_len > 0:
                    cut_index = length - run_len
            if cut_index:
                print(f"parseformatTEXT() Auffuellung gefunden: {cut_index}")
            
        # Relevanten Textbereich ohne Füllzeichen
        text_bytes = data[:cut_index]

        # Jetzt den bereinigten Bereich auf zulässige Zeichen prüfen
        for b in text_bytes:
            if not self._is_valid_textbyte(b):
                print(f"parseformatTEXT() not _is_valid_textchar 0x{b:02X}")
                return result

        # Den enthaltenen Text noch klassifizieren
        result.format = result._FORMAT_TEXT
        result.type = self.classify_basic_text(bytearray(text_bytes))  # gibt einen TYP-String aus ParseResult zurück
        result.transferdata = bytearray(text_bytes)
        result.errorstate = False
        return result

    # ---------------------------------------------------------
    # KCC / KCB
    # ---------------------------------------------------------
    def parseformatKCC(self, filedata: bytearray) -> ParseResult:
        """
        Prüft, ob die übergebenen Daten ein gültiges KCC/KCB-Format haben.
        Liefert bei Erfolg einen gefüllten ParseResult mit errorstate == False.
        """

        result = ParseResult()

        if not isinstance(filedata, bytearray):
            raise TypeError("parseformatTEXT() filedata muss vom Typ bytearray sein")

        data = bytes(filedata)
        size = len(data)

        # Heuristik: SSS-Diskformat (Längenwort + Daten) zuerst ausschließen,
        # damit SSS-Dateien nicht fälschlich als KCC erkannt werden.
        if size >= 2:
            data_len = data[0] + (data[1] << 8)
            if 0 < data_len and data_len + 2 == size:
                # sehr wahrscheinlich SSS, nicht KCC
                result.validstate = 200
                result.errorstate = True
                return result

        # Minimaler KCC-Headerumfang
        if size < 128:
            result.validstate = 201  # Datei enthält keinen vollständigen KCC-Header
            result.errorstate = True
            return result

        # BASIC-Kennungen SSS/TAP/UUU/WWW wie in check_KCC.cpp ausschließen
        if self._check_sss(data):
            result.validstate = 202  # BASIC-Kennung SSS
            result.errorstate = True
            return result

        if self._check_tap(data):
            result.validstate = 203  # TAP-Datei mit SSS-Kennung
            result.errorstate = True
            return result

        if self._check_uuu(data):
            result.validstate = 204  # BASIC-Kennung UUU
            result.errorstate = True
            return result

        if self._check_www(data):
            result.validstate = 205  # BASIC-Kennung WWW
            result.errorstate = True
            return result

        # Header dekodieren (entspricht read_header in check_KCC.cpp)
        name_chars = []
        for b in data[0:11]:
            if 0x20 <= b <= 0x7E:
                name_chars.append(chr(b))
            else:
                name_chars.append("." if b > 0 else " ")
        name = "".join(name_chars)

        addrargs  = data[16]
        startaddr = data[17] + (data[18] << 8)
        endaddr   = data[19] + (data[20] << 8)
        calladdr  = data[21] + (data[22] << 8)
        prog_size = (endaddr - startaddr) & 0xFFFF

        # Programmdaten abspalten
        mem_data = data[128:]
        if not mem_data:
            result.validstate = 206  # keine Programmdaten
            result.errorstate = True
            return result

        # Anzahl Adressargumente prüfen
        if addrargs < 2 or addrargs > 0x0A:
            result.validstate = 207  # Adressargumente ungültig
            result.errorstate = True
            return result

        # Prüfen, ob im Header angegebene Länge zur Dateigröße passt
        if prog_size <= 0 or prog_size + 128 > size:
            result.validstate = 208  # Dateilänge kleiner als im Header angegeben
            result.errorstate = True
            return result

        # Grunddaten übernehmen
        result.start   = startaddr
        result.end     = endaddr
        result.callh   = calladdr if addrargs >= 3 else None
        result.nameh   = name
        # RAM-Bedarf grob als höchste genutzte Adresse
        result.ramclass = self._calc_ramclass(endaddr)

        # BASIC-Programm im KCC-Container erkennen (KCB)
        is_kcb = self._check_basic(data)
        if is_kcb:
            result.type   = result._TYPE_BASICMC
            result.format = result._FORMAT_KCB
        else:
            result.type   = result._TYPE_MC
            result.format = result._FORMAT_KCC

        # CAOS-Menüeinträge (Prolog) suchen
        entries = self._find_menu_entries(startaddr, mem_data)
        if entries:
            first_name, first_addr = entries[0]
            result.namep = first_name
            result.callp = first_addr

        result.transferdata = bytearray(mem_data[:prog_size])
        # Format ist konsistent
        result.validstate = 0
        result.errorstate = False
        return result


    def parseformatSSSDatei(self, filedata: bytearray) -> ParseResult:
        """
        Prüft auf folgendes SSS-BASIC-Muster:
        
        Disk/USB-Format:
             [0..1]  = Programmlänge (Little Endian)
             [2..n]  = Programmdaten (BASIC-Speicherabbild) - die letzten drei Programmdaten-Bytes sind 0x00 0x00 0x00
             danach   : 0–127 Auffüllbytes (beliebige Werte), um auf 128-Byte-Blöcke
                       aufzufüllen 

        """
        result = ParseResult()
        if not isinstance(filedata, bytearray):
            raise TypeError("parseformatSSSDatei() filedata muss vom Typ bytearray sein")

        data = bytes(filedata)
        size = len(data)

        # Es müssen mindestens 2 Bytes Längenwort + 3 Bytes 0x00 vorhanden sein
        if size < 2 + 3:
            result.validstate = 301 
            result.errorstate = True
            return result

        # Längenwort (Little Endian) der Programmdaten
        prog_len = data[0] | (data[1] << 8)

        # Programmdaten müssen mindestens 3 Bytes lang sein (wegen der drei 0x00)
        if prog_len < 3:
            result.validstate = 302 
            result.errorstate = True
            return result

        code_start = 2
        code_end   = code_start + prog_len

        # Datei muss mindestens prog_len Programmdatenbytes enthalten
        if code_end > size:
            result.validstate = 303 
            result.errorstate = True
            return result

        # Auffüllung am Dateiende: maximal 127 Bytes
        padding_len = size - code_end
        if padding_len > 127:
            result.validstate = 304 
            result.errorstate = True
            return result

        prog_bytes = data[code_start:code_end]

        # Programmcode muss mit drei 0x00-Bytes enden
        if prog_bytes[-3:] != b"\x00\x00\x00":
            result.validstate = 305 
            result.errorstate = True
            return result

        # Muster ist erfüllt -> Detokenisieren
        detok = KC_V24_Transfer_BASICdetokenizer()
        listing = detok.detokenize_hc_basic(program=prog_bytes, compact=True)
        
        #print(listing)
        for msg in detok.process_messages: print(" -", msg)
        
        if listing is None:
            result.validstate = 310   # Detokenisierung fehlgeschlagen 
            result.errorstate = True
            return result
        
        # Prüfen, was in der Datei enthalten ist -> BASIC oder BASICODE
        tmp_transferdata = bytearray(listing.encode("latin1"))
        tmp_type         = self.classify_basic_text(tmp_transferdata)    # gibt einen TYP-String aus ParseResult zurück
        # Manche BASIC-Programme beginnen mit unbrauchbaren Zeilen wie -> 0 CLOSE I#1 : RUN10
        # dann muss zur Ausführung direkt in die "richtige" Startzeile gesprungen werden 
        tmp_runlinebasic = self.get_runline_from_basic(tmp_transferdata) # gibt None oder eine Zeilennummer aus dem Basicprogramm zurück
        # wenn bASIC enthalten ist, BASIC-MC bilden und als Binärdatei senden
        if tmp_type == result._TYPE_BASICTEXT:
            # ab  v1.3: BASICMC-Speicherabbild erzeugen (0x0300.., BASIC ab 0x0401)
            return self.build_basicmc_from_basic_program(
                prog_bytes,
                nameh=None,
                fmt=ParseResult._FORMAT_SSSD,
                runlinebasic=tmp_runlinebasic,
            )
        # ansonsten als BASIC-Zeilen senden        
        result.format       = result._FORMAT_SSSD
        result.type         = tmp_type
        result.transferdata = tmp_transferdata
        #result.ramclass     = None
        result.validstate   = 0
        result.errorstate   = False

       


        
        return result
        



    # ---------------------------------------------------------
    # SSS - Disk und Kassettenformat
    # ---------------------------------------------------------
    def parseformatSSSBand(self, filedata: bytearray) -> ParseResult:
        """
        Prüft, ob die übergebenen Daten ein gültiges SSS-Format haben (HC-BASIC).

        KC-Bandformat (mit Bandheader):
             [0..2]  = 0xD3 0xD3 0xD3  ("SSS")
             [3..10] = Dateiname (8 Byte)
             [11..12]= Programmlänge (Little Endian)
             [13..]  = Programmdaten (BASIC-Speicherabbild), am Ende evtl. mit Füllbytes aufgefüllt
                       .
        """

        result = ParseResult()

        if not isinstance(filedata, bytearray):
            raise TypeError("parseformatSSSBand() filedata muss vom Typ bytearray sein")

        data = bytes(filedata)
        size = len(data)
        
        if size < 14:
            # Zu kurz für irgendein SSS-Format
            result.validstate = 400
            result.errorstate = True
            return result

        # -----------------------------------------------------
        # 2) KC-Bandformat mit SSS-Kennung:
        #    0–2: 0xD3 0xD3 0xD3
        #    3–10: 8-Byte-Dateiname
        #    11–12: Programmdatenlänge (LE)
        #    13..: Programmdaten (+ evtl. Füllbytes)
        # -----------------------------------------------------
        if size >= 13 and (self._check_sss(data)
                           or self._check_ttt(data)
                           or self._check_uuu(data)
                           or self._check_www(data)
                           or self._check_tap(data)):
            # Dateiname dekodieren (an KCC-Logik angelehnt)
            name_chars = []
            for b in data[3:11]:
                if 0x20 <= b <= 0x7E:
                    name_chars.append(chr(b))
                else:
                    name_chars.append("." if b > 0 else " ")
            name = "".join(name_chars).rstrip()

            prog_len = data[11] | (data[12] << 8)
            if prog_len <= 0:
                # Längenfeld offensichtlich ungültig
                result.validstate = 402
                result.errorstate = True
                return result

            available = size - 13
            if available < prog_len:
                # Datei enthält weniger Nettodaten als im Header angegeben
                result.validstate = 403
                result.errorstate = True
                return result

            # Nettodaten: exakt prog_len Bytes ab Offset 13.
            # Alles dahinter wird als Füllung (Kassettenblock-Auffüllung) ignoriert.
            prog_bytes = data[13:13 + prog_len]

            # Konsistenztest:
            # Länge der Nettodaten muss der im Header angegebenen Programmdatenlänge entsprechen.
            if len(prog_bytes) != prog_len:
                result.validstate = 404
                result.errorstate = True
                return result

            # Auffüllung am Dateiende: maximal 127 Bytes
            padding_len = size - prog_len - 13
            if padding_len > 127:
                result.validstate = 404 
                result.errorstate = True
                return result

            # Muster ist erfüllt -> Detokenisieren
            detok = KC_V24_Transfer_BASICdetokenizer()
            listing = detok.detokenize_hc_basic(program=prog_bytes, compact=True)

            for msg in detok.process_messages: print(" -", msg)

            if listing is None:
                result.validstate = 410   # Detokenisierung fehlgeschlagen 
                result.errorstate = True
                return result

            # Prüfen, was in der Datei enthalten ist -> BASIC oder BASICODE
            tmp_transferdata = bytearray(listing.encode("latin1"))
            tmp_type         = self.classify_basic_text(tmp_transferdata)    # gibt einen TYP-String aus ParseResult zurück
            # Manche BASIC-Programme beginnen mit unbrauchbaren Zeilen wie -> 0 CLOSE I#1 : RUN10
            # dann muss zur Ausführung direkt in die "richtige" Startzeile gesprungen werden 
            tmp_runlinebasic = self.get_runline_from_basic(tmp_transferdata) # gibt None oder eine Zeilennummer aus dem Basicprogramm zurück
            # wenn bASIC enthalten ist, BASIC-MC bilden und als Binärdatei senden
            if tmp_type == result._TYPE_BASICTEXT:
                # ab  v1.3: BASICMC-Speicherabbild erzeugen (0x0300.., BASIC ab 0x0401)
                return self.build_basicmc_from_basic_program(
                    prog_bytes,
                    nameh=None,
                    fmt=ParseResult._FORMAT_SSSK,
                    runlinebasic=tmp_runlinebasic,
                )
            # ansonsten als BASIC-Zeilen senden        
            result.format       = result._FORMAT_SSSK
            result.type         = tmp_type
            result.transferdata = tmp_transferdata
            #result.ramclass     = None
            result.validstate   = 0
            result.errorstate   = False

        # -----------------------------------------------------
        # 3) Nur Kennung, aber kein auswertbarer SSS-Container
        #    (SSS/TTT/UUU/WWW/TAP im Kassettenvorblock ohne
        #     das hier beschriebene Bandformat).
        #    Diese Fälle werden lediglich als „erkannt, aber
        #    nicht sendbar“ markiert.
        # -----------------------------------------------------
        if self._check_sss(data):
            
            result.validstate = 500    # Kennung erkannt, aber kein Speicherabbild
            result.errorstate = True
            return result
        if self._check_ttt(data):
            
            result.validstate = 501    # Kennung erkannt, aber kein Speicherabbild
            result.errorstate = True
            return result

        if self._check_uuu(data):
            result.validstate = 502
            result.errorstate = True
            return result

        if self._check_www(data):
            result.validstate = 503
            result.errorstate = True
            return result

        if self._check_tap(data):
            result.validstate = 504
            result.errorstate = True
            return result

        # Kein SSS-Format erkannt
        result.validstate = 904
        result.errorstate = True
        return result
    
    
    
    def parseRAWBytes(self, filedata: bytearray) -> ParseResult:
        """
        Interpretiert die übergebenen Bytes als „rohes“ Maschinenprogramm ohne
        Headerinformationen.

        Bedingungen:
          - Das Programm wird ab Adresse 0x0200 in den RAM gelegt.
          - Die letzte belegte Adresse darf nicht größer als 0xBFFF sein.
            (verfügbarer Bereich: 0x0200–0xBFFF, also maximal 0xBE00 Bytes)

        Setzt bei Erfolg u. a.:
          - result.start  = 0x0200
          - result.end    = 0x0200 + len(filedata)   (Endadresse + 1)
          - result.callf  = 0x0200 (Standard-Einsprungadresse)
          - result.type   = "CM"
          - result.format = "RAW"
        """

        result = ParseResult()

        if not isinstance(filedata, bytearray):
            raise TypeError("parseRAWBytes() filedata muss vom Typ bytearray sein")

        data = bytes(filedata)
        size = len(data)

        # leere Datei ist kein sinnvolles Maschinenprogramm
        if size == 0:
            result.validstate = 1000  # RAW: Datei leer
            result.errorstate = True
            return result

        startaddr = 0x0200
        # letzte tatsächlich belegte Adresse im RAM (inklusiv)
        lastaddr_inclusive = startaddr + size - 1

        # maximal zulässige Adresse im RAM unterhalb des ROM
        max_ram_addr = 0xBFFF

        # Prüfen, ob das Programm komplett in den Bereich 0x0200–0xBFFF passt
        if lastaddr_inclusive > max_ram_addr:
            result.validstate = 1001  # RAW: passt nicht in den verfügbaren RAM
            result.errorstate = True
            return result

        endaddr_exclusive = startaddr + size  # Endadresse (+1)

        result.start        = startaddr
        result.end          = endaddr_exclusive
        result.callh        = startaddr          # Standard-Einsprungadresse 0x0200
        result.format       = result._FORMAT_RAW # optional: eigener RAW-Formatname
        result.type         = result._TYPE_MC    # Maschinenprogramm
        result.transferdata = bytearray(data)
        result.ramclass     = self._calc_ramclass(endaddr_exclusive)
        result.validstate   = 0
        result.errorstate   = False

        return result

    
    # ---------------------------------------------------------
    # Hilfsfunktionen für KCC/SSS
    # ---------------------------------------------------------
    def _check_sss(self, data: bytes) -> bool:
        """Prüft auf BASIC-Kennung (SSS) am Dateianfang (Kassettenformat)."""
        return len(data) >= 3 and data[0] == 0xD3 and data[1] == 0xD3 and data[2] == 0xD3

    def _check_ttt(self, data: bytes) -> bool:
        """Prüft auf BASIC-Felddaten-Kennung (TTT) am Dateianfang (Kassettenformat)."""
        return len(data) >= 3 and data[0] == 0xD4 and data[1] == 0xD4 and data[2] == 0xD4

    def _check_uuu(self, data: bytes) -> bool:
        """Prüft auf BASIC-Kennung (UUU) am Dateianfang (Kassettenformat)."""
        return len(data) >= 3 and data[0] == 0xD5 and data[1] == 0xD5 and data[2] == 0xD5

    def _check_www(self, data: bytes) -> bool:
        """Prüft auf BASIC-Kennung (WWW) am Dateianfang (Kassettenformat)."""
        return len(data) >= 3 and data[0] == 0xD7 and data[1] == 0xD7 and data[2] == 0xD7

    def _check_tap(self, data: bytes) -> bool:
        """Prüft auf TAP-Datei mit SSS-Kennung am Anfang."""
        return len(data) >= 3 and data[0] == 0x01 and data[1] == 0xD3 and data[2] == 0xD3

    def _check_basic(self, data: bytes) -> bool:
        """
        Prüft auf BASIC-Arbeitszellen bei Adresse 300h im KCC/KCB-Speicherabbild
        (C3 C0 89/8C an der durch startaddr bestimmten Stelle).
        """
        if len(data) < 128 + 3:
            return False

        startaddr = data[17] + (data[18] << 8)
        if startaddr > 0x0300:
            return False

        checkaddr = 0x0300 - startaddr + 0x80
        if checkaddr + 2 >= len(data):
            return False

        if data[checkaddr + 0] != 0xC3:
            return False
        if data[checkaddr + 1] not in (0x89, 0x8C):
            return False
        if data[checkaddr + 2] != 0xC0:
            return False

        return True

    def _isvalid_menu_char(self, value: int) -> bool:
        """
        Zeichen für CAOS-Menüeinträge zulassen: alphanumerisch oder ':'.
        Entspricht isvalid() aus check_KCC.cpp.
        """
        # 0–9, A–Z, a–z oder ':'
        if 0x30 <= value <= 0x39:
            return True
        if 0x41 <= value <= 0x5A:
            return True
        if 0x61 <= value <= 0x7A:
            return True
        if value == ord(':'):
            return True
        return False

    def _find_menu_entries(self, startaddr: int, mem_data: bytes):
        """
        Sucht im Programmbereich nach CAOS-Prologen (0x7F 0x7F <Name> <Epilog>)
        und liefert eine Liste von (Name, Einsprungadresse) zurück.
        """
        entries = []
        index = 0
        n = len(mem_data)

        # minimaler Prolog = 0x7F 0x7F <Epilog> <Code...>
        while index + 4 < n:
            if mem_data[index] == 0x7F and mem_data[index + 1] == 0x7F:
                name_chars = []
                index += 2
                while index + 1 < n and self._isvalid_menu_char(mem_data[index]):
                    name_chars.append(chr(mem_data[index]))
                    index += 1

                # valides Epilogbyte (<= 0x1F) und nichtleerer Name
                if index < n and mem_data[index] <= 0x1F and name_chars:
                    address = index + 1 + startaddr
                    entries.append(("".join(name_chars), address))

            index += 1
            
        
        print("_find_menu_entries()")
        print(", ".join(f"({s}, 0x{n:04X})" for s, n in entries))
        return entries
    
    
    def _calc_ramclass(self, endaddr: Optional[int]) -> Optional[str]:
        """
        Bestimmt die RAM-Größenklasse ("16k", "32k", "48k")
        anhand der Endadresse (endaddr).
        """
        if endaddr is None:
            return None

        if endaddr <= 0x4000:
            return "16k"
        elif endaddr <= 0x8000:
            return "32k"
        elif endaddr <= 0xC000:
            return "48k"
        else:
            # oberhalb 48 kByte bleibt die höchste Klasse erhalten
            return "??k"
