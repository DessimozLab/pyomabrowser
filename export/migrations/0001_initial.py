# -*- coding: utf-8 -*-
# Generated by Django 1.9.7 on 2018-07-25 08:06
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='StandaloneExportJobs',
            fields=[
                ('data_hash', models.CharField(max_length=32, primary_key=True, serialize=False)),
                ('state', models.CharField(max_length=8)),
                ('genomes', models.TextField(null=True)),
                ('result', models.FileField(blank=True, upload_to='')),
                ('create_time', models.DateTimeField(auto_now=True)),
                ('processing', models.BooleanField(verbose_name=False)),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('name', models.CharField(blank=True, max_length=64)),
            ],
        ),
    ]
