# Log de revisión, errores y correcciones

Revisión del 10 de octubre de 2026. Este archivo registra la comprobación actual; los resultados históricos siguen en `AUDIT.md`. Las pruebas usan datos sintéticos y PostgreSQL separado de las bases reales. No se guardan contraseñas reales, cookies, tokens de recuperación ni cuerpos de peticiones privadas en este log.

## Hallazgos

### A-001 — JSON con enteros excesivos devuelve 500

- **Estado inicial:** reproducido antes de modificar el código. Un objeto con un entero de 5.000 dígitos devuelve 500 en login, registro, solicitud y confirmación de recuperación, aun con CSRF válido.
- **Causa:** los lectores JSON de `accounts/views.py` y `accounts/password_reset.py` no capturan el `ValueError` del límite de conversión de enteros de Python.
- **Corrección aplicada:** lectura común en `config/parsers.py`, captura del límite de enteros y rechazo de JSON inválido con 400. La API comercial utiliza el mismo validador, con límite de 2,5 MiB, profundidad máxima de 100 y números finitos.
- **Verificación:** las ocho pruebas iniciales de seguridad pasan después de la corrección; incluyen los cuatro endpoints. La suite existente de 203 pruebas pasó antes de estos cambios.

### A-002 — Unicode inválido en recuperación provoca una excepción

- **Estado inicial:** reproducido antes de modificar el código. Un correo con un surrogate Unicode aislado llega a `identity.encode('utf-8')` en el límite de recuperación y produce `UnicodeEncodeError`.
- **Causa:** login/recuperación aceptan cadenas sin validar su codificación. También se revisarán caracteres NUL y la entrada de los módulos comerciales.
- **Corrección aplicada:** rechazo de NUL y surrogates aislados en claves y valores JSON antes de hashing, consultas o persistencia. Límite de 254 caracteres para correo y de 4.096 para contraseñas de login/recuperación, antes del hashing; registro conserva su límite de 128.
- **Verificación:** pruebas de regresión reproducidas antes y aprobadas después. PostgreSQL confirmó también `DataError` con NUL en el correo de recuperación.

### A-003 — Dependencia de desarrollo con aviso sin parche publicado

- **Estado inicial:** `npm audit` actualizado informa cinco paquetes afectados por una cadena de desarrollo: `eslint-config-next → @next/eslint-plugin-next → fast-glob → micromatch → braces`.
- **Evidencia:** [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm), consultado durante esta revisión. El aviso afecta `braces <=3.0.3` y no informa una versión corregida.
- **Estado actual:** pendiente de corrección upstream. Se consultaron las últimas versiones de `eslint-config-next`, el plugin Next y `braces`: 16.4.0, plugin con `fast-glob@3.3.1`, y `braces@3.0.3`. La bajada automática a Next 14 no es una corrección compatible. Se conserva el aviso sin ocultarlo.

### A-004 — Producción permite desactivar cookies seguras y HTTPS

- **Estado inicial:** reproducido con carga real de settings en procesos separados. Producción arranca con `SESSION_COOKIE_SECURE=False`, `CSRF_COOKIE_SECURE=False` o `SECURE_SSL_REDIRECT=False`. También acepta confiar en HTTPS de proxy sin declarar redes válidas.
- **Impacto:** una configuración incorrecta puede degradar la protección de cookies o dejar inoperante la detección de HTTPS.
- **Corrección aplicada:** producción exige ambas cookies Secure y redirección HTTPS; cuando confía en HTTPS de proxy, exige redes explícitas válidas. No cambia el funcionamiento del entorno de desarrollo.
- **Verificación:** pruebas de regresión fallan antes de la corrección y pasan después; 216 pruebas del backend aprobadas.

### A-005 — Regresión de mensajes por campo durante la corrección

