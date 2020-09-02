/**
 * Created by adriaal on 30/10/17.
 */
(function(exports) {
    var evidence = {
        EXP: {txt: "Inferred from Experiment", typ: "experimental", url: "http://wiki.geneontology.org/index.php/Inferred_from_Experiment_(EXP)"},
        IDA: {txt: "Inferred from Direct Assay", typ: "experimental", url: "http://wiki.geneontology.org/index.php/Inferred_from_Direct_Assay_(IDA)"},
        IPI: {txt: "Inferred from Physical Interaction", typ: "experimental", url: "http://wiki.geneontology.org/index.php/Inferred_from_Physical_Interaction_(IPI)"},
        IMP: {txt: "Inferred from Mutant Phenotype", typ: "experimental", url: "http://wiki.geneontology.org/index.php/Inferred_from_Mutant_Phenotype_(IMP)"},
        IGI: {txt: "Inferred from Genetic Interaction", typ: "experimental", url: "http://wiki.geneontology.org/index.php/Inferred_from_Genetic_Interaction_(IGI)"},
        IEP: {txt: "Inferred from Expression Pattern", typ: "experimental", url: "http://wiki.geneontology.org/index.php/Inferred_from_Expression_Pattern_(IEP)"},
        HTP: {txt: "Inferred from High Throughput Experiment", typ: "experimental", url: "http://wiki.geneontology.org/index.php/Inferred_from_High_Throughput_Experiment_(HTP)"},
        HDA: {txt: "Inferred from High Throughput Direct Assay", typ: "experimental", url: "http://wiki.geneontology.org/index.php/Inferred_from_High_Throughput_Direct_Assay_(HDA)"},
        HMP: {txt: "Inferred from High Throughput Mutant Phenotype", typ: "experimental", url: "http://wiki.geneontology.org/index.php/Inferred_from_High_Throughput_Mutant_Phenotype_(HMP)"},
        HGI: {txt: "Inferred from High Throughput Genetic Interaction", typ: "experimental", url: "http://wiki.geneontology.org/index.php/Inferred_from_High_Throughput_Genetic_Interaction_(HGI)"},
        HEP: {txt: "Inferred from High Throughput Expression Pattern", typ: "experimental", url: "http://wiki.geneontology.org/index.php/Inferred_from_High_Throughput_Expression_Pattern_(HEP)"},
        ISS: {txt: "Inferred from Sequence or Structural Similarity", typ: "curated", url: "http://wiki.geneontology.org/index.php/Inferred_from_Sequence_or_structural_Similarity_(ISS)"},
        ISO: {txt: "Inferred from Sequence Orthology", typ: "curated", url: "http://wiki.geneontology.org/index.php/Inferred_from_Sequence_Orthology_(ISO)"},
        ISA: {txt: "Inferred from Sequence Alignment", typ: "curated", url: "http://wiki.geneontology.org/index.php/Inferred_from_Sequence_Alignment_(ISA)"},
        ISM: {txt: "Inferred from Sequence Model", typ: "curated", url: "http://wiki.geneontology.org/index.php/Inferred_from_Sequence_Model_(ISM)"},
        IGC: {txt: "Inferred from Genomic Context", typ: "curated", url: "http://wiki.geneontology.org/index.php/Inferred_from_Genomic_Context_(IGC)"},
        IBA: {txt: "Inferred from Biological aspect of Ancestor", typ: "curated", url: "http://wiki.geneontology.org/index.php/Inferred_from_Biological_aspect_of_Ancestor_(IBA)"},
        IBD: {txt: "Inferred from Biological aspect of Descendant", typ: "curated", url: "http://wiki.geneontology.org/index.php/Inferred_from_Biological_aspect_of_Descendant_(IBD)"},
        IKR: {txt: "Inferred from Key Residues", typ: "curated", url: "http://wiki.geneontology.org/index.php/Inferred_from_Key_Residues_(IKR)"},
        IRD: {txt: "Inferred from Rapid Divergence", typ: "curated", url: "http://wiki.geneontology.org/index.php/Inferred_from_Rapid_Divergence(IRD)"},
        RCA: {txt: "Inferred from Reviewed Computational Analysis", typ: "curated", url: "http://wiki.geneontology.org/index.php/Inferred_from_Reviewed_Computational_Analysis_(RCA)"},
        TAS: {txt: "Traceable Author Statement", typ: "curated", url: "http://wiki.geneontology.org/index.php/Traceable_Author_Statement_(TAS)"},
        NAS: {txt: "Non-traceable Author Statement", typ: "curated", url: "http://wiki.geneontology.org/index.php/Non-traceable_Author_Statement_(NAS)"},
        IC : {txt: "Inferred by Curator", typ: "curated", url: "http://wiki.geneontology.org/index.php/Inferred_by_Curator_(IC)"},
        ND : {txt: "No biological Data available", typ: "curated", url: "http://wiki.geneontology.org/index.php/No_biological_Data_available_(ND)_evidence_code"},
        IEA: {txt: "Inferred from Electronic Annotation", typ: "uncurated", url: "http://wiki.geneontology.org/index.php/Inferred_from_Electronic_Annotation_(IEA)"},
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
            var goref = special_ref_map[ref].split(':')[1];
            lnk = "http://purl.obolibrary.org/obo/go/references/"+goref;
        } else if (ref.startsWith("GO_REF:")){
            var refcode = ('0000000' + parseInt(ref.substr(7), 10)).slice(-7);
            lnk = "http://purl.obolibrary.org/obo/go/references/"+refcode;
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

    var dbxrefs = {
        'UniProtKB/SwissProt': {
            url: function(id){ return "https://uniprot.org/uniprot/"+id; },
            tooltip: "UniProtKB/SwissProt: reviewed",
            img: '<img src="'+static_root+'/image/reviewed.gif" alt="UniProtKB/SwissProt" />'
        },
        'UniProtKB/TrEMBL':{
            url: function(id){ return "https://uniprot.org/uniprot/"+id; },
            tooltip: "UniProtKB/TrEMBL: unreviewed",
            img: '<img src="'+static_root+'/image/unreviewed.gif" alt="UniProtKB/TrEMBL" />'
        },
        'RefSeq':{
            url: function(id){ return "https://www.ncbi.nlm.nih.gov/protein/"+id; },
            img: '<img src="'+static_root+'/image/ncbi.gif" alt="RefSeq" />'
        },
        'Ensembl Protein': {
            url: function(id){ return "https://www.ensembl.org/id/"+id;},
            img: '<img src="'+static_root+'/image/ensembl.gif" alt="Ensembl"/>'
        },
        'EnsemblGenomes':{
            url: function(id){ return "http://ensemblgenomes.org/id/"+id; },
            img: '<img src="'+static_root+'/image/ensembl.gif" alt="EnsemblGenomes"/>'
        },
        'PMP':{
            url: function(id){return "https://www.proteinmodelportal.org/query/up/"+id;},
            tooltip: "Protein Model Portal",
            img: '<img src="'+static_root+'/image/pmp.gif" alt="Protein Model Portal"/>'
        },
        'PDB': {
            url: function(id){return "https://www.ebi.ac.uk/pdbe/entry/pdb/"+id;},
            img: '<img src="'+static_root+'/image/pdb.gif" alt="PDB" />'
        },
        'EntrezGene': {
            url: function(id){return "///www.ncbi.nlm.nih.gov/protein/"+id;},
            img: '<img src="'+static_root+'/image/ncbi.gif" alt="NCBI" />'
        },
        'FlyBase':{
            url: function(id){ return "http://flybase.org/reports/"+id;},
            img: '<img src="'+static_root+'/image/flybase.gif" alt="Flybase" />'
        },
        'WormBase': {
            url: function(id){ return "http://www.wormbase.org/db/gene/gene?name="+id;},
            img: '<img src="'+static_root+'/image/wormbase.gif" alt="Wormbase" />'
        },
        'NCBI': {
            url: function(id){return "///www.ncbi.nlm.nih.gov/protein/"+id;},
            img: '<img src="'+static_root+'/image/ncbi.gif" alt="NCBI" />'
        },
        'HGNC': {
            url: function(id){return "https://www.genenames.org/cgi-bin/gene_symbol_report?hgnc_id="+id;},
            img: '<img src="'+static_root+'/image/hgnc.gif" alt="HGNC"/>',
            label: function(id, elem){
                $.getJSON("https://rest.genenames.org/fetch/hgnc_id/"+id, function(data){
                    if (data.hasOwnProperty("response")){
                        var res = data.response.docs[0];
                        var span = document.getElementById(elem);
                        var b = document.createElement('B')
                        b.append(res['symbol']);
                        span.append( ' ', b, ': ' + res['name']);
                    }
                });
            }
        },
        'STRING': {
            url: function(id){return "https://string-db.org/network/"+id;},
            img: '<img src="'+static_root+'/image/string.png" alt="STRING" />'
        },
        'Swiss Model': {
            url: function(id){return "https://swissmodel.expasy.org/repository/uniprot/"+id;},
            img: '<img src="'+static_root+'/image/swissmodel.png" alt="SwissModel" />'
        },
        'neXtProt': {
            url: function(id){return "https://www.nextprot.org/entry/"+id;},
            img: '<img src="'+static_root+'/image/neXtProt.png" alt="neXtProt" />'
        },
        'Bgee': {
            url: function(id){return "https://bgee.org/?page=gene&gene_id="+id;},
            img: '<img src="'+static_root+'/image/bgee.png" alt="Bgee" />'
        },
        'ChEMBL': {
            url: function(id){return "https://www.ebi.ac.uk/chembldb/target/inspect/"+id;},
            img: '<img src="'+static_root+'/image/ChEMBL.png" alt="ChEMBL" />'
        }
    };
    dbxrefs['Ensembl Gene'] = dbxrefs['Ensembl Transcript'] = dbxrefs['Ensembl Protein'];


    exports.dbxref_url = function(id, src, genome_release){
        var db;
        if (dbxrefs[src] !== undefined){
            db = dbxrefs[src];
        } else if (genome_release.match('EnsemblGenomes') && (src === "SourceID" || src === "SourceAC")){
            db = dbxrefs['EnsemblGenomes'];
        } else {
            return id;
        }

        var elem = '<a class="external" href="'+db.url(id)+'" title="';
        if (db.tooltip === undefined){ elem +=  src; } else {elem += db.tooltip;}
        elem += '">';
        if (db.img) {
            elem += db.img + "&nbsp;";
        }
        elem += id + "</a>";
        if (db.label !== undefined) {
            var span_id = src+'_'+id;
            elem = '<span id="'+span_id+'">' + elem + '</span>';
            db.label(id, span_id);
        }
        return elem;

    };

})(this.xref_format = {});
