# -*- coding: utf-8 -*-
"""
Rastreador de ID AC v2 — ciclo de vida de cada orden (MBO) y barridos de liquidez institucional
Datos: Databento MBO (GLBX.MDP3), orden por orden, con el order_id que asigna CME.

Qué hace, en una línea: reconstruye el libro de órdenes del 6J orden por orden (Databento MBO)
y sigue cada order_id desde que entra hasta que se llena, se cancela o se modifica. Con eso
detecta los barridos de liquidez (un agresor, o una ráfaga, que se come varios niveles) y los
clasifica DESPUÉS de ver qué hizo el precio. Las alertas llegan a Telegram, en vivo o al
terminar un análisis histórico.

LO QUE PEDISTE, HECHO A FONDO

  1. RASTREO EXACTO DEL CICLO DE VIDA DE LAS ÓRDENES. Un libro por instrumento con las reglas
     de Databento: A entra, C resta (total o parcial), M trae precio y tamaño NUEVOS (si cambia
     el precio pierde su lugar en la fila), R limpia. T y F NO tocan el libro. Un evento es el
     grupo de registros que cierra la bandera F_LAST: la operación y las C/M de las órdenes que
     se llevó llegan juntas, y así se sabe QUÉ orden se llenó aunque tus datos no traigan
     registros F. Cada orden termina como llena, parcial y cancelada, cancelada, limpieza del
     libro o viva, con su vida, sus modificaciones y si fue fugaz (cancelada sin ejecutarse en
     menos de 100 ms). En 12 simulaciones de 6 h (6.9 millones de registros) el libro final, el
     ciclo de vida de cada orden y los contratos llenados salen IDÉNTICOS a la verdad, con y sin
     registros F. Un snapshot (R + altas con F_SNAPSHOT) no corta la historia de las órdenes
     que siguen vivas.

  2. DETECCIÓN DE "SWEEPS" (BARRIDOS DE LIQUIDEZ INSTITUCIONAL). Dos niveles de lectura:
       · EXACTO: un solo agresor que cruzó varios niveles en un evento (sus T comparten
         F_LAST). Coincide uno a uno con la verdad en las 12 simulaciones;
       · RÁFAGA: golpes agresivos a ≤ 100 ms entre sí (tu SWEEP_WINDOW_MS), con ventana que se
         desliza y dura máximo 1 s. Así se ve el algoritmo que parte su orden en pedazos.
     Califica con tus criterios: ≥ 2 niveles, ≥ 2 ticks, pureza ≥ 70 % y el volumen del
     umbral. De cada barrido se mide cuántas órdenes en reposo consumió y su edad, cuánto se
     había CANCELADO en esos niveles en el segundo anterior (retiro previo) y cuánto REPUSO el
     lado pasivo en el segundo siguiente (reposición).

  3. MONOTONICIDAD, en los dos sentidos:
       · pureza (tu MONOTONICITY_MIN): volumen del lado dominante / total de la ráfaga;
       · monotonicidad del PRECIO: de los pasos de precio de la ráfaga, cuántos van hacia el
         lado del barrido (≥ 70 %).
     Un barrido de un solo agresor tiene que ser monótono por construcción: si no lo es, el
     chequeo de cordura lo marca como dato raro.

  4. CLASIFICADOR FORENSE DE COMPORTAMIENTO. Espera 5 s (tu ventana) en tiempo del mercado y
     mira el mid del LIBRO reconstruido:
       · MOMENTUM: el mid sigue ≥ 0.5·σ más allá del último nivel barrido;
       · CAZA DE STOPS: el mid regresa ≥ 0.5·σ detrás de donde estaba antes del barrido;
       · ABSORCIÓN: ni sigue ni regresa, y el lado pasivo repuso ≥ 50 % de lo barrido;
       · NEUTRAL: el resto.
     σ es el desplazamiento típico del mid en 5 s durante la última hora, con piso de 1 tick.
     Con barridos plantados de clase conocida, en 12 simulaciones: 731 de 735 detectados
     (99.5 %) y 96 % de ellos con la clase correcta. La clase es estable si el horizonte va de
     5 a 30 s (--horizonte).

  5. ADAPTABILIDAD AUTOMÁTICA DE UMBRALES:
       · volumen: percentil 95 (tu VOL_ADAPTIVE_PCTL) de las últimas 1 000 RÁFAGAS, nunca de
         operaciones sueltas; sólo con ráfagas anteriores y con tu piso de 20 contratos;
       · clase: σ del propio instrumento, que cambia con la hora y el día;
       · órdenes grandes: percentil 99.9 del tamaño de las altas (piso 25);
       · enfriamiento de 30 s por dirección en tiempo del MERCADO.
     El tablero dibuja el umbral contra cada barrido.

  6. INTEGRACIÓN DE ALERTAS REMOTAS. Telegram con el token y el chat en variables de entorno:
       · en vivo (--live --telegram-live), un mensaje por barrido clasificado; los NEUTRAL
         llegan sin sonido;
       · con --alerta-inmediata, también un aviso al detectarlo, antes de la clase;
       · con --telegram-grandes, las órdenes grandes que terminan su ciclo;
       · avisos de radar activado, apagado y fallido, como en tu script;
       · lo que llega antes de 2 s se AGRUPA en un mensaje (tu versión lo tiraba), y el HTML
         se escapa;
       · en un análisis histórico, el resumen y los 2 tableros (--telegram).

  Además:
    · rastreo por ID de las órdenes GRANDES: si se ejecutaron, si se retiraron lejos o si se
      retiraron cuando el precio llegó a 1 tick (patrón a vigilar, no prueba de spoofing).
      En la simulación, 94 % de las genuinas se ejecutan (total o parcialmente) y 87 % de las
      plantadas para retirarse salen retiradas;
    · Live con SNAPSHOT y reconexión que reconstruye el libro;
    · tu detector corriendo al lado sobre los mismos datos, para compararlo;
    · un chequeo de cordura de los datos;
    · un simulador MBO con verdad conocida que escribe un DBN de verdad;
    · 2 tableros, 4 CSV y 22 pruebas internas.

QUÉ SE MIDIÓ — 12 simulaciones de 6 h (6 semillas, con y sin registros F), 735 barridos plantados

                                         alertas   barridos vistos   clase correcta
    módulo                                   769       99.5 %         96 % de los vistos
    tu script, con registros F                 0          0 %          —
    tu script, sin F (como corre en replay)   12        2.3 %         4 de 9
    tu script, sin F, enfriamiento por
      tiempo del mercado                     413       93.3 %         40 % de los vistos

  · Con registros F tu detector NO PUEDE alertar: cada contrato entra dos veces, como T (lado
    del agresor) y como F (lado de la orden en reposo), y la "monotonicidad" queda en 0.5
    exacto, abajo de tu 0.7.
  · En replay, tu enfriamiento con time.time() deja pasar casi sólo el primer barrido de cada
    dirección: el replay corre en segundos.
  · Aun dándole tiempo de mercado, tu clasificador llama MOMENTUM a 12 barridos cuando hubo
    ~200: su precio "posterior" es el de cualquier registro, y lo busca antes de que exista.
  · Alertas del módulo = barridos fuera del enfriamiento de 30 s; los 820 barridos (con los
    de enfriamiento y los naturales del simulador) quedan en el CSV.
  · El módulo procesa ~8 µs por registro: un millón de registros MBO en ~8 s.

QUÉ FALLABA EN TU SCRIPT (los comentarios [v1] lo marcan en el código)

  · LA API KEY DE DATABENTO, EL TOKEN DEL BOT Y EL CHAT ID ESTÁN ESCRITOS EN LAS LÍNEAS 14-16.
    Dalos por publicados: regenera la key en el portal de Databento y revoca el token con
    @BotFather (/revoke). Aquí se leen de DATABENTO_API_KEY, TELEGRAM_BOT_TOKEN y
    TELEGRAM_CHAT_ID, igual que en tus otros módulos.

  · EL CLASIFICADOR MIRA UN PRECIO QUE NO ES EL DEL MERCADO, Y A DESTIEMPO. update_price guarda
    el precio de TODOS los registros (una alta 30 ticks abajo, una cancelación, el precio
    indefinido de una R). Y busca el precio 5 s después en el momento de detectar, cuando ese
    futuro todavía no existe. Aquí la clase espera los 5 s y usa el mid del libro.

  · T Y F MEZCLADAS. El lado de una F es el de la orden en reposo, el contrario al agresor.
    Sumarlas a las T duplica el volumen y anula la dirección (arriba). Además tu
    OrderBookTracker resta tamaño con T, F y una acción 'E' que no existe en Databento.

  · EL UMBRAL ADAPTATIVO COMPARA PERAS CON MANZANAS: el volumen TOTAL de una ventana contra el
    percentil 95 del tamaño de UNA operación. Casi cualquier ventana con 3 operaciones lo pasa.

  · RELOJ DE PARED donde va el del mercado: el enfriamiento y purge_stale. La purga borra del
    libro las órdenes con más de una hora: una orden GTC legítima desaparece y sus
    cancelaciones posteriores se vuelven huérfanas.

  · VENTANAS FIJAS ancladas en su primera operación. Parten un barrido en dos si cruza el
    borde, y la última ventana no se evalúa hasta que llega otra operación, quizá minutos
    después.

  · LIVE SIN SNAPSHOT: el libro arranca vacío y las órdenes que ya estaban nunca se conocen.

  · Menores: el límite de 2 s de Telegram tira alertas; el HTML no se escapa; el libro no se
    separa por instrumento (en un roll se mezclan los dos contratos).

LÍMITES QUE CONVIENE SABER
  · La simulación decide la plomería (libro, ciclo de vida, detección, que la clase se
    calcule bien). NO decide si en el 6J real una CAZA DE STOPS anticipa algo: eso lo dice el
    tablero de tus datos (el camino medio del mid después de cada clase).
  · Sin registros F, el llenado se deduce de que la C/M de la orden llegue en el MISMO evento
    que la operación. El chequeo "volumen operado con su orden identificada" lo verifica en tus
    datos: si baja de 99 %, esa deducción no aplica.
  · Si los datos empiezan con órdenes que ya estaban en el libro, sus C/M salen huérfanas y el
    chequeo lo avisa. Por eso el rango por omisión empieza el domingo antes de la apertura.
    En vivo, el snapshot lo resuelve.
  · Las reposiciones tipo iceberg se cuentan como reposición; el módulo no afirma que sean
    icebergs.
  · MBO pesa mucho más que trades: antes de descargar se revisa el costo (--costo-max, 25 USD).
    En NQ son decenas de millones de registros por día.

CÓMO SE USA
    pip install numpy pandas matplotlib databento
    python rastreador_id.py --pruebas                  # 22 pruebas, sin red
    python rastreador_id.py --simulacion               # libro MBO simulado con verdad conocida
    python rastreador_id.py --simulacion --sin-fills   # el mismo, como si tus datos no trajeran F
    python rastreador_id.py                            # 6J, 20-23 de septiembre de 2026
    python rastreador_id.py --simbolo 6E --inicio 2026-09-27T21:00:00 --fin 2026-09-30T21:00:00
    python rastreador_id.py --archivo mbo.dbn.zst
    python rastreador_id.py --ventana-ms 100 --min-niveles 2 --min-ticks 2 --pureza 0.7 --horizonte 5
    python rastreador_id.py --telegram                 # resumen + 2 tableros
    python rastreador_id.py --live --telegram-live     # en vivo; cada barrido a tu teléfono
    python rastreador_id.py --live --telegram-live --alerta-inmediata --telegram-grandes
  Las horas van en hora de CHICAGO y de CDMX (con milisegundos). Con --sin-paridad se salta
  la comprobación de que la ruta de Live (registro por registro) dé lo mismo que la de bloques.

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
  Databento: https://databento.com/docs — esquema MBO, acciones A/C/M/R/T/F/N, banderas
      F_LAST, F_SNAPSHOT, F_BAD_TS_RECV y F_MAYBE_BAD_BOOK, y Live con snapshot.
  CME Group, MDP 3.0 Market by Order — datos por orden y eventos de matching de Globex.
  Osler, C. (2003), "Currency orders and exchange rate dynamics: an explanation for the
      predictive success of technical analysis", Journal of Finance 58(5). — los stops se
      amontonan y su ejecución en cascada mueve el precio.
  Hasbrouck, J. y Saar, G. (2009), "Technology and liquidity provision: the blurring of
      traditional definitions", Journal of Financial Markets 12(2). — las órdenes fugaces.
  Farmer, J. D., Patelli, P. y Zovko, I. (2005), "The predictive power of zero intelligence in
      financial markets", PNAS 102(6). — el tipo de libro del simulador.
  Telegram Bot API: https://core.telegram.org/bots/api
"""
from __future__ import annotations

import argparse
import bisect
import heapq
import html
import json
import math
import os
import re
import sys
import time
import uuid
import warnings
from collections import Counter, deque
from dataclasses import dataclass, replace
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

try:
    import databento as db
except ModuleNotFoundError:
    db = None

IDENTIFICADOR = "rastreador-id-ac-v2"
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)
np.seterr(all="ignore")

NS = 1_000_000_000
NS_MS = 1_000_000
PRICE_SCALE = 1e9                  # precios en punto fijo: enteros × 1e9
UNDEF_PRICE = 9223372036854775807
F_LAST, F_TOB, F_SNAPSHOT, F_MBP, F_BAD_TS_RECV, F_MAYBE_BAD_BOOK = 128, 64, 32, 16, 8, 4

# Raíz → (nombre, tamaño del tick, precio de referencia para la simulación)
CATALOGO = {
    "6J": ("Yen japonés", 0.0000005, 0.0068), "6E": ("Euro", 0.00005, 1.10),
    "6B": ("Libra", 0.0001, 1.27), "6A": ("Dólar australiano", 0.00005, 0.66),
    "6C": ("Dólar canadiense", 0.00005, 0.73), "6S": ("Franco suizo", 0.00005, 1.15),
    "NQ": ("Nasdaq 100", 0.25, 20000.0), "MNQ": ("Micro Nasdaq 100", 0.25, 20000.0),
    "ES": ("S&P 500", 0.25, 5500.0), "MES": ("Micro S&P 500", 0.25, 5500.0),
    "YM": ("Dow Jones", 1.0, 42000.0), "RTY": ("Russell 2000", 0.1, 2200.0),
    "CL": ("Crudo WTI", 0.01, 75.0), "GC": ("Oro", 0.1, 2500.0), "ZN": ("Nota 10 años", 1 / 64, 110.0),
}
DTYPE_MBO = np.dtype([("ts_event", "<u8"), ("ts_recv", "<u8"), ("order_id", "<u8"), ("price", "<i8"),
                      ("size", "<u4"), ("flags", "u1"), ("action", "S1"), ("side", "S1"),
                      ("instrument_id", "<u4"), ("sequence", "<u4")])


# =============================================================================
# 1. CONFIGURACIÓN
# =============================================================================
@dataclass(frozen=True)
class Config:
    # --- Datos ---
    dataset: str = "GLBX.MDP3"
    symbol: str = "6J.n.0"                  # tu SYMBOL
    stype_in: str = "continuous"
    start: str = "2026-09-20T21:00:00"      # UTC: domingo antes de la apertura de Globex (17:00 CT)
    end: str = "2026-09-23T21:00:00"        # UTC, exclusivo: tres sesiones
    tick_size: float | None = None          # None = del catálogo (6J: 0.0000005)
    cache_dir: str = "datos_databento"
    salida_dir: str = "salidas_rid"
    costo_max_usd: float = 25.0
    tam_bloque: int = 2_000_000             # registros por bloque (64 bytes c/u)
    tz_mercado: str = "America/Chicago"
    tz_local: str = "America/Mexico_City"

    # --- Barridos (sweeps) ---
    gap_ms: float = 100.0                   # tu SWEEP_WINDOW_MS: eventos agresivos a ≤ 100 ms = una ráfaga
    dur_max_ms: float = 1000.0              # una ráfaga no dura más de 1 s
    min_niveles: int = 2                    # tu MIN_SWEEP_LEVELS
    min_ticks: int = 2                      # tu MIN_SWEEP_TICKS
    pureza_min: float = 0.70                # tu MONOTONICITY_MIN (volumen del lado dominante / total)
    mono_min: float = 0.70                  # monotonicidad del PRECIO: pasos a favor / pasos con cambio
    min_vol: int = 20                       # tu MIN_SWEEP_VOL: piso del umbral adaptativo
    pctl_vol: float = 0.95                  # tu VOL_ADAPTIVE_PCTL, pero sobre RÁFAGAS, no operaciones
    n_adapt: int = 1000                     # ráfagas recientes para el percentil
    min_obs_adapt: int = 100
    cooldown_s: float = 30.0                # tu COOLDOWN_SEC, en tiempo del MERCADO

    # --- Clasificador forense ---
    horizonte_s: float = 5.0                # tu ventana de 5 s, pero esperándola
    k_cont: float = 0.5                     # continúa ≥ 0.5·σ más allá del extremo → MOMENTUM
    k_rev: float = 0.5                      # regresa ≥ 0.5·σ detrás del inicio → CAZA DE STOPS
    reposicion_min: float = 0.5             # lado pasivo repone ≥ 50 % de lo barrido → ABSORCIÓN
    ventana_repos_ms: float = 1000.0
    ventana_retiro_ms: float = 1000.0       # cancelaciones en los niveles barridos justo antes
    sigma_ventana_s: int = 3600             # σ del mid a H segundos: la última hora

    # --- Órdenes grandes (rastreo por ID) ---
    min_grande: int = 25
    pctl_grande: float = 0.999
    n_grande: int = 5000
    fugaz_ms: float = 100.0                 # cancelada sin ejecutarse antes de 100 ms = fugaz

    # --- Live y alertas ---
    max_reintentos: int = 10                # tu MAX_RETRIES
    espera_max_s: float = 120.0             # tu MAX_BACKOFF
    heartbeat_s: float = 300.0
    telegram_live: bool = False
    telegram_grandes: bool = False
    telegram_intervalo_s: float = 2.0       # tu límite de 2 s, pero agrupando en vez de tirar
    alerta_inmediata: bool = False          # avisar al detectar (sin clase) además de al clasificar

    # --- Simulación ---
    sim_horas: float = 6.0
    sim_tasa: float = 12.0                  # altas por segundo
    sim_cada_min: float = 6.0               # un evento institucional plantado cada ~6 min
    sim_fills: bool = True                  # emitir registros F de las órdenes en reposo
    sim_semilla: int = 0


CFG = Config()
CARPETA_SCRIPT = Path(__file__).resolve().parent


def _ruta(nombre: str) -> Path:
    p = Path(nombre)
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


def raiz(symbol: str) -> str:
    m = re.match(r"[A-Za-z0-9]+?(?=[.]|[FGHJKMNQUVXZ]\d|$)", symbol)
    return (m.group(0) if m else symbol.split(".")[0]).upper()


def simbolo_continuo(s: str) -> str:
    s = s.strip()
    return s if "." in s else f"{s.upper()}.n.0"


def nombre(symbol: str) -> str:
    return CATALOGO.get(raiz(symbol), (raiz(symbol), 1.0, 100.0))[0]


def tick_de(cfg: Config) -> float:
    return cfg.tick_size or CATALOGO.get(raiz(cfg.symbol), ("", 1.0, 100.0))[1]


def tick_int(cfg: Config) -> int:
    """El tick en punto fijo (6J: 500)."""
    return max(1, int(round(tick_de(cfg) * PRICE_SCALE)))


