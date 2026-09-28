# -*- coding: utf-8 -*-
"""
HURST EXPONENT AC v2 — régimen Mean-Reverting / Random Walk / Trending, con confianza estadística
Datos: Databento OHLCV (GLBX.MDP3), barras por sesión de CME Globex, sin saltos de roll.

Qué hace, en una línea: mide en cada barra el exponente de Hurst del log-precio (sin saltos
de roll) y decide si el mercado está en Mean-Reverting, Random Walk o Trending. La decisión
se toma contra lo que daría un paseo aleatorio con TU misma volatilidad. Después audita si
esa etiqueta anticipa algo de lo que pasa DESPUÉS.

LO QUE PEDISTE, HECHO A FONDO

  1-3. LOS TRES REGÍMENES: MEAN-REVERTING (H < 0.45), RANDOM WALK (H ≈ 0.50) Y TRENDING
     (H > 0.55). Se conservan tus umbrales, pero se aplican a H CORREGIDO. En una ventana de
     500 barras el estimador sale sesgado hacia abajo: −0.01 a −0.02 el de aquí, ~−0.03 el tuyo.
     Un régimen sólo cuenta si además se CONFIRMA (punto 6); lo que no se confirma es Random
     Walk, porque no hay evidencia de memoria.

  4. CÁLCULO POR VARIANZA DE DIFERENCIAS (tu "R/S simplificado"): std(x(t) − x(t − τ)) ∝ τ^H,
     con tres cambios medidos:
       · 12 rezagos en escala LOG (1 … 50), no 48 lineales (2 … 49);
       · mínimos cuadrados PONDERADOS por (W − τ)/τ, las diferencias independientes que hay
         detrás de cada punto;
       · τ = 1 incluido.
     Con 400 ventanas independientes y volatilidad realista, la desviación de Ĥ baja de
     0.070-0.074 a 0.041-0.045. Además, para la última ventana: R/S clásico, R/S con la
     corrección de Anis-Lloyd, DFA y la razón de varianzas de Lo-MacKinlay con su prueba z*.

  5. EVALUACIÓN CONTINUA (ROLLING WINDOW). Una ventana por barra, sólo con el pasado, calculada
     con sumas acumuladas: todas las ventanas en O(T · rezagos), más 200 caminos nulos, en
     segundos. Una prueba verifica que da lo mismo que calcular ventana por ventana (1.7e-15)
     y otra que truncar la muestra no cambia el pasado. Tu --step ya no hace falta.

  6. FILTRO DE CONFIANZA (R-CUADRADO). Se mantiene tu R² ≥ 0.85, pero no alcanza: en un paseo
     aleatorio lo pasa el 99.8 % de las ventanas, porque el R² mide que el log-log sea una
     recta, no que H sea distinto de 0.5. Por eso se agrega la prueba que sí decide. En cada
     barra se construyen 200 caminos con los MISMOS retornos pero con signos al azar: igual
     volatilidad, colas y estacionalidad, sin memoria. Esos caminos dan la banda del ruido,
     el sesgo y un p-valor de un lado. Confirmado = umbral cruzado + p < 0.05 + R² ≥ 0.85.

  7. MÓDULO DE AUDITORÍA (FORWARD RETURNS Y AUTOCORRELACIÓN). El Hurst habla de DIRECCIÓN, no
     de tamaño. Por eso, para h = 1, 4, 8 y 24 barras se mide
         D = signo(movimiento de las h barras previas) × retorno de las h barras siguientes,
     con t de Newey-West, tasa de acierto y la correlación entre ambos tramos contra la que
     implica H (2^(2H−1) − 1). Además:
       · la autocorrelación de los retornos DESPUÉS de la etiqueta, contra la teórica del H
         medido;
       · la persistencia real de H (la ventana de hoy contra la siguiente sin solape);
       · una regla operable con costos (seguir en Trending, revertir en Mean-Reverting) contra
         momentum y reversión siempre.
     Todo para el módulo, para el umbral sin confirmar y para tu script, lado a lado.

  8. DASHBOARD VISUAL DE TRANSICIÓN. Dos tableros:
       · TRANSICIÓN: precio con el régimen confirmado, H corregido contra la banda del ruido y
         tu H encima, p-valor y R² en el tiempo, matriz de transición a W barras (la
         persistencia real, no la mecánica del solape), duración de cada régimen y qué pasa
         en las 48 barras después de ENTRAR a cada uno;
       · AUDITORÍA: el log-log de la última ventana con su banda nula, la distribución del
         ruido contra Ĥ, cinco estimadores, D por régimen y horizonte con IC 95 %,
         correlación real contra implícita, autocorrelación condicional, persistencia de H y
         curvas de la regla operable.

  Además: barras de 1, 2, 3, 5, 10, 15, 20 o 30 min (desde OHLCV-1m), de 1-12 h o una por
  sesión, siempre alineadas a la sesión de Globex; rolls del continuo quitados por
  instrument_id; un simulador con tramos de H CONOCIDO para medir todo contra la verdad;
  27 pruebas internas; CSV; y resumen, tableros y alertas por Telegram.

QUÉ SE MIDIÓ
  · 400 ventanas independientes de 500 barras por caso, con volatilidad realista (agrupada
    por sesión, colas t5 y estacionalidad intradía). % de ventanas marcadas:

        H verdadero       tu regla               módulo (confirmado)
                          MEAN_REV   TRENDING    Mean-Reverting   Trending
        0.50 (nada)        39.5 %     11.2 %          5.0 %          4.0 %
        0.45               52.0 %      6.0 %         18.2 %          0.8 %
        0.55               21.0 %     24.5 %          1.0 %         25.5 %
        0.35               80.8 %      0.5 %         81.0 %          0.0 %
        0.65                5.0 %     62.0 %          0.0 %         83.8 %

    Sin memoria, tu regla marca régimen en la mitad de las ventanas y el módulo en el 9 %
    (el 5 % por lado que promete α). Con memoria fuerte (H = 0.65), el módulo la ve más
    seguido que tu regla (84 % contra 62 %). Con H = 0.55, tu regla marca Mean-Reverting
    casi tanto como Trending (21 % contra 24.5 %).
  · Simulación de 8 000 barras de 1 h con tramos Random Walk → Trending → Random Walk →
    Mean-Reverting (--simulacion): exactitud 82.6 % contra 65.5 % de tu regla, y
    correlación con el H verdadero 0.86 contra 0.65. La auditoría ve la memoria que hay:
    tras Trending confirmado D = +2.1 bps a 1 barra (t +4.9), tras Mean-Reverting −2.5 bps
    (t −3.6).
  · Con 20 000 barras de fGn, el estimador recupera H = 0.3 / 0.5 / 0.7 como 0.308 / 0.498 /
    0.699.

QUÉ FALLABA EN EL SCRIPT QUE MANDASTE (los comentarios [v2] lo marcan en el código)

  · LA API KEY ESTÁ ESCRITA EN LA LÍNEA 36. Dala por publicada y regenérala. Aquí se lee de
    DATABENTO_API_KEY, igual que en tus otros módulos.

  · --barra 5, 15 Y 30 NO FUNCIONAN. Databento no tiene "ohlcv-5m", "ohlcv-15m" ni
    "ohlcv-30m": sólo 1 s, 1 min, 1 h y 1 día. Tu propio docstring sugiere --barra 5, y la
    API rechaza esa petición.

  · TUS UMBRALES NO SABEN CUÁNTO RUIDO TIENE H. Con 500 barras la desviación de tu Ĥ es
    ~0.07, más que la distancia de 0.05 entre 0.5 y cada umbral, y el estimador sale sesgado
    hacia abajo (~−0.03). Resultado: en un paseo aleatorio marcas MEAN_REV el 39.5 % de las
    veces y TRENDING el 11.2 %.

  · EL FILTRO R² ≥ 0.85 NO FILTRA. Lo pasa el 99.8 % de las ventanas sin memoria.

  · REZAGOS LINEALES. Con τ = 2 … 49, 40 de los 48 puntos del log-log caen en la mitad de
    arriba, donde cada varianza es más ruidosa. Ellos deciden la pendiente.

  · LOS ROLLS ENTRAN AL PRECIO. El salto trimestral del NQ (del orden de 1 %) entra a
    todas las diferencias que lo cruzan y a los retornos futuros de la auditoría.

  · TU AUDITORÍA NO MIDE LO QUE EL HURST PROMETE. Mide |retorno| futuro (tamaño) en vez de
    dirección y no da estadístico t. Su autocorr() por régimen empareja FILAS del filtro:
    cada vez que el régimen se interrumpe, junta dos barras lejanas de tramos distintos.

  · Menores: el tablero sombrea el régimen aunque la ventana no sea "utilizable", y
    np.random.seed(7) no se usa.

POR QUÉ UN AÑO POR OMISIÓN. Tu ventana (junio-agosto 2026) son ~1 450 barras de 1 h. A
h = 24 eso da unas 60 observaciones independientes para la auditoría, muy pocas para
distinguir algo de ruido. Aquí --start es 2025-09-01; con --start 2026-06-01 vuelves a la
tuya.

LÍMITES QUE CONVIENE SABER
  · LA ETIQUETA LLEGA TARDE Y SE VA TARDE. Una ventana de 500 barras necesita que buena parte
    de ella tenga memoria. En el tramo Trending de la simulación se confirma ~120 barras
    después de que empieza y sigue ~270 después de que acaba: un tercio de las barras
    marcadas Trending ya no lo eran. Con la etiqueta verdadera, D tras Trending sale 1.4 a 2.4
    veces mayor.
  · Con 500 barras sólo se detecta memoria fuerte: H = 0.55 se confirma en el 25 % de las
    ventanas. Una ventana más larga detecta más, pero reacciona más tarde.
  · En futuros líquidos lo normal es que H quede dentro de la banda la mayor parte del
    tiempo. Si en tus datos la auditoría no da |t| ≥ 2 en la dirección del régimen, el
    reporte lo dice: el Hurst describe la ventana pasada, no anticipa la siguiente.
  · La nula de signos al azar supone choques simétricos: prueba la dirección, no la
    asimetría. La regla operable es un diagnóstico, no un backtest con ejecución realista.

CÓMO SE USA
    pip install numpy pandas matplotlib databento
    python hurst_exponent.py --pruebas                    # 27 pruebas, sin red
    python hurst_exponent.py --simulacion                 # todo, con H conocido por tramos
    python hurst_exponent.py --simulacion --sim-paseo     # un paseo aleatorio puro
    python hurst_exponent.py                              # NQ, 1 h, 2025-09-01 → 2026-09-01
    python hurst_exponent.py --start 2026-06-01           # tu ventana original
    python hurst_exponent.py --simbolo ES --barra 5
    python hurst_exponent.py --barra 1440 --ventana 250 --start 2021-01-01   # una barra por sesión
    python hurst_exponent.py --alfa 0.01 --nula 500       # confirmar con más exigencia
    python hurst_exponent.py --telegram                   # resumen + 2 tableros
    python hurst_exponent.py --telegram-solo-alertas      # sólo si cambia el régimen confirmado
  Tus opciones siguen funcionando: --simbolo, --inicio, --fin, --barra, --ventana, --max-lag,
  --r2-min, --sin-grafica y --salida. Las fechas del tablero van en hora de CDMX; el reporte
  muestra también la de Chicago.

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
  Hurst, H. E. (1951), "Long-term storage capacity of reservoirs", Transactions of the
      American Society of Civil Engineers 116. — el R/S original.
  Mandelbrot, B. y Van Ness, J. (1968), "Fractional Brownian motions, fractional noises and
      applications", SIAM Review 10(4). — el modelo con H.
  Anis, A. y Lloyd, E. (1976), "The expected value of the adjusted rescaled Hurst range of
      independent normal summands", Biometrika 63(1). — el sesgo del R/S en muestras chicas.
  Peters, E. (1994), Fractal Market Analysis, Wiley. — el ajuste (n − ½)/n.
  Lo, A. y MacKinlay, C. (1988), "Stock market prices do not follow random walks: evidence
      from a simple specification test", Review of Financial Studies 1(1). — razón de varianzas.
  Lo, A. (1991), "Long-term memory in stock market prices", Econometrica 59(5).
  Peng, C.-K. et al. (1994), "Mosaic organization of DNA nucleotides", Physical Review E 49(2).
      — DFA.
  Couillard, M. y Davison, M. (2005), "A comment on measuring the Hurst exponent of financial
      time series", Physica A 348. — por qué un H ≠ 0.5 en una muestra corta no prueba memoria.
  Davies, R. y Harte, D. (1987), "Tests for Hurst effect", Biometrika 74(1). — la simulación.
  Wu, C. F. J. (1986), Annals of Statistics 14(4), y Mammen, E. (1993), Annals of Statistics
      21(1). — el bootstrap salvaje (signos al azar) que da la nula.
  Newey, W. y West, K. (1987), Econometrica 55(3). — el t con retornos que se solapan.
  Databento: https://databento.com/docs — OHLCV-1m / 1h, símbolos continuos .n.0.
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

IDENTIFICADOR = "hurst-exponent-ac-v2"
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)
np.seterr(all="ignore")

# --- Constantes de la sesión de CME Globex ---
MINUTOS_SESION = 1380            # 17:00 → 16:00 CT (23 horas)
DESFASE_H = 7                    # hora CT + 7 h → la sesión que abre a las 17:00 cae en su fecha

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

MR, RW, TR = "Mean-Reverting", "Random Walk", "Trending"
REGIMENES = (MR, RW, TR)
ESQUEMAS_DATABENTO = ("ohlcv-1s", "ohlcv-1m", "ohlcv-1h", "ohlcv-1d", "ohlcv-eod")


# =============================================================================
# 1. CONFIGURACIÓN
# =============================================================================
@dataclass(frozen=True)
class Config:
    # --- Datos ---
    dataset: str = "GLBX.MDP3"
    symbol: str = "NQ.n.0"
    start: str = "2025-09-01T00:00:00"     # tu script: 2026-06-01 (3 meses; ver el encabezado)
    end: str = "2026-09-01T00:00:00"       # exclusivo
    barra_min: int = 60                    # minutos por barra; 1440 = una barra por sesión
    cache_dir: str = "datos_databento"
    usar_cache: bool = True
    salida_dir: str = "salidas_hurst"
    costo_max_usd: float = 10.0
    tz_mercado: str = "America/Chicago"
    tz_local: str = "America/Mexico_City"

    # --- Hurst: varianza de diferencias ---
    ventana: int = 500                     # barras por ventana (igual que tu script)
    lag_min: int = 1
    max_lag: int = 50
    n_lags: int = 13                       # rezagos espaciados en escala log
    ponderado: bool = True                 # mínimos cuadrados ponderados por (W − τ)/τ

    # --- Filtro de confianza ---
    r2_min: float = 0.85                   # tu R² mínimo
    n_nula: int = 200                      # caminos con signos al azar por barra
    alfa: float = 0.05                     # p-valor máximo, de un lado
    semilla_nula: int = 7

    # --- Régimen ---
    umbral_mr: float = 0.45
    umbral_tr: float = 0.55

    # --- Auditoría ---
    horizontes: tuple[int, ...] = (1, 4, 8, 24)
    h_senal: int = 24                      # barras para la dirección del movimiento previo
    rezagos_acf: int = 10
    costo_ticks: float = 0.5               # por unidad operada (medio spread)

    # --- Simulación ---
    sim_barras: int = 8000
    sim_semilla: int = 0
    sim_hs: tuple[float, float, float] = (0.35, 0.50, 0.65)
    sim_duracion: int = 900                # barras promedio de cada tramo de régimen

    # --- Telegram ---
    telegram_solo_confirmados: bool = True


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
    return CATALOGO.get(raiz(symbol), ("", 0.0, 100.0))[1]


def minutos_por_barra(cfg: Config) -> int:
    return MINUTOS_SESION if cfg.barra_min == 1440 else int(cfg.barra_min)


def barras_por_ano(cfg: Config) -> float:
    return 252.0 * MINUTOS_SESION / minutos_por_barra(cfg)


def etiqueta_barra(cfg: Config) -> str:
    b = cfg.barra_min
    return "sesión" if b == 1440 else (f"{b // 60} h" if b % 60 == 0 else f"{b} min")


def validar(cfg: Config) -> None:
    b = int(cfg.barra_min)
    if not (b == 1440 or (1 <= b < 60 and 60 % b == 0) or (60 <= b <= 720 and b % 60 == 0)):
        sys.exit(f"❌ --barra {b}: usa un divisor de 60 (1, 2, 3, 5, 10, 15, 20, 30), un múltiplo "
                 "de 60 hasta 720, o 1440 (una barra por sesión).")
    if cfg.lag_min < 1 or cfg.max_lag <= cfg.lag_min:
        sys.exit("❌ Hace falta 1 ≤ --lag-min < --max-lag.")
    if cfg.max_lag > cfg.ventana // 5:
        sys.exit(f"❌ --max-lag {cfg.max_lag} es demasiado grande para --ventana {cfg.ventana}: con "
                 f"τ > W/5 quedan menos de 5 diferencias independientes en el rezago más largo "
                 f"y su varianza es ruido. Usa --max-lag ≤ {cfg.ventana // 5}.")
    if not (0.0 < cfg.umbral_mr < 0.5 < cfg.umbral_tr < 1.0):
        sys.exit("❌ Hace falta 0 < --umbral-mr < 0.5 < --umbral-tr < 1.")
    if not (0.0 < cfg.alfa < 0.5):
        sys.exit("❌ --alfa va entre 0 y 0.5.")


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
    "  • La que estaba escrita en la línea 36 de hurst_exponent_deepsek.py hay que darla por\n"
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


def esquema(barra_min: int) -> str:
    """
    [v2] Databento sólo tiene OHLCV de 1 s, 1 min, 1 h y 1 día (más el de fin de sesión).
    Tu descargar() pide "ohlcv-5m", "ohlcv-15m" y "ohlcv-30m", que no existen: con --barra 5
    —el ejemplo de tu propio docstring— la API rechaza la petición. Aquí las barras que no
    son de 1 h se arman con las de 1 min, dentro de cada sesión.
    """
    return "ohlcv-1h" if barra_min % 60 == 0 else "ohlcv-1m"


def dias_calentamiento(cfg: Config) -> int:
    """Días naturales previos a --start para que la primera ventana ya esté llena."""
    sesiones = cfg.ventana * minutos_por_barra(cfg) / MINUTOS_SESION
    return int(math.ceil(sesiones * 7 / 5 * 1.15)) + 7


def obtener_datos(cfg: Config, cliente=None):
    carpeta = _ruta(cfg.cache_dir)
    carpeta.mkdir(parents=True, exist_ok=True)
    inicio = (pd.Timestamp(cfg.start) - pd.Timedelta(days=dias_calentamiento(cfg))
              ).strftime("%Y-%m-%dT%H:%M:%S")
    sch = esquema(cfg.barra_min)
    ruta = carpeta / (_nombre_seguro(cfg.dataset, cfg.symbol, inicio, cfg.end, sch) + ".dbn.zst")
    if ruta.exists() and cfg.usar_cache:
        print(f"📂 Usando caché local: {ruta.name}")
        return db.DBNStore.from_file(ruta)
    cliente = cliente or conectar()
    params = dict(dataset=cfg.dataset, symbols=[cfg.symbol], stype_in="continuous", schema=sch,
                  start=inicio, end=cfg.end)
    costo = cliente.metadata.get_cost(**params)
    print(f"💵 Costo estimado: US$ {costo:,.2f}  ({cfg.symbol}, {sch}, desde {inicio[:10]})")
    if costo > cfg.costo_max_usd:
        sys.exit(f"💰 El costo (US$ {costo:,.2f}) supera tu tope de US$ {cfg.costo_max_usd:,.2f}.\n"
                 f"   Si estás de acuerdo:  --costo-max {math.ceil(costo) + 1}")
    temporal = ruta.with_name(ruta.name + ".parcial")
    temporal.unlink(missing_ok=True)
    print(f"📡 Descargando {cfg.symbol} ({sch}) …")
    cliente.timeseries.get_range(**params, path=temporal)
    temporal.replace(ruta)
    return db.DBNStore.from_file(ruta)


def preparar_barras(tienda, cfg: Config) -> pd.DataFrame:
    """
    OHLCV de un símbolo → barras limpias con sesión de Globex y minuto de sesión.
    La escala se decide por el TIPO de la columna: entera = punto fijo (÷ 1e9); float = tal cual.
    Los rolls se detectan por instrument_id: con stype_in="continuous" la columna `symbol`
    repite el símbolo pedido en todas las filas y nunca cambia en el roll.
    """
    df = tienda.to_df() if hasattr(tienda, "to_df") else tienda
    df = df.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("Los datos no traen índice temporal.")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    for req in ("open", "close"):
        if req not in df.columns:
            raise ValueError(f"Falta la columna {req!r}.")
    escala = "float"
    if pd.api.types.is_integer_dtype(df["close"]):
        for c in ("open", "high", "low", "close"):
            if c in df:
                df[c] = df[c].astype(float) / 1e9
        escala = "punto fijo ÷ 1e9"
    for c in ("open", "close"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
        df.loc[(df[c] <= 0) | (df[c] >= 9.2e9) | ~np.isfinite(df[c]), c] = np.nan
    df["open"] = df["open"].fillna(df["close"])
    df = df.dropna(subset=["close"])
    if "instrument_id" not in df:
        df["instrument_id"] = 0
    df = df[~df.index.duplicated(keep="last")].sort_index()
    ses, minuto = sesion_y_minuto(df.index, cfg.tz_mercado)
    df["sesion"] = ses
    df["minuto"] = minuto
    df.attrs["escala"] = escala
    df.attrs["nativa"] = 60 if esquema(cfg.barra_min) == "ohlcv-1h" else 1
    return df[["open", "close", "instrument_id", "sesion", "minuto"]]


# =============================================================================
# 3. BARRAS DE ANÁLISIS — por sesión de Globex y sin saltos de roll
# =============================================================================
def barras_analisis(b: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """
    Barras de `barra_min` minutos alineadas a la sesión (17:00 CT), con su log-retorno:
      · dentro de la sesión, cierre contra cierre;
      · la primera barra de la sesión incluye el hueco de la pausa o del fin de semana, que
        es un movimiento real del precio;
      · si cambió el instrument_id (roll del .n.0), el salto entre contratos se reemplaza
        por 0: la barra aporta sólo su propio movimiento, apertura contra cierre.
    x = suma acumulada de esos retornos = log-precio continuo sin rolls.

    [v2] Tu script calcula el Hurst y los retornos futuros sobre el precio del continuo con
    sus rolls. En el NQ el roll trimestral es un brinco de ~1 % en una barra de 1 h: un
    retorno de 3-4 σ que entra a la varianza de TODAS las diferencias que lo cruzan y a los
    retornos futuros de las 24 barras previas.
    """
    ses = b["sesion"].to_numpy()
    inst = b["instrument_id"].to_numpy()
    lc, lo = np.log(b["close"].to_numpy()), np.log(b["open"].to_numpy())
    misma_ses = np.r_[False, ses[1:] == ses[:-1]]
    mismo_inst = np.r_[False, inst[1:] == inst[:-1]]
    prev = np.r_[np.nan, lc[:-1]]
    r = np.where(misma_ses & mismo_inst, lc - prev, lc - lo)
    r = r + np.nan_to_num(np.where(~misma_ses & mismo_inst, lo - prev, 0.0))
    r[0] = 0.0
    roll = np.r_[False, ~mismo_inst[1:]]
    nativa = int(b.attrs.get("nativa", 60 if esquema(cfg.barra_min) == "ohlcv-1h" else 1))
    bloque = (np.zeros(len(b), dtype=int) if cfg.barra_min == 1440
              else b["minuto"].to_numpy() // int(cfg.barra_min))
    g = pd.DataFrame({"ses": ses, "bloque": bloque, "r": r, "close": b["close"].to_numpy(),
                      "roll": roll, "fin": b.index + pd.Timedelta(minutes=nativa),
                      "inst": inst})
    A = g.groupby(["ses", "bloque"], sort=True).agg(
        r=("r", "sum"), close=("close", "last"), roll=("roll", "any"), fin=("fin", "last"),
        n=("r", "size"), inst=("inst", "last")).reset_index()
    A = A.set_index("fin").sort_index()
    A.index.name = "fin_utc"
    A["x"] = np.cumsum(A["r"].to_numpy())
    A.attrs["escala"] = b.attrs.get("escala", "float")
    return A


# =============================================================================
# 4. HURST POR VARIANZA DE DIFERENCIAS — rodante, vectorizado
# =============================================================================
def rezagos(cfg: Config) -> np.ndarray:
    """
    Rezagos espaciados en escala LOG entre lag_min y max_lag.

    [v2] Tu script usa τ = 2, 3, …, 49: en el eje log-log 40 de los 48 puntos caen en la
    mitad de arriba (τ ≥ 10), justo donde cada varianza sale de menos diferencias
    independientes. El ajuste lo deciden los rezagos más ruidosos. Medido con fGn de H
    conocido, retornos gaussianos y ventanas de 500 barras: desviación estándar de Ĥ 0.070
    con tus rezagos, 0.045 con 12 rezagos en escala log ponderados y 0.034 si además entra
    τ = 1.
    """
    return np.unique(np.round(np.geomspace(cfg.lag_min, cfg.max_lag, cfg.n_lags)).astype(int))


def pesos_rezagos(lags: np.ndarray, W: int, ponderado: bool) -> np.ndarray:
    """El log de la desviación en el rezago τ sale de ~(W − τ)/τ diferencias independientes."""
    w = (W - lags) / lags if ponderado else np.ones(len(lags))
    return w / w.sum()


def log_std_rodante(x: np.ndarray, W: int, lags: np.ndarray) -> np.ndarray:
    """
    log std(x[s] − x[s − τ]) sobre las diferencias que caben en la ventana de W precios que
    TERMINA en t (inclusive): T × L, NaN mientras no hay W precios. Con sumas acumuladas:
    todas las ventanas en O(T · L).
    """
    x = np.asarray(x, float)
    n = len(x)
    out = np.full((n, len(lags)), np.nan)
    if n < W:
        return out
    t = np.arange(W - 1, n)
    for j, tau in enumerate(lags):
        tau = int(tau)
        d = np.zeros(n)
        d[tau:] = x[tau:] - x[:-tau]
        m = W - tau
        c1 = np.r_[0.0, np.cumsum(d)]
        c2 = np.r_[0.0, np.cumsum(d * d)]
        s1 = c1[t + 1] - c1[t + 1 - m]
        s2 = c2[t + 1] - c2[t + 1 - m]
        var = s2 / m - (s1 / m) ** 2
        out[t, j] = 0.5 * np.log(np.maximum(var, 1e-300))
    return out


def pendiente(Y: np.ndarray, lags: np.ndarray, w: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Pendiente (Ĥ) y R² del ajuste log std = H · log τ + c, fila por fila."""
    X = np.log(lags.astype(float))
    w = w / w.sum()
    xc = X - float(w @ X)
    ym = Y @ w
    yc = Y - ym[:, None]
    b = (yc * (w * xc)).sum(1) / float(w @ (xc * xc))
    res = yc - b[:, None] * xc
    sst = (yc * yc) @ w
    r2 = 1.0 - ((res * res) @ w) / np.where(sst > 0, sst, np.nan)
    return b, r2


