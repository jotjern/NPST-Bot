# NPST Bot

Dette prosjektet er en discord-bot som gir henter informasjon fra PST sin jule-CTF (oppgaver, informasjon etc.). Den kan bl.a lese inboxen på [dass](https://dass.p26e.dev) og sende dette i en kanal. Botten inneholder også modereringsfunksjoner som å automatisk slette CTF-flagg som sendes og å rydde alle kanaler som heter "cryptobins" for alle meldinger som ikke inneholder lenker til cryptobin.

## Oppsett
* Kopier example-config.yaml til config.yaml
* Finn API-keyen til dass.p26e.dev (kan finnes i chrome devtools i en request til api-et)
* Sett inn en bot key (kan finnes på [discord developer portal](https://discord.com/developers))
* Skriv inn brukernavn og passord til en bruker. Her anbefaler jeg å lage en egen en for botten, fordi da vil den ikke lekke mailer som ikke alle får
* Kopier ID-en til en discord-kanal og legg den i mail-cannel
* Skriv inn en mail-check-delay
