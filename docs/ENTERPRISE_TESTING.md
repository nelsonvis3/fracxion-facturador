# Pruebas del desarrollo empresarial

Actualización: 2026-10-15. El entorno temporal del 14 ya no estaba disponible al reanudar. Se creó un clúster sintético nuevo en `/home/nelson/.local/state/fracxion-enterprise-qa/postgres`, con PostgreSQL 18.6 y puerto local 55439. DB de suite `test_postgres`, DB de navegador `test_facturador_e2e`; ninguna base comercial. El runner guarda cada comprobación completada directamente en `docs/enterprise-evidence/2026-10-15-continuous/`, además de su directorio local de QA.

## Estado comprobado más reciente

| Comprobación | Resultado |
| --- | --- |
| Backend | `final-backend-regression`: **353 aprobados**, 65,574 s de tests, teardown correcto en PostgreSQL 18.6. |
| Cobertura | `final-coverage`: **92 %** redondeado, 5.120 sentencias / 403 sin ejecutar; umbral 85 % intacto. |
| Navegador | **52 escenarios únicos / 17 archivos**, completados en varias ejecuciones. Ver `browser-current-summary.json`. La ejecución general recibió SIGTERM tras 39 escenarios; se conserva como interrumpida. `current-browser-remaining` aprobó nueve; `final-browser-regressions` aprobó 14, con solapamiento explícito y sin contar duplicados. |
| Frontend | `final-production-build` Webpack, `final-typecheck` y `final-frontend-lint` aprobados. Recuperación nueva por fragmento y compatibilidad anterior, correo, seguridad y compras repetidos sobre el último build. |
| Contratos | `final-schema` sin warnings; `final-migration-check` sin cambios. |
| Python | `final-backend-lint` y `final-python-format` aprobados; 150 archivos con formato correcto. |
| Recuperación | `recovery-current` y comparación exacta de ambas bases, incluidos 20 eventos y sesión autenticable; dump privado fuera de Git. |
| Dependencias | Python y npm de producción sin avisos conocidos al ejecutar los audits del 15; cinco avisos de desarrollo por una misma cadena de dependencias con braces, sin parche publicado según GHSA-vfj7-8cjw-p6xm. |

Los apartados siguientes conservan los intentos intermedios, errores y correcciones; no sustituyen este estado reciente. No existe validación de producción, Docker/Redis/Caddy/SMTP real, Node 22 o PostgreSQL 17 en esta ejecución.

## Verificación actual — 15 de octubre

| Comprobación | Evidencia / resultado real |
| --- | --- |
| Suite antes de sesiones | `full-backend`: 310 aprobados, teardown correcto. |
| Sesiones | Primer intento: 7/8; la sesión previa a esta función se inventariaba después de responder el primer GET. Se movió su captura antes de la consulta y se conserva captura posterior para login/rotaciones. |
| Sesiones + Admin | `session-controls-tests`: 12 aprobados. |
| Suite con sesiones | `backend-with-sessions`: 318 aprobados, PostgreSQL real; incluye carreras de propietarios, cobros, stock, gastos, workers y lectura consistente. |
| Cobertura | `coverage-current`: 92 % redondeada; 4.524 sentencias, 370 sin ejecutar. Incluye los módulos añadidos; umbral 85 % conservado. |
| Contratos y esquema | `current-schema` sin warnings; `current-migrations` sin cambios pendientes. |
| Estilo Python | `python-current-format`: 138 archivos correctos; `python-current-lint` aprobado. |
| Frontend | Typecheck aprobado, ESLint corregido tras detectar prefer-const en el test de sesiones; build Webpack aprobado. `build-reviewed` aprobado. |
| Navegador — seguridad y gastos | `security-expenses-e2e`: ambos recorridos aprobados. Dos contextos de navegador reales para cambio de contraseña/revocación; gastos/categorías/adjunto/registro/cobros/reversión/exportación y comprobaciones Axe. |
| Revisión visual | Se inspeccionaron capturas de seguridad móvil y detalle de gasto escritorio. Artefactos sintéticos preservados en `2026-10-15-continuous/browser/`. |
| Suite de navegador completa anterior a compras | `full-browser-regression-fixed`: 49 escenarios aprobados en 15 archivos, 436,18 s. Un primer intento falló por un selector ambiguo del test; se corrigió el selector. |

