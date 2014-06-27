import django.conf
import tables

db_handle = tables.open_file(django.conf.settings.HDF5DB['PATH'], 'r')
print('loaded db_handle');
 
