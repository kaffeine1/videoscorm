# Video SCORM / H5P 0.3.0

Generatore locale per nuove videolezioni: esporta un MP4 con un editor qualsiasi e scegli tra uno ZIP SCORM 1.2 a SCO singolo e un pacchetto H5P tracciato. Entrambi i formati sono disponibili per singoli video e intere cartelle. Non sostituisce lezioni già pubblicate e non migra progressi preesistenti.

Il repository contiene sorgenti, test, istruzioni di build e le librerie H5P incluse. Installer, video, pacchetti generati, note di interventi in produzione e dati utente restano fuori dal controllo versione. La cartella `dist` viene creata dal build locale.

## Preparare il video

- Esporta MP4 H.264 con pixel format yuv420p, audio AAC (oppure senza audio), con durata almeno un secondo. Per un avvio rapido sul web, usa l'opzione `faststart` dell'editor quando disponibile. Un MP4 HEVC/H.265 viene rifiutato: la riproduzione nel browser non è sufficientemente uniforme.
- Il titolo proposto viene dal tag `title` del file, se presente; altrimenti dal nome del file. **Controllalo e correggilo prima di creare il pacchetto**. Questa versione non legge il testo delle slide all'interno del filmato.
- Il programma non modifica il video originale. Il video viene copiato nel pacchetto senza ricompressione.

## Windows

Il pacchetto pronto per la prova è `dist/VideoSCORM-0.3.0-Windows.zip`. Estrailo e avvia `VideoSCORM-0.3.0-Setup-x64.exe` su Windows 10/11 a 64 bit. L'installer è offline, include Python e ffprobe, installa nel profilo dell'utente e crea collegamenti sul desktop e nel menu Start. La disinstallazione è disponibile nelle impostazioni delle app di Windows. Il Setup aggiorna una precedente installazione nella stessa cartella, senza intervenire sugli MP4 originali o sui pacchetti salvati nelle cartelle dell'operatore.

**Non caricare `VideoSCORM-0.3.0-Windows.zip` in Moodle:** è l'archivio dell'installer, non una lezione. Carica solo il pacchetto prodotto da **Crea pacchetto** o **Crea tutti**: `lezione_scorm.zip` nell'attività **Pacchetto SCORM**, oppure `lezione_h5p.h5p` nell'attività **H5P**. I campioni di quattro secondi sono `dist/VideoSCORM-Lezione-di-prova_scorm.zip` e `dist/VideoSCORM-Lezione-di-prova_h5p.h5p`.

Al termine vengono provate l'interfaccia Tkinter e la creazione dei pacchetti dal video campione incluso. Il log è `%LOCALAPPDATA%\VideoSCORM\logs\installation.log`. Il programma può essere avviato dal collegamento **Video SCORM**. Il collaudo dell'installer aggiornato sul PC Windows resta da eseguire.

Per avviare direttamente dai sorgenti:

1. Installa Python 3 per Windows, con `tkinter`, e ottieni `ffprobe.exe` da una distribuzione FFmpeg attendibile.
2. Avvia `python gui.py`. Se `ffprobe.exe` non è nel `PATH`, selezionalo nella finestra.
3. Scegli **SCORM 1.2** oppure **H5P**, seleziona il video, correggi il titolo, scegli il pacchetto, la frequenza di salvataggio (15/30/60 secondi) e la ripresa automatica.
4. Premi **Crea pacchetto**. Un file esistente richiede conferma prima della sostituzione.

Per produrre un eseguibile Windows, installa PyInstaller su Windows (`python -m pip install pyinstaller`) ed esegui:

```powershell
.\build_windows.ps1 -FfprobePath C:\percorso\ffprobe.exe
```

L'eseguibile risultante è `dist\VideoSCORM.exe`. Questo build PyInstaller è alternativo all'installer con runtime incluso; non è necessario per usare il Setup.exe già preparato.

L'installer si può ricompilare anche su macOS con `python3 build_installer.py`, avendo NSIS (`makensis`) e FFmpeg disponibili. Le dipendenze sono fissate in `installer_dependencies.json` e verificate tramite SHA-256 prima del packaging. Il contenuto installato è descritto in `build-info.json`.

## Riga di comando

```bash
python builder.py video.mp4 lezione_scorm.zip --title "Titolo corretto" --checkpoint 30
python builder.py video.mp4 lezione_h5p.h5p --format h5p --title "Titolo corretto" --checkpoint 30
```

