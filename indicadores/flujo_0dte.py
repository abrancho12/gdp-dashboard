# -*- coding: utf-8 -*-
"""
Flujo 0DTE AC v2 — exposición de los dealers en las opciones que vencen HOY (Black-76)
Datos: Databento GLBX.MDP3 — futuro, definiciones, estadísticas, cotizaciones y operaciones de las opciones.

Qué hace, en una línea: toma de CME (vía Databento) la cadena de opciones del ES que vence
HOY y el contrato de futuro EXACTO del que son opción. Cada 15 minutos del día invierte
Black-76 con el tiempo REAL que falta al vencimiento, calcula las griegas y suma la posición
estimada de los dealers. Con eso dice cuántos contratos de futuro tendrían que comprar o vender
si el precio se mueve, o si sólo pasa el tiempo. Termina con una auditoría en palabras y dos
tableros.

LO QUE PEDISTE, HECHO A FONDO

  1. INGESTA CRUZADA (CROSS-ASSET). Cinco fuentes de Databento unidas por instrument_id:
       · definiciones de toda la familia de opciones (parent symbology: ES, EW, EW1-EW4 y las
         semanales de lunes a jueves E1A…E5D), de las que se toman las que VENCEN HOY según su
         campo expiration en hora de Chicago;
       · el futuro del que son opción, por su underlying_id (no un continuo);
       · cotizaciones bbo-1m de esas opciones y de ese futuro;
       · estadísticas: OI, liquidación de ayer, y la volatilidad y delta que publica CME;
       · las operaciones del día con su lado agresor.
     Revisa el costo antes de cada descarga y guarda caché. --activo NQ hace lo mismo con el
     Nasdaq; si una familia no existe en Databento no regresa nada, y el reporte dice cuáles sí.

  2. DECODIFICACIÓN BLACK-76 INVERSA. La IV sale por bisección vectorizada (error < 1e-10 en las
     pruebas, de 5 minutos a 30 días al vencimiento) con el tiempo REAL al vencimiento: los
     minutos que faltan, no 1/365. Se calcula la IV del bid, del mid y del ask, y una σ por
     strike desde la opción fuera del dinero. Encima va un smile SUAVE ponderado por vega
     (parábola en la moneyness estandarizada, plana fuera de los datos), para que las alas con
     primas de 1-4 ticks no metan ruido. Una falla no es un 0: lleva su motivo (sin bid, bajo
     el intrínseco, spread ancho, precio mínimo). En 12 días simulados con un smile verdadero
     que NO es una parábola: error mediano 0.08 pts de vol a ±1σ (p90 0.14). Además, la
     liquidación de ayer invertida debe dar la volatilidad que publica CME (StatType 14): en
     la simulación coincide a 0.06 pts; en tus datos ese chequeo es la prueba de verdad.

  3. CÁLCULO DE "LAS GRIEGAS": delta, gamma, vega, vanna, charm y theta, en unidades de operador
     (Δ por punto, por punto de vol y por hora). El charm es el de una opción sobre FUTURO
     (acarreo 0). Todas se verifican contra diferencias finitas (error < 1e-5), y el charm
     integrado de 2 h al vencimiento da exactamente el cambio de delta.

  4. AGREGACIÓN DE RIESGO DE COBERTURA (DEALER HEDGING):
       · la posición de los dealers con tres convenciones:
           - clásica: largos en calls, cortos en puts (la de tu fórmula);
           - clientes compran: cortos en todo;
           - FLUJO (por omisión): la clásica más lo que el agresor compró o vendió hoy. En 0DTE
             el volumen del día pesa más que el OI de ayer;
       · gamma neta en contratos por punto, y GEX en dólares por 1 %;
       · el flip (gamma cero), con el perfil re-calculado en ±3 % con la σ de cada strike;
       · los muros de calls y de puts (máximo gamma × OI) y el max pain como referencia;
       · la tabla "si el futuro va a −2σ … +2σ, los dealers compran/venden X contratos";
       · el charm EXACTO a precio fijo: lo que tendrían que operar en los próximos 30 min y
         hasta el vencimiento. Y la vanna: si la IV baja 1 punto;
       · el movimiento esperado (F·σ·√T), el straddle ATM y el forward por paridad put-call.

  5. DASHBOARD VISUAL 0DTE, en dos tableros:
       · el primero: la gamma por strike con el flip y los muros; el flujo de cobertura contra
         el precio, con el movimiento esperado; el smile con su banda bid/ask; y el día
         completo con el flip, los muros y el régimen de gamma de fondo;
       · el segundo: la vanna y el charm por strike; el OI de ayer contra el volumen de hoy; la
         gamma y el charm durante el día; la sensibilidad a la convención; y la cordura.

  6. AUDITORÍA TEXTUAL. Primero, la foto en palabras: el régimen, qué hacen los dealers si sube
     10 puntos, dónde está el flip, los muros, el charm al cierre, el movimiento esperado y un
     OJO cuando el flip depende del supuesto. Después, una lista ✓/⚠: IV confiable cerca del
     dinero, paridad, IV contra la de CME, griegas contra diferencias finitas, arbitraje de
     spreads, OI publicado, ajuste del smile y flip por convención. Al final, una línea con tus
     fórmulas aplicadas a los mismos precios.

  Además: fotos cada 15 min (--paso, --hora), 4 CSV (por strike, por opción, el día y el perfil),
  Telegram con resumen y tableros, un simulador que escribe registros DBN de verdad y entra por
  la misma normalización que tus datos, y 25 pruebas internas.

QUÉ SE MIDIÓ — 12 días simulados: futuro, smile, OI y flujo de clientes conocidos

  · IV: 0.08 pts de vol de error mediano a ±1σ (p90 0.14), igual temprano que tarde.
  · Flip, convención flujo: a 2.7 pts mediana del verdadero (0.17 movimientos esperados).
    Con la clásica: 6-8 pts (0.4-0.5). Flujo fue mejor en 9 de 12 días y empató en 3; ojo,
    en el simulador el agresor ES el cliente, que es justo lo que supone la convención flujo.
  · Signo de la gamma: correcto en todas las fotos con flujo; con la clásica, en 88-100 %.
  · Los chequeos de datos y de cálculo salieron en verde en los 12 días. El aviso "el flip
    depende de la convención" saltó en 5 (diferencias de 15-23 pts), y en esos días la
    convención flujo fue la cercana.
  · Lo que NO sale preciso es la MAGNITUD: la gamma neta trae ~30-40 % de error y el charm al
    cierre ~40-55 %. Parte del OI es entre clientes y algunos strikes están al revés, y eso
    ninguna convención lo ve. Es la incertidumbre real de todo GEX.

  Tus fórmulas sobre los mismos precios, a 1 h del vencimiento:
      IV × 0.20 · gamma × 1.00 · vanna × 4.9 · charm × −0.03 a −0.05 (signo contrario)

QUÉ FALLABA EN TU SCRIPT (los comentarios [v1] lo marcan en el código)

  · LA API KEY ESTÁ ESCRITA EN LA LÍNEA 16, la misma de tus otros scripts. Regenérala; aquí se
    lee de DATABENTO_API_KEY.

  · NO CORRE, por tres razones:
      - pide "ES.OPT" con stype_in="raw_symbol", y es un símbolo parent;
      - el pivot_table usa la columna 'value', que no existe (las estadísticas traen 'price' y
        'quantity'): KeyError;
      - tu fecha, 2026-08-01, es sábado: ese día no vence nada.

  · LA ESCALA. to_df() ya entrega los precios en puntos. Dividir entre 1e9 deja el strike y el
    futuro en 0.0000055, y como el GEX multiplica por F², sale 1e-9 veces el real: en la
    simulación da exactamente 0.000.

  · EL TIPO DE ESTADÍSTICA: el 11 es el ÚLTIMO PRECIO operado; la liquidación es el 3. El OI sí
    es el 9, pero viene en 'quantity'.

  · T = 1/365. A una 0DTE a las 14:00 CT le queda 1 hora. Con el mismo precio, σ√T no cambia:
    tu IV sale √(1/24) ≈ 0.20 de la real, la vanna ×5 y el charm entre 24. La gamma y la delta
    casi no cambian, y por eso tu GEX "se ve bien".

  · EL CHARM trae un término r/(σ√T) de las opciones sobre ACCIONES (en un futuro el acarreo es
    0), y mide ∂Δ/∂τ, lo que pasa si el plazo AUMENTA. El signo es el contrario a "el tiempo
    pasa".

  · PRECIOS DE AYER CON EL FUTURO DE HOY: usa la liquidación de ayer con el último precio del
    futuro del día UTC, que es posterior al vencimiento. Si el futuro se movió, los precios
    quedan bajo el intrínseco, tu brentq regresa 0 (6 % de las opciones en la simulación) y
    ese 0 entra al promedio del smile.

  · UNIDADES MEZCLADAS EN UN SOLO EJE: el GEX en dólares por 1 %, el VEX en Δ×50 por 100 puntos
    de vol y el CEX en Δ×50 por año. Aquí todo va en contratos de futuro (por punto, por punto
    de vol y por hora), y el GEX en dólares aparte.

  · Tu comentario dice "dealers short calls, long puts", pero tu fórmula los pone LARGOS en
    calls y CORTOS en puts (la convención de SqueezeMetrics). Aquí la convención se elige y se
    reportan las tres.

  · Menores:
      - "ES.n.0" cerca de un roll puede no ser el subyacente de las opciones;
      - el 'price' de mbp-1 es el del último evento del libro, no el mid;
      - promedia la IV de call y put en cada strike (la ITM es ruido);
      - plt.show() sin guardar el tablero.

LÍMITES QUE CONVIENE SABER
  · Las posiciones de los dealers son un SUPUESTO: CME no publica quién tiene qué. El flujo del
    día supone que el agresor es el cliente; los cruces sin lado no cuentan. Lee siempre la
    tabla por convención.
  · El OI es el de la noche anterior (CME lo publica una vez al día). Lo que se abrió y cerró
    hoy sólo entra por el flujo.
  · El perfil supone σ fija por strike ("sticky strike") cuando se mueve el futuro.
  · Tiempo calendario. A minutos del vencimiento la IV de una 0DTE cambia muy rápido, y las
    alas con primas de 1-4 ticks no dan una IV confiable.
  · Black-76 es europeo. Las trimestrales ES son americanas, pero en 0DTE la diferencia es
    despreciable.
  · No pude comprobar los códigos de las semanales de NQ (QN1…, Q1A…) ni si en Databento las
    semanales de ES vienen en su propio parent o dentro de ES.OPT. Por eso se piden todas y se
    junta lo que exista; --productos las cambia.
  · bbo-1m: la foto usa la última cotización de cada minuto; no ve lo que pasa dentro del minuto.

CÓMO SE USA
    pip install numpy pandas scipy matplotlib databento
    python flujo_0dte.py --pruebas                       # 25 pruebas, sin red
    python flujo_0dte.py --simulacion                    # día 0DTE simulado con verdad conocida
    python flujo_0dte.py                                 # ES, viernes 25 de septiembre de 2026
    python flujo_0dte.py --fecha 2026-09-29 --hora 10:30 # otro día; la foto principal a las 10:30 CT
    python flujo_0dte.py --convencion clasica            # tu supuesto de posiciones
    python flujo_0dte.py --activo NQ --paso 30
    python flujo_0dte.py --productos ES,EW,EW4,E5C       # familias a pedir
    python flujo_0dte.py --telegram                      # resumen + 2 tableros
  Las horas van en hora de CHICAGO y de CDMX. El costo se revisa antes de descargar
  (--costo-max, 25 USD por omisión).

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
  Black, F. (1976), "The pricing of commodity contracts", Journal of Financial Economics 3(1-2).
  Haug, E. G. (2007), The Complete Guide to Option Pricing Formulas, 2.ª ed., McGraw-Hill. —
      las griegas de Black-76, incluidos charm y vanna.
  SqueezeMetrics (2017), "Gamma Exposure (GEX)". — la convención clásica de posiciones.
  Barbon, A. y Buraschi, A. (2021), "Gamma fragility", documento de trabajo. — la gamma de los
      dealers y la fragilidad intradía.
  Ni, S. X., Pearson, N. D. y Poteshman, A. M. (2005), "Stock price clustering on option
      expiration dates", Journal of Financial Economics 78(1). — el "pinning" al vencimiento.
  CME Group: especificaciones de las opciones E-mini S&P 500 (diarias, semanales y de fin de
      mes; tick de 0.25 y de 0.05 abajo de 5 puntos).
  Databento: https://databento.com/docs — definiciones, statistics (StatType), bbo-1m, trades
      y parent symbology.
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

import numpy as np
import pandas as pd

try:
    from scipy.special import ndtr as _ndtr
except ModuleNotFoundError:                                   # sin scipy: erfc de math, vectorizada
    _erfc = np.vectorize(math.erfc, otypes=[float])

    def _ndtr(x):
        return 0.5 * _erfc(-np.asarray(x, float) / math.sqrt(2.0))

try:
    import databento as db
except ModuleNotFoundError:
    db = None

IDENTIFICADOR = "flujo-0dte-ac-v2"
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)
np.seterr(all="ignore")

NS = 1_000_000_000
NS_MIN = 60 * NS
ANIO_S = 365.0 * 86400.0                     # tiempo CALENDARIO, en segundos por año
OI, LIQ, VOL_CME, DELTA_CME = 9, 3, 14, 15   # StatType de Databento: open interest, liquidación, vol y delta
Q_INDEF = 2 ** 31 - 1

# Familias de opciones sobre futuros de CME. Los códigos son los de Globex; los que no existan en
# Databento simplemente no regresan nada (el reporte dice cuáles sí).
ACTIVOS = {
    "ES": {"nombre": "E-mini S&P 500", "mult": 50.0, "ref": 5500.0, "paso": 5.0, "tick": 0.25, "tick_bajo": 0.05,
           "productos": ("ES", "EW", "EW1", "EW2", "EW3", "EW4") + tuple(f"E{s}{d}" for d in "ABCD" for s in "12345")},
    "NQ": {"nombre": "E-mini Nasdaq 100", "mult": 20.0, "ref": 20000.0, "paso": 10.0, "tick": 0.25, "tick_bajo": 0.05,
           "productos": ("NQ", "QN", "QN1", "QN2", "QN3", "QN4") + tuple(f"Q{s}{d}" for d in "ABCD" for s in "12345")},
}


# =============================================================================
# 1. CONFIGURACIÓN
# =============================================================================
@dataclass(frozen=True)
class Config:
    # --- Datos ---
    dataset: str = "GLBX.MDP3"
    activo: str = "ES"
    fecha: str = "2026-09-25"               # día del vencimiento (viernes). Tu 2026-08-01 era sábado.
    productos: tuple[str, ...] | None = None  # None = la familia del activo
    cache_dir: str = "datos_databento"
    salida_dir: str = "salidas_0dte"
    costo_max_usd: float = 25.0
    tz_mercado: str = "America/Chicago"
    tz_local: str = "America/Mexico_City"

    # --- Fotos del día ---
    desde: str = "08:30"                    # hora de Chicago (09:30 Nueva York)
    paso_min: int = 15
    hora: str | None = None                 # foto principal (CT); None = la última antes del vencimiento
    antiguedad_max_min: int = 5             # una cotización más vieja que esto no cuenta

    # --- Black-76 ---
    tasa: float = 0.04                      # r: en 0DTE casi no importa (e^(−rT) ≈ 1)
    iv_min: float = 0.005
    iv_max: float = 5.0
    spread_max: float = 0.6                 # (ask − bid) / mid máximo para confiar en la IV
    ticks_min: float = 2.0                  # mid de al menos 2 ticks bajos (si no, la IV es ruido)

    # --- Cobertura de dealers ---
    convencion: str = "flujo"               # clasica | clientes_compran | flujo
    rango_pct: float = 0.03                 # perfil de cobertura: ±3 % alrededor del futuro
    n_rejilla: int = 241

    # --- Simulación ---
    sim_semilla: int = 0
    sim_vol: float = 0.15                   # volatilidad verdadera del futuro (anual)


CFG = Config()
CARPETA_SCRIPT = Path(__file__).resolve().parent
CONVENCIONES = ("clasica", "clientes_compran", "flujo")


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


def activo(cfg: Config) -> dict:
    return ACTIVOS.get(cfg.activo.upper(), {"nombre": cfg.activo, "mult": 1.0, "ref": 100.0, "paso": 1.0,
                                           "tick": 0.01, "tick_bajo": 0.01, "productos": (cfg.activo.upper(),)})


def productos_de(cfg: Config) -> tuple[str, ...]:
    return tuple(cfg.productos) if cfg.productos else activo(cfg)["productos"]


def hora_ct(cfg: Config, hhmm: str, dia: pd.Timestamp | None = None) -> pd.Timestamp:
    """'08:30' del día del vencimiento, hora de Chicago → UTC."""
    d = pd.Timestamp(cfg.fecha) if dia is None else dia
    h, m = (int(x) for x in hhmm.split(":"))
    return (d.normalize() + pd.Timedelta(hours=h, minutes=m)).tz_localize(cfg.tz_mercado).tz_convert("UTC").as_unit("ns")


def validar(cfg: Config) -> None:
    if pd.Timestamp(cfg.fecha).dayofweek >= 5:
        sys.exit(f"❌ {cfg.fecha} es {pd.Timestamp(cfg.fecha).day_name()}: ese día no vence ninguna opción de CME.")
    if cfg.convencion not in CONVENCIONES:
        sys.exit(f"❌ La convención debe ser una de {', '.join(CONVENCIONES)}.")
    if not (0 < cfg.rango_pct < 0.2) or cfg.paso_min < 1:
        sys.exit("❌ rango_pct entre 0 y 0.2 y paso_min ≥ 1.")


# =============================================================================
# 2. INGESTA CRUZADA — futuro + definiciones + estadísticas + cotizaciones + operaciones
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
    "  • La que estaba escrita en tu script (línea 16) hay que darla por publicada: regenérala en\n"
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


@dataclass
class Datos:
    """Todo lo del día, ya normalizado: así el cálculo no sabe si viene de Databento o del simulador."""
    defs: pd.DataFrame          # index iid: simbolo, producto, tipo (C/P), strike, vence (UTC), subyacente, sub_id, mult
    fut: pd.DataFrame           # t (UTC, cuando se CONOCE), sub_id, bid, ask
    cot: pd.DataFrame           # t, iid, bid, ask de las opciones (bbo-1m)
    stats: pd.DataFrame         # iid: oi, oi_t, oi_ref, liq, liq_ref, vol_cme, delta_cme
    ops: pd.DataFrame           # t, iid, precio, tam, lado (+1 compra agresora, −1 venta, 0 sin lado)
    fut_liq: dict               # sub_id → (liquidación anterior, fecha)
    meta: dict


def _descargar(cliente, cfg: Config, nombre_: str, **params):
    """Una petición con caché en disco; regresa (DBNStore, costo)."""
    carpeta = _ruta(cfg.cache_dir)
    carpeta.mkdir(parents=True, exist_ok=True)
    huella = uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(params, sort_keys=True, default=str)).hex[:10]
    clave = _nombre_seguro(cfg.dataset, nombre_, cfg.fecha, huella)
    ruta = carpeta / f"0dte_{clave}.dbn.zst"
    if ruta.exists():
        return db.DBNStore.from_file(ruta), 0.0
    costo = cliente.metadata.get_cost(dataset=cfg.dataset, **params)
    if costo > cfg.costo_max_usd:
        sys.exit(f"💰 {nombre_}: el costo (US$ {costo:,.2f}) supera tu tope de US$ {cfg.costo_max_usd:,.2f}.\n"
                 f"   Si estás de acuerdo:  --costo-max {math.ceil(costo) + 1}")
    temporal = ruta.with_name(ruta.name + ".parcial")
    temporal.unlink(missing_ok=True)
    descarga = cliente.timeseries.get_range(dataset=cfg.dataset, path=temporal, **params)
    del descarga
    temporal.replace(ruta)
    return db.DBNStore.from_file(ruta), costo


def _tabla(tienda) -> pd.DataFrame:
    df = tienda.to_df()
    return df.reset_index() if len(df) else df


def norm_definiciones(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """
    Definiciones → opciones que vencen el día de cfg.fecha (hora de Chicago).

    [v1] Tu script divide strike_price entre 1e9, pero to_df() ya lo entrega en puntos (5500.0):
    el strike quedaba en 0.0000055 y, como el GEX multiplica por F², salía ~1e-9 veces el real.
    """
    if df.empty:
        return pd.DataFrame(columns=["simbolo", "producto", "tipo", "strike", "vence", "subyacente", "sub_id", "mult"])
    d = df[df["instrument_class"].isin(["C", "P"])].copy()
    d = d.sort_values("ts_recv").drop_duplicates("instrument_id", keep="last")
    mult = pd.to_numeric(d.get("unit_of_measure_qty"), errors="coerce")
    out = pd.DataFrame({
        "simbolo": d["raw_symbol"].astype(str).to_numpy(), "producto": d["asset"].astype(str).to_numpy(),
        "tipo": d["instrument_class"].astype(str).to_numpy(), "strike": d["strike_price"].astype(float).to_numpy(),
        "vence": pd.to_datetime(d["expiration"], utc=True).to_numpy(),
        "subyacente": d["underlying"].astype(str).to_numpy(),
        "sub_id": pd.to_numeric(d.get("underlying_id"), errors="coerce").fillna(0).astype(np.int64).to_numpy(),
        "mult": np.where(np.isfinite(mult) & (mult > 0), mult, activo(cfg)["mult"]),
    }, index=pd.Index(d["instrument_id"].astype(np.int64).to_numpy(), name="iid"))
    out["vence"] = pd.to_datetime(out["vence"], utc=True)
    dia = out["vence"].dt.tz_convert(cfg.tz_mercado).dt.date
    return out[(dia == pd.Timestamp(cfg.fecha).date()) & out["strike"].notna() & out["vence"].notna()]


def norm_bbo(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["t", "iid", "bid", "ask"])
    bid = df["bid_px_00"].astype(float).where(df["bid_sz_00"] > 0)
    ask = df["ask_px_00"].astype(float).where(df["ask_sz_00"] > 0)
    return pd.DataFrame({"t": pd.to_datetime(df["ts_recv"], utc=True), "iid": df["instrument_id"].astype(np.int64),
                         "bid": bid, "ask": ask}).sort_values("t", kind="stable").reset_index(drop=True)


def norm_estadisticas(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """
    El OI que se conoce (el último publicado) y la liquidación ANTERIOR con su vol y delta de CME.

    [v1] Tu pivot_table usa la columna 'value', que no existe (son 'price' y 'quantity'), y toma el
    tipo 11 como liquidación: el 11 es el ÚLTIMO PRECIO operado; la liquidación es el 3. El OI (9)
    viene en 'quantity'.
    """
    cols = ["oi", "oi_t", "oi_ref", "liq", "liq_ref", "vol_cme", "delta_cme"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    d = df.sort_values("ts_recv", kind="stable")
    dia = pd.Timestamp(cfg.fecha).date()
    ref = pd.to_datetime(d["ts_ref"], utc=True)
    out = pd.DataFrame(index=pd.Index(sorted(d["instrument_id"].astype(np.int64).unique()), name="iid"), columns=cols)
    o = d[(d["stat_type"] == OI) & (d["quantity"] != Q_INDEF)]
    if len(o):
        u = o.groupby("instrument_id").last()
        out.loc[u.index, "oi"] = u["quantity"].astype(float).to_numpy()
        out.loc[u.index, "oi_t"] = pd.to_datetime(u["ts_recv"], utc=True).to_numpy()
        out.loc[u.index, "oi_ref"] = pd.to_datetime(u["ts_ref"], utc=True).to_numpy()
    for tipo, col in ((LIQ, "liq"), (VOL_CME, "vol_cme"), (DELTA_CME, "delta_cme")):
        s = d[(d["stat_type"] == tipo) & d["price"].notna() & (ref.dt.tz_convert("UTC").dt.date < dia)]
        if len(s):
            u = s.groupby("instrument_id").last()
            out.loc[u.index, col] = u["price"].astype(float).to_numpy()
            if tipo == LIQ:
                out.loc[u.index, "liq_ref"] = pd.to_datetime(u["ts_ref"], utc=True).to_numpy()
    for c in ("oi", "liq", "vol_cme", "delta_cme"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


def norm_operaciones(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["t", "iid", "precio", "tam", "lado"])
    lado = np.select([df["side"] == "B", df["side"] == "A"], [1, -1], 0)
    return pd.DataFrame({"t": pd.to_datetime(df["ts_recv"], utc=True), "iid": df["instrument_id"].astype(np.int64),
                         "precio": df["price"].astype(float), "tam": df["size"].astype(np.int64),
                         "lado": lado}).sort_values("t", kind="stable").reset_index(drop=True)


def obtener_datos(cfg: Config, cliente=None) -> Datos:
    """
    La ingesta cruzada, en dos pasos con revisión de costo:
      1) definiciones de toda la familia (parent symbology) → las opciones que vencen HOY y el
         contrato de futuro EXACTO del que son opción (campo underlying_id, no un continuo);
      2) para esas opciones y ese futuro: cotizaciones bbo-1m, estadísticas y operaciones.

    [v1] Tu script pide "ES.OPT" con stype_in="raw_symbol" (es un símbolo parent) y el futuro
    "ES.n.0": cerca de un roll, el continuo puede ser OTRO contrato que el subyacente de las opciones.
    """
    cliente = cliente or conectar()
    dia = pd.Timestamp(cfg.fecha)
    padres = [f"{p}.OPT" for p in productos_de(cfg)]
    print(f"📡 Definiciones de {len(padres)} familias de opciones ({', '.join(productos_de(cfg)[:6])}…) para {cfg.fecha}")
    t_def, c1 = _descargar(cliente, cfg, "definiciones", symbols=padres, stype_in="parent", schema="definition",
                           start=dia.strftime("%Y-%m-%dT00:00:00"), end=(dia + pd.Timedelta(days=1)).strftime("%Y-%m-%dT00:00:00"))
    df_def = _tabla(t_def)
    defs = norm_definiciones(df_def, cfg)
    if defs.empty:
        sys.exit(f"❌ Ninguna opción de {cfg.activo} vence el {cfg.fecha}. Revisa la fecha o --productos.")
    ids = sorted(int(i) for i in defs.index)
    subs = sorted(int(s) for s in defs["sub_id"].unique() if s > 0)
    inicio = hora_ct(cfg, "17:00", dia - pd.Timedelta(days=1))
    fin = defs["vence"].max() + pd.Timedelta(minutes=10)
    print(f"✅ {len(defs)} opciones 0DTE ({defs['tipo'].eq('C').sum()} calls, {defs['tipo'].eq('P').sum()} puts) de "
          f"{', '.join(sorted(defs['producto'].unique()))} · subyacente {', '.join(sorted(defs['subyacente'].unique()))}")
    rango = dict(start=inicio.strftime("%Y-%m-%dT%H:%M:%S"), end=fin.strftime("%Y-%m-%dT%H:%M:%S"))
    desde_liq = hora_ct(cfg, "14:00", dia - pd.Timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    pedidos = [("cotizaciones", dict(symbols=ids, stype_in="instrument_id", schema="bbo-1m", **rango)),
               ("estadisticas", dict(symbols=ids + subs, stype_in="instrument_id", schema="statistics",
                                     start=desde_liq, end=rango["end"])),
               ("operaciones", dict(symbols=ids, stype_in="instrument_id", schema="trades", **rango))]
    if subs:
        pedidos.append(("futuro", dict(symbols=subs, stype_in="instrument_id", schema="bbo-1m", **rango)))
    else:
        pedidos.append(("futuro", dict(symbols=sorted(defs["subyacente"].unique()), stype_in="raw_symbol",
                                       schema="bbo-1m", **rango)))
    tablas, costo = {}, c1
    for nombre_, params in pedidos:
        print(f"📡 {nombre_} …")
        tienda, c = _descargar(cliente, cfg, nombre_, **params)
        tablas[nombre_] = _tabla(tienda)
        costo += c
    print(f"💵 Costo de esta corrida: US$ {costo:,.2f} (lo que ya estaba en caché no se vuelve a cobrar)")
    return armar_datos(defs, tablas["futuro"], tablas["cotizaciones"], tablas["estadisticas"], tablas["operaciones"],
                       cfg, {"padres": padres, "productos_con_0dte": sorted(defs["producto"].unique()),
                             "definiciones": len(df_def), "costo": costo})


def armar_datos(defs, df_fut, df_cot, df_stats, df_ops, cfg: Config, meta: dict) -> Datos:
    fut = norm_bbo(df_fut).rename(columns={"iid": "sub_id"})
    if len(fut) and not (defs["sub_id"] > 0).any():
        defs = defs.assign(sub_id=int(fut["sub_id"].iloc[0]))
    st_all = norm_estadisticas(df_stats, cfg)
    fut_liq = {}
    for s in defs["sub_id"].unique():
        if s in st_all.index and np.isfinite(st_all.loc[s, "liq"]):
            fut_liq[int(s)] = (float(st_all.loc[s, "liq"]), st_all.loc[s, "liq_ref"])
    stats = st_all.reindex(defs.index)
    return Datos(defs=defs, fut=fut, cot=norm_bbo(df_cot), stats=stats, ops=norm_operaciones(df_ops),
                 fut_liq=fut_liq, meta=meta)


# =============================================================================
# 3. BLACK-76: PRECIO, VOLATILIDAD IMPLÍCITA INVERSA Y GRIEGAS
# =============================================================================
SQ2PI = math.sqrt(2.0 * math.pi)
HORAS_ANIO = 365.0 * 24.0


def _npdf(x):
    return np.exp(-0.5 * x * x) / SQ2PI


def _arr(*xs):
    return [np.asarray(x, dtype=float) for x in np.broadcast_arrays(*xs)]


def precio_b76(F, K, T, r, s, call) -> np.ndarray:
    """Black (1976): opción europea sobre un futuro, descontada a la tasa r."""
    F, K, T, s = _arr(F, K, T, s)
    call = np.broadcast_to(np.asarray(call, bool), F.shape)
    df = np.exp(-r * np.maximum(T, 0))
    v = s * np.sqrt(np.maximum(T, 0))
    ok = v > 0
    with np.errstate(all="ignore"):
        d1 = np.where(ok, (np.log(F / K) + 0.5 * v * v) / np.where(ok, v, 1), 0)
        d2 = d1 - v
        c = df * (F * _ndtr(d1) - K * _ndtr(d2))
        p = df * (K * _ndtr(-d2) - F * _ndtr(-d1))
    intr = df * np.where(call, np.maximum(F - K, 0), np.maximum(K - F, 0))
    return np.where(ok, np.where(call, c, p), intr)


def iv_b76(precio, F, K, T, r, call, lo: float = 0.005, hi: float = 5.0, iteraciones: int = 90):
    """
    Volatilidad implícita: el σ que hace que Black-76 dé el precio observado. Bisección
    vectorizada (el precio es creciente en σ), sin depender de scipy. Regresa (iv, motivo).

    [v1] Tu brentq regresa 0.0 cuando falla y ese 0 entra a los promedios del smile; aquí la
    falla es NaN con su motivo (sin precio, bajo el intrínseco, fuera de rango).
    """
    precio, F, K, T = _arr(precio, F, K, T)
    call = np.broadcast_to(np.asarray(call, bool), F.shape)
    df = np.exp(-r * np.maximum(T, 0))
    intr = df * np.where(call, np.maximum(F - K, 0), np.maximum(K - F, 0))
    techo = df * np.where(call, F, K)
    motivo = np.full(F.shape, "", dtype=object)
    motivo[~np.isfinite(precio) | (precio <= 0)] = "sin precio"
    motivo[(motivo == "") & (T <= 0)] = "vencida"
    motivo[(motivo == "") & (precio <= intr + 1e-12)] = "bajo el intrínseco"
    motivo[(motivo == "") & (precio >= techo)] = "sobre el máximo"
    a, b = np.full(F.shape, lo), np.full(F.shape, hi)
    sano = motivo == ""
    p_lo, p_hi = precio_b76(F, K, T, r, a, call), precio_b76(F, K, T, r, b, call)
    motivo[sano & (precio < p_lo)] = f"IV < {lo:.1%}"
    motivo[sano & (precio > p_hi)] = f"IV > {hi:.0%}"
    for _ in range(iteraciones):
        m = 0.5 * (a + b)
        arriba = precio_b76(F, K, T, r, m, call) > precio
        b = np.where(arriba, m, b)
        a = np.where(arriba, a, m)
    iv = 0.5 * (a + b)
    iv[motivo != ""] = np.nan
    return iv, motivo


def griegas(F, K, T, r, s, call) -> dict[str, np.ndarray]:
    """
    Griegas de Black-76, en unidades de operador:
      delta  contratos de futuro por opción          gamma  Δ por 1 punto del futuro
      vega   puntos de prima por 1 punto de vol      vanna  Δ por 1 punto de vol
      charm  Δ por HORA que pasa (tiempo calendario) theta  puntos de prima por día

    [v1] Tu charm tiene un término r/(σ√T) de las opciones sobre ACCIONES (costo de acarreo r);
    para un futuro el acarreo es 0. Aquí: ∂Δ/∂t = e^(−rT)·[r·Δ* + n(d1)·d2/(2T)], con Δ* = N(d1)
    en calls y N(d1) − 1 en puts. Las pruebas lo verifican con diferencias finitas.
    """
    F, K, T, s = _arr(F, K, T, s)
    call = np.broadcast_to(np.asarray(call, bool), F.shape)
    df = np.exp(-r * T)
    sq = np.sqrt(T)
    v = s * sq
    d1 = (np.log(F / K) + 0.5 * v * v) / v
    d2 = d1 - v
    n1, N1 = _npdf(d1), _ndtr(d1)
    base = np.where(call, N1, N1 - 1.0)
    precio = precio_b76(F, K, T, r, s, call)
    return {"delta": df * base, "gamma": df * n1 / (F * v),
            "vega": F * df * n1 * sq / 100, "vanna": -df * n1 * d2 / s / 100,
            "charm": df * (r * base + n1 * d2 / (2 * T)) / HORAS_ANIO,
            "theta": (r * precio - F * df * n1 * s / (2 * sq)) / 365, "precio": precio}


def delta_vencimiento(F, K, call) -> np.ndarray:
    F, K = _arr(F, K)
    call = np.broadcast_to(np.asarray(call, bool), F.shape)
    c = np.where(F > K, 1.0, np.where(F < K, 0.0, 0.5))
    return np.where(call, c, c - 1.0)


# =============================================================================
# 4. LA FOTO DE UN MOMENTO: IV, GRIEGAS Y COBERTURA DE LOS DEALERS
# =============================================================================
class Rejilla:
    """Cotizaciones por minuto en una matriz (minuto × instrumento), arrastradas hasta 'antigüedad'."""

    def __init__(self, df: pd.DataFrame, col: str, ids, antiguedad: int):
        ids = list(ids)
        self.antiguedad = pd.Timedelta(minutes=antiguedad)
        if df.empty:
            self.t = pd.DatetimeIndex([], tz="UTC")
            self.bid = self.ask = np.empty((0, len(ids)))
            self.ids = ids
            return
        # un registro nuevo SIN bid significa "sin bid ahora": centinela −1 para que no se arrastre el viejo
        d = df.assign(m=df["t"].dt.ceil("min"), bid=df["bid"].fillna(-1.0), ask=df["ask"].fillna(-1.0))
        d = d.drop_duplicates(["m", col], keep="last")
        idx = pd.date_range(d["m"].min(), d["m"].max(), freq="1min")
        piv_b = d.pivot(index="m", columns=col, values="bid").reindex(index=idx, columns=ids).ffill(limit=antiguedad)
        piv_a = d.pivot(index="m", columns=col, values="ask").reindex(index=idx, columns=ids).ffill(limit=antiguedad)
        self.bid = piv_b.where(piv_b >= 0).to_numpy(float)
        self.ask = piv_a.where(piv_a >= 0).to_numpy(float)
        self.t, self.ids = idx, ids

    def en(self, t: pd.Timestamp) -> tuple[np.ndarray, np.ndarray]:
        i = self.t.searchsorted(t, side="right") - 1
        if i < 0 or t - self.t[i] > self.antiguedad:          # después del último dato también caduca
            n = len(self.ids)
            return np.full(n, np.nan), np.full(n, np.nan)
        return self.bid[i], self.ask[i]


@dataclass
class Foto:
    t: pd.Timestamp
    F: float
    tab: pd.DataFrame
    strikes: pd.DataFrame
    perfil: pd.DataFrame
    tot: dict


def posiciones(oi: np.ndarray, flujo: np.ndarray, call: np.ndarray, conv: str) -> np.ndarray:
    """
    Posición de los DEALERS por opción (contratos; + = largos):
      clasica          largos en calls, cortos en puts (el cliente vende calls y compra puts: la
                       convención de SqueezeMetrics y de tu fórmula, aunque tu comentario dice
                       lo contrario);
      clientes_compran cortos en todo (el cliente sólo compra);
      flujo            clasica + lo que los dealers vendieron/compraron HOY: si el agresor compra,
                       el dealer vende. En 0DTE el volumen del día pesa más que el OI de ayer.
    """
    base = np.where(call, oi, -oi) if conv != "clientes_compran" else -oi
    return base + flujo if conv == "flujo" else base


def _flip(rej: np.ndarray, g: np.ndarray, F: float) -> float:
    s = np.sign(g)
    cruces = np.flatnonzero(s[:-1] * s[1:] < 0)
    if not len(cruces):
        return np.nan
    x = [rej[i] - g[i] * (rej[i + 1] - rej[i]) / (g[i + 1] - g[i]) for i in cruces]
    return float(min(x, key=lambda v: abs(v - F)))


def perfil_dealers(F, K, T, r, s, call, pos, cfg: Config) -> pd.DataFrame:
    """Delta y gamma de los dealers si el futuro estuviera en F' (σ fija por strike)."""
    rej = F * (1 + np.linspace(-cfg.rango_pct, cfg.rango_pct, cfg.n_rejilla))
    ok = np.isfinite(s) & (pos != 0)
    if not ok.any():
        return pd.DataFrame({"F": rej, "delta": 0.0, "gamma": 0.0, "flujo": 0.0})
    g = griegas(rej[:, None], K[ok][None, :], T[ok][None, :], r, s[ok][None, :], call[ok][None, :])
    d = (g["delta"] * pos[ok]).sum(1)
    gm = (g["gamma"] * pos[ok]).sum(1)
    d0 = (griegas(F, K[ok], T[ok], r, s[ok], call[ok])["delta"] * pos[ok]).sum()
    return pd.DataFrame({"F": rej, "delta": d, "gamma": gm, "flujo": -(d - d0)})


