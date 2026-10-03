# -*- coding: utf-8 -*-
"""
RASTREADOR DE ID AC v1 — Big trades institucionales con identidad: la agresión exacta de CME,
magnitud empírica causal, tipo de flujo, clusters contra el azar e impacto auditado
Datos: Databento TBBO (GLBX.MDP3): cada operación con el mejor bid/ask JUSTO ANTES de ella.

Qué hace, en una línea: reconstruye cada orden agresiva tal como la casó CME y junta las que un
algoritmo disparó en milisegundos. Mide su tamaño contra las sesiones ANTERIORES y dice cómo
entró (barrido, absorción, fragmentada o bloque). Busca rachas que se agrupan más que la propia
actividad y audita qué pasa después, con estadística agrupada por sesión. A cada huella grande
le da un ID que la sigue a todas partes y la rastrea hasta que su nivel se sostiene o se rompe.

QUÉ ES EL "ID"
  Cada huella grande recibe un ID legible: YM0818-007 es la 7.ª grande de la sesión del 18 de
  agosto del YM. También lleva su id_cme (ts_event:sequence) para encontrarla en los datos
  crudos. El ID viaja por la consola, los 3 tableros, los CSV, Telegram y Live. Y se RASTREA: su
  VWAP queda como nivel y se sigue con triple barrera hasta SOSTENIDO, ROTO o NEUTRO, con MFE y
  MAE. Los clusters también tienen ID (CYM0818-03) y la lista de sus miembros.
  Ojo: los datos públicos de CME no dicen QUIÉN operó. El ID es de la huella, no del cliente.

LO QUE PEDISTE, HECHO A FONDO

  1. AGRUPACIÓN DE EVENTOS EN ALTA FRECUENCIA, en dos capas:
       · EVENTO = la racha de registros con el mismo ts_event, el mismo agresor y el mismo
         contrato. En CME todas las ejecuciones de UNA orden agresiva comparten la hora de la
         casación, aunque peguen contra varias órdenes y varios niveles. Es la orden tal como
         entró, sin ventanas arbitrarias. La prueba: un evento por casación y ni un contrato
         perdido.
       · HUELLA = eventos del MISMO lado a ≤ 100 ms (tu WINDOW_MS) uno del otro, con un tope de
         1 s y sin cruzar sesión ni contrato: la orden que un algoritmo partió en pedazos.
         Las agresiones del lado contrario no la cortan. La auditoría muestra cuántas huellas
         salen con 0, 10, 50, 100, 250 y 1000 ms.
     El motor lee el DBN por bloques y el evento abierto viaja al bloque siguiente. Por bloques
     de 777 registros da EXACTAMENTE lo mismo que de un jalón.

  2. CLASIFICACIÓN DE MAGNITUD EMPÍRICA, causal. Para cada sesión, la referencia son las huellas
     de las 5 sesiones ANTERIORES: la sesión actual no entra en su propia escala. Y va por
     franja: el horario regular se compara con el horario regular y la noche con la noche.
     GRANDE / MEGA / BALLENA = el tamaño ENTERO más chico con a lo más 5 % / 1 % / 0.1 % de la
     referencia por encima. Con empates, tu cuantil interpolado puede marcar el doble. Cada
     huella trae su percentil exacto. Además: el exponente de la cola (Hill) y la curva
     P(tamaño ≥ x) con los umbrales encima. Se descargan 3 sesiones de calentamiento para que la
     primera sesión ya tenga referencia.

  3. TIPIFICACIÓN DEL FLUJO DE ÓRDENES, de la evidencia más dura a la más general:
       ABSORCIÓN    todo en UN precio y, en una sola casación, se ejecutó más de lo que se veía
                    en ese nivel justo antes. Había liquidez oculta (iceberg o implícita) y el
                    nivel aguantó. Una casación no puede llevarse más de lo que hay.
       FRAGMENTADA  ≥ 3 agresiones del mismo lado a milisegundos: una orden partida.
       BARRIDO      una casación cruzó ≥ 2 niveles: urgencia.
       BLOQUE       una o dos agresiones que se llevaron lo visible de un nivel.
     Cada huella trae niveles cruzados, contratos ocultos, duración y lo que el agresor pagó
     contra el mid (costo efectivo).

  4. DETECCIÓN DE CLUSTERS por encadenamiento: huellas ≥ MEGA a ≤ 60 s (tu CLUSTER_WINDOW_SEC)
     una de otra. Cada cluster trae ID, duración, compra, venta, neto, VWAP, rango y PUREZA. Se
     llama COMPRADOR o VENDEDOR con pureza ≥ 0.6, y DISPUTA si no. Dos pruebas de permutación:
       · ¿se agrupan MÁS que la actividad? La clase se reparte al azar entre TODAS las huellas
         de la misma sesión y franja, así que la apertura ya está en la hipótesis nula;
       · ¿son de un solo lado más que si los lados se barajan dentro de la sesión?
     ¿Por qué MEGA y no GRANDE? En horario regular sale una GRANDE cada ~30 s y 60 s encadena
     media sesión. En una simulación eso dio clusters de 84 huellas y 28 min, iguales al azar
     (p = 0.88). --cluster-clase 1 lo regresa a GRANDE.

  5. AUDITORÍA DE IMPACTO PREDICTIVO INSTITUCIONAL, en ticks a favor del agresor:
       · IMPACTO desde el mid ANTES de la huella (incluye lo que ella misma movió) y DERIVA desde
         el primer libro DESPUÉS: lo único que se podía operar al verla. A 1 s, 10 s, 1, 5, 15,
         30 y 60 min, sin cruzar el cierre de sesión ni un roll (NaN, nunca 0);
       · por magnitud, tipo, posición en el rango de la sesión, dentro o fuera de un cluster,
         día o noche, y siempre contra la línea base de las huellas NORMALES;
       · IC 95 % y p con error estándar agrupado por sesión (t con G − 1 gl): las huellas de una
         misma sesión no son independientes;
       · deriva NETA de momentum y flujo de los 5 min previos (regresión con errores agrupados);
       · la curva de impacto contra el tamaño (I ∝ Q^δ) y los costos: spread, lo pagado contra
         el mid y la deriva neta de un spread, en ticks y en US$ por contrato.

  6. DASHBOARD VISUAL COMPLETO, 3 tableros PNG:
       · RASTREADOR: precio en tiempo de negociación con cada huella grande (color = lado,
         forma = tipo, tamaño = magnitud), clusters de fondo, el nivel de cada BALLENA rastreado
         con su ID y estado, el tamaño contra los umbrales causales, el CVD de todo el flujo
         contra el de las grandes, y dónde aparecen dentro del rango de la sesión;
       · AUDITORÍA (9 paneles): curvas de impacto con IC, transitorio contra permanente por
         tipo, impacto contra tamaño, distribución con cola de Hill, permutación de clusters,
         hora del día por tipo, rastreo contra la base, tu script contra el módulo y cordura;
       · IDs: tabla de los últimos 32 IDs y de los últimos clusters, con colores por lado y
         estado.

  Además: el RASTREO de cada ID con triple barrera (López de Prado 2018), el contexto causal de
  cada huella (rango, VWAP y CVD de la sesión hasta ese momento) y un DOBLE MOTOR: el vectorizado
  por bloques y el incremental, registro por registro, para Live. Cada corrida verifica que den
  las mismas huellas sobre los primeros 300 000 registros. Live con Telegram: cada huella ≥ MEGA
  y cada cluster direccional en curso llegan a tu teléfono. También una réplica fiel de tu script
  para medirlo y un simulador con verdad conocida que escribe un DBN TBBO de verdad. Más un
  chequeo de cordura ✓/⚠, 31 pruebas internas y 5 CSV: IDs, clusters, impacto, seguimiento y
  umbrales.

QUÉ SE MIDIÓ — 12 simulaciones de 8 sesiones (5 analizadas, ~187 000 operaciones cada una):
6 con metaórdenes institucionales e icebergs CONOCIDOS, 6 sin ellos

    con flujo institucional (6)                     módulo          tu script
    volumen institucional dentro de "grande"        94.8 %            27.4 %
    precisión (el azar da 10.5 %)                   27.9 %            19.8 %
    dirección correcta                              100 %              0 %

  · Tipo asignado contra el estilo verdadero de las huellas grandes institucionales: BLOQUE
    99.8 %, BARRIDO 98.4 %, FRAGMENTADA 99.4 %, ráfagas contra iceberg → ABSORCIÓN 95.5 %.
    Icebergs encontrados: 89 de 89, con 100 % de precisión de ABSORCIÓN.
  · Clusters: con flujo institucional quedan 1.46 veces más huellas en cluster que en el azar,
    con p = 0.005 en las 6 corridas (el mínimo posible con 200 permutaciones). Su pureza es 0.78
    contra 0.46 barajando los lados, también con p = 0.005 en las 6. Sin flujo institucional
    salen 1.02 veces el azar, con p ≤ 0.05 en 1 de 6 (lo esperado es ~5 %), y la prueba de
    dirección no rechaza en ninguna (p ≥ 0.065). De los clusters direccionales con volumen
    institucional, 389 de 390 apuntan al lado correcto.
  · Impacto: la deriva a 5 min de TODAS las grandes es NEGATIVA, −0.81 ticks (−0.92 sin
    institucionales). Es el rebote del impacto transitorio: un tamaño grande, por sí solo, no
    anticipa nada. Sólo las INFORMADAS siguen, +1.98 ticks, y se SOSTIENEN el 68.5 % de las
    veces. El ruido grande se sostiene el 31.8 % y las institucionales sin información el 30.5 %.
  · ABSORCIÓN: el agresor se sostiene el 28 % de las veces contra 40 % de la base. Gana el
    PASIVO: en una absorción, el institucional es el que absorbe, no el que pega.

QUÉ FALLABA EN EL SCRIPT QUE MANDASTE (los comentarios [v1] lo marcan en el código)

  · LA API KEY ESTÁ ESCRITA EN LA LÍNEA 14. Dala por publicada y regenérala. Aquí se lee de
    DATABENTO_API_KEY, igual que en tus otros módulos.

  · EL LADO ESTÁ AL REVÉS. En Databento el side de una operación es el del AGRESOR: 'B' = compra
    agresiva, 'A' = venta agresiva. Tu script toma 'A' como COMPRA. Tus "Buy" son ventas, tu CVD
    sale con el signo invertido y tus "Forward Returns tras Big Trades BUY" son tras ventas. El
    chequeo de cordura lo demuestra con TUS datos: las compras agresivas se ejecutan en el ask
    del libro previo y tus "compras" en el bid (en la simulación, 100 % y 0 %).

  · HIT_PRICE NO ES EL PRECIO DE LA OPERACIÓN. Es el mejor bid/ask del libro previo: un barrido
    de 3 niveles queda anotado al precio del primero.

  · VENTANAS DE RELOJ DE 100 ms (index.floor sobre ts_recv) agrupadas por precio y lado. El 5.8 %
    de tus big trades suman órdenes agresivas DISTINTAS que cayeron en los mismos 100 ms.

  · PERCENTILES CON TODA LA MUESTRA: el umbral del martes a las 8:00 usa el jueves (mira al
    futuro). Además mezcla Asia con la apertura y, con empates, "p95" no es 5 %.

  · FRAGMENTED NUNCA SE ASIGNA (lo pisan las dos reglas siguientes), y SWEEP es "3 o más trades
    en el grupo": eso no dice si cruzó niveles.

  · TUS CLUSTERS miden 60 s desde el PRIMER trade (una racha de 5 min queda partida en 5),
    mezclan compras con ventas (el 61 % en la simulación), y dos grupos de la MISMA ventana de
    100 ms (otro precio u otro lado) ya cuentan como un cluster.

  · TU CONTEXTO: el "rango" es de 200 SEGUNDOS (200 filas de un mid a 1 s, no barras), se
    asigna con reindex(method='nearest'), que puede tomar un valor POSTERIOR, y fila por fila.

  · TUS RETORNOS rellenan con 0.0 cuando no hay dato (el 12 % a 5 min en la simulación): eso jala
    el promedio a cero. Cruzan el roll del continuo, no tienen t ni IC, no restan costos y se
    miden desde el inicio de la ventana de 100 ms, mezclando el impacto propio con lo que sigue.

  · MBP-10 DE DOS DÍAS Y MEDIO A LA MEMORIA con to_df(), para quedarse sólo con las operaciones.
    TBBO trae exactamente eso (operación + libro previo), en una fracción del tamaño y del costo.

  · Menores: extract_big_trades devuelve un DataFrame o una tupla según el caso, un
    try/except Exception esconde el error real y los warnings están apagados.

LÍMITES QUE CONVIENE SABER
  · TBBO sólo ve el mejor nivel antes de la operación. De un barrido se sabe cuántos niveles
    cruzó, pero no cuánto había en el 2.º y el 3.º. ABSORCIÓN sólo juzga el primer nivel.
  · "Oculta" junta icebergs y liquidez implícita (CME arma precios implícitos con los spreads de
    calendario). MBO los separaría, a un costo mucho mayor.
  · Una huella puede juntar a dos participantes que coincidieron en ≤ 100 ms. La auditoría da
    la sensibilidad al hueco y FRAGMENTADA lo marca.
  · Un tamaño grande NO es por sí mismo institucional: en la simulación el 72 % del volumen
    "grande" es ruido con cola de Pareto. Lo que separa la información es el tipo, el cluster y
    el contexto, y eso lo dice la auditoría con TUS datos, no la simulación.
  · Con 3-5 sesiones la t tiene 2-4 grados de libertad: los IC son anchos y casi nada sale con
    p < 0.05. Más sesiones dan más poder.
  · La simulación decide la plomería y la estadística, no si esto funciona en el YM.
  · Live calienta con 7 sesiones de historia hasta el último halt (16:00 CT). Databento Live
    repite como máximo las últimas 24 h; si el halt quedó antes, avisa del hueco.

CÓMO SE USA
    pip install numpy pandas matplotlib databento
    python rastreador_id.py --pruebas                    # 31 pruebas, sin red
    python rastreador_id.py --simulacion                 # mercado simulado con verdad conocida
    python rastreador_id.py --simulacion --sin-metaordenes --sin-icebergs   # el mismo, sin institucionales
    python rastreador_id.py                              # YM, 18-20 de agosto de 2026 (tu ventana, hora CDMX)
    python rastreador_id.py --simbolo NQ --start "2026-09-21 08:30" --end "2026-09-26 15:00"
    python rastreador_id.py --archivo datos.dbn.zst      # un DBN que ya tengas
    python rastreador_id.py --esquema trades             # más barato, sin libro ni ABSORCIÓN
    python rastreador_id.py --rafaga-ms 50 --cluster-clase 1 --cluster-gap 30
    python rastreador_id.py --telegram                   # resumen + 3 tableros
    python rastreador_id.py --telegram-solo-alertas      # sólo si hubo ≥ MEGA o un cluster en los últimos 15 min
    python rastreador_id.py --live --telegram-live       # en vivo; cada ≥ MEGA a tu teléfono
  --start y --end van en hora de CDMX (cámbialo con --tz-entrada); los reportes, en hora de
  CHICAGO y de CDMX. Antes de descargar se revisa el costo (--costo-max, 25 USD por omisión).
  Con --sin-paridad se salta el chequeo del motor incremental.

LAS CREDENCIALES NO VAN EN EL CÓDIGO — igual que en tus otros módulos.
    Databento   DATABENTO_API_KEY     PowerShell:  setx DATABENTO_API_KEY "db-..."
    Telegram    TELEGRAM_BOT_TOKEN                 setx TELEGRAM_BOT_TOKEN "123456789:AA..."
                TELEGRAM_CHAT_ID                   setx TELEGRAM_CHAT_ID "123456789"
    (cierra y abre VS Code después de setx). El token te lo da @BotFather; el chat_id lo
    encuentras con --telegram-buscar-chat después de escribirle /start a tu bot. Si falta
    alguna y la terminal es interactiva, se pide con getpass y no se guarda. Los errores de
    Telegram nunca imprimen el token, y una prueba revisa que en este archivo no haya
    ninguna key ni token escritos.

FUENTES
  CME Group, "MDP 3.0 — Trade Summary": todas las ejecuciones de una orden agresiva comparten
      TransactTime. — la agrupación exacta en eventos.
  Databento: https://databento.com/docs — esquema TBBO (operación + mejor bid/ask previo), side
      del agresor (A/B/N), banderas F_LAST, F_MAYBE_BAD_BOOK y F_BAD_TS_RECV, Live y replay.
  Hasbrouck, J. (1991), "Measuring the information content of stock trades", Journal of
      Finance 46(1). — impacto permanente contra transitorio.
  Lillo, F., Farmer, J. D. y Mantegna, R. (2003), "Master curve for price-impact function",
      Nature 421. — la concavidad del impacto por operación.
  Lillo, F. y Farmer, J. D. (2004), "The long memory of the efficient market", Studies in
      Nonlinear Dynamics & Econometrics 8(3). — las órdenes grandes se parten.
  Tóth, B. et al. (2011), "Anomalous price impact and the critical nature of liquidity in
      financial markets", Physical Review X 1. — la ley de la raíz cuadrada.
  Gopikrishnan, P., Plerou, V., Gabaix, X. y Stanley, H. E. (2000), "Statistical properties of
      share volume traded in financial markets", Physical Review E 62(4). — la cola del volumen.
  Hill, B. M. (1975), "A simple general approach to inference about the tail of a
      distribution", Annals of Statistics 3(5).
  Ester, M., Kriegel, H.-P., Sander, J. y Xu, X. (1996), "A density-based algorithm for
      discovering clusters", KDD-96. — el encadenamiento (DBSCAN en una dimensión).
  Liang, K.-Y. y Zeger, S. L. (1986), "Longitudinal data analysis using generalized linear
      models", Biometrika 73(1). — los errores estándar agrupados por sesión.
  López de Prado, M. (2018), Advances in Financial Machine Learning, Wiley, cap. 3. — la triple
      barrera del rastreo de IDs.
  Telegram Bot API: https://core.telegram.org/bots/api
"""
from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import sys
import time
import uuid
import warnings
from collections import deque
from dataclasses import dataclass, field, replace
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

try:
    import databento as db
except ModuleNotFoundError:
    db = None

IDENTIFICADOR = "rastreador-id-ac-v1"
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)
np.seterr(all="ignore")

# --- Constantes de la sesión de CME Globex ---
MINUTOS_SESION = 1380            # 17:00 → 16:00 CT (23 horas)
DESFASE_H = 7                    # hora CT + 7 h → la sesión que abre a las 17:00 cae en su fecha
NS = 1_000_000_000
NS_MS = 1_000_000
DIA_NS = 86_400 * NS

# --- Banderas de los registros de Databento (databento_dbn) ---
F_LAST = 128                     # último registro de un evento
F_TOB = 64
F_SNAPSHOT = 32
F_MBP = 16
F_BAD_TS_RECV = 8                # la hora de recepción no es confiable
F_MAYBE_BAD_BOOK = 4             # el libro puede estar mal (hueco en el feed)
UNDEF_PRICE = 9223372036854775807

# Raíz → (nombre, tamaño del tick, precio de referencia para la simulación, US$ por punto)
CATALOGO = {
    "NQ": ("Nasdaq 100", 0.25, 20000.0, 20.0), "MNQ": ("Micro Nasdaq 100", 0.25, 20000.0, 2.0),
    "ES": ("S&P 500", 0.25, 5500.0, 50.0), "MES": ("Micro S&P 500", 0.25, 5500.0, 5.0),
    "YM": ("Dow Jones", 1.0, 42000.0, 5.0), "MYM": ("Micro Dow", 1.0, 42000.0, 0.5),
    "RTY": ("Russell 2000", 0.1, 2200.0, 50.0), "M2K": ("Micro Russell", 0.1, 2200.0, 5.0),
    "ZN": ("Nota 10 años", 1 / 64, 110.0, 1000.0), "ZB": ("Bono 30 años", 1 / 32, 118.0, 1000.0),
    "GC": ("Oro", 0.1, 2500.0, 100.0), "MGC": ("Micro oro", 0.1, 2500.0, 10.0),
    "SI": ("Plata", 0.005, 30.0, 5000.0), "HG": ("Cobre", 0.0005, 4.3, 25000.0),
    "CL": ("Crudo WTI", 0.01, 75.0, 1000.0), "MCL": ("Micro crudo", 0.01, 75.0, 100.0),
    "NG": ("Gas natural", 0.001, 2.6, 10000.0),
    "6E": ("Euro", 0.00005, 1.10, 125000.0), "6J": ("Yen", 0.0000005, 0.0068, 12500000.0),
    "6M": ("Peso mexicano", 0.00001, 0.055, 500000.0),
}

CLASES = ("NORMAL", "GRANDE", "MEGA", "BALLENA")          # índice = clase (−1 = sin referencia)
TIPOS = ("BLOQUE", "BARRIDO", "ABSORCIÓN", "FRAGMENTADA")
ESTADOS = {1: "SOSTENIDO", 0: "NEUTRO", -1: "ROTO"}


# =============================================================================
# 1. CONFIGURACIÓN
# =============================================================================
@dataclass(frozen=True)
class Config:
    # --- Datos ---
    dataset: str = "GLBX.MDP3"
    symbol: str = "YM.n.0"                  # tu SYMBOL
    stype_in: str = "continuous"
    start: str = "2026-08-18T07:00:00"     # tu START_LOCAL (hora de CDMX)
    end: str = "2026-08-20T14:00:00"       # tu END_LOCAL, exclusivo
    tz_entrada: str = "America/Mexico_City"
    dias_calentamiento: int = 3            # sesiones previas: dan los umbrales de la primera sesión
    esquema: str = "tbbo"                  # tbbo (operación + libro justo antes) · trades · mbp-1 · mbp-10
    cache_dir: str = "datos_databento"
    usar_cache: bool = True
    salida_dir: str = "salidas_rastreador"
    costo_max_usd: float = 25.0
    bloque: int = 2_000_000                # registros por bloque al leer el DBN
    tz_mercado: str = "America/Chicago"
    tz_local: str = "America/Mexico_City"

    # --- Higiene ---
    spread_max_ticks: int = 8              # libro previo más ancho = no sirve de referencia

    # --- 1. Agrupación de eventos en alta frecuencia ---
    rafaga_ms: float = 100.0               # tu WINDOW_MS, como HUECO máximo entre agresiones del mismo lado
    rafaga_max_ms: float = 1000.0          # duración máxima de una huella (que la apertura no encadene todo)

    # --- 2. Magnitud empírica (percentiles causales) ---
    p_grande: float = 0.95                 # tu PERCENTILE_LARGE
    p_mega: float = 0.99                   # tu PERCENTILE_MEGA
    p_ballena: float = 0.999               # tu PERCENTILE_WHALE
    ventana_sesiones: int = 5              # sesiones ANTERIORES que dan la distribución de referencia
    min_ref: int = 2000                    # huellas mínimas de referencia (por franja)
    por_franja: bool = True                # umbrales aparte para horario regular y Globex nocturno
    rth_ct: tuple[str, str] = ("08:30", "15:00")
    piso_contratos: int = 0                # tamaño mínimo absoluto para ser GRANDE (0 = sin piso)

    # --- 3. Tipificación ---
    min_eventos_fragmentada: int = 3
    oculta_min: int = 1                    # ABSORCIÓN: contratos ejecutados en UNA casación más allá de lo visible

    # --- 4. Clusters ---
    cluster_gap_s: float = 60.0            # tu CLUSTER_WINDOW_SEC, como hueco máximo entre grandes
    cluster_clase_min: int = 2             # clusters entre huellas ≥ MEGA (1 = desde GRANDE)
    cluster_min: int = 2
    pureza_min: float = 0.60               # |compras − ventas| / total para llamarlo direccional
    n_permutaciones: int = 200
    franja_perm_min: int = 30              # la hipótesis nula conserva la actividad de cada media hora

    # --- 5. Impacto y rastreo de IDs ---
    horizontes_s: tuple[int, ...] = (1, 10, 60, 300, 900, 1800, 3600)
    h_principal_s: int = 300
    h_raiz_s: int = 60                     # horizonte de la curva de impacto contra el tamaño
    rancio_max_s: float = 60.0             # el precio "en t + h" puede llegar hasta max(esto, h/2) después
    seguimiento_s: int = 1800              # barrera vertical del rastreo de cada ID
    barrera_sigma: float = 0.5             # barreras = ± esto × σ de la ventana de seguimiento
    min_rango_ticks: int = 4
    base_normales: int = 20_000            # huellas normales para la línea base del rastreo

    # --- Alertas ---
    alerta_min: int = 2                    # 2 = MEGA, 3 = BALLENA
    alerta_ventana_min: int = 15

    # --- Live ---
    dias_historial_live: int = 7

    # --- Simulación ---
    sim_sesiones: int = 8
    sim_eventos: int = 60_000              # eventos de libro por sesión
    sim_metaordenes: int = 8               # órdenes institucionales por sesión
    sim_icebergs: int = 3                  # órdenes ocultas pasivas por sesión
    sim_semilla: int = 0

    # --- Telegram ---
    telegram_live: bool = False


CFG = Config()
CARPETA_SCRIPT = Path(__file__).resolve().parent


def _ruta(nombre_: str) -> Path:
    p = Path(nombre_)
    return p if p.is_absolute() else CARPETA_SCRIPT / p


def _nombre_seguro(*partes) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", "_".join(str(p) for p in partes))


def _interactivo() -> bool:
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except Exception:
        return False


def _titulo(texto: str, ancho: int = 94) -> None:
    print("\n" + "=" * ancho)
    print(texto)
    print("=" * ancho)


def _fmt(x, dec=3, ancho=9) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return str(x).rjust(ancho)
    return f"{v:{ancho}.{dec}f}" if np.isfinite(v) else "—".rjust(ancho)


def _pct(x, dec=1, ancho=7) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "—".rjust(ancho)
    return f"{100.0 * v:{ancho}.{dec}f}%" if np.isfinite(v) else "—".rjust(ancho)


def _z(p: float) -> float:
    return float(NormalDist().inv_cdf(p))


# --- distribución t (sin scipy) ---
def _betacf(a: float, b: float, x: float) -> float:
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > 1e-300 else 1e-300)
    h = d
    for m in range(1, 400):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > 1e-300 else 1e-300)
        c = 1.0 + aa / c
        c = c if abs(c) > 1e-300 else 1e-300
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > 1e-300 else 1e-300)
        c = 1.0 + aa / c
        c = c if abs(c) > 1e-300 else 1e-300
        de = d * c
        h *= de
        if abs(de - 1.0) < 3e-14:
            break
    return h