Il formato predefinito resta SCORM. `--no-resume` disabilita il posizionamento automatico, non il salvataggio dello stato. `--force` sostituisce un pacchetto esistente. Per l'automazione usa `--ffprobe` se l'eseguibile non è nel `PATH`.

## Creazione massiva

Scegli il formato e, nella scheda **Cartella**, la cartella degli MP4 e la destinazione dei pacchetti. **Crea tutti** legge automaticamente i video e genera un pacchetto indipendente per ciascuno. **Leggi cartella** permette di verificare in anticipo i titoli proposti e di correggerli con **Modifica titolo** prima della generazione. Sono riconosciute anche estensioni come `.MP4`. Cambiare formato invalida il piano precedente e richiede una nuova lettura.

- I titoli sono ricavati dagli stessi metadati o nomi file della creazione singola. Ogni video viene nuovamente verificato prima della creazione.
- **Includi sottocartelle** conserva il percorso relativo nella destinazione, evitando collisioni tra lezioni di moduli diversi. I link simbolici e la cartella di output annidata nell'input vengono esclusi dalla ricerca.
- La creazione è sequenziale: un solo video copiato alla volta, senza caricare il filmato intero in memoria e senza modificare gli originali.
- I pacchetti esistenti sono saltati per impostazione predefinita. **Sostituisci pacchetti esistenti** richiede una conferma. Ogni pacchetto è scritto in un file temporaneo e sostituito solo dopo la verifica di integrità. I formati hanno suffissi distinti e possono convivere nella stessa destinazione.
- **Interrompi** lascia terminare il file in corso e non avvia i successivi. I pacchetti creati restano disponibili; rilanciando l'operazione con la politica predefinita vengono saltati.
- Il report `VideoSCORM-report-*.csv`, UTF-8 con BOM e separatore `;`, è scritto progressivamente nella cartella di destinazione ed è apribile in Excel. Riporta percorso, titolo, esito, errore e secondi impiegati per ogni video, inclusi quelli non elaborati dopo un'interruzione. I titoli che potrebbero essere interpretati come formule sono protetti nel CSV, senza modificare il titolo reale dello SCORM.

Per l'automazione senza interfaccia:

```bash
python batch.py /cartella/video /cartella/pacchetti --recursive --checkpoint 30
python batch.py /cartella/video /cartella/pacchetti --format h5p --recursive --checkpoint 30
```

Le opzioni `--ffprobe`, `--no-resume` e `--force` hanno lo stesso significato della creazione singola. L'output standard contiene un riepilogo JSON; l'avanzamento viene scritto sull'output degli errori. Codice di uscita `0` senza errori, `1` per errori su singoli video o interruzione durante la creazione, `2` per un piano non valido o una lettura preliminare interrotta. `Ctrl+C` richiede l'interruzione tra un file e il successivo.

La modalità massiva prepara i pacchetti locali: **non carica automaticamente attività in Moodle e non sostituisce lezioni già pubblicate**.

## Comportamento del player SCORM

- Il cursore resta libero; lo spostamento non conta come visione. Il completamento richiede la copertura di tutte le porzioni temporali della lezione.
- Dalla 0.2.1 la riproduzione effettiva conta anche quando la pagina passa in background: la visibilità del browser non è usata come prova di ascolto o visione. Pause, salti e avanzamenti incompatibili con il tempo trascorso restano esclusi. L'avvio viene ancorato prima del primo frame per non perdere il primo secondo se l'evento `playing` arriva in ritardo.
- La posizione e una mappa compatta delle porzioni viste sono salvate in `cmi.core.lesson_location` e `cmi.suspend_data` (entro il limite SCORM 1.2 di 4096 caratteri). Il player invia `cmi.core.lesson_status=completed` solo alla copertura completa.
- Non invia `cmi.core.score.raw`: il voto resta materia di un quiz separato. Non appare alcuna finestra di ripresa bloccante.
- Il salvataggio è tentato periodicamente, alla pausa, alla chiusura e al completamento. Se Moodle non conferma il salvataggio, compare un avviso. Un browser non può garantire il salvataggio se la pagina viene terminata di colpo o la rete cade prima del checkpoint.
- La copertura deriva dagli eventi del browser: non è una prova di attenzione umana. Pause e salti possono richiedere di rivedere una porzione parziale; il sistema preferisce non assegnare completamenti non dimostrati.

## Collaudo prima della produzione

