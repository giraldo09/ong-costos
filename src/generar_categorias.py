"""
Genera la asignacion centro -> categoria desde la hoja
"TOTALIZACION X TIPO DE CONTRATO" y reporta ambiguedades.

Salida: data/processed/centro_categoria.csv  (codigo, nombre, categoria, estado)
Uso:    python src/generar_categorias.py [archivo.xls]   (por defecto: el ultimo mes)
"""
import glob
import os
import re
import sys
import unicodedata

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import etl_biable as etl

HOJA_TOT = "TOTALIZACION X TIPO DE CONTRATO"
SIN_CATEGORIA = "Sin categoría"
ESTADO_DECISIONES = os.path.join("data", "processed", "decisiones_categoria.csv")

SECCIONES = {
    "PROMOCION Y FINANCIAMIENTO": "Promoción y Financiamiento",
    "PROPIOS DE NUTRIR": "Propios de Nutrir",
    "AREAS DE APOYO": "Áreas de Apoyo",
    "HOSPITALES INFANTIL": "Hospitales Infantil",
    "OTROS SERVICIOS": "Otros Servicios",
    "CDIS": "CDI's",
    "EJECUCION EXCEDENTES": "Ejecución Excedentes",
}
# Filas "TOTAL xxx" que cierran su seccion (despues de ellas no hay categoria)
CIERRES = {"TOTAL OTROS SERVICIOS", "TOTAL CDIS", "TOTAL EJECUCION EXCEDENTES"}


def norm(s):
    """Mayusculas sin tildes ni signos; tolera texto corrupto por encoding."""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Za-z0-9 ]", " ", s.upper())
    return re.sub(r"\s+", " ", s).strip()


def norm_seccion(s):
    n = norm(s)
    if n.startswith("CDI"):
        n = "CDIS" if n.replace(" ", "") in ("CDIS", "CDI S") or n.startswith("CDI S") else n
    if n.startswith("EJECUCI") and "EXCEDENTES" in n:
        n = "EJECUCION EXCEDENTES"
    return n


def es_codigo(v):
    if pd.isna(v):
        return False
    s = str(v).strip()
    return bool(re.fullmatch(r"\d+(\.0)?(-\d+)*", s))


def codigo_txt(v):
    s = str(v).strip()
    return s[:-2] if s.endswith(".0") else s


def expandir_codigo(cod):
    """'0701-0702' -> 0701, 0702 ; '20011002-03' -> 20011002, 20011003 (sufijo abreviado)."""
    partes = cod.split("-")
    if len(partes) == 1:
        return partes
    base = partes[0]
    out = [base]
    for p in partes[1:]:
        out.append(base[: len(base) - len(p)] + p if len(p) < len(base) and len(p) <= 2 else p)
    return out


def clave(cod):
    """Clave de cruce: ignora ceros a la izquierda (41201 == 041201)."""
    return str(cod).lstrip("0")


def leer_asignacion(path):
    df = pd.read_excel(path, engine="xlrd", sheet_name=HOJA_TOT, header=None)
    actual = None
    filas = []
    for i, r in df.iterrows():
        c0, c1 = r[0], r[1]
        if es_codigo(c0):
            for cod in expandir_codigo(codigo_txt(c0)):
                filas.append({"codigo": cod, "nombre": str(c1).strip(),
                              "categoria": actual, "fila_hoja": i + 1,
                              "codigo_original": codigo_txt(c0)})
            continue
        for celda in (c0, c1):
            if pd.isna(celda):
                continue
            n = norm_seccion(celda)
            if pd.isna(c1) and n in SECCIONES:
                actual = SECCIONES[n]
            elif n in CIERRES:
                actual = None
    return pd.DataFrame(filas)


def archivo_por_defecto():
    fs = [f for f in glob.glob("data/raw/*.xls") if "copia" not in f.lower()]
    meses = list(etl.MESES_ORDEN) if hasattr(etl, "MESES_ORDEN") else None
    orden = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
             "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
    return max(fs, key=lambda f: max((n for m, n in orden.items() if m in f.lower()), default=0))


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else archivo_por_defecto()
    print(f"Archivo base: {os.path.basename(path)}")
    asig = leer_asignacion(path)
    # union de centros de TODOS los informes (el ultimo nombre prevalece)
    fs = sorted((f for f in glob.glob("data/raw/*.xls") if "copia" not in f.lower()), key=lambda f: (f == path, f))
    partes = [etl.extraer_bloques(f, modo="incremental")[["centro_costo_codigo", "centro_costo_nombre"]] for f in fs]
    centros = pd.concat(partes).drop_duplicates("centro_costo_codigo", keep="last")
    print(f"Centros distintos en los 12 informes: {len(centros)}")

    # --- ambiguedades ---
    asig["clave"] = asig.codigo.map(clave)
    dup = asig[asig.duplicated("clave", keep=False)].sort_values("codigo")
    print("\n[1] Codigos presentes en MAS DE UNA seccion:")
    print(dup.to_string(index=False) if len(dup) else "  ninguno")

    asig["clave"] = asig.codigo.map(clave)
    cats_por_codigo = asig.dropna(subset=["categoria"]).groupby("clave")["categoria"].agg(lambda s: sorted(set(s)))
    decisiones = {}
    if os.path.exists(ESTADO_DECISIONES):
        decisiones = dict(pd.read_csv(ESTADO_DECISIONES, dtype=str)[["codigo", "categoria"]].values)
        print(f"\nDecisiones manuales aplicadas desde {ESTADO_DECISIONES}: {decisiones}")

    out = []
    for cod, nom in centros.itertuples(index=False):
        cats = cats_por_codigo.get(clave(cod), [])
        if cod in decisiones:
            cat, est = decisiones[cod], "DECIDIDO"
        elif len(cats) == 1:
            cat, est = cats[0], "OK"
        elif len(cats) > 1:
            cat, est = cats[0], "AMBIGUO"   # provisional: bloquea la carga final
        else:
            cat, est = SIN_CATEGORIA, "SIN_CATEGORIA"
        out.append({"codigo": cod, "nombre": nom, "categoria": cat, "estado": est,
                    "candidatas": " | ".join(cats)})
    res = pd.DataFrame(out)

    sin = res[res.estado == "SIN_CATEGORIA"]
    print(f"\n[2] Centros SIN categoria ({len(sin)}):")
    print(sin[["codigo", "nombre"]].to_string(index=False))

    no_en_mensual = asig[~asig.clave.isin(centros.centro_costo_codigo.map(clave))]
    print(f"\n[3] Codigos de la hoja de totalizacion que NO estan en el informe mensual ({len(no_en_mensual)}):")
    print(no_en_mensual.drop_duplicates("codigo").to_string(index=False) if len(no_en_mensual) else "  ninguno")

    print("\n[4] Centros por categoria:")
    print(res.categoria.value_counts().to_string())

    os.makedirs(os.path.dirname(ESTADO_DECISIONES), exist_ok=True)
    res.to_csv("data/processed/centro_categoria.csv", index=False, encoding="utf-8-sig")
    print("\nGenerado: data/processed/centro_categoria.csv")
    amb = res[res.estado == "AMBIGUO"]
    if len(amb):
        print(f"PENDIENTE: {len(amb)} centro(s) ambiguo(s). Decide y registralo en {ESTADO_DECISIONES} (codigo,categoria).")


if __name__ == "__main__":
    main()
