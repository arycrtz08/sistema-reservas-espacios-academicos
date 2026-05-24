-- CampusHub corregido - instalación/migración idempotente para SQL Server
IF DB_ID('InformationUSR') IS NULL CREATE DATABASE InformationUSR;
GO
USE InformationUSR;
GO

IF OBJECT_ID('Usuarios','U') IS NULL
CREATE TABLE Usuarios(
 id_usuario INT IDENTITY PRIMARY KEY, usuario NVARCHAR(100) NOT NULL,
 carnet_us NVARCHAR(50) NOT NULL UNIQUE, cohorte_sel NVARCHAR(50) NOT NULL,
 rol NVARCHAR(20) DEFAULT 'estudiante', fecha_registro DATETIME DEFAULT GETDATE()
);
GO
IF OBJECT_ID('Administradores','U') IS NULL
CREATE TABLE Administradores(
 id_admin INT IDENTITY PRIMARY KEY, usuario NVARCHAR(50) NOT NULL UNIQUE,
 contrasena NVARCHAR(255) NOT NULL, tipo NVARCHAR(20) NOT NULL
);
GO
-- No se insertan contraseñas públicas. Ejecuta crear_admin.py para crear administradores con hash.

IF OBJECT_ID('LogsIngreso','U') IS NULL
CREATE TABLE LogsIngreso(id_log INT IDENTITY PRIMARY KEY,carnet_us NVARCHAR(50) NOT NULL,fecha_hora_ingreso DATETIME DEFAULT GETDATE());
GO
IF OBJECT_ID('Salas','U') IS NULL
CREATE TABLE Salas(id_sala INT IDENTITY PRIMARY KEY,nombre NVARCHAR(100) NOT NULL,capacidad_min INT DEFAULT 2,capacidad_max INT DEFAULT 6,disponible BIT DEFAULT 1);
GO
IF NOT EXISTS(SELECT 1 FROM Salas)
 INSERT INTO Salas(nombre) VALUES ('Sala KEY001'),('Sala KEY002'),('Sala KEY003'),('Sala KEY004'),('Sala KEY005'),('Sala KEY006');
GO
IF OBJECT_ID('BloqueoSalas','U') IS NULL
CREATE TABLE BloqueoSalas(id_bloqueo INT IDENTITY PRIMARY KEY,id_sala INT NOT NULL,fecha DATE NOT NULL,hora_inicio TIME NOT NULL,hora_fin TIME NOT NULL,motivo NVARCHAR(255) NOT NULL,FOREIGN KEY(id_sala) REFERENCES Salas(id_sala));
GO
IF OBJECT_ID('ReservasSalas','U') IS NULL
CREATE TABLE ReservasSalas(id_reserva INT IDENTITY PRIMARY KEY,id_usuario INT NOT NULL,id_sala INT NOT NULL,fecha DATE NOT NULL,hora_inicio TIME NOT NULL,hora_fin TIME NOT NULL,cantidad_personas INT NOT NULL,estado NVARCHAR(20) DEFAULT 'Activa',FOREIGN KEY(id_usuario) REFERENCES Usuarios(id_usuario),FOREIGN KEY(id_sala) REFERENCES Salas(id_sala));
GO
IF OBJECT_ID(N'AcompañantesReserva','U') IS NULL
CREATE TABLE AcompañantesReserva(id_asistente INT IDENTITY PRIMARY KEY,id_reserva INT NOT NULL,nombre_completo NVARCHAR(150) NOT NULL,carnet NVARCHAR(50) NOT NULL,cohorte NVARCHAR(50) NOT NULL,FOREIGN KEY(id_reserva) REFERENCES ReservasSalas(id_reserva));
GO
IF OBJECT_ID('CiclosAcademicos','U') IS NULL
CREATE TABLE CiclosAcademicos(id_ciclo INT IDENTITY PRIMARY KEY,nombre NVARCHAR(50) NOT NULL,fecha_inicio DATE NOT NULL,fecha_fin DATE NOT NULL,activo BIT DEFAULT 0);
GO
IF NOT EXISTS(SELECT 1 FROM CiclosAcademicos)
 INSERT INTO CiclosAcademicos(nombre,fecha_inicio,fecha_fin,activo) VALUES ('Ciclo 2026','2026-01-01','2026-12-31',1);
GO
IF OBJECT_ID('CategoriasHerramienta','U') IS NULL
CREATE TABLE CategoriasHerramienta(id_categoria INT IDENTITY PRIMARY KEY,nombre NVARCHAR(100) NOT NULL);
GO
IF NOT EXISTS(SELECT 1 FROM CategoriasHerramienta)
 INSERT INTO CategoriasHerramienta(nombre) VALUES ('Equipo de Protección Personal'),('Herramientas Eléctricas'),('Herramientas Manuales'),('Herramientas de Medición'),('Accesorios y Consumibles');