1. Carica lo ZIP **della lezione** in **un corso di prova**, senza sostituire attività esistenti, tramite **Aggiungi attività > Pacchetto SCORM**. In Moodle imposta il criterio di completamento dell'attività su stato SCORM completato, non su semplice visualizzazione; non attribuire voto al video.
2. Prova riproduzione completa, pausa/ripresa, cambio scheda con video in riproduzione, logout/login, refresh, avanzamento manuale fino alla fine e rete momentaneamente assente in Chrome, Edge e Safari. Controlla report SCORM e record dei tentativi, non solo il badge grafico.
3. Confronta la catena di prerequisiti e il completamento del corso su un utente di prova. Solo dopo una prova reale approvare il caricamento di nuove lezioni.

## H5P: tracciamento e limiti

Il pacchetto include il nuovo tipo **H5P.LumTrackedVideo 1.0**, che usa il player ufficiale **H5P.Video 1.6.66** e mantiene la copertura temporale V1 del player SCORM. Non è il semplice video H5P standard: il cursore resta libero ma arrivare alla fine senza riproduzione non completa la visione. Non crea quiz e non assegna voti.

- Il primo import richiede un amministratore autorizzato a installare librerie H5P. La libreria personalizzata non è stata installata automaticamente sulle piattaforme. È inclusa nel file `.h5p`, insieme alla dipendenza ufficiale e alla sua licenza MIT. I diritti sui video non vengono cambiati.
- Posizione e copertura vengono conservate tramite lo stato utente H5P. Su Moodle occorre abilitare **Salva lo stato del contenuto** per l'attività H5P. Il salvataggio di stato usa richieste asincrone: la richiesta non è una conferma di persistenza e chiudere bruscamente il browser può perdere gli ultimi secondi.
- Alla copertura completa viene emesso un evento xAPI `completed`, con durata della riproduzione e senza `score` né voto accademico. I checkpoint parziali non emettono eventi finali e non creano tentativi completi aggiuntivi. Uno stato già completo non reinvia automaticamente il completamento alla riapertura.
- **Reinvia completamento** è un recupero manuale quando il report non registra il risultato; può creare un altro tentativo nel report Moodle. Il player non può certificare da solo che il server abbia registrato l'evento: controllare sempre il report.
- **Il completamento nel report dei tentativi H5P non equivale automaticamente al completamento dell'attività Moodle o allo sblocco dei prerequisiti.** Non usare la semplice visualizzazione come prova di visione completa e non inventare un voto per aggirare il problema. Una futura integrazione deve collegare esplicitamente il completamento xAPI alle regole del corso e va collaudata separatamente.
- Il formato è stato validato in sola lettura con il core H5P 1.27 della Moodle 4.5.10 operativa. Il player è provato localmente; il caricamento come attività, la persistenza su utenti Moodle e le catene di completamento devono ancora essere collaudati in un corso di prova, senza sostituire attività esistenti.

Per il collaudo H5P: importa il campione come amministratore in **Aggiungi attività > H5P**, verifica il salvataggio dello stato, poi usa un discente di prova per riproduzione completa, pausa/riapertura, salti, cambio scheda e interruzione della rete. Confronta stato ripreso, singolo evento finale e report dei tentativi. Non considerare verificati i prerequisiti del corso solo perché il video mostra 100%.

Riferimenti: [specifica dei pacchetti H5P](https://h5p.org/documentation/developers/h5p-specification), [attività H5P Moodle e report](https://docs.moodle.org/501/en/H5P_activity), [sorgenti ufficiali H5P.Video inclusi](https://github.com/h5p/h5p-video/tree/de2a4bdc1ed891cb2183445ec9246b4a73150978).

## Test locali

`python -m unittest test_builder.py test_batch.py test_h5p.py`, `node test_player.cjs` e `node test_h5p_player.cjs`. La suite massiva include una prova con MP4 reali quando `ffprobe` e il campione del build sono disponibili. I test dell'interfaccia richiedono Tk e un desktop funzionante e si abilitano esplicitamente con `VIDEOSCORM_GUI_TESTS=1 python -m unittest test_gui.py` (su PowerShell impostare prima `$env:VIDEOSCORM_GUI_TESTS='1'`). La prova browser opzionale `node test_h5p_browser.cjs` richiede il core H5P 1.27 e Playwright nell'area QA ignorata dal build. Questi test non sostituiscono il collaudo Windows o Moodle.

Le note operative dei singoli interventi in produzione vengono conservate localmente, fuori dal repository. Non fanno parte del programma né autorizzano modifiche alle piattaforme.
