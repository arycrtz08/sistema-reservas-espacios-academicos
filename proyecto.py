from flask import Flask, render_template, request, redirect, url_for, session
import pyodbc
import os #os lee variables del sistema
from dotenv import load_dotenv #carga datos secretos.

load_dotenv() #carga variables ocultas (servidor, usuario, contraseña, etc) desde el archivo .env

app = Flask(__name__)

#agrego a continuación porque necesita "session" para cifrar los logins
app.secret_key = os.getenv('SECRET_KEY', "Passwort")

 #conexión a la base de datos, cambiar los datos en el archivo .env (esto cambia por maquina)   
def get_db_connection():
    # Usamos triples llaves para que el resultado final tenga llaves reales {}
    driver = os.getenv('DB_DRIVER')
    server = os.getenv('DB_SERVER')
    database = os.getenv('DB_NAME')
    user = os.getenv('DB_USER')
    password = os.getenv('DB_PASSWORD')

    conn_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={user};"
        f"PWD={password};"
    )
    
    # Esto imprimirá en tu consola de VS Code exactamente qué se está enviando.
    # Verifica que no salgan llaves dobles o espacios raros.
    print(f"Intentando conectar con: {conn_str}") 
    
    return pyodbc.connect(conn_str)

#página de home
@app.route('/')
def home():
    # Si "usuario" NO está en la sesión, lo mandamos al login
    if 'usuario' not in session:
        return redirect(url_for('login'))
    
    return render_template('home.html')

#página de login
@app.route("/login", methods=["POST", "GET"])
def login():
    if request.method == "POST":
        user = request.form["usuario"]
        carnet = request.form["carnet_us"]
        cohorte = request.form["cohorte"] # en variable local

        # Inserción en la Base de Datos:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            query = "INSERT INTO Usuarios (usuario, carnet_us, cohorte_sel) VALUES (?, ?, ?)"
            cursor.execute(query, (user, carnet, cohorte))
            conn.commit()
            cursor.close()
            conn.close()
            print("Datos guardados exitosamente")

            #crear la sesión 
            session['usuario'] = user
            return redirect(url_for('home'))
            
        except Exception as e:
            print(f"Error al conectar o insertar: {e}")
    else:
        return render_template("login.html") #muestra el formulario de login

#página de reserva de salas
@app.route("/reserva_salas", #methods =[#aun no se que poner])
def salas():
    

if __name__ == '__main__':
    app.run(debug=True)