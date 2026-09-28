# -*- coding: utf-8 -*-
"""
COINTEGRACIÓN LIVE AC — pares de futuros (ES / NQ) en tiempo real: prueba estricta, hedge ratio de Kalman, z del
spread Ornstein-Uhlenbeck, órdenes con costos (de PAPEL), tablero y alertas por Telegram
Databento GLBX.MDP3 · ohlcv-1h (calentamiento) · ohlcv-1m en vivo de los continuos .n.0 y .n.1 → barras de 1 h

Tu v3 (co_integracion_cloud.py) prueba la cointegración con la ventana de 690 barras SIN mirar el futuro, filtra el
hedge ratio y el spread con un solo Kalman, mide la vida media con corrección de sesgo, elige el umbral óptimo con
costos (Bertram) y decide al cierre de la hora para ejecutar a la apertura siguiente. Esa matemática está aquí
copiada TAL CUAL (§2–§12): calendario de CME, ajuste de rolls hacia adelante con la .n.1, el filtro en sus dos formas,
la máxima verosimilitud concentrada, el bootstrap de la vida media, los tiempos de primer paso, la prueba estricta con
histéresis, las reglas de operación, el motor barra a barra (MotorPar), la auditoría, el Agregador de 1 min y
UnirVivo. Las pruebas exigen que el camino en vivo dé las MISMAS filas, el mismo z, las mismas operaciones y el
mismo P&L que el motor histórico de la v3.

    LARGO spread  ·  comprar Y (ES) y vender X (NQ): el spread está por DEBAJO de su media (z ≤ −umbral)
    CORTO spread  ·  vender Y y comprar X: el spread está por ENCIMA (z ≥ +umbral)
    la puerta     ·  la prueba estricta: sin evidencia de cointegración no se abre nada

En vivo [live]:
  1. El --live de la v3 imprimía en la consola; aquí corre como los otros indicadores: tablero web, Telegram,
     reconexión sin huecos (replay intradía + descarte de duplicados por serie) y registro en CSV.
  2. Calentamiento: ohlcv-1h de los últimos 60 días de las cuatro series. El motor recorre esa historia, calibra en
     las mismas barras que el histórico y queda con su filtro, su calendario y su posición de papel.
  3. Live: ohlcv-1m de ES.n.0, NQ.n.0, ES.n.1 y NQ.n.1, con replay desde donde terminó la historia; barras de 1 h con
     el Agregador de la v3; re-estimación una vez por sesión, como en la v3.
  4. EL Z EN CURSO: la v3 decide al cierre de la hora, y así sigue (las órdenes no cambian). Minuto a minuto se
     calcula el z que daría el filtro si la hora cerrara AHORA, sobre una COPIA del filtro (el estado no se toca).
     Si la hora va camino de cerrar con señal, llega un aviso "en curso".
  5. PRECIOS DE DISPARO: la corrección del Kalman es lineal en y, así que se despeja el precio EXACTO de ES que,
     con NQ donde está, deja el z en el umbral: "corto si ES ≥ 6,530.25 · largo si ES ≤ 6,494.00". Se ven en el
     tablero junto al valor justo de ES implicado por NQ (z = 0).
  6. ÓRDENES: al cierre de la hora, qué comprar y qué vender, cuántos contratos (con el β de ese cierre) y el plan
     congelado (objetivo, stop de z, stop de tiempo en vidas medias); en cuanto abre la barra siguiente, el precio
     de papel y, en las salidas, el resultado en US$ con comisión, deslizamiento y rolls, en el mismo hilo.
  7. LA PUERTA: aviso cuando la prueba estricta se abre o se cierra (con los p-valores que la movieron); cada
     re-estimación manda un resumen silencioso. El tablero muestra qué pide cada prueba y si pasa.
  8. ROLLS: aviso cuando rola una pierna, con el salto medido con la .n.1 y su costo si hay posición.
  9. Auditoría de papel (la de la v3: US$, Sharpe, bootstrap estacionario, acierto, factor de beneficio) sobre toda
     la historia de papel y sobre lo que va en vivo, y la curva del umbral óptimo de la última re-estimación.

Nunca envía órdenes: todo es de PAPEL. La ejecución de papel es la apertura de la hora (lo de la v3); el aviso
llega ~1 min después (la barra de 1 h se cierra cuando ya llegó el último minuto de las dos piernas): con una vida
media de horas eso no cambia la cuenta, pero tu precio real será el de ese momento, no el de papel.

Tablero: http://127.0.0.1:8160 (… Iceberg 8130, VEX/CEX 8140, Gamma 8150).

Requisitos: pip install databento numpy pandas scipy statsmodels
API key: setx DATABENTO_API_KEY "db-..."  (una vez; nunca en el código)
Telegram: el mismo telegram_credenciales.txt de los otros indicadores (o token_telegram.txt) junto a este script,
          con TELEGRAM_TOKEN = "..." y TELEGRAM_CHAT_ID = "...", o esas dos variables de entorno.

Uso:
  python co_integracion_live_ac.py                       # ES.n.0 / NQ.n.0 en vivo + tablero + Telegram
  python co_integracion_live_ac.py --y MES.n.0 --x MNQ.n.0 --mult-y 5 --mult-x 2     # micros
  python co_integracion_live_ac.py --alfa 0.10           # la puerta al 10 % (más potencia, ver la v3)
  python co_integracion_live_ac.py --demo                # par sintético de la v3 minuto a minuto, sin Databento
  python co_integracion_live_ac.py --probar-telegram
  python co_integracion_live_ac.py --autoprueba
Con el botón ▶ de VS Code (sin banderas) corre en vivo con lo que diga `Config`.
Detener: Ctrl+C en la terminal.
"""
from __future__ import annotations

import argparse
import copy
import csv
import gc
import html
import itertools
import json
import logging
import math
import os
import queue
import re
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.request
import warnings
import webbrowser
import zoneinfo
from collections import deque
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd
from databento_dbn import ErrorCode, SystemCode
from scipy.special import ndtr

IDENTIFICADOR = "coint-live-ac"
warnings.filterwarnings("ignore", message=r".*(not finalized|UTC midnight|greater than 5 GB|reduced quality|No data found).*")
CARPETA_SCRIPT = Path(__file__).resolve().parent

NS = 1_000_000_000
HORA_NS = 3600 * NS
MS = 1_000_000
TZ_CME = "America/Chicago"
_ZCME = zoneinfo.ZoneInfo(TZ_CME)
MOTIVOS = ("objetivo", "stop_z", "stop_tiempo", "ruptura", "fin")

LOG = logging.getLogger("coint_live")


# =============================================================================
# 1. CONFIGURACIÓN (la de la v3 + lo de Live)
# =============================================================================
@dataclass(frozen=True)
class Config:
    # --- Datos (v3) ---
    dataset: str = "GLBX.MDP3"
    symbol_y: str = "ES.n.0"                # dependiente (la pierna que se compra en "largo spread")
    symbol_x: str = "NQ.n.0"                # cobertura
    stype_in: str = "continuous"
    esquema: str = "ohlcv-1h"               # el calentamiento; en vivo siempre ohlcv-1m (se agrega a `barra_min`)
    barra_min: int = 60                     # tamaño de la barra en minutos
    historia_dias: int = 60                 # historia para calentar: al menos una ventana de formación
    ajustar_rolls: bool = True              # baja también <raíz>.n.1 para medir cada roll
    cache_dir: str = "datos_databento"
    salida_dir: str = "salidas_coint_live"
    costo_max_usd: float = 10.0             # tope del costo de la descarga del calentamiento

    # --- Contratos (ES y NQ; micros: MES 5 y MNQ 2) (v3) ---
    mult_y: float = 50.0                    # US$ por punto de ES
    mult_x: float = 20.0                    # US$ por punto de NQ
    tick_y: float = 0.25
    tick_x: float = 0.25
    contratos_y: int = 2                    # la unidad de spread: n_y de Y contra n_x de X
    comision_usd: float = 2.0               # por contrato y por lado
    deslizamiento_ticks: float = 0.5        # por lado: cruzar medio spread a mercado
    roll_ticks: float = 1.0                 # costo del spread de calendario al rolar
    capital_usd: float = 200_000.0          # para expresar el P&L en %

    # --- Modelo (v3) ---
    escala: str = "log"                     # "log" (β = elasticidad) o "niveles" (β en puntos)
    formacion_barras: int = 690             # ≈ 30 sesiones de 23 h
    reestimar_cada: int = 23                # ≈ una vez por sesión
    kalman: str = "mle"                     # "mle" (q_m, q_β y r por máxima verosimilitud) o "fijo"
    beta_dinamico: bool = True              # False: β de MCO de cada ventana, fijo hasta la siguiente
    phi_fijo: float = 0.5 ** (1 / 24)
    q_m: float = 3e-7
    q_beta: float = 1e-8
    r_obs: float = 1e-7
    kalman_arranque: int = 30

    # --- Prueba estricta (v3) ---
    prueba: str = "estricta"                # "estricta" | "eg" | "ninguna"
    alfa: float = 0.05                      # para ABRIR la puerta: todas las pruebas a este nivel
    alfa_cierre: float = 0.50               # para CERRARLA: que la evidencia se pierda de verdad
    bootstrap_ou: int = 200
    adf_maxlag: int = 12
    johansen_lags: int = 2
    vida_media_min_h: float = 2.0
    vida_media_max_frac: float = 0.25

    # --- Señales (v3) ---
    umbral: str = "optimo"                  # "optimo" (con costos, sobre el OU) o "fijo"
    z_entrada: float = 2.0
    z_salida: float = 0.5
    z_stop: float = 4.0
    z_entrada_min: float = 1.5
    z_entrada_max: float = 3.0
    salidas_opt: tuple = (0.0, 0.25, 0.5, 0.75)
    stop_tiempo_vidas: float = 3.0
    salir_si_rompe: bool = True
    enfriamiento_barras: int = 24

    # --- Evaluación (v3: la auditoría de las operaciones de papel) ---
    bootstrap: int = 2000
    bloque_dias: int = 5
    semilla: int = 17

    # --- Mercado sintético (v3: --demo y autoprueba) ---
    sint_sesiones: int = 130
    sint_inicio: str = "2026-03-02"
    sint_vida_media_h: float = 24.0
    sint_sd_spread: float = 0.0022
    sint_sd_paseo: float = 0.00001
    sint_beta: float = 0.80
    sint_sd_beta: float = 0.0005
    sint_ruptura: tuple = (0.58, 0.70)
    sint_precio_y: float = 6500.0
    sint_precio_x: float = 23500.0
    sint_vol_x_h: float = 0.0030

    # --- [live] Avisos ---
    aviso_en_curso: bool = True             # "si la hora cierra así, abre / cierra" (una vez por barra y tipo)
    aviso_reestimacion: bool = True         # el resumen de cada re-estimación (silencioso)
    reciente_min: float = 10.0              # a Telegram solo lo de los últimos N minutos (no el replay viejo)

    # --- [live] Conexión ---
    replay_max_h: float = 23.0
    heartbeat_s: int = 15
    analisis_s: float = 20.0                # auditoría de papel

    # --- Tablero ---
    zona_local: str = "America/Mexico_City"
    host: str = "127.0.0.1"
    puerto: int = 8160
    abrir_navegador: bool = True
    sonido: bool = True
    max_barras: int = 6000


CFG = Config()


