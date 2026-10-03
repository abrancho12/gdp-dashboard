# -*- coding: utf-8 -*-
"""
KYLAMBA v4 — λ de Kyle institucional con MBP-1 de Databento
============================================================
λ de Kyle (1985):  ΔP = λ · (flujo neto firmado) + ε.  λ alto = mercado poco profundo: cada contrato
agresivo mueve más el precio.  1/λ es la "profundidad de Kyle": contratos que hacen falta para mover
el precio un tick.

Cada bloque del código lleva la etiqueta del punto que resuelve:

 [1] MEDICIÓN CON MICROPRICE Y DIRECCIONALIDAD REAL
     · ΔP se mide con el microprice del libro (bid + spread·qb/(qb+qa)) y NUNCA se mezcla con el último
       trade: si una barra no tiene libro válido, su ΔP queda en blanco.
     · El flujo firmado sale del lado agresor que publica la bolsa (side B = compra, A = venta).
     · Autoauditoría del signo: cada trade se compara con el mid vigente. Si las "compras" no ocurren
       arriba del mid, el programa lo grita (así se habría detectado el signo invertido de v1/v2).
     · λ asimétrico: λ⁺ (impacto de las compras) y λ⁻ (de las ventas). Si comprar mueve más el precio
       que vender, el lado del ask está delgado: el mercado es vulnerable al alza (y al revés).

 [2] REGRESIÓN CAUSAL DINÁMICA
     · Mínimos cuadrados con olvido exponencial (vida media en horas), equivalente a un filtro de Kalman
       con factor de descuento: λ se adapta barra a barra, sin ventanas que "saltan".
     · Estrictamente causal: el valor al cierre de t usa solo barras ≤ t; recortes, centros y escalas
       salen de barras < t. Hay una prueba automática (tests/) que lo verifica truncando los datos.

 [3] FILTROS MATEMÁTICOS RIGUROSOS (si falla cualquiera, λ queda en blanco; no se rellena)
     · t de Newey-West (HAC): robusto a heterocedasticidad y autocorrelación del error.
     · R² mínimo, tamaño efectivo de muestra mínimo y signo económico (λ > 0).
     · Apalancamiento: ninguna barra puede aportar más de cierto % de Σ w·x².
     · Robustez: λ de la regresión y λ mediana (pendientes individuales) deben coincidir.
     · Calidad de datos: cobertura mínima de libro válido dentro de la barra.

 [4] ESCALA Y NORMALIZACIÓN INSTITUCIONAL
     · λ en bps por contrato, ticks por 100 contratos, bps por US$1M de nocional, profundidad de Kyle
       (contratos por tick), slippage medio en bps y costo en US$ de una orden de N contratos, con
       intervalo de confianza al 95%.
     · z robusto en escala logarítmica y DESESTACIONALIZADO: cada barra se compara contra la misma
       franja horaria de los días previos (el ES de madrugada no es "anómalo" por ser de madrugada).

 [5] DOBLE CONFIRMACIÓN PARA SEÑALES
     · Señal = λ extremo y válido (el total, o λ⁺ / λ⁻ por separado con un umbral más alto)
               + confirmación de IMPACTO (Amihud o λ estimado con OFI, un segundo estimador)
               + confirmación del LIBRO  (spread más ancho o menos profundidad de lo normal a esa hora)
     · Persistencia, histéresis (rearme) y enfriamiento. Cada alerta abre un episodio con duración,
       z máximo y dirección de la vulnerabilidad.

 [6] AUDITORÍA DE IMPACTO POSTERIOR
     · Calibración predictiva: ¿el λ de ahora predice el impacto real de las próximas barras?
       (β = 1 es calibración perfecta; R² fuera de muestra contra el λ "típico de esa hora").
     · Estudio de eventos contra una base emparejada por hora del día, con p-valores por permutación
       y control de falsos descubrimientos (Benjamini-Hochberg).
     · Respuesta al impulso: qué parte del impacto es permanente y cuál se revierte (resiliencia).
     · Precisión (hit rate) y correlación de rangos con la volatilidad y el λ futuros.

API key (nunca en el código):
  Windows, una sola vez:  setx DATABENTO_API_KEY "db-..."   y luego cierra y abre VS Code.

Uso:
  python kylamba.py --demo                       # datos sintéticos, sin API key ni costo
  python kylamba.py                              # ES, agosto 2026, barras de 1 min
  python kylamba.py --barra 5 --vida-media 2     # barras de 5 min (sube la vida media)
  python kylamba.py --simbolo NQ.n.0 --inicio 2026-09-01 --fin 2026-09-26
  python kylamba.py --fuente trades              # más barato: sin microprice, OFI ni libro
  python kylamba.py --live                       # tiempo real, con calentamiento histórico
"""
from __future__ import annotations

import argparse
import gc
import json
import math
import os
import re
import sys
import time
import unicodedata
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd

IDENTIFICADOR = "kylamba-v4"


# =============================================================================
# 0. CONFIGURACIÓN
# =============================================================================
@dataclass(frozen=True)
class Config:
    # --- Datos ---
    dataset: str = "GLBX.MDP3"
    symbol: str = "NQ.n.0"
    stype_in: str = "continuous"
    start: str = "2026-06-01T00:00:00"       # UTC
    end: str = "2026-06-28T00:00:00"         # exclusivo
    fuente: str = "mbp-1"                    # "mbp-1" (microprice + OFI + libro) o "trades"
    tick_size: float | None = None           # None = por símbolo (ES: 0.25)
    multiplicador: float | None = None       # USD por punto (ES: 50)
    cache_dir: str = "datos_databento"       # misma caché que v3
    usar_cache: bool = True
    salida_dir: str = "salidas_kylamba"
    costo_max_usd: float = 25.0
    tam_bloque: int = 2_000_000

    # --- [1] Medición: barras, microprice y direccionalidad ---
    barra_min: int = 1                       # barras cortas = más muestra efectiva para la misma memoria
    solo_f_last: bool = True                 # el libro solo se lee en registros con F_LAST
    gap_reset_s: float = 60.0                # el OFI se reinicia tras huecos más largos
    hueco_max_min: float = 20.0              # minutos faltantes tolerados antes de cortar la serie
    cobertura_min: float = 0.5               # fracción mínima de la barra con libro válido
    lado_n: str = "excluir"                  # trades sin agresor: "excluir" o "cotizacion" (quote rule)

    # --- [2] Regresión causal dinámica ---
    ponderacion: str = "exponencial"         # "exponencial" (dinámica) o "ventana" (rodante clásica)
    vida_media_h: float = 0.75               # memoria de λ si ponderacion="exponencial"
    ventana_h: float = 3.0                   # memoria de λ si ponderacion="ventana"
    regresor: str = "delta"                  # "delta" (Kyle: volumen neto) u "ofi" (Cont-Kukanov-Stoikov)
    winsor_k: float = 5.0                    # recorte causal de barras extremas (0 = no recortar)
    hac_lags: int | None = None              # None = regla de Newey-West según la muestra efectiva

    # --- [3] Filtros matemáticos ---
    n_eff_min: float = 40.0
    t_min: float = 2.0                       # t de Newey-West mínimo
    r2_min: float = 0.05
    apalancamiento_max: float = 0.20         # una barra no puede aportar más del 20% de Σ w·x²
    robustez_max: float = 2.0                # λ regresión / λ mediana dentro de [1/2, 2]

    # --- [4] Escala y normalización ---
    normalizacion: str = "estacional"        # "estacional" (misma hora de días previos) o "simple"
    franja_min: int = 10                     # tamaño de la franja horaria (hora de Chicago)
    escala_por_franja: bool = True           # escala = máx(dispersión global, dispersión de la franja)
    dias_norm: int = 15                      # días previos que definen lo "normal" en cada franja
    min_dias_franja: int = 3
    ventana_escala_h: float = 120.0          # escala robusta del residuo desestacionalizado (≈ 5 sesiones)
    min_obs_z: int = 300
    piso_escala_log: float = 0.05            # escala mínima en log (evita z gigantes con spreads planos)
    tamano_orden: int = 100                  # contratos, para costo y slippage
    nocional_ref_usd: float = 1_000_000.0

    # --- [5] Señales con doble confirmación ---
    umbral_z: float = 2.5
    umbral_lado_z: float = 3.0               # λ⁺ o λ⁻ por separado (vacío de un solo lado); más exigente
    umbral_conf_z: float = 1.0
    confirmacion: str = "doble"              # "doble" (impacto Y libro), "simple" (impacto O libro), "ninguna"
    vida_media_libro_h: float = 0.25         # memoria del spread, la profundidad y el desbalance
    persistencia_min: int = 3                # barras consecutivas cumpliendo todo
    rearme_z: float = 1.0                    # histéresis: el z debe bajar de aquí para rearmar
    cooldown_h: float = 2.0
    t_direccion: float = 2.0                 # |t| de λ⁺ − λ⁻ para declarar dirección
    z_severa: float = 4.0

    # --- [6] Auditoría ---
    horizontes_h: tuple[float, ...] = (0.5, 1.0, 2.0, 4.0)
    impulso_min: tuple[int, ...] = (0, 1, 2, 5, 10, 15, 30)
    calibracion_min: tuple[int, ...] = (1, 15, 60)
    n_permutaciones: int = 2000
    semilla: int = 7
    fdr_q: float = 0.10

    # --- Live ---
    dias_historial_live: int = 10            # calentamiento histórico (días naturales)


CFG = Config()

CARPETA_SCRIPT = Path(__file__).resolve().parent
NS = 1_000_000_000
PRICE_SCALE = 1e9
F_LAST = int(db.RecordFlags.F_LAST)
UNDEF_PRICE = db.UNDEF_PRICE
ESPECIFICACIONES = {                          # raíz: (tick, USD por punto)
    "ES": (0.25, 50.0), "MES": (0.25, 5.0), "NQ": (0.25, 20.0), "MNQ": (0.25, 2.0),
    "YM": (1.0, 5.0), "MYM": (1.0, 0.5), "RTY": (0.1, 50.0), "M2K": (0.1, 5.0),
    "CL": (0.01, 1000.0), "MCL": (0.01, 100.0), "GC": (0.1, 100.0), "MGC": (0.1, 10.0),
    "ZN": (1 / 64, 1000.0), "ZB": (1 / 32, 1000.0), "6E": (0.00005, 125000.0),
}
try:
    from zoneinfo import ZoneInfo
    TZ_LOCAL = ZoneInfo("America/Mexico_City")
    TZ_BOLSA = ZoneInfo("America/Chicago")
except Exception:                             # Windows sin tzdata
    import pytz
    TZ_LOCAL = pytz.timezone("America/Mexico_City")
    TZ_BOLSA = pytz.timezone("America/Chicago")

COLUMNAS_BARRA = ["ofi", "delta", "volumen", "vol_n", "vol_eval", "vol_coherente", "n_trades",
                  "n_libro", "n_eventos", "cobertura", "spread", "prof_bid", "prof_ask", "desbalance",
                  "mid", "wmid", "precio", "instrumento"]
COLUMNAS_ENTERAS = ["ofi", "delta", "volumen", "vol_n", "vol_eval", "vol_coherente", "n_trades",
                    "n_libro", "n_eventos"]
SUMAS_LIBRO = ("w", "w_spread", "w_bid", "w_ask", "w_desb")


def especificacion(cfg: Config) -> tuple[float, float]:
    raiz = re.match(r"[A-Za-z0-9]+?(?=[.]|[FGHJKMNQUVXZ]\d|$)", cfg.symbol)
    tick, mult = ESPECIFICACIONES.get(raiz.group(0).upper() if raiz else "", (None, None))
    tick, mult = cfg.tick_size or tick, cfg.multiplicador or mult
    if tick is None or mult is None:
        sys.exit(f"No conozco el tick/multiplicador de {cfg.symbol}: defínelos en Config.")
    return float(tick), float(mult)


def barras_por_hora(cfg: Config) -> float:
    return 60.0 / cfg.barra_min


def validar_config(cfg: Config) -> list[str]:
    """Revisa combinaciones que dejarían al indicador sin mediciones válidas."""
    avisos = []
    opciones = {"fuente": ("mbp-1", "trades"), "ponderacion": ("exponencial", "ventana"),
                "regresor": ("delta", "ofi"), "normalizacion": ("estacional", "simple"),
                "confirmacion": ("doble", "simple", "ninguna"), "lado_n": ("excluir", "cotizacion")}
    for campo, validas in opciones.items():
        if getattr(cfg, campo) not in validas:
            sys.exit(f"Config.{campo}={getattr(cfg, campo)!r} no es válido; opciones: {validas}")
    if cfg.fuente == "trades" and cfg.regresor == "ofi":
        sys.exit("El regresor 'ofi' necesita el libro: usa --fuente mbp-1.")
    n_nom = _Memoria(cfg, cfg.vida_media_h if cfg.ponderacion == "exponencial" else None).n_nominal
    if n_nom < 1.5 * cfg.n_eff_min:
        avisos.append(f"La memoria de λ equivale a {n_nom:.0f} barras efectivas y el filtro pide "
                      f"{cfg.n_eff_min:.0f}: casi todo quedará en blanco. Sube --vida-media o baja --barra.")
    if cfg.fuente == "trades" and cfg.confirmacion == "doble":
        avisos.append("Con --fuente trades no hay libro: la doble confirmación se reduce al canal de impacto.")
    return avisos


def libro_valido(bpx, bsz, apx, asz):
    return (bpx != UNDEF_PRICE) & (apx != UNDEF_PRICE) & (bsz > 0) & (asz > 0) & (bpx < apx)


def ofi_incremento(bpx, bsz, apx, asz, pbpx, pbsz, papx, pasz):
    """e_n de Cont, Kukanov & Stoikov (2014): el regresor alternativo a Kyle."""
    e = 0
    if bpx >= pbpx:
        e += bsz
    if bpx <= pbpx:
        e -= pbsz
    if apx <= papx:
        e -= asz
    if apx >= papx:
        e += pasz
    return e


def ofi_incremento_vec(bpx, bsz, apx, asz, pbpx, pbsz, papx, pasz):
    return (np.where(bpx >= pbpx, bsz, 0) - np.where(bpx <= pbpx, pbsz, 0)
            - np.where(apx <= papx, asz, 0) + np.where(apx >= papx, pasz, 0))


def mid_y_wmid(bpx, bsz, apx, asz):
    """Microprice (mid ponderado) = bid + spread·qb/(qb+qa): si hay más compradores esperando en el bid,
    el precio "justo" está más cerca del ask. to_ndarray entrega nanodólares: se divide una sola vez."""
    mid = (bpx + apx) / 2 / PRICE_SCALE
    wmid = (bpx + (apx - bpx) * bsz / (bsz + asz)) / PRICE_SCALE
    return mid, wmid


