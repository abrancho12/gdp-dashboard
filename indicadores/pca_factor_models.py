# -*- coding: utf-8 -*-
"""
PCA FACTOR MODELS AC v2 — estructura de factores cross-asset, riesgo y régimen Risk-On/Risk-Off
Datos: Databento OHLCV-1h (GLBX.MDP3), cierres SINCRONIZADOS por sesión de Globex.

Qué hace, en una línea: toma 16 futuros de CME de cinco clases (acciones, tasas, metales,
energía y divisas), arma retornos diarios comparables entre sí —a la misma hora y sin saltos
de roll—, encuentra cuántos factores comunes hay de verdad y qué significa cada uno, reparte
el riesgo de cada activo y de tu portafolio entre esos factores, sigue cómo cambia esa
estructura día a día y detecta el régimen Risk-On / Risk-Off con un modelo que sólo usa el
pasado.

LO QUE PEDISTE, HECHO A FONDO

  1. INGESTA MULTI-ACTIVO (CROSS-ASSET). Una sola descarga OHLCV-1h de todo el universo, con
     tope de costo antes de pagar y caché local. Con esas barras cada retorno va de corte a
     corte a la MISMA hora para todos (13:00 CT = 12:00 CDMX), cuando los cinco complejos
     están en horario líquido. Los rolls del continuo se detectan por instrument_id y se
     quitan: el día del roll se arma con dos tramos del mismo contrato. El feriado de un
     solo mercado no tira el día para los demás. En simulación, con rolls y feriados, los
     retornos reconstruidos coinciden con los verdaderos a 1.8e-15.

  2. ANÁLISIS DINÁMICO ESTRUCTURAL (ROLLING PCA). Ventana de 250 días que termina el día
     ANTERIOR, re-estimada cada día, con todos los componentes y alineada con la ventana
     previa (signo y orden por asignación húngara): PC1 no cambia de signo artificialmente
     (congruencia mínima día a día 0.995). Sigue la concentración (PC1, absorption ratio
     y su cambio ΔAR), cuántos factores hacen falta (80 %, 90 % y cuántos superan el ruido
     de Marchenko-Pastur), los loadings de PC1 en el tiempo, la estabilidad contra el PCA
     estático, la correlación acciones-bonos y el riesgo sistemático del portafolio.

  3. DESCOMPOSICIÓN FACTORIAL (PCA ESTÁTICO). PCA de la matriz de correlación de tu ventana.
     Cuántos factores cuentan lo deciden el análisis paralelo de Horn y el límite de
     Marchenko-Pastur, no un número fijo. Cada % de varianza lleva IC 90 % por bootstrap de
     bloques de 20 días, y la estabilidad se mide con la congruencia de Tucker entre la
     primera y la segunda mitad. En simulación ambos criterios encuentran los 3 factores
     verdaderos y PC1-PC3 recuperan su espacio (cosenos 0.999 · 0.996 · 0.981).

  4. INTERPRETACIÓN DE LOADINGS. Cada carga es la correlación del activo con el factor. Cada
     factor se orienta para que su clase dominante pese POSITIVO (PC1 arriba = risk-on;
     tasas arriba = bonos suben; dólar arriba = el dólar se debilita) y se nombra solo por
     la clase que lo compone. Cada carga lleva su IC 90 % bootstrap y sólo se leen las que
     no cruzan el cero.

  5. DESCOMPOSICIÓN CUANTITATIVA DEL RIESGO. Por activo: parte sistemática (entre 0 y 100 %)
     e idiosincrática, y cuánto viene de cada factor. Por portafolio (--pesos; por omisión
     inverso de la volatilidad): cuota EXACTA de cada factor en su varianza (suman 1 a
     1e-9), aporte de cada activo, número efectivo de apuestas (Meucci 2009) y razón de
     diversificación (Choueifaty-Coignard 2008). En la simulación el portafolio por omisión
     tiene ~2 apuestas efectivas de 16: casi todo su riesgo es PC1.

  6. DETECCIÓN DE RÉGIMEN SISTÉMICO (RISK-ON / RISK-OFF). Un modelo de Markov oculto de dos
     estados sobre el log de la varianza realizada INTRADÍA del portafolio de riesgo (23
     retornos horarios por día, con los pesos de PC1 de la ventana anterior). Se re-estima
     cada 20 días sólo con el pasado y da la probabilidad FILTRADA de risk-off. Se
     complementa con fragilidad (ΔAR ≥ 1σ, Kritzman et al. 2011) y turbulencia
     (Mahalanobis, calibrada contra χ²) con su correlación-sorpresa. Y se audita: qué pasa
     DESPUÉS de cada etiqueta (volatilidad de los 20 días siguientes y retorno del día
     siguiente), nunca el mismo día.

  7. DASHBOARD VISUAL MULTIDIMENSIONAL. Tres tableros de 6, 6 y 7 paneles:
       · estructura: scree contra el ruido, mapa de loadings, correlaciones por clase, mapa
         de factores PC1 × PC2, riesgo de cada activo por factor, cargas de PC1 con su IC;
       · dinámica: concentración y absorption ratio, loadings de PC1 en el tiempo, número
         de factores, correlación acciones-bonos, estabilidad y riesgo del portafolio;
       · régimen: PC1 acumulado con el régimen, lo que lee el Markov y su P(risk-off),
         fragilidad, turbulencia, volatilidad futura y retorno siguiente por régimen, y de
         dónde viene el riesgo del portafolio.

  Además: una sección que corre TU script sobre los mismos datos y muestra dónde se
  equivoca; un mundo simulado con factores, régimen, quiebre, rolls y feriados CONOCIDOS
  para medir todo contra la verdad; 25 pruebas internas; CSV de todo; y resumen y tableros
  a Telegram, como en tus otros módulos.

QUÉ SE MIDIÓ, contra la verdad de la simulación
  · Régimen, 6 semillas, sólo días en que el modelo ya existía (fuera de muestra):
                                  exactitud   precisión risk-off   exhaustividad
        retorno diario de PC1      71–91 %          70–93 %           16–75 %  (media 49 %)
        varianza intradía de PC1   92–96 %          66–96 %           91–96 %  (media 94 %)
        tu regla PC1 < −2σ            —             59–95 %            7–18 %
    El retorno diario se pierde la mitad de los días de estrés; 23 retornos horarios miden
    la volatilidad del día mucho mejor que uno solo. La precisión más baja (66 %) sale de la
    semilla con nueve meses seguidos de calma: ahí cualquier día agitado cuenta como falsa
    alarma. Tu regla casi nunca se equivoca porque casi nunca dice nada: marca el 2 % de
    los días y se pierde más del 80 % del estrés.
  · Quiebre estructural: a mitad de la muestra los bonos pasan de cubrir a las acciones a
    moverse con ellas (como en 2022). El PCA rodante lo ve: correlación acciones-bonos −0.62
    antes y +0.24 después, y los loadings de los bonos en PC1 cambian de azul a rojo.
  · Turbulencia con retornos normales: media 1.03 y excede su percentil 95 el 5.7 % de los
    días. El Markov recupera niveles, dispersiones y persistencia de una serie conocida
    (exactitud filtrada 96.5 %), y ni el filtro ni el rolling miran al futuro (truncar la
    muestra no cambia el pasado).
  · El régimen anticipa MAGNITUD: tras Risk-Off la volatilidad de los 20 días siguientes es
    10.3 % anual contra 7.0 % tras Risk-On. La dirección del día siguiente es ruido.

QUÉ FALLABA EN EL SCRIPT QUE MANDASTE (los comentarios [v2] lo marcan en el código)

  · LA API KEY ESTÁ ESCRITA EN LA LÍNEA 16. Dala por publicada y regenérala. Aquí se lee de
    DATABENTO_API_KEY, igual que en tus otros módulos.

  · TU "% SISTEMÁTICO" NO ES UN PORCENTAJE. decompose_risk divide la varianza de retornos
    ESTANDARIZADOS (explained_variance_) entre la de retornos CRUDOS (≈1e-4 al día). En la
    simulación sale en miles y millones de por ciento (8 305 898 % en ZF), y el
    "idiosincrático" enormemente negativo.

  · TU RÉGIMEN NO ES UN RÉGIMEN, Y SU TABLA ES UNA TAUTOLOGÍA. PC1 > +2σ / < −2σ marca el 2 %
    de días con el movimiento más grande, sin persistencia; la banda usa media y σ de TODA
    la muestra (mira al futuro); el "régimen actual" compara contra ±2 en vez de contra la
    banda (±4.73 en la simulación: 25 % de los días salen 'RISK' en una parte del reporte y
    'normal' en la otra). Y los "retornos por régimen" son del MISMO día que define PC1:
    acciones en Risk-On menos Risk-Off +546 bps el mismo día, +8 bps el día siguiente.

  · LOS ROLLS ENTRAN COMO RETORNO. log(df / df.shift(1)) sobre el continuo cuenta el salto
    entre contratos: en gas natural el 15 % de su varianza cae en el 4 % de los días, los
    de roll.

  · CIERRES QUE NO SE PUEDEN COMPARAR. ohlcv-1d corta por día UTC: su cierre es la última
    operación antes de las 18:00-19:00 CT, en la sesión nocturna más delgada. Y dropna()
    tira el día para TODOS si un solo mercado tuvo feriado.

  · TU ROLLING SE TOPA. n_components = 5 hace que n_factors_90 diga 5 en el 100 % de las
    ventanas cuando hacen falta 8-9. Y sin alinear ventanas el signo de PC1 puede voltearse.

  · EL SIGNO DE LOS FACTORES LO DECIDE SKLEARN. Su regla mecánica no sabe qué es "riesgo":
    PC1 arriba puede ser risk-off en una ventana y risk-on en la siguiente.

  · DX.n.0 NO EXISTE EN GLBX.MDP3 (el índice dólar cotiza en ICE) y el try/except con
    `continue` lo quita del análisis sin avisar. Aquí se avisa antes de descargar; el
    dólar queda medido por 6E, 6J, 6A y 6M (el factor "Dólar" de PC3).

  · Menores: divide entre 1e9 precios que to_df() ya entrega en float (los log-retornos no
    cambian, pero cualquier precio que muestres sale en millonésimas) y usa exit() en vez
    de sys.exit().

EL UNIVERSO. Tus 12 activos menos DX, más ZF (5 años), HG (cobre), NG (gas), 6A y 6M
(peso): así cada clase tiene al menos dos activos y el peso mexicano entra en el factor de
riesgo. Para usar exactamente los tuyos: --activos NQ,ES,YM,RTY,ZN,ZB,GC,SI,CL,6E,6J.

LÍMITES QUE CONVIENE SABER
  · Risk-Off aquí es el estado de MÁS VOLATILIDAD del factor de riesgo. Si tu historia casi
    no tiene estrés, un Markov de dos estados parte la calma en dos: mira la "vol típica"
    de cada estado en el reporte antes de leer la etiqueta como crisis.
  · El régimen necesita 250 días de rolling más 250 para arrancar el Markov; por eso se
    descargan 760 días naturales antes de tu --start.
  · Horas sin operaciones en contratos delgados no rompen nada: su movimiento se acumula
    en la siguiente barra. La suma de las 23 horas reproduce el retorno diario exacto.

CÓMO SE USA
    pip install numpy pandas scipy matplotlib databento
    python pca_factor_models.py --pruebas            # 25 pruebas, sin red
    python pca_factor_models.py --simulacion         # todo, con datos simulados
    python pca_factor_models.py                      # tu ventana: 2024-01-01 → 2026-09-01
    python pca_factor_models.py --start 2025-01-01 --ventana 120
    python pca_factor_models.py --activos ES,NQ,ZN,ZB,GC,CL,6E,6J
    python pca_factor_models.py --pesos "ES=1,ZN=-0.5,GC=0.3"   # tu portafolio
    python pca_factor_models.py --factores 4 --corte 12:00
    python pca_factor_models.py --telegram                 # resumen + 3 tableros
    python pca_factor_models.py --telegram-solo-alertas    # sólo si cambia el régimen,
                                                           # sube la fragilidad o hay turbulencia
  Las horas van en hora de CHICAGO; el reporte muestra también la de CDMX.

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
  Kritzman, M., Li, Y., Page, S. y Rigobon, R. (2011), "Principal components as a measure
      of systemic risk", Journal of Portfolio Management 37(4). — absorption ratio y ΔAR.
  Kritzman, M. y Li, Y. (2010), "Skulls, financial turbulence, and risk management",
      Financial Analysts Journal 66(5). — turbulencia.
  Kinlaw, W. y Turkington, D. (2013), "Correlation surprise", Journal of Asset Management
      14(6). — separar magnitud de correlación en la turbulencia.
  Horn, J. (1965), "A rationale and test for the number of factors in factor analysis",
      Psychometrika 30(2). — análisis paralelo.
  Marchenko, V. y Pastur, L. (1967), "Distribution of eigenvalues for some sets of random
      matrices", Math. USSR-Sbornik 1(4). — el límite del ruido.
  Lorenzo-Seva, U. y ten Berge, J. (2006), "Tucker's congruence coefficient as a meaningful
      index of factor similarity", Methodology 2(2).
  Meucci, A. (2009), "Managing diversification", Risk 22(5). — número efectivo de apuestas.
  Choueifaty, Y. y Coignard, Y. (2008), "Toward maximum diversification", Journal of
      Portfolio Management 35(1). — razón de diversificación.
  Hamilton, J. (1989), "A new approach to the economic analysis of nonstationary time
      series and the business cycle", Econometrica 57(2). — el modelo de Markov.
  Andersen, T., Bollerslev, T., Diebold, F. y Labys, P. (2003), "Modeling and forecasting
      realized volatility", Econometrica 71(2). — varianza realizada intradía.
  Epps, T. (1979), "Comovements in stock prices in the very short run", JASA 74(366).
  Künsch, H. (1989), "The jackknife and the bootstrap for general stationary
      observations", Annals of Statistics 17(3). — bootstrap de bloques.
  Databento: https://databento.com/docs — OHLCV-1h, símbolos continuos .n.0.
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
import textwrap
import time
import uuid
import warnings
from dataclasses import dataclass, replace
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

try:
    from scipy.optimize import linear_sum_assignment
    from scipy.stats import chi2
except ModuleNotFoundError:                                   # pragma: no cover
    sys.exit("Falta scipy:  pip install scipy")

try:
    import databento as db
except ModuleNotFoundError:
    db = None

IDENTIFICADOR = "pca-factor-models-ac-v2"
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)
np.seterr(all="ignore")

# --- Constantes de la sesión de CME Globex ---
MINUTOS_SESION = 1380            # 17:00 → 16:00 CT (23 horas)
DESFASE_H = 7                    # hora CT + 7 h → la sesión que abre a las 17:00 cae en su fecha

# Raíz → (nombre, clase, precio de referencia para la simulación)
CATALOGO = {
    "ES": ("S&P 500", "acciones", 5000.0), "NQ": ("Nasdaq 100", "acciones", 18000.0),
    "YM": ("Dow Jones", "acciones", 40000.0), "RTY": ("Russell 2000", "acciones", 2100.0),
    "ZT": ("Nota 2 años", "tasas", 102.0), "ZF": ("Nota 5 años", "tasas", 107.0),
    "ZN": ("Nota 10 años", "tasas", 110.0), "ZB": ("Bono 30 años", "tasas", 118.0),
    "GC": ("Oro", "metales", 2300.0), "SI": ("Plata", "metales", 28.0),
    "HG": ("Cobre", "metales", 4.3), "CL": ("Crudo WTI", "energía", 75.0),
    "NG": ("Gas natural", "energía", 2.6), "6E": ("Euro", "divisas", 1.08),
    "6J": ("Yen", "divisas", 0.0068), "6B": ("Libra", "divisas", 1.27),
    "6A": ("Dólar australiano", "divisas", 0.66), "6C": ("Dólar canadiense", "divisas", 0.73),
    "6S": ("Franco suizo", "divisas", 1.12), "6M": ("Peso mexicano", "divisas", 0.055),
}
FUERA_DE_GLOBEX = {"DX": "el índice dólar (DX) cotiza en ICE Futures U.S., no en CME Globex: "
                         "no está en GLBX.MDP3"}
CLASES = ("acciones", "tasas", "metales", "energía", "divisas", "otro")


# =============================================================================
# 1. CONFIGURACIÓN
# =============================================================================
@dataclass(frozen=True)
class Config:
    # --- Datos (Ingesta multi-activo) ---
    dataset: str = "GLBX.MDP3"
    activos: tuple[str, ...] = ("ES", "NQ", "YM", "RTY", "ZF", "ZN", "ZB", "GC", "SI", "HG",
                                "CL", "NG", "6E", "6J", "6A", "6M")
    start: str = "2024-01-01T00:00:00"     # ventana que se REPORTA (la tuya)
    end: str = "2026-09-01T00:00:00"       # exclusivo
    dias_calentamiento: int = 760          # días naturales previos: ventana (250) + arranque del
                                           # Markov (250) en días hábiles, así todo cubre tu ventana
    cache_dir: str = "datos_databento"
    usar_cache: bool = True
    salida_dir: str = "salidas_pca"
    costo_max_usd: float = 25.0
    tz_mercado: str = "America/Chicago"
    tz_local: str = "America/Mexico_City"
    corte_ct: str = "13:00"                # cierre SINCRONIZADO: todos los mercados abiertos
    min_cobertura: float = 0.80            # fracción de activos con dato para conservar un día

    # --- PCA ---
    ventana: int = 250                     # rolling (tu script: 120)
    factores: int | None = None            # None = los que dicta el análisis paralelo
    n_boot: int = 300
    bloque_boot: int = 20
    n_paralelo: int = 200

    # --- Régimen ---
    hmm_min: int = 250
    hmm_refit: int = 20
    umbral_prob: float = 0.5
    dar_umbral: float = 1.0                # ΔAR en desviaciones (Kritzman et al. 2011)
    turb_conf: float = 0.95
    horizonte_vol: int = 20

    # --- Portafolio ---
    pesos: str | None = None               # "ES=1,ZN=-0.5"; None = inverso de la volatilidad

    # --- Simulación ---
    sim_dias: int = 1150
    sim_semilla: int = 0

    # --- Telegram ---
    telegram_turb_alerta: float = 0.99


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


def nombre(raiz: str) -> str:
    return CATALOGO.get(raiz, (raiz, "otro", 100.0))[0]


def clase(raiz: str) -> str:
    return CATALOGO.get(raiz, (raiz, "otro", 100.0))[1]


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
    "  • La que estaba escrita en la línea 16 de PCA__Factor_Models_Institucional.py hay que\n"
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
    Una sola descarga de barras de 1 HORA para todo el universo.

    [v2] Tu script descarga ohlcv-1d por activo dentro de un try/except que hace `continue`
    en silencio: si un símbolo falla, desaparece del análisis sin avisar. DX.n.0 falla
    siempre, porque el índice dólar no cotiza en CME Globex. Aquí se avisa antes de gastar
    y se reporta después qué llegó y qué no.
    """
    for r in cfg.activos:
        if r in FUERA_DE_GLOBEX:
            sys.exit(f"❌ {r}: {FUERA_DE_GLOBEX[r]}. Quítalo de --activos (el dólar ya queda "
                     "medido por las divisas contra USD: 6E, 6J, 6A, 6M…).")
    carpeta = _ruta(cfg.cache_dir)
    carpeta.mkdir(parents=True, exist_ok=True)
    inicio = (pd.Timestamp(cfg.start) - pd.Timedelta(days=cfg.dias_calentamiento)
              ).strftime("%Y-%m-%dT%H:%M:%S")
    simbolos = [f"{r}.n.0" for r in cfg.activos]
    esquema = "ohlcv-1h"
    ruta = carpeta / (_nombre_seguro(cfg.dataset, "-".join(cfg.activos), inicio, cfg.end, esquema)
                      + ".dbn.zst")
    if ruta.exists() and cfg.usar_cache:
        print(f"📂 Usando caché local: {ruta.name}")
        return db.DBNStore.from_file(ruta)
    cliente = cliente or conectar()
    params = dict(dataset=cfg.dataset, symbols=simbolos, stype_in="continuous", schema=esquema,
                  start=inicio, end=cfg.end)
    costo = cliente.metadata.get_cost(**params)
    print(f"💵 Costo estimado: US$ {costo:,.2f}  ({len(simbolos)} activos, {esquema})")
    if costo > cfg.costo_max_usd:
        sys.exit(f"💰 El costo (US$ {costo:,.2f}) supera tu tope de US$ {cfg.costo_max_usd:,.2f}.\n"
                 f"   Si estás de acuerdo:  --costo-max {math.ceil(costo) + 1}")
    temporal = ruta.with_name(ruta.name + ".parcial")
    temporal.unlink(missing_ok=True)
    print(f"📡 Descargando {len(simbolos)} activos ({esquema}) desde {inicio[:10]} …")
    cliente.timeseries.get_range(**params, path=temporal)
    temporal.replace(ruta)
    return db.DBNStore.from_file(ruta)


