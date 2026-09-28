# -*- coding: utf-8 -*-
"""
VPIN AC v3 — toxicidad del flujo con reloj de VOLUMEN y agresor exacto (Easley, López de Prado y O'Hara)
Datos: Databento trades (GLBX.MDP3), operación por operación, con el lado agresor que reporta CME.

Qué hace, en una línea: arma el VPIN de Easley, López de Prado y O'Hara con las operaciones
del NQ una por una (Databento trades), en paquetes de V contratos en vez de horas y con el
lado agresor que reporta CME en vez de deducirlo del precio. Alerta cuando la toxicidad es
alta RELATIVA a su propia historia y además mayor que la que daría el puro azar. Después
audita si eso anticipa algo que no se viera ya en la volatilidad, el volumen y la hora.

LO QUE PEDISTE, HECHO A FONDO

  1. RELOJ DE VOLUMEN (EN LUGAR DE RELOJ DE TIEMPO). Cada bucket junta exactamente V
     contratos (V = volumen mediano de las 5 primeras sesiones / 50). Una operación grande
     se reparte y puede cerrar varios buckets. En la simulación un bucket tarda 13 min en
     horario regular y 44 fuera de él: el reloj corre con el mercado. Para medir por qué
     importa, el módulo calcula también tu v1 de reloj de TIEMPO (barras de 1 h). Su
     toxicidad sigue a la que daría el azar con el volumen de esa hora, √(2κ/(π·n)):
     Spearman +0.25 a +0.46 en 36 simulaciones. Por eso su IC crudo con la volatilidad
     futura sale NEGATIVO en las 20 simulaciones sin flujo informado (−0.18 en promedio):
     las horas quietas "salen tóxicas" y después viene poca volatilidad. Con reloj de
     volumen el |oi| de un bucket no depende de cuánto tardó (lo vigila el chequeo).

  2. IDENTIFICACIÓN EXACTA DEL AGRESOR. side 'B' = compra agresiva, 'A' = venta agresiva.
     'N' (subasta de apertura, operaciones implícitas) queda fuera de los buckets y se
     reporta aparte. Un chequeo lo verifica en TUS datos: en el mismo segundo las compras
     agresivas deben hacerse arriba de las ventas (+1.05 ticks en la simulación; con los
     lados al revés sale negativo y se marca ⚠). Se compara con la clasificación en bloque
     (BVC) del artículo, que deduce el lado del cambio de precio de 1 min. La BVC atina al
     lado del 71 % del volumen, y como usa el precio, su VPIN es en buena parte un eco de la
     volatilidad. Sin ningún informado, su IC crudo con la volatilidad futura es +0.14
     (positivo en 18 de 20 corridas), contra −0.01 del agresor exacto. Es la crítica de
     Andersen y Bondarenko, reproducida con datos cuya verdad se conoce.

  3. MEDICIÓN POR PERCENTIL DE TOXICIDAD RELATIVA. Es el percentil del VPIN contra los 250
     buckets ANTERIORES (≈ 5 sesiones; el actual no entra y los empates cuentan la mitad).
     Alerta con CDF ≥ 0.90 como el artículo, con histéresis (se rearma bajo 0.75) y 120 min
     de enfriamiento. [v3] Además el VPIN tiene que superar el PISO DE AZAR. Con lados de
     moneda el VPIN vale √(2κ/(π·V)) ± √((1 − 2/π)·κ/(V·n)), con κ = Σq²/Σq de las sesiones
     de calibración. En semanas tranquilas el percentil solo marca como tóxico un VPIN que
     una moneda también daría. En 20 simulaciones sin flujo informado (500 sesiones) el piso
     baja las alertas de 246 a 25. Con flujo informado (16 simulaciones) las alertas
     verdaderas quedan igual (56 contra 55) y las falsas bajan de 31 a 18: la precisión sube
     de 64 % a 76 %. La fórmula se comprueba sola: sin informados, el VPIN mediano queda en
     0.96-1.03 veces ese valor. --sin-piso lo apaga.

  4. AUDITORÍA Y CORRELACIÓN DE RANGO PARCIAL. Spearman entre el percentil y la volatilidad
     FUTURA a 30, 60, 120 y 240 min, cruda y parcial. La parcial quita lo que explican la
     volatilidad y el volumen recientes (tu v2) y además la volatilidad típica de esa media
     hora del día, calculada sólo con sesiones anteriores. La significancia sale de un IC
     parcial POR SESIÓN y una t entre sesiones (Fama-MacBeth), con su IC de 90 % y cuántas
     sesiones salen positivas. Se hace para las tres variantes (exacto, BVC, reloj de
     tiempo). Además: estudio de eventos (volatilidad tras cada alerta / la típica de esa
     hora), dirección (desbalance con signo contra el retorno futuro), relación mecánica con
     la actividad, rebote bid-ask por hora y una lista ✓/⚠ de cordura.

  5. DOBLE MOTOR DE EJECUCIÓN. El vectorizado usa curvas acumuladas de volumen y
     desbalance: el oi en cada límite k·V sale exacto aunque una operación cruce varios. Lee
     la historia por bloques de 5 000 000 registros, arrastrando el estado. El incremental va
     operación por operación y es el de Live. Los dos son los de tu v2, que ya eran
     correctos. Cada corrida verifica que den buckets IDÉNTICOS sobre los primeros 300 000
     registros de tus datos. Las pruebas lo verifican con bloques de 1 a 10⁹ registros,
     desde un DBN de verdad y con 900 registros basura inyectados.

  Además: Live con Telegram (--live --telegram-live manda cada alerta a tu teléfono), un
  simulador con verdad conocida que escribe un DBN de verdad, 2 tableros, 3 CSV y 27
  pruebas internas.

QUÉ SE MIDIÓ — 36 simulaciones de 30 sesiones: 16 con flujo informado (modelo PIN), 20 sin él

    ¿el VPIN exacto anticipa volatilidad?        casos con p < 0.10 (4 horizontes)
                                                 sin informados    con informados
    tu t con n_eff (v2)                               25 %              41 %
    t entre sesiones (módulo)                          5 %              11 %
    (sin informados la respuesta correcta es "no": una buena prueba da ≈ 10 %)

  · Tu t "encuentra" efecto en 41 % de los casos con informados, pero también en 25 % sin
    ellos: no distingue. La del módulo no rechaza de más y, con 25 sesiones, casi nunca
    encuentra el efecto de esta simulación: el IC parcial real del VPIN es +0.035 a 60 min.
  · Que no anticipe de forma continua no es un error de cálculo. En la simulación la noticia
    privada se hace pública al terminar el episodio, con 20 min de volatilidad fuerte, y la
    volatilidad a 60 min después de una alerta es 1.6 veces la típica de esa hora (1.1 sin
    informados). Pero una ventana de 50 buckets es casi una sesión: el VPIN sigue alto horas
    después de que todo pasó, y eso diluye la correlación. Por eso se reportan las dos cosas.
  · Sólo 57 de 182 episodios duran 5 buckets o más. Los demás son nocturnos o cortos, y 1-4
    buckets de informados apenas mueven un promedio de 50. De esos 57, 39 (68 %) quedan
    marcados como tóxicos durante el episodio o hasta 1 h después.

QUÉ CAMBIA RESPECTO A TU v2 (los comentarios [v2] lo marcan en el código)

  Tu v2 ya estaba bien hecha: la key sale de DATABENTO_API_KEY, los dos motores son
  correctos, el uint32 se convierte antes de restar y el percentil no mira al futuro. Todo
  eso se conserva. Lo que cambia:

  · LA PRUEBA DE SIGNIFICANCIA. n_eff = min(n, minutos/h) trata como independientes datos que
    no lo son: el VPIN es un promedio de casi una sesión y la volatilidad tiene un componente
    diario persistente. Por eso rechaza 25 % cuando debería rechazar 10 % (tabla de arriba).

  · LA VOLATILIDAD CON RETORNOS DE 1 MIN del último precio operado incluye el rebote entre bid
    y ask (Roll 1984). Aquí se usan retornos de 5 min, y el tablero muestra por hora cuánto
    pesa el rebote en TUS datos (Σr² con 1 min / Σr² con 5 min).

  · SIN CONTROL POR HORA DEL DÍA, cualquier cosa que suba en la apertura de Nueva York
    "anticipa" volatilidad.

  · SIN PISO DE AZAR, en semanas tranquilas alertaba por un VPIN que da una moneda (246 → 25
    falsas alarmas en la simulación sin informados).

  · Menores: también quedan fuera las operaciones con tamaño 0 o precio indefinido (antes
    sólo las no-operaciones y el side 'N'), y hay Telegram, que no tenía.

LÍMITES QUE CONVIENE SABER
  · El piso de azar supone lados independientes. En el mercado real el signo de las
    operaciones está autocorrelacionado (órdenes partidas; Lillo y Farmer 2004), así que en
    tus datos el VPIN probablemente quede siempre arriba de la moneda y el piso rara vez
    decida. El reporte da el VPIN mediano como múltiplo del azar. κ es uno solo para todas
    las horas.
  · Con un mes de datos quedan ~15-20 sesiones después de calibrar. La t entre sesiones tiene
    pocos grados de libertad y sólo un efecto grande saldrá con p < 0.05: más sesiones dan
    más poder.
  · Menos de 30 alertas en el estudio de eventos es anecdótico (el reporte lo avisa).
  · La simulación decide la plomería y la estadística, no si el VPIN funciona en el NQ. Eso
    lo dice la auditoría con tus datos.
  · Live calienta con 8 días de historia hasta el último halt diario (16:00 CT). Databento
    Live repite como máximo las últimas 24 h; si el halt quedó antes, avisa del hueco.

CÓMO SE USA
    pip install numpy pandas matplotlib databento
    python vpin.py --pruebas                        # 27 pruebas, sin red
    python vpin.py --simulacion                     # mercado simulado con verdad conocida
    python vpin.py --simulacion --sin-informados    # el mismo mercado SIN flujo informado
    python vpin.py                                  # NQ, 1-29 de junio de 2026 (tu Config)
    python vpin.py --inicio 2026-06-01T00:00:00 --fin 2026-08-21T23:59:00
    python vpin.py --simbolo ES --motor incremental
    python vpin.py --archivo trades.dbn.zst
    python vpin.py --volumen-bucket 8000 --ventana 50 --umbral 0.9 --rearme 0.75
    python vpin.py --sin-piso                       # como tu v2: sólo el percentil
    python vpin.py --telegram                       # resumen + 2 tableros
    python vpin.py --telegram-solo-alertas          # sólo si hubo alerta en las últimas 24 h
    python vpin.py --live --telegram-live           # en vivo; cada alerta a tu teléfono
  Las horas van en hora de CHICAGO y de CDMX. Antes de descargar se revisa el costo
  (--costo-max, 25 USD por omisión). Con --sin-paridad se salta el chequeo de motores.

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
  Easley, D., López de Prado, M. y O'Hara, M. (2012), "Flow toxicity and liquidity in a
      high-frequency world", Review of Financial Studies 25(5). — el VPIN, los buckets de
      volumen, la BVC y la alerta con CDF > 0.9.
  Easley, D., López de Prado, M. y O'Hara, M. (2011), "The microstructure of the 'flash
      crash'", Journal of Portfolio Management 37(2).
  Andersen, T. y Bondarenko, O. (2014), "VPIN and the flash crash", Journal of Financial
      Markets 17. — la crítica: buena parte del poder del VPIN viene del volumen y la BVC.
  Chakrabarty, B., Pascual, R. y Shkilko, A. (2015), "Evaluating trade classification
      algorithms: bulk volume classification versus the tick rule and the Lee-Ready
      algorithm", Journal of Financial Markets 25.
  Easley, D., Kiefer, N., O'Hara, M. y Paperman, J. (1996), "Liquidity, information, and
      infrequently traded stocks", Journal of Finance 51(4). — el modelo PIN del simulador.
  Fama, E. y MacBeth, J. (1973), "Risk, return, and equilibrium: empirical tests", Journal
      of Political Economy 81(3). — la prueba entre sesiones.
  Granger, C. y Newbold, P. (1974), "Spurious regressions in econometrics", Journal of
      Econometrics 2(2). — por qué dos series persistentes parecen correlacionadas.
  Roll, R. (1984), "A simple implicit measure of the effective bid-ask spread in an
      efficient market", Journal of Finance 39(4). — el rebote bid-ask.
  Lillo, F. y Farmer, J. D. (2004), "The long memory of the efficient market", Studies in
      Nonlinear Dynamics & Econometrics 8(3). — el signo de las operaciones persiste.
  Databento: https://databento.com/docs — esquema trades, side A/B/N, Live y replay.
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
from collections import deque
from dataclasses import dataclass, replace
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

try:
    import databento as db
except ModuleNotFoundError:
    db = None

IDENTIFICADOR = "vpin-ac-v3"
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)
np.seterr(all="ignore")

MINUTOS_SESION = 1380            # 17:00 → 16:00 CT (23 horas)
DESFASE_H = 7                    # hora CT + 7 h → la sesión que abre a las 17:00 cae en su fecha
NS = 1_000_000_000
NS_MIN = 60 * NS
PRICE_SCALE = 1e9                # to_ndarray() entrega precios en punto fijo (enteros × 1e9)
F_BAD_TS_RECV = 8
UNDEF_PRICE = 9223372036854775807

# Raíz → (nombre, tamaño del tick, precio de referencia para la simulación)
CATALOGO = {
    "NQ": ("Nasdaq 100", 0.25, 20000.0), "MNQ": ("Micro Nasdaq 100", 0.25, 20000.0),
    "ES": ("S&P 500", 0.25, 5500.0), "MES": ("Micro S&P 500", 0.25, 5500.0),
    "YM": ("Dow Jones", 1.0, 42000.0), "MYM": ("Micro Dow", 1.0, 42000.0),
    "RTY": ("Russell 2000", 0.1, 2200.0), "M2K": ("Micro Russell", 0.1, 2200.0),
    "CL": ("Crudo WTI", 0.01, 75.0), "MCL": ("Micro crudo", 0.01, 75.0),
    "GC": ("Oro", 0.1, 2500.0), "MGC": ("Micro oro", 0.1, 2500.0),
    "ZN": ("Nota 10 años", 1 / 64, 110.0), "6E": ("Euro", 0.00005, 1.10),
}
DTYPE_TRADES = np.dtype([("ts_event", "<u8"), ("price", "<i8"), ("size", "<u4"), ("action", "S1"),
                         ("side", "S1"), ("flags", "u1"), ("instrument_id", "<u4")])


# =============================================================================
# 1. CONFIGURACIÓN
# =============================================================================
@dataclass(frozen=True)
class Config:
    # --- Datos ---
    dataset: str = "GLBX.MDP3"
    symbol: str = "NQ.n.0"
    stype_in: str = "continuous"
    start: str = "2026-06-01T00:00:00"      # UTC (tu Config)
    end: str = "2026-06-29T23:59:00"        # UTC, exclusivo
    tick_size: float | None = None          # None = del catálogo
    cache_dir: str = "datos_databento"
    salida_dir: str = "salidas_vpin"
    costo_max_usd: float = 25.0
    tam_bloque: int = 5_000_000             # registros por bloque (48 bytes c/u)
    tz_mercado: str = "America/Chicago"
    tz_local: str = "America/Mexico_City"

    # --- VPIN (Easley, López de Prado y O'Hara 2012) ---
    buckets_por_dia: int = 50               # V = volumen de una sesión típica / 50
    n_buckets: int = 50                     # ventana del VPIN ≈ una sesión de volumen
    volumen_bucket: int | None = None       # fíjalo para Live o para comparar corridas
    dias_calibracion: int = 5               # sesiones para estimar V (sin alertas en ese tramo)

    # --- Toxicidad relativa (percentil sin mirar al futuro) ---
    ventana_pct: int = 250                  # buckets previos (≈ 5 sesiones)
    min_obs_pct: int = 100
    umbral_pct: float = 0.90                # el artículo usa CDF(VPIN) > 0.9
    rearme_pct: float = 0.75                # histéresis
    cooldown_min: int = 120
    z_piso: float | None = 2.33             # piso de azar: VPIN ≥ azar + z·σ (None = sin piso)

    # --- Auditoría ---
    horizontes_min: tuple[int, ...] = (30, 60, 120, 240)
    rv_paso_min: int = 5                    # retornos de 5 min: sin el rebote bid-ask del último precio
    franja_min: int = 30                    # control por hora del día: franjas de 30 min
    min_obs_sesion: int = 15                # observaciones por sesión para su IC parcial
    bvc_ventana_min: int = 1380             # σ del cambio de precio de 1 min para BVC: una sesión
    reloj_tiempo_min: int = 60              # la comparación con reloj de TIEMPO (tu v1): barras de 1 h

    # --- Live ---
    dias_historial_live: int = 8

    # --- Simulación ---
    sim_sesiones: int = 30
    sim_trades: int = 40_000                # operaciones por sesión
    sim_prob_info: float = 0.5              # probabilidad de un evento de información por sesión
    sim_semilla: int = 0

    # --- Telegram ---
    telegram_live: bool = False


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


def raiz(symbol: str) -> str:
    m = re.match(r"[A-Za-z0-9]+?(?=[.]|[FGHJKMNQUVXZ]\d|$)", symbol)
    return (m.group(0) if m else symbol.split(".")[0]).upper()


def simbolo_continuo(s: str) -> str:
    s = s.strip()
    return s if "." in s else f"{s.upper()}.n.0"


def nombre(symbol: str) -> str:
    return CATALOGO.get(raiz(symbol), (raiz(symbol), 1.0, 100.0))[0]


def tick_de(cfg: Config) -> float:
    return cfg.tick_size or CATALOGO.get(raiz(cfg.symbol), ("", 1.0, 100.0))[1]


def validar(cfg: Config) -> None:
    if cfg.n_buckets < 10 or cfg.buckets_por_dia < 5:
        sys.exit("❌ Hacen falta al menos 10 buckets en la ventana y 5 por día.")
    if not (0.5 < cfg.rearme_pct < cfg.umbral_pct < 1.0):
        sys.exit("❌ La histéresis necesita 0.5 < rearme < umbral < 1.")
    if cfg.min_obs_pct > cfg.ventana_pct:
        sys.exit("❌ min_obs_pct no puede ser mayor que ventana_pct.")


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
    "  • La key de Databento NO va en el código: se lee de la variable DATABENTO_API_KEY\n"
    "    (tu vpin_cloud.py ya lo hacía así; se conserva).\n"
    "  • Si la regeneraste, la anterior ya no sirve: https://databento.com/docs/portal/api-keys\n"
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
    """Descarga UNA vez a disco (.dbn.zst), revisando el costo antes. La caché se reutiliza."""
    carpeta = _ruta(cfg.cache_dir)
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / (_nombre_seguro(cfg.dataset, cfg.symbol, cfg.start, cfg.end, "trades") + ".dbn.zst")
    if ruta.exists():
        print(f"📂 Usando caché local: {ruta.name}")
        return db.DBNStore.from_file(ruta)
    cliente = cliente or conectar()
    params = dict(dataset=cfg.dataset, symbols=cfg.symbol, stype_in=cfg.stype_in, schema="trades",
                  start=cfg.start, end=cfg.end)
    costo = cliente.metadata.get_cost(**params)
    print(f"💵 Costo estimado: US$ {costo:,.2f}  ({cfg.symbol}, trades, {cfg.start[:10]} → {cfg.end[:10]})")
    if costo > cfg.costo_max_usd:
        sys.exit(f"💰 El costo (US$ {costo:,.2f}) supera tu tope de US$ {cfg.costo_max_usd:,.2f}.\n"
                 f"   Si estás de acuerdo:  --costo-max {math.ceil(costo) + 1}")
    temporal = ruta.with_name(ruta.name + ".parcial")
    temporal.unlink(missing_ok=True)
    print(f"📡 Descargando trades a {ruta.name} …")
    descarga = cliente.timeseries.get_range(**params, path=temporal)
    del descarga                                # Windows no renombra archivos abiertos
    temporal.replace(ruta)
    return db.DBNStore.from_file(ruta)


def bloques(tienda, cfg: Config):
    """DBNStore → bloques de to_ndarray(); un arreglo estructurado → rebanadas del mismo tamaño."""
    if hasattr(tienda, "to_ndarray"):
        yield from tienda.to_ndarray(count=cfg.tam_bloque)
    else:
        for i in range(0, len(tienda), cfg.tam_bloque):
            yield tienda[i:i + cfg.tam_bloque]


# =============================================================================
# 3. HIGIENE Y MOTORES — el mismo cálculo, dos formas de ejecutarlo
# =============================================================================
# Reglas que comparten los dos motores:
#   R0  Sólo operaciones ('T') con tamaño > 0 y precio definido.
#   R1  side 'B' = +1 (COMPRA agresiva), 'A' = −1 (VENTA agresiva). 'N' (sin agresor: subasta de
#       apertura, operaciones implícitas) no entra a los buckets; se reporta aparte.
#   R2  Reloj de volumen: cada bucket junta exactamente V contratos; una operación grande se
#       reparte entre los buckets que toque y puede cerrar varios a la vez.
#   R3  oi = compras − ventas dentro del bucket.
#   R4  Tiempo monótono (máximo acumulado de ts_event); t_fin = operación que completa el
#       bucket: el momento en que el bucket se CONOCE.
#   R5  n_trades = operaciones que aportan al menos un contrato al bucket.
COLUMNAS_BUCKET = ["t_ini", "t_fin", "oi", "n_trades", "precio", "instrumento"]


def higiene(arr: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    """(operación válida, signo ±1/0, conteos). Las reglas R0-R1 en forma vectorial."""
    es_t = arr["action"] == b"T"
    tam = arr["size"].astype(np.int64)
    precio = arr["price"].astype(np.int64)
    malo = es_t & ((tam <= 0) | (precio <= 0) | (precio == UNDEF_PRICE))
    valido = es_t & ~malo
    signo = (arr["side"] == b"B").astype(np.int64) - (arr["side"] == b"A").astype(np.int64)
    sin_lado = valido & (signo == 0)
    conteo = {"registros": len(arr), "no_operacion": int((~es_t).sum()), "invalidas": int(malo.sum()),
              "sin_lado_n": int(sin_lado.sum()), "sin_lado_vol": int(tam[sin_lado].sum()),
              "operaciones": int(valido.sum()), "volumen": int(tam[valido].sum())}
    return valido, signo, conteo


class MotorVPIN:
    """
    Motor INCREMENTAL, operación por operación: replay de un DBN y Databento Live. Llama a
    `al_cerrar_bucket(fila)` en cuanto un bucket se completa. (Se conserva el de tu v2.)
    """

    def __init__(self, volumen_bucket: int, al_cerrar_bucket=None):
        self.V = int(volumen_bucket)
        if self.V <= 0:
            raise ValueError("volumen_bucket debe ser positivo")
        self.al_cerrar_bucket = al_cerrar_bucket
        self.sin_lado = 0
        self._ts_max = -1
        self._k = 0
        self._vol = 0
        self._oi = 0
        self._n = 0
        self._t_ini = 0
        self._filas: list[dict] = []

    def procesar(self, ts: int, accion: str, lado: str, tam: int, precio: int, instrumento: int) -> None:
        ts = int(ts)
        if ts < self._ts_max:                                   # R4
            ts = self._ts_max
        self._ts_max = ts
        tam, precio = int(tam), int(precio)
        if accion != "T" or tam <= 0 or precio <= 0 or precio == UNDEF_PRICE:     # R0
            return
        if lado == "B":
            s = 1
        elif lado == "A":
            s = -1
        else:
            self.sin_lado += tam
            return
        restante = tam
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
                        "n_trades": self._n, "precio": precio, "instrumento": int(instrumento)}
                self._filas.append(fila)
                self._vol = self._oi = 0
                if self.al_cerrar_bucket is not None:
                    self.al_cerrar_bucket(fila)

    def procesar_registro(self, r) -> None:
        """Un registro de databento (TradeMsg o MBP1Msg)."""
        self.procesar(r.ts_event, str(r.action), str(r.side), r.size, r.price, r.instrument_id)

    def buckets(self) -> pd.DataFrame:
        return tabla_buckets(self._filas)


def tabla_buckets(filas) -> pd.DataFrame:
    df = pd.DataFrame(filas, columns=["k"] + COLUMNAS_BUCKET)
    df = df.astype({"k": np.int64, "t_ini": np.int64, "t_fin": np.int64, "oi": np.int64,
                    "n_trades": np.int64, "precio": np.float64, "instrumento": np.int64})
    df["precio"] = df["precio"] / PRICE_SCALE
    for col in ("t_ini", "t_fin"):
        df[col] = pd.to_datetime(df[col], utc=True)
    return df.set_index("k")


@dataclass
class _Arrastre:
    C: int = 0                  # volumen clasificado acumulado antes del bloque
    D: int = 0                  # compras − ventas acumuladas antes del bloque
    g: int = 0                  # operaciones clasificadas antes del bloque
    k: int = 0                  # buckets cerrados
    D_lim: int = 0              # D exactamente en el último límite k·V
    ts_max: int = -1
    t_ini: int | None = None
    i_ini: int | None = None
    sin_lado: int = 0


def _bloque_buckets(arr: np.ndarray, c: _Arrastre, V: int) -> pd.DataFrame | None:
    """
    Motor VECTORIZADO: curvas acumuladas de volumen C y desbalance D. Entre operaciones D es
    lineal en C, así que D en cualquier límite L = k·V sale exacto aunque una operación cruce
    varios límites. (Es el algoritmo de tu v2.)
    """
    ts = arr["ts_event"].astype(np.int64)
    ts[0] = max(int(ts[0]), c.ts_max)
    ts = np.maximum.accumulate(ts)                                          # R4
    c.ts_max = int(ts[-1])
    valido, signo, conteo = higiene(arr)
    c.sin_lado += conteo["sin_lado_vol"]
    m = valido & (signo != 0)                                               # R0-R1
    if not m.any():
        return None
    ts, s, tam = ts[m], signo[m], arr["size"][m].astype(np.int64)
    precio, iid = arr["price"][m], arr["instrument_id"][m]
    n = len(tam)
    C = c.C + np.cumsum(tam)
    D = c.D + np.cumsum(s * tam)
    C_prev = np.concatenate(([c.C], C[:-1]))
    D_prev = np.concatenate(([c.D], D[:-1]))
    filas = None
    k_fin = int(C[-1] // V)
    if k_fin > c.k:
        kk = np.arange(c.k + 1, k_fin + 1, dtype=np.int64)
        L = kk * V
        i = np.searchsorted(C, L, side="left")
        D_L = D_prev[i] + s[i] * (L - C_prev[i])
        oi = D_L - np.concatenate(([c.D_lim], D_L[:-1]))                  # R3
        j = np.searchsorted(C, L - V, side="right")
        abrio_antes = (L - V) < c.C
        t_ini = np.where(abrio_antes, c.t_ini if c.t_ini is not None else 0, ts[np.minimum(j, n - 1)])
        i_ini = np.where(abrio_antes, c.i_ini if c.i_ini is not None else 0, c.g + j)
        filas = pd.DataFrame({"k": kk, "t_ini": t_ini, "t_fin": ts[i], "oi": oi,
                              "n_trades": c.g + i - i_ini + 1,                # R5
                              "precio": precio[i], "instrumento": iid[i]})
        c.D_lim = int(D_L[-1])
    L_abierto = k_fin * V
    if C[-1] > L_abierto:
        if L_abierto >= c.C:
            j = int(np.searchsorted(C, L_abierto, side="right"))
            c.t_ini, c.i_ini = int(ts[j]), c.g + j
    else:
        c.t_ini = c.i_ini = None
    c.k = k_fin
    c.C, c.D, c.g = int(C[-1]), int(D[-1]), c.g + n
    return filas


def buckets_vectorizado(tienda, V: int, cfg: Config) -> tuple[pd.DataFrame, int]:
    c = _Arrastre()
    partes = [f for f in (_bloque_buckets(a, c, int(V)) for a in bloques(tienda, cfg) if len(a)) if f is not None]
    filas = pd.concat(partes, ignore_index=True) if partes else []
    return tabla_buckets(filas), c.sin_lado


def buckets_incremental(tienda, V: int, cfg: Config) -> tuple[pd.DataFrame, int]:
    m = MotorVPIN(V)
    for arr in bloques(tienda, cfg):
        for r in arr:
            m.procesar(r["ts_event"], r["action"].decode(), r["side"].decode(), r["size"], r["price"],
                       r["instrument_id"])
    return m.buckets(), m.sin_lado


def procesar_buckets(tienda, V: int, cfg: Config, motor: str = "vectorizado") -> tuple[pd.DataFrame, int]:
    return (buckets_incremental if motor == "incremental" else buckets_vectorizado)(tienda, V, cfg)


# =============================================================================
# 4. MINUTOS, SESIONES Y CALIBRACIÓN
# =============================================================================
def fecha_sesion(t_ns: np.ndarray, tz: str) -> np.ndarray:
    """Fecha de la sesión de Globex: hora de Chicago + 7 h (la sesión abre 17:00 CT)."""
    idx = pd.DatetimeIndex(np.asarray(t_ns, np.int64), tz="UTC")
    return (idx.tz_convert(tz).tz_localize(None) + pd.Timedelta(hours=DESFASE_H)).normalize().to_numpy()


def minutos_y_sesiones(tienda, cfg: Config) -> tuple[pd.DataFrame, pd.Series, dict]:
    """
    Una pasada: por minuto (UTC) el último precio, el volumen, las compras y ventas agresivas
    y el número de operaciones; el volumen por sesión; y los conteos de la higiene. También el
    chequeo del agresor: el precio medio de las compras menos el de las ventas en el mismo
    segundo (debe ser positivo: se compra en el ask y se vende en el bid).
    """
    partes, sesiones = [], []
    tot = {}
    dif, n_dif = 0.0, 0
    ts_max = -1
    for arr in bloques(tienda, cfg):
        if not len(arr):
            continue
        ts = arr["ts_event"].astype(np.int64)
        ts[0] = max(int(ts[0]), ts_max)
        ts = np.maximum.accumulate(ts)
        ts_max = int(ts[-1])
        valido, signo, conteo = higiene(arr)
        for k, v in conteo.items():
            tot[k] = tot.get(k, 0) + v
        if not valido.any():
            continue
        t, s = ts[valido], signo[valido]
        q = arr["size"][valido].astype(np.int64)
        p = arr["price"][valido].astype(np.int64) / PRICE_SCALE
        seg = t // NS
        # chequeo del agresor, segundo a segundo
        d = pd.DataFrame({"seg": seg, "s": s, "p": p})
        g = d[d["s"] != 0].groupby(["seg", "s"])["p"].mean().unstack()
        if 1 in g and -1 in g:
            ambos = g.dropna()
            dif += float((ambos[1] - ambos[-1]).sum())
            n_dif += len(ambos)
        mn = t // NS_MIN
        partes.append(pd.DataFrame({"minuto": mn, "precio": p, "volumen": q,
                                    "compras": np.where(s > 0, q, 0), "ventas": np.where(s < 0, q, 0),
                                    "q2": np.where(s != 0, q * q, 0),
                                    "instrumento": arr["instrument_id"][valido].astype(np.int64)})
                      .groupby("minuto").agg(precio=("precio", "last"), volumen=("volumen", "sum"),
                                             compras=("compras", "sum"), ventas=("ventas", "sum"),
                                             q2=("q2", "sum"), n=("volumen", "size"),
                                             instrumento=("instrumento", "last")))
        sesiones.append(pd.Series(q, index=fecha_sesion(t, cfg.tz_mercado)).groupby(level=0).sum())
    if not partes:
        sys.exit("❌ No llegaron operaciones.")
    todo = pd.concat(partes)
    g = todo.groupby(level=0)
    M = pd.DataFrame({"precio": g["precio"].last(), "volumen": g["volumen"].sum(), "compras": g["compras"].sum(),
                      "ventas": g["ventas"].sum(), "q2": g["q2"].sum(), "n": g["n"].sum(),
                      "instrumento": g["instrumento"].last()})
    M.index = pd.to_datetime(M.index.to_numpy(np.int64) * NS_MIN, utc=True)
    M.index.name = "minuto"
    vol = pd.concat(sesiones).groupby(level=0).sum()
    tot["agresor_dif_ticks"] = dif / n_dif / tick_de(cfg) if n_dif else np.nan
    tot["agresor_segundos"] = n_dif
    return M, vol, tot


def calibrar(vol: pd.Series, cfg: Config) -> tuple[int, pd.Timestamp | None]:
    """
    V = mediana del volumen de las primeras `dias_calibracion` sesiones / buckets_por_dia. Las
    alertas y la auditoría empiezan cuando cierran esas sesiones: V no usa información futura.
    """
    if cfg.volumen_bucket:
        return int(cfg.volumen_bucket), None
    if vol.empty:
        sys.exit("❌ No hay operaciones para calibrar el tamaño del bucket.")
    k = min(cfg.dias_calibracion, len(vol))
    if k == len(vol):
        print("⚠ Hay pocas sesiones: todo el rango se usa para calibrar V y no queda tramo para "
              "alertas ni auditoría. Descarga más días o fija --volumen-bucket.")
    V = max(1, int(round(float(vol.iloc[:k].median()) / cfg.buckets_por_dia)))
    fin = (pd.Timestamp(vol.index[k - 1]) + pd.Timedelta(hours=16)).tz_localize(cfg.tz_mercado).tz_convert("UTC")
    return V, fin


@dataclass(frozen=True)
class Azar:
    """El VPIN que daría un mercado donde el lado de cada operación fuera una MONEDA."""
    kappa: float                # Σq² / Σq: tamaño medio de operación ponderado por volumen
    media: float                # √(2κ / (π·V))
    sd: float                   # √((1 − 2/π)·κ / (V·n))
    piso: float                 # media + z·sd (−∞ sin piso)


def texto_piso(azar: Azar) -> str:
    return f"{azar.piso:.4f}" if np.isfinite(azar.piso) else "apagado (--sin-piso)"


def piso_azar(M: pd.DataFrame, V: int, cfg: Config, hasta: pd.Timestamp | None = None) -> Azar:
    """
    Con signos al azar, el oi de un bucket es una suma de ±q con varianza Σq² = κ·V, así que
    E|oi| = √(2/π)·√(κV) y el VPIN "de pura moneda" es √(2κ/(πV)), con desviación
    √((1 − 2/π)·κ/(V·n)) en la ventana de n buckets. Depende de V: con buckets chicos el azar
    solo ya da un VPIN alto. κ sale de las sesiones de calibración (nada del futuro).
    """
    m = M if hasta is None or not (M.index < hasta).any() else M[M.index < hasta]
    firmado = float((m["compras"] + m["ventas"]).sum())
    kappa = float(m["q2"].sum()) / firmado if firmado > 0 else 1.0
    media = math.sqrt(2 * kappa / (math.pi * V))
    sd = math.sqrt((1 - 2 / math.pi) * kappa / (V * cfg.n_buckets))
    piso = media + cfg.z_piso * sd if cfg.z_piso is not None else -math.inf
    return Azar(kappa, media, sd, piso)


# =============================================================================
# 5. VPIN (exacto, BVC y de reloj de tiempo), PERCENTIL Y ALERTAS
# =============================================================================
def percentil_movil(x: pd.Series | np.ndarray, ventana: int, min_obs: int) -> np.ndarray:
    """Percentil de x_t dentro de x_{t−W} … x_{t−1} (rango medio en empates). Sin mirar al futuro."""
    from numpy.lib.stride_tricks import sliding_window_view
    v = np.asarray(x, dtype=np.float64)
    if len(v) == 0:
        return v.copy()
    ref = sliding_window_view(np.concatenate((np.full(ventana, np.nan), v)), ventana)[: len(v)]
    actual = v[:, None]
    validos = np.sum(~np.isnan(ref), axis=1)
    pct = (np.sum(ref < actual, axis=1) + 0.5 * np.sum(ref == actual, axis=1)) / np.where(validos > 0, validos, 1)
    pct = pct.astype(float)
    pct[(validos < min_obs) | np.isnan(v)] = np.nan
    return pct


def calcular_vpin(buckets: pd.DataFrame, V: int, cfg: Config, azar: Azar | None = None) -> pd.DataFrame:
    df = buckets.copy()
    n = cfg.n_buckets
    df["compras"] = (V + df["oi"]) // 2
    df["ventas"] = V - df["compras"]
    df["vpin"] = df["oi"].abs().rolling(n, min_periods=n).sum() / (n * V)
    df["desbalance"] = df["oi"].rolling(n, min_periods=n).sum() / (n * V)
    df["vpin_pct"] = percentil_movil(df["vpin"], cfg.ventana_pct, cfg.min_obs_pct)
    df["duracion_min"] = (df["t_fin"] - df["t_ini"]).dt.total_seconds() / 60
    df["minutos_ventana"] = (df["t_fin"] - df["t_ini"].shift(n - 1)).dt.total_seconds() / 60
    df["exceso"] = df["vpin"] / azar.media if azar is not None else np.nan
    return df


def fraccion_bvc(M: pd.DataFrame, cfg: Config) -> np.ndarray:
    """Φ(ΔP/σ) por barra de 1 min, con σ de las barras ANTERIORES (0.5 si no hay cómo saberlo)."""
    p = M["precio"].to_numpy()
    ins = M["instrumento"].to_numpy()
    dp = np.r_[np.nan, np.diff(p)]
    dp[np.r_[True, ins[1:] != ins[:-1]]] = np.nan
    sd = pd.Series(dp).rolling(cfg.bvc_ventana_min, min_periods=120).std().shift(1).to_numpy()
    z = np.where(sd > 0, dp / sd, np.nan)
    phi = NormalDist().cdf
    return np.array([phi(v) if np.isfinite(v) else 0.5 for v in z])


def acierto_bvc(M: pd.DataFrame, cfg: Config) -> float:
    """Fracción del volumen al que la BVC le atina el lado, medida contra el agresor de CME."""
    firmado = (M["compras"] + M["ventas"]).to_numpy(float)
    error = np.abs(firmado * fraccion_bvc(M, cfg) - M["compras"].to_numpy(float)).sum()
    return 1 - error / firmado.sum() if firmado.sum() > 0 else np.nan


def vpin_bvc(M: pd.DataFrame, V: int, cfg: Config) -> pd.DataFrame:
    """
    El VPIN ORIGINAL de Easley, López de Prado y O'Hara (2012) con clasificación en bloque (BVC):
    cada barra de 1 min reparte su volumen en compras = V_barra · Φ(ΔP / σ_ΔP), con σ de las
    barras ANTERIORES; luego los mismos buckets de V contratos. Sirve para medir qué aporta
    conocer el agresor exacto: la BVC deduce el lado del cambio de PRECIO, así que su
    desbalance ya trae adentro el movimiento del precio.
    """
    frac = fraccion_bvc(M, cfg)
    vol = M["volumen"].to_numpy(np.int64)
    s_equiv = 2 * frac - 1                               # desbalance por contrato de la barra
    C = np.cumsum(vol).astype(float)
    D = np.cumsum(vol * s_equiv)
    C_prev, D_prev = np.r_[0.0, C[:-1]], np.r_[0.0, D[:-1]]
    k_fin = int(C[-1] // V)
    L = np.arange(1, k_fin + 1) * float(V)
    i = np.searchsorted(C, L, side="left")
    D_L = D_prev[i] + s_equiv[i] * (L - C_prev[i])
    oi = np.diff(np.r_[0.0, D_L])
    n = cfg.n_buckets
    t_fin = M.index[i] + pd.Timedelta(minutes=1)
    out = pd.DataFrame({"t_fin": t_fin, "oi": oi}, index=pd.RangeIndex(1, k_fin + 1, name="k"))
    out["vpin"] = pd.Series(np.abs(oi)).rolling(n, min_periods=n).sum().to_numpy() / (n * V)
    out["vpin_pct"] = percentil_movil(out["vpin"], cfg.ventana_pct, cfg.min_obs_pct)
    return out


def vpin_reloj_tiempo(M: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """
    Tu v1: barras de reloj de TIEMPO (1 h) con |compras − ventas| / volumen, promediado sobre
    las últimas 24 barras. Con n contratos de lado al azar, |c − v| / n ≈ √(2κ / (π·n)) (κ =
    Σq²/Σq, como en el piso de azar): las horas tranquilas salen "tóxicas" sólo por tener poco
    volumen. Se calcula para medirlo.
    """
    h = cfg.reloj_tiempo_min
    g = M.resample(f"{h}min")
    H = pd.DataFrame({"compras": g["compras"].sum(), "ventas": g["ventas"].sum(), "q2": g["q2"].sum(),
                      "n": g["n"].sum()})
    H = H[(H["compras"] + H["ventas"]) > 0]
    firmado = H["compras"] + H["ventas"]
    H["tox"] = (H["compras"] - H["ventas"]).abs() / firmado
    H["vpin"] = H["tox"].rolling(24, min_periods=24).mean()
    H["esperado_azar"] = np.sqrt(2 * (H["q2"] / firmado) / (np.pi * firmado))
    H["t_fin"] = H.index + pd.Timedelta(minutes=h)
    return H


class DetectorToxicidad:
    """Una alerta por episodio: dispara al cruzar el umbral y se rearma al bajar de `rearme`.
    Un cruce dentro del cooldown se consume sin avisar. (El de tu v2.) [v3] Además el VPIN debe
    superar el piso de azar: un percentil alto con un VPIN que una moneda también daría no es
    toxicidad, es una racha tranquila que se volvió un poco menos tranquila."""

    def __init__(self, umbral: float, rearme: float, cooldown_ns: int, piso: float = -math.inf):
        self.umbral, self.rearme, self.cooldown_ns, self.piso = umbral, rearme, cooldown_ns, piso
        self.armado = True
        self.t_ultimo: int | None = None

    def actualizar(self, t_ns: int, p: float, vpin: float = math.inf) -> bool:
        if p is None or not np.isfinite(p):
            return False
        if p <= self.rearme:
            self.armado = True
        if p >= self.umbral and vpin >= self.piso and self.armado:
            self.armado = False
            if self.t_ultimo is None or t_ns - self.t_ultimo >= self.cooldown_ns:
                self.t_ultimo = t_ns
                return True
        return False


def detectar_alertas(df: pd.DataFrame, cfg: Config, t_senales: pd.Timestamp | None,
                     piso: float = -math.inf) -> pd.DataFrame:
    det = DetectorToxicidad(cfg.umbral_pct, cfg.rearme_pct, cfg.cooldown_min * NS_MIN, piso)
    desde = t_senales.value if t_senales is not None else -1
    filas = []
    for k, t, p, v in zip(df.index, df["t_fin"].astype("int64").to_numpy(), df["vpin_pct"].to_numpy(),
                          df["vpin"].to_numpy()):
        if det.actualizar(int(t), float(p), float(v)) and t >= desde:
            filas.append(k)
    al = df.loc[filas, ["t_fin", "vpin", "vpin_pct", "desbalance", "precio"]].copy()
    al["lado"] = np.where(al["desbalance"] >= 0, "compras", "ventas")
    return al


# =============================================================================
# 6. AUDITORÍA — ¿el VPIN anticipa algo MÁS ALLÁ de lo obvio?
# =============================================================================
class Rejilla:
    """
    Precios en una rejilla de 1 min con sumas acumuladas. La volatilidad realizada usa
    retornos de `paso` minutos (5 por omisión), en fase con el punto de evaluación.

    [v2] Tu evaluación usa retornos de 1 min del ÚLTIMO PRECIO operado. Ese precio rebota
    entre el bid y el ask: en el NQ un tick es ~1.2 pb, del orden de un retorno de 1 min en
    las horas quietas, así que ahí la RV puede salir inflada por el rebote (el tablero mide
    cuánto, hora por hora). Con retornos de 5 min el rebote pesa 5 veces menos.
    """

    def __init__(self, M: pd.DataFrame, cfg: Config):
        self.paso = int(cfg.rv_paso_min)
        idx = pd.date_range(M.index[0], M.index[-1], freq="1min")
        self.t0 = idx[0].value
        self.n = len(idx)
        p = M["precio"].reindex(idx).ffill(limit=self.paso)
        ins = M["instrumento"].reindex(idx).ffill(limit=self.paso)
        lp = np.log(p.to_numpy())
        k = self.paso
        r = np.full(self.n, np.nan)
        r[k:] = lp[k:] - lp[:-k]
        mismo = np.zeros(self.n, bool)
        mismo[k:] = ins.to_numpy()[k:] == ins.to_numpy()[:-k]
        r[~mismo] = np.nan
        q = np.nan_to_num(r * r)
        ok = np.isfinite(r).astype(float)
        # sumas acumuladas por fase: cs[t] = q[t] + cs[t − paso]
        self.cs_q = q.copy()
        self.cs_ok = ok.copy()
        for t in range(k, self.n):
            self.cs_q[t] += self.cs_q[t - k]
            self.cs_ok[t] += self.cs_ok[t - k]
        self.cs_vol = np.r_[0.0, np.cumsum(M["volumen"].reindex(idx).fillna(0).to_numpy())]
        self.precio = p.to_numpy()
        self.ins = ins.to_numpy()

    def minuto_de(self, t_ns: np.ndarray) -> np.ndarray:
        return (np.asarray(t_ns, np.int64) // NS_MIN * NS_MIN - self.t0) // NS_MIN

    def rv(self, m0: np.ndarray, h: int, futuro: bool) -> np.ndarray:
        """Volatilidad realizada en pb: futuro = (m0, m0 + h], pasado = (m0 − h, m0]."""
        a, b = (m0, m0 + h) if futuro else (m0 - h, m0)
        ok = (a >= 0) & (b < self.n)
        a2, b2 = np.clip(a, 0, self.n - 1), np.clip(b, 0, self.n - 1)
        q = self.cs_q[b2] - self.cs_q[a2]
        c = (self.cs_ok[b2] - self.cs_ok[a2]) / (h / self.paso)
        return np.where(ok & (c >= 0.8), np.sqrt(np.maximum(q, 0)) * 1e4, np.nan)

    def volumen_pasado(self, m0: np.ndarray, h: int) -> np.ndarray:
        a, b = m0 - h, m0
        ok = (a >= 0) & (b < self.n)
        a2, b2 = np.clip(a, 0, self.n - 1), np.clip(b, 0, self.n - 1)
        return np.where(ok, self.cs_vol[b2] - self.cs_vol[a2], np.nan)

    def retorno(self, m0: np.ndarray, base: np.ndarray, h: int, tick: float) -> np.ndarray:
        b = m0 + h
        ok = (m0 >= 0) & (b < self.n)
        b2 = np.clip(b, 0, self.n - 1)
        m2 = np.clip(m0, 0, self.n - 1)
        mismo = self.ins[b2] == self.ins[m2]
        return np.where(ok & mismo & np.isfinite(self.precio[b2]), (self.precio[b2] - base) / tick, np.nan)


def _rangos(x: np.ndarray) -> np.ndarray:
    return pd.Series(x).rank().to_numpy()


def spearman(x, y) -> tuple[float, int]:
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 30:
        return np.nan, int(m.sum())
    return float(np.corrcoef(_rangos(x[m]), _rangos(y[m]))[0, 1]), int(m.sum())


def spearman_parcial(x, y, controles, minimo: int = 30) -> tuple[float, int]:
    """Correlación de rangos entre x e y quitando lo que explican los controles (en rangos)."""
    m = np.isfinite(x) & np.isfinite(y)
    for z in controles:
        m &= np.isfinite(z)
    if m.sum() < max(minimo, len(controles) + 5):
        return np.nan, int(m.sum())
    rx, ry = _rangos(x[m]), _rangos(y[m])
    Z = np.column_stack([np.ones(int(m.sum()))] + [_rangos(z[m]) for z in controles])
    ex = rx - Z @ np.linalg.lstsq(Z, rx, rcond=None)[0]
    ey = ry - Z @ np.linalg.lstsq(Z, ry, rcond=None)[0]
    return float(np.corrcoef(ex, ey)[0, 1]), int(m.sum())


def rv_tipica(rej: Rejilla, t_ns: np.ndarray, h: int, cfg: Config) -> np.ndarray:
    """
    Control por HORA DEL DÍA: la volatilidad futura típica de esa franja de 30 min, promediada
    sólo en sesiones ANTERIORES. Sin él, cualquier cosa que suba en la apertura de Nueva York
    "anticipa" volatilidad.
    """
    minutos = np.arange(rej.n)
    t_min = rej.t0 + minutos * NS_MIN
    ses = fecha_sesion(t_min, cfg.tz_mercado)
    pared = pd.DatetimeIndex(t_min, tz="UTC").tz_convert(cfg.tz_mercado).tz_localize(None) + pd.Timedelta(hours=DESFASE_H)
    ms = ((pared.asi8 - pared.normalize().asi8) // NS_MIN).astype(int)
    inicio = ms % cfg.franja_min == 0
    fut = rej.rv(minutos[inicio], h, True)
    T = pd.DataFrame({"ses": ses[inicio], "franja": ms[inicio] // cfg.franja_min, "rv": fut})
    P = T.pivot_table(index="ses", columns="franja", values="rv", aggfunc="mean").sort_index()
    tipica = P.expanding().mean().shift(1)                     # sólo sesiones anteriores
    m0 = rej.minuto_de(t_ns)
    m0c = np.clip(m0, 0, rej.n - 1)
    s_e, f_e = ses[m0c], ms[m0c] // cfg.franja_min
    fila = tipica.index.get_indexer(pd.DatetimeIndex(s_e))
    col = tipica.columns.get_indexer(f_e)
    A = tipica.to_numpy()
    ok = (fila >= 0) & (col >= 0)
    out = np.full(len(m0), np.nan)
    out[ok] = A[fila[ok], col[ok]]
    return out


def _beta_inc(a: float, b: float, x: float) -> float:
    """Beta incompleta regularizada I_x(a, b) por fracción continua (Lentz)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    if x > (a + 1) / (a + b + 2):
        return 1.0 - _beta_inc(b, a, 1 - x)
    ln = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    diminuto = 1e-300
    c, d = 1.0, 1.0 - (a + b) * x / (a + 1)
    d = 1 / (d if abs(d) > diminuto else diminuto)
    f = d
    for m in range(1, 300):
        for num in (m * (b - m) * x / ((a + 2 * m - 1) * (a + 2 * m)),
                    -(a + m) * (a + b + m) * x / ((a + 2 * m) * (a + 2 * m + 1))):
            d = 1 + num * d
            d = 1 / (d if abs(d) > diminuto else diminuto)
            c = 1 + num / c
            c = c if abs(c) > diminuto else diminuto
            f *= c * d
        if abs(c * d - 1) < 1e-14:
            break
    return math.exp(ln) * f / a


