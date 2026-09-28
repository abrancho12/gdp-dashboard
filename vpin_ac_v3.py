# -*- coding: utf-8 -*-
"""
VPIN AC v3 — Toxicidad del flujo con reloj de VOLUMEN (Easley, López de Prado & O'Hara, 2012)
Datos: Databento trades (GLBX.MDP3) con el lado agresor exacto de cada operación.

La v2 dejó bien la mecánica: el desbordamiento de uint32, el lado agresor, los buckets de volumen fijo, cada valor
fechado al cierre de su bucket y dos motores que dan lo mismo (verificado otra vez aquí). La v3 corrige cómo se LEE
la señal y cuánto se le puede creer. Los comentarios marcados con [v3] explican cada cambio:

  1. PERCENTIL CON REFERENCIA LARGA Y SIN SOLAPAMIENTO. Dos VPIN seguidos comparten 49 de sus 50 buckets: en los
     250 buckets de referencia de la v2 caben ~5 valores independientes (autocorrelación 0.43 a 25 buckets, ~0 a
     50). Medido en un mercado simulado estable: el "percentil 90" de la v2 caía entre el percentil 72 y el 97 de la
     distribución verdadera (del 10 % al 90 % de las veces). Aquí la referencia son 1,000 buckets (≈ 20 sesiones)
     que terminan n buckets ANTES del actual, así que ninguno comparte buckets con su ventana: percentil 87 a 94.
  2. UNA EVALUACIÓN QUE NO SE ENGAÑA. En mercados simulados SIN información en el flujo (el lado agresor es una
     moneda al aire, con actividad en U, operaciones más grandes en el contado y días más o menos agitados), la v2
     declaraba el VPIN "significativo" (|t| > 1.96) en el 40–73 % de los horizontes, también con el IC parcial.
     Tres causas y tres arreglos:
       · el VPIN persiste ~1 sesión y los buckets de un mismo día no son independientes: el error estándar sale
         de un bootstrap por BLOQUES DE SESIONES (se remuestrean días enteros) y el p de una t con (bloques − 1)
         grados de libertad, porque con pocos bloques el bootstrap subestima la varianza;
       · la hora del día mueve a la vez la actividad, el tamaño de las operaciones (y con él el VPIN) y la
         volatilidad: el IC parcial compara cada bucket solo con buckets de la MISMA hora (efectos fijos) y
         descuenta la volatilidad típica de ese minuto (la de las 20 sesiones anteriores, sin mirar el futuro);
       · los días agitados duran varias sesiones: también se descuentan la volatilidad y el volumen de la última
         sesión de mercado, además de los del mismo horizonte (los de la v2).
     El veredicto usa Bonferroni sobre los horizontes y el estudio de eventos compara cada alerta contra lo típico
     de su hora. Medido con --simular (30–40 mercados de cada tipo, 20 sesiones de historia):
                                        sin información (debe ser ~5 %)       con información (potencia)
          v2, |t| > 1.96                40–73 % de los horizontes             55–97 %
          v3, p < 0.05 por horizonte    0–7.5 %                               20 ses.: 10–50 % · 40 ses.: 33–70 %
          v3, veredicto (Bonferroni)    0 %                                   20 ses.: 35 %    · 40 ses.: 70 %
     Es decir: la v3 casi nunca ve información donde no la hay, y a cambio necesita ~40 sesiones (2 meses) de
     evaluación para encontrarla cuando sí la hay. Con 20 sesiones, un "no se distingue de cero" dice poco.
  3. LIVE SIN HUECOS. El reconnect_policy="reconnect" de Databento se vuelve a suscribir con start=None (sin
     replay): lo que pasaba durante el corte se perdía sin aviso y los buckets quedaban mal. Aquí la reconexión es
     propia: replay desde lo último procesado y descarte de duplicados (el Deduplicador de Order Flow / Iceberg),
     con espera creciente y el piso que imponga el gateway.
  4. DETALLES.
     · ES.v.0 (rola por VOLUMEN) en vez de ES.n.0 (por interés abierto): en la semana del roll el .n.0 sigue en el
       contrato que ya casi no opera y el reloj de volumen se frena.
     · La duración de los buckets y de la ventana va en minutos DE MERCADO (sin la pausa diaria ni el fin de
       semana): en la v2 cada ventana que cruzaba un fin de semana parecía "lenta" 49 horas.
     · V = mediana de las últimas 20 sesiones COMPLETAS antes de la evaluación (sin la primera sesión a medias ni
       feriados). Esas sesiones se bajan aparte (historia_dias), así que la evaluación empieza con V, la referencia
       del percentil y la estacionalidad ya listas. En Live, las sesiones más recientes (la v2 usaba las más viejas).
     · Caché por día: cada día UTC es un archivo; al mover las fechas solo se bajan los días que faltan.
     · Tabla de ticks completa (6E, ZN, CL…) para el análisis de dirección.
     · El aviso de "hueco sin replay" en Live solo sale si en el hueco el mercado estuvo abierto.
Lo que se conserva de la v2: los dos motores, el reloj de volumen, el percentil sin look-ahead, la histéresis y el
cooldown de las alertas, la relación mecánica con la actividad, el tablero y la API key fuera del código.

API key (nunca en el código):
  Windows, una sola vez:  setx DATABENTO_API_KEY "db-..."   y luego cierra y abre VS Code
  macOS / Linux:          export DATABENTO_API_KEY="db-..."
  La caché (datos_databento/) y los resultados (salidas_vpin/) se guardan junto a este archivo.

Uso:
  python vpin_ac_v3.py                           # evalúa [start, end) de Config, con historia_dias de historia antes
  python vpin_ac_v3.py --inicio 2026-06-01T00:00:00 --fin 2026-08-21T23:59:00
  python vpin_ac_v3.py --motor incremental
  python vpin_ac_v3.py --archivo trades.dbn.zst  # un archivo propio: calibra con sus primeras sesiones (como la v2)
  python vpin_ac_v3.py --live                    # calienta con las últimas sesiones y sigue en vivo
  python vpin_ac_v3.py --autoprueba              # sin API, ~1 minuto
  python vpin_ac_v3.py --simular 40              # la calibración del punto 2: v2 contra v3 en mercados simulados
  python vpin_ac_v3.py --simular 30 --sesiones-eval 40
"""
from __future__ import annotations

import argparse
import gc
import math
import os
import re
import sys
import threading
import time
import unicodedata
from collections import deque
from dataclasses import dataclass, replace
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd
from databento_dbn import ErrorCode, SystemCode
from numpy.lib.stride_tricks import sliding_window_view

IDENTIFICADOR = "vpin-ac-v3"


# =============================================================================
# 1. CONFIGURACIÓN
# =============================================================================
@dataclass(frozen=True)
class Config:
    # --- Datos ---
    dataset: str = "GLBX.MDP3"
    symbol: str = "ES.v.0"                  # [v3] .v. = el contrato con más volumen (la v2: .n., interés abierto)
    stype_in: str = "continuous"
    start: str = "2026-06-01T00:00:00"      # UTC: inicio de la EVALUACIÓN
    end: str = "2026-06-29T23:59:00"        # UTC (exclusivo)
    historia_dias: int = 35                 # [v3] días antes de start: V, referencia del percentil y estacionalidad
    tick_size: float | None = None          # None = se deduce del símbolo (YM = 1 punto)
    cache_dir: str = "datos_databento"
    salida_dir: str = "salidas_vpin"
    costo_max_usd: float = 25.0             # no descarga si Databento cotiza más que esto (solo lo que falta)
    tam_bloque: int = 5_000_000             # registros por bloque (× 48 bytes = RAM por bloque)

    # --- VPIN (Easley, López de Prado & O'Hara, 2012) ---
    buckets_por_dia: int = 50               # V = volumen de una sesión típica / 50
    n_buckets: int = 50                     # ventana del VPIN ≈ 1 sesión de volumen (el del artículo)
    volumen_bucket: int | None = None       # fíjalo para comparar corridas; None = calibrar
    dias_calibracion: int = 20              # [v3] las últimas 20 sesiones completas antes de la evaluación
    dias_calibracion_archivo: int = 5       # sin historia previa (--archivo): las primeras, como la v2

    # --- Toxicidad relativa (percentil sin look-ahead) ---
    ventana_pct: int = 1000                 # [v3] ≈ 20 sesiones (la v2: 250 ≈ 5 valores independientes)
    rezago_pct: int | None = None           # [v3] None = n_buckets: la referencia no comparte buckets con la ventana
    min_obs_pct: int = 500
    umbral_pct: float = 0.90                # el artículo usa CDF(VPIN) > 0.9
    rearme_pct: float = 0.75                # histéresis: se rearma al bajar de aquí
    cooldown_min: int = 120

    # --- Evaluación ---
    horizontes_min: tuple[int, ...] = (30, 60, 120, 240)
    sesiones_estacionalidad: int = 20       # [v3] la volatilidad típica de cada hora: las 20 sesiones anteriores
    min_sesiones_estacionalidad: int = 5
    bootstrap: int = 500                    # [v3] réplicas del bootstrap por bloques de sesiones
    bloque_sesiones: int = 2                # [v3] sesiones por bloque (el VPIN persiste ~1 sesión)
    alfa: float = 0.05                      # con Bonferroni sobre los horizontes
    semilla: int = 7

    # --- Live ---
    dias_historial_live: int = 35           # [v3] calendario: ~24 sesiones para V, percentil y detector
    replay_max_h: float = 23.0              # el replay intradía de Live cubre ~24 h
    heartbeat_s: int = 15


CFG = Config()

CARPETA_SCRIPT = Path(__file__).resolve().parent
NS = 1_000_000_000
NS_MIN = 60 * NS
PRICE_SCALE = 1e9
TICKS = {"ES": 0.25, "MES": 0.25, "NQ": 0.25, "MNQ": 0.25, "YM": 1.0, "MYM": 1.0, "RTY": 0.1, "M2K": 0.1,
         "CL": 0.01, "MCL": 0.01, "NG": 0.001, "GC": 0.1, "MGC": 0.1, "SI": 0.005, "HG": 0.0005,
         "ZN": 0.015625, "ZB": 0.03125, "ZF": 0.0078125, "ZT": 0.00390625, "UB": 0.03125,
         "6E": 0.00005, "6J": 0.0000005, "6B": 0.0001, "6A": 0.00005, "6C": 0.00005,
         "ZC": 0.25, "ZS": 0.25, "ZW": 0.25}     # [v3] completa

try:
    from zoneinfo import ZoneInfo
    TZ_LOCAL = ZoneInfo("America/Mexico_City")
    TZ_CME = ZoneInfo("America/Chicago")
except Exception:                               # Windows sin el paquete tzdata
    import pytz
    TZ_LOCAL = pytz.timezone("America/Mexico_City")
    TZ_CME = pytz.timezone("America/Chicago")

COLUMNAS_BUCKET = ["t_ini", "t_fin", "oi", "n_trades", "precio", "instrumento"]


def _ns(t) -> np.ndarray:
    """Fechas → enteros en nanosegundos UTC."""
    return pd.DatetimeIndex(t).as_unit("ns").asi8


def tick_de(cfg: Config) -> float:
    if cfg.tick_size:
        return cfg.tick_size
    raiz = re.match(r"[A-Za-z0-9]+?(?=[.]|[FGHJKMNQUVXZ]\d|$)", cfg.symbol)
    return TICKS.get(raiz.group(0).upper() if raiz else "", 1.0)


def rezago_de(cfg: Config) -> int:
    return int(cfg.rezago_pct) if cfg.rezago_pct else int(cfg.n_buckets)


# =============================================================================
# 2. MOTOR INCREMENTAL (trade a trade: replay y Live) — el de la v2, sin cambios
# =============================================================================
# Reglas que comparten ambos motores:
#   R1  Solo trades (action 'T'). side 'B' = +1 (compra agresiva), 'A' = -1 (venta agresiva).
#       side 'N' (sin agresor) no entra a los buckets; se reporta aparte.
#   R2  Reloj de volumen: cada bucket junta exactamente V contratos. Un trade grande se reparte
#       entre los buckets que toque, así que puede cerrar varios a la vez.
#   R3  oi = compras - ventas dentro del bucket (compras = (V + oi)/2).
#   R4  Tiempo monótono (máximo acumulado de ts_event). t_ini = trade que abre el bucket,
#       t_fin = trade que lo completa (momento en que el bucket se conoce).
#   R5  n_trades = trades que aportan al menos un contrato al bucket.
class MotorVPIN:
    def __init__(self, volumen_bucket: int, al_cerrar_bucket=None):
        self.V = int(volumen_bucket)
        if self.V <= 0:
            raise ValueError("volumen_bucket debe ser positivo")
        self.al_cerrar_bucket = al_cerrar_bucket
        self.sin_lado = 0
        self._ts_max = -1
        self._k = 0                 # buckets cerrados
        self._vol = 0
        self._oi = 0
        self._n = 0
        self._t_ini = 0
        self._filas: list[dict] = []

    def procesar(self, r) -> None:
        ts = r.ts_event
        if ts < self._ts_max:                                   # R4
            ts = self._ts_max
        self._ts_max = ts
        if r.action != "T":                                     # R1 (permite MBP-1 también)
            return
        if r.side == "B":
            s = 1
        elif r.side == "A":
            s = -1
        else:
            self.sin_lado += r.size
            return
        restante = r.size
        while restante > 0:                                     # R2
            if self._vol == 0:
                self._t_ini, self._n = ts, 0
            q = min(self.V - self._vol, restante)
            self._vol += q
            self._oi += s * q
            self._n += 1                                        # R5
            restante -= q
            if self._vol == self.V:
                self._k += 1
                fila = {"k": self._k, "t_ini": self._t_ini, "t_fin": ts, "oi": self._oi,
                        "n_trades": self._n, "precio": r.price, "instrumento": r.instrument_id}
                self._filas.append(fila)
                self._vol = self._oi = 0
                if self.al_cerrar_bucket is not None:
                    self.al_cerrar_bucket(fila)

    def buckets(self) -> pd.DataFrame:
        return _tabla_buckets(self._filas)


