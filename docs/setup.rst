.. role:: sh(code)
    :language: sh

Setting up an  OMA Browser
==========================
The preferred way to work with the OMA Browser is nowadays using
docker images. The directory `for_docker` in the pyomabrowser repository
contains all the relevant information how to set it up and bring it
alive using docker-compose.

The OMA Browser can be run via docker-compose as orchestration
tool for near production, testing and development purposes.

Here are the necessary steps to start an instance:

* clone the source of the pyomabrowser repo:

.. code-block:: sh

    git clone ssh://gitolite@lab.dessimoz.org:2222/pyomabrowser
    cd pyomabrowser

* The next step is that you need a hdf5 database instance. There are several options how
  you could obtain or refer to one.

  * copy a release from the UniL NAS, e.g. Test.Jul2014, the corona oma server,
    or a full release. Store the whole directory somewhere on your computer or
    on a external disk. Full release is quite big, several 100GB. Keep the
    structure with ``./data`` and ``./downloads`` subdirectories.

  * alternatively, you can also mount the filesystem via sshfs and directly point with your
    DARWIN_BRWOSERDATA_PATH to the path where the file exists. This is handy, but requires
    a very fast connection.

* now, we're ready to adjust the docker settings. For this move into ``pyomabrowser/for_docker`` directory

.. code-block:: sh

    cd pyomabrowser/for_docker

You will also find up-to-date instruction in the Readme.md file in there.

Overview of system
^^^^^^^^^^^^^^^^^^

The following figure should give you a brief overview of the containers
and volumes and how they interact:

.. image:: ../for_docker/docker-setup.png
   :target: docker-setup.png
   :alt: docker-setup

In our setup of the containers, we make use of the
DOCKER_BUILDKIT extension, especially the ``--ssh default`` feature
to access the lab's git repo server. Currently (May 2020) this feature is
not yet supported by docker-compose directly. Because of this, the
docker images have to be converted with an extra script named ``build_container``.

Settings in ``env`` file
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The ``env`` file contains most settings relevant to build and run the
containers. The paths variables in the beginning are the mount points
*inside* the containers and can in most situations be left as they
are defined.

The values for ``OMA_INSTANCE``\ , and ``PRODUCTION_TYPE`` can be modified
as needed. The OMA_INSTANCE has the main thing to change between
different setups/instances with different features. They load different
django settings.

The settings for PYOMABROWSER_CODEBASE and PYOMABROWSER_GITTAG variables
should be adapted depending on whether from the current source checkout
or directly from the git-repo at a certain tag should be used to build
the oma docker image.

Settings in ``docker-compose.yml``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In the docker-compose file, you should mainly edit the mount method of
the omabrowser data. By default it assumes a
`docker volume <https://docs.docker.com/storage/volumes/>`_\ , but also
a **bind mount** of a host directory into the container is possible (but
discouraged for production).

Last but not least, by uncommenting the line
``..:/usr/src/pyomabrowser``

in the web and celery service:volume section, you can mount the current
repo checkout from your host to the docker containers which allows
to transparently refresh on code changes. Note however that if
static files change, you have to restart the docker-compose instances.

Building the images
^^^^^^^^^^^^^^^^^^^

To build the images you should only need to run
``build_container`` from the for_docker/ directory on your host.
Note that this is a simple python script that requires yaml to
be installed. You might need to install it into a virtualenv or
install it systemwide with ``pip install pyaml``.

Starting services
^^^^^^^^^^^^^^^^^

You should then be able to start the services with
``docker-compose up``. This will run things in the foreground and
you can check the logs of the different services. The first time
you do this using a docker volume for the oma browser data, you
will see error messages the the database cannot be opened. This
means you haven't yet copied the data into the volume.
(See next point)
You can also start the containers in the background with ``docker-compose up -d``
and stop them with ``docker-compose down``.



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
