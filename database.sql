CREATE DATABASE InformationUSR;
GO
USE InformationUSR; 
GO
CREATE TABLE Usuarios (
    id_usuario INT PRIMARY KEY IDENTITY(1,1),
    usuario NVARCHAR(100) NOT NULL, 
    carnet_us NVARCHAR(50) NOT NULL UNIQUE,
    cohorte_sel NVARCHAR(50) NOT NULL,
    fecha_registro DATETIME DEFAULT GETDATE()
);

CREATE TABLE Salas (
    id_sala INT PRIMARY KEY IDENTITY(1,1),
    nombre NVARCHAR(100) NOT NULL,
    capacidad_min INT DEFAULT 2,
    capacidad_max INT DEFAULT 6,
    disponible BIT DEFAULT 1
);

CREATE TABLE CategoriasKite (
    id_categoria INT PRIMARY KEY IDENTITY(1,1),
    nombre NVARCHAR(50) NOT NULL
);

CREATE TABLE RecursosKite (
    id_recurso INT PRIMARY KEY IDENTITY(1,1),
    nombre NVARCHAR(100) NOT NULL,
    id_categoria INT NOT NULL,
    codigo NVARCHAR(50) NOT NULL UNIQUE,
    disponible BIT DEFAULT 1,
    FOREIGN KEY (id_categoria) REFERENCES CategoriasKite(id_categoria)
);

CREATE TABLE ReservasSalas (
    id_reserva INT PRIMARY KEY IDENTITY(1,1),
    id_usuario INT NOT NULL,
    id_sala INT NOT NULL,
    fecha DATE NOT NULL,
    hora_inicio TIME NOT NULL,
    hora_fin TIME NOT NULL,
    cantidad_personas INT NOT NULL,
    estado NVARCHAR(20) DEFAULT 'Activa',
    FOREIGN KEY (id_usuario) REFERENCES Usuarios(id_usuario),
    FOREIGN KEY (id_sala) REFERENCES Salas(id_sala)
);

-- 1. Agregamos una tabla para los acompañantes
CREATE TABLE AcompañantesReserva (
    id_asistente INT PRIMARY KEY IDENTITY(1,1),
    id_reserva INT NOT NULL, -- Relación con la tabla ReservasSalas
    nombre_completo NVARCHAR(150) NOT NULL,
    carnet NVARCHAR(50) NOT NULL,
    cohorte NVARCHAR(50) NOT NULL,
    FOREIGN KEY (id_reserva) REFERENCES ReservasSalas(id_reserva)
);



CREATE TABLE ReservasKite (
    id_reserva INT PRIMARY KEY IDENTITY(1,1),
    id_usuario INT NOT NULL,
    id_recurso INT NOT NULL,
    fecha DATE NOT NULL,
    hora_inicio TIME NOT NULL,
    hora_fin TIME NOT NULL,
    estado NVARCHAR(20) DEFAULT 'Activa',
    observacion NVARCHAR(255),
    FOREIGN KEY (id_usuario) REFERENCES Usuarios(id_usuario),
    FOREIGN KEY (id_recurso) REFERENCES RecursosKite(id_recurso)
);

INSERT INTO Salas (nombre)
VALUES ('Sala KEY001'), ('Sala KEY002'), ('Sala KEY003'), ('Sala KEY004'), ('Sala KEY005'), ('Sala KEY006'); 

INSERT INTO CategoriasKite (nombre)
VALUES ('Mesa'), ('Herramienta'), ('Maquinaria');

INSERT INTO RecursosKite (nombre, id_categoria, codigo)
VALUES --cambie lo que decia mesa, herramienta y maquinaria para que lo pudierea buscar
('Mesa 1', (SELECT id_categoria FROM CategoriasKite WHERE nombre = 'Mesa'), 'M001'),
('Mesa 2', (SELECT id_categoria FROM CategoriasKite WHERE nombre = 'Mesa'), 'M002'),
('Pie de rey', (SELECT id_categoria FROM CategoriasKite WHERE nombre = 'Herramienta'), 'H001'),
('Serrucho', (SELECT id_categoria FROM CategoriasKite WHERE nombre = 'Herramienta'), 'H002'),
('Cinta métrica', (SELECT id_categoria FROM CategoriasKite WHERE nombre = 'Herramienta'), 'H003'),
('Impresora 3D', (SELECT id_categoria FROM CategoriasKite WHERE nombre = 'Maquinaria'), 'MAQ001'),
('Cortadora láser', (SELECT id_categoria FROM CategoriasKite WHERE nombre = 'Maquinaria'), 'MAQ002');

-- ============================================================
-- NUEVAS TABLAS: Kite (Impresoras/CNC/Herramientas) y Computadoras
-- ============================================================