def _tabla_buckets(filas) -> pd.DataFrame:
    df = pd.DataFrame(filas, columns=["k"] + COLUMNAS_BUCKET)
    df = df.astype({"k": np.int64, "t_ini": np.int64, "t_fin": np.int64, "oi": np.int64,
                    "n_trades": np.int64, "precio": np.float64, "instrumento": np.int64})
    df["precio"] = df["precio"] / PRICE_SCALE
    for col in ("t_ini", "t_fin"):
        df[col] = pd.to_datetime(df[col], utc=True)
    return df.set_index("k")


# =============================================================================
# 3. MOTOR VECTORIZADO (numpy por bloques) — el de la v2, sin cambios
# =============================================================================
@dataclass
class _Arrastre:
    C: int = 0                  # volumen clasificado acumulado antes del bloque
    D: int = 0                  # compras - ventas acumuladas antes del bloque
    g: int = 0                  # trades clasificados antes del bloque
    k: int = 0                  # buckets cerrados
    D_lim: int = 0              # D exactamente en el último límite k·V
    ts_max: int = -1
    t_ini: int | None = None    # apertura del bucket abierto (si abrió en un bloque anterior)
    i_ini: int | None = None    # índice global de su primer trade
    sin_lado: int = 0


def _tiempo_monotono(arr, c) -> np.ndarray:
    ts = arr["ts_event"].astype(np.int64)
    ts[0] = max(int(ts[0]), c.ts_max)
    ts = np.maximum.accumulate(ts)
    c.ts_max = int(ts[-1])
    return ts


