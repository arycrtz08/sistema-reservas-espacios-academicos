# CampusHub corregido

Versión integrada del sistema de reservas de espacios académicos. Esta carpeta reemplaza los archivos principales del proyecto y conserva SQL Server + Flask.

## Correcciones aplicadas

- Login de estudiante corregido: la validación del carnet ya no falla al cargar la página.
- Administradores con contraseñas cifradas; no se publican contraseñas iniciales en SQL.
- Protección CSRF para todas las acciones `POST`.
- `SECRET_KEY` obligatoria desde `.env` y modo debug desactivado por defecto.
- Nueva pantalla `kite_bloqueado.html`.
- Tabla `EPPHerramienta` creada y conectada al buscador de herramientas.
- Computadoras muestran correctamente cargador y mouse.
- “Mis reservas” ya no muestra el mensaje vacío cuando sí existen resultados.
- Filtros de fecha parametrizados en SQL.
- Cancelación de reservas activas o pendientes desde el historial.
- Salas reservables por fecha y horario, con validación de cruces y bloqueos administrativos.
- Impresoras 3D y CNC se liberan automáticamente al terminar la reserva.
- Límite PLA solo bloquea PLA, no PETG/TPU/Otro.
- Panel de salas para crear y retirar bloqueos.
- Panel KITE para límites PLA, bloqueos y herramientas dañadas/reparadas.
- Panel general con resumen de reservas activas y restablecimiento conservando historial.
- Validaciones atómicas para evitar que dos personas reserven simultáneamente la misma computadora, impresora o CNC.

## Instalación sobre el proyecto actual

1. Haz una copia de respaldo de tu carpeta actual y de la base de datos.
2. Copia estos archivos reemplazando los del proyecto:
   - `proyecto.py`
   - carpeta `templates/`
   - carpeta `static/`
   - `requirements.txt`
   - `.env.template`
3. Ejecuta `database.sql` en SQL Server Management Studio sobre tu servidor. Es idempotente: crea lo faltante sin borrar tus reservas existentes.
4. Crea un archivo `.env` basado en `.env.template` y coloca una clave secreta privada real.
5. Instala dependencias:

```bash
pip install -r requirements.txt
```

6. Crea o cambia las cuentas administrativas de forma segura:

```bash
python crear_admin.py
```

Crea una cuenta para cada tipo que utilices: `gral`, `kite`, `compu` y `salas`.

7. Inicia la aplicación:

```bash
python proyecto.py
```

## Importante sobre las contraseñas anteriores

El repositorio original contenía contraseñas de administradores visibles en `database.sql`. Deben considerarse comprometidas. Ejecuta `crear_admin.py` para reemplazarlas por contraseñas nuevas. El backend también migra una contraseña antigua a hash al iniciar sesión correctamente, pero lo correcto es cambiarlas.

## Archivos antiguos que ya no se necesitan

Las páginas `comp_confirmacion.html` y `comp_reintegracion.html` del proyecto anterior no forman parte del flujo nuevo: la confirmación y devolución de computadoras se administra desde `admin_compu.html`.

## Validación realizada

Se comprobó que:

- `proyecto.py` y `crear_admin.py` compilan correctamente.
- Las plantillas Jinja incluidas tienen sintaxis válida.
- Los formularios que modifican información incluyen token CSRF.

No fue posible ejecutar pruebas contra tu instancia real de SQL Server desde aquí; después de copiar los archivos, prueba login, una reserva de cada tipo y los paneles administrativos usando tu base local.
