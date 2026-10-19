"""
etl_biable.py
--------------
Extraccion y transformacion de los informes de Centro de Costos exportados
desde Biable (.xls) hacia un formato "largo" (tidy) listo para cargar a
PostgreSQL.

Estructura detectada en los archivos (hoja "MES ANTERIOR MES ACTUAL"):
- Fila 0-1: codigos de periodo (YYYYMM) repetidos cada 9 columnas
- Fila 2: encabezados de cada bloque mensual:
    [blank, NOMBRE_MES, CENTRO DE COSTOS, INGRESOS OPERACIONALES,
     INGRESOS NO OPERACIONALES, GASTOS OPERACIONALES,
     GASTOS NO OPERACIONALES, COSTOS, DEFICIT O EXCEDENTE]
- Fila 4 en adelante: una fila por centro de costos (columna 1 = codigo,
  columna 2 = nombre), con los valores de cada concepto por bloque.
- Hay filas completamente vacias que actuan como separadores -> se ignoran.

Cada archivo mensual trae el HISTORICO COMPLETO desde el primer periodo
registrado hasta el mes del archivo (el reporte "crece" cada mes). Por eso
este script ofrece dos modos de lectura:

  - modo="historico"   -> devuelve TODOS los periodos que trae el archivo
  - modo="incremental" -> devuelve SOLO el ultimo periodo (el mas nuevo),
                           para simular una carga semanal/mensual real,
                           como si cada archivo fuera una actualizacion
                           nueva del sistema.
"""

import re
import glob
import os
from datetime import datetime

import pandas as pd

HOJA = "MES ANTERIOR MES ACTUAL"
ANCHO_BLOQUE = 9  # columnas por bloque mensual
FILA_PERIODOS = 0
FILA_ENCABEZADOS = 2
FILA_INICIO_DATOS = 4

COLUMNAS_CONCEPTO = [
    "ingresos_operacionales",
    "ingresos_no_operacionales",
    "gastos_operacionales",
    "gastos_no_operacionales",
    "costos",
    "deficit_excedente",
]


def _limpiar_numero(valor):
    """Convierte celdas de Biable (a veces texto, a veces numero) a float."""
    if pd.isna(valor):
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip().replace(",", "")
    if texto in ("", "-", "nan"):
        return 0.0
    try:
        return float(texto)
    except ValueError:
        raise ValueError(f"Valor no numerico en la fuente: {valor!r}")


def _leer_hoja_cruda(path):
    return pd.read_excel(path, engine="xlrd", sheet_name=HOJA, header=None)


def _periodos_disponibles(df_crudo):
    """Devuelve lista de (indice_columna_inicio_bloque, periodo) en orden."""
    fila = df_crudo.iloc[FILA_PERIODOS]
    bloques = []
    col = 0
    n_cols = df_crudo.shape[1]
    while col < n_cols:
        # el periodo (YYYYMM) aparece en la 4a columna del bloque
        # (offset +3: blank, blank, blank, PERIODO, blank, blank, blank, blank, blank)
        idx_periodo = col + 3
        periodo_val = fila[idx_periodo] if idx_periodo < n_cols else None
        if pd.notna(periodo_val):
            try:
                periodo = int(periodo_val)
                bloques.append((col, periodo))
            except (ValueError, TypeError):
                pass
        col += ANCHO_BLOQUE
    return bloques