def p_t(t: float, gl: int) -> float:
    """p bilateral de la t de Student con `gl` grados de libertad (exacta, sin scipy)."""
    if not np.isfinite(t):
        return 0.0 if np.isinf(t) else np.nan
    return _beta_inc(gl / 2, 0.5, gl / (gl + t * t))


def _t_cuantil(q: float, gl: int) -> float:
    """Cuantil q (> 0.5) de la t de Student, por bisección sobre p_t."""
    lo, hi = 0.0, 1e3
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if p_t(mid, gl) / 2 > 1 - q else (lo, mid)
    return (lo + hi) / 2


def prueba_parcial(x, y, controles, ses, cfg: Config) -> dict:
    """
    IC parcial POR SESIÓN y prueba t entre sesiones (Fama y MacBeth 1973): cada sesión aporta
    un IC; la media es el efecto y su dispersión entre sesiones, el error. La volatilidad y el
    VPIN son persistentes de un día a otro; comparar dentro de cada sesión quita ese factor
    diario común y las sesiones quedan como observaciones casi independientes.

    [v2] Tu t usa n_eff = min(n, minutos/h) con todos los buckets juntos. En 20 simulaciones SIN
    flujo informado (× 4 horizontes) da p < 0.10 en 25 % de los casos en vez de 10 %; un placebo
    de desplazamiento circular, que también se probó, 31 % a 60 min. La persistencia de un día a
    otro finge señal (Granger y Newbold 1974). Con sesiones como unidad: 5 %.
    """
    ic, n = spearman_parcial(x, y, controles)
    out = {"ic_agrupado": ic, "n": n, "ic": np.nan, "p": np.nan, "lo": np.nan, "hi": np.nan,
           "sesiones": 0, "positivas": np.nan, "por_sesion": np.array([])}
    ses_u, ses_i = np.unique(ses, return_inverse=True)
    por = []
    for k in range(len(ses_u)):
        m = ses_i == k
        r, n_k = spearman_parcial(x[m], y[m], [z[m] for z in controles], cfg.min_obs_sesion)
        if n_k >= cfg.min_obs_sesion and np.isfinite(r):
            por.append(r)
    por = np.array(por)
    out["por_sesion"] = por
    S = len(por)
    if S >= 5:
        media, ee = float(por.mean()), float(por.std(ddof=1) / math.sqrt(S))
        t = media / ee if ee > 0 else np.inf
        tq = _t_cuantil(0.95, S - 1)
        out.update(ic=media, p=p_t(t, S - 1), lo=media - tq * ee, hi=media + tq * ee,
                   sesiones=S, positivas=float(np.mean(por > 0)))
    return out


