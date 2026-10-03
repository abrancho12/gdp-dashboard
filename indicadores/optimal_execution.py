# -*- coding: utf-8 -*-
"""
DOCSTRING_PENDIENTE
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
from dataclasses import dataclass, field, replace
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

try:
    import databento as db
except ModuleNotFoundError:
    db = None

try:                                     # opcional: si no está, el MLE usa un Nelder–Mead propio
    from scipy.optimize import minimize as _sp_minimize
except Exception:                        # noqa: BLE001
    _sp_minimize = None

IDENTIFICADOR = "optimal-execution-ac-v1"
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)
np.seterr(all="ignore")

# --- Constantes de la sesión de CME Globex ---
MINUTOS_SESION = 1380            # 17:00 → 16:00 CT (23 horas)
DESFASE_H = 7                    # hora CT + 7 h → la sesión que abre a las 17:00 cae en su fecha
NS = 1_000_000_000
NS_MS = 1_000_000
NS_MIN = 60 * NS
DIA_NS = 86_400 * NS
PRICE_SCALE = 1e9                # to_ndarray() entrega precios en punto fijo (enteros × 1e9)

# --- Banderas de los registros de Databento (databento_dbn) ---
F_LAST = 128
F_BAD_TS_RECV = 8
F_MAYBE_BAD_BOOK = 4
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


# =============================================================================
# 1. CONFIGURACIÓN
# =============================================================================
@dataclass(frozen=True)
class Config:
    # --- Datos ---
    dataset: str = "GLBX.MDP3"
    symbol: str = "NQ.n.0"                  # tu SYMBOL
    stype_in: str = "continuous"
    sesion_objetivo: str = "2026-08-20"     # tu START_DATE: la sesión que se ejecuta y se audita
    dias_calibracion: int = 10              # sesiones TBBO previas: eventos clave, MLE y walk-forward
    dias_perfil: int = 20                   # sesiones OHLCV-1m previas: perfiles de volumen y de σ
    esquema: str = "tbbo"                   # tbbo (operación + libro justo antes) · mbp-1
    cache_dir: str = "datos_databento"
    usar_cache: bool = True
    salida_dir: str = "salidas_ejecucion"
    costo_max_usd: float = 25.0
    bloque: int = 2_000_000
    tz_mercado: str = "America/Chicago"
    tz_local: str = "America/Mexico_City"
    spread_max_ticks: int = 8

    # --- 1. Eventos clave (motor del rastreador) ---
    rafaga_ms: float = 100.0                # huella = agresiones del mismo lado a ≤ 100 ms
    rafaga_max_ms: float = 1000.0
    p_grande: float = 0.95                  # evento clave = huella ≥ p95 de las sesiones anteriores
    p_mega: float = 0.99
    p_ballena: float = 0.999
    piso_contratos: int = 0
    min_eventos_fragmentada: int = 3
    oculta_min: int = 1
    ventana_magnitud: int = 5               # sesiones previas que dan el percentil
    min_ref: int = 2000
    por_franja: bool = True
    rth_ct: tuple[str, str] = ("08:30", "15:00")
    mle_franja: str = "rth"                 # rth = sólo eventos del horario regular · todo
    aislamiento_s: float = 0.0              # > 0: sólo eventos sin otro evento clave en esos segundos previos

    # --- 2. MLE del modelo de impacto ---
    horizontes_s: tuple[int, ...] = (0, 5, 15, 30, 60, 120, 300, 600, 1800)   # segundos después del print
    min_eventos: int = 300
    slot_min: int = 5                       # rejilla de los perfiles intradía (σ y volumen)
    sesiones_perfil: int = 10               # sesiones previas que promedia cada perfil

    # --- 3. Rolling ---
    ventana_sesiones: int = 5               # sesiones de eventos de cada ajuste rolling / walk-forward
    modelo_ejecucion: str = "propagador"    # propagador (G₀, sin la continuación del flujo) · respuesta
    n_param: int = 100                      # extracciones de θ para la incertidumbre paramétrica del costo

    # --- 4. Ejecución ---
    lado: int = 1                           # 1 = compra, −1 = venta
    orden: int = 5000                       # tu ORDER_SIZE
    inicio_ct: str = "08:30"                # tu 13:30 UTC = apertura de NY
    fin_ct: str = "15:00"                   # tu 20:00 UTC = cierre de NY
    slice_min: int = 5                      # tu N_SLICES = 78 de 5 min
    pov: float = 0.10                       # tu POV_PERCENTAGE
    pieza: int = 10                         # contratos por orden hija dentro de cada slice
    urgencia: float = 1.0                   # κ·T de Almgren–Chriss (0 = TWAP; más = más al principio)
    part_max: float = 0.25                  # participación por minuto que se marca como excesiva

    # --- Simulación (verdad conocida) ---
    sim_sesiones: int = 16
    sim_operaciones: int = 30_000           # operaciones por sesión
    sim_semilla: int = 0
    sim_Y: float = 0.15
    sim_delta: float = 0.5
    sim_pi: float = 0.4
    sim_tau: float = 90.0
    sim_memoria: float = 0.0                # persistencia del signo del flujo (0 = independiente)


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
    if not np.isfinite(v):
        return "—".rjust(ancho)
    return f"{(0.0 if abs(v) < 0.5 * 10 ** -dec else v):{ancho}.{dec}f}"


def _pct(x, dec=1, ancho=7) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "—".rjust(ancho)
    return f"{100.0 * v:{ancho}.{dec}f}%" if np.isfinite(v) else "—".rjust(ancho)


def _z(p: float) -> float:
    return float(NormalDist().inv_cdf(p))


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
    if cfg.esquema not in ("tbbo", "mbp-1"):
        sys.exit("❌ --esquema va tbbo (recomendado) o mbp-1: el modelo necesita el libro previo de cada operación.")
    if cfg.modelo_ejecucion not in ("propagador", "respuesta"):
        sys.exit("❌ --modelo-ejecucion va propagador o respuesta.")
    if cfg.mle_franja not in ("rth", "todo"):
        sys.exit("❌ --franja va rth o todo.")
    if not (0 < cfg.p_grande < 1):
        sys.exit("❌ --p-grande va entre 0 y 1.")
    hs = cfg.horizontes_s
    if len(hs) < 3 or hs[0] != 0 or any(b <= a for a, b in zip(hs, hs[1:])):
        sys.exit("❌ --horizontes debe empezar en 0 y crecer (p. ej. 0,5,15,30,60,120,300,600,1800).")
    if cfg.lado not in (1, -1) or cfg.orden <= 0:
        sys.exit("❌ La orden necesita --lado compra/venta y --orden > 0.")
    if not (0 < cfg.pov < 1) or cfg.pieza <= 0 or cfg.urgencia < 0:
        sys.exit("❌ Hace falta 0 < --pov < 1, --pieza > 0 y --urgencia ≥ 0.")
    if cfg.slice_min <= 0 or cfg.slot_min <= 0 or 60 % cfg.slot_min:
        sys.exit("❌ --slice-min debe ser positivo y slot_min dividir a 60.")
    if cfg.slice_min % cfg.slot_min:
        sys.exit("❌ --slice-min debe ser múltiplo de slot_min (los perfiles van por slot).")
    if cfg.ventana_sesiones < 2 or cfg.dias_calibracion < cfg.ventana_sesiones + 1:
        sys.exit("❌ Hace falta --ventana-sesiones ≥ 2 y --calibracion ≥ ventana + 1 (si no, no hay walk-forward).")
    try:
        a, b = segundo_de_hora(cfg.inicio_ct), segundo_de_hora(cfg.fin_ct)
        if a >= b:
            sys.exit("❌ --inicio debe ser antes de --fin (hora de Chicago).")
        if b > MINUTOS_SESION * 60:
            sys.exit("❌ --fin debe ser a más tardar 16:00 CT (de 16:00 a 17:00 Globex está cerrado).")
        if ((b - a) // 60) % cfg.slice_min or (b - a) % 60:
            sys.exit("❌ El horizonte --inicio → --fin debe ser un múltiplo exacto de --slice-min minutos.")
        pd.Timestamp(cfg.sesion_objetivo)
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


AYUDA_KEY = (
    "  • La key de Databento NO va en el código: se lee de la variable DATABENTO_API_KEY.\n"
    "  • La que estaba escrita en la línea 15 de Optimal_Execution_Algorithms.py hay que darla por\n"
    "    publicada: regenérala en https://databento.com/docs/portal/api-keys\n"
    '  • Guárdala una vez en PowerShell:  setx DATABENTO_API_KEY "db-..."  y cierra y abre VS Code.'
)


def dia_objetivo(cfg: Config) -> int:
    """Día de sesión (entero) de --sesion: la sesión de CME que lleva esa fecha."""
    return int(pd.Timestamp(cfg.sesion_objetivo).normalize().value // DIA_NS)


def dias_previos(dia: int, n: int) -> int:
    """El día de sesión que queda n sesiones hábiles antes de `dia`."""
    return int((fecha_de_dia(dia) - pd.offsets.BDay(n)).value // DIA_NS)


def obtener_datos(cfg: Config, esquema: str, inicio: pd.Timestamp, fin: pd.Timestamp, cliente=None):
    """
    Descarga a DISCO (no a memoria), revisando el costo antes, y devuelve el DBNStore; el motor
    lo lee por bloques.

    [v1] Tu script baja ohlcv-1m con to_df() y además DIVIDE entre 1e9: to_df() ya entrega los
    precios en decimales, así que tu NQ queda en 0.00002. Aquí los precios llegan en punto fijo
    (to_ndarray) y se convierten UNA vez, con el tick del contrato.
    """
    carpeta = _ruta(cfg.cache_dir)
    carpeta.mkdir(parents=True, exist_ok=True)
    i_txt, f_txt = inicio.strftime("%Y-%m-%dT%H:%M:%S"), fin.strftime("%Y-%m-%dT%H:%M:%S")
    ruta = carpeta / (_nombre_seguro(cfg.dataset, cfg.symbol, i_txt, f_txt, esquema) + ".dbn.zst")
    if ruta.exists() and cfg.usar_cache:
        print(f"📂 Usando caché local: {ruta.name}")
        return db.DBNStore.from_file(ruta), 0.0
    cliente = cliente or conectar()
    params = dict(dataset=cfg.dataset, symbols=[cfg.symbol], stype_in=cfg.stype_in, schema=esquema,
                  start=i_txt, end=f_txt)
    costo = float(cliente.metadata.get_cost(**params))
    try:
        tam = cliente.metadata.get_billable_size(**params)
    except Exception:
        tam = float("nan")
    print(f"💵 Costo estimado: US$ {costo:,.2f} · {tam / 1e9:,.2f} GB sin comprimir "
          f"({cfg.symbol}, {esquema}, {i_txt[:16]} → {f_txt[:16]} UTC)")
    return (cliente, params, ruta, costo), costo


def descargar(cfg: Config, pendiente) -> object:
    cliente, params, ruta, _ = pendiente
    temporal = ruta.with_name(ruta.name + ".parcial")
    temporal.unlink(missing_ok=True)
    print(f"📡 Descargando {params['symbols'][0]} ({params['schema']}) a {ruta.name} …")
    descarga = cliente.timeseries.get_range(**params, path=temporal)
    del descarga                                # Windows no renombra archivos abiertos
    temporal.replace(ruta)
    return db.DBNStore.from_file(ruta)


def obtener_todo(cfg: Config, cliente=None) -> tuple[object, object]:
    """
    Dos descargas, con UN tope de costo para las dos:
      · TBBO de `dias_calibracion` sesiones previas + la sesión objetivo (eventos, impacto, barras);
      · OHLCV-1m de `dias_perfil` sesiones previas + la objetivo (perfiles de volumen y σ, barato).
    """
    d = dia_objetivo(cfg)
    fin = pd.Timestamp(apertura_utc(d + 1, cfg.tz_mercado), tz="UTC")
    i_tbbo = pd.Timestamp(apertura_utc(dias_previos(d, cfg.dias_calibracion), cfg.tz_mercado), tz="UTC")
    i_ohlc = pd.Timestamp(apertura_utc(dias_previos(d, cfg.dias_perfil), cfg.tz_mercado), tz="UTC")
    a, ca = obtener_datos(cfg, cfg.esquema, i_tbbo, fin, cliente)
    b, cb = obtener_datos(cfg, "ohlcv-1m", i_ohlc, fin, cliente if cliente is not None else
                          (a[0] if isinstance(a, tuple) else None))
    if ca + cb > cfg.costo_max_usd:
        sys.exit(f"💰 El costo total (US$ {ca + cb:,.2f}) supera tu tope de US$ {cfg.costo_max_usd:,.2f}.\n"
                 f"   Si estás de acuerdo:  --costo-max {math.ceil(ca + cb) + 1}\n"
                 f"   Más barato:  --calibracion 6  (menos sesiones de TBBO)")
    tbbo = descargar(cfg, a) if isinstance(a, tuple) else a
    ohlc = descargar(cfg, b) if isinstance(b, tuple) else b
    return tbbo, ohlc



# =============================================================================
# 3. MOTOR DE EVENTOS, BARRAS Y PERFILES INTRADÍA
# =============================================================================
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
        self.partes = []                                   # no retener una copia de todos los eventos
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
    las `ventana_magnitud` sesiones ANTERIORES con datos (la actual no entra en su propia escala),
    por franja: el horario regular se compara con el horario regular y la noche con la noche.
    Umbrales GRANDE / MEGA / BALLENA = tamaños enteros con a lo más 5 % / 1 % / 0.1 % de la
    referencia por encima (umbral_discreto), más un piso absoluto opcional. El percentil de cada
    huella es su rango medio dentro de esa referencia.
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
            previas = sesiones[max(0, k - cfg.ventana_magnitud):k]
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
                clase[m] = (v >= q[0]).astype(int) + (v >= max(q[0], q[1])) + (v >= max(q[0], q[1], q[2]))
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
    """
    frag = H["n_eventos"].to_numpy() >= cfg.min_eventos_fragmentada
    absor = (H["span"].to_numpy() == 1) & (H["oculta"].to_numpy() >= max(1, cfg.oculta_min))
    barr = H["niv_max"].to_numpy() >= 2
    return np.select([absor, frag, barr], [2, 3, 1], 0).astype(np.int64)


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


