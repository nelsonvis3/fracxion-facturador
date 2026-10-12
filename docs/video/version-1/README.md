# Comercial 3D de Fracxion

Video horizontal de 19 segundos, 1920 × 1080 y 60 fotogramas por segundo, con notebook y móvil modelados en 3D. Toma continua, desplazamiento lento del contenido, fundidos de 1,8 segundos entre las vistas de la notebook y banda instrumental original a 78 BPM.

## Archivos

- `fracxion-comercial-3d.mp4`: entrega H.264 / AAC estéreo, preparada para reproducción progresiva.
- `portada.jpg`: imagen del video exportado.
- `revision-fotogramas.jpg`: hoja de ocho momentos del MP4 para revisar el encuadre.
- `revision-tecnica.json`: resultados de la comprobación del archivo final.
- `revision-reproduccion.json`: reproducción completa a velocidad normal y búsquedas dentro del MP4 en Chromium.
- `render-diagnostics.json`: tiempo, cámara, scroll, estado WebGL y encuadre de cada fotograma.
- `SHA256SUMS.txt`: integridad del MP4.
- `source/`: escena, composición, render, audio y revisión reproducibles.

Las pantallas utilizan las capturas de `docs/screenshots/company-dashboard-desktop.png`, `invoice.png` y `company-dashboard-mobile.png`. Son imágenes de la aplicación con datos sintéticos de pruebas. El video no modifica empresas, clientes, comprobantes ni pagos de ninguna base. La vista del comprobante conserva la indicación de gestión interna sin autorización fiscal.

## Secuencia

| Tiempo | Imagen |
| --- | --- |
| 0–7 s | Resumen de empresa en la notebook; el móvil comienza un desplazamiento lento. |
| 7–9 s | Fundido al detalle del comprobante en la pantalla de la notebook. |
| 9–14 s | Comprobante y cobros; el móvil recorre las herramientas de gestión. |
| 14–16 s | Fundido de regreso al resumen. |
| 16–19 s | Ambos dispositivos siguen visibles; cierre de marca y salida suave de la música. |

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
  -t 19 -movflags +faststart docs/video/fracxion-comercial-3d.mp4
python docs/video/source/review.py
node docs/video/source/playback.mjs
```

El render abre temporalmente `127.0.0.1:8769` y lo cierra al finalizar. En un entorno con GPU compatible puede ejecutarse con `FRACXION_GPU=1`. Para utilizar una instalación temporal de Chromium, definir `PLAYWRIGHT_BROWSERS_PATH` con su directorio. `--benchmark` mide doce fotogramas antes de exportar.

Cada fotograma usa un instante calculado como `n / 60`; el tiempo empleado por el equipo en dibujarlo no altera la velocidad del video. El scroll mantiene velocidad constante en su tramo central, con entrada y salida gradual. El contenido de la notebook conserva la barra lateral de escritorio mientras se desplaza el área principal. Las capturas se escalan uniformemente para conservar sus proporciones.

## Revisión

La comprobación decodifica los 1140 fotogramas del MP4 y verifica duración, formato, resolución, frecuencia, continuidad temporal, ausencia de imágenes idénticas prolongadas, límites del scroll, audio sin saturación, pantallas visibles y encuadre. La revisión visual utiliza imágenes extraídas del archivo exportado; no se limita a la escena de origen. Los resultados concretos quedan en `revision-tecnica.json`.

La validación se refiere a este video y a su reproducción en Chromium local. Las capturas originales proceden de pruebas anteriores; esta entrega no vuelve a ejecutar las operaciones comerciales de la aplicación.

Resultado final: 19,00 s, 1140 fotogramas decodificados, pantallas dentro del encuadre y audio sin saturación. Reproducción completa a 1×, sin errores ni pausas de carga. La prueba utiliza decodificación por software debido a un error del controlador al forzar GPU; ese compositor informa ocho fotogramas omitidos, conservados en el reporte. La codificación del archivo contiene los 1140 fotogramas a 60 fps.
