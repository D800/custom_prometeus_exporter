#
FROM python:3.12.4

#
WORKDIR /code

#
COPY ./requirements.txt /code/requirements.txt

#
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

#
COPY ./app.py /code/app.py
COPY ./config.yml /code/config.yml

CMD ["fastapi", "run", "app.py", "--port", "23889"]