def barras_bloque(arr: np.ndarray, tick_ns_: int, cfg: Config) -> pd.DataFrame:
    """
    Barras de 1 minuto (UTC) de un bloque TBBO: volumen agresor válido, Σ q·precio (para el VWAP
    del mercado), operaciones, último mid del libro previo válido y spread medio, todo en ticks.
    """
    r = normalizar(arr)
    if not len(r["t"]):
        return pd.DataFrame()
    valida, _, libro, _, _ = higiene(r, tick_ns_, cfg)
    m = r["t"] // NS_MIN
    out = []
    if valida.any():
        q = r["tam"][valida].astype(float)
        px = (r["precio"][valida] // tick_ns_).astype(float)
        out.append(pd.DataFrame({"m": m[valida], "vol": q, "qpx": q * px, "n": 1.0}).groupby("m").sum())
    if libro.any():
        mid = ((r["bpx"][libro] + r["apx"][libro]) / 2.0) / tick_ns_
        spr = (r["apx"][libro] - r["bpx"][libro]) / tick_ns_
        g = pd.DataFrame({"m": m[libro], "mid": mid, "spr": spr}).groupby("m")
        out.append(pd.DataFrame({"mid": g["mid"].last(), "spr_s": g["spr"].sum(), "spr_n": g["spr"].count()}))
    return pd.concat(out, axis=1) if out else pd.DataFrame()


def correr_motor_ejecucion(tienda, cfg: Config, verbose: bool = True) -> tuple[pd.DataFrame, MotorEventos, pd.DataFrame]:
    """DBNStore (o arreglo) → eventos y barras de 1 minuto, bloque por bloque."""
    tk = tick_ns(cfg.symbol)
    motor = MotorEventos(cfg, tk, guardar_crudo=False)
    partes = []
    inicio = time.time()
    for k, arr in enumerate(bloques(tienda, cfg)):
        motor.procesar(arr)
        partes.append(barras_bloque(arr, tk, cfg))
        if verbose and (k + 1) % 5 == 0:
            print(f"   … {motor.registros:,} registros ({time.time() - inicio:.0f} s)")
    motor.cerrar()
    if motor.registros == 0:
        sys.exit("❌ No llegaron registros de TBBO.")
    partes = [p for p in partes if len(p)]
    if partes:
        b = pd.concat(partes)
        g = b.groupby(level=0)
        barras = pd.DataFrame({c: g[c].sum() for c in ("vol", "qpx", "n", "spr_s", "spr_n") if c in b})
        if "mid" in b:
            barras["mid"] = g["mid"].last()
        barras = barras.sort_index()
    else:
        barras = pd.DataFrame()
    return motor.eventos(), motor, completar_barras(barras, cfg)


def completar_barras(barras: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Sesión y segundo de sesión de cada minuto, spread medio, VWAP del minuto y mid sin huecos."""
    if not len(barras):
        return barras
    b = barras.copy()
    for c in ("vol", "qpx", "n", "spr_s", "spr_n"):
        if c not in b:
            b[c] = 0.0
        b[c] = b[c].fillna(0.0)
    if "mid" not in b:
        b["mid"] = np.nan
    b.index.name = "m"
    t = b.index.to_numpy().astype(np.int64) * NS_MIN
    b["t"] = t
    b["sesion"], b["seg"] = reloj_sesion(t, cfg.tz_mercado)
    b["spread"] = b["spr_s"] / b["spr_n"].replace(0, np.nan)
    b["vwap"] = b["qpx"] / b["vol"].replace(0, np.nan)
    b["mid"] = b.groupby("sesion")["mid"].ffill()
    return b


def barras_ohlcv(tienda, cfg: Config) -> pd.DataFrame:
    """OHLCV-1m (to_ndarray, punto fijo) → minuto, cierre en ticks, volumen, sesión y segundo de sesión."""
    tk = tick(cfg.symbol)
    partes = []
    for arr in bloques(tienda, cfg):
        if not len(arr):
            continue
        nombres = arr.dtype.names
        cierre = arr["close"].astype(np.int64)
        ok = (cierre > 0) & (cierre != UNDEF_PRICE)
        if "instrument_id" in nombres:
            inst = arr["instrument_id"].astype(np.int64)
        else:
            inst = np.zeros(len(arr), np.int64)
        partes.append(pd.DataFrame({"m": arr["ts_event"].astype(np.int64)[ok] // NS_MIN,
                                    "close": cierre[ok] / PRICE_SCALE / tk,
                                    "vol": arr["volume"].astype(float)[ok], "inst": inst[ok]}))
    if not partes:
        return pd.DataFrame()
    todo = pd.concat(partes)
    varios = todo.groupby("m")["inst"].nunique()
    if len(varios) and (varios > 1).mean() > 0.01:
        sys.exit(f"❌ El OHLCV-1m trae varios contratos a la vez ({(varios > 1).mean():.0%} de los minutos).\n"
                 "   Usa simbología continua (NQ.n.0, como la descarga por omisión) o filtra un solo contrato.")
    b = todo.groupby("m").agg(close=("close", "last"), vol=("vol", "sum"), inst=("inst", "last"))
    t = b.index.to_numpy().astype(np.int64) * NS_MIN
    b["t"] = t
    b["sesion"], b["seg"] = reloj_sesion(t, cfg.tz_mercado)
    return b


def tabla_slots(barras: pd.DataFrame, cfg: Config, col_precio: str) -> pd.DataFrame:
    """
    Por sesión y slot de `slot_min`: volumen y varianza realizada (Σ de cambios de 1 minuto al
    cuadrado, en ticks²) dentro del slot. Los cambios no cruzan sesión ni roll.
    """
    if not len(barras):
        return pd.DataFrame()
    b = barras.dropna(subset=[col_precio])
    p = b[col_precio].to_numpy(dtype=float)
    ses = b["sesion"].to_numpy()
    inst = b["inst"].to_numpy() if "inst" in b else np.zeros(len(b), np.int64)
    d = np.r_[np.nan, np.diff(p)]
    corte = np.r_[True, (ses[1:] != ses[:-1]) | (inst[1:] != inst[:-1])]
    d[corte] = np.nan
    slot = (b["seg"].to_numpy() // (cfg.slot_min * 60)).astype(np.int64)
    df = pd.DataFrame({"sesion": ses, "slot": slot, "vol": b["vol"].to_numpy(dtype=float), "d2": d * d})
    T = df.groupby(["sesion", "slot"]).agg(vol=("vol", "sum"), var=("d2", "sum"), n=("d2", "count"))
    return T.reset_index()


class Perfiles:
    """
    Perfiles intradía CAUSALES: para la sesión s, el volumen y la σ de cada slot son los de las
    `sesiones_perfil` sesiones ANTERIORES (mediana del volumen; σ = raíz de la media recortada de
    la varianza realizada). Nunca usan la sesión que se ejecuta. El volumen sale del OHLCV-1m (más
    historia, barato); la σ, del MID del TBBO cuando hay: el cierre de 1 minuto trae el rebote
    bid-ask (con spreads de 1 tick el efecto es chico: en la simulación δ̂ sale igual con las dos).

    [v1] Tu vwap_schedule reparte la orden con el volumen del MISMO día que ejecuta: sabe a las
    8:30 cuánto se va a operar a las 14:00. Eso es mirar al futuro; un VWAP real sólo tiene el
    perfil de los días anteriores.
    """

    def __init__(self, slots: pd.DataFrame, cfg: Config, slots_mid: pd.DataFrame | None = None):
        self.cfg = cfg
        self.n_slots = MINUTOS_SESION // cfg.slot_min
        cols = range(self.n_slots)
        if len(slots):
            self.vol = slots.pivot(index="sesion", columns="slot", values="vol").reindex(columns=cols).fillna(0.0)
            self.var = slots.pivot(index="sesion", columns="slot", values="var").reindex(columns=cols)
        else:
            self.vol = pd.DataFrame(columns=cols, dtype=float)
            self.var = pd.DataFrame(columns=cols, dtype=float)
        if slots_mid is not None and len(slots_mid):
            vm = slots_mid.pivot(index="sesion", columns="slot", values="var").reindex(columns=cols)
            # varianza del mid donde hay TBBO; la del cierre (OHLCV) en las sesiones más viejas
            self.var = vm.combine_first(self.var)
            self.fuente_sigma = "mid del TBBO"
        else:
            self.fuente_sigma = "cierre del OHLCV-1m"
        self.tot = self.vol.sum(axis=1)
        self._cache: dict[int, tuple] = {}

    def de(self, dia: int) -> tuple[np.ndarray, np.ndarray, int]:
        """(volumen por slot, σ por slot en ticks, sesiones usadas) para la sesión `dia`."""
        if dia in self._cache:
            return self._cache[dia]
        # sesiones incompletas (festivos, cierres anticipados) no entran: el umbral, con el pasado
        tot = self.tot[self.tot.index < dia]
        previas = list(tot.index[tot >= 0.5 * tot.median()])[-self.cfg.sesiones_perfil:] if len(tot) else []
        if not previas:
            out = (np.full(self.n_slots, np.nan), np.full(self.n_slots, np.nan), 0)
        else:
            v = self.vol.loc[previas].to_numpy(dtype=float)
            w = self.var.reindex(previas).to_numpy(dtype=float)
            vol = np.nanmedian(v, axis=0)
            if len(previas) >= 4:                                   # media recortada: sin el máximo
                w = np.sort(np.where(np.isfinite(w), w, np.nan), axis=0)[:-1]
            sig = np.sqrt(np.nanmean(w, axis=0))
            out = (vol, sig, len(previas))
        self._cache[dia] = out
        return out


# =============================================================================
# 4. EXTRACCIÓN DE EVENTOS CLAVE — las huellas grandes y la trayectoria del precio
# =============================================================================
class Varianza:
    """
    Varianza ESPERADA del mid por sesión, con la U intradía: el perfil de σ² por slot de las sesiones
    anteriores (causal), acumulado en el tiempo. V(t₁) − V(t₀) es la varianza de difusión esperada
    entre t₀ y t₁ (ticks²). Con eso la covarianza del modelo sabe que 60 s a las 08:31 no son 60 s a
    las 12:00.
    """

    def __init__(self, perf: Perfiles, cfg: Config):
        self.perf = perf
        self.cfg = cfg
        self.slot_s = cfg.slot_min * 60
        self._cum: dict[int, tuple] = {}

    def acumulada(self, dia: int) -> tuple[int, np.ndarray]:
        if dia not in self._cum:
            _, sig, _ = self.perf.de(dia)
            var = np.where(np.isfinite(sig), sig ** 2, np.nan)
            med = np.nanmedian(var) if np.isfinite(var).any() else 1.0
            var = np.where(np.isfinite(var), var, med)
            self._cum[dia] = (apertura_utc(dia, self.cfg.tz_mercado), np.r_[0.0, np.cumsum(var)])
        return self._cum[dia]

    def V(self, dia: int, t_ns) -> np.ndarray:
        a, cum = self.acumulada(dia)
        x = (np.asarray(t_ns, dtype=np.int64) - a) / NS / self.slot_s
        x = np.clip(x, 0, len(cum) - 1)
        return np.interp(x, np.arange(len(cum)), cum)


@dataclass
class Observaciones:
    """Los eventos clave listos para el MLE: una fila por evento, una columna por horizonte."""
    K: pd.DataFrame                   # metadatos (hora, sesión, lado, Q, σ₅, V₅, spread, deriva, …)
    dm: np.ndarray                    # mid(observado) − mid de referencia, SIN signo, menos la deriva de la sesión
    horizontes: np.ndarray            # segundos (nominales)
    k: np.ndarray                     # horizontes disponibles de cada evento (prefijo)
    e: np.ndarray                     # segundos REALES desde el libro de referencia (t_ini⁻)
    e1: np.ndarray                    # segundos REALES desde el final de la huella (t_fin)
    Vd: np.ndarray                    # varianza de difusión esperada hasta cada observación (ticks²)
    t_obs: np.ndarray                 # ns de cada observación
    qe: np.ndarray                    # tamaño de cada EVENTO de cada huella, concatenados
    ptr: np.ndarray                   # dónde empiezan los eventos de cada huella en qe (n + 1)

    def sub(self, m: np.ndarray) -> "Observaciones":
        m = np.asarray(m, bool)
        cuenta = np.diff(self.ptr)
        qe = self.qe[np.repeat(m, cuenta)]
        ptr = np.r_[0, np.cumsum(cuenta[m])]
        return Observaciones(self.K[m].reset_index(drop=True), self.dm[m], self.horizontes, self.k[m], self.e[m],
                             self.e1[m], self.Vd[m], self.t_obs[m], qe, ptr)

    @property
    def n(self) -> int:
        return len(self.K)


def deriva_sesiones(E: pd.DataFrame, cfg: Config) -> dict:
    """
    Deriva de cada sesión en la franja del MLE (ticks/s): Σ (último mid − primer mid) / Σ duración, por
    TRAMO (misma sesión y mismo contrato), para que el salto de un roll no se reste como tendencia. Se
    resta de cada observación: en un día de tendencia las grandes van sobre todo del lado de la
    tendencia, y sin restarla la deriva se disfraza de impacto PERMANENTE en los horizontes largos.
    """
    if not len(E):
        return {}
    m = np.isfinite(E["mid0"].to_numpy(dtype=float))
    if cfg.mle_franja == "rth":
        m &= E["rth"].to_numpy().astype(bool)
    D = pd.DataFrame({"s": E["sesion"].to_numpy()[m], "i": E["inst"].to_numpy()[m], "t": E["t"].to_numpy()[m],
                      "mid": E["mid0"].to_numpy(dtype=float)[m]})
    if not len(D):
        return {}
    g = D.groupby(["s", "i"], sort=False).agg(t0=("t", "first"), t1=("t", "last"), m0=("mid", "first"), m1=("mid", "last"))
    g["dur"] = (g["t1"] - g["t0"]) / NS
    g["dm"] = g["m1"] - g["m0"]
    tot = g.groupby(level=0)[["dur", "dm"]].sum()
    tot = tot[tot["dur"] >= 1800.0]
    return {int(s): float(r["dm"] / r["dur"]) for s, r in tot.iterrows()}


def eventos_clave(H: pd.DataFrame, E: pd.DataFrame, perf: Perfiles, var: Varianza, deriva: dict,
                  cfg: Config) -> Observaciones:
    """
    EVENTO CLAVE = huella ≥ GRANDE (percentil `p_grande` de las sesiones ANTERIORES) en la franja del
    MLE. Para cada uno:
      · Q, lado del agresor, mid y spread del libro JUSTO ANTES del primer evento (la referencia);
      · σ₅ y V₅: la σ (ticks) y el volumen de 5 min que se esperaban a esa hora según los perfiles de
        las sesiones anteriores: Q / V₅ es la participación del print;
      · el mid observado a cada horizonte h: el del libro previo a la primera operación a partir de
        t_fin + h (h = 0: la primera DESPUÉS de la huella), sin cruzar la sesión ni un roll; si no hay,
        NaN. Con su tiempo REAL desde la referencia: el modelo usa ése, no la etiqueta (en el
        horizonte 0 la siguiente operación puede llegar segundos después);
      · la varianza de difusión esperada hasta cada observación (perfil intradía) y la deriva de su
        sesión, que se resta.
    Los horizontes disponibles de cada evento son un prefijo (k = cuántos).

    [v1] Tu script no tiene eventos: reparte una orden imaginaria sobre velas de 1 minuto. Sin ver las
    operaciones grandes reales no hay con qué medir cuánto mueve el precio una orden.
    """
    hs = np.asarray(cfg.horizontes_s, dtype=float)
    m = H["ventana"].to_numpy() & (H["clase"].to_numpy() >= 1) & H["libro0"].to_numpy().astype(bool)
    if cfg.mle_franja == "rth":
        m &= H["rth"].to_numpy().astype(bool)
    G = H[m]
    if cfg.aislamiento_s > 0 and len(G):
        t = G["t_ini"].to_numpy()
        ses = G["sesion"].to_numpy()
        hueco = np.r_[np.inf, np.diff(t) / NS]
        hueco[np.r_[True, ses[1:] != ses[:-1]]] = np.inf
        G = G[hueco > cfg.aislamiento_s]
    t_e = E["t"].to_numpy()
    mid_e = E["mid0"].to_numpy()
    ft = E["fin_tramo"].to_numpy()
    i1 = G["i_fin"].to_numpy()
    t0 = G["t_ini"].to_numpy()
    t1 = G["t_fin"].to_numpy()
    m0 = G["mid0"].to_numpy()
    n, kh = len(G), len(hs)
    dm = np.full((n, kh), np.nan)
    tob = np.zeros((n, kh), np.int64)
    previo = None
    for j, h in enumerate(hs):
        tq = t1 + int(h * NS)
        jj = np.searchsorted(t_e, t1, side="right") if h == 0 else np.searchsorted(t_e, tq, side="left")
        if previo is not None:
            # si no hubo operaciones entre dos horizontes, los dos caerían en la MISMA observación (dos
            # columnas idénticas que el modelo trataría como ruidos independientes: ω → 0). Se toma la
            # primera operación POSTERIOR a la del horizonte anterior; el modelo usa su tiempo real.
            jj = np.maximum(jj, np.searchsorted(t_e, t_e[np.minimum(previo, len(t_e) - 1)], side="right"))
        previo = jj
        jc = np.minimum(jj, len(t_e) - 1)
        ok = (jj < len(t_e)) & (jj <= ft[i1]) & np.isfinite(mid_e[jc])
        dm[:, j] = np.where(ok, mid_e[jc] - m0, np.nan)
        tob[:, j] = np.where(ok, t_e[jc], 0)
    fin = np.isnan(dm)
    k = np.where(fin.any(axis=1), fin.argmax(axis=1), kh)
    cols = np.arange(kh)[None, :]
    dm[cols >= k[:, None]] = np.nan
    e = np.where(cols < k[:, None], (tob - t0[:, None]) / NS, np.nan)
    e1 = np.where(cols < k[:, None], (tob - t1[:, None]) / NS, np.nan)
    ses = G["sesion"].to_numpy()
    slot = (G["seg"].to_numpy() // (cfg.slot_min * 60)).astype(np.int64)
    sig5 = np.full(n, np.nan)
    v5 = np.full(n, np.nan)
    Vd = np.full((n, kh), np.nan)
    mu = np.zeros(n)
    escala = 300.0 / (cfg.slot_min * 60)
    for s in np.unique(ses):
        vol, sig, _ = perf.de(int(s))
        sel = ses == s
        sig5[sel] = sig[slot[sel]] * math.sqrt(escala)
        v5[sel] = vol[slot[sel]] * escala
        v0 = var.V(int(s), t0[sel])
        vt = var.V(int(s), np.where(tob[sel] > 0, tob[sel], t0[sel][:, None]))
        Vd[sel] = vt - v0[:, None]
        mu[sel] = deriva.get(int(s), 0.0)
    dm = dm - mu[:, None] * e                                  # la deriva de la sesión no es impacto
    lado = G["lado"].to_numpy().astype(int)
    K = pd.DataFrame({"t_ini": t0, "t_fin": t1, "sesion": ses, "slot": slot, "lado": lado,
                      "Q": G["vol"].to_numpy().astype(float), "mid0": m0,
                      "spread": (G["ask0"] - G["bid0"]).to_numpy().astype(float), "sig5": sig5, "v5": v5,
                      "deriva": mu, "clase": G["clase"].to_numpy(), "tipo": G["tipo"].to_numpy(),
                      "vwap": G["vwap"].to_numpy(), "id_huella": G.index.to_numpy(),
                      "rth": G["rth"].to_numpy().astype(bool)})
    K["x"] = K["Q"] / K["v5"]
    K["costo_ef"] = K["lado"] * (K["vwap"] - K["mid0"])          # lo que pagó el agresor contra el mid
    hid = E["hid"].to_numpy()
    o = np.argsort(hid, kind="stable")
    ini_h = np.searchsorted(hid[o], G.index.to_numpy(), side="left")
    fin_h = np.searchsorted(hid[o], G.index.to_numpy(), side="right")
    vol_e = E["vol"].to_numpy().astype(float)[o]
    K["n_eventos"] = fin_h - ini_h
    ok = np.isfinite(sig5) & (sig5 > 0) & (v5 > 0) & (k >= 2)
    sel = np.flatnonzero(ok)
    qe = np.concatenate([vol_e[ini_h[i]:fin_h[i]] for i in sel]) if len(sel) else np.zeros(0)
    ptr = np.r_[0, np.cumsum((fin_h - ini_h)[sel])]
    return Observaciones(K[ok].reset_index(drop=True), dm[ok], hs, k[ok], e[ok], e1[ok], Vd[ok], tob[ok], qe, ptr)


class Flujo:
    """
    Todas las huellas de las sesiones (no sólo las grandes) con su signo, su tiempo y los tamaños de
    sus órdenes: con esto el modelo PROPAGADOR superpone el impacto de cada una sobre el precio
    (Bouchaud, Gefen, Potters y Wyart 2004), en lugar de atribuirle a la grande todo lo que pasa
    después de ella.
    """

    def __init__(self, H: pd.DataFrame, E: pd.DataFrame, perf: Perfiles, cfg: Config):
        orden = np.argsort(H["t_fin"].to_numpy(), kind="stable")
        self.orden = orden
        self.t = H["t_fin"].to_numpy().astype(np.int64)[orden]
        self.s = H["lado"].to_numpy().astype(float)
        ses = H["sesion"].to_numpy()
        slot = (H["seg"].to_numpy() // (cfg.slot_min * 60)).astype(np.int64)
        escala = 300.0 / (cfg.slot_min * 60)
        self.sig5 = np.zeros(len(H))
        self.v5 = np.ones(len(H))
        for s in np.unique(ses):
            vol, sig, _ = perf.de(int(s))
            sel = ses == s
            a, b = sig[slot[sel]] * math.sqrt(escala), vol[slot[sel]] * escala
            ok = np.isfinite(a) & np.isfinite(b) & (b > 0)
            self.sig5[np.flatnonzero(sel)[ok]] = a[ok]
            self.v5[np.flatnonzero(sel)[ok]] = b[ok]
        hid = E["hid"].to_numpy()
        o = np.argsort(hid, kind="stable")
        self.qe = E["vol"].to_numpy().astype(float)[o]
        self.ptr = np.r_[np.searchsorted(hid[o], H.index.to_numpy(), side="left"), len(o)]
        self._cache: dict = {}

    def amplitudes(self, A: float, delta: float, x_ref: float) -> np.ndarray:
        """s_j·f_j de cada huella con f = A·σ₅·Σₑ((qₑ/V₅)/x_ref)^δ, en el orden de t_fin."""
        s = np.add.reduceat(self.qe ** delta, self.ptr[:-1]) if len(self.qe) else np.zeros(len(self.t))
        return (self.s * A * self.sig5 * (self.v5 * x_ref) ** (-delta) * s)[self.orden]

    def estado_de(self, delta: float, tau: float, x_ref: float) -> tuple[np.ndarray, np.ndarray]:
        """(P, T) con A = 1, guardado por (δ, τ): en las diferencias finitas de π, ω, κ, ϕ no cambia."""
        clave = (float(delta), float(tau), float(x_ref))
        if clave not in self._cache:
            if len(self._cache) >= 6:
                self._cache.pop(next(iter(self._cache)))
            self._cache[clave] = self.estado(self.amplitudes(1.0, delta, x_ref), tau)
        return self._cache[clave]

    def indices(self, tq: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Para cada tiempo: la última huella ESTRICTAMENTE anterior, los segundos desde ella y si existe."""
        j = np.searchsorted(self.t, tq, side="left") - 1
        jc = np.maximum(j, 0)
        return jc, (tq - self.t[jc]) / NS, j >= 0

    def estado(self, b: np.ndarray, tau: float) -> tuple[np.ndarray, np.ndarray]:
        """(P, T) justo después de cada huella: P = Σ b (permanente), T = filtro exponencial (transitorio)."""
        P = np.cumsum(b)
        T = np.empty(len(b))
        t = (self.t - self.t[0]) / NS
        inicio, carga, n = 0, 0.0, len(b)
        while inicio < n:
            t0 = t[inicio]
            fin = int(np.searchsorted(t, t0 + 500.0 * tau, side="right"))
            fin = max(fin, inicio + 1)
            u = t[inicio:fin] - t0
            acum = np.cumsum(b[inicio:fin] * np.exp(u / tau))
            T[inicio:fin] = np.exp(-u / tau) * (carga + acum)
            carga = T[fin - 1] * math.exp(-(t[fin] - t[fin - 1]) / tau) if fin < n else 0.0
            inicio = fin
        return P, T

    def impacto_en(self, tq: np.ndarray, P: np.ndarray, T: np.ndarray, pi: float, tau: float,
                   idx: tuple | None = None) -> np.ndarray:
        """I(t) = π·P(t) + (1 − π)·T(t) con las huellas ESTRICTAMENTE anteriores a t."""
        jc, dt, ok = idx if idx is not None else self.indices(tq)
        val = pi * P[jc] + (1 - pi) * T[jc] * np.exp(-dt / tau)
        return np.where(ok, val, 0.0)


# =============================================================================
# 5. AJUSTE MATEMÁTICO DEL MODELO (MLE)
# =============================================================================
NO_LINEALES = ("delta", "pi", "tau", "omega", "kappa", "phi", "nu")
COTAS = {"delta": (0.05, 1.5), "pi": (-0.5, 1.5), "tau": (1.0, 7200.0), "omega": (1e-3, 5.0),
         "kappa": (0.05, 10.0), "phi": (0.0, 10.0), "nu": (2.5, 200.0)}
LOG_ESCALA = ("tau", "omega", "kappa")


def kernel(h, pi: float, tau: float) -> np.ndarray:
    """G(h) = π + (1 − π)·exp(−h/τ): la fracción del impacto inicial que queda a los h segundos."""
    return pi + (1.0 - pi) * np.exp(-np.asarray(h, float) / tau)


def base_huella(qe: np.ndarray, ptr: np.ndarray, sig5, v5, delta: float, x_ref: float) -> np.ndarray:
    """
    Impacto inicial de una HUELLA por unidad de A: σ₅·Σₑ((qₑ/V₅)/x_ref)^δ, la suma sobre las órdenes
    agresivas que la forman. Con δ < 1 dos órdenes de 10 mueven más que una de 20 (√2 veces con
    δ = 0.5); tratar la huella como una sola orden de Σ qₑ infla las huellas chicas —que suelen ser
    varias órdenes— y aplana la curva (en la simulación δ = 0.5 salía 0.44).
    """
    s = np.add.reduceat(qe ** delta, ptr[:-1]) if len(qe) else np.zeros(len(ptr) - 1)
    return np.asarray(sig5, float) * (np.asarray(v5, float) * x_ref) ** (-delta) * s


@dataclass(frozen=True)
class Especificacion:
    nombre: str
    media: str = "respuesta"          # respuesta (impacto propio) · propagador (todas las huellas)
    fijos: tuple = ()                 # ((parámetro, valor), …)
    dist: str = "normal"              # normal (QMLE, el principal) · t (robustez)


MODELOS = {
    "respuesta": Especificacion("respuesta a un print grande (δ libre)"),
    "propagador": Especificacion("propagador: todas las huellas superpuestas", "propagador"),
    "raiz": Especificacion("raíz cuadrada (δ = 0.5)", "respuesta", (("delta", 0.5),)),
    "lineal": Especificacion("lineal tipo Obizhaeva–Wang (δ = 1)", "respuesta", (("delta", 1.0),)),
    "t": Especificacion("respuesta, errores t (robustez)", "respuesta", (), "t"),
}


class Verosimilitud:
    """
    Log-verosimilitud por evento. Para el evento i y su observación a (tiempo real eₐ desde el libro
    de referencia, e'ₐ desde el final de la huella):
      respuesta:   Δmₐ = s·A·b_i·G(e'ₐ) + ruido          (b_i = base_huella: el tamaño normalizado)
      propagador:  Δmₐ = I(t_obs,a) − I(t_ref)  + ruido   (I = impacto vivo de TODAS las huellas)
    con la deriva de la sesión ya restada y
      Cov(Δₐ, Δ_b) = κ²·V(min(eₐ, e_b)) + ω²·(s₀ + 1{a = b}) + ϕ²·1{a = b = 0}:
      · V = varianza de difusión esperada con la U intradía (perfil causal), escalada por κ²;
      · ω² = ruido de microestructura del mid; el del mid de referencia (∝ spread previo², s₀) lo
        comparten todos los horizontes del evento;
      · ϕ² = varianza extra del horizonte 0 (el impacto inmediato no es igual para todos: barrer o no
        un nivel depende de la profundidad).
    Σ no depende de los parámetros de la media, así que el QMLE gaussiano estima bien la media aunque
    la covarianza no sea exacta (con errores sándwich). A entra lineal: dado lo demás, Â sale por GLS
    cerrado y sólo se optimizan los parámetros no lineales.
    """

    def __init__(self, obs: Observaciones, esp: Especificacion, x_ref: float, flujo: Flujo | None = None,
                 t_ref_ns: np.ndarray | None = None):
        self.obs = obs
        self.esp = esp
        self.x_ref = x_ref
        self.flujo = flujo
        self.grupos = []
        s0 = (np.maximum(obs.K["spread"].to_numpy(), 1.0)) ** 2
        for k in range(2, len(obs.horizontes) + 1):
            idx = np.flatnonzero(obs.k == k)
            if not len(idx):
                continue
            Vd = np.maximum(obs.Vd[idx, :k], 0.0)
            M = np.minimum(Vd[:, :, None], Vd[:, None, :])
            cuenta = np.diff(obs.ptr)[idx]
            qe = np.concatenate([obs.qe[obs.ptr[i]:obs.ptr[i + 1]] for i in idx])
            E0 = np.zeros((k, k))
            E0[0, 0] = 1.0
            self.grupos.append({"idx": idx, "k": k, "M": M, "s0": s0[idx], "I": np.eye(k), "E0": E0,
                                "e1": obs.e1[idx, :k], "y": obs.dm[idx, :k], "s": obs.K["lado"].to_numpy()[idx],
                                "qe": qe, "ptr": np.r_[0, np.cumsum(cuenta)],
                                "sig5": obs.K["sig5"].to_numpy()[idx], "v5": obs.K["v5"].to_numpy()[idx],
                                "tob": obs.t_obs[idx, :k], "tref": obs.K["t_ini"].to_numpy()[idx]})
            if flujo is not None and esp.media == "propagador":
                g = self.grupos[-1]
                g["i_obs"] = flujo.indices(g["tob"].ravel())
                g["i_ref"] = flujo.indices(g["tref"])
        self._inv: dict = {}

    def _sigma(self, g: dict, p: dict) -> np.ndarray:
        return ((p["kappa"] ** 2) * g["M"] + (p["omega"] ** 2) * (g["s0"][:, None, None] + g["I"][None])
                + (p["phi"] ** 2) * g["E0"][None])

    def medias_unitarias(self, p: dict) -> list:
        """La media de cada grupo con A = 1 (la media es lineal en A)."""
        out = []
        if self.esp.media == "propagador":
            P, T = self.flujo.estado_de(p["delta"], p["tau"], self.x_ref)
        for g in self.grupos:
            if self.esp.media == "propagador":
                I_obs = self.flujo.impacto_en(None, P, T, p["pi"], p["tau"], g["i_obs"]).reshape(g["tob"].shape)
                I_ref = self.flujo.impacto_en(None, P, T, p["pi"], p["tau"], g["i_ref"])
                out.append(I_obs - I_ref[:, None])
            else:
                b = base_huella(g["qe"], g["ptr"], g["sig5"], g["v5"], p["delta"], self.x_ref)
                out.append((g["s"] * b)[:, None] * kernel(g["e1"], p["pi"], p["tau"]))
        return out

    def inversas(self, p: dict) -> list:
        """
        (Σ⁻¹, log|Σ|, Σ⁻¹y) de cada grupo. Σ depende sólo de (κ, ω, ϕ): se guardan las últimas, así las
        diferencias finitas en δ, π y τ —la mitad de las evaluaciones del optimizador— no la invierten.
        """
        clave = (float(p["kappa"]), float(p["omega"]), float(p["phi"]))
        if clave not in self._inv:
            if len(self._inv) >= 8:
                self._inv.pop(next(iter(self._inv)))
            res = []
            for g in self.grupos:
                Sig = self._sigma(g, p)
                L = np.linalg.cholesky(Sig)                        # falla si Σ no es definida positiva
                Si = np.linalg.inv(Sig)
                res.append((Si, 2.0 * np.log(np.diagonal(L, axis1=1, axis2=2)).sum(axis=1),
                            (Si @ g["y"][:, :, None])[:, :, 0]))
            self._inv[clave] = res
        return self._inv[clave]

    def piezas(self, p: dict) -> tuple[list, list]:
        """Por grupo: (Σ⁻¹·u, Σ⁻¹·y, log|Σ|, u, y) para el GLS de A y la verosimilitud."""
        us = self.medias_unitarias(p)
        res = []
        for g, u, (Si, logdet, Siy) in zip(self.grupos, us, self.inversas(p)):
            res.append(((Si @ u[:, :, None])[:, :, 0], Siy, logdet, u, g["y"]))
        return res, us

    def A_gls(self, p: dict, piezas: list | None = None) -> float:
        piezas = piezas or self.piezas(p)[0]
        num = sum(float(np.einsum("ij,ij->", u, Siy)) for Siu, Siy, _, u, y in piezas)
        den = sum(float(np.einsum("ij,ij->", u, Siu)) for Siu, Siy, _, u, y in piezas)
        return num / den if den > 0 else 0.0

    def por_evento(self, p: dict, A: float | None = None) -> tuple[np.ndarray, float]:
        """(log-verosimilitud de cada evento, A usado). Si A es None, se concentra por GLS."""
        piezas, _ = self.piezas(p)
        if A is None:
            A = self.A_gls(p, piezas)
            if self.esp.dist == "t":
                A = self._A_t(p, piezas, A)
        out = np.empty(self.obs.n)
        for g, (Siu, Siy, logdet, u, y) in zip(self.grupos, piezas):
            # rᵀΣ⁻¹r con r = y − A·u = yᵀΣ⁻¹y − 2A·uᵀΣ⁻¹y + A²·uᵀΣ⁻¹u
            q = (np.einsum("ij,ij->i", y, Siy) - 2 * A * np.einsum("ij,ij->i", u, Siy)
                 + A * A * np.einsum("ij,ij->i", u, Siu))
            q = np.maximum(q, 0.0)
            k = g["k"]
            if self.esp.dist == "t":
                nu = p["nu"]
                ll = (math.lgamma((nu + k) / 2) - math.lgamma(nu / 2) - 0.5 * k * math.log((nu - 2) * math.pi)
                      - 0.5 * logdet - 0.5 * (nu + k) * np.log1p(q / (nu - 2)))
            else:
                ll = -0.5 * (k * math.log(2 * math.pi) + logdet + q)
            out[g["idx"]] = ll
        return out, A

    def _A_t(self, p: dict, piezas: list, A: float, iters: int = 100) -> float:
        """
        A de máxima verosimilitud con errores t (ν y Σ dados): mínimos cuadrados reponderados con
        wᵢ = (ν + k)/(ν − 2 + qᵢ), que bajan el peso de los eventos extremos. Empieza en el GLS.
        """
        nu = p["nu"]
        partes = [(np.einsum("ij,ij->i", y, Siy), np.einsum("ij,ij->i", u, Siy), np.einsum("ij,ij->i", u, Siu), g["k"])
                  for g, (Siu, Siy, _, u, y) in zip(self.grupos, piezas)]
        for _ in range(iters):
            num = den = 0.0
            for yy, uy, uu, k in partes:
                q = np.maximum(yy - 2 * A * uy + A * A * uu, 0.0)
                w = (nu + k) / (nu - 2 + q)
                num += float(w @ uy)
                den += float(w @ uu)
            nuevo = num / den if den > 0 else A
            if abs(nuevo - A) <= 1e-10 * (1 + abs(A)):
                return nuevo
            A = nuevo
        return A

    def mahalanobis(self, p: dict, A: float) -> tuple[np.ndarray, np.ndarray]:
        piezas, _ = self.piezas(p)
        d2 = np.empty(self.obs.n)
        kk = np.empty(self.obs.n, int)
        for g, (Siu, Siy, logdet, u, y) in zip(self.grupos, piezas):
            d2[g["idx"]] = np.maximum(np.einsum("ij,ij->i", y, Siy) - 2 * A * np.einsum("ij,ij->i", u, Siy)
                                      + A * A * np.einsum("ij,ij->i", u, Siu), 0.0)
            kk[g["idx"]] = g["k"]
        return d2, kk



@dataclass
class Ajuste:
    esp: Especificacion
    p: dict                           # parámetros no lineales (naturales)
    A: float                          # impacto inmediato de un print de tamaño de referencia (unidades de σ₅)
    x_ref: float
    ll: float
    n: int
    sesiones: int
    libres: list
    se: dict = field(default_factory=dict)          # max(CR1, CV3)
    se_cr1: dict = field(default_factory=dict)
    se_cv3: dict = field(default_factory=dict)
    se_hess: dict = field(default_factory=dict)     # supone eventos independientes (sólo de referencia)
    ic: dict = field(default_factory=dict)
    claic: float = np.nan
    jackknife: dict = field(default_factory=dict)   # sesión → (A, p) sin ella
    avisos: list = field(default_factory=list)
    evaluaciones: int = 0
    V: np.ndarray | None = None                     # covarianza robusta en la escala del optimizador
    nombres_v: list = field(default_factory=list)
    en_cota: list = field(default_factory=list)     # parámetros que quedaron en una cota: sin EE (fijos)

    @property
    def k_par(self) -> int:
        return len(self.libres) + 1


def _a_opt(nm: str, v: float) -> float:
    return math.log(v) if nm in LOG_ESCALA else v


def _de_opt(nm: str, x: float) -> float:
    return math.exp(min(max(x, -700.0), 700.0)) if nm in LOG_ESCALA else x


def _cotas_opt(nm: str) -> tuple[float, float]:
    lo, hi = COTAS[nm]
    return (math.log(lo), math.log(hi)) if nm in LOG_ESCALA else (lo, hi)


def x_referencia(obs: Observaciones) -> float:
    """Tamaño de referencia: la media geométrica de Q/V₅ de los eventos clave (A queda casi ortogonal a δ)."""
    x = obs.K["x"].to_numpy()
    x = x[np.isfinite(x) & (x > 0)]
    return float(np.exp(np.mean(np.log(x)))) if len(x) else 0.01


def _nelder_mead(fun, x0: np.ndarray, lo: np.ndarray, hi: np.ndarray, iters: int = 3000,
                 tol: float = 1e-10) -> tuple[np.ndarray, float, int]:
    """Nelder–Mead propio, con los puntos recortados a las cotas (por si no hay scipy)."""
    n = len(x0)
    clip = lambda z: np.minimum(np.maximum(z, lo), hi)   # noqa: E731
    S = [clip(x0)] + [clip(x0 + 0.25 * (hi - lo) * 0.2 * np.eye(n)[i]) for i in range(n)]
    F = [fun(z) for z in S]
    ev = n + 1
    for _ in range(iters):
        o = np.argsort(F)
        S, F = [S[i] for i in o], [F[i] for i in o]
        if abs(F[-1] - F[0]) < tol * (1 + abs(F[0])):
            break
        c = np.mean(S[:-1], axis=0)
        xr = clip(c + (c - S[-1]))
        fr = fun(xr)
        ev += 1
        if fr < F[0]:
            xe = clip(c + 2 * (c - S[-1]))
            fe = fun(xe)
            ev += 1
            S[-1], F[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < F[-2]:
            S[-1], F[-1] = xr, fr
        else:
            xc = clip(c + 0.5 * (S[-1] - c))
            fc = fun(xc)
            ev += 1
            if fc < F[-1]:
                S[-1], F[-1] = xc, fc
            else:
                S = [S[0]] + [S[0] + 0.5 * (z - S[0]) for z in S[1:]]
                F = [F[0]] + [fun(z) for z in S[1:]]
                ev += n
    i = int(np.argmin(F))
    return S[i], float(F[i]), ev


INICIO = {"delta": 0.5, "pi": 0.5, "tau": 60.0, "omega": 0.3, "kappa": 1.0, "phi": 0.5, "nu": 8.0}


CARO = ("kappa", "omega", "phi")                      # los que cambian Σ (cada evaluación la invierte)


def _minimizar(fun, x0: np.ndarray, lo: np.ndarray, hi: np.ndarray, maxiter: int = 400) -> tuple[np.ndarray, float, int]:
    if not len(x0):
        return x0, float(fun(x0)), 1
    if _sp_minimize is not None:
        r = _sp_minimize(fun, x0, method="L-BFGS-B", bounds=list(zip(lo, hi)),
                         options={"maxiter": maxiter, "eps": 1e-6, "ftol": 1e-12, "gtol": 1e-6})
        return np.asarray(r.x), float(r.fun), int(r.nfev)
    return _nelder_mead(fun, x0, lo, hi, iters=20 * maxiter)


def ajustar(obs: Observaciones, esp: Especificacion, x_ref: float, flujo: Flujo | None = None,
            inicio: dict | None = None, errores: bool = True, jackknife: bool = False,
            arranques: tuple = (5.0, 60.0, 600.0), vero: Verosimilitud | None = None) -> Ajuste:
    """
    Máxima verosimilitud (QMLE gaussiano por omisión). A se concentra por GLS y se optimizan los no
    lineales (δ, π, τ, ω, κ, ϕ y ν si es t) con L-BFGS-B dentro de cotas en escala natural —τ, ω y κ
    en logaritmo—; sin scipy, Nelder–Mead propio. Por bloques: la media (δ, π, τ) y la covarianza
    (κ, ω, ϕ) son casi ortogonales en la información de Fisher, y sólo los cambios de la covarianza
    obligan a invertir Σ; se alterna un bloque y otro —la media desde varios τ iniciales— y se pule
    con un paso conjunto. Errores estándar:
      · CR1: sándwich H⁻¹(Σ_g s_g s_gᵀ)H⁻¹·G/(G−1) agrupado por SESIÓN (los eventos de una sesión
        comparten régimen y se traslapan);
      · CV3: jackknife quitando una sesión a la vez (más honesto con pocas sesiones);
      · se reporta el mayor de los dos, con IC de la t con G − 1 gl (en escala log para τ, ω y κ).
    El EE del hessiano solo (eventos independientes) queda de referencia: suele ser varias veces menor.
    """
    vero = vero or Verosimilitud(obs, esp, x_ref, flujo)
    fijos = dict(esp.fijos)
    libres = [nm for nm in NO_LINEALES if nm not in fijos and not (nm == "nu" and esp.dist != "t")]
    base = dict(INICIO)
    if inicio:
        base.update({k: v for k, v in inicio.items() if k in base})
    base.update(fijos)
    lo = np.array([_cotas_opt(nm)[0] for nm in libres])
    hi = np.array([_cotas_opt(nm)[1] for nm in libres])
    ev_tot = [0]

    def a_p(x):
        p = dict(base)
        for nm, v in zip(libres, x):
            p[nm] = _de_opt(nm, v)
        return p

    def nll(x):
        ev_tot[0] += 1
        try:
            v = -float(vero.por_evento(a_p(x))[0].sum())
        except np.linalg.LinAlgError:
            return 1e300
        return v if np.isfinite(v) else 1e300

    def por_bloque(x, cuales):
        """Optimiza sólo las coordenadas `cuales` de x."""
        j = np.array([i for i, nm in enumerate(libres) if nm in cuales], int)
        if not len(j):
            return x, nll(x)

        def f(z):
            w = x.copy()
            w[j] = z
            return nll(w)
        z, fz, _ = _minimizar(f, x[j], lo[j], hi[j])
        w = x.copy()
        w[j] = z
        return w, fz

    baratos = [nm for nm in libres if nm not in CARO]
    caros = [nm for nm in libres if nm in CARO]
    x = np.clip(np.array([_a_opt(nm, base[nm]) for nm in libres]), lo, hi)
    x, f = por_bloque(x, caros)
    starts = arranques if (inicio is None and "tau" in libres) else (base["tau"],)
    mejores = []
    for tau0 in starts:
        x0 = x.copy()
        if "tau" in libres:
            x0[libres.index("tau")] = np.clip(_a_opt("tau", tau0), *_cotas_opt("tau"))
        mejores.append(por_bloque(x0, baratos)[::-1])
    f, x = min(mejores, key=lambda u: u[0])
    for _ in range(6):
        f_ant = f
        x, f = por_bloque(x, caros)
        x, f = por_bloque(x, baratos)
        if f_ant - f < 1e-3:
            break
    x2, f2, _ = _minimizar(nll, x, lo, hi, maxiter=200)
    if f2 < f:
        x, f = x2, f2
    p = a_p(x)
    ll_vec, A = vero.por_evento(p)
    aj = Ajuste(esp, p, A, x_ref, float(ll_vec.sum()), obs.n, int(obs.K["sesion"].nunique()), libres,
                evaluaciones=ev_tot[0])
    for nm in libres:
        b_lo, b_hi = _cotas_opt(nm)
        if min(abs(x[libres.index(nm)] - b_lo), abs(b_hi - x[libres.index(nm)])) < 1e-3 * (b_hi - b_lo):
            aj.en_cota.append(nm)
            if nm == "phi" and abs(x[libres.index(nm)] - b_lo) < 1e-3 * (b_hi - b_lo):
                continue                                           # ϕ = 0: sin varianza extra en el horizonte 0
            aj.avisos.append(f"{nm} quedó en la cota ({p[nm]:.3g}): no identificado con estos datos")
    if errores and obs.n > len(libres) + 10:
        errores_estandar(aj, vero, base, jackknife)
    return aj


def errores_estandar(aj: Ajuste, vero: Verosimilitud, base: dict, jackknife: bool) -> None:
    # los que quedaron en una cota no tienen score cero ni curvatura válida: se tratan como FIJOS (si no,
    # el hessiano deja de ser definido positivo, el castigo del CLAIC sale negativo y los IC explotan)
    libres = [nm for nm in aj.libres if nm not in aj.en_cota]
    nombres = ["A"] + libres
    x0 = np.r_[aj.A, [_a_opt(nm, aj.p[nm]) for nm in libres]]
    kp = len(x0)
    base = dict(base, **aj.p)

    def ll_vec(x):
        p = dict(base)
        for nm, v in zip(libres, x[1:]):
            p[nm] = _de_opt(nm, v)
        return vero.por_evento(p, A=x[0])[0]

    hstep = 1e-4 * np.maximum(1.0, np.abs(x0))
    hstep[0] = 1e-4 * max(abs(x0[0]), 1e-3)
    S = np.zeros((aj.n, kp))
    for j in range(kp):
        e = np.zeros(kp)
        e[j] = hstep[j]
        S[:, j] = (ll_vec(x0 + e) - ll_vec(x0 - e)) / (2 * hstep[j])
    Hm = np.zeros((kp, kp))
    f0 = ll_vec(x0).sum()
    for i in range(kp):
        for j in range(i, kp):
            ei = np.zeros(kp)
            ej = np.zeros(kp)
            ei[i], ej[j] = hstep[i], hstep[j]
            if i == j:
                v = (ll_vec(x0 + ei).sum() - 2 * f0 + ll_vec(x0 - ei).sum()) / hstep[i] ** 2
            else:
                v = (ll_vec(x0 + ei + ej).sum() - ll_vec(x0 + ei - ej).sum() - ll_vec(x0 - ei + ej).sum()
                     + ll_vec(x0 - ei - ej).sum()) / (4 * hstep[i] * hstep[j])
            Hm[i, j] = Hm[j, i] = -v
    def_pos = bool(np.all(np.linalg.eigvalsh((Hm + Hm.T) / 2) > 0))
    try:
        Hi = np.linalg.inv(Hm) if def_pos else np.linalg.pinv(Hm)
    except np.linalg.LinAlgError:
        Hi = np.linalg.pinv(Hm)
    if not def_pos:
        aj.avisos.append("el hessiano no es definido positivo: EE poco confiables y sin CLAIC")
    ses = vero.obs.K["sesion"].to_numpy()
    usesiones, inv = np.unique(ses, return_inverse=True)
    G = len(usesiones)
    Sg = np.zeros((G, kp))
    np.add.at(Sg, inv, S)
    J = Sg.T @ Sg
    V_cr1 = Hi @ J @ Hi * (G / (G - 1) if G > 1 else 1.0)
    aj.claic = -2 * aj.ll + 2 * float(np.trace(J @ Hi)) if def_pos else np.nan
    V = V_cr1.copy()
    if jackknife and G >= 3:
        thetas = []
        for g in usesiones:
            sub = vero.obs.sub(ses != g)
            vg = Verosimilitud(sub, vero.esp, aj.x_ref, vero.flujo)
            aj_g = ajustar(sub, vero.esp, aj.x_ref, vero.flujo, inicio=aj.p, errores=False, vero=vg)
            thetas.append(np.r_[aj_g.A, [_a_opt(nm, aj_g.p[nm]) for nm in libres]])
            aj.jackknife[int(g)] = (aj_g.A, dict(aj_g.p))
        T = np.array(thetas) - x0[None, :]
        V_cv3 = (G - 1) / G * (T.T @ T)
        for j, nm in enumerate(nombres):
            aj.se_cv3[nm] = math.sqrt(max(V_cv3[j, j], 0.0))
        # varianzas: la mayor de las dos; correlaciones: las de CR1 (así V queda semidefinida positiva)
        d1 = np.sqrt(np.maximum(np.diag(V_cr1), 0.0))
        d = np.sqrt(np.maximum(np.maximum(np.diag(V_cr1), np.diag(V_cv3)), 0.0))
        R = V_cr1 / np.where(np.outer(d1, d1) > 0, np.outer(d1, d1), 1.0)
        V = R * np.outer(d, d)
    w, Q = np.linalg.eigh((V + V.T) / 2)
    V = (Q * np.maximum(w, 0.0)) @ Q.T
    aj.V, aj.nombres_v = (V if def_pos else None), nombres
    tq = t_cuantil(0.975, G - 1) if G > 1 else np.nan
    for j, nm in enumerate(nombres):
        der = 1.0 if nm == "A" or nm not in LOG_ESCALA else _de_opt(nm, x0[j])
        se_cr1 = math.sqrt(max(V_cr1[j, j], 0.0))
        se_rob = max(se_cr1, aj.se_cv3.get(nm, 0.0) if nm in aj.se_cv3 else 0.0)
        aj.se_cr1[nm] = der * se_cr1
        aj.se_hess[nm] = der * math.sqrt(max(Hi[j, j], 0.0))
        if nm in aj.se_cv3:
            aj.se_cv3[nm] = der * aj.se_cv3[nm]
        aj.se[nm] = der * se_rob
        lo_, hi_ = x0[j] - tq * se_rob, x0[j] + tq * se_rob
        if nm != "A":                                              # acotado al dominio (y sin desbordar exp)
            b_lo, b_hi = _cotas_opt(nm)
            lo_, hi_ = min(max(lo_, b_lo), b_hi), min(max(hi_, b_lo), b_hi)
        aj.ic[nm] = (lo_, hi_) if nm == "A" else (_de_opt(nm, lo_), _de_opt(nm, hi_))
    if "pi" in libres and aj.se_hess.get("pi", 0) > 0.25:
        aj.avisos.append(f"π no identificado: EE ≥ {aj.se_hess['pi']:.2f} aun suponiendo eventos independientes")


def prueba_wald(aj: Ajuste, nm: str, valor: float) -> tuple[float, float]:
    """t robusta (max CR1, CV3) de H0: parámetro = valor, con G − 1 gl."""
    v = aj.A if nm == "A" else aj.p.get(nm, np.nan)
    se = aj.se.get(nm, np.nan)
    if not (np.isfinite(se) and se > 0):
        return np.nan, np.nan
    t = (v - valor) / se
    return t, p_t(t, max(aj.sesiones - 1, 1))


def curva_semiparametrica(aj: Ajuste, vero: Verosimilitud) -> pd.DataFrame:
    """
    La trayectoria EMPÍRICA del impacto sin forma funcional: s·Δm(h) = f_i·g_h + ruido, con f_i del
    ajuste (Â, δ̂) y la misma covarianza, por GLS para el vector g (g_0 ≈ 1 si el modelo cuadra).
    IC agrupado por sesión con la t de G − 1 gl. Es lo que el panel del ajuste compara contra G(h).
    """
    obs = vero.obs
    K = len(obs.horizontes)
    XtX = np.zeros((K, K))
    Xty = np.zeros(K)
    piezas = []
    for g in vero.grupos:
        k = g["k"]
        f = aj.A * base_huella(g["qe"], g["ptr"], g["sig5"], g["v5"], aj.p["delta"], aj.x_ref)
        Sig = vero._sigma(g, aj.p)
        Si = np.linalg.inv(Sig)
        sy = g["s"][:, None] * g["y"]
        XtX[:k, :k] += np.einsum("i,ijk->jk", f * f, Si)
        Xty[:k] += np.einsum("i,ijk,ik->j", f, Si, sy)
        piezas.append((g, f, Si, sy, k))
    usados = np.flatnonzero(np.diag(XtX) > 0)
    gh = np.full(K, np.nan)
    sub = XtX[np.ix_(usados, usados)]
    gh[usados] = np.linalg.solve(sub, Xty[usados])
    ses = obs.K["sesion"].to_numpy()
    u_ses, inv = np.unique(ses, return_inverse=True)
    Sg = np.zeros((len(u_ses), K))
    for g, f, Si, sy, k in piezas:
        r = sy - f[:, None] * gh[None, :k]
        sc = f[:, None] * np.einsum("ijk,ik->ij", Si, r)
        np.add.at(Sg[:, :k], inv[g["idx"]], sc)
    Gn = len(u_ses)
    Bi = np.linalg.inv(sub)
    Vg = Bi @ (Sg[:, usados].T @ Sg[:, usados]) @ Bi * (Gn / (Gn - 1) if Gn > 1 else 1)
    se = np.full(K, np.nan)
    se[usados] = np.sqrt(np.maximum(np.diag(Vg), 0))
    tq = t_cuantil(0.975, Gn - 1) if Gn > 1 else np.nan
    T = pd.DataFrame({"h": obs.horizontes, "g": gh, "se": se, "ic_bajo": gh - tq * se, "ic_alto": gh + tq * se,
                      "modelo": kernel(obs.horizontes, aj.p["pi"], aj.p["tau"])})
    T.attrs["V"] = Vg
    T.attrs["usados"] = usados
    return T


def prueba_permanente(curva: pd.DataFrame, sesiones: int, desde: float = 15, hasta: float = 60) -> tuple[float, float, float]:
    """
    H0: no hay decaimiento (π = 1 ⇒ g ≡ 1). Sobre la curva semiparamétrica, el promedio de g entre 15 y
    60 s (la zona con información, fijada de antemano) contra 1, con t robusta de G − 1 gl. Evita el
    LR de π = 1, que está en la frontera y con τ sin identificar bajo H0 (problema de Davies).
    """
    V, usados = curva.attrs["V"], list(curva.attrs["usados"])
    sel = [j for j in usados if desde <= curva["h"].iloc[j] <= hasta]
    if not sel:
        return np.nan, np.nan, np.nan
    w = np.zeros(len(usados))
    for j in sel:
        w[usados.index(j)] = 1.0 / len(sel)
    gbar = float(np.dot(w, curva["g"].to_numpy()[usados]))
    se = math.sqrt(max(float(w @ V @ w), 0.0))
    t = (gbar - 1.0) / se if se > 0 else np.nan
    return gbar, t, p_t(t, max(sesiones - 1, 1))


def perfil_delta(obs: Observaciones, aj: Ajuste, vero: Verosimilitud, rejilla: np.ndarray | None = None) -> pd.DataFrame:
    """
    Perfil de verosimilitud de δ: para cada δ fijo se re-optimiza lo demás. Como la verosimilitud es
    COMPUESTA (los eventos no son independientes), el LR se escala por ĉ = V_robusta/V_hessiano de δ y
    se compara con ĉ·t²(G−1, 0.975) para el IC.
    """
    lo_d, hi_d = COTAS["delta"]
    se_r, se_h = aj.se.get("delta", np.nan), aj.se_hess.get("delta", np.nan)
    c0 = (se_r / se_h) ** 2 if (np.isfinite(se_r) and np.isfinite(se_h) and se_h > 0) else 1.0
    c0 = max(c0, 1.0)
    medio = max(np.nanmax([se_r, se_h, 0.0]), 0.01) * 2.0 * math.sqrt(c0)
    if rejilla is None:
        fina = np.clip(aj.p["delta"] + medio * np.linspace(-2, 2, 13), lo_d, hi_d)
        rejilla = np.unique(np.round(np.r_[fina, 0.5, 1.0], 4))
    filas = []
    inicio = dict(aj.p)
    for d in rejilla:
        esp = Especificacion(f"δ = {d}", vero.esp.media, tuple(list(vero.esp.fijos) + [("delta", float(d))]), vero.esp.dist)
        a = ajustar(obs, esp, aj.x_ref, vero.flujo, inicio=inicio, errores=False,
                    vero=Verosimilitud(obs, esp, aj.x_ref, vero.flujo))
        inicio = dict(a.p)
        filas.append({"delta": float(d), "ll": a.ll, "A": a.A})
    c = c0
    u = t_cuantil(0.975, max(aj.sesiones - 1, 1)) ** 2
    # si un lado no llega al umbral, se extiende la rejilla de ese lado (hasta la cota)
    for _ in range(4):
        T = pd.DataFrame(filas)
        lr = np.maximum(2 * (aj.ll - T["ll"]) / c, 0.0)
        nuevos = []
        abajo, arriba = T["delta"] < aj.p["delta"], T["delta"] > aj.p["delta"]
        if not (lr[abajo] > u).any() and T["delta"].min() > lo_d + 1e-6:
            nuevos.append(max(T["delta"].min() - 2 * medio, lo_d))
        if not (lr[arriba] > u).any() and T["delta"].max() < hi_d - 1e-6:
            nuevos.append(min(T["delta"].max() + 2 * medio, hi_d))
        if not nuevos:
            break
        for d in nuevos:
            esp = Especificacion(f"δ = {d}", vero.esp.media, tuple(list(vero.esp.fijos) + [("delta", float(d))]), vero.esp.dist)
            a = ajustar(obs, esp, aj.x_ref, vero.flujo, inicio=dict(aj.p), errores=False,
                        vero=Verosimilitud(obs, esp, aj.x_ref, vero.flujo))
            filas.append({"delta": float(d), "ll": a.ll, "A": a.A})
    T = pd.DataFrame(filas).sort_values("delta").reset_index(drop=True)
    T["lr"] = np.maximum(2 * (aj.ll - T["ll"]) / c, 0.0)
    T.attrs["umbral"] = u
    T.attrs["c"] = c
    # IC: donde el LR cruza el umbral, interpolando a cada lado de δ̂
    d, lr = T["delta"].to_numpy(), T["lr"].to_numpy()
    ic = [np.nan, np.nan]
    for lado, sel in ((0, d <= aj.p["delta"]), (1, d >= aj.p["delta"])):
        dd, ll_ = d[sel], lr[sel]
        if lado == 0:
            dd, ll_ = dd[::-1], ll_[::-1]
        dd, ll_ = np.r_[aj.p["delta"], dd], np.r_[0.0, ll_]
        cruza = np.flatnonzero((ll_[:-1] <= u) & (ll_[1:] > u))
        if len(cruza):
            k = cruza[0]
            ic[lado] = float(dd[k] + (u - ll_[k]) * (dd[k + 1] - dd[k]) / (ll_[k + 1] - ll_[k]))
    T.attrs["ic"] = tuple(ic)
    return T


def costo_propio(obs: Observaciones, aj: Ajuste) -> dict:
    """
    ¿Cuánto de su propio impacto paga el agresor? costo_ef − spread/2 = c·f̂ + e, con costo_ef = lado·(VWAP
    − mid previo) del TBBO y f̂ = Â·b del ajuste. En un libro lineal c ≈ ½ (se barre el libro a mitad
    de camino); el optimizador usa ½ y esto lo audita.
    """
    f = aj.A * base_huella(obs.qe, obs.ptr, obs.K["sig5"].to_numpy(), obs.K["v5"].to_numpy(), aj.p["delta"], aj.x_ref)
    y = obs.K["costo_ef"].to_numpy() - obs.K["spread"].to_numpy() / 2.0
    ok = np.isfinite(f) & np.isfinite(y)
    if ok.sum() < 30:
        return {"c": np.nan, "se": np.nan, "n": int(ok.sum())}
    r = mco_agrupado(y[ok], f[ok][:, None], obs.K["sesion"].to_numpy()[ok])
    return {"c": float(r["coef"][0]), "se": float(r["se"][0]), "n": int(ok.sum())}


def A_por_gls(obs: Observaciones, aj: Ajuste, vero: Verosimilitud | None = None) -> tuple[float, float, int]:
    """Â con los demás parámetros FIJOS (GLS cerrado) y su EE agrupado por sesión: lo que estima el rolling."""
    vero = vero or Verosimilitud(obs, aj.esp, aj.x_ref, None)
    piezas, us = vero.piezas(aj.p)
    num = den = 0.0
    sc = np.zeros(obs.n)
    for g, (Siu, Siy, logdet, u, y) in zip(vero.grupos, piezas):
        num += float(np.einsum("ij,ij->", u, Siy))
        den += float(np.einsum("ij,ij->", u, Siu))
    A = num / den if den > 0 else np.nan
    for g, (Siu, Siy, logdet, u, y) in zip(vero.grupos, piezas):
        sc[g["idx"]] = np.einsum("ij,ij->i", u, Siy) - A * np.einsum("ij,ij->i", u, Siu)
    ses = obs.K["sesion"].to_numpy()
    _, inv = np.unique(ses, return_inverse=True)
    G = int(inv.max()) + 1 if len(inv) else 0
    s_g = np.bincount(inv, weights=sc) if G else np.zeros(0)
    se = math.sqrt(float((s_g ** 2).sum()) * (G / (G - 1) if G > 1 else 1.0)) / den if den > 0 else np.nan
    return A, se, G


# =============================================================================
# 6. ANÁLISIS DINÁMICO (ROLLING) — lo que cambia y lo que no se puede saber
# =============================================================================
@dataclass
class Rolling:
    tabla: pd.DataFrame               # por sesión: los parámetros con los que se OPERÓ esa sesión
    por_hora: pd.DataFrame            # A por hora del día (los demás fijos)
    estabilidad: dict                 # prueba de Nyblom sobre A, con p por permutación
    ajustes: dict = field(default_factory=dict)   # sesión → Ajuste expansivo (para el walk-forward)


def rolling(obs: Observaciones, esp: Especificacion, x_ref: float, flujo: Flujo | None, cfg: Config,
            total: Ajuste, verbose: bool = True) -> Rolling:
    """
    Para cada sesión s con al menos `ventana_sesiones` sesiones previas:
      · δ, π, τ, ω, κ, ϕ se re-estiman con TODAS las sesiones anteriores (ventana expansiva, causal):
        con ~10 sesiones ya cuesta identificarlos; con 3-5 serían ruido;
      · A —el impacto inmediato de un print de referencia, lo único bien identificado— se estima con
        las últimas `ventana_sesiones` sesiones por GLS (lo demás fijo), con EE agrupado por sesión.
    Así cada fila tiene los parámetros que se habrían conocido ANTES de operar esa sesión: son los
    que usa el walk-forward. Además, A por hora del día (con todas las sesiones) y una prueba de
    estabilidad de Nyblom sobre los scores de A por sesión, con p por permutación del orden.
    """
    ses = obs.K["sesion"].to_numpy()
    sesiones = np.unique(ses)
    W = cfg.ventana_sesiones
    filas, ajustes = [], {}
    previo = None
    for i in range(W, len(sesiones) + 1):
        s = int(sesiones[i]) if i < len(sesiones) else None
        prev = obs.sub(ses < s) if s is not None else obs
        if prev.n < cfg.min_eventos:
            continue
        vp = Verosimilitud(prev, esp, x_ref, flujo)
        # en frío (varios τ iniciales) la primera ventana y la última; en las demás, en caliente desde la
        # ventana ANTERIOR (nunca desde el ajuste de la muestra completa: sería ver el futuro)
        frio = ajustar(prev, esp, x_ref, flujo, errores=False, vero=vp) if (previo is None or s is None) else None
        caliente = ajustar(prev, esp, x_ref, flujo, inicio=previo, errores=False, vero=vp) if previo is not None else None
        aj = max([a for a in (frio, caliente) if a is not None], key=lambda a: a.ll)
        previo = dict(aj.p)
        win_m = (ses < s if s is not None else np.ones(len(ses), bool)) & (ses >= sesiones[max(0, i - W)])
        win = obs.sub(win_m)
        A, se, G = A_por_gls(win, aj, Verosimilitud(win, esp, x_ref, flujo))
        tq = t_cuantil(0.975, G - 1) if G > 1 else np.nan
        clave = s if s is not None else int((fecha_de_dia(int(sesiones[-1])) + pd.offsets.BDay(1)).value // DIA_NS)
        ajustes[clave] = (aj, A)
        filas.append({"sesion": clave, "siguiente": s is None, "n": win.n, "n_exp": prev.n, "A": A, "se_A": se,
                      "A_lo": A - tq * se, "A_hi": A + tq * se, "A_exp": aj.A, **{k: aj.p[k] for k in ("delta", "pi", "tau")},
                      "frio_caliente": bool(frio and caliente and abs(frio.ll - caliente.ll) > 1.0), "avisos": "; ".join(aj.avisos)})
        if verbose:
            print(f"   rolling {fecha_de_dia(clave):%Y-%m-%d}: A = {A:.4f} ± {se:.4f} · δ {aj.p['delta']:.2f} · "
                  f"π {aj.p['pi']:.2f} · τ {aj.p['tau']:.0f} s")
    T = pd.DataFrame(filas)
    # --- A por hora del día (CT), con los demás parámetros fijos en el ajuste total ---
    hora = a_indice(obs.K["t_ini"].to_numpy()).tz_convert(cfg.tz_mercado).hour
    ph = []
    for h in sorted(set(hora)):
        m = hora == h
        if m.sum() < 100:
            continue
        sub = obs.sub(m)
        A, se, G = A_por_gls(sub, total, Verosimilitud(sub, esp, x_ref, flujo))
        tq = t_cuantil(0.975, G - 1) if G > 1 else np.nan
        ph.append({"hora": int(h), "n": int(m.sum()), "A": A, "se": se, "lo": A - tq * se, "hi": A + tq * se})
    # --- estabilidad: Nyblom sobre los scores de A por sesión ---
    vero = Verosimilitud(obs, esp, x_ref, flujo)
    piezas, _ = vero.piezas(total.p)
    sc = np.zeros(obs.n)
    for g, (Siu, Siy, logdet, u, y) in zip(vero.grupos, piezas):
        sc[g["idx"]] = np.einsum("ij,ij->i", u, Siy) - total.A * np.einsum("ij,ij->i", u, Siu)
    _, inv = np.unique(ses, return_inverse=True)
    s_g = np.bincount(inv, weights=sc)
    est = {"L": np.nan, "p": np.nan, "G": len(s_g)}
    if len(s_g) >= 4 and (s_g ** 2).sum() > 0:
        def nyblom(x):
            C = np.cumsum(x)
            return float((C ** 2).sum() / len(x) / (x ** 2).sum())
        L = nyblom(s_g)
        rng = np.random.default_rng(31)
        perm = np.array([nyblom(rng.permutation(s_g)) for _ in range(2000)])
        est = {"L": L, "p": (1 + float((perm >= L).sum())) / 2001, "G": len(s_g)}
    return Rolling(T, pd.DataFrame(ph), est, ajustes)


# =============================================================================
# 7. ALGORITMOS DE EJECUCIÓN ÓPTIMA Y BACKTEST WALK-FORWARD
# =============================================================================
ALGORITMOS = ("TWAP", "VWAP", "POV", "POV*", "AC", "ÓPTIMO")


@dataclass
class Mercado:
    """Lo que se SABE antes de ejecutar una sesión: rejilla de slices y clips y los perfiles pronosticados."""
    dia: int
    t0: int                           # ns UTC del inicio del horizonte
    t1: int
    N: int                            # slices
    m: int                            # clips por slice
    t_clip: np.ndarray                # ns de cada clip
    slot_clip: np.ndarray
    sig_slot: np.ndarray              # σ pronosticada por slot (ticks por slot)
    vol_slot: np.ndarray              # volumen pronosticado por slot
    spread_slot: np.ndarray           # spread pronosticado por slot (ticks)
    w: np.ndarray                     # fracción del volumen pronosticado de cada slice (suma 1)
    w_min: np.ndarray                 # fracción por minuto del horizonte (suma 1)
    V_hor: float                      # volumen pronosticado en el horizonte
    clip_s: float
    slice_s: float
    slot_s: float
    tope: np.ndarray | None = None    # contratos máximos por slice: part_max del volumen pronosticado

    @property
    def C(self) -> int:
        return len(self.t_clip)


def perfil_spread(barras: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Spread medio por sesión y slot (ticks), del TBBO."""
    if not len(barras):
        return pd.DataFrame()
    b = barras.dropna(subset=["spread"])
    slot = (b["seg"].to_numpy() // (cfg.slot_min * 60)).astype(np.int64)
    return pd.DataFrame({"sesion": b["sesion"].to_numpy(), "slot": slot, "spread": b["spread"].to_numpy()}).groupby(
        ["sesion", "slot"])["spread"].mean().unstack().reindex(columns=range(MINUTOS_SESION // cfg.slot_min))


def mercado(dia: int, perf: Perfiles, spreads: pd.DataFrame, cfg: Config, clip_s: float = 20.0) -> Mercado:
    """
    Horizonte [inicio_ct, fin_ct) de la sesión `dia`, en slices de `slice_min` y clips de `clip_s` s, con el
    perfil de volumen (renormalizado a 1 sobre el horizonte), la σ y el spread PRONOSTICADOS con las
    sesiones anteriores.
    """
    vol, sig, _ = perf.de(dia)
    ap = apertura_utc(dia, cfg.tz_mercado)
    s0, s1 = segundo_de_hora(cfg.inicio_ct), segundo_de_hora(cfg.fin_ct)
    t0, t1 = ap + s0 * NS, ap + s1 * NS
    slice_s = cfg.slice_min * 60.0
    N = int(round((s1 - s0) / slice_s))
    m = max(1, int(round(slice_s / clip_s)))
    clip_s = slice_s / m
    t_clip = t0 + (np.arange(N * m) * clip_s * NS).astype(np.int64)
    slot_clip = ((s0 + np.arange(N * m) * clip_s) // (cfg.slot_min * 60)).astype(np.int64)
    if len(spreads):
        prev = [s for s in spreads.index if s < dia][-cfg.sesiones_perfil:]
        spr = np.nanmedian(spreads.loc[prev].to_numpy(dtype=float), axis=0) if prev else np.full(perf.n_slots, np.nan)
        spr = np.r_[spr, np.full(max(0, perf.n_slots - len(spr)), np.nan)][:perf.n_slots]
    else:
        spr = np.full(perf.n_slots, np.nan)
    spr = np.where(np.isfinite(spr), spr, np.nanmedian(spr) if np.isfinite(spr).any() else 1.0)
    vol = np.where(np.isfinite(vol), vol, 0.0)
    sig = np.where(np.isfinite(sig), sig, np.nanmedian(sig) if np.isfinite(sig).any() else 1.0)
    slots_h = np.arange(s0 // (cfg.slot_min * 60), s1 // (cfg.slot_min * 60))
    V_hor = float(vol[slots_h].sum())
    # fracciones por minuto y por slice (el volumen del slot se reparte parejo entre sus minutos)
    minutos = np.arange((s1 - s0) // 60)
    slot_min_ = ((s0 + minutos * 60) // (cfg.slot_min * 60)).astype(np.int64)
    w_min = vol[slot_min_] / cfg.slot_min
    w_min = w_min / w_min.sum() if w_min.sum() > 0 else np.full(len(minutos), 1 / len(minutos))
    w = w_min.reshape(N, -1).sum(axis=1) if len(minutos) == N * cfg.slice_min else np.full(N, 1 / N)
    r = cfg.part_max / (1.0 - cfg.part_max)               # ser part_max del TOTAL = r × el volumen de los demás
    return Mercado(dia, t0, t1, N, m, t_clip, slot_clip, sig, vol, spr, w, w_min, V_hor, clip_s, slice_s,
                   cfg.slot_min * 60.0, r * w * V_hor if V_hor > 0 else None)


@dataclass
class ModeloImpacto:
    """
    El modelo con el que se OPTIMIZA: propagador LINEAL tipo Obizhaeva–Wang, linealizado en el tamaño de
    clip q que de verdad se usa: κ = f̂(q)/q (ticks por contrato), con f̂ del MLE. Por qué lineal: con
    impacto de potencia (δ < 1), parte permanente y decaimiento exponencial, el costo deja de ser convexo,
    depende de en cuántos pedazos se parta cada orden y admite "manipulación" (comprar en pedazos y
    vender en bloque deja ganancia): Gatheral (2010), Huberman y Stanzl (2004). El modelo de potencia queda
    como DESCRIPTIVO; δ entra aquí sólo a través de f̂(q).
      · transitorio: κ_T(t) = (1 − π)·f̂ₜ(q)/q con la liquidez LOCAL del slot (σ₅, V₅ de esa hora), decae
        como exp(−Δt/τ);
      · permanente: κ_P = π·f̄(q)/q con la liquidez PROMEDIO del horizonte, constante en el día (una
        permanente que cambia con la hora también deja manipular);
      · costo propio de cada clip: c·κ·u² con c = ½ (libro lineal: se barre a mitad de camino).
    """
    A: float
    delta: float
    pi: float
    tau: float
    x_ref: float
    q: float
    kT: np.ndarray                    # por clip
    kP: float
    c_self: float = 0.5
    pi_original: float = np.nan
    kq: np.ndarray | None = None      # impacto TOTAL por contrato de cada clip, f̂(q)/q (calibra λ sin depender de π)


PI_MAX = 0.9          # π de EJECUCIÓN: con 100 % permanente todos los planes cuestan igual y el QP apilaría la orden


def modelo_impacto(p: dict, A: float, x_ref: float, mer: Mercado, cfg: Config, c_self: float = 0.5,
                   pi_max: float = PI_MAX) -> ModeloImpacto:
    """
    π se recorta a [0, 0.9]: π̂ ≥ 1 (no se vio decaimiento en los horizontes medidos) dejaría κ_T = 0, el
    costo sería igual para cualquier plan y el ÓPTIMO metería toda la orden en el slice de menor spread. Parte
    del impacto siempre decae (Bouchaud et al. 2004); el reporte avisa cuando se recorta.
    """
    escala = 300.0 / (cfg.slot_min * 60)
    sig5 = mer.sig_slot * math.sqrt(escala)
    v5 = np.maximum(mer.vol_slot * escala, 1e-9)
    q = float(cfg.pieza)
    pi = float(min(max(p["pi"], 0.0), pi_max))
    tau = float(max(p["tau"], 1.0))
    f = A * sig5 * ((q / v5) / x_ref) ** p["delta"]
    kT = (1 - pi) * f[mer.slot_clip] / q
    slots_h = np.unique(mer.slot_clip)
    f_bar = A * float(np.mean(sig5[slots_h])) * ((q / float(np.mean(v5[slots_h]))) / x_ref) ** p["delta"]
    return ModeloImpacto(A, p["delta"], pi, tau, x_ref, q, kT, pi * f_bar / q, c_self, p["pi"], f[mer.slot_clip] / q)


def matrices(mod: ModeloImpacto, mer: Mercado) -> dict:
    """
    Costo esperado y varianza de un plan por clip u (contratos), sin la trayectoria del mid:
      E[costo] = Σ uₖ·(spreadₖ/2 + c·κₖ·uₖ + Σ_{j<k} uⱼ·(κ_P + κ_T,ⱼ·e^{−(tₖ−tⱼ)/τ}))  = ½uᵀQu + bᵀu
      Var      = Σ wₖ·xₖ²,   xₖ = X − Σ_{j≤k} uⱼ  (lo que falta),  wₖ = σ² del intervalo siguiente.
    """
    t = (mer.t_clip - mer.t_clip[0]) / NS
    dt = t[:, None] - t[None, :]
    low = dt > 0
    KT = np.where(low, mod.kT[None, :] * np.exp(-np.where(low, dt, 0.0) / mod.tau), 0.0)
    K = KT + np.where(low, mod.kP, 0.0)
    kk = mod.kP + mod.kT
    Q = 2.0 * np.diag(mod.c_self * kk) + K + K.T
    b = mer.spread_slot[mer.slot_clip] / 2.0
    w = (mer.sig_slot[mer.slot_clip] ** 2) * mer.clip_s / mer.slot_s
    return {"Q": Q, "b": b, "w": w, "KT": KT, "K": K, "kk": kk}


def costo_modelo(u: np.ndarray, X: float, M: dict) -> tuple[float, float]:
    """(costo esperado en ticks·contratos, desviación estándar del costo por timing)."""
    E = 0.5 * float(u @ M["Q"] @ u) + float(M["b"] @ u)
    x = X - np.cumsum(u)
    return E, math.sqrt(max(float(M["w"] @ (x * x)), 0.0))


def qp_simplex(Qn: np.ndarray, bn: np.ndarray, X: float, tope: np.ndarray | None = None,
               iters: int = 1000) -> tuple[np.ndarray, bool]:
    """
    min ½nᵀQn + bᵀn  s.a.  Σn = X, 0 ≤ n ≤ tope, por conjunto activo con las condiciones KKT exactas (N chico).
    Si los topes no alcanzan para X se agrandan en proporción. Devuelve (n, convergió).
    """
    N = len(bn)
    Qn = Qn + 1e-9 * max(float(np.mean(np.abs(np.diag(Qn)))), 1e-300) * np.eye(N)   # Q singular: KKT compatible
    hi = np.full(N, np.inf) if tope is None else np.maximum(np.asarray(tope, float), 0.0)
    if hi.sum() < X:
        hi = hi * (X / max(hi.sum(), 1e-300)) * (1 + 1e-9) if hi.sum() > 0 else np.full(N, np.inf)
    estado = np.zeros(N, int)                              # 0 libre · −1 en 0 · +1 en el tope
    tol = 1e-9 * max(X, 1.0)
    n = np.full(N, X / N)
    for _ in range(iters):
        F, U = np.flatnonzero(estado == 0), np.flatnonzero(estado == 1)
        if not len(F):
            estado[U[0] if len(U) else 0] = 0
            continue
        resto = X - hi[U].sum()
        k = len(F)
        Mk = np.zeros((k + 1, k + 1))
        Mk[:k, :k] = Qn[np.ix_(F, F)]
        Mk[:k, k] = 1.0
        Mk[k, :k] = 1.0
        rhs = np.r_[-bn[F] - (Qn[np.ix_(F, U)] @ hi[U] if len(U) else 0.0), resto]
        sol = np.linalg.lstsq(Mk, rhs, rcond=None)[0]
        nF, mu = sol[:k], sol[k]
        bajo, alto = -nF, nF - hi[F]
        if max(bajo.max(), alto.max()) > tol:              # factibilidad primal: el que más se sale va a su cota
            if bajo.max() >= alto.max():
                estado[F[int(np.argmax(bajo))]] = -1
            else:
                estado[F[int(np.argmax(alto))]] = 1
            continue
        n = np.zeros(N)
        n[F] = np.clip(nF, 0.0, hi[F])
        n[U] = hi[U]
        g = Qn @ n + bn + mu                               # KKT: g ≥ 0 en la cota de abajo, g ≤ 0 en el tope
        L = np.flatnonzero(estado == -1)
        peor_l = g[L].min() if len(L) else 0.0
        peor_u = g[U].max() if len(U) else 0.0
        umbral = 1e-9 * (1 + abs(mu))
        if peor_l < -umbral and -peor_l >= peor_u:
            estado[L[int(np.argmin(g[L]))]] = 0
            continue
        if peor_u > umbral:
            estado[U[int(np.argmax(g[U]))]] = 0
            continue
        return n, True
    return n, False


def matriz_reparto(mer: Mercado) -> np.ndarray:
    """B (clips × slices): cada slice se reparte parejo entre sus m clips."""
    B = np.zeros((mer.C, mer.N))
    B[np.arange(mer.C), np.arange(mer.C) // mer.m] = 1.0 / mer.m
    return B


def optimo_ow(X: float, lam: float, M: dict, mer: Mercado) -> tuple[np.ndarray, bool]:
    """
    ÓPTIMO con resiliencia (Obizhaeva–Wang, linealizado): min E[costo] + λ·Var sobre los tamaños por slice,
    con la dinámica exacta clip a clip (transitorio que decae, permanente, costo propio y spread).
    Es convexo cuando Q es definida positiva (G convexa y c ≥ ½; Alfonsi, Schied y Slynko 2012). Cada slice
    tiene un tope: part_max del volumen PRONOSTICADO (lo que impone cualquier mesa de ejecución).
    """
    B = matriz_reparto(mer)
    L = np.tril(np.ones((mer.C, mer.C)))
    W = M["w"]
    # Var = Σ w (X − L u)² = uᵀLᵀWLu − 2X·1ᵀWLu + X²Σw
    LB = L @ B
    Qn = B.T @ M["Q"] @ B + 2 * lam * (LB.T * W) @ LB
    bn = B.T @ M["b"] - 2 * lam * X * (W @ LB)
    n, ok = qp_simplex(Qn, bn, X, mer.tope)
    return B @ n, ok


def eta_slices(mod: ModeloImpacto, mer: Mercado, M: dict, total: bool = False) -> np.ndarray:
    """η de cada slice (ticks por contrato², costo = η·n²): el bloque TRANSITORIO del propio slice con flujo parejo."""
    eta = np.zeros(mer.N)
    for k in range(mer.N):
        a, b = k * mer.m, (k + 1) * mer.m
        if total and mod.kq is not None:                    # para λ: el impacto completo, que no depende de π
            t = (mer.t_clip[a:b] - mer.t_clip[a]) / NS
            dt = t[:, None] - t[None, :]
            blk = np.diag(mod.c_self * mod.kq[a:b]) + np.where(dt > 0, mod.kq[a:b][None, :] * np.exp(-np.maximum(dt, 0) / mod.tau), 0.0)
        else:
            blk = np.diag(mod.c_self * mod.kT[a:b]) + M["KT"][a:b, a:b]   # sin el permanente: no distingue planes
        eta[k] = float(blk.sum()) / mer.m ** 2
    return eta


def almgren_chriss(X: float, lam: float, eta: np.ndarray, sig2: np.ndarray) -> np.ndarray:
    """
    Almgren–Chriss (2000) con η y σ por franja (convención de flujo: dentro de cada slice se opera parejo):
      min Σₖ ηₖ·nₖ² + λ·Σₖ σₖ²·(x²ₖ₋₁ + xₖ₋₁xₖ + x²ₖ)/3,   x₀ = X, x_N = 0, nₖ = xₖ₋₁ − xₖ.
    Las condiciones de primer orden son un sistema TRIDIAGONAL en x₁ … x_{N−1}:
      (−2ηⱼ + λσⱼ²/3)·xⱼ₋₁ + (2ηⱼ + 2ηⱼ₊₁ + 2λ(σⱼ² + σⱼ₊₁²)/3)·xⱼ + (−2ηⱼ₊₁ + λσⱼ₊₁²/3)·xⱼ₊₁ = 0.
    Con η y σ constantes la solución es xⱼ = X·sinh(κ(N − j))/sinh(κN) con
    cosh κ = (2η + 2λσ²/3)/(2η − λσ²/3); con λ = 0, ηₖ·nₖ es constante (nₖ ∝ 1/ηₖ).

    [v1] Tu script menciona Almgren–Chriss en la guía final ("ver indicador anterior") pero no lo implementa.
    """
    N = len(eta)
    if N == 1:
        return np.array([float(X)])
    e = np.asarray(eta, float)
    s2 = np.asarray(sig2, float) * lam / 3.0
    escala = max(float(np.max(e)), float(np.max(s2)), 0.0)
    if escala <= 0:                                        # sin transitorio ni aversión (π = 1, λ = 0): da igual, parejo
        return np.full(N, X / N)
    e = np.maximum(e, 1e-9 * escala)                       # π = 1: sin η el sistema es singular
    T = np.zeros((N - 1, N - 1))
    rhs = np.zeros(N - 1)
    for j in range(1, N):                                  # ecuación de x_j (fila j−1)
        r = j - 1
        T[r, r] = 2 * e[j - 1] + 2 * e[j] + 2 * (s2[j - 1] + s2[j])
        a = -2 * e[j - 1] + s2[j - 1]                      # coeficiente de x_{j−1}
        c = -2 * e[j] + s2[j]                              # coeficiente de x_{j+1}
        if j - 1 == 0:
            rhs[r] -= a * X
        else:
            T[r, r - 1] = a
        if j + 1 < N:
            T[r, r + 1] = c
    x = np.linalg.solve(T, rhs)
    xs = np.r_[X, x, 0.0]
    n = xs[:-1] - xs[1:]
    if (n < -1e-9 * X).any():                              # no debería pasar con parámetros positivos
        n = np.maximum(n, 0.0)
        n *= X / n.sum()
    return n


def lambda_de_urgencia(urgencia: float, eta: np.ndarray, sig2: np.ndarray) -> float:
    """
    λ (por tick·contrato) que da una urgencia κ·T dada con los η y σ medianos del horizonte, en la
    convención de flujo: cosh(κT/N) = (2η + 2λσ²/3)/(2η − λσ²/3). Se calcula UNA vez con la ventana de
    calibración y queda fijo todo el walk-forward (κT por sesión daría una aversión distinta cada día).
    """
    N = len(eta)
    if urgencia <= 0:
        return 0.0
    ch = math.cosh(urgencia / N)
    e, s2 = float(np.median(eta)), float(np.median(sig2))
    return float(2 * e * (ch - 1) / (s2 * (2 + ch) / 3)) if s2 > 0 else 0.0


@dataclass
class Realizado:
    """Lo que de verdad pasó en la sesión, en la rejilla de clips y de minutos del horizonte."""
    mid: np.ndarray                   # mid del libro en cada clip (ticks)
    spread: np.ndarray                # spread en cada clip (ticks)
    vol_min: np.ndarray               # volumen del mercado por minuto del horizonte
    vwap_min: np.ndarray              # VWAP del mercado por minuto (ticks)
    mid_fin: float                    # mid al final del horizonte
    sig2_clip: np.ndarray             # varianza realizada por intervalo de clip (para el z del timing)


def realizado(mer: Mercado, E: pd.DataFrame, barras: pd.DataFrame) -> Realizado | None:
    """Mid (libro previo a la primera operación a partir de cada clip), spread y volumen por minuto."""
    t_e = E["t"].to_numpy()
    mid_e = E["mid0"].to_numpy()
    if len(t_e) == 0:
        return None
    j = np.searchsorted(t_e, mer.t_clip, side="left")
    if j.max() >= len(t_e):
        return None
    ses_e = E["sesion"].to_numpy()
    if (ses_e[j] != mer.dia).any():
        return None                                        # cierre anticipado o hueco: el mid sería de otra sesión
    mid = pd.Series(mid_e[np.minimum(j, len(t_e) - 1)]).ffill().bfill().to_numpy()
    m_ini, m_fin = mer.t0 // NS_MIN, mer.t1 // NS_MIN
    b = barras.reindex(np.arange(m_ini, m_fin))
    if b["vol"].isna().mean() > 0.5:                     # minutos sin operaciones son normales en contratos poco líquidos
        return None
    vol_min = b["vol"].fillna(0.0).to_numpy()
    vwap_min = b["vwap"].to_numpy(dtype=float)
    spr_min = b["spread"].ffill().bfill().to_numpy(dtype=float)
    k_min = ((mer.t_clip // NS_MIN) - m_ini).astype(int)
    spread = np.where(np.isfinite(spr_min[k_min]), spr_min[k_min], 1.0)
    jf = min(int(np.searchsorted(t_e, mer.t1, side="left")), len(t_e) - 1)
    if ses_e[jf] != mer.dia:                               # --fin en el cierre: la última operación de la sesión
        jf -= 1
    d = np.diff(np.r_[mid, mid_e[jf]])
    # varianza realizada por clip: la de su minuto, repartida
    d2 = pd.Series(d * d).groupby(k_min).transform("mean").to_numpy()
    return Realizado(mid, spread, vol_min, np.where(np.isfinite(vwap_min), vwap_min, np.nan), float(mid_e[jf]), d2)


def plan_estatico(nombre_: str, X: float, mer: Mercado, mod: ModeloImpacto, M: dict, lam: float) -> np.ndarray:
    """Plan por clip (contratos) de los algoritmos que se deciden ANTES de abrir."""
    B = matriz_reparto(mer)
    if nombre_ == "TWAP":
        return B @ np.full(mer.N, X / mer.N)
    if nombre_ == "VWAP":
        return B @ (X * mer.w)
    if nombre_ == "AC":
        sig2 = M["w"].reshape(mer.N, mer.m).sum(axis=1)
        return B @ almgren_chriss(X, lam, eta_slices(mod, mer, M), sig2)
    if nombre_ == "ÓPTIMO":
        return optimo_ow(X, lam, M, mer)[0]
    if nombre_ == "POV*":                                  # su plan ESPERADO (con el volumen pronosticado)
        return B @ (X * mer.w)
    raise ValueError(nombre_)


def plan_pov(X: float, rho: float, mer: Mercado, vol_min: np.ndarray) -> tuple[np.ndarray, float]:
    """
    POV que sigue el volumen REAL con 1 minuto de rezago: en el minuto t opera ρ/(1−ρ)·V_{t−1}·(ŵₜ/ŵₜ₋₁)
    (el volumen del minuto anterior, corregido por el perfil esperado, para no quedarse corto al abrir).
    ρ/(1−ρ) y no ρ: el volumen histórico no trae el nuestro, y llevar el 10 % del TOTAL exige 10/90 del
    resto. El primer minuto usa el volumen pronosticado. Si no termina, el remanente se fuerza en el
    último clip y se reporta. Devuelve (plan por clip, contratos forzados al final).

    [v1] Tu pov_schedule usa el volumen del slice que todavía no ocurre (decide a las 8:30 con el volumen
    de 8:30-8:35) y al 10 % termina 5000 contratos del NQ en unos minutos: no se compara con algoritmos de
    6.5 horas. Aquí además está POV*, con la ρ que termina al final del horizonte en promedio.
    """
    r = rho / (1 - rho)
    n_min = len(mer.w_min)
    clips_min = max(1, int(round(60.0 / mer.clip_s)))
    u = np.zeros(mer.C)
    hecho = 0.0
    for t in range(n_min):
        if t == 0:
            obj = r * mer.V_hor * mer.w_min[0]
        else:
            ajuste = mer.w_min[t] / mer.w_min[t - 1] if mer.w_min[t - 1] > 0 else 1.0
            obj = r * vol_min[t - 1] * ajuste
        if X - hecho <= 1e-9:
            break
        obj = min(obj, X - hecho)
        if obj <= 0:                                       # un minuto sin volumen: no opera, sigue
            continue
        a = t * clips_min
        u[a:a + clips_min] = obj / clips_min
        hecho += obj
    forzado = max(X - hecho, 0.0)
    u[-1] += forzado
    return u, forzado


def ejecutar(u: np.ndarray, lado: int, mer: Mercado, mod: ModeloImpacto, M: dict, real: Realizado,
             comision: float = 0.0) -> dict:
    """
    Réplica clip a clip sobre lo que pasó: precio de cada clip = mid histórico + lado·(spread/2 + costo
    propio + permanente arrastrado + transitorio arrastrado). El histórico no contiene nuestra orden, así
    que el impacto propio se SUPERPONE con el modelo calibrado: la parte de timing es real, la de costo es
    del modelo (y se rotula así). Atribución exacta (suma el IS al centavo):
      spread + propio + transitorio + permanente + timing + comisiones.

    [v1] Tu simulate_execution pone TODO el slice al close de un minuto, inventa un slippage de 5-10 bps
    discontinuo en vol_ratio = 0.2, no cobra el spread ni el impacto propio, y su "VWAP de mercado" es
    distinto para cada algoritmo (cada uno lo pondera con sus propios minutos).
    """
    X = float(u.sum())
    s = float(lado)
    m0 = float(real.mid[0])
    U = np.cumsum(u) - u                                    # lo ejecutado ANTES de cada clip
    perm = mod.kP * (U + mod.c_self * u)                    # Σ u·perm = ½κ_P·X²: igual para cualquier plan
    trans = M["KT"] @ u
    propio = mod.c_self * mod.kT * u                        # sólo el transitorio del propio clip
    spread = real.spread / 2.0
    precio = real.mid + s * (spread + propio + perm + trans)
    partes = {"spread": float(u @ spread), "propio": float(u @ propio), "transitorio": float(u @ trans),
              "permanente": float(u @ perm), "timing": float(s * (u @ (real.mid - m0))),
              "comisiones": comision * X}
    is_ticks = float(s * (u @ (precio - m0))) + partes["comisiones"]
    # impacto nuestro vivo en cada minuto (para el VWAP contrafactual)
    t_min = mer.t0 + (np.arange(len(real.vol_min)) * 60 + 30) * NS
    t_rel = (t_min[:, None] - mer.t_clip[None, :]) / NS
    vivo = np.where(t_rel > 0, mod.kP + mod.kT[None, :] * np.exp(-np.maximum(t_rel, 0) / mod.tau), 0.0) @ u
    v = real.vol_min
    vw = np.where(np.isfinite(real.vwap_min), real.vwap_min, real.mid[np.minimum(np.arange(len(v)) * int(round(60 / mer.clip_s)), mer.C - 1)])
    vwap_hist = float((v * vw).sum() / v.sum()) if v.sum() > 0 else np.nan
    vwap_cf = float(((v * (vw + s * vivo)).sum() + (u * precio).sum()) / (v.sum() + X)) if v.sum() > 0 else np.nan
    precio_medio = float((u @ precio) / X)
    clips_min = max(1, int(round(60.0 / mer.clip_s)))
    nuestro_min = np.add.reduceat(u, np.arange(0, mer.C, clips_min))[:len(v)]
    part = nuestro_min / np.maximum(v[:len(nuestro_min)] + nuestro_min, 1e-9)
    x = X - np.cumsum(u)
    var_real = float((real.sig2_clip * x * x).sum())
    return {"is_ticks": is_ticks, "is_por_contrato": is_ticks / X, "is_bps": is_ticks / X / m0 * 1e4,
            "precio_medio": precio_medio, "vs_vwap": s * (precio_medio - vwap_hist), "vs_vwap_cf": s * (precio_medio - vwap_cf),
            "part_max": float(part.max()) if len(part) else np.nan, "part_p95": float(np.quantile(part, 0.95)) if len(part) else np.nan,
            "z_timing": partes["timing"] / math.sqrt(var_real) if var_real > 0 else np.nan,
            "costo_modelo": is_ticks - partes["timing"], **partes, "precio": precio}


@dataclass
class Backtest:
    filas: pd.DataFrame               # sesión × algoritmo × lado: IS, atribución, participación…
    planes: dict                      # algoritmo → plan por clip de la sesión objetivo
    mercado: Mercado | None
    modelo: ModeloImpacto | None
    lam: float
    frontera: pd.DataFrame
    parametrica: pd.DataFrame         # diferencias de costo esperado contra TWAP con θ ~ N(θ̂, V)
    arrepentimiento: pd.DataFrame     # costo bajo modelos alternativos
    comparacion: pd.DataFrame         # pareada contra TWAP entre sesiones
    pico: dict
    avisos: list
    real: Realizado | None = None     # lo que pasó en la sesión objetivo (la última de prueba)
    detalle: dict = field(default_factory=dict)   # algoritmo → réplica de la sesión objetivo del lado cfg.lado
    forzado: dict = field(default_factory=dict)


def _planes(X, mer, mod, M, lam, real, cfg):
    planes, forzado = {}, {}
    for nm in ALGORITMOS:
        if nm == "POV":
            planes[nm], forzado[nm] = plan_pov(X, cfg.pov, mer, real.vol_min)
        elif nm == "POV*":
            rho = X / (X + mer.V_hor) if mer.V_hor > 0 else cfg.pov
            planes[nm], forzado[nm] = plan_pov(X, rho, mer, real.vol_min)
        else:
            planes[nm], forzado[nm] = plan_estatico(nm, X, mer, mod, M, lam), 0.0
    return planes, forzado


def backtest(sesiones: list, ajustes: dict, x_ref: float, perf: Perfiles, spreads: pd.DataFrame,
             E: pd.DataFrame, barras: pd.DataFrame, cfg: Config, total: Ajuste | None = None,
             n_param: int = 100, verbose: bool = True) -> Backtest:
    """
    Walk-forward: cada sesión de prueba se ejecuta con los parámetros, perfiles y spreads que se conocían
    ANTES de ella (ajuste expansivo + A rolling), la misma λ fija para todas, y la orden de COMPRA y la de
    VENTA. Promediar las dos cancela exactamente la trayectoria del mercado: queda el costo MODELADO con
    spreads y volúmenes reales. Un solo lado conserva el timing real: ése es el riesgo.
    """
    X = float(cfg.orden)
    filas, avisos = [], []
    lam = None
    planes_obj, mer_obj, mod_obj, M_obj, real_obj, det_obj, forz_obj = {}, None, None, None, None, {}, {}
    for s in sesiones:
        if s not in ajustes:
            continue
        aj, A = ajustes[s]
        mer = mercado(int(s), perf, spreads, cfg)
        real = realizado(mer, E, barras)
        if real is None or mer.V_hor <= 0:
            continue
        mod = modelo_impacto(aj.p, A, x_ref, mer, cfg)
        M = matrices(mod, mer)
        if lam is None:
            sig2 = M["w"].reshape(mer.N, mer.m).sum(axis=1)
            lam = lambda_de_urgencia(cfg.urgencia, eta_slices(mod, mer, M, total=True), sig2)
        planes, forzado = _planes(X, mer, mod, M, lam, real, cfg)
        detalle = {}
        for nm, u in planes.items():
            for lado in (1, -1):
                r = ejecutar(u, lado, mer, mod, M, real)
                if lado == cfg.lado:
                    detalle[nm] = dict(r)
                r.pop("precio")
                E_m, sd_m = costo_modelo(u, X, M)
                filas.append({"sesion": int(s), "algoritmo": nm, "lado": lado, "forzado": forzado[nm],
                              "E_modelo": E_m, "sd_modelo": sd_m, **r})
        planes_obj, mer_obj, mod_obj, M_obj, real_obj, det_obj, forz_obj = planes, mer, mod, M, real, detalle, forzado
        if verbose:
            f = pd.DataFrame([x for x in filas if x["sesion"] == int(s)])
            res = f.groupby("algoritmo")["costo_modelo"].mean() / X
            print(f"   {fecha_de_dia(int(s)):%Y-%m-%d}: costo modelado por contrato " +
                  " · ".join(f"{k} {res[k]:.2f}t" for k in ALGORITMOS if k in res))
    F = pd.DataFrame(filas)
    if not len(F):
        return Backtest(F, {}, None, None, 0.0, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), {}, ["sin sesiones de prueba"])
    fr = frontera(X, mer_obj, mod_obj, M_obj, planes_obj, cfg)
    par = parametrica(X, mer_obj, cfg, lam, total, x_ref, n_param) if (total is not None and total.V is not None and n_param > 0) else pd.DataFrame()
    arr = arrepentimiento(X, mer_obj, mod_obj, lam, planes_obj, cfg)
    comp = comparar(F, X)
    pico = pico_impacto(X, mer_obj, mod_obj, M_obj, planes_obj["ÓPTIMO"])
    if not (1 / 3 <= pico["razon"] <= 3):
        avisos.append(f"el impacto pico de la orden en el modelo es {pico['razon']:.2f}× el de la ley de raíz cuadrada")
    if mer_obj is not None and mer_obj.dia != dia_objetivo(cfg):
        avisos.append(f"la sesión objetivo {cfg.sesion_objetivo} no se pudo replicar (datos incompletos o fuera del "
                      f"archivo): se muestra la {fecha_de_dia(mer_obj.dia):%Y-%m-%d}")
    if mod_obj is not None and not (-0.005 <= mod_obj.pi_original <= PI_MAX + 0.005):
        avisos.append(f"π̂ = {mod_obj.pi_original:.2f} fuera de [0, {PI_MAX:g}]: para ejecutar se recortó a {mod_obj.pi:.2f}")
    return Backtest(F, planes_obj, mer_obj, mod_obj, lam, fr, par, arr, comp, pico, avisos, real_obj, det_obj, forz_obj)


def frontera(X: float, mer: Mercado, mod: ModeloImpacto, M: dict, planes: dict, cfg: Config) -> pd.DataFrame:
    """Frontera eficiente (costo esperado contra desviación) del ÓPTIMO para varias urgencias, y cada algoritmo."""
    sig2 = M["w"].reshape(mer.N, mer.m).sum(axis=1)
    eta = eta_slices(mod, mer, M, total=True)
    filas = []
    for kT in (0.0, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0):
        lam = lambda_de_urgencia(kT, eta, sig2)
        u = optimo_ow(X, lam, M, mer)[0]
        E_, sd = costo_modelo(u, X, M)
        filas.append({"tipo": "frontera", "nombre": f"κT={kT:g}", "urgencia": kT, "lam": lam, "E": E_ / X, "sd": sd / X})
    for nm, u in planes.items():
        E_, sd = costo_modelo(u, X, M)
        n = u.reshape(mer.N, mer.m).sum(axis=1) if len(u) == mer.C else None
        cabe = bool(mer.tope is None or (n is not None and np.all(n <= mer.tope * (1 + 1e-6) + 1e-6)))
        filas.append({"tipo": "algoritmo", "nombre": nm, "urgencia": np.nan, "lam": np.nan, "E": E_ / X, "sd": sd / X,
                      "respeta_tope": cabe})
    return pd.DataFrame(filas)


def _modelo_de(x: np.ndarray, nombres: list, base: dict, x_ref: float, mer: Mercado, cfg: Config) -> ModeloImpacto:
    p = dict(base)
    A = None
    for nm, v in zip(nombres, x):
        if nm == "A":
            A = float(v)
        else:
            lo, hi = _cotas_opt(nm)
            p[nm] = float(_de_opt(nm, min(max(v, lo), hi)))
    return modelo_impacto(p, A, x_ref, mer, cfg)


def parametrica(X: float, mer: Mercado, cfg: Config, lam: float, total: Ajuste, x_ref: float, B: int) -> pd.DataFrame:
    """
    Incertidumbre de los PARÁMETROS (no del mercado): θ⁽ᵇ⁾ ~ N(θ̂, V robusta) en la escala del optimizador;
    para cada extracción se recalculan AC y ÓPTIMO y se evalúa el costo esperado de todos con ESE θ⁽ᵇ⁾.
    La diferencia contra TWAP, pareada, con su intervalo 2.5–97.5 %.
    """
    rng = np.random.default_rng(17)
    nombres = list(total.nombres_v)
    x0 = np.r_[total.A, [_a_opt(nm, total.p[nm]) for nm in nombres[1:]]]
    try:
        Lc = np.linalg.cholesky(total.V + 1e-12 * np.eye(len(x0)))
    except np.linalg.LinAlgError:
        Lc = np.diag(np.sqrt(np.maximum(np.diag(total.V), 0)))
    filas = []
    for b in range(B):
        x = x0 + Lc @ rng.standard_normal(len(x0))
        mod = _modelo_de(x, nombres, total.p, x_ref, mer, cfg)
        if mod.A <= 0:
            continue
        M = matrices(mod, mer)
        planes = {nm: plan_estatico(nm, X, mer, mod, M, lam) for nm in ("TWAP", "VWAP", "AC", "ÓPTIMO")}
        costos = {nm: costo_modelo(u, X, M)[0] / X for nm, u in planes.items()}
        filas.append({"b": b, **costos})
    T = pd.DataFrame(filas)
    return T


def arrepentimiento(X: float, mer: Mercado, mod: ModeloImpacto, lam: float, planes: dict, cfg: Config) -> pd.DataFrame:
    """
    Robustez al modelo: los planes se calcularon con el modelo estimado; ¿cuánto pierden si la verdad es
    otra (τ a la mitad o al doble, π en 0 o en 1, A ±50 %)? Arrepentimiento = (E + λ·Var) del plan − la
    del ÓPTIMO de ESE modelo, por contrato: el mismo objetivo que minimiza el ÓPTIMO.
    """
    alternativas = {"estimado": {}, "τ × 0.5": {"tau": mod.tau * 0.5}, "τ × 2": {"tau": mod.tau * 2},
                    "π = 0 (todo transitorio)": {"pi": 0.0}, "π = 1 (todo permanente)": {"pi": 1.0},
                    "A × 1.5": {"A": mod.A * 1.5}, "A × 0.67": {"A": mod.A / 1.5}}
    filas = []
    for nm_alt, cambios in alternativas.items():
        p = {"delta": mod.delta, "pi": cambios.get("pi", mod.pi), "tau": cambios.get("tau", mod.tau)}
        m2 = modelo_impacto(p, cambios.get("A", mod.A), mod.x_ref, mer, cfg, pi_max=1.0)
        M2 = matrices(m2, mer)
        e_o, sd_o = costo_modelo(optimo_ow(X, lam, M2, mer)[0], X, M2)
        opt = e_o + lam * sd_o ** 2
        for nm, u in planes.items():
            e, sd = costo_modelo(u, X, M2)
            filas.append({"modelo": nm_alt, "algoritmo": nm, "costo": e / X, "arrepentimiento": (e + lam * sd ** 2 - opt) / X})
    return pd.DataFrame(filas)


def pico_impacto(X: float, mer: Mercado, mod: ModeloImpacto, M: dict, u: np.ndarray) -> dict:
    """
    Cordura del tamaño: el impacto vivo máximo de NUESTRA orden en el modelo contra la ley de raíz cuadrada
    de las metaórdenes, Y·σ_horizonte·√(X / V_horizonte) con Y ≈ 0.7 (Tóth et al. 2011).
    """
    vivo = mod.kP * np.cumsum(u) + M["KT"] @ u                # impacto vivo justo después de cada clip
    pico = float(np.max(vivo)) if len(vivo) else np.nan
    sig_h = math.sqrt(float(M["w"].sum()))
    raiz = 0.7 * sig_h * math.sqrt(X / mer.V_hor) if mer.V_hor > 0 else np.nan
    return {"pico": pico, "raiz": raiz, "razon": pico / raiz if raiz and raiz > 0 else np.nan}


def wilcoxon_p(d: np.ndarray) -> float:
    """p de dos colas de Wilcoxon de rangos con signo (aproximación normal con corrección de continuidad)."""
    d = d[np.isfinite(d) & (d != 0)]
    n = len(d)
    if n < 5:
        return np.nan
    r = pd.Series(np.abs(d)).rank().to_numpy()
    W = float(r[d > 0].sum())
    mu, sd = n * (n + 1) / 4, math.sqrt(n * (n + 1) * (2 * n + 1) / 24)
    z = (abs(W - mu) - 0.5) / sd
    return 2 * (1 - NormalDist().cdf(z))


def comparar(F: pd.DataFrame, X: float) -> pd.DataFrame:
    """
    Pareada contra TWAP entre sesiones. COSTO = promedio de compra y venta (sin la trayectoria: costo
    modelado); RIESGO = desviación del IS de un solo lado (timing real). t con n − 1 gl, Wilcoxon y Holm.
    El veredicto usa p de Holm < 0.05 y un umbral de relevancia; el MDE (80 % de potencia) es informativo:
    la diferencia que se habría podido detectar con esas sesiones.

    [v1] Tu script elige el "mejor" con el menor |slippage| de UN solo día: eso lo decide la trayectoria
    del precio (aquí, el timing), no el algoritmo, y el valor absoluto premia igual un slippage negativo.
    """
    c = F.groupby(["sesion", "algoritmo"])["is_por_contrato"].mean().unstack()
    compra = F[F["lado"] == 1].pivot(index="sesion", columns="algoritmo", values="is_por_contrato")
    filas = []
    for nm in c.columns:
        d = (c[nm] - c["TWAP"]).dropna().to_numpy()
        n = len(d)
        media = float(d.mean()) if n else np.nan
        sd = float(d.std(ddof=1)) if n > 1 else np.nan
        t = media / (sd / math.sqrt(n)) if n > 1 and sd > 0 else np.nan
        mde = (t_cuantil(0.975, n - 1) + t_cuantil(0.80, n - 1)) * sd / math.sqrt(n) if n > 1 and sd > 0 else np.nan
        filas.append({"algoritmo": nm, "sesiones": n, "costo": float(c[nm].mean()), "dif_vs_twap": media,
                      "t": t, "p": p_t(t, n - 1) if np.isfinite(t) else np.nan, "p_wilcoxon": wilcoxon_p(d),
                      "mde": mde, "riesgo": float(compra[nm].std(ddof=1)) if nm in compra and len(compra) > 1 else np.nan})
    T = pd.DataFrame(filas)
    # Holm sobre las comparaciones contra TWAP
    m = T[T["algoritmo"] != "TWAP"].sort_values("p")
    k = len(m)
    holm, previo = {}, 0.0
    for i, (_, f) in enumerate(m.iterrows()):
        val = min(1.0, max(previo, (k - i) * f["p"])) if np.isfinite(f["p"]) else np.nan
        holm[f["algoritmo"]] = val
        previo = val if np.isfinite(val) else previo
    T["p_holm"] = T["algoritmo"].map(holm)
    # significativo y además relevante: al menos 0.02 ticks por contrato o 0.5 % del costo de TWAP
    umbral = max(0.02, 0.005 * float(T.loc[T["algoritmo"] == "TWAP", "costo"].iloc[0])) if (T["algoritmo"] == "TWAP").any() else 0.02

    def veredicto(a, ph, dd):
        if a == "TWAP":
            return "—"
        if not (np.isfinite(ph) and ph < 0.05):
            return "indistinguible"
        txt = "más barato" if dd < 0 else "más caro"
        return txt if abs(dd) >= umbral else f"{txt}, irrelevante"
    T["veredicto"] = [veredicto(a, ph, dd) for a, ph, dd in zip(T["algoritmo"], T["p_holm"], T["dif_vs_twap"])]
    return T


# =============================================================================
# 8. SIMULADOR — un tape con el modelo de impacto CONOCIDO
# =============================================================================
DTYPE_OHLCV = np.dtype([("ts_event", "<u8"), ("instrument_id", "<u4"), ("open", "<i8"), ("high", "<i8"),
                        ("low", "<i8"), ("close", "<i8"), ("volume", "<u8")])


def perfil_actividad(minuto: np.ndarray) -> np.ndarray:
    """Actividad relativa por minuto de sesión (0 = 17:00 CT): Asia quieta, Europa, y una U en el horario regular."""
    m = np.asarray(minuto, float)
    p = np.where(m < 540, 0.35, 0.9)                                     # 17:00-02:00 CT: Asia
    rth = (m >= 930) & (m < 1320)                                        # 08:30-15:00 CT
    u = 2.2 + 4.0 * np.exp(-(m - 930) / 25.0) + 2.5 * np.exp(-(1320 - m) / 30.0)
    p = np.where(rth, u, p)
    return np.where(m >= 1320, 0.6, p)


def _media_pareto(alfa: float, tope: int, rng) -> float:
    return float(np.minimum(np.floor(rng.random(400_000) ** (-1 / alfa)), tope).mean())


def simular(cfg: Config, sesiones: int | None = None, semilla: int | None = None,
            impacto: bool = True) -> tuple[np.ndarray, np.ndarray, dict]:
    """
    Registros TBBO (cada operación con el mejor bid/ask justo antes) y barras OHLCV-1m de un mercado
    cuyo impacto sigue EXACTAMENTE el modelo que estima el módulo:
      · operaciones de Poisson con actividad en U; tamaños de Pareto (α = 1.5, tope 200); signos
        independientes (o persistentes con `sim_memoria`);
      · precio verdadero = difusión con σ intradía + impacto PERMANENTE + TRANSITORIO. Cada operación
        de q contratos en el minuto m deja f = Y·σ₅(m)·(q / V₅(m))^δ ticks: π·f para siempre y
        (1 − π)·f que decae como exp(−t/τ). σ₅ y V₅ son la σ y el volumen esperados de 5 min a esa
        hora: el impacto depende de la liquidez del momento;
      · el libro se cuantiza al tick (bid = piso del precio, ask = bid + 1, a veces + 2): ése es el
        ruido de microestructura ω (≈ 0.29 ticks);
      · un factor de actividad por sesión (lognormal), un roll con salto de nivel a la mitad.
    Cada operación sale partida en 1-3 registros (órdenes en reposo distintas).
    """
    rng = np.random.default_rng(cfg.sim_semilla if semilla is None else semilla)
    S = int(sesiones or cfg.sim_sesiones)
    tk = tick(cfg.symbol)
    tk_ns = tick_ns(cfg.symbol)
    p_ref = CATALOGO.get(raiz(cfg.symbol), ("", 0.25, 20000.0, 20.0))[2]
    fechas = pd.bdate_range(end=fecha_de_dia(dia_objetivo(cfg)), periods=S)
    minutos = np.arange(MINUTOS_SESION)
    perfil = perfil_actividad(minutos)
    alfa, tope = 1.5, 200
    eq = _media_pareto(alfa, tope, np.random.default_rng(99))
    tasa = cfg.sim_operaciones / perfil.sum()                            # operaciones por minuto con perfil 1
    sig_s = 0.6 * np.sqrt(perfil)                                         # ticks / √s
    sig5 = sig_s * math.sqrt(300.0)
    vol_min = tasa * perfil * eq                                          # contratos esperados por minuto
    v5 = np.convolve(np.r_[vol_min[:2][::-1], vol_min, vol_min[-2:][::-1]], np.ones(5), "valid")
    Y, dl, pi, tau = cfg.sim_Y, cfg.sim_delta, cfg.sim_pi, cfg.sim_tau
    filas = {k: [] for k in ("tr", "t", "inst", "lado", "precio", "tam", "flags", "seq", "bpx", "apx", "bsz", "asz")}
    ohlc = []
    W = round(p_ref / tk) + 0.37
    P = T = 0.0
    inst = 7001
    seq = 0
    t_ult = 0
    s_prev = 1
    for s_i, fecha in enumerate(fechas):
        dia = int(fecha.value // DIA_NS)
        t_ses = apertura_utc(dia, cfg.tz_mercado)
        if s_i == S // 2:
            inst += 1
            W += 60.0
        fac = math.exp(0.15 * rng.normal())
        n_min = rng.poisson(tasa * perfil * fac)
        seg = np.concatenate([m * 60.0 + np.sort(rng.uniform(0, 60, k)) for m, k in enumerate(n_min)])
        n = len(seg)
        q_all = np.minimum(np.floor(rng.random(n) ** (-1 / alfa)), tope).astype(int)
        z = rng.normal(size=n)
        u_s = rng.random(n)
        partes = rng.random(n)
        spread2 = rng.random(n) < 0.05
        t_prev_s = 0.0
        ult_min, o_min = -1, None
        for i in range(n):
            ts = seg[i]
            dt = ts - t_prev_s
            t_prev_s = ts
            mi = min(int(ts // 60), MINUTOS_SESION - 1)
            W += sig_s[mi] * math.sqrt(max(dt, 0.0)) * z[i]
            if impacto:
                T *= math.exp(-dt / tau)
            verdadero = W + P + T
            bid = math.floor(verdadero)
            ask = bid + (2 if spread2[i] else 1)
            if cfg.sim_memoria > 0 and u_s[i] < cfg.sim_memoria:
                lado = s_prev
            else:
                lado = 1 if rng.random() < 0.5 else -1
            s_prev = lado
            q = int(q_all[i])
            t_ns = max(t_ses + int(ts * NS), t_ult + 1000)
            t_ult = t_ns
            seq += 1
            k = 1 if q < 2 or partes[i] < 0.6 else int(rng.integers(2, min(3, q) + 1))
            cortes = np.sort(rng.choice(np.arange(1, q), k - 1, replace=False)) if k > 1 else []
            precio = ask if lado > 0 else bid
            for j, qq in enumerate(np.diff(np.r_[0, cortes, q])):
                filas["tr"].append(t_ns + 30_000 + j)
                filas["t"].append(t_ns)
                filas["inst"].append(inst)
                filas["lado"].append(b"B" if lado > 0 else b"A")
                filas["precio"].append(int(precio) * tk_ns)
                filas["tam"].append(int(qq))
                filas["flags"].append(F_LAST if j == k - 1 else 0)
                filas["seq"].append(seq)
                filas["bpx"].append(int(bid) * tk_ns)
                filas["apx"].append(int(ask) * tk_ns)
                filas["bsz"].append(int(1 + rng.poisson(8)))
                filas["asz"].append(int(1 + rng.poisson(8)))
            # barra de 1 minuto
            m_abs = (t_ns // NS_MIN)
            if m_abs != ult_min:
                if o_min is not None:
                    ohlc.append(o_min)
                o_min = [m_abs * NS_MIN, inst, precio, precio, precio, precio, q]
                ult_min = m_abs
            else:
                o_min[3] = max(o_min[3], precio)
                o_min[4] = min(o_min[4], precio)
                o_min[5] = precio
                o_min[6] += q
            if impacto:
                f = Y * sig5[mi] * (q / v5[mi]) ** dl
                P += lado * pi * f
                T += lado * (1.0 - pi) * f
        if o_min is not None:
            ohlc.append(o_min)
    n = len(filas["t"])
    arr = np.zeros(n, dtype=DTYPE_TBBO)
    arr["ts_recv"] = np.asarray(filas["tr"], np.uint64)
    arr["ts_event"] = np.asarray(filas["t"], np.uint64)
    arr["instrument_id"] = np.asarray(filas["inst"], np.uint32)
    arr["action"] = b"T"
    arr["side"] = np.asarray(filas["lado"], "S1")
    arr["price"] = np.asarray(filas["precio"], np.int64)
    arr["size"] = np.asarray(filas["tam"], np.uint32)
    arr["flags"] = np.asarray(filas["flags"], np.uint8)
    arr["sequence"] = np.asarray(filas["seq"], np.uint32)
    arr["bid_px_00"] = np.asarray(filas["bpx"], np.int64)
    arr["ask_px_00"] = np.asarray(filas["apx"], np.int64)
    arr["bid_sz_00"] = np.asarray(filas["bsz"], np.uint32)
    arr["ask_sz_00"] = np.asarray(filas["asz"], np.uint32)
    o = np.asarray(ohlc, dtype=np.int64)
    barras = np.zeros(len(o), dtype=DTYPE_OHLCV)
    barras["ts_event"] = o[:, 0]
    barras["instrument_id"] = o[:, 1]
    for j, c in enumerate(("open", "high", "low", "close")):
        barras[c] = o[:, 2 + j] * tk_ns
    barras["volume"] = o[:, 6]
    verdad = {"Y": Y, "delta": dl, "pi": pi, "tau": tau, "impacto": impacto, "sesiones": [int(f.value // DIA_NS) for f in fechas],
              "roll_sesion": S // 2, "sig5": sig5, "v5": v5, "vol_min": vol_min, "omega": math.sqrt(1 / 12) / 1.0}
    return arr, barras, verdad


def config_simulacion(cfg: Config, verdad: dict, escalar_orden: bool = True) -> Config:
    """
    La sesión objetivo es la última simulada; la calibración, todas las anteriores que caben. El mercado
    simulado mueve mucho menos volumen que el NQ real, así que la orden se escala a la MISMA participación
    que 5,000 contratos son del NQ en el horario regular (≈ 1.5 %): con 5,000 fijos la simulación
    ejecutaría el 8-10 % del volumen y todo lo dominaría el impacto permanente.
    """
    ses = verdad["sesiones"]
    c = replace(cfg, sesion_objetivo=f"{fecha_de_dia(ses[-1]):%Y-%m-%d}",
                dias_calibracion=min(cfg.dias_calibracion, len(ses) - 1),
                dias_perfil=min(cfg.dias_perfil, len(ses) - 1))
    if escalar_orden and "vol_min" in verdad:
        m0, m1 = (segundo_de_hora(cfg.inicio_ct) // 60, segundo_de_hora(cfg.fin_ct) // 60)
        v_hor = float(np.asarray(verdad["vol_min"])[m0:m1].sum())
        c = replace(c, orden=int(max(cfg.pieza, round(0.015 * v_hor / cfg.pieza) * cfg.pieza)))
    return c


def a_dbn(arr: np.ndarray, cfg: Config) -> bytes:
    """El TBBO simulado → un archivo DBN de verdad, para probar la ruta de Databento."""
    import databento_dbn as dd
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
                                       action=dd.Action.TRADE, side=lado[bytes(r["side"])], depth=0,
                                       ts_recv=int(r["ts_recv"]), flags=int(r["flags"]),
                                       sequence=int(r["sequence"]), levels=lv)))
    return b"".join(partes)


def a_dbn_ohlcv(barras: np.ndarray, cfg: Config) -> bytes:
    """Las barras simuladas → un DBN OHLCV-1m de verdad."""
    import databento_dbn as dd
    meta = dd.Metadata(dataset=cfg.dataset, start=int(barras["ts_event"][0]), stype_in=dd.SType.CONTINUOUS,
                       stype_out=dd.SType.INSTRUMENT_ID, schema=dd.Schema.OHLCV_1M, symbols=[cfg.symbol],
                       partial=[], not_found=[], mappings=[], end=int(barras["ts_event"][-1]) + NS_MIN)
    partes = [bytes(meta.encode())]
    for r in barras:
        partes.append(bytes(dd.OHLCVMsg(rtype=dd.RType.OHLCV_1M, publisher_id=1, instrument_id=int(r["instrument_id"]),
                                        ts_event=int(r["ts_event"]), open=int(r["open"]), high=int(r["high"]),
                                        low=int(r["low"]), close=int(r["close"]), volume=int(r["volume"]))))
    return b"".join(partes)


# =============================================================================
# 9. EL CÁLCULO COMPLETO, TU SCRIPT, LA VERDAD Y EL CHEQUEO DE CORDURA
# =============================================================================
@dataclass
class Resultado:
    cfg: Config
    E: pd.DataFrame
    H: pd.DataFrame
    barras: pd.DataFrame
    perf: Perfiles
    obs: Observaciones
    x_ref: float
    ajustes: dict                     # nombre del modelo → Ajuste (muestra completa)
    curva: pd.DataFrame
    permanente: tuple
    perfil: pd.DataFrame
    costo_propio: dict
    roll: Rolling
    bt: Backtest
    plan: pd.DataFrame
    plan_info: dict
    cordura: list
    info: dict
    motor: MotorEventos
    ohlcv: pd.DataFrame = field(default_factory=pd.DataFrame)
    tu: dict = field(default_factory=dict)
    verdad: dict | None = None
    medicion: dict | None = None


def plan_siguiente(roll: Rolling, x_ref: float, perf: Perfiles, spreads: pd.DataFrame, cfg: Config,
                   lam: float) -> tuple[pd.DataFrame, dict]:
    """El plan de la PRÓXIMA sesión con lo último que se sabe: slices con hora CT y CDMX por algoritmo."""
    fut = roll.tabla[roll.tabla["siguiente"]] if len(roll.tabla) else roll.tabla
    if not len(fut):
        return pd.DataFrame(), {}
    dia = int(fut["sesion"].iloc[-1])
    aj, A = roll.ajustes[dia]
    mer = mercado(dia, perf, spreads, cfg)
    if mer.V_hor <= 0:
        return pd.DataFrame(), {}
    mod = modelo_impacto(aj.p, A, x_ref, mer, cfg)
    M = matrices(mod, mer)
    X = float(cfg.orden)
    if not lam:
        lam = lambda_de_urgencia(cfg.urgencia, eta_slices(mod, mer, M, total=True), M["w"].reshape(mer.N, mer.m).sum(axis=1))
    filas = {}
    resumen = {}
    for nm in ("TWAP", "VWAP", "POV*", "AC", "ÓPTIMO"):
        u = plan_estatico(nm, X, mer, mod, M, lam)
        n = u.reshape(mer.N, mer.m).sum(axis=1)
        filas[nm] = n
        E_, sd = costo_modelo(u, X, M)
        resumen[nm] = {"costo": E_ / X, "sd": sd / X}
    t_sl = mer.t0 + (np.arange(mer.N) * mer.slice_s * NS).astype(np.int64)
    idx = a_indice(t_sl)
    T = pd.DataFrame({"hora_ct": idx.tz_convert(cfg.tz_mercado).strftime("%H:%M"),
                      "hora_cdmx": idx.tz_convert(cfg.tz_local).strftime("%H:%M"), **filas})
    return T, {"dia": dia, "resumen": resumen, "lam": lam, "A": A, "p": dict(aj.p), "V_hor": mer.V_hor}


def chequeo_lado_e(E: pd.DataFrame) -> float:
    """Fracción de compras agresivas que se ejecutan en el ask previo o más arriba (y ventas en el bid)."""
    m = E["libro0"].to_numpy().astype(bool)
    lado, px = E["lado"].to_numpy()[m], E["px_ini"].to_numpy()[m]
    ok = np.where(lado > 0, px >= E["ask0"].to_numpy()[m], px <= E["bid0"].to_numpy()[m])
    return float(ok.mean()) if len(ok) else np.nan


def analizar(tbbo, ohlcv, cfg: Config, verdad: dict | None = None, verbose: bool = True,
             rapido: bool = False) -> Resultado:
    validar(cfg)
    t_ini = time.time()

    def paso(txt):
        if verbose:
            print(f"⚙️  {txt} ({time.time() - t_ini:.0f} s)")

    paso("Motor de eventos y barras de 1 minuto")
    E0, motor, barras = correr_motor_ejecucion(tbbo, cfg, verbose=verbose)
    if not len(E0):
        sys.exit("❌ No hubo agresiones válidas en el TBBO.")
    E = preparar_eventos(E0, cfg)
    del E0
    d_obj = dia_objetivo(cfg)
    # nada posterior a la sesión objetivo (con --archivo puede haber más): se cortan las sesiones del final
    E = E.iloc[:int(np.searchsorted(E["sesion"].to_numpy(), d_obj, side="right"))].copy()
    barras = barras[barras["sesion"] <= d_obj] if len(barras) else barras
    if not len(E):
        sys.exit(f"❌ No hay eventos hasta la sesión {cfg.sesion_objetivo}.")
    n_ses = int(E["sesion"].nunique())
    cambios = int(np.sum(np.diff(E["inst"].to_numpy()) != 0))
    if cambios > 2 * n_ses + 2:
        sys.exit(f"❌ El TBBO trae varios contratos a la vez ({cambios:,} cambios de contrato en {n_ses} sesiones).\n"
                 "   Usa simbología continua (NQ.n.0, como la descarga por omisión) o filtra un solo contrato.")
    H, hid = agrupar_huellas(E, cfg)
    E["hid"] = hid
    U, pct, clase = clasificar_magnitud(H, cfg)
    H["pct"], H["clase"] = pct, clase
    H["tipo"] = tipificar(H, cfg)
    H["ventana"] = True
    b_ohlc = barras_ohlcv(ohlcv, cfg) if ohlcv is not None else pd.DataFrame()
    if len(b_ohlc):
        b_ohlc = b_ohlc[b_ohlc["sesion"] <= d_obj]
    slots_vol = tabla_slots(b_ohlc, cfg, "close") if len(b_ohlc) else tabla_slots(barras.assign(inst=0), cfg, "mid")
    perf = Perfiles(slots_vol, cfg, tabla_slots(barras.assign(inst=0), cfg, "mid"))
    var = Varianza(perf, cfg)
    der = deriva_sesiones(E, cfg)
    paso("Eventos clave")
    obs = eventos_clave(H, E, perf, var, der, cfg)
    if obs.n < cfg.min_eventos:
        sys.exit(f"❌ Sólo hay {obs.n} eventos clave (mínimo {cfg.min_eventos}). Amplía --calibracion o baja --p-grande.")
    flujo = Flujo(H, E, perf, cfg)
    x_ref = x_referencia(obs)
    ajustes = {}
    paso(f"MLE · respuesta ({obs.n:,} eventos clave)")
    ajustes["respuesta"] = ajustar(obs, MODELOS["respuesta"], x_ref, None, jackknife=not rapido)
    paso("MLE · propagador (todas las huellas)")
    ajustes["propagador"] = ajustar(obs, MODELOS["propagador"], x_ref, flujo, jackknife=not rapido)
    for nm in ("raiz", "lineal", "t"):
        paso(f"MLE · {MODELOS[nm].nombre}")
        ajustes[nm] = ajustar(obs, MODELOS[nm], x_ref, None, inicio=ajustes["respuesta"].p, jackknife=False)
    vero_r = Verosimilitud(obs, MODELOS["respuesta"], x_ref)
    curva = curva_semiparametrica(ajustes["respuesta"], vero_r)
    perm = prueba_permanente(curva, ajustes["respuesta"].sesiones)
    perfil = pd.DataFrame() if rapido else perfil_delta(obs, ajustes["respuesta"], vero_r)
    cp = costo_propio(obs, ajustes["respuesta"])
    esp_ej = MODELOS[cfg.modelo_ejecucion]
    paso(f"Rolling (modelo de ejecución: {esp_ej.nombre})")
    roll = rolling(obs, esp_ej, x_ref, flujo if esp_ej.media == "propagador" else None, cfg,
                   ajustes[cfg.modelo_ejecucion], verbose=verbose)
    spreads = perfil_spread(barras, cfg)
    paso("Backtest walk-forward de los algoritmos")
    pruebas_ = [int(s) for s in roll.tabla.loc[~roll.tabla["siguiente"], "sesion"]] if len(roll.tabla) else []
    bt = backtest(pruebas_, roll.ajustes, x_ref, perf, spreads, E, barras, cfg, ajustes[cfg.modelo_ejecucion],
                  n_param=0 if rapido else cfg.n_param, verbose=verbose)
    plan, plan_info = plan_siguiente(roll, x_ref, perf, spreads, cfg, bt.lam)
    info = {"registros": motor.registros, "operaciones": motor.operaciones, "eventos": len(E), "huellas": len(H),
            "eventos_clave": obs.n, "sesiones_tbbo": int(H["sesion"].nunique()),
            "sesiones_ohlcv": int(b_ohlc["sesion"].nunique()) if len(b_ohlc) else 0,
            "sesiones_prueba": int(bt.filas["sesion"].nunique()) if len(bt.filas) else 0,
            "lado_ok": chequeo_lado_e(E), "fuente_sigma": perf.fuente_sigma, "segundos": time.time() - t_ini,
            "rolls": int(np.sum(np.diff(E["inst"].to_numpy()) != 0))}
    res = Resultado(cfg, E, H, barras, perf, obs, x_ref, ajustes, curva, perm, perfil, cp, roll, bt, plan, plan_info,
                    [], info, motor, b_ohlc, {}, verdad)
    res.tu = tu_script(b_ohlc if len(b_ohlc) else barras.rename(columns={"mid": "close"}), cfg)
    if verdad is not None:
        res.medicion = medir_contra_verdad(res)
    res.cordura = cordura(res)
    paso("Listo")
    return res


def cordura(res: Resultado) -> list:
    c = []
    m, i, cfg = res.motor, res.info, res.cfg
    ops = m.registros - m.conteo.get(REGLAS[0], 0)
    c.append((m.operaciones > 0.5 * ops, f"{m.operaciones:,} de {ops:,} operaciones son agresiones válidas"))
    c.append((i["rolls"] <= i["sesiones_tbbo"], f"{i['rolls']} cambios de contrato en {i['sesiones_tbbo']} sesiones (un contrato a la vez)"))
    c.append((i["lado_ok"] > 0.95, f"side = agresor: {i['lado_ok']:.1%} de las compras en el ask previo o arriba"))
    c.append((i["sesiones_tbbo"] >= cfg.ventana_sesiones + 2,
              f"{i['sesiones_tbbo']} sesiones de TBBO y {i['sesiones_ohlcv']} de OHLCV · σ del perfil con {i['fuente_sigma']}"))
    aj = res.ajustes["respuesta"]
    c.append((aj.n >= cfg.min_eventos, f"{aj.n:,} eventos clave en {aj.sesiones} sesiones para el MLE"))
    c.append((0.15 < aj.p["delta"] < 1.1, f"δ = {aj.p['delta']:.2f} ± {aj.se.get('delta', np.nan):.2f} (impacto cóncavo si < 1)"))
    for a in aj.avisos:
        c.append((False, f"MLE respuesta: {a}"))
    for a in res.ajustes["propagador"].avisos:
        c.append((False, f"MLE propagador: {a}"))
    se_h, se_r = aj.se_hess.get("A", np.nan), aj.se.get("A", np.nan)
    if np.isfinite(se_h) and se_h > 0:
        c.append((True, f"EE robusto de A = {se_r / se_h:.1f}× el del hessiano: los eventos de una sesión no son independientes"))
    g0 = res.curva["g"].iloc[0] if len(res.curva) else np.nan
    c.append((abs(g0 - 1) < 0.3, f"curva semiparamétrica en el horizonte 0: g = {g0:.2f} (≈ 1 si la forma del tamaño cuadra)"))
    gb, tg, pg = res.permanente
    if np.isfinite(gb):
        c.append((True, f"decaimiento: g promedio 15-60 s = {gb:.2f} (H0 sin decaimiento, p = {pg:.3f})"))
    cp = res.costo_propio
    if np.isfinite(cp.get("c", np.nan)):
        if res.verdad is not None:
            c.append((True, f"costo propio del agresor = {cp['c']:.2f} ± {cp['se']:.2f} × su impacto (el simulador llena al "
                            "mejor precio: ≈ 0 es lo esperado; con datos reales se compara con el ½ del optimizador)"))
        else:
            c.append((abs(cp["c"] - 0.5) < max(2 * cp["se"], 0.25),
                      f"costo propio del agresor = {cp['c']:.2f} ± {cp['se']:.2f} × su impacto (el optimizador usa ½)"))
    est = res.roll.estabilidad
    if np.isfinite(est.get("p", np.nan)):
        c.append((est["p"] > 0.05, f"estabilidad de A entre sesiones (Nyblom): p = {est['p']:.3f}"))
    bt = res.bt
    if len(bt.filas):
        n = bt.filas["sesion"].nunique()
        z = bt.filas.loc[(bt.filas["lado"] == 1) & (bt.filas["algoritmo"] == "TWAP"), "z_timing"].to_numpy(dtype=float)
        z = z[np.isfinite(z)]                                  # una por sesión: los algoritmos comparten la trayectoria
        c.append((n >= 5, f"{n} sesiones de prueba en el walk-forward"))
        if len(z) >= 5:
            c.append((0.5 < np.std(z, ddof=1) < 2.0,
                      f"timing estandarizado (TWAP): media {np.mean(z):+.2f}, desv. {np.std(z, ddof=1):.2f} (≈ N(0, 1))"))
        fr = bt.frontera
        if len(fr):
            # optimalidad exacta: para cada λ de la frontera, ningún plan de la misma familia (slices con
            # flujo parejo, decididos antes de abrir) puede tener E + λ·Var menor que el ÓPTIMO de esa λ
            X = float(cfg.orden)
            env = fr[fr["tipo"] == "frontera"]
            malos = []
            alg = fr[(fr["tipo"] == "algoritmo") & fr["nombre"].isin(["TWAP", "VWAP", "AC", "ÓPTIMO"])]
            if "respeta_tope" in alg:                          # el ÓPTIMO lleva el tope de participación: sólo se compara con los que caben
                alg = alg[alg["respeta_tope"].fillna(True).astype(bool)]
            for _, f in alg.iterrows():
                obj_a = f["E"] + env["lam"].to_numpy() * X * f["sd"] ** 2
                obj_k = env["E"].to_numpy() + env["lam"].to_numpy() * X * env["sd"].to_numpy() ** 2
                if (obj_a < obj_k - 1e-6 * (1 + np.abs(obj_k))).any():
                    malos.append(f["nombre"])
            c.append((not malos, "ningún plan estático mejora al ÓPTIMO en E + λ·Var para ninguna urgencia de la frontera"
                      if not malos else f"⚠ mejoran al ÓPTIMO en E + λ·Var (el QP no convergió): {', '.join(malos)}"))
        if np.isfinite(bt.pico.get("razon", np.nan)):
            c.append((1 / 3 <= bt.pico["razon"] <= 3, f"impacto pico de la orden = {bt.pico['razon']:.2f}× la ley de raíz cuadrada"))
        pm = bt.filas.groupby("algoritmo")["part_max"].max()
        altos = [k for k, v in pm.items() if v > cfg.part_max]
        c.append((not altos, f"participación máxima por minuto ≤ {cfg.part_max:.0%}" if not altos
                  else f"participación > {cfg.part_max:.0%} en algún minuto: {', '.join(altos)}"))
        fz = bt.filas.groupby("algoritmo")["forzado"].mean()
        if fz.get("POV", 0) > 0:
            c.append((False, f"POV al {cfg.pov:.0%} dejó {fz['POV']:.0f} contratos para forzar al final, en promedio"))
        for a in bt.avisos:
            c.append((False, a))
    return c


def tu_script(b: pd.DataFrame, cfg: Config) -> dict:
    """
    Réplica FIEL de Optimal_Execution_Algorithms.py sobre las velas de 1 minuto de la sesión objetivo
    (las mismas que bajaría tu fetch_data), para mostrar qué reportaría y por qué no sirve para elegir:
      · TWAP: 78 rebanadas iguales, cada una al CIERRE de un solo minuto;
      · VWAP: pesos con el volumen del MISMO día (sabe a las 8:30 lo que se operará a las 14:00);
      · POV: 10 % del volumen de cada bloque de 5 minutos YA conocido al decidir; termina en minutos;
      · slippage = 5 bps × (q / volumen del minuto), o 10 bps × (q/V − 0.2) si q/V > 0.2;
      · "VWAP de mercado" con los minutos de CADA algoritmo (un benchmark distinto para cada uno);
      · el "mejor" es el de menor |slippage| de ese único día.
    Precios correctos aquí (tu script además los divide entre 1e9: con to_df() ya vienen en decimales).
    """
    if not len(b):
        return {"disponible": False}
    d = dia_objetivo(cfg)
    f = fecha_de_dia(d)
    t0, t1 = a_utc(f"{f:%Y-%m-%d} 13:30", "UTC").value, a_utc(f"{f:%Y-%m-%d} 20:00", "UTC").value   # tu START/END_DATE
    df = b[(b["t"] >= t0) & (b["t"] < t1)].dropna(subset=["close"])
    if len(df) < 30:
        return {"disponible": False}
    X, n_sl, pov = float(cfg.orden), 78, cfg.pov
    precio = df["close"].to_numpy(dtype=float) * tick(cfg.symbol)
    vol = df["vol"].to_numpy(dtype=float)
    n = len(df)
    paso = max(1, n // n_sl)
    # --- schedules, tal cual ---
    tw = [(min(k * paso, n - 1), X / n_sl) for k in range(n_sl)]
    sl = np.floor(np.arange(n) / (n / n_sl)).astype(int)
    vprof = np.bincount(sl[sl < n_sl], weights=vol[sl < n_sl], minlength=n_sl)
    w = vprof / vprof.sum() if vprof.sum() > 0 else np.full(n_sl, 1 / n_sl)
    primero = np.array([int(np.flatnonzero(sl == k)[0]) if (sl == k).any() else n - 1 for k in range(n_sl)])
    vw = [(int(primero[k]), float(w[k] * X)) for k in range(n_sl)]
    vw[-1] = (vw[-1][0], X - sum(q for _, q in vw[:-1]))
    po, hecho = [], 0.0
    for i in range(0, n, 5):
        if hecho >= X:
            break
        vs = float(vol[i:i + 5].sum())
        obj = min(vs * pov, X - hecho)
        if obj > 0:
            hecho += obj
            po.append((i, obj))
    if hecho < X and po:
        po[-1] = (po[-1][0], po[-1][1] + X - hecho)

    def simular_(sch):
        filas = []
        for i, q in sch:
            v = vol[i]
            r = q / v if v > 0 else 0.0
            bps = (r - 0.2) * 10 if r > 0.2 else r * 5
            filas.append((i, q, precio[i], precio[i] * (1 + bps / 1e4), v, bps))
        f = np.array(filas)
        q, pm, pe, v = f[:, 1], f[:, 2], f[:, 3], f[:, 4]
        vwap_e = float((pe * q).sum() / q.sum())
        vwap_m = float((pm * v).sum() / v.sum()) if v.sum() > 0 else np.nan
        return {"rebanadas": len(f), "minutos": int(f[-1, 0] - f[0, 0] + 5), "vwap_exec": vwap_e,
                "vwap_mercado": vwap_m, "slippage_bps": (vwap_e - vwap_m) / vwap_m * 1e4,
                "slippage_medio": float(f[:, 5].mean()), "total_cost": float((pe - pm).sum()),
                "q_max_vs_min": float(np.max(q / np.maximum(v, 1))), "inicio": int(f[0, 0])}
    out = {nm: simular_(sch) for nm, sch in (("TWAP", tw), ("VWAP", vw), ("POV", po))}
    mejor = min(out, key=lambda k: abs(out[k]["slippage_bps"]))
    # cuánto cambian los pesos de VWAP entre el perfil del mismo día y el de los días anteriores
    return {"disponible": True, "res": out, "mejor": mejor, "minutos": n, "fecha": f"{fecha_de_dia(d):%Y-%m-%d}",
            "precio_tuyo": float(precio.mean()) / 1e9, "w_mismo_dia": w}


def medir_contra_verdad(res) -> dict:
    """Con la simulación: los parámetros estimados contra los verdaderos y el costo con el modelo VERDADERO."""
    v, obs, cfg = res.verdad, res.obs, res.cfg
    if not v or not v.get("impacto"):
        return {}
    out = {"params": []}
    # impacto inicial verdadero de cada evento clave: Y·Σₑ σ₅(m)·(qₑ/V₅(m))^δ con los perfiles VERDADEROS
    _, seg = reloj_sesion(obs.K["t_ini"].to_numpy(), cfg.tz_mercado)
    mi = np.clip(seg // 60, 0, len(v["sig5"]) - 1)
    f_true = v["Y"] * base_huella(obs.qe, obs.ptr, v["sig5"][mi], v["v5"][mi], v["delta"], 1.0)
    for nm in ("respuesta", "propagador"):
        aj = res.ajustes.get(nm)
        if aj is None:
            continue
        f_hat = aj.A * base_huella(obs.qe, obs.ptr, obs.K["sig5"].to_numpy(), obs.K["v5"].to_numpy(), aj.p["delta"], aj.x_ref)
        for k in ("delta", "pi", "tau", "omega"):
            se = aj.se.get(k, np.nan)
            out["params"].append({"modelo": nm, "parametro": k, "estimado": aj.p[k], "ee": se, "verdad": v[k],
                                  "z": (aj.p[k] - v[k]) / se if se and np.isfinite(se) and se > 0 else np.nan})
        out["params"].append({"modelo": nm, "parametro": "f̂/f (impacto inicial)", "estimado": float(np.mean(f_hat) / np.mean(f_true)),
                              "ee": np.nan, "verdad": 1.0, "z": np.nan})
    out["params"] = pd.DataFrame(out["params"])
    # costo de cada plan de la sesión objetivo con el modelo VERDADERO (A = Y·x_ref^δ en la escala del módulo)
    bt = res.bt
    if bt.mercado is not None and bt.planes:
        X = float(cfg.orden)
        p_true = {"delta": v["delta"], "pi": v["pi"], "tau": v["tau"]}
        m_true = modelo_impacto(p_true, v["Y"] * res.x_ref ** v["delta"], res.x_ref, bt.mercado, cfg)
        M_true = matrices(m_true, bt.mercado)
        opt = costo_modelo(optimo_ow(X, bt.lam, M_true, bt.mercado)[0], X, M_true)
        filas = []
        for nm, u in bt.planes.items():
            c_true = costo_modelo(u, X, M_true)
            c_mod = costo_modelo(u, X, matrices(bt.modelo, bt.mercado))
            filas.append({"algoritmo": nm, "costo_modelo": c_mod[0] / X, "costo_verdad": c_true[0] / X,
                          "arrepentimiento": (c_true[0] + bt.lam * c_true[1] ** 2 - opt[0] - bt.lam * opt[1] ** 2) / X})
        out["costos"] = pd.DataFrame(filas)
    return out


# =============================================================================
# 10. REPORTES
# =============================================================================
CLASES = ("NORMAL", "GRANDE", "MEGA", "BALLENA")
TIPOS = ("BLOQUE", "BARRIDO", "ABSORCIÓN", "FRAGMENTADA")
NOMBRE_PAR = {"A": "A", "delta": "δ", "pi": "π", "tau": "τ (s)", "omega": "ω", "kappa": "κ", "phi": "ϕ", "nu": "ν"}


def _usd(ticks_contrato: float, cfg: Config, contratos: float | None = None) -> str:
    if not np.isfinite(ticks_contrato):
        return "—"
    return f"US$ {ticks_contrato * valor_tick_usd(cfg.symbol) * (cfg.orden if contratos is None else contratos):,.0f}"


def _hora(t_ns: int, cfg: Config) -> str:
    t = pd.Timestamp(int(t_ns), tz="UTC")
    return f"{t.tz_convert(cfg.tz_mercado):%H:%M} CT · {t.tz_convert(cfg.tz_local):%H:%M} CDMX"


def _lado_txt(cfg: Config) -> str:
    return "COMPRA" if cfg.lado > 0 else "VENTA"


def reporte_datos(res: Resultado) -> None:
    cfg, i, m = res.cfg, res.info, res.motor
    _titulo(f"DATOS · {cfg.symbol} ({nombre(cfg.symbol)}) · tick {tick(cfg.symbol):g} = US$ {valor_tick_usd(cfg.symbol):,.2f}")
    print(f"  Sesión objetivo: {cfg.sesion_objetivo} · horizonte {cfg.inicio_ct}-{cfg.fin_ct} CT · orden de "
          f"{_lado_txt(cfg)} de {cfg.orden:,} contratos en slices de {cfg.slice_min} min (piezas de {cfg.pieza})")
    print(f"  TBBO: {i['sesiones_tbbo']} sesiones · {m.registros:,} registros → {m.operaciones:,} agresiones válidas → "
          f"{i['eventos']:,} EVENTOS (agresión exacta de CME) → {i['huellas']:,} HUELLAS (≤ {cfg.rafaga_ms:g} ms)")
    print(f"  OHLCV-1m: {i['sesiones_ohlcv']} sesiones (perfil de volumen) · σ intradía con el {i['fuente_sigma']} · rolls: {i['rolls']}")
    for k, v in m.conteo.items():
        if v:
            print(f"     descartado · {k:<44} {v:>10,}")
    print(f"  Lado del agresor: {i['lado_ok']:.1%} de las compras se ejecutaron en el ask previo o más arriba")


def reporte_tu_script(res: Resultado) -> None:
    tu = res.tu
    _titulo("TU SCRIPT (Optimal_Execution_Algorithms.py) SOBRE LA MISMA SESIÓN")
    if not tu.get("disponible"):
        print("  (no hay velas de la sesión objetivo en el horizonte para replicarlo)")
        return
    print(f"  {tu['fecha']} · {tu['minutos']} velas de 1 min · tus precios saldrían en ~{tu['precio_tuyo']:.6f} "
          "(divides entre 1e9 lo que to_df() ya entrega en decimales)")
    print(f"  {'Algoritmo':<10}{'rebanadas':>10}{'minutos':>9}{'slippage':>11}{'VWAP mercado':>15}{'q/V máx':>9}")
    for nm, r in tu["res"].items():
        print(f"  {nm:<10}{r['rebanadas']:>10}{r['minutos']:>9}{r['slippage_bps']:>9.2f}bp"
              f"{_precio_pts(r['vwap_mercado']):>15}{r['q_max_vs_min']:>9.2f}")
    print(f"  Tu script declararía MEJOR a {tu['mejor']}. Por qué no se puede concluir eso:")
    po = tu["res"]["POV"]
    print(f"   · POV termina en {po['minutos']} minutos; TWAP y VWAP en {tu['res']['TWAP']['minutos']}: no son la misma orden.")
    print("   · Cada algoritmo se compara con SU propio 'VWAP de mercado' (sólo los minutos en que operó).")
    print("   · VWAP usa el volumen del mismo día (futuro) y POV el del bloque que todavía no ocurre.")
    print("   · Todo se ejecuta al cierre de un minuto; el slippage es una fórmula inventada (5-10 bps × q/V)")
    print("     que no cobra el spread ni el impacto que la propia orden deja para las siguientes.")
    print("   · Un día no es muestra: el resultado lo decide la trayectoria del precio, no el algoritmo.")


def _precio_pts(x: float) -> str:
    return f"{x:,.2f}" if np.isfinite(x) else "—"


def reporte_eventos(res: Resultado) -> None:
    obs, cfg = res.obs, res.cfg
    K = obs.K
    _titulo("1 · EXTRACCIÓN DE EVENTOS CLAVE")
    print(f"  Evento clave = huella ≥ p{cfg.p_grande * 100:g} de las {cfg.ventana_magnitud} sesiones ANTERIORES, "
          f"{'horario regular' if cfg.mle_franja == 'rth' else 'todo el día'}, con libro previo y ≥ 2 horizontes")
    print(f"  {obs.n:,} eventos en {K['sesion'].nunique()} sesiones · tamaño de referencia x_ref = Q/V₅ = {res.x_ref:.4f} "
          f"(≈ {res.x_ref * np.nanmedian(K['v5']):.0f} contratos a media sesión)")
    cl = K["clase"].value_counts().reindex([1, 2, 3]).fillna(0).astype(int)
    tp = K["tipo"].value_counts().reindex(range(4)).fillna(0).astype(int)
    print("  Clases: " + " · ".join(f"{CLASES[c]} {cl[c]:,}" for c in (1, 2, 3)) + "   Tipos: " +
          " · ".join(f"{TIPOS[t]} {tp[t]:,}" for t in range(4)))
    q = K["Q"].to_numpy()
    print(f"  Q: mediana {np.median(q):.0f} · p90 {np.quantile(q, 0.9):.0f} · máx {q.max():.0f} contratos · "
          f"compras {(K['lado'] > 0).mean():.1%} · eventos por huella: mediana {np.median(K['n_eventos']):.0f}")
    disp = (obs.k[:, None] > np.arange(len(obs.horizontes))[None, :]).mean(axis=0)
    print("  Horizontes con dato: " + " · ".join(f"{int(h)}s {d:.0%}" for h, d in zip(obs.horizontes, disp)))


def reporte_mle(res: Resultado) -> None:
    _titulo("2 · AJUSTE MATEMÁTICO DEL MODELO (MLE)")
    print("  Δmid(h)·lado = A·σ₅·Σₑ((qₑ/V₅)/x_ref)^δ · [π + (1 − π)·e^(−h/τ)] + ruido")
    print("  Cov = κ²·V(difusión intradía) + ω²·(microestructura) + ϕ²·(horizonte 0) · QMLE gaussiano, A por GLS")
    print("  EE robusto = max(CR1 por sesión, jackknife CV3), IC con la t de G − 1 gl\n")
    noms = ["A", "delta", "pi", "tau", "omega", "kappa", "phi", "nu"]
    print(f"  {'modelo':<44}" + "".join(f"{NOMBRE_PAR[n]:>14}" for n in noms) + f"{'CLAIC':>12}")
    mejor = min(a.claic for a in res.ajustes.values() if np.isfinite(a.claic)) if any(
        np.isfinite(a.claic) for a in res.ajustes.values()) else np.nan
    for nm, aj in res.ajustes.items():
        celdas = []
        for n in noms:
            v = aj.A if n == "A" else aj.p.get(n, np.nan)
            if n == "nu" and aj.esp.dist != "t":
                celdas.append("—".rjust(14))
                continue
            se = aj.se.get(n, np.nan)
            fijo = n != "A" and n not in aj.libres
            dec = 4 if n == "A" else (0 if n == "tau" else 2)
            txt = (f"{v:.{dec}f}" + ("" if fijo or not np.isfinite(se) else f"±{se:.{dec}f}") + ("*" if fijo else "")
                   + ("†" if n in aj.en_cota else ""))
            celdas.append(txt.rjust(14))
        d = aj.claic - mejor if np.isfinite(aj.claic) else np.nan
        print(f"  {aj.esp.nombre[:43]:<44}" + "".join(celdas) + f"{_fmt(d, 1, 12)}")
    print("  (* fijo · † en la cota, sin EE · CLAIC: diferencia con el mejor; la verosimilitud compuesta penaliza con tr(J·H⁻¹))")
    aj = res.ajustes["respuesta"]
    for nm, val in (("delta", 0.5), ("delta", 1.0)):
        t, p = prueba_wald(aj, nm, val)
        print(f"  Wald robusto δ = {val:g}: t = {_fmt(t, 2, 6)} · p = {_fmt(p, 3, 5)}")
    gb, tg, pg = res.permanente
    print(f"  Decaimiento: g promedio 15-60 s = {gb:.2f} (1 = nada decae) · t = {tg:.2f} · p = {pg:.3f}")
    if len(res.perfil):
        P = res.perfil
        lo, hi = P.attrs.get("ic", (np.nan, np.nan))
        lr1 = P.loc[np.isclose(P["delta"], 1.0), "lr"]
        lr5 = P.loc[np.isclose(P["delta"], 0.5), "lr"]
        print(f"  Perfil de δ (LR escalado por ĉ = {P.attrs['c']:.2f}): IC 95 % [{_fmt(lo, 3, 5).strip()}, {_fmt(hi, 3, 5).strip()}]"
              + (f" · LR(δ = 0.5) = {lr5.iloc[0]:.1f}" if len(lr5) else "") + (f" · LR(δ = 1) = {lr1.iloc[0]:.0f}" if len(lr1) else "")
              + f" (umbral {P.attrs['umbral']:.1f})")
    cp = res.costo_propio
    if np.isfinite(cp.get("c", np.nan)):
        print(f"  Costo propio del agresor: {cp['c']:.2f} ± {cp['se']:.2f} × su impacto (n = {cp['n']:,}; el optimizador usa ½)")
    print("\n  Curva semiparamétrica (sin forma funcional) contra el kernel ajustado:")
    C = res.curva
    print("  " + "  ".join(f"{int(h):>5}s" for h in C["h"]))
    print("  " + "  ".join(f"{g:6.2f}" for g in C["g"]) + "   g(h) empírica")
    print("  " + "  ".join(f"{g:6.2f}" for g in C["modelo"]) + "   G(h) = π + (1 − π)e^(−h/τ)")
    print("  " + "  ".join(f"{s:6.2f}" for s in C["se"]) + "   EE")
    for nm, aj in res.ajustes.items():
        for a in aj.avisos:
            print(f"  ⚠ {nm}: {a}")


def reporte_rolling(res: Resultado) -> None:
    R, cfg = res.roll, res.cfg
    _titulo(f"3 · ANÁLISIS DINÁMICO (ROLLING) · A con las últimas {cfg.ventana_sesiones} sesiones, δ π τ expansivos")
    if not len(R.tabla):
        print("  (no hay sesiones suficientes)")
        return
    print(f"  {'sesión':<12}{'eventos':>8}{'A':>9}{'IC 95 %':>20}{'δ':>7}{'π':>7}{'τ (s)':>8}  avisos")
    for _, f in R.tabla.iterrows():
        et = f"{fecha_de_dia(int(f['sesion'])):%Y-%m-%d}" + ("*" if f["siguiente"] else " ")
        print(f"  {et:<12}{int(f['n']):>8,}{f['A']:>9.4f}   [{f['A_lo']:.4f}, {f['A_hi']:.4f}]{f['delta']:>7.2f}"
              f"{f['pi']:>7.2f}{f['tau']:>8.0f}  {f['avisos'][:40]}")
    print("  (* la próxima sesión: el plan de mañana usa esta fila)")
    if len(R.por_hora):
        print("  A por hora del día (CT): " + " · ".join(f"{int(h)}h {a:.4f}" for h, a in zip(R.por_hora["hora"], R.por_hora["A"])))
    e = R.estabilidad
    if np.isfinite(e.get("p", np.nan)):
        print(f"  Estabilidad de A entre sesiones (Nyblom, {e['G']} sesiones): L = {e['L']:.3f} · p (permutación) = {e['p']:.3f}"
              + ("  → A cambia entre sesiones" if e["p"] < 0.05 else "  → sin evidencia de cambio"))


def reporte_backtest(res: Resultado) -> None:
    bt, cfg = res.bt, res.cfg
    X = float(cfg.orden)
    _titulo(f"4 · ALGORITMOS · walk-forward de {res.info['sesiones_prueba']} sesiones · compra Y venta con lo sabido antes")
    if not len(bt.filas):
        print("  (sin sesiones de prueba)")
        return
    print(f"  λ fija = {bt.lam:.3g} por tick·contrato (urgencia κT = {cfg.urgencia:g}) · costo en ticks por contrato")
    print(f"  {'algoritmo':<9}{'costo':>9}{'en US$':>13}{'vs TWAP':>10}{'p Holm':>8}{'MDE':>8}{'riesgo':>9}  veredicto")
    for _, f in bt.comparacion.iterrows():
        print(f"  {f['algoritmo']:<9}{f['costo']:>9.3f}{_usd(f['costo'], cfg):>13}{_fmt(f['dif_vs_twap'], 3, 10)}"
              f"{_fmt(f['p_holm'], 3, 8)}{_fmt(f['mde'], 3, 8)}{_fmt(f['riesgo'], 1, 9)}  {f['veredicto']}")
    print("  costo = promedio de compra y venta (cancela la trayectoria: queda el costo MODELADO) · riesgo = desv. del")
    print("  IS de un solo lado entre sesiones (timing real) · MDE = diferencia mínima detectable con 80 % de potencia ·")
    print("  'irrelevante' = significativa pero menor que 0.02 t/c o que el 0.5 % del costo de TWAP")
    A = bt.filas.groupby("algoritmo")[["spread", "propio", "transitorio", "permanente", "timing"]].mean() / X
    print("\n  Descomposición (ticks por contrato, promedio de sesiones y lados):")
    print(f"  {'algoritmo':<9}{'spread':>9}{'propio':>9}{'transit.':>10}{'perman.':>9}{'timing':>9}   part. máx  forzado")
    pm = bt.filas.groupby("algoritmo")["part_max"].max()
    fz = bt.filas.groupby("algoritmo")["forzado"].mean()
    for nm in ALGORITMOS:
        if nm in A.index:
            r = A.loc[nm]
            print(f"  {nm:<9}{r['spread']:>9.3f}{r['propio']:>9.3f}{r['transitorio']:>10.3f}{r['permanente']:>9.3f}"
                  f"{r['timing']:>9.3f}   {pm[nm]:>8.1%}  {fz[nm]:>7.0f}")
    print("  El permanente (½·κ_P·X², κ_P = π·f̄/q) es IGUAL para cualquier plan que termine: lo que los distingue es el")
    print("  transitorio (ir rápido lo acumula) contra el riesgo de timing (ir lento lo expone).")
    if len(bt.parametrica):
        P = bt.parametrica
        print(f"\n  Incertidumbre de los parámetros ({len(P)} extracciones de θ ~ N(θ̂, V robusta)), costo − TWAP:")
        for nm in ("VWAP", "AC", "ÓPTIMO"):
            if nm in P:
                d = (P[nm] - P["TWAP"]).to_numpy()
                print(f"     {nm:<7} mediana {np.median(d):+.4f} · 95 % [{np.quantile(d, 0.025):+.4f}, {np.quantile(d, 0.975):+.4f}]"
                      f" · P(más barato) {np.mean(d < 0):.0%}")
    if len(bt.arrepentimiento):
        T = bt.arrepentimiento.pivot(index="modelo", columns="algoritmo", values="arrepentimiento")
        cols = [c for c in ALGORITMOS if c in T.columns]
        print("\n  Arrepentimiento si la verdad es otra (E + λ·Var en ticks por contrato, sobre el óptimo de ESE modelo):")
        print(f"  {'':<26}" + "".join(f"{c:>9}" for c in cols))
        for nm_m, f in T.iterrows():
            print(f"  {nm_m:<26}" + "".join(_fmt(f[c], 3, 9) for c in cols))
    if np.isfinite(bt.pico.get("razon", np.nan)):
        print(f"\n  Impacto pico de la orden: {bt.pico['pico']:.1f} ticks · ley de raíz cuadrada {bt.pico['raiz']:.1f} ticks "
              f"(razón {bt.pico['razon']:.2f})")


def reporte_objetivo(res: Resultado) -> None:
    bt, cfg = res.bt, res.cfg
    if not bt.detalle:
        return
    X = float(cfg.orden)
    fecha_r = f"{fecha_de_dia(bt.mercado.dia):%Y-%m-%d}"
    _titulo(f"5 · LA SESIÓN OBJETIVO ({fecha_r}) · {_lado_txt(cfg)} de {cfg.orden:,} · réplica clip a clip")
    if bt.mercado.dia != dia_objetivo(cfg):
        print(f"  ⚠ La sesión pedida ({cfg.sesion_objetivo}) no se pudo replicar: se muestra la última que sí.")
    print(f"  Precio de llegada {bt.real.mid[0] * tick(cfg.symbol):,.2f} · final {bt.real.mid_fin * tick(cfg.symbol):,.2f} · "
          "IS = lado·(precio medio − llegada)")
    print(f"  {'algoritmo':<9}{'IS t/c':>8}{'IS bps':>8}{'en US$':>13}{'vs VWAP':>9}{'vs VWAP*':>10}{'timing':>9}{'modelo':>9}{'z':>7}")
    for nm in ALGORITMOS:
        r = bt.detalle.get(nm)
        if r is None:
            continue
        print(f"  {nm:<9}{r['is_por_contrato']:>8.2f}{r['is_bps']:>8.2f}{_usd(r['is_por_contrato'], cfg):>13}"
              f"{r['vs_vwap']:>9.2f}{r['vs_vwap_cf']:>10.2f}{r['timing'] / X:>9.2f}{r['costo_modelo'] / X:>9.2f}{_fmt(r['z_timing'], 2, 7)}")
    print("  vs VWAP* = contra el VWAP del mercado CON nuestra orden dentro (el benchmark que de verdad se habría")
    print("  visto) · timing = lo que movió el mercado (real) · modelo = spread + impacto propio (calibrado)")
    print("  Un solo día lo decide el timing: ver la tabla del walk-forward para elegir.")


def reporte_plan(res: Resultado) -> None:
    P, info, cfg = res.plan, res.plan_info, res.cfg
    if not len(P):
        return
    _titulo(f"6 · PLAN DE LA PRÓXIMA SESIÓN ({fecha_de_dia(info['dia']):%Y-%m-%d}) · {_lado_txt(cfg)} de {cfg.orden:,}")
    print(f"  Con A = {info['A']:.4f} · δ {info['p']['delta']:.2f} · π {info['p']['pi']:.2f} · τ {info['p']['tau']:.0f} s · "
          f"volumen esperado del horizonte {info['V_hor']:,.0f} contratos ({cfg.orden / max(info['V_hor'], 1):.2%} de él)")
    print(f"  {'algoritmo':<9}{'costo esp.':>11}{'desv.':>9}{'en US$':>13}")
    for nm, r in info["resumen"].items():
        print(f"  {nm:<9}{r['costo']:>11.3f}{r['sd']:>9.2f}{_usd(r['costo'], cfg):>13}")
    cols = [c for c in ("TWAP", "VWAP", "AC", "ÓPTIMO") if c in P]
    print(f"\n  {'CT':<7}{'CDMX':<7}" + "".join(f"{c:>9}" for c in cols) + "   (contratos por slice; todos en el CSV)")
    idx = list(range(min(6, len(P)))) + ([-1] if len(P) > 6 else [])
    for i in idx:
        f = P.iloc[i]
        if i == -1:
            print("  …")
        print(f"  {f['hora_ct']:<7}{f['hora_cdmx']:<7}" + "".join(f"{f[c]:>9.0f}" for c in cols))


def reporte_cordura(res: Resultado) -> None:
    _titulo("CHEQUEO DE CORDURA")
    for ok, txt in res.cordura:
        print(f"  {'✓' if ok else '⚠'} {txt}")


def reporte_verdad(res: Resultado) -> None:
    md = res.medicion
    if not md:
        return
    _titulo("CONTRA LA VERDAD DE LA SIMULACIÓN")
    P = md["params"]
    print(f"  {'modelo':<12}{'parámetro':<24}{'estimado':>10}{'EE':>9}{'verdad':>9}{'z':>7}")
    for _, f in P.iterrows():
        print(f"  {f['modelo']:<12}{f['parametro']:<24}{f['estimado']:>10.3f}{_fmt(f['ee'], 3, 9)}{f['verdad']:>9.3f}{_fmt(f['z'], 2, 7)}")
    if "costos" in md:
        print("\n  Sesión objetivo: costo esperado de cada plan con el modelo estimado y con el VERDADERO (t/c):")
        for _, f in md["costos"].iterrows():
            print(f"     {f['algoritmo']:<8} modelo {f['costo_modelo']:8.3f} · verdad {f['costo_verdad']:8.3f} · "
                  f"arrepentimiento (E + λ·Var) {f['arrepentimiento']:+.4f}")


# =============================================================================
# 11. DASHBOARD — tablero CUÁDRUPLE y tablero de AUDITORÍA
# =============================================================================
C = {"fondo": "#fcfcfb", "tinta": "#0b0b0b", "tinta2": "#52514e", "tenue": "#898781",
     "grid": "#e1e0d9", "eje": "#c3c2b7", "neutro": "#d6d5ce",
     "s1": "#2a78d6", "s2": "#eb6834", "s3": "#1baf7a", "s4": "#eda100", "s5": "#e87ba4",
     "s6": "#008300", "s7": "#4a3aa7", "s8": "#e34948",
     "alza": "#256abf", "baja": "#e34948"}
COMPRA, VENTA = C["s1"], C["baja"]


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



COLOR_ALGO = {"TWAP": C["tenue"], "VWAP": C["s3"], "POV": C["s4"], "POV*": C["s5"], "AC": C["s7"], "ÓPTIMO": C["s2"]}
ETIQUETA_MODELO = {"respuesta": "respuesta (δ libre)", "propagador": "propagador", "raiz": "raíz (δ = 0.5)",
                   "lineal": "lineal (δ = 1)", "t": "respuesta, errores t"}
ESTILO_ALGO = {"TWAP": "-", "VWAP": "-", "POV": "--", "POV*": ":", "AC": "-", "ÓPTIMO": "-"}


def _cdf_chi2(x: np.ndarray, k: np.ndarray) -> np.ndarray:
    """F de una χ² con k gl (gamma incompleta regularizada; scipy si está, serie/fracción continua si no)."""
    try:
        from scipy.special import gammainc
        return gammainc(np.asarray(k, float) / 2, np.asarray(x, float) / 2)
    except Exception:
        pass
    out = np.empty(len(x))
    for i, (xx, kk) in enumerate(zip(np.asarray(x, float) / 2, np.asarray(k, float) / 2)):
        if xx <= 0:
            out[i] = 0.0
            continue
        lg = kk * math.log(xx) - xx - math.lgamma(kk)
        if xx < kk + 1:                                   # serie
            s = t = 1.0 / kk
            a = kk
            for _ in range(500):
                a += 1
                t *= xx / a
                s += t
                if abs(t) < abs(s) * 1e-14:
                    break
            out[i] = s * math.exp(lg)
        else:                                             # fracción continua (Lentz)
            b, c, d = xx + 1 - kk, 1e300, 1.0 / (xx + 1 - kk)
            h = d
            for n in range(1, 500):
                an = -n * (n - kk)
                b += 2
                d = an * d + b
                d = 1.0 / (d if abs(d) > 1e-300 else 1e-300)
                c = b + an / c
                c = c if abs(c) > 1e-300 else 1e-300
                h *= d * c
                if abs(d * c - 1) < 1e-14:
                    break
            out[i] = 1.0 - h * math.exp(lg)
    return out


def _eje_horas(ax, t0_ns: int, minutos: int, cfg: Config, n: int = 7) -> None:
    pos = np.linspace(0, minutos, n).round().astype(int)
    idx = a_indice(t0_ns + pos.astype(np.int64) * NS_MIN)
    ax.set_xticks(pos)
    ax.set_xticklabels([f"{a:%H:%M}\n{b:%H:%M}" for a, b in zip(idx.tz_convert(cfg.tz_mercado), idx.tz_convert(cfg.tz_local))],
                       fontsize=7.5)
    ax.set_xlim(0, minutos)


def _sin_datos(ax, texto: str) -> None:
    ax.text(0.5, 0.5, texto, ha="center", va="center", color=C["tenue"], fontsize=9, transform=ax.transAxes, wrap=True)
    ax.set_xticks([])
    ax.set_yticks([])


def panel_precio(res: Resultado, ax, axv) -> None:
    """(a) La sesión objetivo: mid, VWAP del mercado, las grandes institucionales y nuestras ejecuciones."""
    cfg, bt = res.cfg, res.bt
    mer, real = bt.mercado, bt.real
    tk = tick(cfg.symbol)
    if mer is None or real is None:
        _sin_datos(ax, "sin sesión objetivo en el backtest")
        _sin_datos(axv, "")
        return
    n_min = len(real.vol_min)
    m0 = mer.t0 // NS_MIN
    b = res.barras.reindex(np.arange(m0, m0 + n_min))
    x = np.arange(n_min) + 0.5
    mid = b["mid"].to_numpy(dtype=float) * tk
    _estilo(ax, f"(a) {fecha_de_dia(mer.dia):%Y-%m-%d} · precio, grandes institucionales y ejecución del ÓPTIMO "
                f"({_lado_txt(cfg)} {cfg.orden:,})")
    ax.plot(x, mid, color=C["tinta2"], linewidth=0.9, label="mid", zorder=2)
    v = real.vol_min
    vw = np.where(np.isfinite(real.vwap_min), real.vwap_min, np.nan)
    cv = np.nancumsum(np.where(np.isfinite(vw), v * vw, 0.0)) / np.maximum(np.cumsum(np.where(np.isfinite(vw), v, 0.0)), 1e-9)
    ax.plot(x, cv * tk, color=C["s3"], linewidth=1.2, label="VWAP del mercado (acumulado)", zorder=3)
    ax.axhline(real.mid[0] * tk, color=C["tinta"], linewidth=0.8, linestyle="--", label="precio de llegada", zorder=1)
    det = bt.detalle.get("ÓPTIMO")
    if det is not None:
        u = bt.planes["ÓPTIMO"]
        pc = det["precio"] * tk
        xc = (mer.t_clip - mer.t0) / NS_MIN
        acum = np.cumsum(u * pc) / np.maximum(np.cumsum(u), 1e-9)
        ok = np.cumsum(u) > 0
        ax.plot(xc[ok], acum[ok], color=COLOR_ALGO["ÓPTIMO"], linewidth=1.6, label="precio medio ejecutado (ÓPTIMO)", zorder=4)
    # las grandes del día en el horizonte
    H = res.H
    g = H[(H["sesion"] == mer.dia) & (H["clase"] >= 1) & (H["t_ini"] >= mer.t0) & (H["t_ini"] < mer.t1)]
    if len(g):
        xg = (g["t_ini"].to_numpy() - mer.t0) / NS_MIN
        yg = g["vwap"].to_numpy(dtype=float) * tk
        q = g["vol"].to_numpy(dtype=float)
        tam = 6 + 220 * (q / q.max()) ** 0.8
        col = np.where(g["lado"].to_numpy() > 0, COMPRA, VENTA)
        borde = np.where(g["clase"].to_numpy() >= 2, C["tinta"], "none")
        ax.scatter(xg, yg, s=tam, c=col, alpha=0.45, edgecolors=borde, linewidths=0.6, zorder=5)
        from matplotlib.lines import Line2D
        extra = [Line2D([], [], marker="o", linestyle="", color=COMPRA, alpha=0.6, label="grande COMPRA (área ∝ contratos)"),
                 Line2D([], [], marker="o", linestyle="", color=VENTA, alpha=0.6, label="grande VENTA"),
                 Line2D([], [], marker="o", linestyle="", markerfacecolor="none", markeredgecolor=C["tinta"], label="MEGA o BALLENA")]
        h_, l_ = ax.get_legend_handles_labels()
        ax.legend(handles=h_ + extra, fontsize=7, frameon=True, facecolor=C["fondo"], edgecolor="none", framealpha=0.9,
                  labelcolor=C["tinta2"], loc="upper left", ncol=2)
    else:
        _leyenda(ax, ncol=2)
    ax.set_ylabel(f"precio ({cfg.symbol})", color=C["tinta2"], fontsize=8)
    ax.set_xlim(0, n_min)
    ax.tick_params(labelbottom=False)
    # volumen del mercado y el nuestro
    _estilo(axv)
    axv.bar(x, v, width=1.0, color=C["neutro"], label="volumen del mercado")
    if det is not None:
        clips_min = max(1, int(round(60.0 / mer.clip_s)))
        nuestro = np.add.reduceat(bt.planes["ÓPTIMO"], np.arange(0, mer.C, clips_min))[:n_min]
        axv.bar(x[:len(nuestro)], nuestro, width=1.0, color=COLOR_ALGO["ÓPTIMO"], label="nuestra orden (ÓPTIMO)")
        axv.text(0.01, 0.92, f"nuestra orden = {bt.planes['ÓPTIMO'].sum() / max(v.sum() + bt.planes['ÓPTIMO'].sum(), 1):.1%} "
                 "del volumen del horizonte", transform=axv.transAxes, fontsize=7.5, color=C["tinta2"], va="top")
    axv.set_ylabel("contratos/min", color=C["tinta2"], fontsize=8)
    _leyenda(axv, ncol=2, loc="upper right")
    _eje_horas(axv, mer.t0, n_min, cfg)


def panel_ajuste(res: Resultado, ax_q, ax_h) -> None:
    """(b) MLE: el impacto inicial contra el tamaño y su decaimiento contra el horizonte."""
    obs = res.obs
    aj = res.ajustes["respuesta"]
    K = obs.K
    _estilo(ax_q, "(b) Ajuste MLE · impacto inicial vs tamaño del print (modelo en los mismos eventos)")
    x = K["x"].to_numpy()
    y = K["lado"].to_numpy() * obs.dm[:, 0] / K["sig5"].to_numpy()
    ok = np.isfinite(x) & np.isfinite(y) & (x > 0)
    bordes = np.unique(np.quantile(x[ok], np.linspace(0, 1, 11)))
    cb = np.clip(np.searchsorted(bordes, x, side="right") - 1, 0, len(bordes) - 2)
    ses = K["sesion"].to_numpy()
    xm, ym, ye, bins = [], [], [], []
    for j in range(len(bordes) - 1):
        m = ok & (cb == j)
        if m.sum() < 20:
            continue
        r = media_sesiones(y[m], ses[m])
        xm.append(float(np.exp(np.mean(np.log(x[m])))))
        ym.append(r["media"])
        ye.append(r["media"] - r["ic_bajo"] if np.isfinite(r["ic_bajo"]) else 0.0)
        bins.append(m)
    if xm:
        ax_q.errorbar(xm, ym, yerr=ye, fmt="o", color=C["tinta"], markersize=4, capsize=2, linewidth=0.9,
                      label="empírico (media ± IC por sesión)", zorder=4)
    # el modelo, evaluado en los MISMOS eventos de cada bin: A·Σₑ((qₑ/V₅)/x_ref)^δ·G(e'₀)
    for nm, col, ls in (("respuesta", C["s2"], "-"), ("raiz", C["s1"], "--"), ("lineal", C["s7"], ":")):
        a = res.ajustes.get(nm)
        if a is None or not bins:
            continue
        pred = (a.A * base_huella(obs.qe, obs.ptr, np.ones(obs.n), K["v5"].to_numpy(), a.p["delta"], a.x_ref)
                * kernel(obs.e1[:, 0], a.p["pi"], a.p["tau"]))
        ax_q.plot(xm, [float(np.nanmean(pred[m])) for m in bins], color=col, linestyle=ls, linewidth=1.4, marker=".",
                  label=f"{a.esp.nombre.split('(')[0].strip()} δ = {a.p['delta']:.2f}")
    ax_q.set_xscale("log")
    ax_q.axhline(0, color=C["eje"], linewidth=0.8)
    ax_q.set_xlabel("Q / V₅ (participación del print en 5 min)", color=C["tinta2"], fontsize=8)
    ax_q.set_ylabel("lado·Δmid(0) / σ₅", color=C["tinta2"], fontsize=8)
    txt = [f"A = {aj.A:.4f} ± {aj.se.get('A', np.nan):.4f}"]
    for k in ("delta", "pi", "tau"):
        dec = 0 if k == "tau" else 2
        txt.append(f"{NOMBRE_PAR[k]} = {aj.p[k]:.{dec}f} ± {aj.se.get(k, np.nan):.{dec}f}")
    txt.append(f"{obs.n:,} eventos · {aj.sesiones} sesiones")
    ax_q.text(0.98, 0.04, "\n".join(txt), transform=ax_q.transAxes, ha="right", va="bottom", fontsize=7.5, color=C["tinta2"],
              bbox=dict(facecolor=C["fondo"], edgecolor=C["grid"], boxstyle="round,pad=0.4"))
    _leyenda(ax_q, fontsize=7)
    # decaimiento
    _estilo(ax_h, "decaimiento: g(h) sin forma funcional vs G(h) ajustado")
    Cv = res.curva
    h = Cv["h"].to_numpy(dtype=float)
    ax_h.fill_between(h, Cv["ic_bajo"], Cv["ic_alto"], color=C["neutro"], alpha=0.6, linewidth=0, label="IC 95 % (por sesión)")
    ax_h.plot(h, Cv["g"], "o", color=C["tinta"], markersize=4, label="g(h) semiparamétrica", zorder=4)
    hs = np.r_[0, np.geomspace(0.5, max(h.max(), 1), 120)]
    for nm, col, ls in (("respuesta", C["s2"], "-"), ("propagador", C["s1"], "--")):
        a = res.ajustes.get(nm)
        if a is not None:
            ax_h.plot(hs, kernel(hs, a.p["pi"], a.p["tau"]), color=col, linestyle=ls, linewidth=1.4,
                      label=f"{nm}: π {a.p['pi']:.2f} · τ {a.p['tau']:.0f} s")
    ax_h.axhline(1, color=C["eje"], linewidth=0.8)
    ax_h.axhline(0, color=C["eje"], linewidth=0.8)
    ax_h.set_xscale("symlog", linthresh=5)
    ax_h.set_xlim(0, max(h.max(), 1) * 1.15)
    ax_h.set_xticks([t for t in (0, 5, 15, 30, 60, 120, 300, 600, 1800) if t <= h.max()])
    ax_h.set_xticklabels([f"{t}" for t in (0, 5, 15, 30, 60, 120, 300, 600, 1800) if t <= h.max()], fontsize=7.5)
    ax_h.set_ylim(-0.4, 1.5)
    ax_h.set_xlabel("segundos desde el final del print", color=C["tinta2"], fontsize=8)
    ax_h.set_ylabel("fracción del impacto inicial que queda", color=C["tinta2"], fontsize=8)
    _leyenda(ax_h, fontsize=7, loc="upper right")


def panel_rolling(res: Resultado, axA, axP, axT) -> None:
    """(c) El rolling: A con su IC por sesión, y δ, π, τ expansivos."""
    R = res.roll.tabla
    _estilo(axA, f"(c) Rolling · A con las últimas {res.cfg.ventana_sesiones} sesiones (IC 95 %), δ π τ con todas las anteriores")
    if not len(R):
        for a in (axA, axP, axT):
            _sin_datos(a, "sin sesiones suficientes para el rolling")
        return
    xi = np.arange(len(R))
    fut = R["siguiente"].to_numpy(bool)
    axA.fill_between(xi, R["A_lo"], R["A_hi"], color=C["s1"], alpha=0.18, linewidth=0)
    axA.plot(xi, R["A"], "-o", color=C["s1"], markersize=4, linewidth=1.3, label="A rolling (GLS, demás fijos)")
    axA.plot(xi[fut], R["A"].to_numpy()[fut], "o", markersize=7, markerfacecolor=C["fondo"], markeredgecolor=C["s1"],
             label="próxima sesión (plan)")
    axA.axhline(res.ajustes[res.cfg.modelo_ejecucion].A, color=C["tinta2"], linewidth=0.8, linestyle="--",
                label="muestra completa")
    e = res.roll.estabilidad
    if np.isfinite(e.get("p", np.nan)):
        axA.text(0.99, 0.95, f"Nyblom p = {e['p']:.3f}", transform=axA.transAxes, ha="right", va="top", fontsize=7.5,
                 color=C["tinta2"])
    axA.set_ylabel("A", color=C["tinta2"], fontsize=8)
    _leyenda(axA, fontsize=7, ncol=3)
    axA.tick_params(labelbottom=False)
    _estilo(axP)
    axP.plot(xi, R["delta"], "-o", color=C["s2"], markersize=3, linewidth=1.2, label="δ")
    axP.plot(xi, R["pi"], "-s", color=C["s7"], markersize=3, linewidth=1.2, label="π")
    if res.verdad:
        axP.axhline(res.verdad["delta"], color=C["s2"], linewidth=0.7, linestyle=":")
        axP.axhline(res.verdad["pi"], color=C["s7"], linewidth=0.7, linestyle=":")
    axP.set_ylabel("δ, π", color=C["tinta2"], fontsize=8)
    _leyenda(axP, fontsize=7, ncol=2)
    axP.tick_params(labelbottom=False)
    _estilo(axT)
    axT.plot(xi, R["tau"], "-o", color=C["s3"], markersize=3, linewidth=1.2, label="τ (s)")
    if res.verdad:
        axT.axhline(res.verdad["tau"], color=C["s3"], linewidth=0.7, linestyle=":", label="verdad (simulación)")
    axT.set_ylabel("τ (s)", color=C["tinta2"], fontsize=8)
    _leyenda(axT, fontsize=7, ncol=2)
    axT.set_xticks(xi)
    axT.set_xticklabels([f"{fecha_de_dia(int(s)):%m-%d}" + ("*" if f else "") for s, f in zip(R["sesion"], fut)], fontsize=7.5)


def panel_inventario(res: Resultado, ax, axc) -> None:
    """(d) Inventario restante de cada algoritmo en la sesión objetivo y el costo del walk-forward contra TWAP."""
    bt, cfg = res.bt, res.cfg
    X = float(cfg.orden)
    _estilo(ax, "(d) Inventario restante en la sesión objetivo")
    if bt.mercado is None:
        _sin_datos(ax, "sin sesión objetivo")
        _sin_datos(axc, "")
        return
    mer = bt.mercado
    xc = np.r_[(mer.t_clip - mer.t0) / NS_MIN, (mer.t1 - mer.t0) / NS_MIN]
    for nm in ALGORITMOS:
        u = bt.planes.get(nm)
        if u is None:
            continue
        resto = np.r_[X, X - np.cumsum(u)] / X
        ax.step(xc, resto, where="post", color=COLOR_ALGO[nm], linestyle=ESTILO_ALGO[nm],
                linewidth=1.8 if nm == "ÓPTIMO" else 1.2, label=nm)
    ax.set_ylim(-0.02, 1.02)
    ax.set_ylabel("fracción de la orden que falta", color=C["tinta2"], fontsize=8)
    _eje_horas(ax, mer.t0, int(round(xc[-1])), cfg, n=6)
    _leyenda(ax, fontsize=7, loc="upper right")
    # costo contra TWAP en el walk-forward, con IC pareado
    _estilo(axc, "walk-forward: costo − TWAP (t/c, IC 95 %)")
    Cm = bt.comparacion.set_index("algoritmo") if len(bt.comparacion) else pd.DataFrame()
    nombres = [nm for nm in ALGORITMOS if nm in Cm.index and nm != "TWAP"]
    if not nombres:
        _sin_datos(axc, "sin walk-forward")
        return
    yy = np.arange(len(nombres))[::-1]
    c = bt.filas.groupby(["sesion", "algoritmo"])["is_por_contrato"].mean().unstack()
    for y_, nm in zip(yy, nombres):
        d = (c[nm] - c["TWAP"]).dropna().to_numpy()
        n = len(d)
        m_ = float(d.mean()) if n else np.nan
        ic = t_cuantil(0.975, n - 1) * d.std(ddof=1) / math.sqrt(n) if n > 1 else np.nan
        axc.errorbar([m_], [y_], xerr=[[ic], [ic]] if np.isfinite(ic) else None, fmt="o", color=COLOR_ALGO[nm],
                     markersize=6, capsize=3, linewidth=1.4)
        f = Cm.loc[nm]
        axc.text(1.02, y_, f"{f['veredicto'].replace(', ', chr(10))}\nriesgo {f['riesgo']:.0f}", transform=axc.get_yaxis_transform(),
                 fontsize=6.8, color=C["tinta2"], va="center")
    axc.axvline(0, color=C["tinta2"], linewidth=0.9)
    axc.set_yticks(yy)
    axc.set_yticklabels(nombres, fontsize=8)
    axc.set_xlabel(f"ticks por contrato · TWAP = {Cm.loc['TWAP', 'costo']:.2f} ({_usd(Cm.loc['TWAP', 'costo'], cfg)})",
                   color=C["tinta2"], fontsize=7.5)


def tablero_cuadruple(res: Resultado, plt, ruta: Path):
    cfg = res.cfg
    fig = plt.figure(figsize=(21, 12.5), facecolor=C["fondo"])
    gs = fig.add_gridspec(2, 2, hspace=0.30, wspace=0.16, left=0.045, right=0.955, top=0.895, bottom=0.06)
    ga = gs[0, 0].subgridspec(2, 1, height_ratios=[3, 1], hspace=0.06)
    ax_p = fig.add_subplot(ga[0])
    ax_v = fig.add_subplot(ga[1], sharex=ax_p)
    panel_precio(res, ax_p, ax_v)
    gb = gs[0, 1].subgridspec(1, 2, wspace=0.25)
    panel_ajuste(res, fig.add_subplot(gb[0]), fig.add_subplot(gb[1]))
    gc = gs[1, 0].subgridspec(3, 1, height_ratios=[2, 1, 1], hspace=0.08)
    a1 = fig.add_subplot(gc[0])
    panel_rolling(res, a1, fig.add_subplot(gc[1], sharex=a1), fig.add_subplot(gc[2], sharex=a1))
    gd = gs[1, 1].subgridspec(1, 2, width_ratios=[1.45, 1], wspace=0.22)
    panel_inventario(res, fig.add_subplot(gd[0]), fig.add_subplot(gd[1]))
    aj = res.ajustes[cfg.modelo_ejecucion]
    fig.suptitle(f"Optimal Execution · {cfg.symbol} ({nombre(cfg.symbol)}) · {_lado_txt(cfg)} de {cfg.orden:,} contratos · "
                 f"{cfg.inicio_ct}-{cfg.fin_ct} CT", x=0.045, ha="left", fontsize=15, color=C["tinta"], y=0.975)
    fig.text(0.045, 0.937, f"Modelo de ejecución ({cfg.modelo_ejecucion}): impacto ∝ (Q/V₅)^{aj.p['delta']:.2f} · "
             f"{aj.p['pi']:.0%} permanente · τ ≈ {aj.p['tau']:.0f} s · "
             f"{res.obs.n:,} eventos clave en {aj.sesiones} sesiones · walk-forward de {res.info['sesiones_prueba']} sesiones · "
             f"{'SIMULACIÓN (verdad conocida)' if res.verdad else 'datos de Databento GLBX.MDP3'}",
             fontsize=9.5, color=C["tinta2"])
    fig.savefig(ruta, dpi=110, facecolor=C["fondo"])
    return fig


def tablero_auditoria(res: Resultado, plt, ruta: Path):
    cfg, bt = res.cfg, res.bt
    X = float(cfg.orden)
    fig = plt.figure(figsize=(22, 13.5), facecolor=C["fondo"])
    gs = fig.add_gridspec(3, 4, hspace=0.42, wspace=0.26, left=0.04, right=0.985, top=0.92, bottom=0.05)
    ax = [[fig.add_subplot(gs[i, j]) for j in range(4)] for i in range(3)]
    # 1. perfil de δ
    a = ax[0][0]
    _estilo(a, "Perfil de verosimilitud de δ (LR escalado)")
    if len(res.perfil):
        P = res.perfil
        tope = max(4 * P.attrs["umbral"], 1)
        vis = P[P["lr"] <= 3 * tope]
        a.plot(vis["delta"], vis["lr"], "-o", color=C["s2"], markersize=4, linewidth=1.3)
        a.axhline(P.attrs["umbral"], color=C["tinta2"], linestyle="--", linewidth=0.9, label=f"umbral 95 % (ĉ = {P.attrs['c']:.2f})")
        if vis["delta"].min() <= 0.5 <= vis["delta"].max():
            a.axvline(0.5, color=C["s1"], linewidth=0.8, linestyle=":", label="raíz cuadrada")
        lo, hi = P.attrs.get("ic", (np.nan, np.nan))
        if np.isfinite(lo) and np.isfinite(hi):
            a.axvspan(lo, hi, color=C["s2"], alpha=0.10, linewidth=0, label=f"IC 95 % [{lo:.3f}, {hi:.3f}]")
        lr1 = P.loc[np.isclose(P["delta"], 1.0), "lr"]
        if len(lr1) and lr1.iloc[0] > 3 * tope:
            a.text(0.98, 0.04, f"δ = 1 (lineal): LR = {lr1.iloc[0]:,.0f}", transform=a.transAxes, ha="right", fontsize=7.5,
                   color=C["tinta2"])
        a.set_ylim(0, tope)
        a.set_xlabel("δ", color=C["tinta2"], fontsize=8)
        _leyenda(a, fontsize=7, loc="upper center")
    else:
        _sin_datos(a, "perfil omitido (--rapido)")
    # 2. QQ de las distancias de Mahalanobis (PIT de la χ²)
    a = ax[0][1]
    _estilo(a, "¿Cuadra la covarianza? PIT de la distancia de Mahalanobis")
    aj = res.ajustes["respuesta"]
    vero = Verosimilitud(res.obs, aj.esp, aj.x_ref)
    d2, kk = vero.mahalanobis(aj.p, aj.A)
    u = np.sort(_cdf_chi2(d2, kk))
    q = (np.arange(1, len(u) + 1) - 0.5) / len(u)
    a.plot(q, u, color=C["s1"], linewidth=1.5, label="gaussiana (QMLE)")
    a.plot([0, 1], [0, 1], color=C["tinta2"], linewidth=0.8, linestyle="--")
    a.set_xlabel("cuantil teórico", color=C["tinta2"], fontsize=8)
    a.set_ylabel("PIT observado", color=C["tinta2"], fontsize=8)
    a.text(0.98, 0.04, f"colas: {np.mean(u > 0.99):.1%} de los eventos > p99\n(1 % si la covarianza es exacta)",
           transform=a.transAxes, ha="right", va="bottom", fontsize=7.5, color=C["tinta2"])
    _leyenda(a, fontsize=7)
    # 3. comparación de modelos
    a = ax[0][2]
    _estilo(a, "Comparación de modelos: ΔCLAIC (menor es mejor)")
    nm_ = [nm for nm, x in res.ajustes.items() if np.isfinite(x.claic)]
    if nm_:
        best = min(res.ajustes[n].claic for n in nm_)
        vals = [res.ajustes[n].claic - best for n in nm_]
        yy = np.arange(len(nm_))[::-1]
        a.barh(yy, vals, color=[C["s2"] if v == 0 else C["neutro"] for v in vals], height=0.6)
        for y_, v, n in zip(yy, vals, nm_):
            a.text(v, y_, f" {v:,.0f}", va="center", fontsize=7.5, color=C["tinta2"])
        a.set_yticks(yy)
        a.set_yticklabels([ETIQUETA_MODELO.get(n, n) for n in nm_], fontsize=7.5)
        t1, p1 = prueba_wald(aj, "delta", 0.5)
        a.set_xlabel(f"Wald δ = 0.5: p = {p1:.3f} · sin decaimiento (15-60 s): p = {res.permanente[2]:.3f}",
                     color=C["tinta2"], fontsize=7.5)
    # 4. A por hora
    a = ax[0][3]
    _estilo(a, "A por hora del día (los demás fijos)")
    ph = res.roll.por_hora
    if len(ph):
        a.errorbar(ph["hora"], ph["A"], yerr=[ph["A"] - ph["lo"], ph["hi"] - ph["A"]], fmt="o-", color=C["s1"],
                   markersize=4, capsize=2, linewidth=1.1)
        a.axhline(res.ajustes[cfg.modelo_ejecucion].A, color=C["tinta2"], linestyle="--", linewidth=0.8)
        a.set_xlabel("hora (CT)", color=C["tinta2"], fontsize=8)
    else:
        _sin_datos(a, "pocos eventos por hora")
    # 5. frontera
    a = ax[1][0]
    _estilo(a, "Frontera eficiente del modelo (sesión objetivo)")
    fr = bt.frontera
    if len(fr):
        f1 = fr[fr["tipo"] == "frontera"]
        a.plot(f1["sd"], f1["E"], "-", color=C["tinta2"], linewidth=1.2, label="ÓPTIMO para cada urgencia κT")
        for _, f in f1.iterrows():
            a.annotate(f["nombre"], (f["sd"], f["E"]), fontsize=6.5, color=C["tenue"], xytext=(3, 3), textcoords="offset points")
        for _, f in fr[fr["tipo"] == "algoritmo"].iterrows():
            a.plot(f["sd"], f["E"], "o", color=COLOR_ALGO.get(f["nombre"], C["tinta"]), markersize=7, label=f["nombre"])
        a.set_xlabel("desviación del costo por timing (t/c)", color=C["tinta2"], fontsize=8)
        a.set_ylabel("costo esperado (t/c)", color=C["tinta2"], fontsize=8)
        _leyenda(a, fontsize=6.8, loc="upper right")
    # 6. IS por sesión (un lado: con timing real)
    a = ax[1][1]
    _estilo(a, f"IS de cada sesión ({_lado_txt(cfg)}, con el timing real)")
    F = bt.filas
    if len(F):
        Fl = F[F["lado"] == cfg.lado]
        for i, nm in enumerate(ALGORITMOS):
            v = Fl.loc[Fl["algoritmo"] == nm, "is_por_contrato"].to_numpy()
            if not len(v):
                continue
            jit = (np.random.default_rng(i).random(len(v)) - 0.5) * 0.3
            a.plot(i + jit, v, "o", color=COLOR_ALGO[nm], markersize=4, alpha=0.75)
            a.plot([i - 0.25, i + 0.25], [np.mean(v)] * 2, color=C["tinta"], linewidth=1.5)
        a.set_xticks(range(len(ALGORITMOS)))
        a.set_xticklabels(ALGORITMOS, fontsize=7.5)
        a.set_ylabel("ticks por contrato", color=C["tinta2"], fontsize=8)
        a.axhline(0, color=C["eje"], linewidth=0.8)
    # 7. atribución
    a = ax[1][2]
    _estilo(a, "Atribución del costo (promedio de compra y venta)")
    if len(F):
        comp = ["spread", "propio", "transitorio", "permanente"]
        colc = [C["neutro"], C["s4"], C["s2"], C["s7"]]
        M_ = F.groupby("algoritmo")[comp + ["timing"]].mean().reindex([n for n in ALGORITMOS if n in set(F["algoritmo"])]) / X
        yy = np.arange(len(M_))[::-1]
        izq = np.zeros(len(M_))
        for c_, col in zip(comp, colc):
            a.barh(yy, M_[c_], left=izq, color=col, height=0.6, label=c_)
            izq += M_[c_].to_numpy()
        for y_, tot in zip(yy, izq):
            a.text(tot, y_, f" {tot:.2f}", va="center", fontsize=7.5, color=C["tinta2"])
        a.set_yticks(yy)
        a.set_yticklabels(M_.index, fontsize=8)
        a.set_xlabel("ticks por contrato", color=C["tinta2"], fontsize=8)
        _leyenda(a, fontsize=6.8, loc="upper center", ncol=4, bbox_to_anchor=(0.5, -0.17))
    # 8. incertidumbre paramétrica
    a = ax[1][3]
    _estilo(a, "Incertidumbre de θ: costo − TWAP (t/c)")
    P = bt.parametrica
    if len(P):
        nms = [n for n in ("VWAP", "AC", "ÓPTIMO") if n in P]
        datos = [(P[n] - P["TWAP"]).to_numpy() for n in nms]
        bp = a.boxplot(datos, vert=False, widths=0.5, patch_artist=True, showfliers=False)
        for patch, n in zip(bp["boxes"], nms):
            patch.set_facecolor(COLOR_ALGO[n])
            patch.set_alpha(0.5)
        a.set_yticks(range(1, len(nms) + 1))
        a.set_yticklabels(nms, fontsize=8)
        a.axvline(0, color=C["tinta2"], linewidth=0.9)
    else:
        _sin_datos(a, "omitido (--rapido o sin covarianza robusta)")
    # 9. perfil de volumen
    a = ax[2][0]
    _estilo(a, "Perfil de volumen: pronóstico vs realizado (por slice)")
    if bt.mercado is not None and bt.real is not None:
        mer, real = bt.mercado, bt.real
        n_sl = mer.N
        vr = real.vol_min[:n_sl * cfg.slice_min].reshape(n_sl, -1).sum(axis=1) if len(real.vol_min) >= n_sl * cfg.slice_min else None
        xs = np.arange(n_sl) * cfg.slice_min
        a.plot(xs, mer.w * 100, color=C["s1"], linewidth=1.5, label="pronóstico (sesiones previas): lo que usa VWAP")
        if vr is not None and vr.sum() > 0:
            a.plot(xs, vr / vr.sum() * 100, color=C["tenue"], linewidth=1.0, label="realizado (tu VWAP lo usaba: futuro)")
        a.set_ylabel("% del volumen del horizonte", color=C["tinta2"], fontsize=8)
        _eje_horas(a, mer.t0, n_sl * cfg.slice_min, cfg, n=6)
        _leyenda(a, fontsize=6.8, loc="upper center")
    # 10. arrepentimiento
    a = ax[2][1]
    _estilo(a, "Arrepentimiento si la verdad es otra (E + λ·Var, t/c)")
    Ar = bt.arrepentimiento
    if len(Ar):
        T = Ar.pivot(index="modelo", columns="algoritmo", values="arrepentimiento")
        cols = [c for c in ALGORITMOS if c in T.columns]
        filas = list(dict.fromkeys(Ar["modelo"]))
        T = T.reindex(index=filas, columns=cols)
        a.imshow(T.to_numpy(), aspect="auto", cmap="Oranges", vmin=0)
        for i in range(T.shape[0]):
            for j in range(T.shape[1]):
                v = T.iat[i, j]
                v = 0.0 if abs(v) < 0.005 else v
                a.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=6.8,
                       color=C["fondo"] if v > 0.6 * np.nanmax(T.to_numpy()) else C["tinta"])
        a.set_xticks(range(len(cols)))
        a.set_xticklabels(cols, fontsize=7)
        a.set_yticks(range(len(filas)))
        a.set_yticklabels(filas, fontsize=7)
        a.grid(False)
    # 11. participación por minuto
    a = ax[2][2]
    _estilo(a, "Participación por minuto en la sesión objetivo")
    if bt.mercado is not None and bt.real is not None:
        mer, real = bt.mercado, bt.real
        clips_min = max(1, int(round(60.0 / mer.clip_s)))
        v = real.vol_min
        for nm in ALGORITMOS:
            u = bt.planes.get(nm)
            if u is None:
                continue
            nu = np.add.reduceat(u, np.arange(0, mer.C, clips_min))[:len(v)]
            part = nu / np.maximum(v[:len(nu)] + nu, 1e-9)
            a.plot(np.arange(len(part)), pd.Series(part).rolling(5, min_periods=1).mean() * 100, color=COLOR_ALGO[nm],
                   linestyle=ESTILO_ALGO[nm], linewidth=1.1, label=nm)
        a.axhline(cfg.part_max * 100, color=C["s8"], linewidth=0.9, linestyle="--", label=f"tope {cfg.part_max:.0%}")
        a.set_ylabel("% del volumen (media móvil 5 min)", color=C["tinta2"], fontsize=8)
        _eje_horas(a, mer.t0, len(v), cfg, n=6)
        _leyenda(a, fontsize=6.5, ncol=2, loc="upper right")
    # 12. cordura
    a = ax[2][3]
    a.set_facecolor(C["fondo"])
    a.axis("off")
    a.set_title("Chequeo de cordura", color=C["tinta"], fontsize=10, loc="left", pad=8)
    y = 0.98
    orden_ = sorted(res.cordura, key=lambda c_: c_[0])         # primero las ⚠
    if len(orden_) > 17:
        orden_ = orden_[:16] + [(True, f"… y {len(res.cordura) - 16} más (ver la consola)")]
    for ok, txt in orden_:
        corto = txt if len(txt) <= 70 else txt[:67] + "…"
        a.text(0.0, y, ("✓ " if ok else "⚠ ") + corto, transform=a.transAxes, fontsize=7.2, va="top",
               color=C["s6"] if ok else C["s8"])
        y -= 0.058
    fig.suptitle(f"Auditoría · {cfg.symbol} · modelo de impacto, ejecución y robustez", x=0.04, ha="left", fontsize=15,
                 color=C["tinta"], y=0.975)
    fig.savefig(ruta, dpi=105, facecolor=C["fondo"])
    return fig


def tableros(res: Resultado, mostrar: bool = True) -> tuple[list[Path], object, bool]:
    plt, ventana = _preparar_grafico(mostrar)
    if plt is None:
        return [], None, False
    carpeta = _ruta(res.cfg.salida_dir)
    carpeta.mkdir(parents=True, exist_ok=True)
    rutas = []
    for nombre_, fn in (("cuadruple", tablero_cuadruple), ("auditoria", tablero_auditoria)):
        ruta = carpeta / f"ejecucion_{nombre_}_{raiz(res.cfg.symbol)}.png"
        fig = fn(res, plt, ruta)
        rutas.append(ruta)
        print(f"🖼  {ruta}")
        if not ventana:
            plt.close(fig)
    return rutas, plt, ventana


# =============================================================================
# 12. TELEGRAM — el token y el chat, igual que la key: FUERA del código
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


def mensaje_telegram(res: Resultado, solo_plan: bool = False, limite: int = 4096) -> str:
    """Resumen del modelo, del walk-forward y el PLAN de la próxima sesión (horas CDMX)."""
    esc = html.escape
    cfg, bt, info = res.cfg, res.bt, res.plan_info
    aj = res.ajustes[cfg.modelo_ejecucion]
    lin = [f"<b>{esc(IDENTIFICADOR)}</b> · {esc(cfg.symbol)} · {_lado_txt(cfg)} {cfg.orden:,} · {cfg.inicio_ct}-{cfg.fin_ct} CT"]
    if not solo_plan:
        lin += ["", f"<b>Modelo</b> ({esc(aj.esp.nombre)}): A {aj.A:.4f} · δ {aj.p['delta']:.2f}±{aj.se.get('delta', np.nan):.2f} · "
                f"π {aj.p['pi']:.2f} · τ {aj.p['tau']:.0f} s · {res.obs.n:,} eventos clave"]
        if len(bt.comparacion):
            lin.append(f"<b>Walk-forward</b> ({res.info['sesiones_prueba']} sesiones, t/c):")
            for _, f in bt.comparacion.iterrows():
                lin.append(esc(f"  {f['algoritmo']:<7} {f['costo']:.3f} ({_usd(f['costo'], cfg)}) · riesgo {f['riesgo']:.0f} · {f['veredicto']}"))
        if bt.detalle:
            lin.append(f"<b>Sesión {fecha_de_dia(bt.mercado.dia):%Y-%m-%d}</b> (IS t/c, con el timing real):")
            lin.append(esc("  " + " · ".join(f"{nm} {bt.detalle[nm]['is_por_contrato']:+.2f}" for nm in ALGORITMOS if nm in bt.detalle)))
    if len(res.plan):
        P = res.plan
        r = info["resumen"]["ÓPTIMO"]
        lin += ["", f"<b>Plan {fecha_de_dia(info['dia']):%Y-%m-%d}</b> · ÓPTIMO: costo esperado {r['costo']:.2f} t/c "
                f"({_usd(r['costo'], cfg)}) ± {r['sd']:.0f} de timing"]
        horas = P["hora_cdmx"].to_numpy()
        n = P["ÓPTIMO"].to_numpy()
        # por hora (CDMX), para que quepa
        hh = np.array([h[:2] for h in horas])
        for h in dict.fromkeys(hh):
            m = hh == h
            lin.append(esc(f"  {h}:00 CDMX  {n[m].sum():>6.0f} contratos  ({n[m].sum() / max(n.sum(), 1):.0%})"))
    malos = [t for ok, t in res.cordura if not ok]
    lin.append(f"\nCordura: {len(res.cordura) - len(malos)}/{len(res.cordura)} ✓")
    for t in malos[:3]:
        lin.append(f"⚠ {esc(t)}")
    texto = "\n".join(lin)
    if len(texto) > limite:
        texto = texto[:limite - 20].rsplit("\n", 1)[0] + "\n…"
    return texto


def enviar_telegram(res: Resultado, rutas: list[Path], documentos: bool = False, solo_plan: bool = False) -> bool:
    cred = credenciales_telegram()
    if cred is None:
        return False
    token, chat = cred
    r = llamar_telegram(token, "sendMessage", {"chat_id": chat, "text": mensaje_telegram(res, solo_plan),
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
# 13. GUARDAR
# =============================================================================
def guardar(res: Resultado, solo_plan: bool = False) -> Path:
    cfg, obs, bt = res.cfg, res.obs, res.bt
    carpeta = _ruta(cfg.salida_dir)
    carpeta.mkdir(parents=True, exist_ok=True)
    suf = _nombre_seguro(raiz(cfg.symbol), cfg.sesion_objetivo.replace("-", ""), _lado_txt(cfg).lower(), cfg.orden)
    tk = tick(cfg.symbol)
    if len(res.plan):
        P = res.plan.copy()
        P.insert(0, "fecha", f"{fecha_de_dia(res.plan_info['dia']):%Y-%m-%d}")
        P.insert(1, "lado", _lado_txt(cfg))
        P.insert(2, "orden", cfg.orden)
        P.insert(3, "urgencia", cfg.urgencia)
        P.to_csv(carpeta / f"ejecucion_plan_{_nombre_seguro(raiz(cfg.symbol), P['fecha'].iloc[0].replace('-', ''), _lado_txt(cfg).lower(), cfg.orden)}.csv",
                 index=False)
    if solo_plan:
        print(f"💾 Plan guardado en {carpeta}")
        return carpeta
    K = obs.K.copy()
    idx = a_indice(K["t_ini"].to_numpy())
    K.insert(0, "hora_cdmx", idx.tz_convert(cfg.tz_local).strftime("%Y-%m-%d %H:%M:%S.%f").str[:-3])
    K.insert(0, "hora_ct", idx.tz_convert(cfg.tz_mercado).strftime("%Y-%m-%d %H:%M:%S.%f").str[:-3])
    K["lado_txt"] = np.where(K["lado"] > 0, "COMPRA", "VENTA")
    K["clase_txt"] = [CLASES[int(c)] for c in K["clase"]]
    K["tipo_txt"] = [TIPOS[int(t)] for t in K["tipo"]]
    K["precio_mid0"] = K["mid0"] * tk
    K["precio_vwap"] = K["vwap"] * tk
    for j, h in enumerate(obs.horizontes):
        K[f"dmid_{int(h)}s_ticks_sin_deriva"] = obs.dm[:, j]
    K.to_csv(carpeta / f"ejecucion_eventos_clave_{suf}.csv", index=False)
    filas = []
    for nm, aj in res.ajustes.items():
        for par in ["A"] + list(NO_LINEALES):
            if par == "nu" and aj.esp.dist != "t":
                continue
            v = aj.A if par == "A" else aj.p.get(par, np.nan)
            lo, hi = aj.ic.get(par, (np.nan, np.nan))
            filas.append({"modelo": nm, "descripcion": aj.esp.nombre, "parametro": par, "valor": v,
                          "libre": par == "A" or par in aj.libres, "ee": aj.se.get(par, np.nan), "ee_cr1": aj.se_cr1.get(par, np.nan),
                          "ee_cv3": aj.se_cv3.get(par, np.nan), "ee_hessiano": aj.se_hess.get(par, np.nan), "ic_bajo": lo,
                          "ic_alto": hi, "ll": aj.ll, "claic": aj.claic, "eventos": aj.n, "sesiones": aj.sesiones, "x_ref": aj.x_ref})
    pd.DataFrame(filas).to_csv(carpeta / f"ejecucion_mle_{suf}.csv", index=False)
    res.curva.to_csv(carpeta / f"ejecucion_curva_impacto_{suf}.csv", index=False)
    if len(res.roll.tabla):
        R = res.roll.tabla.copy()
        R.insert(1, "fecha", [f"{fecha_de_dia(int(s)):%Y-%m-%d}" for s in R["sesion"]])
        R.to_csv(carpeta / f"ejecucion_rolling_{suf}.csv", index=False)
    if len(bt.filas):
        F = bt.filas.copy()
        F.insert(1, "fecha", [f"{fecha_de_dia(int(s)):%Y-%m-%d}" for s in F["sesion"]])
        F["is_usd"] = F["is_ticks"] * valor_tick_usd(cfg.symbol)
        F["precio_medio"] = F["precio_medio"] * tk                       # en puntos, como los demás CSV
        F.to_csv(carpeta / f"ejecucion_walkforward_{suf}.csv", index=False)
        bt.comparacion.to_csv(carpeta / f"ejecucion_comparacion_{suf}.csv", index=False)
    if bt.mercado is not None and bt.planes:
        mer = bt.mercado
        idx = a_indice(mer.t_clip)
        O = pd.DataFrame({"fecha": f"{fecha_de_dia(mer.dia):%Y-%m-%d}",
                          "hora_ct": idx.tz_convert(cfg.tz_mercado).strftime("%H:%M:%S"),
                          "hora_cdmx": idx.tz_convert(cfg.tz_local).strftime("%H:%M:%S"),
                          "mid": bt.real.mid * tk, "spread_ticks": bt.real.spread})
        for nm, u in bt.planes.items():
            O[f"contratos_{nm}"] = u
            if nm in bt.detalle:
                O[f"precio_{nm}"] = bt.detalle[nm]["precio"] * tk
        O.to_csv(carpeta / f"ejecucion_sesion_objetivo_{suf}.csv", index=False)
    print(f"💾 Eventos clave, MLE, curva, rolling, walk-forward, sesión objetivo y plan guardados en {carpeta}")
    return carpeta


# =============================================================================
# 14. LÍNEA DE COMANDOS
# =============================================================================
def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Optimal Execution AC v1 — impacto por MLE y ejecución óptima con TBBO")
    p.add_argument("--pruebas", action="store_true", help="pruebas internas (sin red ni datos)")
    p.add_argument("--simulacion", action="store_true", help="mercado simulado con el impacto CONOCIDO (sin red)")
    p.add_argument("--archivo", default=None, help="TBBO local (.dbn / .dbn.zst) en vez de descargar")
    p.add_argument("--archivo-ohlcv", default=None, help="OHLCV-1m local (opcional; si falta, el volumen sale del TBBO)")
    p.add_argument("--rapido", action="store_true", help="sin jackknife, perfil de δ ni incertidumbre paramétrica")
    p.add_argument("--solo-plan", action="store_true", help="sólo el plan de la próxima sesión (rápido, sin tableros)")
    p.add_argument("--sin-tablero", "--sin-grafica", action="store_true", dest="sin_tablero")
    p.add_argument("--sin-ventana", action="store_true")
    p.add_argument("--sin-cache", action="store_true")
    d = p.add_argument_group("datos")
    d.add_argument("--simbolo", default=None)
    d.add_argument("--sesion", default=None, dest="sesion_objetivo", help="sesión que se ejecuta y audita (AAAA-MM-DD)")
    d.add_argument("--calibracion", type=int, default=None, dest="dias_calibracion", help="sesiones TBBO previas (10)")
    d.add_argument("--perfil", type=int, default=None, dest="dias_perfil", help="sesiones OHLCV-1m previas (20)")
    d.add_argument("--esquema", default=None, choices=("tbbo", "mbp-1"))
    d.add_argument("--costo-max", type=float, default=None, dest="costo_max_usd")
    d.add_argument("--salida", default=None, dest="salida_dir")
    e = p.add_argument_group("1 · eventos clave")
    e.add_argument("--rafaga-ms", type=float, default=None, dest="rafaga_ms")
    e.add_argument("--p-grande", type=float, default=None, help="percentil que define un evento clave (0.95)")
    e.add_argument("--franja", default=None, dest="mle_franja", choices=("rth", "todo"))
    e.add_argument("--aislamiento", type=float, default=None, dest="aislamiento_s",
                   help="segundos sin otro evento clave antes (0 = todos)")
    m = p.add_argument_group("2 · MLE")
    m.add_argument("--horizontes", default=None, help='segundos, p. ej. "0,5,15,30,60,120,300,600,1800"')
    m.add_argument("--min-eventos", type=int, default=None)
    r = p.add_argument_group("3 · rolling")
    r.add_argument("--ventana-sesiones", type=int, default=None)
    r.add_argument("--modelo-ejecucion", default=None, choices=("propagador", "respuesta"))
    r.add_argument("--n-param", type=int, default=None, help="extracciones de θ para la incertidumbre del costo (100)")
    x = p.add_argument_group("4 · ejecución")
    x.add_argument("--lado", default=None, choices=("compra", "venta"))
    x.add_argument("--orden", type=int, default=None, help="contratos (5000)")
    x.add_argument("--inicio", default=None, dest="inicio_ct", help="HH:MM de Chicago (08:30)")
    x.add_argument("--fin", default=None, dest="fin_ct", help="HH:MM de Chicago (15:00)")
    x.add_argument("--slice-min", type=int, default=None)
    x.add_argument("--pov", type=float, default=None)
    x.add_argument("--pieza", type=int, default=None, help="contratos por orden hija (10)")
    x.add_argument("--urgencia", type=float, default=None, help="κT de Almgren–Chriss (1)")
    x.add_argument("--part-max", type=float, default=None)
    t = p.add_argument_group("Telegram")
    t.add_argument("--telegram", action="store_true")
    t.add_argument("--telegram-documentos", action="store_true")
    t.add_argument("--telegram-buscar-chat", action="store_true")
    s = p.add_argument_group("simulación")
    s.add_argument("--sesiones-sim", type=int, default=None, dest="sim_sesiones")
    s.add_argument("--operaciones-sim", type=int, default=None, dest="sim_operaciones")
    s.add_argument("--semilla", type=int, default=None, dest="sim_semilla")
    s.add_argument("--memoria-sim", type=float, default=None, dest="sim_memoria", help="persistencia del signo (0-1)")
    s.add_argument("--sin-impacto", action="store_true", help="simulación sin impacto (prueba de falsos positivos)")
    return p


def config_desde_args(a: argparse.Namespace) -> Config:
    cambios = {}
    for k in ("sesion_objetivo", "dias_calibracion", "dias_perfil", "esquema", "costo_max_usd", "salida_dir", "rafaga_ms",
              "p_grande", "mle_franja", "aislamiento_s", "min_eventos", "ventana_sesiones", "modelo_ejecucion", "n_param",
              "orden", "inicio_ct", "fin_ct", "slice_min", "pov", "pieza", "urgencia", "part_max", "sim_sesiones",
              "sim_operaciones", "sim_semilla", "sim_memoria"):
        v = getattr(a, k, None)
        if v is not None:
            cambios[k] = v
    if a.simbolo:
        cambios["symbol"] = simbolo_continuo(a.simbolo)
    if a.sesion_objetivo:
        try:
            cambios["sesion_objetivo"] = f"{pd.Timestamp(a.sesion_objetivo):%Y-%m-%d}"
        except ValueError:
            pass                                           # validar() da el mensaje
    if a.horizontes:
        cambios["horizontes_s"] = tuple(int(x) for x in a.horizontes.split(",") if x.strip())
    if a.lado:
        cambios["lado"] = 1 if a.lado == "compra" else -1
    if a.sin_cache:
        cambios["usar_cache"] = False
    return replace(CFG, **cambios)


def config_de_archivo(cfg: Config, tienda, con_sesion: bool) -> Config:
    """Con --archivo y sin --sesion: la sesión objetivo es la última del archivo; la calibración, las anteriores."""
    if con_sesion:
        return cfg
    meta = tienda.metadata
    t1 = int(meta.end) if meta.end else int(meta.start) + DIA_NS          # exclusivo
    dia, seg = reloj_sesion([t1 - 1], cfg.tz_mercado)                     # el reloj del último ns cubierto
    dia = int(dia[0])
    if int(seg[0]) + 1 < segundo_de_hora(cfg.fin_ct):      # la última sesión no llega al final del horizonte
        dia = dias_previos(dia, 1)
    return replace(cfg, sesion_objetivo=f"{fecha_de_dia(dia):%Y-%m-%d}")


def main(argv: list[str] | None = None) -> int:
    for flujo_ in (sys.stdout, sys.stderr):                # Windows con la salida redirigida usa cp1252
        try:
            flujo_.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                  # noqa: BLE001
            pass
    a = construir_parser().parse_args(argv)
    cfg = config_desde_args(a)
    if a.pruebas:
        return pruebas()
    if a.telegram_buscar_chat:
        return buscar_chat_telegram()
    validar(cfg)
    print(f"▶ {IDENTIFICADOR} · {cfg.symbol} · {_lado_txt(cfg)} de {cfg.orden:,} · {cfg.inicio_ct}-{cfg.fin_ct} CT · "
          f"slices de {cfg.slice_min} min · modelo de ejecución: {cfg.modelo_ejecucion}")
    verdad = None
    if a.simulacion:
        arr, bar, verdad = simular(cfg, impacto=not a.sin_impacto)
        cfg = config_simulacion(cfg, verdad, escalar_orden=a.orden is None)
        print(f"🎲 {cfg.sim_sesiones} sesiones simuladas (~{cfg.sim_operaciones:,} operaciones cada una) con impacto "
              f"{'CONOCIDO' if verdad['impacto'] else 'NULO'}: δ = {verdad['delta']}, π = {verdad['pi']}, τ = {verdad['tau']:g} s."
              + (f" Orden escalada a {cfg.orden:,} contratos (≈ 1.5 % del volumen, como 5,000 en el NQ)." if a.orden is None else ""))
        tbbo, ohlcv = arr, bar
        if db is not None:
            try:
                tbbo = db.DBNStore.from_bytes(a_dbn(arr, cfg))
                ohlcv = db.DBNStore.from_bytes(a_dbn_ohlcv(bar, cfg))
                print("   (convertido a archivos DBN TBBO y OHLCV-1m de verdad: la misma ruta que tus datos)")
            except Exception as ex:
                print(f"   (sin DBN: {type(ex).__name__}; se usan los arreglos)")
    elif a.archivo:
        if db is None:
            sys.exit("Falta el paquete databento:  pip install databento")
        tbbo = db.DBNStore.from_file(a.archivo)
        ohlcv = db.DBNStore.from_file(a.archivo_ohlcv) if a.archivo_ohlcv else None
        cfg = config_de_archivo(cfg, tbbo, con_sesion=a.sesion_objetivo is not None)
    else:
        tbbo, ohlcv = obtener_todo(cfg)
    res = analizar(tbbo, ohlcv, cfg, verdad=verdad, rapido=a.rapido or a.solo_plan)
    if a.solo_plan:
        reporte_plan(res)
        reporte_cordura(res)
        guardar(res, solo_plan=True)
        if a.telegram:
            enviar_telegram(res, [], solo_plan=True)
        return 0
    reporte_datos(res)
    reporte_tu_script(res)
    reporte_eventos(res)
    reporte_mle(res)
    reporte_rolling(res)
    reporte_backtest(res)
    reporte_objetivo(res)
    reporte_plan(res)
    reporte_cordura(res)
    reporte_verdad(res)
    rutas, plt_, ventana = ([], None, False)
    if not a.sin_tablero:
        print()
        rutas, plt_, ventana = tableros(res, mostrar=not a.sin_ventana)
    guardar(res)
    if a.telegram:
        enviar_telegram(res, rutas, documentos=a.telegram_documentos)
    _titulo("CÓMO LEER ESTO")
    print("  1. El MLE mide cuánto mueve el precio un print grande según su tamaño RELATIVO al volumen de la hora")
    print("     (δ: forma de la curva), qué parte se queda (π) y en cuánto tiempo se va el resto (τ).")
    print("  2. Con eso cada algoritmo se ejecuta en sesiones PASADAS con lo que se sabía antes de cada una, del")
    print("     lado de compra y del de venta: el promedio es el costo; la dispersión de un lado, el riesgo.")
    print("  3. La parte permanente del impacto es igual para cualquier plan que termine: los algoritmos sólo")
    print("     reparten transitorio contra riesgo de timing. Diferencias de centésimas de tick no importan.")
    print("  4. Un solo día no elige algoritmo: lo decide el timing. Mira el walk-forward y el MDE.")
    print("  5. π y τ se identifican mal con pocas sesiones; la tabla de arrepentimiento dice cuánto importa.")
    if rutas and not a.sin_ventana:
        print()
        mostrar_tableros(plt_, ventana, rutas)
    return 0


# =============================================================================
# 15. PRUEBAS INTERNAS
# =============================================================================
def pruebas() -> int:
    import contextlib
    import io
    fallas: list[str] = []
    hecho = 0

    def check(nombre_: str, ok: bool, detalle: str = "") -> None:
        nonlocal hecho
        hecho += 1
        print(f"  {'✓' if ok else '✗'} {nombre_}" + (f"   {detalle}" if detalle else ""))
        if not ok:
            fallas.append(nombre_)

    _titulo("PRUEBAS INTERNAS")
    t_ini = time.time()
    cs = replace(CFG, sim_sesiones=8, sim_operaciones=24_000, dias_calibracion=7, dias_perfil=7, ventana_sesiones=3,
                 sesiones_perfil=5, ventana_magnitud=3, min_ref=1000, min_eventos=200, n_param=20)
    arr, bar, ver = simular(cs, semilla=5)
    cs = config_simulacion(cs, ver)
    tk = tick_ns(cs.symbol)

    def iguales(A: pd.DataFrame, B: pd.DataFrame) -> bool:
        if len(A) != len(B) or list(A.columns) != list(B.columns):
            return False
        for c in A.columns:
            a, b = A[c].to_numpy(dtype=float), B[c].to_numpy(dtype=float)
            if not np.array_equal(np.isfinite(a), np.isfinite(b)) or not np.array_equal(a[np.isfinite(a)], b[np.isfinite(b)]):
                return False
        return True

    E0, motor, barras = correr_motor_ejecucion(arr, cs, verbose=False)

    # 1 ------------------------------------------ lado del agresor
    r = normalizar(arr[:5000])
    _, signo, _, _, _ = higiene(r, tk, cs)
    lado_ok = bool(np.all(signo[r["lado"] == b"B"] == 1) and np.all(signo[r["lado"] == b"A"] == -1))
    check("side B = compra agresiva (en el ask), A = venta (en el bid)", lado_ok and chequeo_lado_e(preparar_eventos(E0, cs)) > 0.999)

    # 2 ------------------------------------------ eventos exactos
    val = (arr["action"] == b"T") & (arr["size"] > 0) & np.isin(arr["side"], [b"B", b"A"])
    n_verdad = len(np.unique(arr["ts_event"][val].astype(np.int64) * 2 + (arr["side"][val] == b"B")))
    check("un evento por casación de CME (misma hora y mismo agresor), sin perder volumen",
          len(E0) == n_verdad and int(E0["vol"].sum()) == int(arr["size"][val].sum()), f"{len(E0):,} eventos")

    # 3 ------------------------------------------ bloques
    E_b, _, barras_b = correr_motor_ejecucion(arr, replace(cs, bloque=777), verbose=False)
    check("procesar en bloques de 777 registros = de un jalón (eventos y barras de 1 minuto)",
          iguales(E0, E_b) and iguales(barras.reset_index(drop=True), barras_b.reset_index(drop=True)))

    # 4 ------------------------------------------ archivos DBN de verdad
    if db is not None:
        try:
            E_d, _, barras_d = correr_motor_ejecucion(db.DBNStore.from_bytes(a_dbn(arr, cs)), replace(cs, bloque=5_000), verbose=False)
            o1 = barras_ohlcv(bar, cs)
            o2 = barras_ohlcv(db.DBNStore.from_bytes(a_dbn_ohlcv(bar, cs)), cs)
            check("archivos DBN TBBO y OHLCV-1m leídos por bloques con to_ndarray = los mismos datos",
                  iguales(E0, E_d) and iguales(o1.reset_index(drop=True), o2.reset_index(drop=True)))
        except Exception as ex:
            check("archivos DBN de verdad", False, f"{type(ex).__name__}: {ex}")
    else:
        check("DBN (databento no instalado: se omite)", True)

    # 5 ------------------------------------------ perfiles causales
    E = preparar_eventos(E0, cs)
    H, hid = agrupar_huellas(E, cs)
    E["hid"] = hid
    _, _, clase = clasificar_magnitud(H, cs)
    H["clase"], H["tipo"], H["ventana"] = clase, tipificar(H, cs), True
    bo = barras_ohlcv(bar, cs)
    perf = Perfiles(tabla_slots(bo, cs, "close"), cs, tabla_slots(barras.assign(inst=0), cs, "mid"))
    d = dia_objetivo(cs)
    bo2 = bo.copy()
    bo2.loc[bo2["sesion"] >= d, "vol"] *= 7.0
    perf2 = Perfiles(tabla_slots(bo2, cs, "close"), cs, tabla_slots(barras.assign(inst=0), cs, "mid"))
    v1, s1, _ = perf.de(d)
    v2, s2, _ = perf2.de(d)
    spreads = perfil_spread(barras, cs)
    w1, w2 = mercado(d, perf, spreads, cs).w, mercado(d, perf2, spreads, cs).w
    check("perfiles y pesos de VWAP sólo con sesiones ANTERIORES (multiplicar el volumen de hoy no los cambia)",
          np.array_equal(v1, v2, equal_nan=True) and np.array_equal(s1, s2, equal_nan=True) and np.array_equal(w1, w2))

    # 6 ------------------------------------------ POV con rezago
    mer = mercado(d, perf, spreads, cs)
    vm = np.full(len(mer.w_min), 100.0)
    u1, _ = plan_pov(500.0, 0.1, mer, vm)
    vm2 = vm.copy()
    vm2[40] *= 5
    u2, _ = plan_pov(500.0, 0.1, mer, vm2)
    cm = max(1, int(round(60.0 / mer.clip_s)))
    check("POV decide el minuto t con el volumen de t − 1 (cambiar el minuto 40 no altera hasta el 40)",
          np.array_equal(u1[:41 * cm], u2[:41 * cm]) and not np.array_equal(u1, u2))
    vm3 = vm.copy()
    vm3[40] = 0.0
    u3, f3 = plan_pov(500.0, 0.1, mer, vm3)
    check("POV sigue operando después de un minuto sin volumen (no manda el resto al final)",
          f3 < 1e-9 and u3[42 * cm:].sum() > 0, f"forzado {f3:.1f}")

    # 7-10 --------------------------------------- formas cerradas
    N, X, eta, sig2, lam = 40, 1000.0, 0.01, 4.0, 0.002
    n = almgren_chriss(X, lam, np.full(N, eta), np.full(N, sig2))
    s2_ = lam * sig2 / 3
    k = math.acosh((2 * eta + 2 * s2_) / (2 * eta - s2_))
    xs = X * np.sinh(k * (N - np.arange(N + 1))) / np.sinh(k * N)
    err = float(np.max(np.abs(np.r_[X, X - np.cumsum(n)] - xs)))
    check("Almgren–Chriss tridiagonal = solución cerrada X·sinh(κ(N − j))/sinh(κN)", err < 1e-8, f"error {err:.1e}")
    v = np.random.default_rng(0).uniform(1, 5, N)
    n2 = almgren_chriss(X, 0.0, 1.0 / v, np.full(N, 1.0))
    err = float(np.max(np.abs(n2 - X * v / v.sum())))
    check("Almgren–Chriss con λ = 0 y η ∝ 1/volumen = VWAP", err < 1e-8, f"error {err:.1e}")
    tau, dt, Cc = 60.0, 30.0, 21
    mer_t = Mercado(0, 0, 0, Cc, 1, (np.arange(Cc) * dt * NS).astype(np.int64), np.zeros(Cc, int), np.ones(1), np.ones(1),
                    np.zeros(1), np.full(Cc, 1 / Cc), np.full(Cc, 1 / Cc), 1.0, dt, dt, 300.0)
    mod_t = ModeloImpacto(1.0, 0.5, 0.0, tau, 1.0, 1.0, np.full(Cc, 0.02), 0.0, 0.5)
    M_t = matrices(mod_t, mer_t)
    u, ok = optimo_ow(X, 0.0, M_t, mer_t)
    a_ = math.exp(-dt / tau)
    x0 = X / ((Cc - 2) * (1 - a_) + 2)
    esper = np.r_[x0, np.full(Cc - 2, (1 - a_) * x0), x0]
    err = float(np.max(np.abs(u - esper)) / X)
    check("ÓPTIMO (QP clip a clip) = Alfonsi–Fruth–Schied: bloques en los extremos y (1 − e^(−Δ/τ)) en medio",
          ok and err < 1e-9, f"error {err:.1e}")
    mod_p = ModeloImpacto(1.0, 0.5, 1.0, tau, 1.0, 1.0, np.zeros(Cc), 0.02, 0.5)
    M_p = matrices(mod_p, mer_t)
    c1 = costo_modelo(np.full(Cc, X / Cc), X, M_p)[0]
    c2 = costo_modelo(np.r_[X, np.zeros(Cc - 1)], X, M_p)[0]
    check("impacto 100 % permanente: el costo es ½κX² para CUALQUIER plan que termine",
          abs(c1 - 0.01 * X * X) < 1e-6 * X * X and abs(c2 - 0.01 * X * X) < 1e-6 * X * X)

    # 11 ----------------------------------------- QP: factible y nadie lo mejora
    mod_r = modelo_impacto({"delta": 0.5, "pi": 0.4, "tau": 90.0}, 0.03, 0.01, mer, cs)
    M_r = matrices(mod_r, mer)
    lam_r = lambda_de_urgencia(2.0, eta_slices(mod_r, mer, M_r, total=True), M_r["w"].reshape(mer.N, mer.m).sum(axis=1))
    u_o, ok_o = optimo_ow(500.0, lam_r, M_r, mer)
    obj = lambda w: costo_modelo(w, 500.0, M_r)[0] + lam_r * costo_modelo(w, 500.0, M_r)[1] ** 2   # noqa: E731
    B = matriz_reparto(mer)
    rng = np.random.default_rng(1)
    mejor = min(obj(B @ (500.0 * rng.dirichlet(np.ones(mer.N)))) for _ in range(200))
    otros = min(obj(plan_estatico(nm, 500.0, mer, mod_r, M_r, lam_r)) for nm in ("TWAP", "VWAP", "AC"))
    check("ÓPTIMO: suma la orden, sin ventas, y ni 200 planes al azar ni TWAP/VWAP/AC bajan su E + λ·Var",
          ok_o and abs(u_o.sum() - 500) < 1e-6 and u_o.min() > -1e-9 and obj(u_o) <= min(mejor, otros) + 1e-9)
    planes_r = {nm: plan_estatico(nm, 500.0, mer, mod_r, M_r, lam_r) for nm in ("TWAP", "VWAP", "AC", "ÓPTIMO")}
    arr_r = arrepentimiento(500.0, mer, mod_r, lam_r, planes_r, cs)
    mer_s = replace(mer, tope=None)
    mod_1 = modelo_impacto({"delta": 0.5, "pi": 1.0, "tau": 90.0}, 0.03, 0.01, mer_s, cs, pi_max=1.0)
    M_1 = matrices(mod_1, mer_s)
    e_1 = costo_modelo(optimo_ow(500.0, 0.0, M_1, mer_s)[0], 500.0, M_1)[0]
    e_min = min(costo_modelo(B @ (500.0 * np.eye(mer.N)[k]), 500.0, M_1)[0] for k in range(mer.N))
    check("arrepentimiento ≥ 0 en E + λ·Var y el QP resuelve el caso singular (π = 1, λ = 0)",
          arr_r["arrepentimiento"].min() > -1e-9 and e_1 <= e_min + 1e-6 * abs(e_min))
    # π̂ = 1.5 (en la cota): π de ejecución 0.9, λ > 0 sin importar π y el ÓPTIMO respeta el tope por slice
    mod_c = modelo_impacto({"delta": 0.5, "pi": 1.5, "tau": 90.0}, 0.03, 0.01, mer, cs)
    M_c = matrices(mod_c, mer)
    lam_c = lambda_de_urgencia(1.0, eta_slices(mod_c, mer, M_c, total=True), M_c["w"].reshape(mer.N, mer.m).sum(axis=1))
    lam_d = lambda_de_urgencia(1.0, eta_slices(mod_r, mer, M_r, total=True), M_r["w"].reshape(mer.N, mer.m).sum(axis=1))
    n_c = optimo_ow(2000.0, lam_c, M_c, mer)[0].reshape(mer.N, mer.m).sum(axis=1)
    check("π̂ en la cota: π de ejecución 0.9, la urgencia no depende de π y el ÓPTIMO respeta el tope de participación",
          mod_c.pi == PI_MAX and abs(lam_c - lam_d) < 1e-9 * max(abs(lam_d), 1e-300) and lam_c > 0
          and np.all(n_c <= mer.tope * (1 + 1e-6) + 1e-6) and (n_c > 0).sum() > mer.N // 4,
          f"slice máximo {n_c.max():.0f} de tope {mer.tope.max():.0f}")
    # QP con cajas: KKT en un problema al azar
    rng_q = np.random.default_rng(3)
    Aq = rng_q.standard_normal((12, 12))
    Qq, bq, hq = Aq @ Aq.T + 0.1 * np.eye(12), rng_q.standard_normal(12) * 5, rng_q.uniform(5, 20, 12)
    nq, okq = qp_simplex(Qq, bq, 100.0, hq)
    gq = Qq @ nq + bq
    libres_q = (nq > 1e-7) & (nq < hq - 1e-7)
    mu_q = -float(np.mean(gq[libres_q])) if libres_q.any() else 0.0
    rq = gq + mu_q
    tq_ = 1e-6 * (1 + np.abs(gq).max())
    kkt = (np.all(np.abs(rq[libres_q]) < tq_) and np.all(rq[nq <= 1e-7] > -tq_) and np.all(rq[nq >= hq - 1e-7] < tq_))
    check("QP con topes: suma la orden, respeta 0 ≤ n ≤ tope y cumple KKT",
          okq and abs(nq.sum() - 100) < 1e-6 and nq.min() > -1e-9 and np.all(nq <= hq + 1e-9) and kkt
          and (nq >= hq - 1e-7).any())


    # 12-13 -------------------------------------- réplica: atribución exacta y compra/venta
    real = realizado(mer, E, barras)
    corte = (E["sesion"].to_numpy() == d) & (E["seg"].to_numpy() >= segundo_de_hora("12:00"))
    E_corta = E[~corte].reset_index(drop=True)
    b_corta = barras[~((barras["sesion"] == d) & (barras["seg"] >= segundo_de_hora("12:00")))]
    d_prev = int(E.loc[E["sesion"] < d, "sesion"].max())
    mer_p = mercado(d_prev, perf, spreads, cs)
    E_sig = E[~((E["sesion"] == d) | ((E["sesion"] == d_prev) & (E["seg"] >= segundo_de_hora("12:00"))))].reset_index(drop=True)
    check("una sesión cortada a mediodía (cierre anticipado) no se replica con precios de la sesión siguiente",
          realizado(mer, E_corta, b_corta) is None and realizado(mer_p, E_sig, barras) is None and real is not None)
    c16 = replace(cs, inicio_ct="15:00", fin_ct="16:00")
    ok16 = realizado(mercado(d_prev, perf, spreads, c16), E, barras) is not None
    check("con --fin 16:00 (el cierre) una sesión intermedia sí se replica", ok16)
    r1 = ejecutar(u_o, 1, mer, mod_r, M_r, real)
    r2 = ejecutar(u_o, -1, mer, mod_r, M_r, real)
    suma = sum(r1[k] for k in ("spread", "propio", "transitorio", "permanente", "timing", "comisiones"))
    check("atribución exacta: spread + propio + transitorio + permanente + timing = IS", abs(suma - r1["is_ticks"]) < 1e-6 * max(1, abs(r1["is_ticks"])))
    check("promedio de compra y venta = costo modelado (el timing se cancela exacto)",
          abs((r1["is_ticks"] + r2["is_ticks"]) / 2 - costo_modelo(u_o, 500.0, M_r)[0] + float(u_o @ (M_r["b"] - real.spread / 2))) < 1e-6 * 500)

    # 14-16 -------------------------------------- MLE: caché, recuperación y caso nulo
    var = Varianza(perf, cs)
    obs = eventos_clave(H, E, perf, var, deriva_sesiones(E, cs), cs)
    x_ref = x_referencia(obs)
    flujo = Flujo(H, E, perf, cs)
    vp = Verosimilitud(obs, MODELOS["propagador"], x_ref, flujo)
    pa, pb = dict(INICIO), dict(INICIO, delta=0.7, pi=0.2, kappa=1.3)
    la = vp.por_evento(pa)[0].sum()
    vp.por_evento(pb)
    la2 = vp.por_evento(pa)[0].sum()
    lf = Verosimilitud(obs, MODELOS["propagador"], x_ref, Flujo(H, E, perf, cs)).por_evento(pa)[0].sum()
    check("la verosimilitud con cachés (Σ⁻¹ por κ ω ϕ, estado del flujo por δ τ) = la recalculada", la == la2 and abs(la - lf) < 1e-8 * abs(lf))
    k_ = obs.k
    crece = all(np.all(np.diff(obs.t_obs[i, :k_[i]]) > 0) for i in range(obs.n))
    check("cada horizonte de un evento clave es una operación DISTINTA y posterior a la del anterior", crece)
    aj = ajustar(obs, MODELOS["respuesta"], x_ref, None, errores=True)
    autov = np.linalg.eigvalsh(aj.V) if aj.V is not None else np.array([-1.0])
    check("ω queda en el interior (sin observaciones duplicadas) y la covarianza robusta es semidefinida positiva",
          "omega" not in aj.en_cota and autov.min() > -1e-12 * max(1.0, autov.max()),
          f"ω = {aj.p['omega']:.3f}")
    _, seg = reloj_sesion(obs.K["t_ini"].to_numpy(), cs.tz_mercado)
    mi = np.clip(seg // 60, 0, len(ver["sig5"]) - 1)
    f_true = ver["Y"] * base_huella(obs.qe, obs.ptr, ver["sig5"][mi], ver["v5"][mi], ver["delta"], 1.0)
    f_hat = aj.A * base_huella(obs.qe, obs.ptr, obs.K["sig5"].to_numpy(), obs.K["v5"].to_numpy(), aj.p["delta"], x_ref)
    razon = float(np.mean(f_hat) / np.mean(f_true))
    z_d = (aj.p["delta"] - ver["delta"]) / aj.se["delta"]
    check("MLE recupera la verdad simulada: δ a menos de 4 EE y el impacto inicial medio a ± 20 %",
          abs(z_d) < 4 and 0.8 < razon < 1.2, f"δ = {aj.p['delta']:.3f} ± {aj.se['delta']:.3f} (verdad {ver['delta']}) · f̂/f = {razon:.2f}")
    arr0, bar0, ver0 = simular(cs, semilla=6, impacto=False)
    with contextlib.redirect_stdout(io.StringIO()):
        E00, _, b00 = correr_motor_ejecucion(arr0, cs, verbose=False)
    E00 = preparar_eventos(E00, cs)
    H0, hid0 = agrupar_huellas(E00, cs)
    E00["hid"] = hid0
    H0["clase"] = clasificar_magnitud(H0, cs)[2]
    H0["tipo"], H0["ventana"] = tipificar(H0, cs), True
    p0 = Perfiles(tabla_slots(barras_ohlcv(bar0, cs), cs, "close"), cs, tabla_slots(b00.assign(inst=0), cs, "mid"))
    o0 = eventos_clave(H0, E00, p0, Varianza(p0, cs), deriva_sesiones(E00, cs), cs)
    A0, se0, _ = A_por_gls(o0, Ajuste(MODELOS["raiz"], dict(INICIO), 0.0, x_referencia(o0), 0.0, o0.n, 0, []))
    check("sin impacto en la simulación, A no sale distinto de 0 (|t| < 3)", abs(A0 / se0) < 3, f"A = {A0:.4f} ± {se0:.4f}")

    # 17 ----------------------------------------- walk-forward causal
    rl = rolling(obs, MODELOS["respuesta"], x_ref, None, replace(cs, ventana_sesiones=4), aj, verbose=False)
    ses = obs.K["sesion"].to_numpy()
    causal = all(int(f["n_exp"]) == int((ses < f["sesion"]).sum()) for _, f in rl.tabla.iterrows() if not f["siguiente"])
    check("rolling: cada sesión se opera con parámetros ajustados SÓLO con las anteriores", causal and len(rl.tabla) > 0,
          f"{len(rl.tabla)} filas")

    # 18 ----------------------------------------- tu script
    tu = tu_script(bo, cs)
    check("réplica de tu script: POV al 10 % termina en minutos y tu VWAP usa el volumen del mismo día",
          tu.get("disponible", False) and tu["res"]["POV"]["minutos"] < tu["res"]["TWAP"]["minutos"])

    # 19 ----------------------------------------- validación
    malos = 0
    for c in (replace(cs, esquema="trades"), replace(cs, p_grande=1.5), replace(cs, horizontes_s=(5, 10, 20)),
              replace(cs, inicio_ct="15:00", fin_ct="08:30"), replace(cs, slice_min=7), replace(cs, pov=1.2),
              replace(cs, ventana_sesiones=8, dias_calibracion=5)):
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                validar(c)
        except SystemExit:
            malos += 1
    check("rechaza configuraciones inválidas", malos == 7, f"{malos}/7")

    # 20-23 -------------------------------------- Telegram y secretos
    tok = "123456789:" + "A" * 35
    msg = _sin_token(f"fallo en https://api.telegram.org/bot{tok}/sendMessage", tok)
    check("los errores de Telegram nunca muestran el token", tok not in msg)
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
        ok = llamar_telegram(tok, "sendPhoto", {"chat_id": "123456789", "caption": "á <b>"}, archivo=("photo", png)).get("ok")
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
    with contextlib.redirect_stdout(io.StringIO()):
        res = analizar(arr, bar, replace(cs, n_param=0), verdad=ver, verbose=False, rapido=True)
    txt = mensaje_telegram(res)
    check("análisis completo de punta a punta y el mensaje de Telegram cabe en un mensaje",
          len(res.bt.filas) > 0 and len(res.plan) > 0 and len(txt) <= 4096 and "<b>" in txt, f"{len(txt)} caracteres")

    print(f"\n  ({time.time() - t_ini:.0f} s)")
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