def _sigma_por_strike(t: pd.DataFrame, F: float) -> tuple[np.ndarray, np.ndarray]:
    """
    Una σ por strike: la de la opción FUERA del dinero (put abajo del futuro, call arriba), que es
    la líquida; si no sirve, la del otro lado; si ninguna, interpolada entre strikes vecinos.
    """
    ks = np.sort(t["strike"].unique())
    v = t[t["valida"]].pivot_table(index="strike", columns="tipo", values="iv_mid", aggfunc="first")
    v = v.reindex(index=ks, columns=["C", "P"])
    c, p = v["C"].to_numpy(float), v["P"].to_numpy(float)
    otm, itm = np.where(ks < F, p, c), np.where(ks < F, c, p)
    sig = np.where(np.isfinite(otm), otm, itm)
    fuente = np.where(np.isfinite(otm), "fuera del dinero",
                      np.where(np.isfinite(itm), "dentro del dinero", "interpolada")).astype(object)
    ok = np.isfinite(sig)
    if ok.sum() >= 2:
        fuera = (ks < ks[ok].min()) | (ks > ks[ok].max())
        sig[~ok] = np.interp(ks[~ok], ks[ok], sig[ok])
        fuente[~ok & fuera] = "extrapolada (plana)"
    elif ok.sum() == 1:
        sig[~ok] = sig[ok][0]
    return ks, np.vstack([sig, fuente])


