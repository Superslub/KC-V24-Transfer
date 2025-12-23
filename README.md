# KC-V24-Transfer

	
Aktuelle Version herunterladen: [KC-V24-Transfer.exe](https://github.com/Superslub/KC-V24-Transfer/raw/refs/heads/main/dist/KC-V24-Transfer.exe)

***Wozu dient das Programm?***

 Mit dem Programm gelingt es mit technischem Minimalaufwand und ohne großes Vorwissen Programme auf einen echten KC zu laden und zu starten. Auch kann die PC-Tastatur als KC-Tastaturersatz genutzt werden. So kann man mit einem KC-Grundgerät und einem M003 ohne Verrenkungen bereits echtes KC-Feeling erleben.

<div align="center">
<img width="322" height="224" alt="app1" src="https://github.com/user-attachments/assets/dad0a225-92d0-49c1-aced-d01b194510c1" />
&nbsp;&nbsp;&nbsp;&nbsp;
<img width="322" height="224" alt="app2" src="https://github.com/user-attachments/assets/bc4eb4e8-1877-44fa-9c2a-3eed4d31b2f0" />
<br/><br/>
</div>  

     
***Wie benutzt man das Programm***
 
 Das Programm überträgt KC-Programmdateien geläufiger Formate automatisch auf den KC und startet diese dort.
 So können Spiele und -Anwenderprogramme auf original KC-Hardware ohne Umwege zum Laufen gebracht werden.
  
***Was das Programm NICHT kann:***

 - Rückkanal: Das Programm kann keine Daten vom KC auf den PC rückübertragen
 - schnelle Datenübertragung: das genutzte Verfahren zur Datenübertragung ist ziemlich langsam
 - funktioniert nur mit KC85/4

***Was benötigt man zur Nutzung? (technische Voraussetzungen)***

 - M003 - V.24-Modul (KC)
 - COM-Port (PC) (z.B. via USB-COM-Portadapter)
 - serielles Kabel zwischen KC(DIN 5polig) <==> PC (D-SUB 9polig) - siehe Kapitel "Serielles Kabel selber bauen"
 - KC-Programme zum Laden (aus dem Netz, z.B. .KCC, .KCB, .SSS oder .BAS-Dateien)

# Nutzungshinweise
	
## Vorbereitung (Hardware)

 1. M003 muss im Grundgerät gesteckt sein
 2. das Serielle Kabel muss in Anschluss "K2" des M003 stecken (rechte Buchse)
 3. am PC muss das Kabel mit einem freien COM-Port verbunden sein

## Programmbedienung

 1. ***COM-Portauswahl***: Hier wird der Serielle Port für die Verbindung gewählt. Bereits belegte serielle Anschlüsse (ausgegraut) können nicht gewählt werden.

 2. ***Datei Laden***: Hier wird die Datei mit den auf den KC zu übertragenden Programm/Daten ausgewählt und ins Programm geladen. Wenn das Dateiformat eingelesen werden konnte, erscheint in der Statusanzeige "Bereit zur Datenübertragung" sowie da erkannte Datei- und Datenformat 

 3. ***Übertragen***: Damit wird der Dateiinhalt mit allen notwendigen Zusatzinformationen auf den KC übertragen. Vor einer Übertragung muss der KC in der Regel per RESET zurückgesetzt werden. Während der Übertragung zeigt der KC keine Meldung oder Bildänderung.
 *Achtung:* Während die Übertragung läuft, darf die Tastatur des KC nicht benutzt werden!
 Bei der Übertragung von Binärdaten zeigt der KC sein Einschaltbild.
 Textdaten (z.B. BASIC-Programme) werden als "virtuelle Tastatureingaben" übertragen - Auf dem KC-Bildschirm ist dabei der Programmtext bei seiner Übergabe zu beobachten.
 Wenn die Übertragung abgeschlossen ist, fragt das Programm (wenn möglich), ob das übertragene Programm auf dem KC gestartet werden soll. 

 4. ***Tastaturmodus***: Nach der Programmübertragung(*) wird der KC in den Tastaturmodus geschaltet. Sofern das KC-V24-Transfer aktiv ist, werden alle Tastatureingaben am PC an den KC übertragen. Ist der Modus eingeschaltet, kann auch der Inhalt der Zwischenablage vom PC an den KC übertragen werden. Entweder über die Tastenkombination "```Strg+-V```" im Programmfenster oder das Kontextmenü (siehe unten "Tastaturmodus")

 (* wird ein Binärprogramm übertragen und im Anschluss nicht gestartet, wird der  Tastaturmodus nicht eingeschaltet - kann aber nachträglich manuell eingeschaltet werden.)
 

#### Besonderheiten BASICODE:
Für Basicode-Programme wird automatisch der Bascoder (v1.5) vorgeladen und gestartet. Wird direkt nach einem BASICODE-Programm ein weiteres BASICODE-Programm übertragen, muss der BASICODER nicht noch einmal übertragen werden.


#### Besonderheiten des Tastaturmodus:
Der KC bietet die Möglichkeit, an der V-24-Schnittstelle eine Tastatur zu nutzen. Dafür muss der KC in den Tastatur-Modus umgeschaltet werden. Der Tastaturmodus wird nach dem Übertragen eines Programmes automatisch aktiviert, wenn das Programm mit KC-V24-Transfer auch gestartet wird oder ein BASIC-Programm übertragen wurde.
Wenn der Tastaturmodus eingeschaltet ist, wird dieser in KC-V24-Transfer als "aktiv" dargestellt (Schalterfeld oben rechts).

 - Aktivierung des Tastaturmodus:
   - wird nach der Übertragung eines Programmes automatisch eingeschaltet
   - wird beim Einfügen aus der Zwischenablage automatisch gestartet
   - Ein *Klick* auf das Schalterfeld startet den Tastaturmodus
   - *Doppelklick* sendet Aktivierungs-Codes für den Tastaturmodus nochmals an den KC (nützlich, nachdem der KC resetted wurde)
   - Tastaturübertragung funktioniert nur, wenn das Programmfenster den Fokus hat (also aktiv ist -> ins Fenster klicken!)
   
 - Tastaturmodus ausschalten: Durch Klick auf den Tastaturschalter kann der Tastaturmodus deaktiviert werden.
 
 - Während laufender Datenübertragungen ist der Tastaturmodus gesperrt.

 - __Achtung:__ Es gibt (selten) auch Programme, die die Duplexroutine ausschalten. In diesem Fall funktioniert die "Ferntastatur" nicht.

 - Einfügen aus der Zwischenablage 
   - ***Code (Strg+V)***: Zur Übertragung von BASIC-Listings per Zwischenablage. Der Inhalt wird zeilenweise an den BASIC-Prompt übergeben - Nach jeder Zeile wird eine angemessene Pause vor der übertragung der nächsten Zeile eingelegt.
   - ***Text (Umschalt+Strg+V)***: Inhalt wird einfach "rausgeschrieben"
   Am PC erstellte und bearbeitete BASIC-Listings können also einfach per Strg-V an einen laufenden BASIC-Prompt am KC übertragen werden.
   
 
 - Zeichenkodierung/Steuertasten 
   - der KC hat als Standardtastenbelegung GROßBUCHSTABEN, diese "Funktion" wird auch auf die PC-Tastatur übernommen. Groß- und Kleinbuchstaben sind also vertauscht.
   - Steuertastenmapping (Kurzübersicht):
     ESC         -> BRK
	 Entf        -> DEL
	 BackSpace   -> CursorLinks + DEL
     Insert      -> EINF +INS
	 Pause       -> STOP
     Home (Pos1) -> HOME
	 F1-F12      -> F1-F6 + Shift-(F1-F6)
     
   
#### Manuelles Starten von Programmen

Wurde ein Programm übertragen und nicht automatisch gestartet, so kann das Programm folgendermaßen manuell gestartet werden:

 - ***BASIC/BASICODE-Programme***: Geben sie am Befehlsprompt des BASIC-Interpreters (">") den Befehl "RUN" ein und drücken sie "ENTER"
 
 - ***CAOS-Programme***: Geben sie im CAOS-Menü "%MENU" ein und drücken "ENTER". Daraufhin baut sich das Menü neu auf und es erscheint darin ein neuer Eintrag mit dem Programmnamen. Navigieren sie mit den Cursortasten in die Zeile des neuen Programmnamens und drücken sie "ENTER"

----

# Technische Hintergründe

## Duplexroutine (mit Empfangsinterrupt) des M003 mit CAOS 4.2

Es werden dabei vom KC-CAOS 4.2 standardmäßig bereitgestellte Übertragungsmechanismen genutzt:
Bei vorhandenem M003-Modul wartet KC-CAOS nach einem RESET automatisch auf Datenübertragungen.
Dabei gibt es zwei grundsätzliche Modi:
- Binärübertragung (ESC-T, „Polling“)
  – CAOS stellt einen ESC-T-Lader bereit, der über V.24 Binärdaten byteweise in einen Speicherbereich lädt.
  – Der KC fragt („pollt“) den V.24-Empfangspuffer ab und übernimmt jedes empfangene Byte direkt in den RAM.
  – Im ESC-T-Header werden Startadresse und Programmlänge angegeben; anschließend werden genau so viele Bytes übertragen wie dort eingetragen sind.

- Tastatur-Übertragung („Tastaturersatz“)
  – Im V.24-Interruptmodus werden empfangene Zeichen wie Tastatureingaben behandelt.
  – Durch die Übertragung werden am KC also "Tastatureingaben" erzeugt
  
Ist der Modus einmal auf "Tastatur" umgeschaltet, kann der Polling-Modus erst nach einem RESET wieder aktiviert werden (leider)

### Schnelllader - Polling-Routine

KC-V24-Transfer beschleunigt die Übertragung von Binärdateien durch eine eigene ESC-T-protokollkompatible Empfangsroutine ("Schnelllader"). Der Code dieser Routine wird von KC-V24-Transfer via CAOS-Polling in einen vom später zu ladenden Programm unbelegten Speicherbereich vorgeladen und gestartet. Der Schnellader schaltet die CAOS-Duplexroutine ab, konfiguriert die Schnittstellengeschwindigkeit auf 2400 Baud und lädt das gewünschte Programm in den Speicher. Nach Abschluss der Übertragung wird die Schnittstellengeschwindigkeit wieder auf 1200 Baud zurückgeschaltet und die CAOS-Duplexroutine wieder eingeschaltet (um. z.B. wieder in den Tastaturmodus gelangen zu können).

Warum keine höheren Übertragungsraten? Obwohl der in der Schnittstelle verbaute DART/CTC theoretisch auch höhere Übertragungsraten als 2400 Baud zulässt, kommt es bei höheren Datenraten im verwendeten asynchronen Modus (8N1) zu Übertragungsfehlern ("Bits kippen"). Das ist wahrscheinlich dem für die Baudraten etwas "schrägen" Grundtakt des KC geschuldet, der von den Schnittstellenbausteinen in den Modi oberhalb 2400 Baud als Referenztakt genutzt wird (CTC läuft für diese Modi nicht mehr im Timermodus, sondern im Countermodus). Daher können diese Modi oberhalb von 2400 Baud nur zur Kopplung von zwei Systemen gleichen Grundtaktes effektiv genutzt werden (z.B. Kopplung KC<->KC).

Die Nutzung der Schnelllader-Routine kann über einen Eintrag in der KC-V24-Transfer-Konfigurationseintrag abgeschaltet werden. Die Konfigurationsdatei liegt unter Windows im lokalen Benutzerprofilverzeichnis unter

```%LOCALAPPDATA%\KC-V24-Transfer\KC-V24-Transfer.ini```

Ein dortiger Eintrag ```use_turboload = False``` unter ```[serial]``` schaltet den Schnelllader ab.

## Speicherformate

- KCC
	- Header mit Anfangs und Endadresse, optional Einsprungadresse, Programmname 
	- Auffüllungen auf vollen 128kB-Block

- KCB
	- wie KCC, nur mit BASIC-Programm
    - Endbytes des BASIC-programmes 00h 00h 00h 03h
	- Auffüllungen auf vollen 128kB-Block

- SSS (Floppy/Disk)
  - kurzer Header (ohne Programmname), Auffüllungen auf 128kB
  - Endbytes des BASIC-programmes 00h 00h 00h 03h
  - Auffüllungen auf vollen 128kB-Block

- SSS (TAPE/Kassette)
  - langer Header (inkl. Programmname) + Blocknummern im Datenstrom
  - Endbytes des BASIC-programmes 00h 00h 00h 03h
  - Auffüllungen auf vollen 128kB-Block

- TEXT/BAS/ASC
  - einfache Textdateien in 8Bit-Kodierung, die die BASIC-Programmliste enthalten
  - können auch in einfachen Texteditoren eingesehen werden

### Datenformate

- ***Speicherabzug***
  - Daten eines Speicherbereichs - zur Wiederherstellung wird Anfangsadresse benötigt - zum Starten eine Einsprungadresse
  - CAOS-Menüeintrag (Prologbytes -> hier neben Name auch Einsprungadresse)
  - Anfangsadresse häufig 0300h
  - können im Polling-Modus mit 1200 Baud übertragen und gestartet werden
  
- ***Tokenisierte BASIC-Programme***
  - interne Form der Programme, wie sie der BASIC-Interpreter per CSAVE und FSAVE ablegt in Form eines Speicherabzugs (meist ab 0401h)
  - beim Einlesen werden die Daten vom _BASIC-Interpreter_ verarbeitet (Variablen bekommen z.B. ihre Speicheradresse etc.)
  - stumpf per CAOS LOAD zurückgeschriebene Speicherabbilder können deshalb in der Regel nicht (per %REBASIC->RUN) gestartet werden
  - KC-V24-Transfer enthält deshalb einen Rückkonvertierer (Detokenizer), der die tokenisierten Programmzeilen aus dem Speicherabbild extrahiert und zurück in textliche BASIC-Programmlistings konvertiert, um sie so (zeilenweise) am BASIC-Prompt in den BASIC-Interpreter zu laden. Die vom KC-V24-Transfer erzeugten BASIC-Listings werden für eine beschleunigte Übertragung in einem möglichst kompakten Format erzeugt.
  
- ***Textliche BASIC-Programmlistings***
  - einfache Textdaten mit den Programmzeilen, wie man sie auch beim Programmieren im BASIC-Interpreter eingibt
  - können im Tastaturmodus nur sehr langsam übertragen werden
  - jede Zeile wird dabei an den BASIC-Prompt übertragen und nach einem <ENTER> vom BASIC-Interpreter tokenisiert und gespeichert
  - können nach Übertragung per RUN aus BASIC heraus gestartet werden
  - eine Besonderheit stellen BASICODE-Programme dar: Das sind BASIC-Programme, die für ihren Start ein zusätzlich vorher geladenes und gestartetes "Basicoder"-Programm benötigen.


### Übertragung per Tastaturmodus

 Der Transfer im Tastaturmodus ist per se sehr langsam. Die Übertragung einen Klartext-Programmlistings erfolgt so:
 1. Jede Zeile wird "eingegeben" und per Return an dem BASIC-Interpreter zu übergeben
 2. Erst nach Verarbeitung durch den Interpreter kann mit der Eingabe der nächsten Zeile begonnen werden
 3. Die Verarbeitungszeit variiert dabei stark, je nach übergebenen Zeileninhalt
 
 Die unterschiedliche Zeilendaten-Verarbeitungszeit wird dabei von KC-V24-Transfer beachtet: Befehlszahl, Variablenreferenzen und Feldvariablenerstellung und -zugriffe werden berechnet und die Wartezeit entsprechend angemessen, um die Übertragung zu beschleunigen.
 
### Serielles Kabel selber bauen

Das benötigte serielle Kabel kann man sich leicht selbst fertigen. Wichtig ist, die Steckerbelegungen (Pinnummern am Stecker/Buchse) korrekt zu recherchieren und zu beachten

Verbindungskabel  DIN 5-polig (KC V.24) <-> SUB-D (PC RS-232):

```
KC/M003.K2 (DIN 5polig)      PC (D-SUB 9polig)
Anschluss Nr                  Anschluss Nr
RxD       1   ------<------   TxD       3
Masse     2   -------------   Masse     5 (und Gehäuse)
TxD       3   ------>------   RxD       2
CTS       4   ------<------   RTS       7
DTR       5   ------>------   CTS       8
```               
Optional können im D-SUB Stecker die Anschlüsse DTR(4),DSR(6) und DCD(1) gebrückt werden

---
***Danksagung***

Dank für die Inspiration geht an E.Müller und sein "KC-Senden" von 2008.
