-- ============================================================
-- CampusHub v2 – Script completo idempotente
-- Copiar y pegar en un New Query sobre la BD InformationUSR.
-- Usa IF NOT EXISTS en todas las tablas y IF COL_LENGTH en
-- los ALTER, por lo que puede ejecutarse varias veces sin error.
-- ============================================================

-- Crear BD si no existe
IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'InformationUSR')
BEGIN
    CREATE DATABASE InformationUSR;
END
GO
USE InformationUSR;
GO

-- ============================================================
-- TABLA: Usuarios
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE name = 'Usuarios' AND type = 'U')
BEGIN
    CREATE TABLE Usuarios (
        id_usuario     INT PRIMARY KEY IDENTITY(1,1),
        usuario        NVARCHAR(100) NOT NULL,
        carnet_us      NVARCHAR(50)  NOT NULL UNIQUE,
        cohorte_sel    NVARCHAR(50)  NOT NULL,
        rol            NVARCHAR(20)  DEFAULT 'estudiante',
        fecha_registro DATETIME      DEFAULT GETDATE()
    );
END
ELSE
BEGIN
    -- Agregar columna rol si no existe
    IF COL_LENGTH('Usuarios', 'rol') IS NULL
        ALTER TABLE Usuarios ADD rol NVARCHAR(20) DEFAULT 'estudiante';
END
GO

-- ============================================================
-- TABLA: Administradores  (login separado del sistema)
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE name = 'Administradores' AND type = 'U')
BEGIN
    CREATE TABLE Administradores (
        id_admin   INT PRIMARY KEY IDENTITY(1,1),
        usuario    NVARCHAR(50)  NOT NULL UNIQUE,  -- Admin_Kite, Admin_compu, etc.
        contrasena NVARCHAR(255) NOT NULL,          -- hash werkzeug (pbkdf2)
        tipo       NVARCHAR(20)  NOT NULL            -- 'kite', 'compu', 'salas', 'gral'
    );
END
GO

-- Insertar admins (contraseñas en texto plano aquí; el INSERT solo corre si no existen)
-- Las contraseñas reales son hasheadas por Python la primera vez que se lean.
-- Para simplificar el setup inicial, guardamos la contraseña en texto y Python la
-- reconocerá y actualizará al hash en el primer login.
IF NOT EXISTS (SELECT 1 FROM Administradores WHERE usuario = 'Admin_Kite')
    INSERT INTO Administradores (usuario, contrasena, tipo) VALUES ('Admin_Kite',  'Kite@2026!',  'kite');
IF NOT EXISTS (SELECT 1 FROM Administradores WHERE usuario = 'Admin_compu')
    INSERT INTO Administradores (usuario, contrasena, tipo) VALUES ('Admin_compu', 'Compu@2026!', 'compu');
IF NOT EXISTS (SELECT 1 FROM Administradores WHERE usuario = 'Admin_salas')
    INSERT INTO Administradores (usuario, contrasena, tipo) VALUES ('Admin_salas', 'Salas@2026!', 'salas');
IF NOT EXISTS (SELECT 1 FROM Administradores WHERE usuario = 'Admin_Gral')
    INSERT INTO Administradores (usuario, contrasena, tipo) VALUES ('Admin_Gral',  'Gral@2026!',  'gral');
GO

-- ============================================================
-- TABLA: LogsIngreso
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE name = 'LogsIngreso' AND type = 'U')
BEGIN
    CREATE TABLE LogsIngreso (
        id_log             INT PRIMARY KEY IDENTITY(1,1),
        carnet_us          NVARCHAR(50) NOT NULL,
        fecha_hora_ingreso DATETIME     DEFAULT GETDATE()
    );
END
GO

-- ============================================================
-- TABLA: Salas
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE name = 'Salas' AND type = 'U')
BEGIN
    CREATE TABLE Salas (
        id_sala       INT PRIMARY KEY IDENTITY(1,1),
        nombre        NVARCHAR(100) NOT NULL,
        capacidad_min INT DEFAULT 2,
        capacidad_max INT DEFAULT 6,
        disponible    BIT DEFAULT 1
    );
