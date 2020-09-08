/**
 * Created by adriaal on 03/06/16.
 */
(function(exports) {
    var cases = {
        Bacteria: {cls: 'label-success', display_text: "Bacteria", tag: "B"},
        Archaea: {cls: 'label-primary', display_text: "Archaea", tag: "A"},
        Eukaryota: {cls: 'label-danger', display_text: "Eukaryota", tag: "E"},
        Viruses: {cls: 'label-warning', display_text: "Viruses", tag: "V"},
        _default: {cls: 'label-default', display_text: "unknown", tag: "?"}
    };

    exports.format_as_kingdom_tag = function (kingdom) {
        var cur_case = cases[kingdom] ? cases[kingdom] : cases['_default']
        return '<span class="label ' + cur_case.cls + '"><abbr class="abbrNoUnder" ' +
            'title="' + cur_case.display_text + '">' + cur_case.tag + '</abbr></span>';
    };

    exports.format_sciname = function(value, row) {
        return "<b>" + value.species + "</b> " + value.strain;
    };

    exports.format_sciname_genomes = function(value, row) {

        if (row.type === "Ancestral") {
            return '<a href="/oma/ancestralgenome/info/'+value+'/">' + value + '</a>';
        }

        return "<b>" + value.species + "</b> " + value.strain;
    };


    exports.format_locus = function(value, row) {
        return value.start + "..." + value.end ;
    };



    exports.format_generic_genome_link = function(value, row) {
        if (value === "Extant") {
             return '<a href="/oma/genome/' + row.uniprot_species_code + '/info/" >' + row.uniprot_species_code + "</a>";

        }

        else if (value === "Ancestral") {
            return '<a href="/oma/ancestralgenome/info/'+row.sciname+'/">' + row.sciname + '</a>';
        }
    };


    exports.format_species_code = function(value, row){
        return '<a href="/oma/genome/' + value + '/info/" >' + value + "</a>";
    };

    exports.format_species_common = function(value, row) {

        if (row.type === "Extant") {
             return value;

        }

        else if (row.type === "Ancestral") {
            return '<a href="/oma/ancestralgenome/'+value+'/info/">' + value + '</a>';
        }

    };


    exports.format_taxonid_as_link = function(value, row){
        return '<a class="external" href="https://uniprot.org/taxonomy/' + value +'">' + value + "</a>"
    };

    exports.format_entry_sequence_matches = function(value, row){

        if (value!=""){

            var a = value.sequence;
            var b1 = "</b>";
            var b2 = "<b>";
            var position1 = value.align[1];
            var position2 = value.align[0];

            var output1 = [a.slice(0, position1), b1, a.slice(position1)].join('');
            var output = [output1.slice(0, position2), b2, output1.slice(position2)].join('');

            return output
        }
        return value;
    };

    exports.format_subgenome = function(value){
        return "sub-genome "+value;
    };

    exports.add_proteinrow_attrs = function(rowdata, index) {
        return {id: rowdata.protid, 'class': "protein"};
    };

    exports.add_proteinrow_attrs_omaid = function(rowdata, index) {
        return {id: rowdata.omaid, 'class': "protein"};
    };

    exports.format_hogid = function(value, row) {
        return '<a href="/oma/hogs/' + row.ReprEntryNr 
                                      + '/">HOG:'
                                      + ('0000000' + value).slice(-7) // Format with leading 0s
                                      + '</a>';
    };
    exports.format_hog_api = function(value, row) {

        return '<a href="/oma/hog/ihamviewer/' + value + '/' +  row.level+'/">' + value + "</a>";

    };
    exports.format_roothog = function(value, row) {
        if (value > 0) {
            return '<a href="/oma/hog/ihamviewer/HOG:' + ('0000000' + value).slice(-7) + '/">HOG:' + ('0000000' + value).slice(-7) + "</a>";
        } else {
            return "n/a";
        }
    };

    exports.format_omagroup_of_entry = function(value, row){
        if (value > 0){
            return '<a href="/oma/group/'+row.protid+'/">' + value +'</a>';
        } else {
            return 'n/a';
        }
    };

    exports.format_omagroup = function(value){
        if (value > 0 || (value !== 'n/a') ){
            return '<a href="/oma/omagroup/'+value+'/">' + value + '</a>';
        } else {return 'n/a';}
    };


    exports.format_omagroup_members = function(value){
        if (value > 0 ){
            return '<a href="/oma/omagroup/'+value+'/members/">' + value + '</a>';
        } else {return 'n/a';}
    };


    exports.format_hogid_vis = function(value, row) {
        return '<a href="/oma/hogs/' + row.ReprEntryNr
                                      + '/vis/">HOG:'
                                      + ('0000000' + value).slice(-7) // Format with leading 0s
                                      + '</a>';
    };


    exports.format_generic_group_id = function(value, row) {

        if (row.type === "HOG") {
             return '<a href="/oma/hog/ihamviewer/HOG:' + ('0000000' + value).slice(-7) + '/">HOG:' + ('0000000' + value).slice(-7) + "</a>";

        }

        else if (row.type === "OMA group") {
            return '<a href="/oma/omagroup/'+value+'/members/">' + value + '</a>';
        }

    };


    exports.format_group_aux = function(value, row) {

        if (row.type === "HOG") {
             return " <b>Root Level: </b> " +  row.level;

        }

        else if (row.type === "OMA group") {
            return "<b>Fingerprint: </b> " +  row.fingerprint;
        }

    };


    exports.format_domainprevalence = function(value, row) {
        return row.PrevFrac.toFixed(1) + "%";
    };

    exports.format_empty = function(value, row) {
        return "";
    };

    exports.format_float_value = function(value, row){
        return parseFloat(value).toPrecision(3)
    };

    exports.format_info_link = function (value, row) {
        return '<a href="/oma/info/' + value + '">' + value + '</a>';
    };

    exports.format_vps_link = function(value, row){
        return '<a href="/oma/vps/' + value + '">' + value + '</a>';
    };

    exports.format_vps_link_isoforms = function(value, row){

        badge = '';
        badge2 = '';

        if (row.is_main_isoform) {

            badge = ' <span class="badge badge-secondary">reference isoform</span>'

        }


        return '<a href="/oma/vps/' + value + '">' + value  + badge+  '</a>';
    };

    exports.format_exons_isoforms = function(value, row){return value.length};

    exports.seq_search_alignment_formatter = function(value, row){
        var seq = row.sequence;
        var alignment = row.alignment;
        if (seq === undefined || alignment === undefined) return "n/a";
        var label = (row.alignment_range[0] <= 9 ? seq.substr(0, row.alignment_range[0]) : "..("+ (row.alignment_range[0]-3)+ ").."+seq.substr(row.alignment_range[0]-3, 3));
        var matched = false, snip = [];
        for (var pos=0; pos < alignment[1].length; pos++){
            if (alignment[1][pos] === "_") continue;
            if (alignment[1][pos] === alignment[0][pos]) {
                if (matched) {
                    snip.push(alignment[1][pos]);
                } else {
                    matched = true;
                    snip.push('<span class="kw1">' + alignment[1][pos]);
                }
            } else {
                if (! matched){
                    snip.push(alignment[1][pos]);
                } else {
                    matched = false;
                    snip.push('</span>', alignment[1][pos]);
                }
            }
        }
        if (matched){ snip.push("</span>"); }
        return label + snip.join("") + "..("+ (seq.length-row.alignment_range[1]) + ")..";
    };

    var xref_re = {
        'UniProtKB/SwissProt': {
            re: /[A-Z0-9]{1,5}_[A-Z][A-Z0-9]{2,4}/,
            url: function(id){return "https://www.uniprot.org/uniprot/" + id;},
            img: "reviewed.gif"
        },
        'UniProtKB/TrEMBL': {
            re: /[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2}/,
            url: function(id){return "https://www.uniprot.org/uniprot/" + id;},
            img: "unreviewed.gif"
        },
        'Ensembl': {
            re: /ENS[A-Z]{0,3}[PGT]\d{11}/,
            url: function(id){return "https://www.ensembl.org/id/"+id;},
            img: "ensembl.gif"
        },
        'FlyBase': {
            re: /FB[gnptr]{2}\d{7}/,
            url: function(id){return "http://flybase.org/reports/"+id;}
        },
    };

    exports.format_xref = function(value, row) {
        var buf = "";
        $.each(xref_re, function (src, obj) {
            if (obj.re.test(value)) {
                buf = '<a class="external" href="' + obj.url(value)
                    + '" title="' + src + '">';
                if (obj.img) {
                    buf += '<img src="'+ static_root + 'image/' + obj.img + '" alt="' + src + '" />&nbsp;'
                }
                buf += value + '</a>';
                return false;  // break the loop
            }
        });
        // in case no regex match, just display xref value
        if (buf.length === 0){
            buf = value;
        }
        return buf;
    };

})(this.tablehooks = {});
