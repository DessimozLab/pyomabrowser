.. role:: sh(code)
    :language: sh

The OMA Browser REST API
============================

The OMA REST API serves as a remote window into the OMA database and so allows the users to access the data they need easily through HTTP requests sent to the server . This abstraction of OMA browser’s data and functions also allows it to be more accessible via programming languages other than Python. Requests can be sent to:

http://omabrowser.org/api

REST
----
The new OMA API is a RESTful API, an architectural style that is based on URLs and HTTP protocol. It was designed to be stateless and hence is does not save data internally between the HTTP requests but rather makes use of caching to be more lightweight and as a result, more dynamic. It supports many data formats and the predominant use of the JSON data format makes it very browser-compatible.

Pagination
----------
Some endpoints such as the list of all Hierarchical Orthologous groups and OMA groups returns a very long list. In order to keep the response size and time manageable the API will take advantage of pagination. Pagination is a mechanism for returning a subset of the results for a request (namely the first 100 objects) and allowing for subsequent requests to “page” through the rest of the results until the end is reached.

HTTP Status Codes
-----------------

+-------------+--------------------------+
|STATUS CODE  |       DESCRIPTION        |
+=============+==========================+
|    200      |     OK. All is well.     |
+-------------+--------------------------+
|    400      |     Malformed request.   |
+-------------+--------------------------+
|    404      |         Not found.       |
+-------------+--------------------------+
|    500      |   Internal Server Error. |
+-------------+--------------------------+

Errors
------
Error responses will have a consistently formed JSON body.

+-------------+----------------------------------------------------------------------+
|    Key      |                               Value                                  |
+=============+======================================================================+
|  message    |    Human readable message which corresponds to the client error.     |
+-------------+----------------------------------------------------------------------+
|   code      |                  Underscored delimited string.                       |
+-------------+----------------------------------------------------------------------+


API Summary
----------------
+-------------------------------------------+--------------------------------+
|     Endpoint                              |        Description             |
+===========================================+================================+
|/genome/                                   | `Genome`_                      |
+-------------------------------------------+--------------------------------+
|/genome/<genome_id>/                       | `Genome-detail`_               |
+-------------------------------------------+--------------------------------+
|/genome/<genome_id>/proteins_list/         | `Genome-detail-proteins_list`_ |
+-------------------------------------------+--------------------------------+
|/protein/<entry_id>/                       | `Protein`_                     |
+-------------------------------------------+--------------------------------+
|/protein/<entry_id>/domains/               | `Protein-domains`_             |
+-------------------------------------------+--------------------------------+
|/protein/<entry_id>/orthologs/             | `Protein-orthologs`_           |
+-------------------------------------------+--------------------------------+
|/protein/<entry_id>/ontology/              | `Protein-ontology`_            |
+-------------------------------------------+--------------------------------+
|/protein/<entry_id>/xref/                  | `Protein-xref`_                |
+-------------------------------------------+--------------------------------+
|/pairs/<genome_id1>/<genome_id2>/          | `Pairs`_                       |
+-------------------------------------------+--------------------------------+
|/group/                                    | `Group`_                       |
+-------------------------------------------+--------------------------------+
|/group/<group_id>/                         | `Group-detail`_                |
+-------------------------------------------+--------------------------------+
|/group/<group_id>/close_groups/            | `Group-detail-close-groups`_   |
+-------------------------------------------+--------------------------------+
|/hog/                                      | `HOG`_                         |
+-------------------------------------------+--------------------------------+
|/hog/<hog_id>/                             | `HOG-detail`_                  |
+-------------------------------------------+--------------------------------+
|/hog/<hog_id>/members/                     | `HOG-detail-members`_          |
+-------------------------------------------+--------------------------------+
|/taxonomy/                                 | `Taxonomy`_                    |
+-------------------------------------------+--------------------------------+
|/taxonomy/<root_level>                     | `Taxonomy-root`_               |
+-------------------------------------------+--------------------------------+