-- Rol de usuario: 'estudiante' (default) o 'guardian'
ALTER TABLE Usuarios ADD rol NVARCHAR(20) DEFAULT 'estudiante';

-- Ciclos académicos (para el límite de 750g de filamento por ciclo por usuario)
CREATE TABLE CiclosAcademicos (
    id_ciclo     INT PRIMARY KEY IDENTITY(1,1),
    nombre       NVARCHAR(50) NOT NULL,
    fecha_inicio DATE NOT NULL,
    fecha_fin    DATE NOT NULL,
    activo       BIT DEFAULT 0
);
INSERT INTO CiclosAcademicos (nombre, fecha_inicio, fecha_fin, activo)
VALUES ('Ciclo 2026', '2026-01-01', '2026-12-31', 1);

-- Categorías de herramientas (estructura tipo ferretería)
CREATE TABLE CategoriasHerramienta (
    id_categoria INT PRIMARY KEY IDENTITY(1,1),
    nombre       NVARCHAR(100) NOT NULL
);
INSERT INTO CategoriasHerramienta (nombre) VALUES
('Equipo de Protección Personal'),
('Herramientas Eléctricas'),
('Herramientas Manuales'),
('Herramientas de Medición'),
('Accesorios y Consumibles');

-- Inventario de herramientas individuales
CREATE TABLE Herramientas (
    id_herramienta      INT PRIMARY KEY IDENTITY(1,1),
    nombre              NVARCHAR(100) NOT NULL,
    id_categoria        INT NOT NULL,
    codigo              NVARCHAR(50) NOT NULL UNIQUE,
    cantidad_total      INT DEFAULT 1,
    cantidad_disponible INT DEFAULT 1,
    FOREIGN KEY (id_categoria) REFERENCES CategoriasHerramienta(id_categoria)
);
INSERT INTO Herramientas (nombre, id_categoria, codigo, cantidad_total, cantidad_disponible) VALUES
-- Equipo de Protección Personal
('Lentes de protección',    1, 'EPP001', 10, 10),
('Gabacha / Mandil',        1, 'EPP002',  8,  8),
('Guantes de trabajo',      1, 'EPP003',  6,  6),
('Careta facial',           1, 'EPP004',  3,  3),
-- Herramientas Eléctricas
('Dremel',                  2, 'ELEC001', 3, 3),
('Taladro',                 2, 'ELEC002', 4, 4),
('Lijadora eléctrica',      2, 'ELEC003', 2, 2),
('Sierra caladora',         2, 'ELEC004', 2, 2),
-- Herramientas Manuales
('Serrucho',                3, 'MAN001',  3, 3),
('Destornillador plano',    3, 'MAN002',  5, 5),
('Destornillador de cruz',  3, 'MAN003',  5, 5),
('Martillo',                3, 'MAN004',  4, 4),
('Alicates',                3, 'MAN005',  4, 4),
('Llave inglesa',           3, 'MAN006',  3, 3),
-- Herramientas de Medición
('Pie de rey',              4, 'MED001',  5, 5),
('Cinta métrica',           4, 'MED002',  6, 6),
('Escuadra',                4, 'MED003',  4, 4),
-- Accesorios y Consumibles
('Brocas (set)',            5, 'ACC001',  4, 4),
('Hojas de serrucho',       5, 'ACC002', 10,10),
('Discos de corte',         5, 'ACC003',  8, 8);

-- Impresoras 3D (7 unidades)
CREATE TABLE Impresoras3D (
    id_impresora INT PRIMARY KEY IDENTITY(1,1),
    nombre       NVARCHAR(100) NOT NULL,
    codigo       NVARCHAR(50) NOT NULL UNIQUE,
    disponible   BIT DEFAULT 1
);
INSERT INTO Impresoras3D (nombre, codigo) VALUES
('Impresora 3D #1', 'IMP001'),
('Impresora 3D #2', 'IMP002'),
('Impresora 3D #3', 'IMP003'),
('Impresora 3D #4', 'IMP004'),
('Impresora 3D #5', 'IMP005'),
('Impresora 3D #6', 'IMP006'),
('Impresora 3D #7', 'IMP007');

-- Máquinas CNC (5 unidades)
CREATE TABLE MaquinasCNC (
    id_cnc     INT PRIMARY KEY IDENTITY(1,1),
    nombre     NVARCHAR(100) NOT NULL,
    codigo     NVARCHAR(50) NOT NULL UNIQUE,
    disponible BIT DEFAULT 1
);
INSERT INTO MaquinasCNC (nombre, codigo) VALUES
('CNC Router #1', 'CNC001'),
('CNC Router #2', 'CNC002'),
('CNC Router #3', 'CNC003'),
('CNC Router #4', 'CNC004'),
('CNC Router #5', 'CNC005');

