from typing import Dict, Iterable, Tuple, List, Union
import sys

# verarbeitet Datenströme aus SSS-Dateien, die tokenisierte HC-BASIC-Binärcode enthalten
# und erstellt aus diesen BASIC-Listing-Dateien, ähnlich wie sie mit LIST
# vom BASIC des KC angezeigt werden
# das CLI-Interface nimmt auch SSS-Dateien mit Diskettenheader und auffüllbytes entgegen
# und erzeugt daraus eine ASCII-Textdatei mit dem Programm-Listing
class KC_V24_Transfer_BASICdetokenizer:
    """Detokenizer für HC-/KC-BASIC-Programme (KC85/3, KC85/4)."""

    HC_BASIC_TOKENS: Dict[int, str] = {
        
        # TOKENS aus dem BASIC-ROM  (0x80–0xD4)
        0x80: "END",
        0x81: "FOR",
        0x82: "NEXT",
        0x83: "DATA",
        0x84: "INPUT",
        0x85: "DIM",
        0x86: "READ",
        0x87: "LET",
        0x88: "GOTO",
        0x89: "RUN",
        0x8A: "IF",
        0x8B: "RESTORE",
        0x8C: "GOSUB",
        0x8D: "RETURN",
        0x8E: "REM",
        0x8F: "STOP",
        0x90: "OUT",
        0x91: "ON",
        0x92: "NULL",
        0x93: "WAIT",
        0x94: "DEF",
        0x95: "POKE",
        0x96: "DOKE",
        0x97: "AUTO",
        0x98: "LINES",
        0x99: "CLS",
        0x9A: "WIDTH",
        0x9B: "BYE",
        0x9C: "!",          # Kurzform von REM
        0x9D: "CALL",
        0x9E: "PRINT",
        0x9F: "CONT",
        0xA0: "LIST",
        0xA1: "CLEAR",
        0xA2: "CLOAD",
        0xA3: "CSAVE",
        0xA4: "NEW",
        0xA5: "TAB(",
        0xA6: "TO",
        0xA7: "FN",
        0xA8: "SPC(",
        0xA9: "THEN",
        0xAA: "NOT",
        0xAB: "STEP",
        0xAC: "+",
        0xAD: "-",
        0xAE: "*",
        0xAF: "/",
        0xB0: "^",
        0xB1: "AND",
        0xB2: "OR",
        0xB3: ">",
        0xB4: "=",
        0xB5: "<",
        0xB6: "SGN",
        0xB7: "INT",
        0xB8: "ABS",
        0xB9: "USR",
        0xBA: "FRE",
        0xBB: "INP",
        0xBC: "POS",
        0xBD: "SQR",
        0xBE: "RND",
        0xBF: "LN",
        0xC0: "EXP",
        0xC1: "COS",
        0xC2: "SIN",
        0xC3: "TAN",
        0xC4: "ATN",
        0xC5: "PEEK",
        0xC6: "DEEK",
        0xC7: "PI",
        0xC8: "LEN",
        0xC9: "STR$",
        0xCA: "VAL",
        0xCB: "ASC",
        0xCC: "CHR$",
        0xCD: "LEFT$",
        0xCE: "RIGHT$",
        0xCF: "MID$",
        0xD0: "LOAD",
        0xD1: "TRON",
        0xD2: "TROFF",
        0xD3: "EDIT",
        0xD4: "ELSE",


        # Tokens aus dem CAOS 4.2 - ROM
        0xD5: "INKEY$",
        0xD6: "JOYST",
        0xD7: "STRING$",
        0xD8: "INSTR",
        0xD9: "RENUMBER",
        0xDA: "DELETE",
        0xDB: "PAUSE",
        0xDC: "BEEP",
        0xDD: "WINDOW",
        0xDE: "BORDER",
        0xDF: "INK",
        0xE0: "PAPER",
        0xE1: "AT",     # PRINT AT(...)
        0xE2: "COLOR",
        0xE3: "SOUND",
        0xE4: "PSET",
        0xE5: "PRESET",
        0xE6: "BLOAD",
        0xE7: "VPEEK",
        0xE8: "VPOKE",
        0xE9: "LOCATE",
        0xEA: "KEYLIST",
        0xEB: "KEY",
        0xEC: "SWITCH",
        0xED: "PTEST",
        0xEE: "CLOSE",
        0xEF: "OPEN",
        0xF0: "RANDOMIZE",
        0xF1: "VGET$",
        0xF2: "LINE",
        0xF3: "CIRCLE",
        0xF4: "CSRLIN",
    }

    # Für besser lesbare Ausgabe im Normalmodus (compact=False)
    KEYWORDS_WITH_SPACE_AFTER = {
        "END", "FOR", "NEXT", "DATA", "INPUT", "DIM", "READ", "LET",
        "GOTO", "RUN", "IF", "RESTORE", "GOSUB", 
        "OUT", "ON", "NULL", "WAIT", "DEF", "POKE", "DOKE",
        "LINES", "WIDTH",
        "CALL", "PRINT", 
        "CLOAD", "CSAVE", "LOAD",
        "TRON", "TROFF",
        "THEN", "ELSE", "TO", "STEP", "AND", "OR", "NOT",
        "INKEY$", "JOYST", "STRING$", "PAUSE", "BEEP",
        "COLOR", "SOUND", "PSET", "PRESET", "BLOAD",
        "VPEEK","VPOKE", "LOCATE", "SWITCH",
        
        "WINDOW", "BORDER", "INK", "PAPER",# "AT",     # PRINT AT(...)
        "PTEST", "CLOSE", "OPEN", "RANDOMIZE",
        "LINE", "CIRCLE",
        
        "VGET$", "CSRLIN", "INSTR",
        
        "REM", "!", "?"
    }

    HC_BASIC_COMPACT_FORMS = {
        "PRINT": "?",   # PRINT -> ?
        "REM":   "!",   # REM   -> !
        "LET":   "",    # LET   entfällt vollständig
    }

    # Mapping von latin1-Zeichencodes auf KC-Zeichencodes
    #out = bytes(mapping.get(b, b) for b in data)           # bytes
    #out_ba = bytearray(mapping.get(b, b) for b in ba)      # bytearray
    _LATIN_2_KC = { 0xE4: 0x7B,  # ä
                    0xF6: 0x7C,  # ö
                    0xFC: 0x7D,  # ü
                    0xC4: 0x7B,  # Ä -> ä
                    0xD6: 0x7C,  # Ö -> ö
                    0xDC: 0x7D,  # Ü -> ü
                    0xDF: 0x7E,  # ß

                    0xAC: 0x5D,  # ¬ 
                    0x7C: 0x5C,  # |
                    0xA9: 0x60,  # ©
                    
                    0x84: 0x22,  # „  -> "
                    0x93: 0x22,  # “  -> "
                    0x94: 0x22,  # ”  -> "
                    0x96: 0x2D,  # –  -> -
                    0x97: 0x2D,  # —  -> -
                 }
    # Mapping von latin1-Zeichencodes auf KC-Zeichencodes
    #out = bytes(mapping.get(b, b) for b in data)           # bytes
    #out_ba = bytearray(mapping.get(b, b) for b in ba)      # bytearray
    _KC_2_LATIN = { 0x7B: 0xE4,  # ä
                    0x7C: 0xF6,  # ö
                    0x7D: 0xFC,  # ü
                    0x7E: 0xDF,  # ß

                    0x5D: 0xAC,  # ¬ 
                    0x5C: 0x7C,  # |
                    0x60: 0xA9,  # ©
                 }
                 

    def __init__(self) -> None:
        # Sammelliste für Hinweise/Warnungen
        self.process_messages: List[str] = []

    @staticmethod
    def _normalize_kc_text_byte(b: int) -> int:
        # Umlaute/ß in tokenisierten Programmen: 0xFB..0xFE -> 0x7B..0x7E
        if b in (0xFB, 0xFC, 0xFD, 0xFE):
            return b & 0x7F
        return b

    def _check_illegal_char(self, b: int, line_no: int, offset: int, context: str) -> bool:
        if b == 0:
            return True
        if (b < 0x20 and b != 0x09):  # TAB erlaubt
            self.process_messages.append(
                f"Unzulässiges Steuerzeichen 0x{b:02X} in Zeile {line_no} an Byte-Offset {offset} ({context}) - Zeichen entfernt"
            )
            return False
        return True
    def _iter_tokenized_lines(self, program: bytes) -> Iterable[Tuple[int, bytes]]:
        """
        Zerlegt einen HC-BASIC-Programmbereich in (Zeilennummer, Roh-Bytes der Zeile).
        Erwartet reine Programmdaten ohne CAOS-Header
        """
        i = 0
        n = len(program)

        while i + 4 <= n:
            next_ptr = program[i] | (program[i + 1] << 8)
            line_no = program[i + 2] | (program[i + 3] << 8)

            # Text der Zeile bis zum 0-Byte
            j = i + 4
            while j < n and program[j] != 0x00:
                j += 1

            line_bytes = program[i + 4:j]
            yield line_no, line_bytes

            # letzte Zeile erreicht
            if next_ptr == 0:
                break

            # zur nächsten Zeile springen (0-Byte überspringen)
            i = j + 1
    def _normalize_text_byte(self, x: int) -> int:
        # TODO: Exakte Prüfung, ob das wirklich so ist!
        # In tokenisierten HC-/KC-BASIC-Programmen werden Umlaute/ß in Strings/REM
        # oft als 0xFB..0xFE abgelegt (KC-Code 0x7B..0x7E mit gesetztem Bit 7).
        if x in (0xFB, 0xFC, 0xFD, 0xFE):
            return x & 0x7F
        return x
    def detokenize_line(self, line_bytes: bytes, compact: bool = False, line_no: str = "") -> str:
        """
        Detokenisiert den Textanteil einer einzelnen BASIC-Zeile.
        Gibt nur den Teil hinter der Zeilennummer zurück.

        compact=False: formatiert mit zusätzlichen Leerzeichen.
        compact=True:  ohne zusätzliche sowie ohne vorhandene Leerzeichen
                       außerhalb von Strings und Kommentaren.
        """
        out: List[str] = []

        in_rem = False
        in_string = False
        i = 0
        length = len(line_bytes)

        while i < length:
            b = line_bytes[i]

            if not in_rem:
                # Tokens werden nur außerhalb von Strings ausgewertet
                token = None if in_string else self.HC_BASIC_TOKENS.get(b)

                if token is not None:
                    if compact and token in self.HC_BASIC_COMPACT_FORMS:
                        token = self.HC_BASIC_COMPACT_FORMS[token]

                    if token == "REM" or token == "!":  # REM
                        # REM – ab hier Kommentar
                        in_rem = True

                    out.append(token)
                    if (not compact) and (token in self.KEYWORDS_WITH_SPACE_AFTER):
                        if not out[-1].endswith(" "):
                            out.append(" ")

                    i += 1
                    continue

                # kein bekanntes Token
                if not in_string:
                    # außerhalb String/REM: hier könnte ein unbekanntes Token liegen
                    if 0x80 <= b <= 0xFF:
                        self.process_messages.append(
                            f"Unbekanntes Token 0x{b:02X} in Zeile {line_no} beim Byte-Offset {i}"
                        )
                        raise ValueError(
                            f"Unbekanntes Token 0x{b:02X} in Zeile {line_no} beim Byte-Offset {i}"
                        )

                # kein Token: normales Zeichen
                if b == 0x22:  # Anführungszeichen "
                    out.append('"')
                    in_string = not in_string
                    i += 1
                    continue

                if not in_string:
                    # außerhalb String und REM
                    if b in (0x20, 0x09):  # Space oder TAB
                        if compact:
                            i += 1
                            continue
                        else:
                            if not out or not out[-1].endswith(" "):
                                out.append(" ")
                            i += 1
                            continue

                    out.append(chr(b))
                    i += 1
                else:
                    # innerhalb String: Zeichen wörtlich übernehmen (mit Normalisierung)
                    b2 = self._normalize_text_byte(b)
                    if self._check_illegal_char(b2, line_no, i, "String"):
                        out.append(chr(b2))
                    i += 1
            else:
                # innerhalb REM/! – alles wörtlich bis Zeilenende
                b2 = self._normalize_text_byte(b)
                if self._check_illegal_char(b2, line_no, i, "REM"):
                    if not compact:  # in der Kurzdarstellung Kommentare weglassen
                        if b2 != 0:
                            out.append(chr(b2) if b2 >= 32 else " ")
                i += 1

        return "".join(out)

    def detokenize_hc_basic(self, program: bytes, compact: bool = False) -> str:
        """
        Wandelt eine tokenisierte HC-BASIC-Programmdarstellung in ein
        BASIC-Listing um.
        Die verwendete Zeichenkodierung ist die von HC-BASIC

        compact=False: normal formatiert (ähnlich LIST).
        compact=True:  maximal kompakt (keine Leerzeichen außerhalb
                       von String/REM).
        """
        try:
            lines: List[str] = []
            line_space = " " if not compact else ""
            for line_no, raw in self._iter_tokenized_lines(program):
                text = self.detokenize_line(raw, compact=compact, line_no=line_no).rstrip()
                tmp = f"{line_no}{line_space}{text}"
                if len(tmp) > 76:
                    self.process_messages.append(
                       f"Warnung: Zeile {line_no} - Zeilenlänge von max. 76 Zeichen überschritten"
                    )
                lines.append(tmp)

            # KC-Zeilenende CRLF
            return (chr(0x0D) + chr(0x0A)).join(lines)
        except ValueError as e:
            print(f"detokenize_hc_basic: {e}")
            return None