### Compras, privacidad de filtros y recuperación

- `purchases-full-backend`: 338 tests aprobados, 55,129 s de tests. `purchases-coverage`: 91 % redondeado, 4.977 sentencias / 443 sin ejecutar; medición anterior al último filtro UUID. Repetir cobertura general después de ese ajuste.
- `purchases-tests-fixed`: 28 tests de compras/gastos/observabilidad aprobados. Primer intento corrigió la expectativa del test: anónimo usa 401 según el contrato, no 403.
- `filter-privacy-reproduction`: fallo real reproducido en cobros: un ID de factura ajena daba 200, uno inexistente 400. `filter-privacy-fixed`: 18 tests aprobados después de reemplazar ModelChoice por UUIDFilter sobre el queryset autorizado. No permitía leer documentos ajenos, pero constituía una diferencia de respuesta innecesaria.
- `purchases-browser-fixed`: dos recorridos nuevos de compras y regresión de gastos aprobados, con backend real, Axe y medidas 390/768/escritorio. El primer intento de su segundo test intentó registrar una cuenta mientras otra estaba conectada y recibió correctamente 403; se corrigió la preparación cerrando esa sesión.
- `purchases-production-build`, `purchases-frontend-lint`, `purchases-typecheck` aprobados. `purchases-schema` sin warnings y `purchases-migration-check` sin cambios.
- `recovery-source-migrate`, `recovery-seed`, `recovery-dump`, `recovery-restore` y `recovery-verify`: restauración nativa PostgreSQL 18.6 a otra base vacía creada solo para QA, con comparación exacta de comprobantes, pagos/reversión, saldos, stock, gasto y 11 eventos de auditoría. El dump privado no se incluye en Git. No acredita backups externos ni restauración de producción.
- Dependencias: `dependencies-python` y `dependencies-node-production`, cero avisos conocidos. `dependencies-node-all`: cinco avisos de desarrollo por una cadena ESLint/braces; GHSA-vfj7-8cjw-p6xm no publica parche al consultar el 15 de octubre. No se aplican actualizaciones forzadas.

### Identidad y regresión general actual

- `identity-full-backend`: **352 tests aprobados** en PostgreSQL real, 63,522 s de tests y teardown correcto. Incluye confirmación simultánea de correo (un éxito y un rechazo), rollback de reversión con varias líneas, filtro de existencia y formularios Admin antiguos.
- `identity-coverage`: **92 % redondeado**, 5.111 sentencias / 403 sin ejecutar; umbral 85 % conservado. Sustituye la medición anterior a filtros.
- `identity-regression-tests`: 33 aprobados; `email-verification-tests`: 20 aprobados antes de añadir los casos concurrentes. Los tests inspeccionan el mensaje real del backend locmem y rechazan caducidad, manipulación, replay, cambio de correo, cuenta inactiva, falta de CSRF y otra cuenta conectada. Fallos de transporte simulados se presentan como fallo, sin secretos.
- `identity-production-build`, `verification-typecheck`, `verification-frontend-lint`, `identity-python-format` y lint aprobados; `identity-schema` sin warnings; `identity-migration-check` sin cambios.
- `identity-browser-focused-fixed`: dos recorridos de identidad aprobados. El primer intento del test de correo coincidió también con el anunciador de rutas de Next; se acotó su selector al main.
- El navegador obtiene su enlace firmado mediante un helper exclusivamente E2E que exige settings/base/buzón sintéticos; no existe endpoint para leer tokens y esto no se presenta como acceso a un buzón SMTP real.

Los resultados del día anterior que siguen abajo son históricos. Parte de sus logs está conservada en `2026-10-14-continuous/`; los archivos temporales desaparecidos no se reconstruyen ni se presentan como evidencia conservada. Las comprobaciones actuales vuelven a ejecutar el código existente.

## Registro histórico del 14 de octubre

