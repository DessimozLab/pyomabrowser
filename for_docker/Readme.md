# Running OMA Browser with docker-compose

### TL;DR

- copy `env.template` to `env`
- make a softlink from `.env` to `env`, i.e. `ln -s env .env`
- adjust settings in `env` (OMA_INSTANCE, keys, ...)
- adjust settings in `docker-compose.yml`:
  - not a bind mount for release data? (see section on copying data into volume)
- copy `labgit.cnf.template` to `labgit.cnf` and set the git access URL (see below)
- copy `token.template` to `token` (leave empty unless using token-based HTTPS auth)
- build:
  - SSH access: `docker compose build --ssh default` (key must be in SSH agent, see below)
  - HTTPS access: `docker compose build`
- `docker compose up -d` to start containers
- `docker compose logs -f` shows log of containers
- access oma instance on http://localhost/oma/home

__WARNING__: there is a docker-compose.override.yml file in the repo, which enables 
mounting the current repo checkout into the containers. This is useful for development purposes
but is not ideal in production. You can start the containers without loading the override file with 
`docker compose -f docker-compose.yml up -d`. 

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

#### Additional notes about docker-compose.override.yml
We provide a docker-compose.override.yml file in the repo, which overrides 
some aspects of the docker-compose setup, relevant for development purposes.
In particular, the override file mounts the current repo checkout into the 
containers so that changes to the code are immediately reflected in the 
containers. This is useful for development purposes but is not ideal in 
production. Note, however, that if static files change, you have to restart 
the docker-compose instances.

You can start the containers without loading the override file by explicitly 
using the `-f` flag with the base docker-compose.yml file only, e.g. 
`docker compose -f docker-compose.yml up -d`.

To see which configs are loaded exactly, you can use the `docker compose config` command:
`docker compose -f docker-compose.yml config` returns the config of the base docker-compose.yml file, where as
`docker compose config` returns the merged config including the override file.


# Settings in `labgit.cnf` and `token`

Building the containers requires cloning private git repositories from `lab.dessimoz.org`.
Access can be configured either via SSH or HTTPS.

Copy `labgit.cnf.template` to `labgit.cnf`. The file contains a single line: the base URL
to the git server. Three variants are supported:

**1. SSH (default)**
```
ssh://gitolite@lab.dessimoz.org:2222/
```
Use `docker compose build --ssh default` to forward your SSH agent into the build.
The key must be loaded in your SSH agent beforehand:
```bash
ssh-add ~/.ssh/your_lab_key
```
You can verify the key is available with `ssh-add -l`. Docker's `--ssh default` flag
only forwards keys that are already in the agent — it does not read `~/.ssh/config`
`IdentityFile` entries directly.

**2. HTTPS with username and password**
```
https://USER:PASSWORD@git.lab.dessimoz.org/git
```
No `--ssh default` flag needed. Credentials are passed securely as a build secret.

**3. HTTPS with a CI token (e.g. GitLab CI)**
```
https://gitlab-ci-token:${TOKEN}@gitlab.myorg.com/
```
The `${TOKEN}` placeholder is substituted at build time from the `token` secret file.
Copy `token.template` to `token` and put the token value in that file:
```bash
echo "glpat-xxxxxxxxxxxxxxxxxxxx" > token
```
Then build normally (no `--ssh default` needed):
```bash
docker compose build
```

If `labgit.cnf` does not contain `${TOKEN}`, the `token` file is ignored. You still need
the file to exist (an empty file is fine):
```bash
cp token.template token
```


### Building the images

To build the images, run `docker compose build` from the `for_docker/` directory.

| Access method | Build command |
|---|---|
| SSH | `docker compose build --ssh default` |
| HTTPS (password or token) | `docker compose build` |

To build only a specific service:
```bash
docker compose build oma --ssh default
```


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

### Populating the download catalogue (Zenodo data (downloads & OMAmer) and B2 buckets)

The `downloads` app keeps a local database of which files are available for each release
and where they live on Zenodo. This catalogue is **not** populated automatically on startup
— run the following two commands once after the containers are up, and again whenever a new
release is published on Zenodo:

```bash
# Sync all OMA Browser release file lists from the primary concept record
docker compose exec web python manage.py sync_zenodo_release 20816667 --concept --set-latest

# Merge OMAmer HDF5 files (different Zenodo concept, same release names)
docker compose exec web python manage.py sync_zenodo_release 17822900 --concept --merge --release-name-prefix All

# Merge data files from Blackblaze B2 buckets
docker compose exec web python manage.py sync_b2_release <bucket> --scan-releases --base-url <base-url> --merge --key-id <key-id> --key <key>
# e.g: for oma's B2 bucket (you could also put the key in the env file)
docker compose exec web python manage.py sync_b2_release oma-download-0000 --scan-releases --base-url https://downloads.omabrowser.org --merge --key-id <key-id> --key <key>
```

The first command creates one `Release` entry per published Zenodo version and marks the
newest as "latest" (used by the `/All/` download URLs). The second merges the OMAmer files
into those same releases without overwriting any metadata.

For restricted or draft Zenodo records, pass `--token $ZENODO_TOKEN`.

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


### Cloudflare load-based challenge