END
GO

-- Datos iniciales de salas
IF NOT EXISTS (SELECT 1 FROM Salas)
    INSERT INTO Salas (nombre) VALUES
    ('Sala M201'), ('Sala M202'), ('Sala M203'),
    ('Sala M204'), ('Sala M205'), ('Sala M206');
GO

-- ============================================================
-- TABLA: BloqueoSalas  (Admin_salas puede bloquear horarios)
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE name = 'BloqueoSalas' AND type = 'U')
BEGIN
    CREATE TABLE BloqueoSalas (
        id_bloqueo  INT PRIMARY KEY IDENTITY(1,1),
        id_sala     INT           NOT NULL,
        fecha       DATE          NOT NULL,
        hora_inicio TIME          NOT NULL,
        hora_fin    TIME          NOT NULL,
        motivo      NVARCHAR(255) NULL,
        FOREIGN KEY (id_sala) REFERENCES Salas(id_sala)
    );
END
GO

-- ============================================================
-- TABLA: ReservasSalas
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE name = 'ReservasSalas' AND type = 'U')
BEGIN
    CREATE TABLE ReservasSalas (
        id_reserva        INT PRIMARY KEY IDENTITY(1,1),
        id_usuario        INT           NOT NULL,
        id_sala           INT           NOT NULL,
        fecha             DATE          NOT NULL,
        hora_inicio       TIME          NOT NULL,
        hora_fin          TIME          NOT NULL,
        cantidad_personas INT           NOT NULL,
        estado            NVARCHAR(20)  DEFAULT 'Activa',
        FOREIGN KEY (id_usuario) REFERENCES Usuarios(id_usuario),
        FOREIGN KEY (id_sala)    REFERENCES Salas(id_sala)
    );
END
GO

-- ============================================================
-- TABLA: AcompañantesReserva
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE name = N'Acompañantes Reserva'
               AND type = 'U')
BEGIN
    -- nombre con ñ puede causar problemas; usar nombre exacto:
    IF NOT EXISTS (SELECT * FROM sys.objects WHERE name LIKE 'Acompa%' AND type = 'U')
    BEGIN
        CREATE TABLE AcompañantesReserva (
            id_asistente    INT PRIMARY KEY IDENTITY(1,1),
            id_reserva      INT           NOT NULL,
            nombre_completo NVARCHAR(150) NOT NULL,
            carnet          NVARCHAR(50)  NOT NULL,
            cohorte         NVARCHAR(50)  NOT NULL,
            FOREIGN KEY (id_reserva) REFERENCES ReservasSalas(id_reserva)
        );
    END
END
GO

-- ============================================================
-- TABLA: CiclosAcademicos
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE name = 'CiclosAcademicos' AND type = 'U')
BEGIN
    CREATE TABLE CiclosAcademicos (
        id_ciclo     INT PRIMARY KEY IDENTITY(1,1),
        nombre       NVARCHAR(50) NOT NULL,
        fecha_inicio DATE         NOT NULL,
        fecha_fin    DATE         NOT NULL,
        activo       BIT          DEFAULT 0
    );
END
GO

IF NOT EXISTS (SELECT 1 FROM CiclosAcademicos)
    INSERT INTO CiclosAcademicos (nombre, fecha_inicio, fecha_fin, activo)
    VALUES ('Ciclo 2026', '2026-01-01', '2026-12-31', 1);
GO

-- ============================================================
-- TABLA: CategoriasHerramienta
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE name = 'CategoriasHerramienta' AND type = 'U')
BEGIN
    CREATE TABLE CategoriasHerramienta (
        id_categoria INT PRIMARY KEY IDENTITY(1,1),
        nombre       NVARCHAR(100) NOT NULL
    );
END
GO

