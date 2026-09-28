# -*- coding: utf-8 -*-
"""
RV INSTITUCIONAL AC v2 — volatilidad realizada robusta por sesión CME + ejecución óptima
Almgren-Chriss con la volatilidad y la liquidez MEDIDAS en tus datos
Datos: Databento OHLCV-1m (GLBX.MDP3), agrupadas por SESIÓN de Globex (17:00 → 16:00 CT).

Qué hace, en una línea: mide la volatilidad de cada SESIÓN de Globex con estimadores robustos
a saltos, prueba formalmente si hubo salto, pronostica la volatilidad de la próxima sesión, y
con esa σ —y el volumen que de verdad hay a cada minuto— calcula cómo ejecutar un bloque de
contratos equilibrando impacto y riesgo (Almgren-Chriss), compara estrategias y mide qué tan
sensible es la decisión a cada supuesto. Y si quieres, te lo manda por Telegram.

LO QUE PEDISTE, HECHO A FONDO

  1. OPTIMIZACIÓN DEL TRADE-OFF ENTRE IMPACTO Y RIESGO. Almgren-Chriss resuelto de tres
     maneras que se verifican entre sí: la fórmula cerrada del artículo (σ y η constantes),
     el sistema tridiagonal EXACTO cuando σ_k y η_k cambian por tramo, y el óptimo numérico
     con el modelo completo: σ por minuto del perfil intradía MEDIDO, impacto temporal
     cóncavo en la participación (β = 0.6), impacto permanente y tope de participación
     (POV, 25 % por omisión). Con β = 1 y la varianza del artículo las tres coinciden a
     menos de 1e-5 contratos, y sus fórmulas (20)-(21) de E y V con las sumas discretas.
     Una corrección al modelo discreto: ahí lo que se ejecuta dentro de un tramo no carga
     riesgo, así que con tramos grandes "vende" media hora de flujo al precio del inicio
     (medido con 5 000 NQ en la sesión regular: E + λV bajaba de 15.0 a 3.9 bps al pasar de
     tramos de 1 a 30 min; con la corrección, 16.9 → 32.3, como debe ser). Aquí la
     tenencia baja en línea recta dentro del tramo, que es la varianza exacta de vender
     parejo y converge al modelo continuo.

  2. PARÁMETRO DE AVERSIÓN AL RIESGO. λ de tres maneras: directo en 1/USD (--lambda), por
     vida media (--vida-media), o —por omisión— el λ que minimiza E + z·SD al 95 %, el
     "costo que no se excede con 95 % de confianza" de la sección 4 del artículo. En un
     óptimo interior el precio marginal del riesgo, 2λ·SD, sale EXACTAMENTE z (medido:
     1.645 contra 1.645, también con el tope activo). Y cuando no hay óptimo interior el
     módulo lo dice en vez de inventarlo: con un bloque muy chico (~50 NQ), E + z·SD baja
     hasta la ejecución más rápida posible porque la pendiente de la frontera se queda
     por debajo de z. Con tus 500 NQ (0.13 % del volumen diario) sí hay óptimo interior,
     pero muy urgente: 97 % en los primeros 5 minutos, porque repartirlos en la primera
     hora de la sesión regular deja ~18 bps de desviación estándar contra ~4 bps de
     impacto por ir rápido.

  3. COEFICIENTES DE IMPACTO. ε (medio spread + comisión), η₀ y β del impacto temporal, γ₀
     del permanente, el η lineal equivalente que usaría la AC de libro, y la tabla de
     impacto por participación en bps, USD y ticks. σ y el volumen por minuto se MIDEN en
     tus datos. η₀ = 0.142, β = 0.6 y γ₀ = 0.314 vienen de Almgren, Thum, Hauptmann y Li
     (2005), porque el impacto CAUSAL no se puede medir con OHLCV: hace falta tu propio
     historial de ejecuciones. Lo digo en vez de fingir una regresión, y la sección de
     sensibilidad mide cuánto importa. Tampoco el spread: probé Corwin-Schultz sobre barras
     de 1 min y, con un spread verdadero de 1 tick, da entre 8 y 17 ticks. En NQ el spread
     es ~1/10 de la σ de un minuto y el rango alto-bajo no lo puede separar. Queda como
     supuesto explícito (--spread-ticks).

  4. COMPARACIÓN DE ESTRATEGIAS. AC óptima, AC clásica, VWAP, TWAP e inmediata: E[costo],
     SD, E + z·SD, participación máxima, y además una RÉPLICA sobre tus propias sesiones
     —la misma ventana horaria en ~250 días reales, reescalada a la σ pronosticada y sin la
     deriva de la muestra— con VaR y CVaR 95 % que sí ven las colas que la normalidad del
     modelo no ve. En la simulación (costo al 95 %, bps): AC óptima 9.5 · inmediata 11.4 ·
     AC clásica 11.5 · VWAP 28.3 · TWAP 30.8.

  5. ANÁLISIS DE SENSIBILIDAD VISUAL. Un tablero entero: urgencia (λ × η₀), costo al 95 %
     (σ × η₀), tornado, ARREPENTIMIENTO —cuánto pierdes si ejecutas el plan base y el
     parámetro verdadero era otro, que es la pregunta que decide—, horizonte y barrido de λ.
     Cada celda RE-OPTIMIZA; ninguna reescala un resultado. Lo que sale en la simulación:
     η₀ al doble mueve el costo de 6.7 a 10.0 bps pero el arrepentimiento es 0.38 bps. El
     costo es sensible a η₀; el PLAN casi no.

  Un resultado que conviene saber: sin aversión al riesgo y con impacto en función de la
  participación, el óptimo NO es el TWAP del artículo, es el VWAP (coincide a 0.05
  contratos de 500). Es la justificación formal de lo que hacen las mesas.

QUÉ SE MIDIÓ. Todo sobre sesiones simuladas de 1 min tipo NQ, 6 semillas × 300 sesiones:
perfil intradía en U con el pico de las 07:30 CT, volatilidad diaria e intradía estocástica,
rebote compra-venta, tick de 0.25, pausa diaria, fines de semana, 4 rolls y 24 SALTOS EN
MINUTOS CONOCIDOS por serie. Sobre datos reales no hay contra qué comparar.

      detector de saltos                    marcadas  precisión  exhaustividad     F1
      módulo · test BNS por sesión, 5 min      20.2      1.000        0.840      0.912
      tu script · días CDMX, 1 min             32.5      0.398        0.535      0.455
      falsas alarmas del test en sesiones SIN salto: 0 de 1 800 (nivel nominal 0.1 %)

  Precisión en puntos de volatilidad anual (RMSE, sesiones sin salto): RV 1 min 0.61 ·
  RV 5 min una rejilla 1.35 · RV 5 min submuestreada 1.10 · BV 1.16 · MedRV 1.20. En
  sesiones CON salto, contra la volatilidad continua: RV +6.9 puntos, BV +1.3, MedRV 0.0.
  Pronóstico fuera de muestra (QLIKE): HAR 0.100 · RV de ayer 0.134 · media de 22 sesiones
  0.156, con t de Diebold-Mariano 3.1 y 3.5.

  Sobre 1 min contra 5 min, lo honesto: si el ruido de microestructura es chico —y en NQ a
  1 min lo es; la firma de volatilidad del tablero te lo dice con TUS datos— el RV a 1 min
  es más preciso (0.61 contra 1.10). Pero el TEST de saltos a 1 min es frágil: si la
  volatilidad cambia de un minuto al siguiente, marca salto en el 100 % de las sesiones sin
  salto; a 5 min, en el 1.3 %. Por eso el muestreo por omisión es 5 min submuestreado.

QUÉ FALLABA EN EL SCRIPT QUE MANDASTE (los comentarios [v2] lo marcan en el código)

  · LA API KEY ESTÁ ESCRITA EN LA LÍNEA 14. Dala por publicada y regenérala. Aquí se lee de
    DATABENTO_API_KEY, igual que en tus módulos de z-score, VWAP y anomalías.

  · AGRUPA POR FECHA CALENDARIO DE CDMX, NO POR SESIÓN. Globex abre a las 17:00 CT y cierra
    a las 16:00 CT del día siguiente; tu "día" es la cola de una sesión, la pausa y la
    cabeza de la siguiente. Medido: 360 "días" para 300 sesiones, 60 de ellos domingos
    sueltos (Globex abre el domingo a las 16:00 o 17:00 CDMX, según la temporada), y 299 de
    360 con la pausa de 16-17 CT
    o el fin de semana adentro, contados como si fueran un retorno de 1 minuto.

  · LOS HUECOS Y LOS ROLLS ENTRAN COMO RETORNOS. log_ret se calcula sobre toda la serie. En
    promedio el 6 % del RV de cada "día" viene de retornos que no ocurrieron dentro de una
    sesión, y el día del roll el 90 %. Consecuencia: 19.7 de las 32.5 marcas de salto de tu
    script (el 60 %) caen en un día con roll o fin de semana.

  · EL "TEST DE BARNDORFF-NIELSEN & SHEPHARD" NO ES UN TEST. El docstring de detect_jumps
    copia la fórmula, pero el código marca salto si JumpRatio > 0.3 y un z-score RODANTE
    (que incluye el día que mide) pasa de 1.5. Ni el 0.3 ni el 1.5 tienen una probabilidad
    de error asociada. Y JUMP_THRESHOLD = 3.0 —justo el crítico del test al 0.1 %— se declara
    y nunca se usa.

  · PRICE_SCALE DIVIDE DOS VECES. Con databento moderno to_df() ya entrega float (verificado
    en la 0.87: price_type="float" por omisión), así que el NQ queda en 0.00002. No afecta a
    los retornos, sí al panel de precio y a cualquier costo en dólares.

  · LOS ROLLS NO SE PUEDEN VER EN LA COLUMNA symbol. Con stype_in="continuous" databento la
    llena con "NQ.n.0" en todas las filas (verificado en su código). Aquí se usa
    instrument_id. Esto también aplica a tu módulo de anomalías, que busca el roll en symbol.

  · LOS SALTOS FIRMADOS NO ESTIMAN NADA CONOCIDO. PosJump resta una bipotencia parcial sólo
    sobre los pares con r_t > 0. Aquí: semivarianzas realizadas (BNKS 2010) y la variación
    de salto firmada ΔJ = RS+ − RS− de Patton y Sheppard (2015).

  · NO PRONOSTICA NI DA INTERVALOS. Describe el pasado; para ejecutar hoy hace falta la σ de
    hoy. Aquí: HAR re-estimado cada día sólo con el pasado, e IC 95 % de cada RV.

  · Menores: ANNUALIZATION_FACTOR, FREQ_INTRADAY y TRADING_HOURS_PER_DAY no se usan; MedRV
    en un bucle de Python con un np.median por barra; BV sin el factor n/(n−1); exit() en
    vez de sys.exit().

  · LO QUE ESTABA BIEN: RSkew y RKurt son los de Amaya et al. (2015), con la referencia
    correcta (normal = 3). Lo que no separan es la estacionalidad intradía: en la simulación
    la curtosis mediana es 5.7 bruta contra 4.2 desestacionalizada. Van las dos.

CÓMO SE USA
    pip install numpy pandas scipy matplotlib databento
    python realized_volatility_institucional.py --pruebas        # 25 pruebas, sin red
    python realized_volatility_institucional.py --simulacion     # todo, con verdad conocida
    python realized_volatility_institucional.py                  # tus datos (jul-ago 2026)
    python realized_volatility_institucional.py --contratos 2000 --horizonte 120 --inicio 09:00
    python realized_volatility_institucional.py --var-conf 0.75  # menos aversión al riesgo
    python realized_volatility_institucional.py --lambda 2e-6    # λ directo, en 1/USD
    python realized_volatility_institucional.py --vida-media 10  # la mitad en 10 minutos
    python realized_volatility_institucional.py --symbol ES.n.0 --part-max 0.10
    python realized_volatility_institucional.py --telegram               # resumen + 3 tableros
    python realized_volatility_institucional.py --telegram-solo-alertas  # sólo si hay salto
                                                                         # o volatilidad alta
  La hora de inicio va en hora de CHICAGO (el reloj del mercado; no cambia con el horario de
  verano de EE. UU.). El reporte y el plan muestran también la hora de CDMX.

LAS CREDENCIALES NO VAN EN EL CÓDIGO — igual que en tus otros módulos.
    Databento   DATABENTO_API_KEY     PowerShell:  setx DATABENTO_API_KEY "db-..."
    Telegram    TELEGRAM_BOT_TOKEN                 setx TELEGRAM_BOT_TOKEN "123456789:AA..."
                TELEGRAM_CHAT_ID                   setx TELEGRAM_CHAT_ID "123456789"
    (cierra y abre VS Code después de setx). El token te lo da @BotFather; el chat_id lo
    encuentras con --telegram-buscar-chat después de escribirle /start a tu bot. Si falta
    alguna y la terminal es interactiva, se pide con getpass y no se guarda. Los errores de
    Telegram nunca imprimen el token, y una de las pruebas revisa que en este archivo no haya
    ninguna key ni token escritos.

FUENTES
  Almgren, R. y Chriss, N. (2000), "Optimal execution of portfolio transactions", Journal of
      Risk 3(2). — el modelo, la trayectoria sinh y las fórmulas de E y V.
  Almgren, R., Thum, C., Hauptmann, E. y Li, H. (2005), "Direct estimation of equity market
      impact", Risk 18(7). — η₀ = 0.142, β = 3/5, γ₀ = 0.314.
  Barndorff-Nielsen, O. y Shephard, N. (2004), "Power and bipower variation with stochastic
      volatility and jumps", Journal of Financial Econometrics 2(1); (2006), "Econometrics of
      testing for jumps in financial economics using bipower variation", JFEc 4(1).
  Huang, X. y Tauchen, G. (2005), "The relative contribution of jumps to total price
      variance", JFEc 3(4). — el estadístico de razón con el ajuste max(1, TQ/BV²).
  Andersen, T., Dobrev, D. y Schaumburg, E. (2012), "Jump-robust volatility estimation using
      nearest neighbor truncation", Journal of Econometrics 169(1). — MedRV.
  Andersen, T., Bollerslev, T. y Diebold, F. (2007), "Roughing it up", Review of Economics and
      Statistics 89(4). — separar la parte continua de los saltos significativos.
  Barndorff-Nielsen, O., Kinnebrock, S. y Shephard, N. (2010), "Measuring downside risk:
      realised semivariance", en Volatility and Time Series Econometrics, Oxford UP.
  Patton, A. y Sheppard, K. (2015), "Good volatility, bad volatility", REStat 97(3).
  Zhang, L., Mykland, P. y Aït-Sahalia, Y. (2005), "A tale of two time scales", Journal of the
      American Statistical Association 100. — submuestreo y TSRV.
  Corsi, F. (2009), "A simple approximate long-memory model of realized volatility", JFEc 7(2).
  Patton, A. (2011), "Volatility forecast comparison using imperfect volatility proxies",
      Journal of Econometrics 160(1). — por qué QLIKE.
  Amaya, D., Christoffersen, P., Jacobs, K. y Vasquez, A. (2015), "Does realized skewness
      predict the cross-section of equity returns?", Journal of Financial Economics 118(1).
  Corwin, S. y Schultz, P. (2012), "A simple way to estimate bid-ask spreads from daily high
      and low prices", Journal of Finance 67(2). — probado y descartado a 1 min, ver arriba.
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
from dataclasses import dataclass, field, replace
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

IDENTIFICADOR = "rv-institucional-ac-v2"
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)
np.seterr(all="ignore")

# --- Constantes de la sesión de CME Globex ---
MINUTOS_SESION = 1380            # 17:00 → 16:00 CT (23 horas)
ANCHO = 1440                     # la matriz cubre el día completo por si llegan barras en la pausa
DESFASE_H = 7                    # hora CT + 7 h → la sesión que abre a las 17:00 cae en su fecha

# --- Constantes de los estimadores ---
MU1 = math.sqrt(2.0 / math.pi)                                  # E|Z|
MU43 = 2.0 ** (2.0 / 3.0) * math.gamma(7.0 / 6.0) / math.gamma(0.5)   # E|Z|^(4/3)
THETA_BNS = math.pi ** 2 / 4.0 + math.pi - 5.0                  # ≈ 0.6090
C_MEDRV = math.pi / (6.0 - 4.0 * math.sqrt(3.0) + math.pi)

# Multiplicador (USD por punto) y tick de los contratos más comunes de CME.
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
    start: str = "2026-07-01T00:00:00"     # ventana que se REPORTA (la tuya)
    end: str = "2026-09-01T00:00:00"       # exclusivo: incluye el 31 de agosto
    dias_calentamiento: int = 330          # historia previa para el HAR, perfiles y réplica
    cache_dir: str = "datos_databento"
    usar_cache: bool = True
    salida_dir: str = "salidas_rv"
    costo_max_usd: float = 25.0

    # --- Contrato ---
    multiplicador: float | None = None     # None = según el símbolo (NQ: 20 USD por punto)
    tick: float | None = None              # None = según el símbolo (NQ: 0.25)
    spread_ticks: float = 1.0              # diferencial compra-venta supuesto, en ticks
    comision_usd: float = 2.0              # por contrato y por lado, todo incluido (supuesto)

    # --- Sesión CME ---
    tz_mercado: str = "America/Chicago"
    tz_local: str = "America/Mexico_City"
    hueco_max_min: int = 30                # un hueco mayor dentro de la sesión no es retorno
    cobertura_min: float = 0.80            # fracción de las 23 h para llamar "completa" a una sesión

    # --- Estimadores ---
    freq_min: int = 5                      # muestreo de RV/BV/MedRV y del test de saltos
    submuestreo: bool = True               # promedia las freq_min rejillas desfasadas
    alfa_salto: float = 0.001              # nivel del test de Barndorff-Nielsen-Shephard
    frecuencias_firma: tuple[int, ...] = (1, 2, 3, 5, 10, 15, 20, 30)

    # --- Pronóstico HAR ---
    har_ventana: int = 500
    har_min: int = 60

    # --- Perfil intradía ---
    perfil_dias: int = 120
    perfil_suavizado: int = 5

    # --- Ejecución (Almgren-Chriss) ---
    lado: str = "venta"                    # "venta" | "compra"
    contratos: float = 500.0
    inicio_ct: str = "08:30"               # hora de Chicago (reloj del mercado)
    horizonte_min: int = 60
    paso_min: int = 1
    aversion: float | None = None          # λ en 1/USD; None = se deduce de var_conf
    var_conf: float = 0.95                 # λ tal que se minimiza E + z·SD (Almgren-Chriss §4)
    vida_media_min: float | None = None    # alternativa: λ que da esta vida media
    part_max: float = 0.25                 # participación máxima por tramo (POV); ≥ 1 = sin tope

    # --- Impacto (Almgren, Thum, Hauptmann y Li 2005) ---
    eta0: float = 0.142                    # impacto temporal: η·σ·(participación)^β
    beta: float = 0.6
    gamma0: float = 0.314                  # impacto permanente: γ·σ·(X / volumen diario)
    adv_dias: int = 20

    # --- Réplica histórica ---
    replica_dias: int = 250
    escalar_vol: bool = True
    sin_deriva: bool = True

    # --- Presentación ---
    carteles: int = 8

    # --- Simulación ---
    sim_sesiones: int = 300
    sim_saltos: int = 24
    sim_rolls: int = 4
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
# 2. SESIONES DE CME — el arreglo de fondo
# =============================================================================
# Tu script agrupa por FECHA CALENDARIO DE CDMX:  df_intraday['date'] = index.date  sobre un
# índice ya convertido a America/Mexico_City. Globex no abre y cierra a medianoche de CDMX:
# abre a las 17:00 CT y cierra a las 16:00 CT del día siguiente. Resultado, en cada "día":
#   · la cola de una sesión, la pausa de 16:00-17:00 CT y la cabeza de la sesión siguiente;
#   · el retorno de la pausa (una hora sin operar) contado como si fuera un retorno de 1 min;
#   · los domingos aparecen como "día" propio (abre 17:00 CT = 16:00 CDMX) con el hueco del
#     FIN DE SEMANA adentro;
#   · y el día del roll del .n.0, el salto de precio entre contratos entra como retorno.
# Aquí la unidad es la sesión: fecha de sesión = fecha de (hora CT + 7 h).

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


# =============================================================================
# 3. ESTIMADORES DE VARIACIÓN REALIZADA
# =============================================================================
def _mediana3(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
    return np.maximum(np.minimum(x, y), np.minimum(np.maximum(x, y), z))


def estimadores_rejilla(r: np.ndarray) -> dict | None:
    """
    Todos los estimadores sobre UNA rejilla de retornos r_1..r_n de una sesión.

        RV    = Σ r²                                               (varianza realizada)
        BV    = (π/2)·n/(n−1)·Σ |r_i||r_{i−1}|                     (bipotencia, BNS 2004)
        MedRV = π/(6−4√3+π)·n/(n−2)·Σ med(|r_{i−1}|,|r_i|,|r_{i+1}|)²   (ADS 2012)
        TQ    = n·μ_{4/3}^{−3}·n/(n−2)·Σ |r_i r_{i−1} r_{i−2}|^{4/3}    (cuarticidad tripotencia)
        RS±   = Σ r² 1{r ≷ 0}                                      (semivarianzas, BNKS 2010)

    [v2] Tu BV no lleva el factor n/(n−1): con 276 retornos de 5 min es un sesgo de −0.4 %,
    pequeño, pero gratis de quitar. Tu MedRV recorre la sesión en un bucle de Python con un
    np.median por barra; aquí la mediana de tres se calcula con mínimos y máximos vectorizados.
    """
    r = np.asarray(r, dtype=float)
    r = r[np.isfinite(r)]
    n = len(r)
    if n < 10:
        return None
    a = np.abs(r)
    rv = float(r @ r)
    bv = (math.pi / 2.0) * (n / (n - 1.0)) * float(a[1:] @ a[:-1])
    med = _mediana3(a[:-2], a[1:-1], a[2:])
    medrv = C_MEDRV * (n / (n - 2.0)) * float(med @ med)
    a43 = a ** (4.0 / 3.0)
    tq = n * MU43 ** -3 * (n / (n - 2.0)) * float(np.sum(a43[2:] * a43[1:-1] * a43[:-2]))
    pos = r > 0
    rsp = float(r[pos] @ r[pos])
    return {"n": float(n), "RV": rv, "BV": bv, "MedRV": medrv, "TQ": tq,
            "RSp": rsp, "RSn": rv - rsp, "S3": float(np.sum(r ** 3)),
            "S4": float(np.sum(r ** 4))}


def estimadores_submuestreados(L: np.ndarray, k: int, submuestreo: bool = True) -> dict | None:
    """
    Promedio de los estimadores sobre las k rejillas de k minutos desfasadas un minuto.

    Muestrear a 5 min tira 4 de cada 5 minutos. Promediar las 5 rejillas desfasadas recupera
    casi toda la precisión de 1 min sin heredar su ruido de microestructura (Zhang, Mykland y
    Aït-Sahalia 2005). Para el test de saltos esto lo vuelve CONSERVADOR: la varianza del
    promedio es menor que la de una rejilla, y el test usa la de una rejilla.
    """
    acumulado = []
    for o in (range(k) if submuestreo else (0,)):
        e = estimadores_rejilla(np.diff(L[o::k]))
        if e is not None:
            acumulado.append(e)
    if not acumulado:
        return None
    return {c: float(np.mean([e[c] for e in acumulado])) for c in acumulado[0]}


def rv_submuestreada(L: np.ndarray, k: int) -> float:
    vals = [float(np.sum(np.diff(L[o::k]) ** 2)) for o in range(k) if len(L[o::k]) > 2]
    return float(np.mean(vals)) if vals else np.nan


def tsrv(L: np.ndarray, k: int) -> float:
    """Two-scale RV (Zhang, Mykland y Aït-Sahalia 2005), con su ajuste de muestra finita."""
    r1 = np.diff(L)
    n = len(r1)
    if k < 2 or n < 3 * k:                 # con k = 1 no hay dos escalas
        return np.nan
    nbar = (n - k + 1.0) / k
    return (rv_submuestreada(L, k) - (nbar / n) * float(r1 @ r1)) / (1.0 - nbar / n)


def z_bns(rv: float, bv: float, tq: float, n: float) -> float:
    """
    Estadístico de razón de Barndorff-Nielsen y Shephard (2006), versión "max-ajustada"
    de Huang y Tauchen (2005):

        z = [(RV − BV)/RV] / sqrt( (π²/4 + π − 5) · (1/n) · max(1, TQ/BV²) )  →  N(0, 1)

    [v2] El docstring de tu detect_jumps dice "test de Barndorff-Nielsen & Shephard" y copia
    esta fórmula, pero el código hace otra cosa: marca salto si JumpRatio > 0.3 y el z-score
    RODANTE de 20 días del JumpRatio (que incluye el día que mide) pasa de 1.5. No es un
    test: ni el 0.3 ni el 1.5 tienen una probabilidad de error asociada. Y tu JUMP_THRESHOLD
    = 3.0 —que es justo el crítico de este test al 0.1 %— se declara y no se usa nunca.
    """
    if not (rv > 0 and bv > 0 and n > 3):
        return np.nan
    return ((rv - bv) / rv) / math.sqrt(THETA_BNS / n * max(1.0, tq / bv ** 2))


# =============================================================================
# 4. SIMULADOR — la verdad contra la que se mide todo
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
# 5. DATOS — Databento, con la key FUERA del código
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
    "  • La que estaba escrita en la línea 14 de Realized_Volatility_Institucional.py hay que\n"
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
    carpeta = _ruta(cfg.cache_dir)
    carpeta.mkdir(parents=True, exist_ok=True)
    inicio = (pd.Timestamp(cfg.start) - pd.Timedelta(days=cfg.dias_calentamiento)
              ).strftime("%Y-%m-%dT%H:%M:%S")
    esquema = "ohlcv-1m"
    ruta = carpeta / (_nombre_seguro(cfg.dataset, cfg.symbol, inicio, cfg.end, esquema)
                      + ".dbn.zst")
    if ruta.exists() and cfg.usar_cache:
        print(f"📂 Usando caché local: {ruta.name}")
        return db.DBNStore.from_file(ruta)
    cliente = cliente or conectar()
    params = dict(dataset=cfg.dataset, symbols=cfg.symbol, stype_in=cfg.stype_in,
                  schema=esquema, start=inicio, end=cfg.end)
    costo = cliente.metadata.get_cost(**params)
    print(f"💵 Costo estimado: US$ {costo:,.2f}")
    if costo > cfg.costo_max_usd:
        sys.exit(f"💰 El costo (US$ {costo:,.2f}) supera tu tope de "
                 f"US$ {cfg.costo_max_usd:,.2f}.\n"
                 f"   Si estás de acuerdo:  --costo-max {math.ceil(costo) + 1}")
    temporal = ruta.with_name(ruta.name + ".parcial")
    temporal.unlink(missing_ok=True)
    print(f"📡 Descargando {cfg.symbol} {esquema} desde {inicio[:10]} …")
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
# 6. PANEL POR SESIÓN
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


def _momentos_desestacionalizados(L: np.ndarray, m_ini: int, k: int,
                                  cum_perfil: np.ndarray) -> tuple[float, float]:
    """
    Asimetría y curtosis realizadas de los retornos divididos entre la σ que el perfil
    intradía les asigna. Sin esto, la curtosis mezcla colas con estacionalidad: una sesión
    perfectamente normal pero con la apertura 3 veces más volátil que la madrugada ya da
    curtosis > 3. (La curtosis de tu script es correcta como número, pero no separa las dos
    cosas.)
    """
    sk, ku = [], []
    for o in range(k):
        idx = np.arange(o, len(L), k)
        if len(idx) < 12:
            continue
        r = np.diff(L[idx])
        ini = m_ini + idx[:-1]
        cuota = cum_perfil[np.minimum(ini + k, len(cum_perfil) - 1)] - cum_perfil[ini]
        z = r / np.sqrt(np.maximum(cuota, 1e-12))
        n, q = len(z), float(z @ z)
        if q > 0:
            sk.append(math.sqrt(n) * float(np.sum(z ** 3)) / q ** 1.5)
            ku.append(n * float(np.sum(z ** 4)) / q ** 2)
    return (float(np.mean(sk)), float(np.mean(ku))) if ku else (np.nan, np.nan)


def panel_diario(ses: Sesiones, cfg: Config,
                 perfil: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Estimadores por sesión + la firma de volatilidad (RV contra frecuencia de muestreo)."""
    k = int(cfg.freq_min)
    crit = _z(1.0 - cfg.alfa_salto)
    cum = (np.r_[0.0, np.cumsum(perfil["var"].to_numpy())] if perfil is not None else None)
    filas, firma = [], []
    for s in range(ses.S):
        L = ses.rejilla(s)
        e = estimadores_submuestreados(L, k, cfg.submuestreo)
        e1 = estimadores_rejilla(np.diff(L[::k]))           # una sola rejilla, para comparar
        r1 = np.diff(L)
        if e is None:
            filas.append({"n": 0})
            firma.append({})
            continue
        n = e["n"]
        z = z_bns(e["RV"], e["BV"], e["TQ"], n)
        rv = e["RV"]
        filas.append({
            **e,
            "RV1": float(r1 @ r1),
            "RV_1rejilla": e1["RV"] if e1 else np.nan,
            "TSRV": tsrv(L, k),
            "z_bns": z,
            "RSkew": math.sqrt(n) * e["S3"] / rv ** 1.5 if rv > 0 else np.nan,
            "RKurt": n * e["S4"] / rv ** 2 if rv > 0 else np.nan,
            # IC 95 % de la varianza integrada: Var(RV) ≈ 2·IQ/n, IQ robusta ≈ TQ
            "RV_ee": math.sqrt(2.0 * e["TQ"] / n) if n > 0 else np.nan,
        })
        if cum is not None:
            filas[-1]["RSkew_des"], filas[-1]["RKurt_des"] = _momentos_desestacionalizados(
                L, int(ses.m_ini[s]), k, cum)
        firma.append({f: rv_submuestreada(L, f) for f in cfg.frecuencias_firma})

    d = pd.DataFrame(filas, index=ses.fechas)
    d.index.name = "sesion"
    d["cierre"] = ses.cierre
    d["cobertura"] = ses.cobertura
    d["completa"] = ses.completa
    d["roll"] = ses.roll
    d["r_noche"] = ses.r_noche
    d["n_cortes"] = ses.n_cortes
    d["volumen"] = np.nansum(ses.vol, axis=1)
    d["salto"] = (d["z_bns"] > crit) & d["completa"]
    d["crit_bns"] = crit
    # Salto "significativo" (Andersen, Bollerslev y Diebold 2007): sólo si pasa el test.
    d["J"] = np.where(d["salto"], np.maximum(d["RV"] - d["BV"], 0.0), 0.0)
    d["C"] = d["RV"] - d["J"]
    d["JumpRatio"] = np.maximum(d["RV"] - d["BV"], 0.0) / d["RV"]
    # [v2] Dirección del salto con la variación de salto FIRMADA de Patton y Sheppard (2015):
    # ΔJ = RS+ − RS−. Tu PosJump resta una bipotencia parcial (sólo los pares con r_t > 0),
    # que no estima nada conocido.
    d["SJ"] = d["RSp"] - d["RSn"]
    d["J_pos"] = np.maximum(d["RSp"] - d["BV"] / 2.0, 0.0)
    d["J_neg"] = np.maximum(d["RSn"] - d["BV"] / 2.0, 0.0)
    d["direccion"] = np.where(d["SJ"] >= 0, "ALZA", "BAJA")
    for c in ("RV", "BV", "MedRV", "TSRV", "RV1", "C", "J"):
        d[f"{c}_anual"] = _anual(np.maximum(d[c], 0.0))
    d["RV_ic_bajo"] = _anual(np.maximum(d["RV"] - 1.96 * d["RV_ee"], 0.0))
    d["RV_ic_alto"] = _anual(d["RV"] + 1.96 * d["RV_ee"])
    d["reportable"] = ((d.index >= pd.Timestamp(cfg.start).normalize())
                       & (d.index < pd.Timestamp(cfg.end)))
    f = pd.DataFrame(firma, index=ses.fechas)
    return d, f


