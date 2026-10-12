# Comercial 3D de Fracxion

Versión dinámica horizontal de 19 segundos, 1920 × 1080 y 60 fotogramas por segundo, con notebook y móvil modelados en 3D. Cinco posiciones de cámara conectadas por una trayectoria suave, acercamientos, giros independientes de ambos dispositivos, fundidos de un segundo entre funciones y banda instrumental original a 78 BPM.

## Archivos

- `fracxion-comercial-3d-dinamico.mp4`: nueva entrega H.264 / AAC estéreo, preparada para reproducción progresiva.
- `fracxion-comercial-3d.mp4`: primera versión conservada.
- `portada.jpg`: imagen del video exportado.
- `revision-fotogramas.jpg`: hoja de ocho momentos del MP4 para revisar el encuadre.
- `revision-tecnica.json`: resultados de la comprobación del archivo final.
- `revision-reproduccion.json`: reproducción completa a velocidad normal y búsquedas dentro del MP4 en Chromium.
- `render-diagnostics.json`: tiempo, cámara, scroll, estado WebGL y encuadre de cada fotograma.
- `SHA256SUMS.txt`: integridad del MP4.
- `source/`: escena, composición, render, audio y revisión reproducibles.

Las pantallas utilizan nuevas capturas reales de la aplicación en `source/demo-captures/`. Se preparó una empresa ficticia, tres clientes y tres productos en PostgreSQL efímero; desde la interfaz se creó y emitió un comprobante de ARS 1.210,00 y se registró un pago parcial de ARS 400,00. El saldo de ARS 810,00 persistió tras recargar. La evidencia de captura está en `source/demo-captures/capture-evidence.json`. La vista del comprobante conserva la indicación de gestión interna sin autorización fiscal.

Las operaciones de demostración se realizaron exclusivamente en la base temporal de esta tarea, sin tocar datos de negocio del proyecto. El render usa las capturas conservadas y se ejecuta sin API ni base de datos. Los informes de la primera versión se conservan en `version-1/`.

## Secuencia

| Tiempo | Imagen |
| --- | --- |
| 0–3 s | Vista general de los dispositivos y resumen de empresa. |
| 3–7 s | Giro hacia la notebook y lista real de clientes. |
| 7–11 s | Cliente y servicio seleccionados en la creación de un comprobante. |
| 11–15 s | Comprobante emitido y formulario de pago por transferencia en el móvil. |
| 15–17 s | Pago registrado, historial y saldo actualizado en ambos dispositivos. |
| 17–19 s | Retorno al encuadre general y cierre de marca. |

## Reproducir el render

Requisitos: dependencias del frontend instaladas, Chromium de Playwright, Node.js, Python con NumPy/Pillow y FFmpeg. El motor Three.js 0.180.0 y la tipografía Adwaita Sans están incluidos con sus licencias. No se consultan API ni servicios externos durante el render.

Desde la raíz del repositorio:

```bash
node frontend/node_modules/playwright/cli.js install chromium --only-shell
python docs/video/source/audio.py
node docs/video/source/render.mjs --preview
node docs/video/source/render.mjs
ffmpeg -y -i /tmp/fracxion-video-frames/silent.mp4 \
  -i /tmp/fracxion-video-frames/soundtrack.wav \
  -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -b:a 192k \
  -t 19 -movflags +faststart docs/video/fracxion-comercial-3d-dinamico.mp4
python docs/video/source/review.py
node docs/video/source/playback.mjs
```

El render abre temporalmente `127.0.0.1:8769` y lo cierra al finalizar. En un entorno con GPU compatible puede ejecutarse con `FRACXION_GPU=1`. Para utilizar una instalación temporal de Chromium, definir `PLAYWRIGHT_BROWSERS_PATH` con su directorio. `--benchmark` mide doce fotogramas antes de exportar.

Cada fotograma usa un instante calculado como `n / 60`; el tiempo empleado por el equipo en dibujarlo no altera la velocidad del video. La trayectoria de cámara tiene tangentes continuas y entrada/salida gradual. Las sombras se recalculan cuando giran los dispositivos. El scroll móvil mantiene velocidad constante en su tramo central y las capturas mantienen sus proporciones. Los pequeños pulsos sobre producto, importe y botón de pago orientan la atención a los controles reales capturados.

## Revisión

La comprobación decodifica los 1140 fotogramas del MP4 y verifica duración, formato, resolución, frecuencia, continuidad temporal, ausencia de imágenes idénticas prolongadas, límites del scroll, movimientos de cámara/dispositivos, audio sin saturación, pantallas visibles y cuerpos completos dentro del encuadre. La revisión visual utiliza imágenes extraídas del archivo exportado; no se limita a la escena de origen. Los resultados concretos quedan en `revision-tecnica.json`.

La validación se refiere a este video y a su reproducción en Chromium local. Se comprobó el flujo comercial mostrado en PostgreSQL real aislado; no se repitió la suite completa del producto. El reproductor de pruebas usa decodificación por software; sus pausas y fotogramas omitidos, si los hay, quedan registrados en `revision-reproduccion.json`.

Resultado de esta versión: 19,00 segundos, 1140 fotogramas decodificados, ambos dispositivos completos dentro del encuadre y reproducción a 1× sin errores, pausas de carga ni fotogramas omitidos en la prueba local. Los servidores de captura y PostgreSQL efímero quedaron cerrados; las capturas incluidas permiten regenerar el video sin ellos.