nginx's rate limits above only shape traffic once it has already reached the origin. `nginx/cloudflare_load_guard.py` adds a layer in front of that: it watches nginx's access log and, when it sees sustained heavy load (high request rate, a high 5xx/429 rate, and/or high median response time), enables a Cloudflare WAF custom rule that puts a Managed Challenge in front of the affected paths — then disables it again once traffic settles. It needs nothing beyond Python 3's standard library and read access to the access log, and can run either as a docker-compose sidecar (recommended for this repo's setup) or standalone via cron on a bare-metal nginx host.

One-time setup, in the Cloudflare dashboard for the zone (same regardless of how the script itself is run):

1. **Security -> WAF -> Custom rules -> Create rule.** Match the URI path(s) to protect (e.g. `starts_with(http.request.uri.path, "/api/")` — or narrower, to the specific endpoint that tends to fall over), action **Managed Challenge**. Save it, but leave it **disabled** — the script is what turns it on.
2. Note the zone ID (dashboard sidebar) and this rule's ruleset/rule IDs. If not obvious from the UI, list them:
   ```bash
   curl -s -H "Authorization: Bearer $CF_API_TOKEN" \
     "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/rulesets/phases/http_request_firewall_custom/entrypoint"
   ```
3. **My Profile -> API Tokens -> Create Token**, "Edit zone WAF" template, restricted to this one zone. Broader tokens are not needed and should not be used here.

#### Docker-compose sidecar (recommended)

The `cloudflare_guard` service in `docker-compose.yml` runs the script in a loop against nginx's own access log. It is gated behind the `cloudflare-guard` compose profile, so it does not start by default — enable it by setting, in your `env` file:

```
NGINX_LOG_TO_FILE=true
COMPOSE_PROFILES=cloudflare-guard
```

`NGINX_LOG_TO_FILE=true` is required regardless of the profile: the sidecar reads `/var/log/nginx/access.log`, which nginx only writes when file logging is turned on (it logs to stdout only by default). Turning it on also makes `nginx.conf.template` define and use the `main_rt` log format automatically, which is what supplies the `rt=$request_time` field the latency trigger needs — no manual nginx config edit required in this mode.

Then fill in the `CF_API_TOKEN`/`CF_ZONE_ID`/`CF_RULESET_ID`/`CF_RULE_ID` variables from the setup above (see the "CLOUDFLARE LOAD-BASED CHALLENGE" section in `env.template` for the full list, including the load thresholds) and run `docker compose up -d` as usual. Two safety nets mean the profile can safely be left enabled without every environment needing this configured:

- If `CF_API_TOKEN` is blank, the container idles (logs a message and sleeps) instead of erroring or crash-looping.
- The read offset and hysteresis counters are kept in a small named volume (`cloudflare_guard_state`), so a container restart doesn't lose track of what's already been processed.

#### Standalone via cron (bare-metal nginx)

If nginx isn't running under this repo's Docker setup at all, run the script directly via cron instead:

The response-time trigger needs `rt=$request_time` in the access log, which is *not* part of nginx's default `combined` format. Add it to the host's nginx config directly — either add `rt=$request_time` to whatever `log_format` it already defines, or add a new one and point `access_log` at it:

```nginx
log_format main_rt '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" rt=$request_time';

access_log /var/log/nginx/access.log main_rt;
```

then `nginx -t && nginx -s reload`. Until this is applied, leave `CF_GUARD_LATENCY_HIGH` unset — the script simply skips the latency trigger when no `rt=` fields are found.

Copy `nginx/cloudflare_load_guard.env.template` to `cloudflare_load_guard.env`, fill in the token/IDs and the path to the real access log, and keep it out of git. Then add a cron entry that sources it and runs the script, e.g. every minute. `set -a`/`set +a` is required around the sourcing — plain `KEY=value` lines (no `export`) only become shell variables, not environment variables a child process like `python3` can see:

```
* * * * * set -a; . /path/to/cloudflare_load_guard.env; set +a; /usr/bin/python3 /path/to/cloudflare_load_guard.py >> /var/log/cloudflare_load_guard.log 2>&1
```

#### Behavior common to both modes

Each run only reads the log bytes appended since the previous run (tracked in a small state file next to it), so it stays cheap even on a busy log. It requires several consecutive elevated windows before enabling the rule and several consecutive calm windows before disabling it again (tunable via `CF_GUARD_CONSECUTIVE_ON`/`_OFF`) — deliberately quicker to turn on than to turn back off — and it always re-reads the rule's live state from Cloudflare before deciding to change it, so a manual toggle in the dashboard is respected rather than immediately undone.

The request-rate, error-rate, and latency thresholds (`CF_GUARD_RPS_HIGH`/`_LOW`, `CF_GUARD_ERROR_RATE_HIGH`, `CF_GUARD_LATENCY_HIGH`) have no safe universal default — run with `CF_GUARD_DRY_RUN=true` (or `--dry-run`) against real traffic first to see what the metrics look like before trusting it to act. Use `--replay <log-file>` to calibrate offline against a historical access log instead (see `cloudflare_load_guard.py --help`).


### Changes
- discontinued the build_container script - please use now directly `docker compose build`.
- We recently dropped the legacy container from the setup, as all functionality has been ported to the Django webserver.
- `labgit.cnf` is now a plain URL file (not a shell script). Supports SSH, HTTPS with credentials, or HTTPS with a `${TOKEN}` placeholder substituted from the `token` secret file.
- SSH builds now configure the container's SSH client to use `gitolite` as the login user for `lab.dessimoz.org`, ensuring compatibility with both the lock file URLs and Docker's SSH agent forwarding.
