.. role:: sh(code)
    :language: sh

The OMA Browser REST API
============================

The newest release of the OMA browser now features its own REST API, which gives a remote window into the application– which, in case of OMA, allows for usage of the algorithm’s genome predictions in other applications. It can be found at <api_path> and returns data in response to a query given as an URL. The data from the REST API can be easily accessed via packages such as httpie/coreapi which allow for the specification of the format that the data is returned in. + R and Python lib

REST API ARCHITECTURE
---------------------

+-------------------------------------------+--------------------------+
|    QUERY                                  |            INFO          |
+===========================================+==========================+
|/genome/                                   | list of all the genomes  |
|                                           | present in the db        |
+-------------------------------------------+--------------------------+
|/genome/<genome_id>/                       | genome information       |
+-------------------------------------------+--------------------------+
|/genome/<genome_id>/proteins_list/         | list of all the proteins |
|                                           | for a genome             |
+-------------------------------------------+--------------------------+
|/protein/<entry_id>/                       | protein information      |
+-------------------------------------------+--------------------------+
|/protein/<entry_id>/info_links             | hyperlinks for a protein |
+-------------------------------------------+--------------------------+
|/protein/<entry_id>/domains/               | domain information for   |
|                                           | a protein                |
+-------------------------------------------+--------------------------+
|/protein/<entry_id>/hog_levels/            | hog levels that a protein|
|                                           | is present in            |
+-------------------------------------------+--------------------------+
|/protein/<entry_id>/orthologs/             | orthologs list for       |
| - ?rel_type                               | a protein                |
+-------------------------------------------+--------------------------+
|/protein/<entry_id>/ontology/              | ontology information for |
|                                           | a protein                |
+-------------------------------------------+--------------------------+
|/protein/<entry_id>/xref/                  | cross references for     |
|                                           | a protein                |
+-------------------------------------------+--------------------------+
|/pairs/<genome_id1>/<genome_id2>/          | pairwise comparison for  |
| - ?chr1 and ?chr2                         | two given proteins       |
+-------------------------------------------+--------------------------+
|/group/<group_id>/                         | oma group information    |
+-------------------------------------------+--------------------------+
|/group/<group_id>/close_groups/            | list of close oma groups |
|                                           | for a given oma group    |
+-------------------------------------------+--------------------------+
|/hogs/                                     | list of all the hog_id's |
| - ?level                                  | paginated at 100 per page|
+-------------------------------------------+--------------------------+
|/hogs/<hog_id>/                            | hog information          |
| - ?level                                  |                          |
+-------------------------------------------+--------------------------+
|/hogs/<hog_id>/members/                    | list of members for a hog|
| - ?level                                  |                          |
+-------------------------------------------+--------------------------+

ACCESING THE API
---------------------