IF NOT EXISTS (SELECT 1 FROM CategoriasHerramienta)
    INSERT INTO CategoriasHerramienta (nombre) VALUES
    ('Equipo de Protección Personal'),
    ('Herramientas Eléctricas'),
    ('Herramientas Manuales'),
    ('Herramientas de Medición'),
    ('Accesorios y Consumibles');
GO

-- ============================================================
-- TABLA: Herramientas
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE name = 'Herramientas' AND type = 'U')
BEGIN
    CREATE TABLE Herramientas (
        id_herramienta      INT PRIMARY KEY IDENTITY(1,1),
        nombre              NVARCHAR(100) NOT NULL,
        id_categoria        INT           NOT NULL,
        codigo              NVARCHAR(50)  NOT NULL UNIQUE,
        cantidad_total      INT           DEFAULT 1,
        cantidad_disponible INT           DEFAULT 1,
        activa              BIT           DEFAULT 1,  -- Admin_Kite puede desactivar
        FOREIGN KEY (id_categoria) REFERENCES CategoriasHerramienta(id_categoria)
    );
END
ELSE
BEGIN
    IF COL_LENGTH('Herramientas', 'activa') IS NULL
        ALTER TABLE Herramientas ADD activa BIT DEFAULT 1;
END
GO

IF NOT EXISTS (SELECT 1 FROM Herramientas)
    INSERT INTO Herramientas (nombre, id_categoria, codigo, cantidad_total, cantidad_disponible) VALUES
    ('Lentes de protección',   1, 'EPP001', 10, 10),
    ('Gabacha / Mandil',       1, 'EPP002',  8,  8),
    ('Guantes de trabajo',     1, 'EPP003',  6,  6),
    ('Careta facial',          1, 'EPP004',  3,  3),
    ('Dremel',                 2, 'ELEC001', 3,  3),
    ('Taladro',                2, 'ELEC002', 4,  4),
    ('Lijadora eléctrica',     2, 'ELEC003', 2,  2),
    ('Sierra caladora',        2, 'ELEC004', 2,  2),
    ('Serrucho',               3, 'MAN001',  3,  3),
    ('Destornillador plano',   3, 'MAN002',  5,  5),
    ('Destornillador de cruz', 3, 'MAN003',  5,  5),
    ('Martillo',               3, 'MAN004',  4,  4),
    ('Alicates',               3, 'MAN005',  4,  4),
    ('Llave inglesa',          3, 'MAN006',  3,  3),
    ('Pie de rey',             4, 'MED001',  5,  5),
    ('Cinta métrica',          4, 'MED002',  6,  6),
    ('Escuadra',               4, 'MED003',  4,  4),
    ('Brocas (set)',           5, 'ACC001',  4,  4),
    ('Hojas de serrucho',      5, 'ACC002', 10, 10),
    ('Discos de corte',        5, 'ACC003',  8,  8);
GO

-- ============================================================
-- TABLA: Impresoras3D
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE name = 'Impresoras3D' AND type = 'U')
BEGIN
    CREATE TABLE Impresoras3D (
        id_impresora INT PRIMARY KEY IDENTITY(1,1),
        nombre       NVARCHAR(100) NOT NULL,
        codigo       NVARCHAR(50)  NOT NULL UNIQUE,
        disponible   BIT           DEFAULT 1
    );
END
GO

IF NOT EXISTS (SELECT 1 FROM Impresoras3D)
    INSERT INTO Impresoras3D (nombre, codigo) VALUES
    ('Impresora 3D #1','IMP001'), ('Impresora 3D #2','IMP002'),
    ('Impresora 3D #3','IMP003'), ('Impresora 3D #4','IMP004'),
    ('Impresora 3D #5','IMP005'), ('Impresora 3D #6','IMP006'),
    ('Impresora 3D #7','IMP007');
GO