- **Estado inicial:** la primera ejecución de la suite completa tras A-001/A-002 detectó que un NUL en `company_name` del registro se rechazaba con un mensaje genérico en lugar del error por campo existente.
- **Corrección aplicada:** el registro comparte el control estructural/tamaño del JSON y delega la validación del texto a su serializer DRF, que ya rechaza NUL y Unicode inválido por campo. Login/recuperación y el resto de la API conservan la validación común de texto.
- **Verificación:** las 216 pruebas del backend pasan, conservando la expectativa de la prueba existente.

### E-001 — Chromium ausente en el entorno de pruebas

- **Estado inicial:** los seis E2E se detuvieron al arrancar: falta `chromium_headless_shell-1248`.
- **Corrección:** instalación de Chromium mediante Playwright en `/tmp/facturador-playwright`. No se considera un fallo funcional de la aplicación.
- **Verificación:** diez escenarios Playwright aprobados en 27 segundos con Chromium instalado: seis flujos de navegador y cuatro de seguridad API.

### A-006 — HSTS no cubre las páginas del frontend

- **Estado inicial:** comprobado con `HEAD /` sobre Caddy HTTPS del stack de producción. La API incluye `Strict-Transport-Security` mediante Django, pero la página de login servida por Next no lo incluye.
- **Corrección aplicada:** política HSTS en el proxy para todas las respuestas del dominio. La primera comprobación detectó cabecera duplicada en Django; se utiliza asignación diferida `>` para reemplazarla al enviar la respuesta, conforme a la [documentación de Caddy](https://caddyserver.com/docs/caddyfile/directives/header).
- **Verificación:** GET en `/` y `/api/auth/csrf/` confirma una sola cabecera HSTS con la política final. Caddy valida la configuración sin aviso de formato.

### E-002 — Lector temporal de correo de prueba

- **Estado inicial:** el script temporal de verificación intentó decodificar nuevamente el mensaje Unicode que devuelve MailHog y falló con `UnicodeDecodeError`; no fue un error de envío del backend.
- **Corrección aplicada:** leer `Content.Body` con su representación Unicode y decodificar solo si indica quoted-printable. El token sintético se guarda únicamente en un archivo privado temporal.
- **Verificación:** Chromium abrió el enlace recibido, cambió la contraseña, rechazó su reutilización e inició sesión con la contraseña nueva. El SMTP recibió exactamente un mensaje; la cuenta desconocida no generó correo.

### A-007 — Datos privados retenidos en el DOM después del logout

- **Estado inicial:** reproducido en Chromium sobre el stack HTTPS. Después de cerrar sesión y llegar al login, `document.body.textContent` todavía contiene el cliente y la empresa sintéticos de la sesión anterior, dentro de páginas ocultas.
- **Causa:** `cacheComponents` conserva páginas con React Activity; `router.replace('/')` cambia de ruta sin descartar ese documento y su estado privado. La API ya invalida la sesión correctamente, pero los datos cargados siguen en memoria/DOM.
- **Corrección aplicada:** `authApi.logout()` descarta el documento tras invalidar la sesión; un 401 en rutas privadas también lleva al login mediante navegación completa. Se eliminan las redirecciones parciales de ambos puntos de logout y del listado de clientes. Mantiene Next Activity durante una sesión válida.
- **Verificación:** prueba nueva reproduce el fallo antes del rebuild y pasa después: datos ocultos ausentes tras cerrar desde empresa y desde selector, e historial sin recuperar la sesión. La reproducción original sobre HTTPS también pasa de `true/true` a `false/false` para cliente/empresa privados en el DOM. Once E2E aprobados tras el cambio.

### E-003 — Selector del smoke de estabilidad

- **Estado inicial:** el script temporal usó `h1` sin distinguir páginas ocultas de Next Activity y falló por múltiples coincidencias.
- **Corrección aplicada:** seleccionar el encabezado visible. Esta investigación permitió descubrir A-007.
- **Verificación:** primera ejecución con 60 cambios de módulo aprobada. Heap tras GC: 5.078.440 → 5.807.148 → 5.963.616 bytes; crecimiento de 885.176 bytes, con cero excepciones JS/5xx. Se repitió sobre la imagen final, con los resultados de la sección Ejecución. Es un smoke breve, no perfilado prolongado.

### A-008 — Dashboard general y accesos de empresa sin estilos

- **Estado inicial:** confirmado en el código antes de editar: `dashboard/page.tsx` y el resumen de empresa usan `workspace-*`, pero `globals.css` no define esas clases. Faltan jerarquía visual, distribución, tarjetas y adaptación móvil. La regla automática de modo oscuro también cambia el texto sobre superficies claras.
- **Corrección aplicada:** estilos completos de sidebar, navegación, cabecera, bienvenida, empresas, módulos y estados. Marca Fracxion consistente, reintento de carga y esquema claro explícito para evitar texto claro sobre tarjetas blancas. Resumen empresarial con iconos, descripciones, contadores de la API y acciones según rol. Adaptación a móvil y reducción de movimiento.
- **Verificación:** la captura previa confirma `workspace-shell` como bloque y sidebar de 1.440 px. En el build corregido, Chromium comprueba sidebar junto al contenido en escritorio, cero desbordamiento horizontal a 1.440/768/390/320 px y navegación por teclado desde empresa hasta módulo. Los cuatro contadores coinciden con respuestas reales de la API. Viewer no recibe creación de borradores ni acceso de auditoría. Carga, error/reintento y lista vacía se verifican con respuestas controladas de navegador. Capturas de ambas vistas en escritorio/móvil inspeccionadas.

### A-009 — Descripción del resumen con contraste insuficiente

- **Estado inicial:** la prueba de legibilidad en Chromium detecta una relación de contraste de **4,45:1** entre la descripción del encabezado y el fondo empresarial, inferior a 4,5:1 para ese tamaño de texto.
- **Corrección aplicada:** color compartido de las descripciones de módulos cambiado de `#64748b` a `#596579`.
- **Verificación:** prueba de contraste del texto visible en el contenido principal aprobada en ambos dashboards a los cuatro anchos, con preferencia de sistema oscura; también se comprueba la preferencia clara. Umbrales: 4,5:1 para texto normal y 3:1 para texto grande. Es una comprobación de esas vistas, no una auditoría completa de accesibilidad del producto.

### E-004 — Selector de alertas de la prueba visual

- **Estado inicial:** el nuevo escenario de error encuentra dos alertas: la de la aplicación y el anunciador accesible de rutas de Next.js.
- **Corrección aplicada:** selección limitada al contenido principal visible. No representa un fallo del reintento de la aplicación.
- **Verificación:** el escenario completa error, reintento contra API real y estado vacío; las tres pruebas específicas y luego la suite completa pasan.

### A-010 — Selector de factura emitida vacío sin explicación

- **Estado inicial:** `PaymentForm` consulta correctamente `status=issued`, pero `ResourceSelect` sigue mostrando «Seleccioná una opción» aunque la API no devuelva registros. La consulta de solo lectura a la base local devuelve cero facturas; no se crean documentos en esa base para hacer aparecer opciones.
- **Corrección aplicada:** mensaje explícito y enlace a Facturas cuando no hay emitidas, selector vacío deshabilitado y explicación diferente para búsquedas sin coincidencias. Los controles de paginación aparecen solo cuando hay otras páginas. Los borradores siguen excluidos; los permisos y las validaciones del backend se conservan.
- **Verificación:** nueva prueba `frontend/e2e/payments.spec.ts` con empresa sintética vacía, borrador ausente del selector, emisión desde UI, opción con número/cliente/saldo, búsqueda sin resultados y recuperación de la opción. Pago parcial desde el módulo Pagos: total 121,00, pago 40,00, saldo 81,00, persistencia tras recarga y respuesta API comprobadas. El E2E comercial anterior registra el pago desde el detalle y no cubría ese selector.

## Ejecución

- Inventario y revisión de autenticación, registro, permisos por empresa, servicios transaccionales, auditoría y configuración de despliegue.
- Línea base: Ruff, formato, `manage.py check`, ESLint y TypeScript aprobados.
- El sandbox impidió inicialmente consultar Docker y el registro npm; las operaciones autorizadas se reintentaron con acceso ampliado. Se creó `facturador-audit-20261010`, con PostgreSQL y credenciales sintéticas, en `127.0.0.1:55433`; el proyecto Compose `facturador-audit-production` agrega el stack HTTPS aislado, con proxy en puertos 8088/8443 de localhost y el resto de los servicios sin puertos publicados.
- `pip-audit -r requirements.txt`: cero vulnerabilidades conocidas en esta consulta.
- Backend completo: **216 pruebas aprobadas** en PostgreSQL real; incluye aislamiento, roles, snapshots, importes, rollback, numeración/pagos concurrentes, recuperación y registro concurrente.
- Cobertura: **91% de sentencias**, 2.007 sentencias y 190 sin ejecutar; umbral de 85% aprobado. No equivale a cobertura de ramas ni ausencia de bugs.
- Ruff/formato, `manage.py check`, ESLint, TypeScript, build standalone, OpenAPI sin advertencias y migraciones sin cambios pendientes: **aprobados**.
- Playwright antes de la corrección visual: **once escenarios aprobados en 28,6 segundos**. Siete flujos UI: persistencia del ciclo cliente/producto/borrador/emisión/pago/reversión/auditoría, viewer, sesión vencida, recuperación, catálogo móvil, registro móvil y descarte de datos privados en logout/historial. Fixture automática comprueba ausencia de excepciones JavaScript y respuestas 5xx en cada flujo.
- Seguridad API en ejecución: **cuatro escenarios aprobados**, con CSRF obligatorio, rechazo de origen ajeno, CORS sin autorización al origen ajeno, `private, no-store`, privilegios falsificados rechazados, datos de empresas ajenas inaccesibles y relaciones cruzadas rechazadas, JSON malformado rechazado con 400.
- `npm audit --omit=dev`: **cero vulnerabilidades conocidas**. Auditoría completa: cinco paquetes de desarrollo afectados por A-003; no se modificaron dependencias para ocultar el aviso. `braces`, `micromatch` y `fast-glob` no aparecen como paquetes en el standalone generado revisado.
- Inspección visual: factura y formulario de registro móvil. Captura de factura actualizada con datos sintéticos.
- Revisión de formatos de secretos en **158 archivos de texto candidatos a Git**: ninguna coincidencia de claves privadas, AWS, GitHub u OpenAI. `.env`, entornos de backend/frontend y fixture de recuperación están ignorados. Es una comprobación de patrones conocidos, no una garantía absoluta contra cualquier dato privado.
- Producción local: **ambas imágenes construidas**, migraciones y `check --deploy --fail-level WARNING` aprobados. Arranque comprobado de PostgreSQL/Redis saludables y Gunicorn/Next standalone/Caddy/SMTP local. Registro desde UI, permisos owner, facturación/pago/reversión/persistencia, auditoría, cookies Secure/HttpOnly/SameSite, CSRF obligatorio, login/logout, health/ready, estáticos Admin y HSTS único de frontend/API aprobados.
- Correo de prueba: **entrega SMTP local y recuperación completas**, token de un solo uso y login posterior aprobados; la cuenta desconocida no genera mensaje. No acredita entrega con un proveedor externo.
- Backup: `pg_dump -Fc` y `pg_restore --no-owner` en otra base vacía del contenedor sintético. Coinciden cantidades de cuentas, empresas, membresías, clientes, productos, facturas, líneas, pagos, reversiones y auditoría, así como total facturado 121,00 y pagos efectivos 0,00. No se tocaron bases reales ni backups externos.
- Estabilidad final: smoke de **60 cambios de módulo** sobre la imagen corregida bajo HTTPS, sin excepciones JS/5xx. Heap tras GC: 5.161.352 → 5.895.384 → 6.074.960 bytes, crecimiento de 913.608 bytes (aproximadamente 0,87 MiB); no muestra crecimiento excesivo en esta ejecución corta.
- Cierre confirmado: API/frontend temporales detenidos; ambos proyectos de prueba sin contenedores, volúmenes ni redes propios pendientes. Puertos 8001, 3010, 55433, 8443 y 8088 sin listeners. Secretos sintéticos, token SMTP y dump temporales eliminados. Código, capturas y log conservados; las imágenes y el navegador instalado permanecen disponibles para nuevas comprobaciones.

### Validación posterior del dashboard

- ESLint sin advertencias, TypeScript y build standalone final: **aprobados**.
- Las tres nuevas pruebas de `frontend/e2e/dashboard.spec.ts` pasan; después se regenera el token de recuperación y se reinicia la API sintética para la suite completa.
- Playwright final con el diseño corregido: **14 escenarios aprobados en 44,3 segundos**, diez flujos UI y cuatro de seguridad API. Sin excepciones JavaScript ni respuestas 5xx en los flujos. Se conserva la regresión de descarte de datos privados tras logout.
- Capturas reales con datos sintéticos: [selector escritorio](screenshots/dashboard-desktop.png), [selector móvil](screenshots/dashboard-mobile.png), [resumen escritorio](screenshots/company-dashboard-desktop.png), [resumen móvil](screenshots/company-dashboard-mobile.png). Preferencia oscura y movimiento reducido comprobados sin cambiar la paleta clara de la aplicación.
- Solo cambia frontend y documentación; las 216 pruebas backend y la comprobación HTTPS Docker corresponden a la ejecución anterior descrita arriba. No se repiten ni se atribuyen al nuevo build visual. Las imágenes anteriores requieren reconstrucción para incorporar este diseño.
- Cierre de esta comprobación: API/frontend detenidos, contenedor `facturador-dashboard-tests` y volumen sintético eliminados, token de recuperación temporal eliminado. Puertos 8001, 3010 y 55433 sin listeners.
- Se recompila después con la configuración local del proyecto: build aprobado, sin dejar incorporada la URL temporal del E2E. Las capturas y resultados de navegador corresponden al entorno sintético descrito.

### Validación posterior del selector de pagos

- ESLint, TypeScript y build standalone para la prueba: **aprobados**.
- Playwright: **15 escenarios aprobados en 47,5 segundos**, once flujos UI y cuatro de seguridad API, sin excepciones JavaScript ni 5xx. Incluye los selectores compartidos de clientes/productos al crear una factura y el nuevo flujo de selección al registrar pago.
- [Captura real del selector de pagos](screenshots/payment-selector.png) inspeccionada en móvil, con datos sintéticos. La base local se consulta solo para el diagnóstico; las operaciones de prueba utilizan PostgreSQL separado y una empresa nueva de pruebas.
- Cierre confirmado: servicios de pruebas en 8001/3010 detenidos, PostgreSQL temporal y volumen eliminados, puerto 55433 libre y token sintético eliminado. Build recompilado correctamente con la configuración local del proyecto.

## Límites

Una revisión y pruebas aprobadas no demuestran que no exista ningún bug, fuga o vulnerabilidad. A-003 sigue pendiente; los demás hallazgos tienen corrección y evidencia descritas arriba. DNS/certificados públicos, entrega SMTP con proveedor real, backups externos, pruebas de carga y perfilado prolongado de memoria requieren comprobaciones adicionales en la infraestructura de destino. Se validó Chromium en este entorno Linux; no una matriz completa de Firefox/WebKit/dispositivos reales.

## Video comercial 3D — 11/10/2026

Entrega independiente en [`video/fracxion-comercial-3d.mp4`](video/fracxion-comercial-3d.mp4): notebook y móvil modelados en Three.js, con capturas existentes de la aplicación y datos sintéticos. Toma continua de 19 segundos, Full HD a 60 fps, scroll lento, fundidos de 1,8 segundos y música instrumental original. Esta tarea no modifica código de la aplicación ni registros de negocio.

### V-001 — Pantallas tapadas por el bisel

- **Evidencia:** las primeras vistas previas muestran ambas pantallas negras; la superficie de imagen coincide con la profundidad exterior del bisel extruido.
- **Corrección:** separación explícita de bisel, imagen, cámara frontal y pieza superior del móvil para eliminar oclusión y conflicto de profundidad.
- **Verificación:** vistas previas de ocho tiempos inspeccionadas y comprobación de luminancia en las pantallas del MP4 final; ambas visibles.

### V-002 — Tamaño del móvil y barra lateral de escritorio

- **Evidencia:** el móvil inicial domina el encuadre; el desplazamiento de la captura completa recorta la marca de la barra lateral de la notebook.
- **Corrección:** escala del móvil ajustada al 80% y separación lateral; composición de scroll que conserva la barra lateral de escritorio. Las imágenes de página mantienen sus proporciones.
- **Verificación:** encuadre de las cuatro esquinas de cada pantalla comprobado en los 1140 fotogramas. Revisión visual del resumen, comprobante, fundidos y cierre extraídos del MP4.

### V-003 — Metadatos de color de la exportación

- **Evidencia:** FFprobe identifica el primer MP4 como `yuvj420p`, rango completo y matriz `bt470bg`, heredados de los JPEG intermedios; la comprobación de entrega esperaba `yuv420p`.
- **Corrección:** conversión explícita del rango y matriz a vídeo BT.709, con `yuv420p` y metadatos de primarias/transferencia. El encoder de origen también incorpora esa conversión para futuros renders.
- **Verificación:** el MP4 final declara H.264, `yuv420p`, rango de vídeo y BT.709; decodificación completa sin errores, 1920 × 1080, 60/1 fps y exactamente 19 segundos. Audio AAC estéreo sin saturación.

### Validación del archivo entregado

- [`video/revision-tecnica.json`](video/revision-tecnica.json): 1140 fotogramas decodificados, cambio máximo entre imágenes de 0,288 niveles sobre 255 en la comprobación reducida, como máximo una repetición consecutiva de un fotograma, scroll móvil limitado a 64,75 px/s y cero errores JavaScript del render.
- Ocho momentos del archivo final inspeccionados: [`video/revision-fotogramas.jpg`](video/revision-fotogramas.jpg). El fundido entre pantallas superpone gradualmente ambas vistas durante la transición; no es un error de duplicación del render.
- SHA-256 conservado en [`video/SHA256SUMS.txt`](video/SHA256SUMS.txt). Escena, audio, renderer y revisión reproducibles en [`video/source/`](video/source/), con dependencias visuales y licencias incluidas.
- El primer intento de reproducción con GPU forzada produce `PIPELINE_ERROR_DISCONNECTED` en el decodificador del navegador de pruebas. La comprobación de reproducción utiliza decodificación por software para separar el archivo de esa limitación del controlador local; su resultado queda en `video/revision-reproduccion.json`.
- Reproducción completa del MP4 final en Chromium: termina en 19 segundos de contenido, a velocidad 1×, sin errores, sin eventos `waiting` ni `stalled`. Se verifican búsquedas a 0/5/10/18,9 s. El compositor local por software informa ocho fotogramas omitidos durante la reproducción; es una limitación medida de ese reproductor, mientras que el archivo contiene los 1140 fotogramas verificados por decodificación independiente.
- Las comprobaciones se refieren al video generado y a Chromium local. Las operaciones comerciales de las capturas pertenecen a las pruebas anteriores; no se vuelven a ejecutar pruebas backend ni E2E de la aplicación para esta entrega.

## Versión dinámica del comercial — 11/10/2026

Nueva entrega: [`video/fracxion-comercial-3d-dinamico.mp4`](video/fracxion-comercial-3d-dinamico.mp4). Conserva 19 segundos, Full HD y 60 fps. Añade cinco posiciones de cámara conectadas por una curva de tangentes continuas, variación suave de distancia/lente, giros y desplazamientos independientes de notebook y móvil. Las sombras se actualizan con los dispositivos. La primera versión permanece disponible y sus informes se archivan en `video/version-1/`.

### Funciones demostradas con evidencia nueva

- PostgreSQL 17 efímero en `127.0.0.1:55435`, contenedor exclusivo `fracxion-video-demo-20261011`, almacenamiento temporal. Configuración E2E con guardas explícitas de base, host y puerto en `video/source/demo_seed.py`.
- Empresa ficticia Demo Fracxion, tres clientes y tres productos; sin datos de negocio del proyecto.
- Flujo real desde Chromium y la API del proyecto: cliente Estudio Sur y servicio Soporte mensual seleccionados, borrador creado y comprobante interno #1 emitido por ARS 1.210,00. Registro de transferencia por ARS 400,00, referencia ficticia DEMO-001; saldo ARS 810,00 comprobado tras recarga.
- Las pantallas muestran clientes, creación y emisión del comprobante, registro del pago e historial/saldo actualizado. Capturas y evidencia del flujo en `video/source/demo-captures/`; el render posterior es independiente de API/base.

### Correcciones durante la revisión

- **V-004 — Captura prematura de estados de carga:** algunas capturas del resumen y del historial conservaban «Cargando información…». Se añade espera explícita de datos/fin de carga y se recapturan mediante consultas, sin nuevos cobros. La evidencia conservada no contiene esos indicadores.
- **V-005 — Acercamiento con base de notebook recortada:** las primeras posiciones acercaban la base al límite inferior del canvas. Se corrige el punto de mirada y se acortan los rótulos para evitar superposición. Se comprueban pantallas y cuerpos completos en cada fotograma. Extremos finales de la notebook: x 399,53–1491,48, y 250,49–989,45; móvil: x 1366,14–1855,69, y 230,60–907,32, dentro de 1920 × 1080.
- **E-006 — Selectores de captura demasiado estrictos:** el nombre accesible de producto incluye SKU y las etiquetas de pago incluyen opciones/ayuda. Se usan celda de la fila, combobox y coincidencia por prefijo. Son correcciones de la automatización de captura, sin cambios en los formularios del producto. El comprobante creado se reutiliza durante los reintentos.

### Validación y cierre

- Sintaxis de JavaScript/Python, referencias de recursos e integridad SHA-256: comprobadas. Decodificación independiente de los **1140 fotogramas**; exactamente **19,00 s**, H.264 `yuv420p` BT.709 y AAC estéreo. Revisión visual de ocho momentos extraídos del MP4.
- Cámara: recorrido horizontal de 4,067 unidades, paso máximo por fotograma de 0,01845 unidades. Giros de ambos dispositivos continuos. Scroll móvil máximo de 53,33 px/s. Cambio máximo entre imágenes: 0,479 niveles sobre 255 en la comprobación reducida; como máximo una repetición consecutiva de fotograma. Audio sin saturación; cero errores JavaScript/WebGL durante el render.
- Chromium reproduce el MP4 final completo a **1×**, sin errores, eventos `waiting`/`stalled` ni fotogramas omitidos en esta comprobación. Búsquedas a 0/5/10/18,9 s correctas. Resultados actuales en `video/revision-tecnica.json` y `video/revision-reproduccion.json`.
- API y frontend de captura detenidos; contenedor PostgreSQL exclusivo eliminado junto con sus datos efímeros. Se conservan únicamente las capturas ficticias y los artefactos de entrega. No se modifica código de la aplicación, configuración persistente ni base de negocio.
- Este flujo comercial específico tiene evidencia nueva. No se vuelve a ejecutar la suite completa backend/E2E y sus resultados anteriores no se atribuyen a esta tarea.
