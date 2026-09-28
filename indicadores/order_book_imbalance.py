# -*- coding: utf-8 -*-
"""
ORDER BOOK IMBALANCE AC v2 — OFI de Cont-Kukanov-Stoikov normalizado + OBI ponderado por tiempo
Datos: Databento MBP-1 (GLBX.MDP3), evento por evento, con higiene de alta frecuencia.

Qué hace, en una línea: lee el mejor bid/ask del NQ evento por evento (MBP-1) y lo limpia.
Con eso mide el flujo de órdenes con la ecuación de Cont-Kukanov-Stoikov (normalizada para
leerse en ticks) y el imbalance del libro ponderado por el tiempo que duró cada estado. Cada
motor da alertas con z robusto e histéresis. Después audita qué pasa tras cada alerta y si
los datos y el cálculo pasan un chequeo de cordura.

LO QUE PEDISTE, HECHO A FONDO

  1. OPTIMIZACIÓN DEL ORDER BOOK IMBALANCE — ECUACIÓN CKS (2014) NORMALIZADA. Cada evento
     aporta e = 1{Pᵇ ≥ Pᵇ₀}qᵇ − 1{Pᵇ ≤ Pᵇ₀}qᵇ₀ − 1{Pᵃ ≤ Pᵃ₀}qᵃ + 1{Pᵃ ≥ Pᵃ₀}qᵃ₀, con precios
     en ticks enteros (comparaciones exactas). El flujo se reinicia en cada sesión, en cada
     roll y tras 5 min sin eventos. El OFI se normaliza por 2 × la profundidad ponderada por
     tiempo, así que se lee en TICKS: es el movimiento que ese flujo "explica". Contra el
     cambio del mid a 10 s, en simulación: pendiente 0.70 y R² 0.58-0.59. Sin normalizar el
     R² baja a 0.36, y sólo con las operaciones a 0.06.

  2. OBI PONDERADO POR TIEMPO. Cada estado del libro pesa lo que DURÓ, en nanosegundos,
     repartido entre los segundos y barras que toca. No cuenta más allá del cierre de su
     sesión ni de un hueco. Tu promedio por evento le da el mismo peso a un estado de 3
     minutos que a uno de 3 microsegundos. En la simulación, con ráfagas de "parpadeo" de
     cotizaciones, la diferencia por barra llega a 0.34-0.66 (p99 0.13-0.20). Pesa en las
     barras de pocos eventos donde cae una ráfaga.

  3. Z-SCORE ROBUSTO ESTRICTO. (x − mediana) / (1.4826 · MAD) de las 288 barras ANTERIORES:
     la barra actual no entra en su propia escala. Sin historia suficiente no hay z (tu
     fillna(0) decía "0 = sin señal" todo el primer día), ni tampoco si la MAD es 0. Para el
     OFI se toma primero OFI / √Σe²: así una barra de las 3 a.m. con 40 eventos y una de la
     apertura con 4 000 hablan en la misma escala. En una simulación SIN flujo informado da
     11 alertas en 6 sesiones, contra 106 si sólo se normaliza por profundidad (la apertura
     parece choque todos los días).

  4. HIGIENE DE DATOS DE ALTA FRECUENCIA. Siete reglas en orden, cada registro contado en la
     primera que falla: banderas F_MAYBE_BAD_BOOK / F_BAD_TS_RECV; sólo el libro al cierre de
     cada evento (F_LAST); precio indefinido o tamaño 0; libro cruzado o trabado; spread de
     más de 8 ticks; limpieza de libro (R); precio fuera del tick. Precios enteros exactos
     con to_df(price_type="fixed"). El DBN se guarda en disco y se lee en bloques de
     2 000 000 registros, arrastrando el estado de un bloque al siguiente. Una prueba inyecta
     4 534 registros defectuosos y verifica que el resultado sea IDÉNTICO al de los datos
     limpios.

  5. GESTIÓN DE ALERTAS POR HISTÉRESIS. Un disparador de Schmitt por motor y dirección: entra
     con |z| ≥ 3, se queda mientras |z| ≥ 1 y avisa cuando sale. Voltea si cruza −3, se
     reinicia en cada sesión y admite un periodo refractario. Una alerta por episodio, no
     una por barra. Tu enfriamiento de 4 h es común a las dos direcciones: una compra a las
     9:00 silencia una venta a las 10:00.

  6. ARQUITECTURA DE DOBLE MOTOR, en dos sentidos:
       · de SEÑAL: el motor estático (OBI por tiempo: quién tiene más cola) y el dinámico (OFI
         de CKS: quién mete y saca órdenes). Cada uno tiene su z y su histéresis, y la
         CONFLUENCIA es cuando los dos empujan igual;
       · de CÁLCULO: un motor vectorizado por bloques para la historia y uno incremental,
         registro por registro, para usarlo en vivo. Dan lo mismo a 1e-13, y cada corrida lo
         verifica sobre los primeros 60 000 registros de tus datos.

  7. AUDITORÍA Y CHEQUEO DE CORDURA:
       · la regresión de CKS: la del módulo, sin higiene, con tu fórmula, sin normalizar y
         sólo con operaciones;
       · la curva OBI → probabilidad de que el siguiente tick suba;
       · el mid a 1, 3, 6 y 12 barras después de cada entrada, con t y tasa de acierto;
       · las alertas por hora del día y el OBI por tiempo contra el OBI por evento;
       · la cascada de la higiene;
       · una lista ✓/⚠: estados válidos, precios fuera del tick, pendiente y R² de CKS, que
         la curva sea monótona, cobertura del libro en horario regular, latencia, ts_event
         que retrocede y la paridad de los dos motores.

  Además: un simulador de libro (modelo de colas) que escribe un archivo DBN de verdad y
  recorre la misma ruta que tus datos; 24 pruebas internas; CSV de barras, alertas y
  auditoría; Telegram; y --esquema bbo-1s, más barato y aproximado.

QUÉ SE MIDIÓ — 4 simulaciones, 24 sesiones, 92 ráfagas de flujo informado conocidas

        motor               alertas   caen en una ráfaga   ráfagas vistas
        módulo · OFI           48            60 %            30 de 92
        tu script · OFI        31            23 %             7 de 92
        OBI (ambos)         40 / 10           0 %             0

  · El OBI no ve ráfagas de minutos, y es lo esperado: anticipa el SIGUIENTE tick. P(que
    suba) va de 5-7 % con OBI < −0.8 a 93-95 % con OBI > 0.8; a 5 min eso se diluye
    (correlación con la barra siguiente ≈ 0.06).
  · Tu OFI acumula +170 a +423 contratos por sesión que no vienen del mercado.

QUÉ FALLABA EN EL SCRIPT QUE MANDASTE (los comentarios [v2] lo marcan en el código)

  · LA API KEY ESTÁ ESCRITA EN LA LÍNEA 55. Dala por publicada y regenérala. Aquí se lee de
    DATABENTO_API_KEY, igual que en tus otros módulos.

  · EL LADO ASK DE TU OFI TIENE LOS TAMAÑOS CRUZADOS. Si el ask sube, tu fórmula cuenta la
    cola nueva en lugar de la que se retiró; si baja, la vieja en lugar de la nueva. La
    ecuación de CKS es antisimétrica (el libro en espejo da el OFI opuesto) y la tuya no:
    falla en el 81 % de los eventos de la prueba y acumula un sesgo alcista. Ojo: tu fórmula
    da MÁS R² (0.67 contra 0.58) porque en cada subida suma las dos colas nuevas y mete en
    la variable parte del propio movimiento. Más R² no la hace correcta.

  · "Precios enteros (nanodólares)" no es cierto: to_df() entrega float por omisión, así que
    tu Microprice / PRICE_SCALE sale en 0.00002. Aquí se piden enteros exactos
    (price_type="fixed"). Y ese "Microprice" es el mid ponderado por las colas, no el
    microprecio de Stoikov (2018); el ajuste de un paso de Stoikov es la curva de la
    auditoría.

  · CINCO DÍAS DE MBP-1 A LA MEMORIA. get_range(...).to_df() de una vez son decenas de
    millones de filas con 19 columnas en la RAM.

  · SIN HIGIENE. Usas los estados intermedios de cada operación, libros cruzados, tamaños 0 y
    la pre-apertura, y el primer registro del domingo se compara contra el último del
    viernes, o contra el contrato anterior en un roll.

  · TU Z SE ESCONDE Y NO VE LA HORA. Su ventana incluye la barra actual, así que su valor
    máximo posible es 16.9 y un choque de 10σ sale en ~8.6. fillna(0) inventa "sin señal"
    donde no hay dato. Y 288 barras mezclan la noche con la apertura: la apertura parece
    choque todos los días (además, una sesión de Globex tiene 276 barras de 5 min, no 288).

  · TUS UMBRALES DE OBI (±0.70 sobre el promedio de 5 min) se alcanzan en menos del 0.5 % de
    las barras de la simulación, y el enfriamiento de 4 h tapa alertas de la otra dirección.

  · Menores: try/except Exception esconde el error real ("Error crítico: …") y las etiquetas
    "Probable Rebote / Probable Caída" nunca se verifican; aquí las verifica la auditoría.

LÍMITES QUE CONVIENE SABER
  · Con barras de 5 min el motor OBI pesa poco: su fuerza está en el siguiente tick (la curva
    de la auditoría). La alerta que la simulación valida es la del OFI, a 5 min; con barras
    de 1 min cada barra tiene menos eventos y en la simulación ya no acierta.
  · MBP-1 sólo ve el mejor nivel. La pendiente de CKS (0.70, no 1) refleja que la
    profundidad detrás del primer nivel no es igual a la del primero.
  · Las ráfagas de la simulación son de órdenes de mercado. El flujo informado real también
    usa órdenes límite, y la auditoría de tus datos es la que decide.
  · MBP-1 del NQ son varios GB por semana: antes de descargar se revisa el costo (--costo-max,
    25 USD por omisión). --esquema bbo-1s es mucho más barato, pero el OFI sale de fotos de 1
    segundo y pierde lo que pasa dentro del segundo.

CÓMO SE USA
    pip install numpy pandas matplotlib databento
    python order_book_imbalance.py --pruebas                 # 24 pruebas, sin red
    python order_book_imbalance.py --simulacion              # libro simulado con verdad conocida
    python order_book_imbalance.py                           # NQ, 16-20 de agosto de 2026, 5 min
    python order_book_imbalance.py --z-entrada 3.5 --z-salida 1.5 --refractario 3
    python order_book_imbalance.py --simbolo ES --start 2026-09-21 --end 2026-09-26
    python order_book_imbalance.py --esquema bbo-1s          # más barato, aproximado
    python order_book_imbalance.py --telegram                # resumen + 2 tableros
    python order_book_imbalance.py --telegram-solo-alertas   # sólo si una alerta ENTRA en la última barra
    python order_book_imbalance.py --telegram-solo-alertas --telegram-confluencia
  Las horas van en hora de CHICAGO y de CDMX. Con --sin-paridad se salta el chequeo del
  motor incremental.

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
  Cont, R., Kukanov, A. y Stoikov, S. (2014), "The price impact of order book events",
      Journal of Financial Econometrics 12(1). — la ecuación del OFI y su normalización.
  Cont, R. y de Larrard, A. (2013), "Price dynamics in a Markovian limit order market", SIAM
      Journal on Financial Mathematics 4(1). — el modelo de colas del simulador.
  Gould, M. y Bonart, J. (2016), "Queue imbalance as a one-tick-ahead price predictor in a
      limit order book", Market Microstructure and Liquidity 2(2). — la curva del OBI.
  Stoikov, S. (2018), "The micro-price: a high-frequency estimator of future prices",
      Quantitative Finance 18(12).
  Rousseeuw, P. y Croux, C. (1993), "Alternatives to the median absolute deviation", JASA
      88(424). — la MAD y su factor 1.4826.
  Databento: https://databento.com/docs — esquemas MBP-1 y BBO, banderas F_LAST,
      F_MAYBE_BAD_BOOK y F_BAD_TS_RECV, price_type="fixed".
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
from dataclasses import dataclass, replace
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

try:
    import databento as db
except ModuleNotFoundError:
    db = None

IDENTIFICADOR = "order-book-imbalance-ac-v2"
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)
np.seterr(all="ignore")

# --- Constantes de la sesión de CME Globex ---
MINUTOS_SESION = 1380            # 17:00 → 16:00 CT (23 horas)
DESFASE_H = 7                    # hora CT + 7 h → la sesión que abre a las 17:00 cae en su fecha
NS = 1_000_000_000

# --- Banderas de los registros de Databento (databento_dbn) ---
F_LAST = 128                     # último registro de un evento: el libro ya es consistente
F_TOB = 64
F_SNAPSHOT = 32
F_MBP = 16
F_BAD_TS_RECV = 8                # la hora de recepción no es confiable
F_MAYBE_BAD_BOOK = 4             # el libro puede estar mal (hueco en el feed)
UNDEF_PRICE = 9223372036854775807

# Raíz → (nombre, tamaño del tick, precio de referencia para la simulación)
CATALOGO = {
    "NQ": ("Nasdaq 100", 0.25, 20000.0), "MNQ": ("Micro Nasdaq 100", 0.25, 20000.0),
    "ES": ("S&P 500", 0.25, 5500.0), "MES": ("Micro S&P 500", 0.25, 5500.0),
    "YM": ("Dow Jones", 1.0, 42000.0), "RTY": ("Russell 2000", 0.1, 2200.0),
    "ZN": ("Nota 10 años", 1 / 64, 110.0), "ZB": ("Bono 30 años", 1 / 32, 118.0),
    "GC": ("Oro", 0.1, 2500.0), "SI": ("Plata", 0.005, 30.0), "HG": ("Cobre", 0.0005, 4.3),
    "CL": ("Crudo WTI", 0.01, 75.0), "NG": ("Gas natural", 0.001, 2.6),
    "6E": ("Euro", 0.00005, 1.10), "6J": ("Yen", 0.0000005, 0.0068),
    "6M": ("Peso mexicano", 0.00001, 0.055),
}


# =============================================================================
# 1. CONFIGURACIÓN
# =============================================================================
@dataclass(frozen=True)
class Config:
    # --- Datos ---
    dataset: str = "GLBX.MDP3"
    symbol: str = "NQ.n.0"
    start: str = "2026-08-16T00:00:00"     # tu ventana: 16 al 20 de agosto de 2026
    end: str = "2026-08-21T00:00:00"       # exclusivo (tu script: 2026-08-20T23:59)
    dias_calentamiento: int = 1            # sesiones previas para que el z tenga historia
    esquema: str = "mbp-1"                 # mbp-1 (cada evento) o bbo-1s (más barato, aproximado)
    cache_dir: str = "datos_databento"
    usar_cache: bool = True
    salida_dir: str = "salidas_obi"
    costo_max_usd: float = 25.0
    bloque: int = 2_000_000                # registros por bloque al leer el DBN
    tz_mercado: str = "America/Chicago"
    tz_local: str = "America/Mexico_City"

    # --- Higiene de datos de alta frecuencia ---
    solo_f_last: bool = True               # sólo el libro al CIERRE de cada evento
    spread_max_ticks: int = 8              # más ancho = libro delgado (pre-apertura, pánico)
    hueco_max_s: float = 300.0             # sin eventos más que esto: el libro ya no es actual

    # --- Barras y z-score robusto ---
    barra_s: int = 300                     # 5 min, como tu script
    z_ventana: int = 288                   # barras previas (tu OFI_Z_WINDOW)
    z_min: int = 60                        # barras previas mínimas para dar un z
    cks_s: int = 10                        # intervalo de la regresión de Cont-Kukanov-Stoikov

    # --- Alertas por histéresis ---
    z_entrada: float = 3.0                 # tu UMBRAL_OFI_Z
    z_salida: float = 1.0
    refractario: int = 0                   # barras sin reentrar en la MISMA dirección
    obi_nivel: float = 0.70                # tu UMBRAL_OBI_REBOTE (se reporta cuánto se alcanza)

    # --- Auditoría ---
    horizontes: tuple[int, ...] = (1, 3, 6, 12)
    cubetas_obi: int = 10

    # --- Simulación ---
    sim_sesiones: int = 6
    sim_eventos: int = 60_000              # eventos de libro por sesión
    sim_episodios: int = 4                 # ráfagas de flujo informado por sesión
    sim_semilla: int = 0

    # --- Telegram ---
    telegram_confluencia: bool = False     # sólo alertar cuando los dos motores coinciden


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


def t_newey_west(x: np.ndarray, rezagos: int) -> float:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 8:
        return np.nan
    d = x - x.mean()
    s = float((d * d).sum() / n)
    for j in range(1, min(int(rezagos), n - 1) + 1):
        s += 2.0 * (1.0 - j / (rezagos + 1.0)) * float((d[j:] * d[:-j]).sum() / n)
    return float(x.mean() / math.sqrt(s / n)) if s > 0 else np.nan


def sesion_y_minuto(idx_utc: pd.DatetimeIndex, tz_mercado: str) -> tuple[np.ndarray, np.ndarray]:
    """Fecha de sesión de Globex y minuto dentro de la sesión (0 = 17:00 CT)."""
    pared = idx_utc.tz_convert(tz_mercado).tz_localize(None)     # hora de pared de Chicago
    corrida = pared + pd.Timedelta(hours=DESFASE_H)
    return (corrida.normalize().to_numpy(),
            (corrida.hour * 60 + corrida.minute).to_numpy().astype(int))


def minuto_de_sesion(hhmm_ct: str) -> int:
    h, m = (int(x) for x in hhmm_ct.strip().split(":"))
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(f"Hora inválida: {hhmm_ct!r} (usa HH:MM, hora de Chicago)")
    return ((h + DESFASE_H) % 24) * 60 + m


def reloj(fecha_sesion, minuto: int, cfg: Config) -> tuple[pd.Timestamp, pd.Timestamp]:
    """(hora CT, hora CDMX) del minuto `minuto` de la sesión con fecha `fecha_sesion`."""
    pared = pd.Timestamp(fecha_sesion).normalize() - pd.Timedelta(hours=DESFASE_H) \
        + pd.Timedelta(minutes=int(minuto))
    ct = pared.tz_localize(cfg.tz_mercado, ambiguous=False, nonexistent="shift_forward")
    return ct, ct.tz_convert(cfg.tz_local)


def raiz(symbol: str) -> str:
    return symbol.split(".")[0].upper()


def simbolo_continuo(s: str) -> str:
    s = s.strip()
    return s if "." in s else f"{s.upper()}.n.0"


def nombre(symbol: str) -> str:
    return CATALOGO.get(raiz(symbol), (raiz(symbol), 0.0, 100.0))[0]


def tick(symbol: str) -> float:
    t = CATALOGO.get(raiz(symbol), ("", 0.0, 100.0))[1]
    if t <= 0:
        sys.exit(f"❌ No conozco el tick de {symbol}. Agrégalo a CATALOGO (raíz → nombre, tick, precio).")
    return t


def tick_ns(symbol: str) -> int:
    return int(round(tick(symbol) * NS))


def validar(cfg: Config) -> None:
    if cfg.esquema not in ("mbp-1", "bbo-1s"):
        sys.exit("❌ --esquema va mbp-1 (cada evento del libro) o bbo-1s (una foto por segundo).")
    if cfg.barra_s < 10 or (MINUTOS_SESION * 60) % cfg.barra_s:
        sys.exit(f"❌ --barra {cfg.barra_s} s debe dividir exacto la sesión de 82 800 s (p. ej. 60, 300, 900).")
    if cfg.barra_s % cfg.cks_s and cfg.cks_s > cfg.barra_s:
        sys.exit("❌ El intervalo CKS debe ser menor que la barra.")
    if not (0 < cfg.z_salida < cfg.z_entrada):
        sys.exit("❌ La histéresis necesita 0 < --z-salida < --z-entrada.")
    if cfg.z_min < 20 or cfg.z_min > cfg.z_ventana:
        sys.exit("❌ Hace falta 20 ≤ z_min ≤ --z-ventana.")


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
    "  • La que estaba escrita en la línea 55 de order_blook_deepseek.py hay que darla por\n"
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


def inicio_descarga(cfg: Config) -> pd.Timestamp:
    """--start menos `dias_calentamiento` sesiones hábiles, para que el z ya tenga historia."""
    t = pd.Timestamp(cfg.start)
    return t - pd.offsets.BDay(cfg.dias_calentamiento) if cfg.dias_calentamiento > 0 else t


def obtener_datos(cfg: Config, cliente=None):
    """
    Descarga a DISCO (no a memoria) y devuelve el DBNStore; el motor lo lee por bloques.

    [v2] Tu script hace get_range(...).to_df() de cinco días de MBP-1 del NQ de un jalón:
    son decenas de millones de registros con 19 columnas en la RAM. Aquí el archivo se
    guarda en caché y se procesa en bloques de `bloque` registros, arrastrando el estado
    del libro de un bloque al siguiente.
    """
    carpeta = _ruta(cfg.cache_dir)
    carpeta.mkdir(parents=True, exist_ok=True)
    inicio = inicio_descarga(cfg).strftime("%Y-%m-%dT%H:%M:%S")
    ruta = carpeta / (_nombre_seguro(cfg.dataset, cfg.symbol, inicio, cfg.end, cfg.esquema) + ".dbn.zst")
    if ruta.exists() and cfg.usar_cache:
        print(f"📂 Usando caché local: {ruta.name}")
        return db.DBNStore.from_file(ruta)
    cliente = cliente or conectar()
    params = dict(dataset=cfg.dataset, symbols=[cfg.symbol], stype_in="continuous",
                  schema=cfg.esquema, start=inicio, end=cfg.end)
    costo = cliente.metadata.get_cost(**params)
    try:
        tam = cliente.metadata.get_billable_size(**params)
    except Exception:
        tam = float("nan")
    print(f"💵 Costo estimado: US$ {costo:,.2f} · {tam / 1e9:,.2f} GB sin comprimir "
          f"({cfg.symbol}, {cfg.esquema}, {inicio[:10]} → {cfg.end[:10]})")
    if costo > cfg.costo_max_usd:
        sys.exit(f"💰 El costo (US$ {costo:,.2f}) supera tu tope de US$ {cfg.costo_max_usd:,.2f}.\n"
                 f"   Si estás de acuerdo:  --costo-max {math.ceil(costo) + 1}\n"
                 f"   Más barato y aproximado:  --esquema bbo-1s  (una foto del libro por segundo)")
    temporal = ruta.with_name(ruta.name + ".parcial")
    temporal.unlink(missing_ok=True)
    print(f"📡 Descargando {cfg.symbol} ({cfg.esquema}) a {ruta.name} …")
    cliente.timeseries.get_range(**params, path=temporal)
    temporal.replace(ruta)
    return db.DBNStore.from_file(ruta)


# =============================================================================
# 3. HIGIENE Y MOTOR DE EVENTOS — vectorizado por bloques, con estado entre bloques
# =============================================================================
REGLAS = ("bandera de libro dudoso", "no es el cierre del evento (F_LAST)", "precio indefinido o tamaño 0",
          "libro cruzado o trabado", "spread demasiado ancho", "limpieza de libro (R)",
          "precio fuera del tick")


def higiene(flags: np.ndarray, accion: np.ndarray, bpx: np.ndarray, apx: np.ndarray,
            bsz: np.ndarray, asz: np.ndarray, tick_ns_: int, cfg: Config,
            usar_last: bool) -> tuple[np.ndarray, np.ndarray, dict]:
    """
    ¿Qué registros son un estado VÁLIDO del mejor bid/ask? Se aplica en orden y cada
    registro se cuenta en la primera regla que lo descarta:
      1. banderas F_MAYBE_BAD_BOOK o F_BAD_TS_RECV (el propio feed avisa);
      2. sin F_LAST: estados intermedios de un mismo evento (p. ej. la operación antes de
         que el libro se actualice) — sólo cuenta el libro al cierre del evento;
      3. precio indefinido o tamaño 0 en un lado;
      4. libro cruzado o trabado (bid ≥ ask);
      5. spread mayor a `spread_max_ticks` (pre-apertura, libro vacío);
      6. limpieza de libro ('R'): reinicia el flujo;
      7. precio que no es múltiplo del tick.
    Devuelve (válido, reinicio, conteos). `reinicio` marca los registros 'R'.

    [v2] Tu script usa TODOS los registros: el estado intermedio de cada operación, libros
    cruzados, tamaños 0 y el primer registro después del fin de semana, que compara el
    libro del lunes contra el del viernes.
    """
    n = len(flags)
    malo = (flags & (F_MAYBE_BAD_BOOK | F_BAD_TS_RECV)) != 0
    no_last = ((flags & F_LAST) == 0) if usar_last else np.zeros(n, bool)
    indef = (bpx == UNDEF_PRICE) | (apx == UNDEF_PRICE) | (bsz <= 0) | (asz <= 0)
    with np.errstate(all="ignore"):
        cruzado = ~indef & (bpx >= apx)
        ancho = ~indef & ((apx - bpx) > cfg.spread_max_ticks * tick_ns_)
        fuera = ~indef & (((bpx % tick_ns_) != 0) | ((apx % tick_ns_) != 0))
    limpia = accion == "R"
    orden = (malo, no_last, indef, cruzado, ancho, limpia, fuera)
    queda = np.ones(n, bool)
    conteo = {}
    for nombre_, m in zip(REGLAS, orden):
        quita = queda & m
        conteo[nombre_] = int(quita.sum())
        queda &= ~m
    return queda, limpia & ~malo, conteo


def ofi_cks(bt: np.ndarray, at: np.ndarray, bs: np.ndarray, as_: np.ndarray,
            bt0: np.ndarray, at0: np.ndarray, bs0: np.ndarray, as0: np.ndarray) -> np.ndarray:
    """
    Contribución de un evento al Order Flow Imbalance (Cont, Kukanov y Stoikov 2014, ec. 4):
        e = 1{Pᵇ ≥ Pᵇ₀}·qᵇ − 1{Pᵇ ≤ Pᵇ₀}·qᵇ₀ − 1{Pᵃ ≤ Pᵃ₀}·qᵃ + 1{Pᵃ ≥ Pᵃ₀}·qᵃ₀
    (con ₀ = el estado anterior). Precios en ticks enteros: las comparaciones son exactas.

    [v2] En tu calculate_ofi el lado ask tiene los tamaños cruzados cuando el precio se
    mueve. Si el ask SUBE, la oferta que se retira es la cola vieja (qᵃ₀) y tú cuentas la
    nueva (qᵃ); si BAJA, la oferta nueva es qᵃ y tú cuentas la vieja (qᵃ₀). Con el precio
    quieto coincide. La ecuación de CKS es ANTISIMÉTRICA: el mismo libro visto en espejo
    (bid ↔ ask) da exactamente el OFI opuesto. La tuya no: en una subida suma las dos colas
    nuevas y en una bajada resta las dos viejas, y eso le da un sesgo que no viene del
    mercado (una prueba lo verifica y el reporte lo mide en tus datos).
    """
    e_b = np.where(bt > bt0, bs, np.where(bt == bt0, bs - bs0, -bs0))
    e_a = np.where(at < at0, -as_, np.where(at == at0, -(as_ - as0), as0))
    return (e_b + e_a).astype(np.int64)


def ofi_tu_script(bt, at, bs, as_, bt0, at0, bs0, as0) -> np.ndarray:
    """Réplica de tu calculate_ofi: i_bid − i_ask con los tamaños del ask como los escribiste."""
    i_bid = np.where(bt > bt0, bs, np.where(bt == bt0, bs - bs0, -bs0))
    i_ask = np.where(at > at0, -as_, np.where(at == at0, as_ - as0, as0))
    return (i_bid - i_ask).astype(np.int64)


def normalizar_bloque(df: pd.DataFrame) -> pd.DataFrame:
    """
    MBP-1 trae action/side/size por registro; BBO-1s (una foto por segundo) no trae action.
    Sin action, cada foto cuenta como un estado del libro y no hay flujo de operaciones.
    """
    faltan = {k: v for k, v in (("action", "A"), ("side", "N"), ("size", 0), ("flags", F_LAST),
                                ("instrument_id", 0)) if k not in df}
    return df.assign(**faltan) if faltan else df


COLS_SEG = ("ofi", "ofi_crudo", "ofi_tu", "e2", "n_ev", "tfi", "vol", "tw_t", "tw_obi", "tw_dep",
            "tw_spr", "ew_obi", "ew_n", "tu_obi", "tu_n")


@dataclass
class Estado:
    """El último estado válido del libro, que pasa de un bloque al siguiente."""
    t: int
    bt: int
    at: int
    bs: int
    as_: int
    inst: int
    ses: int
    fin_ses: int


class MotorEventos:
    """
    Motor 1 · EVENTOS. Recorre el DBN por bloques y acumula, segundo por segundo:
      · OFI de CKS (con higiene), su suma de cuadrados y el número de eventos;
      · el OFI crudo (CKS sin higiene) y el de tu script, para compararlos;
      · la integral en el TIEMPO del OBI, de la profundidad y del spread (y el tiempo válido);
      · el OBI promedio por EVENTO (lo que hace tu script) y el flujo de operaciones (TFI);
      · el mid, el precio ponderado y el OBI vigentes al cierre de cada segundo.
    Todo lo que cruza de un bloque al otro vive en `self.prev`: procesar en bloques da
    exactamente lo mismo que de un jalón (una prueba lo verifica).
    """

    def __init__(self, cfg: Config, t0_ns: int, t1_ns: int, tick_ns_: int, usar_last: bool = True):
        self.cfg = cfg
        self.t0 = int(t0_ns) // NS * NS
        self.n = int((int(t1_ns) - self.t0) // NS) + 2
        self.tick = int(tick_ns_)
        self.usar_last = usar_last
        self.a = {c: np.zeros(self.n) for c in COLS_SEG}
        for c in ("mid", "micro", "obi_fin"):
            self.a[c] = np.full(self.n, np.nan)
        self.a["inst"] = np.full(self.n, -1, dtype=np.int64)
        self.conteo = {r: 0 for r in REGLAS}
        self.registros = 0
        self.operaciones = 0
        self.latencias = []
        self.ts_event_atras = 0
        self.prev: Estado | None = None
        self.prev_crudo: tuple | None = None
        self.reset_pend = False
        self.hueco = int(cfg.hueco_max_s * NS)

    # -- utilidades --
    def _seg(self, t: np.ndarray) -> np.ndarray:
        return (np.asarray(t, np.int64) - self.t0) // NS

    def _add(self, col: str, t: np.ndarray, v: np.ndarray) -> None:
        s = self._seg(t)
        ok = (s >= 0) & (s < self.n)
        if ok.any():
            self.a[col] += np.bincount(s[ok], weights=np.asarray(v, float)[ok], minlength=self.n)

    def _sesiones(self, t: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        idx = pd.DatetimeIndex(np.asarray(t, np.int64), tz="UTC")
        pared = idx.tz_convert(self.cfg.tz_mercado).tz_localize(None) + pd.Timedelta(hours=DESFASE_H)
        dia = pared.normalize()
        ses = (dia.asi8 // (86400 * NS)).astype(np.int64)
        seg_ses = (pared.asi8 - dia.asi8)                       # ns desde el inicio de la sesión
        fin = np.asarray(t, np.int64) + (MINUTOS_SESION * 60 * NS - seg_ses)
        return ses, fin

    # -- un bloque --
    def procesar(self, df: pd.DataFrame) -> None:
        if df is None or not len(df):
            return
        df = normalizar_bloque(df)
        t = df.index.asi8.astype(np.int64)
        flags = df["flags"].to_numpy().astype(np.int64)
        accion = df["action"].astype(str).to_numpy()
        lado = df["side"].astype(str).to_numpy()
        bpx = df["bid_px_00"].to_numpy().astype(np.int64)
        apx = df["ask_px_00"].to_numpy().astype(np.int64)
        bsz = df["bid_sz_00"].to_numpy().astype(np.int64)
        asz = df["ask_sz_00"].to_numpy().astype(np.int64)
        inst = df["instrument_id"].to_numpy().astype(np.int64)
        self.registros += len(df)
        if "ts_event" in df:
            te = pd.DatetimeIndex(df["ts_event"]).asi8.astype(np.int64)
            if len(self.latencias) < 200_000:
                self.latencias.append((t - te)[: 50_000])
            self.ts_event_atras += int(np.sum(np.diff(te) < 0))

        # --- flujo de operaciones (TFI): todas las operaciones sin bandera de problema ---
        malo = (flags & (F_MAYBE_BAD_BOOK | F_BAD_TS_RECV)) != 0
        op = (accion == "T") & ~malo
        if op.any() and "size" in df:
            tam = df["size"].to_numpy().astype(np.int64)[op]
            signo = np.where(lado[op] == "B", 1, np.where(lado[op] == "A", -1, 0))
            self._add("tfi", t[op], signo * tam)
            self._add("vol", t[op], tam)
            self.operaciones += int(op.sum())

        # --- tu script: todos los registros, sin higiene, OFI con el ask cruzado ---
        crudo = (bpx != UNDEF_PRICE) & (apx != UNDEF_PRICE)
        tc, bc, ac, bsc, asc = t[crudo], bpx[crudo] // self.tick, apx[crudo] // self.tick, bsz[crudo], asz[crudo]
        if len(tc):
            con_previo = np.ones(len(tc), bool)
            if self.prev_crudo is not None:
                p = self.prev_crudo
                b0, a0, bs0, as0 = (np.r_[p[i], x[:-1]] for i, x in enumerate((bc, ac, bsc, asc)))
            else:
                b0, a0, bs0, as0 = (np.r_[x[:1], x[:-1]] for x in (bc, ac, bsc, asc))
                con_previo[0] = False
            self._add("ofi_tu", tc, np.where(con_previo, ofi_tu_script(bc, ac, bsc, asc, b0, a0, bs0, as0), 0))
            self._add("ofi_crudo", tc, np.where(con_previo, ofi_cks(bc, ac, bsc, asc, b0, a0, bs0, as0), 0))
            tot = bsc + asc
            self._add("tu_obi", tc, np.where(tot > 0, (bsc - asc) / np.where(tot > 0, tot, 1), 0.0))
            self._add("tu_n", tc, np.ones(len(tc)))
            self.prev_crudo = (bc[-1], ac[-1], bsc[-1], asc[-1])

        # --- higiene → estados válidos ---
        ok, limpia, conteo = higiene(flags, accion, bpx, apx, bsz, asz, self.tick, self.cfg, self.usar_last)
        for k, v in conteo.items():
            self.conteo[k] += v
        # un reinicio ('R') afecta al siguiente estado válido, aunque caiga en el bloque siguiente
        corte = np.cumsum(limpia)
        idx = np.flatnonzero(ok)
        if not len(idx):
            self.reset_pend |= bool(limpia.any())
            return
        reinicio = np.r_[(corte[idx[0]] > 0) | self.reset_pend, np.diff(corte[idx]) > 0]
        self.reset_pend = bool(corte[-1] > corte[idx[-1]])
        ts = t[idx]
        bt, at = bpx[idx] // self.tick, apx[idx] // self.tick
        bs, as_ = bsz[idx], asz[idx]
        ins = inst[idx]
        ses, fin = self._sesiones(ts)
        self._estados(ts, bt, at, bs, as_, ins, ses, fin, reinicio)

    def _estados(self, ts, bt, at, bs, as_, ins, ses, fin, reinicio) -> None:
        """Integra una tanda de estados válidos, con el pendiente del bloque anterior al frente."""
        p = self.prev
        if p is not None:
            T = np.r_[p.t, ts]
            B, A, BS, AS = np.r_[p.bt, bt], np.r_[p.at, at], np.r_[p.bs, bs], np.r_[p.as_, as_]
            I, S, F = np.r_[p.inst, ins], np.r_[p.ses, ses], np.r_[p.fin_ses, fin]
            R = np.r_[False, reinicio]
            nuevo = np.r_[False, np.ones(len(ts), bool)]
        else:
            T, B, A, BS, AS, I, S, F, R = ts, bt, at, bs, as_, ins, ses, fin, reinicio
            nuevo = np.ones(len(ts), bool)
        m = len(T)
        # --- OFI: sólo entre estados del mismo contrato, la misma sesión y sin hueco ---
        e = np.zeros(m, np.int64)
        if m > 1:
            mismo = ((I[1:] == I[:-1]) & (S[1:] == S[:-1]) & ((T[1:] - T[:-1]) <= self.hueco) & ~R[1:])
            e[1:] = np.where(mismo, ofi_cks(B[1:], A[1:], BS[1:], AS[1:], B[:-1], A[:-1], BS[:-1], AS[:-1]), 0)
        tot = (BS + AS).astype(float)
        obi = (BS - AS) / tot
        dep = tot / 2.0
        spr = (A - B).astype(float)
        mid = (A + B) / 2.0
        micro = (B * AS + A * BS) / tot
        nv = nuevo
        self._add("ofi", T[nv], e[nv])
        self._add("e2", T[nv], (e[nv].astype(float)) ** 2)
        self._add("n_ev", T[nv], np.ones(int(nv.sum())))
        self._add("ew_obi", T[nv], obi[nv])
        self._add("ew_n", T[nv], np.ones(int(nv.sum())))
        # --- integrales en el tiempo: intervalos [T_k, fin_k) de los estados 0 … m−2 ---
        if m > 1:
            k = np.arange(m - 1)
            largo = np.minimum.reduce([T[1:] - T[:-1], np.full(m - 1, self.hueco), F[:-1] - T[:-1]])
            largo = np.maximum(largo, 0)
            self._integrar(T[:-1], largo, {"tw_t": np.ones(m - 1), "tw_obi": obi[k], "tw_dep": dep[k],
                                           "tw_spr": spr[k]})
            self._al_cierre(T[:-1], largo, T[-1], mid[k], micro[k], obi[k], I[k])
        self.prev = Estado(int(T[-1]), int(B[-1]), int(A[-1]), int(BS[-1]), int(AS[-1]), int(I[-1]),
                           int(S[-1]), int(F[-1]))

    def _integrar(self, t_ini: np.ndarray, largo: np.ndarray, valores: dict) -> None:
        """
        Reparte ∫ v(t) dt de cada intervalo [t, t + largo) entre los segundos que toca: el
        pedazo del primer segundo, los segundos completos de en medio y el pedazo del último.
        Cada intervalo se integra entero en un solo bloque, así que el resultado no depende
        de dónde se corten los bloques.
        """
        if not len(t_ini):
            return
        t_ini = np.asarray(t_ini, np.int64)
        largo = np.asarray(largo, np.int64)
        t_fin = t_ini + largo
        s0 = (t_ini - self.t0) // NS
        s1 = np.where(largo > 0, (t_fin - 1 - self.t0) // NS, s0)
        uno = s1 == s0
        primero = np.where(uno, largo, self.t0 + (s0 + 1) * NS - t_ini) / NS
        ultimo = np.where(uno, 0, t_fin - (self.t0 + s1 * NS)) / NS
        varios = (s1 - s0) > 1
        for col, v in valores.items():
            v = np.asarray(v, float)
            self._sumar(col, s0, v * primero)
            self._sumar(col, s1[~uno], (v * ultimo)[~uno])
            if varios.any():
                d = np.zeros(self.n + 1)
                np.add.at(d, np.clip(s0[varios] + 1, 0, self.n), v[varios])
                np.add.at(d, np.clip(s1[varios], 0, self.n), -v[varios])
                self.a[col] += np.cumsum(d)[:self.n]

    def _sumar(self, col: str, s: np.ndarray, w: np.ndarray) -> None:
        ok = (s >= 0) & (s < self.n)
        if ok.any():
            self.a[col] += np.bincount(s[ok], weights=w[ok], minlength=self.n)

    def _al_cierre(self, t_ini, largo, t_ult, mid, micro, obi, inst) -> None:
        """Mid, precio ponderado y OBI vigentes al cierre de cada segundo (NaN si el libro no era válido)."""
        p0, p1 = int(t_ini[0]), int(t_ult)
        s_ini = (p0 - self.t0) // NS
        s_fin = (p1 - self.t0) // NS
        if s_fin <= s_ini:
            return
        s = np.arange(s_ini, s_fin)
        borde = self.t0 + (s + 1) * NS
        j = np.searchsorted(t_ini, borde, side="left") - 1
        ok = (j >= 0) & (borde <= t_ini[np.clip(j, 0, None)] + largo[np.clip(j, 0, None)])
        ok &= (s >= 0) & (s < self.n)
        s, j = s[ok], j[ok]
        self.a["mid"][s] = mid[j]
        self.a["micro"][s] = micro[j]
        self.a["obi_fin"][s] = obi[j]
        self.a["inst"][s] = inst[j]

    def cerrar(self, t_fin_datos: int) -> None:
        """El último estado vale hasta el final de los datos (o de su sesión, o del hueco máximo)."""
        p = self.prev
        if p is None:
            return
        largo = max(0, min(int(t_fin_datos) - p.t, self.hueco, p.fin_ses - p.t))
        tot = p.bs + p.as_
        v = {"tw_t": np.ones(1), "tw_obi": np.array([(p.bs - p.as_) / tot]),
             "tw_dep": np.array([tot / 2.0]), "tw_spr": np.array([float(p.at - p.bt)])}
        self._integrar(np.array([p.t]), np.array([largo]), v)
        self._al_cierre(np.array([p.t]), np.array([largo]), p.t + largo,
                        np.array([(p.at + p.bt) / 2.0]), np.array([(p.bt * p.as_ + p.at * p.bs) / tot]),
                        np.array([(p.bs - p.as_) / tot]), np.array([p.inst]))

    def segundos(self) -> pd.DataFrame:
        idx = pd.DatetimeIndex(self.t0 + NS * np.arange(self.n), tz="UTC")
        df = pd.DataFrame(self.a, index=idx)
        vivo = (df["tw_t"] > 0) | (df["n_ev"] > 0) | (df["tu_n"] > 0) | (df["vol"] > 0)
        return df[vivo]


def correr_motor(tienda, cfg: Config, t0_ns: int | None = None, t1_ns: int | None = None,
                 verbose: bool = True) -> tuple[pd.DataFrame, MotorEventos]:
    """DBNStore (o DataFrame con las columnas de to_df) → segundos, bloque por bloque."""
    tk = tick_ns(cfg.symbol)
    if hasattr(tienda, "to_df"):
        meta = tienda.metadata
        t0 = int(t0_ns if t0_ns is not None else meta.start)
        t1 = int(t1_ns if t1_ns is not None else (meta.end or meta.start + 8 * 86400 * NS))
        bloques = tienda.to_df(price_type="fixed", count=cfg.bloque)
        bloques = [bloques] if isinstance(bloques, pd.DataFrame) else bloques
    else:
        t0 = int(t0_ns if t0_ns is not None else tienda.index.asi8[0])
        t1 = int(t1_ns if t1_ns is not None else tienda.index.asi8[-1] + NS)
        bloques = (tienda.iloc[i:i + cfg.bloque] for i in range(0, len(tienda), cfg.bloque))
    motor = None
    t_ult = t0
    inicio = time.time()
    for k, df in enumerate(bloques):
        if not len(df):
            continue
        if motor is None:
            con_last = bool(((df["flags"].to_numpy().astype(np.int64) & F_LAST) != 0).mean() > 0.01)
            motor = MotorEventos(cfg, t0, t1, tk, usar_last=cfg.solo_f_last and con_last)
            if cfg.solo_f_last and not con_last and verbose:
                print("⚠ Los registros no traen F_LAST: se usan todos los estados del libro.")
        motor.procesar(df)
        t_ult = int(df.index.asi8[-1])
        if verbose and (k + 1) % 5 == 0:
            print(f"   … {motor.registros:,} registros ({time.time() - inicio:.0f} s)")
    if motor is None:
        sys.exit("❌ No llegaron registros.")
    motor.cerrar(t_ult)
    return motor.segundos(), motor


class MotorIncremental:
    """
    El mismo motor, un registro a la vez: lo que usarías con el feed EN VIVO (Databento Live),
    donde no hay bloques sino eventos que llegan. Aplica la misma higiene en el mismo orden y
    acumula las mismas columnas por segundo. La prueba de paridad exige que dé EXACTAMENTE lo
    mismo que el motor vectorizado sobre los mismos registros; el reporte la corre sobre los
    primeros registros de tus datos.
    """

    CAMPOS = ("ofi", "e2", "n_ev", "tfi", "vol", "tw_t", "tw_obi", "tw_dep", "tw_spr", "ew_obi", "ew_n")

    def __init__(self, cfg: Config, t0_ns: int, t1_ns: int, tick_ns_: int, usar_last: bool = True):
        self.cfg = cfg
        self.t0 = int(t0_ns) // NS * NS
        self.n = int((int(t1_ns) - self.t0) // NS) + 2
        self.tick = int(tick_ns_)
        self.usar_last = usar_last
        self.a = {c: np.zeros(self.n) for c in self.CAMPOS}
        self.a["mid"] = np.full(self.n, np.nan)
        self.a["obi_fin"] = np.full(self.n, np.nan)
        self.conteo = {r: 0 for r in REGLAS}
        self.prev = None
        self.reset_pend = False
        self.hueco = int(cfg.hueco_max_s * NS)

    def _seg(self, t: int) -> int:
        return (int(t) - self.t0) // NS

    def _intervalo(self, p: Estado, t_sig: int) -> None:
        """Integra el estado p desde p.t hasta su fin, repartido por segundos, y fija los cierres."""
        largo = max(0, min(int(t_sig) - p.t, self.hueco, p.fin_ses - p.t))
        tot = p.bs + p.as_
        v = {"tw_t": 1.0, "tw_obi": (p.bs - p.as_) / tot, "tw_dep": tot / 2.0, "tw_spr": float(p.at - p.bt)}
        a, b = p.t, p.t + largo
        while a < b:
            s = self._seg(a)
            borde = self.t0 + (s + 1) * NS
            c = min(b, borde)
            if 0 <= s < self.n:
                for k, val in v.items():
                    self.a[k][s] += val * (c - a) / NS
            a = c
        # cierres: segundos cuyo borde final cae en (p.t, t_sig] y dentro del intervalo válido
        s = self._seg(p.t)
        while True:
            borde = self.t0 + (s + 1) * NS
            if borde > int(t_sig):
                break
            if borde > p.t and borde <= p.t + largo and 0 <= s < self.n:
                self.a["mid"][s] = (p.at + p.bt) / 2.0
                self.a["obi_fin"][s] = (p.bs - p.as_) / tot
            s += 1
            if borde > p.t + largo:
                break

    def evento(self, t: int, flags: int, accion: str, lado: str, tam: int, bpx: int, apx: int,
               bsz: int, asz: int, inst: int, ses: int, fin_ses: int) -> None:
        malo = (flags & (F_MAYBE_BAD_BOOK | F_BAD_TS_RECV)) != 0
        if accion == "T" and not malo:
            s = self._seg(t)
            if 0 <= s < self.n:
                self.a["tfi"][s] += (1 if lado == "B" else -1 if lado == "A" else 0) * tam
                self.a["vol"][s] += tam
        if malo:
            self.conteo[REGLAS[0]] += 1
            return
        if accion == "R":
            self.reset_pend = True
        if self.usar_last and not (flags & F_LAST):
            self.conteo[REGLAS[1]] += 1
            return
        if bpx == UNDEF_PRICE or apx == UNDEF_PRICE or bsz <= 0 or asz <= 0:
            self.conteo[REGLAS[2]] += 1
            return
        if bpx >= apx:
            self.conteo[REGLAS[3]] += 1
            return
        if apx - bpx > self.cfg.spread_max_ticks * self.tick:
            self.conteo[REGLAS[4]] += 1
            return
        if accion == "R":
            self.conteo[REGLAS[5]] += 1
            return
        if bpx % self.tick or apx % self.tick:
            self.conteo[REGLAS[6]] += 1
            return
        bt, at = bpx // self.tick, apx // self.tick
        nuevo = Estado(int(t), int(bt), int(at), int(bsz), int(asz), int(inst), int(ses), int(fin_ses))
        e = 0
        p = self.prev
        if p is not None:
            self._intervalo(p, t)
            if (p.inst == nuevo.inst and p.ses == nuevo.ses and nuevo.t - p.t <= self.hueco
                    and not self.reset_pend):
                e_b = bsz if bt > p.bt else (bsz - p.bs if bt == p.bt else -p.bs)
                e_a = -asz if at < p.at else (-(asz - p.as_) if at == p.at else p.as_)
                e = int(e_b + e_a)
        s = self._seg(t)
        if 0 <= s < self.n:
            self.a["ofi"][s] += e
            self.a["e2"][s] += float(e) ** 2
            self.a["n_ev"][s] += 1
            self.a["ew_obi"][s] += (bsz - asz) / (bsz + asz)
            self.a["ew_n"][s] += 1
        self.prev = nuevo
        self.reset_pend = False

    def cerrar(self, t_fin_datos: int) -> None:
        if self.prev is not None:
            self._intervalo(self.prev, int(t_fin_datos))


def sesiones_de(t_ns: np.ndarray, cfg: Config) -> tuple[np.ndarray, np.ndarray]:
    """(sesión, fin de la sesión en ns UTC) para cada marca de tiempo."""
    m = MotorEventos.__new__(MotorEventos)
    m.cfg = cfg
    return MotorEventos._sesiones(m, np.asarray(t_ns, np.int64))


def paridad(df: pd.DataFrame, cfg: Config) -> dict:
    """Corre el motor vectorizado y el incremental sobre los MISMOS registros y compara."""
    df = normalizar_bloque(df)
    t = df.index.asi8.astype(np.int64)
    t0, t1 = int(t[0]), int(t[-1]) + NS
    tk = tick_ns(cfg.symbol)
    usar = bool(((df["flags"].to_numpy().astype(np.int64) & F_LAST) != 0).mean() > 0.01) and cfg.solo_f_last
    vec = MotorEventos(cfg, t0, t1, tk, usar_last=usar)
    for i in range(0, len(df), max(1, len(df) // 3)):
        vec.procesar(df.iloc[i:i + max(1, len(df) // 3)])
    vec.cerrar(int(t[-1]))
    inc = MotorIncremental(cfg, t0, t1, tk, usar_last=usar)
    ses, fin = sesiones_de(t, cfg)
    cols = [df[c].to_numpy() for c in ("flags", "action", "side", "size", "bid_px_00", "ask_px_00",
                                       "bid_sz_00", "ask_sz_00", "instrument_id")]
    for k in range(len(df)):
        inc.evento(int(t[k]), int(cols[0][k]), str(cols[1][k]), str(cols[2][k]), int(cols[3][k]),
                   int(cols[4][k]), int(cols[5][k]), int(cols[6][k]), int(cols[7][k]), int(cols[8][k]),
                   int(ses[k]), int(fin[k]))
    inc.cerrar(int(t[-1]))
    dif = {}
    for c in MotorIncremental.CAMPOS + ("mid", "obi_fin"):
        a, b = vec.a[c][:inc.n], inc.a[c]
        ambos = np.isfinite(a) & np.isfinite(b)
        dif[c] = float(np.max(np.abs(a[ambos] - b[ambos]))) if ambos.any() else 0.0
        dif[c] = max(dif[c], float(np.sum(np.isfinite(a) != np.isfinite(b))))
    return {"registros": len(df), "max_dif": max(dif.values()), "por_columna": dif,
            "conteo_igual": vec.conteo == inc.conteo}


# =============================================================================
# 4. MOTOR 2 · BARRAS — OFI normalizado, OBI por tiempo, z robusto y alertas
# =============================================================================
def _segundo_de_sesion(idx: pd.DatetimeIndex, tz: str) -> tuple[np.ndarray, np.ndarray]:
    pared = idx.tz_convert(tz).tz_localize(None) + pd.Timedelta(hours=DESFASE_H)
    dia = pared.normalize()
    return dia.to_numpy(), ((pared.asi8 - dia.asi8) // NS).astype(np.int64)


def agrupar(seg: pd.DataFrame, cfg: Config, largo_s: int) -> pd.DataFrame:
    """Segundos → intervalos de `largo_s` segundos alineados a la sesión (17:00 CT)."""
    ses, s_ses = _segundo_de_sesion(seg.index, cfg.tz_mercado)
    b = s_ses // largo_s
    g = seg.assign(_ses=ses, _b=b)
    suma = [c for c in COLS_SEG if c in g]
    A = g.groupby(["_ses", "_b"], sort=True)[suma].sum()
    fin = g.dropna(subset=["mid"]).groupby(["_ses", "_b"], sort=True)[["mid", "micro", "obi_fin", "inst"]].last()
    A = A.join(fin, how="left")
    A = A.reset_index()
    pared = (pd.to_datetime(A["_ses"]) - pd.Timedelta(hours=DESFASE_H)
             + pd.to_timedelta((A["_b"] + 1) * largo_s, unit="s"))
    A.index = pd.DatetimeIndex(pared).tz_localize(cfg.tz_mercado, ambiguous="NaT",
                                                   nonexistent="shift_forward").tz_convert("UTC")
    A.index.name = "fin_utc"
    A = A.rename(columns={"_ses": "sesion", "_b": "bloque"})
    tw = A["tw_t"].replace(0, np.nan)
    A["twobi"] = A["tw_obi"] / tw
    A["ewobi"] = A["ew_obi"] / A["ew_n"].replace(0, np.nan)
    A["tu_obi_m"] = A["tu_obi"] / A["tu_n"].replace(0, np.nan)
    A["prof"] = A["tw_dep"] / tw
    A["spread"] = A["tw_spr"] / tw
    A["nofi"] = A["ofi"] / (2.0 * A["prof"])
    A["zself"] = A["ofi"] / np.sqrt(A["e2"].replace(0, np.nan))
    A["cobertura"] = A["tw_t"] / largo_s
    return A[np.isfinite(A["mid"])]


def z_robusto(x: np.ndarray, W: int, minimo: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Z robusto ESTRICTO: (x − mediana) / (1.4826 · MAD) con las W barras ANTERIORES (la actual
    no entra en su propia normalización), al menos `minimo` de ellas, y sin z si la MAD es 0.

    [v2] Tu z usa media y desviación estándar de una ventana que INCLUYE la barra actual: un
    choque grande infla su propia desviación y se esconde (con 288 barras, el z máximo
    alcanzable es 287/√288 ≈ 16.9, y un choque de 10 σ sale en ~8.6). Y con fillna(0) las primeras
    288 barras —el primer día— salen como z = 0, "sin señal", en vez de "sin dato".
    """
    x = np.asarray(x, float)
    n = len(x)
    if n == 0:
        return x.copy(), x.copy(), x.copy()
    from numpy.lib.stride_tricks import sliding_window_view
    xp = np.r_[np.full(W, np.nan), x]
    V = sliding_window_view(xp[:-1], W)
    cnt = np.sum(np.isfinite(V), 1)
    med = np.nanmedian(V, 1)
    mad = np.nanmedian(np.abs(V - med[:, None]), 1)
    esc = 1.4826 * mad
    z = np.where((cnt >= minimo) & (esc > 0), (x - med) / np.where(esc > 0, esc, np.nan), np.nan)
    return z, med, esc