-- ============================================================
-- TABLA: ReservasImpresora3D
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE name = 'ReservasImpresora3D' AND type = 'U')
BEGIN
    CREATE TABLE ReservasImpresora3D (
        id_reserva     INT PRIMARY KEY IDENTITY(1,1),
        id_usuario     INT           NOT NULL,
        id_impresora   INT           NOT NULL,
        tiempo_minutos INT           NOT NULL,          -- duración en minutos
        hora_fin       DATETIME      NULL,              -- calculada al confirmar
        tipo_trabajo   NVARCHAR(20)  NOT NULL,
        filamento      NVARCHAR(100) NOT NULL,          -- PLA, TPU, PETG, Otro
        filamento_otro NVARCHAR(100) NULL,              -- si filamento='Otro'
        gramos         INT           NOT NULL,
        fecha          DATETIME      DEFAULT GETDATE(),
        estado         NVARCHAR(20)  DEFAULT 'Activa',
        FOREIGN KEY (id_usuario)   REFERENCES Usuarios(id_usuario),
        FOREIGN KEY (id_impresora) REFERENCES Impresoras3D(id_impresora)
    );
END
ELSE
BEGIN
    IF COL_LENGTH('ReservasImpresora3D', 'tiempo_minutos') IS NULL
        ALTER TABLE ReservasImpresora3D ADD tiempo_minutos INT NULL;
    IF COL_LENGTH('ReservasImpresora3D', 'hora_fin') IS NULL
        ALTER TABLE ReservasImpresora3D ADD hora_fin DATETIME NULL;
    IF COL_LENGTH('ReservasImpresora3D', 'filamento_otro') IS NULL
        ALTER TABLE ReservasImpresora3D ADD filamento_otro NVARCHAR(100) NULL;
END
GO


-- ============================================================
-- TABLA: PrestamosHerramienta
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE name = 'PrestamosHerramienta' AND type = 'U')
BEGIN
    CREATE TABLE PrestamosHerramienta (
        id_prestamo      INT PRIMARY KEY IDENTITY(1,1),
        id_usuario       INT      NOT NULL,
        fecha_prestamo   DATETIME DEFAULT GETDATE(),
        fecha_devolucion DATETIME NULL,
        estado           NVARCHAR(20) DEFAULT 'Prestado',
        FOREIGN KEY (id_usuario) REFERENCES Usuarios(id_usuario)
    );
END
GO

-- ============================================================
-- TABLA: DetallePrestamo
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE name = 'DetallePrestamo' AND type = 'U')
BEGIN
    CREATE TABLE DetallePrestamo (
        id_detalle     INT PRIMARY KEY IDENTITY(1,1),
        id_prestamo    INT NOT NULL,
        id_herramienta INT NOT NULL,
        danada         BIT           NULL,
        nota_dano      NVARCHAR(255) NULL,
        FOREIGN KEY (id_prestamo)    REFERENCES PrestamosHerramienta(id_prestamo),
        FOREIGN KEY (id_herramienta) REFERENCES Herramientas(id_herramienta)
    );
END
ELSE
BEGIN
    IF COL_LENGTH('DetallePrestamo', 'danada') IS NULL
        ALTER TABLE DetallePrestamo ADD danada BIT NULL;
    IF COL_LENGTH('DetallePrestamo', 'nota_dano') IS NULL
        ALTER TABLE DetallePrestamo ADD nota_dano NVARCHAR(255) NULL;
END
GO

-- ============================================================
-- TABLA: Computadoras
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE name = 'Computadoras' AND type = 'U')
BEGIN
    CREATE TABLE Computadoras (
        id_computadora INT PRIMARY KEY IDENTITY(1,1),
        codigo         NVARCHAR(50)  NOT NULL UNIQUE,
        nombre         NVARCHAR(100) NOT NULL,
        tiene_cargador BIT           DEFAULT 1,
        tiene_mouse    BIT           DEFAULT 0,
        disponible     BIT           DEFAULT 1
    );
END
GO