def extraer_bloques(path, modo="historico"):
    """
    Lee un archivo "Informe Centro de Costos <Mes> <Año>.xls" y devuelve
    un DataFrame largo (tidy) con una fila por (periodo, centro_costo).

    modo="historico"   -> todos los periodos que trae el archivo
    modo="incremental" -> solo el periodo mas reciente del archivo
    """
    df_crudo = _leer_hoja_cruda(path)
    bloques = _periodos_disponibles(df_crudo)

    if not bloques:
        raise ValueError(f"No se detectaron bloques de periodo en {path}")

    if modo == "incremental":
        bloques = [bloques[-1]]  # solo el ultimo (mas reciente)

    filas_datos = df_crudo.iloc[FILA_INICIO_DATOS:]
    registros = []

    for col_inicio, periodo in bloques:
        col_codigo = col_inicio + 1
        col_nombre = col_inicio + 2
        cols_valores = [col_inicio + 3 + i for i in range(len(COLUMNAS_CONCEPTO))]

        for _, fila in filas_datos.iterrows():
            codigo = fila[col_codigo]
            nombre = fila[col_nombre]

            # filas separadoras totalmente vacias -> se ignoran
            if pd.isna(codigo) and pd.isna(nombre):
                continue

            if isinstance(codigo, float) and codigo.is_integer():
                codigo = int(codigo)  # evita '20011005.0'
            codigo = str(codigo).strip() if pd.notna(codigo) else None
            nombre = str(nombre).strip() if pd.notna(nombre) else None

            if not codigo:
                continue

            # la fila 'TOTAL' es el gran total del reporte: no es un centro
            # de costo (sumarla duplicaria todo). Se excluye de los hechos.
            if codigo.upper() == "TOTAL":
                continue

            registro = {
                "periodo": periodo,
                "centro_costo_codigo": codigo,
                "centro_costo_nombre": nombre,
            }
            for nombre_col, idx_col in zip(COLUMNAS_CONCEPTO, cols_valores):
                valor = fila[idx_col] if idx_col < len(fila) else None
                registro[nombre_col] = _limpiar_numero(valor)

            registros.append(registro)

    df_largo = pd.DataFrame(registros)
    df_largo["archivo_origen"] = os.path.basename(path)
    df_largo["fecha_carga"] = datetime.now().isoformat(timespec="seconds")
    return df_largo


def extraer_totales(path, modo="incremental"):
    """Devuelve {periodo: {concepto: valor}} con la fila 'TOTAL' del reporte (solo para validar)."""
    df_crudo = _leer_hoja_cruda(path)
    bloques = _periodos_disponibles(df_crudo)
    if modo == "incremental":
        bloques = [bloques[-1]]
    filas = df_crudo.iloc[FILA_INICIO_DATOS:]
    totales = {}
    for col_inicio, periodo in bloques:
        for _, fila in filas.iterrows():
            cod = fila[col_inicio + 1]
            if pd.notna(cod) and str(cod).strip().upper() == "TOTAL":
                totales[periodo] = {
                    n: _limpiar_numero(fila[col_inicio + 3 + i])
                    for i, n in enumerate(COLUMNAS_CONCEPTO)
                }
                break
    return totales


def dimension_centros_costo(df_largo):
    """Tabla de dimension: un registro por centro de costo (codigo+nombre)."""
    dim = (
        df_largo[["centro_costo_codigo", "centro_costo_nombre"]]
        .drop_duplicates(subset="centro_costo_codigo")
        .sort_values("centro_costo_codigo")
        .reset_index(drop=True)
    )
    return dim


def procesar_carpeta(carpeta, modo="incremental", patron="*.xls"):
    """
    Procesa todos los archivos .xls de una carpeta, EN ORDEN CRONOLOGICO
    (por nombre de mes), y concatena los resultados.

    Ignora archivos que contengan 'copia' en el nombre (duplicados).
    """
    meses_orden = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
        "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9,
        "octubre": 10, "noviembre": 11, "diciembre": 12,
    }

    def clave_orden(path):
        nombre = os.path.basename(path).lower()
        for mes, num in meses_orden.items():
            if mes in nombre:
                return num
        return 99

    archivos = [
        f for f in glob.glob(os.path.join(carpeta, patron))
        if "copia" not in os.path.basename(f).lower()
    ]
    archivos.sort(key=clave_orden)

    partes = []
    for archivo in archivos:
        print(f"Procesando: {os.path.basename(archivo)}")
        df_parte = extraer_bloques(archivo, modo=modo)
        partes.append(df_parte)

    df_total = pd.concat(partes, ignore_index=True)
    return df_total


if __name__ == "__main__":
    import sys

    carpeta = sys.argv[1] if len(sys.argv) > 1 else "."
    modo = sys.argv[2] if len(sys.argv) > 2 else "incremental"

    df_resultado = procesar_carpeta(carpeta, modo=modo)
    print(f"\nTotal de registros generados: {len(df_resultado)}")
    print(f"Periodos incluidos: {sorted(df_resultado['periodo'].unique())}")
    print(f"Centros de costo distintos: {df_resultado['centro_costo_codigo'].nunique()}")

    salida = f"hechos_costos_{modo}.csv"
    df_resultado.to_csv(salida, index=False, encoding="utf-8-sig")
    print(f"\nArchivo generado: {salida}")

    dim = dimension_centros_costo(df_resultado)
    dim.to_csv("dim_centros_costo.csv", index=False, encoding="utf-8-sig")
    print(f"Archivo generado: dim_centros_costo.csv ({len(dim)} centros de costo)")