Genome
^^^^^^
.. http:get:: /api/genome/

   The list of all the genomes in the database, paginated at 100 per page.

   **Example request**:

   .. sourcecode:: http

      GET /api/genome/ HTTP/1.1
      Host: omabrowser.org/api
      Accept: application/json

   **Example response**:

   .. sourcecode:: http

      HTTP 200 OK
      Allow: GET, HEAD, OPTIONS
      Content-Type: application/json
      Vary: Accept

        {
            "count": 4,
            "next": null,
            "previous": null,
            "results": [
                {
                    "code": "YEAST",
                    "taxon_id": 559292,
                    "species": "Saccharomyces cerevisiae (strain ATCC 204508 / S288c)",
                    "genome_url": "http://127.0.0.1:8000/api/genome/YEAST/"
                },
                {
                    "code": "SCHPO",
                    "taxon_id": 284812,
                    "species": "Schizosaccharomyces pombe (strain 972 / ATCC 24843)",
                    "genome_url": "http://127.0.0.1:8000/api/genome/SCHPO/"
                },
                {
                    "code": "PLAF7",
                    "taxon_id": 36329,
                    "species": "Plasmodium falciparum (isolate 3D7)",
                    "genome_url": "http://127.0.0.1:8000/api/genome/PLAF7/"
                },
                {
                    "code": "ASHGO",
                    "taxon_id": 284811,
                    "species": "Ashbya gossypii (strain ATCC 10895 / CBS 109.51 / FGSC 9923 / NRRL Y-1056)",
                    "genome_url": "http://127.0.0.1:8000/api/genome/ASHGO/"
                }
            ]
        }


Genome-detail
^^^^^^^^^^^^^
.. http:get:: /genome/<genome_id>

   The information available for a genome entry in the database. The genome id can be either genome's NCBI taxon id or its 5 letter UniProt Species code.

   **Example request**:

   .. sourcecode:: http

      GET /genome/YEAST/ HTTP/1.1
      Host: omabrowser.org/api
      Accept: application/json

   **Example response**:

   .. sourcecode:: http

    HTTP 200 OK
    Allow: GET, HEAD, OPTIONS
    Content-Type: application/json
    Vary: Accept

    {
        "code": "YEAST",
        "taxon_id": 559292,
        "species": "Saccharomyces cerevisiae (strain ATCC 204508 / S288c)",
        "nr_entries": 6352,
        "lineage": [
            "Saccharomyces cerevisiae (strain ATCC 204508 / S288c)",
            "Saccharomycetaceae",
            "Saccharomycetales",
            "Saccharomycetes",
            "Saccharomycotina",
            "saccharomyceta",
            "Ascomycota",
            "Dikarya",
            "Fungi",
            "Opisthokonta",
            "Eukaryota"
        ],
        "proteins_list": "http://127.0.0.1:8000/api/genome/YEAST/proteins_list/",
        "chromosomes": [
            {
                "entry_ranges": [
                    [
                        1527,
                        1754
                    ]
                ],
                "id": "IX"
            },
            {
                "entry_ranges": [
                    [
                        1783,
                        2091
                    ]
                ],
                "id": "V"
            },
            {
                "entry_ranges": [
                    [
                        714,
                        1526
                    ]
                ],
                "id": "IV"
            },
            {
                "entry_ranges": [
                    [
                        5860,
                        6352
                    ]
                ],
                "id": "XVI"
            },
            {
                "entry_ranges": [
                    [
                        1,
                        110
                    ]
                ],
                "id": "I"
            },
            {
                "entry_ranges": [
                    [
                        2790,
                        3091
                    ]
                ],
                "id": "VIII"
            },
            {
                "entry_ranges": [
                    [
                        4370,
                        4864
                    ]
                ],
                "id": "XIII"
            },
            {
                "entry_ranges": [
                    [
                        111,
                        541
                    ]
                ],
                "id": "II"
            },
            {
                "entry_ranges": [
                    [
                        1755,
                        1782
                    ]
                ],
                "id": "Mito"
            },
            {
                "entry_ranges": [
                    [
                        4865,
                        5283
                    ]
                ],
                "id": "XIV"
            },
            {
                "entry_ranges": [
                    [
                        3480,
                        3819
                    ]
                ],
                "id": "XI"
            },
            {
                "entry_ranges": [
                    [
                        2092,
                        2227
                    ]
                ],
                "id": "VI"
            },
            {
                "entry_ranges": [
                    [
                        542,
                        713
                    ]
                ],
                "id": "III"
            },
            {
                "entry_ranges": [
                    [
                        5284,
                        5859
                    ]
                ],
                "id": "XV"
            },
            {
                "entry_ranges": [
                    [
                        3092,
                        3479
                    ]
                ],
                "id": "X"
            },
            {
                "entry_ranges": [
                    [
                        3820,
                        4369
                    ]
                ],
                "id": "XII"
            },
            {
                "entry_ranges": [
                    [
                        2228,
                        2789
                    ]
                ],
                "id": "VII"
            }
        ]
    }