def _beta_inc(a: float, b: float, x: float) -> float:
    """Beta incompleta regularizada I_x(a, b) (fracción continua de Lentz)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lb = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    if x < (a + 1.0) / (a + b + 2.0):
        return math.exp(lb) * _betacf(a, b, x) / a
    return 1.0 - math.exp(lb) * _betacf(b, a, 1.0 - x) / b


def p_t(t: float, gl: float) -> float:
    """p de dos colas de una t con `gl` grados de libertad."""
    if not np.isfinite(t) or gl <= 0:
        return np.nan
    return _beta_inc(gl / 2.0, 0.5, gl / (gl + t * t))


def t_cuantil(q: float, gl: float) -> float:
    """Cuantil q (> 0.5) de la t de Student, por bisección."""
    if gl <= 0:
        return np.nan
    obj = 2.0 * (1.0 - q)
    lo, hi = 0.0, 1e3
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if p_t(mid, gl) > obj:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# --- reloj de la sesión de Globex ---
def _ns(idx) -> np.ndarray:
    """DatetimeIndex (con o sin zona) → enteros en ns."""
    idx = pd.DatetimeIndex(idx)
    if hasattr(idx, "as_unit"):
        idx = idx.as_unit("ns")
    return np.asarray(idx.asi8, dtype=np.int64)


def a_indice(t_ns) -> pd.DatetimeIndex:
    return pd.to_datetime(np.asarray(t_ns, dtype=np.int64), unit="ns", utc=True)


def reloj_sesion(t_ns, tz_mercado: str) -> tuple[np.ndarray, np.ndarray]:
    """
    (día de la sesión, segundo de la sesión) para cada marca en ns UTC. La sesión de CME abre a
    las 17:00 de Chicago y lleva la fecha del día siguiente: hora CT + 7 h. El día es un entero
    (días desde 1970) y el segundo va de 0 (17:00 CT) a 82 799 (15:59:59 CT).
    """
    t = np.asarray(t_ns, dtype=np.int64)
    if not len(t):
        return np.zeros(0, np.int64), np.zeros(0, np.int64)
    pared = a_indice(t).tz_convert(tz_mercado).tz_localize(None) + pd.Timedelta(hours=DESFASE_H)
    p = _ns(pared)
    dia = p // DIA_NS
    return dia.astype(np.int64), ((p - dia * DIA_NS) // NS).astype(np.int64)


def fecha_de_dia(dia: int) -> pd.Timestamp:
    return pd.Timestamp(int(dia) * DIA_NS)


def apertura_utc(dia: int, tz_mercado: str) -> int:
    """ns UTC de las 17:00 CT con que abre la sesión `dia`."""
    pared = fecha_de_dia(dia) - pd.Timedelta(hours=DESFASE_H)
    return int(pared.tz_localize(tz_mercado, ambiguous=False, nonexistent="shift_forward")
               .tz_convert("UTC").value)


def segundo_de_hora(hhmm_ct: str) -> int:
    h, m = (int(x) for x in hhmm_ct.strip().split(":"))
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(f"Hora inválida: {hhmm_ct!r} (usa HH:MM, hora de Chicago)")
    return (((h + DESFASE_H) % 24) * 60 + m) * 60


def a_utc(texto: str, tz: str) -> pd.Timestamp:
    t = pd.Timestamp(texto)
    return (t.tz_localize(tz) if t.tzinfo is None else t).tz_convert("UTC")


def raiz(symbol: str) -> str:
    return symbol.split(".")[0].upper()


def simbolo_continuo(s: str) -> str:
    s = s.strip()
    return s if "." in s else f"{s.upper()}.n.0"


def nombre(symbol: str) -> str:
    return CATALOGO.get(raiz(symbol), (raiz(symbol), 0.0, 100.0, 1.0))[0]


def tick(symbol: str) -> float:
    t = CATALOGO.get(raiz(symbol), ("", 0.0, 100.0, 1.0))[1]
    if t <= 0:
        sys.exit(f"❌ No conozco el tick de {symbol}. Agrégalo a CATALOGO (raíz → nombre, tick, precio, US$/punto).")
    return t


def tick_ns(symbol: str) -> int:
    return int(round(tick(symbol) * NS))


def valor_tick_usd(symbol: str) -> float:
    c = CATALOGO.get(raiz(symbol), ("", 0.0, 100.0, 1.0))
    return c[1] * c[3]


def validar(cfg: Config) -> None:
    if cfg.esquema not in ("tbbo", "trades", "mbp-1", "mbp-10"):
        sys.exit("❌ --esquema va tbbo (recomendado), trades, mbp-1 o mbp-10.")
    if not (0 < cfg.p_grande < cfg.p_mega < cfg.p_ballena < 1):
        sys.exit("❌ Los percentiles deben cumplir 0 < grande < mega < ballena < 1.")
    if cfg.rafaga_ms < 0 or cfg.rafaga_max_ms < cfg.rafaga_ms:
        sys.exit("❌ Hace falta 0 ≤ --rafaga-ms ≤ --rafaga-max-ms.")
    if cfg.ventana_sesiones < 1:
        sys.exit("❌ --ventana-sesiones debe ser al menos 1.")
    if cfg.cluster_gap_s <= 0 or cfg.cluster_min < 2:
        sys.exit("❌ Un cluster necesita --cluster-gap > 0 y al menos 2 huellas grandes.")
    if not (0.5 <= cfg.pureza_min < 1):
        sys.exit("❌ --pureza va entre 0.5 y 1.")
    if cfg.h_principal_s not in cfg.horizontes_s or cfg.h_raiz_s not in cfg.horizontes_s:
        sys.exit("❌ El horizonte principal y el de la curva de impacto deben estar en --horizontes.")
    if cfg.cluster_clase_min not in (1, 2, 3):
        sys.exit("❌ --cluster-clase va 1 (GRANDE), 2 (MEGA) o 3 (BALLENA).")
    if cfg.alerta_min not in (1, 2, 3):
        sys.exit("❌ --alerta-min va 1 (GRANDE), 2 (MEGA) o 3 (BALLENA).")
    try:
        if segundo_de_hora(cfg.rth_ct[0]) >= segundo_de_hora(cfg.rth_ct[1]):
            sys.exit("❌ El horario regular debe empezar antes de terminar (hora CT).")
        if a_utc(cfg.start, cfg.tz_entrada) >= a_utc(cfg.end, cfg.tz_entrada):
            sys.exit("❌ --start debe ser anterior a --end.")
    except ValueError as ex:
        sys.exit(f"❌ {ex}")


# =============================================================================
# 2. DATOS — Databento, con la key FUERA del código
# =============================================================================
def _limpiar_key(texto: str | None) -> str:
    texto = re.sub(r"\x1b\[[0-9;]*[~A-Za-z]", "", texto or "")
    return "".join(ch for ch in texto if ch.isprintable() and not ch.isspace()).strip("\"'")


def _mascara(key: str) -> str:
    key = key or ""
    return (f"{key[:5]}…{key[-3:]} ({len(key)} caracteres)" if len(key) > 8
            else f"({len(key)} caracteres)")


def _leer_secreto(pregunta: str) -> str:
    import getpass
    try:
        return getpass.getpass(pregunta, echo_char="*")
    except TypeError:
        return getpass.getpass(pregunta)


AYUDA_KEY = (
    "  • La key de Databento NO va en el código: se lee de la variable DATABENTO_API_KEY.\n"
    "  • La que estaba escrita en la línea 14 de bigtrade_deepsek.py hay que darla por\n"
    "    publicada: regenérala en https://databento.com/docs/portal/api-keys\n"
    '  • Guárdala una vez en PowerShell:  setx DATABENTO_API_KEY "db-..."  y cierra y abre VS Code.'
)


def _exigir_api_key() -> None:
    guardada = _limpiar_key(os.environ.get("DATABENTO_API_KEY"))
    if guardada:
        os.environ["DATABENTO_API_KEY"] = guardada
        return
    if not _interactivo():
        sys.exit("Falta la variable de entorno DATABENTO_API_KEY.\n" + AYUDA_KEY)
    for _ in range(3):
        key = _limpiar_key(_leer_secreto("Pega tu API key de Databento: "))
        if key.startswith("db-"):
            os.environ["DATABENTO_API_KEY"] = key
            print(f"Key recibida: {_mascara(key)}")
            return
        print(f"Eso no parece una key de Databento; llegó {_mascara(key)}.")
    sys.exit("No se recibió una API key válida.\n" + AYUDA_KEY)


def conectar():
    if db is None:
        sys.exit("Falta el paquete databento:  pip install databento\n"
                 "   (o corre sin red:  --simulacion  /  --pruebas)")
    for _ in range(3):
        _exigir_api_key()
        cliente = db.Historical()
        try:
            cliente.metadata.list_datasets()
            return cliente
        except Exception as e:
            if getattr(e, "http_status", None) not in (401, 403):
                raise
            key = os.environ.pop("DATABENTO_API_KEY", "")
            print(f"❌ Databento rechazó la key {_mascara(key)}.")
            if not _interactivo():
                break
    sys.exit("No se pudo autenticar con Databento.\n" + AYUDA_KEY)


def ventana_utc(cfg: Config) -> tuple[pd.Timestamp, pd.Timestamp]:
    """La ventana que se ANALIZA (lo que pediste), en UTC."""
    return a_utc(cfg.start, cfg.tz_entrada), a_utc(cfg.end, cfg.tz_entrada)


def inicio_descarga(cfg: Config) -> pd.Timestamp:
    """
    La apertura (17:00 CT) de la sesión que queda `dias_calentamiento` sesiones hábiles antes de
    la de --start: esas sesiones sólo dan la distribución de referencia de la primera.
    """
    t0, _ = ventana_utc(cfg)
    dia = int(reloj_sesion([t0.value], cfg.tz_mercado)[0][0])
    fecha = fecha_de_dia(dia)
    if cfg.dias_calentamiento > 0:
        fecha = fecha - pd.offsets.BDay(cfg.dias_calentamiento)
    return pd.Timestamp(apertura_utc(int(fecha.value // DIA_NS), cfg.tz_mercado), tz="UTC")


def obtener_datos(cfg: Config, cliente=None, inicio: pd.Timestamp | None = None,
                  fin: pd.Timestamp | None = None):
    """
    Descarga a DISCO (no a memoria), revisando el costo antes, y devuelve el DBNStore; el motor
    lo lee por bloques.

    [v1] Tu script baja MBP-10 de dos días y medio del YM con get_range(...).to_df() de un
    jalón: cada cambio de los 10 niveles del libro, 70+ columnas, a la RAM, para quedarse sólo
    con las operaciones. TBBO trae exactamente eso que usas —cada operación con el mejor bid/ask
    JUSTO ANTES de ella— en una fracción del tamaño y del costo.
    """
    carpeta = _ruta(cfg.cache_dir)
    carpeta.mkdir(parents=True, exist_ok=True)
    inicio = inicio if inicio is not None else inicio_descarga(cfg)
    fin = fin if fin is not None else ventana_utc(cfg)[1]
    i_txt, f_txt = inicio.strftime("%Y-%m-%dT%H:%M:%S"), fin.strftime("%Y-%m-%dT%H:%M:%S")
    ruta = carpeta / (_nombre_seguro(cfg.dataset, cfg.symbol, i_txt, f_txt, cfg.esquema) + ".dbn.zst")
    if ruta.exists() and cfg.usar_cache:
        print(f"📂 Usando caché local: {ruta.name}")
        return db.DBNStore.from_file(ruta)
    cliente = cliente or conectar()
    params = dict(dataset=cfg.dataset, symbols=[cfg.symbol], stype_in=cfg.stype_in,
                  schema=cfg.esquema, start=i_txt, end=f_txt)
    costo = cliente.metadata.get_cost(**params)
    try:
        tam = cliente.metadata.get_billable_size(**params)
    except Exception:
        tam = float("nan")
    print(f"💵 Costo estimado: US$ {costo:,.2f} · {tam / 1e9:,.2f} GB sin comprimir "
          f"({cfg.symbol}, {cfg.esquema}, {i_txt[:16]} → {f_txt[:16]} UTC)")
    if costo > cfg.costo_max_usd:
        sys.exit(f"💰 El costo (US$ {costo:,.2f}) supera tu tope de US$ {cfg.costo_max_usd:,.2f}.\n"
                 f"   Si estás de acuerdo:  --costo-max {math.ceil(costo) + 1}\n"
                 f"   Más barato (sin libro, sin ABSORCIÓN):  --esquema trades")
    temporal = ruta.with_name(ruta.name + ".parcial")
    temporal.unlink(missing_ok=True)
    print(f"📡 Descargando {cfg.symbol} ({cfg.esquema}) a {ruta.name} …")
    descarga = cliente.timeseries.get_range(**params, path=temporal)
    del descarga                                # Windows no renombra archivos abiertos
    temporal.replace(ruta)
    return db.DBNStore.from_file(ruta)


def bloques(tienda, cfg: Config):
    """DBNStore → bloques de to_ndarray(); un arreglo estructurado → rebanadas del mismo tamaño."""
    if hasattr(tienda, "to_ndarray"):
        partes = tienda.to_ndarray(count=cfg.bloque)
        if isinstance(partes, np.ndarray):
            yield partes
        else:
            yield from partes
    else:
        for i in range(0, len(tienda), cfg.bloque):
            yield tienda[i:i + cfg.bloque]


# =============================================================================
# 3. HIGIENE Y MOTOR 1 · EVENTOS — la agresión exacta que reporta CME, por bloques
# =============================================================================
# El arreglo que entrega to_ndarray() del esquema TBBO (y el que escribe el simulador).
DTYPE_TBBO = np.dtype([("ts_recv", "<u8"), ("ts_event", "<u8"), ("instrument_id", "<u4"), ("action", "S1"),
                       ("side", "S1"), ("price", "<i8"), ("size", "<u4"), ("flags", "u1"), ("sequence", "<u4"),
                       ("bid_px_00", "<i8"), ("ask_px_00", "<i8"), ("bid_sz_00", "<u4"), ("ask_sz_00", "<u4")])

REGLAS = ("no es operación (action ≠ T)", "precio indefinido o tamaño 0", "precio fuera del tick",
          "sin agresor (side N: subasta, implícitas)")


def normalizar(arr: np.ndarray) -> dict:
    """
    Un bloque de to_ndarray() (tbbo, trades, mbp-1 o mbp-10) → columnas con nombres fijos.
    trades no trae libro: bid/ask quedan indefinidos y el módulo trabaja sin él.
    """
    nombres = arr.dtype.names
    n = len(arr)

    def col(k, defecto, dt=np.int64):
        return arr[k].astype(dt) if k in nombres else np.full(n, defecto, dt)

    t = col("ts_event", 0)
    return {"t": t, "tr": col("ts_recv", 0) if "ts_recv" in nombres else t.copy(),
            "inst": col("instrument_id", 0),
            "accion": arr["action"] if "action" in nombres else np.full(n, b"T", "S1"),
            "lado": arr["side"] if "side" in nombres else np.full(n, b"N", "S1"),
            "precio": col("price", UNDEF_PRICE), "tam": col("size", 0), "flags": col("flags", 0),
            "seq": col("sequence", 0), "bpx": col("bid_px_00", UNDEF_PRICE), "apx": col("ask_px_00", UNDEF_PRICE),
            "bsz": col("bid_sz_00", 0), "asz": col("ask_sz_00", 0), "tiene_libro": "bid_px_00" in nombres}


def higiene(r: dict, tick_ns_: int, cfg: Config) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict, int]:
    """
    ¿Qué registros son una AGRESIÓN válida? En orden, cada registro se cuenta en la primera regla
    que falla:
      1. no es una operación (en mbp-1/mbp-10 vienen también altas y cancelaciones);
      2. precio indefinido o tamaño 0;
      3. precio que no es múltiplo del tick;
      4. side 'N': sin agresor (subasta de apertura, operaciones implícitas) — su volumen se
         reporta aparte, no se le inventa dirección.
    Aparte, ¿el libro JUSTO ANTES es una referencia válida? Definido, con tamaños, sin cruzar ni
    trabar, spread ≤ `spread_max_ticks`, en el tick y sin F_MAYBE_BAD_BOOK. Un libro malo no tira
    la operación: sólo le quita el contexto (spread, profundidad visible, mid).
    Devuelve (válida, signo ±1, libro válido, conteos, volumen sin agresor).

    [v1] Tu script toma side == 'A' como COMPRA. En Databento el side de una operación es el del
    AGRESOR: 'B' = compra agresiva (pega en el ask), 'A' = venta agresiva (pega en el bid). Tu
    "Buy" son ventas, tu CVD sale con el signo al revés y tus retornos "tras compras" son tras
    ventas. El chequeo de cordura lo demuestra con TUS datos: las compras agresivas se hacen en el
    ask del libro previo.
    """
    accion, lado, precio, tam = r["accion"], r["lado"], r["precio"], r["tam"]
    es_t = accion == b"T"
    malo = es_t & ((tam <= 0) | (precio <= 0) | (precio == UNDEF_PRICE))
    fuera = es_t & ~malo & ((precio % tick_ns_) != 0)
    signo = (lado == b"B").astype(np.int64) - (lado == b"A").astype(np.int64)
    sin_lado = es_t & ~malo & ~fuera & (signo == 0)
    valida = es_t & ~malo & ~fuera & (signo != 0)
    conteo = {REGLAS[0]: int((~es_t).sum()), REGLAS[1]: int(malo.sum()), REGLAS[2]: int(fuera.sum()),
              REGLAS[3]: int(sin_lado.sum())}
    bpx, apx, bsz, asz = r["bpx"], r["apx"], r["bsz"], r["asz"]
    with np.errstate(all="ignore"):
        definido = ((bpx != UNDEF_PRICE) & (apx != UNDEF_PRICE) & (bpx > 0) & (apx > 0)
                    & (bsz > 0) & (asz > 0))
        libro = (definido & (bpx < apx) & ((apx - bpx) <= cfg.spread_max_ticks * tick_ns_)
                 & ((r["flags"] & F_MAYBE_BAD_BOOK) == 0)
                 & ((bpx % tick_ns_) == 0) & ((apx % tick_ns_) == 0))
    if not r["tiene_libro"]:
        libro = np.zeros(len(libro), bool)
    return valida, signo, libro, conteo, int(tam[sin_lado].sum())


COLS_EVENTO = ("t", "tr", "inst", "lado", "vol", "qpx", "n_prints", "n_niveles", "px_ini", "px_fin",
               "px_min", "px_max", "vol_n1", "bid0", "ask0", "bsz0", "asz0", "libro0", "seq0")


def agregar_eventos(v: dict) -> dict:
    """
    Operaciones válidas (ya en orden) → EVENTOS. Un evento es la racha de registros con el mismo
    ts_event, el mismo agresor y el mismo contrato: en CME todas las ejecuciones de UNA orden
    agresiva comparten la hora de la casación (TransactTime), aunque peguen contra varias órdenes
    y varios niveles de precio. Es la orden agresiva tal como entró al motor de casación.

    [v1] Tu script la reconstruye con ventanas de reloj de 100 ms (index.floor) agrupadas por
    precio y lado: un barrido de 3 niveles queda partido en 3 "trades" (uno por precio), una
    orden que cae en el borde de dos ventanas cuenta doble, y dos órdenes distintas dentro de
    los mismos 100 ms se suman como si fueran una.
    """
    t, s, inst, px, q = v["t"], v["s"], v["inst"], v["px"], v["q"]
    n = len(t)
    if n == 0:
        return {c: np.zeros(0, np.int64) for c in COLS_EVENTO} | {"libro0": np.zeros(0, bool)}
    start = np.r_[True, (t[1:] != t[:-1]) | (s[1:] != s[:-1]) | (inst[1:] != inst[:-1])]
    i0 = np.flatnonzero(start)
    fin = np.r_[i0[1:], n] - 1
    eid = np.cumsum(start) - 1
    cambio = np.r_[False, px[1:] != px[:-1]] & ~start
    en_ini = px == px[i0][eid]
    return {"t": t[i0], "tr": v["tr"][i0], "inst": inst[i0], "lado": s[i0],
            "vol": np.add.reduceat(q, i0), "qpx": np.add.reduceat(q * px, i0),
            "n_prints": (fin - i0 + 1).astype(np.int64),
            "n_niveles": 1 + np.add.reduceat(cambio.astype(np.int64), i0),
            "px_ini": px[i0], "px_fin": px[fin],
            "px_min": np.minimum.reduceat(px, i0), "px_max": np.maximum.reduceat(px, i0),
            "vol_n1": np.add.reduceat(np.where(en_ini, q, 0), i0),
            "bid0": v["bid"][i0], "ask0": v["ask"][i0], "bsz0": v["bsz"][i0], "asz0": v["asz"][i0],
            "libro0": v["libro"][i0], "seq0": v["seq"][i0]}


class MotorEventos:
    """
    Motor 1 · EVENTOS (vectorizado). Recorre el DBN por bloques, aplica la higiene y arma los
    eventos. El último evento de cada bloque puede seguir en el siguiente: sus operaciones viajan
    en `self.pend` y se anteponen al bloque que sigue, así que procesar por bloques da
    EXACTAMENTE lo mismo que de un jalón (una prueba lo verifica). El tiempo se hace monótono
    (máximo acumulado de ts_event), igual que en el motor incremental.
    También guarda, compactas, las operaciones crudas que necesita la réplica de tu script.
    """

    CAMPOS_V = ("t", "tr", "inst", "s", "px", "q", "bid", "ask", "bsz", "asz", "libro", "seq")

    def __init__(self, cfg: Config, tick_ns_: int, guardar_crudo: bool = True):
        self.cfg = cfg
        self.tick = int(tick_ns_)
        self.partes: list[dict] = []
        self.pend: dict | None = None
        self.conteo = {r: 0 for r in REGLAS}
        self.registros = 0
        self.operaciones = 0
        self.volumen = 0
        self.vol_sin_lado = 0
        self.libro_malo = 0
        self.ts_event_atras = 0
        self.latencias: list[np.ndarray] = []
        self.t_max = -1
        self.tiene_libro = False
        self.guardar_crudo = guardar_crudo
        self.crudo: list[dict] = []

    def procesar(self, arr: np.ndarray, final: bool = False) -> None:
        if arr is None or not len(arr):
            if final:
                self.cerrar()
            return
        r = normalizar(arr)
        self.tiene_libro |= r["tiene_libro"]
        n = len(r["t"])
        self.registros += n
        t = r["t"].copy()
        self.ts_event_atras += int(np.sum(np.diff(t) < 0)) + int(self.t_max >= 0 and t[0] < self.t_max)
        if self.t_max >= 0:
            t[0] = max(int(t[0]), self.t_max)
        t = np.maximum.accumulate(t)
        self.t_max = int(t[-1])
        if sum(len(x) for x in self.latencias) < 200_000:
            self.latencias.append((r["tr"] - r["t"])[:50_000])
        valida, signo, libro, conteo, vol_n = higiene(r, self.tick, self.cfg)
        for k, c in conteo.items():
            self.conteo[k] += c
        self.vol_sin_lado += vol_n
        self.operaciones += int(valida.sum())
        self.volumen += int(r["tam"][valida].sum())
        self.libro_malo += int((valida & ~libro).sum())
        if self.guardar_crudo:
            es_t = (r["accion"] == b"T") & (r["precio"] > 0) & (r["precio"] != UNDEF_PRICE)
            self.crudo.append({"t": t[es_t], "tr": r["tr"][es_t], "inst": r["inst"][es_t],
                               "s": signo[es_t].astype(np.int8), "precio": r["precio"][es_t],
                               "q": r["tam"][es_t], "bpx": r["bpx"][es_t], "apx": r["apx"][es_t]})
        tk = self.tick
        v = {"t": t[valida], "tr": r["tr"][valida], "inst": r["inst"][valida], "s": signo[valida],
             "px": r["precio"][valida] // tk, "q": r["tam"][valida],
             "bid": np.where(libro, r["bpx"] // tk, -1)[valida], "ask": np.where(libro, r["apx"] // tk, -1)[valida],
             "bsz": np.where(libro, r["bsz"], 0)[valida], "asz": np.where(libro, r["asz"], 0)[valida],
             "libro": libro[valida], "seq": r["seq"][valida]}
        if self.pend is not None:
            v = {k: np.r_[self.pend[k], v[k]] for k in self.CAMPOS_V}
            self.pend = None
        m = len(v["t"])
        if m == 0:
            return
        if final:
            self.partes.append(agregar_eventos(v))
            return
        # el último evento queda pendiente: puede continuar en el bloque siguiente
        tt, ss, ii = v["t"], v["s"], v["inst"]
        cortes = np.flatnonzero((tt[1:] != tt[:-1]) | (ss[1:] != ss[:-1]) | (ii[1:] != ii[:-1])) + 1
        ult = int(cortes[-1]) if len(cortes) else 0
        if ult > 0:
            self.partes.append(agregar_eventos({k: x[:ult] for k, x in v.items()}))
        self.pend = {k: x[ult:] for k, x in v.items()}

    def cerrar(self) -> None:
        if self.pend is not None and len(self.pend["t"]):
            self.partes.append(agregar_eventos(self.pend))
        self.pend = None

    def eventos(self) -> pd.DataFrame:
        partes = [p for p in self.partes if len(p["t"])]
        if not partes:
            return pd.DataFrame({c: np.zeros(0, np.int64) for c in COLS_EVENTO})
        return pd.DataFrame({c: np.concatenate([p[c] for p in partes]) for c in COLS_EVENTO})

    def operaciones_crudas(self) -> dict:
        if not self.crudo:
            return {}
        return {k: np.concatenate([c[k] for c in self.crudo]) for k in self.crudo[0]}


def correr_motor(tienda, cfg: Config, verbose: bool = True, guardar_crudo: bool = True
                 ) -> tuple[pd.DataFrame, MotorEventos]:
    """DBNStore (o arreglo estructurado) → eventos, bloque por bloque."""
    motor = MotorEventos(cfg, tick_ns(cfg.symbol), guardar_crudo=guardar_crudo)
    inicio = time.time()
    for k, arr in enumerate(bloques(tienda, cfg)):
        motor.procesar(arr)
        if verbose and (k + 1) % 5 == 0:
            print(f"   … {motor.registros:,} registros ({time.time() - inicio:.0f} s)")
    motor.cerrar()
    if motor.registros == 0:
        sys.exit("❌ No llegaron registros.")
    return motor.eventos(), motor


def preparar_eventos(E: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """
    Añade a cada evento su sesión, su segundo de sesión, la franja (horario regular o no), el mid
    del libro previo (en ticks), lo VISIBLE en el primer nivel que atacó y la liquidez OCULTA que
    apareció: lo ejecutado en ese precio por encima de lo que se veía (iceberg o implícita). Y el
    último evento del mismo tramo (misma sesión y mismo contrato): nada se mide cruzando un roll
    ni el cierre de la sesión.
    """
    E = E.copy()
    n = len(E)
    dia, seg = reloj_sesion(E["t"].to_numpy(), cfg.tz_mercado)
    E["sesion"], E["seg"] = dia, seg
    r0, r1 = segundo_de_hora(cfg.rth_ct[0]), segundo_de_hora(cfg.rth_ct[1])
    E["rth"] = (seg >= r0) & (seg < r1)
    lib = E["libro0"].to_numpy().astype(bool)
    lado = E["lado"].to_numpy()
    bid, ask = E["bid0"].to_numpy(), E["ask0"].to_numpy()
    E["mid0"] = np.where(lib, (bid + ask) / 2.0, np.nan)
    mejor = np.where(lado > 0, ask, bid)
    visible = np.where(lado > 0, E["asz0"].to_numpy(), E["bsz0"].to_numpy())
    ok = lib & (E["px_ini"].to_numpy() == mejor)
    E["disp"] = np.where(ok, visible, np.nan)
    E["oculta"] = np.where(ok, np.maximum(E["vol_n1"].to_numpy() - visible, 0), 0).astype(np.int64)
    inst = E["inst"].to_numpy()
    if n:
        nuevo = np.r_[True, (dia[1:] != dia[:-1]) | (inst[1:] != inst[:-1])]
        tramo = np.cumsum(nuevo) - 1
        fin_tramo = np.r_[np.flatnonzero(nuevo)[1:], n] - 1
        E["fin_tramo"] = fin_tramo[tramo]
    else:
        E["fin_tramo"] = np.zeros(0, np.int64)
    return E


# =============================================================================
# 4. MOTOR 2 · HUELLAS, MAGNITUD EMPÍRICA Y TIPO DE FLUJO
# =============================================================================
def asignar_huellas(t: np.ndarray, lado: np.ndarray, ses: np.ndarray, inst: np.ndarray,
                    gap_ns: int, cap_ns: int) -> np.ndarray:
    """
    Eventos → HUELLAS: la segunda capa de agrupación. Un algoritmo que parte una orden grande la
    dispara en pedazos separados por milisegundos; una huella junta los eventos del MISMO lado
    mientras el hueco desde el anterior sea ≤ `gap_ns`, la huella no dure más de `cap_ns`, y sigan
    en la misma sesión y el mismo contrato. Las agresiones del lado contrario no la cortan. Con
    gap 0 cada evento es su propia huella.
    """
    n = len(t)
    hid = np.full(n, -1, dtype=np.int64)
    siguiente = 0
    for s in (1, -1):
        idx = np.flatnonzero(lado == s)
        if not len(idx):
            continue
        ts, ss, ii = t[idx], ses[idx], inst[idx]
        corte = np.r_[True, (np.diff(ts) > gap_ns) | (ss[1:] != ss[:-1]) | (ii[1:] != ii[:-1])]
        ini = np.flatnonzero(corte)
        fin = np.r_[ini[1:], len(ts)]
        for k in np.flatnonzero(ts[fin - 1] - ts[ini] > cap_ns):     # cadenas más largas que el tope
            a, b = int(ini[k]), int(fin[k])
            j = a
            while True:
                j2 = a + int(np.searchsorted(ts[a:b], ts[j] + cap_ns, side="right"))
                if j2 >= b:
                    break
                corte[j2] = True
                j = j2
        local = np.cumsum(corte) - 1
        hid[idx] = siguiente + local
        siguiente += int(local[-1]) + 1
    return hid


def agrupar_huellas(E: pd.DataFrame, cfg: Config) -> tuple[pd.DataFrame, np.ndarray]:
    """Eventos (preparados) → tabla de huellas en orden de inicio, y la huella de cada evento."""
    n = len(E)
    if n == 0:
        return pd.DataFrame(), np.zeros(0, np.int64)
    t = E["t"].to_numpy()
    hid = asignar_huellas(t, E["lado"].to_numpy(), E["sesion"].to_numpy(), E["inst"].to_numpy(),
                          int(round(cfg.rafaga_ms * NS_MS)), int(round(cfg.rafaga_max_ms * NS_MS)))
    o = np.argsort(hid, kind="stable")
    hs = hid[o]
    i0 = np.flatnonzero(np.r_[True, hs[1:] != hs[:-1]])
    fin = np.r_[i0[1:], n] - 1
    pri, ult = o[i0], o[fin]

    def c(nombre_):
        return E[nombre_].to_numpy()

    def suma(nombre_):
        return np.add.reduceat(c(nombre_)[o], i0)

    H = pd.DataFrame({
        "t_ini": t[pri], "t_fin": t[ult], "inst": c("inst")[pri], "lado": c("lado")[pri],
        "sesion": c("sesion")[pri], "seg": c("seg")[pri], "rth": c("rth")[pri],
        "vol": suma("vol"), "qpx": suma("qpx"), "n_eventos": (fin - i0 + 1).astype(np.int64),
        "n_prints": suma("n_prints"), "niv_max": np.maximum.reduceat(c("n_niveles")[o], i0),
        "px_min": np.minimum.reduceat(c("px_min")[o], i0), "px_max": np.maximum.reduceat(c("px_max")[o], i0),
        "px_ini": c("px_ini")[pri], "px_fin": c("px_fin")[ult],
        "bid0": c("bid0")[pri], "ask0": c("ask0")[pri], "bsz0": c("bsz0")[pri], "asz0": c("asz0")[pri],
        "libro0": c("libro0")[pri], "mid0": c("mid0")[pri], "disp0": c("disp")[pri],
        "oculta": suma("oculta"), "i_ini": pri.astype(np.int64), "i_fin": ult.astype(np.int64),
        "seq0": c("seq0")[pri], "tr0": c("tr")[pri]})
    orden = np.argsort(H["t_ini"].to_numpy(), kind="stable")
    H = H.iloc[orden].reset_index(drop=True)
    nuevo = np.empty(len(orden), np.int64)
    nuevo[orden] = np.arange(len(orden))
    H["vwap"] = H["qpx"] / H["vol"]
    H["span"] = H["px_max"] - H["px_min"] + 1
    H["dur_ms"] = (H["t_fin"] - H["t_ini"]) / NS_MS
    return H, nuevo[hid]


def umbral_discreto(ref: np.ndarray, p: float) -> float:
    """
    El tamaño ENTERO más chico v tal que, en la referencia, la fracción de huellas con tamaño ≥ v
    no pase de 1 − p. Con tamaños enteros hay muchos empates: con un cuantil interpolado, "≥ p95"
    puede marcar el 8 % de las huellas. Así una clase nunca pesa más de lo que dice su nombre.
    """
    ref = np.asarray(ref)
    n = len(ref)
    if n == 0:
        return np.nan
    permitido = math.floor((1.0 - p) * n + 1e-9)
    vals = np.unique(ref)
    cuantos = n - np.searchsorted(ref, vals, side="left")
    ok = cuantos <= permitido
    return float(vals[ok][0]) if ok.any() else float(ref[-1] + 1)


def hill(x: np.ndarray, frac: float = 0.01, kmin: int = 50) -> tuple[float, int]:
    """Exponente de la cola de Hill (1975) con las k observaciones más grandes."""
    x = np.sort(np.asarray(x, float)[np.isfinite(x) & (np.asarray(x, float) > 0)])[::-1]
    k = max(kmin, int(frac * len(x)))
    if len(x) <= k + 1 or x[k] <= 0:
        return np.nan, k
    s = float(np.sum(np.log(x[:k] / x[k])))
    return (k / s if s > 0 else np.nan), k


def clasificar_magnitud(H: pd.DataFrame, cfg: Config) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """
    Magnitud EMPÍRICA y CAUSAL. Para cada sesión, la distribución de referencia son las huellas de
    las `ventana_sesiones` sesiones ANTERIORES con datos (la actual no entra en su propia escala),
    por franja: el horario regular se compara con el horario regular y la noche con la noche.
    Umbrales GRANDE / MEGA / BALLENA = tamaños enteros con a lo más 5 % / 1 % / 0.1 % de la
    referencia por encima (umbral_discreto), más un piso absoluto opcional. El percentil de cada
    huella es su rango medio dentro de esa referencia.

    [v1] Tu script calcula p95/p99/p99.9 con TODA la muestra, incluida la parte que todavía no
    ha pasado: el umbral de las 8:00 del martes usa el jueves. Y mezcla Asia con la apertura de
    Nueva York: de noche casi nada llega a "grande" y en la apertura casi todo.
    """
    n = len(H)
    pct = np.full(n, np.nan)
    clase = np.full(n, -1, dtype=np.int64)
    if n == 0:
        return pd.DataFrame(), pct, clase
    ses = H["sesion"].to_numpy()
    fr = H["rth"].to_numpy().astype(int) if cfg.por_franja else np.zeros(n, int)
    vol = H["vol"].to_numpy()
    sesiones = np.unique(ses)
    filas = []
    for f in np.unique(fr):
        por_ses = {s: np.sort(vol[(ses == s) & (fr == f)]) for s in sesiones}
        for k, s in enumerate(sesiones):
            previas = sesiones[max(0, k - cfg.ventana_sesiones):k]
            ref = np.sort(np.concatenate([por_ses[p] for p in previas])) if len(previas) else np.zeros(0)
            m = (ses == s) & (fr == f)
            fila = {"sesion": int(s), "franja": int(f), "n_ref": len(ref), "sesiones_ref": len(previas),
                    "n": int(m.sum()), "q_grande": np.nan, "q_mega": np.nan, "q_ballena": np.nan}
            if len(ref) >= cfg.min_ref:
                q = [max(umbral_discreto(ref, p), float(cfg.piso_contratos))
                     for p in (cfg.p_grande, cfg.p_mega, cfg.p_ballena)]
                fila.update(q_grande=q[0], q_mega=q[1], q_ballena=q[2])
                v = vol[m]
                izq = np.searchsorted(ref, v, side="left")
                der = np.searchsorted(ref, v, side="right")
                pct[m] = (izq + 0.5 * (der - izq)) / len(ref)
                clase[m] = (v >= q[0]).astype(int) + (v >= q[1]) + (v >= q[2])
            filas.append(fila)
    U = pd.DataFrame(filas).sort_values(["sesion", "franja"]).reset_index(drop=True)
    return U, pct, clase


def tipificar(H: pd.DataFrame, cfg: Config) -> np.ndarray:
    """
    Tipo de flujo de cada huella, en este orden de prioridad (de la evidencia más específica a
    la más general):
      ABSORCIÓN    todo en UN precio y, en al menos una casación, se ejecutó más de lo que se veía
                   en ese nivel JUSTO ANTES de ella (≥ `oculta_min` contratos de más): había
                   liquidez fuera de la vista —iceberg o implícita— y el nivel aguantó. Es evidencia
                   dura: una sola casación no puede llevarse más de lo que hay. Necesita libro.
      FRAGMENTADA  ≥ `min_eventos_fragmentada` agresiones del mismo lado separadas por
                   milisegundos: una orden partida por un algoritmo (o varias que coincidieron).
      BARRIDO      alguna casación cruzó ≥ 2 niveles de precio: urgencia, se lleva la liquidez
                   de varios niveles de un golpe.
      BLOQUE       lo demás: una o dos agresiones que se llevaron lo visible de un nivel.

    [v1] En tu script FRAGMENTED nunca se asigna (lo pisan las dos reglas siguientes), y tu
    SWEEP es "3 o más trades en el mismo grupo de 100 ms": eso no dice si cruzó niveles. Tu
    hit_price es el mejor precio del libro previo, no el de la operación: un barrido de 3
    niveles queda anotado al precio del primero.
    """
    frag = H["n_eventos"].to_numpy() >= cfg.min_eventos_fragmentada
    absor = (H["span"].to_numpy() == 1) & (H["oculta"].to_numpy() >= max(1, cfg.oculta_min))
    barr = H["niv_max"].to_numpy() >= 2
    return np.select([absor, frag, barr], [2, 3, 1], 0).astype(np.int64)


# =============================================================================
# 5. CLUSTERS, CONTEXTO, IMPACTO Y RASTREO DE CADA ID
# =============================================================================
def asignar_ids(G: pd.DataFrame, symbol: str) -> np.ndarray:
    """ID legible de cada huella grande: raíz + fecha de la sesión (MMDD) + número en la sesión."""
    if not len(G):
        return np.zeros(0, dtype=object)
    ses = G["sesion"].to_numpy()
    k = G.groupby("sesion").cumcount().to_numpy() + 1
    r = raiz(symbol)
    return np.array([f"{r}{fecha_de_dia(s):%m%d}-{i:03d}" for s, i in zip(ses, k)], dtype=object)


def _grupos_cluster(t: np.ndarray, ses: np.ndarray, gap_ns: int, minimo: int) -> np.ndarray:
    """Encadenamiento simple (DBSCAN en 1-D): −1 = aislada; si no, número de cluster."""
    n = len(t)
    if n == 0:
        return np.zeros(0, np.int64)
    nuevo = np.r_[True, (np.diff(t) > gap_ns) | (ses[1:] != ses[:-1])]
    g = np.cumsum(nuevo) - 1
    tam = np.bincount(g)
    es = tam[g] >= minimo
    cid = np.full(n, -1, np.int64)
    if es.any():
        _, cid[es] = np.unique(g[es], return_inverse=True)
    return cid


def detectar_clusters(G: pd.DataFrame, cfg: Config) -> tuple[np.ndarray, pd.DataFrame]:
    """
    Clusters de huellas ≥ `cluster_clase_min` (MEGA por omisión): se encadenan mientras el hueco
    entre una y la siguiente sea ≤ `cluster_gap_s` (dentro de la sesión); con ≥ `cluster_min`
    miembros es un cluster. ¿Por qué MEGA y no GRANDE? Una GRANDE es el 5 % de las huellas: en
    horario regular sale una cada ~30 s y un hueco de 60 s encadena media sesión. En la simulación
    eso da clusters de 80+ huellas y 28 min que NO se distinguen del azar (p = 0.88); con MEGA son
    episodios de ~45 s, ×1.4 más agrupados que el azar (p = 0.005). --cluster-clase 1 lo regresa.
    Cada uno lleva su ID, duración, volumen comprado y vendido, VWAP, rango y PUREZA = |neto| / total:
      COMPRADOR / VENDEDOR   pureza ≥ `pureza_min` (agresión de un solo lado)
      DISPUTA                pureza menor (los dos lados pelean el mismo tramo)

    [v1] Tu cluster mide 60 s desde su PRIMER trade (una racha continua de 5 min queda partida
    en 5), mezcla compras con ventas y lo llama "acumulación/distribución" sin ver de qué lado
    va; y dos grupos de la misma ventana de 100 ms ya cuentan como "cluster".
    """
    t = G["t_ini"].to_numpy()
    cid = _grupos_cluster(t, G["sesion"].to_numpy(), int(cfg.cluster_gap_s * NS), cfg.cluster_min)
    filas = []
    r = raiz(cfg.symbol)
    cuenta_ses: dict[int, int] = {}
    for c in range(int(cid.max()) + 1 if len(cid) else 0):
        m = cid == c
        g = G[m]
        lado, vol = g["lado"].to_numpy(), g["vol"].to_numpy()
        compra, venta = int(vol[lado > 0].sum()), int(vol[lado < 0].sum())
        tot = compra + venta
        pureza = abs(compra - venta) / tot if tot else 0.0
        direc = int(np.sign(compra - venta)) if pureza >= cfg.pureza_min else 0
        ses = int(g["sesion"].iloc[0])
        cuenta_ses[ses] = cuenta_ses.get(ses, 0) + 1
        por_tipo = g.groupby("tipo")["vol"].sum()
        filas.append({"cluster": f"C{r}{fecha_de_dia(ses):%m%d}-{cuenta_ses[ses]:02d}", "k": c, "sesion": ses,
                      "t_ini": int(g["t_ini"].min()), "t_fin": int(g["t_fin"].max()), "n": int(m.sum()),
                      "vol": tot, "compra": compra, "venta": venta, "neto": compra - venta, "pureza": pureza,
                      "direccion": direc, "vwap": float(g["qpx"].sum() / tot),
                      "px_min": int(g["px_min"].min()), "px_max": int(g["px_max"].max()),
                      "clase_max": int(g["clase"].max()), "tipo_dom": int(por_tipo.idxmax()),
                      "ids": " ".join(g["id"].astype(str).tolist()[:12]) + (" …" if m.sum() > 12 else "")})
    C = pd.DataFrame(filas)
    if len(C):
        C["dur_s"] = (C["t_fin"] - C["t_ini"]) / NS
    return cid, C


def prueba_clusters(G: pd.DataFrame, cid: np.ndarray, H: pd.DataFrame, cfg: Config, semilla: int = 12345) -> dict:
    """
    ¿Los grandes se agrupan MÁS que la actividad misma? Hipótesis nula: ser grande no depende del
    momento, más allá de cuánto se opera. Se simula repartiendo la etiqueta "grande" al azar entre
    TODAS las huellas de la misma sesión y franja (las mismas cantidades) y se cuenta cuántas
    quedan en clusters, `n_permutaciones` veces. p = (1 + #{azar ≥ real}) / (1 + n). La apertura,
    donde todo se amontona, ya está en la nula —con su ritmo exacto, segundo a segundo—: lo que
    sobra es agrupamiento propio de los grandes.
    Dirección: ¿los clusters son más de un solo lado que si los lados se barajan dentro de la
    sesión? Mismo cálculo con la pureza ponderada por volumen.
    """
    n = len(G)
    out = {"n": n, "en_cluster": int((cid >= 0).sum()) if n else 0, "p": np.nan, "esperado": np.nan,
           "razon": np.nan, "pureza": np.nan, "pureza_azar": np.nan, "p_dir": np.nan, "_azar": np.zeros(0)}
    if n < 10 or cfg.n_permutaciones < 1:
        return out
    rng = np.random.default_rng(semilla)
    ses = G["sesion"].to_numpy()
    W = H[H["ventana"].to_numpy()]
    tw, sw, fw = (W[c].to_numpy() for c in ("t_ini", "sesion", "rth"))
    grupos = []
    for (s_, f_), cuenta in G.groupby(["sesion", "rth"]).size().items():
        pool = np.flatnonzero((sw == s_) & (fw == f_))
        grupos.append((pool, int(min(cuenta, len(pool))), s_))
    gap = int(cfg.cluster_gap_s * NS)
    azar = np.zeros(cfg.n_permutaciones)
    for k in range(cfg.n_permutaciones):
        sel = np.concatenate([rng.choice(pool, c, replace=False) for pool, c, _ in grupos])
        tp, sp = tw[sel], sw[sel]
        o = np.lexsort((tp, sp))
        azar[k] = float((_grupos_cluster(tp[o], sp[o], gap, cfg.cluster_min) >= 0).sum())
    obs = out["en_cluster"]
    out.update(p=(1 + float((azar >= obs).sum())) / (1 + len(azar)), esperado=float(azar.mean()),
               razon=obs / azar.mean() if azar.mean() > 0 else np.nan, _azar=azar)
    # --- dirección ---
    m = cid >= 0
    if m.sum() >= 4:
        sv = (G["lado"].to_numpy() * G["vol"].to_numpy()).astype(float)
        v = G["vol"].to_numpy().astype(float)

        def pureza(s_v):
            neto = np.bincount(cid[m], weights=s_v[m])
            return float(np.abs(neto).sum() / v[m].sum())

        p_obs = pureza(sv)
        bar = np.zeros(cfg.n_permutaciones)
        grupos = [np.flatnonzero(ses == s) for s in np.unique(ses)]
        for k in range(cfg.n_permutaciones):
            s2 = sv.copy()
            for gidx in grupos:
                s2[gidx] = np.abs(sv[gidx]) * rng.permutation(np.sign(sv[gidx]))
            bar[k] = pureza(s2)
        out.update(pureza=p_obs, pureza_azar=float(bar.mean()),
                   p_dir=(1 + float((bar >= p_obs).sum())) / (1 + len(bar)))
    return out


def contexto(H: pd.DataFrame, E: pd.DataFrame, cfg: Config, con_libro: bool) -> pd.DataFrame:
    """
    Contexto CAUSAL de cada huella, con lo que se sabía justo ANTES de su primer evento:
      · posición en el rango de la sesión hasta ese momento (0 = mínimo, 1 = máximo);
      · distancia al VWAP de la sesión, en ticks;
      · CVD de la sesión (compras − ventas agresivas, reiniciado en cada sesión);
      · movimiento y flujo neto de los 5 minutos previos (para separar el impacto del momentum).

    [v1] Tu "posición en el rango" usa un máximo/mínimo de 200 SEGUNDOS (200 filas de un mid
    remuestreado a 1 s, no 200 barras) y lo asigna con reindex(method='nearest'), que puede
    tomar un valor POSTERIOR al trade; fila por fila, además, es lentísimo.
    """
    out = pd.DataFrame(index=H.index)
    if not len(H):
        return out
    ses_e = E["sesion"].to_numpy()
    g = pd.Series(ses_e)
    hi = pd.Series(E["px_max"].to_numpy()).groupby(g).cummax().to_numpy()
    lo = pd.Series(E["px_min"].to_numpy()).groupby(g).cummin().to_numpy()
    cq = pd.Series(E["vol"].to_numpy()).groupby(g).cumsum().to_numpy().astype(float)
    cqp = pd.Series(E["qpx"].to_numpy()).groupby(g).cumsum().to_numpy().astype(float)
    sv = E["lado"].to_numpy() * E["vol"].to_numpy()
    cvd = pd.Series(sv).groupby(g).cumsum().to_numpy().astype(float)
    acum = np.cumsum(sv).astype(float)
    i0 = H["i_ini"].to_numpy()
    prev = i0 - 1
    okp = (prev >= 0) & (ses_e[np.maximum(prev, 0)] == H["sesion"].to_numpy())
    pv = np.maximum(prev, 0)
    rango = np.where(okp, hi[pv] - lo[pv], np.nan)
    vw = H["vwap"].to_numpy()
    out["pos_rango"] = np.where(okp & (rango >= cfg.min_rango_ticks), (vw - lo[pv]) / rango, np.nan)
    out["dist_vwap"] = np.where(okp, vw - cqp[pv] / np.where(cq[pv] > 0, cq[pv], np.nan), np.nan)
    out["cvd_previo"] = np.where(okp, cvd[pv], 0.0)
    t_e = E["t"].to_numpy()
    j5 = np.searchsorted(t_e, H["t_ini"].to_numpy() - 300 * NS, side="left")
    j5c = np.minimum(j5, len(t_e) - 1)
    ok5 = okp & (j5 <= prev) & (ses_e[j5c] == H["sesion"].to_numpy())
    precio_e = E["mid0"].to_numpy() if con_libro else E["px_fin"].to_numpy().astype(float)
    p_ahora = H["mid0"].to_numpy() if con_libro else precio_e[pv]
    out["ret_previo"] = np.where(ok5, p_ahora - precio_e[j5c], np.nan)
    base = np.where(j5c > 0, acum[np.maximum(j5c - 1, 0)], 0.0)
    out["flujo_previo"] = np.where(ok5, acum[pv] - base, np.nan)
    return out


def precios_futuros(H: pd.DataFrame, E: pd.DataFrame, cfg: Config, con_libro: bool,
                    mascara: np.ndarray | None = None) -> tuple[np.ndarray, dict]:
    """
    Referencia y precios futuros de cada huella, en ticks, SIN cruzar sesión ni contrato:
      · con libro (tbbo/mbp): referencia = mid del libro JUSTO ANTES del primer evento; precio en
        t_fin + h = mid del libro previo a la primera operación a partir de t_fin + h (el estado
        del libro más cercano que se observa). h = 0 es el primer libro DESPUÉS de la huella.
      · sin libro (trades): último precio operado antes del primer evento y antes de t_fin + h.
        Trae el rebote bid-ask: el reporte lo advierte.
    NaN —no 0— si la sesión termina antes, si hay un roll o si el siguiente libro llega más de
    max(rancio_max_s, h/2) después.

    [v1] Tu get_fwd_ret devuelve 0.0 cuando no hay datos: cada trade cerca del final cuenta como
    "no se movió" y jala el promedio a cero. Y en un roll del continuo el "retorno" es el salto
    entre contratos.
    """
    n = len(H)
    m = np.ones(n, bool) if mascara is None else mascara
    t_e = E["t"].to_numpy()
    ft = E["fin_tramo"].to_numpy()
    mid_e = E["mid0"].to_numpy()
    pxf = E["px_fin"].to_numpy().astype(float)
    i0, i1 = H["i_ini"].to_numpy(), H["i_fin"].to_numpy()
    t1 = H["t_fin"].to_numpy()
    if con_libro:
        p0 = np.where(m, H["mid0"].to_numpy(), np.nan)
    else:
        prev = i0 - 1
        okp = (prev >= 0) & (ft[np.maximum(prev, 0)] == ft[i0])
        p0 = np.where(m & okp, pxf[np.maximum(prev, 0)], np.nan)
    fut = {}
    for h in (0,) + tuple(cfg.horizontes_s):
        tq = t1 + int(h) * NS
        j = np.searchsorted(t_e, t1, side="right") if h == 0 else np.searchsorted(t_e, tq, side="left")
        jc = np.minimum(j, len(t_e) - 1)
        ok = m & (j < len(t_e)) & (j <= ft[i1])
        if con_libro:
            rancio = max(cfg.rancio_max_s, h / 2.0) * NS
            ok &= (t_e[jc] - tq) <= rancio
            fut[h] = np.where(ok, mid_e[jc], np.nan)
        else:
            fut[h] = np.where(ok, pxf[np.maximum(jc - 1, 0)], np.nan)
    return p0, fut


def media_sesiones(v: np.ndarray, g: np.ndarray) -> dict:
    """Media con error estándar AGRUPADO por sesión (Liang-Zeger), t con G − 1 gl e IC 95 %."""
    v = np.asarray(v, float)
    ok = np.isfinite(v)
    v, g = v[ok], np.asarray(g)[ok]
    n = len(v)
    out = {"n": n, "sesiones": 0, "media": np.nan, "se": np.nan, "t": np.nan, "p": np.nan,
           "ic_bajo": np.nan, "ic_alto": np.nan, "acierto": np.nan, "mediana": np.nan}
    if n == 0:
        return out
    media = float(v.mean())
    _, inv = np.unique(g, return_inverse=True)
    G = int(inv.max()) + 1
    out.update(sesiones=G, media=media, acierto=float(np.mean(v > 0)), mediana=float(np.median(v)))
    if G >= 2 and n >= 3:
        s = np.bincount(inv, weights=v - media)
        se = math.sqrt(G / (G - 1) * float((s * s).sum())) / n
        if se > 0:
            tq = t_cuantil(0.975, G - 1)
            out.update(se=se, t=media / se, p=p_t(media / se, G - 1),
                       ic_bajo=media - tq * se, ic_alto=media + tq * se)
    return out


def curva_impacto(vol: np.ndarray, imp: np.ndarray, minimo: int = 30) -> dict:
    """
    Impacto medio contra el tamaño, en cubetas logarítmicas, y el ajuste log I = a + δ log Q.
    Con δ < 1 el impacto es CÓNCAVO: duplicar el tamaño no duplica el movimiento (la ley de la
    raíz cuadrada da δ ≈ 0.5 para metaórdenes; por operación suele salir menor).
    """
    vol = np.asarray(vol, float)
    imp = np.asarray(imp, float)
    ok = np.isfinite(vol) & np.isfinite(imp) & (vol > 0)
    vol, imp = vol[ok], imp[ok]
    out = {"cubetas": pd.DataFrame(), "delta": np.nan, "a": np.nan, "r2": np.nan}
    if len(vol) < minimo * 3:
        return out
    bordes = np.unique(np.round(np.logspace(0, math.log10(vol.max() + 1), 26)).astype(int))
    k = np.searchsorted(bordes, vol, side="right") - 1
    filas = []
    for j in range(len(bordes)):
        s = k == j
        if s.sum() < minimo:
            continue
        x = imp[s]
        filas.append({"desde": int(bordes[j]), "q_media": float(vol[s].mean()), "n": int(s.sum()),
                      "imp": float(x.mean()), "se": float(x.std(ddof=1) / math.sqrt(len(x)))})
    T = pd.DataFrame(filas)
    out["cubetas"] = T
    if len(T) >= 3:
        u = T[T["imp"] > 0]
        if len(u) >= 3:
            X, Y = np.log(u["q_media"].to_numpy()), np.log(u["imp"].to_numpy())
            b, a = np.polyfit(X, Y, 1)
            res = Y - (a + b * X)
            out.update(delta=float(b), a=float(a),
                       r2=float(1 - (res @ res) / max(1e-12, ((Y - Y.mean()) ** 2).sum())))
    return out


def sigma_minuto(E: pd.DataFrame, con_libro: bool) -> dict:
    """σ del cambio de precio a 1 minuto (ticks) de cada sesión, recortando el 0.5 % extremo."""
    if not len(E):
        return {}
    precio = E["mid0"].to_numpy() if con_libro else E["px_fin"].to_numpy().astype(float)
    ok = np.isfinite(precio)
    df = pd.DataFrame({"s": E["sesion"].to_numpy()[ok], "i": E["inst"].to_numpy()[ok],
                       "m": E["t"].to_numpy()[ok] // (60 * NS), "p": precio[ok]})
    ult = df.groupby(["s", "i", "m"], sort=True)["p"].last().reset_index()
    ult["d"] = ult.groupby(["s", "i"])["p"].diff()
    out = {}
    for s, d in ult.dropna().groupby("s")["d"]:
        a = np.abs(d.to_numpy())
        if len(a) < 30:
            continue
        a = a[a <= np.quantile(a, 0.995)]
        out[int(s)] = float(math.sqrt(np.mean(a * a)))
    return out


def rastrear(H: pd.DataFrame, idx: np.ndarray, E: pd.DataFrame, cfg: Config, sig: dict) -> pd.DataFrame:
    """
    El RASTREO de cada ID después de imprimirse: su VWAP queda como nivel L y se le ponen tres
    barreras (López de Prado 2018, cap. 3): una a favor (L ± b), una en contra (L ∓ b) y una
    vertical a `seguimiento_s`. b = barrera_sigma × σ de la ventana de seguimiento, con la σ de
    1 minuto de la sesión ANTERIOR (causal). Se toca primero:
      a favor   → SOSTENIDO (el nivel se defendió y el precio siguió en la dirección del agresor)
      en contra → ROTO      (el precio regresó y atravesó el nivel)
      ninguna   → NEUTRO
    Sin información saldría ~50/50, un poco menos: L es el precio del agresor (en el ask o el
    bid), y el rebote bid-ask y el impacto transitorio lo jalan en contra. Por eso cada grupo se
    compara contra la LÍNEA BASE de huellas normales medida igual, no contra 50 %. También MFE y
    MAE (excursión máxima a favor y en contra) y el resultado al final de la ventana, en ticks.
    """
    filas = {"barrera": [], "estado": [], "t_toque_s": [], "mfe": [], "mae": [], "final": [], "completo": []}
    t_e = E["t"].to_numpy()
    pmx, pmn, pxf = E["px_max"].to_numpy(), E["px_min"].to_numpy(), E["px_fin"].to_numpy()
    ft = E["fin_tramo"].to_numpy()
    sesiones = np.array(sorted(sig))
    T = cfg.seguimiento_s * NS
    for k in idx:
        s = int(H.at[k, "sesion"])
        previas = sesiones[sesiones < s]
        sg = sig[int(previas[-1])] if len(previas) else sig.get(s, np.nan)
        b = max(2.0, cfg.barrera_sigma * sg * math.sqrt(cfg.seguimiento_s / 60.0)) if np.isfinite(sg) else np.nan
        L, lado, i1, tf = float(H.at[k, "vwap"]), int(H.at[k, "lado"]), int(H.at[k, "i_fin"]), int(H.at[k, "t_fin"])
        a = i1 + 1
        lim = int(np.searchsorted(t_e, tf + T, side="right"))
        bnd = min(lim, int(ft[i1]) + 1)
        if a >= bnd or not np.isfinite(b):
            for c, v in (("barrera", b), ("estado", np.nan), ("t_toque_s", np.nan), ("mfe", np.nan),
                         ("mae", np.nan), ("final", np.nan), ("completo", False)):
                filas[c].append(v)
            continue
        hi, lo = pmx[a:bnd], pmn[a:bnd]
        if lado > 0:
            fav, adv = hi >= L + b, lo <= L - b
            mfe, mae = hi.max() - L, L - lo.min()
        else:
            fav, adv = lo <= L - b, hi >= L + b
            mfe, mae = L - lo.min(), hi.max() - L
        jf = int(np.argmax(fav)) if fav.any() else 10 ** 12
        ja = int(np.argmax(adv)) if adv.any() else 10 ** 12
        est = 1 if jf < ja else (-1 if ja < jf else 0)
        j = min(jf, ja)
        filas["barrera"].append(b)
        filas["estado"].append(est)
        filas["t_toque_s"].append((t_e[a + j] - tf) / NS if j < 10 ** 12 else np.nan)
        filas["mfe"].append(float(mfe))
        filas["mae"].append(float(mae))
        filas["final"].append(lado * (float(pxf[bnd - 1]) - L))
        filas["completo"].append(bnd == lim or est != 0)
    return pd.DataFrame(filas, index=idx)


# =============================================================================
# 6. TU SCRIPT (réplica fiel, para medirlo) Y EL MOTOR INCREMENTAL (para Live)
# =============================================================================
TU_WINDOW_MS = 100
TU_CLUSTER_S = 60
TU_HORIZONTES_MIN = (1, 5, 15, 30, 60)


def tu_script(crudo: dict, cfg: Config, t0: int, t1: int, eid_crudo: np.ndarray | None = None) -> dict:
    """
    Réplica de extract_big_trades / detect_clusters / add_context de bigtrade_deepsek.py sobre los
    mismos registros: hit_price = ask si side == 'A' (lo llama compra) y bid si no; ventanas de
    reloj de 100 ms sobre ts_recv (el índice de to_df); grupos (ventana, hit_price, side);
    p95/p99/p99.9 con TODA la muestra; BLOCK si ≤ 2 trades, SWEEP si ≥ 3; clusters de 60 s desde
    el primero; retornos sobre el mid remuestreado a 1 s, con 0.0 si no hay dato.
    Devuelve los grupos y, si se da el evento de cada registro, cuántos eventos quedan partidos.
    """
    out = {"disponible": False}
    if not crudo or not len(crudo.get("t", [])):
        return out
    tr = crudo["tr"]
    sel = (tr >= t0) & (tr < t1)
    if sel.sum() < 100:
        return out
    s = crudo["s"][sel].astype(np.int64)
    bpx, apx = crudo["bpx"][sel], crudo["apx"][sel]
    if np.all(bpx == UNDEF_PRICE):
        return out                                   # trades: tu script necesita el libro
    hit = np.where(s == -1, apx, bpx)
    q = crudo["q"][sel].astype(np.int64)
    ok = hit > 0                                     # tu filtro (UNDEF_PRICE también pasa)
    win = tr[sel] // (TU_WINDOW_MS * NS_MS)
    df = pd.DataFrame({"win": win[ok], "hit": hit[ok], "s": s[ok], "q": q[ok], "pos": np.flatnonzero(ok)})
    g = df.groupby(["win", "hit", "s"], sort=True)
    G = g.agg(total_vol=("q", "sum"), n_trades=("q", "count")).reset_index()
    df["grupo"] = g.ngroup().to_numpy()
    p95, p99, p999 = (float(G["total_vol"].quantile(p)) for p in (0.95, 0.99, 0.999))
    mag = (G["total_vol"].to_numpy() >= p95).astype(int) + (G["total_vol"].to_numpy() >= p99) \
        + (G["total_vol"].to_numpy() >= p999)
    G["mag"] = mag
    G["tipo"] = np.where(G["n_trades"].to_numpy() <= 2, "BLOCK", "SWEEP")    # FRAGMENTED: nunca
    G["dir_tuya"] = np.where(G["s"].to_numpy() == -1, 1, -1)                # 'A' = "Buy"
    big = G[G["mag"] >= 1].copy()
    # clusters: 60 s desde el PRIMER big trade del cluster, sin ver el lado
    tb = (big["win"].to_numpy() * TU_WINDOW_MS) / 1000.0
    cl = np.full(len(big), -1)
    k, ini, miembros = 0, None, []
    for i, x in enumerate(tb):
        if ini is None:
            ini, miembros = x, [i]
        elif x - ini <= TU_CLUSTER_S:
            miembros.append(i)
        else:
            if len(miembros) >= 2:
                cl[miembros] = k
                k += 1
            ini, miembros = x, [i]
    if len(miembros) >= 2:
        cl[miembros] = k
        k += 1
    big["cluster"] = cl
    mixtos = sum(1 for c in range(k) if len(set(big.loc[cl == c, "s"])) > 1)
    # retornos de tu add_context (mid a 1 s, 0.0 sin dato), en bps
    mid = np.where((bpx != UNDEF_PRICE) & (apx != UNDEF_PRICE), (bpx + apx) / 2.0, np.nan)
    seg = tr[sel] // NS
    m1 = pd.Series(mid, index=seg).dropna()
    m1 = m1.groupby(level=0).last()
    rej = pd.Series(m1.to_numpy(), index=m1.index.to_numpy()).reindex(
        np.arange(m1.index.min(), m1.index.max() + 1)).ffill()
    s0 = rej.index[0]
    vals = rej.to_numpy()
    ret = {}
    ts_big = big["win"].to_numpy() * TU_WINDOW_MS * NS_MS // NS
    for h in TU_HORIZONTES_MIN:
        a = np.clip(ts_big - s0, 0, len(vals) - 1)
        b = ts_big + 60 * h - s0
        dentro = b < len(vals)
        r_ = np.where(dentro, (vals[np.clip(b, 0, len(vals) - 1)] - vals[a]) / vals[a] * 1e4, 0.0)
        ret[h] = r_
    out.update(disponible=True, grupos=G, big=big, p95=p95, p99=p99, p999=p999, n_clusters=k,
               clusters_mixtos=mixtos, ret=ret, sel=sel, grupo_de=df["grupo"].to_numpy(),
               pos=df["pos"].to_numpy(), registros=int(sel.sum()))
    if eid_crudo is not None:
        e = eid_crudo[sel][ok]
        val = e >= 0
        par = pd.DataFrame({"e": e[val], "g": df["grupo"].to_numpy()[val]}).drop_duplicates()
        grupos_por_ev = par.groupby("e")["g"].nunique()
        ev_por_grupo = par.groupby("g")["e"].nunique()
        out["eventos_partidos"] = float((grupos_por_ev > 1).mean()) if len(grupos_por_ev) else np.nan
        out["grupos_mezclados"] = float((ev_por_grupo > 1).mean()) if len(ev_por_grupo) else np.nan
        bigset = set(big.index.to_numpy())
        eb = par[par["g"].isin(bigset)]
        partes_big = eb.merge(par, on="e", suffixes=("", "_otro"))
        partes_big = partes_big[partes_big["g"] != partes_big["g_otro"]]
        out["big_pedazo"] = float(partes_big["g"].nunique() / max(1, len(bigset)))
        out["big_mezclados"] = float((ev_por_grupo.reindex(list(bigset)).fillna(0) > 1).mean()) if bigset else np.nan
    return out


def eventos_de_crudo(crudo: dict, tick_ns_: int) -> np.ndarray:
    """El número de evento (fila de E) de cada operación cruda; −1 si la higiene la quitó."""
    s, q, px = crudo["s"].astype(np.int64), crudo["q"], crudo["precio"]
    val = (s != 0) & (q > 0) & ((px % tick_ns_) == 0)
    t, inst = crudo["t"][val], crudo["inst"][val]
    sv = s[val]
    start = np.r_[True, (t[1:] != t[:-1]) | (sv[1:] != sv[:-1]) | (inst[1:] != inst[:-1])] if len(t) else np.zeros(0, bool)
    eid = np.full(len(s), -1, np.int64)
    eid[val] = np.cumsum(start) - 1
    return eid


class MotorIncremental:
    """
    El mismo cálculo, un registro a la vez: lo que corre con Databento Live, donde no hay bloques
    sino registros que llegan. Misma higiene en el mismo orden, mismo tiempo monótono, mismos
    eventos y mismas huellas. Llama a `al_cerrar_huella(h)` en cuanto una huella ya no puede
    crecer: llega un evento suyo que no cabe o el reloj pasa su hueco/tope. La prueba de paridad
    exige que dé EXACTAMENTE las huellas del motor vectorizado.
    """

    def __init__(self, cfg: Config, tick_ns_: int, al_cerrar_huella=None, guardar: bool = True):
        self.cfg = cfg
        self.tick = int(tick_ns_)
        self.gap = int(round(cfg.rafaga_ms * NS_MS))
        self.cap = int(round(cfg.rafaga_max_ms * NS_MS))
        self.cb = al_cerrar_huella
        self.guardar = guardar
        self.t_max = -1
        self.ev: dict | None = None
        self.abiertas: dict[int, dict | None] = {1: None, -1: None}
        self.huellas: list[dict] = []
        self.n_eventos = 0
        self.registros = 0
        self.conteo = {r: 0 for r in REGLAS}
        self._s_ini, self._s_fin, self._s_dia = 0, -1, -1
        self.r0, self.r1 = segundo_de_hora(cfg.rth_ct[0]), segundo_de_hora(cfg.rth_ct[1])

    def _sesion(self, t: int) -> tuple[int, int]:
        if not (self._s_ini <= t < self._s_fin):
            d = int(reloj_sesion([t], self.cfg.tz_mercado)[0][0])
            self._s_dia, self._s_ini, self._s_fin = d, apertura_utc(d, self.cfg.tz_mercado), \
                apertura_utc(d + 1, self.cfg.tz_mercado)
        return self._s_dia, (t - self._s_ini) // NS

    def registro(self, t: int, tr: int, inst: int, accion: str, lado: str, precio: int, tam: int, flags: int,
                 seq: int, bpx: int, apx: int, bsz: int, asz: int, tiene_libro: bool = True) -> None:
        self.registros += 1
        t = max(int(t), self.t_max)
        self.t_max = t
        tk = self.tick
        ok = True
        if accion != "T":
            self.conteo[REGLAS[0]] += 1
            ok = False
        elif tam <= 0 or precio <= 0 or precio == UNDEF_PRICE:
            self.conteo[REGLAS[1]] += 1
            ok = False
        elif precio % tk:
            self.conteo[REGLAS[2]] += 1
            ok = False
        elif lado not in ("B", "A"):
            self.conteo[REGLAS[3]] += 1
            ok = False
        if ok:
            s = 1 if lado == "B" else -1
            libro = (tiene_libro and bpx != UNDEF_PRICE and apx != UNDEF_PRICE and bpx > 0 and apx > 0
                     and bsz > 0 and asz > 0 and bpx < apx and apx - bpx <= self.cfg.spread_max_ticks * tk
                     and not (flags & F_MAYBE_BAD_BOOK) and bpx % tk == 0 and apx % tk == 0)
            px = int(precio) // tk
            e = self.ev
            if e is not None and e["t"] == t and e["lado"] == s and e["inst"] == inst:
                e["vol"] += tam
                e["qpx"] += tam * px
                e["n_prints"] += 1
                if px != e["px_fin"]:
                    e["n_niveles"] += 1
                e["px_fin"] = px
                e["px_min"] = min(e["px_min"], px)
                e["px_max"] = max(e["px_max"], px)
                if px == e["px_ini"]:
                    e["vol_n1"] += tam
            else:
                self._cerrar_evento()
                self.ev = {"t": t, "tr": int(tr), "inst": int(inst), "lado": s, "vol": int(tam), "qpx": int(tam) * px,
                           "n_prints": 1, "n_niveles": 1, "px_ini": px, "px_fin": px, "px_min": px, "px_max": px,
                           "vol_n1": int(tam), "bid0": int(bpx) // tk if libro else -1,
                           "ask0": int(apx) // tk if libro else -1, "bsz0": int(bsz) if libro else 0,
                           "asz0": int(asz) if libro else 0, "libro0": bool(libro), "seq0": int(seq)}
        # reloj: cierra las huellas que ya no pueden crecer
        for lado_h in (1, -1):
            h = self.abiertas[lado_h]
            if h is None or (self.ev is not None and self.ev["lado"] == lado_h):
                continue
            if t - h["t_fin"] > self.gap or t - h["t_ini"] > self.cap or t >= h["fin_ses"]:
                self._cerrar_huella(lado_h)

    def registro_dbn(self, r) -> None:
        """Un registro de databento (MBP1Msg de tbbo/mbp-1 o TradeMsg de trades)."""
        lv = getattr(r, "levels", None)
        if lv:
            b = lv[0]
            self.registro(r.ts_event, r.ts_recv, r.instrument_id, str(r.action), str(r.side), r.price, r.size,
                          int(r.flags), r.sequence, b.bid_px, b.ask_px, b.bid_sz, b.ask_sz, True)
        else:
            self.registro(r.ts_event, r.ts_recv, r.instrument_id, str(r.action), str(r.side), r.price, r.size,
                          int(r.flags), getattr(r, "sequence", 0), UNDEF_PRICE, UNDEF_PRICE, 0, 0, False)

    def _cerrar_evento(self) -> None:
        e = self.ev
        if e is None:
            return
        self.ev = None
        self.n_eventos += 1
        dia, seg = self._sesion(e["t"])
        mejor = e["ask0"] if e["lado"] > 0 else e["bid0"]
        visible = e["asz0"] if e["lado"] > 0 else e["bsz0"]
        okd = e["libro0"] and e["px_ini"] == mejor
        disp = float(visible) if okd else np.nan
        oculta = max(e["vol_n1"] - visible, 0) if okd else 0
        mid0 = (e["bid0"] + e["ask0"]) / 2.0 if e["libro0"] else np.nan
        s = e["lado"]
        h = self.abiertas[s]
        if (h is not None and h["sesion"] == dia and h["inst"] == e["inst"] and e["t"] - h["t_fin"] <= self.gap
                and e["t"] - h["t_ini"] <= self.cap):
            h["t_fin"] = e["t"]
            h["vol"] += e["vol"]
            h["qpx"] += e["qpx"]
            h["n_eventos"] += 1
            h["n_prints"] += e["n_prints"]
            h["niv_max"] = max(h["niv_max"], e["n_niveles"])
            h["px_min"] = min(h["px_min"], e["px_min"])
            h["px_max"] = max(h["px_max"], e["px_max"])
            h["px_fin"] = e["px_fin"]
            h["oculta"] += oculta
            return
        if h is not None:
            self._cerrar_huella(s)
        self.abiertas[s] = {"t_ini": e["t"], "t_fin": e["t"], "inst": e["inst"], "lado": s, "sesion": dia,
                            "seg": int(seg), "rth": bool(self.r0 <= seg < self.r1), "vol": e["vol"], "qpx": e["qpx"],
                            "n_eventos": 1, "n_prints": e["n_prints"], "niv_max": e["n_niveles"],
                            "px_min": e["px_min"], "px_max": e["px_max"], "px_ini": e["px_ini"],
                            "px_fin": e["px_fin"], "bid0": e["bid0"], "ask0": e["ask0"], "bsz0": e["bsz0"],
                            "asz0": e["asz0"], "libro0": e["libro0"], "mid0": mid0, "disp0": disp,
                            "oculta": oculta, "seq0": e["seq0"], "tr0": e["tr"], "fin_ses": self._s_fin}

    def _cerrar_huella(self, s: int) -> None:
        h = self.abiertas[s]
        if h is None:
            return
        self.abiertas[s] = None
        h["vwap"] = h["qpx"] / h["vol"]
        h["span"] = h["px_max"] - h["px_min"] + 1
        h["dur_ms"] = (h["t_fin"] - h["t_ini"]) / NS_MS
        if self.guardar:
            self.huellas.append(h)
        if self.cb is not None:
            self.cb(h)

    def cerrar(self) -> None:
        self._cerrar_evento()
        for s in sorted((1, -1), key=lambda x: (self.abiertas[x] or {"t_ini": 10 ** 20})["t_ini"]):
            self._cerrar_huella(s)

    def tabla(self) -> pd.DataFrame:
        if not self.huellas:
            return pd.DataFrame()
        H = pd.DataFrame(self.huellas)
        return H.sort_values(["t_ini", "lado"], ascending=[True, False], kind="stable").reset_index(drop=True)


COLS_PARIDAD = ("t_ini", "t_fin", "inst", "lado", "sesion", "vol", "qpx", "n_eventos", "n_prints", "niv_max",
                "px_min", "px_max", "px_ini", "px_fin", "bid0", "ask0", "bsz0", "asz0", "oculta", "disp0", "mid0")


def paridad(tienda, cfg: Config, maximo: int = 300_000) -> dict:
    """Motor vectorizado (por bloques) contra el incremental (registro por registro), mismos registros."""
    partes, n = [], 0
    for arr in bloques(tienda, replace(cfg, bloque=min(cfg.bloque, maximo))):
        partes.append(arr[: maximo - n])
        n += len(partes[-1])
        if n >= maximo:
            break
    arr = np.concatenate(partes) if partes else np.zeros(0, DTYPE_TBBO)
    if not len(arr):
        return {"registros": 0, "iguales": True, "max_dif": 0.0, "huellas": 0}
    tk = tick_ns(cfg.symbol)
    mv = MotorEventos(cfg, tk, guardar_crudo=False)
    paso = max(1, len(arr) // 3)
    for i in range(0, len(arr), paso):
        mv.procesar(arr[i:i + paso])
    mv.cerrar()
    E = preparar_eventos(mv.eventos(), cfg)
    Hv, _ = agrupar_huellas(E, cfg)
    mi = MotorIncremental(cfg, tk)
    r = normalizar(arr)
    tl = r["tiene_libro"]
    for k in range(len(arr)):
        mi.registro(int(r["t"][k]), int(r["tr"][k]), int(r["inst"][k]), r["accion"][k].decode(), r["lado"][k].decode(),
                    int(r["precio"][k]), int(r["tam"][k]), int(r["flags"][k]), int(r["seq"][k]), int(r["bpx"][k]),
                    int(r["apx"][k]), int(r["bsz"][k]), int(r["asz"][k]), tl)
    mi.cerrar()
    Hi = mi.tabla()
    if len(Hv) != len(Hi):
        return {"registros": len(arr), "iguales": False, "max_dif": np.inf, "huellas": len(Hv),
                "huellas_inc": len(Hi), "conteo_igual": mv.conteo == mi.conteo}
    dif = 0.0
    for c in COLS_PARIDAD:
        a = Hv[c].to_numpy(dtype=float)
        b = Hi[c].to_numpy(dtype=float)
        ambos = np.isfinite(a) & np.isfinite(b)
        dif = max(dif, float(np.max(np.abs(a[ambos] - b[ambos]), initial=0.0)),
                  float(np.sum(np.isfinite(a) != np.isfinite(b))))
    return {"registros": len(arr), "iguales": dif == 0.0 and mv.conteo == mi.conteo, "max_dif": dif,
            "huellas": len(Hv), "eventos": len(E), "conteo_igual": mv.conteo == mi.conteo}


# =============================================================================
# 7. SIMULADOR — un mercado con órdenes institucionales e icebergs CONOCIDOS
# =============================================================================
ESTILOS = {0: "ruido", 1: "BLOQUE", 2: "BARRIDO", 3: "FRAGMENTADA", 4: "CONTRA ICEBERG"}


def perfil_actividad(minuto: np.ndarray) -> np.ndarray:
    """Actividad relativa por minuto de sesión (0 = 17:00 CT): Asia quieta, Europa, apertura de NY."""
    m = np.asarray(minuto)
    p = np.where(m < 540, 0.45, 1.0)                           # 17:00-02:00 CT: Asia
    p = np.where((m >= 930) & (m < 1335), 3.0, p)              # 08:30-15:15 CT: horario regular
    p = np.where((m >= 930) & (m < 945), 6.0, p)               # la apertura
    return np.where(m >= 1335, 0.6, p)


def simular(cfg: Config, sesiones: int | None = None, semilla: int | None = None, metaordenes: bool = True,
            icebergs: bool = True, defectos: bool = True) -> tuple[np.ndarray, dict]:
    """
    Registros TBBO (cada operación con el mejor bid/ask justo antes), sesión por sesión, de un libro
    con colas en el mejor nivel y profundidad aleatoria detrás:
      · RUIDO: altas, cancelaciones y órdenes de mercado de tamaño con cola de Pareto (α = 1.6):
        el ruido también produce operaciones grandes de vez en cuando, como en el mercado real;
      · un precio eficiente v (paseo aleatorio) al que el libro regresa: el impacto del ruido es
        TRANSITORIO;
      · METAÓRDENES institucionales CONOCIDAS (`sim_metaordenes` por sesión, 5-30 min, 100-900
        contratos), cada una con un estilo: BLOQUE (se lleva lo visible del mejor nivel), BARRIDO
        (órdenes de 15-60 que cruzan niveles) o FRAGMENTADA (cada hija partida en 3-8 pedazos a
        2-40 ms). La mitad son INFORMADAS: mueven v con la ley de la raíz cuadrada sobre lo ya
        ejecutado, 0.6·(√(X + q) − √X) ticks por hija (impacto permanente y cóncavo, ~18 ticks
        una de 900); la otra mitad no. Detrás del mejor nivel el libro se hace más profundo, así
        que el impacto mecánico también es cóncavo;
      · ICEBERGS pasivos CONOCIDOS (`sim_icebergs` por sesión): una orden oculta de 150-600
        contratos en el mejor bid o ask que se repone de a 4-9; una ráfaga agresiva del otro lado
        pega contra ella y el nivel aguanta;
      · subasta de apertura sin agresor (side N), un roll con salto de nivel y —si `defectos`—
        registros que la higiene debe quitar (tamaño 0, fuera del tick, altas de mbp-1, side N
        sueltos) y libros dañados (F_MAYBE_BAD_BOOK, cruzados) en operaciones válidas.
    Cada operación sale partida en 1-3 registros por nivel (órdenes en reposo distintas).
    """
    rng = np.random.default_rng(cfg.sim_semilla if semilla is None else semilla)
    S = int(sesiones or cfg.sim_sesiones)
    tk = tick_ns(cfg.symbol)
    p_ref = CATALOGO.get(raiz(cfg.symbol), ("", 1.0, 42000.0, 5.0))[2]
    fin_dia = int(reloj_sesion([a_utc(cfg.end, cfg.tz_entrada).value], cfg.tz_mercado)[0][0])
    fechas = pd.bdate_range(end=fecha_de_dia(fin_dia), periods=S)
    perfil = perfil_actividad(np.arange(MINUTOS_SESION))
    tasa_min = cfg.sim_eventos / perfil.sum()
    col = {k: [] for k in ("tr", "t", "inst", "accion", "lado", "precio", "tam", "flags", "seq",
                           "bpx", "apx", "bsz", "asz", "meta", "inf", "estilo", "ice", "limpio", "danado")}
    metas, ices = [], []
    estado = {"seq": 0, "t_ult": 0, "tr_ult": 0}
    B = int(round(p_ref / tick(cfg.symbol)))
    v = B + 0.5
    inst = 9001
    roll_en = S // 2
    kappa_inf, sig_v, p_rc = 0.6, 0.12, 0.15
    ejecutado: dict[int, int] = {}

    def emitir(t_ns, accion, lado, precio_t, tam, bbo, meta=-1, inf=False, estilo=0, ice=-1, limpio=True,
               danado=False, flags=0, precio_ns=None):
        estado["tr_ult"] = max(estado["tr_ult"] + 1, t_ns + 40_000)
        col["tr"].append(estado["tr_ult"])
        col["t"].append(t_ns)
        col["inst"].append(inst)
        col["accion"].append(accion)
        col["lado"].append(lado)
        col["precio"].append(precio_t * tk if precio_ns is None else precio_ns)
        col["tam"].append(tam)
        col["flags"].append(flags)
        col["seq"].append(estado["seq"])
        b_, a_, qb_, qa_ = bbo
        col["bpx"].append(b_ * tk if b_ is not None else UNDEF_PRICE)
        col["apx"].append(a_ * tk if a_ is not None else UNDEF_PRICE)
        col["bsz"].append(qb_)
        col["asz"].append(qa_)
        for k_, x in (("meta", meta), ("inf", inf), ("estilo", estilo), ("ice", ice), ("limpio", limpio),
                      ("danado", danado)):
            col[k_].append(x)

    for s_i, fecha in enumerate(fechas):
        dia = int(fecha.value // DIA_NS)
        t_ses = apertura_utc(dia, cfg.tz_mercado)
        if s_i == roll_en:                                     # roll: contrato nuevo, nivel +80 ticks
            inst += 1
            B += 80
            v += 80
        A = B + 1
        rth_min = (perfil >= 2.9)
        qb, qa = 1 + int(rng.poisson(4)), 1 + int(rng.poisson(4))
        # --- línea de tiempo: eventos de libro/ruido + hijas institucionales ---
        n_min = rng.poisson(tasa_min * perfil)
        t_ruido = np.concatenate([m * 60.0 + np.sort(rng.uniform(0, 60, k)) for m, k in enumerate(n_min)])
        hijas = []                                             # (seg, lado, tam o None, meta, inf, estilo)
        if metaordenes:
            for _ in range(cfg.sim_metaordenes):
                en_rth = rng.random() < 0.6
                m0 = int(rng.integers(935, 1290)) if en_rth else int(rng.integers(30, 900))
                dur = float(rng.uniform(5, 30)) * 60
                lado = int(rng.choice((-1, 1)))
                inf = bool(rng.random() < 0.5)
                estilo = int(rng.integers(1, 4))
                Q = int(rng.uniform(200, 900) if en_rth else rng.uniform(100, 400))
                mid_ = len(metas)
                metas.append({"id": mid_, "sesion": dia, "t_ini": t_ses + int(m0 * 60 * NS),
                              "t_fin": t_ses + int((m0 * 60 + dur) * NS), "lado": lado, "informada": inf,
                              "estilo": estilo, "Q": Q})
                hecho = 0
                tiempos = []
                while hecho < Q:
                    if estilo == 1:
                        c = 10                                 # aprox.: se decide al ejecutar (lo visible)
                    elif estilo == 2:
                        c = int(rng.integers(15, 61))
                    else:
                        c = int(rng.integers(20, 61))
                    tiempos.append(c)
                    hecho += c
                ts_ = np.sort(rng.uniform(m0 * 60, m0 * 60 + dur, len(tiempos)))
                for t_c, c in zip(ts_, tiempos):
                    if estilo == 1:
                        hijas.append((t_c, lado, None, mid_, inf, 1))
                    elif estilo == 2:
                        hijas.append((t_c, lado, c, mid_, inf, 2))
                    else:
                        k = int(rng.integers(3, 9))
                        partes = np.diff(np.r_[0, np.sort(rng.choice(np.arange(1, c), k - 1, replace=False)), c])
                        dt = np.cumsum(np.r_[0, rng.uniform(0.002, 0.040, k - 1)])
                        for p_, d_ in zip(partes, dt):
                            hijas.append((t_c + d_, lado, int(p_), mid_, inf, 3))
        ice_plan = []
        if icebergs:
            for _ in range(cfg.sim_icebergs):
                m0 = int(rng.integers(940, 1300)) if rng.random() < 0.7 else int(rng.integers(60, 900))
                ice_plan.append((m0 * 60.0, int(rng.choice((-1, 1))), int(rng.uniform(150, 600)),
                                 int(rng.integers(4, 10))))
        t_hija = np.array([h[0] for h in hijas]) if hijas else np.zeros(0)
        t_ice = np.array([p[0] for p in ice_plan]) if ice_plan else np.zeros(0)
        tiempos = np.r_[t_ruido, t_hija, t_ice]
        tipo_ev = np.r_[np.zeros(len(t_ruido), int), np.ones(len(t_hija), int), np.full(len(t_ice), 2)]
        ref_ev = np.r_[np.arange(len(t_ruido)), np.arange(len(t_hija)), np.arange(len(t_ice))]
        o = np.argsort(tiempos, kind="stable")
        tiempos, tipo_ev, ref_ev = tiempos[o], tipo_ev[o], ref_ev[o]
        n = len(tiempos)
        u = rng.random(n)
        u2 = rng.random(n)
        tam_lib = 1 + rng.geometric(0.45, n) - 1
        tam_mkt = np.minimum(np.floor(rng.random(n) ** (-1 / 1.6)).astype(int), 60)
        ruido_v = rng.normal(0, sig_v, n)
        ice = None
        hijas_extra = []                                       # ráfagas contra iceberg (se agregan al vuelo)
        # --- subasta de apertura: operaciones sin agresor ---
        t0 = t_ses + int(0.2 * NS)
        estado["t_ult"] = max(estado["t_ult"], t0)
        estado["seq"] += 1
        for k in range(int(rng.integers(8, 16))):
            emitir(t0, "T", "N", B if k % 2 else A, int(1 + rng.integers(0, 5)), (None, None, 0, 0),
                   limpio=False, flags=F_LAST if k == 0 else 0)

        def ejecutar(t_ns, lado, Q, meta=-1, inf=False, estilo=0):
            nonlocal B, A, qb, qa, v, ice
            if Q is None:
                Q = max(3, qa if lado > 0 else qb)
            pre = (B, A, qb, qa)
            danado = False
            bbo = pre
            if defectos and rng.random() < 0.004:
                bbo, danado = ((B, A, qb, qa), True) if rng.random() < 0.5 else ((A, B, qb, qa), True)
            dm = 10.0 if rth_min[min(int((t_ns - t_ses) // (60 * NS)), MINUTOS_SESION - 1)] else 4.0
            precio = A if lado > 0 else B
            prof = qa if lado > 0 else qb
            resto = Q
            prints = []
            niveles = 0
            while resto > 0:
                toma = min(resto, prof)
                if toma > 0:
                    prints.append([precio, toma, False])
                resto -= toma
                prof -= toma
                if prof == 0:
                    if ice is not None and ice["lado"] == -lado and ice["precio"] == precio and ice["reserva"] > 0:
                        prof = min(ice["pico"], ice["reserva"])
                        ice["reserva"] -= prof
                        ice["oculto"] += prof
                        if resto > 0:
                            prints.append([precio, 0, True])
                        continue
                    if resto > 0:
                        precio += lado
                        niveles += 1
                        prof = 1 + int(rng.poisson(dm * (1 + 0.6 * niveles)))
            prints = [p for p in prints if p[1] > 0 or p[2]]
            # junta pedazos del mismo precio (el iceberg repone en el mismo nivel)
            junt = []
            for p in prints:
                if junt and junt[-1][0] == p[0]:
                    junt[-1][1] += p[1]
                    junt[-1][2] |= p[2]
                else:
                    junt.append(list(p))
            if prof == 0:
                precio += lado
                prof = 1 + int(rng.poisson(dm))
            if lado > 0:
                movio = precio != A
                A, qa = precio, prof
                if movio and not (ice is not None and ice["lado"] > 0):
                    B, qb = A - 1, 1 + int(rng.poisson(dm))
            else:
                movio = precio != B
                B, qb = precio, prof
                if movio and not (ice is not None and ice["lado"] < 0):
                    A, qa = B + 1, 1 + int(rng.poisson(dm))
            if ice is not None and ((ice["lado"] > 0 and B != ice["precio"]) or (ice["lado"] < 0 and A != ice["precio"])
                                    or ice["reserva"] <= 0 and ((ice["lado"] > 0 and qb == 0) or (ice["lado"] < 0 and qa == 0))):
                ices[ice["id"]]["t_fin"] = t_ns
                ice = None
            # registros: 1-3 por nivel, todos con la misma hora de casación
            t_ns = max(t_ns, estado["t_ult"] + 1000)
            estado["t_ult"] = t_ns
            estado["seq"] += 1
            regs = []
            for precio_p, toma, de_ice in junt:
                k = 1 if toma < 2 or rng.random() < 0.6 else int(rng.integers(2, min(3, toma) + 1))
                cortes = np.sort(rng.choice(np.arange(1, toma), k - 1, replace=False)) if k > 1 else []
                for q_ in np.diff(np.r_[0, cortes, toma]):
                    regs.append((precio_p, int(q_), de_ice))
            for j, (precio_p, q_, de_ice) in enumerate(regs):
                emitir(t_ns, "T", "B" if lado > 0 else "A", precio_p, q_, bbo, meta, inf, estilo,
                       ice=ice_id_actual if de_ice else -1, danado=danado,
                       flags=(F_LAST if j == len(regs) - 1 else 0) | (F_MAYBE_BAD_BOOK if danado and bbo == pre else 0))
            if inf:                                          # raíz cuadrada sobre lo ya ejecutado
                X = ejecutado.get(meta, 0)
                v += lado * kappa_inf * (math.sqrt(X + Q) - math.sqrt(X))
                ejecutado[meta] = X + Q
            return t_ns

        ice_id_actual = -1
        for i in range(n):
            t_ns = t_ses + int(tiempos[i] * NS)
            tp = tipo_ev[i]
            dm = 10.0 if rth_min[min(int(tiempos[i] // 60), MINUTOS_SESION - 1)] else 4.0
            if tp == 1:
                _, lado, c, mid_, inf, est = hijas[ref_ev[i]]
                ejecutar(t_ns, lado, c, mid_, inf, est)
            elif tp == 2:
                if ice is None:
                    _, lado_i, R, pico = ice_plan[ref_ev[i]]
                    ice_id_actual = len(ices)
                    ice = {"id": ice_id_actual, "lado": lado_i, "precio": B if lado_i > 0 else A, "reserva": R,
                           "pico": pico, "oculto": 0}
                    if lado_i > 0:
                        qb = pico
                    else:
                        qa = pico
                    ices.append({"id": ice_id_actual, "sesion": dia, "t_ini": t_ns, "t_fin": None, "lado": lado_i,
                                 "precio": ice["precio"], "reserva": R})
                    # ráfaga agresiva del otro lado contra el iceberg
                    tot, objetivo = 0, rng.uniform(0.6, 1.1) * R
                    ini_r, dur = rng.uniform(1, 5), rng.uniform(20, 120)
                    while tot < objetivo:
                        c = int(rng.integers(10, 36))
                        hijas_extra.append((tiempos[i] + ini_r + rng.uniform(0, dur), -lado_i, c))
                        tot += c
                    hijas_extra.sort()
            else:
                k = ref_ev[i]
                x = u[i]
                if x < 0.30:                                   # orden de mercado de ruido
                    ejecutar(t_ns, 1 if u2[i] < 0.5 else -1, int(tam_mkt[i]))
                elif x < 0.68:                                 # alta en el mejor nivel (o mejora el spread)
                    if u2[i] < 0.5:
                        if A - B > 1 and rng.random() < 0.6 and not (ice is not None and ice["lado"] > 0):
                            B, qb = B + 1, int(tam_lib[k])
                        else:
                            qb += int(tam_lib[k])
                    else:
                        if A - B > 1 and rng.random() < 0.6 and not (ice is not None and ice["lado"] < 0):
                            A, qa = A - 1, int(tam_lib[k])
                        else:
                            qa += int(tam_lib[k])
                else:                                          # cancelación en el mejor nivel
                    if u2[i] < 0.5 and not (ice is not None and ice["lado"] > 0):
                        qb -= min(qb, int(tam_lib[k]))
                        if qb == 0:
                            B, qb = B - 1, 1 + int(rng.poisson(dm))
                    elif u2[i] >= 0.5 and not (ice is not None and ice["lado"] < 0):
                        qa -= min(qa, int(tam_lib[k]))
                        if qa == 0:
                            A, qa = A + 1, 1 + int(rng.poisson(dm))
            # hijas contra el iceberg que ya tocan
            while hijas_extra and hijas_extra[0][0] <= tiempos[i]:
                t_c, lado_c, c = hijas_extra.pop(0)
                ejecutar(t_ses + int(t_c * NS), lado_c, c, -1, False, 4)
            if ice is not None and t_ns - ices[ice["id"]]["t_ini"] > 600 * NS:     # el resto se cancela
                ices[ice["id"]]["t_fin"] = t_ns
                ice = None
            # precio eficiente y regreso del libro hacia él
            v += ruido_v[i]
            if ice is None and rng.random() < p_rc:          # el iceberg fija el precio mientras vive
                mid = (A + B) / 2.0
                if mid - v > 0.75 and not (ice is not None and ice["lado"] > 0):
                    B, A = B - 1, A - 1
                    qb, qa = 1 + int(rng.poisson(dm)), 1 + int(rng.poisson(dm))
                elif mid - v < -0.75 and not (ice is not None and ice["lado"] < 0):
                    B, A = B + 1, A + 1
                    qb, qa = 1 + int(rng.poisson(dm)), 1 + int(rng.poisson(dm))
                if ice is not None and ((ice["lado"] > 0 and B != ice["precio"]) or (ice["lado"] < 0 and A != ice["precio"])):
                    ices[ice["id"]]["t_fin"] = t_ns
                    ice = None
            # defectos sueltos entre dos eventos
            if defectos and rng.random() < 25.0 / max(n, 1):
                tt = max(t_ns, estado["t_ult"]) + 7
                estado["t_ult"] = tt
                kd = int(rng.integers(4))
                estado["seq"] += 1
                if kd == 0:
                    emitir(tt, "T", "B", A, 0, (B, A, qb, qa), limpio=False, flags=F_LAST)
                elif kd == 1:
                    emitir(tt, "T", "A", B, 2, (B, A, qb, qa), limpio=False, flags=F_LAST, precio_ns=B * tk + 7)
                elif kd == 2:
                    emitir(tt, "A", "B", B, 3, (B, A, qb + 3, qa), limpio=False, flags=F_LAST)
                else:
                    emitir(tt, "T", "N", A, 1, (B, A, qb, qa), limpio=False, flags=F_LAST)
        while hijas_extra:
            t_c, lado_c, c = hijas_extra.pop(0)
            ejecutar(t_ses + int(min(t_c, MINUTOS_SESION * 60 - 1) * NS), lado_c, c, -1, False, 4)
        if ice is not None:
            ices[ice["id"]]["t_fin"] = estado["t_ult"]
            ice = None

    n = len(col["t"])
    arr = np.zeros(n, dtype=DTYPE_TBBO)
    arr["ts_recv"] = np.asarray(col["tr"], np.uint64)
    arr["ts_event"] = np.asarray(col["t"], np.uint64)
    arr["instrument_id"] = np.asarray(col["inst"], np.uint32)
    arr["action"] = np.asarray(col["accion"], "S1")
    arr["side"] = np.asarray(col["lado"], "S1")
    arr["price"] = np.asarray(col["precio"], np.int64)
    arr["size"] = np.asarray(col["tam"], np.uint32)
    arr["flags"] = np.asarray(col["flags"], np.uint8)
    arr["sequence"] = np.asarray(col["seq"], np.uint32)
    arr["bid_px_00"] = np.asarray(col["bpx"], np.int64)
    arr["ask_px_00"] = np.asarray(col["apx"], np.int64)
    arr["bid_sz_00"] = np.asarray(col["bsz"], np.uint32)
    arr["ask_sz_00"] = np.asarray(col["asz"], np.uint32)
    verdad = {"meta": np.asarray(col["meta"], np.int64), "informada": np.asarray(col["inf"], bool),
              "estilo": np.asarray(col["estilo"], np.int64), "iceberg": np.asarray(col["ice"], np.int64),
              "limpio": np.asarray(col["limpio"], bool), "danado": np.asarray(col["danado"], bool),
              "metaordenes": metas, "icebergs": ices, "roll_sesion": roll_en,
              "sesiones": [int(f.value // DIA_NS) for f in fechas]}
    return arr, verdad


def config_simulacion(cfg: Config, verdad: dict) -> Config:
    """La ventana analizada son las sesiones simuladas después del calentamiento."""
    ses = verdad["sesiones"]
    k = min(max(cfg.dias_calentamiento, 1), len(ses) - 1)
    t0 = pd.Timestamp(apertura_utc(ses[k], cfg.tz_mercado), tz="UTC")
    t1 = pd.Timestamp(apertura_utc(ses[-1] + 1, cfg.tz_mercado), tz="UTC")
    return replace(cfg, start=t0.strftime("%Y-%m-%dT%H:%M:%S"), end=t1.strftime("%Y-%m-%dT%H:%M:%S"),
                   tz_entrada="UTC")


def a_dbn(arr: np.ndarray, cfg: Config) -> bytes:
    """El arreglo simulado → un archivo DBN TBBO de verdad, para probar la ruta de Databento."""
    import databento_dbn as dd
    acc = {b"A": dd.Action.ADD, b"C": dd.Action.CANCEL, b"M": dd.Action.MODIFY, b"T": dd.Action.TRADE,
           b"F": dd.Action.FILL, b"R": dd.Action.CLEAR}
    lado = {b"B": dd.Side.BID, b"A": dd.Side.ASK, b"N": dd.Side.NONE}
    meta = dd.Metadata(dataset=cfg.dataset, start=int(arr["ts_recv"][0]), stype_in=dd.SType.CONTINUOUS,
                       stype_out=dd.SType.INSTRUMENT_ID, schema=dd.Schema.TBBO, symbols=[cfg.symbol],
                       partial=[], not_found=[], mappings=[], end=int(arr["ts_recv"][-1]) + NS)
    partes = [bytes(meta.encode())]
    for r in arr:
        lv = dd.BidAskPair(bid_px=int(r["bid_px_00"]), ask_px=int(r["ask_px_00"]), bid_sz=int(r["bid_sz_00"]),
                           ask_sz=int(r["ask_sz_00"]), bid_ct=1, ask_ct=1)
        partes.append(bytes(dd.MBP1Msg(publisher_id=1, instrument_id=int(r["instrument_id"]),
                                       ts_event=int(r["ts_event"]), price=int(r["price"]), size=int(r["size"]),
                                       action=acc[bytes(r["action"])], side=lado[bytes(r["side"])], depth=0,
                                       ts_recv=int(r["ts_recv"]), flags=int(r["flags"]),
                                       sequence=int(r["sequence"]), levels=lv)))
    return b"".join(partes)


# =============================================================================
# 8. EL CÁLCULO COMPLETO, LA AUDITORÍA Y EL CHEQUEO DE CORDURA
# =============================================================================
def mco_agrupado(y: np.ndarray, X: np.ndarray, g: np.ndarray) -> dict:
    """MCO con errores estándar agrupados por sesión (sándwich de Liang-Zeger, corrección G/(G−1))."""
    ok = np.isfinite(y) & np.all(np.isfinite(X), axis=1)
    y, X, g = y[ok], X[ok], np.asarray(g)[ok]
    n, k = X.shape
    out = {"n": n, "coef": np.full(k, np.nan), "se": np.full(k, np.nan), "t": np.full(k, np.nan),
           "p": np.full(k, np.nan), "sesiones": 0}
    if n < k + 10:
        return out
    XtX_inv = np.linalg.pinv(X.T @ X)
    b = XtX_inv @ X.T @ y
    e = y - X @ b
    _, inv = np.unique(g, return_inverse=True)
    G = int(inv.max()) + 1
    out.update(coef=b, sesiones=G)
    if G < 2:
        return out
    S = np.zeros((G, k))
    np.add.at(S, inv, X * e[:, None])
    V = XtX_inv @ (S.T @ S) @ XtX_inv * G / (G - 1)
    se = np.sqrt(np.maximum(np.diag(V), 0))
    t = np.where(se > 0, b / se, np.nan)
    out.update(se=se, t=t, p=np.array([p_t(x, G - 1) for x in t]))
    return out


@dataclass
class Auditoria:
    impacto: pd.DataFrame
    curva: dict
    perm: dict
    rastreo: pd.DataFrame
    control: dict
    costos: dict
    cola: tuple
    lado: dict
    sensibilidad: pd.DataFrame
    cordura: list
    paridad: dict | None = None


@dataclass
class Resultado:
    cfg: Config
    E: pd.DataFrame
    H: pd.DataFrame
    U: pd.DataFrame
    G: pd.DataFrame
    C: pd.DataFrame
    motor: MotorEventos
    aud: Auditoria
    tu: dict
    info: dict
    base: pd.DataFrame = field(default_factory=pd.DataFrame)
    verdad: dict | None = None
    medicion: dict | None = None


def grupos_auditoria(H: pd.DataFrame, en_cluster: np.ndarray) -> dict:
    win = H["ventana"].to_numpy()
    cl = H["clase"].to_numpy()
    big = win & (cl >= 1)
    tipo = H["tipo"].to_numpy()
    pos = H["pos_rango"].to_numpy()
    rth = H["rth"].to_numpy().astype(bool)
    g = {"normales": win & (cl == 0), "grandes (todas)": big}
    for c in (1, 2, 3):
        g[CLASES[c]] = big & (cl == c)
    for j, nm in enumerate(TIPOS):
        g[nm] = big & (tipo == j)
    g["rango bajo"] = big & (pos < 1 / 3)
    g["rango medio"] = big & (pos >= 1 / 3) & (pos <= 2 / 3)
    g["rango alto"] = big & (pos > 2 / 3)
    g["en cluster"] = big & en_cluster
    g["aislada"] = big & ~en_cluster
    g["horario regular"] = big & rth
    g["noche (Globex)"] = big & ~rth
    return g


def tabla_impacto(H: pd.DataFrame, grupos: dict, cfg: Config) -> pd.DataFrame:
    filas = []
    ses = H["sesion"].to_numpy()
    for nm, m in grupos.items():
        for h in (0,) + tuple(cfg.horizontes_s):
            for medida in ("imp", "der"):
                if medida == "der" and h == 0:
                    continue
                st = media_sesiones(H[f"{medida}_{h}"].to_numpy()[m], ses[m])
                filas.append({"grupo": nm, "h_s": h, "medida": medida, **st})
    return pd.DataFrame(filas)


def resumen_rastreo(R: pd.DataFrame, H: pd.DataFrame, grupos: dict, base: pd.DataFrame) -> pd.DataFrame:
    """% SOSTENIDO / ROTO / NEUTRO por grupo, contra la línea base de huellas normales."""
    def fila(nm, est):
        est = est[np.isfinite(est)]
        n = len(est)
        s, r = int((est == 1).sum()), int((est == -1).sum())
        return {"grupo": nm, "n": n, "sostenido": s / n if n else np.nan, "roto": r / n if n else np.nan,
                "neutro": (n - s - r) / n if n else np.nan, "decididos": s + r,
                "p_sost": s / (s + r) if s + r else np.nan}
    filas = [fila("normales (base)", base["estado"].to_numpy(dtype=float)) if len(base) else fila("normales (base)", np.zeros(0))]
    est_h = pd.Series(np.nan, index=H.index)
    est_h.loc[R.index] = R["estado"].to_numpy(dtype=float)
    for nm, m in grupos.items():
        if nm == "normales":
            continue
        filas.append(fila(nm, est_h.to_numpy()[m]))
    T = pd.DataFrame(filas)
    b = T.iloc[0]
    z, p = [], []
    for _, f in T.iterrows():
        n1, n2 = f["decididos"], b["decididos"]
        if n1 and n2 and f["grupo"] != b["grupo"]:
            pp = (f["p_sost"] * n1 + b["p_sost"] * n2) / (n1 + n2)
            se = math.sqrt(max(pp * (1 - pp) * (1 / n1 + 1 / n2), 1e-12))
            zz = (f["p_sost"] - b["p_sost"]) / se
            z.append(zz)
            p.append(2 * (1 - NormalDist().cdf(abs(zz))))
        else:
            z.append(np.nan)
            p.append(np.nan)
    T["z_vs_base"], T["p_vs_base"] = z, p
    return T


def sensibilidad_rafaga(E: pd.DataFrame, cfg: Config, mascara: np.ndarray) -> pd.DataFrame:
    """Cuántas huellas salen con distintos huecos de ráfaga (la elección de 100 ms, a la vista)."""
    Ew = E[mascara]
    filas = []
    if not len(Ew):
        return pd.DataFrame()
    t, lado, ses, inst, vol = (Ew[c].to_numpy() for c in ("t", "lado", "sesion", "inst", "vol"))
    for gap in (0, 10, 50, 100, 250, 1000):
        cap = max(cfg.rafaga_max_ms, gap * 10)
        hid = asignar_huellas(t, lado, ses, inst, int(gap * NS_MS), int(cap * NS_MS))
        nh = int(hid.max()) + 1
        ne = np.bincount(hid)
        vh = np.bincount(hid, weights=vol)
        filas.append({"gap_ms": gap, "huellas": nh, "eventos_por_huella": len(t) / nh,
                      "vol_en_multievento": float(vh[ne >= 3].sum() / vh.sum()),
                      "p99_tam": float(np.quantile(vh, 0.99))})
    return pd.DataFrame(filas)


def chequeo_lado(E: pd.DataFrame, mascara: np.ndarray) -> dict:
    """
    ¿El side es el del agresor? Con el libro previo: una compra agresiva se ejecuta en el ask o más
    arriba y una venta en el bid o más abajo. Con la lectura de tu script ('A' = compra) sale al
    revés: "compras" en el bid.
    """
    m = mascara & E["libro0"].to_numpy().astype(bool)
    lado, px = E["lado"].to_numpy()[m], E["px_ini"].to_numpy()[m]
    bid, ask = E["bid0"].to_numpy()[m], E["ask0"].to_numpy()[m]
    if not len(lado):
        return {"n": 0, "consistente": np.nan, "tuyo": np.nan}
    ok = np.where(lado > 0, px >= ask, px <= bid)
    tuyo = np.where(-lado > 0, px >= ask, px <= bid)
    return {"n": int(len(lado)), "consistente": float(ok.mean()), "tuyo": float(tuyo.mean())}


def auditar(H: pd.DataFrame, G: pd.DataFrame, C: pd.DataFrame, E: pd.DataFrame, base: pd.DataFrame,
            perm: dict, motor: MotorEventos, cfg: Config, con_libro: bool, par: dict | None) -> Auditoria:
    en_cluster = np.zeros(len(H), bool)
    if len(G):
        en_cluster[G.index[G["cluster_k"].to_numpy() >= 0]] = True
    grupos = grupos_auditoria(H, en_cluster)
    imp = tabla_impacto(H, grupos, cfg)
    win = H["ventana"].to_numpy()
    curva = curva_impacto(H["vol"].to_numpy()[win], H[f"imp_{cfg.h_raiz_s}"].to_numpy()[win])
    # --- impacto neto de momentum y flujo previo (sólo grandes) ---
    control = {"n": 0}
    if len(G) > 30:
        y = G[f"der_{cfg.h_principal_s}"].to_numpy(dtype=float)
        fl = G["flujo_previo"].to_numpy(dtype=float)
        esc = np.nanstd(fl) or 1.0
        X = np.c_[np.ones(len(G)), G["lado"].to_numpy() * G["ret_previo"].to_numpy(dtype=float),
                  G["lado"].to_numpy() * fl / esc]
        control = mco_agrupado(y, X, G["sesion"].to_numpy())
    # --- costos ---
    costos = {}
    if len(G):
        der = G[f"der_{cfg.h_principal_s}"].to_numpy(dtype=float)
        spr = G["spread"].to_numpy(dtype=float)
        costos = {"spread": float(np.nanmean(spr)), "costo_efectivo": float(np.nanmean(G["costo"])),
                  "deriva": float(np.nanmean(der)), "neto": float(np.nanmean(der) - np.nanmean(spr)),
                  "usd_tick": valor_tick_usd(cfg.symbol)}
    cola = hill(H["vol"].to_numpy()[win])
    rastreo = resumen_rastreo(G[["estado"]] if len(G) else pd.DataFrame({"estado": []}), H, grupos, base)
    lado = chequeo_lado(E, E["t"].to_numpy() >= ventana_utc(cfg)[0].value)
    t0 = ventana_utc(cfg)[0].value
    sens = sensibilidad_rafaga(E, cfg, E["t"].to_numpy() >= t0)
    # --- chequeo de cordura ---
    c = []
    r = max(1, motor.registros)
    c.append((motor.operaciones > 0.5 * (r - motor.conteo[REGLAS[0]]),
              f"{motor.operaciones:,} de {motor.registros:,} registros son agresiones válidas ({motor.operaciones / r:.1%})"))
    if con_libro and lado["n"]:
        c.append((lado["consistente"] > 0.95,
                  f"side = AGRESOR: {lado['consistente']:.1%} de las compras se ejecutan en el ask previo o arriba "
                  f"(y las ventas en el bid). Con 'A' = compra, como tu script: {lado['tuyo']:.1%}"))
        c.append((motor.libro_malo < 0.05 * max(1, motor.operaciones),
                  f"libro previo válido en {1 - motor.libro_malo / max(1, motor.operaciones):.1%} de las operaciones"))
    else:
        c.append((True, "sin libro (esquema trades): no hay ABSORCIÓN ni mid; el impacto usa el último precio "
                        "operado y trae el rebote bid-ask"))
    c.append((motor.ts_event_atras <= 1e-4 * r, f"ts_event que retrocede: {motor.ts_event_atras:,}"))
    if motor.latencias:
        lat = np.concatenate(motor.latencias) / 1e3
        c.append((True, f"latencia ts_recv − ts_event: mediana {np.median(lat):,.0f} µs · p99 {np.percentile(lat, 99):,.0f} µs"))
    if par is not None:
        c.append((par["iguales"], f"motor incremental = vectorizado: {par['huellas']:,} huellas de {par['registros']:,} "
                                  f"registros (diferencia máxima {par['max_dif']:.1e})"))
    nw = int(win.sum())
    sin_ref = int((win & (H["clase"].to_numpy() < 0)).sum())
    c.append((sin_ref == 0, f"huellas de la ventana sin distribución de referencia: {sin_ref:,} de {nw:,}"
              + ("  → sube --calentamiento" if sin_ref else "")))
    frac = float((win & (H["clase"].to_numpy() >= 1)).sum() / max(1, nw - sin_ref))
    c.append((0.5 * (1 - cfg.p_grande) <= frac <= 2 * (1 - cfg.p_grande),
              f"{frac:.1%} de las huellas salen ≥ GRANDE (la referencia dice {1 - cfg.p_grande:.0%}; muy lejos = "
              "cambió el régimen respecto a las sesiones previas)"))
    if len(G):
        m0 = float(np.nanmean(G["imp_0"]))
        c.append((m0 > 0, f"impacto inmediato de las grandes {m0:+.2f} ticks (una agresión mueve el precio a su favor)"))
    if np.isfinite(perm.get("p", np.nan)):
        c.append((True, f"clusters: {perm['en_cluster']:,} huellas ≥ {CLASES[cfg.cluster_clase_min]} en cluster contra "
                        f"{perm['esperado']:.0f} del azar "
                        f"(×{perm['razon']:.2f}, p = {perm['p']:.3f})"))
    if np.isfinite(curva["delta"]):
        c.append((curva["delta"] > 0, f"el impacto crece con el tamaño: δ = {curva['delta']:.2f} · R² {curva['r2']:.2f} "
                                      "(cóncavo si < 1; > 1 = las grandes cargan información desproporcionada)"))
    b = rastreo.iloc[0] if len(rastreo) else None
    if b is not None and b["decididos"] >= 200:
        c.append((True, f"línea base del rastreo (huellas normales): {b['p_sost']:.1%} SOSTENIDO entre las decididas "
                        "(< 50 % por el rebote bid-ask y el impacto transitorio)"))
    rolls = int(np.sum(np.diff(E["inst"].to_numpy()) != 0)) if len(E) else 0
    c.append((True, f"rolls en los datos: {rolls} · ninguna medición cruza un roll ni el cierre de la sesión"))
    return Auditoria(imp, curva, perm, rastreo, control, costos, cola, lado, sens, c, par)


def analizar(tienda, cfg: Config, verdad: dict | None = None, chequear_paridad: bool = True,
             verbose: bool = True) -> Resultado:
    validar(cfg)
    E0, motor = correr_motor(tienda, cfg, verbose=verbose)
    if not len(E0):
        sys.exit("❌ No hubo ninguna agresión válida en los datos.")
    E = preparar_eventos(E0, cfg)
    con_libro = bool(motor.tiene_libro and E["libro0"].mean() > 0.5)
    H, hid = agrupar_huellas(E, cfg)
    E["hid"] = hid
    U, pct, clase = clasificar_magnitud(H, cfg)
    H["pct"], H["clase"] = pct, clase
    H["tipo"] = tipificar(H, cfg)
    t0, t1 = ventana_utc(cfg)
    win = (H["t_ini"].to_numpy() >= t0.value) & (H["t_ini"].to_numpy() < t1.value)
    if not win.any():
        sys.exit("❌ Ninguna agresión cae en la ventana --start/--end.")
    H["ventana"] = win
    ctx = contexto(H, E, cfg, con_libro)
    for c in ctx.columns:
        H[c] = ctx[c].to_numpy()
    p0, fut = precios_futuros(H, E, cfg, con_libro, mascara=win)
    lado = H["lado"].to_numpy()
    H["imp_0"] = (lado * (fut[0] - p0)).astype(np.float32)
    for h in cfg.horizontes_s:
        H[f"imp_{h}"] = (lado * (fut[h] - p0)).astype(np.float32)
        H[f"der_{h}"] = (lado * (fut[h] - fut[0])).astype(np.float32)
    lib = H["libro0"].to_numpy().astype(bool)
    H["spread"] = np.where(lib, H["ask0"] - H["bid0"], np.nan)
    H["costo"] = np.where(lib, lado * (H["vwap"].to_numpy() - H["mid0"].to_numpy()), np.nan)
    big = win & (clase >= 1)
    G = H[big].copy()
    G["id"] = asignar_ids(G, cfg.symbol)
    mc = G["clase"].to_numpy() >= cfg.cluster_clase_min
    cid_c, C = detectar_clusters(G[mc], cfg)
    cid = np.full(len(G), -1, np.int64)
    cid[mc] = cid_c
    G["cluster_k"] = cid
    nombres_c = dict(zip(C["k"], C["cluster"])) if len(C) else {}
    G["cluster"] = [nombres_c.get(k, "") for k in cid]
    perm = prueba_clusters(G[mc], cid_c, H, cfg)
    sig = sigma_minuto(E, con_libro)
    if len(G):
        Rr = rastrear(H, G.index.to_numpy(), E, cfg, sig)
        for c in Rr.columns:
            G[c] = Rr[c].to_numpy()
    else:
        for c in ("barrera", "estado", "t_toque_s", "mfe", "mae", "final", "completo"):
            G[c] = []
    rng = np.random.default_rng(7)
    normales = H.index[win & (clase == 0)].to_numpy()
    muestra = np.sort(rng.choice(normales, min(len(normales), cfg.base_normales), replace=False)) \
        if len(normales) else np.zeros(0, int)
    base = rastrear(H, muestra, E, cfg, sig) if len(muestra) else pd.DataFrame({"estado": []})
    par = None
    if chequear_paridad:
        par = paridad(tienda, cfg)
    aud = auditar(H, G, C, E, base, perm, motor, cfg, con_libro, par)
    crudo = motor.operaciones_crudas()
    eid = None
    if crudo:
        eid = eventos_de_crudo(crudo, tick_ns(cfg.symbol))
        if int(eid.max()) + 1 != len(E):
            eid = None
    tu = tu_script(crudo, cfg, t0.value, t1.value, eid)
    info = {"registros": motor.registros, "operaciones": motor.operaciones, "volumen": motor.volumen,
            "eventos": len(E), "huellas": len(H), "huellas_ventana": int(win.sum()), "grandes": len(G),
            "clusters": len(C), "sesiones": int(H.loc[win, "sesion"].nunique()),
            "sesiones_total": int(H["sesion"].nunique()), "con_libro": con_libro,
            "rolls": int(np.sum(np.diff(E["inst"].to_numpy()) != 0)), "sigma_1m": sig}
    res = Resultado(cfg, E, H, U, G, C, motor, aud, tu, info, base, verdad)
    return res


def medir_contra_verdad(res: Resultado, arr: np.ndarray) -> dict:
    """Con la simulación se conoce la verdad: ¿qué tanto encuentra cada método?"""
    v = res.verdad
    cfg = res.cfg
    tk = tick_ns(cfg.symbol)
    s = (arr["side"] == b"B").astype(np.int64) - (arr["side"] == b"A").astype(np.int64)
    q = arr["size"].astype(np.int64)
    px = arr["price"].astype(np.int64)
    valida = (arr["action"] == b"T") & (q > 0) & (px > 0) & ((px % tk) == 0) & (s != 0)
    t = np.maximum.accumulate(arr["ts_event"].astype(np.int64))
    tv, sv, iv = t[valida], s[valida], arr["instrument_id"][valida]
    start = np.r_[True, (tv[1:] != tv[:-1]) | (sv[1:] != sv[:-1]) | (iv[1:] != iv[:-1])]
    eid = np.full(len(arr), -1)
    eid[valida] = np.cumsum(start) - 1
    out = {"eventos_ok": int(eid.max()) + 1 == len(res.E)}
    H = res.H
    hid = np.full(len(arr), -1)
    hid[valida] = res.E["hid"].to_numpy()[eid[valida]]
    enw = np.zeros(len(arr), bool)
    enw[valida] = H["ventana"].to_numpy()[hid[valida]]
    grande = np.zeros(len(arr), bool)
    grande[valida] = H["clase"].to_numpy()[hid[valida]] >= 1
    inst = (v["meta"] >= 0) | (v["estilo"] == 4)
    base_w = valida & enw
    out["vol_inst"] = float(q[inst & base_w].sum() / max(1, q[base_w].sum()))
    out["modulo"] = {"recall": float(q[inst & base_w & grande].sum() / max(1, q[inst & base_w].sum())),
                     "precision": float(q[inst & base_w & grande].sum() / max(1, q[base_w & grande].sum()))}
    tu = res.tu
    if tu.get("disponible"):
        sel = np.flatnonzero(tu["sel"])
        rec = sel[tu["pos"]]
        bigset = np.zeros(len(tu["grupos"]), bool)
        bigset[tu["big"].index.to_numpy()] = True
        g_big = np.zeros(len(arr), bool)
        g_big[rec] = bigset[tu["grupo_de"]]
        en_tu = np.zeros(len(arr), bool)
        en_tu[rec] = True
        bw = en_tu & (arr["action"] == b"T")
        out["tu"] = {"recall": float(q[inst & bw & g_big].sum() / max(1, q[inst & bw].sum())),
                     "precision": float(q[inst & bw & g_big].sum() / max(1, q[bw & g_big].sum()))}
        dir_tuya = np.zeros(len(arr), np.int64)
        dir_tuya[rec] = np.where(s[rec] == -1, 1, -1)
        mm = inst & g_big & (s != 0)
        out["tu"]["direccion"] = float(np.mean(dir_tuya[mm] == s[mm])) if mm.any() else np.nan
        out["tu"]["eventos_partidos"] = tu.get("eventos_partidos", np.nan)
        out["tu"]["big_pedazo"] = tu.get("big_pedazo", np.nan)
    # --- tipos contra el estilo verdadero de las metaórdenes ---
    G = res.G
    filas = []
    if len(G):
        dfr = pd.DataFrame({"h": hid[valida], "q": q[valida], "e": v["estilo"][valida],
                            "inf": v["informada"][valida], "meta": v["meta"][valida],
                            "ice": v["iceberg"][valida]})
        porh = dfr.groupby(["h", "e"])["q"].sum().unstack(fill_value=0)
        dom = porh.idxmax(axis=1)
        frac_dom = porh.max(axis=1) / porh.sum(axis=1)
        Gd = G.join(pd.DataFrame({"estilo": dom, "frac": frac_dom}), how="left")
        out["tipos"] = pd.crosstab(Gd["estilo"].map(ESTILOS), Gd["tipo"].map(dict(enumerate(TIPOS))))
        es_meta = (dfr["meta"] >= 0).to_numpy()
        sumas = dfr.assign(qi=dfr["q"] * (es_meta | (dfr["e"] == 4).to_numpy()), qm=dfr["q"] * es_meta,
                           qinf=dfr["q"] * (es_meta & dfr["inf"].to_numpy())).groupby("h")[["q", "qi", "qm", "qinf"]].sum()
        inst_h = sumas["qi"] / sumas["q"]
        inf_h = sumas["qinf"] / sumas["qm"].replace(0, np.nan)
        Gd["frac_inst"] = inst_h.reindex(Gd.index).fillna(0).to_numpy()
        Gd["frac_inf"] = inf_h.reindex(Gd.index).to_numpy()
        h = cfg.h_principal_s
        for nm, m in (("informadas", (Gd["frac_inst"] > 0.5) & (Gd["frac_inf"] > 0.5)),
                      ("institucionales no informadas", (Gd["frac_inst"] > 0.5) & ~(Gd["frac_inf"] > 0.5)),
                      ("ruido", Gd["frac_inst"] <= 0.5)):
            d = Gd.loc[m, f"der_{h}"].to_numpy(dtype=float)
            e_ = Gd.loc[m, "estado"].to_numpy(dtype=float)
            e_ = e_[np.isfinite(e_)]
            filas.append({"grupo": nm, "n": int(m.sum()), "deriva": float(np.nanmean(d)) if len(d) else np.nan,
                          "sostenido": float(np.mean(e_ == 1)) if len(e_) else np.nan,
                          "roto": float(np.mean(e_ == -1)) if len(e_) else np.nan})
        out["impacto_verdad"] = pd.DataFrame(filas)
        # icebergs
        ices = [i for i in v["icebergs"] if res.H["ventana"].any()]
        t0, t1 = ventana_utc(cfg)
        ices = [i for i in ices if t0.value <= i["t_ini"] < t1.value]
        absor_h = set(H.index[(H["tipo"].to_numpy() == 2) & H["ventana"].to_numpy()])
        det = 0
        for ic in ices:
            hs = set(hid[(v["iceberg"] == ic["id"]) & valida])
            det += bool(hs & absor_h)
        con_ice = set(hid[(v["iceberg"] >= 0) & valida])
        absor_big = set(G.index[G["tipo"].to_numpy() == 2])
        out["icebergs"] = {"n": len(ices), "detectados": det,
                           "precision_absorcion": len(absor_h & con_ice) / max(1, len(absor_h)),
                           "precision_absorcion_grandes": len(absor_big & con_ice) / max(1, len(absor_big)),
                           "absorcion_grandes": len(absor_big)}
        # clusters
        C = res.C
        if len(C):
            ok_dir, n_dir, con_inst = 0, 0, 0
            for _, cr in C.iterrows():
                miembros = G.index[G["cluster_k"].to_numpy() == cr["k"]]
                sub = dfr[dfr["h"].isin(miembros) & ((dfr["meta"] >= 0) | (dfr["e"] == 4))]
                if cr["direccion"] != 0:
                    n_dir += 1
                    if len(sub):
                        con_inst += 1
                        lados = np.sign(sub.merge(G[["lado"]], left_on="h", right_index=True)["lado"])
                        ok_dir += int(np.sign(lados.mean()) == cr["direccion"])
            out["clusters"] = {"direccionales": n_dir, "con_institucional": con_inst, "direccion_ok": ok_dir,
                               "vol_inst_en_cluster": float(
                                   Gd.loc[Gd["cluster_k"] >= 0, "vol"].mul(Gd.loc[Gd["cluster_k"] >= 0, "frac_inst"]).sum()
                                   / max(1e-9, Gd["vol"].mul(Gd["frac_inst"]).sum()))}
    return out


# =============================================================================
# 9. REPORTES
# =============================================================================
def _hora(t_ns: int, cfg: Config, seg: bool = True) -> str:
    t = pd.Timestamp(int(t_ns), tz="UTC")
    f = "%m-%d %H:%M:%S" if seg else "%m-%d %H:%M"
    return f"{t.tz_convert(cfg.tz_mercado):{f}} CT · {t.tz_convert(cfg.tz_local):%H:%M} CDMX"


def _decimales(symbol: str) -> int:
    partes = f"{tick(symbol):.10f}".rstrip("0").split(".")
    return min(6, len(partes[1])) if len(partes) > 1 else 0


def _precio(ticks_: float, cfg: Config) -> str:
    if not np.isfinite(ticks_):
        return "—"
    return f"{ticks_ * tick(cfg.symbol):,.{_decimales(cfg.symbol)}f}"


def reporte_datos(res: Resultado) -> None:
    cfg, m, i = res.cfg, res.motor, res.info
    t0, t1 = ventana_utc(cfg)
    _titulo(f"DATOS · {cfg.symbol} ({nombre(cfg.symbol)}) · {cfg.esquema} · tick {tick(cfg.symbol):g} = "
            f"US$ {valor_tick_usd(cfg.symbol):,.2f}")
    print(f"  Ventana analizada: {_hora(t0.value, cfg, False)}  →  {_hora(t1.value, cfg, False)}")
    print(f"  Sesiones: {i['sesiones']} analizadas + {i['sesiones_total'] - i['sesiones']} de calentamiento "
          f"(sólo dan la referencia de magnitud) · rolls: {i['rolls']}")
    print(f"  Registros: {m.registros:,} · agresiones válidas: {m.operaciones:,} · volumen {m.volumen:,} contratos")
    for k, v in m.conteo.items():
        if v:
            print(f"     descartado · {k:<44} {v:>10,}")
    if m.vol_sin_lado:
        print(f"     (volumen sin agresor, reportado aparte: {m.vol_sin_lado:,} contratos)")
    print(f"  AGRUPACIÓN:  {m.operaciones:,} operaciones → {i['eventos']:,} EVENTOS (agresión exacta de CME) → "
          f"{i['huellas']:,} HUELLAS (ráfagas de ≤ {cfg.rafaga_ms:g} ms, tope {cfg.rafaga_max_ms:g} ms)")
    print(f"  En la ventana: {i['huellas_ventana']:,} huellas · {i['grandes']:,} GRANDES o más · {i['clusters']:,} clusters")
    if not i["con_libro"]:
        print("  ⚠ Sin libro previo (esquema trades): no hay ABSORCIÓN, ni mid, ni spread; el impacto usa el último")
        print("    precio operado. Para el análisis completo:  --esquema tbbo")


def reporte_tu_script(res: Resultado) -> None:
    tu, aud, cfg = res.tu, res.aud, res.cfg
    _titulo("TU SCRIPT (bigtrade_deepsek.py) SOBRE LOS MISMOS REGISTROS")
    if not tu.get("disponible"):
        print("  (no se puede replicar: tu script necesita el libro de cada operación; usa --esquema tbbo)")
        return
    G, big = tu["grupos"], tu["big"]
    print(f"  Grupos (ventana de 100 ms × hit_price × side): {len(G):,} · big trades: {len(big):,}")
    print(f"  Umbrales con TODA la muestra (miran al futuro): p95 {tu['p95']:.0f} · p99 {tu['p99']:.0f} · "
          f"p99.9 {tu['p999']:.0f} contratos")
    U = res.U[res.U["sesion"].isin(res.G["sesion"].unique())] if len(res.G) else res.U
    if len(U):
        print(f"  Los del módulo (causales, por sesión y franja): GRANDE {U['q_grande'].min():.0f}-{U['q_grande'].max():.0f} · "
              f"MEGA {U['q_mega'].min():.0f}-{U['q_mega'].max():.0f} · BALLENA {U['q_ballena'].min():.0f}-{U['q_ballena'].max():.0f}")
    print(f"  Tipos: BLOCK {int((big['tipo'] == 'BLOCK').sum()):,} · SWEEP {int((big['tipo'] == 'SWEEP').sum()):,} · "
          f"FRAGMENTED 0 (nunca se asigna)")
    lado = aud.lado
    if lado["n"]:
        print(f"  DIRECCIÓN: tu 'Buy' (side A) se ejecuta en el BID del libro previo en el {1 - lado['tuyo']:.1%} "
              f"de los casos → son VENTAS agresivas.")
        print(f"     Con side = agresor ('B' = compra), el {lado['consistente']:.1%} de las compras sale en el ask: así está bien.")
    if "big_mezclados" in tu:
        print(f"  {tu['big_mezclados']:.1%} de tus big trades suman órdenes agresivas DISTINTAS que coincidieron en los "
              f"mismos 100 ms (el módulo las separa)")
    print(f"  Clusters: {tu['n_clusters']:,}, de ellos {tu['clusters_mixtos']:,} mezclan compras y ventas sin decirlo")
    h = cfg.h_principal_s // 60
    if h in TU_HORIZONTES_MIN:
        r = tu["ret"][h]
        b = big["dir_tuya"].to_numpy()
        ceros = float(np.mean(r == 0.0))
        print(f"  Tus retornos a {h} min: 'tras BUY' {np.mean(r[b > 0]) if (b > 0).any() else np.nan:+.2f} bps · "
              f"'tras SELL' {np.mean(r[b < 0]) if (b < 0).any() else np.nan:+.2f} bps · {ceros:.1%} son 0.0 inventados")


def reporte_magnitud(res: Resultado) -> None:
    cfg, H = res.cfg, res.H
    _titulo("2 · MAGNITUD EMPÍRICA — percentiles causales (sesiones anteriores, por franja)")
    U = res.U
    ses_w = np.unique(H.loc[H["ventana"], "sesion"])
    print("  sesión      franja     ref (sesiones)   GRANDE ≥   MEGA ≥   BALLENA ≥   huellas")
    for _, f in U[U["sesion"].isin(ses_w)].iterrows():
        print(f"  {fecha_de_dia(f['sesion']):%Y-%m-%d}  {'regular' if f['franja'] else 'noche  '}   "
              f"{int(f['n_ref']):>9,} ({int(f['sesiones_ref'])})   {_fmt(f['q_grande'], 0, 8)} {_fmt(f['q_mega'], 0, 8)} "
              f"{_fmt(f['q_ballena'], 0, 10)}   {int(f['n']):>8,}")
    w = H["ventana"].to_numpy()
    cl = H["clase"].to_numpy()
    vol = H["vol"].to_numpy()
    tot = vol[w].sum()
    print()
    for c in range(4):
        m = w & (cl == c)
        print(f"  {CLASES[c]:<8} {int(m.sum()):>9,} huellas ({m.sum() / max(1, w.sum()):6.2%})   "
              f"{vol[m].sum() / max(1, tot):6.1%} del volumen")
    a, k = res.aud.cola
    print(f"\n  Cola de la distribución (Hill, k = {k}): α = {a:.2f}  "
          f"(la literatura reporta ≈ 1.5 para el volumen por operación; α < 2 = varianza infinita:")
    print("   la media y la desviación estándar no sirven como umbral, los percentiles sí)")


def reporte_tipos(res: Resultado) -> None:
    G = res.G
    _titulo("3 · TIPO DE FLUJO (huellas grandes)")
    if not len(G):
        print("  (no hay huellas grandes)")
        return
    print("  tipo          n      vol medio   eventos   niveles   oculta   costo vs mid   GRANDE/MEGA/BALLENA")
    for j, nm in enumerate(TIPOS):
        g = G[G["tipo"] == j]
        if not len(g):
            continue
        cl = [int((g["clase"] == c).sum()) for c in (1, 2, 3)]
        print(f"  {nm:<12} {len(g):>5,}   {g['vol'].mean():>9.1f}   {g['n_eventos'].mean():>7.1f}   "
              f"{g['span'].mean():>7.1f}   {g['oculta'].mean():>6.1f}   {_fmt(np.nanmean(g['costo']), 2, 8)} t      "
              f"{cl[0]}/{cl[1]}/{cl[2]}")


def reporte_clusters(res: Resultado) -> None:
    C, p, cfg = res.C, res.aud.perm, res.cfg
    _titulo(f"4 · CLUSTERS (huellas ≥ {CLASES[cfg.cluster_clase_min]} a ≤ {cfg.cluster_gap_s:g} s entre sí)")
    if not len(C):
        print("  (sin clusters)")
        return
    d = C["direccion"].to_numpy()
    print(f"  {len(C):,} clusters · COMPRADOR {int((d > 0).sum())} · VENDEDOR {int((d < 0).sum())} · DISPUTA {int((d == 0).sum())}")
    if np.isfinite(p["p"]):
        print(f"  ¿Más agrupados que la actividad? {p['en_cluster']:,} en cluster contra {p['esperado']:.0f} si la clase "
              f"cayera al azar entre las huellas de la misma sesión y franja (×{p['razon']:.2f}) · p = {p['p']:.3f}")
    if np.isfinite(p["pureza"]):
        print(f"  ¿De un solo lado? pureza {p['pureza']:.2f} contra {p['pureza_azar']:.2f} con los lados barajados · "
              f"p = {p['p_dir']:.3f}")
    print("\n  cluster          inicio                      dur    n    neto    pureza   dirección   precio")
    for _, c in C.sort_values("vol", ascending=False).head(12).iterrows():
        nm = {1: "COMPRADOR", -1: "VENDEDOR", 0: "DISPUTA"}[int(c["direccion"])]
        print(f"  {c['cluster']:<15} {_hora(c['t_ini'], cfg)}  {c['dur_s']:>5.0f}s {c['n']:>4} {c['neto']:>+7,}   "
              f"{c['pureza']:.2f}   {nm:<10} {_precio(c['vwap'], cfg)}")


def reporte_impacto(res: Resultado) -> None:
    cfg, aud = res.cfg, res.aud
    _titulo("5 · AUDITORÍA DE IMPACTO PREDICTIVO — en ticks, a favor del agresor, IC 95 % agrupado por sesión")
    T = aud.impacto
    hs = [h for h in cfg.horizontes_s]
    print("  IMPACTO = desde el mid ANTES de la huella · DERIVA = desde el primer libro DESPUÉS (lo que se podía operar)")
    print("  grupo                  n     " + "".join(f"{_etq_h(h):>9}" for h in hs))
    for medida, titulo in (("imp", "impacto"), ("der", "deriva")):
        print(f"  — {titulo} —")
        for g in ("normales", "grandes (todas)", "GRANDE", "MEGA", "BALLENA") + TIPOS + (
                "rango bajo", "rango alto", "en cluster", "aislada"):
            f = T[(T["grupo"] == g) & (T["medida"] == medida)]
            if not len(f) or f["n"].max() == 0:
                continue
            fila = "".join((f"{f.loc[f['h_s'] == h, 'media'].iloc[0]:>+8.2f}" +
                            ("*" if f.loc[f['h_s'] == h, 'p'].iloc[0] < 0.05 else " ")) if (f["h_s"] == h).any() else " " * 9
                           for h in hs)
            print(f"  {g:<20} {int(f['n'].max()):>6,}  {fila}")
    print("  (* = p < 0.05 con t entre sesiones; con pocas sesiones casi nada lo alcanza: es honesto)")
    h = cfg.h_principal_s
    ct = aud.control
    if ct.get("n", 0) and np.isfinite(ct["coef"][0]):
        print(f"\n  Deriva a {_etq_h(h)} de las grandes NETA de momentum y flujo de los 5 min previos: "
              f"{ct['coef'][0]:+.2f} ticks (t {ct['t'][0]:+.2f}, p {ct['p'][0]:.3f}, {ct['sesiones']} sesiones)")
    cv = aud.curva
    if np.isfinite(cv["delta"]):
        print(f"  Impacto a {_etq_h(cfg.h_raiz_s)} contra el tamaño: I ∝ Q^{cv['delta']:.2f} (R² {cv['r2']:.2f}) — "
              f"cóncavo si < 1 (raíz cuadrada ≈ 0.5)")
    co = aud.costos
    if co and np.isfinite(co.get("spread", np.nan)):
        usd = co["usd_tick"]
        print(f"  Costos: spread medio {co['spread']:.2f} t · el agresor pagó {co['costo_efectivo']:+.2f} t contra el mid · "
              f"deriva a {_etq_h(h)} {co['deriva']:+.2f} t → neta de un spread {co['neto']:+.2f} t "
              f"(US$ {co['neto'] * usd:+,.2f} por contrato)")


def _etq_h(h: int) -> str:
    return f"{h} s" if h < 60 else (f"{h // 60} min" if h < 3600 else f"{h // 3600} h")


def reporte_rastreo(res: Resultado, n: int = 15) -> None:
    cfg, G, T = res.cfg, res.G, res.aud.rastreo
    _titulo(f"6 · RASTREO DE IDs — triple barrera de {cfg.seguimiento_s // 60} min sobre el VWAP de cada huella")
    print("  grupo                    n    SOSTENIDO   ROTO   NEUTRO   P(sost | decidido)   vs base")
    for _, f in T.iterrows():
        if f["n"] == 0:
            continue
        pv = f"p {f['p_vs_base']:.3f}" if np.isfinite(f["p_vs_base"]) else ""
        print(f"  {f['grupo']:<22} {int(f['n']):>5,}   {_pct(f['sostenido'])}  {_pct(f['roto'])}  {_pct(f['neutro'])}"
              f"        {_pct(f['p_sost'])}        {pv}")
    if not len(G):
        return
    print(f"\n  Últimos {min(n, len(G))} IDs (de {len(G):,}):")
    print("  ID            hora                          lado     vol  clase   pct     tipo          precio    "
          f"{_etq_h(cfg.h_principal_s):>6}  estado      cluster")
    for _, g in G.tail(n).iterrows():
        est = ESTADOS.get(int(g["estado"]), "—") if np.isfinite(g["estado"]) else "—"
        print(f"  {g['id']:<13} {_hora(g['t_ini'], cfg)}  {'COMPRA' if g['lado'] > 0 else 'VENTA ':<6} {int(g['vol']):>6,}  "
              f"{CLASES[int(g['clase'])]:<7} {g['pct']:.4f}  {TIPOS[int(g['tipo'])]:<12} {_precio(g['vwap'], cfg):>10} "
              f"{_fmt(g[f'der_{cfg.h_principal_s}'], 1, 6)}  {est:<10}  {g['cluster']}")


def reporte_cordura(res: Resultado) -> None:
    _titulo("CHEQUEO DE CORDURA")
    for ok, txt in res.aud.cordura:
        print(f"  {'✓' if ok else '⚠'} {txt}")


def reporte_verdad(res: Resultado) -> None:
    md = res.medicion
    if not md:
        return
    _titulo("CONTRA LA VERDAD DE LA SIMULACIÓN")
    print(f"  Volumen institucional (metaórdenes + ráfagas contra icebergs): {md['vol_inst']:.1%} del total")
    m = md["modulo"]
    print(f"  Módulo  · ≥ GRANDE contiene el {m['recall']:.1%} del volumen institucional · precisión {m['precision']:.1%}")
    if "tu" in md:
        t = md["tu"]
        print(f"  Tu script · big trades contienen el {t['recall']:.1%} · precisión {t['precision']:.1%} · "
              f"dirección correcta {t['direccion']:.1%}")
    if "tipos" in md:
        print("\n  Estilo verdadero (filas) contra tipo asignado (columnas), huellas grandes:")
        print("  " + md["tipos"].to_string().replace("\n", "\n  "))
    if "icebergs" in md:
        ic = md["icebergs"]
        print(f"\n  Icebergs en la ventana: {ic['n']} · con ABSORCIÓN detectada: {ic['detectados']} · "
              f"precisión de ABSORCIÓN {ic['precision_absorcion']:.1%} (grandes: {ic['precision_absorcion_grandes']:.1%})")
    if "clusters" in md:
        c = md["clusters"]
        print(f"  Clusters direccionales: {c['direccionales']} · con flujo institucional {c['con_institucional']} · "
              f"dirección correcta {c['direccion_ok']} · {c['vol_inst_en_cluster']:.1%} del volumen institucional "
              "grande cae en clusters")
    if "impacto_verdad" in md:
        print("\n  Deriva y rastreo según la verdad:")
        print("  " + md["impacto_verdad"].round(3).to_string(index=False).replace("\n", "\n  "))


# =============================================================================
# 10. DASHBOARD — 3 tableros: rastreador, auditoría y tabla de IDs
# =============================================================================
C = {"fondo": "#fcfcfb", "tinta": "#0b0b0b", "tinta2": "#52514e", "tenue": "#898781",
     "grid": "#e1e0d9", "eje": "#c3c2b7", "neutro": "#d6d5ce",
     "s1": "#2a78d6", "s2": "#eb6834", "s3": "#1baf7a", "s4": "#eda100", "s5": "#e87ba4",
     "s6": "#008300", "s7": "#4a3aa7", "s8": "#e34948",
     "alza": "#256abf", "baja": "#e34948"}
COMPRA, VENTA = C["s1"], C["baja"]
COLOR_TIPO = {0: C["s7"], 1: C["s2"], 2: C["s3"], 3: C["s4"]}         # validado: CVD ΔE ≥ 9
MARCA_TIPO = {0: "o", 1: "D", 2: "s", 3: "P"}
TAM_CLASE = {1: 9, 2: 34, 3: 120}
ALFA_CLASE = {1: 0.30, 2: 0.70, 3: 0.95}
TINTA_CLASE = {0: "#b8b7ae", 1: C["tenue"], 2: C["tinta2"], 3: C["tinta"]}
COLOR_ESTADO = {1: C["s6"], 0: C["neutro"], -1: C["s8"]}


def _preparar_grafico(mostrar: bool):
    try:
        import matplotlib
    except ModuleNotFoundError:
        print("⚠ matplotlib no está instalado:  pip install matplotlib")
        return None, False
    sin_pantalla = (sys.platform.startswith("linux") and not os.environ.get("DISPLAY")
                    and not os.environ.get("WAYLAND_DISPLAY"))
    if not mostrar or sin_pantalla:
        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
        return plt, False
    import matplotlib.pyplot as plt
    if not matplotlib.get_backend().lower().startswith("agg"):
        return plt, True
    for backend in ("TkAgg", "QtAgg", "Qt5Agg", "MacOSX", "WXAgg"):
        try:
            plt.switch_backend(backend)
            if not matplotlib.get_backend().lower().startswith("agg"):
                return plt, True
        except Exception:
            continue
    try:
        plt.switch_backend("Agg")
    except Exception:
        pass
    return plt, False


def _estilo(ax, titulo: str | None = None) -> None:
    ax.set_facecolor(C["fondo"])
    ax.grid(True, color=C["grid"], linewidth=0.7)
    ax.set_axisbelow(True)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(C["eje"])
    ax.tick_params(colors=C["tinta2"], labelsize=8)
    if titulo:
        ax.set_title(titulo, color=C["tinta"], fontsize=10, loc="left", pad=8)


def _leyenda(ax, **kw) -> None:
    opciones = dict(fontsize=7.5, frameon=True, facecolor=C["fondo"], edgecolor="none", framealpha=0.9,
                    labelcolor=C["tinta2"], loc="upper left")
    opciones.update(kw)
    ax.legend(**opciones)


def mostrar_tableros(plt, ventana: bool, rutas: list[Path]) -> None:
    if plt is None or not rutas:
        return
    if not ventana:
        for ruta in rutas:
            try:
                if sys.platform.startswith("win"):
                    os.startfile(str(ruta))                       # noqa: S606
                elif sys.platform == "darwin":
                    import subprocess
                    subprocess.Popen(["open", str(ruta)])
                else:
                    import subprocess
                    subprocess.Popen(["xdg-open", str(ruta)], stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
            except Exception:
                print(f"   (sin ventana disponible; abre el archivo:  {ruta})")
        return
    print("   Abriendo las ventanas… ciérralas para que termine el script.")
    try:
        plt.show()
    except Exception as ex:
        print(f"   No se pudo abrir la ventana ({type(ex).__name__}); los PNG están en {rutas[0].parent}")


class Rejilla:
    """Minutos con operaciones de la ventana, en TIEMPO DE NEGOCIACIÓN (sin huecos de noche ni fin de semana)."""

    def __init__(self, res: Resultado):
        cfg, E = res.cfg, res.E
        t0, t1 = ventana_utc(cfg)
        t = E["t"].to_numpy()
        m = (t >= t0.value) & (t < t1.value)
        precio = E["mid0"].to_numpy() if res.info["con_libro"] else E["px_fin"].to_numpy().astype(float)
        precio = np.where(np.isfinite(precio), precio, E["px_fin"].to_numpy())
        df = pd.DataFrame({"m": t[m] // (60 * NS), "p": precio[m], "s": E["sesion"].to_numpy()[m],
                           "cvd": (E["lado"].to_numpy() * E["vol"].to_numpy())[m]})
        df["cvd"] = df.groupby("s")["cvd"].cumsum()
        u = df.groupby("m").last()
        self.minutos = u.index.to_numpy()
        self.precio = u["p"].to_numpy() * tick(cfg.symbol)
        self.sesion = u["s"].to_numpy()
        self.cvd = u["cvd"].to_numpy()
        self.n = len(self.minutos)

    def pos(self, t_ns) -> np.ndarray:
        k = np.searchsorted(self.minutos, np.asarray(t_ns, np.int64) // (60 * NS), side="right") - 1
        return np.clip(k, 0, max(0, self.n - 1))

    def eje(self, ax, tz: str, n_ticks: int = 9) -> None:
        if self.n < 2:
            return
        pos = np.unique(np.linspace(0, self.n - 1, n_ticks).round().astype(int))
        loc = a_indice(self.minutos[pos] * 60 * NS).tz_convert(tz)
        ax.set_xticks(pos)
        ax.set_xticklabels([t.strftime("%m-%d\n%H:%M") for t in loc], fontsize=8)

    def sesiones(self, ax) -> None:
        for i in np.flatnonzero(np.r_[False, self.sesion[1:] != self.sesion[:-1]]):
            ax.axvline(i - 0.5, color=C["eje"], linewidth=0.9, zorder=0)


def tablero_rastreador(res: Resultado, plt, ruta: Path):
    from matplotlib.lines import Line2D
    cfg, G, Cl = res.cfg, res.G, res.C
    R = Rejilla(res)
    fig = plt.figure(figsize=(19, 15))
    fig.patch.set_facecolor(C["fondo"])
    gs = fig.add_gridspec(4, 1, height_ratios=[2.3, 1.0, 1.0, 0.9], hspace=0.28, bottom=0.05, top=0.94)
    a1 = fig.add_subplot(gs[0])
    a2 = fig.add_subplot(gs[1], sharex=a1)
    a3 = fig.add_subplot(gs[2], sharex=a1)
    a4 = fig.add_subplot(gs[3], sharex=a1)
    n_b = int((G["clase"] == 3).sum()) if len(G) else 0
    fig.suptitle(f"Rastreador de ID · {cfg.symbol} ({nombre(cfg.symbol)}) · {len(G):,} huellas grandes · "
                 f"{n_b} BALLENA · {len(Cl):,} clusters", x=0.01, ha="left", color=C["tinta"], fontsize=12.5)
    tk = tick(cfg.symbol)
    # --- 1: precio, huellas grandes, clusters y niveles rastreados ---
    _estilo(a1, "Precio con las huellas grandes (color = lado del agresor · forma = tipo · tamaño = magnitud) · "
                "fondo = clusters · líneas = nivel de cada BALLENA rastreado")
    R.sesiones(a1)
    a1.plot(np.arange(R.n), R.precio, color=C["tinta"], linewidth=0.9, zorder=3)
    if len(Cl):
        for _, c in Cl.iterrows():
            p0, p1 = R.pos([c["t_ini"], c["t_fin"]])
            col = COMPRA if c["direccion"] > 0 else (VENTA if c["direccion"] < 0 else C["tenue"])
            a1.axvspan(p0 - 0.5, p1 + 0.5, color=col, alpha=0.10, linewidth=0, zorder=1)
    if len(G):
        x = R.pos(G["t_ini"].to_numpy())
        y = G["vwap"].to_numpy() * tk
        for c in (1, 2, 3):
            for j in range(4):
                m = (G["clase"].to_numpy() == c) & (G["tipo"].to_numpy() == j)
                if not m.any():
                    continue
                col = np.where(G["lado"].to_numpy()[m] > 0, COMPRA, VENTA)
                a1.scatter(x[m], y[m], s=TAM_CLASE[c], c=col, marker=MARCA_TIPO[j], alpha=ALFA_CLASE[c],
                           edgecolors=C["fondo"] if c < 3 else C["tinta"], linewidths=0.6 if c < 3 else 0.9,
                           zorder=4 + c)
        top = G[G["clase"] == 3] if n_b else G[G["clase"] == 2]
        top = top.nlargest(min(14, len(top)), "vol")
        fin_seg = cfg.seguimiento_s * NS
        ult_pos = {}
        for _, g in top.sort_values("t_ini").iterrows():
            p0 = int(R.pos([g["t_ini"]])[0])
            t_end = g["t_fin"] + (g["t_toque_s"] * NS if np.isfinite(g["t_toque_s"]) else fin_seg)
            p1 = int(R.pos([int(t_end)])[0])
            col = COMPRA if g["lado"] > 0 else VENTA
            est = int(g["estado"]) if np.isfinite(g["estado"]) else 0
            a1.plot([p0, max(p1, p0 + 1)], [g["vwap"] * tk] * 2, color=col, linewidth=1.1,
                    linestyle={1: "-", 0: "--", -1: ":"}[est], zorder=8)
            cerca = sum(1 for q_ in ult_pos.values() if abs(q_ - p0) < max(3, R.n // 60))
            ult_pos[g["id"]] = p0
            dy = (9 + 11 * cerca) * (1 if g["lado"] > 0 else -1) - (4 if g["lado"] < 0 else 0)
            a1.annotate(f"{g['id']} {'✓' if est == 1 else ('✗' if est == -1 else '·')}",
                        xy=(p0, g["vwap"] * tk), xytext=(5, dy), textcoords="offset points", fontsize=7,
                        color=C["tinta"], zorder=9,
                        bbox=dict(boxstyle="round,pad=0.15", facecolor=C["fondo"], edgecolor="none", alpha=0.85))
    hand = [Line2D([], [], marker="o", linestyle="", color=COMPRA, label="compra agresiva"),
            Line2D([], [], marker="o", linestyle="", color=VENTA, label="venta agresiva")]
    hand += [Line2D([], [], marker=MARCA_TIPO[j], linestyle="", color=C["tinta2"], markersize=6, label=TIPOS[j])
             for j in range(4)]
    hand += [Line2D([], [], marker="o", linestyle="", color=C["tinta2"], markersize=math.sqrt(TAM_CLASE[c]),
                    alpha=ALFA_CLASE[c], label=CLASES[c]) for c in (1, 2, 3)]
    hand += [Line2D([], [], color=C["tinta2"], linestyle=ls, label=f"nivel {ESTADOS[e]}")
             for e, ls in ((1, "-"), (-1, ":"))]
    a1.legend(handles=hand, loc="upper left", fontsize=7.5, frameon=True, facecolor=C["fondo"], edgecolor="none",
              framealpha=0.9, labelcolor=C["tinta2"], ncol=11, columnspacing=1.4, handletextpad=0.5)
    a1.set_ylabel("precio", color=C["tinta2"], fontsize=9)
    # --- 2: tamaño de cada huella grande contra sus umbrales causales ---
    _estilo(a2, "Tamaño de cada huella grande (compras arriba, ventas abajo) y sus umbrales CAUSALES "
                "(sesiones anteriores, por franja)")
    R.sesiones(a2)
    if len(G):
        x = R.pos(G["t_ini"].to_numpy())
        sv = G["lado"].to_numpy() * G["vol"].to_numpy()
        a2.vlines(x, 0, sv, colors=np.where(sv > 0, COMPRA, VENTA), linewidth=0.8, alpha=0.85)
        U = res.U.set_index(["sesion", "franja"])
        seg_m = reloj_sesion(R.minutos * 60 * NS, cfg.tz_mercado)[1]
        r0, r1 = segundo_de_hora(cfg.rth_ct[0]), segundo_de_hora(cfg.rth_ct[1])
        fr = ((seg_m >= r0) & (seg_m < r1)).astype(int) if cfg.por_franja else np.zeros(R.n, int)
        for col, nm, ls in (("q_grande", "GRANDE", ":"), ("q_mega", "MEGA", "--"), ("q_ballena", "BALLENA", "-")):
            q = np.array([U[col].get((s_, f_), np.nan) for s_, f_ in zip(R.sesion, fr)])
            a2.step(np.arange(R.n), q, where="mid", color=C["tinta2"], linewidth=0.8, linestyle=ls, label=f"umbral {nm}")
            a2.step(np.arange(R.n), -q, where="mid", color=C["tinta2"], linewidth=0.8, linestyle=ls)
        a2.axhline(0, color=C["eje"], linewidth=0.8)
        _leyenda(a2, ncol=3)
    a2.set_ylabel("contratos", color=C["tinta2"], fontsize=9)
    # --- 3: CVD de la sesión, todo el flujo contra sólo las grandes ---
    _estilo(a3, "CVD de la sesión (compras − ventas agresivas, se reinicia en cada sesión): todo el flujo "
                "contra sólo las huellas grandes")
    R.sesiones(a3)
    a3.plot(np.arange(R.n), R.cvd, color=C["tinta"], linewidth=1.0, label="CVD de todo el flujo")
    if len(G):
        gc = G.assign(sv=G["lado"] * G["vol"]).groupby("sesion")["sv"].cumsum().to_numpy()
        df = pd.DataFrame({"p": R.pos(G["t_ini"].to_numpy()), "c": gc}).groupby("p")["c"].last()
        serie = pd.Series(np.nan, index=np.arange(R.n))
        serie.loc[df.index] = df.to_numpy()
        serie = serie.groupby(R.sesion).ffill().fillna(0.0)
        a3.plot(np.arange(R.n), serie.to_numpy(), color=C["s7"], linewidth=1.1, label="CVD de las huellas grandes")
    a3.axhline(0, color=C["eje"], linewidth=0.8)
    a3.set_ylabel("contratos", color=C["tinta2"], fontsize=9)
    _leyenda(a3, ncol=2)
    # --- 4: dónde actúan las grandes dentro del rango de la sesión ---
    _estilo(a4, "¿Dónde aparecen? Posición en el rango de la sesión HASTA ese momento (0 = mínimo, 1 = máximo)")
    R.sesiones(a4)
    if len(G):
        x = R.pos(G["t_ini"].to_numpy())
        pr = G["pos_rango"].to_numpy(dtype=float)
        tam = np.array([TAM_CLASE[int(c)] for c in G["clase"]]) * 0.6
        a4.scatter(x, np.clip(pr, -0.1, 1.1), s=tam, c=np.where(G["lado"] > 0, COMPRA, VENTA), alpha=0.5,
                   linewidths=0)
    for yv in (1 / 3, 2 / 3):
        a4.axhline(yv, color=C["tinta2"], linestyle=":", linewidth=0.9)
    a4.set_ylim(-0.15, 1.15)
    a4.set_ylabel("posición", color=C["tinta2"], fontsize=9)
    for ax in (a1, a2, a3):
        ax.tick_params(labelbottom=False)
    R.eje(a4, cfg.tz_local)
    a4.set_xlim(-1, max(1, R.n))
    fig.text(0.008, 0.012, f"{IDENTIFICADOR} · eje en tiempo de negociación (minutos con operaciones) · líneas "
             "verticales = cambio de sesión · fechas en CDMX · junto al ID: ✓ sostenido · ✗ roto · · neutro",
             color=C["tenue"], fontsize=7.5)
    fig.savefig(ruta, dpi=110, facecolor=C["fondo"], bbox_inches="tight")
    return fig


def tablero_auditoria(res: Resultado, plt, ruta: Path):
    import textwrap as _tw
    from matplotlib.ticker import MaxNLocator
    cfg, aud, H, G = res.cfg, res.aud, res.H, res.G
    fig = plt.figure(figsize=(19, 15))
    fig.patch.set_facecolor(C["fondo"])
    gs = fig.add_gridspec(3, 3, hspace=0.48, wspace=0.28, bottom=0.05, top=0.93)
    (b1, b2, b3), (b4, b5, b6), (b7, b8, b9) = [[fig.add_subplot(gs[i, j]) for j in range(3)] for i in range(3)]
    fig.suptitle(f"Rastreador de ID · auditoría de impacto, magnitud, clusters y cordura · {cfg.symbol}",
                 x=0.01, ha="left", color=C["tinta"], fontsize=12.5)
    T = aud.impacto
    hs = (0,) + tuple(cfg.horizontes_s)
    etq = ["después"] + [_etq_h(h) for h in cfg.horizontes_s]
    # 1 — curva de impacto por magnitud
    _estilo(b1, "IMPACTO desde el mid previo, a favor del agresor (ticks, IC 95 %)")
    lim_b1 = []
    for nm, colr in (("normales", TINTA_CLASE[0]), ("GRANDE", TINTA_CLASE[1]), ("MEGA", TINTA_CLASE[2]),
                     ("BALLENA", TINTA_CLASE[3])):
        f = T[(T["grupo"] == nm) & (T["medida"] == "imp")].set_index("h_s").reindex(hs)
        if f["n"].fillna(0).max() < 10:
            continue
        x = np.arange(len(hs))
        b1.plot(x, f["media"], color=colr, linewidth=2, marker="o", markersize=4,
                label=f"{nm} (n = {int(f['n'].max()):,})")
        if f["n"].max() >= 30:
            b1.fill_between(x, f["ic_bajo"], f["ic_alto"], color=colr, alpha=0.12, linewidth=0)
        lim_b1.extend(np.abs(f["media"].to_numpy(dtype=float)).tolist())
    b1.axhline(0, color=C["eje"], linewidth=0.9)
    if lim_b1 and np.isfinite(lim_b1).any():
        m_ = float(np.nanmax(lim_b1))
        b1.set_ylim(-max(0.5, 1.2 * m_), max(0.5, 2.0 * m_))
    b1.set_xticks(range(len(hs)))
    b1.set_xticklabels(etq, fontsize=7.5)
    b1.set_ylabel("ticks", color=C["tinta2"], fontsize=9)
    _leyenda(b1)
    # 2 — transitorio vs permanente por tipo
    h = cfg.h_principal_s
    _estilo(b2, f"Por tipo: impacto a 1 s contra DERIVA posterior a {_etq_h(h)} (IC 95 %)")
    grupos_b = ["normales"] + list(TIPOS)
    x = np.arange(len(grupos_b))
    lim_b2 = []
    for k, (medida, hh, alfa, etq_) in enumerate((("imp", 1, 0.45, "impacto a 1 s"),
                                                   ("der", h, 1.0, f"deriva a {_etq_h(h)}"))):
        vals, lo, hi = [], [], []
        for g in grupos_b:
            f = T[(T["grupo"] == g) & (T["medida"] == medida) & (T["h_s"] == hh)]
            vals.append(f["media"].iloc[0] if len(f) else np.nan)
            lo.append(f["ic_bajo"].iloc[0] if len(f) else np.nan)
            hi.append(f["ic_alto"].iloc[0] if len(f) else np.nan)
        vals, lo, hi = np.array(vals), np.array(lo), np.array(hi)
        cols = [TINTA_CLASE[0]] + [COLOR_TIPO[j] for j in range(4)]
        b2.bar(x - 0.2 + 0.4 * k, vals, width=0.38, color=cols, alpha=alfa, label=etq_)
        err = np.vstack([vals - lo, hi - vals])
        b2.errorbar(x - 0.2 + 0.4 * k, vals, yerr=np.where(np.isfinite(err), err, 0), fmt="none",
                    ecolor=C["tinta"], elinewidth=0.8, capsize=2)
        lim_b2.extend(np.abs(vals[np.isfinite(vals)]).tolist())
    b2.axhline(0, color=C["eje"], linewidth=0.9)
    if lim_b2:
        b2.set_ylim(-2.5 * max(lim_b2) - 0.2, 2.5 * max(lim_b2) + 0.2)
    b2.set_xticks(x)
    b2.set_xticklabels(grupos_b, fontsize=8)
    b2.set_ylabel("ticks", color=C["tinta2"], fontsize=9)
    _leyenda(b2)
    # 3 — impacto contra tamaño
    cv = aud.curva
    _estilo(b3, f"Impacto a {_etq_h(cfg.h_raiz_s)} contra el tamaño de la huella (log-log)")
    cb = cv["cubetas"]
    if len(cb):
        u = cb[cb["imp"] > 0]
        b3.errorbar(u["q_media"], u["imp"], yerr=1.96 * u["se"], fmt="o", color=C["s7"], markersize=4,
                    ecolor=C["tenue"], elinewidth=0.8, capsize=2, label="media por cubeta (IC 95 %)")
        if np.isfinite(cv["delta"]):
            xs = np.logspace(math.log10(u["q_media"].min()), math.log10(u["q_media"].max()), 20)
            b3.plot(xs, np.exp(cv["a"]) * xs ** cv["delta"], color=C["tinta"], linewidth=1.5,
                    label=f"ajuste: I ∝ Q^{cv['delta']:.2f} (R² {cv['r2']:.2f})")
            b3.plot(xs, np.exp(cv["a"]) * xs[0] ** (cv["delta"] - 0.5) * xs ** 0.5, color=C["tinta2"],
                    linestyle=":", linewidth=1.0, label="raíz cuadrada (δ = 0.5)")
        b3.set_xscale("log")
        b3.set_yscale("log")
        from matplotlib.ticker import NullFormatter
        b3.xaxis.set_minor_formatter(NullFormatter())
        b3.yaxis.set_minor_formatter(NullFormatter())
        _leyenda(b3)
    b3.set_xlabel("contratos", color=C["tinta2"], fontsize=9)
    b3.set_ylabel("ticks", color=C["tinta2"], fontsize=9)
    # 4 — distribución del tamaño (CCDF) y umbrales
    _estilo(b4, "Tamaño de las huellas: P(tamaño ≥ x), umbrales y cola de Hill")
    w = H["ventana"].to_numpy()
    v = np.sort(H["vol"].to_numpy()[w])
    if len(v):
        u_, cnt = np.unique(v, return_counts=True)
        ccdf = 1 - (np.cumsum(cnt) - cnt) / len(v)
        b4.plot(u_, ccdf, color=C["tinta"], linewidth=1.6, drawstyle="steps-post", label="huellas de la ventana")
        Uw = res.U[res.U["sesion"].isin(np.unique(H.loc[w, "sesion"]))]
        for col, nm, ls in (("q_grande", "GRANDE", ":"), ("q_mega", "MEGA", "--"), ("q_ballena", "BALLENA", "-")):
            if len(Uw) and np.isfinite(Uw[col]).any():
                b4.axvline(float(np.nanmedian(Uw[col])), color=C["tinta2"], linestyle=ls, linewidth=1.0,
                           label=f"{nm} (mediana {np.nanmedian(Uw[col]):.0f})")
        a, k = aud.cola
        if np.isfinite(a):
            xk = v[::-1][k]
            xs = np.logspace(math.log10(xk), math.log10(v[-1]), 10)
            b4.plot(xs, (k / len(v)) * (xs / xk) ** (-a), color=C["s2"], linewidth=1.5, label=f"Hill: α = {a:.2f}")
        b4.set_xscale("log")
        b4.set_yscale("log")
        _leyenda(b4, loc="lower left")
    b4.set_xlabel("contratos", color=C["tinta2"], fontsize=9)
    # 5 — clusters contra el azar
    p = aud.perm
    _estilo(b5, f"¿Las ≥ {CLASES[cfg.cluster_clase_min]} se agrupan más que la actividad? (permutación)")
    if len(p.get("_azar", [])):
        b5.hist(p["_azar"], bins=25, color=C["neutro"], edgecolor=C["fondo"], linewidth=1, label="azar (misma actividad)")
        b5.axvline(p["en_cluster"], color=C["s7"], linewidth=2, label=f"real: {p['en_cluster']:,}")
        txt = f"×{p['razon']:.2f} · p = {p['p']:.3f}"
        if np.isfinite(p["pureza"]):
            txt += f"\npureza {p['pureza']:.2f} vs {p['pureza_azar']:.2f} barajando lados · p = {p['p_dir']:.3f}"
        b5.text(0.02, 0.80, txt, transform=b5.transAxes, ha="left", va="top", fontsize=8.5, color=C["tinta"],
                bbox=dict(boxstyle="round,pad=0.3", facecolor=C["fondo"], edgecolor="none", alpha=0.9))
        _leyenda(b5, loc="upper left")
    b5.set_xlabel(f"huellas ≥ {CLASES[cfg.cluster_clase_min]} dentro de clusters", color=C["tinta2"], fontsize=9)
    # 6 — por hora del día y tipo
    _estilo(b6, "Huellas grandes por hora del día (CT) y tipo")
    if len(G):
        hora = a_indice(G["t_ini"].to_numpy()).tz_convert(cfg.tz_mercado).hour
        abajo = np.zeros(24)
        for j in range(4):
            cnt = np.bincount(hora[G["tipo"].to_numpy() == j], minlength=24)
            b6.bar(np.arange(24), cnt, bottom=abajo, color=COLOR_TIPO[j], width=0.8, label=TIPOS[j],
                   edgecolor=C["fondo"], linewidth=0.8)
            abajo += cnt
        r0 = segundo_de_hora(cfg.rth_ct[0]) / 3600 - DESFASE_H
        r1 = segundo_de_hora(cfg.rth_ct[1]) / 3600 - DESFASE_H
        b6.axvspan(r0 % 24 - 0.5, r1 % 24 - 0.5, color=C["neutro"], alpha=0.35, linewidth=0, zorder=0)
        b6.set_xticks(range(0, 24, 3))
        b6.set_ylim(0, max(1, abajo.max()) * 1.35)
        b6.yaxis.set_major_locator(MaxNLocator(integer=True))
        _leyenda(b6, ncol=2)
    b6.set_xlabel("hora de Chicago (gris = horario regular)", color=C["tinta2"], fontsize=9)
    # 7 — rastreo
    _estilo(b7, f"Rastreo de IDs: triple barrera a {cfg.seguimiento_s // 60} min sobre el VWAP de la huella")
    Tr = aud.rastreo[aud.rastreo["n"] > 0]
    filas = [g for g in ["normales (base)", "GRANDE", "MEGA", "BALLENA"] + list(TIPOS) if g in set(Tr["grupo"])]
    Tr = Tr.set_index("grupo").loc[filas]
    yy = np.arange(len(Tr))[::-1]
    izq = np.zeros(len(Tr))
    for col, e in (("sostenido", 1), ("neutro", 0), ("roto", -1)):
        vals = Tr[col].to_numpy(dtype=float)
        b7.barh(yy, vals, left=izq, color=COLOR_ESTADO[e], height=0.62, label=ESTADOS[e],
                edgecolor=C["fondo"], linewidth=1)
        izq += np.nan_to_num(vals)
    b7.set_yticks(yy)
    b7.set_yticklabels([f"{g} (n={int(n_):,})" for g, n_ in zip(filas, Tr["n"])], fontsize=8)
    b7.set_xlim(0, 1)
    b7.axvline(Tr["sostenido"].iloc[0] if len(Tr) else 0.5, color=C["tinta"], linestyle=":", linewidth=1)
    _leyenda(b7, loc="lower right", ncol=3)
    # 8 — tu script contra el módulo
    _estilo(b8, "Tu script contra el módulo, en los mismos registros")
    tu, lado = res.tu, aud.lado
    etq8, val8, col8 = [], [], []
    if lado["n"]:
        etq8 += ["compras ejecutadas en el ask\n(módulo: side B = compra)", "'compras' ejecutadas en el ask\n(tu script: side A = compra)"]
        val8 += [lado["consistente"], lado["tuyo"]]
        col8 += [C["s7"], C["s4"]]
    if tu.get("disponible"):
        h_tu = cfg.h_principal_s // 60 if cfg.h_principal_s // 60 in TU_HORIZONTES_MIN else 5
        etq8 += [f"retornos a {h_tu} min que tu script\nrellena con 0.0"]
        val8 += [float(np.mean(tu["ret"][h_tu] == 0.0))]
        col8 += [C["s4"]]
        if "big_mezclados" in tu:
            etq8 += ["tus big trades que suman\nórdenes agresivas distintas"]
            val8 += [tu["big_mezclados"]]
            col8 += [C["s4"]]
    if val8:
        yy = np.arange(len(val8))[::-1] * 1.6
        b8.barh(yy, val8, color=col8, height=0.55)
        for y_, v_, e_ in zip(yy, val8, etq8):
            b8.annotate(f"{v_:.1%}", xy=(v_, y_), xytext=(4, -3), textcoords="offset points", fontsize=8.5,
                        color=C["tinta"])
            b8.text(0.0, y_ + 0.36, e_.replace("\n", " "), fontsize=7.8, color=C["tinta2"], va="bottom")
        b8.set_yticks([])
        b8.set_xlim(0, 1.15)
        b8.set_ylim(-0.6, yy.max() + 1.1)
    # 9 — cordura
    b9.set_facecolor(C["fondo"])
    b9.axis("off")
    b9.set_title("Chequeo de cordura", color=C["tinta"], fontsize=10, loc="left", pad=8)
    yy = 0.98
    for ok_, txt in aud.cordura:
        lineas = _tw.wrap(txt, 64)
        b9.text(0.0, yy, "✓" if ok_ else "⚠", color=C["s6"] if ok_ else C["s8"], fontsize=10.5,
                transform=b9.transAxes, va="top")
        b9.text(0.05, yy, "\n".join(lineas), color=C["tinta"], fontsize=7.8, transform=b9.transAxes, va="top")
        yy -= 0.058 * len(lineas) + 0.022
    fig.text(0.008, 0.012, f"{IDENTIFICADOR} · IC con error estándar agrupado por sesión (t con G − 1 gl) · "
             "deriva = desde el primer libro después de la huella", color=C["tenue"], fontsize=7.5)
    fig.savefig(ruta, dpi=110, facecolor=C["fondo"], bbox_inches="tight")
    return fig


def _hora_corta(t_ns: int, cfg: Config) -> str:
    t = pd.Timestamp(int(t_ns), tz="UTC")
    return f"{t.tz_convert(cfg.tz_mercado):%m-%d %H:%M:%S} · {t.tz_convert(cfg.tz_local):%H:%M}"


def _tabla(ax, filas, cab, colores, anchos, alto_fila: float) -> None:
    anchos = np.asarray(anchos, float)
    tb = ax.table(cellText=filas, colLabels=cab, cellColours=colores, cellLoc="center",
                  colWidths=list(anchos / anchos.sum()), bbox=[0, 1 - alto_fila * (len(filas) + 1), 1, alto_fila * (len(filas) + 1)])
    tb.auto_set_font_size(False)
    tb.set_fontsize(7.6)
    for (r, _), cell in tb.get_celld().items():
        cell.set_edgecolor(C["grid"])
        if r == 0:
            cell.set_facecolor(C["neutro"])
            cell.set_text_props(color=C["tinta"], weight="bold")


def tablero_ids(res: Resultado, plt, ruta: Path, n: int = 32):
    cfg, G, Cl = res.cfg, res.G, res.C
    fig = plt.figure(figsize=(19, 14))
    fig.patch.set_facecolor(C["fondo"])
    gs = fig.add_gridspec(2, 1, height_ratios=[2.5, 1.0], hspace=0.06, bottom=0.04, top=0.95)
    t1, t2 = fig.add_subplot(gs[0]), fig.add_subplot(gs[1])
    fig.suptitle(f"Rastreador de ID · últimos {min(n, len(G))} IDs y clusters · {cfg.symbol}", x=0.01, ha="left",
                 color=C["tinta"], fontsize=12.5)
    h = cfg.h_principal_s
    for ax in (t1, t2):
        ax.set_facecolor(C["fondo"])
        ax.axis("off")
    if len(G):
        S = G.tail(n)
        cab = ["ID", "hora CT · CDMX", "lado", "contratos", "clase", "percentil", "tipo", "eventos", "niveles",
               "oculta", "precio", "imp. 1 s", f"deriva {_etq_h(h)}", "estado", "MFE / MAE", "cluster"]
        filas, colores = [], []
        for _, g in S.iloc[::-1].iterrows():
            est = int(g["estado"]) if np.isfinite(g["estado"]) else None
            filas.append([g["id"], _hora_corta(g["t_ini"], cfg), "COMPRA" if g["lado"] > 0 else "VENTA", f"{int(g['vol']):,}",
                          CLASES[int(g["clase"])], f"{g['pct']:.4f}", TIPOS[int(g["tipo"])], f"{int(g['n_eventos'])}",
                          f"{int(g['span'])}", f"{int(g['oculta'])}", _precio(g["vwap"], cfg),
                          _fmt(g["imp_1"] + 0.0, 1, 1).strip(), _fmt(g[f"der_{h}"] + 0.0, 1, 1).strip(),
                          ESTADOS.get(est, "—") if est is not None else "—",
                          (f"{int(round(g['mfe']))} / {int(round(g['mae']))}" if np.isfinite(g["mfe"]) else "—"), g["cluster"] or "—"])
            fila_c = [C["fondo"]] * len(cab)
            fila_c[2] = "#dbe8f8" if g["lado"] > 0 else "#fadcdc"
            if est is not None:
                fila_c[13] = {1: "#d6efd6", 0: C["fondo"], -1: "#fadcdc"}[est]
            colores.append(fila_c)
        _tabla(t1, filas, cab, colores, [1.25, 1.75, 0.8, 0.8, 0.8, 0.8, 1.1, 0.7, 0.7, 0.7, 0.9, 0.7, 0.9, 1.0, 0.9, 1.2],
               alto_fila=1 / 34)
    else:
        t1.text(0.5, 0.5, "Sin huellas grandes en la ventana", ha="center", color=C["tinta2"])
    if len(Cl):
        S = Cl.sort_values("t_ini").tail(12).iloc[::-1]
        cab = ["cluster", "inicio CT · CDMX", "duración", "grandes", "compra", "venta", "neto", "pureza", "dirección",
               "VWAP", "rango", "primeros IDs"]
        filas, colores = [], []
        for _, c in S.iterrows():
            d = int(c["direccion"])
            ids_ = c["ids"].split()
            filas.append([c["cluster"], _hora_corta(c["t_ini"], cfg), f"{c['dur_s']:.0f} s", f"{int(c['n'])}", f"{int(c['compra']):,}",
                          f"{int(c['venta']):,}", f"{int(c['neto']):+,}", f"{c['pureza']:.2f}",
                          {1: "COMPRADOR", -1: "VENDEDOR", 0: "DISPUTA"}[d], _precio(c["vwap"], cfg),
                          f"{_precio(c['px_min'], cfg)} – {_precio(c['px_max'], cfg)}",
                          " ".join(x for x in ids_[:3] if x != "…") + (f"  (+{int(c['n']) - 3})" if c["n"] > 3 else "")])
            fila_c = [C["fondo"]] * len(cab)
            fila_c[8] = {1: "#dbe8f8", -1: "#fadcdc", 0: C["fondo"]}[d]
            colores.append(fila_c)
        _tabla(t2, filas, cab, colores, [1.2, 1.7, 0.7, 0.6, 0.7, 0.7, 0.7, 0.6, 0.9, 0.8, 1.4, 3.0], alto_fila=1 / 14)
    fig.text(0.008, 0.008, f"{IDENTIFICADOR} · ID = raíz + fecha de la sesión + número · imp./deriva en ticks a favor "
             "del agresor · oculta = contratos ejecutados más allá de lo visible", color=C["tenue"], fontsize=7.5)
    fig.savefig(ruta, dpi=110, facecolor=C["fondo"], bbox_inches="tight")
    return fig


def tableros(res: Resultado, mostrar: bool = True) -> tuple[list[Path], object, bool]:
    plt, ventana = _preparar_grafico(mostrar)
    if plt is None:
        return [], None, False
    carpeta = _ruta(res.cfg.salida_dir)
    carpeta.mkdir(parents=True, exist_ok=True)
    rutas = []
    for nombre_, fn in (("rastreador", tablero_rastreador), ("auditoria", tablero_auditoria), ("ids", tablero_ids)):
        ruta = carpeta / f"rastreador_{nombre_}_{raiz(res.cfg.symbol)}.png"
        fig = fn(res, plt, ruta)
        rutas.append(ruta)
        print(f"🖼  {ruta}")
        if not ventana:
            plt.close(fig)
    return rutas, plt, ventana


# =============================================================================
# 11. TELEGRAM — el token y el chat, igual que la key: FUERA del código
# =============================================================================
TELEGRAM_API = "https://api.telegram.org"
_RE_TOKEN_TG = re.compile(r"^\d{5,12}:[A-Za-z0-9_-]{30,}$")
_RE_CHAT_TG = re.compile(r"^(-?\d{3,20}|@[A-Za-z0-9_]{5,})$")
AYUDA_TELEGRAM = (
    "  • El token del bot y el chat NO van en el código. Se leen de dos variables de entorno:\n"
    "        TELEGRAM_BOT_TOKEN   te lo da @BotFather al crear el bot (/newbot)\n"
    "        TELEGRAM_CHAT_ID     mándale un mensaje a tu bot y córrelo con --telegram-buscar-chat\n"
    '  • Guárdalas una vez en PowerShell:  setx TELEGRAM_BOT_TOKEN "123456789:AA..."\n'
    '                                      setx TELEGRAM_CHAT_ID "123456789"\n'
    "    y cierra y abre VS Code."
)


def _sin_token(texto: str, token: str) -> str:
    return texto.replace(token, _mascara(token)) if token else texto


def credenciales_telegram(preguntar: bool = True, con_chat: bool = True) -> tuple[str, str] | None:
    token = _limpiar_key(os.environ.get("TELEGRAM_BOT_TOKEN"))
    chat = _limpiar_key(os.environ.get("TELEGRAM_CHAT_ID"))
    if preguntar and _interactivo():
        if not token:
            token = _limpiar_key(_leer_secreto("Pega el token de tu bot de Telegram: "))
        if con_chat and not chat:
            try:
                chat = _limpiar_key(input("Chat ID de Telegram: "))
            except EOFError:
                chat = ""
    if not token or not _RE_TOKEN_TG.match(token):
        print(f"⚠ Telegram: falta TELEGRAM_BOT_TOKEN o no tiene forma de token ({_mascara(token)}).\n" + AYUDA_TELEGRAM)
        return None
    if con_chat and (not chat or not _RE_CHAT_TG.match(chat)):
        print("⚠ Telegram: falta TELEGRAM_CHAT_ID o no es un número de chat válido.\n" + AYUDA_TELEGRAM)
        return None
    return token, chat


def llamar_telegram(token: str, metodo: str, campos: dict | None = None,
                    archivo: tuple[str, Path] | None = None, timeout: float = 60.0,
                    intentos: int = 3) -> dict:
    """POST a la Bot API con la librería estándar (respeta HTTPS_PROXY). Nunca imprime el token."""
    import urllib.error
    import urllib.parse
    import urllib.request
    url = f"{TELEGRAM_API}/bot{token}/{metodo}"
    campos = {k: str(v) for k, v in (campos or {}).items()}
    if archivo is not None:
        nombre_campo, ruta = archivo
        frontera = uuid.uuid4().hex
        cuerpo = bytearray()
        for k, v in campos.items():
            cuerpo += (f"--{frontera}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n"
                       f"{v}\r\n").encode("utf-8")
        cuerpo += (f"--{frontera}\r\nContent-Disposition: form-data; name=\"{nombre_campo}\"; "
                   f"filename=\"{Path(ruta).name}\"\r\nContent-Type: image/png\r\n\r\n").encode("utf-8")
        cuerpo += Path(ruta).read_bytes() + f"\r\n--{frontera}--\r\n".encode("utf-8")
        datos, cabeceras = bytes(cuerpo), {"Content-Type": f"multipart/form-data; boundary={frontera}"}
    else:
        datos = urllib.parse.urlencode(campos).encode("utf-8")
        cabeceras = {"Content-Type": "application/x-www-form-urlencoded"}
    for intento in range(intentos):
        req = urllib.request.Request(url, data=datos, headers=cabeceras, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as ex:
            try:
                err = json.loads(ex.read().decode("utf-8"))
            except Exception:
                err = {"description": f"HTTP {ex.code}"}
            if ex.code == 429 and intento + 1 < intentos:
                time.sleep(min(30, int(err.get("parameters", {}).get("retry_after", 2))))
                continue
            if ex.code >= 500 and intento + 1 < intentos:
                time.sleep(2 ** (intento + 1))
                continue
            err.update({"ok": False, "http": ex.code,
                        "description": _sin_token(str(err.get("description", "")), token)})
            return err
        except (urllib.error.URLError, TimeoutError, OSError) as ex:
            if intento + 1 < intentos:
                time.sleep(2 ** (intento + 1))
                continue
            return {"ok": False, "description": _sin_token(f"{type(ex).__name__}: {ex}", token)}
    return {"ok": False, "description": "sin respuesta"}


def hay_alerta(res: Resultado) -> list[str]:
    """
    Huellas ≥ `alerta_min` (MEGA por omisión) en los últimos `alerta_ventana_min` minutos de los
    datos, y clusters direccionales que siguen vivos en ese tramo.
    """
    cfg, G, Cl = res.cfg, res.G, res.C
    if not len(G):
        return []
    t_fin = int(res.E["t"].max())
    desde = t_fin - cfg.alerta_ventana_min * 60 * NS
    avisos = []
    for _, g in G[(G["t_ini"] >= desde) & (G["clase"] >= cfg.alerta_min)].iterrows():
        avisos.append(f"{g['id']} {CLASES[int(g['clase'])]} {'COMPRA' if g['lado'] > 0 else 'VENTA'} "
                      f"{int(g['vol']):,} contratos · {TIPOS[int(g['tipo'])]} · {_precio(g['vwap'], cfg)}")
    if len(Cl):
        for _, c in Cl[(Cl["t_fin"] >= desde) & (Cl["direccion"] != 0)].iterrows():
            avisos.append(f"{c['cluster']} {'COMPRADOR' if c['direccion'] > 0 else 'VENDEDOR'} · {int(c['n'])} grandes · "
                          f"neto {int(c['neto']):+,} · pureza {c['pureza']:.2f}")
    return avisos


def mensaje_telegram(res: Resultado, limite: int = 4096) -> str:
    esc = html.escape
    cfg, G, H = res.cfg, res.G, res.H
    ult = int(H.loc[H["ventana"], "sesion"].max())
    g = G[G["sesion"] == ult] if len(G) else G
    lin = [f"<b>{esc(IDENTIFICADOR)}</b> · {esc(cfg.symbol)} · sesión {fecha_de_dia(ult):%Y-%m-%d}",
           esc(_hora(int(res.E["t"].max()), cfg, False))]
    for a in hay_alerta(res)[:8]:
        lin.append(f"⚠️ {esc(a)}")
    if len(g):
        compra = int(g.loc[g["lado"] > 0, "vol"].sum())
        venta = int(g.loc[g["lado"] < 0, "vol"].sum())
        lin += ["", f"Grandes: {len(g):,} · MEGA {int((g['clase'] == 2).sum())} · BALLENA {int((g['clase'] == 3).sum())}",
                f"Compra {compra:,} · venta {venta:,} · <b>neto {compra - venta:+,}</b> contratos",
                "Tipos: " + " · ".join(f"{TIPOS[j]} {int((g['tipo'] == j).sum())}" for j in range(4))]
        top = g[g["clase"] >= 2].tail(5)
        if len(top):
            lin.append("")
            for _, x in top.iterrows():
                est = ESTADOS.get(int(x["estado"]), "—") if np.isfinite(x["estado"]) else "—"
                lin.append(esc(f"{x['id']} {pd.Timestamp(int(x['t_ini']), tz='UTC').tz_convert(cfg.tz_local):%H:%M} "
                               f"{'▲' if x['lado'] > 0 else '▼'} {int(x['vol'])} {TIPOS[int(x['tipo'])]} "
                               f"{_precio(x['vwap'], cfg)} · {est}"))
    malos = [t for ok, t in res.aud.cordura if not ok]
    lin.append(f"\nCordura: {len(res.aud.cordura) - len(malos)}/{len(res.aud.cordura)} ✓")
    for t in malos[:3]:
        lin.append(f"⚠ {esc(t)}")
    texto = "\n".join(lin)
    if len(texto) > limite:
        texto = texto[:limite - 20].rsplit("\n", 1)[0] + "\n…"
    return texto


def enviar_texto_telegram(texto: str) -> bool:
    cred = credenciales_telegram(preguntar=False)
    if cred is None:
        return False
    r = llamar_telegram(cred[0], "sendMessage", {"chat_id": cred[1], "text": texto, "parse_mode": "HTML",
                                                 "disable_web_page_preview": "true"})
    if not r.get("ok"):
        print(f"⚠ Telegram: {r.get('description', r)}")
    return bool(r.get("ok"))


def enviar_telegram(res: Resultado, rutas: list[Path], documentos: bool = False) -> bool:
    cred = credenciales_telegram()
    if cred is None:
        return False
    token, chat = cred
    r = llamar_telegram(token, "sendMessage", {"chat_id": chat, "text": mensaje_telegram(res),
                                               "parse_mode": "HTML", "disable_web_page_preview": "true"})
    if not r.get("ok"):
        print(f"❌ Telegram rechazó el mensaje: {r.get('description', r)}")
        if r.get("http") == 401:
            print("   El token no es válido (401). Revísalo con @BotFather.")
        elif r.get("http") in (400, 403):
            print("   ¿El chat es correcto y ya le escribiste /start a tu bot?")
        return False
    enviados = 1
    for ruta in rutas:
        metodo, campo = ("sendDocument", "document") if documentos else ("sendPhoto", "photo")
        r = llamar_telegram(token, metodo, {"chat_id": chat, "caption": ruta.stem[:1000]}, archivo=(campo, ruta))
        if r.get("ok"):
            enviados += 1
        else:
            print(f"⚠ No se pudo enviar {ruta.name}: {r.get('description', r)}")
    print(f"📨 Telegram: {enviados} envío(s) al chat {chat[:3]}…")
    return True


def buscar_chat_telegram() -> int:
    cred = credenciales_telegram(con_chat=False)
    if cred is None:
        return 1
    token, _ = cred
    r = llamar_telegram(token, "getUpdates", {"limit": 50})
    if not r.get("ok"):
        print(f"❌ {r.get('description', r)}")
        return 1
    chats = {}
    for u in r.get("result", []):
        msg = u.get("message") or u.get("channel_post") or u.get("my_chat_member") or {}
        ch = msg.get("chat") or {}
        if "id" in ch:
            chats[ch["id"]] = ch.get("title") or ch.get("username") or ch.get("first_name") or ""
    if not chats:
        print("No hay mensajes recientes. Escríbele /start a tu bot y vuelve a correr esto.")
        return 1
    for cid, nm in chats.items():
        print(f"  chat_id = {cid}   {nm}")
    print('\nGuárdalo:  setx TELEGRAM_CHAT_ID "<el número>"   y reabre VS Code.')
    return 0


# =============================================================================
# 12. GUARDAR Y LIVE
# =============================================================================
def guardar(res: Resultado) -> Path:
    cfg, G = res.cfg, res.G
    carpeta = _ruta(cfg.salida_dir)
    carpeta.mkdir(parents=True, exist_ok=True)
    t0, t1 = ventana_utc(cfg)
    suf = _nombre_seguro(raiz(cfg.symbol), f"{t0:%Y%m%d}", f"{t1:%Y%m%d}")
    tk = tick(cfg.symbol)
    if len(G):
        out = G.drop(columns=[c for c in ("qpx", "i_ini", "i_fin", "cluster_k", "ventana") if c in G]).copy()
        out.insert(0, "hora_cdmx", a_indice(G["t_ini"]).tz_convert(cfg.tz_local).strftime("%Y-%m-%d %H:%M:%S.%f").str[:-3])
        out.insert(0, "hora_ct", a_indice(G["t_ini"]).tz_convert(cfg.tz_mercado).strftime("%Y-%m-%d %H:%M:%S.%f").str[:-3])
        out.insert(0, "id", out.pop("id"))
        out.insert(3, "lado_txt", np.where(G["lado"] > 0, "COMPRA", "VENTA"))
        out.insert(4, "clase_txt", [CLASES[int(c)] for c in G["clase"]])
        out.insert(5, "tipo_txt", [TIPOS[int(t)] for t in G["tipo"]])
        out["estado_txt"] = [ESTADOS.get(int(e), "") if np.isfinite(e) else "" for e in G["estado"]]
        for c in ("vwap", "px_min", "px_max", "px_ini", "px_fin", "bid0", "ask0", "mid0"):
            out[f"precio_{c}"] = np.where(G[c].to_numpy(dtype=float) >= 0, G[c].to_numpy(dtype=float) * tk, np.nan)
        out["id_cme"] = [f"{int(t)}:{int(q)}" for t, q in zip(G["t_ini"], G["seq0"])]
        out.to_csv(carpeta / f"rastreador_ids_{suf}.csv", index=False)
    if len(res.C):
        Cc = res.C.copy()
        Cc.insert(1, "inicio_cdmx", a_indice(Cc["t_ini"]).tz_convert(cfg.tz_local).strftime("%Y-%m-%d %H:%M:%S"))
        Cc["precio_vwap"] = Cc["vwap"] * tk
        Cc.to_csv(carpeta / f"rastreador_clusters_{suf}.csv", index=False)
    res.aud.impacto.to_csv(carpeta / f"rastreador_impacto_{suf}.csv", index=False)
    res.aud.rastreo.to_csv(carpeta / f"rastreador_seguimiento_{suf}.csv", index=False)
    U = res.U.copy()
    U.insert(1, "fecha", [f"{fecha_de_dia(s):%Y-%m-%d}" for s in U["sesion"]])
    U.to_csv(carpeta / f"rastreador_umbrales_{suf}.csv", index=False)
    print(f"💾 IDs, clusters, impacto, seguimiento y umbrales guardados en {carpeta}")
    return carpeta


def ultimo_halt_cme(t: pd.Timestamp, cfg: Config) -> pd.Timestamp:
    """Inicio del último halt diario (16:00 CT, lunes a viernes) ≤ t, en UTC."""
    local = t.tz_convert(cfg.tz_mercado).tz_localize(None)
    cand = local.normalize() + pd.Timedelta(hours=16)
    if cand > local:
        cand -= pd.Timedelta(days=1)
    while cand.weekday() >= 5:
        cand -= pd.Timedelta(days=1)
    return cand.tz_localize(cfg.tz_mercado).tz_convert("UTC")


class ClasificadorLive:
    """
    Clasifica en vivo cada huella que cierra el motor incremental, con los MISMOS umbrales causales:
    la referencia de la sesión en curso son las `ventana_sesiones` sesiones anteriores (históricas
    y, al cambiar de sesión, también las vividas en Live). Detecta clusters al vuelo y avisa.
    """

    def __init__(self, cfg: Config, H_hist: pd.DataFrame, avisar=None):
        self.cfg = cfg
        self.avisar = avisar or (lambda texto: None)
        self.por_ses: dict[tuple[int, int], list] = {}
        if len(H_hist):
            fr = H_hist["rth"].to_numpy().astype(int) if cfg.por_franja else np.zeros(len(H_hist), int)
            for (s, f), v in pd.Series(H_hist["vol"].to_numpy()).groupby([H_hist["sesion"].to_numpy(), fr]):
                self.por_ses[(int(s), int(f))] = list(v.to_numpy())
        self.umbrales: dict[tuple[int, int], tuple] = {}
        self.cuenta: dict[int, int] = {}
        self.grandes: deque = deque(maxlen=500)
        self.cluster_vivo: list[dict] = []
        self.n_clusters: dict[int, int] = {}
        self.emitidas = 0

    def _umbral(self, s: int, f: int) -> tuple:
        if (s, f) not in self.umbrales:
            previas = sorted({k[0] for k in self.por_ses if k[0] < s})[-self.cfg.ventana_sesiones:]
            ref = np.sort(np.concatenate([np.asarray(self.por_ses.get((p, f), []), float) for p in previas])) \
                if previas else np.zeros(0)
            if len(ref) >= self.cfg.min_ref:
                q = tuple(max(umbral_discreto(ref, p), float(self.cfg.piso_contratos))
                          for p in (self.cfg.p_grande, self.cfg.p_mega, self.cfg.p_ballena))
            else:
                q = (np.nan, np.nan, np.nan)
            self.umbrales[(s, f)] = q
        return self.umbrales[(s, f)]

    def huella(self, h: dict) -> dict | None:
        cfg = self.cfg
        s, f = int(h["sesion"]), int(h["rth"]) if cfg.por_franja else 0
        self.por_ses.setdefault((s, f), []).append(h["vol"])
        q = self._umbral(s, f)
        if not np.isfinite(q[0]):
            return None
        clase = int(h["vol"] >= q[0]) + int(h["vol"] >= q[1]) + int(h["vol"] >= q[2])
        if clase < 1:
            return None
        h = dict(h)
        tip = tipificar(pd.DataFrame([h]), cfg)[0]
        self.cuenta[s] = self.cuenta.get(s, 0) + 1
        h.update(clase=clase, tipo=int(tip), id=f"{raiz(cfg.symbol)}{fecha_de_dia(s):%m%d}-{self.cuenta[s]:03d}")
        self.emitidas += 1
        # cluster al vuelo
        if self.cluster_vivo and (h["t_ini"] - self.cluster_vivo[-1]["t_ini"] > cfg.cluster_gap_s * NS
                                  or self.cluster_vivo[-1]["sesion"] != s):
            self.cluster_vivo = []
        self.cluster_vivo.append(h)
        hora = pd.Timestamp(int(h["t_ini"]), tz="UTC").tz_convert(cfg.tz_local)
        texto = (f"{h['id']} {hora:%H:%M:%S} {'COMPRA' if h['lado'] > 0 else 'VENTA'} {int(h['vol']):,} "
                 f"({CLASES[clase]}) · {TIPOS[int(tip)]} · {int(h['span'])} nivel(es) · {_precio(h['vwap'], cfg)}")
        print(f"[LIVE] {texto}")
        if clase >= cfg.alerta_min:
            self.avisar(f"⚠️ <b>{html.escape(cfg.symbol)}</b> · {html.escape(texto)}")
        n = len(self.cluster_vivo)
        if n >= max(3, cfg.cluster_min):
            neto = sum(x["lado"] * x["vol"] for x in self.cluster_vivo)
            tot = sum(x["vol"] for x in self.cluster_vivo)
            pureza = abs(neto) / tot
            if pureza >= cfg.pureza_min and n == max(3, cfg.cluster_min):
                d = "COMPRADOR" if neto > 0 else "VENDEDOR"
                msg = f"cluster {d} en curso · {n} grandes · neto {neto:+,} · pureza {pureza:.2f}"
                print(f"⚠ [LIVE] {msg}")
                self.avisar(f"⚠️ <b>{html.escape(cfg.symbol)}</b> · {html.escape(msg)}")
        return h


def correr_live(cfg: Config, cliente_hist=None, cliente_live=None, ahora: pd.Timestamp | None = None,
                max_registros: int | None = None, historia=None) -> ClasificadorLive:
    """
    Calienta con el histórico (las sesiones que dan los umbrales) hasta el último halt diario y
    sigue con Databento Live (tbbo), registro por registro, con el motor incremental. Cada huella
    grande sale con su ID; con --telegram-live las ≥ alerta_min y los clusters llegan a tu
    teléfono. (Los clientes, la historia y `ahora` son inyectables para probarlo sin red.)
    """
    ahora = ahora if ahora is not None else pd.Timestamp.now(tz="UTC")
    corte = ultimo_halt_cme(ahora, cfg)
    if historia is None:
        cliente_hist = cliente_hist or conectar()
        rango = cliente_hist.metadata.get_dataset_range(dataset=cfg.dataset)
        disponible = pd.Timestamp(rango.get("end") or rango.get("end_date"))
        disponible = disponible.tz_localize("UTC") if disponible.tzinfo is None else disponible.tz_convert("UTC")
        if corte > disponible:
            corte = ultimo_halt_cme(disponible, cfg)
        inicio = corte - pd.offsets.BDay(cfg.dias_historial_live) - pd.Timedelta(hours=1)
        historia = obtener_datos(cfg, cliente_hist, inicio=inicio, fin=corte)
    inicio_live = max(corte, ahora - pd.Timedelta(hours=23))
    if inicio_live > corte:
        print(f"⚠ Entre {corte} y {inicio_live} (UTC) no hay replay: si hubo operaciones, faltarán.")
    E0, motor = correr_motor(historia, cfg, verbose=False, guardar_crudo=False)
    E = preparar_eventos(E0, cfg)
    H, _ = agrupar_huellas(E, cfg)
    print(f"🔧 Historia: {len(H):,} huellas de {H['sesion'].nunique() if len(H) else 0} sesiones para los umbrales.")
    tg = cfg.telegram_live and credenciales_telegram(preguntar=False) is not None
    clas = ClasificadorLive(cfg, H, avisar=enviar_texto_telegram if tg else None)
    inc = MotorIncremental(cfg, tick_ns(cfg.symbol), al_cerrar_huella=clas.huella, guardar=False)
    print(f"✅ Conectando a Live ({cfg.esquema}) desde {inicio_live} UTC…")
    if cliente_live is None:
        if db is None:
            sys.exit("Falta el paquete databento:  pip install databento")
        _exigir_api_key()
        cliente_live = db.Live(reconnect_policy="reconnect")
    cliente_live.subscribe(dataset=cfg.dataset, schema=cfg.esquema, symbols=cfg.symbol, stype_in=cfg.stype_in,
                           start=inicio_live)
    corte_ns = corte.value
    vistos = 0
    try:
        for rec in cliente_live:
            nombre_ = type(rec).__name__
            if nombre_ in ("MBP1Msg", "TradeMsg", "MBP10Msg"):
                if rec.ts_event >= corte_ns:
                    inc.registro_dbn(rec)
                vistos += 1
                if max_registros and vistos >= max_registros:
                    break
            elif nombre_ == "ErrorMsg":
                print(f"⚠ Databento: {rec.err}")
            elif nombre_ == "SystemMsg" and not rec.is_heartbeat():
                print(f"ℹ {rec.msg}")
    except KeyboardInterrupt:
        print("\nCerrando…")
    finally:
        inc.cerrar()
        try:
            cliente_live.stop()
        except Exception:
            pass
    return clas


# =============================================================================
# 13. LÍNEA DE COMANDOS
# =============================================================================
def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Rastreador de ID AC v1 — big trades institucionales con TBBO")
    p.add_argument("--pruebas", action="store_true", help="pruebas internas (sin red ni datos)")
    p.add_argument("--simulacion", action="store_true", help="mercado simulado con verdad conocida (sin red)")
    p.add_argument("--sin-metaordenes", action="store_true", help="simulación sin órdenes institucionales")
    p.add_argument("--sin-icebergs", action="store_true", help="simulación sin icebergs")
    p.add_argument("--sin-defectos", action="store_true", help="simulación sin registros defectuosos")
    p.add_argument("--archivo", default=None, help="analiza un .dbn / .dbn.zst local en vez de descargar")
    p.add_argument("--live", action="store_true", help="en vivo con Databento Live")
    p.add_argument("--sin-tablero", "--sin-grafica", action="store_true", dest="sin_tablero")
    p.add_argument("--sin-ventana", action="store_true")
    p.add_argument("--sin-cache", action="store_true")
    p.add_argument("--sin-paridad", action="store_true", help="no correr el chequeo del motor incremental")
    d = p.add_argument_group("datos")
    d.add_argument("--simbolo", default=None)
    d.add_argument("--start", "--inicio", default=None, dest="start")
    d.add_argument("--end", "--fin", default=None, dest="end")
    d.add_argument("--tz-entrada", default=None, help="zona de --start/--end (America/Mexico_City)")
    d.add_argument("--calentamiento", type=int, default=None, dest="dias_calentamiento",
                   help="sesiones previas que dan los umbrales (3)")
    d.add_argument("--esquema", default=None, choices=("tbbo", "trades", "mbp-1", "mbp-10"))
    d.add_argument("--costo-max", type=float, default=None, dest="costo_max_usd")
    d.add_argument("--bloque", type=int, default=None, help="registros por bloque (2 000 000)")
    d.add_argument("--salida", default=None, dest="salida_dir")
    g = p.add_argument_group("1 · agrupación")
    g.add_argument("--rafaga-ms", type=float, default=None, dest="rafaga_ms", help="hueco máximo de una huella (100)")
    g.add_argument("--rafaga-max-ms", type=float, default=None, dest="rafaga_max_ms", help="duración máxima (1000)")
    m = p.add_argument_group("2 · magnitud")
    m.add_argument("--p-grande", type=float, default=None)
    m.add_argument("--p-mega", type=float, default=None)
    m.add_argument("--p-ballena", type=float, default=None)
    m.add_argument("--ventana-sesiones", type=int, default=None)
    m.add_argument("--min-ref", type=int, default=None)
    m.add_argument("--sin-franja", action="store_true", help="un solo umbral para el día y la noche")
    m.add_argument("--piso", type=int, default=None, dest="piso_contratos", help="contratos mínimos para GRANDE")
    t = p.add_argument_group("3 · tipos")
    t.add_argument("--min-eventos-fragmentada", type=int, default=None)
    t.add_argument("--oculta-min", type=int, default=None)
    c = p.add_argument_group("4 · clusters")
    c.add_argument("--cluster-gap", type=float, default=None, dest="cluster_gap_s")
    c.add_argument("--cluster-min", type=int, default=None)
    c.add_argument("--cluster-clase", type=int, default=None, dest="cluster_clase_min", choices=(1, 2, 3),
                   help="clase mínima para formar clusters: 1 GRANDE · 2 MEGA (omisión) · 3 BALLENA")
    c.add_argument("--pureza", type=float, default=None, dest="pureza_min")
    c.add_argument("--permutaciones", type=int, default=None, dest="n_permutaciones")
    i = p.add_argument_group("5 · impacto y rastreo")
    i.add_argument("--horizontes", default=None, help='segundos, p. ej. "1,10,60,300,900,1800,3600"')
    i.add_argument("--h-principal", type=int, default=None, dest="h_principal_s")
    i.add_argument("--h-raiz", type=int, default=None, dest="h_raiz_s")
    i.add_argument("--seguimiento", type=int, default=None, dest="seguimiento_s", help="segundos (1800)")
    i.add_argument("--barrera-sigma", type=float, default=None)
    a = p.add_argument_group("alertas y Telegram")
    a.add_argument("--alerta-min", type=int, default=None, choices=(1, 2, 3), help="1 GRANDE · 2 MEGA · 3 BALLENA")
    a.add_argument("--alerta-ventana", type=int, default=None, dest="alerta_ventana_min")
    a.add_argument("--telegram", action="store_true")
    a.add_argument("--telegram-solo-alertas", action="store_true")
    a.add_argument("--telegram-documentos", action="store_true")
    a.add_argument("--telegram-buscar-chat", action="store_true")
    a.add_argument("--telegram-live", action="store_true")
    s = p.add_argument_group("simulación")
    s.add_argument("--sesiones-sim", type=int, default=None, dest="sim_sesiones")
    s.add_argument("--eventos-sim", type=int, default=None, dest="sim_eventos")
    s.add_argument("--semilla", type=int, default=None, dest="sim_semilla")
    return p


def config_desde_args(a: argparse.Namespace) -> Config:
    cambios = {}
    for k in ("start", "end", "tz_entrada", "dias_calentamiento", "esquema", "costo_max_usd", "bloque", "salida_dir",
              "rafaga_ms", "rafaga_max_ms", "p_grande", "p_mega", "p_ballena", "ventana_sesiones", "min_ref",
              "piso_contratos", "min_eventos_fragmentada", "oculta_min", "cluster_gap_s", "cluster_min", "cluster_clase_min", "pureza_min",
              "n_permutaciones", "h_principal_s", "h_raiz_s", "seguimiento_s", "barrera_sigma", "alerta_min",
              "alerta_ventana_min", "sim_sesiones", "sim_eventos", "sim_semilla"):
        v = getattr(a, k, None)
        if v is not None:
            cambios[k] = v
    if a.simbolo:
        cambios["symbol"] = simbolo_continuo(a.simbolo)
    if a.horizontes:
        cambios["horizontes_s"] = tuple(int(x) for x in a.horizontes.split(",") if x.strip())
    if a.sin_franja:
        cambios["por_franja"] = False
    if a.sin_cache:
        cambios["usar_cache"] = False
    if a.telegram_live:
        cambios["telegram_live"] = True
    return replace(CFG, **cambios)


def config_de_archivo(cfg: Config, tienda, con_inicio: bool) -> Config:
    """Con --archivo y sin --start: se analiza todo menos las primeras `dias_calentamiento` sesiones."""
    meta = tienda.metadata
    t0 = int(meta.start)
    t1 = int(meta.end) if meta.end else t0 + 30 * DIA_NS
    if con_inicio:
        return cfg
    dia = int(reloj_sesion([t0], cfg.tz_mercado)[0][0])
    fecha = fecha_de_dia(dia) + pd.offsets.BDay(max(cfg.dias_calentamiento, 0))
    ini = pd.Timestamp(apertura_utc(int(fecha.value // DIA_NS), cfg.tz_mercado), tz="UTC")
    return replace(cfg, start=ini.strftime("%Y-%m-%dT%H:%M:%S"),
                   end=pd.Timestamp(t1, tz="UTC").strftime("%Y-%m-%dT%H:%M:%S"), tz_entrada="UTC")


def main(argv: list[str] | None = None) -> int:
    a = construir_parser().parse_args(argv)
    cfg = config_desde_args(a)
    if a.pruebas:
        return pruebas()
    if a.telegram_buscar_chat:
        return buscar_chat_telegram()
    validar(cfg)
    if a.live:
        correr_live(cfg)
        return 0
    print(f"▶ {IDENTIFICADOR} · {cfg.symbol} · {cfg.esquema} · ráfagas de {cfg.rafaga_ms:g} ms · "
          f"p{cfg.p_grande * 100:g}/p{cfg.p_mega * 100:g}/p{cfg.p_ballena * 100:g}")
    verdad, arr = None, None
    if a.simulacion:
        print(f"🎲 {cfg.sim_sesiones} sesiones simuladas (~{cfg.sim_eventos:,} eventos de libro cada una): metaórdenes "
              "institucionales, icebergs, ruido con cola de Pareto, un roll y defectos CONOCIDOS.")
        arr, verdad = simular(cfg, metaordenes=not a.sin_metaordenes, icebergs=not a.sin_icebergs,
                              defectos=not a.sin_defectos)
        cfg = config_simulacion(cfg, verdad)
        tienda = arr
        if db is not None:
            try:
                tienda = db.DBNStore.from_bytes(a_dbn(arr, cfg))
                print("   (convertido a un archivo DBN TBBO de verdad: la misma ruta que tus datos)")
            except Exception as ex:
                print(f"   (sin DBN: {type(ex).__name__}; se usa el arreglo)")
    elif a.archivo:
        if db is None:
            sys.exit("Falta el paquete databento:  pip install databento")
        tienda = db.DBNStore.from_file(a.archivo)
        cfg = config_de_archivo(cfg, tienda, con_inicio=a.start is not None)
    else:
        tienda = obtener_datos(cfg)
    res = analizar(tienda, cfg, verdad=verdad, chequear_paridad=not a.sin_paridad)
    if verdad is not None:
        res.medicion = medir_contra_verdad(res, arr)
    reporte_datos(res)
    reporte_tu_script(res)
    reporte_magnitud(res)
    reporte_tipos(res)
    reporte_clusters(res)
    reporte_impacto(res)
    reporte_rastreo(res)
    reporte_cordura(res)
    reporte_verdad(res)
    rutas, plt_, ventana = ([], None, False)
    if not a.sin_tablero:
        print()
        rutas, plt_, ventana = tableros(res, mostrar=not a.sin_ventana)
    guardar(res)
    if a.telegram or a.telegram_solo_alertas:
        if a.telegram_solo_alertas and not hay_alerta(res):
            print(f"📭 Telegram: sin huellas ≥ {CLASES[cfg.alerta_min]} ni clusters direccionales en los últimos "
                  f"{cfg.alerta_ventana_min} min.")
        else:
            enviar_telegram(res, rutas, documentos=a.telegram_documentos)
    _titulo("CÓMO LEER ESTO")
    print("  1. Un EVENTO es una orden agresiva tal como la casó CME; una HUELLA junta las que un algoritmo")
    print("     disparó del mismo lado en milisegundos. El tamaño se clasifica contra las sesiones ANTERIORES.")
    print("  2. El tipo dice CÓMO entró: BARRIDO (cruzó niveles), ABSORCIÓN (pegó contra liquidez oculta y el")
    print("     nivel aguantó), FRAGMENTADA (partida en pedazos) o BLOQUE (se llevó lo visible).")
    print("  3. IMPACTO incluye el movimiento que la propia huella causó; DERIVA es lo que siguió después:")
    print("     eso es lo único que se podía operar al verla, y hay que restarle el spread.")
    print("  4. Cada ID se rastrea con triple barrera; compáralo siempre contra la línea base de las normales.")
    print("  5. Con pocas sesiones el IC es ancho y casi nada sale significativo: eso es honestidad, no un error.")
    if rutas and not a.sin_ventana:
        print()
        mostrar_tableros(plt_, ventana, rutas)
    return 0


# =============================================================================
# 14. PRUEBAS INTERNAS
# =============================================================================
def pruebas() -> int:
    cfg = CFG
    fallas: list[str] = []
    hecho = 0

    def check(nombre_: str, ok: bool, detalle: str = "") -> None:
        nonlocal hecho
        hecho += 1
        print(f"  {'✓' if ok else '✗'} {nombre_}" + (f"   {detalle}" if detalle else ""))
        if not ok:
            fallas.append(nombre_)

    _titulo("PRUEBAS INTERNAS")
    rng = np.random.default_rng(0)
    cs = replace(cfg, sim_sesiones=5, sim_eventos=24_000, dias_calentamiento=2, min_ref=500, n_permutaciones=100,
                 base_normales=4000)
    arr, ver = simular(cs, semilla=3)
    cs = config_simulacion(cs, ver)
    tk = tick_ns(cs.symbol)

    def eventos(tienda, c=cs):
        return preparar_eventos(correr_motor(tienda, c, verbose=False, guardar_crudo=False)[0], c)

    def iguales(A: pd.DataFrame, B: pd.DataFrame) -> bool:
        if len(A) != len(B) or list(A.columns) != list(B.columns):
            return False
        for c in A.columns:
            a, b = A[c].to_numpy(dtype=float), B[c].to_numpy(dtype=float)
            if not np.array_equal(np.isfinite(a), np.isfinite(b)) or not np.allclose(a[np.isfinite(a)], b[np.isfinite(b)], rtol=0, atol=0):
                return False
        return True

    E1 = eventos(arr)

    # 1 ------------------------------------------ el lado es el del AGRESOR
    r = normalizar(arr[:5000])
    _, signo, _, _, _ = higiene(r, tk, cs)
    lado_ok = bool(np.all(signo[r["lado"] == b"B"] == 1) and np.all(signo[r["lado"] == b"A"] == -1)
                   and np.all(signo[r["lado"] == b"N"] == 0))
    ch = chequeo_lado(E1, np.ones(len(E1), bool))
    check("side B = compra agresiva (en el ask), A = venta (en el bid); con tu lectura sale al revés",
          lado_ok and ch["consistente"] > 0.999 and ch["tuyo"] < 0.001,
          f"módulo {ch['consistente']:.1%} · tu script {ch['tuyo']:.1%}")

    # 2 ------------------------------------------ eventos exactos
    val = (arr["action"] == b"T") & (arr["size"] > 0) & (arr["price"].astype(np.int64) % tk == 0) & np.isin(arr["side"], [b"B", b"A"])
    n_verdad = len(np.unique(arr["ts_event"][val].astype(np.int64) * 2 + (arr["side"][val] == b"B")))
    check("agrupación exacta: un evento por casación (misma hora de CME y mismo agresor), sin perder volumen",
          len(E1) == n_verdad and int(E1["vol"].sum()) == int(arr["size"][val].sum()),
          f"{len(E1):,} eventos · {int(E1['vol'].sum()):,} contratos")

    # 3 ------------------------------------------ bloques
    E_b = eventos(arr, replace(cs, bloque=777))
    check("procesar en bloques de 777 registros = de un jalón (el evento abierto cruza el bloque)", iguales(E1, E_b))

    # 4 ------------------------------------------ DBN de verdad
    if db is not None:
        try:
            tienda = db.DBNStore.from_bytes(a_dbn(arr, cs))
            E_d = eventos(tienda, replace(cs, bloque=5_000))
            check("archivo DBN TBBO real leído por bloques con to_ndarray = los mismos eventos", iguales(E1, E_d))
        except Exception as ex:
            check("archivo DBN TBBO real leído por bloques con to_ndarray = los mismos eventos", False,
                  f"{type(ex).__name__}: {ex}")
    else:
        check("archivo DBN real (databento no instalado: se omite)", True)

    # 5 ------------------------------------------ higiene exacta
    E_l = eventos(arr[ver["limpio"]])
    _, mot = correr_motor(arr, cs, verbose=False, guardar_crudo=False)
    quitados = sum(mot.conteo.values())
    check("higiene: con los registros defectuosos da lo mismo que sin ellos, y los cuenta todos",
          iguales(E1, E_l) and quitados == int((~ver["limpio"]).sum()),
          f"{int((~ver['limpio']).sum()):,} defectuosos inyectados · {quitados:,} descartados")

    # 6 ------------------------------------------ libro dañado: la operación queda, el contexto no
    pos_ev = np.flatnonzero(val)
    t_val = np.maximum.accumulate(arr["ts_event"].astype(np.int64))[val]
    s_val = arr["side"][val]
    ini = np.r_[True, (t_val[1:] != t_val[:-1]) | (s_val[1:] != s_val[:-1])]
    danado_ini = ver["danado"][pos_ev[ini]]
    check("libro dañado (F_MAYBE_BAD_BOOK o cruzado): la operación cuenta pero sin libro de referencia",
          danado_ini.sum() > 0 and not E1["libro0"].to_numpy()[danado_ini].any(),
          f"{int(danado_ini.sum())} eventos con libro dañado")

    # 7 ------------------------------------------ paridad
    par = paridad(arr, cs, maximo=60_000)
    check("motor incremental (Live) = vectorizado, registro por registro", par["iguales"],
          f"{par['huellas']:,} huellas de {par['registros']:,} registros")

    # 8 ------------------------------------------ umbral discreto
    ref = np.sort(np.r_[np.ones(900), np.full(60, 2), np.full(40, 5)])
    u = umbral_discreto(ref, 0.95)
    check("umbral con empates: GRANDE nunca pesa más del 5 % (el cuantil interpolado marcaría 10 %)",
          u == 5 and float(np.quantile(ref, 0.95)) == 2.0, f"umbral {u:.0f} · cuantil interpolado {np.quantile(ref, 0.95):.0f}")

    # 9 ------------------------------------------ causalidad
    H1, _ = agrupar_huellas(E1, cs)
    U1, _, c1 = clasificar_magnitud(H1, cs)
    H2 = H1.copy()
    ult = H2["sesion"].max()
    H2.loc[H2["sesion"] == ult, "vol"] *= 10
    U2, _, c2 = clasificar_magnitud(H2, cs)
    antes = H1["sesion"].to_numpy() < ult
    check("umbrales causales: cambiar la última sesión no toca las anteriores ni sus propios umbrales",
          np.array_equal(c1[antes], c2[antes]) and U1.loc[U1["sesion"] == ult, ["q_grande", "q_mega"]].equals(
              U2.loc[U2["sesion"] == ult, ["q_grande", "q_mega"]]))

    # 10 ----------------------------------------- huellas: hueco, tope, lado y sesión
    ms = NS_MS
    t = np.array([0, 50, 140, 300, 60, 1000, 1090, 1180, 1270, 1360, 1450, 1540, 1630, 1720, 1810, 1900, 1990, 2080, 2170]) * ms
    lado = np.array([1, 1, 1, 1, -1] + [1] * 14)
    o = np.argsort(t, kind="stable")
    hid = asignar_huellas(t[o], lado[o], np.zeros(len(t), int), np.zeros(len(t), int), 100 * ms, 1000 * ms)
    grupos = [sorted(t[o][hid == k] // ms) for k in np.unique(hid)]
    esperado = [[0, 50, 140], [300], [1000, 1090, 1180, 1270, 1360, 1450, 1540, 1630, 1720, 1810, 1900, 1990],
                [2080, 2170], [60]]
    check("huellas: junta el mismo lado a ≤ 100 ms, corta a los 1000 ms y no mezcla lados",
          sorted(grupos) == sorted(esperado), f"{len(grupos)} huellas")

    # 11 ----------------------------------------- tipos y su prioridad
    Ht = pd.DataFrame({"n_eventos": [1, 4, 1, 1, 5, 2], "span": [1, 1, 3, 1, 3, 1], "oculta": [5, 0, 0, 0, 0, 0],
                       "niv_max": [1, 1, 2, 1, 3, 1]})
    tp = tipificar(Ht, cs)
    check("tipos: ABSORCIÓN > FRAGMENTADA > BARRIDO > BLOQUE", list(tp) == [2, 3, 1, 0, 3, 0],
          " ".join(TIPOS[k] for k in tp))

    # 12 ----------------------------------------- clusters por encadenamiento
    tc = np.array([0, 30, 80, 200, 230, 1000]) * NS
    cid = _grupos_cluster(tc, np.zeros(6, int), 60 * NS, 2)
    check("clusters: encadena huecos ≤ 60 s (tu ventana desde el primero partiría 0-30-80)",
          list(cid) == [0, 0, 0, 1, 1, -1], f"{[int(x) for x in cid]}")

    # --- el análisis completo de la simulación, una vez ---
    res = analizar(arr, cs, verdad=ver, chequear_paridad=False, verbose=False)
    md = medir_contra_verdad(res, arr)
    res.medicion = md
    H = res.H

    # 13 ----------------------------------------- nada cruza sesión ni roll
    w = H["ventana"].to_numpy()
    fin_t = res.E["t"].to_numpy()[res.E["fin_tramo"].to_numpy()[H["i_fin"].to_numpy()]]
    bien = True
    for h in cs.horizontes_s:
        x = np.isfinite(H[f"imp_{h}"].to_numpy()) & w
        bien &= bool(np.all(H["t_fin"].to_numpy()[x] + h * NS <= fin_t[x]))
    check("impacto: ningún horizonte cruza el cierre de la sesión ni un roll (NaN, no 0)", bien)

    # 14 ----------------------------------------- impacto a mano
    t0_ = 1_786_000_000 * NS
    Em = pd.DataFrame({"t": t0_ + np.array([0, 1, 2, 3, 5]) * NS, "mid0": [100.0, 100.0, 101.0, 102.0, 104.0],
                       "px_fin": [100, 100, 101, 102, 104], "fin_tramo": [4] * 5})
    Hm = pd.DataFrame({"i_ini": [1], "i_fin": [1], "t_fin": [t0_ + NS], "mid0": [100.0], "lado": [1]})
    p0, fu = precios_futuros(Hm, Em, replace(cs, horizontes_s=(1, 3, 9), rancio_max_s=60), True)
    check("impacto a mano: referencia = libro previo; t + h = primer libro a partir de t + h; fuera = NaN",
          p0[0] == 100 and fu[0][0] == 101 and fu[1][0] == 101 and fu[3][0] == 104 and np.isnan(fu[9][0]),
          f"después {fu[0][0]:.0f} · 1 s {fu[1][0]:.0f} · 3 s {fu[3][0]:.0f} · 9 s {fu[9][0]}")

    # 15 ----------------------------------------- estadística
    v_ = np.r_[np.full(50, 1.0), np.full(50, 3.0)]
    st = media_sesiones(v_, np.r_[np.zeros(50), np.ones(50)])
    se_mano = math.sqrt(2 / 1 * ((50 * -1.0) ** 2 + (50 * 1.0) ** 2)) / 100
    check("t agrupada por sesión, p de la t y su cuantil (sin scipy)",
          abs(st["se"] - se_mano) < 1e-12 and abs(p_t(2.0, 10) - 0.073388) < 1e-5
          and abs(t_cuantil(0.975, 10 ** 6) - 1.95996) < 1e-3, f"p(t=2, 10 gl) = {p_t(2.0, 10):.6f}")

    # 16 ----------------------------------------- cola de Hill
    par_ = (1 - rng.random(200_000)) ** (-1 / 1.5)
    a_, k_ = hill(par_)
    check("Hill recupera el exponente de una Pareto (α = 1.5)", 1.35 < a_ < 1.65, f"α̂ = {a_:.3f} con k = {k_}")

    # 17 ----------------------------------------- curva de impacto
    q_ = np.floor((1 - rng.random(60_000)) ** (-1 / 1.2)).clip(1, 400)
    imp_ = 0.3 * np.sqrt(q_) + rng.normal(0, 0.5, len(q_))
    cv = curva_impacto(q_, imp_)
    check("curva de impacto: recupera δ = 0.5 de I = 0.3 √Q + ruido", abs(cv["delta"] - 0.5) < 0.1,
          f"δ̂ = {cv['delta']:.3f}")

    # 18 ----------------------------------------- triple barrera a mano
    t0r = t0_
    Er = pd.DataFrame({"t": t0r + np.arange(8) * 60 * NS, "px_max": [100, 100, 101, 103, 106, 99, 100, 100],
                       "px_min": [100, 100, 100, 102, 105, 90, 100, 100], "px_fin": [100] * 8, "fin_tramo": [7] * 8})
    Hr = pd.DataFrame({"sesion": [1, 1, 1], "vwap": [100.0, 100.0, 100.0], "lado": [1, -1, 1], "i_fin": [1, 1, 5],
                       "t_fin": [t0r + 60 * NS, t0r + 60 * NS, t0r + 300 * NS]}, index=[10, 11, 12])
    Rr = rastrear(Hr, np.array([10, 11, 12]), Er, replace(cs, seguimiento_s=1800, barrera_sigma=1.0),
                  {0: 5 / math.sqrt(30)})
    check("rastreo: toca primero la barrera a favor = SOSTENIDO, en contra = ROTO, ninguna = NEUTRO",
          list(Rr["estado"]) == [1, -1, 0], f"{list(Rr['estado'])} · barrera {Rr['barrera'].iloc[0]:.1f} t")

    # 19 ----------------------------------------- contra la verdad
    m_, b_ = md["modulo"], md["vol_inst"]
    check("encuentra el flujo institucional: recall alto y precisión muy por encima del azar",
          m_["recall"] > 0.8 and m_["precision"] > 1.8 * b_,
          f"recall {m_['recall']:.1%} · precisión {m_['precision']:.1%} (azar {b_:.1%})")
    if "tu" in md:
        check("tu script: dirección invertida en el 100 % de sus big trades institucionales",
              md["tu"]["direccion"] < 0.01, f"dirección correcta {md['tu']['direccion']:.1%}")
    T_ = md["tipos"]

    def tasa(est, tip):
        return float(T_.loc[est, tip] / T_.loc[est].sum()) if est in T_.index and tip in T_.columns else 0.0

    check("los tipos reconocen el estilo verdadero (BARRIDO, FRAGMENTADA, BLOQUE, contra iceberg → ABSORCIÓN)",
          tasa("BARRIDO", "BARRIDO") > 0.8 and tasa("FRAGMENTADA", "FRAGMENTADA") > 0.8
          and tasa("BLOQUE", "BLOQUE") > 0.8 and tasa("CONTRA ICEBERG", "ABSORCIÓN") > 0.8,
          f"{tasa('BARRIDO', 'BARRIDO'):.0%} · {tasa('FRAGMENTADA', 'FRAGMENTADA'):.0%} · {tasa('BLOQUE', 'BLOQUE'):.0%} · "
          f"{tasa('CONTRA ICEBERG', 'ABSORCIÓN'):.0%}")
    ic = md["icebergs"]
    check("ABSORCIÓN encuentra los icebergs y casi no da falsas",
          ic["detectados"] >= 0.8 * ic["n"] and ic["precision_absorcion"] > 0.9,
          f"{ic['detectados']}/{ic['n']} icebergs · precisión {ic['precision_absorcion']:.1%}")
    iv = md["impacto_verdad"].set_index("grupo")
    check("las grandes INFORMADAS dejan deriva a favor y se sostienen más que las demás",
          iv.loc["informadas", "deriva"] > iv.loc["ruido", "deriva"] + 1
          and iv.loc["informadas", "sostenido"] > iv.loc["ruido", "sostenido"] + 0.2,
          f"deriva {iv.loc['informadas', 'deriva']:+.2f} vs {iv.loc['ruido', 'deriva']:+.2f} t · sostenido "
          f"{iv.loc['informadas', 'sostenido']:.0%} vs {iv.loc['ruido', 'sostenido']:.0%}")

    # 20 ----------------------------------------- IDs
    ids = res.G["id"].to_numpy()
    check("cada huella grande tiene un ID único y legible",
          len(set(ids)) == len(ids) and all(re.fullmatch(r"[A-Z0-9]+\d{4}-\d{3,}", x) for x in ids[:50]),
          f"{ids[0]} … {ids[-1]}")

    # 21 ----------------------------------------- sin libro (esquema trades)
    tr_ = np.zeros(len(arr), dtype=[(k, DTYPE_TBBO[k]) for k in ("ts_recv", "ts_event", "instrument_id", "action",
                                                                  "side", "price", "size", "flags", "sequence")])
    for k in tr_.dtype.names:
        tr_[k] = arr[k]
    rt = analizar(tr_, cs, chequear_paridad=False, verbose=False)
    check("--esquema trades: corre sin libro, sin ABSORCIÓN y avisa del rebote",
          not rt.info["con_libro"] and int((rt.H["tipo"] == 2).sum()) == 0 and not rt.tu.get("disponible")
          and np.isfinite(rt.G["imp_60"]).any(), f"{len(rt.G):,} grandes")

    # 22 ----------------------------------------- validación
    malos = 0
    for kw in ({"esquema": "mbo"}, {"p_grande": 0.995}, {"rafaga_ms": 2000.0}, {"pureza_min": 0.3},
               {"h_principal_s": 7}, {"start": "2026-08-21T00:00:00"}, {"alerta_min": 5}):
        try:
            validar(replace(cfg, **kw))
        except SystemExit:
            malos += 1
    check("rechaza configuraciones inválidas", malos == 7, f"{malos}/7")

    # 23 ----------------------------------------- Live con clientes falsos = el análisis por lotes
    ses = ver["sesiones"]
    if db is not None:
        try:
            ap = apertura_utc(ses[-1], cs.tz_mercado)
            hist = arr[arr["ts_event"].astype(np.int64) < ap]
            hoy = db.DBNStore.from_bytes(a_dbn(arr[arr["ts_event"].astype(np.int64) >= ap], cs))

            class _Live:
                def subscribe(self, **kw):
                    self.kw = kw

                def __iter__(self):
                    return iter(hoy)

                def stop(self):
                    pass

            import contextlib
            import io
            with contextlib.redirect_stdout(io.StringIO()):
                cl = correr_live(replace(cs, telegram_live=False), cliente_live=_Live(), historia=hist,
                                 ahora=pd.Timestamp(ap + 3600 * NS, tz="UTC"))
            lote = res.G[res.G["sesion"] == ses[-1]]
            check("Live (incremental + umbrales causales) da las MISMAS huellas grandes que el análisis por lotes",
                  cl.emitidas == len(lote) and cl.emitidas > 0, f"live {cl.emitidas} · lote {len(lote)}")
        except Exception as ex:
            check("Live con clientes falsos", False, f"{type(ex).__name__}: {ex}")
    else:
        check("Live (databento no instalado: se omite)", True)

    # 24-27 -------------------------------------- Telegram y secretos
    tok = "123456789:" + "A" * 35
    msg = _sin_token(f"fallo en https://api.telegram.org/bot{tok}/sendMessage", tok)
    check("los errores de Telegram nunca muestran el token", tok not in msg and "…" in msg)
    import urllib.request
    capturas = []

    class _Resp:
        def __init__(self, cuerpo):
            self.cuerpo = cuerpo

        def read(self):
            return self.cuerpo

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _falso(req, timeout=None):
        capturas.append(req)
        return _Resp(json.dumps({"ok": True, "result": {}}).encode())

    viejo = urllib.request.urlopen
    png = Path(__file__).resolve().parent / "_prueba_telegram.png"
    bien = False
    try:
        urllib.request.urlopen = _falso
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
        ok = llamar_telegram(tok, "sendPhoto", {"chat_id": "123456789", "caption": "á <b>"},
                             archivo=("photo", png)).get("ok")
        cuerpo = capturas[-1].data
        limite = capturas[-1].get_header("Content-type").split("boundary=")[1]
        bien = (ok and cuerpo.startswith(f"--{limite}".encode()) and cuerpo.rstrip().endswith(f"--{limite}--".encode())
                and b'name="photo"; filename="_prueba_telegram.png"' in cuerpo and tok.encode() not in cuerpo)
    finally:
        urllib.request.urlopen = viejo
        png.unlink(missing_ok=True)
    check("Telegram: el multipart de sendPhoto está bien formado y no lleva el token", bool(bien))
    fuente = Path(__file__).read_text(encoding="utf-8")
    check("no hay API keys ni tokens escritos en el código",
          not re.search("db" + "-" + r"[A-Za-z0-9]{20,}", fuente) and not re.search(r"\d{8,10}:" + r"[A-Za-z0-9_-]{35}", fuente))
    txt = mensaje_telegram(res)
    check("el mensaje de Telegram cabe en un mensaje", len(txt) <= 4096 and "<b>" in txt, f"{len(txt)} caracteres")

    print()
    if fallas:
        print(f"❌ {len(fallas)} de {hecho} pruebas fallaron: {', '.join(fallas)}")
        return 1
    print(f"✅ Las {hecho} pruebas pasaron.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrumpido.")
        sys.exit(130)