def _bloque_buckets(arr: np.ndarray, c: _Arrastre, V: int):
    ts = _tiempo_monotono(arr, c)                                           # R4
    es_trade = arr["action"] == b"T"
    signo = (arr["side"] == b"B").astype(np.int64) - (arr["side"] == b"A").astype(np.int64)
    tam = arr["size"].astype(np.int64)          # [v2] uint32 → int64 ANTES de cualquier resta
    c.sin_lado += int(tam[es_trade & (signo == 0)].sum())
    m = es_trade & (signo != 0)                                             # R1
    if not m.any():
        return None
    ts, s, tam = ts[m], signo[m], tam[m]
    precio, iid = arr["price"][m], arr["instrument_id"][m]
    n = len(tam)

    # Curvas acumuladas: volumen C y desbalance D. Entre trades D es lineal en C, así que
    # D en cualquier límite L = k·V se obtiene exacto aunque un trade cruce varios límites (R2).
    C = c.C + np.cumsum(tam)
    D = c.D + np.cumsum(s * tam)
    C_prev = np.concatenate(([c.C], C[:-1]))
    D_prev = np.concatenate(([c.D], D[:-1]))

    filas = None
    k_fin = int(C[-1] // V)
    if k_fin > c.k:
        kk = np.arange(c.k + 1, k_fin + 1, dtype=np.int64)
        L = kk * V
        i = np.searchsorted(C, L, side="left")                  # trade que completa cada bucket
        D_L = D_prev[i] + s[i] * (L - C_prev[i])
        oi = D_L - np.concatenate(([c.D_lim], D_L[:-1]))        # R3
        j = np.searchsorted(C, L - V, side="right")             # primer trade con volumen en él
        abrio_antes = (L - V) < c.C
        t_ini = np.where(abrio_antes, c.t_ini if c.t_ini is not None else 0, ts[np.minimum(j, n - 1)])
        i_ini = np.where(abrio_antes, c.i_ini if c.i_ini is not None else 0, c.g + j)
        filas = pd.DataFrame({"k": kk, "t_ini": t_ini, "t_fin": ts[i], "oi": oi,
                              "n_trades": c.g + i - i_ini + 1,                # R5
                              "precio": precio[i], "instrumento": iid[i]})
        c.D_lim = int(D_L[-1])

    # bucket abierto al terminar el bloque
    L_abierto = k_fin * V
    if C[-1] > L_abierto:
        if L_abierto >= c.C:                                    # abrió dentro de este bloque
            j = int(np.searchsorted(C, L_abierto, side="right"))
            c.t_ini, c.i_ini = int(ts[j]), c.g + j
    else:
        c.t_ini = c.i_ini = None
    c.k = k_fin
    c.C, c.D, c.g = int(C[-1]), int(D[-1]), c.g + n
    return filas


def procesar_buckets_vectorizado(store, V: int, cfg: Config) -> tuple[pd.DataFrame, int]:
    c = _Arrastre()
    partes = []
    for arr in store.to_ndarray(count=cfg.tam_bloque):
        if len(arr):
            f = _bloque_buckets(arr, c, int(V))
            if f is not None:
                partes.append(f)
    filas = pd.concat(partes, ignore_index=True) if partes else []
    return _tabla_buckets(filas), c.sin_lado


def procesar_buckets(store, V: int, cfg: Config, motor: str = "vectorizado"):
    if motor == "incremental":
        m = MotorVPIN(V)
        for rec in store:
            if isinstance(rec, (db.TradeMsg, db.MBP1Msg)):
                m.procesar(rec)
        return m.buckets(), m.sin_lado
    return procesar_buckets_vectorizado(store, V, cfg)


# =============================================================================
# 4. CALENDARIO DE CME, CALIBRACIÓN DE V Y BARRAS DE 1 MINUTO
# =============================================================================
def fecha_sesion_cme(t: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """La sesión de CME abre 17:00 hora de Chicago del día anterior: +7 h cae en su fecha."""
    return (t.tz_convert(TZ_CME).tz_localize(None) + pd.Timedelta(hours=7)).normalize()


def fin_sesion_cme(fecha) -> pd.Timestamp:
    """Cierre de la sesión (16:00 hora de Chicago) en UTC."""
    local = pd.Timestamp(fecha).normalize() + pd.Timedelta(hours=16)
    return local.tz_localize(TZ_CME).tz_convert("UTC")


def _cierres_cme(t0_ns: int, t1_ns: int) -> tuple[np.ndarray, np.ndarray]:
    """[v3] Intervalos con el mercado CERRADO que tocan [t0, t1], en ns UTC: la pausa diaria (16:00-17:00 de
    Chicago, lunes a jueves) y el fin de semana (viernes 16:00 → domingo 17:00). Los feriados no se cuentan."""
    d0 = pd.Timestamp(int(t0_ns), tz="UTC").tz_convert(TZ_CME).tz_localize(None).normalize() - pd.Timedelta(days=3)
    d1 = pd.Timestamp(int(t1_ns), tz="UTC").tz_convert(TZ_CME).tz_localize(None).normalize() + pd.Timedelta(days=3)
    A, B = [], []
    for d in pd.date_range(d0, d1, freq="D"):
        dia = d.weekday()
        if dia > 4:
            continue
        a = d + pd.Timedelta(hours=16)
        b = d + pd.Timedelta(days=2 if dia == 4 else 0, hours=17)
        A.append(a.tz_localize(TZ_CME).tz_convert("UTC").value)
        B.append(b.tz_localize(TZ_CME).tz_convert("UTC").value)
    return np.array(A, np.int64), np.array(B, np.int64)


def minutos_mercado(t_ini, t_fin) -> np.ndarray:
    """[v3] Minutos con el mercado ABIERTO entre t_ini y t_fin (ns UTC; NaN donde falte alguno). La v2 contaba el
    reloj de pared: una ventana que cruzaba el fin de semana parecía 49 horas más lenta."""
    ti = np.atleast_1d(np.asarray(t_ini, dtype=np.float64))
    tf = np.atleast_1d(np.asarray(t_fin, dtype=np.float64))
    ok = np.isfinite(ti) & np.isfinite(tf)
    out = np.full(ti.shape, np.nan)
    if not ok.any():
        return out
    a_i, a_f = ti[ok].astype(np.int64), tf[ok].astype(np.int64)
    A, B = _cierres_cme(int(min(a_i.min(), a_f.min())), int(max(a_i.max(), a_f.max())))
    largo = B - A
    acum = np.concatenate(([0], np.cumsum(largo)))

    def cerrado(t):
        i = np.searchsorted(A, t, side="right") - 1
        dentro = np.where(i >= 0, np.clip(t - A[np.maximum(i, 0)], 0, largo[np.maximum(i, 0)]), 0)
        return np.where(i >= 0, acum[np.maximum(i, 0)], 0) + dentro
    out[ok] = ((a_f - cerrado(a_f)) - (a_i - cerrado(a_i))) / NS_MIN
    return out


def volumen_por_sesion(store, cfg: Config) -> pd.Series:
    partes = []
    for arr in store.to_ndarray(count=cfg.tam_bloque):
        m = arr["action"] == b"T"
        if m.any():
            ses = fecha_sesion_cme(pd.to_datetime(arr["ts_event"][m].astype(np.int64), utc=True))
            partes.append(pd.Series(arr["size"][m].astype(np.int64), index=ses).groupby(level=0).sum())
    if not partes:
        return pd.Series(dtype=np.int64)
    return pd.concat(partes).groupby(level=0).sum()


def calibrar(store, cfg: Config, t_eval: pd.Timestamp | None = None,
             imprimir: bool = True) -> tuple[int, pd.Timestamp | None, pd.Series]:
    """V = mediana del volumen por sesión / buckets_por_dia, solo con sesiones COMPLETAS.
    [v3] Con historia (t_eval): las últimas `dias_calibracion` sesiones que terminan antes de t_eval, y las alertas y
    la evaluación empiezan en t_eval. Sin historia (--archivo): las primeras sesiones del archivo, como la v2.
    Una sesión es completa si tiene al menos la mitad del volumen mediano (fuera la primera a medias y los feriados)."""
    vol = volumen_por_sesion(store, cfg)
    if cfg.volumen_bucket:
        return int(cfg.volumen_bucket), t_eval, vol
    if vol.empty:
        sys.exit("No hay trades para calibrar el tamaño del bucket.")
    if t_eval is not None:
        fines = pd.DatetimeIndex([fin_sesion_cme(d) for d in vol.index])
        previas = vol[np.asarray(fines <= t_eval)]
        completas = previas[previas >= 0.5 * previas.median()] if len(previas) else previas
        usar = completas.iloc[-cfg.dias_calibracion:]
        if len(usar) >= 3:
            V = max(1, int(round(float(usar.median()) / cfg.buckets_por_dia)))
            if imprimir:
                print(f"🔧 V = mediana de las {len(usar)} sesiones completas antes de la evaluación "
                      f"({int(usar.median()):,} contratos) / {cfg.buckets_por_dia} = {V:,} contratos")
            return V, t_eval, vol
        if imprimir:
            print("⚠️  No hay sesiones completas antes de la evaluación: calibro con las primeras (como la v2). "
                  "Sube historia_dias.")
    completas = vol[vol >= 0.5 * vol.median()]
    k = min(cfg.dias_calibracion_archivo, len(completas))
    if k == len(completas) and imprimir:
        print("⚠️  Hay pocas sesiones: todo el rango se usa para calibrar V y no queda tramo "
              "para alertas ni evaluación. Descarga más días o fija volumen_bucket.")
    V = max(1, int(round(float(completas.iloc[:k].median()) / cfg.buckets_por_dia)))
    if imprimir:
        print(f"🔧 V = mediana de las primeras {k} sesiones completas ({int(completas.iloc[:k].median()):,}) / "
              f"{cfg.buckets_por_dia} = {V:,} contratos")
    return V, fin_sesion_cme(completas.index[k - 1]), vol


def barras_minuto(store, cfg: Config) -> pd.DataFrame:
    """Último precio, volumen e instrumento por minuto (índice = inicio del minuto, UTC)."""
    partes = []
    ts_max = -1
    for arr in store.to_ndarray(count=cfg.tam_bloque):
        if not len(arr):
            continue
        ts = arr["ts_event"].astype(np.int64)
        ts[0] = max(int(ts[0]), ts_max)
        ts = np.maximum.accumulate(ts)
        ts_max = int(ts[-1])
        m = arr["action"] == b"T"
        if not m.any():
            continue
        partes.append(pd.DataFrame({
            "minuto": ts[m] // NS_MIN,
            "precio": arr["price"][m] / PRICE_SCALE,
            "volumen": arr["size"][m].astype(np.int64),
            "instrumento": arr["instrument_id"][m].astype(np.int64),
        }).groupby("minuto").agg(precio=("precio", "last"), volumen=("volumen", "sum"),
                                 instrumento=("instrumento", "last")))
    if not partes:
        return pd.DataFrame(columns=["precio", "volumen", "instrumento"],
                            index=pd.DatetimeIndex([], tz="UTC", name="minuto"))
    todo = pd.concat(partes)
    g = todo.groupby(level=0)
    res = pd.DataFrame({"precio": g["precio"].last(), "volumen": g["volumen"].sum(),
                        "instrumento": g["instrumento"].last()})
    res.index = pd.to_datetime(res.index.to_numpy(dtype=np.int64) * NS_MIN, utc=True)
    res.index.name = "minuto"
    return res


# =============================================================================
# 5. VPIN, PERCENTIL Y ALERTAS
# =============================================================================
def percentil_movil(x: pd.Series, ventana: int, min_obs: int, rezago: int = 1) -> pd.Series:
    """Percentil de x_t dentro de x_{t-rezago-ventana+1} … x_{t-rezago} (rango medio en empates).
    [v3] rezago = n_buckets: VPIN_{t-n} y VPIN_t no comparten ni un bucket, así que la referencia no se compara
    consigo misma. Con rezago = 1 es exactamente el de la v2. Por bloques, para no armar una matriz gigante."""
    v = x.to_numpy(dtype=np.float64)
    n = len(v)
    out = np.full(n, np.nan)
    if n == 0:
        return pd.Series(out, index=x.index)
    vv = np.concatenate((np.full(ventana + rezago - 1, np.nan), v))
    for a in range(0, n, 2048):
        b = min(n, a + 2048)
        ref = sliding_window_view(vv[a:b + ventana - 1], ventana)        # fila j: la referencia de x_{a+j}
        actual = v[a:b, None]
        validos = np.sum(~np.isnan(ref), axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            pct = (np.sum(ref < actual, axis=1) + 0.5 * np.sum(ref == actual, axis=1)) / validos
        pct[(validos < min_obs) | np.isnan(v[a:b])] = np.nan
        out[a:b] = pct
    return pd.Series(out, index=x.index)


def calcular_vpin(buckets: pd.DataFrame, V: int, cfg: Config) -> pd.DataFrame:
    df = buckets.copy()
    n = cfg.n_buckets
    df["compras"] = (V + df["oi"]) // 2
    df["ventas"] = V - df["compras"]
    # VPIN = Σ|compras - ventas| / (n·V) sobre los últimos n buckets  (ELO 2012)
    df["vpin"] = df["oi"].abs().rolling(n, min_periods=n).sum() / (n * V)
    # Misma ventana con signo: + = domina la compra agresiva, - = la venta. Está en [-1, 1].
    df["desbalance"] = df["oi"].rolling(n, min_periods=n).sum() / (n * V)
    df["vpin_pct"] = percentil_movil(df["vpin"], cfg.ventana_pct, cfg.min_obs_pct, rezago_de(cfg))    # [v3]
    t_ini, t_fin = _ns(df["t_ini"]).astype(np.float64), _ns(df["t_fin"]).astype(np.float64)
    df["duracion_min"] = minutos_mercado(t_ini, t_fin)                                               # [v3]
    # minutos DE MERCADO que tardaron en llenarse los n buckets de la ventana (lento = poco volumen)
    t_ini_ventana = pd.Series(t_ini).shift(n - 1).to_numpy()
    df["minutos_ventana"] = minutos_mercado(t_ini_ventana, t_fin)                                    # [v3]
    return df


class EstadoVPIN:
    """[v3] Lo mismo que calcular_vpin para el ÚLTIMO bucket, incremental (Live): el VPIN, el desbalance y su
    percentil contra la misma referencia rezagada. La autoprueba exige que coincida fila por fila."""

    def __init__(self, V: int, cfg: Config):
        self.V, self.n = int(V), cfg.n_buckets
        self.W, self.min_obs, self.rezago = cfg.ventana_pct, cfg.min_obs_pct, rezago_de(cfg)
        self.oi: deque = deque(maxlen=self.n)
        self.previos: deque = deque(maxlen=self.W + self.rezago - 1)

    def agregar(self, fila: dict) -> dict:
        self.oi.append(int(fila["oi"]))
        vpin = des = np.nan
        if len(self.oi) == self.n:
            vpin = float(sum(abs(o) for o in self.oi)) / (self.n * self.V)
            des = float(sum(self.oi)) / (self.n * self.V)
        prev = list(self.previos)
        ref = np.array(prev[:max(0, len(prev) - (self.rezago - 1))], dtype=np.float64)
        validos = int(np.sum(~np.isnan(ref)))
        pct = np.nan
        if np.isfinite(vpin) and validos >= self.min_obs:
            pct = (np.sum(ref < vpin) + 0.5 * np.sum(ref == vpin)) / validos
        self.previos.append(vpin)
        return {"k": fila["k"], "vpin": vpin, "desbalance": des, "vpin_pct": pct,
                "t_fin": pd.Timestamp(int(fila["t_fin"]), tz="UTC"), "precio": fila["precio"] / PRICE_SCALE}


class DetectorToxicidad:
    """Una alerta por episodio: dispara al cruzar el umbral, se rearma al bajar de `rearme`.
    Un cruce dentro del cooldown se consume sin avisar."""

    def __init__(self, umbral: float, rearme: float, cooldown_ns: int):
        self.umbral, self.rearme, self.cooldown_ns = umbral, rearme, cooldown_ns
        self.armado = True
        self.t_ultimo: int | None = None

    def actualizar(self, t_ns: int, p: float) -> bool:
        if p is None or not np.isfinite(p):
            return False
        if p <= self.rearme:
            self.armado = True
        if p >= self.umbral and self.armado:
            self.armado = False
            if self.t_ultimo is None or t_ns - self.t_ultimo >= self.cooldown_ns:
                self.t_ultimo = t_ns
                return True
        return False


def _nuevo_detector(cfg: Config) -> DetectorToxicidad:
    return DetectorToxicidad(cfg.umbral_pct, cfg.rearme_pct, cfg.cooldown_min * NS_MIN)


def detectar_alertas(df: pd.DataFrame, cfg: Config, t_senales: pd.Timestamp | None) -> pd.DataFrame:
    det = _nuevo_detector(cfg)
    desde = t_senales.value if t_senales is not None else -1
    filas = []
    t_ns = _ns(df["t_fin"])
    for k, t, p in zip(df.index, t_ns, df["vpin_pct"].to_numpy()):
        if det.actualizar(int(t), float(p)) and t >= desde:
            filas.append(k)
    al = df.loc[filas, ["t_fin", "vpin", "vpin_pct", "desbalance", "precio"]].copy()
    al["lado"] = np.where(al["desbalance"] >= 0, "compras", "ventas")
    return al


def imprimir_alertas(alertas: pd.DataFrame) -> None:
    if alertas.empty:
        print("\nSin alertas de toxicidad con los umbrales actuales.")
        return
    print(f"\n⚠️  {len(alertas)} alertas de toxicidad (hora CDMX, al cierre del bucket):")
    for k, r in alertas.iterrows():
        t = r["t_fin"].tz_convert(TZ_LOCAL)
        print(f"  {t:%a %d-%m %H:%M}  bucket {k:>5}  VPIN={r['vpin']:.3f}  percentil={r['vpin_pct']:.2f}  "
              f"domina {r['lado']:<7} ({r['desbalance']:+.3f})  precio={r['precio']:,.2f}")


# =============================================================================
# 6. EVALUACIÓN: ¿el VPIN anticipa volatilidad más allá de lo obvio?
# =============================================================================
class Ventanas:
    """Sumas por ventanas de minutos con sumas acumuladas (O(1) por consulta). [v3] Más la volatilidad TÍPICA de
    cada hora del día y la sesión de cada minuto (para el bootstrap por sesiones)."""

    def __init__(self, minutos: pd.DataFrame):
        idx = pd.date_range(minutos.index[0], minutos.index[-1], freq="1min")
        self.t0 = idx[0].value
        p = minutos["precio"].reindex(idx)
        inst = minutos["instrumento"].reindex(idx)
        r = np.log(p).diff()
        r[inst != inst.shift(1)] = np.nan                   # rolls y huecos no cuentan
        self.n = len(idx)
        self.cs_r2 = np.concatenate(([0.0], np.cumsum(np.nan_to_num(r.to_numpy() ** 2))))
        self.cs_ok = np.concatenate(([0], np.cumsum(r.notna().to_numpy())))
        self.cs_vol = np.concatenate(([0], np.cumsum(minutos["volumen"].reindex(idx).fillna(0).to_numpy())))
        self.precio = p.to_numpy()
        inst_ff = inst.ffill()
        cambio = (inst_ff != inst_ff.shift(1)).to_numpy(copy=True)
        cambio[0] = False
        self.cs_inst_cambio = np.concatenate(([0], np.cumsum(cambio)))
        loc = idx.tz_convert(TZ_CME)                                           # [v3]
        self.sesion = fecha_sesion_cme(idx).as_unit("ns").asi8
        self.clave = ((loc.hour.to_numpy() * 60 + loc.minute.to_numpy()) - 17 * 60) % 1440   # minuto desde las 17:00 CT
        self._estacional: dict = {}

    def minuto_de(self, t_ns: np.ndarray) -> np.ndarray:
        return (t_ns // NS_MIN * NS_MIN - self.t0) // NS_MIN

    def _rango(self, a, b, h):
        ok = (a >= 0) & (b < self.n)
        a2, b2 = np.clip(a, 0, self.n - 1), np.clip(b, 0, self.n - 1)
        cobertura = (self.cs_ok[b2 + 1] - self.cs_ok[a2]) / h
        return ok & (cobertura >= 0.8), a2, b2

    def rv(self, m0: np.ndarray, h: int, futuro: bool) -> np.ndarray:
        """Volatilidad realizada (pb) con retornos de 1 min: futuro = (m0, m0+h], pasado = [m0-h, m0-1]."""
        a, b = (m0 + 1, m0 + h) if futuro else (m0 - h, m0 - 1)
        ok, a2, b2 = self._rango(a, b, h)
        rv = np.sqrt(self.cs_r2[b2 + 1] - self.cs_r2[a2]) * 1e4
        return np.where(ok, rv, np.nan)

    def rv_estacional(self, m0: np.ndarray, h: int, sesiones: int, min_ses: int) -> np.ndarray:
        """[v3] La volatilidad futura TÍPICA a esa hora del día: el promedio de la RV futura (mismo horizonte) al
        mismo minuto de la sesión en las `sesiones` sesiones ANTERIORES. Sin mirar el futuro: la ventana de la sesión
        anterior termina antes de que empiece la de hoy."""
        if h not in self._estacional:
            todos = self.rv(np.arange(self.n), h, futuro=True)
            tabla = pd.DataFrame({"s": self.sesion, "c": self.clave, "rv": todos}).dropna()
            piv = tabla.pivot_table(index="s", columns="c", values="rv", aggfunc="mean").sort_index()
            self._estacional[h] = piv.shift(1).rolling(sesiones, min_periods=min_ses).mean()
        est = self._estacional[h]
        m0 = np.asarray(m0)
        dentro = (m0 >= 0) & (m0 < self.n)
        mc = np.clip(m0, 0, self.n - 1)
        fila = est.index.get_indexer(self.sesion[mc])
        col = est.columns.get_indexer(self.clave[mc])
        out = np.full(m0.shape, np.nan)
        ok = dentro & (fila >= 0) & (col >= 0)
        out[ok] = est.to_numpy()[fila[ok], col[ok]]
        return out

    def sesion_de(self, m0: np.ndarray) -> np.ndarray:
        return self.sesion[np.clip(m0, 0, self.n - 1)]

    def horas_fijas(self, m0: np.ndarray) -> list[np.ndarray]:
        """[v3] Una columna 0/1 por hora de la sesión (menos una): con ellas como control, el IC compara cada bucket
        solo contra buckets de la MISMA hora. Hace falta porque el VPIN también tiene su patrón por hora (las
        operaciones del horario regular son más grandes: más desbalance por bucket aunque el flujo no informe nada)."""
        hora = self.clave[np.clip(m0, 0, self.n - 1)] // 60
        presentes = np.unique(hora)
        return [(hora == h).astype(np.float64) for h in presentes[1:]]

    def ultima_sesion(self, m0: np.ndarray, minutos: int = 23 * 60) -> tuple[np.ndarray, np.ndarray]:
        """[v3] La volatilidad realizada (pb) y el volumen de los últimos `minutos` minutos CON retorno válido antes
        de m0, saltando la pausa diaria y el fin de semana: qué tan agitado viene el mercado (la persistencia de los
        días agitados mueve a la vez el VPIN y la volatilidad futura)."""
        m = np.clip(m0, 0, self.n - 1)
        fin = self.cs_ok[m]                                   # retornos válidos en [0, m0)
        a = np.searchsorted(self.cs_ok, fin - minutos, side="left")
        ok = (np.asarray(m0) >= 0) & (fin >= minutos)
        a2 = np.clip(a, 0, self.n)
        rv = np.sqrt(np.maximum(self.cs_r2[m] - self.cs_r2[a2], 0)) * 1e4
        vol = self.cs_vol[m] - self.cs_vol[a2]
        return np.where(ok, rv, np.nan), np.where(ok, np.log1p(vol), np.nan)

    def volumen_pasado(self, m0: np.ndarray, h: int) -> np.ndarray:
        a, b = m0 - h, m0 - 1
        ok = a >= 0
        a2, b2 = np.clip(a, 0, self.n - 1), np.clip(b, 0, self.n - 1)
        return np.where(ok, self.cs_vol[b2 + 1] - self.cs_vol[a2], np.nan)

    def retorno_futuro(self, m0: np.ndarray, precio_base: np.ndarray, h: int, tick: float) -> np.ndarray:
        a, b = m0 + 1, m0 + h
        ok, a2, b2 = self._rango(a, b, h)
        sin_roll = (self.cs_inst_cambio[b2 + 1] - self.cs_inst_cambio[np.clip(m0, 0, self.n - 1) + 1]) == 0
        fin = self.precio[b2]
        return np.where(ok & sin_roll & np.isfinite(fin), (fin - precio_base) / tick, np.nan)


def _rangos(v: np.ndarray) -> np.ndarray:
    """Rangos (1…n) con el promedio en los empates, en numpy (el bootstrap los calcula miles de veces)."""
    v = np.asarray(v, dtype=np.float64)
    n = v.size
    o = np.argsort(v, kind="mergesort")
    vs = v[o]
    cortes = np.flatnonzero(vs[1:] != vs[:-1]) + 1
    ini, fin = np.concatenate(([0], cortes)), np.concatenate((cortes, [n]))
    r = np.empty(n)
    r[o] = np.repeat((ini + fin + 1) / 2.0, fin - ini)
    return r


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    a, b = a - a.mean(), b - b.mean()
    d = math.sqrt(float(np.dot(a, a)) * float(np.dot(b, b)))
    return float(np.dot(a, b)) / d if d > 0 else np.nan


def _ic(x: np.ndarray, y: np.ndarray, Z: np.ndarray | None = None, fijos: np.ndarray | None = None) -> float:
    """Correlación de Spearman de x con y; con controles, la PARCIAL: la de los residuos de rangos después de quitar
    lo que explican los rangos de los controles Z (la de la v2) y las columnas 0/1 `fijos` (las horas, sin rango:
    el rango de una columna 0/1 es la misma columna escalada)."""
    rx, ry = _rangos(x), _rangos(y)
    cols = [_rangos(z) for z in Z.T] if Z is not None else []
    if fijos is not None and fijos.shape[1]:
        cols.append(fijos)
    if not cols:
        return _corr(rx, ry)
    R = np.column_stack([np.ones(x.size)] + cols)
    Y = np.column_stack([rx, ry])
    E = Y - R @ np.linalg.lstsq(R, Y, rcond=None)[0]
    return _corr(E[:, 0], E[:, 1])


def _p_t(z: float, gl: int) -> float:
    """p de dos colas de una t de Student con gl grados de libertad (scipy si está; si no, la normal)."""
    try:
        from scipy.stats import t as t_student
        return float(2 * t_student.sf(abs(z), gl))
    except ImportError:
        return math.erfc(abs(z) / math.sqrt(2))


def ic_bootstrap(x, y, controles, sesiones, cfg: Config, rng: np.random.Generator, fijos=None) -> dict:
    """[v3] El IC y su incertidumbre con un bootstrap por BLOQUES DE SESIONES: se remuestrean días enteros, en
    bloques de `bloque_sesiones`, porque dentro de un día los buckets (y su VPIN, que persiste ~1 sesión) no son
    independientes. p = IC / (error estándar del bootstrap) contra una t con (bloques − 1) grados de libertad: con
    pocos bloques el bootstrap subestima la varianza, y la t lo compensa (medido en --simular)."""
    x, y = np.asarray(x, np.float64), np.asarray(y, np.float64)
    Z = np.column_stack(controles).astype(np.float64) if controles else None
    Fj = np.column_stack(fijos).astype(np.float64) if fijos else None
    m = np.isfinite(x) & np.isfinite(y)
    if Z is not None:
        m &= np.all(np.isfinite(Z), axis=1)
    ses = np.asarray(sesiones)[m]
    uniq, inv = np.unique(ses, return_inverse=True)
    out = {"IC": np.nan, "lo": np.nan, "hi": np.nan, "p": np.nan, "n": int(m.sum()), "sesiones": int(uniq.size)}
    if m.sum() < 30 or uniq.size < 4:
        return out
    x, y = x[m], y[m]
    Z = Z[m] if Z is not None else None
    Fj = Fj[m] if Fj is not None else None
    ic = _ic(x, y, Z, Fj)
    grupos = [np.flatnonzero(inv == s) for s in range(uniq.size)]
    S = uniq.size
    L = max(1, min(cfg.bloque_sesiones, S))
    nb = int(math.ceil(S / L))
    reps = np.empty(cfg.bootstrap)
    for b in range(cfg.bootstrap):
        ini = rng.integers(0, S - L + 1, nb)
        sel = (ini[:, None] + np.arange(L)).ravel()[:S]
        idx = np.concatenate([grupos[s] for s in sel])
        reps[b] = _ic(x[idx], y[idx], Z[idx] if Z is not None else None, Fj[idx] if Fj is not None else None)
    se = float(np.nanstd(reps, ddof=1))
    lo, hi = np.nanquantile(reps, [0.05, 0.95])
    p = _p_t(ic / se, max(1, nb - 1)) if se > 0 and np.isfinite(ic) else np.nan
    out.update(IC=ic, lo=float(lo), hi=float(hi), p=p, se=se)
    return out


def _spearman(x, y) -> float:
    m = np.isfinite(x) & np.isfinite(y)
    return _ic(x[m], y[m]) if m.sum() >= 30 else np.nan


def _t_v2(r: float, n_eff: float, k: int = 0) -> float:
    """El t de la v2 (solo para comparar en --simular)."""
    gl = n_eff - 2 - k
    if not np.isfinite(r) or gl <= 1 or abs(r) >= 1:
        return np.nan
    return r * math.sqrt(gl / (1 - r * r))


def evaluar(df: pd.DataFrame, alertas: pd.DataFrame, minutos: pd.DataFrame, cfg: Config,
            t_senales: pd.Timestamp | None, imprimir: bool = True) -> dict:
    ven = Ventanas(minutos)
    desde = t_senales if t_senales is not None else df["t_fin"].min()
    ev = df[df["vpin"].notna() & (df["t_fin"] >= desde)]
    res: dict = {"n_buckets": len(ev)}
    if len(ev) < 30:
        if imprimir:
            print("\nMuy pocos buckets después del calentamiento para evaluar. Usa un rango más largo.")
        return res
    t_ns = _ns(ev["t_fin"])
    m0 = ven.minuto_de(t_ns)
    ses = ven.sesion_de(m0)
    span_min = (t_ns[-1] - t_ns[0]) / NS_MIN
    vp = ev["vpin_pct"].to_numpy()
    rng = np.random.default_rng(cfg.semilla)
    res["sesiones"] = int(np.unique(ses).size)
    horas = ven.horas_fijas(m0)
    rv_dia, vol_dia = ven.ultima_sesion(m0)

    # 1) Relación mecánica con la actividad (crítica de Andersen & Bondarenko), en minutos DE MERCADO
    res["mecanica"] = _spearman(ev["vpin"].to_numpy(), ev["minutos_ventana"].to_numpy())

    # 2) Poder predictivo sobre la volatilidad futura: crudo y descontando la hora del día, la volatilidad y el
    #    volumen recientes. [v3] Intervalos y p por bootstrap de sesiones.
    filas = []
    for h in cfg.horizontes_min:
        fut = ven.rv(m0, h, futuro=True)
        rv_p = ven.rv(m0, h, futuro=False)
        vol_p = np.log1p(ven.volumen_pasado(m0, h))
        est = ven.rv_estacional(m0, h, cfg.sesiones_estacionalidad, cfg.min_sesiones_estacionalidad)
        crudo = ic_bootstrap(vp, fut, [], ses, cfg, rng)
        parcial = ic_bootstrap(vp, fut, [rv_p, vol_p, est, rv_dia, vol_dia], ses, cfg, rng, fijos=horas)
        n_eff = min(len(ev), span_min / h)
        m2 = np.all(np.isfinite(np.column_stack([vp, fut, rv_p, vol_p])), axis=1)          # el parcial de la v2
        ic_par_v2 = _ic(vp[m2], fut[m2], np.column_stack([rv_p, vol_p])[m2]) if m2.sum() >= 30 else np.nan
        filas.append({"h_min": h, "n": crudo["n"], "sesiones": parcial["sesiones"],
                      "IC_VPIN": crudo["IC"], "IC_lo": crudo["lo"], "IC_hi": crudo["hi"], "p_VPIN": crudo["p"],
                      "IC_parcial": parcial["IC"], "par_lo": parcial["lo"], "par_hi": parcial["hi"], "p_parcial": parcial["p"],
                      "IC_vol_pasada": _spearman(rv_p, fut), "IC_volumen": _spearman(vol_p, fut),
                      "IC_hora_del_dia": _spearman(est, fut),
                      "t_v2": _t_v2(crudo["IC"], n_eff), "t_v2_parcial": _t_v2(ic_par_v2, n_eff, 2)})
    res["ic"] = pd.DataFrame(filas)
    alfa_b = cfg.alfa / len(cfg.horizontes_min)
    res["significativos"] = [int(r.h_min) for r in res["ic"].itertuples() if r.p_parcial < alfa_b and r.IC_parcial > 0]

    # 3) Estudio de eventos: ¿la volatilidad sube tras las alertas MÁS que lo típico de esa hora?
    filas = []
    if len(alertas):
        m_al = ven.minuto_de(_ns(alertas["t_fin"]))
        for h in cfg.horizontes_min:
            args = (h, cfg.sesiones_estacionalidad, cfg.min_sesiones_estacionalidad)
            r_todos = ven.rv(m0, h, True) / ven.rv_estacional(m0, *args)
            r_al = ven.rv(m_al, h, True) / ven.rv_estacional(m_al, *args)
            ok = np.isfinite(r_al)
            med_todos = np.nanmedian(r_todos)
            filas.append({"h_min": h, "n": int(ok.sum()), "alertas_vs_su_hora": np.nanmedian(r_al) if ok.any() else np.nan,
                          "todos_vs_su_hora": med_todos,
                          "alertas_vs_todos": (np.nanmedian(r_al) / med_todos) if ok.any() else np.nan,
                          "pct_sobre_mediana": float(np.mean(r_al[ok] > med_todos)) if ok.any() else np.nan})
    res["eventos"] = pd.DataFrame(filas)

    # 4) Dirección: ¿el desbalance con signo anticipa el precio?
    filas = []
    tick = tick_de(cfg)
    for h in cfg.horizontes_min:
        ret = ven.retorno_futuro(m0, ev["precio"].to_numpy(), h, tick)
        d = ic_bootstrap(ev["desbalance"].to_numpy(), ret, [], ses, cfg, rng)
        filas.append({"h_min": h, "n": d["n"], "IC": d["IC"], "IC_lo": d["lo"], "IC_hi": d["hi"], "p": d["p"]})
    res["direccion"] = pd.DataFrame(filas)

    if imprimir:
        _imprimir_evaluacion(res, alertas, ev, cfg)
    return res


def _imprimir_evaluacion(res: dict, alertas: pd.DataFrame, ev: pd.DataFrame, cfg: Config) -> None:
    linea = "=" * 100
    f3 = lambda v: f"{v:+.3f}" if np.isfinite(v) else "   —  "   # noqa: E731
    fp = lambda v: ("<0.001" if v < 0.001 else f"{v:.3f}") if np.isfinite(v) else "  —  "   # noqa: E731
    print(f"\n{linea}\nEVALUACIÓN (desde el fin del calentamiento; volatilidad realizada con retornos de 1 min)\n{linea}")
    dias = max((ev["t_fin"].iloc[-1] - ev["t_fin"].iloc[0]).total_seconds() / 86400, 1e-9)
    print(f"Buckets evaluados: {res['n_buckets']:,} en {res['sesiones']} sesiones  ·  alertas: {len(alertas)} "
          f"(≈ {len(alertas) / dias * 5:.1f} por semana de 5 días)")
    print(f"\n1) Relación mecánica: corr(VPIN, minutos de mercado que tardó la ventana) = {res['mecanica']:+.2f}")
    print("   Cuanto más lejos de 0, más se mueve el VPIN con la velocidad del volumen (+ = sube cuando el\n"
          "   mercado está lento, − = cuando está acelerado). Por eso importa el IC parcial.")
    print("\n2) ¿Anticipa la volatilidad? IC de Spearman entre el percentil del VPIN y la volatilidad futura.")
    print("   [intervalo 90 %] y p salen de remuestrear SESIONES enteras. 'Parcial' compara solo buckets de la misma hora\n"
          "   del día y descuenta la volatilidad típica de ese minuto, la volatilidad y el volumen del mismo horizonte y\n"
          "   los de la última sesión: es lo que el VPIN aporta de verdad.")
    print(f"   {'h':>5} {'buckets':>8} {'IC crudo':>9} {'[90 %]':>17} {'p':>7}   {'IC parcial':>10} {'[90 %]':>17} "
          f"{'p':>7}   {'IC hora':>8} {'IC vol.':>8} {'IC volumen':>10}")
    for r in res["ic"].itertuples():
        print(f"   {r.h_min:>4}m {r.n:>8,} {f3(r.IC_VPIN):>9} [{f3(r.IC_lo)}, {f3(r.IC_hi)}] {fp(r.p_VPIN):>7}   "
              f"{f3(r.IC_parcial):>10} [{f3(r.par_lo)}, {f3(r.par_hi)}] {fp(r.p_parcial):>7}   "
              f"{f3(r.IC_hora_del_dia):>8} {f3(r.IC_vol_pasada):>8} {f3(r.IC_volumen):>10}")
    alfa_b = cfg.alfa / len(cfg.horizontes_min)
    if res["significativos"]:
        print(f"   ✅ Más allá de la hora del día, la volatilidad y el volumen recientes, el VPIN anticipa volatilidad a "
              f"{', '.join(f'{h} min' for h in res['significativos'])} (p < {alfa_b:.4f}, Bonferroni).")
    else:
        print(f"   ➖ Más allá de la hora del día, la volatilidad y el volumen recientes, el VPIN no se distingue de cero "
              f"(p < {alfa_b:.4f} con Bonferroni en ningún horizonte).")
    if res["sesiones"] < 40:
        print(f"   ⚠️  {res['sesiones']} sesiones de evaluación: en mercados simulados CON información, la v3 la encuentra el 35 % de\n"
              "      las veces con 20 sesiones y el 70 % con 40. Con menos de ~40 sesiones (2 meses), un 'no se distingue de\n"
              "      cero' dice poco; un 'anticipa' sí es confiable (sin información sale ~0–5 % de las veces).")
    print("\n3) Después de cada alerta, la volatilidad futura contra la TÍPICA DE SU HORA (1.0 = lo de siempre):")
    if res["eventos"].empty:
        print("   (sin alertas)")
    else:
        print(res["eventos"].to_string(index=False, float_format=lambda v: f"{v:,.2f}"))
        if res["eventos"]["n"].max() < 30:
            print("   ⚠️  Menos de 30 alertas: es anecdótico, no estadístico. Usa más historial.")
    print("\n4) Dirección: IC entre el desbalance con signo y el retorno futuro (en ticks), con el mismo bootstrap.")
    for r in res["direccion"].itertuples():
        print(f"   {r.h_min:>4}m  IC {f3(r.IC)} [{f3(r.IC_lo)}, {f3(r.IC_hi)}]  p {fp(r.p)}  ({r.n:,} buckets)")


# =============================================================================
# 7. DASHBOARD (el de la v2)
# =============================================================================
def _romper_huecos(t: pd.Series | pd.DatetimeIndex, y: np.ndarray, hueco_min: float):
    t = pd.DatetimeIndex(t)
    y = np.asarray(y, dtype=np.float64)
    if len(t) < 2:
        return t, y
    cortes = np.flatnonzero(np.diff(_ns(t)) > hueco_min * NS_MIN)
    if cortes.size == 0:
        return t, y
    s = pd.Series(np.r_[y, np.full(cortes.size, np.nan)],
                  index=t.append(t[cortes] + pd.Timedelta(seconds=1))).sort_index(kind="stable")
    return s.index, s.to_numpy()


def graficar_dashboard(df: pd.DataFrame, alertas: pd.DataFrame, minutos: pd.DataFrame, cfg: Config,
                       V: int, t_senales: pd.Timestamp | None, ruta_png: Path, mostrar: bool = True) -> None:
    import matplotlib
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    C = {"fondo": "#fcfcfb", "tinta": "#0b0b0b", "tinta2": "#52514e", "tenue": "#898781",
         "grid": "#e1e0d9", "eje": "#c3c2b7", "compra": "#2a78d6", "venta": "#e34948",
         "aviso": "#fab219", "vpin": "#4a3aa7"}
    fig, ejes = plt.subplots(4, 1, figsize=(16, 11.5), sharex=True,
                             gridspec_kw={"height_ratios": [2.3, 1, 1, 1]})
    fig.subplots_adjust(left=0.07, right=0.98, bottom=0.07, top=0.87, hspace=0.12)
    fig.patch.set_facecolor(C["fondo"])
    for ax in ejes:
        ax.set_facecolor(C["fondo"])
        ax.grid(True, color=C["grid"], linewidth=0.6)
        ax.set_axisbelow(True)
        for lado in ("top", "right"):
            ax.spines[lado].set_visible(False)
        for lado in ("left", "bottom"):
            ax.spines[lado].set_color(C["eje"])
        ax.tick_params(colors=C["tenue"], labelsize=9)

    t = df["t_fin"].dt.tz_convert(TZ_LOCAL)
    toxico = (df["vpin_pct"] >= cfg.umbral_pct).to_numpy(copy=True)
    toxico[:-1] &= np.diff(_ns(df["t_fin"])) <= 180 * NS_MIN     # la zona no cruza fines de semana

    # --- Panel 1: precio (cierres de 1 min) + zonas y alertas ---
    ax = ejes[0]
    tp, yp = _romper_huecos(minutos.index, minutos["precio"].to_numpy(), 30)
    ax.plot(tp.tz_convert(TZ_LOCAL), yp, color=C["tinta"], linewidth=0.9)
    for a in ejes:
        a.fill_between(t, 0, 1, where=toxico, transform=a.get_xaxis_transform(),
                       color=C["aviso"], alpha=0.16, linewidth=0, step="post")
    if len(alertas):
        ax.scatter(alertas["t_fin"].dt.tz_convert(TZ_LOCAL), alertas["precio"], marker="D", s=60,
                   color=C["aviso"], edgecolors=C["tinta"], linewidths=0.9, zorder=4)
    if t_senales is not None:
        for a in ejes:
            a.axvline(t_senales.tz_convert(TZ_LOCAL), color=C["tenue"], linewidth=0.9)
        ax.annotate("inicio de la evaluación", (t_senales.tz_convert(TZ_LOCAL), 1), xycoords=("data", "axes fraction"),
                    xytext=(4, -12), textcoords="offset points", fontsize=8, color=C["tenue"])
    ax.set_ylabel("Precio (cierre 1 min)", color=C["tinta2"])
    leyenda = [Line2D([], [], ls="none", marker="D", ms=7, markerfacecolor=C["aviso"],
                      markeredgecolor=C["tinta"], label=f"Alerta de toxicidad (percentil ≥ {cfg.umbral_pct:.0%})"),
               Patch(facecolor=C["aviso"], alpha=0.35, label="Zona tóxica")]
    ax.legend(handles=leyenda, loc="lower left", bbox_to_anchor=(0, 1.0), ncols=2,
              frameon=False, fontsize=9, labelcolor=C["tinta2"])

    # --- Panel 2: VPIN ---
    ax = ejes[1]
    tv, yv = _romper_huecos(df["t_fin"], df["vpin"].to_numpy(), 180)
    ax.plot(tv.tz_convert(TZ_LOCAL), yv, color=C["vpin"], linewidth=1.1)
    ax.set_ylabel(f"VPIN ({cfg.n_buckets} buckets)", color=C["tinta2"])

    # --- Panel 3: percentil ---
    ax = ejes[2]
    tq, yq = _romper_huecos(df["t_fin"], df["vpin_pct"].to_numpy(), 180)
    ax.plot(tq.tz_convert(TZ_LOCAL), yq, color=C["tinta2"], linewidth=0.9)
    ax.axhline(cfg.umbral_pct, color=C["tinta"], linewidth=0.9, linestyle=(0, (4, 3)))
    ax.axhline(cfg.rearme_pct, color=C["tenue"], linewidth=0.8, linestyle=(0, (1, 3)))
    ax.fill_between(tq.tz_convert(TZ_LOCAL), yq, cfg.umbral_pct, where=np.nan_to_num(yq) >= cfg.umbral_pct,
                    color=C["aviso"], alpha=0.6, linewidth=0, interpolate=True)
    ax.set_ylim(0, 1.02)
    ax.set_ylabel("Percentil del VPIN", color=C["tinta2"])
    ax.text(1.0, cfg.umbral_pct, f" umbral {cfg.umbral_pct:.2f}", transform=ax.get_yaxis_transform(),
            va="bottom", ha="right", fontsize=8, color=C["tinta2"])

    # --- Panel 4: dirección (misma ventana, con signo) ---
    ax = ejes[3]
    td, yd = _romper_huecos(df["t_fin"], df["desbalance"].to_numpy(), 180)
    td = td.tz_convert(TZ_LOCAL)
    ax.axhline(0, color=C["eje"], linewidth=0.8)
    ax.plot(td, yd, color=C["tinta2"], linewidth=0.8)
    ax.fill_between(td, yd, 0, where=np.nan_to_num(yd) >= 0, color=C["compra"], alpha=0.35, linewidth=0, interpolate=True)
    ax.fill_between(td, yd, 0, where=np.nan_to_num(yd) < 0, color=C["venta"], alpha=0.35, linewidth=0, interpolate=True)
    lim = max(0.05, float(np.nanmax(np.abs(yd))) * 1.15) if np.isfinite(yd).any() else 0.1
    ax.set_ylim(-lim, lim)
    ax.set_ylabel("Desbalance (compras − ventas)", color=C["tinta2"])
    ax.legend(handles=[Patch(facecolor=C["compra"], alpha=0.6, label="domina la compra agresiva"),
                       Patch(facecolor=C["venta"], alpha=0.6, label="domina la venta agresiva")],
              loc="upper left", frameon=False, fontsize=8, labelcolor=C["tinta2"], ncols=2)

    ejes[-1].xaxis.set_major_locator(mdates.AutoDateLocator(tz=TZ_LOCAL))
    ejes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%d-%m\n%H:%M", tz=TZ_LOCAL))
    ejes[-1].set_xlabel("Hora CDMX (cierre de cada bucket)", color=C["tinta2"])

    ini, fin = t.iloc[0], t.iloc[-1]
    fig.text(0.07, 0.975, f"{cfg.symbol} · VPIN con reloj de volumen · 1 bucket = {V:,} contratos",
             ha="left", va="top", fontsize=15, fontweight="semibold", color=C["tinta"])
    fig.text(0.07, 0.948, f"{ini:%d-%m %H:%M} → {fin:%d-%m %H:%M} CDMX · {len(df):,} buckets · "
             f"ventana {cfg.n_buckets} buckets · percentil contra {cfg.ventana_pct} buckets que terminan "
             f"{rezago_de(cfg)} antes · {len(alertas)} alertas", ha="left", va="top", fontsize=10, color=C["tinta2"])

    ruta_png = Path(ruta_png)
    ruta_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(ruta_png, dpi=150, facecolor=C["fondo"], bbox_inches="tight")
    print(f"🖼️  Dashboard guardado en {ruta_png}")
    if mostrar and matplotlib.get_backend().lower() != "agg":
        plt.show()
    plt.close(fig)


# =============================================================================
# 8. DATOS (caché por día), RESULTADOS Y LIVE
# =============================================================================
def _nombre_seguro(*partes: str) -> str:
    texto = unicodedata.normalize("NFKD", "_".join(partes)).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9._-]+", "", texto)


def _ruta(carpeta: str) -> Path:
    p = Path(carpeta)
    return p if p.is_absolute() else CARPETA_SCRIPT / p


def _interactivo() -> bool:
    return sys.stdin is not None and sys.stdin.isatty()


def _limpiar_key(texto: str | None) -> str:
    """Quita lo que se cuela al pegar: marcas de pegado de la terminal (ESC[200~), comillas,
    espacios, saltos de línea y caracteres invisibles."""
    texto = re.sub(r"\x1b\[[0-9;]*[~A-Za-z]", "", texto or "")
    texto = "".join(ch for ch in texto if ch.isprintable() and not ch.isspace())
    return texto.strip("\"'")


def _mascara(key: str) -> str:
    return f"{key[:5]}…{key[-3:]} ({len(key)} caracteres)" if len(key) > 8 else f"({len(key)} caracteres)"


def _leer_oculto(mensaje: str) -> str:
    import getpass
    try:
        return getpass.getpass(mensaje, echo_char="*")      # Python 3.14+: muestra * al pegar
    except TypeError:
        return getpass.getpass(mensaje)


def _exigir_api_key() -> None:
    """La key vive fuera del código: variable de entorno o, si falta, se pide al arrancar."""
    guardada = _limpiar_key(os.environ.get("DATABENTO_API_KEY"))
    if guardada:
        os.environ["DATABENTO_API_KEY"] = guardada
        return
    if not _interactivo():
        sys.exit("Falta la variable de entorno DATABENTO_API_KEY (no pongas la key en el código).")
    for _ in range(3):
        key = _limpiar_key(_leer_oculto("Pega tu API key de Databento y presiona Enter: "))
        if key.startswith("db-"):
            os.environ["DATABENTO_API_KEY"] = key
            print(f"Key recibida: {_mascara(key)}")
            return
        print(f"Eso no parece una API key de Databento (empiezan con 'db-'); llegó {_mascara(key)}.")
    sys.exit("No se recibió una API key válida.")


AYUDA_KEY = (
    "  • Si la regeneraste o la borraste, la anterior ya no sirve. Databento también revoca las keys\n"
    "    que aparecen publicadas (por ejemplo, escritas en código que se comparte).\n"
    "  • Copia la key vigente en el portal de Databento, sección API keys\n"
    "    (guía: https://databento.com/docs/portal/api-keys).\n"
    '  • Guárdala una vez en PowerShell:  setx DATABENTO_API_KEY "db-..."  y cierra y abre VS Code.'
)


def conectar_historico():
    """Cliente histórico con la key verificada antes de cotizar o descargar (list_datasets es gratis)."""
    for _ in range(3):
        venia_de_setx = bool(_limpiar_key(os.environ.get("DATABENTO_API_KEY")))
        _exigir_api_key()
        cliente = db.Historical()
        try:
            cliente.metadata.list_datasets()
            return cliente
        except db.BentoClientError as e:
            if e.http_status not in (401, 403):
                raise
            key = os.environ.pop("DATABENTO_API_KEY", "")
            print(f"❌ Databento rechazó la API key {_mascara(key)} (error {e.http_status}).")
            if venia_de_setx:
                print("   Esa key venía de la variable DATABENTO_API_KEY guardada en tu computadora: actualízala con setx.")
            if not _interactivo():
                break
            print("   Pega la key vigente para intentar de nuevo (Ctrl+C para salir).")
    sys.exit("No se pudo autenticar con Databento.\n" + AYUDA_KEY)


class Tramos:
    """[v3] Varios .dbn.zst (uno por día UTC) leídos como uno solo, con la interfaz que usan los motores: bloques
    de registros (to_ndarray) e iteración registro a registro."""

    def __init__(self, rutas: list[Path]):
        self.rutas = [Path(r) for r in rutas if Path(r).exists()]

    def to_ndarray(self, count: int | None = None):
        for ruta in self.rutas:
            store = db.DBNStore.from_file(ruta)
            try:
                bloques = store.to_ndarray(count=count or 5_000_000)
            except ValueError:                                   # día sin registros (sábado, feriado)
                continue
            for arr in bloques:
                if len(arr):
                    yield arr

    def __iter__(self):
        for ruta in self.rutas:
            yield from db.DBNStore.from_file(ruta)


def _utc(t) -> pd.Timestamp:
    t = pd.Timestamp(t)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def tramos_por_dia(ini: pd.Timestamp, fin: pd.Timestamp) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """[a, b) por día UTC entre ini y fin; el primero y el último pueden quedar a medias."""
    out = []
    d = ini.normalize()
    while d < fin:
        a, b = max(d, ini), min(d + pd.Timedelta(days=1), fin)
        if b > a:
            out.append((a, b))
        d += pd.Timedelta(days=1)
    return out


def _nombre_tramo(a: pd.Timestamp, b: pd.Timestamp) -> str:
    if a == a.normalize() and b == a + pd.Timedelta(days=1):
        return f"{a:%Y-%m-%d}.dbn.zst"                                   # un día completo: se reutiliza siempre
    return f"parcial_{a:%Y%m%dT%H%M%S}_{b:%Y%m%dT%H%M%S}.dbn.zst"


def obtener_datos(cfg: Config, cliente=None, ini: pd.Timestamp | None = None, fin: pd.Timestamp | None = None,
                  decir=print) -> Tramos:
    """[v3] Trades entre ini y fin con caché POR DÍA: cada día UTC completo es un archivo que se reutiliza en
    cualquier corrida; solo se baja lo que falta, con el costo revisado antes (un tope para todo lo que falta)."""
    ini = _utc(ini if ini is not None else pd.Timestamp(cfg.start) - pd.Timedelta(days=cfg.historia_dias))
    fin = _utc(fin if fin is not None else cfg.end)
    carpeta = _ruta(cfg.cache_dir) / _nombre_seguro(cfg.dataset, cfg.symbol, "trades")
    carpeta.mkdir(parents=True, exist_ok=True)
    tramos = tramos_por_dia(ini, fin)
    faltan = [(a, b) for a, b in tramos if not (carpeta / _nombre_tramo(a, b)).exists()]
    if faltan:
        if cliente is None:
            cliente = conectar_historico()
        rango = cliente.metadata.get_dataset_range(dataset=cfg.dataset)
        disponible = _utc(rango.get("end") or rango.get("end_date"))
        if fin > disponible:
            decir(f"⚠️  El histórico llega hasta {disponible:%Y-%m-%d %H:%M} UTC: lo posterior no se baja.")
            tramos = [(a, min(b, disponible)) for a, b in tramos if a < disponible]
            faltan = [(a, b) for a, b in tramos if not (carpeta / _nombre_tramo(a, b)).exists()]
        grupos, actual = [], None                                   # rangos contiguos: una cotización por rango
        for a, b in faltan:
            if actual is not None and actual[1] == a:
                actual = (actual[0], b)
            else:
                if actual is not None:
                    grupos.append(actual)
                actual = (a, b)
        if actual is not None:
            grupos.append(actual)
        base = dict(dataset=cfg.dataset, symbols=cfg.symbol, stype_in=cfg.stype_in, schema="trades")
        costo = sum(float(cliente.metadata.get_cost(**base, start=a.isoformat(), end=b.isoformat())) for a, b in grupos)
        decir(f"💵 Faltan {len(faltan)} día(s) en la caché · costo estimado US$ {costo:,.2f}")
        if costo > cfg.costo_max_usd:
            sys.exit(f"Supera costo_max_usd = {cfg.costo_max_usd}. Súbelo en Config si estás de acuerdo.")
        for a, b in faltan:
            ruta = carpeta / _nombre_tramo(a, b)
            temporal = ruta.with_name(ruta.name + ".parcial")
            temporal.unlink(missing_ok=True)
            decir(f"📡 {a:%Y-%m-%d %H:%M} → {b:%Y-%m-%d %H:%M} UTC …")
            cliente.timeseries.get_range(**base, start=a.isoformat(), end=b.isoformat(), path=temporal)
            gc.collect()                                # suelta el archivo (Windows no renombra abiertos)
            temporal.replace(ruta)
    en_uso = {_nombre_tramo(a, b) for a, b in tramos}
    for vieja in carpeta.glob("parcial_*.dbn.zst"):                  # los tramos a medias de otras corridas
        if vieja.name not in en_uso:
            vieja.unlink(missing_ok=True)
    return Tramos([carpeta / _nombre_tramo(a, b) for a, b in tramos])


def guardar_resultados(df: pd.DataFrame, alertas: pd.DataFrame, evaluacion: dict, cfg: Config, sufijo: str) -> None:
    carpeta = _ruta(cfg.salida_dir)
    carpeta.mkdir(parents=True, exist_ok=True)
    salida = df.copy()
    salida.insert(2, "t_fin_cdmx", salida["t_fin"].dt.tz_convert(TZ_LOCAL))
    salida.to_csv(carpeta / f"buckets_{sufijo}.csv")
    al = alertas.copy()
    al.insert(1, "t_fin_cdmx", al["t_fin"].dt.tz_convert(TZ_LOCAL))
    al.to_csv(carpeta / f"alertas_{sufijo}.csv")
    for clave in ("ic", "eventos", "direccion"):                     # [v3] la evaluación también
        t = evaluacion.get(clave)
        if isinstance(t, pd.DataFrame) and len(t):
            t.to_csv(carpeta / f"evaluacion_{clave}_{sufijo}.csv", index=False)
    print(f"💾 Buckets, alertas y evaluación guardados en {carpeta}")


def ultimo_halt_cme(t: pd.Timestamp) -> pd.Timestamp:
    """Inicio del último halt diario de CME (16:00 hora de Chicago, lunes a viernes) <= t, en UTC."""
    local = t.tz_convert(TZ_CME).tz_localize(None)
    cand = local.normalize() + pd.Timedelta(hours=16)
    if cand > local:
        cand -= pd.Timedelta(days=1)
    while cand.weekday() >= 5:
        cand -= pd.Timedelta(days=1)
    return cand.tz_localize(TZ_CME).tz_convert("UTC")


class Deduplicador:
    """[v3] (El de Order Flow / Iceberg.) Tras una reconexión se vuelve a pedir replay desde un poco antes del
    último mensaje procesado. Llegan en el mismo orden: basta con ts_recv y cuántos mensajes ya se procesaron con
    ese ts_recv."""

    def __init__(self):
        self.ts = -1
        self.n = 0
        self._resync = False
        self._vistos = 0

    def nuevo_stream(self) -> None:
        self._resync = self.ts >= 0
        self._vistos = 0

    def aceptar(self, ts_recv: int) -> bool:
        if self._resync:
            if ts_recv < self.ts:
                return False
            if ts_recv == self.ts:
                self._vistos += 1
                if self._vistos <= self.n:
                    return False
                self.n += 1
                return True
            self._resync = False
        if ts_recv > self.ts:
            self.ts, self.n = ts_recv, 1
        elif ts_recv == self.ts:
            self.n += 1
        return True


ERRORES_FATALES = {ErrorCode.AUTH_FAILED, ErrorCode.API_KEY_DEACTIVATED, ErrorCode.INVALID_SUBSCRIPTION,
                   ErrorCode.SYMBOL_RESOLUTION_FAILED}


def _piso_de_start(texto: str) -> int | None:
    """El gateway de Live rechaza un replay anterior a su ventana ("Must be 2026-09-26T07:15:00Z or later"): se lee
    el piso del propio error."""
    m = re.search(r"Must be (\S+?) or later", texto)
    if not m:
        return None
    try:
        return int(_utc(m.group(1)).value)
    except Exception:
        return None


def bucle_live(motor: MotorVPIN, cfg: Config, corte_ns: int, fabrica=None, detener: threading.Event | None = None,
               espera_base: float = 1.0, reloj=time.time_ns, decir=print) -> dict:
    """[v3] trades en vivo con replay desde lo último procesado. La v2 usaba reconnect_policy="reconnect", que se
    vuelve a suscribir con start=None: todo lo que pasaba durante el corte se perdía sin aviso. Aquí cada
    reconexión pide replay desde un poco antes del último trade, el Deduplicador descarta lo repetido, la espera
    crece si falla y, si el replay pedido es más viejo de lo que el gateway permite, se usa su piso."""
    fabrica = fabrica or (lambda: db.Live(heartbeat_interval_s=cfg.heartbeat_s, slow_reader_behavior="warn"))
    detener = detener or threading.Event()
    dedup = Deduplicador()
    est = {"reconexiones": 0, "duplicados": 0, "trades": 0}
    intentos, piso = 0, 0
    while not detener.is_set():
        minimo = reloj() - int(cfg.replay_max_h * 3600 * NS)
        deseado = dedup.ts - 5 * NS if dedup.ts >= 0 else corte_ns
        inicio = max(deseado, minimo, piso)
        if inicio > deseado and minutos_mercado(deseado, inicio)[0] > 0:        # [v3] solo si hubo mercado
            decir(f"⚠️  Live solo repite ~{cfg.replay_max_h:g} h: faltan los trades entre "
                  f"{pd.Timestamp(deseado, tz='UTC'):%d-%m %H:%M} y {pd.Timestamp(inicio, tz='UTC'):%d-%m %H:%M} UTC.")
        motivo, recibio, fatal, inmediato = "Databento cerró la conexión", False, None, False
        cliente = None
        try:
            cliente = fabrica()
            cliente.subscribe(dataset=cfg.dataset, schema="trades", symbols=cfg.symbol, stype_in=cfg.stype_in,
                              start=pd.Timestamp(inicio, tz="UTC"))
            dedup.nuevo_stream()
            for rec in cliente:
                if isinstance(rec, db.TradeMsg):
                    recibio = True
                    if rec.ts_event < corte_ns:                  # lo anterior al corte vino del histórico
                        continue
                    if dedup.aceptar(int(rec.ts_recv)):
                        est["trades"] += 1
                        motor.procesar(rec)
                    else:
                        est["duplicados"] += 1
                elif isinstance(rec, db.SystemMsg):
                    if rec.is_heartbeat():
                        continue
                    if rec.code == SystemCode.SLOW_READER_WARNING:
                        decir(f"⚠️  Databento: {rec.msg} (el script va atrasado)")
                    else:
                        decir(f"ℹ️  {rec.msg}")
                elif isinstance(rec, db.ErrorMsg):
                    decir(f"⚠️  Databento: {rec.err}")
                    if rec.code in ERRORES_FATALES:
                        fatal = rec.err
                        break
                    if rec.code == ErrorCode.SKIPPED_RECORDS_AFTER_SLOW_READING or "skipped" in str(rec.err).lower():
                        motivo = "Databento saltó mensajes; reconecto para rellenar el hueco con replay"
                        break
                if detener.is_set():
                    break
        except KeyboardInterrupt:
            raise
        except db.BentoError as e:
            p = _piso_de_start(str(e))
            if p is not None and p > piso:
                piso, inmediato = p, True
                motivo = f"el replay de Live empieza en {pd.Timestamp(p, tz='UTC'):%d-%m %H:%M} UTC"
            else:
                motivo = f"{type(e).__name__}: {e}"
        except ValueError as e:
            fatal = str(e)
        except Exception as e:
            motivo = f"{type(e).__name__}: {e}"
        finally:
            if cliente is not None:
                try:
                    cliente.terminate()
                except Exception:
                    pass
        if fatal:
            decir(f"❌ Databento rechazó la conexión: {fatal}\n" + AYUDA_KEY)
            return est
        if detener.is_set():
            break
        if inmediato:
            decir(f"ℹ️  Reconexión: {motivo}.")
            continue
        intentos = 1 if recibio else intentos + 1
        est["reconexiones"] += 1
        espera = espera_base * min(30, 2 ** (intentos - 1))
        decir(f"⚠️  Conexión perdida ({motivo}). Reintento en {espera:.0f} s con replay desde el último trade…")
        detener.wait(espera)
    return est


def correr_live(cfg: Config, cliente_hist=None, fabrica=None, ahora: pd.Timestamp | None = None,
                detener: threading.Event | None = None, espera_base: float = 1.0, reloj=time.time_ns,
                decir=print) -> tuple[MotorVPIN, dict]:
    """Calienta con las sesiones recientes del histórico (hasta el último halt diario) y sigue con Live.
    Los parámetros opcionales existen para probarlo sin conexión (--autoprueba)."""
    cliente_hist = cliente_hist or conectar_historico()     # también deja lista la key para Live
    ahora = ahora if ahora is not None else pd.Timestamp.now(tz="UTC")
    corte = ultimo_halt_cme(ahora)
    rango = cliente_hist.metadata.get_dataset_range(dataset=cfg.dataset)
    disponible = _utc(rango.get("end") or rango.get("end_date"))
    if corte > disponible:
        corte = ultimo_halt_cme(disponible)
    ini = (corte - pd.Timedelta(days=cfg.dias_historial_live)).normalize()      # [v3] días completos: se reutilizan
    store = obtener_datos(cfg, cliente_hist, ini, corte, decir=decir)
    V = int(cfg.volumen_bucket) if cfg.volumen_bucket else calibrar(store, cfg, corte, imprimir=False)[0]   # [v3]
    decir(f"🔧 Bucket = {V:,} contratos (mediana de las últimas sesiones completas / {cfg.buckets_por_dia}). "
          "Calentando con el histórico…")
    estado = EstadoVPIN(V, cfg)
    det = _nuevo_detector(cfg)
    calentando = {"si": True}

    def al_cerrar_bucket(fila: dict) -> None:
        u = estado.agregar(fila)
        alerta = det.actualizar(int(fila["t_fin"]), u["vpin_pct"])
        if calentando["si"]:
            return
        hora = u["t_fin"].tz_convert(TZ_LOCAL)
        decir(f"[LIVE] {hora:%d-%m %H:%M}  bucket {fila['k']}  VPIN={u['vpin']:.3f}  "
              f"percentil={u['vpin_pct']:.2f}  desbalance={u['desbalance']:+.3f}  precio={u['precio']:,.2f}")
        if alerta:
            lado = "compras" if u["desbalance"] >= 0 else "ventas"
            decir(f"⚠️  [LIVE] {hora:%d-%m %H:%M} ALERTA DE TOXICIDAD  percentil={u['vpin_pct']:.2f}  domina {lado}")

    motor = MotorVPIN(V, al_cerrar_bucket=al_cerrar_bucket)
    for rec in store:
        if isinstance(rec, db.TradeMsg):
            motor.procesar(rec)
    calentando["si"] = False
    decir(f"✅ Calentamiento listo ({motor._k:,} buckets). Conectando a Live desde {corte:%d-%m %H:%M} UTC…")
    est = {}
    try:
        est = bucle_live(motor, cfg, corte.value, fabrica=fabrica, detener=detener, espera_base=espera_base,
                         reloj=reloj, decir=decir)
    except KeyboardInterrupt:
        decir("\nCerrando…")
    return motor, est


# =============================================================================
# 9. ANÁLISIS COMPLETO
# =============================================================================
def analizar(store, cfg: Config, t_eval: pd.Timestamp | None, motor: str = "vectorizado", imprimir: bool = True) -> dict:
    t0 = time.perf_counter()
    V, t_senales, vol_ses = calibrar(store, cfg, t_eval, imprimir)
    buckets, sin_lado = procesar_buckets(store, V, cfg, motor)
    if len(buckets) <= cfg.n_buckets:
        raise ValueError("Muy pocos buckets para calcular el VPIN. Usa un rango más largo o un V menor.")
    minutos = barras_minuto(store, cfg)
    total = int(vol_ses.sum())
    df = calcular_vpin(buckets, V, cfg)
    alertas = detectar_alertas(df, cfg, t_senales)
    if imprimir:
        print(f"✅ {len(buckets):,} buckets en {time.perf_counter() - t0:.1f} s [motor {motor}]  ·  "
              f"volumen sin lado agresor: {sin_lado:,} ({sin_lado / max(total, 1):.2%})")
        imprimir_alertas(alertas)
    resultado = evaluar(df, alertas, minutos, cfg, t_senales, imprimir)
    return {"buckets": df, "alertas": alertas, "minutos": minutos, "V": V, "t_senales": t_senales,
            "evaluacion": resultado}


# =============================================================================
# 10. MERCADO SIMULADO (autoprueba y --simular)
# =============================================================================
DT_TRADES = np.dtype([("ts_recv", "<u8"), ("ts_event", "<u8"), ("action", "S1"), ("side", "S1"), ("size", "<u4"),
                      ("price", "<i8"), ("instrument_id", "<u4")])


def mercado_simulado(semilla: int, sesiones: int = 40, inicio: str = "2026-03-02", informado: bool = False,
                     intensidad: float = 4.0) -> np.ndarray:
    """Trades de un futuro tipo ES con lo que el VPIN NO debería confundir con información: actividad en U durante
    el día (pico al abrir el contado), volatilidad que sigue a la actividad, días más o menos agitados y operaciones
    más grandes en el horario regular que de noche.
      informado=False → el lado agresor es una moneda al aire: el flujo no anticipa nada.
      informado=True  → ~1 episodio por sesión: 90 min de flujo de un solo lado (80/20) y después 2 h con la
                        volatilidad ×2.5: aquí el VPIN SÍ anticipa volatilidad."""
    rng = np.random.default_rng(semilla)
    dias = pd.bdate_range(inicio, periods=sesiones)
    minutos = []
    for d in dias:
        ini = (d - pd.Timedelta(days=1)).normalize() + pd.Timedelta(hours=17)
        minutos.append(pd.date_range(ini, periods=23 * 60, freq="1min").tz_localize(TZ_CME).tz_convert("UTC")
                       .as_unit("ns").asi8)
    t = np.concatenate(minutos)
    loc = pd.DatetimeIndex(t, tz="UTC").tz_convert(TZ_CME)
    h = loc.hour.to_numpy() + loc.minute.to_numpy() / 60
    rth = (h >= 8.5) & (h < 15.25)
    act = np.where(rth, 1.0, 0.18) * (1 + 2.5 * np.exp(-((h - 8.5) / 0.35) ** 2) + 1.2 * np.exp(-((h - 15.0) / 0.3) ** 2))
    x = np.zeros(sesiones)                                   # días más o menos agitados: AR(1) en log
    for s in range(1, sesiones):
        x[s] = 0.8 * x[s - 1] + rng.normal(0, 0.2)
    dia = np.repeat(np.exp(x), 23 * 60)
    lam = intensidad * act * dia * np.exp(rng.normal(0, 0.3, t.size))
    sig_extra = np.ones(t.size)
    p_compra = np.full(t.size, 0.5)
    if informado:
        for s in range(sesiones):
            if rng.random() < 0.85:
                a = s * 23 * 60 + int(rng.integers(60, 23 * 60 - 240))
                p_compra[a:a + 90] = 0.8 if rng.random() < 0.5 else 0.2
                lam[a:a + 90] *= 1.3
                sig_extra[a + 90:a + 210] = 2.5
                lam[a + 90:a + 210] *= 1.5
    n = rng.poisson(lam)
    sig = 0.00018 * np.sqrt(lam / intensidad) * sig_extra
    lp = np.log(6500) + np.cumsum(sig * rng.standard_normal(t.size))
    N = int(n.sum())
    idx = np.repeat(np.arange(t.size), n)
    ts = t[idx] + rng.integers(0, NS_MIN, N)
    orden = np.argsort(ts, kind="stable")
    ts, idx = ts[orden], idx[orden]
    a = np.zeros(N, DT_TRADES)
    a["ts_event"] = ts
    a["ts_recv"] = ts + 20_000
    a["action"] = b"T"
    a["side"] = np.where(rng.random(N) < p_compra[idx], b"B", b"A")
    a["size"] = rng.geometric(1.0 / np.where(rth, 5.0, 2.0)[idx])
    a["price"] = np.round(np.exp(lp[idx]) / 0.25) * 0.25 * PRICE_SCALE
    a["instrument_id"] = 5
    return a


def _trade_msg(r):
    import databento_dbn as dbn
    return db.TradeMsg(publisher_id=1, instrument_id=int(r["instrument_id"]), ts_event=int(r["ts_event"]),
                       price=int(r["price"]), size=int(r["size"]), action=dbn.Action.TRADE,
                       side=dbn.Side.BID if r["side"] == b"B" else dbn.Side.ASK if r["side"] == b"A" else dbn.Side.NONE,
                       depth=0, ts_recv=int(r["ts_recv"]), sequence=0)


class StoreMemoria:
    """Un arreglo de trades con la interfaz de DBNStore que usan los motores."""

    def __init__(self, arr: np.ndarray):
        self.arr = arr

    def to_ndarray(self, count: int | None = None):
        paso = count or max(len(self.arr), 1)
        for i in range(0, len(self.arr), paso):
            yield self.arr[i:i + paso]

    def __iter__(self):
        for r in self.arr:
            yield _trade_msg(r)


def _una_simulacion(semilla: int, informado: bool, cfg: Config, sesiones: int = 40, historia: int = 20) -> dict:
    arr = mercado_simulado(semilla, sesiones=sesiones, informado=informado)
    dias = pd.bdate_range("2026-03-02", periods=sesiones)
    t_eval = fin_sesion_cme(dias[historia - 1])
    r = analizar(StoreMemoria(arr), replace(cfg, symbol="ES.v.0"), t_eval, imprimir=False)
    return r["evaluacion"]


def simular(n: int, cfg: Config = CFG, imprimir: bool = True, sesiones_eval: int = 20,
            mercados: tuple = ("sin información", "con información")) -> dict:
    """[v3] La calibración del punto 2: n mercados SIN información y n CON información, 20 sesiones de historia y
    `sesiones_eval` de evaluación cada uno. Sin información, una prueba bien calibrada rechaza ~5 % de las veces."""
    filas = []
    for tipo in mercados:
        for s in range(n):
            ev = _una_simulacion(1000 + s, tipo == "con información", cfg, sesiones=20 + sesiones_eval)
            for r in ev["ic"].itertuples():
                filas.append({"mercado": tipo, "sim": s, "h": r.h_min, "t_v2": r.t_v2, "t_v2_parcial": r.t_v2_parcial,
                              "IC_parcial": r.IC_parcial, "p_parcial": r.p_parcial,
                              "veredicto": r.h_min in ev["significativos"]})
            if imprimir:
                print(f"   {tipo} · corrida {s + 1}/{n}", end="\r", flush=True)
    F = pd.DataFrame(filas)
    tabla = F.groupby(["mercado", "h"]).agg(
        v2_t_crudo=("t_v2", lambda x: np.mean(np.abs(x) > 1.96)),
        v2_t_parcial=("t_v2_parcial", lambda x: np.mean(np.abs(x) > 1.96)),
        v3_p_parcial=("p_parcial", lambda x: np.mean(x < 0.05)),
        v3_IC_parcial_medio=("IC_parcial", "mean"))
    veredicto = F.groupby(["mercado", "sim"])["veredicto"].any().groupby(level=0).mean()
    if imprimir:
        print(" " * 60)
        print(f"Fracción de corridas que declaran 'significativo' ({n} por mercado, {sesiones_eval} sesiones de "
              f"evaluación; α = 5 %):")
        print(tabla.to_string(float_format=lambda x: f"{x:.3f}"))
        print("\nVeredicto de la v3 (algún horizonte, Bonferroni): "
              + " · ".join(f"{k}: {v:.0%}" for k, v in veredicto.items()))
    return {"tabla": tabla, "veredicto": veredicto, "filas": F}


# =============================================================================
# 11. AUTOPRUEBA
# =============================================================================
def autoprueba() -> int:
    import tempfile
    from types import SimpleNamespace
    fallas: list[str] = []
    T0 = time.perf_counter()

    def revisar(nombre: str, ok: bool, detalle: str = "") -> None:
        print(f"  {'OK   ' if ok else 'FALLA'}  {nombre}{('  ' + detalle) if detalle else ''}", flush=True)
        if not ok:
            fallas.append(nombre)

    print("1) Los dos motores de la v2 siguen dando lo mismo (bloques cortados, tiempos fuera de orden, trades que "
          "llenan varios buckets, lado N)", flush=True)
    rng = np.random.default_rng(1)
    difieren = 0
    for rep in range(12):
        n = int(rng.integers(2_000, 20_000))
        a = np.zeros(n, DT_TRADES)
        a["ts_event"] = np.cumsum(rng.integers(0, 3 * NS, n)) + 1_780_000_000 * NS
        a["ts_event"][rng.random(n) < 0.02] -= 5 * NS
        a["action"] = np.where(rng.random(n) < 0.9, b"T", b"A")
        a["side"] = rng.choice([b"B", b"A", b"N"], n, p=[0.48, 0.48, 0.04])
        a["size"] = np.where(rng.random(n) < 0.05, rng.integers(200, 900, n), rng.geometric(0.3, n))
        a["price"] = (6500 + np.cumsum(rng.normal(0, 0.25, n))) * PRICE_SCALE
        a["instrument_id"] = 5
        V = int(rng.integers(50, 700))
        m = MotorVPIN(V)
        for r in a:
            m.procesar(SimpleNamespace(ts_event=int(r["ts_event"]), action=r["action"].decode(), side=r["side"].decode(),
                                       size=int(r["size"]), price=int(r["price"]), instrument_id=5))
        c = _Arrastre()
        partes = [f for b in np.split(a, np.sort(rng.choice(np.arange(1, n), 6, replace=False)))
                  if len(b) and (f := _bloque_buckets(b, c, V)) is not None]
        difieren += not (m.buckets().equals(_tabla_buckets(pd.concat(partes, ignore_index=True))) and m.sin_lado == c.sin_lado)
    revisar(f"12 escenarios aleatorios: {difieren} con diferencias", difieren == 0)

    print("2) El percentil: referencia rezagada sin buckets compartidos, igual a la fuerza bruta; y el de Live igual", flush=True)
    x = pd.Series(np.r_[np.full(49, np.nan), rng.random(3000)])
    W, rez, mo = 300, 50, 120
    pct = percentil_movil(x, W, mo, rez).to_numpy()
    v = x.to_numpy()
    bruta = np.full(len(v), np.nan)
    for t_ in range(len(v)):
        ref = v[max(0, t_ - rez - W + 1): max(0, t_ - rez + 1)]
        ref = ref[~np.isnan(ref)]
        if len(ref) >= mo and np.isfinite(v[t_]):
            bruta[t_] = (np.sum(ref < v[t_]) + 0.5 * np.sum(ref == v[t_])) / len(ref)
    v2 = percentil_movil(x, 250, 100, 1).to_numpy()
    ref2 = sliding_window_view(np.concatenate((np.full(250, np.nan), v)), 250)[:len(v)]
    with np.errstate(invalid="ignore", divide="ignore"):
        v2b = (np.sum(ref2 < v[:, None], 1) + 0.5 * np.sum(ref2 == v[:, None], 1)) / np.sum(~np.isnan(ref2), 1)
    v2b[(np.sum(~np.isnan(ref2), 1) < 100) | np.isnan(v)] = np.nan
    revisar("percentil con rezago = fuerza bruta; con rezago 1 = la fórmula de la v2",
            np.allclose(pct, bruta, equal_nan=True) and np.allclose(v2, v2b, equal_nan=True))
    arr = mercado_simulado(3, sesiones=30)
    cfg_p = replace(CFG, ventana_pct=600, min_obs_pct=300)
    bk, _ = procesar_buckets_vectorizado(StoreMemoria(arr), 400, cfg_p)
    df = calcular_vpin(bk, 400, cfg_p)
    est = EstadoVPIN(400, cfg_p)
    filas = [est.agregar({"k": k, "t_fin": int(r.t_fin.value), "oi": int(r.oi), "precio": r.precio * PRICE_SCALE})
             for k, r in zip(bk.index, bk.itertuples())]
    L = pd.DataFrame(filas).set_index("k")
    revisar(f"EstadoVPIN (Live) = calcular_vpin en los {len(df):,} buckets (VPIN, desbalance y percentil)",
            np.allclose(L["vpin"], df["vpin"], equal_nan=True, rtol=0, atol=1e-15)
            and np.allclose(L["desbalance"], df["desbalance"], equal_nan=True, rtol=0, atol=1e-15)
            and np.allclose(L["vpin_pct"], df["vpin_pct"], equal_nan=True, rtol=0, atol=1e-15))

    print("3) Minutos de mercado y calibración de V", flush=True)
    ct = lambda s: pd.Timestamp(s).tz_localize(TZ_CME).tz_convert("UTC").value   # noqa: E731
    casos = [("2026-06-09 15:50", "2026-06-09 17:10", 20), ("2026-06-12 15:30", "2026-06-14 17:30", 60),
             ("2026-06-10 10:00", "2026-06-10 11:00", 60), ("2026-10-30 12:00", "2026-11-02 12:00", 23 * 60)]
    obt = minutos_mercado([ct(a) for a, _, _ in casos], [ct(b) for _, b, _ in casos])
    revisar(f"pausa diaria, fin de semana y cambio de horario: {obt.tolist()} minutos",
            np.allclose(obt, [c[2] for c in casos]))
    arr40 = mercado_simulado(5, sesiones=40)
    corte_hist = fin_sesion_cme(pd.bdate_range("2026-03-02", periods=40)[29])
    medio = arr40[arr40["ts_event"] >= arr40["ts_event"][0] + 20 * 3600 * NS]      # la primera sesión, a medias
    V, t_s, vol = calibrar(StoreMemoria(medio), CFG, corte_hist, imprimir=False)
    fines = pd.DatetimeIndex([fin_sesion_cme(d) for d in vol.index])
    previas = vol[np.asarray(fines <= corte_hist)]
    esperado = int(round(previas[previas >= 0.5 * previas.median()].iloc[-20:].median() / 50))
    revisar(f"V = mediana de las últimas 20 sesiones completas antes de la evaluación ({V:,}); la primera, a medias "
            f"({previas.iloc[0]:,} contra {int(previas.median()):,}), no cuenta", V == esperado and t_s == corte_hist
            and previas.iloc[0] < 0.5 * previas.median())

    print("4) La evaluación en mercados simulados (20 sesiones de historia; la calibración completa: --simular 40)", flush=True)
    s_sin = simular(12, imprimir=False, sesiones_eval=20, mercados=("sin información",))
    s_con = simular(8, imprimir=False, sesiones_eval=40, mercados=("con información",))
    sin, con = s_sin["tabla"].loc["sin información"], s_con["tabla"].loc["con información"]
    revisar(f"SIN información (12 mercados, 20 sesiones): la v2 declaraba significativo en {sin['v2_t_parcial'].mean():.0%} de "
            f"los horizontes; la v3 en {sin['v3_p_parcial'].mean():.0%}, veredicto en {s_sin['veredicto'].iloc[0]:.0%} "
            f"(IC parcial medio {sin['v3_IC_parcial_medio'].mean():+.3f})",
            sin["v3_p_parcial"].mean() <= 0.15 and abs(sin["v3_IC_parcial_medio"].mean()) < 0.1
            and s_sin["veredicto"].iloc[0] <= 0.17 and sin["v2_t_parcial"].mean() >= 0.3)
    revisar(f"CON información (8 mercados, 40 sesiones): la v3 lo detecta en {con['v3_p_parcial'].mean():.0%} de los horizontes "
            f"(IC parcial medio {con['v3_IC_parcial_medio'].mean():+.3f}); veredicto en {s_con['veredicto'].iloc[0]:.0%}",
            con["v3_p_parcial"].mean() >= 0.25 and con["v3_IC_parcial_medio"].mean() > 0.1 and s_con["veredicto"].iloc[0] >= 0.375)

    print("5) Live: replay, un corte a la mitad, el piso del gateway y el replay que se solapa (TradeMsg reales)", flush=True)
    arrL = mercado_simulado(9, sesiones=30)
    corte_L = fin_sesion_cme(pd.bdate_range("2026-03-02", periods=30)[27])
    fin_L = fin_sesion_cme(pd.bdate_range("2026-03-02", periods=30)[29])
    vivos = arrL[(arrL["ts_event"] >= corte_L.value) & (arrL["ts_event"] < fin_L.value)]
    vivos = np.concatenate([vivos[:5000], vivos[4999:5000], vivos[5000:]])          # un ts_recv repetido
    msgs = [_trade_msg(r) for r in vivos]
    piso = int(vivos["ts_event"][300])
    cfgL = replace(CFG, replay_max_h=1e7, cache_dir="")

    class HistoricoFalso:
        class metadata:
            @staticmethod
            def get_dataset_range(dataset):
                return {"end": corte_L.isoformat()}

            @staticmethod
            def get_cost(**kw):
                return 0.0

        class timeseries:
            llamadas = 0

            @staticmethod
            def get_range(dataset, symbols, stype_in, schema, start, end, path):
                import databento_dbn as dbn
                HistoricoFalso.timeseries.llamadas += 1
                a0, b0 = _utc(start).value, _utc(end).value
                sel = arrL[(arrL["ts_event"] >= a0) & (arrL["ts_event"] < b0)]
                meta = dbn.Metadata(dataset=dataset, schema=dbn.Schema.TRADES, start=a0, end=b0,
                                    stype_in=dbn.SType.CONTINUOUS, stype_out=dbn.SType.INSTRUMENT_ID, symbols=[symbols])
                Path(path).write_bytes(meta.encode() + b"".join(bytes(_trade_msg(r)) for r in sel))

    class ClienteFalso:
        def __init__(self, corte_en=None, piso_err=False):
            self.corte_en, self.piso_err, self.start = corte_en, piso_err, 0

        def subscribe(self, **kw):
            self.start = int(pd.Timestamp(kw["start"]).value)
            if self.piso_err and self.start < piso:
                raise db.BentoError(f"Invalid start time. Must be {pd.Timestamp(piso, tz='UTC').isoformat()} or later, or 0")

        def __iter__(self):
            j = 0
            for r in msgs:
                if r.ts_event < self.start:
                    continue
                j += 1
                if self.corte_en is not None and j >= self.corte_en:
                    raise db.BentoError("conexión perdida (prueba)")
                yield r

        def terminate(self):
            pass
    with tempfile.TemporaryDirectory() as tmp:
        cfgL = replace(cfgL, cache_dir=tmp)
        clientes = iter([ClienteFalso(piso_err=True), ClienteFalso(corte_en=len(msgs) // 2), ClienteFalso()])
        detener = threading.Event()

        def fabrica():
            try:
                return next(clientes)
            except StopIteration:
                detener.set()
                raise db.BentoError("fin de la prueba")
        mudo = lambda *a, **k: None   # noqa: E731
        motor, est = correr_live(cfgL, HistoricoFalso(), fabrica, ahora=corte_L + pd.Timedelta(hours=2), detener=detener,
                                 espera_base=0.0, reloj=lambda: int(fin_L.value), decir=mudo)
        llamadas_1 = HistoricoFalso.timeseries.llamadas
        directo, _ = correr_live(cfgL, HistoricoFalso(), lambda: (_ for _ in ()).throw(KeyboardInterrupt()),
                                 ahora=corte_L + pd.Timedelta(hours=2), decir=mudo)
        llamadas_2 = HistoricoFalso.timeseries.llamadas - llamadas_1
        for r in msgs:
            if r.ts_event >= piso:
                directo.procesar(r)
        ini_L = (corte_L - pd.Timedelta(days=cfgL.dias_historial_live)).normalize()
        store_dias = obtener_datos(cfgL, HistoricoFalso(), ini_L, corte_L, decir=mudo)
        hist = arrL[(arrL["ts_event"] >= ini_L.value) & (arrL["ts_event"] < corte_L.value)]
        igual_cache = procesar_buckets_vectorizado(store_dias, 350, CFG)[0].equals(
            procesar_buckets_vectorizado(StoreMemoria(hist), 350, CFG)[0])
    revisar(f"tras el piso del gateway y un corte: los mismos {len(motor._filas):,} buckets que sin cortes "
            f"({est.get('duplicados', 0):,} trades repetidos descartados, {est.get('reconexiones', 0)} reconexiones)",
            motor._filas == directo._filas and est.get("duplicados", 0) > 0 and est.get("reconexiones", 0) == 2)
    revisar(f"caché por día: {llamadas_1} descargas la primera vez, {llamadas_2} la segunda; leer los días = leer todo junto",
            llamadas_1 > 0 and llamadas_2 == 0 and igual_cache)

    print(f"\n{time.perf_counter() - T0:.0f} s")
    if fallas:
        print(f"{len(fallas)} pruebas fallaron: {', '.join(fallas)}")
        return 1
    print("Todas las pruebas pasaron.")
    return 0


# =============================================================================
# 12. MAIN
# =============================================================================
def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description="VPIN AC v3 con reloj de volumen (Databento trades)")
    ap.add_argument("--motor", choices=("vectorizado", "incremental"), default="vectorizado")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--archivo", help="usar un .dbn / .dbn.zst existente en vez de descargar")
    ap.add_argument("--simbolo")
    ap.add_argument("--inicio", help="UTC, inicio de la evaluación, p. ej. 2026-08-03T00:00:00")
    ap.add_argument("--fin", help="UTC, p. ej. 2026-08-21T23:59:00")
    ap.add_argument("--historia-dias", type=int, help="días antes de --inicio para V, percentil y estacionalidad (35)")
    ap.add_argument("--volumen-bucket", type=int, help="fija V en contratos (omite la calibración)")
    ap.add_argument("--salida", help="carpeta para CSV y PNG (por defecto: salidas_vpin/)")
    ap.add_argument("--sin-grafica", action="store_true")
    ap.add_argument("--autoprueba", action="store_true", help="pruebas sin API (~2 min)")
    ap.add_argument("--simular", type=int, metavar="N", help="calibración: N mercados sin y N con información")
    ap.add_argument("--sesiones-eval", type=int, default=20, help="--simular: sesiones de evaluación (20)")
    args = ap.parse_args(argv)
    if args.autoprueba:
        sys.exit(autoprueba())

    cambios = {k: v for k, v in (("symbol", args.simbolo), ("start", args.inicio), ("end", args.fin),
                                 ("salida_dir", args.salida), ("volumen_bucket", args.volumen_bucket),
                                 ("historia_dias", args.historia_dias)) if v}
    cfg = replace(CFG, **cambios)
    if args.simular:
        simular(args.simular, cfg, sesiones_eval=args.sesiones_eval)
        return {}
    if args.live:
        correr_live(cfg)
        return {}

    if args.archivo:
        store = db.DBNStore.from_file(args.archivo)
        t_eval = _utc(cfg.start) if args.inicio else None
    else:
        store = obtener_datos(cfg)
        t_eval = _utc(cfg.start)
        print(f"🕐 Evaluación {cfg.start} … {cfg.end} UTC, con {cfg.historia_dias} días de historia antes")
    try:
        res = analizar(store, cfg, t_eval, args.motor)
    except ValueError as e:
        sys.exit(str(e))
    df, alertas = res["buckets"], res["alertas"]
    sufijo = _nombre_seguro(cfg.symbol, f"{df['t_fin'].iloc[0]:%Y%m%d}", f"{df['t_fin'].iloc[-1]:%Y%m%d}")
    guardar_resultados(df, alertas, res["evaluacion"], cfg, sufijo)
    if not args.sin_grafica:
        graficar_dashboard(df, alertas, res["minutos"], cfg, res["V"], res["t_senales"],
                           _ruta(cfg.salida_dir) / f"dashboard_vpin_{sufijo}.png")
    return res


if __name__ == "__main__":
    main()
