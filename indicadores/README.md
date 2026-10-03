# Indicadores de microestructura

## `rastreador_id.py` — Rastreador de ID (big trades institucionales)

Con los datos TBBO de Databento (cada operación con el mejor bid/ask justo antes de ella), el script hace esto:

1. **Agrupación de eventos en alta frecuencia**: junta los registros en la orden agresiva exacta que casó CME (mismo `ts_event` y mismo agresor). Después junta en *huellas* las agresiones del mismo lado separadas por ≤ 100 ms.
2. **Magnitud empírica causal**: clasifica cada huella como GRANDE, MEGA o BALLENA (p95, p99 y p99.9) contra las 5 sesiones **anteriores**, con umbrales aparte para el día y la noche.
3. **Tipo de flujo**: ABSORCIÓN, FRAGMENTADA, BARRIDO o BLOQUE.
4. **Clusters**: rachas de huellas ≥ MEGA, con su pureza direccional y dos pruebas de permutación contra el azar.
5. **Auditoría de impacto predictivo**: impacto y deriva a 1 s – 60 min. Usa errores estándar agrupados por sesión y descuenta el momentum y los costos.
6. **Dashboard**: 3 tableros (rastreador, auditoría y tabla de IDs).

Cada huella grande recibe un **ID** (`YM0818-007`) que aparece en la consola, los tableros, los CSV, Telegram y Live. También se **rastrea** con triple barrera: SOSTENIDO, ROTO o NEUTRO.

```bash
pip install numpy pandas matplotlib databento
python rastreador_id.py --pruebas        # 31 pruebas internas, sin red
python rastreador_id.py --simulacion     # mercado simulado con la verdad conocida
python rastreador_id.py                  # YM, 18-20 de agosto de 2026 (hora CDMX)
python rastreador_id.py --live --telegram-live
```

La API key se lee de `DATABENTO_API_KEY`. El token y el chat de Telegram se leen de `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`. La documentación completa está en el docstring del archivo: qué se midió, qué fallaba en el script original, límites y fuentes.

## `optimal_execution.py` — Optimal Execution Algorithms (impacto por MLE y ejecución óptima)

Con TBBO (cada operación con el libro justo antes) y OHLCV-1m de Databento, el script hace esto:

1. **Extracción de eventos clave**: las huellas ≥ p95 de las sesiones **anteriores** (motor exacto de CME del rastreador), con el mid antes del print y a 0 s – 30 min después, el tamaño relativo al volumen de esa hora (Q/V₅) y la σ esperada.
2. **Ajuste matemático del modelo (MLE)**: impacto `A·σ₅·Σ(qₑ/V₅)^δ` que decae como `π + (1 − π)·e^(−h/τ)`, con covarianza de difusión intradía + microestructura. QMLE gaussiano, errores estándar agrupados por sesión (CR1 + jackknife), comparación de modelos (CLAIC, Wald), curva semiparamétrica y perfil de δ.
3. **Análisis dinámico (rolling)**: A con las últimas sesiones y δ, π, τ expansivos, siempre con lo sabido **antes** de cada sesión. A por hora del día y prueba de estabilidad de Nyblom.
4. **Algoritmos**: TWAP, VWAP (perfil de sesiones previas), POV (con 1 min de rezago), POV*, Almgren–Chriss y ÓPTIMO (Obizhaeva–Wang con resiliencia). Se replican clip a clip en un walk-forward de compra **y** venta, con atribución exacta del costo, frontera eficiente, incertidumbre de los parámetros, arrepentimiento y comparación pareada (Holm, MDE).
5. **Dashboard cuádruple**: precio con los large trades institucionales y nuestra ejecución · ajuste MLE · rolling · inventario y costo del walk-forward. Más un tablero de auditoría de 12 paneles.
6. **Plan de la próxima sesión**: contratos por slice con hora de Chicago y de CDMX (CSV y Telegram).

```bash
pip install numpy pandas matplotlib databento scipy   # scipy es opcional (sin él, Nelder–Mead propio)
python optimal_execution.py --pruebas        # 28 pruebas internas, sin red
python optimal_execution.py --simulacion     # mercado simulado con el impacto conocido
python optimal_execution.py                  # NQ, sesión del 20 de agosto de 2026 + 10 previas
python optimal_execution.py --solo-plan --telegram   # sólo el plan de mañana, a tu teléfono
```

Las credenciales se leen de `DATABENTO_API_KEY`, `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`. La documentación completa está en el docstring del archivo: qué se midió, qué fallaba en el script original, límites y fuentes.
