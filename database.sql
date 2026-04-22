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