def ajustar_smile(tab: pd.DataFrame, F: float, r: float) -> tuple[dict | None, float]:
    """
    Smile suave: σ(x) = a + b·x + c·x² con x = ln(K/F) / (σ_atm·√T), por mínimos cuadrados
    ponderados por VEGA con las opciones fuera del dinero válidas. Las alas (primas de 1-4 ticks,
    donde un tick mueve la IV varios puntos) casi no pesan. Fuera del rango con datos, plano.
    Regresa (parámetros, RMSE en puntos de vol ponderado por vega).
    """
    otm = tab[np.where(tab["strike"] < F, tab["tipo"] == "P", tab["tipo"] == "C") & tab["valida"]]
    if len(otm) < 5:
        return None, np.nan
    K, T, s = otm["strike"].to_numpy(float), otm["T"].to_numpy(float), otm["iv_mid"].to_numpy(float)
    s0 = float(np.interp(F, *zip(*sorted(zip(K, s)))))
    x = np.log(K / F) / (s0 * np.sqrt(T))
    w = griegas(F, K, T, r, s, (otm["tipo"] == "C").to_numpy())["vega"]
    w = np.where(np.isfinite(w) & (w > 0), w, 0)
    if np.ptp(x) < 0.5 or w.sum() <= 0:
        return None, np.nan
    A = np.column_stack([np.ones_like(x), x, x * x]) * np.sqrt(w)[:, None]
    coef = np.linalg.lstsq(A, s * np.sqrt(w), rcond=None)[0]
    res_ = s - (coef[0] + coef[1] * x + coef[2] * x * x)
    rmse = float(np.sqrt(np.sum(w * res_ ** 2) / w.sum())) * 100
    return {"coef": coef, "s0": s0, "x_min": float(x.min()), "x_max": float(x.max()), "T": float(np.median(T))}, rmse


def sigma_ajustada(p: dict, K, F: float, T, lo: float, hi: float) -> np.ndarray:
    x = np.clip(np.log(np.asarray(K, float) / F) / (p["s0"] * np.sqrt(np.asarray(T, float))), p["x_min"], p["x_max"])
    a, b, c = p["coef"]
    return np.clip(a + b * x + c * x * x, lo, hi)


def foto(datos: Datos, cfg: Config, t: pd.Timestamp, rej_cot: Rejilla | None = None,
         rej_fut: Rejilla | None = None, conv: str | None = None) -> Foto | None:
    conv = conv or cfg.convencion
    r = cfg.tasa
    a = activo(cfg)
    defs = datos.defs
    rej_cot = rej_cot or Rejilla(datos.cot, "iid", defs.index, cfg.antiguedad_max_min)
    rej_fut = rej_fut or Rejilla(datos.fut, "sub_id", sorted(defs["sub_id"].unique()), cfg.antiguedad_max_min)
    fb, fa = rej_fut.en(t)
    Fs = {s: (b + a_) / 2 for s, b, a_ in zip(rej_fut.ids, fb, fa) if np.isfinite(b) and np.isfinite(a_)}
    if not Fs:
        return None
    bid, ask = rej_cot.en(t)
    tab = defs.copy()
    tab["F"] = tab["sub_id"].map(Fs)
    tab["bid"], tab["ask"] = bid, ask
    tab = tab[(tab["vence"] > t + pd.Timedelta(minutes=1)) & tab["F"].notna()].copy()
    if tab.empty:
        return None
    F = float(np.median(tab["F"]))
    tab["T"] = (tab["vence"] - t).dt.total_seconds().to_numpy() / ANIO_S
    call = (tab["tipo"] == "C").to_numpy()
    K, T, Fo = tab["strike"].to_numpy(float), tab["T"].to_numpy(float), tab["F"].to_numpy(float)
    b_, a_ = tab["bid"].to_numpy(float), tab["ask"].to_numpy(float)
    con_bid = np.isfinite(b_) & (b_ > 0)
    mid = np.where(con_bid & np.isfinite(a_) & (a_ >= b_), 0.5 * (b_ + a_), np.nan)
    tab["mid"] = mid
    tab["iv_mid"], tab["motivo"] = iv_b76(mid, Fo, K, T, r, call, cfg.iv_min, cfg.iv_max)
    tab["iv_bid"] = iv_b76(np.where(con_bid, b_, np.nan), Fo, K, T, r, call, cfg.iv_min, cfg.iv_max)[0]
    tab["iv_ask"] = iv_b76(a_, Fo, K, T, r, call, cfg.iv_min, cfg.iv_max)[0]
    spread = (a_ - b_) / mid
    tab.loc[np.isfinite(mid) & (spread > cfg.spread_max) & (tab["motivo"] == ""), "motivo"] = "spread muy ancho"
    tab.loc[np.isfinite(mid) & (mid < cfg.ticks_min * a["tick_bajo"]) & (tab["motivo"] == ""), "motivo"] = "precio mínimo"
    tab.loc[~con_bid & (tab["motivo"] == "sin precio"), "motivo"] = "sin bid"
    tab["valida"] = tab["motivo"] == ""
    ks, sf = _sigma_por_strike(tab, F)
    tab["iv_crudo"] = tab["strike"].map(dict(zip(ks, sf[0].astype(float)))).astype(float)
    tab["fuente_iv"] = tab["strike"].map(dict(zip(ks, sf[1])))
    ajuste, rmse = ajustar_smile(tab, F, r)
    if ajuste is not None:
        tab["iv"] = sigma_ajustada(ajuste, K, F, T, cfg.iv_min, cfg.iv_max)
        tab["fuente_iv"] = "smile ajustado"
    else:
        tab["iv"] = tab["iv_crudo"]
    mapa_s = tab.groupby("strike")["iv"].first().to_dict()
    s = tab["iv"].to_numpy(float)
    g = griegas(Fo, K, T, r, s, call)
    for k_, v in g.items():
        tab[k_] = v
    # posiciones: OI conocido a esa hora + flujo agresor de hoy hasta esa hora
    oi = datos.stats["oi"].reindex(tab.index).fillna(0).to_numpy(float)
    if "oi_t" in datos.stats and datos.stats["oi_t"].notna().any():
        conocido = pd.to_datetime(datos.stats["oi_t"].reindex(tab.index), utc=True) <= t
        oi = np.where(conocido.to_numpy(), oi, 0.0)
    ops = datos.ops[datos.ops["t"] <= t]
    neto = ops.assign(x=ops["lado"] * ops["tam"]).groupby("iid")["x"].sum() if len(ops) else pd.Series(dtype=float)
    flujo = -neto.reindex(tab.index).fillna(0).to_numpy(float)
    vol_hoy = ops.groupby("iid")["tam"].sum().reindex(tab.index).fillna(0).to_numpy(float) if len(ops) else np.zeros(len(tab))
    tab["oi"], tab["flujo"], tab["vol_hoy"] = oi, flujo, vol_hoy
    pos = posiciones(oi, flujo, call, conv)
    tab["pos"] = pos
    mult = tab["mult"].to_numpy(float)
    for k_ in ("delta", "gamma", "vanna", "charm"):
        tab["e_" + k_] = pos * tab[k_].to_numpy(float)
    tab["e_cierre"] = pos * (delta_vencimiento(Fo, K, call) - tab["delta"].to_numpy(float))
    T30 = np.maximum(T - 1800 / ANIO_S, 1e-12)
    d30 = np.where(T > 1800 / ANIO_S, griegas(Fo, K, T30, r, s, call)["delta"], delta_vencimiento(Fo, K, call))
    tab["e_30m"] = pos * (d30 - tab["delta"].to_numpy(float))
    tab["gex_usd"] = tab["e_gamma"] * 0.01 * Fo * Fo * mult
    # por strike
    cc, pp = tab[tab["tipo"] == "C"], tab[tab["tipo"] == "P"]
    st = pd.DataFrame(index=pd.Index(ks, name="strike"))
    st["gamma_c"] = cc.groupby("strike")["e_gamma"].sum()
    st["gamma_p"] = pp.groupby("strike")["e_gamma"].sum()
    for k_ in ("e_gamma", "e_delta", "e_vanna", "e_charm", "gex_usd"):
        st[k_] = tab.groupby("strike")[k_].sum()
    st["oi_c"], st["oi_p"] = cc.groupby("strike")["oi"].sum(), pp.groupby("strike")["oi"].sum()
    st["vol_c"], st["vol_p"] = cc.groupby("strike")["vol_hoy"].sum(), pp.groupby("strike")["vol_hoy"].sum()
    st["g_oi_c"] = (cc["gamma"] * cc["oi"]).groupby(cc["strike"]).sum()
    st["g_oi_p"] = (pp["gamma"] * pp["oi"]).groupby(pp["strike"]).sum()
    st["iv"] = pd.Series(mapa_s)
    st = st.fillna({c: 0.0 for c in st.columns if c != "iv"})
    perf = perfil_dealers(F, K, T, r, s, call, pos, cfg)
    tot = totales(tab, st, perf, F, t, cfg, datos)
    tot["conv"] = conv
    tot["ajuste_rmse"] = rmse
    tot["por_convencion"] = {}
    for cv in CONVENCIONES:
        p_ = posiciones(oi, flujo, call, cv)
        pf = perf if cv == conv else perfil_dealers(F, K, T, r, s, call, p_, cfg)
        tot["por_convencion"][cv] = {"gamma": float(np.nansum(p_ * tab["gamma"].to_numpy(float))),
                                     "flip": _flip(pf["F"].to_numpy(), pf["gamma"].to_numpy(), F)}
    return Foto(t, F, tab, st, perf, tot)