# =============================================================================
# 1. BARRAS: motor incremental (replay y Live)                         [1]
# =============================================================================
# R1 El libro solo se lee en registros con F_LAST.     R2 Estados válidos (dos lados, sin cruzar).
# R3 OFI entre estados válidos; 0 si cambia el contrato o hay un hueco largo.
# R4 Spread, profundidad y desbalance ponderados por el tiempo que duró cada estado: un estado cuenta en
#    su barra hasta el siguiente estado, y en la barra del siguiente estado desde su inicio.
# R5 Tiempo monótono; cada barra se fecha en su CIERRE.
# R6 side 'B' = compra agresiva (+), 'A' = venta agresiva (−), 'N' = sin agresor (se excluye o se
#    clasifica con la cotización vigente, según Config.lado_n).
# R7 Autoauditoría: un trade con agresor "coherente" es una compra arriba del mid o una venta abajo.
class _Acumulador:
    __slots__ = ("ofi", "delta", "volumen", "vol_n", "vol_eval", "vol_coherente", "n_trades",
                 "n_libro", "n_eventos", "w", "w_spread", "w_bid", "w_ask", "w_desb", "ultimo",
                 "precio", "instrumento")

    def __init__(self):
        self.ofi = self.delta = self.volumen = self.vol_n = self.vol_eval = self.vol_coherente = 0
        self.n_trades = self.n_libro = self.n_eventos = 0
        self.w = self.w_spread = self.w_bid = self.w_ask = self.w_desb = 0.0
        self.ultimo = None
        self.precio = np.nan
        self.instrumento = np.nan


def _estado_libro(bpx, bsz, apx, asz, tick):
    """(spread en ticks, tamaño bid, tamaño ask, desbalance) de un estado válido."""
    return ((apx - bpx) / PRICE_SCALE / tick, float(bsz), float(asz), (bsz - asz) / (bsz + asz))


def _fila_barra(a: _Acumulador, ns: int) -> dict:
    if a.ultimo is not None:
        bpx, bsz, apx, asz = a.ultimo
        mid, wmid = mid_y_wmid(bpx, bsz, apx, asz)
    else:
        mid = wmid = np.nan
    w = a.w if a.w > 0 else np.nan
    return {
        "ofi": a.ofi, "delta": a.delta, "volumen": a.volumen, "vol_n": a.vol_n, "vol_eval": a.vol_eval,
        "vol_coherente": a.vol_coherente, "n_trades": a.n_trades, "n_libro": a.n_libro,
        "n_eventos": a.n_eventos, "cobertura": a.w / ns, "spread": a.w_spread / w,
        "prof_bid": a.w_bid / w, "prof_ask": a.w_ask / w, "desbalance": a.w_desb / w,
        "mid": mid, "wmid": wmid, "precio": a.precio, "instrumento": a.instrumento,
    }


class MotorBarras:
    def __init__(self, cfg: Config, tick: float, al_cerrar_barra=None):
        self.ns = cfg.barra_min * 60 * NS
        self.gap_ns = int(cfg.gap_reset_s * NS)
        self.solo_f_last = cfg.solo_f_last
        self.cotizacion_n = cfg.lado_n == "cotizacion"
        self.tick = tick
        self.al_cerrar_barra = al_cerrar_barra
        self._t_cierres: list[int] = []
        self._filas: list[dict] = []
        self._ts_max = -1
        self._barra: int | None = None
        self._a = _Acumulador()
        self._pend = None       # [t, barra, estado, ya_sumado_en_su_barra]
        self._prev = None       # (t, instrumento, bpx, bsz, apx, asz) del último estado válido

    def _sumar(self, dt: int, estado) -> None:
        a = self._a
        sp, qb, qa, desb = estado
        a.w += dt
        a.w_spread += sp * dt
        a.w_bid += qb * dt
        a.w_ask += qa * dt
        a.w_desb += desb * dt

    def procesar(self, r) -> None:
        ts = r.ts_event
        if ts < self._ts_max:                                   # R5
            ts = self._ts_max
        self._ts_max = ts
        barra = ts - ts % self.ns
        if barra != self._barra:
            if self._barra is not None:
                self._cerrar_barra()
            self._barra = barra
        a = self._a
        a.n_eventos += 1
        a.instrumento = float(r.instrument_id)
        bpx = getattr(r, "bid_px_00", None)

        if r.action == "T":                                     # R6
            lado, tam = r.side, r.size
            if lado == "B":
                a.delta += tam
            elif lado == "A":
                a.delta -= tam
            else:
                a.vol_n += tam
            a.volumen += tam
            a.n_trades += 1
            a.precio = r.price / PRICE_SCALE
            if bpx is not None and libro_valido(bpx, r.bid_sz_00, r.ask_px_00, r.ask_sz_00):
                p2, suma = 2 * r.price, bpx + r.ask_px_00
                if lado in ("B", "A") and p2 != suma:           # R7
                    a.vol_eval += tam
                    if (lado == "B" and p2 > suma) or (lado == "A" and p2 < suma):
                        a.vol_coherente += tam
                elif lado not in ("B", "A") and self.cotizacion_n:
                    a.delta += tam if p2 > suma else (-tam if p2 < suma else 0)

        if bpx is None:                                         # schema "trades": no trae libro
            return
        if self.solo_f_last and not (r.flags & F_LAST):         # R1
            return
        p = self._pend                                          # R4
        if p is not None:
            inicio = p[0] if p[1] == barra else barra
            self._sumar(ts - inicio, p[2])
            self._pend = None

        apx, bsz, asz = r.ask_px_00, r.bid_sz_00, r.ask_sz_00
        if not libro_valido(bpx, bsz, apx, asz):                # R2
            return
        iid = r.instrument_id
        self._pend = [ts, barra, _estado_libro(bpx, bsz, apx, asz, self.tick), False]
        q = self._prev
        if q is not None and q[1] == iid and ts - q[0] <= self.gap_ns:      # R3
            a.ofi += ofi_incremento(bpx, bsz, apx, asz, q[2], q[3], q[4], q[5])
        self._prev = (ts, iid, bpx, bsz, apx, asz)
        a.n_libro += 1
        a.ultimo = (bpx, bsz, apx, asz)

    def _cerrar_barra(self) -> None:
        fin = self._barra + self.ns
        p = self._pend
        if p is not None and p[1] == self._barra and not p[3]:
            self._sumar(fin - p[0], p[2])
            p[3] = True
        fila = _fila_barra(self._a, self.ns)
        self._t_cierres.append(fin)
        self._filas.append(fila)
        if self.al_cerrar_barra is not None:
            self.al_cerrar_barra(pd.Timestamp(fin, tz="UTC"), fila)
        self._a = _Acumulador()

    def finalizar(self) -> pd.DataFrame:
        if self._barra is not None:
            self._pend = None            # el último estado no se extiende a una barra que no terminó
            self._cerrar_barra()
            self._barra = None
        return self.barras()

    def barras(self) -> pd.DataFrame:
        idx = pd.to_datetime(np.asarray(self._t_cierres, dtype=np.int64), utc=True)
        df = pd.DataFrame(self._filas, index=idx, columns=COLUMNAS_BARRA)
        df.index.name = "t_cierre"
        return _tipos_barra(df)


def _tipos_barra(df: pd.DataFrame) -> pd.DataFrame:
    tipos = {c: np.int64 for c in COLUMNAS_ENTERAS}
    tipos.update({c: np.float64 for c in COLUMNAS_BARRA if c not in COLUMNAS_ENTERAS})
    return df.astype(tipos)


# =============================================================================
# 2. BARRAS: motor vectorizado (misma matemática, bloques de millones de registros)   [1]
# =============================================================================
@dataclass
class _Arrastre:
    ts_max: int = -1
    pend: tuple | None = None     # (t, barra, válido, spread, qb, qa, desb)
    prev: tuple | None = None


def _ultimo_por_barra(barras_sel: np.ndarray, valores: dict) -> pd.DataFrame:
    fin = np.flatnonzero(np.r_[barras_sel[1:] != barras_sel[:-1], True])
    return pd.DataFrame({k: v[fin] for k, v in valores.items()},
                        index=pd.Index(barras_sel[fin], name="barra"))


def _procesar_bloque(arr: np.ndarray, c: _Arrastre, cfg: Config, tick: float):
    ns = cfg.barra_min * 60 * NS
    gap_ns = int(cfg.gap_reset_s * NS)
    sumas: list[pd.DataFrame] = []
    ultimos: list[pd.DataFrame] = []
    ts = arr["ts_event"].astype(np.int64)
    ts[0] = max(int(ts[0]), c.ts_max)
    ts = np.maximum.accumulate(ts)                                   # R5
    c.ts_max = int(ts[-1])
    barra = ts - ts % ns
    ultimos.append(_ultimo_por_barra(barra, {"instrumento": arr["instrument_id"].astype(np.float64)}))

    # --- Trades: flujo firmado con el agresor real ---                R6
    es_trade = arr["action"] == b"T"
    lado = arr["side"]
    compra, venta = es_trade & (lado == b"B"), es_trade & (lado == b"A")
    sin_lado = es_trade & ~compra & ~venta
    tam = arr["size"].astype(np.int64)
    firmado = np.where(compra, tam, 0) - np.where(venta, tam, 0)
    vol_eval = vol_coh = np.zeros(len(arr), dtype=np.int64)
    tiene_libro = "bid_px_00" in (arr.dtype.names or ())
    if tiene_libro:                                                  # R7
        bp_t, ap_t = arr["bid_px_00"].astype(np.int64), arr["ask_px_00"].astype(np.int64)
        ok_t = es_trade & libro_valido(bp_t, arr["bid_sz_00"], ap_t, arr["ask_sz_00"])
        p2, suma = 2 * arr["price"].astype(np.int64), bp_t + ap_t
        evaluable = ok_t & (compra | venta) & (p2 != suma)
        coherente = evaluable & ((compra & (p2 > suma)) | (venta & (p2 < suma)))
        vol_eval, vol_coh = np.where(evaluable, tam, 0), np.where(coherente, tam, 0)
        if cfg.lado_n == "cotizacion":
            cls = ok_t & sin_lado
            firmado = firmado + np.where(cls & (p2 > suma), tam, 0) - np.where(cls & (p2 < suma), tam, 0)
    sumas.append(pd.DataFrame({
        "barra": barra, "delta": firmado, "volumen": np.where(es_trade, tam, 0),
        "vol_n": np.where(sin_lado, tam, 0), "vol_eval": vol_eval, "vol_coherente": vol_coh,
        "n_trades": es_trade.astype(np.int64), "n_eventos": np.ones(len(arr), dtype=np.int64),
    }))
    if es_trade.any():
        ultimos.append(_ultimo_por_barra(barra[es_trade],
                                         {"precio": arr["price"][es_trade] / PRICE_SCALE}))
    if not tiene_libro:                                              # schema "trades": sin libro
        return sumas, ultimos

    sel = (arr["flags"] & F_LAST) != 0 if cfg.solo_f_last else np.ones(len(arr), dtype=bool)   # R1
    idx = np.flatnonzero(sel)
    if idx.size == 0:
        return sumas, ultimos
    t, b = ts[idx], barra[idx]
    bpx = arr["bid_px_00"][idx].astype(np.int64)
    apx = arr["ask_px_00"][idx].astype(np.int64)
    bsz = arr["bid_sz_00"][idx].astype(np.int64)
    asz = arr["ask_sz_00"][idx].astype(np.int64)
    iid = arr["instrument_id"][idx].astype(np.int64)
    val = libro_valido(bpx, bsz, apx, asz)                           # R2
    with np.errstate(divide="ignore", invalid="ignore"):
        sp = np.where(val, (apx - bpx) / PRICE_SCALE / tick, 0.0)
        qb, qa = np.where(val, bsz, 0).astype(float), np.where(val, asz, 0).astype(float)
        desb = np.where(val, (bsz - asz) / np.where(val, bsz + asz, 1), 0.0)

    # R4: el estado pendiente del bloque anterior entra como primer renglón
    cols = [t, b, val, sp, qb, qa, desb]
    if c.pend is not None:
        cols = [np.r_[np.asarray([c.pend[k]], dtype=col.dtype), col] for k, col in enumerate(cols)]
    T, B, V, SP, QB, QA, DS = cols
    if T.size > 1:
        propio = np.minimum(T[1:], B[:-1] + ns) - T[:-1]
        cruza = B[1:] != B[:-1]
        siguiente = np.where(cruza, T[1:] - B[1:], 0)
        m = V[:-1]
        for barras_dest, dur, mask in ((B[:-1], propio, m), (B[1:], siguiente, m & cruza)):
            d = dur[mask].astype(float)
            sumas.append(pd.DataFrame({"barra": barras_dest[mask], "w": d, "w_spread": SP[:-1][mask] * d,
                                       "w_bid": QB[:-1][mask] * d, "w_ask": QA[:-1][mask] * d,
                                       "w_desb": DS[:-1][mask] * d}))
    c.pend = tuple(col[-1].item() for col in cols)

    vi = np.flatnonzero(val)                                         # R3
    if vi.size == 0:
        return sumas, ultimos
    tv, iv, bv = t[vi], iid[vi], b[vi]
    Bp, BS, A, AS = bpx[vi], bsz[vi], apx[vi], asz[vi]
    q = c.prev if c.prev is not None else (int(tv[0]), -1, 0, 0, 0, 0)
    pt, pi, pB, pBS, pA, pAS = [np.concatenate(([q[k]], col[:-1]))
                                for k, col in enumerate((tv, iv, Bp, BS, A, AS))]
    inc = np.where((pi == iv) & (tv - pt <= gap_ns), ofi_incremento_vec(Bp, BS, A, AS, pB, pBS, pA, pAS), 0)
    c.prev = (int(tv[-1]), int(iv[-1]), int(Bp[-1]), int(BS[-1]), int(A[-1]), int(AS[-1]))
    sumas.append(pd.DataFrame({"barra": bv, "ofi": inc, "n_libro": np.ones(vi.size, dtype=np.int64)}))
    mid, wmid = mid_y_wmid(Bp, BS, A, AS)
    ultimos.append(_ultimo_por_barra(bv, {"mid": mid, "wmid": wmid}))
    return sumas, ultimos


def barras_de_arreglos(bloques, cfg: Config, tick: float) -> pd.DataFrame:
    """Construye barras desde un iterable de arreglos estructurados (to_ndarray por bloques)."""
    ns = cfg.barra_min * 60 * NS
    c = _Arrastre()
    partes_s, partes_u = [], []
    for arr in bloques:
        if not len(arr):
            continue
        sumas, ultimos = _procesar_bloque(arr, c, cfg, tick)
        partes_s.append(pd.concat(sumas, ignore_index=True).groupby("barra").sum())
        partes_u.extend(ultimos)
    return _ensamblar(partes_s, partes_u, ns)


def _ensamblar(partes_s, partes_u, ns) -> pd.DataFrame:
    if not partes_s:
        vacio = pd.DataFrame(columns=COLUMNAS_BARRA, index=pd.DatetimeIndex([], tz="UTC", name="t_cierre"))
        return _tipos_barra(vacio)
    S = pd.concat(partes_s).groupby(level=0).sum()
    for col in ("ofi", "n_libro") + SUMAS_LIBRO:
        if col not in S:
            S[col] = 0
    # último valor de cada barra: cada columna por separado (no todas vienen en todos los bloques)
    U = {}
    for parte in partes_u:
        for col in parte.columns:
            U.setdefault(col, []).append(parte[col])
    for col, series in U.items():
        S = S.join(pd.concat(series).groupby(level=0).last().rename(col), how="left")
    w = S["w"].where(S["w"] > 0)
    S["cobertura"] = S["w"] / ns
    S["spread"] = S["w_spread"] / w
    S["prof_bid"] = S["w_bid"] / w
    S["prof_ask"] = S["w_ask"] / w
    S["desbalance"] = S["w_desb"] / w
    for col in ("mid", "wmid", "precio", "instrumento"):
        if col not in S:
            S[col] = np.nan
    S.index = pd.to_datetime(S.index.to_numpy(dtype=np.int64) + ns, utc=True)
    S.index.name = "t_cierre"
    return _tipos_barra(S[COLUMNAS_BARRA])


