This readme explains how to get started with working on the pyoma project.

You most probably want to use virtualenv in order to have a seperate python 
environment for this project. Plenty of informations on how to use virtualenv
is available on the web. Do something along the lines:
 mkvirtualenv --python=/usr/bin/python2 pyoma2
 workon pyoma2

In there, install the necessary packages using pip (from requirements.txt):
pip install Cython
pip install numpy
pip install numexpr
pip install tables
pip install django

make sure that $DARWIN_BROWSERDATA_PATH points to the directory where the 
pytables version of the browser db (named 'OmaServer.h5') is located.

The organisation of the code is at the moment the following:
- pybrowser_dev/ contains the information on the project, e.g. databases ...
- oma/ is the app that does the actual job. 
You probably want to modify only things in oma/ 

to get a debug instance of pyoma, do the following:
python manage.py syncdb --> this creates the necessary databases. This, you only
  have to do once. Note: This does not create any pytables database. This is 
  created outside this project.

python manage.py runserver 8000 --nothreading

--> you can access the omabrowser on http://localhost:8000/



  
