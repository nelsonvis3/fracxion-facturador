# Frontend de Fracxion

Next.js App Router, React, TypeScript y Tailwind CSS. Clientes, catálogo, facturas internas, cobros y auditoría consumen la API Django; la sesión utiliza cookies y CSRF. No se calculan totales contables en el navegador.

```sh
cp -n .env.example .env.local
npm ci
npm run dev
```

La API local debe responder en `http://localhost:8000`. Usar el mismo hostname en ambos servicios. **Crear cuenta** desde el login abre `/register`: el alta crea una empresa y su propietario, inicia sesión y lleva al resumen. Los permisos y las validaciones definitivas pertenecen al backend.

```sh
npm run lint
npm run typecheck
npm run build
env PORT=3000 HOSTNAME=localhost npm run start
```

El build genera un servidor standalone; `postbuild` incorpora `public/` y `.next/static/`. La variable pública de API se fija al compilar. Docker utiliza el mismo dominio y rutas `/api/`.

Para arquitectura, funcionalidades y permisos: [README del proyecto](../README.md). Para Playwright y datos sintéticos: [TESTING.md](../docs/TESTING.md). Para HTTPS y producción: [OPERATIONS.md](../docs/OPERATIONS.md).
