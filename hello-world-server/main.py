import os
import logging
from sys import stdout
from flask import Flask, request

app = Flask(__name__)

logger = logging.getLogger('hw-logger')
logger.setLevel(logging.DEBUG) # set logger level
logFormatter = logging.Formatter\
("%(name)-12s %(asctime)s %(levelname)-8s %(filename)s:%(funcName)s %(message)s")
consoleHandler = logging.StreamHandler(stdout) #set streamhandler to stdout
consoleHandler.setFormatter(logFormatter)
logger.addHandler(consoleHandler)


@app.route('/hw', methods=['GET'])
def profileQuery():
    logger.info(" route: /hw, method: GET")
    return "Hello World!\n"


if __name__ == '__main__':
    try:
        p = os.getenv("FLASK_SERVER_PORT", 5000)
        app.run(host="0.0.0.0", port=p)
    except Exception as e:
        logger.error(e)