def validar(cfg: Config) -> None:
    if cfg.min_niveles < 1 or cfg.min_ticks < 0:
        sys.exit("❌ min_niveles ≥ 1 y min_ticks ≥ 0.")
    if not (0.5 <= cfg.pureza_min <= 1 and 0 <= cfg.mono_min <= 1):
        sys.exit("❌ La pureza va de 0.5 a 1 y la monotonicidad de 0 a 1.")
    if cfg.horizonte_s <= 0 or cfg.gap_ms <= 0:
        sys.exit("❌ El horizonte y la ventana deben ser positivos.")


# =============================================================================
# 2. DATOS — Databento MBO, con la key FUERA del código
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
    "  • La que estaba escrita en tu script (línea 14) hay que darla por publicada: regenérala en\n"
    "    https://databento.com/docs/portal/api-keys\n"
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


def obtener_datos(cfg: Config, cliente=None):
    """Descarga UNA vez a disco (.dbn.zst), revisando el costo antes. La caché se reutiliza."""
    carpeta = _ruta(cfg.cache_dir)
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / (_nombre_seguro(cfg.dataset, cfg.symbol, cfg.start, cfg.end, "mbo") + ".dbn.zst")
    if ruta.exists():
        print(f"📂 Usando caché local: {ruta.name}")
        return db.DBNStore.from_file(ruta)
    cliente = cliente or conectar()
    params = dict(dataset=cfg.dataset, symbols=cfg.symbol, stype_in=cfg.stype_in, schema="mbo",
                  start=cfg.start, end=cfg.end)
    costo = cliente.metadata.get_cost(**params)
    print(f"💵 Costo estimado: US$ {costo:,.2f}  ({cfg.symbol}, mbo, {cfg.start[:16]} → {cfg.end[:16]})")
    if costo > cfg.costo_max_usd:
        sys.exit(f"💰 El costo (US$ {costo:,.2f}) supera tu tope de US$ {cfg.costo_max_usd:,.2f}.\n"
                 f"   Si estás de acuerdo:  --costo-max {math.ceil(costo) + 1}")
    temporal = ruta.with_name(ruta.name + ".parcial")
    temporal.unlink(missing_ok=True)
    print(f"📡 Descargando MBO a {ruta.name} …")
    descarga = cliente.timeseries.get_range(**params, path=temporal)
    del descarga                                # Windows no renombra archivos abiertos
    temporal.replace(ruta)
    return db.DBNStore.from_file(ruta)


def bloques(tienda, cfg: Config):
    """DBNStore → bloques de to_ndarray(); un arreglo estructurado → rebanadas."""
    if hasattr(tienda, "to_ndarray"):
        yield from tienda.to_ndarray(count=cfg.tam_bloque)
    else:
        for i in range(0, len(tienda), cfg.tam_bloque):
            yield tienda[i:i + cfg.tam_bloque]


# =============================================================================
# 3. EL LIBRO Y EL CICLO DE VIDA DE CADA ORDEN
# =============================================================================
# Reglas del esquema MBO de Databento (las de la documentación de databento_dbn):
#   A  alta: la orden entra al libro con su order_id.
#   C  cancelación total o parcial: se resta `size`; en 0 la orden sale del libro.
#   M  modificación: precio y tamaño NUEVOS. Si cambia el precio o sube el tamaño pierde su
#      lugar en la fila.
#   R  limpieza: se vacía el libro del instrumento (suele venir antes de un snapshot).
#   T  operación: el lado es el del AGRESOR. NO toca el libro.
#   F  llenado de una orden en reposo. NO toca el libro: la orden baja con su C o su M.
#   N  nada (puede traer banderas).
# Un EVENTO es el grupo de registros que cierra la bandera F_LAST: lo que publicó el motor de
# CME por un solo mensaje. Una orden agresiva que barre 3 niveles deja sus 3 T en un evento, y
# las C/M de las órdenes que se llevó van en el mismo evento: así se sabe QUÉ orden se llenó.
#
# [v1] Tu OrderBookTracker resta tamaño con T, F y 'E' (que no existe en Databento). Con T no
# hace nada (el order_id de una T no es una orden del libro), pero si tus datos traen F la
# orden baja dos veces: con la F y otra vez con su C/M. Aquí T y F no tocan el libro.

O_LADO, O_PRECIO, O_TAM, O_TADD, O_TAM0, O_LLENO, O_CANC, O_NMOD, O_NPRECIO, O_SNAP, O_GRANDE = range(11)
MOTIVOS = ("llena", "parcial y cancelada", "cancelada", "limpieza del libro", "viva al final")
BINS_VIDA = np.arange(-6.0, 6.01, 0.25)                 # log10(segundos de vida)
LADO_DE = {"B": 1, "A": -1, "N": 0}
CHAR_DE = {1: "B", -1: "A", 0: "N"}
CLASES = ("MOMENTUM", "CAZA DE STOPS", "ABSORCIÓN", "NEUTRAL")


class Libro:
    """Las órdenes vivas de UN instrumento y el tamaño por nivel, con el mejor precio al día."""
    __slots__ = ("ordenes", "niv", "mejor")

    def __init__(self):
        self.ordenes: dict[int, list] = {}
        self.niv = {1: {}, -1: {}}
        self.mejor = {1: None, -1: None}

    def sumar(self, lado: int, precio: int, q: int) -> None:
        d = self.niv[lado]
        nuevo = d.get(precio, 0) + q
        if nuevo > 0:
            d[precio] = nuevo
            m = self.mejor[lado]
            if m is None or (precio > m if lado > 0 else precio < m):
                self.mejor[lado] = precio
        else:
            d.pop(precio, None)
            if self.mejor[lado] == precio:
                self.mejor[lado] = (max(d) if lado > 0 else min(d)) if d else None

    def mid(self) -> float | None:
        b, a = self.mejor[1], self.mejor[-1]
        return (b + a) / 2 if b is not None and a is not None else None


class DetectorVentanas:
    """
    Tu SweepAggregator + handle_sweep, tal cual, para compararlo con tus propios datos: ventanas
    FIJAS de 100 ms ancladas en su primera operación, con T y F mezcladas, umbral = percentil 95
    del tamaño de UNA operación, y la ventana se evalúa cuando llega la siguiente operación.
    Única concesión: el enfriamiento corre en tiempo del mercado (con reloj de pared, en un
    replay sólo pasaría el primer barrido de cada dirección).
    """

    def __init__(self, cfg: Config, tick: int):
        self.cfg, self.tick = cfg, tick
        self.v_ns = int(cfg.gap_ms * NS_MS)
        self.t0 = None
        self.tr: list[tuple] = []
        self.vols: deque = deque(maxlen=1000)
        self.ult: dict[str, int] = {}
        self.salida: list[dict] = []

    def agregar(self, ts: int, precio: int, q: int, lado: str) -> None:
        self.vols.append(q)
        if self.t0 is None:
            self.t0, self.tr = ts, [(ts, precio, q, lado)]
            return
        if ts - self.t0 <= self.v_ns:
            self.tr.append((ts, precio, q, lado))
            return
        self._evaluar()
        self.t0, self.tr = ts, [(ts, precio, q, lado)]

    def _evaluar(self) -> None:
        cfg, tr = self.cfg, self.tr
        if len(tr) < 3:
            return
        precios = [p for _, p, _, _ in tr]
        if len(set(precios)) < cfg.min_niveles or (max(precios) - min(precios)) / self.tick < cfg.min_ticks:
            return
        total = sum(q for *_, q, _ in tr)
        compra = sum(q for *_, q, s in tr if s == "B")
        venta = sum(q for *_, q, s in tr if s == "A")
        if total <= 0 or max(compra, venta) / total < cfg.pureza_min:
            return
        umbral = cfg.min_vol if len(self.vols) < 50 else float(np.percentile(self.vols, cfg.pctl_vol * 100))
        if total < max(cfg.min_vol, umbral):
            return
        d = "BUY" if compra > venta else "SELL"
        if d in self.ult and tr[0][0] - self.ult[d] < cfg.cooldown_s * NS:
            return
        self.ult[d] = tr[0][0]
        self.salida.append({"t_ini": tr[0][0], "t_fin": tr[-1][0], "lado": 1 if d == "BUY" else -1, "vol": total,
                            "compra": compra, "venta": venta, "niveles": len(set(precios)),
                            "ticks": (max(precios) - min(precios)) / self.tick, "pureza": max(compra, venta) / total})