def preparar_barras(tienda, cfg: Config) -> pd.DataFrame:
    """
    OHLCV-1h de varios activos → barras limpias con raíz, sesión de Globex y minuto.

    [v2] Tu script divide entre 1e9 los precios que to_df() ya entrega en float (verificado
    en databento 0.87). Aquí la escala se decide por el TIPO de la columna: si llega entera
    es punto fijo; si llega float, se deja. (Un umbral numérico no sirve con varios activos:
    el yen en punto fijo vale 6.8e6 y el Dow en float 4e4.)
    """
    df = tienda.to_df() if hasattr(tienda, "to_df") else tienda
    df = df.copy()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    for req in ("open", "close", "symbol"):
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
    df["raiz"] = df["symbol"].astype(str).str.split(".").str[0]
    df = df.reset_index().drop_duplicates(subset=[df.index.name or "index", "raiz"], keep="last")
    df = df.set_index(df.columns[0]).sort_index()
    ses, minuto = sesion_y_minuto(df.index, cfg.tz_mercado)
    df["sesion"] = ses
    df["minuto"] = minuto
    df.attrs["escala"] = escala
    return df[["open", "close", "instrument_id", "raiz", "sesion", "minuto"]]


# =============================================================================
# 3. INGESTA MULTI-ACTIVO — retornos sincronizados y sin rolls
# =============================================================================
# [v2] Tres cosas que hacen falta para que una matriz de correlación cross-asset signifique algo:
#
#   · CIERRES SINCRONIZADOS Y LÍQUIDOS. La barra ohlcv-1d se arma por día UTC: su "cierre"
#     es la última operación antes de las 00:00 UTC (18:00-19:00 CT), en la sesión nocturna
#     más delgada. En un contrato poco operado esa operación puede ser de minutos antes que
#     la del ES, y correlacionar precios de momentos distintos subestima la correlación
#     (efecto Epps). Los settlements tampoco sirven: cada complejo liquida a otra hora
#     (metales 12:30 CT, energía 13:30, bonos y divisas 14:00, índices 15:00). Aquí todos se
#     toman al mismo corte (13:00 CT por omisión), con los cinco complejos en horario líquido.
#
#   · SIN ROLLS. Tu log(df / df.shift(1)) incluye el salto entre contratos del .n.0: en crudo
#     y gas, cada mes. Aquí el retorno del día del roll se arma con dos tramos del MISMO
#     contrato —el viejo hasta su último cierre y el nuevo desde su primera apertura— y sólo
#     se pierde la pausa de una hora entre ambos.
#
#   · FERIADOS DE UN SOLO MERCADO. Tu dropna() tira el día entero para TODOS los activos si
#     uno no operó. Aquí un mercado cerrado aporta retorno 0 ese día y el movimiento se
#     acumula en su siguiente sesión, que es lo que de verdad pasó con su precio.

def retornos_diarios(barras: pd.DataFrame, cfg: Config) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """
    Retorno de cada activo entre dos cortes consecutivos, en tres tramos:
        r_d = (resto de la sesión d−1 tras el corte) + (hueco de la pausa) + (sesión d hasta el corte)
    Dentro de una sesión los retornos van barra a barra; si cambia el instrument_id (roll),
    el hueco entre contratos se reemplaza por 0.
    """
    corte = minuto_de_sesion(cfg.corte_ct)
    series, rolls, info = {}, {}, {}
    for raiz, g in barras.groupby("raiz", sort=False):
        g = g.sort_index()
        ses = g["sesion"].to_numpy()
        inst = g["instrument_id"].to_numpy()
        lc, lo = np.log(g["close"].to_numpy()), np.log(g["open"].to_numpy())
        misma = np.r_[False, (ses[1:] == ses[:-1]) & (inst[1:] == inst[:-1])]
        lr = np.where(misma, lc - np.r_[np.nan, lc[:-1]], lc - lo)
        antes = (g["minuto"].to_numpy() + 60) <= corte
        d = pd.DataFrame({"ses": ses, "lr": lr, "antes": antes, "lo": lo, "lc": lc, "inst": inst})
        sesiones = pd.Index(np.unique(ses))
        A = d[d["antes"]].groupby("ses")["lr"].sum().reindex(sesiones, fill_value=0.0).to_numpy()
        B = d[~d["antes"]].groupby("ses")["lr"].sum().reindex(sesiones, fill_value=0.0).to_numpy()
        grp = d.groupby("ses")
        lo_ini, i_ini = grp["lo"].first().to_numpy(), grp["inst"].first().to_numpy()
        lc_fin, i_fin = grp["lc"].last().to_numpy(), grp["inst"].last().to_numpy()
        roll = np.r_[False, i_ini[1:] != i_fin[:-1]]
        hueco = np.r_[np.nan, lo_ini[1:] - lc_fin[:-1]]
        hueco[roll] = 0.0
        r = np.r_[np.nan, B[:-1] + hueco[1:] + A[1:]]
        idx = pd.DatetimeIndex(sesiones)
        series[raiz] = pd.Series(r, index=idx)
        rolls[raiz] = pd.Series(roll, index=idx)
        # para el reporte: el salto que tu script habría contado como retorno
        salto = np.r_[np.nan, lo_ini[1:] - lc_fin[:-1]]
        t_ini = pd.Series(g.index, index=ses).groupby(level=0).first()
        info[raiz] = {"sesiones": len(idx), "rolls": int(roll.sum()),
                      "salto_roll_max": float(np.nanmax(np.abs(salto[roll]))) if roll.any() else 0.0,
                      # día UTC en que el continuo cambia de contrato: ahí lo ve un cierre diario UTC
                      "rolls_utc": pd.DatetimeIndex(t_ini.to_numpy()[roll]).tz_convert("UTC")
                      .tz_localize(None).normalize()}
    R = pd.DataFrame(series).sort_index()
    R = R[[r for r in cfg.activos if r in R.columns]]
    rolls_df = pd.DataFrame(rolls).reindex(R.index).fillna(False).astype(bool)
    cob = R.notna().mean(axis=1)
    R = R[cob >= cfg.min_cobertura].iloc[1:]
    rolls_df = rolls_df.reindex(R.index)
    faltan = [r for r in cfg.activos if r not in R.columns]
    info["_dias_descartados"] = int((cob < cfg.min_cobertura).sum())
    info["_ceros_feriado"] = int(R.isna().sum().sum())
    info["_faltan"] = faltan
    return R.fillna(0.0), rolls_df, info


HORAS = 23                       # horas de una sesión de Globex, 17:00 → 16:00 CT


