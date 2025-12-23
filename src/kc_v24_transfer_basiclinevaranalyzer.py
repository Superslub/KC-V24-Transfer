import re
from typing import List, Tuple, Optional, Set


class BasicLineVarAnalyzer:
    """
    Extrahiert Variablenzugriffe aus einer HC-BASIC-Zeile.

    - Stringliterale werden ignoriert
    - Kommentare ab REM oder ! werden ignoriert
    - Kompakte Schreibweise ohne Leerzeichen wird unterstützt (z.B. 'ONOZGOTO' -> ON + OZ + GOTO)
    """

    DEFAULT_KEYWORDS: Set[str] = {
        # Programmfluss / Struktur
        "IF", "THEN", "ELSE", "FOR", "TO", "STEP", "NEXT", "GOTO", "GOSUB", "RETURN", "ON",
        "END", "STOP", "RUN", "CONT", "LET", "DIM",

        # Programmverwaltung / Editor
        "NEW", "LIST", "LIST#", "EDIT", "DELETE", "RENUMBER", "AUTO", "KEY", "KEYLIST", "TRON", "TROFF",

        # Ein-/Ausgabe
        "PRINT", "PRINT#", "INPUT", "INPUT#", "OPEN", "CLOSE",
        "LOAD", "LOAD#", "BLOAD", "CLOAD", "CSAVE",
        "READ", "DATA", "RESTORE",

        # Bildschirm / Grafik / Ton
        "CLS", "PAPER", "INK", "COLOR", "LOCATE", "WINDOW", "WIDTH", "CSRLINE", "TAB", "SPC",
        "PSET", "PRESET", "LINE", "CIRCLE", "PTEST",
        "SOUND", "BEEP", "PAUSE",

        # System / Speicher / Peripherie
        "CLEAR", "FRE", "PEEK", "DEEK", "POKE", "DOKE", "VPEEK", "VPOKE", "CALL", "SWITCH", "USR",
        "INP", "OUT", "WAIT", "JOYST", "POS",
        "BYE", "BASIC", "REBASIC",

        # Operatoren / Logik
        "AND", "OR", "NOT",

        # Mathematik / Konstanten
        "ABS", "ATN", "COS", "EXP", "INT", "LN", "SGN", "SIN", "SQR", "TAN", "RND", "RANDOMIZE", "PI",

        # Strings
        "ASC", "CHR$", "LEN", "VAL", "STR$", "LEFT$", "MID$", "RIGHT$", "RIGTH$", "STRING$",
        "VGET$", "INSTR", "INKEY$", "INKRY$",

        # Kommentare / Funktionen definieren
        "REM", "DEF", "FN",

        # PRINT-Kurzform (wird separat behandelt)
        "?",
    }

    def __init__(self, *, max_var_letters: int = 2, keywords: Optional[Set[str]] = None) -> None:
        self.max_var_letters = max(1, int(max_var_letters))
        kws = keywords if keywords is not None else self.DEFAULT_KEYWORDS
        self.keywords: Set[str] = {k.upper() for k in kws if k}
        self._kw_sorted = sorted([k for k in self.keywords if k != "?"], key=len, reverse=True)

    @staticmethod
    def _strip_leading_line_number(line: str) -> str:
        return re.sub(r"^\s*\d{1,5}\s*", "", line)

    @staticmethod
    def _mask_string_literals(line: str) -> str:
        # alles zwischen "..." (inkl. Anführungszeichen) durch Leerzeichen ersetzen
        out = []
        i = 0
        in_str = False
        while i < len(line):
            ch = line[i]
            if ch == '"':
                # "" innerhalb eines Strings (Escaping) – bleibt im String
                if in_str and i + 1 < len(line) and line[i + 1] == '"':
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

    @staticmethod
    def _cut_comment(masked: str) -> str:
        # '!' startet Kommentar (außerhalb Strings, daher hier sicher)
        excl = masked.find("!")
        if excl != -1:
            masked = masked[:excl]

        # REM startet Kommentar (auch kompakt, z.B. ':REM...')
        m = re.search(r"(?i)(^|[^A-Z0-9$])REM", masked)
        if m:
            idx = m.start(0) + (0 if m.group(1) == "" else 1)
            masked = masked[:idx]
        return masked

    def _match_keyword(self, upper: str, i: int) -> Optional[str]:
        for kw in self._kw_sorted:
            if upper.startswith(kw, i):
                return kw
        return None

    def analyze_line(self, line: str) -> Tuple[int, List[str]]:
        """
        Rückgabe: (Anzahl_Variablenzugriffe, Variablenliste_in_Auftretensreihenfolge)

        Variablen werden auf max_var_letters Buchstaben begrenzt (optional gefolgt von Ziffern und '$'),
        damit kompakte Schreibweise korrekt zerlegt wird.
        """
        if not line:
            return 0, []

        s = self._strip_leading_line_number(line)
        s = self._mask_string_literals(s)
        s = self._cut_comment(s)

        if re.match(r"^\s*(!|REM\b)", s, flags=re.IGNORECASE):
            return 0, []

        upper = s.upper()
        vars_found: List[str] = []
        i = 0
        n = len(upper)

        while i < n:
            ch = upper[i]

            if ch.isspace() or ch.isdigit():
                i += 1
                continue

            if ch == "?":  # PRINT-Kurzform
                i += 1
                continue

            if "A" <= ch <= "Z":
                kw = self._match_keyword(upper, i)
                if kw:
                    if kw in ("DATA", "REM"):
                        break
                    i += len(kw)

                    # FN<name> (Benutzerfunktion): Funktionsname überspringen (nicht als Variable zählen)
                    if kw == "FN" and i < n and ("A" <= upper[i] <= "Z"):
                        letters = 0
                        while i < n and ("A" <= upper[i] <= "Z") and letters < self.max_var_letters:
                            i += 1
                            letters += 1
                        while i < n and upper[i].isdigit():
                            i += 1
                        if i < n and upper[i] == "$":
                            i += 1
                    continue

                # Variable: bis max_var_letters Buchstaben, dann Ziffern, dann optional '$'
                start = i
                letters = 0
                while i < n and ("A" <= upper[i] <= "Z") and letters < self.max_var_letters:
                    i += 1
                    letters += 1
                while i < n and upper[i].isdigit():
                    i += 1
                if i < n and upper[i] == "$":
                    i += 1

                varname = upper[start:i]
                if varname and varname not in self.keywords:
                    vars_found.append(varname)
                continue

            i += 1

        return len(vars_found), vars_found