class Rastreador:
    """
    El motor: un registro a la vez, igual para un archivo DBN que para Databento Live.
    Llama a `al_barrido(b)` cuando un barrido queda CLASIFICADO (y, con alerta_inmediata, también
    al detectarlo) y a `al_grande(g)` cuando una orden grande termina su ciclo de vida.
    """

    def __init__(self, cfg: Config, al_barrido=None, al_grande=None, con_tuyo: bool = True):
        self.cfg = cfg
        self.tick = tick_int(cfg)
        self.al_barrido, self.al_grande = al_barrido, al_grande
        self.libros: dict[int, Libro] = {}
        self.iid: int | None = None
        self._ev_abierto = False
        self._ev_ts = self._ev_iid = None
        self._ev_mid0 = None
        self._ev_snap = True
        self._ev_trades: list[tuple] = []
        self._ev_fills: dict[int, int] = {}
        self._ev_red: list[tuple] = []
        self._ev_adds: list[tuple] = []
        self._resto = None
        self._limbo: dict[int, list] = {}
        self._ts_max = -1
        self.conteo: Counter = Counter()
        self.lat: list[int] = []
        self.vida = {m: np.zeros(len(BINS_VIDA) + 1, np.int64) for m in MOTIVOS}
        self.ciclo: Counter = Counter()
        self.qty: Counter = Counter()
        # barridos
        self._raf = None
        self.n_rafagas = 0
        self.barridos: list[dict] = []
        self.exactos: list[tuple] = []          # (ts, lado, niveles, vol, p_ini, p_ext): eventos de UN agresor con ≥ 2 niveles
        self._vols: deque = deque(maxlen=cfg.n_adapt)
        self._vols_ord: list[int] = []
        self.umbrales: list[tuple] = []          # (ts, umbral) para el tablero
        self._ultimo = {1: -10 ** 19, -1: -10 ** 19}
        self._pend: list[dict] = []
        self._retiros: deque = deque()
        self._altas_rec: deque = deque()          # altas recientes: la reposición empieza al fin del barrido
        self._repos: list[list] = []
        # mid por segundo (tablero, σ y estudio de eventos)
        self.seg_t: list[int] = []
        self.seg_mid: list[float] = []
        self._seg_ult = None
        h = max(1, int(round(cfg.horizonte_s)))
        self._sig: deque = deque(maxlen=cfg.sigma_ventana_s + h)
        # órdenes grandes
        self._adds_tam: deque = deque(maxlen=cfg.n_grande)
        self._n_adds = 0
        self.umbral_grande = cfg.min_grande
        self.grandes_vivas: dict[int, dict] = {}
        self.grandes: list[dict] = []
        self.tuyo = DetectorVentanas(cfg, self.tick) if con_tuyo else None
        self._id = 0

    # ------------------------------------------------------------------ entrada
    def procesar(self, ts: int, acc: str, lado_c: str, precio: int, tam: int, oid: int, flags: int, iid: int,
                 ts_recv: int = 0) -> None:
        c = self.conteo
        c["registros"] += 1
        if ts < self._ts_max:
            c["ts_retrocede"] += 1
            ts = self._ts_max
        self._ts_max = ts
        if self._ev_abierto and (ts != self._ev_ts or iid != self._ev_iid):
            c["eventos_sin_F_LAST"] += 1
            self._cerrar_evento()
        if not self._ev_abierto:
            self._abrir_evento(ts, iid)
        c[acc] += 1
        if flags & F_BAD_TS_RECV:
            c["ts_recv_malo"] += 1
        elif ts_recv and c["registros"] % 64 == 0:
            self.lat.append(ts_recv - ts)
        if flags & F_MAYBE_BAD_BOOK:
            c["libro_dudoso"] += 1
        if not flags & F_SNAPSHOT and acc != "R":
            self._ev_snap = False
        else:
            c["snapshot"] += acc != "R"
        lado = LADO_DE.get(lado_c, 0)
        libro = self.libros.get(iid)
        if libro is None:
            libro = self.libros[iid] = Libro()
        if acc == "A":
            self._alta(libro, ts, lado, precio, tam, oid, flags)
        elif acc == "C":
            self._cancelar(libro, ts, lado, precio, tam, oid)
        elif acc == "M":
            self._modificar(libro, ts, lado, precio, tam, oid)
        elif acc == "T":
            self._ev_trades.append((precio, tam, lado, oid))
            if self.tuyo is not None:
                self.tuyo.agregar(ts, precio, tam, lado_c)
        elif acc == "F":
            self._ev_fills[oid] = self._ev_fills.get(oid, 0) + tam
            if self.tuyo is not None:
                self.tuyo.agregar(ts, precio, tam, lado_c)
        elif acc == "R":
            self._limpiar(libro)
        elif acc != "N":
            c["accion_desconocida"] += 1
        if flags & F_LAST:
            self._cerrar_evento()

    def procesar_registro(self, r) -> None:
        """Un MBOMsg de databento (archivo o Live)."""
        self.procesar(r.ts_event, str(r.action), str(r.side), r.price, r.size, r.order_id, r.flags,
                      r.instrument_id, r.ts_recv)

    def procesar_arreglo(self, arr: np.ndarray) -> None:
        """Un bloque de to_ndarray(): columnas a listas de Python y el mismo motor, registro a registro."""
        ts = arr["ts_event"].astype(np.int64).tolist()
        tr = arr["ts_recv"].astype(np.int64).tolist()
        acc = arr["action"].astype("U1").tolist()
        lado = arr["side"].astype("U1").tolist()
        pr, q, oid = arr["price"].tolist(), arr["size"].tolist(), arr["order_id"].tolist()
        fl, iid = arr["flags"].tolist(), arr["instrument_id"].tolist()
        p = self.procesar
        for i in range(len(ts)):
            p(ts[i], acc[i], lado[i], pr[i], q[i], oid[i], fl[i], iid[i], tr[i])

    # ------------------------------------------------------------------ el libro
    def _alta(self, libro: Libro, ts, lado, precio, tam, oid, flags) -> None:
        if lado == 0 or tam <= 0 or precio == UNDEF_PRICE:
            self.conteo["alta_invalida"] += 1
            return
        viejo = libro.ordenes.pop(oid, None)
        if viejo is not None:
            self.conteo["alta_duplicada"] += 1
            libro.sumar(viejo[O_LADO], viejo[O_PRECIO], -viejo[O_TAM])
        snap = bool(flags & F_SNAPSHOT)
        o = self._limbo.pop(oid, None) if snap else None
        if o is not None and o[O_LADO] == lado:                 # sigue viva tras el snapshot
            o[O_PRECIO], o[O_TAM] = precio, tam
        else:
            o = [lado, precio, tam, ts, tam, 0, 0, 0, 0, snap, False]
            if not snap:
                self.qty["añadido"] += tam
                self._n_adds += 1
                self._adds_tam.append(tam)
                if self._n_adds % 500 == 0 and len(self._adds_tam) >= 500:
                    self.umbral_grande = max(self.cfg.min_grande,
                                             float(np.quantile(self._adds_tam, self.cfg.pctl_grande)))
                if tam >= self.umbral_grande:
                    self._nueva_grande(libro, ts, oid, o)
        libro.ordenes[oid] = o
        libro.sumar(lado, precio, tam)
        self._ev_adds.append((lado, precio, tam))

    def _cancelar(self, libro: Libro, ts, lado, precio, tam, oid) -> None:
        o = libro.ordenes.get(oid)
        if o is None:
            self.conteo["huerfana_C"] += 1
            return
        if tam > o[O_TAM]:
            self.conteo["cancelacion_de_mas"] += 1
        q = min(tam, o[O_TAM]) if tam > 0 else o[O_TAM]
        o[O_TAM] -= q
        libro.sumar(o[O_LADO], o[O_PRECIO], -q)
        quitada = o[O_TAM] == 0
        if quitada:
            del libro.ordenes[oid]
        self._ev_red.append((o, q, quitada, oid, o[O_PRECIO]))

    def _modificar(self, libro: Libro, ts, lado, precio, tam, oid) -> None:
        o = libro.ordenes.get(oid)
        if o is None:
            self.conteo["huerfana_M"] += 1
            if lado != 0 and tam > 0 and precio != UNDEF_PRICE:   # la M trae el estado completo
                self.conteo["recuperada_con_M"] += 1
                o = libro.ordenes[oid] = [lado, precio, tam, ts, tam, 0, 0, 0, 0, True, False]
                libro.sumar(lado, precio, tam)
            return
        if precio == UNDEF_PRICE:
            precio = o[O_PRECIO]
        o[O_NMOD] += 1
        if precio != o[O_PRECIO]:
            o[O_NPRECIO] += 1
            libro.sumar(o[O_LADO], o[O_PRECIO], -o[O_TAM])
            if tam < o[O_TAM]:                                   # con cambio de precio no es llenado
                o[O_CANC] += o[O_TAM] - tam
                self.qty["cancelado"] += o[O_TAM] - tam
            elif tam > o[O_TAM]:
                self.qty["añadido"] += tam - o[O_TAM]
            o[O_PRECIO], o[O_TAM] = precio, tam
            if tam > 0:
                libro.sumar(o[O_LADO], precio, tam)
            else:
                del libro.ordenes[oid]
                self._ev_red.append((o, 0, True, oid, precio))
            return
        d = tam - o[O_TAM]
        if d == 0:
            return
        libro.sumar(o[O_LADO], precio, d)
        o[O_TAM] = tam
        if d > 0:
            self.qty["añadido"] += d
        else:
            if tam == 0:
                del libro.ordenes[oid]
            self._ev_red.append((o, -d, tam == 0, oid, precio))

    def _limpiar(self, libro: Libro) -> None:
        self.conteo["limpiezas"] += 1
        self._limbo.update(libro.ordenes)
        libro.ordenes.clear()
        libro.niv = {1: {}, -1: {}}
        libro.mejor = {1: None, -1: None}

    # ------------------------------------------------------------------ eventos
    def mid(self, iid: int | None = None) -> float | None:
        libro = self.libros.get(self.iid if iid is None else iid)
        return libro.mid() if libro is not None else None

    def _abrir_evento(self, ts: int, iid: int) -> None:
        if iid != self.iid and self.iid is not None:
            self.conteo["cambios_de_instrumento"] += 1
            self._sig.append(np.nan)
        # mid de cada segundo (el que regía al empezar ese segundo)
        s = ts // NS
        if self._seg_ult is None:
            self._seg_ult = s
        elif s > self._seg_ult:
            m = self.mid()
            m = np.nan if m is None else m
            hasta = min(s, self._seg_ult + 300)
            for k in range(self._seg_ult + 1, hasta + 1):
                self.seg_t.append(k)
                self.seg_mid.append(m)
                self._sig.append(m)
            if s > hasta:                                       # hueco largo: halt o fin de semana
                self.seg_t.append(s)
                self.seg_mid.append(np.nan)
                self._sig.append(np.nan)
            self._seg_ult = s
        self.iid = iid
        self._ev_abierto, self._ev_ts, self._ev_iid = True, ts, iid
        self._ev_snap = True
        self._ev_mid0 = self.mid(iid)
        if self._raf is not None and ts - self._raf["t_fin"] > self.cfg.gap_ms * NS_MS:
            self._cerrar_rafaga()
        if self._pend:
            self._clasificar_pendientes(ts)

    def _cerrar_evento(self) -> None:
        ts, iid = self._ev_ts, self._ev_iid
        libro = self.libros[iid]
        consumidas = self._atribuir(ts, iid)
        for o, q, quitada, oid, _ in self._ev_red:
            if quitada:
                self._finalizar(o, oid, ts, "llena" if o[O_LLENO] and not o[O_CANC] else
                                "parcial y cancelada" if o[O_LLENO] else "cancelada")
        if self._limbo and not self._ev_snap:
            for oid, o in self._limbo.items():
                self._finalizar(o, oid, ts, "limpieza del libro")
            self._limbo.clear()
        agr = [t for t in self._ev_trades if t[2] != 0]
        if len(agr) < len(self._ev_trades):
            self.conteo["operaciones_sin_agresor"] += len(self._ev_trades) - len(agr)
            self.qty["operado_sin_agresor"] += sum(q for _, q, s_, _ in self._ev_trades if s_ == 0)
        if agr:
            for s in (1, -1):
                pq = [(p, q) for p, q, ss, _ in agr if ss == s]
                if pq:
                    self._evento_agresivo(ts, s, pq, consumidas)
        if self._repos and self._ev_adds:
            for rp in self._repos:
                b, t_lim, lado_p, lo, hi = rp
                if ts <= t_lim:
                    b["_repuesto"] += sum(q for la, p, q in self._ev_adds if la == lado_p and lo <= p <= hi)
        if self._repos:
            self._repos = [rp for rp in self._repos if ts <= rp[1]]
        if self._ev_adds:
            self._altas_rec.extend((ts, la, p, q) for la, p, q in self._ev_adds)
            lim = ts - int((self.cfg.dur_max_ms + 3 * self.cfg.gap_ms) * NS_MS)
            while self._altas_rec and self._altas_rec[0][0] < lim:
                self._altas_rec.popleft()
        m = libro.mid()
        if m is not None and self._pend:
            for b in self._pend:
                if b["_iid"] == iid and ts <= b["t_fin"] + b["_h_ns"]:
                    e = b["lado"] * (m - b["mid0"]) / self.tick
                    b["mfe"] = max(b["mfe"], e)
                    b["mae"] = min(b["mae"], e)
        if self.grandes_vivas:
            self._vigilar_grandes(libro, iid)
        mb, ma = libro.mejor[1], libro.mejor[-1]
        if mb is not None and ma is not None and mb >= ma:
            self.conteo["libro_cruzado"] += 1
        self.conteo["eventos"] += 1
        self._ev_abierto = False
        self._ev_trades, self._ev_fills, self._ev_red, self._ev_adds = [], {}, [], []

    def _atribuir(self, ts: int, iid: int) -> list[tuple]:
        """
        ¿Cuánto de cada reducción fue LLENADO y cuánto cancelación? Con registros F, el F de esa
        orden lo dice. Sin F, el volumen operado de las T del mismo evento en ese precio, del lado
        pasivo, se reparte entre las reducciones en el orden en que llegaron.
        """
        consumidas = []
        vol_t = sum(q for _, q, _, _ in self._ev_trades)
        self.qty["operado"] += vol_t
        if self._ev_fills:
            fills = dict(self._ev_fills)
            for o, q, quitada, oid, p in self._ev_red:
                f = min(q, fills.get(oid, 0))
                if f:
                    fills[oid] -= f
                self._registrar(o, f, q - f, ts, p, quitada, consumidas)
            sobra = sum(v for v in fills.values() if v > 0)
            self.conteo["F_sin_orden_que_baje"] += sobra
            self._resto = None
            return consumidas
        disp = {}
        if self._resto is not None and self._resto[0] == ts and self._resto[1] == iid:
            disp = self._resto[2]
        for p, q, s, _ in self._ev_trades:
            k = (p, -s) if s else (p, 0)
            disp[k] = disp.get(k, 0) + q
        for o, q, quitada, oid, p in self._ev_red:
            f = 0
            if disp:
                k = (p, o[O_LADO])
                f = min(q, disp.get(k, 0))
                if f:
                    disp[k] -= f
                if f < q and disp.get((p, 0), 0) > 0:
                    g = min(q - f, disp[(p, 0)])
                    disp[(p, 0)] -= g
                    f += g
            self._registrar(o, f, q - f, ts, p, quitada, consumidas)
        resto = {k: v for k, v in disp.items() if v > 0}
        self._resto = (ts, iid, resto) if resto else None
        return consumidas

    def _registrar(self, o, f, cq, ts, p, quitada, consumidas) -> None:
        if f:
            o[O_LLENO] += f
            self.qty["llenado"] += f
            consumidas.append((ts - o[O_TADD], o[O_SNAP], quitada))
        if cq:
            o[O_CANC] += cq
            self.qty["cancelado"] += cq
            self._retiros.append((ts, o[O_LADO], p, cq))
            lim = ts - int((self.cfg.ventana_retiro_ms + self.cfg.dur_max_ms + 2 * self.cfg.gap_ms) * NS_MS)
            while self._retiros and self._retiros[0][0] < lim:
                self._retiros.popleft()

    def _finalizar(self, o, oid, ts, motivo: str) -> None:
        self.ciclo[motivo] += 1
        self.ciclo["modificaciones"] += o[O_NMOD]
        self.ciclo["cambios_de_precio"] += o[O_NPRECIO]
        if o[O_SNAP]:
            self.ciclo["edad_desconocida"] += 1
        else:
            vida = (ts - o[O_TADD]) / NS
            k = 0 if vida <= 0 else int((math.log10(vida) + 6.0) / 0.25) + 1
            self.vida[motivo][min(max(k, 0), len(BINS_VIDA))] += 1
            if motivo == "cancelada" and vida * 1000 < self.cfg.fugaz_ms:
                self.ciclo["fugaces"] += 1
        if o[O_GRANDE]:
            self._cerrar_grande(oid, o, ts, motivo)

    # ------------------------------------------------------------------ barridos
    def _evento_agresivo(self, ts: int, s: int, pq: list, consumidas: list) -> None:
        precios = [p for p, _ in pq]
        vol = sum(q for _, q in pq)
        niveles = len(set(precios))
        p_ext = max(precios) if s > 0 else min(precios)
        if niveles >= 2:
            self.exactos.append((ts, s, niveles, vol, precios[0], p_ext))
            if any(s * (b - a) < 0 for a, b in zip(precios, precios[1:])):
                self.conteo["barrido_no_monotono"] += 1
        r = self._raf
        g, dmax = self.cfg.gap_ms * NS_MS, self.cfg.dur_max_ms * NS_MS
        if r is not None and (ts - r["t_fin"] > g or ts - r["t_ini"] > dmax):
            self._cerrar_rafaga()
            r = None
        if r is None:
            r = self._raf = {"t_ini": ts, "t_fin": ts, "mid0": self._ev_mid0, "iid": self._ev_iid,
                             "vol": {1: 0, -1: 0}, "pv": {1: 0, -1: 0}, "precios": {1: [], -1: []},
                             "n": 0, "n_exactos": 0, "edades": [], "consumidas": 0}
        r["t_fin"] = ts
        r["vol"][s] += vol
        r["pv"][s] += sum(p * q for p, q in pq)
        r["precios"][s].extend(precios)
        r["n"] += 1
        r["n_exactos"] += niveles >= 2
        r["edades"].extend(e for e, snap, _ in consumidas if not snap)
        r["consumidas"] += sum(1 for *_, quit in consumidas if quit)

    def _umbral_vol(self) -> float:
        n = len(self._vols_ord)
        if n < self.cfg.min_obs_adapt:
            return float(self.cfg.min_vol)
        return max(float(self.cfg.min_vol), float(self._vols_ord[min(n - 1, int(self.cfg.pctl_vol * n))]))

    def _agregar_vol(self, v: int) -> None:
        """Ventana móvil de las últimas n_adapt ráfagas, siempre ordenada (percentil en O(1))."""
        if len(self._vols) == self._vols.maxlen:
            del self._vols_ord[bisect.bisect_left(self._vols_ord, self._vols[0])]
        self._vols.append(v)
        bisect.insort(self._vols_ord, v)

    def _cerrar_rafaga(self) -> None:
        r, self._raf = self._raf, None
        cfg = self.cfg
        s = 1 if r["vol"][1] >= r["vol"][-1] else -1
        vol_s, total = r["vol"][s], r["vol"][1] + r["vol"][-1]
        umbral = self._umbral_vol()                              # sólo con ráfagas ANTERIORES
        self._agregar_vol(vol_s)
        self.n_rafagas += 1
        ps = r["precios"][s]
        niveles = len(set(ps))
        p_ext = max(ps) if s > 0 else min(ps)
        ticks = s * (p_ext - ps[0]) / self.tick
        pasos = [s * (b - a) for a, b in zip(ps, ps[1:]) if b != a]
        mono = sum(1 for x in pasos if x > 0) / len(pasos) if pasos else 1.0
        pureza = vol_s / total
        if not (niveles >= cfg.min_niveles and ticks >= cfg.min_ticks and pureza >= cfg.pureza_min
                and mono >= cfg.mono_min and vol_s >= umbral):
            return
        self._id += 1
        lo, hi = min(ps[0], p_ext), max(ps[0], p_ext)
        w = int(cfg.ventana_retiro_ms * NS_MS)
        retiro = sum(q for t, la, p, q in self._retiros if la == -s and lo <= p <= hi and r["t_ini"] - w <= t < r["t_ini"])
        edades = sorted(r["edades"])
        b = {"id": self._id, "t_ini": r["t_ini"], "t_fin": r["t_fin"], "lado": s, "vol": vol_s, "vol_total": total,
             "pureza": pureza, "mono": mono, "niveles": niveles, "ticks": ticks, "p_ini": ps[0], "p_ext": p_ext,
             "vwap": r["pv"][s] / vol_s, "mid0": r["mid0"], "n_eventos": r["n"], "n_exactos": r["n_exactos"],
             "consumidas": r["consumidas"],
             "edad_med_ms": edades[len(edades) // 2] / NS_MS if edades else np.nan,
             "retiro": retiro / vol_s, "umbral": umbral, "clase": None,
             "enfriamiento": r["t_ini"] - self._ultimo[s] < cfg.cooldown_s * NS,
             "mfe": 0.0, "mae": 0.0, "_iid": r["iid"],
             "_repuesto": sum(q for t, la, p, q in self._altas_rec if t > r["t_fin"] and la == -s and lo <= p <= hi),
             "_h_ns": int(cfg.horizonte_s * NS)}
        if not b["enfriamiento"]:
            self._ultimo[s] = r["t_fin"]
        self.umbrales.append((r["t_fin"], umbral))
        self.barridos.append(b)
        self._repos.append([b, r["t_fin"] + int(cfg.ventana_repos_ms * NS_MS), -s, lo, hi])
        if b["mid0"] is None:
            b["clase"] = "SIN LIBRO"
            return
        self._pend.append(b)
        if cfg.alerta_inmediata and self.al_barrido is not None and not b["enfriamiento"]:
            self.al_barrido(b, inmediato=True)

    def sigma(self) -> float:
        """Desplazamiento típico del mid en H segundos (ticks): media de |Δ| en la última hora."""
        h = max(1, int(round(self.cfg.horizonte_s)))
        if len(self._sig) < h + 300:
            return np.nan
        a = np.fromiter(self._sig, float)
        d = np.abs(a[h:] - a[:-h])
        d = d[np.isfinite(d)]
        return float(d.mean()) / self.tick if len(d) >= 300 else np.nan

    def _clasificar_pendientes(self, ts: int) -> None:
        listos = [b for b in self._pend if ts > b["t_fin"] + b["_h_ns"]]
        if not listos:
            return
        self._pend = [b for b in self._pend if ts <= b["t_fin"] + b["_h_ns"]]
        sig = self.sigma()
        for b in listos:
            m = self.mid(b["_iid"])
            self._clasificar(b, m, sig)

    def _clasificar(self, b: dict, m: float | None, sig: float) -> None:
        """
        Forense, DESPUÉS del horizonte (sin mirar al futuro: espera a que llegue):
          MOMENTUM       el mid sigue ≥ k_cont·σ más allá del último nivel barrido;
          CAZA DE STOPS  el mid regresa ≥ k_rev·σ detrás de donde estaba ANTES del barrido;
          ABSORCIÓN      ni lo uno ni lo otro, y el lado pasivo repuso ≥ 50 % de lo barrido en 1 s;
          NEUTRAL        el resto.
        σ = desplazamiento típico del mid en H segundos en la última hora, con piso de 1 tick.

        [v1] Tu classify busca el precio 5 s DESPUÉS en el momento de detectar: ese futuro aún no
        existe y sólo encuentra lo que llegó en los milisegundos siguientes. Y su "precio" es el
        de cualquier registro: una alta 30 ticks abajo también cuenta como precio del mercado.
        """
        cfg, s = self.cfg, b["lado"]
        b["repos"] = b.pop("_repuesto", 0) / b["vol"]
        sig_t = sig if np.isfinite(sig) else 1.0
        b["sigma"] = sig_t
        if m is None:
            b["clase"] = "SIN LIBRO"
            return
        cont = s * (m - b["p_ext"]) / self.tick
        ret = s * (m - b["mid0"]) / self.tick
        b["cont"], b["ret"], b["mid_h"] = cont, ret, m
        if cont >= max(1.0, cfg.k_cont * sig_t):
            b["clase"] = "MOMENTUM"
        elif ret <= -max(1.0, cfg.k_rev * sig_t):
            b["clase"] = "CAZA DE STOPS"
        elif b["repos"] >= cfg.reposicion_min:
            b["clase"] = "ABSORCIÓN"
        else:
            b["clase"] = "NEUTRAL"
        if self.al_barrido is not None and not b["enfriamiento"]:
            self.al_barrido(b, inmediato=False)

    # ------------------------------------------------------------------ órdenes grandes
    def _distancia(self, libro: Libro, o) -> float:
        """Ticks entre la orden y el mejor precio del OTRO lado: 1 = el precio ya la toca."""
        op = libro.mejor[-o[O_LADO]]
        if op is None:
            return np.inf
        return o[O_LADO] * (op - o[O_PRECIO]) / self.tick

    def _nueva_grande(self, libro: Libro, ts: int, oid: int, o: list) -> None:
        o[O_GRANDE] = True
        mismo = libro.mejor[o[O_LADO]]
        self.grandes_vivas[oid] = {"oid": oid, "t_add": ts, "lado": o[O_LADO], "precio": o[O_PRECIO],
                                   "tam": o[O_TAM], "umbral": self.umbral_grande,
                                   "atras_del_mejor": (o[O_LADO] * (mismo - o[O_PRECIO]) / self.tick
                                                       if mismo is not None else np.nan),
                                   "dist_min": self._distancia(libro, o), "_o": o, "_iid": self._ev_iid}

    def _vigilar_grandes(self, libro: Libro, iid: int) -> None:
        for g in self.grandes_vivas.values():
            if g["_iid"] == iid:
                d = self._distancia(libro, g["_o"])
                if d < g["dist_min"]:
                    g["dist_min"] = d

    def _cerrar_grande(self, oid: int, o: list, ts: int, motivo: str) -> None:
        g = self.grandes_vivas.pop(oid, None)
        if g is None:
            return
        g.pop("_o")
        g.pop("_iid")
        lleno = o[O_LLENO] / max(1, o[O_TAM0])
        if motivo == "viva al final":
            r = "viva"
        elif lleno >= 0.5:
            r = "ejecutada"
        elif lleno > 0:
            r = "parcial"
        elif g["dist_min"] <= 1:
            r = "retirada al acercarse el precio"
        else:
            r = "retirada lejos del precio"
        g.update(t_fin=ts, vida_s=(ts - g["t_add"]) / NS, llenado=o[O_LLENO], resultado=r,
                 n_mod=o[O_NMOD], n_precio=o[O_NPRECIO])
        self.grandes.append(g)
        if self.al_grande is not None and r != "viva":
            self.al_grande(g)

    # ------------------------------------------------------------------ fin
    def terminar(self) -> None:
        if self._ev_abierto:
            self._cerrar_evento()
        if self._raf is not None:
            self._cerrar_rafaga()
        for b in self._pend:
            b["clase"] = "SIN HORIZONTE"
            b["repos"] = b.pop("_repuesto", 0) / b["vol"]
        self._pend = []
        for b in self.barridos:
            if "_repuesto" in b:
                b["repos"] = b.pop("_repuesto") / b["vol"]
        ts = self._ts_max
        for libro in self.libros.values():
            for oid, o in list(libro.ordenes.items()):
                self.ciclo["viva al final"] += 1
                if o[O_GRANDE]:
                    self._cerrar_grande(oid, o, ts, "viva al final")
        for oid, o in self._limbo.items():
            self._finalizar(o, oid, ts, "limpieza del libro")
        self._limbo.clear()

    def reiniciar_libros(self, ts: int) -> None:
        """Tras una reconexión: el snapshot nuevo reconstruye el libro; lo de antes se cierra."""
        for libro in self.libros.values():
            self._limbo.update(libro.ordenes)
            libro.ordenes.clear()
            libro.niv = {1: {}, -1: {}}
            libro.mejor = {1: None, -1: None}
        self.conteo["reconexiones"] += 1


# =============================================================================
# 4. SIMULADOR — un libro MBO con verdad conocida
# =============================================================================
CHARB = {1: b"B", -1: b"A", 0: b"N"}


class Simulador:
    """
    Un mercado de órdenes límite al estilo de los modelos de "inteligencia cero" (Farmer, Patelli
    y Zovko 2005): altas alrededor de un precio eficiente que camina, cancelaciones con vidas
    mezcladas (muchas fugaces), modificaciones y órdenes de mercado. Escribe registros MBO como
    los de CME en Databento: cada operación es un evento con sus T (lado del agresor), sus F
    (opcionales) y las C/M de las órdenes que se llevó, cerrado con F_LAST.

    Plantados, con su clase VERDADERA:
      · MOMENTUM: un barrido de 3-6 niveles y el precio eficiente salta en su dirección;
      · CAZA DE STOPS: (60 %) retiran liquidez de esos niveles, barren y el precio regresa
        detrás del inicio;
      · ABSORCIÓN: barren 2-3 niveles y un vendedor (o comprador) pasivo repone en el último
        nivel una y otra vez: el precio se queda;
      · RÁFAGA: 4-8 órdenes agresivas a 10-40 ms entre sí, cada una de 2 niveles, y luego momentum.
    Además: órdenes grandes que se retiran cuando el precio se acerca y otras que se ejecutan,
    un snapshot inicial, un roll, operaciones sin agresor, cancelaciones huérfanas y banderas
    F_BAD_TS_RECV.
    """

    def __init__(self, cfg: Config, semilla: int | None = None, fills: bool | None = None, info: bool = True):
        self.cfg = cfg
        self.rng = np.random.default_rng(cfg.sim_semilla if semilla is None else semilla)
        self.tick = tick_int(cfg)
        self.fills = cfg.sim_fills if fills is None else fills
        self.info = info
        self.recs: list[tuple] = []
        self.seq = 0
        self.iid = 7001
        self._oid = int(self.rng.integers(10 ** 9, 2 * 10 ** 9))
        self.ord: dict[int, list] = {}
        self.niv = {1: {}, -1: {}}
        self.mejor = {1: None, -1: None}
        self.heap: list[tuple] = []
        self.esp: list[tuple] = []
        self.n_esp = 0
        ref = CATALOGO.get(raiz(cfg.symbol), ("", 0.0000005, 0.0068))[2]
        self.m = float(round(ref * PRICE_SCALE / self.tick))
        self.sesgo, self.sesgo_hasta = 0.0, 0
        self.absorbe = None
        self.spoofs: dict[int, int] = {}
        self.cerrar_spoof: set[int] = set()
        self.etiqueta: dict[int, str] = {}
        self.verdad = {"barridos": [], "plantados": [], "grandes": {}, "ciclo": Counter(), "huerfanas": 0,
                       "operado": 0, "llenado": 0, "sin_agresor": 0, "libros": {}}
        self.t0 = int(pd.Timestamp(cfg.start, tz="UTC").value) + 2 * 3600 * NS

    # ------------------------------------------------------------------ registros
    def _evento(self, ts: int, regs: list[tuple]) -> None:
        lat = int(self.rng.integers(20_000, 200_000))
        ult = len(regs) - 1
        for j, (a, l_, p, q, o, f) in enumerate(regs):
            if j == ult:
                f |= F_LAST
            if self.rng.random() < 0.001:
                f |= F_BAD_TS_RECV
            self.seq += 1
            self.recs.append((ts, ts + lat, o, UNDEF_PRICE if p is None else p * self.tick, q, f, a, l_,
                              self.iid, self.seq))

    def _nuevo_oid(self) -> int:
        self._oid += int(self.rng.integers(1, 40))
        return self._oid

    def _recalcular(self, lado: int) -> None:
        d = self.niv[lado]
        self.mejor[lado] = (max(d) if lado > 0 else min(d)) if d else None

    def mid(self) -> float | None:
        b, a = self.mejor[1], self.mejor[-1]
        return (b + a) / 2 if b is not None and a is not None else None

    def _poner(self, ts, lado, precio, tam, vida, regs=None, snap=False) -> int:
        oid = self._nuevo_oid()
        self.ord[oid] = [lado, precio, tam, ts, 0, 0]
        d = self.niv[lado].get(precio)
        if d is None:
            d = self.niv[lado][precio] = deque()
        d.append(oid)
        m = self.mejor[lado]
        if m is None or lado * (precio - m) > 0:
            self.mejor[lado] = precio
        reg = (b"A", CHARB[lado], precio, tam, oid, F_SNAPSHOT if snap else 0)
        if regs is None:
            self._evento(ts, [reg])
        else:
            regs.append(reg)
        if vida < math.inf:
            heapq.heappush(self.heap, (ts + int(vida * NS), oid))
        return oid

    def _sacar(self, oid: int) -> list:
        o = self.ord.pop(oid)
        d = self.niv[o[0]][o[1]]
        d.remove(oid)
        if not d:
            del self.niv[o[0]][o[1]]
            if self.mejor[o[0]] == o[1]:
                self._recalcular(o[0])
        return o

    def _fin(self, oid: int, o: list, motivo: str | None = None) -> None:
        if motivo is None:
            motivo = "llena" if o[4] and not o[5] else "parcial y cancelada" if o[4] else "cancelada"
        self.verdad["ciclo"][motivo] += 1
        if oid in self.verdad["grandes"]:
            self.verdad["grandes"][oid]["motivo"] = motivo
            self.verdad["grandes"][oid]["llenado"] = o[4]

    def _cancelar(self, ts: int, oid: int) -> None:
        if oid not in self.ord:
            return
        o = self.ord[oid]
        if self.rng.random() < 0.05 and o[2] > 1:                 # reducción parcial con M
            nuevo = int(self.rng.integers(1, o[2]))
            o[5] += o[2] - nuevo
            o[2] = nuevo
            self._evento(ts, [(b"M", CHARB[o[0]], o[1], nuevo, oid, 0)])
            heapq.heappush(self.heap, (ts + int(self.rng.exponential(10) * NS), oid))
            return
        o = self._sacar(oid)
        o[5] += o[2]
        self._evento(ts, [(b"C", CHARB[o[0]], o[1], o[2], oid, 0)])
        self._fin(oid, o)
        self.spoofs.pop(oid, None)

    def _mover(self, ts: int, oid: int) -> None:
        """Cancelar y reemplazar a otro precio con M: pierde su lugar en la fila."""
        if oid not in self.ord:
            return
        o = self._sacar(oid)
        nuevo = o[1] - o[0] * int(self.rng.integers(1, 3))
        o[1] = nuevo
        self.ord[oid] = o
        self.niv[o[0]].setdefault(nuevo, deque()).append(oid)
        m = self.mejor[o[0]]
        if m is None or o[0] * (nuevo - m) > 0:
            self.mejor[o[0]] = nuevo
        self._evento(ts, [(b"M", CHARB[o[0]], nuevo, o[2], oid, 0)])

    # ------------------------------------------------------------------ agresión
    def agresion(self, ts: int, s: int, qty: int) -> tuple | None:
        op = -s
        rT, rF, rCM = [], [], []
        resto, niveles, p_ini, p_fin = qty, 0, None, None
        while resto > 0 and self.mejor[op] is not None:
            bp = self.mejor[op]
            d = self.niv[op][bp]
            nivel = 0
            while resto > 0 and d:
                oid = d[0]
                o = self.ord[oid]
                f = min(resto, o[2])
                resto -= f
                nivel += f
                o[2] -= f
                o[4] += f
                if self.fills:
                    rF.append((b"F", CHARB[op], bp, f, oid, 0))
                if o[2] == 0:
                    rCM.append((b"C", CHARB[op], bp, f, oid, 0))
                    d.popleft()
                    del self.ord[oid]
                    self._fin(oid, o)
                    self.spoofs.pop(oid, None)
                else:
                    rCM.append((b"M", CHARB[op], bp, o[2], oid, 0))
            if not d:
                del self.niv[op][bp]
                self._recalcular(op)
            rT.append((b"T", CHARB[s], bp, nivel, 0, 0))
            niveles += 1
            p_ini = bp if p_ini is None else p_ini
            p_fin = bp
        if not rT:
            return None
        self._evento(ts, rT + rF + rCM)
        ejecutado = qty - resto
        self.verdad["operado"] += ejecutado
        self.verdad["llenado"] += ejecutado
        if niveles >= 2:
            self.verdad["barridos"].append((ts, s, niveles, ejecutado, p_ini * self.tick, p_fin * self.tick))
        if self.rng.random() < 0.005:                          # operación implícita: sin agresor
            m = self.mid()
            if m is not None:
                q = int(self.rng.integers(1, 4))
                self._evento(ts + 1000, [(b"T", b"N", int(m), q, 0, 0)])
                self.verdad["sin_agresor"] += 1
                self.verdad["operado"] += q
        return niveles, p_ini, p_fin, ejecutado

    def barrer(self, ts: int, s: int, k: int) -> tuple | None:
        precios = sorted(self.niv[-s], reverse=s < 0)[:k]
        qty = sum(self.ord[o][2] for p in precios for o in self.niv[-s][p])
        return self.agresion(ts, s, qty) if qty else None

    # ------------------------------------------------------------------ flujo normal
    def _alta_aleatoria(self, ts: int) -> None:
        rng = self.rng
        lado = 1 if rng.random() < 0.5 else -1
        g = min(int(rng.geometric(0.4)) - 1, 20)
        if lado > 0:
            tope = math.floor(self.m)
            if self.mejor[-1] is not None:
                tope = min(tope, self.mejor[-1] - 1)
            precio = tope - g
        else:
            piso = math.ceil(self.m)
            if self.mejor[1] is not None:
                piso = max(piso, self.mejor[1] + 1)
            precio = piso + g
        tam = int(rng.geometric(0.45))
        if rng.random() < 0.03:
            tam *= int(rng.integers(5, 15))
        u = rng.random()
        vida = rng.exponential(0.06) if u < 0.35 else rng.exponential(15) if u < 0.9 else rng.exponential(300)
        oid = self._poner(ts, lado, precio, tam, vida)
        if rng.random() < 0.03:
            heapq.heappush(self.esp, (ts + int(rng.exponential(5) * NS), self._n(), "mover", oid))

    def _n(self) -> int:
        self.n_esp += 1
        return self.n_esp

    def _mercado(self, ts: int) -> None:
        rng = self.rng
        m = self.mid()
        sesgo = self.sesgo if ts < self.sesgo_hasta else 0.0
        p = 0.5 + (min(max(0.15 * (self.m - m), -0.35), 0.35) if m is not None else 0.0) + sesgo
        s = 1 if rng.random() < min(max(p, 0.05), 0.95) else -1
        q = int(rng.geometric(0.3))
        if rng.random() < 0.02:
            q *= int(rng.integers(4, 10))
        self.agresion(ts, s, q)

    def _mantener(self, ts: int) -> None:
        """Lo que reacciona al libro: el absorbente repone y las órdenes 'spoof' se retiran."""
        a = self.absorbe
        if a is not None:
            if ts > a["hasta"]:
                self.absorbe = None
            else:
                d = self.niv[a["lado"]].get(a["precio"])
                hay = sum(self.ord[o][2] for o in d) if d else 0
                op = self.mejor[-a["lado"]]
                cruza = op is not None and a["lado"] * (op - a["precio"]) <= 0
                if hay < a["Q"] and not cruza:
                    self._poner(ts + 1000, a["lado"], a["precio"], a["Q"] - hay, rng_vida(self.rng))
        for oid in list(self.spoofs):
            o = self.ord.get(oid)
            if o is None:
                self.spoofs.pop(oid)
                continue
            op = self.mejor[-o[0]]
            if (op is not None and o[0] * (op - o[1]) <= 1 or ts > self.spoofs[oid]) and oid not in self.cerrar_spoof:
                self.cerrar_spoof.add(oid)
                heapq.heappush(self.esp, (ts + int(self.rng.integers(1, 5)) * NS_MS, self._n(), "retirar", oid))

    # ------------------------------------------------------------------ plantados
    def _plantar(self, ts: int) -> None:
        rng = self.rng
        tipo = ["momentum", "caza", "absorcion", "rafaga"][int(rng.integers(0, 4))]
        d = 1 if rng.random() < 0.5 else -1
        mid0 = self.mid()
        if mid0 is None:
            return
        if tipo == "caza":
            k = int(rng.integers(3, 7))
            if rng.random() < 0.6:
                for p in sorted(self.niv[-d], reverse=d < 0)[:k]:
                    for oid in list(self.niv[-d].get(p, ())):
                        if rng.random() < 0.6:
                            o = self._sacar(oid)
                            o[5] += o[2]
                            self._evento(ts, [(b"C", CHARB[o[0]], o[1], o[2], oid, 0)])
                            self._fin(oid, o)
            heapq.heappush(self.esp, (ts + int(rng.integers(100, 400)) * NS_MS, self._n(), "caza", (d, k, mid0)))
        elif tipo == "rafaga":
            n = int(rng.integers(4, 9))
            t = ts
            for j in range(n):
                heapq.heappush(self.esp, (t, self._n(), "golpe", (d, j == n - 1, ts, mid0)))
                t += int(rng.integers(10, 40)) * NS_MS
        else:
            heapq.heappush(self.esp, (ts, self._n(), tipo, (d, mid0)))

    def _especial(self, ts: int, tipo: str, dato) -> None:
        rng = self.rng
        if tipo == "retirar":
            self.cerrar_spoof.discard(dato)
            if dato in self.ord:
                self._cancelar_total(ts, dato)
        elif tipo == "mover":
            self._mover(ts, dato)
        elif tipo in ("momentum", "absorcion"):
            d, mid0 = dato
            k = int(rng.integers(3, 7)) if tipo == "momentum" else int(rng.integers(3, 5))
            r = self.barrer(ts, d, k)
            if r is None or r[0] < 2:
                return
            if tipo == "momentum":
                self.m = r[2] + d * rng.uniform(2, 5)
                self.sesgo, self.sesgo_hasta = 0.3 * d, ts + int(rng.uniform(20, 60) * NS)
                self._desvanecer(ts)
                self._plantado(ts, ts, d, "MOMENTUM", r)
            else:
                Q = max(10, int(round(0.6 * r[3])))
                self.absorbe = {"lado": -d, "precio": r[2], "Q": Q, "hasta": ts + int(rng.uniform(15, 30) * NS)}
                self.m = float(r[2])
                self.sesgo, self.sesgo_hasta = 0.2 * d, self.absorbe["hasta"]
                self._plantado(ts, ts, d, "ABSORCIÓN", r)
        elif tipo == "caza":
            d, k, mid0 = dato
            r = self.barrer(ts, d, k)
            if r is None or r[0] < 2:
                return
            self.m = mid0 - d * rng.uniform(2, 4)
            self.sesgo, self.sesgo_hasta = -0.3 * d, ts + int(rng.uniform(20, 40) * NS)
            self._desvanecer(ts)
            self._plantado(ts, ts, d, "CAZA DE STOPS", r)
        elif tipo == "golpe":
            d, ultimo, t_ini, mid0 = dato
            p = self.mejor[-d]
            if p is None:
                return
            q = sum(self.ord[o][2] for o in self.niv[-d][p]) + int(rng.integers(1, 4))
            r = self.agresion(ts, d, q)
            if ultimo and r is not None:
                self.m = r[2] + d * rng.uniform(2, 5)
                self.sesgo, self.sesgo_hasta = 0.3 * d, ts + int(rng.uniform(20, 60) * NS)
                self._desvanecer(ts)
                self._plantado(t_ini, ts, d, "MOMENTUM", r, rafaga=True)

    def _desvanecer(self, ts: int) -> None:
        """
        Tras un salto del precio eficiente, los creadores de mercado retiran en 20-800 ms las
        cotizaciones que quedaron del lado equivocado (las que ahora regalarían dinero).
        """
        for lado in (1, -1):
            for p in list(self.niv[lado]):
                if lado * (p - self.m) > 0:                 # compra arriba del valor / venta abajo
                    for oid in list(self.niv[lado][p]):
                        if oid not in self.spoofs and oid not in self.cerrar_spoof:
                            self.cerrar_spoof.add(oid)
                            heapq.heappush(self.esp, (ts + int(self.rng.integers(20, 800)) * NS_MS, self._n(),
                                                      "retirar", oid))

    def _cancelar_total(self, ts: int, oid: int) -> None:
        o = self._sacar(oid)
        o[5] += o[2]
        self._evento(ts, [(b"C", CHARB[o[0]], o[1], o[2], oid, 0)])
        self._fin(oid, o)
        self.spoofs.pop(oid, None)

    def _plantado(self, t_ini, t_fin, d, clase, r, rafaga=False) -> None:
        self.verdad["plantados"].append({"t_ini": t_ini, "t_fin": t_fin, "lado": d, "clase": clase,
                                         "niveles": r[0], "rafaga": rafaga})

    def _grande(self, ts: int, retirar: bool) -> None:
        rng = self.rng
        lado = 1 if rng.random() < 0.5 else -1
        mismo = self.mejor[lado]
        if mismo is None:
            return
        tam = int(rng.integers(80, 151))
        if retirar:
            oid = self._poner(ts, lado, mismo - lado, tam, math.inf)
            self.spoofs[oid] = ts + 120 * NS
        else:
            oid = self._poner(ts, lado, mismo, tam, 600)
        self.verdad["grandes"][oid] = {"tipo": "retirada" if retirar else "genuina", "t": ts, "lado": lado}

    def _snapshot(self, ts: int) -> None:
        regs = [(b"R", b"N", None, 0, 0, F_SNAPSHOT)]
        centro = round(self.m)
        for lado in (1, -1):
            for k in range(12):
                p = centro - lado * (k + 1) if lado > 0 else centro + k + 1
                for _ in range(int(self.rng.integers(2, 6))):
                    self._poner(ts, lado, p, int(self.rng.geometric(0.4)), self.rng.exponential(300), regs, snap=True)
        self._evento(ts, regs)

    # ------------------------------------------------------------------ el reloj
    def correr(self, horas: float | None = None) -> tuple[np.ndarray, dict]:
        cfg, rng = self.cfg, self.rng
        horas = cfg.sim_horas if horas is None else horas
        t = self.t0
        fin = t + int(horas * 3600 * NS)
        t_roll = t + int(0.6 * horas * 3600 * NS)
        self._snapshot(t)
        la, lm = cfg.sim_tasa, 0.8
        sig = {"alta": t + int(rng.exponential(1 / la) * NS), "mercado": t + int(rng.exponential(1 / lm) * NS),
               "plantar": t + int(rng.exponential(cfg.sim_cada_min * 60) * NS) if self.info else math.inf,
               "retirada": t + int(rng.uniform(180, 480) * NS), "genuina": t + int(rng.uniform(240, 600) * NS),
               "huerfana": t + int(rng.exponential(600) * NS), "roll": t_roll}
        ultimo = t
        while True:
            tc = self.heap[0][0] if self.heap else math.inf
            te = self.esp[0][0] if self.esp else math.inf
            clave = min(sig, key=sig.get)
            t = min(sig[clave], tc, te)
            if t >= fin:
                break
            self.m += rng.normal() * 0.15 * math.sqrt(max(t - ultimo, 0) / NS)
            ultimo = t
            if t == tc:
                _, oid = heapq.heappop(self.heap)
                if oid in self.ord and oid not in self.spoofs:
                    self._cancelar(t, oid)
            elif t == te:
                _, _, tipo, dato = heapq.heappop(self.esp)
                self._especial(t, tipo, dato)
            elif clave == "alta":
                self._alta_aleatoria(t)
                sig["alta"] = t + max(1, int(rng.exponential(1 / la) * NS))
            elif clave == "mercado":
                self._mercado(t)
                sig["mercado"] = t + max(1, int(rng.exponential(1 / lm) * NS))
            elif clave == "plantar":
                self._plantar(t)
                sig["plantar"] = t + int(rng.exponential(cfg.sim_cada_min * 60) * NS)
            elif clave in ("retirada", "genuina"):
                self._grande(t, clave == "retirada")
                sig[clave] = t + int(rng.uniform(180, 480) * NS) if clave == "retirada" else t + int(rng.uniform(240, 600) * NS)
            elif clave == "huerfana":
                self._evento(t, [(b"C", b"B", int(self.m) - 3, 1, 999_999_999_999 + self.verdad["huerfanas"], 0)])
                self.verdad["huerfanas"] += 1
                sig["huerfana"] = t + int(rng.exponential(600) * NS)
            elif clave == "roll":
                self.verdad["libros"][self.iid] = {oid: (o[0], o[1] * self.tick, o[2]) for oid, o in self.ord.items()}
                self.verdad["ciclo"]["viva al final"] += len(self.ord)
                self.iid += 1
                self.ord, self.niv, self.mejor = {}, {1: {}, -1: {}}, {1: None, -1: None}
                self.heap, self.spoofs, self.absorbe = [], {}, None
                self.esp = [e for e in self.esp if e[2] not in ("retirar", "mover")]
                heapq.heapify(self.esp)
                self._snapshot(t)
                sig["roll"] = math.inf
            self._mantener(t)
        self.verdad["libros"][self.iid] = {oid: (o[0], o[1] * self.tick, o[2]) for oid, o in self.ord.items()}
        self.verdad["ciclo"]["viva al final"] += len(self.ord)
        arr = np.array(self.recs, dtype=DTYPE_MBO)
        return arr, self.verdad


def rng_vida(rng) -> float:
    return rng.exponential(60)


def simular(cfg: Config, horas: float | None = None, semilla: int | None = None, fills: bool | None = None,
            info: bool = True) -> tuple[np.ndarray, dict]:
    return Simulador(cfg, semilla, fills, info).correr(horas)


def a_dbn(arr: np.ndarray, cfg: Config) -> bytes:
    """Arreglo simulado → archivo DBN MBO de verdad (para probar la ruta de Databento)."""
    import databento_dbn as dd
    acc = {b"A": dd.Action.ADD, b"C": dd.Action.CANCEL, b"M": dd.Action.MODIFY, b"T": dd.Action.TRADE,
           b"F": dd.Action.FILL, b"R": dd.Action.CLEAR, b"N": dd.Action.NONE}
    lado = {b"B": dd.Side.BID, b"A": dd.Side.ASK, b"N": dd.Side.NONE}
    meta = dd.Metadata(dataset=cfg.dataset, start=int(arr["ts_event"][0]), stype_in=dd.SType.CONTINUOUS,
                       stype_out=dd.SType.INSTRUMENT_ID, schema=dd.Schema.MBO, symbols=[cfg.symbol],
                       partial=[], not_found=[], mappings=[], end=int(arr["ts_event"][-1]) + NS)
    partes = [bytes(meta.encode())]
    for r in arr:
        partes.append(bytes(dd.MBOMsg(publisher_id=1, instrument_id=int(r["instrument_id"]),
                                      ts_event=int(r["ts_event"]), order_id=int(r["order_id"]),
                                      price=int(r["price"]), size=int(r["size"]), action=acc[bytes(r["action"])],
                                      side=lado[bytes(r["side"])], ts_recv=int(r["ts_recv"]), flags=int(r["flags"]),
                                      channel_id=0, ts_in_delta=0, sequence=int(r["sequence"]))))
    return b"".join(partes)


# =============================================================================
# 5. EL CÁLCULO COMPLETO Y LA AUDITORÍA
# =============================================================================
COLS_BARRIDO = ["id", "t_ini", "t_fin", "lado", "clase", "vol", "vol_total", "niveles", "ticks", "pureza", "mono",
                "n_eventos", "n_exactos", "consumidas", "edad_med_ms", "retiro", "repos", "umbral", "sigma",
                "cont", "ret", "mfe", "mae", "p_ini", "p_ext", "vwap", "mid0", "mid_h", "enfriamiento"]


@dataclass
class Resultado:
    cfg: Config
    motor: Rastreador
    barridos: pd.DataFrame
    grandes: pd.DataFrame
    tuyo: pd.DataFrame
    mid: pd.Series
    estudio: pd.DataFrame
    comparacion: dict
    cordura: list
    paridad: dict | None
    segundos: float
    verdad: dict | None = None
    medicion: dict | None = None


def tabla_barridos(motor: Rastreador) -> pd.DataFrame:
    df = pd.DataFrame([{k: b.get(k, np.nan) for k in COLS_BARRIDO} for b in motor.barridos], columns=COLS_BARRIDO)
    for c in ("t_ini", "t_fin"):
        df[c] = pd.to_datetime(df[c].astype("int64"), utc=True)
    for c in ("p_ini", "p_ext", "vwap", "mid0", "mid_h"):
        df[c] = df[c].astype(float) / PRICE_SCALE
    df["direccion"] = np.where(df["lado"] > 0, "COMPRA", "VENTA")
    return df.set_index("id")


def tabla_grandes(motor: Rastreador) -> pd.DataFrame:
    cols = ["oid", "t_add", "t_fin", "lado", "precio", "tam", "llenado", "resultado", "vida_s", "atras_del_mejor",
            "dist_min", "n_mod", "n_precio", "umbral"]
    df = pd.DataFrame([{k: g.get(k, np.nan) for k in cols} for g in motor.grandes], columns=cols)
    for c in ("t_add", "t_fin"):
        df[c] = pd.to_datetime(df[c].astype("int64"), utc=True)
    df["precio"] = df["precio"].astype(float) / PRICE_SCALE
    return df


def serie_mid(motor: Rastreador) -> pd.Series:
    s = pd.Series(np.asarray(motor.seg_mid, float) / PRICE_SCALE,
                  index=pd.to_datetime(np.asarray(motor.seg_t, np.int64) * NS, utc=True), name="mid")
    return s[~s.index.duplicated(keep="last")]


def estudio_eventos(motor: Rastreador, antes: int = 30, despues: int = 60) -> pd.DataFrame:
    """Camino medio del mid (ticks a favor del barrido) de −30 a +60 s, por clase."""
    if not motor.barridos or not motor.seg_t:
        return pd.DataFrame()
    seg = np.asarray(motor.seg_t, np.int64)
    mid = np.asarray(motor.seg_mid, float)
    tau = np.arange(-antes, despues + 1)
    filas = []
    for b in motor.barridos:
        if b.get("clase") not in CLASES or b["mid0"] is None:
            continue
        objetivo = b["t_fin"] // NS + 1 + tau
        i = np.clip(np.searchsorted(seg, objetivo), 0, len(seg) - 1)
        v = np.where(seg[i] == objetivo, mid[i], np.nan)
        filas.append(pd.Series(b["lado"] * (v - b["mid0"]) / motor.tick, index=tau, name=b["clase"]))
    if not filas:
        return pd.DataFrame()
    return pd.DataFrame(filas)


def comparar_tuyo(motor: Rastreador) -> tuple[pd.DataFrame, dict]:
    tu = pd.DataFrame(motor.tuyo.salida if motor.tuyo else [],
                      columns=["t_ini", "t_fin", "lado", "vol", "compra", "venta", "niveles", "ticks", "pureza"])
    tol = int(motor.cfg.gap_ms * NS_MS)
    mios = [b for b in motor.barridos if not b["enfriamiento"]]
    coinc, razones = 0, []
    for r in tu.itertuples():
        c = [b for b in motor.barridos if b["lado"] == r.lado and b["t_ini"] <= r.t_fin + tol and b["t_fin"] >= r.t_ini - tol]
        if c:
            coinc += 1
            razones.append(r.vol / c[0]["vol_total"])
    vistos = sum(1 for b in mios if len(tu) and ((tu["lado"] == b["lado"]) & (tu["t_ini"] <= b["t_fin"] + tol)
                                                  & (tu["t_fin"] >= b["t_ini"] - tol)).any())
    comp = {"tuyas": len(tu), "coinciden": coinc, "razon_vol": float(np.median(razones)) if razones else np.nan,
            "mios": len(mios), "vistos_por_tuyo": vistos}
    for c in ("t_ini", "t_fin"):
        tu[c] = pd.to_datetime(tu[c].astype("int64"), utc=True)
    return tu, comp


def paridad(tienda, cfg: Config, maximo: int = 200_000) -> dict | None:
    """La ruta de Live (registro por registro, MBOMsg) contra la de bloques, en los primeros registros."""
    if not hasattr(tienda, "to_ndarray"):
        return None
    a = Rastreador(cfg, con_tuyo=False)
    b = Rastreador(cfg, con_tuyo=False)
    arr = next(iter(tienda.to_ndarray(count=maximo)))
    a.procesar_arreglo(arr)
    n = 0
    for r in tienda:
        if type(r).__name__ == "MBOMsg":
            b.procesar_registro(r)
            n += 1
            if n >= len(arr):
                break
    a.terminar()
    b.terminar()
    igual = (a.conteo == b.conteo and a.ciclo == b.ciclo and a.exactos == b.exactos and a.qty == b.qty
             and {i: lb.ordenes for i, lb in a.libros.items()} == {i: lb.ordenes for i, lb in b.libros.items()})
    return {"registros": n, "igual": bool(igual), "barridos": len(a.exactos)}


def chequeos(motor: Rastreador, par: dict | None) -> list[tuple[bool, str]]:
    c, q = motor.conteo, motor.qty
    out = []
    ev = max(1, c["eventos"])
    out.append((c["libro_cruzado"] <= 0.001 * ev,
                f"libro cruzado o trabado al cierre de un evento: {c['libro_cruzado']:,} de {ev:,}"))
    cm = max(1, c["C"] + c["M"])
    h = c["huerfana_C"] + c["huerfana_M"]
    out.append((h <= 0.001 * cm, f"cancelaciones/modificaciones de órdenes desconocidas: {h:,} ({h / cm:.3%})"
                + ("" if h <= 0.001 * cm else " → empieza en la apertura semanal o usa --live (con snapshot)")))
    agr = q["operado"] - q["operado_sin_agresor"]
    out.append((q["llenado"] >= 0.99 * agr if agr else True,
                f"volumen operado con su orden en reposo identificada: {q['llenado'] / agr:.2%}" if agr
                else "sin operaciones"))
    out.append((c["eventos_sin_F_LAST"] == 0, f"eventos que no cierran con F_LAST: {c['eventos_sin_F_LAST']:,}"))
    out.append((c["barrido_no_monotono"] == 0,
                f"barridos de un solo agresor con precio que retrocede: {c['barrido_no_monotono']:,}"))
    out.append((c["ts_retrocede"] == 0 and c["libro_dudoso"] == 0,
                f"ts_event que retrocede: {c['ts_retrocede']:,} · banderas F_MAYBE_BAD_BOOK: {c['libro_dudoso']:,}"))
    out.append((True, f"registros F (llenados por orden) en tus datos: {c['F']:,}"
                      + (" → tu agregador los suma a las T" if c["F"] else "")))
    if par is not None:
        out.append((par["igual"], f"ruta de Live (registro por registro) = ruta de bloques en {par['registros']:,} registros"))
    return out


def analizar(tienda, cfg: Config, verdad: dict | None = None, chequear_paridad: bool = True,
             verbose: bool = True) -> Resultado:
    validar(cfg)
    t0 = time.perf_counter()
    motor = Rastreador(cfg)
    n = 0
    for arr in bloques(tienda, cfg):
        if len(arr):
            motor.procesar_arreglo(arr)
            n += len(arr)
            if verbose and n >= 5_000_000 and n % 5_000_000 < len(arr):
                print(f"   … {n:,} registros")
    motor.terminar()
    seg = time.perf_counter() - t0
    if not motor.conteo["registros"]:
        sys.exit("❌ No llegaron registros MBO.")
    par = paridad(tienda, cfg) if chequear_paridad else None
    tu, comp = comparar_tuyo(motor)
    res = Resultado(cfg=cfg, motor=motor, barridos=tabla_barridos(motor), grandes=tabla_grandes(motor), tuyo=tu,
                    mid=serie_mid(motor), estudio=estudio_eventos(motor), comparacion=comp,
                    cordura=chequeos(motor, par), paridad=par, segundos=seg, verdad=verdad)
    if verdad is not None:
        res.medicion = medir_contra_verdad(res)
    return res


def medir_contra_verdad(res: Resultado) -> dict:
    v, m = res.verdad, res.motor
    tol = 60 * NS_MS
    conf, det, bien = Counter(), 0, 0
    for p in v["plantados"]:
        c = [b for b in m.barridos if b["lado"] == p["lado"] and b["t_ini"] <= p["t_fin"] + tol
             and b["t_fin"] >= p["t_ini"] - tol]
        k = c[0]["clase"] if c else "NO DETECTADO"
        conf[(p["clase"], k)] += 1
        det += bool(c)
        bien += k == p["clase"]
    gr = {g["oid"]: g["resultado"] for g in m.grandes}
    gconf = Counter((g["tipo"], gr.get(o, "no marcada")) for o, g in v["grandes"].items())
    libros = all({o: (x[O_LADO], x[O_PRECIO], x[O_TAM]) for o, x in m.libros[i].ordenes.items()} == lib
                 for i, lib in v["libros"].items())
    ex = sorted(e[:4] for e in m.exactos) == sorted(e[:4] for e in v["barridos"])
    return {"plantados": len(v["plantados"]), "detectados": det, "bien": bien, "confusion": conf,
            "grandes": gconf, "libro_identico": libros, "exactos_iguales": ex,
            "ciclo_igual": all(m.ciclo[k] == v["ciclo"][k] for k in MOTIVOS),
            "llenado": (m.qty["llenado"], v["llenado"]), "huerfanas": (m.conteo["huerfana_C"], v["huerfanas"])}


# =============================================================================
# 6. REPORTES
# =============================================================================
def _hora(t, cfg: Config, ms: bool = False) -> str:
    t = pd.Timestamp(t)
    f = "%a %d-%m %H:%M:%S" + (".%f" if ms else "")
    a = t.tz_convert(cfg.tz_mercado).strftime(f)
    return f"{a[:-3] if ms else a} CT / {t.tz_convert(cfg.tz_local):%H:%M:%S} CDMX"


def _precio(p: float, cfg: Config) -> str:
    dec = max(0, -int(math.floor(math.log10(tick_de(cfg))))) if tick_de(cfg) < 1 else 2
    return f"{p:,.{dec}f}"


def vida_mediana(conteos: np.ndarray) -> float:
    if conteos.sum() == 0:
        return np.nan
    k = int(np.searchsorted(np.cumsum(conteos), conteos.sum() / 2))
    return 10 ** (BINS_VIDA[min(max(k - 1, 0), len(BINS_VIDA) - 1)] + 0.125)


def _segundos(x: float) -> str:
    if not np.isfinite(x):
        return "—"
    return f"{x * 1000:.0f} ms" if x < 1 else f"{x:.1f} s" if x < 120 else f"{x / 60:.1f} min"


def reporte_datos(res: Resultado) -> None:
    cfg, m = res.cfg, res.motor
    c = m.conteo
    _titulo("1 · DATOS Y LIBRO (MBO, orden por orden)")
    print(f"  {cfg.symbol} ({nombre(cfg.symbol)}) · tick {_precio(tick_de(cfg), cfg)} · {c['registros']:,} registros en "
          f"{c['eventos']:,} eventos · {len(m.libros)} instrumento(s) · {res.segundos:.1f} s")
    print("  Acciones: " + " · ".join(f"{a} {c[a]:,}" for a in "ACMRTFN"))
    if m.lat:
        lat = np.percentile(m.lat, [50, 99]) / 1000
        print(f"  Latencia ts_recv − ts_event: mediana {lat[0]:,.0f} µs · p99 {lat[1]:,.0f} µs "
              f"({c['ts_recv_malo']:,} registros con F_BAD_TS_RECV)")
    print(f"  Snapshot: {c['snapshot']:,} registros · limpiezas (R): {c['limpiezas']:,} · órdenes huérfanas: "
          f"{c['huerfana_C'] + c['huerfana_M']:,} (recuperadas con su M: {c['recuperada_con_M']:,})")
    vivas = sum(len(lb.ordenes) for lb in m.libros.values())
    lb = m.libros.get(m.iid)
    if lb is not None and lb.mejor[1] is not None and lb.mejor[-1] is not None:
        print(f"  Libro al final: {vivas:,} órdenes vivas · mejor compra {_precio(lb.mejor[1] / PRICE_SCALE, cfg)} "
              f"({lb.niv[1][lb.mejor[1]]:,}) · mejor venta {_precio(lb.mejor[-1] / PRICE_SCALE, cfg)} "
              f"({lb.niv[-1][lb.mejor[-1]]:,})")


def reporte_ciclo(res: Resultado) -> None:
    m = res.motor
    ci, q = m.ciclo, m.qty
    _titulo("2 · CICLO DE VIDA DE LAS ÓRDENES (por order_id)")
    tot = sum(ci[k] for k in MOTIVOS)
    for k in MOTIVOS:
        med = vida_mediana(m.vida[k]) if k != "viva al final" else np.nan
        print(f"  {k:<22s}{ci[k]:>12,}  {ci[k] / max(1, tot):6.1%}   vida mediana {_segundos(med)}")
    canc = ci["cancelada"]
    print(f"  Fugaces (canceladas sin ejecutarse antes de {res.cfg.fugaz_ms:.0f} ms): {ci['fugaces']:,} "
          f"= {ci['fugaces'] / max(1, canc):.1%} de las canceladas")
    print(f"  Contratos: añadidos {q['añadido']:,} · llenados {q['llenado']:,} ({q['llenado'] / max(1, q['añadido']):.1%}) · "
          f"cancelados {q['cancelado']:,} · cancelado / llenado = {q['cancelado'] / max(1, q['llenado']):.1f}")
    print(f"  Modificaciones por orden: {ci['modificaciones'] / max(1, tot):.2f} · cambios de precio (pierden la fila): "
          f"{ci['cambios_de_precio']:,} · edad desconocida (snapshot o M): {ci['edad_desconocida']:,}")


def reporte_barridos(res: Resultado) -> None:
    cfg, m, B = res.cfg, res.motor, res.barridos
    _titulo("3 · BARRIDOS DE LIQUIDEZ")
    n_ex = len(m.exactos)
    print(f"  {m.n_rafagas:,} ráfagas agresivas (golpes a ≤ {cfg.gap_ms:.0f} ms) · {n_ex:,} eventos de UN agresor que "
          f"cruzaron ≥ 2 niveles")
    print(f"  Califican como barrido: ≥ {cfg.min_niveles} niveles, ≥ {cfg.min_ticks} ticks, pureza ≥ {cfg.pureza_min:.0%}, "
          f"monotonicidad ≥ {cfg.mono_min:.0%} y volumen ≥ umbral adaptativo (percentil {cfg.pctl_vol:.0%} de las "
          f"ráfagas, piso {cfg.min_vol})")
    if B.empty:
        print("  Ningún barrido calificó.")
        return
    print(f"  {len(B)} barridos · umbral actual {m._umbral_vol():.0f} contratos · {int(B['enfriamiento'].sum())} en "
          f"enfriamiento ({cfg.cooldown_s:.0f} s por dirección, tiempo del mercado)")
    print()
    print(f"  {'clase':<15s}{'n':>5s}{'continúa':>10s}{'regresa':>10s}{'MFE':>8s}{'MAE':>8s}{'repone':>9s}{'retiro':>9s}")
    for k in CLASES:
        f = B[B["clase"] == k]
        if len(f):
            print(f"  {k:<15s}{len(f):5d}{f['cont'].mean():10.1f}{f['ret'].mean():10.1f}{f['mfe'].mean():8.1f}"
                  f"{f['mae'].mean():8.1f}{f['repos'].mean():9.0%}{f['retiro'].mean():9.0%}")
    otras = B[~B["clase"].isin(CLASES)]
    if len(otras):
        print(f"  (sin clasificar: {len(otras)} — sin libro o sin {cfg.horizonte_s:g} s de datos después)")
    print("  continúa / regresa / MFE / MAE en ticks a favor del barrido, a los "
          f"{cfg.horizonte_s:g} s; repone y retiro como fracción del volumen barrido")
    print()
    print("  Últimos barridos:")
    for i, r in B.tail(10).iterrows():
        print(f"    {_hora(r['t_ini'], cfg, True)}  {r['direccion']:<6s} {r['niveles']:>2d} niv {r['ticks']:>4.0f} t "
              f"{r['vol']:>6,.0f} c  pureza {r['pureza']:.0%} mono {r['mono']:.0%}  {r['clase'] or '—'}"
              + ("  (enfriamiento)" if r["enfriamiento"] else ""))


def reporte_grandes(res: Resultado) -> None:
    G, m = res.grandes, res.motor
    _titulo("4 · ÓRDENES GRANDES (rastreo por ID)")
    print(f"  Umbral: percentil {res.cfg.pctl_grande:.1%} del tamaño de las altas, piso {res.cfg.min_grande} → "
          f"{m.umbral_grande:.0f} contratos")
    if G.empty:
        print("  Ninguna orden grande.")
        return
    for k, v in G["resultado"].value_counts().items():
        print(f"    {k:<34s}{v:6,d}")
    sp = G[G["resultado"] == "retirada al acercarse el precio"]
    if len(sp):
        print("  Las últimas retiradas cuando el precio llegó a 1 tick (sin ejecutarse):")
        for _, r in sp.tail(5).iterrows():
            print(f"    {_hora(r['t_add'], res.cfg)}  {'compra' if r['lado'] > 0 else 'venta':<6s} {r['tam']:>5,d} c @ "
                  f"{_precio(r['precio'], res.cfg)} · vivió {_segundos(r['vida_s'])}")
    print("  (Que se retire al acercarse el precio es un PATRÓN a vigilar, no una prueba de spoofing.)")


def reporte_auditoria(res: Resultado) -> None:
    cfg, E, comp = res.cfg, res.estudio, res.comparacion
    _titulo("5 · AUDITORÍA")
    if not E.empty:
        print("  Camino del mid después de cada barrido (ticks a favor; 0 = el mid antes del barrido):")
        taus = [t for t in (-10, 1, 5, 15, 30, 60) if t in E.columns]
        print(f"      {'clase':<15s}{'n':>5s}" + "".join(f"{t:>+8d}s" for t in taus))
        for k in CLASES:
            f = E[E.index == k]
            if len(f):
                print(f"      {k:<15s}{len(f):5d}" + "".join(_fmt(f[t].mean(), 1, 9) for t in taus))
    print()
    print(f"  Tu detector (ventanas fijas de {cfg.gap_ms:.0f} ms con T y F, umbral = p95 de UNA operación) sobre los "
          "mismos datos:")
    print(f"      {comp['tuyas']} alertas · {comp['coinciden']} coinciden con un barrido del módulo · de los "
          f"{comp['mios']} barridos del módulo vio {comp['vistos_por_tuyo']}")
    if np.isfinite(comp["razon_vol"]):
        print(f"      su volumen es {comp['razon_vol']:.2f} veces el operado (≈ 2 = cuenta cada contrato con su T y su F)")


def reporte_cordura(res: Resultado) -> None:
    _titulo("6 · CHEQUEO DE CORDURA")
    for ok, txt in res.cordura:
        print(f"  {'✓' if ok else '⚠'} {txt}")


def reporte_verdad(res: Resultado) -> None:
    v = res.medicion
    if not v:
        return
    _titulo("7 · CONTRA LA VERDAD (sólo en simulación)")
    print(f"  Libro final idéntico: {'sí' if v['libro_identico'] else 'NO'} · ciclo de vida idéntico: "
          f"{'sí' if v['ciclo_igual'] else 'NO'} · barridos de un agresor idénticos: {'sí' if v['exactos_iguales'] else 'NO'}")
    print(f"  Contratos llenados: {v['llenado'][0]:,} contra {v['llenado'][1]:,} · huérfanas {v['huerfanas'][0]} "
          f"contra {v['huerfanas'][1]} inyectadas")
    print(f"  Barridos plantados: {v['plantados']} · detectados {v['detectados']} · con la clase correcta {v['bien']}")
    for (a, b), n in sorted(v["confusion"].items()):
        print(f"      {a:<15s} → {b:<15s}{n:4d}")
    print("  Órdenes grandes plantadas (tipo → lo que dijo el módulo):")
    for (a, b), n in sorted(v["grandes"].items()):
        print(f"      {a:<10s} → {b:<34s}{n:4d}")


# =============================================================================
# 7. TABLEROS
# =============================================================================
C = {"fondo": "#fcfcfb", "tinta": "#0b0b0b", "tinta2": "#52514e", "tenue": "#898781",
     "grid": "#e1e0d9", "eje": "#c3c2b7", "neutro": "#d6d5ce",
     "s1": "#2a78d6", "s2": "#eb6834", "s3": "#1baf7a", "s4": "#eda100", "s5": "#e87ba4",
     "s6": "#008300", "s7": "#4a3aa7", "s8": "#e34948",
     "alza": "#256abf", "baja": "#e34948"}
RAMPA_AZUL = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5",
              "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]


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
    opciones = dict(fontsize=7.5, frameon=False, labelcolor=C["tinta2"], loc="upper left")
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


COLOR_CLASE = {"MOMENTUM": C["s1"], "CAZA DE STOPS": C["s8"], "ABSORCIÓN": C["s4"], "NEUTRAL": C["tenue"]}


def _romper(t: pd.DatetimeIndex, y: np.ndarray, hueco_s: float):
    """Inserta NaN donde hay huecos para no unir puntos lejanos."""
    t = pd.DatetimeIndex(t)
    y = np.asarray(y, dtype=float)
    if len(t) < 2:
        return t, y
    cortes = np.flatnonzero(np.diff(t.asi8) > hueco_s * NS)
    if not cortes.size:
        return t, y
    s = pd.Series(np.r_[y, np.full(cortes.size, np.nan)],
                  index=t.append(t[cortes] + pd.Timedelta(milliseconds=1))).sort_index(kind="stable")
    return s.index, s.to_numpy()


def tablero_barridos(res: Resultado, plt, ruta: Path):
    import matplotlib.dates as mdates
    cfg, B, m = res.cfg, res.barridos, res.motor
    tz = cfg.tz_local
    fig = plt.figure(figsize=(18, 13.5))
    fig.patch.set_facecolor(C["fondo"])
    gs = fig.add_gridspec(3, 2, height_ratios=[1.7, 1.0, 1.25], hspace=0.3, wspace=0.18, bottom=0.06, top=0.92)
    a1 = fig.add_subplot(gs[0, :])
    a2 = fig.add_subplot(gs[1, :], sharex=a1)
    a3, a4 = fig.add_subplot(gs[2, 0]), fig.add_subplot(gs[2, 1])
    clas = B[B["clase"].isin(CLASES)] if len(B) else B
    fig.suptitle(f"Rastreador de ID · {cfg.symbol} ({nombre(cfg.symbol)}) · {len(B)} barridos · "
                 + " · ".join(f"{k.lower()} {int((clas['clase'] == k).sum())}" for k in CLASES if len(clas)),
                 x=0.01, ha="left", color=C["tinta"], fontsize=12.5)

    _estilo(a1, f"Mid del libro reconstruido (cada segundo) · ▲ barrido comprador, ▼ vendedor · color = clase a los "
                f"{cfg.horizonte_s:g} s")
    s = res.mid.dropna()
    if len(s):
        tp, yp = _romper(res.mid.index, res.mid.to_numpy(), 30)
        a1.plot(tp.tz_convert(tz), yp, color=C["tinta"], linewidth=0.7)
    for k, col in COLOR_CLASE.items():
        f = B[B["clase"] == k]
        for lado, marca in ((1, "^"), (-1, "v")):
            g = f[f["lado"] == lado]
            if len(g):
                a1.scatter(g["t_fin"].dt.tz_convert(tz), g["p_ext"], marker=marca, s=30 + 12 * g["niveles"],
                           color=col, edgecolors=C["tinta"], linewidths=0.5, zorder=4,
                           label=k.lower() if lado == 1 else None)
    a1.set_ylabel("precio", color=C["tinta2"], fontsize=9)
    _leyenda(a1, loc="upper left", ncol=4, frameon=True, facecolor=C["fondo"], edgecolor="none", framealpha=0.9)

    _estilo(a2, f"Volumen de cada barrido contra el umbral adaptativo (percentil {cfg.pctl_vol:.0%} de las ráfagas, "
                f"piso {cfg.min_vol})")
    if m.umbrales:
        tu_ = pd.to_datetime([t for t, _ in m.umbrales], utc=True).tz_convert(tz)
        a2.step(tu_, [u for _, u in m.umbrales], where="post", color=C["tinta2"], linewidth=1.1, label="umbral")
    for k, col in COLOR_CLASE.items():
        f = B[B["clase"] == k]
        if len(f):
            a2.scatter(f["t_fin"].dt.tz_convert(tz), f["vol"], s=18, color=col, alpha=0.85, linewidths=0)
    a2.set_yscale("log")
    from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter
    a2.yaxis.set_major_locator(LogLocator(base=10, subs=(1.0, 2.0, 5.0)))
    a2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    a2.yaxis.set_minor_formatter(NullFormatter())
    a2.set_ylabel("contratos", color=C["tinta2"], fontsize=9)
    a2.xaxis.set_major_locator(mdates.AutoDateLocator(tz=tz))
    a2.xaxis.set_major_formatter(mdates.DateFormatter("%d-%m\n%H:%M", tz=tz))
    a1.tick_params(labelbottom=False)
    _leyenda(a2, loc="upper left", frameon=True, facecolor=C["fondo"], edgecolor="none", framealpha=0.9)

    _estilo(a3, "Camino del mid alrededor del barrido (ticks a favor; 0 = antes del barrido) · media ± IC 95 %")
    E = res.estudio
    if not E.empty:
        tau = E.columns.to_numpy()
        for k, col in COLOR_CLASE.items():
            f = E[E.index == k]
            if len(f):
                mu = f.mean().to_numpy()
                ee = 1.96 * f.std().to_numpy() / np.sqrt(f.notna().sum().clip(lower=1).to_numpy())
                a3.fill_between(tau, mu - ee, mu + ee, color=col, alpha=0.15, linewidth=0)
                a3.plot(tau, mu, color=col, linewidth=1.8, label=f"{k.lower()} ({len(f)})")
        a3.axvline(0, color=C["tinta2"], linewidth=0.9, linestyle=":")
        a3.axvline(cfg.horizonte_s, color=C["tenue"], linewidth=0.9, linestyle=(0, (4, 3)))
        a3.axhline(0, color=C["eje"], linewidth=0.9)
        _leyenda(a3, loc="upper left", frameon=True, facecolor=C["fondo"], edgecolor="none", framealpha=0.9)
    a3.set_xlabel("segundos desde el barrido (línea punteada = horizonte de la clase)", color=C["tinta2"], fontsize=9)

    _estilo(a4, "Barridos por hora de Chicago, por clase")
    if len(clas):
        hora = clas["t_fin"].dt.tz_convert(cfg.tz_mercado).dt.hour
        base = np.zeros(24)
        for k, col in COLOR_CLASE.items():
            n = np.bincount(hora[clas["clase"] == k], minlength=24)
            a4.bar(range(24), n, bottom=base, color=col, width=0.8, label=k.lower())
            base += n
        a4.set_xticks(range(0, 24, 3))
    a4.set_xlabel("hora de Chicago", color=C["tinta2"], fontsize=9)
    fig.text(0.008, 0.012, f"{IDENTIFICADOR} · un barrido = ráfaga de golpes agresivos a ≤ {cfg.gap_ms:.0f} ms que "
             f"cruza ≥ {cfg.min_niveles} niveles · fechas en CDMX", color=C["tenue"], fontsize=7.5)
    fig.savefig(ruta, dpi=110, facecolor=C["fondo"], bbox_inches="tight")
    return fig


def tablero_ciclo(res: Resultado, plt, ruta: Path):
    cfg, m = res.cfg, res.motor
    fig = plt.figure(figsize=(18, 12.5))
    fig.patch.set_facecolor(C["fondo"])
    gs = fig.add_gridspec(2, 2, hspace=0.36, wspace=0.3, bottom=0.06, top=0.92)
    (b1, b2), (b3, b4) = [[fig.add_subplot(gs[i, j]) for j in range(2)] for i in range(2)]
    q = m.qty
    fig.suptitle(f"Rastreador de ID · ciclo de vida y auditoría · {cfg.symbol} · llenado {q['llenado'] / max(1, q['añadido']):.1%} "
                 f"de lo añadido · cancelado / llenado = {q['cancelado'] / max(1, q['llenado']):.1f}",
                 x=0.01, ha="left", color=C["tinta"], fontsize=12.5)

    _estilo(b1, "Cuánto vive una orden, según cómo termina (fracción de cada grupo)")
    centros = np.r_[BINS_VIDA[0] - 0.125, BINS_VIDA + 0.125]
    for k, col in (("cancelada", C["s8"]), ("llena", C["s1"]), ("parcial y cancelada", C["s4"]),
                   ("limpieza del libro", C["tenue"])):
        v = m.vida[k]
        if v.sum():
            b1.plot(centros, v / v.sum(), color=col, linewidth=1.8, label=f"{k} ({v.sum():,})")
    b1.axvline(math.log10(cfg.fugaz_ms / 1000), color=C["tinta2"], linewidth=0.9, linestyle=":")
    marcas = {-3: "1 ms", -2: "10 ms", -1: "100 ms", 0: "1 s", 1: "10 s", math.log10(60): "1 min",
              math.log10(600): "10 min", math.log10(3600): "1 h"}
    b1.set_xticks(list(marcas))
    b1.set_xticklabels(list(marcas.values()), fontsize=8)
    b1.set_xlim(-4, 4.5)
    b1.text(math.log10(cfg.fugaz_ms / 1000), b1.get_ylim()[1] * 0.95, f" fugaz < {cfg.fugaz_ms:.0f} ms",
            color=C["tinta2"], fontsize=8, va="top")
    _leyenda(b1, loc="upper right", frameon=True, facecolor=C["fondo"], edgecolor="none", framealpha=0.9)

    _estilo(b2, f"Órdenes grandes (≥ {m.umbral_grande:.0f} contratos): cómo terminaron")
    G = res.grandes
    if len(G):
        orden = ["ejecutada", "parcial", "retirada lejos del precio", "retirada al acercarse el precio", "viva"]
        n = G["resultado"].value_counts().reindex(orden).fillna(0)
        col = [C["s1"], C["s3"], C["neutro"], C["s8"], C["tenue"]]
        b2.barh(range(len(n)), n.to_numpy(), color=col)
        b2.set_yticks(range(len(n)))
        b2.set_yticklabels(n.index, fontsize=9)
        b2.invert_yaxis()
        for i, v in enumerate(n.to_numpy()):
            b2.text(v, i, f" {int(v):,}", va="center", fontsize=9, color=C["tinta"])
    else:
        b2.text(0.5, 0.5, "sin órdenes grandes", transform=b2.transAxes, ha="center", color=C["tenue"])

    _estilo(b3, f"Tu detector (ventanas fijas de {cfg.gap_ms:.0f} ms, T + F) contra el del módulo, mismos datos")
    cp = res.comparacion
    etiquetas = ["barridos del\nmódulo", "vistos por\nel tuyo", "alertas\ntuyas", "coinciden con\nel módulo"]
    valores = [cp["mios"], cp["vistos_por_tuyo"], cp["tuyas"], cp["coinciden"]]
    b3.bar(range(4), valores, color=[C["s7"], C["s5"], C["s2"], C["s5"]], width=0.6)
    for i, v in enumerate(valores):
        b3.text(i, v, f"{v:,}", ha="center", va="bottom", fontsize=10, color=C["tinta"])
    b3.set_xticks(range(4))
    b3.set_xticklabels(etiquetas, fontsize=9)
    b3.margins(y=0.15)
    if np.isfinite(cp["razon_vol"]):
        b3.text(0.98, 0.95, f"su volumen = {cp['razon_vol']:.2f}× el operado", transform=b3.transAxes, ha="right",
                va="top", fontsize=9, color=C["tinta"])

    b4.set_facecolor(C["fondo"])
    b4.axis("off")
    b4.set_title("Chequeo de cordura", color=C["tinta"], fontsize=10, loc="left", pad=8)
    import textwrap as _tw
    yy = 0.97
    for ok_, txt in res.cordura:
        lineas = _tw.wrap(txt, 78)
        b4.text(0.0, yy, "✓" if ok_ else "⚠", color=C["s3"] if ok_ else C["baja"], fontsize=11,
                transform=b4.transAxes, va="top")
        b4.text(0.04, yy, "\n".join(lineas), color=C["tinta"], fontsize=9, transform=b4.transAxes, va="top")
        yy -= 0.045 * len(lineas) + 0.04
    fig.text(0.008, 0.012, f"{IDENTIFICADOR} · ciclo de vida por order_id: llenado = la orden bajó en el mismo evento "
             "que una operación en su precio (o con su registro F)", color=C["tenue"], fontsize=7.5)
    fig.savefig(ruta, dpi=110, facecolor=C["fondo"], bbox_inches="tight")
    return fig


def tableros(res: Resultado, mostrar: bool = True) -> tuple[list[Path], object, bool]:
    plt, ventana = _preparar_grafico(mostrar)
    if plt is None:
        return [], None, False
    carpeta = _ruta(res.cfg.salida_dir)
    carpeta.mkdir(parents=True, exist_ok=True)
    rutas = []
    for nombre_, fn in (("barridos", tablero_barridos), ("ciclo_de_vida", tablero_ciclo)):
        ruta = carpeta / f"rid_{nombre_}_{raiz(res.cfg.symbol)}.png"
        fig = fn(res, plt, ruta)
        rutas.append(ruta)
        print(f"🖼  {ruta}")
        if not ventana:
            plt.close(fig)
    return rutas, plt, ventana


# =============================================================================
# 8. TELEGRAM — el token y el chat, igual que la key: FUERA del código
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
        print(f"⚠ Telegram: falta TELEGRAM_BOT_TOKEN o no tiene forma de token "
              f"({_mascara(token)}).\n" + AYUDA_TELEGRAM)
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


EMOJI = {"MOMENTUM": "🚀", "CAZA DE STOPS": "🎯", "ABSORCIÓN": "🧲", "NEUTRAL": "⚪"}


def texto_barrido(b: dict, cfg: Config, inmediato: bool = False) -> str:
    esc = html.escape
    lado = "🟢 COMPRA" if b["lado"] > 0 else "🔴 VENTA"
    clase = f"detectado (clase en {cfg.horizonte_s:g} s)" if inmediato else (b.get("clase") or "—")
    lin = [f"{EMOJI.get(b.get('clase'), '⚡')} <b>BARRIDO {esc(clase)} · {esc(cfg.symbol)}</b>",
           f"{lado} · {b['niveles']} niveles · {b['ticks']:.0f} ticks · {b['vol']:,} contratos en {b['n_eventos']} golpe(s)",
           f"pureza {b['pureza']:.0%} · monotonicidad {b['mono']:.0%} · VWAP {_precio(b['vwap'] / PRICE_SCALE, cfg)}",
           f"retiro previo {b['retiro']:.0%} · órdenes consumidas {b['consumidas']}"
           + (f" (edad mediana {b['edad_med_ms']:,.0f} ms)" if np.isfinite(b["edad_med_ms"]) else "")]
    if not inmediato and "cont" in b:
        lin.append(f"a los {cfg.horizonte_s:g} s: sigue {b['cont']:+.1f} ticks · respecto al inicio {b['ret']:+.1f} · "
                   f"reposición {b.get('repos', 0):.0%}")
    lin.append(esc(_hora(pd.Timestamp(b["t_ini"], tz="UTC"), cfg, True)))
    return "\n".join(lin)


def texto_grande(g: dict, cfg: Config) -> str:
    return (f"🐋 <b>ORDEN GRANDE {html.escape(g['resultado'].upper())} · {html.escape(cfg.symbol)}</b>\n"
            f"{'compra' if g['lado'] > 0 else 'venta'} {g['tam']:,} contratos @ {_precio(g['precio'] / PRICE_SCALE, cfg)} · "
            f"vivió {_segundos(g['vida_s'])} · llenado {g['llenado']:,} · lo más cerca que llegó el precio: "
            f"{g['dist_min']:.0f} tick(s)\n{html.escape(_hora(pd.Timestamp(g['t_add'], tz='UTC'), cfg))}")


class ColaTelegram:
    """
    [v1] Tu límite de 2 s TIRA la alerta que llega antes de tiempo. Aquí se encolan y salen juntas
    en un solo mensaje en cuanto se puede; los NEUTRAL llegan sin sonido.
    """

    def __init__(self, cfg: Config, reloj=time.time):
        self.cfg, self.reloj = cfg, reloj
        self.cred = credenciales_telegram(preguntar=False)
        self.pend: list[tuple[str, bool]] = []
        self.ultimo = -math.inf
        self.enviados = self.fallas = 0

    def poner(self, texto: str, sonido: bool = True) -> None:
        if self.cred is not None:
            self.pend.append((texto, sonido))

    def vaciar(self, forzar: bool = False) -> None:
        if not self.pend or self.cred is None:
            return
        ahora = self.reloj()
        if not forzar and ahora - self.ultimo < self.cfg.telegram_intervalo_s:
            return
        bloque, sonido, largo = [], False, 0
        while self.pend and largo + len(self.pend[0][0]) + 2 <= 4000:
            t, s = self.pend.pop(0)
            bloque.append(t)
            sonido |= s
            largo += len(t) + 2
        if not bloque:
            bloque, sonido = [self.pend.pop(0)[0][:4000]], True
        r = llamar_telegram(self.cred[0], "sendMessage", {"chat_id": self.cred[1], "text": "\n\n".join(bloque),
                                                          "parse_mode": "HTML", "disable_notification": str(not sonido).lower(),
                                                          "disable_web_page_preview": "true"})
        self.ultimo = ahora
        if r.get("ok"):
            self.enviados += 1
        else:
            self.fallas += 1
            if self.fallas <= 3:
                print(f"⚠ Telegram: {r.get('description', r)}")


def hay_alerta(res: Resultado) -> list[str]:
    B = res.barridos
    if B.empty:
        return []
    limite = B["t_fin"].max() - pd.Timedelta(hours=24)
    f = B[(B["t_fin"] >= limite) & B["clase"].isin(CLASES) & ~B["enfriamiento"].astype(bool)]
    return [f"{_hora(r['t_ini'], res.cfg)}: {r['clase']} {r['direccion'].lower()} · {r['niveles']} niveles · "
            f"{r['vol']:,.0f} contratos" for _, r in f.iterrows()]


def mensaje_telegram(res: Resultado, limite: int = 4096) -> str:
    esc, cfg, B, m = html.escape, res.cfg, res.barridos, res.motor
    lin = [f"<b>{esc(IDENTIFICADOR)}</b> · {esc(cfg.symbol)} · {m.conteo['registros']:,} registros MBO"]
    if len(res.mid.dropna()):
        lin.append(f"mid final {_precio(res.mid.dropna().iloc[-1], cfg)} · "
                   f"{esc(_hora(res.mid.dropna().index[-1], cfg))}")
    q = m.qty
    lin.append(f"llenado {q['llenado'] / max(1, q['añadido']):.1%} de lo añadido · fugaces "
               f"{m.ciclo['fugaces'] / max(1, m.ciclo['cancelada']):.0%} de las canceladas")
    if len(B):
        lin.append("<b>Barridos</b>: " + " · ".join(f"{EMOJI[k]} {k.lower()} {int((B['clase'] == k).sum())}" for k in CLASES))
    al = hay_alerta(res)
    for a in al[-8:]:
        lin.append("⚠️ " + esc(a))
    G = res.grandes
    if len(G):
        lin.append(f"🐋 órdenes grandes: {len(G)} · retiradas al acercarse el precio: "
                   f"{int((G['resultado'] == 'retirada al acercarse el precio').sum())}")
    malos = [t for ok, t in res.cordura if not ok]
    lin.append("✅ cordura en verde" if not malos else "⚠️ " + esc(malos[0]))
    texto = "\n".join(lin)
    return texto if len(texto) <= limite else texto[:limite - 20].rsplit("\n", 1)[0] + "\n…"


def enviar_telegram(res: Resultado, rutas: list[Path], documentos: bool = False) -> bool:
    cred = credenciales_telegram()
    if cred is None:
        return False
    token, chat = cred
    r = llamar_telegram(token, "sendMessage", {"chat_id": chat, "text": mensaje_telegram(res),
                                               "parse_mode": "HTML",
                                               "disable_web_page_preview": "true"})
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
        r = llamar_telegram(token, metodo, {"chat_id": chat, "caption": ruta.stem[:1000]},
                            archivo=(campo, ruta))
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
    for cid, nombre in chats.items():
        print(f"  chat_id = {cid}   {nombre}")
    print('\nGuárdalo:  setx TELEGRAM_CHAT_ID "<el número>"   y reabre VS Code.')
    return 0


# =============================================================================
# 9. GUARDAR Y LIVE
# =============================================================================
def guardar(res: Resultado) -> None:
    cfg = res.cfg
    carpeta = _ruta(cfg.salida_dir)
    carpeta.mkdir(parents=True, exist_ok=True)
    t = res.mid.dropna().index
    suf = _nombre_seguro(raiz(cfg.symbol), f"{t[0]:%Y%m%d}" if len(t) else "x", f"{t[-1]:%Y%m%d}" if len(t) else "x")
    B = res.barridos.copy()
    B.insert(1, "t_ini_cdmx", B["t_ini"].dt.tz_convert(cfg.tz_local))
    B.to_csv(carpeta / f"rid_barridos_{suf}.csv")
    res.grandes.to_csv(carpeta / f"rid_ordenes_grandes_{suf}.csv", index=False)
    m = res.motor
    pd.DataFrame({"ordenes": [m.ciclo[k] for k in MOTIVOS],
                  "vida_mediana_s": [vida_mediana(m.vida[k]) for k in MOTIVOS]},
                 index=list(MOTIVOS)).to_csv(carpeta / f"rid_ciclo_de_vida_{suf}.csv")
    res.tuyo.to_csv(carpeta / f"rid_tu_detector_{suf}.csv", index=False)
    print(f"💾 Barridos, órdenes grandes, ciclo de vida y tu detector guardados en {carpeta}")


class _Fin(Exception):
    pass


def correr_live(cfg: Config, fabrica=None, max_registros: int | None = None, dormir=time.sleep,
                reloj=time.time) -> Rastreador:
    """
    Databento Live, esquema MBO CON SNAPSHOT: el libro arranca completo (tu versión empezaba vacía
    y nunca conocía las órdenes que ya estaban). Si la conexión cae, reintenta con espera
    exponencial (tus 10 intentos, hasta 120 s) y el snapshot nuevo reconstruye el libro; las
    órdenes que siguen vivas conservan su historia. Con --telegram-live cada barrido clasificado
    llega a tu teléfono. (`fabrica`, `dormir` y `reloj` son inyectables para probarlo sin red.)
    """
    if fabrica is None:
        if db is None:
            sys.exit("Falta el paquete databento:  pip install databento")
        _exigir_api_key()

        def fabrica():
            return db.Live()
    cola = ColaTelegram(cfg, reloj) if cfg.telegram_live else None

    def al_barrido(b, inmediato=False):
        print(("⚡ " if inmediato else "") + re.sub(r"<[^>]+>", "", texto_barrido(b, cfg, inmediato)).replace("\n", " · "))
        if cola is not None:
            cola.poner(texto_barrido(b, cfg, inmediato), sonido=b.get("clase") != "NEUTRAL")
            cola.vaciar()

    def al_grande(g):
        if cfg.telegram_grandes and cola is not None and g["resultado"] != "viva":
            cola.poner(texto_grande(g, cfg), sonido=False)
            cola.vaciar()

    motor = Rastreador(cfg, al_barrido=al_barrido, al_grande=al_grande)
    if cola is not None:
        cola.poner(f"🟢 <b>RADAR MBO ACTIVADO</b> · {html.escape(cfg.symbol)} · ráfagas a ≤ {cfg.gap_ms:.0f} ms · "
                   f"clase a los {cfg.horizonte_s:g} s")
        cola.vaciar(forzar=True)
    intentos, vistos, latido = 0, 0, reloj()
    while intentos <= cfg.max_reintentos:
        cliente = None
        try:
            cliente = fabrica()
            cliente.subscribe(dataset=cfg.dataset, schema="mbo", symbols=cfg.symbol, stype_in=cfg.stype_in,
                              snapshot=True)
            print(f"✅ Suscripción MBO con snapshot a {cfg.symbol}.")
            for rec in cliente:
                nombre_ = type(rec).__name__
                if nombre_ == "MBOMsg":
                    motor.procesar_registro(rec)
                    vistos += 1
                    intentos = 0
                    if max_registros and vistos >= max_registros:
                        raise _Fin
                elif nombre_ == "ErrorMsg":
                    print(f"⚠ Databento: {rec.err}")
                elif nombre_ == "SystemMsg" and not rec.is_heartbeat():
                    print(f"ℹ {rec.msg}")
                if reloj() - latido >= cfg.heartbeat_s:
                    latido = reloj()
                    print(f"💓 {vistos:,} registros · {len(motor.barridos)} barridos · "
                          f"{sum(len(lb.ordenes) for lb in motor.libros.values()):,} órdenes vivas · "
                          f"reconexiones {motor.conteo['reconexiones']}")
                    if cola is not None:
                        cola.vaciar()
            raise ConnectionError("el flujo terminó")
        except (_Fin, KeyboardInterrupt) as e:
            if isinstance(e, KeyboardInterrupt):
                print("\n🛑 Detenido.")
            break
        except Exception as e:
            intentos += 1
            if intentos > cfg.max_reintentos:
                break
            espera = min(2 ** intentos, cfg.espera_max_s) * np.random.uniform(0.8, 1.2)
            print(f"⚠ {type(e).__name__}: {e} — reintento {intentos}/{cfg.max_reintentos} en {espera:.0f} s")
            motor.reiniciar_libros(motor._ts_max)
            dormir(espera)
        finally:
            if cliente is not None:
                try:
                    cliente.stop()
                except Exception:
                    pass
    motor.terminar()
    if cola is not None:
        fallo = intentos > cfg.max_reintentos
        cola.poner(("❌ <b>RADAR MBO FALLIDO</b>: reintentos agotados." if fallo else "🔴 <b>RADAR MBO APAGADO</b>")
                   + f" · {vistos:,} registros · {len(motor.barridos)} barridos")
        cola.vaciar(forzar=True)
        while cola.pend:
            cola.vaciar(forzar=True)
    motor.vistos_live = vistos
    return motor


# =============================================================================
# 10. LÍNEA DE COMANDOS
# =============================================================================
def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Rastreador de ID AC v2 — ciclo de vida MBO y barridos de liquidez")
    p.add_argument("--pruebas", action="store_true", help="pruebas internas (sin red ni datos)")
    p.add_argument("--simulacion", action="store_true", help="libro MBO simulado con verdad conocida")
    p.add_argument("--live", action="store_true", help="Databento Live con snapshot")
    p.add_argument("--archivo", help="usar un .dbn / .dbn.zst MBO existente en vez de descargar")
    p.add_argument("--simbolo")
    p.add_argument("--inicio", "--start", dest="start", help="UTC, p. ej. 2026-09-20T21:00:00")
    p.add_argument("--fin", "--end", dest="end", help="UTC, p. ej. 2026-09-23T21:00:00")
    p.add_argument("--ventana-ms", type=float, dest="gap_ms", help="golpes a ≤ esto = una ráfaga (100)")
    p.add_argument("--min-niveles", type=int, dest="min_niveles")
    p.add_argument("--min-ticks", type=int, dest="min_ticks")
    p.add_argument("--pureza", type=float, dest="pureza_min")
    p.add_argument("--monotonicidad", type=float, dest="mono_min")
    p.add_argument("--min-vol", type=int, dest="min_vol")
    p.add_argument("--percentil", type=float, dest="pctl_vol")
    p.add_argument("--cooldown", type=float, dest="cooldown_s")
    p.add_argument("--horizonte", type=float, dest="horizonte_s", help="segundos para clasificar (5)")
    p.add_argument("--min-grande", type=int, dest="min_grande")
    p.add_argument("--costo-max", type=float, dest="costo_max_usd")
    p.add_argument("--salida", dest="salida_dir", help="carpeta para CSV y PNG (salidas_rid/)")
    p.add_argument("--sin-grafica", "--sin-tablero", action="store_true", dest="sin_tablero")
    p.add_argument("--sin-ventana", action="store_true")
    p.add_argument("--sin-paridad", action="store_true")
    t = p.add_argument_group("Telegram")
    t.add_argument("--telegram", action="store_true", help="resumen + 2 tableros al terminar")
    t.add_argument("--telegram-solo-alertas", action="store_true")
    t.add_argument("--telegram-live", action="store_true", help="en --live, cada barrido clasificado")
    t.add_argument("--telegram-grandes", action="store_true", help="en --live, también las órdenes grandes")
    t.add_argument("--alerta-inmediata", action="store_true", help="avisar al detectar, antes de la clase")
    t.add_argument("--telegram-documentos", action="store_true")
    t.add_argument("--telegram-buscar-chat", action="store_true")
    s = p.add_argument_group("simulación")
    s.add_argument("--horas-sim", type=float, dest="sim_horas")
    s.add_argument("--semilla", type=int, dest="sim_semilla")
    s.add_argument("--sin-fills", action="store_true", help="simular datos sin registros F")
    s.add_argument("--sin-plantados", action="store_true", help="sin barridos institucionales plantados")
    return p


def config_desde_args(a: argparse.Namespace) -> Config:
    claves = ("start", "end", "gap_ms", "min_niveles", "min_ticks", "pureza_min", "mono_min", "min_vol", "pctl_vol",
              "cooldown_s", "horizonte_s", "min_grande", "costo_max_usd", "salida_dir", "sim_horas", "sim_semilla")
    cambios = {k: getattr(a, k) for k in claves if getattr(a, k, None) is not None}
    if a.simbolo:
        cambios["symbol"] = simbolo_continuo(a.simbolo)
    for k in ("telegram_live", "telegram_grandes", "alerta_inmediata"):
        if getattr(a, k):
            cambios[k] = True
    if a.sin_fills:
        cambios["sim_fills"] = False
    return replace(CFG, **cambios)


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
    print(f"▶ {IDENTIFICADOR} · {cfg.symbol}")
    verdad = None
    if a.simulacion:
        print(f"🎲 {cfg.sim_horas:g} h de libro MBO simulado ({'con' if cfg.sim_fills else 'sin'} registros F): barridos "
              "plantados de momentum, caza de stops, absorción y ráfagas, órdenes grandes y defectos CONOCIDOS.")
        tienda, verdad = simular(cfg, info=not a.sin_plantados)
    elif a.archivo:
        tienda = db.DBNStore.from_file(a.archivo)
    else:
        tienda = obtener_datos(cfg)
    res = analizar(tienda, cfg, verdad=verdad, chequear_paridad=not a.sin_paridad)
    reporte_datos(res)
    reporte_ciclo(res)
    reporte_barridos(res)
    reporte_grandes(res)
    reporte_auditoria(res)
    reporte_cordura(res)
    reporte_verdad(res)
    rutas, plt_, ventana = ([], None, False)
    if not a.sin_tablero:
        print()
        rutas, plt_, ventana = tableros(res, mostrar=not a.sin_ventana)
    guardar(res)
    if a.telegram or a.telegram_solo_alertas:
        if a.telegram_solo_alertas and not hay_alerta(res):
            print("📭 Telegram: sin barridos clasificados en las últimas 24 h.")
        else:
            enviar_telegram(res, rutas, documentos=a.telegram_documentos)
    _titulo("CÓMO LEER ESTO")
    print("  1. Cada orden se sigue por su order_id: alta, cambios, llenados y cancelación. Llenado = la orden bajó")
    print("     en el mismo evento que una operación en su precio; si no, fue cancelación.")
    print("  2. Un barrido es una ráfaga de golpes agresivos que cruza varios niveles hacia un solo lado.")
    print(f"  3. La clase se decide {cfg.horizonte_s:g} s DESPUÉS, con el mid del libro: momentum si el precio sigue, caza")
    print("     de stops si regresa detrás del inicio, absorción si el lado pasivo repuso lo barrido.")
    print("  4. Los umbrales se adaptan solos: el volumen contra las ráfagas recientes y la clase contra la σ del mid.")
    if rutas and not a.sin_ventana:
        print()
        mostrar_tableros(plt_, ventana, rutas)
    return 0


# =============================================================================
# 11. PRUEBAS INTERNAS
# =============================================================================
def pruebas() -> int:
    import contextlib
    import io
    import tempfile

    cfg = CFG
    fallas: list[str] = []
    hecho = 0

    def check(nombre_: str, ok: bool, detalle: str = "") -> None:
        nonlocal hecho
        hecho += 1
        print(f"  {'✓' if ok else '✗'} {nombre_}" + (f"   {detalle}" if detalle else ""))
        if not ok:
            fallas.append(nombre_)

    def callado(fn, *a, **k):
        with contextlib.redirect_stdout(io.StringIO()):
            return fn(*a, **k)

    tk = tick_int(cfg)
    L = F_LAST

    def arreglo(filas, iid=1):
        a = np.zeros(len(filas), dtype=DTYPE_MBO)
        for i, (ts, acc, lado, p, q, oid, fl) in enumerate(filas):
            a[i] = (ts, ts + 1000, oid, UNDEF_PRICE if p is None else p * tk, q, fl, acc.encode(), lado.encode(), iid, i)
        return a

    def correr(filas, c=cfg, **k):
        m = Rastreador(c, **k)
        m.procesar_arreglo(arreglo(filas))
        m.terminar()
        return m

    def libro_de(m):
        return {i: {o: (x[O_LADO], x[O_PRECIO], x[O_TAM]) for o, x in lb.ordenes.items()} for i, lb in m.libros.items()}

    _titulo("PRUEBAS INTERNAS")
    MS = NS_MS

    # 1 ------------------------------------------ ciclo de vida a mano, con y sin registros F
    base = [(1, "A", "B", 100, 5, 1, L), (2, "A", "B", 100, 3, 2, L), (3, "A", "A", 102, 4, 3, L),
            (4, "M", "B", 100, 2, 2, L)]                                         # reducción voluntaria
    llen1 = [(5, "T", "A", 100, 2, 0, 0), (5, "F", "B", 100, 2, 1, 0), (5, "M", "B", 100, 3, 1, L),
             (6, "T", "A", 100, 3, 0, 0), (6, "F", "B", 100, 3, 1, 0), (6, "C", "B", 100, 3, 1, L)]
    fin = [(7, "C", "A", 102, 4, 3, L)]
    bien = True
    for con_f in (True, False):
        filas = base + [f for f in llen1 if con_f or f[1] != "F"] + fin
        m = correr(filas)
        o2 = m.libros[1].ordenes.get(2)
        bien &= (m.ciclo["llena"] == 1 and m.ciclo["cancelada"] == 1 and m.ciclo["viva al final"] == 1
                 and o2 is not None and o2[O_TAM] == 2 and o2[O_CANC] == 1 and m.qty["llenado"] == 5
                 and m.qty["cancelado"] == 5 and m.libros[1].niv[1] == {100 * tk: 2} and m.libros[1].mejor[-1] is None)
    check("ciclo de vida a mano: llena en 2 partes (M y luego C), reducción voluntaria, cancelación — con y sin F",
          bool(bien))

    # 2 ------------------------------------------ T y F no tocan el libro (tu tracker restaba con ellas)
    m = correr([(1, "A", "B", 100, 5, 1, L), (2, "T", "A", 100, 2, 0, 0), (2, "F", "B", 100, 2, 1, L)])
    check("una T y su F sin la C/M del libro no cambian el libro (la orden sigue con 5)",
          m.libros[1].ordenes[1][O_TAM] == 5 and m.conteo["F_sin_orden_que_baje"] == 2)

    # 3 ------------------------------------------ un barrido exacto: un agresor, tres niveles, un evento
    book = [(1, "A", "B", 100, 10, 1, L), (2, "A", "A", 101, 5, 3, L), (3, "A", "A", 102, 5, 4, L),
            (4, "A", "A", 103, 5, 5, L), (5, "A", "A", 104, 20, 6, L)]
    t1 = NS
    barrido = [(t1, "T", "B", 101, 5, 0, 0), (t1, "T", "B", 102, 5, 0, 0), (t1, "T", "B", 103, 5, 0, 0),
               (t1, "C", "A", 101, 5, 3, 0), (t1, "C", "A", 102, 5, 4, 0), (t1, "C", "A", 103, 5, 5, L)]
    cb = replace(cfg, min_vol=10, min_obs_adapt=10 ** 9)
    m = correr(book + barrido + [(7 * NS, "A", "B", 90, 1, 9, L)], cb)
    b = m.barridos[0] if m.barridos else {}
    check("barrido exacto: 3 niveles en un evento → niveles 3, 2 ticks, pureza y monotonicidad 100 %, 3 órdenes consumidas",
          len(m.exactos) == 1 and m.exactos[0][2] == 3 and b.get("niveles") == 3 and b.get("ticks") == 2
          and b.get("pureza") == 1 and b.get("mono") == 1 and b.get("consumidas") == 3 and m.ciclo["llena"] == 3)

    # 4 ------------------------------------------ clasificador forense, sin mirar al futuro
    def clase(despues, t_mov):
        filas = book + barrido + [(t_mov + i, *f) for i, f in enumerate(despues)] + [(7 * NS, "A", "B", 90, 1, 9, L)]
        mm = correr(sorted(filas, key=lambda r: r[0]), cb)
        return mm.barridos[0]["clase"] if mm.barridos else None

    sigue = [("C", "A", 104, 20, 6, L), ("A", "B", 104, 5, 7, L), ("A", "A", 106, 5, 8, L)]
    regresa = [("C", "B", 100, 10, 1, L), ("A", "B", 99, 5, 7, L), ("A", "A", 100, 5, 8, L)]
    absorbe = [("A", "A", 103, 10, 7, L)]
    r4 = {"momentum": clase(sigue, 3 * NS), "caza": clase(regresa, 3 * NS),
          "absorcion": clase(absorbe, t1 + 200 * MS), "neutral": clase([], 3 * NS),
          "tarde": clase(sigue, int(6.5 * NS))}
    check("clasificador: sigue → MOMENTUM, regresa → CAZA DE STOPS, repone → ABSORCIÓN; lo que pasa DESPUÉS de 5 s no cuenta",
          r4 == {"momentum": "MOMENTUM", "caza": "CAZA DE STOPS", "absorcion": "ABSORCIÓN", "neutral": "NEUTRAL",
                 "tarde": "NEUTRAL"}, str(r4))

    # 5 ------------------------------------------ ráfagas: golpes a ≤ 100 ms se juntan
    libro_largo = [(i + 1, "A", "A", 101 + i, 2, 100 + i, L) for i in range(8)] + [(20, "A", "B", 99, 50, 1, L)]
    golpe = lambda t, i: [(t, "T", "B", 101 + i, 2, 0, 0), (t, "C", "A", 101 + i, 2, 100 + i, L)]   # noqa: E731
    filas = libro_largo + golpe(NS, 0) + golpe(NS + 50 * MS, 1) + golpe(NS + 120 * MS, 2) + golpe(NS + 400 * MS, 3)
    m = correr(filas, replace(cb, min_vol=1))
    check("ráfagas: golpes a 50 y 70 ms forman una; uno a 280 ms empieza otra",
          m.n_rafagas == 2 and m.barridos and m.barridos[0]["niveles"] == 3 and m.barridos[0]["n_eventos"] == 3,
          f"{m.n_rafagas} ráfagas")

    # 6 ------------------------------------------ umbral adaptativo: percentil de las ráfagas en ventana móvil
    m = Rastreador(replace(cfg, n_adapt=1000, min_vol=20, pctl_vol=0.95, min_obs_adapt=100))
    u0 = m._umbral_vol()
    for v in range(1, 2001):
        m._agregar_vol(v)
    check("umbral adaptativo: piso antes de 100 ráfagas; luego el percentil 95 de las últimas 1 000",
          u0 == 20 and m._umbral_vol() == 1951 and m._vols_ord == list(range(1001, 2001)), f"{m._umbral_vol():.0f}")

    # 7 ------------------------------------------ snapshot: lo que sigue vivo conserva su historia
    m = correr([(1, "A", "B", 100, 5, 1, L), (2, "A", "A", 101, 5, 2, L),
                (NS, "R", "N", None, 0, 0, F_SNAPSHOT), (NS, "A", "B", 100, 5, 1, F_SNAPSHOT | L),
                (NS + 5, "A", "B", 99, 1, 3, L)])
    o1 = m.libros[1].ordenes.get(1)
    check("snapshot tras R: la orden que reaparece sigue su ciclo; la que no, termina por limpieza",
          m.ciclo["limpieza del libro"] == 1 and m.ciclo["viva al final"] == 2 and o1 is not None and o1[O_TADD] == 1)

    # 8 ------------------------------------------ huérfanas
    m = correr([(1, "C", "B", 100, 1, 999, L), (2, "M", "A", 105, 3, 998, L)])
    check("huérfanas: una C desconocida se cuenta; una M desconocida reconstruye la orden (trae su estado)",
          m.conteo["huerfana_C"] == 1 and m.conteo["recuperada_con_M"] == 1 and m.libros[1].ordenes[998][O_TAM] == 3)

    # --- simulaciones contra la verdad ---
    arr_f, ver_f = simular(cfg, horas=3, semilla=3)
    rf = callado(analizar, arr_f, cfg, verdad=ver_f, chequear_paridad=False, verbose=False)
    arr_s, ver_s = simular(cfg, horas=1.5, semilla=4, fills=False)
    rs = callado(analizar, arr_s, cfg, verdad=ver_s, chequear_paridad=False, verbose=False)

    # 9 ------------------------------------------ el libro y el ciclo de vida, exactos
    ok9 = all(r.medicion["libro_identico"] and r.medicion["ciclo_igual"] and r.medicion["exactos_iguales"]
              and r.medicion["llenado"][0] == r.medicion["llenado"][1] for r in (rf, rs))
    check("simulación: libro final, ciclo de vida, barridos de un agresor y contratos llenados IDÉNTICOS a la verdad "
          "(con F y sin F)", ok9, f"{len(arr_f) + len(arr_s):,} registros")

    # 10 ----------------------------------------- integridad
    check("cordura en verde en la simulación y huérfanas = las inyectadas",
          all(ok for ok, _ in rf.cordura) and rf.medicion["huerfanas"][0] == rf.medicion["huerfanas"][1] > 0,
          f"{rf.medicion['huerfanas'][0]} huérfanas")

    # 11 ----------------------------------------- detección y clasificación de los plantados
    md = rf.medicion
    check("barridos plantados: ≥ 95 % detectados y ≥ 85 % con la clase correcta",
          md["detectados"] >= 0.95 * md["plantados"] and md["bien"] >= 0.85 * md["detectados"],
          f"{md['detectados']}/{md['plantados']} detectados · {md['bien']} bien clasificados")

    # 12 ----------------------------------------- tu detector
    check("tu detector: con registros F no ve ningún barrido (mezcla el lado del agresor con el pasivo); sin F sí",
          rf.comparacion["tuyas"] == 0 and rs.comparacion["tuyas"] > 0 and rs.comparacion["coinciden"] > 0,
          f"con F {rf.comparacion['tuyas']} · sin F {rs.comparacion['tuyas']} ({rs.comparacion['coinciden']} coinciden)")

    # 13 ----------------------------------------- órdenes grandes
    g = md["grandes"]
    gen = sum(v for (t, r), v in g.items() if t == "genuina" and r != "no marcada")
    gen_ok = sum(v for (t, r), v in g.items() if t == "genuina" and r in ("ejecutada", "parcial"))
    ret = sum(v for (t, r), v in g.items() if t == "retirada" and r != "no marcada")
    ret_ok = sum(v for (t, r), v in g.items() if t == "retirada" and r.startswith("retirada"))
    check("órdenes grandes: las genuinas terminan ejecutadas y las 'spoof' retiradas",
          gen and ret and gen_ok >= 0.75 * gen and ret_ok >= 0.75 * ret,
          f"genuinas ejecutadas {gen_ok}/{gen} · retiradas {ret_ok}/{ret}")

    # 14 ----------------------------------------- la ruta de Databento: DBN, to_ndarray y registro por registro
    if db is not None:
        try:
            sub = arr_s[:40_000]
            tienda = db.DBNStore.from_bytes(a_dbn(sub, cfg))
            r_dbn = callado(analizar, tienda, replace(cfg, tam_bloque=7_777), verbose=False)
            r_arr = callado(analizar, sub, cfg, chequear_paridad=False, verbose=False)
            ok14 = (r_dbn.paridad["igual"] and r_dbn.paridad["registros"] == len(sub)
                    and r_dbn.motor.ciclo == r_arr.motor.ciclo and r_dbn.motor.exactos == r_arr.motor.exactos
                    and libro_de(r_dbn.motor) == libro_de(r_arr.motor))
            check("DBN de verdad: bloques de 7 777 = arreglo, y la ruta de Live (MBOMsg uno a uno) = la de bloques",
                  bool(ok14), f"{len(sub):,} registros")
        except Exception as e:                                    # pragma: no cover
            check("DBN de verdad", False, repr(e))
    else:
        print("  · databento no está instalado: se salta la prueba del DBN")

    # 15 ----------------------------------------- Live: snapshot, caída, reconexión y Telegram
    if db is not None:
        import databento_dbn as dd
        import urllib.request
        arr_l, _ = simular(cfg, horas=0.5, semilla=6)
        recs = list(db.DBNStore.from_bytes(a_dbn(arr_l, cfg)))
        k = next(i for i in range(len(recs) // 3, len(recs)) if recs[i].flags & F_LAST) + 1
        corte = Rastreador(cfg, con_tuyo=False)
        corte.procesar_arreglo(arr_l[:k])
        ts_c = int(arr_l["ts_event"][k - 1])
        snap = []
        for iid, lb in corte.libros.items():
            snap.append(dd.MBOMsg(publisher_id=1, instrument_id=iid, ts_event=ts_c, order_id=0, price=UNDEF_PRICE,
                                  size=0, action=dd.Action.CLEAR, side=dd.Side.NONE, ts_recv=ts_c, flags=F_SNAPSHOT,
                                  channel_id=0, ts_in_delta=0, sequence=0))
            for oid, o in lb.ordenes.items():
                snap.append(dd.MBOMsg(publisher_id=1, instrument_id=iid, ts_event=ts_c, order_id=oid, price=o[O_PRECIO],
                                      size=o[O_TAM], action=dd.Action.ADD,
                                      side=dd.Side.BID if o[O_LADO] > 0 else dd.Side.ASK, ts_recv=ts_c,
                                      flags=F_SNAPSHOT, channel_id=0, ts_in_delta=0, sequence=0))
        snap[-1] = dd.MBOMsg(publisher_id=1, instrument_id=snap[-1].instrument_id, ts_event=ts_c,
                             order_id=snap[-1].order_id, price=snap[-1].price, size=snap[-1].size,
                             action=dd.Action.ADD, side=snap[-1].side, ts_recv=ts_c, flags=F_SNAPSHOT | F_LAST,
                             channel_id=0, ts_in_delta=0, sequence=0)

        class _Live:
            def __init__(self, r, cae):
                self.r, self.cae, self.sub, self.parado = r, cae, None, False

            def subscribe(self, **kw):
                self.sub = kw

            def __iter__(self):
                yield from self.r
                if self.cae:
                    raise ConnectionError("se cayó la conexión")

            def stop(self):
                self.parado = True

        clientes = [_Live(recs[:k], True), _Live(snap + recs[k:], False)]
        usados = []

        def fabrica():
            c = clientes[len(usados)]
            usados.append(c)
            return c

        capturas = []

        def _tg(req, timeout=None):
            capturas.append(req.data or b"")
            return io.BytesIO(json.dumps({"ok": True, "result": {}}).encode())

        entorno = {v: os.environ.get(v) for v in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")}
        viejo = urllib.request.urlopen
        t_falso = [0.0]

        def reloj():
            t_falso[0] += 10.0
            return t_falso[0]

        try:
            os.environ["TELEGRAM_BOT_TOKEN"] = "123456789:" + "C" * 35
            os.environ["TELEGRAM_CHAT_ID"] = "987654321"
            urllib.request.urlopen = _tg
            cl = replace(cfg, telegram_live=True)
            motor = callado(correr_live, cl, fabrica=fabrica, max_registros=k + len(snap) + len(recs) - k,
                            dormir=lambda s: None, reloj=reloj)
            directo = Rastreador(cfg, con_tuyo=False)
            directo.procesar_arreglo(arr_l)
            directo.terminar()
            textos = [urllib.parse.unquote_plus(c.decode()) for c in capturas]
            ok15 = (libro_de(motor) == libro_de(directo) and all(motor.ciclo[x] == directo.ciclo[x] for x in MOTIVOS)
                    and motor.exactos == directo.exactos and motor.conteo["reconexiones"] == 1
                    and all(c.sub["snapshot"] and c.parado for c in usados) and len(usados) == 2
                    and any("ACTIVADO" in t for t in textos) and any("APAGADO" in t for t in textos)
                    and (not directo.barridos or any("BARRIDO" in t for t in textos)))
            check("Live: snapshot, caída y reconexión con libro reconstruido = el cálculo de un jalón; avisos por Telegram",
                  bool(ok15), f"{len(recs):,} registros · {len(directo.barridos)} barridos · {len(capturas)} mensajes")
        except Exception as e:                                    # pragma: no cover
            check("Live con clientes falsos", False, repr(e))
        finally:
            urllib.request.urlopen = viejo
            for v_, x in entorno.items():
                if x is None:
                    os.environ.pop(v_, None)
                else:
                    os.environ[v_] = x

    # 16 ----------------------------------------- la cola de Telegram agrupa en vez de tirar
    import urllib.request
    import urllib.parse
    env0 = {v: os.environ.get(v) for v in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")}
    viejo = urllib.request.urlopen
    enviados = []
    try:
        os.environ["TELEGRAM_BOT_TOKEN"] = "123456789:" + "D" * 35
        os.environ["TELEGRAM_CHAT_ID"] = "987654321"
        urllib.request.urlopen = lambda req, timeout=None: (enviados.append(req.data), io.BytesIO(b'{"ok": true}'))[1]
        reloj_ = [100.0]
        cola = ColaTelegram(cfg, reloj=lambda: reloj_[0])
        for i in range(3):
            cola.poner(f"alerta {i}")
            cola.vaciar()
        n1 = len(enviados)
        reloj_[0] += 3
        cola.vaciar()
        ok16 = n1 == 1 and len(enviados) == 2 and not cola.pend and "alerta+1" in urllib.parse.unquote(enviados[1].decode())
    finally:
        urllib.request.urlopen = viejo
        for v_, x in env0.items():
            if x is None:
                os.environ.pop(v_, None)
            else:
                os.environ[v_] = x
    check("Telegram: lo que llega dentro de los 2 s se agrupa y sale después (tu versión lo tiraba)", bool(ok16))

    # 17 ----------------------------------------- reportes, tableros y archivos
    with tempfile.TemporaryDirectory() as tmp:
        rr = replace(rf, cfg=replace(rf.cfg, salida_dir=tmp))
        texto = io.StringIO()
        try:
            with contextlib.redirect_stdout(texto):
                reporte_datos(rr)
                reporte_ciclo(rr)
                reporte_barridos(rr)
                reporte_grandes(rr)
                reporte_auditoria(rr)
                reporte_cordura(rr)
                reporte_verdad(rr)
                rutas, plt_, _ = tableros(rr, mostrar=False)
                guardar(rr)
            archivos = sorted(p.name for p in Path(tmp).iterdir())
            if plt_ is not None:
                plt_.close("all")
            check("reportes, 2 tableros PNG y 4 CSV sin errores",
                  len(rutas) == 2 and all(p.stat().st_size > 50_000 for p in rutas)
                  and sum(a.endswith(".csv") for a in archivos) == 4 and "CONTRA LA VERDAD" in texto.getvalue(),
                  ", ".join(archivos))
        except Exception as e:                                    # pragma: no cover
            check("reportes, tableros y CSV", False, repr(e))

    # 18 ----------------------------------------- línea de comandos
    a_ = construir_parser().parse_args(["--simbolo", "6e", "--start", "2026-09-20T21:00:00", "--fin",
                                        "2026-09-23T21:00:00", "--ventana-ms", "50", "--horizonte", "10",
                                        "--telegram-live", "--sin-fills"])
    c_ = config_desde_args(a_)
    check("línea de comandos: --start/--inicio, --end/--fin, --simbolo 6E → 6E.n.0, --ventana-ms, --horizonte",
          c_.symbol == "6E.n.0" and c_.start.startswith("2026-09-20") and c_.gap_ms == 50 and c_.horizonte_s == 10
          and c_.telegram_live and not c_.sim_fills and tick_int(c_) == 50_000)

    # 19 ----------------------------------------- Telegram: nunca el token
    tok = "123456789:" + "A" * 35
    msg = _sin_token(f"fallo en https://api.telegram.org/bot{tok}/sendMessage", tok)
    check("los errores de Telegram nunca muestran el token", tok not in msg and "…" in msg)

    # 20 ----------------------------------------- multipart de sendPhoto, sin red
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
    png = Path(tempfile.gettempdir()) / "_prueba_telegram_rid.png"
    bien = False
    try:
        urllib.request.urlopen = _falso
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
        ok = llamar_telegram(tok, "sendPhoto", {"chat_id": "123456789", "caption": "á <b>"},
                             archivo=("photo", png)).get("ok")
        cuerpo = capturas[-1].data
        limite = capturas[-1].get_header("Content-type").split("boundary=")[1]
        bien = (ok and cuerpo.startswith(f"--{limite}".encode()) and cuerpo.rstrip().endswith(f"--{limite}--".encode())
                and b'name="photo"; filename="_prueba_telegram_rid.png"' in cuerpo and tok.encode() not in cuerpo)
    finally:
        urllib.request.urlopen = viejo
        png.unlink(missing_ok=True)
    check("Telegram: el multipart de sendPhoto está bien formado y no lleva el token", bool(bien))

    # 21 ----------------------------------------- ninguna key escrita en este archivo
    fuente = Path(__file__).read_text(encoding="utf-8")
    check("no hay API keys ni tokens escritos en el código",
          not re.search("db" + "-" + r"[A-Za-z0-9]{20,}", fuente)
          and not re.search(r"\d{8,10}:" + r"[A-Za-z0-9_-]{35}", fuente))

    # 22 ----------------------------------------- mensajes de Telegram
    txt = mensaje_telegram(rf)
    tb = texto_barrido(rf.motor.barridos[0], cfg) if rf.motor.barridos else "<b>"
    check("los mensajes de Telegram caben y escapan el HTML", len(txt) <= 4096 and "<b>" in txt and "<b>" in tb,
          f"{len(txt)} caracteres")

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
