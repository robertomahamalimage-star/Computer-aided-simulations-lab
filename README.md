# Computer-aided-simulations-lab

Simulatore Python di un servizio taxi per il laboratorio di simulazione.

Per il **secondo laboratorio** (rilevamento online del transitorio, intervalli
di confidenza e studio della precisione), vedere [README_STATIONARY.md](README_STATIONARY.md).
Il comando dedicato è `python3 taxi_stationary_lab.py`; i risultati già eseguiti
sono in [stationary_results/report.md](stationary_results/report.md).

I passeggeri possono chiamare un taxi oppure raggiungere a piedi lo stand più
vicino. Il sistema assegna alle richieste app il taxi idle più vicino, esegue
il viaggio e fa tornare il veicolo a uno stand con spazio disponibile.
Il ribilanciamento può trasferire una parte dei taxi verso zone con maggiore
domanda prevista.

## Esecuzione e verifiche

Dipendenze: Python, NumPy e pandas. Le verifiche sono state eseguite con
Python 3.12, NumPy 2.3.5 e pandas 2.2.3. I test usano `unittest`, incluso in Python.
Nella directory del repository:

```bash
python3 -B -m unittest -v
python3 -B taxi_simulation_v3.py
```

Il secondo comando esegue i controlli interni e **sette scenari con cinque
repliche ciascuno**, usando i seed 1000–1004. Scrive nella directory corrente:

- `taxi_simulation_v3_results.csv`: 35 righe, una per replica;
- `taxi_simulation_v3_summary.csv`: sette righe con medie, numero di repliche e
  deviazioni standard campionarie tra repliche.

I due CSV nel repository sono risultati generati: eseguire il comando dalla
directory del repository li sostituisce. Per conservare un esperimento, eseguire
lo script da una directory di output diversa usando il suo percorso assoluto.
Le colonne delle deviazioni standard terminano con `_std`: non sono intervalli
di confidenza. Cinque repliche consentono un confronto illustrativo; una stima
più precisa richiede di valutarne la variabilità e aumentare il campione.

## Parametri e ipotesi del modello

| Parametro | Significato | Valore predefinito |
| --- | --- | --- |
| `fleet_size` | Numero di taxi | 40 |
| `duration_hours` | Durata osservata | 24 ore |
| `dt_minutes` | Passo temporale massimo | 1 minuto |
| Tassi delle quattro zone | Domanda urbana di base, poi corretta per ora e condizioni | 5, 6, 4, 5 passeggeri/ora |
| `demand_multiplier` | Moltiplicatore della domanda urbana | 1 |
| `p_app` | Probabilità di usare app/telefono per domanda urbana ed eventi | 0,70 |
| `walking_speed_kmh` | Velocità a piedi | 4,8 km/h |
| `taxi_speed_kmh` | Velocità taxi nelle fasce ordinarie | 28 km/h |
| `road_distance_factor` | Rapporto tra distanza stradale e distanza in linea retta | 1,20 |
| `rebalance_interval_min` | Intervallo tra decisioni di ribilanciamento | 30 minuti |
| `rebalance_fraction` | Frazione massima dei taxi idle trasferibile per decisione | 0,25 |

La città misura 10 × 10 km ed è divisa in quattro zone. Le origini urbane sono
uniformi dentro ogni zona; le destinazioni seguono una matrice origine-destinazione.
Le distanze stradali sono approssimate con la distanza euclidea moltiplicata per
un fattore; non è modellata una rete stradale dettagliata. La domanda urbana è
Poisson con intensità variabile nel tempo. Ora, giorno, meteo e trasporto pubblico
possono modificarla; gli hub e gli eventi aggiungono flussi specifici. La domanda
complessiva è quindi **non stazionaria**, mentre la matrice urbana di destinazione
rimane fissa: non rappresenta variazioni direzionali dei pendolari nell'arco del giorno.
Le velocità reagiscono a penalità esogene; non si simula il traffico completo.
I valori sono illustrativi e non calibrati su una città reale.

Ogni intervallo segue questo ordine:

1. Generazione delle richieste e assegnazioni al tempo corrente.
2. Eventuale ribilanciamento.
3. Movimento dei taxi e dei pedoni fino alla fine dell'intervallo.
4. Aggiornamento dell'orologio.

Gli arrivi all'interno di un intervallo sono approssimati dal suo inizio.
Le conclusioni dei movimenti di durata positiva sono arrotondate alla fine
dell'intervallo: rimane un'approssimazione controllata dal passo temporale.
Chi è già allo stand può salire subito; un taxi già presso il cliente può farlo
salire subito. Le assegnazioni non possono usare taxi che saranno disponibili
soltanto a un istante futuro. L'ultimo intervallo viene accorciato per rispettare
esattamente la durata richiesta, anche se non è multipla del passo.

