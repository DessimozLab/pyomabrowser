# Generated by Django 2.2.28 on 2023-05-23 09:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('oma', '0002_auto_20170814_1428'),
    ]

    operations = [
        migrations.AlterField(
            model_name='fileresult',
            name='result_type',
            field=models.CharField(max_length=32),
        ),
    ]
