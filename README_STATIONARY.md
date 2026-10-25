# Secondo laboratorio: transitorio e intervalli di confidenza

Il laboratorio richiede di riconoscere durante la simulazione la fine della
fase iniziale e di stimare le prestazioni con intervalli di confidenza (IC).
Il simulatore originale rappresenta una giornata con picchi e cambiamenti:
per studiare un regime stazionario servono invece condizioni esterne costanti.

## Eseguire lo studio

Richiede i file `taxi_simulation_v3.py`, `stationary_analysis.py` e
`taxi_stationary_lab.py` nella stessa cartella, con le dipendenze indicate in
`requirements.txt`.

```bash
python3 -m pip install -r requirements.txt
python3 -B -m unittest -v
python3 -B taxi_stationary_lab.py
```

In Colab puoi clonare il ramo che contiene questo laboratorio:

```python
!git clone --branch feat/stationary-analysis https://github.com/robertomahamalimage-star/Computer-aided-simulations-lab.git
%cd Computer-aided-simulations-lab
%pip install -r requirements.txt
!python taxi_stationary_lab.py
```

Lo studio salva in `stationary_results/`:

| File | Contenuto |
| --- | --- |
| `confidence_intervals.csv` | Stime, estremi degli IC, semiampiezze e stati di validazione |
| `replications.csv` | Risultati delle singole repliche indipendenti |
| `pilots.csv` | Rilevamento del transitorio nei piloti e relativi seed |
| `detector_trace.csv` | Evoluzione del rilevatore, aggiornata durante ciascun pilota |
| `coverage_validation.csv` | Verifica della copertura su una coda con soluzione nota |
| `configuration.json` | Parametri, seed e versioni dei pacchetti usati |
| `precision.png` | Grafici degli IC e della loro precisione |
| `report.md` | Relazione in italiano con i risultati effettivamente ottenuti |

Per eseguire un solo caso, aumentare le repliche o scegliere una cartella diversa:

```bash
python3 taxi_stationary_lab.py --scenarios baseline --replications 40 --output-dir prova_40
```

Le opzioni `--pilots`, `--pilot-hours` e `--coverage-trials` cambiano il numero di
piloti, l'orizzonte massimo del controllo e gli esperimenti di verifica della
copertura. Non ridurre le repliche per ottenere artificialmente un risultato
favorevole. Le numerosità e le durate vanno fissate prima di osservare la produzione.

Il comando `python3 taxi_simulation_v3.py` continua a eseguire il primo laboratorio,
con gli stessi scenari giornalieri e i suoi due CSV. Non avvia lo studio stazionario.

## 1. Rendere stazionarie le condizioni esterne

Il nuovo parametro `stationary=True` rende costanti la domanda urbana per zona e
la velocità di base. Meteo e disponibilità del trasporto pubblico possono essere
costanti. I controlli rifiutano hub programmati, eventi, scioperi/disservizi
temporanei e ribilanciamento periodico, che introdurrebbero variazioni nel tempo.
La matrice origine-destinazione e le velocità a piedi restano invariate.

```python
from taxi_simulation_v3 import TaxiSimulation

sim = TaxiSimulation(
    stationary=True,
    include_hubs=False,
    rebalancing=False,
    fleet_size=20,
    duration_hours=72,
)
```

**Input costanti non garantiscono code stabili.** Se arrivano più richieste di
quante il servizio riesca a gestire, il transitorio potrebbe non finire mai.
Inoltre il simulatore parte con tutti i taxi parcheggiati e nessun passeggero:
anche un sistema stabile necessita di tempo per perdere l'effetto di questo avvio.

## 2. Rilevare il transitorio in tempo reale

`OnlineWarmupDetector.update()` riceve solo osservazioni già disponibili. Non
usa il futuro della traiettoria. Monitora contemporaneamente:

- numero di utenti non ancora saliti, compresi quelli a piedi;
- frazione di taxi con passeggero a bordo;
- età media delle richieste non ancora servite.

Usare lo stato corrente evita che le medie cumulative nascondano una coda in
crescita. Le osservazioni al minuto vengono aggregate in batch temporali
**non sovrapposti di 30 minuti**, pesando per la durata osservata. Il rilevatore
mantiene due finestre adiacenti di 12 batch ciascuna, quindi 12 ore di dati.
Per ogni variabile calcola:

```text
scala = tolleranza_assoluta + 0.5 × deviazione_standard_delle_due_finestre
spostamento = |media_seconda_finestra − media_prima_finestra|
deriva = |pendenza_lineare| × durata_delle_due_finestre
```

Una verifica passa se `spostamento <= scala` e `deriva <= 2 × scala` per tutte
le variabili. Le tolleranze assolute sono 1,5 utenti, 0,05 per la quota occupied
e 5 minuti per l'età media. Sono soglie pratiche nelle rispettive unità, **non
p-value**. Servono tre verifiche consecutive positive. Il primo rilevamento
possibile con i valori standard è dopo 13 ore. La memoria del rilevatore contiene
al massimo due finestre; l'aggiornamento può essere usato mentre il modello gira.

Si eseguono tre piloti con stream casuali distinti. Lo scarto iniziale usato
successivamente è il massimo dei tre tempi di rilevamento. Se un pilota non
rileva stabilità entro 96 ore, lo scenario viene marcato `warmup_not_detected`:
non vengono prodotte stime di regime né IC per quello scenario.