def totales(tab, st, perf, F, t, cfg: Config, datos: Datos) -> dict:
    r = cfg.tasa
    a = activo(cfg)
    T_med = float(np.median(tab["T"]))
    atm = st.index[np.argmin(np.abs(st.index.to_numpy() - F))]
    sig_atm = float(np.interp(F, st.index.to_numpy(float), st["iv"].to_numpy(float)))
    c_atm = tab[(tab["strike"] == atm) & (tab["tipo"] == "C")]["mid"]
    p_atm = tab[(tab["strike"] == atm) & (tab["tipo"] == "P")]["mid"]
    straddle = float(c_atm.iloc[0] + p_atm.iloc[0]) if len(c_atm) and len(p_atm) else np.nan
    # paridad put-call cerca del dinero: F = K + e^(rT)·(C − P)
    cerca = tab[np.abs(tab["strike"] - F) <= 0.01 * F]
    piv = cerca.pivot_table(index="strike", columns="tipo", values="mid", aggfunc="first")
    f_par = np.nan
    if {"C", "P"} <= set(piv.columns):
        pp_ = piv.dropna()
        if len(pp_):
            f_par = float(np.median(pp_.index + np.exp(r * T_med) * (pp_["C"] - pp_["P"])))
    max_pain = dolor_maximo(st)
    arriba, abajo = st[st.index >= F], st[st.index <= F]
    gamma = float(tab["e_gamma"].sum())
    flip = _flip(perf["F"].to_numpy(), perf["gamma"].to_numpy(), F)
    validas = tab["valida"]
    mov = F * sig_atm * math.sqrt(T_med) if np.isfinite(sig_atm) else np.nan
    usadas = np.where(tab["strike"] < F, tab["tipo"] == "P", tab["tipo"] == "C") & (np.abs(tab["strike"] - F) <= mov)
    return {"F": F, "usadas": int(usadas.sum()), "usadas_ok": int((usadas & validas).sum()),
            "T_h": T_med * HORAS_ANIO, "delta": float(tab["e_delta"].sum()), "gamma": gamma,
            "gex_usd": float(tab["gex_usd"].sum()), "vanna": float(tab["e_vanna"].sum()),
            "charm": float(tab["e_charm"].sum()), "cierre": float(tab["e_cierre"].sum()),
            "charm_30m": float(tab["e_30m"].sum()),
            "flip": flip, "regimen": "POSITIVA" if gamma > 0 else "NEGATIVA",
            "muro_call": float(arriba["g_oi_c"].idxmax()) if len(arriba) and arriba["g_oi_c"].max() > 0 else np.nan,
            "muro_put": float(abajo["g_oi_p"].idxmax()) if len(abajo) and abajo["g_oi_p"].max() > 0 else np.nan,
            "iv_atm": sig_atm, "mov_esperado": F * sig_atm * math.sqrt(T_med), "straddle": straddle,
            "f_paridad": f_par, "max_pain": max_pain, "n": len(tab), "validas": int(validas.sum()),
            "motivos": tab.loc[~validas, "motivo"].value_counts().to_dict(),
            "oi_total": float(tab["oi"].sum()), "vol_hoy": float(tab["vol_hoy"].sum()),
            "mult": float(tab["mult"].median()), "tick": a["tick"]}


def dolor_maximo(st: pd.DataFrame) -> float:
    """Max pain: el strike al que, si el futuro vence ahí, las opciones con OI pagan menos."""
    oi_c, oi_p = st["oi_c"].to_numpy(float), st["oi_p"].to_numpy(float)
    kk = st.index.to_numpy(float)
    if oi_c.sum() + oi_p.sum() <= 0:
        return np.nan
    paga = [np.sum(oi_c * np.maximum(S - kk, 0)) + np.sum(oi_p * np.maximum(kk - S, 0)) for S in kk]
    return float(kk[int(np.argmin(paga))])


def tu_metodo(f: Foto, cfg: Config) -> dict:
    """
    Tus fórmulas sobre los MISMOS precios: T = 1/365 fijo y tu charm. Con el mismo precio, σ√T
    queda igual, así que la gamma y la delta casi no cambian; la IV, la vanna y el charm sí.
    """
    t = f.tab[f.tab["valida"] & np.where(f.tab["strike"] < f.F, f.tab["tipo"] == "P", f.tab["tipo"] == "C")]
    if t.empty:
        return {}
    r = cfg.tasa
    call = (t["tipo"] == "C").to_numpy()
    K, Fo, mid = t["strike"].to_numpy(float), t["F"].to_numpy(float), t["mid"].to_numpy(float)
    T1 = np.full(len(t), 1 / 365)
    iv1 = iv_b76(mid, Fo, K, T1, r, call, cfg.iv_min, cfg.iv_max)[0]
    d1 = (np.log(Fo / K) + 0.5 * iv1 ** 2 * T1) / (iv1 * np.sqrt(T1))
    d2 = d1 - iv1 * np.sqrt(T1)
    comun = np.exp(-r * T1) * _npdf(d1)
    term = (2 * r * T1 - d2 * iv1 * np.sqrt(T1)) / (2 * T1 * iv1 * np.sqrt(T1))
    charm_tu = np.where(call, comun * term - r * np.exp(-r * T1) * _ndtr(d1),
                        comun * term + r * np.exp(-r * T1) * _ndtr(-d1))
    vanna_tu = -np.exp(-r * T1) * _npdf(d1) * d2 / iv1
    gamma_tu = np.exp(-r * T1) * _npdf(d1) / (Fo * iv1 * np.sqrt(T1))
    pos = posiciones(t["oi"].to_numpy(float), 0, call, "clasica")
    nuestro = griegas(Fo, K, t["T"].to_numpy(float), r, t["iv_mid"].to_numpy(float), call)
    ok = np.isfinite(iv1) & np.isfinite(t["iv_mid"].to_numpy(float))
    return {"iv_ratio": float(np.median(iv1[ok] / t["iv_mid"].to_numpy(float)[ok])) if ok.any() else np.nan,
            "gamma_ratio": float(np.nansum(pos * gamma_tu) / np.nansum(pos * nuestro["gamma"])),
            "vanna_ratio": float(np.nansum(pos * vanna_tu / 100) / np.nansum(pos * nuestro["vanna"])),
            "charm_signo": float(np.nansum(pos * charm_tu / HORAS_ANIO) / np.nansum(pos * nuestro["charm"])),
            "n": int(ok.sum()), "T_real_h": float(np.median(t["T"])) * HORAS_ANIO}


# =============================================================================
# 5. EL DÍA COMPLETO Y LA AUDITORÍA
# =============================================================================
@dataclass
class Resultado:
    cfg: Config
    datos: Datos
    fotos: list
    principal: Foto
    serie: pd.DataFrame
    cordura: list
    liq: dict
    tuyo: dict
    segundos: float
    verdad: dict | None = None
    medicion: dict | None = None


def horas_de_foto(datos: Datos, cfg: Config) -> list[pd.Timestamp]:
    fin = datos.defs["vence"].max() - pd.Timedelta(minutes=5)
    t = hora_ct(cfg, cfg.desde)
    out = []
    while t <= fin:
        out.append(t)
        t += pd.Timedelta(minutes=cfg.paso_min)
    if cfg.hora:
        h = hora_ct(cfg, cfg.hora)
        if h <= fin and h not in out:
            out.append(h)
    return sorted(out)


def auditar_liquidacion(datos: Datos, cfg: Config) -> dict:
    """
    Tu inversión contra la de CME: la liquidación de AYER, con el futuro liquidado de ayer y el
    tiempo desde las 15:00 CT de ayer, debe dar la volatilidad que CME publica (StatType 14).
    """
    st = datos.stats.join(datos.defs[["tipo", "strike", "vence", "sub_id"]])
    st = st[st["liq"].notna() & st["vol_cme"].notna() & st["liq_ref"].notna()]
    if st.empty or not datos.fut_liq:
        return {"n": 0}
    Fl = st["sub_id"].map(lambda s: datos.fut_liq.get(int(s), (np.nan, None))[0]).astype(float)
    t_liq = st["liq_ref"].map(lambda x: hora_ct(cfg, "15:00", pd.Timestamp(x).tz_convert("UTC").tz_localize(None)))
    T = (st["vence"] - pd.to_datetime(t_liq, utc=True)).dt.total_seconds().to_numpy() / ANIO_S
    call = (st["tipo"] == "C").to_numpy()
    iv, _ = iv_b76(st["liq"].to_numpy(float), Fl.to_numpy(), st["strike"].to_numpy(float), T, cfg.tasa, call,
                   cfg.iv_min, cfg.iv_max)
    cme = st["vol_cme"].to_numpy(float)
    escala = 100.0 if np.nanmedian(cme) > 3 else 1.0
    cme = cme / escala
    otm = np.where(call, st["strike"] >= Fl, st["strike"] <= Fl)
    ok = np.isfinite(iv) & np.isfinite(cme) & otm & (st["liq"].to_numpy(float) >= 2 * activo(cfg)["tick_bajo"])
    if not ok.any():
        return {"n": 0}
    dif = (iv[ok] - cme[ok]) * 100
    return {"n": int(ok.sum()), "mediana_abs": float(np.median(np.abs(dif))), "sesgo": float(np.median(dif)),
            "p90": float(np.percentile(np.abs(dif), 90)), "escala": escala}


def verificar_griegas(f: Foto, cfg: Config) -> float:
    """Error relativo máximo de las griegas analíticas contra diferencias finitas."""
    t = f.tab[f.tab["valida"]].head(200)
    if t.empty:
        return np.nan
    F, K, T, s = (t[c].to_numpy(float) for c in ("F", "strike", "T", "iv"))
    call, r = (t["tipo"] == "C").to_numpy(), cfg.tasa
    g = griegas(F, K, T, r, s, call)
    h, hs, ht = 0.01, 1e-5, T * 1e-4
    num = {"delta": (precio_b76(F + h, K, T, r, s, call) - precio_b76(F - h, K, T, r, s, call)) / (2 * h),
           "gamma": (precio_b76(F + h, K, T, r, s, call) - 2 * precio_b76(F, K, T, r, s, call)
                     + precio_b76(F - h, K, T, r, s, call)) / h ** 2,
           "vanna": (griegas(F, K, T, r, s + hs, call)["delta"] - griegas(F, K, T, r, s - hs, call)["delta"]) / (2 * hs) / 100,
           "charm": -(griegas(F, K, T + ht, r, s, call)["delta"] - griegas(F, K, T - ht, r, s, call)["delta"])
           / (2 * ht) / HORAS_ANIO}
    peor = 0.0
    for k, v in num.items():
        escala = np.maximum(np.abs(g[k]), np.nanmax(np.abs(g[k])) * 1e-3)
        peor = max(peor, float(np.nanmax(np.abs(g[k] - v) / escala)))
    return peor


def arbitraje(f: Foto) -> int:
    """Calls: un strike más alto no puede tener bid mayor que el ask del strike más bajo."""
    n = 0
    for tipo, signo in (("C", 1), ("P", -1)):
        d = f.tab[(f.tab["tipo"] == tipo) & f.tab["bid"].notna() & f.tab["ask"].notna()].sort_values("strike")
        b, a = d["bid"].to_numpy(), d["ask"].to_numpy()
        if signo > 0:
            n += int(np.sum(b[1:] > a[:-1] + 1e-9))
        else:
            n += int(np.sum(b[:-1] > a[1:] + 1e-9))
    return n


def chequeos(res_f: Foto, datos: Datos, cfg: Config, liq: dict, err_g: float, n_arb: int) -> list[tuple[bool, str]]:
    t = res_f.tot
    out = []
    out.append((t["usadas_ok"] >= 0.8 * max(1, t["usadas"]),
                f"IV confiable en {t['usadas_ok']} de {t['usadas']} opciones fuera del dinero a ±1σ (las que definen el "
                f"smile) · en toda la cadena {t['validas']} de {t['n']}"
                + ("" if not t["motivos"] else "; descartadas: " + ", ".join(f"{k} {v}" for k, v in t["motivos"].items()))))
    if np.isfinite(t["f_paridad"]):
        d = t["f_paridad"] - t["F"]
        out.append((abs(d) <= 2 * t["tick"], f"paridad put-call: forward implícito {t['f_paridad']:,.2f} vs futuro "
                                              f"{t['F']:,.2f} ({d:+.2f} pts)"))
    if liq.get("n"):
        out.append((liq["mediana_abs"] <= 1.0, f"IV de la liquidación de ayer vs la de CME: diferencia mediana "
                                               f"{liq['mediana_abs']:.2f} pts de vol ({liq['n']} opciones)"))
    out.append((err_g < 1e-3, f"griegas analíticas = diferencias finitas (error relativo máximo {err_g:.1e})"))
    out.append((n_arb == 0, f"cotizaciones con arbitraje de spread vertical: {n_arb}"))
    con_oi = int((datos.stats["oi"].fillna(0) > 0).sum())
    out.append((con_oi > 0, f"opciones 0DTE con open interest publicado: {con_oi} de {len(datos.defs)}"
                + (f" (OI del {pd.Timestamp(datos.stats['oi_ref'].dropna().iloc[0]).date()})"
                   if datos.stats["oi_ref"].notna().any() else "")))
    pc = t["por_convencion"]
    flips = [v["flip"] for v in pc.values() if np.isfinite(v["flip"])]
    rango = max(flips) - min(flips) if len(flips) >= 2 else 0.0
    if np.isfinite(t.get("ajuste_rmse", np.nan)):
        out.append((t["ajuste_rmse"] <= 1.5, f"smile ajustado (ponderado por vega): error RMSE {t['ajuste_rmse']:.2f} "
                                             "pts de vol contra las IV observadas"))
    out.append((rango <= t["mov_esperado"] if np.isfinite(t["mov_esperado"]) else True,
                "flip según la convención: " + " · ".join(f"{k} {_fmt_p(v['flip'])}" for k, v in pc.items())))
    return out


def _fmt_p(x) -> str:
    return f"{x:,.2f}" if x is not None and np.isfinite(x) else "—"


def analizar(datos: Datos, cfg: Config, verdad: dict | None = None, verbose: bool = True) -> Resultado:
    validar(cfg)
    t0 = time.perf_counter()
    rej_cot = Rejilla(datos.cot, "iid", datos.defs.index, cfg.antiguedad_max_min)
    rej_fut = Rejilla(datos.fut, "sub_id", sorted(datos.defs["sub_id"].unique()), cfg.antiguedad_max_min)
    fotos = []
    for t in horas_de_foto(datos, cfg):
        f = foto(datos, cfg, t, rej_cot, rej_fut)
        if f is not None:
            fotos.append(f)
    if not fotos:
        sys.exit("❌ No hubo ningún momento con futuro y opciones cotizando.")
    if cfg.hora:
        h = hora_ct(cfg, cfg.hora)
        principal = min(fotos, key=lambda f: abs((f.t - h).total_seconds()))
    else:
        con_hora = [f for f in fotos if f.tot["T_h"] >= 1.0]
        principal = con_hora[-1] if con_hora else fotos[-1]
    serie = pd.DataFrame([{"t": f.t, "F": f.F, "gamma": f.tot["gamma"], "gex_usd": f.tot["gex_usd"],
                           "delta": f.tot["delta"], "flip": f.tot["flip"], "cierre": f.tot["cierre"],
                           "charm_30m": f.tot["charm_30m"],
                           "vanna": f.tot["vanna"], "iv_atm": f.tot["iv_atm"], "mov": f.tot["mov_esperado"],
                           "muro_call": f.tot["muro_call"], "muro_put": f.tot["muro_put"],
                           "validas": f.tot["validas"], "n": f.tot["n"]} for f in fotos]).set_index("t")
    liq = auditar_liquidacion(datos, cfg)
    err_g = verificar_griegas(principal, cfg)
    res = Resultado(cfg=cfg, datos=datos, fotos=fotos, principal=principal, serie=serie,
                    cordura=chequeos(principal, datos, cfg, liq, err_g, arbitraje(principal)), liq=liq,
                    tuyo=tu_metodo(principal, cfg), segundos=time.perf_counter() - t0, verdad=verdad)
    if verdad is not None:
        res.medicion = medir_contra_verdad(res)
    return res