# =============================================================================
# 2. CALENDARIO DE CME
# =============================================================================
# La sesión de CME de la fecha D va de las 17:00 de Chicago del día anterior a las 16:00 de D
# (con la pausa de 16:00 a 17:00). Las barras de 1 h empiezan a las 17:00, 18:00, …, 15:00.
def fechas_sesion(ts_ns: np.ndarray) -> np.ndarray:
    """Fecha de sesión (días desde 1970) de cada instante."""
    ts_ns = np.asarray(ts_ns, dtype=np.int64)
    if ts_ns.size == 0:
        return np.zeros(0, np.int64)
    loc = pd.to_datetime(ts_ns, utc=True).tz_convert(TZ_CME).tz_localize(None)
    d = (loc + pd.Timedelta(hours=7)).normalize()
    return (d.asi8 // (86400 * NS)).astype(np.int64)


def dia_a_fecha(dia: int) -> date:
    return date(1970, 1, 1) + timedelta(days=int(dia))


def _ns_de(fecha: date, hora: int, minuto: int = 0) -> int:
    dt = datetime(fecha.year, fecha.month, fecha.day, hora, minuto, tzinfo=_ZCME)
    return int(dt.timestamp()) * NS


def inicios_barras(inicio: str, sesiones: int, minutos: int = 60) -> np.ndarray:
    """Inicios de barra (ns UTC) de `sesiones` sesiones hábiles consecutivas de CME."""
    out = []
    for d in pd.bdate_range(inicio, periods=sesiones):
        # abre el día ANTERIOR a las 17:00 de Chicago (con su horario de verano)
        base = _ns_de(d.date() - timedelta(days=1), 17, 0)
        n = (23 * 60) // minutos
        out.append(base + np.arange(n, dtype=np.int64) * minutos * 60 * NS)
    return np.concatenate(out) if out else np.zeros(0, np.int64)


# =============================================================================
# 3. EL PAR: ALINEAR, AJUSTAR ROLLS Y PASAR A LA ESCALA DEL MODELO
# =============================================================================
# Un continuo como ES.n.0 cambia de contrato en el roll y el precio SALTA por el acarreo (el
# contrato siguiente cotiza con prima). Sin ajuste, ese salto entra en el spread como si fuera
# un movimiento: en ES y NQ ronda el 0.6-0.9 %, del orden de un desvío completo del spread.
# El ajuste es HACIA ADELANTE (causal): el pasado no se toca; desde el roll, al precio real se
# le resta el salto acumulado. Así las diferencias dentro de un contrato son las reales (el P&L
# en puntos es exacto) y la serie no salta. El salto se mide con <raíz>.n.1 en la barra previa
# al roll: el contrato que entra ya cotizaba ahí como segundo.
BARRA_CAMPOS = ("ts", "o", "h", "l", "c", "v", "iid")


def barras_vacias() -> dict:
    return {k: np.zeros(0, np.int64 if k in ("ts", "v", "iid") else float) for k in BARRA_CAMPOS}


def _indexar(b: dict | None) -> dict:
    if b is None or len(b["ts"]) == 0:
        return {}
    return {int(t): i for i, t in enumerate(b["ts"])}


def ajuste_rolls(b0: dict, b1: dict | None, ts: np.ndarray) -> tuple:
    """Para la pierna con barras `b0` (continuo .n.0) ya alineadas en `ts`: salto de cada roll y
    salto acumulado. Devuelve (G, roll, aproximado): G[i] se resta a los precios de la barra i."""
    n = ts.size
    iid = b0["iid"]
    G = np.zeros(n)
    roll = np.zeros(n, bool)
    aprox = np.zeros(n, bool)
    if n == 0:
        return G, roll, aprox
    idx1 = _indexar(b1)
    acum = 0.0
    for i in range(1, n):
        if iid[i] != iid[i - 1]:
            roll[i] = True
            j = idx1.get(int(ts[i - 1]))
            if j is not None and int(b1["iid"][j]) == int(iid[i]):
                gap = float(b1["c"][j]) - float(b0["c"][i - 1])      # nuevo − viejo, mismo instante
            else:
                gap = float(b0["o"][i]) - float(b0["c"][i - 1])      # sin .n.1: el salto entero
                aprox[i] = True
            acum += gap
        G[i] = acum
    return G, roll, aprox


def unir_par(y0: dict, x0: dict, y1: dict | None = None, x1: dict | None = None,
             cfg: Config = CFG) -> dict:
    """Barras de las dos piernas alineadas por inicio de barra (solo las horas en que operaron
    las dos), con los rolls ajustados hacia adelante y la escala del modelo."""
    comunes = np.intersect1d(y0["ts"], x0["ts"])
    iy = np.searchsorted(y0["ts"], comunes)
    ix = np.searchsorted(x0["ts"], comunes)
    Y = {k: np.asarray(v)[iy] for k, v in y0.items()}
    X = {k: np.asarray(v)[ix] for k, v in x0.items()}
    b = {"ts": comunes.astype(np.int64)}
    for pie, B, B1 in (("y", Y, y1), ("x", X, x1)):
        G, roll, aprox = ajuste_rolls(B, B1 if cfg.ajustar_rolls else None, comunes)
        if not cfg.ajustar_rolls:
            G = np.zeros_like(G)
        for k in ("o", "h", "l", "c"):
            b[f"{k}_{pie}"] = B[k].astype(float) - G          # precio ajustado
        b[f"g_{pie}"] = G                                     # real = ajustado + G
        b[f"roll_{pie}"] = roll
        b[f"aprox_{pie}"] = aprox
        b[f"iid_{pie}"] = B["iid"].astype(np.int64)
        b[f"v_{pie}"] = B["v"].astype(np.int64)
    b["sesion"] = fechas_sesion(b["ts"])
    return a_escala(b, cfg)


def a_escala(b: dict, cfg: Config) -> dict:
    """y, x en la escala del modelo: logaritmo del precio ajustado, o el precio en puntos."""
    if cfg.escala == "log":
        b["y"] = np.log(np.maximum(b["c_y"], 1e-9))
        b["x"] = np.log(np.maximum(b["c_x"], 1e-9))
    elif cfg.escala == "niveles":
        b["y"] = b["c_y"].astype(float)
        b["x"] = b["c_x"].astype(float)
    else:
        raise ValueError(f"escala desconocida: {cfg.escala!r} (log | niveles)")
    return b


def recortar_barras(b: dict, i0: int, i1: int) -> dict:
    return {k: v[i0:i1] for k, v in b.items()}


def agregar_barras(b: dict, minutos: int) -> dict:
    """Barras de 1 min → barras de `minutos` (alineadas a la hora de reloj). Vectorizado; el
    motor en vivo hace lo mismo registro a registro (`Agregador`)."""
    if len(b["ts"]) == 0:
        return barras_vacias()
    paso = minutos * 60 * NS
    k = (b["ts"] // paso) * paso
    cortes = np.flatnonzero(np.r_[True, k[1:] != k[:-1]])
    fin = np.r_[cortes[1:], len(k)]
    return {"ts": k[cortes], "o": b["o"][cortes], "c": b["c"][fin - 1],
            "h": np.maximum.reduceat(b["h"], cortes), "l": np.minimum.reduceat(b["l"], cortes),
            "v": np.add.reduceat(b["v"], cortes), "iid": b["iid"][fin - 1]}


# =============================================================================
# 4. EL MODELO: HEDGE RATIO DINÁMICO Y SPREAD ORNSTEIN-UHLENBECK EN UN SOLO FILTRO
# =============================================================================
# Espacio de estados (Harvey 1989; Durbin y Koopman 2012; con el spread como estado OU como en
# Elliott, van der Hoek y Malcolm 2005):
#     y_t − α = m_t + β_t·(x_t − c) + v_t          v ~ N(0, r)     ruido de medición
#     m_t     = φ·m_{t−1} + η_t                    η ~ N(0, q_m)   el SPREAD: un OU discreto
#     β_t     = β_{t−1} + w_t                      w ~ N(0, q_β)   el hedge ratio, que se mueve
# α y c son el intercepto y la media de x de la ventana de formación: CENTRAR x separa la
# pendiente del nivel (en log, x ≈ 10.06 con variaciones de ±0.05: sin centrar, un cambio de
# β de 0.001 mueve la predicción 0.01 = 1 %, y el β "dinámico" se come el nivel).
# Por qué el spread va DENTRO del filtro: con el modelo de tu script (α y β como paseos
# aleatorios y ruido blanco) la máxima verosimilitud usa α y β para perseguir las desviaciones
# que son del spread —medido: ψ_β = q_β/r de 100 a 2 000— y el "hedge ratio dinámico" se
# vuelve ruido que se come la señal. Con m_t como estado, lo persistente y reversible va a m y β
# solo se mueve si los datos lo piden. La vida media es la de φ: ln 2 / (−ln φ) barras.
class KalmanOU:
    """Forma de COVARIANZAS, escalar (el motor en vivo, barra a barra). Estado [m, β]."""
    __slots__ = ("m", "b", "p11", "p12", "p22", "phi", "qm", "qb", "r", "alfa", "c")

    def __init__(self, m: float, b: float, P, phi: float, qm: float, qb: float, r: float,
                 alfa: float, c: float):
        self.m, self.b = float(m), float(b)
        self.p11, self.p12, self.p22 = float(P[0][0]), float(P[0][1]), float(P[1][1])
        self.phi, self.qm, self.qb, self.r = float(phi), float(qm), float(qb), float(r)
        self.alfa, self.c = float(alfa), float(c)

    def paso(self, y: float, x: float) -> tuple:
        """Predice y corrige con (y, x). Devuelve (m previo, β previo, innovación, varianza)."""
        xt = x - self.c
        ph = self.phi
        m_pr = ph * self.m
        b_pr = self.b
        p11 = ph * ph * self.p11 + self.qm
        p12 = ph * self.p12
        p22 = self.p22 + self.qb
        e = (y - self.alfa) - m_pr - b_pr * xt
        u1 = p11 + p12 * xt
        u2 = p12 + p22 * xt
        f = u1 + u2 * xt + self.r
        self.m = m_pr + u1 / f * e
        self.b = b_pr + u2 / f * e
        self.p11 = p11 - u1 * u1 / f
        self.p12 = p12 - u1 * u2 / f
        self.p22 = p22 - u2 * u2 / f
        return m_pr, b_pr, e, f

    def recentrar(self, alfa: float, c: float) -> None:
        """y = α + β(x − c) + m = α' + β(x − c') + m'  ⇒  m' = m + (α − α') + β(c' − c);
        P' = T P Tᵀ con T = [[1, c' − c], [0, 1]]."""
        d = float(c) - self.c
        self.m += (self.alfa - float(alfa)) + self.b * d
        p11, p12, p22 = self.p11, self.p12, self.p22
        self.p11 = p11 + 2.0 * d * p12 + d * d * p22
        self.p12 = p12 + d * p22
        self.alfa, self.c = float(alfa), float(c)

    def cambiar(self, phi: float, qm: float, qb: float, r: float) -> None:
        self.phi, self.qm, self.qb, self.r = float(phi), float(qm), float(qb), float(r)


def kalman_informacion(y: np.ndarray, x: np.ndarray, alfa: np.ndarray, c: np.ndarray,
                       phi: np.ndarray, qm: np.ndarray, qb: np.ndarray, r: np.ndarray,
                       s0: np.ndarray, P0: np.ndarray, reinicio: dict | None = None,
                       estatico: bool = False) -> dict:
    """La misma recursión en forma de INFORMACIÓN (Ω = P⁻¹, ξ = Ω·s), para el motor histórico.

    Otra derivación del mismo filtro: la corrección SUMA información (Ω = Ω⁻ + hhᵀ/r) en vez
    de restar covarianza. Los parámetros vienen por barra (cambian en cada fila del calendario;
    al cambiar α o c el estado se transforma igual que en `KalmanOU.recentrar`). Las pruebas
    exigen que las dos formas coincidan."""
    if estatico:
        return _informacion_estatica(y, x, alfa, c, phi, qm, r, s0, P0, reinicio or {})
    n = y.size
    out = {k: np.full(n, np.nan) for k in ("m_pr", "b_pr", "e", "f", "m", "b", "p11", "p12", "p22")}
    s = np.asarray(s0, float).copy()
    Om = np.linalg.inv(np.asarray(P0, float))
    xi = Om @ s
    a_prev = alfa[0] if n else 0.0
    c_prev = c[0] if n else 0.0
    for t in range(n):
        if alfa[t] != a_prev or c[t] != c_prev:
            s = np.linalg.solve(Om, xi)
            P = np.linalg.inv(Om)
            d = c[t] - c_prev
            T = np.array([[1.0, d], [0.0, 1.0]])
            s = np.array([s[0] + (a_prev - alfa[t]) + s[1] * d, s[1]])
            Om = np.linalg.inv(T @ P @ T.T)
            xi = Om @ s
            a_prev, c_prev = alfa[t], c[t]
        h = np.array([1.0, x[t] - c[t]])
        Fm = np.array([[phi[t], 0.0], [0.0, 1.0]])
        P = np.linalg.inv(Om)
        s_po_prev = np.linalg.solve(Om, xi)
        s_pr = Fm @ s_po_prev
        P_pr = Fm @ P @ Fm.T + np.diag([qm[t], qb[t]])
        Om_pr = np.linalg.inv(P_pr)
        yt = y[t] - alfa[t]
        e = yt - h @ s_pr
        f = h @ P_pr @ h + r[t]
        Om = Om_pr + np.outer(h, h) / r[t]
        xi = Om_pr @ s_pr + h * (yt / r[t])
        s_po = np.linalg.solve(Om, xi)
        P_po = np.linalg.inv(Om)
        out["m_pr"][t], out["b_pr"][t], out["e"][t], out["f"][t] = s_pr[0], s_pr[1], e, f
        out["m"][t], out["b"][t] = s_po
        out["p11"][t], out["p12"][t], out["p22"][t] = P_po[0, 0], P_po[0, 1], P_po[1, 1]
    return out


def _informacion_estatica(y, x, alfa, c, phi, qm, r, s0, P0, reinicio: dict) -> dict:
    """β fijo (el de MCO de cada ventana): el estado es solo m y la información es un escalar.
    En cada fila nueva el filtro vuelve a arrancar del estado final de su ventana."""
    n = y.size
    out = {k: np.full(n, np.nan) for k in ("m_pr", "b_pr", "e", "f", "m", "b", "p11", "p12", "p22")}
    beta = float(s0[1])
    om = 1.0 / float(np.asarray(P0)[0][0])
    xi = om * float(s0[0])
    for t in range(n):
        if t in reinicio:
            (m_r, b_r), P_r = reinicio[t]
            beta = float(b_r)
            om = 1.0 / float(P_r[0][0])
            xi = om * float(m_r)
        m_pr = phi[t] * (xi / om)
        p_pr = phi[t] * phi[t] / om + qm[t]
        yt = y[t] - alfa[t] - beta * (x[t] - c[t])
        e = yt - m_pr
        om = 1.0 / p_pr + 1.0 / r[t]
        xi = m_pr / p_pr + yt / r[t]
        out["m_pr"][t], out["b_pr"][t], out["e"][t], out["f"][t] = m_pr, beta, e, p_pr + r[t]
        out["m"][t], out["b"][t] = xi / om, beta
        out["p11"][t], out["p12"][t], out["p22"][t] = 1.0 / om, 0.0, 0.0
    return out


def _vero_candidatos(yt: np.ndarray, xt: np.ndarray, b0: float, p22s: np.ndarray,
                     phi: np.ndarray, psi_b: np.ndarray, rho_v: np.ndarray) -> tuple:
    """Log-verosimilitud CONCENTRADA de muchos candidatos (φ, ψ_β = q_β/q_m, ρ = r/q_m) a la vez.
    Todas las varianzas se escriben como q_m·(algo): el filtro corre con q_m = 1 y
    q̂_m = Σ e²/f / n sale en forma cerrada (Harvey 1989, §3.4). Arranque: m₀ = 0 con su
    varianza estacionaria 1/(1 − φ²); β₀ = β de MCO de la ventana."""
    G = phi.size
    m = np.zeros(G)
    b = np.full(G, float(b0))
    p11 = 1.0 / (1.0 - phi * phi)
    p12 = np.zeros(G)
    p22 = p22s.copy()
    ph2 = phi * phi
    S = np.zeros(G)
    L = np.zeros(G)
    for t in range(yt.size):
        xt_ = xt[t]
        m = phi * m
        p11 = ph2 * p11 + 1.0
        p12 = phi * p12
        p22 = p22 + psi_b
        e = yt[t] - m - b * xt_
        u1 = p11 + p12 * xt_
        u2 = p12 + p22 * xt_
        f = u1 + u2 * xt_ + rho_v
        m = m + u1 / f * e
        b = b + u2 / f * e
        p11 = p11 - u1 * u1 / f
        p12 = p12 - u1 * u2 / f
        p22 = p22 - u2 * u2 / f
        S += e * e / f
        L += np.log(f)
    n = max(yt.size, 1)
    q_hat = S / n
    return -0.5 * (n * (math.log(2 * math.pi) + 1.0 + np.log(q_hat)) + L), q_hat


def kalman_mle(yt: np.ndarray, xt: np.ndarray, b0: float, sxx: float, phi: float,
               estatico: bool = False) -> dict:
    """(q_m, q_β, r) por máxima verosimilitud con φ DADO (la velocidad de reversión se estima
    aparte, con corrección de sesgo: la verosimilitud con φ libre la subestima un tercio porque el
    β dinámico se lleva parte de la persistencia; medido con Monte Carlo). Rejilla gruesa y fina
    sobre ψ_β = q_β/q_m y ρ = r/q_m, vectorizada. Si la superficie es plana, dentro de 1 unidad del
    máximo se elige lo MÁS ESTABLE (menor ψ_β): lo que los datos no distinguen no se inventa."""
    def evaluar(lpb, lrv):
        B, R = np.meshgrid(lpb, lrv, indexing="ij")
        ph = np.full(B.size, float(phi))
        if estatico:                                   # β fijo en el de MCO: sin varianza ni ruido
            p22 = np.zeros(B.size)
            pb = np.zeros(B.size)
        else:
            p22 = np.full(B.size, 10.0 / ((1.0 - phi * phi) * max(sxx, 1e-18)))
            pb = 10.0 ** B.ravel()
        ll, q = _vero_candidatos(yt, xt, b0, p22, ph, pb, 10.0 ** R.ravel())
        return B.ravel(), R.ravel(), ll, q
    B1, R1, ll1, q1 = evaluar(np.array([-np.inf]) if estatico else np.arange(-6.0, 2.01, 0.5),
                              np.arange(-3.0, 1.01, 0.5))
    k = int(np.nanargmax(ll1))
    B2, R2, ll2, q2 = evaluar(np.array([-np.inf]) if estatico else B1[k] + np.arange(-0.5, 0.51, 0.1),
                              R1[k] + np.arange(-0.5, 0.51, 0.1))
    B, R, ll, q = np.r_[B1, B2], np.r_[R1, R2], np.r_[ll1, ll2], np.r_[q1, q2]
    casi = np.flatnonzero(ll >= np.nanmax(ll) - 1.0)
    # dentro de 1 unidad del máximo: el de menor ψ_β, y luego el de menor ρ
    j = int(casi[np.lexsort((R[casi], B[casi]))][0]) if casi.size else int(np.nanargmax(ll))
    pb = 0.0 if estatico else float(10.0 ** B[j])
    return {"qm": float(q[j]), "qb": float(q[j] * pb), "r": float(q[j] * 10.0 ** R[j]),
            "psi_b": pb, "rho_v": float(10.0 ** R[j]), "ll": float(ll[j])}


# =============================================================================
# 5. ORNSTEIN-UHLENBECK: VIDA MEDIA, AR(1) DE CONTRASTE Y TIEMPOS DE PASO
# =============================================================================
# dS = θ(μ − S)dt + σ dW muestreado cada Δ es EXACTAMENTE un AR(1): φ = e^{−θΔ}; la vida media
# es ln 2/θ = −Δ·ln 2/ln φ. Tu script usa ln 2/(1 − φ) (la aproximación de primer orden) sobre
# un spread que el filtro ya había achicado. El φ estimado está sesgado HACIA ABAJO en
# muestras finitas (Kendall 1954: E[φ̂ − φ] ≈ −(1 + 3φ)/n): sin corregir, la vida media sale
# corta y la estrategia promete más de lo que da. `ajustar_ou` es el AR(1) directo, que se usa
# como contraste sobre el spread estático de MCO.
def vida_media_h(phi: float, horas_barra: float) -> float:
    if not np.isfinite(phi) or phi >= 1.0:
        return np.inf
    if phi <= 0.0:
        return 0.5 * horas_barra
    return -math.log(2.0) / math.log(phi) * horas_barra


def _ar1_filas(U: np.ndarray) -> np.ndarray:
    """φ̂ de MCO (con intercepto) de cada fila de U."""
    u0, u1 = U[:, :-1], U[:, 1:]
    d0 = u0 - u0.mean(1, keepdims=True)
    d1 = u1 - u1.mean(1, keepdims=True)
    return (d0 * d1).sum(1) / (d0 * d0).sum(1)


def ou_bootstrap(y: np.ndarray, x: np.ndarray, horas_barra: float, B: int = 200) -> dict:
    """Velocidad de reversión del spread con CORRECCIÓN DE SESGO por bootstrap paramétrico.

    El φ de MCO del residuo de una regresión estimada está sesgado hacia abajo bastante más que
    lo que dice Kendall (1954) para un AR(1) simple, porque MCO también eligió el β que hace el
    residuo lo más estacionario posible. Se simula el MISMO procedimiento (x paseo aleatorio con
    su volatilidad, residuo AR(1) con φ̂ y σ̂, MCO de y sobre x, AR(1) del residuo) B veces y se
    resta el sesgo medio; el intervalo al 90 % sale de la misma distribución. Medido: con 690
    barras y vidas medias verdaderas de 12/24/48/96 h, MCO da 10.7/18.1/29.2/41.5 h y la
    corrección 12.5/24.1/51.1/104.3 h, con intervalos que cubren la verdad el 89-96 % de las veces.
    La semilla sale de los propios datos: la misma ventana da el mismo resultado en los dos motores."""
    n = y.size
    xt = x - x.mean()
    A = np.column_stack([np.ones(n), xt])
    coef = np.linalg.lstsq(A, y, rcond=None)[0]
    u = y - A @ coef
    phi = float(_ar1_filas(u[None, :])[0])
    e = u[1:] - (u[1:].mean() + phi * (u[:-1] - u[:-1].mean()))
    sig_e = float(e.std(ddof=2))
    sdx = float(np.diff(x).std(ddof=1))
    rng = np.random.default_rng(int(abs(float(np.sum(y)) * 1e6)) % (2 ** 32))
    ph = min(max(phi, -0.99), 0.9999)
    X = np.cumsum(rng.normal(0.0, sdx, (B, n)), axis=1)
    E = rng.normal(0.0, sig_e, (B, n))
    U = np.empty((B, n))
    U[:, 0] = E[:, 0] / math.sqrt(max(1.0 - ph * ph, 1e-6))
    for t in range(1, n):
        U[:, t] = ph * U[:, t - 1] + E[:, t]
    Xt = X - X.mean(1, keepdims=True)
    Yb = coef[1] * Xt + U
    bb = (Xt * (Yb - Yb.mean(1, keepdims=True))).sum(1) / (Xt * Xt).sum(1)
    pb = _ar1_filas(Yb - Yb.mean(1, keepdims=True) - bb[:, None] * Xt)
    sesgo = float(pb.mean() - phi)
    phi_bc = min(phi - sesgo, 0.999999)
    lo = phi_bc - (float(np.quantile(pb, 0.95)) - float(pb.mean()))
    hi = phi_bc - (float(np.quantile(pb, 0.05)) - float(pb.mean()))
    return {"phi_mco": phi, "phi": phi_bc, "sesgo": sesgo, "sigma_e": sig_e,
            "vida_media_h": vida_media_h(phi_bc, horas_barra),
            "vm_mco_h": vida_media_h(phi, horas_barra),
            "vm_lo": vida_media_h(lo, horas_barra), "vm_hi": vida_media_h(hi, horas_barra)}


def ajustar_ou(s: np.ndarray, horas_barra: float) -> dict:
    """AR(1) directo de una serie (sin corrección): el contraste 'ingenuo' del reporte."""
    s = np.asarray(s, float)
    s = s[np.isfinite(s)]
    if s.size < 30:
        return {"phi": np.nan, "vida_media_h": np.nan, "sigma_eq": np.nan}
    phi = float(_ar1_filas(s[None, :])[0])
    return {"phi": phi, "vida_media_h": vida_media_h(phi, horas_barra),
            "sigma_eq": float(np.std(s, ddof=1))}


# Tiempos medios de paso del OU tipificado (z estacionario N(0,1)): dz = −θz dt + √(2θ) dW.
# Con la función de escala s'(z) = e^{z²/2} y la de velocidad m(z) = e^{−z²/2}/θ:
#   de −a a −b (una barrera, b < a):   T = (√(2π)/θ)·∫_{−a}^{−b} e^{y²/2} Φ(y) dy
#   de −b hasta |z| = a (dos barreras): T = (√(2π)/θ)·∫_{−a}^{−b} e^{y²/2} (½ − Φ(y)) dy
# (la constante ½ sale de la simetría Φ(y) + Φ(−y) = 1). Las pruebas lo comparan con Monte Carlo.
_W = np.linspace(0.0, 6.0, 12001)
_EZ = np.exp(0.5 * _W * _W)
_F1 = _EZ * ndtr(-_W)


def _acum(f: np.ndarray) -> np.ndarray:
    return np.r_[0.0, np.cumsum(0.5 * (f[1:] + f[:-1]) * np.diff(_W))]


_J1, _J2 = _acum(_F1), _acum(_EZ)


def tiempos_ou(a, b) -> tuple:
    """(tiempo dentro de la operación, tiempo fuera hasta la siguiente señal), en unidades de 1/θ."""
    j1a, j1b = np.interp(a, _W, _J1), np.interp(b, _W, _J1)
    j2a, j2b = np.interp(a, _W, _J2), np.interp(b, _W, _J2)
    k = math.sqrt(2.0 * math.pi)
    return k * (j1a - j1b), k * (0.5 * (j2a - j2b) - (j1a - j1b))


def umbral_optimo(sigma_eq: float, costo: float, theta_h: float, cfg: Config) -> dict:
    """El par (entrada a, salida b), en desviaciones del spread, que maximiza la ganancia ESPERADA
    POR HORA de un OU con costos: ((a − b)·σ − costo) / (T_dentro + T_fuera). Es el planteamiento
    de Bertram (2010) con operaciones de los dos lados y espera entre ellas. Como los tiempos
    escalan con 1/θ, el umbral depende de costo/σ: si el spread se mueve poco frente a lo que
    cuesta operarlo, el umbral se abre (y si ninguno gana, no hay umbral rentable)."""
    if not (np.isfinite(sigma_eq) and sigma_eq > 0 and np.isfinite(theta_h) and theta_h > 0):
        return {"z_in": np.nan, "z_out": np.nan, "ganancia_h": np.nan}
    aa = np.arange(cfg.z_entrada_min, cfg.z_entrada_max + 1e-9, 0.05)
    mejor = (-np.inf, np.nan, np.nan)
    for b in cfg.salidas_opt:
        a = aa[aa > b + 0.2]
        if a.size == 0:
            continue
        t_in, t_out = tiempos_ou(a, np.full(a.size, b))
        g = ((a - b) * sigma_eq - costo) / ((t_in + t_out) / theta_h)
        k = int(np.argmax(g))
        if g[k] > mejor[0]:
            mejor = (float(g[k]), float(a[k]), float(b))
    return {"z_in": mejor[1], "z_out": mejor[2], "ganancia_h": mejor[0]}


def ganancia_esperada(a: float, b: float, sigma_eq: float, costo: float, theta_h: float) -> float:
    if not (np.isfinite(sigma_eq) and sigma_eq > 0 and np.isfinite(theta_h) and theta_h > 0):
        return np.nan
    t_in, t_out = tiempos_ou(a, b)
    return ((a - b) * sigma_eq - costo) / ((t_in + t_out) / theta_h)


# =============================================================================
# 6. PRUEBA ESTRICTA DE COINTEGRACIÓN
# =============================================================================
# Medido con Monte Carlo en ventanas de 460-690 barras (pares NO cointegrados, α = 5 %):
#   Engle-Granger en los dos sentidos ........ 3-6 %  (bien calibrada)
#   Johansen, traza ........................... 11-13 % (sobre-rechaza en muestras así)
#   ADF de los residuos con p de Dickey-Fuller  11-15 % (lo que imprime tu script: 3 veces el 5 %)
#   ADF del spread del filtro, críticos de EG .. 3-6 %
# Por eso la puerta usa Engle-Granger (y sobre x Y x sobre y: la prueba no es invariante a cuál
# se normaliza) con p-valores de MacKinnon (2010), más el ADF del spread que se OPERA con los
# críticos de Engle-Granger para dos series; Johansen y KPSS se reportan como diagnóstico.
# La potencia es limitada y se mide y reporta: con vida media de 24 h, Engle-Granger detecta la
# cointegración verdadera el 30-37 % de las veces con 20 sesiones y el 48-65 % con 30.
def pruebas_cointegracion(y: np.ndarray, x: np.ndarray, cfg: Config) -> dict:
    from statsmodels.tsa.stattools import coint, adfuller, kpss
    from statsmodels.tsa.vector_ar.vecm import coint_johansen
    out = {"p_eg_yx": np.nan, "p_eg_xy": np.nan, "traza": np.nan, "crit_traza": np.nan,
           "maxeig": np.nan, "crit_maxeig": np.nan, "kpss_p": np.nan, "adf_resid_p": np.nan}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            out["p_eg_yx"] = float(coint(y, x, trend="c", maxlag=cfg.adf_maxlag, autolag="bic")[1])
            out["p_eg_xy"] = float(coint(x, y, trend="c", maxlag=cfg.adf_maxlag, autolag="bic")[1])
        except (ValueError, np.linalg.LinAlgError):
            pass
        try:
            jo = coint_johansen(np.column_stack([y, x]), det_order=0, k_ar_diff=cfg.johansen_lags)
            out.update(traza=float(jo.lr1[0]), crit_traza=float(jo.cvt[0, 1]),
                       maxeig=float(jo.lr2[0]), crit_maxeig=float(jo.cvm[0, 1]))
        except (ValueError, np.linalg.LinAlgError):
            pass
        A = np.column_stack([np.ones(y.size), x])
        u = y - A @ np.linalg.lstsq(A, y, rcond=None)[0]
        try:
            out["kpss_p"] = float(kpss(u, regression="c", nlags="auto")[1])
        except (ValueError, OverflowError):
            pass
        try:
            out["adf_resid_p"] = float(adfuller(u, maxlag=cfg.adf_maxlag, autolag="bic")[1])
        except (ValueError, np.linalg.LinAlgError):
            pass
    return out


def adf_spread(s: np.ndarray, cfg: Config) -> float:
    """p-valor del ADF del spread del filtro con los críticos de Engle-Granger para 2 series
    (MacKinnon 2010, N = 2): el spread usa un β ESTIMADO y la tabla de Dickey-Fuller no aplica."""
    from statsmodels.tsa.stattools import adfuller
    from statsmodels.tsa.adfvalues import mackinnonp
    s = np.asarray(s, float)
    s = s[np.isfinite(s)]
    if s.size < 40:
        return np.nan
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            t = adfuller(s, maxlag=cfg.adf_maxlag, autolag="bic")[0]
            return float(mackinnonp(t, regression="c", N=2))
        except (ValueError, np.linalg.LinAlgError):
            return np.nan


def contratos_x(beta: float, precio_y: float, precio_x: float, cfg: Config) -> int:
    """Contratos de X por la unidad de spread (cfg.contratos_y de Y). En log, β es elasticidad:
    se cubre β dólares de X por cada dólar de Y. En niveles, β puntos de X por punto de Y."""
    if not (np.isfinite(beta) and beta > 0 and precio_y > 0 and precio_x > 0):
        return 0
    if cfg.escala == "log":
        h = beta * cfg.contratos_y * cfg.mult_y * precio_y / (cfg.mult_x * precio_x)
    else:
        h = beta * cfg.contratos_y * cfg.mult_y / cfg.mult_x
    return int(round(h))


def costos_unidad(nx: int, cfg: Config) -> float:
    """Costo en USD de UN lado (entrada o salida) de la unidad de spread."""
    return (cfg.contratos_y * (cfg.comision_usd + cfg.deslizamiento_ticks * cfg.tick_y * cfg.mult_y)
            + nx * (cfg.comision_usd + cfg.deslizamiento_ticks * cfg.tick_x * cfg.mult_x))


def valor_unidad(precio_y: float, cfg: Config) -> float:
    """USD que vale un movimiento de 1 en el spread (1 log ≈ 100 % de la pierna Y; o 1 punto)."""
    return cfg.contratos_y * cfg.mult_y * (precio_y if cfg.escala == "log" else 1.0)


def calibrar_ventana(y: np.ndarray, x: np.ndarray, cfg: Config, precio_y: float,
                     precio_x: float) -> dict:
    """Una fila del calendario con SOLO la ventana de formación (y, x en escala del modelo;
    precios reales al cierre de la última barra). Función pura: el motor histórico y el motor en
    vivo la llaman con la misma ventana y obtienen exactamente lo mismo.
      1. MCO estático (α, β) con x centrado, y las pruebas de cointegración
      2. velocidad de reversión: AR(1) del spread estático con corrección por bootstrap
      3. Kalman: con esa φ, (q_m, q_β, r) por máxima verosimilitud; el filtro recorre la ventana
      4. el spread filtrado: su media y desviación (el z), y su ADF con críticos de Engle-Granger
      5. el umbral: óptimo con costos sobre el OU, o fijo
      6. las condiciones de la puerta (a α para abrir, a α_cierre para seguir abierta)"""
    n = y.size
    horas = cfg.barra_min / 60.0
    c = float(np.mean(x))
    xt = x - c
    A = np.column_stack([np.ones(n), xt])
    coef = np.linalg.lstsq(A, y, rcond=None)[0]
    alfa, beta_ols = float(coef[0]), float(coef[1])
    fila = {"c": c, "alfa": alfa, "beta_ols": beta_ols}
    fila.update(pruebas_cointegracion(y, x, cfg))
    ou = ou_bootstrap(y, x, horas, cfg.bootstrap_ou)
    phi = float(np.clip(ou["phi"], 1e-6, 0.9999))
    fila.update(phi=phi, phi_mco=ou["phi_mco"], sesgo_phi=ou["sesgo"],
                vida_media_h=vida_media_h(phi, horas), vm_mco_h=ou["vm_mco_h"],
                vm_lo=ou["vm_lo"], vm_hi=ou["vm_hi"],
                theta_h=-math.log(phi) / horas)
    yt = y - alfa
    sxx = float(np.sum(xt * xt))
    if cfg.kalman == "mle":
        ml = kalman_mle(yt, xt, beta_ols, sxx, phi, estatico=not cfg.beta_dinamico)
        qm, qb, r = ml["qm"], ml["qb"], ml["r"]
        fila.update(psi_b=ml["psi_b"], rho_v=ml["rho_v"], ll=ml["ll"])
    else:
        qm, qb, r = cfg.q_m, cfg.q_beta, cfg.r_obs
        fila.update(psi_b=qb / qm, rho_v=r / qm, ll=np.nan)
    if not cfg.beta_dinamico:
        qb = 0.0
    p22_0 = 10.0 * qm / ((1 - phi * phi) * max(sxx, 1e-18)) if cfg.beta_dinamico else 0.0
    kf = KalmanOU(0.0, beta_ols, [[qm / (1 - phi * phi), 0.0], [0.0, p22_0]],
                  phi, qm, qb, r, alfa, c)
    mm = np.empty(n)
    for t in range(n):
        kf.paso(float(y[t]), float(x[t]))
        mm[t] = kf.m
    arr = max(10, min(cfg.kalman_arranque, n // 4))
    mu = float(np.mean(mm[arr:]))
    sd_m = float(np.std(mm[arr:], ddof=1))
    fila.update(qm=qm, qb=qb, r=r, mu=mu, sigma_eq=sd_m, m_fin=kf.m, b_fin=kf.b, p11=kf.p11,
                p12=kf.p12, p22=kf.p22, adf_kalman_p=adf_spread(mm[arr:], cfg))
    nx = contratos_x(kf.b, precio_y, precio_x, cfg)
    vu = valor_unidad(precio_y, cfg)
    costo_s = 2.0 * costos_unidad(max(nx, 1), cfg) / vu if vu > 0 else np.nan
    fila.update(nx_ref=nx, costo_s=costo_s, valor_unidad=vu)
    if cfg.umbral == "optimo":
        uo = umbral_optimo(sd_m, costo_s, fila["theta_h"], cfg)
    else:
        uo = {"z_in": cfg.z_entrada, "z_out": cfg.z_salida,
              "ganancia_h": ganancia_esperada(cfg.z_entrada, cfg.z_salida, sd_m, costo_s, fila["theta_h"])}
    fila.update(z_in=uo["z_in"], z_out=uo["z_out"],
                ganancia_h_usd=uo["ganancia_h"] * vu if np.isfinite(uo["ganancia_h"]) else np.nan)
    vm_max = cfg.vida_media_max_frac * n * horas
    p_eg = max(fila["p_eg_yx"], fila["p_eg_xy"])
    fila["p_eg_max"] = p_eg
    fila["pasa_vm"] = bool(np.isfinite(fila["vida_media_h"])
                           and cfg.vida_media_min_h <= fila["vida_media_h"] <= vm_max)
    fila["pasa_econ"] = bool(np.isfinite(fila["ganancia_h_usd"]) and fila["ganancia_h_usd"] > 0)
    fila["pasa_beta"] = bool(nx >= 1)
    fila["pasa_ou"] = bool(np.isfinite(fila["z_in"]) and np.isfinite(sd_m) and sd_m > 0)
    for sufijo, a in (("", cfg.alfa), ("_cierre", cfg.alfa_cierre)):
        fila[f"pasa_eg{sufijo}"] = bool(p_eg < a)
        fila[f"pasa_adf_kalman{sufijo}"] = bool(fila["adf_kalman_p"] < a)
    fila["pasa_eg_yx"] = bool(fila["p_eg_yx"] < cfg.alfa)
    return fila


def decidir_puerta(fila: dict, abierta_antes: bool, cfg: Config) -> tuple:
    """¿Se puede operar con esta fila? Con histéresis en la prueba estricta: para ABRIR hace
    falta todo a α (Engle-Granger en los dos sentidos, ADF del spread filtrado, vida media en
    rango, umbral rentable); para SEGUIR abierta basta con que la evidencia no se haya perdido
    (p < α_cierre). Con la potencia que tienen estas pruebas (una ventana de 30 sesiones detecta
    una cointegración verdadera de vida media 24 h la mitad de las veces), exigir p < 5 % cada
    día cierra la puerta en plena cointegración; en una ruptura los p-valores se van a 0.5-1."""
    base = [k for k in ("vm", "econ", "beta", "ou") if not fila[f"pasa_{k}"]]
    if cfg.prueba == "ninguna":
        motivos = [k for k in ("beta", "ou") if not fila[f"pasa_{k}"]]
    elif cfg.prueba == "eg":
        motivos = ([] if fila["pasa_eg_yx"] else ["eg"]) + [k for k in ("beta", "ou")
                                                            if not fila[f"pasa_{k}"]]
    elif cfg.prueba == "estricta":
        suf = "_cierre" if abierta_antes else ""
        motivos = [k for k in ("eg", "adf_kalman") if not fila[f"pasa_{k}{suf}"]] + base
    else:
        raise ValueError(f"prueba desconocida: {cfg.prueba!r} (estricta | eg | ninguna)")
    return (not motivos), ",".join(motivos)


def calendario(b: dict, cfg: Config, avisar=None) -> pd.DataFrame:
    """Todas las filas: en cada barra k = F−1, F−1+Δ, … se calibra con las barras [k−F+1, k] y
    la fila rige desde la barra k+1. Causal por construcción."""
    F, D = cfg.formacion_barras, cfg.reestimar_cada
    n = len(b["ts"])
    filas = []
    ks = list(range(F - 1, n - 1, D))
    for j, k in enumerate(ks):
        i0 = k - F + 1
        py = float(b["c_y"][k] + b["g_y"][k])
        px = float(b["c_x"][k] + b["g_x"][k])
        f = calibrar_ventana(b["y"][i0:k + 1], b["x"][i0:k + 1], cfg, py, px)
        f["puerta"], f["motivo"] = decidir_puerta(f, bool(filas[-1]["puerta"]) if filas else False, cfg)
        f.update(k=k, ts=int(b["ts"][k]), rige=int(b["ts"][k + 1]))
        filas.append(f)
        if avisar is not None and (j % 10 == 0 or j == len(ks) - 1):
            avisar(j + 1, len(ks))
    return pd.DataFrame(filas)


# =============================================================================
# 7. LAS REGLAS DE OPERACIÓN (idénticas en los dos motores)
# =============================================================================
# · Una fila del calendario calculada al CIERRE de la barra k rige desde la barra k+1.
# · En la barra t: z_t = (m_{t|t} − μ)/σ con m el spread OU FILTRADO (el estado del modelo). El
#   filtro reparte cada sorpresa entre el spread y el β según lo que estimó la verosimilitud; tu
#   script, en cambio, dejaba que un intercepto que es paseo aleatorio se tragara el 9.5 % de
#   cada desvío en cada vela, y ese "spread" revertía aunque los precios no lo hicieran.
# · Decisión al cierre de t, EJECUCIÓN a la apertura de t+1 (las dos piernas).
# · Entrada: puerta abierta, sin enfriamiento, |z| ≥ z_in, y al menos 1 contrato de cobertura.
#   z ≥ z_in → corto spread (vender Y, comprar X); z ≤ −z_in → largo spread.
# · El plan se congela al entrar: salida z_out, stop z_stop, stop de tiempo k·(vida media).
# · Salidas, por prioridad: objetivo (z vuelve a ±z_out), stop_z, stop_tiempo, ruptura (la
#   prueba deja de pasar). Tras un stop o una ruptura, `enfriamiento_barras` sin entrar
#   (tu COOLDOWN_HOURS, que tu script definía y no usaba). Tras un objetivo se puede entrar
#   en la misma barra del otro lado (el z saltó al extremo contrario).
# · Contratos: n_y fijo y n_x = round(cobertura) con el β corregido y los precios del cierre de t.
# · Costos: comisión + deslizamiento por lado y contrato; al rolar una pierna con posición
#   abierta, dos comisiones más el spread de calendario. Al final de los datos se cierra al
#   último cierre.
DEC = 9            # z se redondea a 1e-9 antes de compararlo: las dos formas del filtro difieren
#                    en ~1e-12 y un empate exacto en un umbral no puede decidir distinto


def _costo_roll(ny: int, nx: int, roll_y: bool, roll_x: bool, cfg: Config) -> float:
    c = 0.0
    if roll_y:
        c += ny * (2 * cfg.comision_usd + cfg.roll_ticks * cfg.tick_y * cfg.mult_y)
    if roll_x:
        c += nx * (2 * cfg.comision_usd + cfg.roll_ticks * cfg.tick_x * cfg.mult_x)
    return c


def _en_vigor(cal: pd.DataFrame, n: int) -> np.ndarray:
    """Para cada barra, el índice de la fila del calendario que rige (−1 si ninguna)."""
    if cal is None or len(cal) == 0:
        return np.full(n, -1)
    return np.searchsorted(cal["k"].to_numpy(), np.arange(n), side="left") - 1


COLS_TRADES = ["dir", "t_dec", "t_ent", "t_dec_sal", "t_sal", "ts_ent", "ts_sal", "ny", "nx",
               "z_ent", "z_sal", "beta_ent", "py_ent", "px_ent", "py_sal", "px_sal", "bruto",
               "costos", "neto", "barras", "motivo", "vm_ent", "z_in", "z_out", "mae", "mfe",
               "rolls"]


# =============================================================================
# 8. MOTOR HISTÓRICO (vectorizado: filtro en forma de información, operaciones por búsqueda)
# =============================================================================
def correr_lote(b: dict, cal: pd.DataFrame, cfg: Config) -> dict:
    n = len(b["ts"])
    j = _en_vigor(cal, n)
    out = {"z": np.full(n, np.nan), "s": np.full(n, np.nan), "b_pr": np.full(n, np.nan),
           "b_post": np.full(n, np.nan), "puerta": np.zeros(n, bool), "z_in": np.full(n, np.nan),
           "z_out": np.full(n, np.nan), "pos": np.zeros(n, np.int64), "pnl": np.zeros(n),
           "costos": np.zeros(n), "fila": j}
    t0 = int(np.argmax(j >= 0)) if (j >= 0).any() else n
    if t0 >= n:
        out["equity"] = np.zeros(n)
        out["trades"] = pd.DataFrame(columns=COLS_TRADES)
        return out
    jj = j[t0:]
    col = {k: cal[k].to_numpy() for k in ("alfa", "c", "phi", "qm", "qb", "r", "mu", "sigma_eq",
                                          "puerta", "z_in", "z_out", "vida_media_h")}
    f0 = cal.iloc[0]
    rein = None
    if not cfg.beta_dinamico:                  # β estático: cada fila vuelve a su estado de ventana
        rein = {int(cal["k"].iloc[q]) + 1 - t0: ((cal["m_fin"].iloc[q], cal["b_fin"].iloc[q]),
                                                 np.array([[cal["p11"].iloc[q], cal["p12"].iloc[q]],
                                                           [cal["p12"].iloc[q], cal["p22"].iloc[q]]]))
                for q in range(1, len(cal))}
    kf = kalman_informacion(b["y"][t0:], b["x"][t0:], col["alfa"][jj], col["c"][jj], col["phi"][jj],
                            col["qm"][jj], col["qb"][jj], col["r"][jj],
                            np.array([f0["m_fin"], f0["b_fin"]]),
                            np.array([[f0["p11"], f0["p12"]], [f0["p12"], f0["p22"]]]),
                            reinicio=rein, estatico=not cfg.beta_dinamico)
    sl = slice(t0, n)
    s = kf["m"]
    with np.errstate(invalid="ignore", divide="ignore"):
        z = np.round((s - col["mu"][jj]) / col["sigma_eq"][jj], DEC)
    out["s"][sl], out["z"][sl], out["b_pr"][sl], out["b_post"][sl] = s, z, kf["b_pr"], kf["b"]
    out["puerta"][sl] = col["puerta"][jj].astype(bool)
    out["z_in"][sl], out["z_out"][sl] = col["z_in"][jj], col["z_out"][jj]
    vm_b = np.full(n, np.nan)
    vm_b[sl] = col["vida_media_h"][jj] / (cfg.barra_min / 60.0)
    zz, pu, zin, zout = out["z"], out["puerta"], out["z_in"], out["z_out"]
    py = b["c_y"] + b["g_y"]
    px = b["c_x"] + b["g_x"]
    nx_arr = np.array([contratos_x(out["b_post"][t], py[t], px[t], cfg) if t >= t0 else 0
                       for t in range(n)])
    with np.errstate(invalid="ignore"):
        valido = np.isfinite(zz) & np.isfinite(zin)
        ent_ok = pu & valido & (np.abs(zz) >= zin) & (nx_arr >= 1)
    ent_ok[n - 1] = False
    ent_ok[:t0] = False
    my, mx, ny = cfg.mult_y, cfg.mult_x, cfg.contratos_y
    trades = []
    t = t0
    cool = -1
    while True:
        cand = np.flatnonzero(ent_ok[max(t, cool):]) + max(t, cool)
        if cand.size == 0:
            break
        te = int(cand[0])
        d = -1 if zz[te] >= zin[te] else 1
        nx = int(nx_arr[te])
        z_o, vmb = float(zout[te]), float(vm_b[te])
        # la primera barra en que se cumple alguna condición de salida (desde te+1)
        seg = slice(te + 1, n)
        zs = zz[seg]
        with np.errstate(invalid="ignore"):
            c_obj = (zs >= -z_o) if d > 0 else (zs <= z_o)
            c_stp = (zs <= -cfg.z_stop) if d > 0 else (zs >= cfg.z_stop)
        tenencia = np.arange(1, n - te)                         # barras en posición
        c_tmp = tenencia >= cfg.stop_tiempo_vidas * vmb if np.isfinite(vmb) else np.zeros(n - te - 1, bool)
        c_rup = ~pu[seg] if cfg.salir_si_rompe else np.zeros(n - te - 1, bool)
        cualq = c_obj | c_stp | c_tmp | c_rup
        k = np.flatnonzero(cualq)
        if k.size:
            t2 = te + 1 + int(k[0])
            i2 = int(k[0])
            motivo = ("objetivo" if c_obj[i2] else "stop_z" if c_stp[i2] else
                      "stop_tiempo" if c_tmp[i2] else "ruptura")
        else:
            t2, motivo = n - 1, "fin"
        ent = te + 1
        sal = t2 + 1 if t2 <= n - 2 else None                   # barra de ejecución de la salida
        pye, pxe = float(b["o_y"][ent]), float(b["o_x"][ent])
        if sal is not None:
            pys, pxs = float(b["o_y"][sal]), float(b["o_x"][sal])
        else:
            pys, pxs = float(b["c_y"][n - 1]), float(b["c_x"][n - 1])
        # P&L por barra (marcado al cierre) y de la última pierna hasta la ejecución
        fin_marca = t2 if sal is not None else n - 1
        cy = b["c_y"][ent:fin_marca + 1]
        cx = b["c_x"][ent:fin_marca + 1]
        ref_y = np.r_[pye, cy[:-1]]
        ref_x = np.r_[pxe, cx[:-1]]
        out["pnl"][ent:fin_marca + 1] += d * (ny * my * (cy - ref_y) - nx * mx * (cx - ref_x))
        if sal is not None:
            out["pnl"][sal] += d * (ny * my * (pys - cy[-1]) - nx * mx * (pxs - cx[-1]))
        no_real = d * (ny * my * (cy - pye) - nx * mx * (cx - pxe))
        costo_lado = costos_unidad(nx, cfg)
        out["costos"][ent] += costo_lado
        rr = np.flatnonzero(b["roll_y"][ent + 1:fin_marca + 1] | b["roll_x"][ent + 1:fin_marca + 1]) + ent + 1
        c_roll = 0.0
        for tr_ in rr:
            cr = _costo_roll(ny, nx, bool(b["roll_y"][tr_]), bool(b["roll_x"][tr_]), cfg)
            out["costos"][tr_] += cr
            c_roll += cr
        out["costos"][sal if sal is not None else n - 1] += costo_lado
        out["pos"][ent:(sal if sal is not None else n)] = d
        bruto = d * (ny * my * (pys - pye) - nx * mx * (pxs - pxe))
        costos = 2 * costo_lado + c_roll
        trades.append({"dir": d, "t_dec": te, "t_ent": ent, "t_dec_sal": t2,
                       "t_sal": sal if sal is not None else n - 1, "ts_ent": int(b["ts"][ent]),
                       "ts_sal": int(b["ts"][sal if sal is not None else n - 1]), "ny": ny, "nx": nx,
                       "z_ent": float(zz[te]), "z_sal": float(zz[t2]),
                       "beta_ent": float(out["b_post"][te]), "py_ent": pye, "px_ent": pxe,
                       "py_sal": pys, "px_sal": pxs, "bruto": bruto, "costos": costos,
                       "neto": bruto - costos, "barras": (sal if sal is not None else n) - ent,
                       "motivo": motivo, "vm_ent": vmb * cfg.barra_min / 60.0,
                       "z_in": float(zin[te]), "z_out": z_o,
                       "mae": float(min(0.0, no_real.min())), "mfe": float(max(0.0, no_real.max())),
                       "rolls": int(rr.size)})
        if sal is None:
            break
        if motivo == "objetivo":
            t, cool = t2, cool
        else:
            t, cool = t2, t2 + cfg.enfriamiento_barras
    out["equity"] = np.cumsum(out["pnl"] - out["costos"])
    out["trades"] = pd.DataFrame(trades, columns=COLS_TRADES)
    return out


# =============================================================================
# 9. MOTOR EN VIVO (barra a barra: Databento Live o repetición)
# =============================================================================
class MotorPar:
    """El mismo sistema, una barra cada vez, con el filtro en forma de covarianzas.

    Si recibe el calendario ya calculado lo usa; si no (en vivo), guarda las últimas F barras y
    llama a `calibrar_ventana` en las mismas barras que el histórico: las filas salen idénticas.
    Las pruebas exigen las mismas filas, z, posiciones, operaciones y P&L que `correr_lote`."""

    def __init__(self, cfg: Config, cal: pd.DataFrame | None = None, al_evento=None):
        self.cfg = cfg
        self.cal_fijo = cal
        self.filas: list = []
        self.al_evento = al_evento
        self.t = -1
        self.buf: deque = deque(maxlen=cfg.formacion_barras)
        self.kf: KalmanOU | None = None
        self.fila = None
        self.fila_pendiente = None
        self.orden = None                   # ("cerrar", motivo) | ("abrir", plan) | ("ambas", motivo, plan)
        self.pos = None                     # dict de la posición abierta
        self.cool = -1
        self.trades: list = []
        self.hist = {k: [] for k in ("z", "s", "b_pr", "b_post", "puerta", "z_in", "z_out", "pos",
                                      "pnl", "costos")}
        self.ultima = None

    # -- utilidades ----------------------------------------------------------------------------
    def _emitir(self, tipo: str, **kw) -> None:
        if self.al_evento is not None:
            self.al_evento({"tipo": tipo, "t": self.t, **kw})

    def _aplicar_fila(self, f: dict) -> None:
        if self.kf is None or not self.cfg.beta_dinamico:
            self.kf = KalmanOU(f["m_fin"], f["b_fin"], [[f["p11"], f["p12"]], [f["p12"], f["p22"]]],
                               f["phi"], f["qm"], f["qb"], f["r"], f["alfa"], f["c"])
        else:
            if f["alfa"] != self.kf.alfa or f["c"] != self.kf.c:
                self.kf.recentrar(f["alfa"], f["c"])
            self.kf.cambiar(f["phi"], f["qm"], f["qb"], f["r"])
        self.fila = f

    def _cerrar(self, py: float, px: float, motivo: str, t_sal: int, ref_y: float, ref_x: float) -> float:
        p = self.pos
        cfg = self.cfg
        pnl = p["dir"] * (p["ny"] * cfg.mult_y * (py - ref_y) - p["nx"] * cfg.mult_x * (px - ref_x))
        costo = costos_unidad(p["nx"], cfg)
        bruto = p["dir"] * (p["ny"] * cfg.mult_y * (py - p["py_ent"]) - p["nx"] * cfg.mult_x * (px - p["px_ent"]))
        tr = {"dir": p["dir"], "t_dec": p["t_dec"], "t_ent": p["t_ent"], "t_dec_sal": p["t_dec_sal"],
              "t_sal": t_sal, "ts_ent": p["ts_ent"], "ts_sal": self.ultima["ts"] if t_sal == self.t else 0,
              "ny": p["ny"], "nx": p["nx"], "z_ent": p["z_ent"], "z_sal": p["z_sal"],
              "beta_ent": p["beta_ent"], "py_ent": p["py_ent"], "px_ent": p["px_ent"],
              "py_sal": py, "px_sal": px, "bruto": bruto, "costos": p["c_roll"] + 2 * costo,
              "neto": bruto - p["c_roll"] - 2 * costo, "barras": p["barras"], "motivo": motivo,
              "vm_ent": p["vm_ent"], "z_in": p["z_in"], "z_out": p["z_out"],
              "mae": p["mae"], "mfe": p["mfe"], "rolls": p["rolls"]}
        self.trades.append(tr)
        self._emitir("salida", trade=tr)
        self.pos = None
        return pnl, costo

    # -- el paso -----------------------------------------------------------------------------------
    def procesar(self, br: dict) -> None:
        """br: ts, o_y, c_y, o_x, c_x (ajustados), g_y, g_x, roll_y, roll_x, y, x."""
        cfg = self.cfg
        self.t += 1
        t = self.t
        self.ultima = br
        my, mx = cfg.mult_y, cfg.mult_x
        pnl = 0.0
        costos = 0.0
        # 1) ejecutar lo decidido al cierre anterior, a la apertura de esta barra
        if self.orden is not None:
            tipo = self.orden[0]
            if tipo in ("cerrar", "ambas") and self.pos is not None:
                p_, c_ = self._cerrar(br["o_y"], br["o_x"], self.orden[1], t, self.pos["ref_y"],
                                      self.pos["ref_x"])
                pnl += p_
                costos += c_
            if tipo in ("abrir", "ambas"):
                plan = self.orden[-1]
                self.pos = {**plan, "t_ent": t, "ts_ent": br["ts"], "py_ent": br["o_y"],
                            "px_ent": br["o_x"], "ref_y": br["o_y"], "ref_x": br["o_x"],
                            "c_roll": 0.0, "rolls": 0, "mae": 0.0, "mfe": 0.0, "barras": 0}
                costos += costos_unidad(plan["nx"], cfg)
                self._emitir("entrada", plan=self.pos)
            self.orden = None
        # 2) rolls con la posición abierta desde antes de esta barra
        if self.pos is not None and self.pos["t_ent"] < t and (br["roll_y"] or br["roll_x"]):
            cr = _costo_roll(self.pos["ny"], self.pos["nx"], bool(br["roll_y"]), bool(br["roll_x"]), cfg)
            self.pos["c_roll"] += cr
            self.pos["rolls"] += 1
            costos += cr
        # 3) marcar al cierre
        if self.pos is not None:
            p = self.pos
            pnl += p["dir"] * (p["ny"] * my * (br["c_y"] - p["ref_y"]) - p["nx"] * mx * (br["c_x"] - p["ref_x"]))
            p["ref_y"], p["ref_x"] = br["c_y"], br["c_x"]
            nr = p["dir"] * (p["ny"] * my * (br["c_y"] - p["py_ent"]) - p["nx"] * mx * (br["c_x"] - p["px_ent"]))
            p["mae"], p["mfe"] = min(p["mae"], nr), max(p["mfe"], nr)
            p["barras"] += 1
        # 4) la fila que rige desde esta barra
        if self.fila_pendiente is not None:
            self._aplicar_fila(self.fila_pendiente)
            self.fila_pendiente = None
        # 5) filtro y z
        z = s = b_pr = b_post = np.nan
        f = self.fila
        if self.kf is not None:
            _, b_pr, _, _ = self.kf.paso(br["y"], br["x"])
            b_post = self.kf.b
            s = self.kf.m
            with np.errstate(invalid="ignore", divide="ignore"):
                z = (float(np.round((s - f["mu"]) / f["sigma_eq"], DEC))
                     if f["sigma_eq"] and np.isfinite(f["sigma_eq"]) else np.nan)
        # 6) decisiones para la apertura siguiente
        if f is not None and self.pos is not None and np.isfinite(z):
            p = self.pos
            motivo = None
            if (p["dir"] > 0 and z >= -p["z_out"]) or (p["dir"] < 0 and z <= p["z_out"]):
                motivo = "objetivo"
            elif (p["dir"] > 0 and z <= -cfg.z_stop) or (p["dir"] < 0 and z >= cfg.z_stop):
                motivo = "stop_z"
            elif np.isfinite(p["vm_b"]) and p["barras"] >= cfg.stop_tiempo_vidas * p["vm_b"]:
                motivo = "stop_tiempo"
            elif cfg.salir_si_rompe and not f["puerta"]:
                motivo = "ruptura"
            if motivo is not None:
                p["z_sal"], p["t_dec_sal"] = z, t
                self.orden = ("cerrar", motivo)
                if motivo != "objetivo":
                    self.cool = t + cfg.enfriamiento_barras
        elif f is not None and self.pos is not None:
            # z indefinido: solo pueden actuar el stop de tiempo y la ruptura
            p = self.pos
            motivo = None
            if np.isfinite(p["vm_b"]) and p["barras"] >= cfg.stop_tiempo_vidas * p["vm_b"]:
                motivo = "stop_tiempo"
            elif cfg.salir_si_rompe and not f["puerta"]:
                motivo = "ruptura"
            if motivo is not None:
                p["z_sal"], p["t_dec_sal"] = z, t
                self.orden = ("cerrar", motivo)
                self.cool = t + cfg.enfriamiento_barras
        plano = self.pos is None or (self.orden is not None and self.orden[0] == "cerrar")
        if f is not None and plano and f["puerta"] and t >= self.cool and np.isfinite(z) \
                and np.isfinite(f["z_in"]) and abs(z) >= f["z_in"]:
            py = br["c_y"] + br["g_y"]
            px = br["c_x"] + br["g_x"]
            nx = contratos_x(b_post, py, px, cfg)
            if nx >= 1:
                plan = {"dir": -1 if z >= f["z_in"] else 1, "t_dec": t, "ny": cfg.contratos_y,
                        "nx": nx, "z_ent": z, "beta_ent": b_post, "z_in": f["z_in"],
                        "z_out": f["z_out"], "vm_ent": f["vida_media_h"],
                        "vm_b": f["vida_media_h"] / (cfg.barra_min / 60.0), "z_sal": np.nan,
                        "t_dec_sal": -1}
                self.orden = ("ambas", self.orden[1], plan) if self.orden is not None else ("abrir", plan)
        # 7) historia de la barra
        pos_barra = self.pos["dir"] if self.pos is not None else 0
        for k, v in (("z", z), ("s", s), ("b_pr", b_pr), ("b_post", b_post),
                     ("puerta", bool(f["puerta"]) if f is not None else False),
                     ("z_in", f["z_in"] if f is not None else np.nan),
                     ("z_out", f["z_out"] if f is not None else np.nan), ("pos", pos_barra),
                     ("pnl", pnl), ("costos", costos)):
            self.hist[k].append(v)
        # 8) calibración al cierre de esta barra (rige desde la siguiente)
        self.buf.append((br["y"], br["x"], br["c_y"] + br["g_y"], br["c_x"] + br["g_x"], br["ts"]))
        F, D = cfg.formacion_barras, cfg.reestimar_cada
        if t >= F - 1 and (t - (F - 1)) % D == 0:
            if self.cal_fijo is not None:
                sel = self.cal_fijo[self.cal_fijo["k"] == t]
                nueva = sel.iloc[0].to_dict() if len(sel) else None
            else:
                a = np.array([(u[0], u[1]) for u in self.buf])
                nueva = calibrar_ventana(a[:, 0], a[:, 1], cfg, self.buf[-1][2], self.buf[-1][3])
                nueva["puerta"], nueva["motivo"] = decidir_puerta(
                    nueva, bool(self.filas[-1]["puerta"]) if self.filas else False, cfg)
                nueva.update(k=t, ts=int(br["ts"]), rige=-1)
            if nueva is not None:
                self.filas.append(nueva)
                self.fila_pendiente = nueva
                self._emitir("calibracion", fila=nueva)

    def terminar(self) -> None:
        """Fin de los datos: lo abierto se cierra al último cierre (con su motivo si ya había
        decidido salir); una entrada pendiente se descarta."""
        if self.pos is not None:
            motivo = self.orden[1] if self.orden is not None and self.orden[0] in ("cerrar", "ambas") else "fin"
            if motivo == "fin":
                self.pos["z_sal"], self.pos["t_dec_sal"] = self.hist["z"][-1], self.t
            br = self.ultima
            _, c_ = self._cerrar(br["c_y"], br["c_x"], motivo, self.t, br["c_y"], br["c_x"])
            self.hist["costos"][-1] += c_
        self.orden = None

    def resultado(self) -> dict:
        h = {k: np.array(v) for k, v in self.hist.items()}
        h["pos"] = h["pos"].astype(np.int64)
        h["puerta"] = h["puerta"].astype(bool)
        h["equity"] = np.cumsum(h["pnl"] - h["costos"])
        h["trades"] = pd.DataFrame(self.trades, columns=COLS_TRADES)
        return h


def barra_de(b: dict, t: int) -> dict:
    return {k: b[k][t] for k in ("ts", "o_y", "c_y", "o_x", "c_x", "g_y", "g_x", "roll_y", "roll_x",
                                 "y", "x")}


def correr_incremental(b: dict, cfg: Config, cal: pd.DataFrame | None = None) -> dict:
    m = MotorPar(cfg, cal)
    for t in range(len(b["ts"])):
        m.procesar(barra_de(b, t))
    m.terminar()
    out = m.resultado()
    out["calendario"] = pd.DataFrame(m.filas)
    out["fila"] = _en_vigor(out["calendario"] if cal is None else cal, len(b["ts"]))
    return out


# =============================================================================
# 10. MERCADO SINTÉTICO CON LA VERDAD CONOCIDA
# =============================================================================
def mercado_par(cfg: Config = CFG, semilla: int = 7, cointegrado: bool = True,
                sesiones: int | None = None, ruptura: tuple | None = None) -> tuple:
    """Dos futuros tipo ES y NQ en barras de 1 h con sesiones de CME, y la verdad de todo.

      log X   paseo aleatorio con volatilidad en U por hora de la sesión y saltos al abrir
      β_t     paseo aleatorio lento alrededor de `sint_beta` (el hedge ratio VERDADERO se mueve)
      m_t     Ornstein-Uhlenbeck con vida media `sint_vida_media_h` y desviación estacionaria
              `sint_sd_spread` — salvo en la `ruptura`, donde es un paseo aleatorio (la
              cointegración se pierde y el spread se va)
      w_t     un paseo aleatorio chico (cointegración PARCIAL: ningún par real es perfecto)
      log Y = y₀ + β_t·(log X − x₀) + m_t + w_t
    Con `cointegrado=False`, m_t es un paseo aleatorio siempre (dos series que se parecen y
    NO están cointegradas: lo que tu script no distingue).
    Contratos: dos rolls en el período (en el segundo, NQ rola una sesión después que ES); el
    contrato siguiente cotiza con prima de acarreo, y también se generan las series .n.1."""
    rng = np.random.default_rng(semilla)
    S = int(sesiones or cfg.sint_sesiones)
    ts = inicios_barras(cfg.sint_inicio, S, 60)
    n = ts.size
    sub = 12                                               # pasos de 5 minutos por barra
    N = n * sub
    hora = np.tile(np.arange(23), S)                       # 0 = barra de las 17:00 CT
    perfil = np.where(hora < 9, 0.55, np.where(hora < 15, 0.85, 1.45))
    perfil = perfil / np.sqrt(np.mean(perfil ** 2))
    vol_sub = np.repeat(cfg.sint_vol_x_h * perfil, sub) / math.sqrt(sub)
    dx = rng.standard_normal(N) * vol_sub
    abre = np.zeros(N, bool)
    abre[::23 * sub] = True                                # primer paso de cada sesión
    dx[abre] += rng.normal(0.0, 2.5 * cfg.sint_vol_x_h, abre.sum())
    lx = math.log(cfg.sint_precio_x) + np.cumsum(dx)
    beta = np.empty(N)
    b_ = cfg.sint_beta
    db_ = rng.standard_normal(N) * cfg.sint_sd_beta / math.sqrt(sub)
    for k in range(N):                                     # paseo reflejado en [0.55, 1.05]
        b_ += db_[k]
        b_ = 1.10 - b_ if b_ > 1.05 else (1.10 - b_ if b_ < 0.55 else b_)
        beta[k] = b_
    theta = math.log(2.0) / cfg.sint_vida_media_h
    phi_s = math.exp(-theta / sub)
    sd_s = cfg.sint_sd_spread * math.sqrt(1.0 - phi_s * phi_s)
    r0, r1 = ruptura if ruptura is not None else cfg.sint_ruptura
    ses = np.repeat(np.arange(S), 23 * sub)
    en_rup = (ses >= int(r0 * S)) & (ses < int(r1 * S)) if cointegrado else np.ones(N, bool)
    e = rng.standard_normal(N)
    m = np.empty(N)
    mk = 0.0
    for k in range(N):
        mk = (mk + 1.5 * sd_s * e[k]) if en_rup[k] else (phi_s * mk + sd_s * e[k])
        m[k] = mk
    w = np.cumsum(rng.standard_normal(N)) * cfg.sint_sd_paseo / math.sqrt(sub)
    ly = math.log(cfg.sint_precio_y) + beta * (lx - lx[0]) + m + w
    # barras OHLC de cada pierna, a partir de los pasos de 5 minutos
    def ohlc(lp):
        P = np.exp(lp).reshape(n, sub)
        return P[:, 0], P.max(1), P.min(1), P[:, -1]
    Yo, Yh, Yl, Yc = ohlc(ly)
    Xo, Xh, Xl, Xc = ohlc(lx)
    # contratos y rolls: el siguiente cotiza con prima g (acarreo de un trimestre)
    g_y, g_x = 0.0060, 0.0080
    rolls_y = [int(0.15 * S), int(0.64 * S)]
    rolls_x = [int(0.15 * S), int(0.64 * S) + 1]
    ses_b = np.repeat(np.arange(S), 23)

    def pierna(o, h, l, c, rolls, g, base_id, tick):
        nro = np.searchsorted(np.array(rolls), ses_b, side="right")      # rolls ya hechos
        m0 = (1.0 + g) ** nro
        m1 = (1.0 + g) ** (nro + 1)
        rd = lambda v: np.round(v / tick) * tick  # noqa: E731
        vol = rng.integers(2000, 40000, n)
        b0 = {"ts": ts.copy(), "o": rd(o * m0), "h": rd(h * m0), "l": rd(l * m0), "c": rd(c * m0),
              "v": vol, "iid": base_id + nro}
        b1 = {"ts": ts.copy(), "o": rd(o * m1), "h": rd(h * m1), "l": rd(l * m1), "c": rd(c * m1),
              "v": vol // 10, "iid": base_id + nro + 1}
        return b0, b1
    y0, y1 = pierna(Yo, Yh, Yl, Yc, rolls_y, g_y, 5001, cfg.tick_y)
    x0, x1 = pierna(Xo, Xh, Xl, Xc, rolls_x, g_x, 6001, cfg.tick_x)
    fin = np.arange(sub - 1, N, sub)                       # el cierre de cada barra
    verdad = {"beta": beta[fin], "m": m[fin], "w": w[fin], "ruptura": en_rup[fin],
              "vida_media_h": cfg.sint_vida_media_h if cointegrado else np.inf,
              "sd_spread": cfg.sint_sd_spread, "cointegrado": cointegrado,
              "rolls_y": [int(ts[s * 23]) for s in rolls_y], "rolls_x": [int(ts[s * 23]) for s in rolls_x],
              "sesiones": S}
    return y0, x0, y1, x1, verdad


# =============================================================================
# 11. AUDITORÍA DE DESEMPEÑO
# =============================================================================
# Todo en DÓLARES, con contratos enteros y costos, sobre las barras de evaluación (las que
# vienen después de la historia de formación). El P&L diario es el de cada sesión de CME.
def _bootstrap_estacionario(r: np.ndarray, B: int, bloque: float, semilla: int) -> np.ndarray:
    """Índices del bootstrap estacionario de Politis y Romano (1994): bloques de largo
    geométrico con media `bloque`, circulares. Conserva la dependencia de días seguidos."""
    n = r.size
    rng = np.random.default_rng(semilla)
    idx = np.empty((B, n), np.int64)
    p = 1.0 / max(bloque, 1.0)
    idx[:, 0] = rng.integers(0, n, B)
    nuevo = rng.random((B, n)) < p
    salto = rng.integers(0, n, (B, n))
    for t in range(1, n):
        idx[:, t] = np.where(nuevo[:, t], salto[:, t], (idx[:, t - 1] + 1) % n)
    return idx


def sharpe_probabilistico(r: np.ndarray, sr0: float = 0.0) -> float:
    """PSR de Bailey y López de Prado (2012): probabilidad de que el Sharpe VERDADERO supere
    sr0, con la asimetría y la curtosis de los rendimientos (Sharpe por periodo, sin anualizar):
        PSR = Φ( (SR − SR₀)·√(n−1) / √(1 − γ₃·SR + (γ₄ − 1)/4·SR²) )"""
    r = np.asarray(r, float)
    r = r[np.isfinite(r)]
    n = r.size
    sd = r.std(ddof=1) if n > 2 else 0.0
    if n < 10 or sd <= 0:
        return np.nan
    sr = r.mean() / sd
    z = (r - r.mean()) / r.std(ddof=0)
    g3 = float(np.mean(z ** 3))
    g4 = float(np.mean(z ** 4))
    den = 1.0 - g3 * sr + (g4 - 1.0) / 4.0 * sr * sr
    if den <= 0:
        return np.nan
    return float(ndtr((sr - sr0) * math.sqrt(n - 1) / math.sqrt(den)))


def sharpe_deflactado(r: np.ndarray, srs_pruebas) -> dict:
    """DSR de Bailey y López de Prado (2014): el PSR contra el MEJOR Sharpe que se esperaría
    por azar al probar N configuraciones con varianza V entre sus Sharpes:
        SR₀ = √V·((1 − γ)·Φ⁻¹(1 − 1/N) + γ·Φ⁻¹(1 − 1/(N·e))),  γ = 0.5772 (Euler-Mascheroni)"""
    from scipy.stats import norm
    s = np.asarray([x for x in srs_pruebas if np.isfinite(x)], float)
    N = s.size
    if N < 2:
        return {"dsr": np.nan, "sr0": np.nan, "N": N}
    g = 0.5772156649
    sr0 = math.sqrt(float(np.var(s, ddof=1))) * ((1 - g) * norm.ppf(1 - 1.0 / N) + g * norm.ppf(1 - 1.0 / (N * math.e)))
    return {"dsr": sharpe_probabilistico(r, sr0), "sr0": sr0, "N": N}


def pnl_diario(res: dict, b: dict, ini: int) -> pd.Series:
    """P&L neto por sesión de CME (incluye los días sin operar, en cero)."""
    neto = (res["pnl"] - res["costos"])[ini:]
    ses = b["sesion"][ini:]
    if neto.size == 0:
        return pd.Series(dtype=float)
    return pd.Series(neto).groupby(ses).sum()


def auditar(res: dict, b: dict, cfg: Config, ini: int = 0, srs_pruebas=None) -> dict:
    tr = res["trades"]
    tr = tr[tr["t_ent"] >= ini] if len(tr) else tr
    d = pnl_diario(res, b, ini)
    out = {"trades": int(len(tr)), "dias": int(d.size)}
    if d.size:
        eq = np.cumsum(d.to_numpy())
        pico = np.maximum.accumulate(np.r_[0.0, eq])[1:]
        caida = float(np.max(pico - eq)) if eq.size else 0.0
        sd = float(d.std(ddof=1)) if d.size > 1 else np.nan
        neg = d[d < 0]
        sd_neg = float(np.sqrt(np.mean(np.minimum(d.to_numpy(), 0.0) ** 2))) if d.size else np.nan
        anual = float(d.mean() * 252)
        out.update({"neto_usd": float(d.sum()), "media_dia": float(d.mean()),
                    "sharpe": float(d.mean() / sd * math.sqrt(252)) if sd and sd > 0 else np.nan,
                    "sortino": float(d.mean() / sd_neg * math.sqrt(252)) if sd_neg and sd_neg > 0 else np.nan,
                    "max_caida_usd": caida, "max_caida_pct": 100 * caida / cfg.capital_usd,
                    "retorno_anual_pct": 100 * anual / cfg.capital_usd,
                    "calmar": (anual / caida) if caida > 0 else np.nan,
                    "dias_positivos": float((d > 0).mean()), "peor_dia": float(d.min()),
                    "mejor_dia": float(d.max()), "n_dias_negativos": int(neg.size)})
        # El bloque medio tiene que cubrir la dependencia: una operación de varios días deja
        # días seguidos con P&L del mismo signo. Con bloques más cortos que las operaciones el
        # intervalo sale angosto de más (con 7 operaciones largas sale "significativo" un azar).
        bloque = float(cfg.bloque_dias)
        if len(tr):
            bloque = max(bloque, 2.0 * float(np.median(tr["barras"])) * cfg.barra_min / 60.0 / 23.0)
        out["bloque_dias"] = bloque
        if d.size >= 20:
            idx = _bootstrap_estacionario(d.to_numpy(), cfg.bootstrap, bloque, cfg.semilla)
            m = d.to_numpy()[idx]
            med = m.mean(1)
            sdb = m.std(1, ddof=1)
            okb = sdb > 0
            out["ic_media_dia"] = tuple(float(v) for v in np.quantile(med, [0.05, 0.95]))
            # con muy pocas operaciones, muchas réplicas salen sin un solo día distinto de cero y
            # su Sharpe no existe: el intervalo solo se da si casi todas lo tienen
            if okb.mean() >= 0.9:
                shb = med[okb] / sdb[okb] * math.sqrt(252)
                out["ic_sharpe"] = tuple(float(v) for v in np.quantile(shb, [0.05, 0.95]))
            else:
                out["ic_sharpe"] = (np.nan, np.nan)
            out["prob_media_pos"] = float(np.mean(med > 0))
        out["psr"] = sharpe_probabilistico(d.to_numpy())
        if srs_pruebas is not None:
            out.update({f"dsr_{k}" if k != "dsr" else "dsr": v
                        for k, v in sharpe_deflactado(d.to_numpy(), srs_pruebas).items()})
    pos = res["pos"][ini:]
    out["tiempo_en_mercado"] = float(np.mean(pos != 0)) if pos.size else 0.0
    if len(tr):
        g = tr["neto"]
        gan, per = g[g > 0], g[g <= 0]
        horas = tr["barras"] * cfg.barra_min / 60.0
        out.update({"bruto_usd": float(tr["bruto"].sum()), "costos_usd": float(tr["costos"].sum()),
                    "acierto": float((g > 0).mean()), "gan_media": float(gan.mean()) if gan.size else np.nan,
                    "per_media": float(per.mean()) if per.size else np.nan,
                    "payoff": float(gan.mean() / -per.mean()) if gan.size and per.size and per.mean() < 0 else np.nan,
                    "factor_beneficio": float(gan.sum() / -per.sum()) if per.size and per.sum() < 0 else np.nan,
                    "esperanza": float(g.mean()), "horas_media": float(horas.mean()),
                    "horas_sobre_vm": float(np.nanmedian(horas / tr["vm_ent"])) if tr["vm_ent"].notna().any() else np.nan,
                    "mae_media": float(tr["mae"].mean()), "mfe_media": float(tr["mfe"].mean()),
                    "costo_equilibrio_x": float(tr["bruto"].sum() / tr["costos"].sum())
                    if tr["costos"].sum() > 0 else np.nan,
                    "rolls": int(tr["rolls"].sum())})
        pm = tr.groupby("motivo")["neto"].agg(["size", "sum", "mean"])
        out["por_motivo"] = pm
        out["por_lado"] = tr.groupby("dir")["neto"].agg(["size", "sum", "mean"])
    out["diario"] = d
    return out




# =============================================================================
# 12. LAS PIEZAS DE LIVE DE LA v3: símbolos, lectura de OHLCV, Agregador de 1 min y UnirVivo (sin cambios;
#     en leer_ohlcv el aviso va al log en vez de a print)
# =============================================================================
ESQUEMAS = ("ohlcv-1h", "ohlcv-1m")
_CONTINUO = re.compile(r"^(.+)\.([cnv])\.(\d+)$")


def siguiente_contrato(symbol: str) -> str | None:
    """ES.n.0 → ES.n.1 (el contrato que entra en el próximo roll). None si no es un continuo."""
    m = _CONTINUO.match(symbol)
    return f"{m.group(1)}.{m.group(2)}.{int(m.group(3)) + 1}" if m else None


def simbolos_par(cfg: Config) -> dict:
    """Las series que hacen falta: y0, x0 (el par) y, para medir los rolls, y1, x1."""
    s = {"y0": cfg.symbol_y, "x0": cfg.symbol_x}
    if cfg.ajustar_rolls and cfg.stype_in == "continuous":
        for k, sym in (("y1", cfg.symbol_y), ("x1", cfg.symbol_x)):
            nxt = siguiente_contrato(sym)
            if nxt:
                s[k] = nxt
    return s
def leer_ohlcv(store) -> dict:
    """Barras OHLCV de un DBNStore (precios enteros × 1e-9, como vienen en el archivo; `to_df()`
    ya los da en puntos: dividirlos otra vez entre 1e9 es el error de tu script). ts = ts_event,
    el INICIO de la barra. Una barra por instante: si hubiera dos contratos, el de más volumen."""
    if store is None:
        return barras_vacias()
    try:
        partes = [np.asarray(a) for a in store.to_ndarray(count=500_000)]
    except ValueError:
        partes = []
    partes = [p for p in partes if len(p)]
    if not partes:
        return barras_vacias()
    a = np.concatenate(partes)
    b = {"ts": a["ts_event"].astype(np.int64),
         "o": a["open"].astype(np.float64) / 1e9, "h": a["high"].astype(np.float64) / 1e9,
         "l": a["low"].astype(np.float64) / 1e9, "c": a["close"].astype(np.float64) / 1e9,
         "v": a["volume"].astype(np.int64), "iid": a["instrument_id"].astype(np.int64)}
    orden = np.lexsort((-b["v"], b["ts"]))
    b = {k: v[orden] for k, v in b.items()}
    unico = np.r_[True, b["ts"][1:] != b["ts"][:-1]]
    if not unico.all():
        LOG.warning(f"{int((~unico).sum())} barras de un segundo contrato en la misma hora: se usa la de "
              "más volumen (usa un continuo como ES.n.0 para enlazar vencimientos).")
        b = {k: v[unico] for k, v in b.items()}
    return b


MIN_NS = 60 * NS


class Agregador:
    """Barras de 1 min de varias series → barras de `minutos`, registro a registro.

    Databento publica cada barra de 1 min al cerrar su minuto (ts_event = su inicio) y solo si
    hubo operaciones. La barra [k, k+paso) se cierra cuando el reloj pasa k + paso + 1 min:
    para entonces ya llegaron las del último minuto de TODAS las series. El reloj avanza con
    cada barra (su fin) y con los heartbeats. Da lo mismo que `agregar_barras` (probado)."""

    def __init__(self, minutos: int, series):
        self.paso = int(minutos) * MIN_NS
        self.abiertas = {s: None for s in series}          # s → [k, o, h, l, c, v, iid]
        self.listas: dict = {}                             # k → {s: (o, h, l, c, v, iid)}
        self.reloj = 0
        self.limite = -1                                   # última k cerrada
        self.tarde = 0

    def agregar(self, s: str, ts: int, o: float, h: float, l: float, c: float, v: int,
                iid: int) -> list:
        ts = int(ts)
        k = ts - ts % self.paso
        a = self.abiertas.get(s)
        if k <= self.limite or (a is not None and k < a[0]):
            self.tarde += 1                                # llegó después de cerrar su barra
            return self.avanzar(ts + MIN_NS)
        if a is not None and k != a[0]:
            self.listas.setdefault(a[0], {})[s] = tuple(a[1:])
            a = None
        if a is None:
            self.abiertas[s] = [k, float(o), float(h), float(l), float(c), int(v), int(iid)]
        else:
            a[2] = max(a[2], float(h))
            a[3] = min(a[3], float(l))
            a[4] = float(c)
            a[5] += int(v)
            a[6] = int(iid)
        return self.avanzar(ts + MIN_NS)

    def avanzar(self, reloj: int) -> list:
        """Cierra lo que el reloj ya dejó atrás; devuelve [(k, {serie: barra}), …] en orden."""
        self.reloj = max(self.reloj, int(reloj))
        tope = self.reloj - MIN_NS - self.paso             # k ≤ tope ⇒ [k, k+paso) terminó
        if tope < 0 or tope - tope % self.paso <= self.limite:
            return []
        tope -= tope % self.paso
        for s, a in self.abiertas.items():
            if a is not None and a[0] <= tope:
                self.listas.setdefault(a[0], {})[s] = tuple(a[1:])
                self.abiertas[s] = None
        self.limite = tope
        listas = sorted(k for k in self.listas if k <= tope)
        return [(k, self.listas.pop(k)) for k in listas]

    def vaciar(self) -> list:
        """Fin de los datos (solo en repeticiones): cierra todo lo abierto."""
        for s, a in self.abiertas.items():
            if a is not None:
                self.listas.setdefault(a[0], {})[s] = tuple(a[1:])
                self.abiertas[s] = None
        out = [(k, self.listas.pop(k)) for k in sorted(self.listas)]
        if out:
            self.limite = max(self.limite, out[-1][0])
        return out


class UnirVivo:
    """`unir_par` de una hora cada vez: solo las horas con barra de las DOS piernas, el salto de
    cada roll medido con la .n.1 en la hora común anterior, el ajuste hacia adelante y la escala.
    Las pruebas exigen las mismas barras que `unir_par` sobre la historia."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.prev = None
        self.G = {"y": 0.0, "x": 0.0}
        self.ultimo_ts = None

    def barra(self, k: int, barras: dict) -> dict | None:
        if "y0" not in barras or "x0" not in barras:
            return None
        if self.ultimo_ts is not None and k <= self.ultimo_ts:
            return None
        cfg = self.cfg
        br = {"ts": int(k)}
        for pie in ("y", "x"):
            B = barras[pie + "0"]                           # (o, h, l, c, v, iid)
            roll = aprox = False
            if self.prev is not None and int(B[5]) != int(self.prev[pie + "0"][5]):
                roll = True
                B1 = self.prev.get(pie + "1")
                if cfg.ajustar_rolls and B1 is not None and int(B1[5]) == int(B[5]):
                    gap = float(B1[3]) - float(self.prev[pie + "0"][3])
                else:
                    gap = float(B[0]) - float(self.prev[pie + "0"][3])
                    aprox = True
                self.G[pie] += gap
            G = self.G[pie] if cfg.ajustar_rolls else 0.0
            for j, cmp in enumerate(("o", "h", "l", "c")):
                br[f"{cmp}_{pie}"] = float(B[j]) - G
            br[f"g_{pie}"] = G
            br[f"roll_{pie}"] = roll
            br[f"aprox_{pie}"] = aprox
            br[f"iid_{pie}"] = int(B[5])
            br[f"v_{pie}"] = int(B[4])
        br["sesion"] = int(fechas_sesion(np.array([k], np.int64))[0])
        if cfg.escala == "log":
            br["y"] = float(np.log(np.maximum(np.array([br["c_y"]]), 1e-9))[0])
            br["x"] = float(np.log(np.maximum(np.array([br["c_x"]]), 1e-9))[0])
        else:
            br["y"], br["x"] = br["c_y"], br["c_x"]
        self.prev = {"ts": int(k), **{s: barras.get(s) for s in ("y0", "x0", "y1", "x1")}}
        self.ultimo_ts = int(k)
        return br


def horas_de(crudas: dict) -> list:
    """Barras crudas por serie → [(k, {serie: (o, h, l, c, v, iid)}), …] en orden de tiempo."""
    por_k: dict = {}
    for s, v in crudas.items():
        if v is None:
            continue
        for j in range(len(v["ts"])):
            por_k.setdefault(int(v["ts"][j]), {})[s] = (float(v["o"][j]), float(v["h"][j]),
                                                        float(v["l"][j]), float(v["c"][j]),
                                                        int(v["v"][j]), int(v["iid"][j]))
    return sorted(por_k.items())



# =============================================================================
# 13. UTILIDADES COMUNES (las de los otros indicadores en vivo, ya probadas)
# =============================================================================
def _utc(t) -> pd.Timestamp:
    t = pd.Timestamp(t)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def mercado_abierto(t) -> bool:
    c = _utc(t).tz_convert(TZ_CME)
    h = c.hour + c.minute / 60
    d = c.weekday()
    if d == 5:
        return False
    if d == 6:
        return h >= 17
    if d == 4:
        return h < 16
    return not 16 <= h < 17


def decimales_de(tick: float) -> int:
    return max(0, -Decimal(repr(float(tick))).normalize().as_tuple().exponent)


def _r(x, d: int):
    return round(float(x), d) if x is not None and np.isfinite(x) else None


def _fin(x) -> bool:
    return x is not None and isinstance(x, (int, float, np.floating, np.integer)) and not isinstance(x, bool) and math.isfinite(x)


def _limpiar(x):
    """numpy y pandas → JSON."""
    if isinstance(x, dict):
        return {str(k): _limpiar(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_limpiar(v) for v in x]
    if isinstance(x, (np.bool_, bool)):
        return bool(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        return float(x) if math.isfinite(x) else None
    if isinstance(x, np.ndarray):
        return _limpiar(x.tolist())
    if isinstance(x, pd.Timestamp):
        return x.isoformat()
    return x


def _hora(t_ns: int, zona: str, formato: str = "%d-%m %H:%M") -> str:
    return pd.Timestamp(int(t_ns), tz="UTC").tz_convert(zona).strftime(formato)


def _pitido() -> None:
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except Exception:
        print("\a", end="", flush=True)


def raiz_de(simbolo: str) -> str:
    return re.split(r"[.\s]", simbolo)[0].upper()


def stype_de(simbolo: str) -> str:
    if re.search(r"\.[cnv]\.\d+$", simbolo):
        return "continuous"
    if simbolo.upper().endswith((".FUT", ".OPT", ".SPOT")):
        return "parent"
    return "raw_symbol"


# =============================================================================
# 14. TELEGRAM (el mismo notificador de los otros indicadores)
# =============================================================================
ARCHIVOS_TELEGRAM = ("telegram_credenciales.txt", "token_telegram.txt")


def credenciales_telegram() -> tuple[str, str] | None:
    """Token y chat_id: variables TELEGRAM_TOKEN / TELEGRAM_CHAT_ID o el archivo telegram_credenciales.txt (o
    token_telegram.txt) junto a este script (el mismo de los otros indicadores). Nunca dentro del código."""
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    for nombre in ARCHIVOS_TELEGRAM:
        ruta = CARPETA_SCRIPT / nombre
        if (not token or not chat) and ruta.exists():
            valores = dict(re.findall(r"^\s*(TELEGRAM_\w+)\s*=\s*[\"']?([^\"'\s]+)", ruta.read_text(encoding="utf-8-sig"), re.M))
            token = token or valores.get("TELEGRAM_TOKEN", "")
            chat = chat or valores.get("TELEGRAM_CHAT_ID", "")
    return (token, chat) if token and chat else None


class NotificadorTelegram:
    """Manda mensajes por la API de bots de Telegram desde un hilo propio (reintentos, límites de Telegram)."""

    URL = "https://api.telegram.org/bot{token}/{metodo}"
    AYUDA = {
        401: "El token no es válido (¿lo regeneraste en @BotFather?).",
        400: "Telegram no encuentra el chat: revisa TELEGRAM_CHAT_ID y que le hayas escrito /start a tu bot.",
        403: "El bot no puede escribirte: ábrelo en Telegram, presiona Iniciar (/start) y no lo bloquees.",
        404: "El token no es válido.",
    }

    def __init__(self, token: str, chat_id: str):
        self.token, self.chat_id = token, str(chat_id)
        self.enviados = 0
        self.ultimo_error = ""
        self._cola: queue.Queue = queue.Queue(maxsize=500)
        self._hilo = threading.Thread(target=self._trabajar, name="telegram", daemon=True)
        self._hilo.start()

    def _llamar(self, metodo: str, datos: dict | None = None, timeout: float = 15) -> dict:
        url = self.URL.format(token=self.token, metodo=metodo)
        req = urllib.request.Request(url, data=json.dumps(datos or {}).encode("utf-8"), headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read())
            except Exception:
                return {"ok": False, "error_code": e.code, "description": str(e)}
        except Exception as e:
            return {"ok": False, "error_code": 0, "description": f"{type(e).__name__}: {e}"}

    def verificar(self) -> tuple[bool, str]:
        r = self._llamar("getMe", timeout=10)
        if r.get("ok"):
            return True, "@" + r["result"].get("username", "?")
        return False, self.AYUDA.get(r.get("error_code"), r.get("description", "error desconocido"))

    def enviar(self, texto: str, guardar_en: dict | None = None, responder_a: dict | None = None, silencioso: bool = False) -> None:
        try:
            self._cola.put_nowait((texto, guardar_en, responder_a, silencioso))
        except queue.Full:
            LOG.warning("Telegram: la cola de mensajes está llena; se descarta uno.")

    def cerrar(self, espera: float = 6.0) -> None:
        try:
            self._cola.put_nowait(None)
        except queue.Full:
            pass
        self._hilo.join(espera)

    def _trabajar(self) -> None:
        while True:
            item = self._cola.get()
            if item is None:
                return
            texto, guardar_en, responder_a, silencioso = item
            datos = {"chat_id": self.chat_id, "text": texto, "parse_mode": "HTML", "disable_web_page_preview": True,
                     "disable_notification": silencioso}
            if responder_a and responder_a.get("tg_id"):
                datos["reply_parameters"] = {"message_id": responder_a["tg_id"], "allow_sending_without_reply": True}
            for intento in range(6):
                r = self._llamar("sendMessage", datos)
                if r.get("ok"):
                    self.enviados += 1
                    if guardar_en is not None:
                        guardar_en["tg_id"] = r["result"]["message_id"]
                    break
                codigo = r.get("error_code")
                self.ultimo_error = r.get("description", "")
                if codigo == 429:
                    time.sleep(min(60, (r.get("parameters") or {}).get("retry_after", 5)))
                    continue
                if codigo in self.AYUDA:
                    LOG.error(f"Telegram: {self.AYUDA[codigo]} ({self.ultimo_error})")
                    break
                time.sleep(min(30, 2 ** intento))
            else:
                LOG.error(f"Telegram: no se pudo enviar un mensaje ({self.ultimo_error}).")


def preparar_telegram() -> NotificadorTelegram | None:
    cred = credenciales_telegram()
    if cred is None:
        LOG.info(f"Telegram desactivado: no hay TELEGRAM_TOKEN / TELEGRAM_CHAT_ID ni {' / '.join(ARCHIVOS_TELEGRAM)}.")
        return None
    notificador = NotificadorTelegram(*cred)
    ok, info = notificador.verificar()
    if not ok:
        LOG.error(f"Telegram desactivado: {info}")
        notificador.cerrar(0)
        return None
    LOG.info(f"Telegram activo: las órdenes y la puerta llegan por el bot {info} (chat {cred[1]}).")
    return notificador


# =============================================================================
# 15. API KEY Y DESCARGAS (las de la v3 y los otros indicadores)
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
    texto = re.sub(r"\x1b\[[0-9;]*[~A-Za-z]", "", texto or "")
    texto = "".join(ch for ch in texto if ch.isprintable() and not ch.isspace())
    return texto.strip("\"'")


def _mascara(key: str) -> str:
    return f"{key[:5]}…{key[-3:]} ({len(key)} caracteres)" if len(key) > 8 else f"({len(key)} caracteres)"


def _exigir_api_key() -> None:
    guardada = _limpiar_key(os.environ.get("DATABENTO_API_KEY"))
    if guardada:
        os.environ["DATABENTO_API_KEY"] = guardada
        return
    if not _interactivo():
        sys.exit("Falta la variable de entorno DATABENTO_API_KEY (no pongas la key en el código).")
    import getpass
    for _ in range(3):
        try:
            key = _limpiar_key(getpass.getpass("Pega tu API key de Databento y presiona Enter: ", echo_char="*"))
        except TypeError:
            key = _limpiar_key(getpass.getpass("Pega tu API key de Databento y presiona Enter: "))
        if key.startswith("db-"):
            os.environ["DATABENTO_API_KEY"] = key
            print(f"Key recibida: {_mascara(key)}")
            return
        print(f"Eso no parece una API key de Databento (empiezan con 'db-'); llegó {_mascara(key)}.")
    sys.exit("No se recibió una API key válida.")


AYUDA_KEY = (
    "  • Si la regeneraste o la borraste, la anterior ya no sirve.\n"
    "  • Copia la key vigente en el portal de Databento, sección API keys.\n"
    '  • Guárdala una vez en PowerShell:  setx DATABENTO_API_KEY "db-..."  y cierra y abre VS Code.'
)


def conectar_historico():
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
            print(f"Databento rechazó la API key {_mascara(key)} (error {e.http_status}).")
            if venia_de_setx:
                print("   Esa key venía de la variable DATABENTO_API_KEY guardada en tu computadora: actualízala con setx.")
            if not _interactivo():
                break
            print("   Pega la key vigente para intentar de nuevo (Ctrl+C para salir).")
    sys.exit("No se pudo autenticar con Databento.\n" + AYUDA_KEY)


def _descargar(cliente, params: dict, ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(ruta.name + ".parcial")
    temporal.unlink(missing_ok=True)
    descarga = cliente.timeseries.get_range(**params, path=temporal)
    del descarga
    gc.collect()
    temporal.replace(ruta)


ERRORES_FATALES = {ErrorCode.AUTH_FAILED, ErrorCode.API_KEY_DEACTIVATED, ErrorCode.INVALID_SUBSCRIPTION,
                   ErrorCode.SYMBOL_RESOLUTION_FAILED}


def fin_historico(cliente, cfg: Config, esquema: str) -> pd.Timestamp:
    """Hasta dónde llega el histórico de ese esquema (el de la v3 miraba el del dataset entero)."""
    rango = cliente.metadata.get_dataset_range(dataset=cfg.dataset)
    if not isinstance(rango, dict):
        rango = {"end": getattr(rango, "end", None)}
    fin = (rango.get("schema") or {}).get(esquema, {}).get("end") or rango.get("end")
    return min(pd.Timestamp.now(tz="UTC"), _utc(fin)).floor("min")


def descargar_calentamiento(cliente, cfg: Config, ini: pd.Timestamp, fin: pd.Timestamp, avisar=lambda t: None) -> dict:
    """Las series del par entre `ini` y `fin` (obtener_par + cargar_par de la v3, sin caché: la ventana cambia en
    cada arranque y son unos centavos), con UN tope de costo para el total. Solo barras COMPLETAS antes de `fin`.
    Si falla una serie .n.1, sigue sin ella (el roll se mide con el salto entero)."""
    if cfg.esquema not in ESQUEMAS:
        sys.exit(f"esquema '{cfg.esquema}' no soportado: usa uno de {ESQUEMAS}")
    if cfg.esquema == "ohlcv-1h" and cfg.barra_min % 60:
        sys.exit("Con ohlcv-1h la barra tiene que ser múltiplo de 60 minutos (usa --esquema ohlcv-1m).")
    sims = simbolos_par(cfg)
    ini_s, fin_s = ini.strftime("%Y-%m-%dT%H:%M:%S"), fin.strftime("%Y-%m-%dT%H:%M:%S")
    costos = {}
    for k, s in sims.items():
        try:
            costos[k] = float(cliente.metadata.get_cost(dataset=cfg.dataset, symbols=s, stype_in=cfg.stype_in,
                                                        schema=cfg.esquema, start=ini_s, end=fin_s))
        except db.BentoClientError as e:
            if k in ("y0", "x0"):
                raise
            LOG.warning(f"{s}: {e} — se sigue sin esa serie.")
    total = sum(costos.values())
    LOG.info(f"Calentamiento: {cfg.esquema} de {', '.join(sims[k] for k in costos)} · {ini_s} … {fin_s} UTC · costo "
             f"estimado US$ {total:,.2f}")
    if total > cfg.costo_max_usd:
        sys.exit(f"El costo (US$ {total:,.2f}) supera tu tope de US$ {cfg.costo_max_usd:,.2f}: usa --costo-max "
                 f"{math.ceil(total) + 1} o baja --historia-dias.")
    carpeta = _ruta(cfg.cache_dir)
    crudas = {}
    for k in costos:
        s = sims[k]
        ruta = carpeta / (_nombre_seguro("calentamiento", str(os.getpid()), s, cfg.esquema) + ".dbn.zst")
        avisar(f"Descargando {cfg.esquema} de {s} ({(fin - ini).days} días)…")
        for intento in range(4):
            try:
                _descargar(cliente, dict(dataset=cfg.dataset, symbols=s, stype_in=cfg.stype_in, schema=cfg.esquema,
                                         start=ini_s, end=fin_s), ruta)
                break
            except db.BentoClientError as e:
                if k in ("y0", "x0"):
                    raise
                LOG.warning(f"{s}: {e} — se sigue sin esa serie.")
                ruta = None
                break
            except Exception as e:
                if intento == 3:
                    raise
                LOG.warning(f"Descarga de {s} fallida ({type(e).__name__}); reintento…")
                time.sleep(3 * (intento + 1))
        if ruta is None:
            continue
        store = db.DBNStore.from_file(ruta)
        crudas[k] = leer_ohlcv(store)
        del store
        gc.collect()
        try:
            ruta.unlink(missing_ok=True)
        except OSError:
            pass
    base = 60 if cfg.esquema == "ohlcv-1h" else 1
    if cfg.barra_min != base:
        crudas = {k: agregar_barras(v, cfg.barra_min) for k, v in crudas.items()}
    paso = cfg.barra_min * MIN_NS
    crudas = {k: {c: v[c][v["ts"] + paso <= fin.value] for c in v} for k, v in crudas.items()}
    for k, v in crudas.items():
        LOG.info(f"   {sims[k]}: {len(v['ts']):,} barras" + (f" · {len(np.unique(v['iid']))} contratos" if len(v["ts"]) else ""))
    return crudas


# =============================================================================
# 16. SERVIDOR DEL TABLERO (HTTP local + Server-Sent Events, el de los otros indicadores)
# =============================================================================
def _json(obj) -> bytes:
    return json.dumps(_limpiar(obj), separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


class _ServidorHTTP(ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = True


class ServidorTablero:
    def __init__(self, nucleo: "NucleoCoint", cfg: Config):
        self.nucleo, self.cfg = nucleo, cfg
        self.detenido = False
        self.httpd: ThreadingHTTPServer | None = None

    def iniciar(self) -> str:
        handler = self._handler()
        for puerto in range(self.cfg.puerto, self.cfg.puerto + 20):
            try:
                self.httpd = _ServidorHTTP((self.cfg.host, puerto), handler)
                break
            except OSError:
                continue
        else:
            raise OSError(f"No hay puertos libres entre {self.cfg.puerto} y {self.cfg.puerto + 19}.")
        if self.httpd.server_address[1] != self.cfg.puerto:
            LOG.warning(f"El puerto {self.cfg.puerto} está ocupado; uso el {self.httpd.server_address[1]}.")
        threading.Thread(target=self.httpd.serve_forever, name="tablero", daemon=True).start()
        return f"http://{self.cfg.host}:{self.httpd.server_address[1]}/"

    def detener(self) -> None:
        self.detenido = True
        if self.httpd:
            with self.nucleo.cambio:
                self.nucleo.cambio.notify_all()
            time.sleep(0.4)
            self.httpd.shutdown()
            self.httpd.server_close()

    def _handler(self):
        servidor, nucleo = self, self.nucleo

        class Handler(BaseHTTPRequestHandler):
            server_version = "CointLive/1.0"

            def log_message(self, formato, *args):
                LOG.debug("tablero: " + formato % args)

            def _enviar(self, codigo: int, cuerpo: bytes, tipo: str) -> None:
                self.send_response(codigo)
                self.send_header("Content-Type", tipo)
                self.send_header("Content-Length", str(len(cuerpo)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(cuerpo)

            def do_GET(self):
                ruta = self.path.split("?", 1)[0]
                try:
                    if ruta in ("/", "/index.html"):
                        self._enviar(200, TABLERO_HTML.encode("utf-8"), "text/html; charset=utf-8")
                    elif ruta == "/api/estado":
                        self._enviar(200, _json(nucleo.snapshot()), "application/json; charset=utf-8")
                    elif ruta == "/api/stream":
                        self._stream()
                    elif ruta == "/favicon.ico":
                        self._enviar(204, b"", "image/x-icon")
                    else:
                        self._enviar(404, "No encontrado".encode("utf-8"), "text/plain; charset=utf-8")
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass

            def _stream(self) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()
                cli = {"epoca": -1, "cursor": 0, "ver": -1}
                ult_tick = ult_envio = 0.0
                try:
                    while True:
                        with nucleo.cambio:
                            nucleo.cambio.wait(timeout=0.3)
                        ahora = time.monotonic()
                        partes = nucleo.paquete(cli, con_tick=ahora - ult_tick >= 0.5)
                        if partes:
                            ult_tick = ahora
                            datos = b"".join(b"event: " + t.encode() + b"\ndata: " + _json(p) + b"\n\n" for t, p in partes)
                            self.wfile.write(datos)
                            self.wfile.flush()
                            ult_envio = ahora
                        elif ahora - ult_envio > 15:
                            self.wfile.write(b": ping\n\n")
                            self.wfile.flush()
                            ult_envio = ahora
                        if servidor.detenido:
                            break
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                    return

        return Handler



# =============================================================================
# 17. [live] LO QUE SE LE AGREGA AL MOTOR: la hora en curso, el z en curso, los precios de disparo, la curva del
#     umbral y la lista de la puerta. Nada de esto cambia una decisión: todo corre sobre COPIAS.
# =============================================================================
def barra_provisional(unir: UnirVivo, k: int, barras: dict) -> dict | None:
    """Lo que UnirVivo.barra daría con la hora EN CURSO (con lo que va de ella), sin tocar su estado: el mismo código
    sobre una copia (el salto acumulado de los rolls es un dict y se copia aparte)."""
    u = copy.copy(unir)
    u.G = dict(unir.G)
    return u.barra(k, barras)


def filtro_siguiente(motor: MotorPar) -> tuple:
    """Una COPIA del filtro tal como va a procesar la próxima barra: con la fila recién calibrada ya aplicada (el
    paso 4 de MotorPar.procesar, con el propio _aplicar_fila de la v3 sobre una copia del motor). Devuelve (filtro,
    fila que rige) o (None, None) si todavía no hay calibración."""
    if motor.kf is None and motor.fila_pendiente is None:
        return None, None
    m = copy.copy(motor)
    m.kf = copy.copy(motor.kf) if motor.kf is not None else None
    if motor.fila_pendiente is not None:
        m._aplicar_fila(motor.fila_pendiente)
    return m.kf, m.fila


def z_de(kf: KalmanOU, f: dict, y: float, x: float) -> tuple:
    """El paso 5 de MotorPar.procesar sobre una copia del filtro: (z, β corregido)."""
    kf.paso(float(y), float(x))
    with np.errstate(invalid="ignore", divide="ignore"):
        z = (float(np.round((kf.m - f["mu"]) / f["sigma_eq"], DEC))
             if f["sigma_eq"] and np.isfinite(f["sigma_eq"]) else np.nan)
    return z, kf.b


def niveles_y(kf: KalmanOU, f: dict, x: float, zs) -> np.ndarray:
    """El y (escala del modelo) que, con ESTE x, deja el z filtrado exactamente en cada valor de `zs`.

    La corrección del filtro es LINEAL en y: m⁺ = m⁻ + (u₁/f)·(y − α − m⁻ − β⁻·(x − c)). Con m⁺ = μ + z·σ:
        y* = α + m⁻ + β⁻·(x − c) + (μ + z·σ − m⁻)·f/u₁
    (u₁, f y m⁻ son los de la predicción de KalmanOU.paso; el filtro no se toca). Como z crece con y, "z ≥ z_in" es
    "Y ≥ su nivel": el precio de disparo de la pierna Y con la pierna X donde está."""
    zs = np.asarray(zs, float)
    xt = float(x) - kf.c
    ph = kf.phi
    m_pr = ph * kf.m
    p11 = ph * ph * kf.p11 + kf.qm
    p12 = ph * kf.p12
    p22 = kf.p22 + kf.qb
    u1 = p11 + p12 * xt
    u2 = p12 + p22 * xt
    fv = u1 + u2 * xt + kf.r
    sig = f["sigma_eq"]
    if not (sig and np.isfinite(sig) and sig > 0 and u1 > 0 and np.isfinite(fv)):
        return np.full(zs.shape, np.nan)
    return kf.alfa + m_pr + kf.b * xt + (f["mu"] + zs * sig - m_pr) * fv / u1


def a_precio(y, g: float, cfg: Config) -> np.ndarray:
    """Escala del modelo → precio REAL del contrato (el ajustado por rolls más el salto acumulado)."""
    y = np.asarray(y, float)
    with np.errstate(over="ignore", invalid="ignore"):
        return (np.exp(y) if cfg.escala == "log" else y) + g


def niveles_dict(kf: KalmanOU | None, f: dict | None, x: float, g_y: float, cfg: Config) -> dict:
    """Los precios de Y (reales) del valor justo (z = 0), de las dos entradas, de los dos objetivos y de los dos
    stops, con la X de `x`."""
    if kf is None or f is None or not np.isfinite(f.get("z_in", np.nan)):
        return {}
    zi, zo, zs = float(f["z_in"]), float(f["z_out"]), float(cfg.z_stop)
    v = a_precio(niveles_y(kf, f, x, [0.0, -zi, zi, -zo, zo, -zs, zs]), g_y, cfg)
    return {"fv": v[0], "li": v[1], "hi": v[2], "obj_l": v[3], "obj_c": v[4], "stop_l": v[5], "stop_c": v[6]}


def curva_umbral(f: dict, cfg: Config) -> dict:
    """La ganancia esperada POR HORA (US$) de cada par (entrada a, salida b): lo que umbral_optimo maximiza, para ver
    dónde quedó el óptimo y qué tan plana es la curva (tiempos_ou de la v3, vectorizado)."""
    aa = np.arange(cfg.z_entrada_min, cfg.z_entrada_max + 1e-9, 0.05)
    sig, costo, th, vu = (float(f.get(k, np.nan)) for k in ("sigma_eq", "costo_s", "theta_h", "valor_unidad"))
    series = []
    if all(np.isfinite([sig, costo, th, vu])) and sig > 0 and th > 0:
        for b in cfg.salidas_opt:
            g = np.full(aa.size, np.nan)
            ok = aa > b + 0.2
            if ok.any():
                t_in, t_out = tiempos_ou(aa[ok], np.full(int(ok.sum()), b))
                g[ok] = ((aa[ok] - b) * sig - costo) / ((t_in + t_out) / th) * vu
            series.append({"b": float(b), "g": g})
    return {"a": aa, "series": series, "z_in": f.get("z_in"), "z_out": f.get("z_out"), "gan": f.get("ganancia_h_usd"),
            "costo_sig": costo / sig if np.isfinite(sig) and sig > 0 else np.nan, "vm": f.get("vida_media_h"),
            "umbral": cfg.umbral}


def lista_puerta(f: dict, abierta_antes: bool, cfg: Config) -> dict:
    """Lo que pide decidir_puerta (v3) con los valores de esta fila: qué pasa, qué no y qué decide."""
    estricta = cfg.prueba == "estricta"
    a = cfg.alfa_cierre if (abierta_antes and estricta) else cfg.alfa
    suf = "_cierre" if abierta_antes and estricta else ""
    vm_max = cfg.vida_media_max_frac * cfg.formacion_barras * cfg.barra_min / 60.0
    menor = lambda v, lim: bool(np.isfinite(v) and v < lim)   # noqa: E731
    items = [
        {"prueba": "Engle-Granger y ~ x (MacKinnon)", "valor": f["p_eg_yx"], "tipo": "p", "exige": f"p < {a:g}",
         "pasa": menor(f["p_eg_yx"], a), "decide": cfg.prueba in ("estricta", "eg")},
        {"prueba": "Engle-Granger x ~ y", "valor": f["p_eg_xy"], "tipo": "p", "exige": f"p < {a:g}",
         "pasa": menor(f["p_eg_xy"], a), "decide": estricta},
        {"prueba": "ADF del spread filtrado (críticos de EG)", "valor": f["adf_kalman_p"], "tipo": "p",
         "exige": f"p < {a:g}", "pasa": bool(f.get(f"pasa_adf_kalman{suf}", False)), "decide": estricta},
        {"prueba": "Vida media (corregida por bootstrap)", "valor": f["vida_media_h"], "tipo": "h",
         "exige": f"{cfg.vida_media_min_h:g}–{vm_max:.0f} h", "pasa": bool(f["pasa_vm"]), "decide": estricta},
        {"prueba": "Ganancia esperada después de costos", "valor": f["ganancia_h_usd"], "tipo": "usd_h",
         "exige": "> 0", "pasa": bool(f["pasa_econ"]), "decide": estricta},
        {"prueba": "Cobertura entera (contratos de X)", "valor": f["nx_ref"], "tipo": "n", "exige": "≥ 1",
         "pasa": bool(f["pasa_beta"]), "decide": True},
        {"prueba": "Umbral del OU", "valor": f["z_in"], "tipo": "z", "exige": "σ > 0", "pasa": bool(f["pasa_ou"]),
         "decide": True},
        {"prueba": "Johansen, traza (diagnóstico)", "valor": f["traza"], "tipo": "x",
         "exige": f"> {f['crit_traza']:.1f}" if np.isfinite(f["crit_traza"]) else "—",
         "pasa": bool(np.isfinite(f["traza"]) and f["traza"] > f["crit_traza"]), "decide": False},
        {"prueba": "KPSS de los residuos (diagnóstico)", "valor": f["kpss_p"], "tipo": "p", "exige": "p > 0.05",
         "pasa": bool(np.isfinite(f["kpss_p"]) and f["kpss_p"] > 0.05), "decide": False},
        {"prueba": "ADF de residuos con la tabla DF (la de tu script)", "valor": f["adf_resid_p"], "tipo": "p",
         "exige": "p < 0.05", "pasa": menor(f["adf_resid_p"], 0.05), "decide": False},
    ]
    return {"items": items, "abierta_antes": abierta_antes, "alfa": a, "puerta": bool(f["puerta"]),
            "motivo": f["motivo"], "prueba": cfg.prueba}


def _vm_json(x) -> float:
    """La vida media para el JSON (que no admite infinito): ∞ se guarda como 1e12."""
    return 1e12 if x is not None and not (isinstance(x, float) and math.isnan(x)) and not np.isfinite(x) else x


def siguiente_barra(ts: int, paso: int) -> int:
    """El inicio de la barra que sigue a la de `ts` con el horario de CME (salta la pausa de las 16:00 de Chicago y el
    fin de semana; los feriados no)."""
    t = int(ts) + paso
    for _ in range(80):
        if mercado_abierto(t):
            return t
        t += paso
    return int(ts) + paso


# =============================================================================
# 18. [live] NÚCLEO: minutos → horas → MotorPar; órdenes, puerta, rolls, z en curso, alertas y tablero
# =============================================================================
LADO = {1: "LARGO spread", -1: "CORTO spread"}
TXT_MOTIVO = {"objetivo": "objetivo", "stop_z": "stop de z", "stop_tiempo": "stop de tiempo",
              "ruptura": "ruptura de la cointegración", "fin": "fin de los datos"}
ICONO_MOTIVO = {"objetivo": "✅", "stop_z": "🛑", "stop_tiempo": "⏱", "ruptura": "💔", "fin": "⏹"}
CAMPOS_POS = ("dir", "ny", "nx", "py_ent", "px_ent", "ts_ent", "z_ent", "c_roll", "barras", "mae", "mfe", "vm_ent",
              "vm_b", "z_in", "z_out", "beta_ent", "t_ent")


class NucleoCoint:
    def __init__(self, cfg: Config, registro: "Registro | None" = None):
        self.cfg = cfg
        self.registro = registro
        self.lock = threading.RLock()
        self.cambio = threading.Condition(self.lock)
        self.modo = "live"
        self.sims = simbolos_par(cfg)
        self.inverso = {sym: s for s, sym in self.sims.items()}
        self.motor = MotorPar(cfg, al_evento=self._al_evento)
        self.unir = UnirVivo(cfg)
        self.agr = Agregador(cfg.barra_min, self.sims.keys())
        self.paso = cfg.barra_min * MIN_NS
        self.dec_y, self.dec_x = decimales_de(cfg.tick_y), decimales_de(cfg.tick_x)
        self.ruta: dict = {}                              # instrument_id → serie (y0, x0, y1, x1)
        self.por_serie: dict = {}
        self.contratos: dict = {}                         # serie → contrato vigente (ESZ6…)
        self.contrato_antes: dict = {}
        self.ult_min: dict = {}                           # serie → último minuto procesado (sin duplicados)
        self.t_datos = 0
        self.serie: deque = deque(maxlen=cfg.max_barras)
        self.prov: dict | None = None                     # la hora en curso
        self.niv: dict = {}                               # precios de disparo para el próximo cierre
        self.sesiones: list = []
        self.equity = 0.0
        self.eq_hist = 0.0
        self._g_prev = {"y": 0.0, "x": 0.0}
        self.marcas: list = []
        self.alertas: list = []
        self.filas: list = []
        self.cerradas: list = []
        self.curva: dict = {}
        self.lista: dict = {}
        self.audit: dict = {}
        self._clave_audit = None
        self.pend: dict | None = None                     # la orden decidida al cierre, hasta que se ejecuta
        self.ent_real: dict = {}                          # precios reales de la entrada abierta
        self.en_curso = {"k": -1, "hechos": set()}
        self._evs: list = []
        self.n_hist = 0
        self.trades_hist = 0
        self.horas_sin_par = 0
        self.cola: deque = deque(maxlen=4000)
        self.seq = self.epoca = self.ver = 0
        self.estado_txt, self.detalle = "iniciando", "Preparando…"
        self.fase = "hist"
        self.retraso_ms: float | None = None
        self.t_ult_msg = time.monotonic()
        self.mensajes = self.reconexiones = self.registros = self.duplicados = self.sin_ruta = 0
        self.notificador: "NotificadorTelegram | None" = None
        self.aviso_inicio_enviado = False
        self.reloj = time.time_ns

    # ---------------- estado general (misma interfaz que los otros núcleos) ----------------
    def avisar(self, estado: str, detalle: str = "", log: bool = True) -> None:
        with self.lock:
            self.estado_txt, self.detalle = estado, detalle
            self.cambio.notify_all()
        if log and detalle:
            LOG.info(detalle)

    def latido(self) -> None:
        self.t_ult_msg = time.monotonic()
        self.mensajes += 1

    def notificar(self, texto: str, silencioso: bool = False, responder_a: dict | None = None, guardar_en: dict | None = None) -> None:
        if self.notificador:
            self.notificador.enviar(texto, silencioso=silencioso, responder_a=responder_a, guardar_en=guardar_en)

    def par(self) -> str:
        return f"{raiz_de(self.cfg.symbol_y)} / {raiz_de(self.cfg.symbol_x)}"

    def contrato(self, s: str) -> str:
        return self.contratos.get(s) or (self.cfg.symbol_y if s[0] == "y" else self.cfg.symbol_x)

    def _nombre_html(self) -> str:
        c = [self.contratos.get(s) for s in ("y0", "x0")]
        return html.escape(self.par() + (f" ({c[0]} / {c[1]})" if all(c) else ""))

    def _py(self, p) -> str:
        return f"{p:,.{self.dec_y}f}" if _fin(p) else "—"

    def _px(self, p) -> str:
        return f"{p:,.{self.dec_x}f}" if _fin(p) else "—"

    def fila_actual(self) -> dict | None:
        return self.motor.fila_pendiente if self.motor.fila_pendiente is not None else self.motor.fila

    def _reciente(self, t: int) -> bool:
        return self.reloj() - int(t) < self.cfg.reciente_min * 60 * NS

    # ---------------- calentamiento ----------------
    def calentar(self, crudas: dict) -> None:
        """La historia (barras ya de `barra_min`) por el MISMO camino que la v3 en correr_live: UnirVivo → MotorPar."""
        with self.lock:
            self.fase = "hist"
            for k, barras in horas_de(crudas):
                self._barra(int(k), barras)
            if self.unir.ultimo_ts is not None:
                self.agr.limite = max(self.agr.limite, self.unir.ultimo_ts)
            self.n_hist = self.motor.t + 1
            self.trades_hist = len(self.motor.trades)
            self.eq_hist = self.equity
            self.epoca += 1
            self.ver += 1
            self.cambio.notify_all()
        m, cfg = self.motor, self.cfg
        if self.n_hist < cfg.formacion_barras:
            LOG.warning(f"Solo {self.n_hist} barras de historia: el motor empieza a operar cuando junte "
                        f"{cfg.formacion_barras} (una ventana de formación).")
        LOG.info(f"Calentado con {self.n_hist:,} barras ({len(m.filas)} re-estimaciones, {len(m.trades)} operaciones de "
                 f"papel en la historia, neto {_usd(self.equity)})")
        f = self.fila_actual()
        if f is not None:
            LOG.info("   última re-estimación: " + texto_fila(f))
        LOG.info(f"   posición al terminar la historia: {self._txt_pos()}"
                 + (f" · orden pendiente: {self.motor.orden[0]}" if self.motor.orden is not None else ""))

    # ---------------- Live: mapeo de símbolos, minutos y reloj ----------------
    def mapeo(self, rec) -> None:
        s = self.inverso.get(str(rec.stype_in_symbol))
        if s is None:
            return
        iid = int(rec.instrument_id)
        with self.lock:
            viejo = self.por_serie.get(s)
            if viejo is not None and self.ruta.get(viejo) == s:
                del self.ruta[viejo]
            self.por_serie[s] = iid
            self.ruta[iid] = s
            nuevo = str(rec.stype_out_symbol or "")
            if nuevo and nuevo != self.contratos.get(s):
                antes = self.contratos.get(s)
                self.contratos[s] = nuevo
                if antes:
                    self.contrato_antes[s] = antes
                    LOG.info(f"{self.sims[s]} → {nuevo} (antes {antes}, instrumento {iid})")
                else:
                    LOG.debug(f"{self.sims[s]} → {nuevo} (instrumento {iid})")

    def ohlcv(self, rec) -> None:
        """Una barra de 1 min de cualquiera de las cuatro series."""
        with self.lock:
            self.registros += 1
            s = self.ruta.get(int(rec.instrument_id))
            if s is None:
                self.sin_ruta += 1
                return
            ts = int(rec.ts_event)
            if ts <= self.ult_min.get(s, -1):              # ya procesado (replay tras reconectar)
                self.duplicados += 1
                return
            self.ult_min[s] = ts
            if ts > self.t_datos:
                self.t_datos = ts
            for k, barras in self.agr.agregar(s, ts, rec.open / 1e9, rec.high / 1e9, rec.low / 1e9, rec.close / 1e9,
                                               rec.volume, rec.instrument_id):
                self._barra(int(k), barras)
            fin_min = ts + MIN_NS
            if self.fase == "vivo":
                self.retraso_ms = (self.reloj() - fin_min) / MS
            elif self.fase == "replay" and self.reloj() - fin_min < 90 * NS:
                self._pasar_a_vivo("alcanzó el tiempo real")
            self._revisar_pendiente()
            if s in ("y0", "x0") and self.fase == "vivo":
                self._actualizar_prov()
            self.cambio.notify_all()

    def reloj_datos(self, te: int, latido: bool = False) -> None:
        """Un heartbeat (o fin de intervalo) adelanta el reloj si está cerca de los datos: cierra la última hora antes
        de una pausa; nunca salta sobre un replay en curso (la regla de la v3)."""
        with self.lock:
            if latido and self.fase == "replay":
                self._pasar_a_vivo("sin más replay")
            if self.agr.reloj and 0 < te - self.agr.reloj <= 15 * MIN_NS:
                for k, barras in self.agr.avanzar(te):
                    self._barra(int(k), barras)
            self._revisar_pendiente()
            self.cambio.notify_all()

    def desde_replay(self, corte_ns: int) -> int:
        """Desde dónde pedir el replay: lo último procesado de las dos piernas (menos 1 min; los duplicados se
        descartan por serie), o el final de la historia."""
        with self.lock:
            vistos = [self.ult_min[s] for s in ("y0", "x0") if s in self.ult_min]
            if len(vistos) == 2:
                return min(vistos) - MIN_NS
            base = corte_ns if self.unir.ultimo_ts is None else min(corte_ns, self.unir.ultimo_ts + self.paso)
            return min([base] + vistos)

    def hueco(self, deseado: int, start: int) -> None:
        """El replay no alcanza (Live repite ~24 h): si hubo mercado en medio, se avisa y se descarta la hora
        incompleta (la de la v3: "la primera barra se descarta por incompleta")."""
        with self.lock:
            abierto = any(mercado_abierto(t) for t in range(int(deseado), int(start), 15 * MIN_NS))
            if not abierto:
                return
            LOG.warning(f"Live solo repite {self.cfg.replay_max_h:g} h: faltan datos entre "
                        f"{_hora(deseado, self.cfg.zona_local)} y {_hora(start, self.cfg.zona_local)} con el mercado abierto.")
            k0 = start - start % self.paso
            lim = k0 if start % self.paso else k0 - self.paso
            if lim > self.agr.limite:
                for s, a in list(self.agr.abiertas.items()):
                    if a is not None and a[0] <= lim:
                        self.agr.abiertas[s] = None
                for k in [k for k in self.agr.listas if k <= lim]:
                    self.agr.listas.pop(k)
                self.agr.limite = lim

    # ---------------- la hora cerrada: el motor de la v3 ----------------
    def _al_evento(self, ev: dict) -> None:
        self._evs.append(ev)

    def _barra(self, k: int, barras: dict) -> None:
        br = self.unir.barra(k, barras)
        if br is None:
            self.horas_sin_par += 1
            return
        cfg, m = self.cfg, self.motor
        kf, f = filtro_siguiente(m)
        niv = niveles_dict(kf, f, br["x"], br["g_y"], cfg)
        p = self.pend
        if p is not None and not p["hecho"]:
            self._llenar(p, br)                              # la barra que la ejecuta: el precio exacto de papel
        pos_antes = m.pos
        g_antes = dict(self._g_prev)
        self._evs = []
        m.procesar(br)
        h = m.hist
        self.sesiones.append(int(br["sesion"]))
        pnl, costos = float(h["pnl"][-1]), float(h["costos"][-1])
        self.equity += pnl - costos
        fila = m.fila
        py, px = br["c_y"] + br["g_y"], br["c_x"] + br["g_x"]
        b_post = h["b_post"][-1]
        pt = _limpiar({"t": k // MS, "o": br["o_y"] + br["g_y"], "h": br["h_y"] + br["g_y"], "l": br["l_y"] + br["g_y"],
                       "c": py, "cx": px, "z": h["z"][-1], "zi": h["z_in"][-1], "zo": h["z_out"][-1],
                       "p": bool(h["puerta"][-1]), "b": b_post, "bo": fila["beta_ols"] if fila is not None else None,
                       "nx": contratos_x(b_post, py, px, cfg) if np.isfinite(b_post) else 0, "pos": int(h["pos"][-1]),
                       "eq": self.equity, "fv": niv.get("fv"), "li": niv.get("li"), "hi": niv.get("hi")})
        self.serie.append(pt)
        if self.fase != "hist":
            self._emitir("punto", pt)
            if self.registro is not None:
                self.registro.barra(pt, pnl, costos, self)
        self.prov = None
        self._g_prev = {"y": br["g_y"], "x": br["g_x"]}
        if br["roll_y"] or br["roll_x"]:
            self._roll(br, g_antes, pos_antes)
        evs, self._evs = self._evs, []
        for ev in evs:
            self._evento(ev, br)
        kf2, f2 = filtro_siguiente(m)
        self.niv = niveles_dict(kf2, f2, br["x"], br["g_y"], cfg)
        if m.orden is not None:
            self._nueva_orden(br)
        self.cambio.notify_all()

    def _evento(self, ev: dict, br: dict) -> None:
        cfg = self.cfg
        if ev["tipo"] == "entrada":
            pl = ev["plan"]
            self.ent_real = {"y": pl["py_ent"] + br["g_y"], "x": pl["px_ent"] + br["g_x"], "ts": pl["ts_ent"]}
            self.marcas.append({"t": pl["ts_ent"] // MS, "tipo": "entrada", "dir": pl["dir"],
                                "texto": f"{'largo' if pl['dir'] > 0 else 'corto'} z {_z(pl['z_ent'])}"})
            self.ver += 1
        elif ev["tipo"] == "salida":
            tr = ev["trade"]
            fase = self.fase
            self.marcas.append({"t": int(br["ts"]) // MS, "tipo": "salida", "dir": tr["dir"], "motivo": tr["motivo"],
                                "texto": f"{TXT_MOTIVO.get(tr['motivo'], tr['motivo'])} {_usd(tr['neto'])}"})
            tj = _limpiar({**tr, "fase": fase, "ts_sal": int(br["ts"]), "real_y_ent": self.ent_real.get("y"),
                           "real_x_ent": self.ent_real.get("x"), "real_y_sal": br["o_y"] + br["g_y"],
                           "real_x_sal": br["o_x"] + br["g_x"], "horas": tr["barras"] * cfg.barra_min / 60.0})
            self.cerradas.append(tj)
            self.ent_real = {}
            p = self.pend
            llen = (p or {}).get("llen") or {}
            if _fin(llen.get("neto")) and abs(llen["neto"] - tr["neto"]) > 0.01:
                LOG.warning(f"El resultado avisado ({_usd(llen['neto'])}) no coincide con el del motor ({_usd(tr['neto'])}).")
            if self.registro is not None and fase != "hist":
                self.registro.operacion(tj, self)
            self.ver += 1
        elif ev["tipo"] == "calibracion":
            self._calibracion(ev["fila"], br)

    def _fila_json(self, f: dict, br: dict) -> dict:
        py = br["c_y"] + br["g_y"]
        esc = py if self.cfg.escala == "log" else 1.0
        return _limpiar({"t": int(br["ts"]) // MS, "rige": siguiente_barra(int(br["ts"]), self.paso) // MS, "k": int(f["k"]),
                         "puerta": bool(f["puerta"]), "motivo": f["motivo"], "p_yx": f["p_eg_yx"], "p_xy": f["p_eg_xy"],
                         "adf": f["adf_kalman_p"], "adf_r": f["adf_resid_p"], "traza": f["traza"], "crit": f["crit_traza"],
                         "kpss": f["kpss_p"], "vm": _vm_json(f["vida_media_h"]), "vm_lo": _vm_json(f["vm_lo"]),
                         "vm_hi": _vm_json(f["vm_hi"]), "vm_mco": _vm_json(f["vm_mco_h"]), "beta_ols": f["beta_ols"], "beta": f["b_fin"], "z_in": f["z_in"],
                         "z_out": f["z_out"], "gan": f["ganancia_h_usd"], "nx": f["nx_ref"], "psi_b": f["psi_b"],
                         "rho_v": f["rho_v"], "sig_pts": f["sigma_eq"] * esc,
                         "costo_sig": f["costo_s"] / f["sigma_eq"] if f["sigma_eq"] else None, "py": py,
                         "fase": self.fase})

    def _calibracion(self, f: dict, br: dict) -> None:
        cfg, m = self.cfg, self.motor
        prev = m.filas[-2] if len(m.filas) >= 2 else None
        abierta_antes = bool(prev["puerta"]) if prev is not None else False
        fj = self._fila_json(f, br)
        self.filas.append(fj)
        self.curva = _limpiar(curva_umbral(f, cfg))
        self.lista = _limpiar(lista_puerta(f, abierta_antes, cfg))
        cambio = bool(f["puerta"]) != abierta_antes
        if cambio:
            self.marcas.append({"t": int(br["ts"]) // MS, "tipo": "puerta", "abre": bool(f["puerta"]),
                                "texto": "puerta abierta" if f["puerta"] else "puerta cerrada"})
        self.ver += 1
        if self.fase == "hist":
            return
        t = int(br["ts"]) + self.paso
        if cambio:
            self._alerta("puerta", t, {"fila": fj, "abre": bool(f["puerta"]), "pos": self._pos_json(),
                                       "niv": dict(self.niv), "sin_previa": prev is None})
        elif cfg.aviso_reestimacion:
            self._alerta("reestimacion", t, {"fila": fj}, silencioso=True)
        if self.registro is not None:
            self.registro.fila(fj, self)

    def _roll(self, br: dict, g_antes: dict, pos_antes: dict | None) -> None:
        cfg, m = self.cfg, self.motor
        for pie, s in (("y", "y0"), ("x", "x0")):
            if not br[f"roll_{pie}"]:
                continue
            salto = br[f"g_{pie}"] - g_antes[pie]
            costo = None
            if pos_antes is not None and m.pos is pos_antes:
                costo = _costo_roll(pos_antes["ny"], pos_antes["nx"], pie == "y", pie == "x", cfg)
            self.marcas.append({"t": int(br["ts"]) // MS, "tipo": "roll", "texto": f"roll {raiz_de(self.sims[s])}"})
            if self.fase != "hist":
                self._alerta("roll", int(br["ts"]) + self.paso, {"pie": pie, "serie": self.sims[s], "k": int(br["ts"]),
                                                                 "nuevo": self.contratos.get(s),
                                                     "antes": self.contrato_antes.get(s), "salto": salto,
                                                     "aprox": bool(br[f"aprox_{pie}"]), "costo": costo},
                             silencioso=True)

    # ---------------- órdenes: al cierre, y su precio de papel en cuanto abre la barra ----------------
    def _pos_json(self) -> dict | None:
        p = self.motor.pos
        return None if p is None else _limpiar({k: p.get(k) for k in CAMPOS_POS})

    def _nueva_orden(self, br: dict) -> None:
        m = self.motor
        o = m.orden
        tipo = o[0]
        f = m.fila
        d = {"orden": tipo, "motivo": o[1] if tipo in ("cerrar", "ambas") else None,
             "plan": _limpiar(dict(o[-1])) if tipo in ("abrir", "ambas") else None,
             "pos": self._pos_json() if tipo in ("cerrar", "ambas") else None, "k": int(br["ts"]),
             "z": m.hist["z"][-1], "cy": br["c_y"] + br["g_y"], "cx": br["c_x"] + br["g_x"], "niv": dict(self.niv),
             "fila": {c: f.get(c) for c in ("z_in", "z_out", "vida_media_h", "p_eg_yx", "p_eg_xy", "adf_kalman_p",
                                             "ganancia_h_usd", "puerta", "beta_ols")} if f is not None else {},
             "ent_real": dict(self.ent_real)}
        self.pend = {"k": int(br["ts"]), "datos": _limpiar(d), "enviada": False, "hecho": False, "alerta": None,
                     "llen": None}
        if self.fase == "hist":
            return
        hay_siguiente = any(a is not None and a[0] > br["ts"] for s, a in self.agr.abiertas.items() if s in ("y0", "x0"))
        if not hay_siguiente:                             # cerró por el reloj (pausa): se avisa ya, sin precio
            self._alerta_orden(self.pend)

    def _llenado(self, k: int) -> dict | None:
        """La barra siguiente, si ya abrieron las DOS piernas: su apertura es el precio de papel (no cambia)."""
        a_y, a_x = self.agr.abiertas.get("y0"), self.agr.abiertas.get("x0")
        if a_y is None or a_x is None or a_y[0] <= k or a_y[0] != a_x[0]:
            return None
        K = a_y[0]
        barras = {s: tuple(a[1:]) for s, a in self.agr.abiertas.items() if a is not None and a[0] == K}
        return barra_provisional(self.unir, K, barras)

    def _resultado(self, p: dict, br: dict) -> dict:
        cfg = self.cfg
        d = p["datos"]
        r = {"t": int(br["ts"]), "oy": br["o_y"] + br["g_y"], "ox": br["o_x"] + br["g_x"]}
        q = d.get("pos")
        if q is not None:
            bruto = q["dir"] * (q["ny"] * cfg.mult_y * (br["o_y"] - q["py_ent"]) - q["nx"] * cfg.mult_x * (br["o_x"] - q["px_ent"]))
            costos = q["c_roll"] + 2 * costos_unidad(q["nx"], cfg)
            r.update(bruto=bruto, costos=costos, neto=bruto - costos)
        return _limpiar(r)

    def _llenar(self, p: dict, br: dict) -> None:
        p["llen"] = self._resultado(p, br)
        p["hecho"] = True
        if self.fase == "hist":
            return
        if not p["enviada"]:
            self._alerta_orden(p)
        else:
            self._seguimiento(p)

    def _revisar_pendiente(self) -> None:
        p = self.pend
        if p is None or p["hecho"] or self.fase == "hist":
            return
        br = self._llenado(p["k"])
        if br is not None:
            self._llenar(p, br)
        elif not p["enviada"] and self.agr.reloj >= p["k"] + self.paso + 2 * MIN_NS:
            self._alerta_orden(p)

    def _alerta_orden(self, p: dict) -> None:
        p["enviada"] = True
        p["alerta"] = self._alerta("orden", p["k"] + self.paso, {**p["datos"], "llen": p["llen"]})

    def _seguimiento(self, p: dict) -> None:
        k = p["alerta"]
        if k is None:
            return
        k["datos"]["llen"] = p["llen"]
        k["texto_ej"] = texto_ejecucion(k, self)
        self.ver += 1
        LOG.info(_plano(k["texto_ej"]).replace("\n", " · "))
        if self.notificador and self._reciente(p["llen"]["t"]):
            self.notificador.enviar(k["texto_ej"], responder_a=k["tg"], silencioso=True)

    # ---------------- la hora en curso ----------------
    def _actualizar_prov(self) -> None:
        cfg = self.cfg
        a_y, a_x = self.agr.abiertas.get("y0"), self.agr.abiertas.get("x0")
        if a_y is None or a_x is None or a_y[0] != a_x[0] or a_y[0] <= self.agr.limite:
            return
        k = a_y[0]
        barras = {s: tuple(a[1:]) for s, a in self.agr.abiertas.items() if a is not None and a[0] == k}
        br = barra_provisional(self.unir, k, barras)
        if br is None:
            return
        py, px = br["c_y"] + br["g_y"], br["c_x"] + br["g_x"]
        pt = {"t": k // MS, "o": br["o_y"] + br["g_y"], "h": br["h_y"] + br["g_y"], "l": br["l_y"] + br["g_y"], "c": py,
              "cx": px, "prov": True}
        kf, f = filtro_siguiente(self.motor)
        if kf is not None and f is not None:
            niv = niveles_dict(kf, f, br["x"], br["g_y"], cfg)
            z, b = z_de(kf, f, br["y"], br["x"])
            pt.update(z=z, zi=f["z_in"], zo=f["z_out"], p=bool(f["puerta"]), b=b, bo=f["beta_ols"],
                      nx=contratos_x(b, py, px, cfg) if np.isfinite(b) else 0, fv=niv.get("fv"), li=niv.get("li"),
                      hi=niv.get("hi"))
            self.niv = niv
            self._en_curso(k, z, b, f, br)
        pt["eq"] = self.equity + self._pnl_en_curso(br)
        self.prov = _limpiar(pt)

    def _pnl_en_curso(self, br: dict) -> float:
        """El P&L de la hora en curso marcado a mercado, con la orden pendiente ya ejecutada a la apertura (las cuentas
        de los pasos 1 y 3 de MotorPar.procesar; sin el costo de un roll)."""
        cfg, m = self.cfg, self.motor
        my, mx = cfg.mult_y, cfg.mult_x
        pnl = 0.0
        o = m.orden
        p = m.pos
        if p is not None:
            if o is not None and o[0] in ("cerrar", "ambas"):
                pnl += p["dir"] * (p["ny"] * my * (br["o_y"] - p["ref_y"]) - p["nx"] * mx * (br["o_x"] - p["ref_x"]))
                pnl -= costos_unidad(p["nx"], cfg)
            else:
                pnl += p["dir"] * (p["ny"] * my * (br["c_y"] - p["ref_y"]) - p["nx"] * mx * (br["c_x"] - p["ref_x"]))
        if o is not None and o[0] in ("abrir", "ambas"):
            pl = o[-1]
            pnl += pl["dir"] * (pl["ny"] * my * (br["c_y"] - br["o_y"]) - pl["nx"] * mx * (br["c_x"] - br["o_x"]))
            pnl -= costos_unidad(pl["nx"], cfg)
        return float(pnl)

    def _en_curso(self, k: int, z: float, b: float, f: dict, br: dict) -> None:
        """¿La hora va camino de cerrar con orden? El paso 6 de MotorPar.procesar con el z en curso (y con la orden
        pendiente ya ejecutada). Un aviso por barra y por tipo."""
        cfg, m = self.cfg, self.motor
        if self.fase != "vivo" or not cfg.aviso_en_curso or not np.isfinite(z):
            return
        if self.en_curso["k"] != k:
            self.en_curso = {"k": k, "hechos": set()}
        o = m.orden
        pos = m.pos
        if o is not None and o[0] in ("cerrar", "ambas"):
            pos = None
        if o is not None and o[0] in ("abrir", "ambas"):
            pos = o[-1]
        py, px = br["c_y"] + br["g_y"], br["c_x"] + br["g_x"]
        datos = None
        if pos is not None:
            motivo = None
            if (pos["dir"] > 0 and z >= -pos["z_out"]) or (pos["dir"] < 0 and z <= pos["z_out"]):
                motivo = "objetivo"
            elif (pos["dir"] > 0 and z <= -cfg.z_stop) or (pos["dir"] < 0 and z >= cfg.z_stop):
                motivo = "stop_z"
            if motivo is not None:
                estimado = None
                if "py_ent" in pos:
                    estimado = (pos["dir"] * (pos["ny"] * cfg.mult_y * (br["c_y"] - pos["py_ent"])
                                              - pos["nx"] * cfg.mult_x * (br["c_x"] - pos["px_ent"]))
                                - pos.get("c_roll", 0.0) - 2 * costos_unidad(pos["nx"], cfg))
                datos = {"que": "salida", "motivo": motivo, "dir": pos["dir"], "ny": pos["ny"], "nx": pos["nx"],
                         "z_out": pos["z_out"], "estimado": estimado}
        elif f["puerta"] and m.t + 1 >= m.cool and np.isfinite(f["z_in"]) and abs(z) >= f["z_in"]:
            nx = contratos_x(b, py, px, cfg)
            if nx >= 1:
                datos = {"que": "entrada", "dir": -1 if z >= f["z_in"] else 1, "ny": cfg.contratos_y, "nx": nx}
        if datos is None or datos["que"] in self.en_curso["hechos"]:
            return
        self.en_curso["hechos"].add(datos["que"])
        self._alerta("en_curso", self.t_datos + MIN_NS, {**datos, "k": k, "z": z, "z_in": f["z_in"], "cy": py, "cx": px,
                                                          "niv": dict(self.niv)}, silencioso=True)

    # ---------------- alertas ----------------
    def _emitir(self, tipo: str, datos) -> None:
        self.seq += 1
        self.cola.append((tipo, datos))

    def _alerta(self, tipo: str, t: int, datos: dict, silencioso: bool = False) -> dict:
        ult = self.serie[-1] if self.serie else {}
        k = {"id": len(self.alertas) + 1, "tipo": tipo, "t": int(t), "fase": self.fase, "datos": datos, "tg": {},
             "z": datos.get("z", ult.get("z")), "cy": datos.get("cy", ult.get("c")), "cx": datos.get("cx", ult.get("cx"))}
        k["texto"] = texto_alerta(k, self)
        self.alertas.append(k)
        self.ver += 1
        LOG.warning("*** " + _plano(k["texto"]).replace("\n", " · "))
        if self.registro is not None:
            self.registro.alerta(k, self)
        reciente = self._reciente(t)
        if self.cfg.sonido and self.modo == "live" and reciente and tipo in ("orden", "puerta"):
            _pitido()
        if self.notificador and reciente:
            self.notificador.enviar(k["texto"], guardar_en=k["tg"], silencioso=silencioso)
        return k

    # ---------------- auditoría de papel (en su propio hilo) ----------------
    def analizar(self) -> None:
        """La auditoría de la v3 sobre las operaciones de PAPEL: toda la historia de papel (desde la primera
        calibración) y lo que va en vivo."""
        cfg = self.cfg
        with self.lock:
            m = self.motor
            n = m.t + 1
            clave = (n, len(m.trades))
            if clave == self._clave_audit or not m.filas:
                return
            res = {"pnl": np.array(m.hist["pnl"], float), "costos": np.array(m.hist["costos"], float),
                   "pos": np.array(m.hist["pos"], np.int64), "trades": pd.DataFrame(m.trades, columns=COLS_TRADES)}
            b = {"sesion": np.array(self.sesiones, np.int64)}
            ini_tot = int(m.filas[0]["k"]) + 1
            ini_viv = max(self.n_hist, ini_tot)
        out = {}
        for nombre, ini in (("total", ini_tot), ("vivo", ini_viv)):
            if ini >= n:
                continue
            a = auditar(res, b, cfg, ini)
            j = {k: v for k, v in a.items() if not isinstance(v, (pd.DataFrame, pd.Series))}
            if isinstance(a.get("por_motivo"), pd.DataFrame):
                j["por_motivo"] = a["por_motivo"].reset_index().to_dict("records")
            out[nombre] = j
        with self.lock:
            self.audit = _limpiar(out)
            self._clave_audit = clave
            self.ver += 1
            self.cambio.notify_all()

    # ---------------- fases ----------------
    def en_replay(self) -> None:
        with self.lock:
            self.fase = "replay"
            self.estado_txt, self.detalle = "replay", "Poniéndose al día con el replay de ohlcv-1m…"
            self.cambio.notify_all()

    def pasar_a_vivo(self, motivo: str = "") -> None:
        with self.lock:
            self._pasar_a_vivo(motivo)

    def _pasar_a_vivo(self, motivo: str) -> None:
        if self.fase != "vivo":
            LOG.info(f"En vivo ({motivo}).")
        self.fase = "vivo"
        self.estado_txt = "demo" if self.modo == "demo" else "vivo"
        self.detalle = ""
        self._revisar_pendiente()
        self._actualizar_prov()
        self.cambio.notify_all()
        if self.notificador and not self.aviso_inicio_enviado:
            self.aviso_inicio_enviado = True
            self.notificador.enviar(texto_inicio(self), silencioso=True)

    # ---------------- tablero ----------------
    def _txt_pos(self) -> str:
        p = self.motor.pos
        if p is None:
            return "plano"
        return (f"{LADO[p['dir']]} ({'+' if p['dir'] > 0 else '−'}{p['ny']} {self.contrato('y0')} / "
                f"{'−' if p['dir'] > 0 else '+'}{p['nx']} {self.contrato('x0')})")

    def _pend_json(self) -> dict | None:
        p = self.pend
        if p is None or (p["hecho"] and self.motor.orden is None):
            return None
        d = p["datos"]
        return {"orden": d["orden"], "motivo": d["motivo"], "plan": d["plan"], "k": d["k"] // MS, "llen": p["llen"],
                "enviada": p["enviada"]}

    def _alerta_json(self, k: dict) -> dict:
        d = k["datos"]
        sub = d.get("orden") or d.get("que") or ("abre" if d.get("abre") else "cierra" if "abre" in d else d.get("pie"))
        texto = _plano(k["texto"])
        if k.get("texto_ej"):
            texto += "\n" + _plano(k["texto_ej"])
        return _limpiar({"id": k["id"], "tipo": k["tipo"], "sub": sub, "t": k["t"] // MS, "f": k["fase"], "z": k["z"],
                         "cy": k["cy"], "dir": (d.get("plan") or d.get("pos") or d).get("dir"), "texto": texto})

    def _cfg_json(self) -> dict:
        c = self.cfg
        return _limpiar({"modo": self.modo, "y": c.symbol_y, "x": c.symbol_x, "ry": raiz_de(c.symbol_y),
                         "rx": raiz_de(c.symbol_x), "sims": self.sims, "dataset": c.dataset, "barra_min": c.barra_min,
                         "formacion": c.formacion_barras, "reestimar": c.reestimar_cada, "prueba": c.prueba,
                         "alfa": c.alfa, "alfa_cierre": c.alfa_cierre, "umbral": c.umbral, "z_stop": c.z_stop,
                         "stop_vidas": c.stop_tiempo_vidas, "enfriamiento": c.enfriamiento_barras, "escala": c.escala,
                         "mult_y": c.mult_y, "mult_x": c.mult_x, "ny": c.contratos_y, "comision": c.comision_usd,
                         "desliz": c.deslizamiento_ticks, "roll_ticks": c.roll_ticks, "capital": c.capital_usd,
                         "kalman": c.kalman, "beta_din": c.beta_dinamico, "zona": c.zona_local, "dec_y": self.dec_y,
                         "dec_x": self.dec_x, "telegram": self.notificador is not None, "n_hist": self.n_hist,
                         "trades_hist": self.trades_hist, "vm_min": c.vida_media_min_h,
                         "vm_max": c.vida_media_max_frac * c.formacion_barras * c.barra_min / 60.0,
                         "en_curso": c.aviso_en_curso})

    def _tick(self) -> dict:
        ahora = self.reloj()
        estado, detalle = self.estado_txt, self.detalle
        if estado == "vivo":
            silencio = time.monotonic() - self.t_ult_msg
            if silencio > 2 * self.cfg.heartbeat_s + 10:
                estado, detalle = "sin_datos", f"No llega nada de Databento desde hace {silencio:.0f} s."
            elif not mercado_abierto(ahora):
                estado, detalle = "cerrado", "Mercado cerrado (horario de CME): la próxima barra llega al abrir."
        m, cfg = self.motor, self.cfg
        f = self.fila_actual()
        prox = None
        if m.t >= cfg.formacion_barras - 1:
            prox = cfg.reestimar_cada - ((m.t - (cfg.formacion_barras - 1)) % cfg.reestimar_cada)
        elif m.t >= 0:
            prox = cfg.formacion_barras - 1 - m.t
        p = m.pos
        pos = None
        if p is not None:
            ult = self.serie[-1] if self.serie else {}
            abierto_cierre = (p["dir"] * (p["ny"] * cfg.mult_y * (p["ref_y"] - p["py_ent"])
                                          - p["nx"] * cfg.mult_x * (p["ref_x"] - p["px_ent"])))
            pos = {**self._pos_json(), "real_y": self.ent_real.get("y"), "real_x": self.ent_real.get("x"),
                   "abierto": abierto_cierre, "vm_barras": p["vm_b"] * cfg.stop_tiempo_vidas if _fin(p["vm_b"]) else None,
                   "ult": ult.get("t")}
        return _limpiar({"ahora": ahora // MS, "estado": estado, "detalle": detalle, "fase": self.fase,
                         "retraso_ms": _r(self.retraso_ms, 0), "abierto": mercado_abierto(ahora),
                         "ult": self.serie[-1] if self.serie else None, "prov": self.prov, "niv": self.niv,
                         "pos": pos, "pend": self._pend_json(),
                         "puerta": ({"abierta": bool(f["puerta"]), "motivo": f["motivo"],
                                     "t": (self.filas[-1]["t"] if self.filas else None)} if f is not None else None),
                         "prox": prox, "equity": self.equity, "eq_vivo": self.equity - self.eq_hist,
                         "contratos": {s: self.contratos.get(s) for s in self.sims},
                         "stats": {"registros": self.registros, "mensajes": self.mensajes, "reconexiones": self.reconexiones,
                                   "duplicados": self.duplicados, "tarde": self.agr.tarde, "sin_ruta": self.sin_ruta,
                                   "barras": m.t + 1, "barras_vivo": m.t + 1 - self.n_hist, "sin_par": self.horas_sin_par,
                                   "filas": len(m.filas), "trades": len(m.trades),
                                   "alertas_vivo": sum(1 for k in self.alertas if k["fase"] == "vivo")}})

    def _listas(self) -> dict:
        return {"alertas": [self._alerta_json(k) for k in self.alertas[-200:]], "marcas": self.marcas[-500:],
                "filas": self.filas[-500:], "trades": self.cerradas[-300:], "audit": self.audit, "curva": self.curva,
                "lista": self.lista, "cfg": self._cfg_json()}

    def snapshot(self) -> dict:
        with self.lock:
            return self._snapshot()

    def _snapshot(self) -> dict:
        return {**self._listas(), "serie": list(self.serie), "tick": self._tick()}

    def paquete(self, cli: dict, con_tick: bool) -> list[tuple[str, dict]]:
        with self.lock:
            if cli["epoca"] != self.epoca or self.seq - cli["cursor"] > len(self.cola):
                cli.update(epoca=self.epoca, cursor=self.seq, ver=self.ver)
                return [("snapshot", self._snapshot())]
            partes: list[tuple[str, dict]] = []
            nuevos = self.seq - cli["cursor"]
            if nuevos:
                partes.extend(itertools.islice(self.cola, len(self.cola) - nuevos, None))
                cli["cursor"] = self.seq
            if cli["ver"] != self.ver:
                partes.append(("listas", self._listas()))
                cli["ver"] = self.ver
            if con_tick or partes:
                partes.append(("tick", self._tick()))
            return partes


# =============================================================================
# 19. TEXTOS DE TELEGRAM
# =============================================================================
def _usd(x, firmado: bool = True) -> str:
    if not _fin(x):
        return "—"
    s = ("+" if x > 0 else "−" if x < 0 else "") if firmado else ("−" if x < 0 else "")
    return f"{s}US$ {abs(x):,.0f}"


def _z(x) -> str:
    return f"{'+' if x > 0 else '−' if x < 0 else ''}{abs(x):.2f}" if _fin(x) else "—"


def _p(x) -> str:
    return "—" if not _fin(x) else ("&lt;0.001" if x < 0.001 else f"{x:.3f}")


def _plano(texto: str) -> str:
    """El texto de Telegram (HTML) sin etiquetas ni entidades: para el log, el CSV y el tablero."""
    return html.unescape(re.sub(r"<[^>]+>", "", texto))


def _ops(n: int) -> str:
    return f"{n} {'operación' if n == 1 else 'operaciones'}"


def _vm(x) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    return "∞" if not _fin(x) or x > 1e4 else f"{x:.1f} h"


def _n(x, d: int = 2) -> str:
    return f"{x:,.{d}f}" if _fin(x) else "—"


def _firmado(x, d: int) -> str:
    return f"{'+' if x > 0 else '−' if x < 0 else ''}{abs(x):,.{d}f}" if _fin(x) else "—"


def _hm(t_ns: int, zona: str) -> str:
    return pd.Timestamp(int(t_ns), tz="UTC").tz_convert(zona).strftime("%H:%M")


def _etiqueta_zona(zona: str) -> str:
    return " CDMX" if zona == "America/Mexico_City" else ""


def texto_fila(f: dict) -> str:
    """Una re-estimación en una línea (la fila_txt de la v3)."""
    return (f"EG p {_p(f['p_eg_yx'])}/{_p(f['p_eg_xy'])} · ADF spread {_p(f['adf_kalman_p'])} · vida media "
            f"{_vm(f['vida_media_h'])} · umbral ±{_n(f['z_in'])}/{_n(f['z_out'])} · puerta "
            + ("ABIERTA" if f["puerta"] else f"cerrada ({f['motivo']})"))


EXPLICA = {"eg": "Engle-Granger no pasa en los dos sentidos", "adf_kalman": "el ADF del spread filtrado no pasa",
           "vm": "la vida media está fuera de rango", "econ": "no hay ganancia esperada después de costos",
           "beta": "el β no da ni un contrato de cobertura", "ou": "el spread no tiene umbral (σ = 0)"}


def _acciones(dir_: int, ny: int, nx: int, nuc: "NucleoCoint", salir: bool = False) -> str:
    """Qué hacer con cada pierna. Largo spread = comprar Y y vender X (y al revés para salir)."""
    compra_y = (dir_ > 0) != salir
    y, x = html.escape(nuc.contrato("y0")), html.escape(nuc.contrato("x0"))
    a = f"{'Comprar' if compra_y else 'Vender'} <b>{ny} {y}</b>"
    b = f"{'vender' if compra_y else 'comprar'} <b>{nx} {x}</b>"
    return f"{a} · {b}"


def _linea_papel(llen: dict | None, nuc: "NucleoCoint") -> str:
    z = nuc.cfg.zona_local
    if not llen:
        return "Papel: a la apertura de la próxima barra (te aviso el precio en este mismo hilo)."
    return (f"Papel: a la apertura de las {_hm(llen['t'], z)} → {html.escape(nuc.contrato('y0'))} {nuc._py(llen['oy'])} · "
            f"{html.escape(nuc.contrato('x0'))} {nuc._px(llen['ox'])}")


def _linea_resultado(llen: dict | None, q: dict, nuc: "NucleoCoint") -> str | None:
    if not llen or not _fin(llen.get("neto")):
        return None
    cfg = nuc.cfg
    horas = q["barras"] * cfg.barra_min / 60.0
    vidas = f" ({horas / q['vm_ent']:.1f} vidas medias)" if _fin(q.get("vm_ent")) and q["vm_ent"] > 0 else ""
    return (f"Resultado de papel: bruto {_usd(llen['bruto'])} − costos {_usd(llen['costos'], False)} = "
            f"<b>neto {_usd(llen['neto'])}</b> · {horas:.0f} h en posición{vidas} · MAE {_usd(q['mae'])} · MFE {_usd(q['mfe'])}")


def texto_alerta(k: dict, nuc: "NucleoCoint") -> str:
    cfg = nuc.cfg
    z = cfg.zona_local
    d = k["datos"]
    par = nuc._nombre_html()
    Y, X = html.escape(raiz_de(cfg.symbol_y)), html.escape(raiz_de(cfg.symbol_x))
    if k["tipo"] == "orden":
        cab = f"🕒 {_hm(k['t'], z)}{_etiqueta_zona(z)} · cierre de la barra de las {_hm(d['k'], z)} · {Y} {nuc._py(d['cy'])} · {X} {nuc._px(d['cx'])}"
        fl = d.get("fila") or {}
        llen = d.get("llen")
        bloques = []
        titulo = None
        if d["orden"] in ("cerrar", "ambas"):
            q = d["pos"]
            mot = d["motivo"]
            por_que = {"objetivo": f"z {_z(d['z'])} {'≥' if q['dir'] > 0 else '≤'} {_z(-q['dir'] * q['z_out'])}: el spread volvió a su media.",
                       "stop_z": f"z {_z(d['z'])}: pasó el stop de |z| ≥ {cfg.z_stop:g} (el spread se fue en contra).",
                       "stop_tiempo": f"{q['barras']} barras en posición: pasó el stop de tiempo "
                                      f"({cfg.stop_tiempo_vidas:g} vidas medias de {_vm(q['vm_ent'])}).",
                       "ruptura": "la prueba estricta dejó de pasar: sin cointegración no se sostiene la apuesta."}.get(mot, mot)
            titulo = f"{ICONO_MOTIVO.get(mot, '⚪')} <b>CERRAR {LADO[q['dir']].upper()} · {TXT_MOTIVO.get(mot, mot)} · {par}</b>"
            bloques += [_acciones(q["dir"], q["ny"], q["nx"], nuc, salir=True), por_que]
            r = _linea_resultado(llen, q, nuc)
            bloques.append(r if r else _linea_papel(llen, nuc))
            if r:
                bloques.append(_linea_papel(llen, nuc))
        if d["orden"] in ("abrir", "ambas"):
            pl = d["plan"]
            dir_ = pl["dir"]
            niv = d.get("niv") or {}
            t_abr = f"{'🟢' if dir_ > 0 else '🔴'} <b>ABRIR {LADO[dir_].upper()} · {par}</b>"
            titulo = t_abr if titulo is None else titulo.replace("</b>", "") + f" y ABRIR {LADO[dir_].upper()}</b>"
            justo = ""
            if _fin(niv.get("fv")):
                justo = (f" · {Y} {nuc._py(d['cy'])} contra su valor justo por {X} {nuc._py(niv['fv'])} "
                         f"({_firmado(d['cy'] - niv['fv'], nuc.dec_y)} pts)")
            obj = niv.get("obj_l") if dir_ > 0 else niv.get("obj_c")
            stp = niv.get("stop_l") if dir_ > 0 else niv.get("stop_c")
            horas_t = cfg.stop_tiempo_vidas * pl["vm_ent"] if _fin(pl.get("vm_ent")) else float("nan")
            bloques += [_acciones(dir_, pl["ny"], pl["nx"], nuc),
                        f"z <b>{_z(pl['z_ent'])}</b> {'≤' if dir_ > 0 else '≥'} {_z(-dir_ * pl['z_in'])} (umbral "
                        f"{'óptimo con costos' if cfg.umbral == 'optimo' else 'fijo'}) · β {pl['beta_ent']:.4f}{justo}",
                        _linea_papel(llen, nuc) if d["orden"] == "abrir" else None,
                        f"Plan congelado: objetivo z {'≥' if dir_ > 0 else '≤'} {_z(-dir_ * pl['z_out'])}"
                        + (f" (hoy ≈ {Y} {'≥' if dir_ > 0 else '≤'} {nuc._py(obj)})" if _fin(obj) else "")
                        + f" · stop |z| ≥ {cfg.z_stop:g}" + (f" (≈ {Y} {'≤' if dir_ > 0 else '≥'} {nuc._py(stp)})" if _fin(stp) else "")
                        + (f" · stop de tiempo {horas_t:.0f} h ({cfg.stop_tiempo_vidas:g} vidas medias de {_vm(pl['vm_ent'])})"
                           if _fin(horas_t) else ""),
                        f"Puerta abierta: EG p {_p(fl.get('p_eg_yx'))}/{_p(fl.get('p_eg_xy'))} · ADF spread "
                        f"{_p(fl.get('adf_kalman_p'))} · ganancia esperada {_usd(fl.get('ganancia_h_usd'))}/h"]
        return "\n".join([titulo, cab] + [b for b in bloques if b] + ["<i>Papel: el indicador no envía órdenes.</i>"])
    if k["tipo"] == "puerta":
        f = d["fila"]
        abre = d["abre"]
        cab = f"🕒 {_hm(k['t'], z)}{_etiqueta_zona(z)} · re-estimación con las {cfg.formacion_barras} barras previas"
        lineas = [f"{'🔓' if abre else '🔒'} <b>PUERTA {'ABIERTA' if abre else 'CERRADA'} · {par}</b>", cab]
        if abre:
            lineas.append(f"Pasa la prueba {cfg.prueba} a α = {cfg.alfa:g}: hay evidencia de cointegración y se puede operar.")
        else:
            mot = [EXPLICA.get(m_, m_) for m_ in str(f["motivo"]).split(",") if m_]
            lineas.append("No pasa: " + "; ".join(mot) + ".")
        lineas.append(f"EG p y~x {_p(f['p_yx'])} · x~y {_p(f['p_xy'])} · ADF del spread {_p(f['adf'])} · vida media "
                      f"{_vm(f['vm'])} [IC 90 %: {_vm(f['vm_lo'])}–{_vm(f['vm_hi'])}]")
        lineas.append(f"Umbral ±{_n(f['z_in'])} / {_n(f['z_out'])} · σ del spread {_n(f['sig_pts'], 1)} pts de {Y} · "
                      f"ganancia esperada {_usd(f['gan'])}/h · β MCO {_n(f['beta_ols'], 4)}")
        pos = d.get("pos")
        niv = d.get("niv") or {}
        if not abre and pos is not None and cfg.salir_si_rompe:
            lineas.append(f"Con la posición abierta ({LADO[pos['dir']]}): se cierra por RUPTURA al cierre de la próxima barra.")
        elif abre and pos is None and _fin(niv.get("hi")):
            lineas.append(f"Rige desde la próxima barra: corto si {Y} ≥ <b>{nuc._py(niv['hi'])}</b> · largo si {Y} ≤ "
                          f"<b>{nuc._py(niv['li'])}</b> (con {X} {nuc._px(k['cx'])}; valor justo {nuc._py(niv['fv'])}).")
        else:
            lineas.append(f"Rige desde la próxima barra ({_hm(f['rige'] * MS, z)}).")
        return "\n".join(lineas)
    if k["tipo"] == "reestimacion":
        f = d["fila"]
        return (f"📐 <b>Re-estimación · {par}</b> · puerta {'abierta (sigue)' if f['puerta'] else 'cerrada (sigue)'}\n"
                f"EG p {_p(f['p_yx'])}/{_p(f['p_xy'])} · ADF spread {_p(f['adf'])} · vida media {_vm(f['vm'])} · umbral "
                f"±{_n(f['z_in'])}/{_n(f['z_out'])} · β MCO {_n(f['beta_ols'], 4)} → {f['nx']} {X} · ganancia {_usd(f['gan'])}/h"
                + ("" if f["puerta"] else f"\nMotivo: {html.escape(str(f['motivo']))}"))
    if k["tipo"] == "en_curso":
        cierre = _hm(d["k"] + nuc.paso, z)
        niv = d.get("niv") or {}
        if d["que"] == "entrada":
            dir_ = d["dir"]
            nivel = niv.get("li") if dir_ > 0 else niv.get("hi")
            return "\n".join([
                f"⏳ <b>SEÑAL EN CURSO · {LADO[dir_].upper()} · {par}</b>",
                f"🕒 {_hm(k['t'], z)}{_etiqueta_zona(z)} · la barra cierra a las {cierre}",
                f"z en curso <b>{_z(d['z'])}</b> (umbral ±{_n(d['z_in'])}): si la hora cierra así, ABRE {LADO[dir_]} → "
                + _acciones(dir_, d["ny"], d["nx"], nuc) + ".",
                f"{Y} ahora {nuc._py(d['cy'])}" + (f" · disparo: {Y} {'≤' if dir_ > 0 else '≥'} <b>{nuc._py(nivel)}</b> con {X} en "
                                                     f"{nuc._px(d['cx'])}" if _fin(nivel) else "") + ".",
                "<i>Aviso: la orden sale al cierre, con el z del cierre.</i>"])
        mot = d["motivo"]
        return "\n".join([
            f"⏳ <b>SALIDA EN CURSO · {TXT_MOTIVO.get(mot, mot)} · {par}</b>",
            f"🕒 {_hm(k['t'], z)}{_etiqueta_zona(z)} · la barra cierra a las {cierre}",
            f"z en curso <b>{_z(d['z'])}</b>: si la hora cierra así, CIERRA el {LADO[d['dir']]} ("
            + _acciones(d["dir"], d["ny"], d["nx"], nuc, salir=True) + ")"
            + (f"; a precios de ahora serían {_usd(d['estimado'])} netos." if _fin(d.get("estimado")) else "."),
            "<i>Aviso: la orden sale al cierre, con el z del cierre.</i>"])
    if k["tipo"] == "roll":
        serie = html.escape(d["serie"])
        cambio = (f"{html.escape(d['antes'])} → {html.escape(d['nuevo'])}" if d.get("antes") and d.get("nuevo")
                  else "cambio de contrato")
        lineas = [f"🔁 <b>ROLL · {serie} · {cambio}</b>",
                  f"🕒 barra de las {_hm(d['k'], z)}{_etiqueta_zona(z)} · salto {_firmado(d['salto'], 2)} pts "
                  + ("(medido con el salto entero: no había .n.1)" if d["aprox"] else "(medido con la .n.1 en la hora previa)"),
                  "El ajuste es hacia adelante: el modelo no ve el salto; el P&amp;L de papel sigue siendo el real."]
        if _fin(d.get("costo")):
            lineas.append(f"Con la posición abierta: costo del roll de papel {_usd(d['costo'], False)} (2 comisiones y "
                          f"{cfg.roll_ticks:g} tick de calendario por contrato).")
        return "\n".join(lineas)
    return html.escape(str(d))


def texto_ejecucion(k: dict, nuc: "NucleoCoint") -> str:
    d = k["datos"]
    llen = d["llen"]
    lineas = [f"✔️ <b>Ejecutada en papel</b> · {nuc._nombre_html()}", _linea_papel(llen, nuc)]
    if d.get("pos") is not None:
        r = _linea_resultado(llen, d["pos"], nuc)
        if r:
            lineas.append(r)
    return "\n".join(lineas)


def texto_inicio(nuc: "NucleoCoint") -> str:
    cfg, m = nuc.cfg, nuc.motor
    Y, X = html.escape(raiz_de(cfg.symbol_y)), html.escape(raiz_de(cfg.symbol_x))
    f = nuc.fila_actual()
    ult = nuc.serie[-1] if nuc.serie else {}
    lineas = [f"🟢 <b>Cointegración Live en vivo · {nuc._nombre_html()}</b>",
              f"Barras de {cfg.barra_min} min · ventana {cfg.formacion_barras} barras · re-estima cada {cfg.reestimar_cada} · "
              f"prueba {cfg.prueba} (abre con α {cfg.alfa:g}, sigue abierta con p &lt; {cfg.alfa_cierre:g}) · contratos "
              f"{cfg.contratos_y} {Y} contra n {X}"]
    if f is None:
        lineas.append(f"Juntando barras: {m.t + 1} de {cfg.formacion_barras} para la primera calibración.")
    else:
        lineas.append(f"Puerta <b>{'ABIERTA' if f['puerta'] else 'CERRADA'}</b> · " + texto_fila(f).split(" · puerta")[0])
    if _fin(ult.get("z")):
        niv = nuc.niv or {}
        lineas.append(f"z <b>{_z(ult['z'])}</b> · β {_n(ult.get('b'), 4)} → {cfg.contratos_y} {Y} / {ult.get('nx')} {X}"
                      + (f" · disparo: corto si {Y} ≥ {nuc._py(niv['hi'])} · largo si {Y} ≤ {nuc._py(niv['li'])}"
                         if _fin(niv.get("hi")) else ""))
    p = m.pos
    if p is not None:
        abierto = p["dir"] * (p["ny"] * cfg.mult_y * (p["ref_y"] - p["py_ent"]) - p["nx"] * cfg.mult_x * (p["ref_x"] - p["px_ent"]))
        lineas.append(f"Posición de papel: <b>{html.escape(nuc._txt_pos())}</b> desde {_hora(p['ts_ent'], cfg.zona_local)} "
                      f"(z {_z(p['z_ent'])}) · P&amp;L abierto {_usd(abierto)}")
    else:
        lineas.append("Posición de papel: plano.")
    if m.orden is not None:
        lineas.append(f"Orden pendiente para la apertura: <b>{m.orden[0].upper()}</b>"
                      + (f" ({TXT_MOTIVO.get(m.orden[1], m.orden[1])})" if m.orden[0] in ("cerrar", "ambas") else ""))
    lineas.append(f"Papel en la historia: {_ops(nuc.trades_hist)}, neto {_usd(nuc.eq_hist)}.")
    lineas.append("Avisos: órdenes al cierre de cada hora (con el precio de papel en el mismo hilo), la puerta, los rolls, "
                  "la re-estimación diaria" + (" y la señal en curso." if cfg.aviso_en_curso else "."))
    return "\n".join(lineas)



# =============================================================================
# 20. LOG, REGISTRO EN CSV, CALENTAMIENTO Y LIVE DE ohlcv-1m
# =============================================================================
def configurar_log(carpeta: Path) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(errors="replace")
        except Exception:
            pass
    LOG.setLevel(logging.DEBUG)
    LOG.handlers.clear()
    LOG.propagate = False
    consola = logging.StreamHandler(sys.stdout)
    consola.setLevel(logging.INFO)
    consola.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))
    ruta = carpeta / f"coint_live_{time.strftime('%Y%m%d')}.log"
    archivo = logging.FileHandler(ruta, encoding="utf-8")
    archivo.setLevel(logging.DEBUG)
    archivo.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S"))
    LOG.addHandler(consola)
    LOG.addHandler(archivo)
    logging.getLogger("databento").setLevel(logging.WARNING)
    return ruta


class Registro:
    """En la carpeta de salidas: alertas_coint_<par>.csv (cada aviso), barras_coint_<par>_<día>.csv (una fila por
    barra cerrada en vivo), operaciones_coint_<par>.csv (cada operación de papel cerrada en vivo) y
    calendario_coint_<par>.csv (cada re-estimación en vivo)."""

    def __init__(self, carpeta: Path, par: str, zona: str):
        carpeta.mkdir(parents=True, exist_ok=True)
        self.carpeta, self.par, self.zona = carpeta, _nombre_seguro(par), zona

    def _escribir(self, ruta: Path, cabecera: list, fila: list) -> None:
        try:
            nuevo = not ruta.exists()
            with open(ruta, "a", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                if nuevo:
                    w.writerow(cabecera)
                w.writerow(fila)
        except OSError as e:
            LOG.warning(f"No se pudo escribir {ruta.name} ({e}). ¿Está abierto en Excel?")

    def _local(self, t_ns: int, formato: str = "%Y-%m-%d %H:%M:%S") -> str:
        return pd.Timestamp(int(t_ns), tz="UTC").tz_convert(self.zona).strftime(formato)

    def alerta(self, k: dict, nuc: "NucleoCoint") -> None:
        d = k["datos"]
        self._escribir(self.carpeta / f"alertas_coint_{self.par}.csv",
                       ["hora_local", "fase", "tipo", "detalle", "z", "precio_y", "precio_x", "texto"],
                       [self._local(k["t"]), k["fase"], k["tipo"], d.get("orden") or d.get("que") or d.get("motivo") or "",
                        _r(k["z"], 3) if _fin(k.get("z")) else None, k.get("cy"), k.get("cx"),
                        _plano(k["texto"]).replace("\n", " · ")])

    def barra(self, pt: dict, pnl: float, costos: float, nuc: "NucleoCoint") -> None:
        t = pt["t"] * MS
        self._escribir(self.carpeta / f"barras_coint_{self.par}_{self._local(t, '%Y%m%d')}.csv",
                       ["hora_local", "precio_y", "precio_x", "z", "beta", "beta_mco", "puerta", "z_in", "z_out", "pos",
                        "contratos_x", "pnl_usd", "costos_usd", "equity_usd", "valor_justo_y", "disparo_largo_y",
                        "disparo_corto_y"],
                       [self._local(t, "%Y-%m-%d %H:%M"), pt["c"], pt["cx"], _r(pt["z"], 4) if _fin(pt.get("z")) else None,
                        _r(pt["b"], 6) if _fin(pt.get("b")) else None, _r(pt["bo"], 6) if _fin(pt.get("bo")) else None,
                        pt["p"], pt["zi"], pt["zo"], pt["pos"], pt["nx"], round(pnl, 2), round(costos, 2),
                        round(pt["eq"], 2), _r(pt["fv"], 2) if _fin(pt.get("fv")) else None,
                        _r(pt["li"], 2) if _fin(pt.get("li")) else None, _r(pt["hi"], 2) if _fin(pt.get("hi")) else None])

    def operacion(self, tr: dict, nuc: "NucleoCoint") -> None:
        self._escribir(self.carpeta / f"operaciones_coint_{self.par}.csv",
                       ["entrada_local", "salida_local", "lado", "contratos_y", "contratos_x", "z_ent", "z_sal",
                        "beta_ent", "precio_y_ent", "precio_x_ent", "precio_y_sal", "precio_x_sal", "bruto_usd",
                        "costos_usd", "neto_usd", "horas", "motivo", "vida_media_ent_h", "mae_usd", "mfe_usd", "rolls"],
                       [self._local(tr["ts_ent"]), self._local(tr["ts_sal"]), LADO[tr["dir"]], tr["ny"], tr["nx"],
                        _r(tr["z_ent"], 3), _r(tr["z_sal"], 3) if _fin(tr.get("z_sal")) else None, _r(tr["beta_ent"], 6),
                        tr.get("real_y_ent"), tr.get("real_x_ent"), tr.get("real_y_sal"), tr.get("real_x_sal"),
                        round(tr["bruto"], 2), round(tr["costos"], 2), round(tr["neto"], 2), tr["horas"], tr["motivo"],
                        _r(tr["vm_ent"], 2) if _fin(tr.get("vm_ent")) else None, round(tr["mae"], 2), round(tr["mfe"], 2),
                        tr["rolls"]])

    def fila(self, fj: dict, nuc: "NucleoCoint") -> None:
        campos = [c for c in fj if c not in ("t", "rige", "fase")]
        self._escribir(self.carpeta / f"calendario_coint_{self.par}.csv", ["hora_local", "rige_desde", *campos],
                       [self._local(fj["t"] * MS), self._local(fj["rige"] * MS), *(fj[c] for c in campos)])


def preparar_live(nucleo: NucleoCoint, cfg: Config, cliente) -> int:
    """La historia reciente (al menos una ventana de formación) por el motor de la v3; devuelve el corte: desde ahí
    sigue el replay de Live."""
    nucleo.avisar("calentando", "Buscando hasta dónde llega el histórico…")
    fin = fin_historico(cliente, cfg, cfg.esquema).floor(f"{cfg.barra_min}min")
    dias = max(cfg.historia_dias, int(math.ceil(cfg.formacion_barras / 23 * 7 / 5)) + 7)
    ini = fin - pd.Timedelta(days=dias)
    crudas = descargar_calentamiento(cliente, cfg, ini, fin, avisar=lambda t: nucleo.avisar("calentando", t, log=False))
    if not len(crudas.get("y0", {}).get("ts", [])) or not len(crudas.get("x0", {}).get("ts", [])):
        sys.exit("Sin datos de alguna de las dos piernas: revisa los símbolos y el dataset.")
    nucleo.avisar("calentando", f"Recorriendo {dias} días de historia con el motor de la v3 (calibra cada "
                                f"{cfg.reestimar_cada} barras)…")
    t0 = time.perf_counter()
    nucleo.calentar(crudas)
    LOG.info(f"Historia lista en {time.perf_counter() - t0:.1f} s (hasta {fin.tz_convert(cfg.zona_local):%d-%m %H:%M}).")
    return int(fin.value)


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


def bucle_live(nucleo: NucleoCoint, cfg: Config, corte_ns: int, fabrica=None, detener: threading.Event | None = None,
               espera_base: float = 1.0, actual: dict | None = None) -> None:
    """ohlcv-1m de las cuatro series con replay desde lo último procesado. Se reconecta con espera creciente si se
    cae, con el piso que imponga el gateway si el replay pedido es demasiado viejo, y sin duplicados: cada serie
    descarta los minutos que ya procesó y el Agregador los de horas ya cerradas."""
    fabrica = fabrica or (lambda: db.Live(heartbeat_interval_s=cfg.heartbeat_s, slow_reader_behavior="warn"))
    detener = detener or threading.Event()
    actual = actual if actual is not None else {}
    simbolos = list(nucleo.sims.values())
    intentos = 0
    caida_avisada = False
    piso = 0
    while not detener.is_set():
        deseado = nucleo.desde_replay(corte_ns)
        start = max(deseado, time.time_ns() - int(cfg.replay_max_h * HORA_NS), piso)
        if start > deseado:
            nucleo.hueco(deseado, start)
        nucleo.avisar("conectando" if intentos == 0 else "reconectando",
                      f"Conectando a Databento Live (ohlcv-1m de {', '.join(simbolos)}; replay desde "
                      f"{_hora(start, cfg.zona_local)})…" if intentos == 0 else f"Reconectando (intento {intentos})…")
        motivo, recibio, fatal, inmediato = "Databento cerró la conexión", False, None, False
        cliente = None
        try:
            cliente = fabrica()
            actual["cliente"] = cliente
            cliente.subscribe(dataset=cfg.dataset, schema="ohlcv-1m", symbols=simbolos, stype_in=cfg.stype_in,
                              start=pd.Timestamp(start, tz="UTC"))
            nucleo.en_replay()
            for rec in cliente:
                nucleo.latido()
                if not recibio:
                    recibio = True
                    if caida_avisada:
                        caida_avisada = False
                        nucleo.notificar(f"🟢 Conexión con Databento recuperada · {nucleo._nombre_html()}. "
                                         "El replay rellena el corte: no faltan barras.", silencioso=True)
                if isinstance(rec, db.OHLCVMsg):
                    nucleo.ohlcv(rec)
                elif isinstance(rec, db.SymbolMappingMsg):
                    nucleo.mapeo(rec)
                elif isinstance(rec, db.SystemMsg):
                    if rec.is_heartbeat():
                        nucleo.reloj_datos(int(rec.ts_event), latido=True)
                    elif rec.code == SystemCode.REPLAY_COMPLETED:
                        nucleo.pasar_a_vivo("replay terminado")
                    elif rec.code == SystemCode.END_OF_INTERVAL:
                        nucleo.reloj_datos(int(rec.ts_event))
                    elif rec.code == SystemCode.SLOW_READER_WARNING:
                        LOG.warning(f"Databento: {rec.msg} (el script va atrasado)")
                    else:
                        LOG.debug(f"Databento: {rec.msg}")
                elif isinstance(rec, db.ErrorMsg):
                    LOG.error(f"Databento: {rec.err}")
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
                motivo = f"el replay de Live empieza en {_hora(p, cfg.zona_local)}"
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
            nucleo.avisar("error", f"Databento rechazó la conexión: {fatal}")
            nucleo.notificar(f"❌ <b>Cointegración Live detenido</b>: Databento rechazó la conexión ({html.escape(str(fatal))}).")
            LOG.error("Revisa tu API key y que tu plan incluya ohlcv-1m en vivo de " + cfg.dataset + ".\n" + AYUDA_KEY)
            return
        if detener.is_set():
            break
        if inmediato:
            LOG.info(f"Reconexión: {motivo}.")
            continue
        intentos = 1 if recibio else intentos + 1
        nucleo.reconexiones += 1
        espera = espera_base * min(30, 2 ** (intentos - 1))
        LOG.warning(f"Conexión perdida ({motivo}). Reintento en {espera:.0f} s…")
        if intentos == 3 and not caida_avisada:
            caida_avisada = True
            nucleo.notificar(f"🔴 <b>Sin conexión con Databento</b> · {nucleo._nombre_html()}\n{html.escape(motivo)}\n"
                             "Sigo reintentando; mientras tanto no hay órdenes ni avisos.")
        fin = time.monotonic() + espera
        while time.monotonic() < fin and not detener.is_set():
            time.sleep(min(0.2, max(0.0, fin - time.monotonic())))


# =============================================================================
# 21. DEMO: el mercado sintético de la v3, minuto a minuto (lo que llega por ohlcv-1m)
# =============================================================================
NOMBRES_DEMO = {"y": ["ESM6", "ESU6", "ESZ6", "ESH7"], "x": ["NQM6", "NQU6", "NQZ6", "NQH7"]}


def mercado_minutos(cfg: Config = CFG, semilla: int = 7, cointegrado: bool = True, sesiones: int | None = None,
                    ruptura: tuple | None = None, inicio: str | None = None) -> tuple:
    """El mercado de mercado_par (v3) —β verdadero que deriva, spread OU con vida media conocida y una RUPTURA,
    cointegración parcial, dos rolls con acarreo (NQ rola una sesión después) y las series .n.1— simulado cada
    MINUTO en vez de cada 5: las barras de 1 min son lo que manda Live, y las de 1 h salen de agregarlas.
    Devuelve (minutos por serie {y0, x0, y1, x1}, nombres de contrato por instrumento, verdad por hora)."""
    rng = np.random.default_rng(semilla)
    S = int(sesiones or cfg.sint_sesiones)
    ts_h = inicios_barras(inicio or cfg.sint_inicio, S, 60)
    n = ts_h.size
    sub = 60
    N = n * sub
    ts = (ts_h[:, None] + np.arange(sub, dtype=np.int64)[None, :] * MIN_NS).ravel()
    hora = np.tile(np.arange(23), S)
    perfil = np.where(hora < 9, 0.55, np.where(hora < 15, 0.85, 1.45))
    perfil = perfil / np.sqrt(np.mean(perfil ** 2))
    vol_sub = np.repeat(cfg.sint_vol_x_h * perfil, sub) / math.sqrt(sub)
    dx = rng.standard_normal(N) * vol_sub
    abre = np.zeros(N, bool)
    abre[::23 * sub] = True
    dx[abre] += rng.normal(0.0, 2.5 * cfg.sint_vol_x_h, abre.sum())
    lx = math.log(cfg.sint_precio_x) + np.cumsum(dx)
    beta = np.empty(N)
    b_ = cfg.sint_beta
    db_ = rng.standard_normal(N) * cfg.sint_sd_beta / math.sqrt(sub)
    for k in range(N):
        b_ += db_[k]
        b_ = 1.10 - b_ if b_ > 1.05 else (1.10 - b_ if b_ < 0.55 else b_)
        beta[k] = b_
    theta = math.log(2.0) / cfg.sint_vida_media_h
    phi_s = math.exp(-theta / sub)
    sd_s = cfg.sint_sd_spread * math.sqrt(1.0 - phi_s * phi_s)
    r0, r1 = ruptura if ruptura is not None else cfg.sint_ruptura
    ses = np.repeat(np.arange(S), 23 * sub)
    en_rup = (ses >= int(r0 * S)) & (ses < int(r1 * S)) if cointegrado else np.ones(N, bool)
    e = rng.standard_normal(N)
    m = np.empty(N)
    mk = 0.0
    for k in range(N):
        mk = (mk + 1.5 * sd_s * e[k]) if en_rup[k] else (phi_s * mk + sd_s * e[k])
        m[k] = mk
    w = np.cumsum(rng.standard_normal(N)) * cfg.sint_sd_paseo / math.sqrt(sub)
    ly = math.log(cfg.sint_precio_y) + beta * (lx - lx[0]) + m + w
    g_y, g_x = 0.0060, 0.0080
    rolls_y = [int(0.15 * S), int(0.64 * S)]
    rolls_x = [int(0.15 * S), int(0.64 * S) + 1]
    ses_m = np.repeat(np.arange(S), 23 * sub)
    nombres = {}

    def pierna(lp, rolls, g, base_id, tick, clave):
        P = np.exp(lp)
        o = np.r_[P[0], P[:-1]]
        ruido = np.abs(rng.normal(0.0, 0.15 * cfg.sint_vol_x_h / math.sqrt(sub), N)) * P
        hi, lo = np.maximum(o, P) + ruido, np.minimum(o, P) - ruido
        nro = np.searchsorted(np.array(rolls), ses_m, side="right")
        salida = []
        for extra in (0, 1):
            mult = (1.0 + g) ** (nro + extra)
            rd = lambda v: np.round(v * mult / tick) * tick  # noqa: E731
            vol = rng.integers(20, 900, N) // (1 + 9 * extra)
            salida.append({"ts": ts.copy(), "o": rd(o), "h": rd(hi), "l": rd(lo), "c": rd(P), "v": vol.astype(np.int64),
                           "iid": (base_id + nro + extra).astype(np.int64)})
        for j, nom in enumerate(NOMBRES_DEMO[clave]):
            nombres[base_id + j] = nom
        return salida
    y0, y1 = pierna(ly, rolls_y, g_y, 5001, cfg.tick_y, "y")
    x0, x1 = pierna(lx, rolls_x, g_x, 6001, cfg.tick_x, "x")
    fin = np.arange(sub - 1, N, sub)
    verdad = {"beta": beta[fin], "m": m[fin], "ruptura": en_rup[fin], "vida_media_h": cfg.sint_vida_media_h,
              "rolls_y": [int(ts_h[s * 23]) for s in rolls_y], "rolls_x": [int(ts_h[s * 23]) for s in rolls_x]}
    return {"y0": y0, "x0": x0, "y1": y1, "x1": x1}, nombres, verdad


def _msg_mapeo(sym: str, iid: int, nombre: str, ts: int):
    import databento_dbn as dbn
    return db.SymbolMappingMsg(publisher_id=1, instrument_id=int(iid), ts_event=int(ts), stype_in=dbn.SType.CONTINUOUS,
                               stype_in_symbol=sym, stype_out=dbn.SType.RAW_SYMBOL, stype_out_symbol=nombre,
                               start_ts=int(ts), end_ts=int(ts) + 86_400 * NS)


def _msg_ohlcv(iid: int, ts: int, o: float, h: float, l: float, c: float, v: int):
    import databento_dbn as dbn
    px = lambda p: int(round(float(p) * 1e9))  # noqa: E731
    return db.OHLCVMsg(rtype=dbn.RType.OHLCV_1M, publisher_id=1, instrument_id=int(iid), ts_event=int(ts), open=px(o),
                       high=px(h), low=px(l), close=px(c), volume=int(v))


def recortar_minutos(crudas: dict, desde: int | None = None, hasta: int | None = None) -> dict:
    out = {}
    for s, v in crudas.items():
        m = np.ones(len(v["ts"]), bool)
        if desde is not None:
            m &= v["ts"] >= desde
        if hasta is not None:
            m &= v["ts"] < hasta
        out[s] = {c: a[m] for c, a in v.items()}
    return out


def mensajes_minutos(crudas: dict, sims: dict, nombres: dict) -> list:
    """Lo que mandaría Live para esos minutos: un SymbolMappingMsg al empezar y en cada roll, y un OHLCVMsg por
    minuto y serie, en orden de tiempo (DBN de verdad, los mismos objetos que da el cliente de Databento)."""
    filas = []
    for orden_s, (s, v) in enumerate(crudas.items()):
        for j in range(len(v["ts"])):
            filas.append((int(v["ts"][j]), orden_s, s, j))
    filas.sort()
    previo: dict = {}
    salida = []
    for ts, _, s, j in filas:
        v = crudas[s]
        iid = int(v["iid"][j])
        if previo.get(s) != iid:
            salida.append(_msg_mapeo(sims[s], iid, nombres.get(iid, str(iid)), ts))
            previo[s] = iid
        salida.append(_msg_ohlcv(iid, ts, v["o"][j], v["h"][j], v["l"][j], v["c"][j], v["v"][j]))
    return salida


def reproducir(nucleo: NucleoCoint, msgs: list, reloj: dict, detener: threading.Event | None = None,
               velocidad: float | None = None, espera_max: float = 0.25, hasta: int | None = None, al_minuto=None) -> int | None:
    """Pasa mensajes de Live al núcleo como llegarían: el reloj va al final de cada minuto y, en las pausas de CME, un
    heartbeat cierra la última hora. Con `velocidad` espera entre minutos (None: tan rápido como pueda)."""
    siguiente = time.monotonic()
    ult = None
    for rec in msgs:
        if detener is not None and detener.is_set():
            break
        if isinstance(rec, db.SymbolMappingMsg):
            nucleo.mapeo(rec)
            continue
        ts = int(rec.ts_event)
        if hasta is not None and ts >= hasta:
            break
        if ts != ult:
            if ult is not None:
                if ts - ult > MIN_NS:
                    reloj["t"] = ult + 2 * MIN_NS
                    nucleo.latido()
                    nucleo.reloj_datos(reloj["t"], latido=True)
                if velocidad:
                    siguiente += 60.0 / velocidad
                    espera = siguiente - time.monotonic()
                    if espera > 0:
                        (detener.wait if detener is not None else time.sleep)(min(espera, espera_max))
                    else:
                        siguiente = time.monotonic()
            if al_minuto is not None:
                al_minuto(ts)
            ult = ts
            reloj["t"] = ts + MIN_NS
        nucleo.latido()
        nucleo.ohlcv(rec)
    return ult


def correr_demo(nucleo: NucleoCoint, cfg: Config, detener: threading.Event, velocidad: float = 3600.0,
                sesiones_cal: int = 32, semilla: int = 1, horas: float | None = None, espera_max: float = 0.25) -> None:
    """Calienta con las primeras `sesiones_cal` sesiones (en barras de 1 h, como el histórico) y sigue minuto a minuto
    con el reloj `velocidad` veces más rápido (3600: una hora de mercado por segundo). El camino es el de Live:
    SymbolMappingMsg y OHLCVMsg → Agregador → UnirVivo → MotorPar → órdenes y avisos. El par tiene una ruptura y un
    roll por delante: la puerta se cierra, se reabre y el roll se ajusta en vivo."""
    hoy = pd.Timestamp.now(tz=TZ_CME).tz_localize(None).normalize()
    inicio = (hoy - pd.offsets.BDay(sesiones_cal)).strftime("%Y-%m-%d")
    crudas, nombres, _ = mercado_minutos(cfg, semilla=semilla, inicio=inicio)
    nucleo.modo = "demo"
    corte = int(crudas["y0"]["ts"][sesiones_cal * 23 * 60])
    reloj = {"t": corte}
    nucleo.reloj = lambda: reloj["t"]
    nucleo.avisar("calentando", f"DEMO: calentando con {sesiones_cal} sesiones del par sintético de la v3…")
    hist = recortar_minutos(crudas, hasta=corte)
    nucleo.calentar({s: agregar_barras(v, cfg.barra_min) for s, v in hist.items()})
    for s_, iid in ((s_, int(v["iid"][-1])) for s_, v in hist.items() if len(v["ts"])):
        nucleo.mapeo(_msg_mapeo(nucleo.sims[s_], iid, nombres.get(iid, str(iid)), corte))
    msgs = mensajes_minutos(recortar_minutos(crudas, desde=corte), nucleo.sims, nombres)
    nucleo.en_replay()
    nucleo.pasar_a_vivo("demo")
    LOG.info(f"DEMO: par sintético de la v3 (β que deriva, spread OU de {cfg.sint_vida_media_h:g} h con una ruptura, rolls "
             f"con acarreo), {len(msgs):,} mensajes de 1 min; reloj ×{velocidad:g}.")
    hasta = corte + int(horas * HORA_NS) if horas is not None else None
    ult = reproducir(nucleo, msgs, reloj, detener, velocidad=velocidad, espera_max=espera_max, hasta=hasta)
    if ult is not None and not (detener.is_set() or hasta is not None):
        reloj["t"] = ult + 2 * MIN_NS
        nucleo.reloj_datos(reloj["t"], latido=True)
    LOG.info("DEMO terminada: el tablero sigue abierto (Ctrl+C para salir).")



# =============================================================================
# 22. TABLERO WEB (el servidor es el de los otros indicadores)
# =============================================================================
TABLERO_HTML = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cointegración Live</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%2310151e'/%3E%3Cpath d='M4 20 C9 12 13 24 18 14 S25 10 28 16' fill='none' stroke='%2338bdf8' stroke-width='2.4'/%3E%3Cpath d='M4 17 C9 9 13 21 18 11 S25 7 28 13' fill='none' stroke='%23f5b301' stroke-width='1.6'/%3E%3C/svg%3E">
<script src="https://cdn.jsdelivr.net/npm/lightweight-charts@5.0.8/dist/lightweight-charts.standalone.production.js"></script>
<style>
:root{
  --bg:#0a0d13; --panel:#10151e; --panel2:#0c1119; --line:#1d2531; --grid:#151b25;
  --text:#e6e9ef; --muted:#8b95a7; --dim:#5a6477;
  --up:#26a69a; --down:#ef5350; --warn:#f5b301; --ok:#22c55e; --bad:#ef4444; --info:#38bdf8; --acento:#a78bfa;
  --largo:#22c55e; --corto:#ef4444; --justo:#f5b301; --beta:#38bdf8;
  --radio:10px; --mono:"Cascadia Mono","JetBrains Mono",Consolas,ui-monospace,monospace; color-scheme:dark;
}
:root[data-theme="light"]{
  --bg:#f4f5f7; --panel:#ffffff; --panel2:#f8f9fb; --line:#e2e5ea; --grid:#eef0f3;
  --text:#0f172a; --muted:#5b6475; --dim:#98a1b0; --up:#089981; --down:#e5484d; --warn:#c98a00; --ok:#16a34a; --bad:#dc2626; --info:#0284c7; --acento:#7c3aed;
  --largo:#16a34a; --corto:#dc2626; --justo:#b77900; --beta:#0284c7; color-scheme:light;
}
*{box-sizing:border-box} html,body{margin:0}
body{background:var(--bg);color:var(--text);font:13px/1.45 system-ui,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;-webkit-font-smoothing:antialiased}
.num{font-family:var(--mono);font-variant-numeric:tabular-nums} .tenue{color:var(--muted)} .sube{color:var(--up)} .baja{color:var(--down)}
.cl{color:var(--largo)} .cc{color:var(--corto)} .cj{color:var(--justo)} .ci{color:var(--info)} .cw{color:var(--warn)}
button{font:inherit;color:var(--text);background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:6px 11px;cursor:pointer}
button:hover{border-color:var(--dim)} button[aria-pressed="true"]{border-color:var(--warn);color:var(--warn)} a{color:var(--info)}
.cabecera{position:sticky;top:0;z-index:5;display:flex;align-items:center;gap:16px;flex-wrap:wrap;padding:10px 16px;background:color-mix(in srgb,var(--bg) 88%,transparent);backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}
.id{display:flex;align-items:center;gap:10px;min-width:0}
.logo{width:30px;height:30px;border-radius:8px;background:var(--panel);border:1px solid var(--line);display:grid;place-items:center} .logo svg{width:20px;height:20px}
.titulo{font-weight:650;font-size:15px} .subtitulo{color:var(--muted);font-size:11.5px}
.pill{display:inline-flex;align-items:center;gap:7px;padding:4px 11px;border-radius:999px;border:1px solid var(--line);font-size:11px;font-weight:700;letter-spacing:.07em;white-space:nowrap}
.pill i{width:8px;height:8px;border-radius:50%;background:var(--dim)}
.pill[data-e="vivo"],.pill[data-e="demo"]{border-color:color-mix(in srgb,var(--ok) 55%,transparent);color:var(--ok)}
.pill[data-e="vivo"] i,.pill[data-e="demo"] i{background:var(--ok);animation:latido 1.6s infinite}
.pill[data-e="replay"],.pill[data-e="conectando"],.pill[data-e="calentando"],.pill[data-e="iniciando"]{border-color:color-mix(in srgb,var(--info) 55%,transparent);color:var(--info)}
.pill[data-e="replay"] i,.pill[data-e="conectando"] i,.pill[data-e="calentando"] i,.pill[data-e="iniciando"] i{background:var(--info);animation:latido 1s infinite}
.pill[data-e="reconectando"],.pill[data-e="sin_datos"],.pill[data-e="error"],.pill[data-e="desconectado"]{border-color:color-mix(in srgb,var(--bad) 60%,transparent);color:var(--bad)}
.pill[data-e="reconectando"] i,.pill[data-e="sin_datos"] i,.pill[data-e="error"] i,.pill[data-e="desconectado"] i{background:var(--bad)}
.pill[data-e="cerrado"],.pill[data-e="detenido"]{color:var(--muted)}
@keyframes latido{0%{box-shadow:0 0 0 0 color-mix(in srgb,currentColor 60%,transparent)}70%{box-shadow:0 0 0 7px transparent}100%{box-shadow:0 0 0 0 transparent}}
.insignia{display:inline-flex;align-items:center;gap:9px;padding:6px 13px;border-radius:10px;font-weight:800;font-size:13.5px;letter-spacing:.04em;border:1px solid var(--line);white-space:nowrap}
.insignia small{font-weight:600;font-size:11.5px;letter-spacing:0;color:var(--muted)}
.insignia[data-s="1"]{color:var(--largo);border-color:color-mix(in srgb,var(--largo) 60%,transparent);background:color-mix(in srgb,var(--largo) 9%,transparent)}
.insignia[data-s="-1"]{color:var(--corto);border-color:color-mix(in srgb,var(--corto) 60%,transparent);background:color-mix(in srgb,var(--corto) 9%,transparent)}
.insignia[data-s="2"]{color:var(--warn);border-color:color-mix(in srgb,var(--warn) 60%,transparent);background:color-mix(in srgb,var(--warn) 9%,transparent)}
.insignia[data-s="0"]{color:var(--muted)}
.precio{display:flex;align-items:baseline;gap:8px} #hZ{font-size:22px;font-weight:650}
.relojes{display:flex;gap:14px;align-items:baseline;margin-left:auto} .botones{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.aviso{margin:12px 16px 0;padding:9px 13px;border-radius:8px;border:1px solid color-mix(in srgb,var(--info) 40%,var(--line));background:color-mix(in srgb,var(--info) 8%,var(--panel))}
.aviso[data-tipo="malo"]{border-color:color-mix(in srgb,var(--bad) 50%,var(--line));background:color-mix(in srgb,var(--bad) 8%,var(--panel))}
main{padding:14px 16px 8px;display:grid;gap:14px}
.kpis{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:12px}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:var(--radio);padding:12px 14px 13px;min-width:0;position:relative;overflow:hidden}
.kpi::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--k,transparent)}
.kpi h3{margin:0 0 5px;font-size:10.5px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;color:var(--muted)}
.valor{font-size:21px;font-weight:650;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.valor small{font-size:12px;font-weight:600;color:var(--muted);margin-left:6px}
.valor.chico{font-size:17px;line-height:1.45} .valor.chico small{margin:0 4px}
.nota{margin-top:6px;color:var(--muted);font-size:11.5px} .nota b{color:var(--text);font-weight:600}
.barra{position:relative;height:8px;border-radius:4px;background:var(--grid);margin-top:9px;overflow:visible}
.barra .zona{position:absolute;top:0;bottom:0}
.barra .marca{position:absolute;top:-3px;width:2px;height:14px;border-radius:1px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:var(--radio);min-width:0}
.panel-cab{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 14px;border-bottom:1px solid var(--line);flex-wrap:wrap}
.panel-cab h2{margin:0;font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.leyenda{font-size:11.5px;color:var(--muted);margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%} .leyenda b{color:var(--text)}
.claves{display:flex;gap:12px;flex-wrap:wrap;font-size:11px;color:var(--muted)} .claves span{display:inline-flex;align-items:center;gap:5px} .claves i{width:10px;height:3px;border-radius:2px}
.lienzo{position:relative} .lienzo canvas{display:block;width:100%}
#cCurva{height:330px}
#grafica{height:clamp(560px,74vh,860px)}
.cont-grafica{position:relative}
.etq-paneles{position:absolute;inset:0;pointer-events:none;z-index:2;display:none} .etq-paneles.visible{display:block}
.etq-paneles span{position:absolute;left:10px;font-size:10.5px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;color:var(--muted);background:color-mix(in srgb,var(--panel) 80%,transparent);padding:1px 5px;border-radius:4px}
.globo{position:absolute;pointer-events:none;z-index:4;background:color-mix(in srgb,var(--panel) 94%,transparent);border:1px solid var(--line);border-radius:8px;padding:6px 9px;font-size:11.5px;white-space:nowrap;display:none;box-shadow:0 4px 18px rgba(0,0,0,.25)}
.fila2{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:14px}
.scroll{max-height:390px;overflow:auto}
table{width:100%;border-collapse:collapse;font-size:12px}
th{position:sticky;top:0;background:var(--panel);color:var(--muted);font-weight:600;font-size:11px;text-align:right;padding:7px 8px;border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:6px 8px;border-bottom:1px solid var(--grid);text-align:right;white-space:nowrap;font-family:var(--mono);font-variant-numeric:tabular-nums}
th:first-child,td:first-child{text-align:left} tbody tr:hover td{background:var(--panel2)} td.vacio{text-align:center;color:var(--muted);padding:22px;font-family:inherit}
td.txt{text-align:left;font-family:inherit;white-space:normal;min-width:280px}
td.nom{font-family:inherit}
tr.grupo td{color:var(--muted);font-family:inherit;font-weight:600;background:var(--panel2)}
tr.nuevo td{animation:brillo 2.5s ease-out}
@keyframes brillo{0%{background:color-mix(in srgb,var(--warn) 25%,transparent)}100%{background:transparent}}
.etq{display:inline-block;margin-left:5px;padding:0 5px;border-radius:4px;font-size:10px;font-family:system-ui,sans-serif;color:var(--muted);border:1px solid var(--line)}
.tipo{display:inline-block;padding:0 6px;border-radius:4px;font-size:10.5px;font-family:system-ui,sans-serif;font-weight:700;border:1px solid var(--line)}
.si{color:var(--ok);font-weight:700} .no{color:var(--bad);font-weight:700}
.nota-panel{padding:8px 14px 12px;font-size:11.5px;color:var(--muted)} .nota-panel b{color:var(--text)}
.resumen{font-size:11.5px;color:var(--muted)} .resumen b{color:var(--text)}
.pie{padding:4px 16px 18px;color:var(--muted);font-size:11.5px;line-height:1.7} .pie b{color:var(--text);font-weight:600}
@media (max-width:1320px){.kpis{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media (max-width:1100px){.fila2{grid-template-columns:minmax(0,1fr)}}
@media (max-width:720px){.kpis{grid-template-columns:repeat(2,minmax(0,1fr))} .relojes{margin-left:0} .cabecera{position:static} #grafica{height:640px}}
@media (max-width:420px){.kpis{grid-template-columns:minmax(0,1fr)}}
</style>
</head>
<body>
<header class="cabecera">
  <div class="id">
    <span class="logo" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M2 15 C6 8 9 18 13 10 S19 6 22 12" fill="none" stroke="#38bdf8" stroke-width="2"/><path d="M2 12 C6 5 9 15 13 7 S19 3 22 9" fill="none" stroke="#f5b301" stroke-width="1.3"/></svg></span>
    <div>
      <div class="titulo">Cointegración · <span id="hPar">—</span> <span id="hCont" class="tenue"></span></div>
      <div class="subtitulo">Kalman · prueba estricta · órdenes de papel · <span id="hFuente">Databento ohlcv-1m</span></div>
    </div>
  </div>
  <span id="hEstado" class="pill" data-e="iniciando"><i></i><b>INICIANDO</b></span>
  <span id="hPuerta" class="insignia" data-s="0"><span>PUERTA —</span><small id="hPuertaNota"></small></span>
  <span id="hPos" class="insignia" data-s="0"><span>PLANO</span><small id="hPosNota"></small></span>
  <div class="precio"><span class="tenue">z</span><span id="hZ" class="num">—</span><span id="hZp" class="num tenue"></span></div>
  <div class="relojes"><span id="hRetraso" class="num tenue"></span><span id="hReloj" class="num"></span></div>
  <div class="botones"><button id="bSonido" type="button" aria-pressed="false">Sonido: no</button><button id="bTema" type="button">Tema</button></div>
</header>
<div id="aviso" class="aviso" hidden></div>
<main>
  <section class="kpis">
    <article class="kpi" id="kZ"><h3>z del spread</h3><div class="valor num" id="vZ">—</div><div class="nota" id="nZ">—</div><div class="barra" id="bZ"></div></article>
    <article class="kpi" style="--k:var(--justo)"><h3 id="tDisp">Precios de disparo</h3><div class="valor num chico" id="vDisp">—</div><div class="nota" id="nDisp">—</div></article>
    <article class="kpi" style="--k:var(--beta)"><h3>Hedge ratio (Kalman)</h3><div class="valor num" id="vBeta">—</div><div class="nota" id="nBeta">—</div></article>
    <article class="kpi" id="kPuerta"><h3>Cointegración · la puerta</h3><div class="valor" id="vPuerta">—</div><div class="nota" id="nPuerta">—</div></article>
    <article class="kpi" id="kPos"><h3>Posición de papel</h3><div class="valor num" id="vPos">—</div><div class="nota" id="nPos">—</div></article>
    <article class="kpi" style="--k:var(--acento)"><h3>P&amp;L de papel</h3><div class="valor num" id="vPnl">—</div><div class="nota" id="nPnl">—</div></article>
  </section>
  <section class="panel">
    <div class="panel-cab"><div style="min-width:0;flex:1"><h2 id="tGrafica">El par, hora a hora</h2><div id="leyenda" class="leyenda num">—</div></div>
      <div class="claves"><span><i style="background:var(--justo)"></i>valor justo por X (z = 0)</span><span><i style="background:var(--corto)"></i>disparo corto</span><span><i style="background:var(--largo)"></i>disparo largo</span><span><i style="background:var(--dim)"></i>puerta cerrada</span><span><i style="background:var(--beta)"></i>β Kalman</span></div>
      <div class="botones"><button id="b10" type="button">Últimos 10 días</button><button id="bTodo" type="button">Todo</button></div></div>
    <div class="cont-grafica"><div id="grafica"></div>
      <div class="etq-paneles" id="etqPaneles" aria-hidden="true"><span id="etq0">Y · su valor justo por X y los precios de disparo</span><span>z del spread filtrado · umbrales (zona gris: puerta cerrada)</span><span>Hedge ratio β: Kalman (línea) y MCO de la ventana (escalones)</span><span>P&amp;L de papel acumulado (US$, con costos)</span></div></div>
  </section>
  <section class="fila2">
    <div class="panel"><div class="panel-cab"><h2>La puerta: lo que pide la prueba</h2><span class="resumen" id="resLista"></span></div>
      <div class="scroll"><table><thead><tr><th>Prueba</th><th>Valor</th><th>Exige</th><th>Pasa</th></tr></thead><tbody id="tbLista"></tbody></table></div>
      <div class="nota-panel" id="nLista"></div></div>
    <div class="panel"><div class="panel-cab"><div style="min-width:0;flex:1"><h2>Umbral óptimo con costos (Bertram)</h2><div class="leyenda" id="lCurva">Ganancia esperada por hora de un OU con los costos de la unidad, para cada salida.</div></div></div>
      <div class="lienzo"><canvas id="cCurva"></canvas><div class="globo" id="gCurva"></div></div>
      <div class="nota-panel" id="nCurva"></div></div>
  </section>
  <section class="fila2">
    <div class="panel"><div class="panel-cab"><h2>Operaciones de papel</h2><span class="resumen" id="resTr"></span></div>
      <div class="scroll"><table><thead><tr><th>Entrada</th><th>Lado</th><th>Contratos</th><th>z ent → sal</th><th>Horas</th><th>Bruto</th><th>Costos</th><th>Neto</th><th>Salida</th></tr></thead><tbody id="tbTr"></tbody></table></div></div>
    <div class="panel"><div class="panel-cab"><h2>Auditoría de papel (la de la v3)</h2><span class="resumen" id="resAud"></span></div>
      <div class="scroll"><table><thead><tr><th>Métrica</th><th>Historia + vivo</th><th>Solo en vivo</th></tr></thead><tbody id="tbAud"></tbody></table></div>
      <div class="nota-panel" id="nAud"></div></div>
  </section>
  <section class="fila2">
    <div class="panel"><div class="panel-cab"><h2>Re-estimaciones (walk-forward)</h2><span class="resumen" id="resFil"></span></div>
      <div class="scroll"><table><thead><tr><th>Hora</th><th>Puerta</th><th>EG y~x</th><th>EG x~y</th><th>ADF spread</th><th>Vida media</th><th>β MCO</th><th>Umbral</th><th>US$/h</th></tr></thead><tbody id="tbFil"></tbody></table></div>
      <div class="nota-panel" id="nFil"></div></div>
    <div class="panel"><div class="panel-cab"><h2>Avisos</h2><span class="resumen" id="resAl"></span></div>
      <div class="scroll"><table><thead><tr><th>Hora</th><th>Tipo</th><th>z</th><th>Detalle</th></tr></thead><tbody id="tbAl"></tbody></table></div></div>
  </section>
</main>
<footer class="pie" id="pie"></footer>
<script>
(() => {
'use strict';
const $ = (id) => document.getElementById(id);
const LW = window.LightweightCharts;
const S = { cfg: null, serie: [], idx: new Map(), marcas: [], al: [], filas: [], trades: [], audit: {}, curva: {}, lista: {}, tick: null, conectado: false, sonido: false, audio: null, vistos: new Set(), primero: true, pintado: 0 };
const ESTADOS = { iniciando: 'INICIANDO', calentando: 'CALENTANDO', conectando: 'CONECTANDO', replay: 'REPLAY', vivo: 'EN VIVO', reconectando: 'RECONECTANDO', cerrado: 'MERCADO CERRADO', sin_datos: 'SIN DATOS', detenido: 'DETENIDO', error: 'ERROR', demo: 'DEMO · SIMULADO', desconectado: 'SIN CONEXIÓN' };
const LADO = { '1': 'LARGO spread', '-1': 'CORTO spread' };
const MOTIVO = { objetivo: 'objetivo', stop_z: 'stop de z', stop_tiempo: 'stop de tiempo', ruptura: 'ruptura', fin: 'fin' };
const esNum = (x) => typeof x === 'number' && isFinite(x);
function num(x, d = 0) { return esNum(x) ? x.toLocaleString('es-MX', { minimumFractionDigits: d, maximumFractionDigits: d }) : '—'; }
function sgn(x, d = 0) { if (!esNum(x)) return '—'; const r = num(Math.abs(x), d); return (r === num(0, d) ? '' : x > 0 ? '+' : '−') + r; }
function usd(x, firma = true) { if (!esNum(x)) return '—'; const s = firma ? (x > 0 ? '+' : x < 0 ? '−' : '') : (x < 0 ? '−' : ''); return s + 'US$ ' + num(Math.abs(x)); }
function pY(x) { return num(x, S.cfg ? S.cfg.dec_y : 2); }
function pX(x) { return num(x, S.cfg ? S.cfg.dec_x : 2); }
function zf(x) { return esNum(x) ? sgn(x, 2) : '—'; }
function pv(x) { return esNum(x) ? (x < 0.001 ? '<0.001' : num(x, 3)) : '—'; }
function vm(x) { return esNum(x) ? (x > 1e4 ? '∞' : num(x, 1) + ' h') : '—'; }
function vmc(x) { return esNum(x) ? (x > 1e4 ? '∞' : num(x, 0)) : '—'; }
function pct(x, d = 0) { return esNum(x) ? num(100 * x, d) + ' %' : '—'; }
function css(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
function alfa(c, a) { c = (c || '').trim(); if (!c.startsWith('#')) return c; const n = parseInt(c.slice(1), 16); return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`; }
function esc(t) { return String(t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]); }
function lado(d) { return d > 0 ? '<span class="cl">LARGO</span>' : '<span class="cc">CORTO</span>'; }
let F = null;
function formatos(tz) { const b = { timeZone: tz, hourCycle: 'h23' }; F = { tz, hm: new Intl.DateTimeFormat('es-MX', { ...b, hour: '2-digit', minute: '2-digit' }), hms: new Intl.DateTimeFormat('es-MX', { ...b, hour: '2-digit', minute: '2-digit', second: '2-digit' }), dhm: new Intl.DateTimeFormat('es-MX', { ...b, weekday: 'short', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }), dm: new Intl.DateTimeFormat('es-MX', { timeZone: tz, day: '2-digit', month: 'short' }) }; }
formatos('America/Mexico_City');
function aviso(t, malo) { const a = $('aviso'); if (t) { a.textContent = t; a.dataset.tipo = malo ? 'malo' : ''; a.hidden = false; } else a.hidden = true; }
function lienzo(c) { const dpr = window.devicePixelRatio || 1; const r = c.getBoundingClientRect(); const w = Math.max(20, r.width), h = Math.max(20, r.height); if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) { c.width = Math.round(w * dpr); c.height = Math.round(h * dpr); } const x = c.getContext('2d'); x.setTransform(dpr, 0, 0, dpr, 0, 0); x.clearRect(0, 0, w, h); x.font = '11px ' + getComputedStyle(document.body).fontFamily; return { x, w, h }; }
function globo(el, html, ex, ey, cont) { if (!html) { el.style.display = 'none'; return; } el.innerHTML = html; el.style.display = 'block'; const r = cont.getBoundingClientRect(); const bw = el.offsetWidth, bh = el.offsetHeight; let l = ex + 14, t = ey + 12; if (l + bw > r.width) l = ex - bw - 14; if (t + bh > r.height) t = ey - bh - 12; el.style.left = Math.max(0, l) + 'px'; el.style.top = Math.max(0, t) + 'px'; }
function ultimo() { const t = S.tick || {}; return t.prov && esNum(t.prov.z) ? t.prov : t.ult; }
function indexar() { S.idx = new Map(S.serie.map((p) => [p.t, p])); }

// ---------------- la gráfica (lightweight-charts, 4 paneles) ----------------
let G = null;
function crearGrafica() {
  if (!LW || !LW.createChart) return null;
  const cont = $('grafica');
  const fUsd = { type: 'custom', minMove: 1, formatter: (v) => usd(v) };
  const fZ = { type: 'custom', minMove: 0.01, formatter: (v) => sgn(v, 2) };
  const fB = { type: 'custom', minMove: 0.0001, formatter: (v) => num(v, 4) };
  const chart = LW.createChart(cont, { autoSize: true, layout: { background: { type: 'solid', color: 'transparent' }, fontSize: 11, fontFamily: getComputedStyle(document.body).fontFamily, panes: { enableResize: true } },
    rightPriceScale: { borderVisible: false, minimumWidth: 86 }, timeScale: { borderVisible: false, rightOffset: 4, barSpacing: 5, minBarSpacing: 0.4, timeVisible: true, secondsVisible: false, tickMarkFormatter: (t, tipo) => { const ms = t * 1000; return tipo <= 2 ? F.dm.format(ms) : F.hm.format(ms); } },
    localization: { locale: 'es-MX', timeFormatter: (t) => F.dhm.format(t * 1000) }, crosshair: { mode: LW.CrosshairMode.Normal } });
  const lin = (o, p) => chart.addSeries(LW.LineSeries, { priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false, ...o }, p);
  const velas = chart.addSeries(LW.CandlestickSeries, { borderVisible: false, priceLineVisible: true, priceLineStyle: LW.LineStyle.Dotted }, 0);
  const fuera = { autoscaleInfoProvider: () => null };     // las velas mandan en la escala
  const justo = lin({ lineWidth: 2, lineStyle: LW.LineStyle.Solid, ...fuera }, 0);
  const dHi = lin({ lineWidth: 1, lineStyle: LW.LineStyle.Dashed, ...fuera }, 0);
  const dLo = lin({ lineWidth: 1, lineStyle: LW.LineStyle.Dashed, ...fuera }, 0);
  const puerta = chart.addSeries(LW.AreaSeries, { priceScaleId: 'puerta', lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false, lineWidth: 1, lineType: LW.LineType.WithSteps, lineColor: 'rgba(0,0,0,0)', autoscaleInfoProvider: () => ({ priceRange: { minValue: 0, maxValue: 1 } }) }, 1);
  puerta.priceScale().applyOptions({ scaleMargins: { top: 0, bottom: 0 } });
  const zS = chart.addSeries(LW.LineSeries, { lineWidth: 2, priceLineVisible: false, priceFormat: fZ }, 1);
  const ziP = lin({ lineWidth: 1, lineStyle: LW.LineStyle.Dashed, lineType: LW.LineType.WithSteps, priceFormat: fZ }, 1);
  const ziN = lin({ lineWidth: 1, lineStyle: LW.LineStyle.Dashed, lineType: LW.LineType.WithSteps, priceFormat: fZ }, 1);
  const zoP = lin({ lineWidth: 1, lineStyle: LW.LineStyle.Dotted, lineType: LW.LineType.WithSteps, priceFormat: fZ }, 1);
  const zoN = lin({ lineWidth: 1, lineStyle: LW.LineStyle.Dotted, lineType: LW.LineType.WithSteps, priceFormat: fZ }, 1);
  const beta = chart.addSeries(LW.LineSeries, { lineWidth: 2, priceLineVisible: false, priceFormat: fB }, 2);
  const betaO = lin({ lineWidth: 1, lineStyle: LW.LineStyle.Dashed, lineType: LW.LineType.WithSteps, priceFormat: fB }, 2);
  const eq = chart.addSeries(LW.BaselineSeries, { baseValue: { type: 'price', price: 0 }, lineWidth: 2, priceLineVisible: false, priceFormat: fUsd }, 3);
  const mVelas = LW.createSeriesMarkers ? LW.createSeriesMarkers(velas, []) : null;
  const mZ = LW.createSeriesMarkers ? LW.createSeriesMarkers(zS, []) : null;
  let lineasZ = [], primera = true, decs = -1;
  const T = (p) => p.t / 1000;
  const v = (t, x) => (esNum(x) ? { time: t, value: x } : { time: t });
  // el valor justo y los disparos solo con la puerta abierta (en una ruptura el filtro pierde la reversión y se van lejos)
  const nivel = (p, x) => (p.p && esNum(x) && Math.abs(x / p.c - 1) < 0.08 ? x : null);
  function tema() { const c = { texto: css('--muted'), rejilla: css('--grid'), borde: css('--line'), dim: css('--dim') };
    chart.applyOptions({ layout: { textColor: c.texto, panes: { separatorColor: c.borde } }, grid: { vertLines: { color: c.rejilla }, horzLines: { color: c.rejilla } }, crosshair: { vertLine: { color: alfa(c.texto, 0.5), labelBackgroundColor: c.dim }, horzLine: { color: alfa(c.texto, 0.5), labelBackgroundColor: c.dim } } });
    velas.applyOptions({ upColor: css('--up'), downColor: css('--down'), wickUpColor: css('--up'), wickDownColor: css('--down'), priceLineColor: c.dim });
    justo.applyOptions({ color: alfa(css('--justo'), 0.9) }); dHi.applyOptions({ color: css('--corto') }); dLo.applyOptions({ color: css('--largo') });
    zS.applyOptions({ color: css('--text') }); ziP.applyOptions({ color: css('--corto') }); ziN.applyOptions({ color: css('--largo') }); zoP.applyOptions({ color: c.dim }); zoN.applyOptions({ color: c.dim });
    beta.applyOptions({ color: css('--beta') }); betaO.applyOptions({ color: c.dim });
    puerta.applyOptions({ topColor: alfa(css('--dim'), 0.2), bottomColor: alfa(css('--dim'), 0.2) });
    eq.applyOptions({ topLineColor: css('--largo'), topFillColor1: alfa(css('--largo'), 0.28), topFillColor2: alfa(css('--largo'), 0.03), bottomLineColor: css('--corto'), bottomFillColor1: alfa(css('--corto'), 0.03), bottomFillColor2: alfa(css('--corto'), 0.28) });
    if (S.cfg) cargar(false); }
  const cerrada = (p) => (p.p ? 0 : 1);
  function vela(p) { const d = { time: T(p), open: p.o, high: p.h, low: p.l, close: p.c }; if (p.prov) { const c = alfa(p.c >= p.o ? css('--up') : css('--down'), 0.45); d.color = c; d.wickColor = c; } return d; }
  function poner(p, metodo) { const t = T(p);
    velas[metodo](vela(p)); justo[metodo](v(t, nivel(p, p.fv))); dHi[metodo](v(t, nivel(p, p.hi))); dLo[metodo](v(t, nivel(p, p.li)));
    puerta[metodo]({ time: t, value: cerrada(p) }); zS[metodo](v(t, p.z)); ziP[metodo](v(t, p.zi)); ziN[metodo](v(t, esNum(p.zi) ? -p.zi : null));
    zoP[metodo](v(t, p.zo)); zoN[metodo](v(t, esNum(p.zo) ? -p.zo : null)); beta[metodo](v(t, p.b)); betaO[metodo](v(t, p.bo)); eq[metodo]({ time: t, value: p.eq }); }
  function cargar(encuadrar) {
    if (S.cfg && decs !== S.cfg.dec_y) { decs = S.cfg.dec_y; const f = { type: 'price', precision: decs, minMove: Math.pow(10, -decs) }; [velas, justo, dHi, dLo].forEach((s) => s.applyOptions({ priceFormat: f })); }
    const L = S.serie; const col = { V: [], J: [], H: [], Lo: [], P: [], Z: [], ZP: [], ZN: [], OP: [], ON: [], B: [], BO: [], E: [] };
    L.forEach((p) => { const t = T(p); col.V.push(vela(p)); col.J.push(v(t, nivel(p, p.fv))); col.H.push(v(t, nivel(p, p.hi))); col.Lo.push(v(t, nivel(p, p.li))); col.P.push({ time: t, value: cerrada(p) }); col.Z.push(v(t, p.z)); col.ZP.push(v(t, p.zi)); col.ZN.push(v(t, esNum(p.zi) ? -p.zi : null)); col.OP.push(v(t, p.zo)); col.ON.push(v(t, esNum(p.zo) ? -p.zo : null)); col.B.push(v(t, p.b)); col.BO.push(v(t, p.bo)); col.E.push({ time: t, value: p.eq }); });
    velas.setData(col.V); justo.setData(col.J); dHi.setData(col.H); dLo.setData(col.Lo); puerta.setData(col.P); zS.setData(col.Z); ziP.setData(col.ZP); ziN.setData(col.ZN); zoP.setData(col.OP); zoN.setData(col.ON); beta.setData(col.B); betaO.setData(col.BO); eq.setData(col.E);
    const pr = S.tick && S.tick.prov; if (pr && L.length && pr.t > L[L.length - 1].t) actualizar(pr);
    marcar(); if (L.length) preparar(); if (encuadrar) requestAnimationFrame(() => requestAnimationFrame(() => dias(10))); }
  function actualizar(p) { if (!p || !esNum(p.o)) return;
    const ts = chart.timeScale(), r = ts.getVisibleLogicalRange(); const alFinal = !r || r.to >= S.serie.length - 1;   // ¿estabas viendo lo último?
    try { poner(p, 'update'); preparar(); if (alFinal) ts.scrollToRealTime(); } catch (e) { /* un punto viejo */ } }
  function marcar() {
    const t0 = S.serie.length ? S.serie[0].t : 0; const M = [], MZ = [];
    S.marcas.filter((k) => k.t >= t0).forEach((k) => { const time = k.t / 1000;
      if (k.tipo === 'entrada') { const m = { time, position: k.dir > 0 ? 'belowBar' : 'aboveBar', color: k.dir > 0 ? css('--largo') : css('--corto'), shape: k.dir > 0 ? 'arrowUp' : 'arrowDown', size: 1, text: k.texto }; M.push(m); MZ.push({ ...m, text: '' }); }
      else if (k.tipo === 'salida') { const m = { time, position: k.dir > 0 ? 'aboveBar' : 'belowBar', color: k.motivo === 'objetivo' ? css('--info') : css('--warn'), shape: 'circle', size: 0.8, text: k.texto }; M.push(m); MZ.push({ ...m, text: '' }); }
      else if (k.tipo === 'puerta') M.push({ time, position: 'aboveBar', color: k.abre ? css('--ok') : css('--dim'), shape: 'square', size: 0.7, text: k.texto });
      else if (k.tipo === 'roll') M.push({ time, position: 'aboveBar', color: css('--acento'), shape: 'square', size: 0.6, text: k.texto }); });
    M.sort((a, b) => a.time - b.time); MZ.sort((a, b) => a.time - b.time);
    if (mVelas) mVelas.setMarkers(M); if (mZ) mZ.setMarkers(MZ);
    lineasZ.forEach((l) => zS.removePriceLine(l)); lineasZ = [];
    if (S.cfg) [S.cfg.z_stop, -S.cfg.z_stop].forEach((z) => lineasZ.push(zS.createPriceLine({ price: z, color: alfa(css('--warn'), 0.8), lineStyle: LW.LineStyle.Dotted, lineWidth: 1, axisLabelVisible: true, title: 'stop' }))); }
  function preparar() { if (!primera) return; const ps = chart.panes(); if (ps.length !== 4) return; primera = false; ps[0].setStretchFactor(3.0); ps[1].setStretchFactor(1.7); ps[2].setStretchFactor(0.9); ps[3].setStretchFactor(1.0); $('etqPaneles').classList.add('visible'); requestAnimationFrame(etiquetas); }
  function dias(n) { const N = S.serie.length + 1; const por = Math.round(n * 23 * 60 / (S.cfg ? S.cfg.barra_min : 60)); chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, N - por), to: N + 3 }); }
  function geometria() { const ps = chart.panes ? chart.panes() : []; const alt = ps.map((p) => (p.getHeight ? p.getHeight() : 0)); const tops = []; let y = 0; alt.forEach((hh) => { tops.push(y); y += hh + 1; }); return { alt, tops }; }
  function etiquetas() { const g = geometria(); const c = $('etqPaneles'); g.tops.forEach((y, i) => { const e = c.children[i]; if (e) e.style.top = (y + 6) + 'px'; }); }
  new ResizeObserver(() => requestAnimationFrame(etiquetas)).observe(cont);
  chart.subscribeCrosshairMove((q) => leyenda(q && q.time != null ? q.time * 1000 : null));
  tema();
  return { tema, cargar, actualizar, dias, todo: () => chart.timeScale().fitContent(), etiquetas, marcar };
}
function leyenda(tMs) { const el = $('leyenda'); if (!S.cfg) return; let p = tMs != null ? S.idx.get(tMs) : null; const pr = S.tick && S.tick.prov; if (!p && pr && (tMs == null || tMs === pr.t)) p = pr; if (!p && S.serie.length) p = S.serie[S.serie.length - 1]; if (!p) { el.textContent = '—'; return; }
  const c = S.cfg;
  el.innerHTML = `<b>${F.dhm.format(p.t)}</b>${p.prov ? ' <span class="cw">en curso</span>' : ''} · ${c.ry} ${pY(p.c)} · ${c.rx} ${pX(p.cx)}` + (esNum(p.z) ? ` · z <b>${zf(p.z)}</b> (±${num(p.zi, 2)})` : '') + (esNum(p.fv) ? ` · justo ${pY(p.fv)} (${sgn(p.c - p.fv, c.dec_y)})` : '') + (esNum(p.b) ? ` · β ${num(p.b, 4)} → ${c.ny}/${num(p.nx)}` : '') + ` · puerta ${p.p ? '<span class="si">abierta</span>' : '<span class="tenue">cerrada</span>'}` + (p.pos ? ` · ${lado(p.pos)}` : '') + ` · P&L ${usd(p.eq)}`; }

// ---------------- cabecera y KPIs ----------------
function pintarCab(t) {
  const e = S.conectado ? (t.estado || 'iniciando') : 'desconectado'; const pill = $('hEstado'); pill.dataset.e = e; pill.querySelector('b').textContent = ESTADOS[e] || e.toUpperCase();
  if (S.conectado) aviso(t.detalle, ['error', 'sin_datos', 'reconectando'].includes(e));
  const c = S.cfg; if (!c) return;
  const pu = t.puerta; const hp = $('hPuerta');
  if (pu) { hp.dataset.s = pu.abierta ? '1' : '0'; hp.firstElementChild.textContent = pu.abierta ? 'PUERTA ABIERTA' : 'PUERTA CERRADA'; $('hPuertaNota').textContent = pu.abierta ? 'hay cointegración' : (pu.motivo || ''); }
  else { hp.dataset.s = '0'; hp.firstElementChild.textContent = 'SIN CALIBRAR'; $('hPuertaNota').textContent = t.prox ? `faltan ${t.prox} barras` : ''; }
  const hs = $('hPos'); const p = t.pos, pe = t.pend;
  if (pe && (pe.orden === 'abrir' || pe.orden === 'ambas') && pe.plan) { hs.dataset.s = '2'; hs.firstElementChild.textContent = 'ABRE ' + (pe.plan.dir > 0 ? 'LARGO' : 'CORTO'); $('hPosNota').textContent = pe.llen ? `papel ${F.hm.format(pe.llen.t / 1e6)}` : 'a la apertura'; }
  else if (pe && pe.orden === 'cerrar') { hs.dataset.s = '2'; hs.firstElementChild.textContent = 'CIERRA'; $('hPosNota').textContent = MOTIVO[pe.motivo] || pe.motivo; }
  else if (p) { hs.dataset.s = String(p.dir); hs.firstElementChild.textContent = p.dir > 0 ? 'LARGO SPREAD' : 'CORTO SPREAD'; $('hPosNota').textContent = `${p.ny} ${c.ry} / ${p.nx} ${c.rx}`; }
  else { hs.dataset.s = '0'; hs.firstElementChild.textContent = 'PLANO'; $('hPosNota').textContent = ''; }
  const u = t.ult || {}, pr = t.prov || {};
  $('hZ').textContent = zf(u.z); $('hZ').className = 'num ' + (esNum(u.z) && esNum(u.zi) && Math.abs(u.z) >= u.zi ? (u.z > 0 ? 'cc' : 'cl') : '');
  $('hZp').textContent = esNum(pr.z) ? `en curso ${zf(pr.z)}` : '';
  $('hRetraso').textContent = e === 'vivo' && esNum(t.retraso_ms) ? `retraso ${num(Math.max(0, t.retraso_ms / 1000), 1)} s` : '';
  $('hReloj').textContent = F.hms.format(t.ahora) + (F.tz === 'America/Mexico_City' ? ' CDMX' : '');
  document.title = `z ${zf(esNum(pr.z) ? pr.z : u.z)} · ${c.ry}/${c.rx} · Cointegración`;
}
function barraZ(zi, zo, zs, z, zp) { const R = zs + 0.6; const X = (q) => 100 * (Math.max(-R, Math.min(R, q)) + R) / (2 * R); let h = '';
  if (esNum(zi)) { h += `<span class="zona" style="left:0;width:${X(-zi)}%;background:${alfa(css('--largo'), 0.35)};border-radius:4px 0 0 4px"></span><span class="zona" style="left:${X(zi)}%;right:0;background:${alfa(css('--corto'), 0.35)};border-radius:0 4px 4px 0"></span>`; }
  if (esNum(zo)) h += `<span class="zona" style="left:${X(-zo)}%;width:${Math.max(0.6, X(zo) - X(-zo))}%;background:${alfa(css('--info'), 0.35)}"></span>`;
  [zs, -zs].forEach((q) => { h += `<span class="marca" style="left:${X(q)}%;background:var(--warn)"></span>`; });
  if (esNum(zp)) h += `<span class="marca" style="left:${X(zp)}%;background:${alfa(css('--text'), 0.45)}"></span>`;
  if (esNum(z)) h += `<span class="marca" style="left:${X(z)}%;background:var(--text);width:3px"></span>`;
  return h; }
function pintarKpis(t) {
  const c = S.cfg; if (!c) return; const u = t.ult || {}, pr = t.prov || {}, n = t.niv || {}, p = t.pos, pe = t.pend;
  const zi = esNum(pr.zi) ? pr.zi : u.zi, zo = esNum(pr.zo) ? pr.zo : u.zo;
  if (esNum(u.z)) { const fuera = esNum(zi) && Math.abs(u.z) >= zi; $('kZ').style.setProperty('--k', fuera ? (u.z > 0 ? 'var(--corto)' : 'var(--largo)') : 'var(--info)');
    $('vZ').innerHTML = `<span class="${fuera ? (u.z > 0 ? 'cc' : 'cl') : ''}">${zf(u.z)}</span><small>cierre ${F.hm.format(u.t + c.barra_min * 60000)}</small>`;
    $('nZ').innerHTML = (esNum(pr.z) ? `en curso <b>${zf(pr.z)}</b> · ` : '') + `entrada ±${num(zi, 2)} · salida ±${num(zo, 2)} · stop ±${num(c.z_stop, 1)}`;
    $('bZ').innerHTML = barraZ(zi, zo, c.z_stop, u.z, pr.z); }
  else { $('vZ').textContent = '—'; $('nZ').textContent = t.prox ? `el filtro arranca con la primera calibración (faltan ${t.prox} barras)` : 'esperando barras'; $('bZ').innerHTML = ''; }
  const Y = c.ry, X = c.rx, cy = esNum(pr.c) ? pr.c : u.c, cx = esNum(pr.cx) ? pr.cx : u.cx;
  const dirPos = pe && pe.plan && (pe.orden === 'abrir' || pe.orden === 'ambas') ? pe.plan.dir : (p && !(pe && pe.orden === 'cerrar') ? p.dir : 0);
  if (!esNum(n.fv)) { $('tDisp').textContent = 'Precios de disparo'; $('vDisp').textContent = '—'; $('nDisp').textContent = 'sin calibración todavía'; }
  else if (dirPos) { $('tDisp').textContent = `Precios de salida (${dirPos > 0 ? 'largo' : 'corto'})`; const ob = dirPos > 0 ? n.obj_l : n.obj_c, st = dirPos > 0 ? n.stop_l : n.stop_c;
    $('vDisp').innerHTML = `<span class="ci">${pY(ob)}</span><small>/</small> <span class="cw">${pY(st)}</span>`;
    $('nDisp').innerHTML = `objetivo si ${Y} ${dirPos > 0 ? '≥' : '≤'} <b>${pY(ob)}</b> · stop de z si ${Y} ${dirPos > 0 ? '≤' : '≥'} <b>${pY(st)}</b>, con ${X} en ${pX(cx)} · ${Y} ahora ${pY(cy)}`; }
  else { $('tDisp').textContent = 'Precios de disparo'; $('vDisp').innerHTML = `<span class="cc">${pY(n.hi)}</span><small>/</small> <span class="cl">${pY(n.li)}</span>`;
    $('nDisp').innerHTML = `corto si ${Y} ≥ <b>${pY(n.hi)}</b> · largo si ${Y} ≤ <b>${pY(n.li)}</b> al cierre, con ${X} en ${pX(cx)} · ${Y} ahora ${pY(cy)} · justo ${pY(n.fv)} (${sgn(cy - n.fv, c.dec_y)})` + (t.puerta && !t.puerta.abierta ? ' · <span class="tenue">puerta cerrada: no entra</span>' : ''); }
  const b = esNum(pr.b) ? pr : u;
  if (esNum(b.b)) { $('vBeta').innerHTML = `${num(b.b, 4)}<small>MCO ${num(b.bo, 4)}</small>`; $('nBeta').innerHTML = `→ <b>${c.ny} ${Y} / ${num(b.nx)} ${X}</b> con los precios de ahora · β ${c.escala === 'log' ? 'en log (elasticidad)' : 'en puntos'} · Kalman ${c.beta_din ? 'dinámico' : 'estático'}`; }
  const f = S.filas.length ? S.filas[S.filas.length - 1] : null; const pu = t.puerta;
  if (pu && f) { $('kPuerta').style.setProperty('--k', pu.abierta ? 'var(--ok)' : 'var(--dim)'); $('vPuerta').innerHTML = pu.abierta ? '<span class="si">ABIERTA</span>' : '<span class="tenue">CERRADA</span>';
    $('nPuerta').innerHTML = `EG p ${pv(f.p_yx)} / ${pv(f.p_xy)} · ADF ${pv(f.adf)} · vida media <b>${vm(f.vm)}</b> · umbral ±${num(f.z_in, 2)}/${num(f.z_out, 2)}` + (pu.abierta ? '' : ` · no pasa: ${esc(pu.motivo)}`) + (t.prox ? ` · re-estima en ${t.prox} barras` : ''); }
  else { $('vPuerta').textContent = '—'; $('nPuerta').textContent = t.prox ? `primera calibración en ${t.prox} barras` : '—'; }
  if (pe && pe.orden && (pe.orden !== 'cerrar' || p)) { $('kPos').style.setProperty('--k', 'var(--warn)');
    const pl = pe.plan; $('vPos').innerHTML = pe.orden === 'cerrar' ? `<span class="cw">CIERRA</span><small>${MOTIVO[pe.motivo] || ''}</small>` : `<span class="cw">${pe.orden === 'ambas' ? 'VOLTEA' : 'ABRE'}</span> ${lado(pl.dir)}<small>${pl.ny}/${pl.nx}</small>`;
    $('nPos').innerHTML = pe.llen ? `papel a la apertura de las ${F.hm.format(pe.llen.t / 1e6)}: ${Y} ${pY(pe.llen.oy)} · ${X} ${pX(pe.llen.ox)}` + (esNum(pe.llen.neto) ? ` · resultado <b>${usd(pe.llen.neto)}</b>` : '') : 'se ejecuta (papel) a la apertura de la próxima barra'; }
  else if (p) { $('kPos').style.setProperty('--k', p.dir > 0 ? 'var(--largo)' : 'var(--corto)');
    $('vPos').innerHTML = `${lado(p.dir)} <small>${p.ny} ${Y} / ${p.nx} ${X}</small>`;
    const enc = esNum(pr.eq) && esNum(t.equity) ? pr.eq - t.equity : null;
    $('nPos').innerHTML = `desde ${F.dhm.format(p.ts_ent / 1e6)} (z ${zf(p.z_ent)}) · abierto <b>${usd(p.abierto)}</b> al último cierre` + (esNum(enc) ? ` (${usd(enc)} en la hora)` : '') + ` · ${num(p.barras)} h de ${num(p.vm_barras)} (stop de tiempo)`; }
  else { $('kPos').style.setProperty('--k', 'var(--dim)'); $('vPos').innerHTML = '<span class="tenue">plano</span>'; $('nPos').textContent = t.puerta && t.puerta.abierta ? 'esperando que |z| llegue al umbral' : 'la puerta está cerrada: no se abre nada'; }
  const a = (S.audit && S.audit.total) || {}, av = (S.audit && S.audit.vivo) || {};
  $('vPnl').innerHTML = `<span class="${t.equity >= 0 ? 'cl' : 'cc'}">${usd(t.equity)}</span>`;
  $('nPnl').innerHTML = `en vivo <b>${usd(t.eq_vivo)}</b> · ${num(a.trades)} operaciones (${num(av.trades)} en vivo) · acierto ${pct(a.acierto)}` + (esNum(a.sharpe) ? ` · Sharpe ${num(a.sharpe, 2)}` : '');
}

// ---------------- umbral óptimo (canvas) ----------------
function pintarCurva(hx) {
  const c = $('cCurva'); const { x, w, h } = lienzo(c); const k = S.curva || {}; if (!k.series || !k.series.length) { x.fillStyle = css('--muted'); x.fillText('Aparece con la primera re-estimación.', 16, 24); return null; }
  const A = k.a; const izq = 64, der = 14, top = 14, bot = 26; const todos = k.series.flatMap((s) => s.g.filter(esNum)); if (!todos.length) return null;
  let lo = Math.min(0, ...todos), hi = Math.max(0, ...todos); if (hi - lo < 1e-9) hi = lo + 1; const pad = 0.06 * (hi - lo); lo -= pad; hi += pad;
  const X = (a) => izq + (a - A[0]) / (A[A.length - 1] - A[0]) * (w - izq - der); const Yp = (g) => top + (hi - g) / (hi - lo) * (h - top - bot);
  x.strokeStyle = css('--line'); x.beginPath(); x.moveTo(izq, Yp(0)); x.lineTo(w - der, Yp(0)); x.stroke();
  const cols = [css('--info'), css('--acento'), css('--justo'), css('--corto')];
  k.series.forEach((s, j) => { x.strokeStyle = cols[j % cols.length]; x.lineWidth = s.b === k.z_out ? 2.2 : 1.2; x.beginPath(); let on = false; s.g.forEach((g, i) => { if (!esNum(g)) { on = false; return; } if (!on) { x.moveTo(X(A[i]), Yp(g)); on = true; } else x.lineTo(X(A[i]), Yp(g)); }); x.stroke();
    x.fillStyle = cols[j % cols.length]; x.fillRect(w - der - 118, top + 4 + 15 * j, 12, 3); x.fillText(`salida ±${num(s.b, 2)}`, w - der - 100, top + 9 + 15 * j); });
  x.lineWidth = 1;
  if (esNum(k.z_in) && esNum(k.gan)) { const px = X(k.z_in), py = Yp(k.gan); x.fillStyle = css('--text'); x.beginPath(); x.arc(px, py, 4.5, 0, 2 * Math.PI); x.fill(); x.fillText(`${k.umbral === 'optimo' ? 'óptimo' : 'fijo'} ±${num(k.z_in, 2)} / ${num(k.z_out, 2)}`, Math.min(px + 8, w - der - 130), py - 8); }
  x.fillStyle = css('--muted'); x.fillText(usd(hi, false) + '/h', 6, top + 10); x.fillText(usd(lo) + '/h', 6, h - bot - 2); for (let i = 0; i <= 6; i++) { const a = A[0] + (A[A.length - 1] - A[0]) * i / 6; x.textAlign = i === 0 ? 'left' : i === 6 ? 'right' : 'center'; x.fillText('entrada ±' + num(a, 2), X(a), h - 7); } x.textAlign = 'left';
  if (hx != null && hx >= izq && hx <= w - der) { const a = A[0] + (hx - izq) / (w - izq - der) * (A[A.length - 1] - A[0]); let j = 0; for (let i = 0; i < A.length; i++) if (Math.abs(A[i] - a) < Math.abs(A[j] - a)) j = i;
    x.strokeStyle = alfa(css('--text'), 0.35); x.beginPath(); x.moveTo(X(A[j]), top); x.lineTo(X(A[j]), h - bot); x.stroke();
    return `<b>entrada ±${num(A[j], 2)}</b><br>` + k.series.map((s) => `salida ${num(s.b, 2)}: ${esNum(s.g[j]) ? usd(s.g[j]) + '/h' : '—'}`).join('<br>'); }
  return null;
}
$('cCurva').addEventListener('mousemove', (e) => { const r = e.currentTarget.getBoundingClientRect(); const t = pintarCurva(e.clientX - r.left); globo($('gCurva'), t, e.clientX - r.left, e.clientY - r.top, e.currentTarget.parentElement); });
$('cCurva').addEventListener('mouseleave', () => { pintarCurva(null); globo($('gCurva'), null); });

// ---------------- tablas ----------------
function valorLista(it) { const v = it.valor; if (it.tipo === 'p') return pv(v); if (it.tipo === 'h') return vm(v); if (it.tipo === 'usd_h') return esNum(v) ? usd(v) + '/h' : '—'; if (it.tipo === 'n') return num(v); if (it.tipo === 'z') return esNum(v) ? '±' + num(v, 2) : '—'; return num(v, 1); }
function pintarTablas() {
  const c = S.cfg; if (!c) return;
  const li = S.lista || {}; const I = li.items || [];
  $('tbLista').innerHTML = I.length ? [['decide', I.filter((q) => q.decide)], ['diagnóstico (no decide)', I.filter((q) => !q.decide)]].map(([g, L]) => L.length ? `<tr class="grupo"><td colspan="4">${g}</td></tr>` + L.map((q) => `<tr><td class="nom">${esc(q.prueba)}</td><td>${valorLista(q)}</td><td>${esc(q.exige)}</td><td class="${q.pasa ? 'si' : 'no'}">${q.pasa ? 'sí' : 'no'}</td></tr>`).join('') : '').join('') : '<tr><td colspan="4" class="vacio">Aparece con la primera re-estimación.</td></tr>';
  $('resLista').innerHTML = I.length ? `puerta <b>${li.puerta ? 'ABIERTA' : 'CERRADA'}</b> · prueba ${esc(li.prueba)} · α ${num(li.alfa, 2)}` : '';
  $('nLista').innerHTML = `Walk-forward: cada re-estimación ve solo las <b>${num(c.formacion)}</b> barras previas. Para <b>abrir</b> la puerta todo tiene que pasar a α = ${num(c.alfa, 2)}; para <b>seguir abierta</b> basta p &lt; ${num(c.alfa_cierre, 2)} (con la potencia de estas pruebas, exigir 5 % cada día la cierra en plena cointegración). ` + (li.abierta_antes ? 'Hoy venía abierta: aplica el nivel de cierre.' : 'Hoy venía cerrada: aplica el nivel de apertura.') + ' Johansen y KPSS son diagnóstico, como en la v3.';
  const k = S.curva || {}; $('nCurva').innerHTML = esNum(k.costo_sig) ? `Costo de ida y vuelta de la unidad = <b>${num(k.costo_sig, 3)} σ</b> del spread · vida media ${vm(k.vm)} · ganancia esperada con el umbral elegido <b>${usd(k.gan)}/h</b>. El umbral maximiza (a − b)·σ − costo entre los tiempos de primer paso del OU (Bertram 2010); si la curva es plana, el umbral exacto importa poco.` : '';
  const TR = S.trades || []; let sN = 0, sG = 0; TR.forEach((q) => { sN += q.neto; if (q.neto > 0) sG++; });
  $('tbTr').innerHTML = TR.length ? [...TR].reverse().map((q) => `<tr><td>${F.dhm.format(q.ts_ent / 1e6)}${q.fase === 'hist' ? '<span class="etq">historia</span>' : q.fase === 'replay' ? '<span class="etq">replay</span>' : ''}</td><td>${lado(q.dir)}</td><td>${q.ny}/${q.nx}</td><td>${zf(q.z_ent)} → ${zf(q.z_sal)}</td><td>${num(q.horas)}</td><td>${usd(q.bruto)}</td><td>${usd(q.costos, false)}</td><td class="${q.neto >= 0 ? 'cl' : 'cc'}">${usd(q.neto)}</td><td>${F.dhm.format(q.ts_sal / 1e6)} <span class="etq">${MOTIVO[q.motivo] || q.motivo}</span></td></tr>`).join('') : '<tr><td colspan="9" class="vacio">Sin operaciones de papel todavía.</td></tr>';
  $('resTr').innerHTML = TR.length ? `${num(TR.length)} · neto <b>${usd(sN)}</b> · ${num(100 * sG / TR.length)} % ganadoras` : '';
  const A = S.audit || {}, a = A.total || {}, v = A.vivo || {};
  const M = [['Operaciones', 'trades', (x) => num(x)], ['Neto', 'neto_usd', usd], ['Bruto', 'bruto_usd', usd], ['Costos', 'costos_usd', (x) => usd(x, false)], ['Acierto', 'acierto', (x) => pct(x)], ['Factor de beneficio', 'factor_beneficio', (x) => num(x, 2)], ['Payoff', 'payoff', (x) => num(x, 2)], ['Esperanza por operación', 'esperanza', usd], ['Sharpe anual', 'sharpe', (x) => num(x, 2)], ['Sharpe: IC 90 % (bootstrap)', 'ic_sharpe', (x) => (x && esNum(x[0]) ? `${num(x[0], 2)} … ${num(x[1], 2)}` : '—')], ['Sortino anual', 'sortino', (x) => num(x, 2)], ['Sharpe probabilístico', 'psr', (x) => pct(x)], ['Caída máxima', 'max_caida_usd', (x) => usd(-x)], ['Sesiones', 'dias', (x) => num(x)], ['Tiempo en mercado', 'tiempo_en_mercado', (x) => pct(x)], ['Horas por operación', 'horas_media', (x) => num(x, 1)], ['Duración en vidas medias', 'horas_sobre_vm', (x) => num(x, 2)], ['MAE medio', 'mae_media', usd], ['MFE medio', 'mfe_media', usd], ['Costos para borrar la ganancia', 'costo_equilibrio_x', (x) => (esNum(x) ? num(x, 1) + '×' : '—')]];
  $('tbAud').innerHTML = A.total ? M.map(([n, kk, f]) => `<tr><td class="nom">${n}</td><td>${f(a[kk])}</td><td>${A.vivo ? f(v[kk]) : '—'}</td></tr>`).join('') : '<tr><td colspan="3" class="vacio">Aparece con la primera re-estimación.</td></tr>';
  $('resAud').innerHTML = A.total ? `bloque del bootstrap ${num(a.bloque_dias, 1)} sesiones` : '';
  $('nAud').innerHTML = 'Todo en dólares, con contratos enteros, comisión, deslizamiento y rolls, por sesión de CME (la auditoría de la v3). <b>Con menos de 20 operaciones nada de esto es significativo</b>: el intervalo del Sharpe lo muestra.';
  const FL = S.filas || [];
  $('tbFil').innerHTML = FL.length ? [...FL].reverse().slice(0, 300).map((f) => `<tr><td>${F.dhm.format(f.t + c.barra_min * 60000)}${f.fase === 'hist' ? '<span class="etq">historia</span>' : ''}</td><td class="${f.puerta ? 'si' : 'tenue'}">${f.puerta ? 'abierta' : 'cerrada'}</td><td>${pv(f.p_yx)}</td><td>${pv(f.p_xy)}</td><td>${pv(f.adf)}</td><td>${vm(f.vm)} <span class="tenue">[${vmc(f.vm_lo)}–${vmc(f.vm_hi)}]</span></td><td>${num(f.beta_ols, 4)}</td><td>±${num(f.z_in, 2)}/${num(f.z_out, 2)}</td><td>${esNum(f.gan) ? usd(f.gan) : '—'}</td></tr>`).join('') : '<tr><td colspan="9" class="vacio">Sin re-estimaciones todavía.</td></tr>';
  $('resFil').innerHTML = FL.length ? `${num(FL.length)} · puerta abierta en ${num(100 * FL.filter((f) => f.puerta).length / FL.length)} %` : '';
  $('nFil').innerHTML = `Cada ${num(c.reestimar)} barras (≈ una sesión) con las ${num(c.formacion)} previas; la fila rige desde la barra siguiente. Vida media corregida por bootstrap [IC 90 %]; en rango: ${num(c.vm_min, 0)}–${num(c.vm_max, 0)} h.`;
  const AL = S.al; const col = (k) => k.tipo === 'orden' ? (k.sub === 'cerrar' ? 'var(--info)' : (k.dir > 0 ? 'var(--largo)' : 'var(--corto)')) : k.tipo === 'puerta' ? (k.sub === 'abre' ? 'var(--ok)' : 'var(--dim)') : k.tipo === 'en_curso' ? 'var(--warn)' : k.tipo === 'roll' ? 'var(--acento)' : 'var(--muted)';
  const et = (k) => ({ orden: { abrir: 'abrir', cerrar: 'cerrar', ambas: 'voltear' }[k.sub] || 'orden', puerta: k.sub === 'abre' ? 'puerta abierta' : 'puerta cerrada', en_curso: 'en curso', reestimacion: 're-estimación', roll: 'roll' })[k.tipo] || k.tipo;
  $('tbAl').innerHTML = AL.length ? [...AL].reverse().slice(0, 150).map((k) => { const nuevo = !S.vistos.has(k.id) && !S.primero; S.vistos.add(k.id); const tx = k.texto.split('\n');
    return `<tr class="${nuevo ? 'nuevo' : ''}"><td>${F.dhm.format(k.t)}${k.f !== 'vivo' ? `<span class="etq">${k.f}</span>` : ''}</td><td><span class="tipo" style="color:${col(k)};border-color:${col(k)}">${et(k)}</span></td><td>${zf(k.z)}</td><td class="txt">${esc(tx.slice(k.tipo === 'reestimacion' ? 1 : 2).join(' · '))}</td></tr>`; }).join('') : '<tr><td colspan="4" class="vacio">Sin avisos todavía.</td></tr>';
  S.primero = false; $('resAl').textContent = `${num(AL.length)} · Telegram ${c.telegram ? 'activo' : 'desactivado'}`;
}
function pintarPie(t) { const c = S.cfg; if (!c) return; const s = t.stats || {}; const ct = t.contratos || {};
  $('pie').innerHTML = `Par: <b>${esc(c.y)}</b> (${esc(ct.y0 || '—')}) contra <b>${esc(c.x)}</b> (${esc(ct.x0 || '—')}) · rolls medidos con ${esc((c.sims && c.sims.y1) || '—')} / ${esc((c.sims && c.sims.x1) || '—')} · unidad: ${c.ny} ${c.ry} × US$ ${num(c.mult_y)}/pt contra n ${c.rx} × US$ ${num(c.mult_x)}/pt · costos: US$ ${num(c.comision, 2)} por contrato y lado + ${num(c.desliz, 2)} tick de deslizamiento; roll ${num(c.roll_ticks, 1)} tick<br>` +
    `Modelo (v3): barras de ${c.barra_min} min · ventana ${num(c.formacion)} barras · re-estima cada ${num(c.reestimar)} · escala ${c.escala} · Kalman ${c.kalman} (${c.beta_din ? 'β dinámico' : 'β estático'}) con el spread OU dentro del filtro · prueba <b>${c.prueba}</b> (abre α ${num(c.alfa, 2)}, sigue p &lt; ${num(c.alfa_cierre, 2)}) · umbral ${c.umbral} · stop |z| ≥ ${num(c.z_stop, 1)} o ${num(c.stop_vidas, 1)} vidas medias · enfriamiento ${c.enfriamiento} barras · decide al cierre, ejecuta (papel) a la apertura siguiente<br>` +
    `${num(s.barras)} barras (${num(s.barras_vivo)} en vivo) · ${num(s.filas)} re-estimaciones · ${num(s.registros)} barras de 1 min · repetidas descartadas ${num(s.duplicados)} · tardías ${num(s.tarde)} · reconexiones ${num(s.reconexiones)} · avisos en vivo ${num(s.alertas_vivo)} · Telegram: ${c.telegram ? '<b>activo</b>' : 'desactivado'}<br>` +
    `Datos: Databento ${esc(c.dataset)} (ohlcv-1h para calentar, ohlcv-1m en vivo) · Gráficas: <a href="https://www.tradingview.com/lightweight-charts/" target="_blank" rel="noopener">TradingView Lightweight Charts™</a> · Todo es de PAPEL: el indicador no envía órdenes y no es una recomendación de inversión.`; }
function pitido() { if (!S.sonido || !S.audio) return; const ctx = S.audio, t0 = ctx.currentTime; [[0, 660], [0.16, 880]].forEach(([dt, f]) => { const o = ctx.createOscillator(), g = ctx.createGain(); o.frequency.value = f; g.gain.setValueAtTime(0.0001, t0 + dt); g.gain.exponentialRampToValueAtTime(0.22, t0 + dt + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, t0 + dt + 0.14); o.connect(g).connect(ctx.destination); o.start(t0 + dt); o.stop(t0 + dt + 0.16); }); }
function recibirSnapshot(s) { S.cfg = s.cfg; formatos(s.cfg.zona || 'America/Mexico_City'); S.serie = s.serie || []; indexar(); S.marcas = s.marcas || []; S.al = s.alertas || []; S.filas = s.filas || []; S.trades = s.trades || []; S.audit = s.audit || {}; S.curva = s.curva || {}; S.lista = s.lista || {}; S.al.forEach((k) => S.vistos.add(k.id));
  $('hPar').textContent = `${s.cfg.ry} / ${s.cfg.rx}`; $('hFuente').textContent = s.cfg.modo === 'demo' ? 'par sintético de la v3 · minuto a minuto' : 'Databento ' + s.cfg.dataset + ' · ohlcv-1m'; $('etq0').textContent = `${s.cfg.ry} · su valor justo por ${s.cfg.rx} y los precios de disparo`;
  S.tick = s.tick; if (G) G.cargar(true); pintarTablas(); recibirTick(s.tick); pintarCurva(null); }
function recibirPunto(p) { if (S.serie.length && S.serie[S.serie.length - 1].t >= p.t) return; S.serie.push(p); S.idx.set(p.t, p); if (G) G.actualizar(p); }
function recibirListas(p) { const antes = S.al.length; const nuevas = (p.alertas || []).filter((k) => !S.vistos.has(k.id)); S.al = p.alertas || S.al; S.marcas = p.marcas || S.marcas; S.filas = p.filas || S.filas; S.trades = p.trades || S.trades; S.audit = p.audit || S.audit; S.curva = p.curva || S.curva; S.lista = p.lista || S.lista; if (p.cfg) S.cfg = p.cfg;
  if (S.al.length > antes && nuevas.some((k) => k.tipo === 'orden' || k.tipo === 'puerta') && S.tick && (S.tick.estado === 'vivo' || S.tick.estado === 'demo')) pitido(); if (G) G.marcar(); pintarTablas(); pintarCurva(null); }
function recibirTick(t) { S.tick = t; const ct = t.contratos || {}; $('hCont').textContent = ct.y0 && ct.x0 ? `· ${ct.y0} / ${ct.x0}` : ''; if (t.prov && G && (!S.serie.length || t.prov.t > S.serie[S.serie.length - 1].t)) G.actualizar(t.prov); pintarCab(t); pintarKpis(t); const a = Date.now(); if (a - S.pintado > 2000) { S.pintado = a; pintarPie(t); } if (G) G.etiquetas(); if (!document.querySelector('#grafica:hover')) leyenda(null); }
function conectar() { const es = new EventSource('/api/stream');
  es.addEventListener('snapshot', (e) => { S.conectado = true; recibirSnapshot(JSON.parse(e.data)); });
  es.addEventListener('punto', (e) => recibirPunto(JSON.parse(e.data)));
  es.addEventListener('listas', (e) => recibirListas(JSON.parse(e.data)));
  es.addEventListener('tick', (e) => { S.conectado = true; recibirTick(JSON.parse(e.data)); });
  es.onerror = () => { S.conectado = false; const pill = $('hEstado'); pill.dataset.e = 'desconectado'; pill.querySelector('b').textContent = ESTADOS.desconectado; aviso('Se perdió la conexión con el script de Python. Si lo cerraste, vuelve a ejecutarlo: esta página se reconecta sola.', true); }; }
try { if (localStorage.getItem('coint-live-tema') === 'light') document.documentElement.dataset.theme = 'light'; } catch (e) { /* */ }
$('bTema').onclick = () => { const r = document.documentElement; if (r.dataset.theme === 'light') delete r.dataset.theme; else r.dataset.theme = 'light'; try { localStorage.setItem('coint-live-tema', r.dataset.theme || 'dark'); } catch (e) { /* */ } if (G) G.tema(); pintarCurva(null); if (S.tick) pintarKpis(S.tick); };
$('bSonido').onclick = () => { S.sonido = !S.sonido; if (S.sonido && !S.audio) { try { S.audio = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) { S.sonido = false; } } if (S.audio && S.audio.state === 'suspended') S.audio.resume(); $('bSonido').setAttribute('aria-pressed', String(S.sonido)); $('bSonido').textContent = 'Sonido: ' + (S.sonido ? 'sí' : 'no'); if (S.sonido) pitido(); };
try { G = crearGrafica(); } catch (e) { console.error(e); }
$('b10').onclick = () => G && G.dias(10); $('bTodo').onclick = () => G && G.todo();
new ResizeObserver(() => requestAnimationFrame(() => pintarCurva(null))).observe(document.querySelector('main'));
conectar();
})();
</script>
</body>
</html>
"""



# =============================================================================
# 23. AUTOPRUEBA
# =============================================================================
class _NotificadorFalso:
    def __init__(self):
        self.mensajes = []

    def enviar(self, texto, guardar_en=None, responder_a=None, silencioso=False):
        if guardar_en is not None:
            guardar_en["tg_id"] = len(self.mensajes) + 100
        self.mensajes.append({"texto": texto, "silencioso": silencioso, "responde": (responder_a or {}).get("tg_id")})

    def cerrar(self, espera=0.0):
        pass


def _nucleo_prueba(cfg: Config, horas_cal: dict, reloj: dict, notificador=None) -> NucleoCoint:
    nuc = NucleoCoint(cfg)
    nuc.reloj = lambda: reloj["t"]
    nuc.notificador = notificador
    nuc.calentar(horas_cal)
    return nuc


def autoprueba() -> int:
    import tempfile
    configurar_log(Path(tempfile.gettempdir()) / "coint_live_autoprueba")
    LOG.handlers[0].setLevel(logging.ERROR)
    fallas: list[str] = []
    T0 = time.perf_counter()

    def revisar(nombre: str, ok: bool, detalle: str = "") -> None:
        print(f"  {'OK   ' if ok else 'FALLA'}  {nombre}{('  ' + detalle) if detalle else ''}", flush=True)
        if not ok:
            fallas.append(nombre)

    # Ventana de 20 sesiones (460 barras) para que las pruebas duren poco; el par tiene una ruptura y dos rolls.
    cfg = replace(CFG, sonido=False, bootstrap=300, formacion_barras=460, sint_sesiones=64, sint_ruptura=(0.50, 0.62),
                  replay_max_h=1e7)
    SEM = 6
    print(f"0) Mercado sintético de la v3 minuto a minuto ({cfg.sint_sesiones} sesiones, semilla {SEM})", flush=True)
    crudas, nombres, verdad = mercado_minutos(cfg, semilla=SEM)
    horas = {s: agregar_barras(v, cfg.barra_min) for s, v in crudas.items()}
    b = unir_par(horas["y0"], horas["x0"], horas["y1"], horas["x1"], cfg)
    cal = calendario(b, cfg)
    L = correr_lote(b, cal, cfg)
    n = len(b["ts"])
    ses_cal = 30
    corte = int(crudas["y0"]["ts"][ses_cal * 23 * 60])
    k_corte = int(np.searchsorted(b["ts"], corte))
    tr_v = L["trades"][L["trades"]["t_ent"] > k_corte]
    revisar(f"escenario: {n:,} barras, {len(cal)} re-estimaciones (puerta abierta {cal['puerta'].mean():.0%}), "
            f"{len(L['trades'])} operaciones ({len(tr_v)} después del corte), rolls en las barras "
            f"{np.flatnonzero(b['roll_y']).tolist()} / {np.flatnonzero(b['roll_x']).tolist()}",
            len(tr_v) >= 2 and cal["puerta"].nunique() == 2 and b["roll_y"][k_corte:].any())

    print("1) El camino en vivo (1 min → Agregador → UnirVivo → MotorPar) = el motor histórico de la v3", flush=True)
    falso = _NotificadorFalso()
    reloj = {"t": corte}
    hist = recortar_minutos(crudas, hasta=corte)
    nuc = _nucleo_prueba(cfg, {s: agregar_barras(v, cfg.barra_min) for s, v in hist.items()}, reloj, falso)
    msgs = mensajes_minutos(recortar_minutos(crudas, desde=corte), nuc.sims, nombres)
    nuc.en_replay()
    nuc.pasar_a_vivo("prueba")
    prov_z: dict = {}
    niv_ok = [0, 0.0]

    def al_minuto(ts: int) -> None:
        if ts % nuc.paso == 0 and nuc.prov is not None and _fin(nuc.prov.get("z")):
            prov_z[nuc.prov["t"]] = nuc.prov["z"]
        if ts % (7 * nuc.paso) == 0:                          # de vez en cuando: el precio de disparo da el z exacto
            kf, f = filtro_siguiente(nuc.motor)
            if kf is not None and nuc.unir.prev is not None and np.isfinite(f["z_in"]):
                x = float(nuc.motor.ultima["x"])
                for zt in (f["z_in"], -f["z_in"], 0.0):
                    ystar = float(niveles_y(kf, f, x, [zt])[0])
                    zz, _ = z_de(copy.copy(kf), f, ystar, x)
                    niv_ok[0] += 1
                    niv_ok[1] = max(niv_ok[1], abs(zz - zt))
    t0 = time.perf_counter()
    ult = reproducir(nuc, msgs, reloj, al_minuto=al_minuto)
    reloj["t"] = ult + 2 * MIN_NS
    nuc.reloj_datos(reloj["t"], latido=True)
    seg = time.perf_counter() - t0
    m = nuc.motor
    Lz, Mz = L["z"], np.array(m.hist["z"])
    filas_m = pd.DataFrame(m.filas)
    # la v3 no calibra en la última barra (su fila no regiría nada); el motor en vivo sí, si le toca
    fm = filas_m.iloc[:len(cal)]
    iguales_filas = (len(filas_m) - len(cal) in (0, 1) and (fm["k"].to_numpy() == cal["k"].to_numpy()).all()
                     and (fm["puerta"].to_numpy() == cal["puerta"].to_numpy()).all()
                     and np.allclose(fm[["phi", "mu", "sigma_eq", "z_in", "z_out", "b_fin"]].to_numpy(float),
                                     cal[["phi", "mu", "sigma_eq", "z_in", "z_out", "b_fin"]].to_numpy(float),
                                     equal_nan=True, rtol=0, atol=1e-12))
    revisar(f"{len(msgs):,} mensajes en {seg:.1f} s: las {len(cal)} re-estimaciones son las de la v3 (k, puerta, φ, μ, σ, "
            f"umbral, β)", iguales_filas)
    tr_m = pd.DataFrame(m.trades, columns=COLS_TRADES)
    Lc = L["trades"][L["trades"]["motivo"] != "fin"].reset_index(drop=True)
    comp = ["dir", "t_dec", "t_ent", "t_dec_sal", "t_sal", "nx", "motivo"]
    iguales_tr = (len(tr_m) == len(Lc) and tr_m[comp].reset_index(drop=True).equals(Lc[comp])
                  and np.allclose(tr_m[["neto", "bruto", "costos", "z_ent"]].to_numpy(float),
                                  Lc[["neto", "bruto", "costos", "z_ent"]].to_numpy(float), atol=1e-6))
    revisar(f"mismo z en las {len(Mz):,} barras (dif. máx {np.nanmax(np.abs(Mz - Lz)) if len(Mz) == len(Lz) else float('nan'):.1e}) "
            f"y las mismas {len(tr_m)} operaciones cerradas con el mismo P&L ({_usd(tr_m['neto'].sum())})",
            len(Mz) == len(Lz) and np.allclose(Mz, Lz, equal_nan=True, atol=1e-9) and iguales_tr)
    pnl_ok = np.allclose(np.array(m.hist["pnl"])[:-1], L["pnl"][:-1], atol=1e-6) and \
        np.allclose(np.array(m.hist["costos"])[:-1], L["costos"][:-1], atol=1e-6)
    revisar(f"mismo P&L y costos barra a barra (equity de papel {_usd(nuc.equity)}; la v3 además cierra lo abierto al final)",
            pnl_ok)

    print("2) La hora en curso: el z en curso al último minuto = el z del cierre; los precios de disparo", flush=True)
    pares = [(t, z) for t, z in prov_z.items()]
    cierres = {p["t"]: p["z"] for p in nuc.serie}
    dif = [abs(z - cierres[t]) for t, z in pares if t in cierres and _fin(cierres[t])]
    revisar(f"{len(dif)} horas: dif. máx entre el z en curso del último minuto y el del cierre {max(dif) if dif else float('nan'):.1e}",
            len(dif) > 100 and max(dif) < 1e-9)
    revisar(f"{niv_ok[0]} precios de disparo: con Y en ese precio el z filtrado queda en el umbral (dif. máx {niv_ok[1]:.1e})",
            niv_ok[0] >= 30 and niv_ok[1] < 1e-6)

    print("3) Órdenes, puerta, rolls y avisos", flush=True)
    ordenes = [k for k in nuc.alertas if k["tipo"] == "orden"]
    entradas = [k for k in ordenes if k["datos"]["orden"] in ("abrir", "ambas")]
    salidas = [k for k in ordenes if k["datos"]["orden"] in ("cerrar", "ambas")]
    tr_vivo = tr_m[tr_m["t_ent"] >= nuc.n_hist]
    ok_ent = all(k["datos"].get("llen") for k in ordenes[:-1])
    reales = [(round(t.py_ent + b["g_y"][t.t_ent], 6), round(t.px_ent + b["g_x"][t.t_ent], 6)) for t in tr_m.itertuples()
              if t.t_ent >= nuc.n_hist]
    avisados = [(round(k["datos"]["llen"]["oy"], 6), round(k["datos"]["llen"]["ox"], 6)) for k in entradas if k["datos"].get("llen")]
    netos_m = [round(t.neto, 4) for t in tr_m.itertuples() if t.t_sal >= nuc.n_hist]
    netos_a = [round(k["datos"]["llen"]["neto"], 4) for k in salidas if k["datos"].get("llen")]
    revisar(f"{len(entradas)} órdenes de entrada y {len(salidas)} de salida: el precio de papel avisado = el de la entrada del "
            f"motor; el neto avisado = el de la operación ({netos_a[:4]}…)",
            ok_ent and len(entradas) >= 2 and avisados[:len(reales)] == reales and 0 <= len(avisados) - len(reales) <= 1
            and netos_a == netos_m)
    filas_v = [f for f in m.filas if int(f["k"]) >= nuc.n_hist]
    previa = [bool(m.filas[i - 1]["puerta"]) if i else False for i, f in enumerate(m.filas) if int(f["k"]) >= nuc.n_hist]
    cambios = sum(bool(f["puerta"]) != p for f, p in zip(filas_v, previa))
    tipos = [k["tipo"] for k in nuc.alertas]
    revisar(f"re-estimaciones en vivo: {len(filas_v)} → {tipos.count('puerta')} avisos de puerta ({cambios} cambios) y "
            f"{tipos.count('reestimacion')} resúmenes", tipos.count("puerta") == cambios and cambios >= 1
            and tipos.count("reestimacion") == len(filas_v) - cambios)
    rolls = [k for k in nuc.alertas if k["tipo"] == "roll"]
    k_roll = [i for i in np.flatnonzero(b["roll_y"] | b["roll_x"]) if i >= nuc.n_hist]
    saltos_v3 = sorted(round(float(b[f"g_{p}"][i] - b[f"g_{p}"][i - 1]), 6) for i in k_roll for p in ("y", "x")
                       if b[f"roll_{p}"][i])
    saltos_a = sorted(round(float(k["datos"]["salto"]), 6) for k in rolls)
    revisar(f"rolls en vivo: {len(rolls)} avisos con los saltos de unir_par de la v3 {saltos_a} y los contratos "
            f"{[k['datos']['antes'] + '→' + k['datos']['nuevo'] for k in rolls if k['datos'].get('antes')]}",
            saltos_a == saltos_v3 and len(rolls) >= 1 and all(k["datos"].get("nuevo") for k in rolls))
    en_curso = [k for k in nuc.alertas if k["tipo"] == "en_curso"]
    por_barra = {}
    for k in en_curso:
        por_barra.setdefault((k["datos"]["k"], k["datos"]["que"]), 0)
        por_barra[(k["datos"]["k"], k["datos"]["que"])] += 1
    ent_curso = [k for k in en_curso if k["datos"]["que"] == "entrada"]
    anticipadas = sum(1 for k in entradas if any(e["datos"]["k"] == k["datos"]["k"] for e in ent_curso))
    revisar(f"{len(en_curso)} avisos en curso (uno por barra y tipo); {anticipadas} de {len(entradas)} entradas se "
            f"anticiparon dentro de su hora", en_curso and max(por_barra.values()) == 1 and anticipadas >= 1)
    tg = falso.mensajes
    principales = [k for k in nuc.alertas]
    seguimientos = [x for x in tg if x["responde"]]
    revisar(f"Telegram: {len(tg)} mensajes = inicio + {len(principales)} avisos + {len(seguimientos)} seguimientos "
            f"(silenciosos: {sum(x['silencioso'] for x in tg)})",
            len(tg) == 1 + len(principales) + len(seguimientos) and "Cointegración Live en vivo" in tg[0]["texto"])
    def html_invalido(t: str) -> bool:
        """Lo que rechaza el parse_mode=HTML de Telegram: un '<' que no abre <b>/<i>, un '&' que no es entidad, o
        etiquetas sin cerrar."""
        return bool(re.search(r"<(?!/?[bi]>)", t) or re.search(r"&(?!(lt|gt|amp|quot);)", t)
                    or t.count("<b>") != t.count("</b>") or t.count("<i>") != t.count("</i>"))
    malos = [x["texto"] for x in tg if html_invalido(x["texto"]) or re.search(r"\b(nan|None|inf)\b", x["texto"])]
    revisar(f"{len(tg)} textos de Telegram: HTML que Telegram acepta (solo <b>/<i>, entidades escapadas) y sin nan/None",
            not malos, malos[0][:160] if malos else "")
    nuc.analizar()
    a = nuc.audit
    revisar(f"auditoría de papel (la de la v3): historia {a.get('total', {}).get('trades')} operaciones, "
            f"{_usd(a.get('total', {}).get('neto_usd'))}; en vivo {a.get('vivo', {}).get('trades')} operaciones",
            a.get("total", {}).get("trades", 0) >= len(tr_vivo) and "vivo" in a)
    snap = json.loads(_json(nuc.snapshot()))
    cli = {"epoca": -1, "cursor": 0, "ver": -1}
    p1, p2 = nuc.paquete(cli, True), nuc.paquete(cli, True)
    revisar("snapshot serializable (serie, filas, operaciones, curva, lista) y paquetes incrementales",
            len(snap["serie"]) == len(nuc.serie) and snap["filas"] and snap["curva"]["series"] and snap["lista"]["items"]
            and [x for x, _ in p1] == ["snapshot"] and [x for x, _ in p2] == ["tick"])

    print("4) Orden en la última hora de la sesión: aviso al cerrar y precio de papel al reabrir, en el mismo hilo", flush=True)
    cfg5 = replace(cfg, prueba="ninguna", umbral="fijo", z_entrada=0.3, z_salida=0.0, enfriamiento_barras=2)
    falso5 = _NotificadorFalso()
    reloj5 = {"t": corte}
    n5 = _nucleo_prueba(cfg5, {s: agregar_barras(v, cfg.barra_min) for s, v in hist.items()}, reloj5, falso5)
    n5.en_replay()
    n5.pasar_a_vivo("prueba")
    fin5 = int(crudas["y0"]["ts"][(ses_cal + 10) * 23 * 60])
    reproducir(n5, mensajes_minutos(recortar_minutos(crudas, desde=corte, hasta=fin5), n5.sims, nombres), reloj5)
    ords5 = [k for k in n5.alertas if k["tipo"] == "orden"]
    seg5 = [k for k in ords5 if k.get("texto_ej")]
    pos_ts = {int(t): i for i, t in enumerate(b["ts"])}
    ok5 = bool(seg5)
    for k in seg5:
        ll = k["datos"]["llen"]
        i = pos_ts.get(ll["t"])
        ok5 &= i is not None and i > 0 and b["ts"][i] - b["ts"][i - 1] > nuc.paso        # abrió tras una pausa
        ok5 &= abs(ll["oy"] - (b["o_y"][i] + b["g_y"][i])) < 1e-9 and abs(ll["ox"] - (b["o_x"][i] + b["g_x"][i])) < 1e-9
        if k["datos"].get("pos") is not None:
            tr = [t for t in n5.motor.trades if t["t_sal"] == i]
            ok5 &= len(tr) == 1 and abs(tr[0]["neto"] - ll["neto"]) < 1e-6
    respuestas = [x for x in falso5.mensajes if x["responde"]]
    revisar(f"{len(ords5)} órdenes con umbral 0.3 en 10 sesiones: {len(seg5)} decididas en la última hora (aviso sin precio al "
            f"cerrar) y su precio de papel llegó al reabrir como respuesta ({len(respuestas)}), igual al de la v3",
            ok5 and len(respuestas) == len(seg5) and all(k["datos"].get("llen") for k in ords5[:-1]))

    print("5) Bucle Live con DBN real: piso del replay, un corte a la mitad y el replay que se solapa", flush=True)
    c2 = int(crudas["y0"]["ts"][(ses_cal + 8) * 23 * 60])     # 8 sesiones más de historia y 3 en vivo, con el roll
    c3 = int(crudas["y0"]["ts"][(ses_cal + 11) * 23 * 60])
    tramo = recortar_minutos(crudas, desde=c2, hasta=c3)
    mensajes = mensajes_minutos(tramo, nuc.sims, nombres)
    hb = []
    ult_ts = None
    for r in mensajes:                                          # heartbeats en las pausas (lo que manda Live)
        if isinstance(r, db.OHLCVMsg):
            if ult_ts is not None and int(r.ts_event) - ult_ts > MIN_NS:
                hb.append(db.SystemMsg(ts_event=ult_ts + 2 * MIN_NS, msg="Heartbeat", code=SystemCode.HEARTBEAT))
            ult_ts = int(r.ts_event)
        hb.append(r)
    mensajes = hb
    horas_c2 = {s: agregar_barras(v, cfg.barra_min) for s, v in recortar_minutos(crudas, hasta=c2).items()}
    piso = c2 + 40 * MIN_NS

    class ClienteFalso:
        def __init__(self, corte_en=None, piso_err=False):
            self.corte_en, self.piso_err, self.start = corte_en, piso_err, 0

        def subscribe(self, **kw):
            self.start = int(pd.Timestamp(kw["start"]).value)
            if self.piso_err and self.start < piso:
                raise db.BentoError(f"Invalid start time. Must be {pd.Timestamp(piso, tz='UTC').isoformat()} or later, or 0")

        def __iter__(self):
            primero = {}
            for r in mensajes:                                   # el mapeo vigente al empezar (lo que manda Live)
                if isinstance(r, db.SymbolMappingMsg) and (int(r.ts_event) <= self.start or str(r.stype_in_symbol) not in primero):
                    primero[str(r.stype_in_symbol)] = r
            j = 0
            yield from primero.values()
            for r in mensajes:
                if isinstance(r, db.SymbolMappingMsg):
                    if int(r.ts_event) > self.start:
                        yield r
                    continue
                if int(r.ts_event) < self.start:
                    continue
                j += 1
                if self.corte_en is not None and j >= self.corte_en:
                    raise db.BentoError("conexión perdida (prueba)")
                yield r

        def terminate(self):
            pass
    reloj_l = {"t": c3 + 10 * 60 * NS}
    nl = _nucleo_prueba(cfg, horas_c2, reloj_l)
    detener = threading.Event()
    n_ohlcv = sum(isinstance(r, db.OHLCVMsg) for r in mensajes)
    clientes = iter([ClienteFalso(piso_err=True), ClienteFalso(corte_en=n_ohlcv // 2 + 7), ClienteFalso()])

    def fabrica():
        try:
            return next(clientes)
        except StopIteration:
            detener.set()
            raise db.BentoError("fin de la prueba")
    bucle_live(nl, cfg, c2, fabrica=fabrica, detener=detener, espera_base=0.0)
    nr = _nucleo_prueba(cfg, horas_c2, {"t": c3 + 10 * 60 * NS})
    nr.hueco(c2, piso)
    directo = ClienteFalso()
    directo.start = piso
    for r in directo:
        if isinstance(r, db.SymbolMappingMsg):
            nr.mapeo(r)
        elif isinstance(r, db.OHLCVMsg):
            nr.ohlcv(r)
        else:
            nr.reloj_datos(int(r.ts_event), latido=True)
    iguales = (nl.motor.t == nr.motor.t and np.allclose(nl.motor.hist["z"], nr.motor.hist["z"], equal_nan=True)
               and abs(nl.equity - nr.equity) < 1e-6 and len(nl.motor.trades) == len(nr.motor.trades)
               and nl.agr.abiertas == nr.agr.abiertas)
    revisar(f"tras el piso del gateway y un corte a la mitad: el mismo estado que sin cortes ({nl.motor.t - nl.n_hist + 1} "
            f"horas en vivo, {nl.duplicados} minutos repetidos descartados, reconexiones {nl.reconexiones}, roll "
            f"{nl.contrato_antes.get('y0')} → {nl.contratos.get('y0')})",
            iguales and nl.duplicados > 0 and nl.reconexiones == 2 and nl.motor.t > nl.n_hist
            and nl.contratos.get("y0") != nl.contrato_antes.get("y0") and any(k["tipo"] == "roll" for k in nl.alertas))

    print("6) Calentamiento con DBN real: cliente histórico falso → descarga, lectura, barras completas y el motor", flush=True)
    import databento_dbn as dbn
    fin6 = pd.Timestamp(int(horas["y0"]["ts"][-1]) + nuc.paso - 5 * MIN_NS, tz="UTC")   # termina a media hora: la última no entra
    sims = simbolos_par(cfg)

    class _Meta:
        def get_dataset_range(self, dataset):
            return {"start": "2020-01-01T00:00:00Z", "end": fin6.isoformat(), "schema": {"ohlcv-1h": {"end": fin6.isoformat()}}}

        def get_cost(self, **kw):
            return 0.25

    class _Series:
        def get_range(self, dataset, symbols, stype_in, schema, start, end, path):
            v = horas[{sym: k for k, sym in sims.items()}[symbols]]
            m = (v["ts"] >= pd.Timestamp(start, tz="UTC").value) & (v["ts"] < pd.Timestamp(end, tz="UTC").value)
            ts = v["ts"][m]
            meta = dbn.Metadata(dataset=dataset, schema=dbn.Schema.OHLCV_1H, start=int(ts[0]), end=int(ts[-1]) + HORA_NS,
                                stype_in=dbn.SType.INSTRUMENT_ID, stype_out=dbn.SType.INSTRUMENT_ID)
            px = lambda q: int(round(float(q) * 1e9))  # noqa: E731
            partes = [meta.encode()] + [bytes(dbn.OHLCVMsg(rtype=dbn.RType.OHLCV_1H, publisher_id=1, instrument_id=int(i),
                                                           ts_event=int(t), open=px(o), high=px(h), low=px(l), close=px(c), volume=int(vv)))
                                        for t, o, h, l, c, vv, i in zip(ts, v["o"][m], v["h"][m], v["l"][m], v["c"][m], v["v"][m], v["iid"][m])]
            Path(path).write_bytes(b"".join(partes))

    class HistoricoFalso:
        metadata, timeseries = _Meta(), _Series()
    with tempfile.TemporaryDirectory() as tmp:
        cfg6 = replace(cfg, cache_dir=tmp)
        n6 = NucleoCoint(cfg6)
        corte6 = preparar_live(n6, cfg6, HistoricoFalso())
    dias6 = max(cfg6.historia_dias, int(math.ceil(cfg6.formacion_barras / 23 * 7 / 5)) + 7)
    ini6 = (fin6.floor("60min") - pd.Timedelta(days=dias6)).value
    ref = _nucleo_prueba(cfg6, {s: {c: v[c][(v["ts"] >= ini6) & (v["ts"] + nuc.paso <= fin6.floor("60min").value)] for c in v}
                                for s, v in horas.items()}, {"t": 0})
    revisar(f"{n6.motor.t + 1:,} barras completas de {dias6} días ({len(n6.motor.filas)} re-estimaciones, {len(n6.motor.trades)} "
            f"operaciones): lo mismo que calentar directo; el replay de Live sigue desde {_hora(corte6, 'UTC')} UTC",
            n6.motor.t == ref.motor.t and np.allclose(n6.motor.hist["z"], ref.motor.hist["z"], equal_nan=True)
            and len(n6.motor.trades) == len(ref.motor.trades) and n6.agr.limite == int(horas["y0"]["ts"][-2])
            and corte6 == fin6.floor("60min").value)

    print(f"\n{time.perf_counter() - T0:.0f} s")
    if fallas:
        print(f"{len(fallas)} pruebas fallaron: {', '.join(fallas)}")
        return 1
    print("Todas las pruebas pasaron.")
    return 0


# =============================================================================
# 24. MAIN
# =============================================================================
def probar_telegram() -> int:
    configurar_log(_ruta(CFG.salida_dir))
    notificador = preparar_telegram()
    if notificador is None:
        print(f"\nCrea {ARCHIVOS_TELEGRAM[0]} junto al script con TELEGRAM_TOKEN y TELEGRAM_CHAT_ID (o define esas variables).")
        return 1
    nuc = NucleoCoint(CFG)
    nuc.contratos = {"y0": "ESZ6", "x0": "NQZ6"}
    t = int(pd.Timestamp("2026-09-25 15:00", tz="UTC").value)
    k = {"tipo": "orden", "t": t + HORA_NS, "fase": "vivo", "z": -2.31, "cy": 6498.75, "cx": 23456.25,
         "datos": {"orden": "abrir", "motivo": None, "k": t, "z": -2.31, "cy": 6498.75, "cx": 23456.25,
                   "plan": {"dir": 1, "ny": 2, "nx": 3, "z_ent": -2.31, "z_in": 2.05, "z_out": 0.0, "beta_ent": 0.8321,
                            "vm_ent": 24.3},
                   "niv": {"fv": 6512.0, "obj_l": 6512.0, "stop_l": 6451.5},
                   "fila": {"p_eg_yx": 0.012, "p_eg_xy": 0.021, "adf_kalman_p": 0.018, "ganancia_h_usd": 18.4},
                   "llen": {"t": t + HORA_NS, "oy": 6499.0, "ox": 23456.75}}}
    notificador.enviar("🧪 <b>PRUEBA de Cointegración Live</b>: si ves este mensaje, las órdenes te van a llegar aquí.\n"
                       "Así se verá una entrada (números de ejemplo):\n\n" + texto_alerta(k, nuc))
    notificador.cerrar(20)
    if notificador.enviados:
        LOG.info("Mensaje de prueba enviado. Revisa tu Telegram.")
        return 0
    LOG.error(f"No se pudo enviar el mensaje de prueba: {notificador.ultimo_error}")
    return 1


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Cointegración de un par de futuros en vivo (Databento): prueba estricta, "
                                             "Kalman, z del spread, órdenes de papel, tablero y Telegram")
    ap.add_argument("--y", dest="symbol_y", help="pierna dependiente (ES.n.0)")
    ap.add_argument("--x", dest="symbol_x", help="pierna de cobertura (NQ.n.0)")
    ap.add_argument("--stype", choices=("continuous", "parent", "raw_symbol"))
    ap.add_argument("--mult-y", type=float, help="US$ por punto de Y (ES 50, MES 5)")
    ap.add_argument("--mult-x", type=float, help="US$ por punto de X (NQ 20, MNQ 2)")
    ap.add_argument("--tick-y", type=float)
    ap.add_argument("--tick-x", type=float)
    ap.add_argument("--contratos-y", type=int, help="contratos de Y por unidad de spread (2)")
    ap.add_argument("--comision", type=float, help="US$ por contrato y lado (2)")
    ap.add_argument("--deslizamiento", type=float, help="ticks por lado (0.5)")
    ap.add_argument("--capital", type=float)
    ap.add_argument("--historia-dias", type=int, help="días de historia para calentar (60)")
    ap.add_argument("--formacion", type=int, help="barras de la ventana de formación (690)")
    ap.add_argument("--reestimar", type=int, help="cada cuántas barras se re-estima (23)")
    ap.add_argument("--escala", choices=("log", "niveles"))
    ap.add_argument("--kalman", choices=("mle", "fijo"))
    ap.add_argument("--beta-estatico", action="store_true", help="β de MCO por ventana (sin Kalman)")
    ap.add_argument("--prueba", choices=("estricta", "eg", "ninguna"))
    ap.add_argument("--alfa", type=float, help="nivel para ABRIR la puerta (0.05)")
    ap.add_argument("--umbral", choices=("optimo", "fijo"))
    ap.add_argument("--z-entrada", type=float)
    ap.add_argument("--z-salida", type=float)
    ap.add_argument("--z-stop", type=float)
    ap.add_argument("--enfriamiento", type=int)
    ap.add_argument("--sin-rolls", action="store_true", help="no ajustar los rolls (no bajar .n.1)")
    ap.add_argument("--costo-max", type=float, help="tope en US$ de la descarga del calentamiento (10)")
    ap.add_argument("--sin-en-curso", action="store_true", help="sin los avisos de 'señal en curso'")
    ap.add_argument("--puerto", type=int, help="puerto del tablero (8160)")
    ap.add_argument("--sin-navegador", action="store_true")
    ap.add_argument("--sin-sonido", action="store_true")
    ap.add_argument("--sin-telegram", action="store_true")
    ap.add_argument("--demo", action="store_true", help="par sintético de la v3 minuto a minuto, sin Databento")
    ap.add_argument("--velocidad", type=float, default=3600.0, help="--demo: veces más rápido que el reloj (3600: 1 h/s)")
    ap.add_argument("--duracion", type=float, help="segundos y se detiene")
    ap.add_argument("--probar-telegram", action="store_true")
    ap.add_argument("--autoprueba", action="store_true")
    args = ap.parse_args(argv)
    if args.autoprueba:
        sys.exit(autoprueba())
    if args.probar_telegram:
        sys.exit(probar_telegram())

    cambios = {k: v for k, v in (
        ("symbol_y", args.symbol_y), ("symbol_x", args.symbol_x), ("stype_in", args.stype), ("mult_y", args.mult_y),
        ("mult_x", args.mult_x), ("tick_y", args.tick_y), ("tick_x", args.tick_x), ("contratos_y", args.contratos_y),
        ("comision_usd", args.comision), ("deslizamiento_ticks", args.deslizamiento), ("capital_usd", args.capital),
        ("historia_dias", args.historia_dias), ("formacion_barras", args.formacion), ("reestimar_cada", args.reestimar),
        ("escala", args.escala), ("kalman", args.kalman), ("prueba", args.prueba), ("alfa", args.alfa),
        ("umbral", args.umbral), ("z_entrada", args.z_entrada), ("z_salida", args.z_salida), ("z_stop", args.z_stop),
        ("enfriamiento_barras", args.enfriamiento), ("costo_max_usd", args.costo_max), ("puerto", args.puerto))
        if v is not None}
    for bandera, campo in (("sin_navegador", "abrir_navegador"), ("sin_sonido", "sonido"), ("sin_en_curso", "aviso_en_curso"),
                           ("sin_rolls", "ajustar_rolls"), ("beta_estatico", "beta_dinamico")):
        if getattr(args, bandera):
            cambios[campo] = False
    cfg = replace(CFG, **cambios)
    if (args.symbol_y or args.symbol_x) and not args.stype:
        cfg = replace(cfg, stype_in=stype_de(cfg.symbol_y))
    if cfg.formacion_barras < 100 or cfg.reestimar_cada < 1:
        sys.exit("formacion_barras tiene que ser ≥ 100 y reestimar_cada ≥ 1.")
    if args.demo:
        cfg = replace(cfg, symbol_y="ES.n.0", symbol_x="NQ.n.0", stype_in="continuous", ajustar_rolls=True)

    carpeta = _ruta(cfg.salida_dir)
    ruta_log = configurar_log(carpeta)
    registro = None if args.demo else Registro(carpeta, f"{raiz_de(cfg.symbol_y)}_{raiz_de(cfg.symbol_x)}", cfg.zona_local)
    nucleo = NucleoCoint(cfg, registro)
    LOG.info(f"Cointegración Live · {cfg.symbol_y} / {cfg.symbol_x} · "
             + ("DEMO (par sintético de la v3, sin Databento)" if args.demo else f"{cfg.dataset} ohlcv-1m")
             + f" · barras de {cfg.barra_min} min · ventana {cfg.formacion_barras} · prueba '{cfg.prueba}' (α {cfg.alfa:g}) · "
               f"umbral '{cfg.umbral}' · Kalman '{cfg.kalman}'" + (" (β estático)" if not cfg.beta_dinamico else "")
             + f" · {cfg.contratos_y} {raiz_de(cfg.symbol_y)} × {cfg.mult_y:g} US$/pt contra {raiz_de(cfg.symbol_x)} × {cfg.mult_x:g}")
    cliente_hist = None if args.demo else conectar_historico()
    if not args.demo and not args.sin_telegram:
        nucleo.notificador = preparar_telegram()
    servidor = ServidorTablero(nucleo, cfg)
    url = servidor.iniciar()
    LOG.info(f"Tablero: {url}   (Ctrl+C para detener)")
    if cfg.abrir_navegador:
        webbrowser.open(url)
    detener = threading.Event()
    actual: dict = {}

    def analisis():
        while not detener.wait(2.0 if not nucleo.audit else cfg.analisis_s):
            try:
                nucleo.analizar()
            except Exception as e:
                LOG.warning(f"Auditoría: {type(e).__name__}: {e}")
    threading.Thread(target=analisis, name="analisis", daemon=True).start()
    if args.duracion:
        def parar():
            detener.set()
            cliente = actual.get("cliente")
            if cliente is not None:
                try:
                    cliente.terminate()
                except Exception:
                    pass
        threading.Timer(args.duracion, parar).start()
    try:
        if args.demo:
            correr_demo(nucleo, cfg, detener, velocidad=args.velocidad)
            while not detener.wait(0.5):
                pass
        else:
            corte_ns = preparar_live(nucleo, cfg, cliente_hist)
            bucle_live(nucleo, cfg, corte_ns, detener=detener, actual=actual)
    except KeyboardInterrupt:
        LOG.info("Deteniendo (Ctrl+C)…")
    finally:
        detener.set()
        nucleo.avisar("detenido", "El script se detuvo. Vuelve a ejecutarlo para seguir en vivo.", log=False)
        LOG.info(f"Resumen: {sum(1 for k in nucleo.alertas if k['fase'] == 'vivo')} avisos en vivo · posición de papel: "
                 f"{nucleo._txt_pos()} · log en {ruta_log}")
        if nucleo.notificador:
            if nucleo.aviso_inicio_enviado:
                nucleo.notificar(f"⏹ Cointegración Live detenido · {nucleo._nombre_html()} · posición de papel: "
                                 f"{html.escape(nucleo._txt_pos())}.", silencioso=True)
            nucleo.notificador.cerrar(6)
        servidor.detener()


if __name__ == "__main__":
    main()