IF NOT EXISTS (SELECT 1 FROM Computadoras)
    INSERT INTO Computadoras (codigo, nombre, tiene_cargador, tiene_mouse) VALUES
    ('COMP001','Computadora #1', 1,1), ('COMP002','Computadora #2', 1,0),
    ('COMP003','Computadora #3', 1,1), ('COMP004','Computadora #4', 1,0),
    ('COMP005','Computadora #5', 1,1), ('COMP006','Computadora #6', 1,0),
    ('COMP007','Computadora #7', 1,1), ('COMP008','Computadora #8', 1,0),
    ('COMP009','Computadora #9', 1,1), ('COMP010','Computadora #10',1,1);
GO

-- ============================================================
-- TABLA: ReservasComputadora
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE name = 'ReservasComputadora' AND type = 'U')
BEGIN
    CREATE TABLE ReservasComputadora (
        id_reserva        INT PRIMARY KEY IDENTITY(1,1),
        id_usuario        INT           NOT NULL,
        id_computadora    INT           NOT NULL,
        razon             NVARCHAR(255) NOT NULL,
        razon_otro        NVARCHAR(255) NULL,
        hora_inicio       DATETIME      DEFAULT GETDATE(),
        hora_fin          DATETIME      NULL,
        estado            NVARCHAR(20)  DEFAULT 'Pendiente',
        en_buen_estado    BIT           NULL,
        cargador_devuelto BIT           NULL,
        mouse_devuelto    BIT           NULL,
        FOREIGN KEY (id_usuario)     REFERENCES Usuarios(id_usuario),
        FOREIGN KEY (id_computadora) REFERENCES Computadoras(id_computadora)
    );
END
ELSE
BEGIN
    IF COL_LENGTH('ReservasComputadora', 'razon_otro') IS NULL
        ALTER TABLE ReservasComputadora ADD razon_otro NVARCHAR(255) NULL;
END
GO

-- ============================================================
-- TABLA: LimiteFilamento  (límites personalizados de PLA)
-- Admin_Kite puede sobreescribir el global (750g) por persona o cohorte.
-- Si existe un límite individual, tiene prioridad sobre el de cohorte.
-- Si existe límite de cohorte, reemplaza el global de 750g.
-- tipo: 'persona' o 'cohorte'
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE name = 'LimiteFilamento' AND type = 'U')
BEGIN
    CREATE TABLE LimiteFilamento (
        id_limite    INT PRIMARY KEY IDENTITY(1,1),
        tipo         NVARCHAR(20)  NOT NULL,  -- 'persona' | 'cohorte'
        id_usuario   INT           NULL,       -- si tipo='persona'
        cohorte      NVARCHAR(50)  NULL,       -- si tipo='cohorte'
        limite_gramos INT          NOT NULL,
        FOREIGN KEY (id_usuario) REFERENCES Usuarios(id_usuario)
    );
END
GO

-- ============================================================
-- TABLA: BloqueoKite  (Admin_Kite bloquea personas o cohortes)
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE name = 'BloqueoKite' AND type = 'U')
BEGIN
    CREATE TABLE BloqueoKite (
        id_bloqueo INT PRIMARY KEY IDENTITY(1,1),
        tipo       NVARCHAR(20)  NOT NULL,  -- 'persona' | 'cohorte'
        id_usuario INT           NULL,
        cohorte    NVARCHAR(50)  NULL,
        mensaje    NVARCHAR(500) NOT NULL,
        activo     BIT           DEFAULT 1,
        FOREIGN KEY (id_usuario) REFERENCES Usuarios(id_usuario)
    );
END
GO

-- ============================================================
-- Limpieza: eliminar usuario Guardian si existe
-- ============================================================
DELETE FROM Usuarios WHERE carnet_us = 'Key_150001' AND usuario = 'Guardian';
GO