# =============================================================================
# 6. SIMULADOR — una cadena 0DTE con verdad conocida, escrita como DBN de Databento
# =============================================================================
def sonrisa(K, F, T, atm: float = 0.14):
    """
    Smile verdadero: σ = atm·(1 − 0.12·tanh(x/1.5) + 0.02·|x|^1.5), x = ln(K/F)/(atm·√T). A
    propósito NO es la parábola con la que el módulo ajusta: así se mide el error de forma.
    """
    x = np.log(np.asarray(K, float) / F) / (atm * np.sqrt(np.maximum(T, 1e-9)))
    return np.clip(atm * (1 - 0.12 * np.tanh(x / 1.5) + 0.02 * np.abs(x) ** 1.5), 0.6 * atm, 3.0 * atm)


def _dbn(schema, recs, stype):
    import databento_dbn as dd
    meta = dd.Metadata(dataset="GLBX.MDP3", start=1, stype_in=stype, stype_out=dd.SType.INSTRUMENT_ID, schema=schema,
                       symbols=["SIM"], partial=[], not_found=[], mappings=[], end=2 ** 63 - 2)
    return db.DBNStore.from_bytes(bytes(meta.encode()) + b"".join(bytes(r) for r in recs))


def _fijo(x: float) -> int:
    return int(round(x * 1e9))


def simular(cfg: Config, semilla: int | None = None) -> tuple[Datos, dict]:
    """
    Un día de vencimiento con todo CONOCIDO:
      · el futuro camina (σ = sim_vol) desde la liquidación de ayer hasta el vencimiento;
      · las opciones cotizan Black-76 con un smile verdadero (sesgo de puts), con bid/ask en los
        ticks de CME (0.25; 0.05 abajo de 5 puntos) y sin bid en las muy lejanas;
      · OI de ayer: los clientes van largos en puts abajo y cortos en calls arriba (con 10 % de
        strikes al revés y una parte del OI entre clientes, que a los dealers no les toca);
      · hoy los clientes compran y venden 0DTE cerca del dinero: el agresor es el cliente;
      · CME publica la liquidación de ayer con su volatilidad y su delta.
    Todo se escribe como registros de Databento (definiciones, bbo-1m, estadísticas y trades) y
    entra por la MISMA normalización que los datos reales.
    """
    import databento_dbn as dd
    rng = np.random.default_rng(cfg.sim_semilla if semilla is None else semilla)
    a = activo(cfg)
    r, paso, tick, tb = cfg.tasa, a["paso"], a["tick"], a["tick_bajo"]
    D = pd.Timestamp(cfg.fecha)
    vence = hora_ct(cfg, "15:00")
    t_liq = hora_ct(cfg, "15:00", D - pd.Timedelta(days=1))
    mins = pd.date_range(t_liq, vence, freq="1min").as_unit("ns")
    dt = 60 / ANIO_S
    z = rng.normal(size=len(mins) - 1)
    F = a["ref"] * np.exp(np.r_[0, np.cumsum(cfg.sim_vol * math.sqrt(dt) * z - 0.5 * cfg.sim_vol ** 2 * dt)])
    F_s = pd.Series(F, index=mins)
    F0 = F[0]
    ks = np.arange(math.floor(F0 * 0.92 / paso) * paso, math.ceil(F0 * 1.08 / paso) * paso + paso, paso)
    sub_id, t_def = 9001, int(D.tz_localize("UTC").value) + NS
    defs, ids, tipo_de, k_de = [], [], {}, {}
    for j, k in enumerate(ks):
        for tipo, base in (("C", 100_000), ("P", 200_000)):
            iid = base + j
            ids.append(iid)
            tipo_de[iid], k_de[iid] = tipo, k
            defs.append(dd.InstrumentDefMsg(
                publisher_id=1, instrument_id=iid, ts_event=t_def, ts_recv=t_def, min_price_increment=_fijo(tick),
                display_factor=10 ** 9, raw_symbol=f"EW4Z6 {tipo}{k:.0f}", asset="EW4", security_type="OOF",
                instrument_class=dd.InstrumentClass.CALL if tipo == "C" else dd.InstrumentClass.PUT,
                security_update_action=dd.SecurityUpdateAction.ADD, expiration=int(vence.value),
                strike_price=_fijo(k), underlying=f"{cfg.activo}Z6", underlying_id=sub_id,
                unit_of_measure_qty=_fijo(a["mult"]), currency="USD"))
    for j, k in enumerate(ks[::10]):                      # opciones que NO vencen hoy: deben quedar fuera
        defs.append(dd.InstrumentDefMsg(
            publisher_id=1, instrument_id=300_000 + j, ts_event=t_def, ts_recv=t_def, min_price_increment=_fijo(tick),
            display_factor=10 ** 9, raw_symbol=f"E1AZ6 C{k:.0f}", asset="E1A", security_type="OOF",
            instrument_class=dd.InstrumentClass.CALL, security_update_action=dd.SecurityUpdateAction.ADD,
            expiration=int((vence + pd.Timedelta(days=3)).value), strike_price=_fijo(k), underlying=f"{cfg.activo}Z6",
            underlying_id=sub_id, unit_of_measure_qty=_fijo(a["mult"]), currency="USD"))
    ids = np.array(ids)
    call = np.array([tipo_de[i] == "C" for i in ids])
    K = np.array([k_de[i] for i in ids], float)

    def cot(t_idx):
        """Precio verdadero y bid/ask de todas las opciones en los minutos dados."""
        Ft = F[t_idx][:, None]
        T = ((vence - mins[t_idx]).total_seconds().to_numpy() / ANIO_S)[:, None]
        s = sonrisa(K[None, :], Ft, T)
        mid = precio_b76(Ft, K[None, :], T, r, s, call[None, :])
        tk = np.where(mid < 5, tb, tick)
        hs = np.maximum(tk, 0.02 * mid)
        bid = np.floor((mid - hs) / tk + 1e-9) * tk
        ask = np.maximum(np.ceil((mid + hs) / tk - 1e-9) * tk, tb)
        return mid, np.where(bid >= tb, bid, np.nan), ask, s

    # --- cotizaciones bbo-1m desde las 08:00 CT
    i0 = int(mins.searchsorted(hora_ct(cfg, "08:00")))
    idx = np.arange(i0, len(mins) - 1)
    mid, bid, ask, sig = cot(idx)
    recs = []
    for fila, i in enumerate(idx):
        tr = int(mins[i].value)
        for j, iid in enumerate(ids):
            b = bid[fila, j]
            recs.append(dd.BBOMsg(rtype=dd.RType.BBO_1M, publisher_id=1, instrument_id=int(iid), ts_event=tr - 30 * NS,
                                  price=_fijo(mid[fila, j]), size=1, side=dd.Side.NONE, ts_recv=tr, flags=0,
                                  levels=dd.BidAskPair(bid_px=_fijo(b) if np.isfinite(b) else 2 ** 63 - 1,
                                                       ask_px=_fijo(ask[fila, j]), bid_sz=10 if np.isfinite(b) else 0,
                                                       ask_sz=10, bid_ct=1, ask_ct=1)))
    rec_f = []
    for i in range(len(mins) - 1):
        bf = math.floor(F[i] / tick) * tick
        rec_f.append(dd.BBOMsg(rtype=dd.RType.BBO_1M, publisher_id=1, instrument_id=sub_id, ts_event=int(mins[i].value) - NS,
                               price=_fijo(bf), size=1, side=dd.Side.NONE, ts_recv=int(mins[i].value), flags=0,
                               levels=dd.BidAskPair(bid_px=_fijo(bf), ask_px=_fijo(bf + tick), bid_sz=50, ask_sz=50)))
    # --- OI de ayer: posiciones de los clientes (los dealers tienen lo contrario)
    cliente = np.zeros(len(ids))
    redondo = (K % 50 == 0).astype(float)
    put_mask, call_mask = ~call & (K < F0), call & (K > F0)
    cliente[put_mask] = (300 * np.exp(-((K[put_mask] - (F0 - 0.022 * F0)) / (0.02 * F0)) ** 2)
                         + 700 * redondo[put_mask] * np.exp(-((K[put_mask] - F0) / (0.03 * F0)) ** 2))
    cliente[call_mask] = -(250 * np.exp(-((K[call_mask] - (F0 + 0.018 * F0)) / (0.018 * F0)) ** 2)
                           + 600 * redondo[call_mask] * np.exp(-((K[call_mask] - F0) / (0.025 * F0)) ** 2))
    cliente = np.round(cliente * rng.uniform(0.7, 1.3, len(ids)))
    al_reves = rng.random(len(ids)) < 0.10
    cliente[al_reves] *= -1
    oi = np.abs(cliente) + np.round(np.abs(cliente) * rng.uniform(0, 0.3, len(ids)))
    dealer_base = -cliente
    # --- estadísticas: OI publicado hoy 06:00 CT; liquidación de ayer con vol y delta de CME
    t_oi, ref = int(hora_ct(cfg, "06:00").value), int((D - pd.Timedelta(days=1)).tz_localize("UTC").value)
    t_pub = int((t_liq + pd.Timedelta(minutes=30)).value)
    T_liq = (vence - t_liq).total_seconds() / ANIO_S
    s_liq = sonrisa(K, F0, T_liq)
    p_liq = precio_b76(F0, K, T_liq, r, s_liq, call)
    tk = np.where(p_liq < 5, tb, tick)
    p_liq = np.maximum(np.round(p_liq / tk) * tk, tb)
    g_liq = griegas(F0, K, T_liq, r, s_liq, call)
    UND = 2 ** 63 - 1
    rec_s = [dd.StatMsg(publisher_id=1, instrument_id=sub_id, ts_event=t_pub, ts_recv=t_pub, ts_ref=ref,
                        price=_fijo(round(F0 / tick) * tick), quantity=Q_INDEF, stat_type=dd.StatType.SETTLEMENT_PRICE)]
    for j, iid in enumerate(ids):
        rec_s += [dd.StatMsg(publisher_id=1, instrument_id=int(iid), ts_event=t_pub, ts_recv=t_pub, ts_ref=ref,
                             price=_fijo(p_liq[j]), quantity=Q_INDEF, stat_type=dd.StatType.SETTLEMENT_PRICE),
                  dd.StatMsg(publisher_id=1, instrument_id=int(iid), ts_event=t_pub, ts_recv=t_pub, ts_ref=ref,
                             price=_fijo(100 * s_liq[j]), quantity=Q_INDEF, stat_type=dd.StatType.VOLATILITY),
                  dd.StatMsg(publisher_id=1, instrument_id=int(iid), ts_event=t_pub, ts_recv=t_pub, ts_ref=ref,
                             price=_fijo(g_liq["delta"][j]), quantity=Q_INDEF, stat_type=dd.StatType.DELTA)]
        if oi[j] > 0:
            rec_s.append(dd.StatMsg(publisher_id=1, instrument_id=int(iid), ts_event=t_oi, ts_recv=t_oi, ts_ref=ref,
                                    price=UND, quantity=int(oi[j]), stat_type=dd.StatType.OPEN_INTEREST))
    # --- operaciones de hoy: el agresor es el cliente; 8 % son cruces sin lado
    n_ops = int(rng.poisson(2500))
    t_ops = np.sort(rng.uniform(hora_ct(cfg, "08:30").value, hora_ct(cfg, "14:55").value, n_ops)).astype(np.int64)
    rec_t, flujo = [], []
    for t_ns in t_ops:
        i = int(mins.searchsorted(pd.Timestamp(t_ns, tz="UTC"), side="right")) - 1
        fila = i - i0
        k = round(F[i] * (1 + rng.normal(0, 0.004)) / paso) * paso
        es_call = (k > F[i]) if rng.random() < 0.8 else (k <= F[i])
        hit = np.flatnonzero((K == k) & (call == es_call))
        if not len(hit) or fila < 0:
            continue
        j = int(hit[0])
        compra = rng.random() < 0.62
        cruce = rng.random() < 0.08
        p = ask[fila, j] if compra else bid[fila, j]
        if not np.isfinite(p):
            continue
        q = int(rng.geometric(0.25))
        lado = dd.Side.NONE if cruce else (dd.Side.BID if compra else dd.Side.ASK)
        rec_t.append(dd.TradeMsg(publisher_id=1, instrument_id=int(ids[j]), ts_event=int(t_ns) - 1000, price=_fijo(p), size=q,
                                 action=dd.Action.TRADE, side=lado, depth=0, ts_recv=int(t_ns)))
        if not cruce:
            flujo.append((int(t_ns), int(ids[j]), -q if compra else q))
    tablas = {"def": _tabla(_dbn(dd.Schema.DEFINITION, defs, dd.SType.PARENT)),
              "fut": _tabla(_dbn(dd.Schema.BBO_1M, rec_f, dd.SType.INSTRUMENT_ID)),
              "cot": _tabla(_dbn(dd.Schema.BBO_1M, recs, dd.SType.INSTRUMENT_ID)),
              "st": _tabla(_dbn(dd.Schema.STATISTICS, rec_s, dd.SType.INSTRUMENT_ID)),
              "ops": _tabla(_dbn(dd.Schema.TRADES, rec_t, dd.SType.INSTRUMENT_ID))}
    datos = armar_datos(norm_definiciones(tablas["def"], cfg), tablas["fut"], tablas["cot"], tablas["st"], tablas["ops"],
                        cfg, {"padres": ["SIM"], "productos_con_0dte": ["EW4"], "definiciones": len(defs), "costo": 0.0})
    verdad = {"F": F_s, "vence": vence, "ids": ids, "call": call, "K": K, "dealer_base": dealer_base, "oi": oi,
              "flujo": pd.DataFrame(flujo, columns=["t", "iid", "dealer"]), "al_reves": al_reves,
              "liq_vol": s_liq, "tablas": tablas}
    return datos, verdad


def verdad_foto(v: dict, cfg: Config, t: pd.Timestamp) -> dict:
    """Lo que el módulo DEBERÍA ver en t, con el futuro, el smile y las posiciones verdaderos."""
    Fv = float(v["F"][v["F"].index <= t].iloc[-1])
    T = np.full(len(v["K"]), (v["vence"] - t).total_seconds() / ANIO_S)
    s = sonrisa(v["K"], Fv, T)
    fl = v["flujo"][v["flujo"]["t"] <= t.value].groupby("iid")["dealer"].sum()
    pos = v["dealer_base"] + pd.Series(v["ids"]).map(fl).fillna(0).to_numpy()
    g = griegas(Fv, v["K"], T, cfg.tasa, s, v["call"])
    perf = perfil_dealers(Fv, v["K"], T, cfg.tasa, s, v["call"], pos, cfg)
    return {"F": Fv, "sig": dict(zip(v["K"], s)), "gamma": float(np.sum(pos * g["gamma"])),
            "delta": float(np.sum(pos * g["delta"])), "vanna": float(np.sum(pos * g["vanna"])),
            "cierre": float(np.sum(pos * (delta_vencimiento(Fv, v["K"], v["call"]) - g["delta"]))),
            "flip": _flip(perf["F"].to_numpy(), perf["gamma"].to_numpy(), Fv), "pos": dict(zip(v["ids"], pos))}


def medir_contra_verdad(res: Resultado) -> dict:
    v, cfg = res.verdad, res.cfg
    filas = []
    for f in res.fotos:
        w = verdad_foto(v, cfg, f.t)
        t = f.tab
        mov_v = w["F"] * 0.14 * math.sqrt((v["vence"] - f.t).total_seconds() / ANIO_S)
        cerca = np.abs(t["strike"] - f.F) <= mov_v
        err_iv = (t.loc[cerca, "iv"] - t.loc[cerca, "strike"].map(w["sig"])).abs() * 100
        g_est = {cv: f.tot["por_convencion"][cv]["gamma"] for cv in CONVENCIONES}
        flips = {cv: f.tot["por_convencion"][cv]["flip"] for cv in CONVENCIONES}
        filas.append({"t": f.t, "F_err": f.F - w["F"], "iv_err": float(err_iv.median()), "iv_err90": float(err_iv.quantile(0.9)),
                      "gamma_v": w["gamma"], **{f"gamma_{cv}": g_est[cv] for cv in CONVENCIONES},
                      "flip_v": w["flip"], **{f"flip_{cv}": flips[cv] for cv in CONVENCIONES},
                      "cierre_v": w["cierre"], "cierre": f.tot["cierre"], "vanna_v": w["vanna"], "vanna": f.tot["vanna"],
                      "mov": f.tot["mov_esperado"]})
    D = pd.DataFrame(filas).set_index("t")
    out = {"serie": D, "iv_err": float(D["iv_err"].median()), "iv_err90": float(D["iv_err90"].median()),
           "F_err": float(D["F_err"].abs().max())}
    for cv in CONVENCIONES:
        e = (D[f"gamma_{cv}"] - D["gamma_v"]).abs() / D["gamma_v"].abs()
        df_ = (D[f"flip_{cv}"] - D["flip_v"]).abs()
        out[f"gamma_err_{cv}"] = float(e.median())
        out[f"flip_err_{cv}"] = float(df_.median()) if df_.notna().any() else np.nan
        out[f"signo_{cv}"] = float(np.mean(np.sign(D[f"gamma_{cv}"]) == np.sign(D["gamma_v"])))
    ok = D["cierre_v"].abs() > 0
    out["cierre_err"] = float(((D["cierre"] - D["cierre_v"]).abs() / D["cierre_v"].abs())[ok].median())
    return out


