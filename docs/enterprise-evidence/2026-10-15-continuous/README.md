# Evidencia local — revisión continua del 15 de octubre

Cada comando terminado se conserva con un `.txt` de salida real y un `.json` con comando, directorio, código de salida y duración observada. Los resultados parciales o fallidos permanecen visibles. El nombre de un archivo no constituye evidencia de aprobación; comprobar su `exit_code`.

Entorno: Bash, Python 3.14.7, PostgreSQL nativo 18.6 aislado en 127.0.0.1:55439, Node 24.21.0, Brave instalado como ejecutable Chromium de Playwright. Correo y caché de tests en memoria. No se ejecutan correos reales ni pruebas sobre producción. Compose/CI declaran otras versiones de Node/PostgreSQL; esta evidencia no acredita Docker, Redis, HTTPS/Caddy o SMTP real.

`browser/` contiene capturas y exportaciones de empresas/cuentas sintéticas. Las capturas no sustituyen los tests funcionales. Los dumps de bases de datos, cookies, tokens de fixtures y secretos no deben añadirse aquí.

La revisión sigue en curso. Consultar `../../ENTERPRISE_TESTING.md` y `../../ENTERPRISE_CHANGELOG.md` para alcance y limitaciones. No hay despliegue o publicación de estos cambios.