def z_tu_script(x: np.ndarray, W: int) -> np.ndarray:
    """Tu OFI_Z: media y desviación de una ventana que incluye la barra actual, y fillna(0)."""
    s = pd.Series(np.asarray(x, float))
    z = (s - s.rolling(W).mean()) / s.rolling(W).std().replace(0, np.nan)
    return z.fillna(0).to_numpy()


def histeresis(z: np.ndarray, sesion: np.ndarray, entrada: float, salida: float,
               refractario: int = 0) -> tuple[np.ndarray, list]:
    """
    Alertas con histéresis (disparador de Schmitt), para cada dirección:
      · se ENTRA cuando |z| ≥ entrada;
      · se SALE sólo cuando |z| baja de `salida` (o cambia de signo más allá de −entrada);
      · al empezar cada sesión el estado se reinicia;
      · opcional: `refractario` barras sin reentrar en la misma dirección.
    Devuelve el estado (−1, 0, +1) por barra y la lista de eventos (i, "entra"/"sale", dir).

    [v2] Tu cooldown de 4 horas apaga el motor después de CUALQUIER alerta: un rebote a las
    9:00 silencia una caída a las 11:00 y el cruce de un umbral cada barra de un episodio
    largo no se distingue de uno nuevo. La histéresis da una alerta por episodio y avisa
    cuando termina.
    """
    n = len(z)
    est = np.zeros(n, dtype=int)
    eventos = []
    e = 0
    ult_salida = {1: -10 ** 9, -1: -10 ** 9}
    for i in range(n):
        if i > 0 and sesion[i] != sesion[i - 1] and e != 0:
            eventos.append((i - 1, "sale", e))
            ult_salida[e] = i - 1
            e = 0
        v = z[i]
        if not np.isfinite(v):
            est[i] = e
            continue
        if e == 0:
            if v >= entrada and i - ult_salida[1] > refractario:
                e = 1
                eventos.append((i, "entra", 1))
            elif v <= -entrada and i - ult_salida[-1] > refractario:
                e = -1
                eventos.append((i, "entra", -1))
        elif e == 1:
            if v <= -entrada:
                eventos.append((i, "sale", 1))
                ult_salida[1] = i
                e = -1
                eventos.append((i, "entra", -1))
            elif v < salida:
                eventos.append((i, "sale", 1))
                ult_salida[1] = i
                e = 0
        else:
            if v >= entrada:
                eventos.append((i, "sale", -1))
                ult_salida[-1] = i
                e = 1
                eventos.append((i, "entra", 1))
            elif v > -salida:
                eventos.append((i, "sale", -1))
                ult_salida[-1] = i
                e = 0
        est[i] = e
    return est, eventos