-- ============================================================
-- Tablas legacy (CategoriasKite, RecursosKite, ReservasKite)
-- Se conservan si ya existen para no perder datos históricos,
-- pero ya no se usan en v2.
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE name = 'CategoriasKite' AND type = 'U')
BEGIN
    CREATE TABLE CategoriasKite (
        id_categoria INT PRIMARY KEY IDENTITY(1,1),
        nombre       NVARCHAR(50) NOT NULL
    );
    INSERT INTO CategoriasKite (nombre) VALUES ('Mesa'),('Herramienta'),('Maquinaria');
END
GO

IF NOT EXISTS (SELECT * FROM sys.objects WHERE name = 'RecursosKite' AND type = 'U')
BEGIN
    CREATE TABLE RecursosKite (
        id_recurso   INT PRIMARY KEY IDENTITY(1,1),
        nombre       NVARCHAR(100) NOT NULL,
        id_categoria INT           NOT NULL,
        codigo       NVARCHAR(50)  NOT NULL UNIQUE,
        disponible   BIT           DEFAULT 1,
        FOREIGN KEY (id_categoria) REFERENCES CategoriasKite(id_categoria)
    );
END
GO

IF NOT EXISTS (SELECT * FROM sys.objects WHERE name = 'ReservasKite' AND type = 'U')
BEGIN
    CREATE TABLE ReservasKite (
        id_reserva  INT PRIMARY KEY IDENTITY(1,1),
        id_usuario  INT          NOT NULL,
        id_recurso  INT          NOT NULL,
        fecha       DATE         NOT NULL,
        hora_inicio TIME         NOT NULL,
        hora_fin    TIME         NOT NULL,
        estado      NVARCHAR(20) DEFAULT 'Activa',
        observacion NVARCHAR(255),
        FOREIGN KEY (id_usuario) REFERENCES Usuarios(id_usuario),
        FOREIGN KEY (id_recurso) REFERENCES RecursosKite(id_recurso)
    );
END
GO

-- ============================================================
-- TABLA: EPPHerramienta
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE name = 'EPPHerramienta' AND type = 'U')
BEGIN
    CREATE TABLE EPPHerramienta (
        id_epp         INT PRIMARY KEY IDENTITY(1,1),
        id_herramienta INT           NOT NULL,
        equipo         NVARCHAR(100) NOT NULL,
        FOREIGN KEY (id_herramienta) REFERENCES Herramientas(id_herramienta)
    );
END
GO

IF NOT EXISTS (SELECT 1 FROM EPPHerramienta)
BEGIN
    -- Dremel
    INSERT INTO EPPHerramienta (id_herramienta, equipo) VALUES (5, 'Lentes de protección');
    INSERT INTO EPPHerramienta (id_herramienta, equipo) VALUES (5, 'Guantes de trabajo');
    -- Taladro
    INSERT INTO EPPHerramienta (id_herramienta, equipo) VALUES (6, 'Lentes de protección');
    INSERT INTO EPPHerramienta (id_herramienta, equipo) VALUES (6, 'Guantes de trabajo');
    -- Lijadora eléctrica
    INSERT INTO EPPHerramienta (id_herramienta, equipo) VALUES (7, 'Lentes de protección');
    INSERT INTO EPPHerramienta (id_herramienta, equipo) VALUES (7, 'Guantes de trabajo');
    INSERT INTO EPPHerramienta (id_herramienta, equipo) VALUES (7, 'Gabacha / Mandil');
    -- Sierra caladora
    INSERT INTO EPPHerramienta (id_herramienta, equipo) VALUES (8, 'Lentes de protección');
    INSERT INTO EPPHerramienta (id_herramienta, equipo) VALUES (8, 'Guantes de trabajo');
    INSERT INTO EPPHerramienta (id_herramienta, equipo) VALUES (8, 'Gabacha / Mandil');
    INSERT INTO EPPHerramienta (id_herramienta, equipo) VALUES (8, 'Careta facial');
    -- Serrucho
    INSERT INTO EPPHerramienta (id_herramienta, equipo) VALUES (9, 'Lentes de protección');
    INSERT INTO EPPHerramienta (id_herramienta, equipo) VALUES (9, 'Guantes de trabajo');
END
GO