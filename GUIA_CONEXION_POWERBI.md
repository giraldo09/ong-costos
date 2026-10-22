# Cómo conectarse a la base de datos desde Power BI

La base está en la nube (Neon / PostgreSQL) y ya tiene todos los datos de 2025.
Solo tienes permiso de **lectura**: no puedes dañar ni cambiar nada.

## Lo que necesitas (te lo pasa Santiago por privado)

| Dato | Valor |
|---|---|
| Servidor | `ep-old-rice-b5q2ub9q.c-7.us-east-2.aws.neon.tech:5432` |
| Base de datos | `neondb` |
| Usuario | `powerbi_lector` |
| Contraseña | *(te la pasa Santiago por mensaje privado; son 24 letras y números)* |

## Pasos en Power BI Desktop

1. Abre **Power BI Desktop** (gratis; búscalo en la Microsoft Store si no lo tienes).
2. Pulsa **Obtener datos**, escribe `PostgreSQL`, elige **Base de datos PostgreSQL** y pulsa **Conectar**.
3. En la ventana que aparece:
   - **Servidor:** `ep-old-rice-b5q2ub9q.c-7.us-east-2.aws.neon.tech:5432`
   - **Base de datos:** `neondb`
   - **Modo de conectividad:** **Importar**
   - Pulsa **Aceptar**.
4. Te pide credenciales. Elige la pestaña **Base de datos** (no "Windows" ni "Cuenta de Microsoft"):
   - **Nombre de usuario:** `powerbi_lector`
   - **Contraseña:** pega **solo** la contraseña, sin espacios antes ni después.
   - Pulsa **Conectar**.
5. En el **Navegador** marca `public.vw_costos_powerbi` (la principal).
   Opcional: `public.dim_categoria` y `public.dim_centro_costo`.
6. Pulsa **Cargar**.

## Cómo saber que funcionó

- En el panel **Datos** (derecha) aparece `vw_costos_powerbi` con: `fecha`, `categoria`, `codigo_centro`, `centro_costo`, `ingresos_operacionales`, `ingresos_no_operacionales`, `gastos_operacionales`, `gastos_no_operacionales`, `costos`, `deficit_excedente`.
- Una tarjeta con el **recuento** de `codigo_centro` debe dar **1,272**.

## Si algo falla

| Problema | Qué hacer |
|---|---|
| "No hemos podido autenticarle" | Casi siempre es la contraseña: bórrala y pega solo la contraseña, sin espacios ni nada más. |
| Sigue fallando | En el campo contraseña prueba: `endpoint=ep-old-rice-b5q2ub9q$TU_CONTRASEÑA` (todo junto, sin espacios). |
| Tarda mucho o da tiempo agotado | La base se duerme tras un rato sin uso. Espera unos segundos y reintenta. |
| Quedó guardada una credencial mala | Archivo → Opciones → Configuración de origen de datos → Permisos → Borrar permisos, y vuelve al paso 3. |

## Cosas que conviene saber

- La columna `fecha` es siempre el **primer día del mes**. Para ver meses, en el eje usa la jerarquía y elige **Mes**.
- `vw_costos_powerbi` sola alcanza para todos los gráficos; ya trae categoría y centro en cada fila.
- Antes de comparar con Biable, lee `NOTAS_DATOS.md`: explica 4 correcciones hechas a la fuente.
- La contraseña no queda guardada dentro del archivo `.pbix`, así que se puede compartir el archivo sin riesgo.
- No pongas la contraseña en chats de grupo, ni en documentos ni en git.