# =============================================================================
# 7. AUDITORÍA TEXTUAL
# =============================================================================
def _hora(t, cfg: Config) -> str:
    t = pd.Timestamp(t)
    return f"{t.tz_convert(cfg.tz_mercado):%H:%M} CT / {t.tz_convert(cfg.tz_local):%H:%M} CDMX"


def _c(x: float) -> str:
    return f"{x:+,.0f}" if np.isfinite(x) else "—"


def _dealers(n: float) -> str:
    if not np.isfinite(n) or abs(n) < 0.5:
        return "no tienen que hacer nada"
    return f"{'COMPRAN' if n > 0 else 'VENDEN'} {abs(n):,.0f} contratos"


def flujo_en(f: Foto, Fx: float) -> float:
    p = f.perfil
    return float(np.interp(Fx, p["F"].to_numpy(), p["flujo"].to_numpy()))


def reporte_datos(res: Resultado) -> None:
    cfg, d = res.cfg, res.datos
    a = activo(cfg)
    _titulo("1 · INGESTA CRUZADA (futuro + definiciones + estadísticas + cotizaciones + operaciones)")
    df = d.defs
    print(f"  {cfg.activo} ({a['nombre']}) · vencimiento {cfg.fecha} a las "
          f"{df['vence'].max().tz_convert(cfg.tz_mercado):%H:%M} CT · familias con 0DTE: "
          f"{', '.join(d.meta.get('productos_con_0dte', []))}")
    print(f"  {len(df)} opciones 0DTE: {int((df['tipo'] == 'C').sum())} calls y {int((df['tipo'] == 'P').sum())} puts, "
          f"strikes {df['strike'].min():,.0f} a {df['strike'].max():,.0f} · subyacente "
          f"{', '.join(sorted(df['subyacente'].unique()))} (el contrato EXACTO de las opciones)")
    oi = d.stats["oi"].fillna(0)
    ref = d.stats["oi_ref"].dropna()
    print(f"  Open interest: {oi.sum():,.0f} contratos en {int((oi > 0).sum())} opciones"
          + (f" (del {pd.Timestamp(ref.iloc[0]).date()})" if len(ref) else ""))
    vol = d.ops["tam"].sum() if len(d.ops) else 0
    sin = d.ops.loc[d.ops["lado"] == 0, "tam"].sum() if len(d.ops) else 0
    print(f"  Operaciones de hoy: {len(d.ops):,} ({vol:,.0f} contratos; {sin:,.0f} sin lado agresor) · "
          f"cotizaciones bbo-1m: {len(d.cot):,} · futuro: {len(d.fut):,}")
    print(f"  {len(res.fotos)} fotos de {res.fotos[0].t.tz_convert(cfg.tz_mercado):%H:%M} a "
          f"{res.fotos[-1].t.tz_convert(cfg.tz_mercado):%H:%M} CT cada {cfg.paso_min} min · {res.segundos:.1f} s")


def reporte_foto(res: Resultado) -> None:
    cfg, f = res.cfg, res.principal
    t = f.tot
    _titulo(f"2 · LA FOTO DE LAS {_hora(f.t, cfg)}")
    h = int(t["T_h"])
    print(f"  Futuro {f.F:,.2f} · faltan {h} h {int((t['T_h'] - h) * 60)} min para el vencimiento · IV ATM "
          f"{t['iv_atm']:.1%}")
    print(f"  Movimiento esperado hasta el vencimiento (1σ): ±{t['mov_esperado']:,.1f} pts → "
          f"{f.F - t['mov_esperado']:,.1f} a {f.F + t['mov_esperado']:,.1f} · straddle ATM {t['straddle']:,.2f}")
    print(f"  Forward por paridad put-call: {_fmt_p(t['f_paridad'])} · max pain {_fmt_p(t['max_pain'])} "
          "(referencia de OI, no una predicción)")


def reporte_cobertura(res: Resultado) -> None:
    cfg, f = res.cfg, res.principal
    t = f.tot
    _titulo(f"3 · GRIEGAS Y COBERTURA DE LOS DEALERS (convención: {t['conv']})")
    print(f"  Gamma neta: {_c(t['gamma'])} contratos por punto · GEX {t['gex_usd'] / 1e6:+,.1f} M USD por 1 % → "
          f"gamma {t['regimen']}")
    if np.isfinite(t["flip"]):
        print(f"  Flip (gamma cero): {t['flip']:,.2f} ({t['flip'] - f.F:+,.1f} pts del futuro)")
    else:
        print(f"  Flip: no hay cambio de signo en ±{cfg.rango_pct:.0%}")
    print(f"  Muro de calls {_fmt_p(t['muro_call'])} · muro de puts {_fmt_p(t['muro_put'])} (máximo gamma × OI)")
    print(f"  Delta neta de las opciones de los dealers: {_c(t['delta'])} contratos (su cobertura: {_c(-t['delta'])} futuros)")
    print()
    print("  Si el futuro se va a…              los dealers, para seguir cubiertos,")
    m = t["mov_esperado"]
    for k in (-2, -1, -0.5, 0.5, 1, 2):
        Fx = f.F + k * m
        print(f"      {Fx:>10,.2f} ({k * m:+7.1f} pts, {k:+.1f}σ)   {_dealers(flujo_en(f, Fx))}")
    print()
    print(f"  Charm, a precio fijo: en los próximos 30 min {_dealers(-t['charm_30m'])}; de aquí al vencimiento "
          f"{_dealers(-t['cierre'])}")
    print(f"  Vanna: si la IV baja 1 punto, {_dealers(t['vanna'])}")
    print("  Con otra convención de posiciones: " + " · ".join(
        f"{k}: gamma {_c(v['gamma'])}, flip {_fmt_p(v['flip'])}" for k, v in t["por_convencion"].items()))


def reporte_dia(res: Resultado) -> None:
    cfg, S = res.cfg, res.serie
    _titulo("4 · EL DÍA, FOTO POR FOTO")
    print(f"      {'hora CT':>8s}{'futuro':>11s}{'gamma':>9s}{'flip':>11s}{'régimen':>10s}{'charm al cierre':>17s}"
          f"{'IV ATM':>8s}{'IV ok':>9s}")
    for t, r in S.iterrows():
        print(f"      {t.tz_convert(cfg.tz_mercado):%H:%M}  {r['F']:>10,.2f}{r['gamma']:>9,.0f}{_fmt_p(r['flip']):>11s}"
              f"{'positiva' if r['gamma'] > 0 else 'negativa':>10s}{r['cierre']:>17,.0f}{r['iv_atm']:>8.1%}"
              f"{int(r['validas']):>5d}/{int(r['n'])}")


def lectura(res: Resultado) -> list[str]:
    """La auditoría en palabras: qué dice la foto, con números y sin promesas."""
    cfg, f = res.cfg, res.principal
    t = f.tot
    out = []
    pos = t["gamma"] > 0
    paso10 = flujo_en(f, f.F + 10) if np.isfinite(t["gamma"]) else np.nan
    out.append(f"A las {_hora(f.t, cfg)} el {cfg.activo} está en {f.F:,.2f} con gamma de dealers "
               f"{'POSITIVA' if pos else 'NEGATIVA'} ({t['gamma']:+,.0f} contratos por punto): si sube 10 puntos los "
               f"dealers {_dealers(paso10).lower()}. "
               + ("Su cobertura va CONTRA el movimiento: tiende a frenarlo." if pos else
                  "Su cobertura va CON el movimiento: tiende a acelerarlo."))
    if np.isfinite(t["flip"]):
        lado = "abajo" if t["flip"] < f.F else "arriba"
        out.append(f"El flip está {abs(t['flip'] - f.F):,.1f} puntos {lado} ({t['flip']:,.2f}): si el precio lo cruza, la "
                   "cobertura de los dealers cambia de frenar a acelerar (o al revés).")
    if np.isfinite(t["muro_call"]) or np.isfinite(t["muro_put"]):
        out.append(f"Muro de calls {_fmt_p(t['muro_call'])} y de puts {_fmt_p(t['muro_put'])}: donde más gamma × OI hay. "
                   "En 0DTE suelen atraer o frenar el precio al acercarse el vencimiento; no es garantía.")
    out.append(f"Por puro paso del tiempo (charm), si el precio no se mueve, de aquí al vencimiento los dealers "
               f"{_dealers(-t['cierre']).lower()}.")
    out.append(f"El mercado de opciones espera ±{t['mov_esperado']:,.1f} puntos (1σ) hasta el vencimiento.")
    fl = [v["flip"] for v in t["por_convencion"].values() if np.isfinite(v["flip"])]
    if len(fl) >= 2 and max(fl) - min(fl) > 0.5 * t["mov_esperado"]:
        out.append("OJO: el flip cambia mucho según quién se supone que está largo o corto; es un supuesto, no un dato.")
    return out


def reporte_auditoria(res: Resultado) -> None:
    _titulo("5 · AUDITORÍA TEXTUAL")
    import textwrap
    for p in lectura(res):
        print("\n".join(textwrap.wrap(p, 94, initial_indent="  • ", subsequent_indent="    ")))
    print()
    for ok, txt in res.cordura:
        print(f"  {'✓' if ok else '⚠'} {txt}")
    tu = res.tuyo
    if tu:
        print()
        print(f"  Tus fórmulas sobre estos mismos precios (T = 1/365 en vez de {tu['T_real_h']:.1f} h, y tu charm):")
        print(f"      IV × {tu['iv_ratio']:.2f} · gamma × {tu['gamma_ratio']:.2f} · vanna × {tu['vanna_ratio']:.2f} · "
              f"charm × {tu['charm_signo']:+.3f}" + ("  (signo contrario)" if tu["charm_signo"] < 0 else ""))
        print("      Con el mismo precio, σ√T no cambia: la gamma casi igual; la IV, la vanna y el charm no.")


def reporte_verdad(res: Resultado) -> None:
    v = res.medicion
    if not v:
        return
    _titulo("6 · CONTRA LA VERDAD (sólo en simulación)")
    print(f"  IV por strike (a ±1σ del futuro): error mediano {v['iv_err']:.2f} pts de vol · p90 {v['iv_err90']:.2f}")
    print(f"  Futuro: error máximo {v['F_err']:.3f} pts (cotización contra precio verdadero)")
    print(f"  {'convención':<18s}{'gamma: error':>14s}{'signo correcto':>16s}{'flip: error':>13s}")
    for cv in CONVENCIONES:
        print(f"  {cv:<18s}{v[f'gamma_err_{cv}']:>14.1%}{v[f'signo_{cv}']:>16.0%}{v[f'flip_err_{cv}']:>11.1f} pts")
    print(f"  Charm al cierre (convención {res.cfg.convencion}): error mediano {v['cierre_err']:.1%}")


# =============================================================================
# 8. TABLEROS
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


def _zoom(f: Foto) -> tuple[float, float]:
    m = f.tot["mov_esperado"] if np.isfinite(f.tot["mov_esperado"]) else 0.01 * f.F
    w = max(2.5 * m, 0.006 * f.F)
    return f.F - w, f.F + w


def tablero_0dte(res: Resultado, plt, ruta: Path):
    import matplotlib.dates as mdates
    cfg, f = res.cfg, res.principal
    t = f.tot
    fig = plt.figure(figsize=(18, 13.5))
    fig.patch.set_facecolor(C["fondo"])
    gs = fig.add_gridspec(3, 3, height_ratios=[1.15, 1.0, 1.05], width_ratios=[1.0, 1.1, 1.1], hspace=0.42,
                          wspace=0.28, bottom=0.06, top=0.92)
    a1 = fig.add_subplot(gs[0:2, 0])
    a2, a3 = fig.add_subplot(gs[0, 1:]), fig.add_subplot(gs[1, 1:])
    a4 = fig.add_subplot(gs[2, :])
    fig.suptitle(f"0DTE · {cfg.activo} · {cfg.fecha} · {_hora(f.t, cfg)} · futuro {f.F:,.2f} · gamma {t['regimen'].lower()} "
                 f"({t['gamma']:+,.0f} c/pt) · flip {_fmt_p(t['flip'])} · ±{t['mov_esperado']:,.0f} pts esperados",
                 x=0.01, ha="left", color=C["tinta"], fontsize=12.5)
    lo, hi = _zoom(f)
    S = f.strikes[(f.strikes.index >= lo) & (f.strikes.index <= hi)]
    paso = float(np.median(np.diff(S.index))) if len(S) > 1 else 1.0
    _estilo(a1, "Gamma de los dealers por strike\n(contratos por punto) · calls y puts")
    a1.barh(S.index, S["gamma_c"], height=paso * 0.8, color=C["s1"], label="calls")
    a1.barh(S.index, S["gamma_p"], height=paso * 0.8, color=C["s8"], label="puts")
    a1.axvline(0, color=C["eje"], linewidth=0.9)
    a1.axhline(f.F, color=C["tinta"], linewidth=1.4, label=f"futuro {f.F:,.2f}")
    if np.isfinite(t["flip"]):
        a1.axhline(t["flip"], color=C["s7"], linewidth=1.3, linestyle=(0, (5, 3)), label=f"flip {t['flip']:,.0f}")
    for k, col, nm in (("muro_call", C["s1"], "muro calls"), ("muro_put", C["s8"], "muro puts")):
        if np.isfinite(t[k]):
            a1.axhline(t[k], color=col, linewidth=1.0, linestyle=":", label=f"{nm} {t[k]:,.0f}")
    a1.set_ylim(lo, hi)
    a1.set_ylabel("strike", color=C["tinta2"], fontsize=9)
    _leyenda(a1, loc="lower right", frameon=True, facecolor=C["fondo"], edgecolor="none", framealpha=0.9)

    _estilo(a2, "Si el futuro va a… los dealers COMPRAN (+) o VENDEN (−) estos contratos para seguir cubiertos")
    p = f.perfil[(f.perfil["F"] >= lo) & (f.perfil["F"] <= hi)]
    a2.fill_between(p["F"], p["flujo"], 0, where=p["flujo"] >= 0, color=C["s3"], alpha=0.35, linewidth=0)
    a2.fill_between(p["F"], p["flujo"], 0, where=p["flujo"] < 0, color=C["s8"], alpha=0.3, linewidth=0)
    a2.plot(p["F"], p["flujo"], color=C["tinta"], linewidth=1.4)
    a2.axhline(0, color=C["eje"], linewidth=0.9)
    m = t["mov_esperado"]
    if np.isfinite(m):
        a2.axvspan(f.F - m, f.F + m, color=C["neutro"], alpha=0.35, linewidth=0, zorder=0)
    a2.axvline(f.F, color=C["tinta"], linewidth=1.2)
    if np.isfinite(t["flip"]):
        a2.axvline(t["flip"], color=C["s7"], linewidth=1.2, linestyle=(0, (5, 3)))
    a2.set_xlim(lo, hi)
    a2.set_ylabel("contratos de futuro", color=C["tinta2"], fontsize=9)
    a2.text(0.01, 0.95, "gris = movimiento esperado (1σ)", transform=a2.transAxes, fontsize=8, color=C["tinta2"], va="top")

    _estilo(a3, "Smile 0DTE: Black-76 inverso con el tiempo REAL al vencimiento · banda = IV del bid al ask")
    tb = f.tab[(f.tab["strike"] >= lo) & (f.tab["strike"] <= hi)]
    otm = tb[np.where(tb["strike"] < f.F, tb["tipo"] == "P", tb["tipo"] == "C")].sort_values("strike")
    a3.fill_between(otm["strike"], otm["iv_bid"] * 100, otm["iv_ask"] * 100, color=C["s5"], alpha=0.25, linewidth=0)
    for tipo, col in (("C", C["s1"]), ("P", C["s8"])):
        g = tb[(tb["tipo"] == tipo) & tb["valida"]]
        a3.scatter(g["strike"], g["iv_mid"] * 100, s=12, color=col, alpha=0.7, linewidths=0,
                   label=f"{'calls' if tipo == 'C' else 'puts'} (mid)")
    a3.plot(S.index, S["iv"] * 100, color=C["tinta"], linewidth=1.5, label="smile ajustado (ponderado por vega)")
    a3.axvline(f.F, color=C["tinta"], linewidth=1.0)
    a3.set_xlim(lo, hi)
    a3.set_ylabel("IV (%)", color=C["tinta2"], fontsize=9)
    _leyenda(a3, loc="upper right", frameon=True, facecolor=C["fondo"], edgecolor="none", framealpha=0.9)

    _estilo(a4, "El día: futuro, flip y muros · fondo verde = gamma positiva (frena), rojo = negativa (acelera)")
    tz = cfg.tz_local
    fut = res.datos.fut
    fut = fut[(fut["t"] >= res.fotos[0].t - pd.Timedelta(minutes=30)) & (fut["t"] <= res.datos.defs["vence"].max())]
    a4.plot(fut["t"].dt.tz_convert(tz), (fut["bid"] + fut["ask"]) / 2, color=C["tinta"], linewidth=0.9, label="futuro")
    S2 = res.serie
    tt = S2.index.tz_convert(tz)
    a4.step(tt, S2["flip"], where="post", color=C["s7"], linewidth=1.4, linestyle=(0, (5, 3)), label="flip")
    a4.step(tt, S2["muro_call"], where="post", color=C["s1"], linewidth=1.0, linestyle=":", label="muro calls")
    a4.step(tt, S2["muro_put"], where="post", color=C["s8"], linewidth=1.0, linestyle=":", label="muro puts")
    bordes = list(tt) + [tt[-1] + pd.Timedelta(minutes=cfg.paso_min)]
    for i, g in enumerate(S2["gamma"].to_numpy()):
        a4.axvspan(bordes[i], bordes[i + 1], color=C["s3"] if g > 0 else C["s8"], alpha=0.08, linewidth=0, zorder=0)
    a4.axvline(f.t.tz_convert(tz), color=C["tinta2"], linewidth=0.9, linestyle=":")
    niveles = np.r_[(fut["bid"] + fut["ask"]).to_numpy() / 2, S2["flip"], S2["muro_call"], S2["muro_put"]]
    niveles = niveles[np.isfinite(niveles)]
    if len(niveles):
        pad = 0.06 * (niveles.max() - niveles.min() + 1)
        a4.set_ylim(niveles.min() - pad, niveles.max() + pad)
    a4.xaxis.set_major_locator(mdates.HourLocator(tz=tz))
    a4.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=tz))
    _leyenda(a4, loc="upper left", ncol=4, frameon=True, facecolor=C["fondo"], edgecolor="none", framealpha=0.9)
    fig.text(0.008, 0.012, f"{IDENTIFICADOR} · convención de posiciones: {t['conv']} · σ fija por strike en el perfil · "
             "horas en CDMX", color=C["tenue"], fontsize=7.5)
    fig.savefig(ruta, dpi=110, facecolor=C["fondo"], bbox_inches="tight")
    return fig


