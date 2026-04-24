from flask import Flask, render_template, request, redirect, url_for, session
import pyodbc
import os #os lee variables del sistema
from dotenv import load_dotenv #carga datos secretos.
from datetime import datetime, timedelta #Me imagino que para la hora

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

#Página salas
@app.route('/reservar_sala', methods=['POST'])
def reservar_sala():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    # 1. Recolección de datos del formulario
    id_sala = request.form['id_sala']
    hora_inicio_str = request.form['hora_inicio'] # Formato HH:MM
    hora_fin_str = request.form['hora_fin']
    cantidad_personas = int(request.form['cantidad_personas']) 

    # Datos de acompañantes
    acomp_nombre = request.form['acomp_nombre']
    acomp_carnet = request.form['acomp_carnet']
    acomp_cohorte = request.form['acomp_cohorte']

    # 2. Conversión a objetos de tiempo para validar
    h_inicio = datetime.strptime(hora_inicio_str, '%H:%M').time()
    h_fin = datetime.strptime(hora_fin_str, '%H:%M').time() 
    
    # 3. VALIDACIONES
    # A. Horario permitido (6:00 AM a 6:00 PM)
    limite_inf = datetime.strptime("06:00", "%H:%M").time()
    limite_sup = datetime.strptime("18:00", "%H:%M").time()

    if h_inicio < limite_inf or h_fin > limite_sup:
        return "Error: El horario permitido es de 6:00 AM a 6:00 PM.", 400

    # B. Duración máxima (2 horas)
    # Convertimos a datetime para restar
    dt_inicio = datetime.combine(datetime.today(), h_inicio)
    dt_fin = datetime.combine(datetime.today(), h_fin)
    duracion = dt_fin - dt_inicio

    if duracion.total_seconds() > 7200: # 7200 segundos = 2 horas
        return "Error: La reserva no puede exceder las 2 horas.", 400
    
    if duracion.total_seconds() <= 0:
        return "Error: La hora de fin debe ser posterior a la de inicio.", 400

    # C. Cantidad de personas (Mín 2, Máx 6)
    if cantidad_personas < 2 or cantidad_personas > 6:
        return "Error: La capacidad debe ser de 2 a 6 personas.", 400

    # 4. Proceso de Inserción (Si todo es válido)
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id_usuario FROM Usuarios WHERE usuario = ?", (session['usuario'],))
                user_id = cursor.fetchone()[0]
                # Insertar reserva
                query_reserva = """
                    INSERT INTO ReservasSalas (id_usuario, id_sala, fecha, hora_inicio, hora_fin, cantidad_personas, estado)
                    OUTPUT INSERTED.id_reserva
                    VALUES (?, ?, GETDATE(), ?, ?, ?, 'Activa')
                """
                cursor.execute(query_reserva, (user_id, id_sala, hora_inicio_str, hora_fin_str, cantidad_personas))
                id_nueva_reserva = cursor.fetchone()[0]

                # Insertar acompañante
                query_acomp = "INSERT INTO AcompañantesReserva (id_reserva, nombre_completo, carnet, cohorte) VALUES (?, ?, ?, ?)"
                cursor.execute(query_acomp, (id_nueva_reserva, acomp_nombre, acomp_carnet, acomp_cohorte))

                # Marcar sala como ocupada
                cursor.execute("UPDATE Salas SET disponible = 0 WHERE id_sala = ?", (id_sala,))
                conn.commit()
        
        return redirect(url_for('lista_salas'))
    except Exception as e:
        return f"Error en la base de datos: {e}", 500

if __name__ == '__main__':
    app.run(debug=True)