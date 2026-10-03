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