def tablero_riesgo(res: Resultado, plt, ruta: Path):
    cfg, f = res.cfg, res.principal
    fig = plt.figure(figsize=(18, 12.5))
    fig.patch.set_facecolor(C["fondo"])
    gs = fig.add_gridspec(2, 3, hspace=0.38, wspace=0.3, bottom=0.06, top=0.92)
    (b1, b2, b3), (b4, b5, b6) = [[fig.add_subplot(gs[i, j]) for j in range(3)] for i in range(2)]
    fig.suptitle(f"0DTE · {cfg.activo} · riesgo de cobertura y auditoría · {_hora(f.t, cfg)}", x=0.01, ha="left",
                 color=C["tinta"], fontsize=12.5)
    lo, hi = _zoom(f)
    S = f.strikes[(f.strikes.index >= lo) & (f.strikes.index <= hi)]
    paso = float(np.median(np.diff(S.index))) if len(S) > 1 else 1.0
    for ax, col, k, tit in ((b1, C["s5"], "e_vanna", "Vanna por strike: contratos por 1 punto de IV"),
                            (b2, C["s4"], "e_charm", "Charm por strike: contratos por hora")):
        _estilo(ax, tit)
        ax.barh(S.index, S[k], height=paso * 0.8, color=col)
        ax.axvline(0, color=C["eje"], linewidth=0.9)
        ax.axhline(f.F, color=C["tinta"], linewidth=1.2)
        ax.set_ylim(lo, hi)
    _estilo(b3, "Open interest (ayer) y volumen de HOY por strike")
    b3.barh(S.index, S["oi_c"], height=paso * 0.8, color=C["s1"], alpha=0.45, label="OI calls")
    b3.barh(S.index, -S["oi_p"], height=paso * 0.8, color=C["s8"], alpha=0.45, label="OI puts")
    b3.barh(S.index, S["vol_c"], height=paso * 0.35, color=C["s1"], label="volumen calls")
    b3.barh(S.index, -S["vol_p"], height=paso * 0.35, color=C["s8"], label="volumen puts")
    b3.axvline(0, color=C["eje"], linewidth=0.9)
    b3.axhline(f.F, color=C["tinta"], linewidth=1.2)
    b3.set_ylim(lo, hi)
    _leyenda(b3, loc="lower right", frameon=True, facecolor=C["fondo"], edgecolor="none", framealpha=0.9)

    _estilo(b4, "Durante el día: gamma neta (c/pt) y charm al cierre (contratos)")
    S2 = res.serie
    tt = S2.index.tz_convert(cfg.tz_local)
    b4.plot(tt, S2["gamma"], color=C["s7"], linewidth=1.6, marker="o", markersize=3, label="gamma neta")
    b4.axhline(0, color=C["eje"], linewidth=0.9)
    b4b = b4.twinx()
    b4b.plot(tt, S2["cierre"], color=C["s4"], linewidth=1.3, linestyle="--", label="charm al cierre")
    b4b.tick_params(colors=C["tinta2"], labelsize=8)
    import matplotlib.dates as mdates
    b4.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=cfg.tz_local))
    h1, l1 = b4.get_legend_handles_labels()
    h2, l2 = b4b.get_legend_handles_labels()
    b4.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8, frameon=False)

    _estilo(b5, "El supuesto de posiciones: gamma y flip con cada convención")
    pc = f.tot["por_convencion"]
    nombres = list(pc)
    b5.bar(range(len(nombres)), [pc[k]["gamma"] for k in nombres],
           color=[C["s7"] if k == f.tot["conv"] else C["neutro"] for k in nombres])
    for i, k in enumerate(nombres):
        b5.text(i, pc[k]["gamma"], f"flip\n{_fmt_p(pc[k]['flip'])}", ha="center",
                va="bottom" if pc[k]["gamma"] >= 0 else "top", fontsize=8.5, color=C["tinta"])
    b5.axhline(0, color=C["eje"], linewidth=0.9)
    b5.set_xticks(range(len(nombres)))
    b5.set_xticklabels([k.replace("_", "\n") for k in nombres], fontsize=9)
    b5.set_ylabel("gamma neta (c/pt)", color=C["tinta2"], fontsize=9)
    b5.margins(y=0.25)

    b6.set_facecolor(C["fondo"])
    b6.axis("off")
    b6.set_title("Chequeo de cordura", color=C["tinta"], fontsize=10, loc="left", pad=8)
    import textwrap as _tw
    yy = 0.98
    lineas_tu = []
    if res.tuyo:
        tu = res.tuyo
        lineas_tu = [(tu["iv_ratio"] > 0.9, f"tus fórmulas aquí: IV ×{tu['iv_ratio']:.2f}, gamma ×{tu['gamma_ratio']:.2f}, "
                                            f"vanna ×{tu['vanna_ratio']:.2f}, charm ×{tu['charm_signo']:+.3f}")]
    for ok_, txt in list(res.cordura) + lineas_tu:
        lineas = _tw.wrap(txt, 58)
        b6.text(0.0, yy, "✓" if ok_ else "⚠", color=C["s3"] if ok_ else C["baja"], fontsize=11, transform=b6.transAxes, va="top")
        b6.text(0.06, yy, "\n".join(lineas), color=C["tinta"], fontsize=8.5, transform=b6.transAxes, va="top")
        yy -= 0.04 * len(lineas) + 0.03
    fig.text(0.008, 0.012, f"{IDENTIFICADOR} · contratos de futuro equivalentes · + = los dealers compran",
             color=C["tenue"], fontsize=7.5)
    fig.savefig(ruta, dpi=110, facecolor=C["fondo"], bbox_inches="tight")
    return fig


def tableros(res: Resultado, mostrar: bool = True) -> tuple[list[Path], object, bool]:
    plt, ventana = _preparar_grafico(mostrar)
    if plt is None:
        return [], None, False
    carpeta = _ruta(res.cfg.salida_dir)
    carpeta.mkdir(parents=True, exist_ok=True)
    rutas = []
    for nombre_, fn in (("dashboard", tablero_0dte), ("riesgo", tablero_riesgo)):
        ruta = carpeta / f"0dte_{nombre_}_{res.cfg.activo}_{res.cfg.fecha}.png"
        fig = fn(res, plt, ruta)
        rutas.append(ruta)
        print(f"🖼  {ruta}")
        if not ventana:
            plt.close(fig)
    return rutas, plt, ventana


# =============================================================================
# 9. TELEGRAM Y ARCHIVOS
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


def mensaje_telegram(res: Resultado, limite: int = 4096) -> str:
    esc, cfg, f = html.escape, res.cfg, res.principal
    t = f.tot
    lin = [f"<b>{esc(IDENTIFICADOR)}</b> · {esc(cfg.activo)} 0DTE · {esc(cfg.fecha)} · {esc(_hora(f.t, cfg))}",
           f"futuro {f.F:,.2f} · faltan {t['T_h']:.1f} h · IV ATM {t['iv_atm']:.1%} · ±{t['mov_esperado']:,.1f} pts (1σ)",
           f"<b>gamma {t['regimen']}</b> {t['gamma']:+,.0f} c/pt · GEX {t['gex_usd'] / 1e6:+,.1f} M USD/1 %",
           f"flip {_fmt_p(t['flip'])} · muro calls {_fmt_p(t['muro_call'])} · muro puts {_fmt_p(t['muro_put'])}",
           f"charm al cierre: dealers {esc(_dealers(-t['cierre']).lower())}", ""]
    lin += [esc(p) for p in lectura(res)[:3]]
    malos = [x for ok, x in res.cordura if not ok]
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


def guardar(res: Resultado) -> None:
    cfg, f = res.cfg, res.principal
    carpeta = _ruta(cfg.salida_dir)
    carpeta.mkdir(parents=True, exist_ok=True)
    suf = _nombre_seguro(cfg.activo, cfg.fecha, f"{f.t.tz_convert(cfg.tz_mercado):%H%M}CT")
    f.strikes.to_csv(carpeta / f"0dte_por_strike_{suf}.csv")
    cols = ["simbolo", "producto", "tipo", "strike", "vence", "T", "F", "bid", "ask", "mid", "iv_mid", "iv_bid", "iv_ask",
            "motivo", "iv", "fuente_iv", "delta", "gamma", "vega", "vanna", "charm", "theta", "oi", "vol_hoy", "flujo",
            "pos", "e_delta", "e_gamma", "e_vanna", "e_charm", "e_cierre", "gex_usd"]
    f.tab[cols].to_csv(carpeta / f"0dte_opciones_{suf}.csv")
    res.serie.to_csv(carpeta / f"0dte_dia_{_nombre_seguro(cfg.activo, cfg.fecha)}.csv")
    f.perfil.to_csv(carpeta / f"0dte_perfil_{suf}.csv", index=False)
    print(f"💾 Por strike, por opción, el día y el perfil de cobertura guardados en {carpeta}")


# =============================================================================
# 10. LÍNEA DE COMANDOS
# =============================================================================
def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Flujo 0DTE AC v2 — exposición de los dealers en las opciones que vencen hoy")
    p.add_argument("--pruebas", action="store_true", help="pruebas internas (sin red ni datos)")
    p.add_argument("--simulacion", action="store_true", help="día 0DTE simulado con verdad conocida")
    p.add_argument("--activo", help="ES (por omisión) o NQ")
    p.add_argument("--fecha", help="día del vencimiento, p. ej. 2026-09-25")
    p.add_argument("--hora", help="foto principal, hora de Chicago, p. ej. 13:30")
    p.add_argument("--desde", help="primera foto, hora de Chicago (08:30)")
    p.add_argument("--paso", type=int, dest="paso_min", help="minutos entre fotos (15)")
    p.add_argument("--convencion", choices=CONVENCIONES)
    p.add_argument("--productos", help="familias de opciones separadas por coma, p. ej. ES,EW,EW4,E1A")
    p.add_argument("--tasa", type=float)
    p.add_argument("--rango", type=float, dest="rango_pct", help="perfil de cobertura ±%% (0.03)")
    p.add_argument("--costo-max", type=float, dest="costo_max_usd")
    p.add_argument("--salida", dest="salida_dir", help="carpeta para CSV y PNG (salidas_0dte/)")
    p.add_argument("--sin-grafica", "--sin-tablero", action="store_true", dest="sin_tablero")
    p.add_argument("--sin-ventana", action="store_true")
    p.add_argument("--semilla", type=int, dest="sim_semilla")
    t = p.add_argument_group("Telegram")
    t.add_argument("--telegram", action="store_true", help="resumen + 2 tableros")
    t.add_argument("--telegram-documentos", action="store_true")
    t.add_argument("--telegram-buscar-chat", action="store_true")
    return p


def config_desde_args(a: argparse.Namespace) -> Config:
    claves = ("fecha", "hora", "desde", "paso_min", "convencion", "tasa", "rango_pct", "costo_max_usd", "salida_dir",
              "sim_semilla")
    cambios = {k: getattr(a, k) for k in claves if getattr(a, k, None) is not None}
    if a.activo:
        cambios["activo"] = a.activo.upper()
    if a.productos:
        cambios["productos"] = tuple(x.strip().upper() for x in a.productos.split(",") if x.strip())
    return replace(CFG, **cambios)


