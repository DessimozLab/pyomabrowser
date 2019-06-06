# syntax=docker/dockerfile:1.0.0-experimental

# pull official base image
FROM python:3.7-slim

# set work directory
WORKDIR /usr/src/pyomabrowser

# set environment varibles
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apt-get -qq update \
    && apt-get install -y --no-install-recommends \
       wget openssh-client git-core gcc build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -m 700 /root/.ssh/ \
    && touch -m 600 /root/.ssh/known_hosts \
    && ssh-keyscan -p 2222 lab.dessimoz.org >> /root/.ssh/known_hosts


# install dependencies
RUN pip install --upgrade pip
RUN pip install pipenv
#COPY ./Pipfile .Pipfile.lock /usr/src/pyomabrowser
COPY requirements.txt /usr/src/pyomabrowser
COPY ./OmaServer.h5 ./OmaServer.h5.idx /data/

#RUN pipenv install --system --dev
RUN --mount=type=ssh pip install -r requirements.txt

COPY . /usr/src/pyomabrowser