Genome-detail-proteins_list
^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. http:get:: /genome/<genome_id>/proteins_list/

   The list of all the proteins available for a genome, paginated at 100 per page. The genome id can be either genome's NCBI taxon id or its 5 letter UniProt Species code.

   **Example request**:

   .. sourcecode:: http

      GET /genome/YEAST/proteins_list/ HTTP/1.1
      Host: omabrowser.org/api
      Accept: application/json

   **Example response**:

   .. sourcecode:: http

      HTTP 200 OK
      Allow: GET, HEAD, OPTIONS
      Content-Type: application/json
      Vary: Accept

    {
        "count": 6352,
        "next": "http://127.0.0.1:8000/api/genome/YEAST/proteins_list/?page=2",
        "previous": null,
        "results": [
            {
                "entry_nr": 1,
                "entry_url": "http://127.0.0.1:8000/api/protein/1/",
                "omaid": "YEAST00001",
                "canonicalid": "YA069_YEAST",
                "sequence_md5": "1b435c086480dfb2b4f04107e3d685a4"
            },
            {
                "entry_nr": 2,
                "entry_url": "http://127.0.0.1:8000/api/protein/2/",
                "omaid": "YEAST00002",
                "canonicalid": "YAG8_YEAST",
                "sequence_md5": "b2adabf2eca2f803ba3e7c1f3e490390"
            }

Protein
^^^^^^^
.. http:get:: /protein/<protein_id>/

   The basic information available for a protein entry in the database. Protein id can be either its oma id, its canonical id or its entry number (version specific).

   **Example request**:

   .. sourcecode:: http

      GET /protein/YEAST108 HTTP/1.1
      Host: omabrowser.org/api
      Accept: application/json

   **Example response**:

   .. sourcecode:: http

    HTTP 200 OK
    Allow: GET, HEAD, OPTIONS
    Content-Type: application/json
    Vary: Accept

    {
        "entry_nr": 108,
        "omaid": "YEAST00108",
        "canonicalid": "PPAB_YEAST",
        "sequence_md5": "f490baccb194ea825ba3e59bcf9fa774",
        "oma_group": 3764,
        "roothog_id": 63,
        "oma_hog_id": "HOG:0000063.2a",
        "hog_levels": [
            "Ascomycota",
            "Saccharomycetaceae",
            "Saccharomycetales",
            "Saccharomycetes",
            "Saccharomycotina",
            "saccharomyceta",
            "Saccharomyces cerevisiae (strain ATCC 204508 / S288c)"
        ],
        "chromosome": "I",
        "locus": [
            225460,
            226863,
            1
        ],
        "sequence_length": 467,
        "sequence": "MLKSAVYSILAASLVNAGTIPLGKLSDIDKIGTQTEIFPFLGGSGPYYSFPGDYGISRDLPESCEMKQVQMVGRHGERYPTVSKAKSIMTTWYKLSNYTGQFSGALSFLNDDYEFFIRDTKNLEMETTLANSVNVLNPYTGEMNAKRHARDFLAQYGYMVENQTSFAVFTSNSNRCHDTAQYFIDGLGDKFNISLQTISEAESAGANTLSAHHSCPAWDDDVNDDILKKYDTKYLSGIAKRLNKENKGLNLTSSDANTFFAWCAYEINARGYSDICNIFTKDELVRFSYGQDLETYYQTGPGYDVVRSVGANLFNASVKLLKESEVQDQKVWLSFTHDTDILNYLTTIGIIDDKNNLTAEHVPFMENTFHRSWYVPQGARVYTEKFQCSNDTYVRYVINDAVVPIETCSTGPGFSCEINDFYDYAEKRVAGTDFLKVCNVSSVSNSTELTFFWDWNTKHYNDTLLKQ",
        "cdna": "ATGTTGAAGTCAGCCGTTTATTCAATTTTAGCCGCTTCTTTGGTTAATGCAGGTACCATACCCCTCGGAAAGTTATCTGACATTGACAAAATCGGAACTCAAACGGAAATTTTCCCATTTTTGGGTGGTTCTGGGCCATACTACTCTTTCCCTGGTGATTATGGTATTTCTCGTGATTTGCCGGAAAGTTGTGAAATGAAGCAAGTGCAAATGGTTGGTAGACACGGTGAAAGATACCCCACTGTCAGCAAAGCCAAAAGTATCATGACAACATGGTACAAATTGAGTAACTATACCGGTCAATTCAGCGGAGCATTGTCTTTCTTGAACGATGACTACGAATTTTTCATTCGTGACACCAAAAACCTAGAAATGGAAACCACACTTGCCAATTCGGTCAATGTTTTGAACCCATATACCGGTGAGATGAATGCTAAGAGACACGCTCGTGATTTCTTGGCGCAATATGGCTACATGGTCGAAAACCAAACCAGTTTTGCCGTTTTTACGTCTAACTCGAACAGATGTCATGATACTGCCCAGTATTTCATTGACGGTTTGGGTGATAAATTCAACATATCCTTGCAAACCATCAGTGAAGCCGAGTCTGCTGGTGCCAATACTCTGAGTGCCCACCATTCGTGTCCTGCTTGGGACGATGATGTCAACGATGACATTTTGAAAAAATATGATACCAAATATTTGAGTGGTATTGCCAAGAGATTAAACAAGGAAAACAAGGGTTTGAATCTGACTTCAAGTGATGCAAACACTTTTTTTGCATGGTGTGCATATGAAATAAACGCTAGAGGTTACAGTGACATCTGTAACATCTTCACCAAAGATGAATTGGTCCGTTTCTCCTACGGCCAAGACTTGGAAACTTATTATCAAACGGGACCAGGCTATGACGTCGTCAGATCCGTCGGTGCCAACTTGTTCAACGCTTCAGTGAAACTACTAAAGGAAAGTGAGGTCCAGGACCAAAAGGTTTGGTTGAGTTTCACCCACGATACCGATATTCTGAACTATTTGACCACTATCGGCATAATCGATGACAAAAATAACTTGACCGCCGAACATGTTCCATTCATGGAAAACACTTTCCACAGATCCTGGTACGTTCCACAAGGTGCTCGTGTTTACACTGAAAAGTTCCAGTGTTCCAATGACACCTATGTTAGATACGTCATCAACGATGCTGTCGTTCCAATTGAAACCTGTTCTACTGGTCCAGGGTTCTCCTGTGAAATAAATGACTTCTACGACTATGCTGAAAAGAGAGTAGCCGGTACTGACTTCCTAAAGGTCTGTAACGTCAGCAGCGTCAGTAACTCTACTGAATTGACCTTTTTCTGGGACTGGAATACCAAGCACTACAACGACACTTTATTAAAACAGTAA",
        "domains": "http://127.0.0.1:8000/api/protein/108/domains/",
        "xref": "http://127.0.0.1:8000/api/protein/108/xref/",
        "orthologs": "http://127.0.0.1:8000/api/protein/108/orthologs/",
        "ontology": "http://127.0.0.1:8000/api/protein/108/ontology/"
    }

Protein-domains
^^^^^^^^^^^^^^^
.. http:get:: /protein/<protein_id>/domains

   The information available for the domains in a protein. Protein id can be either its oma id, its canonical id or its entry number (version specific).

   **Example request**:

   .. sourcecode:: http

      GET /protein/YEAST108/domains HTTP/1.1
      Host: omabrowser.org/api
      Accept: application/json

   **Example response**:

   .. sourcecode:: http

    HTTP 200 OK
    Allow: GET, HEAD, OPTIONS
    Content-Type: application/json
    Vary: Accept

    {
        "regions": [
            {
                "location": "35:439",
                "domainid": "3.40.50.1240",
                "source": "CATH/Gene3D",
                "name": "Phosphoglycerate mutase-like"
            }
        ],
        "length": 468,
        "seq_id": "f490baccb194ea825ba3e59bcf9fa774"
    }

Protein-orthologs
^^^^^^^^^^^^^^^^^
.. http:get:: /protein/<protein_id>/orthologs

   List of orthologs for a protein entry. Protein id can be either its oma id, its canonical id or its entry number (version specific).

   :query reltype: filtering of the orthologs by a specific relationship type indicated

   **Example request**:

   .. sourcecode:: http

      GET /protein/YEAST108/orthologs HTTP/1.1
      Host: omabrowser.org/api
      Accept: application/json

   **Example response**:

   .. sourcecode:: http

    HTTP 200 OK
    Allow: GET, HEAD, OPTIONS
    Content-Type: application/json
    Vary: Accept

    [
        {
            "entry_nr": 8809,
            "entry_url": "http://127.0.0.1:8000/api/protein/8809/",
            "omaid": "SCHPO02457",
            "canonicalid": "PPA2_SCHPO",
            "sequence_md5": "824e10c6011100fbe718647f432716ef",
            "RelType": "n/a",
            "Distance": -1.0,
            "Score": -1.0
        },
        {
            "entry_nr": 9550,
            "entry_url": "http://127.0.0.1:8000/api/protein/9550/",
            "omaid": "SCHPO03198",
            "canonicalid": "PPA3_SCHPO",
            "sequence_md5": "582740e600e98e48077efbd951314bf4",
            "RelType": "n/a",
            "Distance": -1.0,
            "Score": -1.0
        },
        {
            "entry_nr": 10484,
            "entry_url": "http://127.0.0.1:8000/api/protein/10484/",
            "omaid": "SCHPO04132",
            "canonicalid": "PPA1_SCHPO",
            "sequence_md5": "9c2d17b4bcc18254a5737bdfe6606ff2",
            "RelType": "n/a",
            "Distance": -1.0,
            "Score": -1.0
        }
    ]



Protein-ontology
^^^^^^^^^^^^^^^^
.. http:get:: /protein/<protein_id>/ontology

   List of ontologies for a protein entry. Protein id can be either its oma id, its canonical id or its entry number (version specific).

   **Example request**:

   .. sourcecode:: http

      GET /protein/YEAST108/ontology HTTP/1.1
      Host: omabrowser.org/api
      Accept: application/json

   **Example response**:

   .. sourcecode:: http

    HTTP 200 OK
    Allow: GET, HEAD, OPTIONS
    Content-Type: application/json
    Vary: Accept

    [
        {
            "entry_nr": 108,
            "GO_term": "GO:0003993",
            "name": "acid phosphatase activity",
            "evidence": "IDA",
            "reference": "PMID:8817921"
        },
        {
            "entry_nr": 108,
            "GO_term": "GO:0003993",
            "name": "acid phosphatase activity",
            "evidence": "IDA",
            "reference": "SGD_REF:S000039848"
        }

Protein-xref
^^^^^^^^^^^^
.. http:get:: /protein/<protein_id>/xref

   List of cross-references for a protein entry. Protein id can be either its oma id, its canonical id or its entry number (version specific).

   **Example request**:

   .. sourcecode:: http

      GET /protein/YEAST108/xref HTTP/1.1
      Host: omabrowser.org/api
      Accept: application/json

   **Example response**:

   .. sourcecode:: http

    HTTP 200 OK
    Allow: GET, HEAD, OPTIONS
    Content-Type: application/json
    Vary: Accept

    [
        {
            "xref": "6319351",
            "source": "GI",
            "entry_nr": 108,
            "omaid": "YEAST00108"
        },
        {
            "xref": "AAA73479.1",
            "source": "NCBI",
            "entry_nr": 108,
            "omaid": "YEAST00108"
        }


Pairs
^^^^^

.. http:get:: /pairs/<genome_id1>/<genome_id2>/

   Pairwise alignment of two whole genomes. Genome id can be either genome's NCBI taxon id or its 5 letter UniProt Species code.

   :query chr1: chromosome of interest in the first genome
   :query chr2: hromosome of interest in the second genome

   **Example request**:

   .. sourcecode:: http

      GET /pairs/YEAST/ASHGO/ HTTP/1.1
      Host: omabrowser.org/api
      Accept: application/json

   **Example response**:

   .. sourcecode:: http

    HTTP 200 OK
    Allow: GET, HEAD, OPTIONS
    Content-Type: application/json
    Vary: Accept

    [
        {
            "entry_1": {
                "entry_nr": 4,
                "entry_url": "http://127.0.0.1:8000/api/protein/4/",
                "omaid": "YEAST00004",
                "canonicalid": "SEO1_YEAST",
                "sequence_md5": "dac740baab1fb48df0782ef4a476b633"
            },
            "entry_2": {
                "entry_nr": 19998,
                "entry_url": "http://127.0.0.1:8000/api/protein/19998/",
                "omaid": "ASHGO03056",
                "canonicalid": "Q755I1",
                "sequence_md5": "92d70df746808a59ad8398b051c47941"
            },
            "rel_type": "n/a",
            "distance": -1.0,
            "score": -1.0
        }




Group
^^^^^
.. http:get:: /group/

   List of all the OMA groups and the links to access them, paginated at 100 entries per page.

   **Example request**:

   .. sourcecode:: http

      GET /group/ HTTP/1.1
      Host: omabrowser.org/api
      Accept: application/json

   **Example response**:

   .. sourcecode:: http

    HTTP 200 OK
    Allow: GET, HEAD, OPTIONS
    Content-Type: application/json
    Vary: Accept

    {
        "count": 4252,
        "next": "http://127.0.0.1:8000/api/group/?page=2",
        "previous": null,
        "results": [
            {
                "GroupNr": "1",
                "group_url": "http://127.0.0.1:8000/api/group/1/"
            },
            {
                "GroupNr": "2",
                "group_url": "http://127.0.0.1:8000/api/group/2/"
            },
            {
                "GroupNr": "3",
                "group_url": "http://127.0.0.1:8000/api/group/3/"
            }

Group-detail
^^^^^^^^^^^^
.. http:get:: /group/<group_id>/

   Information available for a single oma group. Group id can be either its number, its fingerprint or one of its member proteins.

   **Example request**:

   .. sourcecode:: http

      GET /group/5/ HTTP/1.1
      Host: omabrowser.org/api
      Accept: application/json

   **Example response**:

   .. sourcecode:: http

    HTTP 200 OK
    Allow: GET, HEAD, OPTIONS
    Content-Type: application/json
    Vary: Accept

    {
    "GroupNr": 5,
    "fingerprint": "n/a",
    "related_groups": "http://127.0.0.1:8000/api/group/5/close_groups/",
    "members": [
        {
            "entry_nr": 5220,
            "entry_url": "http://127.0.0.1:8000/api/protein/5220/",
            "omaid": "YEAST05220",
            "canonicalid": "ACAC_YEAST",
            "sequence_md5": "7e03887f55b66db7411fd3c7ef3caba0"
        },
        {
            "entry_nr": 6856,
            "entry_url": "http://127.0.0.1:8000/api/protein/6856/",
            "omaid": "SCHPO00504",
            "canonicalid": "ACAC_SCHPO",
            "sequence_md5": "ed4d6692ce03ba5b55640e04472d5183"
        }

Group-detail-close-groups
^^^^^^^^^^^^^^^^^^^^^^^^^

.. http:get:: /group/<group_id>/close_groups

   Sorted list of related groups for an OMA group. Groups are thought to be related if they share orthologs. Group id can be either its number, its fingerprint or one of its member proteins.

   **Example request**:

   .. sourcecode:: http

      GET /group/1/ HTTP/1.1
      Host: omabrowser.org/api
      Accept: application/json

   **Example response**:

   .. sourcecode:: http

    HTTP 200 OK
    Allow: GET, HEAD, OPTIONS
    Content-Type: application/json
    Vary: Accept

    [
        {
            "GroupNr": "0",
            "Hits": 1
        }
    ]

HOG
^^^
.. http:get:: /hog/

   List of all the Hierarchical Orthologous Groups or HOGs and the links to access them, paginated at 100 entries per page.

   :query level: filtering of the HOGs by a specific taxonomic level indicated

   **Example request**:

   .. sourcecode:: http

      GET /hog/?level=Fungi HTTP/1.1
      Host: omabrowser.org/api
      Accept: application/json

   **Example response**:

   .. sourcecode:: http

    HTTP 200 OK
    Allow: GET, HEAD, OPTIONS
    Content-Type: application/json
    Vary: Accept

    {
        "count": 868,
        "next": "http://127.0.0.1:8000/api/hog/?level=Fungi&page=2",
        "previous": null,
        "results": [
            {
                "roothog_id": "2",
                "hog_id": "HOG:0000002",
                "hog_id_url": "http://127.0.0.1:8000/api/hog/HOG:0000002/?level=Fungi"
            },
            {
                "roothog_id": "5",
                "hog_id": "HOG:0000005",
                "hog_id_url": "http://127.0.0.1:8000/api/hog/HOG:0000005/?level=Fungi"
            },
            {
                "roothog_id": "17",
                "hog_id": "HOG:0000017",
                "hog_id_url": "http://127.0.0.1:8000/api/hog/HOG:0000017/?level=Fungi"
            }


HOG-detail
^^^^^^^^^^
.. http:get:: /hog/<hog_id>/

   Basic information available for a single HOG. Hog ID can also be one of its member proteins.

   :query level: restricting a HOG to a specific taxonomic level indicated - result is a list to any subhogs at that level

   **Example request**:

   .. sourcecode:: http

      GET /hog/<hog_id>/ HTTP/1.1
      Host: omabrowser.org/api
      Accept: application/json

   **Example response**:

   .. sourcecode:: http

    HTTP 200 OK
    Allow: GET, HEAD, OPTIONS
    Content-Type: application/json
    Vary: Accept

    {
        "hog_id": "HOG:0000006",
        "root_level": "Ascomycota",
        "levels": [
            {
                "level": "Ascomycota",
                "level_url": "http://127.0.0.1:8000/api/hog/HOG:0000006/?level=Ascomycota"
            },
            {
                "level": "Schizosaccharomyces pombe (strain 972 / ATCC 24843)",
                "level_url": "http://127.0.0.1:8000/api/hog/HOG:0000006/?level=Schizosaccharomyces+pombe+%28strain+972+%2F+ATCC+24843%29"
            },
            {
                "level": "Schizosaccharomyces pombe",
                "level_url": "http://127.0.0.1:8000/api/hog/HOG:0000006/?level=Schizosaccharomyces+pombe"
            }



HOG-detail-members
^^^^^^^^^^^^^^^^^^
.. http:get:: /hog/<hog_id>/members/

   List of protein members for a single HOG. Hog ID can also be one of its member proteins.

   :query level: restricting a HOG to a specific taxonomic level indicated


   **Example request**:

   .. sourcecode:: http

      GET /hog/<hog_id>/members/ HTTP/1.1
      Host: omabrowser.org/api
      Accept: application/json

   **Example response**:

   .. sourcecode:: http

    HTTP 200 OK
    Allow: GET, HEAD, OPTIONS
    Content-Type: application/json
    Vary: Accept

    {
    "hog_id": "HOG:0000006",
    "level": "Ascomycota",
    "members": [
        {
            "entry_nr": 21,
            "entry_url": "http://127.0.0.1:8000/api/protein/21/",
            "omaid": "YEAST00021",
            "canonicalid": "FLC2_YEAST",
            "sequence_md5": "c529bd50b771663c52485b2e417806d8"
        },
        {
            "entry_nr": 2352,
            "entry_url": "http://127.0.0.1:8000/api/protein/2352/",
            "omaid": "YEAST02352",
            "canonicalid": "FLC3_YEAST",
            "sequence_md5": "f6710047bc70c28095ac77f1b20bed01"
        }


Taxonomy
^^^^^^^^
.. http:get:: /taxonomy/

   The taxonomic tree available in the database in either dictionary format or newick.

   :query type: either newick or dict. default is dictionary(dict)
   :query type: list of members to induce the taxonomy from. Member id's can be either their ncbi taxon ids or their UniProt 5 letter species codes - they just have to be consistent.

   **Example request**:

   .. sourcecode:: http

      GET /taxonomy/?type=newick&members=YEAST,ASHGO HTTP/1.1
      Host: omabrowser.org/api
      Accept: application/json

   **Example response**:

   .. sourcecode:: http

    HTTP 200 OK
    Allow: GET, HEAD, OPTIONS
    Content-Type: application/json
    Vary: Accept

    {
        "root_taxon": {
            "name": "LUCA",
            "taxon_id": "0"
        },
        "newick": "(Ashbya_gossypii_[strain_ATCC_10895_/_CBS_109.51_/_FGSC_9923_/_NRRL_Y-1056],Saccharomyces_cerevisiae_[strain_ATCC_204508_/_S288c])LUCA;"
    }



Taxonomy-root
^^^^^^^^^^^^^
.. http:get:: /taxonomy/<root_id>/

   The taxonomic tree rooted at the level indicated. Root id can be either its species name, its ncbi taxon id or its UniProt 5 letter species code.

   :query type: either newick or dict. default is dictionary(dict)

   **Example request**:

   .. sourcecode:: http

      GET /taxonomy/Fungi/?type=newick HTTP/1.1
      Host: omabrowser.org/api
      Accept: application/json

   **Example response**:

   .. sourcecode:: http

    HTTP 200 OK
    Allow: GET, HEAD, OPTIONS
    Content-Type: application/json
    Vary: Accept

    {
        "root_taxon": {
            "name": "Fungi",
            "taxon_id": "4751"
        },
        "newick": "((Ashbya_gossypii_[strain_ATCC_10895_/_CBS_109.51_/_FGSC_9923_/_NRRL_Y-1056],Saccharomyces_cerevisiae_[strain_ATCC_204508_/_S288c])Saccharomycetaceae,Schizosaccharomyces_pombe_[strain_972_/_ATCC_24843])Ascomycota;"
    }

Accesing the API
----------------

The API can be accessed with any programming laguage that can send HTTP requests and process the JSON file returned. Furthermore, a python library and an R package designed as wrappers to this API have been released and can be found at <link_to_come>.