# Einfacher CLI-Einstiegspunkt
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "python kc_v24_transfer_basicdetokenizer.py <datei.sss> [-compact] [-fileout] [-hcencode]"
            ,"  -compact: Das Listing wird so kompakt wie möglich erzeugt"
            ,"  -fileout: Es wird eine Datei <datei.SSS.enctype.txt> mit dem Listing angelegt"
            ," -hcencode: Das Listing in original HC-BASIC-Zeichenkodierung speichern"
            ,""
            ,"Konvertiert tokenisierte HC-Basic-Binärdaten des KC85/4 in eine textliche BASIC-Programm-Liste"
            ,"Tokenisierte Daten finden sich typischerweise in .SSS-Dateien, die der KC per FSAVE/CSAVE auf Diskette oder Band speichert."
            ,"Das Programm nimmt auch direkt .SSS-Dateien im KC-\"Diskettenformat\" entgegen und versucht die Tokendaten aus diesen zu lesen."
            ,""
            ,"Achtung: Die ohne -compact erzeugten Programmzeilen können länger als die auf dem KC eingebbaren 76 Zeichen sein."
            , sep="\n"
            , file=sys.stderr
        )
        sys.exit(1)

    filename = sys.argv[1]
    compact_flag  = ("-compact"  in sys.argv[2:])
    fileout_flag  = ("-fileout"  in sys.argv[2:])
    hcencode_flag = ("-hcencode" in sys.argv[2:])
    silent_flag   = ("-silent"   in sys.argv[2:])

    try:
        with open(filename, "rb") as f:
            data = f.read()
    except OSError as e:
        print(f"Fehler beim Lesen von '{filename}': {e}", file=sys.stderr)
        sys.exit(1)

    # Standardfall: gesamte Datei als BASIC-Programmdaten verwenden
    program_bytes = data

    # Quick and Dirty-Versuch, ein SSS(D)-ähnliches Format zu erkennen:
    # - erstes Wort (LE) = Länge der BASIC-Daten (ohne dieses Wort)
    # - BASIC-Daten enden mit 00 00 00
    # - Rest der Datei hat höchstens 127 Auffüllbytes
    if len(data) >= 5:  # 2 Byte Länge + mind. 3 Byte 00 00 00
        basic_len = data[0] | (data[1] << 8)
        basic_start = 2
        if basic_len >= 3:
            basic_end = basic_start + basic_len
            if basic_end <= len(data):
                basic_region = data[basic_start:basic_end]
                padding_len = len(data) - basic_end
                if (
                    basic_region[-3:] == b"\x00\x00\x00"
                    and padding_len <= 127
                ):
                    # SSS(D)-BASIC-Bereich erkannt
                    program_bytes = basic_region
                    print("SSS(D) Format erkannt", file=sys.stderr)

    detok = KC_V24_Transfer_BASICdetokenizer()
    listing_kc = detok.detokenize_hc_basic(program=program_bytes, compact=compact_flag)
    
    if listing_kc is not None:
        
        if hcencode_flag:   # nicht konvertieren in latin1-encoding
            listing = listing_kc
        else:
            # KC -> latin1 (ä/ö/ü/ß usw.)
            listing = listing_kc.translate(detok._KC_2_LATIN)
        
        if not -silent_flag:
            print(listing)

        # Optional: Textdatei mit dem Listing erzeugen
        if fileout_flag:
            if hcencode_flag:
                outname = filename + ".hcenc.txt"
            else:
                outname = filename + ".latin1.txt"
                
            try:
                with open(outname, "w", encoding="latin-1") as f_out:
                    flisting = listing
                    f_out.write(flisting.replace("\r\n", "\n"))
                    print()
                    print(f"Datei {outname} erzeugt")
            except OSError as e:
                print(f"Fehler beim Schreiben von '{outname}': {e}", file=sys.stderr)

        # optionale Statistik
        #len0 = len(program_bytes)
        #len1 = len(detok.detokenize_hc_basic(program=program_bytes, compact=False))
        #len2 = len(detok.detokenize_hc_basic(program=program_bytes, compact=True))
        #print()
        #print(f"{len0} Bytes SSS-Quelldatei [100%]")
        #print(f"{len2} Bytes Compact-Format [{(100 + (len2-len0)/len0*100):.0f}%]")
        #print(f"{len1} Bytes LIST-Format    [{(100 + (len1-len0)/len0*100):.0f}%]")

    else:
        print("Fehler: Daten konnten nicht detokenisiert werden")
        
    
    # ggf. Hinweise zu unzulässigen Zeichen und unbekannten Tokens ausgeben
    if detok.process_messages:
        print("\nProzessmeldungen:")
        for msg in detok.process_messages:
            print(" -", msg)