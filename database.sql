CREATE TABLE characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    char_id INTEGER DEFAULT 1,
    text TEXT NOT NULL,
    creator_id TEXT NOT NULL,
    created INTEGER NOT NULL,
    deletor_id TEXT,
    deleted INTEGER
);
CREATE TABLE character_pictures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    char_id INTEGER DEFAULT 1,
    picture_filename TEXT NOT NULL,
    creator_id TEXT NOT NULL,
    created INTEGER NOT NULL,
    deletor_id TEXT,
    deleted INTEGER
);
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    creator_id TEXT NOT NULL,
    created INTEGER NOT NULL,
    deletor_id TEXT,
    deleted INTEGER
);
CREATE TABLE user_command_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    status TEXT NOT NULL,
    updated INTEGER NOT NULL
);
CREATE TABLE static_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    command TEXT NOT NULL,
    response TEXT NOT NULL,
    response_keyboards TEXT,
    alt_commands TEXT
);

INSERT INTO static_messages (command, response, response_keyboards, alt_commands) VALUES ('nur-vorlage', 'Basics:
Originaler Charakter oder OC?:

Vorname:
Nachname:
Rufname/Spitzname:
Alter:
Blutgruppe:
Geschlecht:

Wohnort:

Apparance

Größe:
Gewicht:
Haarfarbe:
Haarlänge:
Augenfarbe:
Aussehen:
Merkmale:

About You

Persönlichkeit: (bitte mehr als 2 Sätze)

Mag:
Mag nicht:
Hobbys:

Wesen:

Fähigkeiten:

Waffen etc:


Altagskleidung:

Sonstiges

(Kann alles beinhalten, was noch nicht im Steckbrief vorkam)', null, null);
INSERT INTO static_messages (command, response, response_keyboards, alt_commands) VALUES ('regeln', '*~RULES~*

1.
Kein Sex! (flirten ist OK, Sex per PN)

2.
Sachen die man tut: *......*
Sachen die man sagt: ohne Zeichen
Sachen die man denkt: //..... //
Sachen die nicht zum RP gehören (....)

3.
Es gibt 2 Gruppen:
Die öffentliche ist für alle Gespräche, die nicht zum RP gehören.
Die *REAL*RPG* Gruppe ist AUSSCHLIEẞLICH zum RPG zugelassen.

4.
Keine overpowerten und nur ernst gemeinte Charakter. (Es soll ja Spaß machen)

5.
RP Handlung:
Schön guten Abend, Seid ihr es nicht auch leid? Von jeglichen Menschen aus eurer Heimat vertrieben zu werden? Gejagt, verfolgt oder auch nur verachtet zu werden? Dann kommt zu uns! Wir bauen zusammen eine Stadt auf. Eine Stadt wo nur Wesen wohnen und auch nur Eintritt haben.

6.
Sei Aktiv mindestens in 3 Tagen einmal!

7.
Keine Hardcore Horror Bilder. (höchstens per PN wenn ihr es unter bringen wollt mit der bestimmten Person)

8.
Wenn du ein Arsch bist oder dich einfach nicht an die Regeln hältst wirst du verwarnt oder gekickt. Wenn es unverdient war schreib uns an.

9.
Übertreibt es nicht mit dem Drama.

10.
Wenn du bis hier gelesen hast sag ''Luke ich bin dein Vater'' Antworte in den nächsten 10 Min.', '["Charaktervorlage", "Hilfe", "Weitere-Beispiele"]', '["rules"]');
INSERT INTO static_messages (command, response, response_keyboards, alt_commands) VALUES ('quellcode', 'Der Quellcode dieses Bots ist Open-Source und unter der Apache License Version 2.0 lizensiert.
Der Quellcode ist zu finden unter: https://github.com/slideup-benni/rpcharbot', '["Hilfe"]', '["source", "sourcecode", "lizenz", "licence"]');
INSERT INTO static_messages (command, response, response_keyboards, alt_commands) VALUES ('hilfe', 'Folgende Befehle sind möglich:
Hilfe
Regeln
Vorlage
Hinzufügen (<username>) <text>
Ändern (<username>) (<char_id>) <text>
Verschieben <username_von> <username_nach> (<char_id>)
Bild-setzen (<username>) (<char_id>)
Anzeigen (<username>) (<char_id>|<char_name>)
Löschen <eigener_username> (<char_id>)
Letzte-Löschen <eigener_username> (<char_id>)
Suchen <char_name>
Berechtigen <username>
Liste
Würfeln (<Anzahl Augen>|<kommagetrennte Liste>)
Münze
Quellcode

Die Befehle können ausgeführt werden indem man entweder den Bot direkt anschreibt oder in der Gruppe ''@rpcharbot <Befehl>'' eingibt.
Beispiel: ''@rpcharbot Liste''

Der Parameter <char_id> ist nur relevant, wenn du mehr als einen Charakter speichern möchtest. Der erste Charakter hat immer die char_id 1. Legst du einen weiteren an, erhält dieser die char_id 2 usw.

Der Bot kann nicht nur innerhalb einer Gruppe verwendet werden; man kann ihn auch direkt anschreiben (@rpcharbot) oder in PMs verwenden.

Erläuterungen der Parameter:
<username>: Benutzername des Nutzers; beginnt immer mit @
<char_id>: Alle Charaktere eines Nutzers werden durchnummeriert. Es handelt sich um eine Zahl größer als 1
<char_name>: Name des Charakers ohne Leerzeichen', '["Regeln", "Kurzbefehle", "Weitere-Beispiele", "Charaktervorlage", "Quellcode"]', '["help", "?", "h", "hilfe!"]');
INSERT INTO static_messages (command, response, response_keyboards, alt_commands) VALUES ('admin-hilfe', 'Folgende Admin-Befehle sind möglich:
auth/Berechtigen <username>
unauth/Entmachten <username>
del/Löschen <username> (<char_id>)
del-last/Letzte-Löschen <username> (<char_id>)', '["rules", "Weitere-Beispiele", "Template"]', '["admin-help"]');
INSERT INTO static_messages (command, response, response_keyboards, alt_commands) VALUES ('hilfe2', 'Folgende Kurz-Befehle sind möglich:
help
rules
template
add (<username>) <text>
change (<username>) (<char_id>) <text>
move <username_from> <username_to> (<char_id>)
set-pic (<username>) (<char_id>)
show (<username>) (<char_id>|<char_name>)
del <eigener_username> (<char_id>)
del-last <eigener_username> (<char_id>)
search <char_name>
auth <username>
list
dice (<Anzahl Augen>|<kommagetrennte Liste>)
coin
source', '["rules", "Weitere-Beispiele", "Template"]', '["help2", "kurzbefehle"]');