def alertas_tu_script(t: pd.DatetimeIndex, x: np.ndarray, umbral: float, horas: float = 4.0) -> list:
    """Tu lógica: cruce de ±umbral con enfriamiento de `horas` compartido por las dos direcciones."""
    out, ult = [], None
    for i, v in enumerate(np.asarray(x, float)):
        if ult is not None and (t[i] - t[ult]).total_seconds() < horas * 3600:
            continue
        if v >= umbral:
            out.append((i, "entra", 1))
            ult = i
        elif v <= -umbral:
            out.append((i, "entra", -1))
            ult = i
    return out


@dataclass
class Motores:
    barras: pd.DataFrame
    z_obi: np.ndarray
    z_ofi: np.ndarray
    est_obi: np.ndarray
    est_ofi: np.ndarray
    est_conf: np.ndarray
    ev_obi: list
    ev_ofi: list
    ev_conf: list
    tu_ev_obi: list
    tu_ev_ofi: list
    tu_z: np.ndarray


def doble_motor(B: pd.DataFrame, cfg: Config) -> Motores:
    """
    Motor ESTÁTICO: el OBI ponderado por tiempo (quién tiene más cola en el mejor nivel).
    Motor DINÁMICO: el OFI de CKS (quién está metiendo y sacando órdenes), autonormalizado
    por su propia actividad: OFI / √(Σ e²). Así una barra de las 3 a. m. con 40 eventos y
    una de la apertura con 4 000 hablan en la misma escala.
    Cada motor tiene su z robusto estricto y su histéresis; la CONFLUENCIA es cuando los dos
    están activos en la misma dirección.
    """
    ses = B["sesion"].to_numpy()
    z_obi = z_robusto(B["twobi"].to_numpy(), cfg.z_ventana, cfg.z_min)[0]
    z_ofi = z_robusto(B["zself"].to_numpy(), cfg.z_ventana, cfg.z_min)[0]
    est_obi, ev_obi = histeresis(z_obi, ses, cfg.z_entrada, cfg.z_salida, cfg.refractario)
    est_ofi, ev_ofi = histeresis(z_ofi, ses, cfg.z_entrada, cfg.z_salida, cfg.refractario)
    conf = np.where((est_obi == est_ofi) & (est_obi != 0), est_obi, 0)
    ev_conf = []
    for i in range(len(conf)):
        prev = conf[i - 1] if i and ses[i] == ses[i - 1] else 0
        if conf[i] != prev:
            if prev != 0:
                ev_conf.append((i, "sale", int(prev)))
            if conf[i] != 0:
                ev_conf.append((i, "entra", int(conf[i])))
    tu_z = z_tu_script(B["ofi_tu"].to_numpy(), cfg.z_ventana)
    tu_ev_obi = alertas_tu_script(B.index, B["tu_obi_m"].to_numpy(), cfg.obi_nivel)
    tu_ev_ofi = alertas_tu_script(B.index, tu_z, cfg.z_entrada)
    return Motores(B, z_obi, z_ofi, est_obi, est_ofi, conf, ev_obi, ev_ofi, ev_conf, tu_ev_obi, tu_ev_ofi, tu_z)


