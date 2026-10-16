# P4-13 — Estabilidad: procedimiento (pendiente de correr con la Pi física)

**Issue:** [#13](https://github.com/sanchezesteban/MLOPS_p4/issues/13) · **Responsable:** Juan Pablo (@jpdelmuro)
**Ámbito:** rúbrica 2.4.

## Estado

**No ejecutado todavía.** La Raspberry Pi está en casa; este documento deja el procedimiento listo
y probado en sus partes (scripts verificados por separado) para correrlo completo en cuanto haya
acceso físico -- ya sea antes del ensayo de las 16:00 o durante él, que de todas formas requiere
tener la Pi, la cámara, el adaptador OTG y la fuente en el mismo lugar.

No se usó la cámara de la laptop ni un video simulado como atajo: el criterio depende de la cámara
real conectada a la Pi funcionando sin caerse, así que correrlo en otro dispositivo no demostraría
nada sobre la Zero 2W.

## Procedimiento

### 1. 20 capturas repartidas entre gato y perro, en operación continua

```bash
cd ~/edge
rm -rf capturas   # opcional, para que la cuenta de esta corrida sea limpia
tmux new-session -d -s edge '~/edge-venv/bin/python main.py --config config.json'
```

Durante al menos 5 minutos, alternar objetos reales (gato/perro, o fotos de ambos) frente a la
cámara, variados a lo largo de la ventana -- no todos al inicio. Con `capture_interval_seconds: 5`
del config, 5 minutos dan ~60 capturas, de sobra para las 20 mínimas.

Verificar al terminar:

```bash
tmux capture-pane -t edge -p | tail -40        # log de la sesión
ls capturas/*.json | wc -l                      # total de capturas
python3 -c "
import json, glob
preds = [json.load(open(f))['predicted_class'] for f in glob.glob('capturas/*.json')]
print('cat:', preds.count('cat'), '| dog:', preds.count('dog'), '| total:', len(preds))
"
cat capturas/log.jsonl | python3 -c "
import json, sys
estados = [json.loads(l)['send_status'] for l in sys.stdin]
print({s: estados.count(s) for s in set(estados)})
"
```

Si algo quedó en `error` real (no simulado), **no se oculta**: se documenta tal cual en la evidencia
final, junto con el resultado de `--retry-failed`.

### 2. Reinicio + captura nueva que llega al portal

```bash
tmux kill-session -t edge
~/edge-venv/bin/python main.py --config config.json --once
```

Copiar el `capture_id` que imprime, y confirmar que llega a la API que usa el portal (sin
credenciales, pública):

```bash
bash verificar_captura.sh <capture_id>
```

O revisarlo directamente en el portal: <http://3.133.248.228> (sección «Capturas Edge»).

### 3. Evidencia para la entrega

- `docs/p4/estabilidad-procedimiento.md` (este documento) actualizado con los resultados reales:
  hora de inicio/fin, total de capturas, conteo gato/perro, cualquier error real y su reintento.
- Lista completa de los 20+ `capture_id` (o el archivo `capturas/log.jsonl` completo como anexo).
- Captura de pantalla del portal mostrando la captura del paso 2 (la del reinicio).

## Scripts de apoyo (ya probados por separado)

- [`edge/sin_red_demo.sh`](../../edge/sin_red_demo.sh) -- mismo patrón que se usará en la demo
  (P4-22/P4-23) para "desconectar red → sigue clasificando → reconectar → llega al portal". Probado
  con una ventana corta (20s): 6 capturas durante el corte, 2 después, todo correcto.
- [`edge/verificar_captura.sh`](../../edge/verificar_captura.sh) -- confirma por API (no por AWS CLI)
  que una captura llegó, igual que lo vería el portal. Probado contra una captura real.

## Criterios de «hecho» (pendientes de ejecución real)

- [ ] 5 minutos de operación continua sin caídas
- [ ] Reiniciar el programa y hacer una captura nueva que llega al portal
- [ ] 20 capturas repartidas entre gato y perro enviadas a AWS
- [ ] Errores reales (si los hubo) quedan registrados