def retornos_horarios(barras: pd.DataFrame, cfg: Config, R: pd.DataFrame) -> np.ndarray:
    """
    Los mismos retornos de corte a corte, partidos en sus 23 horas: arreglo T × 23 × N.
    La hora 0 es la primera tras el corte de d−1; el hueco de la pausa entra en la primera
    barra de la sesión (0 si hubo roll) y un feriado acumula su hora en el día siguiente,
    igual que en retornos_diarios. La suma de las 23 horas reproduce R exactamente.

    Sirve para medir la varianza REALIZADA intradía del portafolio de riesgo: 23
    observaciones por día en lugar de un solo retorno diario.
    """
    corte = minuto_de_sesion(cfg.corte_ct)
    T, N = R.shape
    out = np.zeros((T, HORAS, N))
    for i, raiz in enumerate(R.columns):
        g = barras[barras["raiz"] == raiz].sort_index()
        if g.empty:
            continue
        ses = g["sesion"].to_numpy()
        inst = g["instrument_id"].to_numpy()
        lc, lo = np.log(g["close"].to_numpy()), np.log(g["open"].to_numpy())
        misma_ses = np.r_[False, ses[1:] == ses[:-1]]
        mismo_inst = np.r_[False, inst[1:] == inst[:-1]]
        prev = np.r_[np.nan, lc[:-1]]
        lr = np.where(misma_ses & mismo_inst, lc - prev, lc - lo)
        lr = lr + np.nan_to_num(np.where(~misma_ses & mismo_inst, lo - prev, 0.0))
        fin = g["minuto"].to_numpy() + 60                # minuto en que termina la barra
        sesiones = pd.DatetimeIndex(np.unique(ses))
        k = sesiones.get_indexer(pd.DatetimeIndex(ses)) + (fin > corte)
        dia = np.full(len(k), -1)
        dentro = k < len(sesiones)
        dia[dentro] = R.index.get_indexer(sesiones[k[dentro]])
        hora = ((fin - corte - 1) // 60) % HORAS
        m = dia >= 0
        np.add.at(out, (dia[m], hora[m], np.full(int(m.sum()), i)), lr[m])
    return out


def retornos_tu_script(barras: pd.DataFrame, activos) -> pd.DataFrame:
    """
    Lo que hace tu fetch_all_assets: cierre del DÍA UTC (el de ohlcv-1d), unión exacta con
    dropna() y log(df / df.shift(1)) sobre el continuo, rolls incluidos.
    """
    b = barras.copy()
    b["dia_utc"] = b.index.normalize()
    cierre = b.groupby(["dia_utc", "raiz"])["close"].last().unstack()
    cierre = cierre[[a for a in activos if a in cierre.columns]].dropna()
    return np.log(cierre / cierre.shift(1)).dropna()


# =============================================================================
# 4. PCA — estático, con su incertidumbre
# =============================================================================
def pca_corr(X: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """PCA de la matriz de CORRELACIÓN: autovalores (desc.), autovectores (columnas), C."""
    C = np.corrcoef(X, rowvar=False)
    lam, V = np.linalg.eigh(C)
    o = np.argsort(lam)[::-1]
    return np.clip(lam[o], 0.0, None), V[:, o], C


def orientar(V: np.ndarray, clases_: list[str]) -> np.ndarray:
    """
    [v2] El signo de un autovector es arbitrario. Tu script usa el que devuelve sklearn, que
    lo fija con una regla mecánica (el loading más grande en valor absoluto, positivo) que no
    sabe qué es "riesgo". Aquí cada factor se orienta para que la clase que más pesa en él
    tenga carga promedio POSITIVA: en el factor de riesgo, acciones arriba = risk-on; en el
    de tasas, bonos arriba = tasas abajo; en el de divisas, divisas arriba = dólar débil.
    """
    V = V.copy()
    cl = np.asarray(clases_)
    for k in range(V.shape[1]):
        v = V[:, k]
        pesos = {c: float(np.sum(v[cl == c] ** 2)) for c in set(cl)}
        c_dom = max(pesos, key=pesos.get)
        s = np.sign(np.sum(v[cl == c_dom]))
        if s == 0:
            s = np.sign(v[np.argmax(np.abs(v))])
        V[:, k] = v * (s if s != 0 else 1.0)
    return V


def congruencia(a: np.ndarray, b: np.ndarray) -> float:
    """Coeficiente de congruencia de Tucker: coseno entre dos vectores de cargas."""
    den = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(a @ b) / den if den > 0 else np.nan


def emparejar(V_ref: np.ndarray, V: np.ndarray, k: int) -> np.ndarray:
    """Reordena y re-signa las columnas de V para que las primeras k sigan a las de V_ref."""
    M = np.abs(V_ref[:, :k].T @ V)                       # k × N
    fila, col = linear_sum_assignment(-M)
    orden = col[np.argsort(fila)]
    W = V[:, orden].copy()
    for j in range(k):
        if W[:, j] @ V_ref[:, j] < 0:
            W[:, j] *= -1
    return W


def marchenko_pastur(N: int, T: int) -> float:
    """Autovalor máximo de una matriz de correlación de ruido puro (N activos, T días)."""
    return (1.0 + math.sqrt(N / T)) ** 2


def analisis_paralelo(X: np.ndarray, n: int, rng) -> np.ndarray:
    """
    Horn (1965): percentil 95 de cada autovalor cuando se barajan las columnas por separado
    (se destruye la correlación y se conservan las colas de cada activo).
    """
    T, N = X.shape
    lams = np.empty((n, N))
    for b in range(n):
        Xb = np.column_stack([rng.permutation(X[:, j]) for j in range(N)])
        lams[b] = pca_corr(Xb)[0]
    return np.quantile(lams, 0.95, axis=0)


def bootstrap_bloques(T: int, bloque: int, rng) -> np.ndarray:
    nb = int(np.ceil(T / bloque))
    ini = rng.integers(0, max(1, T - bloque + 1), size=nb)
    return (ini[:, None] + np.arange(bloque)[None, :]).ravel()[:T]


def nombrar_factor(carga: np.ndarray, activos: list[str]) -> str:
    """Nombre legible a partir de qué clase domina el factor y con qué signo."""
    cl = np.array([clase(a) for a in activos])
    tot = float(np.sum(carga ** 2)) or 1.0
    cuota = {c: float(np.sum(carga[cl == c] ** 2)) / tot for c in set(cl)}
    orden = sorted(cuota, key=cuota.get, reverse=True)
    base = {"acciones": "Riesgo (acciones)", "tasas": "Tasas / duración",
            "divisas": "Dólar (divisas vs USD)", "metales": "Metales", "energía": "Energía",
            "otro": "Otros"}
    txt = base.get(orden[0], orden[0])
    if cuota[orden[0]] < 0.55 and len(orden) > 1 and cuota[orden[1]] >= 0.2:
        txt += f" + {orden[1]}"
    return txt


@dataclass
class PCAEstatico:
    activos: list
    lam: np.ndarray
    V: np.ndarray
    C: np.ndarray
    cargas: np.ndarray          # correlación activo-factor = v·√λ
    scores: pd.DataFrame
    expl: np.ndarray
    lam_mp: float
    pa95: np.ndarray
    k_mp: int
    k_pa: int
    K: int
    carga_lo: np.ndarray
    carga_hi: np.ndarray
    expl_lo: np.ndarray
    expl_hi: np.ndarray
    congr_mitades: np.ndarray
    nombres: list


def pca_estatico(R: pd.DataFrame, cfg: Config, semilla: int = 0) -> PCAEstatico:
    rng = np.random.default_rng(semilla)
    X = R.to_numpy(float)
    T, N = X.shape
    activos = list(R.columns)
    cl = [clase(a) for a in activos]
    lam, V, C = pca_corr(X)
    V = orientar(V, cl)
    Z = (X - X.mean(0)) / X.std(0, ddof=1)
    scores = pd.DataFrame(Z @ V, index=R.index, columns=[f"PC{i + 1}" for i in range(N)])
    lam_mp = marchenko_pastur(N, T)
    pa95 = analisis_paralelo(X, cfg.n_paralelo, rng)
    k_mp = int(np.sum(lam > lam_mp))
    k_pa = int(np.argmax(lam <= pa95)) if np.any(lam <= pa95) else N
    K = int(cfg.factores or min(max(1, k_pa), N - 1))
    kb = min(N, K + 2)
    boot_c, boot_e = [], []
    for _ in range(cfg.n_boot):
        idx = bootstrap_bloques(T, cfg.bloque_boot, rng)
        _, Vb, Cb = pca_corr(X[idx])
        Vb = emparejar(V, Vb, kb)
        lb = np.einsum("ij,ik,kj->j", Vb, Cb, Vb)
        boot_c.append(Vb[:, :kb] * np.sqrt(np.clip(lb, 0, None)))
        boot_e.append(lb / N)
    boot_c, boot_e = np.array(boot_c), np.array(boot_e)
    h = T // 2
    congr = []
    lam1, V1, _ = pca_corr(X[:h])
    lam2, V2, _ = pca_corr(X[h:])
    V1, V2 = emparejar(V, V1, kb), emparejar(V, V2, kb)
    for j in range(kb):
        congr.append(abs(congruencia(V1[:, j], V2[:, j])))
    cargas = V * np.sqrt(lam)
    return PCAEstatico(activos, lam, V, C, cargas, scores, lam / N, lam_mp, pa95, k_mp, k_pa, K,
                       np.quantile(boot_c, 0.05, axis=0), np.quantile(boot_c, 0.95, axis=0),
                       np.quantile(boot_e, 0.05, axis=0), np.quantile(boot_e, 0.95, axis=0),
                       np.array(congr), [nombrar_factor(cargas[:, j], activos) for j in range(N)])


# =============================================================================
# 5. DESCOMPOSICIÓN CUANTITATIVA DEL RIESGO
# =============================================================================
def riesgo_activos(p: PCAEstatico) -> pd.DataFrame:
    """
    Fracción de la varianza de cada activo explicada por los K factores comunes (R²).

    [v2] Tu decompose_risk mezcla escalas: explained_variance_ está en unidades de retornos
    ESTANDARIZADOS (varianza 1) y returns.var() en unidades crudas (≈1e-4 al día). Su
    cociente no es un porcentaje: sale del orden de 10⁵-10⁶ %, y el "idiosincrático" sale
    enormemente negativo. En un PCA de correlación la varianza de cada activo es 1 y la
    parte sistemática es Σ_k λ_k·v_ik², que está entre 0 y 1.
    """
    K = p.K
    filas = []
    for i, a in enumerate(p.activos):
        contrib = p.lam[:K] * p.V[i, :K] ** 2
        fila = {"activo": a, "nombre": nombre(a), "clase": clase(a),
                "sistematico": float(contrib.sum()), "idiosincratico": float(1 - contrib.sum())}
        for k in range(K):
            fila[f"PC{k + 1}"] = float(contrib[k])
        filas.append(fila)
    return pd.DataFrame(filas).set_index("activo").sort_values("sistematico", ascending=False)


def parsear_pesos(texto, activos: list[str], sd: np.ndarray) -> tuple[np.ndarray, str]:
    if isinstance(texto, np.ndarray):
        return np.asarray(texto, float), "arreglo de pesos"
    if not texto:
        w = (1.0 / sd) / np.sum(1.0 / sd)
        return w, "inverso de la volatilidad (cada activo aporta el mismo riesgo por sí solo)"
    w = np.zeros(len(activos))
    for par in texto.split(","):
        k, _, v = par.partition("=")
        k = k.strip().upper()
        if k not in activos:
            sys.exit(f"❌ --pesos: {k} no está en el universo ({', '.join(activos)}).")
        w[activos.index(k)] = float(v)
    if not np.any(w):
        sys.exit("❌ --pesos: todos los pesos son cero.")
    return w, "los que pasaste con --pesos"


def riesgo_portafolio(R: pd.DataFrame, p: PCAEstatico, pesos) -> dict:
    """
    Riesgo de un portafolio repartido en factores NO correlacionados.

    Con C = V Λ Vᵀ y Σ = D C D (D = volatilidades), la exposición al factor k es
    b_k = v_kᵀ (D w) y su contribución a la varianza, λ_k·b_k². Como los factores no están
    correlacionados, las contribuciones suman EXACTAMENTE la varianza del portafolio.
      · número efectivo de apuestas (Meucci 2009): exp(−Σ p_k ln p_k) con p_k las cuotas;
        va de 1 (todo el riesgo en un factor) a N.
      · razón de diversificación (Choueifaty-Coignard 2008): Σ|w_i|σ_i / σ_p.
    """
    X = R.to_numpy(float)
    sd = X.std(0, ddof=1)
    w, origen = parsear_pesos(pesos, list(R.columns), sd)
    Sigma = np.cov(X, rowvar=False)
    var_p = float(w @ Sigma @ w)
    b = p.V.T @ (sd * w)
    contrib = p.lam * b ** 2
    cuota = contrib / contrib.sum()
    q = cuota[cuota > 1e-15]
    rc = w * (Sigma @ w) / var_p
    return {"pesos": w, "origen": origen, "vol_anual": math.sqrt(252 * var_p),
            "cuota_factor": cuota, "sistematico": float(cuota[:p.K].sum()),
            "enb": float(np.exp(-np.sum(q * np.log(q)))),
            "dr": float(np.sum(np.abs(w) * sd) / math.sqrt(var_p)),
            "rc_activo": pd.Series(rc, index=R.columns), "cierre_exacto": float(contrib.sum() / var_p)}


# =============================================================================
# 6. ANÁLISIS DINÁMICO ESTRUCTURAL — PCA rodante
# =============================================================================
@dataclass
class PCARodante:
    fechas: pd.DatetimeIndex
    expl: np.ndarray            # T × N  (fracción de varianza de cada componente)
    ar: np.ndarray              # absorption ratio
    dar: np.ndarray             # ΔAR estandarizado
    k_mp: np.ndarray
    n80: np.ndarray
    n90: np.ndarray
    cargas: np.ndarray          # T × N × 3, orientadas y alineadas
    congr_prev: np.ndarray      # T × 3
    congr_est: np.ndarray       # T × 3
    roro: np.ndarray            # retorno del portafolio de riesgo (PC1), en %
    rv_riesgo: np.ndarray       # su varianza realizada intradía (23 horas), en %²
    turb: np.ndarray            # turbulencia / N
    turb_mag: np.ndarray        # sólo magnitud / N
    r2: np.ndarray              # R² sistemático promedio
    port_sis: np.ndarray        # fracción sistemática del portafolio
    port_enb: np.ndarray
    corr_ab: np.ndarray         # correlación acciones-bonos (ES-ZN o la que haya)
    k_ar: int


def pca_rodante(R: pd.DataFrame, p: PCAEstatico, cfg: Config, pesos_w: np.ndarray,
                horas: np.ndarray | None = None) -> PCARodante:
    """
    Ventana de `ventana` días que termina el día ANTERIOR a cada fecha: todo es causal.

    [v2] Tres diferencias con tu rolling_pca:
      · se calculan TODOS los componentes. Tu n_components=5 corta la varianza acumulada: si
        el 90 % necesita 7 factores, tu n_factors_90 dice 5.
      · cada ventana se alinea con la anterior (signo y orden, con asignación húngara): sin
        eso los loadings de PC1 pueden cambiar de signo entre ventanas y la serie brinca.
      · se re-estima cada día, no cada 20: con N = 16 cuesta milisegundos.

    Con `horas` (T × 23 × N, de retornos_horarios) mide además la varianza realizada
    intradía del portafolio de riesgo, con los pesos de la ventana anterior. Sin ellas usa
    el cuadrado del retorno diario (mucho más ruidoso).
    """
    X = R.to_numpy(float)
    T, N = X.shape
    W = int(cfg.ventana)
    cl = [clase(a) for a in R.columns]
    k_ar = max(1, int(round(N / 5)))
    K = p.K
    kt = min(3, N)
    lam_mp = marchenko_pastur(N, W)
    n_out = T - W
    expl = np.full((n_out, N), np.nan)
    cargas = np.full((n_out, N, kt), np.nan)
    cp, ce = np.full((n_out, kt), np.nan), np.full((n_out, kt), np.nan)
    ar, kmp, n80, n90 = (np.full(n_out, np.nan) for _ in range(4))
    roro, turb, tmag, r2, psis, penb, cab, rv = (np.full(n_out, np.nan) for _ in range(8))
    ia = next((R.columns.get_loc(a) for a in ("ES", "NQ", "YM", "RTY") if a in R.columns), None)
    ib = next((R.columns.get_loc(a) for a in ("ZN", "ZF", "ZB", "ZT") if a in R.columns), None)
    V_prev = None
    for j, t in enumerate(range(W, T)):
        win = X[t - W:t]
        mu, sd = win.mean(0), win.std(0, ddof=1)
        lam, V, C = pca_corr(win)
        V = orientar(V, cl) if V_prev is None else emparejar(V_prev, V, N)
        if V_prev is not None:
            cp[j] = [congruencia(V[:, k], V_prev[:, k]) for k in range(kt)]
        lam = np.array([float(V[:, k] @ C @ V[:, k]) for k in range(N)])
        V_prev = V
        ce[j] = [abs(congruencia(V[:, k], p.V[:, k])) for k in range(kt)]
        orden = np.sort(lam)[::-1]
        expl[j] = lam / N
        cum = np.cumsum(orden) / N
        ar[j] = orden[:k_ar].sum() / N
        n80[j] = int(np.argmax(cum >= 0.8)) + 1
        n90[j] = int(np.argmax(cum >= 0.9)) + 1
        kmp[j] = int(np.sum(orden > lam_mp))
        cargas[j] = V[:, :kt] * np.sqrt(np.clip(lam[:kt], 0, None))
        r2[j] = float(np.mean(np.sum(lam[:K] * V[:, :K] ** 2, axis=1)))
        # portafolio de riesgo: PC1 sobre retornos crudos, exposición bruta 1
        w1 = V[:, 0] / sd
        w1 = w1 / np.sum(np.abs(w1))
        roro[j] = float((X[t] - mu) @ w1) * 100.0
        rv[j] = (float(np.sum((horas[t] @ w1) ** 2)) if horas is not None
                 else float(X[t] @ w1) ** 2) * 1e4
        S = np.cov(win, rowvar=False)
        dx = X[t] - mu
        try:
            turb[j] = float(dx @ np.linalg.solve(S, dx)) / N
        except np.linalg.LinAlgError:
            turb[j] = np.nan
        tmag[j] = float(np.sum((dx / sd) ** 2)) / N
        b = V.T @ (sd * pesos_w)
        c_ = lam * b ** 2
        psis[j] = float(c_[:K].sum() / c_.sum())
        q = c_ / c_.sum()
        q = q[q > 1e-15]
        penb[j] = float(np.exp(-np.sum(q * np.log(q))))
        if ia is not None and ib is not None:
            cab[j] = C[ia, ib]
    s = pd.Series(ar)
    dar = ((s.rolling(15, min_periods=10).mean() - s.rolling(W, min_periods=60).mean())
           / s.rolling(W, min_periods=60).std()).to_numpy()
    return PCARodante(R.index[W:], expl, ar, dar, kmp, n80, n90, cargas, cp, ce, roro, rv,
                      turb, tmag, r2, psis, penb, cab, k_ar)


def tu_rolling(R: pd.DataFrame, ventana: int = 120, paso: int = 20, n_comp: int = 5) -> dict:
    """
    Tu rolling_pca tal cual: n_components = 5, sin alinear, re-estimación cada 20 días, y el
    signo que pone sklearn (el loading de mayor valor absoluto, positivo).
    """
    X = R.to_numpy(float)
    ia = [R.columns.get_loc(a) for a in ("ES", "NQ", "YM", "RTY") if a in R.columns]
    n90, n90_real, invertido, v_prev, cambios = [], [], [], None, 0
    for i in range(ventana, len(X), paso):
        lam, V, _ = pca_corr(X[i - ventana:i])
        for k in range(V.shape[1]):
            if V[np.argmax(np.abs(V[:, k])), k] < 0:
                V[:, k] *= -1
        cum5 = np.cumsum(lam[:n_comp]) / len(lam)
        n90.append(int(np.argmax(cum5 >= 0.9)) + 1 if (cum5 >= 0.9).any() else n_comp)
        n90_real.append(int(np.argmax(np.cumsum(lam) / len(lam) >= 0.9)) + 1)
        if ia:
            invertido.append(float(np.mean(V[ia, 0])) < 0)
        if v_prev is not None and V[:, 0] @ v_prev < 0:
            cambios += 1
        v_prev = V[:, 0]
    return {"n90": np.array(n90), "n90_real": np.array(n90_real),
            "invertido": np.array(invertido, dtype=bool), "cambios_signo": cambios,
            "ventanas": len(n90)}


def tu_estatico(R: pd.DataFrame) -> dict:
    """Tu run_pca + decompose_risk + analyze_pc1_regimes, con sus mismas escalas."""
    X = R.to_numpy(float)
    T, N = X.shape
    Z = (X - X.mean(0)) / X.std(0)                       # StandardScaler (ddof = 0)
    C = (Z.T @ Z) / (T - 1)                               # la covarianza que usa sklearn
    lam, V = np.linalg.eigh(C)
    o = np.argsort(lam)[::-1]
    lam, V = lam[o], V[:, o]
    for k in range(N):
        if V[np.argmax(np.abs(V[:, k])), k] < 0:
            V[:, k] *= -1
    sistem = np.sum(V[:, :3] ** 2 * lam[:3], axis=1)
    total = R.var().to_numpy()
    pct_sis = sistem / total * 100
    pc1 = Z @ V[:, 0]
    mu_, sd_ = pc1.mean(), pc1.std(ddof=1)
    on, off = pc1 >= mu_ + 2 * sd_, pc1 <= mu_ - 2 * sd_
    return {"pct_sis": pd.Series(pct_sis, index=R.columns), "pc1": pd.Series(pc1, index=R.index),
            "on": on, "off": off, "banda": 2 * sd_, "V": V, "lam": lam}


# =============================================================================
# 7. RÉGIMEN SISTÉMICO — Risk-On / Risk-Off
# =============================================================================
def hmm_ajustar(x: np.ndarray, ini: dict | None = None, iters: int = 300, tol: float = 1e-9) -> dict:
    """
    Modelo de Markov oculto gaussiano de 2 estados (Hamilton 1989), por EM con escalamiento,
    sobre x = log de la varianza realizada intradía del portafolio de riesgo. El estado 1 es
    el de MAYOR nivel: más varianza = risk-off. No se etiqueta por el retorno medio: medido en
    simulación, con ~40 días de estrés la media observada sale POSITIVA por puro ruido (+0.29 %
    diario en ES cuando la verdadera es negativa) y la etiqueta se invierte. La varianza, en
    cambio, separa los estados sin ambigüedad.
    """
    x = np.asarray(x, float)
    n = len(x)
    m, s = float(np.mean(x)), float(np.std(x)) or 1.0
    par = ini or {"pi": np.array([0.8, 0.2]), "A": np.array([[0.97, 0.03], [0.06, 0.94]]),
                  "mu": np.array([m - 0.4 * s, m + 0.8 * s]), "sd": np.array([0.8 * s, 1.2 * s])}
    pi, A, mu, sd = (np.array(par[k], float) for k in ("pi", "A", "mu", "sd"))
    ll_prev = -np.inf
    for _ in range(iters):
        B = np.exp(-0.5 * ((x[:, None] - mu) / sd) ** 2) / (sd * math.sqrt(2 * math.pi)) + 1e-300
        al, c = np.empty((n, 2)), np.empty(n)
        al[0] = pi * B[0]
        c[0] = al[0].sum()
        al[0] /= c[0]
        for t in range(1, n):
            al[t] = (al[t - 1] @ A) * B[t]
            c[t] = al[t].sum()
            al[t] /= c[t]
        be = np.empty((n, 2))
        be[-1] = 1.0
        for t in range(n - 2, -1, -1):
            be[t] = (A @ (B[t + 1] * be[t + 1])) / c[t + 1]
        g = al * be
        g /= g.sum(1, keepdims=True)
        xi = (al[:-1, :, None] * A[None] * (B[1:] * be[1:])[:, None, :]) / c[1:, None, None]
        pi = g[0]
        A = xi.sum(0) / xi.sum(0).sum(1, keepdims=True)
        mu = (g * x[:, None]).sum(0) / g.sum(0)
        sd = np.sqrt((g * (x[:, None] - mu) ** 2).sum(0) / g.sum(0))
        sd = np.maximum(sd, 1e-3 * s)
        ll = float(np.sum(np.log(c)))
        if abs(ll - ll_prev) < tol * max(1.0, abs(ll)):
            break
        ll_prev = ll
    if mu[0] > mu[1]:                                      # estado 1 = más varianza
        pi, mu, sd = pi[::-1], mu[::-1], sd[::-1]
        A = A[::-1, ::-1]
    return {"pi": pi, "A": A, "mu": mu, "sd": sd, "ll": ll}


def hmm_filtrar(x: np.ndarray, par: dict) -> np.ndarray:
    """P(estado 1 | x_1..x_t): sólo hacia adelante, así que no mira al futuro."""
    x = np.asarray(x, float)
    pi, A, mu, sd = par["pi"], par["A"], par["mu"], par["sd"]
    B = np.exp(-0.5 * ((x[:, None] - mu) / sd) ** 2) / sd + 1e-300
    al = pi * B[0]
    al /= al.sum()
    out = np.empty(len(x))
    out[0] = al[1]
    for t in range(1, len(x)):
        al = (al @ A) * B[t]
        al /= al.sum()
        out[t] = al[1]
    return out


@dataclass
class Regimen:
    fechas: pd.DatetimeIndex
    p_off: np.ndarray
    etiqueta: np.ndarray
    par: dict
    duracion: dict


def detectar_regimen(rod: PCARodante, cfg: Config) -> Regimen:
    """
    [v2] Tu analyze_pc1_regimes marca "Risk-On" los días con PC1 > +2σ y "Risk-Off" los de
    PC1 < −2σ. Eso no es un régimen: es el 2 % de días con el movimiento más grande del
    factor, sin persistencia (un día risk-off rodeado de días normales). Y tres detalles: la
    banda usa media y desviación de TODA la muestra (mira al futuro); el "régimen actual"
    del reporte compara PC1 contra 2 en vez de contra la banda de ±2σ (con σ ≈ 2.2 son
    umbrales distintos); y el signo de PC1 no está fijado.

    Aquí el régimen es un ESTADO: un modelo de Markov oculto de dos estados, re-estimado
    cada `hmm_refit` días sólo con el pasado, y la probabilidad FILTRADA de estar en
    risk-off. Se complementa con el absorption ratio (fragilidad) y la turbulencia (sorpresa).

    El Markov no lee el retorno diario del portafolio de riesgo sino el log de su varianza
    realizada INTRADÍA (23 retornos horarios por día). Un solo retorno diario es una
    observación muy ruidosa de la volatilidad del día; 23 horas la miden mucho mejor. Medido
    en simulación (6 semillas, régimen verdadero conocido, sólo días fuera de muestra):
                                  exactitud   precisión risk-off   exhaustividad
        retorno diario de PC1      71–91 %          70–93 %           16–75 %  (media 49 %)
        varianza intradía de PC1   92–96 %          66–96 %           91–96 %  (media 94 %)
    La precisión casi no cambia; lo que cambia es que el retorno diario se pierde la mitad
    de los días de estrés. La precisión más baja (66 %) sale de una semilla con nueve meses
    seguidos de calma: ahí cualquier día de volatilidad alta cuenta como falsa alarma.
    """
    x = np.log(np.maximum(rod.rv_riesgo, 1e-10))
    n = len(x)
    p = np.full(n, np.nan)
    par = None
    for t0 in range(cfg.hmm_min, n, cfg.hmm_refit):
        par = hmm_ajustar(x[:t0], ini=par)
        t1 = min(n, t0 + cfg.hmm_refit)
        p[t0:t1] = hmm_filtrar(x[:t1], par)[t0:t1]
    et = np.full(n, "—", dtype=object)
    ok = np.isfinite(p)
    frag = np.nan_to_num(rod.dar, nan=-np.inf) >= cfg.dar_umbral
    et[ok] = np.where(p[ok] >= cfg.umbral_prob, "Risk-Off", np.where(frag[ok], "Frágil", "Risk-On"))
    dur = {}
    if par is not None:
        dur = {"Risk-On": 1.0 / max(1e-9, 1.0 - par["A"][0, 0]),
               "Risk-Off": 1.0 / max(1e-9, 1.0 - par["A"][1, 1])}
    return Regimen(rod.fechas, p, et, par or {}, dur)


def auditar_regimen(R: pd.DataFrame, reg: Regimen, rod: PCARodante, cfg: Config) -> dict:
    """
    ¿Sirve la etiqueta? La de hoy (conocida al corte) contra lo que pasa DESPUÉS:
      · retorno del día SIGUIENTE de cada activo por régimen (t de Newey-West);
      · volatilidad realizada del factor de riesgo en los próximos `horizonte_vol` días.

    [v2] Tu tabla de "retornos medios por régimen" usa los retornos del MISMO día con que
    se define el régimen. PC1 es una combinación de esos retornos, así que los activos con
    carga positiva salen muy positivos en "Risk-On" por construcción: es una tautología, no
    un hallazgo.
    """
    Rr = R.reindex(reg.fechas)
    sig = Rr.shift(-1)
    filas = []
    for et in ("Risk-On", "Frágil", "Risk-Off"):
        m = reg.etiqueta == et
        for a in R.columns:
            x = sig[a].to_numpy()[m]
            x = x[np.isfinite(x)]
            filas.append({"regimen": et, "activo": a, "n": len(x),
                          "media_bps": float(np.mean(x)) * 1e4 if len(x) else np.nan,
                          "t": t_newey_west(x - np.nanmean(sig[a]), 1)})
    tabla = pd.DataFrame(filas)
    h = cfg.horizonte_vol
    r = pd.Series(rod.roro)
    vol_fut = (r[::-1].rolling(h, min_periods=h).std()[::-1].shift(-1) * math.sqrt(252)).to_numpy()
    vol = {}
    for et in ("Risk-On", "Frágil", "Risk-Off"):
        m = (reg.etiqueta == et) & np.isfinite(vol_fut)
        vol[et] = (float(np.mean(vol_fut[m])), int(m.sum())) if m.any() else (np.nan, 0)
    return {"tabla": tabla, "vol_fut": vol}


# =============================================================================
# 8. SIMULADOR — un mundo con factores, regímenes y un quiebre CONOCIDOS
# =============================================================================
def simular(cfg: Config, n_dias: int | None = None, semilla: int | None = None,
            quiebre: bool = True, feriados: int = 4) -> tuple[pd.DataFrame, dict]:
    """
    Barras de 1 h de todo el universo, generadas desde tres factores conocidos:
      F1 riesgo (acciones, cobre, crudo, AUD, MXN +; yen −), F2 tasas, F3 dólar.
    Un régimen de Markov (risk-on / risk-off) cambia la media y la volatilidad de F1. A la
    mitad de la muestra la carga de los bonos en F1 pasa de −0.30 a +0.20: la correlación
    acciones-bonos cambia de signo, como en 2022. Además: colas gruesas (t5), rolls con
    salto de nivel y feriados de un solo mercado.
    """
    D = int(n_dias or cfg.sim_dias)
    rng = np.random.default_rng(cfg.sim_semilla if semilla is None else semilla)
    act = list(cfg.activos)
    N = len(act)
    cl = [clase(a) for a in act]
    # --- régimen ---
    P = np.array([[0.985, 0.015], [0.04, 0.96]])
    s = np.zeros(D, dtype=int)
    for d in range(1, D):
        s[d] = rng.choice(2, p=P[s[d - 1]])
    base = {"ES": (1.0, 0, 0), "NQ": (1.25, 0, 0), "YM": (0.9, 0, 0), "RTY": (1.15, 0, 0),
            "ZT": (0, 0.25, 0), "ZF": (0, 0.55, 0), "ZN": (0, 1.0, 0), "ZB": (0, 1.8, 0),
            "GC": (0.1, 0.2, 0.6), "SI": (0.45, 0.1, 0.8), "HG": (0.6, 0, 0.35),
            "CL": (0.7, 0, 0.1), "NG": (0.2, 0, 0), "6E": (0.1, 0.05, 1.0),
            "6J": (-0.3, 0.2, 0.7), "6B": (0.2, 0, 0.9), "6A": (0.45, 0, 0.8),
            "6C": (0.3, 0, 0.6), "6S": (-0.15, 0.1, 0.9), "6M": (0.4, 0, 0.5)}
    idio = {"acciones": 0.004, "tasas": 0.0015, "metales": 0.011, "energía": 0.02, "divisas": 0.003}
    Bm = np.array([base.get(a, (0.3, 0, 0)) for a in act], float)
    Bm2 = Bm.copy()
    for i, a in enumerate(act):
        if cl[i] == "tasas":
            Bm[i, 0] = -0.30 * Bm[i, 1]
            Bm2[i, 0] = 0.20 * Bm[i, 1]
    corte_d = D // 2 if quiebre else D
    sd_i = np.array([0.032 if a == "NG" else idio.get(c, 0.005) for a, c in zip(act, cl)])

    # --- retornos HORARIOS independientes; el diario es su suma ---
    # Cada hora tiene su propio choque de cada factor y de cada activo, con varianza
    # proporcional a su peso en el día. Así dos ventanas que no coinciden con el corte (un
    # cierre UTC, por ejemplo) quedan independientes, como en un mercado de verdad. Las
    # colas gruesas diarias salen de una mezcla de escala: una t5 es una normal con varianza
    # aleatoria, y aquí esa varianza la sortea cada día.
    H = 23
    c = minuto_de_sesion(cfg.corte_ct) // 60             # primer hora DESPUÉS del corte
    S = D + 1
    fechas = pd.bdate_range(pd.Timestamp(cfg.start).normalize()
                            - pd.Timedelta(days=cfg.dias_calentamiento), periods=S)
    perfil = np.r_[np.full(15, 0.6), np.full(8, 1.6)]    # madrugada tranquila, día activo
    orden_h = np.r_[np.arange(c, H), np.arange(0, c)]    # horas del "día" d: tras el corte de d−1 …
    w = perfil[orden_h] / perfil[orden_h].sum()
    mezcla = lambda *forma: 1.0 / np.sqrt(rng.chisquare(5, forma) / 5) / math.sqrt(5 / 3)
    sw = np.sqrt(w)[None, :]
    m1 = mezcla(D)[:, None]
    f1 = (np.where(s == 0, 0.0006, -0.0015)[:, None] * w[None, :]
          + np.where(s == 0, 0.008, 0.019)[:, None] * m1 * sw * rng.normal(size=(D, H)))
    f2 = 0.005 * sw * rng.normal(size=(D, H))
    f3 = 0.004 * sw * rng.normal(size=(D, H))
    Fh = np.stack([f1, f2, f3], axis=2)                  # D × H × 3
    antes_q = (np.arange(D) < corte_d)[:, None, None]
    piezas_todas = np.where(antes_q, Fh @ Bm.T, Fh @ Bm2.T)
    piezas_todas += (sd_i[None, None, :] * mezcla(D, 1, N) * sw[:, :, None]
                     * rng.normal(size=(D, H, N)))
    inc = np.zeros((S, H, N))
    for d in range(D):
        inc[d, c:, :] = piezas_todas[d, :H - c]          # cola de la sesión d
        inc[d + 1, :c, :] = piezas_todas[d, H - c:]      # cabeza de la sesión d+1
    p0 = np.log(np.array([CATALOGO.get(a, ("", "", 100.0))[2] for a in act]))
    ef = p0 + np.cumsum(inc.reshape(S * H, N), axis=0).reshape(S, H, N)
    ef_ini = ef - inc                                    # log-precio al abrir cada barra
    # --- rolls: salto de nivel del continuo al abrir la sesión ---
    cada = {"energía": 21, "metales": 42}
    salto_tam = {"energía": 0.02, "metales": 0.004, "acciones": 0.003, "tasas": 0.006, "divisas": 0.002}
    base_niv = np.zeros((S, N))
    instr = np.zeros((S, N), dtype=int)
    es_roll = np.zeros((S, N), dtype=bool)
    for i, a in enumerate(act):
        k = cada.get(cl[i], 63)
        tam = 0.05 if a == "NG" else salto_tam.get(cl[i], 0.003)
        for sess in range(int(rng.integers(5, k)), S, k):
            es_roll[sess, i] = True
        base_niv[:, i] = np.cumsum(es_roll[:, i] * rng.choice([-1, 1], S) * tam * rng.uniform(0.5, 1.5, S))
        instr[:, i] = 1000 * (i + 1) + np.cumsum(es_roll[:, i])
    obs_c = np.exp(ef + base_niv[:, None, :])
    obs_o = np.exp(ef_ini + base_niv[:, None, :])
    # --- feriados de un solo mercado (tasas) ---
    cerrado = np.zeros((S, N), dtype=bool)
    tasas = [i for i, cc in enumerate(cl) if cc == "tasas"]
    for i in tasas:
        for sess in rng.choice(np.arange(10, S - 10), size=feriados, replace=False):
            if not es_roll[sess, i] and not es_roll[sess + 1, i]:
                cerrado[sess, i] = True
    # --- marcas de tiempo y DataFrame al estilo de to_df() ---
    pared = (np.asarray(fechas, dtype="datetime64[ns]")[:, None] - np.timedelta64(DESFASE_H, "h")
             + (np.arange(H) * 60).astype("timedelta64[m]")[None, :])
    idx = pd.DatetimeIndex(pared.ravel()).tz_localize(cfg.tz_mercado, ambiguous="NaT",
                                                      nonexistent="NaT")
    partes = []
    for i, a in enumerate(act):
        vivo = ~np.repeat(cerrado[:, i], H) & ~idx.isna()
        partes.append(pd.DataFrame({
            "open": obs_o[:, :, i].ravel()[vivo], "close": obs_c[:, :, i].ravel()[vivo],
            "instrument_id": np.repeat(instr[:, i], H)[vivo], "symbol": f"{a}.n.0",
            "ts_event": idx[vivo].tz_convert("UTC")}))
    df = pd.concat(partes).set_index("ts_event").sort_index()
    # --- la verdad: retorno de corte a corte del precio EFICIENTE (sin rolls) ---
    snap = pd.DataFrame(ef[:, c - 1, :], index=fechas, columns=act)
    snap = snap.mask(pd.DataFrame(cerrado, index=fechas, columns=act))
    r_ok = snap.ffill().diff()
    r_ok = r_ok.mask(pd.DataFrame(cerrado, index=fechas, columns=act))
    verdad = {"retornos": r_ok.iloc[1:], "regimen": pd.Series(s, index=fechas[1:]),
              "cargas": Bm, "cargas_post": Bm2, "quiebre": fechas[1:][corte_d] if quiebre else None,
              "rolls": pd.DataFrame(es_roll, index=fechas, columns=act),
              "factores": 3, "sd_idio": sd_i}
    return df, verdad


# =============================================================================
# 9. EL CÁLCULO COMPLETO
# =============================================================================
@dataclass
class Resultado:
    cfg: Config
    R_total: pd.DataFrame
    R: pd.DataFrame             # ventana reportada
    rolls: pd.DataFrame
    info: dict
    est: PCAEstatico
    riesgo: pd.DataFrame
    port: dict
    rod: PCARodante
    reg: Regimen
    aud: dict
    tu: dict
    tu_rol: dict
    tu_R: pd.DataFrame
    diag: dict
    verdad: dict | None = None
    medicion: dict | None = None


def analizar(barras: pd.DataFrame, cfg: Config, verdad: dict | None = None) -> Resultado:
    R_total, rolls, info = retornos_diarios(barras, cfg)
    if len(R_total) < cfg.ventana + 60:
        sys.exit(f"❌ Sólo hay {len(R_total)} días; hacen falta más de {cfg.ventana + 60}. "
                 "Sube --calentamiento o baja --ventana.")
    ini, fin = pd.Timestamp(cfg.start).normalize(), pd.Timestamp(cfg.end)
    R = R_total[(R_total.index >= ini) & (R_total.index < fin)]
    if len(R) < 60:
        R = R_total.iloc[-max(60, len(R_total) // 2):]
    est = pca_estatico(R, cfg)
    riesgo = riesgo_activos(est)
    port = riesgo_portafolio(R, est, cfg.pesos)
    horas = retornos_horarios(barras, cfg, R_total)
    rod = pca_rodante(R_total, est, cfg, port["pesos"], horas)
    reg = detectar_regimen(rod, cfg)
    aud = auditar_regimen(R_total, reg, rod, cfg)
    tu_R = retornos_tu_script(barras, cfg.activos)
    tu_R = tu_R[(tu_R.index >= ini.tz_localize("UTC")) & (tu_R.index < fin.tz_localize("UTC"))] \
        if len(tu_R) else tu_R
    tu = tu_estatico(tu_R) if len(tu_R) > 30 else {}
    tu_rol = tu_rolling(tu_R) if len(tu_R) > 150 else {}
    diag = {"escala": barras.attrs.get("escala", "float"), "n_barras": int(len(barras))}
    res = Resultado(cfg, R_total, R, rolls, info, est, riesgo, port, rod, reg, aud, tu, tu_rol,
                    tu_R, diag, verdad)
    if verdad is not None:
        res.medicion = medir_contra_verdad(res)
    return res


def medir_contra_verdad(res: Resultado) -> dict:
    v, cfg = res.verdad, res.cfg
    out = {}
    tr = v["retornos"].reindex(res.R_total.index)
    dif = (res.R_total - tr.fillna(0.0)).abs().to_numpy()
    out["error_retornos"] = float(np.nanmax(dif))
    # subespacio de factores: ángulos principales entre las cargas verdaderas y las top-3
    Q1, _ = np.linalg.qr(v["cargas_post"] / res.R.to_numpy().std(0)[:, None])
    Q2, _ = np.linalg.qr(res.est.V[:, :3])
    out["cos_angulos"] = np.linalg.svd(Q1.T @ Q2, compute_uv=False)
    reg_v = v["regimen"].reindex(res.reg.fechas).to_numpy()
    ok = np.isfinite(res.reg.p_off) & np.isfinite(reg_v)
    pred = res.reg.p_off[ok] >= cfg.umbral_prob
    real = reg_v[ok] == 1
    out["hmm"] = {"exactitud": float(np.mean(pred == real)),
                  "precision": float((pred & real).sum() / max(1, pred.sum())),
                  "exhaustividad": float((pred & real).sum() / max(1, real.sum())),
                  "dias_off": int(real.sum())}
    if res.tu:
        tr_on = res.tu["off"]
        rv = v["regimen"].reindex(pd.DatetimeIndex(res.tu_R.index.tz_convert("UTC")
                                                   .tz_localize(None).normalize())).to_numpy()
        m = np.isfinite(rv)
        out["tu_regimen"] = {"marcados_off": int(tr_on.sum()),
                             "precision": float((tr_on[m] & (rv[m] == 1)).sum() / max(1, tr_on[m].sum())),
                             "exhaustividad": float((tr_on[m] & (rv[m] == 1)).sum() / max(1, (rv[m] == 1).sum()))}
    ar = res.rod.ar
    out["ar_por_regimen"] = {k: float(np.nanmean(ar[(reg_v == k) & np.isfinite(ar)]))
                             for k in (0, 1) if np.any(reg_v == k)}
    if v.get("quiebre") is not None and np.isfinite(res.rod.corr_ab).any():
        q = v["quiebre"]
        f = res.rod.fechas
        antes = res.rod.corr_ab[(f < q)]
        despues = res.rod.corr_ab[(f >= q + pd.Timedelta(days=int(cfg.ventana * 1.5)))]
        out["corr_ab"] = (float(np.nanmean(antes)), float(np.nanmean(despues)))
    return out


# =============================================================================
# 10. REPORTES
# =============================================================================
def reporte_ingesta(res: Resultado) -> None:
    cfg, R, info = res.cfg, res.R, res.info
    ct, mx = reloj(R.index[-1], minuto_de_sesion(cfg.corte_ct), cfg)
    _titulo("1 · INGESTA MULTI-ACTIVO (cross-asset)")
    print(f"  Barras de 1 h: {res.diag['n_barras']:,} (precios: {res.diag['escala']}) · corte "
          f"sincronizado {ct:%H:%M} CT = {mx:%H:%M} CDMX = {ct.tz_convert('UTC'):%H:%M} UTC")
    print(f"  Días en tu ventana: {len(R):,} · con historia previa: {len(res.R_total):,} · "
          f"descartados por cobertura < {cfg.min_cobertura:.0%}: {info['_dias_descartados']}")
    if info["_faltan"]:
        print(f"  ⚠ Sin datos: {', '.join(info['_faltan'])}")
    print()
    print(f"  {'activo':<7s}{'nombre':<20s}{'clase':<10s}{'rolls':>6s}{'salto máx':>11s}"
          f"{'vol anual':>11s}{'feriados':>10s}")
    vol = R.std() * math.sqrt(252)
    for a in R.columns:
        i = info.get(a, {})
        fer = int((res.R_total[a] == 0).sum())
        print(f"  {a:<7s}{nombre(a):<20s}{clase(a):<10s}{i.get('rolls', 0):>6d}"
              f"{_pct(i.get('salto_roll_max', 0), 2, 10)}{_pct(vol[a], 1, 10)}{fer:>10d}")
    print("  'salto máx' = el mayor brinco de precio en un roll: tu script lo cuenta como retorno.")
    print("  Divisas: futuros de CME cotizan USD por unidad extranjera → sube = el DÓLAR se debilita.")


def reporte_tu_script(res: Resultado) -> None:
    tu, tr = res.tu, res.tu_rol
    _titulo("2 · TU SCRIPT CONTRA EL MÓDULO, SOBRE LOS MISMOS DATOS")
    if not tu:
        print("  (no hay suficientes días para replicarlo)")
        return
    ps = tu["pct_sis"]
    print("  Tu '% Sistemático' (decompose_risk) contra la fracción sistemática real (R²):")
    print(f"      {'activo':<6s}{'tu script':>16s}{'módulo':>10s}")
    for a in list(ps.sort_values(ascending=False).index[:6]):
        print(f"      {a:<6s}{ps[a]:>15,.0f}%{_pct(res.riesgo.loc[a, 'sistematico'], 1, 9)}")
    print("  Tu script divide una varianza de retornos ESTANDARIZADOS entre una de retornos CRUDOS.")
    print()
    Rtu = res.tu_R
    fechas_tu = pd.DatetimeIndex(Rtu.index.tz_convert("UTC").tz_localize(None).normalize())
    roll_var = {}
    for a in res.R.columns:
        if a in Rtu.columns and a in res.info:
            m = fechas_tu.isin(res.info[a]["rolls_utc"])
            x2 = Rtu[a].to_numpy() ** 2
            if m.any() and x2.sum() > 0:
                roll_var[a] = (float(x2[m].sum() / x2.sum()), float(m.mean()))
    if roll_var:
        peores = sorted(roll_var, key=lambda k: roll_var[k][0] / max(roll_var[k][1], 1e-9),
                        reverse=True)[:4]
        print("  Rolls dentro de tus retornos — parte de la varianza que cae en días de roll:")
        print("      " + " · ".join(f"{a} {roll_var[a][0]:.0%} en el {roll_var[a][1]:.0%} de los días"
                                   for a in peores))
    if tr:
        print()
        print(f"  Tu rolling (120 días, cada 20, n_components = 5), {tr['ventanas']} ventanas:")
        print(f"      n_factors_90 topado en 5          : {np.mean(tr['n90'] == 5):.0%} de las ventanas")
        print(f"      factores que de verdad pide el 90 %: {int(np.min(tr['n90_real']))}-"
              f"{int(np.max(tr['n90_real']))}")
        if len(tr["invertido"]):
            print(f"      PC1 con acciones NEGATIVAS (su 'Risk-On' al revés): "
                  f"{np.mean(tr['invertido']):.0%} de las ventanas")
    print()
    print(f"  Tu régimen: banda ±2σ de PC1 = ±{tu['banda']:.2f}, pero el 'régimen actual' del "
          "reporte compara contra ±2.")
    dentro = (np.abs(tu["pc1"]) > 2) & (np.abs(tu["pc1"]) < tu["banda"])
    print(f"  {dentro.mean():.0%} de los días son 'RISK' en una parte de tu reporte y 'normal' en la otra.")
    t_on, t_off = tu["on"], tu["off"]
    Rn = Rtu.to_numpy()
    eq = [Rtu.columns.get_loc(a) for a in ("ES", "NQ") if a in Rtu.columns]
    if eq and t_on.any() and t_off.any():
        mismo = (Rn[t_on][:, eq].mean() - Rn[t_off][:, eq].mean()) * 1e4
        sig = np.r_[Rn[1:], np.full((1, Rn.shape[1]), np.nan)]
        despues = (np.nanmean(sig[t_on][:, eq]) - np.nanmean(sig[t_off][:, eq])) * 1e4
        print(f"  Acciones en 'Risk-On' menos 'Risk-Off' — el MISMO día: {mismo:+.0f} bps; el día "
              f"SIGUIENTE: {despues:+.0f} bps.")
        print("  Lo primero es la definición de PC1 (tautología); lo segundo es lo que sirve.")


def reporte_estatico(res: Resultado) -> None:
    p = res.est
    _titulo(f"3 · DESCOMPOSICIÓN FACTORIAL (PCA estático, {len(res.R)} días × {len(p.activos)} activos)")
    print(f"  Factores con señal: análisis paralelo = {p.k_pa} · Marchenko-Pastur = {p.k_mp} "
          f"(λ > {p.lam_mp:.2f}) · se usan K = {p.K}")
    print(f"  {'':5s}{'λ':>7s}{'% var':>8s}{'IC 90 %':>17s}{'acum.':>8s}{'paralelo 95':>13s}"
          f"{'estab.':>8s}   nombre")
    kb = len(p.congr_mitades)
    for k in range(min(len(p.lam), max(p.K + 2, 5))):
        ic = (f"{100 * p.expl_lo[k]:5.1f}–{100 * p.expl_hi[k]:5.1f} %" if k < kb else "")
        est = f"{p.congr_mitades[k]:.2f}" if k < kb else ""
        marca = "  ←" if k < p.K else ""
        print(f"  PC{k + 1:<3d}{p.lam[k]:7.2f}{100 * p.expl[k]:7.1f}%{ic:>17s}"
              f"{100 * np.cumsum(p.expl)[k]:7.1f}%{p.pa95[k]:13.2f}{est:>8s}   {p.nombres[k]}{marca}")
    print("  estab. = congruencia de Tucker entre la 1ª y la 2ª mitad (> 0.95 idénticos; < 0.85 cambió).")
    print()
    _titulo("4 · INTERPRETACIÓN DE LOADINGS (correlación activo-factor, IC 90 % bootstrap)")
    for k in range(p.K):
        v = p.cargas[:, k]
        orden = np.argsort(-np.abs(v))
        sig = [(p.activos[i], v[i], p.carga_lo[i, k], p.carga_hi[i, k]) for i in orden
               if p.carga_lo[i, k] * p.carga_hi[i, k] > 0][:6]
        print(f"  PC{k + 1} · {p.nombres[k]} · {100 * p.expl[k]:.1f} % de la varianza")
        for a, x, lo, hi in sig:
            print(f"      {a:<5s}{nombre(a):<20s}{x:+.2f}   [{lo:+.2f}, {hi:+.2f}]")
        ns = [p.activos[i] for i in orden if p.carga_lo[i, k] * p.carga_hi[i, k] <= 0]
        if ns:
            print(f"      no distinguibles de 0: {', '.join(ns)}")
    print("  Una carga es la correlación del activo con el factor: ±0.8 es casi el factor; 0.2 no.")
    print("  Sólo se listan las que su IC 90 % no cruza el cero.")


def reporte_riesgo(res: Resultado) -> None:
    p, rk, pt = res.est, res.riesgo, res.port
    _titulo("5 · DESCOMPOSICIÓN CUANTITATIVA DEL RIESGO")
    print(f"  Por activo (fracción de su varianza), K = {p.K} factores:")
    cols = [f"PC{k + 1}" for k in range(p.K)]
    print(f"      {'activo':<6s}{'sistem.':>9s}{'idiosinc.':>11s}" + "".join(f"{c:>8s}" for c in cols))
    for a, x in rk.iterrows():
        print(f"      {a:<6s}{_pct(x['sistematico'], 1, 8)}{_pct(x['idiosincratico'], 1, 10)}"
              + "".join(_pct(x[c], 1, 7) for c in cols))
    print()
    print(f"  Portafolio ({pt['origen']}): vol anual {pt['vol_anual']:.1%}")
    print(f"      sistemático (K = {p.K})      : {pt['sistematico']:.1%}")
    print(f"      número efectivo de apuestas : {pt['enb']:.2f} de {len(p.activos)} (Meucci 2009)")
    print(f"      razón de diversificación    : {pt['dr']:.2f} (Choueifaty-Coignard 2008)")
    print("      cuota por factor            : " + " · ".join(
        f"PC{k + 1} {pt['cuota_factor'][k]:.0%}" for k in range(min(5, len(pt['cuota_factor'])))))
    rc = pt["rc_activo"].sort_values(ascending=False)
    print("      aporte al riesgo por activo : " + " · ".join(f"{a} {x:.0%}" for a, x in rc.head(6).items()))
    print(f"  (las cuotas por factor suman {pt['cierre_exacto']:.6f} de la varianza: la descomposición es exacta)")


def reporte_dinamico(res: Resultado) -> None:
    rod = res.rod
    _titulo(f"6 · ANÁLISIS DINÁMICO ESTRUCTURAL (PCA rodante, ventana {res.cfg.ventana} días)")
    f = rod.fechas
    un_ano = max(0, len(f) - 252)
    print(f"  {'':34s}{'hoy':>9s}{'hace 1 año':>12s}{'mín':>8s}{'máx':>8s}")
    for et, x in (("PC1: % de la varianza", 100 * rod.expl[:, 0]),
                  (f"absorption ratio (top {rod.k_ar}), %", 100 * rod.ar),
                  ("ΔAR estandarizado", rod.dar),
                  ("factores para el 90 %", rod.n90),
                  ("factores sobre Marchenko-Pastur", rod.k_mp),
                  ("R² sistemático promedio, %", 100 * rod.r2),
                  ("portafolio: % sistemático", 100 * rod.port_sis),
                  ("portafolio: apuestas efectivas", rod.port_enb),
                  ("correlación acciones-bonos", rod.corr_ab)):
        if not np.isfinite(x).any():
            continue
        print(f"  {et:<34s}{_fmt(x[-1], 2, 9)}{_fmt(x[un_ano], 2, 12)}{_fmt(np.nanmin(x), 2, 8)}"
              f"{_fmt(np.nanmax(x), 2, 8)}")
    c = rod.congr_prev[:, 0]
    bajos = np.flatnonzero(np.isfinite(c) & (c < 0.95))
    print()
    print(f"  Estabilidad de PC1 día a día (congruencia con la ventana anterior): mínimo "
          f"{np.nanmin(c):.3f}")
    if len(bajos):
        print("  Días con cambio estructural brusco (< 0.95): " + ", ".join(
            f"{f[i]:%Y-%m-%d}" for i in bajos[:8]) + (" …" if len(bajos) > 8 else ""))
    ce = rod.congr_est[:, 0]
    print(f"  Congruencia de PC1 rodante con el PC1 estático: hoy {ce[-1]:.2f} · mínimo {np.nanmin(ce):.2f}")
    if np.isfinite(rod.corr_ab).any():
        a, b = rod.corr_ab[un_ano], rod.corr_ab[-1]
        if np.sign(a) != np.sign(b):
            print(f"  ⚠ La correlación acciones-bonos cambió de signo en el último año ({a:+.2f} → {b:+.2f}):")
            print("    los bonos dejaron de ser (o volvieron a ser) cobertura de las acciones.")


def reporte_regimen(res: Resultado) -> None:
    reg, rod, aud, cfg = res.reg, res.rod, res.aud, res.cfg
    _titulo("7 · RÉGIMEN SISTÉMICO — Risk-On / Risk-Off")
    ok = np.flatnonzero(reg.etiqueta != "—")
    if not len(ok):
        print("  No hay historia suficiente para el modelo de régimen (sube --calentamiento).")
        return
    i = ok[-1]
    et = reg.etiqueta[i]
    j = i
    while j > 0 and reg.etiqueta[j - 1] == et:
        j -= 1
    lim = chi2.ppf(cfg.turb_conf, len(res.R.columns)) / len(res.R.columns)
    print(f"  HOY ({reg.fechas[i]:%Y-%m-%d}): {et.upper()} desde hace {i - j + 1} días")
    print(f"      P(risk-off) filtrada : {reg.p_off[i]:.1%}")
    print(f"      vol intradía de PC1  : {math.sqrt(252 * rod.rv_riesgo[i]):.1f} % anual "
          f"(23 retornos horarios del día)")
    print(f"      ΔAR (fragilidad)     : {rod.dar[i]:+.2f} σ   (umbral {cfg.dar_umbral:+.1f})")
    print(f"      turbulencia          : {rod.turb[i]:.2f}   (el {cfg.turb_conf:.0%} de un día normal: "
          f"{lim:.2f}) · correlación-sorpresa {rod.turb[i] / max(rod.turb_mag[i], 1e-9):.2f}")
    par = reg.par
    if par:
        print()
        print("  Modelo de Markov sobre la varianza intradía de PC1 (último ajuste, sólo con el pasado):")
        for k, nm in ((0, "Risk-On"), (1, "Risk-Off")):
            vol_k = math.sqrt(252 * math.exp(par["mu"][k] + 0.5 * par["sd"][k] ** 2))
            print(f"      {nm:<9s} vol típica del factor {vol_k:5.1f} % anual · "
                  f"duración esperada {reg.duracion[nm]:.0f} días")
    frac = {e: float(np.mean(reg.etiqueta[ok] == e)) for e in ("Risk-On", "Frágil", "Risk-Off")}
    print("  Tiempo en cada régimen: " + " · ".join(f"{e} {x:.0%}" for e, x in frac.items()))
    print()
    print(f"  ¿SIRVE? Volatilidad del factor de riesgo en los {cfg.horizonte_vol} días SIGUIENTES:")
    for e, (v, n) in aud["vol_fut"].items():
        print(f"      tras {e:<9s}: {_fmt(v, 1, 6)} % anual   ({n} días)")
    t = aud["tabla"]
    eq = [a for a in ("ES", "NQ", "RTY", "ZN", "GC", "6J") if a in res.R.columns]
    print("  Retorno del día SIGUIENTE (bps) por régimen:  " + " ".join(f"{a:>7s}" for a in eq))
    for e in ("Risk-On", "Frágil", "Risk-Off"):
        s = t[t["regimen"] == e].set_index("activo")
        print(f"      {e:<10s}" + " " * 30 + " ".join(_fmt(s.loc[a, 'media_bps'], 1, 7) for a in eq))
    print("  La etiqueta anticipa MAGNITUD (más volatilidad tras risk-off), no dirección: un día de")
    print("  retorno medio con |t| < 2 es ruido.")


# =============================================================================
# 11. DASHBOARD VISUAL MULTIDIMENSIONAL
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


def _eje_log(ax) -> None:
    """Escala log con números legibles (2, 5, 10, 20…) en lugar de 2×10⁰."""
    from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter
    ax.set_yscale("log")
    ax.yaxis.set_major_locator(LogLocator(base=10, subs=(1.0, 2.0, 5.0)))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.yaxis.set_minor_formatter(NullFormatter())


COLOR_CLASE = {"acciones": C["s1"], "tasas": C["s2"], "metales": C["s3"], "energía": C["s4"],
               "divisas": C["s5"], "otro": C["tenue"]}
DIVERGENTE = ["#104281", "#256abf", "#6da7ec", "#b7d3f6", "#f0efec", "#f6c4c3", "#ec8988",
              "#e34948", "#a82e2d"]
COLOR_REGIMEN = {"Risk-On": "#cde2fb", "Frágil": "#e8e7e1", "Risk-Off": "#f6c4c3"}


def _cmap_div():
    from matplotlib.colors import LinearSegmentedColormap
    return LinearSegmentedColormap.from_list("div", DIVERGENTE)


def _etiquetas_sin_choque(ax, xs, ys, textos, tam=7.5, radio=5.5):
    """
    Coloca cada etiqueta en la primera posición libre alrededor de su punto: sin tapar otras
    etiquetas, otros puntos ni salirse del panel. Si tiene que alejarse, una línea la une a
    su punto.
    """
    ax.autoscale_view()
    ax.figure.canvas.draw()
    trans = ax.transData
    esc = ax.figure.dpi / 72.0                           # puntos → píxeles
    marco = ax.bbox
    pts = [trans.transform((x, y)) for x, y in zip(xs, ys)]
    r = radio * esc
    ocupadas = [(px - r, py - r, px + r, py + r) for px, py in pts]
    candidatos = []
    for anillo in range(4):
        d = 9 * anillo
        candidatos += [(6 + d, 2 + d, "left"), (6 + d, -10 - d, "left"),
                       (-6 - d, 2 + d, "right"), (-6 - d, -10 - d, "right"),
                       (0, 8 + d, "center"), (0, -17 - d, "center")]
    for i in np.argsort(-np.asarray(ys)):
        px, py = pts[i]
        ancho, alto = 0.62 * tam * len(textos[i]) * esc, 1.15 * tam * esc
        elegido = candidatos[0]
        for dx, dy, ha in candidatos:
            x0 = px + dx * esc - {"left": 0.0, "right": ancho, "center": ancho / 2}[ha]
            caja = (x0, py + dy * esc, x0 + ancho, py + dy * esc + alto)
            dentro = (caja[0] > marco.x0 and caja[2] < marco.x1 and caja[1] > marco.y0
                      and caja[3] < marco.y1)
            if dentro and all(caja[2] < o[0] or caja[0] > o[2] or caja[3] < o[1] or caja[1] > o[3]
                              for o in ocupadas):
                elegido = (dx, dy, ha)
                ocupadas.append(caja)
                break
        dx, dy, ha = elegido
        lejos = abs(dx) > 6 or dy > 8 or dy < -17
        ax.annotate(textos[i], xy=(xs[i], ys[i]), xytext=(dx, dy), textcoords="offset points",
                    fontsize=tam, color=C["tinta"], ha=ha,
                    arrowprops=dict(arrowstyle="-", color=C["tenue"], linewidth=0.6,
                                    shrinkA=0, shrinkB=4) if lejos else None)


def _barra_color(ax, fig, im, etiqueta, afuera=False):
    if afuera:                                            # no le quita ancho al panel
        cb = fig.colorbar(im, cax=ax.inset_axes([1.01, 0.0, 0.012, 1.0]))
        cb.set_label(etiqueta, color=C["tinta2"], fontsize=8)
        cb.ax.tick_params(labelsize=7, colors=C["tinta2"])
        cb.outline.set_visible(False)
        return
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02)
    cb.set_label(etiqueta, color=C["tinta2"], fontsize=8)
    cb.ax.tick_params(labelsize=7, colors=C["tinta2"])
    cb.outline.set_visible(False)


def _sombrear_regimen(ax, fechas, etiquetas):
    et = np.asarray(etiquetas)
    ini = 0
    for i in range(1, len(et) + 1):
        if i == len(et) or et[i] != et[ini]:
            if et[ini] in COLOR_REGIMEN:
                ax.axvspan(fechas[ini], fechas[min(i, len(et) - 1)], color=COLOR_REGIMEN[et[ini]],
                           linewidth=0, zorder=0)
            ini = i


def tablero_estructura(res: Resultado, plt, ruta: Path):
    p, cfg = res.est, res.cfg
    act = p.activos
    N = len(act)
    fig, axes = plt.subplots(2, 3, figsize=(20, 11.5))
    fig.patch.set_facecolor(C["fondo"])
    (a1, a2, a3), (a4, a5, a6) = axes
    fig.suptitle(f"PCA cross-asset · estructura estática · {res.R.index[0]:%Y-%m-%d} → "
                 f"{res.R.index[-1]:%Y-%m-%d} · {len(res.R)} días × {N} activos",
                 x=0.01, ha="left", color=C["tinta"], fontsize=12)
    cmap = _cmap_div()

    # --- 1 scree con Marchenko-Pastur y análisis paralelo ---
    _estilo(a1, "Scree: varianza por componente contra el ruido")
    k = np.arange(1, N + 1)
    a1.bar(k, 100 * p.expl, color=[C["s1"] if i < p.K else C["neutro"] for i in range(N)],
           label="% de la varianza")
    a1.plot(k, 100 * p.pa95 / N, color=C["tinta"], linewidth=1.3, marker="o", markersize=4,
            label="análisis paralelo (95 %)")
    a1.axhline(100 * p.lam_mp / N, color=C["s2"], linewidth=1.3, linestyle="--",
               label="límite de Marchenko-Pastur")
    for i in range(min(p.K, N)):
        a1.annotate(f"{100 * p.expl[i]:.0f}%", xy=(i + 1, 100 * p.expl[i]), xytext=(0, 3),
                    textcoords="offset points", ha="center", fontsize=7.5, color=C["tinta"])
    a1.set_xticks(k)
    a1.set_xlabel("componente", color=C["tinta2"], fontsize=9)
    a1.set_ylabel("% de la varianza total", color=C["tinta2"], fontsize=9)
    _leyenda(a1, loc="upper right")

    # --- 2 mapa de cargas ---
    kk = min(N, p.K + 2)
    _estilo(a2, "Loadings: correlación de cada activo con cada factor")
    a2.grid(False)
    im = a2.imshow(p.cargas[:, :kk], cmap=cmap, vmin=-1, vmax=1, aspect="auto")
    for i in range(N):
        for j in range(kk):
            v = p.cargas[i, j]
            if abs(v) >= 0.5:
                a2.text(j, i, f"{v:+.2f}", ha="center", va="center", fontsize=7,
                        color="#ffffff" if abs(v) > 0.75 else C["tinta"])
    a2.set_xticks(range(kk))
    a2.set_xticklabels([f"PC{j + 1}\n" + "\n".join(textwrap.wrap(p.nombres[j], 16))
                        for j in range(kk)], fontsize=7)
    a2.set_yticks(range(N))
    a2.set_yticklabels([f"{a}  {nombre(a)}" for a in act], fontsize=7.5)
    for tl, a in zip(a2.get_yticklabels(), act):
        tl.set_color(C["tinta2"])
    _barra_color(a2, fig, im, "correlación")

    # --- 3 matriz de correlación ---
    _estilo(a3, "Matriz de correlación (ordenada por clase)")
    a3.grid(False)
    im = a3.imshow(p.C, cmap=cmap, vmin=-1, vmax=1)
    a3.set_xticks(range(N))
    a3.set_xticklabels(act, rotation=90, fontsize=7)
    a3.set_yticks(range(N))
    a3.set_yticklabels(act, fontsize=7)
    cl = [clase(a) for a in act]
    for i in range(1, N):
        if cl[i] != cl[i - 1]:
            a3.axhline(i - 0.5, color=C["fondo"], linewidth=2)
            a3.axvline(i - 0.5, color=C["fondo"], linewidth=2)
    _barra_color(a3, fig, im, "correlación")

    # --- 4 biplot PC1 × PC2 ---
    _estilo(a4, "Mapa de factores: carga en PC1 contra carga en PC2")
    for c_ in CLASES:
        m = [i for i, a in enumerate(act) if clase(a) == c_]
        if m:
            a4.scatter(p.cargas[m, 0], p.cargas[m, 1], s=70, color=COLOR_CLASE[c_], label=c_,
                       edgecolors=C["fondo"], linewidths=1.5, zorder=5)
    a4.axhline(0, color=C["eje"], linewidth=0.8)
    a4.margins(0.12)
    _etiquetas_sin_choque(a4, p.cargas[:, 0], p.cargas[:, 1] if N > 1 else np.zeros(N), act)
    a4.axvline(0, color=C["eje"], linewidth=0.8)
    a4.set_xlabel(f"PC1 · {p.nombres[0]}", color=C["tinta2"], fontsize=9)
    a4.set_ylabel(f"PC2 · {p.nombres[1]}" if N > 1 else "", color=C["tinta2"], fontsize=9)
    _leyenda(a4, loc="best", ncol=1)

    # --- 5 descomposición del riesgo por activo ---
    rk = res.riesgo.sort_values("sistematico")
    _estilo(a5, f"Riesgo de cada activo: sistemático (K = {p.K}) e idiosincrático")
    y = np.arange(len(rk))
    izq = np.zeros(len(rk))
    tonos = [RAMPA_AZUL[i] for i in np.linspace(9, 4, max(1, p.K)).astype(int)]
    for kk_ in range(p.K):
        v = 100 * rk[f"PC{kk_ + 1}"].to_numpy()
        a5.barh(y, v, left=izq, height=0.66, color=tonos[kk_], label=f"PC{kk_ + 1}")
        izq += v
    a5.barh(y, 100 * rk["idiosincratico"].to_numpy(), left=izq, height=0.66, color=C["neutro"],
            label="idiosincrático")
    a5.set_yticks(y)
    a5.set_yticklabels(rk.index, fontsize=7.5)
    a5.set_xlim(0, 100)
    a5.set_xlabel("% de la varianza del activo", color=C["tinta2"], fontsize=9)
    _leyenda(a5, loc="upper center", bbox_to_anchor=(0.5, -0.09), ncol=p.K + 1)

    # --- 6 cargas de PC1 con su incertidumbre ---
    _estilo(a6, f"PC1 · {p.nombres[0]}: cargas con IC 90 % bootstrap")
    o = np.argsort(p.cargas[:, 0])
    y = np.arange(N)
    a6.barh(y, p.cargas[o, 0], height=0.62, color=[COLOR_CLASE[clase(act[i])] for i in o])
    a6.errorbar(p.cargas[o, 0], y, xerr=[p.cargas[o, 0] - p.carga_lo[o, 0],
                                         p.carga_hi[o, 0] - p.cargas[o, 0]],
                fmt="none", ecolor=C["tinta"], elinewidth=1.0, capsize=2)
    a6.axvline(0, color=C["eje"], linewidth=0.8)
    a6.set_yticks(y)
    a6.set_yticklabels([act[i] for i in o], fontsize=7.5)
    a6.set_xlabel("correlación con el factor", color=C["tinta2"], fontsize=9)
    fig.text(0.008, 0.004, f"{IDENTIFICADOR} · PCA de correlación · retornos al corte de "
             f"{cfg.corte_ct} CT, sin rolls · IC por bootstrap de bloques de {cfg.bloque_boot} días",
             color=C["tenue"], fontsize=7.5)
    fig.tight_layout(rect=(0, 0.015, 1, 0.965))
    fig.savefig(ruta, dpi=125, facecolor=C["fondo"], bbox_inches="tight")
    return fig


def tablero_dinamica(res: Resultado, plt, ruta: Path):
    rod, cfg = res.rod, res.cfg
    f = rod.fechas
    act = list(res.R.columns)
    span = max(1, (f[-1] - f[0]).days)
    fig = plt.figure(figsize=(19, 14))
    fig.patch.set_facecolor(C["fondo"])
    gs = fig.add_gridspec(4, 2, height_ratios=[1.1, 1.4, 1.0, 1.0], hspace=0.42, wspace=0.14,
                          bottom=0.05, top=0.93)
    a1 = fig.add_subplot(gs[0, :])
    a2 = fig.add_subplot(gs[1, :], sharex=a1)
    a3 = fig.add_subplot(gs[2, 0], sharex=a1)
    a4 = fig.add_subplot(gs[2, 1], sharex=a1)
    a5 = fig.add_subplot(gs[3, 0], sharex=a1)
    a6 = fig.add_subplot(gs[3, 1], sharex=a1)
    fig.suptitle(f"PCA rodante · ventana de {cfg.ventana} días, re-estimada cada día · causal",
                 x=0.01, ha="left", color=C["tinta"], fontsize=12)

    _estilo(a1, "Concentración del riesgo: varianza de los primeros factores y absorption ratio")
    for k, col in zip(range(3), (C["s1"], C["s2"], C["s3"])):
        a1.plot(f, 100 * rod.expl[:, k], color=col, linewidth=1.5, label=f"PC{k + 1}")
    a1.plot(f, 100 * rod.ar, color=C["tinta"], linewidth=1.8, label=f"absorption ratio (top {rod.k_ar})")
    a1.set_ylabel("% de la varianza", color=C["tinta2"], fontsize=9)
    _leyenda(a1, ncol=4, loc="lower right", bbox_to_anchor=(1.0, 1.0))

    _estilo(a2, "Loadings de PC1 a lo largo del tiempo (alineados: sin cambios de signo artificiales)")
    a2.grid(False)
    import matplotlib.dates as mdates
    x0, x1 = mdates.date2num(f[0]), mdates.date2num(f[-1])
    im = a2.imshow(rod.cargas[:, :, 0].T, cmap=_cmap_div(), vmin=-1, vmax=1, aspect="auto",
                   extent=(x0, x1, len(act) - 0.5, -0.5), interpolation="nearest")
    a2.set_yticks(range(len(act)))
    a2.set_yticklabels([f"{a} {nombre(a)}" for a in act], fontsize=7.5)
    _barra_color(a2, fig, im, "correlación con PC1", afuera=True)

    _estilo(a3, "¿Cuántos factores hay?")
    a3.step(f, rod.n90, where="post", color=C["s1"], linewidth=1.5, label="para el 90 % de la varianza")
    a3.step(f, rod.n80, where="post", color=C["s2"], linewidth=1.5, label="para el 80 %")
    a3.step(f, rod.k_mp, where="post", color=C["tinta"], linewidth=1.5,
            label="sobre Marchenko-Pastur (señal)")
    a3.set_ylabel("factores", color=C["tinta2"], fontsize=9)
    a3.set_ylim(0, np.nanmax(rod.n90) + 3)
    _leyenda(a3, ncol=3, loc="upper left")

    _estilo(a4, "Correlación acciones-bonos (¿los bonos cubren a las acciones?)")
    if np.isfinite(rod.corr_ab).any():
        a4.plot(f, rod.corr_ab, color=C["s1"], linewidth=1.5)
        a4.fill_between(f, rod.corr_ab, 0, where=rod.corr_ab > 0, color=C["baja"], alpha=0.15,
                        linewidth=0, label="positiva: NO cubren")
        a4.fill_between(f, rod.corr_ab, 0, where=rod.corr_ab <= 0, color=C["alza"], alpha=0.15,
                        linewidth=0, label="negativa: sí cubren")
        a4.axhline(0, color=C["eje"], linewidth=0.8)
        _leyenda(a4, ncol=2)
    a4.set_ylabel("correlación", color=C["tinta2"], fontsize=9)

    _estilo(a5, "Estabilidad estructural: congruencia de PC1")
    a5.plot(f, rod.congr_est[:, 0], color=C["s1"], linewidth=1.5, label="contra el PC1 estático")
    a5.plot(f, rod.congr_prev[:, 0], color=C["s2"], linewidth=1.0, label="contra la ventana anterior")
    a5.axhline(0.95, color=C["eje"], linewidth=1.0)
    a5.set_ylabel("congruencia de Tucker", color=C["tinta2"], fontsize=9)
    lo5 = np.nanmin(rod.congr_est[:, 0])
    a5.set_ylim(lo5 - 0.35 * (1.0 - lo5), 1.0 + 0.05 * (1.0 - lo5))
    _leyenda(a5, ncol=2, loc="lower right")

    _estilo(a6, "Riesgo del portafolio: parte sistemática y apuestas efectivas")
    a6.plot(f, 100 * rod.port_sis, color=C["s1"], linewidth=1.5)
    a6.set_ylabel(f"% sistemático (K = {res.est.K})", color=C["s1"], fontsize=9)
    b6 = a6.twinx()
    b6.plot(f, rod.port_enb, color=C["s2"], linewidth=1.2)
    b6.set_ylabel(f"apuestas efectivas (de {len(act)})", color=C["s2"], fontsize=9)
    b6.tick_params(colors=C["s2"], labelsize=8)
    for lado in ("top", "left", "bottom"):
        b6.spines[lado].set_visible(False)
    b6.spines["right"].set_color(C["eje"])
    for ax in (a1, a2, a3, a4, a5, a6):
        _eje_fechas(ax, span)
    for ax in (a1, a2, a3, a4):
        ax.tick_params(labelbottom=False)
    a2.xaxis_date()
    fig.text(0.008, 0.01, f"{IDENTIFICADOR} · cada día usa los {cfg.ventana} días ANTERIORES · "
             "series completas en salidas_pca/pca_rodante.csv", color=C["tenue"], fontsize=7.5)
    fig.savefig(ruta, dpi=125, facecolor=C["fondo"], bbox_inches="tight")
    return fig


def tablero_regimen(res: Resultado, plt, ruta: Path):
    rod, reg, cfg = res.rod, res.reg, res.cfg
    f = rod.fechas
    span = max(1, (f[-1] - f[0]).days)
    fig = plt.figure(figsize=(19, 14))
    fig.patch.set_facecolor(C["fondo"])
    gs = fig.add_gridspec(4, 2, height_ratios=[1.3, 1.0, 1.0, 1.1], hspace=0.42, wspace=0.14,
                          bottom=0.05, top=0.93)
    a1 = fig.add_subplot(gs[0, :])
    a2 = fig.add_subplot(gs[1, 0], sharex=a1)
    a3 = fig.add_subplot(gs[1, 1], sharex=a1)
    a4 = fig.add_subplot(gs[2, 0], sharex=a1)
    a5 = fig.add_subplot(gs[2, 1])
    a6 = fig.add_subplot(gs[3, 0])
    a7 = fig.add_subplot(gs[3, 1])
    ok = reg.etiqueta != "—"
    hoy = reg.etiqueta[np.flatnonzero(ok)[-1]] if ok.any() else "—"
    fig.suptitle(f"Régimen sistémico · hoy: {hoy} · P(risk-off) "
                 f"{reg.p_off[np.flatnonzero(ok)[-1]]:.0%}" if ok.any() else "Régimen sistémico",
                 x=0.01, ha="left", color=C["tinta"], fontsize=12)

    _estilo(a1, "Factor de riesgo (PC1) acumulado y régimen detectado")
    _sombrear_regimen(a1, f, reg.etiqueta)
    a1.plot(f, np.nancumsum(rod.roro), color=C["tinta"], linewidth=1.4, label="PC1 acumulado (%)",
            zorder=3)
    for e, col in COLOR_REGIMEN.items():
        a1.fill_between([], [], color=col, label=e)
    a1.set_ylabel("% acumulado", color=C["tinta2"], fontsize=9)
    _leyenda(a1, ncol=4)

    _estilo(a2, "Lo que lee el Markov: vol intradía de PC1 · y su P(risk-off) filtrada")
    b2 = a2.twinx()
    po = np.nan_to_num(reg.p_off, nan=0.0)
    b2.fill_between(f, 0, po, color=C["baja"], alpha=0.16, linewidth=0, zorder=1)
    b2.plot(f, reg.p_off, color=C["baja"], linewidth=0.9, zorder=2)
    b2.axhline(cfg.umbral_prob, color=C["baja"], linewidth=0.8, linestyle=":")
    b2.set_ylim(0, 1.02)
    b2.set_ylabel("P(risk-off)", color=C["baja"], fontsize=9)
    b2.tick_params(colors=C["baja"], labelsize=8)
    for lado in ("top", "left", "bottom"):
        b2.spines[lado].set_visible(False)
    b2.spines["right"].set_color(C["eje"])
    a2.set_zorder(b2.get_zorder() + 1)
    a2.patch.set_visible(False)
    a2.plot(f, np.sqrt(252 * rod.rv_riesgo), color=C["tinta"], linewidth=0.8,
            label="vol intradía de PC1")
    if reg.par:
        for k, (nm, col) in enumerate((("Risk-On", C["alza"]), ("Risk-Off", C["baja"]))):
            nivel = math.sqrt(252 * math.exp(reg.par["mu"][k] + 0.5 * reg.par["sd"][k] ** 2))
            a2.axhline(nivel, color=col, linewidth=1.1, linestyle="--",
                       label=f"nivel {nm}: {nivel:.1f} %")
    _eje_log(a2)
    a2.set_ylabel("% anual (log)", color=C["tinta2"], fontsize=9)
    _leyenda(a2, ncol=3, frameon=True, facecolor=C["fondo"], edgecolor="none", framealpha=0.92)

    _estilo(a3, "Fragilidad: absorption ratio, cambio estandarizado (ΔAR)")
    a3.plot(f, rod.dar, color=C["s1"], linewidth=1.2)
    a3.axhline(cfg.dar_umbral, color=C["tinta2"], linewidth=1.0)
    a3.axhline(0, color=C["eje"], linewidth=0.8)
    a3.set_ylabel("σ", color=C["tinta2"], fontsize=9)

    lim = chi2.ppf(cfg.turb_conf, len(res.R.columns)) / len(res.R.columns)
    _estilo(a4, "Turbulencia (Mahalanobis / N) — escala log")
    a4.plot(f, rod.turb, color=C["s1"], linewidth=0.9, label="turbulencia")
    a4.axhline(lim, color=C["tinta2"], linewidth=1.0, label=f"{cfg.turb_conf:.0%} de un día normal")
    _eje_log(a4)
    a4.set_ylabel("d² / N", color=C["tinta2"], fontsize=9)
    _leyenda(a4, ncol=2)
    for ax in (a1, a2, a3, a4):
        _eje_fechas(ax, span)
    a1.tick_params(labelbottom=False)

    # --- 5 volatilidad futura por régimen ---
    _estilo(a5, f"¿Sirve? Volatilidad del factor en los {cfg.horizonte_vol} días siguientes")
    vf = res.aud["vol_fut"]
    nombres_ = [e for e in ("Risk-On", "Frágil", "Risk-Off") if vf[e][1] > 0]
    borde = {"Risk-On": C["alza"], "Frágil": C["tenue"], "Risk-Off": C["baja"]}
    a5.bar(nombres_, [vf[e][0] for e in nombres_], color=[COLOR_REGIMEN[e] for e in nombres_],
           edgecolor=[borde[e] for e in nombres_], linewidth=1.2)
    for i, e in enumerate(nombres_):
        a5.annotate(f"{vf[e][0]:.1f} %\n{vf[e][1]} días", xy=(i, vf[e][0]), xytext=(0, 3),
                    textcoords="offset points", ha="center", fontsize=8, color=C["tinta"])
    a5.set_ylabel("% anual", color=C["tinta2"], fontsize=9)
    a5.margins(y=0.2)

    # --- 6 retorno siguiente por régimen ---
    t = res.aud["tabla"]
    act = [a for a in res.R.columns if a in ("ES", "NQ", "RTY", "ZN", "ZB", "GC", "CL", "6J", "6A", "6M")]
    _estilo(a6, "Retorno del día SIGUIENTE por régimen (bps)")
    y = np.arange(len(act))
    for k, (e, col) in enumerate((("Risk-On", C["alza"]), ("Risk-Off", C["baja"]))):
        s = t[t["regimen"] == e].set_index("activo").reindex(act)
        a6.barh(y + (0.2 if k == 0 else -0.2), s["media_bps"], height=0.38, color=col, label=e)
    a6.axvline(0, color=C["eje"], linewidth=0.8)
    a6.set_yticks(y)
    a6.set_yticklabels(act, fontsize=8)
    _leyenda(a6, loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=2)

    # --- 7 portafolio por factor ---
    pt, p = res.port, res.est
    _estilo(a7, f"Portafolio: de dónde viene su riesgo · apuestas efectivas {pt['enb']:.1f} "
                f"de {len(p.activos)}")
    nf = min(8, len(pt["cuota_factor"]))
    a7.bar([f"PC{k + 1}" for k in range(nf)], 100 * pt["cuota_factor"][:nf],
           color=[C["s1"] if k < p.K else C["neutro"] for k in range(nf)])
    resto = 100 * pt["cuota_factor"][nf:].sum()
    if resto > 0.05:
        a7.bar(["resto"], [resto], color=C["neutro"])
    a7.set_ylabel("% de la varianza del portafolio", color=C["tinta2"], fontsize=9)
    fig.text(0.008, 0.01, f"{IDENTIFICADOR} · régimen = Markov de 2 estados sobre la varianza intradía de PC1 "
             f"(re-estimado cada {cfg.hmm_refit} días) + ΔAR ≥ {cfg.dar_umbral:g} σ = frágil",
             color=C["tenue"], fontsize=7.5)
    fig.savefig(ruta, dpi=125, facecolor=C["fondo"], bbox_inches="tight")
    return fig


def tableros(res: Resultado, mostrar: bool = True) -> tuple[list[Path], object, bool]:
    plt, ventana = _preparar_grafico(mostrar)
    if plt is None:
        return [], None, False
    carpeta = _ruta(res.cfg.salida_dir)
    carpeta.mkdir(parents=True, exist_ok=True)
    rutas = []
    for nombre_, fn in (("estructura", tablero_estructura), ("dinamica", tablero_dinamica),
                        ("regimen", tablero_regimen)):
        ruta = carpeta / f"pca_{nombre_}.png"
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
    reg, rod, cfg = res.reg, res.rod, res.cfg
    ok = np.flatnonzero(reg.etiqueta != "—")
    if len(ok) < 2:
        return []
    i = ok[-1]
    avisos = []
    if reg.etiqueta[i] != reg.etiqueta[ok[-2]]:
        avisos.append(f"Cambio de régimen: {reg.etiqueta[ok[-2]]} → {reg.etiqueta[i]}")
    if np.isfinite(rod.dar[i]) and rod.dar[i] >= cfg.dar_umbral:
        avisos.append(f"Fragilidad: ΔAR = {rod.dar[i]:+.2f} σ")
    N = len(res.R.columns)
    if rod.turb[i] >= chi2.ppf(cfg.telegram_turb_alerta, N) / N:
        avisos.append(f"Turbulencia extrema: {rod.turb[i]:.2f} (percentil ≥ {cfg.telegram_turb_alerta:.0%})")
    return avisos


def mensaje_telegram(res: Resultado, limite: int = 4096) -> str:
    esc = html.escape
    reg, rod, p, pt = res.reg, res.rod, res.est, res.port
    ok = np.flatnonzero(reg.etiqueta != "—")
    lin = [f"<b>{esc(IDENTIFICADOR)}</b> · {len(p.activos)} activos"]
    for a in hay_alerta(res):
        lin.append(f"⚠️ {esc(a)}")
    if len(ok):
        i = ok[-1]
        lin += ["", f"<b>Régimen {reg.fechas[i]:%Y-%m-%d}: {esc(reg.etiqueta[i])}</b>",
                f"P(risk-off) {reg.p_off[i]:.0%} · vol intradía PC1 "
                f"{math.sqrt(252 * rod.rv_riesgo[i]):.1f}% · ΔAR {rod.dar[i]:+.2f}σ · "
                f"turbulencia {rod.turb[i]:.2f}",
                f"PC1 explica {100 * rod.expl[-1, 0]:.0f}% · absorption ratio {100 * rod.ar[-1]:.0f}%"]
        if np.isfinite(rod.corr_ab[-1]):
            lin.append(f"Correlación acciones-bonos {rod.corr_ab[-1]:+.2f}")
    filas = ["factor              %var"]
    for k in range(p.K):
        filas.append(f"PC{k + 1} {p.nombres[k][:15]:<15s}{100 * p.expl[k]:5.1f}")
    lin.append("<pre>" + esc("\n".join(filas)) + "</pre>")
    lin.append(f"Portafolio: {pt['sistematico']:.0%} sistemático · {pt['enb']:.1f} apuestas "
               f"efectivas de {len(p.activos)}")
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
    carpeta = _ruta(res.cfg.salida_dir)
    carpeta.mkdir(parents=True, exist_ok=True)
    p, rod, reg = res.est, res.rod, res.reg
    res.R_total.to_csv(carpeta / "pca_retornos.csv")
    pc = [f"PC{k + 1}" for k in range(len(p.lam))]
    pd.DataFrame(p.cargas, index=p.activos, columns=pc).to_csv(carpeta / "pca_cargas.csv")
    pd.DataFrame({"lambda": p.lam, "expl": p.expl, "paralelo95": p.pa95, "nombre": p.nombres},
                 index=pc).to_csv(carpeta / "pca_varianza.csv")
    res.riesgo.to_csv(carpeta / "pca_riesgo_activos.csv")
    p.scores.to_csv(carpeta / "pca_scores.csv")
    pd.DataFrame({"pc1": rod.expl[:, 0], "pc2": rod.expl[:, 1], "ar": rod.ar, "dar": rod.dar,
                  "n80": rod.n80, "n90": rod.n90, "k_mp": rod.k_mp, "roro_pct": rod.roro,
                  "vol_intradia_pc1": np.sqrt(252 * rod.rv_riesgo),
                  "turbulencia": rod.turb, "r2": rod.r2, "port_sistematico": rod.port_sis,
                  "port_enb": rod.port_enb, "corr_acciones_bonos": rod.corr_ab,
                  "p_off": reg.p_off, "regimen": reg.etiqueta}, index=rod.fechas).to_csv(
        carpeta / "pca_rodante.csv")
    pd.DataFrame(rod.cargas[:, :, 0], index=rod.fechas, columns=res.R.columns).to_csv(
        carpeta / "pca_cargas_pc1_rodante.csv")
    res.aud["tabla"].to_csv(carpeta / "pca_auditoria_regimen.csv", index=False)
    print(f"💾 Tablas guardadas en {carpeta}")


# =============================================================================
# 14. PRUEBAS INTERNAS
# =============================================================================
def pruebas() -> int:
    cfg = replace(CFG, sim_dias=560, n_boot=60, n_paralelo=60, ventana=200, hmm_min=150)
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
    df, ver = simular(cfg, semilla=3)
    b = preparar_barras(df, cfg)
    R, rolls, info = retornos_diarios(b, cfg)

    # 1 ------------------------------------------ retornos al corte: exactos con rolls y feriados
    tr = ver["retornos"].reindex(R.index)
    err = float(np.nanmax(np.abs(R.to_numpy() - tr.fillna(0.0).to_numpy())))
    check("retornos al corte reconstruidos exactos, con rolls y feriados de un solo mercado",
          err < 1e-10, f"error máximo {err:.1e} en {R.size:,} retornos")

    # 2 ------------------------------------------ rolls detectados = rolls verdaderos
    vr = ver["rolls"].reindex(R.index).fillna(False)
    ok2 = all(int(rolls[a].sum()) == int(vr[a].sum()) for a in R.columns)
    check("cada roll del continuo se detecta por instrument_id", ok2,
          f"{int(vr.to_numpy().sum())} rolls en {R.shape[1]} activos")

    # 3 ------------------------------------------ tu script: los rolls sí entran como retorno
    tuR = retornos_tu_script(b, cfg.activos)
    ng = "NG" in tuR.columns
    if ng:
        f_tu = pd.DatetimeIndex(tuR.index.tz_localize(None).normalize())
        m = f_tu.isin(info["NG"]["rolls_utc"])
        cuota = float((tuR["NG"].to_numpy()[m] ** 2).sum() / (tuR["NG"].to_numpy() ** 2).sum())
    check("tu log(df/df.shift(1)) mete los saltos de roll en la varianza (gas natural)",
          ng and cuota > 1.5 * float(m.mean()),
          f"{cuota:.0%} de la varianza del NG en el {float(m.mean()):.0%} de los días" if ng else "")

    # 3b ----------------------------------------- las 23 horas suman el retorno del día
    hh = retornos_horarios(b, cfg, R)
    err_h = float(np.abs(hh.sum(1) - R.to_numpy()).max())
    check("retornos horarios: sus 23 horas suman exacto el retorno de corte a corte",
          err_h < 1e-12 and hh.shape[1] == HORAS, f"error máximo {err_h:.1e}")

    # 4 ------------------------------------------ escala por tipo de dato (el yen incluido)
    d4 = df.head(2000).copy()
    d4f = d4.copy()
    for col in ("open", "close"):
        d4f[col] = (d4f[col] * 1e9).round().astype("int64")
    a4, b4 = preparar_barras(d4, cfg), preparar_barras(d4f, cfg)
    check("la escala se detecta por el tipo de la columna (vale para el yen: 0.0068)",
          np.allclose(a4["close"], b4["close"], rtol=1e-9) and b4.attrs["escala"] != "float")

    # 5 ------------------------------------------ DX no está en Globex
    check("DX se detecta como fuera de CME Globex antes de descargar", "DX" in FUERA_DE_GLOBEX)

    # 6 ------------------------------------------ álgebra del PCA
    p = pca_estatico(R, cfg)
    ortog = np.abs(p.V.T @ p.V - np.eye(len(p.lam))).max()
    check("PCA de correlación: varianza explicada suma 1, vectores ortonormales, cargas² suman 1",
          abs(p.expl.sum() - 1) < 1e-9 and ortog < 1e-9
          and np.allclose((p.cargas ** 2).sum(1), 1.0, atol=1e-9))

    # 7 ------------------------------------------ orientación: acciones positivas en PC1
    eq = [p.activos.index(a) for a in ("ES", "NQ", "YM", "RTY") if a in p.activos]
    check("PC1 orientado: acciones con carga positiva (PC1 arriba = risk-on)",
          bool(np.all(p.cargas[eq, 0] > 0)), f"cargas {np.round(p.cargas[eq, 0], 2)}")

    # 8 ------------------------------------------ número de factores
    check("el análisis paralelo encuentra los 3 factores verdaderos", p.k_pa == 3,
          f"paralelo {p.k_pa} · Marchenko-Pastur {p.k_mp}")

    # 9 ------------------------------------------ recupera el subespacio de factores
    Q1, _ = np.linalg.qr(ver["cargas_post"] / R.to_numpy().std(0)[:, None])
    Q2, _ = np.linalg.qr(p.V[:, :3])
    cos = np.linalg.svd(Q1.T @ Q2, compute_uv=False)
    check("PC1-PC3 recuperan el espacio de los 3 factores verdaderos", float(cos.min()) > 0.85,
          "cosenos de los ángulos principales " + " · ".join(f"{c:.3f}" for c in cos))

    # 10 ----------------------------------------- riesgo por activo en [0, 1]; el tuyo no
    rk = riesgo_activos(p)
    tu = tu_estatico(R)
    check("riesgo sistemático por activo entre 0 y 100 %; el de tu fórmula no",
          bool(((rk["sistematico"] >= 0) & (rk["sistematico"] <= 1)).all())
          and float(tu["pct_sis"].min()) > 100,
          f"tu fórmula: {tu['pct_sis'].min():,.0f} % a {tu['pct_sis'].max():,.0f} %")

    # 11 ----------------------------------------- portafolio: descomposición exacta y ENB
    pt = riesgo_portafolio(R, p, None)
    sd_ = R.to_numpy().std(0, ddof=1)
    parejo = riesgo_portafolio(R, p, (p.V @ (1 / np.sqrt(p.lam))) / sd_)   # igual riesgo por factor
    solo1 = riesgo_portafolio(R, p, p.V[:, 0] / sd_)                         # sólo PC1
    N_ = len(p.lam)
    check("portafolio: cuotas por factor exactas; ENB = N con riesgo parejo y 1 con un solo factor",
          abs(pt["cierre_exacto"] - 1) < 1e-9 and abs(parejo["enb"] - N_) < 1e-6
          and abs(solo1["enb"] - 1) < 1e-6 and pt["dr"] >= 1,
          f"ENB {parejo['enb']:.3f} de {N_} · {solo1['enb']:.3f} · razón de diversificación {pt['dr']:.2f}")

    # 12 ----------------------------------------- el rolling no mira al futuro
    w = pt["pesos"]
    r1 = pca_rodante(R, p, cfg, w)
    r2_ = pca_rodante(R.iloc[:-60], p, cfg, w)
    n = len(r2_.fechas)
    check("el PCA rodante no mira al futuro (truncar no cambia el pasado)",
          np.allclose(r1.ar[:n], r2_.ar, equal_nan=True) and np.allclose(r1.roro[:n], r2_.roro, equal_nan=True))

    # 13 ----------------------------------------- sin cambios de signo; los tuyos sí dependen de la regla
    cp = r1.congr_prev[:, 0]
    check("PC1 rodante alineado: nunca cambia de signo entre ventanas",
          bool(np.all(cp[np.isfinite(cp)] > 0)), f"congruencia mínima día a día {np.nanmin(cp):.3f}")

    # 14 ----------------------------------------- tu n_factors_90 queda topado en 5
    trr = tu_rolling(R)
    check("tu n_factors_90 se topa en 5 cuando el 90 % necesita más",
          bool(np.mean(trr["n90"] == 5) > 0.5 and np.max(trr["n90_real"]) > 5),
          f"topado en {np.mean(trr['n90'] == 5):.0%} de las ventanas; hacían falta hasta "
          f"{np.max(trr['n90_real'])}")

    # 15 ----------------------------------------- turbulencia calibrada bajo la nula
    Rg = pd.DataFrame(rng.normal(0, 0.01, (1200, 8)), columns=list("ABCDEFGH"),
                      index=pd.bdate_range("2020-01-01", periods=1200))
    pg = pca_estatico(Rg, replace(cfg, n_boot=5, n_paralelo=5))
    rg = pca_rodante(Rg, pg, replace(cfg, ventana=250), riesgo_portafolio(Rg, pg, None)["pesos"])
    exc = float(np.nanmean(rg.turb > chi2.ppf(0.95, 8) / 8))
    check("turbulencia: con retornos normales su media ≈ 1 y pasa el 95 % en ≈ 5 % de los días",
          0.95 < np.nanmean(rg.turb) < 1.15 and exc < 0.09,
          f"media {np.nanmean(rg.turb):.3f} · excedencias {exc:.1%}")

    # 16 ----------------------------------------- el Markov recupera sus parámetros
    P_ = np.array([[0.985, 0.015], [0.04, 0.96]])
    st = np.zeros(3000, dtype=int)
    for t in range(1, 3000):
        st[t] = rng.choice(2, p=P_[st[t - 1]])
    mu_v, sd_v = np.array([-0.4, 1.3]), np.array([0.7, 0.8])     # log-varianza por estado
    x = mu_v[st] + sd_v[st] * rng.normal(size=3000)
    par = hmm_ajustar(x)
    pf = hmm_filtrar(x, par)
    check("el Markov de 2 estados recupera niveles, dispersiones, persistencia y estados",
          np.allclose(par["mu"], mu_v, atol=0.1) and np.allclose(par["sd"], sd_v, rtol=0.12)
          and abs(par["A"][0, 0] - 0.985) < 0.01 and float(np.mean((pf >= 0.5) == (st == 1))) > 0.9,
          f"niveles {par['mu'][0]:+.2f}/{par['mu'][1]:+.2f} · permanencia {par['A'][0, 0]:.3f}/"
          f"{par['A'][1, 1]:.3f} · exactitud filtrada {np.mean((pf >= 0.5) == (st == 1)):.1%}")

    # 17 ----------------------------------------- el filtro no mira al futuro
    x2 = x.copy()
    x2[2000:] *= 5
    check("la probabilidad filtrada no mira al futuro",
          np.allclose(hmm_filtrar(x, par)[:2000], hmm_filtrar(x2, par)[:2000]))

    # 18 ----------------------------------------- de punta a punta: régimen (muestra de tamaño real)
    c9 = replace(CFG, n_boot=40, n_paralelo=60)
    df9, ver9 = simular(c9, semilla=5)
    res = analizar(preparar_barras(df9, c9), c9, verdad=ver9)
    h = res.medicion["hmm"]
    check("el régimen detectado (causal) coincide con el verdadero",
          h["exactitud"] > 0.85 and h["precision"] > 0.7 and h["exhaustividad"] > 0.8,
          f"exactitud {h['exactitud']:.1%} · precisión risk-off {h['precision']:.1%} · "
          f"exhaustividad {h['exhaustividad']:.1%}")

    # 19 ----------------------------------------- la tabla de tu régimen es tautológica
    tu2 = res.tu
    Rn = res.tu_R.to_numpy()
    ies = res.tu_R.columns.get_loc("ES")
    mismo = (Rn[tu2["on"], ies].mean() - Rn[tu2["off"], ies].mean()) * 1e4
    sig = np.r_[Rn[1:, ies], np.nan]
    despues = (np.nanmean(sig[tu2["on"]]) - np.nanmean(sig[tu2["off"]])) * 1e4
    check("tus retornos 'por régimen' del mismo día son tautológicos; los del día siguiente no",
          abs(mismo) > 5 * abs(despues) and abs(mismo) > 100,
          f"ES on − off: mismo día {mismo:+.0f} bps · día siguiente {despues:+.0f} bps")

    # 20 ----------------------------------------- se ve el quiebre acciones-bonos
    ca = res.medicion.get("corr_ab", (np.nan, np.nan))
    check("el rolling ve el cambio de signo de la correlación acciones-bonos",
          ca[0] < -0.1 and ca[1] > 0.05, f"antes {ca[0]:+.2f} · después {ca[1]:+.2f}")

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
                and tok.encode() not in cuerpo)
    finally:
        urllib.request.urlopen = viejo
        png.unlink(missing_ok=True)
    check("Telegram: el multipart de sendPhoto está bien formado y no lleva el token", bool(bien))

    # 23 ----------------------------------------- ninguna key escrita en este archivo
    fuente = Path(__file__).read_text(encoding="utf-8")
    check("no hay API keys ni tokens escritos en el código",
          not re.search("db" + "-" + r"[A-Za-z0-9]{20,}", fuente)
          and not re.search(r"\d{8,10}:" + r"[A-Za-z0-9_-]{35}", fuente))

    # 24 ----------------------------------------- mensaje de Telegram
    txt = mensaje_telegram(res)
    check("el mensaje de Telegram cabe en un mensaje", len(txt) <= 4096 and "<pre>" in txt,
          f"{len(txt)} caracteres")

    print()
    if fallas:
        print(f"❌ {len(fallas)} de {hecho} pruebas fallaron: {', '.join(fallas)}")
        return 1
    print(f"✅ Las {hecho} pruebas pasaron.")
    return 0


# =============================================================================
# 15. LÍNEA DE COMANDOS
# =============================================================================
def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pca_factor_models.py",
        description="PCA Factor Models AC v2 — estructura de factores cross-asset, riesgo y "
                    "régimen Risk-On/Risk-Off.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="La API key se lee de DATABENTO_API_KEY; Telegram, de TELEGRAM_BOT_TOKEN y "
               "TELEGRAM_CHAT_ID. Nunca los escribas en el código.")
    p.add_argument("--pruebas", action="store_true", help="pruebas internas (sin red ni datos)")
    p.add_argument("--simulacion", action="store_true",
                   help="universo simulado con factores, regímenes y quiebre CONOCIDOS")
    p.add_argument("--sin-tablero", action="store_true")
    p.add_argument("--sin-ventana", action="store_true")
    p.add_argument("--sin-cache", action="store_true")
    d = p.add_argument_group("datos")
    d.add_argument("--activos", default=None, help="raíces separadas por coma, p. ej. ES,NQ,ZN,GC,6E")
    d.add_argument("--start", default=None)
    d.add_argument("--end", default=None)
    d.add_argument("--calentamiento", type=int, default=None, dest="dias_calentamiento")
    d.add_argument("--corte", default=None, dest="corte_ct", help="HH:MM hora de Chicago")
    d.add_argument("--costo-max", type=float, default=None, dest="costo_max_usd")
    a = p.add_argument_group("PCA, riesgo y régimen")
    a.add_argument("--ventana", type=int, default=None, help="días del PCA rodante")
    a.add_argument("--factores", type=int, default=None, help="K fijo (si no, análisis paralelo)")
    a.add_argument("--boot", type=int, default=None, dest="n_boot")
    a.add_argument("--pesos", default=None, help='portafolio, p. ej. "ES=1,ZN=-0.5,GC=0.3"')
    a.add_argument("--umbral", type=float, default=None, dest="umbral_prob",
                   help="P(risk-off) para declarar risk-off")
    t = p.add_argument_group("Telegram")
    t.add_argument("--telegram", action="store_true")
    t.add_argument("--telegram-solo-alertas", action="store_true")
    t.add_argument("--telegram-documentos", action="store_true")
    t.add_argument("--telegram-buscar-chat", action="store_true")
    s = p.add_argument_group("simulación")
    s.add_argument("--dias-sim", type=int, default=None, dest="sim_dias")
    s.add_argument("--semilla", type=int, default=None, dest="sim_semilla")
    return p


def config_desde_args(a: argparse.Namespace) -> Config:
    cambios = {}
    for k in ("start", "end", "dias_calentamiento", "corte_ct", "costo_max_usd", "ventana",
              "factores", "n_boot", "pesos", "umbral_prob", "sim_dias", "sim_semilla"):
        v = getattr(a, k, None)
        if v is not None:
            cambios[k] = v
    if a.activos:
        cambios["activos"] = tuple(x.strip().upper() for x in a.activos.split(",") if x.strip())
    if a.sin_cache:
        cambios["usar_cache"] = False
    return replace(CFG, **cambios)


def main(argv: list[str] | None = None) -> int:
    a = construir_parser().parse_args(argv)
    cfg = config_desde_args(a)
    if a.pruebas:
        return pruebas()
    if a.telegram_buscar_chat:
        return buscar_chat_telegram()
    if len(cfg.activos) < 3:
        sys.exit("❌ Un PCA necesita al menos 3 activos.")
    print(f"▶ {IDENTIFICADOR} · {len(cfg.activos)} activos · corte {cfg.corte_ct} CT · "
          f"ventana {cfg.ventana} días")
    verdad = None
    if a.simulacion:
        print(f"🎲 {cfg.sim_dias} días simulados: 3 factores (riesgo, tasas, dólar), régimen de "
              "Markov, quiebre de la correlación acciones-bonos, rolls y feriados CONOCIDOS.")
        crudo, verdad = simular(cfg)
    else:
        crudo = obtener_datos(cfg)
    barras = preparar_barras(crudo, cfg)
    res = analizar(barras, cfg, verdad=verdad)
    reporte_ingesta(res)
    reporte_tu_script(res)
    reporte_estatico(res)
    reporte_riesgo(res)
    reporte_dinamico(res)
    reporte_regimen(res)
    if res.medicion:
        m = res.medicion
        _titulo("8 · CONTRA LA VERDAD (sólo en simulación)")
        print(f"  Retornos reconstruidos (con rolls y feriados) vs verdaderos: error máx {m['error_retornos']:.1e}")
        print("  Subespacio de los 3 factores verdaderos contra PC1-PC3 (coseno de los ángulos "
              "principales): " + " · ".join(f"{c:.3f}" for c in m["cos_angulos"]))
        h = m["hmm"]
        print(f"  Régimen (Markov filtrado): exactitud {h['exactitud']:.1%} · precisión risk-off "
              f"{h['precision']:.1%} · exhaustividad {h['exhaustividad']:.1%}")
        if "tu_regimen" in m:
            t = m["tu_regimen"]
            print(f"  Tu regla PC1 < −2σ: {t['marcados_off']} días · precisión {t['precision']:.1%} · "
                  f"exhaustividad {t['exhaustividad']:.1%}")
        if "corr_ab" in m:
            print(f"  Correlación acciones-bonos antes / después del quiebre: "
                  f"{m['corr_ab'][0]:+.2f} / {m['corr_ab'][1]:+.2f}")
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
    print("  1. Los retornos son de corte a corte a la misma hora para todos, sin rolls: la matriz")
    print("     de correlación compara lo mismo con lo mismo.")
    print("  2. Sólo los factores que superan al ruido (análisis paralelo) cuentan como estructura.")
    print("  3. Una carga es la correlación del activo con el factor; si su IC cruza el 0, no la leas.")
    print("  4. El riesgo sistemático de cada activo está entre 0 y 100 %, y el del portafolio se")
    print("     reparte EXACTO entre factores. Apuestas efectivas = cuántas fuentes de riesgo reales.")
    print("  5. Risk-Off es un ESTADO con persistencia, no un día grande. Lo que anticipa es más")
    print("     volatilidad, no la dirección de mañana.")
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
