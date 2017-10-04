.. role:: sh(code)
    :language: sh

Setting up an  OMA Browser
==========================

There is a difference between a development environment setup and the production
setup. The first one is usually relatively simple to setup as it involves most often
only a Django server. In the following we explain how to setup the development
setup from basic to more complicated functions, intended to be run on a simple laptop
or dev host and finalize the section with the additioinal setup instructions
requried by the production site (which hosts also darwin and is capable to serve
many requests simultaniously).

Development configuration
-------------------------

* Prepare a virtual environment for at least python3.4. You can do that best with pyenv.
  details are available :doc:`in the zoo documentation <zoo:setup>`

* clone the source of the pyomabrowser repo and install the dependencies:

.. code-block:: sh

    git clone ssh://gitolite@lab.dessimoz.org:2222/pyomabrowser
    cd pyomabrowser
    pip install -r requirements.txt

* The next step is that you need a hdf5 database instance. There are several options how
  you could obtain or refer to one.

  * a basic test db is accessible from the public OMA Browser:
    http://omabrowser.org/All/Test.OmaServer.h5. This database is useful if you want
    to play around on your laptop and don't have a lot of disc space available. Once you
    downloaded the file, rename it to OmaServer.h5 and either place it into the pyomabrowser
    repo or set the environment variable DARWIN_BROWSERDATA_PATH to the folder where you
    downloaded the file to, e.g. :sh:`export DARWIN_BRWOSERDATA_PATH=/path/to/download/folder`


  * alternatively, you can copy the big file to you laptop. it is available on the
    cs and ucl shared space under /oma-{browser,server}/<release>/data/OmaServer.h5.
    The file is quite big (>50GB). procede afterwards as with the above.

  * the last option is to mount the filesystem via sshfs and directly point with your
    DARWIN_BRWOSERDATA_PATH to the path where the file exists. This is handy, but requires
    a very fast connection and will probably break the async computation functionalities like
    the msa or marker gene export.

Now, you are ready to start your server locally using the django 'runserver' command.
If you are not familiar with `Django <https://www.djangoproject.com/>`_, have a careful
ready about it and consider doing their `introduction tutorial <https://docs.djangoproject.com>`_.
Essentially, you can start the service with

.. code-block:: sh

    python manage.py migrations
    python manage.py runserver --nothreading

and access the instance in your web browser on http://localhost:8000.

Advanced features
#################

To be able to test the asynchronous features you need to install rabbitmq on your machine
using homebrew or apt package manager. The omabrowser will connect as guest on localhost
by default, so you don't have to configure any users there. Make sure rabbitmq-server is
running either by starting it manually or as service in the background.

Then you need to start at least one celery process that does the async work. You can do
that by running to following commands in the pyomabrowser root folder:

.. code-block:: sh

    celery worker -A pybrowser_dev --pool=solo --loglevel=DEBUG

The pool=solo is needed on macos only. obviously, you can play with the loglevel parameter.



Production site configuration
-----------------------------
The main omabrowser instance has a python and darwin backend. Both are served from a single
VM server (oma.ucl.ac.uk).


DNS and contact mail config
###########################

DNS entries are regegistered at https://hexonet.net with the "cbrg" account. The password
for this is available on the darwin home account or ask Adrian about it.

The email address contact@omabrowser.org is a mail forward that is registered directly 
at the hexonet account as well. It currently points to adrian.altenhoff@inf.ethz.ch
