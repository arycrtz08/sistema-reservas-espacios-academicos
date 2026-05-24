import getpass
import os
import pyodbc
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()
driver = os.getenv('DB_DRIVER', 'ODBC Driver 17 for SQL Server')
server = os.getenv('DB_SERVER')
db = os.getenv('DB_NAME', 'InformationUSR')
if not server:
    raise SystemExit('Falta DB_SERVER en .env')
usuario = input('Usuario admin: ').strip()
tipo = input('Tipo [kite/compu/salas/gral]: ').strip().lower()
if tipo not in {'kite','compu','salas','gral'}:
    raise SystemExit('Tipo inválido')
password = getpass.getpass('Contraseña: ')
if len(password) < 10:
    raise SystemExit('Usa una contraseña de al menos 10 caracteres.')
conn = pyodbc.connect(f'DRIVER={{{driver}}};SERVER={server};DATABASE={db};Trusted_Connection=yes;TrustServerCertificate=yes;')
cur = conn.cursor()
cur.execute('SELECT id_admin FROM Administradores WHERE usuario=?', usuario)
if cur.fetchone():
    cur.execute('UPDATE Administradores SET contrasena=?, tipo=? WHERE usuario=?', generate_password_hash(password), tipo, usuario)
else:
    cur.execute('INSERT INTO Administradores(usuario,contrasena,tipo) VALUES (?,?,?)', usuario, generate_password_hash(password), tipo)
conn.commit(); cur.close(); conn.close()
print('Administrador guardado con contraseña cifrada.')