# =============================================================================
# 5. AUDITORÍA Y CHEQUEO DE CORDURA
# =============================================================================
def _mco(x: np.ndarray, y: np.ndarray) -> dict:
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if len(x) < 30 or np.var(x) == 0:
        return {"n": int(len(x)), "b": np.nan, "t": np.nan, "r2": np.nan, "a": np.nan}
    X = np.c_[np.ones(len(x)), x]
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    res = y - X @ coef
    s2 = float(res @ res) / (len(x) - 2)
    cov = s2 * np.linalg.inv(X.T @ X)
    r2 = 1 - float(res @ res) / float(((y - y.mean()) ** 2).sum())
    return {"n": int(len(x)), "a": float(coef[0]), "b": float(coef[1]),
            "t": float(coef[1] / math.sqrt(cov[1, 1])), "r2": r2}


def regresion_cks(seg: pd.DataFrame, cfg: Config) -> dict:
    """
    La prueba de cordura del OFI (Cont, Kukanov y Stoikov 2014): en intervalos de `cks_s`
    segundos, el cambio del mid en ticks contra el OFI normalizado por la profundidad,
        Δmid = α + β · OFI / (2 · profundidad) + ε.
    En el modelo de CKS β ≈ 1: un OFI igual a dos veces la profundidad mueve el precio un
    tick. Un OFI mal calculado se nota aquí primero: menos R².
    """
    C = agrupar(seg, cfg, cfg.cks_s)
    mid = C["mid"].to_numpy()
    ses = C["sesion"].to_numpy()
    blo = C["bloque"].to_numpy()
    ins = C["inst"].to_numpy()
    d = np.full(len(C), np.nan)
    ok = (ses[1:] == ses[:-1]) & (blo[1:] == blo[:-1] + 1) & (ins[1:] == ins[:-1])
    d[1:] = np.where(ok, mid[1:] - mid[:-1], np.nan)
    prof = C["prof"].to_numpy()
    out = {"intervalos": int(np.isfinite(d).sum()), "prof_mediana": float(np.nanmedian(prof))}
    for k, col in (("módulo", "ofi"), ("sin higiene", "ofi_crudo"), ("tu script", "ofi_tu"),
                   ("flujo de operaciones", "tfi")):
        out[k] = _mco(C[col].to_numpy() / (2 * prof), d)
    out["sin normalizar"] = _mco(C["ofi"].to_numpy(), d)
    out["_x"] = C["ofi"].to_numpy() / (2 * prof)
    out["_y"] = d
    return out