Il rilevatore è un **criterio euristico di stabilità osservata**, non una prova
matematica di stazionarietà. Può non vedere transitori molto lenti, accettare una
temporanea calma o non accettare un sistema stabile molto rumoroso. Le finestre
adiacenti possono essere ancora correlate; i controlli ripetuti non sono test di
ipotesi al livello 5%. Cambiare finestra e orizzonte aiuta a verificare sensibilità.
`not_detected` non dimostra da solo che la coda sia instabile.

## 3. Costruire gli intervalli di confidenza

Dopo i piloti si avviano **20 nuove repliche**, con stream distinti tra loro e
indipendenti dai piloti. Ogni replica scarta lo stesso tempo prefissato ed è
osservata per 24 ore utili, oppure 48 nello scenario di durata maggiore. Lo
scarto non viene scelto guardando i dati da usare negli IC, e il campione non
viene allungato fino a ottenere l'ampiezza desiderata.

Per ciascun KPI si usa una sola media per replica. Se `Y_r` è questa media,
l'intervallo bilaterale con livello nominale 95% è:

```text
media(Y) ± t_(0.975, R−1) × s(Y) / sqrt(R)
```

La distribuzione t di Student tiene conto della varianza stimata con `R` repliche.
Si usa `scipy.stats.t`; la deviazione standard è campionaria (`ddof=1`). Gli
estremi non vengono tagliati artificialmente a zero o uno. Gli IC su tutte le
configurazioni sono marginali, non garantiscono una copertura simultanea del 95%.

Non si applica questa formula ai singoli minuti o ai singoli passeggeri come se
fossero indipendenti: le code creano autocorrelazione. Le repliche indipendenti
permettono di usarla sulle loro medie. La copertura è comunque approssimata se
resta bias iniziale, la finestra è corta o le medie sono molto asimmetriche.
Un IC stretto indica precisione stimata, non garantisce realismo o assenza di bias.

Il bersaglio statistico è il valore atteso delle medie di replica sulla finestra
utile a input costanti, che approssima la prestazione di regime quando lo scarto
è sufficiente. Per le attese, ogni replica usa la propria coorte di arrivi:
non è una media pesata tra tutti i clienti di tutte le repliche.

### Gestire i clienti ancora in attesa

Le medie delle attese riguardano tutti gli utenti arrivati nella finestra utile,
non solo quelli serviti entro la sua fine. La simulazione continua fino al loro
imbarco, mantenendo anche i normali nuovi arrivi durante il follow-up. Spegnere
gli arrivi potrebbe cambiare il servizio visto da quella coorte.

Il limite di follow-up è 48 ore: un timeout rende la misura incompleta e viene
segnalato, senza eliminare gli utenti o scartare una replica sfortunata per
calcolare comunque l'IC. Un KPI con popolazione vuota è indefinito. Gli IC per
un campione che contiene misure incomplete non vengono calcolati. Le quote
occupied e idle sono misurate solo nella finestra utile tramite differenze dei
contatori: il follow-up non ne altera la durata.

## 4. Valutare l'effetto dei parametri sull'accuratezza

Lo studio confronta questi casi, con i medesimi insiemi di seed per agevolare
la riproducibilità dei confronti:

| Caso | Flotta | Moltiplicatore domanda | Ore utili | Batch per finestra |
| --- | ---: | ---: | ---: | ---: |
| baseline | 20 | 1 | 24 | 12 |
| fewer_taxis | 12 | 1 | 24 | 12 |
| higher_demand | 20 | 2 | 24 | 12 |
| longer_measurement | 20 | 1 | 48 | 12 |
| shorter_detector_window | 20 | 1 | 24 | 6 |
| overload | 4 | 4 | 24 | 12 |

Per ogni caso con misure complete si calcolano IC usando le prime 10 e tutte le
20 repliche, due numerosità fissate a priori. Il confronto valuta:

- **Precisione**: semiampiezza assoluta e relativa dell'IC, dipendente da durata,
  numero di repliche e variabilità del sistema. La semiampiezza tende a diminuire
  come `1/sqrt(R)` a varianza fissata; nel singolo campione la varianza stimata cambia.
- **Sensibilità al transitorio**: tempo scartato e comportamento con finestre più
  corte. Un rilevamento anticipato può lasciare bias; uno più tardivo costa tempo.
- **Carico e flotta**: più congestione può aumentare attese e variabilità; gli IC
  quantificano l'incertezza e i casi senza rilevamento vengono mantenuti nel report.

I grafici e la relazione sono costruiti dai risultati effettivi; il programma
non presume che ogni variazione renda necessariamente più stretto l'IC. Per
confrontare formalmente due configurazioni con seed comuni servirebbe un IC
delle differenze appaiate, diverso dagli IC marginali mostrati qui.

## 5. Verificare il metodo su un risultato noto

La verifica aggiuntiva esegue 300 esperimenti di una coda M/M/1, con tasso di
arrivo 0,5 e tasso di servizio 1. L'attesa media teorica in coda è esattamente 1.
Ogni esperimento usa 20 repliche di 3000 clienti, con attese correlate dentro
ogni replica. La distribuzione iniziale è quella invariante esatta, così il
confronto controlla la copertura degli IC senza confonderla con il transitorio.

Il CSV riporta quante volte l'IC comprende 1 e un intervallo Wilson sulla
copertura osservata: con un numero finito di esperimenti non ci si aspetta
esattamente 95%. Questa verifica **non certifica la copertura degli IC taxi** e
non prova la correttezza del rilevatore; fornisce un controllo riproducibile del
metodo di inferenza su una coda risolvibile. I test separati controllano segnali
stabili, transitori artificiali, derive persistenti, censura e indipendenza dei seed.
