.. role:: sh(code)
    :language: sh

Howto set up a VM and provisioning it
=====================================

These are a few notes taken by Adrian while developing the setup. But I'm sure
you can already use much of it directly if needed.


Setting up a virtual machine with vagrant
-----------------------------------------

Vagrant is a tool to script setting up virtual machines, so you can
more or less configure it (amount of resources,...) in a config file
and vagrant will create it. Here we use virtualbox as the underlying
tool to run the virtualmachines.

Note that the VM runs on your local computer, so it needs to share the
amount of resources you specify with your host operating system. There
is only harmful things that can happen if you for example specify too
much RAM in the config. Resources do not appear from nowhere.

Here are the steps you need to do

- Clone the ansible repo (or part of the pyomabrowser repo?) it contains the
  Vagrantfile (config for the VMs) and afterwards also the ansible playbooks
  to install the whole stack of dependencies for the OMA Browser.

- Install virtualbox and vagrant to your host computer. Available from
  https://www.virtualbox.org/wiki/Downloads
  and https://www.vagrantup.com/downloads.html.

- Install ansible (either from package managment such as homebrew or from pip.
  Personally I'm using the homebrew version)


Next, we will create the virtual machine(s). The Vagrantfile contains the
definition of the base installation. Currently, there are definitions for trusty
and xenial, two long term releases of ubuntu. Others might follow as well.
To make working with the VMs more easily, we will make sure that we can
autmatically login as root to them, and that a new instance of the VM will not
bother you that the known_hosts file is different. Adding the following section
will allow you to do so:

.. code-block:: sh

    cat >> ~/.ssh/config << EOF
    Host 192.168.33.* *.oma.test
        StrictHostKeyChecking no
        UserKnownHostsFile=/dev/null
        User root
        LogLevel ERROR
    EOF

Make sure the file has 600 permissions at the end (in case it didn't exist before).

Add the following plugin to vagrant:

.. code-block:: sh

    vagrant plugin install vagrant-hostsupdater

Then, you can instantiate one or several virtual machines by calling

.. code-block:: sh

    vagrant up (name)

where *name* is optional and should be replaced by any of the names in the Vagrantfile, e.g. *trusty*.

Now, you have your VM up and running (if everything went well) and you can simply ssh into it with

.. code-block:: sh

    ssh trusty.oma.test

Vagrant has a lot of available commands, most importantly vagrant up (starts a vm), vagrant suspend (stops a vm)
and vagrant destroy (removes a vm entirely). The help pages will give you

Next, we will install the dependencies and configuration for all of the oma browser using Ansible.


Provisioning a OMA Virtual Machine with Ansible
-----------------------------------------------

this is under development... Come back later!