def curva_imbalance(seg: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """
    El OBI al cierre de cada segundo contra el SIGUIENTE cambio del mid (mismo contrato y
    sesión): P(sube) y su tamaño esperado en ticks, por cubeta de OBI. Es la curva de
    "queue imbalance" (Gould y Bonart 2016) y el ajuste de un paso del microprecio de
    Stoikov (2018): microprecio ≈ mid + E[siguiente cambio | OBI].
    """
    ok = np.isfinite(seg["mid"].to_numpy())
    mid = seg["mid"].to_numpy()[ok]
    obi = seg["obi_fin"].to_numpy()[ok]
    ins = seg["inst"].to_numpy()[ok]
    ses = _segundo_de_sesion(seg.index[ok], cfg.tz_mercado)[0]
    if not len(mid):
        return pd.DataFrame()
    # tramos de mid constante dentro de un mismo contrato y sesión; el "siguiente cambio"
    # de cada segundo es el mid del tramo que sigue
    grupo = np.r_[True, (ins[1:] != ins[:-1]) | (ses[1:] != ses[:-1])]
    tramo = grupo | np.r_[True, mid[1:] != mid[:-1]]
    k_tramo = np.cumsum(tramo) - 1
    mid_t = mid[tramo]
    sig_t = np.r_[mid_t[1:], np.nan] - mid_t
    sig_t[np.r_[grupo[tramo][1:], True]] = np.nan
    sig = sig_t[k_tramo]
    bordes = np.linspace(-1, 1, cfg.cubetas_obi + 1)
    k = np.clip(np.digitize(obi, bordes) - 1, 0, cfg.cubetas_obi - 1)
    filas = []
    for j in range(cfg.cubetas_obi):
        m = (k == j) & np.isfinite(sig) & np.isfinite(obi)
        if m.sum() < 30:
            continue
        filas.append({"desde": bordes[j], "hasta": bordes[j + 1], "n": int(m.sum()),
                      "p_sube": float(np.mean(sig[m] > 0)), "cambio": float(np.mean(sig[m]))})
    return pd.DataFrame(filas)


def adelante(B: pd.DataFrame, h: int) -> np.ndarray:
    """Cambio del mid en ticks de la barra i a la i + h, sólo dentro de la misma sesión y contrato."""
    mid = B["mid"].to_numpy()
    ses = B["sesion"].to_numpy()
    ins = B["inst"].to_numpy()
    blo = B["bloque"].to_numpy()
    out = np.full(len(B), np.nan)
    if h < len(B):
        ok = (ses[h:] == ses[:-h]) & (ins[h:] == ins[:-h]) & (blo[h:] - blo[:-h] == h)
        out[:-h] = np.where(ok, mid[h:] - mid[:-h], np.nan)
    return out


def auditar_alertas(B: pd.DataFrame, eventos: list, cfg: Config) -> pd.DataFrame:
    """Qué hace el mid DESPUÉS de cada ENTRADA, a h barras: en ticks, a favor de la dirección."""
    filas = []
    ent = [(i, d) for i, tipo, d in eventos if tipo == "entra"]
    for h in cfg.horizontes:
        f = adelante(B, h)
        for d in (1, -1):
            idx = np.array([i for i, dd in ent if dd == d], dtype=int)
            v = f[idx] * d if len(idx) else np.array([])
            v = v[np.isfinite(v)]
            filas.append({"h": h, "dir": d, "n": len(v),
                          "a_favor": float(np.mean(v)) if len(v) else np.nan,
                          "t": float(np.mean(v) / (np.std(v, ddof=1) / math.sqrt(len(v))))
                          if len(v) > 2 and np.std(v) > 0 else np.nan,
                          "acierto": float(np.mean(v > 0)) if len(v) else np.nan})
    return pd.DataFrame(filas)


@dataclass
class Auditoria:
    cks: dict
    curva: pd.DataFrame
    alertas: dict               # nombre → DataFrame
    tw_vs_ew: dict
    por_hora: pd.DataFrame
    cordura: list               # (ok, texto)
    paridad: dict | None = None


def auditar(seg: pd.DataFrame, M: Motores, motor: MotorEventos, cfg: Config,
            paridad_: dict | None = None) -> Auditoria:
    B = M.barras
    cks = regresion_cks(seg, cfg)
    curva = curva_imbalance(seg, cfg)
    alertas = {"OBI (estático)": auditar_alertas(B, M.ev_obi, cfg),
               "OFI (dinámico)": auditar_alertas(B, M.ev_ofi, cfg),
               "confluencia": auditar_alertas(B, M.ev_conf, cfg),
               "tu OBI": auditar_alertas(B, M.tu_ev_obi, cfg),
               "tu OFI": auditar_alertas(B, M.tu_ev_ofi, cfg)}
    f1 = adelante(B, 1)
    d0 = np.r_[np.nan, np.diff(B["mid"].to_numpy())]
    tw, ew = B["twobi"].to_numpy(), B["ewobi"].to_numpy()

    def _c(a, b):
        ok = np.isfinite(a) & np.isfinite(b)
        return float(np.corrcoef(a[ok], b[ok])[0, 1]) if ok.sum() > 30 else np.nan

    dif = np.abs(tw - ew)
    tw_vs_ew = {"corr": _c(tw, ew), "dif_abs": float(np.nanmean(dif)),
                "dif_p99": float(np.nanpercentile(dif, 99)), "dif_max": float(np.nanmax(dif)),
                "i_max": int(np.nanargmax(dif)) if np.isfinite(dif).any() else -1,
                "sig_tw": _c(tw, f1), "sig_ew": _c(ew, f1), "mismo_tw": _c(tw, d0), "mismo_ew": _c(ew, d0),
                "nivel_tu": float(np.nanmean(np.abs(B["tu_obi_m"].to_numpy()) >= cfg.obi_nivel)),
                "nivel_tw": float(np.nanmean(np.abs(tw) >= cfg.obi_nivel))}
    # alertas por hora del día (CT): la estacionalidad que un z de 288 barras no ve
    hora = B.index.tz_convert(cfg.tz_mercado).hour
    filas = []
    for nm, ev in (("módulo OFI", M.ev_ofi), ("tu OFI", M.tu_ev_ofi), ("módulo OBI", M.ev_obi),
                   ("tu OBI", M.tu_ev_obi)):
        h_ = np.array([hora[i] for i, tipo, _ in ev if tipo == "entra"], dtype=int)
        filas.append({"motor": nm, **{int(k): int(np.sum(h_ == k)) for k in range(24)}})
    por_hora = pd.DataFrame(filas).set_index("motor")
    # --- chequeo de cordura ---
    c = []
    tot = sum(motor.conteo.values())
    val = motor.registros - tot
    c.append((val > 0.3 * motor.registros,
              f"{val:,} de {motor.registros:,} registros son estados válidos del libro ({val / max(1, motor.registros):.1%})"))
    fuera = motor.conteo[REGLAS[6]]
    c.append((fuera <= 1e-4 * max(1, motor.registros), f"precios fuera del tick (descartados): {fuera:,}"))
    b = cks["módulo"]
    c.append((np.isfinite(b["b"]) and b["b"] > 0 and b["r2"] > 0.1,
              f"CKS a {cfg.cks_s} s: pendiente {b['b']:.2f} (teoría ≈ 1) · R² {b['r2']:.2f}"))
    if len(curva) >= 4:
        rho = pd.Series(curva["p_sube"].to_numpy()).corr(pd.Series(np.arange(len(curva))), method="spearman")
        c.append((rho > 0.8, f"más OBI → más probable que el siguiente movimiento sea hacia arriba "
                             f"(Spearman {rho:+.2f})"))
    rth = (B.index.tz_convert(cfg.tz_mercado).hour >= 9) & (B.index.tz_convert(cfg.tz_mercado).hour < 15)
    cob = float(B.loc[rth, "cobertura"].mean()) if rth.any() else np.nan
    c.append((not np.isfinite(cob) or cob > 0.95, f"libro válido el {cob:.1%} del tiempo en horario regular"))
    if motor.latencias:
        lat = np.concatenate(motor.latencias) / 1e3
        c.append((True, f"latencia ts_recv − ts_event: mediana {np.median(lat):,.0f} µs · "
                        f"p99 {np.percentile(lat, 99):,.0f} µs"))
    c.append((motor.ts_event_atras == 0 or motor.ts_event_atras < 1e-4 * motor.registros,
              f"ts_event que retrocede: {motor.ts_event_atras:,}"))
    if paridad_ is not None:
        c.append((paridad_["max_dif"] < 1e-6 and paridad_["conteo_igual"],
                  f"motor incremental = vectorizado en {paridad_['registros']:,} registros "
                  f"(diferencia máxima {paridad_['max_dif']:.1e})"))
    return Auditoria(cks, curva, alertas, tw_vs_ew, por_hora, c, paridad_)


# =============================================================================
# 6. SIMULADOR — un libro de colas con flujo informado y defectos CONOCIDOS
# =============================================================================
def perfil_actividad(minuto: np.ndarray) -> np.ndarray:
    """Actividad relativa por minuto de sesión (0 = 17:00 CT): Asia quieta, Europa, apertura de NY."""
    m = np.asarray(minuto)
    p = np.where(m < 540, 0.45, 1.0)                           # 17:00-02:00 CT: Asia
    p = np.where((m >= 930) & (m < 1335), 3.0, p)              # 08:30-15:15 CT: horario regular
    p = np.where((m >= 930) & (m < 945), 6.0, p)               # la apertura
    p = np.where(m >= 1335, 0.6, p)
    return p


def simular(cfg: Config, sesiones: int | None = None, semilla: int | None = None,
            episodios: bool = True, defectos: bool = True) -> tuple[pd.DataFrame, dict]:
    """
    Registros MBP-1 con el formato de to_df(price_type="fixed"), generados por un modelo de
    colas en el mejor bid/ask (Cont y de Larrard 2013): órdenes límite, cancelaciones y
    órdenes de mercado; cuando una cola se vacía el precio se mueve un tick y las colas
    nuevas se sortean. Así el OFI y el precio están ligados como en el modelo de CKS.

    Encima, CONOCIDOS: ráfagas de flujo informado (órdenes de mercado de un lado ×4 durante
    3-12 min), "parpadeo" de cotizaciones (cientos de altas y cancelaciones en milisegundos,
    como hacen los algoritmos), actividad y profundidad que cambian con la hora, un roll con
    salto de nivel, un hueco de 6 min y —si `defectos`— registros que la higiene debe quitar: limpieza de
    libro, pre-apertura con spread ancho, libros cruzados, tamaños 0, banderas de libro
    dudoso, precios fuera del tick y el estado intermedio de cada operación (sin F_LAST).
    """
    rng = np.random.default_rng(cfg.sim_semilla if semilla is None else semilla)
    S = int(sesiones or cfg.sim_sesiones)
    tk = tick_ns(cfg.symbol)
    p_ref = CATALOGO.get(raiz(cfg.symbol), ("", 0.25, 20000.0))[2]
    fechas = pd.bdate_range(end=pd.Timestamp(cfg.end).normalize() - pd.Timedelta(days=1), periods=S)
    minutos = np.arange(MINUTOS_SESION)
    perfil = perfil_actividad(minutos)
    tasa_min = cfg.sim_eventos / perfil.sum()                 # eventos por minuto con perfil 1
    filas, limpio_mask = [], []
    verdad_ep = []
    bid = int(round(p_ref / (tk / NS)))
    inst = 5001
    seq = 0
    roll_en = S // 2
    hueco_en = (min(1, S - 1), 700)                            # sesión, minuto: 6 min sin eventos

    def reg(t, accion, lado, precio, tam, flags, b, a, qb, qa, instr, limpio=True):
        nonlocal seq
        seq += 1
        filas.append((t, accion, lado, precio, tam, flags, b, a, qb, qa, instr, seq))
        limpio_mask.append(limpio)

    for s_i, fecha in enumerate(fechas):
        t_ses = int(pd.Timestamp(fecha - pd.Timedelta(hours=DESFASE_H)).tz_localize(cfg.tz_mercado).tz_convert("UTC").value)
        if s_i == roll_en:                                     # roll: contrato nuevo, nivel +80 ticks
            inst += 1
            bid += 80
        # episodios de flujo informado
        ep = []
        if episodios:
            for _ in range(cfg.sim_episodios):
                m0 = int(rng.integers(60, MINUTOS_SESION - 30))
                ep.append((m0 * 60.0, m0 * 60.0 + rng.uniform(180, 720), int(rng.choice((-1, 1)))))
        for a0, a1, d in ep:
            verdad_ep.append((t_ses + int(a0 * NS), t_ses + int(a1 * NS), d, s_i))
        # tiempos de los eventos: Poisson por minuto con el perfil de actividad
        n_min = rng.poisson(tasa_min * perfil)
        if s_i == hueco_en[0]:
            n_min[hueco_en[1]:hueco_en[1] + 6] = 0
        seg = np.concatenate([m * 60.0 + np.sort(rng.uniform(0, 60, k)) for m, k in enumerate(n_min)])
        n = len(seg)
        prof_media = np.where(perfil[(seg // 60).astype(int)] >= 2.9, 10.0, 4.0)
        u = rng.random(n)
        tam = 1 + rng.geometric(0.55, n) - 1
        # --- libro inicial, precedido de la limpieza y la pre-apertura ---
        qb, qa = 1 + int(rng.poisson(4)), 1 + int(rng.poisson(4))
        t0 = t_ses + int(0.5 * NS)
        if defectos:
            reg(t0 - 3000, "R", "N", UNDEF_PRICE, 0, F_LAST, UNDEF_PRICE, UNDEF_PRICE, 0, 0, inst, False)
            for k in range(5):
                reg(t0 - 2000 + k, "A", "B", (bid - 10) * tk, 1, F_LAST, (bid - 10) * tk,
                    (bid + 10) * tk, 1, 1, inst, False)
        reg(t0, "A", "B", bid * tk, qb, F_LAST, bid * tk, (bid + 1) * tk, qb, qa, inst)
        for i in range(n):
            t = t_ses + int(seg[i] * NS)
            enep = [d for a0, a1, d in ep if a0 <= seg[i] < a1]
            d = enep[0] if enep else 0
            # probabilidades: alta/cancela en cada lado, mercado compra/vende
            pm_c = 0.06 * (4.0 if d > 0 else (0.6 if d < 0 else 1.0))
            pm_v = 0.06 * (4.0 if d < 0 else (0.6 if d > 0 else 1.0))
            pa = (1.0 - pm_c - pm_v) / 2
            corte = np.cumsum([pa * 0.55, pa * 0.55, pa * 0.45, pa * 0.45, pm_c])
            tipo = int(np.searchsorted(corte, u[i] * (corte[-1] + pm_v)))
            q = int(tam[i])
            a = bid + 1
            if tipo == 0:
                qb += q
                reg(t, "A", "B", bid * tk, q, F_LAST, bid * tk, a * tk, qb, qa, inst)
            elif tipo == 1:
                qa += q
                reg(t, "A", "A", a * tk, q, F_LAST, bid * tk, a * tk, qb, qa, inst)
            elif tipo in (2, 5):                               # cancela bid / vende a mercado
                q = min(q, qb)
                if tipo == 5:
                    reg(t, "T", "A", bid * tk, q, 0, bid * tk, a * tk, qb, qa, inst, not defectos)
                qb -= q
                if qb == 0:
                    bid -= 1
                    qb, qa = 1 + int(rng.poisson(prof_media[i])), 1 + int(rng.poisson(prof_media[i]))
                reg(t + 1, "C" if tipo == 2 else "F", "B", bid * tk, q, F_LAST, bid * tk, (bid + 1) * tk,
                    qb, qa, inst)
            else:                                              # cancela ask / compra a mercado
                q = min(q, qa)
                if tipo == 4:
                    reg(t, "T", "B", a * tk, q, 0, bid * tk, a * tk, qb, qa, inst, not defectos)
                qa -= q
                if qa == 0:
                    bid += 1
                    qb, qa = 1 + int(rng.poisson(prof_media[i])), 1 + int(rng.poisson(prof_media[i]))
                reg(t + 1, "C" if tipo == 3 else "F", "A", (bid + 1) * tk, q, F_LAST, bid * tk,
                    (bid + 1) * tk, qb, qa, inst)
            # parpadeo: 150 altas/cancelaciones de 8 lotes en un lado, en ≤ 20 ms
            if rng.random() < 20.0 / n:
                hasta = t_ses + int(seg[i + 1] * NS) if i + 1 < n else t + 10 ** 8
                dur = max(1000, min(20_000_000, (hasta - t - 10) // 2))
                lado_p = "A" if rng.random() < 0.5 else "B"
                for k in range(150):
                    tt = t + 3 + int(dur * (k + 1) / 151)
                    extra = 8 if k % 2 == 0 else 0
                    if lado_p == "A":
                        reg(tt, "A" if extra else "C", "A", (bid + 1) * tk, 8, F_LAST, bid * tk, (bid + 1) * tk,
                            qb, qa + extra, inst)
                    else:
                        reg(tt, "A" if extra else "C", "B", bid * tk, 8, F_LAST, bid * tk, (bid + 1) * tk,
                            qb + extra, qa, inst)
                continue
            # defectos sueltos entre dos eventos
            if defectos and rng.random() < 25.0 / n:
                k = int(rng.integers(5))
                tt = t + 2
                if k == 0:
                    reg(tt, "A", "B", (bid + 1) * tk, 1, F_LAST, (bid + 1) * tk, (bid + 1) * tk, qb, qa, inst, False)
                elif k == 1:
                    reg(tt, "C", "B", bid * tk, 1, F_LAST, bid * tk, (bid + 1) * tk, 0, qa, inst, False)
                elif k == 2:
                    reg(tt, "A", "A", 0, 1, F_LAST | F_MAYBE_BAD_BOOK, (bid - 50) * tk, (bid + 3) * tk, 999, 1,
                        inst, False)
                elif k == 3:
                    reg(tt, "A", "B", bid * tk + 7, 1, F_LAST, bid * tk + 7, (bid + 1) * tk, qb, qa, inst, False)
                else:
                    reg(tt, "M", "B", bid * tk, 1, 0, bid * tk, (bid + 1) * tk, qb + 3, qa, inst, False)
    arr = list(zip(*filas))
    t = np.asarray(arr[0], np.int64)
    orden = np.argsort(t, kind="stable")
    lat = 50_000
    ts_recv = t[orden] + lat
    df = pd.DataFrame({
        "ts_event": pd.DatetimeIndex(t[orden], tz="UTC"),
        "rtype": np.uint8(1), "publisher_id": np.uint16(1),
        "instrument_id": np.asarray(arr[10], np.uint32)[orden],
        "action": np.asarray(arr[1], dtype=object)[orden], "side": np.asarray(arr[2], dtype=object)[orden],
        "depth": np.uint8(0), "price": np.asarray(arr[3], np.int64)[orden],
        "size": np.asarray(arr[4], np.uint32)[orden], "flags": np.asarray(arr[5], np.uint8)[orden],
        "ts_in_delta": np.int32(0), "sequence": np.asarray(arr[11], np.uint32)[orden],
        "bid_px_00": np.asarray(arr[6], np.int64)[orden], "ask_px_00": np.asarray(arr[7], np.int64)[orden],
        "bid_sz_00": np.asarray(arr[8], np.uint32)[orden], "ask_sz_00": np.asarray(arr[9], np.uint32)[orden],
        "bid_ct_00": np.uint32(1), "ask_ct_00": np.uint32(1), "symbol": cfg.symbol},
        index=pd.DatetimeIndex(ts_recv, tz="UTC", name="ts_recv"))
    limpio = np.asarray(limpio_mask, bool)[orden]
    verdad = {"episodios": verdad_ep, "limpio": limpio, "roll_sesion": roll_en, "hueco": hueco_en,
              "sesiones": [str(f.date()) for f in fechas], "defectos": int((~limpio).sum())}
    return df, verdad


def a_dbn(df: pd.DataFrame, cfg: Config) -> bytes:
    """El DataFrame de simular() → un archivo DBN de verdad, para probar la ruta de Databento."""
    import databento_dbn as dd
    acc = {"A": dd.Action.ADD, "C": dd.Action.CANCEL, "M": dd.Action.MODIFY, "T": dd.Action.TRADE,
           "F": dd.Action.FILL, "R": dd.Action.CLEAR}
    lado = {"B": dd.Side.BID, "A": dd.Side.ASK, "N": dd.Side.NONE}
    t = df.index.asi8
    te = pd.DatetimeIndex(df["ts_event"]).asi8
    meta = dd.Metadata(dataset=cfg.dataset, start=int(t[0]), stype_in=dd.SType.CONTINUOUS,
                       stype_out=dd.SType.INSTRUMENT_ID, schema=dd.Schema.MBP_1, symbols=[cfg.symbol],
                       partial=[], not_found=[], mappings=[], end=int(t[-1]) + NS)
    partes = [bytes(meta.encode())]
    cols = [df[c].to_numpy() for c in ("instrument_id", "price", "size", "action", "side", "flags",
                                       "sequence", "bid_px_00", "ask_px_00", "bid_sz_00", "ask_sz_00")]
    for k in range(len(df)):
        lv = dd.BidAskPair(bid_px=int(cols[7][k]), ask_px=int(cols[8][k]), bid_sz=int(cols[9][k]),
                           ask_sz=int(cols[10][k]), bid_ct=1, ask_ct=1)
        m = dd.MBP1Msg(publisher_id=1, instrument_id=int(cols[0][k]), ts_event=int(te[k]), price=int(cols[1][k]),
                       size=int(cols[2][k]), action=acc[cols[3][k]], side=lado[cols[4][k]], depth=0,
                       ts_recv=int(t[k]), flags=int(cols[5][k]), sequence=int(cols[6][k]), levels=lv)
        partes.append(bytes(m))
    return b"".join(partes)


# =============================================================================
# 7. EL CÁLCULO COMPLETO
# =============================================================================
@dataclass
class Resultado:
    cfg: Config
    seg: pd.DataFrame
    motor: MotorEventos
    M: Motores
    aud: Auditoria
    info: dict
    verdad: dict | None = None
    medicion: dict | None = None


def analizar(tienda, cfg: Config, verdad: dict | None = None, chequear_paridad: bool = True,
             verbose: bool = True) -> Resultado:
    validar(cfg)
    seg, motor = correr_motor(tienda, cfg, verbose=verbose)
    B = agrupar(seg, cfg, cfg.barra_s)
    if len(B) < cfg.z_min + 10:
        sys.exit(f"❌ Sólo hay {len(B)} barras de {cfg.barra_s} s; el z necesita más de {cfg.z_min}. "
                 "Amplía las fechas o baja --barra.")
    M = doble_motor(B, cfg)
    par = None
    if chequear_paridad:
        muestra = (tienda.to_df(price_type="fixed", count=60_000) if hasattr(tienda, "to_df")
                   else tienda.iloc[:60_000])
        if not isinstance(muestra, pd.DataFrame):
            muestra = next(iter(muestra))
        par = paridad(muestra, cfg)
    aud = auditar(seg, M, motor, cfg, par)
    info = {"registros": motor.registros, "operaciones": motor.operaciones, "barras": len(B),
            "sesiones": int(B["sesion"].nunique()), "usar_last": motor.usar_last,
            "rolls": int(np.sum(np.diff(B["inst"].to_numpy()) != 0))}
    res = Resultado(cfg, seg, motor, M, aud, info, verdad)
    if verdad is not None:
        res.medicion = medir_contra_verdad(res)
    return res


def medir_contra_verdad(res: Resultado) -> dict:
    """¿Las alertas del motor dinámico caen en las ráfagas de flujo informado verdaderas?"""
    B, M, v = res.M.barras, res.M, res.verdad
    fin = B.index.asi8
    ini = fin - res.cfg.barra_s * NS
    en_ep = np.zeros(len(B), dtype=int)
    for a0, a1, d, _ in v["episodios"]:
        solapa = (ini < a1) & (fin > a0)
        en_ep[solapa] = d
    out = {"episodios": len(v["episodios"]), "defectos": v["defectos"]}
    z_ok = np.isfinite(M.z_ofi)
    for nombre_, ev in (("módulo OFI", M.ev_ofi), ("tu OFI", M.tu_ev_ofi), ("módulo OBI", M.ev_obi),
                        ("tu OBI", M.tu_ev_obi), ("confluencia", M.ev_conf)):
        ent = [(i, d) for i, tipo, d in ev if tipo == "entra" and z_ok[i]]
        acierto = sum(1 for i, d in ent if en_ep[i] == d)
        vistos = set()
        for a0, a1, d, _ in v["episodios"]:
            for i, dd in ent:
                if dd == d and ini[i] < a1 and fin[i] > a0:
                    vistos.add((a0, a1))
                    break
        ep_eval = [e for e in v["episodios"] if e[0] > fin[np.flatnonzero(z_ok)[0]]] if z_ok.any() else []
        out[nombre_] = {"alertas": len(ent), "en_episodio": acierto,
                        "precision": acierto / len(ent) if ent else np.nan,
                        "detectados": sum(1 for e in ep_eval if (e[0], e[1]) in vistos),
                        "evaluables": len(ep_eval)}
    return out


# =============================================================================
# 8. REPORTES
# =============================================================================
def _hora(t: pd.Timestamp, cfg: Config) -> str:
    return f"{t.tz_convert(cfg.tz_mercado):%m-%d %H:%M} CT / {t.tz_convert(cfg.tz_local):%H:%M} CDMX"


def _precio(mid_ticks: float, cfg: Config) -> float:
    return mid_ticks * tick(cfg.symbol)


def reporte_datos(res: Resultado) -> None:
    cfg, m, info = res.cfg, res.motor, res.info
    B = res.M.barras
    _titulo("1 · DATOS E HIGIENE DE ALTA FRECUENCIA")
    print(f"  {cfg.symbol} ({nombre(cfg.symbol)}) · {cfg.esquema} · tick {tick(cfg.symbol):g} · "
          f"{info['registros']:,} registros · {info['operaciones']:,} operaciones")
    print(f"  {info['sesiones']} sesiones · {info['barras']:,} barras de {cfg.barra_s // 60} min · "
          f"de {_hora(B.index[0], cfg)} a {_hora(B.index[-1], cfg)}")
    if info["rolls"]:
        print(f"  {info['rolls']} cambio(s) de contrato del continuo: el flujo se reinicia ahí.")
    print()
    print("  Registros descartados como ESTADO del libro (cada uno en la primera regla que falla):")
    for k, v in m.conteo.items():
        print(f"      {k:<40s}{v:12,d}{_pct(v / max(1, m.registros), 2, 9)}")
    val = m.registros - sum(m.conteo.values())
    print(f"      {'estados válidos':<40s}{val:12,d}{_pct(val / max(1, m.registros), 2, 9)}")
    if not info["usar_last"]:
        print("  ⚠ Los datos no traen F_LAST: se usaron todos los estados.")
    print(f"  Además: el flujo se reinicia en cada sesión, en cada roll y tras {cfg.hueco_max_s:.0f} s sin")
    print("  eventos, y ningún estado pesa en el tiempo más allá del cierre de su sesión.")


def reporte_tu_script(res: Resultado) -> None:
    cfg, M, aud, B = res.cfg, res.M, res.aud, res.M.barras
    _titulo("2 · TU SCRIPT CONTRA EL MÓDULO, SOBRE LOS MISMOS DATOS")
    ses = B.groupby("sesion")
    sesgo = (ses["ofi_tu"].sum() - ses["ofi_crudo"].sum())
    print(f"  Tu OFI con el lado ask cruzado: {sesgo.mean():+,.0f} contratos por sesión de diferencia con la")
    print(f"  ecuación de CKS sobre los mismos registros (el OFI correcto de una sesión es {ses['ofi'].sum().mean():+,.0f}).")
    print("  No es asimetría del mercado: tu fórmula cuenta dos colas nuevas en cada subida y dos viejas")
    print("  en cada bajada.")
    tw = aud.tw_vs_ew
    print(f"  Tu OBI llega a ±{cfg.obi_nivel:.2f} (promedio de 5 min) en el {tw['nivel_tu']:.2%} de las barras: "
          f"{len(M.tu_ev_obi)} alerta(s) en total.")
    p_ = B["mid"].iloc[-1] * tick(cfg.symbol)
    print(f"  Tu Microprice se divide entre 1e9 cuando to_df() ya entrega float: {p_:,.2f} sale como "
          f"{p_ / 1e9:.8f}.")
    n_tu = len(M.tu_ev_ofi)
    n_mod = sum(1 for _, t_, _ in M.ev_ofi if t_ == "entra")
    print(f"  Alertas de OFI: tu script {n_tu} (z con la barra actual dentro, fillna(0) y 4 h de espera) ·")
    print(f"  módulo {n_mod} (z robusto de barras previas, autonormalizado, con histéresis).")
    ph = aud.por_hora
    if len(ph):
        top_tu = ph.loc["tu OFI"].sort_values(ascending=False).head(3)
        top_mod = ph.loc["módulo OFI"].sort_values(ascending=False).head(3)
        print("  Horas CT con más alertas de OFI:  tu script " +
              ", ".join(f"{h}:00 ({v})" for h, v in top_tu.items() if v) +
              "  ·  módulo " + (", ".join(f"{h}:00 ({v})" for h, v in top_mod.items() if v) or "—"))
        print("  Un z de 288 barras mezcla la noche quieta con la apertura: la apertura parece choque todos")
        print("  los días. El OFI autonormalizado (OFI / √Σe²) no depende de cuántos eventos tuvo la barra.")


def reporte_motores(res: Resultado) -> None:
    cfg, M, B = res.cfg, res.M, res.M.barras
    _titulo("3 · DOBLE MOTOR — dónde está cada uno HOY")
    i = len(B) - 1
    etiqueta = {1: "COMPRA", -1: "VENTA", 0: "neutral"}
    print(f"  Última barra: {_hora(B.index[i], cfg)} · mid {_precio(B['mid'].iloc[i], cfg):,.2f} · "
          f"spread medio {B['spread'].iloc[i]:.2f} ticks · profundidad {B['prof'].iloc[i]:.1f} lotes")
    print(f"  Motor ESTÁTICO (OBI por tiempo)   OBI {B['twobi'].iloc[i]:+.3f}  (por evento {B['ewobi'].iloc[i]:+.3f}) "
          f"· z {_fmt(M.z_obi[i], 2, 6)} · {etiqueta[int(M.est_obi[i])]}")
    print(f"  Motor DINÁMICO (OFI de CKS)        OFI {B['ofi'].iloc[i]:+,.0f} lotes · normalizado "
          f"{B['nofi'].iloc[i]:+.2f} ticks · z {_fmt(M.z_ofi[i], 2, 6)} · {etiqueta[int(M.est_ofi[i])]}")
    print(f"  Confluencia: {etiqueta[int(M.est_conf[i])]}")
    print()
    print(f"  Alertas con histéresis (entra con |z| ≥ {cfg.z_entrada:g}, sale con |z| < {cfg.z_salida:g}):")
    for nm, ev in (("OBI", M.ev_obi), ("OFI", M.ev_ofi), ("confluencia", M.ev_conf)):
        ent = [e for e in ev if e[1] == "entra"]
        print(f"      {nm:<12s}{len(ent):4d} episodios · últimos: " + (", ".join(
            f"{'▲' if d > 0 else '▼'} {B.index[k].tz_convert(cfg.tz_local):%m-%d %H:%M}" for k, _, d in ent[-4:]) or "—"))


def reporte_cks(res: Resultado) -> None:
    cfg, aud = res.cfg, res.aud
    c = aud.cks
    _titulo(f"4 · ECUACIÓN DE CKS (2014) NORMALIZADA — Δmid (ticks) contra OFI / (2 · profundidad), {cfg.cks_s} s")
    print(f"  {c['intervalos']:,} intervalos · profundidad mediana en el mejor nivel {c['prof_mediana']:.1f} lotes")
    print(f"      {'variable':<28s}{'pendiente':>11s}{'t':>9s}{'R²':>8s}")
    for k in ("módulo", "sin higiene", "tu script", "flujo de operaciones", "sin normalizar"):
        r = c[k]
        nota = {"sin normalizar": "  (OFI en lotes: la pendiente no es comparable)",
                "flujo de operaciones": "  (sólo operaciones, sin altas ni cancelaciones)"}.get(k, "")
        print(f"      {k:<28s}{_fmt(r['b'], 3, 11)}{_fmt(r['t'], 1, 9)}{_fmt(r['r2'], 3, 8)}{nota}")
    print("  En el modelo de CKS la pendiente es ≈ 1: un OFI de dos veces la profundidad mueve un tick.")
    print("  Normalizar por la profundidad importa porque la profundidad cambia con la hora del día.")
    if c["tu script"]["r2"] > c["módulo"]["r2"]:
        print("  Tu fórmula da más R² porque en cada subida suma las DOS colas nuevas: mete en la variable")
        print("  parte del propio movimiento del precio. Más R² no la hace correcta: la ecuación del artículo")
        print("  es antisimétrica y la tuya no, por eso acumula el sesgo de la sección 2.")


def reporte_auditoria(res: Resultado) -> None:
    cfg, aud, B = res.cfg, res.aud, res.M.barras
    _titulo("5 · AUDITORÍA — qué pasa DESPUÉS")
    cv = aud.curva
    if len(cv):
        print("  OBI al cierre de cada segundo → el SIGUIENTE movimiento del mid:")
        print("      OBI          " + "".join(f"{f'{a:+.1f}…{b_:+.1f}':>12s}" for a, b_ in zip(cv["desde"], cv["hasta"])))
        print("      P(sube)      " + "".join(f"{v:12.1%}" for v in cv["p_sube"]))
        print("      Δ en ticks   " + "".join(f"{v:+12.2f}" for v in cv["cambio"]))
        print("  El OBI anticipa el siguiente tick. A 5 min se diluye:")
    tw = aud.tw_vs_ew
    print(f"      correlación del OBI de la barra con el Δmid de la barra siguiente: por tiempo "
          f"{tw['sig_tw']:+.3f} · por evento {tw['sig_ew']:+.3f}")
    print(f"  OBI por tiempo vs por evento: correlación {tw['corr']:.3f} · diferencia media {tw['dif_abs']:.3f} · "
          f"p99 {tw['dif_p99']:.3f} · máxima {tw['dif_max']:.3f}")
    if tw["i_max"] >= 0:
        print(f"      (la mayor en {_hora(B.index[tw['i_max']], cfg)}: {B['n_ev'].iloc[tw['i_max']]:,.0f} eventos en la barra)")
    print()
    print("  Δmid en ticks A FAVOR de la alerta, h barras después de ENTRAR (t; acierto):")
    hs = list(cfg.horizontes)
    print(f"      {'motor':<18s}{'dir':>4s}" + "".join(f"{'h = ' + str(h):>23s}" for h in hs))
    for nm, T in aud.alertas.items():
        for d in (1, -1):
            celdas = []
            for h in hs:
                f = T[(T.h == h) & (T.dir == d)]
                if f.empty or not f["n"].iloc[0]:
                    celdas.append(f"{'—':>23s}")
                    continue
                f = f.iloc[0]
                tt = f"{f['t']:+.1f}" if np.isfinite(f["t"]) else "—"
                celdas.append(f"{f['a_favor']:+6.2f} ({tt}; {f['acierto']:.0%}) n{int(f['n'])}".rjust(23))
            print(f"      {nm:<18s}{'▲' if d > 0 else '▼':>4s}" + "".join(celdas))
    print("  Con pocas alertas el t no significa nada; lo que cuenta es |t| ≥ 2 con n de decenas.")


def reporte_cordura(res: Resultado) -> None:
    _titulo("6 · CHEQUEO DE CORDURA")
    for ok, txt in res.aud.cordura:
        print(f"  {'✓' if ok else '⚠'} {txt}")


def reporte_verdad(res: Resultado) -> None:
    v = res.medicion
    if not v:
        return
    _titulo("7 · CONTRA LA VERDAD (sólo en simulación)")
    print(f"  {v['episodios']} ráfagas de flujo informado conocidas · {v['defectos']:,} registros defectuosos inyectados")
    print(f"      {'motor':<14s}{'alertas':>9s}{'en ráfaga':>11s}{'precisión':>11s}{'ráfagas vistas':>16s}")
    for nm in ("módulo OFI", "tu OFI", "módulo OBI", "tu OBI", "confluencia"):
        d = v[nm]
        print(f"      {nm:<14s}{d['alertas']:9d}{d['en_episodio']:11d}{_pct(d['precision'], 0, 10)}"
              f"{d['detectados']:10d} de {d['evaluables']}")


# =============================================================================
# 9. DASHBOARD
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


COMPRA, VENTA = C["s1"], C["baja"]


def _eje_barras(ax, idx: pd.DatetimeIndex, tz: str, n_ticks: int = 9) -> None:
    n = len(idx)
    if n < 2:
        return
    pos = np.unique(np.linspace(0, n - 1, n_ticks).round().astype(int))
    loc = idx[pos].tz_convert(tz)
    ax.set_xticks(pos)
    ax.set_xticklabels([t.strftime("%m-%d\n%H:%M") for t in loc], fontsize=8)


def _separar_sesiones(ax, ses: np.ndarray) -> None:
    for i in np.flatnonzero(np.r_[False, ses[1:] != ses[:-1]]):
        ax.axvline(i - 0.5, color=C["eje"], linewidth=0.8, zorder=0)


def _sombrear_estado(ax, est: np.ndarray, alpha: float = 0.16) -> None:
    ini = 0
    for i in range(1, len(est) + 1):
        if i == len(est) or est[i] != est[ini]:
            if est[ini] != 0:
                ax.axvspan(ini - 0.5, i - 0.5, color=COMPRA if est[ini] > 0 else VENTA, alpha=alpha,
                           linewidth=0, zorder=0)
            ini = i


def _panel_z(ax, pos, z, est, cfg, titulo, extra=None):
    _estilo(ax, titulo)
    _sombrear_estado(ax, est)
    ax.plot(pos, z, color=C["tinta"], linewidth=0.8, label="z robusto")
    if extra is not None:
        ax.plot(pos, extra[0], color=C["s4"], linewidth=0.7, alpha=0.85, label=extra[1])
    for s_ in (1, -1):
        ax.axhline(s_ * cfg.z_entrada, color=COMPRA if s_ > 0 else VENTA, linestyle="--", linewidth=1.0)
        ax.axhline(s_ * cfg.z_salida, color=COMPRA if s_ > 0 else VENTA, linestyle=":", linewidth=0.9)
    ax.axhline(0, color=C["eje"], linewidth=0.8)
    lim = max(cfg.z_entrada + 1.5, float(np.nanpercentile(np.abs(z[np.isfinite(z)]), 99.5)) + 0.5) \
        if np.isfinite(z).any() else cfg.z_entrada + 2
    ax.set_ylim(-lim, lim)
    ax.set_ylabel("z", color=C["tinta2"], fontsize=9)


def tablero_motores(res: Resultado, plt, ruta: Path):
    cfg, M = res.cfg, res.M
    B = M.barras
    pos = np.arange(len(B))
    ses = B["sesion"].to_numpy()
    fig = plt.figure(figsize=(19, 15))
    fig.patch.set_facecolor(C["fondo"])
    gs = fig.add_gridspec(4, 1, height_ratios=[1.6, 1.0, 1.0, 1.0], hspace=0.3, bottom=0.05, top=0.94)
    a1 = fig.add_subplot(gs[0])
    a2 = fig.add_subplot(gs[1], sharex=a1)
    a3 = fig.add_subplot(gs[2], sharex=a1)
    a4 = fig.add_subplot(gs[3], sharex=a1)
    i = len(B) - 1
    fig.suptitle(f"Order Book Imbalance · {cfg.symbol} ({nombre(cfg.symbol)}) · barras de {cfg.barra_s // 60} min · "
                 f"OBI z {_fmt(M.z_obi[i], 1, 1).strip()} · OFI z {_fmt(M.z_ofi[i], 1, 1).strip()}",
                 x=0.01, ha="left", color=C["tinta"], fontsize=12.5)
    precio = B["mid"].to_numpy() * tick(cfg.symbol)
    _estilo(a1, "Mid con la CONFLUENCIA de los dos motores de fondo · ▲▼ entradas del OFI · ◆ entradas del OBI")
    _sombrear_estado(a1, M.est_conf, alpha=0.22)
    _separar_sesiones(a1, ses)
    a1.plot(pos, precio, color=C["tinta"], linewidth=0.9, zorder=3)
    rango = np.nanmax(precio) - np.nanmin(precio)
    for ev, marca, desp in ((M.ev_ofi, None, 0.035), (M.ev_obi, "D", 0.07)):
        for k, tipo, d in ev:
            if tipo != "entra":
                continue
            y = precio[k] - d * desp * rango
            a1.scatter([k], [y], marker=marca or ("^" if d > 0 else "v"), s=46 if marca is None else 26,
                       color=COMPRA if d > 0 else VENTA, zorder=4, edgecolors=C["fondo"], linewidths=0.6)
    from matplotlib.lines import Line2D
    a1.legend(handles=[Line2D([], [], marker="^", linestyle="", color=COMPRA, label="OFI: entra compra"),
                       Line2D([], [], marker="v", linestyle="", color=VENTA, label="OFI: entra venta"),
                       Line2D([], [], marker="D", linestyle="", color=C["tinta2"], markersize=5,
                              label="OBI: entra (color = dirección)")],
              loc="upper left", fontsize=8, frameon=True, facecolor=C["fondo"], edgecolor="none",
              framealpha=0.9, labelcolor=C["tinta2"], ncol=3)
    a1.set_ylabel("precio", color=C["tinta2"], fontsize=9)

    _panel_z(a2, pos, M.z_obi, M.est_obi, cfg,
             f"Motor ESTÁTICO · z robusto del OBI ponderado por TIEMPO (entra ±{cfg.z_entrada:g}, sale ±{cfg.z_salida:g})")
    _separar_sesiones(a2, ses)
    _leyenda(a2, loc="upper left", frameon=True, facecolor=C["fondo"], edgecolor="none", framealpha=0.9)
    _panel_z(a3, pos, M.z_ofi, M.est_ofi, cfg,
             "Motor DINÁMICO · z robusto del OFI de CKS autonormalizado · en naranja, tu z del OFI",
             extra=(np.clip(M.tu_z, -20, 20), "tu z"))
    _separar_sesiones(a3, ses)
    _leyenda(a3, loc="upper left", ncol=2, frameon=True, facecolor=C["fondo"], edgecolor="none", framealpha=0.9)

    _estilo(a4, "CKS en acción: OFI normalizado acumulado en la sesión (ticks) contra el cambio del mid")
    nofi = np.nan_to_num(B["nofi"].to_numpy())
    acum = np.zeros(len(B))
    dmid = np.zeros(len(B))
    mid = B["mid"].to_numpy()
    base = mid[0]
    for k in range(len(B)):
        nueva = k == 0 or ses[k] != ses[k - 1] or B["inst"].iloc[k] != B["inst"].iloc[k - 1]
        if nueva:
            base = mid[k]
            acum[k] = nofi[k]
        else:
            acum[k] = acum[k - 1] + nofi[k]
        dmid[k] = mid[k] - base
    b_cks = res.aud.cks["módulo"]["b"]
    a4.plot(pos, dmid, color=C["tinta"], linewidth=1.0, label="Δmid desde el inicio de la sesión")
    a4.plot(pos, b_cks * acum, color=C["s1"], linewidth=1.0,
            label=f"{b_cks:.2f} × OFI normalizado acumulado")
    _separar_sesiones(a4, ses)
    a4.axhline(0, color=C["eje"], linewidth=0.8)
    a4.set_ylabel("ticks", color=C["tinta2"], fontsize=9)
    _leyenda(a4, loc="upper left", ncol=2, frameon=True, facecolor=C["fondo"], edgecolor="none", framealpha=0.9)
    for ax in (a1, a2, a3):
        ax.tick_params(labelbottom=False)
    _eje_barras(a4, B.index, cfg.tz_local)
    a4.set_xlim(-1, len(B))
    fig.text(0.008, 0.012, f"{IDENTIFICADOR} · fondo azul/rojo = motor activo en compra/venta · líneas "
             f"verticales = cambio de sesión · fechas en CDMX", color=C["tenue"], fontsize=7.5)
    fig.savefig(ruta, dpi=120, facecolor=C["fondo"], bbox_inches="tight")
    return fig


def tablero_auditoria(res: Resultado, plt, ruta: Path):
    cfg, aud, M = res.cfg, res.aud, res.M
    B = M.barras
    fig = plt.figure(figsize=(19, 15))
    fig.patch.set_facecolor(C["fondo"])
    gs = fig.add_gridspec(3, 3, hspace=0.45, wspace=0.3, bottom=0.05, top=0.93)
    ax = [[fig.add_subplot(gs[i, j]) for j in range(3)] for i in range(3)]
    (b1, b2, b3), (b4, b5, b6), (b7, b8, b9) = ax
    fig.suptitle(f"Order Book Imbalance · auditoría y cordura · {cfg.symbol}", x=0.01, ha="left",
                 color=C["tinta"], fontsize=12.5)

    # 1 regresión CKS
    c = aud.cks
    x, y = c["_x"], c["_y"]
    ok = np.isfinite(x) & np.isfinite(y)
    _estilo(b1, f"CKS a {cfg.cks_s} s: Δmid contra OFI / (2 · profundidad)")
    if ok.sum() > 10:
        lim = float(np.nanpercentile(np.abs(x[ok]), 99.5))
        sel = ok & (np.abs(x) <= lim)
        b1.hexbin(x[sel], y[sel], gridsize=45, cmap="Blues", mincnt=1, bins="log", linewidths=0)
        xs = np.linspace(-lim, lim, 10)
        r = c["módulo"]
        b1.plot(xs, r["a"] + r["b"] * xs, color=C["baja"], linewidth=1.5,
                label=f"ajuste: pendiente {r['b']:.2f} · R² {r['r2']:.2f}")
        b1.plot(xs, xs, color=C["tinta2"], linestyle=":", linewidth=1.0, label="teoría de CKS (pendiente 1)")
        _leyenda(b1, loc="upper left", frameon=True, facecolor=C["fondo"], edgecolor="none", framealpha=0.9)
    b1.set_xlabel("OFI normalizado (ticks)", color=C["tinta2"], fontsize=9)
    b1.set_ylabel("Δmid (ticks)", color=C["tinta2"], fontsize=9)

    # 2 R² por variable
    _estilo(b2, "¿Qué explica el movimiento del precio? R² a 10 s")
    nombres_ = ["módulo", "sin higiene", "tu script", "sin normalizar", "flujo de operaciones"]
    r2 = [c[k]["r2"] for k in nombres_]
    colores = [C["s1"], C["s3"], C["s4"], C["neutro"], C["s7"]]
    b2.barh(range(len(nombres_))[::-1], r2, color=colores, height=0.6)
    for yy, v in zip(range(len(nombres_))[::-1], r2):
        b2.annotate(f"{v:.2f}", xy=(v, yy), xytext=(4, -3), textcoords="offset points", fontsize=8.5,
                    color=C["tinta"])
    b2.set_yticks(range(len(nombres_))[::-1])
    b2.set_yticklabels(["OFI de CKS (módulo)", "OFI sin higiene", "tu OFI (ask cruzado) *",
                        "OFI sin normalizar", "flujo de operaciones"], fontsize=8.5)
    b2.set_xlim(0, max(0.05, np.nanmax(r2) * 1.2))
    b2.set_xlabel("R²", color=C["tinta2"], fontsize=9)
    b2.text(0.0, -0.2, "* en cada subida suma las dos colas nuevas: mete parte del movimiento\n"
            "  en la variable. Más R² no la hace correcta (no es antisimétrica, tiene sesgo).",
            transform=b2.transAxes, fontsize=7.5, color=C["tinta2"], va="top")

    # 3 curva de imbalance
    cv = aud.curva
    _estilo(b3, "OBI al cierre del segundo → ¿el siguiente tick sube?")
    if len(cv):
        xc = (cv["desde"] + cv["hasta"]) / 2
        b3.bar(xc, cv["p_sube"], width=0.17, color=[COMPRA if v >= 0.5 else VENTA for v in cv["p_sube"]], alpha=0.8)
        b3.axhline(0.5, color=C["tinta2"], linestyle=":", linewidth=1.0)
        for xx, v, n_ in zip(xc, cv["p_sube"], cv["n"]):
            b3.annotate(f"{v:.0%}", xy=(xx, v), xytext=(0, 3), textcoords="offset points", ha="center",
                        fontsize=7.5, color=C["tinta"])
        b3.set_ylim(0, 1.08)
    b3.set_xlabel("OBI = (qᵇ − qᵃ) / (qᵇ + qᵃ)", color=C["tinta2"], fontsize=9)
    b3.set_ylabel("P(sube)", color=C["tinta2"], fontsize=9)

    # 4 retornos tras las alertas
    _estilo(b4, "Después de ENTRAR: Δmid a favor, en ticks (IC 95 %)")
    hs = list(cfg.horizontes)
    nombres_a = list(aud.alertas.keys())
    ancho = 0.8 / len(nombres_a)
    col_a = {"OBI (estático)": C["s3"], "OFI (dinámico)": C["s1"], "confluencia": C["s7"],
             "tu OBI": C["neutro"], "tu OFI": C["s4"]}
    for j, nm in enumerate(nombres_a):
        T = aud.alertas[nm]
        vals, errs = [], []
        for h in hs:
            f = T[(T.h == h) & (T["n"] > 0)]
            n_ = float(f["n"].sum())
            if n_:
                vals.append(float((f["a_favor"] * f["n"]).sum() / n_))
                se = (f["a_favor"] / f["t"]).abs()
                errs.append(1.96 * math.sqrt(float(((f["n"] * se) ** 2).sum())) / n_
                            if se.notna().all() else np.nan)
            else:
                vals.append(np.nan)
                errs.append(np.nan)
        xh = np.arange(len(hs)) - 0.4 + (j + 0.5) * ancho
        b4.bar(xh, vals, width=ancho, color=col_a.get(nm, C["tenue"]), label=nm)
        b4.errorbar(xh, vals, yerr=errs, fmt="none", ecolor=C["tinta"], elinewidth=0.8, capsize=2)
    b4.axhline(0, color=C["eje"], linewidth=0.9)
    b4.set_xticks(range(len(hs)))
    b4.set_xticklabels([f"h = {h} barras" for h in hs], fontsize=8.5)
    b4.set_ylabel("ticks", color=C["tinta2"], fontsize=9)
    _leyenda(b4, loc="upper left", ncol=2, frameon=True, facecolor=C["fondo"], edgecolor="none", framealpha=0.9)

    # 5 alertas por hora
    _estilo(b5, "Alertas del OFI por hora del día (CT)")
    ph = aud.por_hora
    horas = np.arange(24)
    if len(ph):
        b5.bar(horas - 0.2, ph.loc["tu OFI"].reindex(horas, fill_value=0), width=0.4, color=C["s4"],
               label="tu script")
        b5.bar(horas + 0.2, ph.loc["módulo OFI"].reindex(horas, fill_value=0), width=0.4, color=C["s1"],
               label="módulo")
    b5.axvspan(8.5, 15.25, color=C["neutro"], alpha=0.35, linewidth=0, zorder=0)
    b5.set_xticks(range(0, 24, 3))
    from matplotlib.ticker import MaxNLocator
    b5.yaxis.set_major_locator(MaxNLocator(integer=True))
    b5.set_xlabel("hora de Chicago (gris = horario regular)", color=C["tinta2"], fontsize=9)
    _leyenda(b5, loc="upper left")

    # 6 higiene
    m = res.motor
    _estilo(b6, "Higiene: registros descartados como estado del libro")
    reglas = [k for k, v in m.conteo.items() if v > 0]
    vals = [m.conteo[k] for k in reglas]
    val = m.registros - sum(m.conteo.values())
    corto = dict(zip(REGLAS, ("banderas del feed", "sin F_LAST (intermedio)", "precio o tamaño inválido",
                              "cruzado o trabado", "spread ancho", "limpieza (R)", "fuera del tick")))
    etiquetas = [corto.get(k, k) for k in reglas] + ["ESTADOS VÁLIDOS"]
    vals = vals + [val]
    yy = np.arange(len(etiquetas))[::-1]
    b6.barh(yy, vals, color=[C["baja"]] * len(reglas) + [C["s3"]], height=0.6)
    for y_, v in zip(yy, vals):
        b6.annotate(f"{v:,}  ({v / max(1, m.registros):.1%})", xy=(v, y_), xytext=(4, -3),
                    textcoords="offset points", fontsize=8, color=C["tinta"])
    b6.set_xscale("log")
    b6.set_yticks(yy)
    b6.set_yticklabels(etiquetas, fontsize=8)
    b6.set_xlim(0.8, max(vals) * 30)

    # 7 OBI por tiempo vs por evento
    _estilo(b7, "OBI de la barra: por TIEMPO contra por EVENTO (tu promedio)")
    tw, ew = B["twobi"].to_numpy(), B["ewobi"].to_numpy()
    b7.scatter(tw, ew, s=6, color=C["s1"], alpha=0.35, linewidths=0)
    lim = np.nanmax(np.abs(np.r_[tw, ew])) * 1.05
    b7.plot([-lim, lim], [-lim, lim], color=C["tinta2"], linestyle=":", linewidth=1.0)
    b7.set_xlim(-lim, lim)
    b7.set_ylim(-lim, lim)
    b7.set_xlabel("OBI ponderado por tiempo", color=C["tinta2"], fontsize=9)
    b7.set_ylabel("OBI promedio por evento", color=C["tinta2"], fontsize=9)
    b7.text(0.03, 0.95, f"correlación {aud.tw_vs_ew['corr']:.3f}\ndiferencia máx. {aud.tw_vs_ew['dif_max']:.2f}",
            transform=b7.transAxes, va="top", fontsize=9, color=C["tinta"])

    # 8 tu z contra el z robusto
    _estilo(b8, "Distribución del z: tuyo (con la barra actual) vs robusto estricto")
    zt = M.tu_z[np.isfinite(M.tu_z) & (M.tu_z != 0)]
    zm = M.z_ofi[np.isfinite(M.z_ofi)]
    bins = np.linspace(-8, 8, 61)
    b8.hist(np.clip(zt, -8, 8), bins=bins, color=C["s4"], alpha=0.55, label="tu z del OFI")
    b8.hist(np.clip(zm, -8, 8), bins=bins, color=C["s1"], alpha=0.55, label="z robusto (módulo)")
    for s_ in (1, -1):
        b8.axvline(s_ * cfg.z_entrada, color=C["tinta2"], linestyle="--", linewidth=1.0)
    b8.set_yscale("log")
    b8.set_xlabel("z (recortado a ±8)", color=C["tinta2"], fontsize=9)
    _leyenda(b8, loc="upper left")

    # 9 cordura
    b9.set_facecolor(C["fondo"])
    b9.axis("off")
    b9.set_title("Chequeo de cordura", color=C["tinta"], fontsize=10, loc="left", pad=8)
    import textwrap as _tw
    yy = 0.97
    for ok_, txt in aud.cordura:
        lineas = _tw.wrap(txt, 58)
        b9.text(0.0, yy, "✓" if ok_ else "⚠", color=C["s3"] if ok_ else C["baja"], fontsize=11,
                transform=b9.transAxes, va="top")
        b9.text(0.05, yy, "\n".join(lineas), color=C["tinta"], fontsize=8.5, transform=b9.transAxes, va="top")
        yy -= 0.075 * len(lineas) + 0.035
    fig.text(0.008, 0.012, f"{IDENTIFICADOR} · regresión por MCO · IC con el error estándar entre alertas",
             color=C["tenue"], fontsize=7.5)
    fig.savefig(ruta, dpi=120, facecolor=C["fondo"], bbox_inches="tight")
    return fig


def tableros(res: Resultado, mostrar: bool = True) -> tuple[list[Path], object, bool]:
    plt, ventana = _preparar_grafico(mostrar)
    if plt is None:
        return [], None, False
    carpeta = _ruta(res.cfg.salida_dir)
    carpeta.mkdir(parents=True, exist_ok=True)
    rutas = []
    for nombre_, fn in (("motores", tablero_motores), ("auditoria", tablero_auditoria)):
        ruta = carpeta / f"obi_{nombre_}_{raiz(res.cfg.symbol)}.png"
        fig = fn(res, plt, ruta)
        rutas.append(ruta)
        print(f"🖼  {ruta}")
        if not ventana:
            plt.close(fig)
    return rutas, plt, ventana


# =============================================================================
# 10. TELEGRAM — el token y el chat, igual que la key: FUERA del código
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


def hay_alerta(res: Resultado) -> list[str]:
    """Entradas de la ÚLTIMA barra (la histéresis ya garantiza una por episodio)."""
    M, cfg = res.M, res.cfg
    i = len(M.barras) - 1
    avisos = []
    fuentes = (("Confluencia", M.ev_conf),) if cfg.telegram_confluencia else \
        (("OFI", M.ev_ofi), ("OBI", M.ev_obi), ("Confluencia", M.ev_conf))
    for nm, ev in fuentes:
        for k, tipo, d in ev:
            if k == i and tipo == "entra":
                avisos.append(f"{nm}: entra {'COMPRA' if d > 0 else 'VENTA'}")
    return avisos


def mensaje_telegram(res: Resultado, limite: int = 4096) -> str:
    esc = html.escape
    cfg, M = res.cfg, res.M
    B = M.barras
    i = len(B) - 1
    et = {1: "compra", -1: "venta", 0: "neutral"}
    lin = [f"<b>{esc(IDENTIFICADOR)}</b> · {esc(cfg.symbol)} · {cfg.barra_s // 60} min",
           esc(_hora(B.index[i], cfg))]
    for a in hay_alerta(res):
        lin.append(f"⚠️ {esc(a)}")
    lin += ["", f"mid {_precio(B['mid'].iloc[i], cfg):,.2f} · spread {B['spread'].iloc[i]:.2f} t · "
                f"prof {B['prof'].iloc[i]:.1f}",
            f"OBI (tiempo) {B['twobi'].iloc[i]:+.3f} · z {_fmt(M.z_obi[i], 2, 1).strip()} · {et[int(M.est_obi[i])]}",
            f"OFI {B['ofi'].iloc[i]:+,.0f} · {B['nofi'].iloc[i]:+.2f} t · z {_fmt(M.z_ofi[i], 2, 1).strip()} · "
            f"{et[int(M.est_ofi[i])]}",
            f"<b>Confluencia: {et[int(M.est_conf[i])]}</b>"]
    malos = [t for ok, t in res.aud.cordura if not ok]
    lin.append(f"Cordura: {len(res.aud.cordura) - len(malos)}/{len(res.aud.cordura)} ✓")
    for t in malos[:3]:
        lin.append(f"⚠ {esc(t)}")
    texto = "\n".join(lin)
    if len(texto) > limite:
        texto = texto[:limite - 20].rsplit("\n", 1)[0] + "\n…"
    return texto


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
# 11. GUARDAR
# =============================================================================
def guardar(res: Resultado) -> None:
    cfg, M = res.cfg, res.M
    B = M.barras
    carpeta = _ruta(cfg.salida_dir)
    carpeta.mkdir(parents=True, exist_ok=True)
    suf = _nombre_seguro(raiz(cfg.symbol), f"{cfg.barra_s}s")
    out = B.drop(columns=[c for c in ("tw_obi", "tw_dep", "tw_spr", "ew_obi", "ew_n", "tu_obi", "tu_n")
                          if c in B]).copy()
    out.insert(0, "hora_cdmx", B.index.tz_convert(cfg.tz_local).strftime("%Y-%m-%d %H:%M"))
    out.insert(0, "hora_ct", B.index.tz_convert(cfg.tz_mercado).strftime("%Y-%m-%d %H:%M"))
    out["precio_mid"] = B["mid"] * tick(cfg.symbol)
    out["z_obi"], out["z_ofi"], out["tu_z_ofi"] = M.z_obi, M.z_ofi, M.tu_z
    out["estado_obi"], out["estado_ofi"], out["confluencia"] = M.est_obi, M.est_ofi, M.est_conf
    out.to_csv(carpeta / f"obi_barras_{suf}.csv")
    ev = []
    for nm, lista in (("OBI", M.ev_obi), ("OFI", M.ev_ofi), ("confluencia", M.ev_conf),
                      ("tu OBI", M.tu_ev_obi), ("tu OFI", M.tu_ev_ofi)):
        for k, tipo, d in lista:
            ev.append({"motor": nm, "evento": tipo, "direccion": d,
                       "hora_ct": B.index[k].tz_convert(cfg.tz_mercado).strftime("%Y-%m-%d %H:%M"),
                       "precio": B["mid"].iloc[k] * tick(cfg.symbol)})
    pd.DataFrame(ev).to_csv(carpeta / f"obi_alertas_{suf}.csv", index=False)
    pd.concat([T.assign(motor=nm) for nm, T in res.aud.alertas.items()]).to_csv(
        carpeta / f"obi_auditoria_{suf}.csv", index=False)
    print(f"💾 Tablas guardadas en {carpeta}")


# =============================================================================
# 12. LÍNEA DE COMANDOS
# =============================================================================
def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Order Book Imbalance AC v2 — OFI de CKS y OBI por tiempo")
    p.add_argument("--pruebas", action="store_true", help="pruebas internas (sin red ni datos)")
    p.add_argument("--simulacion", action="store_true", help="libro simulado con verdad conocida (sin red)")
    p.add_argument("--sin-tablero", "--sin-grafica", action="store_true", dest="sin_tablero")
    p.add_argument("--sin-ventana", action="store_true")
    p.add_argument("--sin-cache", action="store_true")
    p.add_argument("--sin-paridad", action="store_true", help="no correr el chequeo del motor incremental")
    d = p.add_argument_group("datos")
    d.add_argument("--simbolo", default=None)
    d.add_argument("--start", "--inicio", default=None, dest="start")
    d.add_argument("--end", "--fin", default=None, dest="end")
    d.add_argument("--calentamiento", type=int, default=None, dest="dias_calentamiento",
                   help="sesiones previas descargadas para el z (1)")
    d.add_argument("--esquema", default=None, choices=("mbp-1", "bbo-1s"))
    d.add_argument("--costo-max", type=float, default=None, dest="costo_max_usd")
    d.add_argument("--bloque", type=int, default=None, help="registros por bloque (2 000 000)")
    d.add_argument("--salida", default=None, dest="salida_dir")
    h = p.add_argument_group("higiene")
    h.add_argument("--todos-los-registros", action="store_true", help="no filtrar por F_LAST")
    h.add_argument("--spread-max", type=int, default=None, dest="spread_max_ticks")
    h.add_argument("--hueco-max", type=float, default=None, dest="hueco_max_s")
    b = p.add_argument_group("barras, z y alertas")
    b.add_argument("--barra", type=int, default=None, dest="barra_s", help="segundos por barra (300)")
    b.add_argument("--z-ventana", type=int, default=None)
    b.add_argument("--z-min", type=int, default=None)
    b.add_argument("--z-entrada", type=float, default=None)
    b.add_argument("--z-salida", type=float, default=None)
    b.add_argument("--refractario", type=int, default=None)
    b.add_argument("--obi-nivel", type=float, default=None)
    b.add_argument("--cks", type=int, default=None, dest="cks_s", help="segundos de la regresión CKS (10)")
    b.add_argument("--horizontes", default=None, help='barras, p. ej. "1,3,6,12"')
    t = p.add_argument_group("Telegram")
    t.add_argument("--telegram", action="store_true")
    t.add_argument("--telegram-solo-alertas", action="store_true")
    t.add_argument("--telegram-confluencia", action="store_true", help="sólo alertas de confluencia")
    t.add_argument("--telegram-documentos", action="store_true")
    t.add_argument("--telegram-buscar-chat", action="store_true")
    s = p.add_argument_group("simulación")
    s.add_argument("--sesiones-sim", type=int, default=None, dest="sim_sesiones")
    s.add_argument("--eventos-sim", type=int, default=None, dest="sim_eventos")
    s.add_argument("--semilla", type=int, default=None, dest="sim_semilla")
    s.add_argument("--sin-episodios", action="store_true")
    s.add_argument("--sin-defectos", action="store_true")
    return p


def config_desde_args(a: argparse.Namespace) -> Config:
    cambios = {}
    for k in ("start", "end", "dias_calentamiento", "esquema", "costo_max_usd", "bloque", "salida_dir",
              "spread_max_ticks", "hueco_max_s", "barra_s", "z_ventana", "z_min", "z_entrada", "z_salida",
              "refractario", "obi_nivel", "cks_s", "sim_sesiones", "sim_eventos", "sim_semilla"):
        v = getattr(a, k, None)
        if v is not None:
            cambios[k] = v
    if a.simbolo:
        cambios["symbol"] = simbolo_continuo(a.simbolo)
    if a.horizontes:
        cambios["horizontes"] = tuple(int(x) for x in a.horizontes.split(",") if x.strip())
    if a.todos_los_registros:
        cambios["solo_f_last"] = False
    if a.sin_cache:
        cambios["usar_cache"] = False
    if a.telegram_confluencia:
        cambios["telegram_confluencia"] = True
    return replace(CFG, **cambios)


def main(argv: list[str] | None = None) -> int:
    a = construir_parser().parse_args(argv)
    cfg = config_desde_args(a)
    if a.pruebas:
        return pruebas()
    if a.telegram_buscar_chat:
        return buscar_chat_telegram()
    validar(cfg)
    print(f"▶ {IDENTIFICADOR} · {cfg.symbol} · {cfg.esquema} · barras de {cfg.barra_s} s")
    verdad = None
    if a.simulacion:
        print(f"🎲 {cfg.sim_sesiones} sesiones simuladas (~{cfg.sim_eventos:,} eventos cada una): libro de colas "
              "con ráfagas de flujo informado, parpadeo, un roll y defectos CONOCIDOS.")
        df, verdad = simular(cfg, episodios=not a.sin_episodios, defectos=not a.sin_defectos)
        tienda = df
        if db is not None:
            try:
                tienda = db.DBNStore.from_bytes(a_dbn(df, cfg))
                print("   (convertido a un archivo DBN de verdad: la misma ruta que tus datos)")
            except Exception as ex:
                print(f"   (sin DBN: {type(ex).__name__}; se usa el DataFrame)")
    else:
        tienda = obtener_datos(cfg)
    res = analizar(tienda, cfg, verdad=verdad, chequear_paridad=not a.sin_paridad)
    reporte_datos(res)
    reporte_tu_script(res)
    reporte_motores(res)
    reporte_cks(res)
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
            print("📭 Telegram: sin alertas en la última barra.")
        else:
            enviar_telegram(res, rutas, documentos=a.telegram_documentos)
    _titulo("CÓMO LEER ESTO")
    print("  1. El OFI de CKS mide quién mete y saca liquidez en el mejor nivel; normalizado por la")
    print("     profundidad se lee en ticks: es el movimiento que ese flujo 'explica'.")
    print("  2. El OBI dice hacia dónde es más probable el SIGUIENTE tick; a 5 minutos pesa poco.")
    print("  3. Una alerta entra con |z| ≥ entrada y dura hasta que |z| baja de la salida: una por")
    print("     episodio. La confluencia es cuando los dos motores empujan igual.")
    print("  4. Lee la auditoría antes de operar una alerta: con pocas entradas, el t no significa nada.")
    if rutas and not a.sin_ventana:
        print()
        mostrar_tableros(plt_, ventana, rutas)
    return 0


# =============================================================================
# 13. PRUEBAS INTERNAS
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
    A1 = np.array

    # 1 ------------------------------------------ la ecuación de CKS, caso por caso
    # (bid, ask) antes = (100, 101) con colas (5, 7); después cada combinación de movimientos
    casos, bien = [], True
    for db_, esperado_b in ((1, 9), (0, 9 - 5), (-1, -5)):          # bid sube / igual / baja; qᵇ nuevo = 9
        for da_, esperado_a in ((1, 7), (0, -(4 - 7)), (-1, -4)):    # ask sube / igual / baja; qᵃ nuevo = 4
            e = ofi_cks(A1([100 + db_]), A1([101 + da_]), A1([9]), A1([4]), A1([100]), A1([101]), A1([5]), A1([7]))[0]
            bien &= e == esperado_b + esperado_a
            casos.append(int(e))
    check("OFI de CKS = la ecuación del artículo en las 9 combinaciones de movimientos", bool(bien),
          f"{casos}")

    # 2 ------------------------------------------ antisimetría: el libro en espejo da el OFI opuesto
    n_ = 5000
    bt = 1000 + np.cumsum(rng.integers(-1, 2, n_))
    at = bt + rng.integers(1, 3, n_)
    bs, as_ = rng.integers(1, 30, n_), rng.integers(1, 30, n_)
    e = ofi_cks(bt[1:], at[1:], bs[1:], as_[1:], bt[:-1], at[:-1], bs[:-1], as_[:-1])
    em = ofi_cks(-at[1:], -bt[1:], as_[1:], bs[1:], -at[:-1], -bt[:-1], as_[:-1], bs[:-1])
    et = ofi_tu_script(bt[1:], at[1:], bs[1:], as_[1:], bt[:-1], at[:-1], bs[:-1], as_[:-1])
    etm = ofi_tu_script(-at[1:], -bt[1:], as_[1:], bs[1:], -at[:-1], -bt[:-1], as_[:-1], bs[:-1])
    check("CKS es antisimétrico (espejo bid ↔ ask = OFI opuesto); tu fórmula no",
          np.array_equal(em, -e) and not np.array_equal(etm, -et),
          f"tu fórmula falla en {np.mean(etm != -et):.0%} de los eventos")

    # 3 ------------------------------------------ identidad con el precio quieto
    qb, qa = rng.integers(1, 40, 400), rng.integers(1, 40, 400)
    b0, a0 = np.full(400, 50), np.full(400, 51)
    e3 = ofi_cks(b0[1:], a0[1:], qb[1:], qa[1:], b0[:-1], a0[:-1], qb[:-1], qa[:-1])
    check("sin cambios de precio, Σ OFI = Δqᵇ − Δqᵃ exacto",
          int(e3.sum()) == int((qb[-1] - qb[0]) - (qa[-1] - qa[0])))

    # --- una simulación chica con defectos, para la plomería ---
    cs = replace(cfg, sim_sesiones=3, sim_eventos=12_000, sim_episodios=2, z_min=40, z_ventana=120)
    df, ver = simular(cs, semilla=3)
    libro = ["ofi", "e2", "n_ev", "tw_t", "tw_obi", "tw_dep", "tw_spr", "ew_obi", "ew_n", "mid", "obi_fin"]

    def _igual(s1, s2, cols):
        u = s1.index.union(s2.index)
        a, b = s1.reindex(u)[cols].to_numpy(float), s2.reindex(u)[cols].to_numpy(float)
        ambos = np.isfinite(a) & np.isfinite(b)
        solo = np.isfinite(a) != np.isfinite(b)
        return float(np.max(np.abs(a[ambos] - b[ambos]), initial=0.0)), int(solo.sum())

    # 4 ------------------------------------------ higiene exacta: con defectos = sin ellos
    s_def, m_def = correr_motor(df, cs, verbose=False)
    s_lim, _ = correr_motor(df[ver["limpio"]], cs, t0_ns=int(df.index.asi8[0]), t1_ns=int(df.index.asi8[-1]) + NS,
                            verbose=False)
    dif4, solo4 = _igual(s_def, s_lim, libro)
    check("higiene: el libro CON registros defectuosos da lo mismo que sin ellos",
          dif4 < 1e-9 and solo4 == 0 and ver["defectos"] > 0,
          f"{ver['defectos']:,} defectos inyectados · diferencia {dif4:.1e}")

    # 5 ------------------------------------------ leer por bloques no cambia nada
    s_b, _ = correr_motor(df, replace(cs, bloque=7_777), verbose=False)
    s_1, _ = correr_motor(df, replace(cs, bloque=10 ** 9), verbose=False)
    dif5, solo5 = _igual(s_b, s_1, libro + ["ofi_tu", "ofi_crudo", "tfi"])
    check("procesar en bloques de 7 777 registros = de un jalón (el estado cruza los bloques)",
          dif5 < 1e-9 and solo5 == 0, f"diferencia {dif5:.1e}")

    # 6 ------------------------------------------ la ruta real: DBN → to_df(fixed, count) → motor
    if db is not None:
        try:
            tienda = db.DBNStore.from_bytes(a_dbn(df, cs))
            s_dbn, _ = correr_motor(tienda, replace(cs, bloque=5_000), t0_ns=int(df.index.asi8[0]),
                                    t1_ns=int(df.index.asi8[-1]) + NS, verbose=False)
            dif6, solo6 = _igual(s_dbn, s_1, libro + ["tfi", "vol"])
            check("archivo DBN real leído por bloques con precios enteros = los mismos resultados",
                  dif6 < 1e-9 and solo6 == 0, f"diferencia {dif6:.1e}")
        except Exception as ex:
            check("archivo DBN real leído por bloques con precios enteros = los mismos resultados", False,
                  f"{type(ex).__name__}: {ex}")
    else:
        check("archivo DBN real (databento no instalado: se omite)", True)

    # 6b ----------------------------------------- BBO-1s (sin action): fotos por segundo
    fotos = df[ver["limpio"] & (df["flags"].to_numpy() & F_LAST > 0)]
    fotos = fotos.groupby(fotos.index.floor("s")).tail(1).drop(columns=["action", "side", "size"])
    s_bbo, _ = correr_motor(fotos, cs, t0_ns=int(df.index.asi8[0]), t1_ns=int(df.index.asi8[-1]) + NS,
                            verbose=False)
    check("--esquema bbo-1s: registros sin action se leen como fotos del libro",
          len(s_bbo) > 0 and float(s_bbo["tfi"].abs().sum()) == 0.0 and np.isfinite(s_bbo["mid"]).any(),
          f"{len(fotos):,} fotos · OFI total {s_bbo['ofi'].sum():+,.0f} (con mbp-1: {s_1['ofi'].sum():+,.0f})")

    # 7 ------------------------------------------ paridad: motor incremental = vectorizado
    par = paridad(df.iloc[:40_000], cs)
    check("motor incremental (para vivo) = motor vectorizado, registro por registro",
          par["max_dif"] < 1e-6 and par["conteo_igual"], f"{par['registros']:,} registros · dif {par['max_dif']:.1e}")

    # 8 ------------------------------------------ OBI ponderado por tiempo, a mano
    t0 = 1_786_000_000 * NS
    mano = pd.DataFrame({
        "ts_event": pd.DatetimeIndex([t0, t0 + 900_000_000, t0 + 910_000_000, t0 + 920_000_000], tz="UTC"),
        "action": ["A"] * 4, "side": ["B"] * 4, "size": np.uint32(1), "flags": np.uint8(F_LAST),
        "bid_px_00": np.int64(100 * tick_ns(cs.symbol)), "ask_px_00": np.int64(101 * tick_ns(cs.symbol)),
        "bid_sz_00": np.array([30, 10, 10, 10], np.uint32), "ask_sz_00": np.array([10, 30, 30, 30], np.uint32),
        "instrument_id": np.uint32(1)},
        index=pd.DatetimeIndex([t0, t0 + 900_000_000, t0 + 910_000_000, t0 + 920_000_000], tz="UTC"))
    s8, _ = correr_motor(mano, cs, t0_ns=t0, t1_ns=t0 + 2 * NS, verbose=False)
    tw8 = float(s8["tw_obi"].iloc[0] / s8["tw_t"].iloc[0])
    ew8 = float(s8["ew_obi"].iloc[0] / s8["ew_n"].iloc[0])
    check("OBI por tiempo: 0.9 s a +0.5 y 0.02 s a −0.5 → +0.478; por evento sale −0.25",
          abs(tw8 - (0.9 * 0.5 - 0.02 * 0.5) / 0.92) < 1e-12 and abs(ew8 + 0.25) < 1e-12,
          f"por tiempo {tw8:+.3f} · por evento {ew8:+.3f}")

    # 9-10 --------------------------------------- reinicios: sesión, hueco y roll
    h_ct = s_1.index.tz_convert(cs.tz_mercado).hour
    pausa = s_1[h_ct == 16]
    check("ningún segundo pesa más de 1 s y el libro no pesa nada en la pausa de 16:00-17:00 CT",
          bool((s_1["tw_t"] <= 1.0 + 1e-9).all()) and float(pausa["tw_t"].sum()) == 0.0,
          f"{len(pausa)} segundos con registros en la pausa, 0 s de libro válido")
    t_h = pd.Timestamp(ver["sesiones"][ver["hueco"][0]]) - pd.Timedelta(hours=DESFASE_H) + \
        pd.Timedelta(minutes=ver["hueco"][1])
    t_h = t_h.tz_localize(cs.tz_mercado).tz_convert("UTC")
    ventana_h = s_1[(s_1.index >= t_h) & (s_1.index < t_h + pd.Timedelta(minutes=6))]
    check("tras un hueco sin eventos el libro deja de pesar a los 300 s (no 6 min enteros)",
          abs(float(ventana_h["tw_t"].sum()) - cs.hueco_max_s) < 60,
          f"tiempo válido dentro del hueco: {ventana_h['tw_t'].sum():.0f} s")

    # 11 ----------------------------------------- z robusto estricto
    x = rng.normal(size=600)
    x[500] = 10.0
    z, med, esc = z_robusto(x, 288, 60)
    x2 = x.copy()
    x2[500] = 0.0
    z2, med2, esc2 = z_robusto(x2, 288, 60)
    tz_ = z_tu_script(x, 288)
    check("z robusto: la barra actual no entra en su propia escala; un choque de 10σ no se esconde",
          med[500] == med2[500] and esc[500] == esc2[500] and z[500] > 9 and tz_[500] < 9
          and np.isnan(z[:60]).all() and (tz_[:287] == 0).all(),
          f"z robusto {z[500]:.1f} · tu z {tz_[500]:.1f} · tu primer día: z = 0 en vez de 'sin dato'")

    # 12 ----------------------------------------- histéresis
    zz = np.array([0, 3.2, 2.0, 1.5, 0.8, 3.1, -3.3, -0.5, 0, 3.5, 3.6], float)
    ss = np.array([0] * 9 + [1, 1])
    est, ev = histeresis(zz, ss, 3.0, 1.0)
    esperado = [(1, "entra", 1), (4, "sale", 1), (5, "entra", 1), (6, "sale", 1), (6, "entra", -1),
                (7, "sale", -1), (9, "entra", 1)]
    check("histéresis: entra en 3, se queda arriba de 1, voltea en −3, reinicia por sesión",
          ev == esperado and list(est) == [0, 1, 1, 1, 0, 1, -1, 0, 0, 1, 1], f"{len(ev)} eventos")
    tt = pd.date_range("2026-01-01", periods=len(zz), freq="h", tz="UTC")
    tu_ev = alertas_tu_script(tt, zz, 3.0, horas=4)
    check("tu enfriamiento de 4 h es común a las dos direcciones: la venta de la barra 6 se pierde",
          [(i, d) for i, _, d in tu_ev] == [(1, 1), (5, 1), (9, 1)],
          "tu script: " + ", ".join(f"{i}:{'▲' if d > 0 else '▼'}" for i, _, d in tu_ev))

    # 13 ----------------------------------------- validación
    malos = 0
    for kw in ({"barra_s": 7}, {"z_salida": 3.5}, {"esquema": "mbp-10"}, {"z_min": 5}):
        try:
            validar(replace(cfg, **kw))
        except SystemExit:
            malos += 1
    check("rechaza barras que no dividen la sesión, histéresis invertida y esquemas no soportados", malos == 4)

    # --- la simulación completa, una vez ---
    df_s, ver_s = simular(cfg, semilla=1)
    res = analizar(df_s, cfg, verdad=ver_s, chequear_paridad=False, verbose=False)
    c = res.aud.cks

    # 14 ----------------------------------------- CKS normalizado explica el precio
    check("CKS: pendiente positiva cerca de 1, R² alto; normalizar mejora; operaciones solas, poco",
          0.4 < c["módulo"]["b"] < 1.3 and c["módulo"]["r2"] > 0.4
          and c["módulo"]["r2"] > c["sin normalizar"]["r2"] + 0.1
          and c["flujo de operaciones"]["r2"] < 0.5 * c["módulo"]["r2"],
          f"pendiente {c['módulo']['b']:.2f} · R² {c['módulo']['r2']:.2f} · sin normalizar "
          f"{c['sin normalizar']['r2']:.2f} · operaciones {c['flujo de operaciones']['r2']:.2f}")

    # 15 ----------------------------------------- tu OFI tiene sesgo
    Bs = res.M.barras
    g = Bs.groupby("sesion")
    sesgo = (g["ofi_tu"].sum() - g["ofi_crudo"].sum()).to_numpy()
    check("tu OFI suma un sesgo alcista que no viene del mercado",
          float(sesgo.mean()) > 2 * float(sesgo.std(ddof=1)) / math.sqrt(len(sesgo)),
          f"{sesgo.mean():+,.0f} ± {sesgo.std(ddof=1):,.0f} contratos por sesión")

    # 16 ----------------------------------------- la curva de imbalance
    cv = res.aud.curva
    rho = pd.Series(cv["p_sube"].to_numpy()).corr(pd.Series(np.arange(len(cv))), method="spearman")
    check("más OBI → más probable que el siguiente tick suba (monótona)",
          rho > 0.95 and cv["p_sube"].iloc[0] < 0.3 and cv["p_sube"].iloc[-1] > 0.7,
          f"P(sube) de {cv['p_sube'].iloc[0]:.0%} a {cv['p_sube'].iloc[-1]:.0%}")

    # 17 ----------------------------------------- las alertas del OFI caen en las ráfagas
    md = res.medicion
    check("alertas del OFI: la mayoría cae en ráfagas de flujo informado; las tuyas, no",
          md["módulo OFI"]["precision"] > 0.5 and md["módulo OFI"]["precision"] > md["tu OFI"]["precision"],
          f"módulo {md['módulo OFI']['precision']:.0%} de {md['módulo OFI']['alertas']} · tuyas "
          f"{md['tu OFI']['precision']:.0%} de {md['tu OFI']['alertas']}")

    # 18 ----------------------------------------- sin flujo informado, el OFI casi no alerta
    df_n, ver_n = simular(cfg, semilla=2, episodios=False)
    rn = analizar(df_n, cfg, verdad=ver_n, chequear_paridad=False, verbose=False)
    Bn = rn.M.barras
    z_nofi = z_robusto(Bn["nofi"].to_numpy(), cfg.z_ventana, cfg.z_min)[0]
    _, ev_nofi = histeresis(z_nofi, Bn["sesion"].to_numpy(), cfg.z_entrada, cfg.z_salida)
    n_mod = sum(1 for _, tp, _ in rn.M.ev_ofi if tp == "entra")
    n_nofi = sum(1 for _, tp, _ in ev_nofi if tp == "entra")
    check("sin flujo informado: el OFI autonormalizado casi no alerta; normalizado sólo por profundidad sí",
          n_mod * 4 < n_nofi and n_mod <= 3 * cfg.sim_sesiones,
          f"{n_mod} alertas contra {n_nofi} en {cfg.sim_sesiones} sesiones (la apertura parece choque)")

    # 20 ----------------------------------------- Telegram: nunca el token
    tok = "123456789:" + "A" * 35
    msg = _sin_token(f"fallo en https://api.telegram.org/bot{tok}/sendMessage", tok)
    check("los errores de Telegram nunca muestran el token", tok not in msg and "…" in msg)

    # 21 ----------------------------------------- Telegram de punta a punta, sin red
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
        bien = (ok and cuerpo.startswith(f"--{limite}".encode())
                and cuerpo.rstrip().endswith(f"--{limite}--".encode())
                and b'name="photo"; filename="_prueba_telegram.png"' in cuerpo
                and tok.encode() not in cuerpo)
    finally:
        urllib.request.urlopen = viejo
        png.unlink(missing_ok=True)
    check("Telegram: el multipart de sendPhoto está bien formado y no lleva el token", bool(bien))

    # 22 ----------------------------------------- ninguna key escrita en este archivo
    fuente = Path(__file__).read_text(encoding="utf-8")
    check("no hay API keys ni tokens escritos en el código",
          not re.search("db" + "-" + r"[A-Za-z0-9]{20,}", fuente)
          and not re.search(r"\d{8,10}:" + r"[A-Za-z0-9_-]{35}", fuente))

    # 23 ----------------------------------------- mensaje de Telegram
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