def main(argv: list[str] | None = None) -> int:
    a = construir_parser().parse_args(argv)
    cfg = config_desde_args(a)
    if a.pruebas:
        return pruebas()
    if a.telegram_buscar_chat:
        return buscar_chat_telegram()
    validar(cfg)
    print(f"▶ {IDENTIFICADOR} · {cfg.activo} · vencimiento {cfg.fecha}")
    verdad = None
    if a.simulacion:
        print("🎲 Día 0DTE simulado: futuro, smile, OI y flujo de clientes CONOCIDOS, escritos como registros de Databento.")
        datos, verdad = simular(cfg)
    else:
        datos = obtener_datos(cfg)
    res = analizar(datos, cfg, verdad=verdad)
    reporte_datos(res)
    reporte_foto(res)
    reporte_cobertura(res)
    reporte_dia(res)
    reporte_auditoria(res)
    reporte_verdad(res)
    rutas, plt_, ventana = ([], None, False)
    if not a.sin_tablero:
        print()
        rutas, plt_, ventana = tableros(res, mostrar=not a.sin_ventana)
    guardar(res)
    if a.telegram:
        enviar_telegram(res, rutas, documentos=a.telegram_documentos)
    _titulo("CÓMO LEER ESTO")
    print("  1. Gamma POSITIVA: los dealers venden alzas y compran bajas (frenan). NEGATIVA: al revés (aceleran).")
    print("  2. El flip es el precio donde la gamma cambia de signo; los muros, los strikes con más gamma × OI.")
    print("  3. 'Si el futuro va a…' dice cuántos contratos tendrían que comprar o vender los dealers para seguir")
    print("     cubiertos. El charm dice lo mismo pero por el puro paso del tiempo.")
    print("  4. Todo depende de un SUPUESTO sobre quién está largo y quién corto: mira la tabla por convención.")
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

    _titulo("PRUEBAS INTERNAS")
    rng = np.random.default_rng(0)
    r = 0.04
    n = 4000
    F = rng.uniform(4000, 6000, n)
    K = F * np.exp(rng.normal(0, 0.03, n))
    T = np.exp(rng.uniform(np.log(5 / 525600), np.log(30 / 365), n))       # de 5 minutos a 30 días
    s = rng.uniform(0.05, 0.8, n)
    call = rng.random(n) < 0.5

    # 1 ------------------------------------------ Black-76: paridad put-call exacta
    c = precio_b76(F, K, T, r, s, True)
    p = precio_b76(F, K, T, r, s, False)
    err1 = float(np.max(np.abs(c - p - np.exp(-r * T) * (F - K)) / F))
    check("Black-76: C − P = e^(−rT)·(F − K) en 4 000 casos (de 5 min a 30 días)", err1 < 1e-12, f"error {err1:.1e}")

    # 2 ------------------------------------------ IV inversa: ida y vuelta
    pr = precio_b76(F, K, T, r, s, call)
    vale = pr > np.exp(-r * T) * np.where(call, np.maximum(F - K, 0), np.maximum(K - F, 0)) + 1e-6 * F
    iv, mot = iv_b76(pr, F, K, T, r, call)
    err2 = float(np.nanmax(np.abs(iv[vale] - s[vale])))
    check("IV inversa: precio → σ → precio recupera σ (bisección vectorizada, sin scipy)",
          err2 < 1e-6 and np.isfinite(iv[vale]).all(), f"error máximo {err2:.1e} en {int(vale.sum()):,} opciones")

    # 3 ------------------------------------------ casos que no tienen IV, con su motivo
    _, m3 = iv_b76(np.array([np.nan, 0.0, 1.0, 50.0, 10.0]), 5000.0, np.array([5000, 5000, 4900, 5000, 5000.0]),
                   np.array([0.01, 0.01, 0.01, 0.01, 0.0]), r, np.array([True, True, True, True, True]))
    check("sin IV: sin precio, bajo el intrínseco y vencida, cada una con su motivo (no un 0 que entre a promedios)",
          list(m3[[0, 1, 2, 4]]) == ["sin precio", "sin precio", "bajo el intrínseco", "vencida"])

    # 4 ------------------------------------------ griegas contra diferencias finitas
    sel = np.abs(np.log(K / F)) < 2.5 * s * np.sqrt(T)
    Fm, Km, Tm, sm, cm = F[sel], K[sel], T[sel], s[sel], call[sel]
    g = griegas(Fm, Km, Tm, r, sm, cm)
    h, hs, ht = 1e-3 * sm * np.sqrt(Tm) * Fm, 1e-6, Tm * 1e-5
    num = {"delta": (precio_b76(Fm + h, Km, Tm, r, sm, cm) - precio_b76(Fm - h, Km, Tm, r, sm, cm)) / (2 * h),
           "gamma": (griegas(Fm + h, Km, Tm, r, sm, cm)["delta"] - griegas(Fm - h, Km, Tm, r, sm, cm)["delta"]) / (2 * h),
           "vega": (precio_b76(Fm, Km, Tm, r, sm + hs, cm) - precio_b76(Fm, Km, Tm, r, sm - hs, cm)) / (2 * hs) / 100,
           "vanna": (griegas(Fm, Km, Tm, r, sm + hs, cm)["delta"] - griegas(Fm, Km, Tm, r, sm - hs, cm)["delta"]) / (2 * hs) / 100,
           "charm": -(griegas(Fm, Km, Tm + ht, r, sm, cm)["delta"] - griegas(Fm, Km, Tm - ht, r, sm, cm)["delta"])
           / (2 * ht) / HORAS_ANIO,
           "theta": -(precio_b76(Fm, Km, Tm + ht, r, sm, cm) - precio_b76(Fm, Km, Tm - ht, r, sm, cm)) / (2 * ht) / 365}
    peor = {k: float(np.max(np.abs(g[k] - v) / np.maximum(np.abs(g[k]), np.max(np.abs(g[k])) * 1e-4)))
            for k, v in num.items()}
    check("griegas = diferencias finitas: delta, gamma, vega, vanna, charm (por hora) y theta (por día)",
          max(peor.values()) < 1e-4, " · ".join(f"{k} {v:.0e}" for k, v in peor.items()))

    # 5 ------------------------------------------ charm: decae hacia el delta del vencimiento
    Fq, Kq, sq_ = 5000.0, np.array([4990.0, 5015.0]), 0.15
    Tq = 2 / HORAS_ANIO
    pasos = np.linspace(Tq, 1e-7, 20_001)
    integ = sum(-griegas(Fq, Kq, pasos[i], r, sq_, True)["charm"] * (pasos[i + 1] - pasos[i]) * HORAS_ANIO
                for i in range(len(pasos) - 1))
    exacto = delta_vencimiento(Fq, Kq, True) - griegas(Fq, Kq, Tq, r, sq_, True)["delta"]
    check("∫ charm de 2 h al vencimiento = delta al vencimiento − delta de ahora",
          bool(np.all(np.abs(integ - exacto) < 0.01)), f"{np.round(integ, 3)} vs {np.round(exacto, 3)}")

    # 6 ------------------------------------------ convenciones de posición
    oi, fl, cc = np.array([10.0, 10.0]), np.array([-3.0, 2.0]), np.array([True, False])
    check("posiciones: clásica (+calls −puts), clientes compran (−todo), flujo (clásica + lo de hoy)",
          list(posiciones(oi, fl, cc, "clasica")) == [10, -10] and list(posiciones(oi, fl, cc, "clientes_compran")) == [-10, -10]
          and list(posiciones(oi, fl, cc, "flujo")) == [7, -8])

    # 7 ------------------------------------------ flip
    rej = np.linspace(4900, 5100, 201)
    check("flip: el cruce de la gamma por cero más cercano al futuro, interpolado",
          abs(_flip(rej, (rej - 5037.25) * -2.0, 5000.0) - 5037.25) < 1e-9 and np.isnan(_flip(rej, rej * 0 + 1, 5000.0)))

    # 8 ------------------------------------------ la rejilla de cotizaciones: antigüedad y "sin bid"
    t0 = pd.Timestamp("2026-09-25 14:00", tz="UTC")
    q = pd.DataFrame({"t": [t0, t0 + pd.Timedelta(minutes=1)], "iid": [1, 1], "bid": [5.0, np.nan], "ask": [5.5, 5.75]})
    rj = Rejilla(q, "iid", [1], 5)
    b0, _ = rj.en(t0)
    b1, a1 = rj.en(t0 + pd.Timedelta(minutes=1))
    b2, a2 = rj.en(t0 + pd.Timedelta(minutes=9))
    check("cotizaciones: un minuto nuevo sin bid NO hereda el bid viejo, y nada vive más de 5 min",
          b0[0] == 5.0 and np.isnan(b1[0]) and a1[0] == 5.75 and np.isnan(a2[0]))

    # --- un día simulado completo, por la ruta de Databento (DBN → to_df → normalización) ---
    datos, ver = simular(cfg, semilla=3)
    res = callado(analizar, datos, cfg, verdad=ver, verbose=False)
    md = res.medicion

    # 9 ------------------------------------------ definiciones: 0DTE, puntos y multiplicador
    d = datos.defs
    check("definiciones: sólo lo que vence HOY, strikes en puntos (no entre 1e9) y multiplicador 50 del registro",
          len(d) == len(ver["ids"]) and set(d["producto"]) == {"EW4"} and d["strike"].between(4000, 7000).all()
          and (d["mult"] == 50).all() and (d["vence"].dt.tz_convert(cfg.tz_mercado).dt.hour == 15).all(),
          f"{len(d)} opciones · strikes {d['strike'].min():,.0f}-{d['strike'].max():,.0f}")

    # 10 ----------------------------------------- estadísticas: OI de 'quantity', liquidación = tipo 3 (no 11)
    import databento_dbn as dd
    t_ = int(pd.Timestamp("2026-09-25 11:00", tz="UTC").value)
    ref = int(pd.Timestamp("2026-09-24", tz="UTC").value)
    recs = [dd.StatMsg(publisher_id=1, instrument_id=7, ts_event=t_, ts_recv=t_, ts_ref=ref, price=2 ** 63 - 1,
                       quantity=321, stat_type=dd.StatType.OPEN_INTEREST),
            dd.StatMsg(publisher_id=1, instrument_id=7, ts_event=t_, ts_recv=t_, ts_ref=ref, price=12_500_000_000,
                       quantity=Q_INDEF, stat_type=dd.StatType.SETTLEMENT_PRICE),
            dd.StatMsg(publisher_id=1, instrument_id=7, ts_event=t_, ts_recv=t_, ts_ref=ref, price=99_000_000_000,
                       quantity=Q_INDEF, stat_type=dd.StatType.CLOSE_PRICE)]
    tb = _tabla(_dbn(dd.Schema.STATISTICS, recs, dd.SType.INSTRUMENT_ID))
    ne = norm_estadisticas(tb, cfg)
    check("estadísticas: OI de la columna 'quantity', liquidación del tipo 3 (el 11 es el último precio); "
          "no existe la columna 'value'",
          ne.loc[7, "oi"] == 321 and ne.loc[7, "liq"] == 12.5 and "value" not in tb.columns)

    # 11 ----------------------------------------- la IV recupera el smile verdadero
    check("IV por strike contra el smile verdadero (a ±1σ): error mediano < 0.3 pts de vol",
          md["iv_err"] < 0.3 and md["F_err"] <= 0.25,
          f"{md['iv_err']:.2f} pts (p90 {md['iv_err90']:.2f}) · futuro ±{md['F_err']:.3f}")

    # 12 ----------------------------------------- auditoría en verde en la simulación
    check("auditoría en verde: paridad, IV de CME, griegas, arbitraje, OI y ajuste del smile",
          all(ok for ok, _ in res.cordura), f"{len(res.cordura)} chequeos")

    # 13 ----------------------------------------- el flujo del día es exactamente el de la verdad
    f = res.principal
    flujo_v = ver["flujo"][ver["flujo"]["t"] <= f.t.value].groupby("iid")["dealer"].sum()
    mio = pd.Series(f.tab["flujo"].to_numpy(), index=f.tab.index)
    check("flujo de hoy: lo que vendieron/compraron los dealers (agresor = cliente, sin cruces) = la verdad",
          bool(np.allclose(mio.reindex(flujo_v.index).fillna(0), flujo_v)) and abs(mio.sum() - flujo_v.sum()) < 1e-9,
          f"{abs(flujo_v).sum():,.0f} contratos")

    # 14 ----------------------------------------- agregación y unidades
    st = f.strikes
    gex = float((f.tab["e_gamma"] * 0.01 * f.tab["F"] ** 2 * f.tab["mult"]).sum())
    pf = f.perfil
    i0 = int(np.argmin(np.abs(pf["F"] - f.F)))
    pend = (pf["flujo"].iloc[i0 + 1] - pf["flujo"].iloc[i0 - 1]) / (pf["F"].iloc[i0 + 1] - pf["F"].iloc[i0 - 1])
    check("unidades: Σ por strike = total; GEX = Γ·0.01·F²·mult; la pendiente del flujo de cobertura = −gamma neta",
          abs(st["e_gamma"].sum() - f.tot["gamma"]) < 1e-6 and abs(gex - f.tot["gex_usd"]) < 1e-3 * abs(gex)
          and abs(pend + f.tot["gamma"]) < 0.02 * abs(f.tot["gamma"]), f"pendiente {pend:,.1f} vs gamma {f.tot['gamma']:,.1f}")

    # 15 ----------------------------------------- movimiento esperado y straddle
    t15 = f.tot
    check("straddle ATM ≈ √(2/π)·F·σ·√T (el movimiento esperado que cotiza el mercado)",
          abs(t15["straddle"] / t15["mov_esperado"] - math.sqrt(2 / math.pi)) < 0.08,
          f"straddle {t15['straddle']:.2f} · F·σ·√T {t15['mov_esperado']:.2f}")

    # 16 ----------------------------------------- tus fórmulas
    tu = res.tuyo
    esperado = math.sqrt(tu["T_real_h"] / 24)
    check("tus fórmulas: con T = 1 día la IV sale × √(T real / 1 día) y tu charm tiene el signo contrario",
          abs(tu["iv_ratio"] / esperado - 1) < 0.15 and tu["charm_signo"] < 0 and abs(tu["gamma_ratio"] - 1) < 0.1,
          f"IV × {tu['iv_ratio']:.2f} (esperado {esperado:.2f}) · charm × {tu['charm_signo']:+.3f}")

    # 17 ----------------------------------------- validaciones de entrada
    sab = False
    try:
        validar(replace(cfg, fecha="2026-08-01"))
    except SystemExit:
        sab = True
    check("tu fecha 2026-08-01 es sábado: el módulo lo dice en vez de buscar opciones que no existen", sab)

    # 18 ----------------------------------------- max pain a mano
    st18 = pd.DataFrame({"oi_c": [100.0, 0, 0], "oi_p": [0, 0, 300.0]}, index=pd.Index([90.0, 100.0, 110.0], name="strike"))
    check("max pain: el strike donde las opciones con OI pagan menos (a mano: 110)", dolor_maximo(st18) == 110.0)

    # 19 ----------------------------------------- reportes, tableros y archivos
    with tempfile.TemporaryDirectory() as tmp:
        rr = replace(res, cfg=replace(res.cfg, salida_dir=tmp))
        texto = io.StringIO()
        try:
            with contextlib.redirect_stdout(texto):
                reporte_datos(rr)
                reporte_foto(rr)
                reporte_cobertura(rr)
                reporte_dia(rr)
                reporte_auditoria(rr)
                reporte_verdad(rr)
                rutas, plt_, _ = tableros(rr, mostrar=False)
                guardar(rr)
            archivos = sorted(p_.name for p_ in Path(tmp).iterdir())
            if plt_ is not None:
                plt_.close("all")
            check("reportes, auditoría textual, 2 tableros PNG y 4 CSV sin errores",
                  len(rutas) == 2 and all(p_.stat().st_size > 50_000 for p_ in rutas)
                  and sum(a_.endswith(".csv") for a_ in archivos) == 4 and "AUDITORÍA TEXTUAL" in texto.getvalue()
                  and "Si el futuro se va a" in texto.getvalue(), ", ".join(archivos))
        except Exception as e:                                    # pragma: no cover
            check("reportes, tableros y CSV", False, repr(e))

    # 20 ----------------------------------------- línea de comandos
    try:                                         # Python ≥ 3.14 valida cada help al crear el parser
        ayuda = construir_parser().format_help()
    except Exception as e:                                    # pragma: no cover
        ayuda = repr(e)
    check("la ayuda (--help) se arma sin errores en cualquier versión de Python",
          "--rango" in ayuda and "±%" in ayuda and "%%" not in ayuda, ayuda[-120:])
    a_ = construir_parser().parse_args(["--activo", "nq", "--fecha", "2026-09-24", "--hora", "11:15", "--convencion",
                                        "clasica", "--productos", "nq,qn,q4c", "--paso", "30"])
    c_ = config_desde_args(a_)
    check("línea de comandos: --activo NQ, --fecha, --hora, --convencion, --productos, --paso",
          c_.activo == "NQ" and c_.fecha == "2026-09-24" and c_.hora == "11:15" and c_.convencion == "clasica"
          and productos_de(c_) == ("NQ", "QN", "Q4C") and c_.paso_min == 30 and activo(c_)["mult"] == 20)

    # 21 ----------------------------------------- Telegram: nunca el token
    tok = "123456789:" + "A" * 35
    msg = _sin_token(f"fallo en https://api.telegram.org/bot{tok}/sendMessage", tok)
    check("los errores de Telegram nunca muestran el token", tok not in msg and "…" in msg)

    # 22 ----------------------------------------- multipart de sendPhoto, sin red
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
    png = Path(tempfile.gettempdir()) / "_prueba_telegram_0dte.png"
    bien = False
    try:
        urllib.request.urlopen = _falso
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
        ok = llamar_telegram(tok, "sendPhoto", {"chat_id": "123456789", "caption": "á <b>"},
                             archivo=("photo", png)).get("ok")
        cuerpo = capturas[-1].data
        limite = capturas[-1].get_header("Content-type").split("boundary=")[1]
        bien = (ok and cuerpo.startswith(f"--{limite}".encode()) and cuerpo.rstrip().endswith(f"--{limite}--".encode())
                and b'name="photo"; filename="_prueba_telegram_0dte.png"' in cuerpo and tok.encode() not in cuerpo)
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
    check("el mensaje de Telegram cabe y escapa el HTML", len(txt) <= 4096 and "<b>" in txt, f"{len(txt)} caracteres")

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
