-- Rol de solo lectura para Power BI. Ejecutar en Neon (SQL Editor) como propietario.
-- 1) Reemplaza <PEGAR_CONTRASEÑA> por una contraseña generada por ti (no la compartas en chats ni en git).
-- 2) Revisa el nombre de la base (aqui: neondb); cambia si es otro.
CREATE ROLE powerbi_lector WITH LOGIN PASSWORD '<PEGAR_CONTRASEÑA>';

GRANT CONNECT ON DATABASE neondb TO powerbi_lector;
GRANT USAGE ON SCHEMA public TO powerbi_lector;

-- Solo la vista y las dimensiones (los hechos quedan accesibles a traves de la vista)
GRANT SELECT ON vw_costos_powerbi, dim_categoria, dim_centro_costo TO powerbi_lector;

-- Opcional: tambien la tabla de control de cargas, para auditar validaciones
-- GRANT SELECT ON carga_control TO powerbi_lector;

-- Nota: una vista se ejecuta con los permisos de su propietario, por eso el rol
-- puede leer la vista sin tener SELECT directo sobre hechos_costos.
