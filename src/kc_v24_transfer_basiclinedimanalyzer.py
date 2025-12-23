from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Set, Tuple


@dataclass
class BasicLineDimAnalyzer:
    """
    Analyse von HC-/KC-BASIC-Zeilen für Verzögerungsabschätzung.

    - array_refs: Anzahl Feldvariablen-Referenzen wie OV(OZ) oder C$(30)
                 (DIM-Deklarationen werden dabei nicht mitgezählt)
    - dim_units : gewichtete Schätzung der DIM-Initialisierungsarbeit
    """
    # DIM-Schätzung
    unknown_dim_default: int = 10     # Ersatzwert, wenn Dimension nicht sicher auswertbar ist (als Max-Index)
    option_base: int = 0             # 0 => Elemente (n+1), 1 => Elemente (n)
    string_factor: int = 2           # Gewicht für String-Felder (…$)
    numeric_factor: int = 1          # Gewicht für numerische Felder

    # Funktionen/Keywords mit Klammern, die NICHT als Feldvariable gezählt werden sollen
    non_arrays: Set[str] = field(default_factory=lambda: {
        "AT", "TAB", "SPC",
        "SGN", "INT", "ABS", "SQR", "RND", "LN", "EXP", "COS", "SIN", "TAN", "ATN",
        "USR", "FRE", "INP", "POS", "PEEK", "DEEK",
        "LEN", "STR$", "VAL", "ASC", "CHR$", "LEFT$", "RIGHT$", "MID$", "STRING$", "INSTR",
        "VGET$", "PTEST",
    })

    def add_non_array_names(self, names: Iterable[str]) -> None:
        for n in names:
            self.non_arrays.add(n.upper())

    # ---------------- Public API ----------------

    def analyze_line(self, line: str) -> Tuple[int, int]:
        """Rückgabe: (array_refs, dim_units)"""
        return self.count_array_refs(line), self.dim_allocation_units(line)

    def count_array_refs(self, line: str) -> int:
        """
        Zählt Feldvariablen-Referenzen NAME(...), ignoriert:
        - Strings/Kommentare
        - bekannte Funktionen/Keywords mit Klammern
        - DIM-Deklarationen
        """
        s = self._remove_dim_statements(line)
        n = len(s)
        i = 0
        in_string = False
        count = 0

        while i < n:
            ch = s[i]

            if in_string:
                if ch == '"':
                    if i + 1 < n and s[i + 1] == '"':  # "" innerhalb String
                        i += 2
                        continue
                    in_string = False
                i += 1
                continue

            if ch == '"':
                in_string = True
                i += 1
                continue

            # Kommentarstart
            if ch == "'" or (ch == "!" and (i == 0 or not self._is_alnum(s[i - 1]))):
                break

            if self._is_letter(ch):
                start = i
                i += 1
                while i < n and self._is_alnum(s[i]):
                    i += 1
                if i < n and s[i] == "$":
                    i += 1

                ident = s[start:i].upper()
                if ident == "REM":
                    break

                j = self._skip_ws(s, i)
                if j < n and s[j] == "(":
                    # FN...(...) ist Funktionsaufruf, keine Feldvariable
                    if not ident.startswith("FN") and ident not in self.non_arrays:
                        count += 1
                continue

            i += 1

        return count

    def dim_allocation_units(self, line: str) -> int:
        """
        Schätzt die 'DIM-Kosten' der Zeile:
        - konstante Dimensionen werden ausgewertet (nur sehr einfache Ausdrücke)
        - Elementzahl: Produkt der Dimensionen (unter Berücksichtigung option_base)
        - String-Felder werden höher gewichtet
        """
        code = self._strip_basic_line_number(line)
        raw = self._strip_strings_and_comments(code)
        up = raw.upper()

        units = 0
        i = 0
        while True:
            pos = up.find("DIM", i)
            if pos < 0:
                break

            prev = up[pos - 1] if pos > 0 else " "
            if prev.isalnum() or prev == "$":
                i = pos + 3
                continue

            j = pos + 3
            if j >= len(up) or not ("A" <= up[j] <= "Z"):
                i = pos + 3
                continue

            # DIM-Teil bis ':' auf Top-Level-Klammer-Ebene
            stmt = raw[j:]
            cut: List[str] = []
            depth = 0
            k = 0
            while k < len(stmt):
                ch = stmt[k]
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth = max(0, depth - 1)
                if ch == ":" and depth == 0:
                    break
                cut.append(ch)
                k += 1
            dim_part = "".join(cut).strip()

            for decl in self._split_top_level_commas(dim_part):
                m = re.match(r"^([A-Za-z][A-Za-z0-9]*\$?)\s*\((.*)\)\s*$", decl.strip())
                if not m:
                    continue
                name = m.group(1)
                dims_str = m.group(2).strip()

                dims: List[int] = []
                for de in self._split_top_level_commas(dims_str):
                    v = self._safe_int_expr(de)
                    if v is None:
                        v = self.unknown_dim_default
                    if v < 0:
                        v = 0
                    dims.append(v)

                elems = 1
                for max_index in dims:
                    elems *= self._elements_for_dim(max_index)

                factor = self.string_factor if name.endswith("$") else self.numeric_factor
                units += elems * factor

            i = pos + 3

        return units

    # ---------------- Internals ----------------

    def _elements_for_dim(self, max_index: int) -> int:
        # option_base=0 => 0..max_index => max_index+1
        # option_base=1 => 1..max_index => max_index
        base = 0 if self.option_base <= 0 else 1
        return max(0, max_index - base + 1)

    @staticmethod
    def _is_letter(c: str) -> bool:
        return ("A" <= c <= "Z") or ("a" <= c <= "z")

    @staticmethod
    def _is_alnum(c: str) -> bool:
        return c.isdigit() or BasicLineDimAnalyzer._is_letter(c)

    @staticmethod
    def _skip_ws(s: str, idx: int) -> int:
        n = len(s)
        while idx < n and s[idx].isspace():
            idx += 1
        return idx

    @staticmethod
    def _strip_basic_line_number(line: str) -> str:
        return re.sub(r"^\s*\d+\s*", "", line, count=1)

    @staticmethod
    def _split_top_level_commas(s: str) -> List[str]:
        parts: List[str] = []
        cur: List[str] = []
        depth = 0
        for ch in s:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            if ch == "," and depth == 0:
                parts.append("".join(cur).strip())
                cur = []
            else:
                cur.append(ch)
        tail = "".join(cur).strip()
        if tail:
            parts.append(tail)
        return parts

    @staticmethod
    def _safe_int_expr(expr: str) -> Optional[int]:
        """
        Sichere Auswertung sehr einfacher ganzzahliger Ausdrücke:
        erlaubt nur Ziffern, + - * / und Klammern.
        """
        expr = expr.strip()
        if not expr:
            return None
        if re.search(r"[^0-9\+\-\*\/\(\)\s]", expr):
            return None
        try:
            node = ast.parse(expr, mode="eval")
        except SyntaxError:
            return None

        def ev(n):
            if isinstance(n, ast.Expression):
                return ev(n.body)
            if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
                return int(n.value)
            if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.UAdd, ast.USub)):
                v = ev(n.operand)
                return v if isinstance(n.op, ast.UAdd) else -v
            if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv)):
                a = ev(n.left)
                b = ev(n.right)
                if isinstance(n.op, ast.Add):
                    return a + b
                if isinstance(n.op, ast.Sub):
                    return a - b
                if isinstance(n.op, ast.Mult):
                    return a * b
                if isinstance(n.op, ast.FloorDiv):
                    return a // b
                if isinstance(n.op, ast.Div):
                    return int(a / b)
            raise ValueError("unsafe")

        try:
            return int(ev(node))
        except Exception:
            return None

    @staticmethod
    def _strip_strings_and_comments(line: str) -> str:
        """
        Ersetzt Stringliterale durch Leerzeichen und schneidet Kommentare ab (', REM, !).
        """
        out: List[str] = []
        i = 0
        n = len(line)
        in_string = False

        while i < n:
            ch = line[i]

            if in_string:
                if ch == '"':
                    if i + 1 < n and line[i + 1] == '"':
                        out.append("  ")
                        i += 2
                        continue
                    in_string = False
                    out.append(" ")
                else:
                    out.append(" ")
                i += 1
                continue

            if ch == '"':
                in_string = True
                out.append(" ")
                i += 1
                continue

            if ch == "'":
                break
            if ch == "!" and (i == 0 or not line[i - 1].isalnum()):
                break

            # REM als Kommentar (best effort)
            if line[i:i+3].upper() == "REM":
                prev = line[i - 1] if i > 0 else " "
                nxt = line[i + 3] if i + 3 < n else " "
                if not prev.isalnum() and not nxt.isalnum():
                    break

            out.append(ch)
            i += 1

        return "".join(out)

    def _remove_dim_statements(self, line: str) -> str:
        """
        Entfernt DIM-Statements (best effort), damit DIM-Deklarationen nicht als Feldzugriffe zählen.
        """
        code = self._strip_basic_line_number(line)
        raw = self._strip_strings_and_comments(code)
        up = raw.upper()
        out = list(raw)

        i = 0
        while True:
            pos = up.find("DIM", i)
            if pos < 0:
                break

            prev = up[pos - 1] if pos > 0 else " "
            if prev.isalnum() or prev == "$":
                i = pos + 3
                continue

            j = pos + 3
            if j >= len(up) or not ("A" <= up[j] <= "Z"):
                i = pos + 3
                continue

            # bis ':' auf Top-Level
            k = j
            depth = 0
            while k < len(raw):
                ch = raw[k]
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth = max(0, depth - 1)
                if ch == ":" and depth == 0:
                    break
                k += 1

            for t in range(pos, k):
                out[t] = " "
            i = k

        return "".join(out)
