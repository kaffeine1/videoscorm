Video SCORM / H5P 0.3.0 - Windows 10/11 a 64 bit

English: README-Windows.txt

INSTALLAZIONE
Scarica l'installer da:
https://github.com/kaffeine1/videoscorm/releases/tag/v0.3.0
VideoSCORM-0.3.0-Windows.zip contiene l'installer del programma.
Non caricarlo in Moodle: non è una lezione.
Estrai prima questo archivio sul computer Windows.
Apri VideoSCORM-0.3.0-Setup-x64.exe e segui la procedura.
Python e ffprobe sono inclusi. Non occorre installarli separatamente.
Al termine viene eseguita una prova locale di funzionamento.
Il programma è disponibile sul desktop e nel menu Start come "Video SCORM".
Se hai già installato la versione precedente, il nuovo Setup la aggiorna.
I tuoi MP4 originali e i pacchetti salvati fuori dalla cartella del programma
non vengono modificati dall'aggiornamento.

PRIMA PROVA
1. Apri Video SCORM.
2. Scegli SCORM 1.2 oppure H5P, poi seleziona un video MP4.
   Un piccolo video di prova è nella cartella di installazione, in app\sample.mp4.
3. Controlla il titolo proposto e modificalo se necessario.
4. Scegli dove salvare il pacchetto e premi Crea pacchetto.
5. Carica solo il pacchetto generato: lezione_scorm.zip usando
   Aggiungi attività > Pacchetto SCORM, oppure lezione_h5p.h5p usando
   Aggiungi attività > H5P. Per il primo import H5P serve un amministratore
   autorizzato a installare la libreria personalizzata inclusa nel pacchetto.

CREAZIONE MASSIVA DA CARTELLA
1. Scegli il formato, apri la scheda Cartella e seleziona la cartella MP4.
2. Scegli la cartella di destinazione dei pacchetti.
   La destinazione proposta è la sottocartella Pacchetti dei video.
3. Se vuoi, abilita Includi sottocartelle. La struttura viene mantenuta
   nella destinazione per distinguere video con lo stesso nome.
4. Premi Leggi cartella per controllare i titoli proposti e gli errori.
   Seleziona una riga e premi Modifica titolo per correggerlo.
5. Premi Crea tutti. Puoi anche premere direttamente Crea tutti senza
   lettura preliminare: i titoli verranno ricavati automaticamente.
6. Al termine trovi un pacchetto indipendente per ogni MP4 e un report CSV,
   apribile in Excel, con il risultato di ciascun video.

I pacchetti già esistenti vengono saltati. Sostituisci pacchetti esistenti richiede
una conferma prima della creazione. Un video non valido viene segnalato
nel report e non blocca i successivi. Interrompi termina il file in corso
e lascia intatti i pacchetti già creati; gli altri risultano non elaborati.
I collegamenti simbolici non vengono seguiti.
Per Moodle carica i singoli pacchetti lezione, non la cartella o il report.

Esporta i tuoi video in MP4 H.264, pixel format yuv420p, audio AAC.
Il titolo viene dai metadati del file o dal nome del file.
Il completamento è basato sulle porzioni riprodotte, con navigazione libera.
Il player conserva la posizione senza mostrare una finestra Resume.
La versione 0.2.1 conta anche la riproduzione effettiva in background e
corregge la perdita del primo secondo quando l'evento di avvio è ritardato.
Una pausa o un salto con il cursore non contano come riproduzione.

La generazione del pacchetto è locale. Per verificare il tracciamento, carica il
pacchetto in un corso Moodle di prova e controlla il report del tentativo.

H5P: VERIFICHE IMPORTANTI
Il nuovo tipo H5P.LumTrackedVideo usa il player ufficiale H5P.Video 1.6.66.
Il completamento richiede la copertura temporale completa, non un salto
con il cursore alla fine. Non viene assegnato un voto al video.
Abilita il salvataggio dello stato del contenuto nelle impostazioni H5P.
Il salvataggio è asincrono: evitare di chiudere il browser bruscamente.
L'evento finale completed compare nei report H5P; non dimostra da solo
il completamento dell'attività Moodle o lo sblocco del modulo successivo.
Queste regole richiedono una configurazione o integrazione separata.
Reinvia completamento è un recupero manuale e può aggiungere un tentativo.
Il pacchetto è validato con il core H5P 1.27 della Moodle operativa;
la prova completa con discente e prerequisiti Moodle resta da eseguire.
Il programma non migra lezioni o progressi esistenti e non installa nulla
sulle piattaforme senza un import eseguito da un amministratore.

DISINSTALLAZIONE E DIAGNOSTICA
La disinstallazione è disponibile nelle impostazioni delle app di Windows.
I video originali e i pacchetti salvati nelle tue cartelle vengono conservati.
I log sono in %LOCALAPPDATA%\VideoSCORM\logs.
Il test di installazione è registrato in installation.log; gli errori di avvio
del programma sono registrati in app.log.
