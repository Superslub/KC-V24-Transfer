; gen_cctl01.asm  (KC85/4, CAOS 4.2 / HC-BASIC)
; ORG 4600h
; erzeugt:
;   CCTL0-Kopien: 4800h .. 63FFh  (14 * 512)
;   CCTL1-Kopien: 6400h .. 7FFFh  (14 * 512)

        ORG     4600h

; BASIC-Hilfsroutinen (siehe BASIC-Handbuch, USR-Rahmenprogramm)
CPRVL3  EQU     0C96Fh          ; Parameter auswerten -> DE
FRE3    EQU     0D0B1h          ; Funktionswert aus A/B

; IRM schalten (CAOS)
IRMON   EQU     0F018h
IRMOF   EQU     0F01Bh

; Zeigerzellen (vom User vorgegeben)
CCTL0P  EQU     0B7A6h
CCTL1P  EQU     0B7A8h

DEST0   EQU     04800h
DEST1   EQU     06400h

START:
        CALL    CPRVL3          ; USR(x) Parameter holen (ungenutzt)

        ; --- CCTL0 -> DEST0 ---
        CALL    IRMON
        LD      HL,(CCTL0P)     ; HL = Quelle (CCTL0)
        CALL    IRMOF

        LD      DE,DEST0        ; Zielbasis
        CALL    GEN14           ; erzeugt 14*512 Bytes

        ; --- CCTL1 -> DEST1 ---
        CALL    IRMON
        LD      HL,(CCTL1P)     ; HL = Quelle (CCTL1)
        CALL    IRMOF

        LD      DE,DEST1
        CALL    GEN14

        ; Rückgabe 0 an BASIC
        XOR     A
        LD      B,A
        CALL    FRE3
        RET

; ------------------------------------------------------------
; GEN14: HL=SRC, DE=DESTBASE
; erzeugt Blocks:
;   1..7  : SHIFT DOWN  (1..7 Nullbytes oben, Rest aus Original)
;   8..14 : BOTTOM->TOP (1..7 Bytes vom Ende, Rest Nullbytes)
; Ergebnis: DE zeigt danach hinter den 14 Blöcken.
; ------------------------------------------------------------
GEN14:
        LD      (SRCBASE),HL

        LD      C,1
G14_DN:  CALL    SHIFT_BLOCK     ; C=SD (1..7)
        INC     C
        LD      A,C
        CP      8
        JR      NZ,G14_DN

        LD      C,1
G14_UP:  CALL    BOTTOM_BLOCK    ; C=BK (1..7)
        INC     C
        LD      A,C
        CP      8
        JR      NZ,G14_UP
        RET

; ------------------------------------------------------------
; SHIFT_BLOCK: C=SD (1..7)
; je Zeichen (8 Bytes):
;   SD * 00, dann (8-SD) Bytes von Anfang, Rest der Quelle überspringen
; ------------------------------------------------------------
SHIFT_BLOCK:
        LD      HL,(SRCBASE)
        LD      B,64             ; 64 Zeichen
SB_CH:
        PUSH    BC               ; B=Zeichenzähler, C=SD sichern

        LD      B,C              ; SD Nullbytes
        XOR     A
SB_Z:   LD      (DE),A
        INC     DE
        DJNZ    SB_Z

        LD      A,8
        SUB     C
        LD      B,A              ; (8-SD) Bytes kopieren
SB_CP:  LD      A,(HL)
        INC     HL
        LD      (DE),A
        INC     DE
        DJNZ    SB_CP

        LD      B,C              ; SD Bytes in Quelle überspringen
SB_SK:  INC     HL
        DJNZ    SB_SK

        POP     BC
        DJNZ    SB_CH
        RET

; ------------------------------------------------------------
; BOTTOM_BLOCK: C=BK (1..7)
; je Zeichen:
;   (8-BK) Bytes Quelle überspringen, BK Bytes kopieren, (8-BK) * 00
; ------------------------------------------------------------
BOTTOM_BLOCK:
        LD      HL,(SRCBASE)
        LD      B,64
BB_CH:
        PUSH    BC               ; B=Zeichenzähler, C=BK sichern

        LD      A,8
        SUB     C
        LD      B,A              ; (8-BK) überspringen
BB_SK:  INC     HL
        DJNZ    BB_SK

        LD      B,C              ; BK Bytes kopieren
BB_CP:  LD      A,(HL)
        INC     HL
        LD      (DE),A
        INC     DE
        DJNZ    BB_CP

        LD      A,8
        SUB     C
        LD      B,A              ; (8-BK) Nullbytes
        XOR     A
BB_Z:   LD      (DE),A
        INC     DE
        DJNZ    BB_Z

        POP     BC
        DJNZ    BB_CH
        RET

SRCBASE:
        DW      0
