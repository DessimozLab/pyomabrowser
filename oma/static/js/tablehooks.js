/**
 * Created by adriaal on 03/06/16.
 */
(function(exports) {

    const release_char = JSON.parse(document.getElementById('release_char-data').textContent);

    const cases = {
        Bacteria: {cls: 'label-success', display_text: "Bacteria", tag: "B"},
        Archaea: {cls: 'label-primary', display_text: "Archaea", tag: "A"},
        Eukaryota: {cls: 'label-danger', display_text: "Eukaryota", tag: "E"},
        Viruses: {cls: 'label-warning', display_text: "Viruses", tag: "V"},
        _default: {cls: 'label-default', display_text: "unknown", tag: "?"}
    };

    const zeroPad = function(num, size) {
        if (typeof num !== "number" ){
            return num;
        }
        var s = "00000000000" + num;
        return s.substr(s.length-size);
    };

    const hogid_str = function(hogid){
        if (typeof hogid === "number"){
            return "HOG:" + release_char + zeroPad(hogid, 7);
        } else if (typeof hogid === "string"){
            if (hogid.startsWith('HOG:')){return hogid;}
            const found = hogid.match(/(?<fam>\d+)(?<sub>\..*)?/);
            if (found){
                let res = "HOG:" + release_char + zeroPad(parseInt(found.groups['fam'], 10), 7);
                if (found.groups['sub']){
                    res += found.groups['sub'];
                }
                return res;
            }
        } else {
            console.log("weird hogid to process: " + hogid);
            return hogid;
        }
    }
    const link_to_hog_page_with_hogid_text = function(hogid, level, page="iham"){
        let hog_id = hogid_str(hogid)
        let encoded_hogid = encodeURIComponent(hog_id);
        let encoded_level = ""
        if (level !== undefined){
            encoded_level = "/" + encodeURIComponent(level);
        }
        return '<a href="/oma/hog/' + encoded_hogid + encoded_level + '/' + page+ '/">' + hog_id +'</a>';

    }

    const split_sciname_into_species_and_strain = function(sciname){
        const strain_re = /\(|serogroup|serotype|serovar|biotype|subsp|pv\.|bv.|strain/;
        var pos = sciname.search(strain_re)
        if (pos > 0) {
            return {species: sciname.substring(0, pos), strain: sciname.substring(pos)};
        } else {
            return {species: sciname, strain: ""};
        }
    }

    exports.format_as_kingdom_tag = function (kingdom) {
        var cur_case = cases[kingdom] ? cases[kingdom] : cases['_default']
        return '<span class="label ' + cur_case.cls + '"><abbr class="abbrNoUnder" ' +
            'title="' + cur_case.display_text + '">' + cur_case.tag + '</abbr></span>';
    };

    exports.format_sciname = function(value, row) {
        return "<b>" + value.species + "</b> " + value.strain;
    };

    exports.HOGlist_GOE = function(value, row) {

        var s = Math.random();

        if (value.split(',').length < 5){
            return value
        }

        var str = "<span> " + value.split(',').slice(0,4).join(',')  + "</span>" +
            " <span id='span_more_hog" + s +"' style='display: none'> " + value.split(',').slice(5).join(',')  + " </span> " +
            "<br> " +
            "<b id='more_hogs" + s +"' style='cursor:pointer;' onclick='document.getElementById(\"span_more_hog" + s + "\").style.display = \"block\";document.getElementById(\"more_hogs" + s + "\").style.display = \"none\" '>(Show All...)</b>";

        return str
    };

    exports.format_sciname_from_genome_object = function(genome){
        return exports.format_sciname(split_sciname_into_species_and_strain(genome.species))
    };

    exports.format_sciname_genomes = function(value, row) {

        if (row.type === "Ancestral") {
            return '<a href="/oma/ancestralgenome/'+value+'/info/">' + value + '</a>';
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
            return '<a href="/oma/ancestralgenome/'+row.sciname+'/info/">' + row.sciname + '</a>';
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
            return '<a href="/oma/ancestralgenome/' + encodeURIComponent(value) + '/info/">' + value + '</a>';
        }
    };


    exports.format_taxonid_as_link = function(value, row){
        if (value > 0) {
            return '<a class="external" target="_blank" href="https://uniprot.org/taxonomy/' + value + '">' + value + "</a>";
        } else {
            return '<a target="_blank" href="/oma/taxmap/' + value +'/">' + value + "</a>";
        }
    };

    exports.format_entry_sequence_matches = function(value, row){

        if (value !== ""){

            if (!value.hasOwnProperty('align')){
                return ""
            }

            var seq = value.sequence;
            var pos_start = seq.indexOf(value.align)

            var endcut = pos_start + value.align.length  + 20
            if (endcut < seq.length ){
                seq = seq.slice(0,endcut);
                seq += '...'
            }

            var startcut = pos_start - 20
            if (startcut > 0 ){
                seq = seq.slice(startcut);
                seq = '...' + seq
            }

            seq = seq.replace(value.align, "<b>" + value.align + "</b>")

            return seq




            var a = value.sequence;
            var b1 = "</b>";
            var b2 = "<b>";
            var position1 = value.align[1];
            var position2 = value.align[0];

            var start = position2 - 20;
            var begin_str = '...';
            if (start < 0) {
                start = 0;
                begin_str = ''
            }

            var end = position1 + 20;
            var end_str = '';
            if (end < a.length) {
                end = position1;
                end_str = '...'
            }

            var output1 = [a.slice(0, position1), b1, a.slice(position1)].join('');
            var output = [output1.slice(0, position2), b2, output1.slice(position2)].join('');

            return [begin_str,output.slice(start, end + 20 ), end_str].join('')
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
        if (value === "Reference"){ return value; }
        return link_to_hog_page_with_hogid_text(value, undefined, "table")
    };

    exports.format_hog_api = function(value, row) {
        return link_to_hog_page_with_hogid_text(value, row.level, 'iham')
    };

    exports.format_roothog = function(value, row) {
        if (value > 0) {
            return link_to_hog_page_with_hogid_text(value)
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

    exports.format_hogid_vis = function(value) {
        return link_to_hog_page_with_hogid_text(value);
    };

    exports.format_generic_group_id = function(value, row) {
        if (row.type === "HOG") {
            if (value.includes(".")){
                return link_to_hog_page_with_hogid_text(value)
            }
            return link_to_hog_page_with_hogid_text(row.group_nr);
        }
        else if (row.type === "OMA_Group") {
            return '<a href="/oma/omagroup/' + value + '/members/">' + value + '</a>';
        }
    };


    exports.format_group_aux = function(value, row) {
        if (row.type === "HOG") {
             return " <b>Root Level: </b> " +  row.level;
        }
        else if (row.type === "OMA_Group") {
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
        let badge = '';
        if (row.is_main_isoform) {
            badge = ' <span class="badge badge-secondary">reference isoform</span>'
        }
        return '<a href="/oma/vps/' + value + '">' + value + badge + '</a>';
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
            re: /^[A-Z0-9]{1,5}_[A-Z][A-Z0-9]{2,4}$/,
            url: function(id){return "https://www.uniprot.org/uniprot/" + id;},
            img: "reviewed.gif"
        },
        'UniProtKB/TrEMBL': {
            re: /^([OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2})$/,
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
                buf = '<a class="external" target="_blank" href="' + obj.url(value)
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
