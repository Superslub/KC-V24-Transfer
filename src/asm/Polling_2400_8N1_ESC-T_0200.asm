; Stub, der auf Kanal 2 des M003 in Slot 8 eine Duplex-Routine mit 2400 Baud anbietet
; Nach seinem Start wartet der Stub wie CAOS-Duplex auf ESC-T
; -> 1B 54 <adrL> <adrH> <lenL> <lenH> <Daten... len Bytes>
; um die empfangenen Daten in den Spreicher zu schreiben
; Er kehrt danach zurück und schaltet die "normale" CAOS-Duplex-Routine (1200 Baud) wieder ein
;
; der Stub kann initial mit der CAOS-Duplex-Routine per ESC-T an seine Adresse 
; geladen werden und per ESC-U gestartet werden.
;
; Vor dem ESC-T an den Stub muss die Datenrate der Gegenstelle auf 2400 Baud gestellt werden.
; Nach der Datenübertragung muss die Gegenstelle zurück auf 1200 Baud schalten, 
; um in diesem Modus bspw. den per Stub geladenen Code zu starten

        ORG     0200h

START:  ; vollständige Registersicherung (inkl. Shadow + IX/IY)
        PUSH    AF
        PUSH    BC
        PUSH    DE
        PUSH    HL
        PUSH    IX
        PUSH    IY

        EX      AF,AF'
        PUSH    AF
        EXX
        PUSH    BC
        PUSH    DE
        PUSH    HL
        EXX
        EX      AF,AF'

        DI                      ; kein EI am Ende (Stub läuft im CAOS-ISR-Kontext)

        CALL    SETRUN          ; RUN-Konfig
        CALL    RECV_ESCT       ; ESC 'T' empfangen und an Zieladresse schreiben
        CALL    SETCAOS         ; zurück auf CAOS-Konfig

        ; vollständige Registerwiederherstellung (umgekehrte Reihenfolge)
        EXX
        POP     HL
        POP     DE
        POP     BC
        EXX

        EX      AF,AF'
        POP     AF
        EX      AF,AF'

        POP     IY
        POP     IX
        POP     HL
        POP     DE
        POP     BC
        POP     AF
        RET

; Protokoll: 1B 54 <adrL><adrH><lenL><lenH><daten...>
RECV_ESCT:
WAIT_ESC:
        CALL    GETBYTE
        CP      1Bh
        JR      NZ,WAIT_ESC
        CALL    GETBYTE
        CP      54h             ; 'T'
        JR      NZ,WAIT_ESC

        CALL    GETBYTE         ; adrL
        LD      L,A
        CALL    GETBYTE         ; adrH
        LD      H,A

        CALL    GETBYTE         ; lenL
        LD      C,A
        CALL    GETBYTE         ; lenH
        LD      B,A

LOOP:   LD      A,B
        OR      C
        RET     Z

        CALL    GETBYTE
        LD      (HL),A
        INC     HL
        DEC     BC
        JR      LOOP

; DART-B Status (0Bh) pollen, bei RX-ready Daten aus 09h lesen
GETBYTE:
        IN      A,(0Bh)
        BIT     0,A
        JR      Z,GETBYTE
        IN      A,(09h)
        RET

; --- Konfigurationen (Tabellen + OTIR) ---

SETRUN: LD      HL,RUN_CTC
        CALL    APPLY_CTC
        LD      HL,RUN_SIO
        CALL    APPLY_SIO
        RET

SETCAOS:
        LD      HL,CAOS_CTC
        CALL    APPLY_CTC
        LD      HL,CAOS_SIO
        CALL    APPLY_SIO
        RET

APPLY_CTC:
        LD      C,0Dh
        LD      B,2
        OTIR
        RET

APPLY_SIO:
        LD      C,0Bh
        LD      B,0Bh
        OTIR
        RET

; Tabellen (wie zuletzt)
RUN_CTC:  DB 47h,17h
RUN_SIO:  DB 18h,02h,E2h,14h,44h,03h,E1h,05h,EAh,11h,18h

CAOS_CTC: DB 47h,2Eh
CAOS_SIO: DB 18h,02h,E2h,14h,44h,03h,E1h,05h,EAh,11h,18h
