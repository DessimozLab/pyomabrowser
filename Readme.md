# OMA Browser Readme

This readme explains how to get started with working on the pyoma project, 
especially with the browser part of the project.

## Setting things up
The preferred way to work with the OMA Browser is nowadays using 
docker images. The directory `for_docker` contains all the relevant 
information how to set it up and bring it alive using docker-compose.
Please refer to the [Docker Readme](for_docker/Readme.md) for details 
how to set things up. 


## Code organisation

The organisation of the code is at the moment the following:

 - `pybrowser_dev/` contains the information on the project, e.g. settings, wsgi application reference, etc
 - `oma/` is the app that does the actual job.
 - `oma_rest/` is the rest api stuff
 - `export/` contains stuff for the oma standalone exporter on a cluster - you
           might want to deactivate this app. 
You probably want to modify only things in `oma/` or `oma_rest/`

The omabrowser django app does only make very limited use of Django's ORM system,
as most of the data comes from a hdf5 database. Access to this database
is mostly provided by the [pyoma](https://zoo.cs.ucl.ac.uk/doc/pyoma) repository. 


#### Deprecated notes how to setup omabrowser for development (kept for reference)

You most probably want to use virtualenv in order to have a seperate python 
environment for this project. Plenty of informations on how to use virtualenv
is available on the web. Do something along the lines:

```shell script
  virtualenv --python=/usr/bin/python3 ~/venv/pyoma
  source ~/venv/pyoma/bin/activate
```

In there, install the necessary packages using pip (from requirements.txt):

```shell script
  pip install cython numpy
  pip install -r requirements.txt
```

make sure that $DARWIN_BROWSERDATA_PATH points to the directory where the 
pytables version of the browser db (named 'OmaServer.h5') is located.


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