def construir_barras(store: db.DBNStore, cfg: Config, tick: float, motor="vectorizado") -> pd.DataFrame:
    if motor == "incremental":
        m = MotorBarras(cfg, tick)
        for rec in store:
            if isinstance(rec, (db.MBP1Msg, db.TradeMsg)):
                m.procesar(rec)
        return m.finalizar()
    return barras_de_arreglos(store.to_ndarray(count=cfg.tam_bloque), cfg, tick)


def unir_barras(partes: list[pd.DataFrame]) -> pd.DataFrame:
    """Une barras de varias descargas. Si una barra quedó partida en la frontera, se conserva la que
    tiene más eventos (en la práctica, un puñado de milisegundos)."""
    partes = [p for p in partes if len(p)]
    if not partes:
        return _tipos_barra(pd.DataFrame(columns=COLUMNAS_BARRA,
                                         index=pd.DatetimeIndex([], tz="UTC", name="t_cierre")))
    df = pd.concat(partes)
    df = df.sort_values("n_eventos", kind="stable").loc[lambda d: ~d.index.duplicated(keep="last")]
    return df.sort_index()


# =============================================================================
# 3. MEMORIA DE LA REGRESIÓN: olvido exponencial o ventana rodante        [2]
# =============================================================================
class _Memoria:
    """Sumas ponderadas causales S_t = Σ_{k≤t} w_{t,k}·z_k.
    Exponencial: w = δ^(t−k), δ = 0.5^(1/vida_media_en_barras)  →  mínimos cuadrados con olvido.
    Ventana: w = 1 en las últimas N barras."""

    def __init__(self, cfg: Config, vida_media_h: float | None):
        por_hora = barras_por_hora(cfg)
        if vida_media_h is not None:
            self.exponencial = True
            hl = max(vida_media_h * por_hora, 1.0)
            self.delta = 0.5 ** (1.0 / hl)
            self.n_nominal = (1 + self.delta) / (1 - self.delta)
            self.ventana = max(10, int(round(self.n_nominal)))
        else:
            self.exponencial = False
            self.ventana = max(10, int(round(cfg.ventana_h * por_hora)))
            self.n_nominal = float(self.ventana)

    @staticmethod
    def _suma_exp(z: np.ndarray, d: float) -> np.ndarray:
        n = len(z)
        if n == 0:
            return np.zeros(0)
        media = pd.Series(z).ewm(alpha=1 - d, adjust=True).mean().to_numpy()
        return media * (1 - d ** np.arange(1, n + 1)) / (1 - d)

    def s1(self, z: np.ndarray) -> np.ndarray:
        """Σ w·z"""
        if self.exponencial:
            return self._suma_exp(z, self.delta)
        return pd.Series(z).rolling(self.ventana, min_periods=1).sum().to_numpy()

    def s2(self, z: np.ndarray, lag: int = 0) -> np.ndarray:
        """Σ w_t·w_{t−lag}·z_t  (z_t ya contiene el producto con el rezago)."""
        if self.exponencial:
            return self.delta ** lag * self._suma_exp(z, self.delta ** 2)
        return pd.Series(z).rolling(max(self.ventana - lag, 1), min_periods=1).sum().to_numpy()

    def maximo(self, z: np.ndarray) -> np.ndarray:
        """max_k w_{t,k}·z_k (z ≥ 0): la mayor aportación individual dentro de la memoria."""
        if not self.exponencial:
            return pd.Series(z).rolling(self.ventana, min_periods=1).max().to_numpy()
        ld = math.log(self.delta)
        i = np.arange(len(z), dtype=float)
        with np.errstate(divide="ignore"):
            lz = np.where(z > 0, np.log(np.where(z > 0, z, 1.0)), -np.inf)
        g = np.maximum.accumulate(lz - i * ld)
        return np.exp(g + i * ld)

    def media(self, z: pd.Series) -> np.ndarray:
        """Media ponderada que ignora huecos (NaN)."""
        ok = z.notna().to_numpy()
        num = self.s1(np.where(ok, z.to_numpy(dtype=float), 0.0))
        den = self.s1(ok.astype(float))
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(den > 1e-12, num / den, np.nan)


def _rezago(z: np.ndarray, lag: int) -> np.ndarray:
    if lag <= 0:
        return z
    if lag >= len(z):
        return np.zeros_like(z)
    return np.r_[np.zeros(lag), z[:-lag]]


def regresion_dinamica(x: np.ndarray, y: np.ndarray, v: np.ndarray, mem: _Memoria, lags: int) -> dict:
    """y_t = λ·x_t + ε_t sin intercepto, ponderada por la memoria, con varianza de Newey-West.
    Todo sale de sumas causales, así que el valor en t solo usa barras ≤ t.

    Var(λ̂) = Ω / (Σ w x²)²,   Ω = Σ w² a_t² + 2 Σ_l (1 − l/(L+1)) Σ w_t w_{t−l} a_t a_{t−l},   a = x·(y − λ̂x)
    Como λ̂ cambia en cada t, Ω se expande en sumas de productos de x e y que no dependen de λ̂."""
    x = np.where(v, x, 0.0)
    y = np.where(v, y, 0.0)
    vf = v.astype(float)
    sxx, sxy, syy = mem.s1(x * x), mem.s1(x * y), mem.s1(y * y)
    sw, sw2 = mem.s1(vf), mem.s2(vf)
    with np.errstate(divide="ignore", invalid="ignore"):
        ok = sxx > 0
        lam = np.where(ok, sxy / np.where(ok, sxx, 1), np.nan)
        r2 = np.where(ok & (syy > 0), sxy ** 2 / (sxx * syy), np.nan)
        n_eff = np.where(sw2 > 0, sw ** 2 / sw2, 0.0)
        omega = mem.s2(x * x * y * y) - 2 * lam * mem.s2(x ** 3 * y) + lam ** 2 * mem.s2(x ** 4)
        for lag in range(1, lags + 1):
            xl, yl = _rezago(x, lag), _rezago(y, lag)
            k = 1 - lag / (lags + 1)
            omega = omega + 2 * k * (mem.s2(x * xl * y * yl, lag)
                                     - lam * mem.s2(x * xl * (x * yl + y * xl), lag)
                                     + lam ** 2 * mem.s2(x * x * xl * xl, lag))
        omega = omega * np.where(n_eff > 1, n_eff / (n_eff - 1), np.nan)
        se = np.sqrt(np.clip(omega, 0, None)) / np.where(ok, sxx, np.nan)
        t = np.where(se > 0, lam / se, np.nan)
        apal = np.where(ok, mem.maximo(x * x) / np.where(ok, sxx, 1), np.nan)
    return {"lam": lam, "se": se, "t": t, "r2": r2, "n_eff": n_eff, "apal": apal}


def lags_newey_west(n: float) -> int:
    return int(max(1, math.floor(4 * (max(n, 1) / 100) ** (2 / 9))))


