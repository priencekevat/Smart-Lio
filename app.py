from flask import Flask, render_template

app = Flask(__name__, template_folder="static")

@app.route('/')
def home():
    return "Hello Smart Lio 🚀 Backend is running!"

@app.route('/map')
def map_page():
    return render_template('map.html')

if __name__ == "__main__":
    app.run(debug=True)