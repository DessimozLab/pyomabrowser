This readme explains how to get started with working on the pyoma project.

You most probably want to use virtualenv in order to have a seperate python 
environment for this project. Plenty of informations on how to use virtualenv
is available on the web. Do something along the lines:

  virtualenv --python=/usr/bin/python3 ~/venv/pyoma
  source ~/venv/pyoma/bin/activate

In there, install the necessary packages using pip (from requirements.txt):

  pip install cython numpy
  pip install -r requirements.txt

make sure that $DARWIN_BROWSERDATA_PATH points to the directory where the 
pytables version of the browser db (named 'OmaServer.h5') is located.

The organisation of the code is at the moment the following:

 - pybrowser_dev/ contains the information on the project, e.g. databases ...
 - oma/ is the app that does the actual job.
 - oma_rest/ is the rest api stuff
 - export/ contains stuff for the oma standalone exporter on a cluster - you
           might want to deactivate this app.
You probably want to modify only things in oma/ or oma_rest/


To get a debug instance of pyoma, do the following:

- Ensure RabbitMQ (message broker) is running on your computer. You might need to
  install it (linux: apt-get install rabbitmq; mac: brew install rabbitmq) and start
  the service. If rabbitmq is not running, the OMA Browser might hang forever on
  some requests.

- Create internal databases for Django:
  python manage.py migrate
  --> this creates the necessary databases. This, you only have to do once.
  Note: This does not create any pytables database. This is
        created outside this project.

- Start debug instance on your local computer:
  python manage.py runserver 8000 --nothreading

  --> you can access the omabrowser on http://127.0.0.1:8000/

Pro tips
--------

- If the port 8000 is already used and you get an error when running the server,
you can shutdown process using it by running 'sudo lsof -t -i tcp:8000 | xargs kill -9')
- If the page take forever to load (especially on hard load), don't use
the --nothreading argument in python manage.py runserver 8000.


Docker based instance
---------------------

we can now also build a full working omabrowser (as of now no darwin parts, but
all the rest is supported) in Docker.

You need to have a recent version of Docker installed on your host computer (at
least version 18.09). Then you can:

1) build oma:latest container:
   DOCKER_BUILDKIT=1 docker build -t oma:latest -f for_docker/oma/Dockerfile --ssh default .

2) run the omabrowser using composer:
   docker-compose up -d

3) if this is the first time you use it, you need to add dataset to the docker 
   volume. Get it from the ucl project share 
     /data/ul/projects/cdessimo/oma-browser/<release>/data
   and add it to the docker volume:
   docker cp <path> pyomabrowser_web_1:/data/release/

   Alternatively, if this is going to be too big for your docker volume, you 
   can also mount it directly. see in docker-compose.yml the commented version
   which uses the data from an external usb disk (/Volumes/TOSHIBA\ EXT/...)
   -> Note that 'release_volume' argument should be commented (3 instances in the
   files)

4) run migrate and collect static:
   docker-compose exec web ./manage.py migrate
   docker-compose exec web ./manage.py collectstatic --no-input --flush

5) restart docker-compose
   docker-compose down
   docker-compose up -d 

6) access in your browser localhost:8080
