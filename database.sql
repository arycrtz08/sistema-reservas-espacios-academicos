CREATE DATABASE InformationUSR;
GO
USE InformationUSR;
GO
CREATE TABLE Usuarios (
    id INT PRIMARY KEY IDENTITY(1,1),
    usuario NVARCHAR(100),
    carnet_us NVARCHAR(50),
    cohorte_sel NVARCHAR(50),
    fecha_registro DATETIME DEFAULT GETDATE()
);