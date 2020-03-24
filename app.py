# coding:utf-8
from flask import Flask, jsonify

from eureka import Eureka


app = Flask(__name__)
app.config.from_object('config')
eureka = Eureka(app)


@app.route('/')
def hello_world():
    return jsonify(app.eureka.other_apps)


if __name__ == '__main__':
    app.run()
