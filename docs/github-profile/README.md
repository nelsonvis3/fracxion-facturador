# Nelson Sivisstum

### Full Stack Developer · React, Next.js y Django

Desarrollo aplicaciones web, desde la interfaz y los flujos de usuario hasta la API y el modelo de datos. Trabajo principalmente con React, Next.js, TypeScript, Python y Django.

Mis proyectos más desarrollados son Fracxion, un sistema de gestión comercial para varias empresas, y Ragnar Suplementos, una tienda online para un emprendimiento local. En ambos trabajo sobre el recorrido completo: lo que ve el usuario, las operaciones que resuelve el servidor y los datos que quedan guardados.

Me interesa resolver los detalles que aparecen cuando una aplicación empieza a usarse: un pedido que se reintenta, dos operaciones sobre el mismo stock o un pago que llega después de lo esperado. Ahí entran las decisiones de arquitectura, los permisos y las pruebas.

## Tecnologías

| Área | Herramientas |
| --- | --- |
| Frontend | HTML, CSS, JavaScript, React, Next.js, TypeScript, Tailwind CSS y Zustand. |
| Backend | Python, Django y Django REST Framework. |
| Datos y servicios | PostgreSQL, SQLite y Supabase. |
| Verificación | Pruebas de Django, Playwright, TypeScript y ESLint. |
| Trabajo diario | Git, GitHub, Linux, VS Code y Vite. |

## Proyectos destacados

### Fracxion

Sistema de gestión empresarial para administrar clientes, productos y servicios, facturas internas y cobros de varias empresas. Cada usuario accede a sus espacios de trabajo mediante una membresía con permisos propios.

El recorrido comercial permite crear un cliente, preparar un documento con los precios del catálogo, emitirlo, registrar pagos parciales o totales y consultar su historial. Las reversiones conservan el pago original y actualizan el saldo pendiente.

El desafío principal es conservar la consistencia de la información y respetar los límites entre empresas. Algunas decisiones de implementación:

- **Acceso por empresa y rol.** Las consultas y las operaciones comprueban la membresía y los permisos en el backend.
- **Importes calculados en el servidor.** Uso de `Decimal` para los cálculos monetarios y validación del saldo al registrar un cobro.
- **Operaciones concurrentes.** Transacciones y bloqueos de filas en PostgreSQL para coordinar la numeración de documentos y los pagos simultáneos.
- **Historial comercial.** Cada documento conserva los datos del cliente y del catálogo utilizados al crearlo, aunque después se editen.
- **Auditoría.** El registro de actividad se guarda en la misma transacción que la operación comercial.
- **Pruebas.** Cobertura de permisos, aislamiento entre empresas, integridad, concurrencia y recorridos completos en el navegador.

La interfaz adapta su navegación a escritorio y móvil e incluye estados de carga, errores y reintentos. La entrada y salida de sesión incorporan animaciones de marca con Hyperframes y GSAP, con omisión y movimiento reducido.

Los comprobantes son de gestión interna; la integración fiscal con ARCA y el cobro de suscripciones quedan fuera del alcance actual.

**Stack:** Next.js · React · TypeScript · Tailwind CSS · Django · Django REST Framework · PostgreSQL · Hyperframes · GSAP

[Ver repositorio y documentación →](https://github.com/nelsonvis3/fracxion-facturador)

### Ragnar Suplementos

Tienda online para un emprendimiento local de suplementos deportivos en Formosa. Incluye catálogo de productos y combos, selección de sabores, carrito persistente, pedidos y administración del catálogo.

El comprador puede elegir productos, calcular el envío y completar un pedido como invitado o con una cuenta. El negocio dispone de una interfaz para gestionar imágenes, precios, sabores, stock y publicación de artículos, además del administrador de Django para revisar pedidos y pagos manuales.

El desafío principal está en coordinar catálogo, inventario y pagos durante la compra. Algunas decisiones de implementación:

- **Catálogo centralizado.** Django sirve los productos y vuelve a validar precios y disponibilidad al crear el pedido.
- **Reservas de inventario.** Transacciones y bloqueos de filas coordinan el stock; cada combo consume unidades de sus productos y las reservas se liberan al cancelar o vencer.
- **Reintentos de compra.** Una clave de idempotencia identifica el intento de checkout y permite recuperar el mismo pedido al repetir la solicitud.
- **Verificación de pagos.** La integración con Mercado Pago valida la firma del webhook y consulta al proveedor para comprobar el importe, la moneda y el pedido antes de aprobarlo.
- **Envíos locales.** La cotización se calcula con servicios de mapas y rutas, tiene vencimiento y se valida contra la dirección al confirmar la compra.
- **Administración e historial.** Los permisos protegen el catálogo y cada pedido conserva sus artículos y precios. Las pruebas cubren acceso, edición de stock, combos y conservación de compras anteriores.

La interfaz funciona en escritorio y móvil, con temas claro y oscuro. Zustand mantiene el carrito entre visitas. Las imágenes, el correo y los pagos utilizan integraciones configurables con Cloudinary, SMTP y Mercado Pago; su funcionamiento en producción depende de la configuración y verificación de esos servicios.

**Stack:** Next.js · React · TypeScript · Tailwind CSS · Zustand · Django · Django REST Framework · PostgreSQL

[Ver repositorio y documentación →](https://github.com/nelsonvis3/ragnarsuplementosfsa)

## En qué estoy profundizando

- Diseño de APIs REST y organización de la lógica de negocio.
- Modelado de datos, transacciones y operaciones concurrentes.
- Autenticación, autorización y separación de datos entre empresas.
- Pruebas automatizadas que recorren los flujos completos de la aplicación.
- Despliegue, documentación y mantenimiento de proyectos.

## Objetivo profesional

Busco sumarme a un equipo donde pueda aportar con React, Next.js y Django, aprender de otras personas y participar en las decisiones del producto. Me interesa trabajar tanto en una interfaz clara como en la lógica que sostiene cada operación, y acompañar el desarrollo con pruebas y documentación útil.

## Contacto

- [Portfolio →](https://nelsonvis-portfolio.vercel.app/)
- [LinkedIn →](https://www.linkedin.com/in/nelson-sivisstum-4777a32b4)
- [GitHub →](https://github.com/nelsonvis3)
- **Teléfono:** 11-70625896