@dataclass
class Auditoria:
    ic: pd.DataFrame            # variante × horizonte
    mecanica: dict
    eventos: pd.DataFrame
    direccion: pd.DataFrame
    por_sesion: dict            # (variante, h) → IC parcial de cada sesión
    paridad: dict | None
    cordura: list


def auditar(df: pd.DataFrame, bvc: pd.DataFrame, tiempo: pd.DataFrame, alertas: pd.DataFrame,
            M: pd.DataFrame, cfg: Config, t_senales: pd.Timestamp | None, conteo: dict,
            paridad_: dict | None) -> Auditoria:
    rej = Rejilla(M, cfg)
    desde = t_senales if t_senales is not None else df["t_fin"].min()
    variantes = {
        "VPIN (agresor exacto)": (df[df["t_fin"] >= desde], "vpin_pct"),
        "VPIN BVC (ELO 2012)": (bvc[bvc["t_fin"] >= desde], "vpin_pct"),
        "reloj de tiempo (tu v1)": (tiempo[tiempo["t_fin"] >= desde].assign(
            vpin_pct=lambda d: percentil_movil(d["vpin"], 120, 48)), "vpin_pct"),
    }
    filas, por_sesion = [], {}
    for nombre_, (ev, col) in variantes.items():
        ev = ev[np.isfinite(ev[col])]
        if len(ev) < 60:
            continue
        t_ns = ev["t_fin"].astype("int64").to_numpy()
        m0 = rej.minuto_de(t_ns)
        x = ev[col].to_numpy(float)
        ses = fecha_sesion(t_ns, cfg.tz_mercado)
        for h in cfg.horizontes_min:
            fut = rej.rv(m0, h, True)
            pas = rej.rv(m0, h, False)
            vol = np.log1p(rej.volumen_pasado(m0, h))
            tip = rv_tipica(rej, t_ns, h, cfg)
            ic, n = spearman(x, fut)
            ic2 = spearman_parcial(x, fut, [pas, vol])[0]
            pr = prueba_parcial(x, fut, [pas, vol, tip], ses, cfg)
            por_sesion[(nombre_, h)] = pr["por_sesion"]
            filas.append({"variante": nombre_, "h_min": h, "n": n, "IC": ic,
                          "IC_vol_pasada": spearman(pas, fut)[0], "IC_parcial_tu": ic2,
                          "IC_parcial_agrupado": pr["ic_agrupado"], "IC_parcial": pr["ic"], "lo": pr["lo"],
                          "hi": pr["hi"], "p": pr["p"], "sesiones": pr["sesiones"], "positivas": pr["positivas"]})
    ic = pd.DataFrame(filas)
    # --- relación mecánica con la actividad ---
    ev = df[df["vpin"].notna()]
    mec = {"volumen": spearman(ev["vpin"].to_numpy(), ev["minutos_ventana"].to_numpy())[0],
           "tox_bucket_vs_duracion": spearman((ev["oi"].abs()).to_numpy(float), ev["duracion_min"].to_numpy())[0],
           "tiempo": spearman(tiempo["tox"].to_numpy(), tiempo["esperado_azar"].to_numpy())[0]}
    # --- estudio de eventos, contra la hora del día ---
    filas = []
    ev = df[df["vpin"].notna() & (df["t_fin"] >= desde)]
    m_all = rej.minuto_de(ev["t_fin"].astype("int64").to_numpy())
    if len(alertas):
        t_al = alertas["t_fin"].astype("int64").to_numpy()
        m_al = rej.minuto_de(t_al)
        for h in cfg.horizontes_min:
            fut_al = rej.rv(m_al, h, True)
            tip_al = rv_tipica(rej, t_al, h, cfg)
            fut_all = rej.rv(m_all, h, True)
            ok = np.isfinite(fut_al) & np.isfinite(tip_al)
            filas.append({"h_min": h, "n": int(ok.sum()),
                          "vs_tipico": np.nanmean(fut_al) / np.nanmean(fut_all),
                          "vs_misma_hora": float(np.nanmedian(fut_al[ok] / tip_al[ok])) if ok.any() else np.nan,
                          "vs_pasada": float(np.nanmedian(fut_al / rej.rv(m_al, h, False)))})
    eventos = pd.DataFrame(filas)
    # --- dirección ---
    filas = []
    tick = tick_de(cfg)
    for h in cfg.horizontes_min:
        ret = rej.retorno(m_all, ev["precio"].to_numpy(), h, tick)
        r_, n_ = spearman(ev["desbalance"].to_numpy(), ret)
        filas.append({"h_min": h, "n": n_, "IC": r_})
    direccion = pd.DataFrame(filas)
    # --- chequeo de cordura ---
    c = []
    tot = max(1, conteo.get("volumen", 0))
    c.append((conteo.get("agresor_dif_ticks", np.nan) > 0,
              f"el agresor tiene el sentido correcto: en el mismo segundo las compras agresivas se "
              f"hacen {conteo.get('agresor_dif_ticks', np.nan):+.2f} ticks arriba de las ventas "
              f"({conteo.get('agresor_segundos', 0):,} segundos)"))
    c.append((conteo.get("sin_lado_vol", 0) / tot < 0.05,
              f"volumen sin agresor (side N): {conteo.get('sin_lado_vol', 0) / tot:.2%}"))
    c.append((conteo.get("invalidas", 0) == 0, f"operaciones con tamaño 0 o precio inválido: {conteo.get('invalidas', 0):,}"))
    c.append((mec["tox_bucket_vs_duracion"] < 0.1,
              f"los buckets lentos no salen más tóxicos: Spearman(|oi| del bucket, minutos que tardó) "
              f"{mec['tox_bucket_vs_duracion']:+.2f} (con reloj de tiempo sería claramente positivo)"))
    if paridad_ is not None:
        c.append((paridad_["igual"], f"motor incremental = vectorizado en {paridad_['operaciones']:,} operaciones "
                                     f"({paridad_['buckets']:,} buckets idénticos)"))
    return Auditoria(ic, mec, eventos, direccion, por_sesion, paridad_, c)


