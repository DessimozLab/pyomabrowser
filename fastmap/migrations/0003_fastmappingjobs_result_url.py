# Generated by Django 2.2.12 on 2021-05-26 08:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fastmap', '0002_fastmappingjobs_map_method'),
    ]

    operations = [
        migrations.AddField(
            model_name='fastmappingjobs',
            name='result_url',
            field=models.URLField(blank=True),
        ),
    ]