GO
IF OBJECT_ID('Herramientas','U') IS NULL
CREATE TABLE Herramientas(id_herramienta INT IDENTITY PRIMARY KEY,nombre NVARCHAR(100) NOT NULL,id_categoria INT NOT NULL,codigo NVARCHAR(50) NOT NULL UNIQUE,cantidad_total INT DEFAULT 1,cantidad_disponible INT DEFAULT 1,activa BIT DEFAULT 1,FOREIGN KEY(id_categoria) REFERENCES CategoriasHerramienta(id_categoria));
GO
IF COL_LENGTH('Herramientas','activa') IS NULL ALTER TABLE Herramientas ADD activa BIT DEFAULT 1;
GO
IF NOT EXISTS(SELECT 1 FROM Herramientas)
 INSERT INTO Herramientas(nombre,id_categoria,codigo,cantidad_total,cantidad_disponible) VALUES
 ('Lentes de protección',1,'EPP001',10,10),('Gabacha / Mandil',1,'EPP002',8,8),('Guantes de trabajo',1,'EPP003',6,6),
 ('Careta facial',1,'EPP004',3,3),('Dremel',2,'ELEC001',3,3),('Taladro',2,'ELEC002',4,4),
 ('Lijadora eléctrica',2,'ELEC003',2,2),('Sierra caladora',2,'ELEC004',2,2),('Serrucho',3,'MAN001',3,3),
 ('Destornillador plano',3,'MAN002',5,5),('Destornillador de cruz',3,'MAN003',5,5),('Martillo',3,'MAN004',4,4),
 ('Alicates',3,'MAN005',4,4),('Llave inglesa',3,'MAN006',3,3),('Pie de rey',4,'MED001',5,5),
 ('Cinta métrica',4,'MED002',6,6),('Escuadra',4,'MED003',4,4),('Brocas (set)',5,'ACC001',4,4),
 ('Hojas de serrucho',5,'ACC002',10,10),('Discos de corte',5,'ACC003',8,8);
GO
IF OBJECT_ID('EPPHerramienta','U') IS NULL
CREATE TABLE EPPHerramienta(id_epp INT IDENTITY PRIMARY KEY,id_herramienta INT NOT NULL,equipo NVARCHAR(100) NOT NULL,FOREIGN KEY(id_herramienta) REFERENCES Herramientas(id_herramienta));
GO
IF NOT EXISTS(SELECT 1 FROM EPPHerramienta)
BEGIN
 INSERT INTO EPPHerramienta(id_herramienta,equipo)
 SELECT h.id_herramienta,'Lentes de protección' FROM Herramientas h WHERE h.codigo IN ('ELEC001','ELEC002','ELEC003','ELEC004');
 INSERT INTO EPPHerramienta(id_herramienta,equipo)
 SELECT h.id_herramienta,'Guantes de trabajo' FROM Herramientas h WHERE h.codigo IN ('ELEC002','ELEC003','ELEC004','MAN001');
END
GO
IF OBJECT_ID('PrestamosHerramienta','U') IS NULL
CREATE TABLE PrestamosHerramienta(id_prestamo INT IDENTITY PRIMARY KEY,id_usuario INT NOT NULL,fecha_prestamo DATETIME DEFAULT GETDATE(),fecha_devolucion DATETIME NULL,estado NVARCHAR(20) DEFAULT 'Prestado',FOREIGN KEY(id_usuario) REFERENCES Usuarios(id_usuario));
GO
IF OBJECT_ID('DetallePrestamo','U') IS NULL
CREATE TABLE DetallePrestamo(id_detalle INT IDENTITY PRIMARY KEY,id_prestamo INT NOT NULL,id_herramienta INT NOT NULL,danada BIT NULL,nota_dano NVARCHAR(255) NULL,FOREIGN KEY(id_prestamo) REFERENCES PrestamosHerramienta(id_prestamo),FOREIGN KEY(id_herramienta) REFERENCES Herramientas(id_herramienta));
GO
IF COL_LENGTH('DetallePrestamo','danada') IS NULL ALTER TABLE DetallePrestamo ADD danada BIT NULL;
IF COL_LENGTH('DetallePrestamo','nota_dano') IS NULL ALTER TABLE DetallePrestamo ADD nota_dano NVARCHAR(255) NULL;
GO
IF OBJECT_ID('Impresoras3D','U') IS NULL
CREATE TABLE Impresoras3D(id_impresora INT IDENTITY PRIMARY KEY,nombre NVARCHAR(100) NOT NULL,codigo NVARCHAR(50) NOT NULL UNIQUE,disponible BIT DEFAULT 1);
GO
IF NOT EXISTS(SELECT 1 FROM Impresoras3D)
 INSERT INTO Impresoras3D(nombre,codigo) VALUES ('Impresora 3D #1','IMP001'),('Impresora 3D #2','IMP002'),('Impresora 3D #3','IMP003'),('Impresora 3D #4','IMP004'),('Impresora 3D #5','IMP005'),('Impresora 3D #6','IMP006'),('Impresora 3D #7','IMP007');