# =============================================================================
# 4. NORMALIZACIÓN: centros y escalas robustos, causales y por hora del día     [4]
# =============================================================================
def franjas(idx: pd.DatetimeIndex, cfg: Config) -> np.ndarray:
    """Franja horaria (hora de Chicago) del INICIO de cada barra."""
    ancho = max(cfg.franja_min, cfg.barra_min)
    ini = (idx - pd.Timedelta(minutes=cfg.barra_min)).tz_convert(TZ_BOLSA)
    return np.asarray((ini.hour * 60 + ini.minute) // ancho)


def _ventana_escala(cfg: Config) -> int:
    return max(20, int(round(cfg.ventana_escala_h * barras_por_hora(cfg))))


def centro_causal(serie: pd.Series, franja: np.ndarray, cfg: Config, respaldo: bool = False) -> pd.Series:
    """Mediana de las observaciones PREVIAS: misma franja de los últimos días (estacional) o las
    últimas barras (simple). Con respaldo=True, mientras la franja no tiene historia se usan las
    últimas barras (sirve para escalas de recorte, no para el z)."""
    w_esc = _ventana_escala(cfg)
    minimo_rodante = min(cfg.min_obs_z, 30) if respaldo else cfg.min_obs_z
    rodante = serie.shift(1).rolling(w_esc, min_periods=minimo_rodante).median()
    if cfg.normalizacion != "estacional":
        return rodante
    estacional = _por_franja(serie, franja, cfg, "median")
    return estacional.fillna(rodante) if respaldo else estacional


def _obs_por_franja(cfg: Config) -> int:
    return max(1, max(cfg.franja_min, cfg.barra_min) // cfg.barra_min)


def _por_franja(serie: pd.Series, franja: np.ndarray, cfg: Config, estadistico: str, q: float = 0.5) -> pd.Series:
    """Estadístico rodante de las observaciones PREVIAS de la misma franja horaria (últimos dias_norm días)."""
    por_dia = _obs_por_franja(cfg)
    ventana, minimo = cfg.dias_norm * por_dia, cfg.min_dias_franja * por_dia
    previo = serie.groupby(franja).shift(1)
    rod = previo.groupby(franja).rolling(ventana, min_periods=minimo)
    res = rod.median() if estadistico == "median" else rod.quantile(q)
    return res.droplevel(0).reindex(serie.index)


def normalizar(serie: pd.Series, franja: np.ndarray, cfg: Config) -> tuple[pd.Series, pd.Series, pd.Series]:
    """z robusto = (x − centro) / (IQR/1.349) con centro y escala de barras previas.
    Estacional: centro = misma franja horaria de los días previos; escala = dispersión del residuo
    desestacionalizado de las últimas barras (todas las franjas). Devuelve (z, centro, percentil)."""
    w_esc = _ventana_escala(cfg)
    centro = centro_causal(serie, franja, cfg)
    resid = serie - centro
    ref = resid.shift(1).rolling(w_esc, min_periods=cfg.min_obs_z)
    escala = ((ref.quantile(0.75) - ref.quantile(0.25)) / 1.349).clip(lower=cfg.piso_escala_log)
    if cfg.normalizacion == "estacional" and cfg.escala_por_franja:
        # franjas con variabilidad propia (aperturas, cierres) no deben alarmar por su ruido habitual
        iqr = (_por_franja(resid, franja, cfg, "quantile", 0.75)
               - _por_franja(resid, franja, cfg, "quantile", 0.25)) / 1.349
        escala = np.fmax(escala, iqr)
    z = resid / escala
    pct = resid.rolling(w_esc, min_periods=cfg.min_obs_z).rank(pct=True) * 100
    return z, centro, pct


def _log_pos(s: pd.Series) -> pd.Series:
    return np.log(s.where(s > 0))


# =============================================================================
# 5. KYLE'S LAMBDA: medición, regresión, filtros y escala                [1][2][3][4]
# =============================================================================
def calcular_indicador(barras: pd.DataFrame, cfg: Config, tick: float, mult: float) -> pd.DataFrame:
    df = barras.copy()
    ns_barra = cfg.barra_min * 60 * NS
    mem = _Memoria(cfg, cfg.vida_media_h if cfg.ponderacion == "exponencial" else None)
    mem_libro = _Memoria(cfg, cfg.vida_media_libro_h)
    lags = cfg.hac_lags if cfg.hac_lags is not None else lags_newey_west(mem.n_nominal)
    franja = franjas(df.index, cfg)
    df["franja"] = franja

    # --- [1] Precio de referencia: microprice si hay libro; si no, último trade (sin mezclar) ---
    con_libro = bool(df["wmid"].notna().any())
    df["referencia"] = df["wmid"] if con_libro else df["precio"]
    t_ns = df.index.as_unit("ns").asi8
    faltante = np.r_[np.inf, np.diff(t_ns) - ns_barra]
    corte = faltante > cfg.hueco_max_min * 60 * NS
    corte |= (df["instrumento"] != df["instrumento"].shift(1)).to_numpy()   # el roll rompe la serie
    df["segmento"] = np.cumsum(corte)
    ref, ref_prev = df["referencia"], df["referencia"].shift(1)
    df["dP"] = (ref - ref_prev).where(~corte)                                  # puntos
    df["ret"] = df["dP"] / ref_prev
    df["prof"] = (df["prof_bid"] + df["prof_ask"]) / 2
    calidad = (df["cobertura"] >= cfg.cobertura_min) if con_libro else pd.Series(True, index=df.index)
    df["calidad_ok"] = calidad

    # --- Regresor: volumen neto firmado (Kyle) u OFI (Cont-Kukanov-Stoikov) ---
    df["x"] = (df["ofi"] if cfg.regresor == "ofi" else df["delta"]).astype(np.float64)
    v = (df["dP"].notna() & calidad).to_numpy()
    df["v"] = v

    # --- [3] Recorte causal: escala de la misma franja horaria en días previos ---
    def recortar(col: pd.Series) -> pd.Series:
        if cfg.winsor_k <= 0:
            return col
        escala = centro_causal(col.abs().where(v), franja, cfg, respaldo=True) * 1.4826
        limite = cfg.winsor_k * escala.where(escala > 0)
        return col.clip(-limite, limite).where(limite.notna(), col)

    df["x_r"] = recortar(df["x"])
    df["dP_r"] = recortar(df["dP"])
    x_r, y_r = df["x_r"].fillna(0).to_numpy(), df["dP_r"].fillna(0).to_numpy()

    # --- [2] Regresión causal dinámica con errores de Newey-West ---
    reg = regresion_dinamica(x_r, y_r, v, mem, lags)
    lam = reg["lam"]
    df["lambda_crudo_pts"] = lam
    df["se_pts"] = reg["se"]
    df["t_hac"] = reg["t"]
    df["R2"] = reg["r2"]
    df["n_eff"] = reg["n_eff"]
    df["apalancamiento"] = reg["apal"]

    # λ robusta: mediana de pendientes individuales ΔP/x en las barras con flujo relevante
    corte_x = centro_causal(df["x"].abs().where(v), franja, cfg, respaldo=True)
    razon = (df["dP"] / df["x"]).where(v & (df["x"].abs() >= corte_x) & (df["x"] != 0))
    df["lambda_robusta_pts"] = razon.rolling(mem.ventana, min_periods=max(10, int(cfg.n_eff_min // 2))).median()

    # --- [3] Filtros matemáticos ---
    with np.errstate(invalid="ignore", divide="ignore"):
        cociente = lam / df["lambda_robusta_pts"].to_numpy()
    filtros = {
        "f_muestra": reg["n_eff"] >= cfg.n_eff_min,
        "f_signo": lam > 0,
        "f_t": reg["t"] >= cfg.t_min,
        "f_r2": reg["r2"] >= cfg.r2_min,
        "f_apalancamiento": reg["apal"] <= cfg.apalancamiento_max,
        "f_robustez": (cociente >= 1 / cfg.robustez_max) & (cociente <= cfg.robustez_max),
        "f_datos": calidad.to_numpy() & np.isfinite(ref.to_numpy()),
    }
    valido = np.ones(len(df), dtype=bool)
    for nombre, f in filtros.items():
        df[nombre] = f
        valido &= f
    df["valido"] = valido
    df["lambda_pts"] = np.where(valido, lam, np.nan)            # sin ffill: si no se pudo medir, no hay dato

    # --- [1] Direccionalidad real: λ⁺ (compras agresivas) y λ⁻ (ventas agresivas) ---
    # Siempre con el volumen neto del agresor (aunque el regresor principal sea OFI): la pregunta es cuánto
    # mueve el precio quien COMPRA contra quien VENDE.
    xd = x_r if cfg.regresor == "delta" else recortar(df["delta"].astype(np.float64)).fillna(0).to_numpy()
    pos, neg = xd > 0, xd < 0
    reg_p = regresion_dinamica(np.where(pos, xd, 0.0), y_r, v & pos, mem, lags)
    reg_n = regresion_dinamica(np.where(neg, xd, 0.0), y_r, v & neg, mem, lags)
    lp, ln = reg_p["lam"], reg_n["lam"]
    ok_dir = valido & (reg_p["n_eff"] >= cfg.n_eff_min / 2) & (reg_n["n_eff"] >= cfg.n_eff_min / 2) \
        & (lp > 0) & (ln > 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        df["lambda_compra_pts"] = np.where(ok_dir, lp, np.nan)
        df["lambda_venta_pts"] = np.where(ok_dir, ln, np.nan)
        df["asimetria"] = np.where(ok_dir, (lp - ln) / (lp + ln), np.nan)
        df["t_asimetria"] = np.where(ok_dir, (lp - ln) / np.sqrt(reg_p["se"] ** 2 + reg_n["se"] ** 2), np.nan)
    df["direccion"] = np.select([df["t_asimetria"] >= cfg.t_direccion, df["t_asimetria"] <= -cfg.t_direccion],
                                ["alza", "baja"], "neutral")

    # --- [4] Escala institucional ---
    precio = ref.ffill()
    df["lambda_bps"] = df["lambda_pts"] / precio * 1e4                          # bps por contrato
    df["lambda_ticks_100"] = df["lambda_pts"] / tick * 100                      # ticks por 100 contratos
    df["profundidad_kyle"] = tick / df["lambda_pts"]                            # contratos por tick
    df["impacto_bps_1m"] = df["lambda_bps"] * cfg.nocional_ref_usd / (precio * mult)   # bps por US$1M
    df["slippage_bps"] = df["lambda_bps"] * cfg.tamano_orden / 2                # promedio de la orden
    df["costo_usd"] = df["lambda_pts"] * cfg.tamano_orden ** 2 / 2 * mult       # impacto lineal
    ic = 1.96 * df["se_pts"].where(df["valido"])
    df["lambda_bps_ic_bajo"] = (df["lambda_pts"] - ic) / precio * 1e4
    df["lambda_bps_ic_alto"] = (df["lambda_pts"] + ic) / precio * 1e4
    df["lambda_crudo_bps"] = df["lambda_crudo_pts"] / precio * 1e4
    df["lambda_compra_bps"] = df["lambda_compra_pts"] / precio * 1e4
    df["lambda_venta_bps"] = df["lambda_venta_pts"] / precio * 1e4

    # --- [4] Normalización robusta, logarítmica y desestacionalizada ---
    z, centro, pct = normalizar(_log_pos(df["lambda_bps"]), franja, cfg)
    df["lambda_z"], df["lambda_pct"] = z, pct
    df["lambda_tipico_bps"] = np.exp(centro)

    # --- [5] Intensidad de la señal: λ total o cualquiera de sus lados ---
    # Un vacío de un solo lado (solo se retiran los asks, por ejemplo) sube λ⁺ mucho más que el λ promedio.
    # Cada lado se normaliza igual que λ y necesita un umbral más alto (dos oportunidades extra de disparar).
    z_c = normalizar(_log_pos(df["lambda_compra_bps"]), franja, cfg)[0]
    z_v = normalizar(_log_pos(df["lambda_venta_bps"]), franja, cfg)[0]
    df["lambda_compra_z"], df["lambda_venta_z"] = z_c, z_v
    ajuste = cfg.umbral_lado_z - cfg.umbral_z
    df["z_senal"] = np.fmax(df["lambda_z"], np.fmax(z_c, z_v) - ajuste)
    df["disparo"] = np.select([df["lambda_z"] >= df["z_senal"] - 1e-12, z_c - ajuste >= df["z_senal"] - 1e-12],
                              ["λ total", "λ⁺ compras"], "λ⁻ ventas")

    # --- [5] Canal de impacto: Amihud y un segundo estimador de λ con el otro regresor ---
    amihud_barra = (df["ret"].abs() / df["volumen"].where(df["volumen"] > 0)) * 1e6
    df["amihud"] = mem.media(amihud_barra.where(pd.Series(v, index=df.index)))
    df["amihud_z"] = normalizar(_log_pos(df["amihud"]), franja, cfg)[0]
    if con_libro:
        otro = df["delta"] if cfg.regresor == "ofi" else df["ofi"]
        x_alt = recortar(otro.astype(np.float64)).fillna(0).to_numpy()
        reg_a = regresion_dinamica(x_alt, y_r, v, mem, lags)
        lam_alt = np.where((reg_a["n_eff"] >= cfg.n_eff_min) & (reg_a["lam"] > 0), reg_a["lam"], np.nan)
        df["lambda_alt_bps"] = lam_alt / precio * 1e4
        df["lambda_alt_z"] = normalizar(_log_pos(df["lambda_alt_bps"]), franja, cfg)[0]
    else:
        df["lambda_alt_bps"] = df["lambda_alt_z"] = np.nan

    # --- [5] Canal del libro: spread, profundidad y desbalance con memoria corta ---
    df["spread_ew"] = mem_libro.media(df["spread"])
    df["prof_ew"] = mem_libro.media(df["prof"])
    df["desbalance_ew"] = mem_libro.media(df["desbalance"])
    df["spread_z"] = normalizar(_log_pos(df["spread_ew"]), franja, cfg)[0]
    df["prof_z"] = normalizar(_log_pos(df["prof_ew"]), franja, cfg)[0]
    return df


# Nombre de v3, por compatibilidad con otros scripts
calcular_lambda = calcular_indicador


# =============================================================================
# 6. SEÑALES: doble confirmación + persistencia + histéresis + episodios       [5]
# =============================================================================
def canales_confirmacion(df: pd.DataFrame, cfg: Config) -> tuple[pd.Series, pd.Series, bool]:
    c = cfg.umbral_conf_z
    impacto = (df["amihud_z"] >= c) | (df["lambda_alt_z"] >= c)
    libro = (df["spread_z"] >= c) | (df["prof_z"] <= -c)
    hay_libro = bool(df["spread_z"].notna().any() or df["prof_z"].notna().any())
    return impacto, libro, hay_libro


def detectar_senales(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Marca en df: cumple, persistencia, episodio. Devuelve una fila por alerta (inicio de episodio)."""
    impacto, libro, hay_libro = canales_confirmacion(df, cfg)
    cond_lambda = df["valido"] & (df["z_senal"] >= cfg.umbral_z)
    if cfg.confirmacion == "doble":
        cumple = cond_lambda & impacto & (libro if hay_libro else True)
    elif cfg.confirmacion == "simple":
        cumple = cond_lambda & (impacto | libro)
    else:
        cumple = cond_lambda
    cumple = cumple.astype(bool)
    df["conf_impacto"], df["conf_libro"], df["cumple"] = impacto, libro, cumple
    grupos = (~cumple).cumsum()
    persistencia = cumple.astype(int).groupby(grupos).cumsum()
    df["persistencia"] = persistencia
    listo = (persistencia >= cfg.persistencia_min).to_numpy()

    cooldown_ns = int(cfg.cooldown_h * 3600 * NS)
    t_ns = df.index.as_unit("ns").asi8
    z = df["z_senal"].to_numpy()
    seg = df["segmento"].to_numpy()
    episodio = np.zeros(len(df), dtype=np.int64)
    armado, t_ultimo, activo, n_ep = True, None, False, 0
    inicios, fines, z_max = [], [], []
    for i in range(len(df)):
        if activo and ((np.isfinite(z[i]) and z[i] <= cfg.rearme_z) or seg[i] != seg[inicios[-1]]):
            activo = False
            fines[-1] = i
        if np.isfinite(z[i]) and z[i] <= cfg.rearme_z:
            armado = True
        if listo[i] and armado:
            armado = False
            if t_ultimo is None or t_ns[i] - t_ultimo >= cooldown_ns:
                t_ultimo, activo = t_ns[i], True
                n_ep += 1
                inicios.append(i)
                fines.append(None)
                z_max.append(z[i])
        if activo:
            episodio[i] = n_ep
            if np.isfinite(z[i]):
                z_max[-1] = max(z_max[-1], z[i])
    df["episodio"] = episodio

    cols = ["referencia", "lambda_bps", "lambda_ticks_100", "profundidad_kyle", "impacto_bps_1m",
            "slippage_bps", "costo_usd", "z_senal", "disparo", "lambda_z", "lambda_compra_z", "lambda_venta_z",
            "lambda_pct", "lambda_tipico_bps", "amihud_z",
            "lambda_alt_z", "spread_z", "prof_z", "conf_impacto", "conf_libro", "direccion", "asimetria",
            "t_asimetria", "desbalance_ew", "R2", "t_hac", "n_eff", "persistencia"]
    alertas = df.iloc[inicios][cols].copy()
    if len(alertas):
        fin_idx = [f if f is not None else len(df) - 1 for f in fines]
        alertas["fin_episodio"] = df.index[fin_idx]
        alertas["duracion_min"] = (alertas["fin_episodio"] - alertas.index).dt.total_seconds() / 60
        alertas["z_max"] = z_max
        alertas["severidad"] = np.where(alertas["z_max"] >= cfg.z_severa, "severa", "moderada")
    else:
        for col in ("fin_episodio", "duracion_min", "z_max", "severidad"):
            alertas[col] = pd.Series(dtype=object)
    alertas.index.name = "t_alerta"
    return alertas


# =============================================================================
# 7. AUDITORÍA DE IMPACTO POSTERIOR                                         [6]
# =============================================================================
def _pasos(minutos: float, cfg: Config) -> int:
    return max(1, int(round(minutos / cfg.barra_min)))


def _adelante(serie: pd.Series, pasos: int, seg: pd.Series, agg="mean", min_frac=0.6) -> pd.Series:
    """Agregación de `serie` sobre las barras t+1 .. t+pasos, solo si todas están en el mismo tramo
    continuo (sin halt, fin de semana ni roll)."""
    minimo = max(2 if agg == "std" else 1, int(math.ceil(min_frac * pasos)))
    fut = serie.iloc[::-1].rolling(pasos, min_periods=minimo).agg(agg).iloc[::-1].shift(-1)
    return fut.where(seg.shift(-pasos) == seg)


def _ols_hac(X: np.ndarray, y: np.ndarray, lags: int) -> tuple[np.ndarray, np.ndarray, int]:
    """MCO sin intercepto con matriz de covarianza de Newey-West (kernel de Bartlett)."""
    y = np.asarray(y, dtype=float)
    X = np.asarray(X, dtype=float)
    X = X.reshape(len(y), -1) if X.size else np.empty((len(y), max(1, X.shape[-1] if X.ndim > 1 else 1)))
    ok = np.isfinite(X).all(axis=1) & np.isfinite(y)
    X, y = X[ok], y[ok]
    n, k = X.shape
    nan = np.full(k, np.nan)
    if n < 10 * k:
        return nan, nan, n
    xtx = X.T @ X
    try:
        inv = np.linalg.inv(xtx)
    except np.linalg.LinAlgError:
        return nan, nan, n
    b = inv @ (X.T @ y)
    a = X * (y - X @ b)[:, None]
    s = a.T @ a
    for lag in range(1, min(lags, n - 1) + 1):
        g = a[lag:].T @ a[:-lag]
        s += (1 - lag / (lags + 1)) * (g + g.T)
    v = inv @ (s * n / (n - k)) @ inv
    return b, np.sqrt(np.clip(np.diag(v), 0, None)), n


def _pendiente_hac(x: np.ndarray, y: np.ndarray, lags: int) -> tuple[float, float, int]:
    """Pendiente sin intercepto con error estándar de Newey-West sobre una muestra (no rodante)."""
    b, se, n = _ols_hac(np.asarray(x, dtype=float)[:, None], np.asarray(y, dtype=float), lags)
    return float(b[0]), float(se[0]), n


def _p_normal(t: float) -> float:
    return math.erfc(abs(t) / math.sqrt(2)) if np.isfinite(t) else np.nan


def benjamini_hochberg(p: pd.Series) -> pd.Series:
    """q-valores de Benjamini-Hochberg (tasa de falsos descubrimientos)."""
    ok = p.dropna()
    if ok.empty:
        return pd.Series(np.nan, index=p.index)
    orden = ok.sort_values()
    m = len(orden)
    q = (orden * m / np.arange(1, m + 1)).iloc[::-1].cummin().iloc[::-1].clip(upper=1.0)
    return q.reindex(p.index)


def _prueba_emparejada(metrica: pd.Series, en_alerta: pd.Index, base_mask: pd.Series, franja: pd.Series,
                       rng: np.random.Generator, n_perm: int, signos: pd.Series | None = None,
                       peor: str = "alto") -> dict | None:
    """Compara la métrica tras cada alerta con barras de la MISMA franja horaria que no son alerta.
    Exceso_i = s_i·(M_i − μ_franja_i). p-valor por permutación: se reemplaza cada alerta por una barra al
    azar de su franja y se recalcula el exceso medio. "acierto" = la alerta cayó en el 25% peor de su
    franja (arriba del percentil 75, o abajo del 25 si lo peor es un valor bajo, como la profundidad)."""
    base = metrica[base_mask & metrica.notna()]
    pools = {f: g.to_numpy() for f, g in base.groupby(franja[base.index])}
    filas = []
    for t in en_alerta:
        m, f = metrica.get(t, np.nan), franja.get(t)
        if np.isfinite(m) and f in pools and len(pools[f]) >= 5:
            filas.append((t, m, f))
    if len(filas) < 2:
        return None
    s = np.array([1.0 if signos is None else float(signos.get(t, 1.0)) for t, _, _ in filas])
    m_al = np.array([m for _, m, _ in filas])
    mu = np.array([pools[f].mean() for _, _, f in filas])
    corte = np.array([np.quantile(pools[f], 0.75 if peor == "alto" else 0.25) for _, _, f in filas])
    acierto = (m_al > corte) if peor == "alto" else (m_al < corte)
    exceso = s * (m_al - mu)
    obs = exceso.mean()
    perm = np.empty((len(filas), n_perm))
    for k, (_, _, f) in enumerate(filas):
        perm[k] = pools[f][rng.integers(0, len(pools[f]), n_perm)]
    d_perm = (s[:, None] * (perm - mu[:, None])).mean(axis=0)
    p = (1 + np.sum(np.abs(d_perm) >= abs(obs))) / (n_perm + 1)
    sd = exceso.std(ddof=1)
    return {"n": len(filas), "tras la señal": float(np.mean(s * m_al)), "misma hora sin señal": float(np.mean(s * mu)),
            "razón": m_al.mean() / mu.mean() if signos is None and mu.mean() else np.nan,
            "exceso": obs, "t": obs / (sd / math.sqrt(len(filas))) if sd > 0 else np.nan,
            "p_perm": p, "acierto": float(np.mean(acierto)) if signos is None else np.nan}


def auditar(df: pd.DataFrame, alertas: pd.DataFrame, cfg: Config, imprimir=True) -> dict:
    rng = np.random.default_rng(cfg.semilla)
    seg = df["segmento"]
    franja = df["franja"]
    precio = df["referencia"].ffill()
    medido = df["lambda_z"].notna()
    en_episodio = df.get("episodio", pd.Series(0, index=df.index)) > 0
    base_mask = medido & ~en_episodio
    x_r, y_r = df["x_r"].where(df["v"]), df["dP_r"].where(df["v"])
    res: dict[str, pd.DataFrame | dict] = {}

    # --- Calidad de la medición [1][3] ---
    ev, coh = df["vol_eval"].sum(), df["vol_coherente"].sum()
    calidad = {
        "barras": len(df), "barras_con_libro_ok": float(df["calidad_ok"].mean()),
        "lambda_valida": float(df["valido"].mean()),
        "coherencia_agresor": coh / ev if ev > 0 else np.nan,
        "volumen_sin_agresor": df["vol_n"].sum() / df["volumen"].sum() if df["volumen"].sum() else np.nan,
        "R2_mediano": float(df["R2"].median()), "t_hac_mediano": float(df["t_hac"].median()),
        "n_eff_mediano": float(df["n_eff"].median()),
        "lambda_vs_robusta": float((df["lambda_pts"] / df["lambda_robusta_pts"]).median()),
        "rolls": int((df["instrumento"] != df["instrumento"].shift(1)).iloc[1:].sum()),
    }
    for f in [c for c in df.columns if c.startswith("f_")]:
        calidad["pasa_" + f[2:]] = float(df[f].mean())
    res["calidad"] = calidad

    # --- Calibración predictiva: ¿λ_t predice el impacto de t+k? ---
    filas = []
    bench = df["lambda_tipico_bps"] * precio / 1e4                   # λ típico de esa hora, en puntos
    for minutos in cfg.calibracion_min:
        k = _pasos(minutos, cfg)
        mismo = seg.shift(-k) == seg
        xf, yf = x_r.shift(-k), y_r.shift(-k)
        grupos_cal = (("aceptado por los filtros", df["lambda_pts"]),
                      ("λ alto (z ≥ umbral)", df["lambda_pts"].where(df["lambda_z"] >= cfg.umbral_z)),
                      ("rechazado (λ crudo)", df["lambda_crudo_pts"].where(~df["valido"]
                                                                            & (df["lambda_crudo_pts"] > 0))))
        for grupo, lam_t in grupos_cal:
            m = mismo & lam_t.notna() & xf.notna() & yf.notna() & bench.notna()
            if m.sum() < 30:
                continue
            z = (lam_t * xf)[m].to_numpy()
            yy = yf[m].to_numpy()
            b, se, n = _pendiente_hac(z, yy, lags_newey_west(m.sum()) + k)
            sse_m = float(np.sum((yy - z) ** 2))
            sse_b = float(np.sum((yy - (bench * xf)[m].to_numpy()) ** 2))
            filas.append({"k (min)": minutos, "grupo": grupo, "n": n, "β": b, "t(β=1)": (b - 1) / se if se else np.nan,
                          "t(β=0)": b / se if se else np.nan,
                          "R² fuera de muestra vs λ típico": 1 - sse_m / sse_b if sse_b > 0 else np.nan})
    res["calibracion"] = pd.DataFrame(filas)

    # --- Estudio de eventos con base emparejada por hora [6] ---
    idx_al = alertas.index
    signo_dir = alertas["direccion"].map({"alza": 1.0, "baja": -1.0}) if len(alertas) else pd.Series(dtype=float)
    filas = []
    for h in cfg.horizontes_h:
        p = _pasos(h * 60, cfg)
        sxy = _adelante(x_r * y_r, p, seg, "sum")
        sxx = _adelante(x_r * x_r, p, seg, "sum")
        metricas = {
            "volatilidad (bps)": _adelante(df["ret"], p, seg, "std") * 1e4,
            "λ realizado (bps/contrato)": (sxy / sxx.where(sxx > 0)) / precio * 1e4,
            "spread (ticks)": _adelante(df["spread"], p, seg, "mean"),
            "profundidad (contratos)": _adelante(df["prof"], p, seg, "mean"),
            "volumen por barra": _adelante(df["volumen"].astype(float), p, seg, "mean"),
        }
        for nombre, serie in metricas.items():
            peor = "bajo" if nombre.startswith("profundidad") else "alto"
            r = _prueba_emparejada(serie, idx_al, base_mask, franja, rng, cfg.n_permutaciones, peor=peor)
            if r:
                filas.append({"h (horas)": h, "métrica": nombre, **r})
        ret_fut = ((precio.shift(-p) / precio - 1) * 1e4).where(seg.shift(-p) == seg)
        con_dir = signo_dir.dropna().index if len(alertas) else idx_al
        r = _prueba_emparejada(ret_fut, con_dir, base_mask, franja, rng, cfg.n_permutaciones, signos=signo_dir)
        if r:
            filas.append({"h (horas)": h, "métrica": "retorno hacia el lado delgado (bps)", **r})
    ev_df = pd.DataFrame(filas)
    if len(ev_df):
        ev_df["q_BH"] = benjamini_hochberg(ev_df["p_perm"])
        ev_df["significativo"] = ev_df["q_BH"] <= cfg.fdr_q
    res["eventos"] = ev_df

    # --- Respuesta al impulso: impacto permanente vs transitorio (resiliencia) ---
    # P(t+h) − P(t−1) = a_h·x_t + b_h·Σ_{j=1..h} λ̂_{t+j}·x_{t+j} + e.  a_h es cuánto del empuje del flujo de la
    # barra t sigue en el precio h minutos después, descontando el impacto del flujo que llegó luego (que casi
    # siempre va en la misma dirección) con la liquidez local de cada barra. a_h/a_0 < 1 = parte del impacto
    # se revierte: el libro se repone (resiliencia).
    filas = []
    z = df["lambda_z"]
    grupos = {"λ alto (z ≥ umbral)": df["valido"] & (z >= cfg.umbral_z),
              "λ normal (|z| < 1)": df["valido"] & (z.abs() < 1)}
    lam_local = df["lambda_crudo_pts"].where(df["lambda_crudo_pts"] > 0).ffill()
    empuje = (lam_local * df["x_r"]).fillna(0.0)          # impacto esperado del flujo de cada barra, en puntos
    for minutos in cfg.impulso_min:
        h = int(round(minutos / cfg.barra_min))
        if minutos and h == 0:
            continue
        acumulado = (df["referencia"].shift(-h) - df["referencia"].shift(1)).where(seg.shift(-h) == seg.shift(1))
        posterior = empuje.iloc[::-1].rolling(h, min_periods=h).sum().iloc[::-1].shift(-1) if h else None
        for nombre, g in grupos.items():
            m = g & x_r.notna() & acumulado.notna()
            X = x_r[m].to_numpy()[:, None] if h == 0 else np.c_[x_r[m].to_numpy(), posterior[m].to_numpy()]
            b, se, n = _ols_hac(X, acumulado[m].to_numpy(), h + 1)
            esc = (100 / precio[m] * 1e4).mean() if m.any() else np.nan     # puntos/contrato → bps por 100
            filas.append({"minutos": minutos, "grupo": nombre, "n": n, "impacto_bps_100": b[0] * esc,
                          "ee_bps_100": se[0] * esc})
    ir = pd.DataFrame(filas)
    if len(ir):
        ir0 = ir[ir["minutos"] == 0].set_index("grupo")["impacto_bps_100"]
        ir["fraccion_permanente"] = ir["impacto_bps_100"] / ir["grupo"].map(ir0)
    res["impulso"] = ir

    # --- Correlación de rangos (IC) del z de λ con lo que viene ---
    filas = []
    for h in cfg.horizontes_h:
        p = _pasos(h * 60, cfg)
        sxy = _adelante(x_r * y_r, p, seg, "sum")
        sxx = _adelante(x_r * x_r, p, seg, "sum")
        futuros = {"volatilidad futura": _adelante(df["ret"], p, seg, "std"),
                   "λ realizado futuro": sxy / sxx.where(sxx > 0)}
        for nombre, fut in futuros.items():
            m = z.notna() & fut.notna()
            if m.sum() > 30:
                ic = z[m].rank().corr(fut[m].rank())
                n_ef = m.sum() / p
                t = ic * math.sqrt(max(n_ef - 2, 1) / max(1 - ic * ic, 1e-9))
                filas.append({"h (horas)": h, "vs": nombre, "n": int(m.sum()), "IC": ic, "t": t})
    res["ic"] = pd.DataFrame(filas)
    if imprimir:
        imprimir_auditoria(res, df, alertas, cfg)
    return res


# =============================================================================
# 8. REPORTES EN CONSOLA
# =============================================================================
LINEA = "=" * 100


def _fmt(v) -> str:
    return f"{v:,.4f}" if isinstance(v, float) and abs(v) < 10 else (f"{v:,.2f}" if isinstance(v, float) else str(v))


def imprimir_medicion(df: pd.DataFrame, cfg: Config, tick: float) -> None:
    print(f"\n{LINEA}\nMEDICIÓN [1][2][3][4]\n{LINEA}")
    ev, coh = df["vol_eval"].sum(), df["vol_coherente"].sum()
    if ev > 0:
        r = coh / ev
        print(f"Direccionalidad: {r:.1%} del volumen con agresor ocurre del lado esperado del mid "
              f"(compras arriba, ventas abajo).")
        if r < 0.5:
            print("  🚨 EL SIGNO DEL AGRESOR PARECE INVERTIDO: revisa la convención de 'side' (B/A) de tus datos.")
        elif r < 0.9:
            print("  ⚠️  Coherencia baja: puede haber desfase entre trades y libro o datos implícitos.")
    else:
        print("Direccionalidad: sin libro en los datos (fuente trades), no se puede auditar el agresor contra el mid.")
    tv = df["volumen"].sum()
    if tv:
        print(f"Volumen sin agresor (side N): {df['vol_n'].sum() / tv:.2%} "
              f"({'clasificado con la cotización' if cfg.lado_n == 'cotizacion' else 'excluido del flujo'}).")
    pasa = {f[2:]: df[f].mean() for f in df.columns if f.startswith("f_")}
    print(f"λ utilizable en {df['valido'].mean():.1%} de las barras. Pasa cada filtro: "
          + " · ".join(f"{k} {v:.0%}" for k, v in pasa.items()))
    print(f"R² mediano {df['R2'].median():.3f} · t Newey-West mediano {df['t_hac'].median():.1f} · "
          f"muestra efectiva mediana {df['n_eff'].median():.0f} barras")
    ok = df["lambda_bps"].dropna()
    if len(ok):
        print(f"λ mediano: {ok.median():.5f} bps/contrato = {df['lambda_ticks_100'].median():.3f} ticks por 100 "
              f"contratos = {df['impacto_bps_1m'].median():.3f} bps por US$1M")
        print(f"Profundidad de Kyle mediana: {df['profundidad_kyle'].median():,.0f} contratos para mover 1 tick · "
              f"una orden de {cfg.tamano_orden} contratos cuesta ≈ US$ {df['costo_usd'].median():,.0f} "
              f"({df['slippage_bps'].median():.3f} bps de slippage medio)")
        conc = (df["lambda_pts"] / df["lambda_robusta_pts"]).dropna()
        if len(conc):
            print(f"λ regresión / λ robusta (mediana): {conc.median():.2f}  (≈1 = no la dominan unas pocas barras)")
        u = df.dropna(subset=["lambda_bps"]).iloc[-1]
        print(f"Última medición válida ({u.name.tz_convert(TZ_LOCAL):%d-%m %H:%M} CDMX): "
              f"λ={u['lambda_bps']:.5f} bps [{u['lambda_bps_ic_bajo']:.5f}, {u['lambda_bps_ic_alto']:.5f}] · "
              f"z={u['lambda_z']:+.2f} · percentil {u['lambda_pct']:.0f} · dirección {u['direccion']}")


def imprimir_alertas(alertas: pd.DataFrame, cfg: Config) -> None:
    if alertas.empty:
        print("\nSin alertas de vacío de liquidez con los filtros actuales.")
        return
    flecha = {"alza": "▲ vulnerable al alza", "baja": "▼ vulnerable a la baja", "neutral": "◆ simétrico"}
    print(f"\n💧 {len(alertas)} alertas de vacío de liquidez [5] (hora CDMX, al cierre de la barra):")
    for t, r in alertas.iterrows():
        conf = "+".join(n for n, ok in (("impacto", r["conf_impacto"]), ("libro", r["conf_libro"])) if ok)
        print(f"  {t.tz_convert(TZ_LOCAL):%a %d-%m %H:%M}  {r['severidad']:<8} z={r['z_senal']:+.2f} por "
              f"{r['disparo']} (máx {r['z_max']:+.2f}, {r['duracion_min']:.0f} min) · λ={r['lambda_bps']:.5f} bps/contrato "
              f"({r['lambda_bps'] / r['lambda_tipico_bps']:.1f}× lo típico a esa hora) · "
              f"{r['profundidad_kyle']:,.0f} contratos/tick · {cfg.tamano_orden} contratos ≈ US$ "
              f"{r['costo_usd']:,.0f} · {flecha.get(r['direccion'], r['direccion'])} · confirma: {conf or '—'}")


def imprimir_auditoria(res: dict, df: pd.DataFrame, alertas: pd.DataFrame, cfg: Config) -> None:
    pd_opts = dict(index=False, float_format=lambda v: f"{v:,.4f}")
    print(f"\n{LINEA}\nAUDITORÍA DE IMPACTO POSTERIOR [6]\n{LINEA}")
    print("1) Calibración predictiva: y(t+k) = β · λ(t) · x(t+k).  β≈1 → λ predice bien el impacto real.")
    print(res["calibracion"].to_string(**pd_opts) if len(res["calibracion"]) else "  (sin datos)")
    print("   R² fuera de muestra > 0 → el λ dinámico predice mejor que el λ típico de esa hora.")
    print("\n2) Qué pasó DESPUÉS de cada alerta, contra barras de la misma hora sin alerta:")
    ev = res["eventos"]
    if ev.empty:
        print("  (sin alertas suficientes para auditar)")
    else:
        cols = ["h (horas)", "métrica", "n", "tras la señal", "misma hora sin señal", "razón", "t", "p_perm",
                "q_BH", "acierto"]
        print(ev[cols].to_string(**pd_opts))
        print(f"   p_perm = p-valor por permutación · q_BH = Benjamini-Hochberg (significativo si ≤ {cfg.fdr_q:g}) · "
              "acierto = % de alertas en el 25% peor de su hora (azar = 25%).")
    print("\n3) Respuesta al impulso (bps por cada 100 contratos netos de la barra, descontando el flujo posterior):")
    ir = res["impulso"]
    if len(ir):
        tabla = ir.pivot(index="minutos", columns="grupo", values="impacto_bps_100")
        print(tabla.to_string(float_format=lambda v: f"{v:,.4f}"))
        ult = ir[ir["minutos"] == ir["minutos"].max()].set_index("grupo")["fraccion_permanente"]
        print("   Fracción del impacto que sigue ahí al final (100% = permanente; menos = el libro se repuso): " + " · ".join(f"{g}: {v:.0%}" for g, v in ult.items() if np.isfinite(v)))
    print("\n4) ¿El z de λ ordena lo que viene? (correlación de rangos)")
    print(res["ic"].to_string(**pd_opts) if len(res["ic"]) else "  (sin datos)")


# =============================================================================
# 9. DASHBOARDS
# =============================================================================
COLORES = {"fondo": "#fcfcfb", "tinta": "#0b0b0b", "tinta2": "#52514e", "tenue": "#898781",
           "grid": "#e1e0d9", "eje": "#c3c2b7", "s1": "#2a78d6", "s2": "#eb6834", "s3": "#1baf7a",
           "alza": "#2a78d6", "baja": "#e34948", "aviso": "#fab219"}


def _romper_huecos(idx: pd.DatetimeIndex, y: np.ndarray, hueco_ns: int):
    if len(idx) < 2:
        return idx, y
    t = idx.as_unit("ns").asi8
    cortes = np.flatnonzero(np.diff(t) > hueco_ns)
    if cortes.size == 0:
        return idx, y
    s = pd.Series(np.r_[np.asarray(y, dtype=np.float64), np.full(cortes.size, np.nan)],
                  index=idx.append(idx[cortes] + pd.Timedelta(seconds=1))).sort_index(kind="stable")
    return s.index, s.to_numpy()


def _estilo_ejes(ejes, C):
    for ax in np.ravel(ejes):
        ax.set_facecolor(C["fondo"])
        ax.grid(True, color=C["grid"], linewidth=0.6)
        ax.set_axisbelow(True)
        for lado in ("top", "right"):
            ax.spines[lado].set_visible(False)
        for lado in ("left", "bottom"):
            ax.spines[lado].set_color(C["eje"])
        ax.tick_params(colors=C["tenue"], labelsize=9)


def graficar_dashboard(df: pd.DataFrame, alertas: pd.DataFrame, cfg: Config, ruta_png: Path,
                       mostrar: bool = True) -> None:
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    C = COLORES
    hueco = int((cfg.barra_min + cfg.hueco_max_min) * 60 * NS)
    idx = df.index.tz_convert(TZ_LOCAL)
    fig, ejes = plt.subplots(5, 1, figsize=(16, 14.5), sharex=True,
                             gridspec_kw={"height_ratios": [2.0, 1.2, 1.1, 0.8, 0.7]})
    fig.subplots_adjust(left=0.07, right=0.98, bottom=0.06, top=0.9, hspace=0.16)
    fig.patch.set_facecolor(C["fondo"])
    _estilo_ejes(ejes, C)

    def linea(ax, col, **kw):
        t, y = _romper_huecos(idx, df[col].to_numpy(dtype=float), hueco)
        return ax.plot(t, y, **kw)

    episodio = (df.get("episodio", pd.Series(0, index=df.index)) > 0).to_numpy()
    for ax in ejes:
        ax.fill_between(idx, 0, 1, where=episodio, transform=ax.get_xaxis_transform(),
                        color=C["aviso"], alpha=0.22, linewidth=0, step="post")

    # --- 1) Microprice + alertas por dirección ---
    ax = ejes[0]
    linea(ax, "referencia", color=C["tinta"], linewidth=0.9)
    marcas = {"alza": ("^", C["alza"], "alerta: vulnerable al alza"),
              "baja": ("v", C["baja"], "alerta: vulnerable a la baja"),
              "neutral": ("D", C["tinta2"], "alerta: simétrica")}
    handles = []
    for d, (mk, color, etiqueta) in marcas.items():
        sub = alertas[alertas["direccion"] == d] if len(alertas) else alertas
        if len(sub):
            ax.scatter(sub.index.tz_convert(TZ_LOCAL), sub["referencia"], marker=mk, s=70, color=color,
                       edgecolors=C["fondo"], linewidths=2, zorder=4)
        handles.append(Line2D([], [], ls="none", marker=mk, ms=8, markerfacecolor=color,
                              markeredgecolor=C["fondo"], label=etiqueta))
    handles.append(Patch(facecolor=C["aviso"], alpha=0.4, label="episodio de vacío confirmado"))
    ax.set_ylabel("Microprice" if df["wmid"].notna().any() else "Último trade", color=C["tinta2"])
    ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(0, 1.0), ncols=4, frameon=False,
              fontsize=9, labelcolor=C["tinta2"])

    # --- 2) λ con IC 95% y λ típico de esa hora ---
    ax = ejes[1]
    t_lo, lo = _romper_huecos(idx, df["lambda_bps_ic_bajo"].to_numpy(dtype=float), hueco)
    _, hi = _romper_huecos(idx, df["lambda_bps_ic_alto"].to_numpy(dtype=float), hueco)
    ax.fill_between(t_lo, lo, hi, color=C["s1"], alpha=0.12, linewidth=0)
    linea(ax, "lambda_tipico_bps", color=C["tenue"], linewidth=0.9)
    linea(ax, "lambda_bps", color=C["s1"], linewidth=1.0)
    ax.set_ylabel("λ (bps/contrato)", color=C["tinta2"])
    if df["lambda_bps"].notna().any():
        ax.set_ylim(0, float(np.nanpercentile(df["lambda_bps_ic_alto"], 99.5)) * 1.1)
    ax.legend(handles=[Line2D([], [], color=C["s1"], lw=2, label="λ dinámico (válido)"),
                       Patch(facecolor=C["s1"], alpha=0.25, label="IC 95% (Newey-West)"),
                       Line2D([], [], color=C["tenue"], lw=2, label="λ típico a esta hora")],
              loc="upper left", frameon=False, fontsize=8, ncols=3, labelcolor=C["tinta2"])

    # --- 3) Doble confirmación: λ, canal de impacto y canal del libro en z ---
    ax = ejes[2]
    canal_imp = df[["amihud_z", "lambda_alt_z"]].max(axis=1)
    canal_lib = pd.concat([df["spread_z"], -df["prof_z"]], axis=1).max(axis=1)
    etiqueta_l = "λ: z de señal (total, λ⁺ o λ⁻)"
    for serie, color, etiqueta in ((df["z_senal"], C["s1"], etiqueta_l),
                                   (canal_imp, C["s2"], "canal impacto: máx(Amihud, λ-OFI) (z)"),
                                   (canal_lib, C["s3"], "canal libro: máx(spread, −profundidad) (z)")):
        t, y = _romper_huecos(idx, serie.to_numpy(dtype=float), hueco)
        principal = etiqueta == etiqueta_l
        ax.plot(t, y, color=color, linewidth=0.9 if principal else 0.7, alpha=1.0 if principal else 0.8,
                label=etiqueta, zorder=3 if principal else 2)
    ax.axhline(cfg.umbral_z, color=C["tinta"], linewidth=0.9, linestyle=(0, (4, 3)))
    ax.axhline(cfg.umbral_conf_z, color=C["tenue"], linewidth=0.9, linestyle=(0, (1, 3)))
    ax.axhline(0, color=C["eje"], linewidth=0.8)
    picos = df["z_senal"].dropna()
    techo = float(np.nanpercentile(picos, 99.9)) if len(picos) else 6.0
    ax.set_ylim(-4, min(14, max(6, cfg.umbral_z + 3, techo * 1.1)))
    ax.set_ylabel("z desestacionalizado", color=C["tinta2"])
    ax.legend(loc="upper left", frameon=True, facecolor=C["fondo"], edgecolor="none", framealpha=0.9, fontsize=8,
              ncols=3, labelcolor=C["tinta2"])

    # --- 4) Direccionalidad: asimetría (λ⁺ − λ⁻)/(λ⁺ + λ⁻) ---
    ax = ejes[3]
    t, a = _romper_huecos(idx, df["asimetria"].to_numpy(dtype=float), hueco)
    ax.fill_between(t, 0, a, where=a > 0, color=C["alza"], alpha=0.35, linewidth=0, interpolate=True)
    ax.fill_between(t, 0, a, where=a < 0, color=C["baja"], alpha=0.35, linewidth=0, interpolate=True)
    ax.axhline(0, color=C["eje"], linewidth=0.8)
    ax.set_ylim(-1, 1)
    ax.set_ylabel("asimetría λ⁺/λ⁻", color=C["tinta2"])
    ax.legend(handles=[Patch(facecolor=C["alza"], alpha=0.5, label="comprar mueve más: ask delgado"),
                       Patch(facecolor=C["baja"], alpha=0.5, label="vender mueve más: bid delgado")],
              loc="upper left", frameon=False, fontsize=8, ncols=2, labelcolor=C["tinta2"])

    # --- 5) Calidad: t de Newey-West y barras descartadas ---
    ax = ejes[4]
    linea(ax, "t_hac", color=C["tinta2"], linewidth=0.8)
    ax.axhline(cfg.t_min, color=C["tinta"], linewidth=0.9, linestyle=(0, (4, 3)))
    ax.fill_between(idx, 0, 1, where=(~df["valido"]).to_numpy(), transform=ax.get_xaxis_transform(),
                    color=C["tenue"], alpha=0.18, linewidth=0, step="post")
    if df["t_hac"].notna().any():
        ax.set_ylim(0, float(np.nanpercentile(df["t_hac"], 99)) * 1.15)
    ax.set_ylabel("t Newey-West", color=C["tinta2"])
    ax.set_xlabel("Hora CDMX (cierre de barra) · gris = medición descartada por los filtros", color=C["tinta2"])
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(tz=TZ_LOCAL))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d-%m\n%H:%M", tz=TZ_LOCAL))

    memoria = (f"vida media {cfg.vida_media_h:g} h" if cfg.ponderacion == "exponencial"
               else f"ventana {cfg.ventana_h:g} h")
    fig.text(0.07, 0.975, f"{cfg.symbol} · KYLAMBA v4 · λ de Kyle con microprice · barras de {cfg.barra_min} min · "
             f"regresión dinámica ({memoria}) sobre {'OFI' if cfg.regresor == 'ofi' else 'volumen neto'}",
             ha="left", va="top", fontsize=14, fontweight="bold", color=C["tinta"])
    fig.text(0.07, 0.952, f"{idx[0]:%d-%m %H:%M} → {idx[-1]:%d-%m %H:%M} CDMX · z {cfg.normalizacion} "
             f"(franjas de {cfg.franja_min} min, {cfg.dias_norm} días) · filtros: t ≥ {cfg.t_min:g}, R² ≥ "
             f"{cfg.r2_min:g}, n_eff ≥ {cfg.n_eff_min:g}, apalancamiento ≤ {cfg.apalancamiento_max:.0%} · "
             f"confirmación {cfg.confirmacion} · {len(alertas)} alertas",
             ha="left", va="top", fontsize=10, color=C["tinta2"])
    _guardar_figura(fig, ruta_png, mostrar)


def graficar_auditoria(res: dict, cfg: Config, ruta_png: Path, mostrar: bool = True) -> None:
    import matplotlib.pyplot as plt

    C = COLORES
    fig, ejes = plt.subplots(2, 2, figsize=(16, 10))
    fig.subplots_adjust(left=0.07, right=0.98, bottom=0.08, top=0.88, hspace=0.42, wspace=0.18)
    fig.patch.set_facecolor(C["fondo"])
    _estilo_ejes(ejes, C)

    def vacio(ax, texto):
        ax.text(0.5, 0.5, texto, ha="center", va="center", color=C["tenue"], transform=ax.transAxes)

    # a) Respuesta al impulso
    ax = ejes[0, 0]
    ir = res.get("impulso", pd.DataFrame())
    if len(ir):
        for (g, sub), color in zip(ir.groupby("grupo", sort=False), (C["s2"], C["s1"])):
            sub = sub.sort_values("minutos")
            ax.plot(sub["minutos"], sub["impacto_bps_100"], color=color, linewidth=2, marker="o", ms=5,
                    markeredgecolor=C["fondo"], markeredgewidth=1.5, label=g)
            ax.fill_between(sub["minutos"], sub["impacto_bps_100"] - 1.96 * sub["ee_bps_100"],
                            sub["impacto_bps_100"] + 1.96 * sub["ee_bps_100"], color=color, alpha=0.12, linewidth=0)
        ax.axhline(0, color=C["eje"], linewidth=0.8)
        ax.legend(frameon=False, fontsize=9, labelcolor=C["tinta2"])
    else:
        vacio(ax, "sin datos")
    ax.set_title("Resiliencia: impacto de 100 contratos netos que sigue en el precio (sin el flujo posterior)",
                 loc="left", fontsize=11, color=C["tinta"])
    ax.set_xlabel("minutos después de la barra", color=C["tinta2"])
    ax.set_ylabel("bps por 100 contratos", color=C["tinta2"])

    # b) Estudio de eventos: razón contra la misma hora sin señal
    ax = ejes[0, 1]
    ev = res.get("eventos", pd.DataFrame())
    metricas = ["volatilidad (bps)", "λ realizado (bps/contrato)", "spread (ticks)"]
    sub_ev = ev[ev["métrica"].isin(metricas)] if len(ev) else ev
    if len(sub_ev):
        for m, color in zip(metricas, (C["s1"], C["s2"], C["s3"])):
            s = sub_ev[sub_ev["métrica"] == m].sort_values("h (horas)")
            if not len(s):
                continue
            ax.plot(s["h (horas)"], s["razón"], color=color, linewidth=2, label=m)
            sig = s[s["significativo"]]
            ax.scatter(s["h (horas)"], s["razón"], s=40, color=color, edgecolors=C["fondo"], linewidths=1.5, zorder=3)
            ax.scatter(sig["h (horas)"], sig["razón"], s=110, facecolors="none", edgecolors=C["tinta"],
                       linewidths=1.0, zorder=4)
        ax.axhline(1, color=C["tinta"], linewidth=0.9)
        ax.legend(frameon=False, fontsize=9, labelcolor=C["tinta2"], title="círculo = significativo (BH)",
                  title_fontsize=8)
    else:
        vacio(ax, "sin alertas suficientes")
    ax.set_title("Después de la alerta vs la misma hora sin alerta (razón, 1 = igual)",
                 loc="left", fontsize=11, color=C["tinta"])
    ax.set_xlabel("horizonte (horas)", color=C["tinta2"])

    # c) Calibración
    ax = ejes[1, 0]
    cal = res.get("calibracion", pd.DataFrame())
    if len(cal):
        grupos = list(dict.fromkeys(cal["grupo"]))
        ks = sorted(cal["k (min)"].unique())
        ancho = 0.8 / max(len(grupos), 1)
        colores = {"aceptado por los filtros": C["s1"], "λ alto (z ≥ umbral)": C["s2"],
                   "rechazado (λ crudo)": C["tenue"]}
        for j, g in enumerate(grupos):
            color = colores.get(g, C["tinta2"])
            s = cal[cal["grupo"] == g].set_index("k (min)").reindex(ks)
            pos = np.arange(len(ks)) + (j - (len(grupos) - 1) / 2) * ancho
            se = (s["β"] / s["t(β=0)"]).abs()
            ax.errorbar(pos, s["β"], yerr=1.96 * se, fmt="o", color=color, ms=7, capsize=0, elinewidth=2,
                        markeredgecolor=C["fondo"], markeredgewidth=1.5, label=g)
        ax.set_xticks(np.arange(len(ks)), [f"{k} min" for k in ks])
        ax.axhline(1, color=C["tinta"], linewidth=0.9)
        ax.axhline(0, color=C["eje"], linewidth=0.8)
        ax.legend(frameon=False, fontsize=9, labelcolor=C["tinta2"])
    else:
        vacio(ax, "sin datos")
    ax.set_title("Calibración: ¿λ(t) predice el impacto de t+k? (β = 1 perfecto)",
                 loc="left", fontsize=11, color=C["tinta"])
    ax.set_ylabel("β (IC 95%)", color=C["tinta2"])

    # d) IC
    ax = ejes[1, 1]
    ic = res.get("ic", pd.DataFrame())
    if len(ic):
        tipos = list(dict.fromkeys(ic["vs"]))
        hs = sorted(ic["h (horas)"].unique())
        ancho = 0.8 / len(tipos)
        for j, (tp, color) in enumerate(zip(tipos, (C["s1"], C["s2"]))):
            s = ic[ic["vs"] == tp].set_index("h (horas)").reindex(hs)
            pos = np.arange(len(hs)) + (j - (len(tipos) - 1) / 2) * ancho
            ax.bar(pos, s["IC"], width=min(ancho * 0.9, 0.35), color=color, label=tp)
        ax.set_xticks(np.arange(len(hs)), [f"{h:g} h" for h in hs])
        ax.axhline(0, color=C["eje"], linewidth=0.8)
        lo, hi = float(min(0, ic["IC"].min())), float(max(0, ic["IC"].max()))
        ax.set_ylim(lo * 1.3, hi * 1.35 + 1e-3)
        ax.legend(frameon=False, fontsize=9, labelcolor=C["tinta2"], ncols=2, loc="upper left")
    else:
        vacio(ax, "sin datos")
    ax.set_title("Correlación de rangos del z de λ con lo que viene", loc="left", fontsize=11, color=C["tinta"])
    ax.set_ylabel("IC de Spearman", color=C["tinta2"])

    fig.text(0.07, 0.965, f"{cfg.symbol} · KYLAMBA v4 · Auditoría de impacto posterior",
             ha="left", va="top", fontsize=14, fontweight="bold", color=C["tinta"])
    fig.text(0.07, 0.935, "Todo lo que se evalúa ocurre DESPUÉS del cierre de la barra que generó la medición: "
             "la auditoría es fuera de muestra por construcción.", ha="left", va="top", fontsize=10,
             color=C["tinta2"])
    _guardar_figura(fig, ruta_png, mostrar)


def _guardar_figura(fig, ruta_png: Path, mostrar: bool) -> None:
    import matplotlib
    import matplotlib.pyplot as plt
    ruta_png = Path(ruta_png)
    ruta_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(ruta_png, dpi=140, facecolor=COLORES["fondo"], bbox_inches="tight")
    print(f"🖼️  Gráfica guardada en {ruta_png}")
    if mostrar and matplotlib.get_backend().lower() != "agg":
        plt.show()
    plt.close(fig)


# =============================================================================
# 10. DATOS SINTÉTICOS (demo sin costo y pruebas automáticas)
# =============================================================================
_DTYPE_MBP1 = np.dtype([
    ("length", "u1"), ("rtype", "u1"), ("publisher_id", "<u2"), ("instrument_id", "<u4"),
    ("ts_event", "<u8"), ("price", "<i8"), ("size", "<u4"), ("action", "S1"), ("side", "S1"),
    ("flags", "u1"), ("depth", "u1"), ("ts_recv", "<u8"), ("ts_in_delta", "<i4"), ("sequence", "<u4"),
    ("bid_px_00", "<i8"), ("ask_px_00", "<i8"), ("bid_sz_00", "<u4"), ("ask_sz_00", "<u4"),
    ("bid_ct_00", "<u4"), ("ask_ct_00", "<u4")])
_DTYPE_TRADES = np.dtype(_DTYPE_MBP1.descr[:14])


def generar_sintetico(dias: int = 20, inicio: str = "2026-08-03", semilla: int = 7, fuente: str = "mbp-1",
                      estacional: bool = True, vacios: str | list = "auto", invertir_lados: bool = False,
                      precio0: float = 6500.0, roll_dia: int | None = None, escala_actividad: float = 1.0):
    """Mercado tipo Kyle con λ conocido, sesiones de CME (domingo 17:00 a viernes 16:00 CT, pausa diaria
    16:00-17:00), sesión regular más líquida, un roll y "vacíos de liquidez" inyectados.

    Devuelve (DBNStore, verdad) con verdad = {"vacios": DataFrame(inicio, fin, lado, multiplicador),
    "lambda_rth", "lambda_noche"}. Los registros son MBP-1 reales (mismo formato binario que Databento)."""
    import databento_dbn as dbn

    rng = np.random.default_rng(semilla)
    tick = 0.25
    lam_rth, lam_noche = (2e-3, 5e-3) if estacional else (3e-3, 3e-3)
    mu_rth, mu_noche = (0.6, 0.1) if estacional else (0.25, 0.25)
    prof_rth, prof_noche = (150.0, 40.0) if estacional else (90.0, 90.0)
    sigma = 0.065                                                    # ruido de cotización, puntos/√s
    rho = 0.5                                                        # persistencia del flujo de órdenes
    roll_dia = dias // 2 if roll_dia is None else roll_dia

    sesiones, d = [], pd.Timestamp(inicio).normalize()
    while len(sesiones) < dias:
        if d.weekday() < 5:
            a = (d - pd.Timedelta(days=1) + pd.Timedelta(hours=17)).tz_localize(TZ_BOLSA)
            b = (d + pd.Timedelta(hours=16)).tz_localize(TZ_BOLSA)
            sesiones.append((a, b))
        d += pd.Timedelta(days=1)

    if vacios == "auto":
        vacios = []
        for k, (a, b) in enumerate(sesiones):
            if k >= 4 and rng.random() < 0.8:
                ini = a + pd.Timedelta(hours=2) + (b - a - pd.Timedelta(hours=4)) * rng.random()
                vacios.append((ini, ini + pd.Timedelta(minutes=60), rng.choice(["ambos", "ask", "bid"]), 3.0))
    tabla_vacios = pd.DataFrame(vacios, columns=["inicio", "fin", "lado", "multiplicador"])

    t_all, es_trade_all, inst_all = [], [], []
    for k, (a, b) in enumerate(sesiones):
        seg = np.arange(a.value, b.value, NS, dtype=np.int64)
        loc = pd.DatetimeIndex(seg, tz="UTC").tz_convert(TZ_BOLSA)
        minuto = loc.hour * 60 + loc.minute
        minuto = np.asarray(minuto)
        rth = (minuto >= 8 * 60 + 30) & (minuto < 15 * 60)
        mu = np.where(rth, mu_rth, mu_noche) * escala_actividad
        n_tr = rng.poisson(mu)
        n_q = rng.poisson(0.5 * mu + 0.05)
        tt = np.repeat(seg, n_tr) + rng.integers(0, NS, n_tr.sum())
        tq = np.repeat(seg, n_q) + rng.integers(0, NS, n_q.sum())
        t = np.r_[tt, tq]
        tipo = np.r_[np.ones(len(tt), bool), np.zeros(len(tq), bool)]
        orden = np.argsort(t, kind="stable")
        t_all.append(t[orden])
        es_trade_all.append(tipo[orden])
        inst_all.append(np.full(len(t), 101 if k < roll_dia else 202, dtype=np.int64))
    t = np.concatenate(t_all)
    es_trade = np.concatenate(es_trade_all)
    inst = np.concatenate(inst_all)
    n = len(t)

    loc = pd.DatetimeIndex(t, tz="UTC").tz_convert(TZ_BOLSA)
    minuto = np.asarray(loc.hour * 60 + loc.minute)
    rth = (minuto >= 8 * 60 + 30) & (minuto < 15 * 60)
    lam = np.where(rth, lam_rth, lam_noche)
    prof = np.where(rth, prof_rth, prof_noche)
    p_sp2 = np.where(rth, 0.02, 0.10)
    mult_c, mult_v = np.ones(n), np.ones(n)
    en_vacio = np.zeros(n, bool)
    for ini, fin, lado, mlt in vacios:
        m = (t >= pd.Timestamp(ini).value) & (t < pd.Timestamp(fin).value)
        en_vacio |= m
        if lado in ("ambos", "ask"):
            mult_c[m] *= mlt
        if lado in ("ambos", "bid"):
            mult_v[m] *= mlt
    prof = np.where(en_vacio, prof / 3, prof)
    p_sp2 = np.where(en_vacio, 0.6, p_sp2)

    # flujo de órdenes con persistencia, tamaños geométricos e impacto λ·signo·tamaño
    cambia = rng.random(n) > (0.5 + rho / 2)
    signo = np.where(np.cumsum(cambia) % 2 == 0, 1, -1) * np.where(rng.random() < 0.5, 1, -1)
    tam = rng.geometric(1 / 20, n).astype(np.int64)
    impacto = np.where(es_trade, np.where(signo > 0, lam * mult_c, lam * mult_v) * signo * tam, 0.0)
    dt = np.diff(t, prepend=t[0]) / NS
    nueva_sesion = np.r_[True, np.diff(t) > 30 * 60 * NS]
    ruido = sigma * np.sqrt(np.clip(dt, 1e-6, 60)) * rng.standard_normal(n)
    ruido = np.where(nueva_sesion, 2.0 * rng.standard_normal(n), ruido)
    salto_roll = np.r_[0.0, np.where(np.diff(inst) != 0, 30.0, 0.0)]
    m_post = precio0 + np.cumsum(impacto + ruido + salto_roll)
    m_pre = m_post - impacto

    def libro(m_val):
        s = np.where(rng.random(n) < p_sp2, 2, 1)
        bid = tick * np.floor(m_val / tick - (s - 1) / 2)
        f = np.clip((m_val - bid) / (s * tick), 0.03, 0.97)
        total = np.maximum(4, np.round(2 * prof * rng.lognormal(0, 0.25, n))).astype(np.int64)
        qb = np.maximum(1, np.round(f * total)).astype(np.int64)
        qa = np.maximum(1, total - qb)
        return bid, bid + s * tick, qb, qa

    b_pre, a_pre, qb_pre, qa_pre = libro(m_pre)
    b_post, a_post, qb_post, qa_post = libro(m_post)

    # registros: trade (sin F_LAST, con el libro previo) + libro posterior (F_LAST); cotizaciones sueltas
    it = np.flatnonzero(es_trade)
    lado = np.where(signo[it] > 0, b"B", b"A")
    if invertir_lados:
        lado = np.where(lado == b"B", b"A", b"B")
    sin_ag = rng.random(len(it)) < 0.01
    lado = np.where(sin_ag, b"N", lado)
    precio_tr = np.where(signo[it] > 0, a_pre[it], b_pre[it])

    total = n + len(it)
    rec = np.zeros(total, dtype=_DTYPE_MBP1)
    pos_tr = it + np.arange(len(it))                                # el trade va antes de su libro
    pos_lib = np.arange(n) + np.searchsorted(it, np.arange(n), side="right")
    for campo, val_tr, val_lib in (
            ("ts_event", t[it], t), ("instrument_id", inst[it], inst),
            ("bid_px_00", b_pre[it], b_post), ("ask_px_00", a_pre[it], a_post),
            ("bid_sz_00", qb_pre[it], qb_post), ("ask_sz_00", qa_pre[it], qa_post)):
        if campo.endswith("px_00"):
            val_tr, val_lib = np.round(val_tr * PRICE_SCALE), np.round(val_lib * PRICE_SCALE)
        rec[campo][pos_tr] = val_tr
        rec[campo][pos_lib] = val_lib
    rec["action"][pos_tr] = b"T"
    rec["side"][pos_tr] = lado
    rec["price"][pos_tr] = np.round(precio_tr * PRICE_SCALE)
    rec["size"][pos_tr] = tam[it]
    rec["flags"][pos_tr] = 0
    rec["action"][pos_lib] = np.where(es_trade, b"C", b"M")
    rec["side"][pos_lib] = np.where(rng.random(n) < 0.5, b"B", b"A")
    rec["price"][pos_lib] = rec["bid_px_00"][pos_lib]
    rec["size"][pos_lib] = rec["bid_sz_00"][pos_lib]
    rec["flags"][pos_lib] = F_LAST
    rec["bid_ct_00"] = np.maximum(1, rec["bid_sz_00"] // 5)
    rec["ask_ct_00"] = np.maximum(1, rec["ask_sz_00"] // 5)
    rec["ts_recv"] = rec["ts_event"] + 50_000
    rec["publisher_id"] = 1
    rec["sequence"] = np.arange(total) % (2 ** 32)
    if fuente == "trades":
        rec = rec[rec["action"] == b"T"]
        rec["flags"] = F_LAST
        out = np.zeros(len(rec), dtype=_DTYPE_TRADES)
        for campo in _DTYPE_TRADES.names:
            out[campo] = rec[campo]
        out["length"], out["rtype"] = _DTYPE_TRADES.itemsize // 4, 0
        rec, esquema = out, dbn.Schema.TRADES
    else:
        rec["length"], rec["rtype"] = _DTYPE_MBP1.itemsize // 4, 1
        esquema = dbn.Schema.MBP_1
    meta = dbn.Metadata(dataset="GLBX.MDP3", start=int(sesiones[0][0].value), stype_in=dbn.SType.CONTINUOUS,
                        stype_out=dbn.SType.INSTRUMENT_ID, schema=esquema, symbols=["ES.n.0"],
                        end=int(sesiones[-1][1].value))
    store = db.DBNStore.from_bytes(meta.encode() + rec.tobytes())
    verdad = {"vacios": tabla_vacios, "lambda_rth": lam_rth, "lambda_noche": lam_noche, "registros": len(rec)}
    return store, verdad


def comparar_con_verdad(alertas: pd.DataFrame, verdad: dict, tolerancia_min: float = 90) -> dict:
    """Solo para la demo: qué vacíos inyectados se detectaron y cuántas alertas fueron falsas."""
    vac = verdad["vacios"]
    tol = pd.Timedelta(minutes=tolerancia_min)
    detectados, verdaderas, dir_ok, dir_n = 0, set(), 0, 0
    for _, v in vac.iterrows():
        dentro = alertas[(alertas.index >= v["inicio"]) & (alertas.index <= v["fin"] + tol)]
        if len(dentro):
            detectados += 1
            verdaderas.update(dentro.index)
            esperado = {"ask": "alza", "bid": "baja"}.get(v["lado"])
            if esperado:
                dir_n += 1
                dir_ok += int(dentro["direccion"].iloc[0] == esperado)
    return {"vacios": len(vac), "detectados": detectados, "alertas": len(alertas),
            "falsas": len(alertas) - len(verdaderas), "direccion_correcta": dir_ok, "direccion_evaluable": dir_n}


# =============================================================================
# 11. DATOS REALES (key, caché, costo) Y LIVE
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
    "  • Copia la key vigente en el portal de Databento, sección API keys\n"
    "    (guía: https://databento.com/docs/portal/api-keys).\n"
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
            print(f"❌ Databento rechazó la API key {_mascara(key)} (error {e.http_status}).")
            if venia_de_setx:
                print("   Esa key venía de la variable guardada en tu computadora: actualízala con setx.")
            if not _interactivo():
                break
            print("   Pega la key vigente para intentar de nuevo (Ctrl+C para salir).")
    sys.exit("No se pudo autenticar con Databento.\n" + AYUDA_KEY)


def _ruta_cache(cfg: Config, inicio: str, fin: str) -> Path:
    carpeta = _ruta(cfg.cache_dir)
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta / (_nombre_seguro(cfg.dataset, cfg.symbol, inicio, fin, cfg.fuente) + ".dbn.zst")


def _descargar(cliente, cfg: Config, inicio: str, fin: str, ruta: Path | None) -> db.DBNStore:
    params = dict(dataset=cfg.dataset, symbols=cfg.symbol, stype_in=cfg.stype_in, schema=cfg.fuente,
                  start=inicio, end=fin)
    if ruta is None:
        return cliente.timeseries.get_range(**params)
    temporal = ruta.with_name(ruta.name + ".parcial")
    temporal.unlink(missing_ok=True)
    descarga = cliente.timeseries.get_range(**params, path=temporal)
    del descarga
    gc.collect()
    temporal.replace(ruta)
    return db.DBNStore.from_file(ruta)


def _revisar_costo(cliente, cfg: Config, tramos: list[tuple[str, str]]) -> None:
    costo = 0.0
    for inicio, fin in tramos:
        costo += cliente.metadata.get_cost(dataset=cfg.dataset, symbols=cfg.symbol, stype_in=cfg.stype_in,
                                           schema=cfg.fuente, start=inicio, end=fin)
    print(f"💵 Costo estimado de la descarga: US$ {costo:,.2f}")
    if costo > cfg.costo_max_usd:
        sys.exit(f"💰 El costo (US$ {costo:,.2f}) supera tu tope de US$ {cfg.costo_max_usd:,.2f}.\n"
                 f"   Si estás de acuerdo:  --costo-max {math.ceil(costo) + 1}\n"
                 "   Más barato: --fuente trades (pierdes microprice, OFI y libro) o un rango más corto.")


def obtener_datos(cfg: Config) -> db.DBNStore:
    """Una sola descarga (MBP-1 ya trae los trades). Misma caché y mismo nombre de archivo que v3."""
    ruta = _ruta_cache(cfg, cfg.start, cfg.end)
    if ruta.exists() and cfg.usar_cache:
        print(f"📂 Usando caché local: {ruta}\n   (para bajarla otra vez desde Databento: --sin-cache)")
        return db.DBNStore.from_file(ruta)
    if ruta.exists():
        print(f"♻️  Ignorando la caché local y volviendo a descargar: {ruta.name}")
    cliente = conectar_historico()
    _revisar_costo(cliente, cfg, [(cfg.start, cfg.end)])
    print(f"📡 Descargando {cfg.fuente} a {ruta.parent} …")
    return _descargar(cliente, cfg, cfg.start, cfg.end, ruta)


def barras_historicas_por_dia(cfg: Config, tick: float, inicio: pd.Timestamp, fin: pd.Timestamp,
                              cliente=None) -> pd.DataFrame:
    """Calentamiento del Live: días completos (UTC) en caché, uno por archivo, para no pagar dos veces;
    el tramo del día en curso se baja sin guardar."""
    cliente = cliente or conectar_historico()
    dias = pd.date_range(inicio.floor("D"), fin, freq="D", tz="UTC")
    tramos = [(a, min(a + pd.Timedelta(days=1), fin)) for a in dias if a < fin]
    faltan = [(a, b) for a, b in tramos
              if not (b - a == pd.Timedelta(days=1) and _ruta_cache(cfg, a.isoformat(), b.isoformat()).exists())]
    if faltan:
        _revisar_costo(cliente, cfg, [(a.isoformat(), b.isoformat()) for a, b in faltan])
    partes = []
    for a, b in tramos:
        completo = b - a == pd.Timedelta(days=1)
        ruta = _ruta_cache(cfg, a.isoformat(), b.isoformat()) if completo else None
        if ruta is not None and ruta.exists():
            store = db.DBNStore.from_file(ruta)
        else:
            print(f"📡 Calentamiento: {a:%Y-%m-%d %H:%M} → {b:%Y-%m-%d %H:%M} UTC")
            store = _descargar(cliente, cfg, a.isoformat(), b.isoformat(), ruta)
        partes.append(construir_barras(store, cfg, tick))
    return unir_barras(partes)


def guardar_resultados(df: pd.DataFrame, alertas: pd.DataFrame, auditoria: dict, cfg: Config,
                       sufijo: str) -> Path:
    carpeta = _ruta(cfg.salida_dir)
    carpeta.mkdir(parents=True, exist_ok=True)
    salida = df.copy()
    salida.insert(0, "hora_cdmx", salida.index.tz_convert(TZ_LOCAL))
    salida.to_csv(carpeta / f"barras_{sufijo}.csv")
    al = alertas.copy()
    if len(al):
        al.insert(0, "hora_cdmx", al.index.tz_convert(TZ_LOCAL))
    al.to_csv(carpeta / f"alertas_{sufijo}.csv")
    for nombre in ("calibracion", "eventos", "impulso", "ic"):
        tabla = auditoria.get(nombre)
        if isinstance(tabla, pd.DataFrame):
            tabla.to_csv(carpeta / f"auditoria_{nombre}_{sufijo}.csv", index=False)
    resumen = {"indicador": IDENTIFICADOR, "config": asdict(cfg),
               "calidad": {k: (None if isinstance(v, float) and not np.isfinite(v) else v)
                           for k, v in auditoria.get("calidad", {}).items()},
               "alertas": len(alertas)}
    (carpeta / f"resumen_{sufijo}.json").write_text(json.dumps(resumen, indent=2, ensure_ascii=False, default=str),
                                                    encoding="utf-8")
    print(f"💾 Barras, alertas, auditoría y resumen guardados en {carpeta}")
    return carpeta


def memoria_live_h(cfg: Config) -> float:
    """Horas de barras que el Live conserva para que la última barra salga igual que en el histórico:
    días de la normalización estacional + ventana de escala (ambas en días hábiles) + memoria de λ."""
    dias_habiles = cfg.dias_norm + cfg.ventana_escala_h / 23
    return dias_habiles * 24 * 7 / 5 + 12 * (cfg.vida_media_h if cfg.ponderacion == "exponencial" else cfg.ventana_h) + 48


class SesionLive:
    """Recibe barras cerradas, recalcula el indicador con exactamente la misma matemática del histórico y
    avisa cuando la última barra abre un episodio de vacío."""

    def __init__(self, cfg: Config, tick: float, mult: float, historial: pd.DataFrame | None = None,
                 imprimir: bool = True):
        self.cfg, self.tick, self.mult, self.imprimir = cfg, tick, mult, imprimir
        self.barras = historial if historial is not None else unir_barras([])
        self.alertas_emitidas: list[pd.Timestamp] = []
        self.ultimo: pd.Series | None = None

    def al_cerrar(self, t_cierre: pd.Timestamp, fila: dict) -> None:
        nueva = _tipos_barra(pd.DataFrame([fila], columns=COLUMNAS_BARRA,
                                          index=pd.DatetimeIndex([t_cierre], name="t_cierre")))
        self.barras = unir_barras([self.barras, nueva])
        limite = t_cierre - pd.Timedelta(hours=memoria_live_h(self.cfg))
        self.barras = self.barras[self.barras.index > limite]
        df = calcular_indicador(self.barras, self.cfg, self.tick, self.mult)
        alertas = detectar_senales(df, self.cfg)
        u = df.iloc[-1]
        self.ultimo = u
        if self.imprimir:
            hora = t_cierre.tz_convert(TZ_LOCAL)
            marca = "✓" if u["valido"] else "·"
            print(f"[LIVE] {hora:%d-%m %H:%M} {marca} λ={u['lambda_bps']:.5f} bps/contrato  z={u['z_senal']:+.2f}  "
                  f"t={u['t_hac']:.1f}  R²={u['R2']:.2f}  spread={u['spread']:.2f} ticks  dir={u['direccion']}")
        if len(alertas) and alertas.index[-1] == t_cierre:
            self.alertas_emitidas.append(t_cierre)
            if self.imprimir:
                imprimir_alertas(alertas.iloc[[-1]], self.cfg)
                carpeta = _ruta(self.cfg.salida_dir)
                carpeta.mkdir(parents=True, exist_ok=True)
                ruta = carpeta / "alertas_live.csv"
                alertas.iloc[[-1]].to_csv(ruta, mode="a", header=not ruta.exists())


def correr_live(cfg: Config, tick: float, mult: float, cliente_live=None, historial: pd.DataFrame | None = None,
                cliente_hist=None, imprimir: bool = True) -> SesionLive:
    """Mismo motor y misma matemática que el histórico, barra a barra, con calentamiento histórico para
    que la normalización estacional tenga días previos desde la primera barra.
    Si se pasa `historial` (barras ya construidas), el Live continúa justo donde terminan."""
    ahora = pd.Timestamp.now(tz="UTC")
    if historial is not None and len(historial):
        t0 = historial.index.max()
    elif cfg.dias_historial_live > 0:
        cliente_hist = cliente_hist or conectar_historico()
        fin_disp = ahora - pd.Timedelta(minutes=15)
        try:
            rango = cliente_hist.metadata.get_dataset_range(dataset=cfg.dataset)
            fin_disp = pd.Timestamp(rango.get("schema", {}).get(cfg.fuente, {}).get("end") or rango["end"])
        except Exception:
            pass
        fin_disp = fin_disp.tz_convert("UTC") if fin_disp.tzinfo else fin_disp.tz_localize("UTC")
        t0 = max(min(fin_disp, ahora).floor(f"{cfg.barra_min}min"), (ahora - pd.Timedelta(hours=23)).ceil("h"))
        print(f"🔥 Calentando con {cfg.dias_historial_live} días de historia (hasta {t0:%d-%m %H:%M} UTC)…")
        historial = barras_historicas_por_dia(cfg, tick, t0 - pd.Timedelta(days=cfg.dias_historial_live), t0,
                                              cliente_hist)
    else:
        t0 = ahora.floor(f"{cfg.barra_min}min") - pd.Timedelta(hours=12)
    sesion = SesionLive(cfg, tick, mult, historial, imprimir=imprimir)
    motor = MotorBarras(cfg, tick, al_cerrar_barra=sesion.al_cerrar)
    cliente_live = cliente_live or db.Live(reconnect_policy="reconnect")
    cliente_live.subscribe(dataset=cfg.dataset, schema=cfg.fuente, symbols=cfg.symbol,
                           stype_in=cfg.stype_in, start=int(t0.value))
    frontera = int(t0.value)
    if imprimir:
        print("🔴 Live conectado: primero llega el replay desde el fin del calentamiento… (Ctrl+C para salir)")
    try:
        for rec in cliente_live:
            if isinstance(rec, (db.MBP1Msg, db.TradeMsg)):
                if rec.ts_event < frontera:
                    continue                      # ya estaba en el histórico
                motor.procesar(rec)
            elif isinstance(rec, db.ErrorMsg):
                print(f"⚠️  Databento: {rec.err}")
    except KeyboardInterrupt:
        print("\nCerrando…")
    finally:
        cliente_live.stop()
    return sesion


# =============================================================================
# 12. MAIN
# =============================================================================
def analizar(barras: pd.DataFrame, cfg: Config, tick: float, mult: float, imprimir: bool = True):
    df = calcular_indicador(barras, cfg, tick, mult)
    alertas = detectar_senales(df, cfg)
    if imprimir:
        imprimir_medicion(df, cfg, tick)
        imprimir_alertas(alertas, cfg)
    auditoria = auditar(df, alertas, cfg, imprimir=imprimir)
    return df, alertas, auditoria


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description="KYLAMBA v4: λ de Kyle institucional con microprice (Databento)")
    ap.add_argument("--demo", action="store_true", help="datos sintéticos: sin API key ni costo")
    ap.add_argument("--dias-demo", type=int, default=20, dest="dias_demo")
    ap.add_argument("--motor", choices=("vectorizado", "incremental"), default="vectorizado")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--archivo", help="archivo .dbn/.dbn.zst ya descargado")
    ap.add_argument("--simbolo")
    ap.add_argument("--inicio")
    ap.add_argument("--fin")
    ap.add_argument("--barra", type=int, help="minutos por barra (1 por defecto)")
    ap.add_argument("--vida-media", type=float, dest="vida_media", help="horas de memoria de λ")
    ap.add_argument("--ponderacion", choices=("exponencial", "ventana"))
    ap.add_argument("--fuente", choices=("mbp-1", "trades"))
    ap.add_argument("--regresor", choices=("delta", "ofi"))
    ap.add_argument("--normalizacion", choices=("estacional", "simple"))
    ap.add_argument("--confirmacion", choices=("doble", "simple", "ninguna"))
    ap.add_argument("--umbral", type=float, help="z de λ para alertar")
    ap.add_argument("--tamano-orden", type=int, dest="tamano_orden")
    ap.add_argument("--costo-max", type=float, dest="costo_max")
    ap.add_argument("--sin-cache", action="store_true", dest="sin_cache")
    ap.add_argument("--salida")
    ap.add_argument("--sin-grafica", action="store_true")
    ap.add_argument("--no-mostrar", action="store_true", help="guarda las gráficas sin abrir ventanas")
    args = ap.parse_args(argv)

    cambios = {k: v for k, v in (
        ("symbol", args.simbolo), ("start", args.inicio), ("end", args.fin), ("barra_min", args.barra),
        ("vida_media_h", args.vida_media), ("ponderacion", args.ponderacion), ("fuente", args.fuente),
        ("regresor", args.regresor), ("normalizacion", args.normalizacion), ("confirmacion", args.confirmacion),
        ("umbral_z", args.umbral), ("tamano_orden", args.tamano_orden), ("costo_max_usd", args.costo_max),
        ("salida_dir", args.salida), ("usar_cache", False if args.sin_cache else None)) if v is not None}
    cfg = replace(CFG, **cambios)
    if args.demo and args.salida is None:
        cfg = replace(cfg, salida_dir=str(Path(cfg.salida_dir) / "demo"))
    for aviso in validar_config(cfg):
        print(f"⚠️  {aviso}")
    tick, mult = especificacion(cfg)
    if args.live:
        correr_live(cfg, tick, mult)
        return {}

    verdad = None
    if args.demo:
        print(f"🧪 Demo: generando {args.dias_demo} sesiones sintéticas de MBP-1 con vacíos de liquidez conocidos…")
        store, verdad = generar_sintetico(dias=args.dias_demo, fuente=cfg.fuente, semilla=cfg.semilla)
    elif args.archivo:
        store = db.DBNStore.from_file(args.archivo)
    else:
        store = obtener_datos(cfg)
    t0 = time.perf_counter()
    barras = construir_barras(store, cfg, tick, args.motor)
    if len(barras) < 200:
        sys.exit("Muy pocas barras para estimar λ: usa un rango más largo o barras más cortas.")
    print(f"✅ {len(barras):,} barras de {cfg.barra_min} min en {time.perf_counter() - t0:.1f} s [motor {args.motor}]")
    df, alertas, auditoria = analizar(barras, cfg, tick, mult)
    if verdad is not None:
        r = comparar_con_verdad(alertas, verdad)
        auditoria["demo"] = r
        print(f"\n🧪 Verdad conocida: se inyectaron {r['vacios']} vacíos; se detectaron {r['detectados']} · "
              f"alertas falsas: {r['falsas']} de {r['alertas']} · dirección correcta en "
              f"{r['direccion_correcta']} de {r['direccion_evaluable']} vacíos de un solo lado.")

    sufijo = _nombre_seguro(cfg.symbol, f"{df.index[0]:%Y%m%d}", f"{df.index[-1]:%Y%m%d}", f"{cfg.barra_min}min")
    carpeta = guardar_resultados(df, alertas, auditoria, cfg, sufijo)
    if not args.sin_grafica:
        mostrar = not args.no_mostrar
        graficar_dashboard(df, alertas, cfg, carpeta / f"dashboard_kylamba_{sufijo}.png", mostrar)
        graficar_auditoria(auditoria, cfg, carpeta / f"auditoria_kylamba_{sufijo}.png", mostrar)
    return {"barras": df, "alertas": alertas, "auditoria": auditoria}


if __name__ == "__main__":
    main()