def paridad(tienda, V: int, cfg: Config, maximo: int = 300_000) -> dict:
    """Corre los dos motores sobre las primeras `maximo` operaciones y exige buckets idénticos."""
    arr = next(iter(bloques(tienda, replace(cfg, tam_bloque=maximo))))
    a, sa = buckets_vectorizado(arr, V, replace(cfg, tam_bloque=max(1, maximo // 7)))
    b, sb = buckets_incremental(arr, V, cfg)
    igual = len(a) == len(b) and sa == sb and (len(a) == 0 or bool((a.to_numpy() == b.to_numpy()).all()))
    return {"operaciones": len(arr), "buckets": len(a), "igual": igual}


# =============================================================================
# 7. SIMULADOR — un mercado con flujo informado CONOCIDO
# =============================================================================
def perfil_actividad(minuto: np.ndarray) -> np.ndarray:
    m = np.asarray(minuto)
    p = np.where(m < 540, 0.45, 1.0)                           # 17:00-02:00 CT: Asia
    p = np.where((m >= 930) & (m < 1335), 3.0, p)              # 08:30-15:15 CT
    p = np.where((m >= 930) & (m < 945), 6.0, p)               # la apertura
    return np.where(m >= 1335, 0.6, p)


def simular(cfg: Config, sesiones: int | None = None, semilla: int | None = None,
            info: bool = True) -> tuple[np.ndarray, dict]:
    """
    Operaciones con agresor exacto, sesión por sesión:
      · no informados: lado al azar, actividad por hora del día y por día (agrupada);
      · INFORMADOS (modelo PIN): con probabilidad `sim_prob_info` por sesión llega una noticia
        privada; durante 40-150 min los informados agregan +50 % de volumen, todo de un lado;
      · REVELACIÓN: al terminar el episodio la noticia se hace pública → 20 min con volumen ×3
        balanceado y ruido ×2.5. Es la volatilidad que el VPIN debería anticipar;
      · "noticias públicas" sin flujo informado antes: 10 min de volumen ×4 BALANCEADO
        (volatilidad sin toxicidad: nada que anticipar);
      · precio: cada contrato mueve el precio eficiente (impacto + ruido), se compra en el ask y
        se vende en el bid (rebote), la subasta de apertura sale sin agresor, y a mitad de la
        muestra hay un roll con salto de nivel.
    """
    rng = np.random.default_rng(cfg.sim_semilla if semilla is None else semilla)
    S = int(sesiones or cfg.sim_sesiones)
    tick = tick_de(cfg)
    m_ef = CATALOGO.get(raiz(cfg.symbol), ("", 0.25, 20000.0))[2] / tick
    fechas = pd.bdate_range(end=pd.Timestamp(cfg.end).normalize(), periods=S)
    perfil = perfil_actividad(np.arange(MINUTOS_SESION))
    base = cfg.sim_trades / perfil.sum()
    nivel = 0.0
    h_dia = 0.0
    partes, episodios, noticias, revelaciones = [], [], [], []
    inst = 7001
    for s_i, fecha in enumerate(fechas):
        t_ses = int(pd.Timestamp(fecha - pd.Timedelta(hours=DESFASE_H)).tz_localize(cfg.tz_mercado).tz_convert("UTC").value)
        h_dia = 0.8 * h_dia + 0.25 * rng.normal()
        tasa = base * perfil * math.exp(h_dia)
        n_u = rng.poisson(tasa)
        n_i = np.zeros(MINUTOS_SESION, dtype=int)
        ruido_min = np.ones(MINUTOS_SESION)
        d_ep = 0
        if info and rng.random() < cfg.sim_prob_info:
            m0 = int(rng.integers(60, MINUTOS_SESION - 180))
            dur = int(rng.integers(40, 150))
            d_ep = int(rng.choice((-1, 1)))
            n_i[m0:m0 + dur] = rng.poisson(0.5 * tasa[m0:m0 + dur])
            m_r = m0 + dur
            n_u[m_r:m_r + 20] += rng.poisson(2.0 * tasa[m_r:m_r + 20])
            ruido_min[m_r:m_r + 20] = 2.5
            episodios.append((t_ses + m0 * NS_MIN, t_ses + m_r * NS_MIN, d_ep, s_i))
            revelaciones.append((t_ses + m_r * NS_MIN, t_ses + (m_r + 20) * NS_MIN))
        if rng.random() < 0.3:
            m1 = int(rng.integers(60, MINUTOS_SESION - 20))
            n_u[m1:m1 + 10] += rng.poisson(3.0 * tasa[m1:m1 + 10])
            noticias.append((t_ses + m1 * NS_MIN, t_ses + (m1 + 10) * NS_MIN))
        if s_i == S // 2:
            inst += 1
            nivel += 40.0
        tot = n_u + n_i
        minuto = np.repeat(np.arange(MINUTOS_SESION), tot)
        es_inf = np.concatenate([np.r_[np.zeros(a, bool), np.ones(b, bool)] for a, b in zip(n_u, n_i)])
        t = t_ses + (minuto * 60 + rng.uniform(0, 60, len(minuto))) * NS
        orden = np.argsort(t, kind="stable")
        t, es_inf, minuto = t[orden].astype(np.int64), es_inf[orden], minuto[orden]
        n = len(t)
        lado = np.where(es_inf, d_ep, rng.choice((-1, 1), n))
        q = rng.geometric(0.5, n)
        ruido = rng.normal(size=n) * 1.5 * np.sqrt(q) * ruido_min[minuto]
        m_ef = m_ef + np.cumsum(0.02 * lado * q + ruido)
        m_ef_ult = m_ef[-1]
        precio_t = np.floor(m_ef + nivel) + (lado > 0)
        subasta = minuto == 0
        lado_b = np.where(subasta, b"N", np.where(lado > 0, b"B", b"A"))
        a = np.zeros(n, dtype=DTYPE_TRADES)
        a["ts_event"] = t
        a["price"] = np.round(precio_t * tick * PRICE_SCALE).astype(np.int64)
        a["size"] = q
        a["action"] = b"T"
        a["side"] = lado_b
        a["instrument_id"] = inst
        partes.append(a)
        m_ef = m_ef_ult
    arr = np.concatenate(partes)
    return arr, {"episodios": episodios, "noticias": noticias, "revelaciones": revelaciones, "roll_sesion": S // 2,
                 "sesiones": [str(f.date()) for f in fechas]}


def a_dbn(arr: np.ndarray, cfg: Config) -> bytes:
    """Arreglo simulado → archivo DBN de trades de verdad (para probar la ruta de Databento)."""
    import databento_dbn as dd
    lado = {b"B": dd.Side.BID, b"A": dd.Side.ASK, b"N": dd.Side.NONE}
    meta = dd.Metadata(dataset=cfg.dataset, start=int(arr["ts_event"][0]), stype_in=dd.SType.CONTINUOUS,
                       stype_out=dd.SType.INSTRUMENT_ID, schema=dd.Schema.TRADES, symbols=[cfg.symbol],
                       partial=[], not_found=[], mappings=[], end=int(arr["ts_event"][-1]) + NS)
    partes = [bytes(meta.encode())]
    for r in arr:
        partes.append(bytes(dd.TradeMsg(publisher_id=1, instrument_id=int(r["instrument_id"]),
                                        ts_event=int(r["ts_event"]), price=int(r["price"]), size=int(r["size"]),
                                        action=dd.Action.TRADE, side=lado[bytes(r["side"])], depth=0,
                                        ts_recv=int(r["ts_event"]) + 50_000, flags=int(r["flags"]))))
    return b"".join(partes)


# =============================================================================
# 8. EL CÁLCULO COMPLETO
# =============================================================================
@dataclass
class Resultado:
    cfg: Config
    V: int
    azar: Azar
    t_senales: pd.Timestamp | None
    buckets: pd.DataFrame
    bvc: pd.DataFrame
    tiempo: pd.DataFrame
    alertas: pd.DataFrame
    M: pd.DataFrame
    vol_ses: pd.Series
    conteo: dict
    aud: Auditoria
    motor: str
    segundos: float
    verdad: dict | None = None
    medicion: dict | None = None


def analizar(tienda, cfg: Config, motor: str = "vectorizado", verdad: dict | None = None,
             chequear_paridad: bool = True, verbose: bool = True) -> Resultado:
    validar(cfg)
    t0 = time.perf_counter()
    M, vol_ses, conteo = minutos_y_sesiones(tienda, cfg)
    V, t_senales = calibrar(vol_ses, cfg)
    azar = piso_azar(M, V, cfg, t_senales)
    conteo["bvc_acierto"] = acierto_bvc(M, cfg)
    if verbose:
        k = min(cfg.dias_calibracion, len(vol_ses))
        print(f"🔧 Volumen por sesión (mediana de las primeras {k}): {int(vol_ses.iloc[:k].median()):,} "
              f"→ bucket V = {V:,} contratos")
    B, sin_lado = procesar_buckets(tienda, V, cfg, motor)
    if len(B) <= cfg.n_buckets:
        sys.exit("❌ Muy pocos buckets para el VPIN. Usa un rango más largo o un V menor.")
    seg = time.perf_counter() - t0
    df = calcular_vpin(B, V, cfg, azar)
    bvc = vpin_bvc(M, V, cfg)
    tiempo = vpin_reloj_tiempo(M, cfg)
    alertas = detectar_alertas(df, cfg, t_senales, azar.piso)
    par = paridad(tienda, V, cfg) if chequear_paridad else None
    aud = auditar(df, bvc, tiempo, alertas, M, cfg, t_senales, conteo, par)
    res = Resultado(cfg=cfg, V=V, azar=azar, t_senales=t_senales, buckets=df, bvc=bvc, tiempo=tiempo,
                    alertas=alertas, M=M, vol_ses=vol_ses, conteo=conteo, aud=aud, motor=motor, segundos=seg,
                    verdad=verdad)
    if verdad is not None:
        res.medicion = medir_contra_verdad(res)
    return res


def medir_contra_verdad(res: Resultado) -> dict:
    """
    Alertas: ¿caen durante un episodio de flujo informado o hasta 1 h después? Episodios: los
    que duran ≥ 5 buckets (10 % de la ventana) son los que el reloj de volumen PUEDE ver; uno
    está cubierto si durante él (o 1 h después) el estado fue tóxico, con alerta nueva o no.
    """
    v, cfg, B = res.verdad, res.cfg, res.buckets
    al = res.alertas["t_fin"].astype("int64").to_numpy()
    lado = res.alertas["lado"].to_numpy()
    desde = res.t_senales.value if res.t_senales is not None else 0
    ep = [e for e in v["episodios"] if e[0] >= desde]
    hora = 60 * NS_MIN
    en, dir_ok = 0, 0
    for t, l_ in zip(al, lado):
        for a0, a1, d, s in ep:
            if a0 <= t <= a1 + hora:
                en += 1
                dir_ok += int((l_ == "compras") == (d > 0))
                break
    tb = B["t_fin"].astype("int64").to_numpy()
    toxico = (B["vpin_pct"].to_numpy() >= cfg.umbral_pct) & (B["vpin"].to_numpy() >= res.azar.piso)
    grandes = cubiertos = 0
    for a0, a1, d, s in ep:
        if ((tb >= a0) & (tb <= a1)).sum() >= 5:
            grandes += 1
            cubiertos += bool(toxico[(tb >= a0) & (tb <= a1 + hora)].any())
    en_noticia = sum(1 for t in al if any(a0 <= t <= a1 + 30 * NS_MIN for a0, a1 in v["noticias"]))
    return {"alertas": len(al), "en_episodio": en, "precision": en / len(al) if len(al) else np.nan,
            "direccion_ok": dir_ok, "episodios": len(ep), "grandes": grandes, "cubiertos": cubiertos,
            "en_noticia_publica": en_noticia}


def rebote_por_hora(M: pd.DataFrame, cfg: Config) -> pd.Series:
    """
    Σ r² con retornos de 1 min entre Σ r² con retornos de 5 min, por hora de Chicago. Sin
    rebote bid-ask la razón es ≈ 1; con rebote, el retorno de 1 min suma ruido y la razón sube,
    sobre todo en las horas quietas.
    """
    idx = pd.date_range(M.index[0], M.index[-1], freq="1min")
    p = M["precio"].reindex(idx).ffill(limit=5)
    ins = M["instrumento"].reindex(idx).ffill(limit=5).to_numpy()
    lp = np.log(p.to_numpy())
    r1 = np.r_[np.nan, np.diff(lp)]
    r1[np.r_[True, ins[1:] != ins[:-1]]] = np.nan
    r5 = np.full(len(lp), np.nan)
    r5[5:] = lp[5:] - lp[:-5]
    r5[np.r_[np.ones(5, bool), ins[5:] != ins[:-5]]] = np.nan
    r5[np.arange(len(lp)) % 5 != 0] = np.nan
    hora = idx.tz_convert(cfg.tz_mercado).hour
    s1 = pd.Series(r1 ** 2).groupby(hora).sum(min_count=1)
    s5 = pd.Series(r5 ** 2).groupby(hora).sum(min_count=1)
    activo = pd.Series(M["volumen"].reindex(idx).fillna(0).to_numpy() > 0).groupby(hora).mean()
    return (s1 / s5)[activo >= 0.5].rename("rebote")          # fuera la hora del cierre diario


# =============================================================================
# 9. REPORTES
# =============================================================================
def _hora(t: pd.Timestamp, cfg: Config) -> str:
    return f"{t.tz_convert(cfg.tz_mercado):%a %d-%m %H:%M} CT / {t.tz_convert(cfg.tz_local):%H:%M} CDMX"


def reporte_datos(res: Resultado) -> None:
    cfg, c, B = res.cfg, res.conteo, res.buckets
    _titulo("1 · DATOS, RELOJ DE VOLUMEN Y AGRESOR")
    print(f"  {cfg.symbol} ({nombre(cfg.symbol)}) · {c.get('operaciones', 0):,} operaciones · "
          f"{c.get('volumen', 0):,} contratos · {len(res.vol_ses)} sesiones")
    print(f"  Bucket V = {res.V:,} contratos (volumen típico por sesión / {cfg.buckets_por_dia}) · "
          f"{len(B):,} buckets · ventana del VPIN {cfg.n_buckets} buckets")
    if res.t_senales is not None:
        print(f"  Calibración: primeras {cfg.dias_calibracion} sesiones; alertas y auditoría desde "
              f"{_hora(res.t_senales, cfg)}")
    d = B["duracion_min"]
    hora = B["t_fin"].dt.tz_convert(cfg.tz_mercado).dt.hour
    rth = (hora >= 9) & (hora < 15)
    print(f"  Un bucket tarda {d[rth].median():.1f} min en horario regular y {d[~rth].median():.1f} min "
          f"fuera de él: el reloj corre con el volumen.")
    print(f"  Agresor: side 'B' = compra agresiva, 'A' = venta agresiva. Sin agresor ('N'): "
          f"{c.get('sin_lado_vol', 0):,} contratos ({c.get('sin_lado_vol', 0) / max(1, c.get('volumen', 1)):.2%}), "
          "fuera de los buckets.")
    print(f"  La BVC del artículo (lado deducido del cambio de precio de 1 min) le atina al lado de "
          f"{c.get('bvc_acierto', np.nan):.1%} del volumen; el agresor de CME, al 100 %.")
    z = res.azar
    print(f"  VPIN de pura moneda con este V: {z.media:.4f} ± {z.sd:.4f} (κ = Σq²/Σq = {z.kappa:.2f}) · "
          f"piso de alerta {texto_piso(z)} · VPIN mediano {B['vpin'].median():.4f} = "
          f"{B['vpin'].median() / z.media:.2f}× el azar")
    print(f"  Motor {res.motor}: {res.segundos:.1f} s para calibrar y armar los buckets.")


def reporte_hoy(res: Resultado) -> None:
    cfg, B, al = res.cfg, res.buckets, res.alertas
    _titulo("2 · TOXICIDAD HOY Y ALERTAS")
    u = B.iloc[-1]
    print(f"  Último bucket: {_hora(u['t_fin'], cfg)} · VPIN {u['vpin']:.3f} · percentil {u['vpin_pct']:.0%} "
          f"· desbalance {u['desbalance']:+.3f} ({'compras' if u['desbalance'] >= 0 else 'ventas'}) · "
          f"precio {u['precio']:,.2f}")
    estado = "TÓXICO" if u["vpin_pct"] >= cfg.umbral_pct else ("vigilancia" if u["vpin_pct"] >= cfg.rearme_pct else "normal")
    if estado == "TÓXICO" and u["vpin"] < res.azar.piso:
        estado = "percentil alto, pero el VPIN no supera lo que daría el azar"
    print(f"  Estado: {estado} (umbral {cfg.umbral_pct:.0%}, rearme {cfg.rearme_pct:.0%}, "
          f"enfriamiento {cfg.cooldown_min} min, piso de azar {texto_piso(res.azar)})")
    print()
    if al.empty:
        print("  Sin alertas de toxicidad con los umbrales actuales.")
        return
    dias = max((B["t_fin"].iloc[-1] - B["t_fin"].iloc[0]).total_seconds() / 86400, 1e-9)
    print(f"  {len(al)} alerta{'s' if len(al) != 1 else ''} (≈ {len(al) / dias * 5:.1f} por semana), "
          "al cierre del bucket:")
    for k, r in al.tail(12).iterrows():
        print(f"      {_hora(r['t_fin'], cfg)}  bucket {k:>5}  VPIN {r['vpin']:.3f}  percentil {r['vpin_pct']:.2f}  "
              f"domina {r['lado']:<7} ({r['desbalance']:+.3f})  {r['precio']:,.2f}")
    if len(al) > 12:
        print(f"      … y {len(al) - 12} más en el CSV")


def reporte_auditoria(res: Resultado) -> None:
    a = res.aud
    _titulo("3 · AUDITORÍA — ¿anticipa volatilidad MÁS ALLÁ de lo obvio?")
    print("  IC = correlación de rangos (Spearman) entre el percentil y la volatilidad FUTURA (retornos de 5 min).")
    print("  parcial v2 = tu cálculo: descuenta volatilidad y volumen recientes, todos los buckets juntos.")
    print("  parcial = además descuenta la hora del día, DENTRO de cada sesión; media entre sesiones, su IC 90 %")
    print("  y p de la t entre sesiones (Fama-MacBeth). '+' = sesiones con IC parcial positivo.")
    T = a.ic
    for var in T["variante"].unique():
        print()
        print(f"  {var}")
        print(f"      {'h':>6s}{'n':>7s}{'IC':>8s}{'RV pasada':>11s}{'parcial v2':>12s}{'parcial':>9s}{'IC 90 %':>18s}"
              f"{'p':>8s}{'+':>9s}")
        for f in T[T["variante"] == var].itertuples():
            ic90 = f"[{f.lo:+.3f}, {f.hi:+.3f}]" if np.isfinite(f.lo) else "—"
            pos = f"{f.positivas * f.sesiones:.0f}/{f.sesiones}" if f.sesiones else "—"
            print(f"      {f.h_min:>4d}m{f.n:7,d}{_fmt(f.IC, 3, 8)}{_fmt(f.IC_vol_pasada, 3, 11)}"
                  f"{_fmt(f.IC_parcial_tu, 3, 12)}{_fmt(f.IC_parcial, 3, 9)}{ic90:>18s}{_fmt(f.p, 3, 8)}{pos:>9s}")
    m = a.mecanica
    print()
    print("  Relación MECÁNICA con la actividad (Andersen y Bondarenko 2014):")
    print(f"      reloj de volumen: |oi| de cada bucket vs los minutos que tardó     Spearman {m['tox_bucket_vs_duracion']:+.2f}")
    print(f"      reloj de volumen: VPIN vs los minutos que tardó su ventana        Spearman {m['volumen']:+.2f}")
    print(f"      reloj de tiempo (tu v1): |c − v|/vol de la hora vs √(2κ/(π·n))   Spearman {m['tiempo']:+.2f}")
    print("      → con reloj de tiempo una hora tranquila parece tóxica sólo por tener poco volumen. (La 2ª")
    print("        cifra compara dos series lentas: en la simulación sin informados varía ±0.19 por azar.)")
    rb = a.mecanica.get("rebote")
    if rb is not None and len(rb):
        print(f"  Rebote bid-ask: Σr² con retornos de 1 min / con 5 min va de {rb.min():.2f} ({int(rb.idxmin())}:00 CT) "
              f"a {rb.max():.2f} ({int(rb.idxmax())}:00 CT).")
        print("      Por eso aquí la volatilidad se mide con 5 min (tu v2 usaba 1 min).")
    if not a.eventos.empty:
        print()
        print("  Después de cada alerta — volatilidad futura contra (1.0 = igual):")
        print(f"      {'h':>6s}{'n':>5s}{'bucket típico':>15s}{'misma hora':>12s}{'su pasado':>11s}")
        for f in a.eventos.itertuples():
            print(f"      {f.h_min:>4d}m{f.n:5d}{_fmt(f.vs_tipico, 2, 15)}{_fmt(f.vs_misma_hora, 2, 12)}{_fmt(f.vs_pasada, 2, 11)}")
        if a.eventos["n"].max() < 30:
            print("      ⚠ Menos de 30 alertas: es anecdótico, no estadístico.")
    print()
    print("  Dirección: IC entre el desbalance con signo y el retorno futuro (ticks): " + " · ".join(
        f"{f.h_min}m {f.IC:+.3f}" for f in a.direccion.itertuples() if np.isfinite(f.IC)))
    exacto = T[(T["variante"] == "VPIN (agresor exacto)")]
    sig = exacto[(exacto["p"] < 0.05) & (exacto["IC_parcial"] > 0)]
    print()
    if sig.empty:
        print("  CONCLUSIÓN: descontando la volatilidad reciente, el volumen y la hora del día, el VPIN no")
        print("  anticipa la volatilidad futura en estos datos (ningún horizonte con p < 0.05).")
    else:
        print(f"  CONCLUSIÓN: el VPIN aporta información propia en {len(sig)} de {len(exacto)} horizontes "
              f"(p < 0.05 entre sesiones).")


def reporte_cordura(res: Resultado) -> None:
    _titulo("4 · CHEQUEO DE CORDURA")
    for ok, txt in res.aud.cordura:
        print(f"  {'✓' if ok else '⚠'} {txt}")


def reporte_verdad(res: Resultado) -> None:
    v = res.medicion
    if not v:
        return
    _titulo("5 · CONTRA LA VERDAD (sólo en simulación)")
    print(f"  {v['episodios']} episodios de flujo informado después de la calibración · "
          f"{v['alertas']} alertas")
    print(f"  Alertas durante un episodio (o hasta 1 h después): {v['en_episodio']} "
          f"({_pct(v['precision'], 0, 1).strip()}) · con la dirección correcta: {v['direccion_ok']}")
    print(f"  Episodios que el reloj de volumen puede ver (≥ 5 buckets): {v['grandes']} · con estado tóxico "
          f"durante o hasta 1 h después: {v['cubiertos']}")
    print(f"  (los demás son nocturnos o cortos: 1-4 buckets de informados apenas mueven un promedio de "
          f"{res.cfg.n_buckets}) · alertas en 'noticias' públicas (volumen alto balanceado): {v['en_noticia_publica']}")


# =============================================================================
# 10. DASHBOARD
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


AVISO, VPIN_C = "#eda100", C["s7"]


def _romper(t: pd.Series | pd.DatetimeIndex, y: np.ndarray, hueco_min: float):
    """Inserta NaN donde hay huecos (fines de semana) para no unir puntos lejanos."""
    t = pd.DatetimeIndex(t)
    y = np.asarray(y, dtype=float)
    if len(t) < 2:
        return t, y
    cortes = np.flatnonzero(np.diff(t.asi8) > hueco_min * NS_MIN)
    if not cortes.size:
        return t, y
    s = pd.Series(np.r_[y, np.full(cortes.size, np.nan)],
                  index=t.append(t[cortes] + pd.Timedelta(seconds=1))).sort_index(kind="stable")
    return s.index, s.to_numpy()


def tablero_vpin(res: Resultado, plt, ruta: Path):
    import matplotlib.dates as mdates
    cfg, df, al, M = res.cfg, res.buckets, res.alertas, res.M
    fig = plt.figure(figsize=(18, 14))
    fig.patch.set_facecolor(C["fondo"])
    gs = fig.add_gridspec(5, 1, height_ratios=[2.0, 1.0, 1.0, 0.9, 0.8], hspace=0.28, bottom=0.05, top=0.93)
    ejes = [fig.add_subplot(gs[0])]
    ejes += [fig.add_subplot(gs[i], sharex=ejes[0]) for i in range(1, 5)]
    a1, a2, a3, a4, a5 = ejes
    tz = cfg.tz_local
    t = df["t_fin"].dt.tz_convert(tz)
    toxico = ((df["vpin_pct"] >= cfg.umbral_pct) & (df["vpin"] >= res.azar.piso)).to_numpy(copy=True)
    toxico[:-1] &= np.diff(df["t_fin"].astype("int64").to_numpy()) <= 180 * NS_MIN
    u = df.iloc[-1]
    fig.suptitle(f"VPIN · {cfg.symbol} ({nombre(cfg.symbol)}) · 1 bucket = {res.V:,} contratos · hoy: VPIN "
                 f"{u['vpin']:.3f}, percentil {u['vpin_pct']:.0%} · {len(al)} alertas",
                 x=0.01, ha="left", color=C["tinta"], fontsize=12.5)
    for ax in ejes:
        ax.fill_between(t, 0, 1, where=toxico, transform=ax.get_xaxis_transform(), color=AVISO, alpha=0.14,
                        linewidth=0, step="post")
        if res.t_senales is not None:
            ax.axvline(res.t_senales.tz_convert(tz), color=C["tenue"], linewidth=0.9)
    _estilo(a1, "Precio (cierre de 1 min) · zona tóxica = percentil ≥ umbral y VPIN sobre el piso de azar · ◆ alertas")
    tp, yp = _romper(M.index, M["precio"].to_numpy(), 30)
    a1.plot(tp.tz_convert(tz), yp, color=C["tinta"], linewidth=0.8)
    if len(al):
        a1.scatter(al["t_fin"].dt.tz_convert(tz), al["precio"], marker="D", s=46, color=AVISO,
                   edgecolors=C["tinta"], linewidths=0.8, zorder=4)
    a1.set_ylabel("precio", color=C["tinta2"], fontsize=9)

    _estilo(a2, "VPIN con agresor exacto contra el VPIN BVC del artículo original · líneas = lo que daría una moneda")
    tv, yv = _romper(df["t_fin"], df["vpin"].to_numpy(), 180)
    a2.plot(tv.tz_convert(tz), yv, color=VPIN_C, linewidth=1.1, label="agresor exacto")
    tb, yb = _romper(res.bvc["t_fin"], res.bvc["vpin"].to_numpy(), 180)
    a2.plot(tb.tz_convert(tz), yb, color=C["s4"], linewidth=0.9, alpha=0.9, label="BVC (clasifica por el precio)")
    a2.axhline(res.azar.media, color=C["tenue"], linewidth=0.9, linestyle=(0, (1, 3)), label="azar (moneda)")
    if np.isfinite(res.azar.piso):
        a2.axhline(res.azar.piso, color=C["tinta2"], linewidth=0.9, linestyle=(0, (4, 3)), label="piso de alerta")
    tope = np.nanmax(np.r_[yv, yb, res.azar.media]) if np.isfinite(np.r_[yv, yb]).any() else 0.1
    a2.set_ylim(0, tope * 1.3)
    a2.set_ylabel("VPIN", color=C["tinta2"], fontsize=9)
    _leyenda(a2, ncol=4, frameon=True, facecolor=C["fondo"], edgecolor="none", framealpha=0.9)

    _estilo(a3, f"Toxicidad RELATIVA: percentil del VPIN contra los {cfg.ventana_pct} buckets previos")
    tq, yq = _romper(df["t_fin"], df["vpin_pct"].to_numpy(), 180)
    tq = tq.tz_convert(tz)
    a3.plot(tq, yq, color=C["tinta2"], linewidth=0.8)
    a3.axhline(cfg.umbral_pct, color=C["tinta"], linewidth=0.9, linestyle=(0, (4, 3)))
    a3.axhline(cfg.rearme_pct, color=C["tenue"], linewidth=0.8, linestyle=(0, (1, 3)))
    a3.fill_between(tq, yq, cfg.umbral_pct, where=np.nan_to_num(yq) >= cfg.umbral_pct, color=AVISO, alpha=0.6,
                    linewidth=0, interpolate=True)
    a3.set_ylim(0, 1.02)
    a3.set_ylabel("percentil", color=C["tinta2"], fontsize=9)

    _estilo(a4, "Desbalance con signo (misma ventana): quién domina el flujo agresivo")
    td, yd = _romper(df["t_fin"], df["desbalance"].to_numpy(), 180)
    td = td.tz_convert(tz)
    a4.axhline(0, color=C["eje"], linewidth=0.8)
    a4.fill_between(td, yd, 0, where=np.nan_to_num(yd) >= 0, color=C["s1"], alpha=0.4, linewidth=0, interpolate=True,
                    label="compra agresiva")
    a4.fill_between(td, yd, 0, where=np.nan_to_num(yd) < 0, color=C["baja"], alpha=0.4, linewidth=0, interpolate=True,
                    label="venta agresiva")
    a4.plot(td, yd, color=C["tinta2"], linewidth=0.6)
    lim = max(0.02, float(np.nanmax(np.abs(yd))) * 1.15) if np.isfinite(yd).any() else 0.1
    a4.set_ylim(-lim, lim)
    _leyenda(a4, ncol=2, frameon=True, facecolor=C["fondo"], edgecolor="none", framealpha=0.9)

    _estilo(a5, "Reloj de volumen: minutos que tarda cada bucket (log)")
    a5.scatter(t, df["duracion_min"].clip(lower=0.05), s=3, color=C["s1"], alpha=0.5, linewidths=0)
    a5.set_yscale("log")
    from matplotlib.ticker import FuncFormatter, NullFormatter
    a5.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    a5.yaxis.set_minor_formatter(NullFormatter())
    a5.set_ylabel("min", color=C["tinta2"], fontsize=9)
    for ax in ejes[:-1]:
        ax.tick_params(labelbottom=False)
    a5.xaxis.set_major_locator(mdates.AutoDateLocator(tz=tz))
    a5.xaxis.set_major_formatter(mdates.DateFormatter("%d-%m\n%H:%M", tz=tz))
    fig.text(0.008, 0.012, f"{IDENTIFICADOR} · cada valor se fecha al cierre de su bucket · línea gris = fin de "
             "la calibración · fechas en CDMX", color=C["tenue"], fontsize=7.5)
    fig.savefig(ruta, dpi=120, facecolor=C["fondo"], bbox_inches="tight")
    return fig


def tablero_auditoria(res: Resultado, plt, ruta: Path):
    cfg, a = res.cfg, res.aud
    fig = plt.figure(figsize=(19, 13.5))
    fig.patch.set_facecolor(C["fondo"])
    gs = fig.add_gridspec(2, 3, hspace=0.42, wspace=0.3, bottom=0.06, top=0.92)
    (b1, b2, b3), (b4, b5, b6) = [[fig.add_subplot(gs[i, j]) for j in range(3)] for i in range(2)]
    fig.suptitle(f"VPIN · auditoría · {cfg.symbol}", x=0.01, ha="left", color=C["tinta"], fontsize=12.5)
    T = a.ic
    hs = list(cfg.horizontes_min)
    colores = {"VPIN (agresor exacto)": VPIN_C, "VPIN BVC (ELO 2012)": C["s4"], "reloj de tiempo (tu v1)": C["tenue"]}

    _estilo(b1, "IC PARCIAL con la volatilidad futura\nmedia entre sesiones (IC 90 %) · puntos = cada sesión")
    ex = "VPIN (agresor exacto)"
    rng_ = np.random.default_rng(0)
    for i, h in enumerate(hs):
        ps = a.por_sesion.get((ex, h), np.array([]))
        if len(ps):
            b1.scatter(i - 0.18 + rng_.uniform(-0.05, 0.05, len(ps)), ps, s=9, color=VPIN_C, alpha=0.25,
                       linewidths=0, zorder=1)
    for j, (var, col) in enumerate(colores.items()):
        f = T[T["variante"] == var].set_index("h_min").reindex(hs)
        if f["IC_parcial"].notna().any():
            xh = np.arange(len(hs)) + (j - 1) * 0.18
            b1.errorbar(xh, f["IC_parcial"], yerr=[f["IC_parcial"] - f["lo"], f["hi"] - f["IC_parcial"]],
                        fmt="o", color=col, ecolor=col, elinewidth=1.2, capsize=3, markersize=6, label=var, zorder=3)
    b1.axhline(0, color=C["eje"], linewidth=0.9)
    b1.set_xticks(range(len(hs)))
    b1.set_xticklabels([f"{h} min" for h in hs], fontsize=8.5)
    b1.set_ylabel("IC parcial (Spearman)", color=C["tinta2"], fontsize=9)
    _leyenda(b1, loc="upper left", frameon=True, facecolor=C["fondo"], edgecolor="none", framealpha=0.9)

    _estilo(b2, "VPIN exacto: IC sin controles vs parcial\n(cuánto era volatilidad, volumen y hora)")
    f = T[T["variante"] == ex].set_index("h_min").reindex(hs)
    w = 0.26
    for j, (colm, nm, cc) in enumerate((("IC", "sin controles", C["neutro"]), ("IC_parcial_tu", "parcial tu v2", C["s5"]),
                                        ("IC_parcial", "parcial + hora", VPIN_C))):
        b2.bar(np.arange(len(hs)) + (j - 1) * w, f[colm], width=w, color=cc, label=nm)
    b2.axhline(0, color=C["eje"], linewidth=0.9)
    b2.set_xticks(range(len(hs)))
    b2.set_xticklabels([f"{h} min" for h in hs], fontsize=8.5)
    _leyenda(b2, loc="upper right", frameon=True, facecolor=C["fondo"], edgecolor="none", framealpha=0.9)

    _estilo(b3, "Reloj de TIEMPO (tu v1): toxicidad de cada hora\nvs la que daría el azar con su volumen")
    H = res.tiempo
    b3.scatter(H["esperado_azar"], H["tox"], s=8, color=C["tenue"], alpha=0.5, linewidths=0, label="horas")
    xs = np.linspace(H["esperado_azar"].min(), H["esperado_azar"].max(), 20)
    b3.plot(xs, xs, color=C["baja"], linewidth=1.3, label="y = x: puro azar")
    b3.set_xlabel("√(2κ/(π·contratos de la hora))", color=C["tinta2"], fontsize=9)
    b3.set_ylabel("|compras − ventas| / volumen", color=C["tinta2"], fontsize=9)
    b3.text(0.97, 0.05, f"Spearman {a.mecanica['tiempo']:+.2f}", transform=b3.transAxes, ha="right",
            fontsize=9, color=C["tinta"])
    _leyenda(b3, loc="upper left")

    _estilo(b4, "Después de las alertas\nvolatilidad futura / la típica de esa hora")
    if not a.eventos.empty:
        e = a.eventos
        b4.bar(range(len(e)), e["vs_misma_hora"], color=[AVISO if v > 1 else C["neutro"] for v in e["vs_misma_hora"]])
        for i, (v, n_) in enumerate(zip(e["vs_misma_hora"], e["n"])):
            b4.annotate(f"{v:.2f}\nn {n_}", xy=(i, v), xytext=(0, 3), textcoords="offset points", ha="center",
                        fontsize=8, color=C["tinta"])
        b4.axhline(1, color=C["tinta2"], linewidth=1.0, linestyle=":")
        b4.set_xticks(range(len(e)))
        b4.set_xticklabels([f"{h} min" for h in e["h_min"]], fontsize=8.5)
        b4.margins(y=0.2)
    else:
        b4.text(0.5, 0.5, "sin alertas", transform=b4.transAxes, ha="center", color=C["tenue"])

    _estilo(b5, "Rebote bid-ask por hora de Chicago\nΣr² con 1 min / Σr² con 5 min · 1 = sin rebote")
    rb = a.mecanica.get("rebote")
    if rb is not None and len(rb):
        b5.bar(rb.index, rb.to_numpy(), color=[C["baja"] if v > 1.2 else C["s1"] for v in rb.to_numpy()])
        b5.axhline(1, color=C["tinta2"], linewidth=1.0, linestyle=":")
        b5.axvspan(8.5, 15.25, color=C["neutro"], alpha=0.35, linewidth=0, zorder=0)
        b5.set_xticks(range(0, 24, 3))
    b5.set_xlabel("hora de Chicago (gris = horario regular)", color=C["tinta2"], fontsize=9)

    b6.set_facecolor(C["fondo"])
    b6.axis("off")
    b6.set_title("Chequeo de cordura", color=C["tinta"], fontsize=10, loc="left", pad=8)
    import textwrap as _tw
    yy = 0.97
    for ok_, txt in a.cordura:
        lineas = _tw.wrap(txt, 60)
        b6.text(0.0, yy, "✓" if ok_ else "⚠", color=C["s3"] if ok_ else C["baja"], fontsize=11,
                transform=b6.transAxes, va="top")
        b6.text(0.05, yy, "\n".join(lineas), color=C["tinta"], fontsize=8.5, transform=b6.transAxes, va="top")
        yy -= 0.034 * len(lineas) + 0.035
    fig.text(0.008, 0.012, f"{IDENTIFICADOR} · IC de Spearman · controles: volatilidad y volumen recientes y "
             "volatilidad típica de la hora (sólo sesiones anteriores) · prueba t entre sesiones", color=C["tenue"],
             fontsize=7.5)
    fig.savefig(ruta, dpi=120, facecolor=C["fondo"], bbox_inches="tight")
    return fig


def tableros(res: Resultado, mostrar: bool = True) -> tuple[list[Path], object, bool]:
    plt, ventana = _preparar_grafico(mostrar)
    if plt is None:
        return [], None, False
    carpeta = _ruta(res.cfg.salida_dir)
    carpeta.mkdir(parents=True, exist_ok=True)
    rutas = []
    for nombre_, fn in (("toxicidad", tablero_vpin), ("auditoria", tablero_auditoria)):
        ruta = carpeta / f"vpin_{nombre_}_{raiz(res.cfg.symbol)}.png"
        fig = fn(res, plt, ruta)
        rutas.append(ruta)
        print(f"🖼  {ruta}")
        if not ventana:
            plt.close(fig)
    return rutas, plt, ventana


# =============================================================================
# 11. TELEGRAM — el token y el chat, igual que la key: FUERA del código
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
    """Alertas en el último día de datos."""
    al = res.alertas
    if al.empty:
        return []
    limite = res.buckets["t_fin"].iloc[-1] - pd.Timedelta(hours=24)
    return [f"{_hora(r['t_fin'], res.cfg)}: percentil {r['vpin_pct']:.2f}, domina {r['lado']}"
            for _, r in al[al["t_fin"] >= limite].iterrows()]


def mensaje_telegram(res: Resultado, limite: int = 4096) -> str:
    esc = html.escape
    cfg, u = res.cfg, res.buckets.iloc[-1]
    lin = [f"<b>{esc(IDENTIFICADOR)}</b> · {esc(cfg.symbol)} · bucket {res.V:,} contratos",
           esc(_hora(u["t_fin"], cfg))]
    for a in hay_alerta(res):
        lin.append(f"⚠️ {esc(a)}")
    lin += ["", f"<b>VPIN {u['vpin']:.3f} · percentil {u['vpin_pct']:.0%}</b>",
            f"desbalance {u['desbalance']:+.3f} ({'compras' if u['desbalance'] >= 0 else 'ventas'}) · "
            f"precio {u['precio']:,.2f}"]
    T = res.aud.ic
    f = T[T["variante"] == "VPIN (agresor exacto)"]
    if len(f):
        filas = ["h    parcial     p"] + [f"{int(z.h_min):3d}m {z.IC_parcial:+.3f} {z.p:6.3f}"
                                         for z in f.itertuples() if np.isfinite(z.IC_parcial)]
        lin.append("<pre>" + esc("\n".join(filas)) + "</pre>")
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


def enviar_texto_telegram(texto: str) -> bool:
    cred = credenciales_telegram(preguntar=False)
    if cred is None:
        return False
    r = llamar_telegram(cred[0], "sendMessage", {"chat_id": cred[1], "text": texto, "parse_mode": "HTML"})
    return bool(r.get("ok"))


# =============================================================================
# 12. GUARDAR Y LIVE
# =============================================================================
def guardar(res: Resultado) -> None:
    cfg = res.cfg
    carpeta = _ruta(cfg.salida_dir)
    carpeta.mkdir(parents=True, exist_ok=True)
    B = res.buckets
    suf = _nombre_seguro(raiz(cfg.symbol), f"{B['t_fin'].iloc[0]:%Y%m%d}", f"{B['t_fin'].iloc[-1]:%Y%m%d}")
    out = B.copy()
    out.insert(2, "t_fin_cdmx", out["t_fin"].dt.tz_convert(cfg.tz_local))
    out.to_csv(carpeta / f"vpin_buckets_{suf}.csv")
    al = res.alertas.copy()
    al.insert(1, "t_fin_cdmx", al["t_fin"].dt.tz_convert(cfg.tz_local))
    al.to_csv(carpeta / f"vpin_alertas_{suf}.csv")
    res.aud.ic.to_csv(carpeta / f"vpin_auditoria_{suf}.csv", index=False)
    print(f"💾 Buckets, alertas y auditoría guardados en {carpeta}")


def ultimo_halt_cme(t: pd.Timestamp, cfg: Config) -> pd.Timestamp:
    """Inicio del último halt diario (16:00 CT, lunes a viernes) ≤ t, en UTC."""
    local = t.tz_convert(cfg.tz_mercado).tz_localize(None)
    cand = local.normalize() + pd.Timedelta(hours=16)
    if cand > local:
        cand -= pd.Timedelta(days=1)
    while cand.weekday() >= 5:
        cand -= pd.Timedelta(days=1)
    return cand.tz_localize(cfg.tz_mercado).tz_convert("UTC")


def correr_live(cfg: Config, cliente_hist=None, cliente_live=None, ahora: pd.Timestamp | None = None,
                max_registros: int | None = None) -> MotorVPIN:
    """
    Calienta con el histórico hasta el último halt diario y sigue con Databento Live, bucket por
    bucket, con el motor incremental. Con --telegram-live cada alerta llega a tu teléfono.
    (Los clientes y `ahora` son inyectables para probarlo sin red.)
    """
    cliente_hist = cliente_hist or conectar()
    ahora = ahora if ahora is not None else pd.Timestamp.now(tz="UTC")
    corte = ultimo_halt_cme(ahora, cfg)
    rango = cliente_hist.metadata.get_dataset_range(dataset=cfg.dataset)
    disponible = pd.Timestamp(rango.get("end") or rango.get("end_date"))
    disponible = disponible.tz_localize("UTC") if disponible.tzinfo is None else disponible.tz_convert("UTC")
    if corte > disponible:
        corte = ultimo_halt_cme(disponible, cfg)
    inicio_live = max(corte, ahora - pd.Timedelta(hours=23))
    if inicio_live > corte:
        print(f"⚠ Entre {corte} y {inicio_live} (UTC) no hay replay: si hubo operaciones, faltarán.")
    cfg_h = replace(cfg, start=(corte - pd.Timedelta(days=cfg.dias_historial_live)).strftime("%Y-%m-%dT%H:%M:%S"),
                    end=corte.strftime("%Y-%m-%dT%H:%M:%S"))
    store = obtener_datos(cfg_h, cliente_hist)
    M, vol, _ = minutos_y_sesiones(store, cfg)
    V = int(cfg.volumen_bucket) if cfg.volumen_bucket else calibrar(vol, cfg)[0]
    azar = piso_azar(M, V, cfg)
    print(f"🔧 Bucket = {V:,} contratos · VPIN de puro azar {azar.media:.4f} (piso {texto_piso(azar)}). "
          "Calentando con el histórico…")
    tg = cfg.telegram_live and credenciales_telegram(preguntar=False) is not None
    cola = deque(maxlen=cfg.ventana_pct + cfg.n_buckets + 1)
    det = DetectorToxicidad(cfg.umbral_pct, cfg.rearme_pct, cfg.cooldown_min * NS_MIN, azar.piso)
    estado = {"calentando": True, "alertas": 0}

    def al_cerrar(fila: dict) -> None:
        cola.append(fila)
        u = calcular_vpin(tabla_buckets(list(cola)), V, cfg, azar).iloc[-1]
        alerta = det.actualizar(int(fila["t_fin"]), u["vpin_pct"], u["vpin"])
        if estado["calentando"]:
            return
        print(f"[LIVE] {_hora(u['t_fin'], cfg)}  bucket {fila['k']}  VPIN {u['vpin']:.3f}  "
              f"percentil {u['vpin_pct']:.2f}  desbalance {u['desbalance']:+.3f}  {u['precio']:,.2f}")
        if alerta:
            estado["alertas"] += 1
            lado = "compras" if u["desbalance"] >= 0 else "ventas"
            print(f"⚠ [LIVE] ALERTA DE TOXICIDAD  percentil {u['vpin_pct']:.2f}  domina {lado}")
            if tg:
                enviar_texto_telegram(f"⚠️ <b>{html.escape(cfg.symbol)} · toxicidad</b>\n{html.escape(_hora(u['t_fin'], cfg))}\n"
                                      f"VPIN {u['vpin']:.3f} · percentil {u['vpin_pct']:.0%} · domina {lado}\n"
                                      f"precio {u['precio']:,.2f}")

    motor = MotorVPIN(V, al_cerrar_bucket=al_cerrar)
    for rec in store:
        if type(rec).__name__ == "TradeMsg":
            motor.procesar_registro(rec)
    estado["calentando"] = False
    print(f"✅ Calentamiento listo ({motor._k:,} buckets). Conectando a Live desde {inicio_live} UTC…")
    cliente_live = cliente_live or db.Live(reconnect_policy="reconnect")
    cliente_live.subscribe(dataset=cfg.dataset, schema="trades", symbols=cfg.symbol, stype_in=cfg.stype_in,
                           start=inicio_live)
    corte_ns = corte.value
    vistos = 0
    try:
        for rec in cliente_live:
            nombre_ = type(rec).__name__
            if nombre_ == "TradeMsg":
                if rec.ts_event >= corte_ns:
                    motor.procesar_registro(rec)
                vistos += 1
                if max_registros and vistos >= max_registros:
                    break
            elif nombre_ == "ErrorMsg":
                print(f"⚠ Databento: {rec.err}")
            elif nombre_ == "SystemMsg" and not rec.is_heartbeat():
                print(f"ℹ {rec.msg}")
    except KeyboardInterrupt:
        print("\nCerrando…")
    finally:
        cliente_live.stop()
    motor.alertas_live = estado["alertas"]
    return motor


# =============================================================================
# 13. LÍNEA DE COMANDOS
# =============================================================================
def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="VPIN AC v3 — toxicidad del flujo con reloj de volumen")
    p.add_argument("--pruebas", action="store_true", help="pruebas internas (sin red ni datos)")
    p.add_argument("--simulacion", action="store_true", help="mercado simulado con flujo informado conocido")
    p.add_argument("--motor", choices=("vectorizado", "incremental"), default="vectorizado")
    p.add_argument("--live", action="store_true")
    p.add_argument("--archivo", help="usar un .dbn / .dbn.zst existente en vez de descargar")
    p.add_argument("--simbolo")
    p.add_argument("--inicio", "--start", dest="start", help="UTC, p. ej. 2026-08-03T00:00:00")
    p.add_argument("--fin", "--end", dest="end", help="UTC, p. ej. 2026-08-21T23:59:00")
    p.add_argument("--volumen-bucket", type=int, dest="volumen_bucket", help="fija V en contratos")
    p.add_argument("--buckets-por-dia", type=int, dest="buckets_por_dia")
    p.add_argument("--ventana", type=int, dest="n_buckets", help="buckets en la ventana del VPIN (50)")
    p.add_argument("--umbral", type=float, dest="umbral_pct")
    p.add_argument("--rearme", type=float, dest="rearme_pct")
    p.add_argument("--cooldown", type=int, dest="cooldown_min")
    p.add_argument("--z-piso", type=float, dest="z_piso", help="piso de azar: VPIN ≥ azar + z·σ (2.33)")
    p.add_argument("--sin-piso", action="store_true", help="alertar sólo por percentil, como tu v2")
    p.add_argument("--costo-max", type=float, dest="costo_max_usd")
    p.add_argument("--salida", dest="salida_dir", help="carpeta para CSV y PNG (salidas_vpin/)")
    p.add_argument("--sin-grafica", "--sin-tablero", action="store_true", dest="sin_tablero")
    p.add_argument("--sin-ventana", action="store_true")
    p.add_argument("--sin-paridad", action="store_true")
    t = p.add_argument_group("Telegram")
    t.add_argument("--telegram", action="store_true")
    t.add_argument("--telegram-solo-alertas", action="store_true")
    t.add_argument("--telegram-live", action="store_true", help="en --live, manda cada alerta")
    t.add_argument("--telegram-documentos", action="store_true")
    t.add_argument("--telegram-buscar-chat", action="store_true")
    s = p.add_argument_group("simulación")
    s.add_argument("--sesiones-sim", type=int, dest="sim_sesiones")
    s.add_argument("--semilla", type=int, dest="sim_semilla")
    s.add_argument("--sin-informados", action="store_true")
    return p


def config_desde_args(a: argparse.Namespace) -> Config:
    cambios = {k: getattr(a, k) for k in ("start", "end", "volumen_bucket", "buckets_por_dia", "n_buckets",
                                          "umbral_pct", "rearme_pct", "cooldown_min", "z_piso", "costo_max_usd",
                                          "salida_dir", "sim_sesiones", "sim_semilla")
               if getattr(a, k, None) is not None}
    if a.simbolo:
        cambios["symbol"] = simbolo_continuo(a.simbolo)
    if a.telegram_live:
        cambios["telegram_live"] = True
    if a.sin_piso:
        cambios["z_piso"] = None
    return replace(CFG, **cambios)


def main(argv: list[str] | None = None) -> int:
    a = construir_parser().parse_args(argv)
    cfg = config_desde_args(a)
    if a.pruebas:
        return pruebas()
    if a.telegram_buscar_chat:
        return buscar_chat_telegram()
    validar(cfg)
    if a.live:
        correr_live(cfg)
        return 0
    print(f"▶ {IDENTIFICADOR} · {cfg.symbol} · motor {a.motor}")
    verdad = None
    if a.simulacion:
        print(f"🎲 {cfg.sim_sesiones} sesiones simuladas (~{cfg.sim_trades:,} operaciones cada una): flujo informado "
              "(modelo PIN), noticias públicas balanceadas, rebote bid-ask, subasta sin agresor y un roll CONOCIDOS.")
        tienda, verdad = simular(cfg, info=not a.sin_informados)
    elif a.archivo:
        tienda = db.DBNStore.from_file(a.archivo)
    else:
        tienda = obtener_datos(cfg)
    res = analizar(tienda, cfg, motor=a.motor, verdad=verdad, chequear_paridad=not a.sin_paridad)
    res.aud.mecanica["rebote"] = rebote_por_hora(res.M, cfg)
    reporte_datos(res)
    reporte_hoy(res)
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
            print("📭 Telegram: sin alertas en las últimas 24 h.")
        else:
            enviar_telegram(res, rutas, documentos=a.telegram_documentos)
    _titulo("CÓMO LEER ESTO")
    print("  1. Un bucket es un paquete de V contratos: el VPIN avanza con el volumen, no con el reloj.")
    print("  2. VPIN = Σ|compras − ventas| / (n·V) con el agresor que reporta CME (no deducido del precio).")
    print("  3. Lo que alerta es el PERCENTIL contra los buckets anteriores (toxicidad relativa), siempre que")
    print("     el VPIN supere lo que daría una moneda con este V (piso de azar).")
    print("  4. Antes de usarlo mira la columna 'parcial' y su p: si el VPIN no anticipa volatilidad")
    print("     descontando volatilidad, volumen y hora, sus alertas repiten lo que ya se veía.")
    if rutas and not a.sin_ventana:
        print()
        mostrar_tableros(plt_, ventana, rutas)
    return 0


# =============================================================================
# 14. PRUEBAS INTERNAS
# =============================================================================
def pruebas() -> int:
    import contextlib
    import io
    import tempfile
    from types import SimpleNamespace

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

    def iguales(a: pd.DataFrame, b: pd.DataFrame) -> bool:
        return len(a) == len(b) and (len(a) == 0 or bool((a.to_numpy() == b.to_numpy()).all()))

    _titulo("PRUEBAS INTERNAS")
    rng = np.random.default_rng(0)

    # 1 ------------------------------------------ buckets a mano: reparto, oi, n, tiempos, higiene
    P = int(PRICE_SCALE)
    crudo = [(1, 100 * P, 5, b"T", b"B"), (2, 101 * P, 3, b"T", b"A"), (3, 102 * P, 7, b"T", b"B"),
             (4, 103 * P, 4, b"T", b"N"), (5, 104 * P, 0, b"T", b"B"), (2, 105 * P, 25, b"T", b"A"),
             (7, 106 * P, 3, b"T", b"B"), (8, UNDEF_PRICE, 2, b"T", b"B"), (9, 107 * P, 6, b"A", b"B")]
    chico = np.zeros(len(crudo), dtype=DTYPE_TRADES)
    for i, (t_, p_, q_, a_, s_) in enumerate(crudo):
        chico[i] = (t_, p_, q_, a_, s_, 0, 1)
    esperado = {"oi": [4, 0, -10, -10], "n_trades": [3, 2, 1, 1], "t_ini": [1, 3, 5, 5], "t_fin": [3, 5, 5, 5],
                "precio": [102.0, 105.0, 105.0, 105.0]}
    bien = True
    for tb in (1, 2, 3, 4, 100):
        for fn in (buckets_vectorizado, buckets_incremental):
            b_, sl_ = fn(chico, 10, replace(cfg, tam_bloque=tb))
            bien &= (sl_ == 4 and list(b_.index) == [1, 2, 3, 4]
                     and b_["oi"].tolist() == esperado["oi"] and b_["n_trades"].tolist() == esperado["n_trades"]
                     and b_["t_ini"].astype("int64").tolist() == esperado["t_ini"]
                     and b_["t_fin"].astype("int64").tolist() == esperado["t_fin"]
                     and b_["precio"].tolist() == esperado["precio"])
    check("buckets a mano: una venta de 25 cierra 3 buckets; 'N', tamaño 0, precio indefinido y no-operación "
          "fuera; tiempo monótono — ambos motores, bloques de 1 a 100", bool(bien))

    # --- una simulación chica para la plomería ---
    cs = replace(cfg, sim_sesiones=6, sim_trades=12_000)
    arr, _ = simular(cs, semilla=3)
    V0 = 257

    # 2 ------------------------------------------ doble motor: mismo resultado, en cualquier tamaño de bloque
    a1, s1 = buckets_vectorizado(arr, V0, replace(cs, tam_bloque=7_777))
    a2, s2 = buckets_vectorizado(arr, V0, replace(cs, tam_bloque=10 ** 9))
    a3, s3 = buckets_incremental(arr, V0, cs)
    check("motor vectorizado (bloques de 7 777 o de un jalón) = motor incremental, operación por operación",
          iguales(a1, a2) and iguales(a1, a3) and s1 == s2 == s3 and len(a1) > 200,
          f"{len(arr):,} operaciones · {len(a1):,} buckets idénticos")

    # 3 ------------------------------------------ la ruta real de Databento: DBN → to_ndarray / registros
    if db is not None:
        try:
            sub = arr[:25_000]
            tienda = db.DBNStore.from_bytes(a_dbn(sub, cs))
            b_dbn, _ = buckets_vectorizado(tienda, V0, replace(cs, tam_bloque=4_096))
            b_arr, _ = buckets_vectorizado(sub, V0, cs)
            m_ = MotorVPIN(V0)
            for r in tienda:
                m_.procesar_registro(r)
            M_dbn = minutos_y_sesiones(tienda, cs)[0]
            M_arr = minutos_y_sesiones(sub, cs)[0]
            check("DBN de verdad: to_ndarray por bloques y registro por registro (Side/Action de databento) = arreglo",
                  iguales(b_dbn, b_arr) and iguales(m_.buckets(), b_arr) and M_dbn.equals(M_arr),
                  f"{len(b_arr)} buckets")
        except Exception as e:                                    # pragma: no cover
            check("DBN de verdad: to_ndarray por bloques y registro por registro = arreglo", False, repr(e))
    else:
        print("  · databento no está instalado: se salta la prueba del DBN")

    # 4 ------------------------------------------ higiene: registros basura no cambian nada
    sucio = arr.copy()
    idx = np.sort(rng.choice(np.arange(1, len(arr)), 900, replace=False))
    basura = arr[idx - 1].copy()                                  # mismo tiempo que el registro anterior
    basura["size"][:300] = 0
    basura["price"][300:600] = UNDEF_PRICE
    basura["action"][600:] = rng.choice([b"A", b"C", b"M"], 300)
    sucio = np.insert(sucio, idx, basura)
    b_s, sl_s = buckets_vectorizado(sucio, V0, cs)
    b_i, _ = buckets_incremental(sucio, V0, cs)
    c_s = minutos_y_sesiones(sucio, cs)[2]
    check("higiene: 900 registros basura (tamaño 0, precio indefinido, no-operación) → buckets idénticos",
          iguales(b_s, a1) and iguales(b_i, a1) and sl_s == s1 and c_s["invalidas"] == 600
          and c_s["no_operacion"] == 300, f"inválidas {c_s['invalidas']} · no-operación {c_s['no_operacion']}")

    # 5 ------------------------------------------ percentil: a mano y sin mirar al futuro
    x = np.array([5, 1, 2, 3, 4, 4, 10], float)
    pc = percentil_movil(x, 3, 2)
    esp = [np.nan, np.nan, 0.5, 2 / 3, 1.0, 2.5 / 3, 1.0]
    x2 = x.copy()
    x2[6] = -99
    check("percentil móvil: rango contra los W previos (empates a la mitad), nada del futuro",
          np.allclose(pc, esp, equal_nan=True) and np.allclose(percentil_movil(x2, 3, 2)[:6], pc[:6], equal_nan=True))

    # 6 ------------------------------------------ fórmula del VPIN
    Bf = pd.DataFrame({"t_ini": pd.date_range("2026-01-05", periods=60, freq="min", tz="UTC"),
                       "oi": rng.integers(-100, 101, 60)})
    Bf["t_fin"] = Bf["t_ini"] + pd.Timedelta(seconds=50)
    dfv = calcular_vpin(Bf, 100, replace(cs, n_buckets=10, ventana_pct=20, min_obs_pct=10))
    k_ = 37
    ok6 = (abs(dfv["vpin"].iloc[k_] - np.abs(Bf["oi"].iloc[k_ - 9:k_ + 1]).sum() / 1000) < 1e-12
           and abs(dfv["desbalance"].iloc[k_] - Bf["oi"].iloc[k_ - 9:k_ + 1].sum() / 1000) < 1e-12
           and dfv["vpin"].iloc[:9].isna().all() and (dfv["compras"] + dfv["ventas"] == 100).all())
    check("VPIN = Σ|oi| / (n·V) y desbalance = Σoi / (n·V) sobre los últimos n buckets", bool(ok6))

    # 7 ------------------------------------------ detector: histéresis, enfriamiento y piso de azar
    det = DetectorToxicidad(0.90, 0.75, 60 * NS_MIN, piso=0.05)
    seq = [(0, .95, .06), (10, .97, .07), (20, .70, .05), (30, .95, .06), (40, .60, .03),
           (100, .92, .04), (110, .93, .06), (120, np.nan, .09), (130, .99, .09)]
    dispara = [i for i, (t_, p_, v_) in enumerate(seq) if det.actualizar(t_ * NS_MIN, p_, v_)]
    check("detector: una alerta por episodio, el cruce en enfriamiento se consume, bajo el piso no dispara",
          dispara == [0, 6], f"disparos en {dispara}")

    # 8 ------------------------------------------ calibración sin información futura
    fechas = pd.date_range("2026-03-02", periods=10, freq="B")
    vol = pd.Series([1000, 1200, 800, 1100, 900, 5, 5, 5, 5, 5], index=fechas)
    vol2 = vol.copy()
    vol2.iloc[5:] = 10 ** 7
    Vc, fin = calibrar(vol, cs)
    Vc2, fin2 = calibrar(vol2, cs)
    check("V usa sólo las primeras 5 sesiones y las alertas empiezan al cierre de la 5ª (16:00 CT)",
          Vc == Vc2 == round(1000 / cs.buckets_por_dia) and fin == fin2
          and fin == pd.Timestamp("2026-03-06 16:00", tz="America/Chicago").tz_convert("UTC"),
          f"V = {Vc} · {fin.tz_convert('America/Chicago'):%a %d-%m %H:%M} CT")

    # 9 ------------------------------------------ sesiones de Globex
    ts9 = np.array([pd.Timestamp(v, tz="America/Chicago").value
                    for v in ("2026-03-08 17:00", "2026-03-09 15:59", "2026-03-09 17:00")])
    f9 = [str(pd.Timestamp(v).date()) for v in fecha_sesion(ts9, "America/Chicago")]
    check("sesión de Globex: el domingo 17:00 CT ya es lunes; el lunes 17:00 CT, martes",
          f9 == ["2026-03-09", "2026-03-09", "2026-03-10"], " · ".join(f9))

    # 10 ----------------------------------------- el agresor: sentido correcto y el chequeo que lo vigila
    c_ok = minutos_y_sesiones(arr, cs)[2]
    volteado = arr.copy()
    volteado["side"] = np.where(arr["side"] == b"B", b"A", np.where(arr["side"] == b"A", b"B", arr["side"]))
    c_mal = minutos_y_sesiones(volteado, cs)[2]
    check("agresor: las compras agresivas se hacen arriba de las ventas; con los lados al revés, el chequeo lo ve",
          c_ok["agresor_dif_ticks"] > 0.5 and c_mal["agresor_dif_ticks"] < -0.5,
          f"{c_ok['agresor_dif_ticks']:+.2f} ticks · volteado {c_mal['agresor_dif_ticks']:+.2f}")

    # 10b ---------------------------------------- la t de Student exacta, contra valores de tablas
    check("t de Student sin scipy: p y cuantiles de tablas",
          abs(p_t(2.0639, 24) - 0.05) < 1e-4 and abs(p_t(1.0, 1) - 0.5) < 1e-12
          and abs(_t_cuantil(0.95, 10) - 1.8125) < 1e-4 and abs(_t_cuantil(0.95, 30) - 1.6973) < 1e-4,
          f"p(2.064; 24) = {p_t(2.0639, 24):.4f} · t₀.₉₅(10) = {_t_cuantil(0.95, 10):.4f}")

    # 11 ----------------------------------------- la prueba entre sesiones: tamaño correcto donde tu t falla
    def _ar(n_, phi):
        e = rng.normal(size=n_)
        for i in range(1, n_):
            e[i] += phi * e[i - 1]
        return e

    S_, n_s = 20, 50
    ses_ = np.repeat(np.arange(S_), n_s)
    cs11 = replace(cs, min_obs_sesion=15)
    rechazos = {"sesiones": 0, "tu_t": 0, "potencia": 0}
    R = 120
    for _ in range(R):
        x_ = np.repeat(_ar(S_, 0.9), n_s) + 0.5 * _ar(S_ * n_s, 0.95)
        y_ = np.repeat(_ar(S_, 0.9), n_s) + rng.normal(size=S_ * n_s)
        z_ = rng.normal(size=S_ * n_s)
        pr = prueba_parcial(x_, y_, [z_], ses_, cs11)
        r_, n_ = spearman_parcial(x_, y_, [z_])
        t_ = r_ * math.sqrt((n_ - 3) / (1 - r_ * r_))
        rechazos["sesiones"] += pr["p"] < 0.10
        rechazos["tu_t"] += 2 * (1 - NormalDist().cdf(abs(t_))) < 0.10
        y_s = y_ + 0.3 * (x_ - np.repeat(pd.Series(x_).groupby(ses_).mean().to_numpy(), n_s))
        rechazos["potencia"] += prueba_parcial(x_, y_s, [z_], ses_, cs11)["p"] < 0.01
    check("prueba t entre sesiones: sin señal rechaza ≈ 10 % a p < 0.10 (la t con n_eff, mucho más); "
          "con señal la encuentra",
          rechazos["sesiones"] / R < 0.17 and rechazos["tu_t"] / R > 0.3 and rechazos["potencia"] / R > 0.8,
          f"sin señal: {rechazos['sesiones'] / R:.0%} contra {rechazos['tu_t'] / R:.0%} con la t de todos los "
          f"puntos · con señal: {rechazos['potencia'] / R:.0%} a p < 0.01")

    # --- dos mercados simulados completos: sin y con flujo informado ---
    cn = replace(cfg, sim_sesiones=16, sim_trades=25_000)
    arr_n, ver_n = simular(cn, semilla=10, info=False)
    rn = callado(analizar, arr_n, cn, verdad=ver_n, chequear_paridad=False, verbose=False)
    ci = replace(cfg, sim_sesiones=20, sim_trades=25_000)
    arr_i, ver_i = simular(ci, semilla=0)
    ri = callado(analizar, arr_i, ci, verdad=ver_i, verbose=False)
    ri.aud.mecanica["rebote"] = rebote_por_hora(ri.M, ci)

    # 12 ----------------------------------------- el VPIN de pura moneda
    z = rn.azar
    med = float(rn.buckets["vpin"].median())
    z4 = piso_azar(rn.M, 4 * rn.V, cn, rn.t_senales)
    check("sin informados el VPIN mediano es el de una moneda, √(2κ/(πV)); con 4V, la mitad",
          abs(med / z.media - 1) < 0.1 and abs(z.kappa - 3.0) < 0.15 and abs(z4.media * 2 - z.media) < 1e-12,
          f"mediana {med:.4f} vs {z.media:.4f} · κ {z.kappa:.2f} (geométrica p = ½: 3)")

    # 13 ----------------------------------------- el piso de azar quita las falsas alarmas
    al_sin = detectar_alertas(rn.buckets, cn, rn.t_senales)
    check("sin flujo informado: el piso de azar quita la mayoría de las alertas (todas son falsas)",
          len(rn.alertas) * 3 <= len(al_sin) and len(al_sin) >= 3,
          f"{len(rn.alertas)} alertas con piso contra {len(al_sin)} sin él, en {cn.sim_sesiones} sesiones")

    # 14 ----------------------------------------- relación mecánica: reloj de tiempo sí, de volumen no
    mec = rn.aud.mecanica
    check("reloj de tiempo: |c − v|/vol sigue a √(2/(π·n)); con reloj de volumen los buckets lentos no son más tóxicos",
          mec["tiempo"] > 0.2 and mec["tox_bucket_vs_duracion"] < 0.1,
          f"tiempo {mec['tiempo']:+.2f} · volumen {mec['tox_bucket_vs_duracion']:+.2f}")

    # 15 ----------------------------------------- ecos mecánicos: la BVC y el reloj de tiempo
    T = rn.aud.ic
    ic_bvc = T[T["variante"] == "VPIN BVC (ELO 2012)"]["IC"].mean()
    ic_ex = T[T["variante"] == "VPIN (agresor exacto)"]["IC"].mean()
    ic_t = T[T["variante"] == "reloj de tiempo (tu v1)"]["IC"].mean()
    check("sin informados, la BVC 'anticipa' volatilidad (clasifica con el precio) y el reloj de tiempo la "
          "'anti-anticipa' (horas quietas = tóxicas): ecos, no información",
          ic_bvc > max(0.05, ic_ex + 0.05) and ic_t < -0.05 and 0.55 < rn.conteo["bvc_acierto"] < 0.9,
          f"IC crudo medio: BVC {ic_bvc:+.3f} · exacto {ic_ex:+.3f} · reloj de tiempo {ic_t:+.3f} · "
          f"la BVC atina {rn.conteo['bvc_acierto']:.0%} del volumen")

    # 16 ----------------------------------------- contra la verdad
    md = ri.medicion
    check("con informados: las alertas caen en episodios, con la dirección correcta",
          md["alertas"] >= 3 and md["precision"] >= 0.6 and md["direccion_ok"] >= md["en_episodio"] - 1
          and md["cubiertos"] >= 1,
          f"{md['en_episodio']} de {md['alertas']} alertas · {md['direccion_ok']} con la dirección correcta · "
          f"{md['cubiertos']} de {md['grandes']} episodios visibles cubiertos")

    # 17 ----------------------------------------- chequeos de cordura y paridad dentro de la corrida
    cord = ri.aud.cordura
    check("chequeo de cordura: todo en verde en la simulación, incluida la paridad de motores",
          all(ok for ok, _ in cord) and ri.aud.paridad["igual"], f"{len(cord)} chequeos")

    # 18 ----------------------------------------- rebote bid-ask por hora
    rb = ri.aud.mecanica["rebote"]
    check("rebote por hora: la hora del cierre diario (16 CT) queda fuera y la razón ronda 1 en la simulación",
          16 not in rb.index and len(rb) >= 20 and rb.between(0.6, 1.6).all(),
          f"{len(rb)} horas · de {rb.min():.2f} a {rb.max():.2f}")

    # 19 ----------------------------------------- reportes, tableros y archivos
    with tempfile.TemporaryDirectory() as tmp:
        rr = replace(ri, cfg=replace(ri.cfg, salida_dir=tmp))
        texto = io.StringIO()
        try:
            with contextlib.redirect_stdout(texto):
                reporte_datos(rr)
                reporte_hoy(rr)
                reporte_auditoria(rr)
                reporte_cordura(rr)
                reporte_verdad(rr)
                rutas, plt_, _ = tableros(rr, mostrar=False)
                guardar(rr)
            archivos = sorted(p.name for p in Path(tmp).iterdir())
            ok19 = (len(rutas) == 2 and all(p.stat().st_size > 50_000 for p in rutas)
                    and sum(a.endswith(".csv") for a in archivos) == 3 and "CONCLUSIÓN" in texto.getvalue())
            if plt_ is not None:
                plt_.close("all")
            check("reportes, 2 tableros PNG y 3 CSV sin errores", bool(ok19), ", ".join(archivos))
        except Exception as e:                                    # pragma: no cover
            check("reportes, 2 tableros PNG y 3 CSV sin errores", False, repr(e))

    # 20 ----------------------------------------- el halt diario de CME
    casos = {"2026-03-09 10:00": "2026-03-06 16:00", "2026-03-07 12:00": "2026-03-06 16:00",
             "2026-03-10 17:30": "2026-03-10 16:00", "2026-03-10 16:00": "2026-03-10 16:00"}
    ok20 = all(ultimo_halt_cme(pd.Timestamp(a, tz="America/Chicago").tz_convert("UTC"), cs)
               == pd.Timestamp(b, tz="America/Chicago").tz_convert("UTC") for a, b in casos.items())
    check("último halt diario de CME (16:00 CT, lunes a viernes)", bool(ok20))

    # 21 ----------------------------------------- Live con clientes falsos: calentamiento + flujo en vivo
    if db is not None:
        cl = replace(cfg, sim_sesiones=8, sim_trades=6_000, n_buckets=10, buckets_por_dia=40, ventana_pct=60,
                     min_obs_pct=30, cooldown_min=30, telegram_live=True)
        arr_l, _ = simular(cl, semilla=11)
        ahora = pd.Timestamp("2026-06-29 12:00", tz="America/Chicago").tz_convert("UTC")
        corte = ultimo_halt_cme(ahora, cl)
        t_l = arr_l["ts_event"].astype(np.int64)
        desde_h = (corte - pd.Timedelta(days=cl.dias_historial_live)).value
        hist = arr_l[(t_l >= desde_h) & (t_l < corte.value)]
        vivo = arr_l[(t_l >= corte.value - 5 * NS_MIN) & (t_l < ahora.value)]      # 5 min repetidos
        bytes_hist = a_dbn(hist, cl)

        class _Meta:
            def get_dataset_range(self, dataset):
                return {"end": ahora.isoformat()}

            def get_cost(self, **k):
                return 0.1

        class _Series:
            def get_range(self, path, **k):
                Path(path).write_bytes(bytes_hist)
                return object()

        class _Live:
            def __init__(self, recs):
                self.recs, self.sub, self.parado = recs, None, False

            def subscribe(self, **k):
                self.sub = k

            def __iter__(self):
                return iter(self.recs)

            def stop(self):
                self.parado = True

        live = _Live(list(db.DBNStore.from_bytes(a_dbn(vivo, cl))))
        import urllib.request
        enviados = []

        def _tg(req, timeout=None):
            enviados.append(req.full_url.rsplit("/", 1)[-1])
            return io.BytesIO(json.dumps({"ok": True, "result": {}}).encode())

        entorno = {k: os.environ.get(k) for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")}
        viejo = urllib.request.urlopen
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.environ["TELEGRAM_BOT_TOKEN"] = "123456789:" + "B" * 35
                os.environ["TELEGRAM_CHAT_ID"] = "987654321"
                urllib.request.urlopen = _tg
                motor = callado(correr_live, replace(cl, cache_dir=tmp), SimpleNamespace(metadata=_Meta(),
                                timeseries=_Series()), live, ahora)
                M_h, vol_h, _ = minutos_y_sesiones(hist, cl)
                V_l = calibrar(vol_h, cl)[0]
                todo = np.concatenate([hist, vivo[vivo["ts_event"].astype(np.int64) >= corte.value]])
                esperado_b, _ = buckets_incremental(todo, V_l, cl)
                k_cal = len(buckets_incremental(hist, V_l, cl)[0])
                df_l = calcular_vpin(esperado_b, V_l, cl, piso_azar(M_h, V_l, cl))
                d_ = DetectorToxicidad(cl.umbral_pct, cl.rearme_pct, cl.cooldown_min * NS_MIN,
                                       piso_azar(M_h, V_l, cl).piso)
                n_al = sum(d_.actualizar(int(t_), p_, v_) and k > k_cal for k, t_, p_, v_ in
                           zip(df_l.index, df_l["t_fin"].astype("int64"), df_l["vpin_pct"], df_l["vpin"]))
                ok21 = (motor.V == V_l and iguales(motor.buckets(), esperado_b) and motor.alertas_live == n_al >= 1
                        and enviados == ["sendMessage"] * n_al and live.parado and live.sub["start"] >= corte
                        and len(esperado_b) > k_cal)
                check("Live: calienta con el histórico hasta el halt, sigue en vivo sin duplicar lo repetido, "
                      "alerta igual que el cálculo completo y manda cada alerta a Telegram", bool(ok21),
                      f"{k_cal} buckets de calentamiento + {len(esperado_b) - k_cal} en vivo · {n_al} alertas · "
                      f"{len(enviados)} mensajes")
            except Exception as e:                                # pragma: no cover
                check("Live con clientes falsos", False, repr(e))
            finally:
                urllib.request.urlopen = viejo
                for k, v in entorno.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v

    # 22 ----------------------------------------- línea de comandos
    a_ = construir_parser().parse_args(["--simbolo", "es", "--start", "2026-08-03T00:00:00", "--fin",
                                        "2026-08-21T23:59:00", "--volumen-bucket", "5000", "--telegram-live"])
    c_ = config_desde_args(a_)
    c2 = config_desde_args(construir_parser().parse_args(["--sin-piso"]))
    c3 = config_desde_args(construir_parser().parse_args(["--z-piso", "3"]))
    check("línea de comandos: --start/--inicio, --end/--fin, --simbolo ES → ES.n.0, --sin-piso, --z-piso",
          c_.symbol == "ES.n.0" and c_.start.startswith("2026-08-03") and c_.end.startswith("2026-08-21")
          and c_.volumen_bucket == 5000 and c_.telegram_live and c2.z_piso is None and c3.z_piso == 3.0
          and c_.z_piso == CFG.z_piso)

    # 23 ----------------------------------------- Telegram: nunca el token
    tok = "123456789:" + "A" * 35
    msg = _sin_token(f"fallo en https://api.telegram.org/bot{tok}/sendMessage", tok)
    check("los errores de Telegram nunca muestran el token", tok not in msg and "…" in msg)

    # 24 ----------------------------------------- Telegram de punta a punta, sin red
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
    png = Path(tempfile.gettempdir()) / "_prueba_telegram_vpin.png"
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
                and b'name="photo"; filename="_prueba_telegram_vpin.png"' in cuerpo
                and tok.encode() not in cuerpo)
    finally:
        urllib.request.urlopen = viejo
        png.unlink(missing_ok=True)
    check("Telegram: el multipart de sendPhoto está bien formado y no lleva el token", bool(bien))

    # 25 ----------------------------------------- ninguna key escrita en este archivo
    fuente = Path(__file__).read_text(encoding="utf-8")
    check("no hay API keys ni tokens escritos en el código",
          not re.search("db" + "-" + r"[A-Za-z0-9]{20,}", fuente)
          and not re.search(r"\d{8,10}:" + r"[A-Za-z0-9_-]{35}", fuente))

    # 26 ----------------------------------------- mensaje de Telegram
    txt = mensaje_telegram(ri)
    check("el mensaje de Telegram cabe en un mensaje y escapa el HTML", len(txt) <= 4096 and "<b>" in txt
          and "<pre>" in txt, f"{len(txt)} caracteres")

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