GO
IF OBJECT_ID('ReservasImpresora3D','U') IS NULL
CREATE TABLE ReservasImpresora3D(id_reserva INT IDENTITY PRIMARY KEY,id_usuario INT NOT NULL,id_impresora INT NOT NULL,tiempo_minutos INT NOT NULL,hora_fin DATETIME NULL,tipo_trabajo NVARCHAR(20) NOT NULL,filamento NVARCHAR(100) NOT NULL,filamento_otro NVARCHAR(100) NULL,gramos INT NOT NULL,fecha DATETIME DEFAULT GETDATE(),estado NVARCHAR(20) DEFAULT 'Activa',FOREIGN KEY(id_usuario) REFERENCES Usuarios(id_usuario),FOREIGN KEY(id_impresora) REFERENCES Impresoras3D(id_impresora));
GO
IF OBJECT_ID('MaquinasCNC','U') IS NULL
CREATE TABLE MaquinasCNC(id_cnc INT IDENTITY PRIMARY KEY,nombre NVARCHAR(100) NOT NULL,codigo NVARCHAR(50) NOT NULL UNIQUE,disponible BIT DEFAULT 1);
GO
IF NOT EXISTS(SELECT 1 FROM MaquinasCNC)
 INSERT INTO MaquinasCNC(nombre,codigo) VALUES ('CNC Router #1','CNC001'),('CNC Router #2','CNC002'),('CNC Router #3','CNC003'),('CNC Router #4','CNC004'),('CNC Router #5','CNC005');
GO
IF OBJECT_ID('ReservasCNC','U') IS NULL
CREATE TABLE ReservasCNC(id_reserva INT IDENTITY PRIMARY KEY,id_usuario INT NOT NULL,id_cnc INT NOT NULL,tiempo_minutos INT NOT NULL,hora_fin DATETIME NULL,tipo_trabajo NVARCHAR(20) NOT NULL,material NVARCHAR(100) NOT NULL,fecha DATETIME DEFAULT GETDATE(),estado NVARCHAR(20) DEFAULT 'Activa',FOREIGN KEY(id_usuario) REFERENCES Usuarios(id_usuario),FOREIGN KEY(id_cnc) REFERENCES MaquinasCNC(id_cnc));
GO
IF OBJECT_ID('Computadoras','U') IS NULL
CREATE TABLE Computadoras(id_computadora INT IDENTITY PRIMARY KEY,codigo NVARCHAR(50) NOT NULL UNIQUE,nombre NVARCHAR(100) NOT NULL,tiene_cargador BIT DEFAULT 1,tiene_mouse BIT DEFAULT 0,disponible BIT DEFAULT 1);
GO
IF NOT EXISTS(SELECT 1 FROM Computadoras)
 INSERT INTO Computadoras(codigo,nombre,tiene_cargador,tiene_mouse) VALUES ('COMP001','Computadora #1',1,1),('COMP002','Computadora #2',1,0),('COMP003','Computadora #3',1,1),('COMP004','Computadora #4',1,0),('COMP005','Computadora #5',1,1),('COMP006','Computadora #6',1,0);
GO
IF OBJECT_ID('ReservasComputadora','U') IS NULL
CREATE TABLE ReservasComputadora(id_reserva INT IDENTITY PRIMARY KEY,id_usuario INT NOT NULL,id_computadora INT NOT NULL,razon NVARCHAR(255) NOT NULL,razon_otro NVARCHAR(255) NULL,hora_inicio DATETIME DEFAULT GETDATE(),hora_fin DATETIME NULL,estado NVARCHAR(20) DEFAULT 'Pendiente',en_buen_estado BIT NULL,cargador_devuelto BIT NULL,mouse_devuelto BIT NULL,FOREIGN KEY(id_usuario) REFERENCES Usuarios(id_usuario),FOREIGN KEY(id_computadora) REFERENCES Computadoras(id_computadora));
GO
IF OBJECT_ID('LimiteFilamento','U') IS NULL
CREATE TABLE LimiteFilamento(id_limite INT IDENTITY PRIMARY KEY,tipo NVARCHAR(20) NOT NULL,id_usuario INT NULL,cohorte NVARCHAR(50) NULL,limite_gramos INT NOT NULL,FOREIGN KEY(id_usuario) REFERENCES Usuarios(id_usuario));
GO
IF OBJECT_ID('BloqueoKite','U') IS NULL
CREATE TABLE BloqueoKite(id_bloqueo INT IDENTITY PRIMARY KEY,tipo NVARCHAR(20) NOT NULL,id_usuario INT NULL,cohorte NVARCHAR(50) NULL,mensaje NVARCHAR(500) NOT NULL,activo BIT DEFAULT 1,FOREIGN KEY(id_usuario) REFERENCES Usuarios(id_usuario));
GO