def hurst_ventana(x: np.ndarray, lags: np.ndarray, ponderado: bool = True) -> tuple[float, float]:
    """Ĥ y R² de UNA ventana (la usa el diagnóstico)."""
    Y = log_std_rodante(x, len(x), lags)[-1:]
    b, r2 = pendiente(Y, lags, pesos_rezagos(lags, len(x), ponderado))
    return float(b[0]), float(r2[0])


def nula_signos(r: np.ndarray, cfg: Config, lags: np.ndarray, w: np.ndarray,
                n_nula: int | None = None) -> np.ndarray:
    """
    La nula de paseo aleatorio CON LA MISMA VOLATILIDAD: cada camino multiplica cada
    retorno por un signo al azar (+1/−1). Conserva exactamente las magnitudes —agrupamiento
    de volatilidad, colas gruesas, estacionalidad intradía— y destruye cualquier memoria en
    la dirección. Ĥ de esos caminos es lo que da el estimador cuando NO hay nada.

    Los signos se sortean barra por barra en el orden del tiempo: truncar la muestra no
    cambia la nula de las barras anteriores (el filtro no mira al futuro).
    """
    r = np.asarray(r, float)
    n = len(r)
    B = int(n_nula or cfg.n_nula)
    rng = np.random.default_rng(cfg.semilla_nula)
    signos = rng.integers(0, 2, size=(n, B), dtype=np.int8) * 2 - 1
    out = np.empty((B, n), dtype=np.float32)
    for j in range(B):
        xs = np.cumsum(r * signos[:, j])
        out[j] = pendiente(log_std_rodante(xs, cfg.ventana, lags), lags, w)[0]
    return out


@dataclass
class HurstRodante:
    lags: np.ndarray
    H: np.ndarray               # Ĥ tal cual sale del ajuste
    Hc: np.ndarray              # corregido: Ĥ − (mediana de la nula − 0.5)
    r2: np.ndarray
    banda_lo: np.ndarray        # nula al α y al 1 − α, en unidades de Hc
    banda_hi: np.ndarray
    p_tr: np.ndarray            # P(nula ≥ Ĥ): evidencia de persistencia
    p_mr: np.ndarray            # P(nula ≤ Ĥ): evidencia de reversión
    sd_nula: np.ndarray
    base: np.ndarray            # régimen sólo por umbral (lo que hace tu script, ya corregido)
    regimen: np.ndarray         # régimen CONFIRMADO; si no, Random Walk
    confirmado: np.ndarray
    n_nula: int