-- Reservas de Impresoras 3D
CREATE TABLE ReservasImpresora3D (
    id_reserva   INT PRIMARY KEY IDENTITY(1,1),
    id_usuario   INT NOT NULL,
    id_impresora INT NOT NULL,
    tiempo_uso   NVARCHAR(50) NOT NULL,
    tipo_trabajo NVARCHAR(20) NOT NULL,   -- 'Individual' o 'Grupal'
    filamento    NVARCHAR(100) NOT NULL,
    gramos       INT NOT NULL,
    fecha        DATETIME DEFAULT GETDATE(),
    estado       NVARCHAR(20) DEFAULT 'Activa',
    FOREIGN KEY (id_usuario)   REFERENCES Usuarios(id_usuario),
    FOREIGN KEY (id_impresora) REFERENCES Impresoras3D(id_impresora)
);

-- Reservas de CNC
CREATE TABLE ReservasCNC (
    id_reserva   INT PRIMARY KEY IDENTITY(1,1),
    id_usuario   INT NOT NULL,
    id_cnc       INT NOT NULL,
    tiempo_uso   NVARCHAR(50) NOT NULL,
    tipo_trabajo NVARCHAR(20) NOT NULL,   -- 'Individual' o 'Grupal'
    material     NVARCHAR(100) NOT NULL,
    fecha        DATETIME DEFAULT GETDATE(),
    estado       NVARCHAR(20) DEFAULT 'Activa',
    FOREIGN KEY (id_usuario) REFERENCES Usuarios(id_usuario),
    FOREIGN KEY (id_cnc)     REFERENCES MaquinasCNC(id_cnc)
);

-- Préstamos de herramientas
CREATE TABLE PrestamosHerramienta (
    id_prestamo       INT PRIMARY KEY IDENTITY(1,1),
    id_usuario        INT NOT NULL,
    fecha_prestamo    DATETIME DEFAULT GETDATE(),
    fecha_devolucion  DATETIME NULL,
    estado            NVARCHAR(20) DEFAULT 'Prestado',  -- 'Prestado' o 'Devuelto'
    FOREIGN KEY (id_usuario) REFERENCES Usuarios(id_usuario)
);

-- Detalle de préstamos: qué herramientas incluye cada préstamo (muchos a muchos)
CREATE TABLE DetallePrestamo (
    id_detalle     INT PRIMARY KEY IDENTITY(1,1),
    id_prestamo    INT NOT NULL,
    id_herramienta INT NOT NULL,
    FOREIGN KEY (id_prestamo)    REFERENCES PrestamosHerramienta(id_prestamo),
    FOREIGN KEY (id_herramienta) REFERENCES Herramientas(id_herramienta)
);

-- Computadoras (10 unidades)
CREATE TABLE Computadoras (
    id_computadora INT PRIMARY KEY IDENTITY(1,1),
    codigo         NVARCHAR(50) NOT NULL UNIQUE,
    nombre         NVARCHAR(100) NOT NULL,
    tiene_cargador BIT DEFAULT 1,
    tiene_mouse    BIT DEFAULT 0,
    disponible     BIT DEFAULT 1
);
INSERT INTO Computadoras (codigo, nombre, tiene_cargador, tiene_mouse) VALUES
('COMP001', 'Computadora #1',  1, 1),
('COMP002', 'Computadora #2',  1, 0),
('COMP003', 'Computadora #3',  1, 1),
('COMP004', 'Computadora #4',  1, 0),
('COMP005', 'Computadora #5',  1, 1),
('COMP006', 'Computadora #6',  1, 0),
('COMP007', 'Computadora #7',  1, 1),
('COMP008', 'Computadora #8',  1, 0),
('COMP009', 'Computadora #9',  1, 1),
('COMP010', 'Computadora #10', 1, 1);

-- Reservas de computadoras
-- estado: 'Pendiente' -> 'Confirmada' -> 'Devuelta'
CREATE TABLE ReservasComputadora (
    id_reserva       INT PRIMARY KEY IDENTITY(1,1),
    id_usuario       INT NOT NULL,
    id_computadora   INT NOT NULL,
    razon            NVARCHAR(255) NOT NULL,
    hora_inicio      DATETIME DEFAULT GETDATE(),
    hora_fin         DATETIME NULL,
    estado           NVARCHAR(20) DEFAULT 'Pendiente',
    en_buen_estado   BIT NULL,
    cargador_devuelto BIT NULL,
    mouse_devuelto   BIT NULL,
    FOREIGN KEY (id_usuario)     REFERENCES Usuarios(id_usuario),
    FOREIGN KEY (id_computadora) REFERENCES Computadoras(id_computadora)
);