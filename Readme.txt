This readme explains how to get started with working on the pyoma project.

You most probably want to use virtualenv in order to have a seperate python 
environment for this project. Plenty of informations on how to use virtualenv
is available on the web. Do something along the lines:
 virtualenv --python=/usr/bin/python3 ~/venv/pyoma
 source ~/venv/pyoma/bin/activate

In there, install the necessary packages using pip (from requirements.txt):
pip install cython numpy
pip install -r requirements.txt

make sure that $DARWIN_BROWSERDATA_PATH points to the directory where the 
pytables version of the browser db (named 'OmaServer.h5') is located.

The organisation of the code is at the moment the following:
- pybrowser_dev/ contains the information on the project, e.g. databases ...
- oma/ is the app that does the actual job.
- oma_rest/ is the rest api stuff
- export/ contains stuff for the oma standalone exporter on a cluster - you 
   might want to deactivate this app.
You probably want to modify only things in oma/ or oma_rest/ 

to get a debug instance of pyoma, do the following:
python manage.py migrate --> this creates the necessary databases. This, you only
  have to do once. Note: This does not create any pytables database. This is 
  created outside this project.

python manage.py runserver 8000 --nothreading

--> you can access the omabrowser on http://localhost:8000/



  
