# Sicherheit

Das Plugin greift auf den Regler einer Heizungsanlage zu und kann dort Werte schreiben. Sicherheitsprobleme
bitte **nicht** als öffentliches Issue melden, sondern vertraulich:

- über **GitHub → Security → Report a vulnerability** (private Meldung), oder
- per E-Mail an **cr0ssn0tice@proton.me**.

Bitte beschreiben: betroffene Version, Weg zum Nachstellen, mögliche Auswirkung. Eine erste Antwort gibt es
in der Regel innerhalb weniger Tage; nach einer Korrektur wird die Lücke im CHANGELOG genannt.

Im Rahmen sind insbesondere: die Weboberfläche (`webfrontend/`), die lokale API des Dienstes, die
MQTT-Befehle, der Umgang mit Zugangsdaten und die Installations- und Deinstallationsskripte.
Außerhalb: der Ochsner-/Siemens-Regler selbst und der LoxBerry-Kern.

Wie das Plugin den Regler und die Zugangsdaten schützt, steht in [docs/sicherheit.md](docs/sicherheit.md).
