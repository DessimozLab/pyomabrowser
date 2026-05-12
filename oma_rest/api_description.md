The OMA Browser provides a dedicated REST API that offers programmatic access to 
its underlying database. This API exposes OMA’s data in a structured and 
language-agnostic way, making it straightforward to integrate OMA data into external 
tools, scripts, and workflows across a wide range of programming environments. By 
following REST principles, the API allows users to retrieve specific data through 
simple HTTP requests. The API endpoint is available at `https://omabrowser.org/api`.

The OMA REST API supports multiple response formats, with JSON being the default and 
most widely used due to its compatibility with web applications and modern programming 
languages. To further simplify access, we provide official client libraries that wrap 
the API and handle common tasks such as request construction and response parsing. These 
libraries offer a more convenient and user-friendly interface for working with OMA data 
in Python and R:

 - R package: [OmaDB](https://bioconductor.org/packages/OmaDB/) (Bioconductor package; [project repository](https://github.com/DessimozLab/OmaDB))
 - Python library: [OmaDB](https://github.com/DessimozLab/pyomadb) Python package


## Pagination

Many list endpoints in the OMA REST API are paginated. Pagination metadata is returned in 
HTTP response headers rather than in the response body, following the 
[RFC 8288 Web Linking specification](https://www.rfc-editor.org/rfc/rfc8288). This approach 
is widely adopted by APIs such as GitHub and GitLab.

The response body itself contains a plain JSON array of results for the requested page, while 
navigation and summary information are provided via headers:

| Header          | Description                                                           |
|-----------------|-----------------------------------------------------------------------|
| `X-Total-Count` | Total number of results across all pages                              |
| `Link`          | Navigation links with `rel=first`, `rel=prev`, `rel=next`, `rel=last` |

The `Link` header includes URLs for navigating between pages of results, allowing clients to 
easily traverse the dataset without constructing URLs manually. In addition, the 
`X-Total-Count` header reports the total number of objects matching the request across all pages.

Pagination can be controlled using the `page` and `per_page` query parameters (default page size: 100).

### Example

```bash
   curl -I "https://omabrowser.org/api/genome/?page=2"
```

```http
HTTP 200 OK
Allow: GET, HEAD, OPTIONS
Content-Type: application/json
Link: 
 <https://omabrowser.org/api/genomes/>; rel="first",
 <https://omabrowser.org/api/genomes/>; rel="prev",
 <https://omabrowser.org/api/genomes/?page=3>; rel="next",
 <https://omabrowser.org/api/genomes/?page=22>; rel="last"
Vary: Accept
X-Total-Count: 2198
```


## Changelog

### 1.11

- **`/api/taxonomy/` and `/api/taxonomy/{root_id}/`**: `?type=phyloxml` previously returned
  raw PhyloXML text; it now returns a JSON wrapper `{"root_taxon": {...}, "phyloxml": "..."}`.
  To retrieve raw PhyloXML, send `Accept: application/vnd.phyloxml+xml` instead.
  Clients that need the old behaviour can pin the version with
  `Accept: application/json; version=1.10`.

### 1.7

- **`/api/protein/bulk_retrieve` returns now a list of (query_id, target)
  tuples instead of a plain list of proteins. This is to make it easier to
  map the results back to the original query. Clients that need the old behaviour
  can pin the version with `Accept: application/json; version=1.6`.
