# Notas sobre los datos (Biable 2025)

Fuente: 12 informes mensuales de Centro de Costos. La base tiene 1,272 filas (111 centros).
Tabla `carga_control` guarda la validación de cada mes contra la fila TOTAL de Biable.

## Diferencias conocidas (vienen de la fuente, no se corrigieron)

| Periodo | Diferencia (suma de centros - TOTAL) | Causa probable |
|---|---|---|
| 202510 | +$20,732,000 ingresos operacionales, +$7,490,346.76 gastos operacionales, +$13,241,653.24 déficit/excedente | Los centros 020339 (CENA DE GALA NUTRIR) y 020320 (CLASES DE COCINA NUTRIR) traen valores idénticos; parece un duplicado en el reporte. **Por confirmar con quien exporta de Biable.** |
| 202512 | +$200,000 déficit/excedente | Diferencia presente en la fuente. |

Los otros 10 meses cuadran exacto con el TOTAL.

## Categorías

- 7 categorías de la hoja "TOTALIZACION X TIPO DE CONTRATO" + "Sin categoría" (centros 200210 y 6010).
- GESTAR SSP (20011005) aparece en dos secciones; se asignó a **Propios de Nutrir**
  (mayor parte del monto y es programa GESTAR). Ver `data/processed/decisiones_categoria.csv`.
- Códigos compuestos de la hoja (`0701-0702`, `20011002-03`, etc.) se separaron en sus códigos individuales.

## Uso en Power BI

- Conectar a la vista `vw_costos_powerbi` (modo Importar recomendado: Neon gratuito se duerme tras inactividad).
- `fecha` es siempre el primer día del mes.
- Credenciales: las entrega el responsable de la base por canal privado. No van en git.
