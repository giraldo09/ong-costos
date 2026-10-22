# Notas sobre los datos (Biable 2025)

Fuente: 12 informes mensuales de Centro de Costos. La base tiene 1,272 filas (111 centros).
Tabla `carga_control` guarda la validación de cada mes contra la fila TOTAL de Biable.

## Correcciones manuales a la fuente

Los 12 meses cuadran al 100 % con la fila TOTAL de Biable, tras 4 correcciones documentadas en
`config/ajustes_manuales.csv` (el script de carga las aplica y las anota en `carga_control.detalle`;
solo se aplican si el valor de la fuente coincide con el esperado).

| Periodo | Centro | Qué se corrigió | Por qué |
|---|---|---|---|
| 202510 | 020320 CLASES DE COCINA NUTRIR | Ingresos $20,732,000, gastos $7,490,346.76 y déficit $13,241,653.24 -> 0 | Copia idéntica de CENA DE GALA (020339); el TOTAL de Biable la cuenta una sola vez |
| 202512 | 020320 CLASES DE COCINA NUTRIR | Déficit $200,000 -> 0 | Arrastre de noviembre: ingresos y gastos en 0, y no está en el TOTAL |

Origen: se detectó comparando la suma de centros contra el TOTAL y revisando el histórico del centro. No se pudo confirmar con quien exporta de Biable.

## Categorías

- 7 categorías de la hoja "TOTALIZACION X TIPO DE CONTRATO" + "Sin categoría" (centros 200210 y 6010).
- GESTAR SSP (20011005) aparece en dos secciones; se asignó a **Propios de Nutrir**
  (mayor parte del monto y es programa GESTAR). Ver `data/processed/decisiones_categoria.csv`.
- Códigos compuestos de la hoja (`0701-0702`, `20011002-03`, etc.) se separaron en sus códigos individuales.

## Uso en Power BI

- Conectar a la vista `vw_costos_powerbi` (modo Importar recomendado: Neon gratuito se duerme tras inactividad).
- `fecha` es siempre el primer día del mes.
- Credenciales: las entrega el responsable de la base por canal privado. No van en git.
