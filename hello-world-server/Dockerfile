FROM python:3

RUN pip install 'influxdb-client[ciso]'
RUN pip install Flask

ADD main.py .

CMD [ "python", "./main.py" ]