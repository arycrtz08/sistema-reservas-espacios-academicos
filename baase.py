from flask import Flask, render_template, request, redirect, url_for
app = Flask(__name__)

@app.route('/')
def home():
    return render_template('home.html')

@app.route("/login", methods=["POST", "GET"])
def login():
    if request.method == "POST":
        user = request.form["usuario"]
        carnet = request.form["contraseña"]
        cohorte = request.form["cohorte"] # en variable local

        # Aquí "guardo" en variables del back-end; luego puedes insertar en DB si quieres
        usuario = user
        carnet_us = carnet
        cohorte_sel = cohorte

        return render_template("saludo.html", usuario=usuario)
    else:
        return render_template("login.html") #hacer la page login


if __name__ == '__main__':
    app.run(debug=True)