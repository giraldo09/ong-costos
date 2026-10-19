-- Esquema ONG costos (PostgreSQL / Neon). Idempotente: se puede re-ejecutar.

CREATE TABLE IF NOT EXISTS dim_categoria (
    categoria_id SERIAL PRIMARY KEY,
    nombre       TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS dim_centro_costo (
    centro_id    SERIAL PRIMARY KEY,
    codigo       TEXT NOT NULL UNIQUE,
    nombre       TEXT NOT NULL,
    categoria_id INT  NOT NULL REFERENCES dim_categoria(categoria_id)
);

CREATE TABLE IF NOT EXISTS hechos_costos (
    hecho_id                  BIGSERIAL PRIMARY KEY,
    periodo                   INT NOT NULL CHECK (periodo BETWEEN 190001 AND 299912 AND periodo % 100 BETWEEN 1 AND 12),
    centro_id                 INT NOT NULL REFERENCES dim_centro_costo(centro_id),
    ingresos_operacionales    NUMERIC(18,2) NOT NULL DEFAULT 0,
    ingresos_no_operacionales NUMERIC(18,2) NOT NULL DEFAULT 0,
    gastos_operacionales      NUMERIC(18,2) NOT NULL DEFAULT 0,
    gastos_no_operacionales   NUMERIC(18,2) NOT NULL DEFAULT 0,
    costos                    NUMERIC(18,2) NOT NULL DEFAULT 0,
    deficit_excedente         NUMERIC(18,2) NOT NULL DEFAULT 0,
    cargado_en                TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_hechos_periodo_centro UNIQUE (periodo, centro_id)
);
CREATE INDEX IF NOT EXISTS ix_hechos_centro ON hechos_costos(centro_id);

CREATE TABLE IF NOT EXISTS carga_control (
    carga_id        SERIAL PRIMARY KEY,
    archivo         TEXT NOT NULL,
    periodo         INT  NOT NULL,
    fecha_carga     TIMESTAMPTZ NOT NULL DEFAULT now(),
    total_centros   INT  NOT NULL,
    -- suma de los centros
    suma_ingresos_operacionales    NUMERIC(18,2),
    suma_ingresos_no_operacionales NUMERIC(18,2),
    suma_gastos_operacionales      NUMERIC(18,2),
    suma_gastos_no_operacionales   NUMERIC(18,2),
    suma_costos                    NUMERIC(18,2),
    suma_deficit_excedente         NUMERIC(18,2),
    -- fila TOTAL reportada por Biable
    total_ingresos_operacionales    NUMERIC(18,2),
    total_ingresos_no_operacionales NUMERIC(18,2),
    total_gastos_operacionales      NUMERIC(18,2),
    total_gastos_no_operacionales   NUMERIC(18,2),
    total_costos                    NUMERIC(18,2),
    total_deficit_excedente         NUMERIC(18,2),
    -- diferencia = suma de centros - TOTAL
    dif_ingresos_operacionales    NUMERIC(18,2),
    dif_ingresos_no_operacionales NUMERIC(18,2),
    dif_gastos_operacionales      NUMERIC(18,2),
    dif_gastos_no_operacionales   NUMERIC(18,2),
    dif_costos                    NUMERIC(18,2),
    dif_deficit_excedente         NUMERIC(18,2),
    estado          TEXT NOT NULL CHECK (estado IN ('OK','DIFERENCIA','SIN_TOTAL')),
    detalle         TEXT,
    CONSTRAINT uq_carga_archivo_periodo UNIQUE (archivo, periodo)
);

CREATE OR REPLACE VIEW vw_costos_powerbi AS
SELECT make_date(h.periodo / 100, h.periodo % 100, 1) AS fecha,
       cat.nombre  AS categoria,
       c.codigo    AS codigo_centro,
       c.nombre    AS centro_costo,
       h.ingresos_operacionales,
       h.ingresos_no_operacionales,
       h.gastos_operacionales,
       h.gastos_no_operacionales,
       h.costos,
       h.deficit_excedente
FROM hechos_costos h
JOIN dim_centro_costo c  ON c.centro_id = h.centro_id
JOIN dim_categoria   cat ON cat.categoria_id = c.categoria_id;