| Comprobación | Resultado |
| --- | --- |
| Primeros tests de propietarios/auth/emisión | 28 aprobados. |
| Primera suite ampliada | 231 aserciones de tests aprobadas, pero teardown falló por cuatro conexiones abiertas de mis nuevos threads. Se corrigió su cierre con connections.close_all. |
| Repetición completa corregida | 231 aprobados y teardown correcto. |
| Settings/logos/invitaciones/vencimientos | Primer intento con dos errores de formato en el serializer estricto; corregido. Repetición: 17 aprobados. |
| Suite con esas funciones | 248 aprobados; cobertura de sentencias 89 % redondeada (umbral 85 % conservado). Se sigue ampliando cobertura de rutas críticas y casos adversariales. |
| Orden de bloqueos de identidad | 23 aprobados después de unificar cuenta antes de empresa. Revisión posterior de FK usa no_key en bloqueos de cuentas. |
| Idempotencia y regresión monetaria/propietarios | 31 aprobados, incluido reintento concurrente de pago completo. |
| OpenAPI | Validación sin warnings después de unificar los choices/enum de roles. |
| ESLint y TypeScript | Aprobados en el estado previo a los últimos tests/arnés. Repetición final pendiente. Typecheck ya genera tipos. |
| Build Webpack | Aprobado con módulos settings/team/accept-invitation/vencimientos; segunda compilación aprobada tras etiqueta accesible de vencimiento. |
| Primer E2E empresarial | 2/4 aprobados. Un selector detectó que la ayuda se incluía en el nombre accesible de vencimiento: se separaron label e hint. Otro selector coincidía con el anunciador vacío de rutas de Next: se acotó a main. Repetición en curso. |

Los mensajes de entrega fallida de correo de una prueba son fallos SMTP simulados deliberadamente, cuyo estado persistido se verifica. No equivalen a envío de correos reales ni a una incidencia de proveedor.

## Aislamiento E2E

`npm run test:e2e` inicia y cierra una API de tests propia por archivo. Requiere frontend compilado en 3010 y puerto 8001 libre; rechaza puerto ocupado y nunca detiene procesos ajenos. Configuración `config.e2e_settings`, correo/caché en memoria y fixtures sintéticos preparados con `scripts/seed_e2e.py`.

Los fixtures de reset e invitación son de uso único; regenerarlos antes de repetir una suite que los consuma. Sus JSON están ignorados por Git. Los tokens de invitación viajan en fragmento del enlace y cuerpo POST, sin ser devueltos por las APIs de gestión ni almacenados en localStorage.

No ejecutar estos fixtures, scripts o ataques controlados sobre una instalación comercial. Las simulaciones comprueban permisos, identificadores entre tenants, payloads malformados, límites y concurrencia con datos locales controlados. Se conserva el umbral de cobertura y la suite existente.

### Revisión posterior al primer pase

- `malformed-admin-reproduction`: identificador inválido en contraseña Admin reproducía un 500 después de introducir el bloqueo. Se corrigió el parseo/rango y se comprueba existencia autorizada antes de cambiar la contraseña o auditar.
- `current-backend-regression`: **353 tests aprobados**, 67,417 s de tests y teardown correcto. Incluye identificadores inválidos/fuera de rango/inexistentes sin 500 ni evento falso de cambio de contraseña.
- `recovery-current` y `recovery-current-comparison.json`: backup/restauración del esquema actual entre dos bases nuevas distintas de las anteriores. Comparación exacta: comprobante 121,00; cobrado 30,00; cartera 91,00; gasto 121,00/pagado 20,00/saldo 101,00; stock 4,000; pedido con dos recepciones y una reversión, recibido efectivo 1,000; correo verificado; sesión restaurada autenticable; 20 eventos de auditoría. Ningún dump o cookie se agrega a Git.

Se parseó YAML de Compose y CI con PyYAML disponible. Eso comprueba sintaxis/estructura, no arranque de contenedores ni ejecución de GitHub Actions. CI conserva trazas de Playwright y logs sintéticos de API/frontend ante fallos.

### Limpieza posterior a pruebas

Se detuvieron únicamente frontend y PostgreSQL propios de QA. Se conservaron las bases sintéticas, dumps privados y el build ejecutable; se eliminaron caché de compilación `.next/cache`, caché Ruff de QA, salidas temporales de Playwright y los dos JSON de tokens sintéticos regenerables. Rutas, tamaños y número de archivos en `cleanup.json`. No se eliminaron dependencias, datos comerciales, migraciones o volúmenes. Los artefactos seleccionados ya estaban preservados en la evidencia.
