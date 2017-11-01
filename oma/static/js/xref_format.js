/**
 * Created by adriaal on 30/10/17.
 */
(function(exports) {
    var evidence = {
        EXP: {txt: "Inferred from Experiment", typ: "experimental", url: "http://www.geneontology.org/page/exp-inferred-experiment/"},
        IDA: {txt: "Inferred from Direct Assay", typ: "experimental", url: "http://www.geneontology.org/page/ida-inferred-direct-assay/"},
        IPI: {txt: "Inferred from Physical Interaction", typ: "experimental", url: "http://www.geneontology.org/page/ipi-inferred-physical-interaction/"},
        IMP: {txt: "Inferred from Mutant Phenotype", typ: "experimental", url: "http://www.geneontology.org/page/imp-inferred-mutant-phenotype/"},
        IGI: {txt: "Inferred from Genetic Interaction", typ: "experimental", url: "http://www.geneontology.org/page/igi-inferred-genetic-interaction/"},
        IEP: {txt: "Inferred from Expression Pattern", typ: "experimental", url: "http://www.geneontology.org/page/iep-inferred-expression-pattern/"},
        ISS: {txt: "Inferred from Sequence or Structural Similarity", typ: "curated", url: "http://www.geneontology.org/page/iss-inferred-sequence-or-structural-similarity/"},
        ISO: {txt: "Inferred from Sequence Orthology", typ: "curated", url: "http://www.geneontology.org/page/iso-inferred-sequence-orthology/"},
        ISA: {txt: "Inferred from Sequence Alignment", typ: "curated", url: "http://www.geneontology.org/page/isa-inferred-sequence-alignment/"},
        ISM: {txt: "Inferred from Sequence Model", typ: "curated", url: "http://www.geneontology.org/page/ism-inferred-sequence-model/"},
        IGC: {txt: "Inferred from Genomic Context", typ: "curated", url: "http://www.geneontology.org/page/igc-inferred-genomic-context/"},
        IBA: {txt: "Inferred from Biological aspect of Ancestor", typ: "curated", url: "http://www.geneontology.org/page/iba-inferred-biological-aspect-ancestor/"},
        IBD: {txt: "Inferred from Biological aspect of Descendant", typ: "curated", url: "http://www.geneontology.org/page/ibd-inferred-biological-aspect-descendent/"},
        IKR: {txt: "Inferred from Key Residues", typ: "curated", url: "http://www.geneontology.org/page/ikr-inferred-key-residues/"},
        IRD: {txt: "Inferred from Rapid Divergence", typ: "curated", url: "http://www.geneontology.org/page/ird-inferred-rapid-divergence/"},
        RCA: {txt: "Inferred from Reviewed Computational Analysis", typ: "curated", url: "http://www.geneontology.org/page/rca-inferred-reviewed-computational-analysis/"},
        TAS: {txt: "Traceable Author Statement", typ: "curated", url: "http://www.geneontology.org/page/tas-traceable-author-statement/"},
        NAS: {txt: "Non-traceable Author Statement", typ: "curated", url: "http://www.geneontology.org/page/nas-non-traceable-author-statement/"},
        IC : {txt: "Inferred by Curator", typ: "curated", url: "http://www.geneontology.org/page/ic-inferred-curator/"},
        ND : {txt: "No biological Data available", typ: "curated", url: "http://www.geneontology.org/page/nd-no-biological-data-available/"},
        IEA: {txt: "Inferred from Electronic Annotation", typ: "uncurated", url: "http://www.geneontology.org/page/automatically-assigned-evidence-codes/"},
    };

    var special_ref_map = {
        'GO_REF:007': 'GO_REF:0000002',
        'GO_REF:014': 'GO_REF:0000002',
        'GO_REF:016': 'GO_REF:0000002',
        'GO_REF:017': 'GO_REF:0000002',
        'MGI:2152098': 'GO_REF:0000002',
        'J:72247': 'GO_REF:0000002',
        'ZFIN:ZDB-PUB-020724-1': 'GO_REF:0000002',
        'FBrf0174215': 'GO_REF:0000002',
        'dictyBase_REF:10157': 'GO_REF:0000002',
        'SGD_REF:S000124036': 'GO_REF:0000002',
        'GO_REF:005': 'GO_REF:0000003',
        'MGI:2152096': 'GO_REF:0000003',
        'J:72245': 'GO_REF:0000003',
        'ZFIN:ZDB-PUB-031118-3': 'GO_REF:0000003',
        'SGD_REF:S000124037': 'GO_REF:0000003',
        'GO_REF:009': 'GO_REF:0000004',
        'GO_REF:013': 'GO_REF:0000004',
        'MGI:1354194': 'GO_REF:0000004',
        'J:60000': 'GO_REF:0000004',
        'ZFIN:ZDB-PUB-020723-1': 'GO_REF:0000004',
        'SGD_REF:S000124038': 'GO_REF:0000004',
        'MGI:2152097': 'GO_REF:0000006',
        'J:72246': 'GO_REF:0000006',
        'MGI:2154458': 'GO_REF:0000008',
        'J:73065': 'GO_REF:0000008',
        'MGI:1347124': 'GO_REF:0000010',
        'J:56000': 'GO_REF:0000010',
        'FBrf0159398': 'GO_REF:0000015',
        'ZFIN:ZDB-PUB-031118-1': 'GO_REF:0000015',
        'dictyBase_REF:9851': 'GO_REF:0000015',
        'MGI:2156816': 'GO_REF:0000015',
        'dictyBase_REF:10158': 'GO_REF:0000018',
        'SGD_REF:S000125578': 'GO_REF:0000023',
        'SGD_REF:S000147045': 'GO_REF:0000036',
        'SGD_REF:S000148669': 'GO_REF:0000037',
        'SGD_REF:S000148670': 'GO_REF:0000038',
        'SGD_REF:S000148671': 'GO_REF:0000039',
        'SGD_REF:S000148672': 'GO_REF:0000040',
        'ZFIN:ZDB-PUB-130131-1': 'GO_REF:0000041',
    };

    exports.go_ref_url = function(ref){
        var lnk = "";
        if (ref.startsWith("PMID:")){
            lnk = "http://www.ncbi.nlm.nih.gov/pubmed/" + ref.substr(5);
        } else if (special_ref_map[ref] !== undefined){
            lnk = "http://www.geneontology.org/cgi-bin/references.cgi#"+special_ref_map[ref];
        } else if (ref.startsWith("GO_REF:")){
            var refcode = ('0000000' + parseInt(ref.substr(7), 10)).slice(-7);
            lnk = "http://www.geneontology.org/cgi-bin/references.cgi#GO_REF:"+refcode;
        } else if (ref.startsWith("OMA_Fun:")){
            return '<a href="#" role="button" data-toggle="modal" data-target=".function-modal">'+ref+"</a>";
        } else if (ref.startsWith("FB:")){
            lnk = "http://flybase.org/reports/"+ref.substr(3);
        } else if (ref.startsWith("MGI:")){
            lnk = "http://www.informatics.jax.org/searches/accession_report.cgi?id="+ref;
        } else if (ref.startsWith("GR_REF:")){
            lnk = "http://www.gramene.org/db/literature/pub_search?ref_id="+ref.substr(7);
        } else if (ref.startsWith("SGD_REF:")){
            lnk = "http://www.yeastgenome.org/reference/"+ref.substr(8);
        } else if (ref.startsWith("CGD_REF:")){
            lnk = "http://www.candidagenome.org/cgi-bin/reference/reference.pl?dbid="+ref.substr(8);
        } else if (ref.startsWith("dictyBase_REF:")){
            lnk = "http://dictybase.org/db/cgi-bin/dictyBase/reference/reference.pl?refNo="+ref.substr(14);
        } else if (ref.startsWith('GEO:')){
            lnk = "http://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc="+ref.substr(4);
        } else if (ref.startsWith("WB:")){
            lnk = "http://www.wormbase.org/db/misc/paper?name="+ref.substr(3);
        } else if (ref.startsWith("ZFIN:")){
            lnk = "http://zfin.org/cgi-bin/ZFIN_jump?record="+ref.substr(5);
        } else if (ref.startsWith("TAIR:")){
            lnk = "http://arabidopsis.org/servlets/TairObject?accession="+ref.substr(5);
        } else {
            lnk = "http://www.google.com/search?q="+ref;
        }

        return '<a class="external" href="' + lnk + '">' + ref + '</a>';
    };

    exports.go_evi_url = function(evi){
        var o = evidence[evi], lnk = "";
        if (o !== undefined) {
            lnk = '<a class="' + o.typ + '" href="' + o.url + '" title="' + o.txt + '">' +
                evi + "</a>";
        } else {
            lnk = '<a class="external" href="http://www.google.com/search?q='+evi+'">'+evi+'</a>';
        }
        return lnk;
    };

    exports.go_annotation_url = function(term){
        if (term.hasOwnProperty("name") && term.hasOwnProperty("GO_term")){
            return '<a class="external" title="' + term.name +
                   '" href="http://www.ebi.ac.uk/QuickGO/GTerm?id=' +
                   term.GO_term +'#term=info">' + term.GO_term + "</a>";
        } else {
            return '<a class="external" href="http://www.ebi.ac.uk/QuickGO/GTerm?id='+
                    term + '#term=info">' + term + '</a>';
        }
    };

})(this.xref_format = {});