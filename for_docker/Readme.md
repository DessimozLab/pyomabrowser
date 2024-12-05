# Running OMA Browser with docker-compose

### TL;DR

- copy `env.template` to `env`
- make a softlink from `.env` to `env`, i.e. `ln -s env .env`
- adjust settings in `env` (OMA_INSTANCE, keys, ...)
- adjust settings in `docker-compose.yml`:
  
  - bind mount release data?
  - bind mount current checkout?

- copy `labgit.cnf.template' to `labgit.cnf`
  - if not using git+ssh to clone repos, set your USER and PASSWORD data for git+https in `labgit.cnf`

- `docker compose build --ssh default` to build containers for OMA browser (`--ssh default` only needed if git+ssh is used)
- `docker compose up -d` to start containers
- `docker compose logs -f` shows log of containers
- access oma instance on http://localhost/oma/home


### Background

The OMA Browser can be run via docker-compose as orchestration 
tool for near production, testing and development purposes.

Currently, the setup has not yet been tested under heavy load, 
but it seems to work quite smoothly on various sized datasets.

The following figure should give you a brief overview of the containers 
and volumes and how they interact:
![docker-setup](docker-setup.png "Overview of container setup") 
 

### Settings in `env` file

First, you need to copy the `env.template` file into `env`. The template 
version does not contain any values about passwords and api keys which
you might need to set. Also, you need to create a soft-link .env -> env 
```bash
ln -s env .env
```

The `env` file contains most settings relevant to build and run the 
containers. The paths variables in the beginning are the mount points 
_inside_ the containers and can in most situations be left as they 
are defined. 

Here are the most relevant variables you need to specify:

- __RELEASE_PATH_HOST__: Path on the host machine where the oma browser data is located, e.g. `/local/data/OMA/All.Jul2024`. This location should have at least the two subfolders `data` and `downloads`.'  

- __OMA_INSTANCE__: The OMA_INSTANCE is the main setting to change between different setups/instances with different features. They load different django settings. The default is `full`.
- __DEPLOYMENT_TYPE__:   Either `production` or `development`. if set to development, the provides additional debugging information.

A bit less common but still relevant settings are:

- __ALLALL_PATH_HOST__: Path where the AllAll files are located. This is only relevant for the Export Standalone functionality.

- __DJANGO_SETTINGS_MODULE__: settings module to be used. can be one of `pybrowser_dev.settings.prod`, `pybrowser_dev.settings.testing`


### Settings in `docker-compose.yml`

In the docker-compose file, you should mainly edit the mount method of 
the omabrowser data. By default, we now recommend using bind mounts, but 
you can also change things to use [docker volume](https://docs.docker.com/storage/volumes/). See section below 
on [copying data into a docker volume](#copying-data-into-the-release_volume)
for how this needs to be done.

Last but not least, by uncommenting the line 

`..:/usr/src/pyomabrowser`

in the web and celery service:volume section, you can mount the current 
repo checkout from your host to the docker containers which allows
to transparently refresh on code changes. Note however that if 
static files change, you have to restart the docker-compose instances.


# Settings in `labgit.cnf`
Building the containers requires cloning GIT repositories from the lab.dessimoz.org 
host. Access to this host can be gained either via git+ssh or git+https. 
Please copy the `labgit.cnf.template` file to `labgit.cnf` and either leave
the definition of LABGIT variable unchanged (i.e. `ssh://gitolite@lab.dessimoz.org:2222`)
or uncomment the second variant `export LABGIT="https://USER:PASSWORD@git.lab.dessimoz.org/git"` 
and specify your USER and PASSWORD in the url.


### Building the images

To build the images you should only need to run 
`docker compose build` from the for_docker/ directory on your host. If you use 
git+ssh you need to add `--ssh default` to the command.  



### Starting services
You should then be able to start the services with 
`docker compose up`. This will run things in the foreground, and 
you can check the logs of the different services. The first time 
you do this using a docker volume for the oma browser data, you
will see error messages the database cannot be opened. This 
means you haven't yet copied the data into the volume. 
(See next point)
You can also start the containers in the background with `docker compose up -d` 
and stop them with `docker compose down`. 

### Copying data into the release_volume
In order to copy the data of a specific release into a 
docker release_volume, you need to mount both, the 
original data and the release_volume into a thin docker 
container and copy the data in there:

```shell script
docker run --rm -ti --volume release_volume:/data -v /path/on/host/to/release:/input oma:latest cp -rpn /input/ /data
```

This command would use the oma container to copy the data from /path/on/host/to/relase into the volume. Note that the 
path should be the directory that contains the `data`, and `downloads` directory of the release you need.

### Removing volumes
When changing a release you should consider removing **all the volume data**, i.e.
the postgres sql data, the media folder and probably also the release data.
You can do that with 
```shell script
docker-compose down --volume
```


### Changes
- discontinued the build_container script - please use now directly `docker compose build`.
- We recently dropped the legacy container from the setup, as all functionality has been ported to the Django webserver.