.. role:: sh(code)
    :language: sh

The OMA Browser REST API
============================

The newest release of the OMA browser now features its own REST API, which gives a remote window into the application– which, in case of OMA, allows for usage of the algorithm’s genome predictions in other applications. It can be found at <api_path> and returns data in json,xml or html in response to a query given as an URL. The data from the REST API can be easily accessed via packages such as httpie/coreapi.

REST API ARCHITECTURE
---------------------

+-------------------------------------------+--------------------------+
|    QUERY                                  |            INFO          |
+===========================================+==========================+
|/api/genome/                               | list of all the genomes  |
|                                           | present in the db        |
+-------------------------------------------+--------------------------+
|/api/genome/<genome_id>/                   | genome information       |
+-------------------------------------------+--------------------------+
|/api/genome/<genome_id>/proteins_list/     | list of all the proteins |
|                                           | for a genome             |
+-------------------------------------------+--------------------------+
|/api/protein/<entry_id>/                   | protein information      |
+-------------------------------------------+--------------------------+
|/api/protein/<entry_id>/domains/           | domain information for   |
|                                           | a protein                |
+-------------------------------------------+--------------------------+
|/api/protein/<entry_id>/hog_levels/        | hog levels that a protein|
|                                           | is present in            |
+-------------------------------------------+--------------------------+
|/api/protein/<entry_id>/orthologs/         | orthologs list for       |
| - ?rel_type                               | a protein                |
+-------------------------------------------+--------------------------+
|/api/protein/<entry_id>/ontology/          | ontology information for |
|                                           | a protein                |
+-------------------------------------------+--------------------------+
|/api/protein/<entry_id>/xref/              | cross references for     |
|                                           | a protein                |
+-------------------------------------------+--------------------------+
|/api/pairs/<genome_id1>/<genome_id2>/      | pairwise comparison for  |
| - ?chr1 and ?chr2                         | two given proteins       |
+-------------------------------------------+--------------------------+
|/api/group/<group_id>/                     | oma group information    |
+-------------------------------------------+--------------------------+
|/api/group/<group_id>/close_groups/        | list of close oma groups |
|                                           | for a given oma group    |
+-------------------------------------------+--------------------------+
|/api/hogs/                                 | list of all the hog_id's |
| - ?level                                  | paginated at 100 per page|
+-------------------------------------------+--------------------------+
|/api/hogs/<hog_id>/                        | hog information          |
| - ?level                                  |                          |
+-------------------------------------------+--------------------------+
|/api/hogs/<hog_id>/members/                | list of members for a hog|
| - ?level                                  |                          |
+-------------------------------------------+--------------------------+

ACCESING THE API
---------------------

The data from the REST API can be easily accessed via packages such as httpie/coreapi.

.. code-block:: sh

    http <path>

Python+R bindings


