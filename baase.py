from flask import Flask, render_template, request, redirect, url_for
app = Flask(__name__)

@app.route('/')
def home():
    return render_template('home.html')

@app.route("/login", methods=["POST", "GET"])
def login():
    if request.method == "POST":
        user = request.form["usuario"]
        password = request.form["contraseña"]
        cohorte = request.form["cohorte"] #enviar esto a una base de datos
        return render_template("saludo.html" , usuario=user) #hacer que lo busque en la base de datos
    else:
        return render_template("login.html") #hacer la page login


if __name__ == '__main__':
    app.run(debug=True)