Tutti i taxi partono parcheggiati: la flotta deve poter entrare nei posti
disponibili (80 senza hub, 112 con hub). Valori impossibili vengono rifiutati
con un messaggio. Il ribilanciamento trasferisce al massimo la parte intera di
`taxi_idle × rebalance_fraction`: zero significa zero trasferimenti. Per
disabilitare l'intera politica si può anche usare `rebalancing=False`.

## Come leggere le metriche

| Colonna | Popolazione e significato |
| --- | --- |
| `avg_app_wait_min` | Tempo dalla richiesta all'imbarco degli utenti app già saliti, anche se ancora a bordo |
| `avg_stand_walk_min` | Tempo di cammino di chi ha raggiunto lo stand, anche se aspetta ancora il taxi |
| `avg_stand_wait_min` | Attesa allo stand di chi è già salito |
| `avg_total_access_min` | Tempo totale dalla richiesta all'imbarco, sui passeggeri già saliti |
| `avg_app_wait_lower_bound_min` | Media del tempo di attesa app già osservato, includendo chi non è ancora salito |
| `avg_total_access_lower_bound_min` | Stessa idea, includendo tutti gli utenti e il cammino |
| `avg_stand_walk_lower_bound_min` | Cammino concluso o già trascorso, su tutti gli utenti stand |
| `avg_stand_wait_lower_bound_min` | Attesa conclusa o già trascorsa, su chi ha raggiunto lo stand |
| `boarded_app`, `boarded_stand`, `arrived_at_stand` | Numerosità delle popolazioni usate nelle medie |
| `not_boarded_app`, `not_boarded_stand` | Utenti che non sono ancora saliti |
| `walking_to_stand`, `waiting_at_stand` | Utenti ancora a piedi oppure in coda allo stand |
| `onboard` | Passeggeri ancora in viaggio |
| `unfinished_app`, `unfinished_stand` | Tutti i viaggi non completati, inclusi quelli con passeggero a bordo |
| `completion_rate` | Frazione delle richieste il cui viaggio è terminato entro l'orizzonte |
| `availability_idle_share` | Quota del tempo-flotta trascorsa in stato idle |
| `utilization_occupied_share` | Quota del tempo-flotta con passeggero a bordo |
| `empty_running_share` | Quota del tempo-flotta in movimento a vuoto |
| `immediate_app_dispatch_rate` | Frazione delle richieste app assegnate al loro istante di generazione |
| `empty_distance_share` | Quota dei chilometri percorsi a vuoto |

Le colonne `lower_bound` sono **limiti inferiori**, perché chi aspetta ancora
potrà aspettare ulteriormente. Nessuna di queste medie viene presentata come
attesa finale di tutti i clienti quando esiste una coda residua. Per misurare
quella quantità occorrerebbe osservare la stessa coorte fino al suo servizio.
Quando una popolazione è vuota, la media è `NaN` (cella vuota nel CSV), non zero.
La simulazione termina all'orizzonte e non prevede abbandoni: un viaggio ancora
incompleto non è automaticamente una richiesta persa.

Le seguenti identità permettono di controllare i contatori:

```text
generated = completed + onboard + not_boarded_app + not_boarded_stand
generated = completed + unfinished_app + unfinished_stand
boarded = completed + onboard
```

Rispetto ai CSV precedenti, le medie includono ora anche utenti già saliti ma
ancora in viaggio; il cammino include anche chi è in coda. `unfinished_*` ora
comprende i viaggi a bordo: per il vecchio significato usare `not_boarded_*`.
Le medie del summary sono medie tra repliche, non una media pesata tra tutti i
passeggeri di tutte le giornate.

## Interpretazione degli scenari

Il confronto tra pioggia con sola crescita della domanda e pioggia con
rallentamento confronta gli stessi arrivi casuali e mette in evidenza l'effetto
della velocità sul servizio. Il confronto con/senza hub cambia invece anche gli
stand, i posti, alcune destinazioni e la congestione locale: descrive due
configurazioni complessive, non isola il solo effetto delle raffiche di arrivi.

Il ribilanciamento resta una politica semplice basata sulla domanda prevista
per zona; non ottimizza le code di ogni singolo stand. Possono quindi coesistere
taxi idle in alcune posizioni e clienti in attesa in altre. Le medie giornaliere
riassumono un sistema con domanda variabile: per analizzare i picchi sono utili
anche andamenti temporali di code e disponibilità.