def clasificar(Hc: np.ndarray, p_tr: np.ndarray, p_mr: np.ndarray, r2: np.ndarray,
               cfg: Config) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Tres regímenes por umbral (Mean-Reverting H < 0.45 · Random Walk · Trending H > 0.55) y
    el filtro de confianza: un régimen sólo se CONFIRMA si además
      · el log-log es una recta (R² ≥ r2_min: un solo exponente describe todas las escalas), y
      · Ĥ está fuera de lo que da un paseo aleatorio con la misma volatilidad
        (p-valor de un lado < α).
    Lo que no se confirma es Random Walk: no hay evidencia de memoria.
    """
    Hc = np.asarray(Hc, float)
    ok = np.isfinite(Hc)
    base = np.full(len(Hc), "—", dtype=object)
    base[ok] = np.where(Hc[ok] > cfg.umbral_tr, TR, np.where(Hc[ok] < cfg.umbral_mr, MR, RW))
    r2_ok = np.nan_to_num(r2, nan=-1.0) >= cfg.r2_min
    conf = (((base == TR) & (np.nan_to_num(p_tr, nan=1.0) < cfg.alfa))
            | ((base == MR) & (np.nan_to_num(p_mr, nan=1.0) < cfg.alfa))) & r2_ok
    reg = np.where(conf, base, np.where(ok, RW, "—")).astype(object)
    return base, reg, conf


def hurst_rodante(x: np.ndarray, r: np.ndarray, cfg: Config, verbose: bool = True) -> HurstRodante:
    lags = rezagos(cfg)
    w = pesos_rezagos(lags, cfg.ventana, cfg.ponderado)
    H, r2 = pendiente(log_std_rodante(x, cfg.ventana, lags), lags, w)
    n = len(x)
    B = int(cfg.n_nula)
    tope = int(4e7 // max(n, 1))
    if B > tope:
        if verbose:
            print(f"⚠ {n:,} barras: la nula baja de {B} a {tope} caminos para no agotar la memoria.")
        B = max(40, tope)
    nula = nula_signos(r, cfg, lags, w, B)
    q_lo, med, q_hi = np.nanquantile(nula, [cfg.alfa, 0.5, 1.0 - cfg.alfa], axis=0)
    ok = np.isfinite(H)
    p_tr = np.full(n, np.nan)
    p_mr = np.full(n, np.nan)
    p_tr[ok] = (1.0 + (nula[:, ok] >= H[ok]).sum(0)) / (B + 1.0)
    p_mr[ok] = (1.0 + (nula[:, ok] <= H[ok]).sum(0)) / (B + 1.0)
    sesgo = med - 0.5
    Hc = H - sesgo
    base, reg, conf = clasificar(Hc, p_tr, p_mr, r2, cfg)
    return HurstRodante(lags, H, Hc, r2, q_lo - sesgo, q_hi - sesgo, p_tr, p_mr,
                        np.nanstd(nula, axis=0), base, reg, conf, B)


# =============================================================================
# 5. OTROS ESTIMADORES — para contrastar la última ventana
# =============================================================================
def _e_rs_anis_lloyd(m: int) -> float:
    """Valor esperado de R/S de m retornos independientes (Anis-Lloyd 1976, ajuste de Peters)."""
    if m <= 340:
        g = math.exp(math.lgamma((m - 1) / 2) - math.lgamma(m / 2)) / math.sqrt(math.pi)
    else:
        g = 1.0 / math.sqrt(m * math.pi / 2)
    i = np.arange(1, m)
    return (m - 0.5) / m * g * float(np.sum(np.sqrt((m - i) / i)))


def rs_clasico(r: np.ndarray) -> dict:
    """
    R/S de Hurst (1951) sobre bloques sin solape, con y sin la corrección de Anis-Lloyd-Peters.
    Sin corregir, el R/S de muestras chicas sale arriba de 0.5 aunque no haya memoria.
    """
    r = np.asarray(r, float)
    r = r[np.isfinite(r)]
    n = len(r)
    tams = np.unique(np.round(np.geomspace(8, max(16, n // 4), 10)).astype(int))
    ms, rs, e = [], [], []
    for m in tams:
        k = n // m
        if k < 2:
            continue
        bl = r[:k * m].reshape(k, m)
        dev = bl - bl.mean(1, keepdims=True)
        Z = np.cumsum(dev, 1)
        R = np.maximum(Z.max(1), 0.0) - np.minimum(Z.min(1), 0.0)
        S = bl.std(1)
        ok = S > 0
        if not ok.any():
            continue
        ms.append(m)
        rs.append(float(np.mean(R[ok] / S[ok])))
        e.append(_e_rs_anis_lloyd(int(m)))
    if len(ms) < 3:
        return {"H_rs": np.nan, "H_al": np.nan, "m": [], "rs": [], "e": []}
    lm = np.log(ms)
    h_rs = float(np.polyfit(lm, np.log(rs), 1)[0])
    h_al = 0.5 + float(np.polyfit(lm, np.log(rs) - np.log(e), 1)[0])
    return {"H_rs": h_rs, "H_al": h_al, "m": np.array(ms), "rs": np.array(rs), "e": np.array(e)}


def dfa(r: np.ndarray) -> dict:
    """Detrended Fluctuation Analysis de orden 1 (Peng et al. 1994): inmune a tendencias lineales."""
    r = np.asarray(r, float)
    r = r[np.isfinite(r)]
    y = np.cumsum(r - r.mean())
    n = len(y)
    tams = np.unique(np.round(np.geomspace(8, max(16, n // 4), 10)).astype(int))
    ss, F = [], []
    for s in tams:
        k = n // s
        if k < 2:
            continue
        seg = y[:k * s].reshape(k, s)
        tc = np.arange(s) - (s - 1) / 2
        segc = seg - seg.mean(1, keepdims=True)
        b = segc @ tc / float(tc @ tc)
        res = segc - b[:, None] * tc
        ss.append(s)
        F.append(float(np.sqrt(np.mean(res * res))))
    if len(ss) < 3:
        return {"H": np.nan, "s": [], "F": []}
    return {"H": float(np.polyfit(np.log(ss), np.log(F), 1)[0]), "s": np.array(ss), "F": np.array(F)}


def razon_varianzas(r: np.ndarray, q: int) -> tuple[float, float]:
    """
    Razón de varianzas de Lo y MacKinlay (1988): VR(q) = var(suma de q retornos) / (q · var(1)),
    con el estadístico z* robusto a heterocedasticidad. Paseo aleatorio: VR = 1. Con memoria
    de Hurst H: VR(q) ≈ q^(2H − 1). Es la versión con prueba estadística de tu "varianza de
    diferencias".
    """
    r = np.asarray(r, float)
    r = r[np.isfinite(r)]
    n = len(r)
    if n < 4 * q or q < 2:
        return np.nan, np.nan
    mu = r.mean()
    d = r - mu
    s_a = float(d @ d) / (n - 1)
    rq = np.convolve(r, np.ones(q), mode="valid")
    m = q * (n - q + 1) * (1.0 - q / n)
    s_c = float(np.sum((rq - q * mu) ** 2)) / m
    vr = s_c / s_a
    d2 = d * d
    den = float(d2.sum()) ** 2
    theta = sum((2.0 * (q - j) / q) ** 2 * n * float(d2[j:] @ d2[:-j]) / den for j in range(1, q))
    return vr, math.sqrt(n) * (vr - 1.0) / math.sqrt(theta) if theta > 0 else np.nan


def acf_fgn(k: np.ndarray, H: float) -> np.ndarray:
    """Autocorrelación teórica de los incrementos de un movimiento browniano fraccional."""
    k = np.abs(np.asarray(k, float))
    return 0.5 * (np.abs(k + 1) ** (2 * H) - 2 * k ** (2 * H) + np.abs(k - 1) ** (2 * H))


def corr_escala_fgn(H: float) -> float:
    """Correlación entre el movimiento de h barras y el de las h siguientes: 2^(2H−1) − 1."""
    return 2.0 ** (2.0 * H - 1.0) - 1.0


def diagnostico_ventana(x: np.ndarray, r: np.ndarray, cfg: Config, t: int, n_nula: int = 400) -> dict:
    """La última ventana, a detalle: el log-log con su banda nula, escala por escala, y otros estimadores."""
    W = cfg.ventana
    lags = rezagos(cfg)
    w = pesos_rezagos(lags, W, cfg.ponderado)
    xw = np.asarray(x[t - W + 1:t + 1], float)
    rw = np.diff(xw)
    Y = log_std_rodante(xw, W, lags)[-1]
    b, r2 = pendiente(Y[None, :], lags, w)
    X = np.log(lags.astype(float))
    c = float(w @ Y) - float(b[0]) * float(w @ X)
    rng = np.random.default_rng(cfg.semilla_nula + 1)
    Yn = np.empty((n_nula, len(lags)))
    Hn = np.empty(n_nula)
    lags_tu = np.arange(2, cfg.max_lag)
    Hn_tu = np.empty(n_nula)
    for j in range(n_nula):
        xs = np.r_[0.0, np.cumsum(rw * rng.choice((-1.0, 1.0), size=len(rw)))]
        Yn[j] = log_std_rodante(xs, W, lags)[-1]
        Hn[j] = pendiente(Yn[j][None, :], lags, w)[0][0]
        Hn_tu[j] = pendiente(log_std_rodante(xs, W, lags_tu)[-1:], lags_tu, np.ones(len(lags_tu)))[0][0]
    # la banda nula en el log-log, centrada en la misma ordenada que el ajuste observado
    Yn_c = Yn - (Yn @ w)[:, None] + float(w @ Y)
    cortos, largos = lags <= 5, lags >= 10
    loc = {}
    for nombre_, m in (("corto", cortos), ("largo", largos)):
        if m.sum() >= 3:
            loc[nombre_] = float(pendiente(Y[None, m], lags[m], pesos_rezagos(lags[m], W, cfg.ponderado))[0][0])
    rs = rs_clasico(rw)
    df_ = dfa(rw)
    vr = {q: razon_varianzas(rw, q) for q in (2, 4, 8, 16)}
    return {"t": t, "lags": lags, "Y": Y, "H": float(b[0]), "r2": float(r2[0]), "c": c,
            "banda": np.quantile(Yn_c, [cfg.alfa, 1 - cfg.alfa], axis=0), "H_nula": Hn,
            "sesgo": float(np.median(Hn) - 0.5), "local": loc, "rs": rs, "dfa": df_, "vr": vr,
            "sesgo_tu": float(np.median(Hn_tu) - 0.5), "sd_tu": float(np.std(Hn_tu)),
            "tu_mr_nula": float(np.mean(Hn_tu < cfg.umbral_mr)),
            "tu_tr_nula": float(np.mean(Hn_tu > cfg.umbral_tr))}


# =============================================================================
# 6. TU SCRIPT, REPLICADO SOBRE LOS MISMOS DATOS
# =============================================================================
def hurst_tu_script(serie: np.ndarray, max_lag: int = 50, min_lags: int = 5) -> tuple[float, float, int]:
    """Réplica fiel de tu hurst_exponent(): τ = 2 … max_lag − 1, np.std, MCO sin ponderar."""
    x = np.asarray(serie, dtype=np.float64)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < max_lag + 10:
        return float("nan"), float("nan"), 0
    lags = np.arange(2, max_lag)
    stds = np.array([np.std(x[lag:] - x[:-lag]) for lag in lags])
    mask = np.isfinite(stds) & (stds > 0)
    if mask.sum() < min_lags:
        return float("nan"), float("nan"), 0
    ll, ls = np.log(lags[mask].astype(float)), np.log(stds[mask])
    A = np.column_stack([ll, np.ones(len(ll))])
    coef, *_ = np.linalg.lstsq(A, ls, rcond=None)
    pred = coef[0] * ll + coef[1]
    ss_res, ss_tot = float(np.sum((ls - pred) ** 2)), float(np.sum((ls - ls.mean()) ** 2))
    return float(coef[0]), (1 - ss_res / ss_tot if ss_tot > 0 else float("nan")), int(mask.sum())


def tu_rodante(A: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """
    Tu rolling_hurst sobre las mismas barras, vectorizado: log del cierre CON rolls, ventana
    que termina en la barra ANTERIOR, τ = 2 … max_lag − 1, MCO; régimen por umbral crudo y
    "utilizable" si R² ≥ r2_min. Da lo mismo que tu función barra por barra (una prueba lo
    verifica) pero en milisegundos.
    """
    lags = np.arange(2, cfg.max_lag)
    y = np.log(A["close"].to_numpy(float))
    H, r2 = pendiente(log_std_rodante(y, cfg.ventana, lags), lags, np.ones(len(lags)))
    H = np.r_[np.nan, H[:-1]]
    r2 = np.r_[np.nan, r2[:-1]]
    reg = np.full(len(H), "RANDOM", dtype=object)
    reg[H < cfg.umbral_mr] = "MEAN_REV"
    reg[H > cfg.umbral_tr] = "TRENDING"
    reg[~np.isfinite(H)] = "—"
    return pd.DataFrame({"H": H, "R2": r2, "regimen": reg,
                         "utilizable": (np.nan_to_num(r2, nan=-1) >= cfg.r2_min) & np.isfinite(H)},
                        index=A.index)


# =============================================================================
# 7. AUDITORÍA — ¿el régimen de HOY dice algo de lo que pasa DESPUÉS?
# =============================================================================
@dataclass
class Auditoria:
    tabla: pd.DataFrame         # etiqueta × régimen × horizonte
    acf: dict                   # régimen → (k, ρ realizada, ρ teórica, pares)
    trans_mec: pd.DataFrame     # régimen de t → régimen de t + 1
    trans_real: pd.DataFrame    # régimen de t → régimen de t + W (ventanas sin solape)
    persist: dict
    duraciones: dict
    curvas: pd.DataFrame        # P&L acumulado (bps) de cada regla
    resumen_estr: pd.DataFrame
    eventos: dict               # régimen → (j, media, error estándar, entradas)
    tu_pares: pd.DataFrame      # tu autocorrelación: pares que no son barras consecutivas


def _desplazado(x: np.ndarray, h: int) -> tuple[np.ndarray, np.ndarray]:
    """(x[t] − x[t−h], x[t+h] − x[t]) con NaN donde no existen."""
    n = len(x)
    pasado, futuro = np.full(n, np.nan), np.full(n, np.nan)
    if 0 < h < n:
        pasado[h:] = x[h:] - x[:-h]
        futuro[:-h] = x[h:] - x[:-h]
    return pasado, futuro


def transiciones(lab: np.ndarray, m: np.ndarray, h: int) -> pd.DataFrame:
    n = len(lab)
    M = np.zeros((3, 3))
    if h < n:
        a, b = lab[:-h], lab[h:]
        ok = m[:-h] & m[h:]
        for i, ri in enumerate(REGIMENES):
            for j, rj in enumerate(REGIMENES):
                M[i, j] = float(np.sum(ok & (a == ri) & (b == rj)))
    fila = M.sum(1, keepdims=True)
    P = np.divide(M, fila, out=np.full_like(M, np.nan), where=fila > 0)
    out = pd.DataFrame(P, index=list(REGIMENES), columns=list(REGIMENES))
    out.attrs["n"] = M.sum(1)
    return out


def rachas(lab: np.ndarray, m: np.ndarray) -> dict:
    out = {k: [] for k in REGIMENES}
    prev, largo = None, 0
    for v, ok in zip(lab, m):
        if ok and v == prev:
            largo += 1
            continue
        if prev in out and largo:
            out[prev].append(largo)
        prev, largo = (v, 1) if ok else (None, 0)
    if prev in out and largo:
        out[prev].append(largo)
    return {k: np.asarray(v, int) for k, v in out.items()}


def auditar(A: pd.DataFrame, hr: HurstRodante, tu: pd.DataFrame, cfg: Config, m: np.ndarray) -> Auditoria:
    """
    [v2] Tu auditar() mide |retorno| futuro por régimen. El Hurst no habla de magnitud sino
    de DIRECCIÓN: si H > 0.5, lo que se movió tiende a seguir; si H < 0.5, a regresar. Aquí
    se mide eso, para cada horizonte h:
        D = signo(movimiento de las h barras previas) × retorno de las h barras siguientes
    D > 0 en Trending y D < 0 en Mean-Reverting es lo que el régimen promete. Con t de
    Newey-West (los retornos de h barras se solapan), tasa de acierto y la correlación entre
    ambos tramos, contra la que implica el H medido: 2^(2H−1) − 1.
    """
    x = A["x"].to_numpy(float)
    r = A["r"].to_numpy(float)
    n = len(x)
    etiquetas = {"módulo": hr.regimen, "sólo umbral": hr.base}
    tu_map = {"MEAN_REV": MR, "RANDOM": RW, "TRENDING": TR}
    tu_lab = np.array([tu_map.get(v, "—") for v in tu["regimen"].to_numpy()], dtype=object)
    etiquetas["tu script"] = tu_lab
    Hs = {"módulo": hr.Hc, "sólo umbral": hr.Hc, "tu script": tu["H"].to_numpy(float)}
    filas = []
    for h in cfg.horizontes:
        pasado, futuro = _desplazado(x, h)
        D = np.sign(pasado) * futuro * 1e4
        fin = np.isfinite(D)
        for et, lab in etiquetas.items():
            grupos = [(reg, lab == reg) for reg in REGIMENES] + [("todas", np.ones(n, bool))]
            for reg, sel in grupos:
                s = m & fin & sel
                k = int(s.sum())
                if et != "módulo" and reg == "todas":
                    continue
                if k < 10:
                    filas.append({"etiqueta": et, "regimen": reg, "h": h, "n": k})
                    continue
                c = float(np.corrcoef(pasado[s], futuro[s])[0, 1])
                Hm = float(np.nanmean(Hs[et][s]))
                filas.append({"etiqueta": et, "regimen": reg, "h": h, "n": k,
                              "D_bps": float(np.mean(D[s])),
                              "t": t_newey_west(D[s], max(1, h - 1)) if k > 30 else np.nan,
                              "acierto": float(np.mean(D[s] > 0)),
                              "corr": c, "H_medio": Hm,
                              "corr_teo": corr_escala_fgn(Hm) if reg != "todas" else np.nan})
    tabla = pd.DataFrame(filas)

    # --- autocorrelación de los retornos FUTUROS, condicionada al régimen de hoy ---
    K = int(cfg.rezagos_acf)
    acf = {}
    lab = hr.regimen
    for reg in REGIMENES:
        base_ = np.flatnonzero(m & (lab == reg))
        ks, rho, teo, pares = [], [], [], []
        Hm = float(np.nanmean(hr.Hc[base_])) if len(base_) else np.nan
        for k in range(1, K + 1):
            t = base_[base_ + 1 + k < n]
            if len(t) < 30:
                continue
            a, b = r[t + 1], r[t + 1 + k]
            ks.append(k)
            rho.append(float(np.corrcoef(a, b)[0, 1]))
            teo.append(float(acf_fgn(np.array([k]), Hm)[0]) if np.isfinite(Hm) else np.nan)
            pares.append(len(t))
        acf[reg] = (np.array(ks), np.array(rho), np.array(teo), np.array(pares))

    # --- persistencia: ¿el H de hoy anticipa el de la PRÓXIMA ventana, sin solape? ---
    W = cfg.ventana
    persist = {}
    for et, Hx in (("módulo", hr.Hc), ("tu script", tu["H"].to_numpy(float))):
        if n > W:
            a, b = Hx[:-W], Hx[W:]
            ok = m[:-W] & np.isfinite(a) & np.isfinite(b)
            persist[et] = (float(np.corrcoef(a[ok], b[ok])[0, 1]) if ok.sum() > 30 else np.nan,
                           int(ok.sum()), a[ok], b[ok])
    trans_mec = transiciones(lab, m, 1)
    trans_real = transiciones(lab, m, W)
    durac = rachas(lab, m)

    # --- la regla operable: seguir en Trending, revertir en Mean-Reverting ---
    k = int(cfg.h_senal)
    pasado_k, _ = _desplazado(x, k)
    sig = np.nan_to_num(np.sign(pasado_k))
    direc = {"módulo": np.where(hr.regimen == TR, 1.0, np.where(hr.regimen == MR, -1.0, 0.0)),
             "sólo umbral": np.where(hr.base == TR, 1.0, np.where(hr.base == MR, -1.0, 0.0)),
             "tu script": np.where(tu_lab == TR, 1.0, np.where(tu_lab == MR, -1.0, 0.0)),
             "siempre momentum": np.ones(n), "siempre reversión": -np.ones(n)}
    r_sig = np.r_[r[1:], np.nan]                                  # retorno de la barra siguiente
    precio = A["close"].to_numpy(float)
    costo = cfg.costo_ticks * tick(cfg.symbol) / precio            # en log-retorno por unidad
    curvas, filas_e = {}, []
    ok_t = m & np.isfinite(r_sig)
    for nombre_, d in direc.items():
        pos = np.where(ok_t, sig * d, 0.0)
        cambio = np.abs(np.diff(np.r_[0.0, pos]))
        pnl = np.where(ok_t, pos * np.nan_to_num(r_sig), 0.0) - costo * cambio
        curvas[nombre_] = np.cumsum(pnl) * 1e4
        v = pnl[ok_t]
        sd = float(np.std(v))
        filas_e.append({"regla": nombre_, "total_bps": float(v.sum() * 1e4),
                        "sharpe": float(np.mean(v) / sd * math.sqrt(barras_por_ano(cfg))) if sd > 0 else np.nan,
                        "t": t_newey_west(v, k), "invertido": float(np.mean(pos[ok_t] != 0)),
                        "operaciones": int(np.sum(cambio[ok_t] > 0))})
    curvas = pd.DataFrame(curvas, index=A.index)

    # --- qué pasa DESPUÉS de entrar a un régimen confirmado ---
    J = 2 * max(cfg.horizontes)
    eventos = {}
    for reg in (TR, MR):
        ent = np.flatnonzero(m & (lab == reg) & (np.concatenate([np.array(["—"], dtype=object), lab[:-1]]) != reg))
        ent = ent[(ent + J < n) & (ent >= k)]
        if len(ent) >= 3:
            s0 = np.sign(x[ent] - x[ent - k])
            cam = np.stack([s0 * (x[ent + j] - x[ent]) * 1e4 for j in range(J + 1)], axis=1)
            eventos[reg] = (np.arange(J + 1), cam.mean(0), cam.std(0, ddof=1) / math.sqrt(len(ent)),
                            len(ent))

    # --- tu autocorrelación: pares de filas filtradas que NO son barras consecutivas ---
    filas_p = []
    ut = tu["utilizable"].to_numpy(bool)
    for reg, tr_ in (("MEAN_REV", MR), ("RANDOM", RW), ("TRENDING", TR)):
        idx = np.flatnonzero(m & ut & (tu["regimen"].to_numpy() == reg))
        if len(idx) < 21:
            continue
        salto = np.diff(idx) > 1
        a1 = float(np.corrcoef(r[idx[1:]], r[idx[:-1]])[0, 1])
        cont = idx[:-1][~salto]
        a2 = float(np.corrcoef(r[cont + 1], r[cont])[0, 1]) if len(cont) > 20 else np.nan
        filas_p.append({"regimen": reg, "pares": len(idx) - 1, "no_consecutivos": float(salto.mean()),
                        "tu_autocorr": a1, "solo_consecutivos": a2})
    return Auditoria(tabla, acf, trans_mec, trans_real, persist, durac, curvas,
                     pd.DataFrame(filas_e), eventos, pd.DataFrame(filas_p))


# =============================================================================
# 8. SIMULADOR — un mercado con memoria CONOCIDA que cambia de régimen
# =============================================================================
def fgn(n: int, H: float, rng: np.random.Generator) -> np.ndarray:
    """Ruido gaussiano fraccional de varianza 1 (Davies-Harte, incrustación circulante exacta)."""
    if n <= 0:
        return np.zeros(0)
    if abs(H - 0.5) < 1e-12:
        return rng.normal(size=n)
    k = np.arange(n + 1, dtype=float)
    g = 0.5 * (np.abs(k + 1) ** (2 * H) - 2 * k ** (2 * H) + np.abs(k - 1) ** (2 * H))
    c = np.r_[g, g[-2:0:-1]]
    M = len(c)
    lam = np.maximum(np.fft.fft(c).real, 0.0)
    Z = rng.normal(size=M) + 1j * rng.normal(size=M)
    return np.fft.fft(np.sqrt(lam / (2 * M)) * Z).real[:n]


def perfil_intradia(minuto: np.ndarray) -> np.ndarray:
    """Volatilidad relativa por minuto de sesión: noche tranquila, apertura de NY agitada."""
    m = np.asarray(minuto)
    p = np.where((m >= 930) & (m < 1335), 1.45, 0.55)
    p = np.where((m >= 930) & (m < 960), 2.2, p)
    return p / math.sqrt(float(np.mean(p ** 2)))


def simular(cfg: Config, n_barras: int | None = None, semilla: int | None = None,
            hs: tuple[float, float, float] | None = None) -> tuple[pd.DataFrame, dict]:
    """
    Barras nativas (1 min u 1 h) cuyo log-precio es ruido gaussiano fraccional por tramos:
    Random Walk (H = 0.50) → Trending (0.65) → Random Walk → Mean-Reverting (0.35) → …, con
    tramos de 540 a 1 260 barras de análisis. Encima: estacionalidad intradía, volatilidad que se agrupa por
    sesión, colas gruesas (t5) y rolls trimestrales con salto de nivel. El fGn es
    autosimilar: al juntar barras nativas en barras de análisis conserva su H.
    """
    rng = np.random.default_rng(cfg.sim_semilla if semilla is None else semilla)
    hs = tuple(hs or cfg.sim_hs)
    T = int(n_barras or cfg.sim_barras)
    nativa = 60 if esquema(cfg.barra_min) == "ohlcv-1h" else 1
    f = max(1, minutos_por_barra(cfg) // nativa)
    por_ses = MINUTOS_SESION // nativa
    S = int(math.ceil(T * f / por_ses)) + 1
    N = S * por_ses
    # --- tramos de régimen (en barras nativas) ---
    etiquetas, H_nat = [], []
    ciclo = (RW, TR, RW, MR)
    k_, total = 0, 0
    while total < N:
        largo = int(cfg.sim_duracion * rng.uniform(0.6, 1.4)) * f
        etiquetas.append((ciclo[k_ % 4], largo))
        total += largo
        k_ += 1
    inc, lab = [], []
    for reg, largo in etiquetas:
        H = {MR: hs[0], RW: hs[1], TR: hs[2]}[reg]
        inc.append(fgn(largo, H, rng))
        lab += [reg] * largo
        H_nat += [H] * largo
    inc = np.concatenate(inc)[:N]
    lab = np.array(lab[:N], dtype=object)
    H_nat = np.array(H_nat[:N])
    # --- volatilidad: intradía × sesión (agrupada) × colas t5 ---
    minuto = np.tile(np.arange(por_ses) * nativa, S)
    h_ses = np.zeros(S)
    for s in range(1, S):
        h_ses[s] = 0.95 * h_ses[s - 1] + 0.2 * rng.normal()
    escala_ses = np.exp(h_ses - 0.5 * np.var(h_ses))
    t5 = 1.0 / np.sqrt(rng.chisquare(5, N) / 5.0) * math.sqrt(3.0 / 5.0)
    sigma = 0.20 / math.sqrt(252.0 * por_ses)
    inc = inc * sigma * perfil_intradia(minuto) * np.repeat(escala_ses, por_ses) * t5
    ef = np.cumsum(inc)
    # --- rolls: salto de nivel al abrir la sesión del roll ---
    nivel = np.zeros(S)
    inst = np.zeros(S, dtype=int)
    salto_tam = 0.01 if raiz(cfg.symbol) in ("NQ", "ES", "MNQ", "MES", "YM", "RTY") else 0.006
    for s in range(int(rng.integers(10, 63)), S, 63):
        nivel[s:] += rng.choice((-1.0, 1.0)) * salto_tam * rng.uniform(0.5, 1.5)
        inst[s:] += 1
    niv = np.repeat(nivel, por_ses)
    p0 = math.log(CATALOGO.get(raiz(cfg.symbol), ("", 0.25, 20000.0))[2])
    close = np.exp(p0 + ef + niv)
    open_ = np.exp(p0 + np.r_[0.0, ef[:-1]] + niv)
    # --- marcas de tiempo: sesiones hábiles que terminan antes de cfg.end ---
    fechas = pd.bdate_range(end=pd.Timestamp(cfg.end).normalize() - pd.Timedelta(days=1), periods=S)
    pared = (np.repeat(np.asarray(fechas, dtype="datetime64[ns]"), por_ses)
             - np.timedelta64(DESFASE_H, "h") + minuto.astype("timedelta64[m]"))
    idx = pd.DatetimeIndex(pared).tz_localize(cfg.tz_mercado, ambiguous="NaT", nonexistent="NaT")
    vivo = ~idx.isna()
    ts = idx[vivo].tz_convert("UTC")
    df = pd.DataFrame({"open": open_[vivo], "close": close[vivo],
                       "instrument_id": 1000 + np.repeat(inst, por_ses)[vivo],
                       "symbol": cfg.symbol}, index=pd.DatetimeIndex(ts, name="ts_event"))
    fin = ts + pd.Timedelta(minutes=nativa)
    verdad = {"ef": pd.Series(ef[vivo], index=fin), "regimen": pd.Series(lab[vivo], index=fin),
              "H": pd.Series(H_nat[vivo], index=fin), "rolls": int(inst[-1]), "hs": hs,
              "tramos": etiquetas}
    return df, verdad


# =============================================================================
# 9. EL CÁLCULO COMPLETO
# =============================================================================
@dataclass
class Resultado:
    cfg: Config
    A: pd.DataFrame
    hr: HurstRodante
    m: np.ndarray               # barras de tu ventana con H válido
    tu: pd.DataFrame
    aud: Auditoria
    diag: dict
    vr_global: dict
    info: dict
    verdad: dict | None = None
    medicion: dict | None = None


def _instante(s: str) -> pd.Timestamp:
    t = pd.Timestamp(s)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def analizar(barras: pd.DataFrame, cfg: Config, verdad: dict | None = None) -> Resultado:
    validar(cfg)
    A = barras_analisis(barras, cfg)
    if len(A) < cfg.ventana + 100:
        sys.exit(f"❌ Sólo hay {len(A)} barras de {etiqueta_barra(cfg)}; hacen falta más de "
                 f"{cfg.ventana + 100} (ventana {cfg.ventana} + 100). Adelanta --start o baja --ventana.")
    x, r = A["x"].to_numpy(float), A["r"].to_numpy(float)
    hr = hurst_rodante(x, r, cfg)
    dentro = (A.index >= _instante(cfg.start)) & (A.index < _instante(cfg.end))
    m = dentro & np.isfinite(hr.H)
    if m.sum() < 100:
        m = np.isfinite(hr.H)
    tu = tu_rodante(A, cfg)
    aud = auditar(A, hr, tu, cfg, m)
    t_ult = int(np.flatnonzero(np.isfinite(hr.H))[-1])
    diag = diagnostico_ventana(x, r, cfg, t_ult)
    rm = r[m]
    vr_global = {q: razon_varianzas(rm, q) for q in (2, 4, 8, 16, 24) if len(rm) > 8 * q}
    info = {"barras": len(A), "sesiones": int(A["ses"].nunique()), "rolls": int(A["roll"].sum()),
            "escala": A.attrs.get("escala", "float"), "nativas": int(barras.shape[0]),
            "esquema": esquema(cfg.barra_min), "en_ventana": int(m.sum())}
    res = Resultado(cfg, A, hr, m, tu, aud, diag, vr_global, info, verdad)
    if verdad is not None:
        res.medicion = medir_contra_verdad(res)
    return res


def _dominante(lab: np.ndarray, W: int) -> tuple[np.ndarray, np.ndarray]:
    """Régimen verdadero que ocupa más barras de la ventana que termina en t, y su pureza."""
    n = len(lab)
    frac = np.full((n, 3), np.nan)
    for j, reg in enumerate(REGIMENES):
        c = np.r_[0.0, np.cumsum(lab == reg)]
        t = np.arange(W - 1, n)
        frac[t, j] = (c[t + 1] - c[t + 1 - W]) / W
    ok = np.isfinite(frac[:, 0])
    dom = np.full(n, "—", dtype=object)
    dom[ok] = np.array(REGIMENES, dtype=object)[np.argmax(frac[ok], 1)]
    return dom, np.nanmax(np.where(np.isfinite(frac), frac, -1), 1)


def medir_contra_verdad(res: Resultado) -> dict:
    v, A, hr, cfg = res.verdad, res.A, res.hr, res.cfg
    out = {}
    ef = v["ef"].reindex(A.index).to_numpy(float)
    x = A["x"].to_numpy(float)
    out["error_precio"] = float(np.nanmax(np.abs((x - x[0]) - (ef - ef[0]))))
    lab = v["regimen"].reindex(A.index).to_numpy(object)
    dom, pureza = _dominante(lab, cfg.ventana)
    Hv = v["H"].reindex(A.index).to_numpy(float)
    c = np.r_[0.0, np.cumsum(Hv)]
    W = cfg.ventana
    H_ven = np.full(len(A), np.nan)
    H_ven[W - 1:] = (c[W:] - c[:-W]) / W
    tu_map = {"MEAN_REV": MR, "RANDOM": RW, "TRENDING": TR}
    tu_lab = np.array([tu_map.get(z, "—") for z in res.tu["regimen"]], dtype=object)
    ev = res.m & (pureza >= 0.8)
    out["ventanas_puras"] = int(ev.sum())
    for et, lb in (("módulo", hr.regimen), ("sólo umbral", hr.base), ("tu script", tu_lab)):
        d = {"exactitud": float(np.mean(lb[ev] == dom[ev])) if ev.any() else np.nan}
        for reg in REGIMENES:
            s = ev & (dom == reg)
            d[f"marca_{reg}"] = {k: float(np.mean(lb[s] == k)) for k in REGIMENES} if s.any() else {}
            q = ev & (lb == reg)
            d[f"precision_{reg}"] = float(np.mean(dom[q] == reg)) if q.sum() > 10 else np.nan
        out[et] = d
    ok = res.m & np.isfinite(H_ven) & np.isfinite(hr.Hc)
    out["corr_H"] = float(np.corrcoef(hr.Hc[ok], H_ven[ok])[0, 1]) if ok.sum() > 30 else np.nan
    okt = ok & np.isfinite(res.tu["H"].to_numpy(float))
    out["corr_H_tu"] = float(np.corrcoef(res.tu["H"].to_numpy(float)[okt], H_ven[okt])[0, 1]) \
        if okt.sum() > 30 else np.nan
    out["rolls_verdad"] = v["rolls"]
    out["rolls_detectados"] = int(A["roll"].sum())
    # --- el costo de medir con una ventana: la etiqueta llega tarde y se va tarde ---
    x = A["x"].to_numpy(float)
    m = res.m
    out["precision_barra"] = {k: float(np.mean(lab[m & (hr.regimen == k)] == k))
                              if (m & (hr.regimen == k)).sum() > 10 else np.nan for k in (TR, MR)}
    Dv = {}
    for h in cfg.horizontes:
        pa, fu = _desplazado(x, h)
        D = np.sign(pa) * fu * 1e4
        for k in (TR, MR):
            for nm, lb in (("verdad", lab), ("módulo", hr.regimen)):
                s = m & (lb == k) & np.isfinite(D)
                Dv[(nm, k, h)] = ((float(np.mean(D[s])), t_newey_west(D[s], max(1, h - 1)))
                                  if s.sum() > 30 else (np.nan, np.nan))
    out["D"] = Dv
    entra, sale = {TR: [], MR: []}, {TR: [], MR: []}
    n = len(lab)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and lab[j + 1] == lab[i]:
            j += 1
        k = lab[i]
        if k in (TR, MR) and m[i:j + 1].any():
            dentro = np.flatnonzero(hr.regimen[i:j + 1] == k)
            if len(dentro):
                entra[k].append(int(dentro[0]))
            despues = np.flatnonzero(hr.regimen[j + 1:] != k)
            if hr.regimen[j] == k and len(despues):
                sale[k].append(int(despues[0]) + 1)
        i = j + 1
    out["retraso"] = {k: (float(np.median(entra[k])) if entra[k] else np.nan,
                          float(np.median(sale[k])) if sale[k] else np.nan, len(entra[k]))
                      for k in (TR, MR)}
    return out


# =============================================================================
# 10. REPORTES
# =============================================================================
CORTO = {MR: "MR", RW: "RW", TR: "TR"}


def _hora(res: Resultado, i: int) -> str:
    t = res.A.index[i]
    return (f"{t.tz_convert(res.cfg.tz_mercado):%Y-%m-%d %H:%M} CT / "
            f"{t.tz_convert(res.cfg.tz_local):%H:%M} CDMX")


def _racha_actual(lab: np.ndarray, i: int) -> int:
    j = i
    while j > 0 and lab[j - 1] == lab[i]:
        j -= 1
    return i - j + 1


def reporte_datos(res: Resultado) -> None:
    cfg, info, hr = res.cfg, res.info, res.hr
    _titulo("1 · DATOS")
    i0, i1 = np.flatnonzero(res.m)[[0, -1]]
    print(f"  {cfg.symbol} ({nombre(cfg.symbol)}) · barras de {etiqueta_barra(cfg)} alineadas a la sesión "
          f"de Globex (17:00 CT) · {info['esquema']} · precios: {info['escala']}")
    print(f"  {info['barras']:,} barras en {info['sesiones']} sesiones · {info['rolls']} roll(s) del "
          f"continuo quitado(s) · tu ventana: {info['en_ventana']:,} barras con H")
    print(f"      de {_hora(res, i0)}  a  {_hora(res, i1)}")
    ses = cfg.ventana * minutos_por_barra(cfg) / MINUTOS_SESION
    print(f"  Hurst: ventana de {cfg.ventana} barras (≈ {ses:.0f} sesiones) · rezagos "
          f"{', '.join(str(int(x)) for x in hr.lags)} (escala log) · "
          f"{'ponderado por (W − τ)/τ' if cfg.ponderado else 'MCO sin ponderar'}")
    print(f"  Filtro de confianza: R² ≥ {cfg.r2_min} y p < {cfg.alfa} contra {hr.n_nula} caminos con "
          f"signos al azar · umbrales H < {cfg.umbral_mr} / H > {cfg.umbral_tr}")


def reporte_tu_script(res: Resultado) -> None:
    cfg, tu, m, hr = res.cfg, res.tu, res.m, res.hr
    _titulo("2 · TU SCRIPT CONTRA EL MÓDULO, SOBRE LOS MISMOS DATOS")
    Ht = tu["H"].to_numpy(float)[m]
    Ht = Ht[np.isfinite(Ht)]
    r2t = tu["R2"].to_numpy(float)[m]
    print(f"  Tu H (τ = 2…{cfg.max_lag - 1}, MCO, con rolls): media {np.mean(Ht):.3f} · "
          f"desviación {np.std(Ht):.3f}")
    print(f"  Su R² ≥ {cfg.r2_min} en el {np.mean(r2t[np.isfinite(r2t)] >= cfg.r2_min):.1%} de las ventanas: "
          "el filtro casi no filtra.")
    print("  El R² mide que el log-log sea una recta, no que H sea distinto de 0.5: un paseo aleatorio")
    print("  también da una recta, de pendiente 0.5.")
    d = res.diag
    print("  Tu estimador en la última ventana si NO hubiera memoria (400 caminos con signos al azar y")
    print(f"  la misma volatilidad): Ĥ mediano {0.5 + d['sesgo_tu']:.3f} · desviación {d['sd_tu']:.3f}. "
          f"Tu regla marcaría")
    print(f"  MEAN_REV el {d['tu_mr_nula']:.0%} y TRENDING el {d['tu_tr_nula']:.0%} de las veces: tus umbrales "
          "fijos no saben cuánto")
    print("  ruido tiene H en una ventana de este tamaño, ni que el estimador está sesgado hacia abajo.")
    print()
    print("  % del tiempo en cada régimen:")
    print("      " + " " * 28 + "".join(f"{k:>7s}" for k in ("MR", "RW", "TR")))
    tl = tu["regimen"].to_numpy()[m]
    print("      " + "tu script (umbral crudo)".ljust(28) + "".join(
        _pct(np.mean(tl == k), 1, 7) for k in ("MEAN_REV", "RANDOM", "TRENDING")))
    for et, lab in (("módulo, umbral corregido", hr.base), ("módulo, confirmado", hr.regimen)):
        print("      " + et.ljust(28) + "".join(_pct(np.mean(lab[m] == k), 1, 7) for k in REGIMENES))
    print(f"  Sin memoria, el confirmado marcaría ≈ {2 * cfg.alfa:.0%} del tiempo ({cfg.alfa:.0%} por lado) y "
          f"tu regla ≈ {d['tu_mr_nula'] + d['tu_tr_nula']:.0%}.")
    tp = res.aud.tu_pares
    if len(tp):
        print()
        print("  Tu autocorrelación por régimen: sub['ret'].autocorr() empareja FILAS del filtro, no barras")
        print("  consecutivas: cada vez que el régimen se interrumpe junta dos barras lejanas, de tramos")
        print("  distintos. Aquí son pocos pares; con regímenes que cambian seguido, son muchos:")
        for _, f in tp.iterrows():
            print(f"      {f['regimen']:<9s} {f['pares']:6,d} pares · {f['no_consecutivos']:5.1%} no consecutivos · "
                  f"tuya {f['tu_autocorr']:+.3f} · sólo consecutivos {f['solo_consecutivos']:+.3f}")
    rolls = int(res.A["roll"].sum())
    if rolls:
        print(f"  Rolls: {rolls} salto(s) del continuo dentro de los datos. Tu script los deja en el precio;")
        print("  aquí se quitan (sección 1).")


def reporte_estimacion(res: Resultado) -> None:
    cfg, d, hr = res.cfg, res.diag, res.hr
    t = d["t"]
    _titulo(f"3 · HURST DE LA ÚLTIMA VENTANA (termina {_hora(res, t)})")
    print(f"  Ĥ por varianza de diferencias      {d['H']:.3f}     R² {d['r2']:.4f}")
    print(f"  sesgo del estimador (nula)         {d['H'] - hr.Hc[t]:+.3f}  →  H corregido {hr.Hc[t]:.3f}")
    print(f"  paseo aleatorio con esta volatilidad: {1 - 2 * cfg.alfa:.0%} entre {hr.banda_lo[t]:.3f} y "
          f"{hr.banda_hi[t]:.3f}  (desviación {hr.sd_nula[t]:.3f})")
    print(f"  p-valor  persistencia {hr.p_tr[t]:.3f} · reversión {hr.p_mr[t]:.3f}")
    loc = d["local"]
    if loc:
        print("  escala por escala (sin corregir): " + " · ".join(
            f"{'τ ≤ 5' if k == 'corto' else 'τ ≥ 10'}: {v:.3f}" for k, v in loc.items()))
    print(f"  otros estimadores (sin corregir): R/S clásico {d['rs']['H_rs']:.3f} · R/S con corrección de "
          f"Anis-Lloyd {d['rs']['H_al']:.3f} · DFA {d['dfa']['H']:.3f}")
    print("  razón de varianzas (Lo-MacKinlay):  " + " · ".join(
        f"VR({q}) {v[0]:.3f} (z {v[1]:+.2f})" for q, v in d["vr"].items() if np.isfinite(v[0])))
    lab = hr.regimen
    reg = lab[t]
    extra = "" if hr.confirmado[t] or hr.base[t] == RW else f"  ({hr.base[t]} por umbral, sin confianza)"
    print()
    print(f"  RÉGIMEN HOY: {reg.upper()}{extra} · desde hace {_racha_actual(lab, t)} barras")


def reporte_continuo(res: Resultado) -> None:
    cfg, hr, m, aud = res.cfg, res.hr, res.m, res.aud
    _titulo("4 · EVALUACIÓN CONTINUA (una ventana por barra) Y FILTRO DE CONFIANZA")
    Hc = hr.Hc[m]
    print(f"  H corregido: media {np.mean(Hc):.3f} · percentiles 5/50/95: "
          f"{np.percentile(Hc, 5):.3f} / {np.percentile(Hc, 50):.3f} / {np.percentile(Hc, 95):.3f}")
    arriba = np.mean(hr.Hc[m] > hr.banda_hi[m])
    abajo = np.mean(hr.Hc[m] < hr.banda_lo[m])
    print(f"  Fuera de la banda del paseo aleatorio: {arriba:.1%} arriba · {abajo:.1%} abajo "
          f"(sin memoria se esperaría {cfg.alfa:.0%} en cada lado)")
    r2 = hr.r2[m]
    print(f"  R² ≥ {cfg.r2_min}: {np.mean(r2 >= cfg.r2_min):.1%} de las ventanas · R² mediano {np.median(r2):.4f}")
    base_no_rw = (hr.base[m] != RW)
    print(f"  Regímenes por umbral que el filtro NO confirma: "
          f"{np.mean(~hr.confirmado[m][base_no_rw]):.1%}" if base_no_rw.any() else "")
    print()
    print("  Duración de cada régimen confirmado (barras seguidas): mediana · máxima · rachas")
    for reg in REGIMENES:
        d = aud.duraciones[reg]
        if len(d):
            print(f"      {reg:<15s}{np.median(d):8.0f}{np.max(d):9d}{len(d):8d}")
    for titulo, T in ((f"Transiciones de una barra a la siguiente (mecánicas: las ventanas comparten "
                       f"{cfg.ventana - 1} de {cfg.ventana} barras)", aud.trans_mec),
                      (f"Transiciones a {cfg.ventana} barras (ventanas SIN solape: la persistencia real)",
                       aud.trans_real)):
        print()
        print(f"  {titulo}")
        print("      " + "de / a".ljust(17) + "".join(f"{CORTO[k]:>8s}" for k in REGIMENES) + "   barras")
        for i, reg in enumerate(REGIMENES):
            print(f"      {reg:<17s}" + "".join(_pct(v, 1, 7) for v in T.loc[reg]) +
                  f"{int(T.attrs['n'][i]):8,d}")
    vr = res.vr_global
    if vr:
        print()
        print("  Toda tu ventana, razón de varianzas de Lo-MacKinlay (z* robusto; |z| > 1.96 = no es paseo aleatorio):")
        print("      " + " · ".join(f"VR({q}) {v[0]:.3f} (z {v[1]:+.2f})" for q, v in vr.items()))


def reporte_auditoria(res: Resultado) -> None:
    cfg, aud = res.cfg, res.aud
    _titulo("5 · AUDITORÍA — lo que pasa DESPUÉS de cada etiqueta")
    print("  D = signo(movimiento de las h barras previas) × retorno de las h siguientes, en bps.")
    print("  Trending promete D > 0; Mean-Reverting, D < 0. t de Newey-West; |t| < 2 es ruido.")
    tb = aud.tabla
    hs = list(cfg.horizontes)
    for et in ("módulo", "sólo umbral", "tu script"):
        print()
        print(f"  {et.upper():<22s}" + "".join(f"{'h = ' + str(h):>18s}" for h in hs) + f"{'barras':>10s}")
        regs = list(REGIMENES) + (["todas"] if et == "módulo" else [])
        for reg in regs:
            celdas = []
            for h in hs:
                f = tb[(tb.etiqueta == et) & (tb.regimen == reg) & (tb.h == h)]
                if f.empty or not np.isfinite(f["D_bps"].iloc[0] if "D_bps" in f else np.nan):
                    celdas.append(f"{'—':>22s}")
                    continue
                f = f.iloc[0]
                celdas.append(f"{f['D_bps']:+7.2f} (t{f['t']:+5.2f})".rjust(18))
            f1 = tb[(tb.etiqueta == et) & (tb.regimen == reg) & (tb.h == hs[0])]
            n1 = int(f1["n"].iloc[0]) if len(f1) else 0
            print(f"      {reg:<16s}" + "".join(celdas) + f"{n1:10,d}")
    f = tb[(tb.etiqueta == "módulo") & tb.regimen.isin(REGIMENES)].dropna(subset=["corr"])
    if len(f):
        print()
        print("  Correlación entre el movimiento de h barras y el de las h siguientes: real / la que implica H")
        for reg in REGIMENES:
            g = f[f.regimen == reg]
            if len(g):
                print(f"      {reg:<16s}" + "   ".join(
                    f"h={int(z.h)}: {z.corr:+.3f} / {z.corr_teo:+.3f}" for z in g.itertuples()))
    print()
    print("  Autocorrelación de los retornos de 1 barra DESPUÉS de la etiqueta (rezago 1):")
    for reg, (k, rho, teo, pares) in aud.acf.items():
        if len(k):
            print(f"      {reg:<16s} real {rho[0]:+.4f} · implícita por H {teo[0]:+.4f} · "
                  f"{int(pares[0]):,} pares (banda ±{1.96 / math.sqrt(pares[0]):.4f})")
    for et, (c, n, *_r) in aud.persist.items():
        print(f"  Persistencia de H ({et}): corr(H de hoy, H de la ventana siguiente sin solape) = {c:+.3f} ({n:,} pares)")
    print()
    print(f"  Regla operable: posición = signo del movimiento de {cfg.h_senal} barras × (+1 Trending, −1 "
          f"Mean-Reverting, 0 Random Walk);")
    print(f"  se mantiene 1 barra; costo {cfg.costo_ticks:g} tick por unidad operada.")
    print(f"      {'regla':<20s}{'total bps':>11s}{'Sharpe':>9s}{'t':>8s}{'invertido':>11s}{'operaciones':>13s}")
    for _, f in aud.resumen_estr.iterrows():
        print(f"      {f['regla']:<20s}{f['total_bps']:11.1f}{f['sharpe']:9.2f}{f['t']:8.2f}"
              f"{f['invertido']:10.1%}{int(f['operaciones']):13,d}")
    sig = tb[(tb.etiqueta == "módulo") & tb.regimen.isin((MR, TR)) & (tb["t"].abs() >= 2)] \
        if "t" in tb else tb.iloc[:0]
    print()
    if sig.empty:
        print("  CONCLUSIÓN: en estos datos ningún régimen confirmado anticipa la dirección con |t| ≥ 2.")
        print("  El Hurst describe la ventana pasada; no hay evidencia de que su memoria siga después.")
    else:
        bien = sig[((sig.regimen == TR) & (sig.D_bps > 0)) | ((sig.regimen == MR) & (sig.D_bps < 0))]
        print(f"  CONCLUSIÓN: {len(bien)} de {len(sig)} celdas con |t| ≥ 2 van en la dirección que promete "
              "el régimen.")


def reporte_verdad(res: Resultado) -> None:
    v = res.medicion
    if not v:
        return
    _titulo("6 · CONTRA LA VERDAD (sólo en simulación)")
    print(f"  Log-precio sin rolls contra el verdadero: error máximo {v['error_precio']:.1e} · rolls "
          f"{v['rolls_detectados']} de {v['rolls_verdad']}")
    print(f"  Ventanas con un régimen verdadero que ocupa ≥ 80 % de la ventana: {v['ventanas_puras']:,}")
    print(f"  {'':24s}{'exactitud':>10s}   {'marca TR en RW':>14s}{'marca MR en RW':>15s}"
          f"{'ve TR en TR':>12s}{'ve MR en MR':>12s}")
    for et in ("módulo", "sólo umbral", "tu script"):
        d = v[et]
        rw = d.get(f"marca_{RW}", {})
        print(f"  {et:<24s}{_pct(d['exactitud'], 1, 9)}   {_pct(rw.get(TR), 1, 13)}{_pct(rw.get(MR), 1, 14)}"
              f"{_pct(d.get(f'marca_{TR}', {}).get(TR), 1, 11)}{_pct(d.get(f'marca_{MR}', {}).get(MR), 1, 11)}")
    print(f"  Correlación con el H verdadero promedio de la ventana: módulo {v['corr_H']:+.3f} · "
          f"tu script {v['corr_H_tu']:+.3f}")
    print()
    print(f"  El costo de medir con una ventana de {res.cfg.ventana} barras:")
    for k in (TR, MR):
        ent, sal, nb = v["retraso"][k]
        print(f"      {k:<15s} se confirma {ent:.0f} barras después de que empieza el tramo y sigue "
              f"{sal:.0f} después de que acaba")
        print(f"      {'':15s} ({nb} tramo{'s' if nb != 1 else ''}) · el {v['precision_barra'][k]:.0%} de "
              "las barras marcadas está de verdad en el tramo")
    print("  D (bps, t) con la etiqueta VERDADERA contra la del módulo:")
    for k in (TR, MR):
        print(f"      {k:<15s}" + "   ".join(
            f"h={h}: {v['D'][('verdad', k, h)][0]:+.1f} ({v['D'][('verdad', k, h)][1]:+.1f}) vs "
            f"{v['D'][('módulo', k, h)][0]:+.1f} ({v['D'][('módulo', k, h)][1]:+.1f})"
            for h in res.cfg.horizontes[:3]))


# =============================================================================
# 11. DASHBOARD VISUAL DE TRANSICIÓN + AUDITORÍA
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


COLOR_REG = {TR: C["s1"], MR: C["baja"], RW: C["neutro"]}


def _eje_barras(ax, idx: pd.DatetimeIndex, tz: str, n_ticks: int = 8) -> None:
    """Eje x por número de barra (sin huecos de noches y fines de semana) con fechas de CDMX."""
    n = len(idx)
    if n < 2:
        return
    pos = np.unique(np.linspace(0, n - 1, n_ticks).round().astype(int))
    loc = idx[pos].tz_convert(tz)
    span = (idx[-1] - idx[0]).days
    fmt = "%d-%b\n%H:%M" if span <= 10 else ("%d-%b" if span <= 120 else "%b\n%Y")
    ax.set_xticks(pos)
    ax.set_xticklabels([t.strftime(fmt) for t in loc], fontsize=8)


def _sombrear(ax, lab: np.ndarray, alpha: float = 0.18) -> None:
    ini = 0
    for i in range(1, len(lab) + 1):
        if i == len(lab) or lab[i] != lab[ini]:
            if lab[ini] in (TR, MR):
                ax.axvspan(ini - 0.5, i - 0.5, color=COLOR_REG[lab[ini]], alpha=alpha, linewidth=0, zorder=0)
            ini = i


def _heatmap_transicion(ax, T: pd.DataFrame, titulo: str) -> None:
    _estilo(ax, titulo)
    ax.grid(False)
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("azul", [C["fondo"]] + RAMPA_AZUL[2:])
    ax.imshow(T.to_numpy(float), cmap=cmap, vmin=0, vmax=1, aspect="auto")
    for i in range(3):
        for j in range(3):
            v = T.iloc[i, j]
            if np.isfinite(v):
                ax.text(j, i, f"{v:.0%}", ha="center", va="center", fontsize=10,
                        color="#ffffff" if v > 0.6 else C["tinta"])
    ax.set_xticks(range(3))
    ax.set_xticklabels([f"→ {CORTO[k]}" for k in REGIMENES], fontsize=9)
    ax.set_yticks(range(3))
    ax.set_yticklabels([f"{CORTO[k]}  (n {int(n):,})" for k, n in zip(REGIMENES, T.attrs["n"])], fontsize=8.5)


def tablero_transicion(res: Resultado, plt, ruta: Path):
    cfg, A, hr, aud, m = res.cfg, res.A, res.hr, res.aud, res.m
    idx = np.flatnonzero(m)
    i0, i1 = idx[0], idx[-1] + 1
    sl = slice(i0, i1)
    pos = np.arange(i1 - i0)
    fechas = A.index[sl]
    fig = plt.figure(figsize=(19, 16))
    fig.patch.set_facecolor(C["fondo"])
    gs = fig.add_gridspec(4, 3, height_ratios=[1.45, 1.25, 0.8, 1.35], hspace=0.38, wspace=0.34,
                          bottom=0.05, top=0.94)
    a1 = fig.add_subplot(gs[0, :])
    a2 = fig.add_subplot(gs[1, :], sharex=a1)
    a3 = fig.add_subplot(gs[2, :], sharex=a1)
    a4, a5, a6 = (fig.add_subplot(gs[3, j]) for j in range(3))
    t = i1 - 1
    reg = hr.regimen[t]
    fig.suptitle(f"Hurst · {cfg.symbol} ({nombre(cfg.symbol)}) · barras de {etiqueta_barra(cfg)} · hoy: "
                 f"{reg} · H {hr.Hc[t]:.3f} (paseo aleatorio {hr.banda_lo[t]:.2f}–{hr.banda_hi[t]:.2f})",
                 x=0.01, ha="left", color=C["tinta"], fontsize=12.5)
    lab = hr.regimen[sl]

    _estilo(a1, "Precio con el régimen CONFIRMADO de fondo")
    _sombrear(a1, lab)
    a1.plot(pos, A["close"].to_numpy()[sl], color=C["tinta"], linewidth=0.9, zorder=3)
    from matplotlib.patches import Patch
    a1.legend(handles=[Patch(facecolor=COLOR_REG[TR], alpha=0.35, label=f"Trending (H > {cfg.umbral_tr}, confirmado)"),
                       Patch(facecolor=COLOR_REG[MR], alpha=0.35, label=f"Mean-Reverting (H < {cfg.umbral_mr}, confirmado)"),
                       Patch(facecolor=C["fondo"], edgecolor=C["eje"], label="Random Walk / sin confianza")],
              loc="upper left", fontsize=8, frameon=True, facecolor=C["fondo"], edgecolor="none",
              framealpha=0.9, labelcolor=C["tinta2"], ncol=3)
    a1.set_ylabel("precio", color=C["tinta2"], fontsize=9)

    _estilo(a2, "H corregido por sesgo, contra la banda de un paseo aleatorio con la MISMA volatilidad")
    Hc, lo, hi = hr.Hc[sl], hr.banda_lo[sl], hr.banda_hi[sl]
    a2.fill_between(pos, lo, hi, color=C["neutro"], alpha=0.55, linewidth=0,
                    label=f"paseo aleatorio, {1 - 2 * cfg.alfa:.0%}")
    a2.fill_between(pos, hi, Hc, where=Hc > hi, color=COLOR_REG[TR], alpha=0.35, linewidth=0)
    a2.fill_between(pos, lo, Hc, where=Hc < lo, color=COLOR_REG[MR], alpha=0.35, linewidth=0)
    a2.plot(pos, Hc, color=C["tinta"], linewidth=0.9, label="H corregido")
    a2.axhline(cfg.umbral_tr, color=COLOR_REG[TR], linestyle="--", linewidth=1.1, label=f"umbral {cfg.umbral_tr}")
    a2.axhline(cfg.umbral_mr, color=COLOR_REG[MR], linestyle="--", linewidth=1.1, label=f"umbral {cfg.umbral_mr}")
    a2.axhline(0.5, color=C["tenue"], linestyle=":", linewidth=0.9)
    tu = res.tu["H"].to_numpy(float)[sl]
    a2.plot(pos, tu, color=C["s4"], linewidth=0.7, alpha=0.8, label="tu H (sin corregir, con rolls)")
    lo_y = np.nanmin(np.r_[Hc, lo, tu]) - 0.02
    hi_y = np.nanmax(np.r_[Hc, hi, tu]) + 0.06
    a2.set_ylim(lo_y, hi_y)
    a2.set_ylabel("H", color=C["tinta2"], fontsize=9)
    _leyenda(a2, ncol=5, frameon=True, facecolor=C["fondo"], edgecolor="none", framealpha=0.9)

    _estilo(a3, "Filtro de confianza: p-valor contra el paseo aleatorio (izq.) y R² del log-log (der.)")
    p = np.where(Hc >= 0.5, hr.p_tr[sl], hr.p_mr[sl])
    a3.plot(pos, p, color=C["s7"], linewidth=0.8, label="p-valor del lado de H")
    a3.axhline(cfg.alfa, color=C["s7"], linestyle="--", linewidth=1.0, label=f"α = {cfg.alfa}")
    a3.set_yscale("log")
    a3.set_ylim(max(0.5 / hr.n_nula, 1e-3), 1.05)
    from matplotlib.ticker import FuncFormatter, NullFormatter
    a3.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    a3.yaxis.set_minor_formatter(NullFormatter())
    a3.set_ylabel("p (log)", color=C["s7"], fontsize=9)
    b3 = a3.twinx()
    b3.plot(pos, hr.r2[sl], color=C["s3"], linewidth=0.8)
    b3.axhline(cfg.r2_min, color=C["s3"], linestyle="--", linewidth=1.0)
    b3.set_ylim(min(cfg.r2_min - 0.02, np.nanmin(hr.r2[sl]) - 0.005), 1.002)
    b3.set_ylabel(f"R² (mínimo {cfg.r2_min})", color=C["s3"], fontsize=9)
    b3.tick_params(colors=C["s3"], labelsize=8)
    for lado in ("top", "left", "bottom"):
        b3.spines[lado].set_visible(False)
    b3.spines["right"].set_color(C["eje"])
    _leyenda(a3, ncol=2, loc="lower left", frameon=True, facecolor=C["fondo"], edgecolor="none",
             framealpha=0.9)
    for ax in (a1, a2):
        ax.tick_params(labelbottom=False)
    _eje_barras(a3, fechas, cfg.tz_local)
    a3.set_xlim(-1, len(pos))

    _heatmap_transicion(a4, aud.trans_real, f"Transición a {cfg.ventana} barras (sin solape)")

    _estilo(a5, "Cuánto dura cada régimen confirmado (· = rachas)")
    datos = [aud.duraciones[k] for k in REGIMENES]
    presentes = [k for k, d in zip(REGIMENES, datos) if len(d)]
    if presentes:
        kw = dict(widths=0.55, patch_artist=True, showfliers=True,
                  flierprops=dict(marker=".", markersize=3, markeredgecolor=C["tenue"]),
                  medianprops=dict(color=C["tinta"], linewidth=1.3))
        datos_ = [aud.duraciones[k] for k in presentes]
        try:
            bp = a5.boxplot(datos_, orientation="horizontal", **kw)
        except TypeError:                                  # matplotlib < 3.10
            bp = a5.boxplot(datos_, vert=False, **kw)
        for caja, k in zip(bp["boxes"], presentes):
            caja.set_facecolor(COLOR_REG[k])
            caja.set_alpha(0.55)
            caja.set_edgecolor(C["tinta2"])
        a5.set_yticks(range(1, len(presentes) + 1))
        a5.set_yticklabels([f"{CORTO[k]} · {len(aud.duraciones[k])}" for k in presentes], fontsize=8.5)
        a5.set_xscale("log")
        from matplotlib.ticker import FuncFormatter as _FF
        a5.xaxis.set_major_formatter(_FF(lambda v, _: f"{v:g}"))
    a5.set_xlabel("barras seguidas (log)", color=C["tinta2"], fontsize=9)

    _estilo(a6, f"Después de ENTRAR: signo({cfg.h_senal} barras previas) × retorno")
    for k in (TR, MR):
        if k in aud.eventos:
            j, med, se, ne = aud.eventos[k]
            a6.plot(j, med, color=COLOR_REG[k], linewidth=1.5, label=f"{k} ({ne} entradas)")
            a6.fill_between(j, med - 1.96 * se, med + 1.96 * se, color=COLOR_REG[k], alpha=0.15, linewidth=0)
    a6.axhline(0, color=C["eje"], linewidth=0.9)
    a6.set_xlabel("barras después de entrar", color=C["tinta2"], fontsize=9)
    a6.set_ylabel("bps a favor del momentum", color=C["tinta2"], fontsize=9)
    if aud.eventos:
        _leyenda(a6, loc="upper left")
    else:
        a6.text(0.5, 0.5, "sin entradas suficientes", transform=a6.transAxes, ha="center",
                color=C["tenue"], fontsize=9)
    fig.text(0.008, 0.012, f"{IDENTIFICADOR} · ventana {cfg.ventana} barras · rezagos {int(hr.lags[0])}–"
             f"{int(hr.lags[-1])} (log) · nula = {hr.n_nula} caminos con signos al azar · fechas en CDMX",
             color=C["tenue"], fontsize=7.5)
    fig.savefig(ruta, dpi=120, facecolor=C["fondo"], bbox_inches="tight")
    return fig


def tablero_auditoria(res: Resultado, plt, ruta: Path):
    cfg, aud, d, hr = res.cfg, res.aud, res.diag, res.hr
    fig = plt.figure(figsize=(19, 15))
    fig.patch.set_facecolor(C["fondo"])
    gs = fig.add_gridspec(3, 3, hspace=0.42, wspace=0.36, bottom=0.05, top=0.93)
    ax = [[fig.add_subplot(gs[i, j]) for j in range(3)] for i in range(2)]
    b7 = fig.add_subplot(gs[2, 0])
    b8 = fig.add_subplot(gs[2, 1:])
    (b1, b2, b3), (b4, b5, b6) = ax
    fig.suptitle(f"Hurst · auditoría y estimación · {cfg.symbol} · barras de {etiqueta_barra(cfg)}",
                 x=0.01, ha="left", color=C["tinta"], fontsize=12.5)

    # --- 1 log-log de la última ventana ---
    lags, Y = d["lags"], d["Y"]
    X = np.log(lags.astype(float))
    _estilo(b1, "Última ventana: log std(Δτ) contra log τ · pendiente = H")
    b1.fill_between(lags, np.exp(d["banda"][0]), np.exp(d["banda"][1]), color=C["neutro"], alpha=0.6,
                    linewidth=0, label=f"paseo aleatorio {1 - 2 * cfg.alfa:.0%}")
    b1.plot(lags, np.exp(Y), "o", color=C["tinta"], markersize=5, label="observado")
    b1.plot(lags, np.exp(d["c"] + d["H"] * X), color=C["s1"], linewidth=1.3,
            label=f"ajuste: Ĥ = {d['H']:.3f} · R² {d['r2']:.3f}")
    b1.plot(lags, np.exp(d["c"] + 0.5 * X - 0.5 * float(np.average(X)) + d["H"] * float(np.average(X))),
            color=C["tenue"], linestyle=":", linewidth=1.0, label="pendiente 0.5")
    b1.set_xscale("log")
    b1.set_yscale("log")
    from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter
    for eje, fmt in ((b1.xaxis, lambda v, _: f"{v:g}"), (b1.yaxis, lambda v, _: f"{v * 1e4:.3g}")):
        eje.set_major_locator(LogLocator(base=10, subs=(1.0, 2.0, 5.0)))
        eje.set_major_formatter(FuncFormatter(fmt))
        eje.set_minor_formatter(NullFormatter())
    b1.set_xlabel("rezago τ (barras, log)", color=C["tinta2"], fontsize=9)
    b1.set_ylabel("std de x(t) − x(t−τ), bps (log)", color=C["tinta2"], fontsize=9)
    _leyenda(b1, loc="upper left")

    # --- 2 la nula de la última ventana ---
    _estilo(b2, "¿Cuánto H da el ruido? Ĥ de 400 caminos con signos al azar")
    b2.hist(d["H_nula"], bins=30, color=C["neutro"], edgecolor=C["fondo"])
    b2.axvline(d["H"], color=C["tinta"], linewidth=1.8, label=f"Ĥ observado {d['H']:.3f}")
    s = d["sesgo"]
    b2.axvline(cfg.umbral_tr, color=COLOR_REG[TR], linestyle="--", linewidth=1.1, label="tus umbrales")
    b2.axvline(cfg.umbral_mr, color=COLOR_REG[MR], linestyle="--", linewidth=1.1)
    b2.axvline(0.5 + s, color=C["tenue"], linestyle=":", linewidth=1.0, label=f"mediana nula {0.5 + s:.3f}")
    b2.set_xlabel("Ĥ (sin corregir)", color=C["tinta2"], fontsize=9)
    _leyenda(b2, loc="upper right", frameon=True, facecolor=C["fondo"], edgecolor="none", framealpha=0.9)

    # --- 3 estimadores ---
    _estilo(b3, "La última ventana con otros estimadores")
    est = [("varianza de dif. (Ĥ)", d["H"]), ("… corregido", hr.Hc[d["t"]]),
           ("R/S clásico", d["rs"]["H_rs"]), ("R/S Anis-Lloyd", d["rs"]["H_al"]), ("DFA", d["dfa"]["H"])]
    yv = np.arange(len(est))[::-1]
    b3.axvspan(hr.banda_lo[d["t"]], hr.banda_hi[d["t"]], color=C["neutro"], alpha=0.6, linewidth=0,
               label="paseo aleatorio (corregido)")
    b3.axvline(0.5, color=C["tenue"], linestyle=":", linewidth=1.0)
    b3.scatter([v for _, v in est], yv, s=60, color=[C["s1"], C["tinta"], C["s2"], C["s3"], C["s7"]], zorder=3)
    for (nm, v), y in zip(est, yv):
        b3.annotate(f"{v:.3f}", xy=(v, y), xytext=(7, -3), textcoords="offset points", fontsize=8, color=C["tinta"])
    b3.set_yticks(yv)
    b3.set_yticklabels([nm for nm, _ in est], fontsize=8.5)
    b3.set_ylim(-0.7, len(est) - 0.3)
    xs = [v for _, v in est if np.isfinite(v)] + [hr.banda_lo[d["t"]], hr.banda_hi[d["t"]]]
    b3.set_xlim(min(xs) - 0.03, max(xs) + 0.05)
    b3.set_xlabel("H", color=C["tinta2"], fontsize=9)
    _leyenda(b3, loc="lower right")

    # --- 4 retorno direccional por régimen y horizonte ---
    tb = aud.tabla
    f = tb[(tb.etiqueta == "módulo") & tb.regimen.isin(REGIMENES)].dropna(subset=["D_bps"]) \
        if "D_bps" in tb else tb.iloc[:0]
    _estilo(b4, "Lo que pasa después: D = signo(pasado) × retorno futuro, bps (IC 95 %)")
    hs = list(cfg.horizontes)
    ancho = 0.26
    for j, reg in enumerate(REGIMENES):
        g = f[f.regimen == reg].set_index("h").reindex(hs)
        xh = np.arange(len(hs)) + (j - 1) * ancho
        err = 1.96 * np.abs(g["D_bps"] / g["t"])
        b4.bar(xh, g["D_bps"], width=ancho, color=COLOR_REG[reg] if reg != RW else C["tenue"],
               alpha=0.8, label=reg)
        b4.errorbar(xh, g["D_bps"], yerr=err, fmt="none", ecolor=C["tinta"], elinewidth=0.9, capsize=2)
    b4.axhline(0, color=C["eje"], linewidth=0.9)
    b4.set_xticks(range(len(hs)))
    b4.set_xticklabels([f"h = {h}" for h in hs], fontsize=8.5)
    b4.set_ylabel("bps", color=C["tinta2"], fontsize=9)
    _leyenda(b4, loc="upper left", ncol=3)

    # --- 5 correlación a escala h: real contra la implícita ---
    _estilo(b5, "h barras contra las h siguientes: ● real · — implícita por H")
    for j, reg in enumerate(REGIMENES):
        g = f[f.regimen == reg].set_index("h").reindex(hs)
        xh = np.arange(len(hs)) + (j - 1) * 0.12
        col = COLOR_REG[reg] if reg != RW else C["tenue"]
        b5.plot(xh, g["corr"], "o", color=col, markersize=6, label=reg)
        b5.plot(xh, g["corr_teo"], "_", color=col, markersize=16, markeredgewidth=2)
        n_ = g["n"].to_numpy(float) / np.maximum(1, np.array(hs))
        b5.errorbar(xh, g["corr"], yerr=1.96 / np.sqrt(np.maximum(n_, 1)), fmt="none", ecolor=col,
                    elinewidth=0.8, alpha=0.7)
    b5.axhline(0, color=C["eje"], linewidth=0.9)
    b5.set_xticks(range(len(hs)))
    b5.set_xticklabels([f"h = {h}" for h in hs], fontsize=8.5)
    b5.set_ylabel("correlación", color=C["tinta2"], fontsize=9)
    _leyenda(b5, loc="lower left", ncol=3)

    # --- 6 autocorrelación condicional ---
    _estilo(b6, "Autocorrelación DESPUÉS de la etiqueta: ● real · — por H")
    for j, reg in enumerate(REGIMENES):
        k, rho, teo, pares = aud.acf[reg]
        if not len(k):
            continue
        col = COLOR_REG[reg] if reg != RW else C["tenue"]
        b6.plot(k + (j - 1) * 0.15, rho, "o", color=col, markersize=4.5, label=reg)
        b6.plot(k, teo, color=col, linewidth=1.2)
    if aud.acf[RW][0].size:
        banda = 1.96 / math.sqrt(float(aud.acf[RW][3][0]))
        b6.axhspan(-banda, banda, color=C["neutro"], alpha=0.5, linewidth=0)
    b6.axhline(0, color=C["eje"], linewidth=0.9)
    b6.set_xlabel("rezago (barras)", color=C["tinta2"], fontsize=9)
    _leyenda(b6, loc="lower right", ncol=3)

    # --- 7 persistencia ---
    _estilo(b7, f"¿H persiste? H hoy contra H dentro de {cfg.ventana} barras")
    if "módulo" in aud.persist:
        c, n, a, b = aud.persist["módulo"]
        b7.scatter(a, b, s=4, color=C["s1"], alpha=0.25, linewidths=0)
        lim = [min(np.min(a), np.min(b)) - 0.01, max(np.max(a), np.max(b)) + 0.01]
        b7.plot(lim, lim, color=C["tenue"], linestyle=":", linewidth=1.0)
        b7.axhline(0.5, color=C["eje"], linewidth=0.8)
        b7.axvline(0.5, color=C["eje"], linewidth=0.8)
        b7.text(0.03, 0.95, f"correlación {c:+.2f}\n{n:,} pares", transform=b7.transAxes, va="top",
                fontsize=9, color=C["tinta"])
    b7.set_xlabel("H corregido hoy", color=C["tinta2"], fontsize=9)
    b7.set_ylabel("H corregido de la ventana siguiente", color=C["tinta2"], fontsize=9)

    # --- 8 la regla operable ---
    _estilo(b8, f"Regla: signo de {cfg.h_senal} barras × régimen, 1 barra, costo {cfg.costo_ticks:g} tick (bps acumulados)")
    colores = {"módulo": C["s1"], "sólo umbral": C["s5"], "tu script": C["s4"],
               "siempre momentum": C["tenue"], "siempre reversión": C["tinta2"]}
    idx = np.flatnonzero(res.m)
    pos = np.arange(len(idx))
    tot = aud.resumen_estr.set_index("regla")
    for nm, col in colores.items():
        cur = aud.curvas[nm].to_numpy()[idx]
        cur = cur - cur[0]
        est_ = "--" if nm.startswith("siempre") else "-"
        b8.plot(pos, cur, color=col, linewidth=1.4 if nm == "módulo" else 1.0, linestyle=est_,
                label=f"{nm}: {tot.loc[nm, 'total_bps']:+.0f} bps · Sharpe {tot.loc[nm, 'sharpe']:+.2f}")
    b8.axhline(0, color=C["eje"], linewidth=0.9)
    _eje_barras(b8, res.A.index[idx], cfg.tz_local, n_ticks=7)
    b8.set_ylabel("bps", color=C["tinta2"], fontsize=9)
    _leyenda(b8, loc="upper left", ncol=2, frameon=True, facecolor=C["fondo"], edgecolor="none", framealpha=0.9)
    fig.text(0.008, 0.012, f"{IDENTIFICADOR} · D con t de Newey-West · la regla usa el régimen conocido al "
             "cierre de cada barra y opera la barra siguiente", color=C["tenue"], fontsize=7.5)
    fig.savefig(ruta, dpi=120, facecolor=C["fondo"], bbox_inches="tight")
    return fig


def tableros(res: Resultado, mostrar: bool = True) -> tuple[list[Path], object, bool]:
    plt, ventana = _preparar_grafico(mostrar)
    if plt is None:
        return [], None, False
    carpeta = _ruta(res.cfg.salida_dir)
    carpeta.mkdir(parents=True, exist_ok=True)
    suf = _nombre_seguro(raiz(res.cfg.symbol), etiqueta_barra(res.cfg).replace(" ", ""))
    rutas = []
    for nombre_, fn in (("transicion", tablero_transicion), ("auditoria", tablero_auditoria)):
        ruta = carpeta / f"hurst_{nombre_}_{suf}.png"
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
    hr = res.hr
    ok = np.flatnonzero(np.isfinite(hr.H))
    if len(ok) < 2:
        return []
    i, j = ok[-1], ok[-2]
    avisos = []
    if hr.regimen[i] != hr.regimen[j]:
        avisos.append(f"Cambio de régimen confirmado: {hr.regimen[j]} → {hr.regimen[i]}")
    elif not res.cfg.telegram_solo_confirmados and hr.base[i] != hr.base[j]:
        avisos.append(f"Cambio por umbral (sin confianza): {hr.base[j]} → {hr.base[i]}")
    return avisos


def mensaje_telegram(res: Resultado, limite: int = 4096) -> str:
    esc = html.escape
    cfg, hr, aud = res.cfg, res.hr, res.aud
    t = int(np.flatnonzero(np.isfinite(hr.H))[-1])
    lin = [f"<b>{esc(IDENTIFICADOR)}</b> · {esc(cfg.symbol)} · {esc(etiqueta_barra(cfg))}",
           esc(_hora(res, t))]
    for a in hay_alerta(res):
        lin.append(f"⚠️ {esc(a)}")
    conf = "confirmado" if hr.confirmado[t] else ("sin memoria" if hr.base[t] == RW else
                                                  f"{hr.base[t]} por umbral, sin confianza")
    lin += ["", f"<b>{esc(hr.regimen[t])}</b> ({esc(conf)}) · hace {_racha_actual(hr.regimen, t)} barras",
            f"H {hr.Hc[t]:.3f} · paseo aleatorio {hr.banda_lo[t]:.3f}–{hr.banda_hi[t]:.3f}",
            f"p persistencia {hr.p_tr[t]:.3f} · p reversión {hr.p_mr[t]:.3f} · R² {hr.r2[t]:.3f}"]
    tb = aud.tabla
    reg = hr.regimen[t]
    f = tb[(tb.etiqueta == "módulo") & (tb.regimen == reg)].dropna(subset=["D_bps"]) \
        if "D_bps" in tb else tb.iloc[:0]
    if len(f):
        filas = [f"Después de {CORTO[reg]} (historia)", "  h   D bps      t"]
        for z in f.itertuples():
            filas.append(f"{int(z.h):3d} {z.D_bps:+7.2f} {z.t:+6.2f}")
        lin.append("<pre>" + esc("\n".join(filas)) + "</pre>")
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
# 13. GUARDAR
# =============================================================================
def guardar(res: Resultado) -> None:
    cfg, A, hr, tu = res.cfg, res.A, res.hr, res.tu
    carpeta = _ruta(cfg.salida_dir)
    carpeta.mkdir(parents=True, exist_ok=True)
    suf = _nombre_seguro(raiz(cfg.symbol), etiqueta_barra(cfg).replace(" ", ""), cfg.ventana)
    out = pd.DataFrame({
        "hora_ct": A.index.tz_convert(cfg.tz_mercado).strftime("%Y-%m-%d %H:%M"),
        "hora_cdmx": A.index.tz_convert(cfg.tz_local).strftime("%Y-%m-%d %H:%M"),
        "cierre": A["close"], "log_ret": A["r"], "roll": A["roll"],
        "H": hr.H, "H_corregido": hr.Hc, "banda_baja": hr.banda_lo, "banda_alta": hr.banda_hi,
        "p_persistencia": hr.p_tr, "p_reversion": hr.p_mr, "R2": hr.r2,
        "regimen_umbral": hr.base, "regimen": hr.regimen, "confirmado": hr.confirmado,
        "en_ventana": res.m, "tu_H": tu["H"], "tu_R2": tu["R2"], "tu_regimen": tu["regimen"]},
        index=A.index)
    out.to_csv(carpeta / f"hurst_{suf}.csv")
    res.aud.tabla.to_csv(carpeta / f"hurst_auditoria_{suf}.csv", index=False)
    res.aud.resumen_estr.to_csv(carpeta / f"hurst_estrategia_{suf}.csv", index=False)
    res.aud.trans_real.to_csv(carpeta / f"hurst_transiciones_{suf}.csv")
    print(f"💾 Tablas guardadas en {carpeta}")


# =============================================================================
# 14. LÍNEA DE COMANDOS
# =============================================================================
def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Hurst Exponent AC v2 — régimen con confianza estadística")
    p.add_argument("--pruebas", action="store_true", help="pruebas internas (sin red ni datos)")
    p.add_argument("--simulacion", action="store_true",
                   help="datos simulados con H conocido por tramos (sin red)")
    p.add_argument("--sin-tablero", "--sin-grafica", action="store_true", dest="sin_tablero")
    p.add_argument("--sin-ventana", action="store_true")
    p.add_argument("--sin-cache", action="store_true")
    d = p.add_argument_group("datos")
    d.add_argument("--simbolo", default=None, help="NQ, ES.n.0, CL, …")
    d.add_argument("--start", "--inicio", default=None, dest="start")
    d.add_argument("--end", "--fin", default=None, dest="end")
    d.add_argument("--barra", type=int, default=None, dest="barra_min",
                   help="minutos por barra: 1-30 (divisor de 60), 60, 120…, o 1440 = sesión")
    d.add_argument("--costo-max", type=float, default=None, dest="costo_max_usd")
    d.add_argument("--salida", default=None, dest="salida_dir")
    h = p.add_argument_group("Hurst y confianza")
    h.add_argument("--ventana", type=int, default=None)
    h.add_argument("--max-lag", type=int, default=None, dest="max_lag")
    h.add_argument("--lag-min", type=int, default=None, dest="lag_min")
    h.add_argument("--sin-ponderar", action="store_true", help="MCO en vez de mínimos cuadrados ponderados")
    h.add_argument("--step", type=int, default=None, help=argparse.SUPPRESS)
    h.add_argument("--r2-min", type=float, default=None, dest="r2_min")
    h.add_argument("--nula", type=int, default=None, dest="n_nula", help="caminos de la nula (200)")
    h.add_argument("--alfa", type=float, default=None)
    h.add_argument("--umbral-mr", type=float, default=None, dest="umbral_mr")
    h.add_argument("--umbral-tr", type=float, default=None, dest="umbral_tr")
    a = p.add_argument_group("auditoría")
    a.add_argument("--horizontes", default=None, help='barras, p. ej. "1,4,8,24"')
    a.add_argument("--senal", type=int, default=None, dest="h_senal",
                   help="barras del movimiento previo que da la dirección (24)")
    a.add_argument("--costo-ticks", type=float, default=None, dest="costo_ticks")
    t = p.add_argument_group("Telegram")
    t.add_argument("--telegram", action="store_true")
    t.add_argument("--telegram-solo-alertas", action="store_true")
    t.add_argument("--telegram-documentos", action="store_true")
    t.add_argument("--telegram-buscar-chat", action="store_true")
    s = p.add_argument_group("simulación")
    s.add_argument("--barras-sim", type=int, default=None, dest="sim_barras")
    s.add_argument("--semilla", type=int, default=None, dest="sim_semilla")
    s.add_argument("--sim-paseo", action="store_true", help="simula un paseo aleatorio puro (H = 0.5)")
    return p


def config_desde_args(a: argparse.Namespace) -> Config:
    cambios = {}
    for k in ("start", "end", "barra_min", "costo_max_usd", "salida_dir", "ventana", "max_lag",
              "lag_min", "r2_min", "n_nula", "alfa", "umbral_mr", "umbral_tr", "h_senal",
              "costo_ticks", "sim_barras", "sim_semilla"):
        v = getattr(a, k, None)
        if v is not None:
            cambios[k] = v
    if a.simbolo:
        cambios["symbol"] = simbolo_continuo(a.simbolo)
    if a.horizontes:
        cambios["horizontes"] = tuple(int(x) for x in a.horizontes.split(",") if x.strip())
    if a.sin_ponderar:
        cambios["ponderado"] = False
    if a.sin_cache:
        cambios["usar_cache"] = False
    if a.sim_paseo:
        cambios["sim_hs"] = (0.5, 0.5, 0.5)
    return replace(CFG, **cambios)


def main(argv: list[str] | None = None) -> int:
    a = construir_parser().parse_args(argv)
    cfg = config_desde_args(a)
    if a.pruebas:
        return pruebas()
    if a.telegram_buscar_chat:
        return buscar_chat_telegram()
    validar(cfg)
    print(f"▶ {IDENTIFICADOR} · {cfg.symbol} · barras de {etiqueta_barra(cfg)} · ventana {cfg.ventana}")
    if a.step:
        print("   (--step ya no hace falta: el Hurst se calcula en CADA barra en milisegundos)")
    verdad = None
    if a.simulacion:
        hs = cfg.sim_hs
        print(f"🎲 {cfg.sim_barras:,} barras simuladas: tramos con H = {hs[0]} / {hs[1]} / {hs[2]} "
              "CONOCIDOS, volatilidad agrupada, colas gruesas y rolls.")
        crudo, verdad = simular(cfg)
    else:
        crudo = obtener_datos(cfg)
    barras = preparar_barras(crudo, cfg)
    res = analizar(barras, cfg, verdad=verdad)
    reporte_datos(res)
    reporte_tu_script(res)
    reporte_estimacion(res)
    reporte_continuo(res)
    reporte_auditoria(res)
    reporte_verdad(res)
    rutas, plt_, ventana = ([], None, False)
    if not a.sin_tablero:
        print()
        rutas, plt_, ventana = tableros(res, mostrar=not a.sin_ventana)
    guardar(res)
    if a.telegram or a.telegram_solo_alertas:
        if a.telegram_solo_alertas and not hay_alerta(res):
            print("📭 Telegram: sin alertas.")
        else:
            enviar_telegram(res, rutas, documentos=a.telegram_documentos)
    _titulo("CÓMO LEER ESTO")
    print("  1. H se mide sobre el log-precio sin rolls, con rezagos en escala log, y se CORRIGE por el")
    print("     sesgo que el propio estimador tiene en una ventana de este tamaño.")
    print("  2. La banda gris es lo que da un paseo aleatorio con TU volatilidad. Dentro de ella, H no")
    print("     dice nada, aunque cruce 0.45 o 0.55.")
    print("  3. Trending / Mean-Reverting sólo cuentan confirmados (fuera de la banda y con R² alto).")
    print("  4. La auditoría dice si esa memoria SIGUE después de la etiqueta. Si |t| < 2, no la uses")
    print("     para operar: el Hurst describe la ventana pasada.")
    if rutas and not a.sin_ventana:
        print()
        mostrar_tableros(plt_, ventana, rutas)
    return 0


# =============================================================================
# 15. PRUEBAS INTERNAS
# =============================================================================
def pruebas() -> int:
    cfg = replace(CFG, n_nula=120)
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

    # 1 ------------------------------------------ el rodante vectorizado = ventana por ventana
    x = np.cumsum(rng.standard_t(4, 3000)) * 1e-3
    lags = rezagos(cfg)
    w = pesos_rezagos(lags, cfg.ventana, True)
    Hv, r2v = pendiente(log_std_rodante(x, cfg.ventana, lags), lags, w)
    err = 0.0
    for t in rng.integers(cfg.ventana, len(x), 12):
        xw = x[t - cfg.ventana + 1:t + 1]
        Y = np.array([np.log(np.std(xw[k:] - xw[:-k])) for k in lags])
        X = np.log(lags.astype(float))
        b = np.polyfit(X, Y, 1, w=np.sqrt(w))[0]
        err = max(err, abs(b - Hv[t]))
    check("Hurst rodante con sumas acumuladas = cálculo directo ventana por ventana", err < 1e-9,
          f"diferencia máxima {err:.1e}")

    # 2 ------------------------------------------ la réplica de tu script da lo mismo que tu función
    A0 = pd.DataFrame({"close": np.exp(x + 9.9)}, index=pd.date_range("2026-01-01", periods=len(x),
                                                                     freq="h", tz="UTC"))
    tu0 = tu_rodante(A0, cfg)
    err2 = 0.0
    for i in rng.integers(cfg.ventana + 1, len(x), 6):
        h_, r2_, _ = hurst_tu_script(np.log(A0["close"].to_numpy())[i - cfg.ventana:i], cfg.max_lag)
        err2 = max(err2, abs(h_ - tu0["H"].iloc[i]), abs(r2_ - tu0["R2"].iloc[i]))
    check("tu rolling_hurst vectorizado = tu función barra por barra", err2 < 1e-9,
          f"diferencia máxima {err2:.1e}")

    # 3 ------------------------------------------ el generador de fGn tiene la memoria que dice
    ok3, det3 = True, []
    for H in (0.3, 0.7):
        z = fgn(200_000, H, rng)
        rho = float(np.corrcoef(z[1:], z[:-1])[0, 1])
        ok3 &= abs(rho - corr_escala_fgn(H)) < 0.01
        det3.append(f"H {H}: ρ₁ {rho:+.3f} (teórica {corr_escala_fgn(H):+.3f})")
    check("el ruido gaussiano fraccional simulado tiene la autocorrelación teórica", ok3, " · ".join(det3))

    # 4 ------------------------------------------ con mucha historia, el estimador acierta
    ok4, det4 = True, []
    for H in (0.3, 0.5, 0.7):
        xx = np.r_[0.0, np.cumsum(fgn(20_000, H, rng))]
        h_, _ = hurst_ventana(xx, lags)
        ok4 &= abs(h_ - H) < 0.02
        det4.append(f"{H} → {h_:.3f}")
    check("varianza de diferencias recupera H con 20 000 barras", ok4, " · ".join(det4))

    # 5 ------------------------------------------ barras de 1 h: sin rolls y exacto
    df, ver = simular(cfg, n_barras=2500, semilla=4)
    b = preparar_barras(df, cfg)
    A = barras_analisis(b, cfg)
    ef = ver["ef"].reindex(A.index).to_numpy()
    xa = A["x"].to_numpy()
    e5 = float(np.nanmax(np.abs((xa - xa[0]) - (ef - ef[0]))))
    check("log-precio sin rolls = el verdadero (barras de 1 h)",
          e5 < 1e-10 and int(A["roll"].sum()) == ver["rolls"] and ver["rolls"] > 0,
          f"error máximo {e5:.1e} · {int(A['roll'].sum())} rolls de {ver['rolls']}")

    # 6 ------------------------------------------ barras de 5 min armadas con las de 1 min
    c5 = replace(cfg, barra_min=5, ventana=300, max_lag=30)
    df5, ver5 = simular(c5, n_barras=4000, semilla=2)
    A5 = barras_analisis(preparar_barras(df5, c5), c5)
    ef5 = ver5["ef"].reindex(A5.index).to_numpy()
    x5 = A5["x"].to_numpy()
    e6 = float(np.nanmax(np.abs((x5 - x5[0]) - (ef5 - ef5[0]))))
    por_ses = A5.groupby("ses").size()
    check("barras de 5 min alineadas a la sesión, desde 1 min, sin rolls",
          e6 < 1e-10 and int(por_ses.median()) == MINUTOS_SESION // 5,
          f"error {e6:.1e} · {int(por_ses.median())} barras por sesión")

    # 7 ------------------------------------------ esquemas que SÍ existen en Databento
    check("--barra 5/15/30 pide ohlcv-1m (tu script pide ohlcv-5m, que no existe)",
          esquema(5) == "ohlcv-1m" and esquema(15) == "ohlcv-1m" and esquema(60) == "ohlcv-1h"
          and esquema(1440) == "ohlcv-1h" and "ohlcv-5m" not in ESQUEMAS_DATABENTO
          and all(esquema(k) in ESQUEMAS_DATABENTO for k in (1, 5, 30, 60, 240, 1440)))

    # 8 ------------------------------------------ validación de parámetros
    malos = 0
    for kw in ({"barra_min": 7}, {"max_lag": 200}, {"umbral_mr": 0.55}, {"lag_min": 60}):
        try:
            validar(replace(cfg, **kw))
        except SystemExit:
            malos += 1
    check("rechaza barras que no caben en la sesión, rezagos > W/5 y umbrales cruzados", malos == 4)

    # 9-10 --------------------------------------- calibración con ventanas INDEPENDIENTES
    # K ventanas de W barras, cada una su propio fGn con volatilidad realista (agrupada por
    # sesión, colas t5, estacionalidad intradía); se evalúa sólo donde la ventana rodante
    # cubre exactamente un segmento.
    W = cfg.ventana
    K = 200

    def _ventanas(H: float) -> tuple[HurstRodante, pd.DataFrame, np.ndarray]:
        partes = []
        for _ in range(K):
            hs_ = np.zeros(W // 23 + 2)
            for s_ in range(1, len(hs_)):
                hs_[s_] = 0.95 * hs_[s_ - 1] + 0.2 * rng.normal()
            esc = (np.repeat(np.exp(hs_), 23)[:W] * perfil_intradia((np.arange(W) % 23) * 60)
                   * math.sqrt(3 / 5) / np.sqrt(rng.chisquare(5, W) / 5))
            partes.append(fgn(W, H, rng) * esc * 1e-3)
        rr = np.concatenate(partes)
        xx = np.cumsum(rr)
        fines = np.arange(1, K + 1) * W - 1
        Ak = pd.DataFrame({"close": np.exp(xx + 9.9)},
                          index=pd.date_range("2020-01-01", periods=len(xx), freq="h", tz="UTC"))
        return hurst_rodante(xx, rr, cfg, verbose=False), tu_rodante(Ak, cfg), fines

    h0, t0, f0 = _ventanas(0.5)
    ft = np.minimum(f0 + 1, len(t0) - 1)
    mod_tr, mod_mr = float(np.mean(h0.regimen[f0] == TR)), float(np.mean(h0.regimen[f0] == MR))
    tu_tr = float(np.mean(t0["regimen"].to_numpy()[ft] == "TRENDING"))
    tu_mr = float(np.mean(t0["regimen"].to_numpy()[ft] == "MEAN_REV"))
    check("sin memoria (H = 0.5): el módulo confirma ≈ α por lado; tu regla marca régimen la mitad",
          mod_tr < 0.09 and mod_mr < 0.09 and tu_tr + tu_mr > 0.30,
          f"módulo TR {mod_tr:.1%} · MR {mod_mr:.1%} · tu regla TR {tu_tr:.1%} · MR {tu_mr:.1%}")
    r2_pasa = float(np.mean(t0["R2"].to_numpy()[ft] >= cfg.r2_min))
    check("…y tu filtro R² ≥ 0.85 deja pasar casi todo", r2_pasa > 0.95, f"pasa {r2_pasa:.1%}")
    med_c, med_h = float(np.median(h0.Hc[f0])), float(np.median(h0.H[f0]))
    check("la corrección de sesgo centra H en 0.5 cuando no hay memoria",
          abs(med_c - 0.5) < 0.012 and med_h < med_c, f"Ĥ mediano {med_h:.3f} → corregido {med_c:.3f}")
    h6, t6, f6 = _ventanas(0.65)
    ve_mod = float(np.mean(h6.regimen[f6] == TR))
    ve_tu = float(np.mean(t6["regimen"].to_numpy()[np.minimum(f6 + 1, len(t6) - 1)] == "TRENDING"))
    check("con memoria (H = 0.65): el módulo la confirma más seguido que tu regla",
          ve_mod > ve_tu and ve_mod > 0.6, f"módulo {ve_mod:.1%} · tu regla {ve_tu:.1%}")

    # 11 ----------------------------------------- nada mira al futuro
    dfp, _ = simular(cfg, n_barras=3000, semilla=11)
    Ap = barras_analisis(preparar_barras(dfp, cfg), cfg)
    xp, rp_ = Ap["x"].to_numpy(), Ap["r"].to_numpy()
    h1 = hurst_rodante(xp, rp_, cfg, verbose=False)
    h2 = hurst_rodante(xp[:-300], rp_[:-300], cfg, verbose=False)
    k_ = len(xp) - 300
    check("truncar la muestra no cambia H, la banda ni los p-valores del pasado",
          np.allclose(h1.H[:k_], h2.H, equal_nan=True) and np.allclose(h1.Hc[:k_], h2.Hc, equal_nan=True)
          and np.allclose(h1.p_tr[:k_], h2.p_tr, equal_nan=True))

    # 12 ----------------------------------------- la regla de régimen
    Hc_ = np.array([0.60, 0.60, 0.60, 0.40, 0.40, 0.50, np.nan])
    p_tr_ = np.array([0.01, 0.20, 0.01, 0.99, 0.99, 0.50, np.nan])
    p_mr_ = np.array([0.99, 0.80, 0.99, 0.01, 0.30, 0.50, np.nan])
    r2_ = np.array([0.99, 0.99, 0.50, 0.99, 0.99, 0.99, np.nan])
    base_, reg_, conf_ = clasificar(Hc_, p_tr_, p_mr_, r2_, cfg)
    check("régimen: confirma sólo con umbral + p < α + R²; lo demás es Random Walk",
          list(reg_) == [TR, RW, RW, MR, RW, RW, "—"] and list(base_[:5]) == [TR, TR, TR, MR, MR])

    # 13 ----------------------------------------- R/S con corrección y DFA
    zi = rng.normal(size=4000)
    rs_i = rs_clasico(zi)
    ok13, det13 = rs_i["H_rs"] > 0.53 and abs(rs_i["H_al"] - 0.5) < 0.05, [
        f"iid: R/S {rs_i['H_rs']:.3f} → Anis-Lloyd {rs_i['H_al']:.3f}"]
    for H in (0.35, 0.65):
        z = fgn(4000, H, rng)
        a_, d_ = rs_clasico(z)["H_al"], dfa(z)["H"]
        ok13 &= abs(a_ - H) < 0.08 and abs(d_ - H) < 0.08
        det13.append(f"{H}: R/S-AL {a_:.3f} · DFA {d_:.3f}")
    check("R/S sin corregir sube H aun sin memoria; Anis-Lloyd y DFA recuperan H", ok13, " · ".join(det13))

    # 14 ----------------------------------------- razón de varianzas de Lo-MacKinlay
    het = rng.standard_t(5, 20_000) * np.exp(np.repeat(rng.normal(0, 0.5, 200), 100))
    ar = np.zeros(20_000)
    e_ = rng.normal(size=20_000)
    for t in range(1, 20_000):
        ar[t] = 0.1 * ar[t - 1] + e_[t]
    z_iid = [razon_varianzas(het, q)[1] for q in (2, 4, 8)]
    z_ar = razon_varianzas(ar, 2)[1]
    check("razón de varianzas: z* robusto no se dispara con heterocedasticidad y ve un AR(1) de 0.1",
          max(abs(z) for z in z_iid) < 2.6 and z_ar > 5,
          f"z* heterocedástico {', '.join(f'{z:+.2f}' for z in z_iid)} · AR(1) {z_ar:+.1f}")

    # 15 ----------------------------------------- la teoría que usa la auditoría
    check("ρ₁ del fGn = correlación entre tramos consecutivos = 2^(2H−1) − 1; 0 en H = 0.5",
          all(abs(acf_fgn(np.array([1]), H)[0] - corr_escala_fgn(H)) < 1e-12 for H in (0.3, 0.6))
          and abs(corr_escala_fgn(0.5)) < 1e-15 and abs(acf_fgn(np.array([3]), 0.5)[0]) < 1e-15)

    # 16 ----------------------------------------- pasado y futuro alineados
    xs = np.arange(10.0) ** 2
    pa, fu = _desplazado(xs, 3)
    check("auditoría: movimiento previo x[t] − x[t−h] y futuro x[t+h] − x[t], sin cruzarse",
          pa[5] == 25 - 4 and fu[5] == 64 - 25 and np.isnan(pa[2]) and np.isnan(fu[7]))

    # 17-19 -------------------------------------- de punta a punta, con régimen conocido
    dfs, vers = simular(cfg, n_barras=12000, semilla=0)
    res = analizar(preparar_barras(dfs, cfg), cfg, verdad=vers)
    md = res.medicion
    rw_mod = md["módulo"][f"marca_{RW}"]
    rw_tu = md["tu script"][f"marca_{RW}"]
    fa_mod = rw_mod.get(TR, 0) + rw_mod.get(MR, 0)
    fa_tu = rw_tu.get(TR, 0) + rw_tu.get(MR, 0)
    ve_tr = md["módulo"][f"marca_{TR}"].get(TR, np.nan)
    ve_mr = md["módulo"][f"marca_{MR}"].get(MR, np.nan)
    check("simulación: menos falsas alarmas que tu regla y ve los tramos con memoria",
          fa_mod < 0.5 * fa_tu and ve_tr > 0.4 and ve_mr > 0.4 and md["corr_H"] > md["corr_H_tu"],
          f"falsas alarmas en Random Walk {fa_mod:.1%} vs tuyas {fa_tu:.1%} · ve TR {ve_tr:.0%} · "
          f"ve MR {ve_mr:.0%} · corr con H verdadero {md['corr_H']:.2f} vs {md['corr_H_tu']:.2f}")
    tb = res.aud.tabla
    g = tb[(tb.etiqueta == "módulo")].set_index(["regimen", "h"])
    ok18 = any(g.loc[(TR, h), "D_bps"] > 0 and g.loc[(TR, h), "t"] > 2 for h in cfg.horizontes
               if (TR, h) in g.index) and any(g.loc[(MR, h), "D_bps"] < 0 and g.loc[(MR, h), "t"] < -2
                                              for h in cfg.horizontes if (MR, h) in g.index)
    check("la auditoría ve la memoria que sí hay: D > 0 tras Trending y D < 0 tras Mean-Reverting",
          ok18, " · ".join(f"{k} h={h}: {g.loc[(k, h), 'D_bps']:+.1f} bps (t {g.loc[(k, h), 't']:+.1f})"
                           for k in (TR, MR) for h in (4,) if (k, h) in g.index))
    tp = res.aud.tu_pares
    check("tu autocorr() por régimen empareja barras que no son consecutivas",
          len(tp) > 0 and float(tp["no_consecutivos"].max()) > 0.0,
          " · ".join(f"{z.regimen} {z.no_consecutivos:.1%}" for z in tp.itertuples()))

    # 20 ----------------------------------------- transiciones
    Tm, Tr_ = res.aud.trans_mec, res.aud.trans_real
    filas_ok = all(abs(np.nansum(T.loc[k]) - 1) < 1e-9 for T in (Tm, Tr_) for k in REGIMENES
                   if np.isfinite(T.loc[k]).any())
    check("transiciones: filas suman 1; la persistencia de 1 barra es mecánica (mayor que a W barras)",
          filas_ok and float(np.nanmean(np.diag(Tm))) > float(np.nanmean(np.diag(Tr_))),
          f"diagonal media {np.nanmean(np.diag(Tm)):.1%} a 1 barra vs {np.nanmean(np.diag(Tr_)):.1%} a W")

    # 21 ----------------------------------------- la regla no mira al futuro
    r_ = res.A["r"].to_numpy()
    x_ = res.A["x"].to_numpy()
    k_ = cfg.h_senal
    i_ = np.flatnonzero(res.m)[100:110]
    cost_ = cfg.costo_ticks * tick(cfg.symbol) / res.A["close"].to_numpy()
    pos_ = np.sign(x_ - np.r_[np.full(k_, np.nan), x_[:-k_]])
    man = [pos_[i] * r_[i + 1] - cost_[i] * abs(pos_[i] - pos_[i - 1]) for i in i_]
    cur = res.aud.curvas["siempre momentum"].to_numpy()
    auto = [(cur[i] - cur[i - 1]) / 1e4 for i in i_]
    check("regla operable: posición con datos hasta t, retorno de t a t+1", np.allclose(man, auto, atol=1e-12))

    # 22 ----------------------------------------- Telegram: nunca el token
    tok = "123456789:" + "A" * 35
    msg = _sin_token(f"fallo en https://api.telegram.org/bot{tok}/sendMessage", tok)
    check("los errores de Telegram nunca muestran el token", tok not in msg and "…" in msg)

    # 23 ----------------------------------------- Telegram de punta a punta, sin red
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

    # 24 ----------------------------------------- ninguna key escrita en este archivo
    fuente = Path(__file__).read_text(encoding="utf-8")
    check("no hay API keys ni tokens escritos en el código",
          not re.search("db" + "-" + r"[A-Za-z0-9]{20,}", fuente)
          and not re.search(r"\d{8,10}:" + r"[A-Za-z0-9_-]{35}", fuente))

    # 25 ----------------------------------------- mensaje de Telegram
    txt = mensaje_telegram(res)
    check("el mensaje de Telegram cabe en un mensaje", len(txt) <= 4096 and "<b>" in txt,
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
