USE InformationUSR;
GO

IF COL_LENGTH('DetallePrestamo', 'estado') IS NULL
BEGIN
    ALTER TABLE DetallePrestamo
    ADD estado NVARCHAR(20) NOT NULL
        CONSTRAINT DF_DetallePrestamo_estado DEFAULT 'Prestada' WITH VALUES;
END
GO

IF COL_LENGTH('DetallePrestamo', 'fecha_devolucion') IS NULL
BEGIN
    ALTER TABLE DetallePrestamo ADD fecha_devolucion DATETIME NULL;
END
GO

UPDATE dp
SET dp.estado='Devuelta',
    dp.fecha_devolucion=COALESCE(dp.fecha_devolucion, ph.fecha_devolucion, GETDATE())
FROM DetallePrestamo dp
JOIN PrestamosHerramienta ph ON ph.id_prestamo=dp.id_prestamo
WHERE ph.estado='Devuelto' AND dp.estado='Prestada';
GO