# =============================================================================
# 7. TU SCRIPT, TAL CUAL — para medirlo contra el módulo
# =============================================================================
def script_original(barras: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """
    Réplica fiel de compute_rv_estimators + detect_jumps: retornos sobre TODA la serie, días
    calendario de CDMX, ≥30 barras, BV sin factor de muestra, JumpRatio > 0.3 y z rodante
    de 20 días > 1.5. Se añaden dos columnas que tu script no tiene: qué parte del RV de cada
    "día" viene de retornos que NO son intradía (la pausa, el fin de semana, el roll).
    """
    c = barras["close"].to_numpy(float)
    t = barras.index
    lr = np.full(len(c), np.nan)
    lr[1:] = np.log(c[1:] / c[:-1])
    hueco = np.r_[np.inf, np.diff(t.asi8) / 6e10]
    inst = barras["instrument_id"].to_numpy()
    rolls = np.r_[False, inst[1:] != inst[:-1]]
    fecha = t.tz_convert(cfg.tz_local).tz_localize(None).normalize()
    df = pd.DataFrame({"fecha": fecha, "r": lr, "hueco": hueco, "roll": rolls}).iloc[1:]
    cuenta = df.groupby("fecha").size()
    df = df[df["fecha"].isin(cuenta[cuenta >= 30].index)].copy()
    a = df["r"].abs()
    g = df.groupby("fecha")
    ant, sig = a.groupby(df["fecha"]).shift(1), a.groupby(df["fecha"]).shift(-1)
    df["r2"] = df["r"] ** 2
    df["bp"] = a * ant
    df["med2"] = _mediana3(ant.to_numpy(), a.to_numpy(), sig.to_numpy()) ** 2
    df["no_intradia"] = (df["hueco"] > cfg.hueco_max_min) | df["roll"]
    df["r2_no_intradia"] = np.where(df["no_intradia"], df["r2"], 0.0)
    df["finde"] = df["hueco"] > 600
    g = df.groupby("fecha")
    o = pd.DataFrame({"n": g.size(), "RV": g["r2"].sum(), "bp": g["bp"].sum(),
                      "med2": g["med2"].sum(), "RV_no_intradia": g["r2_no_intradia"].sum(),
                      "con_pausa": g["no_intradia"].any(), "con_roll": g["roll"].any(),
                      "con_finde": g["finde"].any()})
    o["BV"] = (math.pi / 2.0) * o["bp"]
    o["MedRV"] = C_MEDRV * o["n"] / (o["n"] - 2.0) * o["med2"]
    o["JumpRatio"] = np.maximum(o["RV"] - o["BV"], 0.0) / o["RV"]
    m, sd = o["JumpRatio"].rolling(20).mean(), o["JumpRatio"].rolling(20).std()
    o["JumpRatio_Z"] = (o["JumpRatio"] - m) / sd.replace(0, np.nan)
    o["IsJump"] = (o["JumpRatio"] > 0.3) & (o["JumpRatio_Z"] > 1.5)
    o["frac_no_intradia"] = o["RV_no_intradia"] / o["RV"]
    o["domingo"] = o.index.dayofweek == 6
    o["RV_anual"] = _anual(o["RV"])
    return o


# =============================================================================
# 8. PRONÓSTICO HAR — la σ que necesita la ejecución
# =============================================================================
def pronostico_har(diario: pd.DataFrame, cfg: Config) -> dict:
    """
    HAR-RV logarítmico (Corsi 2009) re-estimado cada día con ventana rodante y sólo con el
    pasado:

        log RV_{t+1} = b0 + bd·log RV_t + bw·log RV_t^(5) + bm·log RV_t^(22) + e

    con RV^(h) el promedio de las últimas h sesiones y el pronóstico corregido por sesgo de
    Jensen, exp(ŷ + s²/2). Se evalúa fuera de muestra con QLIKE (Patton 2011), la pérdida
    robusta para comparar pronósticos de varianza con un proxy ruidoso.

    Tu script no pronostica nada: describe el pasado. Para decidir CÓMO ejecutar hoy hace
    falta la σ de HOY, y la mejor estimación de la varianza de mañana no es la de ayer.
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
# 9. PERFIL INTRADÍA Y COEFICIENTES DE IMPACTO
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
# 10. ALMGREN-CHRISS
# =============================================================================
# Venta de X contratos en N tramos de τ minutos. Tenencias x_0 = X, …, x_N = 0; tramo
# n_k = x_{k−1} − x_k. El tramo k se ejecuta al precio del inicio del tramo menos el impacto,
# y la tenencia x_k queda expuesta a la variación del precio durante el tramo k:
#
#   costo  = Σ_k x_k·(−ΔP_k)  +  Σ_k n_k·h_k  +  γ·Σ_k n_k·Σ_{j<k} n_j  +  ε·Σ|n_k|
#   E      = ½γX² − ½γΣn_k² + εX + Σ_k c_k·n_k^(1+β)        (impacto temporal ley de potencia)
#   V      = Σ_k σ_k²·(x_{k−1}² + x_{k−1}·x_k + x_k²)/3      (se vende parejo dentro del tramo)
#
# y se minimiza E + λV. En el modelo DISCRETO del artículo V = Σ_k σ_k²·x_k²: lo que se
# ejecuta dentro de un tramo no carga riesgo, así que con tramos grandes el modelo "vende"
# media hora de flujo al precio del inicio (medido con 5 000 NQ en la sesión regular: E + λV
# caía de 15.0 a 3.9 bps al pasar de tramos de 1 a 30 min). Con la tenencia lineal dentro del
# tramo la varianza es la exacta de ese programa y converge al modelo continuo. El discreto queda para verificar las fórmulas
# cerradas. Con β = 1, σ y η constantes y varianza discreta es exactamente Almgren y Chriss
# (2000) y su solución x_j = X·sinh(κ(T − t_j))/sinh(κT). Lo que se agrega aquí:
# σ_k y el volumen por tramo salen del perfil intradía MEDIDO, y el impacto es cóncavo en la
# participación (β = 0.6, Almgren et al. 2005), que es lo que se observa en los datos.

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


# =============================================================================
# 11. COMPARACIÓN DE ESTRATEGIAS — analítica y contra tus propias sesiones
# =============================================================================
def rendimientos_ventana(ses: Sesiones, cfg: Config, m: Mercado, sigma2_dia: float,
                         rv_sesion: np.ndarray) -> np.ndarray:
    """
    Retornos logarítmicos de 1 minuto de la MISMA ventana horaria en cada sesión histórica
    completa (D × minutos): de 1 minuto para ver el riesgo que hay DENTRO de cada tramo. Con escalar_vol, cada día se reescala a la σ pronosticada (conserva
    la forma intradía y las colas de ese día); con sin_deriva, se quita la media por tramo
    para que la tendencia de la muestra no decida la comparación.
    """
    m0 = int(m.minutos[0])
    tau = int(m.tau)
    pts = m0 - 1 + np.arange(int(m.T) + 1)             # cierre del minuto anterior a cada minuto
    idx = np.flatnonzero(ses.completa)[-cfg.replica_dias:]
    if m0 == 0 or len(idx) == 0:
        return np.empty((0, int(m.T)))
    P = ses.L[idx][:, pts]
    ok = np.all(np.isfinite(P), axis=1)
    R = np.diff(P[ok], axis=1)
    if cfg.escalar_vol:
        rv = rv_sesion[idx][ok]
        R = R * np.sqrt(sigma2_dia / np.where(rv > 0, rv, np.nan))[:, None]
        R = R[np.all(np.isfinite(R), axis=1)]
    if cfg.sin_deriva and len(R):
        R = R - R.mean(axis=0, keepdims=True)
    return R


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


def comparar(m: Mercado, lam: float, z: float, R: np.ndarray, lado: int) -> tuple[pd.DataFrame, dict]:
    x_opt = ac_optima(m, lam)
    trayectorias = {
        "AC óptima (perfil + ley de potencia)": x_opt,
        "AC clásica (σ, η constantes)": ac_clasica(m, lam),
        "VWAP": vwap(m),
        "TWAP": twap(m),
        "Inmediata (bloque)": inmediata(m),
    }
    filas = []
    for nombre, x in trayectorias.items():
        e = evaluar(m, x)
        fila = {"estrategia": nombre, "E": e["E"], "SD": e["SD"], "U": e["E"] + lam * e["V"],
                "E_zSD": e["E"] + z * e["SD"], "temporal": e["temporal"], "fijo": e["fijo"],
                "permanente": e["permanente"], "urg_25": urgencia(x, 0.25),
                "urg_50": urgencia(x, 0.5), "vida_media_min": vida_media(x, m.tau),
                "part_max": float(np.max((x[:-1] - x[1:]) / m.vol))}
        if len(R) >= 20:
            c = costos_replica(m, x, R, lado)
            p95 = float(np.quantile(c, 0.95))
            fila.update({"hist_media": float(np.mean(c)), "hist_sd": float(np.std(c, ddof=1)),
                         "hist_var95": p95, "hist_cvar95": float(np.mean(c[c >= p95])),
                         "hist_n": int(len(c))})
        filas.append(fila)
    df = pd.DataFrame(filas).set_index("estrategia")
    for c in ("E", "SD", "U", "E_zSD", "hist_media", "hist_sd", "hist_var95", "hist_cvar95"):
        if c in df:
            df[c + "_bps"] = df[c] / m.nocional * 1e4
    return df, trayectorias


# =============================================================================
# 12. ANÁLISIS DE SENSIBILIDAD
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
    hs = [h for h in (2, 5, 10, 15, 20, 30, 45, 60, 90, 120, 180, 240, 360)
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


# =============================================================================
# 13. EL CÁLCULO COMPLETO
# =============================================================================
@dataclass
class Resultado:
    cfg: Config
    ses: Sesiones
    diario: pd.DataFrame
    firma: pd.DataFrame
    perfil: pd.DataFrame
    har: dict
    original: pd.DataFrame
    ejec: dict
    sens: dict
    diag: dict
    verdad: dict | None = None


def analizar(barras: pd.DataFrame, cfg: Config, verdad: dict | None = None,
             sensib: bool = True, verboso: bool = True) -> Resultado:
    ses = construir_sesiones(barras, cfg)
    perfil = perfil_intradia(ses, cfg)
    diario, firma = panel_diario(ses, cfg, perfil)
    har = pronostico_har(diario, cfg)
    diario["F_har"] = pd.Series(har["F"], index=har["fechas"]).reindex(diario.index) \
        if len(har["fechas"]) else np.nan
    diario["F_har_anual"] = _anual(diario["F_har"])
    original = script_original(barras, cfg)

    # --- insumos de la ejecución ---
    comp = np.flatnonzero(ses.completa)
    ult = comp[-1] if len(comp) else ses.S - 1
    S0_puntos = float(ses.cierre[ult])
    sigma2 = float(har["F_sig"])
    adv = float(np.mean(diario["volumen"].to_numpy()[comp[-cfg.adv_dias:]])) if len(comp) \
        else float(diario["volumen"].mean())
    m = construir_mercado(cfg, perfil, sigma2, adv, S0_puntos)
    lam, modo = elegir_lambda(m, cfg)
    z = _z(cfg.var_conf)
    lado = 1 if cfg.lado.lower().startswith("v") else -1
    R = rendimientos_ventana(ses, cfg, m, sigma2, diario["RV"].to_numpy())
    tabla, tray = comparar(m, lam, z, R, lado)
    x_opt = tray["AC óptima (perfil + ley de potencia)"]
    ref = lambda_referencia(m)
    fr = frontera(m, ref * np.logspace(-3, 5, 41))
    fr_c = frontera(m, ref * np.logspace(-3, 5, 41), clasica=True)
    e_opt = evaluar(m, x_opt)
    sig_fecha = pd.Timestamp(ses.fechas[ult]) + pd.offsets.BDay(1)
    ejec = {"m": m, "lam": lam, "modo_lambda": modo, "z": z, "lado": lado, "R": R,
            "tabla": tabla, "tray": tray, "frontera": fr, "frontera_clasica": fr_c,
            "S0_puntos": S0_puntos, "sigma2": sigma2, "adv": adv, "fecha": sig_fecha,
            "fecha_datos": ses.fechas[ult], "lam_ref": ref,
            "precio_riesgo": 2.0 * lam * e_opt["SD"],
            "plan": plan(m, x_opt, sig_fecha, cfg)}
    sens = sensibilidad(m, lam, cfg, perfil, sigma2, adv, S0_puntos) if sensib else {}

    diag = {"n_barras": int(len(barras)), "escala": barras.attrs.get("escala", "float"),
            "n_sesiones": ses.S, "n_completas": int(ses.completa.sum()),
            "n_rolls": int(ses.roll.sum()), "n_cortes": int(ses.n_cortes.sum()),
            "n_saltos": int(diario["salto"].sum())}
    if verdad is not None:
        diag["verdad"] = medir_contra_verdad(diario, original, verdad, cfg)
    return Resultado(cfg, ses, diario, firma, perfil, har, original, ejec, sens, diag, verdad)


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


def medir_contra_verdad(diario: pd.DataFrame, original: pd.DataFrame, verdad: dict,
                        cfg: Config) -> dict:
    v = verdad["sesiones"].reindex(diario.index)
    ok = diario["completa"].to_numpy() & v["iv"].notna().to_numpy()
    iv, jv = v["iv"].to_numpy(), v["jv"].to_numpy()
    salto = v["salto"].fillna(False).to_numpy(dtype=bool)
    out = {"precision": {}}
    # --- precisión de los estimadores (en puntos de volatilidad anual) ---
    def err(est, obj, mask):
        a, b = _anual(np.maximum(est[mask], 0)), _anual(obj[mask])
        return float(np.mean(a - b)), float(np.sqrt(np.mean((a - b) ** 2)))
    sin = ok & ~salto
    con = ok & salto
    for nombre, col, objetivo_ in (("RV 1 min", "RV1", "qv"), ("RV 5 min, 1 rejilla", "RV_1rejilla", "qv"),
                                   ("RV 5 min submuestreada", "RV", "qv"), ("TSRV", "TSRV", "qv"),
                                   ("BV", "BV", "iv"), ("MedRV", "MedRV", "iv")):
        est = diario[col].to_numpy(float)
        fila = {}
        fila["sin_salto"] = err(est, iv, sin)
        fila["con_salto_vs_iv"] = err(est, iv, con) if con.any() else (np.nan, np.nan)
        fila["con_salto_vs_qv"] = err(est, iv + jv, con) if con.any() else (np.nan, np.nan)
        out["precision"][nombre] = fila
    # --- detección de saltos: el módulo ---
    det = diario["salto"].to_numpy(dtype=bool) & ok
    tp = int((det & salto).sum())
    out["modulo"] = {"marcadas": int(det.sum()), "verdaderos": int((salto & ok).sum()),
                     "precision": tp / det.sum() if det.sum() else np.nan,
                     "exhaustividad": tp / (salto & ok).sum() if (salto & ok).any() else np.nan,
                     "falsos_sin_salto": float(det[ok & ~salto].mean()) if (ok & ~salto).any() else np.nan}
    # --- detección de saltos: tu script (días calendario CDMX) ---
    fechas_salto = (verdad["saltos_utc"].tz_convert(cfg.tz_local).tz_localize(None).normalize()
                    if len(verdad["saltos_utc"]) else pd.DatetimeIndex([]))
    o = original.dropna(subset=["JumpRatio_Z"])
    marc = o.index[o["IsJump"].to_numpy(dtype=bool)]
    tp_o = int(np.isin(marc, fechas_salto).sum())
    encontrados = int(np.isin(fechas_salto, marc).sum())
    out["original"] = {"marcadas": int(len(marc)), "verdaderos": int(len(fechas_salto)),
                       "precision": tp_o / len(marc) if len(marc) else np.nan,
                       "exhaustividad": encontrados / len(fechas_salto) if len(fechas_salto) else np.nan,
                       "marcadas_con_roll_o_finde": int((o.loc[marc, "con_roll"]
                                                         | o.loc[marc, "con_finde"]).sum())}
    for k in ("modulo", "original"):
        p, r = out[k]["precision"], out[k]["exhaustividad"]
        out[k]["F1"] = 2 * p * r / (p + r) if np.isfinite(p) and np.isfinite(r) and (p + r) > 0 else np.nan
    # --- pronóstico: HAR contra la varianza verdadera del proceso ---
    return out


# =============================================================================
# 14. REPORTES
# =============================================================================
def reporte_datos(res: Resultado) -> None:
    d, cfg, o = res.diag, res.cfg, res.original
    _titulo("1 · DATOS Y SESIONES — la unidad correcta es la sesión de Globex")
    print(f"  Barras de 1 min           : {d['n_barras']:>10,}   (precios: {d['escala']})")
    print(f"  Sesiones                  : {d['n_sesiones']:>10,}   completas: {d['n_completas']:,}")
    print(f"  Rolls del continuo        : {d['n_rolls']:>10,}   (por cambio de instrument_id)")
    print(f"  Cortes dentro de sesión   : {d['n_cortes']:>10,}   (huecos > {cfg.hueco_max_min} min o roll)")
    print()
    print("  TU SCRIPT agrupa por fecha calendario de CDMX. Sobre estos mismos datos:")
    print(f"      'días' que arma                          : {len(o):>6,}")
    print(f"      de ellos, domingos (sesión partida)       : {int(o['domingo'].sum()):>6,}")
    print(f"      con la pausa 16-17 CT o el finde adentro  : {int(o['con_pausa'].sum()):>6,}")
    print(f"      con un roll adentro                       : {int(o['con_roll'].sum()):>6,}")
    fr = o["frac_no_intradia"]
    print(f"      RV que NO es intradía (media / máximo)    : {_pct(fr.mean())} / {_pct(fr.max())}")
    print("  Esa última línea es la fracción del RV de tu script que viene de retornos que no")
    print("  ocurrieron dentro de una sesión: la pausa, el fin de semana, el salto del roll.")


def reporte_estimadores(res: Resultado) -> None:
    dd, cfg = res.diario, res.cfg
    d = dd[dd["reportable"] & dd["completa"]]
    if d.empty:
        d = dd[dd["completa"]]
    _titulo(f"2 · VOLATILIDAD REALIZADA — {len(d)} sesiones de la ventana")
    print(f"  Muestreo {cfg.freq_min} min"
          f"{' submuestreado (promedio de ' + str(cfg.freq_min) + ' rejillas)' if cfg.submuestreo else ''}")
    print(f"  {'estimador':<34s}{'media':>9s}{'mediana':>9s}{'mín':>8s}{'máx':>8s}   (% anual)")
    for nombre, c in (("RV   varianza realizada", "RV_anual"), ("BV   bipotencia (robusta)", "BV_anual"),
                      ("MedRV mediana (muy robusta)", "MedRV_anual"), ("TSRV dos escalas", "TSRV_anual"),
                      ("C    parte continua", "C_anual"), ("RV a 1 min (tu muestreo)", "RV1_anual")):
        x = d[c]
        print(f"  {nombre:<34s}{_fmt(x.mean(), 2, 9)}{_fmt(x.median(), 2, 9)}"
              f"{_fmt(x.min(), 1, 8)}{_fmt(x.max(), 1, 8)}")
    print()
    f = res.firma[dd["completa"].to_numpy()].mean()
    if len(f):
        print("  FIRMA DE VOLATILIDAD (RV media contra frecuencia de muestreo, % anual):")
        print("      " + "  ".join(f"{k:>3d}m {_anual(v):5.2f}" for k, v in f.items()))
        r1 = f.iloc[0] / f.get(5, np.nan) - 1.0 if 5 in f.index else np.nan
        if np.isfinite(r1):
            if abs(r1) < 0.03:
                print(f"  A 1 min el RV difiere {r1:+.1%} del de 5 min: el ruido de microestructura")
                print("  es despreciable en estos datos. 1 min sería viable (--freq 1).")
            else:
                print(f"  A 1 min el RV difiere {r1:+.1%} del de 5 min: hay ruido de microestructura")
                print("  (rebote compra-venta, tick). Por eso el muestreo por omisión es 5 min.")
    print()
    print(f"  {'':<34s}{'bruta':>9s}{'desestacionalizada':>20s}")
    print(f"  {'Asimetría realizada media':<34s}{_fmt(d['RSkew'].mean(), 3)}"
          f"{_fmt(d.get('RSkew_des', pd.Series(dtype=float)).mean(), 3, 20)}")
    print(f"  {'Curtosis realizada mediana':<34s}{_fmt(d['RKurt'].median(), 3)}"
          f"{_fmt(d.get('RKurt_des', pd.Series(dtype=float)).median(), 3, 20)}   (normal = 3)")
    print("  Tu script calcula la curtosis bien y con la referencia correcta (3). Lo que no")
    print("  separa es la ESTACIONALIDAD: con la apertura mucho más volátil que la madrugada,")
    print("  una sesión sin colas gruesas ya da curtosis > 3. La columna desestacionalizada")
    print("  divide cada retorno entre la σ que el perfil intradía le asigna a esa hora.")


def reporte_saltos(res: Resultado) -> None:
    dd, cfg, o = res.diario, res.cfg, res.original
    d = dd[dd["reportable"]]
    if d.empty:
        d = dd
    _titulo("3 · SALTOS — test de Barndorff-Nielsen-Shephard, no umbrales a ojo")
    crit = _z(1 - cfg.alfa_salto)
    n_s = int(d["salto"].sum())
    print(f"  Crítico al {cfg.alfa_salto:.1%} (una cola): z > {crit:.3f}")
    print(f"  Sesiones con salto significativo: {n_s} de {int(d['completa'].sum())}")
    if n_s:
        print(f"  {'sesión':<12s}{'z':>7s}{'salto/RV':>10s}{'dirección':>11s}{'vol del salto':>15s}")
        for t, x in d[d["salto"]].sort_values("z_bns", ascending=False).head(12).iterrows():
            print(f"  {t:%Y-%m-%d}  {x['z_bns']:7.2f}{_pct(x['J'] / x['RV'], 1, 9)}"
                  f"{x['direccion']:>11s}{_fmt(x['J_anual'], 2, 13)}%")
    print()
    oo = o[(o.index >= pd.Timestamp(cfg.start)) & (o.index < pd.Timestamp(cfg.end))]
    if oo.empty:
        oo = o
    print(f"  Tu script (JumpRatio > 0.3 y z rodante > 1.5) marca {int(oo['IsJump'].sum())} 'días'.")
    malos = int((oo["IsJump"] & (oo["con_roll"] | oo["con_finde"])).sum())
    if malos:
        print(f"  {malos} de ellos contienen un roll o el hueco del fin de semana: no son saltos del")
        print("  mercado, son artefactos de juntar sesiones.")


def reporte_verdad(res: Resultado) -> None:
    v = res.diag.get("verdad")
    if not v:
        return
    _titulo("4 · CONTRA LA VERDAD (sólo posible en simulación)")
    print("  Error en puntos de volatilidad ANUAL (sesgo / RMSE) contra la verdad del proceso:")
    print(f"  {'estimador':<26s}{'sin salto':>18s}{'con salto vs IV':>20s}{'con salto vs QV':>20s}")
    for nombre, f in v["precision"].items():
        c = lambda t: f"{t[0]:+6.2f} / {t[1]:5.2f}" if np.isfinite(t[0]) else "—"
        print(f"  {nombre:<26s}{c(f['sin_salto']):>18s}{c(f['con_salto_vs_iv']):>20s}"
              f"{c(f['con_salto_vs_qv']):>20s}")
    print("  (IV = varianza integrada sin saltos; QV = IV + saltos. RV estima QV; BV y MedRV, IV.)")
    print()
    print(f"  {'detector de saltos':<40s}{'marcadas':>9s}{'precisión':>11s}{'exhaustiv.':>12s}{'F1':>7s}")
    for nombre, k in (("módulo · BNS por sesión", "modulo"), ("tu script · días CDMX", "original")):
        x = v[k]
        print(f"  {nombre:<40s}{x['marcadas']:>9d}{_fmt(x['precision'], 3, 11)}"
              f"{_fmt(x['exhaustividad'], 3, 12)}{_fmt(x['F1'], 3, 7)}")
    print(f"  Falsos positivos del test en sesiones SIN salto: {_pct(v['modulo']['falsos_sin_salto'], 2)}"
          f"  (nivel nominal {res.cfg.alfa_salto:.1%})")
    if v["original"]["marcadas_con_roll_o_finde"]:
        print(f"  De las marcas de tu script, {v['original']['marcadas_con_roll_o_finde']} caen en "
              "días con roll o fin de semana.")


def reporte_har(res: Resultado) -> None:
    h, cfg = res.har, res.cfg
    _titulo("5 · PRONÓSTICO HAR — la σ de la próxima sesión")
    if not h["ok"]:
        print(f"  ⚠ {h.get('motivo', 'sin HAR')}")
        print(f"  Varianza usada: {_anual(h['F_sig']):.2f} % anual")
        return
    b = h["coef"]
    print(f"  log RV(t+1) = {b[0]:+.3f} {b[1]:+.3f}·log RV(t) {b[2]:+.3f}·log RV5(t) "
          f"{b[3]:+.3f}·log RV22(t)")
    print(f"  Evaluado fuera de muestra en {h['n_eval']} sesiones (re-estimado cada día):")
    print(f"      {'pronóstico':<22s}{'QLIKE':>10s}{'MSE (×1e9)':>13s}{'t DM vs HAR':>13s}")
    for k in h["qlike"]:
        t = h["dm_t"].get(k, np.nan)
        print(f"      {k:<22s}{h['qlike'][k]:10.4f}{h['mse'][k] * 1e9:13.4f}"
              f"{'' if k == 'HAR' else f'{t:13.2f}'}")
    print("  t DM > 2: el HAR es significativamente mejor que esa alternativa (Newey-West, 5 rezagos).")
    lo, hi = h["ic_sig"]
    print()
    print(f"  PRÓXIMA SESIÓN: {_anual(h['F_sig']):.2f} % anual   IC 95 %: "
          f"{_anual(lo):.1f} – {_anual(hi):.1f} %")
    print(f"  Percentil contra el último año: {h['percentil']:.0%}"
          f"{'  ⚠ RÉGIMEN DE VOLATILIDAD ALTA' if h['percentil'] >= cfg.telegram_percentil_alerta else ''}")


def reporte_impacto(res: Resultado) -> None:
    e, cfg = res.ejec, res.cfg
    m = e["m"]
    mult, tick = multiplicador(cfg), tamano_tick(cfg)
    _titulo("6 · COEFICIENTES DE IMPACTO")
    print(f"  Precio de llegada        : {e['S0_puntos']:,.2f} pts  ·  {m.S0:,.0f} USD por contrato")
    print(f"  Bloque                   : {m.X:,.0f} contratos ({cfg.lado}) · nocional "
          f"{m.nocional / 1e6:,.1f} M USD")
    print(f"  Volumen diario (ADV)     : {e['adv']:,.0f} contratos  → el bloque es "
          f"{m.X / e['adv']:.3%} del ADV")
    print(f"  σ pronosticada (sesión)  : {m.sigma_dia:.3%}  ({_anual(e['sigma2']):.1f} % anual)")
    print()
    print(f"  ε  costo fijo            : {m.eps:,.2f} USD/contrato = medio spread "
          f"({cfg.spread_ticks:g} tick) + comisión {cfg.comision_usd:,.2f}")
    print("     (supuesto, no estimación: el spread de NQ es ~1/10 de la σ de un minuto y no se")
    print("      puede recuperar de OHLC de 1 min — medido, Corwin-Schultz da 8-17 ticks cuando")
    print("      el verdadero es 1. Para medirlo hace falta el esquema mbp-1 con bid y ask.)")
    print(f"  η₀ impacto temporal      : {m.eta0:.3f} · σ · (participación)^{m.beta:g}   "
          "(Almgren et al. 2005)")
    print(f"  γ  impacto permanente    : {m.gamma:.3e} USD por contrato² = {cfg.gamma0:g}·σ·S/ADV")
    print(f"  η  lineal equivalente    : {m.eta_lineal():.4f} USD/(contrato/min)  ← lo que usaría la AC clásica")
    print()
    print("  Impacto temporal por contrato según la participación en el volumen:")
    print(f"      {'participación':>14s}{'bps':>8s}{'USD/contrato':>14s}{'ticks':>8s}")
    for p in (0.005, 0.01, 0.02, 0.05, 0.10, 0.20, 0.50):
        h = m.eta0 * m.sigma_dia * p ** m.beta
        print(f"      {p:>13.1%}{h * 1e4:8.2f}{h * m.S0:14.2f}{h * e['S0_puntos'] / tick:8.2f}")
    print()
    print("  De dónde sale cada número y cuánto creerle:")
    print("   · σ y el volumen por minuto se MIDEN en tus datos (HAR + perfil intradía).")
    print("   · η₀, β y γ₀ son los de Almgren, Thum, Hauptmann y Li (2005), ajustados sobre")
    print("     órdenes reales de acciones de EE. UU. El impacto causal NO se puede medir con")
    print("     OHLCV: haría falta tu propio historial de ejecuciones. Por eso la sección de")
    print("     sensibilidad mide cuánto cambia la decisión si η₀ o β están mal por 2×.")


def reporte_ejecucion(res: Resultado) -> None:
    e, cfg = res.ejec, res.cfg
    m, lam, tab = e["m"], e["lam"], e["tabla"]
    x_opt = e["tray"]["AC óptima (perfil + ley de potencia)"]
    ct0, mx0 = reloj(e["fecha"], int(m.minutos[0]), cfg)
    _titulo("7 · AVERSIÓN AL RIESGO Y ESTRATEGIA ÓPTIMA")
    print(f"  Sesión objetivo: {e['fecha']:%Y-%m-%d} · inicio {ct0:%H:%M} CT = {mx0:%H:%M} CDMX · "
          f"{m.T:.0f} min en {m.N} tramos de {m.tau:.0f} min")
    if np.isfinite(m.part_max):
        subido = m.part_max > cfg.part_max + 1e-9
        print(f"  Tope de participación: {m.part_max:.1%} del volumen de cada tramo"
              f"{'  ⚠ subido: con ' + format(cfg.part_max, '.0%') + ' no se termina en el horizonte' if subido else ''}")
    print(f"  λ = {lam:.3e} 1/USD   ({e['modo_lambda']})")
    if "ESQUINA" in e["modo_lambda"]:
        print("      Con este bloque, E + z·SD baja todo el camino hasta la ejecución más rápida:")
        print("      el riesgo de esperar pesa más que el impacto de ir rápido, y lo que frena es")
        print("      el tope de participación. Para una ejecución más paciente: --var-conf 0.75,")
        print("      --vida-media 15, o --lambda con un valor menor.")
    print(f"      λ de referencia (AC clásica con urgencia κT = 1): {e['lam_ref']:.3e}")
    print(f"      vida media de la ejecución : {vida_media(x_opt, m.tau):.1f} min")
    print(f"      ejecutado en el 1er cuarto : {urgencia(x_opt, 0.25):.1%}   a la mitad: "
          f"{urgencia(x_opt, 0.5):.1%}")
    print(f"      precio del riesgo          : con este λ pagas hasta "
          f"{e['precio_riesgo']:.2f} USD de costo esperado")
    print("                                   por cada USD de desviación estándar que quitas.")
    print()
    _titulo("8 · COMPARACIÓN DE ESTRATEGIAS")
    z = e["z"]
    print(f"  Costo = implementation shortfall contra el precio de llegada. USD y bps del nocional.")
    print(f"  {'estrategia':<38s}{'E[costo]':>11s}{'SD':>11s}{'E+zSD':>11s}{'E bps':>8s}"
          f"{'E+zSD bps':>10s}{'part.máx':>9s}")
    for nombre, x in tab.iterrows():
        print(f"  {nombre:<38s}{_usd(x['E'], 11)}{_usd(x['SD'], 11)}{_usd(x['E_zSD'], 11)}"
              f"{x['E_bps']:8.2f}{x['E_zSD_bps']:10.2f}{x['part_max']:9.1%}")
    print(f"  (z = {z:.3f}: E + z·SD es el costo que no se excede con {res.cfg.var_conf:.0%} de "
          "confianza bajo normalidad)")
    if "hist_media" in tab:
        print()
        n = int(tab["hist_n"].iloc[0])
        print(f"  RÉPLICA SOBRE TUS SESIONES ({n} días, misma ventana horaria"
              f"{', vol reescalada a la pronosticada' if cfg.escalar_vol else ''}"
              f"{', sin deriva' if cfg.sin_deriva else ''}):")
        print(f"  {'estrategia':<38s}{'media bps':>10s}{'SD bps':>9s}{'VaR95 bps':>11s}{'CVaR95 bps':>12s}")
        for nombre, x in tab.iterrows():
            print(f"  {nombre:<38s}{x['hist_media_bps']:10.2f}{x['hist_sd_bps']:9.2f}"
                  f"{x['hist_var95_bps']:11.2f}{x['hist_cvar95_bps']:12.2f}")
        print("  El VaR/CVaR histórico incluye las colas reales (datos de las 07:30, aperturas")
        print("  movidas) que la normalidad del modelo no ve.")
    print()
    opt = tab.iloc[0]
    print(f"  Costo al {res.cfg.var_conf:.0%} de confianza (E + z·SD) de la AC óptima contra:")
    for nombre in ("AC clásica (σ, η constantes)", "VWAP", "TWAP", "Inmediata (bloque)"):
        if nombre in tab.index:
            d = tab.loc[nombre, "E_zSD"] - opt["E_zSD"]
            print(f"      {nombre:<32s}: {'ahorra' if d >= 0 else 'cuesta'} {_usd(abs(d), 0)} USD "
                  f"({abs(d) / m.nocional * 1e4:.2f} bps)")
    print()
    print("  PLAN RECOMENDADO (contratos enteros):")
    print(f"      {'CT':>6s}{'CDMX':>7s}{'contratos':>11s}{'acumulado':>11s}{'participación':>15s}")
    pl = e["plan"]
    ult = int(np.argmax(pl["acumulado_pct"].to_numpy() >= 100.0 - 1e-9)) if len(pl) else 0
    for _, f in pl.iloc[:ult + 1].iterrows():
        print(f"      {f['hora_ct']:>6s}{f['hora_cdmx']:>7s}{f['contratos']:>11,d}"
              f"{f['acumulado_pct']:>10.1f}%{f['participacion_pct']:>14.2f}%")
    if ult + 1 < len(pl):
        print(f"      (bloque completo a las {pl['hora_ct'].iloc[min(ult + 1, len(pl) - 1)]} CT; "
              "el resto del horizonte queda libre)")


def reporte_sensibilidad(res: Resultado) -> None:
    s = res.sens
    if not s:
        return
    _titulo("9 · SENSIBILIDAD — qué parámetro mueve la decisión")
    t = s["tornado"].sort_values("rango_bps", ascending=False)
    print(f"  E + λV óptimo (bps) re-optimizando, y arrepentimiento de ejecutar el plan BASE si")
    print(f"  el parámetro verdadero fuera otro. Base: {t['U_base_bps'].iloc[0]:.2f} bps.")
    print(f"  {'parámetro':<24s}{'bajo':>8s}{'U bajo':>9s}{'alto':>7s}{'U alto':>9s}"
          f"{'arrep. bajo':>13s}{'arrep. alto':>13s}")
    for p, x in t.iterrows():
        print(f"  {p:<24s}{x['etiqueta_bajo']:>8s}{x['U_bajo_bps']:9.2f}{x['etiqueta_alto']:>7s}"
              f"{x['U_alto_bps']:9.2f}{x['arrep_bajo_bps']:13.3f}{x['arrep_alto_bps']:13.3f}")
    print("  Un arrepentimiento chico con un rango grande significa: el costo cambia mucho, pero")
    print("  el plan base sigue siendo casi el óptimo. Eso es lo que hace robusta una decisión.")
    h = s["horizonte"]
    if len(h) > 2:
        u = h["U_bps"]
        mejora = u.iloc[0] - u.min()
        umbral = u.min() + 0.1 * mejora
        suf = int(u.index[np.argmax(u.to_numpy() <= umbral)])
        print()
        print(f"  HORIZONTE: con este λ, {suf} min capturan el 90 % del beneficio de alargar la")
        print(f"  ejecución (E + λV pasa de {u.iloc[0]:.2f} bps a {u.min():.2f} bps). Más allá de eso")
        print("  la trayectoria óptima ya no usa el tiempo extra.")


# =============================================================================
# 15. TABLEROS
# =============================================================================
C = {"fondo": "#fcfcfb", "tinta": "#0b0b0b", "tinta2": "#52514e", "tenue": "#898781",
     "grid": "#e1e0d9", "eje": "#c3c2b7", "neutro": "#d6d5ce",
     "s1": "#2a78d6", "s2": "#eb6834", "s3": "#1baf7a", "s4": "#eda100", "s5": "#e87ba4",
     "s6": "#008300", "s7": "#4a3aa7", "s8": "#e34948",
     "alza": "#256abf", "baja": "#e34948"}
RAMPA_AZUL = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5",
              "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]
ESTILO_ESTRATEGIA = {
    "AC óptima (perfil + ley de potencia)": (C["s1"], "-", "o"),
    "AC clásica (σ, η constantes)": (C["s4"], "--", "s"),
    "VWAP": (C["s3"], "-.", "^"),
    "TWAP": (C["s2"], ":", "D"),
    "Inmediata (bloque)": (C["s5"], "-", "v"),
}
CORTO = {"AC óptima (perfil + ley de potencia)": "AC óptima", "AC clásica (σ, η constantes)":
         "AC clásica", "VWAP": "VWAP", "TWAP": "TWAP", "Inmediata (bloque)": "Inmediata"}


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


def tablero_volatilidad(res: Resultado, plt, ruta: Path):
    cfg, dd = res.cfg, res.diario
    d = dd[dd["reportable"]]
    if len(d) < 10:
        d = dd
    d = d[d["n"] > 0]
    t = d.index
    span = max(1.0, (t[-1] - t[0]).days)
    fig = plt.figure(figsize=(16, 16.5))
    fig.patch.set_facecolor(C["fondo"])
    gs = fig.add_gridspec(5, 2, height_ratios=[1.5, 1.35, 1.0, 0.95, 1.05], hspace=0.36, wspace=0.14,
                          bottom=0.05, top=0.98)
    ax1 = fig.add_subplot(gs[0, :])
    ax2 = fig.add_subplot(gs[1, :], sharex=ax1)
    ax3 = fig.add_subplot(gs[2, :], sharex=ax1)
    ax4 = fig.add_subplot(gs[3, 0], sharex=ax1)
    ax5 = fig.add_subplot(gs[3, 1], sharex=ax1)
    ax6 = fig.add_subplot(gs[4, 0])
    ax7 = fig.add_subplot(gs[4, 1])
    ancho = 0.8 if span < 200 else 1.0

    # --- 1 precio y saltos ---
    _estilo(ax1, f"{cfg.symbol} · cierre de cada sesión de Globex y saltos significativos "
                 f"(BNS, α = {cfg.alfa_salto:.1%})")
    ax1.plot(t, d["cierre"], color=C["tinta"], linewidth=1.3, label="Cierre de sesión")
    for dirn, color, marca in (("ALZA", C["alza"], "^"), ("BAJA", C["baja"], "v")):
        mk = d["salto"] & (d["direccion"] == dirn)
        if mk.any():
            ax1.scatter(t[mk], d.loc[mk, "cierre"], s=70, marker=marca, color=color, zorder=5,
                        edgecolors=C["fondo"], linewidths=1.5,
                        label=f"Salto a la {dirn.lower()} ({int(mk.sum())})")
    rolls = d["roll"].to_numpy(dtype=bool)
    for tr in t[rolls]:
        ax1.axvline(tr, color=C["eje"], linewidth=1.0)
    if rolls.any():
        ax1.plot([], [], color=C["eje"], linewidth=1.0, label="Roll del continuo")
    top = d[d["salto"]].nlargest(cfg.carteles, "z_bns")
    for k, (ti, x) in enumerate(top.iterrows()):
        arriba = x["direccion"] == "ALZA"
        ax1.annotate(f"{ti:%d-%b}\nz={x['z_bns']:.1f}", xy=(ti, x["cierre"]),
                     xytext=(0, (26 + 14 * (k % 2)) * (1 if arriba else -1)),
                     textcoords="offset points", ha="center", va="bottom" if arriba else "top",
                     fontsize=7, color=C["tinta2"],
                     arrowprops=dict(arrowstyle="-", color=C["eje"], linewidth=0.8))
    ax1.margins(y=0.18)
    ax1.set_ylabel("Precio", color=C["tinta2"], fontsize=9)
    _leyenda(ax1, ncol=5)

    # --- 2 estimadores + HAR ---
    _estilo(ax2, "Volatilidad realizada anualizada: RV con IC 95 %, estimadores robustos y "
                 "pronóstico HAR")
    ax2.fill_between(t, d["RV_ic_bajo"], d["RV_ic_alto"], color=C["s1"], alpha=0.12,
                     linewidth=0, label="IC 95 % de la varianza integrada")
    ax2.plot(t, d["RV_anual"], color=C["s1"], linewidth=1.8, label=f"RV {cfg.freq_min} min")
    ax2.plot(t, d["BV_anual"], color=C["s2"], linewidth=1.3, label="BV bipotencia")
    ax2.plot(t, d["MedRV_anual"], color=C["s3"], linewidth=1.3, label="MedRV")
    if d["F_har_anual"].notna().any():
        ax2.plot(t, d["F_har_anual"], color=C["s7"], linewidth=1.3, drawstyle="steps-mid",
                 label="Pronóstico HAR (del día anterior)")
    h = res.har
    if np.isfinite(h.get("F_sig", np.nan)):
        tf = res.ejec["fecha"]
        y = float(_anual(h["F_sig"]))
        if h.get("ok"):
            lo, hi = (float(_anual(v)) for v in h["ic_sig"])
            ax2.errorbar([tf], [y], yerr=[[y - lo], [hi - y]], fmt="o", color=C["s7"],
                         markersize=7, capsize=4, linewidth=1.3,
                         markeredgecolor=C["fondo"], markeredgewidth=1.5)
        ax2.annotate(f"próxima sesión\n{y:.1f} %", xy=(tf, y), xytext=(8, 0),
                     textcoords="offset points", fontsize=7.5, color=C["tinta"], va="center")
    ax2.set_ylabel("% anual", color=C["tinta2"], fontsize=9)
    _leyenda(ax2, ncol=3)

    # --- 3 estadístico BNS ---
    _estilo(ax3, "Estadístico z de Barndorff-Nielsen-Shephard por sesión (una cola)")
    col = np.where(~d["salto"], C["neutro"], np.where(d["direccion"] == "ALZA", C["alza"], C["baja"]))
    ax3.bar(t, d["z_bns"], color=col, width=ancho)
    crit = _z(1 - cfg.alfa_salto)
    ax3.axhline(crit, color=C["tinta"], linewidth=1.0)
    ax3.axhline(0, color=C["eje"], linewidth=0.8)
    ax3.annotate(f"crítico {crit:.2f}", xy=(t[0], crit), xytext=(2, 3), textcoords="offset points",
                 fontsize=7.5, color=C["tinta2"])
    ax3.set_ylabel("z", color=C["tinta2"], fontsize=9)

    # --- 4 asimetría ---
    _estilo(ax4, "Asimetría realizada")
    ax4.bar(t, d["RSkew"], width=ancho, color=np.where(d["RSkew"] >= 0, C["alza"], C["baja"]))
    ax4.axhline(0, color=C["eje"], linewidth=0.8)

    # --- 5 curtosis ---
    _estilo(ax5, "Curtosis realizada, escala log (normal = 3)")
    ax5.plot(t, d["RKurt"], color=C["s2"], linewidth=1.1, label="bruta")
    if "RKurt_des" in d:
        ax5.plot(t, d["RKurt_des"], color=C["s1"], linewidth=1.5, label="desestacionalizada")
    ax5.axhline(3.0, color=C["tinta2"], linewidth=1.0)
    ax5.set_yscale("log")
    from matplotlib.ticker import FixedLocator, NullFormatter, ScalarFormatter
    ax5.yaxis.set_major_locator(FixedLocator([2, 3, 5, 10, 20, 50, 100, 200]))
    ax5.yaxis.set_major_formatter(ScalarFormatter())
    ax5.yaxis.set_minor_formatter(NullFormatter())
    ax5.annotate("normal = 3", xy=(t[-1], 3.0), xytext=(-2, -10), textcoords="offset points",
                 fontsize=7.5, color=C["tinta2"], ha="right")
    _leyenda(ax5, ncol=2)
    for ax in (ax1, ax2, ax3, ax4, ax5):
        _eje_fechas(ax, span)
    for ax in (ax1, ax2):
        ax.tick_params(labelbottom=False)

    # --- 6 firma ---
    _estilo(ax6, "Firma de volatilidad: RV medio contra frecuencia de muestreo")
    f = res.firma[res.diario["completa"].to_numpy()].mean()
    if len(f):
        ax6.plot(f.index, _anual(f.to_numpy()), color=C["s1"], linewidth=2, marker="o",
                 markersize=6, markeredgecolor=C["fondo"], markeredgewidth=1.5)
        if cfg.freq_min in f.index:
            y = float(_anual(f[cfg.freq_min]))
            ax6.scatter([cfg.freq_min], [y], s=160, facecolors="none", edgecolors=C["tinta"],
                        linewidths=1.2, zorder=6)
            ax6.annotate(f"muestreo elegido ({cfg.freq_min} min)", xy=(cfg.freq_min, y),
                         xytext=(10, 10), textcoords="offset points", fontsize=7.5, color=C["tinta2"])
        ax6.set_xscale("log")
        ax6.set_xticks(list(f.index))
        ax6.set_xticklabels([str(v) for v in f.index])
        yy = _anual(f.to_numpy())
        centro, medio = float(np.mean(yy)), max(0.06 * float(np.mean(yy)), 0.6 * float(np.ptp(yy)))
        ax6.set_ylim(centro - medio, centro + medio)
    ax6.set_xlabel("minutos entre observaciones", color=C["tinta2"], fontsize=9)
    ax6.set_ylabel("% anual", color=C["tinta2"], fontsize=9)

    # --- 7 perfil intradía ---
    _estilo(ax7, "Perfil intradía (índice, media de la sesión = 1) y ventana de ejecución")
    p = res.perfil.iloc[:MINUTOS_SESION]
    mins = np.arange(MINUTOS_SESION)
    ax7.plot(mins, p["var"] * MINUTOS_SESION, color=C["s1"], linewidth=1.2, label="Varianza")
    ax7.plot(mins, p["vol"] * MINUTOS_SESION, color=C["s2"], linewidth=1.2, label="Volumen")
    m = res.ejec["m"]
    ax7.axvspan(m.minutos[0], m.minutos[-1] + m.tau, color=C["neutro"], alpha=0.5, linewidth=0,
                label="Ventana de ejecución")
    ax7.set_xlim(0, MINUTOS_SESION)
    ax7.set_xticks(np.arange(0, MINUTOS_SESION + 1, 180))
    ax7.set_xticklabels([reloj(res.ejec["fecha"], int(v), cfg)[0].strftime("%H:%M")
                         for v in np.arange(0, MINUTOS_SESION + 1, 180)])
    ax7.set_xlabel("hora de Chicago (CT)", color=C["tinta2"], fontsize=9)
    _leyenda(ax7, ncol=3)

    fig.text(0.008, 0.02, f"{IDENTIFICADOR} · {len(d)} sesiones · muestreo {cfg.freq_min} min"
             f"{' submuestreado' if cfg.submuestreo else ''} · fechas de sesión de Globex",
             color=C["tenue"], fontsize=7.5)
    fig.savefig(ruta, dpi=130, facecolor=C["fondo"], bbox_inches="tight")
    return fig


def tablero_ejecucion(res: Resultado, plt, ruta: Path):
    cfg, e = res.cfg, res.ejec
    m, tab, tray = e["m"], e["tabla"], e["tray"]
    bps = 1e4 / m.nocional
    fig, axes = plt.subplots(2, 3, figsize=(18, 10.5))
    fig.patch.set_facecolor(C["fondo"])
    (a1, a2, a3), (a4, a5, a6) = axes
    ct0, mx0 = reloj(e["fecha"], int(m.minutos[0]), cfg)
    fig.suptitle(f"{cfg.symbol} · {cfg.lado} de {m.X:,.0f} contratos · {m.T:.0f} min desde "
                 f"{ct0:%H:%M} CT ({mx0:%H:%M} CDMX) · σ {_anual(e['sigma2']):.1f} % · "
                 f"λ = {e['lam']:.2e} 1/USD", x=0.01, ha="left", color=C["tinta"], fontsize=12)

    # --- 1 frontera eficiente ---
    _estilo(a1, "Frontera eficiente: costo esperado contra riesgo (bps)")
    fr, frc = e["frontera"], e["frontera_clasica"]
    a1.plot(fr["SD"] * bps, fr["E"] * bps, color=C["s1"], linewidth=2, label="AC óptima (λ variable)")
    a1.plot(frc["SD"] * bps, frc["E"] * bps, color=C["s4"], linewidth=1.5, linestyle="--",
            label="AC clásica evaluada con el modelo completo")
    for nombre, x in tab.iterrows():
        color, _, marca = ESTILO_ESTRATEGIA[nombre]
        a1.scatter(x["SD_bps"], x["E_bps"], s=70, marker=marca, color=color, zorder=5,
                   edgecolors=C["fondo"], linewidths=1.5)
        a1.annotate(CORTO[nombre], xy=(x["SD_bps"], x["E_bps"]), xytext=(6, 4),
                    textcoords="offset points", fontsize=7.5, color=C["tinta"])
    a1.set_xlabel("desviación estándar del costo (bps)", color=C["tinta2"], fontsize=9)
    a1.set_ylabel("costo esperado (bps)", color=C["tinta2"], fontsize=9)
    _leyenda(a1, loc="upper right")

    # --- 2 trayectorias ---
    _estilo(a2, "Inventario pendiente")
    mins = np.r_[m.minutos, m.minutos[-1] + m.tau]
    for nombre, x in tray.items():
        color, ls, _ = ESTILO_ESTRATEGIA[nombre]
        a2.plot(mins, 100 * x / m.X, color=color, linestyle=ls, linewidth=1.8, label=CORTO[nombre])
    a2.set_ylabel("% del bloque", color=C["tinta2"], fontsize=9)
    _eje_reloj(a2, mins, cfg, e["fecha"])
    a2.set_xlabel("hora CT", color=C["tinta2"], fontsize=9)
    _leyenda(a2, loc="upper right")

    # --- 3 programa ---
    _estilo(a3, "Contratos por tramo")
    x_opt = tray["AC óptima (perfil + ley de potencia)"]
    a3.bar(m.minutos + m.tau / 2, x_opt[:-1] - x_opt[1:], width=m.tau * 0.8, color=C["s1"],
           label="AC óptima")
    for nombre in ("VWAP", "TWAP"):
        color, ls, _ = ESTILO_ESTRATEGIA[nombre]
        x = tray[nombre]
        a3.step(m.minutos + m.tau / 2, x[:-1] - x[1:], where="mid", color=color, linestyle=ls,
                linewidth=1.6, label=nombre)
    _eje_reloj(a3, mins, cfg, e["fecha"])
    a3.set_xlabel("hora CT", color=C["tinta2"], fontsize=9)
    a3.set_ylabel("contratos", color=C["tinta2"], fontsize=9)
    _leyenda(a3, loc="upper right")

    # --- 4 participación ---
    _estilo(a4, "Participación en el volumen esperado del mercado")
    for nombre in ("AC óptima (perfil + ley de potencia)", "VWAP", "TWAP"):
        color, ls, _ = ESTILO_ESTRATEGIA[nombre]
        x = tray[nombre]
        a4.plot(m.minutos + m.tau / 2, 100 * (x[:-1] - x[1:]) / m.vol, color=color, linestyle=ls,
                linewidth=1.8, label=CORTO[nombre])
    _eje_reloj(a4, mins, cfg, e["fecha"])
    a4.set_xlabel("hora CT", color=C["tinta2"], fontsize=9)
    a4.set_ylabel("% del volumen del tramo", color=C["tinta2"], fontsize=9)
    _leyenda(a4, loc="upper right")

    # --- 5 comparación ---
    _estilo(a5, f"Costo esperado y costo al {cfg.var_conf:.0%} (E + z·SD), bps")
    nombres = list(tab.index)
    y = np.arange(len(nombres))
    a5.barh(y + 0.19, tab["E_bps"], height=0.36, color=C["s1"], label="E[costo]")
    a5.barh(y - 0.19, tab["E_zSD_bps"], height=0.36, color=C["s2"], label="E + z·SD")
    for yi, (v1, v2) in enumerate(zip(tab["E_bps"], tab["E_zSD_bps"])):
        a5.annotate(f"{v1:.2f}", xy=(v1, yi + 0.19), xytext=(3, 0), textcoords="offset points",
                    va="center", fontsize=7, color=C["tinta2"])
        a5.annotate(f"{v2:.2f}", xy=(v2, yi - 0.19), xytext=(3, 0), textcoords="offset points",
                    va="center", fontsize=7, color=C["tinta2"])
    a5.set_yticks(y)
    a5.set_yticklabels([CORTO[n] for n in nombres])
    a5.invert_yaxis()
    a5.set_xlabel("bps del nocional", color=C["tinta2"], fontsize=9)
    a5.margins(x=0.15)
    _leyenda(a5, loc="lower right")

    # --- 6 réplica histórica ---
    R = e["R"]
    if len(R) >= 20:
        _estilo(a6, f"Réplica sobre {len(R)} sesiones del histórico: distribución del costo (bps)")
        datos = [costos_replica(m, tray[n], R, e["lado"]) * bps for n in nombres]
        caja_kw = dict(whis=(5, 95), widths=0.55, patch_artist=True, showfliers=False,
                       medianprops=dict(color=C["tinta"], linewidth=1.2))
        try:
            bp = a6.boxplot(datos, orientation="horizontal", **caja_kw)
        except TypeError:                                   # matplotlib < 3.10
            bp = a6.boxplot(datos, vert=False, **caja_kw)
        for caja, n in zip(bp["boxes"], nombres):
            caja.set_facecolor(ESTILO_ESTRATEGIA[n][0])
            caja.set_alpha(0.35)
            caja.set_edgecolor(ESTILO_ESTRATEGIA[n][0])
        for i, dts in enumerate(datos, start=1):
            a6.scatter([np.mean(dts)], [i], marker="D", s=26, color=C["tinta"], zorder=5)
        a6.set_yticks(np.arange(1, len(nombres) + 1))
        a6.set_yticklabels([CORTO[n] for n in nombres])
        a6.invert_yaxis()
        a6.set_xlabel("bps · caja = cuartiles · bigotes = percentiles 5-95 · rombo = media",
                      color=C["tinta2"], fontsize=8.5)
    else:
        _estilo(a6, "Réplica histórica")
        a6.text(0.5, 0.5, "No hay sesiones suficientes con esa ventana horaria",
                ha="center", va="center", transform=a6.transAxes, color=C["tinta2"])
    fig.text(0.008, 0.004, f"{IDENTIFICADOR} · impacto temporal η₀ = {m.eta0:g}, β = {m.beta:g} · "
             f"permanente γ₀ = {cfg.gamma0:g} · spread {cfg.spread_ticks:g} tick + comisión "
             f"{cfg.comision_usd:g} USD", color=C["tenue"], fontsize=7.5)
    fig.tight_layout(rect=(0, 0.015, 1, 0.965))
    fig.savefig(ruta, dpi=130, facecolor=C["fondo"], bbox_inches="tight")
    return fig


def tablero_sensibilidad(res: Resultado, plt, ruta: Path):
    from matplotlib.colors import LinearSegmentedColormap
    cfg, e, s = res.cfg, res.ejec, res.sens
    m, lam = e["m"], e["lam"]
    cmap = LinearSegmentedColormap.from_list("azul", RAMPA_AZUL)
    fig, axes = plt.subplots(2, 3, figsize=(18, 10.5))
    fig.patch.set_facecolor(C["fondo"])
    (a1, a2, a3), (a4, a5, a6) = axes
    fig.suptitle(f"{cfg.symbol} · análisis de sensibilidad de la ejecución óptima",
                 x=0.01, ha="left", color=C["tinta"], fontsize=12)

    def mapa(ax, valores, titulo, xlab, ylab, xt, yt, etiqueta, base_xy, texto_base):
        _estilo(ax, titulo)
        ax.grid(False)
        im = ax.imshow(valores, cmap=cmap, aspect="auto", origin="lower")
        ax.set_xticks(np.arange(valores.shape[1]))
        ax.set_xticklabels(xt, rotation=0)
        ax.set_yticks(np.arange(valores.shape[0]))
        ax.set_yticklabels(yt)
        ax.set_xlabel(xlab, color=C["tinta2"], fontsize=9)
        ax.set_ylabel(ylab, color=C["tinta2"], fontsize=9)
        bx, by = base_xy
        ax.scatter([bx], [by], s=220, facecolors="none", edgecolors=C["tinta"], linewidths=1.5)
        ax.annotate(texto_base, xy=(bx, by), xytext=(12, 10), textcoords="offset points",
                    fontsize=8, color=C["tinta"],
                    bbox=dict(boxstyle="round,pad=0.25", facecolor=C["fondo"], edgecolor=C["eje"]))
        cb = ax.figure.colorbar(im, ax=ax, fraction=0.046, pad=0.02)
        cb.set_label(etiqueta, color=C["tinta2"], fontsize=8)
        cb.ax.tick_params(labelsize=7, colors=C["tinta2"])
        cb.outline.set_visible(False)

    mu = s["mapa_urgencia"]
    lc = np.log10(mu.columns.to_numpy(float))
    xl = float(np.clip((math.log10(lam) - lc[0]) / (lc[1] - lc[0]), 0, len(lc) - 1))
    x_opt = e["tray"]["AC óptima (perfil + ley de potencia)"]
    mapa(a1, mu.to_numpy() * 100, "Urgencia: % del bloque ejecutado en el primer cuarto",
         "λ (1/USD)", "η₀ relativo",
         [f"{v:.0e}" if j % 3 == 0 else "" for j, v in enumerate(mu.columns)],
         [f"{v:g}×" for v in mu.index], "% ejecutado en el 1er cuarto",
         (xl, float(np.argmin(np.abs(mu.index - 1)))), f"λ elegido: {urgencia(x_opt, 0.25):.0%}")
    mc = s["mapa_costo_conf"]
    mapa(a2, mc.to_numpy(), f"Costo al {cfg.var_conf:.0%} (E + z·SD) de la AC óptima, bps",
         "η₀ relativo", "σ relativa", [f"{v:g}×" for v in mc.columns],
         [f"{v:g}×" for v in mc.index], "bps del nocional",
         (float(np.argmin(np.abs(mc.columns - 1))), float(np.argmin(np.abs(mc.index - 1)))),
         f"hoy: {mc.iloc[int(np.argmin(np.abs(mc.index - 1))), int(np.argmin(np.abs(mc.columns - 1)))]:.2f} bps")

    # --- tornado ---
    t = s["tornado"]
    _estilo(a3, "Tornado: E + λV óptimo re-optimizado (bps)")
    base = float(t["U_base_bps"].iloc[0])
    y = np.arange(len(t))
    a3.barh(y, t["U_bajo_bps"] - base, left=base, height=0.62, color=C["s1"], label="valor bajo")
    a3.barh(y, t["U_alto_bps"] - base, left=base, height=0.62, color=C["s2"], label="valor alto")
    for yi, (_, x) in enumerate(t.iterrows()):
        for col, et in (("U_bajo_bps", "etiqueta_bajo"), ("U_alto_bps", "etiqueta_alto")):
            v = x[col]
            a3.annotate(x[et], xy=(v, yi), xytext=(3 if v >= base else -3, 0),
                        textcoords="offset points", va="center",
                        ha="left" if v >= base else "right", fontsize=7, color=C["tinta2"])
    a3.axvline(base, color=C["tinta"], linewidth=1.0)
    a3.set_yticks(y)
    a3.set_yticklabels(t.index)
    a3.set_xlabel(f"bps (base {base:.2f})", color=C["tinta2"], fontsize=9)
    a3.margins(x=0.2)
    _leyenda(a3, loc="lower right")

    # --- arrepentimiento ---
    _estilo(a4, "Arrepentimiento: costo extra de ejecutar el plan base si el parámetro real fuera otro")
    a4.barh(y + 0.18, t["arrep_bajo_bps"], height=0.34, color=C["s1"], label="valor bajo")
    a4.barh(y - 0.18, t["arrep_alto_bps"], height=0.34, color=C["s2"], label="valor alto")
    a4.set_yticks(y)
    a4.set_yticklabels(t.index)
    a4.set_xlabel("bps del nocional", color=C["tinta2"], fontsize=9)
    _leyenda(a4, loc="lower right")

    # --- horizonte ---
    h = s["horizonte"]
    _estilo(a5, "Horizonte de ejecución (λ fijo)")
    a5.plot(h.index, h["U_bps"], color=C["s1"], linewidth=2, marker="o", markersize=5,
            label="E + λV óptimo")
    a5.plot(h.index, h["E_bps"], color=C["s2"], linewidth=1.5, label="E[costo] óptimo")
    a5.plot(h.index, h["U_twap_bps"], color=C["s3"], linewidth=1.5, linestyle="--",
            label="E + λV de un TWAP")
    a5.axvline(m.T, color=C["tinta2"], linewidth=1.0)
    a5.annotate("horizonte elegido", xy=(m.T, 0.02), xycoords=("data", "axes fraction"),
                xytext=(4, 0), textcoords="offset points", fontsize=7.5, color=C["tinta2"])
    a5.set_xscale("log")
    a5.set_xticks(list(h.index))
    a5.set_xticklabels([str(v) for v in h.index], fontsize=7)
    a5.set_xlabel("minutos", color=C["tinta2"], fontsize=9)
    a5.set_ylabel("bps", color=C["tinta2"], fontsize=9)
    a5.set_yscale("log")
    _leyenda(a5, loc="upper left")

    # --- barrido de λ ---
    b = s["barrido_lambda"]
    _estilo(a6, "Aversión al riesgo: costo esperado y riesgo contra λ")
    a6.plot(b["lambda"], b["E_bps"], color=C["s1"], linewidth=2, label="E[costo]")
    a6.plot(b["lambda"], b["SD_bps"], color=C["s2"], linewidth=2, label="SD del costo")
    a6.axvline(lam, color=C["tinta2"], linewidth=1.0)
    a6.annotate(f"λ elegido\n{lam:.2e}", xy=(lam, 0.95), xycoords=("data", "axes fraction"),
                xytext=(4, 0), textcoords="offset points", fontsize=7.5, color=C["tinta2"], va="top")
    a6.set_xscale("log")
    a6.set_xlabel("λ (1/USD)", color=C["tinta2"], fontsize=9)
    a6.set_ylabel("bps", color=C["tinta2"], fontsize=9)
    _leyenda(a6, loc="center right")
    fig.text(0.008, 0.004, f"{IDENTIFICADOR} · los mapas re-optimizan la AC completa en cada celda",
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
    suf = _nombre_seguro(res.cfg.symbol)
    rutas = []
    for nombre, fn in (("volatilidad", tablero_volatilidad), ("ejecucion", tablero_ejecucion),
                       ("sensibilidad", tablero_sensibilidad)):
        if nombre == "sensibilidad" and not res.sens:
            continue
        ruta = carpeta / f"rv_{nombre}_{suf}.png"
        fig = fn(res, plt, ruta)
        rutas.append(ruta)
        print(f"🖼  {ruta}")
        if not ventana:
            plt.close(fig)
    return rutas, plt, ventana


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


# =============================================================================
# 16. TELEGRAM — el token y el chat, igual que la key: FUERA del código
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
    d = res.diario[res.diario["completa"]]
    if len(d) and bool(d["salto"].iloc[-1]):
        x = d.iloc[-1]
        avisos.append(f"Salto significativo en la sesión {d.index[-1]:%Y-%m-%d} "
                      f"(z = {x['z_bns']:.2f}, {x['direccion'].lower()})")
    h = res.har
    if h.get("ok") and h["percentil"] >= res.cfg.telegram_percentil_alerta:
        avisos.append(f"Volatilidad pronosticada en el percentil {h['percentil']:.0%} del año "
                      f"({_anual(h['F_sig']):.1f} % anual)")
    return avisos


def mensaje_telegram(res: Resultado, limite: int = 4096) -> str:
    cfg, e = res.cfg, res.ejec
    esc = html.escape
    m, tab = e["m"], e["tabla"]
    d = res.diario[res.diario["completa"]]
    x = d.iloc[-1] if len(d) else None
    ct0, mx0 = reloj(e["fecha"], int(m.minutos[0]), cfg)
    lin = [f"<b>{esc(IDENTIFICADOR)} · {esc(cfg.symbol)}</b>"]
    for a in hay_alerta(res):
        lin.append(f"⚠️ {esc(a)}")
    if x is not None:
        lin += ["", f"<b>Sesión {d.index[-1]:%Y-%m-%d}</b>",
                f"RV {x['RV_anual']:.1f}% · BV {x['BV_anual']:.1f}% · MedRV {x['MedRV_anual']:.1f}% (anual)",
                f"Test de salto BNS: z = {x['z_bns']:.2f} (crítico {x['crit_bns']:.2f}) → "
                f"{'SALTO ' + esc(x['direccion']) if x['salto'] else 'sin salto'}"]
    h = res.har
    lin.append(f"Pronóstico {'HAR' if h.get('ok') else 'promedio'} próxima sesión: "
               f"<b>{_anual(h['F_sig']):.1f}%</b>"
               + (f" (IC95 {_anual(h['ic_sig'][0]):.1f}–{_anual(h['ic_sig'][1]):.1f}%, "
                  f"percentil {h['percentil']:.0%})" if h.get("ok") else ""))
    lin += ["", f"<b>Ejecución</b> {esc(cfg.lado)} {m.X:,.0f} contratos · {m.T:.0f} min desde "
                f"{ct0:%H:%M} CT ({mx0:%H:%M} CDMX)",
            f"λ = {e['lam']:.2e} 1/USD ({esc(e['modo_lambda'])})"]
    filas = ["estrategia     E bps  SD bps  E+zSD"]
    for nombre, r in tab.iterrows():
        filas.append(f"{CORTO[nombre]:<13s}{r['E_bps']:6.2f}{r['SD_bps']:8.2f}{r['E_zSD_bps']:7.2f}")
    lin.append("<pre>" + esc("\n".join(filas)) + "</pre>")
    p = e["plan"]
    p = p[p["contratos"] > 0]
    if len(p):
        plan_txt = " · ".join(f"{f['hora_ct']} {f['contratos']:,}" for _, f in p.head(16).iterrows())
        lin.append(f"Plan (CT, contratos): {esc(plan_txt)}")
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
# 17. GUARDAR
# =============================================================================
def guardar(res: Resultado) -> None:
    carpeta = _ruta(res.cfg.salida_dir)
    carpeta.mkdir(parents=True, exist_ok=True)
    suf = _nombre_seguro(res.cfg.symbol)
    cols = ["cierre", "completa", "roll", "n", "RV_anual", "RV_ic_bajo", "RV_ic_alto", "BV_anual",
            "MedRV_anual", "TSRV_anual", "RV1_anual", "C_anual", "J_anual", "z_bns", "salto",
            "direccion", "JumpRatio", "RSkew", "RKurt", "F_har_anual", "r_noche", "volumen",
            "reportable"]
    res.diario[[c for c in cols if c in res.diario]].to_csv(carpeta / f"rv_sesiones_{suf}.csv")
    e = res.ejec
    e["tabla"].to_csv(carpeta / f"rv_estrategias_{suf}.csv")
    e["plan"].to_csv(carpeta / f"rv_plan_{suf}.csv", index=False)
    tray = pd.DataFrame({CORTO[k]: v for k, v in e["tray"].items()})
    tray.insert(0, "hora_ct", [reloj(e["fecha"], int(v), res.cfg)[0].strftime("%H:%M")
                               for v in np.r_[e["m"].minutos, e["m"].minutos[-1] + e["m"].tau]])
    tray.to_csv(carpeta / f"rv_trayectorias_{suf}.csv", index=False)
    e["frontera"].drop(columns="x").to_csv(carpeta / f"rv_frontera_{suf}.csv", index=False)
    res.perfil.iloc[:MINUTOS_SESION].to_csv(carpeta / f"rv_perfil_{suf}.csv")
    res.firma.to_csv(carpeta / f"rv_firma_{suf}.csv")
    for k, v in res.sens.items():
        v.to_csv(carpeta / f"rv_sens_{k}_{suf}.csv")
    print(f"💾 Tablas guardadas en {carpeta}")


# =============================================================================
# 18. PRUEBAS INTERNAS
# =============================================================================
def pruebas() -> int:
    cfg = replace(CFG, sim_sesiones=160, har_min=40)
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

    # 1 --------------------------------------------- los estimadores miden la varianza integrada
    s2 = 1.5e-4
    errs = {"RV": [], "BV": [], "MedRV": []}
    for _ in range(200):
        r = rng.normal(0, math.sqrt(s2 / 1380), 1380)
        e = estimadores_submuestreados(np.r_[0, np.cumsum(r)], 5)
        for k in errs:
            errs[k].append(e[k] / s2 - 1)
    sesgos = {k: float(np.mean(v)) for k, v in errs.items()}
    check("RV, BV y MedRV estiman la varianza integrada sin sesgo",
          all(abs(v) < 0.02 for v in sesgos.values()),
          " · ".join(f"{k} {v:+.2%}" for k, v in sesgos.items()))

    # 2 ------------------------------------------------ BV y MedRV resisten un salto; RV no
    r = rng.normal(0, math.sqrt(s2 / 1380), 1380)
    r[700] += 1.0 * math.sqrt(s2)
    e = estimadores_submuestreados(np.r_[0, np.cumsum(r)], 5)
    check("BV y MedRV ignoran un salto; RV lo absorbe",
          e["RV"] / s2 > 1.7 and abs(e["BV"] / s2 - 1) < 0.25 and abs(e["MedRV"] / s2 - 1) < 0.25,
          f"RV {e['RV'] / s2:.2f}× · BV {e['BV'] / s2:.2f}× · MedRV {e['MedRV'] / s2:.2f}× la IV")

    # 3 ------------------------------------------------ la TQ estima la cuarticidad
    tqs = []
    for _ in range(200):
        r = rng.normal(0, math.sqrt(s2 / 1380), 1380)
        tqs.append(estimadores_rejilla(r)["TQ"] / s2 ** 2)
    check("la cuarticidad tripotencia estima ∫σ⁴", abs(np.mean(tqs) - 1) < 0.05,
          f"TQ/σ⁴ = {np.mean(tqs):.3f}  (μ_4/3 = {MU43:.4f})")

    # 4 ------------------------------------------------ el test BNS respeta su nivel
    df4, v4 = simular(cfg, n_sesiones=400, n_saltos=0, n_rolls=0, semilla=21)
    d4, _ = panel_diario(construir_sesiones(preparar_barras(df4, cfg), cfg), cfg)
    tasa4 = float((d4["z_bns"] > _z(1 - cfg.alfa_salto)).mean())
    check("el test de saltos respeta su nivel sin saltos (vol intradía estocástica + perfil U)",
          tasa4 <= 0.005, f"{tasa4:.2%} de 400 sesiones sin salto marcadas (nominal "
                          f"{cfg.alfa_salto:.1%}; el submuestreo lo hace conservador)")

    # 4b ---------------------------------- por qué 5 min: a 1 min, colas t iid rompen el test
    tasas = {}
    for k in (1, 5):
        rech = 0
        for _ in range(300):
            r = math.sqrt(s2 / 1380) * rng.standard_t(5, 1380) / math.sqrt(5 / 3)
            e = estimadores_submuestreados(np.r_[0, np.cumsum(r)], k)
            rech += z_bns(e["RV"], e["BV"], e["TQ"], e["n"]) > _z(0.999)
        tasas[k] = rech / 300
    check("si la vol cambia de un minuto a otro, el test a 1 min se dispara; a 5 min casi no",
          tasas[1] > 0.5 and tasas[5] < 0.05,
          f"falsas alarmas: 1 min {tasas[1]:.0%} · 5 min {tasas[5]:.1%} (tu BV es a 1 min)")

    # 5 ------------------------------------------------ y sí detecta un salto real
    det = 0
    for _ in range(200):
        r = rng.normal(0, math.sqrt(s2 / 1380), 1380)
        r[int(rng.integers(100, 1300))] += 0.8 * math.sqrt(s2) * rng.choice([-1, 1])
        e = estimadores_submuestreados(np.r_[0, np.cumsum(r)], 5)
        det += z_bns(e["RV"], e["BV"], e["TQ"], e["n"]) > _z(0.999)
    check("el test detecta un salto de 0.8 σ diaria", det / 200 > 0.8, f"potencia {det / 200:.0%}")

    # 6 ------------------------------------------------ las semivarianzas suman RV
    e = estimadores_rejilla(rng.normal(0, 1e-3, 500))
    check("RS+ + RS− = RV", abs(e["RSp"] + e["RSn"] - e["RV"]) < 1e-15)

    # 7 ------------------------------------------------ sesión de Globex, no fecha de CDMX
    t = pd.DatetimeIndex(["2026-08-02 17:00", "2026-08-03 15:59", "2026-08-03 17:00",
                          "2026-11-01 17:00", "2026-11-02 08:30"]).tz_localize("America/Chicago")
    ses, mi = sesion_y_minuto(t.tz_convert("UTC"), "America/Chicago")
    esperado = pd.DatetimeIndex(["2026-08-03", "2026-08-03", "2026-08-04", "2026-11-02",
                                 "2026-11-02"])
    check("domingo 17:00 CT abre la sesión del lunes; 17:00 CT abre la del día siguiente",
          bool((pd.DatetimeIndex(ses) == esperado).all()) and list(mi[:3]) == [0, 1379, 0]
          and mi[4] == minuto_de_sesion("08:30"),
          "incluye el cambio de horario de noviembre")

    # 8 ------------------------------------------------ el hueco entre sesiones no entra al RV
    df, ver = simular(cfg, n_sesiones=40, n_saltos=0, n_rolls=0, semilla=3)
    b = preparar_barras(df, cfg)
    ses8 = construir_sesiones(b, cfg)
    df2 = df.copy()
    lunes = pd.DatetimeIndex(sesion_y_minuto(df2.index, cfg.tz_mercado)[0]) == ses8.fechas[20]
    for c in ("open", "high", "low", "close"):
        df2.loc[lunes, c] = df2.loc[lunes, c] * 1.03          # la sesión 20 abre con +3 %
    ses8b = construir_sesiones(preparar_barras(df2, cfg), cfg)
    d1 = estimadores_submuestreados(ses8.rejilla(20), 5)["RV"]
    d2 = estimadores_submuestreados(ses8b.rejilla(20), 5)["RV"]
    check("un hueco de +3 % en la apertura no cambia el RV de la sesión",
          abs(d2 / d1 - 1) < 1e-6 and abs(ses8b.r_noche[20] - ses8.r_noche[20] - math.log(1.03)) < 1e-6,
          f"RV {d1:.3e} → {d2:.3e}; el hueco queda en r_noche")

    # 9 ------------------------------------------------ rolls por instrument_id, no por symbol
    df9, v9 = simular(cfg, n_sesiones=60, n_saltos=0, n_rolls=2, semilla=4)
    ses9 = construir_sesiones(preparar_barras(df9, cfg), cfg)
    check("los rolls se detectan por instrument_id (symbol no cambia en el continuo)",
          int(ses9.roll.sum()) == 2 and df9["symbol"].nunique() == 1
          and bool(np.all(np.isnan(ses9.r_noche[ses9.roll]))),
          f"{int(ses9.roll.sum())} rolls; la columna symbol tiene {df9['symbol'].nunique()} valor")

    # 10 ------------------------------------------------ escala de precios: se detecta
    d10 = df9.head(500).copy()
    d10f = d10.copy()
    for c in ("open", "high", "low", "close"):
        d10f[c] = (d10f[c] * 1e9).round().astype("int64")
    p_float = preparar_barras(d10, cfg)["close"].median()
    p_fijo = preparar_barras(d10f, cfg)["close"].median()
    check("la escala se detecta: float queda igual, punto fijo se divide entre 1e9",
          abs(p_float / p_fijo - 1) < 1e-9 and p_float > 1000,
          f"{p_float:,.2f} en los dos casos; tu PRICE_SCALE lo dejaría en {p_float / 1e9:.2e}")

    # 11 ------------------------------------------------ AC: cerrada = tridiagonal = numérica
    sig2 = np.full(30, 400.0 ** 2)
    m = Mercado(X=500, tau=1.0, sig2=sig2, vol=np.full(30, 2000.0), S0=420_000.0,
                sigma_dia=0.012, eps=4.5, eta0=0.142, beta=1.0, gamma=1e-3,
                minutos=np.arange(930, 960), varianza="discreta")
    lam = 5e-7
    eta = m.eta_lineal()
    xc = ac_cerrada(m.X, m.N, m.tau, 400.0 ** 2, eta, m.gamma, lam)
    xt = ac_lineal_variable(m, lam)
    xn = ac_optima(m, lam)
    check("AC: la fórmula cerrada, el sistema tridiagonal y el óptimo numérico coinciden (β = 1)",
          np.max(np.abs(xc - xt)) < 1e-6 * m.X and np.max(np.abs(xn - xt)) < 1e-4 * m.X,
          f"máx |cerrada − tridiagonal| = {np.max(np.abs(xc - xt)):.1e} · "
          f"|numérica − tridiagonal| = {np.max(np.abs(xn - xt)):.1e} contratos")

    # 12 ------------------------------------------------ las fórmulas (20)-(21) del artículo
    Ec, Vc = ac_cerrada_momentos(m.X, m.N, m.tau, 400.0 ** 2, eta, m.gamma, m.eps, lam)
    ed = evaluar(m, xc)
    check("E y V cerradas de Almgren-Chriss = sumas discretas",
          abs(Ec / ed["E"] - 1) < 1e-9 and abs(Vc / ed["V"] - 1) < 1e-9,
          f"E {Ec:,.2f} vs {ed['E']:,.2f} · V {Vc:.4e} vs {ed['V']:.4e}")

    # 13 ------------------------------------------------ λ → 0 da VWAP con impacto en participación
    f_var, f_vol = perfiles_teoricos()
    mv = construir_mercado(cfg, pd.DataFrame({"var": f_var, "vol": f_vol}), 1.6e-4, 600_000,
                           21000.0)
    x0 = ac_optima(mv, 1e-16)
    xv = vwap(mv)
    check("sin aversión al riesgo, el óptimo con impacto en participación es el VWAP",
          np.max(np.abs(x0 - xv)) < 2e-3 * mv.X,
          f"máx desviación {np.max(np.abs(x0 - xv)):.3f} contratos de {mv.X:.0f}")

    # 14 ------------------------------------------------ λ → ∞: inmediata, o al tope si lo hay
    libre = replace(mv, part_max=np.inf)
    xi = ac_optima(libre, lambda_referencia(libre) * 1e8)
    m14 = replace(mv, X=2000.0)                  # bloque que NO cabe en un minuto al 25 %
    xt = ac_optima(m14, lambda_referencia(m14) * 1e8)
    nt = xt[:-1] - xt[1:]
    k_ = int(np.sum(np.cumsum(m14.tope) < m14.X))       # tramos que caben completos al tope
    al_tope = (np.allclose(nt[:k_], m14.tope[:k_], rtol=1e-3)
               and np.cumsum(nt)[k_] >= m14.X * (1 - 1e-5) and np.all(nt <= m14.tope * (1 + 1e-9)))
    check("con aversión extrema: inmediata sin tope; al tope de participación con tope",
          urgencia(xi, 1 / mv.N) > 0.97 and al_tope and k_ >= 1,
          f"{urgencia(xi, 1 / mv.N):.1%} en el 1er tramo sin tope · 2000 contratos con tope "
          f"{m14.part_max:.0%}: {k_} tramos al máximo y el resto en el siguiente")

    # 15 ------------------------------------------------ la frontera es monótona
    fr = frontera(mv, lambda_referencia(mv) * np.logspace(-3, 4, 25))
    check("frontera eficiente: al subir λ el costo esperado sube y el riesgo baja",
          bool(np.all(np.diff(fr["E"]) > -1e-6 * fr["E"].abs().max())
               and np.all(np.diff(fr["SD"]) < 1e-6 * fr["SD"].max())))

    # 16 ------------------------------------------------ la AC óptima gana en su objetivo
    lam16 = lambda_referencia(libre) * 3
    u_opt = objetivo(libre, ac_optima(libre, lam16), lam16)
    otras = {"TWAP": twap(libre), "VWAP": vwap(libre), "Inmediata": inmediata(libre),
             "AC clásica": ac_clasica(libre, lam16), "tridiagonal": ac_lineal_variable(libre, lam16)}
    peor = min(objetivo(libre, x, lam16) - u_opt for x in otras.values())
    check("la AC óptima tiene el menor E + λV de todas las estrategias", peor >= -1e-6 * u_opt,
          f"margen mínimo {peor:,.2f} USD")

    # 17 ------------------------------------------------ el λ por VaR minimiza E + z·SD
    m17 = construir_mercado(replace(cfg, contratos=6000), pd.DataFrame({"var": f_var, "vol": f_vol}),
                            1.6e-4, 600_000, 21000.0)
    lam17, modo17 = elegir_lambda(m17, cfg)
    z = _z(cfg.var_conf)
    g = lambda l: (lambda e: e["E"] + z * e["SD"])(evaluar(m17, ac_optima(m17, l)))
    v0, vm, vp = g(lam17), g(lam17 * 0.8), g(lam17 * 1.25)
    x17 = ac_optima(m17, lam17)
    lam17b, modo17b = elegir_lambda(replace(mv, X=50.0), cfg)
    check("λ por confianza: interior con precio del riesgo = z; esquina si el bloque es chico",
          v0 <= min(vm, vp) + 1e-6 * v0 and abs(2 * lam17 * evaluar(m17, x17)["SD"] / z - 1) < 0.05
          and "ESQUINA" not in modo17 and "ESQUINA" in modo17b,
          f"6000 contratos: 2λ·SD = {2 * lam17 * evaluar(m17, x17)['SD']:.3f} contra z = {z:.3f} · "
          "50 contratos: esquina")

    # 18 ------------------------------------------------ la réplica reproduce media y SD
    R = rng.normal(0, 1, (4000, mv.N)) * np.sqrt(mv.sig2) / mv.S0
    x18 = ac_optima(mv, lam16)
    c = costos_replica(mv, x18, R, 1)
    e18 = evaluar(mv, x18)
    check("réplica con retornos gaussianos: media ≈ E y SD ≈ √V",
          abs(np.mean(c) - e18["E"]) < 4 * e18["SD"] / math.sqrt(len(c))
          and abs(np.std(c) / e18["SD"] - 1) < 0.05,
          f"media {np.mean(c):,.0f} vs {e18['E']:,.0f} · SD {np.std(c):,.0f} vs {e18['SD']:,.0f}")

    # 19 ------------------------------------------------ el HAR le gana al RV de ayer
    df19, _ = simular(cfg, n_sesiones=220, n_saltos=0, n_rolls=0, semilla=8)
    ses19 = construir_sesiones(preparar_barras(df19, cfg), cfg)
    d19, _ = panel_diario(ses19, cfg)
    h19 = pronostico_har(d19, cfg)
    check("el HAR pronostica mejor que el RV de ayer (QLIKE fuera de muestra)",
          h19["ok"] and h19["qlike"]["HAR"] < h19["qlike"]["RV de ayer"],
          f"QLIKE HAR {h19['qlike']['HAR']:.4f} vs ayer {h19['qlike']['RV de ayer']:.4f} "
          f"(t DM {h19['dm_t']['RV de ayer']:.2f})" if h19["ok"] else "sin HAR")

    # 20 ------------------------------------------------ el pronóstico no mira al futuro
    d19b = d19.copy()
    d19b.iloc[-30:, d19b.columns.get_loc("RV")] *= 5.0
    h19b = pronostico_har(d19b, cfg)
    corte = len(h19["F"]) - 31
    check("el HAR no mira al futuro (alterar las últimas 30 sesiones no cambia lo anterior)",
          np.allclose(h19["F"][:corte], h19b["F"][:corte], equal_nan=True))

    # 21 ------------------------------------------------ Telegram: HTML seguro y sin token
    tok = "123456789:" + "A" * 35
    msg = _sin_token(f"fallo en https://api.telegram.org/bot{tok}/sendMessage", tok)
    check("los errores de Telegram nunca muestran el token", tok not in msg and "…" in msg)

    # 21b ----------------------------------------------- Telegram de punta a punta, sin red
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

    viejo_open = urllib.request.urlopen
    viejo_env = {k: os.environ.get(k) for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")}
    png = Path(__file__).resolve().parent / "_prueba_telegram.png"
    try:
        urllib.request.urlopen = _falso
        os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"] = tok, "123456789"
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
        ok = llamar_telegram(tok, "sendPhoto", {"chat_id": "123456789", "caption": "á <b>"},
                             archivo=("photo", png)).get("ok")
        cuerpo = capturas[-1].data
        cab = capturas[-1].get_header("Content-type")
        limite = cab.split("boundary=")[1]
        bien = (ok and cuerpo.startswith(f"--{limite}".encode())
                and cuerpo.rstrip().endswith(f"--{limite}--".encode())
                and b'name="photo"; filename="_prueba_telegram.png"' in cuerpo
                and "á <b>".encode() in cuerpo and tok.encode() not in cuerpo)
    finally:
        urllib.request.urlopen = viejo_open
        png.unlink(missing_ok=True)
        for k, v in viejo_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    check("Telegram: el multipart de sendPhoto está bien formado y no lleva el token",
          bool(bien), "el token sólo va en la URL de la Bot API, nunca en el cuerpo ni en logs")

    # 22 ------------------------------------------------ ninguna key escrita en este archivo
    fuente = Path(__file__).read_text(encoding="utf-8")
    patron_db = "db" + "-" + r"[A-Za-z0-9]{20,}"
    patron_tg = r"\d{8,10}:" + r"[A-Za-z0-9_-]{35}"
    check("no hay API keys ni tokens escritos en el código",
          not re.search(patron_db, fuente) and not re.search(patron_tg, fuente))

    # 23 ------------------------------------------------ de punta a punta, con Telegram simulado
    df23, v23 = simular(cfg, n_sesiones=120, semilla=12)
    c23 = replace(cfg, start=str(pd.DatetimeIndex(np.unique(sesion_y_minuto(
        df23.index, cfg.tz_mercado)[0]))[-40].date()), end="2100-01-01", replica_dias=100)
    res = analizar(preparar_barras(df23, c23), c23, verdad=v23, sensib=True, verboso=False)
    txt = mensaje_telegram(res)
    check("el módulo corre de punta a punta y arma el mensaje de Telegram",
          len(res.ejec["tabla"]) == 5 and len(txt) <= 4096 and "<pre>" in txt
          and res.ejec["plan"]["contratos"].sum() == int(c23.contratos),
          f"{res.diag['n_sesiones']} sesiones · {len(txt)} caracteres · plan de "
          f"{res.ejec['plan']['contratos'].sum()} contratos")

    print()
    if fallas:
        print(f"❌ {len(fallas)} de {hecho} pruebas fallaron: {', '.join(fallas)}")
        return 1
    print(f"✅ Las {hecho} pruebas pasaron.")
    return 0


# =============================================================================
# 19. LÍNEA DE COMANDOS
# =============================================================================
def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="realized_volatility_institucional.py",
        description="RV Institucional AC v2 — volatilidad realizada robusta por sesión CME y "
                    "ejecución óptima Almgren-Chriss.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="La API key se lee de DATABENTO_API_KEY; Telegram, de TELEGRAM_BOT_TOKEN y "
               "TELEGRAM_CHAT_ID. Nunca los escribas en el código.")
    p.add_argument("--pruebas", action="store_true", help="pruebas internas (sin red ni datos)")
    p.add_argument("--simulacion", action="store_true",
                   help="datos simulados con saltos y rolls CONOCIDOS: mide y se deja medir")
    p.add_argument("--sin-tablero", action="store_true", help="no genera los PNG")
    p.add_argument("--sin-ventana", action="store_true", help="guarda los PNG sin abrir nada")
    p.add_argument("--sin-cache", action="store_true", help="vuelve a descargar de Databento")
    p.add_argument("--sin-sensibilidad", action="store_true", help="salta el análisis de sensibilidad")

    d = p.add_argument_group("datos y contrato")
    d.add_argument("--symbol", default=None)
    d.add_argument("--dataset", default=None)
    d.add_argument("--start", default=None, help="inicio de la ventana reportada (UTC)")
    d.add_argument("--end", default=None, help="fin de la ventana reportada (UTC, exclusivo)")
    d.add_argument("--calentamiento", type=int, default=None, dest="dias_calentamiento",
                   help="días naturales de historia previa (HAR, perfiles, réplica)")
    d.add_argument("--costo-max", type=float, default=None, dest="costo_max_usd")
    d.add_argument("--multiplicador", type=float, default=None, help="USD por punto")
    d.add_argument("--tick", type=float, default=None)
    d.add_argument("--spread-ticks", type=float, default=None, dest="spread_ticks")
    d.add_argument("--comision", type=float, default=None, dest="comision_usd",
                   help="USD por contrato y por lado")

    v = p.add_argument_group("volatilidad")
    v.add_argument("--freq", type=int, default=None, dest="freq_min",
                   help="minutos entre observaciones para RV/BV/MedRV")
    v.add_argument("--sin-submuestreo", action="store_true")
    v.add_argument("--alfa-salto", type=float, default=None, dest="alfa_salto")

    e = p.add_argument_group("ejecución (Almgren-Chriss)")
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
                   help="λ que ejecuta la mitad del bloque en estos minutos")
    e.add_argument("--part-max", type=float, default=None, dest="part_max",
                   help="participación máxima por tramo, p. ej. 0.25 (≥ 1 = sin tope)")

    i = p.add_argument_group("coeficientes de impacto")
    i.add_argument("--eta0", type=float, default=None)
    i.add_argument("--beta", type=float, default=None)
    i.add_argument("--gamma0", type=float, default=None)

    t = p.add_argument_group("Telegram")
    t.add_argument("--telegram", action="store_true", help="envía el resumen y los tableros")
    t.add_argument("--telegram-solo-alertas", action="store_true",
                   help="envía sólo si hay salto en la última sesión o volatilidad alta")
    t.add_argument("--telegram-documentos", action="store_true",
                   help="envía los PNG como documento (sin compresión)")
    t.add_argument("--telegram-buscar-chat", action="store_true",
                   help="lista los chat_id que le escribieron a tu bot y sale")

    s = p.add_argument_group("simulación")
    s.add_argument("--sesiones-sim", type=int, default=None, dest="sim_sesiones")
    s.add_argument("--saltos-sim", type=int, default=None, dest="sim_saltos")
    s.add_argument("--semilla", type=int, default=None, dest="sim_semilla")
    return p


def config_desde_args(a: argparse.Namespace) -> Config:
    cambios = {}
    for k in ("symbol", "dataset", "start", "end", "dias_calentamiento", "costo_max_usd",
              "multiplicador", "tick", "spread_ticks", "comision_usd", "freq_min", "alfa_salto",
              "lado", "contratos", "inicio_ct", "horizonte_min", "paso_min", "aversion",
              "var_conf", "vida_media_min", "part_max", "eta0", "beta", "gamma0", "sim_sesiones",
              "sim_saltos", "sim_semilla"):
        v = getattr(a, k, None)
        if v is not None:
            cambios[k] = v
    if getattr(a, "sin_cache", False):
        cambios["usar_cache"] = False
    if getattr(a, "sin_submuestreo", False):
        cambios["submuestreo"] = False
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

    print(f"▶ {IDENTIFICADOR} · {cfg.symbol} · RV {cfg.freq_min} min · "
          f"{cfg.lado} {cfg.contratos:,.0f} contratos · {cfg.horizonte_min} min desde "
          f"{cfg.inicio_ct} CT")
    verdad = None
    if a.simulacion:
        print(f"🎲 {cfg.sim_sesiones} sesiones simuladas de 1 min: perfil en U, colas gruesas,")
        print(f"   ruido de compra-venta, {cfg.sim_saltos} SALTOS en minutos conocidos y "
              f"{cfg.sim_rolls} rolls.")
        crudo, verdad = simular(cfg)
        fechas = np.unique(sesion_y_minuto(crudo.index, cfg.tz_mercado)[0])
        cfg = replace(cfg, start=str(pd.Timestamp(fechas[-60]).date()), end="2100-01-01")
    else:
        crudo = obtener_datos(cfg)
    barras = preparar_barras(crudo, cfg)
    print(f"📊 {len(barras):,} barras de 1 min · {barras.index[0]:%Y-%m-%d} → "
          f"{barras.index[-1]:%Y-%m-%d} (UTC)")

    res = analizar(barras, cfg, verdad=verdad, sensib=not a.sin_sensibilidad)
    reporte_datos(res)
    reporte_estimadores(res)
    reporte_saltos(res)
    reporte_verdad(res)
    reporte_har(res)
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
            print("📭 Telegram: sin alertas (ni salto en la última sesión ni volatilidad alta).")
        else:
            enviar_telegram(res, rutas, documentos=a.telegram_documentos)

    _titulo("CÓMO LEER ESTO")
    print("  1. La unidad es la sesión de Globex (17:00 → 16:00 CT). Lo que pasa en la pausa y")
    print("     el fin de semana va en r_noche, no en el RV. Los rolls no son retornos.")
    print("  2. Un salto es una sesión cuyo z de BNS pasa el crítico: tiene una probabilidad de")
    print("     falsa alarma conocida. BV y MedRV son la volatilidad 'sin saltos'.")
    print("  3. La σ que usa la ejecución es el PRONÓSTICO HAR de la próxima sesión, repartida")
    print("     minuto a minuto con el perfil intradía medido.")
    print("  4. λ decide cuánto costo esperado aceptas pagar por quitar riesgo. Con --var-conf")
    print("     se elige de modo que la estrategia minimice el costo al 95 % de confianza.")
    print("  5. η₀ y β no se pueden medir con OHLCV. El tornado y el arrepentimiento dicen si")
    print("     tu decisión cambiaría si estuvieran mal; en general cambia el COSTO, no el PLAN.")

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
