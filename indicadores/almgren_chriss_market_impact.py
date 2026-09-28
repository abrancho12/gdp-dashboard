# -*- coding: utf-8 -*-
"""
ALMGREN-CHRISS AC v2 — ejecución óptima con impacto y riesgo medidos en unidades que cierran
Datos: Databento OHLCV-1m (GLBX.MDP3), por SESIÓN de Globex (17:00 → 16:00 CT).

Qué hace, en una línea: calcula cómo ejecutar un bloque de contratos equilibrando el impacto
de ir rápido contra el riesgo de ir lento (Almgren-Chriss), con σ, volumen y precio en
unidades que cierran y estimados SÓLO con las sesiones anteriores al día que se ejecuta; y
después mide cómo le fue a cada estrategia ese día y a lo largo de toda la historia.

LO QUE PEDISTE, HECHO A FONDO

  1. OPTIMIZACIÓN DEL TRADE-OFF ENTRE IMPACTO Y RIESGO. Tres soluciones que se verifican
     entre sí: la fórmula cerrada del artículo, el sistema tridiagonal exacto cuando σ y η
     cambian por tramo, y el óptimo numérico con el modelo completo: σ y volumen de cada
     tramo del perfil intradía MEDIDO, impacto temporal cóncavo en la participación
     (β = 0.6), impacto permanente, spread y tope de participación (25 % por omisión). Con
     β = 1 y la varianza del artículo coinciden a menos de 1e-5 contratos, y sus fórmulas
     (20)-(21) de E y V coinciden con las sumas. El óptimo se busca sobre los TRAMOS, con el
     tope como cota exacta: arrancando de cualquier lado da el mismo resultado a 1e-11.

  2. PARÁMETRO DE AVERSIÓN AL RIESGO. λ en 1/USD, así que significa algo: cuánto costo
     esperado aceptas por quitar varianza. Tres maneras de darlo: directo (--lambda), por
     vida media (--vida-media: se busca el λ cuya trayectoria ÓPTIMA ejecuta la mitad en
     esos minutos) o, por omisión, el λ que minimiza E + z·SD al 95 % (Almgren-Chriss §4).
     En ese óptimo el precio marginal del riesgo, 2λ·SD, sale exactamente z = 1.645, aun
     con el tope activo. Tu RISK_AVERSION = 1e-5, leído en 1/USD, da una vida media de
     3.7-5.1 min. El panel κ contra λ muestra además el techo que pone el tope: por encima de
     cierto λ ya no se puede ir más rápido.

  3. COEFICIENTES DE IMPACTO. ε (medio spread + comisión), η₀ = 0.142 y β = 0.6 del impacto
     temporal, γ₀ = 0.314 del permanente (Almgren, Thum, Hauptmann y Li 2005), el η lineal
     equivalente que usa la AC de libro, y la curva de impacto por participación contra la
     de tu script. σ y el volumen se MIDEN; η₀, β y γ₀ no se pueden medir con OHLCV (haría
     falta tu historial de ejecuciones) y lo digo en vez de fingir una regresión: el tornado
     y el arrepentimiento miden cuánto importa que estén mal.

  4. COMPARACIÓN DE ESTRATEGIAS. Ocho: AC óptima, AC clásica, VWAP, TWAP, POV 10 %, tus
     Front-loaded y Back-loaded, y ejecución inmediata. Cada una con E, SD, E + z·SD, su
     descomposición (spread, impacto temporal, permanente, riesgo), cómo le fue EL DÍA de
     ejecución con sus precios reales, y una réplica sobre ~220 sesiones previas con VaR y
     CVaR 95 %. Promedio de 4 simulaciones, 5 000 NQ en la sesión regular (bps):

         estrategia       E + z·SD   CVaR95 réplica
         AC óptima          27.9        34.8
         Inmediata *        26.8        33.2      * pasa del tope: 46 % del primer tramo
         POV 10 %           37.1        44.6
         AC clásica         38.4        45.9
         Front-loaded       80.2        95.7
         VWAP               93.3       111.0
         TWAP               99.0       117.7
         Back-loaded       116.1       136.8

  5. ANÁLISIS DE SENSIBILIDAD VISUAL. Ocho paneles, y cada punto RE-OPTIMIZA: trayectorias
     según λ (tu panel 5, ahora sí se mueven), κT contra λ (tu panel 6, con la fórmula
     discreta), urgencia en λ × η₀, costo al 95 % en σ × η₀, tornado, arrepentimiento,
     horizonte y tamaño del tramo.

  Dos resultados que conviene saber. Sin aversión al riesgo y con impacto en función de la
  participación, el óptimo no es el TWAP del artículo: es el VWAP (coincide a 2 contratos de
  5 000). Y con 5 000 NQ (~1 % del volumen diario) al 95 %, lo óptimo es ir rápido: vida
  media de ~5 min, pegado al tope de participación en la apertura.

QUÉ SE MIDIÓ. Todo sobre sesiones simuladas de 1 min tipo NQ (perfil intradía en U,
volatilidad diaria e intradía estocástica, colas gruesas, tick de 0.25, rolls). Además de la
tabla de arriba:
  · Pronóstico de σ fuera de muestra (QLIKE): HAR 0.095 · σ de ayer 0.134 · media de 22
    sesiones 0.125; t de Diebold-Mariano contra la de ayer 3.3.
  · Tamaño del tramo con la varianza DISCRETA del artículo: E + λV de 15.0 bps con tramos de
    1 min, 8.7 con 5 y 3.9 con 30. Tramos más gruesos parecen más baratos porque lo que se
    ejecuta dentro de un tramo no carga riesgo: el modelo "vende" media hora de flujo al
    precio del inicio. Con la tenencia bajando en línea recta dentro del tramo: 16.9, 16.9
    y 32.3 bps. Tramos gruesos cuestan más, como debe ser: dan menos opciones.

QUÉ FALLABA EN EL SCRIPT QUE MANDASTE (los comentarios [v2] lo marcan en el código)

  · LA API KEY ESTÁ ESCRITA EN LA LÍNEA 15. Dala por publicada y regenérala. Aquí se lee de
    DATABENTO_API_KEY, igual que en tus módulos de z-score, VWAP y anomalías.

  · LAS UNIDADES NO CIERRAN, Y POR ESO TU SENSIBILIDAD NO SE MUEVE. T = 1 "normalizado",
    τ = 1/78, σ por slice de 5 min, η de una fórmula sin unidades, y κ = √(λσ²/η) mezclando
    las tres escalas. Medido con tus propias fórmulas: κT ≤ 0.01 para TODOS los λ de tu
    lista (0 a 1e-3), así que tus seis trayectorias son el mismo TWAP a menos de 0.003
    contratos de 5 000. Y el costo que reporta, "Cost/Contract (bps)", sale entre 657 y
    1 200 bps —6.6 % a 12 % del nocional— cuando el TWAP cuesta 1.5-1.7 bps con la ley de
    Almgren et al. y el volumen real.

  · LOS COEFICIENTES DE ALMGREN ET AL. (2005) ESTÁN CAMBIADOS. Tu η usa 0.314, que en el
    artículo es el impacto PERMANENTE; el temporal es 0.142. El exponente 0.6 va sobre la
    PARTICIPACIÓN (tu tasa entre la del mercado), no sobre el volumen del slice solo. Y el
    permanente es lineal en X/ADV, no ADV^0.6.

  · ESTIMA CON EL DÍA QUE VA A EJECUTAR. σ, volumen por slice y ADV salen de la sesión del
    20 de agosto, la misma que ejecuta: a las 08:30 nada de eso existe. Y ese "ADV" es el
    volumen de la ventana de ese día, no un promedio. Aquí todo sale de sesiones previas y
    el día de ejecución sólo se usa al final, para evaluar (una prueba lo verifica:
    alterar ese día no cambia σ, perfil ni ADV).

  · TIRA LOS PRIMEROS 20 MINUTOS. df['vol'] = rolling(20).std() no se usa nunca, pero el
    dropna() posterior borra las primeras 20 barras de la ventana: 08:30-08:50, justo lo más
    volátil y más líquido de la sesión, fuera de σ y del volumen.

  · TU VENTANA EN UTC SE MUEVE CON EL HORARIO DE VERANO. 13:30-20:00 UTC es 08:30-15:00 CT
    en agosto pero 07:30-14:00 CT en enero: entra el dato de las 07:30 y se pierde la última
    hora. Aquí la ventana va en hora de Chicago.

  · κ CONTINUO EN UN PROBLEMA DISCRETO. √(λσ²/η) sólo vale con τ → 0; el artículo usa
    cosh(κτ) − 1 = ½τ²λσ²/η̃ con η̃ = η − ½γτ.

  · FALTA ε Y FALTA EL VWAP. El spread y la comisión no están en el costo, y el docstring de
    compare_strategies promete "VWAP (basado en volumen)", que nunca se implementa.

  · PRICE_SCALE DIVIDE DOS VECES: con databento moderno to_df() ya entrega float y el NQ
    queda en 0.00002. Y exit() en vez de sys.exit().

CÓMO SE USA
    pip install numpy pandas scipy matplotlib databento
    python almgren_chriss_market_impact.py --pruebas          # 24 pruebas, sin red
    python almgren_chriss_market_impact.py --simulacion       # todo, con datos simulados
    python almgren_chriss_market_impact.py                    # tu sesión: 2026-08-20
    python almgren_chriss_market_impact.py --fecha 2026-09-25 --contratos 2000 --horizonte 120
    python almgren_chriss_market_impact.py --var-conf 0.75    # menos aversión al riesgo
    python almgren_chriss_market_impact.py --lambda 1e-5      # tu λ, en 1/USD
    python almgren_chriss_market_impact.py --vida-media 60    # la mitad en una hora
    python almgren_chriss_market_impact.py --paso 1 --part-max 0.10 --lado compra
    python almgren_chriss_market_impact.py --telegram               # resumen + 3 tableros
    python almgren_chriss_market_impact.py --telegram-solo-alertas  # sólo si hay algo raro
  La hora de inicio va en hora de CHICAGO; el reporte y el plan muestran también la de CDMX.

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
  Almgren, R. y Chriss, N. (2000), "Optimal execution of portfolio transactions", Journal of
      Risk 3(2). — el modelo, la trayectoria sinh, κ discreto y las fórmulas de E y V.
  Almgren, R., Thum, C., Hauptmann, E. y Li, H. (2005), "Direct estimation of equity market
      impact", Risk 18(7). — η₀ = 0.142, β = 3/5 sobre la participación, γ₀ = 0.314.
  Almgren, R. (2003), "Optimal execution with nonlinear impact functions and trading-enhanced
      risk", Applied Mathematical Finance 10(1). — impacto no lineal.
  Corsi, F. (2009), "A simple approximate long-memory model of realized volatility", JFEc 7(2).
  Patton, A. (2011), "Volatility forecast comparison using imperfect volatility proxies",
      Journal of Econometrics 160(1). — QLIKE.
  Zhang, L., Mykland, P. y Aït-Sahalia, Y. (2005), "A tale of two time scales", JASA 100.
  Databento: https://databento.com/docs — OHLCV-1m, símbolos continuos .n.0.
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
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

try:
    from scipy.linalg import solve_banded
    from scipy.optimize import minimize, minimize_scalar
except ModuleNotFoundError:                                   # pragma: no cover
    sys.exit("Falta scipy:  pip install scipy")

try:
    import databento as db
except ModuleNotFoundError:
    db = None

IDENTIFICADOR = "almgren-chriss-ac-v2"
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)
np.seterr(all="ignore")

# --- Constantes de la sesión de CME Globex ---
MINUTOS_SESION = 1380            # 17:00 → 16:00 CT (23 horas)
ANCHO = 1440                     # la matriz cubre el día completo por si llegan barras en la pausa
DESFASE_H = 7                    # hora CT + 7 h → la sesión que abre a las 17:00 cae en su fecha

ESPECIFICACIONES = {
    "NQ": (20.0, 0.25), "MNQ": (2.0, 0.25), "ES": (50.0, 0.25), "MES": (5.0, 0.25),
    "YM": (5.0, 1.0), "MYM": (0.5, 1.0), "RTY": (50.0, 0.1), "M2K": (5.0, 0.1),
    "CL": (1000.0, 0.01), "MCL": (100.0, 0.01), "GC": (100.0, 0.1), "MGC": (10.0, 0.1),
}


# =============================================================================
# 1. CONFIGURACIÓN
# =============================================================================
@dataclass(frozen=True)
class Config:
    # --- Datos ---
    dataset: str = "GLBX.MDP3"
    symbol: str = "NQ.n.0"
    stype_in: str = "continuous"
    fecha: str = "2026-08-20"              # sesión a ejecutar (la de tu script)
    dias_calentamiento: int = 200          # historia previa: σ, perfiles, ADV, réplica
    cache_dir: str = "datos_databento"
    usar_cache: bool = True
    salida_dir: str = "salidas_ac"
    costo_max_usd: float = 25.0

    # --- Contrato ---
    multiplicador: float | None = None     # None = según el símbolo (NQ: 20 USD por punto)
    tick: float | None = None
    spread_ticks: float = 1.0              # diferencial compra-venta supuesto, en ticks
    comision_usd: float = 2.0              # por contrato y por lado, todo incluido (supuesto)

    # --- Sesión CME ---
    tz_mercado: str = "America/Chicago"
    tz_local: str = "America/Mexico_City"
    hueco_max_min: int = 30
    cobertura_min: float = 0.80

    # --- Volatilidad ---
    freq_min: int = 5                      # RV de cada sesión: 5 min submuestreado
    har_ventana: int = 500
    har_min: int = 60

    # --- Perfil intradía ---
    perfil_dias: int = 120
    perfil_suavizado: int = 5

    # --- Ejecución (los valores de tu script) ---
    lado: str = "venta"                    # "venta" | "compra"
    contratos: float = 5000.0              # ORDER_SIZE
    inicio_ct: str = "08:30"               # tu ventana 13:30 UTC = 08:30 CT sólo en verano
    horizonte_min: int = 390               # EXECUTION_HORIZON
    paso_min: int = 5                      # 78 slices de 5 min
    aversion: float | None = None          # λ en 1/USD; None = se deduce de var_conf
    var_conf: float = 0.95                 # λ tal que se minimiza E + z·SD (Almgren-Chriss §4)
    vida_media_min: float | None = None    # alternativa: λ cuya trayectoria óptima da esta vida media
    part_max: float = 0.25                 # participación máxima por tramo (POV); ≥ 1 = sin tope
    pov: float = 0.10                      # tasa de la estrategia POV de referencia
    lambda_tu_script: float = 1e-5         # tu RISK_AVERSION, para traducirlo a unidades reales

    # --- Impacto (Almgren, Thum, Hauptmann y Li 2005) ---
    eta0: float = 0.142
    beta: float = 0.6
    gamma0: float = 0.314
    adv_dias: int = 20

    # --- Réplica histórica ---
    replica_dias: int = 250
    escalar_vol: bool = True
    sin_deriva: bool = True

    # --- Simulación ---
    sim_sesiones: int = 220
    sim_saltos: int = 12
    sim_rolls: int = 2
    sim_semilla: int = 0

    # --- Telegram ---
    telegram_percentil_alerta: float = 0.90


CFG = Config()
CARPETA_SCRIPT = Path(__file__).resolve().parent


def _raiz_symbol(symbol: str) -> str:
    return re.split(r"[.\s]", symbol.strip().upper())[0]


def multiplicador(cfg: Config) -> float:
    if cfg.multiplicador is not None:
        return float(cfg.multiplicador)
    raiz = _raiz_symbol(cfg.symbol)
    if raiz not in ESPECIFICACIONES:
        sys.exit(f"No conozco el multiplicador de {cfg.symbol}. Pásalo con --multiplicador "
                 f"(USD por punto) y --tick.")
    return ESPECIFICACIONES[raiz][0]


def tamano_tick(cfg: Config) -> float:
    if cfg.tick is not None:
        return float(cfg.tick)
    return ESPECIFICACIONES.get(_raiz_symbol(cfg.symbol), (0.0, 0.25))[1]


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


def _usd(x, ancho=12) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "—".rjust(ancho)
    return f"{v:>{ancho},.0f}" if np.isfinite(v) else "—".rjust(ancho)


def _anual(var_diaria) -> np.ndarray:
    """Varianza de una sesión → volatilidad anualizada en %."""
    return np.sqrt(np.asarray(var_diaria, dtype=float) * 252.0) * 100.0


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


# =============================================================================
# 2. SESIONES DE CME
# =============================================================================
# [v2] Tu script pide START_DATE = "2026-08-20T13:30:00" y END_DATE = "…T20:00:00" en UTC.
# En agosto (horario de verano de Chicago, UTC−5) eso es 08:30-15:00 CT: la sesión regular.
# En enero (UTC−6) la MISMA línea da 07:30-14:00 CT: entra el dato macro de las 07:30 y se
# pierde la última hora. Aquí la ventana se define en hora de Chicago, que es el reloj del
# mercado, y la conversión a UTC la hace la zona horaria.

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


def rv_submuestreada(L: np.ndarray, k: int) -> float:
    vals = [float(np.sum(np.diff(L[o::k]) ** 2)) for o in range(k) if len(L[o::k]) > 2]
    return float(np.mean(vals)) if vals else np.nan


# =============================================================================
# 3. SIMULADOR — la verdad contra la que se mide todo
# =============================================================================
def perfiles_teoricos() -> tuple[np.ndarray, np.ndarray]:
    """Forma intradía de la varianza y del volumen de un índice de CME (en U, con picos)."""
    m = np.arange(ANCHO, dtype=float)
    abre, cierra, datos = minuto_de_sesion("08:30"), minuto_de_sesion("15:00"), \
        minuto_de_sesion("07:30")
    rth = (m >= abre) & (m < cierra)
    var = np.full(ANCHO, 0.30)
    var[rth] = 1.0 + 2.2 * np.exp(-(m[rth] - abre) / 18.0) + 0.9 * np.exp(-(cierra - m[rth]) / 12.0)
    var += 2.5 * np.exp(-np.abs(m - datos) / 2.5)                  # dato macro de las 07:30 CT
    var += 0.6 * np.exp(-np.abs(m - minuto_de_sesion("02:00")) / 30.0)   # apertura europea
    vol = np.full(ANCHO, 0.12)
    vol[rth] = 1.0 + 1.8 * np.exp(-(m[rth] - abre) / 25.0) + 1.6 * np.exp(-(cierra - m[rth]) / 10.0)
    vol += 1.2 * np.exp(-np.abs(m - datos) / 4.0)
    for x in (var, vol):
        x[MINUTOS_SESION:] = 0.0
    return var / var.sum(), vol / vol.sum()


def simular(cfg: Config, n_sesiones: int | None = None, semilla: int | None = None,
            n_saltos: int | None = None, n_rolls: int | None = None,
            tamano_salto: tuple[float, float] = (0.45, 1.3), ruido: bool = True,
            inicio: str = "2025-06-02") -> tuple[pd.DataFrame, dict]:
    """
    Barras de 1 min tipo NQ con sesiones de Globex, perfil intradía en U, volatilidad diaria
    e intradía estocástica persistente (colas gruesas a 1 min), ruido de compra-venta,
    precio redondeado al tick, pausa de 16:00-17:00 CT con su hueco, fin de semana, ROLLS
    del continuo y SALTOS EN MINUTOS CONOCIDOS.

    Devuelve (barras al estilo de to_df(), verdad). La verdad trae, por sesión, la varianza
    integrada del proceso eficiente sin saltos y la variación de los saltos: es contra lo que
    se mide cada estimador.
    """
    S = int(n_sesiones or cfg.sim_sesiones)
    n_saltos = cfg.sim_saltos if n_saltos is None else int(n_saltos)
    n_rolls = cfg.sim_rolls if n_rolls is None else int(n_rolls)
    rng = np.random.default_rng(cfg.sim_semilla if semilla is None else semilla)
    tick = tamano_tick(cfg)
    fechas = pd.bdate_range(inicio, periods=S)
    f_var, f_vol = perfiles_teoricos()
    W = MINUTOS_SESION

    # --- varianza diaria: log-AR(1) persistente, vol media ~20 % anual ---
    mu, phi, sd_eta = math.log(0.20 ** 2 / 252.0), 0.95, 0.20
    ln_s2 = np.empty(S)
    ln_s2[0] = mu
    for i in range(1, S):
        ln_s2[i] = mu + phi * (ln_s2[i - 1] - mu) + rng.normal(0.0, sd_eta)
    s2 = np.exp(ln_s2)

    # --- retornos eficientes de 1 min: volatilidad intradía estocástica y PERSISTENTE ---
    # log-vol AR(1) minuto a minuto (vida media ~46 min). Da colas gruesas a 1 min
    # (curtosis ≈ 3·e^{4s²} ≈ 4.9) sin que la volatilidad salte de un minuto al siguiente,
    # que es lo que distingue una difusión de un proceso con saltos.
    s_h, phi_h = 0.35, 0.985
    h = np.empty((S, W))
    h[:, 0] = rng.normal(0.0, s_h, S)
    eps_h = rng.normal(0.0, s_h * math.sqrt(1 - phi_h ** 2), (S, W))
    for j in range(1, W):
        h[:, j] = phi_h * h[:, j - 1] + eps_h[:, j]
    sd_min = np.sqrt(s2[:, None] * f_var[None, :W]) * np.exp(h - s_h ** 2)
    r_dif = sd_min * rng.normal(0.0, 1.0, (S, W))
    iv = np.sum(sd_min ** 2, axis=1)            # varianza integrada: ∫σ², no Σr²

    # --- saltos en minutos conocidos ---
    salto = np.zeros((S, W))
    tiene = np.zeros(S, dtype=bool)
    tam = np.zeros(S)
    min_salto = np.full(S, -1)
    if n_saltos > 0:
        cand = np.arange(25, S)
        for s in rng.choice(cand, size=min(n_saltos, len(cand)), replace=False):
            m = (minuto_de_sesion("07:30") if rng.random() < 0.3
                 else int(rng.integers(minuto_de_sesion("08:31"), minuto_de_sesion("14:55"))))
            k = rng.uniform(*tamano_salto) * rng.choice([-1.0, 1.0])
            salto[s, m] = k * math.sqrt(s2[s])
            tiene[s], tam[s], min_salto[s] = True, k, m
    jv = np.sum(salto ** 2, axis=1)

    # --- huecos entre sesiones: pausa diaria y fin de semana ---
    lunes = fechas.dayofweek.to_numpy() == 0
    hueco = rng.normal(0.0, 1.0, S) * np.sqrt(s2) * np.where(lunes, 0.35, 0.10)
    hueco[0] = 0.0

    # --- rolls: el contrato siguiente cotiza con prima; el continuo salta de nivel ---
    roll = np.zeros(S, dtype=bool)
    if n_rolls > 0:
        for i in range(1, n_rolls + 1):
            roll[min(S - 1, int(i * S / (n_rolls + 1)))] = True
    prima = np.where(roll, 0.009, 0.0)
    instrumento = 1000 + np.cumsum(roll)

    # --- nivel del precio eficiente ---
    r_tot = r_dif + salto
    fin_sesion = np.cumsum(hueco + r_tot.sum(axis=1))
    ini_sesion = fin_sesion - r_tot.sum(axis=1)                  # ya incluye el hueco
    base = math.log(21000.0) + np.cumsum(prima)                   # log de la prima acumulada
    log_ef = ini_sesion[:, None] + np.cumsum(r_tot, axis=1)
    log_ef0 = ini_sesion

    # --- observado: rebote de compra-venta y redondeo al tick ---
    def observar(lp):
        p = np.exp(lp)
        if ruido:
            p = p + rng.choice([-0.5, 0.5], size=p.shape) * tick
        return np.maximum(tick, np.round(p / tick) * tick)

    cierre = observar(log_ef + base[:, None])
    apertura = np.empty_like(cierre)
    apertura[:, 1:] = cierre[:, :-1]
    apertura[:, 0] = observar(log_ef0 + base)
    # Máximo y mínimo dentro del minuto: los de un puente browniano entre la apertura y el
    # cierre eficientes (fórmula exacta), negociados en el ask y en el bid.
    a_ef = np.concatenate([log_ef0[:, None], log_ef[:, :-1]], axis=1)
    b_ef = log_ef
    raiz = lambda: np.sqrt((b_ef - a_ef) ** 2 - 2.0 * sd_min ** 2 * np.log(rng.random((S, W))))
    alto = np.ceil((np.exp(0.5 * (a_ef + b_ef + raiz()) + base[:, None]) + 0.5 * tick) / tick) * tick
    bajo = np.floor((np.exp(0.5 * (a_ef + b_ef - raiz()) + base[:, None]) - 0.5 * tick) / tick) * tick
    alto = np.maximum(alto, np.maximum(apertura, cierre))
    bajo = np.minimum(bajo, np.minimum(apertura, cierre))

    # --- volumen ---
    v_dia = 560_000.0 * (s2 / math.exp(mu)) ** 0.35 * np.exp(rng.normal(0, 0.15, S))
    volumen = np.maximum(1, np.round(v_dia[:, None] * f_vol[None, :W]
                                     * np.exp(rng.normal(0, 0.5, (S, W))
                                              - 0.125))).astype("int64")

    # --- minutos sin operaciones (sin barra), sólo de madrugada ---
    madrugada = np.zeros(W, dtype=bool)
    madrugada[minuto_de_sesion("22:00"):minuto_de_sesion("06:00")] = True
    hay = ~(madrugada[None, :] & (rng.random((S, W)) < 0.01))
    hay[:, 0] = True
    hay[:, W - 1] = True

    # --- marcas de tiempo (inicio de la barra, UTC) ---
    pared = (np.asarray(fechas, dtype="datetime64[ns]")[:, None]
             - np.timedelta64(DESFASE_H, "h")
             + np.arange(W).astype("timedelta64[m]")[None, :])
    idx = (pd.DatetimeIndex(pared[hay])
           .tz_localize(cfg.tz_mercado, ambiguous="NaT", nonexistent="NaT"))
    ok = ~idx.isna()
    df = pd.DataFrame({
        "open": apertura[hay][ok], "high": alto[hay][ok], "low": bajo[hay][ok],
        "close": cierre[hay][ok], "volume": volumen[hay][ok],
        "instrument_id": np.repeat(instrumento, W).reshape(S, W)[hay][ok],
        "symbol": cfg.symbol}, index=idx[ok].tz_convert("UTC"))
    df.index.name = "ts_event"

    saltos_t = []
    for s in np.flatnonzero(tiene):
        t, _ = reloj(fechas[s], int(min_salto[s]), cfg)
        saltos_t.append(t.tz_convert("UTC"))
    verdad = {
        "sesiones": pd.DataFrame({"iv": iv, "jv": jv, "salto": tiene, "tam_salto": tam,
                                  "minuto_salto": min_salto, "roll": roll, "s2": s2},
                                 index=pd.DatetimeIndex(fechas)),
        "saltos_utc": pd.DatetimeIndex(saltos_t),
    }
    return df, verdad


# =============================================================================
# 4. DATOS — Databento, con la key FUERA del código
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
    "  • La que estaba escrita en la línea 15 de Almgren_Chriss_Market_Impact_Model.py hay que\n"
    "    darla por publicada: regenérala en https://databento.com/docs/portal/api-keys\n"
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
    """
    [v2] Tu script descarga SÓLO la sesión que va a ejecutar y de ahí saca σ, el volumen y
    el ADV: a las 08:30 de ese día nada de eso existe todavía. Aquí se descarga la historia
    previa (para estimar) y el día de ejecución (para medir después cómo le fue a cada
    estrategia, que es lo único que ese día puede aportar sin hacer trampa).
    """
    carpeta = _ruta(cfg.cache_dir)
    carpeta.mkdir(parents=True, exist_ok=True)
    f = pd.Timestamp(cfg.fecha).normalize()
    inicio = (f - pd.Timedelta(days=cfg.dias_calentamiento)).strftime("%Y-%m-%dT%H:%M:%S")
    fin = (f + pd.Timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    esquema = "ohlcv-1m"
    ruta = carpeta / (_nombre_seguro(cfg.dataset, cfg.symbol, inicio, fin, esquema) + ".dbn.zst")
    if ruta.exists() and cfg.usar_cache:
        print(f"📂 Usando caché local: {ruta.name}")
        return db.DBNStore.from_file(ruta)
    cliente = cliente or conectar()
    params = dict(dataset=cfg.dataset, symbols=cfg.symbol, stype_in=cfg.stype_in,
                  schema=esquema, start=inicio, end=fin)
    costo = cliente.metadata.get_cost(**params)
    print(f"💵 Costo estimado: US$ {costo:,.2f}")
    if costo > cfg.costo_max_usd:
        sys.exit(f"💰 El costo (US$ {costo:,.2f}) supera tu tope de "
                 f"US$ {cfg.costo_max_usd:,.2f}.\n"
                 f"   Si estás de acuerdo:  --costo-max {math.ceil(costo) + 1}")
    temporal = ruta.with_name(ruta.name + ".parcial")
    temporal.unlink(missing_ok=True)
    print(f"📡 Descargando {cfg.symbol} {esquema} desde {inicio[:10]} hasta {fin[:10]} …")
    cliente.timeseries.get_range(**params, path=temporal)
    temporal.replace(ruta)
    return db.DBNStore.from_file(ruta)


def preparar_barras(tienda, cfg: Config) -> pd.DataFrame:
    """
    OHLCV-1m → barras limpias con su sesión de Globex y su minuto de sesión.

    [v2] Tu script divide los precios entre PRICE_SCALE = 1e9. Con databento moderno,
    to_df() ya entrega float (verificado en la 0.87: price_type="float" por omisión), así
    que el NQ queda en 0.00002. Los retornos logarítmicos no cambian —la escala se cancela—
    pero el panel de precio sí, y cualquier costo en dólares, que es justo lo que necesita
    el módulo de ejecución. Aquí la escala se DETECTA: sólo se divide si llegan enteros de
    punto fijo.

    [v2] Los rolls se detectan por instrument_id. La columna `symbol` no sirve: con
    stype_in="continuous" databento la llena con el símbolo PEDIDO ("NQ.n.0") en todas las
    filas, así que nunca cambia en el roll.
    """
    df = tienda.to_df() if hasattr(tienda, "to_df") else tienda
    df = df.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("Los datos no traen índice temporal.")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    col = {c.lower(): c for c in df.columns}
    for req in ("open", "high", "low", "close"):
        if req not in col:
            raise ValueError(f"Falta la columna {req!r} ({list(df.columns)}).")
    df = df.rename(columns={col[c]: c for c in ("open", "high", "low", "close", "volume",
                                                "instrument_id") if c in col})
    if "volume" not in df.columns:
        df["volume"] = 0
    if "instrument_id" not in df.columns:
        df["instrument_id"] = 0

    for c in ("open", "high", "low", "close"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    escala = "float"
    mediana = float(np.nanmedian(df["close"])) if len(df) else np.nan
    if np.isfinite(mediana) and mediana > 1e7:
        for c in ("open", "high", "low", "close"):
            df[c] = df[c] / 1e9
        escala = "punto fijo ÷ 1e9"
    for c in ("open", "high", "low", "close"):
        malo = (df[c] <= 0) | (df[c] >= 9.2e9) | ~np.isfinite(df[c])
        df.loc[malo, c] = np.nan
    df["open"] = df["open"].fillna(df["close"])
    df = df.dropna(subset=["close"])
    if df.empty:
        raise ValueError("No quedaron barras con cierre válido tras la limpieza.")
    df["high"] = np.fmax(df["high"], np.fmax(df["open"], df["close"]))
    df["low"] = np.fmin(df["low"], np.fmin(df["open"], df["close"]))
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype("int64")
    df["instrument_id"] = pd.to_numeric(df["instrument_id"], errors="coerce").fillna(-1)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    ses, minuto = sesion_y_minuto(df.index, cfg.tz_mercado)
    df["sesion"] = ses
    df["minuto"] = minuto
    df.attrs["escala"] = escala
    return df[["open", "high", "low", "close", "volume", "instrument_id", "sesion", "minuto"]]


# =============================================================================
# 5. SESIONES, HISTORIA Y PRONÓSTICO DE σ
# =============================================================================
@dataclass
class Sesiones:
    fechas: pd.DatetimeIndex
    L: np.ndarray              # S×1440 log-precio LIMPIO al cierre de cada minuto (NaN fuera)
    L0: np.ndarray             # log de la apertura de la primera barra
    r: np.ndarray              # S×1440 retornos de 1 min limpios
    vol: np.ndarray            # S×1440 volumen
    alto: np.ndarray
    bajo: np.ndarray
    cierre: np.ndarray         # último cierre REAL de la sesión (precio)
    m_ini: np.ndarray
    m_fin: np.ndarray
    cobertura: np.ndarray
    completa: np.ndarray
    n_cortes: np.ndarray
    r_noche: np.ndarray        # retorno de la pausa / fin de semana (NO entra en el RV)
    roll: np.ndarray           # la sesión abre con un contrato distinto al de la anterior

    @property
    def S(self) -> int:
        return len(self.fechas)

    def rejilla(self, s: int) -> np.ndarray:
        """Log-precios de la sesión s: apertura y luego el cierre de cada minuto."""
        return np.concatenate([[self.L0[s]], self.L[s, self.m_ini[s]:self.m_fin[s] + 1]])


def construir_sesiones(barras: pd.DataFrame, cfg: Config) -> Sesiones:
    """
    Matrices sesión × minuto con los retornos LIMPIOS:
      · minuto sin barra (nadie operó): precio anterior → retorno 0, y el siguiente retorno
        cubre el hueco (interpolación de tick previo, la estándar);
      · hueco > hueco_max_min o cambio de instrument_id DENTRO de la sesión: ese retorno se
        reemplaza por el apertura-cierre de la barra (el salto entre precios no es retorno);
      · la primera barra de la sesión aporta su apertura-cierre. El hueco desde el cierre
        anterior (pausa, fin de semana, roll) se guarda aparte en r_noche y NO entra al RV.
    """
    fechas, si = np.unique(barras["sesion"].to_numpy(), return_inverse=True)
    mi = barras["minuto"].to_numpy().astype(int)
    S, W = len(fechas), ANCHO

    def matriz(col, relleno=np.nan):
        M = np.full((S, W), relleno, dtype=float)
        M[si, mi] = barras[col].to_numpy(dtype=float)
        return M

    C, O, H, Lb = matriz("close"), matriz("open"), matriz("high"), matriz("low")
    V, I = matriz("volume", 0.0), matriz("instrument_id")
    obs = np.isfinite(C)
    col = np.arange(W)
    ultimo = np.maximum.accumulate(np.where(obs, col[None, :], -1), axis=1)
    previo = np.concatenate([np.full((S, 1), -1), ultimo[:, :-1]], axis=1)
    filas = np.arange(S)[:, None]
    pc = np.clip(previo, 0, None)
    C_prev = np.where(previo >= 0, C[filas, pc], np.nan)
    I_prev = np.where(previo >= 0, I[filas, pc], np.nan)
    con_previo = obs & (previo >= 0)
    corte = con_previo & (((col[None, :] - previo) > cfg.hueco_max_min) | (I != I_prev))
    lC, lO = np.log(C), np.log(O)
    r = np.full((S, W), np.nan)
    r[obs] = np.where(con_previo & ~corte, lC - np.log(C_prev), lC - lO)[obs]

    m_ini = np.argmax(obs, axis=1)
    m_fin = W - 1 - np.argmax(obs[:, ::-1], axis=1)
    dentro = (col[None, :] >= m_ini[:, None]) & (col[None, :] <= m_fin[:, None])
    r[dentro & ~obs] = 0.0
    fila = np.arange(S)
    L0 = lO[fila, m_ini]
    L = L0[:, None] + np.cumsum(np.where(dentro, np.nan_to_num(r), 0.0), axis=1)
    L[~dentro] = np.nan
    r[~dentro] = np.nan

    cierre = C[fila, m_fin]
    i_ini, i_fin = I[fila, m_ini], I[fila, m_fin]
    roll = np.zeros(S, dtype=bool)
    roll[1:] = i_ini[1:] != i_fin[:-1]
    # Retorno de la pausa / fin de semana: apertura de s contra cierre de s−1, mismo contrato.
    r_noche = np.full(S, np.nan)
    if S > 1:
        dias = np.diff(fechas).astype("timedelta64[D]").astype(int)
        seguido = (dias <= 4) & ~roll[1:]
        r_noche[1:] = np.where(seguido, lO[fila, m_ini][1:] - np.log(cierre[:-1]), np.nan)

    span = m_fin - m_ini + 1
    cobertura = np.minimum(1.0, span / MINUTOS_SESION)
    frac_obs = obs.sum(axis=1) / np.maximum(1, span)
    completa = (cobertura >= cfg.cobertura_min) & (frac_obs >= 0.5)
    return Sesiones(pd.DatetimeIndex(fechas), L, L0, r, V, H, Lb, cierre, m_ini, m_fin,
                    cobertura, completa, corte.sum(axis=1), r_noche, roll)


def recortar(ses: Sesiones, mascara: np.ndarray) -> Sesiones:
    """Subconjunto de sesiones (p. ej. sólo las ANTERIORES al día de ejecución)."""
    idx = np.flatnonzero(np.asarray(mascara, dtype=bool))
    return Sesiones(**{f.name: getattr(ses, f.name)[idx] for f in fields(ses)})


def panel_sesiones(ses: Sesiones, cfg: Config) -> pd.DataFrame:
    """RV de 5 min submuestreado y volumen de cada sesión: lo que necesitan el HAR y el ADV."""
    k = int(cfg.freq_min)
    rv = np.array([rv_submuestreada(ses.rejilla(s), k) if ses.m_fin[s] - ses.m_ini[s] > 3 * k
                   else np.nan for s in range(ses.S)])
    d = pd.DataFrame({"RV": rv, "volumen": np.nansum(ses.vol, axis=1), "completa": ses.completa,
                      "cierre": ses.cierre, "roll": ses.roll}, index=ses.fechas)
    d.index.name = "sesion"
    d["RV_anual"] = _anual(d["RV"])
    return d


def pronostico_har(diario: pd.DataFrame, cfg: Config) -> dict:
    """
    HAR-RV logarítmico (Corsi 2009) re-estimado cada día con ventana rodante y sólo con el
    pasado:

        log RV_{t+1} = b0 + bd·log RV_t + bw·log RV_t^(5) + bm·log RV_t^(22) + e

    con RV^(h) el promedio de las últimas h sesiones y el pronóstico corregido por sesgo de
    Jensen, exp(ŷ + s²/2). Se evalúa fuera de muestra con QLIKE (Patton 2011), la pérdida
    robusta para comparar pronósticos de varianza con un proxy ruidoso.

    [v2] Tu estimate_parameters calcula σ con los retornos de la MISMA sesión que va a
    ejecutar: a las 08:30 esa σ todavía no existe. Aquí la σ del día de ejecución sale de un
    HAR ajustado sólo con sesiones anteriores, y ese día se usa después para evaluar.
    """
    d = diario[diario["completa"] & (diario["RV"] > 0)]
    rv = d["RV"].to_numpy(float)
    T = len(rv)
    out = {"fechas": d.index, "F": np.full(T, np.nan), "ok": False, "n": T}
    if T < 30:
        out["F_sig"] = float(np.mean(rv[-22:])) if T else np.nan
        out["motivo"] = f"sólo {T} sesiones completas: se usa el promedio de las últimas 22"
        return out
    s = pd.Series(rv)
    X = np.column_stack([np.ones(T), np.log(rv), np.log(s.rolling(5).mean()),
                         np.log(s.rolling(22).mean())])
    y = np.log(rv)
    F = np.full(T + 1, np.nan)
    ult = None
    for t in range(21 + cfg.har_min, T):
        j = np.arange(max(21, t - cfg.har_ventana), t)
        A, b = X[j], y[j + 1]
        coef, *_ = np.linalg.lstsq(A, b, rcond=None)
        res = b - A @ coef
        s2 = float(res @ res) / max(1, len(b) - 4)
        F[t + 1] = math.exp(float(X[t] @ coef) + 0.5 * s2)
        ult = (coef, s2, float(X[t] @ coef))
    if ult is None:
        out["F_sig"] = float(np.mean(rv[-22:]))
        out["motivo"] = (f"{T} sesiones no alcanzan para estimar el HAR "
                         f"(pide {22 + cfg.har_min}); se usa el promedio de 22")
        return out
    coef, s2, yhat = ult
    ev = np.isfinite(F[:T])
    ev[:1] = False
    idx = np.flatnonzero(ev)
    realizado = rv[idx]
    pron = {"HAR": F[idx], "RV de ayer": rv[idx - 1],
            "media 22 sesiones": s.rolling(22).mean().to_numpy()[idx - 1]}
    qlike = {k: realizado / v - np.log(realizado / v) - 1.0 for k, v in pron.items()}
    mse = {k: (realizado - v) ** 2 for k, v in pron.items()}
    dm = {k: t_newey_west(qlike[k] - qlike["HAR"], 5) for k in pron if k != "HAR"}
    out.update({
        "ok": True, "F": F[:T], "F_sig": F[T], "coef": coef, "s2": s2,
        "ic_sig": (math.exp(yhat - 1.96 * math.sqrt(s2)), math.exp(yhat + 1.96 * math.sqrt(s2))),
        "qlike": {k: float(np.mean(v)) for k, v in qlike.items()},
        "mse": {k: float(np.mean(v)) for k, v in mse.items()},
        "dm_t": dm, "n_eval": int(len(idx)),
        "percentil": float(np.mean(rv[-250:] < F[T])),
    })
    return out


# =============================================================================
# 6. PERFIL INTRADÍA Y COEFICIENTES DE IMPACTO
# =============================================================================
def _suavizar(x: np.ndarray, w: int) -> np.ndarray:
    if w <= 1:
        return x.copy()
    xp = np.pad(x, (w // 2, w - 1 - w // 2), mode="edge")
    return np.convolve(xp, np.ones(w) / w, mode="valid")


def perfil_intradia(ses: Sesiones, cfg: Config) -> pd.DataFrame:
    """
    Qué fracción de la varianza y del volumen de una sesión cae en cada minuto.

    Cada sesión se normaliza por SU propio total antes de promediar, así que un día de
    salto aporta como máximo 1/n a un minuto: el perfil no lo secuestra un solo evento, y a
    la vez conserva los picos que SÍ se repiten (07:30 CT, la apertura, el cierre), que son
    riesgo real para quien ejecuta a esa hora.
    """
    idx = np.flatnonzero(ses.completa)[-cfg.perfil_dias:]
    if len(idx) == 0:
        idx = np.arange(ses.S)
    r2 = np.nan_to_num(ses.r[idx] ** 2)
    var = np.mean(r2 / np.maximum(1e-300, r2.sum(axis=1, keepdims=True)), axis=0)
    v = ses.vol[idx]
    vol = np.mean(v / np.maximum(1.0, v.sum(axis=1, keepdims=True)), axis=0)
    out = pd.DataFrame({"var_bruta": var, "vol_bruto": vol}, index=pd.RangeIndex(ANCHO, name="minuto"))
    for c_in, c_out in (("var_bruta", "var"), ("vol_bruto", "vol")):
        x = _suavizar(out[c_in].to_numpy(), cfg.perfil_suavizado)
        x[MINUTOS_SESION:] = 0.0
        out[c_out] = x / x.sum()
    out.attrs["n_sesiones"] = int(len(idx))
    return out


@dataclass
class Mercado:
    """Todo lo que la ejecución necesita saber de la ventana, en USD y contratos."""
    X: float                   # contratos a ejecutar
    tau: float                 # minutos por tramo
    sig2: np.ndarray           # varianza del precio en cada tramo (USD² por contrato²)
    vol: np.ndarray            # volumen esperado del MERCADO en cada tramo (contratos)
    S0: float                  # precio de llegada en USD por contrato (precio × multiplicador)
    sigma_dia: float           # volatilidad pronosticada de la sesión (fracción)
    eps: float                 # costo fijo por contrato: medio spread + comisión (USD)
    eta0: float
    beta: float
    gamma: float               # impacto permanente, USD por contrato por contrato
    minutos: np.ndarray        # minuto de sesión en que arranca cada tramo
    part_max: float = np.inf   # tope de participación por tramo (fracción del volumen)
    varianza: str = "continua" # "continua": se vende parejo DENTRO del tramo · "discreta": el artículo

    @property
    def tope(self) -> np.ndarray:
        """Contratos máximos por tramo; infinito si no hay tope."""
        return (self.part_max * self.vol if np.isfinite(self.part_max) and self.part_max < 1e6
                else np.full(self.N, np.inf))

    @property
    def N(self) -> int:
        return len(self.sig2)

    @property
    def T(self) -> float:
        return self.N * self.tau

    @property
    def nocional(self) -> float:
        return self.X * self.S0

    @property
    def c(self) -> np.ndarray:
        """Costo temporal del tramo k = c_k · n_k^(1+β)  (impacto por contrato × contratos)."""
        return self.S0 * self.eta0 * self.sigma_dia * np.power(self.vol, -self.beta)

    def eta_lineal(self, por_tramo: bool = False):
        """
        η del modelo LINEAL de Almgren-Chriss (USD por contrato por contrato/min) que
        reproduce la ley de potencia al ritmo de un TWAP. Es lo que usa la AC clásica.
        """
        nbar = self.X / self.N
        v = self.vol if por_tramo else float(np.mean(self.vol))
        h = self.S0 * self.eta0 * self.sigma_dia * np.power(nbar / v, self.beta)
        return h * self.tau / nbar


def construir_mercado(cfg: Config, perfil: pd.DataFrame, sigma2_dia: float, adv: float,
                      S0_puntos: float, m0: int | None = None, T: int | None = None,
                      eps: float | None = None) -> Mercado:
    m0 = minuto_de_sesion(cfg.inicio_ct) if m0 is None else int(m0)
    T = int(cfg.horizonte_min if T is None else T)
    tau = int(cfg.paso_min)
    if T % tau:
        raise ValueError(f"El horizonte ({T} min) debe ser múltiplo del paso ({tau} min).")
    if m0 + T > MINUTOS_SESION:
        raise ValueError(f"La ventana {cfg.inicio_ct} CT + {T} min se sale de la sesión "
                         f"(cierra a las 16:00 CT).")
    N = T // tau
    mult = multiplicador(cfg)
    S0 = S0_puntos * mult
    pv, pvol = perfil["var"].to_numpy(), perfil["vol"].to_numpy()
    tramos = m0 + tau * np.arange(N)
    sv = np.array([pv[a:a + tau].sum() for a in tramos])
    sq = np.array([pvol[a:a + tau].sum() for a in tramos])
    sigma_dia = math.sqrt(sigma2_dia)
    if eps is None:
        eps = 0.5 * cfg.spread_ticks * tamano_tick(cfg) * mult + cfg.comision_usd
    vol = np.maximum(sq * adv, 1.0)
    part = float(cfg.part_max) if cfg.part_max < 1.0 else np.inf
    if np.isfinite(part) and part * vol.sum() < 1.02 * cfg.contratos:
        # El tope no deja terminar en el horizonte: se sube lo justo, y se avisa en el reporte.
        part = 1.02 * cfg.contratos / vol.sum()
    return Mercado(X=float(cfg.contratos), tau=float(tau),
                   sig2=np.maximum(sv, 1e-12) * sigma2_dia * S0 ** 2,
                   vol=vol, S0=S0, sigma_dia=sigma_dia, eps=eps,
                   eta0=cfg.eta0, beta=cfg.beta,
                   gamma=cfg.gamma0 * sigma_dia * S0 / max(adv, 1.0), minutos=tramos,
                   part_max=part)


# =============================================================================
# 7. ALMGREN-CHRISS
# =============================================================================
# Venta de X contratos en N tramos de τ minutos. Tenencias x_0 = X, …, x_N = 0; tramo
# n_k = x_{k−1} − x_k. El tramo k se ejecuta al precio del inicio del tramo menos el impacto,
# y la tenencia x_k queda expuesta a la variación del precio durante el tramo k:
#
#   costo  = Σ_k x_k·(−ΔP_k)  +  Σ_k n_k·h_k  +  γ·Σ_k n_k·Σ_{j<k} n_j  +  ε·Σ|n_k|
#   E      = ½γX² − ½γΣn_k² + εX + Σ_k c_k·n_k^(1+β)        (impacto temporal ley de potencia)
#   V      = Σ_k σ_k²·(x_{k−1}² + x_{k−1}·x_k + x_k²)/3      (se vende parejo DENTRO del tramo)
#
# y se minimiza E + λV. Con β = 1, σ y η constantes y la varianza discreta del artículo
# (V = Σ σ_k² x_k²) es exactamente Almgren y Chriss (2000). La discreta tiene un defecto: lo
# que se ejecuta dentro de un tramo no carga riesgo, así que con tramos de 30 min el modelo
# "vende" media hora de flujo al precio del inicio. Con la tenencia bajando en línea recta
# dentro del tramo, la varianza es la exacta de ese programa y no depende del tamaño del tramo.
#
# [v2] Lo que cambia contra tu almgren_chriss_optimal, en una tabla:
#   · UNIDADES. Todo en USD y contratos: precio × multiplicador, σ en USD por contrato por
#     tramo, η en USD por (contrato/min), λ en 1/USD. En tu script T = 1 "normalizado",
#     τ = 1/78, σ es por slice de 5 min y η sale de una fórmula sin unidades; κ = √(λσ²/η)
#     mezcla las tres escalas. Medido: con tus propios números κT ≤ 0.01 para TODOS los λ de
#     tu lista (0 a 1e-3), así que las seis trayectorias de tu panel de sensibilidad son el
#     mismo TWAP a menos de 0.003 contratos.
#   · κ DISCRETO. κ sale de cosh(κτ) − 1 = ½τ²λσ²/η̃, con η̃ = η − ½γτ (Almgren-Chriss eq. 19),
#     no de √(λσ²/η), que sólo vale para τ → 0.
#   · LA TENENCIA DENTRO DEL TRAMO. Tu inventory_remaining cuenta cada tramo con la tenencia
#     de su INICIO: el bloque completo expuesto todo el primer tramo aunque lo estés
#     vendiendo. Aquí baja en línea recta dentro del tramo.
#   · FALTA ε. El spread y la comisión no aparecen en tu costo esperado.

def evaluar(m: Mercado, x: np.ndarray) -> dict:
    x = np.asarray(x, dtype=float)
    n = x[:-1] - x[1:]
    temporal = float(np.sum(m.c * np.abs(n) ** (1.0 + m.beta)))
    permanente = 0.5 * m.gamma * (m.X ** 2 - float(n @ n))
    fijo = m.eps * float(np.sum(np.abs(n)))
    E = temporal + permanente + fijo
    if m.varianza == "discreta":
        V = float(np.sum(m.sig2 * x[1:] ** 2))
    else:
        a, b = x[:-1], x[1:]
        V = float(np.sum(m.sig2 * (a * a + a * b + b * b) / 3.0))
    return {"E": E, "V": V, "SD": math.sqrt(max(V, 0.0)), "temporal": temporal,
            "permanente": permanente, "fijo": fijo}


def objetivo(m: Mercado, x: np.ndarray, lam: float) -> float:
    e = evaluar(m, x)
    return e["E"] + lam * e["V"]


def twap(m: Mercado) -> np.ndarray:
    return m.X * (1.0 - np.arange(m.N + 1) / m.N)


def vwap(m: Mercado) -> np.ndarray:
    return m.X * (1.0 - np.r_[0.0, np.cumsum(m.vol)] / m.vol.sum())


def inmediata(m: Mercado) -> np.ndarray:
    x = np.zeros(m.N + 1)
    x[0] = m.X
    return x


def ac_cerrada(X: float, N: int, tau: float, sig2_min: float, eta: float, gamma: float,
               lam: float) -> np.ndarray:
    """Trayectoria de Almgren y Chriss (2000), eq. (18), escrita de forma estable."""
    T = N * tau
    t = np.arange(N + 1) * tau
    eta_t = eta - 0.5 * gamma * tau
    if lam <= 0 or eta_t <= 0:
        return X * (1.0 - t / T)
    kt2 = lam * sig2_min / eta_t
    kappa = math.acosh(1.0 + 0.5 * kt2 * tau ** 2) / tau
    if kappa * T < 1e-8:
        return X * (1.0 - t / T)
    # sinh(κ(T−t))/sinh(κT) = e^{−κt}·(1 − e^{−2κ(T−t)})/(1 − e^{−2κT})
    return X * np.exp(-kappa * t) * (-np.expm1(-2 * kappa * (T - t))) / (-np.expm1(-2 * kappa * T))


def ac_cerrada_momentos(X, N, tau, sig2_min, eta, gamma, eps, lam) -> tuple[float, float]:
    """E y V de la trayectoria óptima, fórmulas (20)-(21) de Almgren y Chriss (2000)."""
    T = N * tau
    eta_t = eta - 0.5 * gamma * tau
    kappa = math.acosh(1.0 + 0.5 * lam * sig2_min / eta_t * tau ** 2) / tau
    sh = math.sinh
    E = (0.5 * gamma * X ** 2 + eps * X + eta_t * X ** 2 * math.tanh(0.5 * kappa * tau)
         * (tau * sh(2 * kappa * T) + 2 * T * sh(kappa * tau)) / (2 * tau ** 2 * sh(kappa * T) ** 2))
    V = (0.5 * sig2_min * X ** 2 * (tau * sh(kappa * T) * math.cosh(kappa * (T - tau))
                                    - T * sh(kappa * tau)) / (sh(kappa * T) ** 2 * sh(kappa * tau)))
    return E, V


def ac_clasica(m: Mercado, lam: float) -> np.ndarray:
    """La AC de libro: σ y η CONSTANTES (promedio de la ventana), impacto lineal."""
    return ac_cerrada(m.X, m.N, m.tau, float(np.mean(m.sig2)) / m.tau, m.eta_lineal(),
                      m.gamma, lam)


def ac_lineal_variable(m: Mercado, lam: float, eta_k: np.ndarray | None = None) -> np.ndarray:
    """
    AC lineal con σ_k y η_k que CAMBIAN por tramo: el problema es cuadrático y sus
    condiciones de primer orden son un sistema tridiagonal exacto. Con varianza discreta,

        −a_j x_{j−1} + (a_j + a_{j+1} + λσ_j²) x_j − a_{j+1} x_{j+1} = 0,   a_k = η_k/τ − γ/2

    y con la continua los vecinos se acoplan también por el riesgo: ±λσ²/6 fuera de la
    diagonal y λ(σ_j² + σ_{j+1}²)/3 en ella.
    """
    N = m.N
    if N == 1:
        return np.array([m.X, 0.0])
    eta_k = m.eta_lineal(por_tramo=True) if eta_k is None else np.asarray(eta_k, float)
    a = np.maximum(eta_k / m.tau - 0.5 * m.gamma, 1e-18)
    s = lam * m.sig2
    ab = np.zeros((3, N - 1))
    rhs = np.zeros(N - 1)
    if m.varianza == "discreta":
        ab[0, 1:] = -a[1:-1]
        ab[1, :] = a[:-1] + a[1:] + s[:-1]
        ab[2, :-1] = -a[1:-1]
        rhs[0] = a[0] * m.X
    else:
        fuera = -a[1:-1] + s[1:-1] / 6.0
        ab[0, 1:] = fuera
        ab[1, :] = a[:-1] + a[1:] + (s[:-1] + s[1:]) / 3.0
        ab[2, :-1] = fuera
        rhs[0] = (a[0] - s[0] / 6.0) * m.X
    return np.r_[m.X, solve_banded((1, 1), ab, rhs), 0.0]


def _reparar_tope(x: np.ndarray, tope: np.ndarray) -> np.ndarray:
    """Recorta los tramos que exceden el tope y reparte el faltante en los primeros con holgura."""
    X = x[0]
    n = np.clip(x[:-1] - x[1:], 0.0, tope)
    falta = X - n.sum()
    if falta > 0:
        for k in range(len(n)):
            extra = min(tope[k] - n[k], falta)
            n[k] += extra
            falta -= extra
            if falta <= 0:
                break
    elif falta < 0:
        for k in range(len(n) - 1, -1, -1):
            quita = min(n[k], -falta)
            n[k] -= quita
            falta += quita
            if falta >= 0:
                break
    return np.r_[X, X - np.cumsum(n)]


def ac_optima(m: Mercado, lam: float, x0: np.ndarray | None = None) -> np.ndarray:
    """
    Mínimo NUMÉRICO de E + λV con el modelo completo (σ_k y volumen por tramo, impacto en
    ley de potencia, tope de participación). Convexo para β > 0 salvo por el término
    permanente, que en la práctica es varios órdenes menor.

    Se optimiza sobre los TRAMOS n_k, no sobre las tenencias: así 0 ≤ n_k ≤ ρ·V_k son cotas
    simples y exactas de L-BFGS-B, y la única restricción que queda, Σ n_k = X, entra con un
    lagrangiano aumentado de UN multiplicador, que está bien condicionado. (Con la tenencia
    como variable, el tope acopla tramos vecinos y hace falta un multiplicador por tramo:
    medido, eso dejaba el óptimo hasta 1 % peor según desde dónde arrancara.)
    """
    N = m.N
    if N == 1:
        return np.array([m.X, 0.0])
    X, c, b1, g = m.X, m.c, 1.0 + m.beta, m.gamma
    s2 = m.sig2[:-1]
    s_all = m.sig2
    continua = m.varianza != "discreta"
    tope = m.tope
    sup = np.minimum(np.where(np.isfinite(tope), tope, X) / X, 1.0)
    escala = max(objetivo(m, twap(m), lam) - m.eps * X - 0.5 * g * X * X, 1e-9)

    def f(q, mu, nu):
        n = q * X
        dn = b1 * c * n ** (b1 - 1.0) - g * n
        U = float(np.sum(c * n ** b1)) - 0.5 * g * float(n @ n)
        if continua:
            xs = X - np.r_[0.0, np.cumsum(n)]           # x_0 … x_N
            a, b = xs[:-1], xs[1:]
            U += lam * float(np.sum(s_all * (a * a + a * b + b * b))) / 3.0
            G = s_all * (a + 2.0 * b) / 3.0            # ∂V/∂x_k, k = 1 … N
            G[:-1] += s_all[1:] * (2.0 * b[:-1] + b[1:]) / 3.0
            dn -= lam * np.cumsum(G[::-1])[::-1]         # ∂V/∂n_j = −Σ_{k≥j} ∂V/∂x_k
        else:
            x = X - np.cumsum(n)[:-1]                   # tenencias x_1 … x_{N−1}
            U += lam * float(np.sum(s2 * x * x))
            dn[:-1] -= np.cumsum((2.0 * lam * s2 * x)[::-1])[::-1]
        h = float(q.sum()) - 1.0
        return U / escala + nu * h + 0.5 * mu * h * h, dn * X / escala + (nu + mu * h)

    if x0 is None:
        x0 = ac_lineal_variable(m, lam)
    q = np.clip(-np.diff(np.asarray(x0, float)) / X, 0.0, sup)
    q = q / q.sum() if q.sum() > 0 else sup / sup.sum()
    opciones = {"maxiter": 20_000, "ftol": 1e-15, "gtol": 1e-12, "maxcor": 30}
    limites = list(zip(np.zeros(N), sup))
    mu, nu, h_prev = 10.0, 0.0, np.inf
    for _ in range(60):
        q = minimize(f, q, args=(mu, nu), jac=True, method="L-BFGS-B", bounds=limites,
                     options=opciones).x
        h = float(q.sum()) - 1.0
        nu += mu * h
        if abs(h) < 1e-12:
            break
        if abs(h) > 0.25 * abs(h_prev):
            mu *= 10.0
        h_prev = h
    x = X * np.r_[1.0, 1.0 - np.cumsum(q)]
    x[-1] = 0.0 if abs(x[-1]) < 1e-9 * X else x[-1]
    return _reparar_tope(x, np.where(np.isfinite(tope), tope, np.inf))


def lambda_referencia(m: Mercado) -> float:
    """λ con el que la AC clásica tiene urgencia κT = 1: la escala natural del problema."""
    eta_t = max(m.eta_lineal() - 0.5 * m.gamma * m.tau, 1e-18)
    return eta_t / (float(np.mean(m.sig2)) / m.tau * m.T ** 2)


def lambda_vida_media(m: Mercado, minutos: float) -> float:
    """
    λ con el que la trayectoria ÓPTIMA (modelo completo) ejecuta la mitad del bloque en
    `minutos`. Con la AC clásica sería una fórmula (κ = ln2/vida media), pero con el perfil
    real la apertura es más volátil y la misma λ da una ejecución más rápida: medido, pedir
    10 min con la fórmula clásica daba 4. Aquí se busca por bisección en log λ.
    """
    objetivo_vm = max(float(minutos), 1e-6)
    lo, hi = math.log(lambda_referencia(m) * 1e-5), math.log(lambda_referencia(m) * 1e7)
    x = None
    if vida_media(ac_optima(m, math.exp(lo)), m.tau) <= objetivo_vm:
        return math.exp(lo)                 # ni sin aversión se tarda tanto (VWAP)
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        x = ac_optima(m, math.exp(mid), x0=x)
        if vida_media(x, m.tau) > objetivo_vm:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-3:
            break
    return math.exp(0.5 * (lo + hi))


def frontera(m: Mercado, lams: np.ndarray, clasica: bool = False) -> pd.DataFrame:
    filas, x = [], None
    for lam in lams:
        x = ac_clasica(m, lam) if clasica else ac_optima(m, lam, x0=x)
        e = evaluar(m, x)
        filas.append({"lambda": lam, "E": e["E"], "SD": e["SD"], "U": e["E"] + lam * e["V"],
                      "x": x})
    return pd.DataFrame(filas)


def elegir_lambda(m: Mercado, cfg: Config) -> tuple[float, str]:
    """
    El parámetro de aversión al riesgo, de tres maneras:
      --lambda      λ directo en 1/USD (el de Almgren-Chriss; poco intuitivo)
      --vida-media  λ tal que la mitad del bloque se ejecuta en esos minutos (AC clásica)
      --var-conf    (por omisión 0.95) el λ cuya trayectoria minimiza E + z·SD, o sea el
                    "costo con 95 % de confianza" de Almgren y Chriss (2000, §4)
    """
    if cfg.aversion is not None:
        return float(cfg.aversion), "λ fijado a mano"
    if cfg.vida_media_min:
        lam = lambda_vida_media(m, cfg.vida_media_min)
        vm = vida_media(ac_optima(m, lam), m.tau)
        if vm < 0.97 * cfg.vida_media_min:
            return lam, (f"pediste vida media de {cfg.vida_media_min:g} min, pero la más lenta posible "
                         f"en esta ventana es {vm:.1f} min (λ → 0: el VWAP)")
        if vm > 1.03 * cfg.vida_media_min:
            return lam, (f"pediste vida media de {cfg.vida_media_min:g} min, pero con el tope de "
                         f"participación la más rápida posible es {vm:.1f} min")
        return lam, f"vida media de {cfg.vida_media_min:g} min"
    z = _z(cfg.var_conf)
    ref = lambda_referencia(m)
    rejilla = ref * np.logspace(-3, 6, 37)
    fr = frontera(m, rejilla)
    val = (fr["E"] + z * fr["SD"]).to_numpy()
    i = int(np.argmin(val))
    if val[-1] <= val.min() * (1 + 5e-4):
        # ESQUINA: E + z·SD sigue bajando hasta la ejecución más rápida que permite el tope
        # (el último punto de la rejilla ya es esa ejecución). Ahí la pendiente de la
        # frontera, dE/dSD, se queda por debajo de z y no existe un óptimo interior. Se
        # reporta el λ más chico que ya la alcanza.
        j = int(np.argmax(val <= val[-1] * (1 + 5e-4) + 1e-9))
        return float(rejilla[j]), (f"E + {z:.3f}·SD (confianza {cfg.var_conf:.0%}) — ESQUINA: "
                                   "conviene la ejecución más rápida permitida")
    lo, hi = math.log(rejilla[max(0, i - 1)]), math.log(rejilla[min(len(rejilla) - 1, i + 1)])
    x_ini = fr["x"].iloc[i]

    def g(ll):
        e = evaluar(m, ac_optima(m, math.exp(ll), x0=x_ini))
        return e["E"] + z * e["SD"]

    r = minimize_scalar(g, bounds=(lo, hi), method="bounded", options={"xatol": 1e-4})
    lam = math.exp(r.x) if r.fun <= val[i] else rejilla[i]
    return lam, f"mínimo de E + {z:.3f}·SD (confianza {cfg.var_conf:.0%})"


def urgencia(x: np.ndarray, fraccion: float) -> float:
    """Fracción del bloque ejecutada en la primera `fraccion` del horizonte."""
    N = len(x) - 1
    xs = np.interp(fraccion * N, np.arange(N + 1), x)
    return 1.0 - xs / x[0]


def vida_media(x: np.ndarray, tau: float) -> float:
    N = len(x) - 1
    k = np.flatnonzero(x <= 0.5 * x[0])
    if len(k) == 0:
        return np.nan
    j = int(k[0])
    if j == 0:
        return 0.0
    # interpolación lineal entre j−1 y j
    return tau * (j - 1 + (x[j - 1] - 0.5 * x[0]) / max(x[j - 1] - x[j], 1e-18))


def pov(m: Mercado, tasa: float) -> np.ndarray:
    """Participación fija en el volumen esperado; si no alcanza, el resto va en el último tramo."""
    n = np.zeros(m.N)
    resto = m.X
    for k in range(m.N):
        q = min(tasa * m.vol[k], resto)
        n[k] = q
        resto -= q
    n[-1] += resto
    return np.r_[m.X, m.X - np.cumsum(n)]


def cargada(m: Mercado, frac_t: float, frac_q: float) -> np.ndarray:
    """Tus Front/Back-loaded: frac_q del bloque en la primera frac_t de los tramos, parejo."""
    k = min(max(1, int(m.N * frac_t)), m.N - 1)
    n = np.r_[np.full(k, m.X * frac_q / k), np.full(m.N - k, m.X * (1 - frac_q) / (m.N - k))]
    return np.r_[m.X, m.X - np.cumsum(n)]


def kappa_clasica(m: Mercado, lam: float) -> float:
    """κ (1/min) de la AC clásica con σ y η promedio de la ventana: cosh(κτ) − 1 = ½τ²λσ²/η̃."""
    eta_t = max(m.eta_lineal() - 0.5 * m.gamma * m.tau, 1e-18)
    arg = 1.0 + 0.5 * lam * (float(np.mean(m.sig2)) / m.tau) / eta_t * m.tau ** 2
    return math.acosh(arg) / m.tau if lam > 0 else 0.0


# =============================================================================
# 8. TU SCRIPT, TAL CUAL — para medirlo contra el módulo
# =============================================================================
def tu_script(ses: Sesiones, e: int, m0: int, T: int, X: float, lambdas=(0, 1e-7, 1e-6, 1e-5, 1e-4, 1e-3)) -> dict:
    """
    Réplica fiel de estimate_parameters + almgren_chriss_optimal sobre la ventana del día de
    ejecución (lo que tu script descarga): σ con la desviación de los retornos de 1 min de
    ESE día, η = 0.314·σ_diaria/V_slice^0.6, γ = 0.314·σ_diaria/ADV^0.6 con ADV = volumen de
    la ventana, T = 1, τ = 1/N, κ = √(λσ_slice²/η).
    """
    r = ses.r[e, m0:m0 + T]
    v = ses.vol[e, m0:m0 + T]
    N = max(1, T // 5)
    s_min = float(np.nanstd(r[np.isfinite(r)], ddof=1))
    s_slice, s_dia = s_min * math.sqrt(5), s_min * math.sqrt(390)
    v_slice = float(np.mean(v[:N * 5].reshape(N, 5).sum(axis=1)))
    adv = float(np.nansum(v))
    eta = 0.314 * s_dia / v_slice ** 0.6
    gamma = 0.314 * s_dia / adv ** 0.6
    tau = 1.0 / N
    tw = np.full(N, X / N)
    filas = []
    for lam in lambdas:
        k = math.sqrt(lam * s_slice ** 2 / eta) if lam > 0 else 0.0
        if k > 0:
            t = np.linspace(0, 1, N + 1)
            inv = X * np.sinh(k * (1 - t)) / np.sinh(k)
            tr = -np.diff(inv)
            tr = tr * X / tr.sum()
        else:
            tr = tw.copy()
        E = 0.5 * gamma * X ** 2 + eta * float(np.sum(tr ** 2)) / tau
        filas.append({"lambda": lam, "kappaT": k, "desv_twap": float(np.max(np.abs(tr - tw))),
                      "costo_bps": E / X * 1e4})
    inm = np.r_[X, np.zeros(N - 1)]
    resto = np.cumsum(inm[::-1])[::-1]
    return {"sigma_min": s_min, "sigma_slice": s_slice, "sigma_dia": s_dia, "v_slice": v_slice,
            "adv": adv, "eta": eta, "gamma": gamma, "N": N,
            "tabla": pd.DataFrame(filas),
            "var_inmediata": s_slice ** 2 * tau * float(np.sum(resto ** 2)),
            "impacto_twap_bps": eta * (X / N) / tau * 1e4}


# =============================================================================
# 9. COMPARACIÓN DE ESTRATEGIAS — ex ante, el día de ejecución y en la historia
# =============================================================================
def retornos_ventana(ses: Sesiones, idx: np.ndarray, m: Mercado) -> tuple[np.ndarray, np.ndarray]:
    """
    Retornos logarítmicos de 1 MINUTO de la ventana en las sesiones `idx`: con retornos por
    tramo no se vería el riesgo que hay mientras se ejecuta cada tramo.
    """
    m0, T = int(m.minutos[0]), int(m.T)
    if m0 == 0 or len(idx) == 0:
        return np.empty((0, T)), np.array([], dtype=int)
    pts = m0 - 1 + np.arange(T + 1)
    P = ses.L[idx][:, pts]
    ok = np.all(np.isfinite(P), axis=1)
    return np.diff(P[ok], axis=1), np.asarray(idx)[ok]


def estrategias(m: Mercado, lam: float, cfg: Config) -> dict:
    return {
        "AC óptima": ac_optima(m, lam),
        "AC clásica": ac_clasica(m, lam),
        "VWAP": vwap(m),
        "TWAP": twap(m),
        "POV": pov(m, cfg.pov),
        "Front-loaded": cargada(m, 0.3, 0.6),
        "Back-loaded": cargada(m, 0.7, 0.4),
        "Inmediata": inmediata(m),
    }


def comparar(m: Mercado, lam: float, z: float, tray: dict, R_hist: np.ndarray,
             R_dia: np.ndarray | None, lado: int) -> pd.DataFrame:
    filas = []
    bps = 1e4 / m.nocional
    c_twap = costos_replica(m, tray["TWAP"], R_hist, lado) if len(R_hist) else None
    for nombre, x in tray.items():
        e = evaluar(m, x)
        fila = {"estrategia": nombre, "E": e["E"], "SD": e["SD"], "U": e["E"] + lam * e["V"],
                "E_zSD": e["E"] + z * e["SD"], "fijo": e["fijo"], "temporal": e["temporal"],
                "permanente": e["permanente"], "urg_25": urgencia(x, 0.25),
                "urg_50": urgencia(x, 0.5), "vida_media_min": vida_media(x, m.tau),
                "part_max": float(np.max((x[:-1] - x[1:]) / m.vol))}
        if R_dia is not None:
            fila["dia"] = float(costos_replica(m, x, R_dia[None, :], lado)[0])
        if len(R_hist) >= 20:
            c = costos_replica(m, x, R_hist, lado)
            p95 = float(np.quantile(c, 0.95))
            fila.update({"hist_media": float(np.mean(c)), "hist_sd": float(np.std(c, ddof=1)),
                         "hist_var95": p95, "hist_cvar95": float(np.mean(c[c >= p95])),
                         "hist_n": int(len(c)),
                         "gana_a_twap": float(np.mean(c < c_twap)) if nombre != "TWAP" else np.nan})
        filas.append(fila)
    df = pd.DataFrame(filas).set_index("estrategia")
    for c in ("E", "SD", "U", "E_zSD", "fijo", "temporal", "permanente", "dia", "hist_media",
              "hist_sd", "hist_var95", "hist_cvar95"):
        if c in df:
            df[c + "_bps"] = df[c] * bps
    return df


def exposicion(m: Mercado, x: np.ndarray, columnas: int) -> np.ndarray:
    """
    Contratos expuestos durante cada columna de R: por minuto (columnas = N·τ) o por tramo
    (columnas = N). Con varianza continua la tenencia baja en línea recta dentro del tramo;
    con la discreta se queda en x_k todo el tramo, como en el artículo.
    """
    x = np.asarray(x, float)
    minutos = int(round(m.N * m.tau))
    if columnas == minutos:
        t = np.arange(minutos + 1) / m.tau
        if m.varianza == "discreta":
            return x[np.ceil(t[1:] - 1e-12).astype(int)]
        h = np.interp(t, np.arange(m.N + 1), x)
        return 0.5 * (h[:-1] + h[1:])
    if columnas == m.N:
        return x[1:] if m.varianza == "discreta" else 0.5 * (x[:-1] + x[1:])
    raise ValueError(f"R tiene {columnas} columnas: se esperaban {minutos} minutos o {m.N} tramos")


def costos_replica(m: Mercado, x: np.ndarray, R: np.ndarray, lado: int) -> np.ndarray:
    """Costo de cada sesión histórica: el determinista del modelo + el de timing REAL."""
    e = evaluar(m, x)
    R = np.atleast_2d(R)
    timing = -lado * m.S0 * (R @ exposicion(m, x, R.shape[1]))
    return e["E"] + timing


# =============================================================================
# 10. ANÁLISIS DE SENSIBILIDAD
# =============================================================================
def _variante(m: Mercado, **mult) -> Mercado:
    """Copia del mercado con multiplicadores: sigma, eta, vol, eps, gamma; o beta absoluto."""
    s = mult.get("sigma", 1.0)
    return replace(m, sig2=m.sig2 * s * s, sigma_dia=m.sigma_dia * s,
                   eta0=m.eta0 * mult.get("eta", 1.0), vol=m.vol * mult.get("vol", 1.0),
                   eps=m.eps * mult.get("eps", 1.0), gamma=m.gamma * mult.get("gamma", 1.0),
                   beta=mult.get("beta", m.beta))


def sensibilidad(m: Mercado, lam: float, cfg: Config, perfil: pd.DataFrame, sigma2_dia: float,
                 adv: float, S0_puntos: float) -> dict:
    base_x = ac_optima(m, lam)
    base_u = objetivo(m, base_x, lam)
    bps = 1e4 / m.nocional
    out = {}

    z = _z(cfg.var_conf)

    # --- mapa 1: urgencia (λ absoluto × η), cubriendo de VWAP a ejecución inmediata ---
    lm = lambda_referencia(m) * np.logspace(-2, 5, 15)
    em = np.array([0.25, 0.35, 0.5, 0.71, 1.0, 1.41, 2.0, 2.83, 4.0])
    urg = np.zeros((len(em), len(lm)))
    for i, e_ in enumerate(em):
        mv = _variante(m, eta=e_)
        x = None
        for j, l_ in enumerate(lm):
            x = ac_optima(mv, l_, x0=x)
            urg[i, j] = urgencia(x, 0.25)
    out["mapa_urgencia"] = pd.DataFrame(urg, index=em, columns=lm)

    # --- mapa 2: costo al nivel de confianza de la AC óptima (σ × η), en bps ---
    sm = np.array([0.5, 0.6, 0.71, 0.84, 1.0, 1.19, 1.41, 1.68, 2.0])
    c95 = np.zeros((len(sm), len(em)))
    for i, s_ in enumerate(sm):
        for j, e_ in enumerate(em):
            mv = _variante(m, sigma=s_, eta=e_)
            ev = evaluar(mv, ac_optima(mv, lam))
            c95[i, j] = (ev["E"] + z * ev["SD"]) * bps
    out["mapa_costo_conf"] = pd.DataFrame(c95, index=sm, columns=em)

    # --- tornado: costo óptimo re-optimizado y arrepentimiento ---
    casos = [("σ pronosticada", {"sigma": 0.5}, {"sigma": 1.5}, "×0.5", "×1.5"),
             ("η₀ impacto temporal", {"eta": 0.5}, {"eta": 2.0}, "×0.5", "×2"),
             ("β exponente", {"beta": 0.5}, {"beta": 0.75}, "0.5", "0.75"),
             ("volumen esperado", {"vol": 0.5}, {"vol": 2.0}, "×0.5", "×2"),
             ("γ₀ impacto permanente", {"gamma": 0.5}, {"gamma": 2.0}, "×0.5", "×2"),
             ("ε spread + comisión", {"eps": 0.5}, {"eps": 2.0}, "×0.5", "×2"),
             ("λ aversión al riesgo", {"lam": 0.1}, {"lam": 10.0}, "×0.1", "×10")]
    filas = []
    for nombre, lo, hi, et_lo, et_hi in casos:
        fila = {"parametro": nombre, "etiqueta_bajo": et_lo, "etiqueta_alto": et_hi}
        for lado_, d_ in (("bajo", lo), ("alto", hi)):
            d_ = dict(d_)
            l_ = lam * d_.pop("lam", 1.0)
            mv = _variante(m, **d_)
            x_re = ac_optima(mv, l_, x0=base_x)
            u_re = objetivo(mv, x_re, l_)
            u_mal = objetivo(mv, base_x, l_)
            fila[f"U_{lado_}_bps"] = u_re * bps
            fila[f"arrep_{lado_}_bps"] = max(0.0, u_mal - u_re) * bps
        filas.append(fila)
    tor = pd.DataFrame(filas).set_index("parametro")
    tor["U_base_bps"] = base_u * bps
    tor["rango_bps"] = (tor[["U_bajo_bps", "U_alto_bps"]].max(axis=1)
                        - tor[["U_bajo_bps", "U_alto_bps"]].min(axis=1))
    out["tornado"] = tor.sort_values("rango_bps", ascending=True)

    # --- horizonte: ¿cuánto tiempo conviene tomarse? ---
    m0 = int(m.minutos[0])
    hs = [h for h in (2, 5, 10, 15, 20, 30, 45, 60, 90, 120, 180, 240, 300, 390, 450)
          if h % cfg.paso_min == 0 and m0 + h <= MINUTOS_SESION and h >= 2 * cfg.paso_min]
    filas = []
    for h in hs:
        mv = construir_mercado(cfg, perfil, sigma2_dia, adv, S0_puntos, m0=m0, T=h, eps=m.eps)
        mv = replace(mv, gamma=m.gamma)
        x = ac_optima(mv, lam)
        e = evaluar(mv, x)
        ut = objetivo(mv, twap(mv), lam)
        filas.append({"horizonte_min": h, "E_bps": e["E"] * bps, "SD_bps": e["SD"] * bps,
                      "U_bps": (e["E"] + lam * e["V"]) * bps, "U_twap_bps": ut * bps,
                      "vida_media_min": vida_media(x, mv.tau)})
    out["horizonte"] = pd.DataFrame(filas).set_index("horizonte_min")

    # --- barrido de λ ---
    fr = frontera(m, lam * np.logspace(-3, 3, 31))
    fr["E_bps"] = fr["E"] * bps
    fr["SD_bps"] = fr["SD"] * bps
    fr["urg_25"] = [urgencia(x, 0.25) for x in fr["x"]]
    fr["vida_media_min"] = [vida_media(x, m.tau) for x in fr["x"]]
    out["barrido_lambda"] = fr.drop(columns="x")
    return out


def sensibilidad_extra(m: Mercado, lam: float, cfg: Config, perfil: pd.DataFrame,
                       sigma2_dia: float, adv: float, S0_puntos: float) -> dict:
    """Lo que tu script intentaba mostrar en los paneles 5 y 6, y la granularidad de los tramos."""
    out = {}
    ref = lambda_referencia(m)
    # --- trayectorias por λ (tu panel 5, ahora con λ en 1/USD que sí mueven la trayectoria) ---
    lams = ref * np.logspace(-2, 4, 7)
    x, tr = None, {}
    for l_ in lams:
        x = ac_optima(m, l_, x0=x)
        tr[l_] = x
    out["trayectorias_lambda"] = tr
    # --- κ contra λ (tu panel 6): la fórmula clásica y la κ efectiva del óptimo ---
    filas, x = [], None
    for l_ in ref * np.logspace(-3, 5, 25):
        x = ac_optima(m, l_, x0=x)
        vm = vida_media(x, m.tau)
        filas.append({"lambda": l_, "kappaT_clasica": kappa_clasica(m, l_) * m.T,
                      "kappaT_efectiva": (math.log(2) / vm * m.T) if vm and vm > 0 else np.nan,
                      "vida_media_min": vm})
    out["kappa"] = pd.DataFrame(filas)
    # --- granularidad: ¿cambia algo ejecutar en tramos de 1, 5 o 30 minutos? ---
    filas = []
    m0, T = int(m.minutos[0]), int(m.T)
    for p in (1, 2, 5, 10, 15, 30):
        if T % p or T < 2 * p:
            continue
        mv = replace(construir_mercado(replace(cfg, paso_min=p), perfil, sigma2_dia, adv,
                                       S0_puntos, m0=m0, T=T, eps=m.eps), gamma=m.gamma)
        e = evaluar(mv, ac_optima(mv, lam))
        b = 1e4 / mv.nocional
        filas.append({"paso_min": p, "N": mv.N, "U_bps": (e["E"] + lam * e["V"]) * b,
                      "E_bps": e["E"] * b, "SD_bps": e["SD"] * b})
    out["granularidad"] = pd.DataFrame(filas).set_index("paso_min")
    return out


# =============================================================================
# 11. EL CÁLCULO COMPLETO
# =============================================================================
@dataclass
class Resultado:
    cfg: Config
    ses: Sesiones
    e: int                      # índice de la sesión de ejecución
    hist: pd.DataFrame          # panel de las sesiones anteriores
    har: dict
    perfil: pd.DataFrame
    m: Mercado
    lam: float
    modo_lambda: str
    z: float
    lado: int
    tray: dict
    tabla: pd.DataFrame
    frontera: pd.DataFrame
    frontera_clasica: pd.DataFrame
    R_hist: np.ndarray
    R_dia: np.ndarray | None
    rv_dia: float
    plan: pd.DataFrame
    tu: dict
    tu_lambda: dict
    sens: dict
    extra: dict
    diag: dict


def indice_ejecucion(ses: Sesiones, cfg: Config) -> int:
    f = pd.Timestamp(cfg.fecha).normalize()
    if f in ses.fechas:
        return int(ses.fechas.get_loc(f))
    cerca = ses.fechas[np.argsort(np.abs((ses.fechas - f).days))[:3]]
    sys.exit(f"❌ La sesión {f:%Y-%m-%d} no está en los datos. Las más cercanas: "
             + ", ".join(f"{x:%Y-%m-%d}" for x in cerca))


def analizar(barras: pd.DataFrame, cfg: Config, sensib: bool = True) -> Resultado:
    ses = construir_sesiones(barras, cfg)
    e = indice_ejecucion(ses, cfg)
    hist_ses = recortar(ses, np.arange(ses.S) < e)
    if hist_ses.S < 30:
        sys.exit(f"❌ Sólo hay {hist_ses.S} sesiones antes de {cfg.fecha}. Sube --calentamiento.")
    hist = panel_sesiones(hist_ses, cfg)
    har = pronostico_har(hist, cfg)
    hist["F_har"] = (pd.Series(har["F"], index=har["fechas"]).reindex(hist.index)
                     if len(har["fechas"]) else np.nan)
    hist["F_har_anual"] = _anual(hist["F_har"])
    perfil = perfil_intradia(hist_ses, cfg)
    comp = np.flatnonzero(hist_ses.completa)
    adv = float(np.mean(hist["volumen"].to_numpy()[comp[-cfg.adv_dias:]]))
    m0 = minuto_de_sesion(cfg.inicio_ct)
    llegada = ses.L[e, m0 - 1] if m0 > 0 else ses.L0[e]
    S0_puntos = float(math.exp(llegada)) if np.isfinite(llegada) else float(hist_ses.cierre[-1])
    sigma2 = float(har["F_sig"])
    m = construir_mercado(cfg, perfil, sigma2, adv, S0_puntos)
    lam, modo = elegir_lambda(m, cfg)
    z = _z(cfg.var_conf)
    lado = 1 if cfg.lado.lower().startswith("v") else -1

    # --- historia: la misma ventana en las sesiones ANTERIORES, reescalada y sin deriva ---
    R_hist, idx_ok = retornos_ventana(hist_ses, comp[-cfg.replica_dias:], m)
    if len(R_hist):
        if cfg.escalar_vol:
            rv = hist["RV"].to_numpy()[idx_ok]
            R_hist = R_hist * np.sqrt(sigma2 / np.where(rv > 0, rv, np.nan))[:, None]
            R_hist = R_hist[np.all(np.isfinite(R_hist), axis=1)]
        if cfg.sin_deriva and len(R_hist):
            R_hist = R_hist - R_hist.mean(axis=0, keepdims=True)
    # --- el día de ejecución: sus retornos REALES, sin tocar ---
    R_d, _ = retornos_ventana(ses, np.array([e]), m)
    R_dia = R_d[0] if len(R_d) else None
    rv_dia = rv_submuestreada(ses.rejilla(e), cfg.freq_min)

    tray = estrategias(m, lam, cfg)
    tabla = comparar(m, lam, z, tray, R_hist, R_dia, lado)
    ref = lambda_referencia(m)
    fr = frontera(m, ref * np.logspace(-3, 5, 41))
    fr_c = frontera(m, ref * np.logspace(-3, 5, 41), clasica=True)
    x_tu = ac_optima(m, cfg.lambda_tu_script)
    e_tu = evaluar(m, x_tu)
    tu_lambda = {"lambda": cfg.lambda_tu_script, "vida_media": vida_media(x_tu, m.tau),
                 "urg_25": urgencia(x_tu, 0.25), "E_bps": e_tu["E"] / m.nocional * 1e4,
                 "SD_bps": e_tu["SD"] / m.nocional * 1e4}
    fecha = ses.fechas[e]
    sens = sensibilidad(m, lam, cfg, perfil, sigma2, adv, S0_puntos) if sensib else {}
    extra = sensibilidad_extra(m, lam, cfg, perfil, sigma2, adv, S0_puntos) if sensib else {}
    diag = {"n_barras": int(len(barras)), "escala": barras.attrs.get("escala", "float"),
            "n_sesiones": ses.S, "n_hist": hist_ses.S, "n_completas": int(hist_ses.completa.sum()),
            "n_rolls": int(ses.roll.sum()), "adv": adv, "sigma2": sigma2, "S0_puntos": S0_puntos,
            "lam_ref": ref, "precio_riesgo": 2.0 * lam * evaluar(m, tray["AC óptima"])["SD"]}
    return Resultado(cfg, ses, e, hist, har, perfil, m, lam, modo, z, lado, tray, tabla, fr, fr_c,
                     R_hist, R_dia, rv_dia, plan(m, tray["AC óptima"], fecha, cfg),
                     tu_script(ses, e, m0, int(m.T), m.X), tu_lambda, sens, extra, diag)


def plan(m: Mercado, x: np.ndarray, fecha, cfg: Config) -> pd.DataFrame:
    """El programa en contratos ENTEROS (restos mayores), agregado en bloques de reloj."""
    n = x[:-1] - x[1:]
    obj = np.cumsum(n)
    ent = np.round(obj).astype(int)
    ent[-1] = int(round(m.X))
    n_int = np.diff(np.r_[0, ent])
    bloque = 5 if m.T <= 60 else (15 if m.T <= 240 else 30)
    bloque = max(bloque, int(m.tau))
    filas = []
    for a in range(0, m.N, max(1, int(bloque // m.tau))):
        b = min(m.N, a + max(1, int(bloque // m.tau)))
        ct, mx = reloj(fecha, int(m.minutos[a]), cfg)
        filas.append({"hora_ct": ct.strftime("%H:%M"), "hora_cdmx": mx.strftime("%H:%M"),
                      "contratos": int(n_int[a:b].sum()),
                      "acumulado_pct": 100.0 * ent[b - 1] / m.X,
                      "participacion_pct": 100.0 * float(n[a:b].sum() / m.vol[a:b].sum())})
    return pd.DataFrame(filas)


# =============================================================================
# 12. REPORTES
# =============================================================================
def reporte_datos(res: Resultado) -> None:
    d, cfg, m = res.diag, res.cfg, res.m
    ct0, mx0 = reloj(res.ses.fechas[res.e], int(m.minutos[0]), cfg)
    ct1, mx1 = reloj(res.ses.fechas[res.e], int(m.minutos[0] + m.T), cfg)
    _titulo("1 · DATOS Y VENTANA DE EJECUCIÓN")
    print(f"  Barras de 1 min           : {d['n_barras']:>10,}   (precios: {d['escala']})")
    print(f"  Sesiones                  : {d['n_sesiones']:>10,}   anteriores a la ejecución: "
          f"{d['n_hist']:,} ({d['n_completas']:,} completas)")
    print(f"  Rolls del continuo        : {d['n_rolls']:>10,}   (por cambio de instrument_id)")
    print(f"  Sesión de ejecución       : {res.ses.fechas[res.e]:%Y-%m-%d}")
    print(f"  Ventana                   : {ct0:%H:%M}-{ct1:%H:%M} CT = {mx0:%H:%M}-{mx1:%H:%M} CDMX = "
          f"{ct0.tz_convert('UTC'):%H:%M}-{ct1.tz_convert('UTC'):%H:%M} UTC")
    print("  Todo lo que decide el plan (σ, perfiles, ADV) sale de las sesiones ANTERIORES; el")
    print("  día de ejecución sólo se usa después, para medir cómo le fue a cada estrategia.")


def reporte_tu_script(res: Resultado) -> None:
    t, m = res.tu, res.m
    _titulo("2 · TU SCRIPT CONTRA EL MÓDULO, SOBRE LOS MISMOS DATOS")
    print(f"  {'':<34s}{'tu script':>16s}{'módulo':>18s}")
    print(f"  {'σ de la ventana (5 min, fracción)':<34s}{t['sigma_slice']:16.2e}"
          f"{math.sqrt(float(np.mean(m.sig2))) / m.S0:18.2e}")
    print(f"  {'   de dónde sale':<34s}{'el MISMO día':>16s}{'HAR, días previos':>18s}")
    print(f"  {'ADV (contratos)':<34s}{t['adv']:16,.0f}{res.diag['adv']:18,.0f}")
    print(f"  {'   de dónde sale':<34s}{'ventana del día':>16s}{'sesiones previas':>18s}")
    print(f"  {'η (impacto temporal)':<34s}{t['eta']:16.2e}{m.eta_lineal():18.4f}")
    print(f"  {'   unidades':<34s}{'ninguna':>16s}{'USD/(contr/min)':>18s}")
    print(f"  {'γ (impacto permanente)':<34s}{t['gamma']:16.2e}{m.gamma:18.2e}")
    tw = res.tabla.loc["TWAP"]
    print(f"  {'costo de un TWAP':<34s}{t['tabla']['costo_bps'].iloc[0]:13.1f} bps"
          f"{tw['E_bps']:15.2f} bps")
    print()
    print("  Tu análisis de sensibilidad, recalculado con tus fórmulas:")
    print(f"      {'λ':>8s}{'κT':>12s}{'máx |trayectoria − TWAP|':>28s}")
    for _, f in t["tabla"].iterrows():
        print(f"      {f['lambda']:>8g}{f['kappaT']:12.2e}{f['desv_twap']:22.4f} contratos")
    print(f"  Con κT ≈ 0.01 la solución sinh es una recta: las {len(t['tabla'])} trayectorias de tu")
    print("  panel son el mismo TWAP. No es que la aversión al riesgo no importe; es que las")
    print("  unidades de σ, η y T no son las mismas y κ queda órdenes de magnitud chica.")
    print(f"  Tu costo de {t['tabla']['costo_bps'].iloc[0]:.0f} bps equivale a pagar "
          f"{t['tabla']['costo_bps'].iloc[0] / 100:.1f} % del nocional en impacto: con la ley")
    print(f"  de Almgren et al. y el volumen real, el TWAP cuesta {tw['E_bps']:.2f} bps.")
    tl = res.tu_lambda
    print()
    print(f"  Tu λ = {tl['lambda']:g}, leído en 1/USD con el modelo del módulo: vida media "
          f"{tl['vida_media']:.1f} min,")
    print(f"  {tl['urg_25']:.0%} ejecutado en el primer cuarto, E = {tl['E_bps']:.2f} bps y SD = "
          f"{tl['SD_bps']:.2f} bps.")


def reporte_volatilidad(res: Resultado) -> None:
    h, cfg = res.har, res.cfg
    _titulo("3 · VOLATILIDAD PRONOSTICADA — la σ que existía antes de abrir")
    if not h["ok"]:
        print(f"  ⚠ {h.get('motivo', 'sin HAR')}")
    else:
        b = h["coef"]
        print(f"  HAR: log RV(t+1) = {b[0]:+.3f} {b[1]:+.3f}·log RV(t) {b[2]:+.3f}·log RV5(t) "
              f"{b[3]:+.3f}·log RV22(t)")
        print(f"  Fuera de muestra ({h['n_eval']} sesiones), QLIKE: " + " · ".join(
            f"{k} {v:.4f}" for k, v in h["qlike"].items()))
        print("  t de Diebold-Mariano contra el HAR: " + " · ".join(
            f"{k} {v:.2f}" for k, v in h["dm_t"].items()))
    print()
    print(f"  σ pronosticada para {res.ses.fechas[res.e]:%Y-%m-%d}: {_anual(h['F_sig']):.2f} % anual"
          + (f"  (IC 95 %: {_anual(h['ic_sig'][0]):.1f} – {_anual(h['ic_sig'][1]):.1f} %; "
             f"percentil {h['percentil']:.0%} del año)" if h.get("ok") else ""))
    if np.isfinite(res.rv_dia):
        print(f"  σ realizada ese día (ex post)  : {_anual(res.rv_dia):.2f} % anual")
    m = res.m
    cuota = float(np.sum(m.sig2)) / (res.diag["sigma2"] * m.S0 ** 2)
    print(f"  La ventana concentra el {cuota:.1%} de la varianza de la sesión y el "
          f"{m.vol.sum() / res.diag['adv']:.1%} de su volumen.")


def reporte_impacto(res: Resultado) -> None:
    cfg, m = res.cfg, res.m
    tick = tamano_tick(cfg)
    S0p = res.diag["S0_puntos"]
    _titulo("4 · COEFICIENTES DE IMPACTO")
    print(f"  Precio de llegada        : {S0p:,.2f} pts  ·  {m.S0:,.0f} USD por contrato")
    print(f"  Bloque                   : {m.X:,.0f} contratos ({cfg.lado}) · nocional "
          f"{m.nocional / 1e6:,.1f} M USD")
    print(f"  ADV (sesiones previas)   : {res.diag['adv']:,.0f} contratos → el bloque es "
          f"{m.X / res.diag['adv']:.2%} del ADV y {m.X / m.vol.sum():.2%} del volumen esperado de la ventana")
    print(f"  σ pronosticada (sesión)  : {m.sigma_dia:.3%}")
    print()
    print(f"  ε  costo fijo            : {m.eps:,.2f} USD/contrato = medio spread "
          f"({cfg.spread_ticks:g} tick) + comisión {cfg.comision_usd:,.2f}")
    print(f"  η₀ impacto temporal      : {m.eta0:.3f} · σ · (participación)^{m.beta:g}   "
          "(Almgren et al. 2005)")
    print(f"  γ₀ impacto permanente    : {cfg.gamma0:g} · σ · X/ADV  →  γ = {m.gamma:.3e} USD por contrato²")
    print(f"  η  lineal equivalente    : {m.eta_lineal():.4f} USD/(contrato/min)  ← la AC clásica")
    print()
    print("  [v2] Tu estimate_parameters usa 0.314 para el impacto TEMPORAL; en Almgren et al.")
    print("  (2005) 0.314 es el PERMANENTE y el temporal es 0.142. Y el exponente 0.6 va sobre")
    print("  la PARTICIPACIÓN (tu tasa entre la del mercado), no sobre el volumen solo.")
    print()
    print("  Impacto temporal por contrato según la participación en el volumen:")
    print(f"      {'participación':>14s}{'bps':>8s}{'USD/contrato':>14s}{'ticks':>8s}")
    for p in (0.005, 0.01, 0.02, 0.05, 0.10, 0.20, 0.50):
        h = m.eta0 * m.sigma_dia * p ** m.beta
        print(f"      {p:>13.1%}{h * 1e4:8.2f}{h * m.S0:14.2f}{h * S0p / tick:8.2f}")
    print()
    print("  σ y el volumen por minuto se MIDEN en tus datos. η₀, β y γ₀ vienen de órdenes reales")
    print("  de acciones (Almgren et al. 2005): el impacto causal no se mide con OHLCV, hace falta")
    print("  tu historial de ejecuciones. La sección 8 mide cuánto cambia la decisión si están mal.")


def reporte_ejecucion(res: Resultado) -> None:
    cfg, m, tab = res.cfg, res.m, res.tabla
    x_opt = res.tray["AC óptima"]
    _titulo("5 · AVERSIÓN AL RIESGO")
    if np.isfinite(m.part_max):
        subido = m.part_max > cfg.part_max + 1e-9
        print(f"  Tope de participación: {m.part_max:.1%} del volumen de cada tramo"
              + (f"  ⚠ subido: con {cfg.part_max:.0%} no se termina" if subido else ""))
    print(f"  λ = {res.lam:.3e} 1/USD   ({res.modo_lambda})")
    print(f"      λ de referencia (AC clásica con κT = 1): {res.diag['lam_ref']:.3e}")
    print(f"      κ clásica                  : {kappa_clasica(m, res.lam):.4f} 1/min "
          f"(κT = {kappa_clasica(m, res.lam) * m.T:.2f})")
    print(f"      vida media de la ejecución : {vida_media(x_opt, m.tau):.1f} min")
    print(f"      ejecutado en el 1er cuarto : {urgencia(x_opt, 0.25):.1%}   a la mitad: "
          f"{urgencia(x_opt, 0.5):.1%}")
    print(f"      precio del riesgo          : pagas hasta {res.diag['precio_riesgo']:.2f} USD de costo "
          "esperado por cada USD de SD que quitas")
    if "ESQUINA" in res.modo_lambda:
        print("      Con este bloque E + z·SD baja hasta la ejecución más rápida permitida: el")
        print("      riesgo de esperar pesa más que el impacto. Para ir más despacio:")
        print("      --var-conf 0.75, --vida-media 60 o --lambda con un valor menor.")

    _titulo("6 · COMPARACIÓN DE ESTRATEGIAS (ex ante, con el modelo)")
    print(f"  {'estrategia':<14s}{'E bps':>8s}{'SD bps':>8s}{'E+zSD':>8s}{'spread':>8s}"
          f"{'temporal':>9s}{'perman.':>8s}{'vida ½':>8s}{'part.máx':>9s}")
    viola = tab["part_max"] > m.part_max * (1 + 1e-6) if np.isfinite(m.part_max) else tab["part_max"] < 0
    for n, x in tab.iterrows():
        print(f"  {n:<14s}{x['E_bps']:8.2f}{x['SD_bps']:8.2f}{x['E_zSD_bps']:8.2f}{x['fijo_bps']:8.2f}"
              f"{x['temporal_bps']:9.2f}{x['permanente_bps']:8.2f}{_fmt(x['vida_media_min'], 1, 7)}m"
              f"{x['part_max']:9.1%}{' *' if viola[n] else ''}")
    print(f"  (z = {res.z:.3f}: E + z·SD es el costo que no se excede con {cfg.var_conf:.0%} de "
          "confianza bajo normalidad; bps del nocional)")
    if viola.any():
        print(f"  * pasa del tope de participación ({m.part_max:.0%}): está como referencia, no como")
        print("    opción. Su impacto se extrapola a participaciones donde la ley de Almgren et al.")
        print("    no se calibró, así que ese costo es optimista.")
    opt = tab.loc["AC óptima"]
    print()
    for n in ("TWAP", "VWAP", "AC clásica", "Front-loaded", "Back-loaded"):
        d = tab.loc[n, "E_zSD"] - opt["E_zSD"]
        print(f"  Costo al {cfg.var_conf:.0%}: la AC óptima {'ahorra' if d >= 0 else 'cuesta'} "
              f"{_usd(abs(d), 0)} USD ({abs(d) / m.nocional * 1e4:.2f} bps) contra {n}")

    if "dia" in tab:
        _titulo(f"7 · EL DÍA DE EJECUCIÓN ({res.ses.fechas[res.e]:%Y-%m-%d}) — ex post, con sus precios reales")
        print(f"  {'estrategia':<14s}{'realizado bps':>15s}{'esperado bps':>14s}{'en SD':>8s}{'lugar':>7s}")
        orden = tab["dia"].rank().astype(int)
        for n, x in tab.iterrows():
            zz = (x["dia"] - x["E"]) / x["SD"] if x["SD"] > 0 else np.nan
            print(f"  {n:<14s}{x['dia_bps']:15.2f}{x['E_bps']:14.2f}{_fmt(zz, 2, 8)}{orden[n]:7d}")
        print("  Un solo día es UNA realización: si el precio fue a tu favor, la estrategia más lenta")
        print("  gana ese día aunque sea la peor en promedio. Por eso la sección siguiente.")

    if "hist_media" in tab:
        n = int(tab["hist_n"].iloc[0])
        _titulo(f"8 · RÉPLICA SOBRE {n} SESIONES ANTERIORES (misma ventana"
                f"{', vol reescalada' if cfg.escalar_vol else ''}{', sin deriva' if cfg.sin_deriva else ''})")
        print(f"  {'estrategia':<14s}{'media':>8s}{'SD':>8s}{'VaR95':>8s}{'CVaR95':>8s}"
              f"{'gana a TWAP':>13s}   (bps)")
        for nm, x in tab.iterrows():
            g = "—" if nm == "TWAP" else f"{x['gana_a_twap']:.0%}"
            print(f"  {nm:<14s}{x['hist_media_bps']:8.2f}{x['hist_sd_bps']:8.2f}"
                  f"{x['hist_var95_bps']:8.2f}{x['hist_cvar95_bps']:8.2f}{g:>13s}")
        print("  'gana a TWAP' = fracción de días en que esa estrategia costó menos que el TWAP.")
        print("  Ojo con leerlo como un marcador: una estrategia más lenta gana muchos días chicos")
        print("  y pierde pocos días grandes. Por eso la columna que decide es CVaR95.")

    print()
    print("  PLAN RECOMENDADO (contratos enteros):")
    print(f"      {'CT':>6s}{'CDMX':>7s}{'contratos':>11s}{'acumulado':>11s}{'participación':>15s}")
    pl = res.plan
    ult = int(np.argmax(pl["acumulado_pct"].to_numpy() >= 100.0 - 1e-9)) if len(pl) else 0
    for _, f in pl.iloc[:ult + 1].iterrows():
        print(f"      {f['hora_ct']:>6s}{f['hora_cdmx']:>7s}{f['contratos']:>11,d}"
              f"{f['acumulado_pct']:>10.1f}%{f['participacion_pct']:>14.2f}%")
    if ult + 1 < len(pl):
        print(f"      (bloque completo antes de las {pl['hora_ct'].iloc[ult + 1]} CT)")


def reporte_sensibilidad(res: Resultado) -> None:
    s, x = res.sens, res.extra
    if not s:
        return
    _titulo("9 · SENSIBILIDAD — qué parámetro mueve la decisión")
    t = s["tornado"].sort_values("rango_bps", ascending=False)
    print(f"  E + λV óptimo (bps) re-optimizando, y arrepentimiento de ejecutar el plan BASE si el")
    print(f"  parámetro verdadero fuera otro. Base: {t['U_base_bps'].iloc[0]:.2f} bps.")
    print(f"  {'parámetro':<24s}{'bajo':>8s}{'U bajo':>9s}{'alto':>7s}{'U alto':>9s}"
          f"{'arrep. bajo':>13s}{'arrep. alto':>13s}")
    for p, f in t.iterrows():
        print(f"  {p:<24s}{f['etiqueta_bajo']:>8s}{f['U_bajo_bps']:9.2f}{f['etiqueta_alto']:>7s}"
              f"{f['U_alto_bps']:9.2f}{f['arrep_bajo_bps']:13.3f}{f['arrep_alto_bps']:13.3f}")
    print("  Arrepentimiento chico con rango grande = el costo cambia, pero el plan base sigue")
    print("  siendo casi el óptimo. Eso es lo que hace robusta una decisión.")
    h = s["horizonte"]
    if len(h) > 2:
        u = h["U_bps"]
        umbral = u.min() + 0.1 * (u.iloc[0] - u.min())
        suf = int(u.index[np.argmax(u.to_numpy() <= umbral)])
        print()
        print(f"  HORIZONTE: {suf} min capturan el 90 % del beneficio de alargar la ejecución.")
    g = x.get("granularidad")
    if g is not None and len(g):
        print()
        print("  GRANULARIDAD (mismo λ, mismo horizonte):  " + " · ".join(
            f"{p} min → {r['U_bps']:.2f}" for p, r in g.iterrows()) + "  bps de E + λV")


# =============================================================================
# 13. TABLEROS
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


def _eje_fechas(ax, span_dias: float) -> None:
    import matplotlib.dates as mdates
    fmt = "%d-%b" if span_dias <= 120 else ("%b\n%Y" if span_dias > 400 else "%d-%b\n%Y")
    ax.xaxis.set_major_formatter(mdates.DateFormatter(fmt))


def _eje_reloj(ax, minutos: np.ndarray, cfg: Config, fecha, n_ticks: int = 7) -> None:
    lo, hi = float(np.min(minutos)), float(np.max(minutos))
    marcas = np.linspace(lo, hi, n_ticks)
    ax.set_xticks(marcas)
    ax.set_xticklabels([reloj(fecha, int(round(v)), cfg)[0].strftime("%H:%M") for v in marcas])


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


ESTILO = {                       # color (orden fijo de la paleta), línea, marcador
    "AC óptima": (C["s1"], "-", "o"),
    "TWAP": (C["s2"], ":", "D"),
    "VWAP": (C["s3"], "-.", "^"),
    "AC clásica": (C["s4"], "--", "s"),
    "Inmediata": (C["s5"], "-", "v"),
    "POV": (C["s6"], "--", "P"),
    "Front-loaded": (C["s7"], "-.", "<"),
    "Back-loaded": (C["s8"], ":", ">"),
}
COMPONENTES = [("fijo_bps", "spread + comisión", RAMPA_AZUL[3]),
               ("temporal_bps", "impacto temporal", RAMPA_AZUL[6]),
               ("permanente_bps", "impacto permanente", RAMPA_AZUL[9])]


def _eje_horas(ax, minutos: np.ndarray, cfg: Config, fecha) -> None:
    """Marcas en horas redondas de Chicago (cada 15 min si la ventana es corta)."""
    lo, hi = float(np.min(minutos)), float(np.max(minutos))
    paso = 60 if hi - lo >= 150 else (30 if hi - lo >= 75 else 15)
    marcas = np.arange(math.ceil(lo / paso) * paso, hi + 1e-9, paso)
    ax.set_xticks(marcas)
    ax.set_xticklabels([reloj(fecha, int(v), cfg)[0].strftime("%H:%M") for v in marcas])


def _texto(ax, x, y, s, **kw):
    kw.setdefault("fontsize", 7.5)
    kw.setdefault("color", C["tinta2"])
    ax.annotate(s, xy=(x, y), **kw)


def tablero_mercado(res: Resultado, plt, ruta: Path):
    cfg, m, ses, e = res.cfg, res.m, res.ses, res.e
    fecha = ses.fechas[e]
    fig, axes = plt.subplots(2, 2, figsize=(17, 10))
    fig.patch.set_facecolor(C["fondo"])
    (a1, a2), (a3, a4) = axes
    fig.suptitle(f"{cfg.symbol} · mercado y coeficientes de impacto · sesión {fecha:%Y-%m-%d}",
                 x=0.01, ha="left", color=C["tinta"], fontsize=12)

    # --- 1 el día de ejecución ---
    m0, T = int(m.minutos[0]), int(m.T)
    mins = np.arange(m0 - 1, m0 + T)
    p = np.exp(ses.L[e, mins])
    _estilo(a1, "Día de ejecución: precio en la ventana (se usa sólo ex post)")
    a1.plot(mins + 1, p, color=C["tinta"], linewidth=1.2, label="Precio (cierre de 1 min)")
    a1.axhline(res.diag["S0_puntos"], color=C["s1"], linewidth=1.2, label="Precio de llegada")
    v = ses.vol[e, m0:m0 + T]
    if np.nansum(v) > 0:
        vwap_mkt = float(np.nansum(p[1:] * v) / np.nansum(v))
        a1.axhline(vwap_mkt, color=C["s3"], linewidth=1.2, linestyle="-.",
                   label="VWAP del mercado en la ventana")
    _eje_horas(a1, mins + 1, cfg, fecha)
    a1.set_xlabel("hora CT", color=C["tinta2"], fontsize=9)
    a1.set_ylabel("puntos", color=C["tinta2"], fontsize=9)
    _leyenda(a1, ncol=3)

    # --- 2 perfil de la ventana ---
    _estilo(a2, "Perfil esperado de la ventana (índice, media = 1), de las sesiones previas")
    cx = m.minutos + m.tau / 2
    a2.plot(cx, m.sig2 / m.sig2.mean(), color=C["s1"], linewidth=1.6, label="Varianza por tramo")
    a2.plot(cx, m.vol / m.vol.mean(), color=C["s2"], linewidth=1.6, label="Volumen por tramo")
    a2.axhline(1.0, color=C["eje"], linewidth=0.8)
    _eje_horas(a2, np.r_[m.minutos, m.minutos[-1] + m.tau], cfg, fecha)
    a2.set_xlabel("hora CT", color=C["tinta2"], fontsize=9)
    _leyenda(a2, loc="upper right")

    # --- 3 curvas de impacto ---
    _estilo(a3, "Coeficientes de impacto: costo temporal por contrato contra participación")
    rho = np.logspace(-4, 0, 200)
    ley = m.eta0 * m.sigma_dia * rho ** m.beta * 1e4
    vbar = float(np.mean(m.vol))
    lin = m.eta_lineal() * (rho * vbar / m.tau) / m.S0 * 1e4
    t = res.tu
    tu = t["eta"] * rho * t["v_slice"] * t["N"] * 1e4
    a3.loglog(rho * 100, ley, color=C["s1"], linewidth=2, label=f"Ley de potencia β = {m.beta:g} (módulo)")
    a3.loglog(rho * 100, lin, color=C["s4"], linewidth=1.5, linestyle="--",
              label="AC lineal equivalente (calibrada al TWAP)")
    a3.loglog(rho * 100, tu, color=C["s8"], linewidth=1.5, linestyle=":", label="Tu script")
    part_twap = m.X / m.vol.sum()
    a3.axvline(part_twap * 100, color=C["tinta2"], linewidth=1.0)
    _texto(a3, part_twap * 100, 0.04, " participación\n de un TWAP", xycoords=("data", "axes fraction"))
    if np.isfinite(m.part_max):
        a3.axvline(m.part_max * 100, color=C["eje"], linewidth=1.0)
        _texto(a3, m.part_max * 100, 0.04, " tope", xycoords=("data", "axes fraction"))
    a3.set_xlabel("participación en el volumen del tramo (%)", color=C["tinta2"], fontsize=9)
    a3.set_ylabel("bps por contrato", color=C["tinta2"], fontsize=9)
    _leyenda(a3)

    # --- 4 σ pronosticada ---
    h = res.hist[res.hist["completa"]].iloc[-120:]
    _estilo(a4, "Volatilidad por sesión: realizada, pronóstico HAR y el día de ejecución")
    a4.plot(h.index, h["RV_anual"], color=C["s1"], linewidth=1.4, label="RV 5 min (realizada)")
    if h["F_har_anual"].notna().any():
        a4.plot(h.index, h["F_har_anual"], color=C["s7"], linewidth=1.3, drawstyle="steps-mid",
                label="Pronóstico HAR del día anterior")
    y = float(_anual(res.har["F_sig"]))
    if res.har.get("ok"):
        lo, hi = (float(_anual(v)) for v in res.har["ic_sig"])
        a4.errorbar([fecha], [y], yerr=[[y - lo], [hi - y]], fmt="o", color=C["s7"], markersize=7,
                    capsize=4, markeredgecolor=C["fondo"], markeredgewidth=1.5,
                    label="Pronóstico para la ejecución (IC 95 %)")
    if np.isfinite(res.rv_dia):
        a4.scatter([fecha], [_anual(res.rv_dia)], s=90, facecolors="none", edgecolors=C["tinta"],
                   linewidths=1.5, zorder=6, label="Realizada ese día (ex post)")
    _eje_fechas(a4, max(1, (h.index[-1] - h.index[0]).days))
    a4.set_ylabel("% anual", color=C["tinta2"], fontsize=9)
    _leyenda(a4, ncol=2)
    fig.text(0.008, 0.004, f"{IDENTIFICADOR} · σ, perfiles y ADV de las {res.diag['n_hist']} sesiones "
             "previas · el día de ejecución no entra en ninguna estimación", color=C["tenue"], fontsize=7.5)
    fig.tight_layout(rect=(0, 0.015, 1, 0.965))
    fig.savefig(ruta, dpi=130, facecolor=C["fondo"], bbox_inches="tight")
    return fig


def tablero_ejecucion(res: Resultado, plt, ruta: Path):
    cfg, m, tab, tray = res.cfg, res.m, res.tabla, res.tray
    fecha = res.ses.fechas[res.e]
    bps = 1e4 / m.nocional
    fig, axes = plt.subplots(2, 3, figsize=(19, 10.5))
    fig.patch.set_facecolor(C["fondo"])
    (a1, a2, a3), (a4, a5, a6) = axes
    ct0, mx0 = reloj(fecha, int(m.minutos[0]), cfg)
    fig.suptitle(f"{cfg.symbol} · {cfg.lado} de {m.X:,.0f} contratos · {m.T:.0f} min desde "
                 f"{ct0:%H:%M} CT ({mx0:%H:%M} CDMX) · {m.N} tramos de {m.tau:.0f} min · "
                 f"λ = {res.lam:.2e} 1/USD", x=0.01, ha="left", color=C["tinta"], fontsize=12)
    nombres = list(tab.index)
    mins = np.r_[m.minutos, m.minutos[-1] + m.tau]

    # --- 1 frontera ---
    _estilo(a1, "Frontera eficiente: costo esperado contra riesgo (bps)")
    a1.plot(res.frontera["SD"] * bps, res.frontera["E"] * bps, color=C["s1"], linewidth=2,
            label="AC óptima (λ variable)")
    a1.plot(res.frontera_clasica["SD"] * bps, res.frontera_clasica["E"] * bps, color=C["s4"],
            linewidth=1.4, linestyle="--", label="AC clásica evaluada con el modelo completo")
    for k, (n, x) in enumerate(tab.sort_values("SD_bps").iterrows()):
        col, _, mk = ESTILO[n]
        a1.scatter(x["SD_bps"], x["E_bps"], s=70, marker=mk, color=col, zorder=5,
                   edgecolors=C["fondo"], linewidths=1.5)
        a1.annotate(n, xy=(x["SD_bps"], x["E_bps"]), xytext=(6, 5 if k % 2 == 0 else -12),
                    textcoords="offset points", fontsize=7.5, color=C["tinta"])
    a1.set_xlabel("desviación estándar del costo (bps)", color=C["tinta2"], fontsize=9)
    a1.set_ylabel("costo esperado (bps)", color=C["tinta2"], fontsize=9)
    _leyenda(a1, loc="upper right")

    # --- 2 inventario ---
    _estilo(a2, "Inventario pendiente")
    for n, x in tray.items():
        col, ls, _ = ESTILO[n]
        a2.plot(mins, 100 * x / m.X, color=col, linestyle=ls, linewidth=2.2 if n == "AC óptima" else 1.5,
                label=n)
    _eje_horas(a2, mins, cfg, fecha)
    a2.set_xlabel("hora CT", color=C["tinta2"], fontsize=9)
    a2.set_ylabel("% del bloque", color=C["tinta2"], fontsize=9)
    _leyenda(a2, loc="upper right", ncol=2)

    # --- 3 programa ---
    _estilo(a3, "Contratos por tramo")
    x = tray["AC óptima"]
    a3.bar(m.minutos + m.tau / 2, x[:-1] - x[1:], width=m.tau * 0.8, color=C["s1"], label="AC óptima")
    for n in ("VWAP", "POV", "TWAP"):
        col, ls, _ = ESTILO[n]
        xx = tray[n]
        a3.step(m.minutos + m.tau / 2, xx[:-1] - xx[1:], where="mid", color=col, linestyle=ls,
                linewidth=1.6, label=n if n != "POV" else f"POV {cfg.pov:.0%}")
    _eje_horas(a3, mins, cfg, fecha)
    a3.set_xlabel("hora CT", color=C["tinta2"], fontsize=9)
    a3.set_ylabel("contratos", color=C["tinta2"], fontsize=9)
    _leyenda(a3, loc="upper right")

    # --- 4 descomposición ---
    _estilo(a4, f"De qué está hecho el costo al {cfg.var_conf:.0%} (bps)")
    y = np.arange(len(nombres))
    izq = np.zeros(len(nombres))
    for col, et, color in COMPONENTES:
        vals = tab[col].to_numpy()
        a4.barh(y, vals, left=izq, height=0.62, color=color, label=et)
        izq += vals
    riesgo = res.z * tab["SD_bps"].to_numpy()
    a4.barh(y, riesgo, left=izq, height=0.62, color=C["neutro"], label=f"riesgo (z·SD)")
    for yi, tot in enumerate(izq + riesgo):
        a4.annotate(f"{tot:.2f}", xy=(tot, yi), xytext=(3, 0), textcoords="offset points",
                    va="center", fontsize=7, color=C["tinta2"])
    a4.set_yticks(y)
    a4.set_yticklabels(nombres)
    a4.invert_yaxis()
    a4.set_xlim(0, float(np.max(izq + riesgo)) * 1.55)
    a4.set_xlabel("bps del nocional", color=C["tinta2"], fontsize=9)
    _leyenda(a4, loc="lower right")

    # --- 5 el día de ejecución ---
    if "dia" in tab:
        _estilo(a5, f"Ex post, {fecha:%d-%b-%Y}: costo realizado y el esperado ± 1 SD (bps)")
        cols = [ESTILO[n][0] for n in nombres]
        a5.barh(y, tab["dia_bps"], height=0.6, color=cols, alpha=0.85)
        a5.errorbar(tab["E_bps"], y, xerr=tab["SD_bps"], fmt="D", color=C["tinta"], markersize=5,
                    capsize=3, linewidth=1.0, label="esperado ± 1 SD")
        a5.axvline(0, color=C["eje"], linewidth=0.8)
        a5.set_yticks(y)
        a5.set_yticklabels(nombres)
        a5.invert_yaxis()
        a5.set_xlabel("bps del nocional (negativo = el precio se movió a tu favor)",
                      color=C["tinta2"], fontsize=8.5)
        _leyenda(a5, loc="lower right")
    else:
        _estilo(a5, "Ex post")
        a5.text(0.5, 0.5, "La ventana no está completa en el día de ejecución",
                ha="center", va="center", transform=a5.transAxes, color=C["tinta2"])

    # --- 6 réplica ---
    R = res.R_hist
    if len(R) >= 20:
        _estilo(a6, f"Réplica sobre {len(R)} sesiones previas: distribución del costo (bps)")
        datos = [costos_replica(m, tray[n], R, res.lado) * bps for n in nombres]
        kw = dict(whis=(5, 95), widths=0.55, patch_artist=True, showfliers=False,
                  medianprops=dict(color=C["tinta"], linewidth=1.2))
        try:
            bp = a6.boxplot(datos, orientation="horizontal", **kw)
        except TypeError:                                   # matplotlib < 3.10
            bp = a6.boxplot(datos, vert=False, **kw)
        for caja, n in zip(bp["boxes"], nombres):
            caja.set_facecolor(ESTILO[n][0])
            caja.set_alpha(0.35)
            caja.set_edgecolor(ESTILO[n][0])
        for i, d in enumerate(datos, start=1):
            a6.scatter([np.mean(d)], [i], marker="D", s=24, color=C["tinta"], zorder=5)
        a6.set_yticks(np.arange(1, len(nombres) + 1))
        a6.set_yticklabels(nombres)
        a6.invert_yaxis()
        a6.set_xlabel("bps · caja = cuartiles · bigotes = percentiles 5-95 · rombo = media",
                      color=C["tinta2"], fontsize=8.5)
    else:
        _estilo(a6, "Réplica histórica")
        a6.text(0.5, 0.5, "No hay sesiones previas suficientes con esa ventana",
                ha="center", va="center", transform=a6.transAxes, color=C["tinta2"])
    tope = f" · tope de participación {m.part_max:.0%}" if np.isfinite(m.part_max) else ""
    fig.text(0.008, 0.004, f"{IDENTIFICADOR} · η₀ = {m.eta0:g}, β = {m.beta:g}, γ₀ = {cfg.gamma0:g} · "
             f"spread {cfg.spread_ticks:g} tick + comisión {cfg.comision_usd:g} USD{tope}",
             color=C["tenue"], fontsize=7.5)
    fig.tight_layout(rect=(0, 0.015, 1, 0.965))
    fig.savefig(ruta, dpi=130, facecolor=C["fondo"], bbox_inches="tight")
    return fig


def tablero_sensibilidad(res: Resultado, plt, ruta: Path):
    from matplotlib.colors import LinearSegmentedColormap
    cfg, m, lam, s, x = res.cfg, res.m, res.lam, res.sens, res.extra
    fecha = res.ses.fechas[res.e]
    cmap = LinearSegmentedColormap.from_list("azul", RAMPA_AZUL)
    fig, axes = plt.subplots(2, 4, figsize=(24, 10.5))
    fig.patch.set_facecolor(C["fondo"])
    (a1, a2, a3, a4), (a5, a6, a7, a8) = axes
    fig.suptitle(f"{cfg.symbol} · análisis de sensibilidad de la ejecución óptima",
                 x=0.01, ha="left", color=C["tinta"], fontsize=12)
    mins = np.r_[m.minutos, m.minutos[-1] + m.tau]

    # --- 1 trayectorias por λ (tu panel 5) ---
    _estilo(a1, "Trayectoria óptima según la aversión al riesgo λ")
    tr = x["trayectorias_lambda"]
    for (l_, xx), tono in zip(tr.items(), np.linspace(3, len(RAMPA_AZUL) - 1, len(tr)).astype(int)):
        a1.plot(mins, 100 * xx / m.X, color=RAMPA_AZUL[tono], linewidth=1.5, label=f"λ = {l_:.0e}")
    a1.plot(mins, 100 * res.tray["AC óptima"] / m.X, color=C["tinta"], linewidth=2.2,
            label=f"λ elegido = {lam:.1e}")
    _eje_horas(a1, mins, cfg, fecha)
    a1.set_ylabel("% del bloque pendiente", color=C["tinta2"], fontsize=9)
    _leyenda(a1, loc="upper right", fontsize=7)

    # --- 2 κ contra λ (tu panel 6) ---
    k = x["kappa"]
    _estilo(a2, "Urgencia κT contra λ (κT > 1: se ejecuta antes del final)")
    a2.loglog(k["lambda"], k["kappaT_clasica"], color=C["s4"], linewidth=1.6, linestyle="--",
              label="AC clásica: cosh(κτ) − 1 = ½τ²λσ²/η̃")
    a2.loglog(k["lambda"], k["kappaT_efectiva"], color=C["s1"], linewidth=2,
              label="efectiva del óptimo: ln2·T / vida media")
    a2.axvline(lam, color=C["tinta2"], linewidth=1.0)
    a2.axhline(1.0, color=C["eje"], linewidth=1.0)
    techo = k["kappaT_efectiva"].max()
    if np.isfinite(m.part_max) and np.isfinite(techo):
        _texto(a2, k["lambda"].iloc[-1], techo, "techo: el tope de participación\nno deja ir más rápido",
               xytext=(0, 8), textcoords="offset points", ha="right", va="bottom")
    a2.set_xlabel("λ (1/USD)", color=C["tinta2"], fontsize=9)
    a2.set_ylabel("κT", color=C["tinta2"], fontsize=9)
    _leyenda(a2, loc="upper left", fontsize=7)

    def mapa(ax, valores, titulo, xlab, ylab, xt, yt, etiqueta, base_xy, texto_base):
        _estilo(ax, titulo)
        ax.grid(False)
        im = ax.imshow(valores, cmap=cmap, aspect="auto", origin="lower")
        ax.set_xticks(np.arange(valores.shape[1]))
        ax.set_xticklabels(xt)
        ax.set_yticks(np.arange(valores.shape[0]))
        ax.set_yticklabels(yt)
        ax.set_xlabel(xlab, color=C["tinta2"], fontsize=9)
        ax.set_ylabel(ylab, color=C["tinta2"], fontsize=9)
        ax.scatter([base_xy[0]], [base_xy[1]], s=220, facecolors="none", edgecolors=C["tinta"],
                   linewidths=1.5)
        ax.annotate(texto_base, xy=base_xy, xytext=(12, 10), textcoords="offset points",
                    fontsize=8, color=C["tinta"],
                    bbox=dict(boxstyle="round,pad=0.25", facecolor=C["fondo"], edgecolor=C["eje"]))
        cb = ax.figure.colorbar(im, ax=ax, fraction=0.046, pad=0.02)
        cb.set_label(etiqueta, color=C["tinta2"], fontsize=8)
        cb.ax.tick_params(labelsize=7, colors=C["tinta2"])
        cb.outline.set_visible(False)

    # --- 3 urgencia λ × η₀ ---
    mu = s["mapa_urgencia"]
    lc = np.log10(mu.columns.to_numpy(float))
    xl = float(np.clip((math.log10(lam) - lc[0]) / (lc[1] - lc[0]), 0, len(lc) - 1))
    mapa(a3, mu.to_numpy() * 100, "Urgencia: % ejecutado en el primer cuarto", "λ (1/USD)",
         "η₀ relativo", [f"{v:.0e}" if j % 3 == 0 else "" for j, v in enumerate(mu.columns)],
         [f"{v:g}×" for v in mu.index], "% en el 1er cuarto",
         (xl, float(np.argmin(np.abs(mu.index - 1)))),
         f"λ elegido: {urgencia(res.tray['AC óptima'], 0.25):.0%}")

    # --- 4 costo al z (σ × η₀) ---
    mc = s["mapa_costo_conf"]
    bi, bj = int(np.argmin(np.abs(mc.index - 1))), int(np.argmin(np.abs(mc.columns - 1)))
    mapa(a4, mc.to_numpy(), f"Costo al {cfg.var_conf:.0%} (E + z·SD) de la AC óptima, bps",
         "η₀ relativo", "σ relativa", [f"{v:g}×" for v in mc.columns], [f"{v:g}×" for v in mc.index],
         "bps del nocional", (float(bj), float(bi)), f"hoy: {mc.iloc[bi, bj]:.2f} bps")

    # --- 5 tornado ---
    t = s["tornado"]
    base = float(t["U_base_bps"].iloc[0])
    yy = np.arange(len(t))
    _estilo(a5, "Tornado: E + λV óptimo re-optimizado (bps)")
    a5.barh(yy, t["U_bajo_bps"] - base, left=base, height=0.62, color=C["s1"], label="valor bajo")
    a5.barh(yy, t["U_alto_bps"] - base, left=base, height=0.62, color=C["s2"], label="valor alto")
    for yi, (_, f) in enumerate(t.iterrows()):
        for col, et in (("U_bajo_bps", "etiqueta_bajo"), ("U_alto_bps", "etiqueta_alto")):
            v = f[col]
            a5.annotate(f[et], xy=(v, yi), xytext=(3 if v >= base else -3, 0),
                        textcoords="offset points", va="center",
                        ha="left" if v >= base else "right", fontsize=7, color=C["tinta2"])
    a5.axvline(base, color=C["tinta"], linewidth=1.0)
    a5.set_yticks(yy)
    a5.set_yticklabels(t.index)
    a5.margins(x=0.2)
    a5.set_xlabel(f"bps (base {base:.2f})", color=C["tinta2"], fontsize=9)
    _leyenda(a5, loc="lower right")

    # --- 6 arrepentimiento ---
    _estilo(a6, "Arrepentimiento: costo extra del plan base si el parámetro real fuera otro")
    a6.barh(yy + 0.18, t["arrep_bajo_bps"], height=0.34, color=C["s1"], label="valor bajo")
    a6.barh(yy - 0.18, t["arrep_alto_bps"], height=0.34, color=C["s2"], label="valor alto")
    a6.set_yticks(yy)
    a6.set_yticklabels(t.index)
    a6.set_xlabel("bps del nocional", color=C["tinta2"], fontsize=9)
    _leyenda(a6, loc="lower right")

    # --- 7 horizonte ---
    h = s["horizonte"]
    _estilo(a7, "Horizonte de ejecución (λ fijo)")
    a7.plot(h.index, h["U_bps"], color=C["s1"], linewidth=2, marker="o", markersize=5,
            label="E + λV óptimo")
    a7.plot(h.index, h["E_bps"], color=C["s2"], linewidth=1.5, label="E[costo] óptimo")
    a7.plot(h.index, h["U_twap_bps"], color=C["s3"], linewidth=1.5, linestyle="--",
            label="E + λV de un TWAP")
    a7.axvline(m.T, color=C["tinta2"], linewidth=1.0)
    _texto(a7, m.T, 0.5, "horizonte elegido ", xycoords=("data", "axes fraction"), ha="right",
           rotation=90, va="center")
    a7.set_xscale("log")
    a7.set_yscale("log")
    a7.set_xticks(list(h.index))
    a7.set_xticklabels([str(v) if j % 2 == 0 or v == int(m.T) else "" for j, v in enumerate(h.index)],
                       fontsize=7)
    a7.set_xlabel("minutos", color=C["tinta2"], fontsize=9)
    a7.set_ylabel("bps", color=C["tinta2"], fontsize=9)
    _leyenda(a7, loc="upper left")

    # --- 8 granularidad ---
    g = x["granularidad"]
    _estilo(a8, "Granularidad: tamaño del tramo (λ y horizonte fijos)")
    a8.plot(g.index, g["U_bps"], color=C["s1"], linewidth=2, marker="o", markersize=5, label="E + λV")
    a8.plot(g.index, g["E_bps"], color=C["s2"], linewidth=1.5, marker="s", markersize=4, label="E[costo]")
    a8.plot(g.index, g["SD_bps"], color=C["s3"], linewidth=1.5, marker="^", markersize=4, label="SD")
    a8.axvline(m.tau, color=C["tinta2"], linewidth=1.0)
    a8.set_xscale("log")
    a8.set_xticks(list(g.index))
    a8.set_xticklabels([str(v) for v in g.index])
    a8.set_xlabel("minutos por tramo", color=C["tinta2"], fontsize=9)
    a8.set_ylabel("bps", color=C["tinta2"], fontsize=9)
    _leyenda(a8, loc="upper left")
    fig.text(0.008, 0.004, f"{IDENTIFICADOR} · cada celda y cada punto RE-OPTIMIZA la AC completa",
             color=C["tenue"], fontsize=7.5)
    fig.tight_layout(rect=(0, 0.015, 1, 0.965))
    fig.savefig(ruta, dpi=130, facecolor=C["fondo"], bbox_inches="tight")
    return fig


def tableros(res: Resultado, mostrar: bool = True) -> tuple[list[Path], object, bool]:
    plt, ventana = _preparar_grafico(mostrar)
    if plt is None:
        return [], None, False
    carpeta = _ruta(res.cfg.salida_dir)
    carpeta.mkdir(parents=True, exist_ok=True)
    suf = _nombre_seguro(res.cfg.symbol, f"{res.ses.fechas[res.e]:%Y%m%d}")
    rutas = []
    for nombre, fn in (("mercado", tablero_mercado), ("ejecucion", tablero_ejecucion),
                       ("sensibilidad", tablero_sensibilidad)):
        if nombre == "sensibilidad" and not res.sens:
            continue
        ruta = carpeta / f"ac_{nombre}_{suf}.png"
        fig = fn(res, plt, ruta)
        rutas.append(ruta)
        print(f"🖼  {ruta}")
        if not ventana:
            plt.close(fig)
    return rutas, plt, ventana


# =============================================================================
# 14. TELEGRAM — el token y el chat, igual que la key: FUERA del código
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
    avisos = []
    h = res.har
    if h.get("ok") and h["percentil"] >= res.cfg.telegram_percentil_alerta:
        avisos.append(f"Volatilidad pronosticada en el percentil {h['percentil']:.0%} del año "
                      f"({_anual(h['F_sig']):.1f} % anual)")
    tab = res.tabla
    if "dia" in tab and "hist_var95" in tab:
        x = tab.loc["AC óptima"]
        if x["dia"] > x["hist_var95"]:
            avisos.append(f"El costo realizado de la AC óptima ({x['dia_bps']:.2f} bps) superó su "
                          f"VaR95 histórico ({x['hist_var95_bps']:.2f} bps)")
    if res.m.X / res.diag["adv"] > 0.05:
        avisos.append(f"El bloque es {res.m.X / res.diag['adv']:.1%} del ADV: fuera del rango en que "
                      "se calibró la ley de impacto")
    return avisos


def mensaje_telegram(res: Resultado, limite: int = 4096) -> str:
    cfg, m, tab = res.cfg, res.m, res.tabla
    esc = html.escape
    fecha = res.ses.fechas[res.e]
    ct0, mx0 = reloj(fecha, int(m.minutos[0]), cfg)
    lin = [f"<b>{esc(IDENTIFICADOR)} · {esc(cfg.symbol)}</b>"]
    for a in hay_alerta(res):
        lin.append(f"⚠️ {esc(a)}")
    h = res.har
    lin += ["", f"<b>Ejecución</b> {esc(cfg.lado)} {m.X:,.0f} contratos · {fecha:%Y-%m-%d} · "
                f"{m.T:.0f} min desde {ct0:%H:%M} CT ({mx0:%H:%M} CDMX)",
            f"σ pronosticada {_anual(h['F_sig']):.1f}% anual · bloque {m.X / res.diag['adv']:.2%} del ADV",
            f"λ = {res.lam:.2e} 1/USD ({esc(res.modo_lambda)})",
            f"Vida media {vida_media(res.tray['AC óptima'], m.tau):.1f} min · "
            f"{urgencia(res.tray['AC óptima'], 0.25):.0%} en el primer cuarto"]
    filas = ["estrategia    E+zSD  día   CVaR"]
    for n, r in tab.iterrows():
        dia = f"{r['dia_bps']:6.2f}" if "dia" in tab else "     —"
        cv = f"{r['hist_cvar95_bps']:6.2f}" if "hist_cvar95" in tab else "     —"
        filas.append(f"{n[:12]:<12s}{r['E_zSD_bps']:7.2f}{dia}{cv}")
    lin.append("<pre>" + esc("\n".join(filas)) + "</pre>")
    lin.append("bps del nocional · día = realizado ex post · CVaR = réplica histórica 95 %")
    p = res.plan[res.plan["contratos"] > 0]
    if len(p):
        lin.append("Plan (CT, contratos): " + esc(" · ".join(
            f"{f['hora_ct']} {f['contratos']:,}" for _, f in p.head(16).iterrows())))
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
# 15. GUARDAR
# =============================================================================
def guardar(res: Resultado) -> None:
    carpeta = _ruta(res.cfg.salida_dir)
    carpeta.mkdir(parents=True, exist_ok=True)
    suf = _nombre_seguro(res.cfg.symbol, f"{res.ses.fechas[res.e]:%Y%m%d}")
    m = res.m
    res.tabla.to_csv(carpeta / f"ac_estrategias_{suf}.csv")
    res.plan.to_csv(carpeta / f"ac_plan_{suf}.csv", index=False)
    tray = pd.DataFrame(res.tray)
    tray.insert(0, "hora_ct", [reloj(res.ses.fechas[res.e], int(v), res.cfg)[0].strftime("%H:%M")
                               for v in np.r_[m.minutos, m.minutos[-1] + m.tau]])
    tray.to_csv(carpeta / f"ac_trayectorias_{suf}.csv", index=False)
    res.frontera.drop(columns="x").to_csv(carpeta / f"ac_frontera_{suf}.csv", index=False)
    pd.DataFrame({"minuto": m.minutos, "sigma_usd": np.sqrt(m.sig2), "volumen": m.vol}).to_csv(
        carpeta / f"ac_perfil_ventana_{suf}.csv", index=False)
    res.hist.to_csv(carpeta / f"ac_historia_{suf}.csv")
    res.tu["tabla"].to_csv(carpeta / f"ac_tu_script_{suf}.csv", index=False)
    for k, v in res.sens.items():
        v.to_csv(carpeta / f"ac_sens_{k}_{suf}.csv")
    for k in ("kappa", "granularidad"):
        if k in res.extra:
            res.extra[k].to_csv(carpeta / f"ac_sens_{k}_{suf}.csv")
    print(f"💾 Tablas guardadas en {carpeta}")


# =============================================================================
# 16. PRUEBAS INTERNAS
# =============================================================================
def pruebas() -> int:
    cfg = replace(CFG, sim_sesiones=150, har_min=40)
    fallas: list[str] = []
    hecho = 0

    def check(nombre: str, ok: bool, detalle: str = "") -> None:
        nonlocal hecho
        hecho += 1
        print(f"  {'✓' if ok else '✗'} {nombre}" + (f"   {detalle}" if detalle else ""))
        if not ok:
            fallas.append(nombre)

    _titulo("PRUEBAS INTERNAS")
    rng = np.random.default_rng(0)
    f_var, f_vol = perfiles_teoricos()
    perf = pd.DataFrame({"var": f_var, "vol": f_vol})

    # 1 ------------------------------------------ tu ventana en UTC se mueve con el horario de verano
    t = pd.DatetimeIndex(["2026-08-20 13:30", "2026-01-15 13:30"]).tz_localize("UTC")
    _, mi = sesion_y_minuto(t, "America/Chicago")
    check("tu ventana 13:30 UTC es 08:30 CT en agosto pero 07:30 CT en enero",
          mi[0] == minuto_de_sesion("08:30") and mi[1] == minuto_de_sesion("07:30"),
          "por eso aquí la ventana se define en hora de Chicago")

    # 2 ------------------------------------------ sesión de Globex
    t = pd.DatetimeIndex(["2026-08-02 17:00", "2026-08-03 15:59", "2026-08-03 17:00"]
                         ).tz_localize("America/Chicago")
    ses_, mi = sesion_y_minuto(t.tz_convert("UTC"), "America/Chicago")
    check("domingo 17:00 CT abre la sesión del lunes; 17:00 CT abre la del día siguiente",
          list(pd.DatetimeIndex(ses_).strftime("%m-%d")) == ["08-03", "08-03", "08-04"]
          and list(mi) == [0, 1379, 0])

    # 3 ------------------------------------------ escala de precios
    df3, _ = simular(cfg, n_sesiones=5, n_saltos=0, n_rolls=0, semilla=1)
    d3 = df3.head(300).copy()
    d3f = d3.copy()
    for c in ("open", "high", "low", "close"):
        d3f[c] = (d3f[c] * 1e9).round().astype("int64")
    pf, pi = preparar_barras(d3, cfg)["close"].median(), preparar_barras(d3f, cfg)["close"].median()
    check("la escala se detecta: float queda igual, punto fijo se divide entre 1e9",
          abs(pf / pi - 1) < 1e-9 and pf > 1000,
          f"{pf:,.2f}; tu PRICE_SCALE lo dejaría en {pf / 1e9:.2e}")

    # 4 ------------------------------------------ rolls por instrument_id
    df4, _ = simular(cfg, n_sesiones=60, n_saltos=0, n_rolls=2, semilla=4)
    ses4 = construir_sesiones(preparar_barras(df4, cfg), cfg)
    check("los rolls se detectan por instrument_id (symbol no cambia en el continuo)",
          int(ses4.roll.sum()) == 2 and df4["symbol"].nunique() == 1)

    # 5 ------------------------------------------ AC: cerrada = tridiagonal = numérica
    m = Mercado(X=500, tau=1.0, sig2=np.full(30, 400.0 ** 2), vol=np.full(30, 2000.0),
                S0=420_000.0, sigma_dia=0.012, eps=4.5, eta0=0.142, beta=1.0, gamma=1e-3,
                minutos=np.arange(930, 960), varianza="discreta")
    lam = 5e-7
    eta = m.eta_lineal()
    xc = ac_cerrada(m.X, m.N, m.tau, 400.0 ** 2, eta, m.gamma, lam)
    xt, xn = ac_lineal_variable(m, lam), ac_optima(m, lam)
    check("AC: la fórmula cerrada, el sistema tridiagonal y el óptimo numérico coinciden (β = 1)",
          np.max(np.abs(xc - xt)) < 1e-6 * m.X and np.max(np.abs(xn - xt)) < 1e-4 * m.X,
          f"máx diferencia {max(np.max(np.abs(xc - xt)), np.max(np.abs(xn - xt))):.1e} contratos")

    # 6 ------------------------------------------ fórmulas (20)-(21)
    Ec, Vc = ac_cerrada_momentos(m.X, m.N, m.tau, 400.0 ** 2, eta, m.gamma, m.eps, lam)
    ed = evaluar(m, xc)
    check("E y V cerradas de Almgren-Chriss = sumas discretas",
          abs(Ec / ed["E"] - 1) < 1e-9 and abs(Vc / ed["V"] - 1) < 1e-9)

    # 7 ------------------------------------------ λ → 0 da VWAP
    cfg5 = replace(cfg, contratos=5000.0, horizonte_min=390, paso_min=5)
    mv = construir_mercado(cfg5, perf, 1.6e-4, 600_000, 21000.0)
    x0 = ac_optima(mv, 1e-18)
    check("sin aversión al riesgo, con impacto en la participación, el óptimo es el VWAP",
          np.max(np.abs(x0 - vwap(mv))) < 2e-3 * mv.X,
          f"máx desviación {np.max(np.abs(x0 - vwap(mv))):.2f} contratos de {mv.X:.0f}")

    # 8 ------------------------------------------ λ → ∞: inmediata sin tope, al tope con tope
    libre = replace(mv, part_max=np.inf)
    xi = ac_optima(libre, lambda_referencia(libre) * 1e9)
    xt = ac_optima(mv, lambda_referencia(mv) * 1e9)
    nt = xt[:-1] - xt[1:]
    k_ = int(np.sum(np.cumsum(mv.tope) < mv.X))
    check("con aversión extrema: inmediata sin tope; al tope de participación con tope",
          urgencia(xi, 1 / mv.N) > 0.97 and np.allclose(nt[:k_], mv.tope[:k_], rtol=1e-3)
          and np.all(nt <= mv.tope * (1 + 1e-9)),
          f"con tope {mv.part_max:.0%}: {k_} tramo(s) al máximo")

    # 9 ------------------------------------------ frontera monótona
    fr = frontera(mv, lambda_referencia(mv) * np.logspace(-3, 4, 25))
    check("frontera eficiente: al subir λ el costo esperado sube y el riesgo baja",
          bool(np.all(np.diff(fr["E"]) > -1e-6 * fr["E"].abs().max())
               and np.all(np.diff(fr["SD"]) < 1e-6 * fr["SD"].max())))

    # 10 ----------------------------------------- la AC óptima gana a las otras siete
    lam10 = lambda_referencia(libre) * 3
    tr10 = estrategias(libre, lam10, replace(cfg5, part_max=1.0))
    u_opt = objetivo(libre, tr10["AC óptima"], lam10)
    peor = min(objetivo(libre, x, lam10) - u_opt for n, x in tr10.items() if n != "AC óptima")
    check("la AC óptima tiene el menor E + λV de las 8 estrategias", peor >= -1e-6 * u_opt,
          f"margen mínimo {peor:,.2f} USD")

    # 11 ----------------------------------------- λ por confianza: interior o esquina
    lam11, modo11 = elegir_lambda(mv, cfg5)
    z = _z(cfg5.var_conf)
    x11 = ac_optima(mv, lam11)
    g = lambda l: (lambda e: e["E"] + z * e["SD"])(evaluar(mv, ac_optima(mv, l)))
    if "ESQUINA" in modo11:
        ok11, det11 = g(lam11) <= g(lam11 * 0.5) + 1e-6, "esquina: la más rápida permitida"
    else:
        ok11 = (g(lam11) <= min(g(lam11 * 0.8), g(lam11 * 1.25)) + 1e-6 * g(lam11)
                and abs(2 * lam11 * evaluar(mv, x11)["SD"] / z - 1) < 0.05)
        det11 = f"2λ·SD = {2 * lam11 * evaluar(mv, x11)['SD']:.3f} contra z = {z:.3f}"
    check("el λ por confianza minimiza E + z·SD", ok11, det11)

    # 12 ----------------------------------------- λ por vida media
    lam12 = lambda_vida_media(mv, 60.0)
    vm = vida_media(ac_optima(mv, lam12), mv.tau)
    check("--vida-media 60 da una trayectoria óptima con vida media de 60 min", abs(vm - 60) < 1.5,
          f"{vm:.1f} min")

    # 13 ----------------------------------------- POV
    xp = pov(mv, 0.10)
    np_ = xp[:-1] - xp[1:]
    check("POV: nunca pasa de su tasa y termina el bloque",
          abs(np_.sum() - mv.X) < 1e-6 and np.all(np_[:-1] <= 0.10 * mv.vol[:-1] + 1e-9))

    # 14 ----------------------------------------- tus front/back-loaded
    xf, xb = cargada(mv, 0.3, 0.6), cargada(mv, 0.7, 0.4)
    k30, k70 = int(mv.N * 0.3), int(mv.N * 0.7)
    check("tus Front/Back-loaded: 60 % en el primer 30 % y 60 % en el último 30 %",
          abs((mv.X - xf[k30]) / mv.X - 0.6) < 1e-9 and abs(xb[k70] / mv.X - 0.6) < 1e-9
          and abs(xf[-1]) < 1e-9 and abs(xb[-1]) < 1e-9)

    # 15 ----------------------------------------- réplica gaussiana, con retornos de 1 minuto
    R = (rng.normal(0, 1, (4000, int(mv.T)))
         * np.repeat(np.sqrt(mv.sig2 / mv.tau), int(mv.tau)) / mv.S0)
    x15 = ac_optima(mv, lam10)
    c = costos_replica(mv, x15, R, 1)
    e15 = evaluar(mv, x15)
    check("réplica con retornos gaussianos: media ≈ E y SD ≈ √V",
          abs(np.mean(c) - e15["E"]) < 4 * e15["SD"] / math.sqrt(len(c))
          and abs(np.std(c) / e15["SD"] - 1) < 0.05)

    # 16 ----------------------------------------- ex post: signo y costo determinista
    T15 = int(mv.T)
    c0 = costos_replica(mv, x15, np.zeros((1, T15)), 1)[0]
    c_baja = costos_replica(mv, x15, np.full((1, T15), -1e-4), 1)[0]
    c_baja_compra = costos_replica(mv, x15, np.full((1, T15), -1e-4), -1)[0]
    check("ex post: sin movimiento cuesta E; si el precio baja, a la venta le cuesta más y a la "
          "compra menos", abs(c0 - e15["E"]) < 1e-6 and c_baja > c0 > c_baja_compra)

    # 17-20 ------------------------------------- de punta a punta, y tu script medido
    df, _ = simular(cfg, semilla=12)
    fechas = np.unique(sesion_y_minuto(df.index, cfg.tz_mercado)[0])
    c17 = replace(cfg5, fecha=str(pd.Timestamp(fechas[-1]).date()), har_min=40, replica_dias=120)
    b17 = preparar_barras(df, c17)
    res = analizar(b17, c17, sensib=False)
    b17b = b17.copy()
    ult = b17b["sesion"] == b17b["sesion"].max()
    fac = np.exp(np.cumsum(rng.normal(0, 3e-3, int(ult.sum()))))
    for col_ in ("open", "high", "low", "close"):
        b17b.loc[ult, col_] = b17b.loc[ult, col_] * fac
    b17b.loc[ult, "volume"] = b17b.loc[ult, "volume"] * 5
    res_b = analizar(b17b, c17, sensib=False)
    check("nada del plan mira el día de ejecución (alterar ese día no cambia σ, perfil ni ADV)",
          np.allclose(res.m.sig2 / res.m.S0 ** 2, res_b.m.sig2 / res_b.m.S0 ** 2)
          and np.allclose(res.m.vol, res_b.m.vol) and res.diag["adv"] == res_b.diag["adv"],
          "sólo cambia el precio de llegada, que sí se conoce al empezar")
    t_ = res.tu["tabla"]
    check("tu script: todos los λ de tu lista dan un TWAP (κT ≈ 0.01)",
          bool((t_["kappaT"] < 0.02).all() and (t_["desv_twap"] < 0.01).all()),
          f"κT máx {t_['kappaT'].max():.1e} · desviación máx {t_['desv_twap'].max():.1e} contratos")
    g17 = res.extra.get("granularidad") if res.extra else None
    check("tu script: el costo en bps no tiene unidades consistentes",
          t_["costo_bps"].iloc[0] > 100 and res.tabla.loc["TWAP", "E_bps"] < 20,
          f"tu script {t_['costo_bps'].iloc[0]:.0f} bps · módulo {res.tabla.loc['TWAP', 'E_bps']:.2f} bps")

    # 20b ---------------------------------------- el tamaño del tramo ya no inventa ahorro
    us = {}
    for vz in ("discreta", "continua"):
        us[vz] = []
        for p_ in (1, 5, 30):
            mp = replace(construir_mercado(replace(cfg5, paso_min=p_), perf, 1.6e-4, 600_000,
                                           21000.0), varianza=vz)
            e_ = evaluar(mp, ac_optima(mp, lam11))
            us[vz].append((e_["E"] + lam11 * e_["V"]) / mp.nocional * 1e4)
    uc, ud = us["continua"], us["discreta"]
    check("tramos más gruesos no pueden salir más baratos (menos opciones); con la varianza "
          "discreta del artículo salen MUCHO más baratos",
          abs(uc[0] / uc[1] - 1) < 0.05 and uc[2] >= uc[1] * 0.99 and ud[2] < 0.5 * ud[0],
          "tramos 1/5/30 min → discreta " + " · ".join(f"{u:.2f}" for u in us["discreta"])
          + " bps; continua " + " · ".join(f"{u:.2f}" for u in us["continua"]) + " bps")

    # 21 ----------------------------------------- Telegram: nunca el token
    tok = "123456789:" + "A" * 35
    msg = _sin_token(f"fallo en https://api.telegram.org/bot{tok}/sendMessage", tok)
    check("los errores de Telegram nunca muestran el token", tok not in msg and "…" in msg)

    # 22 ----------------------------------------- Telegram de punta a punta, sin red
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
                and "á <b>".encode() in cuerpo and tok.encode() not in cuerpo)
    finally:
        urllib.request.urlopen = viejo
        png.unlink(missing_ok=True)
    check("Telegram: el multipart de sendPhoto está bien formado y no lleva el token", bool(bien))

    # 23 ----------------------------------------- ninguna key escrita en este archivo
    fuente = Path(__file__).read_text(encoding="utf-8")
    check("no hay API keys ni tokens escritos en el código",
          not re.search("db" + "-" + r"[A-Za-z0-9]{20,}", fuente)
          and not re.search(r"\d{8,10}:" + r"[A-Za-z0-9_-]{35}", fuente))

    # 24 ----------------------------------------- mensaje de Telegram y plan
    txt = mensaje_telegram(res)
    check("el mensaje de Telegram cabe y el plan suma el bloque",
          len(txt) <= 4096 and "<pre>" in txt and res.plan["contratos"].sum() == int(c17.contratos),
          f"{len(txt)} caracteres · plan de {res.plan['contratos'].sum():,} contratos")

    print()
    if fallas:
        print(f"❌ {len(fallas)} de {hecho} pruebas fallaron: {', '.join(fallas)}")
        return 1
    print(f"✅ Las {hecho} pruebas pasaron.")
    return 0


# =============================================================================
# 17. LÍNEA DE COMANDOS
# =============================================================================
def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="almgren_chriss_market_impact.py",
        description="Almgren-Chriss AC v2 — ejecución óptima con impacto y riesgo en unidades "
                    "consistentes, parámetros estimados sin mirar el día que se ejecuta.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="La API key se lee de DATABENTO_API_KEY; Telegram, de TELEGRAM_BOT_TOKEN y "
               "TELEGRAM_CHAT_ID. Nunca los escribas en el código.")
    p.add_argument("--pruebas", action="store_true", help="pruebas internas (sin red ni datos)")
    p.add_argument("--simulacion", action="store_true",
                   help="datos simulados; la última sesión hace de día de ejecución")
    p.add_argument("--sin-tablero", action="store_true", help="no genera los PNG")
    p.add_argument("--sin-ventana", action="store_true", help="guarda los PNG sin abrir nada")
    p.add_argument("--sin-cache", action="store_true", help="vuelve a descargar de Databento")
    p.add_argument("--sin-sensibilidad", action="store_true", help="salta el análisis de sensibilidad")

    d = p.add_argument_group("datos y contrato")
    d.add_argument("--fecha", default=None, help="sesión a ejecutar, AAAA-MM-DD")
    d.add_argument("--symbol", default=None)
    d.add_argument("--dataset", default=None)
    d.add_argument("--calentamiento", type=int, default=None, dest="dias_calentamiento",
                   help="días naturales de historia previa")
    d.add_argument("--costo-max", type=float, default=None, dest="costo_max_usd")
    d.add_argument("--multiplicador", type=float, default=None, help="USD por punto")
    d.add_argument("--tick", type=float, default=None)
    d.add_argument("--spread-ticks", type=float, default=None, dest="spread_ticks")
    d.add_argument("--comision", type=float, default=None, dest="comision_usd",
                   help="USD por contrato y por lado")

    e = p.add_argument_group("ejecución")
    e.add_argument("--lado", choices=["venta", "compra"], default=None)
    e.add_argument("--contratos", type=float, default=None)
    e.add_argument("--inicio", default=None, dest="inicio_ct", help="HH:MM hora de Chicago")
    e.add_argument("--horizonte", type=int, default=None, dest="horizonte_min", help="minutos")
    e.add_argument("--paso", type=int, default=None, dest="paso_min", help="minutos por tramo")
    e.add_argument("--lambda", type=float, default=None, dest="aversion",
                   help="aversión al riesgo λ en 1/USD")
    e.add_argument("--var-conf", type=float, default=None, dest="var_conf",
                   help="λ que minimiza E + z·SD a esta confianza (por omisión 0.95)")
    e.add_argument("--vida-media", type=float, default=None, dest="vida_media_min",
                   help="λ con el que la mitad del bloque se ejecuta en estos minutos")
    e.add_argument("--part-max", type=float, default=None, dest="part_max",
                   help="participación máxima por tramo, p. ej. 0.25 (≥ 1 = sin tope)")
    e.add_argument("--pov", type=float, default=None, help="tasa de la estrategia POV de referencia")

    i = p.add_argument_group("coeficientes de impacto")
    i.add_argument("--eta0", type=float, default=None)
    i.add_argument("--beta", type=float, default=None)
    i.add_argument("--gamma0", type=float, default=None)

    t = p.add_argument_group("Telegram")
    t.add_argument("--telegram", action="store_true", help="envía el resumen y los tableros")
    t.add_argument("--telegram-solo-alertas", action="store_true",
                   help="envía sólo si hay volatilidad alta, sorpresa de costo o bloque grande")
    t.add_argument("--telegram-documentos", action="store_true",
                   help="envía los PNG como documento (sin compresión)")
    t.add_argument("--telegram-buscar-chat", action="store_true",
                   help="lista los chat_id que le escribieron a tu bot y sale")

    s = p.add_argument_group("simulación")
    s.add_argument("--sesiones-sim", type=int, default=None, dest="sim_sesiones")
    s.add_argument("--semilla", type=int, default=None, dest="sim_semilla")
    return p


def config_desde_args(a: argparse.Namespace) -> Config:
    cambios = {}
    for k in ("fecha", "symbol", "dataset", "dias_calentamiento", "costo_max_usd", "multiplicador",
              "tick", "spread_ticks", "comision_usd", "lado", "contratos", "inicio_ct",
              "horizonte_min", "paso_min", "aversion", "var_conf", "vida_media_min", "part_max",
              "pov", "eta0", "beta", "gamma0", "sim_sesiones", "sim_semilla"):
        v = getattr(a, k, None)
        if v is not None:
            cambios[k] = v
    if getattr(a, "sin_cache", False):
        cambios["usar_cache"] = False
    return replace(CFG, **cambios)


def main(argv: list[str] | None = None) -> int:
    a = construir_parser().parse_args(argv)
    cfg = config_desde_args(a)
    if a.pruebas:
        return pruebas()
    if a.telegram_buscar_chat:
        return buscar_chat_telegram()
    try:                                    # validar la ventana ANTES de descargar nada
        m0 = minuto_de_sesion(cfg.inicio_ct)
    except ValueError as ex:
        sys.exit(f"❌ {ex}")
    if m0 + cfg.horizonte_min > MINUTOS_SESION:
        sys.exit(f"❌ {cfg.inicio_ct} CT + {cfg.horizonte_min} min se sale de la sesión (Globex "
                 f"cierra a las 16:00 CT). Máximo desde esa hora: {MINUTOS_SESION - m0} min.")
    if cfg.horizonte_min % cfg.paso_min or cfg.horizonte_min < 2 * cfg.paso_min:
        sys.exit("❌ El horizonte debe ser múltiplo del paso y de al menos dos tramos.")

    print(f"▶ {IDENTIFICADOR} · {cfg.symbol} · {cfg.lado} {cfg.contratos:,.0f} contratos · "
          f"{cfg.horizonte_min} min desde {cfg.inicio_ct} CT en tramos de {cfg.paso_min} min")
    if a.simulacion:
        print(f"🎲 {cfg.sim_sesiones} sesiones simuladas de 1 min tipo NQ (perfil en U, volatilidad")
        print("   estocástica, colas gruesas, rolls). La última hace de día de ejecución.")
        crudo, _ = simular(cfg)
        fechas = np.unique(sesion_y_minuto(crudo.index, cfg.tz_mercado)[0])
        cfg = replace(cfg, fecha=str(pd.Timestamp(fechas[-1]).date()))
    else:
        crudo = obtener_datos(cfg)
    barras = preparar_barras(crudo, cfg)
    print(f"📊 {len(barras):,} barras de 1 min · {barras.index[0]:%Y-%m-%d} → "
          f"{barras.index[-1]:%Y-%m-%d} (UTC) · ejecución {cfg.fecha}")

    res = analizar(barras, cfg, sensib=not a.sin_sensibilidad)
    reporte_datos(res)
    reporte_tu_script(res)
    reporte_volatilidad(res)
    reporte_impacto(res)
    reporte_ejecucion(res)
    reporte_sensibilidad(res)

    rutas, plt_, ventana = ([], None, False)
    if not a.sin_tablero:
        print()
        rutas, plt_, ventana = tableros(res, mostrar=not a.sin_ventana)
    guardar(res)

    if a.telegram or a.telegram_solo_alertas:
        avisos = hay_alerta(res)
        if a.telegram_solo_alertas and not avisos:
            print("📭 Telegram: sin alertas.")
        else:
            enviar_telegram(res, rutas, documentos=a.telegram_documentos)

    _titulo("CÓMO LEER ESTO")
    print("  1. Todo lo que decide el plan sale de las sesiones ANTERIORES al día de ejecución.")
    print("     Ese día sólo se usa al final, para ver cómo le fue a cada estrategia.")
    print("  2. Todo está en USD y contratos, así que λ tiene unidades (1/USD) y significa algo:")
    print("     cuánto costo esperado aceptas pagar por quitar varianza.")
    print("  3. La frontera eficiente es el menú; λ elige el punto. --var-conf lo elige para que")
    print("     la estrategia minimice el costo que no se excede con esa confianza.")
    print("  4. Un día no decide nada: la réplica sobre las sesiones previas (CVaR95) sí.")
    print("  5. η₀ y β no se pueden medir con OHLCV. El tornado y el arrepentimiento dicen si tu")
    print("     plan cambiaría si estuvieran mal; en general cambia el COSTO, no el PLAN.")

    if rutas and not a.sin_ventana:
        print()
        mostrar_tableros(plt_, ventana, rutas)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrumpido.")
        sys.exit(130)
